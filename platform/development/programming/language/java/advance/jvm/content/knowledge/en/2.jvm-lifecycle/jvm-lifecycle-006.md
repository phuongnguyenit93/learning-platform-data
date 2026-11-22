# When `main` Ends: Non-Daemon Threads and JVM Exit Conditions

The `main(String[] args)` call is the **entry point of a Java application**, but completing the `main` method **does not mean** the entire JVM process has ended. After `main` returns, other threads may still be running or waiting; a live **non-daemon** thread can keep the process alive. Conversely, live **daemon** threads do not by themselves prevent the JVM from beginning the shutdown process.

This article explains the JVM termination rules according to Java SE, distinguishes `main` from the overall application lifecycle, explains how to inspect daemon status, how to manage workers and executors, and exceptions such as `System.exit`, shutdown hooks, and virtual threads.

## 1. The Correct Model: `main` Is a Method of One Thread, the JVM Is a Process That Can Contain Many Threads

Normally, the Java launcher starts the JVM, loads/initializes the main class, and then calls `main` on a **non-daemon thread**. During execution, the program or libraries may start additional threads.

Three events must be distinguished:

1. **The `main` method returns** (or throws an uncaught exception): the call to `main` ends; in normal launcher execution, the main thread also terminates afterward.
2. **The `main` thread terminates**: the JVM checks the termination condition of the *entire* program; other started non-daemon threads may still be alive.
3. **The JVM/process terminates**: threads no longer continue executing Java code; the operating system reclaims process resources. Shutdown hooks may have already been run when the JVM terminates through the normal shutdown path.

