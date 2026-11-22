# CopyOnWriteArrayList, CopyOnWriteArraySet, and Write Costs

An event listener list may be traversed thousands of times while rarely having listeners added or removed. When dispatching an event, an application often wants to use the exact set of listeners for that pass, even if another party just registered or unregistered.

`CopyOnWriteArrayList` and `CopyOnWriteArraySet` solve this kind of problem with a **copy-on-write** strategy: updates create a new version of the backing array, while traversals that already obtained the old array can continue on that version.

The benefit lies in stable reads and not needing to hold an external lock for the duration of an iterator. The cost is shifted to writers, array allocation, and how long old versions remain retained.

To use them correctly, you need to distinguish between:

- **Current collection:** the object to which elements can still be added, removed, or replaced.
- **Array version:** a state of the sequence of element references.
- **Snapshot iterator:** a traversal bound to the version at the time the iterator was created.
- **Mutable element:** the object referenced inside the array; it does not automatically become immutable.
- **Write cost:** not just reassigning a reference, but potentially including searching, copying, allocating, waiting on other writers, and garbage collection.

This lesson starts from the array model, walks through the List/Set contracts and a runnable example, and then analyzes when this cost is worth accepting.

## 1. A New Array for Writers, the Old Array for Traversal

You can picture a `CopyOnWriteArrayList<String>` like this:

~~~text
Current collection -> array V1: [A, B, C]
Iterator I1        -> array V1: [A, B, C]
~~~

When `D` is added:

~~~text
Current collection -> array V2: [A, B, C, D]
Iterator I1        -> array V1: [A, B, C]
~~~

Iterator I1 does not switch to V2 mid-traversal. An iterator created after the update can start on V2.

The `CopyOnWriteArrayList` contract specifies that iterators hold a snapshot at the time of creation, do not reflect subsequent additions, removals, or replacements, and do not throw `ConcurrentModificationException` due to those updates. [Java 17: CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)

"Not seeing new updates" here is intentional semantics, not a data visibility bug. If your application requires an in-progress traversal to immediately reflect every new registration, this snapshot policy may not be appropriate.

### 1.1. The Iterator Does Not Copy the Whole Array

In OpenJDK 17, the iterator receives a reference to the current array and holds onto it. Creating an iterator does not copy the entire sequence of elements each time.

This is why the strategy is called copy-**on-write**, not copy-on-every-read. APIs such as `toArray` have contracts to produce their own result array and may carry different costs; do not lump all read APIs into the same mechanism.

### 1.2. Writes Are Coordinated

Multiple writers do not freely mutate an array that an iterator is using at the same time. The OpenJDK 17 implementation coordinates updates with an internal lock and publishes the current array reference through a `volatile` field.

Those details help explain how new versions appear and why old arrays are not mutated. They are not a promise that every method is lock-free, wait-free, or uses the exact same algorithm across every JDK. [OpenJDK 17 Source: CopyOnWriteArrayList](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/concurrent/CopyOnWriteArrayList.java)

Readers using an iterator do not have to hold an external lock for the entire traversal. However, if many threads attempt to write continuously, there is still coordination overhead among writers.

## 2. Choosing List or Set Based on the Data

| Property | CopyOnWriteArrayList | CopyOnWriteArraySet |
|---|---|---|
| Role | Positional sequence; allows duplicates. | Set of distinct elements according to equality. |
| Indexed access | Has `get`, `set`, and List APIs. | No indexed access APIs. |
| Adding duplicates | `add` still appends another element. | `add` leaves the set unchanged and returns `false` if an equal element already exists. |
| Traversal | In list order, over the snapshot. | In insertion order, over the snapshot. |
| Mutation via iterator | Not supported. | `remove` is not supported. |
| Typical use case | Small lists, frequent traversal, rare updates. | Small sets, frequent traversal, rare updates, deduplication needed. |

`CopyOnWriteArraySet` uses a `CopyOnWriteArrayList` internally; its documentation targets sets that are usually small and where read operations vastly outnumber mutative operations. [Java 17: CopyOnWriteArraySet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArraySet.html)

