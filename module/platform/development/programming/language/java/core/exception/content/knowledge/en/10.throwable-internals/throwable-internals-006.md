# fillInStackTrace and the Impact of Updating the Stack Trace in Java

> **Java Core – Exception** · Group: **Throwable Object** · Examples use Java 17 or later.

## 1. The Problem: What Point in Time Does a Throwable's Stack Trace Represent?

When Java raises an error, the exception object typically carries information about the **call stack** (*stack trace*), helping trace the methods that were executing at a given point in time. For example, part of a trace looks like:

~~~text
java.lang.IllegalStateException: service unavailable
    at Example.makeFailure(Example.java:12)
    at Example.main(Example.java:20)
~~~

The lines above are only **format illustrations**, not fixed output of the program in this lesson. Actual file names, line numbers, frames, and display depend on the program, compiler, and JVM.

In Java, a `Throwable` object normally records stack trace information at the time **it is created**, because most standard constructors call `fillInStackTrace()`. When rethrowing **the same instance** later, the `throw ex;` statement does not automatically re-record the current trace for that object.

If the developer explicitly calls:

~~~java
ex.fillInStackTrace();
~~~

then the method attempts to **record the stack frame information of the currently running thread at the current call site** into **the `ex` object itself**, replacing the previous trace information, unless writable stack trace recording has been disabled or JVM limitations apply.

**Key point:** `fillInStackTrace()` does not create a new exception, does not throw that exception, and does not automatically wrap a cause. It **updates the origin location represented in the stack trace** of an existing `Throwable` object.

After this lesson, you will be able to:

1. Describe what is recorded when creating a Throwable and what does **not** change when merely rethrowing the same instance.
2. Explain that `fillInStackTrace()` records the stack of the **calling thread**, which object it returns, and its impact on the old trace.
3. Distinguish between `fillInStackTrace()`, `getStackTrace()`, `setStackTrace()`, and `printStackTrace()`.
4. Examine the impact on `cause`, suppressed exceptions, and exceptions whose stack trace is not writable.
5. Know when to preserve the original stack trace rather than updating it, especially when debugging and propagating exceptions across multiple application layers.

## 2. Official API Definition

