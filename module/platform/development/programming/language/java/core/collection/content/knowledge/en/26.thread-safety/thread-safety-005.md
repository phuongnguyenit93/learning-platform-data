# Concurrent Collections, Locked Wrappers, and Immutable Copies

## 1. Three Different Models for Shared Data

When multiple threads of execution need the same dataset, the first question is not simply "which class is thread-safe?". You need to determine whether the data can still change, who is allowed to modify it, and how consistent a version readers need to observe.

There are three common ways to organize this:

1. **Concurrent collections:** the data structure and its operations are designed for concurrent access under their own contract, such as `ConcurrentHashMap`.
2. **Locked wrappers:** appropriate operations on an underlying collection are coordinated through a locking mechanism, such as `Collections.synchronizedMap`.
3. **Unmodifiable structural copies:** create an output dataset that does not allow adding, removing, or replacing elements through its API; when an update is needed, create and publish a new version.

These three models are not three tiers of "good, better, poor." They address different requirements.

| Question | Concurrent collection | Locked wrapper | Unmodifiable copy |
| --- | --- | --- | --- |
| Can the data be updated in place? | Yes, according to the class API | Yes, if the underlying structure supports it | No, not through the copy's API |
| Who coordinates access? | The specific concurrent structure and operations | The wrapper and lock regions designed by the application | The mechanism for creating, publishing, and swapping versions |
| Is every multi-call sequence automatically atomic? | No | No; you may need to hold the same lock | Swapping references or reading multiple versions still requires design |
| Do readers always get a whole-collection point-in-time snapshot? | Cannot be assumed in general | State can be captured under a properly scoped lock | A stable copy does not prove that reading the source was an atomic snapshot |
| Are the element objects themselves immutable? | No | No | No, if only the structure is copied |

In this lesson, "immutable copy" refers primarily to the collection structure level: disallowing adding, removing, or replacing elements. Deep immutability also requires ensuring the state of element objects and the objects they reference.

A list containing only `String` and a list containing business objects with setters do not have the same level of stability, even though both are created with `List.copyOf`.

## 2. Unmodifiable, Locked, and Copied Are Three Separate Properties

The following expressions represent three different concepts:

```java
// Illustrative snippet; source is a valid List<String>.
List<String> locked = Collections.synchronizedList(source);
List<String> readOnlyView = Collections.unmodifiableList(source);
List<String> snapshot = List.copyOf(source);
```

- `locked` is a synchronized wrapper, but it still uses `source` as its backing data.
- `readOnlyView` blocks modifications through that view itself, but it still sees the backing data.
- `snapshot` has structural contents that do not automatically update with subsequent changes to the source.

If the source is being modified by multiple parties, the copy creation step itself must read the source under a valid policy. Calling `copyOf` does not automatically fix coordination issues on the input.

### Experiment: Wrapper, View, and Copy

Save to `LockedViewAndCopyDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class LockedViewAndCopyDemo {
    public static void main(String[] args) {
        List<String> locked = Collections.synchronizedList(
                new ArrayList<>(List.of("A", "B")));
        List<String> readOnlyView = Collections.unmodifiableList(locked);
        List<String> snapshot;
        synchronized (locked) {
            snapshot = List.copyOf(locked);
        }

        locked.add("C");
        synchronized (locked) {
            System.out.println("locked=" + locked);
            System.out.println("readOnlyView=" + readOnlyView);
        }
        System.out.println("snapshot=" + snapshot);

        try {
            readOnlyView.add("D");
        } catch (UnsupportedOperationException e) {
            System.out.println("viewAdd=UnsupportedOperationException");
        }
        try {
            snapshot.add("D");
        } catch (UnsupportedOperationException e) {
            System.out.println("copyAdd=UnsupportedOperationException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 LockedViewAndCopyDemo.java
java LockedViewAndCopyDemo
```

Stdout:

