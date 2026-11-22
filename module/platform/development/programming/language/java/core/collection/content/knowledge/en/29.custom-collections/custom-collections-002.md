# AbstractCollection, AbstractList, AbstractSequentialList, and AbstractSet

## 1. Why Does a Custom Collection Need a Skeletal Implementation?

Suppose you have data stored in your own way: an array region, a chain of linked nodes, or a read-only dataset. You still want callers of your class to invoke familiar operations such as `contains`, `toArray`, `iterator`, or `addAll`.

If you write `implements Collection<E>` from scratch, you have to manually provide many behaviors that can actually be derived from fundamental operations. For example, once you know how to iterate over elements, you can find an element by iterating; once you know how to add a single element, you can add a whole group by repeating that operation.

The classes `AbstractCollection`, `AbstractList`, `AbstractSequentialList`, and `AbstractSet` provide **skeletal implementations**: the reusable algorithmic parts are pre-written, while subclasses supply the operations tied to their data storage and constraints.

Distinguish three layers:

- **Interfaces** such as `Collection`, `List`, and `Set` describe the contract visible to callers.
- **Skeletal classes** organize the implementation of many methods around a small set of foundational operations.
- **Concrete classes** decide where data is stored, what modifications are permitted, and which invariants are maintained.

A skeletal class does not automatically create an element storage backing for you. Extending `AbstractList` does not automatically give you an array; extending `AbstractSet` does not automatically give you a hash table, nor does it automatically filter out duplicate elements in your subclass's data.

The relationship among the four classes:

```text
AbstractCollection<E> implements Collection<E>
├── AbstractList<E> implements List<E>
│   └── AbstractSequentialList<E>
└── AbstractSet<E> implements Set<E>
```

These are all abstract classes. To instantiate an object, you need a concrete subclass that completes the missing methods; that subclass can be named or declared anonymously. In our examples, we use named classes to make responsibilities and call paths explicit.

**The key lesson is not how few methods you have to write.** You need to know where inherited methods call back into your class, what happens when a foundational operation is unsupported, and whether the time complexity fits your underlying data storage.

The roadmap for this article is: choose a skeletal class → trace method dependencies → write a small concrete class → verify inherited operations → review invariants and costs.

## 2. Choosing a Skeletal Class Based on Semantics and Access Pattern

| Skeletal Class | Semantics to Provide | Starting Point for Reading Data | Key Considerations for Full Mutability |
| --- | --- | --- | --- |
| `AbstractCollection<E>` | A group of elements without claiming list or set semantics | `iterator()`, `size()` | Addition via `add(E)`; removal via an iterator supporting `remove()`. |
| `AbstractList<E>` | An ordered, positional list | `get(int)`, `size()` | Replacement via `set(int,E)`; resizing via `add(int,E)` and `remove(int)`. |
| `AbstractSequentialList<E>` | A list where advancing a cursor is the natural access pattern | `listIterator(int)`, `size()` | The iterator must provide `set`, `add`, and `remove` operations corresponding to the supported mutability. |
| `AbstractSet<E>` | A duplicate-free set adhering to the `Set` contract | `iterator()`, `size()` | Enforce uniqueness yourself across every data entry path; addition/removal follow the `AbstractCollection` foundation. |

This table describes common construction patterns; it does not require every collection to support all mutation operations. One list might be read-only; another might allow replacing elements without allowing additions or removals.

The authoritative contracts for these four classes are [AbstractCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html), [AbstractList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html), [AbstractSequentialList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSequentialList.html), and [AbstractSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSet.html) in Java 17.

Two criteria must be kept separate:

1. **Semantics:** do callers need a positional list, a duplicate-free set, or simply a group of elements?
2. **Data mechanism:** is accessing an element by index cheap, or is holding a cursor and advancing it step by step what is cheap?

Do not choose `AbstractSet` merely to write fewer methods; declaring a `Set` brings uniqueness obligations and set equality rules. Do not choose `AbstractList` merely because your data class can reluctantly implement `get(i)` by walking from the beginning every single time.

### 2.1. Optional Operations Do Not Mean Optional Design Decisions

In the Collections Framework, several mutation operations are optional: an implementation may decline to support them and throw `UnsupportedOperationException`. Skeletal classes typically use this exact mechanism as the default behavior for mutation operations not overridden by the subclass.

For example, `AbstractCollection.add(E)` does not magically find storage space to insert an element. If the subclass does not override it, calls to add will be unsupported. However, `contains()` can work right away as long as the subclass provides a working iterator.

An operation whose name implies mutation does not necessarily throw an exception on every input either. With an implementation that inherits iteration-based removal, `remove("khong-co")` can return `false` without ever reaching the iterator's remove operation. Only when it actually finds a matching element to remove does it hit the unsupported operation.

Therefore, never use the outcome of a no-op call that leaves data unchanged to conclude that a class supports mutation. You must verify the contract and test cases that genuinely require modifying data. [Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html) is the reference specification for optional operations and element restrictions.

### 2.2. Inheritance Does Not Replace Maintaining Invariants

Several invariants must be maintained by the concrete class itself:

- The reported size matches the underlying data and iteration behavior under supported usage conditions.
- Valid indices are handled properly, and out-of-range indices throw the appropriate exception.
- The iterator advances and terminates properly rather than returning a dummy value to signal exhaustion.
- If it is a `Set`, no duplicate elements exist under the chosen equality rule.
- If advertised as read-only, no mutation path is leaked through an iterator or backing storage object.
- If `modCount` is used for a list, structural modifications are recorded accurately.

A class that compiles has only satisfied the type checker. These invariants determine whether it faithfully fulfills the collection contract.

## 3. AbstractCollection: Reuse Built on Iteration

### 3.1. Important Call Paths

With `AbstractCollection`, start with `iterator()` and `size()`. Inherited operations build upon them:

```text
isEmpty()              → size()
contains(x)            → iterator() and element inspection
remove(x)              → locate via iterator(), then iterator.remove()
addAll(source)         → iterate over source, calling add(e)
removeAll / retainAll  → iterate and invoke iterator.remove() as needed
clear()                → iterate and remove each element
toArray() / toString() → rely on data iteration
```

