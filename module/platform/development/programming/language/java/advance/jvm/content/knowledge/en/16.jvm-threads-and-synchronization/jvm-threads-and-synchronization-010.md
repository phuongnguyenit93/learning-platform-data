# Operation Reordering, Data Races, and Guarantees That `Thread.sleep` Does Not Provide

## 1. Goal: Distinguishing “Looks Sequential” from “Guaranteed by Java”

Java runs on many different CPUs, JVMs, and JIT optimizers. If two threads access mutable state concurrently without proper synchronization, a program may observe results **different from the top-to-bottom source-reading intuition**, even while each thread still behaves according to the rules of the Java Memory Model (JMM).

Three concepts need to be distinguished:

1. **Reordering:** the compiler, JVM, or CPU may organize execution in an order different from the visible statement order, as long as the valid observations required by the memory model are preserved.
2. **Data race:** two operations access the same shared variable, at least one is a **write**, and there is no **happens-before** relationship ordering them. Racy outcomes can be unpredictable and are not protected by the usual sequential consistency model.
3. **`Thread.sleep` is not synchronization:** sleeping pauses a thread temporarily according to the scheduler; it **does not create a happens-before edge, does not force the JVM to flush/reload shared data, and does not release held intrinsic monitors**.

This lesson uses **Java 17**, based directly on **JLS `17.3`, `17.4`, `17.5`** and the `Thread` API. The examples clearly separate **runnable programs with deterministic stdout** from **litmus tests with non-deterministic outcomes**. Do not infer performance or memory guarantees from a single lucky execution on one machine.

## 2. Three Kinds of “Order” Often Confused

When reading:

```java
int a = 1;
int b = 2;
System.out.println(a + b);
```

This is a sequentially executed fragment. The compiler may optimize operations or keep values in registers, but the result must be equivalent to a correct program: printing `3`. For **a single thread**, Java respects **intra-thread semantics**: the observable result of the thread must match its own execution in program order (`as-if-serial` intuitively).

In **multi-threaded** programs, it is necessary to distinguish:

| Term | Role |
| --- | --- |
| **Source order** | The order in which code is laid out in `.java`; not always the order of machine instructions |
| **Program order** | The ordering relation of actions within **a single thread** according to the JMM |
| **Synchronization order** | A total order over **synchronization actions** in an execution, consistent with the program order of each thread |
| **Synchronizes-with** | Specific synchronization edges: volatile write→read, monitor unlock→lock, thread start/join, etc. |
| **Happens-before (HB)** | The ordering relation generated from program order and synchronizes-with (transitive) |
| **Wall-clock order** | The actual real-world time the scheduler lets threads run; by itself it does not define HB |

A claim like “A definitely runs before B in the real world because I called `sleep(100)`” is **not** proof of memory ordering. Wall-clock order predicted from delays cannot substitute for an HB relation.

### HB Is Not Just a Clock

Writing `hb(A, B)` means action A happens **before according to the JMM** action B: the appropriate visibility/ordering requirements apply. Chains can be formed:

```text
In Thread 1:
    A -> B (program order)

B synchronizes-with C in Thread 2

In Thread 2:
    C -> D (program order)

Therefore:
    hb(A, D) by transitivity.
```

Without an edge connecting the two threads, merely making one thread `sleep` longer than the other cannot build that HB path.

## 3. Shared Memory: Which Variables Can Fall Into a Data Race?

JLS `17.4.1` treats **instance fields, static fields, and array elements** as shared variables that can be accessed by multiple threads. Local variables reside in a thread's private frame and are not directly shared variables in that sense; however, local references can point to a **shared object**.

Example:

```java
static int counter;

static void increment() {
    counter++;
}
```

This is a fragment. If two threads call `increment` concurrently without synchronization:

- Both may read the same initial value.
- Each thread computes plus 1.
- Both write the result, causing a **lost update**.

The `counter++` operation consists of **read-modify-write** logic, not an atomic operation guaranteed by the JMM just because it is a single Java statement.

### A Tighter Definition of Data Race Than “Two Threads Running Together”

Two accesses **conflict** if they access the same variable and at least one is a write. A data race occurs when those conflicting accesses are **not ordered by happens-before**.

Having two threads touch an object is not always a data race:

- Both only **read** an immutable/safely published field: no conflicting write.
- Every access to shared state is consistently guarded by **the same intrinsic monitor**: proper synchronization exists.
- One thread writes before `Thread.start()` and the new thread reads after start: a specific HB edge exists.
- One thread completes, another thread successfully calls `join()` and then reads: an HB edge exists.

Conversely, code that “in practice never seems to happen concurrently” thanks to `sleep` does **not** constitute a valid synchronization protocol.

## 4. Reordering: Different Statement Order Yet Still Valid

The JLS gives a model example with two variables initially 0:

```text
Initialization: A = 0, B = 0

Thread 1:            Thread 2:
    r2 = A;              r1 = B;
    B = 1;               A = 2;
```

Without synchronization between threads, outcomes can occur that make readers think writes/reads “swapped order”. Compilers and CPUs are allowed to optimize as long as they obey the JMM, where **happens-before and causality constraints** forbid certain invalid executions.

**There does not need to be an actual moved assembly instruction** to observe surprising results. Many causes can contribute: the JVM optimizer swapping operation order when single-thread behavior is unaffected, hardware store buffers, visibility delays, and scheduler interleavings.

### Do Not Equate Source Instructions With Machine Instructions

An `int x = obj.value` in Java source may correspond to bytecode actions and machine instructions that vary by JIT tier. The compiler may inline, constant-fold, or keep data in registers when allowed. Conversely, a volatile access may enforce appropriate machine-level constraints that source `volatile` does not express as a fixed “single fence line”.

Therefore, reading `javap -c` only shows **class-file bytecode**; it does not prove that machine operations ran in a specific order.

