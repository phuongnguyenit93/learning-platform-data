# Locking the Right Object When Traversing Synchronized Wrappers

## 1. A Synchronized Wrapper Does Not Hold the Lock for the Entire Loop

Methods such as `Collections.synchronizedList`, `synchronizedSet`, and `synchronizedMap` create a wrapper with a synchronization mechanism for their supported operations. However, a traversal via an `Iterator`, `Spliterator`, or `Stream` consists of multiple steps and can span beyond a single method call.

Therefore, the question to answer is:

> Which object's monitor must the entire traversal hold in order to coordinate with code that modifies the data?

The answer is not always "the object being iterated over in the for-each loop". When traversing `map.keySet()`, you must lock the wrapped `Map`. When traversing a sub-range such as `headSet` or `subMap` obtained from the root wrapper, you must still use the root lock specified by the contract.

The documentation for synchronized wrappers requires manually locking the right object when traversing and accessing the underlying data through the wrapper. [Java SE 17 — Collections synchronized wrappers](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedCollection(java.util.Collection)).

Model of this lesson:

~~~text
multiple data views
        |
        v
one backing source and one shared locking protocol
        |
        v
hold the right lock for the entire traversal
~~~

This lesson moves from simple `List`/`Set` wrappers to `Map` and sub-range views, and then points out common locking mistakes: locking the `Iterator`, locking a view, locking the underlying data, creating two independent wrappers, or locking an outer read-only wrapper.

## 2. A Monitor Belongs to an Object, Not a Variable Name or `equals`

`synchronized (object)` acquires the monitor associated with the exact object that the expression references. Two distinct objects have different monitors, even if:

- They have the same implementation class.
- They represent equal contents according to `equals`.
- They share the same underlying collection.
- One object is a view created from the other.

Java allows the same thread to re-acquire a monitor it already holds; this is reentrancy. This allows code holding the wrapper lock to call wrapper methods that use the same monitor without blocking itself. [Java Language Specification 17 — Synchronization](https://docs.oracle.com/en/java/specs/jls/se17/html/jls-17.html#jls-17.1).

However, locking a child object does not automatically lock the parent object:

~~~text
synchronized(view)
    holds only the monitor of view

synchronized(root)
    holds only the monitor of root
~~~

A method on `view` may internally use the root lock in its implementation. That does not make `view`'s own monitor the same monitor as the root's, and it does not make a `synchronized(view)` block hold the root lock across the traversal loop.

This is the difference between **the object whose method is being called** and **the object serving as the lock for the access protocol**.

## 3. Lock Selection Table for Common Cases

Assuming the root wrappers are created by the corresponding public factories in `Collections`:

| What is being traversed | Object to lock to coordinate with the wrapper |
| --- | --- |
| A root `synchronizedCollection` | The wrapped `Collection` returned by the factory |
| A root `synchronizedList` or `synchronizedSet` | The root wrapped `List`/`Set` |
| `subList` obtained from `synchronizedList` | The root wrapped `List` sharing the lock, not just the `subList` |
| `keySet`, `values`, `entrySet` of `synchronizedMap` | The root wrapped `Map` |
| `subSet`, `headSet`, `tailSet` of `synchronizedSortedSet` | The root wrapped `SortedSet` |
| A sub-range or view of `synchronizedSortedMap` | The root wrapped `SortedMap` |
| A navigation view of the corresponding navigable wrapper | The root wrapper per its contract |

"Root" here means the object that owns the locking protocol for the group of views in use, which is not always the raw collection passed into the factory.

For example:

~~~java
List<String> list = Collections.synchronizedList(new ArrayList<>());
~~~

The public lock to use for traversal is `list`. You do not need—and should not try—to find an internal `ArrayList` to lock instead.

If an API only hands you a view without providing information about the locking protocol, you cannot infer the root lock simply by looking at the `Collection` interface type. The API design should keep traversal responsibility where the root is known, or expose a snapshot or a managed traversal operation.

## 4. List and Set: Create the Traverser and Use It Within the Same Lock Region

Example with `List`:

~~~java
List<String> list = Collections.synchronizedList(
        new ArrayList<>(List.of("A", "B", "C")));

synchronized (list) {
    Iterator<String> iterator = list.iterator();
    while (iterator.hasNext()) {
        consume(iterator.next());
    }
}
~~~

This snippet illustrates code inside a method, where `consume` is application-defined. The complete program later in this lesson has no missing helper dependencies and includes explicit run commands.

Both points are important:

1. Create the `Iterator` inside the lock region.
2. Hold the lock until you finish using the `Iterator`.

The `synchronizedList` documentation explicitly states this requirement for `Iterator`, `Spliterator`, and `Stream`. [Java SE 17 — Collections.synchronizedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List)).

