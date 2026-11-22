# Per-Thread Handler, ThreadGroup, and Default Handler When a Java Thread Encounters an Uncaught Exception

## 1. Learning Objectives

After this lesson, you will be able to:

- Identify situations where an exception escapes a thread's `run()` method without being caught.
- Explain the roles of `Thread.UncaughtExceptionHandler`, a per-`Thread` handler, `ThreadGroup`, and the process-wide default handler.
- Determine the exact handling order: the handler assigned specifically to the thread, the thread group's handler and parent group chain, and then the default handler or fallback error printing.
- Write a handler that observes errors without disrupting or hiding other handling paths; know how to attach a handler **before starting the thread**.
- Distinguish exceptions that escape a thread from exceptions stored inside a `Future` from `ExecutorService.submit()`.
- Test exception-handling behavior deterministically without depending on random scheduling order or stack trace contents.

## 2. When Is an Uncaught Exception Handler Invoked?

Each Java thread has an execution path. When a `Throwable` propagates out of the thread's top-level execution block without being caught by application code, the JVM uses the **uncaught exception** handling mechanism for that thread.

Illustrative example in a program with a separate thread:

~~~java
Thread worker = new Thread(() -> {
    throw new IllegalStateException("Tác vụ không thể tiếp tục");
}, "worker");
worker.start();
~~~

The `run()` block throws an error with no enclosing `catch`. This is an **uncaught exception on the worker thread**. It does not automatically jump to a `catch` block surrounding the `worker.start()` call on the parent thread.

Distinguish three operations:

1. **Creating the thread:** `new Thread(...)` creates the object; it does not run the work yet.
2. **Starting:** `start()` asks the JVM to begin a new execution path. `start()` normally does not wait for all of `run()` to finish.
3. **Executing the work:** if an exception escapes `run()`, uncaught exception handling takes place on the termination path of that thread itself.

`Thread.join()` only waits for the thread to finish; **it does not turn a child thread's exception into an exception thrown on the thread calling `join()`**. If you want to collect success/failure results for another thread to handle, you need an additional result-passing mechanism, such as `Future`, synchronized state variables, or an appropriate monitoring system.

### What Does a Handler Do and Not Do?

`Thread.UncaughtExceptionHandler` is an interface with a single method:

~~~java
@FunctionalInterface
public interface UncaughtExceptionHandler {
    void uncaughtException(Thread t, Throwable e);
}
~~~

This is a **simplified API signature for learning**, not a class you need to declare yourself. The JVM invokes the corresponding method when an uncaught exception occurs, passing in **the failing thread** and **the error object**.

Handlers are typically used to write logs, record incident details, send signals to a management component, or standardize critical error reporting. It **does not restore the stack and does not resume the thread's work at the line after the throw statement**.

An exception can be handled right where it occurs if the code has an appropriate recovery strategy. An uncaught handler is only the final observation point for an error that has escaped the thread's handling logic.

## 3. Three Levels of Handling: Per-Thread, ThreadGroup, Default

There are three mechanisms to distinguish:

| Mechanism | Registration/Configuration | Primary Scope |
| --- | --- | --- |
| Per-thread handler | `thread.setUncaughtExceptionHandler(handler)` | Only the thread assigned the handler |
| Handler via `ThreadGroup` | `ThreadGroup.uncaughtException(thread, error)` | Threads in the group without a per-thread handler; can forward to the parent group |
| Default handler | `Thread.setDefaultUncaughtExceptionHandler(handler)` | JVM-wide fallback via the thread group mechanism when no handler is selected at a closer level |

JDK thread groups also implement `Thread.UncaughtExceptionHandler`. According to the `Thread.getUncaughtExceptionHandler()` contract, if a thread has a per-thread handler assigned, it returns that handler; otherwise, the thread's `ThreadGroup` is the handler used.

This explains why **the default handler is not simply the direct return value of `getUncaughtExceptionHandler()`** when no per-thread handler is set: normally that method returns the `ThreadGroup` object, and it is `ThreadGroup`'s default logic that looks up the default handler.

