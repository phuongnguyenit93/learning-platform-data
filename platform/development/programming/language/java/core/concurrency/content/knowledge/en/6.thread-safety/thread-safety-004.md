# Thread Confinement and Explicit Ownership in Java Concurrency

> **Scope:** designing for thread safety by **confining where mutable state is accessed** and **defining a clear owner** for the data. This content applies to Java SE (Java 17+), using standard APIs such as `ExecutorService`, `Future`, `BlockingQueue`, and `ThreadLocal`. Spring-specific implementation concerns are covered in a dedicated chapter.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain **thread confinement**: a mutable object is used by only one thread at a time, and why this can eliminate the need for locking during internal operations.
- Distinguish between **thread confinement**, **task confinement**, **ownership**, **immutable data**, **shared mutable state**, and **safe publication**.
- Recognize when a reference **escapes** its controlled scope, breaking confinement even if the object was created in a local variable.
- Design **ownership handoff** via queues, `Future.get()`, `join()`, or protocols with *happens-before* guarantees; avoid continuing to mutate an object after transferring ownership.
- Use `ThreadLocal` properly with thread pools, know when to call `remove()`, and understand why thread-local **differs** from data scoped to a single request/task.
- Choose between **single owner**, immutable data, partitioning, and locks/atomics according to the problem's invariants.
- Verify correctness and avoid data races, visibility issues, non-deterministic processing order, aliasing, and state leaks across tasks.

**Core idea:** instead of letting multiple threads directly update the same structure and trying to lock everywhere, you can design the system so that **only one thread owns that mutable state**, while other threads send work or independent data copies to the owner. Ownership must be enforced by the API and actual data flow; a comment saying "only used by this thread" does not create safety on its own.

## 2. Why Is Limiting Sharing Often Simpler Than Locked Sharing?

In a sequential program, an `ArrayList`, `HashMap`, or `StringBuilder` can be freely mutated when there is no concurrent access. When multiple threads share the same mutable object without a coordination protocol, operations such as read-then-write, check-then-act, or multi-field updates can interleave and break invariants.

Consider a hypothetical example where both threads act on the same list:

```java
// Illustration of unsafe concurrent access:
List<Integer> numbers = new ArrayList<>();
// Thread A: numbers.add(1);
// Thread B: numbers.add(2);
```

This snippet requires importing `java.util.ArrayList` and `java.util.List`; the thread lines are **illustrative**, not a standalone program. `ArrayList` does not guarantee thread safety for multiple concurrent writers. You should not expect the result to always contain both elements or for the structure to remain in a consistent state.

There are two common design approaches:

1. **Controlled sharing:** multiple threads access shared state using the same lock, atomic, or concurrent collection appropriate for the invariant.
2. **Reduced sharing:** each worker processes its own private state; when exchange is needed, it sends immutable values, snapshots, or commands to a single responsible owner.

Confinement eliminates races on an object **only when the condition of no concurrent access outside the owner truly holds**. It does not automatically make I/O operations or multi-service transactions atomic, does not make the scheduler deterministic, and does not replace ordering constraints required at data-transfer boundaries.

## 3. Concepts to Distinguish

| Concept | Meaning | Example |
|---|---|---|
| **Thread confinement** | A mutable object is used within the scope of a single thread and is not accessed by other threads while still mutable. | A `StringBuilder` used only by the current worker. |
| **Task confinement** | Data and logic private to a single task, not accessed by other tasks during execution. | A local `ArrayList` created inside `Callable.call()`. |
| **Ownership** | Who has **read/write permission**, when that permission begins/ends, and which API is the valid access path. | A single consumer updates the ledger; producers only send commands. |
| **Ownership transfer** | The right to process an object moves from sender to receiver across a clear boundary. | A producer puts a message into a `BlockingQueue` and does not mutate that mutable message afterward. |
| **Immutable object** | Observable content does not change after construction and proper publication. | `String`, `Integer`, or a record containing only immutable components. |
| **Safe publication** | The way an object and its initialized state are made observable to other threads under the guarantees of the Java Memory Model. | Data sent through a `BlockingQueue` or results read via `Future.get()`. |
| **Shared mutable state** | An object that can be mutated and is accessible by multiple threads. | The same `HashMap` updated by multiple workers. |

**Confinement is a property of reference paths and usage**, not of the data type itself. The same `ArrayList` can be safe when completely local, yet become shared mutable state when its reference is passed to another worker while the previous owner continues mutating it.

