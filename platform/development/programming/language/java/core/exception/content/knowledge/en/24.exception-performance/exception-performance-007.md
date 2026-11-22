# Risks of Sharing Exceptions with Mutable Cause or Suppressed Exception Information

In Java, an exception (`Throwable`) is not just a class name and a message. It can also carry a **cause**, **suppressed exceptions**, and a **stack trace**. This information helps diagnose incidents, but it also makes an exception object a container of **mutable state**. If you reuse *the same exception object* across multiple requests, retries, or threads, data from one incident can leak into another.

For example, request A and request B share a `static final RuntimeException`. When A adds a resource-closing exception via `addSuppressed(...)` and B records another resource-closing error on **the same object**, the logs for A or B may show both errors. If one thread calls `fillInStackTrace()` to "update" the throw site, the shared stack trace may change right before another thread writes the log. Even though individual operations may have internal synchronization guards, **the ownership of error context across tasks is still wrong**.

This article explains which parts of a `Throwable`'s state can change, how `initCause()` restricts setting the cause, why suppressed exceptions easily accumulate, the impact of sharing across threads, and how to isolate errors while still considering performance.

## 1. Mental Model: Each Failure Should Have Its Own Error Context

An exception used to report a specific incident typically associates the following information:

- **Primary error**: which operation failed and a message appropriate for that incident.
- **Cause**: the lower-level exception object that caused or is used as the cause of the primary error.
- **Suppressed exceptions**: additional errors that need to be preserved, such as `close()` failing after the `try` body has already thrown the primary error.
- **Stack trace**: the recorded call stack location of the exception object, typically from the time of instantiation.
- **Observability context**: request ID, task, timestamp, and handling logger, which sometimes live outside `Throwable`.

Two independent requests, even if they fail with the same kind of error, should have **two distinguishable incident records**. Having the same exception type does not mean you must use the same object.

```text
Request A
  -> Exception A
       cause      -> IOException A
       suppressed -> CleanupException A
       stack      -> location where A occurred

Request B
  -> Exception B
       cause      -> IOException B
       suppressed -> CleanupException B
       stack      -> location where B occurred
```

If a shared `Exception S` is used:

```text
Request A ------+
                +--> Exception S
Request B ------+       |
                        +--> cause: only one cause can be set
                        +--> suppressed: secondary errors from both A and B
                        +--> stack: shared creation site or a site recorded later
```

When reading a log record, you can no longer be sure which data truly belongs to the incident being reported if the application keeps adding to or modifying shared information.

## 2. What State Does a `Throwable` Contain?

| Property | Related API | How can it change? | Risk when shared |
| --- | --- | --- | --- |
| Message | `getMessage()` | `Throwable`'s message is usually set in the constructor; subclasses may provide their own state | A fixed message does not describe individual requests |
| Cause | `getCause()`, `initCause(Throwable)` | If not yet initialized, `initCause` allows setting it **once** | The first thread/request claims the right to set it; the rest cannot set their own cause |
| Suppressed | `addSuppressed(Throwable)`, `getSuppressed()` | Multiple secondary exceptions can be added when suppression is enabled | The list keeps accumulating errors from different incidents |
| Stack trace | `fillInStackTrace()`, `getStackTrace()`, `setStackTrace(...)` | Can be re-recorded or modified if writable stack trace is enabled | The stack seen at log time may not reflect where the current request failed |
| Extra fields in subclasses | Custom class getters/setters | Depends on the exception class design | Races, stale data, or overwritten data across threads |

**Key point:** `static final Exception ERROR = ...` only prevents **the `ERROR` reference from being reassigned to another object**; it does not make the state of the `Throwable` object immutable.

A `throw ERROR;` statement does not automatically create a new object either. Two throws can pass **the exact same reference** through `catch` blocks.

## 3. `initCause()` Only Sets the Cause Once

Some `Throwable` constructors allow setting the cause at creation time:

```java
new IllegalStateException("Cannot process order", originalError);
```

This is an illustrative snippet with an existing `originalError` variable of type `Throwable`. This approach sets the cause right when creating the object and is usually appropriate when translating a low-level error into a domain-meaningful layer.

