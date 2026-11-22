# Creating, Retaining, and Deleting Global References in JNI with `NewGlobalRef`, `DeleteGlobalRef`

## 1. References and GC: Why Are Global References Needed?

When C/C++ code communicates with the JVM through the Java Native Interface (JNI), a Java object-type parameter is passed as a `jobject` (or `jstring`, `jclass`, `jarray`, etc.). These values are **JNI references** managed by the JVM, not direct C pointers pointing to fixed locations on the Java heap. The Garbage Collector (GC) may move objects; native code still uses a valid JNI handle so the JVM can locate the object.

A classic scenario: Java registers a listener with a C library; C must retain the listener to invoke the callback **in subsequent native calls**, after the registration function has finished. The `jobject` parameter received in the registration function is normally a **local reference**: only valid within the native frame and the thread that created it. If C assigns that reference directly to a global variable, after the frame ends it is no longer guaranteed to be valid.

The JNI solution consists of two operations:

- **`NewGlobalRef(env, obj)`** creates a new **strong global reference**. This handle remains valid across native calls until it is deleted; a strong reference keeps the object reachable, preventing the GC from collecting it just because Java no longer has a variable pointing to it.
- **`DeleteGlobalRef(env, globalRef)`** deletes a global reference owned by native code. It releases the JVM's reference resource and removes one path keeping the object reachable. The object is **not automatically deleted immediately**; the GC can only collect it when no other strong references remain.

Lifecycle model:

```text
Java calls register(listener)
       │ listener is a local ref, valid within the native frame
       ▼
C: NewGlobalRef(env, listener)  ──► g_listener (global ref)
       │
Java register() returns; local ref exits frame
       │
       ▼
C: keeps g_listener across native calls; GC still sees a strong root
       │
Java calls emit() ──► C: CallVoidMethod(env, g_listener, ...)
       │
Java calls unregister()
       ▼
C: DeleteGlobalRef(env, g_listener); g_listener = NULL
       │
GC can collect the Java listener when no other roots remain
```

Key point: creating a global reference **does not copy the Java object**, does not pin the heap address, and does not automatically synchronize the object's contents. It provides **lifetime rules for the reference** when crossing the Java ↔ native boundary.

## 2. How Do Local, Strong Global, and Weak Global References Differ?

| Characteristic | Local reference | Strong global reference | Weak global reference |
| --- | --- | --- | --- |
| Typically obtained/created from | Native parameters, `GetObjectClass`, `NewLocalRef` | `NewGlobalRef` | `NewWeakGlobalRef` |
| Scope | Native frame and **current thread** | Across multiple JNI calls; accessible from any native thread attached to the JVM validly | Across multiple JNI calls, but the target object may be collected by the GC |
| Keeps the object from being GC-collected? | Yes, while the local ref is valid | **Yes**, until deleted or JVM shutdown | **No** |
| Release | `DeleteLocalRef` or JNI frame ends | **`DeleteGlobalRef`** | `DeleteWeakGlobalRef` |
| Main risk | Saving across frames / passing to another thread | Leak if not deleted; race on deletion | Target object disappears between check and use |

**Incorrect** example:

```c
static jobject g_listener = NULL;

// Wrong: only copies the local handle value, does not create a global JNI root.
g_listener = listener;
```

This is an illustration of an error, not a complete program. After the native method returns, `listener` may become invalid; C still storing the bit-pattern of the handle does not grant permission to continue using it.

Correct approach in principle:

```c
jobject saved = (*env)->NewGlobalRef(env, listener);
if (saved == NULL) {
    // Check null input / out of memory / exception according to contract.
    return;
}
// Store saved in native state with a defined owner,
// then delete it with DeleteGlobalRef when the subscription ends.
```

Creating a new reference is different from assigning a handle; the JVM records a strong root. The source reference `listener` remains a local reference and will be cleaned up according to its own lifecycle.

## 3. API Contract of `NewGlobalRef` and `DeleteGlobalRef`

### 3.1. `NewGlobalRef`

C declaration in JNI:

```c
jobject NewGlobalRef(JNIEnv *env, jobject obj);
```

Call syntax:

```c
jobject global = (*env)->NewGlobalRef(env, obj);
```

