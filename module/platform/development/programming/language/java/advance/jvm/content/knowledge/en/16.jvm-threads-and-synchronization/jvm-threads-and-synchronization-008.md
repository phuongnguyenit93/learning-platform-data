# Happens-before relationships via locks, volatile, start, and join

**Happens-before (HB)** is an ordering relationship defined by the **Java Memory Model (JMM)** to explain when the operations of one thread must be correctly observed by another thread. It is especially important when multiple threads access the same mutable state: one thread writes data, another thread reads data; without the necessary synchronization relationships, the program may observe **stale values**, unexpected ordering, or different results across runs.

Four core mechanisms:

- **Monitor locks (`synchronized`):** an **unlock** on monitor `m` happens-before every **subsequent lock** on the **same monitor** in synchronization order.
- **`volatile`:** a **write** to volatile variable `v` happens-before **subsequent reads** of the **same variable `v`** in synchronization order.
- **`Thread.start()`:** a call to `start()` on thread `t` happens-before any action in the started thread `t`.
- **`Thread.join()`:** all actions of thread `t` happen-before an action in another thread that **detects that `t` has terminated**, such as when `join()` completes successfully because the thread has terminated.

These rules, combined with **program order** within each thread and **transitivity**, form a happens-before network. **Happens-before does not mean "runs earlier by wall-clock time", "all operations are automatically atomic", or "the scheduler will run the thread immediately".** It is a contract about **valid ordering/visibility between actions**, not a real-time execution schedule.

Scope of this article: Java SE 17+ and the official Java Memory Model. CPU cache details, fences, and HotSpot/JIT can help visualize things, but **do not replace the rules of the JLS**.

## 1. Why is the Java Memory Model needed?

For example, suppose there are two threads:

```java
// Pseudocode placed in the same class.
int data = 0;
boolean ready = false;

// Writer thread:
data = 42;
ready = true;

// Reader thread:
if (ready) {
    System.out.println(data);
}
```

If `data` and `ready` are ordinary fields, there is a **data race** because threads access the same fields, at least one access is a write, and there is no HB ordering between the conflicting accesses. A programmer relying only on source code order might easily think: "If the Reader sees `ready == true`, then surely `data == 42`." **That conclusion is not guaranteed by the JMM** for this racy program.

What can happen under the JMM/JIT/runtime:

- The Reader has not yet seen `ready` change and takes the false branch.
- The Reader may see `ready == true` but still see a `data` value not as intended for publication due to missing synchronization.
- A non-volatile `while (!ready) {}` loop may never terminate; the JIT may validly hoist/cache reads under an execution lacking HB.
- The result may be "correct millions of times" on your machine and still be **unsafe in terms of Java semantics**.

One should not simply explain that "the CPU always executes those exact two lines out of order." The JMM allows many ways of executing/observing when synchronization is missing; the cause may involve compiler optimizations, memory hierarchy, visibility, or valid reorderings. **The criterion to check is HB**, not just a CPU cache diagram.

### Foundational terminology

| Term | Meaning |
| --- | --- |
| **Action** | An operation in the JMM model: read/write, lock/unlock, volatile access, thread actions... |
| **Program order (po)** | The order of actions performed by a single thread according to program semantics |
| **Synchronization order (so)** | A total order of synchronization actions, consistent with the program order of each thread |
| **Synchronizes-with (sw)** | A synchronization edge across threads or between actions defined by the JMM |
| **Happens-before (hb)** | A relation comprising program order, synchronizes-with, and transitivity |
| **Data race** | Two conflicting accesses to the same variable, at least one a write, not ordered by HB |
| **Correctly synchronized program** | No data races in sequentially consistent executions; the JMM guarantees sequential consistency according to the relevant theorem |
| **Safe publication** | Publishing an object/state so that another thread sees the necessary initialization writes according to proper HB rules |

**Remember:** a program with a data race does not necessarily crash; it may produce the right output in most experiments. That does not turn a program without HB into a safe program.

## 2. How is the happens-before relationship constructed?

The Java Language Specification, **JLS `17.4.4–`17.4.5**, defines synchronization and happens-before edges.

### 2.1. Program order within the same thread

If action `A` precedes `B` in the program order of a single thread, then:

```text
Thread T:
   A  ──program-order──►  B

hb(A, B)
```

This does not force the CPU to execute every machine instruction in the exact apparent order of the source code. The compiler/CPU may reorder while **preserving semantics according to the JMM**. Program order is a component of the HB relation, not a timestamped log of every hardware micro-operation.

### 2.2. Synchronizes-with via synchronization actions

Certain pairs of actions are recognized by the JMM as having a `synchronizes-with` edge:

- Monitor **unlock → subsequent lock** of the same monitor.
- Volatile **write → subsequent read** of the same volatile variable.
- Thread start action → first action of the started thread.
- Final action of a thread → action in another thread that detects the thread has terminated (for example, via `join`/`isAlive`).
- There are other cases such as interrupt detection and default initialization, but this article focuses on the four main mechanisms.

A `synchronizes-with` edge creates a `happens-before` edge. It is then combined with program order and other HB edges.

### 2.3. Transitivity

If `hb(A, B)` and `hb(B, C)`, then `hb(A, C)`.

```text
Writer                Synchronization          Reader
data = 42         →   ready = true       →    sees ready == true
                                                │
                                                ▼
                                             reads data
```

This diagram **only has a guarantee** if `ready` is published/consumed via an appropriate synchronization mechanism, such as `volatile`, and the reader actually reads the value `true` from a published state. In that case:

1. `data = 42` is before the volatile write in program order.
2. The volatile write synchronizes-with the subsequent volatile read.
3. The volatile read is before reading `data` in program order.
4. Transitivity places the write to `data` before the read of `data` in HB.

With **a single writer and no competing writes to `data`**, a reader that sees `ready` in the published state will see `data == 42`.

### 2.4. HB is a partial order

Not every pair of actions from two arbitrary threads has an HB edge. If neither `hb(A, B)` nor `hb(B, A)` can be derived, the actions may **not be ordered by HB**. An observed result "A ran before B according to the log" does not by itself create an HB edge.

**Note:** `synchronized`, volatile, and thread lifecycle are mechanisms that create edges; `Thread.sleep()` and "hoping we waited long enough" do not by themselves create HB.

## 3. Visibility, ordering, and atomicity are three different things

