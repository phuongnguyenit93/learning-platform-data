# Lock Hierarchy and Avoiding Circular Lock Ordering in Java

## 1. Lesson Objectives

After this lesson, you will be able to:

- Explain **deadlock caused by circular lock ordering** and describe a thread **wait-for graph**.
- Understand **lock hierarchy** as a rule that enforces **a single global, stable order** when two or more locks must be held simultaneously.
- Prove why acquiring locks along the same ascending order eliminates wait cycles among those locks, while distinguishing **deadlock**, **starvation**, **livelock**, and **contention**.
- Write Java 17+ code using **synchronized** or **ReentrantLock**, ordering locks by unique ID/rank and always releasing them safely.
- Handle edge cases: same object, equal rank, dynamic lock sets, **System.identityHashCode()** collisions, callbacks, and resources outside the JVM.
- Recognize the limits of **tryLock()**, timeouts, interrupts, and retries: these mechanisms do not replace consistent lock ordering.
- Diagnose deadlocks using thread dumps and invariant tests rather than relying on **Thread.sleep()** or accidental log ordering.

This lesson covers **Java concurrency in the JDK** only, under the **Locks & Conditions** topic. Spring-specific locking and transaction management mechanisms belong to a separate chapter.

## 2. How Does Deadlock Happen?

**Deadlock** is a state in which entities wait on one another in such a way that none of them can make progress to release the resources needed by the others. With mutually exclusive locks in a single JVM, the most familiar example is **two threads acquiring two locks in opposite orders**.

Suppose there are **lockA** and **lockB**:

~~~text
Thread T1                            Thread T2
---------                            ---------
lock(lockA)                          lock(lockB)
  holds A                              holds B
  requests B -> waits for T2           requests A -> waits for T1

T1 holds A and waits for B  ----+
                                +---- wait cycle -> DEADLOCK
T2 holds B and waits for A  ----+
~~~

Both threads hold a resource that the other needs. Without a timeout, an appropriate cancellation/release policy, or another actor changing the condition, neither thread can finish its code block to release its lock.

With **synchronized**, a thread waiting to acquire an intrinsic monitor is typically observed as **Thread.State.BLOCKED**. With **ReentrantLock**, a thread may wait via a different mechanism and is not necessarily reported as BLOCKED; observing thread state alone is not enough to conclude whether a deadlock exists.

### The Four Classic Conditions (Coffman)

| Condition | Meaning |
| --- | --- |
| **Mutual exclusion** | At least one resource cannot be held by multiple threads simultaneously |
| **Hold and wait** | A thread holds one resource while waiting for another |
| **No preemption** | A resource cannot be forcibly taken away from the thread holding it |
| **Circular wait** | A cycle of threads exists, each waiting for a resource held by another |

A lock-based deadlock occurs only when the relevant conditions hold together. **Lock hierarchy aims to break the circular wait condition** by prohibiting threads from acquiring locks in a direction that forms a cycle.

**Do not assume deadlocks only involve two locks.** A cycle can involve T1→T2→T3→T1, many locks, and even combinations of locks with events such as **join()**, **Future.get()**, or waiting callbacks.

## 3. Lock Hierarchy: Enforcing a Global Lock Order

Assign the locks in use a shared **rank** or **level** with a clear total ordering:

~~~text
Rank 10: lockAccount
   ↓
Rank 20: lockLedger
   ↓
Rank 30: lockAudit

Allowed: 10 -> 20 -> 30; 10 -> 30; 20 -> 30.
Forbidden: 30 -> 20; 20 -> 10; 10 -> 30 -> 20.
~~~

A simple rule is:

> When a thread holds a lock of rank **r**, it may only acquire **another** lock with a rank **greater than r**. When exiting nested lock scopes, release the locks in reverse order.

If every code path follows this strictly, no wait cycle can exist among these locks alone:

- Every wait edge for acquiring an additional lock goes from a lower rank to a higher rank.
- A cycle would require a strictly increasing sequence returning to the starting rank, which is impossible.
- Therefore, there is no **circular wait** for the set of locks governed by the same rule.

This is a **correctness argument**, not a guarantee that the code will run fast, avoid starvation, or have no other forms of waiting. The rule must apply to **all acquisition paths for the relevant locks**, including helpers, callbacks, and code deep inside libraries controlled by the application.

### What Properties Should a Rank Have?

A practical rank assignment should ensure:

