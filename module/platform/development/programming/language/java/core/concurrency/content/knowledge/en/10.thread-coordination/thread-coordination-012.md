# Comparing Coordination via Shared State and Message Passing in Java

## 1. Two fundamental ways for threads to collaborate

A concurrent program typically divides work into multiple tasks running concurrently. Those tasks need to **exchange data**, **report progress**, or **produce a shared result**. In Java, the two foundational ways to organize this are:

1. **Shared state:** threads access the same region of data together. They coordinate using `synchronized` monitors, `Lock`, `volatile`, atomic variables, wait conditions, or concurrent data structures.
2. **Message passing:** tasks exchange messages through a channel, such as a `BlockingQueue`. One task can **exclusively own** its state, while other tasks ask it to perform work by sending messages instead of modifying that state directly.

Both exist in standard Java concurrency. Neither choice is always faster or always simpler. The key difference is **where the data lives, who has permission to modify it, who waits on whom, and how consistency is guaranteed**.

For example, consider a counter receiving increment requests from two workers:

```text
SHARED STATE

Producer A ────┐
                ├──> shared Counter <── synchronized / AtomicInteger
Producer B ────┘
        Threads perform direct updates.


MESSAGE PASSING

Producer A ────┐
                ├──> BlockingQueue<Increment> ──> Counter owner
Producer B ────┘                             (only owner modifies count)
        Threads send requests; owner performs updates.
```

Both designs can produce the same correct result, but the ownership transfer path and coordination overhead differ. This lesson belongs to the **Thread Coordination** topic of **general Java concurrency**, independent of any framework.

## 2. Distinguishing shared data from message passing

### Shared state

In the shared state model, multiple threads can hold references to the same mutable object:

```java
final class Counter {
    private int count;

    synchronized void increment() {
        count++;
    }

    synchronized int get() {
        return count;
    }
}
```

This is an **illustrative class definition**, not a program with `main`. Every thread calling `increment()` on the **same instance** must acquire that instance's monitor. If readers also call `get()`, the operations are consistently protected by the same monitor.

**Core idea:** shared data still exists; threads are allowed to access it, but they must obey its synchronization protocol.

### Message passing

In the message passing model, another worker can send an increment request through a queue:

```java
record Increment(int amount) {}

BlockingQueue<Increment> mailbox = new ArrayBlockingQueue<>(32);
mailbox.put(new Increment(1));
```

This is an **illustrative snippet** that requires importing `java.util.concurrent.BlockingQueue` and `ArrayBlockingQueue`. A thread consuming `mailbox.take()` will receive the message. If only that consumer thread owns and updates `count`, producers do not need to lock the `count` variable — because they are **not allowed to modify it**.

**Core idea:** instead of sharing write access to state, threads share a channel for transferring requests/data. You need to ensure channel safety, handle full/empty conditions, manage the consumer lifecycle, and define message semantics.

**Subtle point:** message passing within the same JVM can still pass **references to objects on the shared heap**. Calling `queue.put(message)` does not automatically deep-copy `message` and does not automatically turn a mutable payload into an immutable one. To avoid data races, it is common to use **immutable messages** or an explicit ownership-transfer protocol: the producer no longer modifies the payload after sending it.

## 3. Quick comparison table

| Criterion | Shared state | Message passing |
| --- | --- | --- |
| Interface between tasks | Call methods / read-write shared objects | Send/receive messages via a queue or channel |
| Owner of mutable state | Potentially multiple threads; requires a synchronization protocol | Usually a single owner handles state; producers only send requests |
| Common Java primitives | `synchronized`, `ReentrantLock`, `AtomicInteger`, `volatile`, `Condition` | `BlockingQueue`, `ArrayBlockingQueue`, `LinkedBlockingQueue`, `TransferQueue` |
| Common risks | Data race, stale read, lost update, deadlock, broken invariant | Full queue, blocked producers, backlog, difficult shutdown, payload mutated after sending |
| How consistency is maintained | Common lock, atomic operations, immutable snapshot | Single consumer serializes updates, or a coordination protocol across owners |
| Load control | Usually requires adding a separate throttling/bounding mechanism | Bounded queues naturally support backpressure |
| Returning results | Method calls can usually return results immediately | May require a response message or `CompletableFuture` |
| Latency | Can be short when it is just a single atomic update | Adds enqueue, dequeue, and context/task switching |
| Isolation level | Callers may know deep details of state structure | Owner can hide state details behind a set of messages |
| Best suited for | A small number of simply updated fields, synchronized snapshots | Pipelines, producer–consumer, actor-like owners, task handoff |

