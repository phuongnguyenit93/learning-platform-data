# Runnable, Callable, and Differences in Exception Declarations in Java

> **Java Core – Exception** · Group: **Lambdas and generics** · Focus: the `throws` contract of the target method, how lambdas handle checked exceptions, and how exceptions propagate from tasks to callers via `Future`. Applies to Java 17+.

## 1. Core Answer

`Runnable` and `Callable<V>` are both **functional interfaces**, so their implementations can be created using lambdas. However, the two interfaces have different method signatures:

~~~java
// Core contract of java.lang.Runnable:
void run();

// Core contract of java.util.concurrent.Callable<V>:
V call() throws Exception;
~~~

These are **two illustrative signature declarations**, not a standalone Java file.

They differ in **two independent aspects**:

1. **Result:** `Runnable.run()` returns `void`; `Callable<V>.call()` returns a value of type `V`.
2. **Checked exceptions:** `Runnable.run()` **declares no checked exceptions**; `Callable<V>.call()` declares `throws Exception`. A lambda or implementation of `Callable<V>` can let a compatible checked exception escape from `call()`; a lambda/implementation of `Runnable` must **handle** checked exceptions itself because they are not permitted by the `run()` contract.

**Crucially:** `Runnable` can still throw **unchecked exceptions** such as `IllegalStateException` or `UncheckedIOException`. Having no `throws` clause **does not mean an error can never occur**.

At the same time, `Callable.call() throws Exception` does not mean it **always throws an exception**. It can return a result normally; it can also throw unchecked exceptions. The `throws` clause states the checked exception bound that the method is allowed to propagate under the Java type system, not a guaranteed event.

### Quick Comparison

| Characteristic | `Runnable` | `Callable<V>` |
| --- | --- | --- |
| Functional method | `void run()` | `V call() throws Exception` |
| Return value | None | Type `V`, e.g., `String`, `Integer` |
| Allows checked exceptions to escape directly? | No, due to the `run()` signature | Yes, within the `throws Exception` bound |
| Can throw unchecked exceptions? | Yes | Yes |
| Used directly with `new Thread(...)`? | Yes | No; must be adapted to `Runnable` or use another mechanism |
| Submitted to `ExecutorService.submit`? | Yes | Yes |
| `submit` returns | `Future<?>`; `get()` returns `null` on success | `Future<V>`; `get()` returns a `V` value on success |
| Task failure when accessed via `Future.get()` | Typically wrapped in `ExecutionException.getCause()` | Also wrapped in `ExecutionException.getCause()` |

The `Future` rows apply to tasks submitted via the `submit(Runnable)` and `submit(Callable<T>)` overloads, **not directly to calling `run()` or `call()` yourself**.

## 2. Why Do Lambdas Care About `throws`?

A lambda expression in Java does not have a standalone type on its own. It is **target-typed** to the functional interface at the position where it is used. It is the signature of the **functional method** that determines parameter types, return type, and which checked exceptions the lambda body is allowed to let escape.

Example:

~~~java
import java.io.IOException;
import java.util.concurrent.Callable;

class Illustrations {
    static String read() throws IOException {
        throw new IOException("unavailable");
    }

    static void example() {
        Callable<String> task = () -> read(); // Valid.
    }
}
~~~

This is a valid illustrative class. The lambda has the target type `Callable<String>`, so its body calling `read()` can throw `IOException`; `call()` permits `Exception`, which is a superclass of `IOException`.

Conversely:

~~~java
// INTENTIONALLY DOES NOT COMPILE; placed in a context with read() throws IOException:
Runnable task = () -> {
    read(); // Unhandled exception type IOException.
};
~~~

The target type here is `Runnable`. Its functional method `run()` **has no checked `throws`**, so the lambda body cannot let `IOException` escape. The fact that `Runnable` might run on a separate thread **does not exempt it from this compiler rule**.

This is not a lambda-specific limitation. A class implementing `Runnable` is subject to the same overriding rules:

~~~java
// INTENTIONALLY DOES NOT COMPILE:
class BadTask implements Runnable {
    @Override
    public void run() throws java.io.IOException {
        throw new java.io.IOException("failed");
    }
}
~~~

Reason: an override cannot add new checked exceptions beyond the `Runnable.run()` contract.

