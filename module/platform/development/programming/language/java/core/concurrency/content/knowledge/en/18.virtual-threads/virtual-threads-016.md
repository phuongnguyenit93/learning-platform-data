# Native Methods and Foreign Functions: Virtual Thread Pinning Cases That Still Must Be Evaluated

> Scope: **JVM/JDK-level Java concurrency**, from Java 21 onward; with particular attention to changes in JDK 24 and **JNI** / **Foreign Function & Memory API (FFM)** call paths. The knowledge here applies to plain Java applications without depending on Spring.

## 1. Why is a native/foreign call a special boundary?

A **virtual thread** is a `java.lang.Thread` scheduled by the JVM on a **carrier thread** (platform thread). When a virtual thread waits on an operation for which the JDK supports suspend/unmount, its execution state is saved and the carrier can serve another virtual thread.

However, Java also has to call down into libraries/machine code outside the JVM through two mechanisms:

- **JNI native method:** a Java method declared `native` and implemented in C/C++ code or a platform library. Java still sees the method signature, but the execution code and internal blocking operations reside on the native side.
- **Foreign function:** a call from Java into a function outside the JVM using the FFM API, typically via `Linker.downcallHandle(...)` and `MethodHandle`. FFM provides a stronger API to describe the ABI, represent native memory, and control lifecycles, but a downcall still crosses the Java–native boundary.

A native frame can depend on the OS thread stack, registers, kernel state, native memory, and library thread-local state. The JVM cannot freely relocate or interrupt an executing native call to "unmount and then resume on another carrier" the way it does for some JDK-managed Java blocking operations.

Therefore, **when a virtual thread is executing a native method or foreign function, it can be pinned to its carrier**. If the call returns quickly, the impact is negligible. If it waits for a long time (reading from a device, calling a synchronous library, DNS via a native library, a C API waiting on a lock, a syscall, a blocked JNI callback, etc.), a carrier can be held for a long time even if the application creates many virtual threads.

### Three concepts not to conflate

| Concept | What is happening | Consequence |
|---|---|---|
| **Mount** | The virtual thread is running on a carrier | The carrier is using a CPU/OS thread to serve it |
| **Unmount on wait** | The JDK suspends the virtual thread at a supported point | The carrier is released and can do other work |
| **Pinning** | The virtual thread cannot unmount at the point where it needs to wait | If the wait is long, the carrier is held; throughput may drop |

**A short native call does not automatically become a "pinning bug."** The key risk is **frequency × carrier occupation duration × number of concurrent tasks**, rather than merely the presence of `native`/`downcallHandle` in the source code.

```text
JDK-supported wait path:
Virtual thread -> Java socket read / park -> UNMOUNT -> carrier free
                                               -> resume when ready

Long-blocking native path:
Virtual thread -> JNI/FFM -> native blocking call -> carrier remains occupied
                                              (no safe unmount point)
```

This is a diagram of typical behavior, not a claim that every internal Java call involving native code blocks the carrier. The JDK has special implementations/transitions for many standard blocking APIs; measure the specific execution path.

## 2. Distinguishing JDK 21–23 and JDK 24+

Virtual threads became official in **Java 21 (JEP 444)**. When analyzing pinning, you must state the JDK version:

| Case | JDK 21–23 | JDK 24+ |
|---|---|---|
| Blocking inside a `synchronized` method/block | Can pin the carrier | JEP 491 allows unmounting in common monitor cases |
| Waiting on a monitor / typical `Object.wait()` | Can cause similar limitations | JEP 491 improves how virtual threads wait for and reacquire monitors |
| Long-running/blocking JNI native method | **Still must be evaluated** | **Still must be evaluated** |
| FFM downcall to a blocking C/native function | **Still must be evaluated** | **Still must be evaluated** |
| Native callback (JNI/FFM upcall) returning to Java and calling a blocking API | Can pin while a native frame remains | Still can pin while a native frame remains on the stack |
| Waiting on class initialization or certain special VM regions | Needs observation | Still has special cases needing observation |

**JEP 491 does not mean "Java 24 completely eliminates pinning."** It solves a very important monitor-related issue, but it cannot turn synchronous syscalls and native libraries into automatically suspendable operations. Replacing all `synchronized` blocks with `ReentrantLock` to "fix native pinning" misses the target; changing a Java lock cannot release an OS thread being held inside a native function.

Starting in JDK 22, **the FFM API was finalized under JEP 454**; if you are using JDK 21, FFM is still in preview and the run commands/API may differ. The FFM example in Section 5 uses **JDK 25**, with the platform explicitly noted to avoid version syntax confusion.

