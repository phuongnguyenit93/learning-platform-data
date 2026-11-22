# Safe Publication via `final`, `volatile`, and Locks in Java

> **Goal:** Know when an initialized object is **safely published** so that other threads can read its state; distinguish the special guarantees of `final` from the *happens-before* guarantees of `volatile` and locks; and choose the right approach for sharing an **immutable snapshot** or protecting **mutable state** in Java.

This lesson belongs to the **Thread Safety** group, using Java SE and the Java Memory Model (JMM). The examples run on Java 17+ and do not depend on Spring or any framework lifecycle/DI mechanism.

## 1. Safe publication is a requirement of thread safety

Suppose thread A constructs an object and then thread B begins using it. In A, the constructor writes the fields in source order; however, **wall-clock execution order does not automatically create a memory-visibility relationship** between two threads if the code lacks synchronization.

An object is **safely published** when the path passing its reference from the creating thread to the using thread has a mechanism ensuring that the necessary initialization actions are observed under an appropriate *happens-before* relationship. Safe publication prevents a situation where a consumer sees a reference without any guarantee of seeing the values that the producer wrote during construction.

~~~text
Thread A                                   Thread B
--------                                   --------
new Config(...)       (1) construction
... writes fields
publish reference     (2) publication  ---> receive reference
                                           read initialized fields
                                           (3) subsequent use
~~~

Three phases should be separated:

1. **Construction:** establishing the object's internal invariants, e.g., `host != null` and `timeout > 0`.
2. **Publication:** passing the reference through a protocol with Java Memory Model guarantees.
3. **Subsequent mutation:** if the object continues to change after being published, a separate mechanism is needed to avoid data races, lost updates, or inconsistent snapshots.

**Safe publication does not mean the object is immutable, nor does it automatically make every future operation on the object thread-safe.** It primarily concerns whether the consumer can rely on writes performed **before the synchronized publication point**.

### Why is `ref != null` not proof?

Consider this intentionally unsynchronized snippet (illustrative code, not a standalone program):

~~~java
class Holder {
    static Settings shared; // Plain field; no volatile, no lock.

    static void create() {
        shared = new Settings("service-a", 30);
    }

    static void consume() {
        Settings local = shared;
        if (local != null) {
            use(local.host, local.timeoutSeconds);
        }
    }
}
~~~

If the two methods run on two different threads with no other synchronization edge, reading `shared` is a racy access with respect to writing `shared`. Seeing a non-null reference does not make ordinary field writes in the constructor automatically *happens-before* the consumer. The producer finishing the constructor earlier in real time is **not enough** to prove the consumer will always see the full state.

Do not expect the racy snippet above to print a specific “wrong” result: the machine/JVM may often happen to observe the right values many times by chance. Passing tests do not replace JMM rules.

## 2. Comparison table of the three mechanisms

| Mechanism | What it actually guarantees | Suitable scope | What must **not** be inferred |
| --- | --- | --- | --- |
| `final` field | Guarantees **final-field semantics** after the object is correctly constructed; final fields hold the values assigned in the constructor even under certain unsynchronized publication patterns | Value objects and immutable snapshots | Does not create a lock, does not protect mutation of an object referenced by a final field, does not fix `this` escape |
| `volatile` reference | A volatile write and a corresponding volatile read establish ordering/visibility, thereby publishing writes prior to the volatile write | Publishing/replacing immutable snapshots, simple status flags | Does not make ordinary fields inside the object always thread-safe; not atomic for read-modify-write sequences |
| `synchronized` / `Lock` | Mutually exclusive critical section and a *happens-before* edge between release/acquire on the same locking mechanism | Mutable data, multiple fields that must be updated/read together; transferring references under a lock | Does not protect any reader/writer that bypasses the lock or locks on a different object |

In practice, these mechanisms often **work together**: an object has `final` fields to hold immutable state and is published via a `volatile` reference; or a mutable object is created and read/modified under the same lock.

## 3. Foundation: happens-before matters more than “runs before”