### 4.1. Locking Only When Creating the Iterator Is Not Enough

The following pattern violates the protocol:

~~~java
Iterator<String> iterator;
synchronized (list) {
    iterator = list.iterator();
}

// Wrong if the source can be modified by other parties during traversal.
while (iterator.hasNext()) {
    consume(iterator.next());
}
~~~

Once execution exits the block, other threads can acquire the same lock to modify the source. An `Iterator` does not automatically hold the `List`'s monitor for its entire lifetime.

### 4.2. Locking Each Step Separately Does Not Preserve a Consistent Traversal

If each `hasNext`/`next` call is placed in a separate lock block, gaps remain in which the source can change between steps or between elements. For a standard `Iterator` of the underlying collection, that does not satisfy the whole-traversal protection pattern required by the wrapper.

Define the boundary of the work: if the task needs a stable view, lock the entire pass or create an appropriate snapshot.

### 4.3. `for-each` Is Still a Traversal

~~~java
synchronized (list) {
    for (String value : list) {
        consume(value);
    }
}
~~~

A shorter syntax does not change the lock object. If `for` uses a sub-view, you must check the lock for that view rather than mechanically locking the variable standing after the colon.

A root synchronized `Set` is handled the same way, differing only in the element and ordering contract of the underlying `Set`. Locking the right object does not give a `HashSet` an order or sort its data.

## 5. Map: Lock the Wrapped Map, Not `keySet`, `values`, or `entrySet`

Consider:

~~~java
Map<String, Integer> map =
        Collections.synchronizedMap(new LinkedHashMap<>());

Set<String> keys = map.keySet();
~~~

The `keys` view is not an independent copy. It shares the underlying `Map`. When traversing, the right lock is `map`:

~~~java
synchronized (map) {
    for (String key : keys) {
        consume(key);
    }
}
~~~

Do not replace this with `synchronized (keys)` and assume that `map.put` calls from another thread will be blocked by that lock. Those calls use the `Map`'s locking protocol, not the separate monitor of the `keySet` object.

The `synchronizedMap` documentation requires locking on the returned `Map` when traversing any of its collection views, including `keySet`, `values`, and `entrySet`. [Java SE 17 — Collections.synchronizedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map)).

### 5.1. You Can Obtain the View Beforehand, but the Traverser Must Be Used Under the Right Lock

Obtaining `map.keySet()` before the lock block, as in the example, is a usage pattern shown in the documentation. When starting an `Iterator` or a `Stream` pass on the view, use a lock region that protects the entire corresponding operation.

Do not pass a live `Iterator` out of the block and return it to a caller to use as if it were already "pre-locked".

### 5.2. Entries Have Their Own Contract

When traversing `entrySet` under the lock, you can read the key and value to build output data. If you want to keep the pairs for longer processing after releasing the lock, create independent entries or data objects during the traversal.

Simply copying with `new ArrayList<>(map.entrySet())` does not automatically clone each entry into an independent pair. Holding the lock during the copy does not change the lifetime contract and relationship of the entries obtained from the view.

The demonstration program formats key–value strings inside the lock region and only prints those strings outside. It does not retain live entries from the source for continued use after the source may have changed.