```text
locked=[A, B, C]
readOnlyView=[A, B, C]
snapshot=[A, B]
viewAdd=UnsupportedOperationException
copyAdd=UnsupportedOperationException
```

After creating the three related objects, the program adds `"C"` through `locked`:

- `locked` has `[A, B, C]`.
- `readOnlyView` also has `[A, B, C]` because it reads the backing data through the wrapper.
- `snapshot` remains `[A, B]`.

Both `readOnlyView.add` and `snapshot.add` are rejected, but the fact that they "cannot be modified through the API" does not give the two objects the same relationship to the source.

`Collections.unmodifiableList` creates a view, whereas `List.copyOf` guarantees that subsequent structural changes to the source are not reflected in the result. [Javadoc Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)), [Javadoc List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))

In the example, creating the copy and reading the view are both placed under `locked`'s lock. Do not wrap with an `unmodifiable` layer and assume you have a new monitor replacing the original monitor.

### Do Not Rely on the Identity of a Copy

A factory may reuse a suitable input object instead of always allocating a new one. What you should rely on is the contract regarding contents and mutability, not the assumption that two references are guaranteed to be distinct.

If you need to publish or update data across threads, use an explicit coordination mechanism. Do not choose a value-based collection object itself as a lock just because you assume it is always a newly allocated distinct object.

## 3. Locked Wrappers Fit a Shared Ownership Policy

With `Collections.synchronizedList`, `synchronizedSet`, or `synchronizedMap`, every access path to the underlying structure must follow the wrapper's policy. Keeping a raw reference and mutating it elsewhere breaks that consistency.

Direct operations such as `add`, `get`, or `put` are coordinated, but a decision spanning multiple calls requires its own guarded scope.

Illustrative snippet for check-then-add under the same monitor:

```java
// names is a shared synchronized List<String>.
synchronized (names) {
    if (!names.contains("new")) {
        names.add("new");
    }
}
```

If you omit the outer block, two threads can still both observe that the element is absent before each adds it in turn. Synchronized individual methods do not make the entire algorithm an atomic operation.

### Iteration Is a Scope That Must Be Guarded

For an iterator, spliterator, or stream over a wrapper, you must follow the manual locking rule for the duration of the traversal. For views of a synchronized `Map`, the lock is the original wrapper `Map`, not the `keySet` or `entrySet` object. [Javadoc synchronizedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map))

This allows the application to capture a controlled state while all participating parties use the same locking policy. In return, parties needing the same lock may have to wait while the guarded region is executing.

A single wrapper does not automatically create transactions across multiple collections. If an invariant spans a `List` and a `Map`, two independent monitors are not enough to ensure readers always see a consistent combined state of both.

### Do Not Carry Over Monitor Rules to All Concurrent Collections

A `synchronized (someMap)` block is only useful when the parties that need coordination actually respect that monitor. Normal operations on `ConcurrentHashMap` do not use the object's monitor in the way `synchronizedMap` does.

Therefore, switching the `Map` implementation while keeping the assumption that "an external lock will block all operations" can break the design. Choosing the structure type and choosing how to protect an invariant are a combined decision.

## 4. Concurrent Collections Provide Operations with Their Own Contracts

`ConcurrentHashMap` allows concurrent reads and updates according to its contract. Reads can generally overlap with updates; you should not picture the entire `Map` as being held by a single shared monitor like a synchronized wrapper.

However, "concurrent collection" does not mean every operation is lock-free, every sequence of calls is atomic, or every traversal is a full snapshot.

The following snippet still fails to combine an increment:

```java
// counts is a ConcurrentHashMap<String, Integer>.
int previous = counts.getOrDefault("count", 0);
counts.put("count", previous + 1);
```

Two threads can read the same old value and then write the same new value. The internal structure of the `Map` remains valid, but the goal of counting every update may not be achieved.

For per-key update requirements, choose the appropriate atomic operation—such as `merge`, `compute`, or `putIfAbsent`—according to the required semantics.

### Experiment: Atomic Per-Key Updates

