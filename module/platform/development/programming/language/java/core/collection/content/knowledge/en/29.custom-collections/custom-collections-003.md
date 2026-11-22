# AbstractQueue and AbstractMap

## 1. Skeletal classes provide behavior, subclasses provide backing data

When writing a custom collection, the difficult part is not just storing elements. Callers also expect many methods to have consistent relationships: adding, removing, iterating, inspecting contents, converting to arrays, comparing, and operating through views.

Skeletal implementation classes reduce repetitive work by building many methods on top of a few primitive operations. `AbstractQueue` and `AbstractMap` are two examples:

- `AbstractQueue` builds several Queue operations on top of `offer`, `poll`, and `peek`.
- `AbstractMap` builds many Map operations on top of viewing key–value pairs through `entrySet()`.

They do not pre-determine everything: retrieval order, capacity limits, key storage structure, mutability, and lookup cost still need to be decided.

General model:

```text
Interface contract
    ↓
Skeletal class: implements methods based on primitive operations
    ↓
Subclass: holds the data and properly implements the primitive operations
```

One flawed primitive method can break multiple inherited methods at once. Conversely, when the primitive foundation is sound and appropriate, a subclass can reuse a significant amount of behavior without reimplementing it from scratch.

This article uses Java 17 or later. Three standalone programs successively illustrate a bounded FIFO queue, a small mutable map, and an unmodifiable map. They reuse existing container structures to focus on the relationships among the skeletal class's methods; it is not recommended to replace standard collections with these illustrative classes in general applications.

## 2. Position in the type system and subclass responsibilities

| Aspect | AbstractQueue | AbstractMap |
|---|---|---|
| Primary interface | `Queue<E>` | `Map<K, V>` |
| Direct superclass | `AbstractCollection<E>` | `Object` |
| Core of the underlying implementation | Trial insertion, removing head, inspecting head, iteration, and counting | Set-view of key–value mappings |
| Where is data stored? | Chosen by the subclass | Chosen by the subclass |
| Automatically provides concurrency? | No | No |
| Automatically chooses ordering? | No | No |
| Can be instantiated directly? | Requires a concrete subclass | Requires a concrete subclass |

`Map` belongs to the Java Collections Framework, but it is not a subinterface of `Collection`. Rather, a map's key set, entry set, and value collection are collection views.

Nor should `AbstractQueue` be equated with `BlockingQueue`. Extending it does not automatically create `put`, `take`, or timed waiting operations.

These two skeletal classes provide default algorithms rather than automatically making a subclass's data thread-safe for concurrent access. The mutable examples in this article are designed for single-threaded use or well-defined external synchronization.

## 3. AbstractQueue: from failure-indicating return values to exceptions

### 3.1. Five primitive methods to provide

At a minimum, a concrete subclass must implement:

| Method | Contract to maintain |
|---|---|
| `offer(e)` | Attempt insertion; return `true` on success, return `false` if insertion cannot proceed due to applicable capacity restrictions; do not accept `null` |
| `poll()` | Retrieve and remove the head of the queue; return `null` if empty |
| `peek()` | Inspect the head of the queue without removing it; return `null` if empty |
| `size()` | Current number of elements according to the implementation's contract |
| `iterator()` | Properly iterate over the data in the published order |

`AbstractQueue` uses `false` or `null` results to build its exception-throwing counterparts. Consequently, it is suited for queues that do not store `null` elements. See the [AbstractQueue foundation contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractQueue.html).

The subclass itself defines which element is the "head of the queue." FIFO, priority, or LIFO queues may have different rules. Do not assume that every queue extending this skeleton is FIFO.

`offer` returns `false` when an element cannot be added under normal policy conditions, such as when the queue is full. That does not mean every input error must be turned into `false`; invalid arguments may still need to throw an exception as required by the contract.

### 3.2. Relationships between method pairs

| Inherited method | Underlying primitive used | When the operation fails |
|---|---|---|
| `add(e)` | `offer(e)` | Throws `IllegalStateException` if `offer` returns `false` |
| `remove()` | `poll()` | Throws `NoSuchElementException` if `poll` returns `null` |
| `element()` | `peek()` | Throws `NoSuchElementException` if `peek` returns `null` |

These represent two ways of expressing the same Queue operations with different failure policies. See [Queue method pairs](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html).

There is no need to manually override all six methods just to preserve this default relationship. However, if you override one method, you must maintain consistency with the remaining methods.

For example, if `peek` returns element B while `poll` removes element A in an unchanged state, callers no longer have a consistent meaning of "the head of the queue."

