# Why Fail-Fast Is Not a Synchronization or Correctness Mechanism

A loop that finishes without throwing `ConcurrentModificationException` only tells you that that specific run did not throw that exception. It does not answer three critical questions: whether threads are accessing the data under a safe protocol, which dataset the loop actually observed, and whether the result satisfies the program's requirements.

In the Java Collections Framework, **fail-fast** is the way certain iterators detect modifications incompatible with an ongoing traversal and abort by throwing an exception. This mechanism helps uncover collection misuse. To build a correct multithreaded program, you still must choose the appropriate synchronization mechanism, data-visibility rules, and atomic operations.

This lesson progresses from a single iterator in one thread to the case where multiple threads share a collection. The terms to distinguish are:

- **Traversal:** the process of using a specific iterator or spliterator to read elements.
- **Structural modification:** a change that affects the organization of the collection and the validity of the traversal; the exact criteria depend on the implementing class.
- **Synchronization:** establishing access rights and happens-before visibility relationships between threads.
- **Atomicity:** an operation that must be observed as a single unit, without competing operations interleaving between critical steps.
- **Business invariant:** a condition that the program must preserve, such as each registration ID appearing only once.
- **Diagnostics:** detecting signs of error to aid in fixing the program; a diagnostic signal does not itself enforce the conditions above.

## 1. The Actual Contract of Fail-Fast

`ConcurrentModificationException` may be thrown when an object detects a modification that is not allowed in the current situation. The word "Concurrent" in the exception name does not prove that two threads are involved: a single thread modifying a collection directly while holding an old iterator can also trigger the error.

The Javadoc explicitly states that detection is **best effort**, meaning the implementation attempts to detect it within its capabilities, with no guarantee of catching every case of unsynchronized concurrent modification. This exception must not be relied upon as a condition guaranteeing program correctness. [Java 17: ConcurrentModificationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ConcurrentModificationException.html)

The following example is an illustrative snippet inside a method, using types from `java.util`:

~~~java
List<String> names = new ArrayList<>(List.of("An", "Binh"));
Iterator<String> cursor = names.iterator();

names.add("Chi");
String next = cursor.next();
~~~

The iterator is created before `add`. The subsequent `next` call uses a traversal that has been invalidated by a structural modification of the `ArrayList`. With the implementation verified in the program below, `next` throws `ConcurrentModificationException`.

That same addition, if performed before creating the iterator, means the new iterator starts on the new state. What must be analyzed is the relationship between modification and **iterator lifetime**, not the method name `add` in isolation.

Two common inferences are both invalid:

~~~text
ConcurrentModificationException occurred
    => two threads must be accessing the collection at the same time.

No ConcurrentModificationException occurred
    => the collection was used safely and the result is correct.
~~~

The first inference is wrong because a single thread can cause the error. The second inference is wrong because the detector does not check every kind of bug, every operation, or every business requirement.

## 2. Why Detection Is Useful but Not Sufficient

Suppose the list of commands to process is `[A, B, C]`. After processing `A`, some code adds `D` to the list. The old iterator holds its current position, structural assumptions, and internal state from the earlier traversal.

If it continued as if nothing had changed, the program would have to answer difficult questions on its own: should `D` be read, which element do indices now correspond to, and should a removed element still be processed? A fail-fast iterator does not try to invent a dynamic traversal policy for all of these situations. When it detects a state mismatch, it reports an error so the programmer can redesign how the collection is used.

The value of the mechanism lies in surfacing the error close to the operation using the iterator. However:

- It does not prevent the addition of `D` that already happened.
- It does not roll back the work done to process `A`.
- It does not decide whether `D` belongs to the current processing pass or the next one.
- It does not know whether the application requires exactly-once processing, at-least-once processing, or processing only a snapshot of the initial input.
- It does not choose the appropriate lock or collection type on the programmer's behalf.

Those are design decisions that precede catching an exception.

## 3. The Counter Model: Understand It to Read Errors, Not as a Synchronization Protocol

