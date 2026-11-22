# Ownership and Avoiding Unnecessary Shared State in Java Concurrency

## 1. The problem: sharing too much data makes programs hard to get right

When multiple threads work together, the initial intuition is often to put variables into a shared object and add `synchronized`, `Lock`, or atomics to protect them. That can be necessary, but good design usually starts with an earlier question: **does this data actually need to be owned and mutated by multiple tasks?**

In concurrency design, **ownership** is the convention defining **who is allowed to read, who is allowed to mutate a state, and when that right is transferred**. This is a design convention at the object/task/API level; Java does not have a linear type system enforcing a single owner like some other languages. Therefore, developers must express this convention through data structures, interfaces, task lifecycles, and exchange mechanisms.

This lesson covers general Java concurrency, using Java 17+ and `java.util.concurrent`. No Spring components are used.

Practical goals:

- Identify **shared mutable state** and the reference paths that accidentally cause it to be shared.
- Design data owned exclusively by a single task, or immutable snapshots read by multiple tasks.
- Transfer information between tasks via messages/queues/Futures instead of mutating the same object together.
- Distinguish between **ownership**, **immutability**, **thread confinement**, **safe publication**, **synchronization**, and **data race**.
- Establish lifecycle boundaries, ensuring data and errors are collected before tasks finish.
- Know when state truly needs to be shared, and minimize the scope of sharing rather than trying to eliminate every synchronization mechanism.

## 2. From shared mutable state to ownership

An object becomes **shared** when at least two threads can access that same object. If the object or the objects it references can be mutated, we have **shared mutable state**. For example:

```java
// Illustrative example of an error-prone design; not a standalone program.
class SharedCart {
    final java.util.List<String> items = new java.util.ArrayList<>();
}
SharedCart cart = new SharedCart();

// If two tasks call cart.items.add(...) concurrently:
// ArrayList does not guarantee safety for concurrent updates.
```

Two distinct problems typically arise:

1. **Atomicity / race condition:** multi-step operations interleave, causing lost updates, invalid intermediate states, or data structure corruption.
2. **Visibility and ordering:** other threads do not necessarily observe writes at the right time/order without an appropriate *happens-before* relationship under the Java Memory Model.

Adding `volatile` to the `cart` reference does not make the `ArrayList` inside thread-safe. Adding `AtomicInteger` for one field does not automatically protect invariants involving multiple fields. And placing `synchronized` on a method does not help if callers still access the data through unprotected reference paths.

### What does ownership describe?

Consider a program that receives a list of requests and computes results:

- **Input:** who creates it? Who is allowed to mutate it before and after task submission?
- **Inside the task:** is temporary state kept in local variables and not exposed to other threads?
- **Result:** does the task return a new object, or mutate the caller's result table directly?
- **Handoff:** after submitting a message, does the producer continue mutating the same object?
- **Lifecycle:** does the caller wait for results or shut down the executor before finishing?

A good contract makes the answers clear. For example: "The caller creates an immutable `Task`; each worker uses only local variables; the worker returns a `Result`; a single caller aggregates `Result`s after `Future.get()`." Then there is little shared state needing synchronization.

**The owner is not necessarily a fixed thread.** A task may run on any thread chosen by the executor, yet still have exclusive ownership over the task's data. Conversely, an immutable object can be read by multiple threads without designating an exclusive owning thread when reading.

## 3. Three commonly used design strategies

| Strategy | Access rights | When appropriate | Limitations to remember |
| --- | --- | --- | --- |
| **Task-local / thread-confined state** | One task holds and mutates its own data | Intermediate computations, parsers, temporary buffers, independent accumulators | Do not publish mutable references to other tasks |
| **Immutable shared data** | Multiple tasks read; no one mutates the object after creation | Configuration, request snapshots, lookup data | Immutability must cover mutable components inside |
| **Message passing / ownership transfer** | Producer hands information to consumer; consumer is the one updating its state | Worker queues, actor-like components, pipelines | Need shutdown rules, queue bounds, error handling, and no mutation after transfer |

The three approaches can be combined: a producer sends an **immutable message** into a queue, each consumer uses its own **local state**; results are returned via a `Future` or a response queue. This is how to reduce the number of objects mutated by multiple threads at once.

