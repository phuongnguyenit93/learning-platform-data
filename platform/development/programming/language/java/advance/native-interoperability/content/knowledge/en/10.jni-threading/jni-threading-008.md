# Impact of Long-Running Native Calls on Virtual Threads and Serviceability

**Context:** Java 21 and later provide **virtual threads** for writing applications that serve many concurrent tasks using straightforward synchronous code. When a task waits on I/O through Java APIs supported by the JVM, the virtual thread is typically **unmounted** from a platform thread (an operating system underlying thread, called a *carrier*) so that the carrier can continue running other tasks. However, when a virtual thread is executing a **JNI native** method or foreign function, it cannot rely on the normal unmount mechanism while that native frame is present. A C call waiting on I/O, a mutex, an external library, or a callback for too long can keep the carrier busy or blocked, reducing the number of other tasks that can be served.

An important consequence: **creating one million virtual threads does not create one million carrier threads**. If many virtual threads are stuck in long-running native calls at the same time, the finite carriers can become a bottleneck. A single short native call is not necessarily a problem; the risk lies in **frequency, wait duration, number of concurrent calls, and load-limiting policies**.

This article focuses on the **virtual thread ↔ carrier ↔ JNI/native code** interaction, its impact on throughput/latency, how to design safe native calls, backpressure, cancellation, monitoring, and a runnable example in **Java 21+ and C11 on Linux**.

## 1. Virtual threads and carriers: the foundational model

A virtual thread is a `java.lang.Thread` object with its own logical stack and Java state, but one virtual thread does not correspond to one dedicated OS thread. The JVM has a scheduler that attaches (mounts) a running virtual thread onto a platform thread (*carrier*). When the virtual thread performs a wait operation through a mechanism the JVM can manage, the JVM can save the virtual thread's continuation and detach (unmount) it from the carrier.

For example, in regular Java code:

```java
Thread t = Thread.startVirtualThread(() -> {
    try {
        Thread.sleep(100);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    }
});
t.join();
```

This is a standalone Java snippet in a context where `java.lang` is imported by default and can be placed inside `main`. On a supported JDK, `Thread.sleep` when run from a virtual thread typically allows the JVM to unmount: the carrier does not have to sit idle waiting out the sleep. This aligns with the goal of serving many requests waiting on I/O.

However, when Java calls:

```java
// Illustrative declaration; nativeSleepMillis is implemented via JNI.
private static native void nativeSleepMillis(int milliseconds);
```

the sequence is:

```text
Virtual thread executes Java code
          |
          v
Mounted on a platform thread (carrier)
          |
          v
Calls nativeSleepMillis(...) -> enters JNI frame
          |
          v
C calls blocking syscall / waits on mutex / C library
          |
          +---- native frame remains on the call stack ----+
          |                                                |
          | carrier is held to execute/wait                |
          | virtual thread does not unmount like           |
          | a VT-friendly Java sleep/I/O                   |
          +------------------------------------------------+
          |
          v
Native call returns -> returns to Java
          |
          v
Virtual thread can continue, then unmount
when encountering a JVM-supported wait operation
```

**Important distinction:** `Thread.currentThread().isVirtual()` can still return `true` when the native call originates from a virtual thread. That does **not** mean the native code is running on a "virtual" OS thread. The C instructions ultimately still execute on an operating system carrier platform thread.

### 1.1. What is pinning?

In the context of virtual threads, **pinning** is the state in which a virtual thread cannot unmount from its carrier in a situation where the JVM could normally release the carrier upon blocking. A native frame (JNI or FFM) is a cause of pinning to take into account.

- **Pinned but very short computation:** usually does not cause a significant problem; the carrier is doing useful work.
- **Pinned and waiting for a long time:** the carrier is occupied without completing other Java work; this is a serviceability problem.
- **Many concurrent pinned calls:** can exhaust carrier scheduler capacity, causing new requests to wait even though many virtual threads exist.
- **Long CPU-bound native work:** holds the carrier for computation while also consuming CPU. This is both a risk of not yielding the carrier and a normal CPU resource limit.

Do not equate **virtual thread blocking** with **carrier blocking**. Java code waiting on socket I/O via virtual-thread-supported APIs can release the carrier; native C code calling `read()`, `poll()`, `nanosleep()`, or waiting on an external library inside JNI does not automatically receive that mechanism.

## 2. Differences between JDK 21–23 and JDK 24+

