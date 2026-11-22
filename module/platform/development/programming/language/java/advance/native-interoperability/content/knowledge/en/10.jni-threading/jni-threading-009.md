# Defining Cooperative Cancellation Instead of Assuming `interrupt` Always Stops a C Function

## 1. The Problem in Java–JNI: A Stop Request Is Not a Forced Stop

A Java thread calls a native function through the **Java Native Interface (JNI)**. The C function may compute for many seconds, wait on a device, call a third-party C/C++ library, or be stuck in a blocking operation. While the native function is running, another Java thread calls:

~~~java
worker.interrupt();
~~~

**There is no general guarantee that this call immediately interrupts the C function, aborts the C loop, releases resources, or returns the native method to Java.** `Thread.interrupt()` is a mechanism for **sending a cooperative interrupt request** to a thread, not a command to “kill” an arbitrary block of code.

While executing a native method, the Java process is running native machine code. C/C++ code does **not automatically** read Java's interrupt flag at each loop iteration. If the native method does not support an exit path, the JVM generally has no safe way to force it to stop at an arbitrary point while still preserving the stack, mutexes, memory regions, and library state.

Therefore, the right design is to **define a cooperative cancellation protocol**:

- The cancelling party **signals** using a mechanism with clear memory visibility.
- The native code **checks the signal** at safe points, with bounded or documented cancellation latency.
- The native code **does not abort in an inconsistent state**: it stops accepting new work, finishes or rolls back the current unit of work, and cleans up the resources it owns.
- The caller **observes confirmation** that the native method has finished, rather than treating `interrupt()` or `Future.cancel(true)` as proof that it has stopped.
- When native code may hang uncooperatively, **timeouts at the appropriate layer or isolation into another process** are required rather than promising immediate cancellation.

The goal is not to replace every interrupt with a boolean; the goal is to **explicitly agree on who requests, who observes, the check points, the reaction upon cancellation, and when stopping is considered complete**.

## 2. Distinguishing “interrupt”, “cancellation request”, and “terminated”

| Event | Meaning | What must *not* be inferred |
| --- | --- | --- |
| `thread.interrupt()` | Sets the thread's interrupt status or triggers a defined interrupt mechanism for certain waiting/blocking Java operations | Does not mean the thread is dead or that every JNI/C call has stopped |
| `thread.isInterrupted()` | Reads the interrupt status without clearing the flag | Is not verification that the native function has returned |
| `Thread.interrupted()` | Reads **and clears** the interrupt status of the **current thread** | Not equivalent to `isInterrupted()` |
| `InterruptedException` | Some Java blocking methods exit due to interrupt; the common rule is that the interrupt status is cleared when the exception is thrown | Does not guarantee a C syscall or native library behaves the same way |
| `cancelToken.set(true)` | Sends a cancellation request per the application protocol; with `AtomicBoolean`, visibility is guaranteed through atomic/volatile operations | Does not automatically stop C if C has not checked the token |
| Native method returns `CANCELLED` or confirms completion | Native code has passed through the cancellation handling point, performed defined cleanup, and returned | Does not say that all auxiliary work in other threads/processes has stopped, unless the protocol covers them |
| `Future.cancel(true)` | Requests task cancellation; **may** interrupt the executing thread depending on the executor mechanism | Does not guarantee C received the request or has exited; the future's state does not necessarily reflect native resources |
| `worker.join()` returns after the thread finishes | Can confirm that the thread is no longer executing | Does not by itself indicate whether cancellation succeeded or cleanup was proper; the outcome must still be checked |

Pure Java example:

~~~java
// Illustrates semantics, not a complete program.
worker.interrupt();          // Sends an interrupt request.
boolean pending = worker.isInterrupted(); // Only reads the flag.
worker.join();               // Waits for the Java thread to actually finish.
~~~

`join()` can wait forever if the native code never returns. Therefore, in request-serving systems, an unbounded `join()` cannot be used on the main processing path as a “timed cancellation” solution. Contracts for timing, metrics, and appropriate isolation levels are needed.

## 3. Why Interrupt Cannot Automatically Stop All C Code

### 3.1. The Interrupt Flag Belongs to the JVM; Native Loops Do Not Check It Automatically

The following C code can continue running even when the Java thread is interrupted:

~~~c
/* C code for illustration only, not a standalone JNI native method. */
for (;;) {
    do_cpu_work();
}
~~~

There is no instruction in the loop querying the JVM for an interrupt or cancellation token. The JVM cannot assume an arbitrary location inside `do_cpu_work()` is a safe stopping point.

Some native libraries have their own cancellation/timeout APIs; they only work when **the application integrates those APIs**, not because Java `interrupt()` is implicitly wired to them.

### 3.2. Java Interrupts Are Defined for Specific Operations

Java operations such as `Thread.sleep`, `Object.wait`, `Thread.join`, and many interruptible methods in `java.util.concurrent` have their own contracts regarding interrupts and `InterruptedException`. For some Java I/O, an interrupt may cause a channel to close or throw an exception according to the corresponding API.

**Do not generalize** from those behaviors to:

- `read()`/`recv()`/`poll()`/`select()` called directly by C;
- `pthread_mutex_lock` or native synchronization libraries;
- calls to graphics libraries, native database drivers, GPUs, or devices;
- C functions handling files, compression, encryption, or long CPU computations.

OS signals, EINTR, syscall restart logic, timeouts, callbacks, and library cancel APIs are **different** mechanisms. Depending on the environment, some native calls may return an error when hit by an OS signal, but **`Thread.interrupt()` cannot be treated as a standardized cancellation OS signal** for every C function.