In JLS Java SE 17 `12.8, the normal program termination condition is that **all non-daemon threads have terminated**. Another path is a permitted `System.exit`/`Runtime.exit` call. The `Runtime` documentation further explains the shutdown hooks process; abrupt termination paths need to be considered separately.

### Is a Non-Daemon Thread Still Alive?

| Situation after `main` | Can the JVM terminate on its own immediately when considering threads? | Why |
| --- | --- | --- |
| No live non-daemon threads remain; only daemons remain | Yes, the JVM begins shutdown | Daemons do not keep the JVM alive |
| A non-daemon is still executing work | Not yet | It is still a live thread |
| A non-daemon is in `sleep()`, `wait()`, `join()`, blocked I/O, or waiting for a lock | Not yet | `WAITING`/`BLOCKED`/`TIMED_WAITING` does not mean `TERMINATED` |
| A non-daemon `Thread` object exists but `start()` has not been called | Not because of that object alone | A thread that has not started is not an executing thread keeping the JVM alive |
| A previous non-daemon existed, but `run()` has completed or exited due to an exception | Not because of that dead thread alone | The thread has terminated, even if the `Thread` object is still referenced |
| A live non-daemon exists and a thread calls `System.exit(0)` | Shutdown can begin immediately | `System.exit` is an active termination path and does not wait for all workers to finish via the non-daemon counting mechanism |

The table assumes the application is run with the standard Java launcher, with no other non-daemon threads or shutdown hooks holding the process. "Can terminate" does not promise that the shutdown command takes zero time.

## 2. Daemon Is a Property That Affects When the JVM Shuts Down on Its Own

A `Thread` has a daemon flag:

- **Non-daemon (user thread):** while alive, it prevents the JVM from terminating on its own under the "no non-daemon threads remaining" condition.
- **Daemon:** is still a real Java thread and is still scheduled to execute while the JVM runs; however, on its own it is **not enough** to keep the JVM alive.
- The daemon/non-daemon classification does **not** indicate priority, CPU usage, data safety, or whether the work is important.
- `Thread.isDaemon()` reads the daemon status; `Thread.isAlive()` indicates whether the thread has called `start()` and has not yet terminated. Both need to be combined to understand whether a thread can keep the JVM alive.
- For traditional **platform threads**, `new Thread(runnable)` normally inherits the daemon flag of the thread that *creates the Thread object*. Because `main` on the launcher is normally non-daemon, a worker created from `main` is non-daemon by default.
- `setDaemon(boolean)` must be called **before `start()`**. Calling it after the thread is already alive throws `IllegalThreadStateException`. There is no valid way to use `setDaemon` to turn a running thread from non-daemon to daemon.
- Setting `setDaemon(true)` does not "cancel" the thread when `main` ends; it allows the JVM to terminate even while that thread is still active if no other non-daemon threads remain.

Note the difference: **"a daemon does not keep the JVM alive"** is different from **"a daemon stops immediately when `main` returns"**. If another non-daemon is still alive, the daemon can still continue running. When the JVM actually terminates, unfinished daemon work may be terminated without going through normal cleanup blocks.

## 3. Example A — `main` Has Ended, but a Non-Daemon Still Runs

Create the file **`MainAndWorker.java`**:

```java
public class MainAndWorker {
    public static void main(String[] args) {
        Thread mainThread = Thread.currentThread();

        Thread worker = new Thread(() -> {
            try {
                // Only prints when the main thread has actually terminated.
                mainThread.join();
                System.out.println("worker: main thread terminated");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                System.out.println("worker: interrupted");
            }
        }, "worker");

        // This line clearly illustrates the choice; by default it is already non-daemon
        // because worker is created on the regular main thread.
        worker.setDaemon(false);
        worker.start();

        System.out.println("main: returning");
    }
}
```

Run with **JDK 17+**:

```bash
javac --release 17 MainAndWorker.java
java MainAndWorker
```

**Stdout without external interference**:

```text
main: returning
worker: main thread terminated
```

**Why is the output order deterministic?** `main` prints the first line, then returns. `worker` waits on `mainThread.join()`; that call only returns normally after the `main` thread terminates. Only then does `worker` print the second line. The JVM does not terminate between the two lines because `worker` is a live **non-daemon**. After `worker` finishes `run()`, no non-daemon remains in this example; the JVM can shut down.

The example intentionally uses `join()` from `worker` to prove `main` has *actually* terminated before `worker` continues; an example that merely puts `sleep(1000)` and guesses the order from the screen would depend on OS scheduling.

## 4. Example B — A Daemon Can Be Left Behind When `main` Ends

Create **`DaemonDoesNotKeepJVM.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class DaemonDoesNotKeepJVM {
    public static void main(String[] args) {
        Thread background = new Thread(() -> {
            try {
                // A task waiting indefinitely because the latch is not opened.
                new CountDownLatch(1).await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "background");

        background.setDaemon(true); // before start()
        background.start();

        System.out.println("main: returning");
    }
}
```

Run:

```bash
javac --release 17 DaemonDoesNotKeepJVM.java
java DaemonDoesNotKeepJVM
```

**Stdout**:

```text
main: returning
```

In this standalone program, after `main` ends there are no application non-daemon threads left; `background` is a daemon even though it is waiting on the latch. The JVM can proceed to shutdown without needing the latch to reach 0.

The example intentionally puts the daemon task in a waiting state so the result does not depend on "whether the machine is fast or slow". Replacing the wait with writing a file/transferring data and hoping the daemon always finishes before the JVM exits is a lifecycle management bug. Do not use daemons as a guarantee for completing log writes, saving transactions, flushing buffers, or releasing resources.

## 5. Example C — If You Need the Result, Call `join()` to Wait Actively

Whether the work runs on a daemon or non-daemon thread, if `main` needs to guarantee completion before returning, **wait for the result** explicitly.

File **`WaitForTask.java`**:

```java
public class WaitForTask {
    public static void main(String[] args) throws InterruptedException {
        Thread background = new Thread(
                () -> System.out.println("task: completed"),
                "background"
        );
        background.setDaemon(true);
        background.start();

        background.join();
        System.out.println("main: completed");
    }
}
```

```bash
javac --release 17 WaitForTask.java
java WaitForTask
```

**Stdout**:

```text
task: completed
main: completed
```

`join()` makes `main` print the last line only after the thread has completed. When the worker is a daemon, `main` itself (non-daemon) is still alive while waiting, so the JVM does not exit early on its own. If the worker gets stuck forever, `join()` without a timeout can also wait forever; you can use `join(milliseconds)`, then check `isAlive()` and apply an appropriate timeout/cancellation policy. `join()` can throw `InterruptedException` and needs to be handled according to the program's contract.

### What `join()` Does Not Guarantee

- `join()` only waits for the specified thread; it does not automatically wait for all child threads, thread pools, or I/O operations not tied to that thread.
- If the thread terminates due to an exception, `join()` still completes; a separate channel is needed to report success/failure, such as `Future.get()`.
- `Thread.interrupt()` requests cooperation/interruption support; it is **not** a forced termination command.
- Avoid creating a wait cycle: thread A calling `join()` on B while B calls `join()` on A will not be able to complete normally.

## 6. ExecutorService: A Real-World Cause of Applications "Printing Done Without Exiting"

Common example:

```java
ExecutorService executor = Executors.newSingleThreadExecutor();
executor.submit(() -> System.out.println("task done"));
System.out.println("main done");
// Missing executor.shutdown()
```

This is only an **error illustration snippet**, not a standalone file. `Executors.newSingleThreadExecutor()` in its default usage creates **non-daemon** workers when needed to run tasks. Even when the task returns and `main` ends, the executor can still keep the worker waiting for the next job. The JVM does not exit on its own. Calling `Future.get()` to wait for an individual task to finish also **does not replace** `executor.shutdown()`.

Complete approach for **Java 17+** — file **`ExecutorLifecycle.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ExecutorLifecycle {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> result = executor.submit(() -> 6 * 7);
            System.out.println("result=" + result.get());
        } finally {
            stopExecutor(executor);
        }
    }

    private static void stopExecutor(ExecutorService executor) {
        executor.shutdown(); // do not accept new tasks; process already-received tasks
        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow(); // best-effort interrupt
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    System.err.println("executor: still running");
                }
            }
        } catch (InterruptedException e) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