Regarding unmounting capability, **the JDK version is an important condition**.

| Scenario | JDK 21–23 | JDK 24+ |
| --- | --- | --- |
| Java virtual thread waiting via a VT-friendly API outside a native frame | Can unmount | Can unmount |
| Waiting inside a Java `synchronized`/monitor | Can cause pinning | JEP 491 improves this so virtual threads can wait on monitors without holding the carrier in most relevant scenarios |
| JNI or FFM native method currently on the stack | **Still a source of pinning** | **Still a source of pinning** |
| Native code calls back into Java, then Java code performs a blocking operation | The native frame can still prevent unmounting | The native frame can still prevent unmounting |
| A Java thread waits on `Future.get()` for native work running on **another platform pool** | The virtual thread can unmount while waiting | Similar, depending on whether other sources of pinning exist in the context |

JEP 491, **Synchronize Virtual Threads without Pinning**, was introduced in JDK 24. It resolves pinning caused by Java monitors in the scenarios defined by the JEP. It **does not turn a JNI blocking call into an unmount-capable wait operation**. Therefore, simply upgrading the JDK or replacing `synchronized` with `ReentrantLock` does not solve the root cause when the native function itself waits for a long time.

Do not try to "guess" pinning status from a single stacktrace line. You need to combine JDK version information, native stacks, blocked duration, and actual telemetry.

## 3. Impact on serviceability: throughput, latency, and queueing

A service often has a call path:

```text
HTTP request
  -> virtual thread request handler
  -> Java business logic
  -> JNI call to C library
  -> native I/O / lock / compute
  -> JNI return
  -> Java response
```

When the JNI call is fast, this flow can be reasonable. However, if many concurrent requests wait at the JNI step, carrier threads are held while the server continues receiving incoming requests.

### 3.1. A simple load model

Suppose at the point in time under consideration:

- `P` carrier threads can run tasks on the scheduler in question.
- `N` concurrent tasks all perform a long-waiting native call.
- Each native call takes `T` seconds, and all native calls can genuinely run in parallel at the C layer (no shared mutex or other backend limit).

In this simplified modeling scenario, each carrier only runs one native call at a time, so the number of calls occupying carriers can hardly exceed `P`. The rest may have to wait for a turn to execute. The time to complete all `N` tasks can be approximately **`ceil(N/P) × T`** if they start together, have uniform duration, and there is no carrier compensation mechanism; this is an **intuitive model**, not a measured guarantee of the JVM.

A **hypothetical example for illustration**, not benchmark data:

| Quantity | Illustrative value |
| --- | ---: |
| Available carriers `P` | 4 |
| Concurrent requests needing JNI blocking `N` | 80 |
| Native wait time `T` | 250 ms |
| Idealized number of batches | 20 |
| Time for the last batch according to the model | About 5 s |

During that same time, requests that only need to run lightweight Java logic may also experience increased wait times because carriers available to serve new tasks become scarce.

However, **carrier count is not an immutable constant**; the JVM has its own scheduler, compensation policies, hardware, environment limits, and workload behavior. Do not use the calculation above as an official SLO or limit. It only illustrates why increasing the number of virtual threads **does not automatically create more native processing bandwidth**.

### 3.2. How are throughput and latency affected?

- **Throughput (requests/s):** can decrease or be capped by the number of carriers/threads and the native wait time.
- **Queueing latency:** new requests may sit waiting for CPU/carriers or waiting for the native executor. p95/p99 latency can spike sharply before the average changes much.
- **Tail latency:** when native calls occasionally experience sudden slowdowns, requests sharing the carrier pool suffer cascading effects.
- **Isolation:** one slow native dependency can affect even request types that do not use that dependency if all compete for the shared scheduler.
- **Memory:** waiting virtual threads still retain request state, stack frames, data buffers, and Java references. A large backlog of requests increases memory usage even if the number of OS threads does not grow 1:1.
- **CPU utilization can be low:** carriers are blocked in syscalls/mutexes even when the machine is not using all its CPU. This is a form of **resource starvation** rather than necessarily a CPU bottleneck.

Following the intuitive form of Little's Law, the number of requests in the system `L ≈ λ × W`, where `λ` is the request rate per second and `W` is the time spent in the system. When `W` increases due to native waiting, the backlog of requests can grow if the arrival rate does not decrease. Do not let the request queue grow unboundedly.

### 3.3. Pinning is not the only cause of slowdowns

