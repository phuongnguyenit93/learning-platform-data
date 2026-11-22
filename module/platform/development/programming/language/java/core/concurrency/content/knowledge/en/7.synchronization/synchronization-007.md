# Lock Ordering to Prevent Deadlock in Java

## 1. When Two Threads Need to Hold Multiple Locks

A concurrent operation sometimes must update **multiple objects as a consistent unit**: transferring money between two accounts, moving elements between two structures, changing the owner of a resource, or updating two related components. To protect invariants, the code may need to hold two locks at the same time.

However, if threads acquire locks in different orders, one thread may hold lock A and wait for B, while another thread holds B and waits for A. Both are waiting for a resource held by the other; a **deadlock** occurs and neither thread can make progress on its own.

**Lock ordering** is the rule that all code paths must acquire multiple locks in **the same stable global order**. When the order is applied consistently, lock-wait relationships go in one direction along that order, eliminating the wait-cycle pattern arising solely from the locks in this protocol.

This lesson focuses on **general Java synchronization and concurrency**: intrinsic monitors via `synchronized`, `ReentrantLock`, ordering rules, limitations, and diagnostics. No framework is needed to apply it.

### Learning Outcomes

After this lesson, you can:

1. Identify wait cycles in a wait-for graph and explain why two individually locked regions can still deadlock.
2. Define a global order across resources, including cases where two callers pass arguments in opposite orders.
3. Create a Java 17+ example that acquires locks in a fixed order and preserves multi-object invariants.
4. Understand the conditions required to prove that lock ordering prevents deadlock, the limitations of `tryLock`/timeouts, and pitfalls with callbacks, hidden locks, and mixed lock types.
5. Inspect thread dumps, the `BLOCKED` state, and `ThreadMXBean.findDeadlockedThreads()` output to investigate monitor/ownable synchronizer deadlocks.

## 2. Deadlock and the Wait-for Graph

### 2.1. Two Paths with Reversed Lock Order

Consider two locks A and B.

**Thread 1**:

~~~java
// ILLUSTRATION of risk; lockA and lockB are already declared.
synchronized (lockA) {
    synchronized (lockB) {
        doWork();
    }
}
~~~

**Thread 2**:

~~~java
// ILLUSTRATION of risk; same two locks as above but in reverse order.
synchronized (lockB) {
    synchronized (lockA) {
        doOtherWork();
    }
}
~~~

If thread 1 acquires A, thread 2 acquires B, and each then requests the remaining lock, they wait for each other indefinitely unless there is external intervention. `synchronized` has no timeout when waiting to acquire a monitor; `Thread.interrupt()` alone cannot break a thread that is `BLOCKED` waiting to enter a monitor.

Wait diagram:

~~~text
Thread 1 holds A ---> needs B ---> B is held by Thread 2
      ^                                     |
      |                                     v
      +------------- Thread 2 needs A <-----+
~~~

This is a **resource wait cycle**. Having A and B protected by two separate `synchronized` blocks is not wrong; what is dangerous is **inconsistent lock nesting order**.

### 2.2. The Four Coffman Conditions

A lock-resource deadlock typically involves four conditions simultaneously:

| Condition | Meaning in lock contention |
| --- | --- |
| Mutual exclusion | A lock allows only one owner at any given time |
| Hold and wait | A thread holds one lock while continuing to wait for another lock |
| No preemption | A lock held by another thread cannot be forcibly taken away |
| Circular wait | There is a cycle where A waits for B, B waits for C, …, Z waits for A |

Lock ordering primarily **breaks the circular wait condition** by dictating the direction of lock acquisition. It does not require removing mutual exclusion or weakening invariant protection. However, the argument holds only if **every code path participating in the same lock system** follows the order and other dependencies/hidden locks have also been accounted for.

Deadlock differs from **starvation** (a thread is consistently disadvantaged during contention), **livelock** (threads continuously change state without making progress), and **long blocking** due to I/O. A hung application does not automatically mean a deadlock cycle exists.

