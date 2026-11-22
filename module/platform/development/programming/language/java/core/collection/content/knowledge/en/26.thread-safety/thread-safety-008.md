# Data Visibility and the Limits of Publishing Read-Only Collections

## 1. Read-only answers the mutation-permission question, not the visibility question

Suppose one execution thread creates a list, populates it with data, and hands the reference to another thread. The receiving side only needs to read that list. The phrase "read-only collection" sounds safe enough, yet in practice there are several distinct responsibilities.

| Responsibility | Question to answer |
| --- | --- |
| Mutation permission via API | Can the receiver call `add`, `remove`, `set`, or `put`? |
| Relationship to the source | Is there an independent structure, or merely a view over a still-mutable source? |
| Data publication | By what mechanism does the receiving thread obtain the reference and the initialized state? |
| Subsequent changes | Does anyone still mutate the backing structure or element objects? |
| Version consistency | Do related reads belong to the same version? |

`Collections.unmodifiableList(source)` blocks mutation operations through the view. It does not automatically turn every reference assignment to that view into a cross-thread publication operation.

`List.copyOf(source)` produces a result that does not track subsequent structural changes to the source. Nor does it design how the current reference is swapped when multiple versions need to be shared.

**Data visibility** concerns which values a thread is guaranteed to observe from another thread's writes under the Java Memory Model. It is distinct from:

- Permission to mutate a collection.
- Atomicity of an increment or a multi-step sequence.
- Whether multiple reads belong to the same business state.

For example, two atomic reference reads can each be valid yet observe two different versions. A list that forbids modification can also contain a mutable element object.

This lesson uses standalone Java 17 programs to verify each boundary. The results rely on explicit coordination; uncoordinated code snippets are used only to analyze the limits of guarantees and must not be assigned an imagined stdout.

## 2. Publication must rely on memory model guarantees

Publishing a collection means making its reference and the state needed for reading usable by another thread.

To explain this, Java defines the **happens-before** relation. If a write precedes a read under the appropriate relation, the program has a basis for ordering and visibility, rather than relying on guesses about CPU caches or processor speed.

A typical publication model looks like this:

```text
Publishing thread                     Reading thread

Create structure
Write elements
Finalize state to be published
       ↓
Coordinated publication point ───────> Coordinated receipt point
                                              ↓
                                      Read published state
```

Commonly used rules include writing and reading a `volatile` field, releasing and acquiring the same monitor, `Thread.start`, completing a thread and calling `join`, or concurrent APIs with corresponding memory contracts. [Java Language Specification on happens-before](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5)

There is no need to describe every instance of data visibility as "flushed to RAM." The guarantee lies in the memory model and API contracts; the JVM may implement them in different ways as long as it preserves the permitted behavior.

### Non-tearing references do not imply sufficient publication guarantees

Reading or writing an object reference is atomic in the sense that it does not produce half a reference from one write combined with half a reference from another write. However, that property alone does not establish the publication relationship required for a data-sharing protocol.

The snippet below only illustrates a design lacking a protocol; it is not a program with guaranteed results:

```java
// Ordinary shared field, not volatile.
static List<String> shared;

// One thread executes:
shared = Collections.unmodifiableList(new ArrayList<>(List.of("ready")));

// Another thread reads shared on its own without a coordination point.
```

Merely seeing the name `unmodifiableList` is not enough to explain when the other thread will observe the new reference. If there are special initialization guarantees from `final` fields or properly constructed immutable objects, their exact scope must be analyzed; Section 6 will clarify this.

What you must not do is write a polling loop over an ordinary field, run it on one machine, see it terminate, and conclude that the protocol is always valid.

### Only the right direction and the right timing help

A `volatile` write only helps publish actions that precede it under the corresponding relation. It does not automatically include subsequent mutations in the same publication.

Similarly, releasing lock A does not automatically coordinate with a reader acquiring lock B. Having the `synchronized` keyword in both places is not enough if both sides do not use the same policy.

## 3. Experiment: publishing a list via volatile

Save as `VolatileReadOnlyPublicationDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class VolatileReadOnlyPublicationDemo {
    private static volatile List<Integer> published;

    public static void main(String[] args) throws InterruptedException {
        int[] observed = new int[2];
        Thread reader = new Thread(() -> {
            List<Integer> local;
            while ((local = published) == null) {
                Thread.onSpinWait();
            }
            observed[0] = local.size();
            observed[1] = local.stream().mapToInt(Integer::intValue).sum();
        });
        Thread publisher = new Thread(() -> {
            List<Integer> building = new ArrayList<>();
            building.add(10);
            building.add(20);
            building.add(30);
            published = Collections.unmodifiableList(building);
        });

        reader.start();
        publisher.start();
        publisher.join();
        reader.join();
        System.out.println("seenSize=" + observed[0]);
        System.out.println("seenSum=" + observed[1]);
        try {
            published.add(40);
        } catch (UnsupportedOperationException e) {
            System.out.println("publishedAdd=UnsupportedOperationException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 VolatileReadOnlyPublicationDemo.java
java VolatileReadOnlyPublicationDemo
```

Stdout:

```text
seenSize=3
seenSum=60
publishedAdd=UnsupportedOperationException
```

The publishing thread creates `building`, adds 10, 20, and 30, and only then assigns the view to the `volatile` field `published`.

The reading thread waits until it reads a non-`null` reference, holds it in the local variable `local`, and then reads the size and computes the sum. The data initialization writes occur before the `volatile` write; reading the `volatile` field establishes the coordination point for the reader.

The data-visibility guarantee comes from timely publication through that field. The guarantee blocking `add` comes from the `unmodifiableList` wrapper. Those are two different parts of the contract.

In this program, the backing list is not modified after publication and no mutation path is exposed to the reader. The `Integer` elements are also immutable. Therefore, the reader can process the data after obtaining the reference without another party continuing to change the backing structure.

### volatile on a reference does not make each element volatile

Declaring `volatile List<T>` applies to the field holding the reference. It does not automatically attach a `volatile` policy to the slots of the list, the size counter, or every field inside each `T`.

If a party continues calling `building.add` or mutating element objects after the assignment to `published`, a separate policy is required for those changes. One proper publication does not make all future updates safe.

### onSpinWait is not what creates the visibility guarantee

