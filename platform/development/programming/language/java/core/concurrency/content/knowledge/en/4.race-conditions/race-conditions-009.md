# Distinguishing Data Race, Race Condition, and Logic Race in Java

## 1. Objectives and Scope

After this lesson, you will be able to:

- Distinguish **data race** based on the *happens-before* relationship in the Java Memory Model (JMM), **race condition** based on behavioral correctness, and **logic race** at the operation or business-rule level.
- Explain why a race condition can exist **even without a data race**, as well as why a data race may not manifest as a failure in a single run.
- Recognize the **read–modify–write**, **check–then–act**, and **time-of-check to time-of-use (TOCTOU)** bug patterns.
- Choose the right Java mechanism such as **synchronized**, **AtomicInteger.compareAndSet()**, concurrent data structures, or signaling protocols to protect an *invariant*.
- Create examples with controlled interleavings to reproduce bugs, understand the limits of stress testing, and verify results against business conditions rather than merely inspecting log order.

The scope is **general Java concurrency** at the JDK and JMM level. Spring-specific mechanisms belong to another chapter.

## 2. Three Terms with Different Scopes

### 2.1. Data race: conflicting accesses lacking happens-before ordering

In JMM terminology, a **data race** occurs when there are **two conflicting accesses** to the same variable, performed by different threads, **at least one access is a write**, and there is **no happens-before relationship** ordering those two accesses.

The classic example is multiple threads operating on a regular **int** field without proper synchronization.

~~~java
// Illustrative snippet, not a standalone program:
int count = 0;
// Thread A and thread B both execute:
count++; // Read, compute, then write; not an atomic increment.
~~~

The result can be a *lost update*. One possible execution schedule is:

~~~text
Initially count = 0
Thread A: read count -> 0
Thread B: read count -> 0
Thread A: compute 0 + 1 -> 1
Thread B: compute 0 + 1 -> 1
Thread A: write count = 1
Thread B: write count = 1
Final count = 1 even though two increments were requested.
~~~

This is an illustrative failure schedule; threads can interleave in different ways. The consequences are not limited to lost updates: reading stale data, violating invariants across fields, and unpredictable behavior under the JMM can also occur.

**A data race is a concept about memory access and synchronization**, not a label concluding that business logic has failed. Having a data race in a program is a dangerous design sign; the bug may not surface in a single trial.

### 2.2. Race condition: whether the result is right or wrong depends on interleaving

A **race condition** is a situation where critical program behavior depends on the order/timing in which operations occur, yet the program **does not enforce the necessary ordering constraints or atomicity conditions**. When a valid interleaving leads to a requirement violation, that is a buggy race condition.

Examples:

- Two workers both process a job that must be **processed only once**.
- Two customers both reserve the last seat even though only one remains in inventory.
- One thread checks that a resource exists, but another thread modifies the resource before it is used.
- Two transactions both read the balance, each assuming there are sufficient funds.

**Race condition is broader than data race.** It can involve unsynchronized shared memory, but it can also happen with individual operations that are all thread-safe, or even across different processes or machines.

Not every nondeterministic ordering should be called a bug. For example, two workers that simply print two independent log lines and then finish can produce two valid orders while still satisfying the specification.

### 2.3. Logic race: breakdown in multi-step coordination rules

**Logic race** is a commonly used term for a race condition in **application logic**: each small operation may be safe, but the **sequence of operations** is not protected as a unified decision.

Typical pattern:

~~~text
1. Check whether condition P is true.
2. Another thread modifies the relevant state.
3. Proceed with the action based on the stale check result.
~~~

For example: **stock.get()** and **stock.decrementAndGet()** are both thread-safe operations on **AtomicInteger**, but **“if stock is available, decrement by exactly one unit”** does not automatically become an atomic transaction when split into two calls.

**Terminology note:** *Data race* has a technical definition in the JMM. *Race condition* is a broad concept about correctness. *Logic race* is not a distinct enum category or standard term independently defined by the JMM; in this lesson it refers to race conditions that break **invariants and multi-step workflows**. Naming may vary across sources, but the bug patterns and fixes remain the same.

## 3. Brief Comparison and Their Relationship

