# Exchanger<T> Exchanging Data Between Two Threads in Java

`Exchanger<T>` is a **synchronization rendezvous point** in `java.util.concurrent`: one thread brings an object to `exchange()`, and another thread also arrives at that point with an object of its own; when **a pair is successfully matched**, each side receives **the other side's object** and continues. If only one side arrives, that side **waits** until a partner arrives, it is interrupted, or a timeout expires if using the timed overload.

Example:

```text
Thread A                         Thread B
--------                         --------
has "APPLE"                      has "BANANA"
    |                                |
    +--> exchanger.exchange("APPLE") |
                                     +--> exchanger.exchange("BANANA")
                   MEETING POINT
                  /             \
A receives "BANANA" <-       -> B receives "APPLE"
    |                                |
  continues                        continues
```

This is **not a queue that accumulates multiple items**, not a broadcast of one item to every consumer, and not "send and forget". Both sides must participate in **the same successful exchange** so that both receive the partner's object. This tool is well suited when **two stages of a pipeline need to hand off two buffers to each other**: the producer transfers a full buffer and receives an empty buffer back from the consumer, helping reuse memory instead of allocating continuously.

This Knowledge article belongs to **Synchronizers** in **general Java concurrency**. The examples use Java SE 17+ and do not rely on the Spring Framework.

## 1. Nature of `Exchanger<T>`

`Exchanger<V>` is a synchronization class, not a `Collection`, `Queue`, or `Future`.

- **Bidirectional:** two threads exchange, each passing in a value and receiving the value from the other.
- **Pairing:** if multiple threads call on the same `Exchanger`, the runtime can match them into **pairs**; there is no fixed partner identity per class.
- **Synchronized at the exchange point:** for a successful pair, each side only proceeds after the exchange has been coordinated with the other side.
- **Blocking:** if there is no partner, the untimed `exchange()` can wait forever; the timed overload allows bounding the wait time.
- **Interruptible:** the overloads declare `InterruptedException`; calling code must propagate or handle cancellation.
- **No history storage:** there is no `peek()`, `size()`, `take()`, or `drain()` API. After an exchange, the object belongs to the receiving side's subsequent processing flow according to the application protocol.
- **Does not create threads itself:** the application must still use `Thread`, `ExecutorService`, or an appropriate execution mechanism.

The generic name `T` or `V` is just a type parameter name. `Exchanger<String>` exchanges references to `String`; `Exchanger<List<Integer>>` exchanges references to lists. It does not clone or serialize objects.

## 2. API Signatures and Imports

Use:

```java
import java.util.concurrent.Exchanger;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
```

Main members in Java SE 17:

```java
public Exchanger();

public V exchange(V x) throws InterruptedException;

public V exchange(V x, long timeout, TimeUnit unit)
        throws InterruptedException, TimeoutException;
```

These are **illustrative signatures**, not standalone runnable code; `V` is the class type parameter.

| Method | Behavior |
| --- | --- |
| `new Exchanger<T>()` | Creates an exchange point; no threads are waiting yet |
| `exchange(myObject)` | Waits for another thread to arrive to swap; no time limit |
| `exchange(myObject, timeout, unit)` | Waits at most the timeout duration for a partner; may throw `TimeoutException` |
| Return value | The object that the **partner thread** provided in the successful exchange |

`Exchanger` does not provide separate `send` and `receive` methods. **Both threads call the same method** to both send and receive. Therefore, the right mental model is "swapping" rather than "pushing an item into a queue".

## 3. Sequence of a Successful Exchange

Suppose A and B share the exact same `Exchanger<Message>` instance:

1. A creates `messageA` and calls `exchange(messageA)`.
2. If there is no partner yet, A waits at the exchange point.
3. B creates `messageB` and calls `exchange(messageB)` on **that same instance**.
4. An A/B pair is matched; references are swapped per the contract.
5. A receives the object B passed in, and B receives the object A passed in.
6. Both threads continue independently, possibly at different times depending on the scheduler.

There is no guarantee that A runs before B or vice versa. Nor is there a guarantee that both wake up **at the exact same nanosecond**. The swap result is what is guaranteed; log order and wake-up timing are not part of the contract.

Conceptual state diagram:

```text
A arrives --------\
                   >--- successful pairing ---> both return peer item
B arrives --------/

A arrives --- waits --- timeout -------> TimeoutException
A arrives --- waits --- interrupt -----> InterruptedException
A arrives --- waits --- forever? ------> possible without partner or cancellation
```

The timeout/interrupt paths are not a successful item transfer transaction. The application must decide how to handle the value still held by the caller and whether to retry or terminate.

## 4. Java 17+ Example: Two Threads Exchanging Strings

Save as `BasicExchangerDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Exchanger;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class BasicExchangerDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Exchanger<String> exchanger = new Exchanger<>();
        CountDownLatch start = new CountDownLatch(1);
        AtomicReference<String> aGot = new AtomicReference<>();
        AtomicReference<String> bGot = new AtomicReference<>();

        Thread a = new Thread(() -> {
            try {
                start.await();
                aGot.set(exchanger.exchange(
                        "APPLE", 5, TimeUnit.SECONDS));
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (java.util.concurrent.TimeoutException e) {
                throw new IllegalStateException(e);
            }
        }, "A");

        Thread b = new Thread(() -> {
            try {
                start.await();
                bGot.set(exchanger.exchange(
                        "BANANA", 5, TimeUnit.SECONDS));
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (java.util.concurrent.TimeoutException e) {
                throw new IllegalStateException(e);
            }
        }, "B");

        a.start();
        b.start();
        start.countDown();

        a.join();
        b.join();

        System.out.println("A received: " + aGot.get());
        System.out.println("B received: " + bGot.get());
    }
}
```

Run on JDK 17+:

```bash
javac BasicExchangerDemo.java
java BasicExchangerDemo
```

**Stdout on the success path (both threads meet within the deadline):**

