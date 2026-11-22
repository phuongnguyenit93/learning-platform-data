# Reading Stack Traces by Exception Type and Origin in Java

## 1. What Questions Does a Stack Trace Answer?

When a Java application encounters an exception, a message saying "an error occurred" is usually not enough to fix the root cause. A stack trace (call stack trace) tells you **which exception object was reported**, **which methods appeared in the error's trace**, **the corresponding source code locations**, and, if present, **the cause chain** or **suppressed exceptions**.

Within the scope of Java Core diagnostics, reading a stack trace is the process of connecting four types of information:

1. **Exception type**: NullPointerException, IllegalArgumentException, IOException, SQLException, CompletionException, ...
2. **Error message**: the input, invariant condition, or specific operation that failed, if the exception has a message.
3. **Frames**: the class, method, file, line number, and call order recorded in the stack trace.
4. **Error tree**: the outermost exception, **Caused by** causes, and **Suppressed** cleanup errors.

An error may be detected inside a JDK library while being triggered by invalid data or faulty logic in application code. Therefore, you should not read only the first line and conclude "the JDK has a bug." Conversely, you should not just look for a line with your project's package name and ignore the information in library frames.

**Goal:** From a stack trace, identify *the point where evidence of the error appeared*, *the call path leading to that point*, and *the most appropriate root cause to investigate*. This is a way to prioritize fix hypotheses, **not absolute proof that a single line of code is a design flaw**.

## 2. General Structure of a Java Stack Trace

A typical stack trace snippet looks like this:

~~~text
java.lang.IllegalArgumentException: invalid input
    at com.example.app.ProfileService.parse(ProfileService.java:42)
    at com.example.app.ProfileService.load(ProfileService.java:28)
    at com.example.app.Main.main(Main.java:11)
Caused by: java.lang.NumberFormatException: For input string: "abc"
    at java.base/java.lang.NumberFormatException.forInputString(NumberFormatException.java:...)
    at java.base/java.lang.Integer.parseInt(Integer.java:...)
    at com.example.app.ProfileService.parse(ProfileService.java:40)
    ... 2 more
~~~

This is an **illustrative stack trace**, not the exact output of the program in Section 6. Package names, line numbers, module prefixes, and frame counts are abbreviated to clarify the structure; the **...** in the example does not represent a fixed line number.

It can be broken down into parts:

| Visible part | Main meaning |
| --- | --- |
| **java.lang.IllegalArgumentException: invalid input** | The exception type being printed and its message |
| **at com.example...parse(ProfileService.java:42)** | A frame: class/method and source location information |
| Subsequent **at** lines | Higher-level calls on the stack captured when the Throwable recorded the trace |
| **Caused by: ...** | Another Throwable declared as the cause of the Throwable being printed |
| **Suppressed: ...** | A secondary Throwable stored on a Throwable, typically from cleanup |
| **... N more** | Trailing frames identical to the enclosing trace are omitted when printing; this does not mean they are missing from the Throwable object |

A standard stack trace from **Throwable.printStackTrace()** may additionally display nested classes, truncated sections, or logger-specific formatting. Even when formatting and detail levels vary by environment, the approach of reading **exception type → frames → cause → suppressed** remains useful.

## 3. Starting with the Exception Type and Message

The first line usually has the form:

~~~text
package.ExceptionType: message
~~~

Examples:

~~~text
java.lang.NumberFormatException: For input string: "abc"
java.lang.NullPointerException: Cannot invoke ... because ... is null
java.io.FileNotFoundException: config.txt (The system cannot find the file specified)
java.lang.IllegalStateException: order is already closed
~~~

These are **illustrative message formats**; exact wording, details, and level of explanation from the JVM/JDK may differ.

The **exception type** indicates the error-detection mechanism:

- **NumberFormatException**: a string was converted to a numeric value with invalid syntax.
- **NullPointerException**: code attempted to operate on a null reference in a situation where Java does not allow it.
- **IndexOutOfBoundsException**: an invalid position was accessed in an indexed structure.
- **ClassCastException**: an incompatible reference type cast.
- **IllegalArgumentException**: an API rejected an argument because it violated the contract.
- **IllegalStateException**: an operation is not permitted given the object's current state.
- **IOException**: an error at the input/output operation layer.
- **CompletionException** or **ExecutionException**: may be a wrapper for an error located in **cause**.

The **message** adds context, not the identity of the error. A message can be **null**, can be written by a developer, and can vary across JDK versions. You should not build business logic based on exact string matching of JDK messages.

For example, if you get **NumberFormatException: For input string: "abc"**, what needs investigation is not only where Java throws NumberFormatException, but also where the application supplies the string **"abc"**, how data is validated, and which formats are allowed by the rules.

## 4. Reading Each Stack Frame to Trace the Call Path

A frame is usually displayed as:

~~~text
at package.ClassName.methodName(FileName.java:lineNumber)
~~~

Components:

- **package.ClassName**: the class containing the method according to stack information.
- **methodName**: the method on the call stack when the trace was recorded.
- **FileName.java**: the source file name if the corresponding metadata is available.
- **lineNumber**: the source line if the JDK and class file have matching line information.

Typically, the **first frame** of a Throwable reflects the location closest to where the Throwable's trace was captured (usually when it was constructed). Lower frames reflect the callers at that time. You can read **from top to bottom** to see the recorded error path:

~~~text
at app.Parser.parse(Parser.java:18)        <- nearest location in the application where the error was recorded
at app.Repository.load(Repository.java:35) <- method calling Parser.parse
at app.Service.handle(Service.java:64)    <- method calling Repository.load
at app.Main.main(Main.java:10)            <- entry point
~~~

This is an **illustrative chain**. Frame order is critical information: a frame lower down usually calls into the frame above it, not the other way around.

**Caution:** In a stack trace with a wrapper, the top frame of the **wrapper** and the top frame of the **cause** can be two different locations. The wrapper's top frame points to where the code created/recorded the wrapper; it is not necessarily where the original business error occurred. Therefore, always inspect **Caused by** before settling on an investigation point.

In addition, a stack trace shows the execution path that was captured, but does not guarantee that every step of the application is in a single trace. Asynchrony, callbacks, remote calls, and thread boundaries can split one business flow into multiple separate traces.

## 5. The "Origin" Is Not Always the First Line

When Java creates an exception inside a library, the top frames may belong to **java.base**, **java.util**, or a framework. For example, with **Integer.parseInt("abc")**, the topmost frames may be internal methods of NumberFormatException/Integer, while the first application frame is where parseInt was called.

Proper investigation usually involves two separate questions:

1. **Where did this Throwable record the error?** Look at the top frames of the Throwable itself.
2. **What condition did the application introduce that led to that error?** Look at the relevant application frame and the data passed in.

For instance, an **IndexOutOfBoundsException** thrown by **ArrayList.get** does not mean ArrayList itself is broken. The caller may have computed an invalid index. Similarly, a **NullPointerException** in a JDK operation may be triggered by a null input passed in by the application.

A first frame belonging to a project package is also not automatically a bug. It may simply be where **throw new IllegalArgumentException(...)** is used to reject invalid client input by design. You need to cross-check the API contract, request, actual data, prior operations, and logs with the correlation ID.

**Practical rule:** Read the deeper cause first, find the application frame associated with that cause, and then walk back down the call path to locate the data source or business decision that produced the error condition.

## 6. Java 17+ Example: Exception Type, Application Location, Cause, and Suppressed

The following complete example creates a call chain:

**main → service → repository → parseAge → Integer.parseInt**.

The input string cannot be converted to an int. A resource in **try-with-resources** also throws IOException on close, so Java keeps the parse error as the primary exception and attaches the close error as suppressed. **service** intentionally wraps the parse error in an IllegalArgumentException carrying a business message.

The example iterates over **StackTraceElement** directly to print key fields in a stable way, avoiding reliance on internal library line numbers across JDK versions.

Save as **StackTraceReadingDemo.java**:

~~~java
import java.io.IOException;

public class StackTraceReadingDemo {
    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static int parseAge(String value) {
        return Integer.parseInt(value);
    }

    static int repository(String value) {
        return parseAge(value);
    }

    static void service(String value) throws IOException {
        try (FailingResource resource = new FailingResource()) {
            repository(value);
        } catch (NumberFormatException original) {
            throw new IllegalArgumentException("invalid age input", original);
        }
    }

    static StackTraceElement firstApplicationFrame(Throwable error) {
        for (StackTraceElement frame : error.getStackTrace()) {
            if (frame.getClassName().equals(StackTraceReadingDemo.class.getName())) {
                return frame;
            }
        }
        throw new IllegalStateException("No application frame");
    }

    static String applicationChain(Throwable error) {
        StringBuilder result = new StringBuilder();
        for (StackTraceElement frame : error.getStackTrace()) {
            if (frame.getClassName().equals(StackTraceReadingDemo.class.getName())) {
                if (result.length() != 0) {
                    result.append(" -> ");
                }
                result.append(frame.getMethodName());
            }
        }
        return result.toString();
    }

