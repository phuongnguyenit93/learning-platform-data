# `printStackTrace` and the Complete Representation of an Exception in Java

When Java throws an exception, looking only at a message like `"read failed"` is often insufficient for diagnosis. A **`Throwable`** object also carries the error type, *stack trace* (the call chain), *cause* (the underlying cause), and *suppressed exceptions* (secondary errors retained, often arising when closing resources). The **`printStackTrace()`** method is used to print diagnostic information from that object.

The most important point:

> `getMessage()` only provides the message; `toString()` typically adds the class name; `printStackTrace()` displays the error information along with the call frames, cause chain, and suppressed exceptions in stack trace format. Do not mistake these three representations as equivalent.

This lesson explains how to read an exception completely, how to retrieve or capture a stack trace, its limitations, and how to use it safely in Java 17+ programs.

## 1. What does a `Throwable` object store?

The root of the Java exception hierarchy is `java.lang.Throwable`. Its two important direct branches are `Exception` and `Error`; `RuntimeException` is a subclass of `Exception`. `Throwable` provides common APIs to inspect error information.

| Component | Common API | Information obtained |
| --- | --- | --- |
| Exception type | `ex.getClass()`, `ex.getClass().getName()` | The actual class name of the thrown object |
| Message | `ex.getMessage()` | Error description string, which may be `null` |
| Localized message | `ex.getLocalizedMessage()` | By default, usually the same as `getMessage()`; may differ if overridden by a subclass |
| Error summary | `ex.toString()` | Usually the class name, followed by the message if present |
| Cause | `ex.getCause()` | Another `Throwable` or `null` |
| Suppressed error list | `ex.getSuppressed()` | A `Throwable[]` array, which may be empty |
| Call frames | `ex.getStackTrace()` | An array of `StackTraceElement` describing the recorded stack locations |
| Full display | `ex.printStackTrace()` | Prints a human-readable format to `System.err` |
| Display to custom stream | `ex.printStackTrace(PrintStream/PrintWriter)` | Prints the stack trace to the provided destination |

The concepts in the table do not mean that every object always has a message, cause, suppressed exceptions, or stack frames. For instance, `getMessage()` and `getCause()` can return `null`, and `getSuppressed()` can be an empty array.

### The same error at different representation levels

Suppose:

```java
IllegalArgumentException ex =
        new IllegalArgumentException("quantity must be positive");
```

This is an illustrative statement that needs to be inside a method/class. Ways to observe it:

```java
System.out.println(ex.getMessage());
System.out.println(ex.toString());
```

**Stdout:**

```text
quantity must be positive
java.lang.IllegalArgumentException: quantity must be positive
```

If you write `ex.printStackTrace();`, Java typically prints additional `at ...` lines to **stderr**, not stdout. The exact locations and line numbers depend on the source file, call path, and runtime; therefore, the entire printout should not be treated as a fixed string that can be hard-coded in documentation.

## 2. What does `printStackTrace()` actually do?

`Throwable` has three common ways to be called:

```java
ex.printStackTrace();
ex.printStackTrace(System.err);
ex.printStackTrace(new java.io.PrintWriter(writer));
```

These are **illustrative statements**, where `ex` is a `Throwable` and `writer` is a valid `java.io.Writer`.

- **`printStackTrace()`:** prints the object's stack trace to **`System.err`** — the standard error stream.
- **`printStackTrace(PrintStream stream)`:** prints to the passed `PrintStream`, such as `System.out` or `System.err`.
- **`printStackTrace(PrintWriter writer)`:** prints to a caller-managed `PrintWriter`, convenient when writing to a buffer or writer.

All three **return `void`**. `printStackTrace()` does not return a `String`, does not recover the program from the error, and **does not rethrow the exception** being printed.

### Distinguishing stdout from stderr

`System.out` is for standard output; `System.err` is for error output. A sequence of statements:

