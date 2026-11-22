# Do Not Share JNIEnv or Local References Across Threads

> **Context:** Java Advance → Native Interoperability → Threading with JNI. This lesson explains the boundary between Java threads and native threads when using the Java Native Interface (JNI): `JNIEnv*` belongs to the current thread, local-reference `jobject`/`jclass` handles also belong to their thread and lifetime scope, while `JavaVM*` and **global references** are the appropriate mechanisms when handing work off to another native thread.

## 1. The core problem: one JVM has many threads, but each thread has its own JNI context

When Java calls a `native` method, the JVM transfers control to C/C++ code and passes in a `JNIEnv*` pointer. This pointer allows native code to call JNI functions such as `FindClass`, `NewStringUTF`, `CallObjectMethod`, or `ExceptionCheck`.

**Mandatory rule:** `JNIEnv*` is only valid for **the thread that owns it**. Do not store a pointer received on thread A into a global variable and use it on thread B. The JVM may attach per-thread data and state to `JNIEnv`. Nor should you assume the pointer can be reused after a native thread has called `DetachCurrentThread`.

Java objects passing through JNI use **reference handles**:

- **Local reference** (`jobject`, `jstring`, `jclass`, `jarray`, ...): only valid within **the thread that created the reference** and within **the JNI local frame lifetime**. Do not pass a raw local reference to another native thread.
- **Strong global reference:** created with `NewGlobalRef`, can be used from threads **attached to the same JVM**, as long as the global ref remains valid. You must call `DeleteGlobalRef` at the right time to avoid keeping the object alive too long.
- **Weak global reference:** created with `NewWeakGlobalRef`; the object may be lost to GC. To use it safely, first promote it to a strong local/global reference using `NewLocalRef`/`NewGlobalRef` and check for `NULL`.
- **`JavaVM*`:** represents a JVM, usable from different native threads to call `GetEnv`, `AttachCurrentThread`, and `DetachCurrentThread`. It does **not** replace `JNIEnv*` when calling functions that operate on Java objects.

### Correct and incorrect diagrams

```text
JAVA THREAD A                NATIVE THREAD B

JNIEnv *envA   --X--------->  use envA: WRONG, envA belongs to A
jobject localA --X--------->  use localA: WRONG, local handle belongs to A

JavaVM *vm     ------------>  AttachCurrentThread(vm, &envB)
                                  |
                                  v
                              B's JNIEnv *envB

NewGlobalRef(envA, localA)
       |
       +---- globalRef ----->  use globalRef via envB: CORRECT
                                  |
                                  v
                              DetachCurrentThread(vm)

Thread A: after B no longer uses globalRef,
          DeleteGlobalRef(envA, globalRef)
```

**Sharing a global reference does not mean the object is thread-safe.** A reference only solves **reachability and keeping the object from being collected by GC**. If the Java object has mutable state, the Java Memory Model, `synchronized`, locks, atomic types, or message passing still need to be applied.

## 2. Classification table of what can be passed to another thread

| JNI component | Can it be used directly on another native thread? | Reason and proper approach |
|---|---|---|
| `JNIEnv *envA` | **No** | Bound to thread A; on B obtain `JNIEnv *envB` via `AttachCurrentThread` or `GetEnv` if B is already attached |
| `JavaVM *vm` | **Yes** | JVM-level handle; used to attach/detach/getEnv per thread |
| Local `jobject localRef`, `jstring`, `jclass` | **No** | Only valid within its thread/local frame; create `NewGlobalRef` when handing off work |
| `jobject globalRef` (strong) | **Yes**, if still alive | B must attach and use it with B's own `JNIEnv*`; the owner must delete the global ref when no longer needed |
| `jweak weakRef` | Conditionally | GC can collect the object; create a new strong local/global ref and check the result before using |
| `jmethodID`, `jfieldID` | Can be cached/shared while valid | These are opaque IDs, **not** `jobject` and not local refs; tied to the class/class loader lifecycle |
| Pointers from `GetStringUTFChars` or `GetByteArrayElements` | Follows its own lease contract, not a `jobject` | Follow release/pinning/ownership rules; do not treat C pointers as local/global Java references; avoid lifetime misuse |
| Plain C values like `int`, copied byte buffers | Yes if properly synchronized | No JNI reference needed, but C/C++ memory and data races must still be managed |