### Precedence Diagram

~~~text
Exception escapes run() of Thread T
                    |
                    v
Does T have a per-thread handler?
      | Yes                   | No
      v                       v
Call per-thread handler  Call T.getThreadGroup()
      |                       |
      |                       v
      |               ThreadGroup.uncaughtException(T, e)
      |                       |
      |              +--------+---------------------+
      |              | group overrides and handles  |
      |              |                              |
      |              | default group logic          |
      |              | -> has parent group: forward |
      |              | -> reaches root group:       |
      |              |    check default handler     |
      |              |    if none: print error      |
      v              v                            v
   End reporting handling; failing thread does not resume
~~~

The diagram describes the **typical handling path** based on standard `ThreadGroup`. A subclass of `ThreadGroup` can override `uncaughtException()` and decide for itself whether to call `super.uncaughtException(...)`. Therefore, the default handler **is not guaranteed to be called** if a custom group handles the error and does not forward it.

## 4. Per-Thread Handler

Registering a handler for a specific thread:

~~~java
Thread worker = new Thread(() -> {
    throw new IllegalStateException("Lỗi xử lý");
}, "import-worker");

worker.setUncaughtExceptionHandler((thread, error) -> {
    System.err.println("Luồng lỗi: " + thread.getName());
    System.err.println("Kiểu lỗi: " + error.getClass().getName());
});

worker.start();
~~~

This is a **standalone illustrative snippet inside a method**, which can be placed in `main` of a Java class. A per-thread handler takes two parameters:

- `thread`: the thread where the uncaught error occurred.
- `error`: the exact `Throwable` object that escaped, which may contain a cause chain, stack trace, and suppressed exceptions.

When a per-thread handler is assigned, it takes precedence over `ThreadGroup.uncaughtException()` logic for that same thread. If you only need to handle errors for an independent task, this is the easiest option to control.

**Register before `start()`.** If you wait until after starting, the task may throw an error before the handler is assigned. This is a race condition. In systems using `ThreadFactory`, you should assign the handler when creating the thread object, before returning the thread to the executor.

### What Does setUncaughtExceptionHandler(null) Mean?

Calling `thread.setUncaughtExceptionHandler(null)` clears the handler specifically assigned to the thread. When an uncaught error occurs later, the thread falls back to its fallback handler, typically `ThreadGroup`. This call **does not** set a "no-op handler" that swallows errors.

You should not pass `null` just to disable error recording. If you need to change reporting behavior, choose an appropriate handler and consider the impact on application monitoring.

## 5. ThreadGroup Both Groups Threads and Participates in Exception Handling

`ThreadGroup` allows placing threads into a group. In addition to historical group-management features, it implements `Thread.UncaughtExceptionHandler` and acts as the fallback handler for threads without a per-thread handler.

A group can have a parent group. The standard `ThreadGroup.uncaughtException()` implementation works roughly as follows:

1. If there is a parent group, call `parent.uncaughtException(thread, error)`.
2. If the root group is reached, retrieve `Thread.getDefaultUncaughtExceptionHandler()`.
3. If the default handler is not `null`, call that handler.
4. If there is no default handler, print the exception details and stack trace to `System.err`, except for the JDK's special handling of `ThreadDeath`.

Thus, when using a standard `ThreadGroup` without overrides, an exception can traverse multiple parent groups before reaching the default handler. This mechanism does not create a new exception; it passes the received error object up to the next handling method.

### Overriding uncaughtException in a Group

~~~java
class LoggingGroup extends ThreadGroup {
    LoggingGroup(String name) {
        super(name);
    }

    @Override
    public void uncaughtException(Thread thread, Throwable error) {
        System.err.println("Nhóm bắt gặp lỗi ở " + thread.getName());
        error.printStackTrace(System.err);
    }
}
~~~

This is an **illustrative class definition**, placed in an appropriate file/scope. Because the overridden method does not call `super.uncaughtException(...)`, threads belonging to this group without a per-thread handler are reported here; the error **does not automatically continue** to the parent group or default handler.

