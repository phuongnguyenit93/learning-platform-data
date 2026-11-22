# Differences Between Normal Termination, Uncaught Exceptions, and Forceful JVM Termination

## 1. Distinguishing Thread, JVM, and Process

When saying "the Java application terminates", you must identify the exact entity that is stopping:

- **Thread terminates:** the `run()` method completes or an uncaught `Throwable` escapes the thread. Other threads can still keep running.
- **JVM begins an orderly shutdown:** there are no remaining non-daemon threads, or code calls `System.exit(status)`, or the environment puts the JVM into a supported shutdown flow. The JVM launches registered shutdown hooks according to its rules and then terminates.
- **Process is forcibly terminated:** `Runtime.halt(status)`, `SIGKILL`, certain native crashes, or OS-forced kills can terminate all threads without running Java shutdown hooks.

**Exit code** is a result of the *process*, not a property of an individual thread. By convention, `0` usually indicates success and non-zero usually indicates an error, but the code alone does not tell the termination mechanism: `System.exit(7)` can run shutdown hooks; `Runtime.halt(7)` does not. An uncaught exception in a worker also does not necessarily give the process a non-zero exit code.

~~~text
A thread terminates
    |
    +-- Any non-daemon threads left? -- Yes --> JVM continues running
    |                                |
    |                                +-- No --> JVM begins shutdown
    |
    +-- System.exit(status) is called --> JVM begins shutdown
    |
Process receives Runtime.halt()/SIGKILL/severe crash
    |
    +-- Abrupt termination; do not expect Java shutdown hooks
~~~

These paths are independent: a `SIGKILL` from the operating system does not wait for any Java thread to finish.

## 2. Comparison Table of the Three Scenarios

| Aspect | Normal Completion | Uncaught Exception | Forceful Termination |
| --- | --- | --- | --- |
| Examples | `main()` returns and non-daemon threads finish; or `System.exit(status)` requests shutdown | `IllegalStateException` escapes `main()`/`run()` | `Runtime.halt()`, `SIGKILL`, OS/container forced kill, some native crashes |
| Entity that terminates first | The thread completes or the JVM receives a shutdown command | **The thread carrying the exception** dies first; the JVM may still remain active | Usually **the entire process** is stopped |
| `finally` | Runs when leaving scope normally; however, `System.exit()` **does not unwind the stack** to execute `finally` | Runs when stack unwinding passes through the `finally` block, unless another abrupt stop path occurs | Not guaranteed; `halt`/`SIGKILL` do not unwind the Java stack |
| Shutdown hooks | Run when the JVM actually performs an orderly shutdown | Only run **if the JVM subsequently shuts down** | Do not run with `Runtime.halt()`/`SIGKILL`; with a crash they also cannot be relied upon |
| Exit status | Natural completion of `main` is usually `0`; `System.exit(status)` uses the requested status | A `main` uncaught exception usually produces a non-zero code on the Java launcher; a worker failing alone does not yet cause process exit | `Runtime.halt(status)` uses `status`; OS signals are platform-determined |
| Cleanup | Can use scope/`try-with-resources`; hooks assist shutdown | The failing thread's `finally` may run; other threads remain responsible for their own cleanup | Must assume Java cleanup may not have run |

**Natural** termination and **intentional** shutdown via `System.exit()` can both have hooks, but they do not share the same control flow path: `System.exit()` does not return normally, so `finally` blocks on the stack that called `exit` are not executed just because shutdown has started.

## 3. Natural Termination: `main` Returning Does Not Necessarily Mean JVM Exit

The JVM usually begins natural shutdown when **all started non-daemon threads have terminated**. The `main` thread created by the launcher is normally non-daemon, but it is not necessarily the last non-daemon thread.

- `main()` returns while a non-daemon worker remains: the process continues.
- `main()` returns and no non-daemon threads remain: the JVM begins shutdown.
- Daemon threads do not keep the JVM alive; a daemon currently doing work may not finish when the JVM shuts down.
- A new thread usually inherits the daemon status from the thread that created it (unless a factory/tool specifies otherwise). You should not assume every thread created by every library is non-daemon.

Create the file **MainReturns.java**:

~~~java
public class MainReturns {
    public static void main(String[] args) {
        Thread worker = new Thread(() -> {
            try {
                Thread.sleep(200);
                System.out.println("WORKER_DONE");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                System.out.println("WORKER_INTERRUPTED");
            }
        }, "worker");

        worker.start();
        System.out.println("MAIN_RETURN");
    }
}
~~~