Do not interpret "ownership" to mean only a single thread may reference an object. For immutable objects, sharing references can be safe; for mutable objects, you must clarify **mutation rights** and **publication mechanisms**.

## 4. Before-and-after example: removing a shared total counter

A common approach is having workers write to a shared total variable:

```java
// Illustration of a pattern prone to data races, not a standalone program.
int[] total = {0};
Runnable work = () -> {
    // Suppose multiple threads run work concurrently.
    total[0]++; // read -> add -> write; not atomic
};
```

`total[0]++` consists of read, compute, and write steps; with multiple workers, updates can be lost. In addition, this code has no mechanism to wait for completion or publish the full result. You can replace it with `AtomicInteger` when it truly is a shared counter, but sometimes the data does not need to be summed across multiple threads.

**Ownership-based design:** partition the data, let each task process its own piece, and return a `Result`; only the caller aggregates after tasks complete.

Save the following code to **`OwnedTasksDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class OwnedTasksDemo {
    record Task(String id, int units) {}
    record Result(String id, int cents) {}

    static Result calculate(Task task) {
        // subtotal belongs only to a single task execution.
        int subtotal = task.units() * 100;
        return new Result(task.id(), subtotal);
    }

    public static void main(String[] args) throws Exception {
        List<Task> tasks = List.of(
                new Task("A", 2),
                new Task("B", 3)
        );

        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            List<Future<Result>> pending = new ArrayList<>();
            for (Task task : tasks) {
                pending.add(executor.submit(() -> calculate(task)));
            }

            // Single caller reads and presents the results.
            for (Future<Result> future : pending) {
                Result result = future.get();
                System.out.println(result.id() + "=" + result.cents());
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

Run with JDK 17+:

```bash
javac OwnedTasksDemo.java
java OwnedTasksDemo
```

Stdout:

```text
A=200
B=300
```

**Why does this program need no locks for the total amount?**

1. `Task` contains only `String` and `int`, components that are not mutated in the program; `List.of(...)` creates a list whose structure cannot be modified.
2. Each call to `calculate` creates its own local `subtotal` variable. No two workers write to the same `subtotal`.
3. `Result` is a new record per task; workers do not write to a shared result list but return via `Future`.
4. Only the caller creates/adds to `pending`; at that point workers only hold `Task` and return `Result`, without mutating `pending`.
5. `Future.get()` waits for the task to complete and provides a *happens-before* relationship per the executor contract. All writes by the task before completion are properly observed by the caller when retrieving the result.
6. Even though the two tasks may finish in different orders, the print order is **A then B** because `pending` preserves submission order and the caller reads each `Future` in that order.

If the program needs to sum all results, the caller can do so after the `get()` calls using a local variable, without workers adding to a shared sum. In real-world tasks, `finally` should also manage shutdown deadlines and failed/incomplete tasks according to application requirements; `shutdown()` here only signals not to accept new tasks, while `get()` in the loop already waits for the two tasks in the example.

### When should you still use atomics or locks?

If multiple threads genuinely need to update the same system-wide counter, `AtomicLong` may be appropriate. If you need to maintain an invariant such as "deducting inventory and recording history must be consistent", you may need to use locks or synchronization at the data/resource level. Ownership helps **reduce the amount of shared state**; it does not claim that synchronization mechanisms are useless.

## 5. Immutability: many readers, no writers

### Shallow immutability vs. deep immutability

`final` only prevents reassigning **the field's reference**; it does not lock the object that the reference points to.

```java
// Unsafe illustration if the object is shared and mutated concurrently.
final java.util.List<String> names = new java.util.ArrayList<>();
names.add("one"); // still allowed: final does not freeze ArrayList
```

A record also **does not automatically have deep immutability**:

```java
record Job(String id, java.util.List<String> tags) {}
```

A record has final fields, but if the caller passes in an `ArrayList` and then continues calling `add`, the data inside `Job` changes along with it; and `job.tags()` can expose the mutable list for consumers to modify.

Fix this with a **defensive copy at the object creation boundary**:

```java
import java.util.List;

