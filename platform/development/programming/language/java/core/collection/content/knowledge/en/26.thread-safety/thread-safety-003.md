# Collections.synchronizedList, synchronizedSet, and synchronizedMap

## 1. How do synchronized wrappers handle collection access?

When multiple threads of execution share an ordinary collection, one thread adding or removing elements while another thread accesses it can cause the program to violate that data structure's contract. One way to organize access is to place all access operations behind the same locking mechanism.

Three `Collections` methods create wrappers for this purpose:

| Method | Accepts backing structure | Returns |
| --- | --- | --- |
| `synchronizedList(list)` | A `List<E>` | A `List<E>` whose direct access operations are synchronized |
| `synchronizedSet(set)` | A `Set<E>` | A `Set<E>` whose direct access operations are synchronized |
| `synchronizedMap(map)` | A `Map<K,V>` | A `Map<K,V>` whose direct access operations are synchronized |

The wrapper still uses the backing structure passed into it. It does not copy every element into an independent collection, nor does it make the element objects themselves thread-safe.

The model to understand is:

```text
Callers
      ↓
A shared synchronized wrapper
      ↓
Same locking mechanism for matching operations
      ↓
Backing collection
```

Direct operations such as `list.add`, `set.add`, or `map.put` go through the wrapper. However, an algorithm consisting of multiple calls, or an iteration using an iterator, does not automatically become an atomic unit of work just because the collection is wrapped.

Therefore, there are three levels to distinguish:

1. **A single synchronized direct access operation.**
2. **A sequence of business operations that must be inside the same locked region.**
3. **An iteration that must be guarded for the entire lifetime of the iterator.**

This lesson verifies each of those three levels for List, Set, and Map. The programs target Java 17 and include filenames, compilation commands, and stdout so you can run them independently.

## 2. Create one wrapper and unify the access path

Illustrative initialization, placed inside a method with the corresponding `import` statements:

```java
List<String> names = Collections.synchronizedList(new ArrayList<>());
Set<String> codes = Collections.synchronizedSet(new HashSet<>());
Map<String, Integer> counts = Collections.synchronizedMap(new HashMap<>());
```

The backing structure is created directly inside the call to avoid keeping another reference that could bypass the wrapper.

The contract of these methods emphasizes that all access to the backing structure must go through the returned wrapper. If you still modify a backing `ArrayList` through an old reference while another caller uses the wrapper, there is no longer a single protection policy. [Javadoc synchronizedList, synchronizedSet, and synchronizedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html)

### The wrapper does not change every property of the backing structure

For example:

- `synchronizedList(new ArrayList<>())` still has list semantics, preserving duplicate elements and index order.
- `synchronizedSet(new HashSet<>())` still follows hash set uniqueness rules and does not guarantee iteration order.
- `synchronizedMap(new HashMap<>())` still uses hash map key rules.
- Whether `null` is allowed or a specific mutating operation is supported still depends on the backing structure.
- Wrapping an unmodifiable list does not automatically make `add` a supported operation.

"Synchronized" and "modifiable" are two different properties.

### Do not create two independent wrappers over the same backing structure

The snippet below illustrates a design that fails the shared-lock requirement; it is not a pattern to follow:

```java
List<String> raw = new ArrayList<>();
List<String> first = Collections.synchronizedList(raw);
List<String> second = Collections.synchronizedList(raw);
```

`first` and `second` are two independent wrappers. Operations going through those two objects are not protected by the same monitor simply because both reference `raw`.

Similarly, locking on `raw` does not substitute for the lock used by operations going through the wrapper. You need a single access path and a consistent locking policy, rather than having each caller wrap it separately or choose its own lock object.

If you want to accept initial data and then own a private structure, you can make a backing copy before wrapping it. That copy must still be made at a point when reading the input data is valid; a wrapper cannot fix a copy that is already being concurrently mutated.

## 3. Experimenting with direct operations on the three wrappers

