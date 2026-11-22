# Relationship Between the Interrupt Flag and Interruptible Waiting Methods in Java

## 1. Learning Objectives

After this lesson, you will be able to:

- Understand that an interrupt is a **cooperative request signal** to a running thread, not a command that forcefully terminates the thread.
- Distinguish between <code>thread.interrupt()</code>, <code>thread.isInterrupted()</code>, and <code>Thread.interrupted()</code>, especially the **interrupt-flag-clearing** effect of the last method.
- Explain what happens when a thread waiting in <code>Thread.sleep()</code>, <code>Object.wait()</code>, <code>Thread.join()</code>, <code>BlockingQueue.take()</code>, <code>Condition.await()</code>, or <code>Lock.lockInterruptibly()</code> receives an interrupt.
- Know that waiting methods that throw <code>InterruptedException</code> typically **clear the interrupt flag when throwing the exception**; choosing to propagate the exception or restore the flag must match the method's contract.
- Write safe waiting and cancellation code that avoids infinite spin loops, never releases an unowned lock, and does not accidentally swallow cancellation requests.
- Verify interrupt behavior yourself through Java 17+ programs with deterministic results.

## 2. What Is the Interrupt Flag?

Every <code>Thread</code> in Java has an interruption state (commonly called the **interrupt flag** or *interrupted status*). When a thread calls <code>target.interrupt()</code>, it sends an interrupt signal to <code>target</code>.

Normally, if <code>target</code> is running computational code that does not check the flag, the code **does not stop automatically**. If the thread is waiting in a method whose contract responds to interrupts, the waiting call may terminate with <code>InterruptedException</code>, or another form of response defined by that API.

Intuitive example:

~~~text
Coordinator thread                  Worker thread
       |                                  |
       |                           working / waiting
       |                                  |
       +---- worker.interrupt() --------->|
                                          |
                            API checks interrupt status
                                          |
                         +----------------+----------------+
                         |                                 |
                  interruptible wait               computational task
                         |                                 |
             InterruptedException                 must actively check
              and usually clears flag                isInterrupted()
                         |                                 |
             catch/propagate/restore               decide to stop
               according to contract             according to contract
~~~

The interrupt flag should not be treated as a <code>boolean</code> variable that the application arbitrarily sets and clears. Java provides APIs to send and observe that state. Nor should an interrupt be interpreted as an exception "thrown directly from thread A to thread B": <code>interrupt()</code> is a **signal**, and whether an exception is thrown is decided by the API running in the receiving thread.

### A RUNNABLE Thread Can Ignore an Interrupt

~~~java
while (true) {
    doCpuWork();
}
~~~

This is **illustrative code**; <code>doCpuWork()</code> merely represents computation. If the loop does not check the interrupt status and the work does not call an API that responds to interrupts, calling <code>thread.interrupt()</code> from another thread does not force the loop to stop.

Cooperative pattern:

~~~java
while (!Thread.currentThread().isInterrupted()) {
    doCpuWork();
}
~~~

This is also **illustrative code** assuming an existing <code>doCpuWork()</code> method. Checking the flag allows the loop to choose to stop at an appropriate point. If the actual work performs data writes, it must still release resources and preserve state invariants before terminating.

## 3. Three Important APIs: Signaling, Checking, and Consuming the Flag

| Expression | Effect | Does it clear the interrupt flag? |
| --- | --- | --- |
| <code>target.interrupt()</code> | Requests interruption of thread <code>target</code>; outcome depends on waiting state/API | Not an API for clearing the flag |
| <code>target.isInterrupted()</code> | Reads the interrupt status of the specified thread object | **No** |
| <code>Thread.interrupted()</code> | Reads the interrupt status of the **calling thread** | **Yes**: returns the previous status and clears it |
| <code>Thread.currentThread().interrupt()</code> | Sends an interrupt signal to the **current thread itself**; often used to restore the flag after catching | Sets the interrupt signal, does not clear it |

**Common point of confusion:** <code>Thread.interrupted()</code> is a **static** method. It always checks the flag of the **current thread**, regardless of which thread object you might try to invoke it on. To observe the status of a specific <code>Thread</code> object without clearing the flag, use <code>target.isInterrupted()</code>.

A non-destructive read of the status:

~~~java
boolean requested = Thread.currentThread().isInterrupted();
~~~

A read that simultaneously **consumes** the status:

~~~java
boolean wasInterrupted = Thread.interrupted();
~~~

If <code>Thread.interrupted()</code> returns <code>true</code>, a subsequent read immediately afterward will usually return <code>false</code> if no new interrupt has arrived. This directly affects subsequent waiting APIs: they may no longer see the cancellation request that was just cleared.

### Java 17+ Example: Observing How the Flag Changes

Save the file **InterruptFlagDemo.java**:

~~~java
public class InterruptFlagDemo {
    public static void main(String[] args) {
        Thread current = Thread.currentThread();

        current.interrupt();
        System.out.println("Sau interrupt(): " + current.isInterrupted());

        try {
            Thread.sleep(1_000);
            System.out.println("Sleep hoàn tất");
        } catch (InterruptedException e) {
            System.out.println("Sleep ném InterruptedException");
            System.out.println("Cờ trong catch: " + current.isInterrupted());
        }

        current.interrupt();
        System.out.println("Trước interrupted(): " + current.isInterrupted());
        System.out.println("Thread.interrupted(): " + Thread.interrupted());
        System.out.println("Sau interrupted(): " + current.isInterrupted());
    }
}
~~~

Compile and run with Java 17 or newer:

~~~bash
javac -encoding UTF-8 InterruptFlagDemo.java
java InterruptFlagDemo
~~~

Stdout output in a typical run:

~~~text
Sau interrupt(): true
Sleep ném InterruptedException
Cờ trong catch: false
Trước interrupted(): true
Thread.interrupted(): true
Sau interrupted(): false
~~~

**Step-by-step explanation:**

1. <code>current.interrupt()</code> sets the interrupt flag on the <code>main</code> thread itself, because <code>current</code> refers to <code>Thread.currentThread()</code>.
2. <code>Thread.sleep(1_000)</code> sees that the current thread has been interrupted and throws <code>InterruptedException</code> instead of sleeping for the full requested duration.
3. By the contract of <code>Thread.sleep()</code>, the **interrupted status is cleared when that exception is thrown**. Therefore, inside <code>catch</code>, <code>current.isInterrupted()</code> returns <code>false</code> if no new interrupt occurred.
4. The program intentionally sets the flag again to demonstrate <code>Thread.interrupted()</code>.
5. <code>Thread.interrupted()</code> returns <code>true</code> and simultaneously clears the flag, so the final <code>isInterrupted()</code> call returns <code>false</code>.

The example intentionally does not restore the flag in the first <code>catch</code> block to clearly show the contract of <code>sleep()</code>. In production code, the decision to restore or propagate <code>InterruptedException</code> must follow the rules in the later sections.

## 4. InterruptedException and Interrupt Status Are Two Different Signaling Channels

<code>InterruptedException</code> is a **checked exception**. Several waiting methods use it to report that an interrupt request interrupted the wait operation.

A typical sequence:

~~~text
Flag = false
   |
   | Another thread calls interrupt()
   v
Flag = true
   |
   | Thread calls an interruptible waiting method
   v
Method detects interrupt
   |
   | throws InterruptedException
   v
Flag = false (per the contract of standard waiting methods discussed)
   |
   +--> catch: propagate the exception upward
   |
   +--> catch: restore the flag and exit the operation
   |
   +--> catch: handle according to a special contract
~~~

The key point is that **an exception already carries the information "the operation was interrupted" even if the interrupt flag at the time of catching is <code>false</code>**. If code only inspects the flag after catching and ignores the <code>InterruptedException</code> object, it may wrongly conclude that there was no cancellation request.

According to the Java documentation, <code>InterruptedException</code> is usually accompanied by clearing the interrupted status when thrown, but always check the contract of the specific API. Do not apply this rule to **every API with "interrupt" in its name or behavior**: for example, <code>LockSupport.park()</code> responds by returning without clearing the flag the way <code>Thread.sleep()</code> does.

If a new interrupt arrives **after** the method has thrown the exception but before the code checks the flag, the observed status can also change. The standalone examples below control the number of signals so the results are easy to understand; real-world multithreaded code needs to account for the possibility of multiple interrupt requests.

## 5. Common Waiting Methods and Their Response to Interrupts

| API | When interrupted while waiting | Key things to remember |
| --- | --- | --- |
| <code>Thread.sleep(...)</code> | Throws <code>InterruptedException</code>, clears the flag per contract | Does not automatically release any lock/monitor held by the thread |
| <code>Object.wait(...)</code> | Throws <code>InterruptedException</code>, clears the flag per contract | Must only be called while owning the monitor; temporarily releases and reacquires the monitor before exiting |
| <code>Thread.join(...)</code> | The **joining thread** may receive <code>InterruptedException</code> and have its flag cleared | Does not mean the joined thread was interrupted or has terminated |
| <code>BlockingQueue.take()</code> | May throw <code>InterruptedException</code> while waiting for an element | Do not turn this into a valid element result; terminate/handle properly |
| <code>BlockingQueue.put(...)</code> | May throw <code>InterruptedException</code> while waiting for space | For bounded queues, verify consistency of the producer thread |
| <code>Condition.await()</code> | May throw <code>InterruptedException</code> | Releases and reacquires the lock associated with the Condition before the method exits per contract |
| <code>Lock.lockInterruptibly()</code> | May throw <code>InterruptedException</code> before acquiring the lock | If the lock was not acquired, **do not call <code>unlock()</code>** |
| <code>Lock.tryLock(timeout, unit)</code> | May throw <code>InterruptedException</code> while waiting | Only call <code>unlock()</code> after receiving a successful lock acquisition result |
| <code>CountDownLatch.await()</code>, <code>Semaphore.acquire()</code> | Interruptible waiting calls | Must maintain conventions for results/permits and task cancellation |