**Do not equate “message passing = lock-free”:** a thread-safe queue may use locks, CAS, conditions, or other techniques inside its implementation. What you gain is **not having to share write access to business state yourself** if the owner model is designed properly.

**Do not equate “shared state = definitely wrong”:** an `AtomicInteger.incrementAndGet()` or a properly lock-protected object can be completely thread-safe and clearer than creating an entire worker with a queue for a simple increment.

## 4. Runnable example: shared state with a synchronized counter

Create the file `SharedCounterDemo.java` (Java 17+):

```java
import java.util.concurrent.CountDownLatch;

public class SharedCounterDemo {
    private static final class Counter {
        private int value;

        synchronized void increment() {
            value++;
        }

        synchronized int value() {
            return value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        CountDownLatch start = new CountDownLatch(1);

        Runnable worker = () -> {
            try {
                start.await();
                for (int i = 0; i < 1_000; i++) {
                    counter.increment();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(worker, "a");
        Thread b = new Thread(worker, "b");
        a.start();
        b.start();
        start.countDown();

        a.join();
        b.join();
        System.out.println("shared total=" + counter.value());
    }
}
```

```bash
javac SharedCounterDemo.java
java SharedCounterDemo
```

Output when there is no unexpected interrupt:

```text
shared total=2000
```

**Why the mechanism works:**

1. `Counter` keeps `value` as a private field.
2. Both threads call `increment()` on the **same `counter` instance**.
3. The synchronized methods use `counter`'s monitor, so two read–modify–write operations cannot interleave.
4. `value()` reads under that exact same monitor.
5. Main waits for both `join()` calls, so it only prints after all increments have completed.

If you remove `synchronized` from `increment()`, `value++` can suffer lost updates. If you only put `synchronized` on the getter while writers do not lock, the protocol is no longer correct. If each thread creates its own `Counter`, the result will be two independent counters — not a shared counter.

### When to use AtomicInteger instead of synchronized

For strictly a single simple increment, you can use `AtomicInteger`:

```java
AtomicInteger counter = new AtomicInteger();
counter.incrementAndGet();
int total = counter.get();
```

This snippet is illustrative (requires importing `java.util.concurrent.atomic.AtomicInteger`). An atomic counter eliminates the need to write a critical section to protect **that single counter alone**. However, if an operation needs to change three fields simultaneously and maintain an invariant, three separate `AtomicInteger` instances are not necessarily enough; you need a lock covering the operation or an immutable snapshot published atomically.

## 5. Equivalent example: message passing with a single owner

In the next design, **producers hold no reference to the `count` variable**. Each producer sends 1,000 messages with value `1` into the queue. A single consumer receives each message and updates its local `count`.

Create the file `MessageCounterDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;

public class MessageCounterDemo {
    private static final int STOP = -1;

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Integer> inbox = new ArrayBlockingQueue<>(16);
        CountDownLatch start = new CountDownLatch(1);
        int[] result = new int[1];

        Thread owner = new Thread(() -> {
            int count = 0;
            try {
                while (true) {
                    int amount = inbox.take();
                    if (amount == STOP) {
                        break;
                    }
                    count += amount;
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            result[0] = count;
        }, "owner");

        Runnable producerTask = () -> {
            try {
                start.await();
                for (int i = 0; i < 1_000; i++) {
                    inbox.put(1);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(producerTask, "producer-a");
        Thread b = new Thread(producerTask, "producer-b");
        owner.start();
        a.start();
        b.start();
        start.countDown();

        a.join();
        b.join();
        inbox.put(STOP);
        owner.join();

        System.out.println("message total=" + result[0]);
    }
}
```

```bash
javac MessageCounterDemo.java
java MessageCounterDemo
```

Output when there is no unexpected interrupt:

```text
message total=2000
```

**Why it is correct:**

