# SynchronousQueue and TransferQueue

## 1. Three Different Milestones: Accepted, Received, and Processing Completed

In a workflow that hands off work between threads, the phrase “sent successfully” can mean several different things:

1. The queue has accepted the work to buffer or forward it.
2. The work has been matched with a receiver.
3. The receiver has finished processing it and produced a result.

Without clearly specifying which milestone is being confirmed, a program may proceed too early or wait in the wrong place.

A buffered queue typically lets a producer send first and a consumer take later. A direct handoff mechanism requires the send operation and the receive operation to meet. A result-returning mechanism must also confirm the processing that happens after receipt.

```text
Accept work
    → match with a receive operation
        → receiver performs processing
            → publish result or error
```

`SynchronousQueue` focuses on direct handoff: there is no space to hold a waiting element as in a capacity-1 queue.

`TransferQueue` is an interface that adds a way to send while waiting for a receiver. The common implementation in the standard library is `LinkedTransferQueue`; it supports both ordinary enqueuing into an unbounded queue and sending in a way that waits to be received.

Both mechanisms give the producer more information about the handoff point. Neither automatically turns into a synchronous business-logic call that waits until a result is ready.

This article uses Java 17 or later. The four programs below are standalone and require no external libraries. Save them with the exact file names, then compile and run from the directory containing the files. Results are printed from the main thread at clearly coordinated points rather than inferred from print ordering across multiple threads.

## 2. SynchronousQueue: A Rendezvous Point Between Sender and Receiver

### 2.1. Not a One-Slot Queue

`SynchronousQueue<E>` has no internal capacity, not even for a single element. Every successful insertion must be paired with a corresponding removal operation. Conversely, a taker also needs a peer making data ready for handoff. See [SynchronousQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SynchronousQueue.html).

Conceptual model:

```text
Buffered queue:
send A → [ A is held ] → later a receiver takes A

SynchronousQueue:
sender A ── meets ── receiver A
           no slot holding A between two independent phases
```

This does not require both threads to start their calls at the exact same wall-clock instant. One side can arrive first and wait for the other.

Nor does it mean zero memory is used: a waiting sender can still retain the object to be transferred, call state, and task resources. Having no element buffer does not mean the overall workflow has no pending work.

### 2.2. Choosing a Method Means Choosing How to Wait for a Partner

| Call on SynchronousQueue | Primary Meaning |
|---|---|
| `put(e)` | Waits to be matched with a receive operation if needed |
| `offer(e)` | Transfers only if it can match a waiting receiver; does not retain the element when returning `false` |
| `offer(e, timeout, unit)` | Spends up to the timeout waiting for a receiver |
| `take()` | Waits for a sender to receive an element |
| `poll()` | Attempts to receive from a peer currently making an element available |
| `poll(timeout, unit)` | Spends up to the timeout waiting for an element to be transferred |

`offer` cannot succeed merely because the structure “is empty.” With this mechanism, there is no empty slot to occupy; the required condition is a receiving partner.

`take` returns the received element. `put` completing normally confirms that the handoff was matched, not that processing of the data after the receive call has finished.

### 2.3. Handoff Program and Observations

File `SynchronousHandoffDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.TimeUnit;

public class SynchronousHandoffDemo {
    public static void main(String[] args) throws Exception {
        var queue = new SynchronousQueue<String>();
        System.out.println("initialSize=" + queue.size());
        System.out.println("remainingCapacity=" + queue.remainingCapacity());
        System.out.println("offerWithoutReceiver=" + queue.offer("unused"));
        System.out.println("pollWithoutSender=" + queue.poll());

        var started = new CountDownLatch(1);
        var pool = Executors.newSingleThreadExecutor();
        try {
            var sender = pool.submit(() -> {
                started.countDown();
                queue.put("A");
                return "handoff completed";
            });
            if (!started.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("sender did not start");
            }

            System.out.println("sizeBeforeReceive=" + queue.size());
            System.out.println("emptyBeforeReceive=" + queue.isEmpty());
            System.out.println("peekBeforeReceive=" + queue.peek());
            System.out.println("received=" + queue.take());
            System.out.println("sender=" + sender.get(10, TimeUnit.SECONDS));

            System.out.println("timedOfferWithoutReceiver=" +
                    queue.offer("B", 30, TimeUnit.MILLISECONDS));
            System.out.println("timedPollWithoutSender=" +
                    queue.poll(30, TimeUnit.MILLISECONDS));
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SynchronousHandoffDemo.java
java SynchronousHandoffDemo
```