**Type-name trap:** `jobject` does not itself indicate whether it is **local**, **global**, or **weak global**. All three can share the same C type yet have **different lifetime rules**. Calling `GetObjectClass` returns a **local** `jclass`, not a global one, even though `jclass` looks like "shared metadata".

## 3. Lifecycle of JNIEnv, JavaVM, and attachment

There are two different scenarios.

### Case A — thread created by Java

When `new Thread(...).start()` runs Java code and enters a `native` method, the JVM **has already attached that thread** and passes a valid `JNIEnv*` into the native method. Another Java thread calling the same native method will receive **its own** JNI environment.

```c
// Illustrative snippet. Each time Java calls a native method,
// the JVM provides a valid env for the executing thread.
JNIEXPORT void JNICALL Java_Example_nativeWork(
        JNIEnv *env, jobject thiz) {
    // Only use env/thiz within this thread and JNI local frame.
}
```

When the native callback finishes, the JVM handles the local frame for that call. **Do not call `DetachCurrentThread` directly inside a native method called by Java**: the thread still has Java frames on the call stack and the attachment mechanism belongs to the JVM.

### Case B — thread created manually with pthread/std::thread

A `pthread` created by native code **is not automatically attached to the JVM**. To call JNI from that thread:

1. Have a valid `JavaVM*`. From an already-attached native entrypoint, call `(*env)->GetJavaVM(env, &vm)`; or in library code, receive `JavaVM` when `JNI_OnLoad` is called.
2. Inside **the new native thread itself**, call `(*vm)->GetEnv(vm, (void**)&env, JNI_VERSION_1_6)` to check. If `JNI_EDETACHED`, call `AttachCurrentThread` to obtain that thread's `JNIEnv*`.
3. Use **the env just obtained on the current thread** to manipulate Java objects; only use JNI references valid on this thread (locals it created or live globals).
4. Release local refs/memory/locks, and handle pending Java exceptions.
5. If this native thread attached itself, call `DetachCurrentThread` **before the thread exits**, when no Java methods remain on the call stack.

C API:

```c
// Illustrative snippet inside a native thread.
JNIEnv *env = NULL;
jint rc = (*vm)->GetEnv(vm, (void **)&env, JNI_VERSION_1_6);

if (rc == JNI_EDETACHED) {
    if ((*vm)->AttachCurrentThread(vm, (void **)&env, NULL) != JNI_OK) {
        // No valid JNIEnv; do not call JNI.
        return;
    }
    // This thread is responsible for DetachCurrentThread before exiting.
} else if (rc != JNI_OK) {
    // JNI_EVERSION or other error: do not use env.
    return;
}

// Only use env on the currently running thread.
// Only Detach if this thread actually attached in the branch above.
```

The snippet above is intentionally **not a standalone C program**, illustrating `GetEnv`/`AttachCurrentThread`. When a thread is already attached, calling `AttachCurrentThread` again retrieves the existing environment and does **not** change its daemon status. `AttachCurrentThreadAsDaemon` creates a daemon thread if newly attaching; this choice affects the JVM lifecycle, and does **not** exempt you from proper resource cleanup/detaching.

### Important condition pairs

- `JNI_OK`: the returned `JNIEnv*` can be used for **the current thread**.
- `JNI_EDETACHED`: the thread is not attached yet and must attach if it wants to call JNI.
- `JNI_EVERSION`: the requested JNI version is not supported; do not proceed as if `env` were valid.
- `DetachCurrentThread` does not "delete Java objects": it ends the attachment and invalidates the thread's local references. Global refs stay alive until deleted.
- A native thread attached as **non-daemon** can keep the JVM from exiting; manage startup/shutdown carefully.

## 4. Two anti-patterns: code you must not run

### Mistake 1 — storing JNIEnv in a global variable

```c
// ANTI-PATTERN: DO NOT RUN.
static JNIEnv *cachedEnv;

JNIEXPORT void JNICALL Java_Bad_setEnv(JNIEnv *env, jclass cls) {
    cachedEnv = env;
}

// On another pthread:
jclass c = (*cachedEnv)->FindClass(cachedEnv, "java/lang/String");
// WRONG: cachedEnv belongs to the thread that called setEnv, not the current pthread.
```

