# Happens-before and Its Role in Java Concurrency Correctness

When two threads access shared data, you cannot simply look at the statement order in the source code to conclude that the reading thread will observe the latest result. The Java Memory Model (JMM) describes which memory observations are permitted when a program executes concurrently. **Happens-before (HB)** is an ordering relation used to reason that a set of writes has been published and can be properly observed by subsequent reads.

HB helps answer questions such as: When a worker writes data and terminates, what can `main` read? Is writing a `volatile` flag enough to publish prior data? Why does `synchronized` both prevent interleaving and carry memory effects? Why doesn't `Thread.sleep()` solve a data race? From these questions, we can distinguish **visibility**, **ordering**, and **atomicity**, and prove a program correct according to Java's contract.

This article covers the **Java Memory Model in Java Concurrency in general**. Spring-specific mechanisms are out of scope.

## 1. The problem: source order is not enough for multithreading

Consider shared state:

~~~java
final class Message {
    int data;
    boolean ready;
}
~~~

Writer:

~~~java
message.data = 42;
message.ready = true;
~~~

Reader:

~~~java
while (!message.ready) {
    // Wait for writer.
}
System.out.println(message.data);
~~~

These are **faulty illustrative snippets**, not a standalone program. If `message` is accessed by two threads without synchronization, the reader has no necessary guarantee that it will see `ready == true`, or that when it sees `ready`, it will also observe `data == 42`. The compiler and hardware may legally optimize under the JMM, and plain reads/writes do not by themselves establish data publication across threads.

The `while` loop is also busy waiting: it can run continuously, wasting CPU. Adding `Thread.sleep(10)`, `Thread.yield()`, or `Thread.onSpinWait()` may change the polling rate/schedule, but **does not create the required HB relation**.

We need a real synchronization protocol: `volatile`, a `synchronized` monitor, `Lock`, `CountDownLatch`, `Future`, `Thread.join()`, a concurrent queue, or an API with a clear memory-consistency contract.

### 1.1 Three non-synonymous properties

| Property | Meaning | Common mistake |
| --- | --- | --- |
| **Visibility** | Ensures reads observe updates according to JMM constraints. | A thread reads a stale flag or data when it has not been published. |
| **Ordering** | Ensures the required observation order between actions. | The reader sees the signal without a guarantee that the payload has been published. |
| **Atomicity** | A critical operation/group of operations executes without interleaving according to the protocol. | Two threads both execute `count++`, causing lost updates. |

**HB is the foundation of visibility and ordering.** HB does not automatically make a compound increment atomic and does not replace protecting business invariants.

## 2. Definition and how to read the happens-before relation

The notation `A →HB B` means action A *happens-before* action B. This is a **partial order relation** under the Java Memory Model, not a measurement of how many milliseconds A occurs before B on a wall clock. HB is formed by:

- **Program order:** within the same thread, earlier actions in program order form HB edges to later actions.
- **Synchronizes-with:** inter-thread synchronization relations defined by the JMM, such as unlock→lock on the same monitor or volatile write→subsequent volatile read.
- **Transitivity:** if A →HB B and B →HB C, then A →HB C.

Visualize it as:

~~~text
Writer                              Reader
---------------------------         ----------------------------
write payload = 42                  ...
      |
      v
write volatile ready = true ------> read volatile ready == true
                                          |
                                          v
                                     read payload
~~~

The horizontal arrow is the volatile synchronization edge when the reader reads the signal published by the writer. The two vertical arrows are program order. By transitivity, `write payload = 42 →HB read payload`. If no other writer concurrently modifies `payload`, the reader has grounds to observe 42.

**Do not equate HB with a physical execution schedule.** The JVM/CPU may still reorder instructions as long as they preserve valid observable outcomes under the JMM. Two actions can occur far apart in time yet still lack an HB edge if there is no corresponding synchronization mechanism.