```java
System.out.println("before");
ex.printStackTrace();
System.out.println("after");
```

can produce two lines on stdout and a stack trace on stderr. When a console or execution environment merges the two streams, the display order may depend on the stream buffering and collection mechanism. Therefore:

- Do not use the interleaving between stdout and stderr as definitive proof of execution order.
- In examples requiring **exact stdout**, print stable summary data instead of guessing line numbers or paths in a stack trace.
- `printStackTrace()` is suitable for quick investigation, but production applications should usually use a logger capable of accepting a `Throwable` and managing the output destination, log level, and context.

**A printed stack trace** and **an uncaught exception** are two different concepts. You can call `printStackTrace()` inside a `catch` block and continue the program; conversely, an exception may go uncaught and the thread's default handler is what ends up printing the error information.

## 3. Common shape of a stack trace

An example for **structural illustration**, not a fixed line-number transcript:

```text
java.lang.IllegalStateException: cannot complete checkout
    at example.CheckoutService.checkout(CheckoutService.java:<line>)
    at example.Main.main(Main.java:<line>)
    Suppressed: java.lang.IllegalArgumentException: close warning
        at example.Resource.close(Resource.java:<line>)
        ... <frames omitted>
Caused by: java.io.IOException: storage offline
    at example.Storage.read(Storage.java:<line>)
    ... <frames omitted>
```

Key parts:

1. **First line:** `Throwable.toString()` — the exception class name and message if present.
2. **`at package.Class.method(File.java:line)`:** a location in the stack trace. Frames are typically listed from the location closest to the error source down to the caller.
3. **`Suppressed: ...`:** a secondary exception attached to the primary exception, often from a resource-closing operation.
4. **`Caused by: ...`:** a `Throwable` object attached as the cause.
5. **`... N more`:** several trailing frames match the enclosing exception's stack and are abbreviated when printed. This is a **display compression**, not an indication that information was "lost" from the object.

Some stack traces have multiple levels of `Caused by` or multiple `Suppressed` entries, and each suppressed exception can itself carry its own cause or suppressed exceptions. Not every exception has all of the above sections; the program only prints what the object currently carries.

### How to read quickly when there are multiple exception layers

If the first line is `ServiceException` and the last cause is `SocketTimeoutException`, it usually means the service layer **wrapped** a deeper error from the network layer. Read both:

- **Outer exception:** the type of error the current calling layer is handling, along with high-level context.
- **Inner cause:** what failed at the lower layer.
- **Stack locations:** which code created or propagated the error according to the recorded trace.
- **Suppressed:** cleanup/resource issues that occurred in addition to the primary exception.

Do not treat only the last `Caused by` line as the definitive root cause in every case. Layers can translate errors incorrectly, drop causes, or create an unrelated error; always cross-check with context and actual behavior.

## 4. What is `StackTraceElement`?

Each frame is represented by a `java.lang.StackTraceElement`. When reading a `printStackTrace()` output, an `at package.Class.method(File.java:line)` line usually corresponds to the information of one frame.

| API | Question answered |
| --- | --- |
| `getClassName()`, `getMethodName()` | Which class and method were recorded? |
| `getFileName()`, `getLineNumber()` | Are a source file and line number available? |
| `isNativeMethod()` | Does the frame belong to a native method? |
| `getModuleName()`, `getClassLoaderName()` | Is module/class loader metadata available? |

The file name can be `null`, the line number can be negative, and the trace can be empty; do not parse strings like `File.java:123` as stable data. `getStackTrace()` returns **the array of frames**, whereas `printStackTrace()` is the formatted display including cause/suppressed. If you need to explore getters, defensive copying, and module data, the `getStackTrace`/`StackTraceElement` lesson is the main place for that explanation.

## 5. When is a stack trace recorded?

In `Throwable`'s normal behavior, the stack trace is recorded **when the exception object is created/constructed** (via a mechanism like `fillInStackTrace()`), rather than necessarily at every `throw` site.