`Throwable.initCause(cause)` serves exception classes that were constructed **without a cause assigned**. However:

1. The cause can only be set once. After a successful call, subsequent `initCause(...)` calls throw `IllegalStateException`.
2. Even if the constructor initialized the cause to `null`, `initCause` may still be disallowed because the cause is already considered initialized.
3. `initCause(this)` is rejected because a throwable cannot be its own direct cause.
4. `initCause` **is not a setter to swap the cause per request**. Do not reuse the same exception expecting each failure to get a new `getCause()`.

Illustrative example inside a method:

```java
Exception shared = new Exception("shared");
shared.initCause(new java.io.IOException("request A"));

try {
    shared.initCause(new java.io.IOException("request B"));
} catch (IllegalStateException rejected) {
    System.out.println("Cause was already initialized");
}
```

After the branch above, `shared.getCause()` still refers to the `"request A"` error. If request B uses `shared` to report a failure, someone reading the logs might think A's error caused B's failure.

Java has synchronization for one-time cause initialization, but "only one thread wins" does not make sharing business-correct. With two concurrent threads, whichever thread happens to set the cause first should not be what determines diagnostic data.

## 4. `addSuppressed()` Can Mix Errors from Multiple Tasks

`Throwable.addSuppressed(Throwable)` is designed to **preserve secondary errors related to the same primary failure**, commonly occurring in `try-with-resources`. For example, if the `try` body throws `IOException("read failed")` and `close()` also throws `IOException("close failed")`, Java keeps the read error as the primary exception and attaches the resource-closing error as a suppressed exception.

That does **not** mean `addSuppressed` is a data store for multiple requests to share. If A and B both hold the same throwable and call in turn:

```java
shared.addSuppressed(new java.io.IOException("cleanup of A"));
shared.addSuppressed(new java.io.IOException("cleanup of B"));
```

then `shared.getSuppressed()` can contain **both**. This snippet illustrates the consequence of misusing a shared `Throwable`, not a design to follow.

`addSuppressed` supports thread-safe usage at the individual add-operation level, but **it does not group suppressed exceptions by request**. `getSuppressed()` returns a snapshot array at the time of the call; a later read may contain additional elements. The insertion order under concurrent threads is not a reliable way to determine which request happened first.

In addition, `addSuppressed(null)` and `addSuppressed(this)` are invalid cases; Java rejects them instead of recording them in the list as usual. A throwable created with `enableSuppression=false` will not record suppressed exceptions, even if code attempts to add them. Disabling suppression to reduce overhead is a **diagnostic data trade-off**, not a fix for mixing requests.

## 5. Java 17+ Example: A Shared Exception Accumulating Context from Two Threads

This example uses two different threads that intentionally add secondary errors from two tasks to a shared `Throwable`. For deterministic output, the program waits for both threads to finish and sorts the error names before printing; the actual insertion order does not need to be fixed. This is a **counterexample demonstration** to understand the risk.

Create the file **`SharedThrowableRiskDemo.java`**:

```java
import java.io.IOException;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;

public class SharedThrowableRiskDemo {
    private static final IllegalStateException SHARED = createShared();

    private static IllegalStateException createShared() {
        return new IllegalStateException("shared failure");
    }

    private static void addCleanupFailure(
            String request, CountDownLatch start) {
        try {
            start.await();
            SHARED.addSuppressed(
                    new IOException("cleanup " + request));
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("createdAt="
                + SHARED.getStackTrace()[0].getMethodName());

        SHARED.initCause(new IOException("backend A"));
        boolean secondCauseRejected = false;
        try {
            SHARED.initCause(new IOException("backend B"));
        } catch (IllegalStateException expected) {
            secondCauseRejected = true;
        }

        CountDownLatch start = new CountDownLatch(1);
        Thread a = new Thread(() -> addCleanupFailure("A", start));
        Thread b = new Thread(() -> addCleanupFailure("B", start));
        a.start();
        b.start();
        start.countDown();
        a.join();
        b.join();

        String contexts = String.join(",",
                Arrays.stream(SHARED.getSuppressed())
                        .map(Throwable::getMessage)
                        .sorted()
                        .toList());

        System.out.println("secondCauseRejected="
                + secondCauseRejected);
        System.out.println("cause=" + SHARED.getCause().getMessage());
        System.out.println("suppressedCount="
                + SHARED.getSuppressed().length);
        System.out.println("suppressedContexts=" + contexts);

        SHARED.fillInStackTrace();
        System.out.println("refreshedAt="
                + SHARED.getStackTrace()[0].getMethodName());
    }
}
```