Distinguish among these:

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Carriers busy in native wait, throughput drops | Native frame holds carrier | Native call latency, carrier stacks, JFR, number of concurrent calls |
| 100% CPU, all requests slow | Heavy JNI computation, CPU-bound Java, GC | CPU profiling, native CPU samples |
| Native calls queueing on a mutex | Global lock in C library | Lock contention, number of threads entering native and lock hold time |
| JNI is fast but results arrive slowly | Downstream DB/HTTP, queue, Java lock | Step-by-step latency tracing |
| Thread/heap count grows even though native is fast | Too many concurrent requests, buffers, and Java references | In-flight count, queue depth, heap/native memory |
| Service p99 increases after deploy | Changes in JDK, JNI library, thread pool, workload | Compare versions/configurations and before–after metrics |

The right problem to solve is **controlling the work that actually consumes or holds a finite resource**, not just changing the thread type.

## 4. Types of native calls that require special care

### 4.1. Native code blocking on OS I/O or a third-party library

For example, JNI calling a C function waiting on a socket, file, native RPC SDK, or device transaction:

```c
/* Illustrative native method body, not a standalone C file. */
JNIEXPORT jint JNICALL
Java_NativeApi_readBlocking(JNIEnv *env, jclass clazz, jint fd) {
    (void)env;
    (void)clazz;

    unsigned char buffer[4096];
    ssize_t count = read(fd, buffer, sizeof buffer);
    if (count < 0) {
        return -1;  /* Needs a real error contract. */
    }
    return (jint)count;
}
```

The snippet above assumes POSIX `read()` and needs `<unistd.h>`, along with a proper contract for partial reads, EINTR, errno, buffers, and type sizes; it is **illustrative code**, without full error handling. Even though the OS call can block while the CPU is idle, the virtual thread still has a native frame and the carrier can be held.

### 4.2. Native code holding a mutex or semaphore

A C library with a global mutex or internal serialized resource will force multiple JNI calls to wait for the lock. If 100 virtual threads simultaneously call a native method that holds a lock, failing to limit concurrency can cause **many carrier threads to wait on the same resource**, incurring greater cost than the benefits of virtual threads.

Place an access limit before entering native code, or organize a queue with a finite number of native workers. Do not simply increase the carrier pool size to "work around" a lock that serializes all work anyway.

### 4.3. JNI calling back into Java (callback)

A native method can call `CallVoidMethod`/`CallObjectMethod` to execute Java code and then return to C. Even though the callback is Java, **the native frame is still underneath on the call stack** until it returns. If the callback executes `Thread.sleep`, waits on a future, or performs I/O, the environment still has a source of pinning from the native frame.

Therefore, the "C calls Java and then Java sleeps" approach does not automatically release the carrier. To handle things truly asynchronously, you must **finish the current JNI call** and organize appropriate completion/lifecycle management; do not keep the native stack while waiting.

### 4.4. CPU-intensive native functions

An encryption, compression, image processing, or machine learning algorithm in C running for 500 ms is not an I/O wait; it genuinely consumes CPU. Virtual threads do not make CPU computations run faster or increase the number of cores. The native function holds the carrier for the duration of the computation; if too many tasks are submitted, the number of CPU-ready threads and cache contention can also increase.

In the CPU-bound case, a **bounded executor** with parallelism close to CPU resources or C library limits is usually easier to control. Do not treat the number of virtual threads as the number of native computations running in parallel.

### 4.5. JNI critical sections and GC

If JNI uses `GetPrimitiveArrayCritical` or `GetStringCritical`, the JNI specification requires keeping the critical region short and avoiding blocking operations or arbitrary JNI calls inside that region. Depending on the VM, critical access can involve pinning/copying and affect garbage collection. A long-running native call **does not mean every native call blocks GC**, but a critical region held for a long time can create other JVM impacts beyond carrier starvation.

To reduce risk: only hold JNI critical pointers for the scope actually needed, pair `ReleasePrimitiveArrayCritical` or `ReleaseStringCritical` properly, and do not perform I/O/network waits inside a critical region.

## 5. Runnable example: direct JNI sleep vs. offloading to a platform worker

We will write a Java 21+ program with JNI calling POSIX `nanosleep()`. The example has two paths:

1. **Direct:** a virtual thread directly calls `nativeSleepMillis(50)`. This is the pattern that can hold a carrier during the native call.
2. **Offload:** a virtual thread submits the native work to a **bounded platform thread pool**, then waits on `Future.get()` from Java. The virtual thread can unmount while waiting for the future if there are no other pinning sources; the native call runs on an explicitly chosen platform worker.