Save as `SynchronizedWrappersDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class SynchronizedWrappersDemo {
    public static void main(String[] args) throws InterruptedException {
        List<Integer> list = Collections.synchronizedList(new ArrayList<>());
        Set<Integer> set = Collections.synchronizedSet(new HashSet<>());
        Map<Integer, Integer> map = Collections.synchronizedMap(new HashMap<>());

        Runnable write = () -> {
            for (int i = 0; i < 200; i++) {
                list.add(i);
                set.add(i);
                map.put(i, i * 2);
            }
        };
        Thread first = new Thread(write);
        Thread second = new Thread(write);
        first.start();
        second.start();
        first.join();
        second.join();

        int listSum;
        synchronized (list) {
            listSum = list.stream().mapToInt(Integer::intValue).sum();
        }
        TreeSet<Integer> sortedSet;
        synchronized (set) {
            sortedSet = new TreeSet<>(set);
        }

        System.out.println("listSize=" + list.size());
        System.out.println("listSum=" + listSum);
        System.out.println("setSize=" + set.size());
        System.out.println("setFirstForDisplay=" + sortedSet.first());
        System.out.println("setLastForDisplay=" + sortedSet.last());
        System.out.println("mapSize=" + map.size());
        System.out.println("mapValue199=" + map.get(199));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SynchronizedWrappersDemo.java
java SynchronizedWrappersDemo
```

Stdout:

```text
listSize=400
listSum=39800
setSize=200
setFirstForDisplay=0
setLastForDisplay=199
mapSize=200
mapValue199=398
```

Both threads insert the numbers 0 through 199 into the three structures:

- The List receives each number twice, so it has 400 elements; the sum is `2 × (0 + ... + 199) = 39800`.
- The Set keeps each number only once, so it has 200 elements.
- The Map has 200 keys; both threads write the same value `i * 2` for each key, so key 199 has value 398.

The program does not predict how the two threads interleave when adding to the List. Nor does it predict the iteration order of `HashSet`. The first and last values are printed from a `TreeSet` copy created specifically for ordered display.

Creating the set copy is placed inside `synchronized (set)`, because reading elements to copy them is an iteration. The stream sum calculation is also entirely inside `synchronized (list)`.

The `join()` calls wait for both writer threads to finish before printing the summary results. That way stdout does not describe an intermediate state while writers are still running.

### Three structures do not automatically form a single transaction

Each wrapper has its own locking mechanism. The three statements adding to the List, Set, and Map in the loop body are not a single transaction spanning all three structures.

For example, while the threads are still running, an observer might see the List operation completed while the corresponding Map operation has not happened yet. If the business logic requires an invariant relating multiple structures, you must design a guarded region at the data-owning layer and unify all related access paths.

Do not infer from a correct result after `join` that every intermediate state also satisfies cross-structure invariants.

## 4. A check-then-act sequence needs the same locked region

Consider the requirement: only add code `X` to a list if it is not already present.

The following snippet is insufficient, even though `names` is a synchronized list:

```java
if (!names.contains("X")) {
    names.add("X");
}
```

`contains` and `add` are two separate operations. After the check completes and before adding, another caller can perform the same check and then add.

A valid interleaving is:

```text
Thread A: contains(X) → false
Thread B: contains(X) → false
Thread A: add(X)
Thread B: add(X)
Result: [X, X]
```

There is no requirement for both threads to enter the `add` method at the exact same instant. Each individual operation is guarded, yet the overall decision still violates the goal of "only one X".

### Experiment to produce a controlled interleaving

Save as `SynchronizedCheckThenActDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public class SynchronizedCheckThenActDemo {
    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        List<String> broken = Collections.synchronizedList(new ArrayList<>());
        CountDownLatch bothChecked = new CountDownLatch(2);
        Runnable splitOperation = () -> {
            boolean absent = !broken.contains("X");
            bothChecked.countDown();
            await(bothChecked);
            if (absent) {
                broken.add("X");
            }
        };
        Thread first = new Thread(splitOperation);
        Thread second = new Thread(splitOperation);
        first.start();
        second.start();
        first.join();
        second.join();
        System.out.println("separateCalls=" + broken);
        System.out.println("separateSize=" + broken.size());

        List<String> guarded = Collections.synchronizedList(new ArrayList<>());
        CountDownLatch start = new CountDownLatch(1);
        Runnable combinedOperation = () -> {
            await(start);
            synchronized (guarded) {
                if (!guarded.contains("X")) {
                    guarded.add("X");
                }
            }
        };
        Thread third = new Thread(combinedOperation);
        Thread fourth = new Thread(combinedOperation);
        third.start();
        fourth.start();
        start.countDown();
        third.join();
        fourth.join();
        System.out.println("oneCriticalSection=" + guarded);
        System.out.println("guardedSize=" + guarded.size());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SynchronizedCheckThenActDemo.java
java SynchronizedCheckThenActDemo
```

Stdout:

```text
separateCalls=[X, X]
separateSize=2
oneCriticalSection=[X]
guardedSize=1
```

The `separateCalls` section uses `CountDownLatch(2)` to force both threads to finish the check before either can proceed to `add`. Both observed that `X` was absent, so the result contains two `X` elements.

This is a way to verify a possible interleaving. There is no need to rely on `Thread.sleep` or hope to catch the bug by chance across many runs. The latch only coordinates the timing of the experiment; it does not combine two operations into an atomic one. [Javadoc CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)

The `oneCriticalSection` section places both the check and the add inside `synchronized (guarded)`. While one thread is in this region, operations going through the same wrapper from another caller must coordinate via the same lock. After the first thread adds `X`, the second thread's check will see that it is already present.

Do not place a barrier waiting for two threads to be inside mutually exclusive locked regions at the same time. In the program, the start signal for the correct section is awaited before acquiring the lock.

### Why lock on the wrapper itself?

For the root wrapper returned by the methods in this lesson, the wrapper object itself is the monitor used to coordinate with direct operations. Locking on a separate `new Object()` will not automatically block another caller that is only calling `guarded.add`.

A thread holding a monitor can re-enter operations that require the same monitor; this mechanism is called reentrant locking. Therefore, calling `contains` and `add` inside `synchronized (guarded)` is the appropriate pattern. [Java Language Specification on synchronization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.1)

If the data requirement is genuinely a set of unique values, `Set.add` already combines the membership check and insertion into a single set operation. There is no need to use a List just to rebuild all of Set's rules by hand. However, for an invariant involving multiple conditions or multiple operations, you still need to define the proper scope of the locked region.

## 5. synchronizedMap does not automatically combine get-then-put into a counter increment

A similar bug occurs with incrementing a value:

```java
// Insufficiently guarded snippet; counts is a synchronized map.
int previous = counts.get("hits");
counts.put("hits", previous + 1);
```

Each `get` or `put` on its own is synchronized. However, two callers can both read 0, both compute 1, and sequentially write 1. The result of two increments is a final value of only 1.

To express an increment using these two calls, you must lock both the read step and the write step on the same wrapper.

Save as `SynchronizedMapCounterDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public class SynchronizedMapCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        Map<String, Integer> counts =
                Collections.synchronizedMap(new HashMap<>());
        counts.put("hits", 0);

        List<Thread> threads = new ArrayList<>();
        for (int t = 0; t < 4; t++) {
            Thread thread = new Thread(() -> {
                for (int i = 0; i < 1000; i++) {
                    synchronized (counts) {
                        int previous = counts.get("hits");
                        counts.put("hits", previous + 1);
                    }
                }
            });
            threads.add(thread);
            thread.start();
        }
        for (Thread thread : threads) {
            thread.join();
        }

        Map<String, Integer> snapshot;
        synchronized (counts) {
            snapshot = new TreeMap<>(counts);
        }
        System.out.println("expected=4000");
        System.out.println("actual=" + counts.get("hits"));
        System.out.println("snapshot=" + snapshot);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SynchronizedMapCounterDemo.java
java SynchronizedMapCounterDemo
```