| Aspect | Question | Example |
| --- | --- | --- |
| **Visibility** | Does thread B see the value validly published by thread A? | Reader sees `payload == 42` after volatile flag |
| **Ordering** | Are actions guaranteed to appear in the required relationship? | Write payload HB reader read payload |
| **Atomicity** | Is a multi-step operation executed as a single indivisible operation with respect to competing threads? | `counter++` is **not** atomic even if counter is volatile |
| **Mutual exclusion** | Are two threads prevented from entering the critical section at the same time? | `synchronized` on the same monitor prevents that |

**Volatile provides visibility/ordering for the relevant accesses; it does not make a read-modify-write (`++`) atomic.**

**Monitor locks provide mutual exclusion and HB via unlock/lock**, but only when **every access that needs protection follows the same protocol**; a writer using a lock while a reader reads outside the lock will not automatically receive the same guarantee.

## 4. Happens-before via monitor lock (`synchronized`)

`synchronized` uses an **object monitor**. When a thread enters a synchronized block, it acquires the monitor; when it exits the block normally or via an exception, it releases the monitor according to JVM semantics.

```java
final class LockedState {
    private final Object monitor = new Object();
    private int value;

    void write(int newValue) {
        synchronized (monitor) {
            value = newValue;
        }
    }

    int read() {
        synchronized (monitor) {
            return value;
        }
    }
}
```

This is a valid Java class without `main`. If thread A completes `write(42)` before thread B acquires **the same monitor** to call `read()`, then:

```text
Thread A                          Thread B
lock(m)
value = 42
unlock(m)  ──synchronizes-with──► lock(m)
                                    read value
                                  unlock(m)
```

`unlock(m)` happens-before subsequent `lock(m)`; by program order/transitivity, the write to `value` before the unlock happens before the read in the subsequent critical section. With no other competing writer intervening, the reader will see **42**.

### 4.1. It must be the same monitor

**Wrong** example:

```java
void wrong(int newValue) {
    synchronized (new Object()) {
        shared = newValue;
    }
}
```

This is an illustrative method; `shared` is a field in a hypothetical class. Each `new Object()` creates a separate monitor, **not** the same lock across calls. A writer and reader synchronizing on different monitors will not automatically create the required unlock/lock pair.

Similarly, a `synchronized` method on instance A uses monitor `A`, while a `synchronized` method on instance B uses monitor `B`. Two different instances **are not the same lock**. `static synchronized` uses the monitor of the **Class object**, which is also different from an instance monitor unless specially designed.

### 4.2. A lock does not automatically protect a field read outside the lock

```java
synchronized (monitor) {
    shared = 42;
}
// Another thread reads shared without using monitor or
// another valid synchronization mechanism: missing required HB.
```

This is a snippet in a class with `monitor` and `shared`. The lock protocol must be **consistently followed** by the threads. Just because one thread uses `synchronized` does not mean all plain reads by all other threads will see the new value.

### 4.3. `synchronized` supports compound updates

```java
final class SafeCounter {
    private int count;

    synchronized void increment() {
        count++;
    }

    synchronized int get() {
        return count;
    }
}
```

Here `increment()`/`get()` lock **the same instance**; two threads cannot simultaneously execute `count++` on the same monitor. Therefore, there are no lost updates if all accesses follow the protocol, and reading `get()` is also safe.

`synchronized` does not make Java code "sequential across the entire process"; it only excludes competing threads **on the same monitor** within the corresponding critical sections.

### 4.4. Reentrant monitors and exceptions

Java monitors are **reentrant**: a thread holding a monitor can lock that monitor again without deadlocking itself. The monitor is automatically released when a synchronized block exits due to an exception, but **partially updated state is not automatically rolled back**. HB is not a transaction mechanism. If invariants require updating multiple fields together, design the critical section so readers do not observe intermediate state.

## 5. Happens-before via volatile

A field declared `volatile` has its own memory-consistency guarantees:

```java
final class Message {
    int number;
    String text;
    volatile boolean ready;
}
```

A writer:

```java
message.number = 42;
message.text = "OK";
message.ready = true; // volatile write
```

A reader:

```java
if (message.ready) {  // volatile read
    System.out.println(message.number);
    System.out.println(message.text);
}
```

The snippets above are inside methods with a validly declared/passed `message` variable. Assuming **a single publisher**, a reader observing `ready == true`, and no concurrent writers modifying `number/text`, the reader must observe **42 and "OK"**. The reason is not that the two fields became volatile; they are still **plain fields**, but they were **published before the volatile write** and **consumed after the volatile read**.

### 5.1. HB diagram for volatile publication

```text
WRITER THREAD                         READER THREAD

number = 42                            if (ready) {  // volatile read
text = "OK"                                read number
ready = true  // volatile write              read text
                                            }
   │                                       ▲
   └──── volatile synchronizes-with ──────┘

program order + sw + transitivity:
write number/text HB read number/text
```

**Condition:** `ready` must be **the same volatile variable**. Writing `flagA` while the reader reads `flagB` does not create the corresponding edge just because both are volatile.

### 5.2. Reversing the write order can break the guarantee

**Wrong:**

```java
message.ready = true; // published too early
message.number = 42;
```

The reader may see `ready == true` and then read `number` before the writer has performed the write. Volatile **does not move a write that appears after it in program order backward in time** so that the reader is guaranteed to see it.

**Publication rule:** initialize the required shared state **before** the release action, and the consumer reads the release/ready signal **before** reading the plain fields.

### 5.3. A volatile field does not make the object graph "volatile everywhere"

```java
volatile int[] values = new int[4];
```

Only the **reference field `values`** is volatile. `values[0]` does not automatically become a volatile array element. If threads concurrently update individual elements without a synchronization protocol, a data race can still occur. Swapping the array reference after initialization via a volatile write is a publication mechanism; modifying array contents after publication requires its own synchronization rules.

### 5.4. Volatile has no mutual exclusion

```java
volatile int counter;

void increment() {
    counter++;
}
```

This is a snippet in a class. `counter++` consists of read → add → write logic. Two threads can both read 5, both write 6, losing an update. Volatile **protects visibility and JMM orderings**, but **does not atomically serialize the entire read-modify-write**.

To count safely, use `synchronized`, `AtomicInteger.incrementAndGet()`, or a workload-appropriate structure such as `LongAdder` when only an aggregate counter is needed.