The example **only illustrates thread identity and the execution path**; a 50 ms duration and a single task do not prove production throughput. The stdout lines are deterministic; actual scheduling and timing depend on the JVM/operating system.

### 5.1. Java file: `NativeImpactDemo.java`

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class NativeImpactDemo {
    static {
        System.loadLibrary("nativeimpact");
    }

    private NativeImpactDemo() {}

    private static native void nativeSleepMillis(int milliseconds);

    public static void main(String[] args) throws Exception {
        // Each Java task is run in a virtual thread.
        try (ExecutorService virtual =
                 Executors.newVirtualThreadPerTaskExecutor();
             ExecutorService nativeWorkers =
                 new ThreadPoolExecutor(
                     2, 2, 0L, TimeUnit.MILLISECONDS,
                     new ArrayBlockingQueue<>(4),
                     Executors.defaultThreadFactory(),
                     new ThreadPoolExecutor.AbortPolicy())) {

            Future<Boolean> direct = virtual.submit(() -> {
                nativeSleepMillis(50);
                return Thread.currentThread().isVirtual();
            });
            System.out.println("direct-caller-virtual=" + direct.get());

            Future<Boolean> offloaded = virtual.submit(() -> {
                Future<Boolean> work = nativeWorkers.submit(() -> {
                    nativeSleepMillis(50);
                    return Thread.currentThread().isVirtual();
                });
                // Virtual caller waits on a Future using a Java API.
                return work.get();
            });
            System.out.println("offloaded-worker-virtual="
                               + offloaded.get());
        }

        System.out.println("done");
    }
}
```

Design details:

- `Executors.newVirtualThreadPerTaskExecutor()` is supported from Java 21 and creates one virtual thread per task. It is **not** meant to limit the number of native calls in the system.
- `new ThreadPoolExecutor(2, 2, ...)` creates a pool of at most 2 platform workers and a bounded queue of 4 elements. In the example running the two cases sequentially, there is no queue overflow; in production, `AbortPolicy` throws `RejectedExecutionException` when the pool + queue are full.
- `Executors.defaultThreadFactory()` creates platform threads, unlike a virtual-thread factory. Therefore, the native call in the offload path runs on a platform worker; the virtual caller waiting on Java `Future.get()` can be unmounted from its carrier by the scheduler.
- `Future.get()` is also the point where exceptions from the worker are received via `ExecutionException`; do not forget to handle `InterruptedException` and deadlines in a real service.
- `try-with-resources` closes the executors when exiting the scope; in server applications, pools usually live with the component and are shut down in an orderly manner rather than created/destroyed per request.

### 5.2. Generating the JNI header

```bash
javac -h . NativeImpactDemo.java
```

This command generates `NativeImpactDemo.class` and `NativeImpactDemo.h`. The compiler-generated JNI prototype has the form:

```c
JNIEXPORT void JNICALL
Java_NativeImpactDemo_nativeSleepMillis(
    JNIEnv *, jclass, jint);
```

This is an **illustrative signature excerpt**, not a replacement for the generated header file. Because the native method is `static`, the second parameter is `jclass`; Java `int` corresponds to `jint`.

### 5.3. Complete C file: `NativeImpactDemo.c` (Linux/POSIX)

```c
#define _POSIX_C_SOURCE 200809L

#include "NativeImpactDemo.h"
#include <errno.h>
#include <time.h>

static void throw_java(JNIEnv *env,
                       const char *type,
                       const char *message) {
    jclass exception_type = (*env)->FindClass(env, type);
    if (exception_type != NULL) {
        (*env)->ThrowNew(env, exception_type, message);
        (*env)->DeleteLocalRef(env, exception_type);
    }
}

