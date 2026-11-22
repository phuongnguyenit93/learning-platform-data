# Comparison Table of Cause, Suppressed, and Stack Trace in Java

> **Topic:** Java Core → Exception → Reference. This document is a practical reference table on the three types of `Throwable` information: **cause** (the underlying cause error), **suppressed exceptions** (secondary exceptions attached), and **stack trace** (the call trace). The content uses Java 17+ semantics, standalone `try-with-resources` examples, log reading, wrapper handling, and common misconceptions that can easily cause loss of diagnostic data.

## 1. Quick Comparison Table

| Criterion | Cause | Suppressed exceptions | Stack trace |
|---|---|---|---|
| Question answered | **Which error led to the current exception?** | **Which secondary errors were retained while handling the primary error?** | **What call frame trace does this Throwable have?** |
| Data type | A `Throwable` reference or `null` | `Throwable[]` array, may be empty | `StackTraceElement[]` array, may be empty |
| Read API | `getCause()` | `getSuppressed()` | `getStackTrace()` |
| Write/generation API | Constructor taking `cause` or `initCause()` | `addSuppressed(Throwable)`; automatically added by Java in `try-with-resources` when appropriate | `fillInStackTrace()`, `setStackTrace(...)`; usually captured when constructing the Throwable |
| Relationship to current error | *Cause/layer-translation* relationship | Accompanying error, **does not automatically become the primary cause** | Information about execution frames, **not another Throwable** |
| Direct count | At most one direct cause; a cause can have a further cause | Can have multiple direct suppressed exceptions | Can have multiple frames in one trace |
| Automatically propagated across wrappers? | When the wrapper is created with cause | **Does not automatically transfer** the cause's suppressed exceptions to the wrapper | Wrapper and cause usually have **separate** stack traces |
| When to use | Wrapping technical errors into domain errors; `ExecutionException` holding a task error | Errors when closing resources, cleanup, secondary compensation | Investigating creation/throw site, code path, call layers |
| Checking in tests | `assertSame(expected, ex.getCause())` or checking type | `ex.getSuppressed().length`, element type/message | Top method/class when stable; usually **do not** hard-code line numbers |
| Should it be removed to make logs shorter? | No: may lose the root cause | No: may lose important cleanup errors | Not arbitrarily: may lose the location and call path of the error |
| Can it be absent? | Yes, if not declared or no cause is attached | Yes: an empty array is normal | Yes: stack can be disabled or empty due to implementation/conditions |
| Common display format in `printStackTrace()` | `Caused by: ...` line | `Suppressed: ...` line | Lines starting with `at ...` |

**Note:** Both *cause* and *suppressed* reference **Throwable** objects, whereas *stack trace* contains **StackTraceElement** objects. A single Throwable object can simultaneously have one cause, multiple suppressed exceptions, and its own stack trace; the Throwables in cause/suppressed also have their own metadata.

## 2. Relationship Model on a Throwable

~~~text
IllegalStateException("order processing failed")  <-- outer Throwable
  |
  +-- cause --> IOException("read failed")
  |               |
  |               +-- suppressed[0] --> IOException("close failed")
  |               |                      +-- separate stack trace
  |               +-- separate stack trace
  |
  +-- suppressed[] = empty
  +-- stack trace = frames when creating outer Throwable
~~~

The diagram illustrates **two independent error-linking forms** and a separate trace for each Throwable:

1. The service catches `IOException("read failed")` and wraps it into `IllegalStateException("order processing failed", cause)`.
2. In `try-with-resources`, the `close()` error is added to the **IOException thrown by the try body** as a suppressed exception.
3. The wrapper in the service has the IOException as its cause. `wrapper.getSuppressed()` can still be empty; to see the resource-closing error, you must go to `wrapper.getCause().getSuppressed()`.
4. The wrapper, cause, and suppressed Throwable can each have their own stack trace, captured at different locations.

Do not treat this system as an absolute business-semantic tree. It is a Throwable reference graph; applications can create non-standard relationships, long chains, or reused wrappers. When traversing manually, avoid assuming every throwable only has a simple cause chain.