| Perspective | Data race | Race condition | Logic race |
| --- | --- | --- | --- |
| What is examined | Accesses to the same variable lacking happens-before ordering | Result depends on execution schedule and may violate requirements | Multi-step rule gets interleaved and produces wrong outcome |
| Definition | Formally grounded in the JMM | Depends on specification and correctness requirements | A practical name for a class of race condition |
| Requires unsafe shared data read/write? | Yes, conflicting accesses not ordered by HB | No | No; can use exclusively atomic/thread-safe APIs |
| How to spot in code? | Inspect reads/writes, synchronization, and happens-before | Inspect invariants, business contracts, interleavings | Inspect check–then–act and state transitions |
| Example | Unsynchronized writes to a shared int field | Two orders both receive the last slot | Checking stock.get() then calling decrementAndGet() |
| How to fix | Establish proper synchronization/atomicity/ownership | Enforce atomicity, ordering, or protocol per specification | Combine the decision into an atomic operation/transaction |

Common relationship:

~~~text
               RACE CONDITIONS
              /               \
     With data race       Without data race
      (memory access)      (e.g., check-then-act logic
                            on atomic variables)
                        \
                         LOGIC RACE is the term
                         for multi-step rule bugs
~~~

Do not interpret this diagram as mutually exclusive sets: **a logic race can simultaneously contain a data race** if both the operations and the shared data lack synchronization. Conversely, a data race does not necessarily produce an observable business violation in every execution schedule.

### Three Scenarios for Self-Classification

| Scenario | Assessment |
| --- | --- |
| Two threads perform unsynchronized **plainCounter++** to compute an exact total | Has a data race and a race condition causing lost updates |
| Two threads use **AtomicInteger.get()** then **decrementAndGet()** if stock remains | Individual atomic operations are safe, but there is a logic race and a race condition |
| Two independent threads both log “finished”, line order varies across runs | Nondeterministic order; not a bug if the specification does not require ordering |

## 4. JMM Foundations: Visibility, Atomicity, and Ordering

A concurrent program must distinguish three questions:

1. **Visibility**: can one thread see updates made by another thread?
2. **Atomicity**: can a multi-step operation be interrupted in the middle by another thread?
3. **Ordering**: which operations must happen before which other operations?

The JMM uses the **happens-before** relationship to define memory visibility and ordering guarantees. Common rules:

- Operations before **Thread.start()** in the spawning thread happen-before operations in the started thread.
- Actions of a worker thread happen-before actions of another thread after **join()** returns successfully because the worker has terminated.
- **Unlocking** a monitor happens-before every subsequent **lock** on that same monitor.
- A write to a **volatile** variable happens-before every subsequent matching volatile read in synchronization order.
- Operations on **AtomicInteger** and **AtomicReference** have their respective memory and atomicity contracts; **compareAndSet()** additionally checks and updates in a single conditional operation.
- Concurrent utilities such as **CountDownLatch** and **BlockingQueue** provide memory-visibility relationships specified in their API contracts when used properly.

**Thread.sleep()**, **Thread.yield()**, and the order in which logs appear do not establish happens-before for shared data. Increasing sleep duration only decreases or increases the likelihood of a bug appearing under a given schedule; it does not prove the program is correct.

### What Does volatile Help With, and What Doesn't It Help With?

~~~java
// Illustrative snippet, not a standalone program:
volatile boolean stopRequested = false;
volatile int counter = 0;
~~~

- **stopRequested** can be used as a simple stop-request flag if all relevant reads and writes follow the designed protocol.
- However, **counter++** still consists of a read, an addition, and a write; declaring it **volatile** does not turn those three steps into an atomic increment.
- If you need accurate counting under contention, use **AtomicInteger.incrementAndGet()**, **LongAdder** where appropriate, or a lock protecting the state.

**Being free of data races** is an important condition for JMM-based reasoning, yet it is still **not sufficient** to conclude that business invariants hold. You must also examine the atomicity of **the entire decision sequence**.

## 5. Java 17+ Example: Reproducing a Data Race in a Controlled Way

Running a **counter++** loop millions of times is a common way to observe lost updates, though sometimes the result happens to be right by chance. To demonstrate a failure schedule with a deterministic outcome, we use **CountDownLatch** solely to force both threads to **read the old value before writing**.