    public static void main(String[] args) throws IOException {
        try {
            service("not-a-number");
        } catch (IllegalArgumentException wrapper) {
            Throwable cause = wrapper.getCause();
            StackTraceElement origin = firstApplicationFrame(cause);
            System.out.println("outer type=" + wrapper.getClass().getSimpleName());
            System.out.println("outer message=" + wrapper.getMessage());
            System.out.println("outer application frame="
                    + firstApplicationFrame(wrapper).getMethodName());
            System.out.println("cause type=" + cause.getClass().getSimpleName());
            System.out.println("cause first application frame=" + origin.getMethodName());
            System.out.println("cause application chain=" + applicationChain(cause));
            System.out.println("cause file=" + origin.getFileName());
            System.out.println("cause line available=" + (origin.getLineNumber() > 0));
            System.out.println("cause suppressed count=" + cause.getSuppressed().length);
            System.out.println("suppressed type="
                    + cause.getSuppressed()[0].getClass().getSimpleName());
            System.out.println("suppressed message=" + cause.getSuppressed()[0].getMessage());
        }
    }
}
~~~

Compile with JDK 17+ and run:

~~~bash
javac --release 17 StackTraceReadingDemo.java
java StackTraceReadingDemo
~~~

Stdout verified by compiling and running:

~~~text
outer type=IllegalArgumentException
outer message=invalid age input
outer application frame=service
cause type=NumberFormatException
cause first application frame=parseAge
cause application chain=parseAge -> repository -> service -> main
cause file=StackTraceReadingDemo.java
cause line available=true
cause suppressed count=1
suppressed type=IOException
suppressed message=close failed
~~~

This program is compiled with the default settings of **javac --release 17**, so source line metadata is available. If a build uses options that strip debug line information, line numbers may be unavailable; **cause line available** could then differ. The example does not print specific line numbers because line numbers depend on source file layout.

### Reading the Output Layer by Layer

- **outer type = IllegalArgumentException:** the application exception exposed outward, created in **service**.
- **outer message = invalid age input:** service provides business context without replacing the lower-level error type.
- **outer application frame = service:** the wrapper's stack trace was recorded when the wrapper was constructed in service.
- **cause type = NumberFormatException:** the actual parse error is still preserved and accessible via **getCause()**.
- **cause first application frame = parseAge:** even though some internal JDK frames sit above it, **parseAge** is the first frame belonging to the application class in the cause.
- **cause application chain = parseAge → repository → service → main:** the methods calling each other at the moment NumberFormatException was created.
- **cause suppressed count = 1:** FailingResource's close threw IOException while the try body had already failed. Try-with-resources attaches it as a suppressed exception **on NumberFormatException**, rather than automatically moving it to the suppressed list of the IllegalArgumentException wrapper.
- **suppressed message = close failed:** provides additional information that cleanup failed; reading only the outer message would miss this important detail.

In the example, **service() throws IOException** because FailingResource.close() declares checked IOException and another execution path could make the close error the primary exception. The parse failure in this run makes NumberFormatException primary and the close error suppressed, so catch(NumberFormatException) handles and wraps it. You should not arbitrarily remove the IOException declaration just because the test run does not throw it directly.

## 7. Reading Caused by to Avoid Fixing the Wrapper by Mistake

When a layer adds context with a new exception:

~~~java
// Illustrative code inside a valid catch block.
catch (java.io.IOException original) {
    throw new IllegalStateException("Cannot initialize configuration", original);
}
~~~

The new Throwable is a **wrapper**, while **original** is stored in **cause**. In logs, the wrapper exception usually appears on the first line and has stack frames pointing to where **throw new** was executed. Under **Caused by** is the lower-level Throwable and its corresponding frames.

Conceptual example:

~~~text
java.lang.IllegalStateException: Cannot initialize configuration
    at app.ConfigurationService.start(ConfigurationService.java:58)
Caused by: java.io.FileNotFoundException: config.properties
    at app.ConfigReader.read(ConfigReader.java:21)
    at app.ConfigurationService.start(ConfigurationService.java:54)
    ... 1 more
~~~

This is a simulated example, not stdout from the code in Section 6.

A sound way to read it:

1. Note **the intent the wrapper expresses**: configuration cannot be initialized.
2. Follow **Caused by** to FileNotFoundException.
3. Find the application frame in the cause: ConfigReader.read.
4. Check the configuration path, working directory, permissions, how the path is resolved, and environment configuration.
5. From **ConfigurationService.start**, determine who requested loading the configuration and how the application should respond.

The deepest cause is not always the full business root cause needed to fix the bug. A deepest **ConnectException** tells you a connection could not be established, but the real problem might be a wrong endpoint, DNS, credentials, or an unready service. A stack trace is evidence of *the error path*, not a substitute for observing external systems.

### getCause() and Nested Layers

**Throwable.getCause()** can return null. Many frameworks wrap errors across multiple layers; you must traverse cautiously:

~~~java
// Illustrative code inside a method receiving a Throwable.
Throwable current = failure;
while (current.getCause() != null) {
    current = current.getCause();
}
// current is the deepest cause along this getCause() chain.
~~~