Fix this by storing/passing **`JavaVM*`**, then obtaining a valid `JNIEnv*` on each thread via the Invocation API. Even if pointer values numerically appear the same between two runs, you cannot rely on address comparison to break thread-confinement rules.

### Mistake 2 — passing a local reference directly through a queue

```c
// ANTI-PATTERN: DO NOT RUN.
static jobject saved;

JNIEXPORT void JNICALL Java_Bad_enqueue(JNIEnv *env, jclass cls, jobject obj) {
    saved = obj; // obj is a local ref received by this JNI call.
}

// Another thread:
// (*workerEnv)->CallVoidMethod(workerEnv, saved, callbackId);
// WRONG: saved was created on another thread and may expire when the native call returns.
```

**Fix:** right on the thread that owns the local reference, create `jobject shared = (*env)->NewGlobalRef(env, obj)`; pass **shared** to the worker and transfer ownership clearly; the worker must attach to the JVM before calling JNI. Only call `DeleteGlobalRef` when all workers have stopped using `shared`. Do not delete the global ref immediately after enqueuing, as that creates a use-after-delete in the worker.

## 5. Complete example: passing a String across a pthread validly

This example runs on **Java 17+, Linux with GCC and pthreads**. Java creates **two caller threads**; each caller enters JNI and asks a native `pthread` to read `String.length()`. The native method:

- Receives `JNIEnv*` and a local `jstring` on the caller.
- Calls `GetJavaVM` to obtain the VM-level handle.
- Calls `NewGlobalRef` **before creating the pthread** so the object survives across the thread boundary.
- The worker calls `AttachCurrentThread` and uses **the worker's own env**.
- The worker calls the Java method `String.length()` through the global reference; cleans up the class local reference; detaches.
- The caller calls `pthread_join` to wait for the worker to finish, then calls `DeleteGlobalRef`.
- The two callers use **two separate task structs**; no global native state variable is shared.

### 5.1. File `JniThreadDemo.java`

```java
public final class JniThreadDemo {
    static {
        System.loadLibrary("jnithreads");
    }

    private static native int lengthOnNativeThread(String value);

    public static void main(String[] args) throws InterruptedException {
        String[] output = new String[2];

        Thread callerA = new Thread(
                () -> output[0] = "A = " + lengthOnNativeThread("Lan"),
                "caller-A");
        Thread callerB = new Thread(
                () -> output[1] = "B = " + lengthOnNativeThread("JNI"),
                "caller-B");

        callerA.start();
        callerB.start();

        callerA.join();
        callerB.join();

        // Print after join for deterministic output regardless of thread scheduling.
        System.out.println(output[0]);
        System.out.println(output[1]);
    }
}
```

`String` is used as immutable data in this lesson, so no concurrent content-update issue arises. Two different elements of `output[]` are written by the two callers; the `join()` calls ensure `main` observes the updates before printing. If JNI throws an exception from a caller thread without catching it, the exception is handled by the uncaught exception handler; the normal example assumes the build succeeds and JNI operations do not fail.

### 5.2. Generating the JNI header

```bash
javac -encoding UTF-8 -h . JniThreadDemo.java
```

This command generates `JniThreadDemo.class` and `JniThreadDemo.h`. Use the compiler-generated header to avoid typos in the `Java_JniThreadDemo_lengthOnNativeThread` symbol name or parameter signature.

### 5.3. File `JniThreadDemo.c`

