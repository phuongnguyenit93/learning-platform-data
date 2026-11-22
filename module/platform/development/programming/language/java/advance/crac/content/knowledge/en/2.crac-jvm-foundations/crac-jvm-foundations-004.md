# Java Threads, Operating System Threads, and Synchronization State

A Java program can perform multiple tasks concurrently using threads. However, from the application's perspective, a Thread object is not completely synonymous with a thread scheduled by the operating system. The JVM provides a thread model and thread states at the Java level; the operating system manages CPU allocation for native threads; synchronization mechanisms coordinate access to shared data among them.

Understanding these three layers helps explain why a thread can be in the RUNNABLE state yet not currently running on a CPU, why BLOCKED differs from WAITING, and why an application must bring threads to a stable state before creating a checkpoint with CRaC.

## 1. Processes and Threads

A **process** is a running program with its own address space and set of resources. A process can contain multiple threads.

A **thread** is a unit of execution within a process. Threads in the same process typically share the heap, objects, static memory, and many process resources. Each thread has its own stack, program counter, and execution state.

For example, a Java server might have:

- One thread accepting connections and receiving requests.
- Multiple threads processing requests.
- One thread writing logs.
- One thread running periodic tasks.
- Internal threads created by the JVM or libraries.

Threads can make progress concurrently. On a machine with multiple CPU cores, multiple threads can genuinely run in parallel at the same instant. On a machine with only a single core, the operating system typically time-slices CPU allocation among threads to create the appearance of concurrency.

## 2. Java Threads and OS Threads

Java represents threads with the java.lang.Thread class. When start() is called, the JVM submits the thread for execution. The run() method contains the thread's work; normally an application does not call run() directly to create a new thread, because calling it directly is simply a method call on the current thread.

~~~java
public class ThreadExample {
    public static void main(String[] args) {
        Thread worker = new Thread(() -> {
            System.out.println(
                "Đang chạy trên: " + Thread.currentThread().getName()
            );
        }, "worker-1");

        worker.start();
    }
}
~~~

The following two calls have different meanings:

- worker.start() asks the JVM to start a new thread, and then the new thread executes run().
- worker.run() executes the method body directly on the calling thread without creating a new thread.

### Platform threads

With a **platform thread**, the JVM typically maps a Java thread to a native thread managed by the operating system. On common JVMs such as HotSpot, this model is usually a one-to-one mapping: one platform thread corresponds to one OS thread.

In that case, the operating system is responsible for scheduling OS threads onto CPU cores. The JVM still manages Java-level concepts such as thread names, stack traces, Thread.State, and language synchronization rules.

The one-to-one model is a common implementation approach, not a mandatory rule of the Java specification for every JVM.

### Virtual threads

Since Java 21, Java has supported **virtual threads** as a type of thread managed by the JVM. Instead of needing a dedicated OS thread for every virtual thread, the JVM can multiplex many virtual threads onto a smaller number of platform threads, also known as carrier threads.

Virtual threads are useful for applications with many concurrent tasks that spend most of their time waiting on I/O. They allow an application to create many lighter-weight units of work without creating an equivalent number of OS threads.

Key distinctions:

| Characteristic | Platform thread | Virtual thread |
|---|---|---|
| Entity directly scheduled by the OS | Corresponding OS thread | Carrier platform thread |
| Lifecycle management | JVM and operating system | Primarily managed by the JVM |
| Cost when creating large numbers | Usually higher | Usually lower |
| Well suited for | CPU-bound work, work needing native thread control | High concurrency with frequent I/O waiting |

Virtual threads do not make a CPU-bound task run faster than the available CPU cores. They improve the ability to organize many waiting tasks; CPU processing capacity remains bounded by hardware.

## 3. How Does the Operating System Schedule Threads?

The operating system does not schedule based on Java's Thread.State concept. It schedules the platform's native execution entities.

Conceptually, an OS thread can be:

- **Runnable/ready:** ready to run and waiting to be scheduled onto a CPU.
- **Running:** currently executing on a CPU core.
- **Blocked/sleeping:** waiting for an event, resource, or I/O operation.
- **Stopped/terminated:** stopped or finished, depending on how the OS represents it.