JNIEXPORT void JNICALL
Java_NativeImpactDemo_nativeSleepMillis(
    JNIEnv *env, jclass clazz, jint milliseconds) {
    (void)clazz;

    if (milliseconds < 0) {
        throw_java(env, "java/lang/IllegalArgumentException",
                   "milliseconds must be non-negative");
        return;
    }

    struct timespec requested = {
        .tv_sec = milliseconds / 1000,
        .tv_nsec = (long)(milliseconds % 1000) * 1000000L
    };
    struct timespec remaining;

    while (nanosleep(&requested, &remaining) == -1) {
        if (errno == EINTR) {
            requested = remaining;
            continue;
        }
        throw_java(env, "java/lang/IllegalStateException",
                   "nanosleep failed");
        return;
    }
}
```

`nanosleep()` illustrates a C function that waits at the OS level and can be interrupted by a signal (`EINTR`). The `while` loop continues sleeping for the remaining time after being interrupted by a signal. This is a POSIX example for Linux, not an ISO C API; on Windows, a different native wait API must be used.

**Key takeaway:** Java `Thread.interrupt()` is not automatically translated by JNI into canceling this `nanosleep()`. The C program can continue waiting even if the virtual thread has been marked interrupted. For production, you need a native API with timeouts and an explicitly designed cancellation mechanism, rather than treating Java interruption as a promise to automatically stop every blocking C call.

This code calls `FindClass` and `ThrowNew` when there is no pre-existing pending Java exception; afterward, it deletes the local reference to the class. JNI operations do not turn a native wait into a virtual-thread-friendly operation.

### 5.4. Build/run with JDK 21+ on Linux

Place `NativeImpactDemo.java` and `NativeImpactDemo.c` in the same directory. `JAVA_HOME` must point to the running JDK and contain `include/jni.h`:

```bash
javac -h . NativeImpactDemo.java

cc -std=c11 -Wall -Wextra -Wpedantic -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  NativeImpactDemo.c -o libnativeimpact.so

java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. NativeImpactDemo
```

When run successfully, the **exact stdout** is:

```text
direct-caller-virtual=true
offloaded-worker-virtual=false
done
```

The first line only indicates that the Java code wrapping the native call ran in a virtual thread. The second line confirms that the Java code running in `nativeWorkers` is a platform thread. Neither line asserts the exact number of milliseconds nor that the VM necessarily emits a JFR pinning event.

If you encounter `UnsatisfiedLinkError`, check the `libnativeimpact.so` name, `java.library.path`, CPU architecture, the newly generated JNI header, and compiler/JDK compatibility. On Windows/macOS, you need to change the build flags, shared library name, and sleep API; do not copy the `linux` include path verbatim. On newer JDKs with native access warnings, `--enable-native-access=ALL-UNNAMED` is the option for applications running on the classpath; in a JPMS application, grant permission to the appropriate named module.

### 5.5. What does this example prove?

The example confirms the chosen thread model; it **does not measure pinning directly**. To evaluate performance impact, you must generate concurrent load with realistic request rates, measure latency/throughput/queue depth, and observe carrier activity. Do not compare a single `Thread.sleep(50)` in Java against a single `nanosleep(50)` in C to claim native code is slower by a constant factor; the risk mainly arises when **many calls wait concurrently**.

## 6. Why offloading helps and its limits

Offloading means the virtual request thread **does not directly execute the JNI blocking call**. It submits the work to a bounded pool of platform workers and waits for completion using a Java API that supports virtual threads.

```text
Virtual request handler
      |
      v
submit(native-work) ----> bounded queue ----> platform worker
      |                                       |
      | Future.get() / async await            | JNI
      | virtual thread can unmount            | native blocking call
      v                                       |
