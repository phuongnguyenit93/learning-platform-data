# Designing Reference Ownership to Avoid Leaks or Use of Expired References

## 1. Goal and Context: Java References Crossing the Native Boundary

When Java calls C/C++ code via **JNI (Java Native Interface)**, a `jobject` is not simply a memory address that can be stored forever. It is a **JVM-managed reference**, with rules regarding scope, thread, expiration time, and impact on the garbage collector (GC). An object may still be alive in Java, while the **JNI local reference pointing to it has already expired**. Conversely, a JNI strong global reference can unintentionally keep an object alive and cause a leak even though the Java application thinks it has dropped all references.

This lesson focuses on designing proper ownership: **who creates the reference, who is allowed to use it, for how long, who must delete it, and what happens during errors/concurrent cancellation**. After studying, you should be able to:

- Distinguish **local**, **strong global**, and **weak global** JNI references by lifetime, GC reachability, and cleanup operations.
- Validly convert a local reference to a global reference if native code needs to keep the object after the JNI method returns.
- Reclaim a global/weak global ref logically once; handle replacement, allocation failure, and multiple closes.
- Manage local refs in loops/callbacks/attached native threads and avoid using references past their lifetime.
- Define a clear owner for both native resources and Java objects; handle races when closing concurrently with callbacks/native access.
- Write and run a **Java 17+ + C11** example, observing verifiable behavior without relying on when GC runs.

**Scope:** object references in JNI and their relationship with GC. Addresses of native memory allocated with `malloc`/`free`, direct buffers, or FFM have **different deallocation rules**; do not mix the two types of ownership.

## 2. Separating Three Easily Confused Things: Object, Reference, and Native Allocation

~~~text
Java heap:
    Object O
       ^
       | (reference tracked by JVM)
       |
    Java local variable         JNI local ref         JNI strong global ref
    only exists in Java         in a JNI frame        in the JVM global table
                                                         |
Native heap:                                            | keeps O reachable
    malloc(...) ---> block N                             |
    free(N) frees N; does not delete JNI ref to O -------+
~~~

- **Java object O:** an object on the heap managed by the JVM. The GC decides when to reclaim it when it is no longer reachable according to GC rules; programmers must not assume a fixed physical address or reclamation time.
- **JNI reference handle:** a value of type `jobject` or derived types (`jclass`, `jstring`, `jobjectArray`, …) defined by JNI. Valid only according to the allocated **type and lifetime**. Do not turn a `jobject` into a long-lived native pointer by casting it to `void *` or `jlong`.
- **Native memory:** if C allocates a `malloc` block, C must have an appropriate deallocation convention. `DeleteGlobalRef` does not call `free` for the native block, and `free` does not delete the global reference. If a handle holds both resources, **two independent cleanups in a sensible order** are required.

A deleted reference **does not mean the object is immediately GC'd**: the object may still be reachable through other references. Conversely, an object still being reachable does not let you "resurrect" a local reference that has been deleted or whose JNI frame has ended. **The lifetime of the handle and the lifetime of the referent are two separate conditions.**

## 3. Reference Selection Table: Which Type Owns Which Lifetime?

| Type | How Obtained | Handle Valid Duration | Impact on GC | What Must Be Done |
|---|---|---|---|---|
| **Local** (`jobject`, `jstring`, …) | Native method parameters, most JNI object-returning APIs, `NewLocalRef` | Within the creating JNI local frame and thread; usually expires automatically when the native call returns | Keeps referent reachable while the local ref is valid | `DeleteLocalRef` early in loops; can use `PushLocalFrame`/`PopLocalFrame` |
| **Strong global** (`jobject`) | `NewGlobalRef(env, ref)` | Until `DeleteGlobalRef(env, ref)` | Is a strong JNI root, can keep referent alive longer than desired | Owner must call `DeleteGlobalRef` in cleanup |
| **Weak global** (`jweak`) | `NewWeakGlobalRef(env, ref)` | Handle exists until `DeleteWeakGlobalRef`, but referent may be GC'd before then | Does not keep referent alive | Proactively delete weak handle; **promote** with `NewLocalRef` before accessing |

A `jobject obj` parameter passed by the JVM into a native method is usually a **local reference**. With a local ref, the call:

~~~c
/* Wrong example: a local parameter is stored beyond its lifetime. */
static jobject cached;             /* Does not own a valid reference. */

void wrong(JNIEnv *env, jobject obj) {
    (void)env;
    cached = obj;                  /* After the JNI frame ends, cached expires. */
}
~~~

leaves an invalid handle for subsequent callbacks, even if Java code is still holding the real object. Fix with `NewGlobalRef` if the contract needs to hold the object long-term, and there must be a corresponding cleanup path.