**Ownership here is a design convention** enforced and verified by the program. Java does not have a built-in ownership/borrow-checker type system to prevent you from arbitrarily sharing mutable objects. To make the convention strong enough, you need private fields, immutable messages, APIs that restrict mutation, handoff protocols, and appropriate tests/invariants.

## 4. Three Common Levels of Confinement

### 4.1. Local Variables and Objects Used Only Within a Single Call

```java
String buildLine(String name, int score) {
    StringBuilder builder = new StringBuilder();
    builder.append(name).append(':').append(score);
    return builder.toString();
}
```

This is an **illustrative method** placed inside a class. `builder` is created, used, and discarded within a single invocation; the method returns an immutable `String`. Because calls from two threads do not share the `builder` reference, each invocation has its own state and does not need `synchronized` around `append`.

**Be careful:** "local variable" does not mean "private object":

```java
// Illustration of reference escape risk.
ArrayList<String> local = new ArrayList<>();
someSharedObject.store(local); // Another thread may receive this exact object.
local.add("changed");          // There is no longer a basis to claim it is confined.
```

The snippet above assumes `someSharedObject` has a `store` method and is not a standalone runnable class. Allowing a reference to escape **can** lead to sharing; the risk materializes if the object is used concurrently without coordination. To stay safe, either keep it completely local, or pass an **immutable snapshot** or perform a handoff with a clear contract.

An object created in a constructor is also not automatically safe: if `this` escapes before initialization completes (e.g., registering a callback, starting a thread holding `this`, or adding to a global registry), another thread may observe an incomplete state. Finish initialization before publishing via an appropriate mechanism.

### 4.2. A Worker Owning State Throughout Its Execution Phase

A worker processes each piece of data in a local collection:

```java
// Inside Callable<List<String>>.call()
List<String> results = new ArrayList<>();
for (String item : input) {
    results.add(transform(item));
}
return List.copyOf(results);
```

This is an **illustrative code snippet**, where `input` and `transform` are provided by the problem. Each task creates its own `results`, and no other thread mutates it concurrently. `List.copyOf` creates a structurally unmodifiable list; for the data to be **deeply immutable**, the `String` elements themselves in this example must also be immutable. If the elements are mutable beans, copying the list does **not** freeze the beans.

### 4.3. A Long-Lived Single Owner for Shared State

For example, a consumer manages a balance in a variable that exists only on its thread. Producers do not own the balance; they send `Add(amount)` commands through a queue. Only the consumer is allowed to apply commands, so **all balance updates are serialized within one owner**. External code never obtains a reference to the mutable variable to modify it directly.

This is the **single-writer / actor-style ownership** model at the design level, which can be built using Java SE `BlockingQueue`. You do not need an actor framework to apply this principle.

A single owner often simplifies the invariants of the state it holds. However, if different pieces of state need to commit atomically together, per-owner ownership **does not automatically provide cross-owner transactions**.

## 5. Explicit Ownership: Who Can Do What, and When?

A solid design should have concrete answers to these questions:

1. **Who creates the object?** Who holds the initial mutable reference?
2. **Who is allowed to mutate it?** A single thread, a single task, a long-lived consumer, or multiple threads under the same lock?
3. **When does ownership transfer?** When placed into a queue, when a `Future` completes, when `join` finishes, or after which synchronization operation?
4. **What may the sender still do?** Is it allowed to continue mutating the message after `put()`? If not, how are unintended write paths prevented?
5. **How does the receiver know the data is ready?** Is there a happens-before relationship to observe the correct values?
6. **Who cleans up resources at shutdown?** Does the owning thread close files/sockets/contexts and report errors to the caller?

### An Owner Convention Should Be Expressed Through the API

Conceptual API example:

```java
interface LedgerCommands {
    void submitCredit(long amount) throws InterruptedException;
    // Do not return the internal mutable Map<Long, Account> for callers to mutate.
}
```

This is an **illustrative interface**. The producer only submits commands, and the consumer owns the data. If results are needed, provide a **snapshot**, `Future`, or response message with clear memory visibility and lifecycle rules. Do not return a reference to an internal `HashMap`/`ArrayList` and hope callers "remember not to mutate it."

## 6. Ownership Transfer vs. Sharing the Same Reference