- `env` must be a valid `JNIEnv *` **of the current calling thread**.
- `obj` is normally a valid JNI local/global reference; `NULL` is also accepted. If `obj == NULL`, the result is `NULL`.
- The function returns **a new global reference** to **the same Java object**. The source is not deleted or modified.
- The function may return `NULL` if out of memory; if the source is a weak global reference that has already been collected, it also cannot be promoted to a strong ref. **Do not assume every `NULL` return necessarily has a pending Java exception.**
- Multiple global references can be created to the same object; they are **independent reference ownerships** that need to be cleaned up separately.

When `NewGlobalRef` on a confirmed non-null source returns `NULL`, code should preserve the old reference (if replacing a listener), check `ExceptionCheck`, handle the resource exhaustion according to application policy, and not continue using the failed handle.

### 3.2. `DeleteGlobalRef`

Declaration:

```c
void DeleteGlobalRef(JNIEnv *env, jobject globalRef);
```

Typical usage:

```c
if (global != NULL) {
    (*env)->DeleteGlobalRef(env, global);
    global = NULL;
}
```

`DeleteGlobalRef(env, NULL)` is allowed and does nothing. However, deleting **the same non-null handle twice** is wrong: after the first deletion, the old value is no longer valid. When code holds multiple copies of a handle, they must be prevented from being used before or concurrently with deletion.

**Do not confuse deleting a reference with deleting a Java object.** If Java still holds the listener through a field, collection, thread, or another global ref, it remains reachable after C deletes a global reference. The GC also does not promise when an object that has just become unreachable will be collected.

### 3.3. Do Not Use the Wrong Reference Type

| Value | Correct deletion function |
| --- | --- |
| Local `jobject` | `DeleteLocalRef` (or JNI frame cleans up automatically) |
| Strong global `jobject` created by `NewGlobalRef` | `DeleteGlobalRef` |
| Weak global `jweak` created by `NewWeakGlobalRef` | `DeleteWeakGlobalRef` |

`jmethodID` and `jfieldID` are not `jobject`; **do not** pass them to reference deletion functions. `GetObjectRefType(env, ref)` can help distinguish the reference type **while the ref is still valid**, but must not be used on a deleted handle to "check whether it is still alive".

## 4. Complete Java 17+ Example: Registering a Listener, Calling Back Multiple Times, Then Unregistering

The example uses **Java 17+ and GCC on Linux**, including Java source, C source, and build/run commands. It intentionally calls JNI **sequentially from a single Java thread** with no concurrent callbacks. Multithreaded behavior is explained separately in Section 7.

### 4.1. Directory Structure

```text
jni-global-reference/
├── src/
│   └── demo/
│       └── jni/
│           └── GlobalReferenceDemo.java
├── native/
│   └── globalrefdemo.c
└── build/                       # Generated automatically during compilation
```

### 4.2. Java Source: `src/demo/jni/GlobalReferenceDemo.java`

```java
package demo.jni;

public final class GlobalReferenceDemo {
    static {
        System.loadLibrary("globalrefdemo");
    }

    public static final class Receiver {
        public void onEvent(int value) {
            System.out.println("Received: " + value);
        }
    }

    // Native retains a strong global reference to Receiver.
    private static native void registerReceiver(Receiver receiver);

    // Native calls back onEvent(int) on the registered Receiver.
    private static native void emit(int value);

    // Native deletes the global reference when no longer in use.
    private static native void unregisterReceiver();

    public static void main(String[] args) {
        // Do not hold Receiver in a Java field.
        registerReceiver(new Receiver());

        try {
            emit(5);
            emit(8);
        } finally {
            // Execute even if the callback throws a Java exception.
            unregisterReceiver();
        }

        System.out.println("Unregistered");
    }
}
```

The two `emit` calls are invoked **after `registerReceiver` returns**. Not keeping an extra reference in Java is a way to make JNI's responsibility clear; it does not use `System.gc()` and does not rely on GC definitely running to prove the example works.

### 4.3. Generating the JNI Header with `javac -h`

Change to the `jni-global-reference` directory:

```bash
mkdir -p build/classes build/headers build/lib

javac -encoding UTF-8 \
  -h build/headers \
  -d build/classes \
  src/demo/jni/GlobalReferenceDemo.java
```

The JDK creates `build/classes/demo/jni/GlobalReferenceDemo.class` along with the header `build/headers/demo_jni_GlobalReferenceDemo.h`. Because the three native methods are `static`, the main prototypes in the header are equivalent to:

```c
JNIEXPORT void JNICALL Java_demo_jni_GlobalReferenceDemo_registerReceiver
  (JNIEnv *, jclass, jobject);
JNIEXPORT void JNICALL Java_demo_jni_GlobalReferenceDemo_emit
  (JNIEnv *, jclass, jint);
JNIEXPORT void JNICALL Java_demo_jni_GlobalReferenceDemo_unregisterReceiver
  (JNIEnv *, jclass);
```

This is an **excerpt for explanation**, not a replacement for the complete header with include guards and compiler-generated macros.

### 4.4. C Source: `native/globalrefdemo.c`

```c
#include <jni.h>
#include "demo_jni_GlobalReferenceDemo.h"

// Only accessed sequentially, not used concurrently across threads.
static jobject g_receiver = NULL;    // Strong global reference.
static jmethodID g_onEvent = NULL;   // Method ID, not a JNI reference.

static void throw_java(JNIEnv *env, const char *className,
                       const char *message) {
    jclass exceptionClass = (*env)->FindClass(env, className);
    if (exceptionClass == NULL) {
        return; // Preserve the exception if FindClass fails.
    }
    (*env)->ThrowNew(env, exceptionClass, message);
    (*env)->DeleteLocalRef(env, exceptionClass);
}

JNIEXPORT void JNICALL
Java_demo_jni_GlobalReferenceDemo_registerReceiver(
        JNIEnv *env, jclass owner, jobject receiver) {
    (void)owner; // For static native, the second parameter is jclass.

    if (receiver == NULL) {
        throw_java(env, "java/lang/IllegalArgumentException",
                   "receiver must not be null");
        return;
    }

    jclass receiverClass = (*env)->GetObjectClass(env, receiver);
    if (receiverClass == NULL) {
        return;
    }

    jmethodID callback = (*env)->GetMethodID(
            env, receiverClass, "onEvent", "(I)V");
    (*env)->DeleteLocalRef(env, receiverClass);
    if (callback == NULL) {
        return; // A NoSuchMethodError may be pending.
    }

    // receiver is a local ref. Create a global ref while it is still valid.
    jobject newRef = (*env)->NewGlobalRef(env, receiver);
    if (newRef == NULL) {
        // JNI may return NULL without setting an exception.
        if (!(*env)->ExceptionCheck(env)) {
            throw_java(env, "java/lang/OutOfMemoryError",
                       "NewGlobalRef failed");
        }
        return;
    }

    // Only delete the old registration AFTER successfully creating newRef.
    // The demo does not allow concurrent register/emit/unregister.
    if (g_receiver != NULL) {
        (*env)->DeleteGlobalRef(env, g_receiver);
    }
    g_receiver = newRef;
    g_onEvent = callback;
}

JNIEXPORT void JNICALL
Java_demo_jni_GlobalReferenceDemo_emit(
        JNIEnv *env, jclass owner, jint value) {
    (void)owner;

    if (g_receiver == NULL) {
        throw_java(env, "java/lang/IllegalStateException",
                   "No receiver registered");
        return;
    }

    // The global ref is still alive even though registerReceiver has returned.
    (*env)->CallVoidMethod(env, g_receiver, g_onEvent, value);

    // If onEvent throws a Java exception, the native method returns
    // with the pending exception for the JVM to pass to the Java caller.
}

JNIEXPORT void JNICALL
Java_demo_jni_GlobalReferenceDemo_unregisterReceiver(
        JNIEnv *env, jclass owner) {
    (void)owner;

    if (g_receiver != NULL) {
        (*env)->DeleteGlobalRef(env, g_receiver);
        g_receiver = NULL; // Do not reuse the deleted handle.
    }
    g_onEvent = NULL;
}
```

Step-by-step walkthrough:

1. `registerReceiver` receives `receiver` as a local reference. It retrieves the `jmethodID` for the instance method `onEvent(int)` via the descriptor `"(I)V"`.
2. `NewGlobalRef` creates an **independent global reference**, returning `newRef`. Only when creation succeeds does it replace the old global reference. If creation fails, the old registration remains intact and Java receives an error according to the example's policy.
3. `g_receiver` is stored in a `static` C variable across multiple native calls. In `emit`, `CallVoidMethod` uses this reference to call Java's `Receiver.onEvent`.
4. `unregisterReceiver` deletes the global reference once the listener is no longer needed, setting `g_receiver` and its accompanying ID to `NULL`. The function can be called again without deleting an already destroyed handle.
5. `try/finally` on the Java side ensures cleanup when the callback fails. `DeleteGlobalRef` does not replace closing the listener's sockets/files if the listener owns those additional resources.

