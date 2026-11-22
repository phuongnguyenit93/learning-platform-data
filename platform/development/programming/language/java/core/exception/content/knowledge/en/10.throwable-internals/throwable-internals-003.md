# At What Point Is a Stack Trace Recorded in Java?

When an exception occurs in Java, the stack trace helps answer the question **"in which call path was this error object created?"**. However, a common misconception is that every `throw` statement automatically captures a new stack trace at the throw site. For a typical `Throwable`, **the stack trace is recorded when the exception object is instantiated** (via the `fillInStackTrace()` mechanism during construction), **not automatically refreshed on every `throw e`**.

This explains why an exception created in method A, stored, and then thrown in method B typically has **A** as its first frame, not B; it also explains why `throw e` inside a `catch` block generally preserves the original error trace. However, Java provides APIs to explicitly refresh or replace a stack trace, and the JVM has special exceptions and optimization capabilities. Therefore, it is necessary to distinguish between **recording time**, **throwing time**, **printing time**, and **the current call stack**.

This article clarifies those points in time, how to verify them with Java 17+, the effects of rethrowing, wrapping, `fillInStackTrace()`, `getStackTrace()`, `setStackTrace()`, suppressed exceptions, special constructors, and the practical limitations of stack trace data.

## 1. What Is a Stack Trace?

The **stack trace** of a `Throwable` object is information about the method call sites associated with the point in time when the stack trace was recorded. A stack trace is typically a sequence of `StackTraceElement` instances:

```text
java.lang.IllegalStateException: Lỗi ví dụ
    at Example.create(Example.java:12)
    at Example.main(Example.java:20)
```

This is an **illustrative format**, not the fixed output of a specific program: file names and line numbers vary depending on source code, compilation, and environment.

A `StackTraceElement` can provide:

- Class name: `getClassName()`.
- Method name: `getMethodName()`.
- Source file name: `getFileName()` if available.
- Line number: `getLineNumber()` if available, which may be a negative number indicating that appropriate information is unavailable.
- Native method status: `isNativeMethod()`.
- In modern Java, module and class loader metadata are also included in some cases.

Typically, the first element of the `getStackTrace()` array represents the most recent user-code-level recording point, after the JVM handles internal initialization frames. However, **you should not assume that the count, order, or completeness of all frames is invariant across all JVMs, compilers, and configurations**.

A stack trace is not a history of every statement that executed; it is a **snapshot of the call stack**, not a sequential log of all program events.

## 2. Four Points in Time to Distinguish

| Event | Meaning | Does it by default record a new stack trace into the same exception? |
| --- | --- | --- |
| `new SomeException(...)` | Creates the object; the standard `Throwable` constructor records stack information | **Yes**, via the standard initialization mechanism and if writable stack trace is enabled |
| `throw e;` | Throws the object currently referenced by `e` | **No**; typically preserves the existing stack trace |
| `e.fillInStackTrace();` | Requests refilling the stack trace according to the current call stack | **Yes**, if the object allows a writable stack trace |
| `e.printStackTrace();` or `e.getStackTrace()` | Prints or reads the already-recorded stack trace data | **No**; they do not automatically re-capture the call path just because they are accessed |

In addition:

- `new WrapperException("...", cause)` creates a **new object**, so the wrapper has its own stack trace, recorded at the **site where the wrapper is created**.
- The original exception in `cause` remains a different object and can retain the stack trace created earlier.
- `e.setStackTrace(array)` **replaces the visible stack trace data** with code-supplied data if the object permits it; this is not an operation that automatically captures the current call stack.
- Some `Throwable` objects can be created **without recording a stack trace** using a constructor intended for subclasses, and the JVM may omit or limit information under special mechanisms.

The key takeaway: **throwing an exception** and **recording a stack trace** are two different operations, even though they often occur close together when you write `throw new ...`.

## 3. Why Does `throw new ...` Make Us Think the Stack Trace Is Created at Throw Time?

Consider:

```java
throw new IllegalArgumentException("Sai tham số");
```

This is an **illustrative statement**. Within the same expression, **two things** happen in close succession:

1. `new IllegalArgumentException(...)` creates the object; the standard `Throwable` initialization path records the stack trace.
2. `throw` throws the newly created object.

Because instantiation and throwing are at the same source location, the stack trace usually points to the exact line containing `throw new`. However, the reason is that **the object was created there**, not because Java always records a trace at every `throw` keyword.