- Producers only send positive numbers `1` and do not hold the owner's `count` variable.
- `BlockingQueue.put()` and `take()` protect the handoff between multiple producers and the consumer.
- Only the owner modifies the local `count` variable, so there are no two threads racing to update the count.
- Main waits for **both producers to finish** before sending `STOP`. All `1` messages have already entered the FIFO queue before STOP, so the owner receives all messages before stopping.
- Main waits for `owner.join()` before reading `result[0]`; thread termination via `join` provides a happens-before relationship for the owner's write of the result. The single-element array here is just a place to store the result for a simple example, not a queue or synchronization mechanism.

**Note:** if main sends `STOP` before the producers finish, the owner may stop too early and leave unprocessed work behind; producers may continue calling `put()` until the queue is full and wait indefinitely. The key lesson is that **shutdown is also part of the message passing protocol**.

You can use a record `Increment(int amount)` instead of `Integer` to distinguish business messages from control signals; in this demo, `STOP = -1` is used because all valid data values are positive. Real applications should avoid letting a sentinel marker collide with valid data.

## 6. Why do both programs produce 2000 yet mean different things?

In `SharedCounterDemo`, the two workers perform the work directly:

```text
A --increment()--> Counter
B --increment()--> Counter
         monitor serialize critical sections
```

In `MessageCounterDemo`, each worker expresses a request:

```text
A --put(1)--> Queue --take()--> Owner --count += 1
B --put(1)--> Queue --take()--> Owner --count += 1
```

In terms of correctness of the final sum, both approaches are correct when the protocol is followed. However, the responsibilities differ:

- Shared state: every path that reads or writes state must be synchronized; if one code path forgets to lock, a bug can appear.
- Message passing: the owner is responsible for serializing state; producers must send valid messages and manage the lifecycle. If a mutable payload is shared or multiple owners modify state outside the protocol, the ownership benefit disappears.

The cost also differs: a shared counter may only require lock/unlock or an atomic instruction, whereas message passing typically adds enqueuing, dequeuing, buffering, and context switches. With many producers, a queue also provides a load-aggregation point and decouples production and consumption rates.

## 7. Data ownership: an actor-like model within the same JVM

An easy-to-reason-about message passing design is **single writer**:

1. One component owns the mutable state.
2. Other components **do not receive mutable references** to that state.
3. They send a **command**, **event**, or **request** over a thread-safe channel.
4. The owner receives each message and updates the state.
5. If a reply is needed, the owner sends a response or completes a `CompletableFuture`.

This model is close to actor principles, but using `Thread` and `BlockingQueue` **does not automatically create a full actor runtime**. You still have to handle mailboxes, scheduling, failure recovery, ordering, load limits, and shutdown yourself.

### How do command, event, and request differ?

- **Command:** “please perform change X”. Can be accepted or rejected.
- **Event:** “X has happened”. Usually describes a committed fact; consumers may update a view.
- **Request–response:** “please compute or change X and send me the result”. Requires correlation between request and response.

You can use Java records to define immutable messages:

```java
record Add(int amount) {}
record TotalRequest(long requestId) {}
record TotalReply(long requestId, int total) {}
```

These are illustrative record definitions. Records have final component fields, but **are not automatically deeply immutable** if they contain mutable arrays or lists. With primitives and `String`, building immutable messages is simpler.

## 8. Request–response example using CompletableFuture

Not every caller wants “fire and forget”. Sometimes they need to know that the owner has processed the request and what the result is. One way inside a JVM is to place a `CompletableFuture` inside the message; the owner completes the future when processing finishes.

Create the file `QueueRequestReplyDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CompletableFuture;

public class QueueRequestReplyDemo {
    record Add(int amount, CompletableFuture<Integer> reply) {}

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Add> inbox = new ArrayBlockingQueue<>(8);
        CompletableFuture<Integer> first = new CompletableFuture<>();
        CompletableFuture<Integer> second = new CompletableFuture<>();

        Thread owner = new Thread(() -> {
            int total = 0;
            try {
                for (int i = 0; i < 2; i++) {
                    Add message = inbox.take();
                    total += message.amount();
                    message.reply().complete(total);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "owner");

        owner.start();
        inbox.put(new Add(5, first));
        inbox.put(new Add(7, second));

        System.out.println("first=" + first.join());
        System.out.println("second=" + second.join());
        owner.join();
    }
}
```

```bash
javac QueueRequestReplyDemo.java
java QueueRequestReplyDemo
```