**HB is also not the sole sufficient condition for every read outcome:** if there are multiple writes to the same variable and other ordering relations, all competing writes and the JMM's value-reading rules must be considered. When concluding that a reader sees a specific value, always state assumptions clearly, such as "only one writer writes this variable before the signal."

## 3. Basic HB rules of the JMM

| Source of relation | Key happens-before edge | Condition |
| --- | --- | --- |
| In-thread order | Earlier action →HB later action in program order. | Same thread; does not automatically synchronize with other threads. |
| Monitor (`synchronized`) | Unlock of a monitor →HB every subsequent lock on that same monitor. | Same monitor; all access paths must use the appropriate protocol. |
| `volatile` variable | Volatile write →HB subsequent volatile reads of the **same variable** in synchronization order. | Does not provide atomicity for multi-step `++`. |
| `Thread.start()` | Call to `start()` →HB every action in the started thread. | Caller's writes before `start()` are published according to the rule. |
| Thread termination | Every action in a worker →HB another thread when it detects worker termination, e.g., via a successful `join()`. | A timed join that expires while the worker is still alive does not guarantee completion. |
| Interruption | `interrupt()` →HB the point where the interrupted thread detects that signal. | Interruption is a cooperative request, not a forced stop. |
| Default initialization | Default initialization of an object →HB other actions on the object. | Does not prove all fields were properly configured by the constructor when the object is unsafely published. |
| Transitivity | A →HB B and B →HB C ⇒ A →HB C. | Chains program order and synchronization edges. |

The *synchronizes-with* relation covers only the basic synchronization edges. *Happens-before* also includes program order and transitive chains; therefore, an HB relation can exist from a plain write before a volatile write to a plain read after a volatile read without every variable carrying the `volatile` keyword.

Java also defines *synchronization order*, a total order over synchronization actions consistent with each thread's program order. You do not need to predict this entire order when writing applications, but you must understand that you cannot arbitrarily pair any volatile write with any volatile read to prove what you want.

## 4. Using volatile to publish data

Fixing the initial class:

~~~java
final class Message {
    int data;
    volatile boolean ready;
}
~~~

Writer executes:

~~~java
message.data = 42;     // Write data first.
message.ready = true;  // Signal via volatile write.
~~~

Reader:

~~~java
if (message.ready) {   // Volatile read sees writer's true.
    System.out.println(message.data);
}
~~~

The snippets above assume `message` has already been declared. When the reader sees the appropriate signal, the volatile write→read edge together with program order lets us deduce that writing `data = 42` happens-before reading `data` under HB. With a single writer and no concurrent modifications to `data`, the reader can observe the value 42.

**The order of the two statements matters greatly.** If the writer sets `ready = true` before writing `data = 42`, the reader may receive the signal before the data is prepared. If the reader reads `data` before reading `ready`, that read receives no publication guarantee from the subsequent signal.

**Limitations of volatile:**

- A single volatile read/write has visibility and ordering under the JMM; it does not turn multiple statements into a single transaction.
- `volatile int count; count++` can still lose updates because `++` is read–modify–write.
- A `volatile Message reference` does not automatically protect every field inside `Message` if the object continues to be modified without synchronization after publication.
- A volatile flag is not an efficient waiting mechanism for long durations. For notification/completion protocols, prefer blocking primitives such as a latch or future.

### 4.1 Runnable example: publishing and observing with volatile

The example below uses a volatile flag and a short spin loop **only to clearly observe the mechanism**; in production, use a blocking primitive. The worker is intentionally awaited with `join()` so the program closes its lifecycle properly.

Create `VolatileHappensBeforeDemo.java`:

~~~java
public final class VolatileHappensBeforeDemo {
    private static int payload;
    private static volatile boolean ready;

    public static void main(String[] args) throws InterruptedException {
        Thread reader = new Thread(() -> {
            while (!ready) {
                Thread.onSpinWait();
            }
            System.out.println("Payload: " + payload);
        }, "reader");

        Thread writer = new Thread(() -> {
            payload = 42;
            ready = true;
        }, "writer");

        reader.start();
        writer.start();
        writer.join();
        reader.join();
    }
}
~~~

