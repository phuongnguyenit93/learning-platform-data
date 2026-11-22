# Message Passing to Reduce Shared Mutable State in Java

## 1. The Problem: Multiple Threads Mutating the Same State

When multiple threads concurrently read and write a **mutable** object (shared mutable state), the outcome can depend on execution order. Consider a counter:

~~~java
// Illustrates a race condition scenario; not a standalone program.
int old = counter;
counter = old + 1;
~~~

Incrementing an integer looks simple, yet it consists of reading, computing, and writing. If two threads both observe `old == 10`, both may write `11`, losing one increment. `volatile` can help with visibility and certain ordering guarantees, but it does not make a multi-step increment atomic. `synchronized`, `Lock`, or `AtomicInteger` are valid solutions depending on requirements; when data is complex and consists of multiple interrelated fields, maintaining all invariants with locks can become hard to reason about.

**Message passing** takes a different organizational approach: **a single entity owns and mutates the state**, and all other entities send **operation request messages** to the owner instead of modifying that state directly. The owner processes each message in a disciplined control flow.

~~~text
Producer A ── Add(2) ─┐
                      ├──> Mailbox (thread-safe queue) ──> Owner ──> state
Producer B ── Read() ─┘                                │
                                                       └──> reply/result
~~~

For example, the owner holds a balance, a counter, or a slice of application data. A producer sends an `Add(2)` command; the owner updates the state; if the sender needs a result, the owner replies via a `CompletableFuture` or a response queue. Producers do not need to hold a reference to the state itself.

**Reducing shared mutable state does not mean every component is immutable or synchronization-free.** `BlockingQueue` and `CompletableFuture` themselves are thread-safe coordination structures; the difference is that mutable business data is confined within a single owner rather than being updated arbitrarily by many threads.

This lesson applies to Java concurrency in general and does not depend on Spring or framework mechanisms.

## 2. Four Components of Message Passing Design

| Component | Role | Key Rules |
| --- | --- | --- |
| **Message** | Carries data or operation intent | Prefer immutable; contains enough information to be processed |
| **Sender / producer** | Creates and sends messages | Does not mutate state belonging to the owner; handles full/closed mailbox cases |
| **Mailbox / channel** | Transfers messages between threads | Thread-safe, with clear ordering and capacity policies |
| **Owner / consumer** | Reads messages and updates its own state | Only a single entity mutates each piece of state; handles errors and replies |

Messages typically fall into two categories:

- **Command:** a request to change state, such as `Deposit(amount)`, `Reserve(id)`, `Add(delta)`. If a result is needed, the command carries a reply channel or correlation ID.
- **Query:** a read request, such as `GetBalance(reply)`. The owner returns a **snapshot or immutable value**, rather than returning its internal mutable collection directly.

In Java 17, `record` is well suited for declaring data messages:

~~~java
record Deposit(long amount, String transactionId) {}
record BalanceSnapshot(long cents) {}
~~~

A record's fields are `final`, but **records only guarantee shallow immutability**. If a record holds an `ArrayList` or a mutable array, the caller can still mutate its contents after sending. When a message contains a collection, use defensive copies and immutable views, such as `List.copyOf(items)`, provided the elements themselves are not mutated unexpectedly.

### Ordering and Correctness

An owner sequentially processes messages taken from its mailbox, so no two update operations run concurrently **within that owner**. With a FIFO queue like `ArrayBlockingQueue`, messages are dequeued in the order they were successfully enqueued. When multiple producers run concurrently, the order among competing sends depends on scheduling; do not treat log order written on two different threads as a guaranteed global order.

**Invariants** such as "non-negative balance" or "total equals the sum of accepted transactions" must be checked and updated **right inside the owner**. Move the entire "read, check, mutate" sequence into a single unified command; do not split it into a separate query followed by a command if atomicity between those two steps is required.

## 3. What Tools Does Standard Java Provide?

Message passing is a **design pattern**, not a dedicated keyword in Java.

| API | Suitable When | Things to Remember |
| --- | --- | --- |
| `BlockingQueue<E>` | Producer/consumer across multiple platform threads | `put/take` block; use a bounded queue to create backpressure |
| `ArrayBlockingQueue<E>` | Fixed capacity, FIFO needed | Thread-safe; `put` may wait when full |
| `LinkedBlockingQueue<E>` | Bounded or unbounded queue needed | Default constructor uses a very large capacity; avoid unbounded backlog buildup |
| `CompletableFuture<T>` | Returning results/errors to the sender is needed | Completing a future delivers a result; it does not automatically stop an already-sent command |
| `ExecutorService` | Managing the consumer execution thread is needed | A single-thread executor easily serves as an owner; must be shut down/closed |
| `Flow.Publisher/Subscriber` | Asynchronous streams with a demand/backpressure protocol | `Flow` backpressure differs from `BlockingQueue` blocking operations |
| `SynchronousQueue<E>` | Direct handoff to a receiving thread | Stores no buffer; only pairs a put with a take |