## 5. Famous Litmus Test: Both Threads See 0

Suppose `x = y = 0` and each thread runs:

```text
Thread A:            Thread B:
    x = 1;               y = 1;
    r1 = y;              r2 = x;
```

**The result `r1 == 0 && r2 == 0` is an outcome permitted by the JMM** in this unsynchronized litmus test. It can happen even though each thread sees its own program run “correctly”, because **there is no HB** forcing each thread to see the other's write in time.

Do not conclude:

- Every run will produce `(0, 0)`.
- If you try a million times without seeing `(0, 0)`, the code is safe.
- The JVM necessarily swapped the two statements in the generated machine code.
- Any arbitrary pair of numbers is allowed. The JMM has constraints on source values, well-formed executions, and causality.

### Complete Java 17 Example: One Run With Non-Fixed Output

Create file **`ReorderingLitmus.java`**:

```java
public class ReorderingLitmus {
    static int x, y;
    static int r1, r2;

    public static void main(String[] args)
            throws InterruptedException {
        x = y = r1 = r2 = 0;

        Thread a = new Thread(() -> {
            x = 1;
            r1 = y;
        }, "A");

        Thread b = new Thread(() -> {
            y = 1;
            r2 = x;
        }, "B");

        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("r1=" + r1 + ",r2=" + r2);
    }
}
```

```bash
javac --release 17 ReorderingLitmus.java
java ReorderingLitmus
```

**Stdout is not uniquely deterministic**; for example, it might be:

```text
r1=0,r2=1
```

Another execution might print `r1=1,r2=0`, `r1=1,r2=1`, or the JMM-permitted outcome `r1=0,r2=0`. The example line is **not a measured single run**. Running this test many times is not enough to serve as a formal proof; the frequency of each outcome depends on the machine/JVM/scheduler/JIT.

### Why Doesn't `join()` “Fix” the Race Between A and B?

`join` guarantees that when main reads `r1,r2` after both threads finish, the writes that occurred in A/B are properly observed by main. However, it **does not create an HB edge** from A's `x = 1` to B's `r2 = x` or from B's `y = 1` to A's `r1 = y`. The two worker threads still have racy accesses.

## 6. Happens-before: What to Look For Instead of Guessing CPU Timing

Important HB sources in JLS 17:

| Situation | Synchronization Edge and What Is Guaranteed |
| --- | --- |
| A single thread executes `A` then `B` | `hb(A, B)` by program order |
| Thread A `unlock(M)`, Thread B subsequently `lock(M)` in synchronization order | Unlock **synchronizes-with** subsequent lock of **the same M** |
| A sets `volatileField = value`, B subsequently reads `volatileField` in synchronization order | Volatile write **synchronizes-with** subsequent reads of the same variable |
| A calls `t.start()` | `start` synchronizes-with the first action of thread t |
| A calls `join()` on thread t and detects t terminated | Actions of t happen-before the continuation of A after successful join |
| Thread A `interrupt`s B and B detects the interrupt | There is a synchronization edge specified by the JLS |
| Object undergoes default initialization | Default-initialization writes have HB to appropriate actions |
| `final` field initialization | Specific freeze rules in `17.5` upon valid construction |

**Not in the list of automatic synchronization guarantees:** `Thread.sleep`, `Thread.yield`, calling `System.nanoTime`, `println` in places not designed as a protocol, busy-waiting reading a plain field, `Thread.onSpinWait`.

A library API may define its own memory-consistency effects (e.g., `CountDownLatch`, `BlockingQueue`, `Future`). Rely on the **API contract**, not on guessing whether the API uses locks internally.

## 7. Why Does `sleep` NOT Create Happens-before?

Java SE 17 JLS **`17.3 Sleep and Yield`** states clearly:

- `Thread.sleep` causes the current thread to **suspend execution temporarily** for the requested duration, subject to the precision limits of timers/schedulers.
- Sleep **does not release monitors** owned by the thread.
- `Thread.sleep` and `Thread.yield` **have no synchronization semantics**.
- The JVM is not required to flush writes from registers to shared memory before sleeping or reload values from shared memory after sleeping.

Consequence: code like the following is **incorrect**:

```java
// UNSAFE fragment (for illustration only, should not be run infinitely)
class BrokenWorker {
    boolean done; // NOT volatile

    void waitUntilDone() throws InterruptedException {
        while (!done) {
            Thread.sleep(100);
        }
    }
}
```

Another thread may write `done = true`, but the waiter is **not guaranteed to observe the change**. The JLS illustrates that the compiler may reuse the value already read in the loop. Sleep is **not a polling-with-visibility guarantee**.

A program succeeding 100 times only demonstrates one set of interleavings; it does not establish a cross-thread contract.

### `sleep(0)` or `yield()` Helps Even Less

`Thread.sleep(0)` is not `VarHandle.fullFence`; `Thread.yield()` is only a scheduling hint and may be ignored by the scheduler. There is no JMM rule turning “yielding the CPU” into a release–acquire or public memory fence.

### `sleep` Is Not an Ordering Mechanism

```java
Thread worker = new Thread(() -> {
    // doSomething();
});
worker.start();
Thread.sleep(100);
// Must not assume the worker has finished.
```

This is a fragment inside a method that throws/catches `InterruptedException`. If you need to wait for a thread to **finish**, use `join`, `Future.get`, or an equivalent completion mechanism. If you need to wait for a **mutable condition**, use `volatile` properly, `wait/notify`, `CountDownLatch`, `BlockingQueue`, or an appropriate concurrency abstraction.

## 8. Sleep Does Not Release a Monitor Either: Runnable Demo

Create file **`SleepKeepsMonitorDemo.java`**:

```java
public class SleepKeepsMonitorDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Object lock = new Object();

        synchronized (lock) {
            System.out.println("beforeSleep="
                    + Thread.holdsLock(lock));
            Thread.sleep(20);
            System.out.println("afterSleep="
                    + Thread.holdsLock(lock));
        }

        System.out.println("afterBlock="
                + Thread.holdsLock(lock));
    }
}
```

```bash
javac --release 17 SleepKeepsMonitorDemo.java
java SleepKeepsMonitorDemo
```

**Exact stdout if not externally interrupted:**

```text
beforeSleep=true
afterSleep=true
afterBlock=false
```

Sleep may last **different from exactly 20 ms** and the thread might not resume immediately after the timer expires. However, it **does not release the monitor** while waiting; `Thread.holdsLock` remains true before and after sleep inside the block. Only upon exiting the synchronized block is ownership released.

**Practical warning:** holding a monitor while sleeping forces other threads needing that monitor to wait. Do not use `Thread.sleep` to “reduce contention” inside a critical section; it usually **prolongs** contention.

## 9. How Does `volatile` Fix the Flag Visibility Problem?

Declaring a flag `volatile` makes accesses to the flag participate in **synchronization order**. A volatile write (release-like) before a subsequent volatile read (acquire-like) of **that same field** creates a synchronizes-with relation; from there, transitive HB can transfer writes prior to publication to the reader.

```java
class Signal {
    int payload;
    volatile boolean ready;
}
```

Model:

```text
Writer thread:                 Reader thread:

payload = 42                  while (!ready) ...
ready = true  --sw--->         read ready == true
                               read payload == 42

Writes to payload before the volatile write are ordered
before the reader's reads after the corresponding volatile read.
```

**This does not mean `payload` itself becomes volatile.** They are ordered by the publish/read protocol through **the same volatile ready** and the absence of other racy writes to payload during use.

### Java 17 Runnable: Volatile Publication

Create file **`VolatileSignalDemo.java`**:

```java
public class VolatileSignalDemo {
    private int payload;
    private volatile boolean ready;

    private void publish() {
        payload = 42;
        ready = true;
    }

    private int awaitValue() {
        while (!ready) {
            Thread.onSpinWait();
        }
        return payload;
    }

    public static void main(String[] args)
            throws InterruptedException {
        VolatileSignalDemo signal = new VolatileSignalDemo();
        Thread producer = new Thread(signal::publish, "producer");
        producer.start();

        int result = signal.awaitValue();
        producer.join();
        System.out.println("payload=" + result);
    }
}
```

```bash
javac --release 17 VolatileSignalDemo.java
java VolatileSignalDemo
```

**Stdout once both threads make progress and encounter no runtime issues:**

```text
payload=42
```

The reader only reads `payload` after observing `ready=true` from the volatile. Because `payload=42` precedes the volatile write in program order and the reader reads ready before payload, HB holds through the volatile.

**This is a spin-wait demo to explain the JMM, not a production waiting pattern**: it burns CPU, the JVM/scheduler does not promise a deadline by which the producer thread must run, and it can run indefinitely if the producer is not scheduled. `Thread.onSpinWait` is only a hint to the CPU/runtime; **it does not replace volatile** and does not create HB on its own. In production, consider `CountDownLatch`, `BlockingQueue`, or `CompletableFuture`.

## 10. `volatile` Does Not Make `count++` Atomic

Common mistake:

```java
volatile int count;

void increment() {
    count++; // still read + add + write
}
```

This is a fragment. `volatile` enforces visibility/ordering rules and atomicity of **individual volatile reads/writes**, but a read–modify–write operation does not become an atomic transaction.

Two threads can still do:

```text
initial count = 7
A read count => 7
B read count => 7
A write 8
B write 8

Result = 8, even though there are two increment operations.
```

If multiple threads increment a counter concurrently, use `synchronized`/`ReentrantLock` or `AtomicInteger.incrementAndGet()` as needed. `LongAdder` suits certain high-throughput statistics, though the semantics of `sum()` under concurrent updates differ from an atomic snapshot.

### `AtomicInteger` Example With Deterministic Result

Create file **`AtomicIncrementDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicIncrementDemo {
    public static void main(String[] args)
            throws InterruptedException {
        AtomicInteger count = new AtomicInteger();
        Runnable job = () -> {
            for (int i = 0; i < 10_000; i++) {
                count.incrementAndGet();
            }
        };

        Thread a = new Thread(job, "A");
        Thread b = new Thread(job, "B");
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("count=" + count.get());
    }
}
```

```bash
javac --release 17 AtomicIncrementDemo.java
java AtomicIncrementDemo
```

**Stdout when threads finish normally:**

```text
count=20000
```

`incrementAndGet` provides an atomic read-modify-write; `join` also lets main know both worker threads have finished and all updates are properly observed.

## 11. `synchronized`: Mutual Exclusion and Happens-before

`synchronized(lock)` does not just prevent two threads from simultaneously owning **the same monitor**. Under the JMM, **an unlock of monitor M** synchronizes-with **every subsequent lock** of that same M in synchronization order.

```java
class Box {
    int value;

    synchronized void write(int x) {
        value = x;
    }

    synchronized int read() {
        return value;
    }
}
```

Both instance methods use the **`this`** monitor. When the reader runs after the writer has unlocked **the same instance** and there is no other write, the reader sees the appropriate update. If methods are called on **two different Box objects**, there is no shared monitor protecting a common shared state.

### Pattern Using Synchronized Without a Separate Volatile

Create file **`MonitorStateDemo.java`**:

```java
public class MonitorStateDemo {
    static final class Box {
        private int value;

        synchronized void set(int v) {
            value = v;
        }

        synchronized int get() {
            return value;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Box box = new Box();
        Thread writer = new Thread(() -> box.set(42));
        writer.start();
        writer.join();

        System.out.println("value=" + box.get());
    }
}
```