It is not a `HashSet` with a lock bolted on. In particular, checking whether an element is already present typically relies on scanning the array and comparing elements, with no hash table to give the average lookup cost of a hash set.

### 2.1. Insertion Order Is Not Sorted Order

If you add `"two"` and then `"one"`, `CopyOnWriteArraySet` preserves insertion order for its iterator; it does not sort the strings.

When two threads concurrently add two different elements, the acceptance order can depend on execution scheduling. A traversal preserves the order of the version it captured, but it does not invent an undefined external business order.

### 2.2. Equality Must Be Stable

The set determines element equality according to the `Set` contract. Two objects with different references that are equal according to `equals` are not treated as two separate members. [Java 17: Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

If you mutate fields that affect an element's `equals` result after adding it, the very meaning of "no duplicates" can break. Not using a hash table does not make mutating value-based identity harmless.

Prefer immutable elements or a stable identifier key if the set is used to manage registrations.

### 2.3. Nulls and Duplicates Remain Two Separate Rules

`CopyOnWriteArrayList` accepts `null` and allows multiple equal elements. In the examples in this lesson, `CopyOnWriteArraySet` can also hold `null`, but keeps only a single null element per set semantics.

This does not generalize to other concurrent sets. For example, a set from `ConcurrentHashMap.newKeySet` does not accept null because of the underlying map contract. When switching collection types, re-check the element policy rather than only checking the "concurrent" label.

## 3. A Read-Only Iterator Does Not Make the Collection Immutable

The collection still has write methods, but the snapshot iterator is not a path for modifying the collection:

- `Iterator.remove` is not supported.
- `ListIterator.remove`, `set`, and `add` are not supported.
- Calling those methods throws `UnsupportedOperationException`.

The iterator/list iterator contract explicitly states that synchronization is not needed while traversing a snapshot, and that the mutating methods above are not supported. [Java 17: CopyOnWriteArrayList iterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html#listIterator())

Do not mechanically port the "iterate and call `iterator.remove`" pattern from `ArrayList` to `CopyOnWriteArrayList`.

You can update the collection directly if that matches the required semantics. Existing iterators continue using the old version; they do not automatically drop an element that was just removed from the current collection.

For example, suppose an iterator already includes listener L. Another party successfully removes L from the current set. The old iterator may still invoke L afterward. If the system requires that "once unregister returns, no in-flight or upcoming calls may happen," you need a separate cancellation/waiting protocol. Simply removing from the collection does not provide that strong guarantee.

## 4. A Snapshot Is a Snapshot of References

The array stores references to elements. Copying the array does not automatically deep-copy each object.

~~~text
Old array: [reference P]
New array: [reference P, reference Q]

Both can still point to the same object P.
~~~

If `P` has mutable fields, an old iterator can return `P` with its updated contents. "The old array does not change" means the positions and references in that array are stable, not that the entire object graph reachable from those references is frozen.

`String` is a convenient element type for explaining snapshots because string objects are not mutated in place. The `StringBuilder` example in the program below will make this boundary clearer.

Regarding data publication, the class provides memory-consistency guarantees for actions prior to placing an object into the collection and corresponding accesses from other threads. This does not automatically synchronize subsequent internal mutations of the element.

Therefore, two independent decisions are required:

1. How does the collection protect membership management and traversal?
2. Is the member object itself read/written safely across threads?

## 5. Adding When Absent and Batch Additions

### 5.1. contains Followed by add Is Still Two Calls

With a `CopyOnWriteArrayList`:

~~~java
if (!members.contains(name)) {
    members.add(name);
}
~~~

This snippet assumes the variables already exist. Two threads can both observe that the element is absent and then both add it. Individually thread-safe methods do not combine the entire decision into one atomic action.

Use `addIfAbsent` if you need a check-then-add operation on a `List`. For a `Set`, `add` already expresses the rule of not adding an equal element.

### 5.2. addIfAbsent Does Not Turn a List into a Set

A list that currently holds `[A, A]` will still have two `A` elements after `addIfAbsent("A")`. The method only decides on the new addition; it does not clean up existing duplicates.

If the data must always be a set, use a `Set` structure to express that requirement directly, instead of mixing regular `add` and `addIfAbsent` and hoping the `List` stays unique.

### 5.3. addAllAbsent Returns the Number of New Elements

`CopyOnWriteArrayList.addAllAbsent` appends elements not yet present in source order and returns the count of elements added. It also avoids adding duplicate equal candidates within the same batch.

For example, a list `[A, A]` receiving `[B, A, B, C]` will add `B` and `C`, return `2`, and become `[A, A, B, C]`. The old `A` elements are not removed.

### 5.4. Batch Writes Reduce Version Creation, but Do Not Eliminate All Costs

When adding multiple elements that are already prepared, a single `addAll` usually avoids creating a new destination array version for each individual element. When deduplication is needed, `addAllAbsent` or the `Set` API still incurs equality-check costs.

OpenJDK 17's `CopyOnWriteArraySet` delegates `add` to `addIfAbsent` and `addAll` to `addAllAbsent` on the underlying list. [OpenJDK 17: CopyOnWriteArraySet](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/concurrent/CopyOnWriteArraySet.java)

The source of a batch addition must also be read validly. Having a concurrent destination collection does not automatically make an unsafely mutated source collection safe.

## 6. Full Verification Program

Save the file as `CopyOnWriteCostDemo.java`. The program uses Java 17, was compiled with `javac --release 17`, and was run on OpenJDK Zulu 24.0.2; this is not a claim that it was executed on JVM 17.

Modifications from the background thread are awaited before continuing to read the old iterator so stdout is deterministic. The contended `Set` addition section uses a barrier before the `add` call. No sleep durations are used to guess thread ordering.

The last two lines only compute the **model count of old references copied**; they do not measure elapsed time, allocated bytes, or garbage collection counts.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.ListIterator;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CopyOnWriteArraySet;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class CopyOnWriteCostDemo {
    static <T> List<T> drain(Iterator<T> iterator) {
        List<T> result = new ArrayList<>();
        iterator.forEachRemaining(result::add);
        return result;
    }

    static String unsupported(Runnable action) {
        try {
            action.run();
            return "completed";
        } catch (UnsupportedOperationException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    static void complete(Thread thread, AtomicReference<Throwable> error)
            throws InterruptedException {
        thread.join(5000);
        if (thread.isAlive()) {
            thread.interrupt();
            throw new AssertionError("Thread did not finish");
        }
        if (error.get() != null) {
            throw new AssertionError("Thread failed", error.get());
        }
    }

    public static void main(String[] args) throws Exception {
        CopyOnWriteArrayList<String> names =
                new CopyOnWriteArrayList<>(List.of("A", "B", "C"));
        Iterator<String> oldNames = names.iterator();
        List<String> firstPass = new ArrayList<>();
        firstPass.add(oldNames.next());

        AtomicReference<Throwable> editError = new AtomicReference<>();
        Thread editor = new Thread(() -> {
            try {
                names.set(0, "X");
                names.remove("B");
                names.add("D");
            } catch (Throwable ex) {
                editError.set(ex);
            }
        }, "editor");
        editor.setDaemon(true);
        editor.start();
        complete(editor, editError);
        oldNames.forEachRemaining(firstPass::add);
        System.out.println("old-list-iterator = " + firstPass);
        System.out.println("current-list = " + names);
        System.out.println("new-list-iterator = " + drain(names.iterator()));

        Iterator<String> noRemove = names.iterator();
        noRemove.next();
        System.out.println("iterator-remove = " + unsupported(noRemove::remove));
        ListIterator<String> noEdit = names.listIterator();
        noEdit.next();
        System.out.println("listIterator-set = "
                + unsupported(() -> noEdit.set("Z")));
        System.out.println("listIterator-add = "
                + unsupported(() -> noEdit.add("Z")));

        CopyOnWriteArrayList<String> duplicates =
                new CopyOnWriteArrayList<>(List.of("A", "A"));
        System.out.println("addIfAbsent-existing = " + duplicates.addIfAbsent("A"));
        System.out.println("addAllAbsent-count = "
                + duplicates.addAllAbsent(List.of("B", "A", "B", "C")));
        System.out.println("list-keeps-old-duplicates = " + duplicates);

        CopyOnWriteArraySet<String> receivers =
                new CopyOnWriteArraySet<>(List.of("one", "two"));
        Iterator<String> beforeChange = receivers.iterator();
        System.out.println("set-duplicate-add = " + receivers.add(new String("one")));
        receivers.remove("one");
        receivers.add("three");
        System.out.println("old-set-iterator = " + drain(beforeChange));
        System.out.println("current-set = " + receivers);
        Iterator<String> setCursor = receivers.iterator();
        setCursor.next();
        System.out.println("set-iterator-remove = " + unsupported(setCursor::remove));

        StringBuilder payload = new StringBuilder("draft");
        CopyOnWriteArrayList<StringBuilder> payloads =
                new CopyOnWriteArrayList<>(List.of(payload));
        Iterator<StringBuilder> payloadCursor = payloads.iterator();
        payload.append("-edited");
        StringBuilder observed = payloadCursor.next();
        System.out.println("snapshot-element = " + observed);
        System.out.println("snapshot-same-object = " + (observed == payload));

        CopyOnWriteArrayList<String> nullable =
                new CopyOnWriteArrayList<>(Arrays.asList("N", null, "N"));
        CopyOnWriteArraySet<String> nullableSet = new CopyOnWriteArraySet<>(nullable);
        System.out.println("nullable-list = " + nullable);
        System.out.println("nullable-set = " + nullableSet);

        CopyOnWriteArrayList<Integer> versions = new CopyOnWriteArrayList<>(List.of(1));
        Iterator<Integer> versionOne = versions.iterator();
        versions.add(2);
        Iterator<Integer> versionTwo = versions.iterator();
        versions.clear();
        System.out.println("saved-version-one = " + drain(versionOne));
        System.out.println("saved-version-two = " + drain(versionTwo));
        System.out.println("versions-current = " + versions);

        CopyOnWriteArraySet<String> sharedSet = new CopyOnWriteArraySet<>();
        AtomicInteger accepted = new AtomicInteger();
        AtomicReference<Throwable> addError = new AtomicReference<>();
        CyclicBarrier ready = new CyclicBarrier(2);
        Runnable register = () -> {
            try {
                ready.await(5, TimeUnit.SECONDS);
                if (sharedSet.add("member")) {
                    accepted.incrementAndGet();
                }
            } catch (Throwable ex) {
                addError.compareAndSet(null, ex);
            }
        };
        Thread left = new Thread(register, "left");
        Thread right = new Thread(register, "right");
        left.setDaemon(true);
        right.setDaemon(true);
        left.start();
        right.start();
        complete(left, addError);
        complete(right, addError);
        System.out.println("concurrent-set-accepted = " + accepted.get());
        System.out.println("concurrent-set = " + sharedSet);

        CopyOnWriteArrayList<Integer> individually =
                new CopyOnWriteArrayList<>(List.of(0, 1));
        for (int value : List.of(2, 3, 4)) {
            individually.add(value);
        }
        CopyOnWriteArrayList<Integer> batched =
                new CopyOnWriteArrayList<>(List.of(0, 1));
        batched.addAll(List.of(2, 3, 4));
        System.out.println("individual-content = " + individually);
        System.out.println("batch-content = " + batched);

        long initial = 10_000;
        long additions = 1_000;
        long individualExistingCopies =
                additions * initial + additions * (additions - 1) / 2;
        System.out.println("model-individual-existing-references = "
                + individualExistingCopies);
        System.out.println("model-batch-existing-references = " + initial);
    }
}
~~~

Compile and run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 CopyOnWriteCostDemo.java
java CopyOnWriteCostDemo
~~~

Verified stdout:

~~~text
old-list-iterator = [A, B, C]
current-list = [X, C, D]
new-list-iterator = [X, C, D]
iterator-remove = UnsupportedOperationException
listIterator-set = UnsupportedOperationException
listIterator-add = UnsupportedOperationException
addIfAbsent-existing = false
addAllAbsent-count = 2
list-keeps-old-duplicates = [A, A, B, C]
set-duplicate-add = false
old-set-iterator = [one, two]
current-set = [two, three]
set-iterator-remove = UnsupportedOperationException
snapshot-element = draft-edited
snapshot-same-object = true
nullable-list = [N, null, N]
nullable-set = [N, null]
saved-version-one = [1]
saved-version-two = [1, 2]
versions-current = []
concurrent-set-accepted = 1
concurrent-set = [member]
individual-content = [0, 1, 2, 3, 4]
batch-content = [0, 1, 2, 3, 4]
model-individual-existing-references = 10499500
model-batch-existing-references = 10000
~~~

The program propagates errors from worker threads back to the main thread and checks a completion timeout. It does not ignore errors and still report contended outcomes as if they succeeded.

## 7. Interpreting the Output

### 7.1. Old and New Iterators Belong to Two Different Versions

~~~text
old-list-iterator = [A, B, C]
current-list = [X, C, D]
new-list-iterator = [X, C, D]
~~~

The old iterator read `A` before the writer thread replaced index 0, removed `B`, and added `D`. Its remaining elements still return `B, C` from that same old version.

The new iterator sees the current version `[X, C, D]`. There is no reason to expect the old iterator to switch to that version automatically.

### 7.2. Rejecting Modifications Through the Iterator

The three `UnsupportedOperationException` results for the List and the corresponding result for the Set confirm that mutation via iterators is not supported.

This is not a sign that the collection itself is unmodifiable. The program still uses `set`, `remove`, and `add` on the collection successfully. You must distinguish the capabilities of the collection from the capabilities of the traversal.

### 7.3. List Retains Existing Duplicates

~~~text
addIfAbsent-existing = false
addAllAbsent-count = 2
list-keeps-old-duplicates = [A, A, B, C]
~~~

There is no "full deduplication pass." The conditional methods only govern the elements in the new addition.

### 7.4. Removing from the Set Does Not Remove from an Already Acquired Iterator

~~~text
set-duplicate-add = false
old-set-iterator = [one, two]
current-set = [two, three]
~~~

`new String("one")` is a different object from the existing string, but equal in content, so it is not added as a second member.

After removing `one` and adding `three`, the old iterator still contains `one, two`. A notification registry must either accept or explicitly handle the fact that an already-started pass still uses the old group of listeners.

### 7.5. Mutating an Element Is Not Mutating the Array

~~~text
snapshot-element = draft-edited
snapshot-same-object = true
~~~

The iterator holds a reference to the same `StringBuilder`. Appending `-edited` happens in a single thread in this example, so it only demonstrates that the snapshot is not deep; do not use it to infer that `StringBuilder` is safe under concurrent modification by multiple threads.

### 7.6. Acquired Versions Live Independently of the Current Collection

~~~text
saved-version-one = [1]
saved-version-two = [1, 2]
versions-current = []
~~~

After `clear`, both iterators still retain the data of the earlier versions. Contents that are no longer members of the current version are still needed to fulfill the iterator contract.

This is both a semantic benefit and a source of memory retention cost if iterators are held for too long.

### 7.7. Set Accepts Only One Addition of the Same Element

~~~text
concurrent-set-accepted = 1
concurrent-set = [member]
~~~

Two threads concurrently attempt `add("member")`, with no removals during the test phase. One receives `true` and the other receives `false`. Uniqueness is enforced by the `Set` operation itself, not by a separate `contains` check.

If the element is removed and re-added at a later time, a subsequent `add` can succeed in that new lifecycle. The "once" result here applies to the removal-free phase of the test.

### 7.8. Same Final Result Does Not Mean Same Cost or Same Intermediate States

~~~text
individual-content = [0, 1, 2, 3, 4]
batch-content = [0, 1, 2, 3, 4]
~~~

Three `add` calls and one `addAll` call produce the same result when run sequentially. However, the first approach creates more publication steps; iterators created between those additions can observe different intermediate versions.

Choosing batch additions is also a decision about publication cadence. Do not switch to batching purely for optimization without checking whether readers need to see each step.

## 8. Where Does the Write Cost Come From?

### 8.1. Copying the Reference Array

Suppose the current array has `n` elements. An actual addition typically has to allocate a destination array large enough and copy the old references over.

For a single append at the end under this model, the number of old references that must be copied is proportional to `n`. Unlike a regular `ArrayList` that keeps spare capacity so many appends just write into empty slots, a COW write must leave intact the array version that readers may still be using.

The element objects themselves are not necessarily cloned. Copying `n` references is different from deep-copying `n` large objects.

### 8.2. Many Individual Additions Cause Total Cost to Grow Rapidly

Starting with `n` elements and adding `m` elements one by one, under the model of copying the array for each addition, the number of old references transferred is:

~~~text
n + (n + 1) + ... + (n + m - 1)
= m*n + m*(m - 1)/2
~~~

With `n = 10,000` and `m = 1,000`:

~~~text
10,499,500 old references copied according to the model.
~~~

If the entire batch of `1,000` elements is already available and added in one call to a non-empty destination array, the old references that need to be transferred for that expansion are `10,000`. In addition, there is work on the input data and new elements.

These two numbers are an analytical model for the stated conditions, not actual allocation measurements across every JVM; they exclude array header bytes, reference sizes, intermediate source buffers, and locking overhead.

The program only prints this formula. Do not use a loop lasting a few milliseconds to claim one collection is faster by some exact factor.

### 8.3. Allocation and Garbage Collection

New arrays require memory. When old versions are no longer referenced, they can be reclaimed by the garbage collector. A high rate of array creation increases allocation volume and reclamation work, even when the final dataset size is small.

System cost can show up as write latency, update throughput, memory pressure, or GC pauses. Counting only the final number of elements does not capture the amount of work that took place.

Do not assign a specific byte count per element without accounting for JVM configuration, reference size, and actual object layout.

### 8.4. Writers Must Coordinate

If multiple threads update concurrently, beyond copying there is time spent waiting for a coordinated write turn. Increasing the number of writer threads does not allow copies on the same collection to run independently and merge automatically.

This is why read/write ratio alone is not enough to decide. You need to know the absolute number of writes and the level of contention. A million reads per second do not make tens of thousands of copies of a huge array per second free.

### 8.5. Not Every Write-Intent Call Copies the Same Amount

Cases that do not change the contents may avoid creating a new array. For example, adding an already-present element with `addIfAbsent` can finish after the check; OpenJDK 17 also has an optimization branch in `set` when the reference is identical.

`clear` can publish an empty array rather than copying all elements into another full-sized array. However, old versions may still be retained by active iterators.

Therefore, saying "every write call copies exactly `n` elements" is too strong. The right way to reason is to identify the operation, whether an actual change occurs, the version size, and the implementation in question. General cost models do not replace contracts or measurements.

## 9. Cost of Retaining Old Versions

In OpenJDK 17, an iterator holds a field referencing the snapshot array. As long as the iterator is kept alive, that array and the elements it references can remain reachable to the garbage collector.

Practical consequences:

- Removing an element from the current collection is not guaranteed to free that object immediately.
- Holding multiple iterators from multiple write waves can keep multiple different arrays alive.
- Finishing traversal while keeping the iterator object around for a long time can continue holding the old array under this implementation.
- A heavy element, or one holding indirect resources, can remain referenced even after it is no longer in the current version.

Do not confuse this with a guaranteed memory leak in the library. It is a consequence of a reader still holding a version that the contract allows it to read. Manage the lifetimes of iterators, streams, spliterators, or tasks that hold snapshots appropriately.

The garbage collector does not promise "the old array is collected as soon as `remove` returns." The example program does not measure or claim memory reclamation timing.

## 10. Heavy Reads Also Have Different Cost Profiles

| Common Operation | How to Think About Cost |
|---|---|
| `get(index)` on List | Indexed access on the read's array; typically constant time with respect to element count. |
| Full iterator traversal | Proportional to the number of elements in the snapshot; does not copy the whole array per iterator step. |
| `contains`, value lookup | May have to scan the array and invoke `equals` many times. |
| Successful addition or removal | Typically involves searching/checking and creating a new array version. |
| Batch addition | Can reduce destination version creations, but still needs to read the source and process each candidate. |
| Comparing two sets or batch deduplication | Can involve many comparisons; does not inherently provide hash-table performance. |

Especially with `CopyOnWriteArraySet`, "very heavy reads" requires asking what kind of reads. Traversing a small set many times is very different from checking membership by key on a set of millions of elements.

An expensive `equals` method, or one that depends on state being mutated, also affects both timing and correctness of membership checks.

## 11. Limitations Not to Overlook

### 11.1. size Followed by get Can Still Span Two Versions

~~~java
if (!items.isEmpty()) {
    use(items.get(0));
}
~~~

This is an illustrative snippet assuming `items` is a `CopyOnWriteArrayList` and `use` already exists. Between the two calls, another thread can call `clear`. The List being thread-safe does not guarantee that this sequence of calls uses the same version; `get(0)` may no longer be a valid index.

If you need to traverse a stable group of elements, use a snapshot iterator instead of combining multiple `size/get` calls and assuming they belong to one array.

Similarly, an index loop that repeatedly reads `size` and `get` across multiple calls does not automatically carry iterator snapshot semantics.

### 11.2. subList Is a View, Not an Independent Snapshot

`CopyOnWriteArrayList.subList` returns a view backed by the original list. The documentation specifies that the semantics of the view become undefined if the backing list is structurally modified through any path other than that view. [Java 17: CopyOnWriteArrayList.subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html#subList(int,int))

Do not keep a `subList` and assume it has the same update-isolation guarantees as a snapshot iterator. If you need a stable slice of data, choose an extraction approach with the appropriate contract instead of treating every view as a snapshot.

### 11.3. Not Every Method Follows Iterator Rules

Guaranteeing that an iterator is not broken by structural updates does not mean every callback passed to every method is allowed to arbitrarily perform nested modifications on the collection.

Operations such as `removeIf`, `replaceAll`, or `sort` have their own mechanisms and contracts; in the implementation, some work runs inside the write-coordination region. Keep predicates/transformers short and avoid nested updates or waiting on another party that needs to write to the same collection.

A snapshot iterator traversing and an algorithm producing an updated version are two different contexts.

### 11.4. No Cross-Collection Transactions

Updating a listener list and an auxiliary metadata map are two separate actions. A COW iterator only pins the reference sequence of that collection itself; it does not simultaneously pin another map or each listener's internal state fields.

If an event must use data synchronized across multiple structures, you need a shared version model or a broader protocol.

## 12. When Should You Consider Using It?

Copy-on-write is often worth considering when:

- The collection is usually small or moderate, with acceptable copy costs.
- Traversals clearly outnumber updates and the absolute number of updates is low.
- Stable traversal is needed without holding external locks across listener callbacks.
- It is acceptable for an already-started pass to use old members.
- Elements have state suitable for safe reading or are managed separately.

Good examples might be a list of handlers registered rarely, a read-heavy set of configuration rules, or a small set of event listeners. Always verify against actual size and load.

Revisit the choice when:

- The dataset is large and writes are frequent or arrive continuously one element at a time.
- It is used as a log buffer, work queue, or accumulator for individual results of a parallel job.
- High-frequency membership lookup by key on a large collection is needed.
- Readers must immediately reflect every removal/addition.
- Tasks hold onto old snapshots for very long periods.

There is no fixed read/write percentage threshold that holds for every program. Size, read operation type, writes per second, and snapshot lifetime all matter.

## 13. Where Do Nearby Alternatives Fit?

| Primary Need | Option to Consider |
|---|---|
| Frequently modified list owned by a single thread | Regular `ArrayList`. |
| Protecting an entire traversal/update block with a shared lock | Synchronized wrapper or external lock with a clear protocol. |
| Large set with frequent adds/removes/lookups, weakly consistent traversal acceptable | Set from `ConcurrentHashMap.newKeySet`. |
| Ordered set of keys/elements with frequent updates | Appropriate concurrent skip-list structure. |
| Updating an entire configuration as immutable versions | Build a new configuration instance and publish the version reference. |
| Receiving and processing work in queue fashion | A `Queue` matching producer/consumer, blocking, and capacity needs. |

With the `Collections.synchronizedList` wrapper, traversal requires synchronizing on the wrapper per its contract. That is a different trade-off from holding a snapshot: it may block writers during traversal, but avoids creating an array version on every update as COW does. [Java 17: Collections.synchronizedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List))

A set from `ConcurrentHashMap` has updates and lookups backed by the underlying map, and its iterator has a different policy. Do not swap collections just because both are thread-safe while ignoring whether the iterator is a snapshot or weakly consistent. [Java 17: ConcurrentHashMap.newKeySet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#newKeySet())

Choosing a structure starts from the data contract and observation semantics first, and then measuring cost.

## 14. How to Benchmark Meaningfully

Before measuring, characterize the workload:

- Typical and peak collection sizes.
- Number of traversals, membership lookups, and updates per second.
- Ratio of updates that actually change contents versus no-op updates.
- Number of writer threads and contention level.
- Write batch size if batching is possible.
- Lifetime of iterators and element objects.
- Acceptable write latency, allocation rate, and memory limits.

Then benchmark models that meet the same semantic requirements. Comparing a snapshot iterator against an unsynchronized traversal that violates the contract is not a useful comparison. Nor should you measure only the read loop while ignoring writer and version-retention costs.

The program in this lesson is a behavioral demonstration and a model calculation; it is not a benchmark. The model helps show why costs grow, whereas choosing for a production system requires data matching its workload.

## 15. Practice Exercises

### Exercise 1 — Who Copies the Array?

A system creates very many iterators but rarely writes. Is it true that every iterator of `CopyOnWriteArrayList` must copy the entire array itself?

**Answer:** No, according to the model and implementation examined. The iterator holds a reference to the array version; new updates typically create a new array. Other read APIs such as `toArray` may have their own costs.

### Exercise 2 — Removing a Listener

An iterator has already been created, and then another party removes listener L from the Set. Can L still appear in the old traversal?

**Answer:** Yes. The iterator holds the version it captured. If cancellation must take effect for all in-flight or upcoming calls, an additional protocol is required.

### Exercise 3 — Read-Only Iterator

Why can `list.set(0, x)` be valid while `list.listIterator().set(x)` cannot be used to modify the list?

**Answer:** The collection supports updates, whereas the list iterator is a read path over a snapshot and does not support mutating methods. In addition, normal `ListIterator` preconditions would also apply, but here modification is not supported at all.

### Exercise 4 — List Uniqueness

A list already contains `[A, A]`. Do `addIfAbsent(A)` and `addAllAbsent([B,A,B])` remove one of the old `A`s?

**Answer:** No. They only prevent unnecessary new additions. The result after both calls is `[A, A, B]`.

### Exercise 5 — Deep or Shallow Snapshot?

An iterator is acquired before an element object has one of its data fields modified. Does it guarantee returning the old contents of that object?

**Answer:** No. It holds element references; that object can be the exact same object that was mutated. Element state must be designed separately.

### Exercise 6 — Writing a Thousand Elements

Why can adding elements one by one to a large COW list cost more than adding them as a batch, even when the final contents are identical?

**Answer:** Individual additions create many array versions and repeatedly copy existing elements. Batch addition can reduce the number of destination expansions, though it still needs to process the source and does not automatically eliminate deduplication costs.

### Exercise 7 — Cleared Everything, Yet Memory Does Not Drop Immediately

The collection was cleared with `clear`, yet a task is still holding an old iterator. Why might the old elements still be retained?

**Answer:** The iterator needs the snapshot array to honor the traversal contract. That array still references the elements. When they are freed depends on references being cleared and the garbage collector.

### Exercise 8 — Very High Read Ratio

A collection has one million elements, is updated several thousand times per second, and has even more reads. Is "more reads than writes" alone enough to choose copy-on-write?

**Answer:** No. You must consider the absolute amount of copying and allocation, version retention time, write contention, and reader semantics. A high ratio does not make continuously copying a huge array cheap.

Copy-on-write fits well when keeping a stable traversal is highly valuable and paying the cost on rare updates is acceptable. Evaluate size, read patterns, write cadence, and snapshot lifetime together to make the right choice for your program's data.