**Conclusion:** whether a checked exception may escape depends on **the method signature being implemented**, not on whether the lambda uses braces or whether it runs asynchronously.

## 3. Distinguishing Checked vs. Unchecked When Reading APIs

According to [JLS Java 17 Chapter 11](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html), checked exceptions must be caught or appropriately declared; unchecked exceptions are not subject to compile-time declaration requirements.

~~~text
Throwable
├── Error                         → unchecked
└── Exception
    ├── IOException               → checked
    ├── InterruptedException      → checked
    ├── ExecutionException        → checked
    └── RuntimeException          → unchecked
        ├── IllegalStateException
        ├── IllegalArgumentException
        └── UncheckedIOException
~~~

This is an **abbreviated tree** showing only the relevant classes, not the entire hierarchy.

Method example:

~~~java
static String load() throws java.io.IOException {
    throw new java.io.IOException("I/O failed");
}
~~~

In a `Callable<String>` lambda, you can call `load()` and let `IOException` escape. In a `Runnable` lambda, you must catch, handle, or **intentionally** convert it into an unchecked exception.

A `RuntimeException` can be thrown from either kind of lambda without an explicit `throws` clause. Do not label `Runnable` as “unable to throw” just because you see `void run()`.

## 4. Choosing Between Runnable and Callable Based on the Task Contract

Choose based on the **caller's needs**, not just which lambda is shorter to write.

### Choose Runnable when

- The task **does not need to return a result** through the functional method.
- Checked exceptions arising inside can be **handled locally**, or there is an appropriate policy for converting them to unchecked exceptions.
- You only need to call `run()` directly, or use `Thread`, `Executor.execute`, or `ExecutorService.submit(Runnable)`.

Example:

~~~java
Runnable announce = () -> System.out.println("Task completed");
announce.run();
~~~

Output:

~~~text
Task completed
~~~

This example **runs synchronously** on the calling thread when using `announce.run()`. A `Runnable` object itself does not create a new thread. To schedule it or run it on a separate thread, you must use a mechanism such as `new Thread(announce).start()` or an executor.

### Choose Callable when

- The task needs to **return a typed value**.
- The body may let **checked exceptions** escape under the `call() throws Exception` contract.
- The caller plans to retrieve the result via `Future<V>`, or call `call()` directly in a context that handles `Exception`.

Example:

~~~java
Callable<Integer> count = () -> 42;
~~~

This snippet requires importing `java.util.concurrent.Callable`. The generic type `Integer` is used as the return type of `call()`. The compiler does not require the lambda to throw a specific checked exception; it simply **allows** compatible ones if they occur.

### Is `Callable<Void>` Completely Equivalent to `Runnable`?

No. When you do not need a result but want to preserve the checked-exception contract, you can use:

~~~java
Callable<Void> task = () -> {
    performWork();
    return null;
};
~~~

This is an illustrative snippet; it requires a suitable `performWork()` method and importing `Callable`. It returns `null` because the `Void` type does not represent a normal result value. However, **the functional method signature is still `call() throws Exception`**, which differs from `Runnable.run()`. Therefore, the two interfaces are not completely equivalent just because the result can be `null`.

## 5. Complete Java 17 Example: Five Distinguishing Scenarios

Create the file **`RunnableCallableExceptionDemo.java`**. The program demonstrates `Runnable`, `Callable`, checked exceptions, wrapping `IOException` as an unchecked exception, and the `Callable<Void>` case.

