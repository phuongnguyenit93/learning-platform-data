# Atomicity, Visibility, and Ordering of Operations Between Threads

## 1. Accessing the Same Memory Does Not Mean Seeing the Same Thing

In multithreaded Java, multiple threads can access the same object/field on the heap, but that **does not automatically** guarantee a correct program. One thread may update a field; another thread may see the old value, or the steps making up an update may interleave with steps from another thread.

Three groups of properties to distinguish:

- **Atomicity:** a **specified operation or combination of operations** executes as a unit that cannot be observed in an intermediate state by competing operations according to the atomicity contract.
- **Visibility:** writes from thread A become observable in thread B according to the **Java Memory Model (JMM)** rules when an appropriate synchronization relationship exists.
- **Ordering:** the compiler/CPU/runtime may reorder/optimize instructions as long as valid behavior under the JMM is preserved; relationships such as **happens-before** place constraints on cross-thread observed ordering.

**Key summary:** an **atomic** operation does not necessarily provide the ordering/visibility needed for **other operations**; a `volatile` variable has visibility/ordering guarantees, yet `count++` is still **not atomic**; a `synchronized` block can simultaneously protect the atomicity of a critical section and provide happens-before between lock/unlock actions on **the same monitor**.

### Minimal Example

~~~java
class Counter {
    int count;

    void increment() {
        count++;
    }
}
~~~

This is an illustrative class without a `main` method. If two threads call `increment()` on **the same instance** without synchronization, you are not guaranteed a result equal to the total number of calls. The statement `count++` consists of reading the value, adding 1, and writing it back — it is not an atomic read-modify-write operation under the JMM.

Three issues can occur together:

1. Two threads can both read 5, both compute 6, and both write 6: **lost update** (lack of atomicity).
2. One thread reads an unsynchronized value from the other thread: **visibility/data race**.
3. The compiler/CPU can allow unsynchronized operations to have an observed order that makes code seem reasonable in source order but wrong in multithreading: **ordering**.

This lesson explains these three properties precisely, the relationships between them, and how to write safe Java 17+.

## 2. The Java Memory Model (JMM)

The JMM is defined primarily in the **Java Language Specification, Chapter 17 — Threads and Locks, §17.4**. It specifies **which read/write behaviors are legal** for a multithreaded program, without promising that each Java source line corresponds to one machine instruction or one physical “cache sync”.

Core terms:

| Term | Explanation |
| --- | --- |
| **Action** | Read/write variables, lock/unlock, volatile accesses, thread-start/join-related synchronization actions… |
| **Program order** | The order of actions within a single thread according to that thread's semantics |
| **Synchronization order** | A total order of synchronization actions in a JMM-compliant execution |
| **Synchronizes-with** | A relationship between synchronization actions, for example unlocking a monitor and a subsequent lock on the same monitor |
| **Happens-before (HB)** | The transitive closure of **program order** and **synchronizes-with** |
| **Data race** | Two conflicting accesses to the same variable from different threads, at least one being a write, with no happens-before ordering them |
| **Correctly synchronized** | A program has no data races in sequentially consistent executions according to the JLS; the JMM guarantees that executions appear sequentially consistent |

**Happens-before does not simply mean A “occurred earlier by wall-clock time.”** It is a **rule-based relationship** that constrains the visibility/ordering of A's write results at B; two threads running on the same CPU or looking at real-time timestamps is not enough to prove HB.

### How to Reason Using an HB Graph

~~~text
Thread A                           Thread B
---------                          ---------
data = 42
    |
    v (program order)
volatile ready = true
    |
    | synchronizes-with (when the reader observes the matching write)
    +---------------------------------------+
                                            |
                                    if (ready)  // volatile read
                                            |
                                            v (program order)
                                     print(data)
~~~

If `ready` is `volatile`, the writer writes `data=42` before the volatile write, and the reader reads `ready=true` in the appropriate synchronization order, the transitive HB rule forces the reader to see `data=42` (assuming no other competing write to `data`).

**Do not infer** that every read of `data` from any thread will see the new value **just because there is another volatile field in the same class**. The reader must go through the right synchronization edge or an equivalent edge.

## 3. Atomicity: A Single Read/Write Differs from a Read-Modify-Write

### 3.1. Single Operations

The JLS specifies that reads/writes of **references** and primitive variables of size **at most 32 bits** are atomic at the level of an individual variable access. For **non-volatile** `long`/`double`, JLS `17.7` allows an implementation to treat a read/write as two 32-bit operations by rule, so you must not rely on portable atomicity of plain 64-bit accesses in this case. **Volatile `long`/`double` reads/writes are atomic.**

This **does not** make a sequence of operations atomic. An atomic assignment of `int` does not mean two `x = x + 1` statements on two threads are combined correctly.