If you want to add group logging while still forwarding up to the default level, you can call `super.uncaughtException(thread, error)`. In that case, an incident may be logged twice, because both the group and the handler above it report it. Clearly define who is responsible for final logging to avoid duplication.

**Design note:** `ThreadGroup` has many thread-management APIs that are no longer preferred in modern code. If you only need to attach handlers consistently to threads you create, `ThreadFactory` or direct handler assignment is usually easier to maintain. However, you still need to understand the group mechanism because it sits on the fallback path of uncaught exception handling.

## 6. JVM Default Handler

Registering a global handler:

~~~java
Thread.UncaughtExceptionHandler previous =
        Thread.getDefaultUncaughtExceptionHandler();

Thread.setDefaultUncaughtExceptionHandler((thread, error) -> {
    System.err.println("Unhandled error in " + thread.getName());
    error.printStackTrace(System.err);
});
~~~

This is an **illustrative snippet**, placed in an application with an appropriate handler lifecycle management strategy. `setDefaultUncaughtExceptionHandler` is a `static` method on `Thread`.

The default handler is useful when you want a common fallback reporting point. It does not override per-thread handlers already assigned to individual threads and does not force a custom `ThreadGroup` to forward errors to the default.

Some principles when registering:

- Configure early at application startup to avoid missing errors from threads started earlier.
- Register intentionally, because every part of the same JVM can be affected by the default handler.
- When writing examples or tests, you can save the previous value via `getDefaultUncaughtExceptionHandler()` and restore it after threads have finished.
- When multiple libraries modify the default handler, a later setting can overwrite an earlier one. Do not use this mechanism as a state-exchange channel between independent components.
- The default handler does not replace error-monitoring mechanisms of frameworks, `Future`, or web applications where exceptions are typically caught and converted into results in their own way.

If there is no default handler and the standard `ThreadGroup` path reaches the final fallback, the JDK typically prints a line like `Exception in thread "..."` and the stack trace to `System.err`. The exact string may depend on the runtime; do not treat this as a log API with a stable format. `ThreadDeath` has special handling in standard `ThreadGroup`; do not use `Thread.stop()` to create test scenarios because that API is unsafe and has been removed from modern practice.

## 7. Standalone Java 17+ Example: Testing Three Priority Levels

The standalone runnable below creates three threads sequentially so that stdout has a deterministic order:

1. A thread that both belongs to a custom group and has a per-thread handler: **the per-thread handler is called**.
2. A thread that belongs to a custom group without a per-thread handler: **the group's handler is called**.
3. A thread that belongs to a standard group without a per-thread handler: the error is forwarded to **the default handler**.

Save the entire program to the file **HandlerDispatchDemo.java**:

~~~java
public class HandlerDispatchDemo {
    static final class ObservingGroup extends ThreadGroup {
        ObservingGroup(String name) {
            super(name);
        }

        @Override
        public void uncaughtException(Thread thread, Throwable error) {
            System.out.println("GROUP: " + thread.getName()
                    + " -> " + error.getMessage());
        }
    }

    static Thread failingThread(ThreadGroup group, String name, String message) {
        return new Thread(group, () -> {
            throw new IllegalStateException(message);
        }, name);
    }

    public static void main(String[] args) throws InterruptedException {
        Thread.UncaughtExceptionHandler previous =
                Thread.getDefaultUncaughtExceptionHandler();

        try {
            Thread.setDefaultUncaughtExceptionHandler((thread, error) ->
                    System.out.println("DEFAULT: " + thread.getName()
                            + " -> " + error.getMessage()));

            ThreadGroup specialGroup = new ObservingGroup("special");
            Thread local = failingThread(
                    specialGroup, "worker-local", "local-failure");
            local.setUncaughtExceptionHandler((thread, error) ->
                    System.out.println("THREAD: " + thread.getName()
                            + " -> " + error.getMessage()));
            local.start();
            local.join();

            Thread grouped = failingThread(
                    specialGroup, "worker-group", "group-failure");
            grouped.start();
            grouped.join();

            ThreadGroup regularGroup = new ThreadGroup("regular");
            Thread globally = failingThread(
                    regularGroup, "worker-default", "default-failure");
            globally.start();
            globally.join();
        } finally {
            Thread.setDefaultUncaughtExceptionHandler(previous);
        }
    }
}
~~~

