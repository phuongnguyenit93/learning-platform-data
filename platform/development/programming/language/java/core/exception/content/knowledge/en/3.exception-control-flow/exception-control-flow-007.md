# Uncaught Exceptions and Termination of the Current Thread in Java

An exception is considered an **uncaught exception** for an execution thread when it propagates through all active calls on that thread without **encountering a matching `catch`**. In a regular Java `Thread`, an exception escaping the thread's execution entry point triggers the uncaught-error reporting mechanism, and **that thread terminates**.

Key points to distinguish:

- **An uncaught exception in a thread** can terminate **the running thread**.
- **Terminating a thread** does not mean **every other thread** or **the entire JVM process** stops immediately.
- **Where the thread terminates** is different from **where the error is reported**: an `UncaughtExceptionHandler` can record the incident, but it does not return the thread to the failed statement.
- With `ExecutorService.submit()`, a task's exception can be **stored in the `Future`** and reported back to the caller via `Future.get()`. Therefore, you must not infer that every exception thrown inside a task always escapes to the thread's uncaught handler.

This lesson explains the propagation path of an exception, when a thread terminates, the handler mechanism, the impact on the application, and how to proactively place proper handling boundaries.

## 1. What Does “Uncaught” Mean?

Consider a call:

```java
static int parseAge(String raw) {
    return Integer.parseInt(raw);
}

static void process(String raw) {
    int age = parseAge(raw);
    System.out.println("Tuổi: " + age);
}
```

These are **two illustrative methods** that need to be placed inside a Java class. If `process("abc")` is called, `Integer.parseInt` throws `NumberFormatException`. The `parseAge` method has no matching handler, so the exception propagates out to `process`. `process` also has no handler, so the `println` line does not run. The exception continues moving up the active calls.

There are two possibilities:

1. A caller wraps the call in a compatible `try-catch`, for example `catch (NumberFormatException ex)`. The exception is caught there, and the program can execute a recovery policy or error response.
2. There is no matching handler along the execution path. The exception escapes the thread's entry point; this is an **uncaught exception** for that thread.

You should not call an exception “uncaught” just because the method where it originates has no `catch`. It can still be caught by an upper-level caller; in that case it is **handled** and does not lead to thread termination from that exception.

### Propagation Path on the Call Stack

```text
Running thread
  run() or main()
    └── handleRequest()
          └── execute()
                └── parse()
                      └── throw NumberFormatException
                             ↓
                   parse() has no catch
                             ↓
                   execute() has no catch
                             ↓
                   handleRequest() has no catch
                             ↓
             run()/main() has no matching catch
                             ↓
                Uncaught exception
                             ↓
                Thread terminates
```

During propagation, active calls undergo **abrupt completion**. Statements following the failed call point do not automatically continue running. The JVM performs stack unwinding, during which active `finally` blocks and resource cleanup operations under `try-with-resources` are executed according to Java rules.

## 2. Which Thread Terminates When There Is No `catch`?

Each `Thread` has its own call stack. An uncaught exception terminates **the thread from which the error escapes**, rather than automatically propagating to another thread's call stack.

For example:

- If `main` directly calls a method that throws an exception without catching it, the exception can escape the **main thread**.
- If a custom `Thread` executes `Runnable.run()` and an error escapes `run()`, **that worker thread** terminates.
- If thread A called `worker.start()` to launch thread B, an exception occurring in B **is not automatically rethrown into A**. `start()` only starts the work; it does not turn B into a synchronous call on A's stack.
- If A calls `worker.join()` to wait for B to finish, `join()` **does not automatically rethrow the exception that killed B**. `join()` can throw `InterruptedException` if A itself is interrupted while waiting, but that is a different mechanism.

For a terminated `Thread`, its final state is `Thread.State.TERMINATED`. You **cannot call `start()` a second time on the same `Thread` object**; doing so causes `IllegalThreadStateException`. To run the work again, you must create a new thread/task or design an explicit retry mechanism.

