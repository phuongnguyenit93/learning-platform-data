# Choosing Atomic, Lock, or Thread Confinement in Java Concurrency

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish **atomic variables**, **locks**, and **thread confinement** by their data-protection goal, not merely by Java syntax.
- Identify the **invariant** to preserve, the scope of atomic updates, the number of threads with ownership, and the *happens-before* relationships before choosing a mechanism.
- Use **AtomicInteger**, **AtomicLong**, **AtomicReference**, and **compareAndSet (CAS)** for independent updates or transitioning an immutably encapsulated state.
- Use **synchronized** or **ReentrantLock** when a decision requires protecting multiple reads/writes within the same critical section; understand why reads and writes must follow the same locking protocol.
- Organize **thread confinement**, **thread-local state**, or a state-owning worker to reduce the need to share mutable state; recognize the limitations of **ThreadLocal**, thread pools, ownership transfer, and callbacks.
- Avoid common misconceptions: "atomic means the entire business operation is atomic", "volatile replaces locks", "ThreadLocal automatically makes everything thread-safe", or "no data race means definitely correct".
- Write, run, and test Java 17+ against result specifications instead of relying on sleep or non-deterministic log ordering.

This lesson belongs to **general Java concurrency**, in the **Atomic & CAS** group. Spring-specific mechanisms have their own chapter and are outside the scope of this lesson.

## 2. Three Options for Solving the Same Problem

Suppose multiple threads need to process ticket booking requests. One design uses an atomic variable for the remaining ticket count; another holds a lock while checking the ticket count, recording the order, and updating the total; a third design ensures **only one worker is allowed to mutate** the booking state and other threads send requests to that worker.

All three can be valid if the **specification and data-ownership protocol** fit. There is no single "fastest" or "most correct" choice for every problem.

| Option | Central Idea | Works Well When | Watch Out For |
| --- | --- | --- | --- |
| **Atomic / CAS** | A single atomic operation on one variable or one reference representing state | Counters, flags, CAS state transitions, immutable snapshots | Chaining multiple separate atomic operations still has logic races |
| **Lock** | Only one thread at a time executes a critical section protecting an invariant | Multiple related fields, check–then–act, read-modify-write operations | Deadlock, holding locks too long, choosing the wrong lock, missing unlock paths |
| **Thread confinement** | Prevent multiple threads from touching mutable state concurrently | Sequential processors, per-thread scratch data, clear ownership | Leaked references, multiple workers accessing concurrently, thread pools and thread hops |

**The solution starts with the question "what must be true?",** not by picking AtomicInteger or synchronized out of habit.

## 3. Design Questions Before Choosing a Mechanism

Answer these in order:

1. **Where does the mutable state live?** Is it an integer, a pair of balances, a queue, or an entire object graph?
2. **Which threads are allowed to read or write?** A single thread, a few workers within the same JVM, or multiple JVMs/processes?
3. **What is the invariant?** For example, total money is conserved, stock is non-negative, or a job is claimed only once.
4. **How many steps does the atomic decision require?** Just an increment; or reading stock, checking, decrementing, and recording the result?
5. **Is there ownership transfer?** Are tasks submitted via a queue, which thread do callbacks run on, and are mutable objects returned?
6. **Is blocking needed or should it be avoided?** Can the system tolerate contention, CAS retries, or must it support timeouts/cancellation?
7. **Are there external side effects?** Writing to a DB, file, sending email, or calling a service does not become a transaction just by using Java atomics/locks.
8. **What needs to be measured?** Throughput, contention, fairness, tail latency, memory, and maintenance complexity.

If only **one independent value** needs atomic updates, atomics are usually simple. If **multiple fields must change together**, a lock or an immutable snapshot swapped via CAS may be appropriate. If you can **avoid sharing state to eliminate synchronization**, thread confinement often reduces complexity. That is a starting point, not a rigid rule.

## 4. Foundations: Atomicity, Visibility, Ordering, and Happens-Before

Concurrency issues often mix three properties:

- **Atomicity:** does the required operation execute as an indivisible unit without interleaving?
- **Visibility:** do other threads see the writes that have been performed?
- **Ordering:** which operations must occur before others?

The **Java Memory Model (JMM)** uses the **happens-before** relationship to define the visibility and ordering of actions.

Several key relationships:

- Actions before **Thread.start()** happen-before actions in the newly started thread.
- Actions in a completed thread happen-before actions in another thread after **join()** returns because the target thread has finished.
- **Unlocking** a monitor happens-before every subsequent **lock** on that same monitor.
- Writing to a **volatile** variable happens-before subsequent volatile reads of that variable in synchronization order.
- Atomic classes provide memory semantics per their API contract, and operations like **compareAndSet** also perform check-and-update atomically.

**Thread.sleep()**, **Thread.yield()**, and logs appearing in a "seemingly correct" order do not substitute for happens-before.

### Volatile Does Not Make a Sequence of Steps Atomic

~~~java
// Illustrating a bug in a class with a shared field:
volatile int count;

// Two threads call concurrently:
count++; // Still consists of read, add, and write: not an atomic increment.
~~~

Volatile fits certain **status flags** or **reference publication**, but **count++** still requires AtomicInteger, synchronized, or a single-owner solution if an exact count must be maintained.

### Having No Data Race Can Still Be Logically Wrong

~~~java
// Illustrating a logic race: stock is an already created AtomicInteger.
if (stock.get() > 0) {
    stock.decrementAndGet();
}
~~~

Each AtomicInteger call is thread-safe, yet two threads can both observe stock equal to 1 and both decrement it, leaving stock at -1. **The "non-negative stock" invariant is broken** because check–then–act is not atomic.

## 5. Atomic: When a Single Variable Is the Right Unit of Decision

Classes in **java.util.concurrent.atomic** provide reads, writes, increments, additions, CAS, and functional updates on a single unit of state.

Examples:

| API | Common Use Case | Limitations to Remember |
| --- | --- | --- |
| **AtomicInteger / AtomicLong** | Counters, sequences, numeric state | Does not turn multiple separate variables into a single transaction |
| **AtomicBoolean** | One-time state transition flags | A boolean cannot express complex multi-stage business states |
| **AtomicReference<T>** | Publishing or CAS-ing a reference to a snapshot | Object T should be designed as immutable or synchronized on mutation |
| **AtomicIntegerArray** and atomic arrays | Element updates with corresponding atomic guarantees | Multiple elements are not automatically updated together |
| **LongAdder** | High-contention additive statistics | **sum() is not an atomic snapshot** while updates are in flight |

**CAS** compares the current value against an expected value and writes the new value only if the comparison succeeds. CAS can fail because another thread just updated the value; the program typically needs to retry. Do not assume CAS retries are free or guarantee fair service for every thread.

### Example 1: Accurate Counting with AtomicInteger