Exact names and state sets depend on the operating system. Linux, Windows, and other operating systems do not necessarily use the same state taxonomy.

The scheduler can pause a running thread to give CPU time to another thread. Switching CPU execution from one thread to another is called a **context switch**. During a switch, the system must save and restore execution contexts. Context switching is an overhead to account for when an application creates too many threads or contends heavily on resources.

For example, a machine with 4 CPU cores can run at most about 4 CPU-bound threads simultaneously at one time if each core executes one thread. The application may still have hundreds of threads; most of them may be waiting on I/O, waiting for locks, or waiting to be scheduled onto a CPU.

### Do Not Equate Java State With OS State

Thread.State is an observable state at the Java level. It is not a direct mirror of scheduler state in the operating system.

A Java thread in RUNNABLE may be executing or ready to execute yet not currently scheduled onto a CPU by the OS. Therefore, RUNNABLE does not mean the thread is definitely consuming CPU at the moment of observation.

Similarly, BLOCKED in Java specifically means the thread is waiting to acquire an intrinsic lock to enter a synchronized region. It is not synonymous with every form of blocked or sleeping state recorded by the operating system.

When analyzing performance, combine thread dumps, CPU utilization, thread counts, wait times, and OS inspection tools. Looking at a single Thread.State value is rarely sufficient to identify the cause.

## 4. Six States of a Java Thread

The java.lang.Thread.State enum defines six states. These states exist for observation and diagnostics; they do not describe every internal detail inside the JVM or operating system.

| State | Meaning | Common examples |
|---|---|---|
| NEW | Thread object created, but start() has not been called yet | new Thread(task) |
| RUNNABLE | Running or ready to run inside the JVM | Executing run() or waiting for CPU scheduling |
| BLOCKED | Waiting to acquire a monitor lock to enter a synchronized block/method | Another thread holds the same monitor |
| WAITING | Waiting indefinitely for another thread to perform a wakeup action | Object.wait(), Thread.join() without timeout, LockSupport.park() |
| TIMED_WAITING | Waiting for a bounded period of time | Thread.sleep(), wait(timeout), join(timeout), parkNanos() |
| TERMINATED | Execution has finished | run() completed or exited due to an unhandled exception |

A thread typically progresses through the following state transitions:

~~~text
NEW
  |
  | start()
  v
RUNNABLE <-----------------------------+
  |                                    |
  | waiting for monitor                | acquired monitor
  v                                    |
BLOCKED --------------------------------
  |
  | wait/join/park or timed operation
  v
WAITING or TIMED_WAITING
  |
  | woken up, timed out,
  | interrupted, or wait condition changed
  v
RUNNABLE
  |
  | run() finishes
  v
TERMINATED
~~~

This diagram illustrates common state transitions, not an exhaustive state machine for every scenario. For instance, a thread in WAITING due to Object.wait() must reacquire the monitor before continuing execution after being woken up.

### Observing State

You can retrieve the current state with getState():

~~~java
Thread worker = new Thread(() -> {
    // Work of the thread
}, "worker");

System.out.println(worker.getState()); // NEW
worker.start();
System.out.println(worker.getState()); // Could be RUNNABLE or another state
~~~

The result after start() depends on scheduling. The thread may already be running, waiting on a lock, or finished before the thread calling getState() reads the state.

getState() provides only a snapshot at the moment of the call. Do not use it as a synchronization mechanism, such as polling getState() in a loop to decide when another thread may modify data. Use locks, conditions, latches, semaphores, futures, or an explicit coordination mechanism.

## 5. Synchronization Between Threads

When multiple threads read and write the same data, a program must control three aspects:

1. **Atomicity:** whether an operation can be interleaved by another thread.
2. **Visibility:** whether changes made by one thread are visible to another thread.
3. **Ordering:** whether the JVM and CPU are permitted to reorder operations.

Ignoring these aspects can lead to race conditions, inconsistent data, or bugs that appear only under high load.

### Race conditions

Consider a counter incremented concurrently by two threads:

~~~java
class Counter {
    int value = 0;

    void increment() {
        value++;
    }
}
~~~

The expression value++ is not an atomic operation. Conceptually, it consists of reading the value, adding one, and writing it back. Two threads can both read 10, both compute 11, and both write 11. The final result is 11 despite two increments; one update is lost.