Compile and run with Java 17 or newer:

~~~bash
javac -encoding UTF-8 HandlerDispatchDemo.java
java HandlerDispatchDemo
~~~

**Exact stdout:**

~~~text
THREAD: worker-local -> local-failure
GROUP: worker-group -> group-failure
DEFAULT: worker-default -> default-failure
~~~

The program is designed so it does not rely on stack traces containing package names or non-deterministic line numbers. Each handler prints the same simple pattern; each thread is `join()`ed before creating the next thread.

### Why Does Each Line Appear?

**Line 1 — THREAD:** `local` belongs to `ObservingGroup` but already has a per-thread handler. When the error escapes `run()`, Java invokes the per-thread handler, so neither `ObservingGroup.uncaughtException()` nor the default handler is called for this error.

**Line 2 — GROUP:** `grouped` has no per-thread handler. Its handler is the `ObservingGroup` group. The overridden method prints the `GROUP` line and returns without calling `super`, so the forwarding chain ends right at the group.

**Line 3 — DEFAULT:** `globally` belongs to a standard `ThreadGroup`. This group uses the default `uncaughtException` logic, forwards to parent groups, and ultimately calls the JVM-wide default handler. Thus the `DEFAULT` line appears and there is no fallback stack trace output.

**Why is `try/finally` needed in main?** The `finally` block restores the previous default handler so the example does not accidentally alter the behavior of code running afterward. Because each thread is `join()`ed, all three errors have a chance to finish handling before restoration.

**Why doesn't the example catch exceptions in main?** The errors are thrown from other threads. `main` only creates, starts, and waits for the threads to finish. `join()` does not rethrow the worker thread's `IllegalStateException`.

## 8. Self-Check of Precedence Order

From the example above, you can try changing one detail at a time:

| Change | Expected Behavior |
| --- | --- |
| Remove the `local.setUncaughtExceptionHandler(...)` call | The error from `worker-local` goes to `ObservingGroup` |
| Keep the per-thread handler and change the group | The per-thread handler remains the priority level for that thread |
| In `ObservingGroup.uncaughtException`, call `super.uncaughtException(thread, error)` after printing | The system may also print the default line because the error is forwarded upward |
| Call `Thread.setDefaultUncaughtExceptionHandler(null)` and use a standard group | With no custom handling layer, the standard group's final path prints the error to `System.err` |
| Use `thread.setUncaughtExceptionHandler(null)` before start | The thread no longer has a per-thread handler; the group is the fallback level |

Note: Changing the default handler in a JVM running multiple workloads can affect unrelated threads. Try these changes in a separate program or test environment; do not update the global configuration of a system serving users.

## 9. Handlers Do Not Replace catch, finally, or Error Recovery

Consider a task with resources:

~~~java
Thread worker = new Thread(() -> {
    openResource();
    try {
        doWork();
    } finally {
        closeResource();
    }
});
~~~

This is **non-standalone illustrative code**, assuming the required methods exist and their checked exception signatures allow such calls. If `doWork()` throws an uncaught unchecked exception, `finally` still runs on the normal exit path, and then the remaining exception goes to the uncaught handler.

However, a handler:

- Does not automatically close files/sockets/locks that were forgotten to be released.
- Does not automatically roll back partially updated data state.
- Cannot resume thread execution at the failure point.
- Does not replace `catch` blocks for expected errors that the application can recover from.

For `AutoCloseable` resources, prefer `try-with-resources`. If both the main operation and closing the resource throw errors, Java can keep the close error in `getSuppressed()` of the primary exception; the handler can record the entire `Throwable` object for diagnosis. If `finally` itself throws another exception, the new error can replace the previously propagating error. This is why resource cleanup must be designed properly right inside the task.

### Why Not Catch All Errors Just to Treat Them as Success?

