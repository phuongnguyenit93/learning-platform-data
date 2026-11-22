# Compiler, CPU, and Memory Reordering in the Java Memory Model

In a single-threaded program, we usually read statements in order from top to bottom. However, when two or more threads operate on shared data, **the order in which statements are written in source code does not automatically become the order that another thread is guaranteed to observe**. The compiler, JVM JIT, and hardware can all optimize execution; data may also be held temporarily in registers, caches, or write buffers. The Java Memory Model (JMM) specifies which outcomes are allowed and which synchronization relationships make a program's results predictable.

For example, consider two statements:

```java
data = 42;
ready = true;
```

This is an illustrative snippet, assuming `data` and `ready` are two fields read by another thread. The writing thread sees `data` assigned before `ready`; **the reading thread is not guaranteed by default** to see `data == 42` upon observing `ready == true` if both ordinary fields are accessed without synchronization. The root cause is that the program has not established the required **happens-before** relationship—not that one can definitively conclude from an anomalous result whether the CPU or the compiler reordered the two statements.

This lesson covers **general Java** concurrency, focusing on reordering in the JMM and how to design correct Java 17+ code. It does not depend on Spring Framework-specific concurrency mechanisms.

## 1. What Does Reordering Mean?

**Reordering** refers to operations being executed or observed in an order different from the syntactic order written in source code, within the bounds permitted by the language and architecture. Three perspectives must be distinguished:

1. **Program order:** the order in which actions appear within a single thread's execution flow according to the language model.
2. **Optimization implementation:** the compiler/JIT may reorder, eliminate, or coalesce operations, or cache values temporarily; the CPU may execute and complete operations according to its pipeline and memory mechanisms.
3. **Inter-thread observation order:** what another thread is actually permitted to observe under the JMM, synchronization relationships, and conflicting operations.

This does not mean the JVM arbitrarily breaks programs. Optimizations must **respect the Java Memory Model**, including outcomes that are not allowed to change in a properly synchronized context.

The **as-if-serial** concept states that optimizations within a single thread must preserve the observable behavior of a single-threaded program as if operations were executed under sequential semantics. However, this is **not sufficient to guarantee** that other threads see all memory writes in the intuitive source-code order without a synchronization relationship.

For example:

```java
int a = 10;
int b = 20;
int sum = a + b;
System.out.println(sum);
```

In a single thread, the program must print `30`; the JVM may optimize the computation without emitting each read/write step as a learner might picture it. What matters is preserving valid outcomes, not forcing every machine instruction to follow textual order.

## 2. Why Can the Compiler and JIT Change Execution Order?

Java source is compiled by `javac` into bytecode; the JVM runs bytecode through an interpreter and/or a JIT compiler depending on the environment. Optimization passes can:

- **Hoist a read out of a loop** if repeated reads are deemed unnecessary under existing constraints.
- **Keep values in registers** or eliminate intermediate reads/writes when doing so does not affect behavior that must be preserved.
- **Swap two independent operations** within the same thread when doing so does not violate ordering relationships required by the language.
- **Inline and optimize across method boundaries**, making the execution structure look different from the call arrangement in source code.
- **Optimize field or element accesses**, provided the JMM and rules regarding synchronization, exceptions, and valid observations are respected.

A dangerous example is a polling loop on an ordinary flag:

```java
class UnsafeStopSignal {
    boolean stopped;

    void requestStop() {
        stopped = true;
    }

    void work() {
        while (!stopped) {
            // Do work or spin.
        }
    }
}
```

This is an **illustrative anti-pattern**, not a program meant to be run directly as a test: if one thread calls `work()` and another calls `requestStop()`, the program lacks synchronization. The worker is **not guaranteed** to see the update; the loop may run indefinitely. This may involve compiler read optimizations, caches/registers, or visibility, but a single run is not enough to conclude which specific mechanism caused the behavior.

When `stopped` is a `volatile boolean` and all access paths use that volatile field, every check must respect volatile semantics under the JMM. However, **`volatile` makes no promises about CPU scheduling, completion time, or waking up a worker blocked on I/O**.

## 3. CPU, Cache, and Store Buffers: Intuition for Observation Differences