Example:

```java
static IllegalArgumentException createError() {
    return new IllegalArgumentException("invalid quantity");
}

static void raiseError(IllegalArgumentException ex) {
    throw ex;
}
```

These are two illustrative methods. If an object is created in `createError()` and then thrown in `raiseError()`, throwing **the same object** does not automatically rewrite the stack trace to the `raiseError()` location. This preserves the recorded origin, though it can sometimes lead readers to assume the exception was thrown right where it was created.

**`Throwable.fillInStackTrace()`** can update the stack trace based on the current location, but this operation alters diagnostic evidence. Unless intentional and thoroughly tested, you should **rethrow the same object** to preserve the original information, or **wrap it in a new exception with a cause** if a new layer of context is needed.

With a new exception:

```java
throw new IllegalStateException(
        "checkout processing failed", original);
```

The `original` variable must be an existing `Throwable` in scope. The outer exception has a stack trace recorded where it was created; the original exception keeps its own stack trace and is linked via `getCause()`. `printStackTrace` helps read both.

### Rethrowing is not creating a new exception

Comparison:

- **`throw ex;`:** rethrows the same object. Its runtime type, message, cause, and current stack trace remain those of that object.
- **`throw new SomeException("context", ex);`:** creates a new object with its own stack trace, attaching `ex` as the cause.
- **`throw new SomeException(ex.getMessage());`:** may lose the link to the original object unless preserved by another mechanism.

Do not wrap across many layers just to add the same `"failed"` message; a longer stack trace does not mean better diagnostics.

## 6. How do `getMessage()`, `toString()`, and `printStackTrace()` differ?

Suppose `IOException ex = new IOException("read failed");`:

| Call | Example output or return type | Has stack frames? | Has full cause/suppressed chain? |
| --- | --- | --- | --- |
| `ex.getMessage()` | `"read failed"` | No | No |
| `ex.toString()` | `"java.io.IOException: read failed"` | No | No |
| `ex.getStackTrace()` | `StackTraceElement[]` | Yes, as data | Does not directly contain cause/suppressed relationships |
| `ex.printStackTrace()` | Prints formatted info on `System.err` | Yes | Yes, if the exception carries that data |
| `ex.printStackTrace(writer)` | Writes to `PrintWriter` | Yes | Yes, if the exception carries that data |

`Throwable`'s default **`toString()`** includes the class name and the localized message (`getLocalizedMessage()`) if the message is non-null. A custom exception class may override the relevant methods, so the exact string depends on the error type.

**`getMessage()`** can be `null`, so a statement like:

```java
System.out.println(ex.getMessage().length());
```

can throw a `NullPointerException` inside the handler itself. When constructing diagnostic messages, handle `null` values appropriately.

**`printStackTrace()`** is an action that **writes to an output destination**, not a string-returning API. Calling `String trace = ex.printStackTrace();` is a **compile-time error** because the method returns `void`.

## 7. Complete Java 17+ example: representing an exception with type, cause, suppressed, and trace

The following program creates an outer exception, attaches a root cause and a suppressed exception, and then **captures the stack trace using `StringWriter`**. Instead of printing a raw trace containing unstable line numbers, it prints boolean checks that produce deterministic results on a standard JDK 17.

Save the file as **`ThrowablePortraitDemo.java`**:

```java
import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;

public class ThrowablePortraitDemo {

    static IllegalStateException buildError() {
        IOException cause = new IOException("storage offline");

        IllegalStateException error =
                new IllegalStateException(
                        "cannot complete checkout", cause);

        error.addSuppressed(
                new IllegalArgumentException("close warning"));
        return error;
    }

    public static void main(String[] args) {
        IllegalStateException error = buildError();

        System.out.println(
                "type: " + error.getClass().getSimpleName());
        System.out.println("message: " + error.getMessage());
        System.out.println("toString: " + error);

        System.out.println(
                "cause: "
                + error.getCause().getClass().getSimpleName());
        System.out.println(
                "suppressed count: "
                + error.getSuppressed().length);

        System.out.println(
                "first method: "
                + error.getStackTrace()[0].getMethodName());

        StringWriter buffer = new StringWriter();
        error.printStackTrace(new PrintWriter(buffer));
        String trace = buffer.toString();

        System.out.println(
                "has header: "
                + trace.startsWith(
                        "java.lang.IllegalStateException: "
                        + "cannot complete checkout"));

        System.out.println(
                "has frame: "
                + trace.contains("ThrowablePortraitDemo.buildError"));

        System.out.println(
                "has suppressed: "
                + trace.contains(
                        "Suppressed: java.lang.IllegalArgumentException: "
                        + "close warning"));

        System.out.println(
                "has cause: "
                + trace.contains(
                        "Caused by: java.io.IOException: storage offline"));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ThrowablePortraitDemo.java
java ThrowablePortraitDemo
```

**Exact stdout** (independent of line numbers in the file):

```text
type: IllegalStateException
message: cannot complete checkout
toString: java.lang.IllegalStateException: cannot complete checkout
cause: IOException
suppressed count: 1
first method: buildError
has header: true
has frame: true
has suppressed: true
has cause: true
```

### Part-by-part breakdown

- `getClass().getSimpleName()` identifies the **actual type** of the outer exception: `IllegalStateException`.
- `getMessage()` displays only the outer exception's message.
- `toString()` displays both the fully qualified class name and the message.
- `getCause()` points to `IOException("storage offline")`. This is the cause passed into the constructor by the developer.
- `getSuppressed()` contains an `IllegalArgumentException("close warning")`, added via `addSuppressed`.
- `getStackTrace()[0].getMethodName()` is `buildError`, because the `IllegalStateException` object was created in that method.
- `printStackTrace(new PrintWriter(buffer))` writes text into the buffer. The `contains` checks verify the cause, suppressed error, and call frame in the full representation.

The example **does not throw the exception** out of `main`. You can certainly use `printStackTrace` to inspect a `Throwable` object that was just created or caught; printing does not mean the exception is propagating.

## 8. Complete Java 17+ example: reading each frame of a call chain

Save as **`TraceOriginDemo.java`**:

```java
public class TraceOriginDemo {

    static void origin() {
        throw new IllegalArgumentException("bad quantity");
    }

    static void middle() {
        origin();
    }

    public static void main(String[] args) {
        try {
            middle();
        } catch (IllegalArgumentException ex) {
            StackTraceElement[] frames = ex.getStackTrace();

            System.out.println(
                    "first method: " + frames[0].getMethodName());
            System.out.println(
                    "second method: " + frames[1].getMethodName());
            System.out.println(
                    "third method: " + frames[2].getMethodName());
            System.out.println(
                    "first file: " + frames[0].getFileName());
            System.out.println(
                    "line positive: "
                    + (frames[0].getLineNumber() > 0));
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 TraceOriginDemo.java
java TraceOriginDemo
```

**Stdout with a standard Java compiler including source line info:**

```text
first method: origin
second method: middle
third method: main
first file: TraceOriginDemo.java
line positive: true
```

**Explanation:**

1. `main()` calls `middle()`.
2. `middle()` calls `origin()`.
3. `origin()` creates and throws `IllegalArgumentException`.
4. The handler in `main()` receives the same object and accesses the `StackTraceElement[]` array.
5. The first frame is at `origin`; the subsequent frames are `middle` and then `main`. This is the order of the call chain at the time the stack was recorded.

This example focuses on Java compiled from source files with `javac`. With optimized bytecode, missing debug info, or special runtime conditions, line/frame info may differ. **Do not write application tests that depend on specific line numbers** in a stack trace.

## 9. `Caused by`: cause chain across multiple layers