```text
A received: BANANA
B received: APPLE
```

Why not print from inside the workers? If A and B both call `System.out.println`, the order of the two lines depends on thread scheduling. The code records results into `AtomicReference`, uses `Thread.join()` to wait for both to finish, and then `main` prints in a fixed order.

`CountDownLatch` lets both threads start close together, but does not guarantee *the exact arrival time at exchange*. The 5-second timeout is a bound to avoid hanging for a long time if the system fails; in an environment paused longer than the deadline, the demo may take the timeout branch instead of the success stdout.

**Testing note:** this demo uses simple exception handling to highlight the happy path; production code should collect errors from both threads via `Future`, a completion result, or a managed handler rather than only throwing an unchecked exception on a worker.

## 5. What Happens When There Is No Partner?

With:

```java
String peer = exchanger.exchange("HELLO");
```

if only a single thread ever calls `exchange` on that instance, the thread can **wait indefinitely**. This commonly happens when:

- The partner thread was never started.
- The partner thread terminated due to an exception.
- The two sides use **two different `Exchanger` instances**.
- One side calls a second time while the other side only called once and exited.
- One side is stuck on a lock/I/O before reaching `exchange`.
- The caller assumes `exchange` is just an `offer` into a queue and does not need a receiver.

Do not use `Thread.sleep` to guess that "the partner must be ready". If indefinite waiting is unacceptable, use the timed overload and design a clear failure/interrupt handling protocol.

## 6. The Timed Overload

Signature:

```java
T peer = exchanger.exchange(
        myValue, timeout, TimeUnit.MILLISECONDS);
```

This is an illustrative snippet with variables of type `T`/`myValue` already defined in the method.

Possible outcomes:

- A partner is matched within the deadline: returns the partner's object.
- Waiting exceeds the deadline without a match: throws `TimeoutException`.
- The thread is interrupted at entry or while waiting: throws `InterruptedException`; the interrupt status is **cleared** when the exception is thrown per contract.
- If `timeout <= 0`, the call **does not wait** for a new partner to arrive. It can still match if another thread is already waiting; therefore, **do not** automatically assume every zero-timeout call throws `TimeoutException`.

A timeout on A is not a command to close the `Exchanger`, does not automatically interrupt B, and does not propagate failure to other threads. Each side needs a consistent policy for stopping or restarting the exchange loop.

## 7. Java 17+ Example: A Lone Thread Timing Out

Save as `ExchangerTimeoutDemo.java`:

```java
import java.util.concurrent.Exchanger;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class ExchangerTimeoutDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Exchanger<String> exchanger = new Exchanger<>();
        boolean timedOut = false;

        try {
            exchanger.exchange("ALONE", 30, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            timedOut = true;
        }

        System.out.println("Timed out: " + timedOut);
    }
}
```

```bash
javac ExchangerTimeoutDemo.java
java ExchangerTimeoutDemo
```

Exact stdout if `main` is not interrupted externally:

```text
Timed out: true
```

The program has no partner thread, so `exchange` cannot match. After the wait duration, the method throws `TimeoutException`; the variable becomes `true` and the application continues.

**A timeout does not mean the object `"ALONE"` was sent to a queue and lost.** It was never swapped. If the application wants to retry exchanging the same payload, it must determine whether a future partner will share the same session and whether there is a risk of mismatched rounds.

## 8. `InterruptedException` and Restoring the Interrupt Flag

`Exchanger.exchange` is an interruptible call. If the thread is interrupted while waiting, or has its interrupt status set on entry per contract, it throws `InterruptedException` and **clears the interrupt status**.

If the method allows `throws InterruptedException`, it is usually best to **propagate the exception** so the calling layer can execute its cancellation policy:

```java
static String swap(
        Exchanger<String> exchanger, String value)
        throws InterruptedException {
    return exchanger.exchange(value);
}
```

This is an illustrative method.

At a boundary where a checked exception cannot be added, such as `Runnable.run()`, the common pattern is:

```java
try {
    String received = exchanger.exchange(message);
    handle(received);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
```

This is an illustrative snippet with application-specific `message` and `handle`. **Restore and then stop work appropriately**, rather than just resetting the flag and looping `exchange` infinitely.

Do not use an empty catch:

```java
catch (InterruptedException ignored) {
    // Wrong: clears the cancellation signal and continues normally.
}
```

That can prevent the worker from stopping on executor shutdown/cancel, especially when the partner side has already disappeared.

## 9. Java 17+ Example: Interrupt While Waiting for a Partner

Save as `ExchangerInterruptDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Exchanger;
import java.util.concurrent.atomic.AtomicBoolean;

public class ExchangerInterruptDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Exchanger<String> exchanger = new Exchanger<>();
        CountDownLatch entered = new CountDownLatch(1);
        AtomicBoolean caught = new AtomicBoolean();
        AtomicBoolean clearedInCatch = new AtomicBoolean();
        AtomicBoolean restored = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            try {
                entered.countDown();
                exchanger.exchange("NEVER_MATCHED");
            } catch (InterruptedException e) {
                caught.set(true);
                clearedInCatch.set(
                        !Thread.currentThread().isInterrupted());
                Thread.currentThread().interrupt();
                restored.set(Thread.currentThread().isInterrupted());
            }
        }, "waiting-worker");

        worker.start();
        entered.await();

        // Without a partner, the worker only exits via interruption.
        worker.interrupt();
        worker.join();

        System.out.println("InterruptedException: " + caught.get());
        System.out.println("Flag cleared in catch: "
                + clearedInCatch.get());
        System.out.println("Flag restored: " + restored.get());
    }
}
```

```bash
javac ExchangerInterruptDemo.java
java ExchangerInterruptDemo
```

Exact stdout:

```text
InterruptedException: true
Flag cleared in catch: true
Flag restored: true
```

Why this result is reliable:

1. The worker signals `entered` right before calling `exchange`.
2. If `main` interrupts while the worker is already waiting, `exchange` throws. If the interrupt arrives **before** the worker actually enters exchange, the method still detects the interrupt flag at entry and throws.
3. There is no second thread, so no unexpected pairing occurs.
4. The catch block observes that the flag was cleared per the API, then calls `Thread.currentThread().interrupt()`.
5. `main` calls `join` to wait for the worker to finish before reading the `AtomicBoolean` values.
6. It does not rely on `worker.isInterrupted()` after the worker has terminated to prove restoration; the code measures it **directly inside the worker**.

Cooperative cancellation here belongs to **the waiting worker**. Calling `worker.interrupt()` does not mean every thread using the same exchanger is interrupted.

## 10. Consecutive Exchange Rounds

An `Exchanger` can be reused multiple times:

```text
Round 1:
A sends A1; B sends B1; A receives B1; B receives A1

Round 2:
A sends A2; B sends B2; A receives B2; B receives A2
```

If **exactly two threads** participate and both call in a consistent turn order, each call can match with the corresponding waiting call from the other side. There is no need to create `new Exchanger` for each round.

However, if one side skips a turn, retries uncoordinatedly, or a third thread appears, **a later rendezvous may no longer belong to the same logical round**. `Exchanger` does not carry a "sequence number" or verify that two payloads belong to the same session.

Solutions for multi-round protocols:

- Include a `roundId` or correlation ID in the payload.
- Specify that each side exchanges exactly once per round.
- On timeout/interrupt, clearly define whether to **cancel the whole session** or perform a synchronized retry.
- Do not silently resend if the other side may have already moved to the next round.
- If you need to match by arbitrary request ID, a single `Exchanger` is not the right structure; use a map/future/queue keyed by correlation key.

## 11. Java 17+ Example: Two Exchange Rounds with Deterministic Results

Save as `ExchangerRoundsDemo.java`:

```java
import java.util.concurrent.Exchanger;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class ExchangerRoundsDemo {
    public static void main(String[] args) throws InterruptedException {
        Exchanger<String> exchanger = new Exchanger<>();
        AtomicReference<String> aResults = new AtomicReference<>();
        AtomicReference<String> bResults = new AtomicReference<>();

        Thread a = new Thread(() -> {
            try {
                String first = exchanger.exchange(
                        "A1", 5, TimeUnit.SECONDS);
                String second = exchanger.exchange(
                        "A2", 5, TimeUnit.SECONDS);
                aResults.set(first + "," + second);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (java.util.concurrent.TimeoutException e) {
                throw new IllegalStateException(e);
            }
        });

        Thread b = new Thread(() -> {
            try {
                String first = exchanger.exchange(
                        "B1", 5, TimeUnit.SECONDS);
                String second = exchanger.exchange(
                        "B2", 5, TimeUnit.SECONDS);
                bResults.set(first + "," + second);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (java.util.concurrent.TimeoutException e) {
                throw new IllegalStateException(e);
            }
        });

        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("A got: " + aResults.get());
        System.out.println("B got: " + bResults.get());
    }
}
```

```bash
javac ExchangerRoundsDemo.java
java ExchangerRoundsDemo
```

Stdout when both threads coordinate successfully within the timeout:

```text
A got: B1,B2
B got: A1,A2
```

Only two threads share the instance, and each must complete round 1 before it can call round 2. There is no third thread interfering with pairing, so the results are deterministic per round. If the environment experiences a scheduler stall over 5 seconds or a worker fails, the error path must be handled by a real application.

## 12. Handing Over References, Not Copying Contents

When calling:

```java
List<Integer> received = exchanger.exchange(myBuffer);
```

the operation exchanges **references** to objects. It does not deep-copy the list, does not copy a byte array, and does not make the object immutable. If A sent an `ArrayList` to B, but A keeps its old reference and continues calling `add` while B reads, **a data race still exists**.

Follow the **ownership transfer** rule:

1. A owns buffer A before the exchange and is allowed to write to it.
2. A calls `exchange(bufferA)` and must not modify buffer A after handing it to the exchanger if the other side can access it.
3. When the exchange succeeds, A owns **the buffer received from B**; B owns buffer A.
4. B only reads/writes the received buffer according to the agreed protocol.
5. Old references must not be reused to mutate an object that has been handed over.

If multiple threads need concurrent access/ownership at the same time, use immutable data, snapshot copies, or separate synchronization. `Exchanger` is not a "lock" for all operations on the swapped object.

## 13. Java Memory Model: Happens-Before Across a Swap

The Java SE 17 Javadoc explicitly states the memory consistency effect:

> For each pair of threads that successfully exchange objects via an `Exchanger`, **actions prior to the `exchange()` in each thread happen-before those subsequent to a return from the corresponding `exchange()` in another thread**.

This is crucial when exchanging a **mutable buffer**:

```text
Thread A                               Thread B
--------                               --------
buffer.values[0] = 42
buffer.ready = true
    |
    |  Exchanger.exchange(buffer)
    +-------------------------------> receives buffer
                                        |
                                        v
                                  read buffer.ready
                                  read buffer.values[0]
```

If A finishes writing **before** the successful exchange and B reads the buffer after the exchange, the JMM provides the required visibility relationship across that exchange edge. You do not have to make every field in the buffer `volatile` just to publish writes made *prior to handover* under the protocol.

However:

- **Happens-before does not lock the object after the exchange.** If A continues modifying the buffer after handing it to B, race conditions remain.
- This relationship applies to **a successfully paired exchange**; a timeout cannot be used as proof that the peer received the data.
- Data written **after** A has performed the exchange does not automatically become visible "before B reads".
- If the buffer holds references to objects that a third thread continues to mutate, synchronization for those objects must be analyzed separately.
- Do not infer a "global happens-before" among all threads that ever used the same exchanger across different rounds.

## 14. Java 17+ Example: Publishing a Mutable Payload via Exchange

Save as `ExchangerVisibilityDemo.java`:

```java
import java.util.concurrent.Exchanger;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ExchangerVisibilityDemo {
    static final class Payload {
        int number;  // volatile is not needed for publication in this example
        String text;
    }

    public static void main(String[] args) throws InterruptedException {
        Exchanger<Payload> exchanger = new Exchanger<>();
        AtomicInteger observed = new AtomicInteger(-1);

        Thread producer = new Thread(() -> {
            Payload payload = new Payload();
            payload.number = 42;
            payload.text = "ready";

            try {
                exchanger.exchange(payload, 5, TimeUnit.SECONDS);
                // Do not touch payload again after handing it over.
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (java.util.concurrent.TimeoutException e) {
                throw new IllegalStateException(e);
            }
        });

        Thread consumer = new Thread(() -> {
            try {
                Payload received = exchanger.exchange(
                        new Payload(), 5, TimeUnit.SECONDS);

                if ("ready".equals(received.text)) {
                    observed.set(received.number);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (java.util.concurrent.TimeoutException e) {
                throw new IllegalStateException(e);
            }
        });

        producer.start();
        consumer.start();
        producer.join();
        consumer.join();

        System.out.println("Observed: " + observed.get());
    }
}
```

```bash
javac ExchangerVisibilityDemo.java
java ExchangerVisibilityDemo
```

Stdout if the exchange succeeds:

```text
Observed: 42
```

Reading `number` and `text` does not create a data race in this demo configuration: the producer writes before handover, the consumer reads after receiving, and the producer never mutates the object again. `AtomicInteger` is used here as a result channel for `main`. `main` calls `join` to ensure both threads have finished their work.

If you add `producerPayload.number++` **after the exchange** in the producer while the consumer is still reading, that reasoning no longer holds: the object is now shared for mutation without proper ownership/synchronization.

## 15. Classic Use Case: Producer Swaps a Full Buffer for an Empty Buffer

A two-stage pipeline:

- **Producer:** fills a buffer from input data.
- **Consumer:** processes the full buffer, empties it, and swaps it back.

`Exchanger<Buffer>` lets both sides hand off in pairs:

```text
Producer                              Consumer
--------                              --------
buffer P = empty                      buffer C = empty
fill P
  |                                      |
  +---------- exchange(P) ---------------+ exchange(C)
  |                                      |
gets C = empty                          gets P = full
fill C                                  process P; clear P
  |                                      |
  +---------- exchange(C) ---------------+ exchange(P)
  |                                      |
gets P = empty                          gets C = full
...
```

Benefits:

1. Each side has **its own dedicated buffer** between swaps.
2. No need to allocate a new buffer per batch if reused properly.
3. The producer gets natural **backpressure** while waiting for the consumer to be ready to swap buffers.
4. The consumer never reads a buffer currently being modified by the producer, **provided the ownership protocol is maintained**.
5. No need for a shared mutable `ArrayList` with two threads continuously adding/removing on the same object.

Drawback: the two stages are **paced together**. If the consumer is very slow or fails, the producer may wait a long time. It is not a queue that lets the producer push 100 batches and move on.

## 16. Java 17+ Example: Producer–Consumer Swapping Two `ArrayList`s

Save as `ExchangerBufferDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Exchanger;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class ExchangerBufferDemo {
    public static void main(String[] args) throws InterruptedException {
        Exchanger<List<Integer>> exchanger = new Exchanger<>();
        AtomicReference<List<Integer>> result = new AtomicReference<>();

        Thread producer = new Thread(() -> {
            List<Integer> myBuffer = new ArrayList<>();
            try {
                for (int n = 1; n <= 3; n++) {
                    myBuffer.add(n);

                    // Send the buffer containing an item, receive an empty buffer from the consumer.
                    myBuffer = exchanger.exchange(
                            myBuffer, 5, TimeUnit.SECONDS);

                    // This is the buffer just handed over by the peer; it is empty
                    // according to this example's protocol.
                    myBuffer.clear();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (java.util.concurrent.TimeoutException e) {
                throw new IllegalStateException(e);
            }
        }, "producer");

        Thread consumer = new Thread(() -> {
            List<Integer> myBuffer = new ArrayList<>();
            List<Integer> collected = new ArrayList<>();

            try {
                for (int round = 0; round < 3; round++) {
                    // Send an empty buffer, receive a full buffer.
                    myBuffer = exchanger.exchange(
                            myBuffer, 5, TimeUnit.SECONDS);

                    collected.addAll(myBuffer);
                    myBuffer.clear();
                }
                result.set(List.copyOf(collected));
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (java.util.concurrent.TimeoutException e) {
                throw new IllegalStateException(e);
            }
        }, "consumer");

        producer.start();
        consumer.start();
        producer.join();
        consumer.join();

        System.out.println("Consumed: " + result.get());
    }
}
```

```bash
javac ExchangerBufferDemo.java
java ExchangerBufferDemo
```

Stdout if all three rounds succeed:

```text
Consumed: [1, 2, 3]
```

**Data and ownership proof:**

1. Both sides initialize two separate `ArrayList` instances.
2. The producer adds one number to **the buffer it currently owns**, then swaps with the consumer.
3. The consumer receives the buffer containing that number, copies it into `collected`, and calls `clear()` before the next exchange.
4. The producer receives the buffer the consumer passed in and prepares to fill the next number.
5. Each round uses one swap on both sides, so the order of numbers in `collected` is 1, 2, 3 regardless of scheduler variations.
6. `List.copyOf` creates a result snapshot that prevents structural modification after the consumer finishes.
7. `main` uses `join` to wait for both workers and read the result.

**Production usage conditions:** on the timeout/interrupt branches, you must define a policy for which buffer is owned by which side, what cleanup the workers still need to do, and whether to stop the entire pipeline. This example focuses on the normal path and simple error recording. Do not use a `while(true)` loop without a deadline with `Exchanger` if a peer can die.