Stdout:

```text
expected=4000
actual=4000
snapshot={hits=4000}
```

Four threads run, each incrementing 1000 times. Each increment places `get` and `put` inside the same `synchronized (counts)`, so the result is 4000.

Reading the map to create a `TreeMap` copy is also guarded by the `counts` lock. Afterward, the copy is used for display without continuing to hold the shared map's lock.

This example does not imply that every Map algorithm must be hand-written with `get` then `put`. A compound-operation API may express the intent better in the appropriate situation. What you need to check is the contract of the exact method and the exact Map type, rather than assuming a sequence of separate calls is automatically atomic just from the word "synchronized".

### Multiple reads can also be a compound operation

It is not only updates that need care. With a List, checking non-emptiness and then fetching the first element can be broken by another caller removing data between the two calls:

```java
// Guarded scope illustration; list is a synchronized list.
synchronized (list) {
    if (!list.isEmpty()) {
        String first = list.get(0);
        // Use first within the required guarded scope.
    }
}
```

If you only need to retrieve an element reference, once retrieved you can continue processing outside the lock when the contract permits. If you need to read multiple related states of the element, you must also consider the protection policy for that state.

Marking a collection reference variable `final` also does not automatically combine calls. `final` and the atomicity of an algorithm are two different concerns.

## 6. Iteration requires locking for the entire traversal, not just when obtaining the iterator

The wrapper does not hold the lock on the caller's behalf for the entire duration of using an `Iterator`, `Spliterator`, or `Stream`.

For a root List or Set, the iteration pattern is:

```java
// Illustration snippet; names is a synchronized List<String>.
synchronized (names) {
    Iterator<String> iterator = names.iterator();
    while (iterator.hasNext()) {
        String value = iterator.next();
        // Brief processing; do not structurally modify while iterating.
    }
}
```

Create the iterator inside the locked region and keep holding the lock until iteration finishes. A `for (String value : names)` loop also uses the iterator mechanism; shorter syntax does not automatically add a lock guard.

For a Stream, you must guard the execution of the terminal operation as well:

```java
// Illustration snippet; values is a synchronized List<Integer>.
int total;
synchronized (values) {
    total = values.stream().mapToInt(Integer::intValue).sum();
}
```

Locking only when calling `values.stream()` and then executing `sum()` after leaving the synchronized block does not protect the element-reading phase.

### Map views use the root Map's lock

With `synchronizedMap`, the `keySet()`, `values()`, and `entrySet()` views remain backed by the Map. When iterating over them, synchronize on the returned Map wrapper, not on the view object itself. [Javadoc synchronizedMap on view iteration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map))

For example, `Set<K> keys = map.keySet()` does not make `keys` a copy set. Adding or removing mappings in the Map can change the contents visible through `keys`.

Save as `SynchronizedMapViewsDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.StringJoiner;
import java.util.TreeMap;

public class SynchronizedMapViewsDemo {
    public static void main(String[] args) {
        Map<String, Integer> map =
                Collections.synchronizedMap(new LinkedHashMap<>());
        map.put("A", 1);
        map.put("B", 2);
        map.put("C", 3);
        Set<String> keys = map.keySet();

        StringJoiner entries = new StringJoiner(",");
        int sum = 0;
        boolean holdsMapLock;
        Map<String, Integer> afterRemoval;
        synchronized (map) {
            holdsMapLock = Thread.holdsLock(map);
            for (Map.Entry<String, Integer> entry : map.entrySet()) {
                entries.add(entry.getKey() + "=" + entry.getValue());
                sum += entry.getValue();
            }
            Iterator<String> iterator = keys.iterator();
            while (iterator.hasNext()) {
                if (iterator.next().equals("B")) {
                    iterator.remove();
                }
            }
            afterRemoval = new TreeMap<>(map);
        }

        map.put("D", 4);
        List<String> keySnapshot;
        synchronized (map) {
            keySnapshot = new ArrayList<>(keys);
        }
        System.out.println("holdsMapLock=" + holdsMapLock);
        System.out.println("entriesBeforeRemoval=" + entries);
        System.out.println("sumBeforeRemoval=" + sum);
        System.out.println("afterRemoval=" + afterRemoval);
        System.out.println("keysAfterLaterPut=" + keySnapshot);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SynchronizedMapViewsDemo.java
java SynchronizedMapViewsDemo
```

