# Propagating InterruptedException When the Contract Allows

## 1. Why Propagate the Interruption Signal?

In Java, **interruption** is a mechanism for one thread to notify another thread that its current work should be stopped, canceled, or reconsidered. It is a **cooperative request**: calling **Thread.interrupt()** does not force the JVM to kill the thread and does not automatically roll back data that has already been modified.

When a thread is waiting at an interruptible method—such as **Thread.sleep()**, **CountDownLatch.await()**, **BlockingQueue.take()**, **Future.get()**, or **Thread.join()**—that method may throw **InterruptedException**. This exception lets the code know that the interruption request must be handled rather than continuing to wait until the work completes.

For a method that is allowed to declare **throws InterruptedException**, the most appropriate choice is usually **to let the exception propagate to the caller**. A higher-level caller has more context to decide whether to stop the entire operation, cancel related work, report status, or hand off handling to an orchestration layer.

For example, a service method calling a repository with a blocking wait operation:

~~~java
// Two illustrative methods; not a standalone program.
static String fetch() throws InterruptedException {
    return queue.take();
}

static String load() throws InterruptedException {
    return fetch();
}
~~~

Suppose **queue** is an already declared **BlockingQueue<String>**. If the thread waiting for an element in **queue.take()** is interrupted, InterruptedException passes through **fetch()** and then reaches **load()**; neither layer needs to catch it and continue running as if nothing happened.

Here, **propagation** means preserving the work-lifecycle control signal. This is not an exception representing a normal business error, nor does it automatically mean that another task in the system has already been canceled.

## 2. The throws InterruptedException Contract

**InterruptedException** is a checked exception in **java.lang** that extends **Exception**. A method calling an API that can throw InterruptedException must either:

1. Declare **throws InterruptedException** and let the exception propagate; or
2. Catch the exception and handle it according to an explicit policy.

If the current layer is only an intermediate step and is permitted to declare checked exceptions, the first option is usually simpler, safer, and accurately expresses the contract.

~~~java
// Illustrates a structurally valid Java call chain.
static void lowLevel() throws InterruptedException {
    Thread.sleep(1_000);
}

static void middleLevel() throws InterruptedException {
    lowLevel();
}

static void higherLevel() throws InterruptedException {
    middleLevel();
}
~~~

These methods are logically independent, though they must be placed inside a class to compile. **higherLevel()** does not need to create a new exception; it informs its caller that the operation can be interrupted.

A **throws InterruptedException** signature is important API design information:

- The caller knows this is a call that can be interrupted while waiting.
- The caller can proactively decide whether to exit, clean up, or continue at the boundary that owns the work.
- Code reviews can easily spot an intermediate layer accidentally swallowing or changing the meaning of an interrupt.
- Tests can verify that interruption passes through the layers.

However, you should not arbitrarily declare throws on APIs where it is not genuinely needed. Only make this signal part of the contract when there is an interruptible operation or a valid reason to communicate it to the caller.

## 3. How Are the Interrupt Flag and Exception Related?

Each **Thread** object has its own interrupt state. Another thread can call **target.interrupt()** to set the interruption request. What happens next depends on the code and the operation the thread is currently executing:

- If the thread is waiting in an interruptible API, the wait operation may stop and throw InterruptedException.
- If the thread is running normal computational code, calling interrupt mainly sets the flag; the code must check the flag or reach an interruptible API to respond appropriately.
- If an API does not support interruption, an interrupt might not stop that operation.

Two ways of checking the flag are often confused:

| API | Function | Clears the interrupt flag? |
| --- | --- | --- |
| **Thread.currentThread().isInterrupted()** | Reads the interrupt status of the current thread | No |
| **someThread.isInterrupted()** | Reads the interrupt status of the referenced thread | No |
| **Thread.interrupted()** | Reads the interrupt status of the **calling thread** | **Yes**, clears the flag upon checking |
| **Thread.currentThread().interrupt()** | Re-sets/requests an interrupt on the current thread | Sets the flag |

Many blocking APIs under the JDK contract, including **CountDownLatch.await()**, **clear the thread's interrupted status** when they detect an interruption and before throwing InterruptedException. Therefore, after catching InterruptedException, **isInterrupted()** may be false even though a valid interruption request occurred.

Policy decision points:

- **If you can throw InterruptedException up to the caller**, simply using **throw** or **throw e** is usually enough to signal interruption. The caller receives a meaningful exception; it is not mandatory to reset the interrupt flag in every intermediate layer.
- **If you cannot throw a checked exception**, such as in **Runnable.run()**, the code should usually restore the interrupt flag via **Thread.currentThread().interrupt()** and then exit or let the orchestration boundary decide.
- **If converting to another exception type**, you must determine whether the caller will still recognize the interruption. Usually, you should preserve both the interrupt flag and the cause when InterruptedException cannot be propagated directly.

There is no universal rule to "always re-interrupt and always throw" for every API. If you both restore the interrupt flag and continue calling blocking methods, those methods may immediately throw InterruptedException afterward. The policy must fit the current contract and thread-ownership boundary.

## 4. Java 17+ Example: Propagating Across Layers, Handling at the Runnable Boundary

The following program simulates three layers:

1. **repositoryWait** is the low-level layer using **CountDownLatch.await()**, which can throw InterruptedException.
2. **serviceWait** needs an observation step but still executes **throw failure** to propagate the exact exception upward.
3. **Runnable** is the final boundary; **run()** does not declare checked InterruptedException, so it catches it, restores the interrupt flag, and finishes its work.

Using two latches for coordination ensures the result does not depend on assumptions about thread scheduling speed. **gate** is never opened; in this example, waiting can only end via interruption.

Save to **InterruptPropagationDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class InterruptPropagationDemo {
    static void repositoryWait(CountDownLatch gate)
            throws InterruptedException {
        try {
            gate.await();
        } finally {
            System.out.println("Repository cleanup");
        }
    }

    static void serviceWait(CountDownLatch gate)
            throws InterruptedException {
        try {
            repositoryWait(gate);
        } catch (InterruptedException failure) {
            System.out.println("Service propagates interruption");
            throw failure;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);
        CountDownLatch gate = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                ready.countDown();
                serviceWait(gate);
                System.out.println("Unexpected completion");
            } catch (InterruptedException failure) {
                System.out.println("Boundary caught: InterruptedException");
                System.out.println("Flag in catch: "
                        + Thread.currentThread().isInterrupted());
                Thread.currentThread().interrupt();
                System.out.println("Flag restored: "
                        + Thread.currentThread().isInterrupted());
            }
        }, "worker");

        worker.start();
        ready.await();
        worker.interrupt();
        worker.join();
        System.out.println("Worker finished: " + !worker.isAlive());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 InterruptPropagationDemo.java
java InterruptPropagationDemo
~~~

Stdout verified by compiling and running:

~~~text
Repository cleanup
Service propagates interruption
Boundary caught: InterruptedException
Flag in catch: false
Flag restored: true
Worker finished: true
~~~

### Sequence Walkthrough

**ready.countDown()** confirms that the worker has started. After main passes **ready.await()**, main calls **worker.interrupt()**. At this point, the worker may already be inside **gate.await()** or about to call await; in either case, waiting on gate detects the interrupt state and throws InterruptedException.

In **repositoryWait**, **finally** still executes and prints **Repository cleanup**. The exception continues to propagate because finally does not replace it with another exception.

In **serviceWait**, the catch block only records a trace message and executes **throw failure**: the exact same InterruptedException instance continues propagating upward. Because the service layer declares **throws InterruptedException**, it does not need to wrap the exception in a RuntimeException and does not need to restore the flag here.

**CountDownLatch.await()** clears the interrupt status when throwing the exception, so inside **Runnable**, **isInterrupted()** prints false. Because **Runnable.run()** is not allowed to declare throws InterruptedException, the worker restores the flag and exits the catch branch. Main uses **join()** to confirm the thread has terminated before printing the final line.

This example illustrates the contract in a controlled execution path. It does not mean every API clears the flag when throwing any kind of exception; you must rely on each method's contract.

## 5. When Is As-Is Propagation Better?

In a multi-layered system, a lower layer is usually not the owner of the overall job lifecycle. For example:

~~~text
Controller / job coordinator
    |
    v
Application service
    |
    v
Repository / integration adapter
    |
    v
BlockingQueue.take() or CountDownLatch.await()
~~~

If the repository layer catches InterruptedException and continues an infinite loop, the controller layer may never be able to process a request cancellation. If the service layer turns every interruption into a data error, the coordinator layer might mistakenly retry and cause unnecessary load.