## 6. Happens-before via `Thread.start()`

`Thread.start()` creates an HB edge **from the start action to every action of the new thread**. Importantly, writes **before** calling start are guaranteed to be visible to the child's code.

```java
final class StartExample {
    static int value;

    public static void main(String[] args) throws InterruptedException {
        value = 17;
        Thread child = new Thread(() -> {
            System.out.println("child sees: " + value);
        });

        child.start();
        child.join();
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 StartExample.java
java StartExample
```

**Exact standard output:**

```text
child sees: 17
```

Diagram:

```text
MAIN THREAD                  CHILD THREAD

value = 17
child.start()  ────────────► read value
                            print 17

main program order + start sw:
write value HB child read
```

**`value` does not need to be volatile in this example**, because publication occurs via **`start()`**. A newly started thread does not automatically have a guarantee of seeing plain writes from main **after** main has called `start()`, unless there is another HB edge.

### 6.1. `new Thread(...)` does not replace `start()`

Creating a `new Thread(...)` instance and holding its reference in a variable **does not** mean the child body has run or received a start edge. You must actually call `start()`; calling `run()` directly is just an ordinary method call on the calling thread and does not start a new OS/JVM thread via the Thread.start mechanism.

### 6.2. Start is one-way

```text
MAIN:     x = 1; start(child); x = 2;
CHILD:                       read(x)
```

`x = 1` HB child read thanks to `start`. However, `x = 2` after start **does not automatically** HB child read. If both main and child access plain `x` after start with at least one write, there may be a data race. **There is no guarantee whether child sees 2 or only sees 1** without other synchronization.

### 6.3. Do not confuse thread objects with task submission

`ExecutorService.submit()` has its own documented memory-consistency guarantees in `java.util.concurrent`. One should not interpret calling `run()` on a `Runnable` as equivalent to starting a thread, or assume every async framework uses the exact same `Thread.start/join` pair in user code. For executors/futures, use the API's actual contract instead of guessing the scheduler implementation.

## 7. Happens-before via `Thread.join()`

When thread `t` terminates and another thread **detects that termination** (specifically `join()` completes successfully), **all actions of `t` happen-before** the waiting thread's code after the detection point.

```java
final class JoinExample {
    static int answer;

    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> answer = 84);
        worker.start();

        worker.join();
        System.out.println("after join: " + answer);
    }
}
```

Run:

```bash
javac -encoding UTF-8 JoinExample.java
java JoinExample
```

**Exact standard output:**

```text
after join: 84
```

Diagram:

```text
WORKER THREAD                 MAIN THREAD

answer = 84
thread terminates
      │                         worker.join() completes
      └── termination detection ───────────► read answer
                                              print 84
```

`answer` does not need to be volatile when **the thread has been waited on to complete successfully** and there is no other competing writer. `join()` provides both **waiting for completion** (in its untimed form) and a **visibility guarantee** for the writes of the terminated worker.

### 7.1. `join` does not make a worker's computation atomic while running

If two workers both execute `plainCounter++` without a lock/atomic, and main calls `join()` on both before reading, main **sees the actual final result that was written**, but that result may **be missing increments** due to lost updates. HB from each worker to main **does not create mutual exclusion between the two workers**.

### 7.2. `join` with timeout does not guarantee the thread is dead

```java
worker.join(100); // wait at most about 100 ms
if (!worker.isAlive()) {
    // Detected worker termination; termination HB exists.
} else {
    // Worker may still be running; must not read plain fields
    // as if the worker has definitely finished.
}
```

This is a snippet inside a method; the actual wait duration also depends on the scheduler and JVM. **Do not** infer that because `join(100)` returned normally, the worker has finished. You must verify **termination**; calling `isAlive()` and observing `false` aligns with the detection rule described by the JLS.

### 7.3. `InterruptedException` while waiting

`join()` can throw `InterruptedException` if the waiting thread is interrupted. In that case, **do not assume the worker has terminated**; you must decide whether to retry, propagate, cancel, or restore the interrupt status according to the application contract. If main ignores the exception and then reads plain state, there is no basis to say `join` provided the termination edge the program intended to rely on.

### 7.4. Join is one-way in the opposite direction of Start

- `start`: actions **before start in the starter** are published to the **started thread**.
- `join`: actions **in the child before termination** are published to the **joiner after successful detection**.

Combining the two rules can create a two-way HB chain for a single data exchange, but they do not create live, bidirectional communication throughout the thread's lifetime.

## 8. Combined Java 17+ example: lock, volatile, start, and join

Create a single file **`HappensBeforeDemo.java`**:

```java
public class HappensBeforeDemo {
    static final class Box {
        int value;
        String text;
    }

    static final class Publication {
        int payload;
        int checksum;
        int observed;
        volatile boolean ready;
    }

    static final class Counter {
        private final Object monitor = new Object();
        private int value;

        void increment() {
            synchronized (monitor) {
                value++;
            }
        }

        int get() {
            synchronized (monitor) {
                return value;
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {

        // 1) Actions before start HB actions in the started thread.
        Box fromMain = new Box();
        fromMain.value = 11;
        fromMain.text = "prepared";

        Thread starter = new Thread(() -> {
            if (fromMain.value != 11
                    || !"prepared".equals(fromMain.text)) {
                throw new AssertionError("start visibility");
            }
        });
        starter.start();
        starter.join();
        System.out.println("start: " + fromMain.value
                + " / " + fromMain.text);

        // 2) Actions of the worker HB code after a successful join.
        Box fromWorker = new Box();
        Thread producer = new Thread(() -> {
            fromWorker.value = 22;
            fromWorker.text = "finished";
        });
        producer.start();
        producer.join();
        System.out.println("join: " + fromWorker.value
                + " / " + fromWorker.text);

        // 3) Volatile flag publishes two plain fields.
        Publication publication = new Publication();

        Thread observer = new Thread(() -> {
            while (!publication.ready) {
                Thread.onSpinWait();
            }
            publication.observed =
                    publication.payload + publication.checksum;
        });
        Thread publisher = new Thread(() -> {
            publication.payload = 30;
            publication.checksum = 12;
            publication.ready = true;
        });

        observer.start();
        publisher.start();
        publisher.join();
        observer.join();
        System.out.println("volatile: " + publication.observed);

        // 4) Same monitor makes read-modify-write atomic
        // for two writers coordinating through the lock.
        Counter counter = new Counter();
        Runnable incrementTask = () -> {
            for (int i = 0; i < 10_000; i++) {
                counter.increment();
            }
        };

        Thread first = new Thread(incrementTask);
        Thread second = new Thread(incrementTask);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("lock count: " + counter.get());
        System.out.println("done");
    }
}
```