Stdout:

```text
holdsMapLock=true
entriesBeforeRemoval=A=1,B=2,C=3
sumBeforeRemoval=6
afterRemoval={A=1, C=3}
keysAfterLaterPut=[A, C, D]
```

The program uses a backing `LinkedHashMap` so that the insertion order `A`, `B`, `C` is deterministic for display.

Inside `synchronized (map)`:

1. Iterate `entrySet` and compute the sum 6.
2. Create an iterator from `keys`.
3. Remove key `B` using `iterator.remove()` itself.
4. Create a copy Map after removal.

The line `holdsMapLock=true` confirms that the Map's monitor is held during the iteration region. The lock used is `map`, not `keys` or `map.entrySet()`.

Afterward, `map.put("D", 4)` adds a mapping. When reading `keys` again under the Map lock, the view contains `[A, C, D]`. It reflects the current source rather than keeping a snapshot from when `keySet` was initially obtained.

### Why is locking on the view not enough?

The object written in `synchronized (x)` determines which monitor is held. Locking on `keys` and locking on `map` are two different things.

Ordinary update operations through the Map wrapper coordinate with the Map's monitor. A `synchronized (keys)` block does not automatically prevent them from running just because `keys` is a view of the Map.

The practical rule is to keep a reference to the root wrapper so you use the right monitor when iteration is needed. Do not pass a view elsewhere and lose track of the source's locking policy.

### Locking does not make every modification during iteration legal

Locking prevents other callers from accessing through the same policy, but it does not automatically allow an ordinary iterator to tolerate arbitrary structural modifications from the very thread holding the lock.

For instance, iterating with an iterator while calling `map.remove` through another path can still violate the iterator's contract. When you need to remove elements during iteration and the iterator supports it, use `iterator.remove()` as shown in the program.

Do not rely on the presence or absence of `ConcurrentModificationException` to conclude an algorithm is correct. Change detection is a debugging aid, not a substitute for a locking policy and iteration contract.

Nor should you keep a `Map.Entry` obtained from a view and treat it as an immutable record that can be freely used outside all locks. An Entry can remain tied to the source structure; if you need data for later processing, copy the key and value under the appropriate policy.

## 7. Snapshot data under the lock, then process outside

A long iteration makes other callers that need the same lock wait longer. If the subsequent work does not need to see the latest updates, you can split it into two phases:

1. Hold the lock to capture a valid data state.
2. Release the lock and process the copy or generated output data.

For a List, a structural copy can be `new ArrayList<>(list)` inside a `synchronized (list)` block. For a Map, you can copy the mappings under `synchronized (map)`. If the values are mutable objects, you still need to consider how independent the copy is.

