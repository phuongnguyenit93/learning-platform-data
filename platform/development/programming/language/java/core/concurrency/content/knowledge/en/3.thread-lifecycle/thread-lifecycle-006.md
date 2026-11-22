# Scheduling and Non-Determinism of Execution Order in Java

## 1. What Is Scheduling and Why Is Execution Order Non-Deterministic?

In Java, **thread scheduling** is the process of choosing which thread gets a chance to make progress at a given moment. Both the JVM and the operating system participate in managing thread runnability; the actual scheduling decisions depend on the OS, number of CPU cores, thread priorities, machine load, waiting operations, locks, and many other factors. Developers must not rely on a specific execution schedule just because a program happens to follow that schedule on their own machine.

For example, suppose two independent threads A and B each print a line. Even if `a.start()` is called before `b.start()`, the system may still let B print before A. `start()` initiates asynchronous execution; it does **not** wait for the thread to reach any particular point and does not guarantee that the thread started first will execute its first statement first.

It is important to distinguish three concepts:

- **Concurrency:** multiple threads can make progress within the same time period; the JVM/OS can interleave them on a single core.
- **Parallelism:** threads actually execute simultaneously across multiple cores.
- **Scheduling:** deciding when a thread gets a chance to run, wait, be suspended, or resume. Scheduling provides no ordering guarantee between independent tasks.

**Key takeaway:** the correctness of a multithreaded program must rely on deterministic dependency relationships and synchronization mechanisms, not on the assumption that "this thread will probably run first."

## 2. Thread States Related to the Scheduler

`Thread.State` in Java exposes several JVM-observable states of a thread. It is not a complete description of every state managed by the operating system and is only a snapshot at the moment `getState()` is called.

| `Thread.State` | Practical meaning | Relation to scheduling |
| --- | --- | --- |
| `NEW` | Object has been created but `start()` has not been called | Not yet registered for execution as a new thread |
| `RUNNABLE` | Executing in the JVM or ready to execute | **Does not mean it is actively occupying a CPU at the exact moment of observation** |
| `BLOCKED` | Waiting to acquire a `synchronized` monitor | Must wait for the monitor to become available; not a general state for all I/O |
| `WAITING` | Waiting indefinitely via a wait mechanism, e.g., `Object.wait()`, `Thread.join()`, or `LockSupport.park()` | Cannot proceed until the corresponding wakeup condition or signal occurs |
| `TIMED_WAITING` | Waiting for a bounded duration, e.g., `Thread.sleep()`, timed `join()`, or timed `wait()` | Can resume when the condition is met or the timeout expires, after which it still depends on scheduling |
| `TERMINATED` | `run()` has finished or the thread terminated due to an unhandled error | Cannot be restarted |

A thread can transition through multiple states very quickly. For instance, you might observe `RUNNABLE` and then call `getState()` again only to see `WAITING`. Therefore, do not write coordination logic that repeatedly polls `getState()` and assumes the thread remains in that state.

**Specifically:** calling `Thread.sleep()` does not release ownership of any held monitor; if a thread is inside a `synchronized` block, it retains the monitor while sleeping.

## 3. Java 17+ Example: Two Threads Start at the Same Point, Yet Order Is Not Guaranteed

Create the file `SchedulingObservation.java`:

```java
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;

public class SchedulingObservation {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch go = new CountDownLatch(1);
        ConcurrentLinkedQueue<String> order = new ConcurrentLinkedQueue<>();

        Runnable work = () -> {
            ready.countDown();
            try {
                go.await();
                order.add(Thread.currentThread().getName());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(work, "A");
        Thread b = new Thread(work, "B");

        a.start();
        b.start();
        ready.await();    // Both workers have reached the ready point
        go.countDown();   // Open the shared barrier
        a.join();
        b.join();

        System.out.println("Observed order: " + order);
        System.out.println("Recorded two events: " + (order.size() == 2));
    }
}
```

Compile and run:

```bash
javac SchedulingObservation.java
java SchedulingObservation
```

**Two possible output forms** (order is not guaranteed):

```text
Observed order: [A, B]
Recorded two events: true
```

or:

```text
Observed order: [B, A]
Recorded two events: true
```

There is no guarantee that you will observe both orders even if you run the program many times on the same machine. Scheduling can occasionally repeat one order very consistently by coincidence. **Do not treat that consistency as proof of a guarantee.**

Explanation of the components:

1. `CountDownLatch ready` lets `main` know that both workers have arrived at the starting gate.
2. `go.await()` makes both workers wait until `go.countDown()`; this synchronizes them at a single point, **not** guaranteeing that they run in the same nanosecond or in a particular A/B order.
3. `ConcurrentLinkedQueue` allows recording events safely from multiple threads, avoiding data corruption from non-thread-safe collections.
4. Both `join()` calls make `main` wait until both workers finish before printing the result.
5. As long as the program is not interrupted externally, both workers record a name into the queue. The line `Recorded two events: true` is deterministic; the observed order line depends on the execution schedule.

This illustrates **the ordering of side effects** performed by multiple threads. Even when each thread performs only a very brief operation, Java does not promise to run those operations in the order `start()` was called.

## 4. Causes of Execution Schedule Variations

### 4.1. Runnability vs. Actual CPU Allocation

A thread in the `RUNNABLE` state may be ready to run but not yet executing on a CPU. On a multi-core machine, threads can run in parallel; on a machine with fewer cores than ready threads, they must share processor time. The outcome depends on the operating system and the machine's state at runtime.

### 4.2. Preemption and Context Switching

The operating system can switch the CPU from one thread to another according to its scheduling policy. Context switching allows instructions from multiple threads to interleave. Java provides no guarantee that the code between two semicolons will always execute uninterrupted as a single block.

You must distinguish between an **operation that is short in source code** and an **atomic operation**. For example, `counter++` consists of read, increment, and write steps; writing it on one line does not prevent those three steps from interleaving with another thread's operations.

### 4.3. Waiting on Locks, I/O, and Synchronization Primitives

A thread may have to wait for a `synchronized` monitor, a condition in `wait()`/`notify()`, `CountDownLatch`, `Semaphore`, `BlockingQueue`, `LockSupport`, `Future`, or I/O. When the awaited event completes, the thread becomes a candidate to run; that **does not** guarantee it will be scheduled onto a CPU immediately or ahead of every other thread.

### 4.4. Thread Priority

Java provides `Thread.MIN_PRIORITY`, `Thread.NORM_PRIORITY`, `Thread.MAX_PRIORITY`, and `setPriority(int)` for traditional platform threads. Priority may influence scheduling depending on the JVM and operating system, but it is **not a tool for guaranteeing order, fairness, or deadlines**. Never build correctness on the assumption that a higher-priority thread will always run or finish first.

### 4.5. Optimizations and Memory

Beyond schedule non-determinism, a program with a **data race** also suffers from visibility and ordering issues under the Java Memory Model. The compiler, JIT, and CPU may perform valid optimizations such that another thread does not observe operations in simple source-code order if proper synchronization is absent.

For that reason, saying "just add `sleep()` so the other thread has time to update the variable" has two flaws: sleeping does not guarantee the other thread has finished, and `sleep()` by itself does not establish a happens-before relationship for safe data publication.

## 5. Do `sleep()`, `yield()`, or `join()` Make Scheduling Deterministic?

| API | Effect | What is **not** guaranteed |
| --- | --- | --- |
| `Thread.sleep(millis)` | Requests the current thread to pause for the specified duration | That another thread will finish; the exact time it will resume; data visibility |
| `Thread.yield()` | Hints to the scheduler that the current thread is willing to yield its execution slice | That the scheduler will honor the hint; that another thread will run first; a fixed schedule |
| `Thread.join()` | The calling thread waits for the target thread to terminate | Execution order among independent workers; that the worker completed successfully |
| `Thread.start()` | Starts a new thread | That the newly started thread will run before a thread started later |
| `Thread.setPriority(...)` | Adjusts a priority hint when supported by the implementation | Ordering, fairness, or response deadlines |

**About `sleep()`:** sleep duration also depends on timer resolution, the scheduler, and machine load. `sleep(100)` is not a promise to "resume after exactly 100 ms." You can measure elapsed time to manage timeouts, but you must account for waking up later than requested.

**About `yield()`:** it is a hint with no synchronization semantics. Adding `yield()` inside a loop polling a plain flag does not replace `volatile`, locks, or proper waiting mechanisms. Busy-waiting wastes CPU and remains broken with respect to visibility.

**About `join()`:** once `join()` returns normally without a timeout, the target thread has terminated; however, the order of individual statements between workers prior to that can still vary. `join(timeout)` only waits for a bounded period, so you must check `isAlive()` if you need to know whether the worker actually finished.

## 6. Do Not Confuse Order Non-Determinism with Correctness Non-Determinism

A well-designed concurrent application **can have different execution schedules and still produce the same correct result**. For example, two threads compute two independent parts and `main` sums them after both finish: each part can complete in any order as long as storing and collecting the results is thread-safe.