At the modern hardware level, multiple CPU cores have their own caches and execution pipelines. A write may pass through a **store buffer** before other cores can observe it in the appropriate order; a read may receive data from a cache, register, or the memory subsystem. CPUs also feature pipelining, speculative execution, and architecture-specific memory ordering mechanisms.

Conceptual model:

```text
            Core 1                           Core 2
       +--------------+                 +--------------+
       | registers    |                 | registers    |
       | store buffer |                 | store buffer |
       | cache        |                 | cache        |
       +------+-------+                 +------+-------+
              |                                |
              +---------- memory system -------+
                          |
                     shared data
```

This diagram only helps explain **why cores can observe reads and writes counterintuitively**. It does not accurately depict every cache level or data transfer sequence of a specific CPU.

Two common misconceptions:

- **Cache coherence** (maintaining consistency of values at a single memory address according to hardware rules) **does not mean** the program has a global memory order matching source order across different addresses.
- Java does not require developers to reason about correctness from x86, ARM, or any specific CPU. The **JMM** is the binding contract between a Java program and every compliant implementation; the compiler/JIT/JVM must combine instructions, memory barriers, or other techniques to uphold that contract on the underlying hardware.

A program with a data race may "run fine" on one configuration and fail when changing the JDK, JIT settings, CPU, or system load. That does not prove a platform "fixed" the race; it shows the program relied on an unguaranteed outcome.

## 4. Litmus Test: Two Writes, Two Reads, and a Surprising Outcome

The classic example for thinking about visibility and reordering is the **store-buffering litmus test** with two variables `x` and `y` initially set to `0`:

```text
Initial values: x = 0, y = 0

Thread A                    Thread B
---------                   ---------
x = 1                       y = 1
r1 = y                      r2 = x

Outcome of interest: r1 = 0 and r2 = 0
```

If we treat the four operations as **sequentially interleaved over a globally consistent memory** while preserving program order in each thread, the outcome where both read `0` is impossible: one of the two writes must precede the opposite read in a single total order.

However, with **ordinary (non-volatile) operations without synchronization between threads**, the JMM allows behaviors that do not correspond to such a simple sequential interleaving. The outcome `r1 == 0 && r2 == 0` can be valid. Running the example does not guarantee you will observe it; a given platform may mostly produce other outcomes.

This is an analytical example, not a fixed-stdout demo. If you want to write a standalone Java test, you can use two threads as follows:

```java
public class StoreBufferingIllustration {
    static int x, y, r1, r2;

    public static void main(String[] args) throws InterruptedException {
        Thread a = new Thread(() -> {
            x = 1;
            r1 = y;
        });
        Thread b = new Thread(() -> {
            y = 1;
            r2 = x;
        });

        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("r1=" + r1 + ", r2=" + r2);
    }
}
```

```bash
javac StoreBufferingIllustration.java
java StoreBufferingIllustration
```

**Stdout is non-deterministic.** For instance, you might see `r1=0, r2=1`, `r1=1, r2=0`, `r1=1, r2=1`, or `r1=0, r2=0`; different schedules and JMM-permitted observations affect the result. Observing `1,1` in one run does not prove the code is synchronized.

In the example above, `main` calls `join()` only to **read the results after both workers finish**. `join()` establishes happens-before from each worker's actions to `main` **after join**, but it does not create a strong enough ordering between thread A's `x = 1; r1 = y` and thread B's `y = 1; r2 = x` while they run concurrently. Therefore, `join()` alone does not prevent `0,0`.

Note: you cannot use this test by itself to claim "the compiler reordered the instructions" or "the store buffer delayed the write" in a specific run. The JMM describes **valid outcomes**; it does not license working backward with certainty to a single hardware cause from stdout.

## 5. Java Memory Model: Rules Instead of CPU Guesswork

The JMM is defined in the Java Language Specification, Chapter 17 (Threads and Locks). It specifies the relationships among program actions, synchronization actions, **happens-before**, and which values a read may observe.

Key terminology:

| Term | Meaning |
| --- | --- |
| Program order | The order of actions in the execution model of a single thread |
| Synchronization action | A synchronization action meaningful to the JMM, such as monitor lock/unlock, volatile read/write, or thread start |
| Synchronization order | A total order defined by the memory model over all synchronization actions, consistent with each thread's program order |
| Synchronizes-with | A specific synchronization relationship between actions, such as an unlock followed by a lock on the same monitor, or a volatile write followed by a matching volatile read |
| Happens-before (HB) | Combines program order and synchronizes-with, with transitivity; used to determine guaranteed memory effects |
| Data race | Two conflicting accesses to the same variable, at least one a write, with no happens-before relationship between them |
| Correctly synchronized | A program free of data races in all sequentially consistent executions; enjoys the JMM's sequential consistency guarantee |

**Sequential consistency (SC)** is the intuition that the operations of all threads can be viewed as a single interleaving that preserves program order within each thread. A key result of the JMM: **a correctly synchronized Java program is sequentially consistent** as defined by the JMM. This does **not** mean the JVM must physically execute every instruction in exact source order; it means the outcomes of a correctly synchronized program can be explained by a valid SC execution.

### Happens-Before and Transitivity

If action A **happens-before** B, and B happens-before C, then A happens-before C. This relationship lets us build a **data publication path** from producer to consumer.

Common HB edges:

- An earlier action in the same thread HB a later action in program order.
- `Thread.start()` HB any actions in the started thread.
- Actions in a waited-upon thread HB actions in the calling thread after `Thread.join()` returns successfully.
- Unlocking a monitor HB a subsequent lock on the **same monitor**.
- A volatile write HB subsequent volatile reads of the same variable in synchronization order.
- Actions before submitting a task via `ExecutorService` HB actions in the task; task actions HB actions after retrieving the result via `Future.get()` under the concurrent utilities' contracts.

Simply reading/writing ordinary variables from multiple threads without one of these proper synchronization paths **does not create HB**.

## 6. Key Example: Message Passing with `volatile`

Suppose we want a publisher to update a payload and then signal a reader. Using a **volatile flag** is a basic way to publish data when the protocol is a simple one-shot handoff.

Save as `VolatilePublicationDemo.java`:

```java
public class VolatilePublicationDemo {
    private static int data;
    private static volatile boolean ready;

    public static void main(String[] args) throws InterruptedException {
        Thread reader = new Thread(() -> {
            while (!ready) {
                Thread.onSpinWait();
            }
            System.out.println("Data: " + data);
        });

        reader.start();

        data = 42;
        ready = true;

        reader.join();
    }
}
```

```bash
javac VolatilePublicationDemo.java
java VolatilePublicationDemo
```

**Exact stdout when the program runs to completion:**

```text
Data: 42
```

Why is this correct?

1. In the `main` thread, `data = 42` **happens-before** `ready = true` by program order.
2. `ready = true` is a **volatile write**. When `reader` reads `ready == true` via a volatile read, the corresponding synchronizes-with relationship is established from the volatile write to the volatile read.
3. That volatile read precedes the read of `data` in `reader`'s program order.
4. By **HB transitivity**, the write `data = 42` happens-before the read of `data`. In this protocol there are no other concurrent writes to `data`, so `reader` is guaranteed to see `42`.

`volatile` on **`ready`** is sufficient for this example: it creates a publication edge for the preceding ordinary write. There is no need to mark `data` as volatile as well **when there is only a one-shot protocol and no other concurrent writes**.

This is a mechanics-learning example; a tight `while (!ready)` spin loop continuously consumes CPU and has no timeout. Real applications should use proper blocking coordination such as `CountDownLatch`, `BlockingQueue`, or `Future`. Merely adding `Thread.onSpinWait()` to reduce spin overhead on some platforms **does not create a memory barrier, does not add HB**, and cannot fix a racy ordinary flag.

### What If `volatile` Is Removed?

With `private static boolean ready;`, the writer thread assigns `data = 42` then `ready = true`, yet the reader is **not guaranteed** to observe `ready` change. Even if it sees `true`, the program lacks a data publication relationship guaranteeing that the reader sees `data == 42` under unsynchronized data access.

Do not use `Thread.sleep(100)` as a fix: sleeping for a duration does not create an HB relationship between producer and reader.