### 3.3. Forcible Stopping at an Arbitrary Point Can Corrupt Invariants

Suppose a native function is doing:

~~~text
lock(mutex)
allocate(buffer)
write half of output
update native state
...
unlock(mutex)
free(buffer)
~~~

If the thread is forced to stop right after locking or writing halfway, other threads may get stuck, buffers may leak, data may be left incomplete, or native state may be corrupted. The cancellation protocol needs to define **safe exit points**: complete the chunk/transaction, release resources, roll back if applicable, and emit a clear result.

For that reason, avoid using `Thread.stop`, OS thread-killing tricks (uncontrolled `pthread_cancel`, `TerminateThread`, etc.), or arbitrarily freeing native context while another call is still using it. These are not safe substitutes for cooperative cancellation.

## 4. Designing a Cooperative Cancellation Contract

A contract can be written concisely as:

> The Java side sends **CANCEL_REQUESTED** via a shared token. The native worker checks the token between finite units of work or when a wait times out. Upon seeing the request, the worker does not start the next unit; if needed, it completes/rolls back the in-progress part, releases all resources belonging to the invocation, and returns **CANCELLED**. The caller only confirms “stopped” after observing that the native method has finished.

### 4.1. Clearly Defining the Five Components

| Component | Question to Answer | Example |
| --- | --- | --- |
| **Request path** | Who sends it, via which API, from which thread? | `AtomicBoolean.cancelRequested.set(true)` |
| **Visibility** | How does the native thread see the change? | Calling `AtomicBoolean.get()` via JNI; or `_Atomic bool`/`std::atomic<bool>` with memory order rules |
| **Check points** | How often is it checked? | After each computation chunk; before starting new native I/O; after polling timeout |
| **Cleanup rules** | Who is responsible for closing/freeing resources? | Always release JNI buffers, close files owned by the worker, unlock in order; do not call `DeleteGlobalRef` while users remain |
| **Result/acknowledgement** | How does the caller distinguish completed/cancelled/failed? | Method returns an enum/status or throws an agreed-upon exception; Java thread signals completion via `CountDownLatch` |

Several policies should be decided before implementation:

- **Is cancellation best-effort or does it have an upper bound?** If a chunk is at most 50 ms, plus a 20 ms sleep/poll timeout, the application can document the expected cancellation latency; a strict upper bound should not be promised if the OS/device cannot guarantee it.
- **Where does cancellation apply?** Only before commit, or is mid-way rollback allowed? If already committed successfully, `COMPLETED` may be returned even if the cancellation request arrived very late.
- **Who owns the token and native context?** Memory must not be freed while the worker might still read it.
- **How are error paths prioritized?** If both an I/O error and a cancel occur, record a consistent state and log the cause; do not mask the real error.
- **How long does the caller wait?** The timeout for “waiting for acknowledgement” must be distinct from the “deadline for allowing the work to run”; if exceeded, controlled escalation is needed.

### 4.2. Lifecycle Diagram

~~~text
Java requester              JNI/C worker                 Java supervisor
      |                          |                              |
      | -- submit -------------->|                              |
      |                          | -- start native work ------->|
      |                          |    process chunk             |
      | -- cancel token=true --->|                              |
      |                          | -- poll token                |
      |                          | -- stop new chunks           |
      |                          | -- cleanup resources         |
      |                          | -- return CANCELLED -------->|
      |                          |                              |
      |<------------------------- observe worker termination ---|
~~~

If the native code is in a blocking syscall or a third-party C call that **cannot check the token**, the “poll token” arrow only happens when that call returns. A library timeout/cancellation API, non-blocking design, or process isolation is needed for reliable behavior.

## 5. Categorizing Native Work to Choose a Cancellation Strategy

| Type of Work | Appropriate Cancellation Check Point | Constraints to Know |
| --- | --- | --- |
| CPU-bound loop in C/C++ owned by us | After each finite block; before the next chunk | Long chunks increase cancellation latency |
| Computation with commit/side effects | Between transaction steps, before commit, after rollback | Do not cancel mid-way when invariants are temporarily invalid |
| Native I/O with timeout/poll | After each timed blocking poll/read; or via the library's cancel API | Do not assume Java interrupt automatically makes the syscall return |
| Calling a native library with a cancel API | Send cancel command via the official API and wait for acknowledgement | Must obey the library's thread-safety/lifetime rules |
| Black-box library blocking indefinitely without cancel/timeout | Isolate into a separate process with IPC and timeout | Cannot promise safe in-process cancellation; killing the process loses all state in that process |
| JNI callback / FFM/native loop with Java state | Check token between safe callbacks | Do not make arbitrary JNI calls while holding a critical primitive array/string section |

The last point is especially important: after `GetPrimitiveArrayCritical` or `GetStringCritical`, the code must obey critical section restrictions; do not hold it for long and arbitrarily call `CallBooleanMethod` to query the token in Java. **Release the critical section quickly**, then check for cancellation at a safe point.

## 6. Using `AtomicBoolean` as a Cancellation Token Across JNI

A simple pedagogical approach, transparent regarding memory visibility:

- Java creates `AtomicBoolean cancelRequested = new AtomicBoolean(false)`.
- Java passes the token object into the native method as a `jobject`.
- Another Java thread calls `cancelRequested.set(true)`.
- The native worker calls `AtomicBoolean.get()` via `JNIEnv` between work chunks.
- When `get()` returns `true`, C cleans up resources and returns the cancelled status.

**Why use `AtomicBoolean` instead of a plain Java `boolean`?**

