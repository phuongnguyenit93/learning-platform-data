# Coordinating Reentrant Callbacks and Avoiding Holding Locks Across the Java/C Boundary

## Objectives and Context

When Java calls C code via JNI (Java Native Interface), the C code can call back into a Java method (*callback*). That callback may in turn call C, running on the same thread or on another native thread. Therefore, a seemingly linear `Java → C` call can in practice become `Java → C → Java → C`, or even repeat across multiple levels. The rules below also apply in terms of design to *downcall/upcall* invocations of the Foreign Function & Memory API (FFM); FFM's syntax and JDK version differ from JNI.

After this lesson, learners should be able to:

1. Distinguish **synchronous/reentrant callbacks on the same thread** from **asynchronous callbacks from another thread**.
2. Explain deadlocks caused by non-reentrant C mutexes, Java monitors held while waiting for callbacks, and lock-order inversion between the two runtimes.
3. Design a protocol of **prepare state → release lock → call across boundary → callback updates state**.
4. Preserve data correctness, resource lifecycle, error handling, and task cancellation even when a callback occurs immediately, multiple times, or after a request is no longer valid.
5. Test and diagnose callback scenarios that cause hangs without creating an indefinitely hanging test.

## 1. Properly Understanding "Reentrancy" Across Java/C

Consider the execution path:

```text
Java Thread T1: service.run()
  └─ nativeCall()                    Java → C
       └─ CallVoidMethod(callback)  C → Java
            └─ callback.onEvent()
                 └─ nativeQuery()   Java → C (reentrant)
```

* **Synchronous reentrancy:** C invokes the callback before the original native call returns. With a normal JNI `CallVoidMethod`, the callback runs on **the exact thread calling JNI**. The stack has multiple Java/C frames; the outer state may still be "in mid-operation".
* **Callback on a separate native thread:** C emits an event from a worker thread attached to the JVM. The original Java thread may be waiting for the result or may have already returned. At that point, mutexes/monitors held on another thread genuinely block the callback.
* **A reentrant lock does not mean callback safety:** Java `synchronized` and `ReentrantLock` allow **the same thread** to re-acquire **that same lock**. However, the callback may observe incomplete data invariants, cause unexpected recursion, or require a lock held by **another thread**. A standard (default) `pthread_mutex_t` must not be assumed to be a recursive mutex; re-locking it can cause deadlock or mutex-type-dependent behavior.

Java monitors and C's `pthread_mutex_t` are **two different locking mechanisms**. Protecting a variable with a Java monitor does not automatically protect a native variable with a C mutex, and vice versa. If an operation must coordinate both sides, a clear state protocol and synchronization order are required.

### Three Typical Failure Scenarios

**A — C calls Java while still holding a C mutex:**

```text
T1: C lock(M_C)
T1: C → Java callback.onEvent()
T1: callback → JNI readNativeState()
T1: C tries to lock(M_C) again → may self-deadlock
```

Switching to a recursive mutex only masks the same-thread case; the callback can still observe half-finished state and form a lock cycle with another thread. The fundamental fix is to **release M_C before calling Java**.

**B — Java holds a monitor and waits for a callback from another thread:**

```text
T1: synchronized(M_J) → call C → wait for worker completion
T2: native worker → Java callback → needs synchronized(M_J)
T1: waits for T2       T2: waits for T1's M_J
```

Even `synchronized`'s reentrancy cannot save this because T1 and T2 are two different threads. Timeouts can detect the situation, but **do not replace** fixing the dependency graph.

**C — Lock-order inversion (ABBA):**

```text
T1: holds M_J → waits for M_C
T2: holds M_C → Java callback → waits for M_J
```

Even though each lock is used syntactically correctly, the two threads form a wait cycle. A system-wide lock ordering is one solution when critical sections cannot be separated, but at a boundary with arbitrary callbacks, a more durable approach is to **avoid making calls that can trigger callbacks while holding a lock**.

## 2. Safe Protocol at the Boundary

Design rule: **Every call across Java/C must be treated as potentially reentrant, blocking, throwing, or triggering callbacks, unless the API contract guarantees otherwise.**

A sample operation:

```text
Java                                  C
-----                                 -----
lock(stateLock)
  check preconditions
  record requestId and PENDING state
  snapshot data to send
unlock(stateLock)
      JNI invoke(requestId, snapshot) ─────►
                                      lock(nativeMutex)
                                        briefly read/update state
                                      unlock(nativeMutex)
                          ◄────────── callback(requestId, result)
lock(stateLock)
  validate requestId is still valid
  record COMPLETED/FAILED once
unlock(stateLock)
perform follow-up notification/action outside the lock
```

Points to maintain:

- **Register pending state before calling native.** A synchronous callback may occur right inside the JNI call, before `invoke` returns. If `pending` is created after `invoke`, the callback will not find the request.
- **Snapshot data under the lock, use the snapshot after releasing the lock.** The snapshot should be immutable or have clear ownership; do not pass references to memory that could be freed or modified concurrently.
- **The callback performs a brief state transition.** Only after releasing the lock should you invoke listeners, call other JNI methods, perform potentially blocking logging, dispatch results to a queue/executor, or complete a future.
- **Do not wait for completion while still holding a monitor/mutex.** `Future.get`, `join`, `CountDownLatch.await`, I/O, RPC, or waiting on a C condition must stay outside the lock region, unless a very specific protocol proves it safe.
- **Establish explicit callback rules:** inline or on another thread, once or multiple times, event ordering, thread affinity, permission to call back into the API, error propagation, cancellation, and the "no callbacks under lock" rule.
- **Check locks in higher-level callers.** Even if the JNI wrapper method is not `synchronized`, the caller may still be holding a monitor when invoking the wrapper.

A quick reference table:

| Risky operation under a lock | Alternative |
| --- | --- |
| `synchronized(lock) { nativeCall(); }` | Prepare state inside `synchronized`, call `nativeCall` after exiting the block. |
| `pthread_mutex_lock` → `CallVoidMethod` → unlock | Snapshot/update native state, unlock, then `CallVoidMethod`. |
| Callback both mutates state and calls external listeners | Commit briefly under the lock, take the follow-up work, and dispatch after unlock. |
| Calling thread holds a lock while waiting for callback | Wait outside the lock; use timeout/cancellation and explicit state. |
| Arbitrarily locking Java then C, and vice versa | Break lock chains across the boundary; if lock nesting is unavoidable, define a single global order and verify all paths. |

## 3. Standalone Java 17 Example: Inline Callback and Worker Callback

The following example **simulates** the native boundary using a `Gateway`, to clearly show where the lock is released without needing to compile a C library. This is a complete Java program, filename `CallbackBoundaryDemo.java`:

```java
public final class CallbackBoundaryDemo {
    @FunctionalInterface
    interface Gateway {
        void invoke(Runnable callback) throws InterruptedException;
    }

    private final Object stateLock = new Object();
    private int pending;
    private int completed;

    void dispatch(Gateway gateway) throws InterruptedException {
        // Publish state first: the callback may run inline.
        synchronized (stateLock) {
            pending++;
        }

        // Important: do not hold stateLock when crossing the "native boundary".
        gateway.invoke(this::onEvent);
    }

    private void onEvent() {
        synchronized (stateLock) {
            if (pending <= 0) {
                throw new IllegalStateException("Unexpected callback");
            }
            pending--;
            completed++;
        }
        // If you need to call another listener/native method, do it outside the lock.
    }

    String status() {
        synchronized (stateLock) {
            return "completed=" + completed + ", pending=" + pending;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        CallbackBoundaryDemo demo = new CallbackBoundaryDemo();

        demo.dispatch(Runnable::run); // Callback immediately on the calling thread.
        System.out.println("inline: " + demo.status());

        demo.dispatch(callback -> {
            Thread worker = new Thread(callback, "native-simulation");
            worker.start();
            worker.join(); // Wait outside stateLock.
        });
        System.out.println("worker: " + demo.status());
    }
}
```

Compile/run:

```bash
javac CallbackBoundaryDemo.java
java CallbackBoundaryDemo
```

Expected output:

```text
inline: completed=1, pending=0
worker: completed=2, pending=0
```

