# Shutdown Hooks, System.exit, and Runtime.halt During JVM Termination

## Lesson Objectives

When terminating a Java process, what matters is not only *when* the JVM stops, but also *whether there is time to clean up resources*. This lesson helps you:
- Explain the events that trigger the JVM shutdown process, even when `main()` has already finished.
- Understand the registration, startup, and completion mechanisms of **shutdown hooks**, their concurrency, and their limitations.
- Distinguish between **natural termination**, **`System.exit(int)` / `Runtime.exit(int)`**, and **`Runtime.halt(int)`**.
- Write, run, and explain illustrative Java 17+ programs; identify cases where `finally` or shutdown hooks are not executed.
- Build a time-bounded **graceful shutdown** strategy for multithreaded applications.

## 1. When does the JVM start shutting down?

A Java application does not necessarily stop as soon as the `main()` method returns. The `main()` method runs on a thread; if there are still living **non-daemon threads**, a normal JVM continues running. The JVM can begin the shutdown sequence when:

1. **No non-daemon threads remain alive**: background non-daemon work has completed and no thread is keeping the JVM alive.
2. **An active exit request is made**: the program calls `System.exit(status)` or `Runtime.getRuntime().exit(status)`.
3. **An external event is recognized by the JVM as a termination request**: for example, certain operating system signals or application interrupt actions supported by the JVM.

The three categories above can trigger the **shutdown sequence**. Conversely, certain forced termination situations such as **SIGKILL** on Unix, **TerminateProcess** on Windows, power loss, fatal native errors, or a process manager forcibly terminating the process can cause the JVM to stop without letting hooks run. Shutdown hooks must not be treated as a mechanism guaranteed to execute in *every* process death scenario.

### Non-daemon and daemon threads

- A living **non-daemon** thread usually keeps the JVM alive after `main()` finishes, until shutdown is requested.
- A **daemon thread** does not prevent the JVM from starting shutdown merely because it is still alive.
- Once shutdown has begun, hooks run **concurrently with living threads**, including both daemon and non-daemon threads. Therefore, other threads may still be operating on resources that a hook intends to close.

The condition "no non-daemon threads remain" is an important rule in standard Java applications; if the JVM is embedded and controlled via the JNI Invocation API, lifecycle details also involve the native code controlling the JVM.

## 2. What is a shutdown hook?

A **shutdown hook** is a `Thread` object that has been created but **not yet `start()`ed**, registered with the runtime so that the JVM proactively starts it when entering the shutdown sequence.

Main API:

~~~java
Runtime runtime = Runtime.getRuntime();

Thread hook = new Thread(() -> {
    // Brief, controlled cleanup.
}, "cleanup-hook");

runtime.addShutdownHook(hook);
~~~

The snippet above **illustrates the API**, and is not a standalone Java program class. The runtime will call `start()` on the hook itself at shutdown time; the author **must not call `hook.start()` manually** to "test run" the same registered object. Manually starting a hook before shutdown can put the shutdown sequence into an unspecified behavioral state.

Related APIs:

| API | Purpose |
| --- | --- |
| `Runtime.getRuntime()` | Gets the current runtime object of the application. |
| `addShutdownHook(Thread hook)` | Registers an unstarted `Thread` to run at shutdown. |
| `removeShutdownHook(Thread hook)` | Unregisters a hook; returns `true` if the hook was registered and removed. |
| `System.exit(int status)` | Common way to request the JVM to start shutdown with a status code. |
| `Runtime.exit(int status)` | Underlying API that `System.exit` uses. |
| `Runtime.halt(int status)` | Terminates the JVM immediately, skipping waiting for hooks and without initiating the shutdown sequence. |

**Hooks can only be added/removed when shutdown has not yet begun.** After the shutdown sequence begins, `addShutdownHook` and `removeShutdownHook` will throw `IllegalStateException`. Registering the same hook object again, or a `Thread` that has already run, is invalid and may throw `IllegalArgumentException`. In some Java 17 environments with a SecurityManager, related permission checks may also deny the operation.

