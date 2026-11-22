# CopyOnWriteArraySet and Iterator Snapshot Semantics Under Writes in Java

## 1. The Problem: Reading a Set While Another Thread Adds or Removes Elements

A Java application may maintain a set of active listeners, subscribers, policies, or a group of configuration values. One thread needs to **iterate over all elements**, while another thread may **register a new element or remove** an existing one.

If you use a `HashSet` and modify it concurrently without synchronization, the program is not thread-safe. If you iterate over a regular `HashSet`/`ArrayList` and a structural modification occurs after the iterator is created, the iterator **may** throw `ConcurrentModificationException` via its fail-fast mechanism. That is not a synchronization tool and not a reliable way to detect all races.

Java provides `java.util.concurrent.CopyOnWriteArraySet<E>` for **read/iteration-heavy, write-rare** scenarios, where callers accept that a given traversal sees a **snapshot of the element set at the time the iterator was created**, rather than the latest changes.

Idea:

```text
Time t0: Current Set = [A, B, C]
                       |
               reader creates iterator I
                       |
                       v
          I holds a reference to snapshot [A, B, C]

Time t1: writer add(D)
             Current Set = [A, B, C, D]
             I still iterates [A, B, C]

Time t2: writer remove(B)
             Current Set = [A, C, D]
             I still iterates [A, B, C]

Time t3: reader creates iterator J
             J iterates     [A, C, D]
```

**Key point:** the iterator created at t0 is not a "live query result" that updates itself at t1 and t2. It is a **snapshot iterator**.

This lesson belongs to **Concurrent Collections** in **general Java concurrency**, using Java 17+ APIs with no framework dependencies.

## 2. What Is CopyOnWriteArraySet?

`CopyOnWriteArraySet<E>` is a `Set` implementation backed by a `CopyOnWriteArrayList`.

Key characteristics:

1. **Contains no two elements that are equal according to `equals()`.** If you add an element equal to an existing one, `add` returns `false`.
2. **Thread-safe** for public collection operations when multiple threads add, remove, read, or iterate according to the class contract.
3. Write operations that modify the set of elements generally must create a **new backing array** (copy-on-write), rather than mutating the backing array that older iterators are referencing.
4. An iterator holds a structural snapshot of the element set **at the time the iterator was created**. Subsequent writes do not change the list of elements that an older iterator will traverse.
5. The iterator does not support `remove()`, `set()`, or `add()` like some other iterator/list iterator types; attempting to call a mutating operation through the iterator may throw `UnsupportedOperationException`.
6. `CopyOnWriteArraySet` **allows a `null` element**, unlike `ConcurrentHashMap.newKeySet()`.
7. It does not provide comparator-based sorting. Elements are traversed in the order they are stored in the backing list — typically reflecting insertion order — **not lexicographical or hash order**.
8. Because it must locate elements via linear comparison, `contains`, duplicate checks, and many Set operations have cost proportional to the number of elements; do not treat it as a hash set with `O(1)` lookup.

Understanding the name properly:

- **Copy:** write operations need to copy the backing array when content actually changes.
- **On write:** read operations and creating an iterator typically do not need to copy the entire array.
- **ArraySet:** Set semantics are maintained over an array/list-like structure, not a hash table.

This does not mean every `add` call necessarily creates a new array: for example, adding an element that **already exists** does not need to create a copy containing identical data. The core idea is that **when the set's contents change, the backing array is replaced rather than mutating the old array referenced by existing iterators**.

## 3. Safe Publication Mechanism of the Backing Array

A conceptual view:

```text
Reader I ----> backing array v1: [A, B]

Writer add(C):
  creates new array v2: [A, B, C]
  publishes v2 as the current backing array

Reader I ----> v1: [A, B]           (unchanged)
Reader J ----> v2: [A, B, C]        (created after update)
```

In the underlying `CopyOnWriteArrayList`, the current array is published via appropriate synchronization/visibility mechanisms; writes are coordinated so structural changes are not lost. An iterator captures a reference to the **current array at initialization time** and holds that reference until the iterator is no longer used.

Consequences:

- Readers can traverse the snapshot array without holding a monitor lock for the entire loop.
- Writers can modify the current collection without mutating a reader's snapshot array.
- Old iterators **do not need to restart** and **do not throw `ConcurrentModificationException` simply because the Set was modified**.
- Once a writer publishes a new array, iterators **created afterward** can observe the new set according to the collection's contract.
- Old arrays may remain retained in memory as long as old iterators still hold references to them.

This is not a "copy per reader" mechanism. A new iterator typically just **captures a reference to the current array**, so creating an iterator and traversing it is fast when writes are infrequent. The copy cost primarily occurs on **writes that change the structure**.

## 4. Example 1: Snapshot Created Before Writes

Create `CopyOnWriteSnapshotBasicsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArraySet;

public class CopyOnWriteSnapshotBasicsDemo {
    static List<String> collect(Iterator<String> iterator) {
        List<String> values = new ArrayList<>();
        iterator.forEachRemaining(values::add);
        return values;
    }

    public static void main(String[] args) {
        CopyOnWriteArraySet<String> set =
                new CopyOnWriteArraySet<>(
                        List.of("A", "B", "C"));

        Iterator<String> oldIterator = set.iterator();

        set.add("D");
        set.remove("B");
        set.add("E");

        System.out.println("old snapshot="
                + collect(oldIterator));
        System.out.println("current="
                + new ArrayList<>(set));
        System.out.println("new snapshot="
                + collect(set.iterator()));
    }
}
```