Stdout:

```text
initialSize=0
remainingCapacity=0
offerWithoutReceiver=false
pollWithoutSender=null
sizeBeforeReceive=0
emptyBeforeReceive=true
peekBeforeReceive=null
received=A
sender=handoff completed
timedOfferWithoutReceiver=false
timedPollWithoutSender=null
```

Initially there is no receiver, so `offer("unused")` returns `false` and the element is not retained. There is no sender, so `poll()` returns `null`.

Next, the sender task calls `put("A")` while the main thread calls `take()`. The pair of calls match up: the main thread receives A, and the sender can complete.

The `started` gate sits before `put`. It indicates that the task has reached that point; it does not prove that the thread has definitely entered the waiting state at a specific instant. Regardless of which side reaches the queue operation first, the program still has both sides present to complete the handoff.

At the end of the program, the previous sender has already finished and there is no new partner. The timed `offer` returns `false`; the timed `poll` returns `null`.

Elapsed time is not printed because the exercise checks outcome branches rather than promising scheduling precision.

### 2.4. Why Is size Always 0 Even Though Data Can Still Be Transferred?

For collection-style inspection methods, `SynchronousQueue` behaves like an empty collection:

- `size()` is 0.
- `isEmpty()` is `true`.
- `remainingCapacity()` is 0.
- `peek()` is `null`.
- The iterator does not provide a list of waiting elements to traverse.

In the program, the results before receiving remain the same even though the sender task has started. They cannot be used to count waiting senders, measure total system work, or conclude that no handoff activity is taking place.

Do not write “if size equals 0 then don't call take.” With `SynchronousQueue`, the take operation itself is what participates in receiving data.

Similarly, `clear()` is not an operation that cancels all waiting peers. Shutdown workflows must use an appropriate mechanism for in-flight tasks, such as cooperative interruption.

## 3. TransferQueue: Choosing Between Waiting to Be Received or Just Enqueuing

### 3.1. Distinguishing the Interface from the Implementation Class

```text
BlockingQueue
    ├── SynchronousQueue
    └── TransferQueue
            └── LinkedTransferQueue
```

The diagram shows capabilities through interfaces; it does not claim that every edge is a direct superclass relationship.

`SynchronousQueue` does not implement the `TransferQueue` interface; it does not gain a `transfer` method merely because its `put` behavior also requires a receive.

`TransferQueue<E>` extends `BlockingQueue<E>`, adding transfer operations and information about waiting receivers. The interface itself does not mandate that every implementation be unbounded. See [TransferQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TransferQueue.html).

In this article, the concrete class used is `LinkedTransferQueue`. It is a linked-node-based queue with no capacity limit configurable via constructor. Do not confuse it with `LinkedBlockingQueue`, which provides constructors that allow specifying a capacity.

### 3.2. Send Operations with Different Meanings

| Call | What the Sender Requests | Does It Hold Data Waiting for a Receiver? |
|---|---|---|
| Ordinary `put(e)`, `offer(e)` on LinkedTransferQueue | The queue accepts the data | Can buffer it for a later receiver; does not wait for receipt confirmation |
| `transfer(e)` | Waits to transfer the element to a receiver | Can wait for receipt, even if no receiver is present when called |
| `tryTransfer(e)` | Transfers immediately only to a waiting receiver | If it fails, returns `false` without enqueuing the element to wait |
| `tryTransfer(e, timeout, unit)` | Waits for receipt within a time bound | Can wait; if it times out, reports failure per contract |

`tryTransfer(e)` is not another name for `offer(e)`. On `LinkedTransferQueue`, `offer` can accept data when no consumer is present, whereas `tryTransfer` does not do so when it has to return `false`.

Similarly, `offer(e, timeout, unit)` on `LinkedTransferQueue` does not turn into a call that waits for a receiver. Because the class is unbounded in capacity, that timeout does not create a bounded wait for receipt. You must choose `tryTransfer` with a timeout if that is the requirement.

### 3.3. Program Without a Receiver

File `BufferedTransferChoicesDemo.java`:

```java
import java.util.concurrent.LinkedTransferQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TransferQueue;

public class BufferedTransferChoicesDemo {
    public static void main(String[] args) throws InterruptedException {
        TransferQueue<String> queue = new LinkedTransferQueue<>();
        queue.put("A");
        System.out.println("offerB=" + queue.offer("B"));
        System.out.println("timedOfferC=" +
                queue.offer("C", 1, TimeUnit.SECONDS));
        System.out.println("buffered=" + queue);
        System.out.println("taken=" + queue.take() + ","
                + queue.take() + "," + queue.take());

        System.out.println("immediateTransfer=" + queue.tryTransfer("X"));
        System.out.println("afterImmediateFailure=" + queue.poll());
        System.out.println("timedTransfer=" +
                queue.tryTransfer("Y", 30, TimeUnit.MILLISECONDS));
        System.out.println("afterTimedFailure=" + queue.poll());
        System.out.println("remainingCapacity=" + queue.remainingCapacity());
        System.out.println("waitingConsumer=" + queue.hasWaitingConsumer());
        System.out.println("waitingConsumerCount=" +
                queue.getWaitingConsumerCount());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 BufferedTransferChoicesDemo.java
java BufferedTransferChoicesDemo
```

Stdout:

```text
offerB=true
timedOfferC=true
buffered=[A, B, C]
taken=A,B,C
immediateTransfer=false
afterImmediateFailure=null
timedTransfer=false
afterTimedFailure=null
remainingCapacity=2147483647
waitingConsumer=false
waitingConsumerCount=0
```

There is no consumer thread in the program. A, B, and C are still accepted via `put` and `offer`, and then the main thread takes them in the order they were sent.

The key point is that the call inserting A finished before the program began taking A. `LinkedTransferQueue.put` does not need a receiving partner to appear immediately in order to complete.

By contrast, `tryTransfer("X")` has no waiting receiver, so it returns `false`. X does not show up in the subsequent `poll`. The timed transfer of Y also fails and does not leave Y in the queue.