carrier can run another request <---- result/exception
```

In return, the system **still needs OS threads to execute the blocking C calls**. The benefit is that the number of OS threads held by native code is controlled and does not directly occupy the carrier pool serving Java virtual threads. This is a method of isolation and load control, not a way to make a C wait suddenly become nonblocking.

### 6.1. Do not use an unbounded queue as a "solution"

`Executors.newFixedThreadPool(n)` creates a finite number of workers, but in its common configuration it has an **unbounded queue**. If requests arrive faster than the native processing capacity, the queue can grow indefinitely. Adding more virtual threads does not make native code process faster either; at that point, heap/latency can deteriorate.

A `ThreadPoolExecutor` with a **bounded queue** and an explicit **rejection policy** limits the backlog of work. In the example, at most 2 executing tasks plus 4 waiting tasks are accepted in the pool at a given time; the seventh request (when the queue and workers are full) can be rejected. These numbers are for illustration; production must measure and choose limits based on the capacity of the native dependency, CPU, memory, and latency targets.

An API server should translate `RejectedExecutionException` into a clear **overloaded/busy** signal or apply a backpressure mechanism with a deadline, rather than silently running on the caller thread via `CallerRunsPolicy`: if the caller is a virtual request thread, running the native task directly on the caller can reintroduce the pinning risk you are trying to avoid.

### 6.2. Sizing the native worker pool

There is no single number for every system:

- **CPU-bound** native work: limit according to CPU cores, library resources, and the number of computations that truly run concurrently.
- **I/O-bound** native work without an async API: the pool can be larger than the core count, but is still bounded by OS threads, file descriptors, native memory, backend concurrency, and cancellation/timeout.
- Native library with a **global lock**: adding workers may only cause more threads to queue up waiting for the lock.
- Non-**thread-safe** native library: must serialize or fix the contract; do not attempt concurrent calls.
- Native library with a rate limit/token quota: apply a concurrency cap or rate limiter independent of the thread pool size.

Measure **service time**, queue wait, p95/p99, rejection rate, CPU, native allocations, and backend utilization before choosing a size. Do not assume `Runtime.getRuntime().availableProcessors()` is the actual number of running carriers, nor assume the number of native workers should equal the number of virtual threads.

### 6.3. Separating resource bottlenecks from thread bottlenecks

Moving to a platform pool can free up Java carriers, but it will not necessarily increase throughput if the native resource can only process one thing at a time. For example, if C code has a global mutex protecting a device: a pool of 2 or 32 workers still goes through the mutex one by one. In that case, you must address contention, batching, or a native asynchronous API; do not chase thread count.

A design can combine: virtual threads for appropriate HTTP/JDBC parts, a dedicated native executor for blocking C, a bulkhead/concurrency limit per library, timeouts, bounded retries, metrics, and a circuit breaker at the boundary.

## 7. Moving to a native async API: reducing JNI frame hold time

If the C library supports **true asynchrony**, you can design JNI to only perform a **quick work-initiation** operation and return to Java immediately, while completion occurs when C/OS finishes processing.

Example architectural flow:

```text
Virtual request thread
      |
      v
JNI nativeStart(request, completion-id)
      |
      +--> create/copy data that must outlive the call
      +--> submit native asynchronous operation
      +--> RETURN immediately, without waiting for the result
      |
      v
Java CompletableFuture / callback registry
      |
      | Java waits for completion via a VT-friendly API
      v
Native completion thread/event loop
      |
      +--> attach JVM thread if calling back into Java
      +--> create necessary local refs
      +--> complete result / exception
      +--> clean up local/global references per lifecycle
      v
Virtual request thread resumes when completion arrives
```

**Important limitation:** "start async" that internally still waits for completion before returning **solves nothing**. Only when the native entry point returns quickly and the waiting is managed outside the request's carrier does it reduce the hold time of the request's native frame.

An async design must specify:

1. **Data lifetime:** do not retain pointers to Java arrays/strings after the JNI call unless using permitted JNI mechanisms; copy native data or use global refs at the right time. Local `jobject`/`jclass` references must not be stored long-term or passed to another thread.
2. **Thread attachment:** a native-created thread that wants to call JNI must obtain `JavaVM *`, call `AttachCurrentThread`, and use its own thread-specific `JNIEnv *`; `DetachCurrentThread` when finished according to JVM rules.
3. **Complete exactly once:** results, errors, or cancellation must not complete twice; use a state machine/atomic transitions.
4. **Cancel/timeout:** a Java-side timeout does not automatically stop the native operation; you need a native cancel handle if supported, or a mechanism to discard late results and clean up resources.
5. **Backpressure:** do not turn the async queue into an unbounded request list; an in-flight limit is still needed.
6. **Exceptions:** if a Java callback throws an exception on a native thread, you must check/clear it or report the error per the contract before continuing normal JNI calls.
7. **Thread safety:** synchronization, ownership, and callback release must not resurrect closed resources.

This option requires more design work than a bounded platform pool. Use it when the native SDK genuinely benefits from async support, or when the required load is high enough to justify the integration cost.

## 8. Cancellation, interruption, timeouts, and serviceability

A good service must have request deadlines; however, with JNI, **Java-side deadlines and native deadlines are not automatically aligned**.

Suppose a virtual request thread is calling C and is interrupted:

```java
// Illustrative, outside an active native call.
requestThread.interrupt();
```

All of the following must be distinguished:

- Java `Thread.interrupt()` sets an interrupt request according to Java thread semantics. It does **not** guarantee stopping a waiting C syscall or a third-party native function.
- `Future.cancel(true)` can mark the Future as canceled and request interruption of the Java worker; JNI code is not obligated to exit a blocking C call unless the library is designed for cancellation.
- `Future.get(timeout, unit)` only limits **how long the caller waits for the result**; it does not promise that the native operation has finished.
- `CompletableFuture.orTimeout(...)` only changes the completion/timeout state of the future per the API; native C code may continue running.
- If a timeout occurs while native code is still active, you need **late-result handling** and must keep resources alive until native code truly no longer needs them. Do not free buffers for native code while it can still dereference them.

Illustrative timeout structure (illustrative excerpt; `nativeWorkers` is an existing executor, `nativeOperation` is a system-defined callable):

```java
Future<Result> result = nativeWorkers.submit(nativeOperation);