## 3. Cause: Underlying Reason Preserved Across Abstraction Boundaries

A cause is a Throwable that the current exception treats as its **underlying cause error**. Read API:

~~~java
Throwable cause = exception.getCause();
~~~

If there is no cause, the value is usually `null`. A constructor with a cause:

~~~java
// Snippet inside a method.
java.io.IOException original =
        new java.io.IOException("database response unavailable");

IllegalStateException wrapper =
        new IllegalStateException("cannot load order", original);

System.out.println(wrapper.getCause() == original); // true
~~~

In this example, `IllegalStateException` is the error at the outer abstraction; `IOException` is the technical cause. Wrapping does not turn IOException into a suppressed exception. Cause and suppressed are **two different relationships**.

### When to use cause?

- Repository translates driver/I/O errors into storage exceptions.
- Service translates storage errors into domain exceptions that the caller can understand.
- Executor stores execution errors in `ExecutionException` received by the thread calling `Future.get()`.
- CompletableFuture reports exceptional completion via `CompletionException` when calling `join()`.
- An operation needs to add context while still allowing investigators to see the root cause.

Proper constructor when wrapping an error:

~~~java
catch (java.io.IOException ex) {
    throw new IllegalStateException("could not load profile", ex);
}
~~~

Avoid:

~~~java
catch (java.io.IOException ex) {
    throw new IllegalStateException(ex.getMessage());
}
~~~

The second approach **does not preserve the cause**; the caller can lose the IOException stack and cause information. If you only want to propagate the error according to the contract, use `throw ex;` when possible — not every catch block needs to create a wrapper.

### getCause() and initCause()

`Throwable.initCause(Throwable)` can set the cause **once** if the Throwable has not already had its cause initialized by constructor design. It returns the Throwable receiving the call. Attempting to change an already-initialized cause throws `IllegalStateException`; setting a Throwable as its own cause is invalid.

~~~java
// Valid inside a method.
Exception outer = new Exception("outer");
IOException cause = new IOException("inner");
outer.initCause(cause);
~~~

This snippet requires importing `java.io.IOException` if using the short name. **Prefer constructors that accept a cause** when the library provides them, because they are concise, clear, and keep the state valid from the start. Do not rely on `initCause()` to mutate an error chain already published to other threads.

Some Throwables have constructors that already initialize the cause (even if the value is `null`), so `initCause` cannot be called afterward; read the Javadoc of the constructor being used.

## 4. Suppressed Exceptions: Retaining Secondary Errors Without Masking the Primary Error

`Throwable.addSuppressed(Throwable)` attaches a secondary exception to the current Throwable. `getSuppressed()` returns an array of attached Throwables, or an empty array if there are none. Do not treat suppressed as unimportant errors: errors when closing a file, completing a transaction, or cleaning up resources can help determine why the final state is not as expected.

Manual usage example:

~~~java
// Snippet inside a method.
IllegalStateException primary =
        new IllegalStateException("primary failure");

primary.addSuppressed(new IOException("cleanup also failed"));

System.out.println(primary.getSuppressed().length); // 1
~~~

This snippet requires importing `java.io.IOException`. `addSuppressed(null)` throws `NullPointerException`; adding a Throwable as suppressed of itself throws `IllegalArgumentException`. `getSuppressed()` returns an array for reading; modifying elements of the returned array is not the way to update the internal suppressed list.

### Is suppressed the same as cause?

No:

- `cause` represents the relationship “exception A was caused by B” or “A wraps B”.
- `suppressed` helps retain “besides A, error C also occurred during processing/cleanup”.
- `getCause()` does not return suppressed exceptions; `getSuppressed()` does not return the cause.
- `printStackTrace()` can display both according to the Throwable's structure.

Do not turn every secondary error into a cause or vice versa just to make logs look shorter. You need to preserve **which error determines the primary failure outcome** and **which errors accompany it**.

## 5. Try-with-resources: The Most Common Place Suppressed Exceptions Appear

`try-with-resources` automatically calls `close()` on resources at the end of the scope. Suppose the `try` body has already thrown exception A, and `close()` also throws exception B. Java keeps A as the **primary exception**, while attaching B to `A.getSuppressed()`.