The operation can be protected using synchronized:

~~~java
class Counter {
    private int value = 0;

    synchronized void increment() {
        value++;
    }

    synchronized int getValue() {
        return value;
    }
}
~~~

Only one thread at a time can execute a synchronized method or block on the same monitor. Exiting a synchronized region also establishes memory visibility with the next acquisition of the same monitor.

### Monitors and synchronized

Every Java object can be used as a monitor. When a thread enters a synchronized (lock) block, it must acquire the monitor of the lock object. If another thread currently holds that monitor, the arriving thread transitions to BLOCKED.

~~~java
private final Object lock = new Object();

void update() {
    synchronized (lock) {
        // Critical section: access shared data
    }
}
~~~

Key points to remember:

- Monitors are **reentrant**: a thread already holding a monitor can re-enter another synchronized region protected by that same monitor.
- synchronized blocks on the same object are mutually exclusive between threads.
- synchronized on an instance method uses the monitor of this.
- static synchronized uses the monitor of the corresponding Class object.
- Threads using different monitors do not automatically exclude one another.

Avoid holding monitors for long periods, especially while performing I/O, calling external services, or waiting on operations of unbounded duration. Doing so increases wait time for other threads and can cause deadlocks.

### wait, notify, and notifyAll

wait(), notify(), and notifyAll() are methods on Object that operate on the object's monitor.

- wait() causes the thread holding the monitor to release it and move into the set of threads waiting on that object.
- notify() wakes up one thread waiting on that monitor.
- notifyAll() wakes up all threads waiting on that monitor.
- A woken thread must contend to reacquire the monitor. It resumes only after reacquiring the monitor.

Example:

~~~java
final class StartGate {
    private boolean open = false;

    public synchronized void awaitOpen() throws InterruptedException {
        while (!open) {
            wait();
        }
    }

    public synchronized void open() {
        open = true;
        notifyAll();
    }
}
~~~

The condition is checked inside a while loop, not an if, because:

- A thread may wake up even when the application condition is not yet true (spurious wakeup).
- notifyAll() can wake multiple threads while only some satisfy the condition.
- Another thread can change the condition before the woken thread reacquires the monitor.

wait() must be called while the thread holds the monitor of the target object; otherwise, the JVM throws IllegalMonitorStateException.

**wait() vs. sleep():**

| Characteristic | Object.wait() | Thread.sleep() |
|---|---|---|
| Belongs to | Object | Thread |
| Requires holding monitor before calling | Yes | No |
| Releases monitor of synchronized object | Yes | No |
| How waiting ends | notify/notifyAll, interrupt, or timeout | Timeout elapsed or interrupt |
| Used for | Condition-based coordination | Pausing a thread for a duration |

If a thread calls sleep() while holding a monitor, it continues holding that monitor for the entire sleep duration. Consequently, using sleep() to wait for another thread to modify data can prevent that other thread from acquiring the lock to make the change.

### volatile

volatile is suitable when a variable must be read/written directly across multiple threads and the operation does not require a compound update sequence to be atomic.

~~~java
class ServiceState {
    private volatile boolean running = true;

    void stop() {
        running = false;
    }

    void runLoop() {
        while (running) {
            doOneUnitOfWork();
        }
    }

    private void doOneUnitOfWork() {
        // Process one unit of work
    }
}
~~~

When one thread writes to a volatile variable, another thread reading the same volatile variable can observe the new value under Java's memory rules. volatile also establishes required ordering constraints for related operations.

However, volatile does not make value++ atomic. If thread-safe incrementing/decrementing is required, use AtomicInteger, a lock, or synchronized depending on requirements.

### Locks and Other Coordination Utilities

Beyond the intrinsic lock of synchronized, Java provides utilities in java.util.concurrent:

- ReentrantLock: explicit lock supporting tryLock(), configurable fairness, and Condition objects.
- CountDownLatch: allows one or more threads to wait until a number of tasks complete.
- Semaphore: limits the number of threads allowed to access a resource simultaneously.
- CyclicBarrier and Phaser: coordinate threads across phases.
- CompletableFuture: describes asynchronous task chains and result composition.
- Atomic classes such as AtomicInteger and AtomicReference: provide atomic operations for suitable data.