### 5.3. Locking a View Can Create a False Impression

A single method on `keySet` may still synchronize properly internally because the view shares the root lock with the `Map`. That does not validate holding `synchronized(keys)` around an `Iterator`.

In OpenJDK 17, a wrapper's `keySet`, `values`, and `entrySet` views are created with the same mutex as the `Map` wrapper. This mechanism explains why their methods share the protocol, while the monitor of the view object itself remains a different object. [OpenJDK 17 — Collections.java](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/Collections.java).

## 6. Sub-Ranges Continue to Use the Root Lock

### 6.1. `subList` of `synchronizedList`

~~~java
List<String> list = Collections.synchronizedList(
        new ArrayList<>(List.of("A", "B", "C")));
List<String> tail = list.subList(1, 3);

synchronized (list) {
    for (String value : tail) {
        consume(value);
    }
}
~~~

`tail` is a different view object, but the sub-wrapper's operations share the lock with the root `List`. Therefore, holding `tail`'s monitor does not replace holding `list`'s monitor for the traversal.

OpenJDK source code shows that `subList` on a `synchronizedList` forwards the existing mutex to the sub-wrapper; it does not create a new independent protocol for the same data range.

Beyond locking, `subList` also has a contract regarding structural modifications of the backing `List`. If the parent structure is modified outside the view in a way that invalidates the `subList`, merely acquiring the right lock afterward does not make the view valid again. Locking solves interleaved access; it does not replace structural validity rules.

### 6.2. `subSet`, `headSet`, and `tailSet`

With `SortedSet`:

~~~java
SortedSet<Integer> sorted = Collections.synchronizedSortedSet(
        new TreeSet<>(List.of(1, 2, 3, 4)));
SortedSet<Integer> head = sorted.headSet(4);

synchronized (sorted) {
    for (Integer value : head) {
        consume(value);
    }
}
~~~

Here, `headSet(4)` selects elements strictly less than `4`. The lock object is `sorted`, not `head`. The documentation for synchronized `SortedSet` explicitly states that you must lock the root set even when traversing sub-ranges. [Java SE 17 — Collections.synchronizedSortedSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedSortedSet(java.util.SortedSet)).

With `NavigableSet`, navigation views and range views with inclusive/exclusive parameters must also follow the root lock according to the corresponding wrapper contract. Do not assume that adding boundary parameters creates a new independent lock.

### 6.3. `subMap`, `headMap`, `tailMap`, and Chained Views

With `SortedMap`:

~~~java
SortedMap<String, Integer> root =
        Collections.synchronizedSortedMap(new TreeMap<>());
SortedMap<String, Integer> range = root.subMap("A", "C");

synchronized (root) {
    for (String key : range.keySet()) {
        consume(key);
    }
}
~~~

You must lock `root`, not `range` and not `range.keySet()`.

Views can pass through multiple layers, yet the protocol cannot be inferred from the outermost layer alone. The `synchronizedSortedMap` and `synchronizedNavigableMap` documentation specifies the root `Map` for traversing such sub-range views. [Java SE 17 — Collections.synchronizedSortedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedSortedMap(java.util.SortedMap)).

An accurate way to remember this is to track **who owns the shared lock** from the moment the wrapper is created, and keep that information alongside the views derived from it.

## 7. `Spliterator` and `Stream` Must Live Within the Appropriate Protection Scope

### 7.1. A `Spliterator` Does Not Hold the Wrapper's Lock for Life

~~~java
synchronized (list) {
    Spliterator<String> source = list.spliterator();
    source.forEachRemaining(value -> consume(value));
}
~~~

This is a sequential traversal under the `List` lock. Do not take a `Spliterator` outside the block and assume the wrapper turned it into a snapshot or a self-locking traverser.

After `trySplit`, the split parts still read from the underlying source. Splitting does not automatically create multiple snapshots independent of writes to the source.