```c
#include <jni.h>
#include <pthread.h>
#include "JniThreadDemo.h"

typedef struct {
    JavaVM *vm;
    jobject valueGlobal;  // Strong global JNI reference.
    jint length;
    int error;
} Task;

static void throwState(JNIEnv *env, const char *message) {
    jclass type = (*env)->FindClass(
            env, "java/lang/IllegalStateException");
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
        (*env)->DeleteLocalRef(env, type);
    }
}

static void *nativeWorker(void *arg) {
    Task *task = (Task *) arg;
    JNIEnv *env = NULL;  // Independent of the caller's JNIEnv.

    if ((*task->vm)->AttachCurrentThread(
            task->vm, (void **) &env, NULL) != JNI_OK) {
        task->error = 1;
        return NULL;
    }

    jclass stringClass = (*env)->GetObjectClass(
            env, task->valueGlobal);
    if (stringClass == NULL || (*env)->ExceptionCheck(env)) {
        task->error = 2;
        goto cleanup;
    }

    jmethodID lengthId = (*env)->GetMethodID(
            env, stringClass, "length", "()I");
    if (lengthId == NULL || (*env)->ExceptionCheck(env)) {
        task->error = 3;
        goto cleanup;
    }

    // Java String.length() returns the number of UTF-16 code units.
    task->length = (*env)->CallIntMethod(
            env, task->valueGlobal, lengthId);
    if ((*env)->ExceptionCheck(env)) {
        task->error = 4;
    }

cleanup:
    // Pending exceptions on the worker do not automatically propagate to the caller.
    // In this example, print diagnostics, clear the pending exception,
    // and report the error via task->error.
    if ((*env)->ExceptionCheck(env)) {
        (*env)->ExceptionDescribe(env);
        (*env)->ExceptionClear(env);
    }
    if (stringClass != NULL) {
        (*env)->DeleteLocalRef(env, stringClass);
    }
    if ((*task->vm)->DetachCurrentThread(task->vm) != JNI_OK) {
        task->error = 5;
    }
    return NULL;
}

JNIEXPORT jint JNICALL Java_JniThreadDemo_lengthOnNativeThread(
        JNIEnv *env, jclass owner, jstring value) {
    (void) owner;

    if (value == NULL) {
        throwState(env, "value must not be null");
        return 0;
    }

    // Task lives on the caller's stack and survives past pthread_join.
    Task task = {0};
    if ((*env)->GetJavaVM(env, &task.vm) != JNI_OK) {
        throwState(env, "GetJavaVM failed");
        return 0;
    }

    // Must create a strong global ref BEFORE handing off to another thread.
    task.valueGlobal = (*env)->NewGlobalRef(env, value);
    if (task.valueGlobal == NULL) {
        if (!(*env)->ExceptionCheck(env)) {
            throwState(env, "NewGlobalRef failed");
        }
        return 0;
    }

    pthread_t thread;
    if (pthread_create(&thread, NULL, nativeWorker, &task) != 0) {
        (*env)->DeleteGlobalRef(env, task.valueGlobal);
        throwState(env, "pthread_create failed");
        return 0;
    }

    // The example has one valid joinable pthread and exactly one join site.
    if (pthread_join(thread, NULL) != 0) {
        // Unsafe to abandon Task on the stack while the worker might still be running.
        (*env)->FatalError(env, "pthread_join failed");
        return 0; // Unreachable: FatalError terminates the JVM.
    }

    // Worker has stopped using the global ref: caller can delete it.
    (*env)->DeleteGlobalRef(env, task.valueGlobal);

    if (task.error != 0) {
        throwState(env, "Native worker failed");
        return 0;
    }
    return task.length;
}
```

**What makes this example reference-safe?**

1. `value` is a local `jstring` belonging to the caller JNI thread. `value` is not placed into `Task` to be passed to the worker.
2. `NewGlobalRef` is called on the caller using **the caller's env**; `task.valueGlobal` is then passed via `pthread_create`.
3. `JavaVM*` is the appropriate handle for the worker to attach. `nativeWorker` creates a **new `JNIEnv *env` variable on its own stack**, receiving the worker's environment from `AttachCurrentThread`.
4. The worker uses `task.valueGlobal` via its own env, whereas `stringClass` returned by `GetObjectClass` is **the worker's local reference**. The worker calls `DeleteLocalRef` before detaching; it does not send `stringClass` back to the caller.
5. `pthread_join` waits for the thread to finish so `task.length` and `task.error` are ready, and the caller knows when it is allowed to call `DeleteGlobalRef`.
6. Keeping `Task` on the stack is only safe because the code **always waits for the thread to finish**. If switching to asynchronous processing where the native method returns immediately, the task must be allocated with its own lifetime and a defined deallocation site; do not pass the address of a stack variable outside the function.