Run with JDK 17+:

~~~bash
javac VolatileHappensBeforeDemo.java
java VolatileHappensBeforeDemo
~~~

Output when threads are given normal scheduling opportunities:

~~~text
Payload: 42
~~~

`Thread.onSpinWait()` is only a CPU hint; it does **not** create HB. It is the write/read of `ready` that forms the synchronization edge. Despite having proper visibility, a spin loop can still consume CPU and suffer starvation if the scheduler does not run one side. In the practical section below, we use `CountDownLatch.await()` instead of this waiting style.

## 5. Synchronized: both mutual exclusion and memory publication

A monitor lock provides two distinct effects:

1. **Mutual exclusion:** only one thread holds the same monitor at a time. Reads/writes inside the critical section are protected from interleaving by other threads using that monitor.
2. **Happens-before:** unlocking a monitor happens-before a subsequent lock on the **same monitor**. State written under the protocol is published according to the JMM.

Java 17+ example, create `SynchronizedHappensBeforeDemo.java`:

~~~java
public final class SynchronizedHappensBeforeDemo {
    private static final Object LOCK = new Object();
    private static int total;

    public static void main(String[] args) throws InterruptedException {
        Runnable add = () -> {
            for (int i = 0; i < 1_000; i++) {
                synchronized (LOCK) {
                    total++;
                }
            }
        };

        Thread first = new Thread(add, "first");
        Thread second = new Thread(add, "second");
        first.start();
        second.start();
        first.join();
        second.join();

        synchronized (LOCK) {
            System.out.println("Total: " + total);
        }
    }
}
~~~

Compile and run:

~~~bash
javac SynchronizedHappensBeforeDemo.java
java SynchronizedHappensBeforeDemo
~~~

Stdout:

~~~text
Total: 2000
~~~

Every `total++` executes under the same `LOCK` monitor, so no two critical sections overlap. `join()` ensures `main` waits for both threads to finish and publishes the workers' actions to `main`; the final lock acquisition also adheres to the monitor protocol.

If you keep both `join()` calls but remove `synchronized` in the worker, the result can suffer lost updates. `join()` makes results **visible after the thread has finished running**; it does not fix races that occurred **during execution**.

If two threads lock two different objects, they do not share the same monitor and have no mutual exclusion. Do not conclude "both places have `synchronized`" while ignoring **which specific lock** and **all access paths** to the invariant.

## 6. start() and join(): two-way publication along the thread lifecycle

In most simple worker problems, `Thread.start()` and `Thread.join()` already provide the necessary HB edges.

Create `StartJoinVisibilityDemo.java`:

~~~java
public final class StartJoinVisibilityDemo {
    private static final class Job {
        int input;
        int output;
    }

    public static void main(String[] args) throws InterruptedException {
        Job job = new Job();
        job.input = 21;

        Thread worker = new Thread(() -> {
            job.output = job.input * 2;
        }, "calculator");

        worker.start();
        worker.join();

        System.out.println("Result: " + job.output);
    }
}
~~~

Run:

~~~bash
javac StartJoinVisibilityDemo.java
java StartJoinVisibilityDemo
~~~

Stdout:

~~~text
Result: 42
~~~

Reasoning graph:

~~~text
main: job.input = 21
       |
       v  program order
main: worker.start()
       |
       v  start happens-before worker actions
worker: read input, write output = 42
       |
       v  termination detected by join
main: worker.join() completes
       |
       v  program order
main: read output = 42
~~~

Although `input` and `output` are plain `int`s, accesses following this `start`/`join` flow have a proper HB relation. There is no need to mark every field `volatile` if **no other thread accesses them concurrently outside the protocol**.

Note: `Thread.sleep(100)` in `main` after `worker.start()` does not replace `join()`. It only waits for a duration, does not guarantee the worker has finished, and provides no completion edge. A `join(timeout)` that returns while the worker is still alive also does not guarantee all results have been published.