When two threads process a mutable object sequentially, you can use a **handoff**:

```text
Producer thread                              Consumer thread
------------------------------------------   -----------------------------------
Create object, owner = producer
Populate all data
Put message into BlockingQueue
Do not mutate or read-mutate after handoff
                                             queue.take() receives message
                                             owner = consumer
                                             Read/write state per contract
                                             Create snapshot / send response
```

With `BlockingQueue`, actions in a thread prior to placing an element into the queue *happen-before* actions in another thread subsequent to accessing or removing that element from the queue, per the memory consistency contract of `java.util.concurrent`. This guarantees **publication/visibility** through the queue.

However, a handoff has **two independent conditions**:

- **Visibility/order:** the receiver must observe the data prepared before sending; a queue, `Future`, or lock can provide HB.
- **Exclusive ownership:** the sender **must not continue mutating** the object after handoff if the receiver may be using it; the queue **does not** erase references still held by the producer.

It is wrong if the producer continues modifying `message` after `queue.put(message)` while the consumer reads concurrently: the queue guarantees visibility for writes **before put**, not safety for writes **after put**. If both sides need to read, use an immutable object/snapshot; if both need to write, you must have a back-and-forth ownership-transfer protocol or protect all accesses with appropriate synchronization.

This is the difference between **safe publication** and **ongoing thread safety**: a properly published object can still suffer data races if mutated concurrently later.

### Clarifying Aliasing

Two differently named variables can still point to **the same object**:

```java
ArrayList<Integer> first = new ArrayList<>();
List<Integer> second = first;
second.add(1);
System.out.println(first); // [1]
```

This snippet can compile inside a method (requiring imports for `List` and `ArrayList`). This is normal aliasing, not a race by itself. However, if thread A uses `first` and thread B uses `second` concurrently, confinement is broken because they refer to **a single object**. To create two independent copies, copy with the appropriate semantics; a shallow copy does not separate mutable elements.

## 7. Safe Publication and the Java Memory Model

Confinement does not require synchronization for every update step **inside a single owner**. However, when data changes owners or is published, the Java Memory Model still matters.

Common valid boundaries:

| Boundary | Relevant Guarantee | Use Correctly When |
|---|---|---|
| `Thread.start()` | Actions before `start()` HB actions in the started thread. | Preparing data before the thread starts. |
| Successful `Thread.join()` | Actions in the terminated thread HB actions in another thread after confirming termination via join. | Owner finishes, then caller reads/collects results. |
| `ExecutorService.submit()` → `Future.get()` | Actions before submit HB the task; task actions HB actions after successful `Future.get()`. | Returning results from worker to caller. |
| `BlockingQueue.put/offer` → `take/poll` receiving element | Actions before placing the element HB actions after removing/accessing the element in another thread. | Sending data/commands between owners. |
| `synchronized` unlock → lock on same monitor | Release/Acquire establishes `synchronizes-with` and HB ordering. | Sharing mutable state with locking. |
| Appropriate `volatile` write → read | Guarantees ordering/visibility related to the volatile variable. | Flags/simple publication with a proper protocol; no compound atomicity. |

HB guarantees visibility/ordering of the related actions. **HB does not mean an object is automatically immutable, nor does it force threads to complete on a single fixed schedule.**

With `Future.get()`, the caller should handle `ExecutionException` and `InterruptedException`; a cancelled or incomplete call cannot be treated as having a ready result. For APIs that return results under specific contracts, read the corresponding Javadoc rather than assuming a `sleep` is enough to safely receive an object.

**`final` fields and immutable objects:** Java provides special guarantees for `final` fields when an object is properly constructed and `this` does not escape during construction. However, `final List<T> items` only prevents the `items` reference from being reassigned; if the list is still mutable and shared, its elements can still change. Distinguish between **immutable reference**, **immutable container**, and **deeply immutable object graph**.

## 8. Hands-On Java 17+ Example: Task-Local Data and Single Owner

The program has two parts:

- Two `Callable` instances each build their **own** `ArrayList<Integer>` and return `List.copyOf(local)`. The caller retrieves both results via `Future.get()` and merges them on the main thread.
- A single thread owns the `balance` variable. Main sends addition commands through an `ArrayBlockingQueue`; the consumer is the **only place** that updates `balance`. The `Integer` values sent through the queue are immutable.