In the demo, if `pthread_join` unexpectedly fails, the code uses `FatalError` to prevent returning and unwinding the stack while the worker might still be running. This is a **fail-fast policy for an unrecoverable invariant in a synchronous example**; real applications need solid thread/task lifetime and shutdown management, rather than relying on aborting for routine error handling.

**About exceptions:** a Java exception raised when the worker calls `CallIntMethod` is **pending on the worker thread**, and does not automatically transfer to the caller Java thread. The example logs diagnostics and clears the exception on the worker, records `task.error`, and the caller throws `IllegalStateException` after joining. Applications that need to preserve the cause can create a **global reference to the Throwable** on the worker, then convert it to a local ref/throw on the caller and clean up the global ref, with strict ownership and locking protocols; never pass a local exception ref directly to the caller.

### 5.4. Compiling the library and running

Assuming `JAVA_HOME` points to JDK 17+ and GCC is available:

```bash
gcc -std=c11 -fPIC -pthread -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libjnithreads.so JniThreadDemo.c

java -Djava.library.path=. JniThreadDemo
```

With JDK 24+ on the classpath, grant JNI native access explicitly:

```bash
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. JniThreadDemo
```

**stdout on a successful run:**

```text
A = 3
B = 3
```

The output is printed on `main` after the two Java `join()` calls, so the order is **fixed**, even though the two callers and two native workers may be scheduled in different orders. When building on macOS or Windows, you must adjust the `.dylib`/`.dll` library name, JNI platform headers, OS-appropriate pthread/thread-creation mechanisms, and linker flags; the GCC command above is specific to Linux.

## 6. Why is a local reference both a thread *and* a frame boundary?

A local JNI reference is a JVM-issued handle managed through a table/lifetime belonging to the current thread. Typically:

- Java object arguments passed into a native method are local references for that invocation.
- JNI APIs such as `FindClass`, `NewStringUTF`, `GetObjectClass`, and `GetObjectArrayElement` return new local references.
- When a native method **returns to Java**, the local references of that frame are automatically released.
- Within the same native method, `DeleteLocalRef` lets you clean up a reference early; `PushLocalFrame`/`PopLocalFrame` organize scopes when creating many references.
- When a **native-created thread** has attached and processes long-running work without the normal return-to-Java cycle of a regular native entrypoint, it must **actively clean up local references** (or use local frames), because they can otherwise persist until detach.

Distinguish between **the Java object** and **the JNI handle**. A Java object can be used concurrently by multiple Java threads according to the Java Memory Model, yet a local JNI reference representing that object is still only valid in the thread/frame that created the handle. A Java reference can be passed through standard Java synchronization mechanisms, whereas native code must create a JNI global reference if it needs to keep an object beyond the original thread/frame.

### `PushLocalFrame`/`PopLocalFrame` for a worker running a loop

```c
// Illustrative snippet inside an ALREADY-ATTACHED native thread.
// env and inputArray are valid on the current thread.
for (jsize i = 0; i < count; ++i) {
    if ((*env)->PushLocalFrame(env, 16) != JNI_OK) {
        // Usually an OutOfMemoryError is pending: stop and handle the error.
        break;
    }

    jobject element = (*env)->GetObjectArrayElement(env, inputArray, i);
    if ((*env)->ExceptionCheck(env)) {
        (*env)->PopLocalFrame(env, NULL);
        break;
    }

    // Process element using this thread's env.
    // DO NOT send element (local) to another thread.

    (*env)->PopLocalFrame(env, NULL);
    // Local references created inside the frame have just been cleaned up.
}
```

This snippet is not a standalone C file; it assumes `count`/`inputArray` already exist and all JNI usage happens on the current thread. `PopLocalFrame(env, NULL)` destroys local refs inside the frame. If a local reference needs to survive `PopLocalFrame` **on the same thread**, it can be returned via the `result` parameter of `PopLocalFrame`; that mechanism does **not** turn the reference into a cross-thread global reference.

Do not use `DeleteLocalRef` on a global ref or `DeleteGlobalRef` on a local ref. Keep the New/Delete pairs matched within each ownership path.

## 7. Global ownership and safety in asynchronous processing

