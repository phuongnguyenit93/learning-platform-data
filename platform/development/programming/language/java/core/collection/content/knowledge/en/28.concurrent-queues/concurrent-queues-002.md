# BlockingQueue: put, take, and Timed Operations

## 1. A Queue Is Also a Coordination Point Between Threads

One thread produces work; another thread processes it. With an ordinary queue, the consumer has to decide what to do when no element is available yet, and the producer has to decide what to do when there is no space left. Writing your own loop to check, sleep, and check again makes the program both hard to stop and prone to wasting CPU unnecessarily.

`BlockingQueue<E>` adds operations that can wait for the appropriate condition. The side creating data is called the producer; the side taking data to process is called the consumer.

For a bounded-capacity queue, the basic model is:

```text
Producer
    → puts work into the queue
        → consumer takes work out
            → processes work

When full: the producer can wait or give up.
When no element is available to take: the consumer can wait or give up.
```

You must distinguish **waiting to insert/take data** from **waiting for work to finish processing**. A successful insertion call does not mean the work has been processed. A successful take call also does not mean subsequent processing will succeed.

This lesson focuses on `put`, `take`, timed `offer` and `poll`, along with interruption, capacity, and termination conditions. The examples use `ArrayBlockingQueue` for fixed capacity and clear FIFO ordering.

`BlockingQueue` is an interface; do not assume every implementation retrieves elements in FIFO order or uses a single storage region with the same behavior. For example, priority-based or delay-based queues follow different element selection rules.

The programs below are standalone, target Java 17 or later, and require no external libraries. Save each file with its exact name, compile, and run in the directory containing the file. Multi-threaded results are collected before printing so output does not depend on thread print order.

## 2. Choosing How to React When an Operation Cannot Proceed

A group of methods lets you choose the policy directly at the call site:

| Need | Signal via exception if not possible | Return special value | Wait without a caller-specified timeout | Wait with a timeout |
|---|---|---|---|---|
| Insert element | `add(e)` | `offer(e)` | `put(e)` | `offer(e, timeout, unit)` |
| Retrieve and remove head | `remove()` | `poll()` | `take()` | `poll(timeout, unit)` |
| Examine head only | `element()` | `peek()` | No corresponding form | No corresponding form |