For lifecycle APIs, `Thread.isAlive()` returning `false` after a thread has started and terminated can detect termination under the JMM, but continuously polling `isAlive()` usually wastes CPU. Prefer `join()` to wait directly.

## 7. What is a data race?

Two accesses in different threads **conflict** if they access the same variable and at least one access is a write. When they are not ordered by HB, the program has a **data race**.

Example:

~~~java
int counter; // Shared field.

// Thread A:
counter++;

// Thread B:
counter++;
~~~

This is an illustrative snippet. Each increment consists of reading the old value, computing the new value, and writing it back; both threads can read the same initial value and overwrite each other, leading to lost updates.

**The JMM constrains even programs with data races**, so saying "a data race allows Java to do anything" is inaccurate. However, when required HB edges are missing, the intuition "the source statements ran in the right order so it must be right" is not enough to prove the outcome.

A **correctly synchronized** program as defined by the JMM has no data races in its sequentially consistent executions. Such a program receives the guarantee that its behavior can be explained by *sequential consistency*: operations appear as if interleaved in a total order that respects each thread's program order.

This is a guarantee about **observable memory behavior**; it does not mean threads literally run sequentially, or that there is no CPU contention or no deadlock. A program that uses locks completely correctly can still have business logic bugs or wait indefinitely.

### 7.1 HB is not atomicity

Suppose two threads both run:

~~~java
if (balance > 0) {
    balance--;
    withdrawals++;
}
~~~

To preserve the invariant "balance is non-negative, successful withdrawals count matches," both the check and the updates must be protected as a critical section. Marking `balance` and `withdrawals` as `volatile` does not make the block of statements atomic. You can use the same lock for all read/write paths or an atomic state transition designed for the entire invariant.

HB proves ordered data publication; atomicity ensures no other thread interleaves with an update that requires integrity. In concurrent design, **both must be checked**.

## 8. Safe publication of objects and final fields

*Safe publication* is transferring a reference to another thread via a synchronization mechanism so that the initialized object state is properly observed.

Risky example:

~~~java
final class Settings {
    String host;
    int port;
}

// Thread A, assuming shared is a plain field:
Settings value = new Settings();
value.host = "localhost";
value.port = 8080;
shared = value;

// Thread B:
Settings snapshot = shared;
if (snapshot != null) {
    // Insufficient basis to treat host/port as safely published.
}
~~~

The snippet above omits the declaration of `shared`; it is a **faulty example**, not a standalone program. Because the writer and reader access the reference without synchronization, the reader seeing a non-null reference is not enough to conclude that all initialized state is observed under a safe protocol.

Common publication techniques:

- Write the reference to a `volatile` field and read it back through the same `volatile` field.
- Use the same `synchronized` monitor or `Lock`.
- Pass the object through a `BlockingQueue` or concurrent collection with a corresponding memory-consistency contract.
- Retrieve the object as the result from `Future.get()` after the task completes.
- Publish via valid JVM class initialization.
- Design an immutable object with `final` fields and do not let `this` escape during construction.

### 8.1 Be careful with final

~~~java
final class Endpoint {
    final String host;
    final int port;

    Endpoint(String host, int port) {
        this.host = host;
        this.port = port;
    }
}
~~~

The JMM provides special initialization guarantees for `final` fields when the constructor completes properly and the reference does not escape during construction. These fields are useful for immutable objects. However:

- `final` fixes the **field's reference**, not making the referenced object itself immutable; a `final List<String>` can still point to a mutable list.
- Modifications to mutable state **after the constructor** still require synchronization.
- Do not let `this` escape by registering listeners or starting threads that use the object being constructed before the constructor finishes.

Snapshot publication example:

~~~java
final class Config {
    final String host;
    final int port;

    Config(String host, int port) {
        this.host = host;
        this.port = port;
    }
}

final class ConfigHolder {
    private volatile Config current = new Config("localhost", 8080);

    Config readSnapshot() {
        return current;
    }