Output:

```text
first=5
second=12
```

Main sends two messages sequentially into the FIFO queue. The owner is the sole consumer, so it processes `Add(5)` before `Add(7)`. Each message carries its own future, avoiding response mix-ups. `CompletableFuture.join()` on main waits for the result of each request; this is **a way of synchronizing between caller and owner**, not `Thread.join()`. If the future completes exceptionally, `join()` can throw `CompletionException`.

**Important:** the `CompletableFuture` object is mutable so the owner can complete the response. The message record here only fixes the reference to the future; it is not a completely deeply immutable object graph. This is acceptable because the protocol grants completion rights to the owner and waiting rights to the caller, but all components must adhere to the contract.

A production implementation must define how failures are reported if the owner crashes, is interrupted, or encounters an exception before completing the future; if the future is left uncompleted, a caller calling `join()` may wait forever. You should complete exceptionally, set timeouts on the caller side, and design a clear lifecycle. `CompletableFuture.cancel()` also **does not automatically interrupt the owner thread** or remove a message sitting in the queue.

## 9. Shared state is still useful when there are many readers

Having multiple reader threads does not mean you must send a “ReadRequest” to an owner. For example, configuration data can be built into an **immutable snapshot** and published via `AtomicReference<Config>`:

```java
record Config(String host, int port) {}

AtomicReference<Config> active =
        new AtomicReference<>(new Config("localhost", 8080));

Config snapshot = active.get();
System.out.println(snapshot.host() + ":" + snapshot.port());
```

This is an illustrative snippet; it requires importing `java.util.concurrent.atomic.AtomicReference` and placing it inside a valid class/method. Readers simply fetch a snapshot reference and read immutable fields without needing an owner to receive a message to return host/port. When config changes, the writer creates a complete new `Config` and publishes **a single consistent reference**.

This is a **hybrid** model: read data is shared, but immutable and safely published; updates can arrive via message passing to an owner, and then the owner swaps the root reference. The two approaches are not mutually exclusive.

**Caution:** two separate reads `active.get().host()` and `active.get().port()` can come from two different versions if a writer swaps the snapshot between them. When consistency is required, read `Config snapshot = active.get()` **once** and then read all components from that snapshot.

## 10. What does a shared mutable object require?

When choosing shared state, you must define:

- **Invariant:** a condition that must always hold, e.g., `balance >= 0` or `left + right == 100`.
- **Reader/writer:** who has permission to read and write, and do all of them follow the same mechanism?
- **Atomicity:** can a logical change span multiple fields?
- **Visibility:** are reading threads guaranteed to see writes from other threads?
- **Waiting points:** are locks held during I/O or while waiting on other threads?
- **Liveness:** can deadlock, starvation, or missed-signal wait loops occur?

### Example of properly scoped locking

```java
final class Balance {
    private int amount;

    synchronized boolean withdraw(int cost) {
        if (cost < 0 || cost > amount) {
            return false;
        }
        amount -= cost;
        return true;
    }

    synchronized void deposit(int value) {
        if (value < 0) {
            throw new IllegalArgumentException();
        }
        amount += value;
    }

    synchronized int snapshot() {
        return amount;
    }
}
```

This is an illustrative class definition. Checking sufficient funds and subtracting are in the **same critical section** so two writers cannot both pass the check. You also need to check for overflow if the domain allows large values. Locking writers while letting readers read the field directly without the lock is still a synchronization bug.

A `volatile int amount` does not make the “check-then-subtract” operation atomic. `AtomicInteger` can solve this with a CAS loop if there is a single field, but the code must retry/validate against the new state. If data spans multiple fields, an immutable snapshot or a critical section is easier to reason about and prove correct.

## 11. Message passing and happens-before: is data in a message visible?

A queue in `java.util.concurrent` does more than just hold elements. The concurrent collection APIs provide **memory guarantees** so that handoffs between threads are meaningful.

For standard `BlockingQueue` implementations, actions in a producer **prior to placing an object into the queue** *happen-before* actions in a consumer **subsequent to removing that object** under the concurrent collections contract. Therefore, a producer can create a payload, initialize its fields, and call `put`; a consumer taking the message via `take` has a JMM guarantee to see the writes that occurred before enqueueing.

However, distinguish between two things:

1. **Publishing data created before sending:** the queue gives producer and consumer clear ordering/visibility.
2. **Mutating the payload after sending:** if the producer continues modifying a mutable object while the consumer is reading it, the queue **does not protect modifications made after enqueueing**.

Dangerous example:

```java
List<String> payload = new ArrayList<>();
payload.add("A");
queue.put(payload);
payload.add("B"); // Can race with the consumer iterating over payload.
```

This is a counter-example snippet that requires declaring/importing `queue` and the appropriate collection types. The fix is to copy into immutable data before sending:

```java
List<String> message = List.copyOf(payload);
queue.put(message);
```

If the list elements themselves are mutable objects, `List.copyOf` only copies the **structure/element references**, not deep-copying each object. You should use immutable element types or establish clear ownership.

## 12. Ordering: which order is message order?

`BlockingQueue` has multiple implementations with different ordering contracts. `ArrayBlockingQueue` and `LinkedBlockingQueue` are used as FIFO queues: elements are retrieved in the order they entered the queue. However, when **multiple producers send concurrently**, who enqueues first is the result of system interleaving, **not a strict order by thread name**.

A single consumer processes each message in dequeue order, but if there are **multiple consumers**, messages can be taken by different workers and **finish processing out of receive order**.

Design questions:

- Do you need to preserve order **within a single producer**?
- Do you need a global order **across multiple producers**? If so, who assigns the sequence and where?
- Do you need **completion** to be sequential, or only **dequeue**?
- Can any message be reprocessed after an error?
- If a message is part of a transaction, how do you maintain consistency across messages?

**FIFO does not mean exactly-once processing.** An in-memory queue does not automatically provide durable storage or transactions. A consumer can take a message and then throw an exception before updating the result. You must decide on retry, dead-letter, idempotency, or durable messaging mechanisms when the problem requires them.

## 13. Backpressure: a crucial difference

A producer can generate work faster than a consumer can process it. If a queue grows without bound, the program can retain more and more objects on the heap and eventually suffer GC pressure or `OutOfMemoryError`.

A **bounded queue** puts a limit on the backlog. When full:

- `put(message)` **waits** until space becomes available; it can be interrupted with `InterruptedException`.
- `offer(message)` does not wait, returning `false` if it cannot be added immediately.
- `offer(message, timeout, unit)` waits up to the timeout and can be interrupted.
- `add(message)` can throw `IllegalStateException` if the queue is bounded and has no space left.

### Backpressure example with deterministic output

Create `BackpressureDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class BackpressureDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(1);

        queue.put(10);
        System.out.println("offer while full=" + queue.offer(20));
        System.out.println("take=" + queue.take());
        System.out.println("offer after take=" + queue.offer(20));
        System.out.println("take again=" + queue.take());
    }
}
```

```bash
javac BackpressureDemo.java
java BackpressureDemo
```

Output:

```text
offer while full=false
take=10
offer after take=true
take again=20
```

The queue has capacity 1. When it holds `10`, adding `20` with `offer` fails. After `take` removes `10`, there is a slot for `20`. The example runs on a single thread to demonstrate the **queue contract**, not to measure concurrent thread throughput.

### Choosing a policy when the queue is full

There is no single policy right for every system. You can:

- **Block the producer:** use `put` to propagate backpressure upstream; consider whether the producer is allowed to wait.
- **Fail fast:** use `offer` returning `false` so the caller sees “busy” and decides whether to retry.
- **Timeout:** use `offer(timeout)` to balance waiting time.
- **Drop/coalesce:** apply only if the domain permits losing or merging messages (for example, certain observability metrics).
- **Scale consumers or partition:** shard load by key when ordering/ownership requirements allow.

With an **unbounded queue**, `put` generally does not block due to a bounded capacity limit, but do not treat “no backpressure” as free: the heap is still finite. A `LinkedBlockingQueue` constructed without a capacity can accept a huge number of elements before hitting actual memory limits.

## 14. Shutdown and cancellation in message passing

In shared state, a synchronized method call can finish as soon as its modification is done. With message passing, there is a **mailbox**, one or more consumers, and producers that may be waiting to send. Shutting down the system requires answering:

1. Will new messages still be accepted?
2. How are producers currently blocked on `put` handled?
3. Does the queue need to be drained before stopping?
4. How is a consumer currently blocked on `take` woken up?
5. Will requests waiting for a response be completed or failed?
6. How many consumers exist and how many stop signals are needed?

