# Atomicity, Visibility, and Ordering in Java

## 1. Three Distinct Guarantees of the Java Memory Model

When two threads share mutable state, a developer needs to answer three questions:

- **Atomicity:** Is an operation executed as an indivisible unit? Can another thread observe an intermediate, partially updated state?
- **Visibility:** When thread A writes a value, what guarantees that thread B reads the published value?
- **Ordering:** Are actions constrained to be observed in a specific order, even though the compiler/JIT and CPU may optimize execution?

The **Java Memory Model (JMM)** defines which cross-thread read/write outcomes are legal under the Java language, along with the guarantees provided when using `volatile`, `synchronized`, and concurrency APIs. It is a language-level model; you should not oversimplify every issue as "data sitting in CPU cache," because the JMM applies across different machine architectures.

The three properties are related but do not replace one another. A `volatile` variable can guarantee visibility and ordering for a data publication protocol, yet `counter++` on that same variable is still not atomic. A lock protecting updates to two fields can preserve an invariant, whereas two independent `AtomicInteger` variables do not automatically form a joint transaction.

### Mental Map

| Property | Question to check | Common Java mechanisms |
| --- | --- | --- |
| Atomicity | Who can interleave between the update steps? | `synchronized`, `Lock`, `AtomicInteger.incrementAndGet()` |
| Visibility | When is a write from one thread visible to another under JMM guarantees? | `volatile`, monitor acquire/release, `join()`, `Future.get()` |
| Ordering | In what order are the effects of actions constrained to be observed? | Happens-before relationship, program order, volatile, lock/unlock |

This lesson only covers concurrency and the JMM in **general Java**. Framework-level synchronization mechanisms are out of scope here.

## 2. Atomicity: "One Statement" Does Not Necessarily Mean "One Operation"

### 2.1. Why can `count++` lose increments?

~~~java
// Illustrative snippet in a shared object; not a standalone program.
int count = 0;

// Two threads execute concurrently:
count++;
~~~

Logically, `count++` reads the old value, adds one, and then writes the result. If A and B both read 0, both can write 1. Two increments that were expected to yield 2 end up producing only 1. This is a **lost update**.

A single read or write of an `int` is atomic as a single operation, but a **read–modify–write** sequence is not atomic by default. `volatile int count` still does not make `count++` atomic.

For `long` and `double` *not declared volatile*, the language specification even permits a 64-bit read/write to be split into two 32-bit halves on some implementations. Conversely, every read/write of a `volatile long` or `volatile double` is guaranteed to be atomic. You should not infer from the behavior of one modern JVM that all implementations are stronger than the language specification.

### 2.2. Java 17+ Example: Controlled Lost-Update Simulation

A random race condition may not appear across many runs. To observe the bug clearly, this example uses `CountDownLatch` to force both workers to **read the old value before either worker writes**. This is an experiment that deliberately constructs an interleaved schedule; it is not an update pattern to use in applications.