Example using CountDownLatch to wait for a group of tasks to complete:

~~~java
int taskCount = 3;
CountDownLatch done = new CountDownLatch(taskCount);

for (int i = 0; i < taskCount; i++) {
    new Thread(() -> {
        try {
            performTask();
        } finally {
            done.countDown();
        }
    }).start();
}

done.await();
System.out.println("Tất cả công việc đã hoàn tất");
~~~

In real applications, it is usually better to submit tasks to an ExecutorService rather than creating a new thread for each request. Thread pools bound thread counts, reuse resources, and centralize task lifecycle management.

## 6. Interruption and Controlled Thread Termination

Java discourages forcibly stopping a running thread. The standard approach is asking a thread to stop itself via **interrupt** or a shared status flag.

interrupt() sends an interruption signal to the thread. The effect depends on what the thread is doing:

- If the thread is waiting in sleep(), wait(), or join(), the operation usually terminates with InterruptedException.
- If the thread is not in an interruptible waiting operation, the interrupt flag is set for the thread to check and respond to.
- Interrupting does not automatically kill a thread.

Example:

~~~java
class Worker implements Runnable {
    @Override
    public void run() {
        while (!Thread.currentThread().isInterrupted()) {
            doOneUnitOfWork();
        }

        cleanUp();
    }

    private void doOneUnitOfWork() {
        // Work must have bounded execution time
    }

    private void cleanUp() {
        // Release resources owned by the worker
    }
}
~~~

When handling InterruptedException, the application should explicitly decide whether to stop or propagate the interrupt signal up the call stack. If the exception cannot be rethrown, restore the interrupt flag via Thread.currentThread().interrupt() before exiting or returning control.

