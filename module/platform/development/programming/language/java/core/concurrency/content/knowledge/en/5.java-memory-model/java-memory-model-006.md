# Thread.start(), Thread.join(), and Synchronization Relationships in the Java Memory Model

In multithreaded programming, the fact that one thread **performs a write earlier in wall-clock time** does not automatically mean another thread is guaranteed to see that write. The Java Memory Model (JMM) defines memory relationships that allow us to reason about **ordering** and **visibility** across threads. Two fundamental `Thread` operations — `start()` and `join()` — also serve as important synchronization points in the JMM.

This lesson focuses on two guarantees:

1. **Before `start()` → inside the started thread:** every action in thread A prior to calling `threadB.start()` has a *happens-before* relationship with every action in the started thread B.
2. **Inside the terminated thread → after `join()` succeeds:** every action in thread B has a *happens-before* relationship with the actions in thread A after A detects that B has successfully terminated via `threadB.join()`.

These are **directional** relationships, not promises about CPU scheduling order. Understanding both rules correctly lets you pass input data to a worker and retrieve results after the worker completes, even when the example data variables do not use `volatile` or `synchronized`.

## 1. What Does Happens-Before Mean?

According to the JMM, if action A *happens-before* action B, the memory effects of A are constrained so that B observes them according to the memory model rules; a read at B must still account for **other writes** that might intervene, rather than automatically receiving the exact value of "write A" in every case.

Key points:

- Within the **same thread**, earlier actions in *program order* happen-before later actions, even though the compiler/JIT/CPU may perform optimizations within the bounds of preserving semantics.
- The happens-before relationship is **transitive**: if A → B and B → C, then A → C.
- A *synchronizes-with* relationship (for example, `start()` or detecting thread termination) creates a happens-before edge between threads.
- Happens-before **does not mean** the two threads run completely sequentially one after the other. Actions that are not constrained can still interleave.
- *Lacking* an appropriate happens-before relationship when two threads access the same mutable state can create a **data race** and produce results without expected visibility guarantees.

Therefore, `start()` and `join()` should be understood as both lifecycle APIs and **memory synchronization milestones**.

## 2. Thread.start(): Publishing Data Before Starting

The core rule: **a call to `t.start()` on a thread `t` synchronizes-with the actions in thread `t`**. Combined with program order, every operation performed before the `start()` call in the starting thread happens-before the operations in the new thread.

Diagram:

```text
Thread main                           Thread worker
-----------                           -------------
data.input = 21
data.label = "ready"
      |
      | program order
      v
worker.start()
      |  synchronizes-with
      +--------------------------------> read data.input, data.label
                                         compute result
```

This is very useful for **passing prepared input** to a new thread: an object initialized/populated before `start()` can be read by the worker under that happens-before relationship. However, if the main thread continues to **write to the same variable after `start()`** while the worker is reading it, the two actions after `start()` may not be synchronized with each other. `start()` does not make all future data sharing safe.

Simple example:

```java
// Illustrative snippet, assuming appropriate Data data and Thread worker.
data.input = 21;         // Has happens-before with actions in worker.
worker.start();
data.input = 99;         // NOT automatically protected by start() with respect to the worker.
```

If both main and worker access `data.input` without synchronization after `start()`, a separate coordination mechanism is required. You cannot infer from having called `start()` that the worker will definitely read 21 or 99.

**Common misconception:** `start()` does not wait for the worker to finish running, nor does it even guarantee that the worker has executed its first statement when `start()` returns. It only starts the new thread and establishes the directional synchronization edge from actions before `start()`.

## 3. Thread.join(): Detecting Termination and Retrieving Results Properly

`thread.join()` causes the **calling thread** to wait for the target thread to finish; if interrupted while waiting, the method can throw `InterruptedException`. Once the target thread is detected to have actually terminated via `join()`, the actions performed in the target thread happen-before subsequent actions on the calling thread.