Save to `ConcurrentMapOperationsDemo.java`.

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;

public class ConcurrentMapOperationsDemo {
    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
        CountDownLatch start = new CountDownLatch(1);
        Thread[] threads = new Thread[4];
        for (int i = 0; i < threads.length; i++) {
            threads[i] = new Thread(() -> {
                await(start);
                for (int n = 0; n < 500; n++) {
                    counts.merge("requests", 1, Integer::sum);
                }
            });
            threads[i].start();
        }
        start.countDown();
        for (Thread thread : threads) {
            thread.join();
        }

        Integer first = counts.putIfAbsent("limit", 42);
        Integer second = counts.putIfAbsent("limit", 99);
        System.out.println("requests=" + counts.get("requests"));
        System.out.println("firstPrevious=" + first);
        System.out.println("secondPrevious=" + second);
        System.out.println("limit=" + counts.get("limit"));

        try {
            counts.put("invalid", null);
        } catch (NullPointerException e) {
            System.out.println("nullValue=NullPointerException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ConcurrentMapOperationsDemo.java
java ConcurrentMapOperationsDemo
```

Stdout:

```text
requests=2000
firstPrevious=null
secondPrevious=42
limit=42
nullValue=NullPointerException
```

All four threads wait for the start signal and then each increments `requests` 500 times. `merge("requests", 1, Integer::sum)` expresses inserting the initial value if absent, or adding to the current value as an atomic operation under the method's contract. After joining the threads, the total is 2000. [Javadoc ConcurrentHashMap.merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#merge(K,V,java.util.function.BiFunction))

The remapping function `Integer::sum` only computes the new value; it performs no I/O and does not update another map. The recomputation function in these operations should be short and adhere to the method's constraints; do not treat it as a place to run an arbitrary long business workflow.

The two `putIfAbsent` calls for the key `"limit"` show:

- On the first call, the key is absent, so `42` is inserted and `null` is returned to indicate there was no previous value.
- On the second call, `42` is already present, so it is not replaced with `99`, and `42` is returned.
- The final value of `"limit"` remains `42`.

`ConcurrentHashMap` does not accept `null` keys or values. Therefore, `firstPrevious=null` indicates there was no previous mapping, not that the `Map` was storing a `null` value.

### Per-Key Atomicity Is Not a Multi-Key Transaction

A correct `merge` or `putIfAbsent` does not automatically create a transaction spanning two keys, two `Map`s, or a `Map` and an external system.

For example, if you need to update two metrics whose sum must remain constant, two separate update calls can still allow readers to observe an intermediate state. In that case, you must design the invariant and data publication strategy appropriately rather than simply changing the `Map` type.

Similarly, retrieving a value object from a `Map` and mutating its fields does not automatically become an atomic `Map` operation. The thread safety of the container structure and the thread safety of element state remain two separate layers.

## 5. Traversal Shows the Difference Between Models Most Clearly

At least three traversal behaviors must be distinguished:

| Traversal type | How it is organized | What the reader must understand |
| --- | --- | --- |
| Traversal under a wrapper lock | Hold the proper monitor for the entire traversal | Updaters using the same lock must wait |
| Snapshot traversal of `CopyOnWriteArrayList` | The iterator holds the array that existed when it was created | It does not automatically see subsequent additions or removals |
| Weakly consistent traversal of `ConcurrentHashMap` | Traverses according to the class's concurrent policy | There is no guarantee of an atomic point-in-time snapshot of the whole `Map` |

Do not lump the latter two together into "anything concurrent does snapshot traversal." Each class's policy has a different meaning.

### Experiment: Wrapper Blocking Writers and Snapshot Iterators

Save to `TraversalModelsDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;

public class TraversalModelsDemo {
    public static void main(String[] args) throws InterruptedException {
        List<Integer> locked = Collections.synchronizedList(
                new ArrayList<>(List.of(1, 2, 3)));
        CountDownLatch approachingAdd = new CountDownLatch(1);
        CountDownLatch addFinished = new CountDownLatch(1);
        List<Integer> lockedRead = new ArrayList<>();
        Thread writer;
        boolean finishedInsideLock;

        synchronized (locked) {
            writer = new Thread(() -> {
                approachingAdd.countDown();
                locked.add(4);
                addFinished.countDown();
            });
            writer.start();
            approachingAdd.await();
            Iterator<Integer> iterator = locked.iterator();
            while (iterator.hasNext()) {
                lockedRead.add(iterator.next());
            }
            finishedInsideLock = addFinished.getCount() == 0;
        }
        writer.join();
        System.out.println("lockedRead=" + lockedRead);
        System.out.println("addFinishedInsideLock=" + finishedInsideLock);
        System.out.println("lockedAfterWriter=" + locked);

        CopyOnWriteArrayList<Integer> copyOnWrite =
                new CopyOnWriteArrayList<>(List.of(1, 2, 3));
        Iterator<Integer> oldIterator = copyOnWrite.iterator();
        Thread anotherWriter = new Thread(() -> copyOnWrite.add(4));
        anotherWriter.start();
        anotherWriter.join();
        List<Integer> oldRead = new ArrayList<>();
        oldIterator.forEachRemaining(oldRead::add);
        System.out.println("snapshotIteratorRead=" + oldRead);
        System.out.println("copyOnWriteAfterWriter=" + copyOnWrite);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 TraversalModelsDemo.java
java TraversalModelsDemo
```

Stdout:

```text
lockedRead=[1, 2, 3]
addFinishedInsideLock=false
lockedAfterWriter=[1, 2, 3, 4]
snapshotIteratorRead=[1, 2, 3]
copyOnWriteAfterWriter=[1, 2, 3, 4]
```

In the synchronized `List` section, the main thread holds `locked`'s monitor. The writer signals before calling `locked.add(4)`. While the main thread still holds the lock, that addition cannot complete, so `addFinishedInsideLock=false`.

Here, the signal is emitted before the writer needs the lock. Thus, the main thread can wait for the milestone inside the locked region without requiring the writer to enter the locked region in order to signal.

The data traversed under the lock is `[1, 2, 3]`. After releasing the lock and waiting for the writer to finish, the source contains `[1, 2, 3, 4]`. The experiment does not guess scheduling state or use sleep durations to infer that the writer has finished.

In the `CopyOnWriteArrayList` section, the iterator is created before adding `4`. The writer completes before the old iterator is traversed, yet the iterator still returns `[1, 2, 3]`. Meanwhile, the current state of the collection is already `[1, 2, 3, 4]`.

That is the iterator's snapshot policy: it reads the array captured at the time the iterator was created and does not update to the collection's newer array. Writes incur the cost of copying the array; this policy must be weighed against read and write frequencies. [Javadoc CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)

### ConcurrentHashMap Does Not Provide That Same Snapshot

`ConcurrentHashMap` iterators and spliterators have a weakly consistent policy. They support traversal during concurrent updates, but they do not guarantee that the overall result corresponds to a single point-in-time state. Aggregate operations such as `size` during updates are also not a barrier for deciding a global invariant. [Javadoc ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

Not throwing `ConcurrentModificationException` is only part of that contract; it does not mean:

- Seeing every update that just occurred.
- Preserving every value as of when the iterator was created.
- Producing the same result as a full read under a lock.
- Being able to perform a multi-key transaction based on the traversal result.

If the use case only needs to traverse changing data for monitoring or best-effort processing under an allowed policy, this consistency model may fit. If a unified version is required, you must design how that version is captured or published.

## 6. A Stable Copy Is Not Necessarily Created from an Atomic Point in Time

`List.copyOf`, `Set.copyOf`, and `Map.copyOf` produce structurally unmodifiable results according to their respective contracts. When the source is modified later, the resulting structure does not follow the source.

However, there are two independent stages:

```text
Read state from source  →  Create unmodifiable result structure
          ↑                                  ↑
   Is it consistent?              Is it stable afterward?
```

A stable output only answers the second question. If the input is being read under a weakly consistent policy, no global lock magically appears just because the final result is created with `copyOf`.

An illustrative example of how a read can be interleaved with updates:

```text
Initial state: A=1, B=1

Copy read: reads A=1
Writer:    updates A to 2
Writer:    updates B to 2
Copy read: reads B=2

Values read: A=1, B=2
```

In this schedule, the states the source passed through were `(1,1)`, `(2,1)`, and `(2,2)`. The pair of values read, `(1,2)`, is not one of those whole-source states.

This illustrates the problem of reading multiple changing values, not a fixed stdout of a program assumed to always hit this exact interleaving. A weakly consistent traversal structure makes no guarantee to prevent all such cases.

### When a Properly Scoped Snapshot Is Needed, Guard the Capture Step

With a locked wrapper, you can hold the appropriate monitor while copying, provided all writers to the relevant data follow the same policy.

With a system that publishes unmodifiable versions, readers can acquire a version reference once and read all data from that exact version.

With a concurrent collection being updated independently across multiple keys, if the requirement demands global state, a dedicated design is needed. `Map.copyOf(concurrentMap)` is not a transactional operation that snapshots the entire `Map` at a single instant.

Even when creating a copy from a plain `ArrayList`, you must still ensure the source-reading phase is not mutated in violation of its contract. An unmodifiable result cannot fix an invalid data-capture step.

## 7. Publishing Unmodifiable Versions via a Coordinated Reference

When data is mostly read, another model is to never update in place a version that has already been handed to readers. Writers build the next version and then swap the reference used to publish the current version.

Readers acquire the reference once and continue using that exact version:

```text
Current reference ──> new version
Existing reader   ──> old version remains intact
```

Structural unmodifiability enables reading a stable version. The reference publication mechanism coordinates visibility and version swapping across threads. These two responsibilities do not replace each other.

Publication can be organized with a lock, a `volatile` field in an appropriate design, or an `AtomicReference`. If multiple writers need to compute a new version from the current one, simply calling `get` followed by a separate `set` does not combine the whole update atomically.

### Experiment: Atomic Version Swapping

Save to `PublishedImmutableVersionsDemo.java`.

```java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

public class PublishedImmutableVersionsDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicReference<Map<String, Integer>> current =
                new AtomicReference<>(Map.of("count", 0));
        Map<String, Integer> oldVersion = current.get();

        Runnable update = () -> {
            for (int i = 0; i < 200; i++) {
                current.updateAndGet(previous -> {
                    Map<String, Integer> next = new HashMap<>(previous);
                    next.put("count", previous.get("count") + 1);
                    return Map.copyOf(next);
                });
            }
        };
        Thread first = new Thread(update);
        Thread second = new Thread(update);
        first.start();
        second.start();
        first.join();
        second.join();

        Map<String, Integer> latest = current.get();
        System.out.println("oldVersionCount=" + oldVersion.get("count"));
        System.out.println("latestVersionCount=" + latest.get("count"));
        try {
            latest.put("count", -1);
        } catch (UnsupportedOperationException e) {
            System.out.println("latestPut=UnsupportedOperationException");
        }
        System.out.println("oldVersionStill=" + oldVersion.get("count"));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 PublishedImmutableVersionsDemo.java
java PublishedImmutableVersionsDemo
```

Stdout:

```text
oldVersionCount=0
latestVersionCount=400
latestPut=UnsupportedOperationException
oldVersionStill=0
```

Each thread performs 200 updates. `updateAndGet` combines reading the current version, computing the candidate, and updating the reference under the method's atomic contract, so after both threads finish, the value is 400. [Javadoc AtomicReference.updateAndGet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html#updateAndGet(java.util.function.UnaryOperator))

Each candidate is built using a local `HashMap`, modifying that local copy, and converting it with `Map.copyOf`. There is no in-place mutation of a published `Map`.

`oldVersion` still holds `count=0`, while `latest` has `count=400`. Calling `put` on `latest` is rejected. Both keys and values in the example are immutable (`String` and `Integer`), so there is no mutable object value hidden inside a version.

### The Version Computation Function May Be Retried

When updates contend, `updateAndGet` may re-apply the computation function. Therefore, that function must have no external side effects.

Creating a local `Map` in the example is appropriate: if the candidate is discarded, no external data has been mutated. Do not put actions inside the function that send external requests, record an event that must happen only once, or increment a shared variable while assuming the function is always called exactly once per successful update.

This differs from a normal business method call that a code reader might assume runs only once.

### Fetch the Same Version for Related Reads

If an operation needs to read two fields belonging to the same configuration state, fetch the current reference once and read both fields from that fetched version.

Calling `current.get()` separately before each field can yield different versions if a writer has just published a new version. Each individual reference fetch being valid does not mean multiple consecutive fetches automatically belong to a single shared read transaction.

The example intentionally keeps `oldVersion` and `latest` as two separate references to make version boundaries clear. Do not use `Thread.sleep` to infer that writers have finished; the `join` calls guard when the final result is evaluated.

### The Cost Does Not Disappear; It Shifts to Updates

Creating a full copy on every update incurs copying and object-allocation overhead. This model can be a good fit when readers need a stable version and updates are relatively infrequent, but it is not the default optimal choice for a large `Map` that is modified continuously.

The example uses a single-entry map to verify correctness, not to benchmark performance. When data is large, you must consider version size, update frequency, retention of old versions, and how unused versions are reclaimed.

## 8. Unmodifiable Copies Still Have Limits at the Element Level

A `List.copyOf` copy does not automatically create new objects for each element. Nor does `Map.copyOf` deep-copy all keys and values.

Save to `ShallowImmutableCopyDemo.java`.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class ShallowImmutableCopyDemo {
    static final class MutableTag {
        private String text;

        MutableTag(String text) {
            this.text = text;
        }
    }

    public static void main(String[] args) {
        MutableTag tag = new MutableTag("before");
        List<MutableTag> source = new ArrayList<>(List.of(tag));
        List<MutableTag> copiedList = List.copyOf(source);
        Map<String, MutableTag> copiedMap = Map.copyOf(Map.of("tag", tag));

        source.add(new MutableTag("later"));
        tag.text = "after";
        System.out.println("sourceSize=" + source.size());
        System.out.println("copiedListSize=" + copiedList.size());
        System.out.println("copiedListText=" + copiedList.get(0).text);
        System.out.println("copiedMapText=" + copiedMap.get("tag").text);

        try {
            copiedList.add(new MutableTag("extra"));
        } catch (UnsupportedOperationException e) {
            System.out.println("copiedListAdd=UnsupportedOperationException");
        }
        try {
            List.copyOf(Arrays.asList("A", null));
        } catch (NullPointerException e) {
            System.out.println("nullListElement=NullPointerException");
        }

        Map<String, String> withNull = new HashMap<>();
        withNull.put("key", null);
        try {
            Map.copyOf(withNull);
        } catch (NullPointerException e) {
            System.out.println("nullMapValue=NullPointerException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ShallowImmutableCopyDemo.java
java ShallowImmutableCopyDemo
```

Stdout:

```text
sourceSize=2
copiedListSize=1
copiedListText=after
copiedMapText=after
copiedListAdd=UnsupportedOperationException
nullListElement=NullPointerException
nullMapValue=NullPointerException
```

After adding an element to the source:

- The source has two elements.
- `copiedList` still has one element.

This is structural independence.

However, changing `tag.text` to `"after"` makes both `copiedListText` and `copiedMapText` print `after`. They still reference the same `MutableTag`. The experiment runs these mutations on a single thread to observe reference relationships; it does not make mutating a shared field thread-safe.

Therefore, if multiple readers need a deeply immutable data version, you must also consider the element model:

- Use appropriate immutable value types.
- Create separate output objects if you need to sever references to source objects.
- Copy or protect mutable nested structures.
- Do not expose a setter or a reference that allows mutation across the published data boundary.

No collection wrapper can automatically infer the right deep-copying strategy for arbitrary business objects.

### Null and Ordering Policies Must Also Be Checked

The `List.copyOf`, `Set.copyOf`, and `Map.copyOf` factories reject `null` elements, keys, or values according to their respective contracts. The program verifies the null `List` element and null `Map` value cases. [Javadoc List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html), [Javadoc Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html), [Javadoc Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

Changing the data model can change these other policies as well:

| Choice | Nulls | Ordering to note |
| --- | --- | --- |
| Wrapper over a backing collection | Follows the backing collection's capability | Follows the backing collection's contract |
| `ConcurrentHashMap` | Rejects null keys and null values | Does not guarantee insertion-order iteration |
| `CopyOnWriteArrayList` | Allows null elements | List order; iterator reads a snapshot |
| `List.copyOf` | Rejects null elements | Preserves the source's iteration order |
| `Set.copyOf` | Rejects null elements | Does not guarantee preserving the source's iteration order |
| `Map.copyOf` | Rejects null keys and null values | Does not guarantee preserving the source's iteration order |

For example, replacing a backing `Map` that allows `null` with `ConcurrentHashMap` or `Map.copyOf` changes more than just access coordination. You must verify valid data and API contracts.

Similarly, when you need a `Map` snapshot that iterates in insertion order, do not assume `Map.copyOf` preserves that order. You can build a separate ordered backing structure and wrap it as unmodifiable, while ensuring no backing mutation path is exposed and the capture step remains protected.

## 9. Choosing a Model Based on Invariants and Update Patterns

| Scenario | Potentially suitable model | What must be specified |
| --- | --- | --- |
| Many independent per-key updates | Concurrent collection and appropriate atomic operations | Per-key atomic scope; value state |
| A group of operations needing the same shared state | Locked wrapper or owning class with an explicit lock policy | The monitor and all read/write paths that need coordination |
| Read-heavy configuration data replaced by version | Unmodifiable versions published properly | Element immutability, reference swapping, and reading a single version |
| List traversed frequently, updated rarely | Snapshot-policy collection such as copy-on-write if cost fits | Write cost and readers not seeing newer updates |
| Long computation accepting data at a point in time | Capture a valid snapshot, then process the snapshot | Consistency during capture and depth of copying |
| Returning output data to a read-only caller | Unmodifiable copy or output data model | Whether element objects are shared |

These choices must be tested against real requirements. Not every `Map` has a global invariant, and not every read needs to see the latest data. The clearer the requirements, the easier it is to design the coordination scope.

### Error-Prone Conclusions

| Wrong conclusion | What to distinguish |
| --- | --- |
| Having "concurrent" in the name means every multi-step algorithm is correct | Specific atomic operations differ from arbitrary call sequences |
| Using a wrapper means you only need to avoid mutating the raw data directly | Compound operations and traversal must also be guarded |
| Wrapping with `unmodifiable` gives you a snapshot | A view can still track changes to the backing structure |
| `copyOf` automatically locks the entire source while reading | The data-capture step needs its own consistency policy |
| A stable `copyOf` result must represent a single point-in-time source state | Stability afterward differs from atomicity when reading the source |
| `CopyOnWriteArrayList` and `ConcurrentHashMap` share the same traversal policy | A snapshot iterator differs from weakly consistent traversal |
| A thread-safe `Map` protects every setter on its values | Values with shared mutable state need their own policy |
| An unmodifiable list means all elements are deeply immutable | A structural copy can still hold the same element references |
| Calling `AtomicReference.get` then `set` separately is an atomic compound update | Requires an appropriate atomic operation or an external policy |
| The `updateAndGet` function is always called exactly once | It may be re-applied under contention |
| Calling `current.get` multiple times automatically gives the same version | If version consistency is needed, fetch the reference once |
| `synchronized` on `ConcurrentHashMap` blocks all its operations | Does not share the same monitor contract as `synchronizedMap` |
| Changing models only affects speed | Null handling, ordering, traversal policy, and mutability may also differ |

A design can combine multiple models across different boundaries. For instance, a writer component uses a concurrent `Map` for independent updates; another process builds aggregated data under a defined policy and publishes an unmodifiable result. However, the boundary integration must have an explicit contract—it does not appear automatically just because each individual component is called thread-safe.

## 10. Practice: Identifying the Right Guarantees

### Exercise 1: View or Copy?

From a synchronized `List` containing `[A, B]`, create a `Collections.unmodifiableList` and a `List.copyOf` following the proper locking policy. Then add `"C"` to the source through the wrapper. Do the two reads produce the same result?

**Check:**

No. The view reads `[A, B, C]`, while the copy keeps `[A, B]`. Both reject `add` operations through the result's API, but they have different relationships to the source.

### Exercise 2: Incrementing with Two Calls on ConcurrentHashMap

A piece of code uses `get` then `put` to increment a counter. Can you skip coordinating the compound operation just because the `Map` is concurrent?

**Check:**

No. Two threads can compute from the same old value. For a per-key counting requirement, you can use `merge` as shown in the program, or choose another operation with an appropriate contract.

This still does not solve invariants spanning multiple keys or external systems.

### Exercise 3: Seeing the Old Version or the Updated Version?

An iterator of `CopyOnWriteArrayList` is created when the list contains `[1, 2, 3]`. Another thread adds `4` and finishes before the old iterator is traversed. Must the old iterator see `4`?

**Check:**

No. It reads the snapshot from when it was created, so in the verified scenario it still sees `[1, 2, 3]`. To read the new state, obtain a new traversal according to the class contract.

### Exercise 4: Calling Map.copyOf on a Updating Map

A concurrent `Map` holds multiple related values. After `Map.copyOf`, the result is unmodifiable. Can you immediately conclude that all values in it belong to a single global point in time?

**Check:**

No. You must check how the source was read. A stable output can be constructed from values observed at different times if the source does not provide an atomic snapshot.

If a unified version is needed, guard the data-capture step or use a version-publication mechanism that meets the requirement.

### Exercise 5: An Unmodifiable Map Containing MutableTag

A `Map` is created with `Map.copyOf`, but the value is a `MutableTag` also used elsewhere. When another part of the code mutates a field of `tag`, is the value read through the `Map` guaranteed to keep the old state?

**Check:**

No. The `Map` blocks replacing mappings through its API; it does not deep-copy the tag object. You need immutable element data, an appropriate copy, or a separate coordination policy.

### Exercise 6: Publishing Versions with AtomicReference

A requirement needs to read two parameters belonging to the same version. Which approach is clearer: calling `current.get()` before each parameter, or fetching a version variable once and reading both from that variable?

**Check:**

Fetch one version reference and read both from it. If a writer swaps the reference between two `get` calls, two separate reads can come from two different versions.

`AtomicReference` coordinates the reference, but the application must still define the scope of a consistent read.

### Exercise 7: Side Effects in updateAndGet

A new-version computation function both builds a `Map` and records an external event. Can you assume that event occurs exactly once per successful update?

**Check:**

No. The computation function may be re-applied under contention. Keep the computation function free of external side effects and design event recording with a separate appropriate mechanism.

### Exercise 8: Stating Full Conditions for a Choice

Choose one of the three requirements:

1. Multi-key counters updated independently.
2. A pair of data items that must be read and modified as a single state.
3. A configuration set replaced by version, where readers must hold one version throughout a task.

For your choice, specify the structure or coordination model, the atomic scope, the traversal policy, and the level of element protection.

A satisfactory answer does not just name a class. It must explain what state readers are allowed to observe, where writers may mutate, and why related updates do not break the chosen invariant.
