# Per-Invocation and Per-Thread Scope of Local References (JNI Local References)

## 1. Core Problem

In the Java Native Interface (JNI), C/C++ code can hold `jobject`, `jclass`, `jstring`, `jarray`, and similar reference types to operate on Java objects. However, a `jobject` value is **not a C pointer pointing directly to an object on the heap**. It is a **JNI reference** managed by the JVM. The most common kind of reference is a **local reference**.

There are two boundaries you must understand:

1. **Per-invocation:** Local references received when Java calls a native method, or created during that call, are generally valid only within the **current native invocation**; when the native method returns, the JVM automatically reclaims the local references belonging to that invocation's frame.
2. **Per-thread:** A local reference is valid only on the **thread that created it**. You must not pass a raw local `jobject` value to another thread for that thread to use, even if the original invocation has not yet finished.

For a **native thread that calls `AttachCurrentThread`** on the JVM, there is an important timing exception: local references on this thread **are not automatically cleaned up by default when an ordinary C native function returns**; unless explicitly deleted or managed with a local frame, they can persist until the thread detaches.

Three questions to decide whether a local reference is still usable:

- **Which thread was it created on?** Is the current thread the exact thread that created the reference?
- **Is the JNI frame/invocation containing it still alive?** Has it already returned, or had `DeleteLocalRef` or `PopLocalFrame` called?
- **Is it actually a valid JNI reference?** Do not reuse a handle that has already been destroyed, even if its bit value still sits in a C variable.

Remember: **the lifecycle of a local JNI reference is different from the lifecycle of the referenced Java object**. Deleting a local reference does not mean destroying the object. If Java or another valid strong reference still holds the object, it continues to exist; if the object is no longer reachable, the GC may reclaim it according to JVM mechanisms.

## 2. Where Are Local References Created?

Typical sources:

| Source | Example | Type/lifecycle |
| --- | --- | --- |
| Object parameters passed from Java to a native method | `jobject receiver`, `jstring text`, `jobjectArray items` | Local references valid within the current native invocation |
| JNI functions that create objects | `NewStringUTF`, `NewObject`, `NewObjectArray` | Typically return a local reference |
| JNI functions that look up classes | `FindClass`, `GetObjectClass` | Return a local `jclass` |
| Retrieving an element of an object array | `GetObjectArrayElement` | Returns a local `jobject`, even when the Java array lives longer |
| Creating an additional local handle to the same object | `NewLocalRef` | A new local reference with its own lifecycle |
| Passing a result out of a child frame | `PopLocalFrame(env, result)` | Creates a valid local reference in the parent frame on success |

Simple illustrative Java/C example:

~~~java
// Java: signature illustration only.
class Example {
    private native void inspect(String value);
}
~~~

~~~c
/* C: illustrative signature, not a standalone compilable program. */
JNIEXPORT void JNICALL Java_Example_inspect(
        JNIEnv *env, jobject receiver, jstring value) {
    jclass actualClass = (*env)->GetObjectClass(env, value);
    if (actualClass == NULL) {
        return; /* Example: check for error/exception per contract. */
    }

    /* receiver, value, and actualClass are JNI local references
       that may only be used on a valid thread and frame. */
    (*env)->DeleteLocalRef(env, actualClass);
}
~~~

In the example, `receiver` and `value` are local references provided by the JVM as parameters; `actualClass` is a new local reference created by `GetObjectClass`. Normally you do not need to manually delete parameters passed from Java at the end of a short native method; `actualClass` can be deleted early because it is no longer needed. The JVM cleans up the rest when the native method returns.

**Do not confuse a "local C variable" with a "local JNI reference".** A `jobject ref` variable can be placed on the C stack, in a struct, or copied to another C variable. **The C scope of the variable does not determine the validity of the JNI reference**; the contract regarding the thread and JNI frame is what decides.

## 3. Lifecycle Across a Single Java Call to a Native Method

Suppose Java makes two calls:

~~~text
Java thread T
  |
  +-- calls native method (1st time)
  |      +-- JVM provides JNI frame F1
  |      +-- jobject/jstring parameters are local references of F1
  |      +-- FindClass / GetObjectClass create new local refs
  |      +-- C code uses valid refs
  |      +-- native method returns
  |      +-- JVM frees local refs of F1
  |
  +-- calls native method (2nd time)
         +-- JVM provides a separate JNI frame F2
         +-- creates new local refs for this invocation
         +-- refs belonging to F1 do not come back to life
~~~

Key points to understand:

- **Two consecutive calls, even on the same Java thread, are two different local reference scopes.** A local `jobject` obtained from the 1st call must not be cached and used in the 2nd call.
- Returning from a native method does not destroy all Java objects it saw; it only ends the JNI local handles belonging to that invocation.
- The JVM handles **the `jobject` value returned from a native method** specially, so that Java receives a valid object on the calling side. Therefore, you can return a newly created local `jstring` **without** turning it into a global reference.
- A local reference on which `DeleteLocalRef` has been called becomes invalid **at the exact moment of deletion**, without waiting for the native method to finish.
- If `PushLocalFrame` and `PopLocalFrame` are used during an invocation, local refs of the child frame become invalid upon popping, which can be earlier than when the native method returns.

### Returning a Java Object Across the Native Method Boundary

Valid pattern:

~~~c
/* Example body of a JNI native method returning jstring. */
JNIEXPORT jstring JNICALL Java_Example_makeMessage(
        JNIEnv *env, jclass owner) {
    (void) owner;
    return (*env)->NewStringUTF(env, "hello");
}
~~~

`NewStringUTF` returns a local `jstring`. The JVM takes the object as the Java result before cleaning up the local frame. After the call, Java can store the String in a field or variable without needing a global JNI reference.

**Do not** create a local `jstring`, call `DeleteLocalRef` on that handle, and then return the deleted handle. If you want to clean up a nested frame while still returning an object, use `PopLocalFrame(env, result)` and **the return value of that function** (see section 6).

## 4. Per-Thread Lifecycle: What "Local" Actually Constrains

`JNIEnv*` is the JNI interface bound to the **current thread**. Likewise, a **local `jobject` is valid only on the thread that created it**. It does not become a shared reference merely because C can copy a few bytes of the variable to another thread.

~~~text
Java thread T1                     Java thread T2
------------------                 --------------------
JNIEnv* env1                       JNIEnv* env2
local jobject obj1                 local jobject obj2

obj1 is valid only on T1           obj2 is valid only on T2

T1 passes obj1 directly to T2      -> VIOLATES JNI CONTRACT
T1 passes env1 directly to T2      -> VIOLATES JNI CONTRACT
~~~

**Even when T1 and T2 access the same Java object**, each thread still needs **a valid JNI reference in its own context** or must access the object through proper JVM/Java mechanisms. When you need to share a JNI reference across threads, the usual approach is to create a valid **global reference** (`NewGlobalRef`) and then, if needed, create a new local reference on the receiving thread (`NewLocalRef`).

A local reference valid on T1 is also not automatically allowed to be used with T2's `JNIEnv*`. Separate two concepts:

1. **Which thread does the JNI reference belong to?** T1/T2; local refs must not be used across threads.
2. **Is the Java object thread-safe?** Even with a valid shared global ref, the data inside the object may still require locks, immutable state, or appropriate Java synchronization mechanisms.

In addition, `JavaVM*` is a JVM-level interface that can be shared across threads so each thread can obtain its own `JNIEnv*` via `AttachCurrentThread`/`GetEnv`, depending on whether the thread is already attached. Do not cache thread A's `JNIEnv*` to use on thread B.

## 5. Complete Java 17 + JNI Program: One Native Method, Multiple Calls, and Multiple Threads

The following example runs on **Linux + JDK 17+ + a GCC compiler compatible with the JVM architecture**. The program shows Java calling the same native method sequentially on the main thread and on another Java thread. Each call has its own local references. Another native function returns a valid `jstring` to Java.

### 5.1. `LocalRefLifetimeDemo.java`

~~~java
public final class LocalRefLifetimeDemo {
    static {
        System.loadLibrary("localrefs");
    }

    private static native int sumUtf16Lengths(String[] labels);