The table describes the typical behavior of standard Java APIs. A waiting method may complete due to a normal condition, timeout, a new element, or an interrupt; the exact outcome is governed by each method's contract. Do not infer from a method's name that all waiting calls respond the same way.

### Not All Waiting Methods Follow the Same Pattern

- <code>ReentrantLock.lock()</code> acquires the lock in a way that **cannot be canceled by <code>InterruptedException</code> while waiting**; if interrupted while waiting, it continues waiting and preserves/restores the interrupt status per its contract.
- <code>ReentrantLock.lockInterruptibly()</code> allows canceling the wait via <code>InterruptedException</code>.
- <code>Condition.awaitUninterruptibly()</code> does not throw <code>InterruptedException</code> from interrupts while waiting; it continues waiting until the wakeup condition is satisfied per its contract, while preserving the interrupt status so the caller can observe it after returning.
- <code>LockSupport.park()</code> can return due to an interrupt **without clearing the interrupt flag** and without throwing <code>InterruptedException</code> the way <code>sleep()</code> does.

Therefore, the relationship between the flag and waiting behavior is **the contract of the waiting API**, not a JVM rule that "every blocking call throws an exception."

## 6. Thread.sleep(): Receives Interrupts but Does Not Release Locks

<code>Thread.sleep</code> is a static method that pauses execution of the **current thread** for the requested duration, unless interrupted or another condition specified by the API occurs.

Two very important points:

1. When interrupted during sleep, the method throws <code>InterruptedException</code> and clears the interrupt flag per its contract.
2. <code>sleep()</code> **does not automatically release any monitor or Lock** owned by the thread.

Illustrative example in a class that has <code>monitor</code>:

~~~java
synchronized (monitor) {
    Thread.sleep(1_000);
}
~~~

The snippet above is **not a standalone Java program**, and its enclosing method must handle or declare <code>InterruptedException</code>. The thread holds the monitor while sleeping. If sleep is interrupted, before exiting the <code>synchronized</code> block, control flow follows Java's block-exit semantics; the monitor is released **because execution exits the synchronized block**, not because <code>sleep()</code> released it when starting to wait.

Similarly:

~~~java
lock.lock();
try {
    Thread.sleep(1_000);
} finally {
    lock.unlock();
}
~~~

This is **illustrative code** with a <code>lock</code> variable of type <code>Lock</code> and a method with an appropriate checked-exception contract. If <code>sleep()</code> throws an exception, <code>finally</code> releases the lock. Holding a lock while sleeping generally increases the time other threads must wait and should be reconsidered in design.

## 7. Object.wait(): Temporarily Releases the Monitor and Reacquires It Before Exiting

<code>Object.wait()</code> must only be called when the current thread **owns the monitor** of the object being waited on, typically inside <code>synchronized (monitor)</code>. If it does not own the monitor, the call may throw <code>IllegalMonitorStateException</code>.

Illustrative snippet:

~~~java
synchronized (monitor) {
    while (!ready) {
        monitor.wait();
    }
    consume();
}
~~~

The variables <code>monitor</code>, <code>ready</code>, and the method <code>consume()</code> are illustrative components. The enclosing method must handle or declare <code>InterruptedException</code>.

Unlike <code>sleep()</code>, <code>wait()</code> **temporarily releases the monitor of the waited-on object**, allowing another thread to enter the synchronized region to update the condition and call <code>notify()</code>/<code>notifyAll()</code>. Before <code>wait()</code> returns or throws <code>InterruptedException</code>, the thread must reacquire that monitor according to the API semantics.

A thread can wake up due to a signal, a timeout (if using a timed overload), an interrupt, or a *spurious wakeup*. Therefore, the condition must be checked in a **<code>while</code> loop**, never assuming a single <code>if</code> check is enough before proceeding.

When interrupted while waiting:

- <code>wait()</code> throws <code>InterruptedException</code> after the required monitor reacquisition step.
- The interrupted status is cleared when the exception is thrown.
- If the code lets the exception exit the <code>synchronized</code> block, the monitor is released according to synchronized-region exit rules.
- If the code catches the exception **directly inside** the synchronized region, at the moment of catching it still owns the monitor; it must decide to exit the block or handle it without holding the monitor for too long.

**Do not equate** "wait released the monitor while waiting" with "after catching, the monitor is no longer held." Those are two different points in time.

