# The `volatile` Write/Read Rule in the Java Memory Model

## 1. Objectives and Scope

In Java concurrency, one thread may write to a shared variable while another thread reads from it. Without synchronization, the fact that one thread **has executed an assignment** does not automatically guarantee that the other thread will observe that exact value or related data changes. The `volatile` keyword provides special rules for **write** and **read** operations on a field: ensuring visibility, participating in the synchronization order, and establishing a **happens-before** relationship.

After this lesson, you will be able to:
- Accurately state the rule that a `volatile write` **synchronizes-with** subsequent `volatile read` operations on the **same variable**, according to the synchronization order.
- Explain via a happens-before chain why normal writes performed **before** publishing a `volatile` flag become visible after another thread reads the flag.
- Distinguish volatile visibility/ordering from atomicity and mutual exclusion; identify why `volatile count++` or "check-then-act" is still incorrect.
- Use `volatile boolean` for a one-time notification flag, a `volatile` reference to publish an immutable snapshot, and know when to use `synchronized`, atomic APIs, or thread coordination utilities.
- Read standalone Java 17+ examples, understanding the conditions for correct output as well as limitations regarding liveness, CPU usage, and concurrent updates.

The scope covers only **Java SE, the Java Memory Model (JMM), and the JDK standard library**. The explanations and examples below do not depend on any framework.

## 2. Formal Statement of the Rule

According to the Java Language Specification, §17.4.4–§17.4.5:

> A **write to a `volatile` variable `v`** *synchronizes-with* all **subsequent reads of `v`** by any thread, where "subsequent" is defined according to the **synchronization order**.

From this rule, a corollary follows: a volatile write **happens-before** subsequent volatile reads of the same variable. `synchronizes-with` is one of the relationships that form `happens-before`; `happens-before` also includes **program order** within each thread and **transitivity**.

Conditions to read carefully:
1. Both accesses must be **volatile** and on the same **field/variable `v`**. Two different variables do not automatically have a direct `synchronizes-with` edge between them.
2. "Subsequent" is determined in the **synchronization order** of the memory model, not simply based on a wall clock or timestamps from logs.
3. A volatile read observes a value according to the valid rules of the JMM; it is neither necessary nor accurate to describe it as an instruction that "reads directly from RAM."
4. A thread may not have executed the volatile read yet, may not have been scheduled yet, or may be blocked for another reason. **Visibility/ordering rules do not guarantee completion time** or thread wake-up.
5. If, after publication, normal data continues to be modified concurrently without a new protective protocol, the earlier volatile read **does not automatically make all future data accesses safe**.

You can use the phrase "**volatile write is like release; volatile read is like acquire**" as a mental model to remember the direction of information transfer between threads. However, this is a practical explanation; Java's exact contract remains the synchronization order and happens-before rules of the JMM.

## 3. Why Does Another Thread See Normal Data Written Before a Volatile Write?

Suppose we have shared fields:

~~~java
int payload;               // not volatile
volatile boolean ready;    // synchronization flag
~~~

Producer thread:

~~~java
payload = 42; // A: normal write
ready = true; // B: volatile write
~~~

Consumer thread:

~~~java
if (ready) {             // C: volatile read observing true
    int answer = payload; // D: normal read
}
~~~

Suppose the **producer is the only writer to `payload`**, `ready` starts as `false`, the producer assigns `payload` before publishing `ready=true`, and there are no competing writes to `payload` afterward. If the consumer enters the `if (ready)` branch by reading `true` from this publication, then **`answer` must be 42**. This does not require `payload` itself to be declared volatile.

Chain of relationships:

~~~text
Producer:   A: payload = 42
                     |
               program order
                     v
            B: ready = true     (volatile WRITE)
                     |
               synchronizes-with
                     v
Consumer:   C: read ready=true  (volatile READ)
                     |
               program order
                     v
            D: read payload
~~~

Combining them:
- `A happens-before B` because they are in the same producer thread and A precedes B in program order.
- `B synchronizes-with C` because C is a matching volatile read on the same variable `ready`, subsequent to B in synchronization order.
- `C happens-before D` because they are in the same consumer thread and C precedes D in program order.
- By transitivity, **`A happens-before D`**.

This is the **publication via volatile flag pattern**: write the data first, then **publish** via a volatile write; on the receiving side, **read the flag first**, and only then read the data. Reversing the order completely invalidates this reasoning.

## 4. Standalone Java 17+ Example: One-Time Publication

Save the file as **VolatileWriteReadDemo.java**:

~~~java
public class VolatileWriteReadDemo {
    private static int payload;
    private static volatile boolean ready;

    public static void main(String[] args) throws InterruptedException {
        Thread consumer = new Thread(() -> {
            while (!ready) {
                Thread.onSpinWait();
            }
            System.out.println("payload=" + payload);
        }, "consumer");

        Thread producer = new Thread(() -> {
            payload = 42;
            ready = true;
        }, "producer");

        consumer.start();
        producer.start();

        producer.join();
        consumer.join();
        System.out.println("completed=true");
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac VolatileWriteReadDemo.java
java VolatileWriteReadDemo
~~~

Output when threads are scheduled normally without external interference:

~~~text
payload=42
completed=true
~~~

**Why can we trust this result?**
- The static field `ready` is initialized by default to `false` and `payload` to 0; the sole producer writes `payload=42`, followed by the volatile write `ready=true`.
- The consumer only exits the wait loop when the volatile read observes `true`. That read establishes the required synchronization relationship with the publication.
- After reading `ready=true`, the actions before the producer's publication (including `payload=42`) happen-before the consumer's read of `payload`.
- `join()` in `main` waits for the workers to finish, ensuring `main` only prints `completed=true` after all work has completed. **`join()` is not the reason `payload` has the value 42 in the consumer**; the reason is volatile publication.
- `Thread.onSpinWait()` is merely an optimization hint for short spin loops and **does not itself create a happens-before relationship**; the volatile read in the `while` condition is what matters.

**Practical warning:** The `while (!ready)` loop is a **busy-wait**, which can consume CPU and has no timeout or cancellation. Use it only to demonstrate memory semantics or for very brief waits after careful consideration. If a thread needs to sleep and be woken up, use `CountDownLatch`, `BlockingQueue`, `Condition`, `Future`, or an appropriate blocking mechanism. `volatile` does not replace these mechanisms.

## 5. What Do Volatile Writes and Volatile Reads Guarantee?

| Aspect | Exact Meaning | Should NOT Be Misunderstood As |
|---|---|---|
| **Visibility** | Eligible writes before a volatile write are ordered happens-before accesses after the corresponding volatile read. | Every thread always sees the new state instantaneously, even without performing a read. |
| **Ordering** | The JMM disallows reorderings that would produce behavior violating an established happens-before relationship. | The machine always emits instructions strictly in source order or never optimizes. |
| **Atomicity of volatile access** | A single volatile read/write of a field is an atomic operation under JMM rules, including `volatile long` and `volatile double`. | Compound expressions involving multiple reads/computations/writes like `count++` are also atomic. |
| **Synchronization** | Volatile accesses are synchronization actions; a write-read pair on the same field has a synchronizes-with relationship. | `volatile` locks a resource, or guarantees mutual exclusion or fairness. |
| **Happens-before** | Program order + synchronizes-with + transitivity allow proving observation order. | Calling the same method, sharing a field name, or having two close timestamps automatically creates happens-before. |
| **Liveness** | `volatile` prevents the compiler from caching a stale copy of the flag indefinitely in examples with proper volatile accesses. | A thread is guaranteed to get CPU time, be woken up, or receive a result within N ms. |

### 5.1. Which Value Does a Volatile Read "See"?

Volatile reads and writes are placed in a **synchronization order** consistent with each thread's program order. A volatile read must obey synchronization rules with respect to volatile writes of **that same field**. If multiple writers write `true`, `false`, or different numeric values, a consumer may observe different states depending on valid interleavings. There is no guarantee that every assignment turns into an "event" that every consumer must receive.

For example, setting `ready=true` followed quickly by `ready=false` can cause a consumer that has not yet been scheduled to **never observe `true`**, even though both assignments are volatile. This is why a volatile flag is unsuitable for representing an **event queue** or counting notifications.

### 5.2. Visibility Does Not Mean "Flush the Entire Cache to RAM"

Sometimes `volatile` is loosely described as "the writer flushes its cache, the reader reads from main memory." This phrasing is inaccurate and easily leads to wrong conclusions across different CPUs and JVMs. The JMM is a **contract of observable behavior**; the JVM, JIT, and CPU are free to choose appropriate instructions and memory barriers for each architecture as long as that contract is upheld. When explaining code, reason using `happens-before`, not a fixed hardware cache model.

### 5.3. Single Reads/Writes of `long` and `double`

The JLS allows certain reads/writes of **non-volatile `long` and `double`** to be treated as two 32-bit halves in certain implementations; marking them `volatile` eliminates the risk of word tearing for a **single access**. However, `volatile long counter; counter++;` is still a compound read–modify–write operation and **can suffer lost updates** when there are multiple writers.

## 6. Wrong Publication Order: Setting `ready` Before the Data

Consider this buggy code:

~~~java
// PRODUCER — WRONG publish order:
ready = true;  // volatile WRITE
payload = 42;  // normal WRITE performed afterward
~~~

Consumer remains:

~~~java
if (ready) {
    System.out.println(payload);
}
~~~

The consumer may read `ready=true` and then read `payload=0`, because the producer may not have assigned 42 yet. You cannot apply the "all writes before the volatile write" reasoning to an operation that **occurs after** the volatile write.

~~~text
Producer: ready=true ─────────────► payload=42
              │
              └─ Consumer observes ready=true
                                  └─ may read payload=0
~~~

Simply changing `payload` to `volatile` **does not fix the business ordering**: the consumer can still read before the producer writes 42. Arrange for data initialization to complete before publishing a well-defined signal, or use an immutable snapshot published atomically.

## 7. Safe Publication Using a Volatile Reference

Instead of using multiple mutable fields alongside a flag, a cleaner design is often to create an **immutable object** and publish a **volatile reference** to that object.

Example:

~~~java
public final class ConfigStore {
    public record Config(String endpoint, int retries) {}

    private volatile Config current = new Config("primary", 2);

    public void update(String endpoint, int retries) {
        Config next = new Config(endpoint, retries);
        current = next; // volatile WRITE: publish new snapshot
    }

    public Config snapshot() {
        return current; // volatile READ: obtain the same snapshot
    }
}
~~~

This is a standalone Java 17+ class without a `main` method; it can be placed into a project and used as a configuration store component. The record itself holds two components, `String` and `int`; `String` is immutable. The reader must **read the reference once** and then use that object:

~~~java
ConfigStore.Config c = store.snapshot();
use(c.endpoint(), c.retries());
~~~

This is an illustrative snippet inside a method where `store` and `use(...)` are already declared.

Benefits:
- Each snapshot contains properties that were established before `current` was updated.
- The volatile write of the reference publishes the prior changes; the volatile read obtains the reference and receives safely initialized data.
- The reader can use fields from the **same snapshot**, avoiding reading `endpoint` from version A and `retries` from version B as would happen when reading separate fields.

**Boundary of the guarantee:** `volatile Config current` only gives volatile semantics to reads and writes of the reference itself. It does **not** make the contents of any mutable object that the reference points to immutable or automatically thread-safe. If the object contains a mutable `List` and another thread continues modifying the list without synchronization, a data race can still occur. Use immutable/deeply immutable state or a synchronization protocol for subsequent mutations.

### 7.1. Be Careful When Reading Twice

~~~java
String endpoint = store.snapshot().endpoint();
int retries = store.snapshot().retries();
~~~

If the writer publishes a new snapshot between the two calls to `snapshot()`, the two values may come from **two different versions**. Each volatile read is individually valid, but the pair of reads is not a single transaction. To get consistent fields, read **the reference once**, store it in a local variable, and access all properties from that same object.

## 8. `volatile` Does Not Protect `count++` or Check-Then-Act

Incorrect example:

~~~java
class BrokenCounter {
    volatile int count = 0;

    void increment() {
        count++; // can still suffer lost update
    }
}
~~~

Two threads can:
1. Both volatile-read `count = 5`.
2. Both compute `5 + 1 = 6`.
3. Both volatile-write `count = 6`.

The result is 6 instead of 7. Each individual read/write has volatile semantics, yet **the entire increment operation** is still not atomic. `volatile` holds no lock and does not prevent another thread from entering the computation.

If an atomic counter is needed:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

class SafeCounter {
    private final AtomicInteger count = new AtomicInteger();

    void increment() {
        count.incrementAndGet();
    }

    int get() {
        return count.get();
    }
}
~~~

A variable used solely to observe "whether work has finished" can use `volatile boolean done`; a variable tracking "how many requests have been processed" needs `AtomicInteger`, `AtomicLong`, `LongAdder` (under appropriate reading conditions), or a lock depending on the update pattern.

### 8.1. Check-Then-Act on `volatile` Is Also Not Atomic

~~~java
volatile int tickets = 1;

// Two threads run concurrently:
if (tickets > 0) {
    tickets--; // both may believe they bought a ticket
}
~~~

Even if `tickets--` happens to decrement by only one in total due to a lost update, **both threads can still enter the branch**. What needs protection here is **both the condition check and the state change**, not just the decrement. You can use a shared monitor/lock or a CAS loop on `AtomicInteger`.

### 8.2. A Volatile Array Differs from Volatile Elements

~~~java
volatile int[] numbers = {0};

// This operation performs a normal array element update:
numbers[0]++;
~~~

Declaring `volatile int[] numbers` only applies volatile semantics to the **reference field `numbers`**, not to accesses of `numbers[i]`, which are neither volatile nor atomic. Any concurrent element access still requires a safe protocol. Depending on the case, choose `AtomicIntegerArray`, a lock, or an immutable array snapshot.

Similarly, `volatile Map<K,V>` does not make operations on a mutable `Map` thread-safe.

## 9. A Volatile Flag Is Not a Message Queue

For a single state transition (from `false` to `true`), a volatile flag can represent "ready." However, when multiple consecutive notifications need to be sent:

~~~java
volatile boolean changed;

// Producer:
changed = true;
changed = false;
changed = true;
~~~

A reading consumer is not guaranteed to observe `true` twice. Similarly, a `volatile int eventId` can "skip numbers" when the writer updates faster than the reader processes. `volatile` helps observe state consistent with ordering, **does not record every transition**, and does not acknowledge that each event was processed.

If every individual event must be received, use a `BlockingQueue`, an appropriate `Channel` (if provided by a library), a counting semaphore, or a message/queue abstraction with a delivery contract. If you only need to signal one-time completion, `CountDownLatch` or `CompletableFuture` usually avoids busy-waiting and communicates results or errors more clearly.

## 10. The Write/Read Rule with Multiple Volatile Fields

You must not claim that "writing `volatile a` synchronizes-with reading `volatile b`" if `a` and `b` are **two different fields**. However, through **program order** and other happens-before edges, a volatile field can act as a *bridge* to make operations on other normal fields visible.

Example:

~~~java
int x;
int y;
volatile boolean published;

// Producer:
x = 10;
y = 20;
published = true;

// Consumer:
if (published) {
    int a = x;
    int b = y;
}
~~~

Once the consumer reads the published `true` and there are no other competing writers, the writes `x=10` and `y=20` happen-before the corresponding reads. Even though they are **not volatile**, they are protected along the happens-before path.

Conversely, having two independent volatile fields `volatile boolean a` and `volatile boolean b` does not automatically create a "transaction" updating both variables as a pair. If an invariant requires `a` and `b` to always belong to the same version, publish an object containing both or synchronize on a shared lock.

### Do Not Assume a Volatile Read Sees Every "Latest Value" of Other Fields

After the consumer reads `published=true`, writes occurring after the producer's publication (for example, the writer continuing to modify `x`) are not protected by that volatile read. If multiple writers update `x` and `y`, lacking a synchronization protocol for subsequent updates can still cause data races or inconsistent combined states. One-time publication differs from a continuous stream of updates.

## 11. `volatile` and Wait Loops

An application sometimes has a worker running until it receives a stop signal:

~~~java
class Worker implements Runnable {
    private volatile boolean stopRequested;

    public void requestStop() {
        stopRequested = true;
    }

    @Override
    public void run() {
        while (!stopRequested) {
            doOneUnitOfWork();
        }
    }

    private void doOneUnitOfWork() {
        // A finite unit of work, respecting the lifecycle.
    }
}
~~~

This is an illustrative class, **not a standalone program with `main`**. If `doOneUnitOfWork()` always completes in finite time and the loop keeps reading the volatile flag, the worker can observe the stop request according to visibility rules. However, `volatile` **cannot force** a blocking I/O call or an indefinite wait to finish, nor does it guarantee that the scheduler will grant CPU time within a fixed interval.

For a worker waiting on an interruptible API:
- Combine the stop state with `Thread.interrupt()`, timeouts, or an API-supported cancellation mechanism.
- Catch `InterruptedException` according to contract: typically exit or restore the interrupt flag via `Thread.currentThread().interrupt()` when not rethrowing.
- On shutdown, wait via `join()`, `Future.get()`, or controlled executor shutdown to confirm work has genuinely finished.

Do not use `Thread.sleep()` or `Thread.yield()` as a substitute for a happens-before relationship; they do not provide the synchronization required for a non-volatile field.

## 12. Classic Case: Double-Checked Locking Requires `volatile`

Another example using **safe publication** is lazy initialization, where multiple threads need to access the same instance:

~~~java
public final class LazyService {
    private static volatile LazyService instance;

    private final String label;

    private LazyService() {
        label = "ready";
    }

    public static LazyService getInstance() {
        LazyService result = instance;
        if (result == null) {
            synchronized (LazyService.class) {
                result = instance;
                if (result == null) {
                    result = new LazyService();
                    instance = result;
                }
            }
        }
        return result;
    }

    public String label() {
        return label;
    }
}
~~~

**Analysis:**
- `instance` is a volatile reference; object construction completes before publishing to the volatile field.
- The fast path reads the volatile field into a local variable. If non-null, the caller can use the safely published instance without acquiring a lock.
- If null, locking on `LazyService.class` allows only one thread into the initialization block at a time. The second check **inside the lock** prevents a later thread from recreating the instance.
- After publication, matching non-null reads of `instance` observe the writes performed before the volatile write. Here, the constructor does not let `this` escape before construction finishes.
- This pattern is safe under the modern JMM; the code is considerably more complex than simpler alternatives such as the **initialization-on-demand holder idiom** or an eager singleton. Do not choose double-checked locking merely to "demonstrate volatile" if you do not genuinely need lazy initialization and a fast path.

**Note:** If this class later acquires mutable state, the volatile reference does not make operations on that state automatically thread-safe. A separate concurrency contract is needed for state modified after initialization.

## 13. Second Compilable Example: Reading a Published Snapshot

This program creates an immutable snapshot before a volatile write and reads it after a volatile read. It illustrates a volatile reference field without requiring every field inside to be volatile.

Save the file as **VolatileSnapshotDemo.java**:

~~~java
public class VolatileSnapshotDemo {
    record Snapshot(String status, int code) {}

    private static volatile Snapshot latest;

    public static void main(String[] args) throws InterruptedException {
        Thread consumer = new Thread(() -> {
            Snapshot observed;
            do {
                observed = latest; // volatile read
                if (observed == null) {
                    Thread.onSpinWait();
                }
            } while (observed == null);

            System.out.println("status=" + observed.status());
            System.out.println("code=" + observed.code());
        }, "consumer");

        Thread producer = new Thread(() -> {
            Snapshot prepared = new Snapshot("READY", 200);
            latest = prepared; // volatile write
        }, "producer");

        consumer.start();
        producer.start();
        producer.join();
        consumer.join();
    }
}
~~~

Compile and run:

~~~bash
javac VolatileSnapshotDemo.java
java VolatileSnapshotDemo
~~~

Deterministic output when threads run normally:

~~~text
status=READY
code=200
~~~

Each iteration reads `latest` only once into a local variable. After obtaining a non-null reference, the consumer reads exclusively from that same snapshot. The producer creating `Snapshot` before publishing and the consumer reading `latest` after publishing establish happens-before for the initialization. Both runnable examples use spinning to clarify the principle and **wait loops should not be copied verbatim into production** when wait times may be long.

## 14. Distinguishing `volatile`, `synchronized`, and Atomic Classes

| Requirement | Typically Suitable Solution | Why |
|---|---|---|
| Status flag published by one thread, read by many | `volatile boolean` | Read/write and visibility/ordering are sufficient for simple state. |
| Publishing a complete immutable snapshot | `volatile Snapshot` | Provides an atomic reference update point, making pre-publish initialization visible. |
| Multiple writers accurately incrementing a counter | `AtomicInteger.incrementAndGet()` or a lock | Requires an atomic **read–modify–write**; `volatile count++` is insufficient. |
| Check-then-act and multiple fields must obey an invariant | `synchronized`, `Lock`, or appropriate CAS | Must protect the entire logical sequence of actions. |
| Waiting for an event without CPU polling | `CountDownLatch`, `Future`, `BlockingQueue`, `Condition` | Provides blocking, wake-up/wait mechanics, and usually error/cancellation handling. |
| Summing metrics with many writers, reading aggregate observations | `LongAdder` | Optimizes contention, though `sum()` is not an atomic snapshot while writers are active. |

Do not treat `volatile` as a "lightweight lock." A lock provides **mutual exclusion** to isolate a critical section; `volatile` does not protect multi-step sequences from interleaving. Conversely, when all you need is to properly publish a flag or snapshot, putting everything inside `synchronized` can introduce unnecessary coordination overhead. Choose the tool based on the invariants and behavioral guarantees required, then measure under a realistic workload if performance matters.

## 15. Common Mistakes Found in Code Reviews

**Mistake A — Only the publisher uses `volatile`, while the consumer reads from another path.** Reads must access the exact same volatile field or use a compatible synchronization mechanism. Another flag with the same name or a copy in a non-volatile variable does not create the desired `synchronizes-with` edge.

**Mistake B — Writing the flag before the payload.** The consumer can see the flag set while the payload has not yet been written. Publish the data first, the flag afterward, and do not modify the payload without synchronization after publication.

**Mistake C — Putting `volatile` on a reference and then mutating the object without control.** A volatile reference does not make elements of an `ArrayList`, `HashMap`, or fields inside the object atomic or thread-safe.

**Mistake D — Using `volatile count++`.** Individual read/write guarantees do not imply an atomic compound update. Use an atomic increment or a lock.

**Mistake E — Using `volatile` as a notification queue.** Flags can be overwritten, and readers can miss rapid transitions. Use a queue or a counting/synchronization mechanism with an event-retention contract when needed.

**Mistake F — Equating happens-before with real time.** A volatile write does not make another thread get scheduled immediately, and a thread that does not read the flag cannot receive the signal merely because the variable changed.

**Mistake G — Assuming a volatile read keeps all data consistent forever.** Publication delivers writes *before* the signal to the reader. Updates *after* the signal still require a separate protocol or a new snapshot.

**Mistake H — Reading a snapshot multiple times and mixing versions.** For state with multiple fields, hold one local snapshot reference and read all fields from it.

**Mistake I — Using `sleep` to "wait for `volatile` to take effect."** `sleep()` does not create a synchronization action for normal variables; it only alters scheduling and does not fix a data race.

**Mistake J — Relying on a single stress test to prove there are no bugs.** JITs, runtimes, OSes, and interleavings vary; seeing no errors in one run does not make code correct under the JMM.

## 16. How to Prove to Yourself That a `volatile` Snippet Is Correct

For each case, explicitly identify four milestones:

1. **W(data):** What data does the writer create and write?
2. **W(v):** Does the writer write to **the exact volatile field `v`** after writing the data?
3. **R(v):** Does the reader perform a volatile read from the same field and observe the appropriate published state?
4. **R(data):** Does the reader read the data only after R(v), and is there any writer that continues modifying the data without synchronization?

If you can establish `W(data) →program-order W(v) →synchronizes-with R(v) →program-order R(data)`, then concluding `W(data) happens-before R(data)` is sound. If any arrow is missing, look for another synchronization mechanism that **actually exists**—do not guess based on timing.

### Quick Exercises

**Question 1.** The producer writes `data=10`, then `ready=true` (`ready` is volatile). The consumer reads `ready` as `true` and then reads `data`; there are no other writers. Can `data` be 0?

**Answer:** No, under the described conditions and matching read/write relationship. The write to `data` happens-before the read of `data` following the read of `ready`.

**Question 2.** The producer reverses the order to `ready=true; data=10;`. The consumer still reads `ready` then `data`. Can it observe 0?

**Answer:** Yes. The write to `data` occurs after the volatile write, so it is not guaranteed by that flag read.

**Question 3.** `volatile int n`; two threads both call `n++`. Is the total increment guaranteed to be 2?

**Answer:** No. Lost updates are possible. You must use an atomic read–modify–write or a lock.

**Question 4.** One thread writes `volatile boolean a=true`; another thread reads `volatile boolean b`, where `a` and `b` are unrelated. Does reading `b` directly synchronize-with writing `a`?

**Answer:** No. The direct write/read rule requires **the same field `v`**; to get happens-before for related data, you must find other valid edges.

**Question 5.** `volatile List<String> list`; after publishing `list`, a writer continues calling `list.add(...)` and a reader calls `list.size()` without locking. Has the volatile reference made this safe?

**Answer:** No. Concurrent mutations on a mutable list still require a proper thread-safe design, an immutable snapshot, or appropriate synchronization.

## 17. References

- **Java Language Specification §17.4.4 — Synchronization Order:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.4.4
- **Java Language Specification §17.4.5 — Happens-before Order:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.4.5
- **Java Language Specification §8.3.1.4 — volatile Fields:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.3.1.4
- **AtomicInteger API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- **CountDownLatch API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- **Thread.onSpinWait API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html#onSpinWait()

**Key takeaway:** *Write data before the volatile write; the reader performs a volatile read on the same field before reading the data.* The chain program order → synchronizes-with → program order creates happens-before, giving publication proper visibility and ordering. However, `volatile` **does not make compound updates atomic**, does not lock threads, does not retain every event, and does not protect unsynchronized mutations occurring after publication.