## 3. Types of native/foreign paths to inspect

### 3.1. JNI calling a long-blocking I/O or synchronous operation

Example JNI bridge signature:

```java
final class NativeBridge {
    static {
        System.loadLibrary("nativebridge");
    }

    static native int readSensorBlocking();
}
```

*This snippet is only a bridge declaration; running it requires the corresponding native library. It is not a standalone Java program.*

If `readSensorBlocking()` waits 500 ms for device data inside C/C++, the virtual thread calling it is not automatically placed by the JDK onto an I/O wait list to unmount. Thousands of virtual threads calling the method concurrently can tie up many OS threads or cause carrier starvation.

The same applies to cryptographic/hardware token libraries, device drivers, media codecs, specialized file-processing libraries, or a JNI wrapper calling a legacy C library. You need to verify the **actual waiting mechanism**: blocking syscall, mutex/condition variable, polling, callback, or pure CPU computation.

### 3.2. FFM downcall calling a synchronous native function

An FFM call looks like this:

```java
// API illustration; requires creating an ABI-appropriate linker and function descriptor.
MethodHandle function = linker.downcallHandle(symbol, signature);
Object result = function.invokeWithArguments(arguments);
```

Using `Linker` and `MethodHandle` **does not turn** a synchronous C function into non-blocking Java. If the underlying function waits on native I/O or a native lock for 2 seconds, the carrier typically cannot be returned to the scheduler during that interval. With FFM, you must also read the C function's documentation: which operations block, timeouts, interruptibility, thread affinity, thread safety, and callback behavior.

### 3.3. Native calling back into Java (JNI callback / FFM upcall)

```text
Virtual thread
  -> Java wrapper
     -> JNI/FFM native function
        -> native C code
           -> Java callback
              -> LockSupport.park / Thread.sleep / socket read
                 -> cannot unmount while a native frame remains on the stack
```

This is an easy case to overlook: the wait call appears in **Java callback code**, yet the stack still has a native frame underneath it. A normal `Thread.sleep(...)` call can unmount; the exact same operation inside a callback chain from native code can cause the carrier to be held. Whether pinning occurs must be verified on your specific JDK, JVM, JNI/FFM wiring, and real workload.

An FFM **upcall stub** allows C to call back into Java; when a foreign library creates its own thread to invoke the callback, threading and observability rules may differ from a downcall initiated from a virtual thread. Do not assume the callback is definitely running on the same kind of thread; check using `Thread.currentThread().isVirtual()` and actual stack traces.

### 3.4. Native code performing long CPU computation

A native call can occupy a carrier for a long time **without any explicit blocking wait call**. This is a CPU/carrier utilization limit, not necessarily a pinning event caused by a virtual thread trying to unmount and failing. Examples include a native codec processing images for seconds, a continuous C algorithm, or a CPU-heavy cryptographic library. The primary solution is managing CPU-bound concurrency and avoiding unbounded virtual thread creation; looking only at pinning events will miss this bottleneck.

### 3.5. Waiting on native locks, class initialization, and restricted JVM regions

JNI/FFM can call libraries with **native mutexes, condition variables, thread-local storage**, or thread-affinity requirements. Check whether the call path returns quickly or waits for a long time on a mutex/OS primitive. Beyond the native boundary, the JVM still has a few rare situations where a virtual thread cannot unmount, such as waiting on class initialization and special VM regions. Do not attribute all scalability issues to `synchronized` or JNI without stack traces and metrics.

## 4. Distinguishing a "blocked carrier" from the `jdk.VirtualThreadPinned` event

**An important measurement point:** the JFR event `jdk.VirtualThreadPinned` primarily helps detect moments when a virtual thread **attempts to park/block but cannot unmount**, subject to a configurable duration threshold. A native function that blocks inside C for one second can keep a carrier busy for one second **without necessarily emitting a pinned event for that duration**.

For example: a virtual thread is inside C's `sleep(1)` via FFM. It is waiting inside the native call; the JVM may not observe that wait as a Java parking point that emits `jdk.VirtualThreadPinned`. Conversely, if a native frame calls back into Java and Java calls `LockSupport.park(...)`, JFR can record the native frame as the reason unmounting failed.

Therefore:

- **Long and repeated pinned events present**: strong evidence that the carrier is not being released when a virtual thread blocks.
- **No pinned events**: **does not prove** there is no native blocking time or no carrier starvation.
- **Native frames present in the stack**: only a clue; must be combined with duration/frequency and carrier state.
- **Very high virtual thread count**: does not by itself prove a bottleneck; also monitor runnable backlog, CPU, and downstream resources.