### 3.3. clear and addAll also rely on the chosen primitives

By default, `clear()` repeatedly calls `poll()` until it receives `null`. If `poll` is implemented to only inspect without removing, the clearing operation may never terminate. If `poll` throws an exception when empty instead of returning `null`, the clearing path no longer conforms to the foundation expected by the skeletal class.

By default, `addAll` inserts elements one by one through the `add` path. If one insertion throws an exception, preceding elements may already have entered the queue. It is not an all-or-nothing transaction that automatically rolls back.

```text
addAll([C, D, E])
    → add(C) → offer(C) → succeeds
    → add(D) → offer(D) → succeeds
    → add(E) → offer(E) → no space left → exception

C and D may still remain in the queue.
```

Mutability through the iterator also matters. `remove(Object)` is a different operation from `remove()`: the object-taking version searches for a matching element and relies on the iterator to remove it.

If the iterator does not support removal, you must not assume that every inherited removal operation will work. Supported operations must be accurately documented and tested.

## 4. Queue program: five primitive methods, many inherited behaviors

File `QueueSkeletonDemo.java`:

```java
import java.util.AbstractQueue;
import java.util.ArrayDeque;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;

public class QueueSkeletonDemo {
    static final class BoundedFifo<E> extends AbstractQueue<E> {
        private final int capacity;
        private final ArrayDeque<E> elements = new ArrayDeque<>();

        BoundedFifo(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            this.capacity = capacity;
        }

        @Override
        public boolean offer(E element) {
            Objects.requireNonNull(element, "element");
            if (elements.size() == capacity) {
                return false;
            }
            return elements.offerLast(element);
        }

        @Override
        public E poll() {
            return elements.pollFirst();
        }

        @Override
        public E peek() {
            return elements.peekFirst();
        }

        @Override
        public int size() {
            return elements.size();
        }

        @Override
        public Iterator<E> iterator() {
            return elements.iterator();
        }
    }

    public static void main(String[] args) {
        var queue = new BoundedFifo<String>(2);
        System.out.println("offerA=" + queue.offer("A"));
        System.out.println("offerB=" + queue.offer("B"));
        System.out.println("peek=" + queue.peek());
        System.out.println("offerC=" + queue.offer("C"));
        try {
            queue.add("C");
        } catch (IllegalStateException ex) {
            System.out.println("fullAdd=" + ex.getClass().getSimpleName());
        }

        System.out.println("removeHead=" + queue.remove());
        System.out.println("removeB=" + queue.remove("B"));
        try {
            queue.addAll(List.of("C", "D", "E"));
        } catch (IllegalStateException ex) {
            System.out.println("bulkFailure=" + ex.getClass().getSimpleName());
        }
        System.out.println("afterBulk=" + queue);
        queue.clear();
        System.out.println("emptyPoll=" + queue.poll());
        try {
            queue.element();
        } catch (java.util.NoSuchElementException ex) {
            System.out.println("emptyElement=" + ex.getClass().getSimpleName());
        }

        queue.addAll(List.of("X", "Y"));
        Iterator<String> iterator = queue.iterator();
        System.out.println("iteratorNext=" + iterator.next());
        iterator.remove();
        System.out.println("afterIteratorRemove=" + queue);
        try {
            queue.offer(null);
        } catch (NullPointerException ex) {
            System.out.println("nullOffer=" + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 QueueSkeletonDemo.java
java QueueSkeletonDemo
```

Stdout:

```text
offerA=true
offerB=true
peek=A
offerC=false
fullAdd=IllegalStateException
removeHead=A
removeB=true
bulkFailure=IllegalStateException
afterBulk=[C, D]
emptyPoll=null
emptyElement=NoSuchElementException
iteratorNext=X
afterIteratorRemove=[Y]
nullOffer=NullPointerException
```

### 4.1. Representation and invariants of the example

`BoundedFifo` stores its data in a private `ArrayDeque`, appending at the tail and removing from the head. The capacity is an element count limit enforced by the wrapper class, not a guarantee that the internal array has only that exact number of slots.

`offer` checks for `null` before checking fullness. When space is available, it appends to the tail; when the limit has been reached, it returns `false`. All valid insertion paths go through this method.

`poll` and `peek` both access the head of the deque, but one removes the element while the other only reads it. The iterator is obtained directly from the backing data structure, so it traverses the same contents and supports removing visited elements.

Do not return an iterator over a defensive copy if you want iterator removals to affect the original queue.

### 4.2. Which call paths do the results demonstrate?

