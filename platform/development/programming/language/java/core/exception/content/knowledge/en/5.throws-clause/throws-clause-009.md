# Exception Contract of `main` and Limits of Propagating Errors to the Top

## 1. Objective and Problem to Solve

In command-line Java applications, `main` is the familiar starting point. When lower-level methods can throw checked exceptions, developers can keep declaring `throws` along the call chain:

```text
Java launcher
    |
    v
main(String[] args) throws IOException
    |
    v
loadConfig() throws IOException
    |
    v
readFile() throws IOException
```

This allows the code to **compile** and propagate the exception out of `main`, but it raises an important question: **Once an exception exits `main`, who handles it?** The answer is not "the JVM will automatically recover." An uncaught exception can terminate the initial thread, trigger the uncaught exception reporting mechanism, and cause the command-line application to terminate unsuccessfully. How the JVM launcher presents the error and the specific exit code depend on the execution environment.

This lesson helps you:

- Understand the syntax and effect of `throws` on the `main` method.
- Distinguish between the **compile-time checked exception contract** and the **error-handling policy at the application boundary**.
- Know what happens when a checked or unchecked exception exits `main`.
- Choose appropriately between `try/catch`, propagating, cleaning up, reporting failure, and terminating the process.
- Avoid assuming that errors on a worker thread or asynchronous task will automatically propagate to `main`.
- Recognize the limits of `throws Exception`, `throws Throwable`, and top-level handling mechanisms.

The examples use Java 17+; sections marked with `javac`/`java` are standalone runnable programs.

## 2. The `main` Signature and the `throws` Clause

For a typical Java SE 17 program, the standard entry point is:

```java
public static void main(String[] args) {
    // Program body.
}
```

This is a **method declaration snippet** to illustrate the signature; when actually running it, it must be placed inside a valid Java class.

You can add `throws` after the parameter list:

```java
public static void main(String[] args)
        throws java.io.IOException {
    // Calls that may propagate IOException outward.
}
```

You can declare **multiple types**:

```java
public static void main(String[] args)
        throws java.io.IOException, java.text.ParseException {
    // May propagate one of this group of checked exceptions.
}
```

And the `public static void main(String... args)` syntax using varargs also corresponds to a `String[]` array parameter at compile time.

Things to remember:

1. `throws` is an **exception type declaration**, not a statement that throws an object.
2. A `throw` statement or a failing operation/call is what actually produces an exception.
3. `main throws IOException` does not mean every run throws `IOException`.
4. `main throws IOException, ParseException` lists **different possibilities**, not a requirement that a single failure throws two objects.
5. The listed types must follow language rules and be separated by commas, not the `|` symbol used in multi-catch.
6. You cannot rely on the `throws` clause to expect the operating system, launcher, or user to automatically provide a recovery strategy.

In Java 17, the standard `main` method has a `void` return type. You cannot change it to `int main(...)` to directly return a status code as in some other languages.

### Why can `main` declare checked exceptions?

Suppose `main` calls a method with a `throws IOException` contract. Java's checked exception rules force the caller to either **catch** or **declare** a compatible exception. `main` is still a regular Java method with respect to exception checking, so choosing `throws IOException` is valid.

What is special is that above `main` there is usually no longer **an application method you wrote** that has a chance to catch the exception. Class startup and invoking the entry point belong to the launcher/runtime mechanism. Therefore, pushing a checked exception up to `main` satisfies the source code's compile-time obligation, but **does not by itself solve how to respond to the user or monitoring system**.

## 3. Runnable Example: `main throws IOException`

Create the file **`MainThrowsDemo.java`**:

```java
import java.io.IOException;

public class MainThrowsDemo {
    private static String loadConfig(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("demo read failed");
        }
        return "ready";
    }

    public static void main(String[] args) throws IOException {
        boolean fail = args.length > 0 && args[0].equals("fail");
        System.out.println(loadConfig(fail));
        System.out.println("main completed");
    }
}
```

Compile and run the success path:

```bash
javac MainThrowsDemo.java
java MainThrowsDemo
```

Exact `stdout` output:

```text
ready
main completed
```

On this path, `loadConfig(false)` returns the string `ready`; **no exception occurs at all**, even though both `loadConfig` and `main` declare `throws IOException`.

Try the failure path:

```bash
java MainThrowsDemo fail
```

The execution flow then is:

1. `loadConfig(true)` executes `throw new IOException("demo read failed")`.
2. `loadConfig` terminates abruptly; the exception propagates up to the call in `main`.
3. `main` has no matching `catch`, so it fails to print the `main completed` line.
4. The exception exits `main` and becomes an uncaught application exception on the initial thread.

On a typical Java launcher, you will see type information `java.io.IOException`, the message `demo read failed`, and a stack trace on `stderr`. The file location, line numbers, additional text, and exit code should not be assumed fixed in documentation or unit tests intended to run across multiple environments.

**Do not confuse:** `throws IOException` on `main` does not mean the JVM retries `loadConfig`, allocates extra resources, creates a fallback automatically, or turns the exception into a business message. It only allows this checked exception path to exit the method according to Java rules.

## 4. Declaring Multiple Types on `main`

When an application reads input and parses its format, it can distinguish between two checked exception types. For example, **`MainMultipleThrowsDemo.java`**:

```java
import java.io.IOException;
import java.text.ParseException;

public class MainMultipleThrowsDemo {
    private static int parse(String input)
            throws IOException, ParseException {
        if (input == null) {
            throw new IOException("input unavailable");
        }

        try {
            return Integer.parseInt(input);
        } catch (NumberFormatException failure) {
            ParseException parsed =
                    new ParseException("not an integer", 0);
            parsed.initCause(failure);
            throw parsed;
        }
    }

    public static void main(String[] args)
            throws IOException, ParseException {
        System.out.println("value=" + parse("42"));
    }
}
```

```bash
javac MainMultipleThrowsDemo.java
java MainMultipleThrowsDemo
```

`stdout`:

```text
value=42
```

`main` is valid when declaring multiple types `throws IOException, ParseException`. If the input is invalid and the exception actually propagates up, the corresponding call path terminates abruptly. Keeping `NumberFormatException` as the `cause` inside `ParseException` preserves the root error when the application or monitoring system reads the stack trace.

### Are `throws Exception` and `throws Throwable` valid?

Syntactically, you can write:

```java
public static void main(String[] args) throws Exception {
    // ...
}
```

Or even `throws Throwable`. However, these are **broad** declarations:

- `throws Exception` covers many checked exceptions under the `Exception` branch and still does not cover `Error` in the inheritance hierarchy.
- `throws Throwable` covers both `Exception` and `Error` at the type level, but **does not make the JVM state recoverable** if a serious error occurs.
- In small exercises or experimental tools, `main throws Exception` is a concise way to focus on the API being learned.
- In command-line applications that need clear error messages, meaningful exit codes, resource cleanup, and observability, merely adding `throws Exception` is usually not enough.

Specific declarations such as `IOException` and `ParseException` are useful for documentation and maintenance; meanwhile, **what the application decides to do when an error occurs** should be expressed at the appropriate boundary.

## 5. When an Uncaught Exception Exits `main`

For an exception that actually exits the `main` call and is not caught by the application, handling follows the thread's uncaught exception mechanism. In terms of typical behavior:

```text
main calls task
      |
      v
task throws Throwable
      |
      v
no matching catch in call chain
      |
      v
exits main
      |
      v
thread uncaught exception mechanism
      |
      v
main thread terminates
```

This needs to be understood accurately:

- An error exiting `main` **is not automatically converted into a return value**, because `main` returns `void`.
- On a typical Java launcher environment, if no custom handler is set, a stack trace can be observed on `stderr`. The content/format of the message is not a contract for application code to depend on absolutely.
- If other non-daemon threads are still active, the JVM may **continue running** after the `main` thread terminates. "The `main` thread has terminated" and "the JVM process has terminated" are two different statements.
- If the JVM/process terminates, the operating system sees a process completion status; the convention of `0` for success and a non-`0` value for failure is commonly used in CLIs, but do not promise a **specific error code** across all launchers/JVMs when an uncaught exception occurs.
- `throws` does not automatically send an HTTP response, roll back a transaction, cancel running tasks, or format an error message the way the user expects.

In library code, do not rely on "the exception has reached `main`" to design behavior. Developers may call the same library from unit tests, GUI applications, services, worker threads, schedulers, or other entry points.

### `finally` and Closing Resources

When the stack unwinds under normal exception mechanics, the corresponding `finally` blocks are executed. `try-with-resources` also closes resources according to language rules. However, this **does not guarantee** cleanup completes if the process/VM is forcibly terminated, encounters a fatal crash, or has `Runtime.halt(...)` called.