    private static native String nativeGreeting();

    public static void main(String[] args) throws InterruptedException {
        String[] mainLabels = {"JNI", "local", null};

        System.out.println(
                "mainSum=" + sumUtf16Lengths(mainLabels));
        System.out.println(
                "message=" + nativeGreeting());

        Thread worker = new Thread(() -> {
            String[] workerLabels = {"thread", "JNI"};
            int total = sumUtf16Lengths(workerLabels);
            System.out.println("workerSum=" + total);
        }, "jni-worker");

        worker.start();
        worker.join();
    }
}
~~~

### 5.2. `localrefs.c`

~~~c
#include <jni.h>
#include "LocalRefLifetimeDemo.h"

JNIEXPORT jint JNICALL Java_LocalRefLifetimeDemo_sumUtf16Lengths(
        JNIEnv *env, jclass owner, jobjectArray labels) {
    (void) owner;

    if (labels == NULL) {
        jclass npe = (*env)->FindClass(
                env, "java/lang/NullPointerException");
        if (npe != NULL) {
            (*env)->ThrowNew(env, npe, "labels must not be null");
            (*env)->DeleteLocalRef(env, npe);
        }
        return 0;
    }

    jsize n = (*env)->GetArrayLength(env, labels);
    jint total = 0;

    for (jsize i = 0; i < n; i++) {
        /* Each call can create a local JNI reference. */
        jobject item = (*env)->GetObjectArrayElement(
                env, labels, i);

        if ((*env)->ExceptionCheck(env)) {
            return 0; /* Let the pending exception propagate back to Java. */
        }

        if (item != NULL) {
            total += (*env)->GetStringLength(
                    env, (jstring) item);

            /* Clean up immediately, do not hold until the end of a large loop. */
            (*env)->DeleteLocalRef(env, item);
        }
    }

    return total;
}

JNIEXPORT jstring JNICALL Java_LocalRefLifetimeDemo_nativeGreeting(
        JNIEnv *env, jclass owner) {
    (void) owner;

    /* Returning a local jstring to Java is valid. */
    return (*env)->NewStringUTF(env, "hello from JNI");
}
~~~

Why the key lines are valid:

- Java declares the method as `static native`, so the second JNI argument is `jclass owner`. An instance method would receive `jobject receiver` in this position.
- `String[]` maps to `jobjectArray`, **not `jstring*`**. Each time `GetObjectArrayElement` returns a non-`NULL` object, it is a new local JNI reference.
- Because Java guarantees the array is `String[]`, a non-null element can be used with `GetStringLength` via the cast `(jstring) item`. The function returns the number of **UTF-16 code units**, not necessarily the number of Unicode code points.
- `DeleteLocalRef` is called **inside the loop** after finishing each element; this is important when the number of elements is very large, because the native frame does not automatically clean up each local ref on every iteration.
- `nativeGreeting` returns a local `jstring` to Java, which the JVM handles when the native method finishes; Java receives a valid String object.

The example uses very small input data so `jint total` does not overflow. When writing a general-purpose API, you must determine length/sum bounds and choose appropriate Java/JNI types.

### 5.3. Compiling and Running

Create both files in the same directory. Set `JAVA_HOME` to point to JDK 17+ and run:

~~~bash
javac -h . LocalRefLifetimeDemo.java
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o liblocalrefs.so localrefs.c
java -Djava.library.path=. LocalRefLifetimeDemo
~~~

**Exact** stdout on Linux under the conditions above:

~~~text
mainSum=8
message=hello from JNI
workerSum=9
~~~

Checking the numbers: `"JNI"` has 3 UTF-16 units, `"local"` has 5, null is not added, so the first total is `8`. `"thread"` has 6, `"JNI"` has 3, so the worker thread's run is `9`. `worker.join()` ensures the worker's result line finishes printing before `main` exits and the lines before `start()` have already been printed in order.

**Important note:** The two calls in the program **do not share any local JNI reference**. The example shows the valid way for each thread to receive fresh JNI parameters and create/delete its own local references; attempting to pass a raw `jobject` from the first native invocation to a later invocation is a bug even if the output looks normal on a given JVM.

