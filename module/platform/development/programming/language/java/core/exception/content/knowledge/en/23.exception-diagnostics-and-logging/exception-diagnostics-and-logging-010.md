# Using the Debugger with Exception Breakpoints for Caught or Uncaught Exceptions

## 1. Why Are Exception Breakpoints More Useful Than Just Reading Logs?

In a Java application, an error can occur in a low-level method, be **caught** at an intermediate layer, and then be converted into a fallback result or another exception. If the debugger only pauses when the program terminates abnormally, you may miss errors that were caught early. Conversely, if you only read the message in a catch block, you may not know the exact variable state and call chain at the moment the exception was first raised.

An **exception breakpoint** gives the debugger an opportunity to pause when the JVM notifies it that a matching exception is **thrown** at runtime. After pausing, you can inspect frames, variable values, threads, the stack, and the conditions that led to the error. Depending on the debugger, a breakpoint can be configured for **caught exceptions**, **uncaught exceptions** (no matching handler), or both.

Key distinctions:

- **Line breakpoint:** pauses when execution reaches a specific source line or corresponding bytecode location, regardless of whether an error occurs.
- **Exception breakpoint:** pauses when an exception throw event occurs for the selected type and satisfies the caught/uncaught condition supported by the debugger.
- **Stopping in a catch block:** pauses when the error-handling logic starts executing; this is not necessarily where the exception was originally created.
- **Stopping when the process dies from an exception:** only observes a subset of unhandled error cases; insufficient for analyzing exceptions that were caught, wrapped, or converted into fallbacks.

**Learning goal:** use exception breakpoints to find *the exact throw site*, distinguish *caught errors* from *uncaught errors*, read data at the moment the error occurs, and then follow the exception path to understand the business impact. A debugger is a diagnostic tool; it does not fix bugs by itself or replace testing.

## 2. What Do “Caught” and “Uncaught” Mean?

A **caught exception** generally refers to an exception throw event that has a matching handler in the Java execution path. For example:

~~~java
// Illustrative code; parse(...) is defined in the same class/context.
try {
    int value = Integer.parseInt("abc");
} catch (NumberFormatException failure) {
    System.out.println("Input is invalid");
}
~~~

**NumberFormatException** is thrown by the string-to-number conversion; the catch block handles it. Under normal execution, the program can continue and will not print a stack trace to stderr. However, if a breakpoint is enabled for **caught NumberFormatException**, the debugger can pause **right at the throw event** — before the catch code modifies any state.

An **uncaught exception** generally refers to an exception event that has no matching handler in the current JVM execution path, which may eventually reach the thread's uncaught exception handler. For example:

~~~java
// Illustrative code inside main or a calling method.
int port = Integer.parseInt("abc");
// No matching catch in the call path.
~~~

In a simple console application, this error typically causes the **main** thread to terminate and the JVM to print a stack trace to stderr. However, whether the entire process terminates depends on other non-daemon threads, uncaught exception handlers, and the runtime environment.

**Understand the limits of caught/uncaught labels:** Debuggers and the JVM debug mechanism classify events based on whether a handler can be found on the stack at the throw site, not based on business-level predictions such as “will someone log this error later?”. A framework, executor library, proxy, or compiler-generated code may catch an exception and report it back through a different result. Depending on the IDE/debugger, the displayed labels and event classification may differ at such boundaries.

In particular, an exception that is **caught and rethrown** can generate an additional throw event. An exception that is **wrapped into a new exception** creates at least two related error objects: the original and the wrapper. The debugger may pause multiple times within the same incident chain, and that does not necessarily mean there are multiple independent bugs.

## 3. When Does an Exception Breakpoint Pause?

Consider a call chain:

~~~text
Main.main()
  -> OrderService.create()
     -> Validator.parse()
        -> Integer.parseInt("bad")
           [throws NumberFormatException]
     -> catch(NumberFormatException)
        -> log / return error result / throw wrapper
~~~

If you place a line breakpoint inside the catch block, you only start observing after the JVM has transferred control into the catch. An exception breakpoint for **NumberFormatException** can pause where **Integer.parseInt** actually throws the error, with a stack containing the frames leading back to the application's **Validator.parse** method. You can inspect the actual input `"bad"`, object state, branching conditions, and the frames before the catch alters any data.

You should not assume the IDE's displayed location is identical across all JDK versions. An exception may be thrown in library code, native code, or a proxy class; the IDE may automatically redirect to an available source frame or skip library frames according to **Just My Code / step filters**. Therefore, distinguish **the location the debugger brings to screen** from **the actual throw event location** in the call stack.

