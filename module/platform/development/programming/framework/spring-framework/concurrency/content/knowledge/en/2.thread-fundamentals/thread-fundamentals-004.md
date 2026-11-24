# Data Contention, Atomicity, and Visibility of Changes

> **Scope:** multithreaded programming fundamentals with Java 17+ and how to apply them in Spring Framework applications. The focus is on state accessed concurrently by multiple threads, conditions under which bugs arise, Java Memory Model (JMM) guarantees, and selecting synchronization tools matched to the invariant being protected.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **data race**, **race condition**, **atomicity**, and **visibility**.
2. Explain why `counter++` can lose increments and why adding `volatile` does not fix it.
3. Use the **happens-before** relationship to reason about when one thread's writes are guaranteed to be visible to another thread.
4. Choose among immutable data, `synchronized`, `volatile`, `AtomicInteger`, locks, and concurrent collections.
5. Identify dangerous shared state in Spring singleton beans, `@Async` tasks, and multi-instance applications.

## 1. How Does Shared State Create Problems?

A **thread** is an execution unit. Two threads can run interleaved or in parallel. Local variables of a method invocation normally belong to that invocation alone; by contrast, a field of an object referenced by two threads is **shared mutable state** if it can change.

For example, two HTTP requests concurrently call a method on a Spring service with the default `singleton` scope. They may operate on **the same service instance**. If the service stores `int count` and both requests execute `count++`, the outcome depends on how operations interleave.

A **data race** under the JMM occurs when two conflicting accesses to the same variable (at least one being a write) from different threads are not ordered by a happens-before relationship. A **race condition** is a broader concept: a program's outcome depends on timing or execution order, sometimes even when individual data accesses are already synchronized. Fixes must target the *business invariant* to protect, not merely look at a single variable in isolation.

A simple example:

~~~java
class UnsafeCounter {
    private int count;

    void increment() {
        count++;
    }

    int get() {
        return count;
    }
}
~~~

This is an **illustrative snippet**, without `main`. Both `increment()` and `get()` access `count` without synchronization. Bugs can appear when multiple threads use the same instance.

## 2. Atomicity: An Increment Is Not One Step

**Atomicity** means an operation is observed as an indivisible unit that cannot be interleaved in the middle, within the scope of that operation's guarantees. Logically, `count++` consists of three steps:

1. Read the current value.
2. Compute the new value as the old value plus 1.
3. Write the new value.

Suppose `count = 0`:

| Step | Thread A | Thread B | `count` |
| --- | --- | --- | ---: |
| 1 | Read 0 | | 0 |
| 2 | | Read 0 | 0 |
| 3 | Write 1 | | 1 |
| 4 | | Write 1 | 1 |

Two increments were requested, yet the final result is only **1**. This is a *lost update*. Replacing `int` with `volatile int` still does not make the entire read–modify–write sequence atomic.

### Controlled Experiment Reproducing a Lost Update

Save the following to `LostUpdateDemo.java`. `CountDownLatch` forces both threads to read the same initial value before being allowed to write. Thus the result of **this experiment** is deterministic; race bugs in real programs typically manifest intermittently.

~~~java
import java.util.concurrent.CountDownLatch;

public class LostUpdateDemo {
    private static int count = 0;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Runnable increment = () -> {
            int snapshot = count;
            bothRead.countDown();

            try {
                allowWrite.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            count = snapshot + 1;
        };

        Thread first = new Thread(increment);
        Thread second = new Thread(increment);
        first.start();
        second.start();

        bothRead.await();
        allowWrite.countDown();
        first.join();
        second.join();

        System.out.println("count = " + count);
    }
}
~~~

Run:

~~~bash
javac LostUpdateDemo.java
java LostUpdateDemo
~~~

Output:

~~~text
count = 1
~~~

Both threads read `0`, then both write `1`. The latches only coordinate step order in the **experiment**; they do not turn the `count` update here into an atomic increment. `join()` ensures the `main` thread reads the result only after both threads have terminated.

**Key distinction:** a single read/write of certain types can be atomic while *a sequence of multiple operations* remains non-atomic. Under the JLS, **non-volatile** `long` or `double` reads/writes have a historical atomicity exception, so you should not infer that every primitive read/write has identical guarantees. Safe multithreaded code relies on synchronization constructs with clear contracts.

## 3. Visibility: Does Another Thread See the New Value?