// Illustrative snippet: place in Job.java or an appropriate program.
record Job(String id, List<String> tags) {
    Job {
        tags = List.copyOf(tags);
    }
}
```

In the compact constructor, the `tags` parameter value is replaced with a copied list before being assigned to the record field. `List.copyOf` creates a list that cannot be modified via its API. Similarly, `Map.copyOf` and `Set.copyOf` can create corresponding unmodifiable snapshots. These copy methods reject `null` elements or keys/values according to API rules.

However, **`List.copyOf` is only a shallow copy**: if the elements are `MutableAddress`, each of those elements can still be mutated through another reference. Deep immutability requires using immutable elements or copying the internal mutable objects according to a dedicated contract.

### `Collections.unmodifiableList` vs. a snapshot

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> source = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(source);
List<String> snapshot = List.copyOf(source);

source.add("B");

System.out.println(view);      // [A, B]
System.out.println(snapshot);  // [A]
```

This is an illustrative snippet inside a method, **not a standalone program**. The `unmodifiableList` view disallows modification through `view` but still reflects changes from `source`. `List.copyOf` provides a structural snapshot of the list at the time of copying, provided the elements are safe to share. Do not publish a "read-only view" over a collection still being mutated by another thread and assume it is immutable or thread-safe.

### Immutables must be safely published

A properly designed immutable object still needs to be delivered to other threads through an appropriate publication channel, for example:

- Passing arguments when submitting a task to an executor.
- Placing a message into a `BlockingQueue`.
- Exchanging through a `Future`, concurrent collection, or synchronization mechanism with a clear contract.
- Fully constructing the object before storing it in a `final` field published according to Java Memory Model rules, avoiding leaking `this` while the constructor is still running.

For properly constructed immutable objects, `final` rules provide additional guarantees; however, you should not rely on that in place of clear data transfer paths and lifecycles. Do not prematurely publish an object under construction or let another method read a mutable structure without a memory barrier.

## 6. Transferring ownership via messages and BlockingQueue

Suppose a producer receives requests and a single consumer updates a local total. A good design is for the producer to only create **messages** and deliver them to a mailbox. The consumer reads each message and updates a **total variable that only it holds**.

Save in **`MailboxDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class MailboxDemo {
    record Message(int amount, boolean stop) {}

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Message> mailbox = new ArrayBlockingQueue<>(2);

        Thread consumer = new Thread(() -> {
            int total = 0; // Only the consumer thread mutates this.
            try {
                while (true) {
                    Message message = mailbox.take();
                    if (message.stop()) {
                        break;
                    }
                    total += message.amount();
                }
                System.out.println("total=" + total);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();
        mailbox.put(new Message(4, false));
        mailbox.put(new Message(5, false));
        mailbox.put(new Message(0, true)); // Termination signal after data
        consumer.join();
        System.out.println("finished");
    }
}
```

Run with JDK 17+:

```bash
javac MailboxDemo.java
java MailboxDemo
```

Stdout:

```text
total=9
finished
```

**Path of ownership:**

1. The producer creates a `Message` containing immutable data and sends it via `mailbox.put`.
2. The consumer receives it via `mailbox.take`. The queue guarantees thread-safe exchange and has memory consistency effects per the `java.util.concurrent` contract: actions prior to placing an object into the queue *happen-before* actions subsequent to another thread taking that object out.
3. Only the consumer mutates the `total` variable. The producer has no reference to this local variable, so it cannot accidentally create a data race on `total`.
4. Capacity `2` indicates a **bounded** mailbox; if full, `put` waits until space is available. This is a form of backpressure that needs to be managed in real applications.
5. The `stop` message is sent last; in this example with one producer, a FIFO queue, and one consumer, all preceding messages are processed before the consumer exits.
6. `join()` makes main wait for the consumer before printing `finished`; the two stdout lines have a deterministic order.

`BlockingQueue` makes **passing the reference** safe, but **does not automatically turn a mutable object into an immutable one**. If you send an `ArrayList` into the queue and the producer continues adding/removing elements while the consumer reads it, a data race can still occur. Therefore, choose immutable messages, defensive copies, or a transfer-of-ownership convention where **the producer is no longer allowed to access it for mutation after sending**.

With multiple producers, multiple consumers, or long-running systems, a shutdown protocol using a "poison message" needs dedicated design: a single stop message may only stop one consumer; producers might still send after stop; shutting down in the wrong order causes data loss or infinite waiting. You need ownership for the **mailbox lifecycle**: who closes, who waits, and who is responsible for handling and reporting errors.

## 7. Ownership transfer is not the same as just passing a reference

Consider the following example:

```java
// Code snippet illustrating a design flaw.
List<String> payload = new ArrayList<>();
payload.add("first");
queue.put(payload);       // Consumer can take it immediately.
payload.add("second");    // Producer continues mutating the same ArrayList.
```

If `queue` is a `BlockingQueue<List<String>>`, `put`/`take` only coordinates handing off/receiving the element and visibility for actions prior to insertion. It does not forbid mutation after delivery. Calling `payload.add("second")` concurrently while the consumer reads is sharing mutable state.

Three valid options depending on requirements:

1. **Copy-and-share:** the producer calls `queue.put(List.copyOf(payload))`, and the consumer receives a structurally immutable snapshot; safe when elements are immutable.
2. **Exclusive handoff:** the producer hands over a mutable object and commits to no longer mutating or reading it in a racy way; the consumer is transferred mutation rights. The contract must be upheld by every caller.
3. **Synchronized shared mutable state:** when both genuinely need to mutate the same object, use a thread-safe structure or appropriate lock protecting the entire invariant.

In Java, exclusivity is a **convention**, not compiler-verified. You need to review alias paths: other variables, other collections, callbacks, closures, or static fields may still hold the same reference. If you cannot control all aliases, an immutable snapshot is usually easier to verify.

## 8. Thread confinement and task confinement

**Thread confinement**: state is accessed by only one thread. You can use local variables in `Runnable.run()`, or a worker instance that owns a data structure and processes messages sequentially.

**Task confinement**: state is tied to a logical computation, even though an executor may pick different threads for different tasks. This is often a more useful way to describe many modern Java programs.

```java
// Illustrative snippet.
Callable<Integer> task = () -> {
    int localSum = 0;
    for (int value : inputSnapshot) {
        localSum += value;
    }
    return localSum;
};
```

When `inputSnapshot` does not change and `localSum` does not escape the task, multiple invocations can run concurrently without sharing `localSum`. Only task submission and result collection need to be managed.

Note that a local variable **holding a reference** does not mean the pointed-to object is private. For example, `List<String> local = sharedList;` still points to the shared list. A lambda can capture a mutable reference from the enclosing scope; `effectively final` only prevents the variable from being reassigned, not mutating the object.

`ThreadLocal<T>` is a tool for storing values private to **each thread**, but it does not replace task-level ownership:

- In a reused thread pool, if you forget `remove()`, the value from an old task can still affect a subsequent task, while also retaining resources longer than necessary.
- With virtual threads created per task, using many `ThreadLocal`s or large values also consumes memory; do not turn every parameter into an implicit context.
- A task may switch threads across different async stages; do not assume a `ThreadLocal` will follow every call after leaving the initial thread.
- Passing explicit parameters, immutable request contexts, or messages usually makes ownership clearer; `ThreadLocal` has its place when required by a library's contract.

## 9. Ownership and the Java Memory Model: do not ignore happens-before

Separating state helps reduce races, but exchanges between threads still need proper mechanisms.

| Event | Useful guarantee |
| --- | --- |
| Create data then call `thread.start()` | Actions before `start` *happen-before* actions in the new thread |
| A thread finishes, another thread successfully calls `join()` | Actions of the finished thread *happen-before* the waiting thread proceeds after `join` |
| Submit a `Runnable` or `Callable` to `ExecutorService` | Actions before submit *happen-before* task execution |
| Task completes and caller retrieves result via `Future.get()` | Actions inside the task *happen-before* actions after retrieving the result |
| `BlockingQueue.put` then consumer `take`s the exact element | Actions before putting the element *happen-before* actions after taking it |
| Write and read the same `volatile` variable, or matching lock/unlock | Provides ordering/visibility per corresponding JMM rules; does not automatically make compound operations atomic |

`happens-before` speaks to ordering and visibility, **not proving that an object is no longer being mutated**. If you put a mutable object into a queue and the producer subsequently continues mutating it, the put/take guarantee does not eliminate invalid interactions after the handoff point.

Every shared state must have a clear answer: read-only immutable? Single write owner? Handoff protocol? Or a synchronization mechanism protecting access? You cannot substitute the answer with `Thread.sleep(100)`, `yield()`, or guessing that one thread will run before another.

## 10. Business invariants and drawing boundaries

Many races do not lie in a single `++` statement, but in **multi-field invariants**.