On macOS, use the JNI header `$JAVA_HOME/include/darwin` and build a library named `liblocalrefs.dylib` with appropriate linker options such as `clang -dynamiclib`. On Windows, use `localrefs.dll` and include `%JAVA_HOME%\include\win32`, with a toolchain matching the CPU/ABI. Take native symbol names from the header generated by `javac -h` to avoid mistakes with packages, overloads, and JNI name mangling.

## 6. Early Reclamation: `DeleteLocalRef`, `EnsureLocalCapacity`, and Local Frames

The JVM **automatically reclaims local references when the native method returns**, but not when each loop iteration finishes. Suppose:

~~~c
/* Bad pattern in a native method processing very many elements. */
for (jsize i = 0; i < n; i++) {
    jobject obj = (*env)->GetObjectArrayElement(env, values, i);
    /* Process obj, but forget DeleteLocalRef... */
}
~~~

With a large `n`, the loop can accumulate a huge number of local handles in the same native frame, causing memory/reference-table pressure or JNI errors. Do not reason that reassigning the C variable `obj` makes the previous iteration's local reference disappear; **overwriting a variable does not delete a JNI reference**.

A reasonable pattern for short operations:

~~~c
/* Illustrating the body of a native method, where values is a valid jobjectArray. */
jsize n = (*env)->GetArrayLength(env, values);

for (jsize i = 0; i < n; i++) {
    jobject obj = (*env)->GetObjectArrayElement(
            env, values, i);

    if ((*env)->ExceptionCheck(env)) {
        return; /* Illustrative signature assumes void return. */
    }

    if (obj != NULL) {
        /* Process obj while still valid... */
        (*env)->DeleteLocalRef(env, obj);
    }
}
~~~

Three APIs used to manage capacity and frames:

| JNI API | Meaning | Use case |
| --- | --- | --- |
| `DeleteLocalRef(env, ref)` | Deletes **one specific local reference** | Clean up an object once done processing it, especially in loops |
| `EnsureLocalCapacity(env, capacity)` | Requests the JVM to ensure capacity to create at least `capacity` more local references | Prepare for a code section using many local refs; check the error result |
| `PushLocalFrame(env, capacity)` | Creates a child frame for local refs, ensuring initial capacity | Group a batch/computation that has many local refs |
| `PopLocalFrame(env, result)` | Cleans up the child frame's refs; can **retain one result object** in the previous frame | End a batch while returning only one needed reference |

According to the JNI specification, before entering a native method, the JVM guarantees room for **at least 16 local references**. Actual limits and overflow handling can vary between JVMs; do not write code assuming you can accumulate them indefinitely. `EnsureLocalCapacity` or `PushLocalFrame` can report an error (often with a pending `OutOfMemoryError`) if the JVM cannot allocate enough resources; you must check the return value.

### Keeping a Result After `PopLocalFrame`

Pattern **illustrating only the body of a native method returning `jstring`**, not a standalone C program:

~~~c
if ((*env)->PushLocalFrame(env, 8) < 0) {
    return NULL; /* There may be a pending OutOfMemoryError. */
}

jstring inside = (*env)->NewStringUTF(env, "result");

/* Clean up the child frame, transfer the result to the parent frame. */
return (jstring) (*env)->PopLocalFrame(env, inside);
~~~

- `inside` is initially a local reference in the child frame.
- `PopLocalFrame` cleans up the child frame's local references and returns **a new reference** to the same object in the previous frame, if there is a valid result.
- The old `inside` value becomes invalid after popping. You must only use **the value returned by `PopLocalFrame`**.
- If creating the String fails, there may be a pending exception; `PopLocalFrame` is a frame-cleanup operation permitted in appropriate cases, and the result will be `NULL`.

`DeleteLocalRef` and `PopLocalFrame` **do not directly `malloc`/`free` native memory**; they release JNI handles. Similarly, `GetStringUTFChars`/`GetIntArrayElements` return **temporary data pointers that have their own release APIs** (`ReleaseStringUTFChars`/`ReleaseIntArrayElements`), which must not be confused with `DeleteLocalRef`.