It uses an `ExecutorService` with **a single worker thread** and waits for each `Future` before moving to the next step so that the output is easy to verify and does not depend on race ordering among multiple tasks.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class RunnableCallableExceptionDemo {
    private static String read(String key) throws IOException {
        if ("fail".equals(key)) {
            throw new IOException("file unavailable");
        }
        return "DATA:" + key;
    }

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        Runnable plain = () -> System.out.println("runnable=done");

        Callable<String> successful = () -> read("ok");
        Callable<String> checkedFailure = () -> read("fail");

        Runnable adapted = () -> {
            try {
                read("fail");
            } catch (IOException ex) {
                throw new UncheckedIOException("runnable I/O failure", ex);
            }
        };

        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            System.out.println("== successful jobs ==");
            Future<?> plainFuture = executor.submit(plain);
            System.out.println("runnable-result=" + plainFuture.get());

            Future<String> callFuture = executor.submit(successful);
            System.out.println("callable-result=" + callFuture.get());

            System.out.println("== checked exception from Callable ==");
            Future<String> checkedFuture = executor.submit(checkedFailure);
            try {
                checkedFuture.get();
            } catch (ExecutionException ex) {
                System.out.println("wrapper=" + ex.getClass().getSimpleName());
                Throwable cause = ex.getCause();
                System.out.println("cause=" + cause.getClass().getSimpleName()
                        + ": " + cause.getMessage());
            }

            System.out.println("== checked exception adapted to Runnable ==");
            Future<?> adaptedFuture = executor.submit(adapted);
            try {
                adaptedFuture.get();
            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause();
                System.out.println("cause=" + cause.getClass().getSimpleName()
                        + ": " + cause.getMessage());
                System.out.println("root="
                        + cause.getCause().getClass().getSimpleName()
                        + ": " + cause.getCause().getMessage());
            }

            System.out.println("== Callable<Void> ==");
            Callable<Void> noValue = () -> {
                System.out.println("callable-void=done");
                return null;
            };
            System.out.println("void-result=" + executor.submit(noValue).get());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

### Compile and Run

Using JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 RunnableCallableExceptionDemo.java
java RunnableCallableExceptionDemo
~~~

**Exact stdout, run and verified:**

~~~text
== successful jobs ==
runnable=done
runnable-result=null
callable-result=DATA:ok
== checked exception from Callable ==
wrapper=ExecutionException
cause=IOException: file unavailable
== checked exception adapted to Runnable ==
cause=UncheckedIOException: runnable I/O failure
root=IOException: file unavailable
== Callable<Void> ==
callable-void=done
void-result=null
~~~

The example **was compiled with `javac --release 17` and executed successfully**. It requires no real files or network; the `read()` method simulates success/failure with fixed messages. For clarity, tasks are submitted and awaited step by step; the output does not depend on thread names or arbitrary scheduling order.

**Java 17 environment note:** `ExecutorService` in the example is shut down with `shutdown()` in `finally`. Do not use `try (ExecutorService ...)` if your code must compile against Java 17; `AutoCloseable` support on this interface in newer Java versions does not change Java 17 source compatibility.

## 6. Analyzing Stdout: Success with Runnable and Callable

### 6.1. Runnable Returns No Value, Yet `Future.get()` Still Exists

Snippet:

~~~java
Runnable plain = () -> System.out.println("runnable=done");
Future<?> plainFuture = executor.submit(plain);
System.out.println("runnable-result=" + plainFuture.get());
~~~

There are two distinct layers of behavior:

- `Runnable.run()` itself has a `void` return type and produces no result object.
- `ExecutorService.submit(Runnable)` **returns a `Future<?>` to track completion status**; if the task completes normally, `get()` returns `null`.

At runtime, the task prints `runnable=done` first. After `plainFuture.get()` returns, the caller prints `runnable-result=null`.

**Do not confuse this:** the `Runnable` lambda does not “return null”; the `null` value is **the result defined by the `submit(Runnable)` overload for `Future`**, while the functional method remains `void run()`.

### 6.2. `Callable<String>` Returns `String` via `Future<String>`

Snippet:

~~~java
Callable<String> successful = () -> read("ok");
Future<String> callFuture = executor.submit(successful);
System.out.println("callable-result=" + callFuture.get());
~~~

At runtime, `read("ok")` returns `"DATA:ok"`. Because the callable succeeds, `Future.get()` returns that exact string. At compile time, the `String` generic argument lets the caller know the result is a string rather than an `Object` requiring a manual cast.

The type parameter `V` of `Callable<V>` describes the **return value type**; it is **not** a generic parameter describing an exception type. The signature of `call()` still declares `throws Exception` regardless of whether `V` is `String`, `Integer`, or `Void`.

## 7. Callable Throws IOException: How Does `Future.get()` Propagate Errors?

Snippet:

~~~java
Callable<String> checkedFailure = () -> read("fail");
Future<String> checkedFuture = executor.submit(checkedFailure);
try {
    checkedFuture.get();
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    System.out.println(cause.getClass().getSimpleName());
}
~~~

Step-by-step analysis:

1. The lambda body has target type `Callable<String>`, so calling `read("fail")` is allowed to let `IOException` escape from `call()`.
2. The executor runs the callable on a worker thread.
3. `read("fail")` throws `IOException("file unavailable")`.
4. The task completes **exceptionally**. When the caller invokes `Future.get()`, the API throws `ExecutionException`, whose **cause is the original `Throwable`** from the task.
5. The caller inspects `ex.getCause()` to see the exact cause; in this program, it is `IOException`.

Stdout shows:

~~~text
wrapper=ExecutionException
cause=IOException: file unavailable
~~~

**Java does not automatically turn `IOException` into `ExecutionException` simply because `call()` is declared.** The wrapping happens at the **boundary of retrieving the result through `Future`**. If you invoke `checkedFailure.call()` directly on the same thread, the original exception is thrown directly to the caller of `call()` and must be handled according to `throws Exception`; there is no automatic wrapping into `ExecutionException` just because the object is a `Callable`.

### Which Checked Exceptions Must the Caller Catch at `get()`?

The key signature of `Future.get()`:

~~~java
V get() throws InterruptedException, ExecutionException;
~~~

This is an abbreviated signature parameterized by `Future`'s type `V`, not a standalone file.

- `InterruptedException`: **the thread waiting on `get()`** was interrupted while waiting. It is not necessarily an error from the callable body.
- `ExecutionException`: **the task failed**; inspect `getCause()` for the `Throwable` thrown by the task.
- `CancellationException`: unchecked; can occur if the `Future` was cancelled.
- `get()` can block until the task finishes; the overload with a timeout can also throw `TimeoutException`.

Do not write `catch (IOException)` directly around `future.get()` expecting to catch `IOException` from the callable. Outside `Future`, the API reports task failures through `ExecutionException`.

## 8. Runnable Encounters IOException: Must Handle Inside the Lambda

Main program example:

~~~java
Runnable adapted = () -> {
    try {
        read("fail");
    } catch (IOException ex) {
        throw new UncheckedIOException("runnable I/O failure", ex);
    }
};
~~~

Why must `IOException` be caught? Because `Runnable.run()` does not allow checked `IOException` to escape. Why can we `throw new UncheckedIOException(...)`? Because `UncheckedIOException extends RuntimeException`, which is unchecked.

Choosing a wrapper should be explicit:

- It **does not make the read operation succeed**; the error still propagates.
- It changes the **error propagation contract from checked to unchecked**.
- Passing the cause to the constructor preserves the original `IOException` for diagnostics.
- If a system can recover from an I/O error inside the task, it can **handle it locally** instead of wrapping it.
- Do not “catch `IOException` and ignore it” just to make `Runnable` compile; doing so can cause silent false successes.

When submitting the failing `Runnable` via `executor.submit(adapted)`, the worker thread throws `UncheckedIOException`. When the caller calls `Future.get()`, it receives `ExecutionException` with `UncheckedIOException` as its cause, and **the cause of `UncheckedIOException`** is the original `IOException`.

~~~text
ExecutionException
  └── UncheckedIOException("runnable I/O failure")
        └── IOException("file unavailable")
~~~

That is why stdout distinguishes the two lines:

~~~text
cause=UncheckedIOException: runnable I/O failure
root=IOException: file unavailable
~~~

### Why Not Throw IOException Directly from Runnable Using Casts?

Do not use “sneaky throws”, generic casting tricks that fool the compiler, reflection, or other workarounds to bypass checked exceptions just to let `IOException` escape `Runnable.run()`. They make the public signature mismatch the caller's expectations and make code harder to understand and maintain.

When a task genuinely needs to throw checked exceptions, **using `Callable` or a custom functional interface with an appropriate `throws` clause** is the clearer choice. If a framework mandates `Runnable`, choose a clear handling policy or an unchecked wrapper with a preserved cause.

## 9. `Callable<Void>` When `throws` Is Needed Without a Return Value

`Callable`'s signature always returns type `V`. If you only need the checked-exception contract without a meaningful result, use `Callable<Void>`:

~~~java
Callable<Void> task = () -> {
    saveDocument();
    return null;
};
~~~

This is an **illustrative snippet**; it requires importing `Callable` and defining `saveDocument()`. The lambda must have a `return null;` branch for normal completion. Because the target type is `Callable<Void>`, `saveDocument()` may throw a compatible checked exception.

In the runnable program, the task is declared as:

~~~java
Callable<Void> noValue = () -> {
    System.out.println("callable-void=done");
    return null;
};
System.out.println("void-result=" + executor.submit(noValue).get());
~~~

On normal completion, `Future` returns `null`. Compared with `Runnable`:

- Both can yield a `Future` with a `null` result.
- However, their **functional signatures** differ: `Callable<Void>.call() throws Exception` versus `Runnable.run()` with no checked `throws`.
- Callback APIs that require `Runnable` **do not automatically accept `Callable<Void>`**. You need an adapter or a matching overload.

## 10. Differences Between Direct Invocation and Executor Submission

It is important to distinguish **three contexts**:

| Execution method | Where it runs | Result retrieval | Exceptions |
| --- | --- | --- | --- |
| `runnable.run()` | Current thread | None | Unchecked exceptions propagate directly if uncaught |
| `callable.call()` | Current thread | `V` value directly | Can propagate checked `Exception` per signature |
| `executor.submit(runnable)` | Executor-managed thread | `Future<?>` returning `null` on success | Failure surfaced via `ExecutionException` on `get()` |
| `executor.submit(callable)` | Executor-managed thread | `Future<V>` | Failure surfaced via `ExecutionException` on `get()` |
| `executor.execute(runnable)` | Managed by executor | No `Future` | Unchecked handling depends on implementation/uncaught handling; no `Future.get()` to observe |
| `new Thread(runnable).start()` | New thread | No `Future` | Uncaught thread exception handled by `Thread`/JVM uncaught exception handler |

A common point of confusion: **`executor.execute(runnable)` and `executor.submit(runnable)` do not provide the same exception observation mechanism.** With `submit`, the executor returns a `Future`; task failures are retrieved when calling `get()`. With `execute`, the caller receives no `Future` from that API, so it cannot rely on `get()` to detect task failure.

Additionally, `new Thread(callable)` is not a standard overload accepting `Callable`. To run a `Callable` directly with `Thread`, you can use `FutureTask<V>` (which is both a `Runnable` and a `Future`), or more simply use `ExecutorService` if the goal is to submit tasks and retrieve results.

### Do Thread and Runnable Differ on Checked Exceptions?

No: `Runnable.run()` **keeps the exact same signature** whether run directly, on a `Thread`, or in an executor. Scheduling on another thread does not allow a `Runnable` lambda to throw checked `IOException` without handling it.

### Callable Does Not Mean Asynchronous

`callable.call()` is an ordinary method call that runs on the current thread if invoked directly. Only when submitted to an executor or another scheduling mechanism is execution controlled by a framework/scheduler. Similarly, `runnable.run()` is just a normal method call.

## 11. What Role Do Generics Play in `Callable<V>`?

Consider:

~~~java
Callable<String> textTask = () -> "hello";
Callable<Integer> numberTask = () -> 123;
Callable<Void> actionTask = () -> {
    System.out.println("done");
    return null;
};
~~~

This is an **illustrative snippet**, requiring `Callable` to be imported. The return types of `call()` are `String`, `Integer`, and `Void`, respectively; the Java compiler checks the return type in the lambda against the target type.

However, every parameterization still uses a functional method declared with `throws Exception`. There is no generic type parameter such as `E extends Exception` in standard `Callable` to specify a narrower checked exception type.

If you need a narrower contract, you can define your own:

~~~java
@FunctionalInterface
interface IoTask<T> {
    T execute() throws java.io.IOException;
}
~~~

This is a valid interface definition that can be placed inside a class or in its own file. A lambda assigned to `IoTask<String>` is permitted to throw `IOException`, but **cannot arbitrarily throw checked `SQLException`** because the contract only allows `IOException`.

Note that `IoTask<T>` **is not a `Callable<T>`** just because their signatures look similar. To pass it to an API expecting `Callable`, convert it:

~~~java
IoTask<String> io = () -> readData();
Callable<String> callable = io::execute;
~~~

This illustrative snippet requires a matching `readData()` method and importing `Callable`. The method reference `io::execute` throws checked `IOException`, which is valid because `Callable` permits `Exception`.

**General rule:** Checked-exception compatibility is analyzed by the compiler against the **functional target** of the lambda or method reference; generics specify data types, and do not automatically “erase” `throws` constraints.

## 12. Adapter from a Throwing Functional Interface to Runnable

If an API truly accepts only `Runnable`, you can write a centralized adapter instead of repeating `try/catch` in every lambda.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;

@FunctionalInterface
interface IoAction {
    void run() throws IOException;
}

class Adapters {
    static Runnable asRunnable(IoAction action) {
        return () -> {
            try {
                action.run();
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        };
    }
}
~~~

This is a **valid illustrative Java snippet** without a `main` method. Usage where a method throws `IOException`:

~~~java
Runnable task = Adapters.asRunnable(() -> readInput());
~~~

`readInput()` must be defined. The adapter only changes how the exception is surfaced through `Runnable.run()`; **it does not turn an `IOException` into a successful result**.

Risks to consider:

- Callers of the `Runnable` may be unaware of the wrapper if the API is not documented.
- If the error can be handled where the task is created, catching and recovering may be better than wrapping and propagating.
- For `InterruptedException`, do not blindly wrap it and discard the interrupt status; see Section 14.
- If the business logic needs a return value or wants to preserve checked exceptions in their original form, `Callable` is usually simpler than an adapter.

## 13. Be Careful When Using Lambdas in Overloads Accepting Runnable/Callable

An API may provide overloads such as:

~~~java
Future<?> submit(Runnable task);
<T> Future<T> submit(Callable<T> task);
~~~

These are **two abbreviated API signatures** from `ExecutorService`. Java uses target typing and overload resolution rules to decide which functional interface a lambda matches.

Example with explicit variable declarations:

~~~java
Runnable r = () -> process();
Callable<String> c = () -> load();
~~~

`process()` and `load()` are illustrative placeholder names. With explicit target types, the compiler knows `r` is a `Runnable` (no checked `throws` allowed) and `c` is a `Callable<String>` (`Exception` allowed).

If you pass a lambda directly to an overloaded method and the compiler reports an **ambiguous** call or a `throws`/return-type compatibility error, do not try to solve it by “removing checked exceptions” from the body. Instead, assign a variable of type `Runnable` / `Callable<T>` or cast the lambda to the intended target type:

~~~java
executor.submit((Callable<String>) () -> load());
~~~

This snippet is illustrative; `executor` and `load()` must be declared. Choosing the target type also selects the **checked-exception contract** that the body is allowed to let escape.

**Do not cast the target type just to trick the caller**: carefully check whether the task should return a result, throw checked exceptions, and how failures will be handled after execution.

## 14. `InterruptedException` When Waiting on `Future` Is Not an `IOException` from the Task

`Future.get()` can throw `InterruptedException` when **the thread waiting for the result** is interrupted. This is a separate checked exception from any exception thrown by the callable itself.

An appropriate way to handle it when `InterruptedException` cannot be propagated further:

~~~java
try {
    String value = future.get();
    use(value);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Stop or signal cancellation appropriately for the application's control flow.
    return;
} catch (ExecutionException ex) {
    handleTaskFailure(ex.getCause());
}
~~~

This is an **illustrative snippet**, placed in a method whose return type matches `return;`, with `future`, `use`, `handleTaskFailure`, and the corresponding imports defined.

**Why call `Thread.currentThread().interrupt()`?** When a waiting operation throws `InterruptedException`, the interrupt flag is typically cleared as the exception is thrown. If the method cannot declare/propagate `InterruptedException`, restoring the flag so higher layers know an interruption was requested is a standard policy. Afterwards, you should **stop the current work** rather than continuing as if nothing happened.

If the method can declare `throws InterruptedException` and responsibility belongs to the caller, **propagating the checked exception** is usually clearer than catching and ignoring it.

Avoid writing:

~~~java
// BAD PATTERN: swallowing the interrupt request.
try {
    future.get();
} catch (InterruptedException ex) {
    // Ignore and continue normally.
}
~~~

This is an illustrative anti-pattern and does not handle `ExecutionException`, so it is not a standalone program. The main takeaway is **never silently ignore interrupts** in concurrent code.

## 15. Timeouts and Cancellation Do Not Change the `throws` of `Runnable`/`Callable`

`Future.get(timeout, unit)` can also throw `TimeoutException` if the wait time expires before the task completes. **Timing out while waiting** does not automatically mean the task has stopped.

If the application decides to cancel:

~~~java
future.cancel(true);
~~~

this is a **cancellation request**, which may interrupt the running thread if the task allows it and the backend supports it. There is no guarantee that every I/O or CPU operation will stop immediately. Tasks must be designed to cooperate with interruption/cancellation.

Exceptions at this boundary should be distinguished:

- `ExecutionException`: the task completed with a failure; inspect the cause.
- `InterruptedException`: the waiting thread was interrupted.
- `TimeoutException`: the result was not obtained within the specified time.
- `CancellationException`: the `Future` was cancelled.
- Unchecked exceptions from the task itself: when observed through `Future.get()` of a submitted task, they are typically wrapped in `ExecutionException` rather than appearing directly as in a synchronous method call.

Do not assume that `Callable.call() throws Exception` is the reason `Future.get()` can throw `InterruptedException` or `TimeoutException`. Those come from **the waiting and task-management mechanism**, not from the business method's own requirements.

## 16. Scheduling, Shutdown, and Observing Exceptions

A task example may run properly yet still mismanage the executor if it forgets to shut it down. With Java 17:

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();
try {
    Future<String> result = executor.submit((Callable<String>) () -> "done");
    System.out.println(result.get());
} finally {
    executor.shutdown();
}
~~~

This is an **illustrative snippet** inside a method that handles/declares `InterruptedException` and `ExecutionException` and imports the concurrency APIs. `shutdown()` tells the executor to stop accepting new work and continue processing previously submitted tasks according to its policy; **it does not necessarily wait for all tasks to finish**. If the application needs to wait for resources to actually stop, it must use `awaitTermination(...)` with an appropriate timeout and interrupt handling policy.

In the main program, every `Future` is resolved via `get()` before `shutdown()`, so the example tasks have already completed and the output is deterministic.

For long-running applications, also consider monitoring, bounded queues, rejection policies, cancellation, timeouts, and how `Throwable` instances are logged. Those requirements belong to **application-level concurrency design**, and do not alter the `Runnable.run()` or `Callable.call()` signatures.

## 17. Common Misconceptions

1. **“Runnable can never throw exceptions.”** False: it can throw unchecked exceptions; it simply cannot let new checked exceptions escape on its own.
2. **“Callable must throw a checked exception.”** False: `throws Exception` is a permission, not an obligation to always throw.
3. **“Only tasks running on a thread are subject to checked-exception rules.”** False: the compiler checks lambdas/overrides regardless of whether execution is direct or asynchronous.
4. **“Assigning the same lambda to Runnable or Callable has nothing to do with `throws`.”** False: the target type determines the checked `throws` contract.
5. **“`Runnable.run` returns null.”** False: `run()` returns `void`; `Future.get()` on a successful `submit(Runnable)` returns `null`.
6. **“`Callable<Void>` and `Runnable` are the same interface.”** False: their functional methods and checked `throws` clauses differ.
7. **“`Callable<String>` means it only throws `StringException`.”** False: the generic `String` is the **return type**, not an exception type.
8. **“An `IOException` from a callable will be caught directly by `catch (IOException)` around `Future.get()`.”** False: `Future.get()` reports task failure via `ExecutionException`; inspect `getCause()`.
9. **“If `Future` reports `ExecutionException`, then `get()` itself caused the `IOException` in the worker.”** False: the original error occurred in the task, and `Future` surfaces it at the result-waiting boundary.
10. **“Wrapping `IOException` into `UncheckedIOException` erases the cause.”** False if the cause is passed to the constructor.
11. **“Wrapping checked into unchecked is always a good idea.”** False: you must consider caller policy and avoid swallowing errors.
12. **“`Executor.execute` and `submit` are the same for retrieving exceptions.”** False: `execute` does not return a `Future`.
13. **“`new Thread(callable)` is a standard overload accepting `Callable`.”** False: `Thread` accepts `Runnable` in that constructor; you need an adapter or `FutureTask`.
14. **“`InterruptedException` from `get()` is an exception from the `Callable` body.”** Not necessarily; it indicates the waiting thread was interrupted.
15. **“Catching `InterruptedException` and ignoring it is harmless.”** False: it can break task stopping/cancellation policies.
16. **“`Future.get` with a timeout means the task is automatically cancelled when time expires.”** False: timing out on the wait does not stop the task itself.
17. **“`Runnable` does not require shutting down the executor.”** False: executor lifecycle management is independent of the task type.
18. **“Simply catching `Exception` in `Runnable` is enough.”** Broad catches can hide bugs; catch the specific checked exceptions and apply a clear error policy.
19. **“An exception occurring on another thread will automatically be thrown on the thread calling `submit`.”** False: you must observe it via `Future`, a handler, or another appropriate mechanism.
20. **“Changing the target type later does not affect source compatibility.”** It can affect compatibility because the functional method's return type and checked `throws` differ.

## 18. Self-Check Questions

**Q1.** Why can `Runnable r = () -> Files.readString(path);` cause a compile-time error?

*Answer:* `Files.readString` can throw checked `IOException`. When the target type is `Runnable`, `run()` declares no checked exceptions, so the error must be handled inside the lambda or a suitable target type must be used.

**Q2.** If you change the target type to `Callable<String>`, can `Files.readString(path)` compile?

*Answer:* Yes, because the functional method `call() throws Exception` allows `IOException` to escape, provided the return type and other context details are valid.

**Q3.** Does calling `r.run()` create a new thread?

*Answer:* No. It is a normal method call on the calling thread.

**Q4.** What does `Future.get()` return after `submit(Runnable)` completes normally?

*Answer:* `null`, for the `submit(Runnable)` overload that does not specify a custom result.

**Q5.** If a callable throws `IOException` while running in an executor, what does `Future.get()` throw?

*Answer:* `ExecutionException`, where `getCause()` contains the original `IOException`.

**Q6.** If a `Runnable` catches `IOException` and throws `UncheckedIOException`, what cause does `Future.get()` from `submit(Runnable)` provide?

*Answer:* The direct cause of `ExecutionException` is `UncheckedIOException`; the cause of `UncheckedIOException` is the wrapped `IOException`.

**Q7.** Why does `Callable<Void>` still require `return null;` on the normal completion path?

*Answer:* The functional method `call()` has return type `V`; when `V` is `Void`, the lambda must still return a compatible value (typically `null`) if it has a normal completion path.

**Q8.** Does a task completing with a failure cause an earlier `submit` call to throw the original error directly?

*Answer:* No. Submitting a task and retrieving its result are two separate steps; you must observe the failure via `Future` or a handler as defined by the API.

**Q9.** How should `InterruptedException` from `get()` be handled?

*Answer:* Propagate it if the contract allows, or restore the interrupt flag and stop/exit according to policy; do not silently swallow the interruption request.

**Q10.** Does a generic `Callable<V>` have a generic type parameter for the exception type?

*Answer:* No. `V` describes the return type; the checked `throws` signature is `Exception` regardless of `V`.

**Q11.** When an API only accepts `Runnable` but the operation needs to throw `IOException`, what are the options?

*Answer:* Catch and recover appropriately, or wrap it in an unchecked exception with a clear cause; if the API can be changed, `Callable` or a custom throwing functional interface may be more natural.

**Q12.** Does `executor.shutdown()` automatically wait for all tasks to finish before returning?

*Answer:* No, there is no such guarantee; to wait, you need an additional mechanism such as `awaitTermination()` or waiting on `Future`s, along with a timeout/interrupt policy.

## 19. Official Java 17 Documentation

- [Runnable API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runnable.html): `run()` signature, contract for tasks with no return value.
- [Callable API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Callable.html): `V call() throws Exception` signature.
- [ExecutorService API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit` overloads and executor lifecycle management.
- [Future API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get()`, `cancel()`, timeouts, and waiting exceptions.
- [ExecutionException API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html): task exceptions surfaced through `Future`.
- [UncheckedIOException API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/UncheckedIOException.html): unchecked wrapper for `IOException`.
- [Executors API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html): factory utilities and adapters between `Runnable` and `Callable`.
- [JLS Java 17 Section 15.27.3 – Type of a Lambda Expression](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.3): lambda compatibility with function types, including checked exceptions.
- [JLS Java 17 Section 11.2 – Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): rules for checked-exception analysis.

**Final takeaway:** `Runnable.run()` **has no checked `throws`**, yet it can still throw unchecked exceptions; `Callable<V>.call() throws Exception` can **propagate checked exceptions** and return a result of type `V`. Lambdas are bound by the contract of their target functional interface. When run via `ExecutorService.submit`, failures from both task types are observed via **`Future.get() → ExecutionException → getCause()`**. Choose `Runnable` or `Callable` based on **the return value, checked-exception needs, and caller handling policy**, not just the interface name.