# FFM Upcalls — Catching All Exceptions in Callbacks to Prevent Escaping Across the Upcall Boundary

## 1. The Cardinal Rule: Never Let a Java `Throwable` Cross an FFM Upcall

The **Foreign Function & Memory (FFM) API** allows Java to call C functions using a **downcall**, while also allowing native code to call back into Java using an **upcall stub**. An upcall stub is a native function pointer created by `Linker.upcallStub(MethodHandle, FunctionDescriptor, Arena)`; when C calls that pointer, the JVM executes the Java `MethodHandle` bound to the stub.

The problem is that **a Java exception is not a C exception**. C has no mechanism to catch, unwind, or interpret Java's `RuntimeException`, `IOException`, or `Error`. According to the official contract of `Linker.upcallStub`, **the target method handle must not throw an exception**. If the target throws an exception that escapes across the upcall boundary, **the JVM will terminate abruptly**, rather than simply returning the exception to the Java caller.

That is why this lesson has one mandatory rule:

> **Wrap all callback code in `try/catch (Throwable t)`; record the failure without rethrowing inside the upcall; return a valid value according to the C ABI; after the native call finishes, handle/propagate the failure on the Java side.**

Diagram:

```text
Java                           Native/C                         Java callback
  │                                │                                  │
  ├── downcall qsort(array, cmp) ──►│                                  │
  │                                ├── cmp(pointerA, pointerB) ──────►│
  │                                │                             try { work(); }
  │                                │                             catch(Throwable t) {
  │                                │                               record(t);
  │                                │                               return 0;
  │                                │                             }
  │                                │◄───────── int (valid ABI) ───────┤
  │◄──── native function returns ──┤                                  │
  │                                                                    │
  ├── inspect recorded failure                                       │
  └── throw Java exception HERE, after native returns                │
```

You must distinguish between **a Java exception in a normal Java call chain** and **an exception escaping through a callback being invoked by native code**. Java can `throw` in another Java method once it has returned to a Java context, but **must not `throw` out of the target method handle used by `upcallStub`**.

**Example scope:** Official FFM API **JDK 22+ (JEP 454)**. The programs have been compiled/run with **OpenJDK 24.0.2 on Windows x64** using the standard C library `qsort`. No custom DLL needs to be built; 64-bit ABI guidance and Linux/macOS notes are included. JDK 21 is still FFM preview (JEP 442), requiring flags and API review.

## 2. How Is an Upcall Created?

Standard C example:

```c
void qsort(void *base, size_t count, size_t element_size,
           int (*compare)(const void *, const void *));
```

`qsort` takes a `compare` function pointer. Native code calls the comparator multiple times to decide element ordering; the comparator **must return an integer**:

- Negative value: the first element is less than the second.
- `0`: the two elements compare equal.
- Positive value: the first element is greater than the second.

In Java FFM, we need to:

1. Obtain `Linker.nativeLinker()` and create a **downcall handle** to `qsort`.
2. Write a Java static method with a signature matching the callback: two `MemorySegment` parameters as `const void*` addresses, returning `int`.
3. Create a `MethodHandle` pointing to that Java method.
4. Use `Linker.upcallStub` to create a native function pointer for `qsort`.
5. Keep the **Arena and upcall stub alive** until native code is guaranteed to no longer call the callback.
6. Inside the callback, **do not let any Java `Throwable` escape**; save the failure and return a valid value.
7. After `qsort` returns, **check the recorded failure**, and do not use the sorted data if the comparator failed.

### Two Different `FunctionDescriptor`s

For the 64-bit ABI in this article:

```java
// qsort(void *base, size_t count, size_t elemSize, functionPointer)
FunctionDescriptor qsortDesc = FunctionDescriptor.ofVoid(
    ValueLayout.ADDRESS, ValueLayout.JAVA_LONG,
    ValueLayout.JAVA_LONG, ValueLayout.ADDRESS);

// int compare(const void *a, const void *b)
FunctionDescriptor compareDesc = FunctionDescriptor.of(
    ValueLayout.JAVA_INT,
    ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT),
    ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT));
```

This is a valid abbreviated snippet when FFM types are imported. `size_t` is **64 bits** wide on Windows x64 and Linux x86-64, so `JAVA_LONG` matches here; **do not** apply this descriptor as-is to a 32-bit system. `ValueLayout.ADDRESS` has the `MemorySegment` carrier in Java, while `JAVA_INT` is the primitive `int`.

The two pointers of the `qsort` comparator actually point to `C int` elements. `ADDRESS.withTargetLayout(JAVA_INT)` tells FFM that each pointer has at least **4 valid bytes** for Java to read, instead of a zero-length pointer that cannot be dereferenced. Declaring this target layout is **restricted**, because you must ensure on your own that it matches the ABI and actual contents. An incorrect ABI/pointer/bounds can cause a crash regardless of whether the code has `catch(Throwable)`.