### Poison pill (stop message)

In `MessageCounterDemo`, main sends `STOP` after the producers have finished. A single consumer receives STOP and exits. With **N consumers**, you normally need **N stop signals** compatible with the protocol, or another shutdown mechanism; sending a single STOP does not automatically wake all consumers.

If the queue is full and the consumer has already died, `put(STOP)` can wait forever. If producers are still running, STOP can end up ahead of business messages, causing the consumer to exit too early. Therefore, you need an **ordered shutdown procedure**: stop accepting new work, wait for producers or cancel them in a controlled way, allow draining if needed, send valid stop signals, and wait for consumer cleanup.

### Interrupt vs. poison pill

`Thread.interrupt()` is a **cooperative cancellation request** at the thread level; blocking methods like `BlockingQueue.take()` and `put()` can throw `InterruptedException`. A poison pill is **a message in the business protocol**. They are not equivalent:

- An interrupt can stop a consumer while messages still remain in the queue.
- A poison pill usually preserves queue order and allows “drain then stop”, but depends on being able to enqueue the marker.
- You can combine a lifecycle flag with an interrupt/wakeup mechanism; ensure no producer sends after the closed state is entered.

Do not use `Thread.stop()` to cancel a consumer; it is an unsafe and deprecated API.

## 15. Error handling: where do exceptions happen?

In shared state, the caller typically executes the method on its own thread. If the method throws an exception, the caller receives it directly and can handle it on the same call stack.

In message passing, the producer usually only enqueues. Exceptions happen later in the **consumer** and do not automatically “return” to the producer thread:

```text
Producer -> put(command) -> return
Consumer -> take(command) -> process -> exception
```

For the caller to know the outcome, you must design a **response channel**, a future, a callback, a result event, or an appropriate error-recording mechanism. If the owner stops due to an exception and futures remain uncompleted, callers may hang while waiting.

In a worker event loop, you should distinguish:

- **Single-message error:** you can fail that specific request and continue processing the next item if state remains consistent.
- **Error that breaks the owner's invariant:** you may need to stop the owner, notify pending requests, and reinitialize state according to the contract.
- **Infrastructure error:** if the queue or supporting resources are no longer operational, you need a clear shutdown/retry path.

Message passing decouples processing components, but **does not automatically solve retries, exactly-once, transactions, idempotency, or crash recovery**. Those requirements need an application-level protocol and often an appropriate persistence layer.

## 16. Shared state still appears inside message passing

In the JVM, “passing a message” is not transferring data across isolated address spaces like two processes on different machines. Threads can still hold references to the same objects. Thus two rules are needed simultaneously:

1. **The channel must be thread-safe:** for example, `ArrayBlockingQueue` is a primitive designed for multiple producers/consumers.
2. **Message contents must have clear ownership:** ideally an immutable DTO/record containing immutable data; if a mutable payload is transferred, the producer must **stop modifying it** after transfer and the consumer must have clear ownership.

Consequently, the two approaches are often combined:

- The producer creates an **immutable message** in local state.
- The producer calls `put` into a **shared thread-safe queue**.
- The consumer owns the mutable business state and updates it sequentially.
- The consumer can **publish an immutable snapshot** via an `AtomicReference` for fast reads by readers.

This hybrid model uses shared state for the queue/atomic reference, while separating responsibility for writing the main state. There is no absolute boundary where “message passing shares no memory”.

## 17. Should you choose shared state or message passing?

### Choose shared state when

- State is small, invariants are simple, and operations need an immediate response **within the method call**.
- A suitable atomic primitive exists, such as incrementing a counter with `AtomicInteger.incrementAndGet()`.
- Critical sections are short and thread contention is at an acceptable level.
- Operations on the object have a clear contract that can be encapsulated in synchronized methods or a lock protecting the entire invariant.
- You need to read the current snapshot with low latency and already have a proper data-publication mechanism.

### Choose message passing when

- You have a **producer–consumer** pattern, a pipeline, or a worker receiving commands.
- You want a single owner to exclusively manage mutable state to reduce direct write paths.
- You want to decouple work generation from processing and need **bounded backlog/backpressure**.
- You have multiple message types and a processing loop that serializes related state changes.
- You need to batch commands, log events, shard by key, or add request-based response mechanisms.