    void replace(Config next) {
        current = next;
    }
}
~~~

This is an illustrative snippet. The writer constructs a complete `Config` and replaces the volatile reference; the reader obtains an instance to use for an operation. If `readSnapshot()` is called multiple times, different calls may receive different versions. When a consistent snapshot is needed throughout processing, store the reference in a local variable once.

## 9. java.util.concurrent provides additional memory-consistency effects

Beyond foundational JMM relations, many concurrent classes have specific HB contracts:

| API | Key relation | Limitations to understand |
| --- | --- | --- |
| `CountDownLatch` | Actions before `countDown()` →HB actions after a successful `await()` when count reaches 0. | The latch does not collect task exceptions; `countDown` must happen at the right completion point. |
| `ExecutorService` | Actions before submitting a task →HB actions in the task; actions in the task →HB actions after retrieving the result via `Future.get()`. | Submitting does not mean the task has finished running. |
| `Future.get()` | Task actions →HB actions after retrieving the result via `get()`. | Must distinguish completion, failure, cancellation, and timeout. |
| `BlockingQueue` | Actions before putting an object →HB actions after another thread takes/accesses the element per the contract. | Does not automatically protect modifications to the object after `put`. |
| `Semaphore` | Actions before `release()` →HB actions after a corresponding successful `acquire()`. | Maintaining multi-field invariants still requires its own protocol. |
| `Lock` | Successful lock/unlock operations have memory effects like the corresponding monitor. | Must lock/unlock with the same mechanism and release in `finally`. |
| Atomic classes | Reads/writes/CAS operations have memory effects described by the API. | Separate `get()` then `set()` steps do not automatically combine into an atomic transaction. |

You must read the contract **of the specific primitive**. Do not assume that touching any concurrent collection publishes every update across the entire object graph. HB effects generally apply to data **before** the handoff action and receiving/accessing the element per the API, not protecting updates that occur afterward.

### 9.1 Java 17+ example: no volatile needed when using a latch