```bash
javac --release 17 ExecutorLifecycle.java
java ExecutorLifecycle
```

**Normal stdout**:

```text
result=42
```

- `result.get()` waits for the task to return the number, while also wrapping task errors into `ExecutionException`. It does not close the executor on its own.
- `shutdown()` rejects new tasks while still processing already-submitted tasks; `awaitTermination()` waits for the pool to terminate up to the timeout.
- `shutdownNow()` only **attempts** to stop running tasks via interrupt and drains waiting tasks; uncooperative tasks may remain alive. Therefore, the code checks again and logs a warning if it cannot be stopped.
- When the thread calling shutdown is interrupted, the example preserves the interrupt flag after the cancellation request; a real application must decide its own policy if the timeout is prolonged.
- In Java 17, do not default to `try (ExecutorService executor = ...)` with AutoCloseable syntax; `ExecutorService` in the Java 17 API does not have `close()` yet. For newer releases, read the API for the exact version when using the new closing mechanism.

If a web server/listener is designed to run continuously, non-daemon threads keeping the JVM alive is the **correct behavior**. The issue only arises when the problem requires termination without a path to stop the server/executor.

## 7. What Changes When Calling `System.exit`?

Two different paths:

### A. Natural Termination

`main` ends → remaining non-daemons continue running → when the last non-daemon dies, the JVM begins shutdown → runs registered shutdown hooks → after hooks finish, the JVM terminates.

### B. Calling `System.exit(status)` (or `Runtime.getRuntime().exit(status)`)

The JVM **begins the shutdown process** on request, even when non-daemons are still running. Registered shutdown hooks are started and may run concurrently with other threads; after hooks finish, the runtime proceeds to termination. `status` is the status code requested to be returned to the program's calling environment; `0` usually indicates successful termination by OS convention.

Therefore, `System.exit(0)` is **not** a substitute for `join()` or shutting down an executor. It does not guarantee that all tasks have completed, buffers have been flushed, or `finally` blocks of terminated threads will be executed. In a server, library, or test suite, calling `System.exit` directly can also terminate the entire JVM unexpectedly.