Conversely, if multiple threads update a shared mutable variable without synchronization, the computed result can be wrong depending on how their steps interleave.

### Why Is `counter++` Unsafe?

Suppose two threads both read `counter = 0`, each computes `1`, and then both write `1`. We expect `2` but get `1`: one increment is lost. This is called a **lost update**, a form of race condition. `volatile int counter` guarantees visibility of individual reads and writes, but it **does not** make the read-modify-write operation `counter++` atomic.

To make the example produce the right output, use `AtomicInteger.incrementAndGet()` or `getAndIncrement()`, or protect the operation with an appropriate lock.

Create the file `AtomicScheduling.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicScheduling {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger counter = new AtomicInteger();

        Runnable increment = () -> {
            for (int i = 0; i < 1_000; i++) {
                counter.incrementAndGet();
            }
        };

        Thread a = new Thread(increment, "A");
        Thread b = new Thread(increment, "B");
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("Final count: " + counter.get());
    }
}
```

Compile and run:

```bash
javac AtomicScheduling.java
java AtomicScheduling
```

Output:

```text
Final count: 2000
```

The scheduler can interleave A and B in any valid schedule; the result is still 2,000 because both threads perform the full number of atomic increments and `main` waits for both with `join()`. There is **no need** to force A to finish completely before B starts. This is good design: use primitives with the right guarantees so the result does not depend on scheduling order.

## 7. To Enforce Order, Express Dependency Relationships

Some workflows have genuine business-logic ordering requirements: for example, a "load configuration" step must complete before a "use configuration" step. In such cases, synchronize **on the actual event**, rather than hoping a thread started earlier will always finish first.

### Java 17+ Example: Guaranteeing Step 1 Before Step 2 with `CountDownLatch`

Create the file `OrderedSteps.java`:

```java
import java.util.concurrent.CountDownLatch;

public class OrderedSteps {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch firstDone = new CountDownLatch(1);

        Thread second = new Thread(() -> {
            try {
                firstDone.await();
                System.out.println("Step 2: use data");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        Thread first = new Thread(() -> {
            System.out.println("Step 1: prepare data");
            firstDone.countDown();
        }, "producer");

        second.start(); // Intentionally start the consumer first
        first.start();

        first.join();
        second.join();
        System.out.println("All done");
    }
}
```

Run:

```bash
javac OrderedSteps.java
java OrderedSteps
```

Output in a normal completed run:

```text
Step 1: prepare data
Step 2: use data
All done
```

Even though `second.start()` was called first, `second` prints step 2 only after `firstDone` is decremented to 0. This ordering is **created by the synchronization condition**, not by the scheduler favoring any thread.

`CountDownLatch.countDown()` has a happens-before relationship with actions following a successful `await()` in another thread. Thus, if the producer writes data before `countDown()` and the consumer reads it only after `await()`, this forms a valid data-publication boundary. Note that a latch does not automatically propagate exceptions or prove the producer succeeded: production code must define error handling and avoid waiting forever if the producer never calls `countDown()`.

### When You Only Need the Result After a Thread Terminates

`worker.join()` is simpler when the **entire** worker thread must terminate before `main` uses the result. However, if a consumer needs to wait for a **milestone** while the producer continues working, `CountDownLatch`, `BlockingQueue`, `Condition`, or a similar abstraction expresses the requirement more accurately.

## 8. Java Memory Model: Logical Ordering and Visibility

The scheduler decides when a thread gets a chance to run, whereas the **Java Memory Model (JMM)** defines what data observations are guaranteed across threads when synchronization conditions are satisfied.

Key **happens-before** relationships to remember:

- Actions within the same thread follow program order under JMM semantics; this does not mean every machine instruction is emitted in exact source-code order.
- A call to `thread.start()` happens-before any action in the newly started thread.
- Actions in a thread happen-before another thread confirms that thread has terminated via a successful `join()`.
- An unlock of a monitor happens-before every subsequent lock of that **same monitor**.
- A write to a `volatile` field happens-before every subsequent read of that same field in the synchronization order.
- With `CountDownLatch`, actions before `countDown()` happen-before actions after a successful `await()` once the latch opens.

Happens-before is the foundation for visibility and ordering; it **does not mean the scheduler forces the earlier thread in the relation to be picked first by the CPU at every moment**. For instance, `main` calls `a.start()` then `b.start()`: each `start()` has a happens-before relation with actions in its respective worker, but it **creates no** total order across all actions of A and B.

Do not use `System.out.println()` or `Thread.sleep()` as a coordination protocol. Some I/O implementations have internal synchronization, but relying on logging side effects to fix races or enforce ordering is a fragile design.