According to [Java SE 17 API – Throwable.fillInStackTrace](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#fillInStackTrace()), the method has the signature:

~~~java
public synchronized Throwable fillInStackTrace()
~~~

The method records information about the current state of the stack frames for the **current thread** into this `Throwable` object itself. The return value is **the same `this` reference**. If the Throwable's writable stack trace is disabled, the call **has no effect** on the trace.

Once a stack trace has been recorded, operations such as `getStackTrace()` and `printStackTrace()` reflect the new information according to their respective rules.

| API | Function | Replaces the internal trace of the Throwable? |
| --- | --- | --- |
| `fillInStackTrace()` | Records the stack trace at the current thread/call site | **Yes**, if the trace is writable |
| `getStackTrace()` | Returns an array of `StackTraceElement` representing the current trace | **No** |
| `setStackTrace(StackTraceElement[])` | Overwrites the stack-frame elements with the specified array | **Yes**, if the trace is writable |
| `printStackTrace()` | Prints the exception object and its associated trace to the default stream | **No** |
| `getCause()` | Inspects the cause exception, if any | **No** |
| `getSuppressed()` | Inspects suppressed exceptions, typically from cleanup | **No** |

Example:

~~~java
Throwable same = ex.fillInStackTrace();
System.out.println(same == ex); // true
~~~

This is an **illustrative snippet**; it must be placed inside a method with an already-created `ex` variable of type `Throwable`.

Note: the word "record" describes the API-level result, not a guarantee about internal storage such as native backtraces, JVM structures, or memory layout. A JVM is permitted to omit some frames in certain situations.

## 3. Default Capture Timing and the Impact of Rethrowing

### 3.1. Normally the trace is formed when the exception is created

Example:

~~~java
static RuntimeException createFailure() {
    return new IllegalStateException("service unavailable");
}
~~~

The snippet above is an illustrative method. The `IllegalStateException` constructor calls the superclass `Throwable` mechanism to fill in the stack trace. On a typical JVM, the first observed frame will correspond to where **the instance was created**, here `createFailure`.

**Creating** an exception and **throwing** it are two separate actions:

~~~java
RuntimeException failure = createFailure();
// ... additional work may happen here ...
throw failure;
~~~

The `throw failure;` statement uses the existing instance. This operation itself **does not force a trace refresh**; on common JVMs, the trace continues to point to `createFailure`, rather than suddenly switching to the `throw failure;` line.

### 3.2. Explicitly calling fillInStackTrace before rethrowing

~~~java
failure.fillInStackTrace();
throw failure;
~~~

This illustrative pattern differs in that `fillInStackTrace()` actively records the thread's stack at the call site. If the trace is writable, the top frame can change to the method that performed the refresh. Then `throw failure;` throws **the same instance** with the updated trace.

**Design warning:** Updating the trace can cause the **original** failure location to be replaced by the rethrow site. During debugging, the original error site is usually much more valuable than the forwarding site. Therefore, **you should not automatically call `fillInStackTrace()` before every rethrow**.

If you need to add upper-layer context while preserving the original error, **exception chaining** is usually more appropriate:

~~~java
try {
    serviceCall();
} catch (IOException ex) {
    throw new IllegalStateException("Cannot complete request", ex);
}
~~~

This is **illustrative code**; it requires a `serviceCall()` method and importing `IOException`. The new exception has a trace at the site where it is created, while `ex` is stored as the `cause` with its own origin trace. This changes **the object and causal relationship**, which is completely different from updating the trace of the old instance.

## 4. Complete Java 17 Program

Create the file **`FillInStackTraceDemo.java`**. The program uses no external libraries; each example prints short verifiable values rather than source line numbers or entire stack traces that may vary.

~~~java
import java.io.IOException;

public class FillInStackTraceDemo {
    private static RuntimeException createFailure() {
        return new IllegalStateException("service unavailable");
    }

    private static String top(Throwable ex) {
        StackTraceElement[] frames = ex.getStackTrace();
        return frames.length == 0 ? "<empty>" : frames[0].getMethodName();
    }

    private static void throwSame(RuntimeException ex) {
        try {
            throw ex;
        } catch (RuntimeException caught) {
            System.out.println("same object=" + (caught == ex));
            System.out.println("top after throw=" + top(caught));
        }
    }

    private static void refreshHere(Throwable ex) {
        Throwable returned = ex.fillInStackTrace();
        System.out.println("fill returns this=" + (returned == ex));
        System.out.println("top after fill=" + top(ex));
    }

    private static final class NoTraceException extends Exception {
        NoTraceException() {
            super("no frames", null, true, false);
        }
    }

    public static void main(String[] args) {
        System.out.println("== creation and rethrow ==");
        RuntimeException original = createFailure();
        System.out.println("top on create=" + top(original));
        throwSame(original);
        refreshHere(original);
        throwSame(original);

        System.out.println("== manual trace ==");
        original.setStackTrace(new StackTraceElement[] {
                new StackTraceElement("Synthetic", "custom", "Fake.java", 123)
        });
        System.out.println("top after set=" + top(original));
        refreshHere(original);

        System.out.println("== cause and suppressed ==");
        IllegalArgumentException cause = new IllegalArgumentException("root");
        IllegalStateException wrapped = new IllegalStateException("wrapper", cause);
        wrapped.addSuppressed(new IOException("close failed"));
        Throwable result = wrapped.fillInStackTrace();
        System.out.println("same after fill=" + (result == wrapped));
        System.out.println("cause same=" + (wrapped.getCause() == cause));
        System.out.println("suppressed=" + wrapped.getSuppressed().length);
        StackTraceElement[] copy = wrapped.getStackTrace();
        copy[0] = new StackTraceElement("Fake", "change", "X.java", 1);
        System.out.println("defensive copy=" + !top(wrapped).equals("change"));

        System.out.println("== disabled stack ==");
        NoTraceException hidden = new NoTraceException();
        System.out.println("initial size=" + hidden.getStackTrace().length);
        System.out.println("fill returns this=" + (hidden.fillInStackTrace() == hidden));
        hidden.setStackTrace(new StackTraceElement[] {
                new StackTraceElement("Fake", "method", "X.java", 1)
        });
        System.out.println("after fill+set size=" + hidden.getStackTrace().length);
    }
}
~~~

Compile with **Java 17** compatibility, then run:

~~~bash
javac --release 17 -encoding UTF-8 FillInStackTraceDemo.java
java FillInStackTraceDemo
~~~

**Actual stdout, verified on OpenJDK with full frames of the illustrative methods:**

~~~text
== creation and rethrow ==
top on create=createFailure
same object=true
top after throw=createFailure
fill returns this=true
top after fill=refreshHere
same object=true
top after throw=refreshHere
== manual trace ==
top after set=custom
fill returns this=true
top after fill=refreshHere
== cause and suppressed ==
same after fill=true
cause same=true
suppressed=1
defensive copy=true
== disabled stack ==
initial size=0
fill returns this=true
after fill+set size=0
~~~

**Portability:** The Javadoc allows some JVMs to omit stack frames in certain cases, or even return an empty array. Therefore, lines containing top method names such as `createFailure` or `refreshHere` are **results from the tested JVM**, not a mandatory guarantee across all JVMs, optimization flags, and environments. The lines checking reference identity, cause, and suppressed exceptions reflect a more stable API contract. On a JVM with full traces, the output clearly demonstrates the refresh order.

## 5. Analyzing Parts of the Program

### 5.1. Creating in createFailure and rethrowing in throwSame

In `main`, an `IllegalStateException` instance is created by `createFailure()`. The program prints:

~~~text
top on create=createFailure
~~~

When `throwSame(original)` executes, it throws and catches **the exact same `original` object**, verifying that `caught == ex` is `true`. Because there is no new exception constructor or `fillInStackTrace()` call, the trace still points to the creation site:

~~~text
same object=true
top after throw=createFailure
~~~

**Takeaway:** catching and rethrowing does not make Java rebuild the trace for the old instance. This is why logs of an exception rethrown multiple times can still display the same original source location.

### 5.2. refreshHere changes the top frame

The method:

~~~java
private static void refreshHere(Throwable ex) {
    Throwable returned = ex.fillInStackTrace();
    System.out.println("fill returns this=" + (returned == ex));
    System.out.println("top after fill=" + top(ex));
}
~~~

records the trace at the call site. `returned == ex` is `true` because the API returns the updated instance itself. On the tested JVM, the top frame changes from `createFailure` to `refreshHere`.

If the same instance is thrown again afterward, `throwSame` still sees the `refreshHere` frame, without automatically changing it to `throwSame`. The `throw` operation is not an implicit refresh command.

### 5.3. How does setStackTrace differ from fillInStackTrace?

In the `manual trace` section, the snippet:

~~~java
original.setStackTrace(new StackTraceElement[] {
        new StackTraceElement("Synthetic", "custom", "Fake.java", 123)
});
~~~

**explicitly assigns the provided frame list**, instead of capturing the thread's current stack. Hence `top(original)` returns `custom`. After calling `refreshHere(original)`, `fillInStackTrace()` re-records the current stack information, so on the tested JVM `top` changes back to `refreshHere`.

Comparison:

| Operation | Frame data source | Effect |
| --- | --- | --- |
| Standard `new SomeException(...)` | Current stack at creation time | Sets the initial trace |
| `throw existingException;` | Does not capture anything additional | Keeps the existing trace |
| `existingException.fillInStackTrace()` | **Current** stack of the calling thread | Refreshes the trace |
| `existingException.setStackTrace(array)` | `StackTraceElement`s provided by code | Replaces the trace representation with the array |
| `existingException.getStackTrace()` | Existing trace inside the exception | Returns an array copy for reading |

`setStackTrace()` is mainly useful for RPC frameworks, systems that transmit stack traces across process boundaries, or specialized engineering tools. Arbitrarily assigning synthetic frames to business exceptions can **obscure where the error actually started**. Do not use it to "fix" an error merely by altering log output.

### 5.4. Cause and suppressed are not cleared by fillInStackTrace

In the `cause and suppressed` branch:

~~~java
IllegalArgumentException cause = new IllegalArgumentException("root");
IllegalStateException wrapped = new IllegalStateException("wrapper", cause);
wrapped.addSuppressed(new IOException("close failed"));
Throwable result = wrapped.fillInStackTrace();
~~~

We have these independent relationships:

- `wrapped.getCause() == cause` remains `true`.
- `wrapped.getSuppressed().length` remains `1`.
- `result == wrapped` remains `true`.

`fillInStackTrace()` refreshes **the trace of `wrapped`**, without creating a different cause or clearing the suppressed list. The cause is also a separate `Throwable` object with its own trace; this method does not automatically update the cause's trace.

Thus **stack trace**, **exception chaining (cause)**, and **suppressed exceptions** are distinct parts of a `Throwable` object's information. Reliable debugging requires knowing which parts are preserved and which are replaced.

### 5.5. The getStackTrace array is a defensive copy

The `getStackTrace()` API returns a `StackTraceElement[]` array for programmatic access. Modifying elements in the returned array **does not alter the trace stored** inside the `Throwable`.

The test snippet:

~~~java
StackTraceElement[] copy = wrapped.getStackTrace();
copy[0] = new StackTraceElement("Fake", "change", "X.java", 1);
System.out.println("defensive copy=" + !top(wrapped).equals("change"));
~~~

prints `defensive copy=true` on the verified JVM. If you want to change the displayed stack trace, you must call **`setStackTrace()`**; mutating an array returned by the getter is not enough.

To make code safe across all JVMs, check the array length before accessing `copy[0]` because the specification allows an empty trace under some circumstances. The full example above was verified in an environment with normal frames; it is not a unit test for every JVM configuration. Production code should write:

~~~java
StackTraceElement[] frames = ex.getStackTrace();
if (frames.length > 0) {
    System.out.println(frames[0].getMethodName());
}
~~~

This snippet only illustrates safe array handling; `ex` must be an existing `Throwable`.

### 5.6. When writableStackTrace is disabled

The JDK provides the protected constructor:

~~~java
protected Throwable(
        String message,
        Throwable cause,
        boolean enableSuppression,
        boolean writableStackTrace)
~~~

An exception subclass can choose `writableStackTrace=false`:

~~~java
private static final class NoTraceException extends Exception {
    NoTraceException() {
        super("no frames", null, true, false);
    }
}
~~~

In this example, the third argument `true` **enables suppression**; the fourth argument `false` **disables writing the stack trace**. According to the Javadoc, when `writableStackTrace` is `false`, the constructor does not call `fillInStackTrace()`, subsequent calls to `fillInStackTrace()` do not update the trace, and `setStackTrace(...)` does not set frames either; `getStackTrace()` returns a zero-length array.

Test output:

~~~text
initial size=0
fill returns this=true
after fill+set size=0
~~~

Even when the trace is not writable, `fillInStackTrace()` still returns **the object itself**. Do not confuse this case with disabled suppression: if `enableSuppression=false`, `getSuppressed()` is empty and `addSuppressed` does not record anything; that configuration is **independent** of `writableStackTrace`.

## 6. How Does Updating the Trace Affect Logs and Error Investigation?

Suppose an error actually occurs in the file-reading layer and is then propagated through a service and controller. If the same instance is kept:

~~~java
try {
    readInput();
} catch (IOException ex) {
    log(ex);
    throw ex;
}
~~~

this is illustrative code; it requires defining `readInput()`, `log()`, and declaring/handling `IOException` per the contract. The exception can preserve the trace at the original failure point. If `ex.fillInStackTrace();` is added right before rethrowing, the trace is typically updated to the **service layer** that rethrew it; some initial frames in the reading layer may no longer appear in the new trace.

This can have consequences:

1. **Loss of the original exception creation site in the primary trace.** Later logs may mislead investigators toward the forwarding site rather than where the error originated.
2. **Altered incident grouping in observability tools.** Some systems group errors by class, message, and stack frames; refreshing can cause the same error to be grouped differently.
3. **Misleading information when exceptions are shared.** If an instance is cached or shared across multiple threads, updating the trace reflects **the most recent thread calling fill**, rather than automatically preserving the original failing thread.
4. **Runtime overhead.** Collecting stack frames can be expensive, especially on hot paths that create or update many `Throwable`s. Do not call it repeatedly just for routine logging.
5. **Does not revert side effects or program state.** A trace is diagnostic information; refreshing does not re-run the failed operation, roll back, or alter the logical outcome that already occurred.

For typical applications, a better approach is to keep the original `Throwable` and **wrap it with a cause when additional context is needed**:

~~~java
try {
    readInput();
} catch (IOException ex) {
    throw new IllegalStateException("Input processing failed", ex);
}
~~~

The result is a new wrapper at the current layer **and** a cause preserving the original source. In the printed stack trace, there will typically be a `Caused by: ...` section for the original exception. There is no need to destroy the old trace by calling `fillInStackTrace()`.

### Is there ever a good reason to explicitly call fillInStackTrace?

Yes, but there should be a clear technical reason. For example, a framework might reuse a `Throwable` to represent a **new event at the current time** and have a contract requiring **changing the diagnostic point** on the same instance. In that case, calling `fillInStackTrace()` is intentional, not the default.

If you want to keep the original location before refreshing, do not assume an automatic history mechanism exists. You can save a snapshot from `getStackTrace()` or design an appropriate wrapper/cause. However, manually saving snapshots and resetting traces requires a clear policy, because traces can contain sensitive information about code structure and make diagnosis harder if altered arbitrarily.

## 7. Difference Between an Existing Stack Trace and the Thread's Current Stack

Two concepts are easy to confuse:

- **The Throwable's trace:** the frames that the exception currently stores or exposes via `getStackTrace()`; usually starts where the `Throwable` was created or where `fillInStackTrace()` was last called.
- **The thread's current stack:** the methods currently on the call stack at the time of observation. This can be inspected with debugging tools, `Thread.currentThread().getStackTrace()`, or the `StackWalker` API in appropriate situations.

Calling `ex.fillInStackTrace()` requests updating **ex's trace** with the stack state **of the calling thread**. It does not search for "the thread that first threw ex" and is not an operation to capture stacks across all threads.

In particular, if an exception instance is reused across multiple threads, the result after refreshing can switch to a completely different context from its origin. Reusing or updating a `Throwable` across multiple threads also makes investigation data unstable; normally you should create an exception per failure and keep its initial trace.

## 8. JLS and JVM Allow Incomplete Traces

Based on the [Java 17 getStackTrace API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getStackTrace()), the element at index 0 is normally the top frame of the stack (closest to where the trace was recorded). However, **you must not assume the array always has elements**. Depending on the JVM and circumstances, some frames may be omitted or the array may be empty.

Therefore, in real-world code:

~~~java
StackTraceElement[] frames = ex.getStackTrace();
if (frames.length == 0) {
    System.out.println("No stack trace available");
} else {
    StackTraceElement first = frames[0];
    System.out.println(first.getClassName());
    System.out.println(first.getMethodName());
}
~~~

The snippet above is illustrative and requires an already-declared `ex` variable of type `Throwable`. Class and method names can be useful during investigation, but **file names and line numbers are not always available**, especially for code without debug information or executed/optimized differently.

Do not use exact `StackTraceElement.toString()` string matching down to whitespace and line numbers as a business criterion. In exercises, printing method names helps clearly observe the refresh effect; in broad automated tests, test against the API contract and avoid asserting exact frames across all JVMs.

## 9. setStackTrace and the Integrity of Diagnostic Data

`setStackTrace(StackTraceElement[])` allows assigning provided frames to a `Throwable`. It does not need to inspect the thread's current stack to populate data. The API also **copies the input array**, so modifying the input array after the call does not change the trace that was set.

Illustrative example:

~~~java
StackTraceElement[] frames = {
    new StackTraceElement("RpcService", "call", "RpcService.java", 18)
};
ex.setStackTrace(frames);
frames[0] = new StackTraceElement("Other", "changed", "Other.java", 1);
// The line above does not directly alter the trace already set in ex.
~~~

This is illustrative code requiring `ex` to be a `Throwable` with a writable stack trace. `setStackTrace` is suited to certain RPC systems or reconstructing traces from information sent over the network; normally it should be avoided for replacing traces of application bugs.

When the trace is not writable (constructor `writableStackTrace=false`), the Javadoc states that `setStackTrace` has no effect **beyond argument validation**. It does not re-enable a writable trace. You must create a new instance with the appropriate configuration if the contract requires a trace.

### Should you override fillInStackTrace for performance?

Some specialized exceptions may be designed to skip stack trace collection, but this is a direct trade-off against **diagnosability**. For `Throwable` subclasses, consider the protected constructor accepting `writableStackTrace=false` if truly appropriate.

In addition, `Throwable`'s normal constructor invokes the stack-trace-filling mechanism; overriding a method that may be called during object construction requires careful design because subclass-specific state may not yet be initialized. Do not apply this optimization to all business exceptions unless you have measured actual cost and explicitly accept losing the trace.

## 10. Distinguishing Operations with Quick Questions

| Scenario | Same Throwable? | How is the trace handled? |
| --- | --- | --- |
| `throw existing;` | Yes | Does not automatically refresh the trace |
| `existing.fillInStackTrace(); throw existing;` | Yes | Refreshes the trace before throwing, if writable |
| `Throwable other = existing.fillInStackTrace();` | Yes, `other == existing` | Same updated instance |
| `throw new IllegalStateException("context", existing);` | No, new wrapper | Wrapper has its own trace; `existing` becomes the cause |
| `existing.setStackTrace(frames);` | Yes | Displayed trace is set to the provided frames |
| `existing.getStackTrace();` | Yes | Reads an array copy only, does not refresh |
| `existing.printStackTrace();` | Yes | Prints the current trace, does not refresh |
| Calling fill when `writableStackTrace=false` | Yes | Does not change the trace; typically an empty array |

**Separate note:** If the expression after `throw` evaluates to `null`, Java throws a runtime-created `NullPointerException`; that is a different situation from calling `fillInStackTrace()` on a non-null `Throwable` object.

## 11. Common Misconceptions

1. **"Every `throw` makes Java re-record the stack trace."** False: rethrowing the same instance does not automatically refresh the trace.
2. **"`fillInStackTrace` creates a new exception."** False: the API returns the calling object itself.
3. **"`fillInStackTrace` automatically throws the exception."** False: it only updates the information; propagating the error still requires `throw` or a corresponding mechanism.
4. **"Updating the trace also updates `cause` and `suppressed`."** False: these relationships are independent.
5. **"`getStackTrace` returns an array you can modify to change the internal trace."** False: the getter returns a defensive copy.
6. **"`setStackTrace` and `fillInStackTrace` are the same."** False: one uses frames supplied by code; the other captures the thread's current stack state.
7. **"Refreshing preserves the original trace."** Usually the opposite: the old trace may be replaced.
8. **"A stack trace always has every frame and line number."** False: the API allows the JVM to omit frames or return an empty array.
9. **"No trace means the exception doesn't really exist."** False: a `Throwable` can be created with a non-writable stack trace.
10. **"`writableStackTrace=false` also disables suppression."** False: the two flags are independent.
11. **"Calling `fillInStackTrace` on any thread always captures the stack of the thread that originally caused the error."** False: it uses the thread **executing the refresh call**.
12. **"Just refresh at the controller layer for cleaner logs."** That can lose the original frames; consider exception chaining instead.
13. **"Updating the trace retries or rolls back the failed operation."** False: only diagnostic information changes.
14. **"Synthetic frames from `setStackTrace` can always be trusted unconditionally."** No: a library or framework can deliberately alter trace contents, so you must evaluate the trustworthiness of the source.

## 12. Self-Check Exercises

**Q1.** An exception is created in `createFailure()`, then rethrown in `controller()` without calling fill: does the trace automatically switch to `controller`?

*Answer:* No. `throw existing;` does not automatically refresh the stack trace.

**Q2.** Does `Throwable ref = ex.fillInStackTrace();` create a new object?

*Answer:* No. `ref == ex` is `true`.

**Q3.** If `refreshHere(ex)` calls fill, and `ex` is later thrown again elsewhere, will the trace reflect the refresh step or the second throw?

*Answer:* Typically it reflects the most recent refresh location, except when the stack trace is disabled or the JVM omits frames.

**Q4.** If `ex` has a cause and a suppressed exception, does calling fill remove them?

*Answer:* No. Cause and suppressed exceptions exist independently of updating the stack trace.

**Q5.** If you modify `StackTraceElement[] a = ex.getStackTrace(); a[0] = ...;`, does `ex`'s trace change automatically?

*Answer:* No. The array returned by the getter is a copy; you must use the appropriate setter API if you intentionally want to replace the trace.

**Q6.** Why should `getStackTrace()[0]` be preceded by a length check?

*Answer:* The Javadoc allows some Throwables/JVMs to have an empty trace array; accessing index 0 then throws `ArrayIndexOutOfBoundsException`.

**Q7.** A subclass calls `super(message, cause, true, false)`; will calling fill multiple times populate frames in the trace array?

*Answer:* No. Setting `writableStackTrace` to `false` prevents both fill and set from updating the trace; the getter returns an empty array.

**Q8.** When a service needs to add context while preserving the original error source, what solution should you consider?

*Answer:* Create a new wrapper exception with a message and the original exception as its cause; do not refresh the old trace by default.

## 13. Official Documentation

- [Java SE 17 API – Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): constructors and cause/suppression/writable stack trace properties.
- [Java SE 17 API – fillInStackTrace](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#fillInStackTrace()): records the current thread's stack information and returns the same instance.
- [Java SE 17 API – getStackTrace](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getStackTrace()): frame ordering and JVM permission to omit trace entries.
- [Java SE 17 API – setStackTrace](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#setStackTrace(java.lang.StackTraceElement%5B%5D)): assigns an array of stack frames via the API.
- [Java SE 17 API – StackTraceElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackTraceElement.html): structure of each frame and getters for class/method names, file, and line number.
- [Java SE 17 API – Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed()): reads the list of secondary exceptions.
- [Java SE 17 JLS Section 14.18 – throw statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.18): how a `Throwable` object is thrown; rethrowing is not synonymous with refreshing.

**Remember:** `fillInStackTrace()` **updates the trace at the time of the call on the existing `Throwable` itself**, without creating a new `Throwable` or throwing an error. After refreshing, the starting point of the trace can shift from the original failure site to the update site, which strongly affects debugging. Only use it when you genuinely want to replace the trace; normally, preserve the original trace and use exception chaining to add context.
