# synchronized method vs. synchronized block in Java

## 1. Objectives and Scope

The two code snippets below can use the **same monitor lock** while providing different levels of control:

~~~java
public synchronized void increment() {
    count++;
}

public void increment() {
    synchronized (this) {
        count++;
    }
}
~~~

When both are **instance methods** and the `this` object is the same, their bodies are protected by the same monitor. A `synchronized method` locks the receiver object's monitor for the **entire method body**; a `synchronized block` allows choosing a monitor object and narrowing the protected code region. If `this` is replaced with a different lock object, they no longer automatically share the same monitor.

After this lesson, you will be able to:
- Accurately describe the syntax, lock object, scope, and semantics of `synchronized` on instance methods, static methods, and code blocks.
- Explain mutual exclusion, reentrancy, visibility, and happens-before rules when acquiring/releasing the same monitor.
- Analyze the difference between locking an entire method and locking only a critical section; choose lock granularity while still protecting the full invariant.
- Recognize the pitfall of synchronizing individual getters/setters while leaving check-then-act or read-modify-write sequences exposed.
- Use a `private final Object lock`, determine the effect of `synchronized(this)` and `synchronized(MyClass.class)`, and avoid locking on the wrong object.
- Run Java 17+ examples with consistent results and know when to use `Lock` or other concurrency utilities.

This lesson covers only **Java SE and JVM concurrency**, with no framework dependencies.

## 2. What Does `synchronized` Actually Protect?

Every object in Java has an **intrinsic lock**, also known as a **monitor**. When a thread executes a `synchronized` section associated with that object, the thread must acquire the monitor before entering the critical section. If another thread currently holds the same monitor, the incoming thread must wait until it can acquire the lock.

~~~text
             Monitor of object sharedCounter
                           │
Thread A ─── lock(sharedCounter) ──▶ critical section ──▶ unlock
                           │                  │
Thread B ───── must wait ──┴──────────────────┘
                                            └─▶ lock, then enter
~~~

**Mutual exclusion applies only to code sections synchronized on the exact same monitor.** Not all code accessing an object is automatically locked. Another regular method can still run while a thread holds the monitor if that method does not attempt to acquire that monitor.

Example:

~~~java
class Counter {
    private int count;

    synchronized void increment() { // uses this's monitor
        count++;
    }

    int readUnsafe() {               // does NOT acquire monitor
        return count;
    }
}
~~~

Two threads calling `increment()` and `readUnsafe()` concurrently are **not guaranteed** that `readUnsafe` will observe consistent values according to `increment`'s synchronization contract. A `private` field does not automatically make read paths safe. If multiple threads need to read/write a changing value, all access paths must follow the same protocol: for example, `synchronized int get()` on the same monitor, or a design using an atomic API.

`synchronized` is also important for the **Java Memory Model (JMM)**:
- An **unlock** on monitor `m` synchronizes-with every **subsequent lock** on the same monitor `m` in synchronization order.
- From that relationship and program order, writes protected before the unlock can be properly observed by code that acquires the same lock afterward.
- This relationship guarantees visibility and ordering via happens-before; there is no need to explain it by assuming "every value always resides directly in RAM."

`synchronized` does not make the operating system run threads in a specific order, does not provide fairness by default, does not create timeouts, and does not guarantee that a task will finish within a fixed time.

## 3. synchronized instance method: Locking the Entire Method Body

Syntax:

~~~java
class Balance {
    private int cents;

    public synchronized void add(int amount) {
        cents += amount;
    }

    public synchronized int getCents() {
        return cents;
    }
}
~~~

When calling `balance.add(100)`, the thread must acquire the **monitor of the `balance` instance itself** before executing the body. In terms of the lock and critical section scope, this is equivalent to:

~~~java
public void add(int amount) {
    synchronized (this) {
        cents += amount;
    }
}
~~~

All update and read paths protecting the `cents` field use the same instance's monitor. Multiple threads calling `add` or `getCents` on the same object cannot be inside these critical sections at the same time.

### Characteristics

- The `synchronized` method modifier is declared only on a **method**: locking applies to the entire execution of the method body, not selectively line by line.
- For an instance method, the lock object is `this` of the receiver in the call. The same class with **different instances** has different monitors.
- One synchronized method does not automatically make **all other methods** of the class synchronized.
- Execution entering the method must acquire the lock before running the body; exiting the method normally or via an exception releases the monitor.
- `synchronized` is not part of the method signature for overload resolution; when overriding, the overriding method is **not required to inherit** the `synchronized` modifier. You must check the actual implementation being called.
- A synchronized instance method is not a class-wide lock: it does not prevent methods on other instances or static methods from running concurrently by default.