~~~bash
javac --release 17 MainReturns.java
java MainReturns
~~~

An uninterrupted execution produces the output:

~~~text
MAIN_RETURN
WORKER_DONE
~~~

`main()` returned first, but the non-daemon worker kept the JVM alive. The sleep duration only illustrates the ordering; in real applications, use `join()`, `Future`, appropriate structured concurrency, or a managed `ExecutorService` lifecycle. If a non-daemon thread pool is not shut down, the application may "refuse to exit" even though `main()` has finished.

### `System.exit()` Is a Shutdown Request, Not a Return

`System.exit(status)` invokes the `Runtime.exit(status)` mechanism, requesting JVM termination with the corresponding status code, even if other non-daemon threads are still running. The JVM enters the shutdown sequence and runs registered hooks. The call **does not return normally** and does not proactively unwind the entire stack of the current thread; if resources need to be closed in a `try` block, perform cleanup **before calling exit**.

## 4. Uncaught Exceptions: Only the Failing Thread Terminates First

When a `Throwable` is not caught and escapes the root method of a thread, that thread dies. The JVM may pass the `Throwable` to an `UncaughtExceptionHandler` to report the error. The handler records the incident; it **does not resume running** the code that threw the exception.

For the `main` thread:

1. As the exception propagates through scopes, the corresponding `finally` and `try-with-resources` blocks have a chance to perform cleanup during stack unwinding.
2. If the exception escapes `main()`, the `main` thread terminates. The default handler of the Java launcher usually prints the stack trace to **stderr**.
3. If non-daemon threads remain, the JVM can still keep running. If none remain, the JVM begins shutdown and hooks are launched.
4. With common Java launchers, an uncaught exception in `main` usually produces a non-zero exit status, but the JVM specification does not require every error in every thread to produce a fixed exit code.

For worker threads, other threads can continue operating normally. In `ExecutorService`, behavior depends on how tasks are submitted: an error in a `Future` is usually stored so that `Future.get()` throws `ExecutionException`; it does not necessarily go through the default uncaught handler. Do not equate "a task threw" with "the VM died".

`UncaughtExceptionHandler` is a path for **observing failure**, not a `catch` capable of letting the thread continue. If the handler itself errors, that handler also does not help recover the thread.

## 5. Orderly JVM Shutdown and Shutdown Hooks

Register before shutdown begins:

~~~java
Runtime.getRuntime().addShutdownHook(
        new Thread(() -> System.out.println("cleanup"), "cleanup-hook"));
~~~

When the JVM shuts down in an orderly manner, it starts the registered hooks and waits for them to finish. Points to understand accurately:

- Multiple hooks run in an **unspecified** order and may run **concurrently**. Do not design hook A to have to finish before hook B starts.
- Hooks cannot be added or removed once shutdown has started; the operation may throw `IllegalStateException`.
- Hooks must be fast, able to handle errors, and avoid waiting indefinitely. If a hook deadlocks itself, the process may hang during the shutdown phase.
- Other application threads may still be running during the shutdown sequence; do not assume they have been joined or that their resources are still in a ready state.
- Calling `System.exit()` from a running hook may block indefinitely; do not use it to "exit again".
- Hooks are not guaranteed to run on `Runtime.halt()`, `SIGKILL`, or sudden crashes/OS kills; hooks may also be cut short if an orchestrator's grace period expires.

Hooks are suitable for bounded final cleanup and final logging; they are not the sole place to put transaction commits, critical message emission, or flushing of all unpersisted data.

## 6. Forceful Termination: `Runtime.halt`, `SIGKILL`, Signals, and Crashes

**`Runtime.getRuntime().halt(status)`** terminates the JVM immediately, **without launching shutdown hooks** and without performing Java stack unwinding for pending `finally` blocks. It is a special mechanism, not a standard API for ending normal business logic.

Several process-level termination paths:

- **`SIGKILL` / `kill -9`** on Unix/Linux cannot be caught or delayed by the process; Java hooks have no chance to run.
- **Container/OS forced kill:** the management system may send a stop signal and grant a grace period, then kill the process if it has not exited yet.
- **Native/JVM crash:** may abort the process; some JVMs such as HotSpot may generate `hs_err_pid*.log` or a core dump if conditions allow, but a file is not guaranteed in all cases.
- **Power loss/OS death:** data residing only in RAM, buffers, or not yet synced to storage may be lost.