| Access | Atomic under portable semantics? | Other cross-thread synchronization? |
| --- | --- | --- |
| Plain read/write `int` | Yes, at the single read/write level | No |
| Plain read/write reference | Yes, at the single reference read/write level | No |
| Plain read/write `long`/`double` | Not guaranteed 64-bit indivisible by the JLS | No |
| `volatile long` read/write | Yes | Has volatile ordering/visibility |
| `volatile int` read/write | Yes | Has volatile ordering/visibility |
| `volatile int++` | **No**, because of multiple steps | Has individual volatile accesses but does not protect the whole RMW |
| `AtomicInteger.incrementAndGet()` | **Yes**, atomic update per API | Has memory effects of the atomic operation |
| `synchronized(lock) { count++; }` | Critical section protected with the same lock | Has monitor HB on proper release/acquire |

### 3.2. Lost Update

~~~text
Initially count = 5

Thread A                         Thread B
--------                         --------
read count -> 5
                                 read count -> 5
calculate 6
                                 calculate 6
write count = 6
                                 write count = 6

Result: 6, even though there were two increments -> logical expectation: 7
~~~

An **interleaving like the one above** is enough to explain why two reads plus two writes are not atomic. With a plain unsynchronized field, in reality the JMM also allows additional complex visibility/ordering behaviors; the diagram only illustrates one failure mode.

### 3.3. Volatile Does Not Save `++`

~~~java
class VolatileCounter {
    volatile int count;

    void increment() {
        count++;
    }
}
~~~

**`volatile` does not turn the expression `count++` into an atomic read-modify-write.** The JIT may emit a volatile read, an add, and a volatile write with appropriate memory ordering, but another thread can still interleave in between. For a shared counter, use `AtomicInteger.incrementAndGet()`, `LongAdder.increment()` when appropriate accumulation semantics are acceptable, or `synchronized`/`Lock` if multiple variables must be protected together.

## 4. Visibility: Why Written Data May Not Be Observable Yet?

Example:

~~~java
class StopFlag {
    boolean running = true;

    void work() {
        while (running) {
            // work
        }
    }

    void stop() {
        running = false;
    }
}
~~~

This is an illustrative class that **has a data race if two threads call `work`/`stop` without synchronization**, and should not be used as-is in an application. One thread writing `running=false` does not create an HB edge to another thread via a plain assignment alone.

**Possible bug:** the reader continues to see a stale value or the compiler/JIT optimizes the loop path assuming there is no properly synchronized modification. JLS `17.4` has an example of a non-terminating loop when a variable is unsynchronized.

Do not conclude from the fact that a program “always stops on my machine” that it is correct under the JMM: CPU cache, compiler tier, workload, and timing can cause the bug to appear only at other times.

### What Does `volatile` Provide?

~~~java
class StopFlag {
    volatile boolean running = true;

    void stop() {
        running = false;
    }
}
~~~

Volatile reads/writes have **ordering/visibility effects** under the JMM. A volatile write to `running` **synchronizes-with** subsequent volatile reads of **the same variable** in synchronization order.

That allows a flag protocol to be visibility-correct if other actions are placed properly before/after. However:

- The JMM does not promise that a thread will definitely be given CPU by the scheduler within a deadline.
- `volatile` does not lock multiple statements together into a transaction.
- If the program needs wait/notify, blocking, or cancellation, prefer `Interrupt`, `BlockingQueue`, `CountDownLatch`, or an appropriate concurrency API instead of an unbounded busy spin.

**Do not explain volatile simply as “every read must fetch from RAM, bypassing CPU cache.”** The physical mechanism may involve cache coherence, barriers, compiler scheduling, and CPU ISA; what Java guarantees is **observable ordering/visibility semantics**, not cache access details.

## 5. Ordering: Code That Is Correct in One Thread Can Be Wrong When Reasoning Across Threads

The compiler/JIT and CPU may perform transformations/reorderings **as long as intra-thread semantics and JMM-permitted behavior are preserved**. The statement “Java executes instructions from top to bottom” is only safe when referring to **single-thread behavior as observed according to the rules**; it does not establish a common total order of plain unsynchronized accesses across all threads.

A famous litmus test:

~~~java
// Initially x = 0, y = 0
// Thread A                     // Thread B
x = 1;                           y = 1;
r1 = y;                          r2 = x;
~~~

This is **concurrent litmus pseudocode**, not a standalone Java class. If `x`/`y` are plain unsynchronized shared `int`s, the outcome `r1 = 0` **and** `r2 = 0` is a valid behavior in a model with a data race in this situation.

**There is no need to assume the two threads “time-traveled.”** The two writes/reads have no HB edges, so the JMM can allow observations that do not match the sequential intuition of someone reading the source.

If both `x` and `y` are `volatile` and the actions are as above, synchronization ordering makes the configuration “both reads are 0” invalid: each thread has a volatile write before a volatile read, so a total synchronization order cannot place both reads before their corresponding writes while still respecting program order.