### 4.5. Compiling the Library and Running

Install a JDK (with `jni.h`) and GCC; configure `JAVA_HOME` to the corresponding **JDK**. After the `javac -h` step, run on Linux:

```bash
gcc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/headers \
  -o build/lib/libglobalrefdemo.so \
  native/globalrefdemo.c

java -Xcheck:jni \
  -Djava.library.path=build/lib \
  -cp build/classes \
  demo.jni.GlobalReferenceDemo
```

`-Ibuild/headers` allows C to include the header `demo_jni_GlobalReferenceDemo.h`, and `-Djava.library.path=build/lib` helps the JVM load `libglobalrefdemo.so` corresponding to the logical name `globalrefdemo`.

**Expected stdout:**

```text
Received: 5
Received: 8
Unregistered
```

The callback works across two separate JNI calls. This shows that the reference is stored and used properly in the example, **not that a GC cycle has occurred**. Do not use GC counts or memory addresses as correctness criteria for the exercise.

On **macOS**, use the include path `$JAVA_HOME/include/darwin` and build `libglobalrefdemo.dylib` with an appropriate compiler; on **Windows**, use the include path `%JAVA_HOME%\include\win32` with a compatible compiler to build `globalrefdemo.dll`. Ensure the library architecture matches the JVM architecture.

## 5. Understanding GC and Keeping Objects Alive Properly

A strong global reference is an **effective GC root** for the object it references. If a listener also has paths to other objects, the entire object graph reachable through the listener may be kept alive longer than intended:

```text
C global reference
    └──► Java listener
             ├──► cache
             ├──► UI view / component
             ├──► executor
             └──► related class loader
```

If a native library repeatedly registers listeners but forgets `DeleteGlobalRef`, the application may have a **JNI global reference leak**: Java no longer uses the listeners, but they remain reachable from the native registry. In plugin/hot-reload systems, object/class references held for too long can also prevent the class loader from being reclaimed.

Conversely, calling `DeleteGlobalRef` **does not force the GC to run**. If Java still has another strong reference (for example, a static field or a local reference on the stack), the object remains alive. Even when no roots remain, the GC decides when to collect; do not use `System.gc()` as deterministic proof.

A `jclass` is a JNI reference to a class object; if C wants to cache a class across multiple native calls, it must convert the local `jclass` returned by `FindClass`/`GetObjectClass` into a valid global reference and delete it at the proper lifecycle point. Method/field IDs such as `jmethodID` and `jfieldID` **do not keep the class loaded by themselves**. If the class is unloaded, the IDs are no longer guaranteed to be valid.

## 6. Ownership Mistakes to Avoid

### 6.1. If You Create Two Global Refs, Delete Both

```c
jobject first  = (*env)->NewGlobalRef(env, obj);
jobject second = (*env)->NewGlobalRef(env, obj);

// Each successfully created ref needs its own DeleteGlobalRef.
if (first != NULL)  (*env)->DeleteGlobalRef(env, first);
if (second != NULL) (*env)->DeleteGlobalRef(env, second);
```

Two handles pointing to the same Java object are still **two global references that require separate cleanup**. Deleting `first` does not release `second`. Do not rely on comparing `first == second` to merge ownership; JNI references are opaque handles. If you need to compare Java object identity, use `IsSameObject(env, first, second)` on **still-valid references**.

### 6.2. Do Not Reuse After Deletion

Wrong:

```c
(*env)->DeleteGlobalRef(env, g_receiver);
// Wrong: this is an already-destroyed handle.
(*env)->CallVoidMethod(env, g_receiver, g_onEvent, (jint)42);
```

A simple safeguard is to set `g_receiver = NULL` immediately upon deletion and guard against any subsequent calls. In multithreaded programs, simply setting `NULL` is not enough: another thread may have already copied the old handle, so synchronization is needed around both usage rights and the deletion operation.

### 6.3. Do Not Confuse Releasing a Reference with Freeing Native Memory

If the library also `malloc`s a C buffer or holds a native file descriptor, these resources must be freed with their own respective APIs (for example, `free`/`close` per contract), not `DeleteGlobalRef`. Similarly, do not expect JNI to automatically call `AutoCloseable.close()` on the Java object when deleting a global reference.