```bash
javac --release 17 MonitorStateDemo.java
java MonitorStateDemo
```

**Stdout:**

```text
value=42
```

This example has **two HB sources**: writer unlock→main acquiring the lock of the same Box, and writer completion→main successful `join`. Therefore, do not use it to prove synchronized alone is the only edge; it demonstrates a valid pattern and a deterministic outcome.

To verify locking correctness without relying on sleeps, you can add multiple readers/writers sharing a Box, use a startup barrier, and assert invariants, though scheduling and throughput will be non-deterministic.

## 12. `Thread.start` Creates HB That Sleep Cannot

JLS `17.4.4–17.4.5` specifies that calling `t.start()` synchronizes-with the first action in thread `t`. All actions performed by the launching thread **before start** in program order have an HB path to the actions of the new thread.

Example:

```java
int[] data = {1, 2, 3};
Thread worker = new Thread(() ->
        System.out.println(data[0] + data[1] + data[2]));
worker.start();
```

This is a fragment. The `data` array is created and populated before `start`; the new thread is guaranteed to see the proper initialization. **There is no need to sleep to “wait for the array to appear in RAM”**.

However, `start()` does **not** automatically synchronize writes occurring **after** `start` from parent to worker. If the parent continues modifying `data` after start while the worker reads without synchronization, a data race can still occur.

### `join` Creates the Reverse Direction

When main calls `worker.join()` and returns successfully after the worker finishes, the worker's actions happen-before subsequent actions in main.

```text
Main:  initialize input
       start(worker) --sw---> Worker reads input
                                   |
                                   | compute result = 42
                                   v
Main:  join(worker) succeeds <-- thread termination
       read result (visibility guaranteed)
```

`Thread.sleep` plays no synchronization role in either direction.

## 13. Java 17: `join` Properly Resolves Completion Order

Create file **`JoinVisibilityDemo.java`**:

```java
public class JoinVisibilityDemo {
    private static int result;

    public static void main(String[] args)
            throws InterruptedException {
        int input = 21;
        Thread worker = new Thread(() -> result = input * 2);

        worker.start();
        worker.join();

        System.out.println("result=" + result);
    }
}
```

```bash
javac --release 17 JoinVisibilityDemo.java
java JoinVisibilityDemo
```

**Stdout:**

```text
result=42
```

The `result` field is not volatile, yet main reads it **after a successful join**: the JMM provides HB through termination/join. Writing `Thread.sleep(100)` instead of `join` would **not** provide the same guarantee, even if on a test machine the worker usually finishes within a few milliseconds.

### `join(timeout)` Needs Additional Conditions

If using `worker.join(100)`, the call may return when the timeout expires even if the worker is still running. You cannot assume the thread has terminated merely because `join(timeout)` returned. Check `isAlive()`/an appropriate completion condition and the API semantics. The simplest practice when you need to wait reliably for completion is `join()` without a timeout, with an appropriate interruption/cancellation strategy.

## 14. CountDownLatch: Replacing Sleep With a Contracted Signal

`CountDownLatch` defines **memory consistency effects**: actions in a thread prior to calling `countDown()` happen-before actions in another thread following a successful return from the corresponding `await()`.

Create file **`LatchPublicationDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class LatchPublicationDemo {
    private static int payload;
    private static String label;

    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);

        Thread writer = new Thread(() -> {
            payload = 42;
            label = "prepared";
            ready.countDown();
        }, "writer");
        writer.start();

        ready.await();

        System.out.println("payload=" + payload);
        System.out.println("label=" + label);
        writer.join();
    }
}
```

```bash
javac --release 17 LatchPublicationDemo.java
java LatchPublicationDemo
```

**Stdout when writer completes normally:**

```text
payload=42
label=prepared
```

Because the writer writes `payload`, `label`, and then calls `countDown()`, and main's `await()` succeeds before reading: **HB is guaranteed by the concurrency library**, even though the two regular fields are not volatile.

Differences from sleep:

| Sleep | CountDownLatch |
| --- | --- |
| Waits for a relative duration | Waits for an **event** where count reaches 0 |
| Does not know whether the producer has finished preparing | Successful `await()` confirms the latch has opened |
| Does not provide HB by sleep itself | Has a memory-consistency edge specified by the API |
| Does not guarantee the scheduler runs the producer | Also does not promise a deadline, but the event protocol is correct when the producer progresses |
| No business-condition outcome | Valid completion signal |

`CountDownLatch` is single-use; if you need a repeatable barrier across multiple phases, use `CyclicBarrier`/`Phaser` or another workflow design.

## 15. `wait/notify`: Differing From `sleep` in Monitor Ownership

A thread inside `synchronized(lock)` can call `lock.wait()` while holding the monitor:

- `wait()` **releases the monitor of that `lock` object** and moves the thread to the wait set per API rules.
- Upon waking (notification, interruption, timeout/spurious wakeup per semantics), it must **re-acquire the monitor** before continuing or throwing as appropriate.
- `notify()`/`notifyAll()` requires the caller to own the monitor; notifying does not release the monitor immediately by itself.
- Always use `while (!condition) lock.wait()`, because waking up does not guarantee the business condition is true.

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    consumePayload();
}
```

This is a fragment in a method with `throws InterruptedException` or an appropriate catch, and `lock`, `ready`, `consumePayload` declared.

**`sleep` is completely different:** sleeping inside synchronized holds the monitor, does not establish an event-notification protocol, and does not guarantee a plain `ready` field will be reloaded.

## 16. Java 17: Conditional wait/notifyAll With Stable Output

Create file **`WaitConditionDemo.java`**:

```java
public class WaitConditionDemo {
    static final class Mailbox {
        private boolean ready;
        private int data;