### Does the JVM Stop When the Main Thread Dies?

**Not always.** In a typical Java program, the JVM exits when no **non-daemon** threads remain alive (aside from other ways of stopping the process such as `System.exit`). Therefore:

- If the main thread has an uncaught exception and **no other non-daemon threads remain**, the process usually terminates.
- If another non-daemon worker is still running, the main thread's termination **does not automatically kill that worker**. The process may continue running.
- A daemon thread **does not keep the JVM running by itself** once all non-daemon threads have finished. Therefore, you should not rely on daemon threads to complete critical work during application shutdown.

Three concepts must be separated: **failure of a task**, **termination of a thread**, and **termination of the JVM/process**. They may be related, but they are not identical.

## 3. Java 17+ Example: Worker Fails, Main Continues

To observe the result **consistently, without depending on the JVM's stack trace format**, we attach an `UncaughtExceptionHandler` to the worker. The handler only prints deterministic information and lets the thread terminate.

Save the entire program as **`UncaughtThreadDemo.java`**:

```java
public class UncaughtThreadDemo {

    static void doWork() {
        System.out.println("worker: bắt đầu");
        throw new IllegalStateException("không xử lý được dữ liệu");
    }

    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(
                UncaughtThreadDemo::doWork, "job-worker");

        worker.setUncaughtExceptionHandler((thread, error) -> {
            System.out.println(
                    "handler: " + thread.getName()
                    + " -> " + error.getClass().getSimpleName()
                    + ": " + error.getMessage());
        });

        System.out.println("main: khởi động worker");
        worker.start();
        worker.join();

        System.out.println("main: worker còn sống = " + worker.isAlive());
        System.out.println("main: tiếp tục sau join");
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 UncaughtThreadDemo.java
java UncaughtThreadDemo
```

**Exact stdout in a normal run, with no other thread interrupting main:**

```text
main: khởi động worker
worker: bắt đầu
handler: job-worker -> IllegalStateException: không xử lý được dữ liệu
main: worker còn sống = false
main: tiếp tục sau join
```

### Step-by-Step Walkthrough

1. The main thread creates a `Thread` object named `job-worker` and attaches a dedicated handler using `setUncaughtExceptionHandler`.
2. Main prints `"main: khởi động worker"` **before** calling `worker.start()`. Thus, that line appears before the worker's first line.
3. The worker starts executing `doWork()`, prints `"worker: bắt đầu"`, and then throws `IllegalStateException`.
4. There is no `catch` on the worker's exit path, so the uncaught-exception mechanism invokes the handler attached to this thread. The handler runs **on the failing worker thread itself**, printing the thread name, exception class name, and message.
5. After the worker's termination process completes, `worker.join()` in main returns. At that point `worker.isAlive()` is `false`.
6. Main still continues to print the final line: the worker's error does not automatically jump into `main` as a new exception.

The handler **cannot repair the failing stack**: after the handler finishes running, the worker does not return to `doWork()` to execute the next statement. If a retry is needed, place retry logic at the orchestration layer and create a new task with appropriate limits/controls.

## 4. Without a Dedicated Handler: What Happens by Default?

Each thread can have its own `Thread.UncaughtExceptionHandler`. When a thread is about to terminate due to an uncaught exception, the JVM passes the thread and `Throwable` information to the handler determined by `Thread`'s mechanism.

There are three common levels:

- **Thread-specific handler:** set via `thread.setUncaughtExceptionHandler(handler)`.
- **Application-wide default handler:** set via `Thread.setDefaultUncaughtExceptionHandler(handler)`, acting as a global observation point when used by the handler selection mechanism.
- **`ThreadGroup` / default behavior:** if a thread has no specific handler, its thread group performs delegation; when no other default handler is set, standard Java implementations typically report the exception and stack trace to `System.err` (except in special cases such as `ThreadDeath`).

In common development environments, if the main thread throws an uncaught `IllegalStateException`, stderr looks like:

```text
Exception in thread "main" java.lang.IllegalStateException: ...
    at Example.someMethod(Example.java:...)
    at Example.main(Example.java:...)
```

This is an **illustrative pattern**, not a fixed output: file names, line numbers, stack trace, formatting, and message content depend on the actual code and environment. With a custom handler, the output can also be completely different.

### How to Read the Default Message

- `Exception in thread "main"`: the name of the thread from which the exception escaped.
- `java.lang.IllegalStateException`: the **actual type** of the exception.
- The part after the colon: the message, if any.
- The `at ...` lines: the call path at the time the stack trace was recorded; they indicate the origin point and the callers.
- The `Caused by: ...` sections (if any): the cause chain passed via `Throwable.getCause()` or a constructor accepting `cause`.

**Stack traces help with diagnosis, but they are not a stable string-based error classification API.** You should not build business logic based on searching for method names or messages in stderr.

## 5. What Can and Cannot `UncaughtExceptionHandler` Do?

A handler is registered with:

```java
thread.setUncaughtExceptionHandler((currentThread, error) -> {
    // Log, count failed tasks, send internal signals...
});
```

This is an **illustrative snippet**; the `thread` variable must be an already-created `Thread` object.

The handler receives:

- `currentThread`: the thread that is terminating due to the error.
- `error`: the uncaught `Throwable` object, containing its type, message, cause, and stack trace for diagnosis.

Appropriate actions typically include:

1. Recording the thread name, exception type, cause, and non-sensitive task ID.
2. Notifying a monitoring or orchestration mechanism that **the task/thread failed**.
3. Deciding at **another layer** whether to launch a new task, fail the request, or perform a controlled service shutdown.
4. Retaining enough context for investigation while avoiding logging tokens, passwords, or sensitive personal data.

**Incorrect** assumptions:

- The handler is not a `catch` block that lets the thread return to the `throw` point.
- The handler does not automatically restart the dead `Runnable`.
- The handler does not automatically roll back transactions, undo file changes, or release leaked resources.
- The handler does not guarantee that information reached monitoring if the logging/transport mechanism itself fails.
- You should not rely on the handler throwing another exception to re-handle it: by Java's contract, an exception thrown by `uncaughtException` itself is not turned into a reliable thread recovery mechanism.

In particular, the callback is invoked in the **context of the failing thread**. If the handler performs an operation that can block for a long time, the thread's termination process and any caller in `join()` can be delayed. Keep handlers short and safe, avoid deadlocks, and think carefully about error handling inside the handler itself.

### The Default Handler Has a Broad Scope

`Thread.setDefaultUncaughtExceptionHandler` changes the error-reporting policy at the JVM level, so it can affect threads not directly managed by a single module. For shared libraries, it is usually best to let the application decide the default handler rather than altering the global policy.

## 6. Catching Errors at the `run()` Boundary for Proactive Application Recovery

If you want a worker not to terminate unexpectedly when a business operation fails, design a handling boundary inside `run()` or directly around the operation that may fail:

```java
Runnable task = () -> {
    try {
        processOneMessage();
    } catch (IllegalArgumentException ex) {
        System.out.println("Bỏ qua thông điệp sai định dạng");
    }
};
```

This is an **illustrative code snippet** and needs to be placed in a method that has `processOneMessage()` and the appropriate imports/dependencies. This approach can keep the worker alive if a loop processing other messages is designed to continue running.

Only catch exceptions that you **actually have a plan to handle**:

- Malformed data in a message: logging the error and skipping the message according to policy may be reasonable.
- Database connection exhaustion: you may retry within limits, move the task to a queue, or report a failed status.
- Unrecoverable internal invariant violation: trying to continue can be more dangerous than terminating and letting the orchestration layer detect it.
- `OutOfMemoryError`, `StackOverflowError`, and other `Error` types: should not be treated as ordinary business errors with `catch (Throwable)` to keep running.