## 3. How does the JVM run shutdown hooks?

Conceptual model:

~~~text
Running application
      |
      | no non-daemon threads left / System.exit / JVM-recognized event
      v
START SHUTDOWN SEQUENCE
      |
      +--> JVM starts hook A ---------------------+
      |                                           |
      +--> JVM starts hook B ---------------------+--> All hooks finish
      |                                           |          |
      +--> JVM starts hook C ---------------------+          v
      |                                              JVM exits
      +--> Running threads may still run
           concurrently during the shutdown phase
~~~

Things you must remember:

1. **The order of calling `start()` and the completion order of hooks are not guaranteed**. Registering A before B **does not mean A will run before B**.
2. **Hooks run concurrently**; each hook is a separate thread. Shared data must ensure thread safety, and closing the same resource needs coordination.
3. **The JVM waits for all hooks to finish** in a normal shutdown sequence. A hook that is stuck indefinitely can cause the process to hang during shutdown.
4. Hooks may run alongside other application threads; you should not assume "the entire application has stopped".
5. A hook that throws an uncaught exception is handled like a normal thread exception; that hook terminates, while other hooks can continue. Exceptions should not be used as a mechanism to "block the entire JVM".
6. **Creating and starting other threads** during the shutdown sequence can happen, but must be coordinated carefully: completion of the sequence is determined by *the hooks* finishing, not every additionally created task.

Therefore, two hooks that tightly depend on each other (for example, "close database" and "flush database write queues") are very prone to ordering bugs. The solution is usually to **combine steps that require a strict order into the same hook** or a lifecycle management component, rather than relying on registration order.

## 4. How does natural termination differ from `System.exit`?

**Natural termination:** when the last non-daemon thread finishes, the JVM starts shutdown. Registered hooks run and then the JVM exits.

**`System.exit(status)`:** requests active termination, **even when non-daemon threads remain**. This is a call that affects the *entire JVM process*, not merely stopping the calling thread. `System.exit(status)` is a convenient way to call `Runtime.getRuntime().exit(status)`.

- Common convention: **`status = 0`** indicates success; **nonzero** indicates an error or abnormal termination. The specific meaning of exit codes belongs to the application and the calling environment.
- When exit is accepted, the shutdown sequence is triggered; hooks are run and the JVM exits after they finish.
- The `exit` call does not return normally; lines of code after it in the same thread will not run.
- Do not assume running threads will finish their tasks on their own before the JVM exits: if not coordinated, they may be stopped when all hooks finish.

### Example 1 — `System.exit` still runs shutdown hooks

Create the file **`ExitDemo.java`**:

~~~java
public class ExitDemo {
    public static void main(String[] args) {
        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> System.out.println("hook: cleanup"), "cleanup"));

        System.out.println("main: request exit");
        System.exit(7);

        System.out.println("main: unreachable");
    }
}
~~~

Compile and run on **JDK 17+**:

~~~bash
javac ExitDemo.java
java ExitDemo
~~~

**Exact stdout** in a typical standalone run:

~~~text
main: request exit
hook: cleanup
~~~

The `System.exit(7)` call triggers the hook and then the JVM exits with **exit status 7**. The line `main: unreachable` is not printed. In this example there is only one hook and no other application work, so the order of the two lines is clear; with **multiple hooks** or threads running in parallel, the output order may not be fixed.

### When should you call `System.exit`?

In command-line programs, `System.exit` is appropriate if you need to return a specific exit code to the shell/CI or force the entire application to terminate. In libraries, request handlers, or framework-managed applications, calling `System.exit` from business code is usually inappropriate because it stops the **entire JVM**. It is usually better to return an error/exception to the orchestrator and let the application lifecycle be managed centrally.

## 5. `Runtime.halt`: immediate forced termination

**`Runtime.getRuntime().halt(status)`** forces the JVM to stop immediately. Unlike `exit`, it:
- **Does not start the shutdown sequence** if the sequence has not started.
- **Does not wait** for running shutdown hooks if the sequence has already started.
- May skip cleanup work, flushing, method completion, `finally`, `try-with-resources`, and unfinished exception handling.
- May lead to data loss, files/transactions in an incomplete state, logs not fully written, or other systems not receiving a clean termination signal.