**Important point:** do not use `Thread.sleep` or `Thread.yield` to “fix reordering.” They do not establish ordinary HB edges between plain writes/reads of two threads.

## 6. Happens-Before: How to Legitimize Visibility and Ordering

JLS `17.4.5` defines HB from:

1. **Program order:** if action A precedes B in the same thread, then A happens-before B.
2. **Synchronizes-with:** pairs of synchronization actions specified by the JLS.
3. **Transitivity:** if A HB B and B HB C, then A HB C.

Notable synchronization edges:

| Source (release) | Target (acquire) | Important HB |
| --- | --- | --- |
| `unlock` monitor M | subsequent `lock` on **the same monitor M** | Writes in the prior critical section are properly visible |
| `volatile write` field V | subsequent `volatile read` of **V** in synchronization order | Ordinary writes before the release can be published |
| `Thread.start()` from thread A | Actions of the started thread | Data prepared before start is published |
| Thread T completes | Actions in another thread detecting termination (successful `join`, etc.) | Results written by T can be read after join |
| `interrupt` to a thread | Action recognizing the interrupt per JLS | Ordering related to interruption |
| Class initialization per JLS | Accesses that need to see the class initialized | Class-init synchronization guarantees |
| `CountDownLatch.countDown` | corresponding `await` return | Memory consistency guarantee per `java.util.concurrent` API |

**Be careful:** `Thread.join()` can complete abnormally via `InterruptedException`/timeout; only infer HB from the proper semantics of detecting thread termination. `await` must also succeed according to its contract to infer the corresponding action relationship.

### Release/Acquire and Transitive Visibility

~~~text
Thread A                         Thread B
data = 42
ready = true   [volatile write] --sw--> [volatile read] ready == true
                                                |
                                                v
                                         print(data) => 42

data write --program order--> volatile write
volatile read --program order--> data read

=> data write happens-before data read.
~~~

This is the **message-passing pattern** when `data` is only published by the writer before `ready`, with no competing writers outside the protocol. If the reader only treats `ready` as a plain variable, there is no synchronization edge and the reasoning above no longer holds.

### HB Does Not Mean “Real-Time Before”

Even if a log timestamp from thread A is smaller than a timestamp from thread B, without synchronization, log order does not establish HB for the shared field you want to verify. Logger/I/O may have its own locking, accidentally changing timing and masking a race.

## 7. Runnable Java 17+: AtomicInteger and Synchronized Counter