Java's `AtomicBoolean.set` and `get` have volatile write/read semantics under the Java Memory Model: they provide the necessary visibility between two threads. A plain non-`volatile` boolean field read/written concurrently without synchronization does not provide an equivalent visibility contract. `AtomicBoolean` makes it easy to represent a token and avoids hand-rolling a memory barrier protocol.

**Why does native read the token via JNI instead of casting `jobject` to a C pointer?**

`jobject` is an opaque reference managed by the JVM, not a pointer to a Java object's layout. Native code must use `GetObjectClass`, `GetMethodID`, and `CallBooleanMethod`, or appropriate JNI accessors. Calling `AtomicBoolean.get()` preserves Java semantics and avoids guessing memory offsets.

**Cost:** Each `CallBooleanMethod` is a call across JNI into a Java method, which has overhead. If a loop runs millions of iterations per second, only check at appropriate chunk boundaries, or design a tightly managed native atomic token. The example below prioritizes **correct semantics, clarity, and runnability** over extreme throughput.

## 7. Complete Java 17 + C/JNI Example: Interrupt Is Not Enough; Token Allows Exit

Demo goals:

1. Java creates a worker thread and sends the worker into a native method.
2. The native method signals that it has started using `CountDownLatch.countDown()`.
3. The main thread calls `worker.interrupt()` **without setting the token yet**. The native method remains in the loop because C has no logic checking the interrupt status.
4. Java confirms the worker has not finished after a bounded wait.
5. Java calls `cancel.set(true)`. Native code observes the token via `AtomicBoolean.get()` and returns.
6. Java confirms the native method has returned; the worker may still retain the interrupt flag, as this code does not call any API that clears the flag.

Environment: **Linux + JDK 17 or later + GCC** matching the JVM architecture. Create two files `NativeCancellationDemo.java` and `native_cancel.c` in the same directory. Set the `JAVA_HOME` environment variable to the JDK.

### 7.1. Java — `NativeCancellationDemo.java`

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public final class NativeCancellationDemo {
    static {
        System.loadLibrary("nativecancel");
    }

    private static native boolean runUntilCancelled(
            AtomicBoolean cancel, CountDownLatch entered);

    public static void main(String[] args)
            throws InterruptedException {

        AtomicBoolean cancel = new AtomicBoolean(false);
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);

        AtomicBoolean nativeSawCancel = new AtomicBoolean(false);
        AtomicBoolean interruptStillSet = new AtomicBoolean(false);
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread worker = new Thread(() -> {
            try {
                boolean cancelled = runUntilCancelled(cancel, entered);
                nativeSawCancel.set(cancelled);
                interruptStillSet.set(
                        Thread.currentThread().isInterrupted());
            } catch (Throwable error) {
                failure.set(error);
            } finally {
                exited.countDown();
            }
        }, "native-worker");

        worker.start();
        entered.await(); // C has entered the native method.

        worker.interrupt(); // Only sets the interrupt status.
        boolean stoppedByInterruptAlone =
                exited.await(75, TimeUnit.MILLISECONDS);

        cancel.set(true);  // Cooperative cancellation protocol: C checks this.
        worker.join();     // Wait for worker to ACTUALLY finish.

        if (failure.get() != null) {
            throw new IllegalStateException(
                    "Native worker failed", failure.get());
        }

        System.out.println(
                "stoppedByInterruptAlone="
                + stoppedByInterruptAlone);
        System.out.println(
                "nativeSawCancel=" + nativeSawCancel.get());
        System.out.println(
                "interruptStillSet=" + interruptStillSet.get());
    }
}
~~~

Design choices in the Java code:

- `entered.await()` only returns after the native code has called `countDown()`; thus the main thread does not have to guess when native execution started.
- `exited.await(75, TimeUnit.MILLISECONDS)` is only a bounded observation window, **not a mandatory JVM cancellation time**. Because the native method's only successful exit path is when the token is `true`, it cannot finish “by interrupt alone” in the normal demo case.
- `cancel.set(true)` is the signal that the native code **actually reads**. `worker.join()` is used here to confirm the worker has finished in the demo environment; production needs timeouts and an escalation policy.
- `AtomicReference<Throwable> failure` transfers unexpected errors from the worker to the main thread so the example does not silently print a false result as if it succeeded.
- `Thread.currentThread().isInterrupted()` reads the flag **without clearing** it. The example does not call `Thread.interrupted()`, does not call Java's `sleep()`, and does not catch `InterruptedException` in the worker.

### 7.2. C/JNI — `native_cancel.c`

~~~c
#define _POSIX_C_SOURCE 200809L

#include <jni.h>
#include <time.h>
#include "NativeCancellationDemo.h"