A and B are accepted; C cannot enter yet, so `offer` returns `false`. When `add("C")` is called, the skeletal class itself translates that failure into an exception.

`remove()` retrieves A via `poll`. `remove("B")` locates B through the collection operation path and removes it from the backing data.

After the queue becomes empty, adding C, D, and E in bulk accepts only C and D. The exception on E does not roll back C and D. The output `afterBulk=[C, D]` is a key behavior to observe, not a bug in the verification program.

`clear` empties the data through the polling path. The subsequent `poll` returns `null`, whereas `element` throws an exception because there is no queue head.

Finally, the iterator advances past X and removes X, leaving only Y in the queue. This verifies that iterator mutability affects inherited methods.

### 4.3. What the skeletal class does not automatically provide

This example has no blocking wait operations, multi-threaded synchronization, or priority policy. If a queue requires those capabilities, you must choose an appropriate implementation or design additional mechanisms.

A Queue also does not automatically define element-by-element equality semantics like `List`. For this example class, which does not override `equals`/`hashCode`, do not expect two queues with identical contents to compare equal by value.

The Queue contract and skeletal implementation do not promise that every operation will share the exact semantics of another collection type.


## 5. AbstractMap: entrySet is the implementation foundation, not just an output for printing

### 5.1. The central abstract method

`AbstractMap<K, V>` requires subclasses to provide `entrySet()`, returning a `Set<Map.Entry<K, V>>` view of the map's mappings. From this, the skeletal class provides many read operations and related views.

`put` is unsupported by default. To support adding or replacing mappings, a subclass must provide a suitable `put` implementation. To use the default removal paths, the entry-set's iterator must support removal in accordance with its advertised capabilities. See [AbstractMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.html).

Note that `entrySet` returns a **view of the map**, not a detached snapshot of the data. A mutable map that returns a disconnected copy of entries fails to uphold the view relationship that callers are entitled to rely on.

### 5.2. Which methods are built from entrySet?

| Method or group | Default underlying mechanism to consider |
|---|---|
| `size()` | Size of the entry-set |
| `isEmpty()` | Result of the size check |
| `get(key)`, `containsKey(key)` | Iterates over entries to find the key |
| `containsValue(value)` | Iterates over entries to find the value |
| `remove(key)` | Finds the matching entry and removes it via the iterator |
| `clear()` | Calls `entrySet().clear()` |
| `putAll(map)` | Calls `put` for each mapping in the source map |
| `keySet()`, `values()` | Views backed by the map's mappings and entry-set iterator |
| `equals`, `hashCode`, `toString` | Contents of the mappings |

This table describes the skeletal class's default implementations. A subclass may override them to use a more efficient representation, provided it preserves the contractual semantics.

In particular, extending `AbstractMap` does not automatically create a hash table. By default, `get` scans the entry-set linearly; if you need indexed lookups, you must supply the corresponding representation and lookup path.

### 5.3. The entry-set must uphold the semantics of a Set of mappings

An entry consists of both a key and a value. When comparing one entry to another, you cannot compare only the key and ignore the value.

For example, if the map currently contains `a → 20`:

- Removing `"a"` through `keySet` checks only the key.
- Removing the entry `("a", 999)` through `entrySet` must not be treated as a match merely because the key is the same.
- Removing the entry `("a", 20)` through `entrySet` can remove the mapping if removal is supported.

A Map must not contain two separate mappings for the same key under its published key-equivalence rule. Even if the underlying entry storage is a list, it must enforce this invariant itself, because `AbstractSet` does not automatically deduplicate elements for arbitrary backing representations.

`entrySet` is not a backdoor for inserting new pairs in place of `put`. The `add` method on the entry-set should not be arbitrarily enabled just because its return type is `Set`; the view's capabilities must align with the Map contract.

### 5.4. get returning null does not determine whether a key exists

If a map permits `null` values, two distinct states can cause `get(k)` to return `null`:

```text
There is no mapping for k.
There is a mapping k → null.
```

In sequential usage, `containsKey` distinguishes between the two. In multi-threaded usage, two separate reads do not automatically form an atomic operation.

When writing `put` yourself, do not rely solely on `get(key) == null` to conclude that the key does not exist before appending a new entry. When null values are permitted, doing so can create duplicate entries for the same key.

## 6. Map program: a live view connected to backing data

File `MapSkeletonDemo.java`:

```java
import java.util.AbstractMap;
import java.util.AbstractSet;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class MapSkeletonDemo {
    static final class TinyMap<K, V> extends AbstractMap<K, V> {
        private final List<Entry<K, V>> entries = new ArrayList<>();
        private final Set<Entry<K, V>> entryView = new AbstractSet<>() {
            @Override
            public Iterator<Entry<K, V>> iterator() {
                return entries.iterator();
            }

            @Override
            public int size() {
                return entries.size();
            }

            @Override
            public void clear() {
                entries.clear();
            }
        };

        @Override
        public Set<Entry<K, V>> entrySet() {
            return entryView;
        }

        @Override
        public V put(K key, V value) {
            for (Entry<K, V> entry : entries) {
                if (Objects.equals(entry.getKey(), key)) {
                    return entry.setValue(value);
                }
            }
            entries.add(new SimpleEntry<>(key, value));
            return null;
        }
    }

    public static void main(String[] args) {
        var map = new TinyMap<String, Integer>();
        System.out.println("firstPut=" + map.put("a", 1));
        System.out.println("replaceA=" + map.put("a", 2));
        map.put("b", null);
        System.out.println("size=" + map.size());
        System.out.println("getB=" + map.get("b"));
        System.out.println("hasB=" + map.containsKey("b"));
        System.out.println("hasMissing=" + map.containsKey("missing"));

        Set<String> keys = map.keySet();
        var values = map.values();
        map.put("c", 3);
        System.out.println("liveKeys=" + keys);
        System.out.println("liveValues=" + values);

        Iterator<Map.Entry<String, Integer>> iterator = map.entrySet().iterator();
        Map.Entry<String, Integer> first = iterator.next();
        System.out.println("oldEntryValue=" + first.setValue(20));
        System.out.println("mapAfterEntryWrite=" + map);
        System.out.println("removeNullValue=" + values.remove(null));
        System.out.println("removeKeyC=" + keys.remove("c"));

        Map<String, Integer> reference = Map.of("a", 20);
        System.out.println("equalsForward=" + map.equals(reference));
        System.out.println("equalsBackward=" + reference.equals(map));
        System.out.println("sameHash=" +
                (map.hashCode() == reference.hashCode()));

        System.out.println("removeWrongEntry=" +
                map.entrySet().remove(new AbstractMap.SimpleImmutableEntry<>("a", 999)));
        System.out.println("removeExactEntry=" +
                map.entrySet().remove(new AbstractMap.SimpleImmutableEntry<>("a", 20)));
        System.out.println("emptyAfterEntryRemove=" + map.isEmpty());
        map.put(null, 7);
        System.out.println("nullKeyValue=" + map.get(null));
        map.clear();
        System.out.println("sizeAfterClear=" + map.size());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 MapSkeletonDemo.java
java MapSkeletonDemo
```

Stdout:

```text
firstPut=null
replaceA=1
size=2
getB=null
hasB=true
hasMissing=false
liveKeys=[a, b, c]
liveValues=[2, null, 3]
oldEntryValue=2
mapAfterEntryWrite={a=20, b=null, c=3}
removeNullValue=true
removeKeyC=true
equalsForward=true
equalsBackward=true
sameHash=true
removeWrongEntry=false
removeExactEntry=true
emptyAfterEntryRemove=true
nullKeyValue=7
sizeAfterClear=0
```

### 6.1. What did the subclass implement?

`TinyMap` keeps its entries in a private list. This is a small representation designed to make the mechanics clear, not an optimized hash table.

`entryView` is an `AbstractSet`:

- `size` reads directly from the backing data list.
- Its iterator traverses that exact list and supports `remove`.
- `clear` calls `entries.clear()` directly.
- Adding entries directly is not enabled; the class does not override `add` on the set-view.

`put` searches for a key using `Objects.equals`. If found, it replaces the value on the existing entry and returns the old value. If not found, it appends a new `SimpleEntry`.

Because only `put` creates new mappings and it checks for existing keys first, the representation maintains the invariant that no two mappings share the same key. `SimpleEntry` provides entry equality based on both key and value.

The class does not manually override `get`, `containsKey`, `keySet`, `values`, `equals`, or `hashCode`. The results shown in stdout flow through the skeletal class's default execution paths.

### 6.2. Updating an existing key does not increase the number of mappings

Initially putting `a → 1` returns `null`; replacing it with `a → 2` returns `1`. After adding `b → null`, the size is 2.

Key `b` is present even though `get("b")` returns `null`. `containsKey("b")` is `true`, whereas `"missing"` is absent.

The example also tests a `null` key, because this implementation intentionally permits it and uses null-safe comparisons. Another implementation might forbid null, in which case it must define and enforce that policy consistently.

### 6.3. keySet and values are live views connected to the map

