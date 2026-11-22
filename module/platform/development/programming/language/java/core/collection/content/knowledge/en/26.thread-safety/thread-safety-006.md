# Weakly Consistent Iterators and Snapshot Iterators

## 1. Why Do Thread-Safe Collections Still Have Different Iteration Semantics?

Suppose a program is iterating over a list of notification subscribers while another party registers a new subscriber. Should the current notification round send to the list determined at the start, or can it include the newly registered subscriber? If someone unsubscribes mid-round, is a pending call to that subscriber canceled immediately?

Another scenario is iterating over a status table that receives frequent updates. The program might accept a near-current report for monitoring, whereas an end-of-period reconciliation requires data from a single consistent version.

Those scenarios require different **guarantees about iteration results**. Choosing a thread-safe collection only answers part of the question. You also need to know which version an iterator observes, whether it reflects changes made during iteration, and whether the collection can be modified through the iterator.

The two main mechanisms in this lesson are:

- **Weakly consistent iterator:** allows iteration concurrently with other operations according to the class contract, without pinning the entire traversal to a single version.
- **Snapshot iterator:** traverses the structural state captured at the time the iterator was created. Subsequent structural changes do not alter the set of references that the iterator is traversing.

"Snapshot" here must be understood at the right depth. A fixed array of references does not automatically make the state of every element object immutable.

After this lesson, you should be able to distinguish three questions: **can it be iterated safely**, **which version is it observing**, and **is the result consistent enough for the application's requirements**. They are related, but they do not substitute for one another.

The programs use Java 17 or later. Prerequisite knowledge includes `Iterator`, `List`, `Map`, object references, and `for-each` loops. The two-thread experiment section explains the coordination points inline.

## 2. Mental Model: A Live Collection and a Single Traversal

### 2.1. Collections, Views, and Iterators Have Different Lifecycles

A collection is an object that holds data. A **view** is a way to access related data, such as `map.keySet()`. An iterator is an object that holds the progress of **a single traversal**.

The following snippet creates two different traversals over the same list:

```java
Iterator<String> first = names.iterator();
names.add("Lan");
Iterator<String> second = names.iterator();
```

This is an illustrative snippet assuming `names` is a `CopyOnWriteArrayList<String>`. `first` and `second` are created at different points in time. They do not necessarily traverse the same version. `first` is not "refreshed" just because the program calls `iterator()` to create `second`.

An enhanced `for (String name : names)` loop obtains one iterator at the start of the loop. It does not obtain a new iterator for each element. Therefore, the moment the loop starts matters for snapshot iterators.

With `ConcurrentHashMap`, `keySet` is a view backed by the map, and the view's iterator is weakly consistent. Obtaining a view does not mean taking an independent snapshot copy of all keys. [ConcurrentHashMap — keySet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#keySet())

### 2.2. Three Axes to Examine Separately

| Axis | Example Question | Do Not Infer Automatically |
| --- | --- | --- |
| Change visibility policy | Will additions after iterator creation appear in this traversal? | Not throwing an exception means always seeing new data |
| Iteration order | By index, key order, FIFO, or no guaranteed order? | Weakly consistent means completely arbitrary order |
| Modification via iterator | Are `remove`, `set`, `add` supported? | Safe iteration means the iterator is read-only |

A map with sorted keys can still use a weakly consistent iterator. A list ordered by index can still use a snapshot iterator. The two properties "order" and "observed version" are not the same.

### 2.3. Quick Comparison with Fail-Fast Iterators

Iterators of standard structures like `HashMap` use **fail-fast modification detection** when they detect structural changes outside the protocol they allow. This mechanism only makes a best-effort attempt to detect bugs; the presence or absence of `ConcurrentModificationException` must not be used to prove thread safety. [HashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)

This exception can occur even when a single thread iterates and modifies improperly; the word "Concurrent" in the exception name does not mean there must be at least two threads.

Conversely, weakly consistent iterators and snapshot iterators are designed with different policies to handle concurrent or interleaved modifications. The fact that they do not throw `ConcurrentModificationException` due to source structural changes does not mean every usage pattern in a program is correct.

The term "fail-safe iterator" often appears in informal articles, but it should not be used as a blanket contract that lumps every non-fail-fast iterator into the same category. Use the actual policy names and guarantees stated in each class's documentation.

## 3. Snapshot Iterators: Pinning Structure at Creation Time

### 3.1. How `CopyOnWriteArrayList` Works

`CopyOnWriteArrayList` uses a copy-on-write mechanism. An iterator holds a reference to the array version at the time it was created. Updating the list creates and installs a new array version for the current list; old iterators continue to see the old version.