Diagram:

```text
Thread worker                          Thread main
-------------                          -----------
read input data
result.answer = 42
exit run()
      |
      | thread termination detected by join
      +--------------------------------> worker.join() completes
                                         |
                                         | program order
                                         v
                                       read result.answer
```

It is not mandatory to declare `result.answer` as `volatile` **just for a one-way result handoff** if there are no conflicting accesses and main only reads after `join()` completes successfully. `join()` provides both the lifecycle wait point and the necessary memory visibility guarantee.

Important distinctions:

- `join()` **does not** start a thread. An unstarted `Thread` has no execution to wait for; calling `join()` on it does not cause `run()` to be invoked.
- `join()` **does not** by itself ask the worker to stop running. If the worker hangs forever, an untimed `join()` can wait forever.
- `join()` **does not** automatically propagate exceptions thrown in the worker to the calling thread. You must design a separate error/result collection mechanism.
- Only **detecting that the thread has terminated** creates the appropriate relationship; a `join(timeout)` returning while the worker is still alive is not proof that the worker has finished.
- This memory relationship applies to the *specific thread* being waited on. If the worker spawns child threads or submits tasks to an executor and then terminates itself, joining the worker **does not automatically wait** for those independent tasks still running elsewhere.

The JMM also allows another thread to detect termination via `isAlive()` returning `false` for a thread that has actually terminated; however, when the goal is to wait for completion, `join()` communicates intent much more clearly and avoids continuous polling.

## 4. Example 1 — Passing Input Before start, Reading Output After join

This complete example intentionally uses plain `int` fields, without adding `volatile` or `synchronized`, to demonstrate the combination of the two happens-before edges.

Create **`StartJoinVisibility.java`**:

```java
public class StartJoinVisibility {
    static final class Data {
        int input;
        int output;
    }

    public static void main(String[] args) throws InterruptedException {
        Data data = new Data();
        data.input = 21;

        Thread worker = new Thread(() -> {
            data.output = data.input * 2;
        }, "calculator");

        worker.start();
        worker.join();

        System.out.println("Input: " + data.input);
        System.out.println("Output: " + data.output);
    }
}
```

Compile and run with JDK 17+:

```bash
javac StartJoinVisibility.java
java StartJoinVisibility
```

Output:

```text
Input: 21
Output: 42
```

JMM interpretation:

1. Main writes `data.input = 21` **before** `worker.start()`; this write happens-before the read of `data.input` in the worker.
2. Worker reads 21, computes 42, writes `data.output = 42`, and finishes `run()`.
3. Main waits for `worker.join()` to complete; the worker's write to output happens-before main's read of output after `join()`.
4. No thread overwrites either field concurrently during that window, so the output above is guaranteed.

The transitive chain can be represented as:

```text
main: input = 21
       |
       | program order + start()
       v
worker: read input 21 -> output = 42 -> terminate
       |
       | termination detected via join()
       v
main: read output 42
```

**Practical takeaway:** delegating a computation to another thread and calling `join()` is a valid way to hand off state. This does not mean every sharing of plain fields between threads is safe: the example is structured so that input is written before start and output is only read by main after join.

## 5. No Reverse Relationship From Worker to Main From start() Alone

Consider this snippet (illustrative snippet; `data` is already declared):

```java
Thread worker = new Thread(() -> data.output = 42);
worker.start();
System.out.println(data.output); // No fixed result.
```

The worker's write to `data.output` **does not automatically happen-before** the read in main just because of `start()`. Main may read the old or new value, and running it multiple times and seeing the same output still does not prove the code is correct. If `data.output` is an unsynchronized `int` field, this conflicting write/read can constitute a data race.

The clear fix when the result is needed **after completion**:

```java
worker.start();
worker.join();
System.out.println(data.output);
```