File **AtomicCounterChoiceDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounterChoiceDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger counter = new AtomicInteger();

        Runnable increment = () -> {
            for (int i = 0; i < 10_000; i++) {
                counter.incrementAndGet();
            }
        };

        Thread first = new Thread(increment, "first");
        Thread second = new Thread(increment, "second");

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("count = " + counter.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AtomicCounterChoiceDemo.java
java AtomicCounterChoiceDemo
~~~

Stdout:

~~~text
count = 20000
~~~

**Why choose atomic?** Each request only needs to increment a shared counter, with no invariant spanning multiple fields. **incrementAndGet()** guarantees an atomic increment; **join()** only makes main wait for both workers before printing, and is not the mechanism fixing lost updates.

If the counter is only for multi-threaded statistics and does not need an exact total read immediately during updates, consider LongAdder; however, do not replace AtomicLong with LongAdder when the API requires **getAndIncrement**, a linear sequence, or an immediate snapshot.

## 6. Atomic CAS: Checking a Condition and Updating in One Operation

Suppose there is exactly **1 ticket** and two threads try to book simultaneously. Invariant: accept at most 1 request and keep remaining tickets non-negative.

If you only use **get()** followed by **decrementAndGet()**, both threads can pass the check. CAS solves this by **decrementing only if the value has not changed**.

File **AtomicReservationDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicReservationDemo {
    static boolean reserve(AtomicInteger stock) {
        while (true) {
            int seen = stock.get();
            if (seen <= 0) {
                return false;
            }

            if (stock.compareAndSet(seen, seen - 1)) {
                return true;
            }
            // Another thread modified stock: re-read and retry.
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicInteger stock = new AtomicInteger(1);
        AtomicInteger accepted = new AtomicInteger();

        Runnable buyer = () -> {
            if (reserve(stock)) {
                accepted.incrementAndGet();
            }
        };

        Thread first = new Thread(buyer, "buyer-1");
        Thread second = new Thread(buyer, "buyer-2");
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("accepted = " + accepted.get());
        System.out.println("remaining = " + stock.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AtomicReservationDemo.java
java AtomicReservationDemo
~~~

Stdout:

~~~text
accepted = 1
remaining = 0
~~~

CAS guarantees that only one **1 → 0** transition succeeds. The other thread observes state 0 and rejects. There is no reliance on which thread runs first.

**Important limitation:** This example only manages ticket count in the memory of **a single JVM**. If after CAS succeeds you also call payment, save an order, or send a notification, those side effects are **not part of a single transaction with CAS**. Distinguish between **a granted reservation** and **a completed business transaction**, and design retries, rollback/compensation, and idempotency accordingly.

### Why Can a CAS Loop Be Hard to Maintain?

If the transition logic involves multiple mutable fields, nested collections, complex conditions, or operations requiring I/O, building a new state and CAS-ing can incur allocation overhead, repeat many times, and easily cause duplicate side effects if external actions are placed inside the retry loop.

A key rule: **the function computing the new state in a CAS loop should be pure (no non-repeatable side effects)**. A failed CAS does not mean the function was invoked only once.

## 7. Multiple Fields Can Still Use CAS If Encapsulated in an Immutable Snapshot

Do not take "atomic is only for one field" literally. You can encapsulate **the entire invariant set** into an **immutable record** and swap **a single reference** via CAS. Every reader then receives a **consistent snapshot**.

For example, two fields **available** and **reserved** have the invariant:

- available is non-negative.
- reserved is non-negative.
- available + reserved always equals the initial total.

File **AtomicSnapshotDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicSnapshotDemo {
    record Inventory(int available, int reserved) {}

    static boolean reserveOne(AtomicReference<Inventory> ref) {
        while (true) {
            Inventory old = ref.get();

            if (old.available() <= 0) {
                return false;
            }

            Inventory next = new Inventory(
                    old.available() - 1,
                    old.reserved() + 1
            );

            if (ref.compareAndSet(old, next)) {
                return true;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicReference<Inventory> ref =
                new AtomicReference<>(new Inventory(100, 0));

        Runnable task = () -> {
            for (int i = 0; i < 50; i++) {
                reserveOne(ref);
            }
        };

        Thread[] threads = new Thread[4];
        for (int i = 0; i < threads.length; i++) {
            threads[i] = new Thread(task, "worker-" + i);
            threads[i].start();
        }
        for (Thread thread : threads) {
            thread.join();
        }

        Inventory end = ref.get();
        System.out.println("available = " + end.available());
        System.out.println("reserved = " + end.reserved());
        System.out.println(
                "total = " + (end.available() + end.reserved())
        );
    }
}
~~~

~~~bash
javac -encoding UTF-8 AtomicSnapshotDemo.java
java AtomicSnapshotDemo
~~~

Stdout:

~~~text
available = 0
reserved = 100
total = 100
~~~

**Why is this correct?** Each CAS transition swaps **one reference** to a fully constructed Inventory object. Readers observe a complete version and never see an intermediate state where available has decreased while reserved has not yet increased. Four workers make 200 total reservation attempts for only 100 tickets; the remaining attempts are rejected.

**Required conditions:**

- Inventory is **immutable** in this example: the record holds only two int values, with no mutable collection exposed.
- Every change relevant to the invariant goes through **the same AtomicReference**.
- No irreversible operations exist inside the CAS loop.
- Readers needing a consistent snapshot must read **ref.get() once**, then use the fields of that same snapshot; do not read the reference twice to fetch two fields and treat them as one version.

If the state is very large, allocation/GC or CAS retries under contention can be costly. For multi-step logic, a lock may be easier to understand.

### ABA and Reference Identity

CAS can encounter **ABA**: a value changes A→B→A, so a thread sees "still A" even though the state underwent a change. This matters when semantics depend on history or version, especially in lock-free data structures.

If you need to detect every change, you can attach a **version** in the immutable state or consider **AtomicStampedReference**. With CAS on references to **newly allocated** immutable records as in this example, each replacement uses a new object so it does not revert to the exact same old reference, though that does not mean every system using AtomicReference is immune to ABA.

## 8. Lock: Protecting a Multi-Step Critical Section

When a decision involves multiple fields that must be updated together, **synchronized** or **ReentrantLock** is often more intuitive than CAS over complex state. A lock protects an **invariant**, not merely a single variable.

For example, an inventory has two fields **available** and **reserved**. If you use two independent AtomicIntegers:

~~~java
// Illustrating a bug if a consistent snapshot is required:
available.decrementAndGet();
reserved.incrementAndGet();
~~~

Each individual update is atomic, yet a reader can observe a state where **available has decreased but reserved has not yet increased**. A shared ReentrantLock across read/write methods prevents that case.

### Correct ReentrantLock Pattern

~~~java
// Illustrative code in a class with a ReentrantLock lock and shared state.
lock.lock();
try {
    // Read condition + update the entire invariant.
} finally {
    lock.unlock();
}
~~~

**finally** is crucial: if the code throws an exception or returns early, the thread must release the lock. Conversely, if **tryLock()** returns false or **lockInterruptibly()** throws InterruptedException **before acquiring the lock**, you must not unlock a lock you do not own.

### Example 4: Lock Protecting Stock and Reserved Count

File **LockedInventoryDemo.java**:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public class LockedInventoryDemo {
    static final class Inventory {
        private final ReentrantLock lock = new ReentrantLock();
        private int available = 100;
        private int reserved;

        boolean reserveOne() {
            lock.lock();
            try {
                if (available == 0) {
                    return false;
                }

                available--;
                reserved++;
                return true;
            } finally {
                lock.unlock();
            }
        }

        int[] snapshot() {
            lock.lock();
            try {
                return new int[] {available, reserved};
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Inventory inventory = new Inventory();

        Runnable task = () -> {
            for (int i = 0; i < 50; i++) {
                inventory.reserveOne();
            }
        };

        Thread[] workers = new Thread[4];
        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(task, "worker-" + i);
            workers[i].start();
        }
        for (Thread worker : workers) {
            worker.join();
        }

        int[] end = inventory.snapshot();
        System.out.println("available = " + end[0]);
        System.out.println("reserved = " + end[1]);
        System.out.println("total = " + (end[0] + end[1]));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LockedInventoryDemo.java
java LockedInventoryDemo
~~~

Stdout:

~~~text
available = 0
reserved = 100
total = 100
~~~

**Difference from AtomicSnapshotDemo:** Inventory keeps two separate **mutable** fields, but all reads/writes related to the invariant go through **the same ReentrantLock**. Inside the critical section, checking then decrementing available and incrementing reserved execute as one unit for threads following the protocol.

**Locks are suitable when:**

- Multiple fields or a collection with complex operations must be protected.
- Multiple conditions must be checked before committing.
- Logic must modify multiple memory locations simultaneously where CAS on a snapshot becomes cumbersome.
- Waiting paths via **Condition** (with ReentrantLock) or monitor wait/notify are needed.
- Specific coordination is required such as tryLock, timed waiting, or interruptible lock acquisition.

**A lock does not automatically create a DB transaction**, nor does it protect instances in other JVMs. Do not hold a lock across network calls or long I/O when steps can be safely separated, as that increases contention and deadlock risk.

### synchronized or ReentrantLock?

| Criterion | synchronized | ReentrantLock |
| --- | --- | --- |
| Release on scope exit | Automatically releases monitor | Must place unlock in finally |
| Reentrant | Yes | Yes |
| Memory visibility | Monitor unlock/lock provides happens-before | Lock/unlock provides corresponding semantics |
| Non-blocking acquisition attempt | No try-enter syntax | tryLock() |
| Timed lock waiting | Not directly | tryLock(timeout, unit) |
| Interruptible while waiting to acquire | Does not throw InterruptedException on monitor entry | lockInterruptibly() |
| Condition waiting | Object.wait/notify | Condition.await/signal |
| Configurable fairness | No | Optional, though not absolute fairness |

**Prefer the simplest option that meets the requirements**. Do not claim ReentrantLock is always faster than synchronized; performance depends on JIT, contention, and lock hold time.

## 9. Thread Confinement: Reduce Sharing Instead of Locking More

**Thread confinement** organizes ownership so that mutable state is **accessed by only one thread** during its period of use. If there is no concurrent access from other threads, the state itself may not need atomics or locks.

Types of confinement:

1. **Stack/local confinement:** local variables and objects created inside a method without letting references escape to other threads. A "local variable" is not automatically safe if it points to a **shared object**.
2. **Thread-local confinement:** each thread has its own copy of data, potentially using **ThreadLocal<T>**. It does not automatically aggregate results across multiple threads.
3. **Ownership confinement:** a single worker/actor/event loop is granted **exclusive authority** to update state; other threads send messages/tasks and receive results through a synchronized protocol.

The core point is **access control**, not merely placing a variable into ThreadLocal. If a reference to a mutable object leaks out, ownership can be broken.

### Example 5: A Worker Owns the Counter, No Lock Needed Inside the Counter

File **ConfinedCounterDemo.java**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ConfinedCounterDemo {
    static final class Counter {
        private int value;

        void increment() {
            value++; // Safe if only the owner thread mutates it.
        }

        int snapshot() {
            return value;
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService owner = Executors.newSingleThreadExecutor();
        Counter counter = new Counter();

        try {
            for (int i = 0; i < 1_000; i++) {
                owner.submit(counter::increment);
            }

            Future<Integer> result = owner.submit(counter::snapshot);
            System.out.println("value = " + result.get());
        } finally {
            owner.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConfinedCounterDemo.java
java ConfinedCounterDemo
~~~

Stdout:

~~~text
value = 1000
~~~

**Why is this correct?**

- A single-thread executor executes submitted tasks sequentially; calls to **counter.increment()** do not overlap.
- Main **does not directly read/write counter.value** while the owner is processing. Instead, main submits a **counter.snapshot()** read task to the owner itself, then retrieves the result via **Future.get()**.
- The snapshot task is submitted after the 1,000 increment tasks from the same thread; in a single-worker executor, it runs after those tasks and therefore returns 1,000.
- Future.get() provides the result and corresponding synchronization guarantees to the caller. No synchronized is needed in Counter **because the ownership protocol** eliminates concurrent access to that state.

**Boundary to maintain:** If main or a third thread calls counter.increment() directly while the executor is using counter, confinement is broken and the code faces races again. If a multi-worker thread pool is used instead of **newSingleThreadExecutor()**, tasks are no longer guaranteed to run on the same thread under this model.

Do not treat a single-worker executor as a transaction or durable queue. It does not make external side effects atomic; task failures must be handled via Future, and executor lifecycle requires proper shutdown.

## 10. ThreadLocal: Per-Thread State, Not Per-Request

**ThreadLocal<T>** provides a value bound to **the current thread**. Each thread can receive its own object from **withInitial()**. It is useful for temporary buffers, scratch counters, or context with genuine thread affinity.

~~~java
// Illustrative snippet in a class with the corresponding imports:
private static final ThreadLocal<StringBuilder> BUFFER =
        ThreadLocal.withInitial(StringBuilder::new);

// Inside a thread's execution path:
StringBuilder buffer = BUFFER.get();
try {
    buffer.append("work");
    // Use buffer within this same thread.
} finally {
    BUFFER.remove();
}
~~~

This is an illustrative snippet, not a standalone application.

**Important limitations:**

- **ThreadLocal does not make a shared mutable object private** if the initializer returns the same shared object or the reference is passed between threads.
- **Thread pools reuse threads:** one task finishes and another task running on the same thread may see leftover ThreadLocal data; call **remove() in finally** when the context scope ends.
- **ThreadLocal is per-thread, not per-request or per-logical-task.** A unit of work moving to another thread via an executor/callback does not automatically carry ThreadLocal values along.
- Aggregating data across multiple threads requires an explicit **merge** step or separate synchronization mechanism. Individual ThreadLocal values do not automatically form an accurate global total.
- ThreadLocal lives as long as the thread if not cleaned up, which can retain unwanted references/resources on long-lived threads.

If the problem is "all tasks update a shared balance", do not use ThreadLocal and assume the shared balance is automatically protected. Instead, define ownership or a synchronized aggregation mechanism.

## 11. Confinement Does Not Exempt Safe Publication and Ownership Transfer

Thread confinement is safe when ownership is clear. When data is handed from thread A to thread B:

- Before handover, A may mutate the object freely.
- When transferring ownership to B, a **safe communication protocol** must be used (e.g., BlockingQueue, submitting a task to ExecutorService, CompletableFuture with the appropriate contract).
- After handover, A must not continue mutating that object concurrently while B is using it, unless separate synchronization is in place.
- If multiple readers are needed, you can send an **immutable snapshot** instead of a mutable object.
- If an object is returned to a caller while still being mutated by the owner, treat it as shared mutable state rather than confined.

### Producer/Consumer Communication Example

A producer can create immutable messages and put them into a **BlockingQueue**. A consumer owns the aggregated state and updates it sequentially. The queue provides the communication and memory consistency guarantees defined by its API. However, if the producer keeps a reference to a mutable message and modifies it after put, the consumer can still see races on the message contents; the queue does not "freeze" the object.

**Confinement** is usually simpler when tasks/messages are immutable or contain no shared mutable data.

### Staged Confinement

One thread can build an object completely and then hand **exclusive ownership** to another thread. This is *ownership transfer*, not a requirement that the object live forever on the same thread. What matters is **never having two concurrent owners and ensuring safe publication on transfer**.

## 12. Quick Decision Table by Scenario

| Scenario | Prefer Considering | Reason |
| --- | --- | --- |
| Exact total request count, independent updates | AtomicLong or AtomicInteger | Single atomic increment |
| High-thread-count stats counter, approximate sum during updates is fine | LongAdder | Spreads contention; sum() is not an atomic snapshot during updates |
| A PENDING → RUNNING state claimed by only one thread | AtomicReference/AtomicInteger CAS | Atomic conditional single-variable transition |
| "If tickets remain, decrement by one" on a single count variable | CAS loop | Combines check and update |
| Stock and reserved must update together | Lock or AtomicReference to immutable snapshot | Protects multi-field invariant |
| Multiple checks/rollbacks or mutating large data structures | synchronized/ReentrantLock | Clear critical section and easy to reason about |
| Per-thread scratch buffer, reference never shared | Local/ThreadLocal confinement | Avoids sharing mutable state |
| Event stream processed by one owner | Single-thread executor/actor-style ownership | Serializes updates |
| Updating multiple DB records across multiple instances | DB transaction/conditional update | Java locks/atomics are JVM-scoped only |
| Config snapshot replaced atomically as a whole | Volatile/AtomicReference to immutable snapshot | Read one reference to see a consistent version |
| Need await condition or acquisition timeout | ReentrantLock/Condition, or suitable blocking primitive | Wait/signal API with clear contract |
| Data both processed by a thread pool and mutated directly by caller | Redesign ownership or synchronization | No longer confined |

**Choose by the largest invariant**, not by class name. A system can combine approaches: an owner thread processing tasks, an AtomicLong for independent metrics, and a lock for another shared structure. Each mechanism needs clear ownership boundaries.

## 13. Performance: Do Not Assume Atomic Is Always Faster Than Lock

Under light load, synchronized or ReentrantLock may be more than sufficient. Under heavy load, a CAS loop on the same atomic can retry many times; a lock can also cause contention and context switching. Confinement reduces contention on state but **caps throughput at a single owner's speed**, which can become a bottleneck.

| Mechanism | Potential Costs | What to Measure |
| --- | --- | --- |
| Atomic/CAS | Cache-line contention, retries, spinning, snapshot allocation | CAS failures, throughput, latency |
| Lock | Lock contention, waiting, context switches, fairness overhead | Lock hold/wait time, tail latency |
| Confinement | Queueing delay, messaging overhead, single-owner bottleneck | Queue length, wait latency, consumption rate |
| ThreadLocal | Multiple memory copies, cleanup/thread reuse | Memory footprint, lifecycle |

Do not benchmark by looping once or adding Thread.sleep() and concluding a performance ranking. Test under a representative workload, across multiple contention levels, with warmup/JIT time, and report both throughput and latency. Choices that improve one metric may degrade another.

A **LongAdder.sum()** running while multiple threads update may not reflect an atomic point-in-time value. If exact numbers are needed for ID generation, quota checks, or business decisions, use a mechanism with the right contract rather than choosing LongAdder just for high throughput.

## 14. Anti-Patterns to Avoid

### One AtomicInteger Does Not Protect Other Fields

~~~java
// Illustrating an error if available + reserved must always be consistent:
AtomicInteger available = new AtomicInteger(10);
AtomicInteger reserved = new AtomicInteger();

available.decrementAndGet();
reserved.incrementAndGet();
~~~

Another reader can interleave between the two atomic operations. Fix this with a lock protecting the whole operation, or CAS on an immutable snapshot representing both fields.

### Two Different Locks for the Same State

~~~java
// Illustrating a bug if each caller creates its own lock:
void update() {
    synchronized (new Object()) {
        shared++;
    }
}
~~~

There is no shared monitor across calls, so shared is unprotected. Use a single **private final** lock object shared across all related access paths.

### Non-Atomic Check-Then-Act

~~~java
// Illustrating a bug:
if (jobStatus.get() == PENDING) {
    jobStatus.set(RUNNING);
}
~~~

This example assumes jobStatus is an AtomicReference with predefined PENDING/RUNNING state values. Two threads can both see PENDING and execute the same job. Use **compareAndSet(PENDING, RUNNING)** so only the succeeding thread begins processing.

### Locking Reads/Writes Inconsistently (Locked Write, Unlocked Read)

If the writer holds a lock while the reader reads a plain field outside the lock, the reader does not participate in the same synchronization protocol. Use the same lock for all related access paths, or another design with proper happens-before.

### Using ThreadLocal to "Isolate" a Shared Object

If multiple ThreadLocals hold **the same reference to a mutable ArrayList**, those threads can still mutate the same object. ThreadLocal only separates **slots per thread**; it does not deep-copy objects.

### Returning a Mutable Reference from an Owner

An owner thread owns a HashMap, yet returns that exact HashMap to a caller and continues mutating it. The caller may mutate or iterate concurrently, breaking confinement. Return an immutable copy/snapshot or provide an API that sends commands to the owner.

### Holding a Lock Across Long I/O

~~~java
lock.lock();
try {
    // Network call, sleep, waiting on Future.get(), uncontrolled callback...
} finally {
    lock.unlock();
}
~~~

This snippet is not a standalone program. It can cause contention or deadlock if another thread needs the lock to complete the awaited condition. Hold the lock only for the portion required by the invariant; do not split a critical section blindly if doing so breaks atomicity.

### Thinking "No Data Race" Means Business Correctness

An algorithm can use AtomicInteger everywhere and still have a broken check-then-act. An actor can process messages sequentially and still record the same order twice due to duplicate commands. Java concurrency helps protect data, **it does not define idempotency or transactions**.

## 15. Combined Strategies and System Boundaries

### Atomic for Metrics, Lock for Invariants, Owner for Pipelines

A service might:

- Use a worker owning the state of a report being built.
- Use AtomicLong for the count of tasks accepted from multiple threads.
- Use a lock for a small cache that must update multiple fields together.
- Publish immutable snapshots to readers via AtomicReference.

These are **different synchronization domains**. Using AtomicReference in one domain does not mean you can drop locks in another.

### Boundaries Across Multiple JVMs/Processes

**AtomicInteger, ReentrantLock, synchronized, and ThreadLocal** operate on objects within a single JVM. If multiple processes write to the same account in a database, synchronization is needed **at the shared data store**, such as conditional updates, optimistic locking/versioning, constraints, transactions, or appropriate coordination mechanisms.

For example, in-JVM CAS can prevent two threads from booking the same ticket **within that process**, but cannot prevent two different instances from each selling the last ticket from a local cache. Place the "no global oversell" invariant where the authoritative ticket inventory is managed.

### Cancellation and Retries

If a task is interrupted or times out, atomic/lock/confinement state does not automatically roll back prior actions. Define clearly:

- At what point is processing authority granted?
- Have side effects been committed yet?
- Can retries cause duplicate processing?
- Are late results from an old attempt allowed to overwrite newer state?

Answering these questions is part of business design; do not expect a Java Lock to provide exactly-once execution on its own.

## 16. Testing for Correctness

Write tests against invariants and observable outcomes:

1. **AtomicCounterChoiceDemo**: after both threads join, count always equals 20,000.
2. **AtomicReservationDemo**: with 1 ticket and two buyers, accepted=1, remaining=0.
3. **AtomicSnapshotDemo**: with 100 tickets and 200 attempts, available=0, reserved=100, and total=100.
4. **LockedInventoryDemo**: preserves the same invariant as the snapshot example, using a lock to protect both fields.
5. **ConfinedCounterDemo**: all increments run on the owner and snapshot is executed by the owner after the commands, yielding 1,000.

When designing additional tests:

- Use **CountDownLatch** to create a contended starting point, but do not use the latch as a substitute for synchronization in the code under test.
- Test varying thread counts, contention levels, and exception/interrupt scenarios.
- For locks, verify **return/throw** paths still release the lock; with tryLock, unlock only when acquisition succeeded.
- For confinement, explicitly verify there are no direct calls violating ownership, and that messages/immutable snapshots are safely published.
- For CAS, test failure/retry paths and ensure no non-idempotent side effects sit inside an update function that may be retried.
- Do not conclude "definitely thread-safe" just because a stress test passes a few times; reason from the JMM and invariants.

Log ordering across workers can be non-deterministic; do not assert fixed stdout for unsynchronized sections that may interleave. The five examples above print summaries only **after a clear completion protocol**, so they produce deterministic stdout under normal execution.

## 17. Decision Checklist

**Before writing code:**

- [ ] I have a concrete invariant definition and know which variables belong to it.
- [ ] I know all writers/readers and the relevant thread/JVM boundaries.
- [ ] Can I avoid sharing mutable state altogether?
- [ ] If choosing atomic, does the atomic operation cover **the entire required decision**?
- [ ] If choosing CAS on a snapshot, is the state truly immutable with no side effects during retries?
- [ ] If choosing a lock, do all access paths hold **the same lock**, without creating per-caller locks?
- [ ] With ReentrantLock, is every successful acquisition released by its owner in finally?
- [ ] If multiple locks exist, is there a consistent lock ordering to avoid circular wait?
- [ ] If choosing ThreadLocal, is there cleanup in thread pools and no confusion between per-thread and per-request?
- [ ] If choosing an owner thread, can mutable references leak to other threads?
- [ ] Is there a completion/safe-publication protocol for data passed between threads?
- [ ] Is there a separate strategy for DB, side effects, timeouts, retries, and cancellation?

## 18. Self-Check Questions

**1. Two threads increment a shared counter, unrelated to any other state. What is preferred?**  
You can use **AtomicInteger.incrementAndGet()** or AtomicLong. If it is purely an additive statistics counter under high contention and does not need a linear snapshot, consider LongAdder.

**2. There are two fields stock and reserved; after every update, stock + reserved = total must hold. Are two separate AtomicIntegers enough?**  
No. A reader can observe the two fields at different points in time. Use a lock covering updates/reads or an AtomicReference to an immutable snapshot.

**3. A single worker serializes all updates to a mutable object. Is synchronized needed inside the object?**  
Not necessarily, if ownership confinement is genuine: no other thread accesses it concurrently, and work/result handoffs use safe publication.

**4. Does ThreadLocal guarantee that a request runs on only one thread?**  
No. ThreadLocal is bound to the executing thread, not the request; tasks switching threads will not automatically carry the value. Thread pools can reuse leftover data if remove() is not called.

**5. Can CAS fail even when the current thread's code has no bug?**  
Yes. Another thread may update the value first, making the current value differ from expected. You need a retry or an appropriate handling branch.

**6. Why shouldn't a CAS loop call a payment API inside the retry loop?**  
Because each retry can execute pre-CAS logic multiple times even though only one CAS succeeds. Side effects can be duplicated; separate business steps using an appropriate protocol.

**7. Can synchronized and ReentrantLock protect state across two JVMs?**  
No. Java locks only apply to threads using the corresponding lock object within the same JVM. Cross-process data requires mechanisms at the shared store.

**8. Is it an architectural flaw for an application to use both AtomicLong and ReentrantLock?**  
No. Different variables/invariant groups may require different mechanisms, provided boundaries and ownership are clear.

**9. If a lock is used for writers while readers read a plain field outside the lock, are readers guaranteed to see updates?**  
That cannot be inferred from the writer's lock alone. Readers must participate in the same protocol or have another properly designed happens-before relationship.

**10. When should maintainability and simplicity be prioritized?**  
When performance requirements are not yet proven to demand otherwise, **small and clear synchronized blocks** can be better than a complex CAS state machine; when single-worker ownership can be guaranteed, avoiding sharing can be even simpler than both.

## 19. Summary

**Atomic** fits when the entire decision can be executed by a single atomic primitive or a CAS on an immutable snapshot; **lock** fits when a multi-step, multi-field critical section must be protected; **thread confinement** fits when you can design **a single exclusive owner** for mutable state and exchange data only through clear protocols.

The right choice is evaluated by **invariants, happens-before, ownership, JVM boundaries, and side effects**, not merely by lines of code or presumed performance. When needed, combine mechanisms in separate state domains; always define who can read, who can write, which updates must be atomic, and how to verify the result.