        synchronized void publish(int value) {
            data = value;
            ready = true;
            notifyAll();
        }

        synchronized int receive() throws InterruptedException {
            while (!ready) {
                wait();
            }
            return data;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Mailbox box = new Mailbox();
        Thread writer = new Thread(() -> box.publish(42));
        writer.start();

        int observed = box.receive();
        writer.join();
        System.out.println("observed=" + observed);
    }
}
```

```bash
javac --release 17 WaitConditionDemo.java
java WaitConditionDemo
```

**Stdout upon normal completion:**

```text
observed=42
```

- If the writer publishes first, `ready` is already true and the reader does not need to wait.
- If the reader arrives first, it calls `wait` and releases the monitor for the writer, then re-acquires it after notify.
- The plain field `data` remains safe via **monitor ordering**: both writes and reads are performed inside synchronized methods of **the same Mailbox instance**.
- `writer.join()` after `receive` is not the sole reason the reader sees data; the condition and monitor protocol already handle it safely.

Do not use `if (!ready) wait()`: you must withstand **spurious wakeups** and recheck the condition after reacquiring.

## 17. So What Is Guaranteed for a “Data-Race-Free” Program?

JLS `17.4.5` states a prominent principle: a **correctly synchronized** program (free of data races in sequentially consistent executions) yields outcomes that can be understood under **sequential consistency**. Practically speaking: if all shared mutable state has a proper synchronization protocol, you do not need to guess which machine instructions the compiler/CPU swapped to reason about unexpected racy values.

**Sequential consistency** means there exists a total order of actions across threads in which each thread preserves its own program order and reads observe writes consistent with that order.

However, avoid three misconceptions:

- It does **not** mean thread A runs completely before thread B; actions from multiple threads can interleave.
- It does **not** mean the scheduler is fair or that deadlocks are impossible; the JMM is a model of memory behavior, not a liveness guarantee.
- It does **not** mean any arbitrary method call is automatically atomic; critical sections/atomic operations must cover the right invariants.

A data-race-free program can still have a **logical race** (for example, two clients ordering the last item when business logic lacks sufficient locking/transactions), or deadlock due to reversed lock ordering, even though memory visibility itself obeys the JMM.

## 18. A Data Race in Java Does Not Mean “Anything Can Happen”

Do not mechanically apply C/C++'s definition of `undefined behavior` to Java. The JMM still restricts the set of valid executions:

- The compiler must preserve appropriate intra-thread semantics.
- Reads are constrained as to which writes they can observe under the JMM.
- Volatiles, locks, thread start/join, and synchronization actions must obey ordering.
- `final` field initialization has special rules.
- **Causality requirements** prevent certain “out of thin air” values.

However, **lacking HB** for conflicting plain accesses allows results that differ from a sequentially consistent trace, and applications must not rely on what is “usually seen” on hardware.

Do not design correctness around “x86 has strong memory ordering so a plain field is probably fine”, or “my HotSpot JDK still reloads the variable after every `sleep`”. The JVM must be portable across compiler optimizations, CPU architectures, and updates.

## 19. Safe Publication: Publishing an Object Graph Properly

A shared object may be constructed properly in thread A, yet thread B needs a valid **publication event** to receive those prior writes.

Volatile reference pattern:

```java
final class Config {
    final int port;
    final String host;

    Config(int port, String host) {
        this.port = port;
        this.host = host;
    }
}

class Holder {
    volatile Config current;

    void publish() {
        Config cfg = new Config(8080, "localhost");
        current = cfg;
    }
}
```

These are fragments, without `main`. When another thread reads `holder.current` via volatile and sees the published reference, writes prior to the volatile write have appropriate HB guarantees. **Do not modify `cfg` after publication** if you want to maintain a stable immutable snapshot, unless other synchronization is used.

Besides volatile, safe publication can be achieved via:

- Initializing before `Thread.start` and passing the object to the worker.
- Guarding publication and consumption with the same monitor.
- Thread-safe concurrent collections/queues with API memory-consistency effects.
- `CountDownLatch`/`Future`/`CompletableFuture` following their contracts.
- Class initialization: the JVM guarantees appropriate initialization synchronization.
- Final field semantics when the object is constructed properly and `this` does not escape prematurely.

### Safe Publication Does Not Permanently Make a Mutable Object Thread-Safe

After a reference is safely published, if multiple threads continue modifying non-final fields of the object without a new protocol, **data races can still occur**. Safe publication lets readers see the state **at the time of publication** under appropriate conditions; subsequent mutations require proper synchronization.

## 20. `final` Fields and Constructors: Benefits With Limits

JLS `17.5` specifies special **final field semantics**: when an object is properly constructed and `this` does not escape from the constructor, final fields have initialization guarantees even if the reference is passed to another thread without full synchronization.

```java
final class Message {
    final int code;
    final String text;

    Message(int code, String text) {
        this.code = code;
        this.text = text;
    }
}
```

This is a class fragment, without `main`. `final` helps protect properly constructed state, but it does not mean every mutable sub-object deep in the graph is **automatically thread-safe** or that all post-initialization behavior is safe.

Especially avoid **this escape**:

```java
// Bad design: publishing this inside the constructor.
class BadPublication {
    static BadPublication shared;
    final int number;

    BadPublication() {
        shared = this;
        number = 42;
    }
}
```

This snippet illustrates an **unsafe practice**, not a recommended program. If the reference escapes before final fields are assigned or the constructor finishes, the intended initialization guarantees can be broken.

Do not write that “reading a final field always sees 0 in a race”; nor write that “final can replace synchronized for all mutable state”. Read `JLS 17.5` accurately.

## 21. `volatile` and Compound Invariants: Visibility Is Not Enough

Suppose:

```java
class Range {
    volatile int min;
    volatile int max;