To prove this, separate the two actions:

```java
IllegalArgumentException problem =
        new IllegalArgumentException("Sai tham số");
// Other operations may occur here.
throw problem;
```

This is an **illustrative snippet inside a method**. The stack trace is normally recorded on the line where `problem` is created. The subsequent `throw problem` statement does not automatically refresh the trace.

This distinction is especially important when an exception is instantiated by a helper, stored in a field, or passed across multiple layers before being thrown.

## 4. Runnable Example: Created in A, Thrown in B

Save the following program as **`CreationVsThrowDemo.java`**:

```java
public class CreationVsThrowDemo {
    static IllegalStateException makeProblem() {
        return new IllegalStateException("Không hợp lệ");
    }

    static void throwLater(IllegalStateException problem) {
        throw problem;
    }

    public static void main(String[] args) {
        IllegalStateException problem = makeProblem();
        System.out.println("Tạo xong exception");

        try {
            throwLater(problem);
        } catch (IllegalStateException e) {
            System.out.println("Bắt tại main");
            System.out.println("Frame đầu: "
                    + e.getStackTrace()[0].getMethodName());
            System.out.println("Cùng object: " + (e == problem));
        }
    }
}
```

Compile/run with Java 17+:

```bash
javac -encoding UTF-8 --release 17 CreationVsThrowDemo.java
java CreationVsThrowDemo
```

**Exact stdout** in a standard JVM environment with a writable stack trace:

```text
Tạo xong exception
Bắt tại main
Frame đầu: makeProblem
Cùng object: true
```

The first frame is `makeProblem`, where `new IllegalStateException(...)` executed, **not `throwLater`**. Even though the actual `throw` statement is inside `throwLater`, no automatic re-capture of the stack trace occurs merely because an existing object is thrown.

The object inside the handler is still `problem`; the comparison `e == problem` is `true`. `getStackTrace()[0]` is used in an example with a normal trace; for a `Throwable` type that disables writable stack traces or undergoes special optimization, the array may be empty, so general diagnostic code must check the array length.

## 5. How Does the `Throwable` Constructor Relate to `fillInStackTrace()`?

Standard `Throwable` constructors record stack information during object creation. The `fillInStackTrace()` API provides the ability to **refill the object's stack trace information according to the current calling context**.

This can be understood as:

```text
new MyException(...)
    |
    +-- runs the Throwable constructor chain
    |       |
    |       +-- normally records the current stack trace
    |
    +-- object is used afterwards
            |
            +-- throw object: does not auto-recapture
            +-- fillInStackTrace(): explicitly recaptures (if writable)
```

The model above describes **Java semantics**, not an assumption that every JVM has identical internal native code. At the application level, what matters is that stack trace information is normally tied to **object creation time** and can change when `fillInStackTrace()` is explicitly called.

Subclasses can customize trace initialization and management. Therefore, when handling exceptions created by frameworks, libraries, or the JVM, you should not assume with certainty that every object is recorded exactly once and is immutable.

## 6. Does Rethrowing with `throw e` Preserve the Stack Trace?

Normally **yes**. `throw e` inside a handler rethrows the **exact same object** that was caught, so it preserves that object's stack trace if no code modifies the trace.

Example **`RethrowTraceDemo.java`**:

```java
public class RethrowTraceDemo {
    static void origin() {
        throw new IllegalArgumentException("Lỗi tại origin");
    }

    static void middle() {
        try {
            origin();
        } catch (IllegalArgumentException e) {
            System.out.println("Catch giữa: "
                    + e.getStackTrace()[0].getMethodName());
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            middle();
        } catch (IllegalArgumentException e) {
            System.out.println("Catch ngoài: "
                    + e.getStackTrace()[0].getMethodName());
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 RethrowTraceDemo.java
java RethrowTraceDemo
```

**Exact stdout** on standard Java 17:

```text
Catch giữa: origin
Catch ngoài: origin
Message: Lỗi tại origin
```

When `origin()` calls `new IllegalArgumentException(...)`, the trace is recorded with `origin` as the first frame. The handler in `middle` receives the object, reads the trace, and executes `throw e`. The outer handler receives the same object; the first frame is still `origin`.