try {
    return result.get(500, TimeUnit.MILLISECONDS);
} catch (TimeoutException timeout) {
    result.cancel(true); // Does not guarantee the running C call is stopped.
    throw timeout;
}
```

This is **not a standalone program**; it requires `Result`, `nativeWorkers`, and `nativeOperation`. It only illustrates the hazard: if the native operation does not support cancellation, the request's cleanup path **must not immediately free** native buffers that are still in use by the operation.

A reliable design uses **timeouts at the JNI/native SDK level** (if supported), **request-level deadlines**, and a **lifetime state machine**. For a native library that can block indefinitely with no way to cancel, a separate worker process with process-level isolation/termination capability may be needed rather than trusting that Java thread cancellation will solve it.

## 9. JNI and threads: mistakes not directly related to carriers that increase risk

A long-running native call also extends the lifetime of JNI resources created during the call.

### 9.1. Local references and GC

Local `jobject` references created by `GetObjectArrayElement`, `NewStringUTF`, `FindClass`, etc. normally expire automatically when the native method returns. However, in a very long-running native loop, if local refs are continuously created without `DeleteLocalRef` or popping a local frame, the JNI reference table can grow; objects remain strongly held and are harder for GC to reclaim when no longer needed.

Solution: release refs each iteration with `DeleteLocalRef`, or use `PushLocalFrame`/`PopLocalFrame` in batches. Do not let a long native wait hold onto JNI references that are no longer needed.

### 9.2. `JNIEnv *` is thread-local

`JNIEnv *` is only valid in the current thread; do not save this pointer to pass to another C worker or to a completion callback on another thread. A native-created thread must attach and obtain its own `JNIEnv *`. Do not call Java `Thread.currentThread().isVirtual()` from a native-attached thread and infer that it is on the original request's virtual thread; once the native task has switched threads, the context does not transfer automatically.

### 9.3. Holding monitors, locks, or critical pointers while blocking

Native code can acquire a JNI monitor via `MonitorEnter`, or operate on critical array pinning/copying. If it waits for a long time before the matching `MonitorExit`/release, it can prolong lock contention and affect GC. Design short scopes and avoid network I/O or unbounded waits while holding such resources.

### 9.4. JNI errors and native errors are two separate channels

When C encounters a timeout from a native library, it needs to map it to an explicit Java exception or result. `ExceptionCheck` only reports **a pending Java exception**; it does not automatically detect `errno`, return codes, or native timeouts. If `ThrowNew` is needed, check that no other exception is already pending so as not to lose the original information.

## 10. Observing pinning and services in production

To conclude that native calls are causing a bottleneck, monitor both **JVM-level** and **application-level** metrics:

| Signal | What to observe |
| --- | --- |
| JNI call duration histogram | p50/p95/p99, number of calls exceeding deadline, operation type |
| In-flight native calls | Number of running native work items; number of platform workers actually busy |
| Native executor queue | Queue length, queue wait time, rejections |
| Service throughput | Completed requests/s, not just incoming request rate |
| Request latency | End-to-end request p95/p99, by endpoint and dependency |
| Virtual threads | Number running/waiting, Java stacks where requests are blocked |
| Carrier/platform threads | OS thread states, stacks, number blocked in C |
| CPU and native resources | CPU time, mutex contention, file descriptors, native heap |
| GC | Pause times, Java heap, and JNI references/critical regions if any |
| Timeout/cancel | Number of requests timed out while native work continues running |

### 10.1. JDK Flight Recorder (JFR)

On supported JDKs, JFR has the `jdk.VirtualThreadPinned` event. Oracle documentation describes this event as used to observe cases where a virtual thread is pinned while performing certain **blocking operations**, typically with a default duration threshold of around 20 ms. You can start a recording and then print it:

```bash
java -XX:StartFlightRecording=filename=native-impact.jfr,dumponexit=true,settings=profile \
  --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. NativeImpactDemo