## 8. Thread.join(): Interrupts the Waiting Thread, Not the Target Thread

Consider:

~~~java
Thread worker = new Thread(() -> compute());
worker.start();
worker.join();
~~~

This is **illustrative code**, assuming <code>compute()</code> exists and the calling method handles or declares <code>InterruptedException</code>.

Calling <code>worker.join()</code> causes the **thread calling join** to wait for <code>worker</code> to finish. If the joining thread is interrupted, the <code>join()</code> call itself may throw <code>InterruptedException</code>; that **does not prove** <code>worker</code> has finished, nor does it automatically call <code>worker.interrupt()</code>.

Therefore, the managing thread's handler needs to decide the policy:

- Stop waiting and report that the management task was canceled.
- Propagate <code>InterruptedException</code> to the coordination layer if the signature allows it.
- If cleanup responsibilities require waiting for the worker to finish, design an explicit cancel/wait procedure rather than silently swallowing interrupts or waiting indefinitely.

Do not write a loop like <code>while (worker.isAlive()) worker.join()</code> that ignores every <code>InterruptedException</code> if the system is meant to support cancellation. That turns an interrupt request into an ignored signal.

## 9. BlockingQueue.take(): Java 17+ Program with an Interrupt from Another Thread

<code>BlockingQueue.take()</code> waits for an available element. When the queue is empty, the worker may block; if it receives an interrupt per its contract, the waiting call throws <code>InterruptedException</code> and the worker must decide how to handle the cancellation request.

The example below uses an empty <code>LinkedBlockingQueue</code> and a <code>CountDownLatch</code> to coordinate ordering. The synchronization condition intentionally **does not depend** on the exact moment the worker enters the parked/blocked state: if the interrupt arrives right before <code>take()</code> begins, this interruptible operation still receives the signal.

Create the file **InterruptibleQueueDemo.java**:

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;

public class InterruptibleQueueDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new LinkedBlockingQueue<>();
        CountDownLatch ready = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            ready.countDown();

            try {
                String item = queue.take();
                System.out.println("Worker nhận: " + item);
            } catch (InterruptedException original) {
                System.out.println("Worker nhận InterruptedException");
                System.out.println("Cờ sau khi catch: "
                        + Thread.currentThread().isInterrupted());

                Thread.currentThread().interrupt();
                System.out.println("Cờ sau khi restore: "
                        + Thread.currentThread().isInterrupted());
            }
        }, "queue-worker");

        worker.start();
        ready.await();

        worker.interrupt();
        worker.join();

        System.out.println("Worker đã kết thúc: " + !worker.isAlive());
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac -encoding UTF-8 InterruptibleQueueDemo.java
java InterruptibleQueueDemo
~~~

Stdout of the example (when no other source sends an interrupt):

~~~text
Worker nhận InterruptedException
Cờ sau khi catch: false
Cờ sau khi restore: true
Worker đã kết thúc: true
~~~

Analysis:

1. <code>queue</code> starts empty and no code adds any elements. Thus <code>take()</code> cannot complete by receiving an element.
2. <code>ready.countDown()</code> allows <code>main</code> to send the interrupt after the worker has started. It **does not prove** the worker has completely entered the waiting state; the example does not require that for a correct result.
3. <code>worker.interrupt()</code> causes the <code>take()</code> call—whether already waiting or about to wait—to respond with <code>InterruptedException</code>.
4. Upon entering <code>catch</code>, the worker's interrupt status has already been cleared by <code>take()</code>'s interrupt handling, so it prints <code>false</code>.
5. The worker restores the flag with <code>Thread.currentThread().interrupt()</code> to preserve the signal for any upstream management code; it prints <code>true</code>.
6. The lambda finishes, and <code>main</code> uses <code>join()</code> to wait until the worker has actually stopped before printing the final line.

**Do not misinterpret this:** restoring the flag to <code>true</code> does not keep the worker "alive" or make it go back to waiting. In the example, the worker terminates because execution exited the lambda. The decision to terminate comes from application logic.

### Why Not Catch and Immediately Loop Again?

An error-prone pattern:

~~~java
while (true) {
    try {
        process(queue.take());
    } catch (InterruptedException ignored) {
        // Loop immediately, acting as if there were no cancellation request.
    }
}
~~~

This snippet is **intentionally flawed illustrative code**, assuming <code>queue</code> and <code>process()</code> exist. It silently discards the interrupt request. For a worker serving a system with an interrupt-based shutdown policy, the loop can cause the task to keep running after a stop signal was sent.

If you catch and **restore the flag yet still loop again**, some interruptible waiting APIs will immediately throw <code>InterruptedException</code> on the next iteration, potentially causing a tight CPU-consuming spin loop. Therefore, when you want to honor a cancellation request, you usually need to **exit the loop or propagate the exception**, not merely restore the flag and continue indefinitely.