### 7.2. `Stream` Is Lazy, So Pay Attention to Where the Terminal Operation Runs

Incorrect scope pattern:

~~~java
Stream<String> plan;
synchronized (list) {
    plan = list.stream().filter(value -> !value.isBlank());
}

// The actual traversal happens outside the lock.
List<String> result = plan.toList();
~~~

Creating the pipeline inside the lock region does not mean reading the elements is finished. For a source that can be modified by other parties, you must protect the entire terminal execution as required by the contract.

Appropriate sequential pattern:

~~~java
List<String> result;
synchronized (list) {
    result = list.stream()
            .filter(value -> !value.isBlank())
            .toList();
}
~~~

This snippet assumes non-null elements and that a result matching `toList`'s contract fits the requirement.

### 7.3. Do Not Use an Outer Lock as an Automatic Solution for `parallelStream`

A parallel pipeline may dispatch actions to other threads. If the calling thread holds the root lock and waits for tasks to complete, while a task tries to acquire that same lock, the program can fail to make progress.

Even when callbacks do not acquire the lock, you still need to understand the source's policy, protection scope, and lock hold cost. When you want parallel processing or long-running work, a more controllable approach is usually to create a valid snapshot under the lock and process the snapshot after releasing it.

This does not mean every `parallelStream` is forbidden. It is a requirement to design lock ownership and hold duration deliberately rather than wrapping with `synchronized` and ignoring task behavior.

## 8. Objects Commonly Chosen by Mistake as Locks

### 8.1. Locking the Underlying Collection Instead of the Wrapper

~~~java
List<String> backing = new ArrayList<>();
List<String> safe = Collections.synchronizedList(backing);
~~~

The wrapper's methods use `safe`'s protocol. Holding only `synchronized(backing)` does not force a thread calling `safe.add` to wait on that lock.

To avoid this mistake, create the wrapper and keep it as the single access point. Do not leave other code modifying `backing` directly outside the protocol. If a custom design uses a different lock, every access site must follow that design uniformly; do not accidentally mix it with the standard wrapper's mutex.

### 8.2. Locking the `Iterator`

An `Iterator` is a traversal object, not the lock object used by the wrapper's methods. `synchronized(iterator)` does not make callers of `list.add` coordinate with that loop.

Similarly, locking a `Stream` or `Spliterator` locks only that object; it does not lock the source.

### 8.3. Two Separate Wrappers on the Same Backing Collection

~~~java
List<String> first = Collections.synchronizedList(backing);
List<String> second = Collections.synchronizedList(backing);
~~~

Two independent factory calls do not detect the shared backing collection and unify on one monitor. One party locking `first` does not prevent another party from going through `second` under a different monitor.

If two parties both modify `backing` through two independent protocols, the fact that both are called `synchronizedList` will not save the design.

In the program below, this case only tests whether two different monitors can be acquired; it does not perform conflicting writes to `backing`. It serves to demonstrate lock identity, not as a pattern for using two wrappers to protect the same source.

### 8.4. Locking an Outer Read-Only Wrapper

~~~java
List<String> readOnly = Collections.unmodifiableList(safe);
~~~

`readOnly` forbids modifications through that interface, but `readOnly`'s monitor is not automatically `safe`'s monitor. Holding `synchronized(readOnly)` does not make code using `safe` obey that lock.

If an API only exposes `readOnly` to callers, consider providing a snapshot or a managed read method from the owning side. Do not require callers to guess how many wrapper layers exist inside and which lock is the right one.

## 9. A Read API Should Keep Locking Authority Where the Source Is Known

If a function only accepts `Collection<T> view` and writes `synchronized(view)`, it does not have enough basis to guarantee correctness for every synchronized view that might be passed in.

Two clearer design directions:

| Approach | Responsibility |
| --- | --- |
| The data owner performs the read pass | It knows the root wrapper and holds the right lock |
| The data owner returns an independent snapshot | It creates the snapshot under a valid protocol and lets the caller read outside the lock |

