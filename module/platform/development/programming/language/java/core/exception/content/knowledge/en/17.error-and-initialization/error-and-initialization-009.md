# Why Catching `Throwable` or `Error` Requires a Clear Boundary and Purpose in Java

In Java, **catching an exception does not mean you can safely recover from it**. This distinction is especially important when writing `catch (Throwable)` or `catch (Error)`: both options widen the catch scope to serious conditions such as memory errors, class linkage errors, and invariant failures, which normally **should not be handled like an ordinary business error**.

A high-risk example:

~~~java
// Anti-pattern: do not apply to production systems.
try {
    processRequest();
} catch (Throwable failure) {
    return defaultResponse();
}
~~~

The snippet above is **illustrative code** only; `processRequest()` and `defaultResponse()` would be needed in a real context. The problem is that it lumps together `IOException`, `NullPointerException`, `OutOfMemoryError`, `NoClassDefFoundError`, `AssertionError`, and many other types into the same "fallback result" and pretends the system is still reliable. A task may have partially executed, resources may be exhausted, or the program code may be incompatible with the runtime. Returning a normal result in that case easily hides system failures, causes duplicate transactions, or leads to data loss.

Practical principle:

> **Only catch where you can define the work boundary, the handling goal, and the conditions for the system to continue.** With `Error` or a broad `Throwable`, the goal should usually be minimal observation, cleanup, or propagating the error up to an appropriate management boundary — not swallowing the error and treating it as success.

This article clarifies when `catch (Error)` or `catch (Throwable)` can be used, when `catch (Exception)` or catching specific types should be used, how to design boundaries for workers/plugins/tests, how to preserve the original error when cleanup fails, and how to recognize situations where a component must be stopped or restarted. The demonstration programs use **Java 17+**, testing with controlled `AssertionError`s, **without attempting to trigger real out-of-memory or stack-overflow errors**.

## 1. Why Does the Type Hierarchy Determine `catch` Behavior?

Simplified structure:

~~~text
java.lang.Throwable
├── java.lang.Exception
│   ├── IOException
│   ├── SQLException
│   └── java.lang.RuntimeException
│       ├── IllegalArgumentException
│       ├── IllegalStateException
│       └── NullPointerException
└── java.lang.Error
    ├── VirtualMachineError
    │   ├── OutOfMemoryError
    │   └── StackOverflowError
    ├── LinkageError
    │   ├── NoClassDefFoundError
    │   ├── NoSuchMethodError
    │   └── ExceptionInInitializerError
    ├── AssertionError
    └── ThreadDeath
~~~

The types in the diagram have an **inheritance relationship**, not horizontal priority levels. A `catch` matches when the runtime type of the thrown object is that class or an appropriate subtype.

| `catch` branch | Which types are caught? | Key point to remember |
| --- | --- | --- |
| `catch (IOException ex)` | `IOException` and subtypes | Suitable if there is an I/O error recovery policy |
| `catch (RuntimeException ex)` | `RuntimeException` subtypes | Does not catch `Error` |
| `catch (Exception ex)` | `Exception` and subtypes, including checked and runtime exceptions | Does not catch `Error` |
| `catch (Error err)` | `Error` and subtypes | Catches errors that may be serious outside the business scope |
| `catch (Throwable t)` | Both `Exception` and `Error` | Widest scope across both main branches |
| Not caught | Error propagates up the stack to a matching handler or uncaught mechanism | Does not automatically mean the JVM dies immediately |

**`Error` is unchecked**: the compiler does not require a method that throws it to declare `throws Error`. "Unchecked" only refers to compile-time checking; it **does not** mean it is mild, harmless, or safe to ignore.

The second important point: `Error` **is not a subtype of `Exception`**, so a `catch (Exception)` written at a request boundary usually intentionally lets `Error` conditions escape the normal application error-handling mechanism.

## 2. Distinguishing Three Goals: Handling, Observing, and Containing Damage

The phrase "catching errors" often obscures three different activities.

### 2.1. Handle / Recover

You know a **sufficiently specific cause**, know the **task state after the error**, and have a **contract-compliant recovery path**. For example:

~~~java
// Illustrative snippet inside a method that has readFromPrimary/Backup.
try {
    return readFromPrimary();
} catch (java.io.IOException ex) {
    return readFromBackup();
}
~~~

A recovery path makes sense when backup data is valid and using the backup is permitted. This is not a standalone compilable example, because both read methods must be defined. If `readFromBackup()` also throws a checked `IOException`, the enclosing method must handle or declare it.

### 2.2. Observe / Record

You **are not sure you can fix the error**, but want to record the cause, task name, or diagnostic information. A task-management boundary can record `Throwable` and then **rethrow** it, letting the management system decide whether to continue.

~~~java
// Illustrates an intentional observation boundary.
try {
    runTask();
} catch (Error err) {
    minimalFailureSignal(err);
    throw err;
}
~~~

The snippet above is not standalone; both helper functions depend on the application. The "minimal recording then rethrow" policy is **different** from `return success`.

### 2.3. Contain / Isolate Damage