When method signatures allow it, let **InterruptedException** propagate up to the place that can make decisions about the task's lifecycle. An intermediate layer can still catch it to:

- Ensure local cleanup.
- Record genuinely necessary diagnostic information.
- Adjust unpublished temporary data according to the contract.
- Attach context without altering the nature of the interruption signal.

Then **rethrow the exact same exception** if the upper layer is still allowed to receive InterruptedException.

There is no need to catch just to log and rethrow at every single layer. That approach can produce duplicate logs without adding real value. A method only needs:

~~~java
// Illustrative code inside a class with an appropriate queue variable.
static String load(BlockingQueue<String> queue)
        throws InterruptedException {
    return queue.take();
}
~~~

The signature fully expresses the interruption contract; no redundant catch is needed.

## 6. Do Not Swallow InterruptedException

A common mistake:

~~~java
// Illustrative anti-pattern.
try {
    blockingCall();
} catch (InterruptedException ignored) {
    // Continue processing as if no cancellation request ever happened.
}
doNextStep();
~~~

This is an illustrative snippet within a larger method. If blockingCall stops due to an interrupt, continuing to **doNextStep()** may perform side effects that the coordinator is trying to stop.

Another anti-pattern:

~~~java
// Illustrative anti-pattern: a loop with no exit path.
while (true) {
    try {
        process(queue.take());
    } catch (InterruptedException ignored) {
        // Swallow the signal and go right back to take().
    }
}
~~~

A blocking API typically clears the flag when throwing InterruptedException. After the exception is swallowed, the loop may go back to waiting indefinitely with a cleared flag. **Interrupt loses its ability to coordinate an exit** if code repeatedly ignores it.

If the calling API allows it:

~~~java
// Illustrative method; queue is a BlockingQueue<Task>.
static void runOne(BlockingQueue<Task> queue)
        throws InterruptedException {
    Task task = queue.take();
    task.execute();
}
~~~

Simply propagate InterruptedException from **take()**. This contextual snippet assumes a Task type with an execute method already exists; it is not a standalone runnable program.

If the code is not allowed to declare checked exceptions and has no full handling policy at that spot, the standard approach is to restore the flag and stop:

~~~java
// Inside a Runnable or callback that does not declare InterruptedException.
try {
    blockingCall();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Using **return** here ends the current task after restoring the flag, which is different from **return inside finally** that can mask exceptions. If there are resources requiring cleanup, cleanup must be structured so that it still runs before the task exits.

## 7. Why Not Re-Interrupt at Every Layer When Throwing?

Consider the following chain:

~~~java
// Illustrates a method with a throws InterruptedException contract.
static void service() throws InterruptedException {
    try {
        Thread.sleep(10_000);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw e;
    }
}
~~~

This snippet is not necessarily wrong in every context, but calling **interrupt()** right before **throw e** is usually **unnecessary** if the sole goal is to report the interruption to the caller. The exception itself already carries the signal. When the upper layer receives the error and intends to perform cleanup involving blocking operations, a prematurely restored interrupt flag may cause that cleanup operation to be interrupted immediately. The upper layer's contract should decide when to handle the flag.

A simpler approach:

~~~java
// Illustrates a method with a throws InterruptedException contract.
static void service() throws InterruptedException {
    Thread.sleep(10_000);
}
~~~

If you need to catch to clean up, you can still preserve the original exception:

~~~java
// Illustrative; releaseLocalState() must follow its own contract.
try {
    blockingOperation();
} catch (InterruptedException e) {
    releaseLocalState();
    throw e;
}
~~~

Note: if **releaseLocalState()** also throws an exception, it can mask InterruptedException. For cleanup that might throw, use an appropriate mechanism to preserve the primary exception, such as **try-with-resources** for AutoCloseable or suppressed exceptions when handling manually. Do not focus solely on writing **throw e** while overlooking the impact of the cleanup path.

## 8. Preserve the InterruptedException Type and Stack Trace

When propagating:

- **throw e** rethrows the exact object that was caught and preserves the information on that exception.
- **throws InterruptedException** on the signature informs the caller of the checked exception type that may occur.
- Do not create **new InterruptedException(e.getMessage())** without a special reason: doing so creates a new object and does not automatically preserve the full cause, suppressed exceptions, and stack trace of the original exception.
- Do not wrap it in a generic RuntimeException when the signature can propagate it as-is; callers may no longer be able to catch InterruptedException as expected.

In a service interface where multiple implementations need to support interruption, including InterruptedException in the signature can be a sound decision. If it is a public API that does not allow checked exceptions, a documented conversion policy is needed; avoid hiding the interruption behind an unrelated business message.

### If You Want to Add Context

You do not always need to create a new exception. Context can be logged at an orchestration boundary, keeping the Throwable intact and letting the upper layer decide. If the API forces wrapping, you must:

1. Restore the interrupt flag if InterruptedException is no longer propagated directly by contract.
2. Preserve the original as the **cause** when the wrapper type supports it.
3. Ensure the caller understands that the wrapper represents an interruption, not a normal business failure.
4. Avoid automatically retrying non-idempotent operations.

Example conversion in a callback that does not declare checked exceptions:

~~~java
// Illustrative code in a callback that does not declare checked exceptions.
try {
    blockingOperation();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Operation interrupted", e);
}
~~~

This is an API policy that can be used in some cases, but it does not mean **IllegalStateException** is the standard cancellation type or that every callback should behave this way. If the API provides a more appropriate exception or cancellation type, prefer that API's contract. Some callbacks should exit normally after recording a canceled status instead of throwing an unchecked exception.

## 9. Runnable Differs from Callable in Exception Contract

**Runnable.run()** does not declare checked exceptions. Therefore, a Runnable lambda or method reference cannot simply call an API that throws InterruptedException and let that exception pass through **run()** without catching or converting it appropriately.

~~~java
// Illustrates a Runnable inside a method.
Runnable task = () -> {
    try {
        Thread.sleep(10_000);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return;
    }
};
~~~

Meanwhile, **Callable<V>.call()** is declared with **throws Exception**, so a Callable can let InterruptedException propagate out:

~~~java
// Illustrates a Callable in context.
Callable<String> task = () -> {
    Thread.sleep(10_000);
    return "done";
};
~~~

However, when submitting a Callable via **ExecutorService.submit()**, an external caller usually does not receive the InterruptedException *thrown by the worker* directly when calling **Future.get()**. If the task fails with InterruptedException and the Future has not been canceled, **Future.get()** typically throws **ExecutionException** whose **getCause()** is InterruptedException.

You must distinguish between these cases:

| Situation | Signal received by the Future.get() caller |
| --- | --- |
| **The thread calling get() itself** is interrupted while waiting | **InterruptedException** directly |
| **The worker's Callable** throws InterruptedException and the Future completes abnormally | **ExecutionException**, with InterruptedException as its cause |
| The Future has already transitioned to the canceled state | **CancellationException** |
| A get(timeout) call expires | **TimeoutException** |

Therefore, do not assume every InterruptedException observed in asynchronous code involves the same thread. There are two distinct actors: **the waiting caller** and **the executing worker**.

### CompletableFuture

**CompletableFuture.supplyAsync** takes a **Supplier<T>**, whose **get()** method does not declare throws InterruptedException. Thus, the supplier lambda must catch it or use an adapter according to a cancellation policy. **CompletableFuture.get()** and **join()** also have different waiting/exception contracts: get declares InterruptedException, whereas join does not declare checked InterruptedException.

Do not assume that **CompletableFuture.cancel(true)** necessarily interrupts a running supplier. CompletableFuture uses its own completion state, and the **mayInterruptIfRunning** parameter does not control computation in the same way a standard FutureTask does. If you need to genuinely interrupt work, manage the underlying Future/task or an appropriate cancellation token separately.

## 10. Do Not Equate InterruptedException with CancellationException

**InterruptedException** indicates that an interruptible wait operation on the current thread was interrupted. **CancellationException** describes the canceled state of a Future object or asynchronous result. Calling cancel(true) on a Future may cause the executor mechanism to send an interrupt to the worker, but the two exceptions still appear in different places and carry different meanings.

A Future may already be canceled and **get()** may throw CancellationException even before the worker finishes handling the interrupt. Conversely, a thread may be interrupted while calling Future.get() while the task continues running, causing the caller to receive InterruptedException while the Future is not yet canceled.

**TimeoutException**, on the other hand, describes a timed wait that has expired; it does not automatically interrupt the caller or cancel the Future. Only the application decides whether to keep waiting, return a fallback, send a cancellation request, or end the request.

When propagating InterruptedException upward, the caller should evaluate whether related subtasks must also be canceled. That is a policy of the work group, not an automatic side effect of the **throws** keyword.

## 11. Cleanup When Propagating Interruption

When an interruption occurs in the middle of an operation holding resources, the code must still ensure proper cleanup. A **try/finally** block allows cleanup to run as the exception propagates upward:

~~~java
// Illustrative: lock is declared and can be acquired via lockInterruptibly().
lock.lockInterruptibly();
try {
    blockingOperation();
} finally {
    lock.unlock();
}
~~~

The key point is that **lock.lockInterruptibly()** is placed before the try block. If acquiring the lock is interrupted and throws InterruptedException, the thread has not acquired the lock along the success path, and the code must not call unlock as though it held the lock. Once acquired successfully, finally is responsible for calling unlock when the try body finishes or throws an error.

An error-prone anti-pattern:

~~~java
// Illustrative anti-pattern; do not use in real programs.
try {
    lock.lockInterruptibly();
    blockingOperation();
} finally {
    lock.unlock(); // May unlock without ever having locked successfully.
}
~~~

If lockInterruptibly fails before acquiring the lock, unlock can throw **IllegalMonitorStateException**, masking the original InterruptedException. Place the cleanup scope after the resource or lock has been successfully acquired, or explicitly track whether acquisition succeeded.

### Cleanup Can Fail on Its Own

If the main logic throws InterruptedException and closing or rolling back inside finally throws a new exception, the cleanup exception can mask the interrupt signal. For **AutoCloseable** resources, prefer **try-with-resources**, because close errors are attached as **suppressed** exceptions when the try body has already thrown a primary exception.

~~~java
// Illustrative: resource is AutoCloseable.
try (var resource = openResource()) {
    resource.blockingAction(); // May throw InterruptedException.
}
~~~

This snippet needs to sit within an appropriate API context; it is purely illustrative code. To let InterruptedException propagate intact, the caller or enclosing method must accept that checked exception type, along with any other checked exceptions that close may throw according to the resource's contract.

**Cleanup is not automatic rollback.** Releasing a lock does not revert a modified mutable object; closing a stream does not erase bytes already written; canceling a wait does not prove a remote request produced no side effects. When interruption occurs, rules for preserving state and transactions still need to be designed separately.

## 12. Keeping State Consistent When Interrupted Mid-Operation

Propagating the right InterruptedException type only solves control flow and cancellation signaling. If code modifies data before calling a blocking operation, the state may end up partially updated:

~~~java
// Illustrative anti-pattern: entries is an already-published mutable list.
entries.add(item);
remoteGate.await(); // May throw InterruptedException.
commitOtherFields();
~~~

If remoteGate.await is interrupted, the list already has the item added while the other updates have not completed. To maintain strong state consistency, you can:

1. Validate conditions and prepare new data in local variables or a private snapshot.
2. Perform wait operations or computations that may throw InterruptedException before publishing.
3. Commit only when all conditions are satisfied and publishing the result is still permitted.
4. If the operation has already sent external side effects, apply an appropriate transaction, idempotency, or compensation workflow.

Illustrative code:

~~~java
// Contextual method illustration; not a standalone program.
Snapshot candidate = prepareCandidate(current);
remoteGate.await();  // If interrupted, current remains unchanged.
current = candidate;  // Commit after preparation succeeds.
~~~

This only provides guarantees within the scope of state that **current** actually owns and controls. If preparing candidate also mutates shared mutable objects or remoteGate causes external side effects, the final assignment does not turn the entire system into an atomic transaction.

In addition, there can be a race between checking the interrupt flag and committing: an interrupt request may arrive right after the check. The system must define what point counts as committed and how much cancellation it promises; it cannot arbitrarily guarantee that *every interrupt arriving at any instant* will prevent all side effects.

## 13. Interruption in Worker Loops

A worker running multiple units of work should have a clear exit path:

~~~java
// Illustrates worker logic; not a standalone program.
static void consume(BlockingQueue<Job> queue)
        throws InterruptedException {
    while (true) {
        Job job = queue.take();
        job.process();
    }
}
~~~

Here **queue.take()** can throw InterruptedException. If the calling layer allows it, the exception exits **consume()**, thereby terminating the loop. There is no need to catch InterruptedException and **continue**: doing so can cause the worker to ignore the interruption request.

However, if **job.process()** is long-running CPU-bound work or uses non-interruptible I/O, the interruption signal might not be handled during that time. You can design explicit check points:

~~~java
// Contextual illustration; not a standalone program.
while (!Thread.currentThread().isInterrupted()) {
    doSmallUnitOfWork();
}
~~~

The **isInterrupted()** condition only checks the flag; it does not throw InterruptedException on its own. If the worker's contract requires signaling interruption via a checked exception, you need to choose an appropriate point to translate the signal or use interruptible APIs; do not construct InterruptedException arbitrarily without well-defined semantics.

### When a Loop Must Stop but Cleanup Is Mandatory

A worker may have a finally block to release a connection or lock after the loop ends. When an interruption throws up through the layers, finally runs on the exit path under normal execution conditions. If cleanup needs to perform a new blocking operation, you must consider whether the flag has been cleared and whether cleanup has its own timeout policy. Avoid blocking indefinitely during cancellation-path cleanup.

## 14. Interruption in ExecutorService

When a task is submitted to an ExecutorService:

- **Future.cancel(true)** may attempt to interrupt a running task if the executor and task allow it.
- **ExecutorService.shutdownNow()** attempts to interrupt executing workers, though it does not guarantee every task stops immediately.
- **ExecutorService.shutdown()** does not send interrupts to all accepted tasks the way shutdownNow does.
- **awaitTermination(timeout, unit)** is a call that can throw InterruptedException on the thread waiting for the executor to finish.

If the thread managing the executor is interrupted while waiting for shutdown, an appropriate policy may be to stop waiting, call shutdownNow when it genuinely owns the executor, and then restore the flag or rethrow InterruptedException. You must not shut down a shared executor just because a single request's caller was interrupted when that layer does not own the executor's lifecycle.

Illustrative example at a boundary managing an owned executor:

~~~java
// Illustrative code; the executor is owned by this scope.
executor.shutdown();
try {
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        executor.shutdownNow();
    }
} catch (InterruptedException e) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
~~~