## 3. Why Must You Catch `Throwable`, Not Just `Exception`?

Java hierarchy:

```text
java.lang.Throwable
├── java.lang.Exception
│   ├── RuntimeException
│   │   ├── IllegalArgumentException
│   │   ├── IllegalStateException
│   │   ├── IndexOutOfBoundsException
│   │   └── NullPointerException
│   └── IOException, InterruptedException, ...
└── java.lang.Error
    ├── AssertionError
    ├── LinkageError
    ├── OutOfMemoryError
    ├── StackOverflowError
    └── VirtualMachineError, ...
```

`catch (Exception e)` does not intercept `Error`. If the callback throws `AssertionError`, `LinkageError`, or another `Error`, that exception can escape across the upcall boundary. **`catch (Throwable t)`** is the boundary wrapper broad enough to satisfy the `Linker.upcallStub` contract.

You must understand its limits accurately:

- Catching `Throwable` is **a measure to block exceptions at the Java boundary**, not a guarantee that every fatal error is recoverable. With `OutOfMemoryError`, `StackOverflowError`, or JVM corruption, even the handler may lack enough resources to perform complex work; the JVM may still terminate for other reasons.
- Do not rethrow `t` **inside the target method handle**.
- Do not construct new exceptions, format long stack traces, do complex logging, or call code that can easily throw inside `catch`.
- Use a minimal error-recording mechanism (for example `AtomicReference.compareAndSet`) to store **the first failure** and return a valid sentinel to C.
- Report the error at **the Java boundary outside the native call** (for example, after `qsort.invokeExact(...)` finishes).

**Important:** A `try/catch(Throwable)` only covers code that is actually **inside `try`**. If the callback has logic that can throw before `try`, in `finally`, or in the handler after catching, an exception can still escape. Do not let logger/metrics/callback cleanup create a second error outside the protected region.

## 4. Two Wrong Examples That Must Not Go Into Production

### Wrong 1 — callback throws directly across the upcall

```java
// INTENTIONALLY WRONG: method used as an FFM upcall target.
static int unsafeCompare(MemorySegment a, MemorySegment b) {
    int x = a.get(ValueLayout.JAVA_INT, 0);
    if (x < 0) {
        throw new IllegalArgumentException("negative element");
    }
    return Integer.compare(x, b.get(ValueLayout.JAVA_INT, 0));
}
```

When C `qsort` calls the comparator and `x < 0`, the Java exception escapes from the target; **there is no safe catching mechanism on the C side**. Do not run this variant to "see if the JVM crashes": according to the Linker documentation, the JVM may terminate abruptly. Replace it with the wrapped callback in Section 5.

### Wrong 2 — only catching `Exception` or rethrowing in the handler

```java
// INTENTIONALLY WRONG: Error is not caught.
try {
    work();
} catch (Exception e) {
    throw new RuntimeException("callback failed", e); // Still escapes the upcall!
}
```

Even `catch (Throwable t) { throw new RuntimeException(t); }` **is still wrong**. Do not transfer exceptions back to native by throwing a Java `Throwable`. Define an **error protocol** that can be represented in C: return a status code, set an out-parameter, mark a failure state, or call an appropriate error-reporting API (as long as the handler does not throw).

## 5. Complete and Verified Example: Safely Calling `qsort` with FFM

Goal:

- `qsort` will call back into the Java comparator through an FFM upcall stub.
- For valid input, the comparator works normally and `qsort` sorts the numbers in ascending order.
- If the comparator sees the value `-7`, it **intentionally throws `IllegalArgumentException` inside the `try` block**, but `catch(Throwable)` catches it, records it into `AtomicReference`, and returns `0` to C.
- After `qsort` completes, Java detects the recorded failure and throws `IllegalStateException` **outside the upcall boundary**. The Java caller reads the cause via `getCause()`; the JVM continues running.
- The output does not depend on the sort order of the failure case, because that case **must discard the result**.

### 5.1. Complete source: `SafeQsortUpcallDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicReference;

public final class SafeQsortUpcallDemo {
    private static final Linker LINKER = Linker.nativeLinker();