You must distinguish **`SIGTERM`** from **`SIGKILL`**. `SIGTERM` is usually a *handleable* stop request: HotSpot on many Linux/Unix environments typically translates it into a shutdown with hooks, though behavior depends on the JVM implementation, native signal handlers, and host/configuration. **`SIGKILL`** is always an uncatchable forced kill. `Ctrl+C`, `SIGINT`, `ProcessHandle.destroy()`, and service stop operations also have platform-dependent details. Do not promise that all operating systems will run hooks upon receiving a "stop command".

## 7. Verification Experiment on Java 17+

Create the file **JvmExitCases.java**. Each invocation of the `java` command is **a separate process**, so that `exit`/`halt` does not affect other experiments:

~~~java
public final class JvmExitCases {
    private static void log(String message) {
        System.out.println(message);
        System.out.flush();
    }

    public static void main(String[] args) throws InterruptedException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Choose normal, uncaught, worker, exit, or halt");
        }

        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> log("HOOK"), "cleanup-hook"));

        String mode = args[0];
        if ("worker".equals(mode)) {
            Thread worker = new Thread(() -> {
                throw new IllegalStateException("worker-boom");
            }, "worker");

            worker.setUncaughtExceptionHandler((thread, error) ->
                    log("HANDLER: " + thread.getName() + ": "
                            + error.getClass().getSimpleName()));

            worker.start();
            worker.join();
            log("MAIN_CONTINUES");
            return;
        }

        try {
            log("BODY");
            switch (mode) {
                case "normal" -> { }
                case "uncaught" -> throw new IllegalStateException("boom");
                case "exit" -> System.exit(7);
                case "halt" -> Runtime.getRuntime().halt(9);
                default -> throw new IllegalArgumentException(
                        "Unknown mode: " + mode);
            }
        } finally {
            log("FINALLY");
        }
    }
}
~~~

Compile and run each mode separately:

~~~bash
javac --release 17 JvmExitCases.java
java JvmExitCases normal
java JvmExitCases uncaught
java JvmExitCases worker
java JvmExitCases exit
java JvmExitCases halt
~~~

To check the exit code **immediately after the command to inspect**:

~~~bash
# Bash on Linux/macOS
java JvmExitCases exit
echo $?

# PowerShell on Windows
java JvmExitCases exit
echo $LASTEXITCODE
~~~

### 7.1. normal

Stdout:

~~~text
BODY
FINALLY
HOOK
~~~

`main` finishes, `finally` runs; when no non-daemon threads remain, the JVM enters shutdown and runs the hook. The typical exit code is **0**.

### 7.2. uncaught

The **stdout** lines:

~~~text
BODY
FINALLY
HOOK
~~~

In addition, by default there is the `IllegalStateException` stack trace with message `boom` on **stderr**. When merging both streams, the appearance order between the stack trace and the `HOOK` line may vary. On common Java launchers the exit code is non-zero (OpenJDK is typically `1`); do not rely on the value `1` as a guarantee from the JVM specification. The difference from `normal` here is that **main died due to an exception**, even though the hook still ran when the JVM shut down.

### 7.3. worker

Stdout:

~~~text
HANDLER: worker: IllegalStateException
MAIN_CONTINUES
HOOK
~~~

`worker` dies; the custom handler logs the error; `main`'s `join()` sees the thread has finished and continues. The JVM only shuts down when `main` returns and no non-daemon threads remain. The typical exit code is **0**. Because a custom handler was installed that does not print the stack trace, the example does not have the worker's default stack trace.

### 7.4. exit

Stdout:

~~~text
BODY
HOOK
~~~

There is no `FINALLY`. `System.exit(7)` requests shutdown with hooks, but **does not** exit through `finally` on the current stack; the exit code is **7**.

### 7.5. halt

Stdout was proactively flushed before `halt`:

~~~text
BODY
~~~

There is no `FINALLY` and no `HOOK`; the exit code is **9**. Flushing in the example allows the `BODY` line to be observed, but `halt` can lose data in other buffers. Do not use the `halt` path for normal application processing logic.

**Practical verification:** this code was compiled with JDK 21 using `--release 17` and run in all five modes. The stdout output and statuses were 0, 1, 0, 7, and 9 respectively in the verification environment; `main`'s exception lines are on `stderr`, and how streams are interleaved by logging tools is not fixed.