Create the file **`OwnershipDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class OwnershipDemo {
    static final class BuildChunk implements Callable<List<Integer>> {
        private final int first;
        BuildChunk(int first) { this.first = first; }

        @Override
        public List<Integer> call() {
            ArrayList<Integer> local = new ArrayList<>();
            local.add(first);
            local.add(first + 1);
            return List.copyOf(local);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<List<Integer>> one = executor.submit(new BuildChunk(1));
            Future<List<Integer>> two = executor.submit(new BuildChunk(3));

            List<Integer> merged = new ArrayList<>();
            merged.addAll(one.get());
            merged.addAll(two.get());
            System.out.println("merged=" + merged);
            System.out.println("sum=" + merged.stream().mapToInt(Integer::intValue).sum());
        } finally {
            executor.shutdown();
        }

        BlockingQueue<Integer> inbox = new ArrayBlockingQueue<>(4);
        Thread owner = new Thread(() -> {
            int balance = 0; // Only this thread is allowed to mutate it.
            try {
                while (true) {
                    int command = inbox.take();
                    if (command == Integer.MIN_VALUE) break; // Stop after commands.
                    balance += command;
                }
                System.out.println("ownerTotal=" + balance);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "account-owner");

        owner.start();
        inbox.put(5);
        inbox.put(7);
        inbox.put(Integer.MIN_VALUE);
        owner.join();
    }
}
```

Run with JDK 17 or newer:

```bash
javac --release 17 OwnershipDemo.java
java OwnershipDemo
```

**Verified stdout:**

```text
merged=[1, 2, 3, 4]
sum=10
ownerTotal=12
```

### Why Is the Result Correct Despite a Non-Deterministic Scheduler?

1. Each `BuildChunk.call()` creates and mutates the `local` list **only within that task's worker**; workers do not share a mutable list.
2. `List.copyOf(local)` returns a list that does not support structural modification. Each element is an immutable `Integer`, so the result contains no mutable objects needing extra coordination.
3. Main calls `one.get()` and `two.get()` in a **fixed order** before calling `addAll` on `merged` (owned by main). Even if the second task finishes first, the merged order is still `[1, 2, 3, 4]`. `Future.get()` gives the caller a completion boundary and proper memory consistency.
4. `balance` is a local variable inside the consumer's lambda and **is not exposed externally** for other threads to mutate. Commands sent to the queue are taken by the consumer in the FIFO order of `ArrayBlockingQueue`.
5. Main sends `5`, `7`, and then the sentinel `Integer.MIN_VALUE`. The consumer processes the first two numbers and then stops; the result is always `12` on normal completion.
6. `owner.join()` waits for the receiver to finish before main exits; the program does not rely on delays or `sleep()`.

**Intentional limitations of the example:** the sentinel `Integer.MIN_VALUE` is a reserved termination signal, so a real system must ensure this value **is not valid data**, or should use separate message types such as `record Add(int amount)` and `enum Stop`. The example uses only **one producer** to make FIFO order clear; with multiple producers, messages from different producers can interleave, and defining business ordering requires a clear contract. If the consumer throws an exception, a real system must report the error rather than failing silently: e.g., via a `Future`, response channel, or completion signal. `shutdown()` here stops accepting new tasks for the executor; in long-running applications, you need a lifecycle await/close strategy and cancellation handling.

**Key takeaway:** there is no `synchronized` around each addition to `balance`, because no second thread updates that variable. Yet `BlockingQueue` is still a synchronization primitive between threads. "No locks needed for local state" **does not mean cross-thread communication needs no synchronization**.

## 9. ThreadLocal: A Value Instance Bound to Each Thread

`ThreadLocal<T>` gives **each thread** its own value for the same `ThreadLocal` key. It is useful for auxiliary state that needs to be tied to a thread, such as a short-lived buffer you do not want to pass through many method layers, but its limitations must be understood.

Example:

```java
private static final ThreadLocal<StringBuilder> BUFFER =
        ThreadLocal.withInitial(StringBuilder::new);

static String format(String name, int quantity) {
    StringBuilder builder = BUFFER.get();
    try {
        builder.setLength(0);
        builder.append(name).append(':').append(quantity);
        return builder.toString();
    } finally {
        BUFFER.remove();
    }
}
```

These are **illustrative members of a class**; the default `java.lang` import is sufficient. `BUFFER.get()` in each thread returns that thread's `StringBuilder` instance. Because each `StringBuilder` is used only by its associated thread and is not published to other threads, the append operations do not need synchronization.