**Visibility** answers the question: after thread A modifies data, is thread B guaranteed to observe that change? Compilers, JITs, and CPUs may use registers, caches, and operation reordering within JMM bounds. Without a proper synchronization relationship, B may observe stale data; never assume that "A wrote earlier by wall-clock time" implies "B is guaranteed to read the new value."

Example of a stop flag:

~~~java
class WorkerLoop implements Runnable {
    private volatile boolean running = true;

    @Override
    public void run() {
        while (running) {
            Thread.onSpinWait();
        }
    }

    void stop() {
        running = false;
    }
}
~~~

This is an **illustrative snippet**, not a standalone application. For a flag that only needs single reads/writes, `volatile` creates the appropriate visibility guarantee: one thread writing `running = false` *happens-before* subsequent reads of `running` in synchronization order. Removing `volatile` without other synchronization leaves the looping thread with no guarantee of ever observing the stop signal. `Thread.onSpinWait()` is only a CPU hint, **not** a synchronization tool. In real applications, prefer `interrupt()`, blocking wait mechanisms, or task cancellation over CPU-burning loops.

### Atomicity and Visibility Are Two Different Requirements

| Question | Bug Example | Typically Suitable Tools |
| --- | --- | --- |
| **Atomicity**: Does the whole operation occur without interleaving? | Two `count++` lose one increment | `synchronized` or `AtomicInteger.incrementAndGet()` |
| **Visibility**: Does thread B see A's update? | Stop flag not observed | `volatile`, locks, or another happens-before edge |
| **Ordering**: Are operations observed in the required order? | Reading dependent state before safe publication | Safe publication via locks, `volatile`, proper `final`, or concurrency constructs |
| **Invariant**: Do multiple fields always stay mutually consistent? | Deducting balance and updating ledger out of sync | One lock region covering the operation, or suitable transaction/coordination |

`volatile` fits status flags or *an independent snapshot value*. It does **not** make `x++`, `if (x == 0) x = 1`, or updates across two fields into an atomic transaction.

## 4. Java Memory Model and the Happens-Before Relationship

The JMM is the contract defining what values a thread can read and the synchronization effects between threads. The **happens-before (HB)** relationship is the primary tool for reasoning about visibility and ordering: if action A *happens-before* action B, then A's effects are guaranteed to be visible/ordered for B under JMM rules. HB is a logical ordering relation, **not merely** wall-clock order.

Rules to remember:

- **Program order:** within the same thread, an action happens-before actions that follow it in program order.
- **Monitor:** an unlock operation of `synchronized` happens-before a subsequent lock on **the same monitor**.
- **Volatile:** a write to a `volatile` field happens-before a subsequent read of that same field in synchronization order.
- **Thread.start():** actions before calling `start()` happen-before actions in the newly started thread.
- **Thread.join():** actions in a terminated thread happen-before another thread successfully returns from `join()` on that thread.
- **Transitivity:** if A HB B and B HB C, then A HB C. `Future.get()` and many constructs in `java.util.concurrent` also provide memory consistency guarantees documented in their APIs.

Visualizing safe ordering of a message:

~~~text
Thread A:  data = "ready"  ->  ready = true (volatile write)
                                       |
                                  happens-before
                                       v
Thread B:                       if (ready) (volatile read)
                                 -> reads data
~~~

If B observes `ready == true` from that publication write, the data written prior to the volatile write is properly published for B's subsequent reads. When using this pattern, keep the exact order of writing data before writing the flag, and do not continue mutating the shared data without a synchronization protocol.

**Important fact:** log appearance order, sleep durations (`Thread.sleep`), thread priorities, or "it worked on my machine" **do not create** a happens-before relationship for shared state. Avoid interpreting HB as a promise that the scheduler must execute A completely before B.

## 5. Ways to Protect Shared Data

### 5.1. Prefer Not Sharing Mutable State

A method that only uses parameters, local variables, and unescaped immutable objects is typically easy for many requests to call concurrently. Use `record`, `final` fields, defensive copies, and new return values where appropriate.

`final` stabilizes the reference and has special publication rules when an object is properly constructed, but **does not make a referenced `ArrayList`/`HashMap` itself immutable**. Never let `this` escape from a constructor before initialization completes.

### 5.2. `synchronized`: Both Mutual Exclusion and Visibility

~~~java
final class Wallet {
    private long balance;

    Wallet(long openingBalance) {
        this.balance = openingBalance;
    }

    synchronized boolean withdraw(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        if (balance < amount) {
            return false;
        }
        balance -= amount;
        return true;
    }

    synchronized long balance() {
        return balance;
    }
}
~~~