With a standard `Runnable.run()`, the signature does not allow declaring `throws` for a broad checked exception like `IOException`. Therefore, you must **catch checked exceptions inside**, deliberately wrap/convert them into unchecked exceptions, or use a task API like `Callable<V>` when a contract declaring checked exceptions is needed.

Example of an independent work boundary that requires cleanup before the thread terminates:

```java
static void runJob() {
    try {
        performJob();
    } catch (IllegalArgumentException ex) {
        reportBadInput(ex);
    } finally {
        releaseJobResources();
    }
}
```

This is a **design skeleton**, not a standalone program; `performJob`, `reportBadInput`, and `releaseJobResources` must be defined. `finally` usually runs when leaving `try` whether an error occurred or not. However, `finally` can also throw an exception and mask the original cause; closing `AutoCloseable` resources should generally use `try-with-resources`.

## 7. `ExecutorService`: Task Errors Are Not Always Uncaught Exceptions of the Worker Thread

In concurrent applications, many tasks are submitted to a thread pool via `ExecutorService`. You must distinguish **task failure** from **an exception escaping the worker thread's own run loop**.

With `executor.submit(Callable)` or `submit(Runnable)`, the executor returns a `Future`. If the task body throws an exception, the task execution is marked as failed; calling `future.get()` reports it with `ExecutionException`, where `getCause()` holds the task's underlying cause.

### Complete Java 17+ Example: Error Propagated via `Future`