Compile and run on **JDK 17+**:

```bash
javac CopyOnWriteSnapshotBasicsDemo.java
java CopyOnWriteSnapshotBasicsDemo
```

Output:

```text
old snapshot=[A, B, C]
current=[A, C, D, E]
new snapshot=[A, C, D, E]
```

At the moment the first `set.iterator()` was called, the set contained A, B, C. Afterward:

- `add("D")` published a set containing D.
- `remove("B")` removed B from the current set.
- `add("E")` added E.
- However, `oldIterator` still holds the snapshot of the old set, so it **still returns B**, and **does not return D or E**.
- A new iterator created after the modifications traverses the current set.

**A common misconception:** calling `oldIterator.next()` **for the first time after a writer has written** does not mean it will read the current Set. The snapshot is fixed when **`iterator()`** is called, not when `next()` is called.

## 5. Example 2: With an Actual Writer Thread

A single-threaded example can demonstrate the contract, but to understand concurrency properly, create the iterator **before another thread updates the set**, then use `Thread.join()` to know when the writer has finished.

Create `ConcurrentSnapshotDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArraySet;
import java.util.concurrent.CountDownLatch;

public class ConcurrentSnapshotDemo {
    static List<String> readAll(Iterator<String> iterator) {
        List<String> result = new ArrayList<>();
        iterator.forEachRemaining(result::add);
        return result;
    }

    public static void main(String[] args) throws InterruptedException {
        CopyOnWriteArraySet<String> set =
                new CopyOnWriteArraySet<>(
                        List.of("alpha", "beta"));

        Iterator<String> beforeWrite = set.iterator();
        CountDownLatch start = new CountDownLatch(1);

        Thread writer = new Thread(() -> {
            try {
                start.await();
                set.add("gamma");
                set.remove("alpha");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "writer");

        writer.start();
        start.countDown();
        writer.join();

        System.out.println("before write="
                + readAll(beforeWrite));
        System.out.println("after write="
                + readAll(set.iterator()));
    }
}
```

```bash
javac ConcurrentSnapshotDemo.java
java ConcurrentSnapshotDemo
```

Output when there are no unexpected interrupts:

```text
before write=[alpha, beta]
after write=[beta, gamma]
```

Key takeaways:

- Main creates `beforeWrite` before the writer begins `add/remove`.
- The writer mutates the collection; main waits on `join()` and then observes the current set.
- The old iterator still returns the elements from its captured snapshot.
- The two traversals are two **intentional versions**, not a random result depending on scheduling.

If you omit `writer.join()` and create a new iterator concurrently with the updates, the new iterator may see the version before, between, or after the sequence of writes, depending on creation timing. **Each iterator remains consistent with a single version of the backing array**, but you must not expect it to always be the latest version while multiple writers continue operating.

## 6. How Does a Snapshot Iterator Differ from a Fail-Fast Iterator?

Three easily confused behavior groups:

| Collection/Iterator Type | When the collection is modified after iterator creation | What to keep in mind |
| --- | --- | --- |
| Regular `HashSet`, `ArrayList` | Iterator is usually fail-fast and **may** throw `ConcurrentModificationException` | Fail-fast is best-effort; it does not make the collection thread-safe |
| `CopyOnWriteArraySet` | Iterator traverses a **fixed snapshot**; unaffected by subsequent writes | May see removed elements; will not see newly added elements |
| `ConcurrentHashMap.newKeySet()` | Iterator is **weakly consistent**; may see some concurrent changes | Not an immutable point-in-time snapshot |
| `Collections.synchronizedSet(...)` | Requires **external synchronization** during iteration per API docs | Does not automatically provide lock-free snapshot iterators |

**Do not use `ConcurrentModificationException` for control flow.** A fail-fast iterator detects modifications on a best-effort basis; the absence of an exception does not prove concurrent read/write code is safe.

### Snapshot vs weakly consistent

The snapshot iterator of `CopyOnWriteArraySet` has a well-defined set of elements at **iterator creation time**. If a writer adds X after that point, the old snapshot does not contain X.

Weakly consistent iterators, such as those of some other concurrent collections, may reflect **some** changes during traversal. This is useful for workloads with many writers, but it does not guarantee "the exact set of elements at the moment the iterator was initialized."

Choose semantics based on the caller's needs:

- Need **each processing pass to have a fixed list of objects** → snapshot iterator.
- Need to process a large amount of data with frequent writes, where iteration does not need to reflect a global instant → appropriate concurrent key set / collection.
- Need a true snapshot across multiple related structures → may require a dedicated synchronization/freezing protocol; not just picking any iterator.

## 7. Old Iterators Do Not Allow `remove()`

Unlike some regular collection iterators, `CopyOnWriteArraySet`'s iterator **does not support modifying the collection through the iterator**. If you want to remove an element, call the method on the **Set**, not `iterator.remove()`.

Create `SnapshotIteratorRemoveDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArraySet;

public class SnapshotIteratorRemoveDemo {
    public static void main(String[] args) {
        CopyOnWriteArraySet<String> set =
                new CopyOnWriteArraySet<>(List.of("one", "two"));

        Iterator<String> iterator = set.iterator();
        System.out.println("first=" + iterator.next());

        try {
            iterator.remove();
        } catch (UnsupportedOperationException e) {
            System.out.println("iterator.remove unsupported=true");
        }

        System.out.println("after iterator.remove="
                + new ArrayList<>(set));

        set.remove("one");
        System.out.println("after set.remove="
                + new ArrayList<>(set));
    }
}
```

```bash
javac SnapshotIteratorRemoveDemo.java
java SnapshotIteratorRemoveDemo
```

Output:

```text
first=one
iterator.remove unsupported=true
after iterator.remove=[one, two]
after set.remove=[two]
```

`iterator.remove()` throws `UnsupportedOperationException`. Meanwhile, `set.remove("one")` is a valid operation that may create a new backing array. The old iterator is unaffected by this removal through the Set.

When you need to filter many elements, you can use a collection helper like `removeIf` or a strategy that replaces the whole snapshot. However, consider the copy/write cost and how the application wants to coordinate updates, rather than calling `remove` one element at a time on a large Set with many writers.

## 8. Snapshots Preserve Set Membership Structure, Not Deep Copies of Objects

This is a very important boundary.

`CopyOnWriteArraySet` snapshots **the array of element references**. It does not automatically clone each object. If an element is a mutable object, both the old iterator and the current collection can still hold **the same reference** to that object.

```text
snapshot array v1: [ reference -> Item(id=1, name="old") ]
current  array v2: [ reference -> Item(id=1, name="old"), Item2 ]

If Item.name is modified to "new":
snapshot v1 still contains Item(id=1), but observing Item.name may return "new".
```

Therefore:

- The snapshot protects **Set membership at a point in time**.
- The snapshot **does not protect mutable state inside each member**.
- If an object is mutated from another thread without synchronization, there can still be a **data race/visibility problem** on that object's fields.
- To get a truly immutable view, prefer immutable elements or appropriate deep copies, published safely.

### Example 3: Mutable element changing inside an old snapshot

Create `MutableElementSnapshotDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArraySet;

public class MutableElementSnapshotDemo {
    static final class Item {
        final int id;
        String name;

        Item(int id, String name) {
            this.id = id;
            this.name = name;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Item item && id == item.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }

        @Override
        public String toString() {
            return id + ":" + name;
        }
    }

    static List<String> describe(Iterator<Item> iterator) {
        List<String> result = new ArrayList<>();
        iterator.forEachRemaining(
                item -> result.add(item.toString()));
        return result;
    }

    public static void main(String[] args) {
        Item first = new Item(1, "old");
        CopyOnWriteArraySet<Item> set =
                new CopyOnWriteArraySet<>();
        set.add(first);

        Iterator<Item> snapshot = set.iterator();

        first.name = "new";
        set.add(new Item(2, "second"));

        System.out.println("old snapshot=" + describe(snapshot));
        System.out.println("current=" + describe(set.iterator()));
    }
}
```

```bash
javac MutableElementSnapshotDemo.java
java MutableElementSnapshotDemo
```

Output:

```text
old snapshot=[1:new]
current=[1:new, 2:second]
```

This example mutates the `name` field **sequentially in a single thread**, so there is no visibility race. It demonstrates that the old snapshot still holds the same `first` object, so `name` can change from `old` to `new` even while membership in the snapshot remains unchanged.

In a multithreaded system, if you genuinely need concurrent updates to `name`, you must use `volatile`, locks, immutable replacement, or an appropriate synchronization mechanism. **Do not rely on the Set's copy-on-write behavior to guarantee thread safety for all fields of `Item`.**

## 9. Uniqueness by equals(), Not by Hash Bucket

`CopyOnWriteArraySet` adheres to `Set` semantics: elements that are duplicates according to `equals()` are not added a second time. Unlike `HashSet`, it does not rely on a hash table for lookups; instead, it checks elements in the backing array/list.

As a result:

- `new String("Java")` and an already stored `String` with the same content are treated as duplicate elements.
- Element order is not `hashCode()` order.
- `contains(element)` has linear cost in the number of elements in the general case.
- If `equals()` is expensive, `add`/`contains` calls can also be expensive.
- If `equals()` is unstable because mutable fields are modified, Set uniqueness logic may no longer behave as expected.

### Example 4: Duplicates, null, and iteration order

Create `CopyOnWriteSetEqualityDemo.java`:

```java
import java.util.ArrayList;
import java.util.concurrent.CopyOnWriteArraySet;

public class CopyOnWriteSetEqualityDemo {
    public static void main(String[] args) {
        CopyOnWriteArraySet<String> set =
                new CopyOnWriteArraySet<>();

        boolean first = set.add("apple");
        boolean duplicate = set.add(new String("apple"));
        boolean nullFirst = set.add(null);
        boolean nullAgain = set.add(null);

        System.out.println("first=" + first);
        System.out.println("duplicate=" + duplicate);
        System.out.println("null first=" + nullFirst);
        System.out.println("null again=" + nullAgain);
        System.out.println("elements=" + new ArrayList<>(set));
    }
}
```