1. **Stability** throughout the lock's lifetime: never change the rank while a thread might be holding it.
2. **Comparability under the same rule** everywhere those locks are used.
3. **Distinguishability between different locks** when the rule requires a strict order; if two locks share the same rank, a proven *tie-break* mechanism is required.
4. **Independence from scheduling**: do not pick the first lock based on which thread happens to run faster.
5. **No bypasses**: manual lock acquisition or callbacks into other code must not violate the order.

For example, a business object ID can be suitable if it is assigned **uniquely and immutably** within the scope of the coordinated locks. Do not use mutable values or compare only by display name.

## 4. Wait-For Graphs and Cycles

A **wait-for graph** is a directed graph:

- **Vertices** are threads or tasks.
- An edge **Ti → Tj** means Ti is waiting for a resource held by Tj.
- A **wait cycle** in the context of exclusive resources is strong evidence of a deadlock.

Example:

~~~text
T1 --waits for lockB held by T2--> T2
T2 --waits for lockC held by T3--> T3
T3 --waits for lockA held by T1--> T1

=> T1 -> T2 -> T3 -> T1 : wait cycle.
~~~

A **lock-order graph**, by contrast, has locks as vertices: an edge **A → B** means that along some execution path, a thread acquires B while holding A. If the system exhibits both **A → B** and **B → A**, there is a risk of a wait cycle when those paths execute concurrently.

Not every cycle in a theoretical graph leads to a deadlock in a specific run; it indicates a potential interleaving that needs inspection. Conversely, a thread dump showing no cycle at the moment it was captured **does not prove** deadlock can never occur.

### Lock Order Is Different from Execution Order

A lock hierarchy does not force T1 to run before T2, nor does it force task A to finish before task B. It only enforces the **resource acquisition order** in code sections that need multiple locks.

For instance, a thread may acquire rank 20 when it holds no locks; it does not have to acquire rank 10 first. However, while holding rank 20, it **must not additionally acquire rank 10**.

## 5. Anti-Pattern: Two Threads Acquiring Locks in Opposite Orders

This is an **error-illustration snippet**, not a standalone program to run directly:

~~~java
Object lockA = new Object();
Object lockB = new Object();

// Thread T1:
synchronized (lockA) {
    synchronized (lockB) {
        // Work requiring both A and B.
    }
}

// Thread T2:
synchronized (lockB) {
    synchronized (lockA) {
        // Work requiring both B and A.
    }
}
~~~

If T1 holds A and T2 holds B, both inner lock acquisitions can wait on each other indefinitely. **Do not add Thread.sleep() to "fix" it**: sleep does not release a monitor. Switching to Thread.yield() neither releases a monitor nor establishes a cycle-free protocol.

Practice examples should not create an infinite deadlock in main because the program can hang. The examples below use **proper lock ordering** or fail-fast checks so they terminate with deterministic stdout.

## 6. Example 1: Ordering ReentrantLock by Rank

A helper acquires two locks in ascending rank order regardless of the argument order passed by the caller. Because two threads may request the same two resources in opposite directions, the helper must establish **the same actual order** before locking.

