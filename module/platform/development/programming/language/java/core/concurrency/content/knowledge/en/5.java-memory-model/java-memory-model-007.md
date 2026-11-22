# Safe Publication and the Risk of Reading Partially Initialized Objects in Java

> **Key Takeaway:** Properly creating an object in one thread is **not enough** for another thread to observe that object correctly. You need **safe publication**: passing the object reference to another thread through a synchronization mechanism with a *happens-before* contract. If the reference is shared too early, another thread may even observe a **partially initialized** object. `final` helps protect immutable state when an object is properly constructed, but it does not fix `this` escaping the constructor too early.

This article belongs to the **Java Memory Model** section of general Java concurrency, using Java SE mechanisms (`volatile`, `synchronized`, class initialization, `java.util.concurrent`). It does not cover bean lifecycles, dependency injection, proxies, or Spring-specific concurrency mechanisms.

## 1. Three Concerns to Distinguish

Suppose we want one thread to create a configuration and other threads to use it:

~~~text
Thread A (producer)                     Thread B (consumer)
-------------------                     -------------------
1. Allocate object
2. Initialize fields
3. Publish reference -----------------> 4. Read reference
                                        5. Read fields
~~~

A correct design must answer three questions:

1. **Construction — has the object finished initializing?** Have all invariants (states that must remain consistent) of the object been established? Has the constructor or factory completed?
2. **Publication — how does the consumer receive the reference?** Is there a synchronization relationship ensuring that writes performed during initialization are observed before the consumer's reads?
3. **Subsequent mutation — will the object be modified after publication?** If so, later modifications must be protected separately; safe publication of an initial snapshot does not make all future operations thread-safe.

**Do not equate an object existing with an object being safely published.** Having `ref != null` does not automatically prove that the consumer sees the fields in the final state established by the constructor.

### What Does Partial Initialization Mean?

Java assigns default values to an object's fields before initialization steps run: `int` defaults to `0`, `boolean` to `false`, and references to `null`. A constructor may change those fields to valid values, such as `port = 8080` and `name = "primary"`.

If thread B obtains the reference before the constructor completes, B may read some fields in their default state or see invariants not yet established. Even if the object has finished constructing, if its reference is handed over through a **data race**, the JMM does not guarantee that B will observe writes to ordinary fields as A intended. Two causes must be distinguished:

- **Early escape:** the object is published **before construction completes**; partial reads can actually occur because the fields have not been written yet.
- **Unsafe publication:** the object may have finished constructing in A, but there is no appropriate *happens-before* relationship between the object's construction writes and B's reads.

## 2. Java Memory Model and `happens-before`

The Java Memory Model (JMM) specifies which values a thread is permitted to observe and the limits on read/write reordering. It does not force every thread to immediately see each other's ordinary writes when a program lacks synchronization.

The **happens-before** (HB) relationship is the primary reasoning tool. If A's data write *happens-before* B's corresponding read, this relationship provides the required visibility and ordering guarantees, provided no other competing writes alter the result. HB **is not simply** "A happens before B on a wall clock."

Some common sources of HB:

| Mechanism | Key Relationship |
| --- | --- |
| **Program order** | An earlier action in the same thread HB a later action in that thread. |
| **`volatile`** | A write to a volatile variable HB a subsequent volatile read of that same variable in synchronization order. |
| **Monitor (`synchronized`)** | An unlock on a monitor HB a subsequent lock on the same monitor. |
| **`Thread.start()`** | Actions before `start()` HB actions of the started thread. |
| **Successful `Thread.join()`** | Actions of the terminated thread HB actions following `join()` in the waiting thread. |
| **Class initialization** | The JVM coordinates one-time class initialization according to class initialization rules; static state is properly published through that mechanism. |
| **Concurrent utilities** | APIs such as `BlockingQueue`, `Future.get()`, and executors provide specific memory consistency guarantees per their documentation. |