### Consider a hybrid approach when

- An owner receives messages to update state;
- Public state is represented as an **immutable snapshot**;
- Multiple readers simply fetch the snapshot via an atomic/volatile reference;
- A queue coordinates writers, while readers do not have to send a message just to view data.

Quick selection table:

| Problem | Starting choice | Risks to check |
| --- | --- | --- |
| Many threads incrementing a metric | `AtomicLong` or `LongAdder` depending on snapshot needs | Contention, overflow, `sum()` semantics |
| Transferring money within a small object | `synchronized`/lock or immutable CAS snapshot | Atomicity of check and update |
| One worker consuming many jobs | `BlockingQueue<Job>` + consumer | Backpressure, shutdown, interrupt |
| Many producers sending event logs | Bounded queue + logger owner (if appropriate) | Log loss when queue is full, I/O errors, drain |
| Infrequently changing config, many readers | Immutable config + `AtomicReference` | Readers fetching the same snapshot once |
| Many tasks editing a complex object graph | Single owner receiving commands or lock covering invariant | Queue/lock overhead and state leaks |
| Asynchronous request–response needed | Message + `CompletableFuture`/response channel | Timeout, correlation, exceptional completion |
| Transaction across database and RAM needed | Transaction/idempotency protocol at the appropriate layer | No JVM primitive automatically guarantees distributed atomicity |

## 18. Performance and fairness: do not decide from the model name alone

**Shared state** can be very fast when locks are uncontended or when appropriate atomic primitives are used. If a global class monitor is held across slow I/O, it can cause head-of-line blocking. If many threads modify a hot atomic value, cache contention can reduce throughput.

**Message passing** adds enqueue/dequeue steps, message packaging/copying, and often context switches. In return, the owner can batch multiple messages, optimize state locality, limit the number of writers, and maintain backpressure via a bounded queue.

There is no universal rule that “lock-free = fast” or “queue = always scales well”. A single consumer can become a bottleneck if processing volume is too high. To scale, you can partition state with a separate owner per partition, though cross-partition ordering and invariants become more complex.

You should also distinguish:

- **Fairness:** can a request wait forever because of other requests? Some lock/queue implementations offer fairness options, but with tradeoffs.
- **Throughput:** the number of tasks completed per second.
- **Latency:** the time from when a request is sent until a result is available.
- **Tail latency:** the slowest cases, often heavily impacted by queue backlog.
- **Memory:** the number of messages waiting on the heap, object allocation, and GC pressure.

Measure on real workloads or with proper benchmarks; a few `System.nanoTime()` calls are not enough to declare one model faster due to JIT, warm-up, core count, and scheduling effects.

## 19. Common misconceptions

### 19.1. “Message passing means no more data races”

False if the producer sends a mutable object and continues modifying it. The consumer can read the same object while the producer is writing to it. The queue only guarantees the handoff protocol across queue operations; it does not automatically freeze the payload.

### 19.2. “Shared state only needs volatile”

False if the operation is read-modify-write or if an invariant spans multiple fields. `volatile` is suitable for publishing/reading certain states under a contract, but it does not turn `counter++` into an atomic transaction.

### 19.3. “A single owner means no need to think about synchronization”

False if the owner's data leaks through getters returning mutable references, callbacks, or unprotected futures/collections. Single writer is an **ownership convention**, not a property that the JVM automatically enforces on any object.

### 19.4. “A FIFO queue guarantees all tasks complete in order”

A queue's FIFO guarantees **dequeue** order according to the queue's contract. With multiple consumers, completion times can differ from receive order. With multiple producers, global enqueue order depends on scheduling.

### 19.5. “`put()` always returns immediately”

With a full bounded queue, `put` blocks until space is available or it is interrupted. If the design does not handle cancellation/shutdown, producers can wait indefinitely.

### 19.6. “`Future.cancel(true)` means the consumer has stopped and finished cleanup”

Cancel sends a signal according to the Future/executor contract; it does not guarantee the thread has cleaned up immediately or that the queue has drained. To confirm shutdown is complete, you need appropriate monitoring/waiting mechanisms.

### 19.7. “Once a consumer receives a message, it has definitely processed it successfully”