## 7. Which Reorderings Does `volatile` Forbid, and What Can It Not Do?

In the JMM, volatile reads and writes are **synchronization actions** with an ordering; compilers and CPUs must implement them so that outcomes conform to Java's memory rules. With the message-passing pattern:

```java
data = 42;        // Ordinary write
ready = true;     // Volatile write
```

and:

```java
if (ready) {      // Volatile read
    use(data);    // Ordinary read
}
```

This snippet is illustrative: `use` is a hypothetical method. The volatile write acts as a **release**, and the corresponding volatile read acts as an **acquire** in the common mental model. Effects prior to publication cannot vanish or be observed in a way that violates the required HB once the reader receives the publication.

That **does not mean** every ordinary variable system-wide suddenly becomes synchronized, or that the entire program is barred from optimization. Constraints only need to be strong enough to satisfy JMM behavior.

Three critical limitations:

1. **Does not make compound operations atomic:** `volatile int count; count++;` is still a read-modify-write and can lose updates.
2. **Does not create a critical section:** multiple threads can concurrently execute code after observing a volatile flag; there is no mutex protecting multi-field invariants.
3. **Does not guarantee timing or progress:** a volatile read does not wake up a worker that is in `sleep()`, waiting on a queue, or stuck on I/O; nor does it guarantee the scheduler grants CPU time promptly.

If you only need a stop flag or one-way publication, `volatile` may be appropriate. If you need atomic counter updates, use `AtomicInteger` or a lock; if you need multi-variable invariants, typically use `synchronized`/`Lock` or an ownership-transfer design.

## 8. `volatile` and the Litmus Test: What Does It Fix?

Returning to the `x` and `y` example. If **both are volatile**:

```java
static volatile int x;
static volatile int y;

// Thread A: x = 1; r1 = y;
// Thread B: y = 1; r2 = x;
```

Volatile accesses belong to a total synchronization order consistent with each thread's program order. If both threads read the initial value `0`, from the ordering:

```text
A: volatile write x=1  before  volatile read y=0
B: volatile write y=1  before  volatile read x=0
```

we would need an ordering cycle that contradicts synchronization order and the ordering of volatile writes and reads. Therefore, the outcome **`r1=0, r2=0` is forbidden** in the version where both `x` and `y` are volatile, with the same initialization and no third thread modifying them.

Crucial point: if you only change one field to volatile while conflicting ordinary accesses remain unsynchronized, you cannot conclude the program is correct. You must analyze **the entire protocol** and the HB relationships of every read and write.

## 9. `synchronized` Monitors: Mutual Exclusion Combined with Ordering and Visibility

A `synchronized` block or method on the same monitor solves two problems:

- **Mutual exclusion:** only one thread holds that monitor to execute the critical section at a time.
- **Memory ordering/visibility:** unlocking a monitor happens-before a subsequent lock on **that same monitor**.

Example using a monitor to pass a value:

Save as `MonitorPublicationDemo.java`:

```java
public class MonitorPublicationDemo {
    private static final class Mailbox {
        private int value;
        private boolean ready;

        synchronized void publish(int newValue) {
            value = newValue;
            ready = true;
            notifyAll();
        }

        synchronized int awaitValue() throws InterruptedException {
            while (!ready) {
                wait();
            }
            return value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Mailbox box = new Mailbox();

        Thread consumer = new Thread(() -> {
            try {
                System.out.println("Message: " + box.awaitValue());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();
        box.publish(42);
        consumer.join();
    }
}
```

```bash
javac MonitorPublicationDemo.java
java MonitorPublicationDemo
```

Stdout on a normal run:

```text
Message: 42
```

Why is the signal never lost even if the publisher runs before the consumer?

- Both `publish` and `awaitValue` synchronize on the same `Mailbox` object.
- The `ready` field is checked while holding the monitor; if it is already `true`, the consumer reads immediately without calling `wait`.
- If the consumer calls `wait()` first, it temporarily **releases the monitor**, allowing the publisher to enter, update both fields, and call `notifyAll()`; the consumer only resumes to read `value` after reacquiring the monitor.
- `while (!ready)` is more correct than `if` because spurious wakeups can occur or another thread might change the condition. `notifyAll()` does not allow the consumer to read outside the monitor.
- Writes before the publisher's unlock are guaranteed to be properly visible after the consumer reacquires the monitor.