JNIEXPORT jboolean JNICALL
Java_NativeCancellationDemo_runUntilCancelled(
        JNIEnv *env,
        jclass owner,
        jobject cancel,
        jobject entered) {

    (void) owner;

    if (cancel == NULL || entered == NULL) {
        jclass invalid = (*env)->FindClass(
                env, "java/lang/IllegalArgumentException");
        if (invalid != NULL) {
            (*env)->ThrowNew(
                    env, invalid, "cancel and entered are required");
            (*env)->DeleteLocalRef(env, invalid);
        }
        return JNI_FALSE;
    }

    /* Prepare AtomicBoolean.get(): boolean. */
    jclass tokenClass = (*env)->GetObjectClass(env, cancel);
    if (tokenClass == NULL) {
        return JNI_FALSE;
    }
    jmethodID getMethod = (*env)->GetMethodID(
            env, tokenClass, "get", "()Z");
    (*env)->DeleteLocalRef(env, tokenClass);

    if (getMethod == NULL) {
        return JNI_FALSE;
    }

    /* Prepare CountDownLatch.countDown(): void. */
    jclass latchClass = (*env)->GetObjectClass(env, entered);
    if (latchClass == NULL) {
        return JNI_FALSE;
    }
    jmethodID countDown = (*env)->GetMethodID(
            env, latchClass, "countDown", "()V");
    (*env)->DeleteLocalRef(env, latchClass);

    if (countDown == NULL) {
        return JNI_FALSE;
    }

    /* Signal: native method has entered the main execution region. */
    (*env)->CallVoidMethod(env, entered, countDown);
    if ((*env)->ExceptionCheck(env)) {
        return JNI_FALSE;
    }

    for (;;) {
        /* Poll token via JNI: if AtomicBoolean.get() == true,
           the native method cooperatively returns. */
        jboolean cancelled = (*env)->CallBooleanMethod(
                env, cancel, getMethod);

        if ((*env)->ExceptionCheck(env)) {
            return JNI_FALSE; /* Propagate Java exception. */
        }
        if (cancelled == JNI_TRUE) {
            return JNI_TRUE;
        }

        /* Illustrate bounded native wait: 10 ms per iteration.
           nanosleep is POSIX/Linux, not a JNI API. */
        struct timespec delay = {0, 10 * 1000 * 1000};
        (void) nanosleep(&delay, NULL);
    }
}
~~~

**Reading the key points:**

- `jobject cancel` and `jobject entered` are **JNI local references** valid throughout this native call; Java also holds both objects, so creating a global reference is not needed.
- `GetObjectClass` creates a local `jclass`; the code deletes it immediately with `DeleteLocalRef` after looking up `jmethodID`. Method IDs are not JNI object references and do not use `DeleteLocalRef`.
- The descriptor `"()Z"` represents the `get()` method with no parameters returning `boolean`; `"()V"` represents `countDown()` with no parameters returning `void`.
- `CallVoidMethod` notifies Java that C has entered the wait loop. JNI calls are made using the worker thread's own `JNIEnv*`.
- `CallBooleanMethod` executes `AtomicBoolean.get()` to inspect the cancellation state. Native code **does not directly read/write Java fields using C offsets**.
- If a JNI callback causes a pending Java exception, the method returns so Java can handle the error; it does not clear the exception and continue an endless loop.
- `nanosleep` reduces CPU busy-waiting and illustrates periodic checking. A native sleep call may end early due to an OS signal; the simple example ignores the result and loops back to check the token. Nothing in the loop **forces a stop due to the Java interrupt flag**.
- Returning `JNI_TRUE` means **the native loop observed the token as true and exited per the protocol**, not that there is a secret Java mechanism that kills C.

The example intentionally does not simulate complex resources. When adding native buffers, files, mutexes, Java global refs, or devices, every return path must go through appropriate cleanup before signaling completion.

### 7.3. Compiling and Running on Linux

From the directory containing both files:

~~~bash
javac -h . NativeCancellationDemo.java

gcc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libnativecancel.so native_cancel.c

java -Djava.library.path=. NativeCancellationDemo
~~~

- `javac -h .` generates `NativeCancellationDemo.class` and `NativeCancellationDemo.h` with a JNI signature matching the Java method.
- `gcc -std=c11 -fPIC -shared` builds the Linux shared library `libnativecancel.so`. The `_POSIX_C_SOURCE` macro enables the POSIX `nanosleep` declaration.
- `-Djava.library.path=.` helps `System.loadLibrary("nativecancel")` find the library in the working directory; this is not the Java classpath.
- The native binary and JDK must match in CPU architecture and ABI.

**Exact expected stdout** when the program runs successfully in the environment above, with no auxiliary errors:

~~~text
stoppedByInterruptAlone=false
nativeSawCancel=true
interruptStillSet=true
~~~

Reasons:

1. The worker signaled `entered` and entered a loop that only exits when `AtomicBoolean.get()` returns true.
2. Java `interrupt()` only changes the interrupt status; C does not query `Thread.isInterrupted()`, so it does not stop on its own.
3. During the 75 ms before `cancel.set(true)`, the worker has no normal exit path, so `exited.await` returns false.
4. After `cancel.set(true)`, the loop sees the request and returns `JNI_TRUE`; Java records `nativeSawCancel=true`.
5. No code on the worker actively clears the interrupt status, so `isInterrupted()` returns true.

**Limitations of the example:** If the program encounters a JVM/native error, `entered.await()` or `join()` might not reach the success path; this is a mechanism lesson, **not** a production monitor with a watchdog. For real operations, add deadlines, error propagation, and handling for unresponsive native libraries.

On macOS, JNI headers are located in `$JAVA_HOME/include/darwin`, the dynamic library is typically named `libnativecancel.dylib`, and it can be built with Clang `-dynamiclib`. On Windows, POSIX `nanosleep` does not exist with the same API; replace it with a Windows timed wait primitive or an appropriate cross-platform C++ design. The JNI cancellation token and return contract remain the same.

## 8. Observing the Java Interrupt Status in C Code When Truly Needed

Some applications want to **use the Java interrupt flag itself as a source of cancellation requests**. That **can be done if native code actively calls JNI to read it**; there is no global automatic mechanism.

Conceptual execution path:

1. Inside the native method, obtain the appropriate `java.lang.Thread` class.
2. Call static `Thread.currentThread()` to get the current thread (creates a local JNI reference).
3. Call instance `isInterrupted()` on that thread to read the flag **without clearing** it.
4. Clean up local references, check exceptions; only poll at safe points and perform cleanup before returning.