## 10. Two Valid Strategies in catch: Propagate or Restore

### Approach A — Propagate InterruptedException to the Caller

If the method is allowed to declare the checked exception, the simplest approach is usually to **let <code>InterruptedException</code> propagate**:

~~~java
String awaitNextItem(BlockingQueue<String> queue)
        throws InterruptedException {
    return queue.take();
}
~~~

This snippet is **illustrative code inside a class with appropriate imports**, not a standalone program. The caller directly receives the reason the wait was interrupted and is responsible for deciding whether to cancel or continue.

When simply propagating the exception immediately, do not mechanically catch and call <code>Thread.currentThread().interrupt()</code> without a clear reason. The checked-exception contract already delivers the signal to the caller; higher-level code can implement its own policy.

### Approach B — Cannot Throw Checked Exception: Restore and Terminate

The <code>Runnable.run()</code> interface does not allow declaring <code>throws InterruptedException</code>. When a worker receives an interrupt during a waiting operation, a reasonable pattern is:

~~~java
@Override
public void run() {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            String task = queue.take();
            process(task);
        }
    } catch (InterruptedException original) {
        Thread.currentThread().interrupt();
    } finally {
        releaseOwnedResources();
    }
}
~~~

This is **illustrative code inside a class implementing Runnable** that has suitable <code>queue</code>, <code>process(...)</code>, and <code>releaseOwnedResources()</code> members.

- Throwing from <code>take()</code> moves control flow out of the loop.
- <code>catch</code> restores the signal because the method cannot propagate the checked exception upward.
- <code>finally</code> releases resources owned by the worker.
- After <code>catch/finally</code>, <code>run()</code> exits. The code does not repeat the wait operation as if the signal never existed.

In some cases, the application contract requires **translating the failure into an unchecked exception**. In that case, pass the original exception as the cause, for example:

~~~java
catch (InterruptedException original) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Tác vụ bị ngắt", original);
}
~~~

This is only an **illustrative catch block** in an appropriate context. You should clearly decide which exception type represents task cancellation; <code>IllegalStateException</code> here illustrates the mechanism, not a mandatory naming pattern. Resetting the flag preserves the information for code that checks interrupt status, while the cause preserves the trace of the thrown <code>InterruptedException</code>.

### When Should You Not Restore?

If an API of yours **genuinely consumes the interrupt request** under a published contract, completes its recovery procedure, and decides to continue work, it may handle it under its own policy. But that must be a deliberate decision with a clear rationale, not a generic <code>catch (InterruptedException ignored)</code>.

A common case where you do not need to restore at an intermediate layer is when **propagating <code>InterruptedException</code> immediately** to the layer responsible for cancellation. There is no rule requiring every catch block to both restore the flag and throw a checked exception.

## 11. Difference Between Thread.interrupted() and isInterrupted() in a Loop

Consider:

~~~java
while (!Thread.interrupted()) {
    doWork();
}
~~~

This is **illustrative code**. It uses the static call to consume the interrupt flag. When the loop exits because <code>Thread.interrupted()</code> returned <code>true</code>, the flag has been **cleared**. This can be intentional for a component that consumes the signal, but it easily loses information that later layers need to observe.

In a worker that wants cleanup code or callers to know an interrupt request occurred, it is usually clearer to write:

~~~java
while (!Thread.currentThread().isInterrupted()) {
    doWork();
}
~~~

<code>isInterrupted()</code> does not clear the flag. Exiting the loop does not automatically clear the stop request.

If a manager needs to query the status of **another thread**, use <code>worker.isInterrupted()</code>. However, reading the flag does not prove the work has stopped, resources have been released, or the thread has terminated. To wait for completion, use an appropriate synchronization mechanism such as <code>join()</code> or a completion API.

Some libraries/frameworks may handle interrupts internally in their waiting methods. Therefore, **reading <code>false</code> later does not prove an interrupt never occurred**. For testing and observability, you need to know which API received and may have consumed the signal.

## 12. Lock.lockInterruptibly(): Interrupt Before Acquiring the Lock

<code>java.util.concurrent.locks.Lock</code> provides interruptible lock acquisition via <code>lockInterruptibly()</code>. With <code>ReentrantLock</code>, if the thread is interrupted while waiting for the lock or already has its interrupt status set upon entering the call, the method throws <code>InterruptedException</code> and clears the interrupt status per its contract.

Correct pattern:

~~~java
lock.lockInterruptibly();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
~~~

This is **illustrative code** in a method that declares/handles <code>InterruptedException</code>, with <code>lock</code> and <code>updateSharedState()</code>. <code>lockInterruptibly()</code> is placed **before** <code>try</code> so that if the call is interrupted before acquiring the lock, <code>finally</code> does not run and does not release an unowned lock.