### 6.4. Do Not Keep `JNIEnv *` Across Threads

A global reference can be used across multiple native calls, including from a native thread properly attached to the JVM. However, `JNIEnv *` is a **per-thread interface**: do not copy `JNIEnv *` from thread A and use it on thread B. A thread created by C itself needs `GetEnv`/`AttachCurrentThread` to obtain its own `JNIEnv *` and `DetachCurrentThread` when a self-attached thread finishes its work.

## 7. Multithreading: Preventing Races Between Callbacks and `DeleteGlobalRef`

The example in Section 4 is **not thread-safe**: C uses the `static g_receiver` variable without a mutex. If thread A is executing `emit` while thread B calls `unregisterReceiver`, B may delete the global reference before A uses it, causing a **use-after-delete**. A long-lived global reference **does not mean registry access across threads is safe**.

A better strategy for multithreaded systems is:

1. Protect the registry (the global ref and method ID of the same listener) with a lock/mutex.
2. When preparing a callback, hold the lock and create a **local snapshot** using `NewLocalRef(env, g_receiver)` on the thread preparing the callback; at the same time, retrieve the corresponding ID. If the snapshot fails, handle the unregistered/out-of-resources case explicitly.
3. **Release the lock before calling into Java** to avoid deadlocks and reentrancy issues. The local snapshot keeps the object reachable throughout the callback, even if another thread has already removed the global reference.
4. Use `CallVoidMethod` with the snapshot, then `DeleteLocalRef` on the same thread. Callback exceptions must be handled or propagated back to the Java caller according to the contract.
5. When unregistering, hold the same lock to update the registry and delete the global reference. Define the contract: whether an already-started callback is allowed to finish, or whether unregister must wait for all callbacks to complete before returning.

Sketch in **pseudocode, not a standalone C program** (lock functions and error handling must be implemented):

```c
lock(registry_mutex);
jobject local = (*env)->NewLocalRef(env, g_receiver);
jmethodID id = g_onEvent;
unlock(registry_mutex);

if (local == NULL) {
    handle_missing_listener_or_allocation_error();
    return;
}

(*env)->CallVoidMethod(env, local, id, value);
(*env)->DeleteLocalRef(env, local);
```

All registration, unregistration, and callback invocation operations must follow **the same locking discipline**. If unregister uses a mutex while the callback skips it, the race still exists. Also, do not pass `local` to another thread: local references are only valid on the thread that created them.

When C creates its own native worker thread to dispatch callbacks, it must attach the worker to the JVM first to get a valid `JNIEnv *`, and then take the snapshot on that thread. For a self-attached C thread, local references should be deleted when no longer needed because they may persist until detach, unlike short-lived native frames called from Java.

## 8. When to Use a Weak Global Reference?

`NewGlobalRef` is appropriate when native code **must own** the listener: once registration succeeds, callbacks are still allowed to occur until unregistration. But if you only want a **cache that does not keep objects alive**, a strong global reference may retain the heap for too long. You can consider `NewWeakGlobalRef` and delete it with `DeleteWeakGlobalRef`.

A weak global reference **does not prevent the GC from collecting** the target object. Therefore, you should not do:

```c
// Unsafe: the object may be GC'd after the check.
if (!(*env)->IsSameObject(env, weak, NULL)) {
    // ... use weak in a later step without holding a strong reference ...
}
```

To use it safely, create a **strong local reference** with `NewLocalRef(env, weak)`, check for `NULL`, use the valid local reference in the operation, and then `DeleteLocalRef` when finished. If it returns `NULL`, the object may have already been collected or an allocation error occurred; do not proceed to invoke methods on `NULL`.

That solves the goal of **not keeping a cache alive indefinitely**. It does not replace the responsibility of cleaning up a strong global reference with `DeleteGlobalRef` for a registration with true ownership.