Compile and run:

```bash
javac --release 17 SharedThrowableRiskDemo.java
java SharedThrowableRiskDemo
```

Output:

```text
createdAt=createShared
secondCauseRejected=true
cause=backend A
suppressedCount=2
suppressedContexts=cleanup A,cleanup B
refreshedAt=main
```

Meaning of each result:

- `SHARED` was created by `createShared()`. The initial stack trace records the object's creation site, even though the object is later reused from multiple places.
- `initCause` sets `"backend A"` successfully; attempting to set `"backend B"` is rejected. The remaining cause **does not reflect** request B.
- Two independent threads add two errors `cleanup A` and `cleanup B`; a log entry printing the entire shared exception may include both. Internal synchronization on the add operation cannot fix the problem of **mixed business contexts**.
- `fillInStackTrace()` in `main` replaces the stack information of **the shared object itself**. If another thread is preparing to log it, the presented data can vary depending on when it is observed.

In practice, resource-closing errors should be attached to the primary exception **of the exact operation that owned that resource**. The example intentionally puts them into a shared object to demonstrate why such reuse is dangerous.

## 6. `fillInStackTrace()` and `setStackTrace()` Break Incident Localization

By default, a `Throwable` records its stack trace at creation time. If you create a shared exception at application startup and rethrow it at multiple sites, the stack trace may continually point to initialization code rather than where the error actually occurred.

Some code tries to "fix" this by calling:

```java
shared.fillInStackTrace();
throw shared;
```

This is an illustrative snippet inside a method that has a `shared` variable. `fillInStackTrace()` re-records stack information on **the same object** when the stack trace is writable. If thread A calls it first and thread B calls it afterward, A does not have its own copy to preserve its trace: the shared stack may already be overwritten by B before it is formatted or analyzed.

`setStackTrace(StackTraceElement[])` can also alter how the stack is displayed for a throwable with a writable stack trace. Modifying the stack to make an incident look like it originated elsewhere is especially dangerous during troubleshooting. You should not "tag a request" by editing the stack of a shared error.

`getStackTrace()` returns a **copy array** of stack elements, so modifying an element in the returned array does not automatically update the stack stored inside `Throwable`. However, that does not make the `Throwable` object itself immutable: the stack-updating APIs still exist, and each read may observe a different state after another thread mutates it.

Whether a logger captures the stack at call time or formats it lazily depends on the backend/formatter. If asynchronous logging is used, you should rely even less on a shared `Throwable` that continues to be mutated after the log call always appearing with its state at the exact time of logging.

## 7. Method-Level "Thread-Safety" Does Not Guarantee Correct Context

It is important to distinguish two questions:

1. **Operation-level data safety:** when two threads concurrently add suppressed exceptions, is the internal storage structure corrupted?
2. **Business correctness:** do those errors belong to the same primary incident and the same diagnostic report?

An API can have internal synchronization and still be wrong if the application lets two threads **co-own** a context-carrying object. Java does not automatically know that `IOException("cleanup A")` belongs to request A and `IOException("cleanup B")` belongs to request B. Nor can a logger split them into two accurate incidents based solely on the `getSuppressed()` of a shared object.

Example of a sequence of operations that an application might think is "consistent":

```text
Thread A: prepares to log for request A
Thread B: adds suppressed exception for request B
Thread A: reads getCause and getSuppressed and writes log
Thread B: calls fillInStackTrace
Thread A: formats stack frames
```

There is no **atomic** business snapshot covering all cause, suppressed, stack, extra message, and request metadata fields. Moreover, when the cause object (`getCause()`) is also shared and mutated, even a fresh wrapper exception for request A can point to data that does not belong to A.