A low-level API might throw `IOException`, and an upper layer wraps it in `IllegalStateException` to indicate that the application cannot complete the operation. Example:

```java
static void loadRequiredData() {
    try {
        readFromStorage();
    } catch (java.io.IOException cause) {
        throw new IllegalStateException(
                "Required data could not be loaded", cause);
    }
}
```

This is an **illustrative method**, assuming `readFromStorage()` exists and can throw `IOException`.

If the outer error is printed with `printStackTrace()`, the reader might see:

```text
java.lang.IllegalStateException: Required data could not be loaded
    at ... <stack of wrapper>
Caused by: java.io.IOException: <underlying problem>
    at ... <stack of original exception>
```

This is a **structural description**, not fixed stdout. `Throwable.getCause()` returns the direct cause object; you can traverse multiple levels when there are nested wrappers.

### Rethrowing and wrapping errors must be deliberate choices

- If the outer caller can still handle `IOException`, passing that exception up as-is is sometimes better than wrapping it.
- If the service layer needs to present the error at a higher level of abstraction, creating a wrapper with `cause` preserves the original trace.
- If you only write `throw new IllegalStateException("failed");`, the caller may **lose the specific cause** that was caught.
- Do not rely on `getMessage()` content to detect causes by string matching: library authors can change wording and multiple errors can share messages.

You can use a loop to read the cause chain when truly needed:

```java
Throwable current = ex;

while (current.getCause() != null) {
    current = current.getCause();
}

System.out.println(current.getClass().getSimpleName());
```

This is an illustrative snippet where `ex` is a `Throwable` object. In custom classes or untrusted data, applications should guard against unusual cause chains and avoid assuming the "last error" is always the sole actual cause.

## 10. `Suppressed`: recording secondary errors, especially in `try-with-resources`

In `try-with-resources`, Java automatically closes `AutoCloseable` resources when leaving the scope. A scenario can occur where:

1. The `try` body throws exception **E1**.
2. During closing, `close()` throws exception **E2**.
3. Java keeps **E1 as the primary exception** and attaches E2 as a **suppressed exception** of E1, rather than letting E2 mask the error that caused the initial failure.

Illustrative form:

```java
try (AutoCloseable resource = openResource()) {
    performWork(resource);
}
```

This is an illustrative skeleton; `openResource` and `performWork` must be defined, and the checked exception signature of `AutoCloseable.close()` may require `throws Exception` or an appropriate handler.

The outer layer can read:

```java
for (Throwable secondary : ex.getSuppressed()) {
    System.out.println("secondary: " + secondary);
}
```

`getSuppressed()` returns an array, never `null`; it may be empty when no secondary errors are stored.

### Notes on `addSuppressed()`

`Throwable.addSuppressed(Throwable exception)` allows manually attaching a secondary exception when policy requires it. Do not pass `null` or suppress the object itself. Let Java manage standard `try-with-resources` cases and avoid reinventing the mechanism unnecessarily.

**Suppressed is different from cause.** A cleanup exception is not necessarily the cause of a data-reading error; therefore, it is typically *suppressed*, not a `cause`. `printStackTrace` displays both relationships, while `getCause()` does not itself contain the suppressed list.

### A `Throwable` class can disable suppression or stack trace recording

The API has constructors for subclasses that allow configuring suppression and stack trace writability. Therefore, in applications using special custom exceptions, do not assume `getSuppressed()` always reflects every secondary error or that `getStackTrace()` always contains a complete set of frames.

These options are primarily for performance-critical designs or special contracts; for ordinary business errors, retain sufficient diagnostic information.

## 11. Not every stack trace prints every frame verbatim

Common `printStackTrace` output may contain:

```text
... 3 more
```

This indicates that several trailing frames of the cause/suppressed section match the trailing frames already printed in the enclosing exception. They are **abbreviated to avoid repetition**. It does not mean Java stopped tracking the error after three calls.