When investigating a native path, combine JFR + thread dumps + a native/OS profiler if needed; analyze native execution time as well rather than stopping at a single event type.

## 5. Runnable FFM demo: calling C `sleep` on Linux/x64

This example uses **JDK 25+, Linux/x64**, and the standard C function on POSIX systems. It helps illustrate the difference between **running a native call directly on a virtual thread** and **offloading a blocking native call to a bounded pool of platform threads**. The example does not claim that a single run is guaranteed to emit `jdk.VirtualThreadPinned`.

Create the file **`NativeBoundaryDemo.java`**:

```java
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.invoke.MethodHandle;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import static java.lang.foreign.ValueLayout.JAVA_INT;

public class NativeBoundaryDemo {
    // C: unsigned int sleep(unsigned int seconds);
    // On Linux/x64, unsigned int has a 32-bit layout.
    private static final MethodHandle NATIVE_SLEEP = findNativeSleep();

    private static MethodHandle findNativeSleep() {
        Linker linker = Linker.nativeLinker();
        return linker.downcallHandle(
                linker.defaultLookup().findOrThrow("sleep"),
                FunctionDescriptor.of(JAVA_INT, JAVA_INT));
    }

    private static int callNativeSleep() {
        try {
            return (int) NATIVE_SLEEP.invokeExact(1);
        } catch (Throwable problem) {
            throw new IllegalStateException("Native call failed", problem);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        // Approach 1: call native directly on a virtual thread.
        Thread direct = Thread.ofVirtual().start(() -> {
            System.out.println("direct virtual="
                    + Thread.currentThread().isVirtual());
            System.out.println("direct remaining=" + callNativeSleep());
        });
        direct.join();

        // Approach 2: use a bounded number of platform threads
        // to execute the blocking native part.
        try (ExecutorService nativePool = Executors.newFixedThreadPool(2)) {
            Thread caller = Thread.ofVirtual().start(() -> {
                System.out.println("offload caller virtual="
                        + Thread.currentThread().isVirtual());
                Future<Integer> result = nativePool.submit(() -> {
                    System.out.println("native worker virtual="
                            + Thread.currentThread().isVirtual());
                    return callNativeSleep();
                });

                try {
                    // Future.get() waits via Java API; the virtual caller can unmount.
                    System.out.println("offload remaining=" + result.get());
                } catch (InterruptedException interruption) {
                    result.cancel(true);
                    Thread.currentThread().interrupt();
                } catch (ExecutionException failure) {
                    throw new IllegalStateException(failure.getCause());
                }
            });
            caller.join();
        }
    }
}
```

Compile/run on **JDK 25+, Linux/x64**:

```bash
javac NativeBoundaryDemo.java
java --enable-native-access=ALL-UNNAMED NativeBoundaryDemo
```

When both `sleep(1)` calls complete normally (without an interrupting signal), stdout is:

```text
direct virtual=true
direct remaining=0
offload caller virtual=true
native worker virtual=false
offload remaining=0
```

With C `sleep`, the return value is non-zero if interrupted with remaining sleep time; therefore `remaining=0` is **the result in the uninterrupted case**, not a guarantee across all environments. `defaultLookup()` and `unsigned int` are ABI/platform-dependent; on Windows or another ABI you must choose the appropriate library, symbol, and layout. Do not use this code as-is as a cross-platform demo.

**Explanation:** the direct section performs native blocking on the virtual thread's carrier. The offload section performs native blocking on a **platform worker** of `nativePool`; the virtual caller waits on `Future.get()` and can yield its carrier via the JDK mechanism. A two-worker pool only allows at most two native tasks to run concurrently; it does not shorten `sleep(1)` or turn a C function into a non-blocking one. For some native APIs—especially those requiring thread affinity or callbacks—you must verify whether thread switching is permitted before applying this pattern.

Note that Java's `Future.cancel(true)`/interrupt **does not guarantee** stopping a native syscall or a C library that does not support cancellation. In real systems, use the timeout/cancellation provided by the native API itself when available.

### What are the limitations of this demo?

- Using 2 tasks and `sleep(1)` is only for illustrating the boundary. It **does not** provide a throughput benchmark, p99 latency, or confirmation of the presence/absence of pinning events.
- If running measurements, you must control scheduler parallelism, task count, wait duration, platform pool size, and load level. Do not use a single run result to decide production configuration.
- If a native API returns almost immediately, dispatching through a pool can cost more in queueing/context switching than calling it directly; offloading is primarily for **native calls that can block for a long time and occur frequently**.

## 6. Observing and verifying pinning on a real JVM

### Step 1: confirm the runtime and call paths