This pattern combines a lock and a condition; in real multi-task code, you can use `BlockingQueue` or `CountDownLatch` instead of hand-rolling a condition when the contract fits better.

## 10. `Thread.start()` and `Thread.join()` Also Create Memory Ordering

Not every shared field needs to be volatile. When thread lifecycle operations already establish the right HB relationships, plain fields can be read safely at specific points.

Save as `JoinVisibilityDemo.java`:

```java
public class JoinVisibilityDemo {
    private static int result;

    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> result = 42);

        worker.start();
        worker.join();

        System.out.println("Result: " + result);
    }
}
```

```bash
javac JoinVisibilityDemo.java
java JoinVisibilityDemo
```

Exact stdout:

```text
Result: 42
```

The write `result = 42` in `worker` happens-before `main`'s actions after `worker.join()` succeeds. With a single writer as shown and no other concurrent accesses to `result`, `volatile` is unnecessary.

However, if `main` reads `result` **before** `join()` while `worker` is still running, that is a different access pattern and requires separate synchronization analysis. Similarly, `start()` publishes actions that occurred before `start()` to the new thread; it does not automatically synchronize writes made **after** `start()` in the parent thread.

**Polling `Thread.getState()` cannot replace the completion semantics of `join()`.** You need a primitive with an explicit completion/HB contract.

## 11. `Future.get()`, Queues, and Library-Level Happens-Before Edges

Utilities in `java.util.concurrent` have **memory consistency effects** documented in their APIs. Common examples:

| Mechanism | Guarantee to Rely On |
| --- | --- |
| `ExecutorService.submit(...)` | Actions before submitting the task happen-before actions inside the task |
| `Future.get()` | Actions of the task happen-before actions after the caller retrieves the result via `get()` |
| `BlockingQueue.put/take` | Actions before placing an element into the queue happen-before actions after another thread takes that element |
| `CountDownLatch.countDown/await` | Actions before `countDown()` happen-before actions after a corresponding `await()` returns normally |
| `synchronized` on the same monitor | Unlock happens-before subsequent lock of the same monitor |
| `volatile` | Write happens-before subsequent volatile reads of the same variable under JMM rules |

A clear `Future` example:

Save as `FutureVisibilityDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureVisibilityDemo {
    private static int result;

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<?> future = executor.submit(() -> result = 42);

            future.get(); // Wait for completion and establish the HB edge.
            System.out.println("Result: " + result);
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac FutureVisibilityDemo.java
java FutureVisibilityDemo
```

Exact stdout:

```text
Result: 42
```

Here, the task writes to the ordinary field `result`, and `main` only reads it after `get()` succeeds. The state of `result` is published under `Future`'s memory consistency contract. If multiple tasks continue overwriting `result` afterward, `get()` on a single task is not enough to protect a read against the remaining writers.

General takeaway: higher-level synchronization APIs such as futures or queues are usually much easier to use correctly than inventing two boolean flags and relying on unsynchronized reads/writes.

## 12. Reordering Guarantees Do Not Make `count++` Atomic

Suppose:

```java
private static volatile int count;

static void increment() {
    count++;
}
```

This snippet illustrates an anti-pattern, not a standalone program. `volatile` gives each individual read and write of `count` volatile semantics. However, `count++` still consists of logical steps:

```text
Thread A                    Thread B
read count = 5
                            read count = 5
compute 6
                            compute 6
write count = 6
                            write count = 6
```

The result can be `6` after two increments instead of `7`. **Ordering/visibility does not automatically guarantee atomicity for read-modify-write operations**.

Fix it with an atomic operation:

```java
import java.util.concurrent.atomic.AtomicInteger;

final class Counter {
    private final AtomicInteger count = new AtomicInteger();

    int incrementAndGet() {
        return count.incrementAndGet();
    }
}
```

Or use `synchronized` for a proper critical section. If an invariant spans multiple variables, you must protect the entire transaction, not just individual reads and writes.