The example in section 5 waits for the worker with `pthread_join`, so the time to delete the global ref is clear. In event-loop systems, native thread pools, or asynchronous SDK callbacks, you usually have to manage three independent lifetimes:

1. **Object JNI lifetime:** create `NewGlobalRef` when the queue accepts a task, transfer ownership to the task, and call `DeleteGlobalRef` when the task completes or is safely cancelled.
2. **Native task lifetime:** the C/C++ memory holding the task, buffers, and callback handles must stay alive until **no native worker is still using it**; only `free` after a synchronization point.
3. **Thread attachment lifetime:** each native worker attaches once when it first needs JNI; uses its own env; detaches when the thread stops and no Java frames remain.

Architecture example:

```text
Java caller
  -> JNI submit(envCaller, objLocal)
       -> NewGlobalRef(envCaller, objLocal) = objGlobal
       -> queue.push(Task{JavaVM*, objGlobal, ...})
       -> return to Java
                         |
                         v
                 Native worker thread
                    GetEnv/AttachCurrentThread -> envWorker
                    use objGlobal with envWorker
                    process result / callback
                    DeleteGlobalRef(envWorker, objGlobal) when task completes
                    DetachCurrentThread when worker exits
```

If the caller cancels the task while the worker is processing it, **do not delete the global ref before the worker stops accessing it**. Use appropriate mutexes/condition variables/atomics/reference counting in the native layer, along with an idempotent cancellation contract and shutdown cleanup. `NewGlobalRef` only keeps the object alive; it does **not** allocate a lock and does not prevent concurrent mutation. In C/C++, never read/write task fields from multiple threads without synchronization.

### Weak global reference

Weak global references are suitable for caches that do not need to force an object to stay alive, but GC can collect the object at any time. Checking and then directly using a weak ref can race with GC. On an attached worker, call:

```c
// Illustrative snippet; weakRef is a managed weak global reference.
jobject strongLocal = (*env)->NewLocalRef(env, weakRef);
if (strongLocal != NULL) {
    // Object is alive and strongly held within this local ref's scope.
    // Use strongLocal on THIS current thread.
    (*env)->DeleteLocalRef(env, strongLocal);
} else {
    // The object may have been collected by GC (or ref creation failed).
    // Check pending exceptions when needed to distinguish errors.
}
```

If a worker needs to hold the object across multiple threads, create a strong **global** ref from a still-live weak ref, following `NewGlobalRef` ownership rules. Do not cache the result of `IsSameObject(weakRef, NULL)` and use the weak reference afterward: the state may change between the check and the use.

## 8. Subtle bugs beyond JNI handles

### 8.1. A global ref does not make a mutable Java object thread-safe

Suppose native workers hold global refs to the same `ArrayList` and call `add` concurrently. Even though the ref is valid on every thread, `ArrayList` does not protect itself against concurrent mutation. The application still needs synchronization per the Java contract, or to choose an appropriate concurrent/immutable collection. Visibility/happens-before must also be considered if native code writes memory shared with Java.

**Right mental model:** A global reference solves **GC reachability and valid referencing**; locks solve **data-access synchronization**. These are two independent responsibilities.

### 8.2. Class loader when a native thread attaches itself

`FindClass` inside a native method can use the class loader associated with the class declaring the native method. However, a self-attaching native thread **has no Java caller** from which to infer a loader in the usual way; by default, the context class loader of an attached native thread is **the bootstrap loader**. Therefore `FindClass(envWorker, "com/example/Plugin")` can fail even when the plugin class exists under a custom class loader.

The safe way when you need to call an application class: obtain the `jclass` on a Java caller that has the right loader, **create a global ref** for it, hand it to the worker, and have the worker call `GetMethodID` on the global class reference. Or pass a class loader/entrypoint with a clearly managed lifecycle. Never share a local `jclass` obtained from `FindClass` on the caller directly.

### 8.3. A cached `jmethodID` is not a global reference

`jmethodID`/`jfieldID` are opaque IDs, not `jobject`, and you do not use `NewGlobalRef` on IDs. They can be cached while the class remains loaded, but you must understand class loader lifecycles: unloading/reloading can invalidate old IDs. If caching a class alongside its method IDs, the class reference needs to be global/weak global as appropriate and cleaned up properly.