~~~java
Thread worker = new Thread(() -> {
    try {
        performWork();
    } catch (Exception ignored) {
        // Do not report, do not fix state, continue as if succeeded.
    }
});
~~~

This is an **intentionally bad example to avoid**, with `performWork()` as an illustrative method. The error has been caught, so the uncaught handler will never know about it. If the task contract genuinely allows recovery, the code here must handle it and publish an accurate result; otherwise, let the error propagate or convert it into a structured failure result.

## 10. ExecutorService.submit() Has an Important Difference

A common misconception: "Once an `UncaughtExceptionHandler` is assigned to an executor's threads, every exception in a task goes to the handler."

This is **not true for the normal execution path of `ExecutorService.submit()`**. `submit()` returns a `Future`. The task is wrapped by a result-recording mechanism; when the task throws an exception, `Future` stores the failure state. A subsequent `Future.get()` call reports `ExecutionException` with the cause containing the task's underlying cause. The exception has been caught/recorded by the task mechanism, so it does not escape `Thread.run()` as an uncaught exception.

### Standalone Java 17+ Example with Future

Create the file **FutureFailureDemo.java**:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class FutureFailureDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger handlerCalls = new AtomicInteger();

        ThreadFactory factory = task -> {
            Thread thread = new Thread(task, "pool-worker");
            thread.setUncaughtExceptionHandler(
                    (t, error) -> handlerCalls.incrementAndGet());
            return thread;
        };

        ExecutorService executor = Executors.newSingleThreadExecutor(factory);
        try {
            Future<?> future = executor.submit(() -> {
                throw new IllegalArgumentException("bad task");
            });

            try {
                future.get();
            } catch (ExecutionException e) {
                System.out.println("FUTURE: "
                        + e.getCause().getClass().getSimpleName()
                        + " -> " + e.getCause().getMessage());
            }
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                throw new AssertionError("Executor không kết thúc");
            }
        }

        System.out.println("HANDLER CALLS: " + handlerCalls.get());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 FutureFailureDemo.java
java FutureFailureDemo
~~~

**Exact stdout:**

~~~text
FUTURE: IllegalArgumentException -> bad task
HANDLER CALLS: 0
~~~

Explanation:

1. `ThreadFactory` creates threads for the executor and assigns a per-thread handler. The handler only increments a counter.
2. `submit()` returns a `Future` for a task that throws `IllegalArgumentException`.
3. `future.get()` observes the failure via `ExecutionException`; `getCause()` is the task's original exception.
4. Because the task failure was stored in the `Future`, the thread's handler **is not called for that error**; the counter is 0.
5. `shutdown()` and `awaitTermination()` ensure executor resources are managed cleanly. The program handles this task's `ExecutionException` to print a deterministic result.

### What About execute()?

With `ThreadPoolExecutor.execute(Runnable)`, a `RuntimeException` or `Error` escaping `Runnable.run()` can cause the worker thread to terminate abnormally; that thread's uncaught exception handling path may be triggered. However, how a specific executor handles tasks also depends on the implementation, wrappers, and the type of task submitted.

Therefore, **do not design a system that relies solely on handlers to collect all task errors**. With `Future`, observe results using `get()`; with other async mechanisms like `CompletableFuture`, use the appropriate completion and exceptional-completion handling APIs. If consistent recording at the executor is needed, apply a task-level handling policy or use a monitoring hook provided by the framework.

## 11. ThreadFactory: Attaching Handlers to New Threads

When managing your own worker pool or using `ExecutorService`, `ThreadFactory` helps apply thread names and handlers consistently:

~~~java
java.util.concurrent.ThreadFactory factory = runnable -> {
    Thread thread = new Thread(runnable, "document-worker");
    thread.setUncaughtExceptionHandler((t, error) -> {
        System.err.println("Worker thất bại: " + t.getName());
        error.printStackTrace(System.err);
    });
    return thread;
};
~~~

This is an **illustrative snippet**, not a standalone program. The key point is that the factory configures the thread **before the executor or another component starts it**.