## 17. Backpressure Exists, But It Is Not a Bounded Queue

If the producer can generate 100 buffers in 1 second while the consumer only processes 1 buffer/second, using `Exchanger` forces the producer to wait for the consumer on every round. This limits the number of "in-flight" buffers under the **two-buffer protocol**.

However, it is not equivalent to `ArrayBlockingQueue<>(2)`:

- `BlockingQueue` has **storage slots** for items via the `put`/`take` API.
- `Exchanger` is a **rendezvous**: each thread must both provide an item and receive an item.
- A queue supports one-way flow where the producer sends items and the consumer receives them; `Exchanger` supports two-way swapping at the same synchronization point.
- A queue can have multiple producers/consumers and explicit capacity policies; `Exchanger` pairs waiting callers and does not manage a list of queued items.
- If you want the producer to send without needing the consumer to have its own item to trade, a queue is usually easier to model.
- If you need to send while also returning a reusable buffer, `Exchanger` can reduce copying/allocation and clarify ownership.

Choose the tool based on the **data transfer protocol**, not merely because both can block.

## 18. `Exchanger` vs. `SynchronousQueue`

The Javadoc describes `Exchanger` as a **bidirectional** variant of `SynchronousQueue`.

| Criterion | `Exchanger<T>` | `SynchronousQueue<T>` |
| --- | --- | --- |
| Primary methods | `exchange(item)` | `put(item)` / `take()` |
| Data direction | Both threads send and receive in one call | One thread puts, one thread takes |
| Synchronization pair | Two callers of `exchange` are paired | Producer and consumer rendezvous |
| Stores backlog? | No | No, zero-capacity queue |
| Returns partner's object? | Yes | Producer `put` does not receive a return payload from consumer |
| Timeout/interrupt support? | Yes | Yes, on the appropriate overloads |
| Suitable for multi-client request–response? | Only when pairing/round protocol is controlled | Usually needs correlation/future/queue mechanisms |

Both are synchronization tools; neither provides durability or guarantees processing by a remote service.

If you only want a **one-way handoff**, `SynchronousQueue` usually makes the contract clearer. If you want a **two-way buffer swap**, `Exchanger` is the direct choice.

## 19. `Exchanger` vs. `CyclicBarrier`, `CountDownLatch`, `Phaser`

These synchronizers differ in purpose:

- **`CountDownLatch`:** one or more threads wait until a count reaches 0. Does not swap data; cannot be reset.
- **`CyclicBarrier`:** N parties wait for each other at a barrier point; can have a barrier action. Does not exchange payloads two-way by default.
- **`Phaser`:** manages multiple phases and dynamic registration/deregistration of parties. Suitable when the number of participants can change.
- **`Exchanger`:** **pairs two threads** and exchanges objects at the meeting point; does not wait for N participants in a collective barrier.
- **`Semaphore`:** limits the number of permits; does not directly swap two objects.

If you want **three threads to meet together and then proceed**, `CyclicBarrier(3)` or `Phaser` is usually more appropriate than `Exchanger`. `Exchanger` may pair two of the three threads and leave the third waiting, causing a hang if no fourth thread arrives.

## 20. More Than Two Threads Using the Same `Exchanger`

Although lessons typically use two threads, an `Exchanger` can be called by many threads. The runtime matches **pairs** for each successful swap.

For example, if four threads A, B, C, D arrive together:

```text
Possible pairing 1: (A,B), (C,D)
Possible pairing 2: (A,C), (B,D)
Possible pairing 3: (A,D), (B,C)
```

These are **logical possibilities**, not a probability distribution or an ordering guaranteed by the Javadoc.

With three arriving threads and no one else, one thread may wait for a partner forever if there is no timeout/interrupt. When you want to send specifically to **B**, an `Exchanger` shared by A, B, C, D is **not an addressed routing system**. Use a dedicated instance per fixed pair or a protocol with correlation keys.

Do not treat `Exchanger` as a "broadcast channel" where all parties receive everyone else's payloads: each exchange pairs **two** callers, not a multicast.

## 21. Java 17+ Example: Four Threads Paired into Two Pairs

Save as `ExchangerMultiplePairsDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Exchanger;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ExchangerMultiplePairsDemo {
    public static void main(String[] args) throws InterruptedException {
        Exchanger<String> exchanger = new Exchanger<>();
        CountDownLatch begin = new CountDownLatch(1);
        AtomicInteger succeeded = new AtomicInteger();
        AtomicInteger differentPeer = new AtomicInteger();

        Thread[] workers = new Thread[4];

        for (int i = 0; i < workers.length; i++) {
            final String mine = "T" + i;

            workers[i] = new Thread(() -> {
                try {
                    begin.await();
                    String peer = exchanger.exchange(
                            mine, 5, TimeUnit.SECONDS);

                    succeeded.incrementAndGet();
                    if (!mine.equals(peer)) {
                        differentPeer.incrementAndGet();
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } catch (java.util.concurrent.TimeoutException e) {
                    throw new IllegalStateException(e);
                }
            }, mine);
            workers[i].start();
        }

        begin.countDown();
        for (Thread thread : workers) {
            thread.join();
        }

        System.out.println("Successful threads: " + succeeded.get());
        System.out.println("Got other thread's item: "
                + differentPeer.get());
    }
}
```

```bash
javac ExchangerMultiplePairsDemo.java
java ExchangerMultiplePairsDemo
```

**Stdout when all four threads pair successfully within the deadline:**

```text
Successful threads: 4
Got other thread's item: 4
```

The specific partner identity is not printed because the pairing (T0/T1, T0/T2, or T0/T3) is **non-deterministic**. The logical outcome is stable: each successful thread receives an item from another thread, not the item it sent itself. Each worker's `mine` string is unique; no thread intentionally sends duplicate items.

If the system stalls for more than 5 seconds, threads can time out so the success count may be smaller; the article does not promise hard scheduling deadlines. In production, collect errors from workers and coordinate shutdown/cancellation so failed tasks are not silently dropped.