Do not hardcode **failure.getCause().getCause()** without null checks. Moreover, picking only the final cause can discard contextual information from the wrappers above it. In diagnostic reports, it is better to preserve the entire **error tree** and then focus on the appropriate layer for the fix.

## 8. Reading Suppressed to Spot Cleanup Errors Without Masking the Root Error

A **suppressed exception** is a secondary Throwable attached to another Throwable via **addSuppressed()**. Try-with-resources uses this mechanism when the try body is already throwing an exception and closing the resource also throws an error.

Log-style example:

~~~text
java.lang.NumberFormatException: For input string: "not-a-number"
    at java.base/java.lang.Integer.parseInt(Integer.java:...)
    at app.StackTraceReadingDemo.parseAge(StackTraceReadingDemo.java:...)
    Suppressed: java.io.IOException: close failed
        at app.StackTraceReadingDemo$FailingResource.close(StackTraceReadingDemo.java:...)
        ... 3 more
~~~

This is an illustrative structure with abbreviated line numbers and frames. **Suppressed** does not mean the close error caused NumberFormatException. The relationship is: after the primary exception occurred, a second error also occurred during cleanup. Reversing that causality can lead to fixing close instead of the parsed data.

In the program from Section 6, the IllegalArgumentException wrapper has **cause = NumberFormatException**; it is NumberFormatException itself that carries the **suppressed IOException**. Consequently, when a log only shows the wrapper exception or a helper only queries **wrapper.getSuppressed()**, the close error may not appear. You need to inspect cause and suppressed at the right node.

Quick distinction:

| Relationship | API | Question to ask |
| --- | --- | --- |
| **Cause** | **getCause()** | Which error led to this exception as wrapped by the code? |
| **Suppressed** | **getSuppressed()** | While handling/closing resources, what secondary errors were retained? |
| **Stack frame** | **getStackTrace()** | At the moment the trace was recorded, which methods were on the call stack? |

If **close()** fails when the try body **did not error**, the close error can be thrown as the primary exception. Do not assume every IOException from close is only a suppressed error.

## 9. Meaning of the ... N more Line

When Throwable.printStackTrace prints an exception with a cause or suppressed exception, it may omit trailing frames that are **identical** between the current trace and the enclosing exception's trace. When you see:

~~~text
Caused by: java.io.IOException: read failed
    at app.Reader.read(Reader.java:17)
    ... 3 more
~~~

It does not mean Java lost three frames because the exception was randomly "truncated." **... 3 more** usually indicates that the last three frames match those of the enclosing trace and do not need to be printed again.

When reading:

1. Look at the cause's own frames right above **... N more**.
2. Match the corresponding frames in the outer trace to reconstruct the shared caller path.
3. Focus on the unique frames with diagnostic value: usually where the deeper exception originated.
4. Do not confuse the number **N** with the number of exceptions, retry count, number of occurrences, or skipped lines of code.

If you call **getStackTrace()** on a Throwable object in code, you get an array of **StackTraceElement** for that Throwable itself; **... N more** is a **compact printing format**, not a special element stored in the array.

## 10. Wrapper, throw e, throw new, and When the Trace Is Captured

A common misconception is that a stack trace necessarily reflects where a Throwable **was most recently thrown**. A **Throwable** usually captures its stack trace when it is instantiated (or when **fillInStackTrace()** is called according to the class design).

Example:

~~~java
// Illustrative code, inside a method with an appropriate declaration.
try {
    riskyOperation();
} catch (IllegalArgumentException original) {
    throw original; // Preserves the same Throwable object.
}
~~~

Normally **throw original** does not create a new error object and does not automatically replace the entire stack trace with the rethrow site. During investigation, this helps preserve where the exception was originally recorded.

Conversely:

~~~java
// Illustrative code.
try {
    riskyOperation();
} catch (IllegalArgumentException original) {
    throw new IllegalStateException("Processing failed", original);
}
~~~

**new IllegalStateException(...)** creates a wrapper with its own stack trace at the creation site; the prior error remains available via **getCause()**. If you look only at the outermost trace, you may see the wrapping line and miss the lower-level failure point.

Code like the following loses the original trace:

~~~java
// Illustrative anti-pattern.
catch (IllegalArgumentException original) {
    throw new IllegalStateException(original.getMessage());
}
~~~

The new exception does not keep original as its cause. Even if the message is the same, the original stack trace and any suppressed exceptions on original are detached from the wrapper; the logging system receives only a wrapper that is hard to trace back to the root cause.

You should also avoid **reusing a single exception instance** for failures at different times: the old instance's trace may not reflect the new invocation. APIs such as **setStackTrace()**, **fillInStackTrace()**, custom **Throwable** classes disabling writable stack traces, or certain JVM optimizations can all make traces differ from the standard structure.

**Takeaway:** The top frame records where the trace of that **specific Throwable** was constructed/captured, not universal proof that every throw of the same object happened at that exact line.