`keys` and `values` are obtained before key `c` is added. Yet they still reflect `c` when inspected after the insertion, proving that they are not two independent snapshots.

Removing the `null` value via `values.remove(null)` removes the entire corresponding mapping, rather than merely changing its value to something else. Removing `c` via `keys.remove("c")` likewise removes the `c` mapping.

`values()` is a `Collection`, not a `Set`: multiple distinct keys may map to equal values. Removing a matching value through `values()` removes a single matching mapping; it does not mean every mapping with that value is automatically removed.

Key and value views support appropriate removal operations when the backing map supports removal, but they do not support `add` as a way to create incomplete mappings. A key alone is insufficient to determine a value, and a value alone is insufficient to determine a key.

The relationship between a map and its views is a core part of the [Map contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#entrySet()), not an incidental convenience just for printing data.

### 6.4. Entry.setValue is a distinct update path

In the example, the first entry is obtained via the iterator, and `setValue(20)` directly updates the value held by the map. It returns the previous value, `2`.

An entry may or may not support modifying its value. If an implementation supports it, it must maintain the proper relationship with the backing map within the valid lifetime of the entry. Do not promise that an obtained entry will remain connected across arbitrary structural modifications to the map or after the entry itself has been removed. See the [Map.Entry contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html).

Because this example stores `SimpleEntry` instances directly in the list, changing an entry's value mutates the actual mapping. If a map returned detached copy entries while still allowing `setValue`, callers could mutate the copy while leaving the map unchanged, violating expectations for a mutable view entry.

Support for `put`, support for removal, and support for mutation via entries should each be decided deliberately. An implementation is not required to support every optional operation simply because it supports one of them, but its API paths must not make contradictory promises.

### 6.5. Removing an entry requires matching both key and value

When the map holds `a → 20`, removing the entry `a → 999` returns `false`; removing the entry `a → 20` returns `true`.

This path relies on the entry-set iterator's ability to remove elements from the backing list. If the iterator only traversed a copy or did not support `remove`, the default removal paths could not be considered working.

Checking bidirectional `equals` against `Map.of("a", 20)` along with matching hash codes verifies the inherited Map value semantics. Two objects do not need to share the same implementation class to be equal by content.

### 6.6. Representation costs remain the subclass's responsibility

With the list of entries in this example, finding a key and inserting or replacing a key must scan through mappings sequentially. The default `get` searches linearly in the same way. No hash index is created automatically.

`entryView.clear` is overridden to invoke the list's clearing path directly. Relying solely on element-by-element removal through an iterator over a list that shifts elements on each removal would incur unnecessary repeated work.

This is a purposeful extension point: preserving the view semantics while substituting an execution path suited to the backing representation. Sound optimization starts with understanding which method calls which, rather than randomly overriding many methods at once.


## 7. Unmodifiable maps: controlling both entries and views

### 7.1. Merely omitting a put override does not close all mutation paths

By default, `AbstractMap.put` throws `UnsupportedOperationException`. That alone is not enough to make a map read-only if the subclass's entry-set still permits element removal or if its entries still permit changing values.

The mutation paths to examine include:

```text
map.put(...)
map.remove(...)
map.clear()
map.entrySet().iterator().remove()
entry.setValue(...)
map.keySet().remove(...)
map.values().remove(...)
```

If a map is meant to be unmodifiable, its entry source must enforce appropriate restrictions across all exposed paths.

A `Set<Map.Entry<K,V>>` that disallows adding or removing elements does not automatically block `setValue` on the entry objects inside it. Just as an unmodifiable list can still hold mutable element objects, an unmodifiable set wrapper does not automatically make each entry immutable.

### 7.2. A program that also closes the entry mutation path

File `ReadOnlyMapSkeletonDemo.java`:

```java
import java.util.AbstractMap;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

public class ReadOnlyMapSkeletonDemo {
    static final class FrozenMap<K, V> extends AbstractMap<K, V> {
        private final Map<K, V> frozen;

        FrozenMap(Map<? extends K, ? extends V> source) {
            frozen = Collections.unmodifiableMap(new LinkedHashMap<>(source));
        }

        @Override
        public Set<Entry<K, V>> entrySet() {
            return frozen.entrySet();
        }
    }

    public static void main(String[] args) {
        var source = new LinkedHashMap<String, Integer>();
        source.put("x", 1);
        var frozen = new FrozenMap<>(source);
        source.put("y", 2);
        System.out.println("frozen=" + frozen);
        System.out.println("hasSourceAddition=" + frozen.containsKey("y"));

        try {
            frozen.put("z", 3);
        } catch (UnsupportedOperationException ex) {
            System.out.println("put=" + ex.getClass().getSimpleName());
        }
        try {
            frozen.entrySet().iterator().next().setValue(9);
        } catch (UnsupportedOperationException ex) {
            System.out.println("entryWrite=" + ex.getClass().getSimpleName());
        }
        try {
            frozen.keySet().remove("x");
        } catch (UnsupportedOperationException ex) {
            System.out.println("keyRemove=" + ex.getClass().getSimpleName());
        }
        System.out.println("unchanged=" + frozen);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ReadOnlyMapSkeletonDemo.java
java ReadOnlyMapSkeletonDemo
```

Stdout:

```text
frozen={x=1}
hasSourceAddition=false
put=UnsupportedOperationException
entryWrite=UnsupportedOperationException
keyRemove=UnsupportedOperationException
unchanged={x=1}
```

The constructor creates a private `LinkedHashMap` copy from the source and wraps it with `Collections.unmodifiableMap`. Because `entrySet` is returned from the properly wrapped map, the entries observed through it also block value modifications to the backing data. See [unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)).