~~~java
try (SomeResource resource = openResource()) {
    throw new IOException("body failed");
    // When leaving scope, close() is still called.
}
~~~

This is an illustrative snippet; `SomeResource` and `openResource()` need to be defined. If `close()` throws a second IOException, that exception is typically placed in the suppressed list of the error from the `try` body.

Important cases:

| Try body | close() | Result |
|---|---|---|
| Succeeds | Succeeds | No error from these two sources |
| Fails with A | Succeeds | Throws A |
| Succeeds | Fails with B | Throws B as the primary error |
| Fails with A | Fails with B | Throws A; B is suppressed onto A |
| Multiple resources, body fails | Multiple close calls fail | Close failures can be attached as suppressed onto the primary error |
| No body error, multiple close calls fail | Close fails on one or more resources | The error from the first failing close when closing in reverse order is thrown as primary; subsequent close errors can be suppressed |

Java closes resources in **reverse order of declaration**. If `A` is opened then `B`, Java calls `B.close()` before `A.close()`. Do not guess which suppressed exception belongs to which resource solely from array position if you have not verified the closing order and throw sites.

### Compared to a hand-written finally block

The following manual code can let a close error **mask** the original error:

~~~java
// Anti-example. closeResource() may throw.
try {
    readData();             // Throws primary error.
} finally {
    closeResource();        // If this also throws, it may replace the propagating error.
}
~~~

`try-with-resources` handles suppression automatically to preserve the `try` body error when both paths fail. With manual cleanup, if multiple errors must be preserved, you must design an appropriate combination/`addSuppressed` mechanism; do not just call `close` in `finally` and assume all causes are preserved.

## 6. Stack Trace: Execution Trace Attached to a Throwable

`Throwable.getStackTrace()` returns a `StackTraceElement[]` array. An element provides information such as class name, method name, source file, line number (if available), or other frame metadata.

~~~java
// Snippet inside a method; exception has already been created.
StackTraceElement[] frames = exception.getStackTrace();
if (frames.length > 0) {
    System.out.println(frames[0].getClassName());
    System.out.println(frames[0].getMethodName());
}
~~~

A stack trace is usually recorded **when the Throwable object is constructed** via `fillInStackTrace()`, not when any particular caller sees the exception. This is critical when:

- Creating an exception first and throwing it later: the stack may point to the creation site.
- Catching and `throw ex;`: rethrowing the same object usually **does not capture a new stack**.
- Catching and `throw new WrapperException(..., ex);`: the wrapper has a trace at the wrapper creation site; the cause keeps its own trace at the cause creation site.
- An exception travels from a worker via `Future.get()`: the wrapper on the waiting thread and the task error can have **traces on two different threads**.
- The JVM/Throwable may optimize or disable stack traces; the array can be empty, so do not assume `frames[0]` always exists.

`getStackTrace()` does not return a list of other errors. A frame is neither a cause nor a suppressed Throwable; a frame describes a point in the call chain.

### printStackTrace is a broader structured output

`Throwable.printStackTrace()` may print:

~~~text
java.lang.IllegalStateException: operation failed
    at Example.execute(Example.java:...)
Caused by: java.io.IOException: read failed
    at Example.read(Example.java:...)
    Suppressed: java.io.IOException: close failed
        at Example$Resource.close(Example.java:...)
~~~

This is a **reference format diagram**, not the exact output of the code in section 7. In practice, locations and indentation may differ; common frames may be abbreviated as `... N more`. Do not build business parsers based on `printStackTrace()` text.

Use `logger.error("operation failed", ex)` or an equivalent logger API that supports Throwable in production, instead of only `logger.error(ex.getMessage())` which loses cause/suppressed/frames.

## 7. Standalone Java 17 Program Demonstrating All Three

This program intentionally triggers an error in the `try` body and an error during `close`, then wraps the error up to the application layer. Key assertions rely on **type, message, count, and top-of-stack method name**, without depending on line numbers.

Save as **`ThrowableRelationsDemo.java`**:

~~~java
import java.io.IOException;