Save as `SynchronizedSnapshotDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class SynchronizedSnapshotDemo {
    static final class Document {
        private String title;

        Document(String title) {
            this.title = title;
        }
    }

    record DocumentView(String title) {}

    public static void main(String[] args) throws InterruptedException {
        Document first = new Document("draft");
        List<Document> documents = Collections.synchronizedList(
                new ArrayList<>(List.of(first)));

        List<Document> structuralSnapshot;
        List<DocumentView> projectedSnapshot;
        synchronized (documents) {
            structuralSnapshot = new ArrayList<>(documents);
            projectedSnapshot = documents.stream()
                    .map(document -> new DocumentView(document.title))
                    .toList();
        }

        Thread writer = new Thread(() -> {
            synchronized (documents) {
                first.title = "updated";
                documents.add(new Document("later"));
            }
        });
        writer.start();
        writer.join();

        System.out.println("sourceSize=" + documents.size());
        System.out.println("structuralSnapshotSize=" + structuralSnapshot.size());
        System.out.println("sharedDocumentTitle=" + structuralSnapshot.get(0).title);
        System.out.println("projectedTitle=" + projectedSnapshot.get(0).title());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SynchronizedSnapshotDemo.java
java SynchronizedSnapshotDemo
```

Stdout:

```text
sourceSize=2
structuralSnapshotSize=1
sharedDocumentTitle=updated
projectedTitle=draft
```

The program captures two kinds of data before starting the writer thread:

- `structuralSnapshot` copies the list structure but still references the same `Document` object.
- `projectedSnapshot` creates `DocumentView` instances whose `String` field holds the title at the time of capture.

After the writer thread changes the title and adds an element:

- The source has two elements.
- The structural copy still has one element.
- The title of the shared object read through the structural copy is now `updated`.
- The title in the projected output data is still `draft`.

### Protecting the collection and protecting element state are different

A synchronized wrapper protects operations accessed through it. A call that mutates a field on an already-retrieved object does not automatically go back through the collection's locking mechanism.

If you choose to use the collection lock to protect the title field as well, every caller reading or writing that field under contention must follow the same policy. Having only one caller use `synchronized (documents)` while another mutates it directly at will is not enough.

In the program, the main thread calls `writer.join()` before reading the modified title. It waits for the writer to finish; the example does not perform an uncoordinated read while the field is being written. The completion relationship between threads makes the observed result meaningful; do not replace `join` with an estimated sleep duration. [Java Language Specification on happens-before](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5)

The fields of `DocumentView` in the example use immutable `String` values, so the title data is decoupled from the mutable field of `Document`. If the output object contains references to other mutable structures, you still need to design how those parts are copied or protected.

### Avoid holding the lock for work that does not need the shared source

Performing I/O, waiting on other tasks, or running long computations inside a locked region can keep other callers waiting. If you can process a snapshot, hold the lock only for the phase that reads the data and maintains the required invariants.

When processing in parallel, other worker threads do not automatically own the monitor held by the calling thread. Do not hold the source lock and then dispatch a subtask that needs that exact lock while the calling thread waits for the result. An appropriate data snapshot often helps separate reading the shared source from the computation phase.

## 8. Scope of guarantees and cost of synchronized wrappers

### Synchronization is also about data visibility

Using the same monitor does more than prevent two guarded regions from running at the same time. Releasing a monitor has a guaranteed happens-before relationship with a subsequent acquisition of the same monitor, thereby providing visibility rules for prior writes.

However, this rule requires a consistent policy. One caller writing outside the lock and another reading inside the lock do not automatically form a valid coordination pair just because the reader uses the `synchronized` keyword.

The programs create data before starting threads, use the wrapper or locked regions for contended access, and wait on `join` before evaluating the final result. These are meaningful coordination points in the Java contract, not guessed wait times.

### A single shared monitor can become a contention point

Direct operations on a root wrapper coordinate through the same monitor, so callers must wait on one another according to that lock scope. This organization is easy to understand and allows grouping a multi-operation invariant with an external lock.

In return, multiple callers accessing the same structure can contend on the same lock, even when working on different elements or different business keys. The wrapper does not promise to make parallel execution faster, nor does it guarantee fair lock scheduling in request order.

Do not shrink the locked region so much that part of an invariant is left out. Nor should you extend it to processing that no longer needs the shared source. The right scope must be determined by the data requirements.