A plugin runner, test runner, or supervisor may need to keep the **outer management unit** running when an **isolated child unit** fails. However, this is only justified if there is control over **state, resource ownership, side effects, and error types**. A `catch(Throwable)` placed in the same heap/JVM **does not create a safe boundary against `OutOfMemoryError`**.

For example, a test runner can catch `AssertionError` to mark one test as failed and continue to the next test; yet that same test runner cannot by default recover safely from an internal JVM error.

**Rule:** every `catch` branch must clearly answer "what am I doing with this error?" and "why is it still permissible to keep running?". If you cannot answer those, you should not use an overly broad `catch`.

## 3. An `Error` Is Not Like an Expected Business Error

Business errors usually have **deterministic rules** and **valid responses**:

- Negative quantity input → reject with `IllegalArgumentException` or a validation code.
- Configuration file not found → `IOException` or an exception at the configuration abstraction.
- User lacks permission → appropriate access-control error.
- Task timed out → controlled timeout/retry policy.

Meanwhile:

- `OutOfMemoryError`: allocation cannot be satisfied. Even logging or building a response may continue to fail.
- `StackOverflowError`: the thread's stack may be exhausted; complex call paths inside a handler may be unsafe.
- `LinkageError`: bytecode/dependency/runtime may be incompatible. Retrying the same deployment usually cannot fix it.
- `AssertionError`: may indicate a programming invariant has been broken; the task's data and side effects must be inspected.

All of the above are **`Error`**s, yet their origins differ. Do not apply an absolute judgment like "every `Error` terminates the JVM", and do not use a single generic recovery branch for all of them.

## 4. Mandatory Questions Before Writing `catch (Error)` or `catch (Throwable)`

Before placing a broad catch, determine:

1. **Where is the boundary?** A business method, a request, a worker, a test case, or the entire process?
2. **Who owns the state?** Are there unfinished transactions, intermediate data, locks, streams, or global variables?
3. **Why is a broad catch needed?** For observation, cleanup, transferring orchestration control, or is there genuinely a recovery path?
4. **Should it be rethrown immediately?** If not, what evidence permits continuing?
5. **How is the original error preserved?** Are the stack trace, cause, and suppressed exceptions replaced or lost?
6. **What if the handler or logging itself fails?** Especially under low memory and stack exhaustion.
7. **Is `Error` distinguished from `Exception`?** Do not equate system failures with invalid input.
8. **Who decides to restart/isolate?** The application, supervisor, container orchestrator, or test framework?
9. **Can it be tested with a safe scenario?** Use a simulated `AssertionError` instead of trying to exhaust the heap.
10. **Could the caller receive a false success result?** This is usually a sign of a flawed design.

A broad catch that cannot satisfy these questions should be replaced by catching **specific exception types** or moved to an appropriate management boundary.

## 5. `catch (Exception)` Is Usually a Better Choice in Business Code

A request handler can handle errors as follows:

~~~java
// Illustrative snippet, depends on processRequest and response classes.
try {
    return processRequest();
} catch (IllegalArgumentException ex) {
    return invalidRequest(ex.getMessage());
} catch (java.io.IOException ex) {
    return temporaryFailure();
} catch (Exception ex) {
    reportUnexpectedException(ex);
    return internalFailure();
}
~~~

This structure still requires a clear policy for each type, but **`Error` is not caught by `catch (Exception)`**. It avoids turning JVM/linkage errors into an "ordinary 500 error" response and continuing to serve traffic as if nothing happened.

`catch (Exception)` is not always appropriate either: it is still very broad compared to `IOException` or `IllegalArgumentException` and can swallow programming bugs that belong to `RuntimeException`. In low-level libraries, prefer catching **the specific types you can handle**.

Conversely, a controller or execution boundary may need to catch `Exception` to log or produce a final response, provided it does not promise to recover unverified state.

## 6. Catching `Error` to Observe and Rethrow

Separate normal input handling from serious invariant errors.

Complete Java 17 program `BoundaryRethrowDemo.java`:

~~~java
public class BoundaryRethrowDemo {
    static void runTask(String mode) {
        if ("invalid".equals(mode)) {
            throw new IllegalArgumentException("tham số sai");
        }
        if ("bug".equals(mode)) {
            throw new AssertionError("bất biến hỏng");
        }
        System.out.println("Tác vụ hoàn thành");
    }

    static void boundary(String mode) {
        try {
            runTask(mode);
        } catch (IllegalArgumentException ex) {
            System.out.println("Xử lý đầu vào: " + ex.getMessage());
        } catch (Error err) {
            System.out.println("Quan sát lỗi nghiêm trọng: "
                    + err.getClass().getSimpleName());
            throw err;
        }
    }