### Compile/run

```bash
javac -encoding UTF-8 HappensBeforeDemo.java
java HappensBeforeDemo
```

**Standard output of the program when the threads are scheduled to run and complete normally:**

```text
start: 11 / prepared
join: 22 / finished
volatile: 42
lock count: 20000
done
```

**Progress note:** as with all concurrency examples, Java does not guarantee OS scheduler fairness or a deadline for a thread to always be run within X milliseconds. This volatile wait loop is illustrative, not a production design pattern (see section 14). When the threads make progress and terminate normally, the result **does not depend on any valid interleaving order**.

### Explaining why the output is stable

1. Main sets `fromMain.value=11` and `text="prepared"` **before** `starter.start()`. Start HB the child's reads; the child verifies the published values. Main joins before printing so validation is no longer running.
2. Worker writes `fromWorker.value=22` and `text="finished"` and then terminates. Main calls `join()`, which completes before reading the two fields. Volatile is not needed in this case.
3. Publisher writes **30** and **12** before the volatile write `ready=true`. Observer waits until a volatile read sees `true`, then reads the two plain fields. HB through volatile guarantees the sum **42**, because there is no other writer. Main calls `join()` on observer to read `observed` after observer has terminated.
4. Both writers use `counter.increment()`, locking **the same monitor**. Each read-modify-write increment cannot interleave inside the critical section, so **20,000 increments** are not lost. `join()` only ensures main waits for both writers; **the lock** is what prevents lost updates.
5. Each section is run sequentially in `main`, so the order of the println lines is also stable.

### A detail easily misunderstood in the example

In the volatile section, main also calls `join()`, and `join` has its own HB to main. **What demonstrates volatile publication is in the reader thread**, where observer waits for `ready` and then reads `payload/checksum`. If you removed volatile and relied only on main's join at the end, main could still see publisher's writes after join, **but observer reading payload earlier would lack the necessary synchronization edge**. These are two different points in time / pairs of reads.

In production, replace busy-wait with `CountDownLatch`, `BlockingQueue`, `Future`, or an appropriate notification mechanism when low-level spinning is not needed.

## 9. Why `volatile++` is still wrong: illustrating lost update

```java
final class BrokenCounter {
    volatile int value;

    void increment() {
        value++;
    }
}
```

If two threads execute `increment()` concurrently:

```text
Initial: value=5

Thread A           Thread B
read value=5       read value=5
add 1 → 6          add 1 → 6
write value=6      write value=6

Expected for two increments: 7
Possible result: 6
```

Individual volatile read/write operations have memory-consistency guarantees, but do not create an **atomic transaction** covering all three steps. A volatile write by A can be ordered with other volatile operations and still not guarantee that `value++` of A and B are completely separated.

### Approach 1: synchronized on the same monitor

```java
final class SynchronizedCounter {
    private int value;

    synchronized void increment() {
        value++;
    }

    synchronized int get() {
        return value;
    }
}
```

### Approach 2: AtomicInteger

```java
final class AtomicCounter {
    private final java.util.concurrent.atomic.AtomicInteger value =
            new java.util.concurrent.atomic.AtomicInteger();

    void increment() {
        value.incrementAndGet();
    }

    int get() {
        return value.get();
    }
}
```

`AtomicInteger.incrementAndGet()` uses an atomic read-modify-write per the API contract, with defined memory effects. This is the appropriate approach for a concurrent counter without complex constraints across multiple fields. For aggregate statistics under very high contention, `LongAdder` may be another option, though it is not a drop-in replacement if a consistent point-in-time read is required.

## 10. There is no HB between two plain fields just by "waiting long enough"

Example:

```java
final class UnsafeFlag {
    int result;
    boolean done;

    void produce() {
        result = 42;
        done = true;
    }

    int consume() {
        while (!done) {
            Thread.onSpinWait();
        }
        return result;
    }
}
```

This is a valid class but **lacks synchronization**; it should not be run as a test requiring guaranteed termination. `Thread.onSpinWait()` is a **performance hint to the JVM/CPU**; it does not create happens-before and does not make `done` volatile.

Similarly:

```java
Thread.sleep(100);
```

**Is not a memory synchronization primitive.** Calling sleep may give other threads CPU time to run, but the JMM does not define "Thread.sleep(100) happens-before reading a plain field from another thread" just because enough milliseconds passed.

### Println can hide bugs

`System.out.println()` in common implementations has synchronized I/O internals. If you insert println between two accesses, it may **change timing or introduce unintended extra synchronization**; bugs can easily disappear when logging is added.

The right approach: do not use logged output as proof that a program has safe HB. Analyze **the protocol the code actually relies on**, not accidental locks in diagnostic libraries.

## 11. Fixing a data-race flag properly

### Approach A: volatile flag

```java
final class VolatileFlag {
    int result;
    volatile boolean done;

    void produce() {
        result = 42;
        done = true;
    }

    int consume() {
        while (!done) {
            Thread.onSpinWait();
        }
        return result;
    }
}
```

With **a single writer**, if the reader observes `done == true` and there are no other concurrent writes to `result`, volatile HB makes `consume()` return **42**. However, the spin loop consumes CPU, lacks a scheduling liveness guarantee, and does not handle cancellation/timeouts; this is still **not the default production pattern**.

### Approach B: monitor condition

```java
final class MonitorFlag {
    private int result;
    private boolean done;

    synchronized void produce() {
        result = 42;
        done = true;
        notifyAll();
    }

    synchronized int consume() throws InterruptedException {
        while (!done) {
            wait();
        }
        return result;
    }
}
```

`wait()` must be called while the thread holds the corresponding monitor; it releases the monitor while waiting and must reacquire it before returning. `notifyAll()` does not immediately yield the lock: the producer must exit the synchronized method/monitor before the consumer can reacquire it.

**Always use `while` to re-check the condition**, due to spurious wakeups and state changes by other threads. The monitor unlock/lock pair also creates the required HB.

### Approach C: CountDownLatch