Corresponding descriptors:

~~~text
java/lang/Thread
currentThread : ()Ljava/lang/Thread;
isInterrupted : ()Z
~~~

This is an **API sketch**, not a standalone runnable C snippet. You can use `GetStaticMethodID` + `CallStaticObjectMethod` to get the thread and `GetMethodID` + `CallBooleanMethod` to read the flag. Do not arbitrarily use `Thread.interrupted()` because this static method reads **and clears** the current thread's flag, which could lose a signal that the Java layer needs to see.

Drawbacks of relying solely on interrupt status:

- You must clearly define **who owns the interrupt flag** and whether any Java/JNI code might clear the flag upon encountering `InterruptedException` or calling `Thread.interrupted()`.
- A native task may run on a Java thread reused by an executor. If tasks do not handle the interrupt policy properly, observing a leftover flag or losing a flag can cause unpredictable behavior.
- Interrupt status does not represent all cancellation reasons (client disconnect, service shutdown, deadline, cancelling a specific operation).
- Cancelling one native operation does not necessarily mean wanting to interrupt the entire Java thread or all other work on that thread.

Therefore, for long JNI tasks, an **operation-specific token** is usually clearer. You can specify that `interrupt` **triggers the token**, while still letting native code poll, clean up, and return.

## 9. Native Cancellation Flag Using C Atomics: Correct Memory, Correct Ownership

When calling Java `AtomicBoolean.get()` via JNI on every chunk is too expensive, a native flag can be used, such as C11 `_Atomic bool` or C++ `std::atomic<bool>`. However, correctness does **not** come from C's `volatile`.

### 9.1. Using `volatile` Alone Is Not Enough

Wrong expectation:

~~~c
/* Illustrates an incorrect multithreaded synchronization design. */
static volatile int cancel_requested = 0;

/* Thread A writes cancel_requested = 1;
   Thread B reads cancel_requested in a loop. */
~~~

`volatile` in C does **not** automatically establish synchronization/happens-before between threads like an atomic operation; if a normal variable is accessed concurrently without synchronization, the C program can have a data race and undefined behavior. That is not fixed simply by also calling `Thread.interrupt()`.

Correct idea in C11:

~~~c
/* Illustrative snippet, not a standalone JNI program. */
#include <stdatomic.h>
#include <stdbool.h>

_Atomic bool requested = false;

/* Requesting thread. */
atomic_store_explicit(
        &requested, true, memory_order_release);

/* Processing thread checks at a safe point. */
if (atomic_load_explicit(
        &requested, memory_order_acquire)) {
    /* Cleanup then return CANCELLED. */
}
~~~

If the flag is only used to pass a single cancellation bit, `memory_order_relaxed` may suffice in a design that does not need to publish other data; however, when publication/ownership is complex, choose memory orders according to the full contract. Do not copy an illustrative snippet and assume you already have a safe lifecycle.

### 9.2. Do Not Use a `jlong` Native Handle Without Lifecycle Rules

An API sometimes uses a `long nativeHandle` in Java to point to a C struct containing an atomic cancel flag. That brings its own issues:

- Who creates and frees the struct?
- If a Java thread sends a cancel after the worker has `free`d the struct, a **use-after-free** can occur.
- If the worker finishes and the handle is reused for another object, an old cancel command might affect the wrong operation (**ABA/reuse**).
- How are `cancel()`, `close()`, and native `run()` synchronized?
- On 32/64-bit systems, integer-pointer conversions and ABIs must be correct; do not treat `jlong` as a “safe by default” pointer.
- If JNI native code spawns an auxiliary thread, it must properly handle `AttachCurrentThread`/`DetachCurrentThread` if that thread needs to call into the JVM.

Solutions may require reference counting, a handle table with generations, locks, `RUNNING/CANCELLING/STOPPED` states, and **cleanup after all users of the handle have finished**. For an introductory cancellation lesson, Java `AtomicBoolean` via JNI cleanly separates visibility and avoids having to design the entire native handle lifecycle from scratch.

## 10. Safe Points, Chunks, and Bounding Cancellation Latency

Cooperative cancellation is only as fast as **the nearest check point**. If a C chunk processes a million records for 20 seconds before checking the token, a cancellation request may take about 20 seconds to be acted upon.

A model:

~~~text
time ->
[check][chunk A: 5 ms][check][chunk B: 8 ms][check]
                                      ^
                              cancel requested
                                      |
                                wait until check
~~~

If a native function has logic like:

~~~c
/* Idea: not a standalone C function. */
for (size_t start = 0; start < total; start += chunk_size) {
    if (is_cancel_requested()) {
        cleanup();
        return CANCELLED;
    }

    process_chunk(start, chunk_size);
}
~~~

then token observation latency is primarily governed by the maximum duration of one `process_chunk`, check overhead, CPU scheduling, and cleanup operations. **Tight latency cannot be promised** if `process_chunk` can block indefinitely.

Some rules:

- Choose chunks short enough to meet latency targets without being so small that they cause excessive JNI/atomic overhead.
- Do not poll with a 100% CPU busy-spin if unnecessary; use a signaled event/condition or timed wait.
- Do not trade off consistency: if a chunk is a transaction that cannot be cancelled mid-way, only stop after commit/rollback.
- If using JNI critical array pinning, release with the proper API before calling JNI to poll.
- Record metrics: `cancelRequestedAt`, `cancelObservedAt`, `nativeExitAt`; distinguish delays from polling, I/O, and cleanup.