If creating multiple threads, use a naming policy that distinguishes them rather than duplicate names so logs are easier to read. The handler should be lightweight, reliable, and avoid long blocking operations. A single thread failing does not mean the entire executor or JVM has stopped; worker replacement, task state, and shutdown policies depend on the executor.

## 12. Which Exceptions Can Reach a Handler?

The `uncaughtException(Thread, Throwable)` method receives a `Throwable`, not just an `Exception`. Therefore, the handler can see `RuntimeException`, other unchecked exceptions, and `Error` that have escaped the thread.

You should not assume that a handler can **recover from every `Error`**. Severe errors such as JVM resource errors can make even logging unreliable. A handler is the best possible observation point, not a self-healing engine for every failure.

Checked exceptions such as `IOException` must normally be caught or declared at the call site according to Java rules. `Runnable.run()` does not declare checked exceptions, so code directly inside a `Runnable` lambda must handle or wrap them before they can escape as uncaught exceptions.

Illustrative example:

~~~java
Runnable task = () -> {
    try {
        readFromFile();
    } catch (java.io.IOException original) {
        throw new IllegalStateException("Không thể đọc dữ liệu", original);
    }
};
~~~

This snippet assumes a `readFromFile()` method declared with `throws IOException`. If `IllegalStateException` escapes the task executing directly on the thread, the handler receives that wrapper. The wrapper's `getCause()` still preserves the original `IOException` for diagnosis.

An exception that application code **has already caught and handled** is not considered uncaught; the handler will not know about it unless the code explicitly reports it.

## 13. What Should a Handler Do?

A good handler typically limits its job to **recording the incident accurately enough** and providing a signal to the management layer. It can:

- Record the thread name/ID, timestamp, and task name if available.
- Log the exception object to preserve the full type, cause, stack trace, and suppressed exceptions.
- Increment a metric or emit an internal event with appropriate resource bounds.
- Notify a worker manager that a thread has terminated abnormally.
- Provide a unified error-reporting mechanism, such as sending to the application's logger.

Important limitations:

1. **Do not treat the handler as a place to retry the task**: there is not enough reliable information about idempotency, side effects already performed, or post-error state.
2. **Do not perform complex, failure-prone processing**: the handler may be called when the system is in a degraded state.
3. **Do not lose original information**: when converting an error into an event, try to preserve the cause for internal investigation.
4. **Do not expose sensitive information**: stack traces can contain paths, resource names, technical messages, or application data; store/display them according to appropriate access levels.
5. **Avoid duplicate logging**: if both a group handler and the default handler print the same exception, operations can easily count one incident as two.
6. **Do not rely on the console for business processing**: `System.err` is not a stable communication contract for distributed systems.

### What If the Handler Itself Throws an Exception?

By the contract of `Thread.UncaughtExceptionHandler`, any exception thrown by `uncaughtException` itself is ignored by the JVM. You cannot expect a failing handler to trigger a second error-reporting round or return to executing the original work.

Therefore, keep handlers short, avoid error-prone shared state, and test the handler itself with unusual inputs. Depending on requirements, you can wrap reporting code with appropriate safeguards, but do not create recursive handler calls when the logging system itself is failing.

## 14. Differences Between Handling Errors in a Task and in a Handler

| Question | Catching errors in the task | Uncaught handler |
| --- | --- | --- |
| Can it recover and continue work? | Yes, if task logic knows how to recover | Cannot return to the point where it exited |
| Can it convert the error into a business result? | Yes, per the task contract | Usually only observes/reports; needs another result channel |
| Can it release local resources? | Yes, via `finally` or try-with-resources | Too late to rely on the handler for cleanup instead of the task |
| Does it have sufficient business context? | Usually yes | Only passed `Thread` and `Throwable`; other info must be designed separately |
| Does it receive errors from `submit()`? | Future/task wrapper stores the exception; caller handles via `get()` | Usually does not see task errors because the wrapper catches them |

No single level fits every error. Expected and recoverable errors should be handled inside the task or in the corresponding async contract. An uncaught handler is a fallback point that helps observe errors **that have escaped** the normal handling path.