Create the file `AtomicityDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicityDemo {
    private static int ordinary = 0;

    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch bothRead = new CountDownLatch(2);
        AtomicInteger safe = new AtomicInteger(0);

        Runnable job = () -> {
            int snapshot = ordinary;
            bothRead.countDown();

            try {
                bothRead.await();
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                return;
            }

            ordinary = snapshot + 1;
            safe.incrementAndGet();
        };

        Thread first = new Thread(job, "writer-1");
        Thread second = new Thread(job, "writer-2");
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("ordinary = " + ordinary);
        System.out.println("atomic = " + safe.get());
    }
}
~~~

Compile and run:

~~~bash
javac AtomicityDemo.java
java AtomicityDemo
~~~

Stdout when the workers finish:

~~~text
ordinary = 1
atomic = 2
~~~

Both read `ordinary == 0` before being allowed to write 1, so one increment is lost. Meanwhile, `AtomicInteger.incrementAndGet()` performs an atomic read–modify–write operation, so the final value is 2. `join()` ensures the `main` thread waits for both workers to finish before printing the results.

The example intentionally splits the operation into two phases. In a real program, if updating a variable lacks a lock or atomic operation, incorrect results may appear only under certain execution schedules.

### 2.3. When to choose atomic classes?

Types such as `AtomicInteger`, `AtomicLong`, `AtomicBoolean`, and `AtomicReference<T>` enable atomic operations on a corresponding single state. For example:

~~~java
// Illustrative snippet, not a standalone program.
AtomicInteger requests = new AtomicInteger();
int current = requests.incrementAndGet();
boolean changed = requests.compareAndSet(1, 2);
~~~

`compareAndSet(expected, update)` (CAS) updates the value only if the current value matches the expected one. A CAS algorithm may need to retry when multiple threads contend; with `updateAndGet(...)`, the update function may also be invoked multiple times. That function should not produce side effects such as sending emails, writing files, or performing network calls.

Atomicity for **a single variable** does not protect an invariant spanning **multiple variables**: deducting from account A's balance and then crediting account B with two separate atomic operations still allows another thread to observe the intermediate state. When you need an update unit across multiple fields, use a shared lock or atomically replace an entire immutable snapshot according to an appropriate design.

CAS can also suffer from the **ABA problem**: a value goes A → B → A and the comparison only sees A, even though the state changed in between. If change history is part of the invariant, you must choose a different protocol or version the state.

## 3. Visibility: Writing Does Not Guarantee Another Thread Reads the Right Value

### 3.1. Unsafe Stop-Flag Scenario

~~~java
// Unsafe illustration: running is a plain variable used by two threads.
boolean running = true;

// Worker:
while (running) {
    processWork();
}

// Control thread:
running = false;
~~~

Without synchronization between the two sides, the JMM does not guarantee that the worker will observe the control thread's write of `false`. The compiler/JIT and CPU may optimize within the bounds of the JMM, and observing code "work correctly" on one machine does not prove the program is correct according to the specification.

For a simple flag protocol, you can use:

~~~java
// Illustrative snippet in a class shared between two threads:
private volatile boolean running = true;
~~~

`volatile` establishes visibility and ordering guarantees when two threads write/read this variable according to the proper protocol. However, **visibility is not liveness**: if the worker is blocked on I/O without checking the flag or is not scheduled, merely flipping the flag will not make it stop immediately. For long-waiting operations, use appropriate coordination primitives or interrupts instead of spinning indefinitely.

### 3.2. Happens-Before: The Precise Way to Express It

**Happens-before (HB)** is a logical ordering relationship in the JMM. It determines whether one action is guaranteed to be ordered before another in the memory observation model. You should not treat HB as merely wall-clock order or the order of log lines.

Important HB edges:

| Rule | Guarantee |
| --- | --- |
| **Program order** | Within a single thread, earlier actions in program order HB later actions |
| **Monitor** | An unlock on a monitor HB a subsequent lock by another thread on the same monitor |
| **Volatile** | A volatile write synchronizes-with a subsequent corresponding volatile read in synchronization order |
| **Start** | A call to `Thread.start()` HB the actions of the started thread |
| **Join** | The actions of a worker HB the actions of another thread after `join()` completes successfully |
| **CountDownLatch** | Actions before `countDown()` HB actions after `await()` returns successfully |
| **Executor/Future** | Under the API's memory consistency contract, actions before submission HB the task; actions of the task HB actions following `Future.get()` |

HB is **transitive**: if A HB B and B HB C, then A HB C. This is especially important in **safe publication**: write the data first and then publish a volatile flag; another thread reads that flag and then reads the data.

Seeing a new value without a reliable HB protocol does not prove that all subsequent runs will be correct. Conversely, `Thread.sleep(...)` does not create an HB relationship on its own; waiting for a duration only affects scheduling.

### 3.3. Java 17+ Example: Publishing Data via `volatile`

Create the file `VolatilePublicationDemo.java`:

~~~java
public class VolatilePublicationDemo {
    private static int payload;
    private static volatile boolean ready;

    public static void main(String[] args)
            throws InterruptedException {
        Thread reader = new Thread(() -> {
            while (!ready) {
                Thread.onSpinWait();
            }
            System.out.println("payload = " + payload);
        }, "reader");

        reader.start();

        payload = 42;
        ready = true;

        reader.join();
    }
}
~~~

Compile and run:

~~~bash
javac VolatilePublicationDemo.java
java VolatilePublicationDemo
~~~

Once the reader is scheduled to run and sees `ready == true`, stdout is:

~~~text
payload = 42
~~~

The `main` thread writes `payload = 42` before writing `ready = true`. The reader thread reads `payload` only after observing that volatile write. Program order, synchronizes-with, and transitivity establish an HB relationship from the write of `payload` to the read of `payload`. Therefore, the data is safely published even though `payload` is not declared `volatile`.

`Thread.onSpinWait()` is only a CPU/JVM hint for a short wait loop; **it does not create synchronization or HB**. The example is meant to illustrate a one-time publication protocol. In real applications, use `CountDownLatch`, `BlockingQueue`, `Future`, or a condition with proper waiting/cancellation support instead of an unbounded spin loop. Do not reuse this pattern by repeatedly resetting `ready = false` and flipping it back without designing a proper state protocol.

## 4. Ordering: Source Code Order and Cross-Thread Observation

### 4.1. The Optimizer Can Reorder Execution Within the JMM

Within a single thread, Java preserves **as-if-serial** semantics: optimizations must not alter the result that a single thread is permitted to observe. That does not mean every statement must be physically executed by the CPU in exact source order.

When threads access shared mutable state without synchronization, the cross-thread observations can be broader than the set of outcomes a reader of sequential code expects. You should not infer that "line 1 appears before line 2" automatically creates a visibility relationship for another thread.

### 4.2. The Two-Variable Problem and Counterintuitive Outcomes

Suppose `x = 0` and `y = 0` initially. Two threads execute:

~~~java
// Conceptual illustration, not a standalone program.
// Thread A:               // Thread B:
// x = 1;                  y = 1;
// r1 = y;                 r2 = x;
~~~

If `x` and `y` are plain variables with no HB between the two threads, the JMM allows an execution in which `r1 == 0` **and** `r2 == 0`. If all actions had to interleave strictly in a single global sequential order while preserving each thread's program order, that outcome could not occur. This example helps illustrate the consequences of data races and missing ordering constraints.

If both `x` and `y` are declared `volatile`, the volatile accesses participate in a total synchronization order consistent with program order; the outcome where both read 0 is no longer legal under the sequence above.

**Important note:** "Allowed by the JMM" does not mean a single run on a specific machine will definitely exhibit that result. Do not write tests expecting to reliably observe reordering effects; the takeaway must be grounded in the memory model's contract.

### 4.3. Data Races and Sequential Consistency

Two actions that access **the same variable**, where at least one is a write, and are not ordered by HB form a **data race**. For example, two threads concurrently executing `count++` on a plain variable can create a data race.

For **correctly synchronized** programs (free of data races under the JMM standard), Java provides the strong guarantee of **sequential consistency**: execution can be understood as an interleaving of actions in a single total order that preserves each thread's program order.

Sequential consistency does not dictate which thread runs first, nor does it eliminate deadlock, starvation, or business-logic bugs. It only narrows the set of legal memory behaviors so developers can reason consistently.

## 5. What Does `volatile` Solve and What Does It Not Solve?

`volatile` is often suitable for one-way status flags or publishing data under a designed protocol. It guarantees that individual reads/writes of the volatile variable have the corresponding visibility and ordering semantics; reads/writes of `volatile long/double` are also always atomic.

However, none of the following are **automatically guaranteed by `volatile`**:

- `volatileCounter++` is an atomic read–modify–write.
- Updates to two fields can be observed as a single transaction.
- `volatile List` makes the referenced `ArrayList` thread-safe.
- Another blocked thread will automatically wake up as soon as the flag changes.
- All mutable data behind a volatile reference becomes immutable or self-protected against concurrent modification.
- Side effects on a database, file, or network are rolled back when a thread fails.

~~~java
// Incorrect illustration: despite volatile, the increment is not atomic.
private volatile int counter = 0;

void increment() {
    counter++;
}
~~~

To count accurately, use `AtomicInteger.incrementAndGet()` or `synchronized`/locks. For algorithms that must read state and then decide on an update, you need to protect the entire **check-then-act** sequence. You cannot just put `volatile` on a variable and expect the condition check and update sequence to become atomic.

### Safe Publication and `final` Fields

An object should be completely initialized before another thread uses it. Common safe publication patterns include assigning the reference via `volatile`/atomic, passing the object through a concurrent queue, accessing it under a lock, or creating the data before calling `Thread.start()`.

`final` fields receive special initialization guarantees from the JMM when the constructor executes properly and the `this` reference does not escape during construction. However, `final List<String> items` only prevents the `items` **reference** from being reassigned; it does not make the underlying list immutable. If a mutable object still has multiple writers, those writers must be coordinated.

Avoid registering callbacks, placing `this` into shared structures, or starting threads inside a constructor before the object is fully initialized.

## 6. `synchronized`: Mutual Exclusion and HB Guarantees

A `synchronized` block uses a **monitor lock**. Threads that abide by the same lock receive:

1. **Mutual exclusion:** while one thread holds the lock, another thread cannot concurrently enter a synchronized region using the same monitor.
2. **Visibility:** an unlock from an earlier thread has an HB relationship with a subsequent lock on the same monitor.
3. **Ordering:** acquire/release semantics ensure actions inside the critical section are published according to the locking protocol.

You must ensure that all read/write paths for the same invariant obey **the same lock**. If a writer locks but a reader reads a field directly from outside, whether the reader gets a valid snapshot is no longer guaranteed by that lock.

### Java 17+ Example: Protecting a Two-Variable Invariant

Create the file `SynchronizedInvariantDemo.java`:

~~~java
public class SynchronizedInvariantDemo {
    static final class Balances {
        private int left = 100;
        private int right = 0;

        synchronized void move(int amount) {
            if (amount < 0 || amount > left) {
                throw new IllegalArgumentException("Invalid amount");
            }
            left -= amount;
            right += amount;
        }

        synchronized String snapshot() {
            return "left=" + left
                + ", right=" + right
                + ", total=" + (left + right);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Balances balances = new Balances();
        Thread first = new Thread(() -> balances.move(40));
        Thread second = new Thread(() -> balances.move(60));

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println(balances.snapshot());
    }
}
~~~

Compile and run:

~~~bash
javac SynchronizedInvariantDemo.java
java SynchronizedInvariantDemo
~~~

Stdout when both workers finish:

~~~text
left=0, right=100, total=100
~~~

Because each `move` holds the lock across both the check and the two update operations, any execution order of the two threads is valid: both 40 and 60 are transferred, and the total is always 100. `snapshot()` also uses the same monitor, so when called, it never observes a transfer in mid-update. `join()` ensures `main` prints the result after the workers finish.

This example only describes data **in the memory of a single JVM**. `synchronized` is not a database transaction and does not automatically protect state in another process.

### `Lock` and Scope of Critical Sections

`ReentrantLock` is another option when you need `tryLock()`, interruptible locking, or flexible wait conditions. Always release the lock in a `finally` block:

~~~java
// Illustration inside a method; lock is already declared.
lock.lock();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
~~~

Avoid holding a lock while performing long-blocking I/O if possible. An overly broad critical section increases contention; acquiring multiple locks in different orders can cause deadlock. Correctness of invariants must be established first, and only then should you measure and tune performance.

## 7. Other APIs Also Have Memory Consistency Contracts

### 7.1. `Thread.start()` and `Thread.join()`

Actions in the caller before calling `thread.start()` HB the actions of the worker. After the worker finishes, a caller that successfully waits on `thread.join()` receives an HB guarantee for the worker's actions.

~~~java
// Illustrative snippet, not a standalone program.
int[] result = new int[1];
Thread worker = new Thread(() -> result[0] = 99);
worker.start();
worker.join();  // Must handle or declare InterruptedException.
System.out.println(result[0]);  // 99 after join succeeds.
~~~

Do not replace `join()` with `Thread.sleep(100)` just because you guess the worker has had enough time to run; sleep is not an HB edge between two threads.

### 7.2. Executor and Future

Under `ExecutorService`'s contract, actions before submitting a task HB the actions of the task; the actions of the task HB actions after the result is retrieved via `Future.get()`. Even so, **two independent tasks** running in an executor still need their own mechanism if they update a shared variable.

`Future.get()` can block and can throw `ExecutionException` if the task fails. `get(timeout, unit)` limits how long the caller waits; it does not automatically cancel a running task. Cancellation, timeouts, and exceptions must be managed explicitly.

### 7.3. CountDownLatch and BlockingQueue

`CountDownLatch` establishes a memory consistency relationship from actions before `countDown()` to actions after `await()` succeeds. `BlockingQueue` provides an element-passing mechanism and a suitable data publication contract between producer and consumer. These primitives are usually clearer than sharing multiple plain boolean flags and guessing each other's state.

## 8. Design for the Requirements, Not Out of Habit by Adding `volatile`

| Scenario | Suitable tool | What to check |
| --- | --- | --- |
| Simple stop flag, worker actively polls | `volatile boolean` | Does the thread actually loop back to read the flag or get woken up? |
| Counting independent events | `AtomicInteger` or `LongAdder` when appropriate | Is an exact snapshot needed while updates are happening? |
| Transferring value between two fields, preserving invariant | `synchronized` or `Lock` | Do all read/write paths follow the same protocol? |
| Publishing fully initialized data | Volatile reference, immutable snapshot, queue, start/join | Can the reference escape before initialization finishes? |
| Multiple threads modifying a collection | Appropriate concurrent collection | Does a "check-then-write" sequence need to be atomic? |
| No shared state needed | Thread confinement, immutable values, message passing | Can the design avoid locks from the start? |

`LongAdder` helps reduce contention for heavy addition in statistical use cases. However, `sum()` is not an atomic snapshot while updates are still in progress; do not use it as a transactional counter that requires exact instantaneous condition checks.

With shared data, the key is to design the **ownership and publication protocol** before choosing a tool; code can be free of data races and still have deadlock, starvation, or business-logic bugs.

## 9. Common Mistakes

**"A single Java statement is atomic."** False for `count++`, `map.get(k)` followed by `map.put(k, v)`, or check-then-act sequences.

**"Having `volatile` is enough for thread safety."** False for multiple variables that must stay consistent or a mutable object modified concurrently.

**"Seeing the new value once proves visibility is guaranteed."** A passing test run is no substitute for HB analysis; JIT optimizations and thread schedules can differ on other runs.

**"`Thread.sleep` creates ordering."** Sleep affects scheduling rather than creating the required HB synchronization relationship.

**"Use `synchronized` when writing, no need when reading."** A reader can observe an inconsistent state if it reads outside the locking protocol.

**"Using two `AtomicInteger` instances is a transaction."** Each update to one variable is atomic; two updates are not guaranteed to be observed together by others.

**"No race seen in stress tests means correctness is proven."** Tests can uncover bugs, but they cannot exhaustively check every legal execution. You must reason according to the JMM and audit every access path.

**"Data-race-free means the application has no concurrency bugs."** False: deadlock, business-order logic, timeouts, and liveness can still be wrong even when every memory access is synchronized.

## 10. Testing and Observing Behavior

When testing JMM properties, measure **invariants**, not just whether the program throws an exception:

1. For **atomicity**, have multiple writers update concurrently and compare the result against the expected total. You can use a latch/barrier to deliberately create contention, as in `AtomicityDemo`.
2. For **visibility**, identify which HB edge publishes the data. Tests should not rely on sleep as the sole signal; use timeouts and proper coordination mechanisms.
3. For **ordering**, analyze which executions are/are not permitted by the JMM. An outcome that "can happen" will not necessarily appear on every JVM.
4. For **multi-field invariants**, have readers observe while writers update, and verify that every full snapshot is valid.
5. For performance, monitor lock contention, CPU, throughput, latency, queue wait times, and thread states using a profiler, thread dumps, or Java Flight Recorder when appropriate.

Stress tests and specialized tools like JCStress can help detect certain cross-thread behaviors. They support sound reasoning, not replace proof under JMM rules. Also distinguish performance measurement from memory-safety testing.

## 11. Self-Check Questions

**1.** Why can `volatile int counter` still lose updates when two threads concurrently run `counter++`?

Because `volatile` does not turn the read–add–write combination into an atomic operation; two threads can both read the old value. Use `AtomicInteger.incrementAndGet()` or an appropriate lock.

**2.** One thread writes `payload = 42` and then `ready = true` where `ready` is `volatile`; another thread reads `ready == true` and then reads `payload`. Which guarantees make this publication safe?

Program order, the volatile synchronizes-with rule, and the transitivity of happens-before establish an HB relationship from the write of `payload` to the read of `payload`.

**3.** Do two `AtomicInteger` variables managing two balances automatically guarantee that the total remains correct when transferring an amount between them?

No. A single update on each variable is atomic, but the two updates do not form a joint transaction. You need a lock or an immutable snapshot representation with an appropriate atomic update.

**4.** Why does running code successfully many times still not prove that unsynchronized code is thread-safe?

Because those runs only explore a subset of possible execution schedules. A data race may simply not have manifested yet; correctness must be reasoned from JMM guarantees and program invariants.

**5.** If a thread waits with `Thread.sleep(200)` after starting a worker and then reads the result, is it guaranteed to see all of the worker's updates?

No. Sleep does not wait for the worker to finish and does not create a happens-before edge. Use `join()`, `Future.get()`, or a primitive suited to the problem.

**Conclusion:** **Atomicity** protects the integrity of an operation; **visibility** guarantees data publication; **ordering** constrains observation order. Proper concurrency design in Java requires establishing sufficient happens-before relationships and protecting entire shared invariants, rather than just adding `volatile` or `synchronized` without understanding their scope.