This class's iterator does not reflect additions, removals, or replacements on the list after creation time. It does not support `remove`; `ListIterator` also does not support `set` or `add`. Those operations throw `UnsupportedOperationException`. [CopyOnWriteArrayList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)

You can visualize this with two versions:

```text
t0: list -> [An, Binh, Chi]
             ^
             old iterator keeps this version

t1: list -> [An, Binh-moi, Dung]

old iterator: An, Binh, Chi
new iterator: An, Binh-moi, Dung
```

There is no "re-sync" step for the old iterator to jump to the new array. This gives the traversal a stable structural scope, though the results can be stale relative to the current list.

### 3.2. Complete Program: Old Versions and Old References

Save as **`SnapshotIteratorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.ListIterator;
import java.util.concurrent.CopyOnWriteArrayList;

public class SnapshotIteratorDemo {
    public static void main(String[] args) {
        CopyOnWriteArrayList<String> names =
                new CopyOnWriteArrayList<>(List.of("An", "Binh", "Chi"));
        Iterator<String> old = names.iterator();

        names.set(1, "Binh-moi");
        names.remove("Chi");
        names.add("Dung");

        List<String> oldNames = drain(old);
        require(oldNames.equals(List.of("An", "Binh", "Chi")), "old snapshot");
        System.out.println("old iterator = " + oldNames);
        System.out.println("new iterator = " + drain(names.iterator()));
        System.out.println("current list = " + names);
        System.out.println("iterator.remove = " + unsupported(old::remove));

        ListIterator<String> editableCursor = names.listIterator();
        editableCursor.next();
        System.out.println("listIterator.set = "
                + unsupported(() -> editableCursor.set("X")));
        System.out.println("listIterator.add = "
                + unsupported(() -> editableCursor.add("Y")));

        Item apple = new Item("apple", 1);
        Item banana = new Item("banana", 2);
        CopyOnWriteArrayList<Item> items =
                new CopyOnWriteArrayList<>(List.of(apple, banana));
        Iterator<Item> itemSnapshot = items.iterator();

        items.set(0, new Item("new-apple", 7));
        items.remove(banana);
        apple.quantity = 99;

        List<Item> oldItems = drain(itemSnapshot);
        require(oldItems.get(0) == apple, "element reference was copied deeply");
        require(oldItems.get(1) == banana, "removed reference was lost");
        require(oldItems.get(0).quantity == 99, "field change was not visible");
        System.out.println("old item references = " + oldItems);
        System.out.println("current item references = " + items);
        System.out.println("same original apple = " + (oldItems.get(0) == apple));
    }

    private static <T> List<T> drain(Iterator<T> iterator) {
        List<T> result = new ArrayList<>();
        iterator.forEachRemaining(result::add);
        return result;
    }

    private static String unsupported(Runnable action) {
        try {
            action.run();
            throw new AssertionError("expected UnsupportedOperationException");
        } catch (UnsupportedOperationException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static final class Item {
        private final String name;
        private int quantity;

        private Item(String name, int quantity) {
            this.name = name;
            this.quantity = quantity;
        }

        @Override
        public String toString() {
            return name + ":" + quantity;
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all SnapshotIteratorDemo.java
java SnapshotIteratorDemo
```

Stdout on a successful run:

```text
old iterator = [An, Binh, Chi]
new iterator = [An, Binh-moi, Dung]
current list = [An, Binh-moi, Dung]
iterator.remove = UnsupportedOperationException
listIterator.set = UnsupportedOperationException
listIterator.add = UnsupportedOperationException
old item references = [apple:99, banana:2]
current item references = [new-apple:7]
same original apple = true
```

The program contains two separate experiments.

**Names experiment:** the iterator is created before the list is modified. The program then replaces `Binh`, removes `Chi`, and adds `Dung`. The old iterator still traverses the three references from the old version. The new iterator and the current list object see the new version.

The `remove`, `set`, and `add` calls attempted through the iterators only demonstrate that these operations are unsupported. They do not modify the list. To update the list, call methods on `CopyOnWriteArrayList`, understanding that any ongoing traversal still follows its own snapshot.

**Items experiment:** the iterator holds references to the original `apple` and `banana`. The current list replaces `apple` with a new object and removes `banana`, yet both old references remain in the snapshot. When `apple.quantity = 99` is modified, the old iterator reads that same object and prints `apple:99`.

The expression `oldItems.get(0) == apple` checks object identity, proving that the snapshot did not make a deep copy of `apple`.

### 3.3. A Structural Snapshot Is Not a Deep Snapshot