If programmatic analysis is required, work with the structured APIs:

```java
Throwable cause = ex.getCause();
StackTraceElement[] frames = ex.getStackTrace();
Throwable[] suppressed = ex.getSuppressed();
```

instead of splitting raw strings by `"Caused by:"`, `"Suppressed:"`, or `"at "` lines. Formatting can vary due to the JVM, module info, loggers, and error-collection tools.

Each cause object has its own `getStackTrace()` array. You can inspect each object individually rather than relying on the number of lines displayed by `printStackTrace`.

## 12. Does `printStackTrace()` "catch" or "handle" an exception?

No. Example:

```java
try {
    doWork();
} catch (IllegalStateException ex) {
    ex.printStackTrace();
    System.out.println("handler finished");
}
```

This is an illustrative skeleton. `printStackTrace` **only prints information**. The handler will finish normally unless a rethrow statement or a new exception occurs, and code can continue after the `try-catch` block.

If you want to propagate the exception to the caller:

```java
try {
    doWork();
} catch (IllegalStateException ex) {
    ex.printStackTrace();
    throw ex;
}
```

The `throw ex;` statement is what actually rethrows the object; `printStackTrace` does not do that. While this snippet may be useful in an experiment, real applications generally should not both print stack traces at multiple layers and rethrow, as that causes **duplicate logs**.

### When there is no handler

An exception escaping a thread's entry point may be passed to an `UncaughtExceptionHandler`. Common default implementations report the error information and stack trace to stderr. However:

- A custom handler can change how it is logged or choose not to log.
- The failing thread terminates; the handler does not make it return to the failed statement.
- An error in an `ExecutorService.submit()` task may be stored by the framework in a `Future` and delivered to the caller via `ExecutionException` instead of becoming an uncaught worker exception.

Do not assume every stack trace seen in the console is an "uncaught" exception; it could also be printed by a developer or logger inside a `catch` block.

## 13. How to get a stack trace as a string when truly needed

Because `printStackTrace()` returns `void`, the standard way to obtain a string representation is:

```java
java.io.StringWriter buffer = new java.io.StringWriter();
java.io.PrintWriter writer = new java.io.PrintWriter(buffer);

ex.printStackTrace(writer);
writer.flush();

String traceText = buffer.toString();
```

This is an illustrative snippet where `ex` is a `Throwable`. `writer.flush()` makes the intent explicit when using a buffered writer; `StringWriter` stores the string in memory.

Avoid doing this on every production request just to get a message:

- Stack traces can be very long, consuming memory and storage.
- The text may contain file names, internal classes, SQL, paths, or sensitive data in the message.
- If the logging system supports accepting a `Throwable`, passing the error object directly to the logger is usually better than building strings manually.

Example with Java Util Logging (an **illustrative snippet**, requiring `ex` and an appropriate logger):

```java
java.util.logging.Logger logger =
        java.util.logging.Logger.getLogger("application");

logger.log(
        java.util.logging.Level.SEVERE,
        "Order processing failed",
        ex);
```

Here the logger receives the **`Throwable` object**, allowing the configured handler/formatter to decide how to write the trace, rather than logging only `ex.getMessage()` and losing the cause chain.

## 14. Trace limitations: where the exception was created, not everything that happened

A stack trace is **diagnostic information about the recorded stack**, not a complete historical log.

Some important limitations:

- `getStackTrace()` usually reflects where the object was created or where `fillInStackTrace()` was most recently called, **not every rethrow**.
- One thread's stack trace does not automatically include the stacks of other threads.
- With asynchronous code, callbacks, `CompletableFuture`, or executors, the cause/wrapper chain may matter more than a single stack.
- When code is compiled differently, line numbers and generated class names can change.
- Some frames may lack file/line info, or the stack trace may be truncated/limited by the runtime.
- Not all errors have a cause or suppressed exceptions, even when an investigator wishes they did.
- A full stack trace does not prove that data was rolled back or that resources were successfully released.