    public static void main(String[] args) {
        boundary("ok");
        boundary("invalid");
        try {
            boundary("bug");
        } catch (AssertionError err) {
            System.out.println("Tầng gọi nhận lại: " + err.getMessage());
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 BoundaryRethrowDemo.java
java BoundaryRethrowDemo
~~~

Exact stdout:

~~~text
Tác vụ hoàn thành
Xử lý đầu vào: tham số sai
Quan sát lỗi nghiêm trọng: AssertionError
Tầng gọi nhận lại: bất biến hỏng
~~~

How to interpret this:

- `mode="ok"`: the task finishes successfully.
- `mode="invalid"`: an `IllegalArgumentException` is caught at the boundary and handled as an invalid-input case.
- `mode="bug"`: produces an `AssertionError`; `catch (Error)` only records it and uses `throw err;`, **without changing the object type** and without treating the task as successful.
- `main` has a very specific `catch (AssertionError)` handler to **demonstrate** that the error was propagated to the caller. In production, what the outer layer does depends on the task/process termination policy.

**Warning:** the logging branch uses `System.out.println` for visibility in the example; do not assume you can always print logs when an actual `OutOfMemoryError` occurs. A production-grade boundary needs a minimalist monitoring strategy and must not rely on unbounded memory allocation.

## 7. `throw err;` vs. `throw new RuntimeException(err);`

Consider these two options inside the same `catch(Error err)`:

~~~java
// Propagate the original Error object outward.
throw err;
~~~

~~~java
// Create a new RuntimeException wrapper; usually should not be done for serious Errors.
throw new RuntimeException("lỗi tác vụ", err);
~~~

Differences:

| Criterion | `throw err` | `throw new RuntimeException(..., err)` |
| --- | --- | --- |
| Outermost object type | Preserves original `Error` type | New `RuntimeException` |
| Object identity | Preserves the same object | New wrapper object |
| Cause | Creates no new link | `Error` is preserved under `getCause()` if the right constructor is used |
| `catch (Exception)` in caller | Does not directly catch original `Error` | Can catch the `RuntimeException` wrapper |
| Risk | Error continues propagating with the right type | May cause caller to treat it as a business exception if it does not inspect the cause |

**Do not wrap `OutOfMemoryError` or `LinkageError` in a `RuntimeException` just so they fall into a "generic Exception" handler.** Doing so alters type classification and can mask a critical system incident. If a framework's contract wraps `Throwable`, integrators must inspect the actual cause before deciding on recovery.

Creating the wrapper itself also allocates a new object — unreliable under severe memory pressure.

## 8. When Can `catch (Throwable)` Have a Legitimate Purpose?

`catch (Throwable)` catches both the `Exception` and `Error` branches. Certain boundaries **may** need to observe every `Throwable`:

- A test runner collecting a test case's failure to report across the entire suite.
- A task-orchestration framework receiving a final failure report from a worker.
- A lifecycle management layer receiving a failure from a tightly controlled plugin sandbox.
- A final cleanup/monitoring block where an error must be recorded before handing over handling control.
- A task/future executor that must store `Throwable` per its API contract.

But the condition is strict: **receiving every `Throwable` does not mean you can recover from every `Throwable`**. There are fatal errors after which, once recorded, the process should stop and let an external supervisor handle it.

If you only need to record and propagate, the pattern is:

~~~java
// Illustrative code when runTask() can throw Exception.
try {
    runTask();
} catch (Throwable failure) {
    observeMinimal(failure);
    throw failure;
}
~~~

Here `observeMinimal` must be a defined monitoring method. This snippet is **not standalone**. When `runTask()` declares a checked exception, the enclosing method must satisfy catch-or-declare. With `throw failure` on an effectively final catch parameter, Java applies the **precise rethrow** rule, allowing the compiler to analyze which checked types can actually escape the `try` block. Do not assume `catch(Throwable)` makes all checked exceptions disappear.

## 9. Java 17: Observing Both `Exception` and `Error` and Propagating the Exact Type

File `ThrowableGuardDemo.java`:

~~~java
public class ThrowableGuardDemo {
    static void simulate(String mode) throws Exception {
        if ("checked".equals(mode)) {
            throw new Exception("lỗi kiểm tra");
        }
        if ("error".equals(mode)) {
            throw new AssertionError("lỗi bất biến");
        }
    }

    static void observeAndPropagate(String mode) throws Exception {
        try {
            simulate(mode);
        } catch (Throwable failure) {
            System.out.println("Quan sát: " + failure.getClass().getSimpleName());
            throw failure;
        }
    }

    public static void main(String[] args) {
        for (String mode : new String[]{"checked", "error"}) {
            try {
                observeAndPropagate(mode);
            } catch (Exception ex) {
                System.out.println("Bên ngoài Exception: " + ex.getMessage());
            } catch (Error err) {
                System.out.println("Bên ngoài Error: " + err.getMessage());
            }
        }
    }
}
~~~

Commands:

~~~bash
javac --release 17 -encoding UTF-8 ThrowableGuardDemo.java
java ThrowableGuardDemo
~~~

Exact stdout:

~~~text
Quan sát: Exception
Bên ngoài Exception: lỗi kiểm tra
Quan sát: AssertionError
Bên ngoài Error: lỗi bất biến
~~~

Analysis:

1. `simulate()` can produce a checked `Exception` or an unchecked `AssertionError`.
2. `catch(Throwable)` in `observeAndPropagate()` receives both cases, prints the actual type, and **rethrows the same object**.
3. The signature `observeAndPropagate() throws Exception` is sufficient for the checked path; there is no need to declare `throws Error`.
4. The caller `main()` catches each type by **runtime relationship**: `Exception` enters `catch(Exception)`; `AssertionError` enters `catch(Error)`.
5. This example simulates observing and forwarding; it does not prove that every `Error` in an application should be handled by catching broad types.

Do not overuse `throws Throwable` in public APIs just because you used `catch(Throwable)`. Widening a checked contract to `Throwable` forces callers to handle an overly broad set of types and hurts maintainability.

## 10. `catch` Ordering Rules Also Matter

If the same `try` has both specific and broad handlers, you must place **specific handlers before broad handlers**:

~~~java
try {
    runTask();
} catch (IllegalArgumentException ex) {
    // Handle invalid input.
} catch (Exception ex) {
    // Other Exceptions.
} catch (Error err) {
    // Observe Error if the boundary genuinely needs to.
}
~~~

This is an illustrative snippet; `runTask()` must exist. You can use `catch(Throwable)` last if a boundary API has a special policy, but do not add it to every method by habit.

Invalid example:

~~~java
// INTENTIONALLY WRONG: the specific branch is shadowed by the earlier broad catch.
try {
    runTask();
} catch (Throwable t) {
    // ...
} catch (Exception ex) {
    // Unreachable catch: Exception is already covered by Throwable.
}
~~~

The compiler rejects the `catch(Exception)` branch because it is unreachable. Beyond the language requirement, ordering from specific → broad also helps code reviewers see clearly which error types are actively handled and which are merely observed.

## 11. `finally` and `try-with-resources` Are Usually Better Than Broad Catches for Cleanup

The purpose of `finally` and `try-with-resources` is not to decide whether an error is recoverable; they provide a **resource cleanup** path when a scope exits normally or abruptly under Java semantics.

~~~java
// Illustrative snippet.
try {
    doWork();
} finally {
    closeLocalResources();
}
~~~

If `doWork()` throws `AssertionError`, the JVM normally attempts to run `finally` before propagating the error. However:

- `finally` may **not run** if the process is killed, `Runtime.halt()` occurs, or the JVM cannot continue.
- If code inside `finally` throws its own error, the new error **can mask the original error** unless designed to preserve it.
- An overly complex `closeLocalResources()` can corrupt secondary state, making investigation harder.
- Cleanup does not by itself prove that all side effects or transactions have rolled back.

For resources implementing `AutoCloseable`, `try-with-resources` preserves the primary exception and attaches resource-closing errors as **suppressed**. This is usually the better choice to reduce the risk of masking the root cause.

## 12. Java 17: Primary `Error` and `close()` Failure as Suppressed

File `CleanupErrorDemo.java`:

~~~java
import java.io.IOException;

public class CleanupErrorDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("Đã gọi close()");
            throw new IOException("đóng lỗi");
        }
    }