This is an **illustrative class definition**, without `main`. Every access to `balance` goes through the same monitor, the `Wallet` object. *Checking the balance and subtracting* sit in the same locked region, so two threads cannot both withdraw against the same stale balance; when one thread releases the lock, the next thread acquiring the lock sees the update. This solves consistency **for one object within one JVM**; it does not automatically solve database transactions or multiple service instances.

Note: `synchronized` locks attach to the **monitor object**. Two distinct `Wallet` instances have two distinct monitors. Avoid locking on public strings, arbitrarily exposed `this`, or objects that external code might lock on itself. A `private final Object lock = new Object();` often gives clearer control over the lock scope. Keep critical sections just large enough to protect the invariant and avoid slow I/O inside locks.

### 5.3. `AtomicInteger`, `AtomicLong`, and CAS

For standalone counters, Java provides atomic increment, add, and compare-and-set operations. `AtomicInteger.incrementAndGet()` is **an atomic update**, unlike `count++`.

Save the following to `AtomicCounterDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        final int threadCount = 4;
        final int incrementsPerThread = 50_000;
        AtomicInteger count = new AtomicInteger();
        Thread[] workers = new Thread[threadCount];

        for (int i = 0; i < threadCount; i++) {
            workers[i] = new Thread(() -> {
                for (int j = 0; j < incrementsPerThread; j++) {
                    count.incrementAndGet();
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("count = " + count.get());
    }
}
~~~

Run:

~~~bash
javac AtomicCounterDemo.java
java AtomicCounterDemo
~~~

Exact output:

~~~text
count = 200000
~~~

`incrementAndGet()` performs an atomic increment; `join()` ensures all threads have completed before printing. Do not rely on `sleep()` to "wait long enough." An `AtomicInteger` only guarantees atomic operations published on **that variable itself**; it does not automatically protect invariants spanning a balance, transaction history, and other objects.

**CAS** (compare-and-set) updates a value only if it still equals the expected value, enabling many constructs without per-update monitors. For computations using `updateAndGet`, the supplied function may be re-applied under contention, so it should have **no side effects**. `LongAdder` is useful for heavily contended counters, though `sum()` while updates are ongoing is not a globally atomic snapshot.

### 5.4. Explicit Locks and Concurrent Collections

`ReentrantLock` is used when you need `tryLock`, timed locking, interruptible lock waiting, or multiple `Condition`s. Always release in `finally`:

~~~java
lock.lock();
try {
    // Read and modify all state belonging to the same invariant.
} finally {
    lock.unlock();
}
~~~

The snippet above is a **structural pattern**, assuming `lock` has already been declared as a `ReentrantLock`. A lock helps nothing if another read/write path accesses the same data while bypassing that lock.

- `ConcurrentHashMap` supports high concurrency and atomic **per-key** operations such as `compute`, `merge`, and `putIfAbsent`. Two separate calls `containsKey` then `put` are **not** a single compound atomic operation.
- `CopyOnWriteArrayList` is useful for read-heavy, write-rare workloads because every modification copies the underlying structure.
- `Collections.synchronizedList(...)` synchronizes individual methods, yet iterating with an iterator still requires external synchronization around the iteration per the API contract.
- `BlockingQueue` fits producer–consumer patterns; put/take operations combine element transfer with conditional waiting, avoiding custom polling loops with volatile flags.
- `ThreadLocal` stores per-thread values and does not make external shared state safe. With thread pools, threads are reused, so clean up via `ThreadLocal.remove()` if managing manually.

Choose a data structure by **the operations that must be atomic**, not by the word "concurrent" in its name. A concurrent map does not automatically create consistent transactions across multiple keys.

## 6. Tool Selection Table by Requirement

| Practical Need | First Choice | Limitations to Remember |
| --- | --- | --- |
| Read-only data after configuration | Immutable object, `final`, safe publication | `final` does not make mutable objects inside immutable |
| Cancellation flag or independent status | `volatile boolean` or `AtomicBoolean` | Does not perform compound check-then-act |
| Counter in a single JVM instance | `AtomicInteger` / `AtomicLong` | Does not represent a multi-node system-wide counter |
| Write-heavy counter for stats reading | `LongAdder` | `sum()` is not an atomic snapshot amidst concurrent updates |
| Check then modify multiple fields | `synchronized` / `ReentrantLock` | Every access path must follow the same locking protocol |
| Key-based lookup/update | `ConcurrentHashMap.compute` / `merge` | Atomic per key operation, not across multiple keys |
| Exchanging tasks across threads | `BlockingQueue`, `ExecutorService` | Shut down the executor and handle cancellation/errors properly |
| Data consistency across multiple service instances | Appropriate transactions / conditional updates / distributed locks | In-JVM locks protect only a single process |

## 7. Direct Connection to Spring Framework

### 7.1. Singleton Beans Can Be Called by Many Threads Simultaneously

In Spring, the default `singleton` scope means one instance per bean definition within a Spring container. It is **not synonymous with thread-safe**. Two requests, scheduler tasks, or `@Async` calls can use the same service.

Bug-prone pattern:

~~~java
import org.springframework.stereotype.Service;

@Service
public class UnsafeTicketSequence {
    private long lastId;

    public long nextId() {
        return ++lastId; // can lose numbers when many requests call concurrently
    }
}
~~~

If the requirement is only a unique sequence number **within a single JVM instance**, it can be fixed as:

~~~java
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

@Service
public class TicketSequence {
    private final AtomicLong lastId = new AtomicLong();

    public long nextId() {
        return lastId.incrementAndGet();
    }
}
~~~

Both snippets above require the Spring Framework library to compile and are **not standalone Java SE programs**. The fix only solves counting within one object/JVM. If there are multiple pods/instances, each has its own counter; if IDs must be unique system-wide, use a database strategy or an appropriate ID-generation service.

For order-processing services, a simpler approach is usually a **stateless service**: do not store the current user, request body, or per-request result list in singleton fields. Accept data via parameters, create local objects, and return results. Switching a bean to `prototype` or `request` scope solely to dodge a race condition does not replace identifying what data is actually shared, especially when mutable references are passed to other threads.

### 7.2. `@Async` and Thread Pools Do Not Automatically Synchronize Data

Spring provides `TaskExecutor` and `@Async` support (when `@EnableAsync` is active). An `@Async` method called through a Spring proxy dispatches work to the configured executor; multiple tasks can run concurrently and reference the same singleton bean. If a method in the same class calls its own `@Async` method under default proxy behavior, the internal call bypasses the proxy and does not trigger async execution.

Illustrative example **inside a Spring application with async configured**, not a standalone runnable file:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportJobService {
    private final AtomicInteger finished = new AtomicInteger();

    @Async("applicationExecutor")
    public CompletableFuture<Integer> finishOneReport() {
        int completed = finished.incrementAndGet();
        return CompletableFuture.completedFuture(completed);
    }
}
~~~

`applicationExecutor` must be the name of a configured executor bean; `@EnableAsync` must be enabled. Each invocation via the proxy is scheduled asynchronously, while `AtomicInteger` protects the counter if multiple tasks run concurrently. If reporting requires writing to a database, the logic must handle transactions/data synchronization at the storage layer; a JVM counter does not replace that.

**Three boundaries to distinguish:**

- `@Async` changes how work is scheduled; it does **not** make fields inside a bean thread-safe.
- `@Transactional` coordinates transactions with resources managed by the transaction manager; it does **not** automatically lock Java fields of a singleton bean. Transaction context is normally thread-bound and is not carried over to `@Async` threads by default.
- `synchronized` or `AtomicInteger` only coordinates threads sharing **the same JVM memory**. Do not use them to conclude that data across multiple pods, servers, or processes is updated atomically.

### 7.3. Publishing Consistent Configuration Across Threads

When replacing a multi-field configuration *snapshot*, you can use an immutable object and a `volatile` reference:

~~~java
record Limits(int maxJobs, int maxRetries) {}

class LimitsHolder {
    private volatile Limits current = new Limits(10, 3);

    Limits snapshot() {
        return current;
    }

    void replace(int maxJobs, int maxRetries) {
        current = new Limits(maxJobs, maxRetries);
    }
}
~~~

This is an **illustrative Java 17 snippet**, without `main`. Each call to `snapshot()` obtains a reference to an entire immutable set of values rather than reading two mutable fields separately that could be updated out of sync. Read once into a local variable and use that snapshot throughout the business logic. This example does not automatically handle multiple writers needing check-then-write coordination; for that, an appropriate update mechanism must be designed.

## 8. Common Reasoning Mistakes

1. **"`volatile int count` makes `count++` thread-safe."** False: volatile guarantees visibility/ordering, yet the read–add–write sequence can still be interleaved. Use atomic RMW or a lock.
2. **"`final Map` never changes."** False: `final` keeps the reference unchanged; it does not prevent adding/removing map entries.
3. **"Each `ConcurrentHashMap` operation is safe, so two combined operations are also atomic."** False: use the appropriate atomic API such as `compute` or a broader synchronization protocol.
4. **"I locked on writes; reads don't need a lock."** Insufficient if the read path needs to observe consistent state and has no other HB relationship.
5. **"Adding `Thread.sleep(100)` eliminates the race."** False: sleep only affects execution timing; it establishes no data synchronization guarantee.
6. **"Spring creates singletons so it handles races automatically."** False: the container manages lifecycle and dependency injection; mutable application state remains the author's responsibility to protect.
7. **"Database transactions protect Java fields in a service."** False: those are two different consistency scopes.
8. **"Running 1,000 times with the right result proves the code is thread-safe."** Insufficient: races can be rare and depend on JVM, CPU, and scheduling.
9. **"`AtomicInteger` updates two variables together."** False: single-variable atomicity does not cover multi-variable invariants.
10. **"Adding locks to every method is optimal."** Not necessarily: overly broad locking increases contention and can cause deadlocks; prefer eliminating shared mutable state where possible.

## 9. How to Analyze and Test Issues in a Project

1. **Identify shared data:** `static` fields, mutable fields in singletons, caches, maps, lists, session objects, and references passed into tasks.
2. **State the invariants explicitly:** for example "balance is non-negative" or "each order is processed once," rather than just writing "no race."
3. **List read/write paths and execution threads:** HTTP handlers, `@Async`, schedulers, event listeners, executors. Determine whether the scope is one JVM or multiple instances.
4. **Prove HB relationships or atomicity:** for each communication edge between two threads, identify which lock, volatile, atomic operation, or concurrency API provides the guarantee.
5. **Write targeted contention tests:** use `CountDownLatch`/`CyclicBarrier` to start concurrently or force an interleaving, and assert the final invariant. Run many iterations under heavy load; passing tests do not prove the absence of races. For low-level JMM issues, consider studying `jcstress`.
6. **Measure and review after fixing:** confirm correctness first, then measure contention, latency, and throughput; inspect thread dumps when suspecting deadlock or prolonged lock waiting. Never optimize by removing locks without safety proof.

### Self-Check Exercises

**Scenario A:** A singleton `@Service` has `private int activeRequests`. `begin()` calls `activeRequests++` and `end()` calls `activeRequests--`. What is wrong?  
**Suggested answer:** lost updates due to non-atomic RMW; `volatile` does not fix it. If only counting independently within one JVM, `AtomicInteger` can be used while ensuring every begin/end path balances (including errors) via `try/finally`.

**Scenario B:** One thread sets `stopped = true`, and another loops checking `stopped`. What guarantee is needed?  
**Suggested answer:** visibility/happens-before; `volatile boolean` may suffice for a single flag, though if waiting on I/O or a blocking queue, use an appropriate cancellation/interrupt mechanism.

**Scenario C:** Two requests both check `balance >= amount` and then subtract, using `AtomicLong` for balance. Is it guaranteed correct?  
**Suggested answer:** not if checking and subtracting are two separate atomic calls; one request could subtract based on a stale balance. Use a proper CAS loop or a lock covering both check and update; for database accounts / multi-instance setups, use transactions/conditional updates at the storage layer.

**Scenario D:** Two replicas of a Spring app both have `AtomicLong nextId`. Are IDs guaranteed not to collide?  
**Suggested answer:** no; each replica has its own memory. Choose an ID generator/sequence coordinated system-wide.

## 10. Takeaways

- **Data race**: conflicting accesses not ordered by HB; **race condition**: broader timing/order-dependent outcomes.
- **Atomicity** protects an operation/invariant from interleaving; **visibility** ensures updates are observed; **ordering** governs which effect orderings threads may see.
- `volatile`: visibility and ordering for independent flags/values; does **not** make increments or check-then-act atomic.
- `synchronized`: mutual exclusion and HB on the same monitor; `AtomicInteger`: atomic RMW on one variable; concurrent collections: guarantees depend on the specific API.
- In Spring, **singleton ≠ thread-safe**, **`@Async` ≠ synchronization**, and **database transactions ≠ locking Java fields**. The first recommendation is usually to eliminate shared mutable state, then pick a protection mechanism matched to the invariant.

## Official References

- Java Language Specification, Chapter 17 — Threads and Locks, especially 17.4.5 on happens-before: https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html
- Java SE 17, `java.util.concurrent` and memory consistency properties: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html
- Java SE 17, `AtomicInteger` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- Spring Framework, Bean Scopes: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework, Task Execution and Scheduling / `@Async`: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