Example engineering target, **not a JVM guarantee**: “worker checks token after at most 25 ms of CPU work; native wait uses at most a 50 ms timeout; supervisor waits 2 seconds for acknowledgement then escalates if not finished.” These values are chosen by the application and must be measured under realistic conditions.

## 11. When Blocked in Native I/O or a Third-Party C Library

This is the case where a correct token is still **not enough without a safe point**.

### 11.1. Blocking I/O

Suppose C calls `read(fd, ...)` and no data arrives for several minutes. The worker cannot check `cancelRequested` while the syscall is still blocking. Some platform-dependent design approaches:

- Use **non-blocking I/O** or `poll`/`select`/`epoll`/`kqueue` with a finite timeout, checking the token after each round.
- Use the official asynchronous/cancel API if provided by the library or OS.
- A dedicated wake-up mechanism (pipe/eventfd/event/condition) can be used to cancel the wait; races between wake-up, closing the descriptor, and I/O operations must be avoided.
- Configure **timeouts at the native library/driver layer itself**, not just Java's `Future.get(timeout)`.
- On Windows, the I/O model and cancellation APIs have their own specifics; do not assume equivalent Linux POSIX behavior.

Do not arbitrarily call `close(fd)` from another thread and trust that all blocking operations will stop safely and immediately on every OS. You must follow OS/library documentation, manage descriptor ownership, and handle error returns.

### 11.2. Native Third-Party Libraries

If a call like `vendor_process(...)` blocks for a very long time, outer JNI code **cannot poll the token inside it**. Check if the library has:

- a `timeout` or deadline parameter;
- a `shouldCancel` callback;
- a synchronous or asynchronous `requestCancel/abort` API;
- a session-closing API with documented thread-safety;
- the ability to process per batch/stream chunk instead of one monolithic call.

When a vendor library does not support cancellation, do not claim that `Thread.interrupt` provides cancellation capability. If isolation is a system requirement, run that native part in a **child process**: the process can be terminated after a timeout using OS mechanisms, at the trade-off of losing all state of the child process and the responsibility of cleaning up files/temp data/IPC.

### 11.3. GPUs, Accelerators, or Peripheral Devices

Commands already submitted to a device may continue running even if the Java task is cancelled. The contract must define: whether it only stops enqueuing new work, whether running work can actually be cancelled, when buffers/driver handles can be freed, and when the Java caller is notified of completion. Cancelling a Java thread does **not** mean the computation on the GPU has been rolled back.

## 12. Returning Results So the Caller Is Not Misled

Distinguish between **cancellation request recorded**, **native has seen the cancellation**, and **resources have been released**.

A minimal result protocol:

| Status | Meaning | Caller Action |
| --- | --- | --- |
| `COMPLETED` | Native completed the work per contract, including cases where cancel arrived after commit | Accept the result; do not label it `CANCELLED` just because interrupt was called |
| `CANCELLED` | Worker saw the token and exited through confirmed cleanup | Do not use partial output if the contract forbids it |
| `FAILED` | A native/JNI/I/O error occurred, not normal cancellation | Preserve original error info; roll back/clean up appropriately |
| `TIMED_OUT_WAITING` | The waiter timed out, but the worker has not confirmed exit | **Must not assume native has stopped**; do not free resources the worker might still be using |

Design-oriented Java interface example:

~~~java
// Illustrates contract, not a standalone program.
enum Outcome {
    COMPLETED, CANCELLED, FAILED
}

interface CancellableNativeOperation {
    void requestCancel();  // Only sends signal.
    Outcome awaitResult();  // Waits and receives actual result.
}
~~~

If a deadline is needed for `awaitResult`, return a separate `TIMED_OUT_WAITING` status or throw a timeout exception indicating **waiting timed out**, without interpreting it as successful cancellation. Once cancel is declared, decide on partial results, transaction commits, and cleanup of files/native buffers.

A `boolean` is sufficient for the `runUntilCancelled` demo, but in real products, use explicit statuses/exceptions so `FAILED` is not conflated with `COMPLETED` or `CANCELLED`.

## 13. Interaction with `ExecutorService` and `Future.cancel(true)`

A common Java pattern:

~~~java
// Illustrative Java example, incomplete imports/initialization.
Future<?> future = executor.submit(() -> nativeCall());
future.cancel(true);
~~~

`cancel(true)` on a `Future` may attempt to interrupt the executing thread, but **there is no guarantee that `nativeCall()` stops** if it is inside an uncooperative C function. The `Future` state may become cancelled even though the underlying native work has not actually stopped using resources.

Therefore, if a task holds important native state:

1. Each operation has its own cancellation token/handle.
2. When the caller cancels the future, the coordinator **issues a cancellation request to that specific operation** (not just calling `future.cancel(true)`).
3. The native worker polls the token or receives the library's cancel API and **acknowledges upon exit**.
4. The coordinator keeps the native context alive until the worker actually finishes and completes cleanup; do not `free`/close handles mid-use.
5. If a deadline is exceeded, log a “cancellation incomplete” status, isolate resources, or escalate per policy rather than calling it a success.

In particular, `CompletableFuture.cancel(boolean)` does not have the same semantics as forcibly stopping a running task: `CompletableFuture` documentation states that the `mayInterruptIfRunning` parameter has no effect in this implementation because interrupts are not used to control processing. All the more reason to separate **future cancellation state** from **native worker termination**.

### Shutting Down a Service

`ExecutorService.shutdownNow()` typically attempts to interrupt running tasks, but that is still **best-effort**. If many workers are stuck in C, do not expect `shutdownNow` to immediately free native resources. A sensible shutdown protocol: stop accepting new jobs → issue cancel to each operation → wait for acknowledgements up to a deadline → handle uncooperative operations.

