# Minimal Methods and the Optional Operation Contract

## Understanding "Minimal" When Implementing a Custom Collection

When implementing a custom collection, the first question is often: "How many methods must I write?". The answer depends on the base class and the capabilities you want to provide. A read-only list has a different starting point than a resizable list; a map has update paths through views that an ordinary collection does not have.

The Java Collections Framework provides skeletal implementation classes: `AbstractCollection`, `AbstractList`, `AbstractSequentialList`, `AbstractSet`, `AbstractQueue`, and `AbstractMap`. You write a group of foundational methods, and the skeletal class builds many other methods on top of that group.

The relationship to understand is:

~~~text
Interface contract
    -> Skeletal class chooses a general implementation strategy
        -> Foundational methods of the subclass
            -> Behavior of inherited methods
~~~

For example, an `AbstractList` can create an iterator from `get(int)` and `size()`. If a subclass implements `remove(int)`, removal through the inherited iterator gains an execution path. If `remove(int)` is not supported, the iterator can still traverse elements, but it cannot remove them.

There are two different levels of "minimal":

- **Enough to become a concrete class:** `abstract` methods need implementations so the compiler accepts the class.
- **Enough to fulfill its promise:** every read method, write method, iterator, and view must comply with the published contract, including inherited methods.

The second level determines whether the class genuinely works as a `List`, `Set`, `Queue`, or `Map`. Successful compilation does not prove there are no duplicate elements in a set, does not make a map view a valid live view rather than a detached copy, and does not automatically provide synchronization for multiple threads.

This article uses the Java 17 API as its baseline. When upgrading Java versions, review whether new interface methods and new default implementations affect your class.

## Optional Operations Still Have a Contract

A method documented as an `optional operation` does not mean the implementer can omit the method from the object or return arbitrary results. It means an implementation is permitted not to support that capability; when a call requests an unsupported capability, the appropriate exception is `UnsupportedOperationException`.

For example, a fixed-size list may support `set` while not supporting `add` or `remove`. It is still a `List`. A read-only list may support none of the three. These choices are part of each implementation's contract and cannot be inferred solely from the type `List<E>`.

Distinguish between the following:

| Result or Exception | Typical Meaning |
| --- | --- |
| `UnsupportedOperationException` | The implementation does not support the requested operation |
| `false` from `Set.add` | The element is already present, so the set is unchanged |
| `false` from `Queue.offer` | The insertion cannot be performed immediately, for instance because the queue is full |
| `IndexOutOfBoundsException` | The index is outside the valid range |
| `IllegalStateException` from an iterator supporting removal | The removal call is invalid for the current traversal state |
| `NoSuchElementException` from `Iterator.next` | No more elements remain |
| `NullPointerException` | A `null` argument or element is invalid under the applicable contract |

An unsupported `add` should not pretend to return `false` for every element. An unsupported `set` should not silently ignore the request and return `null`. Such results mislead callers into thinking the operation was processed according to its normal contract.

The rules for optional operations and element restrictions are specified in [Java 17 Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html). Identical method names do not guarantee that every implementation has the same write capabilities.

### No-Op Calls Might Not Throw an Exception

This is an easy pitfall that can make a capability test inaccurate:

~~~java
collection.addAll(List.of());
~~~

A collection that does not support addition may throw `UnsupportedOperationException`, but under the general contract, a call that has no effect may also complete normally. Similarly, removing a non-existent element may return `false`, even though removing an existing element would throw an exception.

Therefore:

- `addAll` succeeding with an empty collection does not prove `add` is supported.
- `remove` returning `false` for an absent value does not prove removing an existing value will succeed.
- `removeIf` with an always-`false` predicate does not prove the iterator supports removal.
- A call to `putAll` with an empty map does not prove the map can add new mappings.

Do not use no-op calls to probe capabilities and then rely on that outcome to decide whether real data can be written. The Collections Framework does not have a general method such as `supportsAdd()`. Callers need to know the contract of the received object or design inputs with explicit capabilities.