### 8.4. Exceptions are per-thread state

If a worker calls a Java method that leaves an exception pending, that exception does not automatically "jump" to the caller Java thread waiting in `pthread_join`. The worker must handle/translate it or transfer the `Throwable` via a **global reference** per contract, then delete it. Do not pass a local `jthrowable` directly to another thread. Do not leave an exception pending and call a series of JNI functions that are disallowed in that state.

### 8.5. Daemon attachment and JVM shutdown

A native worker attached via `AttachCurrentThread` is **non-daemon** by API; if not detached, it can prevent the JVM from shutting down. `AttachCurrentThreadAsDaemon` does not keep the JVM alive like a non-daemon thread, but daemon does not mean resources are automatically cleaned up: when the JVM terminates, native work may be interrupted. You must design graceful shutdown, stop queues, join workers, and release globals before exiting if integrity is required.

### 8.6. JNI on Java virtual threads

In JDKs with virtual threads, JNI calls and the use of native thread-affine state require even closer attention to scheduler context and lifecycle. Do not cache `JNIEnv*` based on thread name, task name, or Java logical thread ID. The correct approach remains using **the env provided at the JNI entrypoint** or obtaining an env after attachment on the native thread calling JNI, along with reference ownership rules. When long-lived interaction with native callbacks is needed, consider platform threads and check the JDK guidance for the target version.

## 9. Checklist before running a native worker

| Question to answer | If not met |
|---|---|
| Does the worker obtain `JNIEnv*` **on its own thread**? | Do not call JNI; attach/getEnv on the right thread |
| Did you accidentally store the caller's `JNIEnv*` in a static/queue? | Remove it; only keep `JavaVM*` |
| Are objects passed outside the native frame via a **strong global ref**? | Call `NewGlobalRef` before queuing/starting the worker |
| Is there a single owner responsible for calling `DeleteGlobalRef`? | Design ownership to avoid double delete/leaks |
| Does the global ref stay alive for the **entire** time the worker uses it? | Add synchronization/finish acknowledgement |
| Has the worker attached and will it detach at the right time? | Need lifecycle management and cleanup on every branch |
| Does the worker create many local refs in a loop? | Use `DeleteLocalRef` or a local frame to avoid accumulation |
| Is mutable data protected by appropriate synchronization? | A global ref does not solve data races |
| Does the worker call back into application classes via the right class loader? | Pass a global `jclass`/loader from the Java caller |
| Are pending exceptions and JNI error codes handled? | Avoid using invalid results or hanging/failing silently |
| Do multiple callers share a task buffer/error variable? | Give each request its own state or lock shared state |
| Is JNI native access granted per JDK/version? | Use the exact access configuration and test on the target JVM |

When debugging, running with `-Xcheck:jni` can catch some JNI usage errors, such as invalid reference/thread usage. It cannot prove full C/C++ memory safety or replace race detectors/AddressSanitizer/ThreadSanitizer for the native side. Start with an example that has clear results and cleanup before moving to an asynchronous thread pool.

## 10. Common mistakes and consequences

| Mistake | Possible consequence | How to fix |
|---|---|---|
| Using `JNIEnv*` from thread A on thread B | Crash, JNI error, or undefined behavior | `GetEnv`/`AttachCurrentThread` on B |
| Saving a local `jobject` after the JNI function returns | Expired handle, crash, or garbage data | `NewGlobalRef` before the caller frame ends |
| Using a local `jclass` from the caller in a pthread | Thread-local reference violation | Create a global class ref or perform a valid lookup on B |
| Deleting a global ref immediately after enqueueing | Worker may access an already-deleted ref | Transfer ownership to the task; delete safely after completion/cancel |
| Failing to call `DeleteGlobalRef` | Keeps object alive, native/JVM memory leak | Clean up globals on completion and shutdown |
| Forgetting `DetachCurrentThread` in a native worker | Thread resources not cleaned up, JVM may struggle to shut down | Detach native-created threads after finishing |
| Detaching a Java thread inside a native callback | Invalid while Java frames remain on the stack | The JVM manages attachment for Java-created threads |
| Native-created thread accumulating local refs for a long time | Local reference table grows, runs out of resources | `DeleteLocalRef` / `PushLocalFrame` |
| Using a global ref to share a mutable `HashMap` without locking | Data race or corrupted state | Apply Java/thread synchronization |
| `FindClass` on an attached worker cannot find an app class | Different class loader context | Pass a global `jclass`/class loader from the caller |
| Callback throws a Java exception but caller is unaware | Error state is ignored | Handle on worker; transfer `Throwable` via global ref when needed |
| Calling `pthread_join` while holding a lock the worker needs | Deadlock | Design lock, callback, join, and timeout ordering |