Create file `LatchHappensBeforeDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public final class LatchHappensBeforeDemo {
    private static int result;
    private static final CountDownLatch READY = new CountDownLatch(1);

    public static void main(String[] args) throws InterruptedException {
        Thread producer = new Thread(() -> {
            result = 42;
            READY.countDown();
        }, "producer");

        Thread consumer = new Thread(() -> {
            try {
                READY.await();
                System.out.println("Result: " + result);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        consumer.start();
        producer.start();
        producer.join();
        consumer.join();
    }
}
~~~

Run:

~~~bash
javac LatchHappensBeforeDemo.java
java LatchHappensBeforeDemo
~~~

Stdout without external interruption:

~~~text
Result: 42
~~~

`result` is a plain `int`. However, `result = 42` occurs before `READY.countDown()`, and the reader only reads `result` after `READY.await()` succeeds: there is an HB edge from the latch. There is no need to add `volatile` to `result` just to publish that write.

Note that `CountDownLatch.await()` can return when the signal count reaches 0 even if the producer thread is not yet completely `TERMINATED` at that moment; to wait for the `Thread` lifecycle itself to end, `join()` is needed. Here, the two `join` calls also ensure `main` finishes after the workers.

## 10. Double-checked locking: missing volatile can publish brokenly

The lazy initialization pattern with two checks is commonly called *double-checked locking* (DCL). If the shared reference is a plain field, the read branch outside the lock may lack an HB relation with the write branch:

~~~java
final class LazyService {
    private static Service instance; // Wrong: missing volatile.

    static Service getInstance() {
        if (instance == null) {
            synchronized (LazyService.class) {
                if (instance == null) {
                    instance = new Service();
                }
            }
        }
        return instance;
    }
}
~~~

This is a faulty snippet; `Service` is not defined. Only the check inside the lock is synchronized via the monitor. The reader on the fast path outside the lock lacks a complete publication relation with a plain write to `instance`. Fix the field to:

~~~java
private static volatile Service instance;
~~~

With a `volatile` reference and the right protocol, initialization, reference write, and corresponding reference read are ordered. However, DCL has many error-prone details; for a simple lazy singleton, the holder idiom can be easier to read:

~~~java
final class Service {
    private Service() {}

    private static final class Holder {
        static final Service INSTANCE = new Service();
    }

    static Service getInstance() {
        return Holder.INSTANCE;
    }
}
~~~

This is an illustrative class snippet. JVM class initialization has a corresponding synchronization mechanism; when `Holder` is initialized for the first time, the singleton is published under the initialization contract. You must still avoid leaking `this` before the constructor finishes.

## 11. Happens-before does not guarantee liveness

A program can use synchronization properly to ensure consistent state yet still **make no progress**:

- Thread A holds lock L1 and waits for L2; thread B holds lock L2 and waits for L1: deadlock.
- A task in a small pool waits for the result of another task in that same pool's queue: thread-pool starvation.
- A reader waits on a latch that nobody calls `countDown` on: it can block forever.
- A CAS loop retries continuously: the system as a whole may make progress while an individual thread suffers starvation.

HB and the JMM address **valid memory observations**. Liveness/progress addresses **the conditions under which work continues and completes**. For a real program to be correct, you must design both data publication and wait timeouts, cancellation, interruption, and lock acquisition order.

Do not use the fact that multiple threads are still burning CPU as proof that every operation will finish. And do not use `Thread.sleep` to "fix" a race: it only makes the bug appear less often or changes the interleaving.

## 12. Common HB misinterpretations

| Misconception | Correct explanation |
| --- | --- |
| "A ran before B by wall-clock time, so A →HB B." | HB is a JMM relation based on program order/synchronization, not elapsed time. |
| "With `volatile`, all operations are atomic." | `volatile` does not make `count++` atomic. |
| "`Thread.join()` fixes lost updates between workers." | `join` publishes results after the worker finishes; races while the worker is running can still happen. |
| "Any two `synchronized` blocks create HB." | They must use the **same monitor** in the appropriate protocol. |
| "A `final` reference makes the entire object graph immutable." | Only the reference is `final`; mutable objects it points to need separate control. |
| "Once `ready = true`, all subsequent writes are also published." | Signaling HB applies to actions before the synchronizing write; later writes need their own protocol. |
| "`sleep()`, `yield()`, `onSpinWait()` help visibility." | They do not create HB edges for shared data. |
| "Logs show the right output, proving there is no data race." | Logging and the scheduler can mask races; finite tests do not replace a proof. |
| "Sequential consistency means the runtime executes sequentially." | It is a memory-outcome model, not a requirement that the scheduler run one thread at a time. |
| "Using `AtomicInteger` for one field protects every invariant." | You must analyze all state transitions and dependent fields. |

## 13. Process for proving correctness with an HB graph

For a concurrent code snippet, proceed step by step:

1. **State the invariant explicitly.** For example, "balance is non-negative," "config is read as a consistent snapshot," "a task only returns a result after initialization finishes."
2. **List all conflicting accesses.** Which threads read/write the same field? Are there any accesses outside a lock or outside the protocol?
3. **Mark each thread's program order.** Is the payload write before or after the signal? Is the read before or after receiving the signal?
4. **Find real synchronization edges.** Same monitor lock, matching volatile write/read, start/join, latch, future, queue transfer?
5. **Connect edges via transitivity.** Is there a path A →HB B from the write to be published to the read to be guaranteed?
6. **Account for other writers.** Is there any competing write that invalidates a single-value conclusion or creates a data race?
7. **Check atomicity.** Can a multi-step operation be interleaved and break the invariant?
8. **Check liveness.** Can a lock be held forever, can a signal never arrive, are timeouts/interrupts handled?
9. **Write invariant-based tests.** Use barriers/latches to reproduce interleavings and bounded stress tests; do not rely solely on `sleep()` as a condition.
10. **Re-review the code after edits.** Adding one access that bypasses a lock or a writer after publication can break the entire prior reasoning.

Example of a properly published protocol:

~~~text
writer                             reader
------                             ------
payload = 42
   |
   v
volatile ready = true ---------> if (ready)  // volatile read
                                    |
                                    v
                               use(payload)
~~~

If `use(payload)` is moved **before** `if (ready)` or `payload = 42` is moved **after** writing `ready`, the HB path guaranteeing the data no longer matches the diagram.

## 14. Testing concurrency and the limits of trial runs

You cannot use "ran 10,000 times and looked right" to prove a protocol has HB. Data races depend on scheduling, the optimizer, load, runtime, and CPU.

- Use `CountDownLatch` or `CyclicBarrier` to start tasks concurrently and create specific interleaving conditions; do not use `sleep` to guess.
- Assert **exact invariants**, e.g., two threads each incrementing 1,000 times must yield 2,000, rather than asserting the result is greater than 0.
- Stress-test repeatedly with many threads to find bugs, but accept that observing no failures does not prove the program is safe.
- Use concurrency research tools like **OpenJDK jcstress** when you need to explore observable outcomes of small code snippets; interpret the outcomes permitted by the JMM accurately.
- Review the HB graph alongside the atomicity protocol: this is verification that finite testing cannot replace.
- Logging/`println` in a racy section can accidentally add synchronization or alter scheduling, masking bugs; avoid relying on that effect.

Thread dumps help inspect `BLOCKED` or `WAITING` threads when a program hangs, but they do not prove a field was safely published. Keep the observation goals clear: HB for memory consistency, thread dumps for runtime/liveness investigation.

## 15. Self-check questions

**1.** A writer writes `data=42` then `volatile ready=true`; a reader sees `ready==true` and then reads `data`. Why can we conclude it reads 42 if there are no other writers?  
**Answer:** The writer's program order, the volatile write→read edge, and the reader's program order form an HB path from writing `data` to reading `data`.

**2.** If `volatile` is removed from `ready` while keeping the same code order, does the same guarantee hold?  
**Answer:** No. Synchronization is missing; the reading and writing threads can suffer a data race.

**3.** Can `Thread.sleep(100)` after starting a worker replace `join()`?  
**Answer:** No. `sleep` has no HB edge with worker termination; `join` detects completion.

**4.** Two threads both run `volatile int counter; counter++`. Is it guaranteed to reach 2,000 increments?  
**Answer:** No. The compound increment is not atomic; a lock or atomic increment is needed.

**5.** Why don't two `synchronized` blocks using two different objects protect a shared variable?  
**Answer:** Mutual exclusion and the unlock→lock edge only apply to the same matching monitor.

**6.** After `worker.join()`, `main` sees the output written by the worker, but two workers had previously updated it incorrectly. Does `join` fix the bug?  
**Answer:** No. `join` creates visibility after termination; it does not prevent races and lost updates that already occurred.

**7.** An object has `final List<String> items`. Can the list be updated from multiple threads without synchronization?  
**Answer:** No. `final` only fixes the reference; the referenced object is still mutable.

**8.** `CountDownLatch.await()` returns when the count reaches 0. Does the reader see the state the producer wrote before `countDown()`?  
**Answer:** Yes, according to the latch's memory-consistency contract when `await()` returns normally.

**9.** Is a program without data races automatically free of deadlocks?  
**Answer:** No. Safety/visibility and liveness are two different dimensions of correctness.

**10.** What is needed to prove a concurrent invariant?  
**Answer:** Identify accesses, build the HB graph, find competing writers, check atomicity of compound operations, and consider liveness. Tests only supplement reasoning.

**Key takeaway:** *Happens-before* helps prove **properly ordered publication and observation of data** across threads. For a program to be completely correct, you must also protect **atomicity and invariants** as well as address **liveness**. Rely on the explicit contracts of `volatile`, `synchronized`, `start()/join()`, and `java.util.concurrent` rather than delays, logs, or scheduler luck.
