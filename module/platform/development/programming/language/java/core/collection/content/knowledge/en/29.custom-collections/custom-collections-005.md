# Writing an Iterator, Supporting remove, and Managing Cursor State

## An Iterator Is a Stateful Traversal

A collection holds data; an `Iterator<E>` describes a pass through that data. An iterator is not merely a function that "gets the element at index i". It must also remember how far it has progressed and which element is currently eligible for removal.

Suppose a collection contains the elements:

~~~text
[A, B, C, D]
~~~

After the iterator returns `B`, there are two distinct pieces of information:

- The next `next()` call must return `C`.
- The next valid `remove()` call must remove `B`.

If a single variable without a clear meaning is used for both, removal can easily cause the cursor to skip over `C`, mistakenly remove `C`, or allow `B` to be removed a second time.

This lesson focuses on a forward iterator over array storage, then relates it to iterators over linked nodes and bidirectional `ListIterator`s. The complete example manages the array, element shifting, and removal state itself so that the reason behind every update step is visible.

Three terms will be used:

| Term | Meaning in the Example |
| --- | --- |
| `cursor` | Index of the element that `next()` will return on the next successful call |
| `lastReturned` | Index of the element most recently returned by `next()` and not yet removed by this iterator |
| `expectedModCount` | The structural version number expected by the iterator |

Variable names are just a choice for the example. What must be preserved are their meanings and invariants.

## The Contract to Satisfy Before Writing Code

`Iterator` has two foundational read methods:

- `hasNext()` indicates whether more elements remain to be read.
- `next()` returns the next element; if none remain, it throws `NoSuchElementException`.

`remove()` is an optional operation: if supported, it removes the element most recently returned by the iterator, at most once per successful `next()` call. The default implementation of `Iterator.remove` throws `UnsupportedOperationException`. These conditions are specified in [Java 17 Iterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html).

This leads to several important requirements:

1. Calling `next` does not require calling `hasNext` first.
2. Calling `hasNext` multiple times must not consume unreturned elements.
3. `null` can be a valid element if the collection permits it; do not use it to signal the end of data.
4. An iterator that supports removal must reject `remove` before the first valid read.
5. After a successful removal, there must be a new successful read before removing again.
6. `hasNext` returning `false` does not cancel the right to remove the last element just returned.

The final point is easy to confuse. "No more elements ahead" is different from "no recently returned element to remove". An iterator can return the last element, check that no more elements remain, and then remove that very last element.

### Distinguishing Three Types of Errors

| Situation | Appropriate Exception |
| --- | --- |
| Removal via iterator is not supported | `UnsupportedOperationException` |
| Removal is supported, but there is no valid recently returned element or it has already been removed | `IllegalStateException` |
| `next` is called when no more data remains | `NoSuchElementException` |

If an implementation chooses a policy of detecting external structural modifications, it may also throw `ConcurrentModificationException` at specified points.

When a single call violates multiple conditions simultaneously, one should not rely on a universal exception-checking order across all implementations. The example below actively checks the `remove` state first, and only then checks for structural modification. The test cases exercise each condition separately so that the results have a clear meaning.

## State Design for an Array-Backed Iterator

Suppose the active array is used in the range `[0, size)`. Slots from `size` onward are the unoccupied region of the collection.

When no out-of-protocol modifications have occurred and the iterator remains valid, maintain these invariants:

~~~text
0 <= cursor <= size

lastReturned == -1
    or is the index of the element most recently returned by next, not yet removed

valid lastReturned after next:
    lastReturned == cursor - 1
~~~

Initialization:

~~~text
cursor = 0
lastReturned = -1
expectedModCount = collection's modCount when the iterator is created
~~~

`-1` is the signal for "no valid removal target yet". Do not use `null` for that meaning, because the data itself may contain `null`.

### hasNext Only Observes

In this simple design:

~~~java
@Override
public boolean hasNext() {
    return cursor < size;
}
~~~

It does not increment `cursor`, does not set `lastReturned`, and does not read and discard an element.

If `hasNext` is called twice before `next`, the next element must still be the initial element. If `hasNext` incremented the index, the common loop below would skip data:

~~~java
while (iterator.hasNext()) {
    E value = iterator.next();
    use(value);
}
~~~

The snippet above only illustrates usage; `use` represents an application action.

In the example, `hasNext` does not check the structural version. This is a specific choice, not a guarantee that `hasNext` remains meaningful after every external modification. Version checks are placed in `next` and valid `remove` calls.

### next Must Check for Exhaustion Itself

A successful `next` call does three things:

1. Checks that the iterator has not been invalidated by external structural modification.
2. Checks `cursor < size`.
3. Reads the element at `cursor`, remembers the position just returned, and increments `cursor`.

Core form:

~~~java
E value = elementAt(cursor);
lastReturned = cursor;
cursor++;
return value;
~~~

The read is performed after checking bounds. Do not increment the cursor first and only then detect exhaustion, and do not let the array storage's `ArrayIndexOutOfBoundsException` substitute for the iterator's `NoSuchElementException`.

A valid `next` returning `null` is still a successful read. Afterward, `remove` can remove the `null` element just read if the iterator supports removal.

## remove on an Array: Accounting for Shifted Elements

Before removing `B`:

~~~text
Index:          0   1   2   3
Data:          [A,  B,  C,  D]
                        ^
cursor = 2 ------------+
lastReturned = 1
~~~

`cursor = 2` means the next read will return `C`. When removing at index `1`, `C` and `D` shift to the left:

~~~text
Index:          0   1   2
Data:          [A,  C,  D]
                    ^
new cursor = 1 ----+
~~~

If `cursor = 2` were kept, the next call would return `D` and skip `C`. Therefore, after a successful removal:

~~~java
cursor = lastReturned;
lastReturned = -1;
~~~

For the forward iterator in the example, `lastReturned` equals `cursor - 1` right before removal, so setting `cursor = lastReturned` is equivalent to moving the cursor back by one position. Writing it in terms of the removal target makes the reasoning clearer.

`lastReturned = -1` prevents removing twice after the same `next`. If you only adjusted the cursor and forgot to clear the old target marker, the next `remove` call could delete the element that was just shifted into that position.

### Three Data Removal Steps and One State Maintenance Step

The array storage's removal method needs to:

1. Shift the segment after the removal target to the left.
2. Decrement `size`.
3. Clear the reference in the trailing slot that is no longer used.
4. Increment the structural modification version.

For example, with `[A,B,C,D]` in an array with capacity greater than four, after removing `B`, the active portion is `[A,C,D]`. The old slot that previously held `D` behind the new `size` must be set to `null`.

Setting the trailing slot to `null` does not "delete the object from the JVM". It simply drops an unneeded reference from the array. The object remains alive if another place still holds a reference, such as the variable returned earlier by `next`.

Updating the iterator's state is performed only after the data removal operation succeeds. Do not set `lastReturned = -1` before performing an operation that might fail and leave the iterator unable to tell whether it actually removed the element.

## Removing by Position, Not by equals

An error-prone way to write it:

~~~java
@Override
public void remove() {
    collection.remove(lastValue);
}
~~~

This illustrates a bug when the collection contains equal elements and `remove(Object)` removes the first equal match.

Suppose the data contains:

~~~text
[X#first, X#second, Y#tail]
~~~

The two objects `X#first` and `X#second` have different identities, but `equals` considers them equal. The iterator has read both and just returned `X#second`.

`Iterator.remove` must remove the exact occurrence that was just returned, leaving `X#first`. Calling `collection.remove(lastValue)` may search from the beginning and remove `X#first`.

Storing the position or node just returned is how the removal operation is tied to the exact element of the traversal. A value that compares equal is not enough to identify the position.

A similar issue arises with map entries, queues with duplicate elements, or a filtered view. Before delegating `remove`, you must know whether the delegate still points to the exact element that the outer iterator returned.

## Structural Modification and expectedModCount

If elements are added to or removed from the collection directly while an iterator holds indices, those indices may no longer accurately describe the traversed data segment. A common policy is to detect this and refuse to continue, often called fail-fast.

The example uses:

~~~text
Collection:
    modCount

Each iterator:
    expectedModCount
~~~

Each time an addition or removal succeeds, the collection increments `modCount`. The iterator records the version when it is created. Before `next` and before a `remove` with a valid target, it compares the two numbers. If they differ, it throws `ConcurrentModificationException`.

### Why Doesn't an Iterator Invalidating Through Its Own remove Break Itself?

A valid `remove` also changes the structure, so `modCount` increments. The iterator knows that it performed the change itself and has already adjusted its cursor. Therefore, after removal, it updates:

~~~java
expectedModCount = modCount;
~~~

If this line is omitted, the very next `next` call after a valid iterator removal will report a structural modification error.

If there are two iterators, each keeps its own version. The first iterator removes an element and resynchronizes its own version. The second iterator does not have its cursor automatically fixed; it retains the old version and will be caught when it reaches a check point.

Do not update the expected version of every iterator to "avoid errors". Doing so only masks the fact that another iterator's cursor has not been adjusted.

### Fail-Fast Is Not a Synchronization Mechanism

Matching version numbers do not prove the absence of a data race. An `int` counter does not create a lock, does not make read/write operations transactional, and does not provide a safe concurrent access policy.

`ConcurrentModificationException` can occur within a single thread if that thread modifies the collection directly and then continues using an old iterator. Conversely, when unsynchronized updates occur across multiple threads, you must not rely on the exception being guaranteed to appear. The [ConcurrentModificationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ConcurrentModificationException.html) documentation clearly states that this is a best-effort bug-detection mechanism.

For a custom collection, you should document its concurrency policy separately. The example in this lesson is intended for sequential use or proper external synchronization; it does not provide a snapshot iterator or an iterator for concurrent updates.

## Complete Program: Writing an Iterator with remove

Save this as `IteratorCursorDemo.java`. The program uses Java 17+ with no external libraries.

`ArrayBag` is a fixed-capacity collection so that array resizing management does not distract from the lesson. It allows duplicates and `null`, and traverses elements in insertion order. When full, `add` throws `IllegalStateException`. The utility method `bag(...)` allocates enough capacity for small experiments.

`Cursor` is a non-`static` inner class, so it accesses the data of its enclosing `ArrayBag` instance directly. Each `iterator()` call creates a new `Cursor` with its own independent state.

The tests cover middle/end removal, consecutive removals, duplicate elements by `equals`, two iterators, modification outside the iterator, `null` data, a read-only iterator, `removeIf`, `forEachRemaining`, and a section using a standard `ListIterator` to contrast bidirectional cursors.

~~~java
import java.util.AbstractCollection;
import java.util.ArrayList;
import java.util.Collection;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;
import java.util.ListIterator;
import java.util.NoSuchElementException;
import java.util.Objects;

public class IteratorCursorDemo {
    static final class ArrayBag<E> extends AbstractCollection<E> {
        private final Object[] elements;
        private int size;
        private int modCount;

        ArrayBag(int capacity) {
            if (capacity < 0) {
                throw new IllegalArgumentException("negative capacity");
            }
            elements = new Object[capacity];
        }

        @Override public int size() {
            return size;
        }

        @Override public boolean add(E value) {
            if (size == elements.length) {
                throw new IllegalStateException("bag is full");
            }
            elements[size++] = value;
            modCount++;
            return true;
        }

        private void removeAt(int index) {
            Objects.checkIndex(index, size);
            int moved = size - index - 1;
            if (moved > 0) {
                System.arraycopy(elements, index + 1, elements, index, moved);
            }
            elements[--size] = null;
            modCount++;
        }

        @SuppressWarnings("unchecked")
        private E elementAt(int index) {
            return (E) elements[index];
        }

        @Override public Iterator<E> iterator() {
            return new Cursor();
        }

        private final class Cursor implements Iterator<E> {
            private int cursor;
            private int lastReturned = -1;
            private int expectedModCount = modCount;

            private void checkForModification() {
                if (expectedModCount != modCount) {
                    throw new ConcurrentModificationException();
                }
            }

            @Override public boolean hasNext() {
                return cursor < size;
            }

            @Override public E next() {
                checkForModification();
                if (cursor >= size) {
                    throw new NoSuchElementException();
                }
                E value = elementAt(cursor);
                lastReturned = cursor;
                cursor++;
                return value;
            }

            @Override public void remove() {
                if (lastReturned < 0) {
                    throw new IllegalStateException();
                }
                checkForModification();
                removeAt(lastReturned);
                cursor = lastReturned;
                lastReturned = -1;
                expectedModCount = modCount;
            }
        }
    }

    static final class Token {
        private final String value;
        private final String tag;

        Token(String value, String tag) {
            this.value = value;
            this.tag = tag;
        }

        @Override public boolean equals(Object other) {
            return other instanceof Token token && value.equals(token.value);
        }

        @Override public int hashCode() {
            return value.hashCode();
        }

        @Override public String toString() {
            return value + "#" + tag;
        }
    }

    @SafeVarargs
    static <E> ArrayBag<E> bag(E... values) {
        ArrayBag<E> bag = new ArrayBag<>(Math.max(16, values.length));
        for (E value : values) {
            bag.add(value);
        }
        return bag;
    }

    static String outcome(Runnable action) {
        try {
            action.run();
            return "OK";
        } catch (RuntimeException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    static <E> Iterator<E> readOnly(Iterator<E> source) {
        return new Iterator<>() {
            @Override public boolean hasNext() { return source.hasNext(); }
            @Override public E next() { return source.next(); }
        };
    }

    public static void main(String[] args) {
        ArrayBag<String> words = bag("A", "B", "C", "D");
        Iterator<String> it = words.iterator();
        System.out.println("remove-before-next = " + outcome(it::remove));
        System.out.println("repeated-hasNext = " + it.hasNext() + "," + it.hasNext());
        System.out.println("first = " + it.next());
        System.out.println("second = " + it.next());
        it.remove();
        System.out.println("after-remove-B = " + words);
        System.out.println("next-after-shift = " + it.next());
        it.remove();
        System.out.println("after-remove-C = " + words);
        System.out.println("remove-twice = " + outcome(it::remove));
        System.out.println("last = " + it.next());
        System.out.println("hasNext-at-end = " + it.hasNext());
        it.remove();
        System.out.println("after-remove-last = " + words);
        System.out.println("next-at-end = " + outcome(it::next));

        ArrayBag<Integer> all = bag(1, 2, 3, 4);
        List<Integer> visited = new ArrayList<>();
        Iterator<Integer> every = all.iterator();
        while (every.hasNext()) {
            visited.add(every.next());
            every.remove();
        }
        System.out.println("remove-all-visited = " + visited);
        System.out.println("remove-all-result = " + all);

        Token first = new Token("X", "first");
        Token second = new Token("X", "second");
        ArrayBag<Token> duplicates = bag(first, second, new Token("Y", "tail"));
        Iterator<Token> duplicateIt = duplicates.iterator();
        duplicateIt.next();
        System.out.println("duplicate-last-returned = " + duplicateIt.next());
        duplicateIt.remove();
        System.out.println("duplicate-after-remove = " + duplicates);

        ArrayBag<String> shared = bag("A", "B", "C");
        Iterator<String> left = shared.iterator();
        Iterator<String> right = shared.iterator();
        System.out.println("independent-first = " + left.next() + "," + right.next());
        left.remove();
        System.out.println("removing-iterator-continues = " + left.next());
        System.out.println("other-iterator = " + outcome(right::next));
        Iterator<String> stale = shared.iterator();
        shared.add("D");
        System.out.println("external-add = " + outcome(stale::next));

        ArrayBag<String> nullable = bag(null, "tail");
        Iterator<String> nullableIt = nullable.iterator();
        System.out.println("null-is-value = " + nullableIt.next());
        System.out.println("after-null-hasNext = " + nullableIt.hasNext());
        nullableIt.remove();
        System.out.println("after-remove-null = " + nullable);

        Iterator<String> readOnly = readOnly(bag("R").iterator());
        System.out.println("read-only-next = " + readOnly.next());
        System.out.println("read-only-remove = " + outcome(readOnly::remove));
        Iterator<String> empty = IteratorCursorDemo.<String>bag().iterator();
        System.out.println("empty-hasNext = " + empty.hasNext());
        System.out.println("empty-next = " + outcome(empty::next));

        ArrayBag<Integer> numbers = bag(1, 2, 3, 4, 5, 6);
        System.out.println("removeIf-changed = " + numbers.removeIf(n -> n % 2 == 0));
        System.out.println("removeIf-result = " + numbers);
        Iterator<String> rest = bag("F", "G", "H").iterator();
        System.out.println("before-forEachRemaining = " + rest.next());
        List<String> remaining = new ArrayList<>();
        rest.forEachRemaining(remaining::add);
        System.out.println("forEachRemaining-result = " + remaining);
        System.out.println("forEachRemaining-null = "
                + outcome(() -> rest.forEachRemaining(null)));

        List<String> list = new ArrayList<>(List.of("A", "B", "C"));
        ListIterator<String> both = list.listIterator(2);
        System.out.println("list-previous = " + both.previous());
        both.remove();
        System.out.println("list-next-after-remove = " + both.next());
        System.out.println("list-previous-again = " + both.previous());
        both.set("X");
        both.add("Y");
        System.out.println("list-after-set-add = " + list);
        System.out.println("list-set-after-add = " + outcome(() -> both.set("Z")));
        System.out.println("list-previous-after-add = " + both.previous());
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 -encoding UTF-8 IteratorCursorDemo.java
java IteratorCursorDemo
~~~

The code was compiled with `--release 17` and run using OpenJDK Zulu 24.0.2. Exact stdout:

~~~text
remove-before-next = IllegalStateException
repeated-hasNext = true,true
first = A
second = B
after-remove-B = [A, C, D]
next-after-shift = C
after-remove-C = [A, D]
remove-twice = IllegalStateException
last = D
hasNext-at-end = false
after-remove-last = [A]
next-at-end = NoSuchElementException
remove-all-visited = [1, 2, 3, 4]
remove-all-result = []
duplicate-last-returned = X#second
duplicate-after-remove = [X#first, Y#tail]
independent-first = A,A
removing-iterator-continues = B
other-iterator = ConcurrentModificationException
external-add = ConcurrentModificationException
null-is-value = null
after-null-hasNext = true
after-remove-null = [tail]
read-only-next = R
read-only-remove = UnsupportedOperationException
empty-hasNext = false
empty-next = NoSuchElementException
removeIf-changed = true
removeIf-result = [1, 3, 5]
before-forEachRemaining = F
forEachRemaining-result = [G, H]
forEachRemaining-null = NullPointerException
list-previous = B
list-next-after-remove = C
list-previous-again = C
list-after-set-add = [A, Y, X]
list-set-after-add = IllegalStateException
list-previous-after-add = Y
~~~

## Reading the Results Through Cursor State

### hasNext Does Not Consume Elements

`repeated-hasNext = true,true` is printed before reading. Two checks do not lose `A`; `first = A` is still the first element.

`remove-before-next = IllegalStateException` confirms there is no valid removal target yet. This is an iterator that supports `remove` where the call occurs in an invalid state, unlike a read-only iterator that does not support the operation at all.

### Removal Does Not Skip Shifted Elements

After reading `A` and `B`, `remove` leaves `[A,C,D]`. The line `next-after-shift = C` proves that the cursor was moved back to the position now holding `C`.

Removing `C` next leaves `[A,D]`. Another removal without reading first receives `IllegalStateException`. Afterward, the iterator still reads `D`.

`hasNext-at-end = false` appears after returning `D`. Even though no next element remains, `remove` still deletes `D` and leaves the collection with `[A]`. Do not use `hasNext` as the condition deciding whether the just-returned element can be removed.

### Removing All Elements Tests Both the Leading and Empty Boundaries

The loop that reads and removes every element collects the full `[1,2,3,4]` and leaves a final collection of `[]`. If you forget to move the cursor back after each array shift, this test typically skips every other element.

It also verifies that when removing the element at index zero, subsequent elements are handled properly; and after the final removal, both `cursor` and `size` return to zero.

### Two Equal Elements Must Still Remove the Exact Occurrence

`Token.equals` compares only the `value` field, while `tag` makes each distinct object visible in stdout.

The iterator just returned `X#second`. After removal, the result `[X#first,Y#tail]` shows that the removal target was determined by the recently returned position. Keeping `X#second` and removing `X#first` would be wrong, even though a list comparison based solely on `equals` might fail to detect it.

When testing structures with duplicate elements, use data whose identity or position can be distinguished. Testing only distinct strings will not catch value-based removal bugs.

### Two Iterators Have Independent Cursors and Versions

`independent-first = A,A` shows that two iterators both start from the beginning rather than sharing a single index variable inside the collection.

After `left` removes `A`, it continues to return `B` itself because it adjusted its cursor and version. `right` retains the old version, so `right.next` throws `ConcurrentModificationException`.

Creating another iterator and then calling `shared.add("D")` directly also causes the stale iterator to be rejected on `next`. This is a deterministic single-threaded test, not a randomized multi-threaded scheduling test.

### null Is Not the End of Data

`null-is-value = null` is a successful read result. `after-null-hasNext = true` shows that `tail` still remains.

After `nullableIt.remove`, the collection is `[tail]`. If `lastValue == null` were used to infer that `next` had not been called, the iterator would mistakenly reject this removal. The variable `lastReturned = -1` avoids mixing control state with data values.

### Read-Only Iterators Have a Different remove Contract

The `readOnly` method delegates only `hasNext` and `next`, keeping the default implementation of `Iterator.remove`. It can read `R`, but removing receives `UnsupportedOperationException`.

This is an illustrative wrapper class and does not turn the underlying collection into an immutable collection: if another place still holds a reference to the collection, it can modify it through permitted APIs. It only blocks removal through the returned iterator.

### Inherited Operations Work When the Iterator Is Correct

`ArrayBag` does not implement `removeIf` itself. The default implementation on `Collection` uses the iterator and removes elements matching the predicate. The result `[1,3,5]` shows that removing multiple elements in a single pass does not corrupt the cursor.

Other operations on `AbstractCollection` can also rely on the iterator. Therefore, supporting `remove` properly does not just serve hand-written loops; it also enables inherited removal operations. See [AbstractCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html) and [Collection.removeIf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#removeIf(java.util.function.Predicate)).

## Do Not Mix remove with Traversal Mechanisms Outside the Protocol

### for-each Hides the Iterator from the Loop Body

For a standard `Iterable`, the `for-each` loop uses an iterator to traverse. Inside the loop body, the element variable is not the iterator; calling `collection.remove(value)` modifies the collection through a different path.

An illustrative snippet to avoid when the collection does not permit modification outside the traversal protocol:

~~~java
for (String value : values) {
    if (shouldDelete(value)) {
        values.remove(value);
    }
}
~~~

`shouldDelete` here represents an application condition. The explicit way to write this when you want to remove via the iterator is:

~~~java
Iterator<String> iterator = values.iterator();
while (iterator.hasNext()) {
    String value = iterator.next();
    if (shouldDelete(value)) {
        iterator.remove();
    }
}
~~~

The second approach still requires an iterator that supports `remove`. A read-only collection, a snapshot iterator, or another implementation may reject it. There is no rule that every iterator of every collection is modifiable.

For simple cases, `values.removeIf(this::shouldDelete)` can express the intent more concisely if the collection supports it. However, the callback should not directly modify the collection currently being traversed by that method.

How `for-each` translates for `Iterable` is specified in [JLS 14.14.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.14.2). For arrays, `for-each` uses a different mechanism and does not create an `Iterator` on which `remove` can be called.

### forEachRemaining Is Not an Iterator Removal Loop

`forEachRemaining` passes the remaining elements to an action. In the program, the iterator already read `F`, so the remaining elements collected are `[G,H]`.

There are three limitations to remember:

- The action should not modify the source collection, including calling `iterator.remove` from inside the callback, unless the implementation explicitly documents a policy permitting it.
- The behavior of `remove` after `forEachRemaining` is not specified by the general `Iterator` contract.
- If the callback throws an exception, do not assume the subsequent state of the iterator has a universal meaning across all implementations.

Therefore, do not infer that because the default implementation takes the form of a "`hasNext/next` loop", interleaving `remove` in any manner is guaranteed to work like an explicit loop. When removal is needed, use an explicit `next/remove` loop or `removeIf` according to the contract.

The program does not call `remove` after `forEachRemaining`. It only verifies that the remaining data was delivered and that passing a `null` action throws `NullPointerException`, even when the iterator has already been exhausted. These constraints are documented in [Iterator.forEachRemaining](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#forEachRemaining(java.util.function.Consumer)).

## Extending to ListIterator: The Cursor Sits Between Elements

A forward `Iterator` only needs the concept of the next element to read. A `ListIterator` also moves backward, inserts at the cursor, and replaces the most recently returned element. Consequently, the cursor must be clearly separated from the target element of `remove/set`.

For a three-element list, there are four cursor positions:

~~~text
Cursor positions:
    0     1     2     3
    |  A  |  B  |  C  |
~~~

If `cursor = 2`:

- `next` returns `C` and moves the cursor to `3`.
- `previous` returns `B` and moves the cursor to `1`.

There is no single "current element" at the cursor; it is a boundary between the previous and next elements. `remove/set` act on the element most recently returned by `next` or `previous`. See [ListIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html).

### Adjustment Formula After Bidirectional Removal

Representing the cursor as the index of the element that `next` would return, suppose `lastReturned` is the index of the removal target before shifting the array:

~~~text
Remove at lastReturned:

if lastReturned < cursor:
    decrement cursor by 1
otherwise:
    keep cursor unchanged

lastReturned = -1
~~~

Why not always decrement?

- After `next`, the just-returned element lies before the cursor. Removing it shifts subsequent elements left, so the cursor must decrement.
- After `previous`, the just-returned element lies right at the new cursor index. Removing it shifts the following element into that exact index, so the cursor stays unchanged.

In this array model, setting `cursor = lastReturned` after removal also produces the right result in both directions because the relationship between the two variables changes depending on the direction just traveled. What must not be applied mechanically is always executing `cursor--`: after `previous`, doing so would step back one position too far. When changing the cursor representation or moving to linked nodes, derive the update from the specific invariants of that structure.

### add and set Have Different State Effects

`ListIterator.add(e)` inserts before the element that `next` would return and after the element that `previous` would return. In terms of indices, it inserts at `cursor` and then increments `cursor` so the cursor sits after the new element.

After insertion:

- A `next` call still advances to the element that was originally after the cursor.
- A `previous` call returns the newly added element.
- You cannot call `remove` or `set` based on a read prior to the insertion; there must be a new `next/previous` call first.

`set(e)` only replaces the just-returned element; it does not move the cursor and does not add or remove positions. If supported, it does not consume the right to call `set` the way `remove` consumes the right to remove. However, calling `remove/add` after a read invalidates the prior `set` eligibility.

The final section of the program uses `ArrayList.listIterator(2)`:

1. `previous` returns `B`.
2. Removes `B`.
3. `next` returns `C`, without skipping it.
4. `previous` returns `C` again.
5. `set("X")` replaces `C` with `X`.
6. `add("Y")` produces `[A,Y,X]`.
7. `set` immediately after `add` receives `IllegalStateException`.
8. `previous` returns `Y`, the newly added element.

This contrasts the behavior of the standard API. The `ArrayBag.Cursor` class in this lesson only implements a forward `Iterator` and does not claim support for `previous/add/set`.

## When the Backing Storage Is Linked Nodes

With a linked list, removing a node typically does not shift an entire data segment. However, the removal target state still needs to be tracked.

For example:

~~~text
A -> B -> C -> D

already returned B
next node to return = C
last returned node  = B
~~~

Removing `B` must link `A` to `C`, while the position to visit next remains `C`.

With a singly linked list, an iterator usually needs enough information to locate the node preceding the removal target, or uses a sentinel structure and tracks predecessor nodes. Keeping only `nextNode` is generally not enough to remove the just-returned node in constant time.

Cases that must be considered individually:

- Removing the head node: update the list head.
- Removing the tail node: update the tail if one is maintained.
- Removing the only node: both head and tail return to the empty state.
- Removing multiple consecutive nodes via the iterator: the predecessor and new target must not point to an already unlinked node.
- Two iterators: modification through one iterator does not automatically fix the cursor of the other iterator.

With a doubly linked list, knowing the exact node helps relink both sides, but a `ListIterator` must still properly update its position and the direction most recently traversed. Different data structures change the removal algorithm, not the iterator contract. The standard `LinkedList` is an example of a doubly linked list with an iterator and list iterator, described in [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html).

## Wrapper Iterators and Lookahead in hasNext

For an array iterator, `hasNext` simply compares indices. For a filtering iterator, to know whether a matching element exists, `hasNext` may need to read ahead from an underlying iterator and buffer that element.

Lookahead is fine as long as the externally observable contract holds: calling `hasNext` multiple times does not skip elements, `next` returns the buffered element, and exhaustion is reported accurately.

However, `remove` becomes harder. Consider:

1. The outer iterator returns element `A`.
2. The caller invokes `hasNext`.
3. The outer iterator calls `delegate.next` multiple times to find the next matching element `C`.
4. The caller invokes `remove` on the outer iterator expecting to remove `A`.

If you simply call `delegate.remove` at this point, the delegate's target may now be `C`, no longer `A`. Merely delegating methods with matching names is insufficient.

There are three design directions:

- Do not support `remove` in the wrapper and document this clearly.
- Maintain a mechanism to remove the exact returned target, if the backing storage or protocol permits it.
- Redesign the traversal/lookahead strategy so that the published contract is preserved.

You must never silently remove a different element just because "the underlying iterator can only remove its most recent element". Supporting an optional operation is a choice; removing the right target once supported is an obligation.

Similarly, a snapshot iterator should not simply call `source.remove(value)` to simulate removal if doing so cannot identify the exact occurrence and lifecycle of the original element.

## Common Implementation Pitfalls

| Pitfall | Consequence | Fix According to the Lesson's Model |
| --- | --- | --- |
| `hasNext` increments `cursor` | Checking loses elements | Only observe; if looking ahead, maintain a stable buffer |
| `next` assumes the caller always checks first | Exhaustion causes storage errors or returns wrong results | Check bounds itself and throw `NoSuchElementException` |
| Using `null` as an unread marker | Cannot remove a valid `null` element | Keep a separate state flag/index |
| Removing from an array without fixing `cursor` | Skips the element just shifted left | Move the cursor to the exact position to read next |
| Forgetting to reset `lastReturned` | Removes twice after a single read | Clear the valid target after a successful `remove` |
| Calling `remove(Object)` by value | Removes the wrong equal occurrence | Remove by the returned index/node |
| Forgetting to update expected version after self-removal | Iterator reports an error on its own next step | Resynchronize the version of the iterator that just adjusted itself |
| Sharing a single cursor across all iterators | Two traversals interfere with each other | Keep state inside each individual iterator instance |
| Not clearing unused trailing array slots | Retains obsolete object references | Set the slot behind the active segment to `null` |
| Swallowing modification errors and continuing with old indices | Reads or removes the wrong data | Do not auto-recover without a protocol that repairs cursor state |

Another pitfall is returning the exact same partially used iterator object from every `collection.iterator()` call. For a general-purpose collection supporting multiple traversals, each pass needs its own independent state. Two nested `for-each` loops should not share a single cursor.

A single-use data source may have a different contract, but it must clearly document that it is single-use. Do not apply that choice to a collection where callers expect to create independent traversals. The role of `Iterable.iterator` and loops is introduced in [Iterable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Iterable.html).

## How to Test an Iterator Supporting remove

Test sequences of operations, not just individual methods in isolation.

### Basic State Sequence

~~~text
create iterator
-> remove: state error
-> hasNext, hasNext: does not advance
-> next: receives first element
-> remove: succeeds
-> remove: state error
-> next: receives the right next element
~~~

Repeat on an empty collection, a single-element collection, and a multi-element collection. With a single element, make sure to test the case where no elements remain ahead, yet the just-returned element can still be removed.

### Data Sequence with Duplicate Elements and null

Use two objects that are equal according to `equals` but have distinguishable identities; advance to the second object and remove it. Verify that the first object is the one that remains.

Use a `null` element if the collection permits it. Reading `null` must succeed, the subsequent check must be accurate, and removing `null` must follow the exact same state rules.

### Structural Modification Sequence

With a published fail-fast policy:

- Create an iterator, modify the collection directly, and then call a check point on the iterator.
- Create two iterators, remove via one iterator, and verify that this iterator continues traversing properly.
- Verify that the other iterator does not silently resynchronize without fixing its cursor.
- Separately verify that a failed operation does not increment the version as if the structure had changed.

These sequential tests catch cursor logic bugs much better than a randomized multi-threaded test. If concurrent updates must be supported, design and test specifically for that concurrency model rather than merely adding a counter.

### Interaction Sequence with Inherited Methods

Test `remove(Object)`, `removeIf`, `clear`, and other inherited operations that the collection claims to support. If they rely on the iterator, cursor bugs may surface under a different method name.

Do not claim bulk operations are transactional or rollback-capable unless you have designed them that way. When a callback or processing step throws an exception, some elements may have already been removed. The iterator protocol guarantees removal targets and traversal state under published conditions; it does not provide business transactions.

## Self-Check Exercises

### 1. Why is it wrong if removing B and calling next returns D?

Collection `[A,B,C,D]`, the iterator returned `B`, then removed `B`, and `next` returned `D`.

**Answer:** `C` was shifted from index 2 to 1, but the cursor remained at 2. The cursor must be moved to the position holding the next element after the shift, which in the forward model is `cursor = lastReturned`.

### 2. If hasNext returns false, is remove still allowed?

The iterator just returned the last element, has not removed it yet, and confirmed that no next element remains.

**Answer:** Yes, provided the iterator supports removal and no event has invalidated that condition. `hasNext` only observes what lies ahead; it does not clear the marker for the element just returned.

### 3. Why not use lastValue == null to check whether next has been called?

The collection permits `null` and the iterator just returned a `null` element.

**Answer:** `null` in this case is valid data. You must maintain a separate state such as `lastReturned = -1` or a validity flag, without conflating it with the element value.

### 4. Is removing by equals sufficient?

The iterator just returned the second of two equal objects. `collection.remove(lastValue)` removes the first equal object.

**Answer:** No, it is not sufficient. `Iterator.remove` must remove the exact occurrence that was just returned. You need to track the position or node, not just a value used for searching.

### 5. Why does an iterator throw CME on next after removing an element itself?

The removal adjusted the cursor and incremented `modCount`, but did not update `expectedModCount`.

**Answer:** The iterator is comparing its old expected version against the modification it performed itself. After successfully updating the data and cursor state, update that iterator's expected version.

### 6. Should two iterators share a cursor?

One traversal loop reads an element while another traversal loop starts on the same collection.

**Answer:** For a collection supporting independent traversals, no. The data and structural version belong to the collection; the cursor, last returned element, and expected version belong to each individual iterator.

### 7. Does calling ListIterator.previous followed by remove always decrement cursor?

The cursor is the index of the element that `next` would return. `previous` just decremented the cursor and returned the element at that new position.

**Answer:** No, it does not always decrement. When removing the element located at the cursor after `previous`, keep the index unchanged so that the following element shifts into that position. Only decrement when the removal target lies before the cursor under the chosen index model.

### 8. Can iterator.remove be called inside forEachRemaining?

A callback wants to remove each element it receives using `iterator.remove`.

**Answer:** Do not rely on the general `Iterator` contract to do this. The behavior of a callback modifying the source is unspecified unless the implementation documents its own policy; calling `remove` after `forEachRemaining` also has no general guarantee. Use an explicit `next/remove` loop or an appropriate `removeIf` call.