In the first call, the callback occurs before `dispatch` returns; in the second, it runs from another worker. Both acquire `stateLock` because `dispatch` already released the lock. If you move `gateway.invoke(...)` **inside** `synchronized (stateLock)`, the inline case may still run due to Java monitor reentrancy, but the worker case with `join` will deadlock: the calling thread waits for the worker, and the worker waits for the monitor. **Do not use this dangerous change as a test without a timeout.**

The example only illustrates locking and callback ordering. A real system must handle `invoke` failures, interruption, duplicate/late callbacks, cancelled requests, and pending state; it must never assume each callback always corresponds to one `pending`.

## 4. Real JNI/C Example: C → Java → C Reentrancy Without Holding a Mutex

The Linux example below uses Java 17+, JNI, and `pthread_mutex_t`. Java calls `emit()` into C. C increments a counter under a mutex and then **releases the mutex before** calling back `onEvent(int)`. The callback calls `readSequence()` into C, acquiring **that same mutex** to read. If the mutex were held during `CallVoidMethod`, this reentrant path could hang.

File `JniCallbackDemo.java`:

```java
public final class JniCallbackDemo {
    static {
        System.loadLibrary("jnicallback");
    }

    private final Object stateLock = new Object();
    private int lastId = -1;
    private int lastNative = -1;

    private native void emit();
    private native int readSequence();

    // JNI invokes the callback on the thread that entered emit().
    private void onEvent(int eventId) {
        int observed = readSequence(); // Java -> C a second time.
        synchronized (stateLock) {
            lastId = eventId;
            lastNative = observed;
        }
    }

    public static void main(String[] args) {
        JniCallbackDemo demo = new JniCallbackDemo();
        demo.emit(); // Do not hold stateLock around the native call.
        synchronized (demo.stateLock) {
            System.out.println("event=" + demo.lastId
                    + ", native=" + demo.lastNative);
        }
    }
}
```

File `jni_callback.c`:

```c
#include <jni.h>
#include <pthread.h>

static pthread_mutex_t native_mutex = PTHREAD_MUTEX_INITIALIZER;
static jint sequence = 0;

JNIEXPORT void JNICALL
Java_JniCallbackDemo_emit(JNIEnv *env, jobject self) {
    // C-side critical section: only operate on native state.
    pthread_mutex_lock(&native_mutex);
    jint event_id = ++sequence;
    pthread_mutex_unlock(&native_mutex);

    // Must not hold native_mutex when calling back into Java.
    jclass type = (*env)->GetObjectClass(env, self);
    if (type == NULL) {
        return; // The JVM already has a pending exception if the lookup failed.
    }

    jmethodID on_event =
        (*env)->GetMethodID(env, type, "onEvent", "(I)V");
    if (on_event != NULL) {
        (*env)->CallVoidMethod(env, self, on_event, event_id);
    }
    // DeleteLocalRef is a JNI operation permitted when an exception is pending.
    (*env)->DeleteLocalRef(env, type);
}

JNIEXPORT jint JNICALL
Java_JniCallbackDemo_readSequence(JNIEnv *env, jobject self) {
    (void)env;
    (void)self;

    pthread_mutex_lock(&native_mutex);
    jint result = sequence;
    pthread_mutex_unlock(&native_mutex);
    return result;
}
```

On **Linux** with JDK and GCC installed, in the directory containing both files:

```bash
javac -h . JniCallbackDemo.java
gcc -std=c11 -shared -fPIC -pthread \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -o libjnicallback.so jni_callback.c
java -Djava.library.path=. JniCallbackDemo
```

Result with one `emit` in a fresh process:

```text
event=1, native=1
```

Implementation notes: set `JAVA_HOME` to point to the JDK used for compilation; library names/extensions and build commands differ on Windows/macOS. `javac -h .` generates the JNI header matching the class/method names; the example uses a class **without a package**, so the C symbols are as shown above. Production code must check the return codes of `pthread_mutex_lock/unlock`, manage errors, and handle native resource lifecycles; this section focuses on lock ordering and callbacks.

**C counterexample (illustrates the bug only, do not include in a runnable program):**