## 7. Self-Attaching Native Threads: A Different Lifecycle Boundary from Native Methods

Consider two scenarios:

**Scenario A: Java creates a Thread, and then the Thread calls a native method.**

~~~text
Java Thread -> JNI native method -> JNI local refs
            -> native method returns -> JVM automatically reclaims the call's local refs
~~~

This is how the `LocalRefLifetimeDemo` program works. Each Java thread has its own JNI context. The native method invocation still has a clear call scope, and the JVM reclaims the invocation's local refs when it returns.

**Scenario B: C/C++ creates an OS/native thread, and then attaches it to the JVM.**

~~~text
Native thread created by C/C++
    |
    +-- AttachCurrentThread(JavaVM*, ...) -> obtains its own JNIEnv*
    |
    +-- multiple JNI API calls, creating local refs
    |   (A C function return is NOT automatically a JNI native-method boundary)
    |
    +-- DeleteLocalRef / PushLocalFrame + PopLocalFrame when done
    |
    +-- DetachCurrentThread -> ends the attachment and remaining refs
~~~

According to the JNI specification, **local references created on an attached native thread do not automatically disappear each time a C helper function returns**. If the thread is long-running, you should not wait until `DetachCurrentThread` for the JVM to clean everything up; you must actively manage refs.

For native code that manages threads:

- You can keep `JavaVM*` so threads can obtain their own `JNIEnv*`. `JNIEnv*` is **not shared** between threads.
- A native thread wanting to call JNI must first attach if not already attached; an already-attached thread can use `GetEnv`/`AttachCurrentThread` according to the contract.
- For local refs created in a long-running native thread, use `DeleteLocalRef` in loops or `PushLocalFrame`/`PopLocalFrame` to bound resources.
- Before the native thread terminates, detach properly; do not hold local JNI refs after detaching.
- When a Java callback runs inside an attached thread, call and callback boundaries can be nested; still distinguish which local frame owns each reference.

Note: `AttachCurrentThread` does not make a local handle created on another thread suddenly valid on the newly attached thread. Attaching only provides **a valid JNI context for the current thread itself**.

## 8. When You Need to Use an Object in Another Call or Another Thread

### 8.1. Use a Global Reference, Then Reclaim It at the Right Time

Local references **must not be cached** for a later JNI call or another thread. If you need to keep a Java object across those boundaries:

1. While the local reference is still valid, call `NewGlobalRef(env, local)`.
2. Store the global reference in a structure with appropriate ownership and synchronization.
3. Once another thread has attached to the JVM and has its own `JNIEnv*`, it can use the global reference; when a local reference is needed on that thread, call `NewLocalRef(env, global)`.
4. When there are no more users, call `DeleteGlobalRef(env, global)` exactly once according to the ownership design. Ensure no accesses are still in progress.

**Isolated illustrative** JNI code example, not a standalone C program and omitting locking/thread lifecycle:

~~~c
/* On thread T1, local belongs to the current invocation: */
jobject shared = (*env)->NewGlobalRef(env, local);
if (shared == NULL) {
    /* Possibly out of memory; do not use shared. */
}

/* After transferring shared via a synchronization protocol to thread T2
   and T2 has its own JNIEnv* env2: */
jobject mine = (*env2)->NewLocalRef(env2, shared);
if (mine != NULL) {
    /* Use mine only on T2, within a valid scope. */
    (*env2)->DeleteLocalRef(env2, mine);
}

/* When all users have stopped, one owning side cleans up the global: */
(*env2)->DeleteGlobalRef(env2, shared);
~~~

Do not copy the snippet above verbatim into a multithreaded application: it **lacks synchronization, handle handoff, error reporting, and deciding which thread cleans up**, because its purpose is only to show the right reference types. In practice, `NewGlobalRef` can fail; if a Java exception is pending it must be handled per contract; and the state of the variable holding the global ref must be protected against use-after-delete.