```java
import java.util.concurrent.CountDownLatch;

final class LatchFlag {
    private int result;
    private final CountDownLatch ready = new CountDownLatch(1);

    void produce() {
        result = 42;
        ready.countDown();
    }

    int consume() throws InterruptedException {
        ready.await();
        return result;
    }
}
```

This is a syntactically runnable class without `main`; it uses a high-level concurrency API. According to the API, actions before `countDown()` happen-before actions after a corresponding successful `await()`, so `result` is safely published.

**Do not mix up mechanisms:** a latch has its own memory-consistency effects; there is no need to add volatile to `result` just because it is read by another thread after a successful await (provided there are no other competing writes).

## 12. Happens-before does not mean "every plain read always sees the last write by wall clock"

The JMM uses the HB relation and validity rules to determine which writes a read can see. With multiple writers:

```java
int data; // shared

// Thread A:
data = 1;

// Thread B:
data = 2;

// Thread C:
int observed = data;
```

This is a conceptual example with no synchronization described between A, B, and C. One cannot use wall-clock timestamps, which logger printed first, or assumptions about CPU execution order to determine a portable result for `observed`.

Even if C has HB from A, if B writes `data` without being validly ordered with C, the program still has another conflict/data race that can prevent the read value from being determined by "A just published 1." **All conflicting writes must be considered**, not just one desired edge.

### How to reason about a correct protocol

1. Identify **all shared variables**.
2. Identify **all writes** to them and which threads can write.
3. Identify the **publication/release** action.
4. Identify the **observation/acquire** action that actually occurs.
5. Connect program order + synchronizes-with into an HB path.
6. Check if any **competing unordered writes** break determinism.
7. Check atomicity if the code reads/modifies multiple fields.
8. Check whether threads actually terminate/run under liveness conditions.

## 13. Happens-before and memory reordering

Classic example:

```java
int x = 0;
int y = 0;
int r1;
int r2;

// Thread A:
x = 1;
r1 = y;

// Thread B:
y = 1;
r2 = x;
```

This is pseudocode of actions in a two-thread class, **not a standalone runnable program**. When two threads execute without HB linking the accesses, **the result `r1 == 0 && r2 == 0` is allowed by the JMM** in the classic store buffering problem. That does not mean every run will return 0/0.

### Why a 0/0 result does not necessarily mean "the CPU is wrong"?

There is no cross-thread HB forcing Thread A to see B's write before reading `y`, nor any cross-thread HB forcing B to see A's write before reading `x`. The JMM preserves intra-thread semantics and validity conditions, but a data-racy execution does not automatically have sequential consistency.

**The right fix** depends on the logical requirement:

- If each thread needs to see an event from the other thread, use volatile flags or a synchronization protocol.
- If the state exchange needs to be atomic, use a lock or an appropriate atomic class.
- If you only need to collect results after both finish, the caller calls `join()` on both threads and reads then; however, join does not make reads performed while they were running without HB safe.

### Volatile changes the problem

Changing `x` and `y` to volatile fields adds synchronization order/visibility constraints. With **both variables volatile**, the 0/0 case of the store-buffering pattern above is no longer consistent with a total volatile order consistent with program order; however, other valid interleavings remain, and that logic should not be used to infer an atomic transaction across multiple fields.

## 14. Thread lifecycle and execution progress pitfalls

HB says **if a valid observable event occurs**, then ordering/visibility is guaranteed. It **does not guarantee** that the event will occur within 100 ms or that every thread will be scheduled fairly.

### 14.1. What is wrong with busy-wait?

```java
while (!ready) {
    Thread.onSpinWait();
}
```

If `ready` is volatile, the loop has appropriate visibility semantics when the writer publishes. However, it can:

- Consume CPU if waiting for a long time.
- Lack timeout/cancellation.
- Run infinitely if the writer never publishes due to a logic bug.
- Be delayed by CPU quota/OS scheduling.
- Be unsuitable for most I/O-bound services.

Usually prefer `CountDownLatch`, `BlockingQueue`, `Condition`, `CompletableFuture`, or an appropriate blocking primitive.

### 14.2. `join(timeout)` vs `join()`

Untimed `join()` waits for the thread to terminate unless interrupted or another valid error occurs. `join(timeout)` **can** return when the time expires; you must check for termination before relying on the completion edge.

Example:

```java
worker.join(200);
if (worker.isAlive()) {
    // Timed out or worker has not terminated yet:
    // cannot assume final state has been received via join.
} else {
    // Detected that worker terminated.
}
```

### 14.3. InterruptedException does not mean the child terminated

A thread calling `join` or `wait` can be interrupted. Exception signaling has its own HB semantics related to interrupt detection, but **does not** automatically cause the worker to terminate. Do not swallow the exception and then read plain fields as if a successful join had occurred.

### 14.4. Deadlock despite `synchronized`

`synchronized` creates mutual exclusion and HB edges; it **does not guarantee** the system avoids deadlocks:

```text
Thread A holds lock1, waits for lock2.
Thread B holds lock2, waits for lock1.
```

That is a lock wait cycle. HB rules only speak about the ordering of actions that have occurred or can occur; they do not create progress when threads are deadlocked.

## 15. Safe publication of objects: not just boolean flags

An object with multiple fields needs safe initialization before another thread uses it:

```java
final class Config {
    final String host;
    final int port;

    Config(String host, int port) {
        this.host = host;
        this.port = port;
    }
}
```

**Final fields** have their own initialization safety rules in the JMM if the object is constructed properly (not allowing `this` to escape during construction), but one should not invoke final fields to justify a protocol that accesses mutable shared state without synchronization.

### Publishing a reference via volatile

```java
final class Holder {
    private Config config; // plain field

    private volatile boolean ready;

    void publish() {
        config = new Config("localhost", 8080);
        ready = true;
    }

    Config await() {
        while (!ready) {
            Thread.onSpinWait();
        }
        return config;
    }
}
```

This is an example class that compiles without `main`. After a volatile read sees `true`, the reader has HB from the actions before the volatile write, so the previously published `config` is validly seen. Do not turn this spin-wait example into a production library; use high-level primitives if blocking/cancellation is desired.

### A volatile reference is simpler than a separate flag

```java
final class VolatileConfig {
    private volatile Config config;

    void publish(Config next) {
        config = next;
    }

    Config snapshot() {
        return config;
    }
}
```