```bash
javac CopyOnWriteSetEqualityDemo.java
java CopyOnWriteSetEqualityDemo
```

Output:

```text
first=true
duplicate=false
null first=true
null again=false
elements=[apple, null]
```

The two `String` instances are distinct objects but equal according to `equals()`, so the second `add` returns `false`. `null` is allowed **once** in `CopyOnWriteArraySet`. This differs from `ConcurrentHashMap.newKeySet()`, because its underlying Map does not permit null keys.

Do not assume that every concurrent Set allows `null`. Always check **the contract of the chosen implementation**, especially when switching from `CopyOnWriteArraySet` to another concurrent set.

## 10. Element Mutation Affecting equals()

A subtler bug than the deep-snapshot issue: when an element `Item` uses a **mutable field in `equals()`**, modifying that field can change its equality relationship with other elements.

For example, suppose a class bases `equals()` on `name`, you put `Item("A")` into the Set, and then mutate `name` to `"B"`:

- `contains(new Item("A"))` may change from `true` to `false`.
- `contains(new Item("B"))` may change from `false` to `true`.
- If another `Item("B")` already existed, the Set can end up containing two objects that are now logically **equal** even though each was validly added at different times.
- If another thread mutates that field without synchronization, equality checks also suffer from a data race.

**Recommendation:** use elements with **stable** identity/equality while they are in the Set. With a `record` containing only `String`, primitives, or immutable value objects, keeping `equals()` semantics stable is usually straightforward.

Be cautious with a `record` containing a mutable `List` or array: a `record` does not automatically guarantee **deep immutability** of the entire object graph. If an element's contents change, the snapshot is still only a snapshot of **references**.

## 11. Practical Example: Listener / Event Subscriber List

A small set of listeners with rare registrations/unregistrations that is iterated very frequently is a classic fit for copy-on-write.

Suppose a system receives an event and, on each receipt, needs to invoke the listeners **belonging to that dispatch pass's snapshot**. If listener A removes B and adds C during dispatch, a clear semantic choice is:

- The current pass still processes A and B according to the old snapshot.
- C only appears in the **next dispatch pass**.
- Removing B from the Set **does not cancel callbacks already in the snapshot**.

### Example 5: Modifying the Set during a traversal loop

Create `ListenerSnapshotDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArraySet;

public class ListenerSnapshotDemo {
    public static void main(String[] args) {
        CopyOnWriteArraySet<String> listeners =
                new CopyOnWriteArraySet<>(List.of("A", "B"));

        List<String> firstRound = new ArrayList<>();

        for (String listener : listeners) {
            firstRound.add(listener);
            if (listener.equals("A")) {
                listeners.remove("B");
                listeners.add("C");
            }
        }

        List<String> secondRound = new ArrayList<>();
        for (String listener : listeners) {
            secondRound.add(listener);
        }

        System.out.println("first round=" + firstRound);
        System.out.println("second round=" + secondRound);
    }
}
```

```bash
javac ListenerSnapshotDemo.java
java ListenerSnapshotDemo
```

Output:

```text
first round=[A, B]
second round=[A, C]
```

The first `for-each` loop creates an iterator once at the start. Even though code inside the loop removes B and adds C, this loop's iterator still traverses the `[A, B]` snapshot. The second loop takes a new snapshot and therefore traverses `[A, C]`.

This is a major advantage when listeners are allowed to register or unregister themselves inside callbacks and you do not want to hold a lock while invoking subscribers.

### Limitations of the listener pattern

- `unsubscribe(B)` **does not guarantee B will no longer be called in an already-started dispatch pass**.
- If you must guarantee "once removed, no callback for B is running," you need an additional protocol to manage **in-flight callbacks** (state/cancel/acknowledgment). A copy-on-write Set alone does not provide that guarantee.
- If a callback throws an exception, you must decide whether to continue with the remaining listeners; the Set does not handle exceptions for you.
- A slow callback slows down the dispatch loop; the Set only solves how **membership is traversed and updated**, not callback scheduling.
- If a listener holds resources outside the JVM (sockets, files), removing it from the Set does not automatically close those resources.

## 12. Snapshot Iterators and the "Latest" View

An iterator provides **the set of elements that existed at creation time**. It is not an API to fetch "the latest set regardless of what writers are doing."

There are two distinct cases:

**A. Writer has finished and coordination is explicit:** if thread A performs updates and thread B waits for A via `join()`/latch before calling `set.iterator()`, B obtains a snapshot of the current set **after that sequence of updates** (assuming no competing third writer).

**B. Reader creates an iterator concurrently with a writer:** the ordering between capturing the array reference and publishing the new array determines whether the iterator sees the earlier or later version. Do not predict this based on `Thread.sleep(...)` or thread names.

**C. Multiple continuous writers:** an iterator created at a point in time may see an intermediate version between separate `add`/`remove` operations. For example, updating A and then B does not become a single atomic transaction just because `CopyOnWriteArraySet` is used.