HB is **transitive**: if `A HB B` and `B HB C`, then `A HB C`. Therefore, when a producer writes fields, then performs a release operation, and a consumer performs the corresponding acquire operation, we can deduce that the writes prior to the release will be observed.

A simple example:

~~~text
Thread A:  config = new Config(...);   // Initialize fields
           READY = config;             // Volatile write (release)

Thread B:  local = READY;              // Volatile read sees reference (acquire)
           local.port();               // Read initialized data
~~~

If `READY` is a `volatile` field and B sees the reference written by A, the actions preparing the object before the volatile write are properly published to B. B must read through that mechanism; it must not bypass it via another unsynchronized reference path.

### Safe Publication Is Different from Atomicity

Safe publication guarantees that the **state at the time of publication** is observed correctly according to the synchronization relationship. It **does not mean** all subsequent field modifications are atomic. If threads concurrently increment a mutable counter with `count++`, `synchronized`, atomic RMW, or an appropriate mechanism is still required. **Making the reference-holding variable `volatile` does not automatically make the fields inside the object volatile.**

## 3. Pitfall 1 — Publishing Through an Ordinary Field

Consider the following illustration (deliberately unsynchronized, not a standalone program):

~~~java
final class MutableConfig {
    int port;
    String host;

    MutableConfig(int port, String host) {
        this.port = port;
        this.host = host;
    }
}

class Registry {
    static MutableConfig shared; // Not volatile; no lock.

    static void publish() {
        shared = new MutableConfig(8080, "primary");
    }

    static void consume() {
        MutableConfig local = shared;
        if (local != null) {
            System.out.println(local.port + " / " + local.host);
        }
    }
}
~~~

If `publish()` and `consume()` run on different threads **without** another HB mechanism, writing/reading `shared` creates a data race. The JMM provides no guarantee that the consumer will observe the object as the producer just constructed it, or even always see the new reference in an unsynchronized polling loop.

You should not expect a specific stdout for this broken example: on a familiar machine it may print `8080 / primary` millions of times and **still be wrong with respect to the contract**. In an unsynchronized execution, a thread reading default/stale fields or failing to observe updates can happen depending on the JMM and optimizations, and we must never treat "usually works" as proof.

A point worth noting: the producer writing `new MutableConfig(...)` **before** assigning `shared` in source code does not by itself create an HB relationship with the consumer. Program order only creates an intra-thread relationship within the producer; constraining the consumer requires an inter-thread synchronization edge.

## 4. Pitfall 2 — `this` Escaping the Constructor Too Early

An object must not be accessed by another thread while its invariants are still being constructed. Examples that cause **constructor escape**:

- Assigning `this` to a static/global variable read by another thread.
- Invoking a callback or registering a listener that may be called immediately and expose `this`.
- Submitting a lambda that captures `this` to an executor before the constructor finishes.
- Starting a thread inside the constructor with `new Thread(() -> use(this)).start()` and then continuing to set fields.
- Calling an overridable method inside the constructor; overridden code in a subclass may see the subclass before it has finished initializing.

In particular, `Thread.start()` only guarantees that writes **before the start call** HB actions of the new thread; fields assigned **after start** do not automatically have the same guarantee.

### Example 1 — Deterministically Observing an Incompletely Constructed Object