## 15. Testing Handlers and Handling Order

Test suites should verify behavior **by mechanism**, without depending on execution timing or JVM stack traces.

| Scenario | Expectation |
| --- | --- |
| Thread has a per-thread handler and is in a custom group | Only the per-thread handler receives the exception, if the handler itself does not forward |
| Thread has no per-thread handler, group overrides `uncaughtException` | The group's handler is called |
| Thread uses a standard group, default handler is set | At the end of the parent group chain, the default handler is called |
| Group overrides without calling `super` | Default handler does not automatically receive the error |
| Group overrides and calls `super` | The handling path can reach the parent/default |
| Task already caught and handled the exception | Does not trigger the uncaught handler for that exception |
| Task runs via `ExecutorService.submit()` | Error is retrieved via `Future.get()`; the thread's handler does not automatically receive it |

In tests, you can use `AtomicReference<Throwable>` or a synchronization utility to record the exception delivered to the handler. Start the thread, call `join()`, and then assert the exception type and **the same object identity** if needed.

**Do not write tests that risk hanging indefinitely** when a task might wait on a lock or I/O. Set appropriate test timeouts and handle timeout states. Do not assert that a handler was "never called" just from reading a counter too early before the thread has finished.

For the default handler, save and restore the previous handler according to the test lifecycle. If multiple tests run in parallel in the same JVM and modify the default handler concurrently, they can interfere with each other; isolate or coordinate this global state.

## 16. Common Pitfalls

1. **Catching exceptions around `thread.start()` expecting to catch errors in `run()`:** the two calls run on different threads.
2. **Attaching the handler after `start()`:** the thread may have already thrown the error before the handler was installed.
3. **Assuming the default handler is always called:** a per-thread handler or an overridden `ThreadGroup` may terminate the error-reporting path earlier.
4. **Assuming a group is just a classification label:** `ThreadGroup` is also a fallback `UncaughtExceptionHandler`.
5. **Overriding a group and forgetting to decide whether to call `super`:** either default logging is lost, or duplicate logging occurs accidentally.
6. **Thinking a handler lets the task continue running:** the thread has already exited the failing execution path.
7. **Expecting `join()` to rethrow a worker's exception:** `join()` only waits for termination and can itself be interrupted on the waiting thread.
8. **Using a handler to find all errors from `submit()`:** the task's exception may be inside the `Future`.
9. **Logging only `error.getMessage()`:** loses the type, cause chain, and stack trace.
10. **Logging full error details to public output:** risks exposing infrastructure details.
11. **Doing heavy work inside the handler:** easily causes new errors when the system is already unstable.
12. **Forgetting to restore the default handler after tests:** alters the behavior of subsequent tests or components.
13. **Treating all errors as recoverable:** `Error` and severe system errors may not allow recovery.
14. **Logging the same error at multiple levels:** creates noise in incident counting and analysis.

## 17. Design Checklist

Before operating a multithreaded program, check:

- Have you distinguished **expected errors in a task** from **uncaught exceptions escaping a thread**?
- Have threads needing custom handling been assigned a handler **before `start()`**?
- Does any custom `ThreadGroup` have clear error-forwarding rules, and does it avoid duplicate logging?
- Has the default handler been configured at an appropriate startup point?
- If the code uses `ExecutorService.submit()`, who is responsible for `Future.get()` or handling failure results?
- When an error occurs, is local cleanup guaranteed by `finally` or `try-with-resources`?
- Does the handler have enough observation context without exposing sensitive information?
- Do tests verify precedence order, throwable identity, and the actual reporting path?
- Are recovery, retry, or application termination policies decided at a layer with sufficient context?

**Key takeaway:** a per-thread handler takes priority for each `Thread`; if none is set, `ThreadGroup` receives the error and can forward it to the parent group; standard logic at the root group then uses the default handler before falling back to fallback error printing. Uncaught handlers help **observe errors at the end of a thread's execution path**, while result handling, cleanup, and recovery must be designed at the right layer with sufficient context.