## 11. Library Frames vs. Application Frames

A stack trace can contain frames from multiple system layers:

- **java.base/java.lang...**, **java.base/java.util...**: JDK methods.
- **org.springframework...**, **org.hibernate...**, **com.fasterxml...**, or other framework packages: framework/library layers.
- **com.example...**: your application code.
- Names containing **lambda$...**, **$$Lambda**, proxies, or reflection: ways the JVM/framework implements callbacks and dynamic invocation.

Reading a stack trace should not mean filtering out all library frames and discarding them. For example:

- **Integer.parseInt** tells you the error is string-to-number conversion.
- **Objects.requireNonNull** tells you there is a non-null validation check.
- **ArrayList.get** tells you it is an indexed access operation.
- **CompletableFuture** or **FutureTask** tells you the error crossed an asynchronous boundary.
- **Method.invoke** helps identify a reflection call.

Then locate the application frame **closest to and most relevant to the error area**, rather than assuming the first application frame is the bug. If the error occurred when a framework called back into your code via a callback, important application frames may appear at multiple positions.

### Other Ways Locations Are Displayed

You may encounter:

~~~text
at java.base/java.util.ArrayList.get(ArrayList.java:427)
at app.NativeBridge.nativeMethod(Native Method)
at app.GeneratedProxy.call(Unknown Source)
at app.Main.lambda$main$0(Main.java:23)
~~~

