# Exception Propagation Along the Call Stack in Java

When a Java method throws an exception without a matching `catch` block to handle it, the exception **propagates back along the call chain**. Java exits execution contexts one by one, runs any required `finally` blocks or resource-closing operations, and searches for the nearest matching exception handler. This process is commonly referred to as **exception propagation** and **stack unwinding**.

Understanding this mechanism helps you explain why an error in the data-access layer can be caught in the orchestration layer; why statements after `throw` do not execute; why `finally` still runs; and why a stack trace contains the names of multiple methods even though the exception was thrown at a single location.

## 1. The Call Stack and the Direction an Exception Travels

Each active method invocation has a logical **stack frame** holding execution state, local variables, and information needed to return to the caller. Suppose the flow follows this chain:

~~~text
main() calls outer()
    outer() calls middle()
        middle() calls deepest()
            deepest() throws IllegalStateException
~~~

The state right before the throw can be visualized as follows:

~~~text
Top of call stack
┌───────────────────────────────────────────────┐
│ deepest()       ← exception originates here   │
├───────────────────────────────────────────────┤
│ middle()        ← no matching catch           │
├───────────────────────────────────────────────┤
│ outer()         ← has matching catch          │
├───────────────────────────────────────────────┤
│ main()          ← calls outer()               │
└───────────────────────────────────────────────┘
Bottom of call stack

Propagation path: deepest() → middle() → outer()
~~~

Key points to distinguish:

- The **call flow** goes from the caller to the callee: `main → outer → middle → deepest`.
- An **unhandled exception** travels in the opposite direction: `deepest → middle → outer → main`, until it encounters a matching handler or reaches the end of the thread's stack.
- An exception is a thrown **`Throwable` object**. It does not automatically create a new exception at each layer.
- When a method completes abruptly due to an exception, that method **does not return a normal value**, even if its signature declares a return type.
- The stack used to search for a `catch` is the **dynamic execution** stack: what matters is which calls are currently enclosing the failing operation, not merely class relationships or lexical placement in the source file.

Java Language Specification §11.3 describes finding the nearest dynamically enclosing `catch` capable of handling the exception value. The `try`/`catch`/`finally` construct is specified in detail in §14.20.

## 2. What Does the Runtime Do When It Encounters an Exception?

Consider a statement such as `throw new IllegalStateException("kết nối thất bại");`, or an API that throws an exception itself. The semantic steps are:

1. **Normal execution stops at the throw point:** remaining statements on the normal path of the currently executing block are skipped.
2. **Check handlers in the current context:** the runtime searches the `catch` clauses of enclosing `try` blocks that match the *actual runtime type* of the exception object.
3. **If no matching handler exists:** perform mandatory actions upon exiting the context (such as `finally` or closing resources managed by `try-with-resources`), then complete the current invocation abruptly.
4. **Return to the calling context:** the previous-layer call also completes abruptly; searching for a `catch` continues at that call site.
5. **When a matching `catch` is found:** the `catch` block executes. If it completes normally, propagation of this exception ends. If it throws again, the exception continues propagating along the new path.
6. **If no layer catches it:** the exception escapes the thread's entry-point method; the thread's uncaught exception handling mechanism (`UncaughtExceptionHandler`) is applied and the thread terminates.

This is a **control-flow** model: each layer does not "automatically log," each layer does not automatically append messages to the exception, and the JVM does not run every `catch` along the return path. Only the matching `catch` block is selected according to the language rules; the relevant `finally` blocks still execute while exiting blocks.

## 3. Complete Java 17+ Example: Exception Passing Through a Middle Layer

Save the following content in `PropagationDemo.java`:

~~~java
public class PropagationDemo {
    static String deepest() {
        System.out.println("3. deepest chạy");
        throw new IllegalStateException("kết nối thất bại");
    }

    static String middle() {
        try {
            System.out.println("2. middle chạy");
            return deepest();
        } finally {
            System.out.println("4. finally của middle");
        }
    }