**Why call `remove()`?** Workers in an `ExecutorService` can be reused across many different tasks; a `ThreadLocal` value can outlive a task on the worker and leak state, memory, or data from a previous task into the next one. Calling `remove()` in `finally` clears the current thread's binding even if the task throws an exception. For a simple single-method use case, a local `new StringBuilder()` variable is usually clearer and avoids managing `ThreadLocal` lifecycle.

### Important Limitations of ThreadLocal

- **Thread-local does not mean request-local or task-local.** Two requests running sequentially on the same pooled thread can see the same value if not reset/removed; a single request switching to another thread will see a different value.
- `ThreadLocal` does not deep-copy the object stored in it. If two threads call `set(sharedMutableObject)` with **the same object reference**, both can still race on that object even though their `ThreadLocal` keys are separate.
- `ThreadLocal` does not create locks or transactions for shared resources (files, DB, sockets, static maps).
- `InheritableThreadLocal` has different inheritance semantics, does not make state safe when mutable data is shared, and should not be assumed to propagate properly across thread pools.
- Do not use `ThreadLocal` to hide important business parameters to the point where ownership, cleanup, or data flow becomes invisible. Explicit context is usually easier to test.
- With **virtual threads (Java 21+)**, `ThreadLocal` still exists, but each virtual thread has its own lifecycle; creating a huge number of threads with heavy state can consume significant memory. Do not design logic assuming "a specific thread will be reused" when using virtual threads.

## 10. Single-Writer Ownership vs. synchronized / Atomic

Confinement is a **design choice**, not always the optimal replacement for other mechanisms.

| Scenario | Suitable Approach | What Must Be Proven |
|---|---|---|
| Each task computes an independent result | Local state then immutable result / `Future.get()` | No mutable object escape; result is properly published |
| Multiple producers emit commands, one state owner | `BlockingQueue` + single consumer | Correct ordering, backlog/backpressure, shutdown, error handling |
| Multiple tasks access the same invariant needing immediate response | `synchronized` / `ReentrantLock` | All relevant reads/writes use the same protocol |
| Independent counter updated from multiple threads | `AtomicInteger` / `LongAdder` (per required semantics) | Appropriate atomicity and snapshot semantics |
| Each key can be processed independently | Partition/sharding by key and owner | No cross-partition updates breaking invariants |
| Data shared for reading, never mutated | Safely published immutable snapshot | No nested mutable references retained |
| Small per-thread auxiliary buffers | Local variable or `ThreadLocal` | No shared references; cleanup if using a pool |

**Thread confinement does not mean "thread affinity is free."** Funneling all requests through a single owner reduces update contention, but it can create a queue bottleneck, increase latency, overflow queues, or overload one thread. For independent CPU-bound tasks, partitioning across multiple owners can utilize more cores.

**Use one owner per invariant** when correctness is simpler that way; if state must be updated atomically across multiple owners, you may need a more complex coordination protocol. Do not split ownership just to add parallelism if you cannot preserve the invariants.

## 11. Common Pitfalls: "Only One Thread Mutates" Can Still Be Wrong

### 11.1. One Side Uses a Lock, the Other Reads Directly

```java
// Incorrect illustration when accessing the same state without a shared protocol.
synchronized (guard) {
    sharedValue++;
}
// In another thread: int value = sharedValue; // read without the same lock/HB
```

This is an illustrative snippet with `guard` and `sharedValue` already declared. Proper locking by the writer is insufficient if a reader reads mutable state without a happens-before relationship. Confinement is only valid when readers **do not read directly** during single-owner possession; send a snapshot or use the same synchronization protocol.

### 11.2. Mutating an Object After Handoff

```java
// Incorrect illustration if the producer continues mutating after publication.
List<String> message = new ArrayList<>();
message.add("before");
queue.put(message);
message.add("after"); // consumer may already be reading message.
```

This is an illustrative snippet inside a method with `throws InterruptedException`, assuming `queue` is a `BlockingQueue<List<String>>`. `put` guarantees visibility for actions **before put**; it does not make concurrent mutation safe. Fix this by using an immutable `List.copyOf(message)`, a strict ownership handoff, or a lock covering all reads/writes.

### 11.3. Returning a Reference to Internal State