This is a policy for a context that **does not continue throwing InterruptedException** and has the authority to stop the executor. If the method allows **throws InterruptedException**, you can replace the boundary by rethrowing after appropriate cleanup. Do not apply this mechanically to a server's shared thread pool.

## 15. APIs That Disallow Checked Exceptions: Responsible Conversion

Some interfaces do not declare checked exceptions, such as **Runnable**, **Supplier**, certain callbacks, or overridden methods constrained by their signature. You cannot add **throws InterruptedException** to an overridden method if the interface does not permit it.

In such cases, common options include:

- **Restoring the interrupt flag and ending the work** when interruption means a request to stop.
- **Converting to an unchecked exception with a clear cause** when the framework needs an abnormal failure path and the contract allows it.
- **Recording a canceled status in the business result** if the API is designed to represent cancellation with a dedicated state.
- **Using an external wrapper/adapter** to place the blocking operation inside an interface that can declare checked exceptions, such as Callable when appropriate.

There is no single universally right option for every callback. However, **catching and ignoring** is usually wrong because it makes the interruption signal disappear.

When converting to an unchecked exception, do not use an ambiguous exception that causes the system to retry unconditionally. The caller or framework needs to recognize that the reason is interruption/cancellation to make the right operational decision. Also, resetting the interrupt flag must account for the thread pool contract; do not proceed to run subsequent blocking operations as if the flag had been cleared.