With construction completed before the volatile write, a reader receiving a non-null `config` via a volatile read has **safe publication** of the state prepared before publishing. However, **mutable fields modified after publication** still require separate synchronization.

### Escaping from a constructor is a different problem

If a constructor publishes `this` before initialization is complete, another thread may observe a partially constructed object; **final-field semantics also have limitations in `this` escape situations**. Do not try to solve this merely by adding `final` everywhere while still publishing the object too early.

## 16. Double-checked locking and volatile

Traditional lazy singleton pattern:

```java
final class LazyService {
    private static volatile LazyService instance;

    private LazyService() {
    }

    static LazyService get() {
        LazyService local = instance;
        if (local == null) {
            synchronized (LazyService.class) {
                local = instance;
                if (local == null) {
                    local = new LazyService();
                    instance = local;
                }
            }
        }
        return local;
    }
}
```

**This is a valid class under Java 17.** In this double-checked locking pattern, the volatile reference serves as **safe publication** on the lock-free fast path.

Why is `volatile` needed?

- The constructor completes before the volatile write `instance = local` in the relevant program order.
- A reader reading a non-null `instance` via a volatile read has HB to the published writes.
- The lock on the slow path prevents multiple threads from creating instances in an uncontrolled manner.
- Reading into a local variable first makes the logic clear, using only the instance that was read; the second check under the lock prevents duplicate construction.

**This does not mean** every singleton needs DCL: the **initialization-on-demand holder idiom** or static initialization is often simpler. And if `LazyService` has mutable fields updated by threads after construction, singleton publication does not by itself resolve races on those fields.

## 17. ReentrantLock and concurrency utilities create memory-consistency edges

Many APIs in `java.util.concurrent` provide similar effects or build on the JMM:

| API | High-level memory-consistency contract |
| --- | --- |
| `ReentrantLock` / `Lock` | Successful `lock/unlock` has memory synchronization semantics like the corresponding monitor lock/unlock |
| `CountDownLatch` | Actions before `countDown()` HB actions after the corresponding successful `await()` |
| `Future.get()` | Actions performed by the asynchronous computation HB actions after the corresponding successful `get()` |
| `ExecutorService` | Actions before submitting a task HB actions in the task; task actions HB after `Future.get` |
| `BlockingQueue` | Actions before placing an object into the queue HB actions after the consumer retrieves the corresponding object |
| `ConcurrentHashMap` | APIs have documented memory effects; visibility for specific access patterns |
| Atomic classes | Atomic operations and memory effects per contract (`get`/`set`/CAS...) |

**Always read the specific API contract**, because there are methods that fail/timeout/cancel and weaker access modes such as `lazySet`, `getAcquire`, `setRelease`, and `getOpaque` in `VarHandle`/`Atomic*` APIs. There is no rule saying "every method on concurrent classes creates a global happens-before."

### Lock API vs. synchronized

```java
import java.util.concurrent.locks.ReentrantLock;

final class LockCounter {
    private final ReentrantLock lock = new ReentrantLock();
    private int value;

    void increment() {
        lock.lock();
        try {
            value++;
        } finally {
            lock.unlock();
        }
    }

    int snapshot() {
        lock.lock();
        try {
            return value;
        } finally {
            lock.unlock();
        }
    }
}
```

This is a compilable class without `main`. `try/finally` is important to always unlock. A correct protocol requires both writes and reads accessing `value` to coordinate on the same lock; `ReentrantLock` adds capabilities like `tryLock`/`lockInterruptibly` but is not "automatically better than" `synchronized` in every respect.

## 18. `wait/notifyAll` is not just "sending a notification"

Many learners write:

```java
synchronized (monitor) {
    monitor.notifyAll();
}
```

and think the waiting thread immediately resumes running. In reality:

1. The thread calling `wait()` must own the monitor.
2. `wait()` releases the monitor and waits according to JMM/`Object.wait` rules.
3. The thread calling `notify/notifyAll` must also own the monitor.
4. Notification makes one or more waiters **eligible to wake up**, but they need to **reacquire the monitor**.
5. The producer may still hold the monitor after notify until it exits the synchronized block.
6. The waiter must re-check the condition in a **`while` loop**, due to spurious wakeups or state changes.

**Do not rely on notify without a condition variable/state**. A notification can be sent before a thread starts waiting, leading to a missed signal if the protocol does not maintain state properly. With a flag read/written under the same monitor, the unlock/lock pair and condition loop make the protocol much more solid.

## 19. Race risks remain if synchronized at the wrong scope

### 19.1. Two different locks

```java
final Object lockA = new Object();
final Object lockB = new Object();
int state;

// Writer:
synchronized (lockA) {
    state = 123;
}

// Reader:
synchronized (lockB) {
    System.out.println(state);
}
```

This is an illustrative snippet in a class. `unlock(lockA)` **does not** synchronize-with `lock(lockB)` just because both are monitors. Without another HB edge, accesses to `state` may be racy.

### 19.2. One volatile field, multiple fields needing an invariant

```java
volatile int left;
volatile int right;
```

If a writer updates two fields and a reader needs to see them as **an atomic pair**, volatile is **not enough**. A reader can observe a pair consisting of one new write and one old write at a valid interleaving point. Use a monitor or publish an **immutable snapshot** through a volatile reference when an invariant across multiple fields must be preserved.

### 19.3. CAS protects one location, not the entire object graph atomically

`AtomicReference.compareAndSet(expected, update)` is atomic for the reference update per the API, but it does not turn unsynchronized writes to the referenced object's fields into a transaction. Concurrent state design should distinguish **atomic publication of a reference** from **atomic mutation of contents**.

### 19.4. Locking around the writer while the reader does not follow the protocol

The writer may lock properly; if the reader reads the field directly without locking and without volatile, the expected guarantee is still missing. You must trace the complete **release-to-acquire chain for the read in question**, not just mark one place with the `synchronized` keyword.

## 20. A clear HB reasoning recipe

When given a piece of Java concurrency code, do not guess by timing. Build an action table:

| Thread | Action | Kind |
| --- | --- | --- |
| T1 | `x = 7` | Plain write |
| T1 | `ready = true` | Volatile write |
| T2 | `if (ready)` | Volatile read |
| T2 | `r = x` | Plain read |

Assuming T2 actually sees `ready == true` from T1's publication (and no other writer interferes):