public class ThrowableRelationsDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static void read() throws IOException {
        try (Resource resource = new Resource()) {
            throw new IOException("read failed");
        }
    }

    static void execute() {
        try {
            read();
        } catch (IOException cause) {
            throw new IllegalStateException("operation failed", cause);
        }
    }

    public static void main(String[] args) {
        try {
            execute();
        } catch (IllegalStateException outer) {
            Throwable cause = outer.getCause();
            Throwable[] suppressed = cause.getSuppressed();

            System.out.println("outer: " + outer.getMessage());
            System.out.println("cause: "
                    + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
            System.out.println("outer suppressed: "
                    + outer.getSuppressed().length);
            System.out.println("cause suppressed: " + suppressed.length);
            System.out.println("suppressed[0]: "
                    + suppressed[0].getClass().getSimpleName()
                    + ": " + suppressed[0].getMessage());

            System.out.println("outer top method: "
                    + outer.getStackTrace()[0].getMethodName());
            System.out.println("cause top method: "
                    + cause.getStackTrace()[0].getMethodName());
            System.out.println("suppressed top method: "
                    + suppressed[0].getStackTrace()[0].getMethodName());
        }
    }
}
~~~

Run with JDK 17+:

~~~bash
javac ThrowableRelationsDemo.java
java ThrowableRelationsDemo
~~~

**Exact stdout of the example when run on a standard JDK with stack traces enabled:**

~~~text
outer: operation failed
cause: IOException: read failed
outer suppressed: 0
cause suppressed: 1
suppressed[0]: IOException: close failed
outer top method: execute
cause top method: read
suppressed top method: close
~~~

### Reading the output

1. `Resource.close()` throws `IOException("close failed")`.
2. `read()` throws `IOException("read failed")` **before** closing, so the body error is the primary error; Java automatically attaches the close error to the suppressed array of the **read error**.
3. `execute()` catches IOException and creates `IllegalStateException("operation failed", cause)`. The wrapper has IOException as its cause, but **does not automatically inherit the cause's suppressed exceptions**. Therefore outer suppressed = 0, cause suppressed = 1.
4. The outer trace starts at `execute`, the body IOException at `read`, and the close IOException at `close`. These are three Throwable objects and three stack traces with different origin sites.
5. You do not need to print `printStackTrace()` to verify the relationships. If printed, the stack will contain `Caused by` and `Suppressed` lines along with file/line info, which depends on source layout.
6. The example uses no threads, network, clock, or filesystem; data and ordering are deterministic. In custom runtimes where stack traces are disabled, direct assertions on `[0]` must be adjusted.

## 8. Quick Reference Table of Key Throwable APIs

| API | Read/Write | Result or note |
|---|---|---|
| `getCause()` | Read | Returns direct cause or `null` |
| `initCause(cause)` | Write once when allowed | Sets cause; do not arbitrarily replace an already-initialized cause |
| `getSuppressed()` | Read | Returns suppressed array; empty array if none |
| `addSuppressed(error)` | Write | Attaches secondary Throwable; forbids `null` and self-suppression |
| `getStackTrace()` | Read | Returns a copy of the frame array; may be empty |
| `setStackTrace(frames)` | Write | Replaces the presented stack trace when writable; use with caution |
| `fillInStackTrace()` | Write | Refreshes trace to current stack if writable; may overwrite original evidence |
| `printStackTrace()` | Display | Prints exception trace along with cause/suppressed in diagnostic format |
| `getMessage()` | Read | Human-readable message; not a default contract error code |
| `getLocalizedMessage()` | Read | May be localized; do not use as machine-readable data |
| `toString()` | Read | Typically combines class name and message; does not replace full stack trace |

### Can you modify the stack trace?

`setStackTrace(StackTraceElement[])` allows replacing the presented trace in Throwables that support a writable stack trace. `fillInStackTrace()` re-captures the current situation. Neither is rarely the right way to "fix" business errors: if used blindly, you can erase the original error-creation site, making investigation harder.

`getStackTrace()` returns an array that should not be treated as shared mutable state. Modifying an element of the returned array is not the way to update a Throwable's stack trace; if you genuinely need to set a trace, you must call the intentional API and understand the consequences.