### Standalone Java 17+ Example: Canceling While Contending for a Lock

Create the file **InterruptibleLockDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.ReentrantLock;

public class InterruptibleLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch ready = new CountDownLatch(1);

        lock.lock();
        try {
            Thread contender = new Thread(() -> {
                ready.countDown();
                try {
                    lock.lockInterruptibly();
                    try {
                        System.out.println("Contender đã lấy khóa");
                    } finally {
                        lock.unlock();
                    }
                } catch (InterruptedException original) {
                    System.out.println("Contender bị ngắt khi đợi khóa");
                    System.out.println("Cờ khi catch: "
                            + Thread.currentThread().isInterrupted());
                    Thread.currentThread().interrupt();
                    System.out.println("Cờ sau restore: "
                            + Thread.currentThread().isInterrupted());
                }
            }, "contender");

            contender.start();
            ready.await();

            contender.interrupt();
            contender.join();

            System.out.println("Main vẫn giữ khóa: "
                    + lock.isHeldByCurrentThread());
        } finally {
            lock.unlock();
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 InterruptibleLockDemo.java
java InterruptibleLockDemo
~~~

Stdout:

~~~text
Contender bị ngắt khi đợi khóa
Cờ khi catch: false
Cờ sau restore: true
Main vẫn giữ khóa: true
~~~

**Why is the result deterministic?**

- The <code>main</code> thread acquires the lock before creating the contender thread, so contender cannot acquire the lock while <code>main</code> holds it.
- <code>ready</code> ensures contender has started; the interrupt may occur just before or during <code>lockInterruptibly()</code>, and both timings lead to <code>InterruptedException</code> with this implementation.
- Contender never acquired the lock, so the <code>catch</code> branch does not call <code>unlock()</code>. Calling unlock erroneously would cause <code>ReentrantLock</code> to throw <code>IllegalMonitorStateException</code>.
- After <code>contender.join()</code> completes, <code>main</code> still owns the lock and prints <code>true</code>, and only then releases it in <code>finally</code>.

If the call were replaced with <code>lock.lock()</code>, waiting would **not throw InterruptedException under the same mechanism**. In this example, the main thread holds the lock; if main waited for contender via <code>join()</code> while contender waited on an uninterruptible lock, the program could deadlock due to a circular wait. This is why you must choose a lock-acquisition contract that matches your cancellation policy.

## 13. Condition.await(): When Interrupted, the Lock Must Be Reacquired Before Exiting

<code>Condition</code> is typically associated with a <code>ReentrantLock</code>. When a thread calls <code>condition.await()</code> while owning the lock, the call temporarily releases that lock so another thread can modify the condition and signal it.

A commonly used pattern:

~~~java
lock.lock();
try {
    while (!ready) {
        condition.await();
    }
    consume();
} finally {
    lock.unlock();
}
~~~

This is **illustrative code** with <code>lock</code>, <code>condition</code>, <code>ready</code>, and <code>consume()</code> provided by the enclosing class; the method must handle/declare <code>InterruptedException</code>.

Notes:

- <code>Condition.await()</code> can be interrupted with <code>InterruptedException</code>.
- The <code>ReentrantLock</code> will be reacquired before the <code>await()</code> call completes by throwing the exception per Condition's contract; therefore, when entering <code>finally</code>, the code still has the right to release the lock acquisition taken earlier.
- The condition must be checked in a <code>while</code> loop because a wakeup signal does not guarantee the invariant still holds when the thread reacquires the lock, and *spurious wakeups* can occur.
- If catching the exception directly inside the lock region to restore or translate the error, do not hold the lock for too long after deciding to cancel.

Unlike <code>lockInterruptibly()</code>, a thread calling <code>await()</code> **already owned the lock before waiting**. Therefore, <code>await()</code> throwing <code>InterruptedException</code> does not mean <code>unlock()</code> is unnecessary: in the standard structure, <code>finally</code> must still release the lock after it has been reacquired.

With <code>awaitUninterruptibly()</code>, interrupts do not raise <code>InterruptedException</code> to terminate waiting under this mechanism; the interrupt flag is still preserved/restored according to the implementation's contract. Do not use this variant for a task whose policy requires timely wait cancellation.

## 14. LockSupport.park(): A Case That Does Not Throw InterruptedException

<code>java.util.concurrent.locks.LockSupport.park()</code> is a low-level primitive commonly used by synchronization libraries to park threads. It can return when the thread is interrupted, but it **does not throw <code>InterruptedException</code>** and **does not clear the interrupt flag** merely because it returned due to an interrupt.

Illustration inside a method:

~~~java
java.util.concurrent.locks.LockSupport.park();
boolean interrupted = Thread.currentThread().isInterrupted();
~~~

This snippet is **illustrative code**, not a standalone runnable example, because <code>park()</code> can wait indefinitely if there is no wakeup cause. If <code>park()</code> returns because the interrupt flag is set, <code>interrupted</code> will usually be <code>true</code> until code actively consumes the flag or another mechanism changes the state.

Because the flag remains set, calling <code>park()</code> repeatedly without handling the interrupt can return immediately, creating an unwanted spin loop. Algorithms using <code>LockSupport</code> must manage waiting conditions, permits, interrupt status, and spurious wakeups themselves.

This difference underscores that **interruptible waits** come in multiple forms: throwing a checked exception and clearing the flag, returning normally with the flag preserved, or continuing to wait in uninterruptible variants.

## 15. Cooperative Cancellation: Orderly Termination

An interrupt request often appears when a system wants to stop a worker, shut down an application, or cancel a task:

~~~text
Coordinator wants to stop
          |
          | worker.interrupt()
          v
Worker is computing or waiting
          |
          +--- isInterrupted() sees true ------+
          |                                    |
          +--- wait throws InterruptedException+
                                               |
                                               v
                                  Apply termination policy
                                               |
                                    finally/close/cleanup
                                               |
                                               v
                                       Worker terminates
~~~

An interrupt signal **does not automatically roll back data or close every resource**. If a task performs multiple steps, intermediate state must be designed so that it stops at a valid point, completes cleanup, or records a clear cancellation outcome.

Some practical guidelines:

- Do not use <code>Thread.stop()</code> to forcefully stop a thread: forced termination is unsafe for data invariants.
- Do not hold locks for too long while waiting on I/O or a condition where policy requires early cancellation.
- For operations with side effects, do not automatically retry just because an interrupt was received: the work may have partially completed.
- If your async API has its own cancelled state, distinguish the interrupt signal from the confirmed cancellation outcome.
- When stopping a worker, you can combine an application control flag with an interrupt to wake up waiting operations; avoid assuming every blocking API is interrupted by the same mechanism.

### Future.cancel(true) Does Not Mean the Worker Has Definitely Stopped

When using <code>Future</code>, <code>cancel(true)</code> may request interrupting the thread executing the task if the implementation supports it. It **does not force** arbitrary code to accept cancellation; a task that intentionally ignores interrupts or is waiting in an API that does not respond accordingly may still be running. Do not use <code>Future.isCancelled()</code> as the sole proof that ongoing side effects have ceased at that exact moment.

Conversely, a task that throws <code>InterruptedException</code> and has it recorded as an error in a future mechanism does not necessarily enter the "cancelled" state unless the framework's contract defines it that way.

## 16. Common Mistakes with the Interrupt Flag and Waiting APIs

### Mistake 1 — Catching InterruptedException and Staying Silent

~~~java
try {
    Thread.sleep(500);
} catch (InterruptedException ignored) {
    // Do not report anything and continue working as normal.
}
~~~

This is **illustrative code that is intentionally discouraged**. After <code>sleep()</code> throws the exception, the flag has been cleared. The failure is swallowed, and downstream layers never receive the stop request. If continuing is genuinely allowed by the contract, document the explicit handling logic; in most workers with a cancellation policy, propagate the exception or restore the flag and exit.

### Mistake 2 — Assuming isInterrupted() Clears the Flag

~~~java
boolean first = Thread.currentThread().isInterrupted();
boolean second = Thread.currentThread().isInterrupted();
~~~

Two reads do not modify the state themselves; if no other call/API intervenes, they observe the same value. This differs from <code>Thread.interrupted()</code>, which clears the flag.

### Mistake 3 — Using Thread.interrupted() Just for Logging

~~~java
System.out.println("Interrupted: " + Thread.interrupted());
~~~

This is **illustrative code**. The log statement has a side effect: if the flag was set, it is now cleared. If you only want to observe it, use <code>Thread.currentThread().isInterrupted()</code> to preserve the signal.

### Mistake 4 — Restoring the Flag but Immediately Continuing to Wait

~~~java
while (true) {
    try {
        queue.take();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    }
}
~~~

This is **intentionally flawed code**, assuming <code>queue</code> exists. After restoring, the next <code>take()</code> call may throw immediately, causing the loop to spin rapidly. If an interrupt means cancellation, exit the loop; if the design requires continuing, use an explicit signal-consumption policy instead of the pattern above.

### Mistake 5 — Assuming sleep() or join() Releases All Locks

<code>sleep()</code> does not release monitors or locks. <code>join()</code> does not automatically release arbitrary locks held by the calling thread. Waiting while holding a lock that the worker needs can lead to deadlock. <code>Object.wait()</code> only temporarily releases the monitor of the object being waited on; <code>Condition.await()</code> does the same for the lock associated with the condition per its contract.

### Mistake 6 — Calling unlock() After lockInterruptibly Fails

~~~java
try {
    lock.lockInterruptibly();
    work();
} finally {
    lock.unlock();
}
~~~

This is **intentionally flawed illustrative code** when <code>lock</code> is a <code>ReentrantLock</code>: if <code>lockInterruptibly()</code> throws before acquiring the lock, <code>finally</code> still runs and may throw <code>IllegalMonitorStateException</code>. The correct pattern is to acquire the lock first, then enter <code>try/finally</code> to release it.

### Mistake 7 — Treating Interrupts as Exceptions That Are Always Thrown

A CPU loop that does not check the flag can keep running. <code>LockSupport.park()</code> can return without throwing <code>InterruptedException</code>. <code>ReentrantLock.lock()</code> can continue waiting. Always check the exact API contract.

### Mistake 8 — Equating an Interrupt Signal with Completed Cancellation

<code>worker.interrupt()</code> only sends a signal. Afterward, you must wait or observe using <code>join()</code>, <code>Future</code>, a latch, or an appropriate management mechanism if you need to know the worker has finished. Do not check the flag and conclude that cleanup is complete.

### Mistake 9 — Catching Exception Too Broadly and Treating It as a Business Error

~~~java
try {
    performTask();
} catch (Exception error) {
    reportFailure(error);
}
~~~

This is **illustrative code**. If an <code>InterruptedException</code> inside is caught via <code>Exception</code>, the cancellation signal may be lost. Especially when using exception-handling wrappers or frameworks, distinguish normal business failures from thread interruption requests.

## 17. What Should Be Tested?

A valuable test suite should distinguish **flag state**, **exceptions thrown**, **lock ownership**, and **cancellation outcome**:

| Scenario | What to verify |
| --- | --- |
| Call <code>interrupt()</code> then <code>isInterrupted()</code> | Flag is set; reading does not clear it |
| Call <code>Thread.interrupted()</code> when flag is set | Returns <code>true</code> and clears the flag |
| Flag set before <code>sleep()</code> | <code>InterruptedException</code> is thrown and flag is cleared |
| Worker interrupted in <code>BlockingQueue.take()</code> | Waiting call reports interruption; worker follows termination policy |
| Catch and restore | Flag is set again if code explicitly calls <code>interrupt()</code> |
| Interrupted in <code>lockInterruptibly()</code> before acquiring lock | Does not release an unowned lock |
| Interrupted in <code>Condition.await()</code> | Lock is reacquired per contract and properly released from <code>finally</code> |
| Interrupting the thread calling <code>join()</code> | Does not conclude that the target thread has stopped |
| Task executing without checking the flag | Does not assume it stops automatically just by receiving an interrupt |
| <code>park()</code> returns due to interrupt | Does not confuse with <code>sleep()</code>'s <code>InterruptedException</code> path |

For multithreaded tests, use <code>CountDownLatch</code>, queues, or equivalent synchronization mechanisms to establish verification ordering rather than relying solely on <code>Thread.sleep()</code> to "wait long enough." If a failure could cause a test to hang, set an appropriate timeout and clean up resources after the test.

When checking the flag state immediately after receiving <code>InterruptedException</code>, verify whether any other thread is sending another interrupt. If a new interrupt signal arrives, observing <code>true</code> does not contradict the contract that the waiting method cleared the status for the interrupt it handled.

## 18. Project Application Checklist

When a method calls a blocking API, ask yourself:

1. **Is this API interruptible?** Does it throw <code>InterruptedException</code>, return early while keeping the flag, or continue waiting?
2. **Where is the flag after being interrupted?** Check the API contract rather than guessing from the method name.
3. **What is the current layer's contract?** Can it declare <code>throws InterruptedException</code> and propagate it upward?
4. **If you must catch**, should you restore the flag and exit the operation, or is there a genuinely valid custom signal-handling rule?
5. **Have you avoided losing the flag** through an unintended call to <code>Thread.interrupted()</code>?
6. **Are you holding any locks or resources while waiting?** Which APIs temporarily release them, and which do not?
7. **When lock waiting is interrupted**, does the code avoid calling <code>unlock()</code> if the lock was not acquired?
8. **Could cancellation leave partially updated data?** Are resources and invariants protected by <code>finally</code> or an appropriate update protocol?
9. **Is there a completion confirmation mechanism** such as <code>join()</code> or a completion state, rather than relying only on the <code>interrupt()</code> signal?
10. **Do tests distinguish** between the exception, the interrupt flag, and the actual completion of the task?

**Core takeaway:** the interrupt flag is a **cooperative signaling state of a thread**. A waiting method may respond to the signal with <code>InterruptedException</code> and clear the flag, or respond in another way defined by its contract. When catching <code>InterruptedException</code>, the application must clearly decide to **propagate**, **restore the signal and exit**, or **handle it intentionally**. Managing this relationship properly helps the system stop work in an orderly manner without silently ignoring cancellation requests.