## 16. How to Test InterruptedException Propagation

A good test must verify both the **exception propagation path** and the **behavior of the thread owning the task**. You should not just call Thread.sleep with a guessed number and hope a thread has reached the right blocking point.

Prefer using **CountDownLatch**, barriers, or synchronization utilities to control timing:

1. Create a **ready** latch indicating the thread has started.
2. Keep a **gate** latch closed so the wait operation cannot succeed yet.
3. Once ready is signaled, call **interrupt()** on the exact thread under test.
4. Let the exception propagate through the low-level and service methods via **throws InterruptedException**.
5. At a boundary that does not declare checked exceptions, record the exception, restore the flag according to contract, and exit.
6. **join()** the thread to verify it is no longer running; in production test suites, use a safe timeout to avoid hanging the suite if the code has a bug.
7. Assert that no side effects occurred after interruption, mandatory cleanup ran, and data only changed within the committed scope.

In the runnable program above, the ready/gate latches eliminate scheduler dependency: whether the interrupt happens before or during the await call, it leads to InterruptedException on the worker. The **Repository cleanup** line confirms finally ran; the **Service propagates interruption** line shows the service layer rethrew; the two **Flag** lines show the status when caught and after restoration.

### Test Cases to Include

| Case | Expectation |
| --- | --- |
| Low-level layer interrupted during await | InterruptedException is thrown |
| Middle layer declares throws and does not swallow | Caller receives InterruptedException |
| Middle layer catches then executes throw e | Caller still receives the exact original exception |
| Middle layer catches then continues | Test detects the task did not stop per contract |
| Runnable boundary cannot throw | Flag is restored if policy chooses re-interrupt; task exits |
| Worker Callable throws InterruptedException | Future.get typically throws ExecutionException with InterruptedException as cause |
| Caller interrupted during Future.get | Caller receives InterruptedException directly |
| Cleanup in finally runs | Resources are cleaned up per contract |
| Cleanup also throws an error | Primary is not masked; suppressed is appropriate |
| Interrupt near commit point | Application preserves proper semantics for commit timing and side effects |