**A global reference is a strong reference**, so it can prevent the GC from reclaiming the Java object if you forget `DeleteGlobalRef`. If you need a weak reference that does not keep the object alive, JNI provides **weak global references** (`NewWeakGlobalRef`, `DeleteWeakGlobalRef`); when using one, you must check whether the target is still alive and typically promote it via `NewLocalRef` and check for `NULL`. A weak global **does not** become a local ref usable across threads.

### 8.2. No Global Ref Needed If the Object Can Be Passed Back from Java

If Java already holds the object in a variable, field, or thread-safe structure, the simpler approach is often to **pass the object again as an argument** in the next native call. The JVM will issue a **new valid local JNI reference** for that invocation.

~~~text
Java holds the object in a field
   -> native call 1: local JNI ref #1 (expires on return)
   -> native call 2: local JNI ref #2 (new, same Java object)
~~~

This design often avoids having native code manage long-lived global refs. Only when native code needs to use the object asynchronously, after the Java call has returned, is a global ref (or equivalent ownership mechanism) truly necessary.

## 9. Common Local Reference Pitfalls

### 9.1. Storing a Local Ref in a Static C Variable for Later Use

~~~c
/* WRONG: the local reference will become invalid after the native return. */
static jobject cached = NULL;

void unsafeStore(jobject local) {
    cached = local;
}
~~~

Assigning a `jobject` value to a static variable **does not create a global reference**. After the native invocation finishes, `cached` is just a copy of an old JNI handle with no valid access to the object. It can cause JNI errors, crashes, or undefined behavior. The right way is to create `NewGlobalRef` while the local is still valid and have a clear global cleanup rule.

### 9.2. Copying a Local Handle by Assignment and Then Deleting One Alias

~~~c
/* WRONG if you continue using alias after DeleteLocalRef. */
jobject alias = local;
(*env)->DeleteLocalRef(env, local);
/* alias is also just a copy of the handle that was just destroyed. */
~~~

**C variable assignment does not create a new JNI reference**. If you need two independent local handles pointing to the same object, use `NewLocalRef(env, local)` to create a new handle; then `IsSameObject` can determine that the two handles reference the same Java object.

### 9.3. Using a Local `jclass` Across Invocations or Threads

~~~c
/* WRONG: storing a local jclass returned by FindClass in a static variable. */
static jclass cachedClass;
cachedClass = (*env)->FindClass(env, "java/lang/String");
~~~

`jclass` is a **JNI object reference**; it follows the same local/global rules. If you want to cache a `Class` long-term, you need a global `jclass` and a release rule; note that global refs can keep classes/class loaders alive longer than expected, especially in plugin systems or hot-reload deployments.

### 9.4. Confusing "Local in JNI" with "Local to a Java Method"

A Java variable `String name` in a Java method exists according to Java/JVM reference and optimization rules. A JNI local reference is **a handle in the native thread's JNI frame**. Both variables may point to the same object, but deleting the local JNI reference **does not** null out the Java variable and does not "free" the Object on native code's whim.

### 9.5. Treating `jobject` Like a C Pointer

`jobject` is an opaque reference; do not `free(jobject)`, do not `delete jobject`, do not read fields by `struct` offset, and do not perform pointer arithmetic. Use `GetObjectClass`, `GetFieldID`, `GetObjectField`, `CallObjectMethod`, `IsSameObject`, or the appropriate JNI API. If a native pointer is stored in a Java `long` field, that is **a separate native handle**, not a local JNI reference; its ownership and safety must be designed separately.

### 9.6. Comparing Two Handles with Pointer Operators

Two JNI references with different handles can still point to the same Java object. Do not use `a == b` to determine **object identity**; use `IsSameObject(env, a, b)` for valid references. Do not use `GetObjectRefType`/`IsSameObject` to "check" a handle that has already had `DeleteLocalRef` called or has expired; calling JNI with an invalid reference is already an error.

### 9.7. Letting the JVM Clean Up Everything at the End of the Method

A native method handling a few short-lived refs can rely on cleanup upon return. However, if you call `GetObjectArrayElement` millions of times, failing to delete local refs on each iteration can increase the number of handles kept alive in the same native frame. Use `DeleteLocalRef` as soon as you are done, or `PushLocalFrame`/`PopLocalFrame` for each batch.