## 9. Common Scheduling-Related Mistakes

### 9.1. Assuming `start()` Order Determines Result Order

Wrong: `a.start(); b.start();` does not guarantee A prints before B. Solution: if ordering is needed, use `join()` at the right boundary or an event-synchronization primitive. If tasks are independent, write code that accepts any valid order.

### 9.2. Using `sleep()` to "Wait Long Enough"

Wrong: sleeping 500 ms does not prove another task has finished or that data has been published safely. Wait on a real condition: `join()`, `Future.get()`, a latch, a queue, or a lock/condition; when a deadline is needed, use timeout-aware APIs and check the resulting state.

### 9.3. Using `yield()` or Priority to Fix a Race

Wrong: `yield()` is only a scheduling hint; priority likewise creates no ordering and guarantees no fairness. Data-access bugs must be solved with proper synchronization relationships or data redesign.

### 9.4. Thinking Thousands of Passing Test Runs Mean There Is No Race

Wrong: the same machine, same load, and a common schedule can hide a race condition. Thread scheduling varies by OS and load; repeated runs, stress tests, and observability tools only increase the chance of detection—they do not prove the absence of all races.

### 9.5. Busy-Waiting Without Synchronization

Conceptually flawed example:

```java
while (!finished) {
    Thread.yield();
}
```

If `finished` is a plain boolean written by another thread without proper synchronization, the waiting thread may never observe the change; moreover, the loop wastes CPU. This is a **snippet illustrating a bug**, not a complete Java program. Use `volatile` for a simple signal in a valid design, or `CountDownLatch`, `BlockingQueue`, or `Condition` when waiting for an event. For complex state transitions, `volatile` alone does not solve atomicity issues.

### 9.6. Deadlock from a Circular Wait Graph

If A holds a lock and waits for B while B needs that lock to finish, the scheduler cannot "fix" the wait relationship on its own. For example, if A calls `B.join()` while holding a monitor that B must acquire, both can get stuck. Design a consistent lock ordering, avoid holding locks while waiting, and eliminate dependency cycles.

### 9.7. Confusing Starvation with Deadlock

**Starvation** occurs when a thread gets little or no chance to make progress due to resource contention, locks, or an unfair scheduling/priority policy; other threads in the system may still be making progress. **Deadlock** is a dependency cycle that prevents a group of threads from making any progress. **Livelock** occurs when threads remain active and keep changing state without achieving their goal. All three can occur in concurrent programs, and "raising priority" is not a general solution.

## 10. Observing and Measuring Properly

- Use clear thread names (`new Thread(task, "worker-A")`) so logs, stack traces, and thread dumps are easy to interpret.
- When inspecting state, treat `Thread.getState()` as a **snapshot**, not a synchronization protocol or execution-order guarantee.
- To analyze a real program, combine thread dumps (`jcmd` and JVM tools), JFR, logs with timestamps and thread names, CPU profiling, lock contention data, and latency/throughput metrics. Observation itself can alter execution timing; do not infer from a single log capture that every run behaves identically.
- To verify correctness, define concrete invariants: no lost updates, no duplicate processing, business ordering preserved, no unbounded waits. Test across varied schedules and loads, and review happens-before edges and shared-state points in code reviews.
- For benchmarks, use a representative environment and workload, warm up the JVM, and take multiple measurements. Variable runtimes do not by themselves prove a scheduling issue; identify bottlenecks and measure synchronization, locks, I/O, and GC.

## 11. Checklist Before Relying on Ordering Between Threads

1. **Is ordering actually required?** If tasks are independent, prefer a design that does not depend on completion order.
2. **Which event establishes the before/after relationship?** `start()`, `join()`, a latch, lock, queue, `Future`, or an explicit protocol must be used properly.
3. **Is data published safely?** Prove happens-before or use appropriate atomic/`synchronized`/`volatile` primitives; never rely on "it usually runs first."
4. **Can it hang?** Check for wait cycles, lock contention, timeouts, interrupts, and error paths where the completion signal is never emitted.
5. **Is the result correct under every valid schedule?** Avoid assuming `println` order, exact `sleep` wakeup times, `yield` effectiveness, or thread priority ordering.
6. **Is your observation reliable?** Rely on invariants, synchronization evidence, and workload measurements; a log or single run is only a snapshot.

**Remember:** scheduling in Java is non-deterministic in the sense that a program cannot rely on a specific execution schedule for independent threads. Correctness is built through synchronization relationships and thread-safe data handling so that the program produces valid results regardless of which execution order the JVM/OS chooses.