You can also pass an agreed-upon lock object in an internal API, but that must be an explicit contract. Passing an arbitrary `Object` does not automatically create a relationship with methods modifying the source.

Also avoid returning a live `Iterator` from inside a `synchronized` method:

~~~java
// Demonstrates a design that does not hold the lock while the caller uses the Iterator.
Iterator<String> iteratorForCaller() {
    synchronized (list) {
        return list.iterator();
    }
}
~~~

The monitor is already released when the method returns. If you need to provide data for the caller to traverse independently, returning an appropriate copy is usually easier to express correctly.

The goal is not to hide locks to the point where callers cannot tell whether data is consistent. The goal is to place protocol enforcement where sufficient information exists and keep the scope of responsibility clear.

## 10. Create a Snapshot Under the Lock, Then Work Outside the Lock

For a list of non-null names:

~~~java
List<String> snapshot;
synchronized (list) {
    snapshot = List.copyOf(list);
}

process(snapshot);
~~~

`process` is an application-provided function; this snippet illustrates separating lock hold time from potentially long processing. The snapshot does not reflect subsequent positional additions or removals in the source `List`.

If the source can legitimately contain `null`, choose a copy operation that accepts `null` and has the appropriate mutability rather than defaulting to `List.copyOf`. A structural copy also does not automatically clone mutable element objects.

For a `Map`, if you need a snapshot of pairs for later use, create independent pairs right inside the lock region. If using `SimpleImmutableEntry`, the key/value references are preserved in the new pair; internal state of mutable key/value objects still requires its own policy.

A snapshot is only meaningful if creating it read the source validly. Creating a copy outside the lock from a wrapper being modified by other parties does not solve the stable-traversal requirement just by being called a "copy".

Readers also need to know that snapshot data may be stale. If business logic must check a condition and then update based on current state, do not replace that transactional step with a snapshot while omitting the required atomic validation/update.

## 11. Locking the Right Object Does Not Replace the Iterator Contract and Callback Policy

Holding the lock prevents parties following the same lock from interleaving, but the traversing thread itself can still perform an invalid operation.

For example, calling `add` directly on the source while an `Iterator` is running can break the `Iterator`'s contract, even though the same thread holds the lock and can re-enter the monitor. Reentrancy does not turn an arbitrary structural modification into a valid `Iterator` operation.

If you need to remove during a supported traversal, use the appropriate `Iterator` operation or a modification method suited to the structure and requirements. Do not treat a single run without `ConcurrentModificationException` as proof that any modification is acceptable.

Callbacks inside the lock region also need control. A callback that performs slow I/O, acquires another lock, or waits for work that needs the root lock can increase blocking time or cause a deadlock.

If multiple locks are needed for multiple sources, establish a consistent lock acquisition order in the design. Do not lock `List` before `Map` in one place and `Map` before `List` in another without considering circular waiting.

For `list.forEach(action)` directly, the wrapper implementation may synchronize the entire method; that is not the same call as `list.iterator().forEachRemaining(action)`. Do not infer from a convenience method having an internal lock that every extracted traverser holds the lock for its entire usage.

## 12. Checking Monitors with `Thread.holdsLock`