    private static final FunctionDescriptor COMPARE_DESCRIPTOR =
        FunctionDescriptor.of(ValueLayout.JAVA_INT,
            ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT),
            ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT));

    private static final FunctionDescriptor QSORT_DESCRIPTOR =
        FunctionDescriptor.ofVoid(ValueLayout.ADDRESS, ValueLayout.JAVA_LONG,
            ValueLayout.JAVA_LONG, ValueLayout.ADDRESS);

    // The method handle bound to the upcall stub must NEVER let
    // a Throwable escape to foreign code.
    private static int safeCompare(MemorySegment a, MemorySegment b,
                                   AtomicReference<Throwable> failure) {
        try {
            if (failure.get() != null) return 0;

            int x = a.get(ValueLayout.JAVA_INT, 0);
            int y = b.get(ValueLayout.JAVA_INT, 0);

            if (x == -7 || y == -7) {
                throw new IllegalArgumentException("element -7 is invalid");
            }
            return Integer.compare(x, y);
        } catch (Throwable t) {
            // Keep the FIRST failure; avoid logging or throwing here.
            failure.compareAndSet(null, t);
            return 0; // Valid int ABI; do NOT trust sorting result now.
        }
    }

    private static int[] sort(int[] values) throws Throwable {
        // A NEW failure box for each native call avoids cross-call leakage.
        AtomicReference<Throwable> failure = new AtomicReference<>();

        MethodHandle target = MethodHandles.lookup().findStatic(
            SafeQsortUpcallDemo.class, "safeCompare",
            MethodType.methodType(int.class, MemorySegment.class,
                MemorySegment.class, AtomicReference.class));

        // Insert the failure state as arg #2: target is now
        // (MemorySegment, MemorySegment)int, matching the C callback.
        target = MethodHandles.insertArguments(target, 2, failure);

        MethodHandle qsort = LINKER.downcallHandle(
            LINKER.defaultLookup().findOrThrow("qsort"), QSORT_DESCRIPTOR);

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment array = arena.allocate(
                (long) values.length * ValueLayout.JAVA_INT.byteSize(),
                ValueLayout.JAVA_INT.byteAlignment());

            for (int i = 0; i < values.length; i++) {
                array.setAtIndex(ValueLayout.JAVA_INT, i, values[i]);
            }

            // The stub lives at least as long as qsort may call it.
            MemorySegment callback =
                LINKER.upcallStub(target, COMPARE_DESCRIPTOR, arena);

            // qsort is synchronous: when it returns, callbacks are done.
            qsort.invokeExact(array, (long) values.length,
                ValueLayout.JAVA_INT.byteSize(), callback);

            // Only after returning from native code may Java throw.
            Throwable cause = failure.get();
            if (cause != null) {
                throw new IllegalStateException("upcall failed", cause);
            }

            int[] result = new int[values.length];
            for (int i = 0; i < result.length; i++) {
                result[i] = array.getAtIndex(ValueLayout.JAVA_INT, i);
            }
            return result;
        }
    }

    public static void main(String[] args) throws Throwable {
        System.out.println("good: "
            + Arrays.toString(sort(new int[] {4, 1, 3, 2})));

        try {
            sort(new int[] {5, -7, 3});
        } catch (IllegalStateException e) {
            Throwable cause = e.getCause();
            System.out.println("error after return: "
                + cause.getClass().getSimpleName() + ": " + cause.getMessage());
        }

        System.out.println("JVM still alive");
    }
}
```

### 5.2. Compile and Run

Choose **JDK 22+**, a **64-bit** ABI that has `qsort` in `Linker.defaultLookup()` (the program was run on Windows x64/OpenJDK 24). No DLL or C source needs to be created for this example.

In the directory containing `SafeQsortUpcallDemo.java`:

```bash
javac -encoding UTF-8 SafeQsortUpcallDemo.java