These are format illustrations, not claims about fixed line numbers in any JDK version. **Native Method** and **Unknown Source** indicate that there is no corresponding Java source line location in the frame as displayed; **lambda$...** may be a synthetic method generated for a lambda, whose name can vary by compiler. The module prefix, such as **java.base/**, is not part of the class name returned by **StackTraceElement.getClassName()**.

If classes were compiled without **LineNumberTable** or the running code differs from the source open in the IDE, line numbers may not be useful. Do not edit that exact line in an outdated source copy and claim the issue is resolved: first verify the matching artifact, commit, and runtime environment.

## 12. Java 17: Reading StackTraceElement Programmatically

A Throwable can provide:

~~~java
// Illustrative code in a method receiving a Throwable.
StackTraceElement[] frames = failure.getStackTrace();
for (StackTraceElement frame : frames) {
    String className = frame.getClassName();
    String method = frame.getMethodName();
    String fileName = frame.getFileName();
    int line = frame.getLineNumber();
    // Use these values for analysis or display.
}
~~~

Useful APIs:

| API | Meaning and limitations |
| --- | --- |
| **getClassName()** | Binary name of the class for the frame, not necessarily a Java file you can edit |
| **getMethodName()** | Method name or compiler-generated synthetic name |
| **getFileName()** | Source file name if known; may be null |
| **getLineNumber()** | Line number if available; special values indicate unknown or native |
| **isNativeMethod()** | Whether the frame represents a native method |
| **toString()** | Frame representation close to the **at ...** line syntax |

Do not assume **getStackTrace()[0]** always exists: a Throwable can have an empty trace, especially when writable stack trace is disabled or configured by the class author. For diagnostic code used in production, check the array length before indexing.

The Section 6 example uses a helper **firstApplicationFrame** that filters by the example's own class. It **intentionally throws IllegalStateException** if no matching frame is found to catch violated assumptions in the demo. A general-purpose diagnostic tool should return Optional or a "not found" signal rather than assuming every trace has a frame from an application package.

Java 9+ also provides **StackWalker** to traverse the current executing thread's stack. However, StackWalker captures **the current stack when called**, whereas **Throwable.getStackTrace()** reads the trace already stored on a Throwable. They do not replace each other: to find where an earlier exception occurred, you usually need that exception's trace, not the stack of the running logger.

## 13. Distinguishing Main Thread Traces from Errors in Asynchronous Tasks

With **ExecutorService**, **Future**, or **CompletableFuture**, a task may fail on a worker thread while the error result is read on the caller thread. Two layers of traces then easily appear:

1. **Task cause**: frames from the worker, where the exception was created/raised.
2. **Wrapper when retrieving the result**: frames from the caller invoking **get()** or **join()**, or frames from the completion machinery.

Conceptual example:

~~~text
java.util.concurrent.ExecutionException: java.lang.IllegalStateException: worker failed
    at java.base/java.util.concurrent.FutureTask.report(FutureTask.java:...)
    at java.base/java.util.concurrent.FutureTask.get(FutureTask.java:...)
    at app.Main.main(Main.java:...)
Caused by: java.lang.IllegalStateException: worker failed
    at app.Worker.compute(Worker.java:...)
    at app.Worker.call(Worker.java:...)
    ... more ...
~~~

This is an illustrative structure, not exact stdout. The top section describes where **the caller retrieved the error result**, while **Caused by** describes where **the worker created the error**.

With **CompletableFuture**, **get()** typically throws checked **ExecutionException** when the Future completes exceptionally due to a task error; **join()** typically throws unchecked **CompletionException**. Both wrappers can hold the same original error in their cause. For a cancelled Future, **CancellationException** may be thrown directly. **get(timeout)** can throw **TimeoutException** because the wait expired, not necessarily because the worker created an exception.

When investigating, distinguish:

- **InterruptedException at caller.get()**: the caller itself may have been interrupted while waiting.
- **InterruptedException from a Callable worker**: may appear as the cause inside ExecutionException.
- **TimeoutException directly from get(timeout)**: the caller did not see a result within the deadline.
- **TimeoutException as a cause after CompletableFuture's orTimeout**: the Future was completed exceptionally by a timeout policy.

If you look only at the caller's wrapper and hunt for a bug at **future.get()**, you will likely miss the real error inside the task or a timeout policy at another layer.

## 14. Reading Traces with try-with-resources, finally, and Cleanup

Resources are released when exiting a block, even if the try body already threw an exception. However, **close()** can also fail.

With **try-with-resources**:

~~~java
// Illustration with a resource implementing AutoCloseable.close().
try (var resource = openResource()) {
    performOperation(resource);
}
~~~

If **performOperation** throws error A and **resource.close()** throws error B, A is kept as primary and B is added to **A.getSuppressed()**. Therefore, when reading logs, also look for **Suppressed** to see whether cleanup failed without mistaking B for the cause of A.

If you use **finally** for cleanup and close throws a new unhandled exception, B can mask A. That is a programming bug that loses the stack trace of the initial failure. Do not compare only the two messages and conclude "close is the only error."

Another case: the try body succeeds, but close fails. There is no error A from the body; B can be the primary exception propagated out. Hence **suppressed** does not mean **every exception originating in close**.

If a cleanup error sits deep inside a wrapper's cause as in the main example, check **Suppressed** on the relevant cause itself. Printing only **wrapper.getSuppressed()** may return an empty array even though **wrapper.getCause().getSuppressed()** contains a critical error.

## 15. Common Sources of Confusion When Comparing Logs with Source Code

A stack trace taken from a running system must be placed side-by-side with **the exact source code version**:

- Were the right JAR, classpath, and container image deployed?
- Were the **.class** files compiled from the right commit?
- Did line numbers shift because source code was edited without rebuilding/redeploying?
- Was an exception wrapped at a framework boundary so the top frame looks different from expected?
- Are there lambdas, proxies, reflection, or generated code making class/method names harder to match?
- If it occurred in an async task, are you looking at the consumer thread's stack trace instead of the producer's error?
- Did the log aggregator strip **Caused by**, **Suppressed**, or truncate stack trace length?

A log showing **NullPointerException** with no frames because the logger configuration prints only the message is not proof that the JVM had no stack trace. Check how the Throwable is passed to the logging API.

Similarly, a trace containing **Unknown Source** does not mean the error is "impossible to debug." Use class/method names, neighboring frames, matching bytecode/artifacts, and operational facts to narrow it down; and enable line number metadata for builds that need diagnostic support.

## 16. Logging Without Losing Traceback Information

Java provides **Throwable.printStackTrace()**, which is suitable for examples or simple diagnostics:

~~~java
// Illustrative code inside a valid catch block.
catch (Exception failure) {
    failure.printStackTrace();
}
~~~

In production applications, you should usually use a logging framework or **java.util.logging** according to system policy. Example with the JDK's **java.util.logging.Logger**:

~~~java
import java.util.logging.Level;
import java.util.logging.Logger;

// Illustration inside a class with Logger logger and Throwable failure.
logger.log(Level.SEVERE, "Unable to process request", failure);
~~~

This is a contextual snippet, not a standalone class; **logger** must be initialized and **failure** must exist.

For loggers with an **error(String, Throwable)** signature:

~~~java
// Illustration of the corresponding logger API, not standalone Java SE.
logger.error("Unable to process request", failure);
~~~

Passing the **Throwable** gives the formatter the opportunity to output the stack trace, cause, and suppressed exceptions. Conversely:

~~~java
// Anti-pattern: usually logs only the message.
logger.error("Unable to process request: " + failure.getMessage());
~~~

can lose the trace. Check the logger signature and specific logging pipeline; do not assume every logging system prints the full exception tree just because the object was passed.

### Logging Once at the Appropriate Boundary

An error passing through multiple service/controller layers can get logged in every catch block and rethrown. The result is duplicate stack traces for the same request, easily miscounted as multiple incidents. A better pattern is usually:

- Lower layers **throw/wrap with an appropriate cause** and preserve necessary context.
- The boundary-owning layer (controller/job scheduler/message consumer) logs the full error once at the appropriate level.
- Use a request ID/trace ID or correlation ID to connect events across threads and services.
- Log again at intermediate layers only if there is genuinely useful independent information.

When logging in real systems, avoid writing passwords, tokens, personal data, card data, or raw requests containing secrets into exception messages. Diagnostic stack traces should be thorough while still complying with security and data retention policies.

## 17. A Step-by-Step Workflow for Reading a Stack Trace to Find a Bug

An effective practical workflow:

### Step 1: Collect the Full Throwable Tree

Do not capture only the first exception line. Gather **at** frames, **Caused by**, **Suppressed**, preceding/following messages for the same request, and application version metadata. If the log is truncated, retrieve the full version before drawing conclusions.

### Step 2: Identify Wrapper vs. Direct Error

If the first line is **CompletionException**, **ExecutionException**, **InvocationTargetException**, or a framework exception used to add context, follow **getCause()** down. Do not mistake the wrapping site for the original business error site.

### Step 3: Read the Appropriate Deep Error Type

Determine whether the error relates to input, state, parsing, permissions, concurrency, I/O, or an external system. Use the exception type as a directional clue, not a replacement for inspecting actual logic.

### Step 4: Inspect the Application Frame Nearest the Cause

Find the system's own code frame appearing in the relevant Throwable's trace. Open the exact file and line of the running artifact. Identify which expression on that line can fail, rather than reading only the method name.

### Step 5: Walk Down the Callers to See Where the Data Came From

The lower frames show the call chain. Ask where the caller received the input, where it was validated, whether any state mutated, and whether a race condition or stale data is possible.

### Step 6: Inspect Additional Cause/Suppressed Entries

If **Caused by** is present, determine the causal relationship. If **Suppressed** is present, check whether cleanup broke and left any state side effects. Do not conflate the two as "the same error."

### Step 7: Cross-Check Operational Context

Check timestamps, dependency status, thread names, endpoints, request IDs, deployed versions, feature flags, configuration, system load, and actions immediately preceding the error. A stack trace is usually a good starting point, not the entire picture.

### Step 8: Write a Reproducing Test

Write a unit test or integration test with the failing data and conditions. Verify not only that "the right exception is thrown," but also the cause, useful message, and state preservation on failure.

### Step 9: Fix the Root Cause, Not Just the Symptom

Do not fix by adding **catch(Exception) { return null; }** or a swallowing **try/catch** just to make the log disappear. If the error is bad input, fix validation/handling; if it is a race, fix synchronization/ownership; if a resource is missing, fix configuration/resource lifecycle.

### Step 10: Verify Results and Monitor After Deployment

Test the success path, similar failure paths, and cleanup errors; after deployment, confirm the corresponding logs drop without state corruption or new regressions.

## 18. Analysis Examples for Common Scenarios

### NullPointerException

~~~text
java.lang.NullPointerException
    at app.OrderService.calculate(OrderService.java:81)
    at app.OrderController.create(OrderController.java:33)
~~~

Check which variable can be null when dereferenced at **calculate:81**, where the data is initialized/validated, and what object the caller **create** passes in. Do not automatically conclude every NullPointerException should be fixed with an **if (x != null)**; the contract may require the object to be non-null, meaning the caller needs fixing or the data needs clearer validation.

### NumberFormatException

~~~text
java.lang.NumberFormatException: For input string: "x"
    at java.base/java.lang.Integer.parseInt(Integer.java:...)
    at app.ConfigParser.parsePort(ConfigParser.java:19)
    at app.Bootstrap.start(Bootstrap.java:8)
~~~

**Integer.parseInt** is where the error was created in the JDK, but **parsePort** is the frame to inspect for configuration data. Check where the port is read from, whether there is whitespace, invalid formatting, or range constraints.

### IndexOutOfBoundsException

~~~text
java.lang.IndexOutOfBoundsException: Index 4 out of bounds for length 3
    at java.base/java.util.ArrayList.get(ArrayList.java:...)
    at app.ReportService.column(ReportService.java:47)
~~~

Check how ReportService computes the index relative to the data size, whether the collection could be modified concurrently, loop boundaries, or missing data. Do not blame ArrayList when the caller supplies an out-of-range index.

### IOException with a Deep Cause

~~~text
java.io.IOException: failed to load feed
    at app.FeedReader.read(FeedReader.java:56)
Caused by: java.net.ConnectException: Connection refused
    at ... network stack ...
~~~

The outer layer says loading the feed failed. The cause tells you the connection was refused. Cross-check host/port, target service, network policy, and dependency status. A stack trace alone cannot prove whether it is a firewall issue or a downed service without external evidence.

### CompletionException from Async Execution

~~~text
java.util.concurrent.CompletionException: java.lang.IllegalStateException: worker failed
    at ... completion machinery ...
Caused by: java.lang.IllegalStateException: worker failed
    at app.Worker.process(Worker.java:72)
~~~

Prioritize inspecting **Worker.process:72** and the task input. The consumer line calling **join()** is not necessarily the source of the error, even though that is where the exception was observed.

All snippets above are format illustrations, not exact output from running the Section 6 program.

## 19. Testing Exception Behavior and Trace Quality

When designing classes and APIs that can fail, treat exception quality as part of the contract:

| Scenario to test | What to verify |
| --- | --- |
| Invalid input | Correct exception type, message has enough context without leaking sensitive data |
| Wrapped low-level error | Wrapper has the original error as its cause |
| Rethrown Throwable | Does not accidentally lose the original object, cause, or suppressed exceptions |
| Try-with-resources with primary and close errors | Primary error stays intact; close error is in suppressed |
| Failed async task | Consumer sees the expected wrapper; cause reflects the task error |
| Logger receiving Throwable | Tests/integration verify the formatter preserves stack trace/cause/suppressed |
| Multiple artifact versions | File/line in trace matches the running version |
| Intentionally recovered error | Do not treat fallback as success if the business contract requires reporting failure |

You can assert **same instance** for the cause instead of comparing messages alone. For example, in Section 6, if you extract a method returning the wrapper for testing, verify that **wrapper.getCause()** is still the exact NumberFormatException that was caught, and **getSuppressed()** on the cause contains the IOException from close.

**Do not hardcode source line numbers in ordinary tests**, unless the diagnostic tool's own contract requires line mapping. Line numbers shift as code is edited, and traces can differ across build modes. Tests can assert class/method names or cause/suppressed relationships more reliably.

If using JUnit, a simple test can assertThrows the expected type and then inspect cause/suppressed. However, actual test code must match your JUnit version and project setup; do not confuse framework-dependent code with standalone compilable Java SE code.

## 20. Common Mistakes When Reading or Logging Stack Traces

**Reading only the first line.** Easily misses the deep cause holding the real error, especially with CompletionException/ExecutionException or business wrappers.

**Assuming the wrapper's top frame is the lowest-level error source.** The top frame may just be where the wrapper was constructed; inspect the cause's trace.

**Finding only a project package frame and assuming it is the bug.** The application frame may be reporting an error by contract while the root cause lies in configuration, input, external data, or a dependency.

**Ignoring Suppressed.** You may miss that close/rollback failed and left system state uncleaned.

**Confusing ... N more with N new errors.** It is a compact way of omitting duplicate frames when printing the exception tree.

**Catching an error and creating a new RuntimeException from getMessage only.** Breaks the cause chain and loses the original trace, making debugging harder.

**Logging only getMessage().** Logs lack class/method/source line, cause, and suppressed exceptions. Pass the Throwable to the logger.

**Logging at every layer.** Creates duplicate records of the same incident, alert noise, and wasted resources. Choose responsible observation boundaries.

**Trusting line numbers blindly when code and deployment differ in version.** You may be reading outdated source. Verify artifact/hash/commit and debug line info.

**Using exception messages as branching keys in logic.** Messages can change across JDKs or contexts; prefer type, cause, structured error codes, or API contracts.

**Treating the trace at caller.get()/join() as the entire async history.** The worker may have its own trace in the cause; follow the pipeline and correlation ID.

**Leaking secrets through logs.** Exceptions and stack traces are still operational data that can contain file names, URIs, inputs, and configuration; apply masking and access/retention policies.

## 21. Practical Checklist for Reading a Stack Trace

Before concluding on a root cause, answer:

1. What is the **outermost exception type**, and what context does its message provide?
2. Is there a **Caused by**? Which deep cause actually relates to the failed operation?
3. Is there a **Suppressed** exception? What failed during cleanup?
4. Where is the **first frame of the Throwable being analyzed**? Is it a library, wrapper, or application frame?
5. Which application frame is closest to the error point, and **what does that line do** with the current data?
6. What callers do the lower frames reflect, and how did data flow through them?
7. Are there **lambda/proxy/reflection** names, module prefixes, Native Method, or Unknown Source entries that need explanation?
8. Did the error cross **Future/CompletableFuture** so the wrapper was created on a consumer thread?
9. Does the stack trace match **the deployed code** and the running build's source line metadata?
10. Does the log include the full Throwable tree, context, and trace ID without exposing sensitive data?
11. Have you written a reproducing test and fixed **the root cause** rather than merely swallowing the exception?

**Conclusion:** Effective stack trace reading starts with **the exception type and message**, then follows **the stack frames**, distinguishes **where the exception was recorded** from **where the application created the error condition**, and always inspects **Caused by** along with **Suppressed**. With wrappers or asynchronous tasks, the outermost error is not necessarily the initial business failure. Preserving the full Throwable chain when logging and matching against the exact running source code are the foundation for reliably identifying root causes.