File **DataRaceDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class DataRaceDemo {
    static class Counter {
        int value = 0; // Unprotected shared state.
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch releaseWrites = new CountDownLatch(1);

        Runnable increment = () -> {
            int next = counter.value + 1;
            bothRead.countDown();

            try {
                releaseWrites.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }

            counter.value = next; // Two conflicting writes, no HB ordering.
        };

        Thread a = new Thread(increment, "counter-a");
        Thread b = new Thread(increment, "counter-b");
        a.start();
        b.start();

        bothRead.await();
        releaseWrites.countDown();

        a.join();
        b.join();
        System.out.println("counter = " + counter.value);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 DataRaceDemo.java
java DataRaceDemo
~~~

Stdout (without external interrupts):

~~~text
counter = 1
~~~

**Step-by-step explanation:**

1. Both A and B read **counter.value = 0** to compute **next = 1** before main releases the **releaseWrites** latch.
2. After the signal, each worker assigns **counter.value = 1**. These two writes are not ordered by happens-before with respect to each other, so they are conflicting accesses forming a **data race**.
3. **a.join()** and **b.join()** ensure main reads only after both workers have finished; the final value is **1**, whereas two requested increments should have produced **2**.
4. The latches **only force an interleaving to reproduce the bug**; they do not protect the write and do not enforce the invariant “every increment must be added”.

Even though the example prints a deterministic result, **a data race does not necessarily always print the wrong answer** in ordinary programs. Other execution schedules can produce the right result by coincidence. The fact that two threads write the same value or that multiple test runs fail to detect a bug does not prove safety.

### Fixing with an Atomic Increment

File **AtomicCounterDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger counter = new AtomicInteger(0);
        Runnable increment = counter::incrementAndGet;

        Thread a = new Thread(increment, "counter-a");
        Thread b = new Thread(increment, "counter-b");
        a.start();
        b.start();

        a.join();
        b.join();
        System.out.println("counter = " + counter.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AtomicCounterDemo.java
java AtomicCounterDemo
~~~

Stdout:

~~~text
counter = 2
~~~

The two **incrementAndGet()** calls are atomic; there are no more lost updates for this counter. **join()** ensures main reads after both increments complete. If an invariant must protect **multiple fields together**, a single AtomicInteger does not solve the entire problem on its own.

## 6. Logic Race Example Even When Every Individual Operation Is Atomic

An inventory has **1 item** left. The business rule requires:

> Only accept an order if the item is in stock; never accept two orders when only one item remains.

Buggy code:

~~~java
// Illustrative snippet: stock is an AtomicInteger created beforehand.
if (stock.get() > 0) {
    stock.decrementAndGet();
    acceptOrder(); // Hypothetical business method, not defined here.
}
~~~

**get()** and **decrementAndGet()** are both thread-safe, but **the check-then-decrement pair** is not atomic. Two threads can both read stock = 1 and then each decrement once. The result is **stock = -1** and two orders accepted. This is a **logic race** and a **race condition**, even without a data race on the stock variable.

### Example 2: Forcing Both Threads Past the Check Condition

File **LogicRaceDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class LogicRaceDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger stock = new AtomicInteger(1);
        AtomicInteger accepted = new AtomicInteger(0);
        CountDownLatch bothChecked = new CountDownLatch(2);

        Runnable reserve = () -> {
            if (stock.get() > 0) {
                bothChecked.countDown();
                try {
                    bothChecked.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }

                stock.decrementAndGet();
                accepted.incrementAndGet();
            }
        };

        Thread a = new Thread(reserve, "buyer-a");
        Thread b = new Thread(reserve, "buyer-b");
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("accepted = " + accepted.get());
        System.out.println("stock = " + stock.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 LogicRaceDemo.java
java LogicRaceDemo
~~~

Stdout (without external interrupts):

~~~text
accepted = 2
stock = -1
~~~

**Why is this example noteworthy?**

- Before any decrement happens, both threads see stock = 1. The latch makes each thread wait for the other after passing the check, so the invariant-violating schedule is deliberately reproduced.
- **AtomicInteger** keeps each individual update atomic, so there is no plain-int lost update: both decrements take effect and stock goes from 1 down to -1.
- The bug lies in the gap between **reading the condition** and **acting**. This is **time-of-check to time-of-use (TOCTOU)**.
- Increasing the thread count or adding **sleep()** or **yield()** can change the probability of failure, but does not fix the rule.

**Do not use the code above for real order placement**; this is an example that intentionally violates the business rule to demonstrate a logic race.

## 7. Fixing a Logic Race with CAS Protecting the Entire Decision

We replace **check then decrement** with a **compare-and-set (CAS)** loop: read the current quantity, reject if it is 0, and only decrement if the value still equals the number we read. If another thread changed stock in the meantime, retry.

File **SafeReservationDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class SafeReservationDemo {

    static boolean tryReserve(AtomicInteger stock) {
        while (true) {
            int observed = stock.get();
            if (observed <= 0) {
                return false;
            }
            if (stock.compareAndSet(observed, observed - 1)) {
                return true;
            }
            // Another thread changed stock; re-read and retry.
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicInteger stock = new AtomicInteger(1);
        AtomicInteger accepted = new AtomicInteger(0);

        Runnable reserve = () -> {
            if (tryReserve(stock)) {
                accepted.incrementAndGet();
            }
        };

        Thread a = new Thread(reserve, "buyer-a");
        Thread b = new Thread(reserve, "buyer-b");
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("accepted = " + accepted.get());
        System.out.println("stock = " + stock.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SafeReservationDemo.java
java SafeReservationDemo
~~~

Stdout:

~~~text
accepted = 1
stock = 0
~~~

Both threads may attempt CAS at the same time, but only one **1 → 0** transition succeeds; the other thread sees 0 and rejects. The result preserves the invariant within the scope of **a single AtomicInteger in a single JVM**, assuming other stock updates also go through a compatible protocol.

**Important caveat:** This example only maintains **an in-memory stock count**. If the operation also involves writing an order, charging money, or writing to a DB, a CAS on stock **does not make external side effects atomic**. You must design appropriate transactions, idempotency, or commit/compensation mechanisms at the real data boundary.

### Using synchronized When a Decision Involves Multiple Fields

Illustrative class API example, not a standalone program:

~~~java
final class Inventory {
    private int stock;
    private int reserved;

    Inventory(int initialStock) {
        stock = initialStock;
    }

    synchronized boolean reserveOne() {
        if (stock <= 0) {
            return false;
        }
        stock--;
        reserved++;
        return true;
    }

    synchronized int remaining() {
        return stock;
    }

    synchronized int reservedCount() {
        return reserved;
    }
}
~~~

The **reserveOne()** method holds the same monitor throughout both the check and the update of both fields. Other methods accessing the two fields must also use a compatible locking protocol. If you only lock around **stock--** while leaving **if (stock > 0)** outside the lock, the logic race remains.

For shared memory, the key point is **the atomicity scope of the invariant**, not the number of **synchronized** keywords or the number of fields declared **volatile**.

## 8. Check–Then–Act Bug Patterns in Concurrent APIs

Using a thread-safe data structure does not mean **every combination of multiple calls** on it is automatically atomic.

### ConcurrentHashMap: containsKey() Then put()

~~~java
// Logic race illustration:
// map is a previously declared ConcurrentHashMap<String, String>.
if (!map.containsKey("job-42")) {
    map.put("job-42", "RUNNING");
}
~~~

Each call to **containsKey()** and **put()** is thread-safe, yet two threads can both observe that the key is absent and then both do the work. If you only want to **write a value when the key is not yet present**, use:

~~~java
// Illustration: putIfAbsent is an atomic conditional operation.
String previous = map.putIfAbsent("job-42", "RUNNING");
if (previous == null) {
    // This write succeeded for a previously absent key.
}
~~~

Note: if both threads have already **invoked an expensive task or side effect before putIfAbsent()**, putIfAbsent cannot undo or prevent the duplicate external execution. You must place the authorization decision at the right point in the protocol. When initializing a value by key, **computeIfAbsent()** has different semantics from a **get/put** pair, but the mapping function must obey the collection's contract and should not contain uncontrolled side effects.

### Concurrent Collection: Check Empty Then Poll

~~~java
// Logic race illustration, queue declared beforehand:
if (!queue.isEmpty()) {
    Object item = queue.poll();
    // item can still be null if another thread took the element first.
}
~~~

If you need to retrieve an element, work with the result of **poll()** and handle **null** when empty; if you need to wait for an element to arrive, consider **BlockingQueue.take()**. Two calls **isEmpty() + poll()** do not merge into an atomic delivery decision.

### Data Race and Logic Race Can Coexist

If **stock** is an unlocked plain int, the snippet **if(stock > 0) stock--;** can contain **both a data race** and a logic race. Replacing it with AtomicInteger while keeping the two-step **get() then decrementAndGet()** only fixes the synchronization aspect of each individual access; **it does not fix the invariant**.

## 9. Race Conditions Don't Live Only in RAM

TOCTOU also exists in filesystems, databases, networks, and inter-process workflows:

- Checking if a file exists, then opening it: another actor can delete or replace the file in between.
- Reading an order in PENDING state, then updating it to RUNNING: another worker may have already claimed the same order before the update.
- Checking inventory count in a DB and creating an order in another transaction: two requests can both pass the check.
- Receiving a message and processing it; when the message is redelivered, side effects can execute a second time without idempotency.

These cases can happen **between two processes/JVMs**, without two threads sharing a Java field. **AtomicInteger** and **synchronized** within one JVM do not protect data manipulated concurrently by other processes.

The solution must live **where the invariant is managed**:

| Contention boundary | Typically suitable mechanism |
| --- | --- |
| A single atomic variable in the same JVM | AtomicInteger/AtomicReference CAS |
| Multiple shared variables in the same JVM | synchronized/Lock or immutable state design |
| Queue between threads | BlockingQueue and its communication contract |
| Shared data across multiple instances | Transactions, unique constraints, optimistic concurrency/versioning, or conditional updates at the DB |
| Operations with repeated side effects on retry | Idempotency key, attempt state, contract-based deduplication |

These are choices about **preserving correctness conditions**, not mechanical drop-in replacements for one another. For example, a *unique constraint* protects uniqueness in the DB, but does not by itself guarantee that an external service call is executed at most once.

## 10. Correctness Conditions: Write the Invariant Before Choosing a Lock

Before fixing a race condition, write down what **must always be true**:

- A counter receiving two increments must yield **2**.
- If initial stock is 1 item, **accepted <= 1** and **stock >= 0**.
- A job may only be transitioned from **PENDING** to **RUNNING** by one worker per processing attempt.
- After receiving a cancellation request, a task must not mark itself **SUCCEEDED** if the cancellation policy won the race.

Then identify the **linearization point**: a logical point at which the operation can be treated as taking place atomically with respect to other threads.

In **SafeReservationDemo**, the successful **compareAndSet(1, 0)** is the point that confirms the right to reserve an item. For a database transaction, the authorization point might be a conditional update statement **affecting exactly one row** committed under the storage engine's protocol. A linearization point must not be arbitrarily assigned to a log line or a **sleep()** call.

Not every problem requires full linearizability; some computations use eventual consistency or tolerate duplicate processing. However, **which tolerance and ordering rules apply** must be explicitly specified rather than left to accidental execution schedules.

### Distinguishing Atomicity, Thread Safety, and Business Correctness

- **Single-operation atomicity:** an incrementAndGet() cannot be split into separately observable steps on that AtomicInteger.
- **Component thread safety:** ConcurrentHashMap upholds the guarantees of each documented operation.
- **Business-sequence atomicity:** “read stock, reserve item, write order, return confirmation” requires its own multi-step protocol.
- **Correctness:** the final outcome conforms to the specification even under contention, timeouts, retries, cancellations, or crashes (if within scope).

You cannot deduce the third and fourth items from the first two alone.

## 11. Why sleep(), yield(), Logs, and a Single Test Run Are Not Enough

Triggering a race bug can depend on a very narrow timing window. Adding **System.out.println(...)**, JIT compilation, I/O, and the scheduler can all alter the execution schedule. A bug that disappears when logging is enabled is not proven fixed.

The following approaches **are not valid solutions**:

~~~java
// Illustrative anti-pattern; not a standalone program:
if (ready) {
    Thread.sleep(10); // Does not make check-then-act atomic.
    doWork();
}

while (!ready) {
    Thread.yield(); // Guarantees neither visibility nor progress.
}
~~~

In the snippet above, **ready** and **doWork()** are hypothetical; sleep throws a checked exception that must be handled. If ready is a plain field modified from another thread, even observing the flag can lack memory guarantees.

To test on solid footing:

1. **Write down the invariants** and list concurrent scenarios that could violate them.
2. **Control interleaving with latches/barriers**, forcing two threads to reach the sensitive spot together as shown in the examples. Use these tools to reproduce bugs; do not treat barriers as fixing operation atomicity.
3. **Repeat stress tests** with varying thread counts and loads; record seeds/configurations if applicable. Passing every run still does not prove the program is race-free.
4. **Assert final state** and count side effects, instead of only checking “no exception thrown”.
5. **Audit happens-before and critical sections**: which lock protects which field, which update path bypasses the lock/CAS, and is check/use split apart?
6. **Account for retries, cancellation, and late side effects** if work spans multiple attempts or processes. Do not let an old attempt's result overwrite a newer attempt's state.

Reasoning about correctness from synchronization contracts and invariants is primary; testing is a tool to uncover bugs and build confidence, not a substitute for that reasoning.

## 12. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| Data race and race condition are the same thing | Data race is about memory accesses lacking HB; race condition is about schedule dependence causing a requirement violation |
| Every race condition involves a data race | A logic race using exclusively atomic operations can still be wrong |
| Using AtomicInteger makes the whole business flow safe | Individual atomic operations do not make a check–then–act sequence atomic |
| One run producing the right value means there is no data race | It may simply be due to a lucky execution schedule |
| Two log lines appearing in swapped order is always a race bug | It is only a bug if that ordering violates the specification |
| volatile makes **count++** atomic | volatile does not merge read–modify–write |
| sleep/yield guarantees another thread has finished updating | Neither provides a synchronization protocol or scheduler guarantee |
| ConcurrentHashMap makes every get/put pair safe like a transaction | Only operations with matching atomic contracts provide that guarantee |
| synchronized on each individual method is enough | If an invariant spans two methods, threads can still interleave between the two lock acquisitions |
| AtomicInteger protects inventory shared across multiple JVMs | AtomicInteger only manages a variable within a single JVM |
| Running tests many times without failure means no race remains | The failing schedule may simply not have occurred; prove via invariants and HB |

## 13. Reasoning Exercises

**Exercise 1.** Two threads increment a **plain int** 1,000 times each, and this run happens to yield 2,000. Does that prove there is no data race?  
**Answer:** No. The conflicting reads/writes still lack proper synchronization; a lucky schedule may simply avoid lost updates. Use an atomic increment or a lock protecting the entire increment.

**Exercise 2.** Two threads call **stock.get() > 0** then **stock.decrementAndGet()**, each call being atomic. Why can stock still go negative?  
**Answer:** The condition is checked on a snapshot, with no guarantee the value holds until the decrement. You need a CAS loop or a critical section wrapping both check and update.

**Exercise 3.** One thread uses **synchronized** around a check method, and another uses synchronized around a decrement method, both on the same lock. Is that enough to prevent overselling?  
**Answer:** No, if check and decrement are in two separate critical sections. Another thread can interleave in between. The entire decision must sit inside a single critical section or an equivalent atomic conditional operation.

**Exercise 4.** Two workers write to a **ConcurrentHashMap** with no data race on the operations. Can we be sure a job runs only once?  
**Answer:** No. If they check that the job is absent and execute it before the claiming step, both workers can still do the work. You must design atomic claiming and retry/idempotency rules.

**Exercise 5.** If a program uses no shared mutable state and only receives two network responses arriving in nondeterministic order, can it still have a race condition?  
**Answer:** Yes, if the business outcome requires ordering or uniqueness but the code handles whichever response arrives first without a rule. It is not necessarily a JMM data race.

**Exercise 6.** Why is CountDownLatch needed in **LogicRaceDemo**?  
**Answer:** To force both threads past the check step while stock is still 1 before allowing either to decrement. That reliably reproduces the oversell result. The latch does not fix the check–then–act invariant.

**Exercise 7.** An **AtomicInteger** gives the right result after two workers join. Is join what prevented lost updates?  
**Answer:** No. **incrementAndGet()/CAS** ensures atomic updates; **join()** only lets the caller wait for the workers to finish before observing the completed result.

## 14. Summary

- **Data race**: conflicting accesses from multiple threads to the same variable, at least one write, lacking JMM happens-before ordering.
- **Race condition**: an interleaving can cause the result to violate a correctness requirement; does not require a data race.
- **Logic race**: a race condition in coordinating multiple steps of an application rule, typically **check–then–act/TOCTOU**.
- **The fix** must start from the invariant: identify the data and decision scope that must be atomic, and use synchronization/CAS/transactions or claiming protocols at the right boundary.
- **Verify interleavings and final state**, but never use sleep, yield, or lucky test runs as a substitute for a synchronization contract.