For example, a warehouse has `available` and `reserved`, requiring that their sum does not exceed `capacity`. Two threads both reading "space available" and both reserving can break the invariant even if each field is a separate atomic. If there truly is a shared warehouse that must be updated immediately, you need a synchronization mechanism **at the level of the entire check-and-update operation**, or funnel all reservation commands to a single owner.

The **single writer** model:

```text
Multiple producers
   |     |
   v     v
  immutable commands
         |
         v
  bounded mailbox
         |
         v
  single owner processes sequentially
         |
         +--> mutable state mutated only by owner
         |
         +--> immutable result / Future / response queue
```

Advantage: invariants are checked in one single place, reducing locks across multiple callers. In return, the owner can become a bottleneck; you need to manage capacity, fairness, timeouts, errors, and shutdown. If throughput needs to increase, consider splitting state into **independent partitions** (e.g., each key belongs to one owner) with clear boundaries. Poor partitioning or multi-key tasks may again require coordination/transactions across owners.

Do not call every "single-thread processing" setup non-concurrent: multiple producers can still run in parallel and the mailbox requires synchronization. The benefit lies in having **a single write owner for the core mutable state**, making invariants easier to reason about.

## 11. Managing errors, timeouts, and lifecycle with ownership

Designing the data alone is not enough; a task can fail, be cancelled, or run past its deadline.

- **Who owns the Future?** The caller submitting the task should hold the `Future` or transfer management responsibility to another component responsible for waiting, cancelling, and reporting errors.
- **Who stops the executor?** The component that creates the executor should have a clear shutdown/close contract; do not let individual tasks arbitrarily call shutdown on a shared executor.
- **Who closes the queue?** Choose a coordinator or protocol that tracks the number of producers, ensuring all valid messages are processed or reported as failed.
- **Who closes resources?** Sockets/streams/DB connections cannot be handed off with just a verbal convention. You must describe who closes them, the closing order, exception handling, and cancellation paths.
- **What if it times out?** `Future.get(timeout, unit)` reports a wait timeout; it does not automatically ensure the task has stopped. The managing owner may call `cancel(true)`, and the task needs to cooperate in handling interrupts.
- **What if the task throws an exception?** `Future.get()` may throw `ExecutionException`. Do not mark work as successful just because the producer enqueued it or `submit()` returned.
- **What if the queue is full?** `put()` blocks until space is available; `offer(timeout)` allows a rejection/bounding policy instead of blocking indefinitely.

In Java 17, `ExecutorService` is managed via `shutdown()` and `awaitTermination(...)` when full waiting is needed, along with a cancel/`shutdownNow()` policy depending on errors. Do not design a shutdown mechanism where all workers wait on each other, which easily causes deadlocks. Newer JDKs add lifecycle management utilities, but the ownership principle remains clearly identifying which **scope** creates tasks and which scope collects results.

**Object ownership does not equal result ownership.** A task may have finished and no longer be mutating an object, yet the caller has still not called `Future.get()` to receive an exception. Conversely, a caller may no longer have the right to mutate the input, yet still have the obligation to receive the result.

## 12. Design checklist before adding locks

Answer these questions in order:

1. **List the state:** which objects can change? Which fields point to collections, arrays, buffers, or internal mutable objects?
2. **Identify the owner of each part:** caller, a task, a worker/partition, or a component holding shared state?
3. **Find aliases:** is any other place holding a reference to the same object for mutation? Do lambda captures, static fields, caches, listeners, callbacks, and getters leak data?
4. **Separate input and output:** can you pass an immutable snapshot to the task and return an immutable result? Can you aggregate in the caller instead of summing into a shared variable?
5. **Identify the handoff point:** via queue/Future/start/join or another publication mechanism? Does the producer stop mutating after that point?
6. **Preserve invariants:** if multiple fields must be consistent, is there a single write owner or a critical section covering the whole operation?
7. **Bound resources:** is the queue bounded? Are there too many concurrent tasks? Who is responsible for timeouts, backpressure, cancellation, and shutdown?
8. **Verify:** you can run tests many times to detect races, but passing tests do not prove there are no races remaining. Reason based on ownership, API contracts, and the Java Memory Model.

### Common anti-patterns