Separate the following three things:

| What Is Preserved | Example | Automatically Provided by a Snapshot Iterator? |
| --- | --- | --- |
| The set of references and order of the list version | Still contains the `banana` reference removed from the current list | Yes, for `CopyOnWriteArrayList`'s iterator |
| Internal state inside each element | `apple.quantity` always stays `1` | No |
| Consistent relationships across multiple objects outside the list | Item totals and configuration belonging to the same business version | No |

When elements are immutable `String`s, preserving references makes the example easy to observe: the string itself does not change its contents. With objects that have mutable fields, the story is completely different.

The program above uses **a single thread** when modifying and reading `quantity`. It demonstrates reference sharing, not that plain field reads/writes across multiple threads are properly synchronized.

If multiple threads modify element state, a separate protocol is needed: immutable objects, `volatile`/atomic types for the relevant state, or locks covering a sufficient scope. Placing an object into a concurrent collection does not automatically synchronize all future mutations on that object.

Concurrent collections provide data publication guarantees according to their memory consistency contracts; this does not replace a protocol for subsequent modifications. [java.util.concurrent — Memory Consistency Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html#MemoryVisibility)

### 3.4. Cost and Lifecycle of a Snapshot

Read-heavy, write-rare workloads are the typical fit for copy-on-write. An actual modification to the list may require copying the backing array; if writes are frequent or the list is large, allocation and copying costs must be measured under realistic workloads.

Creating an iterator does not mean deep-copying every element. Because the iterator holds onto the old array version, it follows that a long-lived iterator also keeps the references from that version alive. Removing an element from the current list does not force old iterators to release their references immediately.

Only when there are no longer any reachable references to the old version can the garbage collector reclaim it according to JVM rules. Do not hold onto iterators unnecessarily in caches or long-waiting tasks.

`CopyOnWriteArraySet` also uses an array-snapshot-based iterator and does not support removal via the iterator. It suits typically small sets where reads greatly outnumber updates; it is not a default solution for every concurrent data set. [CopyOnWriteArraySet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArraySet.html)

## 4. Weakly Consistent Iterators: Allowing Updates Without Pinning a Global Version

### 4.1. What You Can Rely On

The `java.util.concurrent` documentation describes many concurrent iterators as weakly consistent: they can proceed concurrently with other operations, do not use `ConcurrentModificationException` to report source modifications, and may—but are not required to—reflect changes made after the iterator was created. Always read the specific class's contract. [java.util.concurrent — Concurrent Collections](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html)

In `ConcurrentHashMap`, iterator results reflect the state of the map at points in time at or after the iterator was created; there is no guarantee that the entire traversal is a single snapshot. Each iterator is designed for use by one thread at a time. [ConcurrentHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

A useful way to read this is: **you are allowed to traverse a live, active structure, but you must not upgrade the guarantee on your own into a single-version report**.

This does not mean the iterator is allowed to return arbitrary data, ignore all ordering rules, or return elements that never belonged to the source. Each class's contract still constrains the results. Stable elements that are not added, removed, or replaced during traversal are good anchors for designing checks; for modified elements, check exactly what the API promises.

### 4.2. A Single Traversal Result Can Span Multiple Phases

Suppose a traversal has already read row A. Before it reads row B, another task updates the data. The later part of the traversal may be affected by the later phase, while the part already returned is not automatically recomputed.

Therefore, a running sum accumulated from an iterator is not necessarily the sum of the entire system at any single point in time. Even when each individual `Integer` value is immutable, **the points in time at which the mappings were observed** can still differ.

Similarly, when key `session-7` is removed or has its value replaced, the fact that the iterator saw it does not prove that the session is still registered by the time you finish processing it. A traversal result is an observation used to decide the next piece of work, not a lock holding the resource.

"Weakly consistent" also does not mean "an iterator that has reached the end will keep updating until it sees every new change." An iterator is a single traversal with progress; it is not an event stream or a subscription for all changes.

### 4.3. Ordering Still Depends on the Collection Type

| Collection / View | Iterator Policy | Ordering Point to Remember |
| --- | --- | --- |
| `ConcurrentHashMap.keySet/values/entrySet` | Weakly consistent | Do not rely on hash table key order |
| `ConcurrentLinkedQueue` | Weakly consistent | The queue has FIFO ordering per its contract |
| `ConcurrentSkipListMap` and its views | Weakly consistent | Keys remain in natural or comparator order |
| `CopyOnWriteArrayList` | Snapshot | In index order of the captured version |

`ConcurrentLinkedQueue` specifies that its iterator can operate concurrently with other operations; element and ordering guarantees must be read from the queue documentation. `ConcurrentSkipListMap` specifies a weakly consistent iterator even though the map itself keeps keys sorted. [ConcurrentLinkedQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html), [ConcurrentSkipListMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html)

This table only lists specific classes. Do not assume every class prefixed with `Concurrent` uses the same iterator algorithm, or that every structure in `java.util.concurrent` provides a snapshot.

## 5. Two-Thread Experiment with a Weakly Consistent Iterator

### 5.1. Designing a Test Around What Is Guaranteed

A common flawed test does the following: create an iterator, insert a new key, and assert that the iterator must see that key. That assertion imposes a stronger guarantee than the weakly consistent contract.

The following program splits keys into two groups:

- `base-a`, `base-b` are added before the iterator is created and are not modified or removed during the entire traversal.
- `changing-0`, `changing-1`, `changing-2` are changed in two phases after the iterator is created.

The test only checks that the stable keys are definitely found, with no unknown keys or duplicate keys under this update schedule. It **does not assert that a fixed subset of the changing keys must appear**.

Only one task owns the iterator. The other task only modifies the map. `CountDownLatch` instances establish the ordering of phases; `Thread.sleep` is not used to guess when the other thread has run.

### 5.2. Complete Program

Save as **`WeakIteratorDemo.java`**:

```java
import java.util.HashSet;
import java.util.Iterator;
import java.util.Set;
import java.util.TreeSet;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class WeakIteratorDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();
        map.put("base-a", 1);
        map.put("base-b", 2);
        map.put("changing-0", 0);

        CountDownLatch created = new CountDownLatch(1);
        CountDownLatch phaseOneDone = new CountDownLatch(1);
        CountDownLatch firstVisited = new CountDownLatch(1);
        CountDownLatch phaseTwoDone = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<Set<String>> traversal = pool.submit(() -> {
                Iterator<String> iterator = map.keySet().iterator();
                created.countDown();
                await(phaseOneDone);

                Set<String> seen = new HashSet<>();
                require(iterator.hasNext(), "stable entries must be available");
                require(seen.add(iterator.next()), "repeated first key");
                firstVisited.countDown();
                await(phaseTwoDone);

                while (iterator.hasNext()) {
                    require(seen.add(iterator.next()), "repeated key");
                }
                return seen;
            });

            Future<?> updates = pool.submit(() -> {
                await(created);
                map.remove("changing-0");
                map.put("changing-1", 1);
                phaseOneDone.countDown();

                await(firstVisited);
                map.remove("changing-1");
                map.put("changing-2", 2);
                phaseTwoDone.countDown();
                return null;
            });

            Set<String> seen = traversal.get(10, TimeUnit.SECONDS);
            updates.get(10, TimeUnit.SECONDS);
            Set<String> stable = Set.of("base-a", "base-b");
            Set<String> universe = Set.of(
                    "base-a", "base-b",
                    "changing-0", "changing-1", "changing-2");

            require(seen.containsAll(stable), "stable entry was missed");
            require(universe.containsAll(seen), "unknown key");
            System.out.println("stable keys found = " + seen.containsAll(stable));
            System.out.println("observed keys are known = "
                    + universe.containsAll(seen));
            System.out.println("repeated keys = false");
            System.out.println("changing-key subset = not asserted");
            System.out.println("final keys = " + new TreeSet<>(map.keySet()));
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }

    private static void await(CountDownLatch latch) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("latch timed out");
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Run commands:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all WeakIteratorDemo.java
java WeakIteratorDemo
```

Stdout on a successful run:

```text
stable keys found = true
observed keys are known = true
repeated keys = false
changing-key subset = not asserted
final keys = [base-a, base-b, changing-2]
```

Coordination order explained:

1. The traversal task creates the iterator and opens the `created` gate.
2. The update task replaces `changing-0` with `changing-1`, then opens `phaseOneDone`.
3. The traversal task retrieves one element, opens `firstVisited`, and waits.
4. The update task replaces `changing-1` with `changing-2`, opening `phaseTwoDone`.
5. The traversal task finishes the remaining elements. The main thread retrieves the results and checks the chosen conditions.

In this schedule, one element is returned before the second update phase, and the rest after that phase. The traversal task's `seen` set is its own private data and is not modified by the update task.

The line `changing-key subset = not asserted` **is not an observed result set**. It explicitly states that the test does not enforce a fixed result for the changing group. You can print `new TreeSet<>(seen)` yourself to inspect it, but that output is not a fixed stdout guaranteed by the general contract.

The `final keys` line is read after both tasks complete. At that point no writer is modifying the map, so printing the final keys with `TreeSet` gives a clear order. This is the final state, not a claim that the earlier iterator traversed that exact final set.

The timeouts ensure the program fails fast instead of hanging if a task cannot make progress. Any assertion failure inside a task is propagated to the main thread via `Future.get`. The test does not catch errors and continue printing as if it succeeded.

### 5.3. What Must Not Be Inferred from a Single Run

If your machine prints all of the new keys, that does not turn "may reflect changes" into "must reflect all changes." If another run sees only a subset of the changes, that does not mean the iterator is broken either.

Do not assert a specific key sequence based on hash distribution or internal bucket order observed on a particular JDK build. That may simply be an artifact of the current implementation or execution schedule. `ConcurrentHashMap`'s unspecified order is not an order to memorize.

The test synchronizes the schedule only at the points needed to place updates in the middle of the traversal. It does not lock the entire map to eliminate updates, because doing so would stop testing the scenario we need to distinguish.

## 6. Direct Comparison of the Two Policies

| Question | Weakly Consistent Iterator | Copy-on-Write Snapshot Iterator |
| --- | --- | --- |
| Traverses concurrently with source updates? | Yes, per class contract | Yes; old traversal keeps the captured version |
| Pins the entire traversal to the creation-time version? | Not guaranteed as such | Yes, for the structure/references of the captured version |
| Can changes after creation appear? | May appear; not all changes are required to appear | Does not alter the structure the old iterator is traversing |
| Throws `ConcurrentModificationException` for source changes allowed by the policy? | No | No |
| Deep-copies every element? | No such guarantee | No |
| Can modify through the iterator? | Depends on the specific class and operation | `remove` is unsupported; `ListIterator` also does not support `set`/`add` |
| Is returned data guaranteed to be current when processing finishes? | No general guarantee | No; the version may already be stale |
| Turns multi-step work into a transaction? | No | No |

The two policies solve different needs. A listener traversal may want a fixed recipient set for a single dispatch round. A status dashboard may prefer to keep operating during updates rather than halting all writers to take a global snapshot.

However, an audit that must prove all numbers belong to the same version cannot simply say "the iterator didn't throw an exception." The application's consistency requirements determine whether that result is acceptable.

### 6.1. Do Not Confuse a Single-Entry Snapshot with a Whole-Iterator Snapshot

`ConcurrentSkipListMap` documentation describes returned `Map.Entry` instances as snapshots of mappings at the time they were produced, and they do not support `Entry.setValue`. At the same time, the map's iterator remains weakly consistent. [ConcurrentSkipListMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html)

These two facts do not contradict each other: entry A may be created at time t1, and entry B at time t2. Each key-value pair being preserved does not prove that the whole set of pairs belongs to the same point in time.

Whenever you hear "snapshot," always ask: a snapshot of **what**, at **what time**, and at **what depth**? For an entry holding a reference to a mutable object, the internal state of that object is still a separate question.

### 6.2. Modifying via an Iterator Is a Separate Part of the Contract

The `Iterator` interface defines `remove` as an optional operation. By default it may be unsupported; modification rules during traversal depend on the implementing class's policy. [Iterator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#remove())

`ConcurrentHashMap` supports removal through its view iterators, whereas the copy-on-write iterator tested above does not. Thus, you cannot use a "non-fail-fast" label to guess modification support.

If the requirement is **to remove only when the current value still equals the observed value**, express that condition using the appropriate conditional operation. The following non-standalone snippet assumes `states` is a `ConcurrentHashMap<String, String>`:

```java
for (Map.Entry<String, String> entry : states.entrySet()) {
    if ("STALE".equals(entry.getValue())) {
        states.remove(entry.getKey(), entry.getValue());
    }
}
```

`ConcurrentMap.remove(key, expectedValue)` checks the value and removes the entry in a single atomic operation. It checks according to value equality rules, not a version number. If the value changes and then changes back to the old value, a version-based requirement needs version data in the design. [ConcurrentMap — conditional remove](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html#remove(java.lang.Object,java.lang.Object))

Nor should you infer from a single allowed removal that "the entire cleanup pass is a transaction." Other updates can still occur between processing different entries.

## 7. Application: A Notification Round with a Fixed Listener Set

### 7.1. Desired Rule

Suppose an event dispatch round takes the listener list at the start. While invoking listener A, A unregisters B and adds C.

With a snapshot policy, a reasonable choice is:

- The current round continues calling A then B because that is the captured list.
- The next round calls A then C.
- There is no need to hold a collection lock for the entire duration of listener code execution just to protect the iterator.

This describes **the rule of the example**, not a requirement suitable for every system. If unregistration must immediately prevent any unstarted invocation, a plain snapshot alone is not enough.

### 7.2. Complete Program

Save as **`ListenerSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class ListenerSnapshotDemo {
    public static void main(String[] args) {
        CopyOnWriteArrayList<Runnable> listeners = new CopyOnWriteArrayList<>();
        List<String> calls = new ArrayList<>();

        Runnable listenerB = () -> calls.add("B");
        Runnable listenerC = () -> calls.add("C");
        Runnable listenerA = () -> {
            calls.add("A");
            listeners.remove(listenerB);
            listeners.addIfAbsent(listenerC);
        };

        listeners.add(listenerA);
        listeners.add(listenerB);

        dispatch(listeners);
        require(calls.equals(List.of("A", "B")), "first round");
        System.out.println("round 1 = " + calls);
        calls.clear();

        dispatch(listeners);
        require(calls.equals(List.of("A", "C")), "second round");
        System.out.println("round 2 = " + calls);
        System.out.println("registered listeners = " + listeners.size());
    }

    private static void dispatch(CopyOnWriteArrayList<Runnable> listeners) {
        for (Runnable listener : listeners) {
            listener.run();
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Run commands:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all ListenerSnapshotDemo.java
java ListenerSnapshotDemo
```

Stdout on a successful run:

```text
round 1 = [A, B]
round 2 = [A, C]
registered listeners = 2
```

The `for-each` loop creates an iterator before calling A. When A modifies the list, the first round's iterator still contains B. C is added to the current list so the next round sees it.

`addIfAbsent(listenerC)` keeps the example from re-registering the same C object every time A runs. This is a specific list-management operation; the snapshot policy itself does not prevent duplicates via other `add` paths.

The example intentionally uses **a single dispatch thread**. `calls` is an `ArrayList` read and written only by this thread. If multiple threads call `dispatch` concurrently, you must separately consider thread safety of the listeners, log data, and any state the listeners access.

### 7.3. Additional Requirements Not Solved by Snapshots Alone

A list snapshot does not make callback code thread-safe. Two concurrent dispatch rounds can still invoke the same listener on two threads.

It also does not guarantee that every listener will be invoked successfully. In the program above, if one `listener.run()` throws an exception without proper handling, the loop stops there. A stable set of references does not mean processing every element will complete.

If the unregistration rule is stricter, you may need registration state, invocation-time permission checks, or coordination with running tasks. You must specify when "unregistration takes effect" and how already-started calls are handled. Switching collections does not define those rules.

Similarly, a listener removed from the current list can still be referenced by an active round's snapshot. Unregistering and having no remaining references are two different events.

## 8. When You Need a Truly Consistent Snapshot

### 8.1. Copying After a Weak Traversal Does Not Make the Source a Single Version

The following snippet creates a new map:

```java
Map<String, Integer> copy = new HashMap<>(concurrentMap);
```

Suppose `concurrentMap` is a `ConcurrentHashMap<String, Integer>` being updated. `copy` has its own structure after creation, but the data entering it was still collected while the source could change.

Therefore, separate two properties:

- **Post-copy independence:** changing a mapping in the new copy does not change the source mapping.
- **Collection-time consistency:** did all collected mappings belong to the same source version?

The first property does not prove the second. Sorting the copy with a `TreeMap` only changes presentation order; it does not fix the data-collection history. Wrapping the copy in an unmodifiable view does not upgrade the consistency of the source either.

If you pause or coordinate all writers and then take a copy, the argument changes: the source does not switch versions during collection. What needs to be proven lies in the pause/coordination mechanism, not in the name of the copy constructor.

### 8.2. Taking a Copy Under a Lock Respected by Every Access Path

Non-standalone illustrative example:

```java
Map<String, Integer> shared =
        Collections.synchronizedMap(new HashMap<>());

Map<String, Integer> snapshot;
synchronized (shared) {
    snapshot = new HashMap<>(shared);
}
```

All accesses to the underlying map must go through the same wrapper object, and multi-step work must hold the right monitor for the entire operation. The copy happens inside the synchronized block, so writers going through the wrapper on other threads must wait. With immutable `String` keys and `Integer` values in this example, the copy does not share mutable element fields.

The synchronized map documentation requires holding the lock on the returned map throughout iteration over its collection views; do not lock only `keySet` instead of the map. [Collections — synchronizedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map))

If the source is a `ConcurrentHashMap`, arbitrarily writing `synchronized (concurrentMap)` around the copy does not make threads that only call `put` wait on that external monitor. A lock only coordinates access paths that actually obey the locking protocol. A private wrapper class can prevent the map from escaping and expose update/snapshot methods using the same lock.

When a deep snapshot is needed, element state must be copied while that state is also protected. Copying individual objects at disjoint times does not create consistency for relationships between them.

### 8.3. Publishing Immutable State by Version

Another approach is to build a complete immutable state and publish a reference to the new version through an appropriate synchronization mechanism. Readers hold one version for the duration of their work.

This approach is only convincing if the related data is genuinely grouped within the version and no mutable references leak around it. If two lists are published independently, each having a snapshot iterator still does not prove they belong to the same business version.

No single option is mandatory for every application. Start from the requirement: approximate monitoring while active, sending to a fixed set, or reconciling data from the same point in time. Then choose a mechanism whose guarantees meet that requirement.

## 9. Do Not Generalize an Iterator Contract to Every Access Pattern

### 9.1. An Index Loop Is Not a Snapshot Iterator

The snippet below does not create a snapshot iterator, even when `names` is a `CopyOnWriteArrayList<String>`:

```java
for (int i = 0; i < names.size(); i++) {
    System.out.println(names.get(i));
}
```

Each `size` and `get` is a separate call on the current list. Between checking `i < names.size()` and calling `get(i)`, another thread can remove an element, making the index invalid. Even without an index error, two `get` calls can observe two different versions.

A `for-each` loop or an explicitly created iterator has a different policy because it tracks progress on the source as specified by the iterator contract. Do not replace a snapshot loop with an index loop and assume the same level of guarantee.

### 9.2. An Unmodifiable View Does Not Mean a Snapshot

Wrapping a live list with `Collections.unmodifiableList` only blocks certain mutation paths through that view. It does not detach the data from the underlying list, does not create a lock against writers, and does not upgrade the underlying iterator to a snapshot iterator. [Collections — unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List))

Similarly, a `subList` is a view with its own contract. For `CopyOnWriteArrayList.subList`, the documentation states that view semantics become undefined if the backing list is modified through any path other than that view. Do not infer "the original list has a snapshot iterator" to mean "every operation on every view unconditionally preserves the old version." [CopyOnWriteArrayList — subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html#subList(int,int))

Always identify the actual object in use: the original list, a view, an already-created iterator, or an independent copy.

### 9.3. `Spliterator` and Streams Require Reading the Exact Source-Binding Point

Streams typically obtain data via a `Spliterator`. Two common characteristics are:

- `CONCURRENT`: the source allows concurrent modification according to its policy.
- `IMMUTABLE`: the source the spliterator is traversing cannot be structurally modified during that traversal.

`CONCURRENT` does not mean multiple threads can freely call the same spliterator instance concurrently, nor does it promise a global snapshot. `IMMUTABLE` describes the source/version the spliterator traverses; it does not prove that the internal state of each element object is immutable. [Spliterator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html)

For example, `CopyOnWriteArrayList`'s spliterator reports `IMMUTABLE` and holds a snapshot from when the spliterator was created, even though the list object still allows subsequent additions and removals. The spliterators of `ConcurrentHashMap` views report `CONCURRENT`. These are two different ways of managing source changes.

Do not assume every `stream()` pins data at the moment the method is called, or that every stream waits until the terminal operation to bind to the source. The binding point depends on the source and how the spliterator/stream is created; some sources are late-binding, while others capture an early snapshot.

Functions in the processing pipeline must still obey non-interference requirements and manage state properly. Allowing a concurrent source to be updated does not make arbitrary side effects in lambdas safe. [java.util.stream — Non-interference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html#NonInterference)

If the task only needs a sequential traversal, master `Iterator` first. Do not switch to a parallel stream to "fix" a consistency requirement that the source does not satisfy.

### 9.4. Do Not Share a Single Traversal Cursor Just Because the Collection Is Safe

An iterator object holds progress state, such as the current position and the last returned element. Being able to let **one thread iterate while another thread modifies the collection** does not mean **two threads using the same iterator** is safe.

The standard approach is for each task to have its own iterator, or to delegate element splitting to a mechanism designed for that purpose. If a cursor must be shared, it needs its own synchronization contract/protocol; do not use the collection's thread safety as substitute evidence.

The same applies to collected data: a local `ArrayList` written by only one task as in the experiment cannot be turned into a shared result container without rethinking the coordination mechanism.

## 10. Choosing a Mechanism Based on Observation Requirements

| Requirement | Potentially Suitable Choice | Limitations to Accept or Address |
| --- | --- | --- |
| Traverse a status table under continuous updates, accepting observations from different phases | Weakly consistent iterator on an appropriate collection | Do not use the result as a global reconciliation snapshot |
| Pin the recipient set for one round, with infrequent registration changes | Copy-on-write snapshot iterator | Unregistration does not automatically remove elements from a running snapshot |
| Read-heavy, rarely changing data needing list order | `CopyOnWriteArrayList` | Copying cost on updates and retaining old versions |
| Small set, read-heavy, no duplicates | `CopyOnWriteArraySet` | Evaluate lookup/update cost at realistic sizes |
| Report requiring all numbers from the same version | Copy under a shared lock or publish immutable state | All write paths and element state must follow the same protocol |
| Only want to forbid callers from modifying through a view | Unmodifiable view | No new snapshot or synchronization just because the view is read-only |

When choosing, determine how much staleness the application can tolerate. A stable snapshot that is too stale may not fit current control requirements. A fresher traversal that mixes versions may not fit reconciliation.

Performance also depends on the actual workload: element count, read/write ratio, number of concurrent active traversals, per-element processing time, and element state cost. Do not extrapolate from a small loop in an example to conclude that one collection is always fastest.

## 11. Practice: Identifying the Exact Scope of Guarantees

### Exercise 1 — Removing a Recipient Mid-Round

A copy-on-write list contains A, B, C. An iterator is created; after returning A, another party removes B and adds D. Elements are immutable strings.

**Question:** Must the old iterator reflect the removal and addition? Does creating a new iterator after the update mean the same thing as continuing the old iterator?

**Check:** The old iterator continues with the captured A, B, C version; after A has been returned, the remaining elements are B and C. A new iterator gets the post-update version. The two traversals have different snapshot times.

### Exercise 2 — Snapshot with Mutable Elements

A snapshot iterator holds `Order` references with a `status` field. After creating the iterator, another thread changes `status`.

**Question:** Can you guarantee the iterator always reads the old status? Can you guarantee every field read is thread-safe?

**Check:** Neither can be guaranteed from the snapshot iterator alone. The snapshot preserves references, not deep fields. You must examine `Order`'s immutability and synchronization mechanism; if there are multi-field invariants, a single `volatile` field alone does not solve the whole problem.

### Exercise 3 — Summing from a Concurrent Map

One thread iterates over values in a `ConcurrentHashMap` to compute a sum. Another thread is moving one unit between two keys using two updates.

**Question:** Is the absence of `ConcurrentModificationException` enough to prove the sum belongs to a single version?

**Check:** No. A weakly consistent iterator supports traversal during updates; it does not turn two edits or the entire summation into a transaction. You need a protocol that preserves invariants and a corresponding read/snapshot mechanism if the sum must reflect a single point in time.

### Exercise 4 — Snapshot Entries, Weak Iterator

A `ConcurrentSkipListMap` returns a first entry and then a second entry. The documentation calls an entry a snapshot of the mapping.

**Question:** Can you take that as proof that both entries belong to the same whole-map version?

**Check:** No. Each entry has its own creation time; a snapshot of a single mapping is not a snapshot of the entire traversal. Sorted key order does not unify observation times either.

### Exercise 5 — A Test Enforcing an Unguaranteed Result

A test creates an iterator on a concurrent map, adds key `late`, and requires every run to see `late`.

**Question:** What is the test verifying incorrectly?

**Check:** It turned a change that *may* be reflected into a change that *must* be reflected. It should test the guarantees actually needed by the algorithm, or switch mechanisms if the application genuinely requires including that key.

### Exercise 6 — The `IMMUTABLE` Flag

A `CopyOnWriteArrayList` spliterator has the `IMMUTABLE` characteristic, yet the program still calls `list.add` successfully.

**Question:** Do those two facts contradict each other?

**Check:** No. The flag describes the source/version that the spliterator is traversing; the current list object can move to a different version. Nor does that flag freeze the fields of every element object.

## 12. Reference Documentation When Switching Collections

The programs and scenarios in this lesson are designed to distinguish guarantees about observed versions. When applying these ideas to another class, read the iterator/spliterator policy and modification rules for that exact class:

- [java.util.concurrent Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html): weak consistency and data publication.
- [CopyOnWriteArrayList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html), [CopyOnWriteArraySet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArraySet.html): snapshot iterators and update limits.
- [ConcurrentHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html), [ConcurrentLinkedQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html), [ConcurrentSkipListMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html): contracts of specific structures.
- [Iterator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html), [Spliterator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html): traversal cursors, optional operations, and source characteristics.
- [Collections Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): views and locking requirements for synchronized wrappers.