## 3. The Lock Ordering Principle: Establishing a Total Order

Suppose each resource has its own lock. Assign each resource a **unique, stable rank**; for example, account 100 has a lower rank than account 200. With two locks, the code must always:

1. Determine which lock has the lower rank.
2. Acquire the lower-ranked lock first.
3. Acquire the higher-ranked lock second.
4. Perform the operation that needs protection.
5. Exit the lock region according to the corresponding mechanism.

Even if the call is `transfer(from=A,to=B)` or `transfer(from=B,to=A)`, the lock acquisition order **does not depend on the business direction**; it is still A then B if A has the lower rank.

### Why Does This Rule Prevent Wait Cycles?

Suppose all threads may only hold a lower-ranked lock when waiting for a higher-ranked lock. When a wait chain exists, the ranks of the locks being waited on must strictly increase. A wait cycle would require ranks to keep increasing and then return to a smaller initial lock, contradicting strict ascending order. Therefore, no cycle can form **among locks that follow this protocol**.

Essential conditions:

- Each distinct resource must have a **distinct** rank; ties must have a clear tie-breaking rule.
- Ranks **must not change while the resource is active**.
- **All code acquiring two locks** must use the same rule, including reading a multi-object snapshot.
- If currently holding a higher-level lock, do not call a method that acquires a lower-level lock.
- Callbacks, listeners, complex logging, or out-of-scope code calls may acquire additional locks; locks acquired **indirectly** must also be accounted for.

This is a design principle applied across all execution paths of the program, not just a few lines of code in a single method.

## 4. Runnable Example — Transferring Data with a Stable Lock Order (Java 17+)

Suppose two in-memory accounts have a `balance`; transferring between them needs to be atomic across **both accounts**. Each account has a **private** monitor and a rank assigned at creation.