An implementation may provide stronger guarantees. For example, lists created via `List.of` specify that mutator methods always throw `UnsupportedOperationException`. Do not project that specific guarantee backward onto every minimal subclass of `AbstractList`. See the unmodifiable lists section in [List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

## Choosing a Skeletal Class and Foundational Methods

The table below is a starting point; it does not replace reading the contract of every operation the class intends to support.

| Skeletal Class | Foundational Methods to Provide | To Enable Write Capabilities |
| --- | --- | --- |
| `AbstractCollection<E>` | `iterator()` and `size()` | Implement `add(E)` for insertion; support `remove()` on the iterator so many inherited removal operations work |
| `AbstractSet<E>` | `iterator()` and `size()`, while guaranteeing no duplicates per the set contract | Implement addition/removal while preserving uniqueness |
| `AbstractList<E>` | `get(int)` and `size()` for a read-only list | `set(int,E)` to replace elements; `add(int,E)` and `remove(int)` to resize |
| `AbstractSequentialList<E>` | `listIterator(int)` and `size()` | Bidirectional iterator supporting `set`; add `add/remove` if resizing is supported |
| `AbstractQueue<E>` | `offer(E)`, `peek()`, `poll()`, `iterator()`, and `size()` | Separately decide iterator removal, removal by value, and bulk operations |
| `AbstractMap<K,V>` | `entrySet()` for a read-only map | `put(K,V)` for writing; `entrySet` iterator supporting removal so inherited removal paths work; `Entry.setValue` if updating via entries is supported |

If you implement an interface directly, you must provide every method except those already validly inherited, such as `default` methods. A skeletal class reduces the number of methods you must write by preselecting general algorithms.

However, writing fewer methods also creates dependencies: a bug in `iterator` or `get` can simultaneously break `contains`, `toArray`, `equals`, `toString`, and many other operations.

## AbstractCollection: Reading Relies on the Iterator, and Removal Usually Does Too

With `AbstractCollection`, `size()` provides the element count while `iterator()` provides the way to traverse data. The skeletal class can use the iterator to search for a value, build an array, or construct a display string.

For a read-only collection, the iterator must still:

- Return `hasNext()` consistently with whether elements remain.
- Return the exact next element from `next()`.
- Throw `NoSuchElementException` when `next()` is called past the last element.
- Respect ordering if the collection publishes an order.
- Not expose an unintended removal path.

`Iterator.remove` has a default implementation that throws `UnsupportedOperationException`. Consequently, an iterator that only implements `hasNext` and `next` can traverse elements without supporting removal. See [Iterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html).

The last point is crucial for encapsulation. If `iterator()` directly returns the iterator of an internal `ArrayList`, a caller can remove elements through the iterator even if `add` on the collection is blocked. To prevent modification through the collection, you must inspect the iterator path as well.

### Call Chains for Removal Operations

Visualize the typical execution paths of the skeletal implementation:

~~~text
remove(value)
    -> find value using iterator
    -> iterator.remove() if found

clear()
    -> traverse using iterator
    -> iterator.remove() for each element

default removeIf(predicate)
    -> traverse using iterator
    -> iterator.remove() for matching elements
~~~

If the iterator does not support removal, `remove(value)` might only fail when the value is actually found. If not found, it returns `false` without needing to call `remove` on the iterator.

This is why you must test both inputs that cause an effect and inputs that do not. A class tested only with an empty collection might appear to support many operations, yet fail when real data arrives.

For a fully modifiable collection under this model, implementing `add(E)` and supporting `Iterator.remove` form the key extension group. You can override other methods when a more efficient algorithm is available, provided you preserve the promised results, exceptions, and side effects. See [AbstractCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html).

## AbstractList: Reading, Replacing, and Resizing Are Three Distinct Capabilities

`AbstractList` builds positional operations. For data that supports efficient indexed access, `get(int)` and `size()` produce a readable list equipped with an iterator and many built-in algorithms.

There are three useful tiers:

| List Type | `get/size` | `set` | `add/remove` |
| --- | --- | --- | --- |
| Read-only | Yes | No | No |
| Fixed-size, element-replaceable | Yes | Yes | No |
| Resizable | Yes | Yes, if replacement is supported | Yes, as published |

Addition/removal capability and replacement capability are not a single "mutable" flag. When designing a specialized class, describe each major operation group explicitly.

### Why Overriding add(E) Is Not Enough

The inherited `AbstractList.add(E)` calls `add(size(), e)`. If you want to integrate with the skeletal implementation, the proper extension point is usually `add(int,E)`.

If you only write `add(E)` while leaving `add(int,E)` unsupported, indexed insertion paths or `ListIterator.add` may still throw `UnsupportedOperationException`. In that case, the class only supports a narrower set of operations; it must not be described as "supporting element insertion at arbitrary positions".

Similarly, `remove(int)` and `remove(Object)` are two distinct overloads. For a `List<Integer>`:

~~~java
numbers.remove(1);                 // Remove at index 1.
numbers.remove(Integer.valueOf(1)); // Remove the first occurrence of value 1 if present.
~~~

This illustrates overload resolution rather than a standalone program. When implementing and testing, distinguish argument types carefully so you do not test the wrong capability.

### Inherited Iterators Build Upon List Methods

With `AbstractList`'s implementation, you can visualize:

~~~text
Iterator.next()          -> get(index)
Iterator.remove()        -> remove(index)

ListIterator.set(value)  -> set(index, value)
ListIterator.add(value)  -> add(index, value)
~~~

This does not bypass iterator state rules. For instance, an iterator that supports removal still disallows removing before `next` returns an element, and disallows removing twice after the same `next` call.

A `ListIterator` positions its cursor between elements. `set/remove` act on the element most recently returned by `next` or `previous`, not arbitrarily on an element at whatever cursor index is currently reported. After operations that invalidate that state, the caller must traverse again according to the contract before calling them again. See [ListIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html).

### set Also Enables replaceAll and sort

A fixed-size list can sort and replace all its values without adding or removing elements. The relevant default implementations in `List` rely on replacement through the list iterator.

Therefore, not supporting resizing does not mean `sort` is impossible. Conversely, supporting `add/remove` without supporting `set` does not automatically make replacement algorithms work.

In the example below, `FixedList` adds only `set` to `get/size`. It sorts, converts strings to lowercase, and replaces elements via `ListIterator.set` successfully; `add` and `remove(int)` remain unsupported.

### modCount When Using Inherited Iterators and subList

`AbstractList` provides `modCount` to detect structural modifications in inherited iterators and list iterators. For a class that uses this mechanism, structurally modifying methods must update `modCount` properly. A single addition or removal should increment it at most once.

In the example, a successful addition or removal increments `modCount`; `set` only replaces an element, so it does not increment `modCount` for this list model. If a call fails before modifying data, do not increment `modCount` as if a modification occurred.

Do not rely solely on the fact that the internal backing store is an `ArrayList`. Iterators created by the outer `AbstractList` track the outer class's state; a separate counter inside the internal `ArrayList` does not automatically substitute for that outer counter.

Using `modCount` for modification detection is a subclass choice documented in [AbstractList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html). It is not a lock, does not make the class thread-safe, and is not a way to verify concurrent program correctness.

`subList` is a view, not a detached copy. If modification through the view is permitted, changes must propagate to the backing list according to the contract. When the backing list is structurally modified through another path while a view is in use, callers must not assume the view remains valid.

## AbstractSequentialList: Reversing the Dependency

If the data store traverses linked nodes, repeatedly calling `get(0)`, `get(1)`, `get(2)` may have to start over from the beginning each time and become expensive.

`AbstractSequentialList` takes the opposite direction from `AbstractList`: you provide `listIterator(int)`, and it builds positional operations on top of that iterator. The foundational group is `listIterator(int)` and `size()`. See [AbstractSequentialList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSequentialList.html).

If you write a custom read-only `ListIterator`, you must still provide method bodies for every abstract method in `ListIterator`:

- Forward/backward traversal: `hasNext`, `next`, `hasPrevious`, `previous`.
- Cursor indices: `nextIndex`, `previousIndex`.
- Optional operations `add`, `set`, `remove`: if unsupported, implement them to throw `UnsupportedOperationException`.

Note that `ListIterator` redeclares these operations; do not look at the default implementation of `Iterator.remove` and assume a class directly implementing `ListIterator` can omit them.

To support replacing elements, the iterator needs a working `set`. To support resizing, the iterator needs working `add/remove` implementations, including adjusting the cursor and last-returned element state. Only then do the inherited index-based operations have an adequate foundation to work properly.

Choosing a skeletal class is not just about writing less code: it also chooses the algorithmic path. `RandomAccess` is a marker informing external algorithms about access characteristics; it does not make `get` fast by itself and should not be attached to a linked list just to look complete.

## AbstractSet: The Skeletal Class Does Not Automatically Deduplicate

`AbstractSet` uses the same foundational method group as `AbstractCollection` while providing set `equals/hashCode` semantics. However, it does not turn an arbitrary backing store into a valid set.

If a subclass stores `[A, A]` inside an internal list and returns that list's iterator with `size = 2`, merely naming the class `CustomSet` does not fix the contract violation. Every data entry point, including constructors and `add`, must maintain uniqueness.

The snippet below shows one way to delegate insertion when the internal store already enforces set semantics:

~~~java
@Override
public boolean add(E value) {
    return backingSet.add(value);
}
~~~

If the internal store is a list, you must check and preserve the uniqueness invariant yourself; no deduplication guarantee appears merely from `extends AbstractSet`.

Equality across different set implementations must be preserved: different iteration orders do not make two sets with the same elements unequal. `hashCode` must also follow the set contract. By contrast, lists compare elements in order. A "bag"-style collection that allows duplicates should not adopt list or set semantics just to reuse `equals`. See [AbstractSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSet.html).

Some operations like `removeAll` may choose different execution paths depending on the relative sizes of the two collections. Therefore, do not test only one size and assume removal capabilities are consistent across all cases. Cross-check the published contract against both direct removal methods and iterator removal.

## AbstractQueue: A Different Method Group Than Ordinary Collections

`AbstractQueue` requires `offer`, `poll`, `peek`, `iterator`, and `size` as its foundation. It is designed for queues that do not accept `null` elements.

Why `null` matters: `poll/peek` use `null` as the return value indicating an empty queue. If `null` were allowed as an actual element, inherited implementations could no longer distinguish a real element from an empty signal.

Inherited methods provide two ways to report outcomes:

| Foundational Method | Method Built Upon It | Difference When No Result Is Available |
| --- | --- | --- |
| `offer(e)` | `add(e)` | `offer` returns `false` when full; `add` throws `IllegalStateException` |
| `poll()` | `remove()` | `poll` returns `null` when empty; `remove` throws `NoSuchElementException` |
| `peek()` | `element()` | `peek` returns `null` when empty; `element` throws `NoSuchElementException` |

This is the contract of [AbstractQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractQueue.html). A full queue still supports insertion once space becomes available again; do not use `UnsupportedOperationException` to express a temporary full state.

### remove() Differs from remove(Object)

Queue's `remove()` removes the head element. `remove(Object)` searches for and removes a specific value.

A queue may support head removal via `poll` without allowing its iterator to remove arbitrary elements. With the skeletal implementation, `remove()` still works through `poll`, whereas `remove(existingValue)` may throw `UnsupportedOperationException` because it requires `Iterator.remove`.

The `clear` capability also depends on the skeletal class. `AbstractCollection.clear` relies on iterator removal, whereas `AbstractQueue.clear` repeatedly calls `poll` until empty. Consequently, in the example, the queue does not support iterator removal, yet `clear` still works.

This is a practical reason to read the "Implementation Requirements" of the exact class you extend, rather than applying one mental call model to every collection.

## AbstractMap: entrySet Is Both the Foundation and a Write Path

`Map` is not a subtype of `Collection`. With `AbstractMap`, the foundational method is `entrySet()`: a set view representing the mappings.

From `entrySet()`, the skeletal class can derive `size`, look up keys, read values, compare maps, and create key or value views. A map only needs `entrySet` to become readable, but the quality of this view determines most of the remaining behavior.

For a modifiable map using the skeletal implementation, `put` is the extension point for adding/updating mappings, and the `entrySet` iterator must support removal if inherited removal paths are to work. See [AbstractMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.html).

### Do Not Return a Snapshot When the Contract Requires a Live View

Suppose the map can still be updated. If `entrySet()` always creates a detached copy, a view obtained earlier will not reflect subsequent map changes as required by the contract.

Furthermore, `entrySet().iterator().remove()`, if supported, must remove the mapping from the backing map, not merely remove an element from a temporary copy. The `keySet` and `values` views are likewise bound to the backing map.

In the example, the map copies its source once in the constructor and keeps that copy unmodifiable. `entrySet` returns a view of the exact data the map owns; it does not create a fresh snapshot on every call.

### Blocking put Is Not Enough to Make a Map Read-Only

A map has many potential modification paths:

~~~text
put / putAll / remove / clear
keySet().remove(...)
values().remove(...)
entrySet().iterator().remove()
entrySet().iterator().next().setValue(...)
replaceAll(...) and other default update methods
~~~

If you only make `put` throw `UnsupportedOperationException` while returning writable entries, `Entry.setValue` can still mutate values.

In particular, `Collections.unmodifiableSet(backingMap.entrySet())` only blocks structural set modifications through that wrapper; it does not wrap each individual `Map.Entry` object to block `setValue`. To back a read-only map with an unmodifiable map, returning `entrySet` from a properly constructed `Collections.unmodifiableMap` is a much cleaner approach.

If you implement custom entries, decide whether they are connected to the map or standalone. A `SimpleEntry` can change its own value, but a detached entry does not automatically write back to the map's store. Do not return an entry that appears writable where `setValue` only mutates a copy when the view contract requires updating the underlying mapping. See [Map.Entry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html).

### Supporting put Does Not Mean Default replaceAll Is Supported

The default implementation of `Map.replaceAll` iterates over entries and calls `Entry.setValue`. Therefore, a map that implements `put` but whose entries do not support `setValue` cannot use the default `replaceAll`.

To publish support for it, you must either provide a working entry update path or override the method appropriately. Do not infer from a single working update operation that all default update methods work.

Conversely, `putAll` in `AbstractMap` calls `put` for each mapping. Because an empty source triggers zero `put` calls, the example map accepts `putAll(Map.of())` normally even though `put` is blocked. This behavior aligns with the no-op allowance permitted by [Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

## Complete Program Verifying Capabilities

Save the following code into `MinimalCollectionsDemo.java`. The small classes use existing standard structures as backing stores to focus on the call paths of the skeletal classes, not to replace standard collections.

The program includes six illustrative classes:

- `ReadOnlyBag`: only `iterator/size`, retains duplicate elements.
- `ReadOnlyList`: only `get/size`, copies the source.
- `FixedList`: adds `set`, keeps size fixed.
- `EditableList`: adds `add(int,E)/remove(int)` and updates `modCount`.
- `LimitedQueue`: the five foundational queue methods, intentionally omitting iterator removal.
- `ReadOnlyMap`: only `entrySet` backed by an unmodifiable map copy.

`outcome` is used solely to record exception names for the experiment. In application code, do not turn every `RuntimeException` into a string and continue as if the operation succeeded.

~~~java
import java.util.AbstractCollection;
import java.util.AbstractList;
import java.util.AbstractMap;
import java.util.AbstractQueue;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.ListIterator;
import java.util.Map;
import java.util.Objects;
import java.util.RandomAccess;
import java.util.Set;

public class MinimalCollectionsDemo {
    static final class ReadOnlyBag<E> extends AbstractCollection<E> {
        private final List<E> data;

        ReadOnlyBag(Collection<? extends E> source) {
            data = List.copyOf(source);
        }

        @Override public int size() { return data.size(); }

        @Override public Iterator<E> iterator() {
            Iterator<E> delegate = data.iterator();
            return new Iterator<>() {
                @Override public boolean hasNext() { return delegate.hasNext(); }
                @Override public E next() { return delegate.next(); }
            };
        }
    }

    static final class ReadOnlyList<E> extends AbstractList<E>
            implements RandomAccess {
        private final List<E> data;

        ReadOnlyList(Collection<? extends E> source) {
            data = List.copyOf(source);
        }

        @Override public E get(int index) { return data.get(index); }
        @Override public int size() { return data.size(); }
    }

    static class FixedList<E> extends AbstractList<E> implements RandomAccess {
        protected final ArrayList<E> data;

        FixedList(Collection<? extends E> source) {
            data = new ArrayList<>(source);
        }

        @Override public E get(int index) { return data.get(index); }
        @Override public int size() { return data.size(); }
        @Override public E set(int index, E value) {
            return data.set(index, value);
        }
    }

    static final class EditableList<E> extends FixedList<E> {
        EditableList(Collection<? extends E> source) {
            super(source);
        }

        @Override public void add(int index, E value) {
            data.add(index, value);
            modCount++;
        }

        @Override public E remove(int index) {
            E previous = data.remove(index);
            modCount++;
            return previous;
        }
    }

    static final class LimitedQueue<E> extends AbstractQueue<E> {
        private final int capacity;
        private final ArrayDeque<E> data = new ArrayDeque<>();

        LimitedQueue(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            this.capacity = capacity;
        }

        @Override public int size() { return data.size(); }
        @Override public E peek() { return data.peekFirst(); }
        @Override public E poll() { return data.pollFirst(); }

        @Override public boolean offer(E value) {
            Objects.requireNonNull(value);
            if (data.size() == capacity) {
                return false;
            }
            data.addLast(value);
            return true;
        }

        // Head removal is supported; iterator removal is not supported.
        @Override public Iterator<E> iterator() {
            Iterator<E> delegate = data.iterator();
            return new Iterator<>() {
                @Override public boolean hasNext() { return delegate.hasNext(); }
                @Override public E next() { return delegate.next(); }
            };
        }
    }

    static final class ReadOnlyMap<K, V> extends AbstractMap<K, V> {
        private final Map<K, V> data;

        ReadOnlyMap(Map<? extends K, ? extends V> source) {
            data = Collections.unmodifiableMap(new LinkedHashMap<>(source));
        }

        @Override public Set<Entry<K, V>> entrySet() {
            return data.entrySet();
        }
    }

    static String outcome(Runnable action) {
        try {
            action.run();
            return "OK";
        } catch (RuntimeException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        ReadOnlyBag<String> bag = new ReadOnlyBag<>(List.of("A", "B", "A"));
        System.out.println("bag = " + bag);
        System.out.println("bag-contains-A = " + bag.contains("A"));
        System.out.println("bag-add = " + outcome(() -> bag.add("C")));
        System.out.println("bag-remove-missing = " + bag.remove("Z"));
        System.out.println("bag-remove-existing = " + outcome(() -> bag.remove("A")));
        System.out.println("bag-addAll-empty = " + bag.addAll(List.of()));
        System.out.println("bag-removeIf-no-match = " + bag.removeIf(s -> s.equals("Z")));
        System.out.println("bag-removeIf-match = "
                + outcome(() -> bag.removeIf(s -> s.equals("A"))));

        ArrayList<String> source = new ArrayList<>(List.of("one", "two"));
        ReadOnlyList<String> readOnly = new ReadOnlyList<>(source);
        source.set(0, "changed");
        System.out.println("read-only-snapshot = " + readOnly);
        System.out.println("list-equals = " + readOnly.equals(List.of("one", "two")));
        System.out.println("list-hash-equals = "
                + (readOnly.hashCode() == List.of("one", "two").hashCode()));
        System.out.println("read-only-set = " + outcome(() -> readOnly.set(0, "X")));

        FixedList<String> fixed = new FixedList<>(List.of("B", "A"));
        System.out.println("fixed-set-old = " + fixed.set(0, "C"));
        fixed.sort(null);
        fixed.replaceAll(String::toLowerCase);
        System.out.println("fixed-after-sort-replace = " + fixed);
        ListIterator<String> fixedIt = fixed.listIterator();
        fixedIt.next();
        fixedIt.set("first");
        System.out.println("fixed-after-iterator-set = " + fixed);
        System.out.println("fixed-add = " + outcome(() -> fixed.add("D")));
        System.out.println("fixed-remove-index = " + outcome(() -> fixed.remove(0)));

        EditableList<String> editable = new EditableList<>(List.of("A", "B", "C"));
        editable.add("D");
        ListIterator<String> it = editable.listIterator();
        System.out.println("editable-remove-before-next = " + outcome(it::remove));
        it.next();
        it.remove();
        it.add("X");
        System.out.println("editable-after-iterator = " + editable);
        List<String> view = editable.subList(1, 3);
        view.clear();
        System.out.println("editable-after-sublist-clear = " + editable);
        Iterator<String> oldIterator = editable.iterator();
        editable.add("E");
        System.out.println("editable-old-iterator = " + outcome(oldIterator::next));

        LimitedQueue<String> queue = new LimitedQueue<>(2);
        System.out.println("queue-first-offer = " + queue.offer("A"));
        System.out.println("queue-add = " + queue.add("B"));
        System.out.println("queue-full-offer = " + queue.offer("C"));
        System.out.println("queue-full-add = " + outcome(() -> queue.add("C")));
        System.out.println("queue-remove-existing = "
                + outcome(() -> queue.remove("B")));
        System.out.println("queue-remove-head = " + queue.remove());
        queue.clear();
        System.out.println("queue-after-clear = " + queue);
        System.out.println("queue-empty-poll = " + queue.poll());
        System.out.println("queue-empty-remove = " + outcome(queue::remove));
        System.out.println("queue-null-offer = " + outcome(() -> queue.offer(null)));

        LinkedHashMap<String, Integer> input = new LinkedHashMap<>();
        input.put("A", 1);
        input.put("B", 2);
        ReadOnlyMap<String, Integer> map = new ReadOnlyMap<>(input);
        input.put("A", 99);
        System.out.println("map-snapshot = " + map);
        System.out.println("map-get = " + map.get("A"));
        System.out.println("map-put = " + outcome(() -> map.put("C", 3)));
        System.out.println("map-remove-missing = " + map.remove("Z"));
        System.out.println("map-remove-existing = " + outcome(() -> map.remove("A")));
        System.out.println("map-putAll-empty = " + outcome(() -> map.putAll(Map.of())));
        Map.Entry<String, Integer> entry = map.entrySet().iterator().next();
        System.out.println("map-entry-setValue = " + outcome(() -> entry.setValue(8)));
        System.out.println("map-keySet-remove = " + outcome(() -> map.keySet().remove("A")));
        System.out.println("map-replaceAll = "
                + outcome(() -> map.replaceAll((key, value) -> value + 1)));
        System.out.println("map-after-attempts = " + map);
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 -encoding UTF-8 MinimalCollectionsDemo.java
java MinimalCollectionsDemo
~~~

The code was compiled with `--release 17` and run using OpenJDK Zulu 24.0.2. Exact stdout from the run:

~~~text
bag = [A, B, A]
bag-contains-A = true
bag-add = UnsupportedOperationException
bag-remove-missing = false
bag-remove-existing = UnsupportedOperationException
bag-addAll-empty = false
bag-removeIf-no-match = false
bag-removeIf-match = UnsupportedOperationException
read-only-snapshot = [one, two]
list-equals = true
list-hash-equals = true
read-only-set = UnsupportedOperationException
fixed-set-old = B
fixed-after-sort-replace = [a, c]
fixed-after-iterator-set = [first, c]
fixed-add = UnsupportedOperationException
fixed-remove-index = UnsupportedOperationException
editable-remove-before-next = IllegalStateException
editable-after-iterator = [X, B, C, D]
editable-after-sublist-clear = [X, D]
editable-old-iterator = ConcurrentModificationException
queue-first-offer = true
queue-add = true
queue-full-offer = false
queue-full-add = IllegalStateException
queue-remove-existing = UnsupportedOperationException
queue-remove-head = A
queue-after-clear = []
queue-empty-poll = null
queue-empty-remove = NoSuchElementException
queue-null-offer = NullPointerException
map-snapshot = {A=1, B=2}
map-get = 1
map-put = UnsupportedOperationException
map-remove-missing = null
map-remove-existing = UnsupportedOperationException
map-putAll-empty = OK
map-entry-setValue = UnsupportedOperationException
map-keySet-remove = UnsupportedOperationException
map-replaceAll = UnsupportedOperationException
map-after-attempts = {A=1, B=2}
~~~

## Explaining the Results and Limitations of the Example

### A Read-Only Bag Can Still Have Removal Calls Return Normally

`bag-remove-missing = false` and `bag-addAll-empty = false` are calls that do not modify data. They never reach the blocked write path.

By contrast, `bag-remove-existing` and `bag-removeIf-match` require iterator removal and throw `UnsupportedOperationException`. On the very same object, the difference lies in the actual execution path of the call, not in the collection's capabilities changing between lines.

`ReadOnlyBag` copies its data via `List.copyOf`, so the constructor rejects `null` elements. This is a choice of the example class; not every `AbstractCollection` subclass is required to forbid `null`.

It does not override `equals/hashCode` to use list semantics merely because its internal data is stored in a list. The storage structure is an implementation detail; the published abstract type determines the appropriate equality semantics.

### ReadOnlyList Detaches Source Data and Has List Semantics

After modifying an element in `source`, `readOnly` still displays `[one, two]`. The constructor took a copy of the elements at construction time; the object is not a view of `source`.

`list-equals = true` and `list-hash-equals = true` show that `AbstractList` provides element-wise, order-sensitive comparison semantics compatible with a standard list holding the same data. There is no need to rewrite that algorithm when it already satisfies the contract.

This is still a shallow copy. If the elements are mutable objects, the copy holds references to those same objects. The example uses `String` so that internal element mutation does not distract from the lesson on collection mutability.

### FixedList Only Needs set to Unlock Another Group of Operations

`fixed-set-old = B` serves as a reminder that `set` must return the previous element, not the new element or an arbitrary success flag.

After `sort` and `replaceAll`, the list becomes `[a, c]`; after `ListIterator.set`, it becomes `[first, c]`. The element count remains two.

`fixed-add` and `fixed-remove-index` throw `UnsupportedOperationException`. That is the distinction between replacement and resizing. An API accepting a `List` that only needs to permute or replace elements has different capability requirements than an API that needs to append new rows.

### EditableList Inherits Modification Paths Through Both Iterators and subList

Starting from `[A, B, C]`, the inherited `add("D")` delegates to the subclass's `add(int,E)`. Next, the iterator retrieves `A`, removes `A`, and inserts `X` at the cursor, producing `[X, B, C, D]`.

The `remove` call before `next` throws `IllegalStateException`: removal is supported, but the call occurred in an invalid state. Do not conflate this exception with `UnsupportedOperationException`.

`subList(1,3)` selects `[B,C]`. Calling `clear` on the view leaves the backing list with `[X,D]`. This demonstrates that the write path through the view operates on the underlying data.

Finally, the program creates an iterator and then adds `E` directly through the list. The subsequent `next` call on the old iterator throws `ConcurrentModificationException` in this single-threaded test. This shows that `modCount` is wired into the inherited mechanism; it does not prove that the mechanism provides synchronization for multi-threaded updates.

`data` in `FixedList` is `protected` so the illustrative subclass `EditableList` can share the backing store. When developing a library where arbitrary subclasses are not under your control, design access modifiers carefully so subclasses cannot mutate the backing store while bypassing invariants or modification counters.

### LimitedQueue Supports Head Removal but Not Arbitrary Removal

The capacity-two queue accepts `A` and `B`. When full, `offer("C")` returns `false` while `add("C")` throws `IllegalStateException`. This pair of behaviors is built by `AbstractQueue` on top of `offer`.

`queue.remove("B")` finds the matching element, but because the iterator does not implement `remove`, it throws `UnsupportedOperationException`. `queue.remove()`, however, successfully removes `A` via `poll`.

`queue.clear()` drains the remaining element using `poll`, so it works. Afterward, `poll` returns `null`, whereas `remove()` throws `NoSuchElementException`. Inserting `null` is blocked by `Objects.requireNonNull` before storing data.

The example class provides no waiting, locking, or concurrent usage guarantees. A capacity-bounded queue does not automatically become a `BlockingQueue` or a thread-safe structure.

### ReadOnlyMap Blocks Both Entry and View Modification Paths

The map retains `{A=1, B=2}` even after the input map changes `A` to `99`. Modification blocking is enforced on its private copy, preventing callers holding the source map from directly mutating the example object's store.

`get`, `size`, and string formatting are derived from `entrySet`. However, the inherited `AbstractMap.get` may have to scan entries linearly; the fact that the internal store is a `LinkedHashMap` does not automatically turn the outer class's `get` path into a hash lookup. If read performance matters, override `get/containsKey/size` to delegate appropriately while preserving the contract.

`map-remove-missing = null` is a no-op call. `map-remove-existing`, `map-keySet-remove`, and `map-entry-setValue` are all blocked. `map-replaceAll` is likewise blocked along the entry update path. The final map remains `{A=1, B=2}`.

The map copy is also a shallow copy. With mutable keys, mutating fields that affect `equals/hashCode` after insertion into a map can break lookup assumptions. Do not use a "read-only" label to infer that every contained object is immutable.

## Minimal Method Count Does Not Mean Minimal Quality

### Indices and Sizes Must Be Exact

For a list, the valid index range for `get/set/remove(int)` is from `0` to less than `size()`. `add(int,E)` additionally permits insertion at `size()`, immediately after the last element.

If you write a custom data store, check both boundary rules properly. Do not share a single `index < size` check that accidentally prevents inserting into an empty list or appending at the end.

`size` must be consistent with the number of elements the iterator traverses under supported usage conditions. If the backing store can grow too large to represent as an `int`, follow the `Collection.size` specification rather than letting it overflow into a negative number. For the small classes in the example, the internal standard structures handle this.

When exhausted, `next` must throw `NoSuchElementException` rather than returning `null` as an end signal: a collection might legitimately contain `null` under its own policy. `hasNext` must not consume an element and discard it.

### Element Policies Must Be Explicitly Defined

When implementing a specialized class, document policies such as:

- Whether `null` is permitted.
- Whether duplicates are accepted or uniqueness is enforced.
- Whether ordering is guaranteed.
- Whether objects are copied or held as a live view of the source.
- Whether there are limits on capacity, value ranges, or data types.
- Whether concurrent multi-threaded access is supported or external synchronization is required.

Not every data error is an unsupported operation. If a class supports addition but an element is invalid, throw the exception type appropriate for the published constraint. For querying an invalid value, some interface contracts allow either returning a not-found result or throwing an exception depending on the implementation; do not assume all collections share the exact same policy.

A constructor accepting a `Collection` or `Map` is a recommendation for general-purpose implementations, not an interface method that the compiler forces every class to have. A specialized structure may require capacity parameters or a custom data source; its API must clearly explain how to construct a valid instance.

### Default Methods Must Also Be Included in the Capability Audit

Do not test only the methods you wrote by hand. For a list, there are also `removeIf`, `replaceAll`, `sort`, iterators, list iterators, and sublists. For a map, there are also `putIfAbsent`, `replace`, `compute`, `merge`, `replaceAll`, and views.

For instance, a default method might only perform a write along one branch. A `computeIfAbsent` call might return an existing value without ever calling `put`; that does not prove the map supports writing when a key is absent.

If a class promises that "every write operation fails immediately", keeping only a minimal skeletal implementation may not be sufficient to enforce that strong guarantee. You must review and potentially override all relevant paths, including no-op paths and views. Even if you only promise that data cannot be mutated through the API, you must still ensure no write path was overlooked.

### Bulk Operations Do Not Guarantee Automatic Rollback

An inherited `addAll` may insert elements one by one. If it adds several elements and then encounters invalid data or a capacity limit, the method may throw an exception after partially modifying the collection.

Similarly, `removeIf` may have removed several elements before the predicate throws an error; a bulk update may have replaced some values before failing. Do not advertise "all-or-nothing" atomicity merely because an operation is invoked through a single method name.

If a class requires a stronger guarantee, design an appropriate mechanism: validate preconditions accurately beforehand, build a new state and publish it, or use another update protocol. Pre-validation must also account for whether state could change between checking and writing when multiple threads are involved.

## A Systematic Checklist Before Publishing a Class

Start from your public promises, then trace every execution path.

| Test Category | Valuable Example Inputs |
| --- | --- |
| Reading | Empty, single element, multiple elements, duplicates if allowed |
| Indices | `-1`, `0`, last index, `size()`, greater than `size()` |
| Addition | New value, duplicate value, at head/tail, when full |
| Replacement | Returned old value, identical value, invalid value |
| Removal | Existing value, absent value, head removal, iterator removal |
| Iterator State | Before `next`, after one `next`, double removal, exhausted |
| Bulk Operations | Empty source, no match, matching elements, mid-operation invalid data |
| Views | Do edits via `subList/keySet/values/entrySet` properly propagate to the backing store? |
| Equality | Compare against a standard implementation of the same abstract type |
| Encapsulation | Can the original source, iterator, or entries mutate data unintentionally? |

You do not need to rewrite a test suite for the entire JDK to test a small class, but inherited paths directly tied to your promised capabilities must be verified. A test that merely "creates an object and prints it" checks very little of the contract.

For performance, count call paths first. If `iterator.next` calls `get(i)` and `get(i)` takes time proportional to `i`, a full traversal becomes quadratic. If `AbstractMap.get` scans `entrySet`, repeated lookups can be expensive even when the physical store has a hash table. First satisfy the contract, then optimize measured or clearly analyzed bottlenecks.

## Self-Check Exercises

### 1. Is implementing only size enough to create a concrete AbstractCollection?

A subclass implements only `size()` and wants to rely on the skeletal class for everything else.

**Answer:** Not enough. You must also provide `iterator()`. The iterator must traverse the actual data; an iterator that is always empty while `size` is non-zero is not a valid implementation either.

### 2. Does AbstractSet automatically remove duplicate elements in a constructor?

A custom set class stores `new ArrayList<>(source)` and returns the list's iterator. `source` contains two equal elements.

**Answer:** No. The subclass must maintain the uniqueness invariant right from the constructor and across all update paths. `AbstractSet` does not automatically filter the backing store for its subclasses.

### 3. Why does an empty addAll succeed while an actual add fails?

A read-only collection inherits `addAll` from its skeletal class.

**Answer:** With an empty source, no `add` call is ever executed. The general contract allows a no-op call to complete normally. Do not use this case to probe whether addition is supported.

### 4. Can a List that only supports set be sorted?

A class implements `get/size/set` properly but disallows adding and removing elements.

**Answer:** It can use the default sorting mechanism because the element count does not change and writing elements back through the list iterator relies on `set`. Always check the specific implementation's contract; do not infer from `add` being blocked that all mutating operations are blocked.

### 5. Why can a queue remove its head element but fail to remove a specific value?

An `AbstractQueue` subclass has a working `poll`, while its iterator only supports reading.

**Answer:** `remove()` relies on `poll`. The inherited `remove(Object)` searches using the iterator and then requires `iterator.remove` when a match is found. The two overloads go through two different foundational method groups.

### 6. Is a Map read-only if it blocks put but its entries are still writable?

`entrySet().iterator().next().setValue(v)` mutates the map's data.

**Answer:** No. A map has an update path through its entries. You must block or properly design the entries, iterators, and views as well; blocking only `put` is insufficient.

### 7. Is incrementing modCount inside set always the right thing to do?

A list class uses `set` to replace an element without changing the list's structure, yet every `set` call increments `modCount`.

**Answer:** You should not increment it out of habit. Under this model, replacing an element is not a structural modification. The counter must reflect the kind of changes that the published iterator mechanism is meant to track; updating it improperly can cause iterators to throw false modification errors. Never use `modCount` as a substitute for thread synchronization.

### 8. Is there a contradiction when put is supported but replaceAll fails at setValue?

A custom map implements `put`, returns entries that do not support `setValue`, and keeps the default `replaceAll`.

**Answer:** The default `replaceAll` works through entries, so it may be unsupported in that design. If the class intends to publish support for `replaceAll`, it must provide a working implementation; testing that `put` succeeds does not test this update path.