    public static void main(String[] args) throws IOException {
        try (Resource resource = new Resource()) {
            throw new AssertionError("lỗi chính");
        } catch (AssertionError err) {
            System.out.println("Chính: " + err.getMessage());
            System.out.println("Số suppressed: " + err.getSuppressed().length);
            System.out.println("Phụ: " + err.getSuppressed()[0].getMessage());
        } finally {
            System.out.println("finally kết thúc");
        }
    }
}
~~~

Commands:

~~~bash
javac --release 17 -encoding UTF-8 CleanupErrorDemo.java
java CleanupErrorDemo
~~~

Exact stdout:

~~~text
Đã gọi close()
Chính: lỗi chính
Số suppressed: 1
Phụ: đóng lỗi
finally kết thúc
~~~

Explanation:

- The `try` body throws `AssertionError`, which is the primary error.
- When leaving the scope, `close()` is called and throws `IOException`.
- `IOException` is added to **`AssertionError`'s `getSuppressed()`**, rather than automatically replacing the primary error.
- `catch(AssertionError)` in the example only reads the error structure for demonstration; in a normal application, you can let the error propagate after cleanup.
- `main throws IOException` is still required so the compiler accepts the implicit `close()` call with a checked `IOException`. Do not assume that an `Error` thrown in the body eliminates checked obligations of resource closing.
- `getSuppressed()[0]` is safe in the example because `close()` deterministically throws one exception. General-purpose code must check the array length before accessing elements.

An `Error` can have suppressed exceptions just like other `Throwable`s; however, this does not turn the resource error into the **cause** of the `Error`. `getCause()` and `getSuppressed()` describe two different relationships.

## 13. Why Should You Not Swallow Errors in `finally`?

The following snippet is risky:

~~~java
// Anti-pattern: an error in finally can mask the original error.
try {
    throw new AssertionError("nguyên nhân chính");
} finally {
    throw new IllegalStateException("cleanup thất bại");
}
~~~

When `finally` throws `IllegalStateException`, the final abrupt completion reason of the statement is the new error, and the earlier `AssertionError` **is not automatically attached as cause/suppressed**.

Instead of using `return` or `throw` arbitrarily in `finally`, prefer `try-with-resources` where appropriate. If manual cleanup is unavoidable, design it to **preserve the primary error** and handle cleanup errors properly; using `Throwable.addSuppressed()` also requires care regarding reference cycles and cases where suppression is disabled in a custom throwable.

**Do not use `return` in `finally` to "stabilize" the program.** It can override both normal return values and exception paths, causing serious errors to be swallowed.

## 14. Thread Boundaries: An Uncaught `Error` Can Terminate Only One Thread