Create the file `OrderedTransferDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicLong;

public class OrderedTransferDemo {
    static final class Account {
        private static final AtomicLong NEXT_ID = new AtomicLong();
        private final long lockOrderId = NEXT_ID.getAndIncrement();
        private final Object lock = new Object();
        private int balance;

        Account(int initialBalance) {
            if (initialBalance < 0) {
                throw new IllegalArgumentException("Negative balance");
            }
            balance = initialBalance;
        }

        int balance() {
            synchronized (lock) {
                return balance;
            }
        }
    }

    static void transfer(Account from, Account to, int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        if (from == to) {
            return;
        }

        Account first = from.lockOrderId < to.lockOrderId ? from : to;
        Account second = first == from ? to : from;

        synchronized (first.lock) {
            synchronized (second.lock) {
                if (from.balance < amount) {
                    throw new IllegalArgumentException("Insufficient funds");
                }
                from.balance -= amount;
                to.balance += amount;
            }
        }
    }

    static int total(Account a, Account b) {
        if (a == b) {
            return a.balance();
        }

        Account first = a.lockOrderId < b.lockOrderId ? a : b;
        Account second = first == a ? b : a;

        synchronized (first.lock) {
            synchronized (second.lock) {
                return a.balance + b.balance;
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Account a = new Account(100);
        Account b = new Account(100);

        Thread one = new Thread(
            () -> transfer(a, b, 10), "transfer-a-to-b"
        );
        Thread two = new Thread(
            () -> transfer(b, a, 20), "transfer-b-to-a"
        );

        one.start();
        two.start();
        one.join();
        two.join();

        System.out.println(
            "A=" + a.balance() + ", B=" + b.balance()
        );
        System.out.println("total=" + total(a, b));
    }
}
~~~

Compile and run:

~~~bash
javac OrderedTransferDemo.java
java OrderedTransferDemo
~~~

Stdout when both transfers complete normally:

~~~text
A=110, B=90
total=200
~~~

**Explanation of the output:**

- Account A starts with 100, sends 10, and receives 20, so it ends at 110. B receives 10 then sends 20, so it ends at 90. Both transactions are valid regardless of which thread acquires the locks first.
- `AtomicLong` assigns a unique rank to each `Account` in the example. The lock protecting `balance` is `private final Object lock`, so callers cannot accidentally `synchronized` on a public monitor.
- Both `transfer` and `total` order locks by `lockOrderId` and acquire `first.lock` before `second.lock`. Thus, no call path reverses A/B simply because the transfer direction changed.
- Both updates `from.balance -= amount` and `to.balance += amount` happen while holding both monitors; an aggregate read operation also holds the exact same two monitors so it never observes a half-completed transfer.
- `balance()` also acquires the corresponding monitor. In the example, the two individual reads only run **after `join()`**, when no transfers are active. If you want to read **both balances concurrently as a snapshot**, you must use a method that acquires both locks in order like `total` or returns an immutable snapshot containing both fields.
- `Thread.join()` waits for each thread to finish, but `join()` itself does not retry a failed transaction and does not automatically report thread errors. In production, you need a mechanism to retrieve task results/exceptions rather than assuming a terminated thread succeeded.

**Scope of the example:** The code manages two objects within a single JVM process. It illustrates Java in-memory locking; it does not replace transactions or inter-process synchronization for data in a database or other services. In real-world cases where enough accounts could be created for `long` ranks to wrap around, you must use a non-colliding ID allocation mechanism or handle overflow; the example assumes IDs have not overflowed.

### What Happens When You Try Writing by Transfer Direction?

A dangerous design often writes:

~~~java
// Incorrect illustration, not a standalone program.
synchronized (from.lock) {
    synchronized (to.lock) {
        moveBalance(from, to, amount);
    }
}
~~~

If one caller transfers A → B and another caller transfers B → A, they acquire locks in opposite orders. Therefore, locks must be ordered by **resource order**, not by the `from`/`to` role.

## 5. How to Choose Locks and Ranks?

### 5.1. Use Private Locks Instead of Locks Easily Held by External Code

A public object or a widely shared `String` can accidentally be used as a monitor by another component. In that case, your method does not know which locks are already held before it runs.

Prefer:

~~~java
// Illustration inside a class; not a standalone program.
private final Object lock = new Object();

void update() {
    synchronized (lock) {
        // Protect internal state.
    }
}
~~~

Do not use `synchronized(this)` out of habit if the instance is passed to many components and you do not control where it might be locked. A `private final` lock helps express ownership. However, a class using multiple private locks must still define an ordering relationship between them if any methods hold more than one lock.

### 5.2. Choose Immutable and Totally Ordered Ranks

A **unique and immutable** business ID is a good choice if the contract guarantees it is truly unique. If the ID can change, locking based on a dynamic ID will cause two threads to use two different orders.

You can assign a dedicated rank when constructing the object. For multiple lock levels, define a common order, for example:

~~~text
Lock level 10: global configuration
Lock level 20: session
Lock level 30: child resource
Lock level 40: local cache
~~~

If you hold a level 30 lock and then call code that needs a level 10 lock, that call path violates the protocol. You do not need to hold all four locks at all times; the rule only applies when multiple locks are held simultaneously.

### 5.3. Be Careful with `hashCode()` and `System.identityHashCode()`

You should not automatically order locks by `object.hashCode()`:

- `hashCode()` can be overridden by a class, may depend on mutable state, or may not be unique.
- `System.identityHashCode(object)` is stable per identity over the object's lifetime, but it **can collide** between two different objects.
- If two threads process a pair A/B with equal identity hashes and "keep the input order," they can still reverse the locks and deadlock.

If a design relies on identity hashes, it needs a shared **tie lock** for collisions, or better yet, distinct ranks assigned in a controlled manner. Never assume two hash codes are always different.

### 5.4. What If Two Parameters Point to the Same Object?

Java monitor lock objects are **reentrant**: the same thread can `synchronized` on the same monitor multiple times without self-deadlocking. However, the design should still handle `from == to` explicitly, as that may be a no-op transaction or require specific business behavior.

With `ReentrantLock`, the same thread can also re-acquire a lock it already owns; it must release it the exact number of times it was acquired. With **non-reentrant locks** or other primitives, re-acquiring the same lock can cause a self-deadlock. Therefore, the lock ordering rule should handle duplicate parameters and account for the type of primitive being used.

## 6. With Three or More Locks: Order Must Be System-Wide Consistent

Suppose A, B, and C are ordered A < B < C. Valid paths when multiple locks are needed will follow ascending order, such as A → C or A → B → C. A path C → A can form a cycle with other paths and must be fixed.

### Example of Three Threads with a Wait Cycle

~~~text
Thread 1: holds A, waits for B
Thread 2: holds B, waits for C
Thread 3: holds C, waits for A

Wait-for graph:
  T1 --> T2 --> T3 --> T1
~~~

Looking at each method in isolation may not reveal the cycle. It can form through nested calls or across modules sharing the same resources.

If a code path needs to acquire multiple locks, collect the locks, deduplicate by identity, and **sort by the common rank** before acquiring them. When using `Lock`, release all acquired locks in `finally`, in reverse order for easier verification.

**Do not sort only by "current" data** if the involved locks can be replaced or their ranks change during execution. The rank used for sorting must be durable, and callers must share the same definition.

### Lock Ordering Review Table

| Code Path | Locks Acquired in Order | Satisfies A < B < C? |
| --- | --- | --- |
| Process A then B | A → B | Yes |
| Read snapshot of A and C | A → C | Yes |
| Check B then C | B → C | Yes |
| Update C then call function using A | C → A | **No** |
| Acquire A then B then C | A → B → C | Yes |
| Invoke callback while holding C and callback acquires B | C → B | **No** |

Mapping out such call paths often uncovers risks hidden by helper methods or callbacks.

## 7. `synchronized` and `ReentrantLock` in Lock Ordering

### 7.1. Intrinsic Monitors

`synchronized` has the advantage of automatically releasing the monitor when exiting the block, even when an exception occurs. The drawback when debugging deadlocks is that entering a monitor has no timeout or `lockInterruptibly` mechanism; a thread `BLOCKED` waiting for a monitor cannot use interruption alone to immediately stop waiting for the lock.

Global ordering is the real prevention; once stuck, you usually have to inspect thread dumps and fix the code.

### 7.2. Explicit Locks

`ReentrantLock` supports `lock()`, `tryLock()`, `tryLock(timeout, unit)`, and `lockInterruptibly()`. It allows deciding **not to wait indefinitely** in certain cases, but it does not enforce lock ordering on its own.

Example pattern with two locks already ordered properly:

~~~java
// Java 17+ illustration, assuming first/second are distinct ReentrantLocks.
first.lock();
try {
    second.lock();
    try {
        updateTogether();
    } finally {
        second.unlock();
    }
} finally {
    first.unlock();
}
~~~

Always unlock the correct lock, even if the update throws an exception. If there are more locks, wrap the ordering and cleanup in a clear abstraction; avoid complex copy-pasting that leads to unlocking mistakes.

**Note:** `ReentrantLock.lock()` can wait indefinitely, even if the thread is interrupted before or while waiting; after acquiring, the interrupt flag may still be set. If you want lock acquisition to respond to interruption, use `lockInterruptibly()` or timed `tryLock` and handle `InterruptedException` appropriately.

### 7.3. `tryLock` Is Controlled Failure, Not a Full Design Replacement

`tryLock()` can return `false` immediately if the lock is unavailable. `tryLock(timeout, unit)` waits for a bounded time and can throw `InterruptedException`. When acquiring multiple locks, if the next lock cannot be acquired, you must release the locks already held, then return a failure result or retry according to policy.

A short, complete example showing the choice to **not block indefinitely**.

Create the file `TryLockDemo.java`:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public class TryLockDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        lock.lock();

        try {
            Thread worker = new Thread(() -> {
                if (lock.tryLock()) {
                    try {
                        System.out.println("Acquired");
                    } finally {
                        lock.unlock();
                    }
                } else {
                    System.out.println("Lock unavailable");
                }
            }, "competitor");

            worker.start();
            worker.join();
        } finally {
            lock.unlock();
        }
    }
}
~~~

Compile and run:

~~~bash
javac TryLockDemo.java
java TryLockDemo
~~~

Stdout:

~~~text
Lock unavailable
~~~

The `main` thread holds the `ReentrantLock` throughout the time the worker calls `tryLock()`. The worker is on another thread so `tryLock()` fails immediately, prints one line, and finishes. `join()` returns, after which `main` releases the lock in `finally`. This is a contrived example for deterministic output; in a normal program, `tryLock` may succeed or fail depending on lock state.

Distinguish between **avoiding indefinite blocking** and **guaranteeing a successful update**: when the lock cannot be acquired, the business operation has not been performed. The caller must have a rule to return an error, enqueue, cancel, retry a bounded number of times, or wait until a deadline—never pretend the update succeeded.

### 7.4. Retry and Backoff Also Have Pitfalls

If two threads each acquire one lock, fail to acquire the second, and immediately retry in lockstep, they can fall into a **livelock** or waste CPU. Solutions may include backoff, jitter, and a retry limit; however, retrying does not fix an inconsistent lock order at the core of the design. Prefer lock ordering rules whenever possible.

With timed `tryLock`, the business deadline must be calculated across **the entire lock chain**, avoiding waiting up to N seconds per lock and multiplying latency several times over.

## 8. Deadlocks Caused by Hidden Locks and External Code Calls

Even if your method always acquires A then B, the program can still deadlock if it is holding a lock that was not accounted for in the ordering. For example:

- Holding an account lock and calling a plugin-written callback; the callback tries to acquire a lower-ranked global config lock.
- Holding a cache lock and unknowingly calling a `synchronized` method on another object; another thread holds that object and needs the cache.
- Holding a monitor while performing logging, observer notification, or calling an overridden method that may call back into the original code.
- Holding a lock while waiting on `Future.get()`; the task inside the future needs the very lock being held.
- Creating a dependency between workers in a single-worker thread pool: task A waits for task B in the same pool, but B has no worker available to run.

The last two cases can be **task-dependency deadlocks** or pool starvation, even without a two-monitor wait cycle. Monitor lock ordering alone does not handle every kind of wait.

Prevention principles:

1. Keep critical sections **short**; prepare data outside the lock when safe.
2. Avoid calling callbacks or third-party code while holding a lock if possible.
3. Do not wait indefinitely for I/O, network, user input, or other tasks while holding a lock.
4. Document which locks each method requires; if a method calls deep into other code, check for hidden locks.
5. If multiple locks must be held, treat them as **a single ordering protocol** across all involved layers.

## 9. How to Detect Deadlocks in the JVM?

### 9.1. Symptoms

Some signs: requests hang continuously, threads do not finish despite making no progress, CPU may be low, and thread dumps show `BLOCKED` or `WAITING` threads. However, low CPU and many waiting threads are not enough to conclude deadlock: normal applications also have workers waiting on queues/locks.

**Strong evidence** is a resource cycle where each thread holds a lock that another thread is requesting, or JVM tooling reports a deadlock.

### 9.2. Thread Dumps and JDK Tools

You can use tools corresponding to your deployed JDK/JVM version:

~~~bash
jcmd <PID> Thread.print -l
~~~

or when `jstack` is available:

~~~bash
jstack -l <PID>
~~~

`<PID>` is the actual JVM process ID; the lines above are **command templates** that must be replaced with the real PID. They are not the stdout of a demo program.

In a thread dump, look at thread names, stack frames waiting on monitors, owned lock information, and locks being waited on. For monitor deadlocks detected by the JVM, many dumps include a deadlock section listing the lock/owner chain.

Meaningful states:

| Common State | Interpretation |
| --- | --- |
| `BLOCKED` | Thread is waiting to acquire an intrinsic monitor for a `synchronized` block |
| `WAITING` | May be waiting on `Object.wait`, `LockSupport.park`, `Thread.join`, or another primitive |
| `TIMED_WAITING` | Waiting with a deadline/time limit; not automatically a deadlock |
| `RUNNABLE` | Executing or ready to run; does not by itself prove useful progress |

With `ReentrantLock`, a thread may appear in `WAITING` or `TIMED_WAITING` (waiting via `LockSupport`), not `BLOCKED` waiting on an intrinsic monitor. Therefore, do not filter only for `BLOCKED` threads when investigating.

### 9.3. ThreadMXBean

`java.lang.management.ThreadMXBean` provides:

- `findMonitorDeadlockedThreads()`: detects deadlock cycles involving **object monitors**.
- `findDeadlockedThreads()`: finds deadlock cycles involving **object monitors and ownable synchronizers**, when supported by the JVM; it does not detect all forms of non-JVM waits or system-dependent deadlocks.
- `getThreadInfo(ids, true, true)`: retrieves monitor and synchronizer information according to JVM support.

Query example, **not a standalone program**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

ThreadMXBean bean = ManagementFactory.getThreadMXBean();
if (bean.isSynchronizerUsageSupported()) {
    long[] ids = bean.findDeadlockedThreads();
    if (ids != null) {
        System.out.println("Deadlocked threads: " + ids.length);
    }
}
~~~

The snippet above only queries information; the application must have an alerting/investigation mechanism and avoid polling at a frequency that incurs high overhead. Not finding a cycle at a single point in time does not prove all threads are progressing well, nor does it rule out a deadlock occurring later.

### 9.4. When a Deadlock Is Detected in Production

Collect thread dumps or appropriate JFR/logs, identify which thread holds/waits on which lock, trace the call sources into the monitors/locks, draw the wait-for graph, and find the reversed-order path. Fix the lock-acquisition protocol in the source code; avoid treating process restarts as the root solution. If operational intervention is needed, note that force-stopping threads while they hold invariants can corrupt state.

Do not use `Thread.stop()` to "break a deadlock": this API is unsafe, deprecated, and not a valid recovery strategy.

## 10. Testing Lock Ordering Rules

A simple test that spawns two threads and sleeps for 100 ms does not prove the absence of deadlock; the threads might run sequentially during that test run.

For meaningful testing:

1. Design **invariants** to preserve: total balance, element count, update state, record ordering.
2. Launch multiple tasks in both operation directions (A → B, B → A), optionally using `CountDownLatch` or `CyclicBarrier` to start contention simultaneously.
3. Wait for completion with a test-level timeout; if it times out, collect a thread dump and determine why. A timeout alone does not prove deadlock.
4. Check results/invariants after all tasks finish; do not treat "did not hang" as sufficient.
5. Analyze **all call paths and hidden locks**, including snapshot getters, callbacks, and error handlers.
6. Run appropriate stress tests and measure contention/latency, but treat the **ordering argument** as the primary design guarantee.

An example test can generate multiple account pairs, transfer back and forth, and verify that the total is unchanged, balances are non-negative, and no threads are stuck. Limit the number of tasks and wait time so the test does not hang forever when a bug is detected.

## 11. Common Pitfalls

**"Always lock the `from` object before `to`."** When two callers go in opposite directions, they reverse the order and can create a wait cycle. Order by a stable rank independent of business direction.

**"`hashCode` is a unique order."** Hashes can collide and be overridden. Use a dedicated unique rank or a consistently applied tie-breaker.

**"Just fixing where two `synchronized` blocks are nested is enough."** Code can acquire locks indirectly via helpers/callbacks; you must check the entire call graph and multi-level lock acquisition paths.

**"`ReentrantLock` automatically avoids deadlock."** Explicit locks can still be acquired in the wrong order. `tryLock`/timeouts prevent waiting forever in some situations, but require cleanup and a retry policy.

**"Acquiring two locks is very fast so it cannot deadlock."** Deadlock depends on contention order, not just critical section duration. Short lock hold times reduce probability, not prove safety.

**"Only `BLOCKED` threads can deadlock."** `ReentrantLock` waits via `LockSupport`; `Future` or queue dependencies can put threads in `WAITING`. Read stack traces and owner info.

**"Every timeout is a deadlock."** Timeouts can result from CPU overload, slow I/O, starvation, or worker pool exhaustion. You need evidence of the wait chain and resource types.

**"Once lock ordering is used, all concurrency bugs disappear."** Lock ordering only addresses one class of deadlocks; data can still race if there are unlocked read/write paths, or the system can still suffer from livelock, starvation, cancellation bugs, timeouts, and external resource failures.

## 12. Pre-Production Review Checklist

| Question | Criteria |
| --- | --- |
| Do any resources require holding two locks at once? | All call paths listed, including snapshot reads |
| Is each lock's rank unique and stable? | Does not depend on input order, mutable state, or colliding hashes |
| Do all code paths acquire locks in the same order? | No helper/callback secretly acquires a lower-ranked lock while holding a higher-ranked one |
| Are locks privately encapsulated? | Avoid external code unexpectedly holding the monitor |
| Does code perform I/O or wait on tasks while holding a lock? | Unbounded waits minimized |
| Are `ReentrantLock`s properly unlocked in `finally`? | Every acquire has a matching release |
| Does lock acquisition failure return a clear result? | No partial updates, no infinite retries |
| Is there a way to investigate deadlocks? | Thread dumps/JFR/metrics, stacks, and lock owners |
| Are invariants checked after concurrent runs? | Multi-directional tests, with timeouts and diagnostics |
| Are limitations understood? | Lock ordering does not automatically handle resource deadlocks outside the ordered locks |

### Self-Check Questions

**1.** Thread 1 acquires A → B; thread 2 acquires B → A. When does a deadlock occur?

When thread 1 holds A and needs B while thread 2 holds B and needs A, forming a wait cycle. Each individual lock working properly does not eliminate this cycle.

**2.** In a system with rank A < B, which lock should be acquired first when transferring money from B to A?

Still **A then B**, regardless of the B → A business direction.

**3.** Why is ordering locks by `System.identityHashCode` without handling equal values insufficient?

Two different objects can have the same identity hash. If two threads keep the parameter order on a tie, they can acquire A/B in opposite orders. A tie lock or unique rank is needed.

**4.** A thread is `BLOCKED` waiting to enter `synchronized`. Does calling `interrupt()` automatically make it stop waiting for the monitor?

No. Entering an intrinsic monitor is not an interruptible wait like `ReentrantLock.lockInterruptibly()`. You must design to avoid wait cycles or use an appropriate primitive from the start.

**5.** Two threads always acquire A then B, but while holding B a callback tries to acquire lock C, while a third thread holds C and needs A. Is that enough to prove deadlock-freedom?

No. Lock C is part of the wait-for graph and must be included in the global order, or the callback must not be invoked inside the critical section.

**Remember:** When multiple locks are needed simultaneously, **define a stable total order over resources and follow it on every lock-acquisition path**. Proving that no wait edge goes against the order eliminates deadlocks caused by wait cycles among those locks, while still maintaining the locking needed to protect invariants.