## 9. Cause Chain Differs from Suppressed List and Trace Frames

The three query operations typically have different shapes.

**Traversing the cause chain:**

~~~java
// Illustrative snippet, exception already exists.
Throwable current = exception;
while (current != null) {
    System.out.println(current.getClass().getSimpleName());
    current = current.getCause();
}
~~~

**Reading suppressed exceptions of a specific Throwable:**

~~~java
for (Throwable extra : exception.getSuppressed()) {
    System.out.println("additional: " + extra.getMessage());
}
~~~

**Reading frames of a specific Throwable:**

~~~java
for (StackTraceElement frame : exception.getStackTrace()) {
    System.out.println(frame.getClassName() + "."
            + frame.getMethodName());
}
~~~

These snippets are illustrative, not standalone programs; they require an `exception` variable and appropriate imports. If you only traverse `getCause()`, you may miss suppressed exceptions. If you only call `getSuppressed()` on the outer wrapper, you may miss suppressed exceptions **on the cause**. If you only inspect the outermost trace, you may see where the wrapper was created without knowing where the original technical error occurred.

In production code with unusual exception structures or reference cycles from integrations, when writing a graph traversal utility, use a visited identity set (e.g., `IdentityHashMap`) and limit depth/node count; do not use an unbounded loop on untrusted input.

## 10. Scenario 1 — Cause Only, No Suppressed

Example:

~~~java
IOException io = new IOException("file not found");
RuntimeException application =
        new IllegalStateException("cannot import", io);
~~~

In this case:

- `application.getCause() == io` is true.
- `application.getSuppressed().length` is usually 0.
- `io.getSuppressed().length` is also usually 0 if nothing else attached one.
- `application.getStackTrace()` is the trace when the wrapper was created.
- `io.getStackTrace()` is the trace when the IOException was created.

If you log only the outermost exception as `application.getMessage()`, you will lose `"file not found"` and the IOException's stack. Always pass the full Throwable to the logger.

## 11. Scenario 2 — Suppressed Present, No Cause

~~~java
IllegalStateException primary =
        new IllegalStateException("commit failed");
primary.addSuppressed(new IOException("rollback failed"));
~~~

Here:

- The cause of `primary` may be `null`.
- Suppressed contains `IOException("rollback failed")`.
- `rollback failed` does not automatically become the root cause of the commit failure; it is a **secondary error** that must be recorded.
- Do not replace `primary` with `new RuntimeException("rollback failed")` and discard the commit error.

The example uses `IOException` so it requires an import in the method/class. When handling real transactions, business logic must design its own compensation/rollback policy; suppressed only stores error information and does not automatically fix data.

## 12. Scenario 3 — Wrapper with a Cause That Has Suppressed Exceptions

This is the exact situation in `ThrowableRelationsDemo`:

~~~text
outer IllegalStateException
  cause -> body IOException
           suppressed[0] -> close IOException
~~~

**Two queries yield different results:**

~~~java
outer.getSuppressed();             // Empty array.
outer.getCause().getSuppressed();  // Contains IOException from close.
~~~

The illustrative snippet requires the `outer` variable as in the full program. Do not copy suppressed exceptions up to outer without a clear reason: doing so can cause a close error to appear **twice** when a logger traverses both outer and cause. Having the wrapper keep the `cause` reference intact is sufficient to preserve the underlying metadata.

In logs, `printStackTrace()` traverses both cause and the cause's suppressed exceptions. Common loggers with Throwable support typically also display the error tree; verify your specific backend configuration if output is missing suppressed info.

## 13. Scenario 4 — Multiple Resources Closed in Reverse Order

Given:

~~~java
try (ResourceA a = new ResourceA();
     ResourceB b = new ResourceB()) {
    doWork();
}
~~~

Java closes `b` before `a`. If `doWork()` throws A, `b.close()` throws B, and `a.close()` throws C:

~~~text
Primary: A (doWork)
  suppressed[0]: B (b.close)
  suppressed[1]: C (a.close)
~~~