    static void outer() {
        try {
            System.out.println("1. outer chạy");
            System.out.println(middle());
            System.out.println("Dòng này không chạy");
        } catch (IllegalStateException ex) {
            System.out.println("5. outer bắt: " + ex.getMessage());
        } finally {
            System.out.println("6. finally của outer");
        }
    }

    public static void main(String[] args) {
        outer();
        System.out.println("7. Sau outer");
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 PropagationDemo.java
java PropagationDemo
~~~

Exact stdout output:

~~~text
1. outer chạy
2. middle chạy
3. deepest chạy
4. finally của middle
5. outer bắt: kết nối thất bại
6. finally của outer
7. Sau outer
~~~

**Why in this exact order?**

- `main()` calls `outer()`; `outer()` enters `try` and calls `middle()`.
- `middle()` enters `try`, then calls `deepest()`. `deepest()` throws `IllegalStateException` and does not return a `String`.
- `middle()` has no `catch`, but it has `finally`. The JVM executes `middle()`'s `finally` before propagating the exception out of the `middle()` call.
- `outer()` has `catch (IllegalStateException ex)` enclosing the call site of `middle()`, so it handles the exception and prints line 5. The expression `System.out.println(middle())` **prints no result** because evaluating the argument `middle()` failed.
- `outer()`'s `finally` prints line 6. The `outer()` method completes normally because `catch` handled the exception, and `main()` prints line 7.

Notice: the statement `System.out.println("Dòng này không chạy")` does not run because it lies in the part of `try` after the failing call. By contrast, `System.out.println("7. Sau outer")` runs because it sits **after** a call that has already finished handling the exception.

You cannot expect `deepest()` to execute the remaining statements after `throw`, nor can you expect `middle()` to return a value when `deepest()` completes abruptly.

## 4. When Does Propagation Stop, and When Does It Continue?

### 4.1. Catching a matching type ends the current propagation path

A `catch` is selected based on the runtime type of the exception object and inheritance relationships. For example, `catch (RuntimeException ex)` can catch `IllegalStateException`, because `IllegalStateException extends RuntimeException`. `catch (IOException ex)` cannot catch `IllegalStateException`.

Within a `try`, Java selects the **first matching `catch` block**. Write `catch` blocks from subtype to supertype:

~~~java
// Illustrative snippet inside a method.
try {
    throw new IllegalArgumentException("dữ liệu không hợp lệ");
} catch (IllegalArgumentException ex) {
    System.out.println("Sai đối số");
} catch (RuntimeException ex) {
    System.out.println("Lỗi runtime khác");
}
~~~

The output is `Sai đối số`. There is no automatic fall-through to `catch (RuntimeException)` after the first block finishes. If `catch (RuntimeException)` is placed before `catch (IllegalArgumentException)`, the code will not compile because the later, more specific branch is unreachable.

### 4.2. Catching and rethrowing: continuing propagation

A `catch` can record additional context or clean up and then rethrow the same exception object:

~~~java
// Illustrative snippet inside a method.
try {
    callDownstream();
} catch (IllegalStateException ex) {
    System.err.println("Lỗi tại tầng trung gian");
    throw ex;
}
~~~

`throw ex;` continues propagating the **same object**. It is not the same as `throw new IllegalStateException(...)`, because the latter creates a different object; if you need to wrap an exception, pass `ex` as the `cause`.

If `catch` only logs and completes normally, the error is considered handled right there. The caller does not automatically receive the exception again. Therefore, be explicit about intent: genuinely handle it, rethrow it, or wrap it; do not log and pretend the operation succeeded.

### 4.3. Throwing a different exception type at a middle layer

For example, a configuration method reads a file and translates an I/O error into a business-layer message:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

// Illustrative snippet placed in a class.
static String loadConfig(Path path) {
    try {
        return Files.readString(path);
    } catch (IOException ex) {
        throw new IllegalStateException("Không nạp được cấu hình: " + path, ex);
    }
}
~~~

`loadConfig` catches `IOException` and throws a new runtime exception. The caller will see `IllegalStateException` as the outermost exception; `getCause()` returns the original `IOException`. When printing the stack trace, you will typically see a `Caused by:` section for the cause chain.

Wrapping an error is only appropriate when the current layer adds useful meaning. In many I/O APIs, keeping `throws IOException` can be simpler and make the contract clearer.

## 5. Checked vs. Unchecked: Same Runtime Propagation, Different Compile-Time Checking

Both `IOException` (checked) and `IllegalStateException` (unchecked) can cross multiple calls via the runtime mechanism described above. The difference lies in the **compile-time rules**:

- For a checked exception like `IOException`, every method that can let the exception escape must declare a compatible checked type in `throws`, unless it already catches it or it cannot arise through the method's control flow.
- For an unchecked exception like `IllegalStateException`, `NullPointerException`, and `Error` subclasses, `throws` is not required even though they can still propagate across the call stack.
- `throws` communicates responsibility to **calling code at compile time**. It does not create a runtime handler branch and does not intercept the exception.

A valid checked exception example:

~~~java
import java.io.IOException;

// Methods in the same class.
static void lowLevel() throws IOException {
    throw new IOException("không thể đọc");
}

static void middleLevel() throws IOException {
    lowLevel();
}

static void topLevel() {
    try {
        middleLevel();
    } catch (IOException ex) {
        System.out.println(ex.getMessage());
    }
}
~~~

When `topLevel()` is called, stdout is `không thể đọc`. If `throws IOException` is removed from `middleLevel()`, the code above fails to compile with an error such as `unreported exception IOException; must be caught or declared to be thrown`. This is required at the **definition** of `middleLevel`, regardless of whether `topLevel` eventually catches the error.

## 6. Impact of `finally` During Stack Unwinding

`finally` is executed when exiting the associated `try`/`catch`, whether by normal completion, `return`, or throwing an exception. This is an important reason why "unwinding the call stack" does not mean skipping all code in intermediate layers.

~~~java
// Illustrative snippet inside a method.
try {
    throw new IllegalStateException("lỗi gốc");
} finally {
    System.out.println("Dọn dẹp trước khi truyền lỗi");
}
~~~

The `finally` block prints the message and then the exception still propagates outward (because `finally` completes normally). This sequence can repeat across multiple calls, from the `finally` of a deeper layer up to the `finally` of a shallower layer.

**Warning about masked exceptions:** if `finally` itself throws another exception, or executes `return`, the original reason for exiting the block can be replaced. The following example returns `2` even though the `try` block prepared `return 1`:

~~~java
// Illustrative snippet that should not be used in real-world design.
static int unsafeReturn() {
    try {
        return 1;
    } finally {
        return 2;
    }
}
~~~

Even more dangerously, `return` or `throw` in `finally` can mask the real exception currently propagating. Put only appropriate cleanup work in `finally`, and avoid writing abrupt control-flow termination there.

`finally` is a guarantee under Java semantics when a block is exited normally or abruptly; it is **not an absolute promise** if the JVM or process is forcibly terminated, such as by `Runtime.halt` or a power loss.

## 7. `try-with-resources`: Primary Exception and Suppressed Exceptions

To manage `AutoCloseable` objects, `try-with-resources` automatically invokes `close()` when exiting the block. Resources are closed in the **reverse order of their successful initialization**.

Both the `try` body and `close()` can throw exceptions. In that case, Java prioritizes preserving the primary exception from the `try` body; any exception thrown during closing is recorded as a **suppressed exception** (accessible via `getSuppressed()`), rather than masking the primary error like a carelessly written `finally` block.

Standalone program `SuppressedDemo.java`:

~~~java
public class SuppressedDemo {
    static class BrokenResource implements AutoCloseable {
        @Override
        public void close() throws Exception {
            throw new Exception("lỗi đóng");
        }
    }

    public static void main(String[] args) {
        try (BrokenResource resource = new BrokenResource()) {
            throw new Exception("lỗi xử lý");
        } catch (Exception ex) {
            System.out.println("Chính: " + ex.getMessage());
            System.out.println("Suppressed: " + ex.getSuppressed()[0].getMessage());
        }
    }
}
~~~

Run with:

~~~bash
javac -encoding UTF-8 SuppressedDemo.java
java SuppressedDemo
~~~

Stdout:

~~~text
Chính: lỗi xử lý
Suppressed: lỗi đóng
~~~

If the `try` body does not throw an exception but `close()` does, the exception from `close()` can become the propagating exception. When reading stack traces from code with multiple resources, check both `Caused by` (the cause chain) and `Suppressed` (secondary errors during resource cleanup); they are not the same relationship.

## 8. Reading a Stack Trace to Trace the Call Path

`Throwable.printStackTrace()` prints the exception type, message, and relevant stack frames. For an exception created in `deepest()` and thrown while called from `middle()` and `outer()`, the format may look like:

~~~text
java.lang.IllegalStateException: kết nối thất bại
    at PropagationDemo.deepest(PropagationDemo.java:4)
    at PropagationDemo.middle(PropagationDemo.java:10)
    at PropagationDemo.outer(PropagationDemo.java:19)
    at PropagationDemo.main(PropagationDemo.java:29)
~~~

This is a **format illustration**, not the stdout of the `PropagationDemo` program in section 3 (because that program caught the exception and only printed `getMessage()`). Line numbers in a stack trace depend on the exact saved source code and environment; you should not infer them from illustrative examples.

When analyzing a trace:

1. The first line shows the **exception type and message**.
2. The top frame usually points to where the stack trace was recorded when the exception object was created or `fillInStackTrace()` was called; the frames below represent the call chain at that time.
3. Read from top to bottom to trace back through the caller layers; read from bottom to top to see the entry path into the call that led to the error.
4. If `Caused by:` is present, follow the deeper cause; the outermost error may just be a wrapper around the root error.
5. If `Suppressed:` is present, inspect secondary errors that occurred during resource cleanup.

A common misconception: **propagation does not automatically push additional frames onto the stack trace on each `throw ex;`**. An exception object carries the trace captured at creation or when its stack trace was updated, typically at the deep layer. When a new wrapper exception is created, the wrapper has its own stack trace at the wrapping point; the original exception remains linked via `cause`.

For good diagnostics, log the full exception once at the boundary responsible for reporting errors (passing the object itself to the logger to preserve the trace), and add context when crossing layers. Logging and rethrowing at every layer typically produces duplicate records without adding value.

## 9. Does Propagation Cross Thread Boundaries?

**Not automatically.** A call stack belongs to a single executing thread; an exception in a child thread does not unwind back into the stack of the thread that called `Thread.start()`.

~~~java
// Illustrative snippet: catch outside start() does not catch errors inside the task.
try {
    Thread worker = new Thread(() -> {
        throw new IllegalStateException("lỗi của worker");
    });
    worker.start();
} catch (IllegalStateException ex) {
    // Does not handle the exception thrown later in the worker thread.
}
~~~

The `start()` call happens on the calling thread and primarily starts another thread. The exception occurs when the lambda executes on `worker`'s **own call stack**. If `worker` does not handle it itself, the exception goes to `worker`'s `UncaughtExceptionHandler`; the `catch` around `start()` does not receive it.

Similarly, when using `ExecutorService.submit(Callable)`, an error inside the task is typically held in the `Future`; when calling `future.get()`, the receiver may encounter **`ExecutionException`** and retrieve the task error via `getCause()`. With `CompletableFuture.join()`, an abnormal failure is typically reflected via **`CompletionException`**. This mechanism transfers **error information through the task result**, rather than throwing the same exception across two independent call stacks.

This matters when debugging applications with thread pools, callbacks, or asynchronous tasks: you need to locate where the task runs, where the result is collected, and any exception-wrapping layer; you cannot simply wrap the launch site in a `try/catch` and expect to catch all future errors.

## 10. What If No `catch` Matches?

For synchronous calls, when an exception is not caught anywhere along the current call path, it reaches the thread's execution boundary. The JVM applies the configured `Thread.UncaughtExceptionHandler`; the default handler typically prints the error details and stack trace to standard error. The thread terminates due to the uncaught exception.

If it is the only `main` thread of a simple program, the process usually terminates. If it is a worker thread, other threads do not necessarily stop along with it; application-level behavior depends on how threads and tasks are managed. Some frameworks/executors **capture the error** and return it as an abnormal result instead of letting it reach the default handler.

Do not use broad `catch (Throwable)` or `catch (Error)` everywhere to "prevent the program from stopping": serious JVM errors may be unrecoverable. Catch exceptions you actually know how to handle; configure error handling at application boundaries according to observability and operational requirements.

## 11. Common Reasoning Mistakes and Design Pitfalls

| Misconception | Reality | How to handle it |
| --- | --- | --- |
| An exception is always caught right inside the throwing method | It is searched from the nearest context outward through callers. | Draw the call chain and mark `try` scopes. |
| After `throw`, execution continues with the rest of `try` | Normal execution stops; matching `finally` blocks still run. | Trace normal and abnormal flows separately. |
| `throws` resolves or swallows an error | `throws` only declares to the compiler, not a runtime catch. | Place `catch` at a layer that has a real handling strategy. |
| Every compatible `catch` along the path executes | Only the nearest matching handler is chosen for that throw. | Note where `catch` completes or rethrows. |
| `finally` is unrelated to exceptions | It runs while exiting the block and can affect the propagation path. | Clean up safely; avoid `return`/`throw` that masks the original error. |
| `throw ex` always updates the stack trace at the rethrow site | Rethrowing the same object usually keeps the existing trace. | Use `cause` when creating a new exception with added context. |
| A `catch` outside `thread.start()` catches errors in the new thread | Each thread has its own call stack. | Handle errors inside the task or read the `Future` result. |
| Logging the same error at every layer makes debugging better | It easily produces duplicate logs for a single incident. | Wrap with sufficient context and log once at an appropriate observation point. |
| An exception from `close()` always replaces the processing error | `try-with-resources` has a suppressed-exception mechanism. | Inspect `getSuppressed()` alongside `getCause()`. |

A practical debugging approach is to mark three locations: **the throw point**, **cleanup blocks along the path**, and **the catch point**. If there is no catch point, identify the thread boundary or task-execution mechanism receiving the error. Then trace `cause` and `suppressed` so the root cause is not missed.

## 12. Self-Check Questions

1. **A calls B, B calls C, C throws `RuntimeException`. B has no `catch`, A catches `RuntimeException`. Who handles it?** — A handles it; the exception travels C → B → A, unless B has a `finally` block that alters the exit path.
2. **Does a `return` after a failing call execute?** — No, if the exception was not caught inside that call or expression.
3. **If B has `finally` and A has `catch`, what is the order?** — B's `finally` completes before control transfers to A's `catch`, assuming `finally` does not complete abruptly.
4. **Does `catch (Exception)` catch `Error`?** — No; `Error` is not a subclass of `Exception`.
5. **Does rethrowing the same object with `throw ex` create a new exception?** — No; it is the same object, keeping its existing trace unless explicitly updated.
6. **Can `try (resource)` preserve both a body error and a `close()` error?** — Yes, the close error can be found in `getSuppressed()` of the primary error.
7. **Does an error in a `Callable` run by an executor jump directly into a `catch` around `submit()`?** — No; you typically need to check `Future.get()` and `ExecutionException.getCause()`.

## References

- Java Language Specification 17, [§11.3 — Run-Time Handling of an Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.3): mechanism for finding a `catch` in the execution context.
- Java Language Specification 17, [§14.18 — The throw Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.18): how a `throw` statement completes abruptly.
- Java Language Specification 17, [§14.20 — The try Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): `catch` selection, `finally` execution, and `try-with-resources`.
- Java SE 17 API, [Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()`, `getSuppressed()`, `printStackTrace()`.
- Java SE 17 API, [Thread.UncaughtExceptionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.UncaughtExceptionHandler.html) and [Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): observing errors at thread/task boundaries.

Key takeaway: an exception travels back through **active calls** to find the nearest compatible `catch`; stack unwinding still obeys `finally` and resource-closing rules, while handling or rethrowing at the catching layer determines subsequent execution flow.