### Do not swap in a concurrent collection while keeping all wrapper-lock assumptions

`ConcurrentHashMap` is designed for concurrent reads and updates under its own policy; its operations do not use the object's monitor under the same contract as a `synchronizedMap` wrapper. Therefore, a `synchronized (map)` block does not automatically block ordinary updates on a `ConcurrentHashMap`. [Javadoc ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

If you need per-key independent operations with better scalability, consider an appropriate concurrent API. If you need a consistent shared state across multiple steps, you must redesign the invariant for the exact structure and operations chosen.

Similarly, `CopyOnWriteArrayList` provides snapshot iteration, but mutations incur the cost of creating a new backing array. It fits workloads with matching read and write characteristics, not as a drop-in replacement for every synchronized list. [Javadoc CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)

The goal is to choose a clear access model: a wrapper with a shared monitor, a snapshot-iterating source, or a concurrent structure with appropriate operations. Do not mix assumptions across them simply because all of them are called thread-safe.

## 9. Designing usage and recognizing common mistakes

A class that owns the data should keep the wrapper reference private and expose meaningful operations. If you expose the collection for callers to mutate directly, it becomes very hard to maintain the owner's compound invariants.

For example, instead of letting callers arbitrarily run `contains` then `add`, the owning class can provide an "add if absent" method with the proper locked region. Instead of returning a Map view without specifying how to lock, it can return a data snapshot when that is what the receiver needs.

The protection scope should be clear in both the description and the code:

| Scenario | Organization |
| --- | --- |
| A single direct `add`, `contains`, `get`, `put` call | Call through the shared wrapper |
| Check then update the same structure | Hold the wrapper's monitor for the entire decision |
| Read multiple values that must be consistent with each other | Read within a properly scoped locked region |
| Iterate a List or Set with an iterator | Hold the root wrapper lock from iterator creation until iteration completes |
| Iterate a view of a synchronized Map | Hold the root Map wrapper lock |
| Execute a stream reading shared data | Hold the lock for the entire traversal phase, or process a snapshot |
| Long computation not requiring the latest state | Snapshot valid data under the lock, then compute outside |
| Elements are mutable objects | Define an additional policy for object state |
| Invariant spanning multiple structures | Design an owning boundary and overarching lock policy; do not treat separate wrappers as a shared transaction |

Common mistakes:

| Pattern or assumption | Problem |
| --- | --- |
| Keeping `raw` and updating it outside the wrapper | Bypasses the chosen protection mechanism |
| Creating two independent wrappers over the same `raw` | Two monitors do not coordinate with each other |
| Locking on the backing collection instead of the root wrapper | Not the same monitor as ordinary operations through the wrapper |
| Assuming two separate calls are automatically atomic | Another operation can interleave between them |
| Locking when creating the iterator and releasing before the loop | The actual traversal is no longer guarded |
| Using a `for-each` loop and forgetting it uses an iterator | The syntax does not automatically add a locked region |
| Iterating `map.keySet()` under `synchronized (keys)` | Must lock on the root Map wrapper |
| Creating a stream under the lock and executing after releasing it | Does not protect the time when the pipeline reads the source |
| Holding the lock and mutating the structure in a way incompatible with the iterator | Locking does not replace the iterator's contract |
| Treating no exception as proof of safety | Coordination bugs are not always caught by exceptions |
| Returning an element object and assuming all its setters are guarded | Setter calls do not automatically acquire the collection lock |
| Switching to `ConcurrentHashMap` while still relying on wrapper monitor locking | The two structures have different coordination contracts |
| Reading multiple collections after individual calls and treating them as one shared state | Separate wrappers do not form a cross-structure transaction |
| Using `sleep` to wait for a writer instead of completion coordination | Elapsed time does not substitute for a signal or `join` |

When fixing a multithreading bug, useful questions are: what state needs protection, which monitor is every caller using, and what scope of operations must be treated as a single unit? Simply adding a wrapper without answering those three questions usually solves only part of the problem.