**Avoid this misconception:** although the trace retains the original location, the exception did indeed pass through `middle()`. The original stack trace already recorded the frames active at instantiation time; it does not mean the trace continues to grow longer on each rethrow. If you want to record an important rethrow decision, you can add structured logging at the appropriate boundary or use a wrapper exception with a cause according to your contract.

## 7. Explicitly Calling `fillInStackTrace()` Changes the Recording Point

`Throwable.fillInStackTrace()` is a public method (declared `synchronized` in the API) that returns the `Throwable` itself after updating the stack trace information if trace recording is permitted.

Program **`RefillTraceDemo.java`**:

```java
public class RefillTraceDemo {
    static IllegalStateException createProblem() {
        return new IllegalStateException("Dữ liệu sai");
    }

    static void refreshAndThrow(IllegalStateException problem) {
        System.out.println("Trước refresh: "
                + problem.getStackTrace()[0].getMethodName());
        problem.fillInStackTrace();
        System.out.println("Sau refresh: "
                + problem.getStackTrace()[0].getMethodName());
        throw problem;
    }

    public static void main(String[] args) {
        IllegalStateException problem = createProblem();

        try {
            refreshAndThrow(problem);
        } catch (IllegalStateException e) {
            System.out.println("Caller thấy: "
                    + e.getStackTrace()[0].getMethodName());
            System.out.println("Cùng object: " + (e == problem));
        }
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 RefillTraceDemo.java
java RefillTraceDemo
```

**Exact stdout** when writable trace behaves normally:

```text
Trước refresh: createProblem
Sau refresh: refreshAndThrow
Caller thấy: refreshAndThrow
Cùng object: true
```

`fillInStackTrace()` **does not create a new exception**: object identity is preserved. However, it **replaces the stack trace information attached to the object** with information from the site of the explicit refresh, so the first frame changes to `refreshAndThrow`.

Design warning: calling `fillInStackTrace()` can cause the original failure site to no longer be visible as before, making diagnosis harder. You should not call this method merely to make the stack trace "look closer to the current point" unless there is a clear reason and the original information is preserved through an appropriate mechanism.

## 8. `throw e`, `throw new ...`, and Wrapping Have Different Traces

Three options to distinguish:

| Approach | Thrown object | Typical trace recording site | Where is the original error preserved? |
| --- | --- | --- | --- |
| `throw e;` | The `e` object itself | When `e` was created/refreshed | The object itself |
| `throw new IllegalStateException("Lỗi mới");` | New object | Where the new object is created | Old object is not kept unless linked |
| `throw new IllegalStateException("Lỗi dịch vụ", e);` | New wrapper | Where the wrapper is created | `wrapper.getCause() == e` |
| `e.fillInStackTrace(); throw e;` | The `e` object itself | Where `fillInStackTrace()` is called | May lose the object's original trace |

**Wrapping** is a way to add current-layer context without overwriting the original exception's stack trace. If the repository layer throws an I/O error, the service layer can create an exception describing the service failure with the I/O error as its `cause`.

The checked/unchecked signature of the wrapper must follow Java's contract; passing `cause` does not automatically turn a checked exception into an unchecked one unless the chosen **wrapper type** is unchecked.

## 9. Wrapper Example: Two Stack Traces at Two Points in Time

Save **`WrapperTraceDemo.java`**:

```java
public class WrapperTraceDemo {
    static void operation() {
        throw new IllegalArgumentException("Giá trị không hợp lệ");
    }

    static void service() {
        try {
            operation();
        } catch (IllegalArgumentException e) {
            throw new IllegalStateException(
                    "Dịch vụ thất bại", e);
        }
    }

    public static void main(String[] args) {
        try {
            service();
        } catch (IllegalStateException e) {
            System.out.println("Wrapper frame đầu: "
                    + e.getStackTrace()[0].getMethodName());
            System.out.println("Cause frame đầu: "
                    + e.getCause().getStackTrace()[0].getMethodName());
            System.out.println("Cause message: "
                    + e.getCause().getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 WrapperTraceDemo.java
java WrapperTraceDemo
```

**Exact stdout** with a normal writable trace:

```text
Wrapper frame đầu: service
Cause frame đầu: operation
Cause message: Giá trị không hợp lệ
```

`IllegalArgumentException` was created in `operation`, so the cause keeps the trace from there. The `IllegalStateException` wrapper was created in `service`, so the wrapper's trace has `service` as its first frame. The `getCause()` relationship lets you see **both the higher-layer context and the original origin**.