This is a logical model assuming both close calls throw. Do not rely on suppressed ordering to infer causal relationships between B and C; the order reflects how Java closes resources.

If the body does not throw and `b.close()` throws B, error B can be primary; the error from `a.close()` is suppressed onto B. Changing resource declaration order can change close order, but you should not rearrange resources just to make exception output look nicer.

### Keeping resource-opening errors separate

If a constructor or initialization expression of a resource in the declaration list throws an error, Java must still close resources **that were previously opened successfully** according to try-with-resources rules. Close errors during cleanup of those resources can be suppressed onto the initial initialization exception. This is also why cleanup tests need to cover errors both during opening and in the try body.

## 14. Scenario 5 — Exceptions Crossing Future and CompletableFuture

A worker throws an error and the caller receives a wrapper exception:

~~~java
// Snippet; pool is an ExecutorService.
Future<String> future = pool.submit(() -> {
    throw new IOException("read failed");
});

try {
    future.get();
} catch (ExecutionException ex) {
    Throwable original = ex.getCause();
}
~~~

This snippet requires imports and handling `InterruptedException`, or placing it in a method declaring `throws InterruptedException`. `ExecutionException` acts as a **wrapper**, holding the exception from the task as its cause. The worker error is not "thrown" directly on the waiting thread's call stack; the caller receives the error channel via `Future.get()`.

With `CompletableFuture.join()`:

~~~java
// Snippet:
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(new IOException("disk failed"));

try {
    failed.join();
} catch (CompletionException ex) {
    Throwable cause = ex.getCause();
}
~~~

In normal exceptional completion, `join()` throws `CompletionException` containing the cause; a cancelled future can throw `CancellationException` directly. Do not treat the new wrapper as the original technical error or assume suppressed exceptions are on the wrapper.

When a task has a suppressed resource-close exception before being wrapped, inspect suppressed **on the Throwable originating in the task**, i.e., on the cause or a deeper cause. Do not treat the `ExecutionException` stack trace on the caller as evidence that the I/O error occurred on the waiting thread.

## 15. Scenario 6 — Logging and Serialization Losing Metadata

An anti-pattern:

~~~java
catch (Exception ex) {
    logger.error(ex.getMessage());
    throw new IllegalStateException("failed");
}
~~~

This snippet is illustrative only; `logger` is the application logger. Here:

- The logger may only record text, without stack/cause/suppressed.
- The new wrapper does not keep `ex` as its cause.
- Investigators cannot recover the resource-closing error or the original error site from just the string `"failed"`.

How to preserve metadata:

~~~java
catch (Exception ex) {
    throw new IllegalStateException("operation failed", ex);
}
~~~

If this layer only rethrows, it does not necessarily need to log here. Log once at the responsible boundary, using a logger API that accepts both `Throwable` and context such as operation/request ID. Avoid printing raw messages containing secrets or personal data into public responses.

### JSON log data does not automatically preserve the Throwable tree

A JSON event like:

~~~json
{
  "exceptionType": "IllegalStateException",
  "message": "operation failed",
  "requestId": "req-15"
}
~~~

is an illustrative log that **does not** yet contain cause, suppressed, and stack frames. If the system needs investigation capabilities, the logger/serializer must explicitly include fields/renderers for those structures, or store a trace ID linked to the full error. Do not claim "the Throwable was logged" if in practice only `getMessage()` was serialized.

## 16. Testing the Three Relationships Separately

A test suite should verify:

| Goal | Recommended assertion | What to avoid |
|---|---|---|
| Wrapper has the right cause | `assertSame(original, wrapper.getCause())` | Comparing messages only |
| Cause is not lost across layers | `assertInstanceOf(IOException.class, wrapper.getCause())` | Wrapping and dropping the cause |
| Suppressed of try-body error | `assertEquals(1, cause.getSuppressed().length)` | Checking suppressed on the wrapper and assuming there are none |
| Close error type | `assertInstanceOf(IOException.class, suppressed[0])` | Parsing `printStackTrace()` to get the subtype |
| Stack trace has frames | Check array is non-empty when test environment guarantees support | Hard-coding source line numbers |
| Wrapper and cause traces differ | Verify top methods like `execute` and `read` in the demo | Treating stack as just a cause chain |
| Multiple close failures | Verify corresponding suppressed order and count | Counting suppressed errors as two independent failed operations |
| Rethrowing same Throwable | Verify identity/cause per contract | Expecting stack to auto-update at every `throw` |
| Error only occurs in close | `getSuppressed()` may be empty; close failure is primary | Assuming every close failure is suppressed |
| Logger | Ensure cause and suppressed rendering per backend | Testing logic via regex on dynamic log text |