## 9. Diagnosing Leaks and Reference Errors

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Listener/Activity/class loader is not collected by GC | Native still holds a strong global reference | Audit register/unregister and global roots; call `DeleteGlobalRef` at the right lifecycle point |
| Crash after native method returns | Storing a local `jobject` in a static variable | Create `NewGlobalRef` before the native frame ends |
| Crash after unregister | Callback uses a deleted handle | Stop dispatching, synchronize unregister, use a local snapshot when multithreaded |
| Listener remains alive after `DeleteGlobalRef` | Another Java/GC root still holds the object | Inspect retained references; do not assume immediate GC |
| `NewGlobalRef` returns `NULL` | `null` input, out of memory, weak ref lost its target | Check input/exception; avoid overwriting valid state |
| JNI reports wrong reference usage | Calling `DeleteLocalRef` instead of `DeleteGlobalRef` or using an ID as a ref | Clearly distinguish local/global/weak refs and member IDs |
| Native worker thread fails JNI calls | Using another thread's `JNIEnv *`, not attached yet | Obtain the current thread's `JNIEnv *` via `GetEnv`/`AttachCurrentThread` |
| Heap grows after many register/unregister cycles | Each `NewGlobalRef` lacks a matching `DeleteGlobalRef` | Count still-owned handles and test teardown cycles |
| Callback method not found | Wrong name/descriptor or class loader | Verify `GetMethodID`, `"(I)V"`, and the actual class |

When testing, you can run the JVM with `-Xcheck:jni` as in the example. It helps detect some JNI errors but **does not replace** checking for races, native memory leaks, and retained objects. Use heap/GC root tools to determine whether an object is still kept alive by a JNI global reference; also pay attention to references residing in class loaders of plugin systems.

In applications with multiple listeners, design a separate **native subscription handle** for each registration and an idempotent `close/unregister` API, avoiding a single static variable if multiple concurrent subscriptions are needed. `try/finally` or `AutoCloseable` in Java helps express teardown responsibility, but must match the ownership that C actually enforces.

## 10. Practical Checklist

Before putting JNI global references into long-lived code, self-check:

1. **Valid source:** the original `jobject` is still alive at the time `NewGlobalRef` is called.
2. **Failure handled:** if `NewGlobalRef` returns `NULL`, the program does not store/call as if it succeeded; does not lose the old registration when replacement fails.
3. **Clear owner:** who stores the handle, who is responsible for calling `DeleteGlobalRef`, under what circumstances, and how many times.
4. **Correct thread for callbacks:** each thread has a valid `JNIEnv *`; local references are not passed to another thread.
5. **Safe deletion:** prevent callbacks from using a deleted handle; synchronize the registry and the policy for in-flight callbacks.
6. **No leaks:** every successfully created global reference is deleted; do not keep listeners/class loaders longer than intended.
7. **No conflating concepts:** deleting a global reference does not mean the GC has run, nor does it mean the Java object is closed or C memory is freed.

## 11. Review Questions

1. Why might `static jobject saved = listener;` appear to work "fine" in a few test runs, yet be an incorrect JNI design if you want to use `saved` after the native method returns?
2. Does `NewGlobalRef` copy the Java object or create a new JNI handle pointing to the same object? How does this affect the GC?
3. If two global references are created to the same Java listener and only one is deleted, is the listener guaranteed to be eligible for GC collection? Explain.
4. After calling `DeleteGlobalRef`, what definitely happens to the reference, and what is **not guaranteed** to happen to the Java object?
5. In the Java/C example, why can `emit(8)` still call Java's `onEvent` even though `registerReceiver` has finished? When does C delete the reference?
6. If thread B unregisters at the exact moment thread A calls `emit`, why is simply setting `g_receiver = NULL` not enough? Describe the safe mutex and `NewLocalRef` workflow.
7. In what situations should a weak global reference be used instead of a strong global reference? Why must a weak ref be promoted to a local ref before use?
8. What must a native thread created by C do with `JavaVM` and `JNIEnv` to invoke a Java callback through a global reference?
9. A native plugin holds a global `jclass` after a Java module has been logically unloaded. Why might the class loader still be kept reachable, and where does cleanup need to happen?

**Key takeaway:** `NewGlobalRef` creates a **strong JNI reference that persists across multiple native calls**; `DeleteGlobalRef` ends **that reference ownership**. You must properly pair create/delete, manage GC reachability, control races during callbacks, and use `JNIEnv` on the right thread.

### Official Documentation

- [JNI Specification JDK 21 — Design Overview: Global and Local References](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html).
- [JNI Specification JDK 21 — JNI Functions: NewGlobalRef, DeleteGlobalRef, NewLocalRef, Weak Global References](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html).
- [JNI Specification JDK 21 — Invocation API: AttachCurrentThread / DetachCurrentThread](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/invocation.html).