## 11. Self-check exercises

**Exercise 1 — spotting the violation.** A JNI method receives `jstring name` and stores `name` in a global C variable; another `pthread` attaches and calls `GetStringLength(envWorker, savedName)`. Is this safe?

**Answer:** **No.** Even though the worker has a thread-appropriate env, `savedName` is the caller's local reference. You must create `NewGlobalRef(envCaller, name)` before leaving the caller frame/handing off work; delete the global ref after the worker finishes using it.

**Exercise 2 — fixing how env is obtained.** A worker created with `pthread_create` holds `JNIEnv* envCaller` from an earlier native callback. It calls `CallVoidMethod(envCaller, ...)`. How do you fix this?

**Answer:** Keep `JavaVM*`, on the worker use `GetEnv` and `AttachCurrentThread` if not yet attached to obtain `envWorker`; only call JNI through `envWorker`. Detach before the worker exits if the worker attached itself.

**Exercise 3 — global ref and synchronization.** Two workers both hold valid strong global refs to the same mutable `ArrayList`; both call `add` concurrently. Does a valid reference guarantee data correctness?

**Answer:** **No.** Appropriate synchronization or a concurrent structure is required. A JNI global ref manages reachability, not consistency of object state.

**Exercise 4 — lifecycle.** The worker finishes, and the caller has successfully called `pthread_join`. Can the caller call `DeleteGlobalRef` and then return from the native method?

**Answer:** **Yes**, provided no other worker/task holds permission to use that global ref and no asynchronous callback is still running. Joining establishes a synchronization point proving this worker has stopped.

**Exercise 5 — class loader.** An attached pthread cannot find `com/example/MyPlugin` with `FindClass`, even though the class is on the application classpath and loaded via a custom loader. What possibility should you check?

**Answer:** The worker lacks the expected Java caller/class loader context; an attached thread's default context loader may be the bootstrap loader. Pass a valid global `jclass` or class loader from the Java caller, managing its lifetime properly.

**Exercise 6 — local reference management.** A worker attaches once, runs 1 million iterations, and calls `NewStringUTF` on every iteration without deleting the local reference. Is detaching when the thread exits good enough?

**Answer:** **No.** During the loop, local refs accumulate and can exhaust resources before detaching. Use `DeleteLocalRef` each iteration or `PushLocalFrame`/`PopLocalFrame`.

## 12. Takeaways and official references

Three principles to memorize:

1. **`JNIEnv*` is per-thread:** each thread calling JNI needs its own environment obtained on that thread; never pass a `JNIEnv*` pointer to another thread.
2. **Local references are per-thread/frame:** never pass a local `jobject`/`jclass` to another thread or keep it after the frame ends; use a **global ref** for handing off work, with well-defined ownership and cleanup.
3. **`JavaVM*` + attach/detach:** is the valid path for a native thread to interact with the JVM. Even with a valid global ref, you must still ensure object thread safety and native data synchronization.

**Official references:**

- [Oracle JNI Specification — Design Overview: JNI Interface Pointers, Local and Global References](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/design.html)
- [Oracle JNI Specification — The Invocation API: AttachCurrentThread, GetEnv, DetachCurrentThread](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/invocation.html)
- [Oracle JNI Specification — JNI Functions: NewGlobalRef, DeleteGlobalRef, NewLocalRef, DeleteLocalRef, PushLocalFrame](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html)
- [Android NDK — JNI Tips: Threads and managing local references when a native thread attaches](https://developer.android.com/ndk/guides/jni-tips)
- [Java Language Specification — Threads and Locks / Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html)
- [JEP 472 — Prepare to Restrict the Use of JNI (JDK 24)](https://openjdk.org/jeps/472)