The subclass implements only `entrySet`; all remaining read operations go through the skeleton. The default `put` is rejected, `setValue` on an entry is rejected, and removing key `"x"` through the key view is also rejected.

Adding `"y"` to the external source map after construction does not cause `"y"` to appear in the private map. That isolation comes from the defensive copy step, not merely from the unmodifiable wrapper.

This example serves to illustrate how to connect a safe entry-set to the skeletal class. If you simply need an unmodifiable map in an application, you can use standard library utilities directly; creating a custom subclass is not always necessary.

### 7.3. Structural copying is not deep copying

Creating a new map still retains references to the same key and value objects. If those objects are internally mutable, they are not automatically frozen.

In particular, keys must maintain stable identity and equality semantics while serving as map keys. Read-only access through a map reference cannot prevent external code from mutating a key object if mutable keys are used.

The example uses `String` keys and `Integer` values to avoid conflating element-level mutability with map write paths.

### 7.4. Do not rely on retained entries across arbitrary source changes

A map entry's usage rules are tied to its view and traversal context. If you need a standalone record, create an appropriate independent copy of the entry; do not hold onto a view entry and assume it will forever remain a valid update handle after structural operations.

Conversely, do not return detached copies when the API contract promises a live view capable of writing through to the backing map. Choose clearly between "an independent read-only entry copy" and "a live map view entry," and keep that choice consistent.

## 8. Foundation bugs that break multiple methods at once

### 8.1. Circular calls between size and entrySet.size

A map may compile cleanly yet fail at runtime when computing its size if the two sides delegate back to each other:

```text
map.size()
    → entrySet().size()
        → map.size()
            → entrySet().size()
                → continues infinitely without ever reading actual backing data
```

That is infinite recursion, not valid code reuse.

In `TinyMap`, `entryView.size` directly calls `entries.size`. That touches the actual backing storage and terminates the call chain.

A related mistake is implementing the entry-set's iterator by iterating over the map's own `keySet()`, while the default `keySet()` is itself built on top of the entry-set iterator. Always trace the dependency graph before wiring views through one another.

### 8.2. Returning a snapshot instead of a live view for a mutable map

If `entrySet` merely returns a detached copy of entries disconnected from the backing store, a previously obtained view may fail to reflect subsequent additions or removals. Furthermore, if removal is permitted on that set, removing an entry only mutates the copy.

Calls to `entrySet()` are not required to return the exact same view object identity in every implementation. What must be preserved are the live data relationship and operational semantics promised by the contract.

In `TinyMap`, a single `entryView` instance is held and reads directly from the backing list. In the read-only map, the view delegates to an internal unmodifiable map. Both approaches avoid detached copies that would violate view semantics.

### 8.3. Confusing peek with poll, or allowing null as valid data in an AbstractQueue foundation

If `peek` removes an element, a simple inspection silently loses data before the caller performs a retrieval. If `poll` fails to remove the element, `remove` and `clear` cannot uphold their contracts.

If a queue permits `null` elements, the skeletal class can no longer distinguish whether `poll` returned `null` because the queue was empty or because the head element was actually `null`. That is why rejecting `null` must be enforced on all insertion paths.

Do not return an arbitrary placeholder element when empty just to avoid returning `null`. Failure-indicating return values must adhere strictly to the contract.

### 8.4. Duplicate keys caused by checking only values

A map that permits `null` values must distinguish between "key absent" and "key present with a null value." A `put` path that relies solely on the result of `get` can insert a duplicate mapping if it mishandles this case.