## 14. Exceptions, Cleanup, and JNI Thread Rules

### 14.1. Every Exit Path Must Clean Up Owned Resources

Illustrative example of C code using a resource:

~~~c
/* C pseudocode: not a standalone runnable program. */
int result = FAILED;
Resource *resource = open_resource();
if (resource == NULL) {
    return FAILED;
}

for (;;) {
    if (cancel_requested()) {
        result = CANCELLED;
        break;
    }

    if (work_finished()) {
        result = COMPLETED;
        break;
    }

    if (work_failed()) {
        result = FAILED;
        break;
    }
}

close_resource(resource); /* Cleanup before reporting result. */
return result;
~~~

A single-cleanup-exit pattern reduces the risk of forgetting to release on cancellation or error. This is **pseudocode**, contains no definitions for `Resource`/`work_finished`, and is not intended to be copied/compiled verbatim.

With JNI, cleanup may include:

- `ReleaseIntArrayElements`/`ReleasePrimitiveArrayCritical` for acquired array element regions;
- `ReleaseStringUTFChars`/`ReleaseStringChars` for acquired character buffers;
- `DeleteLocalRef` for local JNI references that can be cleaned up early;
- `DeleteGlobalRef` only when no users of the global reference remain;
- freeing `malloc`/`free`, C++ RAII resources, file descriptors, and mutexes according to ownership.

**You cannot replace `Release...` for JNI buffers with `DeleteLocalRef`**, and you cannot `free(jobject)` because the object is still managed by the JVM.

### 14.2. JNI Exceptions

Calls like `GetObjectClass`, `GetMethodID`, and `CallBooleanMethod` can fail or leave a pending Java exception. If a JNI callback fails:

- Check the result/null/`ExceptionCheck`.
- Do not continue along the normal processing path as if the callback succeeded.
- Clean up owned native resources using permitted cleanup APIs.
- Propagate the current exception, or convert it to a clear error per the protocol **without silently clearing the cause**.

The complete example above returns `JNI_FALSE` when a JNI exception is pending; Java will receive the exception before it can trust the boolean value. Do not treat `JNI_FALSE` as a successful business result while a Java exception still exists.

### 14.3. `JNIEnv*` Cannot Be Used Across Threads

`JNIEnv*` is bound to the current thread. If native code spawns its own thread, that thread needs `AttachCurrentThread`/`GetEnv` to obtain its corresponding `JNIEnv*`, and `DetachCurrentThread` when appropriate. Do not pass worker A's `JNIEnv*` to worker B.

JNI local references also cannot be used directly on another thread. If a Java token needs to be accessed from an **auxiliary native thread** that outlives the original call, you must create a valid global reference while the local reference is alive, synchronize ownership, and delete it when no longer in use; use that thread's own `JNIEnv*`. In the demo, the token is **passed as a parameter to the native method and only accessed within the same call and thread**, so a local reference suffices.

### 14.4. Do Not Make Arbitrary JNI Calls Inside Critical Sections

When native code holds a pointer via `GetPrimitiveArrayCritical` or `GetStringCritical`, the JNI contract imposes restrictions to avoid preventing the JVM from performing necessary operations. Polling a token with `CallBooleanMethod` **inside a long critical section** is a risky design that can violate JNI constraints. Break work into small segments and release the critical region before checking for cancellation.

## 15. Common Anti-Patterns

### Anti-pattern 1: “Called `interrupt()`, so the thread definitely stopped”

~~~java
// FLAWED REASONING: native work does not necessarily stop.
worker.interrupt();
nativeContext.close(); // Risk of closing context while C is still using it.
~~~

Correct approach: issue a cancel request, **wait for the signal that the worker has exited**, and only then release the native context per ownership; if waiting times out, record that it has not stopped and escalate via the proper mechanism.

### Anti-pattern 2: “C just calls `sleep`, so Java interrupt will interrupt `nanosleep`”

Java's `Thread.interrupt()` does not define that a native C OS `nanosleep` must throw `InterruptedException`; C does not even have that Java checked exception. A native sleep may be interrupted by an OS signal per OS semantics, but do not rely on that as a general cancellation contract. Replace it with a timed wait that polls a token/notification appropriately.

### Anti-pattern 3: “Changing a plain C variable from a Java thread will automatically be visible to native”

A plain C variable read and written from two native threads without atomics/locks can cause a data race. C `volatile` does not substitute for synchronization. Use `AtomicBoolean` via JNI, `std::atomic`, or `_Atomic` with proper lifetimes.

### Anti-pattern 4: “Future is cancelled means cleanup is done”

The `Future` state and the native worker state are **not necessarily synchronized**. Before freeing buffers, unloading a native library, or reusing a handle, you must wait for native acknowledgement. Otherwise, use-after-free, double close, or partially written results can occur.

### Anti-pattern 5: “Checking cancel at every instruction”

Polling too frequently can cause heavy overhead; polling too rarely slows down UX. Use chunks and safe points suited to the workload, and measure latency with tests. For I/O, wake-up/cancel APIs or timeouts at the blocking layer itself are needed.

### Anti-pattern 6: “Cancelling means throwing any arbitrary exception”

If a native method holds a mutex or buffer, throwing or returning abruptly before cleanup can break invariants. Define non-cancellable regions, rollback/commit, a single cleanup path, and clear statuses/exceptions.

### Anti-pattern 7: “A Java token always stops any C call”

No. If C is inside a blocking third-party library that cannot return to poll, the token will not be observed. You need timeout/cancel support in the native library, callbacks, or process isolation.