### 9.8. Encountering an Exception and Continuing to Create References

Some JNI calls can create a pending Java exception. When you encounter an error result, stop the normal processing path and use only the set of APIs permitted while an exception is pending to inspect/clean up/propagate. Do not continue dereferencing error data or arbitrarily calling a series of JNI operations. `ExceptionCheck` helps detect exceptions; `DeleteLocalRef` and `PopLocalFrame` support cleanup per contract. **Do not clear a Java exception and arbitrarily return a success status.**

## 10. Local References and the Garbage Collector (GC)

In JNI, local references are ordinarily **strong references** for their valid lifetime: the JVM must account for the fact that native code may still use them. This can extend the lifetime of a Java object during a native call or on an attached native thread whose local handles have not been deleted.

Example:

~~~text
Java object O
  ^
  |   Local ref L1 (thread T1, native frame F1)
  |   Local ref L2 (thread T1, native frame F1)
  |
  +-- While both L1 and L2 are valid, the JVM knows native code may use O.
  +-- DeleteLocalRef(L1): O is still held by L2.
  +-- DeleteLocalRef(L2): if no other strong roots remain,
      O becomes eligible to be reclaimed by the GC.
~~~

**"Eligible to be reclaimed" does not mean "immediately reclaimed by the GC"**. The JVM decides when to run GC and may keep the object because of other strong references.

Differences between handle types:

| Property | Local reference | Global reference | Weak global reference |
| --- | --- | --- | --- |
| Is the object strongly held? | Ordinarily yes, within the valid local scope | Yes, until the global ref is deleted | Does not keep the object alive on its own |
| Can it be used directly on another thread? | **No** | Yes, with the attached thread's `JNIEnv*` | Requires weak semantics handling, typically promoted via a local ref |
| When does it become invalid? | Upon `DeleteLocalRef`, frame pop, or native invocation end; attached native threads have an exception until detach | `DeleteGlobalRef` | `DeleteWeakGlobalRef`, or the target may be cleared by the GC |
| Risk when forgotten | Handle accumulation in loops/long-running native threads | Unnecessarily keeping objects and class loaders alive | Native bookkeeping leaks; target may already have been cleared by GC |

JNI references are only one part of memory management: buffers from `GetStringUTFChars` or `GetIntArrayElements` have **different release rules**; `malloc` and direct native memory have **different ownership**. Do not substitute these release APIs for one another.

## 11. Design Checklist for the Two Boundaries: Call and Thread

When a native method creates or receives a Java object reference, ask these questions:

1. **Which JNI function created the reference?** Is it a new local `jobject` returned by `GetObjectClass`/`FindClass`/`NewObject`/`GetObjectArrayElement`?
2. **Who is the final consumer of the reference?** The current native call, the Java caller, a synchronous callback, or a thread/queue that will run later?
3. **Does the thread change?** If the object must be passed to another thread, do not pass the local handle directly; design a global ref or pass the object back through Java.
4. **Does the call end before the object is used again?** If so, there must be an appropriate long-lived reference, or Java must own it and pass it again.
5. **Are refs created in a long loop?** Use `DeleteLocalRef` or local frames to reduce pressure.
6. **Is a native thread self-attaching?** It needs its own `JNIEnv*`; clean up local refs explicitly rather than waiting for a long-running thread to detach.
7. **Are exceptions and cleanup handled thoroughly?** Error paths must also release handles and buffers that the code validly acquired.
8. **Are you cleaning up a handle or memory?** `DeleteLocalRef` does not release a Java object with `free` or a native buffer.
9. **Is ownership documented?** If creating a global ref, who calls `DeleteGlobalRef`, at what point, and how is double-delete avoided across multiple threads?
10. **Has it been checked with tooling?** On HotSpot you can run with `-Xcheck:jni` to catch certain JNI bugs, combined with multi-call and multithreaded tests.

When investigating real bugs, log by **thread, native method name, and when references are created/deleted** at an appropriate level, but **do not** log or expose handle values as if they were fixed Java object addresses.

## 12. Before-and-After Comparison Scenario