~~~java
try {
    Thread.sleep(1_000);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Do not catch InterruptedException and ignore it if the task must support controlled termination. Swallowing the interrupt signal can cause application shutdown or coordination to hang.

## 7. Common Synchronization Issues

### Deadlock

Deadlock occurs when threads wait on each other in a cycle and no thread can proceed.

Example:

- Thread A holds lock X and waits for lock Y.
- Thread B holds lock Y and waits for lock X.

Neither thread can acquire the remaining lock to exit its critical section.

Ways to reduce risk:

- Establish a consistent lock acquisition order across the entire application.
- Avoid invoking external code while holding a lock.
- Keep synchronized regions short.
- Use tryLock() with timeouts when appropriate.
- Collect thread dumps when the application shows signs of hanging.

### Starvation and livelock

**Starvation** occurs when a thread repeatedly fails to obtain a needed resource because other threads are always prioritized or monopolize the resource.

**Livelock** occurs when threads remain active and continually respond to one another without making useful progress. For example, two threads keep yielding to each other according to a rule that causes both to repeat the yield indefinitely.

These phenomena differ from deadlock: in deadlock, threads are generally blocked waiting; in livelock, they remain running yet fail to finish work.

## 8. Observing and Diagnosing Threads

When an application is slow or unresponsive, determine whether threads are running on CPU, waiting on monitors, waiting on I/O, or waiting on an application condition.

Useful tools include:

- jcmd <pid> Thread.print: captures a thread dump of the Java process.
- jstack <pid>: captures thread stack traces, if the tool is available in the JDK environment.
- ThreadMXBean: retrieves thread information programmatically and can help detect deadlocks.
- OS tools: correlate CPU usage, OS thread count, and native thread states.

When reading a thread dump, note:

- Many threads in BLOCKED waiting on the same monitor can indicate a lock contention hotspot.
- A thread in WAITING or TIMED_WAITING is not necessarily a problem; it may be an expected idle wait state.
- A thread in RUNNABLE is not necessarily consuming CPU; correlate stack traces with CPU metrics.
- Repeated stack traces at the same location across multiple samples can help locate long loops or bottlenecks.

Do not conclude deadlock merely from seeing many threads waiting. Look for lock dependency cycles or use deadlock detection tools.

## 9. Connection to CRaC: Bringing Threads to a Quiescent Point Before Checkpoint

CRaC (Coordinated Restore at Checkpoint) allows saving the state of a Java process to restore that process in a later run. Because a checkpoint involves the memory and execution state of the process, thread lifecycles and synchronization state must be accounted for in application design.

A checkpoint taken while the application is mid-work can carry state that is hard to coordinate with external systems after restore. For example:

- A thread holds a lock while updating shared data.
- A group of threads are waiting on one another or on an unmet condition.
- A task is processing a request while an external transaction is incomplete.
- A thread holds a connection or native resource that must be recreated after restore.
- A background thread runs a periodic schedule tied to wall-clock time or external state.

The goal of pre-checkpoint preparation is to bring the application to a **quiescent point**: no new work is accepted, running work has completed or been stopped cleanly, and external resources have been handled appropriately.

A common sequence:

1. Stop accepting new requests or tasks.
2. Signal workers to stop pulling work and finish in-progress items.
3. Wait for running tasks to finish using a coordinated mechanism with a timeout.
4. Complete or roll back open transactions according to application policy.
5. Close or release connections, file handles, and external resources that need reinitialization.
6. Perform the checkpoint.
7. After restore, recreate external resources, restart workers, and resume accepting work.

Do not poll Thread.getState() or call sleep() in a loop to guess that all threads have stopped. Use application-managed signals and conditions such as CountDownLatch, Phaser, shutdown flags, or worker pause/resume protocols.

### CRaC Resource callbacks

The CRaC API provides Resource so the application can register actions to execute before checkpoint and after restore. The example below illustrates the lifecycle of an outbound client connection; request-handling methods are implemented by the application itself.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class BackendResource implements Resource {
    private ExternalClient client;

    public BackendResource() {
        client = createClient();
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        stopAcceptingNewRequests();
        awaitInFlightRequests();
        client.close();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        client = createClient();
        resumeAcceptingRequests();
    }

    private ExternalClient createClient() {
        // Create client according to application configuration
        return new ExternalClient();
    }

    private void stopAcceptingNewRequests() {
        // Close gate for new work or transition service to paused state
    }

    private void awaitInFlightRequests() throws Exception {
        // Wait for running work to finish with an appropriate timeout
    }

    private void resumeAcceptingRequests() {
        // Allow service to accept work after resources are ready
    }
}
~~~

This example is an illustrative skeleton; ExternalClient and coordination methods should be replaced with actual application classes. If multiple resources depend on each other, design close and reopen ordering so dependent resources are initialized before workers use them.

### Managing thread pools across checkpoints

An ExecutorService on which shutdown() has been called will not accept new tasks. Therefore, if you want to keep using a pool after restore, do not blindly call shutdown() and expect the pool to resume functioning on its own. Choose one of two approaches:

- Use an application-managed pause mechanism: stop submitting tasks, wait for running tasks to complete, retain the pool structure in a runtime-supported way, and resume after restore.
- Shut down the pool before checkpoint and create a new pool during the post-restore phase.

The choice depends on the executor type, the CRaC-enabled JDK, the operating system, and how the application manages workers. Verify target runtime behavior rather than assuming all native threads or library resources can continue being used safely.

In addition to thread pools, audit ThreadLocals. Thread-bound data may store per-request, transaction, or security context information. Clear data according to the task lifecycle to avoid carrying stale state into another task or into the post-restore phase.

## 10. Design Principles to Remember

- Use start() to launch a thread; calling run() directly does not create a new thread.
- Distinguish platform threads from virtual threads and understand which thread is directly scheduled by the operating system.
- Do not treat Thread.State as an OS thread state map.
- RUNNABLE can mean running or waiting for CPU; BLOCKED means waiting for an intrinsic monitor.
- Use synchronized, locks, or java.util.concurrent utilities to protect shared data.
- wait() releases the monitor; sleep() does not release the monitor.
- Check wait conditions inside a while loop when using wait().
- volatile guarantees appropriate visibility and ordering rules, but does not make compound operations like count++ atomic.
- Use interrupts and shutdown protocols to terminate threads cleanly.
- When diagnosing, combine thread dumps with CPU metrics and OS observations.
- Before a CRaC checkpoint, coordinate workers to a quiescent point, handle in-flight tasks, and manage resources that must be recreated after restore.

Understanding the relationship among Java threads, OS threads, and monitors provides a clear foundation for reading thread dumps, resolving resource contention, and preparing applications for checkpoint/restore.