The JMM describes *synchronizes-with* and *happens-before* (HB) relationships. When **a necessary write HB a read** in another thread, the model provides a basis for the visibility/order of that write. HB is transitive: if A HB B and B HB C, then A HB C.

Commonly used edges:

- **Program order:** an earlier action in a thread HB a later action in the same thread.
- **Monitor:** an unlock of `synchronized(lock)` HB a subsequent lock on **the same monitor**.
- **Volatile:** a volatile write HB subsequent volatile reads of the same variable in synchronization order.
- **`Thread.start()`:** actions before `start()` HB actions of the new thread.
- **`Thread.join()`:** actions in the terminated thread HB actions after `join()` completes successfully in the waiting thread.
- **Concurrent utilities:** APIs such as `BlockingQueue` and `ExecutorService.submit`/`Future.get` have their own memory-consistency rules.
- **Class initialization:** the JVM ensures class initialization is coordinated so that threads use an initialized class according to the specification.

**There is no HB edge merely because of `sleep()`, logging “thread A before thread B”, reading a clock, setting a high priority, or calling `System.out.println()` and inferring out-of-band data ordering.** An I/O library may use internal locks to print, but that is not a synchronization contract for our business state.

Diagram of publication via `volatile`:

~~~text
A: create Config -> write fields -> volatile WRITE ref
                                         |
                                synchronizes-with
                                         v
B:                               volatile READ ref -> read fields
~~~

If the consumer uses the reference received through that synchronization edge, the writes that created the state in A are published to B. If the consumer obtains the same object through **another leaked path**, that path must be analyzed separately.

## 4. `final`: stable values and the *freeze* rule

A `final` field can only be assigned according to Java's initialization rules. The JMM defines **final-field semantics**: for an object that is **constructed correctly**, when the constructor finishes there is a *freeze* action associated with the `final` fields. Other threads are guaranteed to observe the values the constructor assigned to those `final` fields as specified in JLS `17.5, even in certain scenarios where the reference is shared through a data race.

~~~java
// An illustrative class for an immutable value object.
final class Endpoint {
    final String host;
    final int port;

    Endpoint(String host, int port) {
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("host");
        }
        if (port <= 0 || port > 65535) {
            throw new IllegalArgumentException("port");
        }
        this.host = host;
        this.port = port;
    }
}
~~~

Here, the `String` and `int` components carry no internal mutable state modifiable by the caller; the class cannot be subclassed, and the reference is not published during the constructor. A constructed instance is a value object with stable state.

### What does “Constructed correctly” mean?

**Do not let `this` escape the constructor before construction completes.** Suspicious practices include:

- Storing `this` into a static field/registry that another thread can read.
- Passing `this` to a listener/callback that may run immediately.
- Submitting a lambda that captures `this` to an executor right inside the constructor.
- Calling `new Thread(() -> use(this)).start()` before the remaining fields are assigned.
- Calling an overridable method in the constructor; a subclass implementation may run before the subclass fields are constructed.

If a thread reads the object **before the constructor finishes**, the post-freeze final-field guarantee cannot retroactively fix reads that already happened earlier. Even when fields are `final`, do not let consumers touch the object while the constructor is still running.

### `final` does not mean *deeply immutable*

~~~java
final class Names {
    final java.util.List<String> values;

    Names(java.util.List<String> values) {
        this.values = values; // Still holds the caller's list!
    }
}
~~~

The `values` field cannot be reassigned, but another thread can mutate the referenced `ArrayList`, corrupting its structure or causing a data race. When a read-only snapshot is needed, it is safer to do:

~~~java
final class Names {
    final java.util.List<String> values;

    Names(java.util.List<String> source) {
        this.values = java.util.List.copyOf(source);
    }
}
~~~

`List.copyOf` creates a list that cannot be mutated through the standard API while also decoupling the list structure from the mutable source list. However, if the elements themselves are mutable objects, `List.copyOf` **does not deep-copy each element**. Consider copying/designing the entire data tree as immutable or applying appropriate synchronization.