### Sample JUnit 5 test

JUnit 5 requires an external dependency outside the JDK. The following example can be placed in the same default package as `ThrowableRelationsDemo` in a test project:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.io.IOException;
import org.junit.jupiter.api.Test;

class ThrowableRelationsDemoTest {
    @Test
    void causeHoldsBodyFailureAndSuppressedHoldsCloseFailure() {
        IllegalStateException outer = assertThrows(
                IllegalStateException.class,
                ThrowableRelationsDemo::execute);

        Throwable cause = outer.getCause();
        assertInstanceOf(IOException.class, cause);
        assertEquals("read failed", cause.getMessage());

        assertEquals(0, outer.getSuppressed().length);
        assertEquals(1, cause.getSuppressed().length);
        assertInstanceOf(IOException.class, cause.getSuppressed()[0]);
        assertEquals("close failed",
                cause.getSuppressed()[0].getMessage());

        assertEquals("execute",
                outer.getStackTrace()[0].getMethodName());
        assertEquals("read",
                cause.getStackTrace()[0].getMethodName());
        assertEquals("close",
                cause.getSuppressed()[0].getStackTrace()[0].getMethodName());
    }
}
~~~

**Stack trace test condition:** this example uses default Throwables with writable stack traces on a standard JVM. If a framework is configured to disable stack traces or reuse stackless exceptions, do not use hard assertions on `getStackTrace()[0]` in all cases; testing cause and suppressed metadata can remain independent of the trace.

## 17. Commonly Confused Questions — Quick Answers

**Q1. Is cause always the first error chronologically?** Not necessarily. Cause is a relationship set by API/developers to express causality/layer translation; chronological order is only one factor.

**Q2. Is suppressed a separate Exception type?** No. They are `Throwable` objects attached to another Throwable; their subtypes can still be IOException, SQLException, RuntimeException, or others.

**Q3. Can a single Throwable have both cause and suppressed?** Yes. The three metadata groups coexist independently.

**Q4. Does `throw ex;` automatically create a new stack trace?** Usually no. It rethrows the same object; the trace was recorded when the object was created or when `fillInStackTrace()` was called.

**Q5. Does `getCause() == null` mean the error had no underlying reason?** It only means no cause was attached for the caller to read. You cannot infer that no actual cause existed in the system.

**Q6. Does `getSuppressed().length == 0` mean there were no cleanup errors?** Not necessarily. Cleanup may have succeeded, an error may have been dropped/masked, suppression may be disabled, or the error may sit on another Throwable in the cause chain.

**Q7. Does `getStackTrace().length == 0` mean the exception is not real?** No. A stack trace can be empty/disabled due to configuration, constructor, or runtime specifics.

**Q8. Should tests rely on line numbers in stack traces?** No. Refactoring even a few lines changes line numbers; check error type, cause/suppressed, and meaningful frames if needed.

**Q9. Does `printStackTrace()` display suppressed exceptions?** For standard `Throwable`, yes, including suppressed and cause branches. Custom loggers/JSON serializers may format differently or omit them if misconfigured.

**Q10. Does a suppressed close IOException need to be handled?** It can be very important, especially if `close` flushes data or commits a buffer. Suppressed does not mean it can be ignored.

**Q11. When wrapping a new cause, do I need to copy all suppressed exceptions to the wrapper?** Usually no. The cause retains its own suppressed exceptions; copying can create duplicate reports.

**Q12. Is an error in finally automatically suppressed?** Not by default. `try-with-resources` has special suppression rules; a manual `finally` can replace the earlier error if it throws.

## 18. Common Mistakes and How to Fix Them