This is one reason wrapping with a cause is usually better than calling `fillInStackTrace()` on an existing exception: a wrapper preserves both perspectives without overwriting the original trace.

## 10. `getStackTrace()` Does Not Auto-Update to the Current Call Stack

`getStackTrace()` returns a `StackTraceElement[]` array representing the stack trace data **currently stored in the object**. Calling the method from caller A, B, or C does not turn the array into a snapshot at A, B, or C.

For example:

```java
static String firstFrame(Throwable e) {
    StackTraceElement[] frames = e.getStackTrace();
    return frames.length == 0
            ? "(không có frame)"
            : frames[0].getMethodName();
}
```

This is an **illustrative method** that can be placed inside a Java class. It reads the existing first frame while safely handling an empty array. It does not call `fillInStackTrace()`.

Two notes:

1. **There is no guarantee the array always has elements.** A `Throwable` may have been created with writable trace disabled, or in some cases the JVM may not provide the expected frames.
2. **Line numbers and file names should not be treated as stable data keys.** They can change when source code is edited, debug information is missing, native code is used, builds differ, or runtime optimizations occur.

Calling `getStackTrace()` at a later time does not "rewind" past call stacks; it only reads the information stored in the object.

## 11. `getStackTrace()` Returns a Modifiable Array, but Modifying It Does Not Mutate the Object

`Throwable.getStackTrace()` returns a **copy of the array** (`StackTraceElement[]`), not an array that can be used to directly mutate the internal trace of the object by replacing elements.

Example **`StackTraceCopyDemo.java`**:

```java
public class StackTraceCopyDemo {
    static IllegalStateException create() {
        return new IllegalStateException("Ví dụ");
    }

    public static void main(String[] args) {
        IllegalStateException e = create();

        StackTraceElement[] snapshot = e.getStackTrace();
        String originalMethod = snapshot[0].getMethodName();

        snapshot[0] = new StackTraceElement(
                "FakeClass", "fakeMethod", "Fake.java", 1);

        System.out.println("Snapshot đã sửa: "
                + snapshot[0].getMethodName());
        System.out.println("Object vẫn giữ: "
                + e.getStackTrace()[0].getMethodName());
        System.out.println("Ban đầu: " + originalMethod);
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 StackTraceCopyDemo.java
java StackTraceCopyDemo
```

**Exact stdout** with a normal trace:

```text
Snapshot đã sửa: fakeMethod
Object vẫn giữ: create
Ban đầu: create
```

You replaced an element of the **local `snapshot` array**, not the trace information inside the object. If you want to formally alter an exception's trace, the API provides `setStackTrace(...)`; however, injecting fake frames like that is not something you should do in business code.

`StackTraceElement` is an object representing a frame; using them for observation and diagnosis is different from trying to rewrite history and obscure the source of an error.

## 12. `setStackTrace()` Replaces Data; It Does Not Capture the Current Stack

`Throwable.setStackTrace(StackTraceElement[] stackTrace)` can **replace** the trace information of a `Throwable` that supports a writable stack trace with a `StackTraceElement` array you provide. No automatic capture of the current call path occurs simply by calling `setStackTrace`.

Illustrative example:

```java
Throwable e = new IllegalStateException("Lỗi");
e.setStackTrace(new StackTraceElement[] {
        new StackTraceElement("Example", "custom", "Example.java", 7)
});
```

This is an **illustrative snippet**. After setting an artificial trace, if the object allows a writable stack trace, `e.getStackTrace()[0].getMethodName()` will be `"custom"`; that does **not** mean a Java method named `custom` was actually called at the time of the error.

The API validates the passed array—for example, it rejects a `null` array or `null` elements. It also copies the array to prevent the caller from mutating the stored data by modifying the external array afterwards.

In practice, **do not fabricate traces to "fix" an error**. When you need additional context, use messages, error codes, wrappers with `cause`, or structured logging; when you need the current call stack, use a current-stack inspection API instead of writing fake frames into a `Throwable`.

## 13. Distinguishing a Recorded Stack Trace from the Live Call Stack

A `Throwable` object holds **diagnostic data recorded at a specific point in time**. A thread's current call stack is a structure that changes continuously with every call and return.

APIs for inspecting the current stack include `Thread.currentThread().getStackTrace()` or `StackWalker` (Java 9+). They serve a different purpose from reading an old trace stored in an exception.