### Anti-pattern 8: “The interrupt flag always stays intact”

Some Java blocking APIs may clear the status when throwing `InterruptedException`; `Thread.interrupted()` also clears it. Do not mix interrupts with business tokens without clearly defining how to preserve/restore them. In Java code that catches `InterruptedException` and cannot finish immediately, `Thread.currentThread().interrupt()` may be needed to restore the status per contract, while considering the error flow and caller.

## 16. Review Checklist for a Cancellable JNI Operation

Before taking a long-running JNI operation to production, check:

1. **Who generates the cancellation request?** User, HTTP disconnect, deadline, service shutdown, or executor?
2. **What is the cancellation channel?** Atomic Java token via JNI, native atomic flag, library API, timed wait/event, or IPC?
3. **Is visibility guaranteed?** Are Java Memory Model, C/C++ atomics, and native handle ownership all clear?
4. **Where are the safe points?** In CPU loops, between batches, before commit, after each blocking call? Can any call block indefinitely?
5. **Where will resources be cleaned up?** Is there a single cleanup path for successful completion, cancellation, and failure?
6. **How is the Java interrupt flag handled?** Do any methods clear the flag? Should an interrupt cancel the current operation or every task on the thread?
7. **How is stopping confirmed?** Return value, JNI status, latch, worker termination, completion callback? Is *requested* distinguished from *done*?
8. **Which timeouts apply?** Native I/O/driver timeout, result-waiting timeout, shutdown timeout; no ambiguity.
9. **What if it is uncooperative?** Isolate processes, log and operate escalations, avoid unloading/freeing a running context.
10. **Are races tested?** Cancel before start, during a CPU chunk, while waiting on I/O, right at commit, after completed, during cleanup, and concurrently with closing context.
11. **Have JNI errors been checked?** Use HotSpot `-Xcheck:jni` and test on actual target JVMs/OSes/architectures.
12. **Is there monitoring?** Count cancellations requested, cancellations confirmed, timeouts waiting for native exit, leaks, hung threads, and exceptions.

A minimal test suite should include:

| Test | Expectation |
| --- | --- |
| Cancel before native processes the first chunk | Native sees the token early and does not start unnecessary work |
| Cancel between multiple chunks | Native completes/rolls back the chunk per contract and returns CANCELLED |
| Cancel immediately after completed | Returns COMPLETED if already committed, does not falsely turn into CANCELLED |
| Interrupt without setting token | For a worker that only polls the token, native does **not** return due to interrupt |
| Native exception or Java exception in callback | Does not log a false “cancelled”; cleans up and propagates the error |
| Waiter times out while native is still running | Does not free context, marks waiting timed out, applies policy |
| Cancel concurrently with closing native handle | No double free/use-after-free; ownership is synchronized |
| Worker blocked in vendor API | Verifies real timeout/cancel of the library, not just a Java flag |

## 17. Self-Check Questions

1. Why is `Thread.interrupt()` not a command to kill an arbitrary native C function?
2. Does `Future.cancel(true)` status prove that the JNI worker has released its buffers and returned?
3. In the `NativeCancellationDemo` example, why is `stoppedByInterruptAlone` `false`?
4. Why can `cancel.set(true)` be seen by native code when C calls `AtomicBoolean.get()` via JNI?
5. If C is calling a blocking vendor function without timeout/cancel, does polling the token in the surrounding loop guarantee stopping by the deadline?
6. Why can using a C `volatile int` variable still be wrong when two threads read/write it for cancellation?
7. While `GetPrimitiveArrayCritical` is in effect, should you arbitrarily poll the token using `CallBooleanMethod`?
8. What is required to consider a cancellation **completed**, rather than just **requested**?
9. If an auxiliary native thread wants to use a Java token after the initial JNI invocation returns, can it keep the raw local `jobject`?
10. Why can closing/freeing a native context right after `interrupt` cause a use-after-free?
11. If a cancellation request arrives after data has already been committed, must `CANCELLED` always be returned?
12. If a native library does not support cancellation and may hang, what architectural option allows enforcing a more strongly isolated timeout?

**Summary answers:** (1) interrupt is cooperative and C does not poll by default; (2) no; (3) the worker only exits when the token is true, and the token was not set at the time of checking; (4) `AtomicBoolean`'s volatile semantics and JNI calling the real Java method; (5) no, there must be an API/timeout inside the call; (6) C `volatile` does not replace atomics/synchronization; (7) no, the critical region must be released first; (8) native return/acknowledgement after cleanup; (9) no, a global ref/ownership and proper thread attachment are needed; (10) native code is still using the context; (11) no, it depends on the commit contract; (12) a child process with IPC/timeout and a process termination policy.

## 18. Authoritative References

- [Java SE 17 — `Thread.interrupt`, `isInterrupted`, `interrupted`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html)
- [Java SE 17 — `AtomicBoolean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicBoolean.html)
- [Java SE 17 — `Future.cancel(boolean)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — JNI Functions (`CallBooleanMethod`, critical arrays, exceptions)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
- [Java SE 17 — JNI Invocation API (`AttachCurrentThread`)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html)
- [Java SE 17 — `CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)

**Conclusion:** `Thread.interrupt()` and `Future.cancel(true)` are **interrupt/cancellation requests**, not proof that any native C function has been stopped. A reliable JNI operation must have a **readable cancellation signal**, **safe points**, **proper cleanup/ownership**, and **acknowledgement after native actually returns**. When native code cannot cooperate, **execution-layer timeout/cancellation APIs** or **process isolation** are required; never assume by default that an interrupt will make C exit safely.