When `halt` is called while an `exit` is waiting for hooks, the status code passed to `halt` can **override the intended exit status** of `exit`. `halt` is a last resort when the JVM must be stopped forcibly, not the default way to handle application errors.

### Example 2 — `halt` bypasses shutdown hooks

Create the file **`HaltDemo.java`**:

~~~java
public class HaltDemo {
    public static void main(String[] args) {
        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> System.out.println("hook: should not run")));

        System.out.println("main: before halt");
        System.out.flush();

        Runtime.getRuntime().halt(9);

        System.out.println("main: unreachable");
    }
}
~~~

Run in a **separate process** so it does not stop another program:

~~~bash
javac HaltDemo.java
java HaltDemo
~~~

**Program stdout**:

~~~text
main: before halt
~~~

The hook does not run; the line `main: unreachable` does not appear. The process exits with **status 9** when `halt(9)` is executed. `System.out.flush()` helps ensure the message before halt is pushed to the stream; one should not infer that `halt` flushes all I/O buffers or guarantees durable writes.

> **Experiment warning:** `System.exit`/`Runtime.halt` examples **terminate the JVM running them**. Test them using the `java ClassName` command in a separate process, and avoid calling them directly inside an IDE console/plugin host or a server hosting tasks serving users.

## 6. `finally`, try-with-resources, and shutdown hooks: different guarantee scopes

`finally` and **try-with-resources** help clean up resources in **normal Java control flow** or when an exception causes the stack to unwind. They are *not* a JVM-wide hook mechanism.

Example:

~~~java
public class ExitFinallyDemo {
    public static void main(String[] args) {
        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> System.out.println("hook: executed")));

        try {
            System.out.println("try: before exit");
            System.exit(5);
        } finally {
            System.out.println("finally: not executed");
        }
    }
}
~~~

Commands:

~~~bash
javac ExitFinallyDemo.java
java ExitFinallyDemo
~~~

**Stdout:**

~~~text
try: before exit
hook: executed
~~~

The `finally` block of the thread calling exit **is not executed**, because `System.exit` does not return and does not unwind the stack like a normal exception. The hook runs because the JVM enters the shutdown sequence. If you replace `System.exit(5)` with `throw new IllegalStateException("failed");`, `finally` will run as the stack unwinds; that is a completely different mechanism.

Comparison:

| Mechanism | When to use | What to keep in mind |
| --- | --- | --- |
| `try-with-resources`, `finally` | Closing connections/files/locks at the end of a work scope, even when an exception is thrown | Local, easily controlled cleanup; not guaranteed if the JVM is halted/killed or exit is called before unwinding. |
| Shutdown hook | Cleanup when the JVM starts the **shutdown sequence** | Runs best effort, concurrently, not guaranteed on forced termination. |
| `System.exit` / `Runtime.exit` | Actively initiating shutdown and providing an exit status | Process-level call; hooks get a chance to run; may affect active threads. |
| `Runtime.halt` | Forcibly terminating the entire JVM immediately | Bypasses or interrupts cleanup and hooks; risk of data loss. |

**Design principle:** use **try-with-resources for clearly scoped resources**, formal lifecycle management for service components, and shutdown hooks as a "safety net" for resources that live until the end of the process. Do not dump all application cleanup into hooks.

## 7. Designing safe shutdown hooks for multithreaded applications

A good shutdown hook needs to be **fast, time-bounded, idempotent when appropriate, and safe when running concurrently**. Typical graceful shutdown steps are:

1. **Stop accepting new work** (server/listener/job scheduler).
2. **Signal running work to stop in an orderly way**; if possible, wait for a finite period of time.
3. **Flush/commit necessary data**, then close queues, pools, connections, files, and telemetry/logging in dependency order.
4. **Return control from the hook** so the JVM can complete the shutdown sequence; if timed out, consider interrupting/canceling according to the component's protocol.
5. **Enforce ordering within a single hook or lifecycle coordinator**, instead of hoping independent hooks run in registration order.