### Two Instances, Two Monitors

~~~java
Counter first = new Counter();
Counter second = new Counter();

// One thread can lock first while another thread locks second.
~~~

If the invariant resides within each individual instance, that may be desirable. However, if both instances actually modify the same **static mutable field**, locking each instance's monitor is not enough to protect the static field. In that case, a shared lock or atomic protocol scoped appropriately to the shared state is required.

## 4. synchronized block: Choosing the Monitor and Limiting the Locked Region

Syntax:

~~~java
synchronized (lockExpression) {
    // actions protected by the lockExpression monitor
}
~~~

`lockExpression` must have a reference type; the expression is evaluated to obtain **a monitor object** before entering the block. If the result is `null`, the runtime throws `NullPointerException`; there is no monitor to acquire. A block can appear inside a method, constructor, static initializer, or another valid code block.

Example:

~~~java
class Inventory {
    private final Object quantityLock = new Object();
    private int quantity;

    void add(int delta) {
        if (delta <= 0) {
            throw new IllegalArgumentException("delta must be positive");
        }

        synchronized (quantityLock) {
            quantity += delta;
        }
    }

    int current() {
        synchronized (quantityLock) {
            return quantity;
        }
    }
}
~~~

This code protects the `quantity` field with `private final Object quantityLock`. The parameter check `delta <= 0` does not depend on shared mutable state, so it can be done **before acquiring the lock**; the critical section only wraps the modification of `quantity`.

The biggest difference from a synchronized method is the ability to **choose a monitor other than `this`**. If two threads call `add()` on the same `Inventory`, they contend for `quantityLock`. If external code executes `synchronized(inventory)`, it does **not** lock `quantityLock`, so it does not directly block `add()`.

### Why Is a `private final` Lock Usually Preferred?

- **private:** external callers do not know about it and cannot accidentally acquire the same monitor and hold it too long.
- **final:** all calls use the same fixed lock object; the lock reference cannot change between calls.
- **A dedicated new Object for locking:** avoids tying the lock to a `String` literal, a cached `Integer` object, a shared `Class` object, or a mutable parameter that callers might also lock on.

`private final` does not make all state thread-safe; it only helps **keep the monitor identity stable**. Every method reading or writing the same invariant must still obey the same lock or a compatible protocol.

### When Is Locking the Entire Method Too Broad?

~~~java
class ReportService {
    private final Object stateLock = new Object();
    private int completed;

    void process(String input) {
        String formatted = input.strip().toUpperCase(java.util.Locale.ROOT);
        // Computation that does not touch shared mutable state: no need to hold the lock.

        synchronized (stateLock) {
            completed++;
        }

        System.out.println(formatted);
        // Printing to console has its own side effects; no need to hold stateLock.
    }

    int completed() {
        synchronized (stateLock) {
            return completed;
        }
    }
}
~~~

Here, only incrementing/reading `completed` needs the same lock. If `process` were changed to `synchronized void process(...)` on `this` while other update paths still used `stateLock`, that would create **two different locking protocols** and could fail to protect the invariant properly. When refactoring, do not just change syntax: inspect every access path to the state.

Do not hold a lock across I/O, sleep, callbacks, or long-running work **when unnecessary**: holding a monitor for a long time forces other threads to wait. However, do not move **half of an invariant** outside the lock just to optimize. Safety and atomicity of the business operation come first.

## 5. Direct Comparison Table

| Criterion | synchronized instance method | synchronized block |
|---|---|---|
| Syntax | `synchronized void method() { ... }` | `synchronized (lock) { ... }` |
| Default monitor | Receiver `this` | The object evaluated from the `lock` expression |
| Protection scope | Entire method body | Only the statements inside the block |
| Can choose a dedicated private lock? | No, via the instance `synchronized` modifier; use a block for a different lock | Yes, via `synchronized (privateLock)` |
| Where used | Method declaration | Inside a method body, constructor, initializer, or valid block |
| Works with `static`? | Yes: `static synchronized` acquires the `Class` monitor | Yes: `synchronized (SomeClass.class)` or another shared lock |
| When an exception exits the critical section | JVM releases the monitor | JVM releases the monitor |
| Reentrant | Yes | Yes |
| Visibility / happens-before | Based on the monitor the method acquires/releases | Based on the monitor the block acquires/releases |
| Performance | Depends on contention, work inside, and JIT/JVM | Depends on contention, work inside, monitor, and hold time |
| Readability | Concise when the entire method is one critical section | Clear boundaries when only one segment needs protection |