```c
pthread_mutex_lock(&native_mutex);
(*env)->CallVoidMethod(env, self, on_event, event_id);
pthread_mutex_unlock(&native_mutex); // May never reach here.
```

The `onEvent` callback calls `readSequence` and then waits for `native_mutex`, which is held by the outer `emit` call. This is the same thread, yet a native mutex must not be assumed to be reentrant. Similarly, in Java do not write `synchronized (stateLock) { emit(); }` because the callback or a worker may need that same monitor again.

## 5. When the Callback Actually Runs on a Separate C Thread

The JNI example above invokes the callback **synchronously on the Java calling thread**, so the `JNIEnv *env` passed in by the JVM is already valid. If the C library spawns its own `pthread` and then calls Java, you must additionally consider:

1. Store the appropriate `JavaVM *`, use `AttachCurrentThread` to obtain a `JNIEnv *` **on the exact thread performing the callback**, and call `DetachCurrentThread` when the self-attached native thread finishes its work. Never pass a `JNIEnv *` from one thread to another.
2. If a Java object must survive past the return of the initial native method, use a JNI **global reference** (`NewGlobalRef`) with explicit creation/deletion rules (`DeleteGlobalRef`). Do not retain a local `jobject` reference across the lifetime of an asynchronous callback.
3. Do not hold a C mutex when calling `AttachCurrentThread`, invoking a Java callback, waiting for a callback, or performing potentially blocking work. Do not hold a Java monitor while waiting for a native worker.
4. Design shutdown: mark `closing`, stop emitting new events, drain/handle in-flight callbacks, complete cancellations/timeouts, and release global refs and C resources **after** ensuring callbacks no longer use them.
5. Determine where the callback runs: if the callback manipulates UI or a dedicated executor, dispatch the event to the appropriate executor. Enqueuing must be designed so that it does not block while holding a mutex.

With JNI, a Java exception thrown inside a callback becomes a **pending exception** on the JNI thread. After `CallVoidMethod`, native code can use `ExceptionCheck` to detect it, or let the exception propagate back to Java when the native method returns. Do not arbitrarily call disallowed JNI APIs while an exception is pending; if you intentionally call `ExceptionClear`, there must be a policy to translate/record the error rather than silently swallowing the exception. In the example above, `DeleteLocalRef` is a permitted cleanup operation and C returns immediately.

In particular, the region between `GetPrimitiveArrayCritical` and `ReleasePrimitiveArrayCritical` has strict JNI constraints: do not call other JNI functions or perform operations that may block waiting for a Java thread. Therefore, **no callbacks, no blocking locks, and no blocking I/O** while holding a critical pointer. For regular native memory, lifecycle, race, and synchronization rules still need to be designed explicitly.

## 6. State, Ordering, and Lifecycle Under Reentrant Callbacks

A design that only "releases the lock before callback" is still insufficient if the data protocol is not tight. Requests should be modeled by ID and states, for example:

```text
CREATED → REGISTERED/PENDING → COMPLETED
                       ├──────→ FAILED
                       └──────→ CANCELLED/TIMED_OUT
late or duplicate callback → check ID/state → ignore or record in a controlled manner
```

- **Register before calling:** generate `requestId`, store the callback/future/`PENDING` state, and only then call C. Inline callbacks are handled just like normal callbacks.
- **Single state transition:** under a brief lock or via appropriate CAS/atomics, only one path wins the transition from `PENDING` to a terminal state. Duplicate callbacks do not complete a future twice or free a buffer twice.
- **Tolerate arbitrary ordering:** a callback may occur before the native call returns, or multiple callbacks may arrive in an order different from submission order. Use IDs/version numbers (*generation*) to discard events from stale sessions.
- **Separate state updates from external actions:** extract the list of listeners/results to notify while holding the lock, **release** it, and only then invoke listeners or `CompletableFuture.complete`, because a completion handler may run immediately on the calling thread and re-enter the system.
- **Clear ownership:** who allocates/frees C buffers, when Java is allowed to read them, and can callbacks arrive after `close()`? Logical cancellation does not automatically stop running C code; there must be a stop/quiescence protocol before freeing.
- **Do not conflate memory models:** `volatile`/monitors/atomics in Java guarantee visibility according to the Java Memory Model for Java variables; C mutexes/atomics protect C state according to C/native rules. Coordinating state across the boundary requires a documented publish/snapshot/copy protocol; do not treat two separate locks as a shared memory barrier. Standalone `volatile` also does not protect compound multi-field operations.