### Example 3 — Shutting down an executor with a timeout

Create **`GracefulPoolDemo.java`**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class GracefulPoolDemo {
    public static void main(String[] args) {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            System.out.println("hook: stopping executor");
            pool.shutdown(); // Do not accept new tasks.
            try {
                if (!pool.awaitTermination(2, TimeUnit.SECONDS)) {
                    pool.shutdownNow(); // Request to interrupt running tasks.
                }
            } catch (InterruptedException ex) {
                pool.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }, "executor-shutdown"));

        pool.submit(() -> System.out.println("task: completed"));
        System.out.println("main: request exit");
        System.exit(0);
    }
}
~~~

Commands:

~~~bash
javac GracefulPoolDemo.java
java GracefulPoolDemo
~~~

**Lines that may appear:**

~~~text
task: completed
main: request exit
hook: stopping executor
~~~

This is **one valid output, not a guaranteed order**. The executor task may run before or after the line `main: request exit`; the hook also runs concurrently with the worker. In this simple example, the hook calls `shutdown()`, waits for the task to finish (up to two seconds), and then finishes. If a task does not stop when interrupted, `shutdownNow()` is only an **interrupt request**, not a mechanism that forces the task to definitely finish. Once the hook has finished, the JVM can still stop even if other work remains.

In real applications, you should **catch and log cleanup errors for each resource** so that one failed close does not accidentally skip subsequent close steps. If a resource can also be closed from another thread, use synchronization/state mechanisms to avoid dangerous double-closes. Do not block forever in `join()`, `awaitTermination()`, cross-locks, or network calls without timeouts.

## 8. Things to strictly avoid in shutdown hooks

### Calling `System.exit` from the hook itself

This is a serious bug: while the JVM is waiting for all hooks to finish, calling `System.exit`/`Runtime.exit` inside a hook can **block indefinitely** and prevent the shutdown process from completing. To report a cleanup error, **record/log it** and let the hook finish; do not call `exit` again.

### Waiting for another hook or depending on a resource another hook is closing

Because hooks run concurrently without ordering, **hook A waiting for B**, while B needs a lock held by A, will deadlock. Similarly, waiting for a service (logging, AWT event thread, thread pool) that has already been closed by another hook can hang. If there is a dependency chain A→B→C, have a lifecycle coordinator actively order them, or design each closing step with a clear contract.

### Performing overly long transactions/computations

Platforms like containers/orchestrators may only give the process a finite **grace period** before forcing a stop. A hook's job is to finish quickly; it is not the right place for long backups, user interaction, or launching new business workflows. You still need to save/commit periodically during normal processing flow.

### Assuming hooks always run

Certain process kill commands, native crashes, power loss, or `Runtime.halt` can prevent hooks from running. Application design must support **crash recovery**, for example relying on transactions, durable logging, message acknowledgment, or retry/idempotency mechanisms, rather than using hooks as the sole place to save state.

### Using hooks to "rescue" unwritten data on process loss

A hook is **best-effort cleanup**. It does not replace journals/transactions, write-ahead logs, fsync when needed, recovery mechanisms, or a framework's graceful shutdown procedure. A `println` statement at termination also does not prove that data was durably written to disk.

## 9. Recognizing real-world issues

| Symptom | Cause to check | How to handle |
| --- | --- | --- |
| `main()` finishes but the Java process stays alive | Non-daemon threads, thread pools, or timers still not stopped | Check thread dump; close executors/services properly in their lifecycle. |
| Calling `System.exit` but the program does not exit | Hook hanging, deadlock, or waiting indefinitely on I/O | Take a thread dump during shutdown; add timeouts and log cleanup steps. |
| Logs from multiple hooks reverse order between runs | Hooks run concurrently, order not guaranteed | Combine dependent steps into a single coordinator. |
| Hook does not print logs on `kill -9` | SIGKILL does not let the JVM shut down cleanly | Use monitoring/crash recovery; do not rely on hooks for data durability. |
| Late hook registration throws `IllegalStateException` | JVM has already entered the shutdown sequence | Register during application startup; do not register while stopping. |
| Hook has not run yet but developer called `hook.start()` | Hook was started manually; violates the registration contract | Only create and call `addShutdownHook`, let the JVM start it. |
| Adding the same hook a second time throws `IllegalArgumentException` | `Thread` object already registered or already run | Manage a single registration per hook. |
| Server loses in-flight requests on exit | Shutdown sequence does not ensure business threads finish | Stop accepting requests, drain, apply timeout, and only then close resources. |
| Using `Runtime.halt` leaves logs/files incomplete | `halt` skips cleanup and cuts off threads | Use `halt` only when forced termination is mandatory and a recovery plan exists. |