## 13. Safe Publication: Initialize Completely Before Publishing

An object can have multiple interrelated fields. If one thread creates an object, initializes its fields, and passes the **reference** to another thread without safe publication, the reader may not be guaranteed to see the constructed state as expected under the JMM.

Dangerous pattern:

```java
class Config {
    int port;
    String host;
}

class UnsafeConfigHolder {
    Config config; // Plain reference, no publication protocol.

    void initialize() {
        Config c = new Config();
        c.port = 8080;
        c.host = "localhost";
        config = c; // Another thread reads config without synchronization.
    }
}
```

This is a buggy illustration, not a complete runnable program. You must not argue that "because `config = c` is last, every thread is guaranteed to see all the new fields." Without HB, publishing a reference through a plain field while a reader accesses it without synchronization **provides no such guarantee**.

A simple solution is an **immutable snapshot + volatile reference**, when the fields and contained objects have genuinely immutable semantics:

```java
record Config(int port, String host) {}

final class ConfigHolder {
    private volatile Config current = new Config(8080, "localhost");

    void update(int port, String host) {
        current = new Config(port, host);
    }

    Config snapshot() {
        return current;
    }
}
```

`Config` is a record holding `int` and `String` (both immutable), making it very easy to reason about the published state. Each `snapshot()` call grabs **a single reference** to a complete value. The volatile write/read provides proper publication; readers never observe an object being mutated field by field mid-flight.

If a record contains a `List<Item>` where `Item` is mutable, the record is **not automatically deep-immutable**; you need defensive copies, ownership boundaries, or protection for the elements as required.

## 14. `final` Fields and Initialization Boundaries

The JMM has special rules for **final fields** when an object is properly constructed: final fields initialized in a constructor carry stronger visibility guarantees than ordinary fields in scenarios involving constructor freeze. Even so, there are limits:

- **Do not let `this` escape the constructor** before initialization finishes. For example, do not register a listener pointing to `this` or start a thread using `this` mid-constructor.
- `final List<String> items` only fixes the **reference**; it does not prevent `items.add(...)` and does not automatically make the list thread-safe.
- Distinguish between **proper object initialization** and **subsequent mutable state updates**; final field rules do not protect later mutations.
- Safe publication remains the preferred design for handing objects between threads and protecting relationships across mutable data.

`final` fields are well suited for value objects and invariants, but they are not a "trick" to fix all data races.

## 15. Double-Checked Locking and the Role of `volatile`

The traditional lazy-initialization singleton example checks quickly without locking, then checks again inside a lock:

```java
final class LazyService {
    private static volatile LazyService instance;

    private LazyService() {
    }

    static LazyService getInstance() {
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

This is a complete illustrative class without a `main` method because the focus is the initialization protocol.

**Why is `volatile` important?**

- The writer must construct the object and then **publish the reference** through the volatile field.
- A reader on the fast path may see a non-null reference and use it **without acquiring the monitor**. The volatile read ensures publication aligns with writes that occurred before the volatile write.
- If `volatile` is removed, the fast-path non-null check has no synchronization with the writer; in modern Java this is not considered a valid double-checked locking implementation.
- The check inside `synchronized` prevents multiple threads from concurrently creating instances while `instance` is still null.

For simple singletons, a static holder or enum is usually easier to understand. If the constructor lets `this` escape prematurely or the object holds mutable state needing later protection, a volatile singleton reference does not solve those issues by itself.

## 16. CPU Memory Barriers and the JMM: The Right Mental Model

In hardware terminology, a **memory fence/barrier** is a mechanism that restricts certain reorderings and memory observations. The JVM may use fence instructions, JIT constraints, acquire/release operations, or instructions with appropriate ordering semantics to implement the JMM on specific hardware.

There is no simple rule that "every `volatile` always emits the exact same fence instruction on every CPU/JDK." The JMM specifies **required effects**, not a fixed machine instruction. Across different platforms, compilers and CPUs may enforce different constraints to satisfy the same Java contract.

Java also provides advanced APIs such as `VarHandle` with `ordinary`, `opaque`, `acquire`, `release`, and `volatile` access modes. These serve specialized concurrent protocols; choosing the wrong mode can leave ordering insufficient. Arbitrarily placing a pair of fence calls **does not by itself establish a valid publication protocol** without matching paired operations and read/write conditions.

When learning reordering, master `volatile`, `synchronized`, and standard concurrent primitives first. Only reach for `VarHandle`, fences, or lock-free algorithms when you have a clear requirement and can verify the algorithm's JMM conditions.

## 17. Do Not Use `sleep()` or Logging to "Fix" Ordering Issues

The following changes sometimes make a bug rarer, but they do not build a synchronization contract:

- Inserting `Thread.sleep(10)` between two operations.
- Printing `System.out.println(...)` inside a loop and seeing the bug disappear.
- Changing JIT optimization levels and concluding the race is fixed.
- Running a thread in a debugger and getting consistent results.
- Switching from a multi-core machine to a machine with fewer cores and seeing tests pass.

Some logging or debugger actions can **alter scheduling and introduce incidental synchronization**, making a race harder to reproduce. You must never rely on such side effects to guarantee shared-data behavior. A sound design explicitly identifies **publication points and HB edges** in business code.

To tell them apart, ask yourself: "If I remove all `sleep` calls, logs, and breakpoints, what synchronizes-with relationship remains between writer and reader?" If none, revisit the protocol.

## 18. When Is Reordering Allowed and When Is It Constrained?

| Scenario | Can another thread be assumed to see source order? | Reason |
| --- | --- | --- |
| Two ordinary fields, unsynchronized writer and reader | **No** | No HB between conflicting accesses |
| Writer writes data then volatile flag; reader sees flag then reads data | **Yes, within the analyzed publication scope** | Volatile write/read creates HB, and HB is transitive |
| Writer unlocks monitor; reader locks same monitor before reading | **Yes, for properly protected writes/reads** | Unlock/lock on the same monitor establishes HB |
| `main` calls `start()` after configuring data; worker reads initial data | **Yes, for actions occurring before `start()`** | Thread start creates HB |
| `main` reads result after `worker.join()` succeeds | **Yes, for actions before worker termination**, if no other conflicting writers exist | Thread termination/join HB |
| `main` reads result after `Future.get()` succeeds | **Yes, per Future's memory consistency effects** | Task actions HB caller after `get()` |
| Only using `Thread.sleep(...)` to wait for writer | **No** | Sleep is neither publish nor acquire |
| `volatile count++` from two writers | **No guarantee on total increment count** | Volatile ordering does not create atomic read-modify-write |

This table describes **guarantees of a specific protocol**, not a promise that an object stays immutable forever after publication. If new writers appear, you must re-examine HB edges and invariants at the time of reading.

## 19. Reordering, Visibility, and Atomicity: Three Concerns to Separate

| Aspect | Question | Tools / Examples |
| --- | --- | --- |
| Ordering | Can actions be observed out of the order required by the protocol? | Volatile publication; lock/unlock; HB |
| Visibility | Is the reader guaranteed to observe a prior write? | HB edges via volatile, monitor, start/join, future, queue |
| Atomicity | Can a sequence of operations interleave mid-way and break an invariant? | `AtomicInteger.incrementAndGet()`, proper CAS, critical section |
| Progress / liveness | Can the task continue and terminate? | Signaling, timeout, interruption, deadlock prevention |

A program can solve ordering/visibility for a flag and still be broken because it uses `count++` from multiple writers. Or it can have atomic increments while a worker deadlocks on another lock. **The JMM does not replace coordination and lifecycle design**, and thread-safety requirements must be evaluated at concrete business boundaries.

## 20. How to Analyze a Piece of Multithreaded Code

When you encounter a situation that "reads right single-threaded but fails under multiple threads," follow these steps:

1. **List shared variables:** Which fields can be read/written by at least two threads? Are there mutable objects or collections behind a shared reference?
2. **Mark conflicting accesses:** Are there reads/writes to the same variable where at least one is a write?
3. **Find HB edges:** Are volatile reads/writes on the same variable, monitor lock/unlock on the same object, thread start/join, future/queue/latch, or another mechanism with a memory consistency contract in use?
4. **Identify invariants:** Do you only need to publish a snapshot, or do you need atomic read-modify-write or simultaneous multi-field updates?
5. **Design publication:** Use immutable snapshot + volatile reference, `synchronized`, atomic types, concurrent collections, or appropriate single-owner/message-passing patterns.
6. **Ensure progress:** Is there any risk of infinite spinning, indefinite blocking, missed signals, deadlock, or cancellation without cleanup?
7. **Verify against the contract**, and only then stress-test and measure performance. Tests can uncover bugs, but passing results over a few runs do not prove the absence of races.

For example, if an application has `volatile boolean done` while multiple workers simultaneously increment an ordinary `int processed`, the `done` flag will not fix lost increments **among the workers**. You must resolve atomicity or ownership of `processed` before using the flag to publish the result.

## 21. Self-Check Questions

**1. Is the Java compiler allowed to optimize or swap two operations without preserving source-order machine instructions?**

Yes, provided the outcomes and constraints required by the JMM are preserved. You cannot infer machine instruction order or another thread's observation order from source order without synchronization.

**2. Why might `data = 42; ready = true;` not be enough for another thread?**

If `data` and `ready` are ordinary shared fields without synchronization, there is no HB guaranteeing that the reader sees `ready` and the correct payload. Use a proper volatile publication protocol, a monitor, or another mechanism to establish HB.

**3. In the `x=1; r1=y` and `y=1; r2=x` litmus test, can two ordinary variables yield both `r1` and `r2` equal to `0`?**

Yes, under the JMM. However, a single run may not observe that outcome; you cannot assert from output exactly what the CPU or JIT did.

**4. If both `x` and `y` are volatile in the same litmus test, is the `0,0` outcome still valid?**

No, under the stated model assumptions, because volatile actions must follow a synchronization order consistent with program order and cannot form the ordering cycle needed for both reads to see `0`.

**5. Why can `volatile count++` still lose increments?**

Because incrementing is a sequence of read, compute, and write. `volatile` does not merge them into a single atomic operation. Use `AtomicInteger` or a lock protecting the entire increment.

**6. Does `Thread.join()` fix a race between two workers concurrently reading and writing shared state while running?**

No. `join()` lets `main` wait and observe completed work; it does not provide mutual exclusion or sufficient ordering between two workers concurrently updating the same data beforehand.

**7. Does cache coherence mean Java automatically sees all writes in source order across all threads?**

No. Cache coherence is not a language-level JMM contract across multiple addresses and unsynchronized actions. HB must be analyzed under Java's rules.

**8. Can you fix an ordinary-flag polling loop by adding `Thread.sleep()`?**

No. Sleep only delays execution; it does not create a publication edge between writer and reader. Replace the flag with `volatile` under a proper protocol or use a coordination primitive.

**9. Do `record` and `final` eliminate all reordering risks with shared mutable state?**

No. Immutable values reduce issues, but a record containing mutable elements can still be modified. You still need proper construction, no `this` escape in the constructor, safe publication, and protection for any later mutations.

## 22. Key Takeaways

- **Reordering** is about how actions are executed and observed under JMM constraints; source order is not an observation guarantee between unsynchronized threads.
- **Compiler/JIT, CPU, and the memory subsystem** can all influence how reads/writes manifest, but an anomalous result does not prove a single-layer cause.
- **Happens-before** is the primary tool for reasoning about ordering and visibility. Program order plus synchronizes-with is transitive.
- **`volatile`** fits certain publication/flag protocols. It does **not** make `count++` atomic or replace locks for multi-step invariants.
- **`synchronized`**, thread `start/join`, `Future.get()`, and queues/latches have specific memory consistency effects; choose the tool matching the required guarantee.
- **Safe publication** and immutable data prevent many subtle bugs; conversely, a data race can lurk even when tests frequently pass.
- **`sleep`, logs, breakpoints, or intuition about CPU caches** are not substitutes for synchronization design.

When diagnosing Java concurrency bugs, explicitly identify the **writer**, **reader**, conflicting operations, **atomicity** boundaries, and **happens-before** edges. This way of reasoning holds up far better across changes in JIT, CPU, and memory subsystems than guessing execution order from source code.