Example **`LiveVsStoredStackDemo.java`**:

```java
public class LiveVsStoredStackDemo {
    static Exception make() {
        return new Exception("Tạo trong make");
    }

    static void inspect(Exception e) {
        System.out.println("Lỗi được tạo tại: "
                + e.getStackTrace()[0].getMethodName());

        boolean hasInspect = StackWalker.getInstance()
                .walk(stream -> stream.anyMatch(
                        frame -> frame.getMethodName().equals("inspect")));
        System.out.println("Call stack hiện tại có inspect: " + hasInspect);
    }

    public static void main(String[] args) {
        Exception e = make();
        inspect(e);
    }
}
```

Run on Java 17:

```bash
javac -encoding UTF-8 --release 17 LiveVsStoredStackDemo.java
java LiveVsStoredStackDemo
```

**Exact stdout** on standard Java 17:

```text
Lỗi được tạo tại: make
Call stack hiện tại có inspect: true
```

`e.getStackTrace()` still reports `make`, where the exception was created. `StackWalker` observes the **active** stack when `inspect` is called, so it includes the `inspect` frame.

Do not confuse the two kinds of information: if you want to know where the exception originally came from, read the trace attached to the exception; if you want to know which calls the code is executing **right now**, use a current-stack API.

## 14. `printStackTrace()` Happens Later, but That Does Not Mean the Trace Was Recorded Later

An exception can be created at time T1, thrown at T2, caught at T3, and printed at T4:

```java
Throwable e = new IllegalStateException("Lỗi ví dụ"); // T1
// ...
throw e; // T2
```

This is **skeleton code**. If the caller catches it and invokes `e.printStackTrace()` at T4, printing occurs at T4, yet the displayed stack trace is still the data recorded at T1, unless another API or mechanism modified the data in between.

Distinguish:

- `getMessage()`: returns the message, not the trace.
- `toString()`: a short description usually consisting of the class name and message, not the frame list.
- `getStackTrace()`: returns the frame data stored in the object.
- `printStackTrace()`: performs the **action of printing** the exception and trace information, possibly including causes and suppressed exceptions.
- `fillInStackTrace()`: **modifies trace data**, not a print command.
- `setStackTrace()`: **assigns caller-supplied frame data**.

According to the standard API, the no-argument `printStackTrace()` prints to `System.err`, not `System.out`. When stdout and stderr output are interleaved, the actual display order between the two streams can vary; do not write tests that rely on an unguaranteed merged order.

## 15. Causes Have Their Own Traces; Suppressed Exceptions Also Have Their Own Traces

An exception can reference a **cause** and a list of **suppressed exceptions**:

```java
IllegalArgumentException root =
        new IllegalArgumentException("Lỗi chính");

IllegalStateException wrapped =
        new IllegalStateException("Lỗi dịch vụ", root);

wrapped.addSuppressed(
        new IllegalStateException("Không cleanup được"));
```

This is an **illustrative code snippet inside a method**, without `main`. The three `Throwable` instances are **three separate objects**. Each object is created at its own respective time, so each normally carries its own trace. Attaching object A as a cause or suppressed exception of B **does not automatically re-capture A's stack trace**.

With `try-with-resources`:

1. The main body throws exception A.
2. When exiting the block, `close()` may throw exception B.
3. Java keeps A as the **primary** exception and attaches B to `A.getSuppressed()` as appropriate.
4. A and B have separate traces: A's is tied to where A was created, and B's is tied to where B was created/filled.

Example **`SuppressedFramesDemo.java`**:

```java
public class SuppressedFramesDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("Lỗi close");
        }
    }

    static void work() {
        throw new IllegalArgumentException("Lỗi work");
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            work();
        } catch (IllegalArgumentException e) {
            System.out.println("Primary: "
                    + e.getStackTrace()[0].getMethodName());
            Throwable closing = e.getSuppressed()[0];
            System.out.println("Suppressed: "
                    + closing.getStackTrace()[0].getMethodName());
        }
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 SuppressedFramesDemo.java
java SuppressedFramesDemo
```

**Exact stdout** on standard Java 17:

```text
Primary: work
Suppressed: close
```

A's trace starts at `work`; B's trace starts at `close`. The fact that A contains B in its suppressed list does not merge the two frame arrays into one snapshot and does not turn B into an exception created in `work`.