## 8. How `finally`, `try-with-resources`, and Shutdown Hooks Differ

| Mechanism | When to Use | Limitations |
| --- | --- | --- |
| `try-with-resources` | Closing an `AutoCloseable` upon leaving scope, including when an exception traverses the scope | A `halt`/kill before leaving scope can leave cleanup unfinished |
| `finally` | Handling when exiting a `try` block via normal control flow or exception stack unwinding | `System.exit` does not automatically run `finally` blocks currently on the stack; neither does `halt`/kill |
| Shutdown hook | Cleaning up when the JVM actually begins an orderly shutdown | Does not run on all termination paths; ordering across multiple hooks is unspecified |

Example of closing a writer by scope, without waiting for a shutdown hook:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class ScopedResource {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("sample.txt");
        try (var writer = Files.newBufferedWriter(path)) {
            writer.write("important data");
        }
        System.out.println("FILE_CLOSED");
    }
}
~~~

On the success path, `writer` is closed before `FILE_CLOSED` is printed; if `write()` throws `IOException`, `try-with-resources` still attempts to close `writer`. Even so, **`close`/`flush` at the Java layer does not mean data has been fsynced/made durable against power loss**. Data preservation requires designing appropriately for the storage system, transactions, retries, and recovery.

Do not wait until shutdown to commit all messages, transactions, or business state. Recording progress per unit of work and having safe retry mechanisms help the application withstand `SIGKILL` or crashes.

## 9. When a Program "Refuses to Exit" or Dies Unexpectedly, How to Investigate?

1. **Confirm whether the JVM/process is still alive or dead.** If `main` finishes but the process does not exit, check non-daemon threads, thread pools, network services, and thread dumps.
2. **Inspect exit status, stack traces, `stderr`, and lifecycle logs.** A worker's uncaught exception does not prove the process died; a non-zero exit code does not prove `SIGKILL`.
3. **Inspect the source of the stop request:** `System.exit`, signal, service manager, container orchestrator, OOM killer, timeout, native crash. For containers, also check restart reasons and grace periods.
4. **Check whether hooks started/finished:** a hook may hang due to a lock, `join`, network call, or dependence on a stopped thread. Missing the `HOOK` line does not by itself prove `SIGKILL` because logs can also be lost.
5. **Verify external resources:** database commits, message acks, file flush/sync, lease timeouts, and replay capability. Merely seeing a cleanup log does not guarantee data was persisted.
6. **Fix at the right lifecycle:** close executors/servers according to protocol, stop accepting new work, wait for a bounded timeout, and then complete in a controlled manner; keep hooks concise and bounded.

Common misconceptions:

- "`main()` returning means the process exits": false if non-daemon threads remain.
- "An uncaught exception always kills the JVM": false, first it only terminates the failing thread.
- "`System.exit` runs all `finally` blocks": false; it uses shutdown hooks rather than unwinding all stacks.
- "`System.exit(7)` is the same as `Runtime.halt(7)`": false, same status but different cleanup.
- "`SIGTERM` is the same as `SIGKILL`": false, `SIGTERM` can be handled, `SIGKILL` cannot.
- "Hooks run in registration order": false, the order is unspecified and may be parallel.
- "Having a shutdown hook guarantees data safety on power loss": false.

## 10. Self-Check Questions

1. `main` throws an uncaught `RuntimeException`, but a non-daemon worker is still alive: must the JVM exit immediately? **No.**
2. Why does `worker` mode have a handler that prints an error yet the normal exit code is still 0? **The worker died, `main` continued to completion, and no error status was requested for the process.**
3. Does `System.exit(0)` execute a `finally` block enclosing that very call? **No; it initiates shutdown rather than returning from the scope via normal control flow.**
4. Does `Runtime.halt(0)` invoke shutdown hooks? **No.**
5. Do daemon threads keep the JVM alive after all non-daemon threads terminate? **No.**
6. Does seeing `HOOK` prove all data has been durably written? **No; the corresponding commit/ack/fsync must be verified.**

**Technical conclusion:** natural completion and `System.exit()` can produce an orderly shutdown; uncaught exceptions kill **the thread carrying the error** first; `Runtime.halt()`, `SIGKILL`, and forceful kills can stop **the entire process** without shutdown hooks. Design cleanup around resource scopes, manage non-daemon threads, observe errors at task boundaries, and build recovery mechanisms for all critical work.