An actor with a mailbox is a common way to organize message passing, but **Java does not automatically enforce actor isolation just by declaring a queue**. You must actually keep state private, avoid returning mutable references, confine state processing to the owner, and define the lifecycle. A thread-safe queue does not automatically make every object inside a message thread-safe.

## 4. Complete Java 17 Example: CounterMailbox with a Single Owner

This example illustrates the ownership and reply rules:

1. `CounterMailbox` keeps `int total` **only on the owner thread's stack**.
2. Producers send `Add` or `Snapshot` through an `ArrayBlockingQueue<Message>` with capacity 2.
3. Each command carries a `CompletableFuture<Integer>` as a reply channel; the owner is where the future is completed.
4. `Math.addExact` checks for overflow. On error, the owner returns a failed future and keeps the previous value.
5. `Stop` is the stop message. When closing, the system enqueues `Stop` **after already-enqueued messages** and waits for the owner to finish.
6. `synchronized` only protects **sending to and closing the mailbox**; it is not used to protect `total`, because no thread other than the owner accesses `total` directly.

Save to `MessagePassingDemo.java`:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;

public class MessagePassingDemo {
    private sealed interface Message
            permits Add, Snapshot, Stop {}

    private record Add(
        int delta, CompletableFuture<Integer> reply
    ) implements Message {}

    private record Snapshot(
        CompletableFuture<Integer> reply
    ) implements Message {}

    private enum Stop implements Message {
        INSTANCE
    }

    private static final class CounterMailbox implements AutoCloseable {
        private final BlockingQueue<Message> inbox;
        private final Thread owner;
        private boolean closed;

        CounterMailbox(int capacity) {
            this.inbox = new ArrayBlockingQueue<>(capacity);
            this.owner = new Thread(this::runLoop, "counter-owner");
            this.owner.start();
        }

        CompletionStage<Integer> add(int delta)
                throws InterruptedException {
            CompletableFuture<Integer> reply =
                new CompletableFuture<>();
            enqueue(new Add(delta, reply));
            return reply.minimalCompletionStage();
        }

        CompletionStage<Integer> snapshot()
                throws InterruptedException {
            CompletableFuture<Integer> reply =
                new CompletableFuture<>();
            enqueue(new Snapshot(reply));
            return reply.minimalCompletionStage();
        }

        private synchronized void enqueue(Message message)
                throws InterruptedException {
            if (closed) {
                throw new IllegalStateException("Mailbox đã đóng");
            }
            // Block if the queue is full: producer experiences backpressure.
            inbox.put(message);
        }

