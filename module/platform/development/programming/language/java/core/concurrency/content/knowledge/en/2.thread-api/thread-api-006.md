# Daemon Threads and User Threads on JVM Exit

In Java, a thread (`Thread`) can be either a **user thread** (a normal, non-daemon thread) or a **daemon thread** (a background thread). The most important difference is **whether the JVM waits for that thread before terminating on its own**. This is a rule about the Java process lifecycle, not a classification of CPU priority or task importance.

## 1. JVM Termination Rules

In the case of normal program termination, the JVM begins the shutdown process when **no live non-daemon threads remain**. The JVM does not need to wait for daemon threads to complete. You can think of it as:

| State | Can the JVM terminate on its own? | Explanation |
|---|---|---|
| `main` has returned, one user thread is still running/waiting | Not yet | The user thread still keeps the JVM alive. |
| `main` has returned, only daemon threads remain | Yes | Daemon threads do not keep the JVM alive; they may be stopped mid-execution. |
| All user threads have terminated | Yes | The JVM begins normal shutdown. |
| `System.exit(status)` is called | Yes, begins shutdown | This call proactively initiates shutdown even when user threads are still running. |
| `Runtime.getRuntime().halt(status)` is called | Forced termination | Bypasses the normal shutdown process, including shutdown hooks. |

**Distinguishing two moments:** the `main()` method finishing **does not mean** the JVM process terminates. `main` normally runs on a user thread. When `main` returns, other user threads can still continue running; when only daemon threads remain, the JVM can close the process without waiting for them.

The rule above describes the condition for the JVM to keep the process alive; it does **not** guarantee that all work on user threads will complete under all circumstances. `System.exit`, `halt`, fatal process errors, or the operating system terminating the process can leave work unfinished.

## 2. How Are Daemon Threads Created and Checked?

For standard Java **platform threads**:

- `thread.isDaemon()` returns the daemon status of a thread. `Thread.currentThread().isDaemon()` checks the currently executing thread.
- `new Thread(...)` by default **inherits the daemon status of the thread that creates it**, unless `setDaemon(...)` is called to change it before starting. Since `main` is normally a user thread, a thread created directly from `main` is also normally a user thread.
- `thread.setDaemon(true)` marks the thread as a daemon; `thread.setDaemon(false)` marks it as a user thread. It must be set **before `start()`**; changing it on a running thread can throw `IllegalThreadStateException`.
- `thread.start()` starts asynchronous execution; calling `thread.run()` directly only executes the method like a normal call on the current thread.
- `isAlive()` reflects whether the thread has started and has not yet terminated, **independent** of `isDaemon()`. A daemon thread can still be in the `RUNNABLE`, `WAITING`, or `TIMED_WAITING` state.

The name *daemon* does **not** mean the JVM gives it lower scheduling priority, automatically interrupts it, or invokes `finally` blocks to clean up before exiting. A daemon thread still runs under the normal thread scheduling mechanism while the process is alive.

> Version scope: the examples below use Java 17+ with platform threads. Starting in **Java 21**, virtual threads are always daemon threads and do not keep the JVM alive; the API for creating virtual threads is not present in Java 17.

## 3. Example 1 — A User Thread Can Keep the JVM Alive After `main`

Create the file `UserThreadExample.java`:

```java
import java.util.concurrent.CountDownLatch;

public class UserThreadExample {
    public static void main(String[] args) {
        CountDownLatch release = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                release.await();
                System.out.println("User worker finished");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "user-worker");

        System.out.println("worker.isDaemon() = " + worker.isDaemon());
        worker.start();
        System.out.println("Main is finishing");
        release.countDown();
    }
}
```

Compile and run:

```bash
javac UserThreadExample.java
java UserThreadExample
```

Output:

```text
worker.isDaemon() = false
Main is finishing
User worker finished
```

By default, `worker` is not a daemon because it was created from `main`. `CountDownLatch` keeps the worker waiting until `Main is finishing` is printed, so the message order is deterministic in a normal run. The `main` method **does not call `join()`**; the JVM still has to account for the worker if it remains alive after `main` returns. Note: a specific execution schedule could also allow the worker to finish before `main` actually returns; that does not change the JVM rule.

Try replacing `release.countDown();` with an operation that never releases the latch: the non-daemon worker will wait forever and the process may not exit on its own. That is an **illustration for reasoning**, not something you should leave hanging in practice.

## 4. Example 2 — A Daemon Thread Does Not Keep the JVM Alive

Create the file `DaemonThreadExample.java`:

```java
import java.util.concurrent.CountDownLatch;

public class DaemonThreadExample {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);

        Thread background = new Thread(() -> {
            System.out.println("Daemon started");
            started.countDown();

            try {
                neverReleased.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                System.out.println("Daemon cleanup");
            }
        }, "background");

        background.setDaemon(true); // Must be before start().
        background.start();
        started.await();
        System.out.println("Main is finishing");
    }
}
```

```bash
javac DaemonThreadExample.java
java DaemonThreadExample
```

Output on a normal run:

```text
Daemon started
Main is finishing
```

The `started` latch helps ensure the daemon has printed its first line before `main` proceeds. `neverReleased` is never opened, so the daemon keeps waiting. When `main` finishes, there are no application-created user threads left to keep the JVM alive, and the JVM can terminate the process. The line `Daemon cleanup` is **not guaranteed to appear**: the JVM does not need to wake up the daemon and does not guarantee executing `finally` blocks of a waiting thread.

Key takeaway: `setDaemon(true)` addresses **whether a thread keeps the process alive**; it is **not** a mechanism for clean thread shutdown. If a daemon is writing files, emitting events, sending data, or updating state, its work can be cut off mid-way.