This fix is an illustrative snippet that must be inside a method that handles `InterruptedException`. If you need to receive **results while the worker is still running**, `join()` does not fit because it waits for termination; you need `volatile`, `Atomic*`, locks, `BlockingQueue`, `CountDownLatch`, `Future`, or another synchronization construct suited to the data-exchange protocol.

**You also cannot infer** that calling `first.start(); second.start();` makes all of `first`'s work happen-before `second`'s work. Main orders the two `start()` calls, but there is no direct edge between the execution actions inside `first` and `second` from those two calls alone.

## 6. Example 2 — Transitivity When Handing Off Data Between Two Workers

If main truly waits for the first thread to terminate before starting the second thread, the happens-before edges link into a chain.

Create **`ThreadHandoff.java`**:

```java
public class ThreadHandoff {
    static final class Box {
        int value;
    }

    public static void main(String[] args) throws InterruptedException {
        Box box = new Box();

        Thread producer = new Thread(() -> {
            box.value = 7;
        }, "producer");

        producer.start();
        producer.join();

        Thread consumer = new Thread(() -> {
            System.out.println("Received: " + box.value);
        }, "consumer");

        consumer.start();
        consumer.join();
        System.out.println("Done");
    }
}
```

```bash
javac ThreadHandoff.java
java ThreadHandoff
```

Output:

```text
Received: 7
Done
```

Chain of relationships:

```text
producer: box.value = 7
             |
             | producer terminates -> main join() detects
             v
main: producer.join() completes -> consumer.start()
                                      |
                                      | start() synchronizes-with consumer
                                      v
consumer: read box.value == 7
```

Because happens-before is transitive, the producer's write happens-before the consumer's read under the JMM. A separate `volatile` on `box.value` is not needed in this exact **producer finishes → main joins → consumer starts** protocol.

If you omit `producer.join()`, main could start the consumer before the producer writes the data; the consumer is not guaranteed to read 7. In real applications, serializing two threads into phases like this can reduce concurrency. If you need concurrent execution with event-driven data transfer, use a coordination mechanism such as a queue, latch, or future.

## 7. join(timeout): Waiting Ending Does Not Mean the Worker Terminated

`join(long millis)` waits **at most a bounded amount of time** for the worker to terminate; it can return while the worker is still running. Therefore, you must **check the completion condition** after the call if you need to decide whether it is safe to read the final state.

The following example intentionally holds the worker in a waiting state with a latch so that the "timed out while thread is still alive" branch is easy to observe and does not depend on fast/slow scheduling.

Create **`TimedJoinDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class TimedJoinDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch release = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "waiting-worker");

        worker.start();
        worker.join(20);

        System.out.println("Alive after timed join: " + worker.isAlive());

        release.countDown();
        worker.join();

        System.out.println("Alive after full join: " + worker.isAlive());
    }
}
```

```bash
javac TimedJoinDemo.java
java TimedJoinDemo
```

Output in a normal run:

```text
Alive after timed join: true
Alive after full join: false
```

The worker cannot exit `release.await()` before main calls `release.countDown()`, so after `join(20)` it is still alive. Once the release signal is given, the worker terminates, the untimed `join()` returns, and main confirms the thread is done. The latch itself also has its own memory synchronization rules; in this example, it primarily helps control when the worker terminates.

**Important:** a `join(timeout)` call returning is not by itself enough to infer the *worker terminated → main* guarantee. Only when `worker.isAlive()` shows it has actually terminated is it a case of detecting termination. With a timeout value, the thread might finish before the deadline or still be running after the deadline; code must not assume only one side.

Do not use `join(0)` to specify a zero timeout: in the `join(long)` overload, **0 means wait indefinitely**. If you want an actual deadline or cancellation capability, design an explicit timeout/interruption handling path.

## 8. Interrupted join() and Proper Lifecycle Handling

Only the thread **calling `join()`** is blocked in the wait operation. If the waiting thread receives an interrupt, `join()` throws `InterruptedException` and the wait has been aborted; you must not automatically conclude that the target worker has finished. The target worker may still be running.