In `TinyMap`, `put` searches for the key itself among the entries. When found, it replaces the entry's value rather than appending a second entry just because the old value was `null`.

Similarly, removing an entry through the entry view must check both key and value. Comparing by key alone is the semantics of a different operation.

### 8.5. Inconsistently advertised mutability

A map might support `put` without supporting mutation via `Entry.setValue`, or it might reject certain other optional operations. What matters is documenting and enforcing each capability consistently.

If you only implement `put` and assume `remove` will work automatically, callers will encounter `UnsupportedOperationException` if the entry-set iterator does not support `remove()`.

If a queue supports `poll` but its iterator does not support `remove()`, the default `clear` still works through `poll`, whereas `remove(Object)` follows a different path via the iterator. Do not assume that because one removal method succeeds, all removal methods are supported.

For no-op calls—such as attempting to remove a non-existent key—whether an exception is thrown depends on the contract and the specific execution path reached. Avoid writing overly broad test rules assuming that every method whose name suggests mutation must unconditionally throw an exception in every state.

## 9. Performance costs, default interface methods, and concurrency

### 9.1. Reusing skeletal algorithms does not automatically yield HashMap performance

In `TinyMap`, the default `get` and `containsKey` must scan the entry list linearly. The example's `put` also performs a linear search.

If many new keys are inserted via `putAll`, each individual `put` scans a progressively growing map. The fact that the skeletal class wrote the outer loop does not make the overall operation linear in time.

Map comparison operations also depend on the lookup cost of the other map being compared. An operation that appears to iterate only once can still invoke expensive lookups inside its loop.

Always read the implementation specifications (`@implSpec`) of inherited methods, and override hot spots when your backing representation offers a better approach. You can compare the [call paths of AbstractMap in OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/AbstractMap.java).

### 9.2. The underlying iterator determines many removal costs

An iterator that removes elements directly from a linked structure has different performance characteristics from an iterator that removes elements from an array by shifting subsequent elements. When a default method repeats removals in a loop, that difference multiplies.

That is why `entryView.clear` in our example calls `entries.clear()` instead of letting `AbstractCollection.clear()` iterate through every entry and call `iterator.remove()`. It produces the same outcome while using a clearing path suited to the backing store.

For a queue, the default `clear` repeatedly invokes `poll`. If a backing representation offers a more efficient bulk clear that still honors all invariants, the subclass can override `clear`. Do not optimize by skipping reference cleanup (causing memory leaks) or leaving views in an inconsistent state.

### 9.3. Default interface methods are part of the usable API surface

A Map class is not called exclusively through methods declared in the body of `AbstractMap`. The `Map` interface also provides default methods such as `compute`, `merge`, `replaceAll`, and conditional update operations.

For instance, a default method's execution path may rely on `put`, `remove`, or `Entry.setValue`. If the required underlying primitive capability is unsupported, the composite default method may also fail whenever a modification is needed.

Do not assume that because a subclass compiles, every interface method has been validated against your new representation. Review the full interface contract and verify the behaviors you intend to provide to callers.

### 9.4. Skeletal classes do not provide ConcurrentMap or BlockingQueue contracts

A `get` followed by a `put` in `TinyMap` does not automatically become an atomic action. Nor do standard default methods on `Map` acquire concurrency guarantees just because their names resemble methods on concurrent classes.

Likewise, checking "is capacity available" and then inserting in `BoundedFifo.offer` is logic meant for single-threaded or externally synchronized usage. Calling it freely from multiple threads on an unsynchronized private `ArrayDeque` does not make a valid concurrent queue.

Supporting multi-threaded access requires a dedicated design covering state visibility, compound actions, iterators, and object lifecycles. You cannot simply sprinkle `synchronized` on a few primitive methods while ignoring views and inherited operations.

## 10. How to verify a subclass of the two skeletons

### 10.1. For Queue

A meaningful test suite should cover:

- When empty: `poll`/`peek` return `null`, and `remove`/`element` throw the expected exceptions.
- When space is available: `offer` and `add` insert elements in the proper order.
- When full (if bounded): `offer` returns `false`, and `add` throws `IllegalStateException`.
- `null` elements are properly rejected across all insertion paths.
- `poll` actually removes the head element, whereas `peek` leaves it intact.
- The iterator traverses the expected contents and supports whatever removal capability is advertised.
- `clear`, `remove(Object)`, and `addAll` execute cleanly through valid paths.
- The resulting queue state after a mid-batch bulk operation failure is well understood.