Therefore, production investigation requires combining stack traces with **timestamp**, **operation name**, **safe request/correlation ID**, **application version**, and relevant operational metrics.

## 15. Common mistakes when representing exceptions

| Wrong or incomplete practice | Consequence | Better approach |
| --- | --- | --- |
| Logging only `ex.getMessage()` | Loses error location, cause, and suppressed | Pass `Throwable` to the logger when investigation is needed |
| Thinking `System.out.println(ex)` prints the stack trace | Usually only calls `toString()` | Use `printStackTrace` or a logger accepting `Throwable` |
| Thinking `ex.printStackTrace()` returns a `String` | Compile error: return type is `void` | Use `StringWriter` + `PrintWriter` when needed |
| Not distinguishing stdout/stderr | Mixed output, unpredictable ordering | Read/route streams according to their purpose |
| Truncating the trace at the first `Caused by` line | Loses deep cause chains or suppressed errors | Inspect the entire `Throwable`/cause/suppressed |
| Catching an error and creating a new exception without keeping `cause` | Loses connection to the original error | Wrap using a constructor that accepts `cause` when appropriate |
| Assuming every `StackTraceElement` has a positive line number | Fails for native/unknown sources | Check the value and do not depend on line numbers |
| Driving business logic with `trace.contains("Parser.java:42")` | Fragile across code edits/versions | Use exception types, error codes, or structured data |
| Printing the same trace in repository, service, and controller | Duplicate logs, hard to distinguish a single incident | Choose a logging boundary and propagate errors clearly |
| Printing every exception message into API responses | May leak internal secrets | Separate public messages from controlled internal logs |
| Thinking `printStackTrace` recovers the program | It is only an output action | Decide `catch`, retry, return, or rethrow separately |
| Thinking suppressed is a cause | Misunderstands error relationships | Inspect `getCause()` and `getSuppressed()` separately |
| Using `setStackTrace` to hide the error location | Misleading diagnostics, reduced auditability | Keep the original stack, add context via wrappers/logs |

### Why is logging only the message not enough?

Suppose a log records:

```text
failed to read data
```

This line does not tell you where the error occurred, what kind of I/O error it was, who called the operation, or whether there were resource-closing errors.

Conversely, if the logger receives the entire `Throwable`, the log entry can show the stack trace, cause, and suppressed errors. Still, effective investigation requires **safe and accurate context**; a long stack trace without knowing which request it belongs to can still be hard to act on.

## 16. Be careful with sensitive data and log volume

Stack traces can reveal a lot of internal information. The first line can contain a message constructed by the application or provided by a library. If code writes:

```java
throw new IllegalArgumentException(
        "invalid token: " + suppliedToken);
```

then the token risks appearing in `toString()`, `printStackTrace()`, and logging systems that record `Throwable`. This is an **anti-pattern**, with `suppliedToken` as a hypothetical variable.

Replace it with a message that does not expose secrets:

```java
throw new IllegalArgumentException("invalid authentication token");
```

Practical guidelines:

1. Do not concatenate passwords, secrets, API keys, cookies, or user payloads into exception messages.
2. Choose non-sensitive request/correlation IDs for structured logs.
3. Do not return full stack traces to clients over HTTP or public interfaces.
4. Establish an appropriate logging boundary to avoid printing the same error multiple times.
5. Control log levels, access permissions, retention periods, and event volume when errors repeat.
6. Do not swallow exceptions just to reduce logs; handle them deliberately and observe at the appropriate layer.

`printStackTrace` is a diagnostic tool, **not a stable error-response protocol or safe for public exposure by default**.

## 17. Self-check exercises

**Exercise A.** Is `System.out.println(ex)` equivalent to `ex.printStackTrace()`?