**Decision rule:** If the object is only used within the **current native call**, a local ref is usually sufficient. If it needs to be used after the call ends, in callbacks, or across threads, use **strong global** (when you need to guarantee the object stays alive), or **weak global + promote** (when you do not want to extend reachability). There is no "one best ref type" for all purposes.

## 4. Ownership Contract: Before Creating a Reference, Answer Six Questions

Design a verifiable resource using a contract table:

| Question | Value to Decide Clearly |
|---|---|
| **Creator/owner?** | Java wrapper, a dedicated native context, singleton registry, or engine? Only one owner is ultimately responsible for release |
| **Borrower?** | Which thread/callback only borrows the handle within a narrow scope? Is it allowed to keep a copy after the call? |
| **Lifetime start/end?** | `NewGlobalRef`/`NewWeakGlobalRef` succeeds → `Delete...Ref`; local → end of frame or deleted earlier |
| **GC semantics?** | Need to keep the object alive (strong) or accept the object disappearing (weak)? |
| **Concurrency?** | When Java calls `close()` at the exact moment a native callback is accessing, who prevents premature deletion? |
| **Errors and ownership?** | If creating a new ref fails, does the old ref remain? Which cleanup is mandatory even in exception/failure paths? |

Example of a reasonable contract for caching a Java listener: **the native context is the owner of a strong global ref** created upon registration; callbacks only **borrow a valid local ref** during execution; `unregister/close` blocks new callbacks, waits for running callbacks to exit, and then deletes the global; Java only frees the context itself after JNI confirms there are no remaining borrowers. If you still want the listener to be GC-eligible when Java drops it, replace strong with weak, but each callback must promote and handle the case where the referent has disappeared.

Describe ownership in terms of **actual events**, do not use "GC will clean up when needed" as a destruction mechanism. GC does not automatically know when a native cache needs to drop `NewGlobalRef` or when `malloc` needs `free`.

## 5. Runnable Example: Single Owner of a Strong Global Reference, Explicit Cleanup

We create **a single global slot for the entire process**. The Java public API consists of `retain(Object)`, `refersTo(Object)`, `release()`, and `countNonNull(Object[])`. The methods manipulating the slot are declared **`static synchronized`**, so within the scope of accessing only through this API, every slot operation is protected by the same class monitor. This is a learning pattern with **one slot**, not a design for multiple independent sessions; multi-owner expansion is in section 9.

Main flow:

~~~text
Java retain(marker)
    -> JNI argument local ref
    -> NewGlobalRef(marker) succeeds
    -> held_global holds strong ref
Java refersTo(marker)
    -> IsSameObject(held_global, marker) == JNI_TRUE
Java release()
    -> held_global = NULL
    -> DeleteGlobalRef(old)
Java refersTo(marker)
    -> held_global NULL => false, does not dereference old handle
~~~

### 5.1. Complete Java Source, JDK 17+

Create file **`src/demo/jni/ReferenceOwnershipDemo.java`**:

~~~java
package demo.jni;

import java.util.Objects;

public final class ReferenceOwnershipDemo {
    static {
        System.loadLibrary("refownership");
    }

    private ReferenceOwnershipDemo() {}

    private static native void replace0(Object value);
    private static native boolean same0(Object candidate);
    private static native void clear0();
    private static native int countNonNull0(Object[] values);

    public static synchronized void retain(Object value) {
        replace0(Objects.requireNonNull(value, "value"));
    }

    public static synchronized boolean refersTo(Object candidate) {
        return same0(candidate);
    }

    public static synchronized void release() {
        clear0();
    }

    public static int countNonNull(Object[] values) {
        return countNonNull0(Objects.requireNonNull(values, "values"));
    }

    public static void main(String[] args) {
        Object marker = new Object();
        try {
            retain(marker);
            System.out.println("retainedSame=" + refersTo(marker));
            System.out.println("retainedOther=" + refersTo(new Object()));
            System.out.println("nonNull=" + countNonNull(
                    new Object[]{marker, null, new Object()}));
        } finally {
            release();
        }
        System.out.println("afterRelease=" + refersTo(marker));
    }
}
~~~

Explanation of important design points:

- `Objects.requireNonNull` enforces the `retain` contract: the registered ref must point to a non-null object. `refersTo(null)` is still allowed, and `IsSameObject` will compare identity with null.
- `retain`, `refersTo`, and `release` share the **class monitor**. There is no other access path to `held_global` from native threads in the example. If adding a multi-threaded native worker/registry, synchronization must be added in C/context rather than relying solely on Java.
- `countNonNull` **does not use the global slot**. It demonstrates an independent native method needing to delete temporary local refs inside a loop.
- `finally` always calls `release` whether the test block finishes normally or throws an exception. `System.gc()` is not called because the example is testing **handle ownership**, not GC timing.
- `release` can be called multiple times; repeating it does not double-delete. After release, `refersTo` simply returns `false`, without accessing the deleted reference.

### 5.2. Compile Java, Generate Header from Real Signatures