Do not conclude that a `synchronized block` is always faster than a `synchronized method`. If a block locks `this` and wraps the entire method, the semantics are equivalent; HotSpot/JIT performs many optimizations, and actual performance must be measured on your workload. The advantage of a block is clearer **design of lock scope and lock identity**, not a syntax that automatically creates a "faster lock."

## 6. Which Monitor Does a `static synchronized` Method Use?

Given:

~~~java
class GlobalCounter {
    private static int total;

    static synchronized void increment() {
        total++;
    }

    static synchronized int get() {
        return total;
    }
}
~~~

The acquired lock is the **`Class` object** corresponding to `GlobalCounter.class` (the `java.lang.Class` object representing the class within the relevant class loader context). In terms of monitor and locked region, it can be written equivalently as:

~~~java
static void increment() {
    synchronized (GlobalCounter.class) {
        total++;
    }
}
~~~

This is **different** from `synchronized(this)` in an instance method:

~~~text
new GlobalCounter()             ──▶ instance monitor X
new GlobalCounter()             ──▶ instance monitor Y
GlobalCounter.class             ──▶ class monitor Z

static synchronized method      ──▶ locks Z
instance synchronized method    ──▶ locks X or Y (depending on receiver)
~~~

Therefore:
- Two `static synchronized` calls on the **same class monitor** are mutually exclusive.
- A `static synchronized` method and an instance `synchronized` method on an instance **do not automatically exclude each other**.
- If the same static field is modified from an instance method locking `this` and a static method locking `Class`, a race condition can still occur.
- Two `Class` objects with the "same class name" defined by **two different class loaders** are not necessarily the same object; do not use a class lock as a synchronization mechanism across processes or class loaders.

You can use a `private static final Object LOCK = new Object();` and blocks locking `LOCK` instead of locking the `Class` object when you want to completely separate the business lock from a monitor that external code might use.

## 7. Standalone Example 1: Same Monitor, Both Method and Block Work Correctly

This program runs on **Java 17+**, having two threads increment a counter instance: one thread uses a synchronized method, and the other uses a `synchronized(this)` block. Both use the monitor of the **same object**. The second part repeats this for a `static synchronized` method and `synchronized(Class.class)`.

Save the file **SynchronizedFormsDemo.java**:

~~~java
public class SynchronizedFormsDemo {
    static final class Counter {
        private int value;
        private static int global;

        synchronized void incrementMethod() {
            value++;
        }

        void incrementBlock() {
            synchronized (this) {
                value++;
            }
        }

        synchronized int value() {
            return value;
        }

        static synchronized void incrementStaticMethod() {
            global++;
        }

        static void incrementStaticBlock() {
            synchronized (Counter.class) {
                global++;
            }
        }

        static synchronized int global() {
            return global;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();

        Thread first = new Thread(() -> {
            for (int i = 0; i < 100_000; i++) {
                counter.incrementMethod();
            }
        }, "method-worker");

        Thread second = new Thread(() -> {
            for (int i = 0; i < 100_000; i++) {
                counter.incrementBlock();
            }
        }, "block-worker");

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("instance=" + counter.value());

        Thread third = new Thread(() -> {
            for (int i = 0; i < 100_000; i++) {
                Counter.incrementStaticMethod();
            }
        }, "static-method-worker");

        Thread fourth = new Thread(() -> {
            for (int i = 0; i < 100_000; i++) {
                Counter.incrementStaticBlock();
            }
        }, "static-block-worker");

        third.start();
        fourth.start();
        third.join();
        fourth.join();

        System.out.println("static=" + Counter.global());
    }
}
~~~

Compile and run:

~~~bash
javac SynchronizedFormsDemo.java
java SynchronizedFormsDemo
~~~

Exact stdout, assuming no other thread modifies `Counter` in the same program:

~~~text
instance=200000
static=200000
~~~

**Explanation:**
1. `first` and `second` share the `counter` instance. `incrementMethod()` acquires `counter`'s monitor; `incrementBlock()` uses `synchronized (this)` with `this == counter`.
2. Each `value++` step is fully protected; the threads can interleave **between increments**, but cannot execute the critical section on `counter` at the same time.
3. `join()` waits for all 200,000 increments before `main` reads the result. The `value()` method is also synchronized on the corresponding monitor.
4. `incrementStaticMethod()` and `incrementStaticBlock()` both lock `Counter.class`; after both threads finish, `global()` reads 200,000.
5. Having **both fields appear in the same class** does not cause the instance lock and class lock to intersect. The example uses two different fields, each with its own consistent locking protocol.

This program demonstrates the **correctness of the two locking forms**; it does not measure latency, contention, or overhead. If benchmarking is needed, warm up the JVM, measure multiple times, and vary critical section size, thread count, CPU quota, and external load.

## 8. A Synchronized Getter + Synchronized Setter Can Still Lose Updates

A major design mistake is making each method `synchronized`, then letting callers compose them into a single business operation:

~~~java
class SplitCounter {
    private int count;