```text
T1: write x = 7
       │ program order
       ▼
T1: volatile write ready = true
       │ synchronizes-with
       ▼
T2: volatile read ready == true
       │ program order
       ▼
T2: plain read x

Conclusion: hb(write x, read x).
If there is no other conflicting write: r == 7.
```

### Step-by-step reasoning checklist

1. List the shared **objects and variables**.
2. Identify **which threads write**, **which threads read**, and the logical timing.
3. Find **program order** edges in each thread.
4. Find **synchronizes-with** edges: same monitor, same volatile variable, `start`, termination detection.
5. Chain edges by **transitivity**.
6. Check **all conflicting accesses**: is there any unordered writer?
7. Identify what is being guaranteed: **visibility**, **ordering**, **atomicity**, or **progress**?
8. For wait loops, check **liveness**, interrupts, timeouts, and cancellation.
9. Do not interpret logging output or `sleep` as nonexistent JMM edges.
10. If results are complex, use stress testing and cross-check against the official JLS.

## 21. JCStress and testing: what can be tested?

**JCStress** is OpenJDK's concurrency testing harness dedicated to testing outcomes of concurrent actors; it is useful when studying JMM litmus tests or finding very subtle race conditions. However:

- An outcome not appearing after millions of iterations **does not prove** the JMM forbids it.
- An outcome appearing may be a signal of a synchronization/protocol bug; the test definition must be checked.
- VM flags, JIT warm-up, OS/CPU/architecture, and test structure can change the set of observed outcomes.
- Do not write unit tests that depend on "a data race will definitely fail after N runs."
- Do not add println or sleep to the critical path and treat it as still measuring the same litmus test.

**Common flawed experiment:** asserting that a plain-field spinning loop must exit within 100 ms. That it exits once may be due to timing or unoptimized compiled code, and does not create a portability guarantee.

### ThreadSanitizer, profilers, and runtime tools

Diagnostic/profiler tools can help find contention, thread states, or data races depending on the JDK/build. However, **JFR, `jstack`, `jcmd Thread.print`** primarily provide a runtime view and **do not replace JMM analysis**. Race detection support and false positives/negatives depend on the tool; use the right supported tools on the running environment.

## 22. Common misconceptions

| Misconception | Reality |
| --- | --- |
| "Happens-before means action A runs earlier by wall-clock time." | It is a JMM relation for ordering/visibility, not a physical timeline |
| "Any two actions in any two threads are always ordered by HB." | HB is a partial order; there may be no edge |
| "`Thread.sleep` is enough to publish plain fields." | Sleep does not create an HB edge |
| "`Thread.onSpinWait` makes a field volatile." | It is only a hint, adding no JMM synchronization |
| "`volatile` makes `counter++` atomic." | Read-modify-write can still suffer lost updates |
| "A volatile flag publishes only the flag itself." | Writes before the release can be published via transitivity |
| "Putting volatile on an array reference makes every element volatile." | No; elements need their own protocol |
| "A write to one volatile var HB a read of any volatile var." | The sw rule requires **the same volatile variable** |
| "`synchronized(lockA)` synchronizes with `synchronized(lockB)`." | Different monitors do not create the corresponding unlock/lock edge |
| "Only the writer using synchronized is enough." | The reader must follow the protocol or have another valid HB edge |
| "`start()` publishes all writes of the starter, even after start." | The start edge guarantees writes before start; after start needs its own mechanism |
| "`new Thread` means the thread is already running." | You must call `start()` |
| "Calling `run()` directly creates a new thread." | No, it is just an ordinary method call |
| "`join(timeout)` returning means the child is dead." | It may have timed out; termination detection is needed |
| "`join` protects two workers from lost increments." | Join only orders with the joiner after completion; it does not serialize workers |
| "If the reader sees `ready=true` even when ready is plain, it surely sees the new payload." | Missing HB, not portable |
| "`notifyAll` immediately transfers monitor ownership to the reader." | The waiter needs to reacquire the monitor after the notifier unlocks |
| "`volatile` protects invariants across multiple fields." | Not like a transaction; use a lock or immutable snapshot |
| "Final fields mean the object is always safely published in every construction." | There are specific rules and limits when `this` escapes |
| "Seeing the right output on x86 means it is race-free." | A common observed outcome does not prove a JMM guarantee |
| "HB can fix a program that is broken in liveness/fairness." | Ordering does not guarantee scheduler progress |
| "Having GC/JIT logs lets you infer all HB edges." | Logs do not define the program synchronization protocol |

## 23. Exercises with answers

**Exercise 1.** Thread A writes `data=42`, then `ready=true` (volatile). Thread B reads `ready==true` then reads `data`. Single writer, no other updates. What does B see?  
**Answer:** `42`, because program order + volatile synchronizes-with + transitivity create HB.

**Exercise 2.** Writer writes `ready=true` first and then `data=42`. Reader sees `ready==true`. Is `data==42` guaranteed?  
**Answer:** No. The payload write comes after the volatile publication.

**Exercise 3.** Writer uses `synchronized(lockA)`, reader uses `synchronized(lockB)`. Is there an unlock/lock HB?  
**Answer:** No, if the two monitors are different and there is no other synchronization edge.

**Exercise 4.** Two threads each do `volatileCounter++` 1000 times, main joins both. Is the result always 2000?  
**Answer:** No. Lost updates can occur; `join` only waits and publishes the actual result, it does not make increments atomic.

**Exercise 5.** Does `AtomicInteger.incrementAndGet()` help?  
**Answer:** Yes, it provides an atomic increment per the Java concurrency API contract.

**Exercise 6.** Main writes `x=5` then `child.start()`; child prints `x`. Does `x` need to be volatile when there is no competing writer?  
**Answer:** No, start HB child actions.

**Exercise 7.** Main writes `x=5` **after** `child.start()`; child reads plain `x`. Does `start` automatically publish this write?  
**Answer:** No. A write after start lacks the start HB edge; appropriate synchronization is needed.

**Exercise 8.** Worker writes `result=10`; main calls `worker.join()`, which completes, then reads. Does `result` need to be volatile if there is no other writer?  
**Answer:** No, actions of the terminated thread HB code after a successful join.

**Exercise 9.** `join(100)` returns with `worker.isAlive()==true`; can main assume the worker has published its final result?  
**Answer:** No. The worker has not been detected as terminated.