To see that this is a real initialization-order issue, the program below **deliberately allows the consumer to read mid-constructor**. Create `EscapingThisDemo.java` (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;

public class EscapingThisDemo {
    private static volatile Leaky shared;
    private static final CountDownLatch exposed = new CountDownLatch(1);
    private static final CountDownLatch resume = new CountDownLatch(1);

    static final class Leaky {
        int answer; // Initially 0.

        Leaky() throws InterruptedException {
            shared = this;      // Wrong: published before completion.
            exposed.countDown();
            resume.await();     // Intentionally pause constructor mid-way.
            answer = 42;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Thread maker = new Thread(() -> {
            try {
                new Leaky();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        maker.start();
        exposed.await();
        System.out.println("while constructing = " + shared.answer);

        resume.countDown();
        maker.join();
        System.out.println("after construction = " + shared.answer);
    }
}
~~~

Run:

~~~bash
javac EscapingThisDemo.java
java EscapingThisDemo
~~~

Output when there is no external interruption:

~~~text
while constructing = 0
after construction = 42
~~~

Because `shared = this` occurs **before** `answer = 42` and the latch holds the constructor at that point, the consumer is guaranteed to read `answer` while the field is still at its default `0`. After `resume.countDown()`, the constructor continues. `maker.join()` ensures `main` waits for `maker` to finish before printing `42`.

This example **does not need** to rely on a subtle reordering effect: it shows that an object can literally be published before it is ready. More importantly, `shared` here **is already volatile**: using `volatile` cannot "push" future writes in the constructor backward before the point of publication. Safe publication must happen **after** the object finishes initializing.

### Fixing the Structure

Do not register callbacks, start workers, or attach `this` to a registry from inside the constructor when consumers can run immediately. Instead:

1. Build the object in the constructor **without letting the reference escape**.
2. Verify invariants and complete construction.
3. Publish the reference through an HB mechanism; or call a `start()`/`register()` method **after** the factory has returned the complete object.

If a callback can run concurrently, the callback itself also needs an appropriate synchronization protocol for the state it accesses.

## 5. Approach 1 — Publishing an Immutable Snapshot via `volatile`

For configuration that is replaced as a whole, a simple approach is to create a complete **immutable** object and assign its reference to a `volatile` field.

Create `VolatilePublication.java` (Java 17+):

~~~java
public class VolatilePublication {
    record Config(String host, int retries) {}

    private static volatile Config current;

    public static void main(String[] args) throws InterruptedException {
        Thread consumer = new Thread(() -> {
            Config snapshot;
            while ((snapshot = current) == null) {
                Thread.onSpinWait(); // Only for short demo.
            }
            System.out.println(snapshot.host() + " / " + snapshot.retries());
        });

        consumer.start();                // Consumer has already started.
        Config built = new Config("primary", 3);
        current = built;                 // Publish after construction.
        consumer.join();
    }
}
~~~

Run:

~~~bash
javac VolatilePublication.java
java VolatilePublication
~~~

Output:

~~~text
primary / 3
~~~

The essential point is not `record` itself, but the chain:

~~~text
Producer: initialize Config -> volatile write current
                                 |
                                 | synchronizes-with
                                 v
Consumer:                 volatile read current -> read Config fields
~~~

The consumer only reads the fields of **the snapshot it just captured into a local variable**, rather than reading the reference from the registry multiple times and mixing fields from different versions. A `record` creates `final` components; here `String` and `int` contain no mutable state that could be modified after publication.

The `Thread.onSpinWait()` loop is a **busy-wait solely for teaching volatile semantics**, not a production recommendation. For real work, use `BlockingQueue`, `CountDownLatch`, `Future`, or a notification mechanism to wait efficiently.

### Snapshot Replacement Is Safe, Compound Updates May Not Be

~~~java
// Illustration: each update publishes a whole snapshot.
current = new Config("backup", 5);
~~~

Each consumer can obtain one of the published versions; that snapshot is consistent across both of its fields. However, if **multiple producers** concurrently read `current`, compute a new version, and write it back, the read-modify-write sequence can still suffer lost updates. When update coordination is required, use a lock or `AtomicReference.updateAndGet()`/CAS with a pure update function.

In addition, a `volatile` field only guarantees publication through that field itself; if you publish an object and then **continue modifying ordinary fields** inside it without synchronization, later changes can create data races.

## 6. Approach 2 — `synchronized` and the Same Monitor

`synchronized` serves two related roles: **mutual exclusion** (preventing concurrent execution in the critical section) and **visibility/ordering** via unlock/lock on the same monitor.

Create `MonitorPublication.java` (Java 17+):

~~~java
public class MonitorPublication {
    static final class Config {
        final String host;
        final int retries;

        Config(String host, int retries) {
            this.host = host;
            this.retries = retries;
        }
    }

    private static final Object LOCK = new Object();
    private static Config shared; // Does not need volatile when always using LOCK.

    private static void publish(Config config) {
        synchronized (LOCK) {
            shared = config;
            LOCK.notifyAll();
        }
    }

    private static Config awaitConfig() throws InterruptedException {
        synchronized (LOCK) {
            while (shared == null) {
                LOCK.wait();
            }
            return shared;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Thread consumer = new Thread(() -> {
            try {
                Config snapshot = awaitConfig();
                System.out.println(snapshot.host + " / " + snapshot.retries);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();
        publish(new Config("primary", 3));
        consumer.join();
    }
}
~~~

Run:

~~~bash
javac MonitorPublication.java
java MonitorPublication
~~~

Normal output:

~~~text
primary / 3
~~~

`publish()` constructs `Config` **before** placing the reference into `shared` under the `LOCK` monitor. `awaitConfig()` reads `shared` under **that exact same monitor**. The producer's unlock HB the consumer's subsequent lock. `notifyAll()` wakes up waiting threads; checking the condition in a `while` loop is necessary because Java permits *spurious wakeups*.

**Common mistake:** the producer uses `synchronized(lockA)` while the consumer reads `shared` outside the lock or uses `lockB`. There is no HB guarantee from `lockA` to `lockB` merely because both are locks.

If the reader must return the snapshot for long-lived processing, keep the snapshot state immutable. If a mutable object is modified after being retrieved from the lock, that work still requires separate protection.

## 7. Approach 3 — Ownership Transfer via `BlockingQueue`

A thread-safe queue both transports the reference and serves as a handoff protocol with memory consistency guarantees. Actions before a producer puts an element into a `BlockingQueue` HB actions after a consumer takes that element per the API.

Create `QueuePublication.java` (Java 17+):

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class QueuePublication {
    record Message(String text, int code) {}

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Message> queue = new ArrayBlockingQueue<>(1);

        Thread consumer = new Thread(() -> {
            try {
                Message message = queue.take();
                System.out.println(message.text() + " / " + message.code());
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();
        Message built = new Message("ready", 200);
        queue.put(built);
        consumer.join();
    }
}
~~~

Run:

~~~bash
javac QueuePublication.java
java QueuePublication
~~~

Output:

~~~text
ready / 200
~~~

Advantages: the consumer can **block** waiting for data without a volatile polling loop; the queue also models ordering and backpressure by capacity. You must understand the ownership rule: if the producer calls `queue.put(mutableObject)` and then continues mutating the object while the consumer reads it, the queue only safely hands off **actions before `put`**; concurrent modifications afterward require separate protection.

Communicating with immutable snapshots or explicit ownership transfer generally reduces shared mutable state.

## 8. Approach 4 — Java Class Initialization and Initialization-on-Demand Holder

The JVM has rules synchronizing the class initialization process. When a static field is assigned during class initialization, other code using the properly initialized class per the contract will observe the completed static state.

An example of a lazy singleton using the *initialization-on-demand holder*. Create `LazySingleton.java`:

~~~java
public class LazySingleton {
    static final class Service {
        final int answer;

        Service(int answer) {
            this.answer = answer;
        }
    }

    private static final class Holder {
        static final Service INSTANCE = new Service(42);
    }

    static Service getService() {
        return Holder.INSTANCE;
    }

    public static void main(String[] args) {
        Service first = getService();
        Service second = getService();

        System.out.println("same instance = " + (first == second));
        System.out.println("answer = " + first.answer);
    }
}
~~~

Run:

~~~bash
javac LazySingleton.java
java LazySingleton
~~~

Output:

~~~text
same instance = true
answer = 42
~~~

`Holder` is initialized when its static field is needed; the JVM guarantees one-time class initialization according to concurrency rules. Threads calling `getService()` receive the same instance whose constructor has completed, provided the constructor does not let `this` escape early. This approach avoids manually writing double-checked locking for a simple lazily initialized singleton.

### A `final` Static Field Is Different from a "Completely Immutable Object"

~~~java
static final java.util.List<String> NAMES =
        new java.util.ArrayList<>();
~~~

`final` here **only keeps the reference fixed** to the list; the list itself remains mutable and not thread-safe. If multiple threads concurrently add/remove elements, you must design synchronization/ownership or choose an appropriate data structure. For read-only configuration, prefer immutable snapshots such as `List.copyOf(source)`. Note that an immutable collection does not automatically make its **contained elements** immutable if those elements hold mutable state.

## 9. `final` Field Semantics: Powerful, but Conditional

The JMM provides special rules for `final` fields. When an object is **constructed correctly** — meaning the `this` reference does not escape during construction — and the constructor finishes, the *freeze* mechanism on final fields allows other threads to observe the final values assigned in the constructor, even in some scenarios where the reference is passed via a data race.

Example:

~~~java
// Type declaration example, not a standalone program.
final class Point {
    final int x;
    final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }
}
~~~

When a `Point` is constructed properly, final-field semantics provide special guarantees for `x` and `y`. However, **do not interpret this** as "just using `final` makes all publication safe." Distinguish carefully:

- `final` on a field assigned in the constructor **with no constructor escape** has its own guarantee for the initialized value.
- Ordinary (non-final) fields do not automatically receive final-field semantics guarantees; for objects with ordinary mutable data, publish via HB.
- `final SomeObject reference` only prevents **reassigning the reference** after construction; if the referenced object can be modified, subsequent modifications still need synchronization.
- Rules for objects whose references are reached through a final field provide visibility guarantees for state prior to the freeze, but **do not guarantee that any subsequent mutation is safe**.
- If `this` escapes early, another thread may read the field **before assignment** or before the constructor finishes; you cannot rely on the freeze to fix that behavior.
- Using reflection, unsafe mechanisms, or special serialization to modify final fields afterward has complex semantics; do not rely on such patterns for shared state.

**Safe practice:** design truly immutable objects and publish them through an explicit HB mechanism. Final fields help ensure the correctness of immutable data, while the publication mechanism keeps the handoff flow clear and easier to evolve when data types change.

### Does `record` Make Every Object Thread-Safe?

`record` is often convenient for creating an immutable snapshot in terms of component references:

~~~java
record Settings(String endpoint, int timeoutSeconds) {}
~~~

The component fields are `final`. However, a record with a `List<MutableItem>` component can still carry mutable objects if it does not perform defensive copying and protect the items. Constructors must also avoid letting `this` escape early, and methods should not expose internal mutable state without control.

## 10. Safe Publication with `Thread.start()` and `Thread.join()`

A new `volatile` field is not always required. When **the producer constructs the object and only then calls `start()`** on the consumer, `start()` itself is a synchronization event:

~~~java
// StartPublication.java — Java 17+
public class StartPublication {
    static final class Data {
        int value;

        Data(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Data built = new Data(42); // Completed before start.

        Thread consumer = new Thread(
                () -> System.out.println("value = " + built.value));
        consumer.start();
        consumer.join();
    }
}
~~~

Run `javac StartPublication.java` and `java StartPublication`:

~~~text
value = 42
~~~

The object-construction actions in `main` before `consumer.start()` HB the consumer's actions. `volatile` is not needed on `built` for this one-way scenario.

`Thread.join()` creates the **reverse** direction: if `main` waits for the consumer to finish, the consumer's actions before terminating HB `main`'s actions after `join()`. For example, a worker writing a result to an ordinary field that `main` reads **only after a successful join** has a visibility basis. However, `join()` only helps **the thread that waited**; it does not mean a third thread reading shared state will automatically be synchronized.

**Note:** starting a thread **inside the constructor** and then continuing to assign fields of `this` reverses the order; writes after `start()` are not automatically covered by the HB edge of `start()`. This is a common cause of constructor escape.

## 11. `Future`, Executors, and Concurrent Collections

Standard Java utilities generally have documented API memory consistency rules. For example, with `ExecutorService`, actions of the thread submitting a task **prior to submission** HB actions of the task; actions within the task HB actions after another thread retrieves the result via `Future.get()`. When used properly, the `submit/get` pair is a safe channel for passing state and retrieving results.

Create `FuturePublication.java` (Java 17+):

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FuturePublication {
    static final class Result {
        final int sum;
        Result(int sum) {
            this.sum = sum;
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<Result> future = executor.submit(
                    () -> new Result(20 + 22));

            Result result = future.get();
            System.out.println("sum = " + result.sum);
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Run:

~~~bash
javac FuturePublication.java
java FuturePublication
~~~

Output:

~~~text
sum = 42
~~~

`Future.get()` waits for the computation to complete and delivers the result across an API-specified HB relationship. If the task fails, `get()` may throw `ExecutionException`; if canceled, it may throw `CancellationException`. Publication safety does not replace error/cancellation handling rules.

Similarly, `ConcurrentHashMap`, blocking queues, and other synchronization primitives have their own guarantees for supported operations. **Do not infer from the name "concurrent" that a multi-step `get -> compute -> put` sequence or a multi-key transaction is automatically atomic.** Safe publication and compound-action atomicity are two separate requirements.

## 12. Double-Checked Locking and the Role of `volatile`

A classic lazy-singleton bug is using **double-checked locking (DCL)** while forgetting `volatile` on the reference:

~~~java
// Bug illustration: instance is not volatile.
private static Service instance;

static Service get() {
    if (instance == null) {
        synchronized (LOCK) {
            if (instance == null) {
                instance = new Service();
            }
        }
    }
    return instance;
}
~~~

The first check outside the lock is an unsynchronized read with respect to the writer inside the lock. Because it lacks a proper HB relationship, the design is unsafe: another thread can observe the reference without guarantees about the object's state that needs to be observed. Historical explanations often phrase this as "it may see a partially initialized object"; in practice, it should be analyzed in terms of the visibility contract and specific fields, without claiming every JVM will definitely reproduce the symptom.

Correct DCL for Java 5+ requires a `volatile` field, a non-escaping constructor, and the same monitor guarding initialization:

~~~java
// Illustrative method form; fields belong in the singleton-holding class.
private static volatile Service instance;
private static final Object LOCK = new Object();

static Service get() {
    Service local = instance;
    if (local == null) {
        synchronized (LOCK) {
            local = instance;
            if (local == null) {
                local = new Service();
                instance = local; // Volatile write after construction.
            }
        }
    }
    return local;
}
~~~

`volatile` ensures the fast-path read outside the lock still participates in the publication mechanism. Using a local variable reduces the number of volatile reads on the fast path. If the use case is just a simple static singleton, the **holder idiom** in section 8 is usually less complex.

DCL does not solve cases where `Service`'s constructor registers `this` into another registry, nor is it responsible for ensuring thread safety for `Service`'s mutable methods afterward.

## 13. Why a "Volatile Reference" Is Not Enough If the Object Remains Mutable

Suppose `volatile Config shared` is properly published after construction, and then thread A modifies an ordinary field:

~~~java
// Logic bug illustration, not a standalone program.
Config snapshot = new Config();
snapshot.port = 8080;
shared = snapshot;  // Safely publishes state constructed up to this point.

// At another time, thread A:
snapshot.port = 9090; // Unsynchronized ordinary mutation.

// Meanwhile, thread B:
int observed = shared.port;
~~~

The initial assignment to `shared` may safely publish the value `8080`. However, the write `snapshot.port = 9090` **after publication** does not automatically become thread-safe just because the field holding the reference is `volatile`. If B reads the data concurrently while A modifies it without an appropriate HB relationship, a data race still exists. B may also read stale state or partially updated state when multiple fields are involved.

Three generally better design approaches:

1. **Immutable snapshots:** construct a complete `new Config(...)` and assign the new volatile reference; consumers work with their local snapshot.
2. **Shared lock:** all reads and writes of mutable state share a lock protecting the entire invariant.
3. **Atomic whole-state replacement:** `AtomicReference<State>` holds immutable state; to compute a new state from the old state under contention, use CAS/`updateAndGet()`. The update function should be pure because it may be re-executed on retries.

If you need to maintain a long-lived mutable collection, choose a concurrent structure with the right semantics and avoid leaking references to unprotected internal state.

## 14. Choosing a Publication Strategy by Need

| Need | Recommended Mechanism | Notes |
| --- | --- | --- |
| One producer updates configuration snapshots, many readers fetch the current version | `volatile` reference to an immutable object | Publish **after** construction; post-publish mutation must be avoided or protected |
| Reading/writing multiple mutable fields as one invariant | Shared `synchronized` or `Lock` | Both writers and readers must participate in the same protocol |
| Passing messages/tasks between producer and consumer | `BlockingQueue` | Object state after `put` requires clear ownership rules |
| Lazily initialized static singleton | Initialization-on-demand holder | Constructor must not escape; internal state must have its own concurrency policy |
| Worker produces data and `main` needs the result | `Future.get()`, `Thread.join()` where appropriate | Wait on the right target and handle failure/interruption |
| Replacing multi-field state atomically under contention | `AtomicReference<ImmutableState>` + CAS | Atomicity applies to **one reference**, not to external side effects |
| Reference passed to a thread **after** initialization in the same thread | `Thread.start()` | Writes **after `start`** are not automatically covered by the pre-start HB edge |
| Any object that needs to be shared safely | Do not let `this` escape from the constructor | Do not call external/uncontrolled code that might publish `this` too early |

Do not use "it passed when run," `Thread.sleep`, timestamp ordering, or assumptions that "CPUs automatically sync caches" as criteria to prove safe publication.

## 15. Workflow for Reviewing a Publication Bug

**Step 1 — Find where the object is created.** Does the constructor fully initialize all invariants? Does it call overridable methods, callbacks, listener registrations, or start threads inside the constructor?

**Step 2 — Trace how the reference reaches the consumer.** Through a static field, instance field, global registry, queue, future, local variable capture, or a callback? Is the reference shared before the constructor finishes?

**Step 3 — Draw the HB edge.** Before the consumer's read path, is there a volatile write/read, unlock/lock on the same monitor, `start`, `join`, `Future.get`, queue put/take, static class init, or another documented protocol? If you cannot point to an edge, do not conclude visibility is safe.

**Step 4 — Distinguish the fields.** Which fields are properly `final`, which are ordinary mutable, and which are `volatile`? What conditions apply to final-field semantics? Are there nested mutable objects that need protection?

**Step 5 — Look for post-publication mutations.** Is the consumer using a fixed snapshot or re-reading the reference multiple times? Are multiple producers doing RMW and losing updates? Is the object modified without synchronization after the consumer holds the reference?

**Step 6 — Fix at the right boundary.** Move publication after the constructor, use an immutable snapshot and `volatile`, synchronize both producer/consumer, or pass data through a concurrency API with HB. Merely adding `volatile` to the reference does not fix premature publication.

**Step 7 — QA the right property.** A racy bug example can run "correctly" many times; do not treat that as a proof test. Use a latch-controlled early-escape example to demonstrate initialization order, and use HB reasoning/code inspection for the correctness of the fix. Stress tests can help uncover bugs, but they do not replace JMM reasoning.

### Common Misconceptions

- **"If the reference is non-`null`, the object must be finished constructing."** No: `this` can be exposed externally before the constructor completes.
- **"The producer finished the constructor, so every reader always sees all fields."** Not sufficient for ordinary fields without safe publication; `final` has special guarantees only when constructed correctly.
- **"Making the reference `volatile` makes the fields inside thread-safe forever."** No: post-publication mutations require their own mechanism.
- **"`final` means all referenced objects are deeply immutable."** No: `final` locks the reference, not the mutable object being referenced.
- **"Calling `new Thread(...).start()` in the constructor is always safe."** No: the child thread may observe `this` before fields assigned after `start`.
- **"Both producer and consumer use `synchronized`, so any lock works."** No: they must use the same monitor/protocol to establish the relevant HB edge.
- **"`Future.isDone()` alone gives all guarantees."** For specific results, use `Future.get()`/documented completion rules and handle errors; do not make arbitrary assumptions about state outside the computation.
- **"Once safely published, lock-free compound actions are safe."** No: safe publication is different from atomic read-modify-write or multi-field transactions.

## 16. Self-Check

**Question 1.** Thread A fully initializes a `Config` and assigns it to an ordinary field; thread B reads the ordinary field without a lock. A ran earlier on the wall clock. Is B guaranteed to see all ordinary fields correctly?  
**Answer:** There is no guarantee from **real time** alone. An HB edge or appropriate mechanism is required; properly constructed `final` fields have their own rules.

**Question 2.** An object assigns itself to a static `volatile` reference at the beginning of the constructor, and only then sets its fields. Can a consumer read default values?  
**Answer:** Yes. Volatile publishes **the writes that happened before it**, and does not guarantee that fields written later will be written before the reader runs.

**Question 3.** A producer creates an immutable snapshot and performs a volatile write; a consumer volatile-reads that reference. Is an extra lock needed just to read the created immutable fields?  
**Answer:** No, if the object is constructed correctly and follows the protocol, the volatile write/read establishes HB for the initialized values.

**Question 4.** Thread A builds an object and then calls `consumer.start()`, and the consumer only reads the object without further modification. Is there an HB basis?  
**Answer:** Yes: actions in A before `start()` HB actions of the started thread.

**Question 5.** Does `final List<MutableItem> items` prove that the list and its items cannot be modified concurrently?  
**Answer:** No. `final` only fixes the reference; the collection and its items may still be mutable.

**Question 6.** A `BlockingQueue` delivers an immutable message from producer to consumer. Why doesn't the consumer need a separate `volatile` field just to retrieve the message?  
**Answer:** The queue already has a synchronization protocol and memory consistency guarantees for actions before `put` relative to actions after `take` of that exact element.

**Question 7.** DCL reads the reference outside the lock, but the field is not `volatile`. Why is that dangerous?  
**Answer:** The read outside the lock lacks an HB relationship with the initializing writer; the reader is not guaranteed to observe the proper state. You need `volatile` or should choose the holder idiom.

## Official References

- [Java Language Specification, Java SE 17 — `17.4 Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4): synchronization order, happens-before, data races.
- [Java Language Specification, Java SE 17 — `17.5 final Field Semantics](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): constructor freeze, correctly constructed objects, and limits of `final`.
- [Java Language Specification, Java SE 17 — `12.4 Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): class initialization rules.
- [`Thread` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `start`, `join`, and memory consistency.
- [`BlockingQueue` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html), [`ExecutorService` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html), [`Future` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): work/data handoff guarantees.
- [`AtomicReference` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): atomic update of a reference.

**Remember:** **Construct first -> publish safely -> protect later mutation.** For a consumer to observe an object reliably, avoid constructor escape and establish an explicit *happens-before* mechanism between threads.