    synchronized int get() { return count; }

    synchronized void set(int next) { count = next; }
}

// Callers A and B run concurrently:
int old = counter.get();
counter.set(old + 1);
~~~

Each method is protected **individually**, but the monitor is released when `get()` returns; another thread can enter `get()` before the first caller calls `set()`. Both threads read 0, and then both write 1. Both methods are syntactically synchronized, yet the overall increment is still **not atomic**.

~~~text
A: lock → get()=0 → unlock
B: lock → get()=0 → unlock
A: lock → set(1) → unlock
B: lock → set(1) → unlock

Expected = 2, actual = 1
~~~

**The right approach** is to move the entire read-modify-write into **a single atomic method**, or hold the same monitor across the pair of calls if the API truly requires it:

~~~java
synchronized void increment() {
    count++;
}
~~~

Similarly, a business rule like "if quantity is greater than 0, decrement it" must lock **both the check and the decrement together**. Locking only the decrement still allows two threads to both conclude that the operation can proceed, breaking the business invariant.

### Standalone Example 2: Reproducing the Bug and Fixing It with the Same Lock

Save the file **SplitCriticalSectionDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class SplitCriticalSectionDemo {
    static final class Counter {
        private int count;

        synchronized int get() {
            return count;
        }

        synchronized void set(int next) {
            count = next;
        }

        void incrementAtomically() {
            synchronized (this) {
                count++;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter split = new Counter();
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Runnable brokenIncrement = () -> {
            int snapshot = split.get();
            bothRead.countDown();
            try {
                allowWrite.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            split.set(snapshot + 1);
        };

        Thread a = new Thread(brokenIncrement, "split-a");
        Thread b = new Thread(brokenIncrement, "split-b");
        a.start();
        b.start();
        bothRead.await();
        allowWrite.countDown();
        a.join();
        b.join();

        System.out.println("split=" + split.get());

        Counter safe = new Counter();
        Thread c = new Thread(safe::incrementAtomically, "atomic-c");
        Thread d = new Thread(safe::incrementAtomically, "atomic-d");
        c.start();
        d.start();
        c.join();
        d.join();

        System.out.println("atomic=" + safe.get());
    }
}
~~~

Commands:

~~~bash
javac SplitCriticalSectionDemo.java
java SplitCriticalSectionDemo
~~~

Stdout under normal execution, with no external interrupts:

~~~text
split=1
atomic=2
~~~

**Why is the result deterministic?**
- `bothRead` forces both threads of the broken increment to finish `split.get()` before either proceeds to `set()`.
- When `main` releases `allowWrite`, both `snapshot` values are 0; both call `set(1)` (even though the setter itself is locked), so the final result is 1.
- All `get()` and `set()` calls share `split`'s monitor; **the gap between the two methods** causes the lost update, not a lack of locking inside each individual method.
- In the `safe` branch, the entire `count++` executes under `synchronized (this)` on the same `Counter`. There is no gap between read and write for another thread using the same monitor.
- `join()` lets `main` read the result after all workers finish; `CountDownLatch` in the first branch **stages the bug**, it is not a fix.

If a problem requires multiple fields to change consistently, place the entire operation under one shared monitor or use immutable state with an atomic reference swap. Splitting critical sections too finely can break invariants, even if each field has synchronized getters/setters.

## 9. Monitor Identity: Same Code Does Not Mean Same Lock

Consider two methods:

~~~java
class WrongLocks {
    private final Object firstLock = new Object();
    private final Object secondLock = new Object();
    private int value;

    void add() {
        synchronized (firstLock) {
            value++;
        }
    }

    int read() {
        synchronized (secondLock) {
            return value;
        }
    }
}
~~~

This code uses **two different monitors** to access shared state. Mutual exclusion on `firstLock` does not prevent `read()` using `secondLock` from running while `add()` is updating; furthermore, unlocking `firstLock` **does not establish** a synchronizes-with relationship with locking `secondLock`. If a consistent read/write protocol is needed, both methods must use the **same monitor** or an equivalent synchronization mechanism.

This is the opposite case from validly using multiple locks for **two independent state regions**. If two fields truly have independent invariants, you can have two locks, with each field protected by exactly one lock. However, if logic needs to read/compute across both fields as a single snapshot, a multi-lock design must clearly define how both are acquired together, lock ordering, and deadlock potential.

### Bug: Locking on a New Object per Call

~~~java
void broken() {
    synchronized (new Object()) {
        count++;
    }
}
~~~

This is only a **snippet** inside a class with a `count` field. Because each call creates its own monitor, threads do not share a lock and thus fail to protect `count`. Some JVMs may eliminate this uncontended lock during optimization, but the design bug exists independently of optimization.

### Bug: Locking on a Mutable Reference

~~~java
private Object lock = new Object();

void update() {
    synchronized (lock) {
        // ...
    }
}

void replaceLock() {
    lock = new Object();
}
~~~

If `lock` can be reassigned to another object, threads can simultaneously hold **two different monitors** while both believing they have exclusive access. Therefore, a field used as a monitor should be stable, typically `private final Object lock`; never replace the lock while threads are active.

### Bug: Using a String Literal or Boxed Value as a Monitor

~~~java
synchronized ("GLOBAL_LOCK") {
    // ...
}
~~~

String literals are interned; unrelated code elsewhere may accidentally lock on the same `String`. Boxed values can also be cached/shared. Locking on objects that can easily be aliased externally creates coupling and hard-to-diagnose contention/deadlock risks. Prefer a private lock object that is never exposed externally.

### Pitfall: Locking on `this` Exposes Lock Control to External Callers

~~~java
final class Service {
    synchronized void runTask() {
        // ...
    }
}
~~~

External code can still execute `synchronized(service) { ... }` and hold the same monitor, preventing `runTask()` from entering. There is nothing wrong with this from a JMM standpoint, but it can reduce control over lock ownership. For a shared service with many callers, a private lock often reduces coupling; choose between method and block based on your public API semantics.

## 10. Lock Granularity: Coarse-Grained or Fine-Grained?

**Lock granularity** is the scope of state and code protected by a single monitor. Design must balance three factors:

1. **Correctness:** The entire invariant must be atomic with respect to operations that may contend.
2. **Contention:** Holding a monitor too long makes other threads wait unnecessarily, even during work that does not need sharing.
3. **Complexity:** Many monitors make lock ordering, coupling, and deadlock harder to control.

For example, a method that performs an expensive computation but only increments a shared counter:

~~~java
class TaskProcessor {
    private final Object counterLock = new Object();
    private long completed;

    void process(byte[] input) {
        long checksum = checksumLocally(input);

        synchronized (counterLock) {
            completed++;
        }

        publishResult(checksum);
    }

    long completed() {
        synchronized (counterLock) {
            return completed;
        }
    }

    private long checksumLocally(byte[] bytes) {
        long sum = 0;
        for (byte b : bytes) sum += b & 0xff;
        return sum;
    }

    private void publishResult(long checksum) {
        // A side effect outside the critical section,
        // with the receiver's own concurrency contract.
    }
}
~~~

This is an illustrative class, not a program with `main`. `checksumLocally()` does not modify shared instance state and runs outside the lock. `publishResult()` is assumed to have its own valid protocol; if the business requirement is that publishing the result and incrementing the count form **one transaction**, splitting them is not enough—atomicity must be designed at the appropriate data-source scope.

**Do not arbitrarily pull state reads outside the lock:** If the checksum depended on shared mutable data that another thread could modify, that snapshot or read would also need protection. Only move truly independent computations or operations on immutable inputs outside the lock.

### When Two Resources Are Truly Independent

~~~java
final class TwoCounters {
    private final Object leftLock = new Object();
    private final Object rightLock = new Object();
    private int left, right;

    void incrementLeft() {
        synchronized (leftLock) { left++; }
    }

    void incrementRight() {
        synchronized (rightLock) { right++; }
    }
}
~~~

Two calls can run concurrently because they use different monitors and only modify independent fields. If an invariant such as `left + right <= capacity` is added later, you must **redesign** the locking mechanism—do not rely on independent locks to protect the combined check.

## 11. Reentrancy: The Same Thread Can Re-Acquire a Monitor It Already Holds

Java intrinsic monitors are **reentrant**. When a thread already holds monitor `this`, it can call another `synchronized` method on the same object (or enter `synchronized(this)`) without deadlocking itself.

~~~java
class ReentrantExample {
    private int count;

    synchronized void incrementTwice() {
        incrementOnce(); // same thread re-acquires monitor this
        incrementOnce();
    }

    synchronized void incrementOnce() {
        count++;
    }

    synchronized int get() {
        return count;
    }
}
~~~

When `incrementTwice()` calls `incrementOnce()` twice, the same thread can re-enter the monitor. The JVM tracks the corresponding acquire/release nesting count; the monitor only becomes free for other threads once the owning thread completes all lock levels. Reentrancy does not allow **two threads** to hold the same monitor simultaneously.

### Exceptions and `return`

With a synchronized method, the JVM releases the monitor when the method exits (whether via `return` or an exception). With a synchronized block, exiting the block also releases the monitor, including when an exception exits the block. You do not need to write `finally { unlock(); }` manually as with `ReentrantLock`.

However, if a method modifies **half** of the state and then throws an exception, releasing the monitor **does not mean** the state rolls back automatically. The program must design its own exception safety and invariant handling if a multi-step operation can fail midway.

## 12. Deadlock Can Still Happen with `synchronized`

`synchronized` guarantees mutual exclusion per monitor, but it does not automatically prevent deadlock when multiple monitors are acquired in opposite orders:

~~~text
Thread A: lock(L1) → waits for lock(L2)
Thread B: lock(L2) → waits for lock(L1)

Both hold one monitor and wait for the other → deadlock can occur.
~~~

With nested synchronized blocks, there must be a consistent **lock ordering policy**, for example every path needing both locks acquires `L1` then `L2`. Another option is merging both invariants under a single lock if appropriate, avoiding the need to lock multiple resources simultaneously.

For synchronized methods, deadlock also occurs if a method on object A, while holding monitor A, calls a synchronized method on B, while another thread holds B and calls back into A. "Not seeing nested blocks" is not enough to conclude there is no deadlock; inspect the **call graph and lock order**.

### Avoid Holding a Monitor While Calling Uncontrolled Code If Possible

Invoking callbacks, observers, or external I/O while holding a monitor can cause code to call into other locks, wait for a long time, or block indefinitely. If atomicity across the callback is not required, capture the necessary data inside the lock, exit the lock, and then invoke the callback—while ensuring the snapshot remains consistent with invariants. When holding the lock is required for correctness, control the lock graph and operation bounds.

## 13. Which Monitor Do `wait`/`notify` Relate To?

`Object.wait()`, `notify()`, and `notifyAll()` coordinate using **the monitor of the receiver object itself**. The thread must hold that exact monitor when calling them; otherwise `IllegalMonitorStateException` is thrown.

Example:

~~~java
class Signal {
    private final Object monitor = new Object();
    private boolean ready;

    void markReady() {
        synchronized (monitor) {
            ready = true;
            monitor.notifyAll();
        }
    }

    void awaitReady() throws InterruptedException {
        synchronized (monitor) {
            while (!ready) {
                monitor.wait();
            }
        }
    }
}
~~~

This is an illustrative Java 17+ class without `main`. Calling `wait()` causes the thread to **temporarily release the monitor** of `monitor` and wait; when awakened, the thread must re-acquire the monitor before continuing. Use a `while` loop to re-check the condition after waking up, because spurious wakeups can occur or other threads may have changed the state.

If `markReady()` used `synchronized (monitor)` while `awaitReady()` were a synchronized instance method using `this`'s monitor, those would be **two different monitors**, breaking the coordination protocol. To use `wait`/`notify` safely, you must use the exact same monitor and shared condition.

`Thread.sleep(...)` **does not release any held monitor**; do not confuse `sleep` with `wait`. In new designs, higher-level utilities such as `CountDownLatch`, `BlockingQueue`, `Condition`, or `Future` are often clearer and less error-prone when they fit the need.

## 14. `synchronized` Does Not Guarantee All Invariants Automatically

Suppose the `balance` variable is protected by `synchronized`. The following is not enough if both methods are synchronized but the caller executes them separately:

~~~java
if (account.balance() >= amount) {  // synchronized getter
    account.withdraw(amount);        // synchronized update
}
~~~

Another thread can withdraw money after the first check returns and before the caller invokes `withdraw`. A single operation that both checks and updates is required:

~~~java
class Account {
    private long balance;

    synchronized boolean tryWithdraw(long amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("negative amount");
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

This is an illustrative class working with state inside a single JVM and cannot replace a transaction protocol for external resources or multiple processes. It shows that **the atomic unit must be the business operation**, not individual accessors. The same idea can be written as:

~~~java
boolean tryWithdraw(long amount) {
    if (amount < 0) throw new IllegalArgumentException("negative amount");
    synchronized (accountLock) {
        if (balance < amount) return false;
        balance -= amount;
        return true;
    }
}
~~~

In the block version, `accountLock` is a `private final` lock of the instance; other read/write paths for `balance` must also use the same lock to ensure correctness.

## 15. When Should You Use `synchronized` Method, `synchronized` Block, `Lock`, or Atomic Classes?

| Requirement | Reasonable Approach | Notes |
|---|---|---|
| Most of an instance method body is a critical section and a public monitor is appropriate | `synchronized` instance method | Concise, readable, locks `this` for the entire body. |
| Only a portion of a method touches shared mutable state | `synchronized(privateLock)` block | Keeps the lock properly scoped and still protects the full invariant. |
| Static state managed class-wide | `static synchronized` or block locking a shared static lock | Class monitor is distinct from instance monitors. |
| A simple atomic counter | `AtomicInteger.incrementAndGet()` / `AtomicLong` | No lock needed just to increment one variable; check-then-act sequences still need appropriate CAS. |
| Multiple fields requiring a combined invariant | Method/block with the same monitor or `Lock` | Must protect the entire operation, including condition checks. |
| Need timeout on lock acquisition or interruptible waiting | `ReentrantLock.tryLock(timeout)` / `lockInterruptibly()` | Manual lock/unlock, `unlock()` in `finally` after successful acquisition. |
| Many readers, few writers with a suitable structure | `ReadWriteLock` or `StampedLock` depending on design | More complex; must measure effectiveness and understand semantics. |
| Avoid shared mutable state entirely | Immutable data / local variables / thread confinement | Reduces synchronization requirements and is usually easiest to verify. |

Do not choose a mechanism merely because it is "faster." First ask: **what invariant needs protection, where is that state shared, who is allowed to update it, and when must reads see the result?** Then check contention and performance under a real workload.

### Note on Virtual Threads

In Java 21, certain blocking operations occurring while a virtual thread holds a monitor can cause the carrier thread to experience **pinning**, affecting scalability under long-waiting workloads; JVM support has continued to improve in newer JDK releases. The mutual exclusion and happens-before rules of synchronized methods and blocks remain essentially the same Java rules. Do not use "synchronized block instead of method" as a trick to avoid pinning: **the held monitor and the type of blocking operation** are what matter. Evaluate on your **specific JDK** and avoid holding monitors across long blocking operations when unnecessary.

## 16. Common Misconceptions in Interviews and Code Reviews

**"A `synchronized` method locks the entire class."** False for an **instance method**: it locks the receiver's monitor. Only `static synchronized` uses the class monitor; instances have their own separate monitors.

**"`synchronized(this)` is different from a `synchronized` instance method even when wrapping the whole method."** Incorrect regarding lock identity and critical section: both use the `this` monitor. They differ in syntax and scope-selection capability, not by default in safety.

**"I locked the getter and setter, so get-then-set is atomic."** False. Each method releases the monitor upon returning; another thread can interleave between the two calls. Combine read-modify-write or check-then-act into a single critical section.

**"Two `synchronized` blocks in two methods always exclude each other."** Only if they acquire the **same monitor object**. If `lockA` and `lockB` are different objects, they do not.

**"More locking is always safer."** Excessive locking can increase contention or deadlock risk and still cannot fix a broken protocol. You must protect **all access paths** and the right **business unit**.

**"Code outside a `synchronized` method is blocked from accessing that object."** No. Only code that attempts to acquire the same monitor waits. An unsynchronized method can run concurrently, even while the monitor is held.

**"`synchronized` only handles atomicity, not visibility."** False. Unlock and subsequent lock on the same monitor have a synchronizes-with relationship, establishing happens-before that guarantees visibility and ordering under the JMM.

**"A `synchronized` block is always faster than a method."** No guarantee. When they lock the same monitor and the same scope, the synchronization logic is similar. The key difference is choosing lock granularity and the monitor.

**"A `synchronized` method that throws an exception holds the lock forever."** False. The monitor is automatically released when exiting the method or block, even due to an exception. However, data may remain in a partially updated state if the operation is not exception-safe.

**"There is no `synchronized` in this method, so it cannot deadlock."** False. The method may call other methods that acquire monitors, or have nested locks along the call graph.

**"`synchronized` guarantees FIFO fairness."** No. The JVM does not promise that threads contending for a monitor will acquire the lock in request order; applications must not infer deadlines or starvation freedom from this modifier.

## 17. Checklist for Applying in Production Code

1. List all **mutable state** that multiple threads may access concurrently.
2. Define the invariants to preserve: single-field, multi-field, check-then-act, or a longer sequence.
3. Decide on **one consistent monitor identity** for all related reads and writes.
4. If the entire method body is genuinely one critical section and locking the receiver is appropriate, use a `synchronized` method.
5. If only part needs protection or a private lock is needed, use a `synchronized` block while keeping **all** related steps inside.
6. For static state, verify whether the lock is the class monitor or a `private static final` lock; do not confuse it with an instance monitor.
7. Avoid creating a new lock per call, mutable locks, `String` literals, and objects that external code might hold for long periods.
8. Do not call potentially long-blocking code or callbacks inside a lock unless the invariant requires it.
9. If multiple locks exist, document the lock ordering and analyze deadlock risk.
10. Ensure state reads are properly synchronized; do not rely on `private`/`final` fields to protect mutable state.
11. Write concurrency tests using `CountDownLatch`/`Future`/`join` to verify correctness. Do not treat one passing stress test as proof that all races are eliminated.
12. Measure real workloads before concluding which lock granularity is optimal; correctness always comes before performance.

## 18. Self-Check Exercises

**Q1.** Two threads call `synchronized void add()` on **two different instances** of `Counter`. Must they wait for each other?

**Answer:** No, because the two instances have different monitors, unless `add` also uses another shared lock internally. If both instances modify the same static field, instance-level `synchronized` does not automatically protect that field.

**Q2.** `synchronized void update()` and `void read() { synchronized(this) { ... } }` belong to the **same instance**. Can the two critical sections run concurrently on two threads?

**Answer:** No. Both acquire the same monitor of the receiver.

**Q3.** `static synchronized void update()` and `synchronized void updateInstance()` belong to the same class. Do they automatically exclude each other?

**Answer:** No. The static method uses the `Class` monitor; the instance method uses the receiver's monitor.

**Q4.** Both the getter and setter are synchronized on `this`. Is that safe enough for `set(get()+1)`?

**Answer:** No. The lock is released between the two methods. A single synchronized operation covering the entire read-modify-write is required.

**Q5.** Why does `synchronized(new Object())` usually fail to resolve contention on a shared counter?

**Answer:** Each call creates a different monitor. Threads do not acquire the same lock, so there is no mutual exclusion on the counter.

**Q6.** If a method performs 1 second of I/O but only increments a shared counter once, should you use a `synchronized` method or block?

**Answer:** If the I/O is not part of the invariant requiring the lock, use a block protecting only the increment with the shared lock to avoid holding the monitor throughout the I/O. If external resources participate in the invariant, a broader consistency protocol must be designed.

## 19. Reference Documentation

- **Java Language Specification `8.4.3.6 — synchronized Methods`:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.3.6
- **Java Language Specification `14.19 — The synchronized Statement`:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.19
- **Java Language Specification `17.1 — Synchronization`:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.1
- **Java Language Specification `17.4.4 — Synchronization Order`:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.4
- **Java Language Specification `17.4.5 — Happens-before Order`:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5
- **ReentrantLock API (Java 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html
- **Thread API (Java 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html

**Key takeaway:** A `synchronized instance method` is equivalent to a `synchronized(this)` wrapping the entire method body; `static synchronized` is equivalent to using the `MyClass.class` monitor; a `synchronized block` allows choosing a different monitor and narrowing the locked region. **The same monitor and the right atomicity scope determine correctness**, not merely seeing the `synchronized` keyword.