Record `java -version`, OS/ABI, native library name/version, JNI vs. FFM, number of connections/devices, and the specific native functions. Check which APIs actually block, have timeouts, use callbacks, require affinity, or use native locks; do not draw conclusions solely from the library name.

### Step 2: enable JDK Flight Recorder

Example with the `NativeBoundaryDemo` program above (JDK 25):

```bash
java --enable-native-access=ALL-UNNAMED \
  -XX:StartFlightRecording:filename=native-recording.jfr,dumponexit=true \
  NativeBoundaryDemo

jfr print --events jdk.VirtualThreadPinned native-recording.jfr
```

The trailing `\` in the shell example is Bash/Linux line-continuation syntax. If using Windows PowerShell, run the `java` command on a single line or use PowerShell's line-continuation syntax.

Events to examine include `jdk.VirtualThreadPinned`, blocking events such as `jdk.SocketRead`/`jdk.ThreadSleep` when available, and CPU/sampling events depending on configuration. On JDKs with the `jdk.VirtualThreadPinned` event, the default threshold is typically **20 ms**; very short events may not be recorded. Adjust the JFR threshold if you need to demonstrate an issue at shorter durations.

On **JDK 21–23**, you can also use `-Djdk.tracePinnedThreads=full` or `short` to find stacks where a virtual thread blocks while pinned. That is a diagnostic tool for older versions; do not assume those options or trace contents remain identical across JDKs.

### Step 3: capture thread dumps under load

```bash
jcmd <PID> Thread.dump_to_file -format=json threads.json
```

`<PID>` is the PID of the running JVM; replace it with the actual number. Thread dumps help inspect many virtual threads and carrier states, but they are a **point-in-time snapshot**, insufficient for measuring duration or identifying native library calls by themselves. If JFR points to native/VM frames, correlate stack traces, timings, and CPU/native profiler samples (e.g., an environment-compatible OS/native profiler). Only use native profilers supported by your environment that can capture the required stack frames.

### Step 4: measure a representative workload

At a minimum, track:

| Measurement group | Question to answer |
|---|---|
| Throughput and p95/p99 latency | With many concurrent tasks, does throughput still scale or does tail latency degrade? |
| CPU / OS thread count / carriers | Is native blocking holding many platform threads while CPU utilization is not correspondingly busy? |
| JFR pinned events | Are there Java wait points that fail to unmount due to native frames? Frequency/duration? |
| Native function wall time / profiler | Is the C function actually waiting on a syscall, a lock, or doing CPU work? |
| Queue length / worker saturation | Is the offload pool becoming congested and pushing latency into the queue? |
| Connection/native resource limits | Have sockets, descriptors, buffers, native memory, or service resources been exhausted? |

Use before-and-after comparisons on the **same JDK, load, and resource limits**, or explicitly note differences when changing JDKs. `jdk.VirtualThreadPinned` is only part of the evidence. If JFR is silent while native wall time rises or OS threads are blocked, continue investigating the native path.

## 7. Mitigating impact while preserving correctness

### Approach A: prefer JDK-managed Java blocking APIs when possible

If the requirement is standard network I/O, consider standard Java APIs compatible with virtual threads so the JVM has an opportunity to unmount while waiting. Moving from blocking JNI to standard Java APIs **can** improve concurrency, but you must verify functional equivalence, timeouts, formats, latency, and side effects. There is no rule that "every Java API unmounts" or "every native call must be removed."

### Approach B: isolate blocking native workloads onto a bounded platform pool

Use a dedicated `Executors.newFixedThreadPool(n)` for native libraries that may block for a long time, letting the virtual caller wait on `Future.get()` or an equivalent result. This **caps the number of OS threads** blocked by the native library; the queue must be bounded/have backpressure and wait times must be managed to avoid trading carrier exhaustion for queue overload. `newFixedThreadPool` uses an unbounded queue by default; in production you must design limits on in-flight tasks/queue size, or appropriate semaphore/admission control.

Do not use this pool just to "pool virtual threads"; the goal is to isolate and control a finite native resource. Do not arbitrarily switch threads for native APIs that require all calls to occur on a single OS thread—such as certain graphics APIs, toolkits, and libraries with thread-local context; always respect the library contract.

### Approach C: limit concurrency at the underlying resource

Use a `Semaphore`, connection pool, bounded worker queue, timeout, or rate limit to manage the number of concurrent native calls. For example, if a library allows at most 8 device sessions, grant only 8 permits even if there are 100,000 virtual threads. Remember to release the permit in `finally`; `Semaphore.acquire()` should happen **before entering the native path** so that waiting for a permit can unmount on the virtual thread.

### Approach D: prefer native APIs with timeouts/asynchronous completion

If a library provides an asynchronous API/callback from its own thread or cancellation support, consider it after evaluating ownership, callback threads, memory lifetime, and Java interaction. An "async" native API can still hold internal locks, spawn expensive threads, or invoke callbacks that retain native frames; you must empirically verify its waiting/completion mechanism.

### Approach E: upgrade the JDK when the bottleneck is monitors, not native code

If JFR shows `synchronized` causing pinning on JDK 21–23, JDK 24+ can address it via JEP 491. However, if a C function is sleeping for 500 ms on a carrier, upgrading the JDK solely for JEP 491 **does not guarantee** resolving the native wait. Classify the root cause accurately before changing `synchronized`, replacing JNI/FFM, or tuning the scheduler.

## 8. Common diagnostic and design mistakes

1. **"There are no `jdk.VirtualThreadPinned` events, so native code isn't blocking."** False: a blocking native syscall can occupy a carrier without emitting a corresponding Java parking event.
2. **"Switching to FFM eliminates JNI pinning."** False: FFM changes the interface and management of foreign calls; a blocking downcall still executes natively on an OS thread.
3. **"Java 24 fixed all pinning."** False: JEP 491 focuses on monitors; native/VM frames still require observation.
4. **"Every native call bottlenecks the system."** False: very fast calls usually have little impact; what matters is duration, frequency, and concurrency.
5. **"Increase `jdk.virtualThreadScheduler.parallelism` as a complete fix."** Changing configuration may mask symptoms in a test but does not remove native blocking or downstream limits; look at the real bottleneck.
6. **"`Future.cancel(true)` definitely cancels the C function."** Not guaranteed. The native API must support cancellation or timeouts according to its own protocol.
7. **"A platform thread pool automatically provides good enough backpressure."** `newFixedThreadPool` has an unbounded queue by default; you must design admission control/backpressure if task volume is uncontrolled.
8. **"You can move a native call to any thread."** Not every native library is thread-safe or free of thread affinity; read the API contract.
9. **"Native memory has GC like the Java heap."** FFM `Arena` and JNI typically require explicit lifetime/ownership management; using a segment after its arena closes or holding an invalid pointer causes severe failures independent of pinning.
10. **"Offloading every native function to a platform pool is always faster."** Offloading also incurs task-queue/context-switching overhead and can increase latency; consider it when native blocking is **genuinely long and frequent**.

## 9. Audit checklist for a JNI/FFM library before deploying Virtual Threads

1. **Map the call path:** from Java task → wrapper → JNI/FFM → C library → syscall/lock/callback → back to Java; mark points that can wait or depend on OS threads.
2. **Classify the native call:** quick/CPU-bound/long blocking/callback/thread-affine; verify timeouts, cancellation, signals, and thread safety.
3. **Lock down versions for measurement:** JDK 21–23 differs from JDK 24+ regarding monitors; FFM is standard from JDK 22. Record ABI, OS, and native library version.
4. **Collect JFR and stack/OS samples:** look for both Java-side pinning and native blocking invisible to JFR events. Do not conclude from a single trace alone.
5. **Bound resources before scaling load:** in-flight native calls, queues, native memory, connection/file descriptors, and downstream capacity.
6. **Compare approaches:** direct virtual-thread call; compatible blocking Java API; bounded native platform executor; native asynchronous API. Check throughput, tail latency, CPU, OS threads, errors, and cancellation.
7. **Finalize design based on data:** fix only proven hotspots; document the conditions under which re-measurement is needed when upgrading the JDK or changing the JNI/FFM library.

## Authoritative references

- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): introduces the official feature in Java 21 and native/foreign limitations.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): monitor changes from JDK 24; does not eliminate all native pinning.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM becomes a standard API in Java 22.
- [Oracle JDK 25 — Virtual Threads](https://docs.oracle.com/en/java/javase/25/core/virtual-threads.html): mount/unmount, native pinning, JFR, and thread dumps.
- [Oracle JDK 25 — Linker API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html): downcalls, layouts, and ABI.
- [Oracle JDK 25 — Memory Segments and Arenas](https://docs.oracle.com/en/java/javase/25/core/memory-segments-and-arenas.html): native memory lifecycle.

**Key takeaway:** Both JNI and FFM can hold a carrier when crossing into native code; what causes harm is **long and frequent waiting** on finite OS thread resources. JDK 24+ fixes pinning caused by common monitors, while native paths must be audited with both Java/JFR **and native/OS observation**, before choosing a different API, bounding concurrency, or offloading in a controlled manner.