If lock nesting is truly unavoidable in an internal branch, establish a formal lock order such as `M_J before M_C` and prove that **every** call path, including callbacks and error cleanup, obeys it. For arbitrary callbacks from C into Java, the rule "do not call across the boundary while holding a lock" is usually easier to reason about than a global lock order.

## 7. Common Failures and How to Test Them

| Symptom | Cause to investigate | Remediation |
| --- | --- | --- |
| Hangs only when a C callback calls back into a native function | `CallVoidMethod` runs while still holding a C mutex; the mutex is re-acquired. | Snapshot state, unlock before callback; avoid using a recursive mutex as a default patch. |
| Hangs only when a callback runs on a native worker | Java thread holds a monitor during `join/get/await`; the worker needs that monitor. | Release the monitor before waiting; callback commits state inside a brief locked region. |
| Works single-threaded but hangs under load | ABBA, hidden lock order via helpers, listeners, or exceptions. | Draw the thread/lock wait graph; audit both callback and cleanup paths. |
| Callback reports "unknown request" | `pending` state was registered after calling native; callback ran inline. | Register/publish state before crossing the boundary. |
| Double completion, use-after-free | Duplicate callback or arrival after timeout/close. | State machine keyed by ID/generation, single completion, ownership and quiescence. |
| Deadlock does not appear in Java thread dump | Thread is blocked in `pthread_mutex_lock` or a native syscall. | Combine `jcmd <pid> Thread.print -l` with native backtraces (`gdb`/`lldb`) when appropriate. |

**A minimal test suite** should include:

1. An inline callback directly inside the native call that calls back into the C API again; verify no deadlock and valid state ordering.
2. A callback from another native thread while the Java caller is waiting for the result, with a bounded timeout; verify the caller no longer holds the monitor.
3. Two threads running `Java → C` and `C → Java` concurrently, attempting to trigger inverted lock ordering; run repeatedly with a barrier/latch.
4. A callback throwing an exception, JNI lookup failure, and cancellation paths: every branch releases locks, loses no errors, and does not use freed references.
5. Duplicate/late callbacks, closing the module during a callback, and testing native thread self-attach/detach.

Concurrency tests should have a **bounded timeout** to detect hangs and collect evidence without letting CI hang indefinitely. To pinpoint root causes, log `requestId`, thread name/id, `lock/unlock` points, and `Java→C`/`C→Java` direction; do not invoke a potentially blocking logger inside a sensitive locked section.

## 8. Pre-Integration Checklist

- [ ] The callback contract specifies inline/async, thread, reentrancy, multiplicity, ordering, and errors.
- [ ] No Java monitor or C mutex is held across a call that can trigger callbacks or block.
- [ ] All pre-crossing state changes are committed/published; callbacks can find the request even when running inline.
- [ ] Callbacks only commit data briefly under a lock; all listener calls, JNI calls, `complete`, waits/I/O run outside the lock.
- [ ] A lock-order policy exists for any genuinely unavoidable nested locks.
- [ ] JNI `JNIEnv` matches the thread; local/global refs, pending exceptions, and attach/detach follow proper lifecycles.
- [ ] Cancellation, timeouts, duplicate/late callbacks, and safe memory deallocation rules are in place.
- [ ] Tests cover synchronous, multi-threaded, nested reentrancy, error, and shutdown cases; observability covers both Java and native stacks.

**Rule of thumb:** bring state to a consistent point **before** crossing the boundary; **release locks** before letting Java/C code call into each other; callbacks **check and record state briefly**, then continue potentially reentrant actions outside the lock.

### References

- [Oracle JNI Specification — JNI Functions (Call Methods, MonitorEnter/Exit, Critical Arrays)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
- [Oracle JNI Specification — Invocation API (AttachCurrentThread, DetachCurrentThread)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html)
- [Java Language Specification — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html)