java --enable-native-access=ALL-UNNAMED SafeQsortUpcallDemo
```

**Exact stdout verified on OpenJDK 24.0.2 / Windows x64:**

```text
good: [1, 2, 3, 4]
error after return: IllegalArgumentException: element -7 is invalid
JVM still alive
```

This is **actual execution** output, not a guess. The compiler may emit warnings about restricted FFM APIs if `-Xlint:all` is enabled; the command above does not request lint. `--enable-native-access=ALL-UNNAMED` grants native access permission to classpath code when using `downcallHandle`, `upcallStub`, and `ADDRESS.withTargetLayout`.

### 5.3. Analysis of the Details That Make It Safe

**`safeCompare` wraps its entire body in a single `try`:** every segment read, data validation, and `Integer.compare` lies inside the region covered by `catch(Throwable)`. When the value `-7` triggers `IllegalArgumentException`, the code **does not throw out of the callback**, and instead stores the exact `Throwable`.

**`AtomicReference<Throwable> failure` is per-invocation state:** if a global `static` variable were used without resetting, a failure from a previous sort could corrupt the next one. `AtomicReference` also makes the failure visible across threads if a native API invokes callbacks from multiple threads; however, it **does not replace** a protocol for waiting until callbacks finish.

**`compareAndSet(null,t)` keeps the first failure:** native code may call the comparator many times. After the first failure, the callback returns `0` for subsequent calls, avoiding further risky work. Under normal conditions, this AtomicReference operation does not need to allocate a new exception and does not throw.

**`return 0` preserves the ABI, not the sort result:** `0` is a valid `int` value for the C comparator. However, because some pairs are treated as equal after the failure, the `qsort` result of the failed run **is untrustworthy**. Therefore, the `sort` method **never copies or returns the result when `failure != null`**; it throws `IllegalStateException` after the native call.

**`MethodHandles.insertArguments` preserves the callback signature:** the original Java method has a third parameter `AtomicReference`, which is not a C parameter. After `insertArguments(target,2,failure)`, the actual target handle has `MethodType (MemorySegment,MemorySegment)int`, matching the callback descriptor. If you do not bind the context and pass the three-parameter handle directly to `upcallStub`, the linker will reject it due to a mismatch.

**`Arena.ofConfined()` stays alive for the entire downcall:** both the stub and the array are allocated in the arena and are only cleaned up **after** `qsort.invokeExact` returns. `qsort` is a synchronous example: after returning, it does not retain the function pointer to call later. If a native API registers a long-lived callback, **do not close the arena** immediately after the register call; you must unregister, wait for any running callbacks to complete, and only then close the arena appropriately.

**The Java error is thrown in `sort` after native finishes:** because execution has returned to Java code outside the callback, a new Java exception can follow normal rules up to the caller. `getCause()` preserves the original failure, even when the public API only wants to expose `IllegalStateException`.

## 6. Why Can't You Just "Wrap the Downcall in try/catch"?

A pattern that **does not solve the upcall boundary**:

```java
// Strategically WRONG: the upcall target is still allowed to throw.
try {
    qsort.invokeExact(array, n, elementSize, unsafeCallback);
} catch (RuntimeException e) {
    // If a Java exception has already escaped from the target to native,
    // there is no guarantee control will return here.
}
```

This is an illustrative snippet, not standalone compilable code. C `qsort` **is not a Java method**; after C calls the function pointer to the upcall, a Java exception crossing the callback boundary can cause the JVM to terminate before `qsort.invokeExact` returns. Putting `try/catch` **in the Java caller around the downcall** does not replace blocking the exception **right inside the target**.

Similarly, a thread's Java `UncaughtExceptionHandler` is not a protection mechanism for FFM upcalls. It does not change the "target should not throw" contract, and cannot turn a `Throwable` into a C exception that the library understands.

## 7. Second Approach: `MethodHandles.catchException`

When the callback is an existing `MethodHandle` or its source is hard to modify, you can **wrap the method handle** using a combinator:

```java
MethodHandle safe = MethodHandles.catchException(
    rawTarget, Throwable.class, fallbackHandler);
```

`fallbackHandler` must have a compatible signature: **its first parameter is `Throwable`**, followed by parameters corresponding to the target as needed; **its return type matches the target**. If the target returns `int`, the handler must return `int`. The handler also **must not throw an exception out**.

### 7.1. Standalone Example: `CatchCombinatorCheck.java`

This program tests `MethodHandles.catchException` itself in pure Java, **without calling native**. It illustrates exactly how to bind the error box and catch `Throwable`. For a real upcall, pass the protected handle as the target of `Linker.upcallStub`.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.concurrent.atomic.AtomicReference;

public class CatchCombinatorCheck {
    public static int raw(int x) {
        if (x < 0) throw new IllegalArgumentException("negative");
        return x * 2;
    }

    public static int fallback(Throwable error,
                               AtomicReference<Throwable> box,
                               int x) {
        box.compareAndSet(null, error);
        return -1;
    }

    public static void main(String[] args) throws Throwable {
        AtomicReference<Throwable> box = new AtomicReference<>();

        MethodHandle raw = MethodHandles.lookup().findStatic(
            CatchCombinatorCheck.class, "raw",
            MethodType.methodType(int.class, int.class));

        MethodHandle handler = MethodHandles.lookup().findStatic(
            CatchCombinatorCheck.class, "fallback",
            MethodType.methodType(int.class, Throwable.class,
                AtomicReference.class, int.class));

        // Handler: (Throwable, AtomicReference, int)int
        // After binding box: (Throwable, int)int
        handler = MethodHandles.insertArguments(handler, 1, box);

        MethodHandle safe = MethodHandles.catchException(
            raw, Throwable.class, handler);

        System.out.println("safe type: " + safe.type());
        System.out.println("success: " + (int) safe.invokeExact(4));
        System.out.println("failure code: " + (int) safe.invokeExact(-1));
        System.out.println("captured: "
            + box.get().getClass().getSimpleName());
    }
}
```