## 5. Example 3 — Proactively Stopping a Thread and Waiting for Completion

If you want guaranteed cleanup under normal control flow, the application must coordinate stopping and wait for the worker to finish. Here is an example using a stop signal and `join()`, even though the worker is marked as a daemon.

Create the file `GracefulDaemonExample.java`:

```java
import java.util.concurrent.CountDownLatch;

public class GracefulDaemonExample {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch stop = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                System.out.println("Worker started");
                started.countDown();
                stop.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                System.out.println("Worker cleaned up");
            }
        }, "cleanup-worker");

        worker.setDaemon(true);
        worker.start();

        started.await();
        System.out.println("Requesting stop");
        stop.countDown();
        worker.join();
        System.out.println("Main finished after join");
    }
}
```

```bash
javac GracefulDaemonExample.java
java GracefulDaemonExample
```

Output:

```text
Worker started
Requesting stop
Worker cleaned up
Main finished after join
```

`stop.countDown()` is the signal for the worker to exit its wait; `worker.join()` makes `main` wait for the worker to finish, so the cleanup line is printed before the final message. `join()` works with **both daemon and user threads**. Real-world cases also need a strategy for handling workers that refuse to stop (for example, waiting with a timeout via `join(timeout)`, logging an error, and deciding how safe it is to exit).

**Do not use `Thread.stop()`** to force termination: this API is deprecated and unsafe. For real-world work, use cooperative cancellation mechanisms such as a status flag with memory visibility guarantees (`volatile`/`AtomicBoolean`), `interrupt()`, queues/signals, or an appropriate lifecycle management API. If you handle `InterruptedException` without rethrowing it, you should usually restore the interrupt flag with `Thread.currentThread().interrupt()`.

## 6. Common Misconceptions

### `main` returns, yet the application keeps running

The usual cause is a user thread waiting on a lock, waiting on I/O, or running a loop with no termination condition. Name your threads and inspect their state with a thread dump (`jcmd <pid> Thread.print` on a suitable JDK), then identify which component created that thread. Marking every thread as a daemon just to make the application exit can mask resource management bugs.

### Executors and thread pools

When creating an `ExecutorService`, you need to manage when it stops accepting new work and when workers stop—for example, using `shutdown()`, `awaitTermination(...)`, and only when truly necessary considering `shutdownNow()`. With common thread factories, pool workers may be non-daemon and keep the JVM alive. You should not rely on `main` finishing to automatically clean up the pool. `shutdownNow()` only **attempts** to cancel running tasks, typically via interruption; tasks that ignore interrupts may continue.

### Shutdown hooks do not make daemon threads completely safe

`Runtime.getRuntime().addShutdownHook(thread)` registers an **unstarted** thread (not yet `start()`ed) for the JVM to launch during normal shutdown. Hooks are useful for sending stop signals and reclaiming resources in a controlled way, but hooks can run concurrently, can hang, and do not run on `Runtime.halt()` or when the process is forcibly terminated. Do not assume daemon threads will be waited on or that all daemon `finally` blocks will run simply because a shutdown hook exists.

### `System.exit(0)` and `return` are two different things

- `return` in `main`: only ends the `main` call; the JVM continues if user threads remain.
- `System.exit(0)`: requests the JVM to begin normal shutdown even if user threads are running; registered shutdown hooks get a chance to execute.
- `Runtime.getRuntime().halt(0)`: forces immediate termination, bypassing shutdown hooks; do not use it as a routine thread management solution.

### Daemon status is different from priority and data correctness

`setDaemon(true)` does not replace `setPriority(...)`, does not guarantee running on a specific schedule, and does not guarantee task completion. A daemon holding a lock or updating data can still affect user threads while the JVM is running. For tasks that must complete, you need explicit completion waiting points, durable persistence mechanisms, and proper error handling.

## 7. How to Choose in a Java Program

| Type of work | Usually appropriate choice | Important condition |
|---|---|---|
| Computation or data writes that must complete before exiting | User thread, or an executor with explicitly managed lifecycle | Stop accepting new work, wait for completion, handle errors. |
| Auxiliary background monitoring that can be abandoned when the process closes | A daemon can be used | Do not depend on the daemon running to completion for data correctness. |
| Periodic background work that must flush data/reports | Choose based on completion requirements and manage shutdown explicitly | Provide a stop signal and wait for critical parts to finish. |
| Thread pool processing many tasks | Manage the executor explicitly | Call shutdown and wait with a timeout; understand the thread factory behavior. |

The deciding question is: **"If the JVM closes immediately after all user threads finish, is it acceptable for this thread's work to be abandoned mid-way?"** If the answer is no, you must not rely solely on a daemon thread. Conversely, a non-daemon thread also needs a stopping mechanism to avoid keeping the application alive indefinitely.

## 8. Self-Check Questions

1. **Why has the process not exited even after the last line of `main` was printed?** Because live user threads may still remain; check a thread dump and the lifecycle of executors/workers.
2. **Does `setDaemon(true)` make a worker's `finally` block always run?** No. The JVM does not wait for daemon threads and can terminate the process while a daemon is waiting or processing.
3. **Can `setDaemon(true)` be set after `start()`?** That must not be done; it must be configured before starting, and attempting to change it while the thread is alive will throw `IllegalThreadStateException`.
4. **Can `join()` be used with a daemon thread?** Yes. Daemon status describes the condition for keeping the JVM alive; `join()` is a call to wait for a thread to finish.
5. **Why is `System.exit(0)` different from `return` in `main`?** `System.exit` proactively initiates shutdown; `return` only returns from `main`.

**Remember:** user threads can keep the JVM alive; daemon threads do not keep the JVM alive; **to finish work safely, you must explicitly coordinate stopping and wait for completion**.