### How Are Shutdown Hooks Related?

Registering a hook while the JVM is active:

```java
Runtime.getRuntime().addShutdownHook(new Thread(
        () -> System.out.println("shutdown hook"),
        "shutdown-hook"
));
```

This is an **illustrative snippet**, not a complete program. A hook is a `Thread` object registered for the JVM to start during the shutdown phase. An **unstarted** hook is not a non-daemon worker keeping the program alive before shutdown. Hooks can run **in parallel**, and execution order is not guaranteed; a hung hook can prevent the shutdown process from completing. Therefore:

- Use hooks for necessary cleanup operations within a reasonable timeframe; avoid circular waits or depending on services that are themselves shutting down.
- Do not use the output order of two hooks to infer a guaranteed sequence.
- Do not expect hooks to always run on forced termination: `Runtime.halt()` bypasses the shutdown sequence; severe native errors, forced process kills, or power loss can also skip hooks.
- Even when a hook finishes, other still-running normal threads are not automatically "joined" by the JVM along the `System.exit` path.

## 8. Since Java 21: Virtual Threads Are Always Daemon

**This section applies to Java 21+**, not part of the Java 17 public API. In the Java 21 `Thread` Javadoc, **virtual threads are daemon threads** and by themselves do not prevent the JVM from beginning shutdown. A virtual thread cannot be turned into a non-daemon via `setDaemon(false)`.

Standalone example, file **`VirtualThreadLifetime.java`**:

```java
public class VirtualThreadLifetime {
    public static void main(String[] args) throws InterruptedException {
        Thread task = Thread.startVirtualThread(
                () -> System.out.println("virtual: completed")
        );

        task.join();
        System.out.println("main: completed");
    }
}
```

```bash
javac --release 21 VirtualThreadLifetime.java
java VirtualThreadLifetime
```

**Stdout**:

```text
virtual: completed
main: completed
```

`Thread.startVirtualThread` has existed since Java 21. If `task.join()` is omitted, the program can shut down as soon as `main` and other non-daemons finish, leaving the virtual thread's work incomplete. **Do not "fix" this by changing the virtual thread to non-daemon:** structure the task lifecycle to wait for results, with timeouts and cancellation when needed.

This makes the non-daemon rule especially important when migrating from traditional thread pools to virtual threads: the task creation API and completion mechanisms differ, but **the responsibility for waiting for essential tasks still belongs to the application**.

## 9. Checking When a Program Does Not Exit

When the terminal/CI is still waiting after logging `main completed`, check systematically:

1. **Has any `System.exit`/`Runtime.halt` or shutdown hook started?** If so, this is an active shutdown/hook branch, not just a `main` story.
2. **Are there live non-daemons?** Identify the name, `Thread.isDaemon()`, and `Thread.isAlive()`; threads in `WAITING`, `TIMED_WAITING`, or `BLOCKED` are still live threads.
3. **Where did that thread come from?** `new Thread`, `ExecutorService`/`ScheduledExecutorService`, server socket, I/O listener, scheduler, HTTP/DB library, GUI/event loop, or custom callbacks.
4. **What condition is the thread waiting on?** `Lock`/monitor, `CountDownLatch`, `BlockingQueue.take()`, `Object.wait()`, `Thread.join()`, socket/accept, or an empty task queue.
5. **Is there a valid stop path?** Stop accepting new tasks, close sockets/listeners, signal cancellation, call `shutdown()` on the executor, `awaitTermination()`, or wait with `join()`, with a timeout and failure-handling policy.

With a **HotSpot JDK** that has the corresponding diagnostic tools, you can take a thread dump using:

```bash
jcmd <PID> Thread.print
```

`<PID>` is the Java process ID to inspect. The output helps view the list of threads, names, stacks, and states; depending on the JDK/display format, daemon and virtual thread information may vary. Do not decide based solely on the word "RUNNABLE": a non-daemon thread in `WAITING` is enough to block natural shutdown. A thread dump is a snapshot at a point in time, so you may need to observe multiple times when investigating deadlocks or waiting pools.