No. The consumer can throw an exception after `take()`. If you need retry/durable delivery guarantees, a simple in-RAM queue is not enough.

### 19.8. “Sending one poison pill stops every consumer”

If there are multiple consumers, a single marker is received by only one consumer. Design the number of markers or shutdown mechanism to match the number of workers and the distribution contract.

### 19.9. “A `CompletableFuture` for a request reply is itself an immutable message”

A record holding a `CompletableFuture` reference only fixes the reference, while the future itself is a stateful mutable object. You must assign who can complete/cancel it and handle timeouts/exceptions.

### 19.10. “Once using message passing, you don't need to worry about cross-owner consistency”

If a business operation must update state in **two different owners**, sending two consecutive messages does not automatically turn the two changes into a transaction. You need to define ordering, acknowledgments, compensation, or a coordinator; or consider consolidating the invariant under a single owner.

## 20. Self-check

**Question 1.** Two workers call a `synchronized` method on the same counter. Why is there no lost update?

**Answer:** They use the same instance monitor; they cannot execute the protected read-modify-write section at the same time. Related read methods must also use the same mechanism.

**Question 2.** Two producers send `Increment(1)` through a `BlockingQueue` to a single consumer. Does the consumer need to synchronize its local `count` variable with the two producers?

**Answer:** No, if `count` belongs solely to the consumer and producers have no way to modify or read it outside the protocol. The queue handles transferring messages between threads; publishing the result to another thread requires an appropriate publication relationship.

**Question 3.** After `queue.put(list)`, can the producer safely continue calling `list.add(...)`?

**Answer:** There is no safety guarantee if the consumer concurrently reads that mutable list. Use an immutable snapshot or an ownership-transfer protocol with no remaining old writer.

**Question 4.** An `ArrayBlockingQueue` with capacity 1 currently holds one element. What does `offer(newItem)` return?

**Answer:** `false` if there is no space at the time of the call; `put(newItem)` instead waits for space unless interrupted.

**Question 5.** Can STOP be sent into the queue before producers finish?

**Answer:** That easily causes bugs. The consumer may stop before processing messages that arrive after STOP, and producers may block if the queue no longer has a consumer. A clear shutdown/drain protocol is required.

**Question 6.** Do a FIFO queue and two consumers guarantee the first message finishes processing before the second message?

**Answer:** No. FIFO governs the order of taking elements, while two consumers processing in parallel can finish out of order.

**Question 7.** A message with a `CompletableFuture` has been sent; the consumer throws an exception before completing it. Does the caller's `future.join()` automatically receive the exception from the consumer thread?

**Answer:** Not automatically. You need to catch the error and call `completeExceptionally`, or apply timeouts, supervision, and a clear failure policy.

**Question 8.** In shared state, when is a single `AtomicInteger` a more reasonable choice than message passing?

**Answer:** When you only need to update a single integer variable with a simple atomic operation and there is no multi-field invariant, no need for an ownership pipeline, or backpressure.

**Question 9.** An owner receives a message and swaps an `AtomicReference<Config>` for many readers to read. Is this shared state or message passing?

**Answer:** It is a **hybrid model**: message passing for the write path, and a shared immutable snapshot for the read path.

**Question 10.** Two owners handle two parts of a transaction. Can atomic updates of both be guaranteed just by two `queue.put` calls?

**Answer:** No. Two messages create two independent actions. You need an appropriate transaction/coordination or compensation design.

## 21. Conclusion

**Shared state** coordinates by protecting data accessed concurrently by multiple threads. Its strength is directness and potentially high efficiency for small operations; its core requirement is that **every reader and writer obeys the same synchronization mechanism and invariants**.

**Message passing** coordinates by sending data/requests through a thread-safe channel and usually assigning **a single owner** to perform updates. Its strength is reducing shared write access to state and enabling producer–consumer coordination, queueing, and backpressure; in return, you must design message immutability/ownership, processing order, responses, failure handling, and shutdown.

The two approaches are not mutually exclusive: a Java application can use a `BlockingQueue` to send commands, an owner to update state, and an `AtomicReference` holding an immutable snapshot for readers that need fast reads. Choose based on **the unit of consistency, update rate, response needs, and work lifecycle**, rather than slogans like “using a queue means no races” or “using locks isn't scalable”.