## 10. Practice verifying the right lock scope

### Exercise 1: why are there still two Xs?

A synchronized list is used with two calls: `contains` then `add`. Each method goes through the wrapper, yet the result still has two `X` elements. Has the wrapper's internal safety broken?

**Reference check:**

No. The bug is that the two-call algorithm was not combined into a single locked region. Two threads can both observe that `X` is absent and then sequentially add it. `SynchronizedCheckThenActDemo` uses a latch to verify this exact interleaving.

Place the entire check and add inside `synchronized (list)` if that is the invariant to preserve.

### Exercise 2: Set and an accompanying action

In a synchronized set that only has callers adding elements and no callers removing them, you want to know whether this exact call added a new code. Do you need to call `contains` then `add` yourself?

**Reference check:**

No. Use the boolean return value of `set.add(code)`: `true` indicates the call added an element that was not present, and `false` indicates the element was already present according to Set rules.

If other updates must happen together with the add as an invariant, you must design a shared protection scope for them. The return value of a single call does not automatically bundle subsequent actions into a transaction.

### Exercise 3: incrementing a counter in a Map

Two threads both read `hits=0` from a synchronized Map and each writes the value it read plus 1. Can the final value be 1? Does one `put` waiting for the other `put` to finish solve it?

**Reference check:**

The final value can be 1. Both computed from the same old value before writing. Serializing the two writes does not bring back the lost increment.

When using `get` then `put`, hold the Map wrapper's monitor across the read, computation, and write as in the counter program.

### Exercise 4: choosing the lock object when iterating a Map

Given `Map<String,Integer> map = Collections.synchronizedMap(...)` and `Set<String> keys = map.keySet()`. When using an iterator from `keys`, should you lock on `keys` or `map`?

**Reference check:**

Lock on `map`, the root wrapper. Create the iterator and hold the lock until iteration finishes. Locking on the view does not use the same monitor as ordinary operations on the Map wrapper.

### Exercise 5: lock block ended before the loop

A program creates an iterator inside `synchronized (list)`, assigns the iterator to an outer variable, and then iterates after leaving the block. Does that meet the requirement?

**Reference check:**

No. What needs protection is the entire traversal process, not just creating the iterator. Hold the lock across the loop, or create a data snapshot under the lock and iterate the snapshot according to its own policy.

### Exercise 6: does a second wrapper save the first wrapper?

One caller uses `first = synchronizedList(raw)`, and another caller creates `second = synchronizedList(raw)`. Neither uses `raw` directly. Is the condition "both are synchronized" enough?

**Reference check:**

No. Two independent wrappers do not automatically share the same monitor. You must share the same wrapper or design a genuinely shared access policy, rather than letting each caller wrap the same data with its own lock.

### Exercise 7: does a copy captured under a lock freeze the elements?

A `List<Document>` is copied with `new ArrayList<>(documents)` under the right lock. Afterward, a caller modifies the title of a shared `Document`. Must the copy retain the old title?

**Reference check:**

No. It is structurally independent, but it still holds references to that object. If you need to preserve the title value at the time of capture, create appropriate output data under the protection policy, such as `DocumentView` in the example.

When verifying reads after writes across different threads, use proper coordination points; do not infer data visibility from a sleep duration.

### Exercise 8: changing the Map type while keeping synchronized

A variable is changed from a synchronized Map to `ConcurrentHashMap`, while still using `synchronized (map)` to try to block all `put` calls from other callers. Can that assumption be kept?

**Reference check:**

No. The monitor rule in this lesson applies to synchronized wrappers. Ordinary operations on `ConcurrentHashMap` do not coordinate under that same assumption. You must choose operations and design invariants according to the contract of the new Map type.

A correct solution must explain why every caller accessing the related state is protected by the same policy, rather than merely pointing out that the code contains the `synchronized` keyword.