The guarantees that timeout or interruption do not leave the element waiting are explicitly documented in [LinkedTransferQueue transfer operations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedTransferQueue.html#tryTransfer(E,long,java.util.concurrent.TimeUnit)).

`remainingCapacity()` here is `Integer.MAX_VALUE`, indicating that the class is not capacity-bounded. It does not measure remaining memory and does not prove infinite resources.

The receiver counts return 0 or `false` because there is no receiver in the experiment. In a real multi-threaded workflow, they are only point-in-time state observations, not reservations.

## 4. transfer Confirms Handoff, Not Processing Completion

### 4.1. The Most Commonly Misunderstood Point

Consider the call path:

```text
Producer: transfer(work) ── completes when the handoff is matched
                            │
Consumer:              take() receives work
                            → process
                            → produce result
```

The processing code runs after `take()`. The sender can resume before that processing runs to a result.

You should not even infer that every statement immediately after `take` on the receiver side has already executed before `transfer` returns on the sender side. The two threads are scheduled independently once the handoff is matched.

If the business logic needs a result, model a separate reply path. One application-level approach is to send a `CompletableFuture` along with the work object so the processor can publish the result or error.

### 4.2. Program Separating Receipt and Processing with a Latch

File `ReceiptAndReplyDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedTransferQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TransferQueue;

public class ReceiptAndReplyDemo {
    record Work(String text, CompletableFuture<Integer> reply) {}

    public static void main(String[] args) throws Exception {
        TransferQueue<Work> queue = new LinkedTransferQueue<>();
        var received = new CountDownLatch(1);
        var allowProcessing = new CountDownLatch(1);
        var work = new Work("java", new CompletableFuture<>());
        var pool = Executors.newFixedThreadPool(2);

        try {
            var consumer = pool.submit(() -> {
                Work item = queue.take();
                received.countDown();
                try {
                    if (!allowProcessing.await(10, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("processing gate timeout");
                    }
                    item.reply().complete(item.text().length());
                    return "consumer finished";
                } catch (Exception ex) {
                    item.reply().completeExceptionally(ex);
                    throw ex;
                }
            });
            var producer = pool.submit(() -> {
                queue.transfer(work);
                return "receipt confirmed";
            });

            System.out.println("transfer=" + producer.get(10, TimeUnit.SECONDS));
            if (!received.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("receipt gate timeout");
            }
            System.out.println("replyDoneBeforeProcessing=" + work.reply().isDone());

            allowProcessing.countDown();
            System.out.println("result=" + work.reply().get(10, TimeUnit.SECONDS));
            System.out.println("consumer=" + consumer.get(10, TimeUnit.SECONDS));
        } finally {
            allowProcessing.countDown();
            pool.shutdownNow();
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ReceiptAndReplyDemo.java
java ReceiptAndReplyDemo
```

Stdout:

```text
transfer=receipt confirmed
replyDoneBeforeProcessing=false
result=4
consumer=consumer finished
```

`Work` holds the string to process and a future for the reply. The consumer takes the work, opens the `received` gate, and is not allowed to process until the main thread opens `allowProcessing`.

The producer calls `transfer(work)`. The main thread waits for that call to complete, then confirms the receiver has passed the receipt gate. Even so, the reply future is still not done because the processing gate is still closed.

The result `replyDoneBeforeProcessing=false` does not rely on sleeping for a bit and hoping the other side has not finished. It relies on an explicit condition: the program has not yet permitted processing.

After opening the gate, the consumer computes the length of `"java"` and completes the future with 4. The main thread retrieves the result via `get`, then waits for the consumer task to finish.

### 4.3. Four States to Manage When There Is a Reply Path

An application may need to distinguish:

1. Not yet handed off.
2. Received by a peer, waiting to be processed.
3. Processing completed with a result.
4. Processing failed or was cancelled.

`transfer` addresses the handoff boundary; it does not replace all the remaining states.

`CompletableFuture` supports publishing a result or completing with an error. If you forget to complete the error path, a waiter may hold onto a future that no one is responsible for finishing anymore. See [CompletableFuture Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html).

The example catches ordinary exceptions after receipt to report the error into the future, then lets the task fail. This is a teaching pattern about the two milestones, not a full recovery system for all errors, process termination, or resource loss.

### 4.4. Reply Timeout Differs from Handoff Timeout

If the sender waits 1 second for a reply and times out, the work may already have been received and may still be processing. A timeout on `Future.get` does not automatically take the work out of the consumer's hands.

Conversely, if a timed handoff fails, you should not wait for a result as if someone had already taken responsibility for processing it.

Cancellation policy must be tied to actual state. Do not blindly resend every piece of work just because no reply has arrived yet: the first execution may still be running, leading to duplicate execution.

For external operations that must avoid duplication, work identifiers and deduplication mechanisms are business-level decisions. An in-memory handoff structure does not by itself provide system-wide exactly-once processing.

## 5. Timeout and Interruption Must Be Separate Branches

### 5.1. Timeout Outcomes

On `SynchronousQueue`:

- `offer(e, timeout, unit)` returns `false` when it cannot transfer within the wait time.
- `poll(timeout, unit)` returns `null` when it does not receive an element within the wait time.

On `TransferQueue`, the timed `tryTransfer` variant returns `false` if it cannot transfer within the wait time. With `LinkedTransferQueue` in the example, the element from that failed attempt is not left behind for another peer to receive later.

Do not reinterpret `false` as “enqueued to be processed later.” If the application wants a fallback enqueuing branch, you must write and adopt that policy explicitly.

A timeout is not a duration that must be waited out in full if a partner is already ready. Nor is it a hard real-time guarantee of when the thread will definitely get CPU time and return to the caller.

### 5.2. Interruption Outcomes

`SynchronousQueue.put`, `take`, the timed waiting variants, as well as `transfer` and timed `tryTransfer`, can throw `InterruptedException`.

This is typically the control path for a task to cooperate with a stop request. Do not swallow the exception and retry the handoff indefinitely without checking the cancellation request.

If a method can propagate the exception, preserve that branch for the caller to decide. At a task boundary that cannot propagate checked exceptions, you can restore the interrupt flag and exit according to policy.

### 5.3. Program Cancelling an Unreceived transfer

File `InterruptedTransferDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedTransferQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TransferQueue;
import java.util.concurrent.atomic.AtomicReference;

public class InterruptedTransferDemo {
    public static void main(String[] args) throws Exception {
        TransferQueue<String> queue = new LinkedTransferQueue<>();
        var started = new CountDownLatch(1);
        var outcome = new AtomicReference<String>();

        Thread sender = new Thread(() -> {
            started.countDown();
            try {
                queue.transfer("cancelled");
                outcome.set("unexpected receipt");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                outcome.set("failure=" + ex.getClass().getSimpleName()
                        + ", restored=" + Thread.currentThread().isInterrupted());
            }
        }, "transfer-sender");

        sender.start();
        try {
            if (!started.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("sender did not start");
            }
            sender.interrupt();
            sender.join(10_000);
            if (sender.isAlive()) {
                throw new IllegalStateException("sender did not stop");
            }
            System.out.println(outcome.get());
            System.out.println("remainingElement=" + queue.poll());
            System.out.println("senderAlive=" + sender.isAlive());
        } finally {
            sender.interrupt();
            sender.join(10_000);
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 InterruptedTransferDemo.java
java InterruptedTransferDemo
```

Stdout:

```text
failure=InterruptedException, restored=true
remainingElement=null
senderAlive=false
```

No consumer can receive the element in this experiment. The main thread requests interruption, then waits for the sender to finish before inspecting the queue.

The `started` gate sits before the `transfer` call; the signal may arrive before the call begins waiting or while it is waiting. The program does not use observable thread states to force a single execution schedule.

The output shows that the `InterruptedException` branch is handled, the flag is restored, and no `"cancelled"` element remains for `poll` to receive afterward.

The “no receiver” condition keeps the experiment's outcome clear. If in a real application the handoff already succeeded before a stop request arrived, a late signal must not be treated as undoing the work already handed off.

### 5.4. Separating Wait-Abandonment Policy from Work-Reclamation Policy

Abandoning a wait on an unsuccessful transfer differs from reclaiming work that someone else has already received. Abandoning a wait for a reply also differs from stopping processing or I/O activity.

Specify clearly which phase each timeout applies to, who still holds ownership of the work, and who must complete the reply path. If there are multiple attempts, use an appropriate total budget rather than granting the full timeout again at every step.

Do not use `clear`, `remove`, or a size check as a substitute for an application-level cancellation and acknowledgment protocol. Collection operations do not fully model work that has already moved to another thread.

## 6. Waiting Receiver Information: Observation Is Not a Reservation

`TransferQueue` provides:

- `hasWaitingConsumer()`: whether there is a consumer waiting to receive via `take` or a timed `poll`.
- `getWaitingConsumerCount()`: an estimate of the number of waiting consumers.

These metrics are useful for observation or making a decision that can tolerate staleness. They do not guarantee that the state will remain the same until the next call.

The snippet below has a gap between check and action and is not a standalone program:

```java
// Do not infer from this check that transfer will not wait.
if (queue.hasWaitingConsumer()) {
    queue.transfer(item);
}
```

After the check, another producer may match with that receiver; the receiver may also time out or be interrupted. This producer's `transfer` call may still have to wait.

If the true requirement is to transfer only when an immediate match is possible, call `tryTransfer(item)` and handle that call's own return value. Do not use a prior observation to turn a blocking operation into a non-blocking one.

Similarly, do not spin in a loop repeatedly calling `getWaitingConsumerCount()` to try to achieve accuracy. The count is documented as an estimate and can be more expensive than a simple check; it is not a synchronization control mechanism.

A pattern that may fit when the business logic accepts falling back to queuing is:

```java
// Illustrative code inside a method, not a standalone program.
// Policy: if immediate transfer is not possible, fall back to queuing for later receipt.
if (!queue.tryTransfer(item)) {
    queue.put(item);
}
```

You must understand the policy in the fallback branch: it gives up the immediate-receipt requirement and allows data to be buffered. This is no longer a “reject if no receiver” rule.

If priority, expiration, or pending-data limits are needed, the fallback branch must satisfy those requirements rather than merely ensuring the call appears to succeed.

## 7. Capacity, Backpressure, and Progress

### 7.1. SynchronousQueue Forces Sender to Meet Receiver, but Does Not Bound All Resources

When a producer calls `put`, it cannot pre-send multiple elements into an internal buffer. This is a handoff point that forces the source to coordinate with the receiver.

However, if the application keeps creating new tasks or producer threads, each waiting task can still retain a work object. Pending work has shifted from a queue of elements to blocked tasks.

Therefore, you cannot conclude “capacity is 0, so the system cannot accumulate data.” You must also control the number of active senders, work size, and in-flight work count.

### 7.2. LinkedTransferQueue Has No Default Capacity Limit to Prevent Accumulation

Sending via `put` or `offer` on `LinkedTransferQueue` lets the source run ahead of the receiver. If the source is faster over a sustained period, waiting data can grow until resources are exhausted.

Using `transfer` makes a producer wait for receipt on each send. But if there are many independent producers, or if consumers take items and push work elsewhere without bounds, total load is not necessarily bounded as intended.

To bound the number of unfinished jobs until processing completes, the admission boundary must span across both processing and completion. The “received” condition alone is an earlier boundary.

### 7.3. Who Can Make a Waiting Call Complete?

A design can fail to make progress if sending and receiving are scheduled on the wrong resources. Example reasoning:

```text
Executor has only one thread.
Sender task starts: transfer(work) → waits for receiver.
Receiver task is queued behind it in the same pool.
No free thread remains to run the receiver task.
```

Replacing `transfer` with `SynchronousQueue.put` has the same waiting dependency. You must ensure the partner can run, or change the protocol.

Another scenario: the sender holds lock L and then waits for a receiver, while the receiver must acquire lock L before reaching its receive call. The handoff structure cannot release the application's external lock on its own.

Before choosing a blocking method, identify which partner can appear, what resources that partner needs, and whether any of those resources are held by the waiting side.

## 8. Ordering, Data Visibility, and Lifecycle

### 8.1. Do Not Assume an Unpromised Global Order

`SynchronousQueue` has a fairness option at construction time. Enabling the flag selects a FIFO grant policy for waiting peers per the class contract; the default does not promise that fair ordering.

This does not make all peers finish processing in the order they received items. Two jobs with different processing durations can still finish out of order.

For `LinkedTransferQueue`, the contract describes FIFO per producer. In the A, B, C data of the program there is only one sender, so order is easy to verify. With multiple senders, do not infer ID order, business-time order, or completion order from an observed result list.

If global ordering is a business requirement, define the milestone and how it is established; do not rely solely on the queue's name.

### 8.2. The Handoff Point Guarantees Visibility from Sender to Receiver

Actions prior to placing an object into a concurrent queue have a happens-before relationship with actions after another thread accesses or removes that element. The sender should finish constructing the data before handing it off. See [BlockingQueue memory consistency effects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

The queue transfers references, not automatic deep copies. If the sender keeps mutating data after sending while the receiver also reads or mutates it, ownership or synchronization rules are needed for that data itself.

Do not infer the reverse direction—that all updates made during the receiver's processing are already visible to the sender merely because `transfer` finished. Processing may not even have run yet.

In the reply example, the future is a separate mechanism for publishing completion results. Actions of the task have a happens-before relationship with actions after retrieving the result via `Future.get()`. See [Future guarantees](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html).

### 8.3. Inspecting LinkedTransferQueue Does Not Produce a Transactional Snapshot

`LinkedTransferQueue.size()` requires traversal and should not be treated as an exact reservation number while data is changing. Iterators are weakly consistent; operations across multiple elements do not automatically form a single transaction.

Observe the right milestone: the number of items waiting to be received, the number of waiting consumers, the number of waiting sends, and the number of in-flight jobs are different quantities.

Specifically, `SynchronousQueue.size()` is always 0, so graphing queued element count will not show waiting senders. A metric that looks like “empty queue” does not prove the system is idle.

### 8.4. Shutdown Sources Must Have Their Own Protocol

Neither structure automatically provides a universal source-closing operation for all applications. You may need interruption, sentinel/completion signals, or an explicit lifecycle management mechanism.

With `SynchronousQueue`, a completion signal must also be matched with a receiver. If receivers have already stopped, attempting an unbounded `put` of a signal can leave the coordinator waiting indefinitely.

With multiple consumers, a single signal is received by only one peer. You must decide the number of signals, when all producers have finished, and how to handle a peer that has failed.

For work carrying a reply future, shutdown must also resolve unfinished replies. Do not simply let receiver tasks exit and leave senders waiting forever.

## 9. Choosing by the Milestone to Confirm

| Need | Suitable Direction to Consider | What Is Still Needed |
|---|---|---|
| Direct handoff without holding elements in a buffer between two sides | `SynchronousQueue` | Partner must be able to run; cancellation/shutdown policy |
| Sometimes just enqueue, sometimes wait to be received | `TransferQueue` with a suitable implementation, such as `LinkedTransferQueue` | Choose the right method and bound load at the application level |
| Accept only when it can be transferred immediately to a waiting peer | `tryTransfer(e)`, or `SynchronousQueue.offer(e)` depending on the structure in use | Handle the failure branch explicitly |
| Wait for a receiver within a time bound | Timed `tryTransfer`, or timed `offer` on SynchronousQueue | Time budget and interruption branch |
| Need data queued with bounded capacity | A suitable bounded queue | Full-queue policy and operations |
| Need processing results | A reply protocol, such as a future in the message | Complete all success, error, and cancellation paths |
| Need durability after process termination | Persistent storage or a suitable messaging system | Acknowledgment, recovery, and deduplication rules |

The table does not treat one class as faster or stronger in every context. The right mechanism is the one whose completion milestone matches what the caller actually needs to know.

A few API misuse patterns to spot immediately:

- Calling timed `offer` on `LinkedTransferQueue` and thinking it waited for a receiver.
- Calling `tryTransfer`, seeing it fail, and thinking the element is still held for later receipt.
- Using `hasWaitingConsumer` as a pre-reservation of a receiver.
- Treating `transfer` completion as proof that processing succeeded.
- Treating `SynchronousQueue` `size=0` as meaning no tasks are waiting.
- Stopping or resending work without knowing whether it has already been received.

These mistakes are mainly about confusing state and responsibility. Method names are only helpful when tied to the right milestone in the workflow.

## 10. Practice and Self-Check

### Exercise 1: “Empty” Yet Cannot Send

Create a `SynchronousQueue`, call `size`, `isEmpty`, then try `offer("A")` when there is no receiver.

Why are `size=0` and `isEmpty=true`, yet `offer` returns `false`? If replaced with a buffered queue that still has space, what condition changed?

Explanation guide: `SynchronousQueue` has no storage slot to hold A. The presence of a receiving partner, not the number of free slots, is the condition for handoff.

### Exercise 2: Choosing the Right Send Operation on LinkedTransferQueue

There is no consumer. Predict the difference between:

1. `put("A")`.
2. `offer("B", 1, SECONDS)`.
3. `tryTransfer("C")`.
4. `tryTransfer("D", 1, SECONDS)`.

Explanation guide: A and B can be queued for later receipt; C is not queued when immediate transfer fails; D waits for transferability for a period and is not retained if it times out per the class contract.

Do not run an untimed `transfer` on the same thread and expect subsequent code on that thread to reach `take`; that thread cannot act as its own partner.

### Exercise 3: Receipt Is Not Completion of Processing

Keep the processing gate closed as in `ReceiptAndReplyDemo`. The sender has completed `transfer`.

Can you read the processing result from an ordinary variable and assume the new value is definitely present? Which mechanism in the example is used to publish actual completion?

Explanation guide: processing has not even been allowed to start yet. The reply future models the separate result milestone; the handoff point does not replace that milestone.

### Exercise 4: Race After hasWaitingConsumer

Producer P1 sees `hasWaitingConsumer=true`. Before P1 sends, P2 transfers an element to that receiver.

Why can P1 still block if it calls `transfer`? If P1's requirement is to try an immediate transfer only, which operation's result must it use?

Explanation guide: observation does not reserve. Use `tryTransfer` to decide whether an immediate transfer succeeded within the operation itself.

### Exercise 5: Stopping a Workflow with Replies

Multiple jobs have been received but have not completed their futures. The manager requests stopping the consumers.

What must be done for those waiting on results? If a caller has timed out waiting, can it infer that the work has stopped running? If resending, how do you identify the previous execution?

Explanation guide: you must manage the lifecycle of processing and replies, including error/cancellation. A waiter's timeout is not confirmation that work stopped. Identification and deduplication belong to the business protocol.

### Questions Before Finalizing a Handoff Design

1. Does the sender need to know it was accepted, received, or finished processing?
2. Does the structure have a buffer; does the method being called wait for receipt?
3. If transfer fails, where is the element still held?
4. Which partner, resources, and threads are needed for the receiver to appear?
5. How are timeout and interruption outcomes handled differently?
6. Are size or waiting-consumer metrics being used as reservations?
7. After receipt, who is allowed to modify the data and who publishes the result?
8. On shutdown, who is responsible for completing pending sends and replies?

When the three milestones—acceptance, handoff, and processing completion—are clearly separated, learners can choose the right method and explain success, timeout, cancellation, and shutdown paths alike.