The example in this article exercised representative paths for comparison. When writing a new implementation, you can also test sequences of operations against a reference model sharing the same bounding and ordering policy, rather than inspecting only internal fields.

### 10.2. For Map

At a minimum, tests should cover:

- Inserting new keys and replacing existing keys.
- Return values of `put` and `remove`.
- Null policies for both keys and values.
- Uniqueness of keys (no two mappings for the same key).
- Consistency across `get`, `containsKey`, `containsValue`, and `size`.
- Live views continuing to reflect the backing store after valid mutations.
- Removals through `keySet`, `values`, and `entrySet` behaving according to advertised capabilities.
- Entries supporting or rejecting `setValue` according to policy.
- Symmetric `equals` and matching `hashCode` against a standard reference map.
- `clear` and bulk operations preserving all contractual invariants.

Do not test only `put` and `get` while ignoring views: because the views form the foundation of the skeletal class itself, bugs in the views propagate to many other methods.

### 10.3. What the examples have and have not proven

The three programs in this article were compiled and executed on Java 17. Their stdout outputs verify specific functional branches, including state after intentional exceptions and write-through mutations via views.

These examples do not benchmark execution speed, measure memory footprint in bytes, or prove thread-safety under concurrency. Nor do they replace deeper testing if a structure is scaled to large datasets, extended with new mutation capabilities, or shared across threads.

Keeping claims aligned with what was actually tested helps you decide when primitive methods can be safely reused and when a custom redesign is required.

## 11. Practice

### Exercise 1: trace the call graph before overriding

For the example queue, trace the call path for:

1. `add("A")`.
2. `remove()`.
3. `element()`.
4. `clear()`.
5. `remove("A")`.

Why do item 2 and item 5 not follow the same execution path? If `iterator.remove` support were dropped, which operation would still work and which operation would need to be reconsidered?

Explanation hint: `remove()` delegates to `poll`, whereas `remove(Object)` searches for a matching element via the iterator. Their mutation capabilities must be evaluated separately.

### Exercise 2: bulk insertion when only two slots remain

Suppose a bounded queue is currently empty with a capacity of 2. You call `addAll` with three non-null elements.

Predict the exception thrown and the resulting data state under `AbstractQueue`'s default implementation. If business requirements demand all-or-nothing batch insertion, what boundary must you design instead of assuming the skeletal class will roll back?

Do not "fix" this by silently dropping the final element and returning success.

### Exercise 3: fix a recursive size loop

Suppose a subclass stores its data in a `records` list. `map.size()` uses the inherited default, while `entrySet().size()` calls `map.size()`.

Explain why this call chain never terminates. Which method needs to query `records.size()` directly? Why does merely renaming a helper method not resolve the circular dependency?

Explanation hint: at least one primitive operation must read the actual backing state rather than having two layers delegate back and forth to each other.

### Exercise 4: a read-only map mutated through an entry

Suppose a class does not override `put`, and its `entrySet()` returns `Collections.unmodifiableSet` wrapping a set of mutable `SimpleEntry` instances.

If a caller obtains an entry from the iterator and calls `setValue`, is the unmodifiable set wrapper enough to prevent the value change? Contrast this with how `FrozenMap` in this article obtains its entry-set from a map wrapped with `Collections.unmodifiableMap`.

Explanation hint: you must protect the entry elements themselves, not just set membership.

### Exercise 5: null values and key existence checks

Suppose a map contains the mapping `b → null`. A newly written `put` implementation decides: "if `get(b)` equals `null`, append a new entry."

Why can that logic violate the unique-key invariant? How should key existence actually be checked? If `null` values were forbidden instead of permitted, across which entry points would that policy need to be enforced?

Explanation hint: a missing value (`null`) and a missing key are two distinct concepts whenever a map permits `null` values.

### Questions to answer before publishing a subclass

1. Which operations are the primitives, and where do they read actual backing data?
2. Which inherited methods call those primitive operations?
3. Are there any circular call chains across views?
4. Are null handling, ordering, and failure-indicating return values consistent?
5. Which mutation paths do the iterator and entries expose?
6. Are views live-connected to backing data or detached copies, and under what contract?
7. Are the performance costs of the default methods acceptable for the chosen representation?
8. Are concurrency guarantees and optional operations accurately documented?

Using `AbstractQueue` and `AbstractMap` effectively means understanding their call graphs and upholding their underlying primitive contracts. When the foundation is consistent, the skeletal class eliminates a great deal of boilerplate; when the foundation is flawed, bugs can surface in inherited methods that the subclass never explicitly wrote.