        private void runLoop() {
            int total = 0; // Only the owner thread reads and writes.
            try {
                while (true) {
                    Message message = inbox.take();
                    if (message == Stop.INSTANCE) {
                        return;
                    }
                    if (message instanceof Add add) {
                        try {
                            int next = Math.addExact(total, add.delta());
                            total = next;
                            add.reply().complete(total);
                        } catch (ArithmeticException error) {
                            add.reply().completeExceptionally(error);
                        }
                    } else if (message instanceof Snapshot query) {
                        query.reply().complete(total);
                    }
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        }

        @Override
        public synchronized void close()
                throws InterruptedException {
            if (!closed) {
                // Wait for space if needed, then enqueue Stop at the end of the queue.
                inbox.put(Stop.INSTANCE);
                closed = true;
            }
            owner.join();
        }
    }

    public static void main(String[] args) throws Exception {
        try (CounterMailbox counter = new CounterMailbox(2)) {
            CompletionStage<Integer> first = counter.add(2);
            CompletionStage<Integer> second = counter.add(3);
            CompletionStage<Integer> state = counter.snapshot();

            System.out.println("+2 -> " +
                first.toCompletableFuture().join());
            System.out.println("+3 -> " +
                second.toCompletableFuture().join());
            System.out.println("snapshot -> " +
                state.toCompletableFuture().join());

            CompletionStage<Integer> overflow =
                counter.add(Integer.MAX_VALUE);
            try {
                overflow.toCompletableFuture().join();
            } catch (CompletionException error) {
                System.out.println("overflow -> " +
                    error.getCause().getClass().getSimpleName());
            }

            System.out.println("after error -> " +
                counter.snapshot().toCompletableFuture().join());
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 MessagePassingDemo.java
java MessagePassingDemo
~~~

Stdout:

~~~text
+2 -> 2
+3 -> 5
snapshot -> 5
overflow -> ArithmeticException
after error -> 5
~~~

The lines always appear in this order even though the owner runs on a different thread: `main` puts `Add(2)`, `Add(3)`, and `Snapshot` into the queue in order, then prints the results in the order it awaits each stage. `Math.addExact(5, Integer.MAX_VALUE)` throws `ArithmeticException`, and `total` is only assigned after the addition succeeds, so the final snapshot remains `5`.

### Why Does This Design Reduce Races?

Producers are not given a reference to `total`. They can only describe a change via `Add(delta)`. Each `Add` processing step in the owner performs the read, computation, overflow check, and write before the owner processes the next message. Therefore, **lost updates between two producers** cannot occur when only the owner is permitted to update state.

`ArrayBlockingQueue` provides appropriate synchronization for transferring messages between producers and the consumer. Under the `BlockingQueue` contract, actions in a thread prior to placing an object into the queue happen-before actions subsequent to the access or removal of that element from the queue in another thread. This ensures the owner observes properly published messages. For results, `CompletableFuture` is a safe coordination mechanism for producers to receive completion signals.

`minimalCompletionStage()` (Java 9+) returns a composition-only view, making it harder for callers to interfere with the `complete` operation of the source future. Callers can still call `toCompletableFuture()` to await the view's result, as in the example; operations on the future returned from the view do not grant direct control over the mailbox's internal future.

### Limitations of the Example

This is an **in-JVM** example; it does not persist to disk and does not implement retries. There is no mechanism to restart the owner if the thread encounters a fatal error. The `InterruptedException` path in the owner illustrates preserving the interrupt flag, whereas a production application must handle all pending commands, complete replies exceptionally, publish the stopped state, and decide on retry/restart. The example only calls `close()` from a thread outside the owner and does not actively interrupt the owner. Synchronizing `enqueue/close` ensures no further commands are accepted after `Stop` has been enqueued when using this class's API properly.

## 5. Blocking and Backpressure Considerations

Message passing should not be used as an excuse to create unbounded queues. If producers send faster than the owner processes, the number of pending messages grows, leading to memory exhaustion and increased latency.

In the example, `ArrayBlockingQueue<>(2)` sets a limit of **two pending messages in the queue** (excluding the message the owner has already taken). When full, `put()` blocks the producer until space becomes available. That is a form of **backpressure**: the rate of work creation is throttled by the rate of consumption.

Main options:

| Send Method | When Queue Is Full | Trade-off |
| --- | --- | --- |
| `put(message)` | Waits until space is available; may be interrupted | Simple, but can block the calling thread |
| `offer(message)` | Returns `false` immediately | Requires a rejection, retry, or drop policy |
| `offer(message, timeout, unit)` | Waits for a bounded time then returns `false` | Controls wait time, still needs failure handling |
| `add(message)` | Throws `IllegalStateException` when bounded queue is full | Suitable when fail-fast via exception is desired |

Do not call `put()` on the same mailbox from the **owner thread** if the queue can fill up: the owner would wait for itself to take a message from the queue, causing a deadlock. Similarly, if a `CompletableFuture` continuation runs synchronously on the owner and invokes a blocking operation waiting on the owner, a wait cycle can occur. In high-throughput systems, offload heavy processing or blocking I/O from the owner's message loop, or use an asynchronous design with explicit backpressure.

Under overload, define a policy per message type: wait, return an overload error, drop non-critical messages, coalesce snapshots, or partition. **Do not automatically retry state-mutating commands** without solving idempotency; a command may have already been processed even if the caller timed out.

## 6. Request–Reply: Results, Errors, Timeouts, and Cancellation

Not every message needs a reply. Events like "a change occurred" can be fire-and-forget **only when the application accepts not knowing the outcome immediately**. For commands requiring confirmation, use a reply:

~~~java
// Illustrative snippet: a layer receiving CompletionStage<Integer>
// from CounterMailbox.add(...) in section 4.
CompletionStage<String> report =
    counter.add(7).thenApply(value -> "total=" + value);
~~~

`thenApply` here only runs when `add(7)` succeeds. If the owner completes the future exceptionally, `report` also fails unless there is a recovery handler. Callers can use `handle`, `exceptionally`, or `whenComplete` depending on their needs.

**A request–reply timeout does not mean the message is removed from the mailbox.** If a caller waits on a stage for a period of time and then gives up, the command may still be in the queue or already processed. Likewise, canceling the caller's future does not automatically remove the message or roll back already-mutated state.

For reliable handling in complex applications, you can add:

- `requestId`/correlation ID to match messages and responses.
- A deadline checked at the owner before execution if an expired command is no longer valid.
- An idempotency key so retries do not apply the same update twice.
- Explicit result states: accepted, rejected, committed, failed; distinguish *enqueued* from *processed*.
- A cap on in-flight requests awaiting replies and a way to clean up abandoned futures.

The `CompletionStage` example in section 4 represents **the result after the owner has processed the command**, not merely "placed into the queue". Successful enqueueing and reply completion happen at two different points in time.

## 7. Immutable Data, Ownership, and Avoiding Mutable Reference Leaks

Suppose an owner holds a `Map<String, List<String>>`. A query that returns the internal list directly breaks isolation:

~~~java
// Flawed approach in an owner managing a mutable List:
reply.complete(internalList); // caller can modify the list!
~~~

It is better to create a snapshot:

~~~java
// Illustrative, placed inside the owner; internalList belongs to the owner.
reply.complete(java.util.List.copyOf(internalList));
~~~

`List.copyOf` creates a list that disallows modification through the returned list's API, but if the elements inside are mutable and still modified elsewhere, the data is not yet a deep snapshot. When full isolation is required, copy nested structures or return an immutable DTO containing only the necessary data.

The same applies to input messages:

~~~java
record SubmitBatch(java.util.List<String> items) {
    SubmitBatch {
        items = java.util.List.copyOf(items);
    }
}
~~~

This is a valid Java 17 record: the compact constructor turns `items` into an immutable copy before it is automatically assigned to the field. `String` is immutable, so in this example there is no mutable-element issue.

Do not send a `ByteBuffer` that the producer continues mutating while the owner reads it; do not retain a shared mutable object by reference and assume that merely calling `queue.put` eliminates races. Ownership rules only hold if **no other actor concurrently mutates the object the owner is operating on**.

## 8. When a Single Owner Becomes a Bottleneck

Message passing trades centralized state-update rights for easy-to-reason-about rules. If every operation goes through a single owner, update throughput is limited by the rate at which that owner processes each message. Common scaling approaches:

1. **Key-based partitioning:** For example, each account ID is mapped to a fixed mailbox/owner. Each owner handles the state of a distinct set of keys, reducing contention; operations that must touch multiple partitions simultaneously require a separate coordination protocol.
2. **Separating commands from heavy computation:** The owner receives computation results as a new message instead of blocking its processing loop while making network calls or running heavy tasks. Ensure late results remain valid against the current state version.
3. **Batching:** Group multiple small commands when semantics allow; clearly define ordering, commit conditions, and how each command receives its reply.
4. **Coalescing:** For "latest value" state, multiple pending updates can sometimes be collapsed into one final update. Does not apply to commands where every occurrence must be recorded, such as money transfers.
5. **Snapshot reads:** Provide immutable snapshots to multiple readers, while clearly specifying snapshot freshness. A snapshot may be stale relative to recently enqueued commands.

A multi-owner system still has to address inter-owner messaging, cross-partition ordering, error handling, and consistency. An in-JVM local queue model does not by itself provide durability, exactly-once delivery, or distributed transactions.

## 9. Comparison with synchronized, Atomics, and ThreadLocal

| Option | Where State Is Updated | When to Consider |
| --- | --- | --- |
| `synchronized` / `ReentrantLock` | Multiple threads access under lock protection | Small shared state, simple invariants, and acceptable contention |
| `AtomicInteger` / CAS | Multiple threads update via atomic operations | A few independent variables/operations, avoiding simple lost updates |
| `ThreadLocal` | Each thread holds its own state | Data is truly thread-bound; requires cleanup when thread pools reuse threads |
| **Message passing** | One owner processes state, other threads send messages | Complex invariants, need to serialize commands and minimize shared mutable state |

These techniques are not mutually exclusive: a mailbox uses internal synchronization; replies can use safe primitives; multiple owners can use `AtomicLong` for aggregate metrics. What to avoid is mixing ownership without discipline—for example, having an owner process `Add` via a queue while also letting external threads call `counter++` directly.

Compared to `ThreadLocal`, an owner's state **is bound to a logical component** and message protocol, not implicitly tied to whichever thread happens to handle a request. When work needs to move across multiple threads or controlled access is required, message passing makes the handoff path clearer.

## 10. Shutdown, Unexpected Errors, and Observability

The `Stop` example is a **poison pill**: a special message telling the consumer to stop. With a single owner and a FIFO queue, sending `Stop` after already-enqueued messages allows all preceding messages to be processed. If multiple consumers pull from the same queue, one poison pill only stops **one** consumer; you must design the appropriate number of signals or a suitable shutdown mechanism.

Real-world applications must handle the following cases:

- **Reject new messages when closing:** checking `closed` and enqueueing must share the same synchronization policy. Do not allow messages to arrive after `Stop`, because no one will process them.
- **Avoid hanging when the consumer dies:** if the owner stops unexpectedly, pending futures must be completed exceptionally and the queue should be drained/rejected. `close` using `put` can block forever if the consumer has already died and the queue is full.
- **Interrupts:** `BlockingQueue.put/take` can throw `InterruptedException`. Choose a clear fail/stop/retry behavior and restore the interrupt flag if not handling it further. Do not accidentally swallow interrupts.
- **Business errors:** fail only the affected message if execution can continue safely, preserving invariants before reporting the error. In the example, overflow does not kill the owner.
- **Heavy callbacks:** `CompletableFuture.complete` may directly execute dependent actions without the `Async` suffix on the completing thread. If the consumer is the owner, a heavy continuation can stall the entire mailbox; offload heavy work to an appropriate executor.
- **Metrics:** track queue depth, rejected message count, enqueue wait time, time from enqueue to processing, error count, and age of the oldest message.
- **Shutdown protocol:** decide whether `close` must drain all messages, reject immediately, or checkpoint state before stopping. `Thread.join` waits for the owner to terminate; it does not prove messages were durably persisted.

Taking a message off the queue only indicates *it was handed off to the owner*. If the owner dies before committing, the sender should not be told the operation succeeded. When crash durability is required, add durable storage/protocols and commit acknowledgements; an in-memory queue does not solve that.

## 11. Common Pitfalls and How to Test

| Pitfall | Consequence | Prevention |
| --- | --- | --- |
| Sending a mutable reference and continuing to mutate it in the producer | Data race despite using a queue | Immutable messages or genuine ownership transfer |
| Owner returning an internal collection | Caller breaks owner invariants | Return immutable snapshots/DTOs |
| Unbounded queue | Message backlog and memory growth | Bounded queue, backpressure, overload policy |
| Producer holding another lock while waiting on `put` | Potential deadlock with the owner | Check lock ordering; avoid blocking inside critical sections |
| Owner calling `join` on a reply that the owner itself must complete | Self-wait deadlock | Turn into non-blocking messages/continuations |
| Checking only enqueue success | Reporting success before the command is processed | Acknowledge after processing |
| Caller timing out and resending non-idempotent commands | Same update applied twice | Request ID, deadline, idempotency |
| Single owner for all unrelated data | Performance bottleneck | Partition by key and manage cross-partition work |
| Catching all exceptions and ignoring them | Hung stages, lost errors, or corrupted state | Fail replies, log/record errors, define restart policy |
| Sending `Stop` before other producers finish | Messages after `Stop` are never processed | Close admission first, then enqueue `Stop`, await shutdown |

To test this lesson yourself:

1. Run `MessagePassingDemo` and verify the exact five lines of stdout.
2. Submit many `add(1)` commands from different producers; after **all commands have been enqueued**, send `snapshot`; the total must equal the number of successful commands. Do not assert per-producer ordering without an ordering protocol.
3. Try `add(Integer.MAX_VALUE)` after `5`: it must fail with an overflow error and `total` must remain `5`.
4. Reduce queue capacity to `1` and make the owner process slowly in a controlled manner; verify that `put` actually blocks or `offer` returns `false` according to policy.
5. Try `add` after `close`: it must be rejected; no operations should be accepted after the stop signal.
6. Simulate an abrupt owner death in an experimental implementation: ensure callers receive a failure rather than waiting on the future forever. This is a production requirement to add beyond the demo.
7. Send a message containing a mutable collection and mutate the collection in the producer after enqueueing; verify why defensive copying is necessary.

## 12. Practical Conclusion

**Message passing reduces shared mutable state by turning mutation rights into a single owner's responsibility and turning interactions into messages with clear contracts.** The key is not the queue class name: it lies in ownership boundaries, immutability of transferred data, processing order, and how results/errors are delivered.

With Java 17, `record`/`sealed interface` help model messages, `BlockingQueue` safely transfers messages between threads, and `CompletableFuture` provides composable request–reply. An effective design also requires bounded queues, avoiding accidental owner blocking, cleaning up resources, and completing replies along every error path. When a single owner limits throughput, partition by key rather than reverting to letting multiple threads arbitrarily mutate the same object.