**Design takeaway:** thread safety does not replace the rule that **each failure needs its own context and ownership**.

## 8. Proper Design: Create a Separate Exception for Each Incident

Normally, an operation that catches a root error creates an exception meaningful at its layer and **preserves the cause directly in the constructor**:

```java
try {
    storage.save(order);
} catch (java.io.IOException cause) {
    throw new IllegalStateException(
            "Cannot save order " + order.id(), cause);
}
```

This is an **illustrative snippet** inside a method with appropriate `storage`, `order`, and return/source types; it is not a standalone program. Each execution of the `catch` block creates a new `IllegalStateException`, linked to the `IOException` of that specific save operation.

If secondary errors need to be recorded, attach them to **the primary exception of the same execution**, or let `try-with-resources` apply the proper suppressed exception rules:

```java
try (Resource resource = openResource()) {
    resource.process();
}
```

This illustrative snippet requires the application's `Resource`, `openResource`, and `process` classes/methods. When both the `try` body and `close()` throw, Java preserves the primary exception and adds the resource-closing error as suppressed. Never use a global throwable as a sink for resource-closing errors from all requests.

### Java 17+ Example: Two Requests with Independent Error Objects

Create the file **`IsolatedThrowableDemo.java`**:

```java
import java.io.IOException;

public class IsolatedThrowableDemo {
    private static IllegalStateException fail(String request) {
        IOException cause = new IOException("storage " + request);
        IllegalStateException error = new IllegalStateException(
                "request " + request + " failed", cause);
        error.addSuppressed(new IOException("cleanup " + request));
        return error;
    }

    public static void main(String[] args) {
        IllegalStateException a = fail("A");
        IllegalStateException b = fail("B");

        System.out.println("differentErrors=" + (a != b));
        System.out.println("differentCauses="
                + (a.getCause() != b.getCause()));
        System.out.println("messageA=" + a.getMessage());
        System.out.println("causeA=" + a.getCause().getMessage());
        System.out.println("causeB=" + b.getCause().getMessage());
        System.out.println("suppressedA="
                + a.getSuppressed()[0].getMessage());
        System.out.println("suppressedB="
                + b.getSuppressed()[0].getMessage());
    }
}
```

Compile and run:

```bash
javac --release 17 IsolatedThrowableDemo.java
java IsolatedThrowableDemo
```

Output:

```text
differentErrors=true
differentCauses=true
messageA=request A failed
causeA=storage A
causeB=storage B
suppressedA=cleanup A
suppressedB=cleanup B
```

When separate objects are used, A's context is not appended to by B. The example above **simulates** a cleanup error using `addSuppressed` to verify isolation; it does not mean every exception should manually add suppressed errors. In a real application, a suppressed exception is only appropriate when it is genuinely a secondary error of the primary failure.

This approach has allocation and stack-collection costs, but that is precisely the data needed to trace a real incident. If the error volume is too high, investigate what is causing abnormal failures and measure performance before deciding to discard diagnostic data.

## 9. Indirect Sharing Cases to Watch Out For

### 9.1. New Wrapper, Shared Cause Object

Example:

```java
static final java.io.IOException SHARED_CAUSE =
        new java.io.IOException("upstream unavailable");

RuntimeException a =
        new IllegalStateException("request A failed", SHARED_CAUSE);
RuntimeException b =
        new IllegalStateException("request B failed", SHARED_CAUSE);
```

This is an **illustrative snippet belonging to a class/method declaration**, not a standalone program. `a != b`, yet `a.getCause() == b.getCause()`. If `SHARED_CAUSE` has suppressed exceptions or a modified stack, all wrappers reference that same information.

There are cases where a single root incident genuinely affects multiple operations—for example, system startup fails and multiple threads receive the same cause. Sharing a **reference** then may reflect the real relationship, but you must clearly design **who owns it and whether the cause may still be mutated**. If each request fails independently, do not share a global cause.

### 9.2. Exception Caching or Singletons for "Optimization"

Using `static final Exception FAILURE = new Exception("failed")` saves object creation on subsequent calls, but comes with a stack trace at the initial creation site and the risk of secondary error information mixing together. You must weigh the cost separately based on incident frequency, diagnostic context, and the need to preserve stack/cause.