**No.** The first usually uses `Throwable.toString()`, printing the class name and message; the second displays stack frames along with cause/suppressed and defaults to stderr.

**Exercise B.** What does `Throwable.printStackTrace()` return?

**`void`.** To get the text in a string, pass a `PrintWriter` backed by a `StringWriter` and then call `buffer.toString()`.

**Exercise C.** Given `new IllegalStateException("outer", cause)`, what does `getCause()` return?

It returns the `cause` object passed to the constructor (if valid), not the cause's message string.

**Exercise D.** In `try-with-resources`, both the `try` body and `close()` throw errors. Where is the closing error usually located?

In **`getSuppressed()`** of the primary exception from the `try` body. Do not assume it can be found via `getCause()`.

**Exercise E.** Does a stack trace printing `... 2 more` mean Java lost two frames?

No. It is a shorthand for trailing frames that duplicate those already printed in the enclosing exception. You can inspect each object's `getStackTrace()` array if structured data is needed.

**Exercise F.** An exception object is created in `createError()` and then `throw`n in `process()`. Is the first element of the stack trace always `process()`?

No. A stack trace is normally recorded when the exception is created/constructed; rethrowing the same object does not automatically rebuild the stack. You need to consider where the object was created and whether `fillInStackTrace` was called.

**Exercise G.** Is it safe to hard-code a test asserting that a stack trace contains `OrderService.java:137`?

Usually no. Line numbers can change when refactoring, compiling, or running in different environments. Test the exception type, cause, structured properties, and handling behavior instead; only check the stack when there is a specific diagnostic requirement.

**Exercise H.** If `ex.getMessage()` is `null`, will `ex.toString()` also be `null`?

Not necessarily. Under the default behavior of `Throwable.toString()`, the string still includes the class name even when the message is null. A custom class may change this representation.

**Exercise I.** Does `printStackTrace` make a `catch` block recover from an exception?

No. It only prints information. The handler must decide whether to continue, return a failure result, rethrow, or wrap the exception according to policy.

**Exercise J.** When production already has a logger that accepts `Throwable`, should you also call `printStackTrace()` at every layer?

Usually no. Doing so easily creates duplicate records and bypasses the logger's routing, log levels, and sensitivity controls. Choose an appropriate logging boundary.

## 18. Checklist for reading and logging an exception responsibly

When encountering a stack trace, go through these steps in order:

1. **Identify the outer exception type:** read the first line or `getClass()`.
2. **Read the message:** understand the failure condition; verify whether sensitive data is present.
3. **Inspect the frames:** identify the involved methods and the location closest to where the stack was recorded.
4. **Inspect the `Caused by` chain:** find the lower-layer cause and relate it to the high-level error.
5. **Inspect `Suppressed`:** look for cleanup/resource-closing errors that might be overlooked.
6. **Understand `... N more`:** it abbreviates duplicate frames, not the entire content of the cause.
7. **Separate stdout and stderr:** do not infer exact ordering from a merged-stream console.
8. **Identify the handling boundary:** was the error caught/logged, or did it actually escape the thread?
9. **Read safe context:** request ID, operation, version, and system state, without relying on a single trace alone.
10. **Distinguish handling from representation:** `printStackTrace` does not decide retry, fallback, rollback, or termination.
11. **Test deliberately:** prefer exception type/cause/suppressed over comparing an entire trace containing line numbers.
12. **Protect secrets:** do not expose stack traces or exception messages carelessly to public places.

**Conclusion:** a Java exception is more than just a message. `Throwable` lets you observe **error type, message, stack frames, cause, and suppressed exceptions**. `printStackTrace()` is a convenient combined representation for investigation that defaults to printing to **`System.err`**, while the `PrintStream`/`PrintWriter` overloads let you choose the output destination. In real applications, preserve the cause chain, manage resource-closing errors properly, and pass the `Throwable` to a logger at a responsible boundary, rather than logging only the message or hard-coding stack trace formats.