In a method responsible for handling it rather than rethrowing `InterruptedException`, it is common to restore the interrupt flag so callers above can observe it:

```java
try {
    worker.join();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Decide whether to cancel work / delegate cleanup.
}
```

This is an illustrative snippet, assuming the `worker` variable is already declared. **Interrupting the waiting thread** is different from **interrupting the target worker**. `worker.interrupt()` sends a cooperative signal to the worker; it does not force the worker to terminate immediately, does not automatically transition the worker to TERMINATED, and does not replace `join()`.

If a worker could wait indefinitely, the practical approach is to have a **stop-request protocol**, handle interrupts in the right places, and use reasonable wait timeouts. `Thread.stop()` is not a solution: that method is obsolete and unsafe.

## 9. join() Does Not Carry Results or Exceptions Back for You

`Thread.join()` returns `void` and only serves waiting/lifecycle coordination. It **does not return a value from a Runnable**, nor does it automatically rethrow uncaught exceptions from the worker. You can use a shared result/error holder and read it only after `join()`, or choose an API that carries results such as `Future`.

Create **`JoinAndFailure.java`**:

```java
import java.util.concurrent.atomic.AtomicReference;

public class JoinAndFailure {
    public static void main(String[] args) throws InterruptedException {
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread worker = new Thread(() -> {
            throw new IllegalStateException("bad input");
        }, "failing-worker");

        worker.setUncaughtExceptionHandler((thread, error) -> {
            failure.set(error);
        });

        worker.start();
        worker.join();

        Throwable error = failure.get();
        System.out.println("Worker terminated: " + !worker.isAlive());
        System.out.println("Failure: "
                + (error == null ? "none" : error.getMessage()));
    }
}
```

```bash
javac JoinAndFailure.java
java JoinAndFailure
```

Output:

```text
Worker terminated: true
Failure: bad input
```

The `UncaughtExceptionHandler` receives the error as the thread is about to terminate due to an uncaught exception. After `join()`, main observes the information recorded by the handler and decides how to handle the error. `AtomicReference` here serves as a result container with a clear access interface; in a protocol that only reads after a successful `join()`, waiting for termination already provides the memory relationship for data written by the worker prior to termination.

Keep in mind that **worker termination does not mean worker success**. If you want an API that returns results/exceptions with a clearer contract, `ExecutorService.submit(...)` and `Future.get()` offer an alternative approach, along with the added responsibility of shutting down the executor.

## 10. How Thread.start()/join() Differ From volatile, synchronized, and Other Tools

| Tool | Main relationship / guarantee | When to use |
|---|---|---|
| `Thread.start()` | Actions before start in the starting thread happen-before actions in the new thread. | Publishing prepared data before the worker starts. |
| `Thread.join()` | Actions of the terminated thread happen-before actions after another thread detects termination. | Waiting for a worker and reading final state/results. |
| `volatile` | A volatile write synchronizes-with subsequent reads of the same variable in synchronization order. | Flags/signals or simple values exchanged **while threads are still running**. |
| `synchronized` | Unlocking a monitor synchronizes-with the next lock of the same monitor, while protecting a critical section. | Check-then-act or invariants involving multiple steps/fields. |
| `AtomicInteger` and `Atomic*` | Reads/writes/updates with atomicity guarantees and memory effects per the API. | Counters, CAS, and single-variable atomic state. |
| `CountDownLatch` | Actions before `countDown()` happen-before actions after a successful `await()` in another thread. | Coordinating between threads that have not terminated. |
| `Future.get()` | Has a contract to wait for the result, and the task's actions happen-before actions after the corresponding `get()`. | Receiving results or errors from an asynchronous task. |

The `start()` and `join()` examples do not need `volatile` for properly structured one-way data handoff; however, **you cannot omit all synchronization** if two threads concurrently read/write state while running. A `volatile` read/write also does not automatically make a multi-step check-then-act sequence atomic.