Some systems may use a **lightweight signal object with a very narrow contract** that carries no request context and disables both stack recording and suppression:

```java
final class FixedSignal extends RuntimeException {
    FixedSignal() {
        super("fixed signal", null, false, false);
    }
}
```

This is only an **illustrative class declaration**, not a standalone program. The four-argument constructor sets the cause to `null` and disables suppression and writable stack trace. If you reuse an object of this class as an internal control signal, make sure not to add mutable state in subclasses, do not use it to report errors that need a real stack, and document the usage boundaries. This is an intentional design exception, not the default for all failures.

Even with this kind of signal, using a result type/enum or normal control flow is usually clearer when the situation is truly an expected state. Do not use exceptions as general control flow just because you disabled the stack trace.

### 9.3. `ThreadLocal<Throwable>` Does Not Necessarily Solve the Problem

A separate throwable per `Thread` can avoid **two threads concurrently mutating the same object**, but executor threads are typically reused across sequential requests. If the context is not recreated/reset properly, suppressed exceptions and the cause from an old request still remain. `ThreadLocal` also carries the risk of retaining data across a worker's lifetime and increasing memory usage if not cleaned up in the right place.

Therefore, "one exception per thread" is still different from "one exception per failure". Error ownership should be tied to the **incident/operation**, not implicitly tied to the lifetime of a thread.

## 10. Impact on Logging, Error Tracking, and Security

When a logger receives a full `Throwable`, the backend can typically record the exception class name, stack trace, `Caused by:`, and `Suppressed:`. That is a diagnostic advantage, but it exposes the effects of a shared object even more clearly.

- **Wrong-request logs:** secondary errors from B appear in request A's logs, causing confusion or leading on-call engineers down the wrong trail.
- **Stale or altered stack traces:** the stack points to singleton initialization code, or to the thread that just called `fillInStackTrace()`, rather than where the error actually originated for the record being viewed.
- **Inconsistent diagnostics:** the same throwable reference logged at two different times may display different numbers of suppressed exceptions.
- **Cross-user data exposure risk:** if the message/cause/suppressed contains request-specific data, sharing can cause one user's details to appear in a log record associated with another user. Avoid putting secrets into exception messages in the first place.
- **Incorrect error grouping:** error-tracking systems may rely on the stack and exception type to group incidents; a shared or mutated stack makes error grouping less accurate.

To reduce risk, log at clear responsibility boundaries, pass **the incident's own exception object** along with a safe correlation ID, preserve the cause when wrapping errors, and avoid unnecessarily logging the same stack trace multiple times. Using asynchronous logging does not make a shared object immutable.

Do not create a new exception **just to copy the message** and drop the cause: `new IllegalStateException(shared.getMessage())` loses the real cause context. If you truly need a new exception, take the *actual cause of the operation* and pass it to the appropriate constructor. A cause that has already been shared should still be carefully evaluated before being referenced.

## 11. Performance: How Should the Error Path Be Optimized?

The risk of sharing throwables often arises from trying to save on exception creation and stack trace capture. Trade-offs should be analyzed at the system level:

| Option | Potential benefit | Key drawback |
| --- | --- | --- |
| Create a new exception per failure | Isolated context/cause/suppressed/stack | Allocation and stack-capture cost |
| Use a singleton throwable with stack | Reduces new object allocations | Stale stack, shared mutable state, hard-to-trace logs |
| Singleton signal without stack/suppression, no context | Can reduce overhead under a special internal contract | No stack; easily misused for real failures |
| Structured result for normal states | No exception created on expected branches | Requires explicit API design, calling, and result checking |
| Log rate-limiting/sampling, metric tracking | Reduces duplicate logging load | Must still retain enough diagnostics for investigable errors |

When a type of error occurs at high frequency, the first question should be: **is this truly an exception, or a frequent outcome according to the API contract?** If not finding a target is an expected condition, `Optional`, an enum, or a result type may be more appropriate than repeatedly throwing exceptions.