## 22. Pairing Is Neither FIFO, Fair, Nor Routed

Do not write code relying on these assumptions:

- The thread that calls `exchange` earliest will definitely pair with the next caller in strict FIFO order.
- Thread A will definitely pair only with B even when C and D also use the exchanger.
- After one side times out, its retry will always pair on the exact "turn" with the old peer.
- A thread is guaranteed to find a partner within a fixed deadline just because many other threads exist.
- Pairing order corresponds to task ID, request ID, or timestamp.

`Exchanger` does not provide a fairness parameter like some locks or queues. Pairing order and wait times depend on scheduling, contention, and runtime details. If you need **fairness or partner identity**, design it at the application layer or choose a different tool.

With two fixed threads, having each thread call **once per round** is much easier to reason about than a global exchanger receiving requests from hundreds of threads without a sequencing protocol.

## 23. Timeouts, Cancellation, and Session Skew

Scenario:

```text
A: wants to exchange round 7 data
B: still processing round 6

A.exchange(round7, 100ms) -> timeout
A decides to retry round7

B later arrives at exchange(round6)
A's retry may meet B's round6, even though A thinks B has reached round7
```

`Exchanger` only knows **there are two waiting callers**. It does not check whether the payloads have the same round ID. Therefore, **a round timeout is a protocol issue**, not just an exception to log.

One way to handle this with a fixed pair:

1. Agree that a timeout/interrupt means **canceling the entire session**, rather than retrying unilaterally.
2. If retries are needed, include a handshake/sequence ID and state recovery on **both sides**.
3. Do not apply side effects based on a received payload if `roundId` does not match.
4. Do not share one exchanger across independent sessions if cross-pairing is possible.
5. Set both per-round timeouts and an overall timeout so workers do not wait forever after a failure.
6. Use appropriate resource-close/cancellation tokens if a worker may block elsewhere before reaching `exchange`.

Do not assume `exchange(x, timeout)` has a "rollback protocol" across multiple exchanges. It only decides the outcome **of a single call**.

## 24. When One Side Throws an Exception Before Exchange

Suppose the producer hits an exception in `fillBuffer()` and exits the thread, while the consumer still calls:

```java
Buffer next = exchanger.exchange(emptyBuffer);
```

This is an illustrative snippet with hypothetical `Buffer`/`emptyBuffer`. The consumer can **wait forever** because there is no longer a producer.

Solutions:

- Use timed `exchange` and check for timeouts.
- When one side fails, send a **separate cancellation signal** (token/interrupt) to the other side.
- Define `RUNNING`, `STOPPING`, `STOPPED` states and clean up ownership.
- Do not rely on the failing worker's `finally` block to "open the exchanger": `Exchanger` **has no `countDown` or `close`**.
- If there are only two workers, the coordinating caller can use `Future` to observe one side's failure and then `cancel(true)` the remaining side per the executor's contract.
- If a buffer has already had its ownership transferred, avoid having both sides clean up or mutate that buffer on failure.

Error callback pattern to watch out for: if one thread times out and leaves, the other thread may still be at the corresponding exchange turn and must be woken by an interrupt or its own timeout.

## 25. Can `Exchanger` Pass `null`?

The generic parameter `T` is a reference type. `Exchanger` does not turn `null` into a business-identified token; a call may need to pass **no object** according to the two sides' protocol.

In readable code, prefer an **explicit message type**:

```java
record Envelope(long round, String status, String payload) {}

Exchanger<Envelope> exchanger = new Exchanger<>();
```

This is a Java 17 illustrative snippet without `main`. To represent "no payload", use `status` or an appropriate sealed hierarchy/enum. Avoid using `null` as an undocumented **END** signal, because the receiver will struggle to distinguish normal completion, missing data, or a logic bug.

A swapped object may contain null fields according to its own contract; thread safety still depends on ownership and publication. **Do not rely on `null` to coordinate lifecycle**, especially with retries or multiple rounds.

## 26. Generics and Type Safety

`Exchanger<T>` specifies the compile-time type of the exchanged objects:

```java
Exchanger<String> strings = new Exchanger<>();
Exchanger<byte[]> byteBuffers = new Exchanger<>();
Exchanger<java.util.List<Integer>> batches = new Exchanger<>();
```

These declarations are valid in an appropriate method or field scope. The Java compiler prevents the call:

```java
strings.exchange(123); // Does not compile: Integer is not String.
```

This is an **intentional non-compiling anti-example**; the method also declares `InterruptedException`.

**Generics do not deep-copy objects:** `byte[]` or `ArrayList` remains mutable. Generic types help prevent mixing payload types, but do not replace ownership contracts or round-ID matching.

If you need to exchange two different **kinds** of data in the same pair, wrap them in a common supertype/record/interface or use a wrapper:

```java
record SwapMessage(String sender, int round, byte[] payload) {}
```

Design the message type around the business contract to avoid unsafe casts. For a record containing `byte[]`, the record is shallowly immutable: the array inside is still mutable; copy it or transfer ownership safely.

## 27. With an Executor, Who Manages the Lifecycle?

`Exchanger` does not create or shut down threads. If running two `Runnable` tasks via `ExecutorService`, you need:

- A pool with enough capacity **for both sides to reach `exchange`**. A fixed single-thread pool running two tasks will have the first task wait at `exchange` and occupy the worker, preventing the second task from ever running: this can hang.
- **Observe errors from both tasks**, e.g., using `Future.get` or a result channel; throwing an exception in a worker does not automatically notify the caller.
- A deadline or cancellation policy for the exchange.
- If one side is canceled via `Future.cancel(true)`, the other side still needs to be woken up or time out if there is no new partner.
- `shutdownNow` typically requests interrupting workers; it does not guarantee arbitrary blocking I/O or user code stops immediately.
- Do not share a single exchanger across multiple application sessions without explicit pairing management.