Save as **`FutureFailureDemo.java`**:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureFailureDemo {

    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<Integer> result = pool.submit(() -> {
                System.out.println("task: bắt đầu");
                throw new IllegalStateException("không thể tính kết quả");
            });

            try {
                int value = result.get();
                System.out.println("result: " + value);
            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause();
                System.out.println(
                        "main: task thất bại vì "
                        + cause.getClass().getSimpleName()
                        + ": " + cause.getMessage());
            }

            System.out.println("main: vẫn hoạt động");
        } finally {
            pool.shutdown();
        }
    }
}
```

Compile and run commands:

```bash
javac -encoding UTF-8 FutureFailureDemo.java
java FutureFailureDemo
```

Stdout under normal running conditions:

```text
task: bắt đầu
main: task thất bại vì IllegalStateException: không thể tính kết quả
main: vẫn hoạt động
```

**Explanation:**

- `submit` returns a `Future<Integer>` representing **the task's result**, not a direct reference to a `Thread`.
- The task lambda throws `IllegalStateException`. In the standard executor `Future` mechanism, the error is recorded as the task's failed outcome.
- `result.get()` waits for the task to complete and then throws `ExecutionException`; `getCause()` is the original `IllegalStateException`.
- The `result: ...` line does not run because `get()` does not return an `int`.
- Main continues after `catch`. `pool.shutdown()` instructs the executor to stop accepting new tasks and terminate after already-accepted tasks complete. In the example, the task has already finished when `get()` returns/throws.

An exception that has been **caught by the framework and placed into a `Future`** is not an “uncaught exception escaping the worker thread” simply because the code inside the lambda has no `catch`. Consequently, a thread-level handler may not be invoked for this failure.

### `execute`, `submit`, and Other Asynchronous Tasks

With `Executor.execute(Runnable)`, how a task exception escapes can differ from `submit`, because no result `Future` is returned. For example, in the standard `ThreadPoolExecutor`, an unchecked exception escaping a `Runnable` passed to `execute` enters the worker's failure handling and can reach the thread's handler, after which the executor may allocate a replacement worker if needed. Those details belong to the executor's mechanism and implementation configuration, and **you should not assume all executor types behave identically**.

With `CompletableFuture`, errors can be observed via `get()` (wrapped in `ExecutionException`) or `join()` (typically throwing `CompletionException`). Choose where to observe the result and the handling policy of the API in use.

Key point to remember: to know whether an error becomes a **thread's uncaught exception**, you must examine **who stands at the execution boundary** and whether the framework catches/stores the error before it escapes the thread.

## 8. Where Do `try-catch` and `finally` Fit in Thread Termination?

When an uncaught exception is propagating back up the stack, `finally` blocks are executed according to language rules. For example:

```java
static void job() {
    try {
        System.out.println("đang xử lý");
        throw new IllegalStateException("thất bại");
    } finally {
        System.out.println("dọn dẹp");
    }
}
```

This is an **illustrative method**. If the caller does not catch the error, the method prints:

```text
đang xử lý
dọn dẹp
```

and then `IllegalStateException` continues propagating upward. No “succeeded” line appears on its own.

### `try-with-resources` Should Be Preferred for Resources

If a resource implements `AutoCloseable`, use the construct:

```java
static String read(java.nio.file.Path path)
        throws java.io.IOException {
    try (var reader = java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
```

This is an **illustrative method**; an actual file must be specified when using it. The reader is closed upon leaving `try` even if the read operation throws `IOException`. If errors occur both inside the `try` body and while closing, Java can record the closing error as a **suppressed exception** to preserve the primary exception.

You should not rely solely on an uncaught handler to close connections, streams, or locks. The handler only receives the error once the failure has propagated to the thread's termination point; resource lifecycles must be managed **right where they are allocated/used**. Note that a `finally` block is not guaranteed to run if the process is terminated abnormally, such as via `Runtime.halt()` or being forcibly killed by the operating system.

## 9. `InterruptedException` Does Not Mean an Uncaught Exception

When a thread in `sleep()`, `wait()`, or `join()` is interrupted, those methods can throw **`InterruptedException`**. This is a **checked exception**; it signals an interruption/cancellation request during waiting, and does not inherently mean an unchecked error escaped the thread.

In `Runnable.run()`, an example of cancellation handling can be:

```java
@Override
public void run() {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            doOneStep();
        }
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
    } finally {
        closeResources();
    }
}
```

This is an **illustrative method skeleton**, assuming the class implements `Runnable`, `doOneStep()` can throw `InterruptedException`, and `closeResources()` is already defined. Calling `interrupt()` again restores the interrupt flag (methods like `sleep()` typically clear the flag when throwing `InterruptedException`), so the orchestration layer can observe the appropriate state. In this example, `run()` then exits in a controlled manner; this is not an uncaught `InterruptedException`.

If business logic needs to continue rather than terminate after being interrupted, there must be an explicit policy. Do not catch `InterruptedException` and silently ignore it, as that can prevent cancellation mechanisms from working as intended.

## 10. Where Should Errors Be Handled?

| Boundary | Handling Goal | Recommendation |
| --- | --- | --- |
| Inside business functions | Detect errors, preserve the meaning of the cause | `throw` a specific exception when a contract is violated |
| Calling layer capable of recovery | Retry, fix input, or transition to a business state | `catch` the appropriate type, limit retries, and preserve `cause` |
| `run()` boundary / task processing loop | Decide whether a failed task stops the loop | Catch handleable errors; close resources in the proper scope |
| `Thread.UncaughtExceptionHandler` | Record that a thread failed unexpectedly | Keep logging/monitoring brief; do not treat it as a stack recovery point |
| Caller of `Future.get()` | Observe success/failure of a submitted task | Catch `ExecutionException`, inspect `getCause()` |
| Application orchestration layer | Decide on retries, alerts, service shutdown, or user response | Base decisions on policy and whether the system remains in a safe state |

For example, a message-reading consumer can handle formatting errors per message and continue with the next message. However, if an error corrupts internal state beyond recovery, keeping the thread alive by ignoring the exception can allow bad data to spread. Do not lump both situations into a single `catch (Exception ignored)`.

## 11. Common Pitfalls

### “If the worker fails, main automatically receives the error”

Incorrect. `Thread.start()` creates an independent execution thread; `join()` only waits for the thread to finish. If you need to pass a result or error back to the caller, use `Future`, `CompletableFuture`, a message queue, properly synchronized state, or a well-designed reporting mechanism.

### “If the main thread dies, the entire application stops immediately”

Not true in all cases. Other non-daemon threads can keep the JVM alive. Conversely, the application can also terminate after a worker error if no non-daemon threads remain to keep the JVM running. You must consider the actual lifecycle of threads/processes.

### “Having an uncaught handler means the error is caught and recovered”

The handler **receives a notification as the thread is terminating**. It is not equivalent to a `try-catch` placed before the error exit point and does not resume an unwound stack. To recover, place logic where it can proactively handle the error or orchestrate a new task.

### “Using `catch (Throwable)` to keep the thread alive is safe”

Catching `Throwable` can swallow severe `Error`s such as `OutOfMemoryError`. In many cases, the application is no longer in a valid state to continue. Choose the right exception types and define a safe termination policy instead of returning a false success status.

### “`finally` guarantees every failure is cleaned up”

`finally` helps clean up when exiting a `try` region under Java rules, but it does not replace proper resource management, does not roll back all changes, and is not guaranteed in every abnormal JVM termination. Throwing another exception inside `finally` can also mask the original cause.

### “`submit` throws an error in the worker, so it will always print a stack trace”

Not necessarily. With `submit` on a standard executor, task errors are typically recorded in the `Future` and only surface when observed/logged. If you do not read the `Future` or monitor the result, errors risk being silently lost. Therefore, you need a standard way to observe the success/failure of each task.

### “`join()` succeeding means the task succeeded”

Incorrect. `join()` only indicates that the thread has terminated (when it returns normally). The thread may have terminated because it completed its work or because of an uncaught exception. The `TERMINATED` state does not carry a business outcome; there must be a separate reporting channel.

### “You can call `start()` again on a `TERMINATED` thread”

Incorrect. A `Thread` object can only be `start()`ed once. A task that needs to be retried must be executed in a new thread or managed by an appropriate executor.

## 12. Practice Scenarios and Conclusion

**Scenario 1:** Worker B throws `IllegalArgumentException` with no `catch` and no custom handler; main A is waiting on B with `join()`. What happens?

B terminates due to the uncaught exception, and the default error-reporting mechanism may print the stack trace to stderr. `join()` in A returns after B terminates, unless A is interrupted. B's exception **is not automatically rethrown from `join()`**; A needs another channel if it wants to know the failure reason.

**Scenario 2:** A task submitted with `ExecutorService.submit()` throws `IllegalStateException`. Can `Future.get()` be used to detect the error?

Yes. `get()` can throw `ExecutionException`; `getCause()` reveals the task's exception. Storing the error in the `Future` does not in itself mean the worker thread died.

**Scenario 3:** A worker has `try { ... } finally { ... }` without a `catch`; an unchecked exception occurs inside `try`. Does the worker continue after `finally`?

If there is no matching handler at another layer of the thread, the exception still propagates upward and the thread terminates. `finally` usually runs during stack unwinding, but it **does not swallow the exception on its own**.

**Scenario 4:** A non-daemon worker is running a loop. The main thread throws an uncaught exception. Is the JVM guaranteed to stop immediately?

No. If the worker is still alive, a non-daemon worker can keep the JVM running. The application needs its own termination/orchestration policy.

**Scenario 5:** An `UncaughtExceptionHandler` is attached to a worker, and the handler logs the error. Can you use that same `Thread` object and call `start()` to retry?

No. A terminated thread cannot be restarted; create a new thread or resubmit the task through an executor.

**Key takeaway:** an exception is truly **uncaught for a thread** only when it escapes past all active handlers to the thread's termination boundary. At that point the thread terminates, the handler can report the error, and other threads may remain alive. In code using an executor, observe **task** errors through results such as `Future`; and where recovery is needed, place it at a boundary capable of real handling rather than using an uncaught handler as a substitute for `try-catch`.