Many classes extending `AbstractList` use the `modCount` field to support structural change detection. `AbstractList` allows subclasses to opt in or out of this mechanism; it is not a requirement that every collection use the same counter. [Java 17: AbstractList.modCount](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html#modCount)

You can picture a traversal using the following model. This is an explanatory model, not code to replace the JDK's iterator:

~~~text
Collection tracks changes: revision = 8
Iterator remembers:        expected = 8

A tracked modification occurs:
    revision = 9

At an iterator check point:
    if revision differs from expected, report an error
~~~

The remembered number is not a copy of all the data. Nor does comparing two equal values perform a semantic verification of every element.

In OpenJDK 17's `ArrayList`, the iterator keeps an expected value and checks it along certain code paths. `hasNext` uses the current cursor position and size, whereas `next` has a modification-check path. Therefore, you cannot deduce from the name "fail-fast" that every call checks immediately. This is an implementation detail that explains observed behavior, not a contract applicable to all iterators. [OpenJDK 17 Source: ArrayList.Itr](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/ArrayList.java)

### 3.1. A Counter Is Not a Lock

Comparing two numbers does not force a writing thread to wait. Another thread can still modify the data in the window between the check and the data access. If accesses already lack synchronization, merely reading the counter does not establish a complete data-publication relationship.

Conversely, a shared lock defines which code may enter a protected region and when. Under the Java Memory Model, unlocking a monitor happens-before a subsequent lock on the same monitor with respect to data visibility. `volatile` and the utilities in `java.util.concurrent` also have their own contracts. Comparing an ordinary numeric field has none of these effects. [JLS 17, Sections 17.1 and 17.4.5](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html)

Even the idea of "making the counter `volatile`" does not solve the problem: seeing a new number does not make checking and then reading multiple elements an atomic unit. You need to design an access protocol, not just make the change marker more visible.

### 3.2. Reverting Content Does Not Restore an Old Iterator

Start with `[A, B]`, create an iterator, add `TEMP`, and then remove `TEMP`. The final list is `[A, B]` again. That does not mean the iterator has become valid again.

This scenario distinguishes **content equality at two points in time** from **no modification during that interval**. Change tracking is not a comparison between the final list and an initial copy. The full program will show that the old iterator still reports an error.

You should never read or mutate internal counters to "re-validate" an iterator. Applications must follow the API and modification policy of the collection in use.

### 3.3. "Same Size" Is Not a General Rule

For `ArrayList`, replacing a reference at an index using `set` is not considered a structural modification according to the class specification. Meanwhile, other structural management operations can affect traversal in ways that cannot be evaluated solely by comparing `size` before and after. [Java 17: ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

Consequently, checking `oldSize == list.size()` is not a substitute for the iterator contract. Nor should you generalize `ArrayList`'s `set` rule to every collection, every view, or every algorithm.

## 4. Three Layers That Must Be Evaluated Independently

| Layer to Evaluate | Specific Question | What Does Fail-Fast Answer? |
|---|---|---|
| Access safety | Are there conflicting unsynchronized reads/writes? | Does not verify the overall inter-thread protocol. |
| Traversal contract | Which modifications does this iterator allow? | Can detect some violations according to the class's policy. |
| Requirement correctness | Are items skipped, duplicated, mis-summed, or violating uniqueness? | Has no knowledge of invariants or business meaning. |

A program can satisfy the first layer yet violate the second. For example, all operations sit inside the same lock block, yet the very thread holding the lock calls `list.add` and then continues using the old iterator.

Another program might use individual thread-safe methods yet violate the third layer: two threads both check "not present yet" and then both add the same ID. If no traversal occurs in that section, there is no reason to expect an iterator detector to intervene.

To prove correctness, you must specify **what must always remain true**, **which operations preserve it**, and **how competing accesses are coordinated**. The absence of an exception does not replace those three parts.

## 5. A Program Verifying the Boundaries

The `FailFastBoundaryDemo.java` file below is a standalone program using APIs available in Java 17. It was compiled with `javac --release 17` and run on OpenJDK Zulu 24.0.2; this is not a claim that it was executed on a Java 17 JVM.

The parts that intentionally break the iterator contract are confined to cases with a clear ordering. The program does not create an unconstrained read/write race on an `ArrayList` and then assert that the race's stdout must be fixed.

The multithreaded section uses a `CyclicBarrier` to force both threads to finish checking before adding. List accesses there go through `Collections.synchronizedList`. Thus, the duplicate result can be explained by the execution schedule of individually valid calls, without relying on internal structural corruption.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class FailFastBoundaryDemo {
    @FunctionalInterface
    interface Action {
        void run() throws Exception;
    }

    static String outcome(Runnable action) {
        try {
            action.run();
            return "completed";
        } catch (ConcurrentModificationException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    static void runPair(Action action) throws Exception {
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Runnable task = () -> {
            try {
                action.run();
            } catch (Throwable ex) {
                failure.compareAndSet(null, ex);
            }
        };
        Thread first = new Thread(task, "first");
        Thread second = new Thread(task, "second");
        first.setDaemon(true);
        second.setDaemon(true);
        first.start();
        second.start();
        first.join(5000);
        second.join(5000);
        if (first.isAlive() || second.isAlive()) {
            first.interrupt();
            second.interrupt();
            throw new AssertionError("Pair did not finish");
        }
        if (failure.get() != null) {
            throw new AssertionError("Task failed", failure.get());
        }
    }

    public static void main(String[] args) throws Exception {
        List<String> direct = new ArrayList<>(List.of("A", "B"));
        Iterator<String> directIt = direct.iterator();
        direct.add("C");
        System.out.println("direct = " + outcome(() -> directIt.next()));

        List<String> removed = new ArrayList<>(List.of("A", "B", "C"));
        Iterator<String> removeIt = removed.iterator();
        while (removeIt.hasNext()) {
            if (removeIt.next().equals("B")) {
                removeIt.remove();
            }
        }
        System.out.println("iterator-remove = " + removed);

        List<String> guarded =
                Collections.synchronizedList(new ArrayList<>(List.of("P", "Q")));
        synchronized (guarded) {
            Iterator<String> guardedIt = guarded.iterator();
            guarded.add("R");
            System.out.println("guarded-direct = "
                    + outcome(() -> guardedIt.next()));
        }

        List<String> restored = new ArrayList<>(List.of("A", "B"));
        Iterator<String> restoredIt = restored.iterator();
        restored.add("TEMP");
        restored.remove("TEMP");
        System.out.println("restored-content = " + restored);
        System.out.println("restored-iterator = "
                + outcome(() -> restoredIt.next()));

        List<String> replaced = new ArrayList<>(List.of("old", "tail"));
        Iterator<String> replaceIt = replaced.iterator();
        replaced.set(0, "new");
        System.out.println("set-next = " + replaceIt.next());

        StringBuilder box = new StringBuilder("safe");
        List<StringBuilder> boxes = new ArrayList<>(List.of(box));
        Iterator<StringBuilder> boxIt = boxes.iterator();
        box.append("?");
        System.out.println("element-next = " + boxIt.next());

        List<String> shortened = new ArrayList<>(List.of("A", "B"));
        Iterator<String> shortIt = shortened.iterator();
        System.out.println("shortcut-first = " + shortIt.next());
        shortened.remove("B");
        System.out.println("shortcut-hasNext = " + shortIt.hasNext());

        List<String> ordered = new ArrayList<>(List.of("L", "R"));
        Iterator<String> orderedIt = ordered.iterator();
        AtomicReference<Throwable> writerFailure = new AtomicReference<>();
        Thread writer = new Thread(() -> {
            try {
                ordered.add("S");
            } catch (Throwable ex) {
                writerFailure.set(ex);
            }
        }, "ordered-writer");
        writer.setDaemon(true);
        writer.start();
        writer.join(5000);
        if (writer.isAlive()) {
            writer.interrupt();
            throw new AssertionError("Writer did not finish");
        }
        if (writerFailure.get() != null) {
            throw new AssertionError("Writer failed", writerFailure.get());
        }
        System.out.println("after-join = " + outcome(() -> orderedIt.next()));

        List<Integer> duplicate =
                Collections.synchronizedList(new ArrayList<>());
        CyclicBarrier checked = new CyclicBarrier(2);
        runPair(() -> {
            boolean absent = !duplicate.contains(42);
            checked.await(5, TimeUnit.SECONDS);
            if (absent) {
                duplicate.add(42);
            }
        });
        System.out.println("separate-calls = " + duplicate);
        System.out.println("unique-invariant = " + (duplicate.size() == 1));

        List<Integer> unique =
                Collections.synchronizedList(new ArrayList<>());
        CyclicBarrier ready = new CyclicBarrier(2);
        runPair(() -> {
            ready.await(5, TimeUnit.SECONDS);
            synchronized (unique) {
                if (!unique.contains(42)) {
                    unique.add(42);
                }
            }
        });
        System.out.println("whole-operation = " + unique);
        System.out.println("unique-invariant-fixed = " + (unique.size() == 1));

        List<String> jobs = new ArrayList<>(List.of("A", "B", "C"));
        List<String> delivered = new ArrayList<>();
        boolean interrupted = false;
        Iterator<String> jobIt = jobs.iterator();
        try {
            while (jobIt.hasNext()) {
                String job = jobIt.next();
                delivered.add(job);
                if (job.equals("A")) {
                    jobs.add("D");
                }
            }
        } catch (ConcurrentModificationException ex) {
            interrupted = true;
        }
        System.out.println("retry-caught = " + interrupted);
        System.out.println("effects-before-retry = " + delivered);
        for (String job : jobs) {
            delivered.add(job);
        }
        System.out.println("effects-after-retry = " + delivered);

        CopyOnWriteArrayList<String> snapshots =
                new CopyOnWriteArrayList<>(List.of("U", "V"));
        Iterator<String> snapshotIt = snapshots.iterator();
        snapshots.add("W");
        List<String> snapshotRead = new ArrayList<>();
        snapshotIt.forEachRemaining(snapshotRead::add);
        System.out.println("snapshot-iterator = " + snapshotRead);
        System.out.println("snapshot-current = " + snapshots);
    }
}
~~~

Compile and run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 FailFastBoundaryDemo.java
java FailFastBoundaryDemo
~~~

Stdout from the verification run:

~~~text
direct = ConcurrentModificationException
iterator-remove = [A, C]
guarded-direct = ConcurrentModificationException
restored-content = [A, B]
restored-iterator = ConcurrentModificationException
set-next = new
element-next = safe?
shortcut-first = A
shortcut-hasNext = false
after-join = ConcurrentModificationException
separate-calls = [42, 42]
unique-invariant = false
whole-operation = [42]
unique-invariant-fixed = true
retry-caught = true
effects-before-retry = [A]
effects-after-retry = [A, A, B, C, D]
snapshot-iterator = [U, V]
snapshot-current = [U, V, W]
~~~

Specifically, the line `shortcut-hasNext = false` is an observation on the tested implementation and matches how `ArrayList.Itr` is written in the referenced OpenJDK 17 source. Another implementation or version might check at a different point. Do not write applications that rely on this contract violation staying silent.

The five-second timeouts help the verification program report an error if coordination stalls; they are not used to decide which thread wins. `Thread.sleep` plays no part in shaping the execution schedule. Results are printed only after the corresponding threads have finished; errors in worker threads are propagated to the main thread rather than ignored.

## 6. Reading Each Group of Results

### 6.1. A Single Thread Is Enough to Trigger the Exception

`direct` creates an iterator and then adds an element via the list itself. The subsequent `next` call throws `ConcurrentModificationException`. No secondary thread exists in this scenario.

Conversely, `iterator-remove` removes `B` through the active iterator itself, leaving `[A, C]`. This is a modification path supported by `ArrayList`'s iterator. For the `Iterator` interface in general, `remove` is an optional operation that must be called after `next` and cannot be called twice for the same returned element. Never assume every iterator supports removal. [Java 17: Iterator.remove](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#remove())

Replacing `removeIt.remove()` with `removed.remove("B")` changes the path used to modify the collection. Even though the intent is still to remove `B`, the contract with respect to the active iterator is different.

If there are two iterators on the same `ArrayList`, a valid modification through the first iterator does not automatically update the expected state of the second iterator. The right to modify belongs to the traversal performing the operation, not as a blanket exemption for every active traversal.

### 6.2. Proper Locking Still Does Not Allow Arbitrary Modification During Traversal

In `guarded-direct`, a single thread holds the monitor of the synchronized list wrapper, creates an iterator, and adds `R`. The add succeeds because Java monitors are reentrant: the thread currently holding the lock can re-enter code guarded by the same lock.

The lock keeps other threads following the same protocol outside the protected region. It does not turn `guarded.add("R")` into `guardedIt.add`, nor does it make the previously created iterator forget the modification history.

This situation often arises through callbacks: a loop holding a lock invokes a handler for each element, and that handler adds to or removes from the collection. When inspecting a stack trace, trace through indirectly invoked functions as well, not just the loop body.

Choose one of the approaches that makes sense for your problem:

- Remove via the iterator if that operation is supported and appropriate.
- Collect intended changes and apply them after the traversal finishes.
- Iterate over a safely taken snapshot, accepting that the snapshot reflects the point in time it was captured.
- Choose a data structure whose traversal policy allows the required kind of updates.

Each option changes how data is processed, so re-check your application's requirements.

### 6.3. Changes Do Not Necessarily Produce a Fail-Fast Signal

`set-next = new` occurs because replacing a reference in this list via `set` does not invalidate the iterator under the mechanism being examined. The iterator returns the new value at the unread position. This does not make concurrent `set` and `get` calls across multiple threads on an `ArrayList` safe.

`element-next = safe?` illustrates another boundary: the collection holds a reference to a `StringBuilder`. Mutating that object's own contents is not an addition or removal of elements in the collection. An iterator is not a monitor for every field of every object it might return.

The `StringBuilder` mutation example uses only one thread. When moving to multiple threads, element-level thread safety must be designed separately; a thread-safe collection does not automatically make every object stored inside it thread-safe.

`shortcut-hasNext = false` demonstrates a check point that may never be reached. After retrieving `A`, the program removes `B` directly; the iterator's cursor position then matches the new size. The observed `hasNext` path returns `false`, so a typical loop can terminate without calling `next` again.

The lesson from this observation is **never to use silence as a certificate of correctness**, not to learn a list-mutation trick to dodge exceptions.

### 6.4. Two Threads Do Not Require Overlapping Access

In `after-join`, the iterator is created before starting the writer thread. The writer thread adds `S` and terminates; the main thread waits with `join` and only then calls `next`.

No structural read of the list by the main thread occurs concurrently with the add in this example. Even so, the old iterator is used after a modification that did not go through it and throws an exception.

The happens-before relationship after a thread finishes via `join` publishes the writer thread's results to the main thread. The exception here does not prove `join` lacks synchronization; it reflects an iterator lifetime spanning across an incompatible modification. [JLS 17.4.5: Thread.start and Thread.join](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5)

This is also why you should not mechanically translate the exception name into the conclusion "two statements executed at the exact same instant."

### 6.5. No Exception, Yet the Invariant Still Fails

`separate-calls` has a controlled execution schedule as follows:

~~~text
First thread:  contains(42) -> false
Second thread: contains(42) -> false
Both pass the barrier
First thread:  add(42)
Second thread: add(42)
Result: [42, 42]
~~~

The order of the two adds can swap, but both add the same value, so the result is still two `42`s. Each individual call through the wrapper is protected on its own. What is unprotected is **the compound check-then-add decision**.

Here, no iterator is created, no `ConcurrentModificationException` occurs, and `unique-invariant = false`. Failure is demonstrated by the desired data condition, not by waiting for an exception.

The `whole-operation` section places both `contains` and `add` inside a shared `synchronized` block. The thread entering second re-checks inside the protected region and sees the element is already present. Hence only `[42]` remains. The barrier is placed **before** the lock block; waiting for both threads inside the same lock could cause one thread to wait for the other while preventing it from entering.

### 6.6. An Exception Does Not Roll Back Side Effects Already Emitted

In the `jobs` section, element `A` has already been added to `delivered` before `D` is added to the source list and the iterator detects the error. Therefore, after catching the exception:

~~~text
effects-before-retry = [A]
~~~

When the program naively retries from the beginning, `A` is added a second time:

~~~text
effects-after-retry = [A, A, B, C, D]
~~~

`delivered` models an observable side effect: sending a notification, writing a file, updating another system, or incrementing metrics. The iterator's exception does not undo those effects. Nor does a `synchronized` block provide a rollback mechanism.

You cannot make a "catch and retry" approach correct simply by limiting the retry count. You must define the input of a processing pass, how completed work is identified, idempotency of the operation, and a transaction mechanism if the problem requires one.

### 6.7. A Non-Fail-Fast Iterator Can Be a Valid Choice

`CopyOnWriteArrayList` provides an iterator backed by a snapshot of the array at the time the iterator was created. Subsequent changes to the list do not update the array that iterator uses; mutating operations through the iterator are unsupported. [Java 17: CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)

Accordingly, the program prints:

~~~text
snapshot-iterator = [U, V]
snapshot-current = [U, V, W]
~~~

The absence of an exception here conforms to a well-defined traversal policy. However, if the application requirement is "the traversal must also process `W` that was just added," then the stale snapshot does not satisfy that requirement. Even when choosing a thread-safe collection, you still must verify its data-observation semantics.

## 7. Choosing the Right Mechanism for Your Requirements

### 7.1. Data Owned by a Single Thread

The easiest approach to reason about in many cases is restricting ownership: a temporary list is built and traversed by only one thread. When data needs to be handed off to another thread, transfer the result using a proper publication mechanism and clearly specify which side may still mutate it.

Restricting ownership does not eliminate self-modification bugs while using an iterator. For selective removal within a single thread, you can use an iterator that supports `remove` or an appropriate filtering API.

The following snippet is inside a method and requires `java.util.ArrayList` and `java.util.List`:

~~~java
List<Integer> values = new ArrayList<>(List.of(1, 2, 3, 4));
values.removeIf(value -> value % 2 == 0);
// After the call: values contains [1, 3].
~~~

This is an update call executed by the collection according to its API contract, not permission for the predicate itself to add to or remove from the same source. With ordinary collections, you also must not assume `removeIf` provides coordination with other threads.

### 7.2. Needing a Stable Traversal Over a Mutable Collection

If using a `Collections.synchronizedList` wrapper, traversing via an iterator, spliterator, or stream must occur while holding the wrapper's lock, per the API contract. All accessing parties must follow the same synchronization path. [Java 17: Collections.synchronizedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List))

An illustrative example inside a method, using types from `java.util`:

~~~java
List<Integer> shared =
        Collections.synchronizedList(new ArrayList<>(List.of(10, 20, 30)));

int total = 0;
synchronized (shared) {
    for (int value : shared) {
        total += value;
    }
}
// total is 60 for the initial data above.
~~~

The lock block must encompass both creating and using the iterator, not just the `iterator()` call. Another party holding a reference to the underlying `ArrayList` and mutating it directly breaks the protocol even if the loop locked the wrapper.

For map views or sublists, you must identify the root mutex required by the API. Locking an arbitrary object with the same contents does not coordinate with writers.

Even when holding the right lock, avoid letting callbacks mutate the structure through a path incompatible with the active iterator. Also consider lock hold duration, multi-lock acquisition order, and potentially blocking work inside the loop body.

### 7.3. Needing to Release the Lock Before Long Processing

You can take a copy under the lock, then process the copy outside:

~~~java
List<Integer> snapshot;
synchronized (shared) {
    snapshot = new ArrayList<>(shared);
}

for (int value : snapshot) {
    // Process the data from this snapshot.
}
~~~

This snippet continues using `shared` declared in the previous example. The copy is a separate list; adding or removing elements in the source after copying does not change the members in the copy.

This is a decision about the point of observation. It does not guarantee that the data is still current when results are sent out. If elements are mutable objects, both lists can still hold the same references; copying the list does not deep-copy the entire object graph.

More importantly, taking the copy itself must be safe. Writing `new ArrayList<>(unsafeSource)` while another thread mutates `unsafeSource` without coordination does not magically produce a consistent snapshot.

### 7.4. Needing Traversal Concurrent With Updates

You can choose a concurrent collection with an appropriate traversal policy. For example, `ConcurrentHashMap`'s iterator does not throw `ConcurrentModificationException` due to map updates and is weakly consistent; it does not promise a point-in-time snapshot of the entire map. The iterator is still designed to be used by one thread at a time. [Java 17: ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

This may suit monitoring metrics that tolerate changing data. It may not suit exporting a report where every row must belong to the same version of the data. Stronger guarantees require additional design or a different model.

`CopyOnWriteArrayList` is suitable when traversals far outnumber modifications and the copy cost on updates is acceptable. The snapshot is only stable with respect to the members/references in the iterator's array; mutability inside the elements themselves remains a separate question.

Do not judge the quality of two iterator types by which one throws more exceptions. Match the traversal policy against the needs of the data consumer.

### 7.5. Needing Key-Level Atomic Operations

For concurrent maps, use APIs with an appropriate per-key contract such as `putIfAbsent`, conditional `replace`, or update methods guaranteed by the specific class. Writing two calls—`get` followed by `put`—still leaves a window for other operations to interleave. [Java 17: ConcurrentMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html)

A standalone illustrative example inside a method:

~~~java
java.util.concurrent.ConcurrentMap<String, String> registrations =
        new java.util.concurrent.ConcurrentHashMap<>();

String previous = registrations.putIfAbsent("id-7", "Lan");
boolean created = previous == null;
// In this empty-initialized example: created is true.
~~~

If a rule requires updating multiple keys, two collections, or both a collection and an external system, a single-key atomic operation does not protect the entire rule.

Similarly, if the data represents a unique set, a `Set` with an appropriate concurrent contract may express the requirement more directly than a list plus a separate check. Choosing the structure must go hand in hand with the requirements and supported operations.

## 8. "Fixes" That Only Mask Symptoms

### 8.1. Catching and Ignoring the Exception

~~~java
try {
    // Iterate and process.
} catch (java.util.ConcurrentModificationException ex) {
    // Ignore.
}
~~~

This snippet illustrates an anti-pattern, not a complete program. It turns an observable failure into a truncated run that looks like a success. If the method returns partial results, the caller may not know that data was missed.

You may catch the exception at an appropriate boundary to log diagnostics or mark the run as failed. That is different from treating the bug as fixed and continuing to return results as normal. Resources must still be closed using the appropriate resource-management construct.

### 8.2. Switching to an Index Loop to Stop the Error

~~~java
for (int index = 0; index < list.size(); index++) {
    consume(list.get(index));
}
~~~

The snippet above assumes `list` and `consume` already exist. It does not create a fail-fast iterator, yet the `size` and `get` calls remain separate steps. If elements are removed, indices can shift and data can be skipped or read inconsistently; if multiple threads access it without coordination, the synchronization bug remains.

Changing the loop style is only worthwhile when the new algorithm actually has a proper modification contract and protection. Seeing fewer exceptions is not itself an improvement in correctness.

### 8.3. Making Threads Sleep to "Avoid Collisions"

Adding delays only alters the execution schedule on a few runs. It does not prove that the writer thread has finished or that writes have been published via the required happens-before relationship.

When you need to wait for an event, use a coordination utility with a clear contract such as `join`, a latch, or a future suited to the task. In tests, use barriers or latches to control rendezvous points; do not turn arbitrary wait times into a correctness argument.

### 8.4. Putting `volatile` on the Collection Reference Variable

A `volatile List<?>` reference can participate in publishing an object or swapping a data snapshot under a proper protocol. It does not make add/remove operations inside the same `ArrayList` atomic, nor does it protect mutable elements.

If you choose a model that replaces the entire data snapshot, you must specify whether a published snapshot may continue to be mutated and which snapshot a reader uses throughout an operation. Do not mix the idea of swapping snapshots with multiple threads freely mutating the same instance.

### 8.5. Renaming the Mechanism "Fail-Safe"

Java documentation describes iterators by concrete contracts such as fail-fast, snapshot, or weakly consistent. "Fail-safe" is often used informally in conversation, but that label alone is not enough to deduce visibility policies, removal support, or atomicity. The package documentation clearly describes the weakly consistent iterator group and the characteristics of concurrent collections. [Java 17: java.util.concurrent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html)

When reading a guide that uses this term, translate it into concrete questions: when does the iterator capture data, which updates can appear, is `remove` supported, and can the same iterator be shared across threads?

## 9. Streams and Spliterators Still Need a Data-Source Contract

Replacing a `for-each` loop with `stream().forEach(...)` does not automatically add a lock around the source. Streams require behavioral parameters not to interfere improperly with the source during execution; for concurrent sources, the source's policy may allow updates, yet you still must understand the expected result. [Java 17: Stream Non-Interference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html#NonInterference)

Because stream processing can be deferred until the terminal operation, you must distinguish when the pipeline is constructed from when the source is traversed. If using a synchronized wrapper and relying on external locking, locking only while creating the stream and then executing the terminal operation outside the lock does not protect the traversal.

A `Spliterator` also has its own source-binding policy and interference detection. For bulk traversal operations, detection may be deferred to a check point after invoking the consumer on multiple elements. Therefore, an exception does not prove that no side effects have occurred. [Java 17: Spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html)

`parallelStream` adds the possibility of multiple tasks processing concurrently. It does not fix an unsafe source and does not automatically make an external result list a valid concurrent write target. When aggregating results, use a reduction or a collector with an appropriate contract while ensuring the source is used properly.

## 10. Investigating Errors and Verifying Correctness Conditions

When you encounter `ConcurrentModificationException`, trace from the object being traversed to every path that modifies it:

1. Identify the actual runtime implementation class, wrappers, and views, rather than looking only at declared types like `List` or `Map`.
2. Identify where the iterator was created and whether it is retained across multiple calls or across an update.
3. Look for direct modifications, modifications through aliases, through a view's backing collection, and through callbacks.
4. Distinguish modifications by the same thread from modifications by another thread; the exception name does not give you the answer.
5. Check the locking protocol, data publication, and iterator lifetime as separate concerns.
6. Write down the business outcome that must be preserved before changing how you iterate or switching collections.

Useful diagnostic information includes timestamps, thread names, collection identity, update operations, and processing-pass boundaries. Note that logging the contents of a collection while it is being mutated without coordination can itself become an unsafe traversal.

In tests, verify meaningful conditions directly:

- Exactly the expected set of job IDs from the selected input.
- No ID processed twice when exactly-once is required.
- Correct final totals or registration counts.
- Failed updates reported clearly rather than interpreted as partial success.
- Snapshot results distinguished from live-data results.

Running a test many times may uncover more failing schedules, but it does not prove no other schedules exist. A test that always expects `ConcurrentModificationException` from an unsynchronized race can itself encode a false assumption. Combine API contracts, reasoning about access ordering, and tests with controlled schedules.

## 11. Self-Check Exercises

### Exercise 1 — Exception in a Single Thread

A method creates an iterator on an `ArrayList`, calls a helper method that adds an element to that same list, and then continues calling `next`. There are no other threads. Can `ConcurrentModificationException` be ruled out?

**Answer:** No. You must examine how the helper modified the structure outside the iterator's path. Thread count does not determine iterator validity.

### Exercise 2 — Locked Yet Still Failing

All code is inside `synchronized (list)` on a synchronized wrapper. Inside the loop, the element handler calls `list.remove`. The author concludes the JVM failed to respect the lock because an exception still occurred. Where is this conclusion wrong?

**Answer:** A lock only coordinates parties using the same monitor; it does not prevent the lock-holding thread from re-entering and mutating the list itself. You must choose an update path compatible with the iterator or separate the update phase from the traversal phase.

### Exercise 3 — Restored Content

Create an iterator on `[1, 2]`, add `3`, then remove `3`, and continue using the old iterator. Can safety be proven by comparing the final list to the initial list?

**Answer:** No. Comparing two states does not say that no modification occurred in between. In the verified `ArrayList` example, the old iterator reports a modification even though the final content matches the initial content.

### Exercise 4 — No Error, Yet Duplicate IDs

Two threads use a `synchronizedList`, each calling `contains` and then `add` if absent. The system runs without exceptions, yet duplicate IDs appear. Should you add a `catch` block or change the operation boundary?

**Answer:** Change the operation boundary or the data structure. You must protect the entire check-then-add decision with a shared protocol, or use an atomic operation that directly expresses the requirement. Catching an exception does not prevent two decisions from both acting on the "not present" state.

### Exercise 5 — Does a Snapshot Meet the Requirement?

A `CopyOnWriteArrayList` iterator is created before a new listener is registered. The current notification pass does not invoke the new listener and throws no exception. Is this a collection bug?

**Answer:** You cannot conclude that. That is the snapshot behavior of the iterator. You must define whether a listener added during notification should participate in the current pass or the next pass; if the requirement differs, choose or design a corresponding mechanism.

### Exercise 6 — Retrying After External Side Effects

A loop has already sent two notifications before the iterator throws an error. The author catches the exception and reruns the entire loop. Is each notification guaranteed to be sent only once?

**Answer:** No. The exception does not undo the two previously sent notifications. You must design idempotency, task identifiers, or an appropriate transaction; merely switching iterators or capping retry attempts does not satisfy the requirement.

### Exercise 7 — Elements Mutate While the List Does Not

A list holds balance objects. No elements are added or removed, yet one thread mutates balance fields while another thread reads them. Does the absence of exceptions prove safety?

**Answer:** No. You must examine the synchronization contract of the balance objects and the fields being read/written. Tracking collection structure does not track every piece of state inside elements.

### Exercise 8 — Negative Testing

A test spawns two threads freely reading and writing an `ArrayList` and runs a million times without seeing `ConcurrentModificationException`. Can that result be used to remove locks in production code?

**Answer:** No. The test neither establishes a synchronization guarantee nor proves all execution schedules. Identify conflicting accesses, data contracts, and invariants to preserve; then choose the proper protocol and verify the outcome with intentionally coordinated schedules.

When evaluating a change to a collection, the decisive question is: **what mechanism protects the operations and observation semantics the problem requires?** Fail-fast helps surface misuse; designing ownership, synchronization, and invariants is what forms the basis for reasoning about correctness.