Therefore, place cleanup at the proper resource scope and do not treat `main throws ...` as a resource management mechanism.

## 6. Catching Errors at the `main` Boundary When a Clear Policy Is Needed

When a command-line application needs to translate technical errors into understandable messages, `main` can serve as the final error-handling place for the **startup thread**:

```java
try {
    initialize();
    execute();
} catch (IOException failure) {
    System.err.println("Cannot start: " + failure.getMessage());
}
```

This is an **illustrative snippet**, requiring `initialize()` and `execute()` to be declared in a real application. This pattern handles I/O errors per the contract, but says nothing about the termination policy and exit code; the application must decide that.

### Runnable Example: Catching an Error and Performing Cleanup

Create the file **`MainCatchDemo.java`**:

```java
import java.io.IOException;

public class MainCatchDemo {
    private static void initialize() throws IOException {
        throw new IOException("config missing");
    }

    public static void main(String[] args) {
        try {
            initialize();
            System.out.println("initialized");
        } catch (IOException failure) {
            System.out.println("startup failed: "
                    + failure.getMessage());
        } finally {
            System.out.println("startup cleanup");
        }

        System.out.println("main reached end");
    }
}
```

```bash
javac MainCatchDemo.java
java MainCatchDemo
```

`stdout` output:

```text
startup failed: config missing
startup cleanup
main reached end
```

Explanation:

1. `initialize()` throws `IOException` and skips printing `initialized`.
2. `main`'s handler turns the failure into intentional output.
3. `finally` runs to perform the corresponding cleanup action; in the example, printing a line.
4. After `try/catch/finally`, the program continues running and prints `main reached end`.

The last point is especially important: **catching and printing a line is not necessarily the right failure policy**. If required configuration fails to load, a real application may need to stop startup, report a failure status, and avoid continuing as if it were ready.

### Do Not Swallow Errors and Report Success

The following example easily misleads systems calling the application:

```java
try {
    startRequiredService();
} catch (Exception failure) {
    System.err.println(failure.getMessage());
}
System.out.println("ready"); // Potentially wrong: the service has not started.
```

This is a **design-flawed snippet for illustration**, assuming `startRequiredService()` exists. If the service cannot be started, you should not print `ready`, return a success result, or continue with steps that depend on the failed initialization.

A helper method can catch an exception **to add context and rethrow**, but it should preserve `cause`:

```java
try {
    loadSettings();
} catch (IOException failure) {
    throw new IllegalStateException("Startup configuration failed",
            failure);
}
```

This is an illustrative snippet inside a method, requiring `loadSettings()` to declare a checked exception. Wrapping the error into `IllegalStateException` expresses the new context while still preserving the original error for tracing. Do not wrap errors across multiple layers just to rename them without adding useful information.

## 7. Returning Success/Failure Results and CLI Exit Codes

`public static void main(String[] args)` returns `void`, so a command-line application often separates its logic into a method that returns a status code:

```java
static int run(String[] args) {
    // 0 = success; non-zero = failure per application convention.
    return 0;
}
```

This is an **illustrative snippet**, not yet a standalone executable program. A useful design is to have `run` return a status or throw an exception per contract, while `main` is where the application decides how to terminate.

Example **`CliExitPolicyDemo.java`**, without actually calling `System.exit` to learn how errors are mapped:

```java
import java.io.IOException;

public class CliExitPolicyDemo {
    private static void execute(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("input unavailable");
        }
    }

    private static int run(String[] args) {
        boolean fail = args.length > 0 && args[0].equals("fail");
        try {
            execute(fail);
            return 0;
        } catch (IOException failure) {
            System.out.println("error: " + failure.getMessage());
            return 2;
        }
    }

    public static void main(String[] args) {
        int status = run(args);
        System.out.println("status=" + status);
    }
}
```

```bash
javac CliExitPolicyDemo.java
java CliExitPolicyDemo
java CliExitPolicyDemo fail
```

The two independent runs produce `stdout` respectively:

```text
status=0
```

```text
error: input unavailable
status=2
```

Here, the code `2` is only a **printed logical status value**, not the actual exit code of the Java process. Because `main` finishes normally, you cannot conclude that the operating system received exit code `2`.

In a real CLI application that needs to report status to the operating system, the entry point author can use `System.exit(status)` according to a specific policy. However:

- `System.exit` instructs the JVM to begin the shutdown sequence; it affects **the entire process** and all threads, not just a single call.
- `System.exit` is not an operation that should be called arbitrarily inside libraries, business methods, or unit tests.
- Calling `System.exit` inside a `try` block is not a reliable way to force `finally` on the same thread to complete like a normal exit path.
- Do not take a **fixed exit code** from an uncaught exception example to create a rule for all JVMs. Define and test exit codes at the CLI boundary you control.
- If the application is managed by a framework, IDE, test runner, or server, follow that environment's lifecycle mechanism; do not call `System.exit` by default.

## 8. `main throws InterruptedException` and Thread Interruption

`main` can also declare:

```java
public static void main(String[] args)
        throws InterruptedException {
    Thread.sleep(100);
}
```

This is a valid method snippet in a Java class. `Thread.sleep` declares `InterruptedException`; `throws InterruptedException` allows the interruption notice to exit `main` without writing a `catch`.

However, in real applications, an interrupt request may be a signal to cancel work or shut down the application. If you catch `InterruptedException` without fully handling the cancellation, you usually need to restore the interrupt flag with `Thread.currentThread().interrupt()`, then finish the work according to contract.

Example snippet:

```java
try {
    Thread.sleep(100);
} catch (InterruptedException failure) {
    Thread.currentThread().interrupt();
    return;
}
```

This is a snippet for a **`void`-returning method** (such as `main`). Not every handler must restore the flag: if you deliberately propagate the `InterruptedException` itself outward using `throws`, that already preserves the signal via the exception type. Policy also depends on the framework and task cancellation structure.

## 9. Important Limit: Exceptions on Other Threads Do Not Automatically Propagate to `main`

A common misconception: "`main throws Exception` will receive every exception in the program."

This is false. Exceptions propagate **along the stack of the executing thread**. When a worker thread with its own stack throws an uncaught exception, that exception does not automatically move over to the `main` thread's stack.

Create the file **`WorkerFailureDemo.java`**:

```java
public class WorkerFailureDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Thread worker = new Thread(
                () -> { throw new IllegalStateException("child failed"); },
                "worker"
        );

        worker.setUncaughtExceptionHandler((thread, failure) ->
                System.out.println("worker error: "
                        + failure.getMessage()));

        worker.start();
        worker.join();
        System.out.println("main completed");
    }
}
```

```bash
javac WorkerFailureDemo.java
java WorkerFailureDemo
```

`stdout`:

```text
worker error: child failed
main completed
```

`Thread.join()` only waits for the worker to finish; by itself it **does not rethrow the worker's `IllegalStateException` to `main`**. The example sets an `UncaughtExceptionHandler` on the worker to control error reporting; thanks to `join()`, the order of the two printed lines is deterministic.

If there is no local handler, the thread's uncaught exception handling mechanism is applied, typically printing a stack trace. This does not turn `main throws ...` into a "global handler."

### Does `setDefaultUncaughtExceptionHandler` replace `try/catch`?

No. The default handler is called in the situation where an exception is about to terminate a thread without being caught. It is suitable for logging the final error, but cannot return to the throw point to continue the body of the failed method. If the handler itself needs to allocate memory, write to a file, or send a notification, those operations may also fail when the environment is experiencing resource exhaustion.

In production, keep the handler's body minimal and avoid treating it as a guaranteed recovery mechanism.

## 10. Another Limit: Tasks via `ExecutorService` and `Future`

Unlike creating a `Thread` directly, a task submitted via `ExecutorService.submit(...)` is typically wrapped so that the exception is stored in the completion state of the `Future`. The caller can observe the error when calling `Future.get()`; the task's failure appears as an **`ExecutionException`** with the actual cause in `getCause()`.

Create the file **`FutureFailureDemo.java`**:

```java
import java.io.IOException;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureFailureDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Callable<String> task = () -> {
                throw new IOException("worker IO failed");
            };

            Future<String> future = pool.submit(task);
            try {
                System.out.println(future.get());
            } catch (ExecutionException failure) {
                System.out.println("task cause: "
                        + failure.getCause().getClass().getSimpleName());
            }
        } finally {
            pool.shutdown();
        }

        System.out.println("main completed");
    }
}
```

```bash
javac FutureFailureDemo.java
java FutureFailureDemo
```

Output:

```text
task cause: IOException
main completed
```

Explanation:

- `Callable<String>` allows a task to throw a checked exception; here it is `IOException`.
- `submit` returns a `Future<String>`. An error thrown by the task does not automatically become an `IOException` at the `submit` line on the `main` thread.
- `future.get()` reports `ExecutionException` when the task finishes with a failure. `getCause()` points to the original `IOException`.
- `main` declares `throws InterruptedException` because waiting may be interrupted; `ExecutionException` is caught and handled separately.
- `shutdown()` stops accepting new tasks; it is not an immediate forced stop of running tasks. In the example, `future.get()` already waited for the specific task to complete, so the output is deterministic.

To push errors to the application boundary, you must **actively collect and handle `Future` results** or use an appropriate task coordination mechanism. With `CompletableFuture`, the error-reporting mechanism differs in wrappers and APIs (such as `CompletionException` or `ExecutionException` depending on how you wait), but the principle remains: **exceptions do not automatically jump across thread boundaries**.

## 11. Errors Beyond What `main throws` Can Handle

### 11.1. Errors Before Entering the `main` Body

Some errors can occur during class loading, linking, or required class initialization before the JVM executes the first lines of `main`. For example, a static initialization error may manifest as `ExceptionInInitializerError`. Because the `main` body has not even started yet, a `try/catch` placed **inside the `main` body** cannot enclose and catch all errors from the entire startup phase outside of it.

Do not promise that `main throws Throwable` will capture every JVM or launcher startup error.

### 11.2. Serious Errors Under the `Error` Branch

`OutOfMemoryError` or `StackOverflowError` are `Error`s, not `Exception`s. `catch (Exception e)` does not catch these objects; `throws Exception` is not a mechanism for managing them either.

Even if some `Error`s can be caught at the type level, continuing to run after a serious error can be dangerous due to lack of resources or corrupted state. Do not artificially trigger out-of-memory or stack-overflow errors to test an entry point in a real application.

### 11.3. Process Loss and Forced Shutdown

Operating system signals, native errors, power loss, `Runtime.halt(...)`, or forced termination events can prevent the program from executing the full exception-handling path, `finally`, and shutdown hooks. `throws` does not provide a guarantee that "a final handler will always run."

### 11.4. Errors Already Absorbed by a Framework or Task Runner

In an application with its own scheduler, event loop, message consumer, or worker management system, errors may be caught, stored, retried, or routed to callbacks by the framework. You cannot deduce that every error reaches `main` just because `main` is the program's starting point.

Describing and testing an error policy requires examining the **actual execution boundaries**: thread, task, `Future`, callback, service container, or request handler.

## 12. Choosing Which Layer Handles Errors

Not every error should be handled in `main`; nor should everything be thrown to the top.

| Incident Type | Layer That Usually Has Enough Context | Handling Direction |
| --- | --- | --- |
| Invalid CLI input data | Argument-receiving boundary | Report usage/invalid value; intentional application status code |
| Required configuration file cannot be opened | Application startup | Report error source, stop startup, avoid reporting "ready" |
| One data record is invalid but skippable | Record-processing layer | Log and continue if the contract allows |
| Temporary system error that can be safely retried | I/O layer aware of idempotency and retry limits | Retry with a limit or propagate error to the orchestration boundary |
| Programming bug `NullPointerException` | Where the invalid state/reference is created | Fix the root cause; do not use a broad `catch` to hide bugs |
| Error in an asynchronous worker | Task/worker result boundary | Observe `Future`/callback/handler, decide whether to cancel or report failure |
| `OutOfMemoryError`/serious runtime error | Operations and process management | Collect evidence if feasible, isolate, and fix the root cause |

A useful way to organize a CLI is:

```text
main                -> receive args, error-reporting/exit-code policy
  |
  +-- application    -> orchestration, business rules
         |
         +-- IO/API   -> declare checked exceptions per contract
```

Lower layers throw meaningful exception types. Upper layers handle them where **the right action can be decided**. `main` should focus on process-boundary policy; do not put business logic and excessive duplicate `catch` blocks inside it.

### When can you leave `main throws Exception`?

- Learning examples, quick test programs, and small internal tools where a direct stack trace is sufficient.
- When there is no need for custom error formatting, dedicated cleanup, standardized exit codes, or long-lived service state.
- When the launcher's default failure behavior is acceptable and has been verified in the runtime environment.

### When should you have an explicit handler in `main`?