### 7.2. Running the Combinator Example

```bash
javac -encoding UTF-8 CatchCombinatorCheck.java
java CatchCombinatorCheck
```

**Stdout verified on OpenJDK 24:**

```text
safe type: (int)int
success: 8
failure code: -1
captured: IllegalArgumentException
```

To use `safe` as an upcall target, the `FunctionDescriptor` must match this handle's `(int)int` signature. In the `qsort` example of Section 5, the comparator takes **two pointers**, so you must write the target/handler as `(MemorySegment,MemorySegment)int` and keep the parameters and return ABI intact when wrapping.

**Combinator limitation:** if `fallbackHandler` itself throws an exception (for example, a logger fails) or an outer `filter`/adapter around the wrapped handle throws, an exception can still escape. Therefore, **wrap the final layer** actually passed to `upcallStub` and also test failures from the handler. In many applications, an explicit `try/catch(Throwable)` Java method like `safeCompare` is easier to review and manage ownership for.

## 8. Designing an ABI-Compatible Error Protocol Instead of Throwing Java Exceptions

### 8.1. Callback Whose Return Value Is a Status Code

A C API controlled by the application can be designed as:

```c
// 0 = success, nonzero = application-defined callback failure.
typedef int (*process_callback)(int value, void *user_data);
int for_each_value(process_callback cb, void *user_data);
```

The Java callback can return `-1` or another code according to the **contract defined by C**, while recording the Java failure for later handling. If C supports stopping immediately when the callback returns nonzero, it will not continue processing bad data. This design **is better than `qsort`** when you have control over the API design, because the `qsort` comparator only has negative/0/positive semantics and **has no error-reporting channel**.

### 8.2. Comparators Like `qsort` Have No Dedicated Error Channel

If a callback is forced to return a comparison `int`, there is no valid "return Java exception". Choosing a fallback (for example `0`) is only a way to ensure C continues in a state without a Java exception. Once a failure occurs:

- `AtomicReference` records the failure so Java knows about it.
- The comparator performs no unnecessary additional business logic.
- The native algorithm may continue for a few steps because it has no dedicated error code.
- After `qsort` returns, **discard the result and report the error in Java**.

Do not put post-failure sort state into a cache, DB, or public result as if the sort had succeeded. This is a **data integrity** requirement, not just preventing a JVM crash.

### 8.3. `void` Callbacks

If the C signature is `void (*callback)(...)`, the Java upcall must also return `void`; **do not add parameters or return `int` just because you want an error code**. In the handler:

```java
// Snippet; errorBox is a valid AtomicReference<Throwable>.
static void safeNotify(int value,
                       AtomicReference<Throwable> errorBox) {
    try {
        doWork(value);
    } catch (Throwable t) {
        errorBox.compareAndSet(null, t);
        // Do not rethrow. Return void according to the C ABI.
    }
}
```

`doWork` is application-specific logic defined separately; the snippet is illustrative only and **is not a standalone file**. If the C API does not support a status code, use an error state/out-param or a separate error-reporting mechanism; do not invent a return value that violates the ABI.

### 8.4. Callbacks Returning a Pointer `T*`

If the C callback requires returning `char*`/`void*`, the corresponding Java carrier is `MemorySegment`. A possible fallback is `MemorySegment.NULL` **only when the C contract accepts NULL**. If the API requires a non-null pointer, returning NULL can still cause C to dereference it and crash. At the same time, you must not return a pointer to a segment whose scope has already ended when the upcall finishes. In other words, **you must agree on an error protocol with the native ABI; there is no universal sentinel**.

## 9. Storing and Surfacing the Java Error at the Right Time

### 9.1. Prefer Per-Call State

For synchronous native functions like `qsort`, an `AtomicReference<Throwable>` created **separately for each invocation** prevents error leakage between calls:

```java
AtomicReference<Throwable> failure = new AtomicReference<>();
// Bind failure to the callback MethodHandle.
nativeDowncall.invokeExact(...);
Throwable cause = failure.get();
if (cause != null) {
    throw new IllegalStateException("callback failed", cause);
}
```

This snippet is **control-flow pseudocode**, not a standalone program, because `nativeDowncall` and the parameter list vary by API. Crucially: only `throw` **after you are sure the native function will no longer invoke that callback**.

If you want to retry, create a new error box or reset it under a protocol where no callback is running; do not reuse a state with a leftover failure.

### 9.2. When C Calls the Callback on Another Thread

A native library may create its own C worker thread and then invoke the function pointer. In that case, the Java callback may run on **a different thread from the Java thread that registered the callback**:

- **Do not assume the caller's `ThreadLocal` holds the error from the callback thread.** `ThreadLocal` is bound per thread; another native-created thread will not have the same value.
- `AtomicReference` or a thread-safe queue is suitable for reporting errors across threads. If multiple exceptions need to be collected, use a bounded queue / mechanism that avoids unbounded allocation.
- If the native call is **asynchronous**, callbacks may not have finished when the register function returns; **do not check the error once immediately after register and conclude it is safe**.
- You need an unregister/shutdown protocol, wait for the callback count to reach zero or join/wait on a callback completion signal; only then inspect the failure and close the upcall stub.
- If multiple callbacks run concurrently, you must define which outcome takes precedence: the first error, the most severe error, or all errors. `compareAndSet(null,t)` intentionally keeps the first error.

### 9.3. Do Not Retain `Throwable` Forever in a Native Registry

A `Throwable` holds a cause, a stack trace, and may reference objects/class loaders; keeping it in an `AtomicReference` longer than necessary can cause memory retention. Once it is safe to handle the error, clear the state according to the lifecycle (or discard the entire per-operation holder). If a native callback registration is long-lived, define memory limits, logging, and an unregistration policy.

## 10. Cases Where `catch(Throwable)` Is Still Not Enough

**Never promise that catching every Throwable prevents every JVM crash.** It only blocks the path of **Java exception propagation** across the upcall boundary when the handler logic actually executes. Other failures include:

| Failure Type | Why `catch(Throwable)` Cannot Save It |
| --- | --- |
| Wrong `FunctionDescriptor` or calling convention | C uses the wrong ABI, misreads parameters/writes stack incorrectly; may crash without becoming a Java exception |
| Stub deallocated because Arena was closed | C calls an expired function pointer; native fault occurs before the Java callback runs |
| Native C buffer overflow / invalid pointer | Memory safety violation in native code, does not necessarily throw a Java `Throwable` |
| `catch` handler throws a new exception | The new error can still escape across the upcall |
| Severe `OutOfMemoryError` / `StackOverflowError` | The process/JVM may already be in a state where it cannot continue safely |
| Native C retains callback pointer after unregister/free | Use-after-free of a function pointer, not a Java exception |
| Callback returns wrong type/lifetime | C dereferences an invalid pointer or misinterprets the return value |
| Deadlock / recursive upcall | Callback may block on a monitor/lock held by a native thread; catch does not resolve deadlocks |

Do not try to "test" this by letting an uncaught exception cross an upcall in a production process. Use unit tests to trigger an exception **inside `try` and verify the handler blocks it**, like the `-7` demo in Section 5.

### The Handler's Error Handling Must Be Simple Enough

It can be unsafe to write:

```java
catch (Throwable t) {
    LOGGER.error("Callback failed: {}", complexObject.toString(), t);
    // Logger, formatter, toString, allocation, or lock can all throw/fail.
    return 0;
}
```

This is a **not-recommended** pattern for FFM upcalls. Instead, store the `Throwable` in a stable state and log/format **after the native return**. `AtomicReference.compareAndSet(null,t)` is a much simpler primitive, though the program itself must still ensure the holder is valid and no throwable logic lies outside the guard.

If the callback performs cleanup, ensure that cleanup cannot emit an error outward. It is usually better to manage resources in **the scope surrounding the downcall** in Java, after the native call finishes, rather than performing potentially throwing cleanup inside the callback.

## 11. Managing the Lifecycle of the Upcall Stub and Native Registration

`Linker.upcallStub(target, descriptor, arena)` creates a function pointer tied to an **Arena**. If the arena is closed while C still uses that pointer, a subsequent callback invocation by C can cause a crash. Distinguish between:

- **Synchronous callback (e.g., `qsort`):** `try (Arena arena = Arena.ofConfined())` is appropriate when the native function returns **after** all callbacks. The stub stays alive throughout the call, and then the arena closes.
- **Asynchronous/registered callback:** `registerCallback(pointer)` may return while C still holds the pointer. The arena must stay alive **until unregister** and all in-flight callbacks finish; `Arena.ofShared()` is usually more appropriate when C invokes callbacks across multiple threads.
- **Confined arena:** if native code invokes callbacks or touches memory on another thread, evaluate thread accessibility. Do not assume a confined arena fits every async native callback.
- **Native library unload:** C must not invoke the stub or downcall symbols after the backing library/registration is unloaded; lifecycle must be managed on both sides.

A sound shutdown protocol:

```text
register pointer (stub + state) → receive callbacks
           │
           ▼
stop accepting new callbacks / unregister from native library
           │
           ▼
wait for all in-flight callbacks to complete
           │
           ▼
process recorded failure / deliver Java result
           │
           ▼
close Arena and release upcall stub
```

**Never close the Arena before the unregister-and-drain step.** `catch(Throwable)` cannot protect a function pointer that has already been deallocated.