Advice: if multiple changes must appear **simultaneously according to a business invariant**, build a complete new immutable snapshot and publish it via an `AtomicReference`, or apply an appropriate locking/transaction protocol. Consecutive `set.add` / `set.remove` calls remain **multiple** separate changes.

## 13. Time and Memory Complexity

Approximate cost table for a set with `n` elements:

| Operation | Typical Cost | Reason |
| --- | --- | --- |
| `iterator()` | `O(1)` to obtain snapshot reference | Does not copy the whole array just to create an iterator |
| Full traversal of `n` elements | `O(n)` | Walks each element in the snapshot |
| `contains(x)` | `O(n)` | Linear search using equality |
| `add(x)` when absent | `O(n)` | Checks for duplicates and creates/copies a new backing array |
| `add(x)` when present | `O(n)` worst-case for search | No need to insert/copy to install a new element |
| `remove(x)` when present | `O(n)` | Finds the element then creates a new array without it |
| `size()` | Usually `O(1)` | Based on the current array length |
| Each live iterator | Holds a reference to a snapshot array | May delay GC of old arrays |

This table describes the general shape, not a hard guarantee for every nanosecond or every JDK implementation. Bulk operations and internal optimizations may have different costs.

**On memory:** if the Set holds `n` references, a membership change typically requires allocating an `O(n)` backing array. If many old iterators remain alive, multiple array versions may coexist on the heap. Element objects may be referenced by multiple array versions, and if an element has been removed from the current Set while still present in an old snapshot, it **remains alive** until no snapshot/iterator references it.

Do not confuse "copying the reference array" with "cloning all element objects": array allocation cost is significant, but it does not deep-copy every object.

## 14. Cumulative Copy Cost Under Frequent Writes

Suppose `n = 100_000` elements and tens of thousands of elements are added/removed every second. With copy-on-write:

- Each membership change can copy an array of tens or hundreds of thousands of references.
- Many temporary array versions increase allocation rate and GC pressure.
- Writers must coordinate internally, so writes do not all run independently in parallel.
- Under continuous writes, lock-free reads may not offset the writer overhead.

This is why `CopyOnWriteArraySet` is usually well-suited when:

- The element count is small or moderate.
- **Reads/traversals are frequent, writes are very rare**.
- Each traversal wants stable membership.
- Simplicity of iteration is preferred and eventual visibility per snapshot pass is acceptable.

And it is usually **unsuitable** when:

- Membership is updated continuously at high frequency.
- The Set is very large with many writers.
- The problem requires minimal latency for each `add`/`remove`.
- The workload needs a "live view" reflecting new elements immediately within the current traversal.

Do not conclude from the word "concurrent" alone that this collection fits every multithreaded scenario.

## 15. Comparison with ConcurrentHashMap.newKeySet()

Another option is:

```java
Set<String> names = ConcurrentHashMap.newKeySet();
```

This is an illustrative snippet; it requires importing `java.util.Set` and `java.util.concurrent.ConcurrentHashMap`.

### Key differences

| Criterion | `CopyOnWriteArraySet` | `ConcurrentHashMap.newKeySet()` |
| --- | --- | --- |
| Underlying structure | Copy-on-write array | Concurrent hash table |
| `contains` lookup | Linear in element count | Typically near constant-time, depending on hash distribution |
| Frequent add/remove | Expensive array copies, not ideal for large n | Usually better suited for write-heavy workloads |
| Iterator | **Snapshot**, membership fixed at creation time | **Weakly consistent**, may reflect some changes |
| Iteration order | Backing list / insertion order in typical usage | No ordering guarantee |
| `null` | **Allows** one null element | **Does not allow** null |
| Repeated read/traversal cost | No long-held reader lock; stable snapshot | Iterator avoids full-copy overhead, but has different semantics |
| Typical fit | Small listener/config sets, read-heavy write-rare | Large key sets with high-volume concurrent reads/writes |

Do not say `ConcurrentHashMap.newKeySet()` is "always faster." For a very small Set, hashing and traversing a different structure may offer no clear benefit; and if a fixed snapshot is strictly required, using a weakly consistent iterator may force you to build a separate snapshot mechanism anyway.

It is not just a performance question, but a matter of **iteration semantics**: do you need to see the set as it was at the start, or a set that can reflect concurrent updates?

## 16. Comparison with Collections.synchronizedSet()

You can create:

```java
Set<String> set =
        Collections.synchronizedSet(new HashSet<>());
```

This is an illustrative snippet; it requires importing `java.util.*`. The wrapper provides synchronization for many Set operations; however, **the iterator does not automatically have snapshot semantics**. The Java documentation requires manual synchronization when iterating over a synchronized collection:

```java
synchronized (set) {
    for (String value : set) {
        use(value);
    }
}
```

This is an illustrative snippet where `use` is an application method. Holding `set`'s monitor throughout the loop is only correct if **all modification paths go through the same wrapper and the same synchronization protocol**. If a caller keeps the iterator and exits the `synchronized` block early, or if code bypasses the wrapper to mutate the underlying `HashSet`, the guarantee is broken.

Operational differences:

- `synchronizedSet` can force writers to **wait until a long traversal finishes** because the reader holds the monitor.
- `CopyOnWriteArraySet` lets writers replace the backing array while readers continue traversing the old snapshot, without locking for the whole traversal.
- `synchronizedSet` avoids copying the whole array on every add/remove, but has locking overhead.
- Either can be right; choose based on read/write frequency, traversal duration, snapshot requirements, and contention levels.

If `use(value)` performs slow I/O inside the `synchronized` block, writers may wait a long time. That is one reason listener patterns often prefer snapshot iterators.

## 17. Comparison with ConcurrentSkipListSet

`ConcurrentSkipListSet` provides a concurrent sorted/navigable set, useful when the application needs:

- Traversing elements **by comparator / natural ordering**.
- Finding nearest elements (`lower`, `higher`, `floor`, `ceiling`).
- Working with ordered range views.

It uses a concurrent skip list structure, not a copy-on-write backing array. Its iterator is **weakly consistent**, unlike `CopyOnWriteArraySet`'s snapshot iterator; it also generally does not allow `null` elements.

If the problem needs "a listener list in registration order" with rare changes, `CopyOnWriteArraySet` can be convenient. If the problem needs "all keys in ascending order and range operations" under concurrent updates, `ConcurrentSkipListSet` is usually a better fit.

Do not pick `CopyOnWriteArraySet` expecting `sort()` or a comparator to automatically apply to the Set — it is not a `SortedSet`.

## 18. Rules for `add`, `remove`, and Return Values

`CopyOnWriteArraySet` still follows standard `Set` contracts:

- `add(e)` returns `true` if the Set changed because the element was not already present.
- `add(e)` returns `false` when an equal element is already present.
- `remove(e)` returns `true` if a matching element existed and was removed.
- `remove(e)` returns `false` if no matching element was found.
- `contains(e)` checks membership at a point in time of the collection.
- `size()` returns the current set size at the time of the call.

You can use `add`'s return value to avoid performing a side effect on the losing caller **in a registration race**:

```java
if (listeners.add(listener)) {
    reportNewRegistration(listener);
}
```

This is an illustrative snippet. Understand the limit: `add` and reporting are **two separate operations**. If another thread calls `remove`/`add` for the same listener in between, or if reporting fails, you cannot infer an exactly-once side effect in all situations.

If business logic requires exactly-once registration outside the JVM, define IDs, transactions/idempotency, and an appropriate protocol; copy-on-write only manages membership in an in-JVM Set.

## 19. Old Snapshot Arrays Can Retain Removed Objects

An often-overlooked production issue is **retained memory**. Suppose:

1. A Set contains 10,000 listener objects.
2. Thread A creates an iterator and holds onto it during a very long-waiting task.
3. Thread B removes 9,000 listeners.
4. The current Set only has 1,000 listeners, but A's iterator still holds **the snapshot array with 10,000 old references**.
5. Removed listeners may **not be garbage-collected yet** if they are still held by the old snapshot and have no other references.

Therefore:

- Avoid holding iterators/snapshots longer than necessary.
- Avoid letting an iterator escape its intended scope/lifecycle when it references large objects.
- Do not assume `set.remove(e)` means object `e` is immediately eligible for collection.
- If many iterators live concurrently alongside large writes, allocation and retained heap can grow.

This is a tradeoff of snapshot semantics. It is not an unbounded memory leak in every case; once old iterators are no longer referenced, old arrays and removed elements can be GC'd subject to normal reachability rules.

## 20. Combining CopyOnWriteArraySet with Immutable Elements

A simple and reliable pattern:

```java
record Subscriber(String id, String channel) {}
CopyOnWriteArraySet<Subscriber> subscribers =
        new CopyOnWriteArraySet<>();
```

This is an illustrative snippet. `Subscriber` holds two immutable `String`s and its record components are final, so each element cannot be mutated in place.

When you want to change the channel:

```java
Subscriber oldValue = new Subscriber("u-1", "news");
Subscriber newValue = new Subscriber("u-1", "alerts");

subscribers.remove(oldValue);
subscribers.add(newValue);
```

This illustrative snippet is **not a transaction**: between `remove` and `add`, an observer might temporarily see neither old nor new, while an older snapshot still holds `old`. If membership must transition **atomically across multiple steps**, do not expect two Set calls to behave as one operation; replace an entire immutable aggregate via an `AtomicReference` or use another coordination mechanism.

**Equality trap:** `record Subscriber(id, channel)` compares both `id` and `channel`. If business logic treats **`id` as the unique identifier**, two records with the same `id` but different `channel` are not equal, so the Set can contain both. Choose an appropriate identity model: custom `equals`/`hashCode` based only on `id`, a `Map` keyed by `id`, or a value aggregate keyed by `id`.

This is a semantic bug, not a race condition: a collection can only enforce uniqueness according to the **`equals()` defined by its elements**, not according to external business rules.

## 21. Thread Safety and the Java Memory Model

`CopyOnWriteArraySet` is part of `java.util.concurrent` and uses safe publication for its backing array. Actions in a thread prior to placing an object into a concurrent collection have appropriate visibility guarantees to another thread after retrieving/observing that object via the collection, per the memory consistency properties of concurrent collections.

In practice:

- One thread constructs an element and calls `set.add(item)`.
- Another thread creates a new iterator and retrieves that `item` from the snapshot.
- The reading thread has visibility guarantees for state initialized **before the element was published**.

**Do not overgeneralize this into a deep-immutability guarantee**:

- If a writer continues modifying `item.name` after adding it, separate synchronization is required for that mutable state.
- If an element contains a mutable `List`, copying the Set's backing array does not copy the internal list structure.
- If a method checks `set.contains(x)` and then reads `x`'s mutable state without synchronization, the thread-safe Set does not protect those field reads.
- An old iterator still sees members of the old snapshot even after the current Set has removed them.
- Separate `add`/`remove` calls do not form a multi-element transaction.

Prefer immutable elements and design clear ownership of membership changes.

## 22. Is a "Snapshot" a Snapshot of the Whole Application?

No. It is only a structural snapshot of **that specific CopyOnWriteArraySet**.

For example, suppose a service has:

```text
CopyOnWriteArraySet<Listener> listeners
ConcurrentHashMap<String, Config> configs
AtomicInteger version
```

A `listeners.iterator()` pass does not create a consistent point-in-time snapshot of `configs` or `version`. If business logic requires "listeners and configs from the same version," design a higher-level snapshot unit, such as an immutable record containing both and published via a single reference.

Do not conflate:

- **Snapshot iterator:** the set of element references fixed when the iterator is formed.
- **Snapshot element:** all fields/object graphs inside an element are immutable per version.
- **Snapshot transaction:** multiple data structures read/updated at a single consistent point.

These are three distinct concepts. `CopyOnWriteArraySet` directly solves **the first**, while the latter two require additional data design and protocols.

## 23. Common Mistakes

### 23.1. Thinking an old iterator sees every new `add`

Wrong. The snapshot is fixed when `iterator()` is created. To get the latest membership, create a new iterator at the appropriate time.

### 23.2. Thinking `remove(e)` stops an old iterator from returning `e`

Wrong. An old iterator can still return `e` if `e` was in the snapshot at creation time, even if the current Set has already removed `e`.

### 23.3. Calling `iterator.remove()`

Not supported; throws `UnsupportedOperationException`. Remove through the Set or choose another structure if iterator-based removal is required.

### 23.4. Expecting the iterator to provide a deep copy

Wrong. It holds element references. Mutable elements can still change their contents inside an old snapshot.

### 23.5. Using CopyOnWriteArraySet for millions of elements with continuous writes

This can cause massive array copy, allocation, and GC overhead. Consider a concurrent hash-backed set, partitioned structures, or another design.

### 23.6. Thinking `contains` is O(1) like HashSet

`CopyOnWriteArraySet` uses a backing list and checks equality linearly. With a large Set and many lookups, the cost can be substantial.

### 23.7. Using keys/elements with mutable equality

If an element mutates fields used in `equals`, uniqueness and membership may no longer reflect the business design.

### 23.8. Using `Collections.synchronizedSet` without synchronizing the entire iterator loop

The synchronized wrapper does not make iteration a snapshot. By contract, you must hold the appropriate monitor for the entire duration of the traversal.

### 23.9. Using a weakly consistent iterator and assuming it is a snapshot

`ConcurrentHashMap.newKeySet()` has an iterator with different semantics. It may reflect some modifications during traversal; it does not guarantee a fixed element set from creation time.

### 23.10. Thinking unregistering a listener immediately stops all callbacks

No. A dispatch pass that already captured a snapshot may continue invoking a removed listener. You need an in-flight management protocol if that is required.

### 23.11. Keeping iterators alive for too long

Old snapshots retain backing arrays and references, which can keep old objects alive longer than intended.

### 23.12. Thinking multiple add/remove calls form a transaction

Each operation may be a separate atomic change. A reader creating a snapshot between two calls can observe an intermediate state.

### 23.13. Using `null` without checking contracts across Set implementations

`CopyOnWriteArraySet` allows `null`, but not every concurrent set does; for example, `ConcurrentHashMap.newKeySet()` forbids `null`.

### 23.14. Ignoring callback exceptions or timeouts

A stable iterator does not mean callbacks inside the loop will always succeed. If event handling fails, you must decide whether to continue with subsequent listeners, stop dispatching, retry, or record the outcome.

### 23.15. Benchmarking with a single run

Performance depends on Set size, read/write ratio, number of writers, element distribution, and iterator lifetime. JVM benchmarks require warm-up and multiple runs; do not draw conclusions from uncontrolled microbenchmarks.

## 24. When Should You Use CopyOnWriteArraySet?

**A great fit when:**

- The listener/subscriber or observer list is relatively small.
- Read/traversal loops happen very frequently.
- Registrations/unregistrations happen rarely.
- Each dispatch pass wants a **fixed list of targets from start to finish**.
- You do not want to hold a shared lock across potentially long callbacks.
- Elements are immutable or have separate synchronization for mutable state.

**Consider alternatives when:**

- Many writers modify the Set continuously or the element count is very large.
- Very fast `contains` lookups are needed on a set with many keys.
- You want the iterator to reflect some ongoing changes rather than an old snapshot.
- You need natural/comparator sorting and range queries.
- You want to update multiple elements in a single transaction.
- You need direct removal via the iterator.