### Server/container perspective

A service application usually has a **framework-orchestrated shutdown process**. For example, the framework may close HTTP listeners, cancel scheduled jobs, wait for in-flight requests, close pools, and flush logging. If you add your own hook, check whether it "competes" for resources with the framework's hook. For containers/orchestrators, check the signals sent to the Java process, the stop timeout, and resource limits. Do not assume that all environments send the same signal or always provide enough time.

## 10. Self-Check

**Question 1.** `main()` has returned, but a non-daemon `new Thread(...).start()` is still running. Must the JVM shut down immediately?

**Answer:** No. Living non-daemon threads usually keep the JVM running. The JVM begins natural shutdown when no non-daemon threads remain.

**Question 2.** Two hooks A and B are registered in the order A then B. Is B guaranteed to run after A and guaranteed to see resources already cleaned up by A?

**Answer:** No. Hooks are started in an unspecified order and run concurrently. You must design ordering/coordination yourself.

**Question 3.** Does `System.exit(4)` automatically run code in the `finally` block of the calling thread? Do registered hooks get run?

**Answer:** `System.exit` does not unwind the calling thread's stack like an exception, so it does not automatically run `finally` at that location. If the JVM starts the shutdown sequence successfully, shutdown hooks are run, except in forced termination cases or errors beyond guarantee.

**Question 4.** One hook waits indefinitely; all other hooks finish. When does the JVM exit normally?

**Answer:** When **all hooks** finish. If one hook hangs indefinitely, the shutdown sequence may not complete; `halt` or forced termination from the environment can cut it short, but with risk of data loss.

**Question 5.** `Runtime.halt(9)` is called before shutdown begins. Do hooks run and is `finally` guaranteed to run?

**Answer:** No. `halt` does not start the shutdown sequence and terminates the JVM immediately; hooks and `finally` are not guaranteed to execute.

**Question 6.** When an application receives SIGKILL on Linux, should you expect a hook to save the last transaction?

**Answer:** No. SIGKILL gives the JVM no opportunity to run cleanup. Consistency must be ensured through durable storage, transactions, and recovery on restart.

## 11. Mental Model

~~~text
Natural termination / System.exit / event handled by the JVM
                        |
                        v
                SHUTDOWN SEQUENCE
                 /      |      \
              hook A  hook B   hook C  (concurrent, no guaranteed order)
                 \      |      /
                      all done
                        |
                        v
                     JVM stops

Runtime.halt --------------> JVM stops immediately, skips/interrupts hooks

SIGKILL/crash -------------> JVM may be stopped, hooks not guaranteed
~~~

**Key takeaway:** a shutdown hook is a **cleanup opportunity before the JVM shuts down**, `System.exit` is a **request to start termination that executes the shutdown sequence**, and `Runtime.halt` is **forced termination without waiting for cleanup**. For services requiring high reliability, cleanup must be short, ordered, time-bounded, and paired with recovery mechanisms after sudden process death.

## Official Reference Documentation

- [Oracle JDK 17 — `java.lang.Runtime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): `addShutdownHook`, `removeShutdownHook`, `exit`, `halt`, and shutdown notes.
- [Oracle JDK 17 — `java.lang.System`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html): `System.exit`.
- [Java Virtual Machine Specification 21 — §5.7 JVM Termination](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.7): JVM termination cases.