From the practice directory `jni-reference`:

~~~sh
mkdir -p src/demo/jni native out
javac --release 17 -h native -d out src/demo/jni/ReferenceOwnershipDemo.java
~~~

`javac -h` generates **`native/demo_jni_ReferenceOwnershipDemo.h`** and the class at `out/demo/jni/ReferenceOwnershipDemo.class`. Do not manually edit the generated header. When running:

~~~sh
javap -s -p -classpath out demo.jni.ReferenceOwnershipDemo
~~~

the four native methods must have the following descriptors:

~~~text
replace0(java.lang.Object);           (Ljava/lang/Object;)V
same0(java.lang.Object);              (Ljava/lang/Object;)Z
clear0();                              ()V
countNonNull0(java.lang.Object[]);    ([Ljava/lang/Object;)I
~~~

The table above summarizes **methods and descriptors**, not the verbatim full `javap` output. Symbols: `L...;` is an object reference, `[` is an array, `Z` is boolean, `V` is void, `I` is int. The actual header will have corresponding C prototypes, with `JNIEnv *` and `jclass` preceding the Java parameters because all native methods are `static`.

### 5.3. Complete Native C Source, with Destruction Path and Error Path

Create file **`native/reference_ownership.c`**:

~~~c
#include "demo_jni_ReferenceOwnershipDemo.h"

static jobject held_global = NULL;

JNIEXPORT void JNICALL Java_demo_jni_ReferenceOwnershipDemo_replace0(
        JNIEnv *env, jclass ignored, jobject value) {
    (void)ignored;
    jobject replacement = (*env)->NewGlobalRef(env, value);
    if (replacement == NULL) {
        if (!(*env)->ExceptionCheck(env)) {
            jclass error_class = (*env)->FindClass(
                    env, "java/lang/OutOfMemoryError");
            if (error_class != NULL) {
                (*env)->ThrowNew(env, error_class, "Cannot create global ref");
                (*env)->DeleteLocalRef(env, error_class);
            }
        }
        return;
    }

    jobject old = held_global;
    held_global = replacement;
    if (old != NULL) {
        (*env)->DeleteGlobalRef(env, old);
    }
}

JNIEXPORT jboolean JNICALL Java_demo_jni_ReferenceOwnershipDemo_same0(
        JNIEnv *env, jclass ignored, jobject candidate) {
    (void)ignored;
    if (held_global == NULL) {
        return JNI_FALSE;
    }
    return (*env)->IsSameObject(env, held_global, candidate)
           ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT void JNICALL Java_demo_jni_ReferenceOwnershipDemo_clear0(
        JNIEnv *env, jclass ignored) {
    (void)ignored;
    if (held_global != NULL) {
        jobject old = held_global;
        held_global = NULL;
        (*env)->DeleteGlobalRef(env, old);
    }
}

JNIEXPORT jint JNICALL Java_demo_jni_ReferenceOwnershipDemo_countNonNull0(
        JNIEnv *env, jclass ignored, jobjectArray values) {
    (void)ignored;
    jsize length = (*env)->GetArrayLength(env, values);
    jint count = 0;
    for (jsize i = 0; i < length; ++i) {
        jobject element = (*env)->GetObjectArrayElement(env, values, i);
        if ((*env)->ExceptionCheck(env)) {
            return 0; /* Java exception remains pending. */
        }
        if (element != NULL) {
            ++count;
            (*env)->DeleteLocalRef(env, element);
        }
    }
    return count;
}
~~~

The code above is a complete native library for the lesson's Java source. Key points:

1. `NewGlobalRef(env, value)` creates **a new strong global ref**. Do not assign `held_global = value` directly because `value` is a local reference of the current JNI call.
2. When **creating the new ref fails**, the code keeps the old `held_global`. If the JVM has not left a pending exception, the code attempts to create an `OutOfMemoryError` for Java. Do not discard the old ref just because the replacement process failed.
3. When creation succeeds, `held_global` is updated and then the old ref is passed to `DeleteGlobalRef`. Subsequent `retain` calls do not silently accumulate unused global refs.
4. `clear0` sets the slot to `NULL` before deleting the old ref; calling it again is a no-op. The Java side never receives back or uses the deleted `old` variable.
5. `IsSameObject` compares **object identity according to JNI**, not the numeric value of the handle. Do not assume two references to the same object must have the same address/bit pattern.
6. `GetObjectArrayElement` creates a local ref for each non-null element; `DeleteLocalRef` immediately after use prevents accumulating local refs proportional to array length. If a JNI API throws an exception, the code returns with a pending Java exception; do not call further object-manipulating APIs in an error state.
7. `error_class` is returned by `FindClass` as a **local ref**, so it is deleted immediately after `ThrowNew`. Appropriate JNI cleanup functions are allowed when an exception is pending.

**Intentional limitation:** C only has one `held_global` at file scope; the `static synchronized` Java wrappers exclude concurrent slot operations **only if accessed through the wrappers**. Do not extend this design by letting a native background thread use that variable without a lock/lifetime protocol.

### 5.4. Build and Run on Linux, macOS, Windows

Run the commands from the `jni-reference` directory with the file tree:

~~~text
jni-reference/
├─ src/demo/jni/ReferenceOwnershipDemo.java
├─ native/demo_jni_ReferenceOwnershipDemo.h   (auto-generated)
├─ native/reference_ownership.c
└─ out/demo/jni/ReferenceOwnershipDemo.class   (auto-generated)
~~~

**Linux** (GCC/Clang; `JAVA_HOME` points to the JDK root; if unset and the shell has `readlink -f`, use the first command to infer it):

~~~sh
export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"
cc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Inative \
  -o librefownership.so native/reference_ownership.c

java -Xcheck:jni -Djava.library.path=. \
  -cp out demo.jni.ReferenceOwnershipDemo
~~~

**macOS** (Xcode Command Line Tools; choose architecture compatible with JVM):

~~~sh
export JAVA_HOME="$(/usr/libexec/java_home)"
cc -std=c11 -Wall -Wextra -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Inative \
  -o librefownership.dylib native/reference_ownership.c

java -Xcheck:jni -Djava.library.path=. \
  -cp out demo.jni.ReferenceOwnershipDemo
~~~

**Windows, MSVC Developer Command Prompt (CMD)** with `JAVA_HOME` and compiler matching the architecture:

~~~bat
javac --release 17 -h native -d out src\demo\jni\ReferenceOwnershipDemo.java

cl /nologo /W4 /LD ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  /Inative ^
  native\reference_ownership.c /Fe:refownership.dll

java -Xcheck:jni -Djava.library.path=. -cp out demo.jni.ReferenceOwnershipDemo
~~~

In CMD, `^` is used for line continuation; do not run raw CMD syntax in PowerShell. `loadLibrary("refownership")` automatically maps to `librefownership.so` (Linux), `librefownership.dylib` (macOS), or `refownership.dll` (Windows). `-cp out` is the Java classpath; `-Djava.library.path=.` is the location to search for the native library; they do not substitute for each other.

With the given source, **exact stdout**:

~~~text
retainedSame=true
retainedOther=false
nonNull=2
afterRelease=false
~~~

The program does not print confirmation that the object has been GC'd; **`afterRelease=false` only proves the global slot was cleared**. The Java variable `marker` can still keep the object alive, and GC has no obligation to reclaim it immediately.

The C/Java example has been verified on Linux using **JDK 21, `javac --release 17`, GCC with `-std=c11 -Wall -Wextra -Werror -pedantic`, and `java -Xcheck:jni`**. Exported JNI symbols and the four descriptors from `javap` were cross-checked. The macOS and Windows commands apply the same JNI contract but require the platform-appropriate compiler/toolchain.

## 6. Local Refs: Auto-Expiring at Frame End Can Still Overflow the Temporary Table

Every JNI call creates a local frame containing argument references and temporary refs created by JNI. The JVM normally frees the frame's local refs when the native method returns, **but does not guarantee the program can create unlimited refs in a long native call**. Therefore, if looping over thousands/millions of elements and keeping each `GetObjectArrayElement` until the end of the call, native code may consume more and more local reference space.

Pattern applied from the example:

~~~c
/* Excerpt from countNonNull0 in section 5, not a standalone C program. */
jobject element = (*env)->GetObjectArrayElement(env, values, i);
if ((*env)->ExceptionCheck(env)) {
    return 0;                    /* Exception propagates back to Java. */
}
if (element != NULL) {
    ++count;
    (*env)->DeleteLocalRef(env, element); /* Destroy immediately after last use. */
}
~~~

For a complex sequence of JNI operations creating many local refs at once, you can use:
- `EnsureLocalCapacity(env, n)`: asks the JVM to ensure space for at least `n` additional local refs in a frame; reported errors must still be handled.
- `PushLocalFrame(env, capacity)` and `PopLocalFrame(env, result)`: opens a nested frame to group temporary refs, frees them all at once, and **keeps at most one local ref `result`** passed up to the parent frame (if needed).
- `DeleteLocalRef(env, ref)`: releases each local handle early. This is the simplest choice for loops when the ref is not needed after each iteration.

A pattern illustrating a nested frame (not a standalone C file):

~~~c
/* env belongs to the current thread; used inside a JNI native method. */
if ((*env)->PushLocalFrame(env, 16) < 0) {
    return NULL;    /* Usually has pending OOME; let Java handle it. */
}

jclass type = (*env)->FindClass(env, "java/lang/String");
if (type == NULL) {
    (*env)->PopLocalFrame(env, NULL);
    return NULL;    /* Preserve FindClass Java exception. */
}

/* type is only needed inside the nested frame. */
(*env)->PopLocalFrame(env, NULL);
return NULL;
~~~

This snippet illustrates frame-managed refs, not intended to implement a specific native API. In practice, if an object created in the nested frame needs to be returned, use `PopLocalFrame(env, objectToKeep)` to pass a valid ref up to the parent frame, do not return a deleted handle. For native threads created by C itself and attached to the JVM, local refs can persist for the entire duration the thread remains attached if not freed by an appropriate mechanism; thus long loops and callbacks need proactive cleanup.

## 7. Weak Global Refs: Do Not Keep Objects Alive, but Must Avoid Check-Then-Use

Use a weak global ref when the native side wants to **remember if an object is still reachable**, without letting the cache/callback itself prevent GC from reclaiming the object. Examples include an observer that does not own the listener or a cache key not allowed to extend the lifetime of a Java object.

**Unsafe:**

~~~c
/* Pattern illustrating a race bug; weak is a validly created jweak. */
if (!(*env)->IsSameObject(env, weak, NULL)) {
    /* GC can still clear weak before the next JNI call. */
    use_object_somehow(weak); /* use_object_somehow is just an illustrative name. */
}
~~~

`IsSameObject(weak, NULL)` only answers the state **at the time of the check**. GC can run between the check and the use. The correct pattern is to attempt to **promote to a strong local** before using:

~~~c
/* Snippet inside a JNI native method, not a standalone C program. */
jobject alive = (*env)->NewLocalRef(env, weak);
if (alive == NULL) {
    /* Referent is gone, or unable to create local ref.
       Check pending exception and handle according to contract. */
    return;
}

/* alive is a strong local ref in the current frame. Use the object here. */
consume_java_object(env, alive); /* Illustrative application function. */

(*env)->DeleteLocalRef(env, alive);
~~~

`NewLocalRef` returns `NULL` if the referent has been GC'd, the input reference is null, or ref creation fails due to lack of resources. When `alive` is valid, the strong local ref **keeps the referent reachable** during the operation, avoiding the "object disappeared right after checking" race. When done, delete `alive` so strong reachability is not held longer than necessary.

The owner of `jweak` must still call:

~~~c
/* In cleanup, when no borrower is using weak. */
(*env)->DeleteWeakGlobalRef(env, weak);
weak = NULL;
~~~

**A weak global does not disappear on its own as a handle resource** just because the referent has been GC'd; GC may make that handle point to a functionally gone object, but the responsibility of freeing the weak global handle still belongs to the owner. Do not use `System.gc()` as a mandatory test: the call is a hint and GC timing is non-deterministic. A proper test can verify the "promote returns NULL" path using a controlled model/stub or non-mandatory observation, without asserting that the object must be reclaimed within a fixed time window.

## 8. Use-After-Scope Bugs: A Live Object Does Not Revive a Local Handle

### Bug 1: Storing a local parameter in a static C variable

~~~c
/* Wrong: local ref is only valid within the current JNI call. */
static jobject listener;

JNIEXPORT void JNICALL Java_demo_jni_SomeClass_register(
        JNIEnv *env, jclass ignored, jobject callback) {
    (void)env;
    (void)ignored;
    listener = callback;
}

/* A native callback called later uses listener => invalid reference. */
~~~

Fix: `listener = NewGlobalRef(env, callback)` on successful registration; `DeleteGlobalRef(env, listener)` on cancellation; and synchronize to prevent callbacks from continuing to use it after freeing. If you do not want to keep the callback alive, store `NewWeakGlobalRef` and promote on each callback.

### Bug 2: Calling DeleteLocalRef and continuing to use it

~~~c
jobject temporary = (*env)->GetObjectArrayElement(env, values, 0);
(*env)->DeleteLocalRef(env, temporary);
/* Using temporary in a JNI API after this line is wrong, even though the array still holds the object. */
~~~

After `DeleteLocalRef`, **the `temporary` handle is invalid**. To access it further, obtain a new valid reference while a valid source still exists. Do not check "temporary is not NULL" and assume it is still alive; non-null does not equal validity.

### Bug 3: Deleting a global ref while a callback is still running

~~~text
Callback thread             Close thread
-----------------------     ----------------------------
reads shared global handle
                            DeleteGlobalRef(handle)
CallObjectMethod(handle)    <- using deleted handle: unsafe
~~~

This is a race between **borrow** and **delete**. You must organize an ownership/call-in-flight protocol: a lock/registry protecting state, holding a separate strong local ref during the callback, or waiting for all callbacks to finish before deleting. Merely declaring the pointer `volatile` does not solve lifetime.

### Bug 4: Forgetting to release global refs because "no Java variables remain"

A Java wrapper may lose all normal Java references, yet the global JNI root remains alive so the object stays reachable. Missing `DeleteGlobalRef` leads to **leaking and retaining the Java object** (and potentially retaining the entire object graph, classloader, and other resources). Missing `DeleteWeakGlobalRef` leaks native/JVM handle resources even without keeping the referent alive. Place cleanup in normal destruction, error, timeout, and shutdown paths.

## 9. From Singleton Demo to an API with an Explicit Owner

The example in section 5 uses **one global slot** to focus on lifecycle. A real library has multiple Java sessions/callbacks and therefore cannot just hold a single shared `static jobject held_global` variable: session A could replace/delete a reference belonging to session B.

A multi-session contract should look like:

~~~text
Java Session
  OPEN
    | register: native context allocated + NewGlobalRef
    v
  ACTIVE (each Session owns exactly 1 native context)
    | operation: borrows reference for a short duration
    | close: blocks new operations, waits for running operations
    v
  CLOSING
    | native context DeleteGlobalRef (and frees own resources if any)
    v
  CLOSED (subsequent close is no-op; new operations report "closed")
~~~

Suggested responsibility table:

| Resource | Who Creates | Who Is Responsible for Destruction | What Borrowers May Do |
|---|---|---|---|
| JNI local ref from parameter | JVM/current call | JVM when frame ends; native may delete early if in right scope | Only use within valid frame/thread |
| Strong global ref listener | A native context/registration | That context itself on `close/unregister` | May use when guaranteed still alive and not concurrently deleted |
| Weak global ref cache entry | A native cache entry | That cache entry itself on evict/close | Promote to local before use; accept being cleared |
| Native buffer/struct | Native allocator or caller | Owner defined by C API (`free` or release function) | Do not use after free; do not conflate with JNI ref |
| Java `AutoCloseable` wrapper | Java code | Call `close()` via `try-with-resources` lexical scope | Do not reuse closed wrapper |

A Java wrapper sample illustrating only **the state mechanism**, without the C registry implementation:

~~~java
// Design fragment: not a standalone runnable program.
public final class Session implements AutoCloseable {
    private boolean closed;

    public synchronized void perform() {
        if (closed) {
            throw new IllegalStateException("Session closed");
        }
        // Call native operation under the same lifetime protection mechanism.
    }

    @Override
    public synchronized void close() {
        if (!closed) {
            // Block new callbacks/operations, wait for running callbacks
            // (if native registry uses a separate thread), then native release.
            closed = true;
        }
    }
}
~~~

Real code must define the order when release fails and how synchronization works across both Java and native. For long calls, do not hold a Java monitor while native is calling back into Java along a path that could re-enter the same object and cause deadlock; instead use an `OPEN/CLOSING/CLOSED` state, count **in-flight operations**, a lock/condition, or a clear execution owner thread. Only transition to CLOSED after resources have actually been released or there is a well-founded retry/recovery strategy.

If Java holds a `long nativeHandle` containing the pointer/ID of the C context, `nativeHandle` **is not a jobject**. You must prevent stale handles and double-free: invalidate the handle on the Java side, validate in the native registry, disallow use-after-close, and beware of pointer addresses being reused by the allocator (ABA). A handle table with a **generation counter** is usually easier to control than letting Java hold arbitrary raw addresses.

**`Cleaner`** can serve as a fallback path when the application forgets to close, but proper cleanup must be **explicit `close()` / `try-with-resources`** when the lifetime is deterministic. Do not rely on `finalize()` (a mechanism being phased out), do not rely on GC to guarantee destruction order between native resources and callbacks, and do not let the lambda/cleaning action accidentally retain the very referent that needs to be cleaned up.

## 10. Multithreading: Global References Work Across Threads, but JNIEnv Does Not

A strong global ref can be used from another thread **when that thread has properly attached to the JVM and the ref is still valid**. However, `JNIEnv *` is an interface pointer **valid only for the thread that received it**; do not store `JNIEnv *` in a C global and use it on another worker thread.

If a native library creates its own thread and needs to call JNI:
1. Have a valid `JavaVM *` stored/provided per the JNI contract.
2. The worker thread calls `AttachCurrentThread` (or the appropriate daemon variant), receiving **that thread's own `JNIEnv *`**.
3. When calling Java, if using a weak ref then promote; if using a shared strong global then block concurrent deletion or create a local borrow under a lock.
4. Handle Java exceptions thrown during callbacks, and free local refs generated in loops.
5. Threads attached by native code must `DetachCurrentThread` before exiting when safe; do not call detach while Java methods are still on the stack.

Attach snippet (illustrating the interface, not a standalone multithreaded program):

~~~c
/* JavaVM *vm is validly provided by the JVM and persists for the thread's scope. */
JNIEnv *env = NULL;
jint status = (*vm)->AttachCurrentThread(vm, (void **)&env, NULL);
if (status != JNI_OK) {
    /* Handle attach error; never use env. */
    return;
}

/* JNI calls on current thread; clean up refs created during work. */

(*vm)->DetachCurrentThread(vm);
~~~

If the library receives callbacks when close occurs, it must ensure **close does not delete the ref/context before running callbacks**. Even though a global `jobject` can be used cross-thread, reading/writing the C variable holding it does not automatically have synchronization. Executing JNI under a class monitor as in section 5 only protects **call paths through those exact Java wrappers**; a native worker thread must have C-side synchronization or a dedicated owner thread design.

`JNI_OnUnload` can be a cleanup point for resources belonging to the library/classloader lifecycle, but it is not a reason to skip `close/unregister` on shorter-lived objects. When a native library holds a `jclass` via a strong global, it can extend the lifetime of the class and classloader; keep that in mind when caching.

## 11. Failure-Safe Cleanup: Do Not Leak When APIs Fail

### Create the new strong ref first, then delete the old ref

Safe pattern in the demo:

~~~c
jobject replacement = (*env)->NewGlobalRef(env, value);
if (replacement == NULL) {
    /* Keep old held_global, propagate or create Java exception. */
    return;
}

jobject old = held_global;
held_global = replacement;
if (old != NULL) {
    (*env)->DeleteGlobalRef(env, old);
}
~~~

This is **failure atomicity** within the scope of a synchronized slot: if allocating the new ref fails, the old state remains. If you deleted the old ref first and then called `NewGlobalRef`, a memory error could cause the registry to lose the old owner even though the replacement operation failed.

### JNI APIs that throw exceptions must be handled on the error branch

Many JNI functions can set a **pending Java exception**. In that case you must not treat a reference/primitive return value as success and continue using it; check the return value and `ExceptionCheck` when an API can fail, perform appropriate cleanup, and then return so the JVM propagates the exception back to Java. Do not "swallow" exceptions with `ExceptionClear` unless the contract is explicit and you have meaningfully translated/recovered the error state.

In `countNonNull0`, if `GetObjectArrayElement` fails, the local refs from previous loop iterations have already been deleted, and the native method returns, propagating the pending exception back to Java. If a complex function has already allocated C heap or global refs before an error occurs, there must be a cleanup path for **every resource that was successfully allocated**.

### Leaks can happen on both sides

~~~text
Resource C context:  malloc -> context
Java reference root: NewGlobalRef -> object graph
                               |
close/unregister:
    stop new calls + wait in-flight callbacks
    DeleteGlobalRef(env, context->listener)
    context->listener = NULL
    free(context)
~~~

If you only call `free(context)` and skip `DeleteGlobalRef`, the JNI global table still holds the root in the JVM. If you only call `DeleteGlobalRef` and skip `free`, the native context still occupies memory. The actual order must match the context's invariants and locking; the diagram above shows **two independent deallocation obligations**.

## 12. How to Test Ownership and Observe Bugs

### Deterministic behavior tests

The demo provides observable assertions **without needing GC to run**:

1. After `retain(marker)`, `refersTo(marker)` returns `true`.
2. Compared with another `new Object()`, `refersTo(...)` returns `false` because identity is checked.
3. The `countNonNull` loop returns 2 for a three-element array with one `null`; native deletes the local ref of each used element.
4. After `release()`, `refersTo(marker)` returns `false`. Calling `release()` again does not crash/double-delete.

In a multi-owner test, add tests: destroying A does not affect B; failed replace keeps the old ref; closing concurrently with callbacks does not use-after-delete; cancelled callbacks are not invoked again; native memory is always released on all paths.

### JNI environment tests

Run:

~~~sh
java -Xcheck:jni -Djava.library.path=. \
  -cp out demo.jni.ReferenceOwnershipDemo
~~~

HotSpot can warn or abort when it detects certain JNI misuses. This is a diagnostic aid; **it does not guarantee every misuse will be detected**, especially concurrency races or C memory corruption. Combine methods by symptom:

| Symptom | Hypothesis to Investigate | How to Narrow Down |
|---|---|---|
| Memory/JVM JNI reference usage grows after repeated registrations | Missing `DeleteGlobalRef` or `DeleteWeakGlobalRef` | Count create/delete calls, cross-check lifecycle/registration, inspect JNI global roots with supported heap/profiler tools |
| Java listener/classloader still not GC'd after unregister | Strong global root or Java owner still holds object | Inspect reachability from GC roots, especially JNI global refs; do not conclude from a single `System.gc()` |
| Crash/corrupted reference after callback | Expired local ref, prematurely deleted global, unattached thread, or wrong ABI | Check ref type/lifetime/thread; run `-Xcheck:jni` and native trace |
| Local reference table overflow when processing many objects | Each loop iteration creates refs without deleting | `DeleteLocalRef` in loop, or `PushLocalFrame/PopLocalFrame` |
| Works single-threaded but crashes on shutdown | Callback/operation using resource during close | Race test with barrier/latch, locks, and in-flight counter |
| Native heap grows even though global refs are deleted | Native allocation not freed | Check malloc/free symmetry and release of each native resource |
| Weak cache works intermittently | GC cleared the referent | Check promote code; treat `NewLocalRef(...) == NULL` as normal |

Do not write default tests that **assert GC must run within N seconds**, because GC determinism is not part of the application contract. Test ownership via state/create–release symmetry and post-close access checks; use GC logs, heap dumps, and stress tests for additional **diagnostics**, not as sole proof.

## 13. Design Checklist Before Publishing a Native API

- [ ] Every JNI reference is classified as **local / global / weak global**; locals are not stored past their frame.
- [ ] Every `NewGlobalRef` has a `DeleteGlobalRef` path; every `NewWeakGlobalRef` has a `DeleteWeakGlobalRef`. Error, replace, and shutdown paths are all accounted for.
- [ ] If using weak: always create a temporary strong local/global to use it; handle `NULL` result from promote.
- [ ] Do not use a handle after `DeleteLocalRef`/`DeleteGlobalRef`/`DeleteWeakGlobalRef`; do not rely on `jobject` bit values to compare identity.
- [ ] Loops creating local refs have early cleanup, or a nested frame with capacity and cleanup.
- [ ] Owners and borrowers are clearly named; `close/unregister` is an explicit, idempotent action that blocks new operations.
- [ ] No race exists between callback/global read and delete; there is a synchronization protocol or protected local borrow.
- [ ] `JNIEnv *` is only used on the thread that created it; native workers must attach/detach properly.
- [ ] Native memory and JNI refs are two separate resources; both have balanced cleanup.
- [ ] Java exceptions are propagated/translated properly; do not drop the old ref when creating a replacement ref fails.
- [ ] Test deterministic results and lifecycle without assuming GC timing; use `-Xcheck:jni` when possible.

## 14. Self-Assessment Questions

**Question 1.** A native method receives `jobject listener`, stores it directly into `static jobject saved` for a callback 10 minutes later. Java still holds the listener in a field. Is the code correct?  
**Answer:** No. `listener` in the JNI method is a local handle and its lifetime ends when the native frame ends. The object staying alive does not validate the old handle. You must create a strong global ref (or weak global + promote depending on semantics) and clean up on unregister.

**Question 2.** After `DeleteGlobalRef`, is the Java object guaranteed to be reclaimed immediately?  
**Answer:** No. Deleting only removes one JNI strong root. Other Java/JNI roots may still hold the object; GC operates asynchronously and has no guarantee of a specific timing.

**Question 3.** If a JNI weak global ref is still non-null, can we check it once and call a method afterward?  
**Answer:** Insufficient. GC can clear the referent between the check and the use. You must call `NewLocalRef(env, weak)` (or `NewGlobalRef`) to obtain a temporary strong ref, check the result, and delete the new ref when done.

**Question 4.** Why is a valid global `jobject` usable cross-thread while `JNIEnv *` is not?  
**Answer:** A global reference belongs to the JVM-wide reference table with an owner-managed lifetime; `JNIEnv *` is an interface pointer with state/contract tied to a thread. A worker thread needs to attach and receive its own env.

**Question 5.** A native context contains a `jobject global` and a `malloc` buffer. Is `free(context)` alone sufficient?  
**Answer:** No. You must call `DeleteGlobalRef` per JNI before losing the handle; and also free the buffer/context with the appropriate allocator, after no callbacks are using it.

**Question 6.** Two Java threads call `close` and `call` concurrently on the same native session. Why is checking `if (!closed)` on the Java side not necessarily enough?  
**Answer:** If the native call continues running after the Java check, `close` can delete the global ref/context mid-call. You need atomic acquire/borrow or an in-flight counter + synchronization across the right scope; `close` only releases when no borrowers remain.

## 15. Takeaways and References

**Key takeaway:** JNI reference design always consists of two parts: **handle lifetime** and **Java referent reachability**. Local refs must stay within a valid frame/thread; strong globals are resources that must be deleted and can keep objects alive; weak globals do not keep objects alive but still require handle deallocation and safe promotion when used. One owner is responsible for release, all borrowers have clear boundaries, and close must coordinate with callbacks/concurrency so there is no use-after-delete.

Official technical documentation for reference: [Oracle JNI Design Overview — Referencing Java Objects](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html), [Oracle JNI Functions — Local/Global/Weak Global References, NewLocalRef, and Push/PopLocalFrame](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html), [Oracle JNI Invocation API — AttachCurrentThread and DetachCurrentThread](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/invocation.html). For the Android ecosystem, [Android NDK JNI tips](https://developer.android.com/ndk/guides/jni-tips) has additional practical examples of reference lifetimes; JNI rules should still be cross-checked against the JVM/toolchain specification in use.