    void update(int low, int high) {
        min = low;
        max = high;
    }
}
```

Two `volatile` fields guarantee ordering for individual reads/writes, but a reader may observe **new min, old max** if another thread reads between the two writes. If the invariant `min <= max` must always be observed as a consistent snapshot, the design must use synchronization, an immutable snapshot via **a single volatile reference**, or an atomic protocol for the entire state.

### Fixing With an Immutable Snapshot

```java
record RangeSnapshot(int min, int max) {}

class RangeHolder {
    private volatile RangeSnapshot snapshot =
            new RangeSnapshot(0, 0);

    void set(int low, int high) {
        snapshot = new RangeSnapshot(low, high);
    }

    RangeSnapshot get() {
        return snapshot;
    }
}
```

This is a Java 17 fragment. A volatile reference update publishes **the entire immutable snapshot object** in one atomic reference read/write action; the reader uses a local `RangeSnapshot r = holder.get()` and then reads both `r.min()` and `r.max()` to get values from **the same snapshot**.

If the caller calls `holder.get()` **two different times**, it may read two different versions; do not turn a composite read into a snapshot without using the same local reference.

## 22. `sleep` Does Not Guarantee Deadlines, Fairness, or Thread Completion

Beyond memory visibility, `Thread.sleep` lacks the following guarantees:

| Expectation | Does `sleep` guarantee it? | What to use instead when needed |
| --- | --- | --- |
| Another thread has reached a specific statement | **No** | `CountDownLatch`/barrier/handshake |
| Another thread has finished | **No** | `join`/`Future.get` |
| Writes in another thread are visible | **Not merely because of sleep** | HB via volatile/locks/latch/join |
| Releasing monitor while sleeping | **No** | `Object.wait`/`Condition.await` when appropriate |
| Sleeping for exactly N milliseconds | **No** | Scheduler/timers have limits; handle timeouts with deadlines/clock |
| Yielding CPU to a chosen thread | **No** | Scheduler decides; `yield` is only a hint |
| Guaranteeing a thread is eventually scheduled | **No** | Liveness fairness is not a contract of sleep |
| Guaranteeing a composite operation is atomic | **No** | Atomic API/lock/transaction |
| Protecting queues and avoiding lost notifications | **No** | BlockingQueue/Condition/monitor protocol |
| Avoiding deadlock while holding locks | **No** | Lock ordering, timeouts, critical section management |

In concurrency tests, `Thread.sleep(100)` “to let thread A run before B” is often a **flaky test pattern**. On slow CI, thread B might not get CPU until after 100 ms; on a fast machine, B might overtake A immediately. Test design should use latches/barriers to establish the exact interleaving or condition to observe.

## 23. Two Testing Examples: Race Condition and Event Synchronization

### Wrong: Sleeping to Assume the Producer Finished Writing

```java
// Incorrect illustration code, NO fixed output.
static int result;

static void broken() throws InterruptedException {
    new Thread(() -> result = 42).start();
    Thread.sleep(100); // does not prove the writer finished
    System.out.println(result);
}
```

The thread might not have been scheduled yet, so main could see `0`; even in runs where the writer performed the write before main read in wall-clock time, HB is still missing for the plain field `result` without synchronization.

### Right: Waiting for the Producer to Finish

```java
static int result;

static void corrected() throws InterruptedException {
    Thread t = new Thread(() -> result = 42);
    t.start();
    t.join();
    System.out.println(result); // 42 if the thread completed normally
}
```

These are fragments. `join` creates HB from the producer's actions to main after a successful join. If the producer throws an exception before the assignment or is canceled, completion/failure must be handled per the business protocol; `join` does not by itself guarantee business work succeeded.

### Right: Waiting for the “Data Ready” Event Instead of the Whole Thread Finishing

Use `CountDownLatch` when the producer still has other work to do after the data is ready; use `BlockingQueue` if producer/consumer exchange multiple messages; use `CompletableFuture`/`Future` if you need to pass a value or failure.

## 24. Thread Interruption: Interrupted Sleep Differs From a Synchronization Protocol

`Thread.sleep` can throw `InterruptedException` if the thread is interrupted. When throwing that exception, the **interrupted status is cleared** per the `Thread.sleep` API. However, the `interrupt` action and detecting the interrupt can participate in **synchronizes-with** under the JLS. That is synchronization from the **interrupt protocol**, **not from sleep itself**.

Two points to separate:

1. **`Thread.sleep` has no synchronization semantics** of its own.
2. Another event such as `interrupt()/InterruptedException` has semantics specified by the JMM.

If you catch `InterruptedException` and cannot handle it, it is usually best to restore the interrupt status:

```java
try {
    Thread.sleep(100);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
```

This is a fragment. Restoring the interrupt is a decision about the **cancellation contract**; in code whose API throws `InterruptedException` to the caller, propagating it is often better. Do not use a loop that swallows the exception and keeps sleeping forever, preventing the worker from shutting down cleanly.

## 25. Busy-Wait, `Thread.onSpinWait`, and Backoff Do Not Replace the JMM

A loop:

```java
while (!ready) {
    Thread.onSpinWait();
}
```

is a fragment that is **only visibility-correct if `ready` is already properly synchronized**, such as volatile. `Thread.onSpinWait()` is a **performance hint** for short-term spin-wait loops; it does not place a memory fence/happens-before between producer and consumer.

Other techniques like exponential backoff and `LockSupport.parkNanos` serve scheduling/CPU usage, **not as a replacement for a state-transfer protocol**. When using `park/unpark`, follow the API's permit semantics; do not assume all plain field writes around any sleep/park become universally visible.

A busy-wait with a non-volatile flag can be optimized by the JIT to hoist the field read out of the loop when constraints allow. Adding sleep inside does not force the compiler to reload under the JLS.

## 26. Notes on `long`/`double` and Single-Access Atomicity

JLS `17.7` allows **non-volatile `long`/`double` reads/writes** to be treated as two 32-bit halves in cases described by the specification; therefore, portable code should not assume every non-volatile 64-bit primitive access is atomic like volatile.

At the same time:

- **Volatile `long` and `double`** have atomicity guaranteed by the JMM for appropriate single accesses.
- Atomicity of **a single write/read** differs from the atomicity of `counter++`.
- Some HotSpot/hardware configurations in practice perform non-volatile 64-bit accesses atomically, but that cannot be taken as a universal Java SE guarantee.
- Adding volatile does not make operations involving multiple fields an atomic transaction.

Do not use the mental model “all races only have stale reads” — there are also lost updates, inconsistent snapshots, and reordering effects.

## 27. When Do Memory Barriers/Fences Actually Need to Be Understood?

`volatile`, intrinsic locks, atomics, and concurrency libraries are implemented by the JVM using lower-level mechanisms, which may include compiler barriers, CPU fences, atomic read-modify-write instructions, and cache-coherence behavior. However, the JMM is a **semantic contract**, not a fixed list of assembly instructions.

For example:

- On one CPU architecture, the compiler may need a machine fence to satisfy volatile ordering.
- On another architecture, some ordering may already be guaranteed by the instruction/store model, so codegen differs.
- The JIT may merge, move, or eliminate unnecessary barriers while preserving Java semantics.
- Bytecode `monitorenter`/`monitorexit` is the synchronization mechanism at the class-file level; JIT code may use fast paths or lock elimination under valid conditions.
- VarHandle modes (`getAcquire`, `setRelease`, `getVolatile`, `setVolatile`) have distinct contracts; not every mode is equivalent to full volatile.

Therefore, **do not read JVM assembly from one machine and write universal conclusions about Java ordering**. When correctness is needed, choose the right public abstraction (`volatile`, synchronized, atomic, concurrent collections). When low-level optimization is needed, study `VarHandle` memory-order modes and measure on the specific JDK/hardware.

## 28. A Common Bug: Holding a Lock During `sleep` Causes Starvation

Suppose:

```java
synchronized (lock) {
    updateState();
    Thread.sleep(500);
}
```

This is a fragment inside a method that throws/catches `InterruptedException`. Sleep **does not release the monitor**, so another thread needing `lock` may be blocked for the full 500 ms or longer. If repeated many times under the lock, throughput drops and tail latency rises.

Redesign if the invariant allows:

```java
synchronized (lock) {
    updateState();
}
Thread.sleep(500);
```

However, **do not move sleep outside the lock purely on instinct** if the business protocol requires an atomic operation or condition waiting; in that case, `wait/notify` or `Condition.await` may be used. What must be determined first is **what needs mutual exclusion** and **when it is safe to release the lock**.

## 29. What Can `System.out.println` Hide in a Race Demo?

Some concurrency demos call `System.out.println` repeatedly across threads and conclude “no race” because the output looks sequential. In reality, the implementation of `PrintStream` and I/O may have synchronization or scheduling side effects that alter interleavings.

Do not rely on it to infer that plain field accesses in other paths are properly synchronized. Conversely, calling println only in **main after join** as in `ReorderingLitmus` does not fix the data race between the two worker threads.

Benchmark/race testing practices:

- Separate sampling/output from the hot critical path.
- Use stress tests with barriers to create concurrency, not guesswork sleeps.
- Do not equate “stress test didn't fail” with proof.
- Use formal JMM reasoning or dedicated concurrency testing tools for sensitive cases.
- Cross-check across interpreter/JIT/hardware configurations instead of relying on a single CPU.

## 30. Code Review Checklist on Sleep, Ordering, and Races

Before merging multi-threaded code, answer these questions:

1. **Which variables are shared?** Instance fields, static fields, array elements, or published object graphs?
2. Are there **conflicting accesses** (at least one write)?
3. Do the two accesses have an HB edge through **the same volatile variable**, **the same monitor**, `start`/`join`, or a concurrency API contract?
4. Are there `count++`, `check-then-act`, or two writes together forming an invariant that needs **atomicity**?
5. Is `Thread.sleep` used to “wait for a worker to finish” instead of `join`/`Future`?
6. Is `Thread.sleep` used inside a synchronized block, forcing other threads to wait long?
7. Is there a spin-loop on a **plain boolean** assuming sleep/onSpinWait will flush caches?
8. Does a `volatile` flag publish payload writes **before** the signal, with the reader only reading after acquiring?
9. Does the reader ever read fields **before** checking the flag?
10. Are other writers modifying the payload without synchronization despite publication?
11. Are tests flaky because sleep is used to order threads?
12. Does an object suffer **this-escape in the constructor**, breaking safe-final-field publication?
13. Are **join(timeout)** or `await(timeout)` mistaken for having succeeded even when they timed out?
14. Is `InterruptedException` handled in accordance with the cancellation contract?
15. What memory-consistency effects does the concurrent API being used have per Java 17 docs?
16. Have **thread-safety**, **progress/liveness**, **fairness**, and performance been distinguished?

## 31. Common Misconceptions

| Misconception | Correct Fact |
| --- | --- |
| “Sleeping 1 second means the other thread definitely ran” | Scheduler/timers do not guarantee order or completion |
| “Sleep automatically flushes CPU caches” | JLS `17.3` states sleep/yield **have no synchronization semantics** |
| “Sleep releases a synchronized lock” | Sleep **holds** monitors; `Object.wait` releases/reacquires the waited monitor |
| “Yield is a memory fence” | `yield` is only a scheduling hint, creating no JMM HB |
| “Two threads having wall-clock order means HB exists” | Appropriate program-order/synchronizes-with edges are required |
| “Not seeing a race during testing means there is no data race” | A successful run schedule is not a proof |
| “A data race only makes results slower” | It can cause wrong values, stale reads, lost updates, nontermination |
| “A Java data race allows any arbitrary value” | The JMM still constrains executions and causality |
| “volatile makes ++ atomic” | Only individual accesses; increment is read–modify–write |
| “A volatile reference makes the entire object graph immutable” | Post-publication mutations require their own protocol |
| “Each volatile field creates an atomic snapshot for the whole object” | Atomic composition or an immutable snapshot is needed |
| “join only waits for scheduler timing, not visibility” | A successful join creates HB to the caller |
| “Thread.start only schedules, doesn't publish prior writes” | `start` has a synchronizes-with edge |
| “CountDownLatch is like sleep because both wait” | Latch has an event protocol and memory-consistency effects |
| “wait() and sleep() are the same” | `wait` releases/reacquires the monitor; `sleep` does not |
| “onSpinWait ensures a plain boolean is always reloaded” | CPU hint, does not replace volatile |
| “If it looks fine on x86, portable Java is right” | JMM must hold across different JVMs/hardware |
| “JIT reordering means violating Java” | Reordering is valid if JMM/inter-thread constraints are preserved |
| “println makes plain shared fields thread-safe” | I/O implementation side effects do not replace a proper protocol |
| “Data-race-free means never deadlocking” | Deadlock/liveness is distinct from memory consistency |
| “Just using final fields makes any mutable graph safe” | Final initialization rules have limits and require proper construction |

## 32. Self-Check Questions

**Question 1.** Thread A writes `done = true` to a plain field; B loops `while(!done) Thread.sleep(100)`. Is B guaranteed to stop?

**No.** There is no HB/visibility guarantee; sleep does not create synchronization, and the compiler may reuse the old value per the JLS.

**Question 2.** Why can two threads each writing one variable and reading the other's variable both read 0?

Without synchronization, the JMM permits the outcome `(0,0)` in that litmus test; this does not prove a specific reorder happened in machine code.

**Question 3.** Thread A calls `t.start()` after creating an array. Will thread t see the values assigned before start?

**Yes**, due to HB from actions before start to actions in the new thread.

**Question 4.** Main uses `Thread.sleep(500)` instead of `worker.join()`. Is it guaranteed the worker finished and data is visible?

**No**. Use a successful `join` or a completion primitive.

**Question 5.** Does `volatile int count; count++;` make the increment atomic?

**No**. Use `AtomicInteger.incrementAndGet` or a lock.

**Question 6.** Writer writes `payload=42` then volatile `ready=true`; reader observes ready true then reads payload. Why can the reader trust payload?

The volatile write/read creates synchronizes-with; transitive HB connects the payload write to the payload read, provided there are no competing writes causing a data race.

**Question 7.** Does sleeping inside `synchronized(lock)` release the lock so another thread can enter?

**No.** It is released upon monitor exit; `Object.wait` temporarily releases the waited monitor when called under the right conditions.

**Question 8.** Why is `while(!condition) wait()` better than `if(!condition) wait()`?

Because of spurious wakeups and contention after notification; the predicate must be rechecked under the same monitor.

**Question 9.** Does `join(timeout)` returning always mean the thread has terminated?

**No.** The timeout may expire before completion; check the state/result.

**Question 10.** Can a data-race-free program deadlock?

**Yes.** Memory ordering correctness does not guarantee progress/fairness.

**Question 11.** Does `Thread.onSpinWait` turn a plain field into volatile?

**No.** It is a runtime hint and does not create the required memory consistency.

**Question 12.** Why are `final` fields good yet unable to fix every unsafe publication?

The constructor must not let `this` escape prematurely; and mutable state after construction still needs valid synchronization.

## 33. Java SE 17 References

- [JLS 17 `17.3` — Sleep and Yield](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.3): directly explains **no synchronization semantics**, no flush/reload guarantees, and sleep not releasing monitors.
- [JLS 17 `17.4.1` — Shared Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.1): instance fields, static fields, array elements.
- [JLS 17 `17.4.3` — Program Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.3): actions within each thread.
- [JLS 17 `17.4.4` — Synchronization Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.4): volatile, monitor, thread start/termination, interrupts.
- [JLS 17 `17.4.5` — Happens-before Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5): HB, data races, correctly synchronized programs, and sequential consistency.
- [JLS 17 `17.4.8` — Executions and Causality](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.8): causality constraints, not assuming every value is valid in a race.
- [JLS 17 `17.5` — Final Field Semantics](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): constructor, final initialization, this-escape.
- [JLS 17 `17.7` — Non-Atomic Treatment of double and long](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.7): distinguishing non-volatile and volatile 64-bit accesses.
- [Java SE 17 `Thread.sleep`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#sleep(long)): timeout, interrupted status, not releasing monitors.
- [Java SE 17 `Thread.onSpinWait`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#onSpinWait()): performance hint, not volatile.
- [Java SE 17 `CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): memory consistency effects of `countDown`/`await`.
- [Java SE 17 `AtomicInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic read–modify–write operations.
- [Java SE 17 `Object.wait/notify`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): wait sets, monitor release/reacquisition.
- [Java SE 17 `VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): memory-ordering modes when low-level study is needed.

**Remember:** Java permits transformations/reordering as long as the **JMM** is preserved, so a program with a **data race** is not protected by the intuition that “source lines will reach each thread in the same order”. `Thread.sleep` is merely a scheduler delay tool: **it does not synchronize memory, does not guarantee a worker has finished, does not release monitors, and does not make a plain flag volatile**. To make a program correct, establish **happens-before** using `volatile`, intrinsic locks, `Thread.start/join`, and concurrency APIs with clear contracts; use atomic operations when both visibility **and** read–modify–write atomicity are needed.