This dependency map helps you read the example; it is not a mandate that every subclass must retain those exact algorithms. If your backing store has a faster way to locate or delete elements, the subclass can override the appropriate methods while preserving the contract.

`removeIf` has a notable point regarding where it is declared: it is a default method on `Collection`, not a method declared by `AbstractCollection` itself. Its default implementation iterates and invokes `Iterator.remove()` for elements matching the predicate. See [Collection.removeIf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#removeIf(java.util.function.Predicate)) for details.

Consequently, supporting only `add(E)` does not make a collection removable. Writing a custom `remove(Object)` alone also does not automatically make inherited `retainAll` work if the iterator still cannot remove elements. You must trace the actual call path of every method you intend to expose.

### 3.2. Program: One Mutable Group and One Read-Only Group

The following example uses an `ArrayList` as the backing store so we can focus on the skeletal implementation. `Bag` accepts duplicate elements and `null`; it does not claim to be a `List` or a `Set`. `ReadOnlyBag` copies the input and returns only an unmodifiable iterator.

Save as `AbstractCollectionDemo.java`:

```java
import java.util.AbstractCollection;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class AbstractCollectionDemo {
    public static void main(String[] args) {
        Bag<String> bag = new Bag<>(Arrays.asList("red", "red", null, "blue"));
        System.out.println("initial = " + bag);
        System.out.println("remove one red = " + bag.remove("red"));
        System.out.println("after remove = " + bag);
        bag.removeIf(Objects::isNull);
        bag.addAll(List.of("blue", "green"));
        System.out.println("after removeIf and addAll = " + bag);
        bag.retainAll(Set.of("blue"));
        System.out.println("after retainAll = " + bag);
        bag.clear();
        System.out.println("after clear = " + bag);

        ReadOnlyBag<String> readOnly = new ReadOnlyBag<>(List.of("A", "B"));
        System.out.println("read-only contains A = " + readOnly.contains("A"));
        expectUnsupported("read-only add", () -> readOnly.add("C"));
        System.out.println("read-only remove missing = " + readOnly.remove("Z"));
        expectUnsupported("read-only remove present", () -> readOnly.remove("A"));
        System.out.println("same contents equal = "
                + readOnly.equals(new ReadOnlyBag<>(List.of("A", "B"))));
    }

    private static final class Bag<E> extends AbstractCollection<E> {
        private final List<E> data;

        private Bag() {
            data = new ArrayList<>();
        }

        private Bag(Collection<? extends E> source) {
            data = new ArrayList<>(source);
        }

        @Override
        public Iterator<E> iterator() {
            return data.iterator();
        }

        @Override
        public int size() {
            return data.size();
        }

        @Override
        public boolean add(E element) {
            return data.add(element);
        }
    }

    private static final class ReadOnlyBag<E> extends AbstractCollection<E> {
        private final List<E> data;

        private ReadOnlyBag() {
            this(List.of());
        }

        private ReadOnlyBag(Collection<? extends E> source) {
            data = Collections.unmodifiableList(new ArrayList<>(source));
        }

        @Override
        public Iterator<E> iterator() {
            return data.iterator();
        }

        @Override
        public int size() {
            return data.size();
        }
    }

    private static void expectUnsupported(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("operation unexpectedly succeeded");
        } catch (UnsupportedOperationException ex) {
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run with JDK 17 or later:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all AbstractCollectionDemo.java
java AbstractCollectionDemo
```

Output:

```text
initial = [red, red, null, blue]
remove one red = true
after remove = [red, null, blue]
after removeIf and addAll = [red, blue, blue, green]
after retainAll = [blue, blue]
after clear = []
read-only contains A = true
read-only add -> UnsupportedOperationException
read-only remove missing = false
read-only remove present -> UnsupportedOperationException
same contents equal = false
```

### 3.3. Interpreting the Output Through Foundational Operations

`Bag` implements only three element-working methods: `iterator`, `size`, and `add`. All other transformations in `main` come from inherited behavior:

- `remove("red")` removes only a single occurrence, so one `red` remains.
- `removeIf` removes the `null` element using the removal-capable iterator.
- `addAll` uses `add` to insert each item, so `blue` is kept twice.
- `retainAll` does not turn the group into a set; it retains both occurrences of `blue`.
- `clear` removes everything through the iterator.

`ReadOnlyBag` does not override `add`, so addition calls are rejected. For `remove("Z")`, the algorithm never finds the item to remove and returns `false`. For `remove("A")`, it finds the item, but the iterator does not support removal, so it throws an exception. Both outcomes are consistent with the chosen implementation.

Two `ReadOnlyBag` instances with identical contents still evaluate `equals` to `false`. `AbstractCollection` does not define value-based content equality; our example class inherits `Object` identity equality. Never infer from the printed format `[A, B]` that every collection shares list equality semantics.

The defensive copy inside `ReadOnlyBag` is a structural copy. If an element itself is a mutable object, external code holding another reference to that object can still mutate its internal state. Preventing structural modification of a collection is different from making an entire object graph deeply immutable.

The subclasses are marked `private` and `final` inside a demonstration program; they are not yet a public library API. For a reusable general-purpose class, you should also design visibility levels, documentation on permitted elements, and appropriate constructors. Providing a no-argument constructor and a constructor accepting `Collection<? extends E>` is a helpful convention rather than a method requirement enforced by an interface.


## 4. AbstractList: Using Index-Based Operations as the Foundation

### 4.1. Construction Pattern for Random-Access Lists

With array-like data storage, `get(i)` is natural and cheap. `AbstractList` takes advantage of that: you provide index-based operations, and the skeletal class builds iterators and many list behaviors on top of them.

Key call paths to remember:

```text
get(i), size()                 → reading foundation
iterator(), listIterator(...)  → use index-based operations
add(e)                         → add(size(), e)
iterator.remove()              → list's remove(index)
listIterator.set(e)            → set(index, e)
listIterator.add(e)            → add(index, e)
clear()                        → removeRange(0, size())
```

The two read methods `get(int)` and `size()` are sufficient to start an unmodifiable list. To support replacing elements, provide `set(int,E)`. To support full resizing, additionally provide `add(int,E)` and `remove(int)`. The inherited iterators delegate directly to those operations. See [AbstractList in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html).

A very common mistake is overriding only `add(E)`. Doing so might allow appending at the end, while `add(index,E)` and insertion via `ListIterator` remain unsupported. Under the design of this skeletal class, positional insertion `add(int,E)` is the proper foundation to implement.

Be careful to distinguish these two method signatures as well:

- `remove(int index)` removes by position and returns the old element.
- `remove(Object value)` removes a single occurrence by value and returns `boolean`.

These are two distinct operations. On a list of integers, picking the wrong overload can remove the wrong position even when the concrete class is implemented completely right.

### 4.2. Element Index Bounds Differ from Cursor Position Bounds

For a list with `n` elements:

| Operation | Valid Range |
| --- | --- |
| `get(i)`, `set(i,e)`, `remove(i)` | `0 <= i < n` |
| `add(i,e)` | `0 <= i <= n` |
| `listIterator(i)` | `0 <= i <= n` |
| `subList(from,to)` | `0 <= from <= to <= n`; `from` is inclusive, `to` is exclusive |

Position `n` does not hold an element to read, yet it is a valid position for appending at the end or placing a cursor past the last element. Do not use the exact same bounds check across all methods.

The `set` method returns the previous element and leaves the size unchanged. `add` inserts an element, shifting the indices of subsequent elements. `remove(int)` removes an element and shifts remaining elements toward the front. The skeletal class cannot automatically fix off-by-one errors in a subclass's storage logic.

### 4.3. Program: A Small Array-Backed List

`ArrayBuffer` below stores its elements directly in an `Object[]`. Because it does not delegate to an `ArrayList`, you can clearly see the responsibilities that fall on the subclass: index validation, array growth, element shifting, size updates, and recording structural modifications.

Save as `AbstractListDemo.java`:

```java
import java.util.AbstractList;
import java.util.Arrays;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;
import java.util.ListIterator;
import java.util.Objects;
import java.util.RandomAccess;

public class AbstractListDemo {
    public static void main(String[] args) {
        ArrayBuffer<String> list = new ArrayBuffer<>();
        list.addAll(List.of("A", "B", "C"));
        System.out.println("initial = " + list);

        ListIterator<String> cursor = list.listIterator(1);
        System.out.println("cursor next = " + cursor.next());
        cursor.set("B*");
        cursor.add("X");
        System.out.println("after cursor add = " + list);
        System.out.println("cursor previous = " + cursor.previous());
        cursor.remove();
        System.out.println("after cursor remove = " + list);

        List<String> middle = list.subList(1, 3);
        middle.set(0, "B2");
        middle.remove(1);
        System.out.println("backing after view edits = " + list);
        System.out.println("equals standard list = " + list.equals(List.of("A", "B2")));
        System.out.println("same list hash = "
                + (list.hashCode() == List.of("A", "B2").hashCode()));

        Iterator<String> afterSet = list.iterator();
        list.set(0, "A2");
        System.out.println("iterator after set = " + afterSet.next());

        Iterator<String> stale = list.iterator();
        list.add("D");
        try {
            stale.next();
            throw new AssertionError("structural change was not detected");
        } catch (ConcurrentModificationException ex) {
            System.out.println("stale iterator -> " + ex.getClass().getSimpleName());
        }
        list.subList(1, list.size()).clear();
        System.out.println("after range clear = " + list);
    }

    private static final class ArrayBuffer<E>
            extends AbstractList<E> implements RandomAccess {
        private Object[] elements = new Object[2];
        private int count;

        @Override
        public int size() {
            return count;
        }

        @Override
        @SuppressWarnings("unchecked")
        public E get(int index) {
            Objects.checkIndex(index, count);
            return (E) elements[index];
        }

        @Override
        public E set(int index, E element) {
            E previous = get(index);
            elements[index] = element;
            return previous;
        }

        @Override
        public void add(int index, E element) {
            if (index < 0 || index > count) {
                throw new IndexOutOfBoundsException("index: " + index);
            }
            if (count == elements.length) {
                int capacity = Math.addExact(count, Math.max(1, count / 2));
                elements = Arrays.copyOf(elements, capacity);
            }
            System.arraycopy(elements, index, elements, index + 1, count - index);
            elements[index] = element;
            count++;
            modCount++;
        }

        @Override
        public E remove(int index) {
            E previous = get(index);
            System.arraycopy(elements, index + 1, elements, index, count - index - 1);
            elements[--count] = null;
            modCount++;
            return previous;
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all AbstractListDemo.java
java AbstractListDemo
```

Output:

```text
initial = [A, B, C]
cursor next = B
after cursor add = [A, B*, X, C]
cursor previous = X
after cursor remove = [A, B*, C]
backing after view edits = [A, B2]
equals standard list = true
same list hash = true
iterator after set = A2
stale iterator -> ConcurrentModificationException
after range clear = [A2]
```

### 4.4. How Do Just Five Methods Allow the Iterator to Mutate the List?

The concrete class provides `get`, `size`, `set`, `add(int,E)`, and `remove(int)`. It does not write `iterator()` or `listIterator()` itself.

The list iterator is created at position 1, right before `B`. After `next()`, the last returned element is `B`. `set("B*")` replaces it. `add("X")` inserts right before the element that would be returned by the next call to `next()`, turning the list into `[A, B*, X, C]`. The cursor now sits after `X`, so `previous()` returns `X`, and `remove()` removes that exact element just returned.

The inherited methods handle cursor management and invoke the right subclass operations. However, array correctness still depends entirely on the subclass:

- When inserting, shift the segment starting at `index` to the right before writing the new element.
- When removing, shift the trailing segment to the left.
- After removing, clear the unused trailing slot in the array to `null` so the list does not retain an obsolete reference.
- Increment or decrement `count` exactly once.
- Return values only at validated indices.

The cast from `Object` to `E` in `get` is confined to a single method and annotated with `@SuppressWarnings("unchecked")`. Its soundness relies on the fact that the array is written exclusively through class paths accepting `E` and is never exposed to external code. This is not an excuse to disable warnings project-wide or use raw types.

The array grows its capacity when full; `Math.addExact` prevents capacity arithmetic from silently overflowing. The code remains a compact learning example and does not include the full maximum-capacity policies or optimizations of a production library collection. It does not promise to allocate arbitrarily large arrays.

### 4.5. modCount Tracks Structural Modifications

`AbstractList` provides the `protected modCount` field. Inherited iterators can use it to detect structural modifications that bypassed the active iterator.

In `ArrayBuffer`:

- A successful `add(int,E)` changes the size, so it increments `modCount` once.
- A successful `remove(int)` also increments it once.
- `set(int,E)` only replaces the value at an existing position, so it does not increment `modCount`.
- A request rejected due to an invalid index must neither mutate the data nor increment the counter.

The [modCount contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html#modCount) warns against incrementing `modCount` more than once within a single call to `add(int,E)` or `remove(int)` when relying on the built-in iterator mechanism. Incrementing it in both an outer method and an internal helper method can trick the iterator into falsely detecting an unexpected concurrent modification.

Do not conflate `modCount` with list size: removing one item and then adding another leaves the final size unchanged, yet the structure has changed twice. An iterator created prior to those two operations cannot treat the underlying data as untouched.

The program demonstrates two cases on a **single thread**:

1. Create an iterator, call `set` on the list to replace `A` with `A2`, and then call `next()`. It reads `A2` normally.
2. Create another iterator, add `D` directly to the list, and then call `next()`. The inherited iterator detects the structural change and throws `ConcurrentModificationException`.

This exception does not prove that two threads are running. It signals a usage pattern that violates the iterator's expectations. Nor should you ever rely on this failure-detection mechanism for thread synchronization: [ConcurrentModificationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ConcurrentModificationException.html) specifies fail-fast detection on a best-effort basis, not a thread-safety guarantee under unsynchronized concurrent modification.

`modCount` does not lock data, does not make compound operations atomic, and does not create a snapshot for the iterator.

### 4.6. subList Is a View Backed by the Original List

`middle = list.subList(1,3)` does not copy `B*` and `C` into an independent list. `middle.set(0,"B2")` replaces the element at the corresponding position in the original backing list. `middle.remove(1)` removes `C` from the backing list. As a result, the backing list becomes `[A, B2]`.

Modifications performed through the view map back to the backing list; size and structural modification state must be tracked consistently. When a subclass manages its own storage, forgetting to update `modCount` can break subList views as well, not just standalone iterators.

After making a direct structural change to the backing list outside the view, do not continue using the old view. According to the [List.subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int)) contract, the semantics of a sublist view become undefined if the backing list is structurally modified in any way other than via the view itself. An implementation may detect this and throw an exception, but catching an exception is not a way to "refresh" the view.

Our program does not reuse `middle` after adding `D` directly to the backing list. Instead, it creates a fresh view to clear the trailing range.

### 4.7. Correct Reuse Is Not Necessarily Optimal

`ArrayBuffer.get(i)` performs direct array indexing after a bounds check, which fits `AbstractList` well. Implementing `RandomAccess` also matches this characteristic. [RandomAccess](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/RandomAccess.html) is a marker interface that lets generic algorithms recognize fast random access; extending `AbstractList` does not automatically confer that marker, nor does adding the marker make a slow `get` faster.

Conversely, inserting or removing elements in the middle of an array requires shifting data. The inherited iterator calls the right operations, but it still pays that shifting cost.

Inherited `clear()` calls `removeRange(0,size())`. The default implementation of `removeRange` uses an iterator to remove elements one by one. On an array, repeatedly removing from the front can shift elements multiple times, resulting in quadratic cost. A sensible optimization is overriding `removeRange` to shift the remaining tail segment once, null out vacated slots, and update the count and `modCount` properly.

You do not need to rewrite every method upfront. First establish a correct implementation and understand the call paths; then choose override points that improve real usage scenarios. `removeRange` is a prime candidate because both `clear()` on the list and range clearing through `subList` benefit from it.


## 5. AbstractSequentialList: Inverting the Dependency Toward ListIterator

### 5.1. Having get(int) Does Not Mean Direct Access Is Cheap

A linked list can still provide `get(i)`. However, to reach that position, it has to traverse nodes. If every element lookup starts a fresh traversal, an index-based loop can end up walking across the data repeatedly.

A more natural approach is positioning a cursor once and calling `next()` to advance. `AbstractSequentialList` adopts that direction: the subclass provides `listIterator(int)` and `size()`, while index-based operations are built on top of the iterator.

```text
get(i)      → listIterator(i).next()
set(i,e)    → position iterator at i, call next(), then set(e)
add(i,e)    → position iterator at i, then add(e)
remove(i)   → position iterator at i, call next(), then remove()
iterator()  → delegates to the list iterator
```

Compared to `AbstractList`, the dependency direction is inverted. Both classes implement `List`, but their algorithmic fulcrums differ. This is the core design distinction described in [AbstractSequentialList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSequentialList.html).

A classic mistake when choosing this class is implementing `listIterator(i)` by calling back into the inherited `get(i)`. Since inherited `get(i)` calls `listIterator(i)`, you create infinite recursion rather than a data-access foundation. The foundational method must access actual storage or an independent backing iterator.

### 5.2. The Iterator Must Fulfill the Full Contract

A `ListIterator` maintains a cursor positioned **between** elements. A list of `n` items has `n+1` valid cursor positions, ranging from before the first item to after the last item.

Read methods must be implemented consistently: `hasNext`, `next`, `hasPrevious`, `previous`, `nextIndex`, and `previousIndex`. When exhausted in the respective direction, `next` or `previous` must throw `NoSuchElementException` rather than returning `null` to signal the end, because `null` can be a legitimate element.

Mutation methods `remove`, `set`, and `add` must either be properly implemented or explicitly rejected with `UnsupportedOperationException`. There is no single generic `index()` method replacing the two directional index methods of `ListIterator`.

For a mutable list iterator:

- `set` and `remove` act upon the last element returned by the most recent `next` or `previous` call.
- `add` inserts at the current cursor position and places the cursor immediately after the newly added element.
- `remove` cannot be called twice in a row for the same returned element.
- Immediately after `add`, neither `set` nor `remove` may be called until another `next` or `previous` call returns an element.

The authoritative state rules are defined in [ListIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html). The skeletal class relies on these exact guarantees to execute other operations; an "almost working" iterator can cause multiple inherited methods to malfunction.

### 5.3. Program: A Sequential Class Delegating Its Iterator

This example uses a `LinkedList` as the underlying storage structure and wraps its iterator. The goal is to observe how `AbstractSequentialList` reuses operations without writing full linked-node manipulation from scratch.

The wrapper performs two specific tasks:

1. Counts how many times a list iterator is started so we can observe call paths.
2. Updates the outer class's `modCount` upon successful additions or removals so inherited views can track structural changes.

Save as `AbstractSequentialListDemo.java`:

```java
import java.util.AbstractSequentialList;
import java.util.Collection;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;

public class AbstractSequentialListDemo {
    public static void main(String[] args) {
        SequentialBuffer<String> list = new SequentialBuffer<>(List.of("A", "B", "C"));
        list.iteratorStarts = 0;
        StringBuilder indexed = new StringBuilder();
        for (int i = 0; i < list.size(); i++) {
            indexed.append(list.get(i));
        }
        int indexedStarts = list.iteratorStarts;

        list.iteratorStarts = 0;
        StringBuilder traversed = new StringBuilder();
        for (String value : list) {
            traversed.append(value);
        }
        int traversalStarts = list.iteratorStarts;
        System.out.println("indexed values = " + indexed);
        System.out.println("indexed iterator starts = " + indexedStarts);
        System.out.println("traversal values = " + traversed);
        System.out.println("traversal iterator starts = " + traversalStarts);

        ListIterator<String> cursor = list.listIterator(1);
        System.out.println("cursor next = " + cursor.next());
        cursor.set("B*");
        cursor.add("X");
        System.out.println("after cursor add = " + list);
        System.out.println("cursor previous = " + cursor.previous());
        cursor.remove();
        System.out.println("after cursor remove = " + list);
        list.subList(1, 3).clear();
        System.out.println("after view clear = " + list);
        try {
            list.get(list.size());
            throw new AssertionError("end position is not an element");
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("get at end -> " + ex.getClass().getSimpleName());
        }
    }

    private static final class SequentialBuffer<E>
            extends AbstractSequentialList<E> {
        private final LinkedList<E> data;
        private int iteratorStarts;

        private SequentialBuffer() {
            data = new LinkedList<>();
        }

        private SequentialBuffer(Collection<? extends E> source) {
            data = new LinkedList<>(source);
        }

        @Override
        public int size() {
            return data.size();
        }

        @Override
        public ListIterator<E> listIterator(int index) {
            ListIterator<E> delegate = data.listIterator(index);
            iteratorStarts++;
            return new ListIterator<>() {
                @Override
                public boolean hasNext() {
                    return delegate.hasNext();
                }

                @Override
                public E next() {
                    return delegate.next();
                }

                @Override
                public boolean hasPrevious() {
                    return delegate.hasPrevious();
                }

                @Override
                public E previous() {
                    return delegate.previous();
                }

                @Override
                public int nextIndex() {
                    return delegate.nextIndex();
                }

                @Override
                public int previousIndex() {
                    return delegate.previousIndex();
                }

                @Override
                public void remove() {
                    delegate.remove();
                    modCount++;
                }

                @Override
                public void set(E element) {
                    delegate.set(element);
                }

                @Override
                public void add(E element) {
                    delegate.add(element);
                    modCount++;
                }
            };
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all AbstractSequentialListDemo.java
java AbstractSequentialListDemo
```

Output:

```text
indexed values = ABC
indexed iterator starts = 3
traversal values = ABC
traversal iterator starts = 1
cursor next = B
after cursor add = [A, B*, X, C]
cursor previous = X
after cursor remove = [A, B*, C]
after view clear = [A]
get at end -> IndexOutOfBoundsException
```

### 5.4. Starting Three Iterators vs. Advancing One Iterator

In the index-based loop, each inherited `get(i)` call creates a new list iterator positioned at `i` and fetches the next element. With three items, the counter records three iterator starts.

In the `for-each` loop, `iterator()` creates a single iterator that the loop repeatedly advances. The counter records only 1 start. Both loops produce the string `ABC`, but their paths through the data-access layer are completely different.

This is a direct observation of invocation counts in our example. It does not measure nanoseconds, does not benchmark how much faster a specific machine runs, and does not generalize a fixed cost across all `AbstractSequentialList` implementations.

With linked data structures, positioning cost is the exact reason we care. [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html) documents that index-based operations traverse from whichever end (beginning or end) is closer. Repeating that positioning traversal for every index in a loop can lead to quadratic total cost; holding a single iterator and advancing it step by step avoids that repeated traversal.

Conversely, if you extend `AbstractList` for a linked store and implement `get(i)` by walking from the head node each time, the inherited iterator built on top of `get` will suffer poor complexity too. The `List` interface name does not determine speed; you have to inspect how methods call one another and how the underlying store locates positions.

### 5.5. Why Not Return the LinkedList Iterator Directly Without a Wrapper?

The `LinkedList` iterator tracks modifications inside the `LinkedList` itself. However, the outer class also inherits mechanisms from `AbstractList`—for instance, `subList` views rely on the structural modification state (`modCount`) of the outer list.

If the outer class mutates its backing store without updating its own `modCount`, the two layers can see mismatched structural versions. In our example, each successful `delegate.add` or `delegate.remove` is followed by exactly one increment of the outer counter. `delegate.set` does not change the list's size, so it does not increment `modCount`.

If the `delegate` operation throws an exception, the subsequent increment statement does not execute. This prevents recording a modification that never took place. Valid iterator state transitions, boundary checks, and backing modification detection are delegated to the `LinkedList` iterator.

This is a specific design resulting from using two object layers. If you write your own node structure and iterator directly, you manage the cursor, last returned element, size, and modification detection yourself. There is no requirement that subclasses of `AbstractSequentialList` must wrap a `LinkedList`.

The call `subList(1,3).clear()` cleanly removes `B*` and `C` through the designed call paths. Calling `get(list.size())` afterward throws `IndexOutOfBoundsException`: the end position is a valid cursor position, but not a valid element index to read. `AbstractSequentialList` translates iterator exhaustion during an indexed read into the appropriate index exception.

### 5.6. When Should You Choose This Direction?

Choose `AbstractSequentialList` when moving forward and backward from a current cursor position is the natural access primitive, whereas random access requires traversal to locate the position. You do not need to fake an array-like `get` only to build every other operation on top of it.

Conversely, for an array store where `get(i)` is cheap, `AbstractList` usually yields a more direct representation. The fact that `AbstractSequentialList` subclasses `AbstractList` does not make it "more complete" for every situation. It specializes the construction pattern for a different access model.

In both directions, mutation operations can be restricted by design: read-only, mutable values with fixed size, or dynamically resizable. The public contract must accurately reflect those capabilities; never assume from the word "sequential" that a list is mutable or thread-safe.


## 6. AbstractSet: Contract Skeleton Provided, Uniqueness Still Your Responsibility

### 6.1. No Implicit Hash Table Is Created

`AbstractSet` inherits the iteration foundation of `AbstractCollection` and implements the `Set` interface. A subclass still needs to provide `iterator` and `size`. To support adding elements, it must provide an appropriate `add` implementation.

What `AbstractSet` adds is set semantics—most notably `equals` and `hashCode` implementations that conform to the `Set` contract. In addition, `AbstractSet` provides its own `removeAll` implementation. It is not a stripped-down `HashSet`: there is no requirement that data be stored using hashing, and there is no automatic deduplication engine intercepting writes to the subclass's private backing store.

If a subclass uses a backing array or list and its `add` method simply appends elements to the end, equal elements can still appear multiple times. Inheriting the class name does not fix that violated invariant.

For a small example, a straightforward way to enforce uniqueness is checking whether an equal element already exists before adding. If it is already present, return `false` and leave the set unchanged. If it is absent, store the element and return `true`. Even when you choose a more sophisticated data structure or algorithm, you must preserve the return value semantics and equality rules.

These constraints belong to [Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html); the specific reusable methods belong to [AbstractSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSet.html).

### 6.2. Program: A Small Set Backed by a List

`TinySet` deliberately uses an `ArrayList` so you can see clearly that a `Set` does not have to be backed by a hash table. In this implementation, it accepts a single `null`, iterates in insertion order, and searches by linear traversal.

Save as `AbstractSetDemo.java`:

```java
import java.util.AbstractSet;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Collections;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Set;

public class AbstractSetDemo {
    public static void main(String[] args) {
        TinySet<String> set = new TinySet<>();
        System.out.println("add alpha = " + set.add("alpha"));
        System.out.println("add equal alpha = " + set.add(new String("alpha")));
        set.add("beta");
        set.add(null);
        System.out.println("initial = " + set);

        Set<String> other = new HashSet<>(Arrays.asList(null, "beta", "alpha"));
        System.out.println("equals standard set = " + set.equals(other));
        System.out.println("reverse equality = " + other.equals(set));
        System.out.println("same set hash = " + (set.hashCode() == other.hashCode()));
        System.out.println("equals list = " + set.equals(Arrays.asList("alpha", "beta", null)));
        set.removeAll(Collections.singleton("alpha"));
        System.out.println("after removeAll = " + set);

        Iterator<String> cursor = set.iterator();
        System.out.println("iterator next = " + cursor.next());
        cursor.remove();
        System.out.println("after iterator remove = " + set);

        TinySet<String> copied = new TinySet<>(Arrays.asList("x", "x", null));
        System.out.println("copy = " + copied);
        System.out.println("copy size = " + copied.size());
        System.out.println("add second null = " + copied.add(null));
    }

    private static final class TinySet<E> extends AbstractSet<E> {
        private final List<E> data = new ArrayList<>();

        private TinySet() {
        }

        private TinySet(Collection<? extends E> source) {
            addAll(source);
        }

        @Override
        public Iterator<E> iterator() {
            return data.iterator();
        }

        @Override
        public int size() {
            return data.size();
        }

        @Override
        public boolean add(E element) {
            if (contains(element)) {
                return false;
            }
            return data.add(element);
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all AbstractSetDemo.java
java AbstractSetDemo
```

Output:

```text
add alpha = true
add equal alpha = false
initial = [alpha, beta, null]
equals standard set = true
reverse equality = true
same set hash = true
equals list = false
after removeAll = [beta, null]
iterator next = beta
after iterator remove = [null]
copy = [x, null]
copy size = 2
add second null = false
```

### 6.3. Uniqueness Must Hold Across Every Data Entry Path

The first call `add("alpha")` modifies the set and returns `true`. The call to add `new String("alpha")` passes a distinct object reference with equal value; it returns `false`. Constructing a new `String` instance here serves strictly to verify value-based equality rather than reference identity—it is not a string creation idiom for everyday code.

The constructor accepting a `Collection` does not blindly copy every item straight into `data`. Instead, it calls `addAll(source)`, whose inherited path inserts each element one by one through `add`, where duplicate checking takes place. Consequently, the input `["x", "x", null]` produces a two-element set `[x, null]`.

If we replaced that with `data.addAll(source)`, we would bypass the outer class's deduplication rule. That is why you must audit constructors, bulk methods, and every internal update path—not just direct `set.add(...)` calls made by users.

`data` is kept private and never returned directly to callers. The iterator permits removal but has no insertion method, so iteration cannot introduce duplicates either. The policy allowing `null` comes from the design of `TinySet` and its backing list, not from any rule promising that every `AbstractSet` subclass accepts `null`.

The printed element order in our example is an artifact of `TinySet` using an `ArrayList` backing store. Do not treat it as an ordering guarantee for all `Set` implementations. Set equality remains independent of iteration order.

### 6.4. Set equals and hashCode Differ from List

In the program, `set` and `other` contain the same elements but were populated in different orders and belong to two different concrete classes. Equality holds in both directions (`true`), and their hash codes match. This interoperability allows compliant `Set` implementations to work seamlessly together.

Meanwhile, a `List` containing those exact same items is still not equal to the `Set`. Never use an ad-hoc "same items" check that erases the semantic boundary between lists and sets.

Comparing the three branches:

| Base Class | Inherited Equality Semantics | Does Order Matter? |
| --- | --- | --- |
| `AbstractCollection` | Adds no content-based rule; defaults to `Object` unless overridden | No general content comparison rule is imposed here. |
| `AbstractList` and `AbstractSequentialList` | Equal to another `List` when both have the same length and corresponding elements at each index are equal | Yes. |
| `AbstractSet` | Equal to another `Set` when both have the same size and contain the same elements | No. |

A list's hash code accumulates sequentially in order using a multiplier of 31; a set's hash code is the sum of the hash codes of its elements, with `null` contributing 0. Never swap one formula for the other just because the underlying storage looks similar.

If you define custom content-based equality for a general collection that is neither a `List` nor a `Set`, you must preserve symmetry and the `hashCode` contract. You cannot make your custom group claim equality with a `List` while `List.equals` rejects your group. In our `Bag` example, keeping `Object` equality avoids introducing a flawed comparison rule outside the scope of the demonstration.

Uniqueness also depends on the stability of element equality. If you mutate fields used by `equals` while an object is already stored inside a set, you can cause previously distinct elements to become equal. Choose elements with stable values or establish a clear update policy; a skeletal class cannot monitor internal mutations inside element objects.

### 6.5. removeAll Can Take Two Different Execution Paths

`AbstractSet.removeAll` compares the sizes of the two collections to choose between two strategies:

- Iterate over the argument collection and call `remove(Object)` on the receiving set.
- Or iterate over the receiving set, check whether the argument collection contains each item, and remove matching elements via the receiving set's iterator.

Details can be seen in [AbstractSet.removeAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSet.html#removeAll(java.util.Collection)) and the [OpenJDK 17u source code](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/AbstractSet.java).

Therefore, if you only override a custom `remove(Object)` while leaving the iterator unable to remove elements, you cannot assume `removeAll` will work on all inputs. Which branch executes depends on the relative sizes of the data. To publicly support `removeAll`, you must either satisfy all underlying dependencies or override `removeAll` with a self-consistent implementation.

`TinySet` returns the backing list's iterator, which supports removal, so both mutation paths have working foundations. After `removeAll` removes `alpha`, the explicit iterator advances past `beta` and removes it, leaving `[null]`.

This is also a clear illustration of why you should never guess an algorithm merely from a method's name. The same interface operation may be specialized by a skeletal subclass to better suit its collection category.

### 6.6. Set Correctness Does Not Imply HashSet Performance

In `TinySet`, inherited `contains` performs a linear scan over the elements. Adding a new item requires checking for duplicates first, so insertion cost grows linearly with the number of existing items. Bulk-adding many distinct items can incur quadratic total cost.

Computing a set's hash code requires iterating over its elements. Comparing two sets for equality also depends on lookup cost in the target collection; never assume every `Set` offers constant-time lookup.

A small list-backed set can be completely appropriate for learning or for tiny domain element sets. If your primary requirement is fast lookup over large datasets, choose an appropriate backing data structure. Extending `AbstractSet` reuses the contract and baseline algorithms—it does not choose a data structure for you.

## 7. Reviewing a Custom Implementation Before Publishing

### 7.1. Test Inherited Methods Too

Do not just test `add` followed by `get`. Test the indirect paths callers will invoke:

- For `AbstractCollection`: `contains`, `remove(Object)`, `addAll`, `retainAll`, `removeIf`, `clear`, and array conversion (`toArray`).
- For lists: standard `Iterator`, `ListIterator`, insertion at head and tail, index boundaries, `subList`, and range removal.
- For sets: adding equal objects with distinct references, constructors receiving duplicate inputs, `addAll`, equality comparison against a standard `Set` implementation, and `hashCode`.
- For read-only types: test operations that would genuinely modify existing data, not just no-op calls on absent elements.

Default bulk operations typically proceed step by step. If an intermediate step throws an exception, do not assume earlier changes were rolled back. If your domain requires validating the entire input before applying any change, or requires cross-thread atomicity, you must design that guarantee explicitly.

None of the four skeletal classes automatically provide thread-safe concurrent access. Using modification counters or catching `ConcurrentModificationException` is no substitute for proper synchronization.

### 7.2. Choose Inheritance When You Need to Expose the Full Contract

If your goal is building a custom `List` or `Set` that participates directly in Collections Framework algorithms, skeletal classes are valuable because they faithfully reuse standard semantics.

If your goal is simply holding an internal list inside a domain business object, prefer composition: encapsulate an existing standard collection inside your class and expose only the domain operations needed. There is no need to turn every class that holds multiple items into a collection subclass.

The examples in this article intentionally show both mechanisms side by side: a concrete class extends a skeletal class while delegating actual storage to an internal backing object. When designing a real API, however, you must decide whether you want to commit to the entire collection contract or expose a narrower set of domain behaviors.

### 7.3. Override to Optimize While Preserving the Contract

A well-chosen override can speed up multiple inherited operations at once: `contains` for an indexed store, `removeRange` for an array-backed list, or `addAll` when a contiguous block can be copied efficiently.

Every optimization must preserve all observable contract guarantees: return values, ordering for lists, uniqueness for sets, handling of invalid indices and disallowed elements, mutability policies, iterators, and views. "Running faster" never excuses an insertion path that bypasses duplicate checks or a structural change that fails to update `modCount`.

When analyzing performance, trace the entire call chain. A concise inherited method might repeatedly invoke a linear operation under the hood. Conversely, implementing the same `List` interface does not force two different data structures to share the same performance profile.

## 8. Practice and Self-Check Exercises with Solutions

### Exercise 1. Read-Only with AbstractCollection

You implement `iterator()` and `size()` properly and do not override `add`. The iterator does not support removal. What happens when calling `contains(x)`, `add(x)`, and `remove(x)`?

**Solution:** `contains` works by iterating over the elements. `add` throws `UnsupportedOperationException` by default. `remove` returns `false` if the target item is not found; if the item is found and `remove` attempts to invoke the iterator's unsupported `remove()` operation, it throws `UnsupportedOperationException`. Never infer mutability from removing an absent item.

**Practice:** Using `ReadOnlyBag` from the first program, test `removeIf` with a predicate that matches nothing and a predicate that matches `A`. Explain the difference by tracing the call path to `Iterator.remove`, not from the method name.

### Exercise 2. Fixed-Size List

A subclass of `AbstractList` implements `get`, `size`, and `set`, while leaving `add(int,E)` and `remove(int)` at their default implementations. Can elements be replaced via `ListIterator`? Can elements be added via the iterator?

**Solution:** Elements can be replaced whenever the iterator state permits `set`, because the iterator delegates to the subclass's `set` method. Elements cannot be added via the iterator because the foundational `add(int,E)` operation is unsupported. The ability to replace values does not imply the ability to resize the list.

**Practice:** Create a fixed-size list backed by a defensive copy of an array, implementing the three read/replace methods above. Verify that the size remains fixed and boundary indices are handled properly.

### Exercise 3. Double Increment of modCount During a Single Addition

Suppose `add(int,E)` calls a helper method, and both methods increment `modCount`. Why might an iterator throw an exception even when you only called `listIterator.add(e)`?

**Solution:** The inherited iterator tracks the expected number of structural modifications. Counting a single structural operation twice causes a mismatch between the list's `modCount` and the iterator's expected counter. Choose a single place to record a completed structural addition. Never increment `modCount` merely because a helper was entered or an addition was requested before validation succeeds.

**Practice:** Trace the execution path of `ArrayBuffer.add` and identify the exact line where the structural update is completed. Explain why `set` does not increment `modCount` in this implementation.

### Exercise 4. Linked Data Using an Iterator Built on get

You extend `AbstractList` and implement `get(i)` by traversing from the head node to position `i`. Is a `for-each` loop guaranteed to run in linear time?

**Solution:** No. The inherited iterator calls `get` for each sequential index. The total number of node steps across the loop becomes `1 + 2 + ... + n`, which is quadratic. Either extend `AbstractSequentialList` with an efficient forward-moving iterator, or provide a custom iterator and carefully audit all remaining index-based paths.

**Practice:** In the sequential list program, increase the number of elements and observe the iterator start count. Distinguish the measured method invocation count from the number of traversed nodes and actual wall-clock runtime.

### Exercise 5. Set Deduplicating in add but Not in the Constructor

A subclass of `AbstractSet` checks for duplicates in `add`, but its constructor directly executes `new ArrayList<>(source)`. If `source` contains two equal items, does the class fulfill the `Set` contract?

**Solution:** No. The constructed instance already violates set uniqueness before anyone even calls `add` on the new object. You must route constructor input through an invariant-preserving path or filter duplicates during construction. `TinySet` uses `addAll`, which routes through `add`.

**Practice:** Test constructor inputs containing repeated identical references, two distinct object references that are equal by value, and multiple `null` elements (if permitted by policy). Verify both the resulting size and contents.

### Exercise 6. Using the Same Hash Code Formula for Both List and Set

Suppose you want to sum element hash codes across every custom collection for extra code reuse. Does that preserve the `List` contract?

**Solution:** You cannot arbitrarily replace the standard `List` hash code formula. Lists use order-dependent equality and a corresponding positional hash code formula; sets use order-independent equality and their own commutative sum formula. Two equal lists must produce identical hash codes across all compliant `List` implementations, not just when compared against your own custom class.

**Practice:** Compare a custom list against `List.of("A","B")` in both directions and verify that their hash codes match. Do the same with `TinySet` and `HashSet`, deliberately inserting elements in different orders.

### Exercise 7. Implementing Only remove(Object) for a Set

Suppose a set's iterator does not support removal, but `remove(Object)` has been overridden and works properly. Can you advertise that inherited `removeAll` is always supported?

**Solution:** Not without further work. `AbstractSet.removeAll` may choose the iterator-based removal path depending on the relative sizes of the two collections. You must either support all foundational operations that the inherited algorithm may call or override `removeAll` to match your advertised capabilities.

**Practice:** Design two test inputs where the receiving set is respectively larger and smaller than the argument collection. Trace which branch executes in the JDK source code; never test just one collection size and extrapolate to all cases.

## 9. Verification and Reference Documentation

The four programs in this article were compiled with `javac --release 17 -encoding UTF-8 -Xlint:all` and executed on OpenJDK 24.0.2, producing the exact output blocks shown above. The `--release 17` flag validates syntax and API usage against Java 17 at compile time; it does not mean the verification runtime itself used a Java 17 JVM.

Observations such as iterator start counts, `TinySet` print order, and `modCount` increments apply specifically to the example classes written here. The reuse call paths were cross-checked against the Java 17 API contracts; whenever a subclass overrides an algorithm, you must analyze that concrete implementation directly.

Primary references:

- [AbstractCollection — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html): iteration foundation, optional addition/removal, and inherited algorithms.
- [AbstractList — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html): index-based operations, iterators, `modCount`, `removeRange`, and views.
- [AbstractSequentialList — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSequentialList.html): building index-based operations on top of a list iterator.
- [AbstractSet — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSet.html): set constraints, equality, hash code, and `removeAll`.
- [Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html), [List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html), [Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html): contracts that must be preserved regardless of backing storage.
- [ListIterator — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html): cursor positions, mutation states, and exceptions.
- [AbstractList source in OpenJDK 17u](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/AbstractList.java) and [AbstractSet source](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/AbstractSet.java): detailed call-path reference for the baseline implementations; does not replace the general contract for arbitrary subclasses.