If you are using a unit test framework, you can check exception identity to detect a layer accidentally creating a new exception. In integration tests, check resource states and actual side effects, not just the Throwable type.

## 17. Common Mistakes and Fixes

**Swallowing InterruptedException and continuing.** This is the core mistake: the cancellation request is no longer reflected and the task may perform additional side effects. If allowed, declare throws and propagate; if not allowed, use an appropriate flag-restoration and exit policy.

**Resetting the interrupt flag at every layer even when throwing.** Usually unnecessary when the caller already receives InterruptedException properly. Let the work-ownership boundary decide how to handle the flag.

**Confusing isInterrupted with Thread.interrupted.** The static Thread.interrupted method checks and clears the current thread's flag; using it to "just peek" can accidentally consume the signal.

**Converting interruption into a generic business error without a cause.** Callers lose the ability to distinguish stopping a task from a data-processing error. If you must wrap, preserve the cause and interrupt-flag policy.

**Assuming Future.get throwing InterruptedException means the worker was interrupted.** It may just be the waiting caller thread that was interrupted. Worker failures are typically wrapped in ExecutionException when observing an uncanceled Future.

**Using CompletableFuture cancellation to assert the supplier stopped.** Future state and whether the executing worker actually stopped are two different concepts; a concrete cancellation mechanism is needed.

**Calling unlock when lockInterruptibly has not succeeded.** If acquisition is interrupted, calling unlock erroneously throws IllegalMonitorStateException and can mask the original error. Place try/finally after acquiring the lock successfully.

**Letting cleanup throw and lose InterruptedException.** For AutoCloseable resources, prefer try-with-resources; for manual cleanup, preserve primary and suppressed exceptions.

**Assuming interruption rolls back data.** Interrupt is only a signal; side effects in RAM, files, databases, or networks require their own state-preservation strategy.

**Relying on Thread.sleep to create race tests.** The scheduler can vary. Use latches or barriers to control waiting conditions and verify outcomes permitted by the contract.

## 18. Checklist When Writing Interruptible Methods

Before finalizing a blocking Java snippet or an API chain with cancellation, ask yourself:

1. Is this method allowed to declare **throws InterruptedException**?
2. Does the current layer have enough authority to decide task cancellation, or should it let the exception propagate upward?
3. If catching the exception, does it genuinely add valid handling before **throw e**?
4. Does any catch swallow the interrupt, continue a loop, or retry automatically?
5. When a blocking API throws InterruptedException, does it clear the flag per contract?
6. If a checked exception cannot be thrown, how will the boundary restore the flag, return a canceled status, or convert to another exception?
7. Have you distinguished an interrupted worker from an interrupted caller thread of Future.get?
8. Can any cleanup throw another exception and mask the interrupt error?
9. If interruption occurs after side effects, is state still consistent and are necessary rollback/compensation mechanisms in place?
10. Do tests trigger the interrupt at the actual waiting point, verifying both exception propagation and worker exit?

**Conclusion:** When API signatures permit, **propagating InterruptedException as-is** is a clean way to preserve the stop-request signal and delegate work-lifecycle decisions to the responsible layer. There is no need to catch and restore the flag at every intermediate layer. At boundaries where checked exceptions cannot be thrown, there must be a clear policy to preserve the meaning of interruption, clean up resources, and exit safely. Interruption is a coordination signal, while preserving state and managing side effects must always be designed and verified separately.