In general programs, you must check `getSuppressed().length` before accessing element `[0]`. This example deliberately designs the resource to always throw on close and the body to always throw, so the result has one suppressed exception.

## 16. A Constructor Can Disable Writable Stack Traces

Since Java 7, `Throwable` has a constructor for subclasses:

```java
protected Throwable(String message,
                    Throwable cause,
                    boolean enableSuppression,
                    boolean writableStackTrace)
```

The last parameter, `writableStackTrace`, controls whether the object can record a stack trace. When set to `false`, the object is created in a **non-recording stack trace** mode, and operations like `fillInStackTrace()` or `setStackTrace()` on that object do not behave in the usual way. `getStackTrace()` returns an empty array.

Runnable example **`NoWritableTraceDemo.java`**:

```java
public class NoWritableTraceDemo {
    static class SilentTraceException extends Exception {
        SilentTraceException(String message) {
            super(message, null, true, false);
        }
    }

    public static void main(String[] args) {
        SilentTraceException problem =
                new SilentTraceException("Không ghi stack");

        System.out.println("Ban đầu: "
                + problem.getStackTrace().length);
        problem.fillInStackTrace();
        System.out.println("Sau fill: "
                + problem.getStackTrace().length);

        try {
            throw problem;
        } catch (SilentTraceException e) {
            System.out.println("Sau throw: "
                    + e.getStackTrace().length);
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 NoWritableTraceDemo.java
java NoWritableTraceDemo
```

**Exact stdout:**

```text
Ban đầu: 0
Sau fill: 0
Sau throw: 0
Message: Không ghi stack
```

This directly demonstrates that **not every `Throwable` has frames to read**, even after the object has been created, thrown, and caught. Code like `e.getStackTrace()[0]` is unsafe if applied indiscriminately to every exception.

Disabling writable stack traces can be used intentionally in some very frequently created exceptions to reduce overhead, at the cost of diagnostic capability. Do not disable stack traces just to hide a bug or because you want shorter logs.

## 17. `fillInStackTrace()` Does Not Force All Subclasses to Behave Identically

`Throwable.fillInStackTrace()` can be **overridden** in non-final subclasses. In addition to the constructor with the `writableStackTrace` parameter, a subclass can customize its trace-collection policy.

Consequences:

- Do not assume every library exception has its stack trace recorded in the constructor in the exact same way.
- Do not assume calling `fillInStackTrace()` will always produce frames if the object or subclass was designed not to retain a trace.
- Do not manipulate `Throwable` internals directly; use the public API and check for empty arrays.
- If you create a custom exception with special behavior, document its impact on logging, debugging, and error-observability tools.

For ordinary exceptions extending `RuntimeException` or `Exception` that do not override this mechanism and do not disable writable traces, the effective rule of thumb remains: **the constructor records the trace; `throw e` preserves it; `fillInStackTrace()` refreshes it**.

## 18. Special JVM Cases

Exceptions generated by the JVM can differ from `new` calls made by application code. On certain JVMs, versions, or configurations, there are optimizations that **omit or truncate the stack trace** of some exceptions that occur repeatedly at hot sites. In HotSpot, there is an optimization commonly called **fast-throw** for certain implicit exceptions; the actual behavior depends on the JVM, runtime flags, and circumstances.

Therefore:

- Do not rely on the assumption that every `NullPointerException` thrown by the JVM has complete stack frames.
- Do not use a single run to draw rigid conclusions about stack trace optimizations across all JVMs.
- Do not depend on fixed frame counts or line numbers for monitoring systems.
- A normal `new IllegalArgumentException(...)` exception and an implicit VM-thrown exception are not necessarily created or traced through the same internal path.
- When analyzing performance or JVM-specific differences, inspect the information of the actual running JVM version and logging/profiling configuration rather than changing business code based on assumptions.

**Warning:** A "stack trace missing frames" does not by itself prove that an exception was hidden or fabricated. It may result from the `Throwable` construction mode, optimizations, missing debug info, or code that modified the trace.

## 19. Why Should You Not Reuse the Same Exception Instance?

At the language level, you can create an exception object once and throw it multiple times:

```java
static final IllegalStateException SHARED =
        new IllegalStateException("Lỗi dùng chung");

static void run() {
    throw SHARED;
}
```

This is an **incomplete illustrative class/method**. The problem: `SHARED` is created when the class is initialized, so the stack trace may reflect **the static field initialization point**, not a specific `run()` call. If the same object is thrown across multiple threads or requests, the error information cannot distinguish between occurrences by their new call stacks.