`Thread.onSpinWait()` only hints to the runtime that the code is waiting in a loop; it may help how the spin loop is executed. The program remains valid regarding its publication mechanism if that call is removed, because the checked variable is `volatile`. [Javadoc Thread.onSpinWait](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#onSpinWait())

Do not add `onSpinWait` to a loop reading an ordinary field and treat the protocol as fixed. In application code, you can use a latch, future, or queue when they express waiting and data handoff more clearly than a busy-wait loop.

### join protects the final result evaluation

The `observed` array is written only by the reader thread, and the main thread reads it only after `reader.join()` completes. The `join` calls make the timing of printing the results meaningful.

That does not replace the relationship between the publishing thread and the reading thread while the data pipeline is in use: in this example, the primary publication relationship remains the `volatile` field `published`.

## 4. Changes after publication require a new coordination relationship

Suppose a read-only view has been assigned to a `volatile` field, and the backing list is subsequently modified. The reader must not rely on the old publication to infer that all new modifications have been coordinated.

There are two separate issues:

1. The view still shares the backing data.
2. Subsequent writes need their own visibility and consistency rules.

### Experiment for changes after an explicit coordination point

Save as `ChangesAfterPublicationDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public class ChangesAfterPublicationDemo {
    private static volatile List<String> published;

    public static void main(String[] args) throws InterruptedException {
        List<String> backing = new ArrayList<>(List.of("before"));
        published = Collections.unmodifiableList(backing);
        List<String> copied = List.copyOf(backing);
        CountDownLatch referenceCaptured = new CountDownLatch(1);
        CountDownLatch changeFinished = new CountDownLatch(1);
        String[] observed = new String[4];

        Thread reader = new Thread(() -> {
            List<String> view = published;
            referenceCaptured.countDown();
            try {
                changeFinished.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            }
            observed[0] = Integer.toString(view.size());
            observed[1] = view.get(0);
            observed[2] = Integer.toString(copied.size());
            observed[3] = copied.get(0);
        });
        reader.start();

        referenceCaptured.await();
        backing.set(0, "after");
        backing.add("later");
        changeFinished.countDown();
        reader.join();

        System.out.println("viewSize=" + observed[0]);
        System.out.println("viewFirst=" + observed[1]);
        System.out.println("copySize=" + observed[2]);
        System.out.println("copyFirst=" + observed[3]);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ChangesAfterPublicationDemo.java
java ChangesAfterPublicationDemo
```

Stdout:

```text
viewSize=2
viewFirst=after
copySize=1
copyFirst=before
```

The reading thread captures the `view` reference and then signals the `referenceCaptured` milestone. The main thread waits for that milestone, modifies the backing list, and only then signals `changeFinished`. The reading thread resumes reading the structure only after `await` succeeds.

Thus, the output `viewSize=2` and `viewFirst=after` has a clear explanation:

- The view is not a copy, so it still reads from the backing source.
- The latch provides the coordination relationship for writes occurring after the assignment to `published`.

Actions before `countDown` have a happens-before relationship with actions after a corresponding successful `await`, according to the latch contract. [Javadoc CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)

This program does not prove that a read-only view automatically guarantees visibility of future updates. On the contrary, it intentionally introduces a separate coordination mechanism so the reads have a valid contract.

`copied` was created using `List.copyOf` when the source still contained `before`. It retains the structure `[before]` even though the source now contains `[after, later]`. In this example, the elements are immutable `String` instances, so there is no shared mutable element state.

### A latch in an example is not just a delay tool

When designing a multithreaded experiment, a latch can both orchestrate ordering and establish memory relationships. Do not add a latch and then use the result to conclude that a version without the latch has the same guarantees.

Similarly, if you use `join` to wait for the writer to finish before reading, `join` itself provides a completion relationship. A correct result after `join` does not prove that a concurrent, uncoordinated read is also always correct.

In this example, the initial data was also created before `reader.start()`; that matters for initial publication as well. What is being verified is the writes performed after the reader has already captured the view, and those are coordinated via `changeFinished`.

### volatile is not a lock for the backing source

Reading a `volatile` field and then iterating over an `ArrayList` while another party modifies it can still violate the source's iteration contract. A properly published reference and a source protected during use are two separate conditions.

If you want to keep modifying the same structure, you can use a locking policy or an appropriate concurrent data structure. If you want a stable version for reading, create a proper copy and do not modify the published version.

## 5. Individual reads with valid visibility can still mix two versions

A `volatile` field or an `AtomicReference` helps coordinate access to a reference. It does not automatically combine multiple reference fetches into a single transactional read.

Suppose version 1 has the label `old`, and version 2 has the label `new`. If a reader obtains the version number from a first read and the label from a second reference read, it can combine "version 1, label new."

This is not necessarily a memory-visibility bug. Each read may observe a valid published version, but the reading algorithm chose two different points in time.

Save as `CapturedVersionReadDemo.java`.

```java
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class CapturedVersionReadDemo {
    record Settings(int version, List<String> labels) {
        Settings {
            labels = List.copyOf(labels);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicReference<Settings> current =
                new AtomicReference<>(new Settings(1, List.of("old")));
        CountDownLatch firstRead = new CountDownLatch(1);
        CountDownLatch replacementReady = new CountDownLatch(1);
        String[] observed = new String[4];

        Thread reader = new Thread(() -> {
            Settings captured = current.get();
            observed[0] = Integer.toString(captured.version());
            firstRead.countDown();
            try {
                replacementReady.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            }
            observed[1] = current.get().labels().get(0);
            observed[2] = Integer.toString(captured.version());
            observed[3] = captured.labels().get(0);
        });
        reader.start();

        firstRead.await();
        current.set(new Settings(2, List.of("new")));
        replacementReady.countDown();
        reader.join();

        System.out.println("separateReadVersion=" + observed[0]);
        System.out.println("separateReadLabel=" + observed[1]);
        System.out.println("capturedVersion=" + observed[2]);
        System.out.println("capturedLabel=" + observed[3]);
        System.out.println("latestVersion=" + current.get().version());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 CapturedVersionReadDemo.java
java CapturedVersionReadDemo
```

Stdout:

```text
separateReadVersion=1
separateReadLabel=new
capturedVersion=1
capturedLabel=old
latestVersion=2
```

The latch forces the reader to capture `captured` before the main thread swaps the reference. After the swap completes, the reader is allowed to proceed.

The first two lines combine values from two points in time:

```text
separateReadVersion=1
separateReadLabel=new
```

The next two lines read from the same `captured` instance:

```text
capturedVersion=1
capturedLabel=old
```

The current version is already 2, yet the local variable still holds the reference to version 1. `Settings` has fixed record fields and a constructor that copies the list using `List.copyOf`; the labels are `String` instances. There are no in-place mutations to the old version.

`AtomicReference` provides a way to access and update a reference variable with atomic operations. In this example, it serves as the publication point for the current version; latches are also used to create a deterministic observation schedule for the experiment. [Javadoc java.util.concurrent.atomic](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/package-summary.html)

### Rule for capturing one version per task

If a requirement calls for multiple version-consistent reads:

1. Fetch the current version reference once.
2. Hold it in a local variable.
3. Read the related data from that exact version object.
4. Do not mix in data from a newly fetched version unless the contract allows it.

This requires the version itself to have an appropriate level of stability. If it contains mutable elements, holding the same reference alone is not enough to get a deep snapshot.

Multiple writers also introduce another requirement. Performing `get` followed by a separate `set` to compute a new version does not automatically form an atomic compound update. An appropriate update operation or a protection policy covering the entire computation and publication step is needed.

## 6. final has its own initialization guarantees, but does not freeze all data

You should not reduce the publication problem to "anything without `volatile` is wrong." Java also provides guarantees for `final` fields, class initialization, and other coordination mechanisms.

### Local final variables and final fields have different roles

A local variable `final List<T>` cannot be reassigned after initialization. That property does not create a publication channel to another thread and does not make the list deeply immutable.

An instance `final` field has additional initialization semantics in the Java Memory Model. When an object is properly constructed—without allowing the `this` reference to escape to another thread before the constructor finishes—the `final` field values carry special initialization guarantees. These guarantees also extend to the initialized state of objects reachable through those fields. This is a special guarantee for initialized state once another thread observes a properly constructed object, even when passing the reference does not use ordinary synchronization; it does not create a mechanism that forces a spin loop to observe every reference replacement. [Java Language Specification on final fields](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5)

Snippet illustrating class design, not a standalone program:

```java
final class Catalog {
    private final List<String> names;

    Catalog(List<String> source) {
        this.names = List.copyOf(source);
    }

    List<String> names() {
        return names;
    }
}
```

Here we must assume that reading `source` during the copy is valid. The object does not expose itself in the constructor, the list forbids structural modification, and the elements are immutable `String` instances.

Because of the `final` guarantee, you must not conclude that an ordinary reference field used to swap the current `Catalog` will automatically have an update and notification protocol. The initialization guarantee does not force a spin loop over an ordinary field to observe every reference replacement.

Nor does it protect subsequent modifications to a still-mutable backing collection or to unprotected fields of elements.

### static final via class initialization is a valid way to share

Example of declaring a field in a class:

```java
private static final List<String> DEFAULT_NAMES = List.of("A", "B");
```

Class initialization has JVM-level coordination mechanisms. When used properly, this kind of unchanging static data does not need a separate `volatile` field just for class users to read the initialized default list. [Java Language Specification on class initialization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2)

However, if you replace the elements with objects that have setters, `static final` still does not automatically make every setter call thread-safe. It fixes the field reference and participates in the initialization contract, rather than placing a lock over the entire object graph.

### Creation before Thread.start also matters

Actions before calling `start` have a happens-before relationship with actions in the started thread. Therefore, a snapshot that is prepared, passed into a task, and followed by starting the reader thread can form a valid publication path without using an additional `volatile` field.

The remaining condition is controlling subsequent changes. If a party continues modifying the shared object, the guarantee at thread-start time does not automatically cover future modifications.

## 7. A read-only collection can still contain mutable elements

A collection that forbids adding or removing elements is not yet a deeply immutable object graph. The references inside it can still point to mutable state.

Save as `ReadOnlyListMutableCounterDemo.java`.

```java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class ReadOnlyListMutableCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        List<AtomicInteger> counters = List.of(new AtomicInteger());
        Runnable increment = () -> {
            for (int i = 0; i < 1000; i++) {
                counters.get(0).incrementAndGet();
            }
        };
        Thread first = new Thread(increment);
        Thread second = new Thread(increment);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("listSize=" + counters.size());
        System.out.println("counterValue=" + counters.get(0).get());
        try {
            counters.add(new AtomicInteger());
        } catch (UnsupportedOperationException e) {
            System.out.println("listAdd=UnsupportedOperationException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ReadOnlyListMutableCounterDemo.java
java ReadOnlyListMutableCounterDemo
```

Stdout:

```text
listSize=1
counterValue=2000
listAdd=UnsupportedOperationException
```

The list has exactly one element and forbids calling `add`. Yet that element is an `AtomicInteger`, which is designed to be updated.

Two threads each increment 1000 times, so the final value is 2000. The correctness of the increments and the value-access rules come from `AtomicInteger`, not from the outer list forbidding modification. [Javadoc AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html)

The data is prepared before starting both threads, and the main thread waits for both to finish via `join` before printing the results. There are no uncoordinated array or element reads in the final evaluation.

If you replace `AtomicInteger` with an object that has an ordinary `int` field and perform `value++` from two threads, the read-only list does not automatically protect that read-add-write sequence. The situation also has an atomicity issue, not just a data-visibility issue.

### Keys or values in a Map have similar limits

A Map that forbids changing mappings can still contain values with setters. A Set that forbids adding elements can still contain objects with mutable state.

If mutating state affects `equals`, `hashCode`, or the comparison order of keys or set elements, it can even violate the data structure's invariants. Therefore, designing stable elements is valuable for both collection correctness and cross-thread sharing.

When an API contract says "read-only," it should state clearly whether it forbids structural modification or provides a deeply immutable value. The two promises are not equivalent.

## 8. Queue handoff can provide a clear publication path

Not every protocol needs a `volatile` field and a hand-written spin loop. A `BlockingQueue` has a memory contract when one thread puts an element in and another thread takes that element out.

Actions before placing an object into the queue have a happens-before relationship with actions after another thread accesses or removes that exact element. [Javadoc BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

Save as `ReadOnlyQueueHandoffDemo.java`.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class ReadOnlyQueueHandoffDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<List<String>> channel = new ArrayBlockingQueue<>(1);
        String[] received = new String[1];
        int[] sizes = new int[2];

        Thread consumer = new Thread(() -> {
            try {
                List<String> message = channel.take();
                received[0] = message.toString();
                sizes[0] = message.size();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            }
        });
        Thread producer = new Thread(() -> {
            try {
                List<String> building =
                        new ArrayList<>(List.of("alpha", "beta"));
                List<String> message = List.copyOf(building);
                channel.put(message);
                building.add("later");
                sizes[1] = building.size();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            }
        });

        consumer.start();
        producer.start();
        producer.join();
        consumer.join();
        System.out.println("received=" + received[0]);
        System.out.println("receivedSize=" + sizes[0]);
        System.out.println("builderSizeAfterSend=" + sizes[1]);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ReadOnlyQueueHandoffDemo.java
java ReadOnlyQueueHandoffDemo
```

Stdout:

```text
received=[alpha, beta]
receivedSize=2
builderSizeAfterSend=3
```

The producer has a `building` list owned exclusively by itself:

1. Populate `alpha` and `beta`.
2. Create `message = List.copyOf(building)`.
3. Put `message` into the queue.
4. Continue modifying `building` by adding `later`.

The consumer retrieves `message` via `take`. It reads the exact list `[alpha, beta]` with size 2. The producer's own builder now has size 3, yet it does not cause `message`'s structure to change along with it.

Two guarantees combine here:

- The queue provides the publication relationship for data prior to the send step.
- The unmodifiable copy and immutable `String` elements keep the message data stable afterward.

The arrays used to record results are updated by the worker threads and then read by the main thread only after `join`. They are the result-recording slots for the example, not an unprotected concurrent reading channel.

### Sending a still-mutable view is a different contract

If you replace `List.copyOf(building)` with a `Collections.unmodifiableList(building)` view and the producer continues modifying `building` after sending, the view still uses the same backing structure.

The queue contract only publishes actions prior to inserting the element under the corresponding relation. It does not automatically forbid the sender from mutating the backing structure later, nor does it lock on behalf of the receiver throughout the read.

Another option is to transfer ownership of the structure to the receiver and commit that the sender will not touch it again. That option must be explicitly designed and followed; merely wrapping in a read-only layer does not create a transfer of ownership.

## 9. Design the data path instead of only choosing a read-only label

You can trace a collection-sharing design through the following chain:

```text
Build valid data
        ↓
Choose structure and element protection level
        ↓
Finalize the version to hand to readers
        ↓
Publish via a mechanism with a memory contract
        ↓
Readers capture the right version scope
        ↓
Any subsequent changes have their own policy
```

Questions that must be clearly answered:

| Stage | What must be clear |
| --- | --- |
| Construction | Is any party reading or mutating the same source while creating the copy? |
| Mutation limits | Is the result a view, a structural copy, or deeply immutable data? |
| Publication | What relationship allows the receiving thread to read the prepared state? |
| Reading | Does a task capture one version, or can it combine multiple versions? |
| Subsequent updates | Mutate in place under a lock, use atomic elements, or create a new version? |
| Task completion | Is a proper completion signal used when results need to be observed? |

If you choose locking, both writers and readers of the related state must use the same monitor or locking protocol. Locking on a newly created read-only wrapper does not automatically coordinate with a party locking on a different backing object.

If you choose `volatile` or an atomic reference, identify which writes precede the publication step and whether any mutations still occur afterward.

If you choose an unmodifiable version, check both nested structures and element state; a single list copy does not automatically deep-copy every object.

### Do not use elapsed time as a substitute for data visibility

`Thread.sleep` and `Thread.yield` have no synchronization semantics to force writes to be published or reads to reload an ordinary field. [Java Language Specification on sleep and yield](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.3)

Adding logging can alter scheduling or lock interactions in a program. A bug disappearing when `println` is added does not constitute proof that the data protocol is correct.

For code with a data race, do not promise a fixed wrong outcome such as "always reads 0," "always hangs," or "re-running will definitely show the bug." The limitation is the absence of required guarantees; a favorable observation does not expand Java's contract.

### Commonly confused conclusions

| Conclusion | Correction |
| --- | --- |
| If `add` cannot be called, the data is safely published | API mutation permission is distinct from cross-thread publication mechanisms |
| If a reference is assigned atomically, all state is already visible | Reference atomicity is distinct from initialization and publication relationships |
| `volatile List` makes every element automatically `volatile` | Only the reference field has that policy |
| One `volatile` write protects all future mutations of the backing list | Subsequent writes require a separate coordination relationship |
| `unmodifiableList` severs the relationship with the source | It is a view, not an independent copy |
| `copyOf` makes every element deeply immutable | It does not automatically deep-copy the object graph |
| Having `final` means no need to analyze constructors or sharing | `final` guarantees have their own construction conditions and scope |
| All read-only data must have a `volatile` field | Class initialization, `final` initialization semantics within its scope, `start`, locks, or handoff APIs also provide appropriate guarantees |
| Calling `AtomicReference.get` multiple times gives a single version | Each fetch may observe a different valid version |
| Using a latch in tests only slows down steps | A latch also establishes memory relationships that can change what is being verified |
| If reading after `join` is correct, prior concurrent reads are also correct | `join` provides a completion point; it cannot be omitted from the reasoning |
| A queue protects all mutations after sending an object | The handoff contract does not automatically protect future updates to a shared object |
| A wait loop with `sleep` or `onSpinWait` is safe on its own | There must be a variable or protocol with proper coordination semantics |
| Running many times without error means there is no data race | You must verify memory relationships, not just count successful runs |

A contract returning a read-only collection should state clearly whether the data can change from another side, whether elements can mutate, and whether the caller receives a snapshot or a view. For data used across threads, it must also describe the publication path or appropriate usage protocol.

## 10. Practice: finding the right guarantee relationship

### Exercise 1: wrapping unmodifiable and assigning to an ordinary field

One thread creates a list, wraps it with `unmodifiableList`, and assigns it to a shared non-`volatile` field. Another thread loops reading that field without a coordination point. Can you explain that the wait loop will always observe the new reference solely because the list forbids modification?

**Review:**

No. A read-only wrapper is not a notification protocol for a new reference. You must identify an appropriate publication and observation-progress guarantee, such as a `volatile` field, a shared lock, or a data-handoff API.

If there are special initialization guarantees for a properly constructed immutable object, you must distinguish them from a spin loop on an ordinary field being guaranteed to see updates.

### Exercise 2: mutating the backing list after a volatile write

A backing list is populated, published via a `volatile` field, and then modified via `set`. The reader reads that reference field only once. Does the earlier `volatile` write automatically protect the later `set`?

**Review:**

No. It does not automatically include subsequent writes in the same publication. You need a new policy for those updates, or you must not mutate the published version.

`ChangesAfterPublicationDemo` has deterministic output because it uses an additional latch for the post-publication writes.

### Exercise 3: two safe reads that see different versions

Version 1 has label `old`, and version 2 has label `new`. A reader fetches the version number and then fetches the label via two separate reads of the current reference. Why can it combine "1, new" without assuming a memory read error?

**Review:**

The first read can observe version 1, and the next read can observe version 2. Those are two valid observations at two different points in time. If a consistent state is required, fetch the reference once and read the related values from the same stable version.

### Exercise 4: final referencing a List

A class has a `final List<MutableItem>` field assigned in the constructor. After the constructor completes, another party mutates a field of `MutableItem`. Can you conclude from the `final` keyword alone that this operation is protected?

**Review:**

No. A `final` field has its own initialization guarantees when properly constructed, but it does not lock all subsequent mutations of the referenced objects. `MutableItem` state needs its own immutability or coordination.

### Exercise 5: static final default list

A class declares `private static final List<String> DEFAULTS = List.of("A", "B");` and has no mutable elements. Is it necessary to add `volatile` solely because the data is read from multiple threads?

**Review:**

It is not necessary to add it just to read default data that has been properly class-initialized. Class initialization already has a coordination contract, and the structure along with the `String` values do not change in this design.

Do not generalize this answer to another reference variable that is frequently reassigned or to elements with mutable state.

### Exercise 6: read-only on the outside, AtomicInteger on the inside

A `List.of(new AtomicInteger())` forbids adding elements. Two threads can still increment the counter inside. Why is there no contradiction?

**Review:**

The list is not structurally modified; the state of the element object is updated. `AtomicInteger` provides the contract allowing values to be incremented and read; the read-only nature of the list neither performs that nor forbids it.

### Exercise 7: queue and still-mutable backing data

A sender puts `Collections.unmodifiableList(building)` into a `BlockingQueue`, then continues modifying `building`. Can the receiver treat the message as an unchanging snapshot simply because it passed through a queue?

**Review:**

No. The queue has publication guarantees for actions prior to sending, but the view still has a shared backing list. You need an appropriate copy, a transfer of ownership, or a policy for subsequent modifications.

### Exercise 8: identifying what a verification actually proves

An example only reads an ordinary field after calling `join` on the writer, and the result is always correct. Can you remove `join` and use that same observation to claim the uncoordinated version is also safe?

**Review:**

No. `join` is part of the completion and data-visibility reasoning. Changing the coordination point changes the guarantees in use.

A good solution should point out each milestone: where the data is created, how the reference is transferred, which writes precede the publication point, which version the reader holds, and how subsequent changes are protected.