Java lets you set a `Thread.UncaughtExceptionHandler` to receive a `Throwable` when a thread terminates abruptly without a prior handler.

Program `WorkerUncaughtDemo.java`:

~~~java
public class WorkerUncaughtDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(
                () -> { throw new AssertionError("worker lỗi"); }, "worker-196");

        worker.setUncaughtExceptionHandler((thread, failure) ->
                System.out.println("Uncaught " + thread.getName() + ": "
                        + failure.getClass().getSimpleName()));

        worker.start();
        worker.join();
        System.out.println("Main còn chạy");
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 WorkerUncaughtDemo.java
java WorkerUncaughtDemo
~~~

Exact stdout:

~~~text
Uncaught worker-196: AssertionError
Main còn chạy
~~~

**Correct interpretation:**

- `worker` throws an uncaught `AssertionError`, so it terminates abruptly.
- The uncaught handler receives the worker's error and prints a message.
- `main`'s `join()` completes after `worker` finishes; `main` continues.
- The fact that "main is still running" **does not prove that shared state is still consistent** or that the failed work can be automatically re-run.
- The handler is a place to **record the thread's failure**, not a way to resume running that same thread after the throwing statement.

For `ExecutorService` or `Future`, task errors may be recorded according to the executor/future contract and only surface when retrieving results via APIs like `Future.get()`. Do not assume every task failure goes through the same uncaught handler as a raw `Thread` example.

## 15. Isolated Test/Plugin Boundaries: When Does Continuing Make Sense?

A test runner can be **intentionally designed** so that one test fails with `AssertionError` while the suite continues. That is different from production code swallowing any `Error` in core business logic.

Java 17 program `IsolatedPluginDemo.java` uses only an **internal fixture**, without calling external plugin code:

~~~java
public class IsolatedPluginDemo {
    interface Plugin {
        void execute();
    }

    static boolean runIsolatedFixture(Plugin plugin) {
        try {
            plugin.execute();
            return true;
        } catch (AssertionError err) {
            System.out.println("Plugin thử nghiệm thất bại: "
                    + err.getClass().getSimpleName());
            return false;
        }
    }

    public static void main(String[] args) {
        boolean first = runIsolatedFixture(
                () -> { throw new AssertionError("fixture"); });
        boolean second = runIsolatedFixture(
                () -> System.out.println("Plugin thử nghiệm OK"));
        System.out.println("Kết quả: " + first + ", " + second);
    }
}
~~~

Commands:

~~~bash
javac --release 17 -encoding UTF-8 IsolatedPluginDemo.java
java IsolatedPluginDemo
~~~

Stdout:

~~~text
Plugin thử nghiệm thất bại: AssertionError
Plugin thử nghiệm OK
Kết quả: false, true
~~~

The example shows that at a boundary whose **explicit goal is to record fixture failures**, catching **specifically `AssertionError`** and continuing to the next fixture can be reasonable. However, the name `IsolatedPluginDemo` does not mean the same JVM provides a security sandbox, memory isolation, or isolation of side effects from untrusted plugins. **This is not a real sandbox**; it only isolates *control flow and local variables of the demo*.

For untrusted plugins, a `catch(Throwable)` in the same JVM **is not sufficient isolation**: a plugin can mutate static state, spawn threads, hold resources, block indefinitely, exhaust the heap, or call dangerous APIs. You need permission controls and potentially **process/container isolation** per system requirements, along with timeout/kill/restart policies. Do not advertise `catch(Error)` as a reliable fault-isolation mechanism.

## 16. Classifying Errors After `catch(Throwable)`: Avoiding a "False Success" Branch

If a framework must observe every `Throwable`, it needs to **classify by handleability** rather than returning `true` regardless of the error.

A suggested logic (not complete framework code):

~~~java
// Illustrative code at a boundary with its own policy.
try {
    invokePlugin();
} catch (java.io.IOException ex) {
    reportRecoverableFailure(ex);
} catch (Error fatal) {
    reportCriticalFailureBestEffort(fatal);
    throw fatal;
} catch (Exception ex) {
    reportUnexpectedException(ex);
    throw ex;
}
~~~

The helper functions depend on the application; the enclosing method may need to declare `throws Exception` if a checked exception escapes. The key is **separating the nature of the error**: if the code detects an `Error`, it does not hastily turn it into "the plugin failed normally, keep using it".

You do not necessarily have to catch all `Error`s to classify them: a boundary can let `Error` propagate and rely on out-of-process monitoring. An in-process `Error` recording strategy is only appropriate if its costs and risks are well understood.

Special case: `ThreadDeath` is a subclass of `Error`. Java documentation emphasizes that if an application catches `ThreadDeath`, it should normally **rethrow** it so the thread-stopping mechanism can proceed; avoid blocking/swallowing this error. Similarly, do not catch `VirtualMachineError` just to attempt "generic recovery".

## 17. Broad Catches and `InterruptedException`: Do Not Break Cancellation Signals

A very broad catch can cause problems even with **`Exception`** types. `InterruptedException` is a checked exception that typically signals a thread has been requested to stop while blocked in APIs such as `sleep()` or `wait()`.

Example in a worker:

~~~java
try {
    Thread.sleep(10_000);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
~~~

This is an illustrative snippet inside an appropriate `void` method. **Restoring the interrupt flag** with `Thread.currentThread().interrupt()` before leaving the scope is a common choice when the current layer cannot declare `InterruptedException` upward. If the contract allows, you can `throw ex;` so the caller handles it properly.

A `catch(Exception ex)` or `catch(Throwable t)` that ignores it can hide a task-cancellation signal. Although this is not an `Error`, it illustrates why a broad catch must have a **purpose and policy** rather than handling every error through a single path.

**Do not equate `InterruptedException` with `ThreadDeath`**: they are two very different types and mechanisms; `Thread.stop()` which causes `ThreadDeath` has been deprecated because it is unsafe. In new code, prefer cooperative cancellation mechanisms such as interrupts, cancellation flags, or appropriate task-cancellation APIs.

## 18. Transaction Boundaries and Side Effects: "Caught" Is Not Rolled Back

Suppose an operation performs:

~~~text
Read request
    ↓
Write partial data
    ↓
Send external notification
    ↓
Serious error thrown
    ↓
catch(Throwable) { return success; }
~~~

A successful `catch` **does not undo** the two steps already executed. If the caller sees success and sends another request, state can become even more corrupted.

When considering recovery:

1. Does the storage transaction actually roll back automatically?
2. Could side effects outside the transaction (email, payment, message queue) have already occurred?
3. Is there an **idempotency** key to avoid duplicate execution?
4. Are any resources/locks still held?
5. Can you determine whether the operation completed?
6. If unknown, should it transition to an **unknown/pending investigation** state instead of success?

A reliable boundary can **stop processing the task**, record the failure, and let reconciliation/monitoring processes decide the next step. Catching `Throwable` and returning a default value is rarely the right solution for work with side effects.

## 19. `OutOfMemoryError`: Why Can Cleanup/Logging Inside `catch` Also Fail?

Under memory exhaustion, many ordinary actions require allocation: creating strings, formatting stack traces, serializing JSON, creating a new exception wrapper, or asynchronous logging.

Therefore:

~~~java
// Anti-pattern: DO NOT treat this as an OOM recovery strategy.
try {
    runHeavyTask();
} catch (OutOfMemoryError err) {
    logger.error("Thất bại: " + err.getMessage(), err);
    return new LargeFallbackResponse();
}
~~~

This illustrative snippet depends on `runHeavyTask`, `logger`, and `LargeFallbackResponse`, and is not a runnable program. It is unsafe to treat as a general policy: **the handling inside the catch itself may continue requesting memory**.

Better practice: set up **monitoring, resource limits, heap dumps when appropriate, restart policies, and health checks** before incidents occur. For systems that need task-level fault tolerance, consider isolating workloads in processes/containers so an out-of-process supervisor can take control when an instance is no longer trustworthy.

We cannot claim every `OutOfMemoryError` is guaranteed to kill the JVM; however, **there is no guarantee it is safe to continue just because you caught it**.

## 20. `LinkageError` and Class Initialization Errors: Retrying the Same Class Solves Nothing

A `LinkageError` is usually related to dependency versions, classloader state, or bytecode. Examples:

- `NoSuchMethodError` when code calls a method that does not exist in the runtime version of a library.
- `UnsupportedClassVersionError` when the JVM does not support the class file version.
- `NoClassDefFoundError` when no suitable class definition exists or the class previously failed initialization.
- `ExceptionInInitializerError` when static initialization terminates abruptly with a non-`Error` cause.

Suppose a static initializer threw `IllegalStateException`. The JVM may report `ExceptionInInitializerError` on the first use, and then **`NoClassDefFoundError`** on subsequent uses in the same classloader because the class is in an erroneous state.

A `catch(Throwable)` that tries to access that class again **does not re-run the static initializer normally**. Recovery usually requires fixing configuration/deployment/lifecycle, not adding blind local retries.

If you encounter `NoClassDefFoundError`, do not assume "missing .class file"; check the first error, the classpath/module path, and class initialization logs. The outermost `Error` type does not always convey the full root cause.

## 21. Reading `cause` and `suppressed` at a Boundary

A `Throwable` provides several diagnostic angles:

- `getClass()`: the actual runtime type of the observed object.
- `getMessage()`: diagnostic message; should not be parsed as a stable error code.
- `getCause()`: the exception/Throwable attached as the direct cause, if any.
- `getSuppressed()`: secondary errors, commonly seen during cleanup in `try-with-resources`.
- Stack trace: the frames related to the path where the error occurred.

When errors are wrapped, the outermost exception may belong to the `Exception` branch while a deeper cause is an `Error`. Therefore, a boundary should not decide "this error is retryable" based solely on the **outermost wrapper** being an `Exception`.

Example:

~~~java
// Illustrative code inside a method.
Throwable fatal = new AssertionError("bất biến hỏng");
Exception wrapper = new Exception("tác vụ thất bại", fatal);

System.out.println(wrapper instanceof Exception);  // true
System.out.println(wrapper.getCause() instanceof Error); // true
~~~

The two lines above print `true` and `true`. This is **illustrative code without a full class/main**. The takeaway is that **a wrapper changes the outermost type but does not make the underlying error recoverable**.

If you want to traverse the entire cause chain and suppressed list of an arbitrary `Throwable`, you should guard against abnormal cyclic/circular references; do not use an unbounded `getCause()` loop on untrusted data.

## 22. `Thread.UncaughtExceptionHandler` Is Not an Automatic Error-Fixing Mechanism

An uncaught handler can receive a `Throwable` when a thread terminates abruptly. It is suitable for **recording the event** and updating supervisor state. However:

- The handler does not return to the statement that threw.
- The handler runs under the uncaught-handling mechanism; it does not turn an exception into a worker success result.
- An uncaught handler can fail itself; do not depend on heavy operations or large allocations.
- If the worker owns shared data, other threads may be affected.
- If a task is managed by an `ExecutorService`, errors may be wrapped in a `Future` instead of always going through a thread uncaught handler.

Therefore, **design boundaries according to the execution mechanism in use** (direct Thread, executor, actor, job queue, test runner), rather than copying a generic `catch(Throwable)` block everywhere.

## 23. Decision Tree When Reviewing a Broad Catch

~~~text
An operation can fail
        |
        v
Do you know the error type and have a contract-compliant handler?
        |
        +-- Yes --> Catch the specific type (IOException, domain exception...)
        |             |
        |             +--> Recover/transform/structured error, per policy
        |
        +-- No  --> Do you genuinely need to observe every Throwable at the boundary?
                      |
                      +-- No  --> Let the error propagate; use finally/TWR cleanup
                      |
                      +-- Yes --> Is the boundary clearly defined?
                                    |
                                    +-- No  --> Redesign the boundary
                                    |
                                    +-- Yes --> Minimal observation
                                                  |
                                                  +--> Serious Error?
                                                  |       |
                                                  |       +--> Usually rethrow/mark
                                                  |             component unhealthy
                                                  |
                                                  +--> Exception with a policy?
                                                          |
                                                          +--> Catch/transform per contract
~~~

This diagram is a **thinking tool**, not an algorithm that automatically classifies every exception. Some `Error`s like `AssertionError` are intentionally used in test runners; some `Exception` errors can also indicate an untrustworthy state and should not be retried. All decisions must consider **context**.

## 24. Common Anti-Patterns

| Anti-pattern | Risk | Fix |
| --- | --- | --- |
| `catch(Throwable) { }` | Swallows all errors, including serious `Error`s | Catch specifically; if observation is needed, rethrow or report failure status |
| `catch(Error) { return fallback; }` in every request | Pretends the system is healthy even when out of memory or linkage is broken | Let `Error` propagate and use a supervisor policy |
| `catch(Throwable)` converting everything to HTTP 200 | Hides errors and incomplete side effects | Return structured errors only for scenarios with a valid contract |
| `catch(OutOfMemoryError)` then allocating many objects to log | Handler may run out of memory again | Pre-configured monitoring/dumps/restarts; minimize in-process handling |
| Immediately retrying the same call after `LinkageError` | Cannot fix wrong dependency/classloader | Check build/deploy, fix versions, restart appropriately |
| Unconditionally wrapping `Error` in `RuntimeException` | Masks serious type so `catch(Exception)` treats it as business logic | Preserve type/propagate or use a transparent framework contract |
| Using `return` in `finally` | Can swallow a propagating `Throwable` | Use clean cleanup, avoid `return`/`throw` overriding original error |
| Cleanup throws a new error masking the primary error | Loses root-cause trail | `try-with-resources`, suppressed, or error-preserving strategy |
| Logging only `getMessage()` | Loses stack trace, cause, suppressed | Log the full `Throwable` at the appropriate boundary |
| Seeing a worker thread die while main still runs, and assuming the system is safe | Shared state may be corrupted | Evaluate transactions, locks, resources, and consistency |
| Using `catch(Throwable)` as a sandbox for untrusted plugins | Does not isolate heap, threads, or side effects | Manage permissions/resources and consider process isolation |
| Swallowing `InterruptedException` with other types | Loses cooperative cancellation signal | Propagate or restore the interrupt flag |
| Swallowing `ThreadDeath` | Can block legacy thread-stopping mechanism | Avoid `Thread.stop`; if caught, have a reason and usually rethrow |
| Assuming `Error` cannot be thrown manually | Misjudges `AssertionError` in tests | Read the actual type and throw source |
| Assuming catching OOM means memory has recovered | No guarantee resources are available | Monitoring, resource limits, lifecycle management |

## 25. Code Review Checklist for `catch(Error)` or `catch(Throwable)`

Before approving:

1. Does the method/class name indicate an **orchestration boundary** (runner, supervisor, framework) rather than just a business method?
2. Is there a clear **error-type policy**, especially for `VirtualMachineError` and `LinkageError`?
3. Does the handler only record/cleanup, or does it return a **false success**?
4. If the handler does not rethrow, is there **genuine state isolation** permitting continuation?
5. Does cleanup preserve the primary error if cleanup itself throws?
6. Is there any `return` or `throw` in `finally` that could mask the original `Error`?
7. When logging is needed, are **class, stack trace, cause, and suppressed** preserved?
8. Is logging cost bounded, avoiding large allocations when resources are scarce?
9. Are uncontrolled retries avoided after `OutOfMemoryError`, `StackOverflowError`, and `LinkageError`?
10. Is there a distinction between raw threads, executor/futures, and plugin runners?
11. Are `InterruptedException` and `ThreadDeath` preserved according to policy?
12. Are **success, recoverable error, and simulated serious error** paths all tested?
13. Do tests **avoid trying to exhaust heap/stack** on shared machines?
14. Who owns the decision to **stop, restart, mark unhealthy, or reconcile** when the boundary cannot guarantee safety?

A `catch(Throwable)` branch without answers to these questions can be considered a **design risk**, even if the code compiles and happy-path tests pass.

## 26. Self-Check Questions

**Q1.** Does `catch(Exception)` catch `OutOfMemoryError`?

**Answer:** No. `Error` is not a subtype of `Exception`.

**Q2.** Does `catch(Throwable)` catch both `Exception` and `Error`?

**Answer:** Yes. That is precisely why it needs a clear boundary and purpose.

**Q3.** Does catching an `Error` prove the application can continue normally?

**Answer:** No. You must determine the error type, available resources, and post-failure state.

**Q4.** Why can a test runner catch a test case's `AssertionError` while not every web request handler should catch `Error`?

**Answer:** A test runner has a contract to **record test failures** and has a test boundary; a request handler cannot by default recover from all JVM or invariant errors.

**Q5.** Does `throw err` from `catch(Error err)` create a new wrapper?

**Answer:** No. It rethrows the exact `Error` object.

**Q6.** Can `throw new RuntimeException("x", err)` cause an outer `catch(Exception)` to catch the wrapper?

**Answer:** Yes; however, an `Error` in the cause can still indicate a critical condition.

**Q7.** Does `finally` run when the body throws `AssertionError` during normal Java execution?

**Answer:** Normally yes. However, it is not guaranteed if the JVM is forcibly terminated or can no longer continue.

**Q8.** If `close()` throws `IOException` while a `try-with-resources` body throws `AssertionError`, where is the close error placed?

**Answer:** Usually in `getSuppressed()` of the primary `AssertionError`.

**Q9.** If a worker thread throws an uncaught `AssertionError`, can `main` continue?

**Answer:** Yes. However, there is no guarantee that shared state and side effects remain valid.

**Q10.** Does `UncaughtExceptionHandler` return the worker to the point before the error was thrown?

**Answer:** No. It receives the error report when the thread terminates abruptly.

**Q11.** Why is `catch(Throwable) { return success; }` dangerous in tasks that process payments or write data?

**Answer:** Errors can occur after unrolled-back side effects; returning false success misleads the caller about state and risks repeating operations.

**Q12.** Is catching `OutOfMemoryError` and creating large log/response objects reliable?

**Answer:** No. Those steps can also require allocations and fail further.

**Q13.** When a task runs in an `ExecutorService`, should you expect every error to be reported by an uncaught handler like a direct `Thread`?

**Answer:** No. Task results and exceptions may be managed by `Future` or the executor's own mechanism.

**Q14.** If you need to clean up resources without turning an `Error` into a success result, what should you use?

**Answer:** Prefer `finally` or `try-with-resources` according to contract, while preserving the original error.

**Q15.** Is a plugin called in the same JVM with `catch(Throwable)` around it already a safe sandbox?

**Answer:** Not yet. It still shares JVM resources and state; additional controls are needed, and sometimes process isolation is required.

## 27. Java 17 References

- [Java SE 17 API — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): error hierarchy, `getCause()`, `getSuppressed()`, stack trace, and `addSuppressed()`.
- [Java SE 17 API — `Error`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Error.html): meaning of the `Error` branch and guidance that applications should not catch it indiscriminately.
- [Java SE 17 API — `Exception`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Exception.html): distinguishing the `Exception` branch.
- [Java SE 17 API — `VirtualMachineError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/VirtualMachineError.html), [`OutOfMemoryError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/OutOfMemoryError.html), [`StackOverflowError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackOverflowError.html): JVM resource errors.
- [Java SE 17 API — `LinkageError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html), [`NoClassDefFoundError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html): linkage and initialization failures.
- [Java SE 17 API — `Thread.UncaughtExceptionHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.UncaughtExceptionHandler.html): handling uncaught `Throwable`s at the thread level.
- [Java SE 17 API — `ThreadDeath`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadDeath.html): historical characteristics of the thread-stopping error.
- [Java Language Specification 17 — §11](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): checked/unchecked classification and exception propagation.
- [Java Language Specification 17 — §14.20](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): `try`, `catch`, `finally`, and `try-with-resources`.
- [Java Language Specification 17 — §12.4.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): class initialization and erroneous state.

**Conclusion:** `catch(Throwable)` or `catch(Error)` only makes sense when placed at a **well-defined boundary**, with a **specific purpose** such as observation, cleanup, reporting failure status, or isolating a controlled fixture. Catching an `Error` does not guarantee sufficient resources or consistent data to continue. In business code, prefer **catching specific `Exception` types with a clear recovery path**; for serious system errors, usually let them propagate, preserve the root cause, and use external monitoring/lifecycle management instead of swallowing the error and returning success.