### `final` helps visibility; it does not replace an entire sharing protocol

The special guarantee for `final` fields **does not mean** that all other ordinary fields of the object are safely published. Nor does it provide a mechanism to wait for a reference to appear, provide ordering for post-constructor mutations, or make a sequence of operations across multiple objects atomic.

**Good habit:** use `final` fields to express unchanging state, and still choose an **explicit publication path** such as `volatile`, a lock, class initialization, or a concurrent queue.

## 5. Java 17 example: value object with `final` fields published before `Thread.start()`

Create `FinalConfigDemo.java`:

~~~java
public class FinalConfigDemo {
    private static final class Config {
        final String host;
        final int timeoutSeconds;

        Config(String host, int timeoutSeconds) {
            this.host = host;
            this.timeoutSeconds = timeoutSeconds;
        }

        String describe() {
            return host + ":" + timeoutSeconds;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Config config = new Config("api.internal", 15);

        Thread reader = new Thread(
                () -> System.out.println("config = " + config.describe()));

        reader.start();
        reader.join();
    }
}
~~~

Run:

~~~bash
javac FinalConfigDemo.java
java FinalConfigDemo
~~~

Stdout:

~~~text
config = api.internal:15
~~~

This code has **two good properties**: `Config` has completed construction and has `final` fields; furthermore, the writes preparing the object before `reader.start()` HB the actions of the reader thread. Therefore, **do not use this example's output to claim that `final` alone replaces all publication techniques**. This is a readable, practical pattern that avoids testing unsafe publication, which has no deterministic stdout.

Calling `reader.join()` also ensures `main` waits for `reader` to finish before exiting, though it is not the publication mechanism from `main` to `reader`; the publication direction here comes from `start()`.

## 6. `volatile`: safely publishing a reference after construction

When the producer finishes building the object and then writes the reference to a `volatile` field, a reader that reads that same `volatile` field participates in the synchronization mechanism. Writes prior to the producer's volatile write are observed through the consumer's corresponding volatile read.

Example:

~~~java
// Illustrative class structure; fields and methods are in the same class.
private static volatile Config latest;

static void replaceConfig() {
    Config complete = new Config("primary", 20);
    latest = complete; // Volatile WRITE after construction.
}

static Config currentConfig() {
    return latest; // Volatile READ.
}
~~~

If `Config` is an immutable snapshot, a reader can capture `Config local = currentConfig()` once and then read multiple fields consistently from **the same snapshot**. When the publisher replaces `latest` with a new snapshot, another reader may see either the old or the new version depending on when it reads, but it will never see “half” of a reference assignment or have to deal with an object being mutated field by field.

### Java 17 example: replacing a snapshot via `volatile`

Create `VolatileSnapshotDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public class VolatileSnapshotDemo {
    private record Settings(String host, int retries) {}

    private static volatile Settings current;
    private static final CountDownLatch readerStarted =
            new CountDownLatch(1);

    public static void main(String[] args) throws InterruptedException {
        Thread reader = new Thread(() -> {
            readerStarted.countDown();
            Settings snapshot;
            while ((snapshot = current) == null) {
                Thread.onSpinWait();
            }
            System.out.println(
                    snapshot.host() + " / retries=" + snapshot.retries());
        }, "reader");

        reader.start();
        readerStarted.await();

        Settings built = new Settings("primary", 3);
        current = built; // Volatile write AFTER initialization.
        reader.join();
    }
}
~~~

Compile/run:

~~~bash
javac VolatileSnapshotDemo.java
java VolatileSnapshotDemo
~~~

Output during normal execution:

~~~text
primary / retries=3
~~~

`readerStarted` only coordinates the point at which the reader has started to demonstrate two threads. The consumer repeats a **volatile read** until it sees the reference. Once `current` is observed, the values from the fully constructed `built` object are published via the volatile write/read and can be read reliably.

**Spin loops are for demos only.** In applications that need waiting with timeouts, cancellation, or without burning CPU, use `BlockingQueue`, `CountDownLatch`, `Condition`, `Future`, or similar utilities instead of spinning indefinitely. The JMM provides visibility guarantees; when a thread is scheduled by the OS and makes progress is not a hard real-time guarantee.

### `volatile` does not make the entire object automatically thread-safe

~~~java
// Illustrates a logic bug, not a standalone program.
class MutableState {
    int count;
}
volatile MutableState state = new MutableState();

void increment() {
    state.count++; // Still a read-modify-write on an ordinary int.
}
~~~

Each read of the `state` field has volatile-reference semantics, but `count++` on the shared object is not automatically atomic. Two writers can still suffer lost updates. A volatile write to a **reference** does not make every field of the referent volatile or atomic, and it does not lock post-publication operations.

If state must change, **replace the entire immutable snapshot** via a volatile write, or protect the mutable fields with an appropriate lock/atomic.

### Two writers: volatile replacement does not guarantee read-modify-write

~~~java
// Incorrect illustrative code if multiple writers run concurrently.
Settings old = current;
current = new Settings(old.host(), old.retries() + 1);
~~~

Even though `current` is `volatile`, two writers can both read the same old snapshot and both write a new snapshot, losing one update. To guarantee an update based on the current state, use the same lock or `AtomicReference<Settings>.updateAndGet(...)`/CAS with a pure update function. **Publishing a new snapshot** and **atomicity of computing a new snapshot from the current state** are two different requirements.

## 7. `synchronized`: publication and state access via the same monitor

`synchronized` does not merely prevent two threads from entering the same monitor at once; the producer's **unlock** has an HB edge to the consumer's subsequent **lock** on that exact monitor. Writes to ordinary fields inside the critical section are properly observed by the reader when the reader follows the same protocol.

Create `MonitorPublicationDemo.java`:

~~~java
public class MonitorPublicationDemo {
    private static final Object LOCK = new Object();
    private static Profile shared; // Ordinary field, not volatile.

    private record Profile(String name, int level) {}

    private static void publish(Profile ready) {
        synchronized (LOCK) {
            shared = ready;
            LOCK.notifyAll();
        }
    }

    private static Profile awaitProfile() throws InterruptedException {
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
                Profile local = awaitProfile();
                System.out.println(local.name() + " level " + local.level());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        consumer.start();
        publish(new Profile("Ada", 7));
        consumer.join();
    }
}
~~~

Run:

~~~bash
javac MonitorPublicationDemo.java
java MonitorPublicationDemo
~~~

Output during a normal run:

~~~text
Ada level 7
~~~

Both `publish` and `awaitProfile` use **the same `LOCK`**. The producer publishes `Profile` after construction, and the consumer waits on the condition within that monitor. `notifyAll()` wakes waiting threads; **the `while` loop is required by the pattern**, because `Object.wait()` can wake up spuriously or be awakened before the condition holds.

Notice: the consumer may acquire the lock before the producer or vice versa; both orderings are valid. No `Thread.sleep` is needed to produce the result.

### When should `volatile` be added to `shared`?

**It is not needed** if *every read/write path for the reference* is properly synchronized under the same lock. Adding `volatile` does not fix an unlocked read path that uses the wrong protocol or lacks mutual exclusion for multiple fields that must be read together.

If a consumer keeps a reference to a **mutable** object and reads it outside the lock while the producer continues modifying it, you must protect the use of that state or switch to an immutable snapshot. The pattern above is safe and convenient because `Profile` has immutable state.

## 8. `ReentrantLock`: similar HB semantics via lock/unlock

`ReentrantLock` is an alternative when you need `tryLock()`, interruptible locking, timeouts, or `Condition`. `unlock()`/`lock()` calls on the same lock provide synchronization effects equivalent to a matching monitor.

~~~java
// Method snippet for illustration, not a standalone program.
// LOCK is a ReentrantLock shared by both writer and reader.
LOCK.lock();
try {
    shared = new Profile("Ada", 7);
} finally {
    LOCK.unlock();
}
~~~

The reader also needs:

~~~java
LOCK.lock();
try {
    Profile snapshot = shared;
    // Only use snapshot outside the lock if it is immutable or has its own protocol.
} finally {
    LOCK.unlock();
}
~~~

**A lock has no effect if each thread creates its own `new ReentrantLock()`**, or if another read/write path bypasses the lock. Reading state that has been immutably copied out of the locked region can be safe if the snapshot was properly initialized, whereas continuing to mutate a shared object still requires protection.

Use `finally` to release the lock on every return or exception path.

## 9. Comparison by scenario: `final`, `volatile`, or lock?

| Scenario | Option to consider | Why |
| --- | --- | --- |
| Value object unchanged after constructor | `final` fields, immutable class/record; publish via HB | Clear value semantics and easy to share |
| Multi-field configuration, replaced in batches, mostly read by readers | `volatile` reference to an immutable snapshot | Readers grab one snapshot and read it consistently |
| A single stop flag updated by one writer, checked by readers | `volatile boolean`, or `AtomicBoolean` if RMW is needed | Publication/visibility for a single signal |
| Multiple threads must update multiple mutable fields together | `synchronized` or `ReentrantLock` over the same state | Lock preserves invariants inside the critical section |
| Must compute a new snapshot from the current snapshot with multiple writers | Lock or CAS via `AtomicReference<ImmutableState>` | Prevents lost updates |
| Task producer hands off an object to a consumer | `BlockingQueue`, executor/Future per contract | Provides both handoff channel and HB |
| Lazy-initialized Java singleton, no framework | Initialization-on-demand holder | JVM guarantees safe class initialization |
| Nested object with mutable fields | Defensive copy, confinement, lock/atomic for mutations | A `final` reference alone is not enough |
| Constructor has callbacks or starts threads | Refactor so `this` does not escape | Publishing before freeze/construction completion is dangerous |

**Choose the mechanism based on invariants and actual access paths**, not based on “this field is read often so let's add `volatile` just to be safe.”

## 10. Example of *constructor escape*: `final` also has limits

Imagine this constructor:

~~~java
// Anti-pattern illustration; not a standalone program.
class BadStart {
    final int number;

    BadStart() {
        new Thread(() -> consume(number)).start();
        number = 42;
    }
}
~~~

Do not use this pattern. Starting the thread can expose `this` to the consumer **before the constructor finishes and before the `final` field has its intended value**. Moreover, with the Java declaration above, the compiler may reject referencing a blank `final` field from a lambda before it is definitely assigned; to demonstrate the flaw at the principle level, a clearer example has an **instance method** reading the field, and the thread calls that method:

~~~java
// Illustrates a lifecycle hazard; not intended to be run.
class UnsafeStarter {
    final int number;

    UnsafeStarter() {
        new Thread(this::inspect).start(); // Leaks this too early.
        number = 42;
    }

    void inspect() {
        consume(number);
    }

    void consume(int value) {
        // Consumer may observe an uninitialized number.
    }
}
~~~

Even though the `this` reference is passed to the new thread via `start()`, the HB edge of `start()` only covers actions **before** the `start()` call, and does not automatically cover the assignment `number = 42` that occurs **afterward**. Reading a default value due to incomplete initialization is a real risk; do not expect specific stdout or count probabilities, as it depends on scheduling.

### Proper design: finish construction before activating

~~~java
// Illustrative structure, not a standalone program.
final class ReadyService {
    final int number;

    ReadyService() {
        number = 42;
    }

    void inspect() {
        System.out.println(number);
    }
}

// Outside the constructor:
ReadyService service = new ReadyService();
new Thread(service::inspect).start();
~~~

Here the object completes construction before the new thread starts; the preparatory actions before `start` HB the actions of that thread. The same applies to callback/listener registration APIs: finish constructing the object first, then register it through a synchronized protocol.

**In addition to early escape, calling an overridable method in a constructor can also expose uninitialized subclass state**; prefer `final` classes for immutable value objects or avoid calling overridable behavior from constructors.

## 11. Another option: class initialization to publish a singleton

Java class initialization has built-in synchronization rules. You can leverage the *initialization-on-demand holder* idiom without writing DCL yourself:

~~~java
// HolderPublicationDemo.java — Java 17+
public class HolderPublicationDemo {
    static final class Service {
        final String endpoint;

        Service(String endpoint) {
            this.endpoint = endpoint;
        }
    }

    private static final class Holder {
        static final Service INSTANCE = new Service("local");
    }

    static Service service() {
        return Holder.INSTANCE;
    }

    public static void main(String[] args) {
        Service a = service();
        Service b = service();
        System.out.println("same = " + (a == b));
        System.out.println("endpoint = " + b.endpoint);
    }
}
~~~

Run:

~~~bash
javac HolderPublicationDemo.java
java HolderPublicationDemo
~~~

Stdout:

~~~text
same = true
endpoint = local
~~~

This code relies on JVM class initialization to create the singleton safely and only once, provided the constructor does not let `this` escape. This is a clean choice when you need a pure-Java immutable singleton.

**`static final` does not automatically make the referent thread-safe:** if `INSTANCE` is a mutable service with methods that modify state, those methods still need proper concurrency design, even though the reference itself is safely published.

## 12. Double-checked locking: why must the reference be `volatile`?

Lazy initialization is often written like this:

~~~java
// NOT safe if instance is read outside the lock without volatile.
private static Service instance;

static Service instance() {
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

A reader at the first check **does not acquire the lock**; if `instance` is an ordinary field, it lacks an HB edge with the thread that wrote it inside `synchronized`. This bug is not fixed by reasoning that “the constructor must have finished in real time.”

For Java 5+, a safe DCL form is (class structure example, not a standalone file):

~~~java
private static volatile Service instance;
private static final Object LOCK = new Object();

static Service instance() {
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

Thanks to `volatile`, the unlocked read has an appropriate memory-visibility relationship with the publishing write, while only one thread enters the initialization critical section when `instance` is still null. `local` avoids unnecessarily re-reading the volatile field on the fast path. **Conditions:** the constructor must not leak `this`, all initialization paths must follow this protocol, and any mutable operations on the service after initialization must still be protected separately.

If you do not need to optimize a lazy singleton with this pattern, using the holder idiom from the previous section is usually easier to verify.

## 13. Publication via built-in concurrency APIs

Not every reference handoff requires creating your own `volatile` field. Several standard APIs provide explicit memory-consistency guarantees.

- **`BlockingQueue`:** actions of the producer **prior to placing** an element into the queue HB actions of the consumer **after taking** that element.
- **`ExecutorService.submit` → task → `Future.get()`:** actions before submission HB actions of the task; actions of the task HB actions after another thread retrieves the result via `Future.get()`.
- **`Thread.start`/`Thread.join`:** provide directional HB edges for data prepared before `start` or produced by a thread before `join` completes.
- **`ConcurrentHashMap`:** operations on mappings provide memory-consistency and atomic update capabilities per contract; this does not mean a multi-key sequence of operations is a single transaction.

### Java 17 example: handing off a snapshot via `BlockingQueue`

Create `QueueHandoffDemo.java`:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class QueueHandoffDemo {
    private record Message(String title, int version) {}

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Message> queue = new ArrayBlockingQueue<>(1);

        Thread consumer = new Thread(() -> {
            try {
                Message message = queue.take();
                System.out.println(message.title() + " v" + message.version());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        consumer.start();
        Message ready = new Message("config", 2);
        queue.put(ready);
        consumer.join();
    }
}
~~~

Run:

~~~bash
javac QueueHandoffDemo.java
java QueueHandoffDemo
~~~

Stdout:

~~~text
config v2
~~~

The queue serves as both a coordinated handoff channel and an HB guarantee. No separate `volatile` reference is needed just to transfer this message. However, if the producer continues to **modify mutable contents** of the message after `put`, those modifications are not automatically protected by the queue; use immutable messages or explicit ownership transfer.

## 14. Safe publication differs from thread safety of the entire object

Compare three designs:

**Design A — immutable object is published:**

~~~java
record Snapshot(String host, int port) {}
volatile Snapshot current;
~~~

Readers grab a local snapshot and only read immutable fields. If the producer replaces the reference with a new snapshot, readers already holding the old snapshot can continue using it consistently. However, if multiple writers compute a new snapshot from the old one, a lock/CAS is needed to avoid lost updates.

**Design B — mutable object published via `volatile` and mutated normally:**

~~~java
final class MutableCounter {
    int value;
}
volatile MutableCounter counter;
~~~

Safe publication of the reference only guarantees visibility of writes before publication. `counter.value++` across multiple threads is still a race. Adding `volatile` to `value` does not make `++` atomic either; use `AtomicInteger.incrementAndGet()` or a lock properly.

**Design C — mutable object shared through a single monitor:**

~~~java
// Protocol illustration: all accesses to state use LOCK.
synchronized (LOCK) {
    state.balance += amount;
    state.version++;
}
~~~

If invariants require `balance` and `version` to be updated/read together, the monitor protects the entire combination. Readers must read **both** under the same lock, or take an immutable snapshot under the lock and use it outside the lock.

Do not put `final` on a **reference** and assume the referent's mutable state becomes an immutable snapshot. Safe publication is only the *first step* toward thread safety when mutable shared state is involved.

## 15. Notes on `final`, `record`, defensive copies, and object graphs

For multi-level object graphs, the question is not just whether the outermost object has `final` fields:

~~~java
record Team(java.util.List<Member> members) {}
// If Member has mutable fields or the caller still mutates the list,
// the record syntax alone does not prove the entire graph is immutable.
~~~

Rules to remember:

1. `record` makes component fields `final`, but a component referencing a mutable object can still be mutated.
2. A shallow copy of a collection only protects **the collection structure**, not a deep copy of every element.
3. For a truly immutable object, choose immutable value types, make defensive copies during construction, and do not expose mutable internals via getters.
4. `final` is suitable for preserving invariants after construction, but **never let `this` escape early**.
5. Post-publication mutations require locks/atomics/ownership even if the references leading to that state are `final`.
6. If multiple fields change together, making each field individually `volatile` does not automatically guarantee a consistent snapshot of the whole group.

A clean API typically accepts immutable inputs, builds a new snapshot, and publishes the snapshot through a single synchronization point.

## 16. How to reason about and inspect a publication path

When reviewing code that shares objects across threads, follow this order:

1. **Trace the reference path:** where is the object created, what does the constructor do, and which field/listener/queue passes the reference to readers?
2. **Check construction:** are invariants ready before the reference escapes? Is there any `this` escape, thread started in constructor, callback, or overridable method?
3. **Classify state:** which fields are `final`; which parts are mutable; are there nested mutable objects, collections, arrays, or caches?
4. **Find the HB edge:** volatile write/read on the same variable, unlock/lock on the same monitor, queue handoff, submit/get, start/join, or class init? Identify the exact before/after of the edge.
5. **Check all readers and writers:** is there any path bypassing the lock/volatile? Does any thread hold a direct reference from an unsynchronized registry?
6. **Check post-publication:** is the object mutated afterward? Are there compound actions needing atomicity or multi-field invariants?
7. **Choose a small, clear solution:** immutable snapshot + `volatile` for read-mostly; monitor/Lock for mutable invariants; concurrent utility for handoff; atomic/CAS for independently updated state.
8. **Verify correctness before performance:** reason from the JMM and invariants; write tests with latches to control interleaving if needed; never conclude safety from passing stress tests.

### Common mistakes

- **“The constructor finished in wall-clock time, so that's enough.”** No: the reader must have an appropriate publication/happens-before basis.
- **“`final` makes the object graph deeply immutable.”** No: a `final` field can reference a mutable collection/object.
- **“A `volatile` reference makes all ordinary fields volatile.”** No: it publishes writes that happened beforehand; subsequent mutations must be protected.
- **“`counter++` on volatile state is atomic.”** No: read-modify-write requires an atomic API or a lock.
- **“`synchronized` in two places is enough even with different monitors.”** No: HB through a monitor must use the same lock.
- **“Publishing before the constructor finishes is fine if the reference is volatile.”** No: `volatile` does not publish writes that have not happened yet.
- **“DCL without `volatile`, but the writer uses a lock.”** No: the unlocked fast-path reader is not synchronized with the writer.
- **“Waiting long enough with `Thread.sleep` is safe publication.”** No: sleeping does not create an HB edge for fields.
- **“A concurrent queue keeps mutable objects safe forever afterward.”** No: mutation/ownership rules are still needed after handoff.
- **“Safe publication solves races on all operations.”** No: you must verify thread safety of the entire API after the object is shared.

## 17. Self-check questions

**Q1:** `final Config config` is assigned properly in the constructor, but `Config` holds a mutable `ArrayList`. Can multiple threads add elements without a lock just because the `config` field is `final`?  
**Answer:** No. `final` fixes the reference; it does not make mutations to the `ArrayList` thread-safe.

**Q2:** A producer builds `Config` and writes it to `volatile Config current`; a consumer reads `current` into a local variable and then reads its immutable fields. Why does the consumer see the correct state?  
**Answer:** Publication goes through a volatile write/read, creating an appropriate HB edge between the constructor writes and the field reads in the consumer.

**Q3:** Using `volatile MutableState state`, multiple threads call `state.count++`. Does this prevent lost updates?  
**Answer:** No. `volatile` on the reference does not make RMW on the `count` field atomic.

**Q4:** The producer writes `shared` inside `synchronized(lockA)`, and the consumer reads it inside `synchronized(lockB)`. Is that sufficient?  
**Answer:** No, if `lockA` and `lockB` are different objects and there is no other HB mechanism.

**Q5:** `this` is added to a registry at the start of the constructor, and `final` fields are assigned at the end of the constructor. Does final-field semantics protect reads that occur while the constructor is still running?  
**Answer:** No. Those reads can occur **before assignment/freeze**; early escape must be avoided.

**Q6:** When updating a configuration with three fields, readers need a snapshot with all three values from the same version. Should you publish each field as a separate `volatile`, or publish one immutable object through a single `volatile` reference?  
**Answer:** Usually prefer a single immutable snapshot published via one `volatile` reference, so readers capture and read the same version.

**Q7:** A worker processes messages received from a `BlockingQueue`. Does the producer need to add `volatile` to every field of an immutable message just so the consumer sees writes made before `put`?  
**Answer:** No; the queue provides memory-consistency guarantees for the handoff per contract. Mutating the message after `put` is a separate matter.

**Q8:** When should you use a monitor instead of `volatile` alone?  
**Answer:** When there is mutable shared state or multiple actions/fields that must be protected as **a single invariant**, or when multiple writers must perform atomic compound operations.

## Official API and specification references

- [Java Language Specification `17.4 — Memory Model, Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4): synchronization actions, happens-before, data races.
- [Java Language Specification `17.5 — final Field Semantics, Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): freeze and correctly constructed conditions.
- [Java Language Specification `12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): class initialization.
- [`Thread` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `start()` and `join()`.
- [`BlockingQueue` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): memory consistency for producer–consumer.
- [`ExecutorService` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html), [`Future` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): task handoff and results.
- [`AtomicReference` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): atomic replacement and CAS.

**Takeaway:** `final` protects properly initialized values via final-field semantics; `volatile` publishes pre-write state to synchronized readers; locks protect both publication and mutable state access when threads share a protocol. Always complete **construction before publication**, and decide separately how to protect **post-publication mutation**.