Create the file **`AtomicityDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicityDemo {
    private static final Object LOCK = new Object();

    private static int protectedCount;
    private static final AtomicInteger atomicCount = new AtomicInteger();

    private static void runIncrements() {
        for (int i = 0; i < 100_000; i++) {
            synchronized (LOCK) {
                protectedCount++;
            }
            atomicCount.incrementAndGet();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Thread first = new Thread(AtomicityDemo::runIncrements);
        Thread second = new Thread(AtomicityDemo::runIncrements);

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("synchronized=" + protectedCount);
        System.out.println("atomic=" + atomicCount.get());
    }
}
~~~

Run:

~~~bash
javac -g AtomicityDemo.java
java AtomicityDemo
~~~

**Deterministic stdout if threads complete normally:**

~~~text
synchronized=200000
atomic=200000
~~~

Because:

- Two threads, each running **100,000** increments.
- Both access `protectedCount` under **the same monitor LOCK**; increments do not interleave concurrently inside the critical section.
- `AtomicInteger.incrementAndGet()` is an atomic update operation.
- Main calls `join()` on both threads before printing, so actions prior to completion are guaranteed to be properly observed under HB.
- Only the main thread prints to stdout, so the order of the two lines is fixed.

**Do not equate overall semantics:** synchronized can protect multiple fields if they are under the same lock protocol; `AtomicInteger` provides atomic operations on its own value. If you want to update **two fields as a single transaction**, two independent `AtomicInteger`s alone are usually not enough.

### Why Not Include Plain `count++` in the Expected Output?

If you add a plain `int racyCount++` alongside, the value may be less than 200,000, or occasionally equal to 200,000 due to scheduling; **there is no reliable fixed output**. This lesson does not measure races with `println` statements, but rather demonstrates correct implementations.

## 8. Runnable Java 17+: Volatile Publication and Message Passing

An example using volatile as a **data publication flag**:

Create the file **`VolatileMessage.java`**:

~~~java
public class VolatileMessage {
    private static int payload;
    private static volatile boolean ready;

    public static void main(String[] args) throws InterruptedException {
        Thread reader = new Thread(() -> {
            while (!ready) {
                Thread.onSpinWait();
            }
            System.out.println("payload=" + payload);
        });

        reader.start();

        Thread writer = new Thread(() -> {
            payload = 42;
            ready = true;
        });

        writer.start();
        writer.join();
        reader.join();

        System.out.println("ready=" + ready);
    }
}
~~~

Run:

~~~bash
javac -g VolatileMessage.java
java VolatileMessage
~~~

**Stdout when threads are scheduled and complete normally:**

~~~text
payload=42
ready=true
~~~

Why `payload=42`:

1. The writer writes plain `payload = 42` before the volatile write `ready=true`.
2. The reader checks `ready` with a volatile read and exits the loop when it sees true.
3. The volatile write/read on the same variable establishes a synchronization/HB edge.
4. By transitivity, writing `payload` happens-before reading `payload` in the reader.
5. Main `join()`s both threads, then reads `ready` and prints the result.

**Practical condition:** the JMM does not guarantee that a thread will always be given CPU by the scheduler within a specific time; the spin loop has no deadline. The example is suitable for understanding visibility, not a good production waiting approach for performance. In a real application, use `CountDownLatch`, `BlockingQueue`, `Condition`, or `CompletableFuture` to wait instead of busy spinning; `Thread.onSpinWait` is only a hint to the CPU/JVM and does not itself create a memory synchronization edge.

**Do not confuse:** `payload` does not need to be declared volatile in this protocol because **the volatility of the ready flag** is sufficient to publish the ordinary write before the flag if the protocol is followed. However, if another thread still modifies `payload` without synchronization, the problem changes.

## 9. `synchronized`: Mutual Exclusion While Also Creating HB

A block:

~~~java
synchronized (lock) {
    balance = balance + amount;
    transactionCount++;
}
~~~

Is an **illustrative code snippet**, requiring `lock`/`balance`/`transactionCount` and an appropriate class.

If **all threads** use **the same monitor object `lock`** to read/write the related fields, the monitor guarantees:

- **Mutual exclusion:** two threads do not execute the critical section of **the same monitor** at the same time.
- **Visibility/ordering:** a monitor unlock **synchronizes-with** a subsequent lock of that monitor.
- **Compound invariant:** both `balance` and `transactionCount` can be protected so they are updated/observed as a single logical transaction unit under the lock.

**Common mistake:** the writer uses `synchronized(lockA)`, the reader uses `synchronized(lockB)`, and thinks because “both are synchronized” there is already HB. No — different locks do not create an unlock→lock edge on **the same monitor**.

### Instance Synchronized vs Static Synchronized

- `synchronized void f()` locks on `this`.
- `static synchronized void g()` locks on `YourClass.class`.
- `synchronized(otherObject)` locks on `otherObject`.

Therefore, `f()` on two different instances does not lock the same monitor. Use a fixed shared lock or the same instance according to actual ownership.

### Lock on All Read as Well as Write Paths

If the writer protects a field under a lock but the reader reads the field plain outside the lock, you cannot assume the reader synchronizes-with the writer. Thread safety requires a **uniform protocol** across all accesses to shared mutable state.

## 10. `volatile`: Visibility/Ordering Is Not a Multi-Field Transaction

Consider:

~~~java
class PairState {
    volatile int x;
    volatile int y;

    void setBoth(int a, int b) {
        x = a;
        y = b;
    }

    int sum() {
        return x + y;
    }
}
~~~

The two writes are **two separate volatile writes**, and the two reads are **two separate volatile reads**. The reader can read a pair of values from **two different states** when the writer interleaves. `volatile` does not combine two writes/references into an atomic snapshot.

Solutions depending on the problem:

- Use `synchronized`/`Lock` around both set/read.
- Use an **immutable snapshot** published via **a single volatile reference**:

~~~java
record Snapshot(int x, int y) {}

volatile Snapshot current = new Snapshot(0, 0);
~~~

This is an illustrative snippet inside a class, not a standalone file. When the writer assigns a **new immutable Snapshot** to `current` and the reader reads `current` **once** and then retrieves both `x`/`y`, the reader gets a consistent snapshot without mixing fields between two object versions.

**Be careful:** if the reader writes `current.x() + current.y()` and reads `current` twice, the two volatile reads may see two different snapshots. Instead, use:

~~~java
Snapshot snapshot = current;
int total = snapshot.x() + snapshot.y();
~~~

This is a continuation of the illustrative snippet and requires a class context. **A volatile reference does not make the pointed-to object immutable.** If a mutable object inside is modified after publication without synchronization, a race still exists.

## 11. Atomic Classes and Compare-And-Set (CAS)

`AtomicInteger`, `AtomicLong`, and `AtomicReference` provide atomic operations and memory effects clearly documented by the API, typically based on VarHandle primitives / appropriate machine-level synchronization instructions.

### Compare-and-set

~~~java
AtomicInteger value = new AtomicInteger(10);

boolean ok = value.compareAndSet(10, 20);
int now = value.get();
~~~

This is an illustrative snippet requiring `import java.util.concurrent.atomic.AtomicInteger`, yielding `ok == true` and `now == 20` if no other thread intervenes.

**CAS** checks the current value against the expected value and updates it only when it matches as an atomic operation. It is a building block for lock-free algorithms, but:

- **CAS failure** can occur due to concurrent interference.
- **Weak CAS** variants can **spuriously fail** per the API.
- `compareAndSet` on one field **does not create a concurrent transaction** across multiple fields.
- If the retry calculation logic has **side effects**, re-invoking the lambda in `updateAndGet` can repeat side effects multiple times — the API recommends side-effect-free functions.
- **ABA problem:** a value changing A→B→A can allow a CAS expecting A to still succeed even though the state changed in between; for complex lock-free structures, appropriate versions/stamps/algorithms are needed.

### `LongAdder` and Snapshot Consistency

`LongAdder` is suitable for high-contention counters and `sum()` can aggregate multiple cells, but **`sum()` is not an atomic snapshot when updates are running concurrently**. Do not use `LongAdder` if every read must be linearizable like `AtomicLong.get()` in a protocol requiring atomic state.

## 12. Runnable Java 17+: Entire State Under the Same Monitor

Create the file **`LockedAccount.java`**:

~~~java
public class LockedAccount {
    private int balance;
    private int operations;

    public synchronized void deposit(int amount) {
        balance += amount;
        operations++;
    }

    public synchronized String snapshot() {
        return balance + ":" + operations;
    }

    public static void main(String[] args) throws InterruptedException {
        LockedAccount account = new LockedAccount();

        Thread a = new Thread(() -> {
            for (int i = 0; i < 5_000; i++) {
                account.deposit(2);
            }
        });
        Thread b = new Thread(() -> {
            for (int i = 0; i < 5_000; i++) {
                account.deposit(3);
            }
        });

        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("balance:operations=" + account.snapshot());
    }
}
~~~

Run:

~~~bash
javac -g LockedAccount.java
java LockedAccount
~~~

**Exact stdout if both threads complete normally:**

~~~text
balance:operations=25000:10000
~~~

Explanation:

- A contributes `5000 * 2 = 10000`, B contributes `5000 * 3 = 15000`, total **25000**.
- Total number of `deposit` calls is **10000**.
- `deposit` and `snapshot` are **instance synchronized** on **the same `account`**, so critical sections exclude each other; main `join` ensures both threads have completed before the snapshot.
- This is an example where multiple fields must remain consistent with each other, unlike a single `AtomicInteger` counter.

**Limitation:** the example does not guard against negative amounts or overflow; if writing a real bank account, validation, currency semantics, transaction storage, and separate domain rules are needed. This lesson focuses only on the JMM.

## 13. Thread.start, Thread.join, and Safe Handoff

It is not only `volatile`/`synchronized` that create HB; thread lifecycles also have synchronization rules.

### `Thread.start()`

~~~java
class StartExample {
    int data;

    void runExample() throws InterruptedException {
        data = 42;
        Thread worker = new Thread(() -> {
            System.out.println(data);
        });
        worker.start();
        worker.join();
    }
}
~~~

This is an illustrative class without `main`. Writing `data=42` in the parent thread occurs before `start()` in program order; `start()` creates a synchronizes-with edge to the worker thread. Thus the worker sees the properly published data if there are no competing writes.

### `Thread.join()`

When main successfully detects that the worker has terminated via `join()`, the worker's actions happen-before main observes the data after join under the JMM. In the two demos `AtomicityDemo` and `LockedAccount`, `join()` is the critical part that ensures main reads the result after all increments complete.

**Do not assume** that `Thread.sleep(100)` replaces `join()`. Sleep only pauses a thread, does not wait accurately for worker completion, and does not have the same HB guarantee.

### Publication Through Concurrent Utilities

`java.util.concurrent` defines **memory consistency effects** for many utilities:

- Actions before `CountDownLatch.countDown()` happen-before actions following a successful return from the corresponding `await()`.
- Actions before submitting a task to an `ExecutorService` happen-before task actions per the documented contract.
- Task actions happen-before actions following a successful `Future.get()` per the documented contract.
- Enqueue/dequeue in concurrent collections have memory consistency guarantees per each API.

**Simply “using a method in the concurrent package” does not automatically make all fields thread-safe.** Always read the contract of the exact operation and build an appropriate protocol.

## 14. Runnable Java 17+: CountDownLatch Instead of Busy Spin

Create the file **`LatchHandoff.java`**:

~~~java
import java.util.concurrent.CountDownLatch;

public class LatchHandoff {
    private static int payload;
    private static final CountDownLatch READY = new CountDownLatch(1);

    public static void main(String[] args) throws InterruptedException {
        Thread consumer = new Thread(() -> {
            try {
                READY.await();
                System.out.println("payload=" + payload);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();

        Thread producer = new Thread(() -> {
            payload = 42;
            READY.countDown();
        });

        producer.start();
        producer.join();
        consumer.join();
        System.out.println("completed");
    }
}
~~~

~~~bash
javac -g LatchHandoff.java
java LatchHandoff
~~~

**Stdout in a normal, uninterrupted run:**

~~~text
payload=42
completed
~~~

Here `payload` **does not need to be volatile** because the producer writes before `countDown()`, and the consumer reads after `await()`; the `CountDownLatch` API provides HB, while main `join` guarantees the print order of the two lines.

This is a better pattern than a long spin loop because the consumer **waits with a blocking mechanism**. If the consumer is interrupted, the code restores the interrupt flag and does not print `payload`; the output above is stated specifically for normal execution.

**Do not use `CountDownLatch` as a resettable event:** once the count reaches 0, it does not reset. If repeated signaling is needed, consider `Phaser`, `Condition`, or an appropriate API.

## 15. Final Fields and Safe Publication

JLS `17.5` gives special semantics for **final fields**, which are very useful for immutable objects.

~~~java
final class Point {
    final int x;
    final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }
}
~~~

This is an illustrative class. If the constructor is executed properly without letting `this` escape before completion, final-field semantics help threads that receive the reference see the properly initialized final values under the conditions specified by the JLS.

**Do not assume the entire object graph is automatically thread-safe just because a reference is final.** For example:

~~~java
final class Holder {
    final int[] values = {1, 2, 3};
}
~~~

The reference field `values` is final, but **the array elements are still mutable**. If one thread modifies `values[0]` and another thread reads it without synchronization, there is still a race on the element.

### Useful Safe Publication

Safe options for publishing a new object:

- Share via a **volatile reference** following the proper protocol.
- Publish inside a monitor/lock and read under the same monitor/lock.
- Put/take through a concurrent collection with memory consistency effects.
- Use thread-start/handoff and join according to documented HB.
- Build an immutable object and use **final fields** properly, avoiding `this` escape in the constructor.

**Final-field guarantees are not a license to publish any mutable state without synchronization.** An object with final fields can be safer regarding initialization, but mutable nested objects and publishing the reference still require protocol consideration.

### Double-Checked Locking

When writing a lazy singleton using double-checked locking, the `instance` field must use an appropriate publication mechanism (usually **`volatile`**) to prevent the risk of reading an improperly published instance. Simpler and easier-to-verify approaches are the **static holder idiom** or an `enum` singleton when appropriate.

## 16. Reordering Does Not Mean a Program Can Return “Arbitrary” Values

Another misconception: without `volatile`, Java “can return any bit pattern.” The JMM **does not** allow arbitrarily creating values out of thin air; it has rules for well-formed executions and causality (§17.4.7–§17.4.8). Nevertheless, a program with a data race can have counterintuitive behavior that a programmer is not allowed to ignore.

The right way to learn:

- With a **data-race-free design**, you have a model to reason consistently via synchronization/HB.
- With a **racy design**, do not replace the model with assumptions like “the CPU will probably execute in source order” or “on x86 cache coherence will save me.”
- With **`volatile`**, use the proper release/acquire communication pattern or atomic update methods, do not treat it as a lock.
- With **locks**, protect all accesses to the same data under the same protocol.

### Data Race Freedom and Sequential Consistency

The JLS states that a **correctly synchronized** program has executions that appear **sequentially consistent**. However, sequential consistency **does not automatically make a multi-step operation atomic**: if logic requires read/modify/write as a transaction, you still need mutual exclusion or an atomic RMW. Do not equate “no data race” with “all business invariants are definitely correct.”

## 17. VarHandle: Plain, Opaque, Acquire/Release, Volatile

Since Java 9, `java.lang.invoke.VarHandle` provides access modes with different memory-ordering guarantees, useful when building low-level primitives/concurrent structures.

| Mode | Example operations | General meaning |
| --- | --- | --- |
| **Plain** | `get`, `set` | Like accessing a non-volatile field, minimal ordering; does not resolve races by itself |
| **Opaque** | `getOpaque`, `setOpaque` | Atomic/coherent for the same variable per API, weaker ordering than acquire/release |
| **Acquire** | `getAcquire` | Prevents subsequent accesses from being reordered before it per acquire semantics; pairs with release |
| **Release** | `setRelease` | Publishes prior accesses per release semantics; pairs with acquire |
| **Volatile** | `getVolatile`, `setVolatile` | Has stronger volatile ordering guarantees |
| **Atomic RMW** | `compareAndSet`, `getAndAdd` | Atomic update with memory semantics corresponding to the mode |

**Each access mode has its own contract**; do not say all acquire/release/opaque/volatile modes are equivalent or that every plain 64-bit operation is bitwise atomic. Java SE 17 `VarHandle` documents the differences in detail, including spurious failures of weak CAS.

### Be Careful When Using Fences

`VarHandle.fullFence()`, `acquireFence()`, `releaseFence()`, and related methods help place ordering constraints, but **do not automatically turn every plain variable access into a thread-safe protocol**. Fences do not turn a non-atomic `count++` into an atomic one.

**Prefer** `volatile`, `AtomicInteger`, `synchronized`, `Lock`, or concurrent utilities first; only use VarHandle/fences when a low-level algorithm is truly needed and can be verified.

## 18. Java Memory Model and CPU Memory Model

CPUs have cache coherence, store buffers, and instruction reordering; the JIT compiler also optimizes machine code for the target architecture. **The JMM sets the contract at the Java layer**, while HotSpot/CPU must implement it using appropriate instructions/barriers/hardware.

~~~text
Java code + JMM promises
          |
          v
Compiler (interpreter, C1, C2, etc.)
          |
          v
Architecture-specific machine code
          |
          v
CPU caches, store buffers, memory ordering
          |
          v
Observable Java behavior must conform to the JMM
~~~

On x86-64, some CPU ordering guarantees are stronger than on weaker architectures; on ARM/AArch64 there are acquire/release instructions and appropriate memory barriers. However, **do not write Java code relying on the habit “x86 usually seems to work”**: the JIT and runtime are allowed to optimize according to the JMM, and the application may run on different hardware/JVMs.

**`volatile` does not mean “data must be flushed to DRAM every time.”** Cache lines can stay in cache while being managed with proper coherence/ordering; what needs to be measured or proven is Java-level HB semantics.

## 19. Choosing the Right Tool for the Requirement

| Need | Appropriate approach | Avoid misconception |
| --- | --- | --- |
| A completion/one-time publication flag | `volatile boolean` or `CountDownLatch` | `volatile` does not promise a scheduler wake deadline |
| A simple atomic counter | `AtomicInteger` / `AtomicLong` | `volatile int++` is not atomic |
| High-contention statistical counter | `LongAdder` | `sum` is not an atomic snapshot while updates run |
| Multi-field invariant | `synchronized` or `Lock` | Multiple volatile fields do not form a transaction |
| Passing messages between threads | `BlockingQueue` / concurrent collection | A plain shared list is not safe enough |
| Wait for completion/result | `join()` / `Future.get()` / latch | `sleep()` does not replace synchronization |
| Shared immutable snapshot | Immutable record/object + volatile publication | A volatile reference does not make a mutable object immutable |
| Lock-free primitive algorithm | CAS/VarHandle + verified design | CAS on one field is not atomic across multiple fields |
| Pause/cancel worker | Interrupt/appropriate protocol | A plain boolean loop has visibility risk |
| Thread-local state only | No shared lock needed for unshared data | Do not over-synchronize, but verify it does not escape |

**For enterprise code**, start from high-level abstractions such as executors, queues, structured handoff, immutable values, and properly protocoled locks. Only drop down to weaker memory modes when there are benchmarks and correctness verification.

## 20. Common Misconceptions

| Misconception | What is true |
| --- | --- |
| “One source statement equals one atomic operation.” | `count++` consists of read-modify-write, not atomic by itself. |
| “A `volatile int++` is atomic.” | False; individual volatile read/write does not make RMW atomic. |
| “Atomicity automatically implies ordering of all other fields.” | No; check the memory effects of the operation and HB edges. |
| “Every thread always reads the most recent write by wall clock.” | The JMM considers synchronization/HB, not just real time. |
| “`volatile` means not using CPU cache.” | The JMM specifies observable semantics, not DRAM access methods. |
| “`Thread.sleep` helps flush cache/happens-before.” | Does not create HB between plain shared accesses. |
| “`Thread.yield` fixes visibility.” | No; it is only a scheduling hint. |
| “Two `synchronized` blocks with different locks synchronize with each other.” | Unlock→lock HB requires **the exact same monitor**. |
| “An instance synchronized method locks all instances.” | It locks the calling `this` instance. |
| “`static synchronized` locks on the instance.” | Locks on the corresponding Class object. |
| “A volatile reference makes the pointed-to object thread-safe.” | No; mutable fields need their own protocol. |
| “Two volatile fields are always a consistent snapshot.” | No; the accesses are separate. |
| “`AtomicInteger` automatically creates a multi-variable transaction.” | No, it protects atomic operations on that single value. |
| “`LongAdder.sum()` is atomic while updates are running.” | Does not guarantee an atomic snapshot under concurrent updates. |
| “One run not reproducing a race means the code is right.” | No; timing/JIT/architecture can hide the bug. |
| “`Thread.join()` only waits and is unrelated to visibility.” | Successfully observing termination has HB under the JMM. |
| “Data-race-free means all logic is automatically right.” | Proper invariants and atomic grouping are also needed. |
| “`final List` means the list is immutable.” | A final reference does not make the pointed-to object immutable. |
| “`volatile long` can tear like plain long.” | Volatile 64-bit read/write is atomic per JLS. |
| “`VarHandle.fullFence` makes `x++` atomic.” | A fence does not replace an atomic RMW. |
| “Just using volatile/atomic means no need to consider operation ordering.” | You still must design the proper protocol. |
| “The Java Memory Model is only a rule for HotSpot.” | The JMM is a Java language contract; every valid implementation must satisfy it. |

## 21. Self-Check Questions (With Answers)

**1.** How do atomicity, visibility, and ordering differ?  
**Answer:** Atomicity is about an operation executing as an uninterruptible unit per contract; visibility is about which written values another thread is allowed to see; ordering is about observed ordering relationships between actions.

**2.** Why is `count++` not atomic?  
**Answer:** It reads, computes, and then writes; two threads can both read the old value and write the same result, causing a lost update.

**3.** Is `volatile int count; count++;` right for a shared counter?  
**Answer:** No; use an atomic RMW like `AtomicInteger.incrementAndGet` or a critical section with the same lock.

**4.** What does volatile publication `payload=42; ready=true` require from the reader?  
**Answer:** `ready` must be volatile and the reader must read the flag and observe the published value under appropriate synchronization before reading payload, with no competing writes breaking the protocol.

**5.** Does `sleep()` guarantee thread A sees the writer's update?  
**Answer:** No. Sleep does not create the required HB edge.

**6.** Why do `synchronized(lockA)` and `synchronized(lockB)` not synchronize with each other?  
**Answer:** They guard different monitors; there is no unlock(lockA)→lock(lockB) synchronizes-with rule.

**7.** What does `AtomicityDemo` print upon completion?  
**Answer:** `synchronized=200000` and `atomic=200000`, thanks to atomic/synchronized increments and join.

**8.** Why does the main thread need `join()` before printing?  
**Answer:** To wait for completion and establish HB from thread actions to the observation after join.

**9.** Can `VolatileMessage` cause the reader to see ready=true but an old payload?  
**Answer:** No under the lesson's protocol with a single writer and no competing writes: volatile HB publishes payload=42.

**10.** Are two volatile fields `x`/`y` an atomic snapshot?  
**Answer:** No; use a lock or an immutable object published via a single volatile reference.

**11.** Is a plain `long` read/write always portable 64-bit atomic?  
**Answer:** Not guaranteed under JLS `17.7`; volatile long read/write is guaranteed atomic.

**12.** Does a `final int[]` make the array elements immutable?  
**Answer:** No, the reference does not change, but the contents can still be mutable and racy.

**13.** Does CAS completely eliminate the ABA problem?  
**Answer:** No; A→B→A can allow a CAS expecting A to still succeed.

**14.** Do acquire/release and plain VarHandle modes have the same semantics?  
**Answer:** No; release/acquire provide ordering that plain does not.

**15.** Does the statement “all executions of a correctly synchronized program appear sequentially consistent” make a multi-step invariant atomic?  
**Answer:** No; multi-step logic needs its own critical section/atomic grouping.

## 22. Official References

- [Java Language Specification SE 17 — Chapter 17 Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): especially **§17.4** JMM, §17.4.4 synchronization order, §17.4.5 happens-before, §17.5 final-field semantics, §17.7 non-atomic treatment of double/long.
- [Java SE 17 — `java.util.concurrent` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html): concurrent utility memory consistency effects.
- [Java SE 17 — `AtomicInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic increment/CAS and memory effects.
- [Java SE 17 — `AtomicLong`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html): atomic 64-bit values.
- [Java SE 17 — `LongAdder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): high-contention counters and non-atomic `sum()` under concurrent updates.
- [Java SE 17 — `CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): blocking handoff and memory consistency effect.
- [Java SE 17 — `Thread`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `start`, `join`, `interrupt`, and `onSpinWait`.
- [Java SE 17 — `VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): Plain/Opaque/Acquire/Release/Volatile access modes, CAS, and fences.
- [Java SE 17 — `Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): task execution and memory consistency after `get()`.
- [Java SE 17 — `ReentrantLock`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): explicit lock with memory synchronization semantics.
- [OpenJDK JSR 133 — Java Memory Model FAQ](https://www.cs.umd.edu/~pugh/java/memoryModel/jsr-133-faq.html): explanatory foundational document; prefer the current JLS when determining exact rules.

**Remember:** When multiple threads share mutable state, **atomicity** determines whether operations can interleave, **visibility** determines how one thread observes another thread's data, and **ordering** determines the constraints on operation reordering/observation. Java connects them via **happens-before**. `volatile` is suitable for publication flags and independent ordered reads/writes, but **does not turn `++` into an atomic operation**. `synchronized`/`Lock` protect critical sections and invariants; atomic classes/CAS provide atomic operations; `start`/`join`/latches/queues have memory-consistency effects. Designing the right protocol and reading the API contract is more important than guessing CPU execution order.