If you still must use exceptions, measure on the target JDK, realistic load, and stack depth. Java Microbenchmark Harness (JMH) is useful for measuring exception creation cost; profilers and metrics help identify impact on CPU, allocation, GC, and logging. Do not conclude from a single benchmark that dropping stack traces for all errors is safe.

In particular, `Throwable.addSuppressed` can cause a long-lived shared object to accumulate more and more references to secondary exceptions and related objects. This creates a risk of **retaining memory longer than necessary**, in addition to diagnostic bugs. Never use the suppressed list as an unbounded incident history.

## 12. Code Review Checklist

When you find a `Throwable` used across multiple requests or threads, check:

1. Is the object created **per failure**, per thread, or once in a `static final`/cache?
2. Is the cause set at creation time? Does any code call `initCause` for different requests?
3. Does `addSuppressed` only receive secondary errors belonging to **the same operation**, or does it mix data from multiple tasks?
4. Does any place call `fillInStackTrace()` or `setStackTrace(...)` on a shared object?
5. Can the logger format the event after another thread has mutated the throwable? The backend's behavior should be verified.
6. Is a new wrapper holding a reference to a **mutable global cause**?
7. Is there a cache/`ThreadLocal` causing error state to outlive a single operation?
8. Can exceptions for expected situations be replaced with a result type, or can logging be rate-limited instead of using a singleton throwable?
9. If intentionally using a stackless throwable signal, does the contract truly guarantee it contains no request context or data needed for investigation?
10. In the worst case, could one user's log contain information from another user?

## 13. Self-Check Questions

**Q1.** Does `static final RuntimeException SHARED = new RuntimeException("failed");` mean the object cannot be modified?  
**A:** No. `final` only fixes the field's reference. `Throwable` still has state such as an uninitialized cause, the suppressed list, and the stack trace that the API allows updating.

**Q2.** Two requests both call `shared.addSuppressed(...)`; since the method supports synchronization, is the data kept separate?  
**A:** No. The list still belongs to **the same object**; synchronizing the operation does not automatically partition elements by request.

**Q3.** After calling `initCause(causeA)` successfully, can you call `initCause(causeB)` to replace the cause?  
**A:** No. The second call is rejected with `IllegalStateException`.

**Q4.** Does rethrowing the same exception from two methods automatically create two independent stack traces?  
**A:** No. It is still one object. If you call `fillInStackTrace`, you update the stack attached to the shared object, rather than creating a separate copy.

**Q5.** Do two wrappers `new IllegalStateException("A", common)` and `new IllegalStateException("B", common)` have different causes?  
**A:** No. They are separate wrapper objects, but they still hold **the same reference** `common`; if it carries mutable data, both see it.

**Q6.** `getSuppressed()` returns a separate array, so is `Throwable` immutable?  
**A:** No. The returned array is a snapshot at the time of the call; another thread can still add suppressed exceptions to the original object.

**Q7.** Does switching from a singleton throwable with a stack to a stackless singleton solve all risks?  
**A:** No. It removes one source of diagnostic state, while also losing the ability to locate where the error occurred. Only consider it for an internal signal that carries no request context, has a clear contract, and has been measured.

**Q8.** What is the standard safe approach when two requests fail independently?  
**A:** Create a separate exception for each incident, pass the incident's own cause in the constructor, only attach suppressed exceptions that genuinely belong to that incident, and log with an appropriate correlation ID.

## 14. API References

- [Java 17 — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `initCause`, `addSuppressed`, `getSuppressed`, `getStackTrace`, `fillInStackTrace`, and constructors controlling suppression/stack trace.
- [Java 17 — `RuntimeException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html): constructors for setting cause, suppression, and writable stack trace.
- [Java 17 — `AutoCloseable` and `try-with-resources`](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html): examples of primary exceptions and suppressed exceptions when closing resources.

**Remember:** a `Throwable` is **an object with diagnostic state**, not just an immutable error code. `initCause` does not allow changing the cause arbitrarily; suppressed exceptions can accumulate; stack traces can be updated. Reusing this object across independent incidents easily mixes data and makes logs misleading. Prefer **one exception per incident**, preserve the right cause, use suppressed exceptions according to true secondary-error relationships, and optimize the error path based on real measurements.