jfr print --events jdk.VirtualThreadPinned native-impact.jfr
```

**Interpretation warning:** a direct C call to `nanosleep()` might **not appear** as a `jdk.VirtualThreadPinned` event depending on how the JVM records blocking. A JFR event is not a counter for every nanosecond of every JNI call. The absence of a pinning event **does not prove** that native code is not holding a carrier. For direct JNI, combine timers around the call, thread sampling, native profiling, and active caller counts.

An event in a Java callback context may record a reason such as `Native or VM frame on stack`; what matters is that the stack and duration show where the carrier was not released. Specific event fields vary by JDK.

### 10.2. Thread dumps and profilers

For a running Java process with a known PID:

```bash
jcmd <PID> Thread.dump_to_file -format=json threads.json
```

This is an **illustrative command**; replace `<PID>` with the actual PID; do not type literal `<PID>` in the shell. A thread dump can show waiting virtual threads, mounted virtual threads, and native frames at the stack level where they can be captured. On supported JDKs/VMs, use JFR and a native CPU profiler or OS thread sampling to trace wait times inside C libraries.

**Do not draw conclusions from a single sample.** A profiler might sample right when a task has just started; to understand long-tail behavior, you need many samples and per-request tracing.

### 10.3. Controlled load testing

Compare at least two execution paths with the **same work**:

1. **Direct JNI on a virtual thread.**
2. **Offloading JNI to a bounded platform executor, with the virtual thread waiting on completion.**

Keep the same native library, data, wait times, and dependency limits; measure across multiple concurrency levels (e.g., 1, 4, 16, 64, 256). Collect p50/p95/p99, throughput, native in-flight count, worker utilization, and queue wait. Alongside this, include a Java-only sleep/I/O baseline to observe unmounting capability when no native frame is present.

Do not apply load test results from Linux to Windows, macOS, or a different JDK without verification. Scheduler tuning and native libraries can have a significant impact.

## 11. JNI design checklist for services using virtual threads

**Before deployment:**

1. List all JNI native methods called from request virtual threads and check whether they block, lock, sleep, perform I/O, or do long CPU work.
2. Determine the normal and worst-case duration of each call; if there is no deadline/timeout in the native API, treat this as a service risk.
3. Check thread-safety and concurrency limits of the C library, global mutexes, memory pools, file descriptors, and downstream backends.
4. Choose direct JNI (when short), a bounded platform pool (when sync-blocking), or an async native API with completion (when the workload justifies the investment).
5. Apply backpressure with a limit on **running native calls + waiting requests**; do not use an unbounded queue.
6. Define the policy when the pool is overloaded: rejection, timeout, or bounded retry; avoid caller-runs accidentally performing blocking JNI on a carrier.
7. Specify cancellation and native resource lifecycles: `Thread.interrupt`/`Future.cancel` is not native cancellation by default.
8. Clean up JNI refs, arrays, strings, local frames, and native allocations on all error/success paths; do not hold critical pointers across I/O waits.
9. Do not share `JNIEnv *` across threads; use global references properly if an async worker needs to retain a Java object across calls.
10. Measure carrier contention, request latency, native call duration, queue depth, and JFR; test on both JDK 21–23 and JDK 24+ if the product supports multiple runtimes.
11. Keep Java APIs waiting on a `Future` or native result **outside the native frame** when you want the virtual thread to unmount while waiting.
12. Do not use increasing the number of virtual threads as a way to increase the capacity of a C library with fixed throughput.

**Rule of thumb:** virtual threads are very useful when a large number of requests wait using Java APIs capable of yielding the carrier. However, if a request enters a **long-running JNI native call**, the carrier can be held until native returns. Measure the type of wait, limit the number of executing JNI calls, isolate blocking work, or use true native async and enforce deadlines. The goal is for the service to continue processing other requests even when a native dependency is slow.

### References

- [Oracle JDK 21 — Virtual Threads, scheduling, pinning, and JFR](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Oracle JDK 25 — Virtual Threads, native pinning, and diagnostics](https://docs.oracle.com/en/java/javase/25/core/virtual-threads.html)
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491)
- [Java SE 21 — JNI Design Overview](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html)
- [Java SE 21 — JNI Functions, references, and critical regions](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html)