## 12. Native Access Flags, Java Version, and Platform ABI

### JDK 22+

FFM was finalized in **JDK 22 (JEP 454)**. To use `Linker.downcallHandle`, `Linker.upcallStub`, and `AddressLayout.withTargetLayout`, the appropriate module must have native access permission:

```bash
java --enable-native-access=ALL-UNNAMED SafeQsortUpcallDemo
```

`ALL-UNNAMED` applies to classpath code, such as the demo. For a named module, use the corresponding module name (e.g., `--enable-native-access=com.example.ffm`). `--enable-native-access` **does not** replace `--enable-preview` in versions where FFM was still in preview.

JDK 24 may emit compile-time warnings if built with `javac -Xlint:all` because of restricted APIs. That is an FFM safety concern, not because the exception handler is wrong. Enable native access for the process so you do not encounter restricted access warnings/denials at runtime under the running JDK's policy.

### JDK 21

FFM in **JDK 21 is Third Preview (JEP 442)**. When porting the source to JDK 21, you must check the API signatures of that release and then compile/run with:

```bash
javac --enable-preview --release 21 SafeQsortUpcallDemo.java
java --enable-preview --enable-native-access=ALL-UNNAMED SafeQsortUpcallDemo
```

These two commands illustrate **the required flags** on JDK 21; **they do not claim that the JDK 24 example source was tested on JDK 21 or guarantee that the source compiles verbatim**. Starting from JDK 22, preview flags are no longer needed for FFM alone, though native-access permissions still must be considered.

### ABI and Compiler

`qsort` uses C `size_t`, while the callback receives two `const void*` parameters and returns `int`. On the **64-bit** ABIs in the example, `size_t` is 8 bytes, so `JAVA_LONG` is appropriate. On 32-bit platforms, the descriptor must be changed. `C long` also differs between Windows x64 (LLP64) and Linux x86-64 (LP64), so do not infer a type merely from the name `long`. Always cross-check **the C header, OS/CPU ABI, alignment, and calling convention**.

`Linker.defaultLookup()` is not guaranteed to contain every symbol on every system; in the example on Windows x64/OpenJDK 24, `qsort` was found and used successfully. If another platform does not provide `qsort` in the default lookup, you must use `SymbolLookup.libraryLookup` to the appropriate C library, configure the path, and keep the library loaded for the entire lifetime of the callback.

## 13. FFM Upcall vs. JNI Exception Boundary

Traditional JNI and FFM upcalls both have a **Java ↔ native boundary**, but their mechanisms differ.

| Aspect | JNI | FFM Upcall |
| --- | --- | --- |
| Java calls native | `native` method with a C/C++ entrypoint via JNI | Java calls a C function via a `MethodHandle` downcall |
| Native calls Java | `Call<Type>Method`, creates a pending Java exception if the Java method throws | Native calls the C function pointer of `upcallStub` |
| Detecting Java exceptions | JNI has `ExceptionCheck`/`ExceptionOccurred` | **There is no `ExceptionCheck` mechanism in an FFM upcall target like JNI** |
| Java error crossing native boundary | JNI programmers check/manage pending exceptions per contract | **Upcall target must not throw; the JVM may terminate abruptly** |
| Propagating errors safely | Use a JNI pending Java exception properly when native returns | Catch `Throwable` in the callback; return an ABI value; store the error and handle it after the native call finishes |

Do not use JNI functions like `env->ExceptionCheck()` in a callback written purely with FFM; FFM does not pass a `JNIEnv*` to the upcall Java target. If your C library has both JNI and FFM, each path must still obey its own contract.

## 14. Safe Design Checklist

- [ ] Every target method handle actually passed to `Linker.upcallStub` **must not let `Throwable` escape**.
- [ ] Use `catch(Throwable)`, not just `catch(Exception)`, to ensure `Error` also does not cross the boundary.
- [ ] All potentially throwing logic sits inside the guard region, including memory reads, validation, business callbacks, and adapters.
- [ ] Inside the handler, record the failure minimally; **do not rethrow**, and do not call error-prone logging/formatting.
- [ ] Return type/value matches the C ABI; a sentinel is valid only when the C API accepts it.
- [ ] Have a dedicated error-reporting channel (return status, out-param, atomic state, queue, Java future, etc.) matching the native protocol.
- [ ] For synchronous native functions, **check for failure after the downcall and before using the result**.
- [ ] For async callbacks, unregister/drain/join before reading the final result and closing the Arena.
- [ ] Use a separate error holder per invocation/registration; avoid mutable global state shared across callbacks.
- [ ] FFM `FunctionDescriptor` and `MethodType` match each carrier/ABI; verify C `int`, `size_t`, and pointer sizes.
- [ ] Keep the stub, arena, and native library alive as long as C still holds the function pointer.
- [ ] Do not treat `catch(Throwable)` as protection against native memory corruption, ABI mismatch, or severe JVM errors.
- [ ] Test the success path, normal Java exceptions, controlled `Error`s, fallback behavior, subsequent callbacks, cleanup, and failure propagation.