`Thread.holdsLock(object)` reports whether **the current thread** holds the monitor of that object. It does not acquire the lock, does not wait for the lock, and does not check whether another thread holds the lock. [Java SE 17 — Thread.holdsLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#holdsLock(java.lang.Object)).

In the example:

~~~java
synchronized (list) {
    System.out.println(Thread.holdsLock(list)); // true
    System.out.println(Thread.holdsLock(tail)); // false if tail is a different object
}
~~~

These two results do not contradict the fact that `tail`'s methods share the root mutex. Calling `holdsLock(tail)` only queries the monitor of `tail` itself.

This method is useful for checking preconditions of internal helpers or for learning about lock identity. It does not by itself prove the entire system is safe; you must still verify all data-modification sites and traverser lifetimes.

The program also uses a probe thread and a latch: while the calling thread holds the view's monitor, the probe thread tries to acquire the root monitor. If it succeeds and signals through the latch before the calling thread releases the view, that proves the two monitors are not mutually exclusive.

The latch only coordinates the test; it does not participate in a broken source traversal algorithm. [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html).

## 13. Complete Demonstration Program

Save the following code as **WrapperTraversalLockDemo.java**. The program uses Java 17-compatible APIs and requires no external libraries.

All actual traversals hold the correct root lock. The wrong-lock tests only probe monitors and do not traverse or write conflicting data through an unprotected view. There is no attempt to reproduce a random failure from a data race.

After adding `D` to the root `List`, the program does not continue using the old `subList`. Entries from the `Map` are converted to strings right inside the lock, so the data printed afterward does not retain live entries from the view.

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.SortedMap;
import java.util.SortedSet;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

public class WrapperTraversalLockDemo {
    private static boolean rootLockAvailableWhileViewHeld(Object root, Object view)
            throws InterruptedException {
        CountDownLatch enteredRoot = new CountDownLatch(1);
        Thread probe = new Thread(() -> {
            synchronized (root) {
                enteredRoot.countDown();
            }
        });
        boolean entered;
        synchronized (view) {
            probe.start();
            entered = enteredRoot.await(5, TimeUnit.SECONDS);
        }
        probe.join(5000);
        if (probe.isAlive()) {
            probe.interrupt();
            throw new AssertionError("Probe did not finish");
        }
        return entered;
    }

    public static void main(String[] args) throws Exception {
        List<String> list = Collections.synchronizedList(
                new ArrayList<>(List.of("A", "B", "C")));
        List<String> visited = new ArrayList<>();
        synchronized (list) {
            Iterator<String> iterator = list.iterator();
            while (iterator.hasNext()) {
                visited.add(iterator.next());
            }
            System.out.println("list-root-held=" + Thread.holdsLock(list));
        }
        System.out.println("list-values=" + visited);

        List<String> tail = list.subList(1, 3);
        List<String> tailValues = new ArrayList<>();
        synchronized (list) {
            for (String value : tail) {
                tailValues.add(value);
            }
            System.out.println("sublist-root-held=" + Thread.holdsLock(list));
            System.out.println("sublist-view-held=" + Thread.holdsLock(tail));
        }
        System.out.println("sublist-values=" + tailValues);
        synchronized (tail) {
            System.out.println("view-only-root-held=" + Thread.holdsLock(list));
        }
        System.out.println("root-available-under-sublist-lock="
                + rootLockAvailableWhileViewHeld(list, tail));

        String joined;
        synchronized (list) {
            joined = list.stream().collect(Collectors.joining("|"));
        }
        System.out.println("stream-under-root=" + joined);

        Map<String, Integer> map = Collections.synchronizedMap(new LinkedHashMap<>());
        map.put("B", 2);
        map.put("A", 1);
        Set<String> keys = map.keySet();
        Collection<Integer> values = map.values();
        Set<Map.Entry<String, Integer>> entries = map.entrySet();
        List<String> keyValues = new ArrayList<>();
        List<Integer> mappedValues = new ArrayList<>();
        List<String> entryValues = new ArrayList<>();
        synchronized (map) {
            for (String key : keys) {
                keyValues.add(key);
            }
            for (Integer value : values) {
                mappedValues.add(value);
            }
            for (Map.Entry<String, Integer> entry : entries) {
                entryValues.add(entry.getKey() + "=" + entry.getValue());
            }
            System.out.println("map-root-held=" + Thread.holdsLock(map));
            System.out.println("map-key-view-held=" + Thread.holdsLock(keys));
        }
        System.out.println("map-keys=" + keyValues);
        System.out.println("map-values=" + mappedValues);
        System.out.println("map-entries=" + entryValues);
        System.out.println("map-root-available-under-key-lock="
                + rootLockAvailableWhileViewHeld(map, keys));

        SortedSet<Integer> sorted = Collections.synchronizedSortedSet(
                new TreeSet<>(List.of(1, 2, 3, 4)));
        SortedSet<Integer> head = sorted.headSet(4);
        List<Integer> headValues = new ArrayList<>();
        synchronized (sorted) {
            for (Integer value : head) {
                headValues.add(value);
            }
            System.out.println("set-root-held=" + Thread.holdsLock(sorted));
            System.out.println("set-range-held=" + Thread.holdsLock(head));
        }
        System.out.println("set-range-values=" + headValues);

        SortedMap<String, Integer> sortedMap =
                Collections.synchronizedSortedMap(new TreeMap<>());
        sortedMap.put("A", 1);
        sortedMap.put("B", 2);
        sortedMap.put("C", 3);
        SortedMap<String, Integer> range = sortedMap.subMap("A", "C");
        List<String> rangeKeys = new ArrayList<>();
        synchronized (sortedMap) {
            for (String key : range.keySet()) {
                rangeKeys.add(key);
            }
            System.out.println("sorted-map-root-held=" + Thread.holdsLock(sortedMap));
            System.out.println("sorted-map-range-held=" + Thread.holdsLock(range));
        }
        System.out.println("sorted-map-range-keys=" + rangeKeys);

        List<String> snapshot;
        synchronized (list) {
            snapshot = List.copyOf(list);
        }
        list.add("D");
        System.out.println("snapshot=" + snapshot);
        System.out.println("current-list=" + list);

        List<String> sharedBacking = new ArrayList<>(List.of("X"));
        List<String> firstWrapper = Collections.synchronizedList(sharedBacking);
        List<String> secondWrapper = Collections.synchronizedList(sharedBacking);
        System.out.println("independent-wrapper-locks="
                + rootLockAvailableWhileViewHeld(firstWrapper, secondWrapper));

        List<String> readOnly = Collections.unmodifiableList(list);
        System.out.println("outer-read-only-lock-is-different="
                + rootLockAvailableWhileViewHeld(list, readOnly));
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 -encoding UTF-8 WrapperTraversalLockDemo.java
java WrapperTraversalLockDemo
~~~

Exact stdout:

~~~text
list-root-held=true
list-values=[A, B, C]
sublist-root-held=true
sublist-view-held=false
sublist-values=[B, C]
view-only-root-held=false
root-available-under-sublist-lock=true
stream-under-root=A|B|C
map-root-held=true
map-key-view-held=false
map-keys=[B, A]
map-values=[2, 1]
map-entries=[B=2, A=1]
map-root-available-under-key-lock=true
set-root-held=true
set-range-held=false
set-range-values=[1, 2, 3]
sorted-map-root-held=true
sorted-map-range-held=false
sorted-map-range-keys=[A, B]
snapshot=[A, B, C]
current-list=[A, B, C, D]
independent-wrapper-locks=true
outer-read-only-lock-is-different=true
~~~

The code was compiled with `--release 17` and run on JDK 24.0.2. The compiler flag verifies the Java 17 language/API level; the runtime JVM is explicitly noted rather than representing a run on a Java 17 JVM.

How to read the output:

- `list-root-held` confirms that the `List` traversal region holds the root monitor.
- `sublist-root-held` and `sublist-view-held` distinguish the root from the `subList` object.
- `view-only-root-held` shows that locking only the `subList` does not cause the current thread to hold the root lock.
- The `root-available` lines show that another thread can acquire the root while we only hold the view's monitor.
- `map-keys`, `map-values`, and `map-entries` are collected within a single `Map` lock region.
- The `SortedSet` and `SortedMap` ranges are traversed under the root wrapper lock, not under the range's own monitor.
- `snapshot` remains unchanged after `D` is added to the source.
- The last two lines check the distinct monitors of two independent wrappers and an outer read-only wrapper.

Printing order is driven by the `main` thread. The probe thread only signals via the latch and exits; the program does not use `sleep` to guess thread scheduling.

## 14. Practice with Answers

### Exercise 1 — Root List and Iterator

A helper locks a `synchronizedList`, creates an `Iterator`, releases the lock, and returns the `Iterator`. Can the caller treat that `Iterator` as protected for the entire traversal?

**Answer:** No. The monitor is already released when the helper returns. You must hold the right lock for the entire duration of using the traverser, or return a snapshot for the caller to traverse independently.

### Exercise 2 — Locking `keySet`

A `Map` is created with `synchronizedMap`. Why does `synchronized(map.keySet())` not replace `synchronized(map)` for a loop over the keys?

**Answer:** Wrapper operations coordinate through the `Map`'s root mutex. The monitor of the `keySet` object is a different object. Locking `keySet` does not make callers of `map.put` wait on that same monitor.

### Exercise 3 — A `subList` That Has `synchronized` in Its Implementation Name

The `subList` of a `synchronizedList` is still a synchronized wrapper. Why is locking the `subList` itself around an `Iterator` still wrong?

**Answer:** The sub-wrapper shares the root's mutex for its methods; it does not use its own monitor as an independent lock for the entire traversal. You must track and hold the root wrapper that owns the shared locking protocol.

### Exercise 4 — Sub-Range of a `SortedMap`

Suppose `root` is a `synchronizedSortedMap`, `range` is `root.subMap(...)`, and `keys` is `range.keySet()`. When traversing `keys`, which object should you lock?

**Answer:** Lock `root`. Do not choose `range` or `keys` just because they are closer to the loop. Nested view layers continue to use the root protocol per the wrapper contract.

### Exercise 5 — Creating a `Stream` Under the Lock

A pipeline is created under `synchronized(list)`, but `toList` runs after exiting the block. Are the elements protected for the traversal?

**Answer:** Not merely from the pipeline-creation step. Because `Stream` is lazy, the terminal operation is where the actual read happens. Hold the appropriate lock during the sequential terminal operation, or create a valid snapshot and process it outside the lock.

### Exercise 6 — Two Wrappers on the Same Backing Collection

Two modules each call `synchronizedList` on the same `ArrayList`, and each locks its own wrapper. Is that enough coordination?

**Answer:** No. Two independent wrappers have independent monitors. You need a single access point and a shared locking protocol; do not create multiple separate wrappers and assume they unify on one lock.

### Exercise 7 — Does `holdsLock` Acquire the Lock?

`Thread.holdsLock(root)` returns `false`. Does that mean `root` is currently held by another thread? Does the call protect the code that follows?

**Answer:** It tells you neither. It only reports that the current thread does not hold `root`'s monitor, and it performs no lock acquisition. To use the protocol, you must acquire the lock with the appropriate mechanism; `holdsLock` is only an observation or precondition check.

### Exercise 8 — Holding the Lock While a Callback Adds Elements

An `Iterator` loop already holds the correct wrapper lock. A callback calls `add` directly on the source on the same thread. Why can this still be invalid?

**Answer:** Locking prevents other parties from interleaving, but it does not change the `Iterator` contract. Modifying the structure directly during traversal can invalidate the `Iterator`. Monitor reentrancy does not make an arbitrary modification a valid traversal operation.

## 15. Rules for Working with Synchronized Wrappers

Retain information about the root object from the moment the wrapper is created so that all views and read–write operations coordinate under the same protocol. When traversing, lock the right root before creating the traverser and hold it until the protected scope is complete.

If you do not want to hold the lock across long processing, create independent data inside the protected region and work on it outside the lock. Do not let an `Iterator`, `Spliterator`, unexecuted `Stream`, or live entry leak a traversal out of the scope in which it must be protected.

The core rule is: **lock the object that owns the synchronization protocol, not a lock chosen by variable name or by the view being traversed.** For a root `List`/`Set`, that is the root wrapper; for `Map` views and sub-ranges sharing a mutex, it is still the root lock specified by the contract.