**Note:** a thread's state is a lifecycle characteristic of that thread, not the state of the entire JVM. The number of threads changes continuously; do not conclude whether the process has/has not exited solely from `main`'s logs.

## 10. Common Misconceptions

| Misconception | Correction |
| --- | --- |
| "The end of `main` is the end of the program" | `main` ending only finishes one thread; other non-daemons can continue keeping the process alive |
| "Holding a `Thread` reference means the JVM will wait" | Only **started and still-alive** threads matter; unstarted/dead objects do not keep the JVM alive |
| "A `WAITING` thread is considered stopped" | `WAITING` is still alive, and a non-daemon still prevents natural shutdown |
| "`daemon=true` means low priority or auto cleanup" | Daemon only relates to the right to keep the JVM alive; work can be cut off when the JVM terminates |
| "`setDaemon(true)` can be called anytime" | For platform threads, it must be called before `start()` |
| "`Future.get()` closes the executor" | `get()` waits for the task result; `shutdown()` is what asks the pool to terminate |
| "`shutdownNow()` always stops all workers" | Interrupt is cooperative/best effort; uncooperative workers may still run |
| "`System.exit(0)` always completes all cleanup" | It initiates shutdown, and only hooks have a wait mechanism in this path; other tasks are not guaranteed |
| "Virtual threads keep the JVM alive like platform threads" | Java 21+ virtual threads are always daemon |
| "Hooks are guaranteed to be called for every way of killing a process" | There are abrupt termination cases where hooks do not run |

## 11. How to Design a Clear JVM Lifecycle

A batch/CLI application should have a **clear completion condition**: receive work → wait for necessary tasks → collect errors → close executors/resources → return from `main`. A server application should have a **clear stop condition**: request shutdown → stop accepting requests → wait for remaining tasks within bounds → close listeners/executors → let non-daemons finish.

Short decision diagram:

```text
main() returns
    |
    v
Any started and unfinished non-daemon remaining?
    | Yes                    | No
    v                        v
JVM stays alive        Begin shutdown
    |                        |
    v                        v
Worker processes/waits Run shutdown hooks
    |                        |
    v                        v
Last non-daemon dies   Hooks completed?
    |                        | Yes
    +------> shutdown -------+----> JVM exits
```

`System.exit(...)` is a separate path entering shutdown without waiting for the last non-daemon to die; `Runtime.halt(...)` and some external failures do not follow the normal hook path. Do not use the diagram to infer that every hook always finishes: a hung hook can also block shutdown.

### Checklist When Reading or Reviewing Code

- Which workers need to run to completion? Is there `join()`, `Future.get()`, completion coordination, or another synchronization mechanism to guarantee it?
- In what context are new threads created, and is the daemon flag checked or explicitly set before `start()`?
- Does the executor/scheduler have a `shutdown()` and termination wait path? If there is a timeout, what happens next?
- Are there long-running components like servers, listeners, event loops, or GUIs, and an active closing mechanism?
- Is `System.exit` called anywhere instead of managing workers/resources?
- Is JDK 17 or 21+ used? With virtual threads, daemon threads do not keep the JVM alive; is there a waiting mechanism in place?
- Do shutdown hooks avoid indefinite blocking, deadlocks, and dependencies on the order of other hooks?

## Official Sources for Reference

- [JLS Java SE 17, `12.8 Program Exit](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.8): program termination conditions according to non-daemons and `System.exit`.
- [`Thread` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): daemon flag, `start()`, `join()`, states, and property inheritance.
- [`Runtime` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): `exit`, `halt`, `addShutdownHook`, and shutdown sequence.
- [`ExecutorService` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `shutdown`, `shutdownNow`, `awaitTermination`.
- [`Thread` — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): virtual threads are always daemon; `Thread.startVirtualThread` exists since Java 21.

**Remember:** `main` ending only says that the main thread's work is done. The JVM only shuts down on its own along the normal path when **no live non-daemon threads remain**; if you want the application to terminate properly and safely, manage task completion and resource closing explicitly.