- A CLI called from shell scripts/CI that needs stable error categorization.
- A long-running application that needs to decide whether startup succeeded.
- An application with resources that need to be closed according to a clear lifecycle.
- A system that needs contextual logs without printing sensitive stack traces to end users.
- An application coordinating multiple workers that must mark a job as failed if a required task fails.

In all cases, a top-level handler can only manage **exceptions that actually reach it** and must consider the process state before deciding to continue.

## 13. Common Misconceptions

**"`throws Exception` on `main` means all errors are handled."** False. It only declares checked exception types at the signature level; it creates no handler, recovery, or structured error output.

**"`throws IOException` forces the JVM to print `IOException` if an error occurs."** Inaccurate. An inner handler, a wrapper, or a different runtime can change how errors are reported. `throws` does not control output formatting.

**"Because `main` is the entry point, every worker exception will automatically reach it."** False. Each thread has its own call stack; `Future` or an error-exchange mechanism must be handled explicitly.

**"`Thread.join()` rethrows the error that the worker threw."** False. `join()` waits for completion; it is not a channel for transferring worker exceptions. It can throw `InterruptedException` if the waiting thread is interrupted.

**"`System.out.println(status)` makes the operating system receive that exact exit code."** False. Printing a string and terminating a process are two different things.

**"A `catch (Exception)` in `main` covers `Error` and errors before `main` runs."** False. `Error` is in a different branch, and errors occurring before the `main` body begins cannot be enclosed by a `catch` inside the body.

**"With `finally`, cleanup always runs even if the process is killed."** False. The guarantee in Java semantics is conditional on the VM still being able to execute that exit path.

**"If an error is caught in `main`, the process is automatically marked as failed."** False. Catching an error and continuing to normal termination can be treated as success by the runtime environment. An exit code policy must be programmed explicitly when needed.

**"The broader the declaration, the safer it is."** False. `throws Throwable` usually obscures the API's meaning and does not improve recoverability.

## 14. Self-Check Questions

1. **Is `public static void main(String[] args) throws IOException` valid in Java 17?** Yes.
2. **Does `throws IOException` in `main` guarantee the program always throws an error?** No, it describes a possibility of occurring.
3. **If a call throws a checked exception that is not caught in `main`, what does the compiler require?** `main` must declare a compatible type in `throws` or catch it.
4. **When an uncaught checked exception exits `main`, does the JVM automatically retry?** There is no automatic retry guarantee or rule from `throws`.
5. **A worker throws `IllegalStateException`; can `main throws Exception` catch that error?** No, because errors do not automatically propagate across threads.
6. **What type does `Future.get()` typically report a task failure with?** `ExecutionException` with the cause in `getCause()`.
7. **Is `return 2;` valid directly inside a standard `public static void main`?** No, because `main` returns `void`.
8. **What problem can catching an error in `main` and then printing `ready` cause?** The application reports a success status even though initialization actually failed.
9. **If class initialization fails before entering the `main` body, can a handler placed inside `main` catch it?** It cannot catch an error that occurs before the handler exists on the execution path.
10. **Does `main throws Throwable` make the JVM always run `finally` on power loss?** No.
11. **When should you let an exception exit `main`?** When the runtime environment's default error-reporting mechanism is acceptable and no other handling/lifecycle policy is needed.
12. **When should you handle errors at the `main` boundary?** When you need messaging, cleanup, status codes, or a stop/continue decision with clear application semantics.

## 15. References

- [Java Language Specification 17 — §8.4.6 Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): meaning of the `throws` clause.
- [Java Language Specification 17 — §11.2 Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): checked exception rules.
- [Java Language Specification 17 — §11.3 Run-Time Handling of an Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.3): exception handling and propagation.
- [Java SE 17 API — Thread.UncaughtExceptionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.UncaughtExceptionHandler.html): handling uncaught exceptions at the thread boundary.
- [Java SE 17 API — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html) and [ExecutionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html): receiving asynchronous task failures.
- [Java SE 17 API — System.exit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#exit(int)): requesting JVM termination with a status.
- [Java SE 17 API — Thread.join](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#join()): waiting for a thread to finish.

**Key takeaway:** `throws` on `main` is a language-level exception contract, allowing checked exceptions to propagate out to the program boundary. To respond properly when a failure occurs, an application must clearly define **handlers, cleanup, thread/task boundaries, and a termination policy**; those things are not created simply by adding `throws Exception`.