This can also cause risks when other code modifies the suppressed exceptions or stack trace of the same object while multiple threads read it concurrently.

In most applications:

- **Create a new exception for each actual failure** to get an accurate trace.
- Let errors propagate naturally with `throw e` when you need to preserve the original object.
- If you need additional context at another layer, consider a wrapper with `cause` instead of reusing a static exception.
- Do not turn an exception object into a shared state accumulator across independent requests.

Some specialized high-performance frameworks or libraries may intentionally reuse stackless exceptions; that is a deliberate trade-off between diagnostics and performance, not the default pattern for business code.

## 20. Verifying Trace Recording Time with Stable Tests

If you write tests about stack traces, avoid asserting on a full string containing line numbers and file names, because those details change easily. Instead, for an explicitly created exception with a writable trace, verify the **first method name** or object **identity** according to the example's contract.

Example **`TraceAssertionsDemo.java`**:

```java
public class TraceAssertionsDemo {
    static IllegalStateException make() {
        return new IllegalStateException("Lỗi");
    }

    static void relay(IllegalStateException e) {
        throw e;
    }

    public static void main(String[] args) {
        IllegalStateException problem = make();

        try {
            relay(problem);
            throw new AssertionError("Đã không ném lỗi");
        } catch (IllegalStateException e) {
            if (e != problem) {
                throw new AssertionError("Đã đổi object");
            }

            StackTraceElement[] frames = e.getStackTrace();
            if (frames.length == 0
                    || !"make".equals(frames[0].getMethodName())) {
                throw new AssertionError("Sai thời điểm ghi trace");
            }

            System.out.println("PASS: tạo ở make, rethrow không làm mới");
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 TraceAssertionsDemo.java
java TraceAssertionsDemo
```

**Exact stdout** for a standard `Throwable`:

```text
PASS: tạo ở make, rethrow không làm mới
```

The test uses `throw new AssertionError(...)` to signal failure so it **does not depend on the `-ea` flag** of the `assert` statement. Checking for an empty frame array ensures the test fails with a clear message when run in an environment that violates the example's writable-trace assumption.

In general integration tests across multiple JVMs, consider the appropriate level of verification: do not depend on a specific first frame of a VM-thrown exception or the stability of `printStackTrace()` formatting.

## 21. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| "Every `throw e` records a stack trace at the `throw` line." | For a normal `Throwable`, `throw e` throws an existing object and does not auto-refresh the trace. |
| "`throw new E(...)` proves `throw` captures the trace." | In that expression, `new` creating the `Throwable` right before `throw` is the usual reason. |
| "`getStackTrace()` records the call stack at the time it is read." | It returns the trace data stored in the object; it does not call `fillInStackTrace()`. |
| "`printStackTrace()` creates a new trace." | It prints existing information; it is not a refresh operation. |
| "`fillInStackTrace()` creates a new object." | It returns the same `Throwable` and may update the current object's trace. |
| "Rethrowing loses the original trace." | `throw e` normally preserves the original trace; a new wrapper has its own trace and can keep the cause. |
| "`setStackTrace` is a snapshot of the current call stack." | It sets a caller-provided frame array; it does not capture the current stack. |
| "Modifying an element of `getStackTrace()` mutates the exception." | The API returns a copy of the array; to set the trace, use `setStackTrace`. |
| "Every `Throwable` always has at least one frame." | It can be empty due to `writableStackTrace=false` or special JVM behavior. |
| "A stack trace is a history of every method that ever ran." | It is point-in-time data, not a chronological event log. |
| "Cause and suppressed share the wrapper's trace." | Each object has its own trace, if present. |
| "File names and line numbers in a stack trace are always fixed." | They can change due to source edits, debug info, the JVM, and other mechanisms. |
| "Pre-creating an exception to reuse it reveals every throw site." | The trace may point to the **initial creation site**, causing misdiagnosis of later throw sites. |
| "Disabling stack traces does not affect error handling." | The object can still be thrown and caught, but crucial diagnostic information is lost. |

## 22. Self-Check Questions

**Question 1.** `Exception e = new Exception("x");` is in method A, then `throw e` is in B. Where does the stack trace normally start?  
**Answer:** From where the object was created/filled, normally method A; it does not automatically change to B because of `throw e`.