1. **Logging only `ex.getMessage()`:** loses stack/cause/suppressed. → Pass the Throwable to the logger.
2. **Wrapping an error without cause:** creates a new exception without `ex`. → Use a constructor that accepts `Throwable cause`.
3. **Equating suppressed with cause:** mistaking a close failure for the root cause. → Distinguish primary/secondary relationships.
4. **Calling only `outer.getSuppressed()`:** misses suppressed on the cause. → Inspect the right Throwable node.
5. **Parsing `printStackTrace()` text as business data:** depends on dynamic formatting. → Use typed APIs and error codes.
6. **Assuming `throw ex;` adds a new frame:** confuses creation site with rethrow site. → Understand the Throwable lifecycle.
7. **Creating exceptions early and reusing them everywhere:** trace/context can be stale. → Create errors at meaningful locations, do not reuse arbitrarily.
8. **Calling `fillInStackTrace()` to "update" every rethrow:** can erase evidence of the original error site. → Only use if there is a clear technical requirement.
9. **Using `finally` that throws a close error without preserving the body error:** masks the primary failure. → Use try-with-resources or design manual suppression.
10. **Ignoring resource suppressed exceptions:** cleanup errors become invisible. → Test failures in both body and close.
11. **Collapsing all Throwables into a single root cause:** loses wrappers containing context/domain info. → Preserve the full chain.
12. **Logging the same exception at multiple layers and rethrowing:** multiplies one incident into multiple ERRORs. → Establish responsible logging boundaries.
13. **Assuming a future wrapper has the worker trace:** wrapper and cause traces originate in different contexts. → Read cause/stack on the right node.
14. **Attaching suppressed to an unrelated exception:** corrupts causal relationships. → Only attach secondary errors from the same operation/cleanup.
15. **Not handling null/empty in Throwable-reading utilities:** `getCause()` can be null, suppressed/trace arrays can be empty. → Check bounds and limit traversal.
16. **Exposing stack traces in public responses:** can leak code, paths, libraries, and sensitive info. → Return safe error codes/request IDs; keep traces in internal channels.

## 19. Checklist for Investigating Java Exceptions

When opening a log event or an error reported from a thread/future:

1. Identify the **outermost Throwable** and the associated operation/request/task.
2. Record the exception type and message, but do not automatically treat the message as an error code.
3. Read `getCause()` to see which error was wrapped; iterate along the chain **in a controlled way** if needed.
4. On **every Throwable**, check `getSuppressed()` — not just on the wrapper.
5. On each important node, inspect `getStackTrace()` to locate where the Throwable was created.
6. Distinguish **try-body failures** from **close/cleanup failures**.
7. If the error came through `Future.get()`/`join()`, separate the completion wrapper from the task error.
8. If multiple suppressed exceptions are present, check resource count, close order, and which secondary operations failed.
9. Check exception contracts across application layers: was the type changed, cause dropped, or message copied?
10. Do not conclude that rollback or resource cleanup completed just because an exception was thrown and suppressed.
11. When logging, keep the full Throwable and include permitted operation, error code, and request/business IDs.
12. Test for exact type/cause/suppressed; do not hard-code stack trace text or line numbers.

## 20. Conclusion

The distinction between **cause, suppressed, and stack trace** comes down to three questions:

- **Cause** (`getCause()`): *Which error is attached as the underlying cause of the current error?*
- **Suppressed** (`getSuppressed()`): *Which secondary errors were retained alongside the primary error, especially when cleanup/close failed?*
- **Stack trace** (`getStackTrace()`): *What call trace was recorded for this Throwable object itself?*

These three pieces of information do not replace one another. An outer exception can have a cause, that cause can have suppressed exceptions, and all three Throwables can have separate stack traces. Writing proper Java means **preserving causes when wrapping errors, respecting suppression in try-with-resources, and using stack traces for investigation rather than as business data**.

### References

- [Java SE 17 — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html)
- [Java SE 17 — StackTraceElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackTraceElement.html)
- [Java Language Specification `14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3)
- [Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html)
- [Java SE 17 — ExecutionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html)
- [Java SE 17 — CompletionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html)