## 15. Common Errors and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| JVM terminates when Java comparator throws | `Throwable` escapes the upcall target | Wrap the target properly with `try/catch(Throwable)` or `MethodHandles.catchException` |
| `catch(RuntimeException)` does not block `AssertionError` | Only catches a subtype, not covering `Error` | Use `catch(Throwable)` at the boundary |
| Upcall handler catches error and still crashes | Logger/formatter/cleanup inside `catch` throws again | Minimize the handler; record state and return |
| Error occurs but Java still uses the sort result | Fallback returning `0` lets qsort continue, result is no longer trustworthy | Read the error box after the downcall; **discard** data and report error |
| `IllegalArgumentException` when creating stub | MethodType differs from FunctionDescriptor or descriptor unsupported | Check exact parameter/return carriers and `insertArguments` order |
| Callback reading pointer hits `IndexOutOfBoundsException` | Upcall pointer defaults to zero-length | Use a target layout matching the ABI when the object size is actually known |
| Crash after registering callback | Arena containing the stub was closed early | Keep Arena/stub until unregister + callbacks are drained |
| `WrongThreadException` during callback | Using confined resources on a disallowed thread | Design shared resources and an appropriate threading contract |
| Error not visible in Java caller | Callback on another thread, misused `ThreadLocal` | Use thread-safe state and a completion signal |
| C callback returns wrong type | Incompatible return ABI | Choose sentinel/status per C signature, do not return Throwable |
| Crash despite catching Throwable | Native memory bug, wrong calling convention, invalid pointer | Audit ABI/ownership, use native diagnostics/sanitizers |
| `--enable-preview` enabled yet native-access warning remains | Preview does not grant restricted permission | Use `--enable-native-access` for the module needing native access |

## 16. Practice Exercises

1. Why is `catch(Exception)` insufficient in an FFM upcall target? Which additional error groups does `catch(Throwable)` block?
2. What happens under the `Linker.upcallStub` contract if the Java target throws an exception that escapes? Can you rely on a `try/catch` in the Java downcall caller to save it?
3. In `SafeQsortUpcallDemo`, why does `safeCompare` record into `AtomicReference` and return `0` instead of rethrowing `IllegalArgumentException`?
4. After the callback returns the sentinel `0`, should you trust the `qsort` result? Why is it necessary to check for failure after the native return?
5. Why must you call `insertArguments(target,2,failure)` before creating the upcall stub? What `MethodType` does the final target have?
6. If the C callback signature is `void (*cb)(int)`, may Java change the return type to `int` on its own to report an error?
7. When a native API runs asynchronously and invokes the callback from a C worker thread, why is the Java caller's `ThreadLocal` unsuitable as a failure box?
8. How does `MethodHandles.catchException` differ from a `try/catch(Throwable)` wrapper? What happens if the combinator's handler itself throws?
9. Why must the Arena stay alive until the native library is guaranteed to no longer use the function pointer?
10. Which failures can crash the JVM that `catch(Throwable)` **cannot** solve?
11. If you need to keep multiple errors from multiple callbacks, how should you define a policy to select the first error or collect errors?
12. For Java 21 preview and Java 24 finalized FFM, how do the runtime flags differ?

**Key takeaway:** At the **FFM upcall boundary**, always treat a Java callback as a function **that is not allowed to throw**. Catch **`Throwable`** right inside the target, record the failure using a mechanism with clear ownership, **return a valid ABI value**, and then handle/throw in Java code **after the native call has finished**. Do not expect a C native library to catch `Throwable` on Java's behalf.

### Official Documentation

- [Oracle JDK 24 — Linker.upcallStub: target must not throw, otherwise JVM terminates](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Linker.html).
- [Oracle JDK 22 — Linker and FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html).
- [Oracle JDK 24 — MethodHandles.catchException](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/invoke/MethodHandles.html).
- [Dev.java — How to Handle a Call from Native Code Back to Java Code (FFM Upcalls)](https://dev.java/learn/api/io/ffm/upcall/).
- [Oracle JDK 24 — Restricted Methods and native access permissions](https://docs.oracle.com/en/java/javase/24/core/restricted-methods.html).
- [OpenJDK JEP 454 — FFM Final API](https://openjdk.org/jeps/454).
- [OpenJDK JEP 442 — FFM Third Preview](https://openjdk.org/jeps/442).