```java
class Owner {
    private final List<String> data = new ArrayList<>();

    List<String> getData() {
        return data; // caller can mutate without the owner knowing.
    }
}
```

This illustrative class requires importing `java.util.List` and `java.util.ArrayList`. `private` only protects the **field reference** from direct access, whereas the method exposes the mutable object externally. Return a snapshot `List.copyOf(data)` while on the owner or under the appropriate lock; if elements are mutable, also snapshot/copy to the depth required by the contract.

### 11.4. Using ThreadLocal to Hold Request "Ownership" in a Pool

If a task stores data in `ThreadLocal` and a subsequent task may run on a **different worker**, the request context does not follow the task. If the next task runs on the **same worker**, stale values from the previous request may remain. Therefore, `ThreadLocal` is not a tool for guaranteeing per-request ownership; use explicit parameters, immutable context, or a context-propagation API with a clear lifecycle.

### 11.5. Single Writer with Uncoordinated Readers

**Single-writer does not automatically imply all readers are thread-safe.** If a writer mutates a `HashMap` while another reader iterates over it without synchronization, a data race still occurs; a single writer only prevents *writer–writer races*, not *writer–reader races*. You need immutable snapshots, copy-on-write, read/write locking, or a protocol where readers never access state while it is being mutated.

### 11.6. Holding Mutable References Inside an Immutable Wrapper

`List.copyOf(list)` makes **the resulting list unable to add/remove elements**, but if an element is a mutable `Order`, `get(0).setStatus(...)` can still mutate that object. Java `record` types also only make component fields `private final` by default; a record containing `List<MutableItem>` is not automatically deeply immutable. You need defensive copies, immutable element types, and appropriate constructors/accessors.

### 11.7. Confusing Dequeue Order with Completion Order

A FIFO queue for one consumer determines the order in which commands are **received** relative to enqueue order, but a system with multiple producers has a non-deterministic global enqueue order; adding asynchronous I/O can also cause side effects to complete out of order. If business logic requires total order, sequence numbers, or a coordinating owner, you must explicitly define the points of ordering and completion.

## 12. Owner Lifecycle and Failures

Owner design does not stop at "the consumer is the only thread that mutates state." It must also address practical scenarios:

1. **Startup:** is the owner created before receiving commands, or can the queue buffer commands while the owner starts up?
2. **Shutdown:** does the caller send a termination signal after all producers finish? Should the queue be drained or remaining tasks dropped? Could a sentinel collide with real data?
3. **Backpressure:** is the queue bounded or unbounded? `put()` blocks when full, while `offer(timeout)` can report failure; that policy must be explicit.
4. **Exceptions:** if a handler fails, must the owner report the error to the caller while keeping state consistent? Exceptions do not automatically roll back prior updates.
5. **Cancellation/interrupts:** a worker waiting on `take()` can be interrupted; cleanup and termination state must be handled without swallowing `InterruptedException`.
6. **Resource ownership:** who is responsible for closing resources (`AutoCloseable`) and when? Never let a producer close a resource while the consumer is still using it.
7. **Memory:** a queue can accumulate many messages if producers outpace the consumer. Use bounded queues and monitor queue length, processing time, latency, and rejection/backpressure.

With `ExecutorService`, calling `shutdown()` stops accepting new tasks but does not automatically wait for all tasks to finish. Use `Future.get()` for critical tasks or `awaitTermination()` when a clean shutdown boundary is needed; handle `InterruptedException`/`ExecutionException`/timeouts per contract. Do not use `Thread.sleep()` as a substitute for lifecycle synchronization.

## 13. Designing Explicit Ownership with Multiple Workers

Several organizational patterns are commonly used:

**Local map-reduce:** each worker creates its own accumulator; after `Future.get()`, main merges them. Advantage: low contention. If aggregation requires exact results on numeric types that can overflow or floating-point numbers that are not strictly associative, you must define the order and precision policy.

**Partitioning by key:** `hash(key)` or a routing rule sends all updates for the same key to a single owner. Independent keys can run in parallel. Routing must remain stable during resizing/rebalancing, and partition ownership transfers must be synchronized.

**Event loop / actor-style:** one thread sequentially processes a command queue and owns the state. This fits well when state has many interrelated fields, but long blocking I/O must be avoided so the queue does not stall. If async I/O is needed, you must design callbacks/reentry and result-application order.