A practical way to decide: determine the **read/write ratio**, size `n`, traversal duration, snapshot membership requirements, acceptable write latency, and memory budget for old snapshots. Choose a collection based on **semantics and workload**, not just because it has "Concurrent" in its name.

## 25. Self-Check Questions

**Q1.** A Set contains A, B. You create iterator I. Then you add C and remove A. What will I iterate over?

**Answer:** I still iterates over the initial snapshot A, B. A new iterator created after the updates will see B, C, assuming no other writers.

**Q2.** Does calling `I.next()` for the first time after the changes cause I to capture a new snapshot?

**Answer:** No. The snapshot is fixed when `set.iterator()` is called, not when `next()` is called.

**Q3.** Why does the iterator not throw `ConcurrentModificationException` simply because a writer calls add/remove?

**Answer:** It traverses a snapshot array that is not modified by the writer; the writer swaps in a new backing array. There is no structural modification to the iterator's snapshot array.

**Q4.** Can you call `iterator.remove()` to delete the element just visited?

**Answer:** No. `CopyOnWriteArraySet`'s iterator does not support `remove` and will throw `UnsupportedOperationException`.

**Q5.** If a mutable element's `name` is modified after the iterator is created, does the snapshot preserve the old `name`?

**Answer:** No. The snapshot holds element references, not deep copies of objects. If modified concurrently, synchronization is also needed for that field.

**Q6.** Does `CopyOnWriteArraySet` allow `null`?

**Answer:** Yes. The Set still allows at most one `null` element per `Set` semantics.

**Q7.** Is `CopyOnWriteArraySet` a hash set with O(1) lookup?

**Answer:** No. It is backed by `CopyOnWriteArrayList`; `contains` and equality checks generally require a linear scan.

**Q8.** Why can `add`/`remove` cost be high for a large Set?

**Answer:** When membership changes, the writer typically has to allocate/copy a new backing array of size `O(n)`, in addition to the element search cost.

**Q9.** Is `ConcurrentHashMap.newKeySet()`'s iterator the same as `CopyOnWriteArraySet`'s snapshot iterator?

**Answer:** No. It is weakly consistent; it may reflect some concurrent modifications and does not capture a fixed membership at creation time.

**Q10.** A listener is removed while a dispatch pass is iterating a snapshot. Is it guaranteed not to be called in that pass?

**Answer:** No. If the listener was already in the snapshot, the dispatch pass may still invoke it. Guaranteeing cancellation of in-flight callbacks requires an additional protocol.

**Q11.** Why does `synchronizedSet` require manual synchronization when iterating?

**Answer:** The iterator does not automatically hold the monitor for the entire traversal; to prevent concurrent structural modifications through the same wrapper, the caller must lock according to the collection's contract.

**Q12.** Does a snapshot make two operations `add(A)` and `remove(B)` a transaction?

**Answer:** No. An iterator created between the two calls can observe an intermediate state.

**Q13.** Why can a long-lived iterator cause the heap to retain removed elements?

**Answer:** It still holds the old snapshot array containing references to those elements; GC can only reclaim them once no live references remain.

**Q14.** Does creating an iterator need to copy the entire Set to achieve a snapshot?

**Answer:** No. `CopyOnWriteArraySet` typically captures a reference to the current backing array; the copy cost is primarily on writes that change membership.

**Q15.** If two listeners have the same `id` but different `channel`, and a record's `equals` checks both fields, does the Set guarantee only one listener per `id`?

**Answer:** No. Uniqueness is based on the element's `equals()`, not on `id` alone. Equality/keys must be designed to match business requirements.

## 26. Summary

**`CopyOnWriteArraySet` is suited for relatively small sets that are read/iterated very frequently and modified rarely.** When a writer adds or removes an element, the collection may create a new backing array; existing iterators continue traversing **the old snapshot array**, do not reflect new changes, and do not suffer `ConcurrentModificationException` due to writes on the Set.

Rules to remember:

1. **The snapshot is taken at `iterator()`**, not at the first `next()` call.
2. Subsequent writes **do not add/remove elements in an old iterator**.
3. `iterator.remove()` is not supported; modify the collection via the Set's API.
4. Snapshots only hold **member references**, **do not deep-copy elements**, and do not automatically make mutable fields thread-safe.
5. `add`/`remove` calls that change membership typically cost `O(n)` due to array copying; `contains` also scans linearly.
6. Old iterators can retain arrays and removed objects longer than expected; avoid holding snapshots for too long.
7. Compared to `ConcurrentHashMap.newKeySet()` with its weakly consistent iterator, `CopyOnWriteArraySet` yields **a fixed membership list for the entire traversal**.
8. When business requirements call for in-flight cancellation, multi-element transactions, or snapshots across multiple structures, an application-level protocol is required.

A fitting example is a **listener registry**: very frequent dispatch passes and very rare registrations/unregistrations. Once you understand when the snapshot is captured, the limits with mutable elements, and the cost of each write, you can use `CopyOnWriteArraySet` as the specialized tool it is in **Java Concurrent Collections**, rather than treating it as a "best-for-everything" concurrent Set.