| Anti-pattern | Consequence | Adjustment |
| --- | --- | --- |
| Passing a shared `ArrayList` to all tasks and letting each call `add` | Races, lost updates, or corrupted structure | Each task returns a result; a single owner combines the list after `get` |
| Marking a `Map` field `final` and treating the Map as immutable | Elements/entries can still be modified | Defensive copy and immutable elements; clear contract |
| Using `Collections.unmodifiableList` on a list still being mutated | View still reflects external changes | Use a `List.copyOf` snapshot if elements are safe |
| Passing a mutable object through a queue and continuing to mutate it | Race after the handoff point | Copy before sending or exclusive handoff |
| Each worker updates multiple atomics to maintain a shared invariant | Invariant can be broken between steps | Single writer or synchronization covering the full operation |
| Using `ThreadLocal` for all task data | Hidden context, retained resources, hard to transfer across async stages | Explicit parameters and task-local state |
| Putting `volatile` on a reference and freely reading/mutating internal fields | Does not make the object graph thread-safe | Split ownership or synchronize the state properly |
| Submitting a task and discarding the `Future`, never checking the result | Errors are ignored, lifecycle is ambiguous | Caller/scope owns the Future and collects errors |
| Trying to limit task count by creating a tiny thread pool for all I/O waiting | Throughput bottleneck, high latency | Bound the target resource and use an executor suited to the workload |
| Moving state into a singleton/static just for convenient access by many tasks | Increases shared surface area and synchronization burden | Pass data as parameters and return results |
| Adding local locks inside a class while exposing a mutable list via a getter | Callers still mutate outside the lock | Provide operation APIs, snapshots, or encapsulation |

## 13. Practice exercises and self-check questions

**Exercise 1 – Aggregating results:** There are 100 tasks reading 100 files and counting lines. Which design has less shared mutable state: (A) tasks increment a shared `int`, (B) each task returns a `long` via `Future` and the caller sums them? **B** is the easier choice to verify. Tasks can still read shared immutable input data, but the accumulator is not mutated by multiple workers.

**Exercise 2 – Aliasing via record:** Does `record Request(List<String> names) {}` automatically protect the list from being modified? **No.** The field is final, but the list itself may be mutable. Use a defensive copy in the constructor; if elements are also mutable, deep copying or immutable elements are needed.

**Exercise 3 – After queue.put:** A producer puts an `ArrayList` into a `BlockingQueue` and then mutates the list; a consumer concurrently iterates over it. Is it guaranteed to be race-free because the queue is thread-safe? **No.** The queue protects the delivery of the element and visibility at the handoff point, not subsequent modifications.

**Exercise 4 – Multi-field invariant:** Are two `AtomicInteger`s for `available` and `reserved` sufficient to maintain an invariant involving both? **Not necessarily**; individual updates can still interleave. You need single-writer ownership, an appropriate transaction/lock, or a different invariant design.

**Exercise 5 – ThreadLocal:** Tasks A and B run sequentially on the same platform thread from a pool. If A puts a context into `ThreadLocal` and does not call `remove()`, can B read the old context? **Yes**, depending on the code path. Therefore, clean up in `finally` or avoid hidden context.

**Exercise 6 – Future:** Does `submit` returning a `Future` mean the task has succeeded? **No.** The task may not have run yet, may be running, or may have completed with an error. The caller must manage and retrieve the result/exception per the contract.

**Exercise 7 – Single writer:** If a single consumer updates `total` as a local variable, does that variable need an `AtomicInteger`? **No** in the example's model. The queue and `join` guarantee exchange and the completion point; no other thread mutates `total`.

## 14. Practical principles to remember

Design concurrency by **defining ownership before adding synchronization**:

- Data serving only a single computation should be kept **task-local**; results are returned when the task finishes.
- Data that needs to be shared for reading should use **immutable snapshots** with control over the entire object graph.
- Data that must be mutated over time should ideally have a **single write owner**; other callers send commands or messages through a thread-safe channel.
- Unavoidable shared mutable state needs **synchronization at the level of the invariant**, not just protecting a few scattered lines.
- Every handoff must have a clear contract regarding **when mutation rights are lost**, visibility, capacity bounds, error handling, and lifecycle.

This way of thinking makes code easier to test and maintain: instead of having to prove every read/write across a multitude of shared objects is correct, we reduce the number of places with write access, reduce aliasing, and only need to prove that the **communication boundaries** are safe.