**Snapshot publishing:** the owner builds a complete snapshot and safely publishes it to multiple readers. An immutable snapshot lets readers read lock-free for the lifetime of the snapshot; the next generation is built separately and swapped in via an appropriate publication mechanism (e.g., a volatile reference to an immutable snapshot). This is a good strategy for read-heavy/write-light workloads, though it incurs copy overhead and does not form a transaction with external side effects.

### Quick Selection Diagram

```text
Is there mutable state to process?
    |
    +-- No: immutable data / pure function -> safe to share for reading when properly published
    |
    +-- Yes
         |
         +-- Used by only one task, no escape? -> task-local / thread confinement
         |
         +-- Multiple producers, one place updating state?
         |       -> single owner + queue/command + backpressure
         |
         +-- Multiple threads need to update the same invariant?
                 -> synchronized / Lock / atomic / partitioned data
                    at the right granularity and contract
```

This diagram is an initial architectural guide, not an algorithm for every problem. The choice also depends on throughput, latency, consistency requirements, failure recovery, and multi-process needs.

## 14. Thread Confinement and Java 21+ Virtual Threads

Virtual threads use a model with many lightweight Java threads compared to platform threads, but **ownership and data-race rules still apply**:

- A mutable object used by only one virtual thread without escaping can still be confined.
- `ThreadLocal` is bound to each virtual thread, unlike a small pool of reused platform worker threads. Heavy values multiplied by a large number of virtual threads can consume significant memory.
- Do not assume "virtual threads have low overhead" means you can share mutable `ArrayList`/`HashMap` instances across them without locking.
- Bounded queues, backpressure, and state partitioning are still necessary when downstream capacity is finite.

The hands-on example in this lesson **runs on Java 17** with platform threads. Virtual threads were standardized in Java 21; you do not need them to understand thread confinement.

## 15. Testing and Evaluating a Confinement Architecture

### Verifying Correctness

1. Draw an **ownership map**: for each mutable object, who creates it, who can read it, who can write it, where it is handed off, and where its lifecycle ends.
2. Check **escape paths**: returned references, static fields, listeners/callbacks, lambda captures, shared collections, queues, and constructor leaks.
3. For each handoff, identify which **happens-before** edge makes the prepared data visible to the receiver.
4. Check whether the sender **is still allowed to access/mutate** after handoff; use immutable snapshots or drop references if needed.
5. Stress-test multiple producers/consumers, varied completion orders, cancellation, and full queues; assert invariants, processed message counts, and proper errors/timeouts.
6. Test `ThreadLocal.remove()` cleanup with pooled workers running multiple sequential tasks; watch out for cross-task data leaks.
7. Measure throughput, p95/p99 latency, queue depth, CPU, and memory. If a single owner becomes a bottleneck, consider partitioning invariants that can be safely separated.

### Meaningful Assertion Examples

If you send 100 increment-by-`1` commands through a consumer and wait for completion, the total must equal 100. However, if command retries are possible, you must define whether commands are applied once or use an idempotency key; single-owner only serializes updates, **it does not automatically provide exactly-once delivery**.

For task-local + merge models, verify that all elements are present without duplicates or omissions, and that the input was not unintentionally mutated by workers. Avoid using "ran 1,000 times without crashing" as sole proof of thread safety.

## 16. Common Misconceptions

1. **"An object created in a local variable is guaranteed to be used by only one thread."** False if the reference escapes into a shared field, callback, queue, or is passed to another thread while still being mutated.
2. **"Once using BlockingQueue, you can mutate the message after put."** False; the queue guarantees publication for actions before handoff, not protection for out-of-owner writes afterward.
3. **"A single writer means any reader can read lock-free."** False; writer–reader data races still exist if mutable state is shared without synchronization.
4. **"ThreadLocal = task-local = request-local."** False; thread pools reuse threads and tasks can switch workers.
5. **"List.copyOf makes all elements immutable."** False; copying the container can still retain references to mutable elements.
6. **"A final field means the object is immutable."** False; a `final List` can still contain and point to mutable structures.
7. **"Using synchronized around a worker is mandatory for thread safety."** No, if the worker only mutates private state and uses a handoff with clear memory semantics; locks may be unnecessary in local processing.
8. **"A single owner guarantees all tasks complete in submission order."** It still depends on multi-producer enqueue order, async processing, and response contracts.
9. **"Future returning data means the worker guaranteed all side effects outside the JVM succeeded."** No; `Future.get()` provides the task's result or exception, not a database or network transaction.
10. **"Not using locks means there is no synchronization."** Primitives like `BlockingQueue`/`Future` still coordinate threads and carry memory guarantees.
11. **"Fast is all that matters."** You must prioritize invariants, visibility, lifecycle, and correctness first; only then measure contention/throughput/latency.
12. **"Thread confinement automatically prevents deadlocks."** It reduces the need for locks on local state, but an owner can still block waiting for a response from another owner or a blocking queue, creating dependency cycles and halting progress.