**Exercise 10.** `join()` throws `InterruptedException`. Can it be ignored and state read as if join succeeded?  
**Answer:** No. There has been no successful termination detection as relied upon by the logic.

**Exercise 11.** A thread calls `run()` directly on a Thread object. Does it receive a start HB edge?  
**Answer:** There is no new-thread start event; it is an ordinary method call.

**Exercise 12.** Does the field `volatile int[] arr` make `arr[0]++` atomic?  
**Answer:** No. Volatile applies to the reference field, not automatically to array elements or composite updates.

**Exercise 13.** Can `wait()` return while the condition is still false?  
**Answer:** Yes, due to spurious wakeups or state changes; use `while (!condition) wait()`.

**Exercise 14.** Does `notifyAll()` make a waiter run immediately before the notifier unlocks?  
**Answer:** No. The waiter still needs to reacquire the monitor and be scheduled.

**Exercise 15.** Every run of a data race test prints the right output. Does that prove JMM correctness?  
**Answer:** No. HB analysis is needed, or stress testing only to find bugs, not to prove the absence of errors.

**Exercise 16.** Does `volatile` provide mutual exclusion like `synchronized`?  
**Answer:** No. It has ordering/visibility semantics, not critical section locking.

**Exercise 17.** The same monitor protects writer/reader, but the reader reads outside the lock in another path. Is that path automatically safe?  
**Answer:** No; HB must be checked for the actual read.

**Exercise 18.** An immutable object consisting of final fields is published via a volatile reference. Can the constructed state be read after the acquire read?  
**Answer:** Yes, with valid construction and publication; mutable fields updated afterward still need their own protocol.

**Exercise 19.** Is a DCL singleton without volatile safe under the Java 17 model?  
**Answer:** The classic double-checked locking pattern without volatile is unsafe for publication; use volatile or a class initialization approach.

**Exercise 20.** In `HappensBeforeDemo`, what does the `volatile:` line print?  
**Answer:** `volatile: 42` if the threads complete normally; volatile ready read as true publishes 30 and 12.

**Exercise 21.** In `HappensBeforeDemo`, what does the `lock count:` line print?  
**Answer:** `lock count: 20000` because two writers each increment 10,000 times under the same monitor.

**Exercise 22.** Threads A and B write plain `x=1`/`x=2` concurrently, C reads without synchronization. Can "which write ran last according to the log" be used to conclude what C sees?  
**Answer:** No; there is no sufficiently clear cross-thread HB, and logging can alter timing/protocol.

**Exercise 23.** Writer writes data then `CountDownLatch.countDown()`; reader succeeds in `await()` then reads data. Is there HB?  
**Answer:** Yes, per the memory-consistency contract of CountDownLatch.

**Exercise 24.** `Future.get()` returns the task result; is it necessary to also read a plain ready flag to ensure seeing writes from the task?  
**Answer:** Usually no; the Future API has a memory-consistency guarantee for actions of the asynchronous computation before actions after a successful get, per the Future contract.

## 24. Checklist before concluding a design is thread-safe

- [ ] List the shared mutable fields and all readers/writers.
- [ ] Are there any **data races**? If so, has it been determined why the outcome is still valid?
- [ ] If using a monitor, do all critical accesses lock **the same object**?
- [ ] If using volatile publication, are writes placed **before** the release write and reads after the acquire read?
- [ ] Are there competing writers or post-publication mutations that break determinism?
- [ ] Are there composite operations like `++`, check-then-act, or read-modify-write that need atomicity?
- [ ] Was `Thread.start()` actually called, or only `run()`?
- [ ] Do reads from the child properly depend on actions **before start**?
- [ ] Do reads from the joiner occur **after successful termination detection**?
- [ ] If using timed join, is it checked whether the child actually terminated?
- [ ] Is `InterruptedException` handled according to the application contract?
- [ ] Does the waiter check the condition using `while` under the same monitor?
- [ ] Is there a bounded wait, timeout/cancellation instead of an infinite spin where appropriate?
- [ ] Are high-level utilities used to avoid hand-rolling a signaling protocol when unnecessary?
- [ ] Are visibility/ordering distinguished from mutual exclusion/atomicity?
- [ ] Is using println, sleep, or debugger timing as proof of JMM correctness avoided?
- [ ] Are final-field construction rules and the risk of `this` escape understood?
- [ ] Is correctness tested against the specification rather than trusting a single stress outcome?
- [ ] Is JLS §17.4.5 used as the standard when reasoning about HB edges?

## 25. Summary: four paths to create HB to remember

```text
1) MONITOR
   T1: writes → unlock(m)  ---HB---> lock(m) → reads :T2

2) VOLATILE
   T1: writes → write(v)   ---HB---> read(v) → reads :T2
                 volatile              volatile

3) THREAD.START
   T1: writes → t.start()  ---HB---> actions in thread t

4) THREAD.JOIN / TERMINATION DETECTION
   Thread t: writes → termination  ---HB---> joiner
                                           after successful join

HB is transitive with program order.
No HB ≠ guaranteed to see stale value, but
also no guarantee of the desired visibility.
```

**Happens-before is a proof tool**, not a trick to make the CPU "flush cache." With locks, volatile, start, and join, the right question is always **"which action synchronizes with which action, and which writes does transitivity carry to which reads?"** Once you have drawn the HB path, you have a basis to talk about visibility; after that, you still need to check atomicity, competing writers, progress, and resource lifecycle.

### Standard references to cross-check

1. **Java Language Specification, Java SE 17, Chapter 17 — Threads and Locks:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html
2. **JLS §17.4.4 — Synchronization Order:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.4
3. **JLS §17.4.5 — Happens-before Order:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5
4. **Java SE 17 — Thread API, start/join/isAlive and interruptions:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
5. **Java SE 17 — java.util.concurrent package memory-consistency effects:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html
6. **Java SE 17 — CountDownLatch and Future API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html ; https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
7. **Java SE 17 — AtomicInteger:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
8. **OpenJDK JCStress project:** https://github.com/openjdk/jcstress

**Core takeaway:** `synchronized` creates HB via **the same monitor** and provides mutual exclusion; `volatile` creates HB via **the same variable** but does not make compound operations atomic; `Thread.start()` publishes the starter's writes to the child; `Thread.join()` publishes the terminated child's writes to the joiner. Use **program order + synchronizes-with + transitivity** to prove correctness, instead of hoping based on timing or cache behavior.