File **OrderedLocksDemo.java**:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public class OrderedLocksDemo {
    static final class RankedLock {
        final int rank;
        final ReentrantLock lock = new ReentrantLock();

        RankedLock(int rank) {
            this.rank = rank;
        }
    }

    static void withBoth(
            RankedLock a, RankedLock b, Runnable action) {

        if (a == b) {
            a.lock.lock();
            try {
                action.run();
            } finally {
                a.lock.unlock();
            }
            return;
        }

        if (a.rank == b.rank) {
            throw new IllegalArgumentException("ranks must be unique");
        }

        RankedLock first = a.rank < b.rank ? a : b;
        RankedLock second = a.rank < b.rank ? b : a;

        first.lock.lock();
        try {
            second.lock.lock();
            try {
                action.run();
            } finally {
                second.lock.unlock();
            }
        } finally {
            first.lock.unlock();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        RankedLock left = new RankedLock(10);
        RankedLock right = new RankedLock(20);
        int[] counter = {0};

        Runnable forward = () -> {
            for (int i = 0; i < 10_000; i++) {
                withBoth(left, right, () -> counter[0]++);
            }
        };
        Runnable backward = () -> {
            for (int i = 0; i < 10_000; i++) {
                withBoth(right, left, () -> counter[0]++);
            }
        };

        Thread a = new Thread(forward, "forward");
        Thread b = new Thread(backward, "backward");
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("counter = " + counter[0]);
    }
}
~~~

Run with Java 17+:

~~~bash
javac -encoding UTF-8 OrderedLocksDemo.java
java OrderedLocksDemo
~~~

Stdout:

~~~text
counter = 20000
~~~

**Why is this correct?**

1. **forward** passes (left, right) and **backward** passes (right, left), yet both lock **rank 10 before rank 20**.
2. Every **counter[0]++** executes while holding both locks; increments never overlap.
3. **finally** blocks at both levels guarantee that successfully acquired locks are released even if action throws an exception.
4. **join()** makes main wait for both threads to finish before reading counter, so stdout is deterministic.
5. If **a == b**, the helper locks only once. If two distinct locks have the same rank, the helper **rejects** the call instead of arbitrarily picking an inconsistent order.

In a real system, do not merely check for equal ranks per pair while letting other code assign duplicate ranks; define **rank assignment and resource ownership rules** at the design level.

## 7. Example 2: Bidirectional Transfers with synchronized by ID

This is a classic problem: transferring money from account A to B must keep both balances consistent. If each thread locks **the source account then the destination account**, two opposite-direction transfers easily produce A→B and B→A.

We enforce: **lock the account with the smaller ID first, then the larger ID**, regardless of transfer direction.

File **OrderedTransferDemo.java**:

~~~java
public class OrderedTransferDemo {
    static final class Account {
        final long id;
        final Object monitor = new Object();
        long balance;

        Account(long id, long balance) {
            this.id = id;
            this.balance = balance;
        }
    }

    static boolean transfer(
            Account from, Account to, long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        if (from == to) {
            return true;
        }
        if (from.id == to.id) {
            throw new IllegalArgumentException("ids must be unique");
        }

        Account first = from.id < to.id ? from : to;
        Account second = from.id < to.id ? to : from;

        synchronized (first.monitor) {
            synchronized (second.monitor) {
                if (from.balance < amount) {
                    return false;
                }

                from.balance -= amount;
                to.balance += amount;
                return true;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Account a = new Account(10, 1_000);
        Account b = new Account(20, 1_000);

        Thread ab = new Thread(() -> {
            for (int i = 0; i < 20_000; i++) {
                transfer(a, b, 1);
            }
        }, "a-to-b");

        Thread ba = new Thread(() -> {
            for (int i = 0; i < 20_000; i++) {
                transfer(b, a, 1);
            }
        }, "b-to-a");

        ab.start();
        ba.start();
        ab.join();
        ba.join();

        synchronized (a.monitor) {
            synchronized (b.monitor) {
                System.out.println("total = " + (a.balance + b.balance));
                System.out.println(
                    "nonnegative = "
                        + (a.balance >= 0 && b.balance >= 0)
                );
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 OrderedTransferDemo.java
java OrderedTransferDemo
~~~

Stdout:

~~~text
total = 2000
nonnegative = true
~~~

**Explanation:**

- Both threads request **bidirectional** transfers, yet every transfer locks **ID 10 then ID 20**.
- The balance check and updates to both accounts sit inside the same two-monitor critical section, so **the total balance is conserved** and no account goes negative from checked transfers.
- Some transfers may return **false** when the source account temporarily lacks funds; the exact success count and individual balances are **not deterministic** across schedules. The program intentionally prints only two invariants that hold on every normal run.
- The final print block locks the two accounts in the same order, avoiding an opposite-direction lock acquisition path in the observation code itself.
- **IDs must be unique and immutable** for all distinct Accounts managed by this rule. In the demo, IDs 10 and 20 satisfy this condition.

**Limitation:** This models state within a single JVM only. Real money transfers require transactions, durable balances/ledgers, overflow checks, idempotency, and error-handling policies. Java monitors cannot protect data across multiple processes or application instances.

## 8. Same Object, Equal Rank, and Tie-Break Rules

### Two References Pointing to the Same Lock

If **a == b**, a reentrant lock can be acquired multiple times by the same thread, but the code must release it the exact same number of times. For a pair-locking helper, the clearest approach is usually to **detect the same object and lock it once**.

If one object plays two roles in the same operation, define the operation's semantics rather than merely changing lock order. For example, transferring from an account to itself may be a no-op, but that is a **business rule**, not something a Java Lock decides on its own.

### Two Different Objects with the Same Rank

If two different locks share the same rank, you cannot simply say "lock the smaller one first" without defining a tie-break. Two threads could pick different orders depending on argument position.

Solutions:

- **Assign unique IDs** to every lock within the same comparison domain.
- Use a **stable total comparator** over immutable attributes (for example, ID + resource type, if that pair is truly unique).
- Where duplicate comparison keys are unavoidable, use **a shared tie-breaking lock (*tie lock*)** for collisions, or redesign the rank assignment scheme.

Never "just pick by parameter order" when ranks are equal, because that reproduces the exact opposite-ordering bug.

### Why identityHashCode Is Not Always Enough

**System.identityHashCode(object)** returns an identity-related hash value, **with no guarantee against collisions** between two distinct objects. If you compare hashes to order locks, you must handle equal-hash collisions.

The following snippet **illustrates the tie-lock solution**, not a complete application:

~~~java
private static final Object TIE_LOCK = new Object();

static void withPair(Object a, Object b, Runnable action) {
    if (a == b) {
        synchronized (a) {
            action.run();
        }
        return;
    }

    int ha = System.identityHashCode(a);
    int hb = System.identityHashCode(b);

    if (ha < hb) {
        synchronized (a) {
            synchronized (b) {
                action.run();
            }
        }
    } else if (ha > hb) {
        synchronized (b) {
            synchronized (a) {
                action.run();
            }
        }
    } else {
        synchronized (TIE_LOCK) {
            synchronized (a) {
                synchronized (b) {
                    action.run();
                }
            }
        }
    }
}
~~~

Place this snippet inside a class to compile; action represents an operation needing both monitors. **TIE_LOCK** must be **a single shared object** for the entire protocol. When hashes collide, only one thread at a time can enter the tie path, so two calls with reversed arguments cannot acquire the two monitors in opposite orders concurrently. When using this approach, apply it consistently across **all acquisition paths for the involved locks**; if other code holds a or b and then requests TIE_LOCK, a wait cycle can still occur.

For new designs, a unique, immutable global ID is usually easier to reason about than relying on identity hashes and a tie lock.

## 9. More Than Two Locks

With three or more locks, the principle stays the same: **collect the lock list, deduplicate references, sort by the global order, acquire from lowest to highest, and release in reverse**.

Example pseudocode:

~~~text
input: list of resources to lock
1. Verify IDs/ranks are immutable and no two distinct resources share the same rank.
2. Deduplicate references or merge requests for the same resource.
3. Sort in ascending rank order.
4. Acquire all locks sequentially.
5. Once all are held, check and mutate business invariants.
6. Release only the locks actually acquired, in reverse order.
~~~

When using **ReentrantLock**, use nested try/finally blocks or explicitly record successfully acquired locks in a stack structure, releasing them in finally. If acquiring the third lock fails or is interrupted, the first two locks **that the thread actually holds** must be released.

With **synchronized**, there is no arbitrary runtime list enter/exit API without structuring nested blocks or a recursive helper. If you write a recursive helper, ensure it uses the exact same order as every other entry path and that no callback acquires a lower-ranked lock.

### When the Lock List Changes Dynamically

A thread that already holds rank 50 and then discovers it needs rank 10 **must not immediately acquire rank 10**. Depending on the contract, the options are:

- Precompute the resource set upfront, then acquire in the proper order.
- Release the held locks, rebuild and sort the list, and retry. **Business conditions must be re-checked** because state may have changed after releasing.
- Design the API so callers cannot request a lower-ranked lock while holding a higher-ranked one.
- Use an ownership or message-passing model if transactions require such dynamic resource sets that a hierarchy becomes unmanageable.

Do not treat releasing and re-acquiring locks as a gap-free transaction. **Releasing a lock** allows other threads to update data; any snapshot read earlier may now be stale.

## 10. Example 3: Fail-Fast Hierarchy Checking During Development

In large applications, a documented lock hierarchy can be broken when new code calls another helper. You can build a **runtime checker** to catch out-of-order lock acquisitions immediately during tests.

The following example intentionally enforces **strictly increasing ranks** for managed locks; the checker **disallows re-acquiring the same rank**, even though plain ReentrantLock supports reentrancy. This is a policy of the checker to make violations easy to spot, not a limitation of ReentrantLock.

File **LockRankCheckerDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.concurrent.locks.ReentrantLock;

public class LockRankCheckerDemo {
    private static final ThreadLocal<Deque<Integer>> HELD =
            ThreadLocal.withInitial(ArrayDeque::new);

    static final class RankedLock {
        private final int rank;
        private final ReentrantLock lock = new ReentrantLock();

        RankedLock(int rank) {
            this.rank = rank;
        }

        void acquire() {
            Deque<Integer> held = HELD.get();
            if (!held.isEmpty() && rank <= held.peek()) {
                throw new IllegalStateException("lock order violation");
            }

            lock.lock();
            held.push(rank);
        }

        void release() {
            Deque<Integer> held = HELD.get();

            if (!lock.isHeldByCurrentThread()
                    || held.isEmpty()
                    || held.peek() != rank) {
                throw new IllegalStateException("invalid unlock order");
            }

            lock.unlock();
            held.pop();
            if (held.isEmpty()) {
                HELD.remove();
            }
        }
    }

    public static void main(String[] args) {
        RankedLock low = new RankedLock(10);
        RankedLock high = new RankedLock(20);

        low.acquire();
        try {
            high.acquire();
            try {
                System.out.println("ascending = allowed");
            } finally {
                high.release();
            }
        } finally {
            low.release();
        }

        high.acquire();
        try {
            try {
                low.acquire();
            } catch (IllegalStateException ex) {
                System.out.println("descending = rejected");
            }
        } finally {
            high.release();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 LockRankCheckerDemo.java
java LockRankCheckerDemo
~~~

Stdout:

~~~text
ascending = allowed
descending = rejected
~~~

**Key points to understand:**

- **ThreadLocal<Deque<Integer>>** stores the stack of ranks acquired by the **calling thread** through the checker.
- On each acquire, the new rank must be **greater than** the rank at the top of the stack; otherwise, an exception is thrown **before attempting to lock**, avoiding a wait cycle in the demo itself.
- Each release requires the correct owner and LIFO order; **finally** keeps lock ownership balanced.
- After releasing the last lock, HELD.remove() avoids retaining unnecessary ThreadLocal state on threads that may be pooled and reused.
- This demo illustrates a simple checker for **static ranks and a closed API**. It has no visibility into locks acquired directly via synchronized, other ReentrantLocks, external callbacks, or cross-process resources; do not treat it as a complete detector for all deadlocks.

If an application needs a thread to re-acquire the **same** lock, a real checker must distinguish **reentrant same-object** from **different-object same-rank**, tracking object identity and hold counts appropriately. Do not simply drop the equal-rank check if doing so would allow two distinct objects of the same rank to be locked in arbitrary order.

## 11. tryLock() and Timeouts: An Alternative to Waiting Forever

**ReentrantLock.tryLock()** attempts to acquire the lock immediately and returns a boolean. **tryLock(timeout, TimeUnit)** can wait up to a bounded duration and throws InterruptedException if interrupted. If the second lock cannot be acquired, the caller can **release the first lock, wait an appropriate backoff, and retry**.

Mandatory rules for "all-or-none acquisition":

1. Track **which locks were actually acquired**.
2. Perform no business side effects until all required locks are held.
3. If any lock cannot be acquired, release **all acquired locks** in finally.
4. On retry, re-check all conditions because state may have changed while locks were released.
5. Enforce retry limits, deadlines, or cancellation paths to avoid infinite retries under contention.

### Example 4: Failing to Acquire the Second Lock and Safe Cleanup

File **TryLockCleanupDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.ReentrantLock;

public class TryLockCleanupDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock first = new ReentrantLock();
        ReentrantLock second = new ReentrantLock();
        CountDownLatch finished = new CountDownLatch(1);

        second.lock(); // Main intentionally holds second while worker tries to acquire it.
        try {
            Thread worker = new Thread(() -> {
                first.lock();
                try {
                    boolean gotSecond = second.tryLock();
                    try {
                        System.out.println(
                            "got second = " + gotSecond
                        );
                    } finally {
                        if (gotSecond) {
                            second.unlock();
                        }
                    }
                } finally {
                    first.unlock(); // Even when tryLock fails.
                    finished.countDown();
                }
            }, "worker");

            worker.start();
            finished.await();
            worker.join();
            System.out.println("first locked = " + first.isLocked());
        } finally {
            second.unlock();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 TryLockCleanupDemo.java
java TryLockCleanupDemo
~~~

Stdout:

~~~text
got second = false
first locked = false
~~~

**Explanation:** Main holds second until after the worker finishes, so the worker's tryLock(second) must return false. The worker **does not unlock second** because it does not own it; it still releases first in finally. Main waits on the completion latch and joins the worker before reading isLocked() after first has been released, giving deterministic stdout.

This example demonstrates cleanup on failed acquisition, **not a recommendation to replace all lock ordering with tryLock**. In an application where multiple workers retry concurrently, if they all grab their first lock and all fail on the second, they can repeatedly release and re-contend without anyone completing (**livelock**). Retries need proper backoff, limits, and cancellation; **a lock hierarchy is still usually easier to prove correct**.

### Does Interrupting Automatically Break a Deadlock?

- A thread waiting on a **synchronized monitor** cannot use interrupt to acquire the lock or force the owner to release the monitor.
- **ReentrantLock.lockInterruptibly()** lets a thread abandon *waiting for a lock* when interrupted, but it does not automatically release locks that the thread **already holds**.
- **tryLock(timeout, unit)** prevents the caller from waiting forever on a single acquisition; the caller must still actively clean up previously acquired locks.
- **Thread.interrupt()** is a cooperative request, not a command that forcibly rolls back or unlocks another thread.

Therefore, **preventing deadlock through consistent lock ordering** is the primary approach when the problem allows it. Timeouts and interrupts are complementary tools for progress control and safe cancellation.

## 12. Lock Ordering with synchronized, ReentrantLock, and Condition

### synchronized

When using intrinsic monitors, nested synchronized blocks make the acquisition order explicit:

~~~java
synchronized (lowerRankLock) {
    synchronized (higherRankLock) {
        // Critical section requiring both.
    }
}
~~~

This is an illustrative snippet inside a method; both variables must be shared lock object references with ranks assigned by contract. Upon exiting the scope, Java releases the corresponding monitor even if an exception is thrown.

There is no direct API to put a timeout on **monitor entry** like tryLock(timeout). That makes avoiding unordered nested lock chains even more important.

### ReentrantLock

Use two levels of try/finally:

~~~java
low.lock();
try {
    high.lock();
    try {
        update();
    } finally {
        high.unlock();
    }
} finally {
    low.unlock();
}
~~~

This is an illustrative snippet; low/high are ReentrantLocks with established ranks, and update() is the protected operation. If high.lock() throws an unexpected error before acquiring, the outer finally still releases low. In the normal case, the thread acquires both in a stable order and releases them in reverse.

### Condition and Temporarily Releasing a Lock

**Condition.await()** requires the current thread to hold the corresponding ReentrantLock; while waiting, it **releases only the lock associated with that condition**, and re-acquires it before returning per contract. It **does not release any other locks** that the thread is holding.

If a thread holds **low**, then **high**, and then calls await() on **high**'s condition, it may continue holding low while waiting. This can prevent another thread that needs low from performing the action that makes high's condition true. Thus, a simple rank rule **does not replace analyzing await/signal, join, or callback protocols**.

Prefer designs that avoid holding multiple locks during long condition waits, or explicitly prove that the signal can be delivered without needing the held locks.

## 13. Deadlock, Starvation, Livelock, and Contention Are Not the Same

| Phenomenon | Description | How far does lock hierarchy help? |
| --- | --- | --- |
| **Deadlock** | Threads form a wait cycle and cannot proceed under the current protocol | Prevents wait cycles among rank-compliant locks; does not prevent all deadlocks from other resources |
| **Starvation** | A thread is repeatedly denied CPU/locks/resources while other threads make progress | Does not guarantee fairness or bounded wait times |
| **Livelock** | Threads continuously react, retrying/releasing locks without completing useful work | Does not prevent poorly designed retry policies |
| **Contention** | Multiple threads want the same lock so some must wait | Still occurs even when lock ordering is correct |

A deadlock-free program can still be slow due to lock contention, starvation, or holding locks for too long. With ReentrantLock, **fair=true** enforces certain queuing rules but does not guarantee absolute CPU scheduling fairness; an untimed **tryLock()** can still barge ahead even on a fair lock.

Never write a test asserting "it didn't hang for one second, so there is no deadlock." A schedule that triggers a cycle might simply not have occurred in that run. You must examine **all possible lock orders** and reason from program structure.

## 14. Lock Hierarchy Across Helpers, Callbacks, and Libraries

One common source of hierarchy violations is an apparently "harmless" method that internally acquires another lock:

~~~text
ServiceA.process():
  holds lock(rank 30)
  calls ServiceB.validate()
    -> ServiceB acquires lock(rank 10)
       => VIOLATION 30 -> 10
~~~

Sometimes a callback or overridden method running under one lock calls back into a class holding another lock, creating a **lock inversion** that is hard to spot at the direct call site. Practice the following:

- Document **lock ranks** explicitly in the APIs of classes that hold locks.
- Avoid invoking callbacks, hooks, custom loggers, plugin code, or external I/O while holding a lock if you cannot control which locks they acquire.
- Minimize **nested locks** by reorganizing data ownership or taking immutable snapshots before calling external code.
- For operations needing multiple resources, collect the **full lock set** upfront and coordinate it through a single helper.
- Use a checker in tests to catch rank violations; do not rely solely on a stress test "passing."

**There is no automatic lock ordering across Java libraries.** A newly created ReentrantLock does not know "my rank is 10"; the JVM does not automatically detect out-of-order usage. Ranks only work when every usage path obeys the contract you design.

### Never Mutate a Rank After the Lock Is Published

If a rank is derived from a balance, task priority, creation timestamp, or mutable field, two threads can sort the same pair of locks differently at different times. A lock's rank should be **immutable**; if business structure must change, use a safe reconfiguration protocol.

### Locking by ID Does Not Protect Data Across Multiple JVMs

Two JVMs have two separate lock objects even when they represent the same account ID. Lock ordering on Java objects in JVM A **does not exclude** updates from JVM B. For databases, distributed storage, or remote resources, use the storage layer's transactions, optimistic concurrency, or distributed locks. A local lock hierarchy still helps prevent deadlocks **within** each JVM, but it does not replace inter-process synchronization.

## 15. Designing APIs So Locks Cannot Be Acquired Out of Order

A good API reduces the chance that callers must remember the order themselves:

- Encapsulate locks as **private final** fields; avoid exposing a ReentrantLock directly for arbitrary external acquisition.
- Provide transactional methods like **transfer(from, to, amount)** or **withLocks(resources, action)** that sort IDs, acquire locks, run the action, and release.
- If nested locks are allowed, make the hierarchy and each layer's methods explicit.
- Prefer immutable objects, copy-on-write, or message passing where shared mutable state can be avoided.
- Separate the **all-locks-acquired** state from the **attempting-to-acquire** state so side effects do not happen prematurely.

If an operation must lock a list of objects that other threads can modify, taking a snapshot of the list is **not enough** if objects can be added or removed and an invariant spans the whole set. You need a protocol protecting **the membership list itself** (such as a higher-level lock, or versioning with re-validation under lock). Lock ordering is part of the solution, not a complete fix for dynamic topology consistency.

## 16. Diagnosing Deadlocks in Java

When suspecting a deadlock involving monitors or ownable synchronizers:

1. **Capture a thread dump** when the system appears stuck. Use JDK tools such as **jcmd <pid> Thread.print** or **jstack <pid>** where permitted.
2. Identify which threads hold which monitors/locks and which locks they are waiting for; compare stack traces containing nested synchronized or ReentrantLock acquisitions.
3. Draw the **wait-for graph**: thread A waits for a resource held by thread B, B waits for C, C waits for A.
4. Trace **which call path** introduced the lock edge that goes against the hierarchy.
5. Fix the design: unify the acquisition order and API; do not merely increase timeouts or add logs/sleeps.
6. Add a regression test with reversed-argument pairs (A→B and B→A), asserting invariants after all workers join.

**ThreadMXBean** provides methods such as **findDeadlockedThreads()** to detect deadlock cycles on object monitors or ownable synchronizers visible to the JVM. A null result does not prove the program is deadlock-free at other times or on resources outside the JVM's visibility. A thread dump may also lack visibility into external resources such as database locks.

### Testing Without Creating Intentional Deadlocks

A test can launch multiple threads calling the lock-ordering helper, then **join with a timeout** and assert invariants. The timeout detects when a test may be hanging; it does not fix the workers. If a test times out, capture stack/lock info for diagnosis and ensure the test does not leave non-daemon threads hung forever blocking the test suite.

The runnable examples in this lesson avoid deadlocking programs with no exit path. To study faulty schedules, use isolated environments/tests with safe shutdown mechanisms; never put infinite-deadlock patterns in the application's default execution path.

## 17. Common Mistakes

| Design Mistake | Risk | Fix |
| --- | --- | --- |
| T1 locks A→B, T2 locks B→A | Two-lock wait cycle | Enforce A→B on all paths |
| Ordering by input parameter position | Reversed calls lock in opposite order | Order by immutable ID/rank, not parameter order |
| Rank mutates at runtime | Threads may observe different orders | Assign stable ranks by contract |
| Different locks share a rank with no tie-break | No total order | Use unique IDs or a tie-lock protocol |
| Assuming identityHashCode never collides | Can fall back to nondeterministic order | Design a safe tie-break |
| Helper method acquires a lower-ranked lock under a higher one | Hidden hierarchy violation | Encapsulate APIs and audit the full call graph |
| Failing to release held locks when a second tryLock fails | Holds resources, raises deadlock risk | Release all acquired locks in finally |
| Running business logic before all locks are held | Partial side effects when acquisition fails | Execute only after acquiring all locks and checking invariants |
| Waiting on join/await while holding a lock others need | Wait cycle outside lock contention | Analyze dependencies; avoid holding locks across waits |
| Using sleep/yield to "break" a deadlock | Does not release locks or ensure progress | Fix lock order / protocol |
| Catching InterruptedException, ignoring it, and keeping locks | No clean cancellation/cleanup path | Handle interrupts and release safely in finally |
| Seeing getState() != BLOCKED and concluding no deadlock | ReentrantLock uses different wait mechanics | Inspect lock owners, wait-for graph, and thread dumps |
| Using a single-JVM lock hierarchy to protect a multi-instance DB | No inter-process mutual exclusion | Synchronize at the shared data store |
| Relying on a single test run not hanging | Cycle-inducing schedule may not have occurred | Prove lock order + reversed-direction tests + diagnostics |

## 18. Code Review Checklist

**Design:**

- [ ] Every lock has a clear, stable **role and rank/ID**, distinguishable where needed.
- [ ] All nested acquisitions follow **one ascending direction**, with no helper/callback silently going backward.
- [ ] Same-object references are handled explicitly; distinct objects with equal ranks have a proper tie-break.
- [ ] Steps mutating multiple shared fields sit inside a critical section protecting the **entire invariant**.
- [ ] No lower-ranked lock is held while waiting on an event that can only happen when another thread acquires that lock.

**Implementation:**

- [ ] For ReentrantLock, every successful acquire has a matching **finally unlock** on the same thread, the exact number of times.
- [ ] On failed tryLock/interrupt, all held locks are released and no business side effects happen prematurely.
- [ ] When releasing and retrying, state is re-read and retries/backoff are bounded as required.
- [ ] No I/O, callbacks, or long sleeps while holding a monitor unless strictly required for the invariant.
- [ ] Neither rank nor lock object identity is mutated after publication to other threads.

**Testing & Operations:**

- [ ] Bidirectional tests (A→B and B→A) verify progress and invariants.
- [ ] Thread dump / ThreadMXBean diagnostics are available if threads block.
- [ ] Error handling, timeouts, and cleanup are explicit rather than relying on lucky scheduling.
- [ ] The **single-JVM** scope of Java locks and boundaries with DB/external resources are clearly documented.

## 19. Self-Check

**Q1.** Why can T1 acquiring A then B and T2 acquiring B then A deadlock?  
**Answer:** Each thread can hold one lock while waiting for the lock held by the other. That is a circular wait.

**Q2.** Which deadlock condition does an ascending-rank lock acquisition rule eliminate?  
**Answer:** It eliminates **circular wait** among the set of locks properly governed by that rule.

**Q3.** If both transfer(A,B) and transfer(B,A) lock the account with the smaller ID first, can an A↔B deadlock still occur?  
**Answer:** Not from that pair of monitors in opposite directions, provided all paths acquiring those monitors follow the same order. Other resources still require separate analysis.

**Q4.** Why shouldn't System.identityHashCode be used as a unique rank by default?  
**Answer:** Two distinct objects can still have the same identity hash. A stable tie-break is required.

**Q5.** If a thread already holds rank 30 and discovers it needs rank 10, what should it do?  
**Answer:** Do not acquire rank 10 under rank 30. Release the held lock, determine the full resource set, sort, acquire, and re-check state; or redesign the API.

**Q6.** tryLock(second) returns false while holding first. Can the code proceed to update data requiring both locks?  
**Answer:** No. It must release first and handle failure/retry per protocol, unless the business logic has a proven fallback that does not need second.

**Q7.** Does a fair ReentrantLock replace a lock hierarchy?  
**Answer:** No. Fairness does not break wait cycles across different locks.

**Q8.** Does Condition.await() release all locks held by the thread?  
**Answer:** No. Per contract, it releases only the lock associated with that Condition; other locks may remain held while waiting.

**Q9.** Why can a deadlock-free system still be slow or fail to make progress?  
**Answer:** Due to contention, starvation, livelock, I/O, or other waiting policies; avoiding wait cycles does not guarantee bounded progress.

**Q10.** Why doesn't a Java ReentrantLock across two JVMs protect the same account in a database?  
**Answer:** The two processes own separate lock objects. Synchronization is needed at the shared data store layer.

## 20. Summary

**Lock hierarchy** prevents deadlocks by enforcing **a single global, stable order when acquiring multiple locks**: sort by rank/ID, acquire from low to high, release in reverse, and handle duplicate objects and tie-breaks explicitly. It eliminates wait cycles caused by **opposing lock orders**, but it does not guarantee fairness, eliminate contention, or by itself resolve condition waits, callbacks, I/O, or cross-JVM resources.

In Java, encapsulate multi-lock acquisitions behind order-enforcing APIs, use **finally** to release every actually acquired lock, re-check invariants on retries, and verify with reversed-direction tests and thread dumps when needed. The right approach starts from **lock dependency graphs and data invariants**, not from sleep, yield, or hoping the scheduler picks a lucky interleaving.