## 17. Self-Check Questions and Answers

**Q1.** Thread A creates an `ArrayList` in a method, passes that reference to B, and continues calling `add` while B iterates over the list. Is there thread confinement?  
**Answer:** No. The object has escaped and has two concurrent accessors. You need a strict ownership handoff, an immutable snapshot, or coordination across all reads/writes.

**Q2.** Why is `BlockingQueue.put(message)` helpful yet insufficient if the producer continues mutating `message` afterward?  
**Answer:** The queue establishes HB from actions before `put` to actions in the receiver after `take`, but it does not prevent data races on updates made after `put`. You must stop mutating or use a different protocol.

**Q3.** Two `Callable` tasks each build their own `ArrayList<Integer>` and return `List.copyOf`; main waits on `Future.get()` before merging. Is locking needed around each `local.add()`?  
**Answer:** No, if each list truly belongs only to its worker; `get` establishes a completion and visibility boundary. Main merges into a list owned by main.

**Q4.** A pooled thread uses `ThreadLocal<StringBuilder>` for a previous task, and the next task runs on the same worker. Can unwanted state remain?  
**Answer:** Yes. `ThreadLocal` is bound to the thread and can persist across tasks. Reset state and call `remove()` in `finally` according to the lifecycle.

**Q5.** An object has `private final List<Order> orders`; callers obtain `List.copyOf(orders)`. Is it guaranteed that callers cannot mutate an `Order` inside?  
**Answer:** No. `List.copyOf` only protects the list structure; it does not deep-freeze mutable elements. You need immutable `Order` objects or a defensive deep snapshot.

**Q6.** Why does single-writer often reduce lock contention yet not guarantee it is always faster than locked shared state?  
**Answer:** A single consumer can become a bottleneck, queues have overhead/queuing delays, and producers need backpressure. Results depend on workload and partitionability.

**Q7.** Is a handoff using `Thread.sleep(100)` between producer and consumer enough to safely publish data?  
**Answer:** No. Sleep does not establish a valid HB relationship for sharing state; use a queue, lock, volatile protocol, `Future`, or a primitive with the right contract.

**Q8.** If one thread owns `balance` but multiple threads can read it directly via an unsynchronized getter, is it still considered safe confinement?  
**Answer:** No, because mutable data is shared with readers without a protocol. Return a snapshot through the owner or protect readers with a memory-consistency protocol.

**Q9.** To split one owner into four for better performance, what is the most important condition?  
**Answer:** Partition state along independent invariants and ensure keys/messages always route to the right owner; cross-partition operations require a separate protocol.

**Q10.** `volatile Snapshot current` points to a truly immutable snapshot; the owner builds a new snapshot and assigns `current = snapshot`. Readers only read the current snapshot. Can locks be avoided on readers?  
**Answer:** Yes, if the snapshot is properly constructed/published, the entire read object graph is immutable, and each reader reads the `volatile` reference once per operation. The volatile assignment provides publication/visibility; the owner must never mutate an old snapshot that readers may be using.

## Official References

- [Java SE 17 — java.util.concurrent package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html): concurrency primitives and memory-consistency properties.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): task submission and lifecycle.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): task completion and results.
- [Java SE 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): producer-consumer model, blocking, and memory consistency.
- [Java SE 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): per-thread values, `withInitial`, `get`, and `remove`.
- [Java SE 17 — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): structurally unmodifiable lists, with notes on mutable elements.
- [JLS 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model, data races, happens-before, and monitors.
- [Java SE 17 — Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `start`, `join`, and thread lifecycle.

**Key reminder:** to rely on thread confinement for thread safety, control **every alias to a mutable object**, specify **who may mutate it and when**, and establish **publication/handoff boundaries with happens-before**. When ownership is explicit, many local updates need no locks; coordination between owners still requires reliable mechanisms and invariant verification.