Anti-pattern example:

```java
ExecutorService pool = Executors.newSingleThreadExecutor();

pool.submit(() -> exchanger.exchange("A"));
pool.submit(() -> exchanger.exchange("B"));
```

This is an illustrative snippet, intentionally omitting checked exception handling. Both tasks must run concurrently to reach the rendezvous, but the single worker is blocked by the first task while the second task sits in the queue. Use at least two appropriate workers, or a design that does not require both tasks to occupy workers simultaneously. Do not treat increasing pool size as a cure-all: if one task never reaches `exchange`, adding more workers still will not create a partner.

## 28. Avoid Holding a Lock While Waiting at `exchange()`

A dangerous mistake:

```java
synchronized (lock) {
    exchanger.exchange(myBuffer);
}
```

This is an illustrative snippet; `InterruptedException` handling is omitted.

If the partner must **acquire the same monitor `lock`** to prepare its payload before exchanging, a circular dependency arises:

```text
Thread A: holds lock -> waits for partner at exchange
Thread B: waits for lock -> cannot reach exchange
```

That is a lock-ordering deadlock, not a bug in `Exchanger` itself. The same applies to holding a `ReentrantLock`, a semaphore permit, or a transaction lock across a blocking exchange.

**Rule:** prepare the payload and protect required state inside a short lock region, **release the lock before waiting for the partner**, and then apply the result according to the appropriate protocol. If you need an atomic update with the swap result, design a protocol without circular waits or use a different primitive.

## 29. `Exchanger` and Virtual Threads

In Java versions with virtual threads (stable since Java 21), `Exchanger` remains a thread coordination API under the Java SE contract. However, **`Exchanger` does not solve logic deadlocks by itself**: if only one side arrives, it still needs a partner, a timeout, or an interrupt.

This lesson uses **Java 17+** with platform threads so runnable examples work on JDK 17. It does not depend on virtual thread APIs or specific virtual thread scheduler implementation details.

If using virtual threads in newer Java versions, you still must consider mutable buffer ownership, exception propagation, multiple rounds, and match identity. Do not assume cheaper virtual threads mean a task can wait indefinitely for a partner without affecting application lifecycle.

## 30. Common Mistakes

**1. "`exchange` sends an item into a queue."** False. It is a two-way rendezvous; a partner is required for success.

**2. "A thread can call `exchange` alone and get its own item back."** Without a partner it blocks, times out, or is interrupted; it never self-completes with its own item.

**3. "`Exchanger` always pairs two threads named A and B."** No. When multiple callers share an instance, partner pairing is not fixed by thread name.

**4. "`exchange` creates the missing thread."** False. You must start/submit the participating tasks yourself.

**5. "The timed overload always throws when timeout is 0."** Not necessarily. If a partner is already waiting, it can match immediately; it just will not wait for a new partner once the budget is exhausted.

**6. "A timeout automatically interrupts the partner side."** False. Timeout applies to the current call; the peer needs its own cancellation protocol.

**7. "The interrupt status stays set inside `catch (InterruptedException)`."** Per `exchange`'s contract, the status is cleared when thrown; if you cannot propagate and want to preserve cancellation, restore it.

**8. "`Exchanger` copies the `ArrayList`/buffer."** False. It swaps references; objects remain mutable.

**9. "After swapping, the producer is free to keep modifying the buffer it sent."** This violates ownership handoff and can cause a data race.

**10. "`happens-before` means no synchronization is needed for any future mutations."** False. It guarantees ordering/visibility for actions before a successful exchange and corresponding actions after it, not locking future operations.

**11. "If three threads call `exchange`, all three finish."** There is no collective barrier for three; one thread can remain waiting.

**12. "`Exchanger` has FIFO and fairness by default."** There is no such fairness or partner-ordering guarantee in the public API.

**13. "Two rounds sharing an exchanger always stay aligned even if one side retries or skips a turn."** No. You need a sequence/cancellation protocol to avoid round skew.

**14. "If the producer crashes, the consumer automatically receives an end signal."** No. `Exchanger` has no built-in close/EOF; use timeouts/interrupts and lifecycle signals.

**15. "A single-worker pool can run two blocking exchange tasks."** This easily deadlocks/starves because the first task waits for the second task, which cannot start.

**16. "Wrapping `exchange` in `synchronized` is always safe."** Not if the peer needs that monitor to reach `exchange`.

**17. "`Exchanger` replaces all queues, barriers, and phasers."** No. Each has a distinct synchronization goal.

**18. "A successful exchange means the consumer has finished processing the payload."** No. It only confirms the reference swap between the pair, not that the receiver has committed business work.

**19. "You can retry any exchange indefinitely on `TimeoutException`."** This risks session-skewed retries or holding resources forever; design shared deadlines and correlation IDs.

**20. "Generic type `T` makes the exchanged object immutable."** No. Mutable payloads still require ownership and synchronization.

## 31. `Exchanger<T>` Implementation Checklist

Before deploying to production:

1. **Is it truly bidirectional?** If it is only one-way sending, consider `BlockingQueue`/`SynchronousQueue`.
2. **Does each exchange have exactly two intended participants?** If multiple threads share it, define the pairing policy.
3. **Do both sides share the same exchanger instance?** Two different instances will never pair with each other.
4. **Is the partner guaranteed to reach `exchange` on all execution paths?** Including exceptions and early returns.
5. **Is there a timeout or cancellation plan?** Avoid waiting forever when a peer dies.
6. **Is `InterruptedException` handled properly?** Propagate if possible; otherwise restore and stop.
7. **Does a timeout cancel the whole session or retry?** Never retry unilaterally without coordination.
8. **Is there a sequence ID/correlation ID for multiple rounds?** Prevent cross-round mismatches.
9. **Is there an ownership rule for mutable payloads?** Never reuse a reference already sent to a partner.
10. **Do received objects have the right lifecycle?** Is the buffer cleared, reusable, and untouched by the other side?
11. **Did you test a missing partner?** Test one thread being canceled before reaching the rendezvous.
12. **Is any shared lock held across `exchange`?** Avoid circular-dependency deadlocks.
13. **Does the executor have enough workers for both sides to reach `exchange`?** A single-thread fixed pool is usually insufficient.
14. **Did you test multiple callers and arbitrary pairing?** Do not hardcode that T0 always pairs with T1.
15. **Do you log success/failure/timeouts and wait durations?** Monitor latency, without confusing scheduling delays with bugs.
16. **Did you test JMM visibility with the right pattern?** Write before swap, read after swap; avoid concurrent mutation after handover.
17. **Who is responsible for shutdown?** `Exchanger` has no `close`; stop threads/tasks via their owner.
18. **Do you need exactly-once processing or durability?** `Exchanger` provides neither transaction logs nor business acks.
19. **Are there memory/resource bounds?** Do not retain oversized buffers indefinitely in an exchange loop.
20. **Is there a fallback when a peer is slow?** Choose deadlines, tokens, another queue, or controlled pipeline termination.

## 32. Self-Check Questions

**Q1:** Is `Exchanger<String>` a queue that stores Strings?

**No.** It is a rendezvous point: one caller brings a String and waits for a peer to bring another String to swap.

**Q2:** A sends `"X"`, B sends `"Y"`. What do A and B receive on success?

A receives `"Y"`, B receives `"X"`. There is no guarantee on the order in which the two threads resume after the swap.

**Q3:** What if only A calls `exchange("X")` and B never arrives?

A can wait forever unless interrupted; if using the timed overload, it can receive `TimeoutException`.

**Q4:** Does `exchange(x, timeout)` throwing `TimeoutException` send a cancellation to B?

No. A timeout only reports that A could not match within the deadline; B must have its own signal or timeout.

**Q5:** Does `exchange` with a mutable buffer create a deep copy?

No. Both sides swap references. Ownership rules must prevent concurrent modification after handover.

**Q6:** If `payload.number=42` is written before the swap and the partner reads it after a successful swap, is visibility guaranteed?

Yes, per the memory consistency effect specified in the Javadoc for a successfully paired exchange, provided no unsynchronized concurrent mutation breaks the contract.

**Q7:** Three threads A/B/C use one exchanger; are all three guaranteed to pass through `exchange`?

No. Two threads can pair up, leaving the remaining thread waiting for a fourth partner or a timeout/interrupt.

**Q8:** Does `Exchanger` identify partners by ID automatically?

No. When multiple callers share one, you need per-pair instances or an external routing/correlation protocol.

**Q9:** Is it safe for the producer to send a full buffer and immediately call `clear()` on the buffer it just sent?

No. The consumer may be reading that same object. The producer may only clear **the newly received buffer** that it now owns.

**Q10:** What can happen when two exchange tasks are submitted to `Executors.newSingleThreadExecutor()`?

The first task blocks waiting for a partner while the second task stays in the queue and cannot start, which can lead to no progress.

**Q11:** Should `InterruptedException` from `exchange` always be ignored so the task keeps running?

No. Usually you should propagate it, or restore the flag and stop per the cancellation contract at a `Runnable` boundary.

**Q12:** When is `Exchanger` better than `SynchronousQueue`?

When **both sides have an object to trade**, especially when swapping full/empty buffers. For one-way transfer, `SynchronousQueue` is usually clearer.

**Q13:** Can you create one global exchanger and use it for all client request–response pairs?

Only if pairing does not matter or a separate protocol guards it. If responses must match specific requests, a shared `Exchanger` does not provide ID-based routing.

**Q14:** How do `CountDownLatch` and `Exchanger` differ?

A latch waits for a count/event and does not swap payloads. `Exchanger` pairs two callers to swap objects.

**Q15:** Should you hold a `ReentrantLock` while waiting at `exchange` if the partner needs that lock to prepare its item?

No. That easily creates a circular dependency leading to deadlock.

**Q16:** Does a successful exchange pair prove the receiver has finished business processing on the payload?

No. It confirms the swap, not downstream processing success or commit. Acknowledgments require an additional protocol.

## 33. Summary

- **`Exchanger<T>` swaps objects between pairs of threads**; it does not queue, broadcast, or create threads.
- **`exchange(x)`** waits for a partner, swaps, and returns the partner's object; **`exchange(x, timeout, unit)`** adds a time limit and `TimeoutException`.
- **`InterruptedException`** is the cooperative cancellation path; `exchange` clears the status when thrown, so never use an empty catch if you need to preserve stop requests.
- **Happens-before** between actions before a successful exchange and actions after the exchange in the partner thread helps **publish prepared payloads**, but does not protect against post-handover mutations.
- The classic use case is **swapping full/empty buffers**, reducing allocations and clarifying ownership in two-stage producer–consumer pipelines.
- With multiple threads, `Exchanger` only **pairs two at a time**, without guaranteeing partner identity, fairness, FIFO, or collective synchronization for N threads.
- **Timeouts, exceptions, or missed rounds** can skew the protocol; use sequence IDs, deadlines, cancellation, and explicit cleanup for multi-round usage.
- **`SynchronousQueue` is better suited for one-way handoffs; `CountDownLatch`/`CyclicBarrier`/`Phaser` fit other waiting patterns.**
- Never wait at `exchange` while holding a monitor/lock the partner needs; never run two blocking tasks on a single-worker executor.
- A successful swap is not a transaction, a business processing acknowledgment, or a durable delivery guarantee.

**Design self-check:** *"Who is the partner, what object does each side send, which buffer does each side currently own, and if one side never reaches the exchange point, how can the other side exit and clean up?"* If you can answer those four questions, `Exchanger<T>` can be a very clean tool for two-way data exchange protocols in Java concurrency.

**Official reference:** [Java SE 17 — Exchanger Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Exchanger.html).