Suppose a native method processes 100,000 strings in a Java array.

**Before:**

~~~c
/* Illustration: accumulating local refs in every loop iteration. */
for (jsize i = 0; i < count; i++) {
    jobject s = (*env)->GetObjectArrayElement(env, array, i);
    if (s != NULL) {
        /* Process s without cleaning up the local ref. */
    }
}
/* Only when the native method returns does the JVM clean up. */
~~~

Problem: each `GetObjectArrayElement` can create a local ref held until the end of the native method. 100,000 iterations can create a large number of unnecessary handles.

**After:**

~~~c
/* Illustration: deleting the local ref after finishing each element. */
for (jsize i = 0; i < count; i++) {
    jobject s = (*env)->GetObjectArrayElement(env, array, i);
    if ((*env)->ExceptionCheck(env)) {
        return; /* Assumes a void function. */
    }
    if (s != NULL) {
        /* Process s while s is still valid. */
        (*env)->DeleteLocalRef(env, s);
    }
}
~~~

Benefit: fewer simultaneously live JNI local handles; no need to wait until the native method ends. This illustrative snippet **is not a complete function** and does not handle all `NULL` input cases, `count` bounds, or errors in the processing logic. Do not interpret it as an optimal recipe for every workload.

If each step creates multiple nested local refs or requires calling multiple JNI APIs in succession, consider `PushLocalFrame`/`PopLocalFrame` per batch. The key remains: **a local ref may only be used on a valid thread and frame**.

## 13. Self-Check Questions

1. A Java thread calls a native method twice. Can you keep the raw local `jobject` created during the first call to use in the second call? Why?
2. In a native method, a loop calls `GetObjectArrayElement` 50,000 times. Why should you not rely solely on cleanup when the method returns?
3. Why does `jobject copy = original;` not create two independent JNI references?
4. Does `DeleteLocalRef` immediately destroy the Java object on the heap?
5. Java creates two threads, each calling the same native method. Can you pass the `JNIEnv*` or a local `jobject` from the first thread to the second thread?
6. A native thread is created by C/C++ and then calls `AttachCurrentThread`. When a C helper function on this thread returns, are all local refs automatically cleaned up by the JVM right away?
7. A native method wants to return a `jstring` just created with `NewStringUTF` to Java. Is it mandatory to convert it to a global ref before returning?
8. How does `PopLocalFrame(env, result)` differ from `DeleteLocalRef(env, result)`?
9. When you genuinely need to keep a Java object across multiple JNI calls and share it with another thread, which reference type should you use and which API reclaims it?
10. A global ref keeps an object alive, but the object contains mutable state. Does the global ref guarantee the object is thread-safe?

**Suggested answers:** (1) No, the local ref expires when the first invocation ends; (2) local handles accumulate in the frame; (3) assignment only copies the handle—to get a new ref, use `NewLocalRef`; (4) no, it only deletes the handle and may change reachability; (5) no, both are bound to the thread; (6) no, an attached native thread requires explicit cleanup/frames or waiting until detach; (7) no, a valid local JNI result can be returned to the JVM; (8) pop cleans up the entire child frame and can create one result in the parent frame, whereas delete removes a single handle; (9) `NewGlobalRef` followed by `DeleteGlobalRef` when done, with synchronization; (10) no, it must still follow the Java memory model/synchronization.

## 14. Official References

- [Java SE 17 JNI Specification — Design Overview, Global and Local References](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html)
- [Java SE 17 JNI Specification — JNI Functions: Local References](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
- [Java SE 17 JNI Specification — Invocation API (`AttachCurrentThread`, `DetachCurrentThread`)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html)
- [Java SE 17 JNI Specification — JNI Types and Data Structures](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html)

**Key takeaway:** A local JNI reference is valid for the **thread that created it** and the **frame/invocation that owns it**. The JVM automatically cleans up a native method's local refs when the method returns, but long loops need early cleanup; self-attaching native threads must manage local refs until detach. To keep a Java object across calls or threads, use a proper ownership design, typically a **global reference** with `NewGlobalRef`/`DeleteGlobalRef`, or have Java hold the object and pass it again when needed.