**Question 2.** Does `catch (Exception e) { throw e; }` automatically instantiate a new exception?  
**Answer:** No. It rethrows the same object as long as `e` was not reassigned to another object.

**Question 3.** How does `e.fillInStackTrace()` differ from `e.printStackTrace()`?  
**Answer:** `fillInStackTrace()` requests updating the object's stack trace (if supported), whereas `printStackTrace()` prints the current trace information to a stream.

**Question 4.** Does `new ServiceException("...", cause)` make `cause`'s trace become the wrapper's trace?  
**Answer:** No. The wrapper is a new object with its own trace at its creation site; `cause` retains its own trace.

**Question 5.** If `getStackTrace()` returns an empty array, can you read `[0]`?  
**Answer:** No. You must check `length > 0`; a `Throwable` may not store any frames.

**Question 6.** After getting `StackTraceElement[] a = e.getStackTrace()`, does replacing `a[0]` automatically mutate the object?  
**Answer:** No. `getStackTrace()` returns a copy of the stack trace array.

**Question 7.** Is `setStackTrace(...)` a safe way to obtain the current call path?  
**Answer:** No. It replaces the trace data with the passed array; to inspect the current stack, use `StackWalker` or the appropriate `Thread` API.

**Question 8.** With `try-with-resources`, does an exception in `close()` have its own stack trace?  
**Answer:** Normally yes, if it is a `Throwable` created in `close()`. When a primary body error also occurs, the closing error is kept in the primary exception's `getSuppressed()`.

**Question 9.** Can a `Throwable` be created without collecting a stack trace?  
**Answer:** Yes. A subclass can use the constructor with `writableStackTrace=false`; certain JVM mechanisms can also result in an empty trace or missing frames.

**Question 10.** If the same exception instance is rethrown across two requests, do the two throws automatically create two separate traces?  
**Answer:** No. Without refreshing or replacing the trace, the same object retains the old information. This makes reusing a shared exception instance generally unsuitable for diagnostics.

**Question 11.** Why is asserting on an exact `Exception.java:123` brittle?  
**Answer:** Line numbers, file names, debug info, and how the runtime formats traces can change. Verify more stable characteristics appropriate to the test's scope.

**Question 12.** Is `Thread.currentThread().getStackTrace()` the same array as that of a previously created exception?  
**Answer:** No. It inspects the thread's live execution stack; an exception stores its own information from its capture time.

## 23. Practical Checklist

When you need to explain a stack trace in a Java project:

1. Identify where the exception was **created**; distinguish `throw new ...` from `throw existing`.
2. Check whether it is **rethrown** through `catch` blocks or forwarding layers.
3. Look for any calls to `fillInStackTrace()` or `setStackTrace()` that alter the diagnostic data.
4. If there is a **wrapper**, inspect `getCause()` to trace the original exception's creation site.
5. If `try-with-resources` is used, inspect `getSuppressed()` for cleanup errors and their own traces.
6. Do not overlook the possibility of an **empty trace array**, missing frames, or a disabled writable stack trace.
7. Do not confuse `printStackTrace()` (printing time) with the time information was recorded into the object.
8. Do not base business logic on message wording or line numbers.
9. If you need to add context, prefer clear logging and wrappers with `cause` rather than overwriting the original trace.
10. If you need the current stack, consider `StackWalker` or thread APIs instead of reading a previously created exception.
11. If the error is generated by the JVM itself, be mindful of JVM optimizations and configuration.
12. In tests, assert meaningful behavior and account for stability across different JVMs, versions, and execution modes.

## 24. Key Takeaways

**For a normal `Throwable`, the stack trace is recorded when the exception object is instantiated, not automatically re-recorded on every `throw e`.** The statement `throw new E(...)` looks like it records at the throw site because the object is created right inside the throw expression. `throw e` preserves the existing object and trace; `fillInStackTrace()` can explicitly update the trace, while a new wrapper gets a trace at its creation site and preserves the old exception via `cause`.

`getStackTrace()` and `printStackTrace()` are **read/print** operations, not mechanisms to re-capture the current stack. When a trace is disabled, modified, or subject to JVM optimization, it may be empty or missing frames that developers expect.

For accurate diagnosis, always separate three questions: **When was the exception created/traced? Where was the object thrown or rethrown? When was the information read or printed?** Answering these three questions correctly helps identify the root cause without confusing the observation point with the failure origin.