### An Exception Breakpoint Is Not Equivalent to “Break on a throw Statement”

An exception can be created/implicitly thrown by the JVM or a library without an explicit **throw** statement in your application code:

- **Integer.parseInt** throws NumberFormatException when the input is invalid.
- Accessing a null reference can cause NullPointerException.
- Accessing an array with an invalid index can cause ArrayIndexOutOfBoundsException.
- An invalid cast can cause ClassCastException.
- Calling **Future.get()** can throw ExecutionException or CancellationException.

Setting the appropriate exception breakpoint lets you observe these errors even when the application code does not contain a corresponding **throw new** statement.

## 4. Prerequisites for Debugging Java 17+

An easily reproducible learning workflow:

1. Install JDK 17 or newer and configure the IDE to use the same JDK for the project.
2. Compile with appropriate source line metadata. Standard **javac** generates line number information; builds with debug metadata disabled may only show **Unknown Source**.
3. Run in **Debug** mode rather than **Run**, ensuring the debugger is attached to the correct JVM process.
4. Open the **Breakpoints** or **Exception Breakpoints** configuration in your IDE.
5. Add the exception type you want to observe, such as **java.lang.NumberFormatException**.
6. Choose to break on **caught**, **uncaught**, or both depending on your goal.
7. Use a small, repeatable failure case to confirm the debugger actually pauses.
8. When paused, inspect **Threads**, **Frames/Call Stack**, **Variables**, and **Evaluate Expression** if your tool supports it.

Menu names and layouts in IntelliJ IDEA, Eclipse, and VS Code Java extensions may vary by version. Look for options corresponding to **exception breakpoint**, **caught/uncaught**, **break on thrown exceptions**, and **exception type/class filters**. Do not assume every IDE uses the same checkbox names or supports the same level of filtering.

**Note on observability permissions:** Code running under a debugger may contain tokens, passwords, or sensitive data in memory and local variables. Only debug environments and data you are authorized to access; consider the consequences of **Evaluate Expression**, because invoking a method with side effects can alter the paused program.

## 5. Standalone Java 17+ Example: Five Exception Paths

The following program intentionally creates five scenarios to test breakpoints:

1. **caught:** NumberFormatException is caught in the same thread.
2. **wrapped:** NumberFormatException is caught and converted into an IllegalArgumentException with a cause.
3. **suppressed:** the parse error is primary; IOException from **close()** is attached as suppressed.
4. **async:** NumberFormatException occurs inside a CompletableFuture task; on **join()**, the caller receives CompletionException.
5. **uncaught:** NumberFormatException escapes **main** without a matching catch.

Save the file **ExceptionBreakpointLab.java**:

~~~java
import java.io.IOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class ExceptionBreakpointLab {
    static final class FaultyResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static int parsePort(String text) {
        return Integer.parseInt(text);
    }

    static void caughtCase() {
        try {
            parsePort("not-a-number");
        } catch (NumberFormatException problem) {
            System.out.println("caught: " + problem.getClass().getSimpleName());
        }
    }

    static void wrappedCase() {
        try {
            parsePort("bad-port");
        } catch (NumberFormatException original) {
            throw new IllegalArgumentException("invalid port", original);
        }
    }

    static void suppressedCase() throws IOException {
        try (FaultyResource resource = new FaultyResource()) {
            parsePort("bad");
        } catch (NumberFormatException original) {
            System.out.println("suppressed primary: "
                    + original.getClass().getSimpleName());
            System.out.println("suppressed close: "
                    + original.getSuppressed()[0].getClass().getSimpleName());
        }
    }

    static void asyncCase() {
        CompletableFuture<Integer> stage =
                CompletableFuture.supplyAsync(() -> parsePort("bad-async"));
        try {
            stage.join();
        } catch (CompletionException wrapper) {
            System.out.println("async wrapper: "
                    + wrapper.getClass().getSimpleName());
            System.out.println("async cause: "
                    + wrapper.getCause().getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws IOException {
        String mode = args.length == 0 ? "caught" : args[0];
        switch (mode) {
            case "caught" -> caughtCase();
            case "wrapped" -> {
                try {
                    wrappedCase();
                } catch (IllegalArgumentException wrapper) {
                    System.out.println("wrapped outer: "
                            + wrapper.getClass().getSimpleName());
                    System.out.println("wrapped cause: "
                            + wrapper.getCause().getClass().getSimpleName());
                }
            }
            case "suppressed" -> suppressedCase();
            case "async" -> asyncCase();
            case "uncaught" -> {
                System.out.println("about to throw uncaught");
                System.out.flush();
                parsePort("bad-uncaught");
            }
            default -> System.out.println("unknown mode");
        }
    }
}
~~~

Compile with JDK 17 or newer:

~~~bash
javac --release 17 ExceptionBreakpointLab.java
~~~

Run each mode separately:

~~~bash
java ExceptionBreakpointLab caught
java ExceptionBreakpointLab wrapped
java ExceptionBreakpointLab suppressed
java ExceptionBreakpointLab async
java ExceptionBreakpointLab uncaught
~~~

Verified **exact stdout** output for the four modes that exit normally:

**caught**

~~~text
caught: NumberFormatException
~~~

**wrapped**

~~~text
wrapped outer: IllegalArgumentException
wrapped cause: NumberFormatException
~~~

**suppressed**

~~~text
suppressed primary: NumberFormatException
suppressed close: IOException
~~~

**async**

~~~text
async wrapper: CompletionException
async cause: NumberFormatException
~~~

For **uncaught** mode, the program prints one line to stdout before throwing:

~~~text
about to throw uncaught
~~~

Then the JVM normally prints the **stack trace of NumberFormatException to stderr** and the Java process exits with a non-zero exit code. The stderr stack trace contains file names/line numbers, internal JDK frames, and the call path **parsePort → main**; exact line numbers depend on source layout and build. Do not treat a sample stack trace with fixed line numbers as the example's stdout.

**Why does suppressedCase declare throws IOException?** **FaultyResource.close()** has a `throws IOException` signature. The compiler must account for the possibility that the try body completes normally and then `close()` throws IOException as the primary exception. In the demonstrated execution path, `parsePort` throws NumberFormatException first; the close failure becomes suppressed on NumberFormatException and is read in the corresponding catch block.

**Why does asyncCase catch CompletionException?** **join()** normally reports exceptional completion as a CompletionException. The cause in this example is the NumberFormatException created by the supplier. These are two points/objects to inspect when debugging: the original error on the thread running the supplier and the wrapper observed at the consumer.

## 6. Practicing Breakpoints for Caught Exceptions

Start with the command:

~~~bash
java ExceptionBreakpointLab caught
~~~

To run under the debugger from an IDE, set **program arguments = caught** and choose **Debug**.

Create an exception breakpoint for **java.lang.NumberFormatException** and enable the **caught** option if your debugger supports it. When you run:

1. The JVM starts executing **caughtCase()**.
2. **parsePort("not-a-number")** calls **Integer.parseInt**.
3. The JDK creates and throws NumberFormatException.
4. The breakpoint can pause at the exception event **before** the catch in `caughtCase` executes.
5. Open the call stack to locate **ExceptionBreakpointLab.parsePort** and **caughtCase**.
6. Select the **parsePort** frame to inspect the variable **text = "not-a-number"**.
7. Continue/resume; the catch block will print **caught: NumberFormatException**.

If the breakpoint only has **uncaught** enabled, this scenario typically will not pause the debugger on NumberFormatException under the uncaught criterion, because a matching catch handles it. Some debuggers have different option definitions or filtering mechanisms; check the actual configuration and Java debugger you are using before concluding a breakpoint is broken.

**Key takeaway:** A caught exception can be normal control flow (for example, attempting to parse and returning an input error) or a sign of a hidden bug. The fact that the debugger pauses on a caught exception does not by itself prove the process failed. You need to understand what the catch block does afterward.

### If Paused Inside a Library Frame

When the breakpoint pauses inside a **java.lang.Integer** method, open the **Call Stack** and select the application frame **parsePort**. There you can inspect the input, data passed from the caller, and the decision to call parse. You do not necessarily need to **Step Into** deep into JDK library code, especially when the library code is well-tested and the real issue lies in the argument supplied by the application.

## 7. Practicing Breakpoints for Uncaught Exceptions

Run the mode:

~~~bash
java ExceptionBreakpointLab uncaught
~~~

Enable the **NumberFormatException** breakpoint with the **uncaught** criterion. In this mode, **parsePort("bad-uncaught")** is called from `main` and there is no matching NumberFormatException or superclass catch in this application call path. Along this small program's execution path, the error escapes `main`, so a debugger that supports uncaught exception breakpoints has an opportunity to pause when the exception occurs.

When paused:

1. Note the **current thread**: here it is `main`.
2. Verify the **exception type** and the message containing the unparseable input value.
3. Locate **parsePort** in the Call Stack and select the application frame.
4. Inspect the `text` variable and the line calling `parseInt`.
5. Inspect the **main** frame to see where the caller obtained the string.
6. Resume to observe the uncaught exception handler mechanism and the stack trace on stderr.

**Uncaught does not mean “nothing anywhere in the system ever caught it.”** An error can go uncaught in the current thread while a thread uncaught handler, runtime, framework, or process supervisor still collects/records it through another mechanism. Do not infer from a breakpoint not firing that no error occurred; debugger configuration, attaching to the wrong process, class filters, framework handlers, or runtime optimizations can affect what events you observe.

### If the Application Continues Running After an Uncaught Exception

In a multithreaded program, a worker with an uncaught exception may terminate while other threads keep running. Even an abnormal termination of the `main` thread does not necessarily shut down a process that still has non-daemon threads. Distinguish a **thread-level uncaught exception** from **process termination** and errors that a framework converts into a job status.

## 8. Why Can a Wrapped Error Pause Multiple Times?

Run **wrapped** mode and test two exception breakpoints: **NumberFormatException** and **IllegalArgumentException**.

In **wrappedCase()**:

~~~java
// Snippet from the full program.
try {
    parsePort("bad-port");
} catch (NumberFormatException original) {
    throw new IllegalArgumentException("invalid port", original);
}
~~~

Logical sequence:

1. **Integer.parseInt** throws NumberFormatException.
2. **wrappedCase** catches NumberFormatException.
3. The catch creates a new **IllegalArgumentException** with message `invalid port` and `original` as its cause.
4. The **throw new ...** statement throws the wrapper.
5. **main** catches the wrapper and prints the outer/cause types.

Because NumberFormatException **extends IllegalArgumentException**, a breakpoint set on **IllegalArgumentException** may match both **NumberFormatException** and the wrapper, depending on whether the debugger applies an **include subclasses** filter or matches only the exact class. This is a common reason for seeing more pauses than expected.

Do not conclude there were three separate incidents just because the debugger paused multiple times. Check:

- **Exception object identity** (if the debugger can display and compare it).
- **Actual exception type** at each pause.
- Whether the wrapper's **cause** is the original exception just caught.
- **Thread** and **stack frames** at each event.
- Whether a catch block **rethrew the same object** versus **created a new wrapper object**.

In the example, the outer exception is caught in `main`, so if breaking on **caught** is enabled, the debugger can pause at the wrapper event even though the program ultimately prints the result and exits normally.

## 9. Debugging try-with-resources and Suppressed Exceptions

Run **suppressed** mode. Set exception breakpoints for:

- **NumberFormatException** — the primary error from **parsePort("bad")**.
- **IOException** — the error from **FaultyResource.close()**.

Sequence:

1. The try body throws NumberFormatException.
2. The JVM begins resource cleanup via the try-with-resources mechanism.
3. **close()** throws IOException.
4. The mechanism automatically preserves NumberFormatException as **primary** and attaches IOException to **primary.getSuppressed()**.
5. The NumberFormatException catch reads the suppressed exception and prints two output lines.

If the debugger pauses on the IOException from `close`, **that does not mean IOException caused the parse error**. It is a secondary error occurring during resource cleanup. The investigator must read both the primary and suppressed exceptions, and ask whether the cleanup failure left the resource or system state untrustworthy.

**A debugger trap:** When paused right at the **throw new IOException(...)** statement inside `close`, the step that attaches IOException to NumberFormatException's suppressed list **may not have completed yet**. To verify the final suppressed array, continue to the catch block or a breakpoint after the cleanup point, then inspect **original.getSuppressed()**. The object state at the throw site and after cleanup completes are two different moments in time.

If you use a manual **finally** block with a **close()** that can throw, the cleanup error can even mask the primary exception. Try-with-resources is Java's standard way to preserve secondary errors while keeping the primary error intact in this case.

## 10. Debugging Exceptions Inside CompletableFuture

Run **async** mode and set an exception breakpoint for NumberFormatException. The supplier:

~~~java
// Snippet from the full program.
CompletableFuture<Integer> stage =
        CompletableFuture.supplyAsync(() -> parsePort("bad-async"));
~~~

is executed by CompletableFuture's default executor in this example. **NumberFormatException** is thrown on the thread executing the supplier, not at the **stage.join()** line on `main`. CompletableFuture captures the error to complete the stage exceptionally; when `main` calls `join`, it receives **CompletionException** with NumberFormatException as its cause.

To debug effectively:

1. Run with a debugger that supports debugging threads other than `main`.
2. Enable breaking on **NumberFormatException** (including caught if needed).
3. When paused, check **Threads** to identify the thread executing the supplier.
4. Inspect the application frame **parsePort** and the parameter **text = "bad-async"**.
5. Resume, and you can observe **CompletionException** at **join()** if a breakpoint is set for that type.
6. Inspect **getCause()** on CompletionException to connect the error received by the consumer with the error produced by the worker.
7. Do not use only the **main** frame at `join` to conclude the bug is inside `join`; the actual failure site may be in the supplier lambda.

**Note:** Errors in CompletableFuture are typically **caught** by the framework and converted into an exceptional completion. Therefore, an exception you think of as “the task crashed” may be classified by the debugger as **caught** at the moment it is thrown. Enabling only **uncaught** may miss the root error. Select both caught and uncaught while investigating, then narrow down after finding the location.

Some debuggers support **async stack traces** or display links between stages; availability and completeness depend on the environment. A standard `Throwable` stack trace cannot guarantee reconstructing an entire request journey across threads, executors, and services. Use a task ID, request ID, or correlation ID when you need to link events beyond a single thread's call stack.

## 11. Caught/Uncaught and Checked/Unchecked Are Two Different Classifications

A very common misconception is assuming that:

- **Checked exception** means the error will be caught.
- **Unchecked exception** means the error will not be caught.

Both statements are **false**.

**Checked/unchecked** is a **compile-time checking** rule:

- **IOException** is checked: a method calling code that can throw it must catch it or declare `throws` per Java rules.
- **NumberFormatException** and **IllegalArgumentException** are unchecked: the compiler does not force declaring or catching them.

Meanwhile, **caught/uncaught** reflects **how the exception is handled at runtime**. A RuntimeException can certainly be caught. A checked exception can be declared with `throws` across multiple layers and ultimately not be caught by a matching handler on the executing thread.

For example, **main(String[] args) throws IOException** in the main program allows `close()` to throw the checked IOException outward if the execution path has no matching catch. This does not turn IOException into an unchecked exception; the compiler accepts it because `main`'s signature declares that error type.

Choose exception breakpoints based on **the path you need to observe**, not on whether the exception requires writing **throws** in source code.

## 12. Adding Breakpoints for a Specific Exception vs. General Throwable

An overly broad breakpoint configuration can cause the debugger to pause constantly on thousands of exceptions that frameworks intentionally use as control signals. In a large application, many libraries attempt parsing, catch errors and fall back, probe the classpath, access nonexistent resources as expected, or use exceptions to implement internal mechanisms.

There are three strategies:

| Strategy | When to use | Risk |
| --- | --- | --- |
| **A specific type** such as NumberFormatException | You already know the primary error from a stack trace/log | May miss wrappers or other error types |
| **A superclass group** such as IOException or RuntimeException | Narrowing down a pattern of related errors | May match many subclasses and pause frequently |
| **Throwable / All exceptions** | Short investigation when the type is unknown or looking for swallowed errors | Very high event volume, slow, and hard to focus |

**Practical recommendation:** Start from the exception type known from logs or observed behavior. Enable caught when you suspect an error is being caught/swallowed; enable uncaught when a process or thread terminates abnormally. Use filters by package/class/thread/method when the IDE supports them. Once you identify the type and location, narrow the breakpoint scope to reduce noise.

Understand inheritance when setting superclass breakpoints: NumberFormatException extends IllegalArgumentException, IllegalArgumentException extends RuntimeException, RuntimeException extends Exception. Do not assume **subclass inclusion** is enabled or disabled identically across all debuggers; check the setting.

## 13. Class, Package, Thread, and Conditional Filters

Some IDEs/debuggers allow you to:

- Pause only when the exception originates in a matching class or package.
- Exclude JDK or framework libraries using class filters.
- Observe only a specific thread, if the debugger supports it.
- Suspend all threads or only the thread containing the event.
- Use conditional expressions if supported.
- Select caught only, uncaught only, or both.

Filters reduce noise, but they can also hide the event you need to see. For example, the error is actually thrown inside **Integer.parseInt** in package **java.lang**; if you filter to pause only on exceptions thrown inside your application package, the debugger may not pause even though an application frame **parsePort** is on the stack.

Do not confuse a **throwing class filter** with finding an **application frame**. An exception thrown by the JDK can be directly tied to invalid input from the application.

When setting conditions, also be careful:

- Breakpoint condition evaluation can run many times.
- Some expressions reference variables only available in a specific frame.
- Evaluating methods can mutate application state.
- Complex conditions can slow down the debugger and make reproduction harder.
- If a breakpoint does not pause, try removing filters before concluding the exception does not occur.

A clean strategy is **specific exception type → caught/uncaught as needed → remove overly strict filters → check thread/frame → add filters gradually**.

## 14. Using the Call Stack to Read State Right Before Catch

When an exception breakpoint triggers, follow this priority workflow:

1. Check the **thrown Throwable type**, message, and relevant fields if displayed by the debugger.
2. Check which **thread** is paused.
3. Identify the **top frame** in the debugger: it may be a Java library method.
4. Switch to the **first relevant application frame**.
5. Read local variables, parameters, `this` fields, and related objects.
6. Walk down caller frames to find the input source and data flow.
7. Compare against **contract validity conditions**, rather than guessing from the message alone.
8. Step/Resume to see where the exception is caught or whether it escapes.
9. When reaching the catch, inspect the logic deciding retry, fallback, wrap, rollback, or logging.
10. If the final result does not match expectations, add a line breakpoint after the catch to verify the mutated state.

**Step Into, Step Over, and Step Out** control execution step-by-step by frame; they do not automatically take you to the original frame of a cause if you are paused on a wrapper. Use both the Call Stack and the **Throwable.getCause()** object.

At a debugger breakpoint, a **Throwable's stack trace** and the **live call stack** are not necessarily identical: a Throwable typically retains the trace from when it was created/filled in, while the debugger shows the thread's stack at the moment of the pause. Especially with catch/rethrow, async, and new wrappers, the two stacks can differ without contradiction.

## 15. When an Exception Is Caught and Swallowed

An ignored error can let the application continue running while producing incorrect data:

~~~java
// Illustrative anti-pattern, not a standalone program.
try {
    updateDatabase();
} catch (Exception ignored) {
    // No logging, no error returned, and execution continues.
}
markOrderCompleted();
~~~

If `updateDatabase` fails, **markOrderCompleted()** can still be called. How to investigate:

1. Suspect an exception type based on business logic or dependency logs.
2. Enable a **caught** exception breakpoint for the appropriate type.
3. Re-run the failure scenario.
4. When the breakpoint triggers, inspect the call stack and error message.
5. Continue to the catch or place a line breakpoint inside the catch.
6. Check whether the catch swallows the error, replaces the exception, returns a fallback, or continues erroneously.
7. Fix the error contract and state-update logic, not just by adding a log statement if the data remains wrong.

In the snippet above, naming a variable **ignored** does not make the exception harmless. The API author must decide which specific errors are acceptable to ignore in that context. If an operation is optional and the error belongs to an acceptable set, handling should include a clear message, metrics, or a well-reasoned fallback.

A **caught exception breakpoint** is especially useful here because “seeing no exception in the terminal” does not mean no exception was thrown.

## 16. When Exceptions Are Valid Control Flow

Not every caught exception is a bug. Some operations are intentional:

- Attempting to parse input and reporting a validation error.
- Looking up an optional file and falling back to a controlled default.
- Verifying a token/credentials and rejecting an invalid request.
- Receiving CancellationException when a Future is canceled on request.
- Receiving InterruptedException and propagating the stop signal to the task owner.
- Retrying under a bounded policy with backoff when a dependency temporarily fails.

If you enable breakpoints for every **caught exception**, the debugger may pause on all these designed scenarios, causing “first-chance exception noise.” Do not change code solely because an exception breakpoint paused. Compare the behavior against the contract, frequency, context, and business outcome.

Also do not call every caught exception “handled successfully”: a catch may rethrow, wrap, retry and then fail, or swallow improperly. Trace from the **throw point** to the **boundary that receives the final result**.

## 17. Debugger and Exceptions Across Reflection, Proxies, and Callbacks

In real-world Java applications, errors can pass through reflection or proxies:

- **Method.invoke()** can wrap an exception thrown by the invoked method in **InvocationTargetException**.
- A proxy/framework can translate a low-level exception into its own exception type.
- A callback invoked by a framework may be caught by an event loop or scheduler.
- **Future.get()** can propagate task failures via **ExecutionException**.
- **CompletableFuture.join()** typically propagates exceptional completion via **CompletionException**.

In these cases, an “original” exception may be seen by the debugger as caught inside the framework, even though the business request ultimately fails. You need to observe the **throw point**, **wrapper creation**, and **error-returning boundary**.

Suggested way to set breakpoints:

1. Start from the wrapper in the logs, such as CompletionException.
2. Inspect **getCause()** to find the root exception.
3. Set an exception breakpoint for the cause type, enabling caught if the framework may catch it.
4. Use class/thread filters to narrow down after locating the throw site.
5. Add a line breakpoint where the framework or service translates errors if you need to analyze the mapping process.

Do not conclude **the framework swallowed the exception** just because it caught it to produce an exceptionally completed Future. That mechanism may be the exact error-reporting contract of the asynchronous API.

## 18. Investigating Interruption and Cancellation Exceptions

An exception breakpoint for **InterruptedException** can pause at a blocking API that is being interrupted. However, keep in mind:

- **InterruptedException** represents that **that thread's** waiting operation received an interrupt signal.
- **CancellationException** represents that a Future/result was canceled, which does not necessarily mean the worker has stopped.
- **TimeoutException** from **Future.get(timeout)** represents that the wait timed out; it does not automatically cancel the task.
- **ExecutionException** from **Future.get()** can contain a cause that is an error from the **worker**.

These exceptions can be caught very frequently in executors, thread pools, or applications with timeouts. Enabling a caught exception breakpoint for **InterruptedException** across the entire JVM can cause the debugger to pause on completely valid shutdown paths.

Check:

1. Which thread was interrupted and who requested it?
2. Does the catch **throw e** upward if the contract allows?
3. If it cannot propagate the checked exception, does the catch restore **Thread.currentThread().interrupt()** and exit appropriately?
4. Had the work already mutated state before stopping?
5. Can a canceled Future continue producing side effects?
6. Do timeouts cause the code to retry infinitely or create duplicate requests?

The debugger helps you inspect state at the point of failure, but it does not guarantee rollback. When pausing threads, observing races and timeouts can also change because **time spent paused under a debugger** is not normal execution time.

## 19. Breakpoints Change the Timing of Multithreaded Applications

Setting an exception breakpoint in a concurrent system can alter the behavior you are investigating:

- If the debugger suspends **all threads**, a worker holding a lock causes other threads to pause or block as well.
- If it suspends only the **event thread**, other workers can keep modifying objects and mutating state before you finish inspecting.
- Pausing can cause external service deadlines to expire, because external systems are not paused by your debugger.
- A rare race condition during normal runs may disappear or happen more often when breakpoints are active.
- Method evaluation with side effects can cause deadlocks if it calls a method requiring a lock held by a suspended thread.

Therefore:

1. Determine whether the debugger suspends the **current thread** or the **entire process**.
2. Record timestamps, thread names, and correlation IDs.
3. Do not rely on a single debugger run as the sole evidence of a race condition.
4. For timing bugs, combine structured logging, metrics, thread dumps, and unit/concurrency tests.
5. If a bug disappears while debugging, do not rush to rule out a race or visibility issue.

In production environments, attaching a debugger and suspending threads can affect SLAs, request timeouts, and system integrity. Only do so with proper authorization, operational procedures, and an appropriate environment; prefer reproducing in staging/test.

## 20. Recording Findings After Debugging

After finding the origin, document concisely:

- **Original exception type:** e.g., NumberFormatException.
- **Throw site:** e.g., Integer.parseInt called by ExceptionBreakpointLab.parsePort.
- **Input/state:** unparseable string, `text` variable in the frame.
- **Catch or propagation path:** caught, wrapped, suppressed, async, or uncaught.
- **Cause/suppressed:** which wrapper class received the error, which secondary cleanup error occurred.
- **Impact:** whether the request was rejected, the task completed exceptionally, or data was mutated.
- **Fix:** which validation, API contract, state, or cleanup mechanism needs to be fixed.
- **Reproduction/test:** required mode, input, and assertions.

Do not just take a debugger screenshot and omit information that can be verified with tests. A bug fix should be proven with tests checking the right state and exception type, including the success path.

### Avoiding Duplicate Logs

You do not need to add **printStackTrace()** at every layer. If a catch only wraps/rethrows, a single error can appear in multiple log entries. Usually, preserve **Throwable cause/suppressed** across layers and log once at the responsible handling boundary. The goal of an exception breakpoint is **to find the source**, not to add noise to production logs.

## 21. Testing to Confirm Root Cause, Not Just Catching the Right Exception

A good test for caught/wrapped/suppressed chains should assert:

| Scenario | What to verify |
| --- | --- |
| Caught | Entered the catch of the expected type with no unintended side effects |
| Uncaught | Exception escapes the test scope as expected; for a child process, you can check exit code and stderr |
| Wrapped | Wrapper preserves the exact original cause instance, not just a matching message |
| Suppressed | Primary remains intact; close failure is in `getSuppressed()` in the right order |
| Async | Consumer sees the appropriate wrapper; cause points to the supplier error |
| Retry/fallback | Only allowed error types are handled; dangerous errors are not turned into success |
| Multi-thread | Thread and post-error state conform to the cancellation/synchronization contract |

An **exception breakpoint is not a unit test**. It only lets you pause at one event in a single run. You still need tests to confirm correct logic across multiple inputs, timings, and environments. With the code in Section 5, you can use the standalone run modes to verify exception types and causes; specifically, `uncaught` mode should be run as a child process if you want to test the exit code, avoiding crashing the test process itself.

If a unit test uses a framework with `assertThrows`, assert the exception type as well as **getCause()**, **getSuppressed()**, and before/after state, rather than stopping at verifying that some exception was thrown.

## 22. Common Configuration and Usage Mistakes

**Enabling only uncaught and failing to find caught errors.** Enable a caught exception breakpoint for the right type, especially when you suspect the error is caught by a framework or converted into a fallback.

**Leaving Throwable + caught enabled across the entire JVM for too long.** This can trigger thousands of pauses on validly handled errors. Narrow by type, class, package, thread, or condition deliberately.

**Assuming a debugger pause guarantees a bug.** A caught exception can be a completely valid invalid-input handling path. Always check the business contract.

**Mistaking a top JDK frame for a JDK bug.** Read the application frame that called the library method and inspect the input passed in.

**Forgetting subclass matching.** A breakpoint on IllegalArgumentException may match NumberFormatException if configured to include subclasses, causing more pauses than expected.

**Missing the wrapper.** Pausing only on CompletionException at `join` and fixing the consumer while ignoring NumberFormatException in the supplier. Always inspect the cause.

**Overlooking cleanup errors.** An IOException in `close` may be suppressed rather than primary. Inspect the Throwable tree before drawing conclusions.

**Assuming uncaught = the whole process must die.** A worker thread can terminate while the process keeps running; a framework may catch and convert the error into a job status.

**Not checking that the debugger is attached to the right JVM.** You may be attached to the wrong build, server instance, test fork, or a process on a different port.

**Reading variables in the wrong frame.** While paused in `Integer.parseInt`, local variables of `parsePort` may not be visible in the current frame; switch to the application frame.

**Evaluating expressions with side effects.** Method evaluation can mutate state, perform I/O, acquire locks, or throw new exceptions, skewing the investigation.

**Relying on fixed line numbers from a stack trace to match a different source version.** Verify the running code and build before making fixes.

**Leaving broad breakpoints active in environments that need stability.** Remove/disable overly broad exception breakpoints after debugging, keeping only minimal configuration for the next reproduction.

## 23. Step-by-Step Checklist

Before ending a debugging session, check:

1. **Right JVM?** Is the debugger attached to the right process, classpath, and code version?
2. **Right exception type?** Is the breakpoint set for the actual type, not just the wrapper in logs?
3. **Caught/uncaught?** Did you choose the mode matching the suspected handling path?
4. **Inheritance?** Does the class breakpoint match subclasses and cause extra pauses?
5. **Filters?** Are filters excluding the throw site in libraries or the thread you need to inspect?
6. **Throw point?** Have you inspected the frame where the Throwable was thrown and the relevant application frame?
7. **Variables?** Have you recorded inputs, object state, and conditions leading to the error?
8. **Catch path?** Have you traced the exception to its catch, wrapper, retry, fallback, or uncaught handler?
9. **Cause/suppressed?** Have you distinguished the primary error, wrapped error, and cleanup error?
10. **Concurrency?** Have you identified the suspend policy and how pausing affects threads, races, and timeouts?
11. **Outcome?** Have you verified state impact and created a reproducing test?
12. **Cleanup?** Have you disabled overly broad breakpoints, protected sensitive data, and kept necessary logs/tests?

**Conclusion:** Exception breakpoints for **caught exceptions** help uncover errors that were caught or translated by frameworks without showing up directly in the console. Exception breakpoints for **uncaught exceptions** help pinpoint error paths with no matching handler on the running thread. Both are most useful when combined with the **Call Stack**, local variables, **cause**, **suppressed** exceptions, and an understanding of threads/async execution. Use the debugger to find *where an exception is thrown* and *where it is handled*, then confirm the root cause and fix with tests.