When there is no space left, `offer` returns `false`; when there is no element to take, `poll` returns `null`. The timed forms use those same return values if the operation cannot complete within the wait duration. `put` does not return a success flag; `take` returns the retrieved element. See the [Java 17 BlockingQueue method summary](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

### 2.1. Special Return Values Are Different from Input Errors

`false` does not mean every error in `offer` is converted into `false`. For instance, passing `null` into a `BlockingQueue` throws `NullPointerException`. Errors related to element type or properties also depend on the implementation's rules.

Disallowing `null` elements makes it possible to distinguish a `poll` result with no data from a real data item. Do not use `null` as an end-of-stream sentinel placed in the queue.

Also read the overload carefully: `remove()` retrieves and removes the head of the queue and may throw when empty; `remove(Object)` searches for and removes a matching element. They do not serve the same purpose.

### 2.2. Program with Non-Blocking Operations

File `QueueMethodFormsDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class QueueMethodFormsDemo {
    public static void main(String[] args) {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
        System.out.println("offerA=" + queue.offer("A"));
        System.out.println("offerB=" + queue.offer("B"));
        System.out.println("peek=" + queue.peek());

        try {
            queue.add("B");
        } catch (IllegalStateException ex) {
            System.out.println("fullAdd=" + ex.getClass().getSimpleName());
        }
        System.out.println("remove=" + queue.remove());
        System.out.println("emptyPoll=" + queue.poll());
        try {
            queue.element();
        } catch (java.util.NoSuchElementException ex) {
            System.out.println("emptyElement=" + ex.getClass().getSimpleName());
        }
        try {
            queue.offer(null);
        } catch (NullPointerException ex) {
            System.out.println("nullOffer=" + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 QueueMethodFormsDemo.java
java QueueMethodFormsDemo
```

Stdout:

```text
offerA=true
offerB=false
peek=A
fullAdd=IllegalStateException
remove=A
emptyPoll=null
emptyElement=NoSuchElementException
nullOffer=NullPointerException
```

The capacity is only 1. A is added successfully, and B cannot be added yet, so `offer` returns `false`. `peek` only inspects A; since A is still present, `add("B")` throws `IllegalStateException`.

After `remove()` takes A, `poll()` returns `null` because the queue is empty. `element()` on an empty queue throws `NoSuchElementException`. Attempting to insert `null` is rejected with its own exception.

These results are produced on a single thread without contention. They help clarify each method's policy before introducing cross-thread waiting.

“Non-waiting” here means not waiting for the queue to have space or an element. Do not assume a non-timed call is always lock-free or cannot take time due to internal coordination.

## 3. put and take: Waiting for Conditions to Change

### 3.1. put Waits for Space, take Waits for an Element

With `ArrayBlockingQueue`, capacity is fixed at creation and elements are retrieved in FIFO order. If full, `put(e)` waits until space is available to insert; if empty, `take()` waits until an element is available to retrieve. If the condition is already satisfied, they can complete without waiting for another thread. See [Java 17 ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html).

Do not interpret “blocking” as the program spawning extra threads on its own. The calling thread itself may have to wait. If that thread is serving a request, its capacity to serve is also tied up while it waits.

A successful `take` removes the element from the queue. Two consumers will not both receive the same retrieval of a given element sitting in the queue. However, an application can intentionally insert the same object multiple times; this structure is not a deduplicating set.

### 3.2. Program Coordinating Put and Take

File `WaitingPutTakeDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class WaitingPutTakeDemo {
    public static void main(String[] args) throws Exception {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
        queue.put("first");
        var producerStarted = new CountDownLatch(1);
        var consumerStarted = new CountDownLatch(1);
        var pool = Executors.newFixedThreadPool(2);

        try {
            var producer = pool.submit(() -> {
                producerStarted.countDown();
                queue.put("second");
                return "put completed";
            });
            if (!producerStarted.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("producer did not start");
            }

            System.out.println("takenFirst=" + queue.take());
            System.out.println("producer=" + producer.get(10, TimeUnit.SECONDS));
            System.out.println("takenSecond=" + queue.take());

            var consumer = pool.submit(() -> {
                consumerStarted.countDown();
                return queue.take();
            });
            if (!consumerStarted.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("consumer did not start");
            }
            queue.put("third");
            System.out.println("consumer=" + consumer.get(10, TimeUnit.SECONDS));
            System.out.println("empty=" + queue.isEmpty());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 WaitingPutTakeDemo.java
java WaitingPutTakeDemo
```

Stdout:

```text
takenFirst=first
producer=put completed
takenSecond=second
consumer=third
empty=true
```

The queue initially holds `"first"`. The producer wants to insert `"second"`. The main thread takes `"first"`, freeing space; after the producer task finishes, the main thread takes `"second"`.

In the second part, the consumer calls `take` on a queue that currently has no data. The main thread puts `"third"` in, and the consumer receives it.

The `producerStarted` and `consumerStarted` latches indicate that each task has reached the point just before its queue call. Opening a latch does not prove the thread immediately enters a waiting state on the very next instruction. Scheduling may allow the main thread to change the condition before the queue call actually begins.

The program's correctness does not rely on guessing that timing: inserting `"second"` cannot complete before `"first"`'s slot is freed, and the final consumer only receives data after that data has been inserted.

The 10-second timeout on the latches and `Future.get` is a bound to detect a stalled experiment. It does not give the `put` and `take` calls inside the tasks a 10-second timeout of their own.

### 3.3. Unbounded Waiting Still Needs an Exit Path

A `take()` call can keep waiting if no one else ever inserts data. A `put()` call can keep waiting if the queue is full and no one else ever takes data. The program must determine which side can still change the condition.

Common termination approaches to consider are thread interruption, a stop message following a protocol, or replacing the call with a timed form to periodically check status. Which approach to choose depends on the workflow's lifecycle.

Do not switch to `put` merely out of a desire “not to lose data” while ignoring the possibility that the consumer has stopped. Data remaining in a producer's variable does not mean the system can still make progress.

## 4. Timed offer and poll

### 4.1. Reading Outcomes in Three Branches

For `offer(e, timeout, unit)`:

- `true`: the element was inserted.
- `false`: the element could not be inserted within the call's wait time.
- `InterruptedException`: the thread was interrupted during the wait operation.

For `poll(timeout, unit)`:

- Returns a non-`null` element: the element was retrieved and removed from the queue.
- `null`: no element could be retrieved within the wait time.
- `InterruptedException`: the wait operation was interrupted.

Do not collapse the interruption branch into the timeout branch. One branch is a timing policy; the other is typically a cancellation or shutdown request from thread management.

These two methods do not use `TimeoutException` to signal a timeout. Do not confuse them with `Future.get(timeout, unit)`, which is a different result-waiting API.

### 4.2. Program with Steady Full and Empty Conditions

File `TimedQueueDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

public class TimedQueueDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
        queue.put("A");

        boolean accepted = queue.offer("B", 40, TimeUnit.MILLISECONDS);
        System.out.println("fullTimedOffer=" + accepted);
        System.out.println("existing=" + queue.take());

        String missing = queue.poll(40, TimeUnit.MILLISECONDS);
        System.out.println("emptyTimedPoll=" + missing);

        System.out.println("availableTimedOffer=" +
                queue.offer("C", 1, TimeUnit.SECONDS));
        System.out.println("availableTimedPoll=" +
                queue.poll(1, TimeUnit.SECONDS));

        System.out.println("zeroTimedOffer=" +
                queue.offer("D", 0, TimeUnit.NANOSECONDS));
        System.out.println("zeroTimedPoll=" +
                queue.poll(0, TimeUnit.NANOSECONDS));
        System.out.println("zeroTimedPollEmpty=" +
                queue.poll(0, TimeUnit.NANOSECONDS));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 TimedQueueDemo.java
java TimedQueueDemo
```

Stdout:

```text
fullTimedOffer=false
existing=A
emptyTimedPoll=null
availableTimedOffer=true
availableTimedPoll=C
zeroTimedOffer=true
zeroTimedPoll=D
zeroTimedPollEmpty=null
```

When the queue holds A and there is no consumer during `offer("B", ...)`, the result is `false`. A remains. After taking A, there is no producer during `poll(...)`, so the result is `null`.

When the condition is met, timed forms can still execute immediately: C is inserted and taken without spending a full second. A timeout is an upper bound on waiting for the condition, not a requirement to sleep for that exact duration.

In the zero-timeout calls, the queue is still checked against its current state: D is inserted when space is available, then taken when data is available. Once empty, the next `poll` returns `null`. Do not use 0 to mean “wait forever”.

Elapsed milliseconds are not printed to stdout because actual timing depends on the execution environment. What is verified here is the outcome branch and remaining data, not an exact timing number.

### 4.3. TimeUnit and Precision Limits

`TimeUnit.MILLISECONDS` and `TimeUnit.SECONDS` give the same number 50 completely different meanings. Writing the unit explicitly at the call site helps avoid confusing seconds with milliseconds.

The nanosecond unit does not promise that the operating system or scheduler can wake a thread with nanosecond precision. See [TimeUnit semantics and resolution limits](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html).

A woken thread must still be scheduled onto a CPU and complete the necessary coordination before the caller observes the result. Therefore, do not treat a timeout as a hard real-time guarantee that the method will return before a specific wall-clock deadline.

### 4.4. A Timeout Does Not Undo a Successful Operation

If `offer` returns `true`, the work has been added; the caller later realizing the original request has expired does not automatically remove the work from the queue.

If `poll` returns an element, that element has already been removed. An error occurring in a later processing step does not automatically put it back in place.

Thus you must define at which layer “expiration” applies:

- Exceeding the allowed time to wait for space in the queue.
- Exceeding the allowed time to wait to take a job.
- The job sitting in the queue for too long.
- The entire request having to finish before a business deadline.

These are separate policies. Merely passing a timeout to `offer` does not solve the other three.

## 5. InterruptedException and Preserving the Stop Signal

### 5.1. Interruption Is a Control-Flow Branch

`put`, `take`, and the timed `offer`/`poll` forms declare `InterruptedException`. A waiting call can be asked to stop waiting via `interrupt()`.

Interruption is not `Thread.stop`: it does not forcibly terminate all code executing on a thread. The code receiving the signal must react appropriately.

There are two common ways to handle it:

1. The method can report the error to its caller: propagate `InterruptedException`.
2. At a boundary such as `Runnable.run`, where checked exceptions cannot be propagated upward: restore the interrupt status, then terminate the task according to policy.

Restoring the flag and then continuing to call the waiting operation in an infinite loop usually does not represent a sensible stop decision. The task must decide whether to exit, clean up resources, or report a result.

### 5.2. Program Interrupting a Consumer

File `InterruptQueueDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class InterruptQueueDemo {
    public static void main(String[] args) throws Exception {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
        var started = new CountDownLatch(1);
        var outcome = new AtomicReference<String>();

        Thread consumer = new Thread(() -> {
            started.countDown();
            try {
                queue.take();
                outcome.set("unexpected item");
            } catch (InterruptedException ex) {
                boolean cleared = !Thread.currentThread().isInterrupted();
                Thread.currentThread().interrupt();
                outcome.set("failure=" + ex.getClass().getSimpleName()
                        + ", cleared=" + cleared
                        + ", restored=" + Thread.currentThread().isInterrupted());
            }
        }, "queue-consumer");

        consumer.start();
        try {
            if (!started.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("consumer did not start");
            }
            consumer.interrupt();
            consumer.join(10_000);
            if (consumer.isAlive()) {
                throw new IllegalStateException("consumer did not stop");
            }
            System.out.println(outcome.get());
            System.out.println("queueEmpty=" + queue.isEmpty());
            System.out.println("consumerAlive=" + consumer.isAlive());
        } finally {
            consumer.interrupt();
            consumer.join(10_000);
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 InterruptQueueDemo.java
java InterruptQueueDemo
```

Stdout:

```text
failure=InterruptedException, cleared=true, restored=true
queueEmpty=true
consumerAlive=false
```

No producer puts an element into the queue. The main thread requests interruption after the `started` latch. The signal may arrive before `take` actually blocks or while it is waiting; both cases fit the experiment.

In this `ArrayBlockingQueue` example, when the exception is caught, the interrupt flag has already been cleared. The task checks that, calls `interrupt()` on itself to restore the flag, records the result, and exits.

Working with `InterruptedException` may also involve checking and clearing the status via `Thread.interrupted()`. See [Java 17 InterruptedException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InterruptedException.html).

`isInterrupted()` only reads the status; `Thread.interrupted()` reads and clears the current thread's status. Do not call the latter just for logging if you do not intend to consume the signal. See [Thread interrupt status check contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#interrupted()).

### 5.3. Anti-Pattern: Turning Interruption into “No Data Yet”

The following snippet illustrates incorrect code, not a standalone program:

```java
// WRONG: loses the stop signal and keeps waiting indefinitely.
while (true) {
    try {
        handle(queue.take());
    } catch (InterruptedException ex) {
        System.out.println("try again");
    }
}
```

If the thread's owner wants to stop the task, the loop swallows the signal and goes right back to waiting. A log message is no substitute for implementing a cancellation policy.

A handling pattern at a task boundary can look like:

```java
// Illustrative code inside the body of a Runnable, not a standalone program.
try {
    while (!Thread.currentThread().isInterrupted()) {
        handle(queue.take());
    }
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
}
```

In this pattern, the `catch` block sits outside the loop so the task exits the processing loop when the wait operation is interrupted. The `handle` function and resource cleanup must still follow the application design; an interrupt signal does not automatically roll back partially completed work.

### 5.4. Shutting Down an Executor Is Different from Closing a Queue

Calling `shutdown()` on an `ExecutorService` does not automatically insert a message into the application's queue and does not automatically inform a waiting `take()` loop that the data source is exhausted.

`shutdownNow()` attempts to prevent unstarted tasks from running and stop running tasks, typically via interruption; it does not guarantee every piece of code will stop if that code does not cooperate. See [ExecutorService lifecycle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html).

In the demo programs, the `finally` block uses `shutdownNow()` to request cleanup of remaining tasks if the experiment fails. That is not a protocol for draining and finishing all work in a real system.

## 6. Capacity, Backpressure, and Progress Guarantees

### 6.1. A Queue Bound Only Works When Paired with the Right Policy

If producers are faster than consumers, pending work grows. A bounded queue forces the application to state what happens when full:

| Choice | Consequence to accept |
|---|---|
| `put` | Producer may have to wait until space opens or it is interrupted |
| `offer` | Producer immediately receives the failure result under the capacity condition |
| Timed `offer` | Producer spends only a bounded wait for this insertion |
| Redirect data elsewhere on failure | Requires a capacity and error policy for the alternative destination |

Slowing down the producer when the consumer cannot keep up is commonly called backpressure. A bounded queue provides a point to apply that policy; it does not decide for the application whether to drop, retry, fail fast, or persist durably.

If `offer` returns `false` and the caller ignores it, data may be silently lost. If the caller retries forever with a fresh timeout each time, the overall wait bound can disappear. If every failed job is moved into an unbounded list, the capacity problem is merely relocated.

### 6.2. Do Not Assume Every Queue Has a Small Bound

`LinkedBlockingQueue` lets you specify a capacity. If you use the no-arg constructor, the default bound is `Integer.MAX_VALUE`, which is not a small bound that regulates real-world load. See [LinkedBlockingQueue constructors and capacity](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html).

Memory can be exhausted long before hitting a huge count limit. Each element's size, the data it references, and the number of in-flight jobs must all be factored in when choosing capacity.

Do not assume `put` will create useful backpressure just because a variable has type `BlockingQueue`. You must inspect the concrete implementation and how the instance is constructed.

### 6.3. remainingCapacity Does Not Reserve a Slot

The illustrative snippet below does not guarantee the insertion will succeed immediately:

```java
// Illustrative code with a gap between check and action.
if (queue.remainingCapacity() > 0) {
    queue.put(job);
}
```

After this side sees available space, another thread may take that slot. `put` can still end up waiting. Similarly, checking `isEmpty()` before calling `take()` does not guarantee the retrieval will not block.

If you want to try without waiting for the condition, use `offer` or `poll` directly and handle the result. If you want bounded waiting, use the timed forms. Pre-checking does not replace the policy of the actual operation.

`size` and `remainingCapacity` remain useful for observing load, but they are not reservation tickets for a subsequent step.

### 6.4. Avoid Holding Resources Needed by the Side That Changes the Condition

A design scenario that cannot make progress:

```text
Producer holds lock L → calls put on a full queue → waits
Consumer needs lock L → before it can reach the take step
```

The queue cannot release an external lock held by application code on its own. You must narrow the resource-holding scope or change the coordination mechanism.

Another scenario is sharing the same small thread pool across multiple producer and consumer tasks. If all threads are occupied by waiting `put` calls while consumer tasks have not yet run, no thread is left to free space.

You do not need to avoid every blocking call; you must be explicit about who can still change the condition while that call waits.

### 6.5. Element FIFO Is Different from Thread Fairness

`ArrayBlockingQueue` uses FIFO for elements. Its constructor with a fairness flag also controls the order in which waiting threads are granted access according to the class's policy.

These are two separate concerns: the order in which jobs are taken does not dictate which thread runs first, and a thread that takes a job earlier may finish processing after another thread. Fairness also has overhead; do not enable the flag merely because the name sounds universally better.

## 7. Termination Protocol: Stop Signals Must Be Designed

### 7.1. BlockingQueue Does Not Know When Producers Are Done

A `poll` returning `null` only says that retrieval received no data within the wait time. It does not prove no producer will add data later.

The interface has no general close operation to signal permanent end of data. A common approach is a dedicated stop message recognized by the application.

Do not use a string that could collide with real data such as `"STOP"` if the data domain allows that string. Do not use `null`. An explicit message type cleanly separates work items from the termination signal.

### 7.2. Single-Producer, Single-Consumer Program

File `ProducerConsumerStopDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ProducerConsumerStopDemo {
    sealed interface Message permits Data, Stop {}
    record Data(int value) implements Message {}
    enum Stop implements Message { INSTANCE }
    record Totals(int count, int sum) {}

    static Totals consume(BlockingQueue<Message> queue)
            throws InterruptedException {
        int count = 0;
        int sum = 0;
        while (true) {
            Message message = queue.take();
            if (message == Stop.INSTANCE) {
                return new Totals(count, sum);
            }
            Data data = (Data) message;
            count++;
            sum += data.value();
        }
    }

    public static void main(String[] args) throws Exception {
        BlockingQueue<Message> queue = new ArrayBlockingQueue<>(2);
        var pool = Executors.newSingleThreadExecutor();

        try {
            var result = pool.submit(() -> consume(queue));
            queue.put(new Data(10));
            queue.put(new Data(20));
            queue.put(new Data(30));
            queue.put(Stop.INSTANCE);

            Totals totals = result.get(10, TimeUnit.SECONDS);
            System.out.println("processed=" + totals.count());
            System.out.println("sum=" + totals.sum());
            System.out.println("queueEmpty=" + queue.isEmpty());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ProducerConsumerStopDemo.java
java ProducerConsumerStopDemo
```

Stdout:

```text
processed=3
sum=60
queueEmpty=true
```

`Message` has only two forms: `Data` holding the number to process, and `Stop.INSTANCE` representing termination. With a single consumer, the producer inserts three data items followed by one stop signal.

Because the example uses a FIFO `ArrayBlockingQueue` and has no other producers, the consumer sees the three data items before seeing the stop signal. It returns the totals instead of calling `take` again.

The capacity of 2 is smaller than the total number of messages. The program still makes progress because the consumer runs independently, taking items and freeing space while the producer keeps inserting.

This is an experiment with a well-defined happy path. In a real application, if the consumer fails, the producer could remain stuck in `put`; error reporting, cancellation, and handling of incomplete work are needed.

### 7.3. Multiple Consumers Need Enough Signals or a Different Protocol

If there are three consumers and each exits upon receiving a stop signal, one signal only wakes and terminates the single consumer that receives it. The other two can remain waiting.

A common protocol is to send one signal per consumer, but only after ensuring all producers have finished and will add no more data. The consumer count, insertion order, and error handling must be clearly known.

Do not let one producer send a stop signal while other producers are still active. Data inserted after the signal could be left behind if consumers have already exited.

The “consumer takes the signal and puts it back for another” approach also introduces extra conditions: the re-insertion step can block, or the task can be interrupted or stopped mid-way. Do not assume it is a coordination-free solution.

### 7.4. Draining All Work vs. Stopping Immediately Are Two Different Requirements

If you want to process all accepted data, you need a shutdown order that allows consumers to keep working until the source closes by protocol.

If you want to stop immediately, you must decide what happens to data still in the queue and work currently in progress: discard, persist, hand off, or report as incomplete. Sending a signal does not automatically reclaim work that has already been taken.

A `volatile boolean running` flag also does not wake a thread waiting inside `take()`. Some action must cause that call to exit or switch to an appropriately bounded wait.

Do not solve waking by spinning in a loop checking the flag and throwing away the queue's waiting capability.

## 8. Data Handoff and Visibility Between Threads

Actions by a producer prior to placing an object into a `BlockingQueue` have a happens-before relationship with actions subsequent to the access or removal of that element from the queue in another thread. This allows the queue to serve as a data handoff point between threads. See [BlockingQueue memory-consistency guarantees](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

Reasoning example: the producer finishes initializing the job before calling `put`; the consumer calls `take` to receive that job and then reads the initialized data. You do not need to add your own “initialized” flag just to duplicate the handoff point the queue already provides.

Keep the boundaries clear:

- This guarantee applies to the object transferred through the queue.
- The queue does not make a deep copy of the object.
- If the producer keeps mutating the object after inserting it, those mutations are not automatically synchronized with subsequent reads on the consumer side.
- The queue does not automatically make an `ArrayList` or a mutable nested structure safe for concurrent sharing.

In `ProducerConsumerStopDemo`, the data items are simple records with numeric fields that are not mutated after creation. The producer hands off the message and does not touch that message's data afterward.

A clean convention is for the producer to finish building the data before sending; the receiver owns the work item after taking it, or the data is kept immutable if multiple parties must read it. When mutable state must be shared, design synchronization for that state itself.

A successful take also only means the element has been transferred from the queue to the receiver. For the sender to know processing has completed, you need a result channel, acknowledgment, or another mechanism. Do not attach that meaning to `put` returning.

## 9. Multi-Step Deadlines and Boundaries to Keep Clear

### 9.1. Do Not Reset the Full Budget on Every Retry

Suppose a request is allowed a total of 300 milliseconds for the waiting phase. If each failed `offer` is retried with another 300 milliseconds, the total wait time can far exceed the original intent.

You must pick a start mark and subtract elapsed time before deciding to wait again. `System.nanoTime()` is used to measure elapsed intervals within the same JVM, not as a wall-clock timestamp for recording date/time or comparing across machines. See [Java 17 System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()).

The method below is an illustrative integration snippet, not a standalone program. Place it in a class that imports `BlockingQueue` and `TimeUnit`; `startedAt` is obtained from `System.nanoTime()` at the start of the budgeted phase:

```java
static boolean offerWithinBudget(
        BlockingQueue<String> queue,
        String item,
        long startedAt,
        long budgetNanos) throws InterruptedException {

    long elapsed = System.nanoTime() - startedAt;
    long remaining = budgetNanos - elapsed;
    if (remaining <= 0) {
        return false;
    }
    return queue.offer(item, remaining, TimeUnit.NANOSECONDS);
}
```

This snippet chooses the policy of not attempting to insert once the budget is exhausted, even if space currently exists. That is a decision of the integration helper, distinct from an `offer` call with timeout 0 which still probes the current condition.

It assumes a non-negative budget of reasonable length and measurements taken within the same JVM. Do not add to a wall-clock date/time timestamp as a substitute for interval measurement.

### 9.2. The Queue Operation Budget Is Not the Deadline for the Whole Job

Time after receiving an element can still include waiting in the queue, waiting on other resources, performing I/O, and processing results. To control end-to-end time, each stage must receive the remaining budget or check the same deadline according to the application model.

Even without resetting the budget, the JVM and scheduler are not turned into a hard real-time system. A timeout mechanism helps the application stop waiting by policy; it does not guarantee that every external resource or already-started task stops at the exact moment.

### 9.3. Avoid Using a Single Timeout to Conclude the Source Is Closed

A consumer using `poll(1, SECONDS)` can periodically check stop requests, log status, or perform maintenance work. If it receives `null`, it must decide the next step according to the overall protocol.

Stopping just because one poll received no data can break a bursty producer source. Conversely, looping forever after the source has genuinely finished leaves unnecessary tasks running.

Therefore, timeouts and source completion conditions must be modeled separately. The end-of-source signal should come from a party with enough information to confirm it, rather than being inferred from current throughput.

### 9.4. Observe Each Stage Separately

When the system is slow, distinguish:

- Time spent waiting for space to be accepted.
- Time the job sits in the queue.
- Processing time after being taken.
- Number of rejected or timed-out insertions.
- Number of interruptions and the reason for stop requests.
- Number of jobs in flight, separate from the count still in the queue.

An empty queue does not prove all work is complete: consumers may have taken everything and still be working. A non-full queue also does not prove the system is not overloaded at another layer.

The experiments in this lesson verify operation contracts and controlled coordination. They do not replace load testing the application or prove that every possible execution schedule is problem-free.

## 10. Common Mistakes and Practice

### 10.1. Identifying Bugs from the Chosen Policy

| Usage pattern | Problem | What to consider |
|---|---|---|
| `put` on a thread not allowed to wait long | Thread can block when full | Use a rejection or bounded-wait policy |
| Ignoring `offer` result | Cannot tell whether work was accepted | Handle the `false` branch explicitly |
| Catching interrupt and continuing loop | Can lose the stop request | Propagate or restore flag and exit per policy |
| Using `null` as a stop message | Invalid for BlockingQueue | Use a dedicated message type or object |
| Seeing `poll` return `null` and assuming work is done | Source may still add more later | Use a source termination protocol |
| Checking `remainingCapacity` and assuming a reserved slot | Another thread can take the slot first | Rely on the actual operation's result |
| Resetting the full timeout on retry | Total time is no longer bounded as intended | Compute remaining budget |

The directions above are decisions about application behavior. No single method fits every kind of workload or every requirement for data loss, latency, and system shutdown.

### Exercise 1: Choose the Right Method for the Requirement

A queue has bounded capacity. For each requirement below, choose the method and handling branch:

1. If there is no space yet, return immediately to the caller so it can report overload.
2. Allow waiting for space up to a specific duration.
3. A background task is allowed to wait for incoming data but must be stoppable.
4. Only want to inspect the head element without removing it.

Explanation guide: use `offer`, timed `offer`, `take` with an interruption or termination policy, and `peek`. Clearly state the return value or exception for each branch.

### Exercise 2: What Happens When Full and Empty?

With capacity 1, insert A, attempt to insert B with a timed `offer` while there is no consumer, take A, then call timed `poll` while there is no producer.

Explain why the B insertion receives `false`, the later poll receives `null`, and why neither queue method throws `TimeoutException`.

Then add the case where the thread is interrupted while waiting. This branch must be described separately, without renaming it to a timeout.

### Exercise 3: Find Where Progress Stops

A thread pool has two threads. Both producer tasks are currently calling `put` on a full queue; the consumer task is queued in the same pool but has not run yet.

Point out who can free space in that state. Does increasing the capacity reliably fix the dependency relationship?

Explanation guide: increasing capacity may delay the situation, but it does not replace a design that ensures the consumer can run. Examine thread layout, waiting policy, and task dependencies.

### Exercise 4: Stopping Multiple Consumers

There are two producers and three consumers. One producer has just finished and wants to send a stop message.

- Does it already have enough information that the source is out of data?
- If each consumer exits when taking a signal, how must the number of signals be organized?
- If one consumer fails while the queue is full, where can the signal sender get stuck?

Explanation guide: coordinate completion across all producers first, then design termination for all consumers. An error and cancellation path is required, not only the happy path with stop messages.

### Exercise 5: Handoff and Processing Completion

A producer creates an object, puts it into the queue, and then continues modifying its fields. A consumer takes the object and concurrently reads those fields.

Why is the thread-safety of the queue not enough to conclude that subsequent writes and reads are safe? If the sender wants to know when processing is done, what additional information does it need?

Explanation guide: the handoff point guarantees visibility for work done before sending; it does not synchronize subsequent modifications. You need immutable data, ownership transfer, or separate synchronization, along with an acknowledgment channel if processing completion must be tracked.

### Questions to Answer Before Using Waiting Operations

1. Is the caller allowed to tie up its thread while waiting?
2. Who can change the waiting condition?
3. Is capacity actually bounded according to operational goals?
4. How are the timeout branch and the interruption branch handled?
5. By what protocol does the source terminate, and who is authorized to confirm termination?
6. Is a lock or resource being held that the other side needs?
7. Is success currently defined as queued, taken, or finished processing?
8. Will the object continue to be modified by multiple sides after handoff?

Using `put`, `take`, and timed forms properly requires both the right method choice and a clear answer on progress, data ownership, and task lifecycle.