### Confusing "Happened in Wall-Clock Time" With "Happens-Before"

The JMM defines a formal relationship. Seeing in logs that A printed before B does not necessarily mean other data operations between the two threads have a corresponding happens-before relationship; logging itself uses internal synchronization that can also alter scheduling. You must establish it with concrete edges such as start, join, lock/unlock, volatile, or synchronization primitives.

### Confusing Start Order With Completion Order

`a.start(); b.start();` does not guarantee A finishes before B. Nor does it guarantee A prints a line before B just because A was started first. If you want B to execute work only after A finishes, wait for `a.join()` before starting B or use a synchronization protocol between the two workers.

### Confusing In-Memory Data With External Side Effects

Happens-before guarantees memory relationships within Java; it **does not** promise that a file has been flushed/persisted to disk, a network request has been processed by another system, or an out-of-process transaction has committed. Those guarantees require the specific APIs and protocols of the external resource.

## 11. Questions to Verify Correctness

When deciding whether you can exchange data using `start()`/`join()`, check each of these in order:

1. **Who writes the input and when?** If main finishes writing before `start()`, the worker can rely on the start edge.
2. **Is the input modified by another thread after start?** If so, the start edge does not protect those later concurrent operations.
3. **Who writes the output and when does main read it?** If it is only read after `join()` completes due to worker termination, the termination edge applies.
4. **Are you using `join(timeout)`?** If the worker is still alive after the timeout, the final data cannot yet be assumed stable; you must check for termination or use an appropriate primitive.
5. **Does the worker spawn additional threads/tasks?** `join()` only waits for the specified worker, not automatically for all tasks it delegated.
6. **What if the worker fails or never terminates?** Are there proper error reporting, cooperative cancellation, timeouts, and cleanup?
7. **Does the invariant span multiple steps or multiple fields?** If so, start/join may fit separate *phases*, while concurrent access within a phase requires appropriate locks/atomics/primitives.

Note that these happens-before rules apply to Java thread relationships; for **virtual threads** officially introduced in Java 21, the essence of the start/join rules still holds. The lesson examples use standard Java 17 APIs so they can be compiled and run directly.

## 12. Self-Check

1. **Which direction of data flow does `start()` guarantee?** Actions that occurred before start on the starting thread happen-before actions of the started thread. There is no reverse guarantee from worker to main from start alone.
2. **Why doesn't `data.output` need `volatile` in Example 1?** Because main only reads after `join()` completes, creating a happens-before relationship from the worker's write to main's read; accesses are not contended outside the protocol.
3. **Does `a.start(); b.start();` make `a`'s actions happen-before `b`'s?** No, unless there is an additional synchronization edge connecting the two threads.
4. **If `join(20)` returns, is the worker guaranteed to have terminated?** No; you must verify that the worker has actually terminated or use another completion-waiting mechanism.
5. **Does `join()` automatically propagate a worker's exception to main?** No; you need an error holder, an uncaught exception handler, a Future, or a separate result protocol.
6. **What happens if main is interrupted while waiting in join?** The call can throw `InterruptedException`; you must not assume the worker has completed.
7. **Why can two threads concurrently writing/reading a variable after `start()` still race?** Because the start edge only covers actions before start to the new thread; it does not order subsequent conflicting accesses.
8. **If producer finishes, main joins producer, and then starts consumer, what guarantees consumer sees the result?** The termination → join edge, program order on main, and the start → consumer edge combine into a transitive happens-before relationship.

**Key takeaway:** `Thread.start()` is the edge for **publishing data into a worker**; `Thread.join()` when termination is actually observed is the edge for **receiving results from a worker**. Combining these two edges properly with *program order* and transitivity creates a simple, clear data-handoff protocol under the Java Memory Model. For concurrent accesses while a worker is still running, appropriate synchronization mechanisms are still required.
