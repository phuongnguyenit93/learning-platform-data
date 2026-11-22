# Releasing Local References in Loops and Long-Running Calls (JNI)

When native code calls Java through the Java Native Interface (JNI), each reference to a Java object created by JNI functions is usually a **local reference**. The JVM manages these references as roots that can keep Java objects alive during GC. In a short native method, most local references are cleaned up automatically when the function returns. However, if a native function loops tens of thousands of times, processes a large batch, or runs for a very long time before returning, waiting until the end of the call to clean up can fill the local reference table, keep unnecessary objects alive for too long, and consume memory.

The two central operations are **`DeleteLocalRef`** (deleting a specific local reference) and the **`PushLocalFrame` / `PopLocalFrame`** pair (managing a group of local references by scope). They serve a different purpose from C's `free()` or `ReleaseStringUTFChars`: deleting a JNI reference **is not directly equivalent to freeing the Java object or a native buffer**.

This lesson belongs to the **References and GC** group in Java Advance — native-interoperability, focusing on mechanisms, API selection, error handling, and proper practices with Java 17+ and C11.

## 1. What is a local reference and how long does it exist?

A JNI reference is an **opaque handle** that allows the JVM to locate a Java object even when GC may move that object. Do not interpret `jobject`, `jclass`, `jstring`, or `jarray` as C pointers pointing directly to the Java object structure.

Common sources of local references:

- Objects and classes passed into a native method, for example `jobject self`, `jclass clazz`, `jstring name`, `jobjectArray items`.
- Results returned from `GetObjectArrayElement`, `GetObjectClass`, `FindClass`, `NewStringUTF`, `NewObject`, `CallObjectMethod`, `NewLocalRef`.
- A local reference created inside a nested local frame by `PushLocalFrame`.

Not every JNI result is a local reference. `jint`, `jlong`, and `jboolean` are just primitive values; `jmethodID`/`jfieldID` are opaque IDs, not `jobject`; pointers returned from `GetStringUTFChars` or `GetByteArrayElements` require their own separate release functions.

### 1.1. Default lifecycle

For a **native method called from Java**, the JVM automatically creates a local reference scope for that invocation. Local references belonging to the invocation remain valid in the current thread until explicitly deleted or until the native method returns to Java. Returning a valid local `jstring` to Java is a scenario supported by JNI; there is no need to convert it to a global reference to return the result.

In a loop inside the same native method, **completing one iteration does not automatically clean up local references**. What cleans up per call is when the native method **returns**, not when a C variable leaves lexical scope or when the loop moves to the next iteration.

For a **native thread that attaches itself** to the JVM via `AttachCurrentThread`, having a `JNIEnv *` does not create an automatic cleanup point for each C loop. Local references generated in a thread attached via the Invocation API may remain until `DetachCurrentThread` if not deleted or managed with local frames. Long-lived threads therefore need explicit cleanup even more.

### 1.2. References hold a GC root, but do not own the object like a C pointer

A valid local reference is a strong reference path considered by the JVM during GC. `DeleteLocalRef(env, ref)` removes **that JNI reference path**. It **does not immediately call a destructor**, does not guarantee the object is GC'd immediately, and does not remove other strong references from the Java stack, fields, arrays, or global JNI references.

For example: when `GetObjectArrayElement` reads an element of a `String[]`, deleting the local reference to the element **does not make the element disappear from the array**. The array still holds the object; the direct effect of `DeleteLocalRef` here is to reclaim a **JNI slot/handle** and avoid accumulating local roots created by native code.

Conversely, if JNI `NewStringUTF` creates a temporary String and no other Java/global references remain, deleting the local reference early can make the String eligible for GC, depending on the remaining roots.

## 2. Why do native loops easily accumulate local references?

Consider the following JNI C code (illustrating the bug only, not a standalone program):

```c
jsize n = (*env)->GetArrayLength(env, values);

for (jsize i = 0; i < n; ++i) {
    jstring s = (jstring)(*env)->GetObjectArrayElement(env, values, i);
    if (s != NULL) {
        /* Process s. */
    }
    /* Missing DeleteLocalRef(env, s). */
}
```

Each time `GetObjectArrayElement` returns a non-`NULL` object, it creates a local reference. Reassigning `s` in the next iteration **does not release the old reference**. A native method processing 100,000 elements can create a large number of simultaneously live local references, even though at any given moment the C program only needs one element.

JNI guarantees a minimum reserve of **16 local reference slots** upon entering a native method. This **is not a hard limit on the total number of refs**: the VM may allocate more; when exceeding the limit, you may see warnings or out-of-memory errors, or even fatal errors when no more slots can be allocated. Do not rely on a specific JVM's ability to automatically expand the table.

Fix at the iteration level:

```c
jsize n = (*env)->GetArrayLength(env, values);

for (jsize i = 0; i < n; ++i) {
    jobject element = (*env)->GetObjectArrayElement(env, values, i);
    if ((*env)->ExceptionCheck(env)) {
        return; /* void return type in this illustrative code. */
    }

    if (element != NULL) {
        /* Process element while the reference is still alive. */
        (*env)->DeleteLocalRef(env, element);
    }
}
```

This pattern keeps the number of temporary local references created by the loop nearly **O(1)** instead of growing with the number of elements **O(n)**. It does not automatically delete local references created and forgotten by helper functions, so if you call `FindClass`, `GetObjectClass`, `NewStringUTF`, or methods returning objects inside the loop, those refs must also be cleaned up.

## 3. Using `DeleteLocalRef` properly

JNI prototype on the C side:

```c
void DeleteLocalRef(JNIEnv *env, jobject localRef);
```

Rules:

1. Delete a local reference **after its last use**, before allocating subsequent local refs in a large loop.
2. `DeleteLocalRef(env, NULL)` is a no-op according to JNI, so using it on cleanup paths that may have `NULL` is valid.
3. After deletion, the C variable still holds the old bits/handle. **Do not call any other JNI function with that reference again**; if you want to reduce the risk of accidental reuse, assign the local variable to `NULL`.
4. If two separate local references `a` and `b` point to the same Java object (for example creating `b = NewLocalRef(env, a)`), deleting `a` **does not automatically invalidate `b`**. Manage each handle individually; do not use Java object identity to decide "already deleted".
5. Only use `DeleteLocalRef` with **local** references. Global references must go with `DeleteGlobalRef`; weak global references must go with `DeleteWeakGlobalRef`.
6. Do not delete a local reference and then return that deleted handle as the native method's result. If you need to return to Java, keep a valid reference or use `PopLocalFrame(env, result)` to transfer the result across frames.
7. Object parameters passed from Java into JNI are also local references, but normally you let the JVM clean them up automatically at the end of the call; only delete them explicitly when you are certain that parameter will not be used further.
8. Local references are only valid in the **thread that created them**. Do not pass a local `jobject` to a pthread or store it in a global C variable to use after the native method finishes.

An important point regarding GC: deleting `ref` does not guarantee the object is collected immediately, because Java or JNI may still hold other references. Conversely, simply assigning `ref = NULL` in C does not guarantee the JNI slot is reclaimed; you must call `DeleteLocalRef` or pop the frame.

## 4. Complete Java 17 + C11 example: processing 100,000 elements

The example uses two native methods to clearly show two management approaches:

- `nativeCountNonEmpty` iterates over the **entire** array, creating a local reference for each non-`null` String, calling `DeleteLocalRef` in each iteration.
- `nativeFirstNonEmpty` uses `PushLocalFrame` to open a child reference scope; when it encounters the String to return to Java, it calls `PopLocalFrame(env, result)` keeping **one** valid result reference in the parent frame.

Empty strings (`""`) are skipped; `null` is also skipped. The length uses `GetStringLength` (in **UTF-16 code units**), which is sufficient to check for emptiness without converting to UTF-8.

### 4.1. Java: `LocalRefLifecycle.java`

```java
import java.util.Objects;

public final class LocalRefLifecycle {
    static {
        System.loadLibrary("localrefs");
    }

    private static native int nativeCountNonEmpty(String[] values);
    private static native String nativeFirstNonEmpty(String[] values);

    public static int countNonEmpty(String[] values) {
        Objects.requireNonNull(values, "values");
        return nativeCountNonEmpty(values);
    }

    public static String firstNonEmpty(String[] values) {
        Objects.requireNonNull(values, "values");
        return nativeFirstNonEmpty(values);
    }

    public static void main(String[] args) {
        String[] values = new String[100_000];

        for (int i = 0; i < values.length; ++i) {
            values[i] = (i % 10 == 0) ? "hit" : "";
        }
        values[1] = null;

        System.out.println("nonEmpty=" + countNonEmpty(values));
        System.out.println("first=" + firstNonEmpty(values));
    }
}
```

Because indices `0, 10, 20, ... 99990` have the value `"hit"`, there are exactly **10,000 non-empty elements**. Index `1` was originally an empty string; changing it to `null` does not change the count. At index `0`, the second function immediately finds `"hit"`.

### 4.2. Generating the JNI header

In the directory containing `LocalRefLifecycle.java`:

```bash
javac -h . LocalRefLifecycle.java
```

The command generates `LocalRefLifecycle.class` and `LocalRefLifecycle.h`. The C file needs to include this exact header. The generated native signatures look like:

```c
JNIEXPORT jint JNICALL
Java_LocalRefLifecycle_nativeCountNonEmpty(
    JNIEnv *, jclass, jobjectArray);

JNIEXPORT jstring JNICALL
Java_LocalRefLifecycle_nativeFirstNonEmpty(
    JNIEnv *, jclass, jobjectArray);
```

This is a **prototype illustration** snippet; do not create the header file manually instead of `javac -h` when renaming classes/packages or overloading. For `static` native methods, the second parameter is `jclass`; for instance methods, it is `jobject`.

### 4.3. C: `LocalRefLifecycle.c`

```c
#include "LocalRefLifecycle.h"

static void throw_null_array(JNIEnv *env) {
    jclass cls = (*env)->FindClass(
        env, "java/lang/NullPointerException");

    if (cls == NULL) {
        /* FindClass failed; let the pending exception propagate to Java. */
        return;
    }

    (*env)->ThrowNew(env, cls, "values must not be null");
    (*env)->DeleteLocalRef(env, cls);
}

/*
 * Approach 1: DeleteLocalRef on each element.
 * Each element only needs to stay alive for exactly one iteration.
 */
JNIEXPORT jint JNICALL
Java_LocalRefLifecycle_nativeCountNonEmpty(
    JNIEnv *env, jclass clazz, jobjectArray values) {

    (void)clazz;

    if (values == NULL) {
        throw_null_array(env);
        return 0;
    }

    jsize length = (*env)->GetArrayLength(env, values);
    jint count = 0;

    for (jsize i = 0; i < length; ++i) {
        jstring item = (jstring)
            (*env)->GetObjectArrayElement(env, values, i);

        if ((*env)->ExceptionCheck(env)) {
            /* Keep the JNI exception; Java will receive the exception. */
            return 0;
        }

        if (item != NULL) {
            jsize utf16_units = (*env)->GetStringLength(env, item);

            /*
             * While an exception is pending, DeleteLocalRef is
             * one of the cleanup operations still allowed to be called.
             */
            if ((*env)->ExceptionCheck(env)) {
                (*env)->DeleteLocalRef(env, item);
                return 0;
            }

            if (utf16_units > 0) {
                ++count;
            }

            (*env)->DeleteLocalRef(env, item);
            item = NULL;
        }
    }

    return count;
}

/*
 * Approach 2: PushLocalFrame/PopLocalFrame.
 * Preserve exactly one result jstring across the frame boundary.
 */
JNIEXPORT jstring JNICALL
Java_LocalRefLifecycle_nativeFirstNonEmpty(
    JNIEnv *env, jclass clazz, jobjectArray values) {

    (void)clazz;

    if (values == NULL) {
        throw_null_array(env);
        return NULL;
    }

    if ((*env)->PushLocalFrame(env, 8) != JNI_OK) {
        /* JNI leaves a corresponding exception if the frame cannot be opened. */
        return NULL;
    }

    jsize length = (*env)->GetArrayLength(env, values);

    for (jsize i = 0; i < length; ++i) {
        jstring item = (jstring)
            (*env)->GetObjectArrayElement(env, values, i);

        if ((*env)->ExceptionCheck(env)) {
            (*env)->PopLocalFrame(env, NULL);
            return NULL;
        }

        if (item == NULL) {
            continue;
        }

        jsize utf16_units = (*env)->GetStringLength(env, item);

        if ((*env)->ExceptionCheck(env)) {
            (*env)->PopLocalFrame(env, NULL);
            return NULL;
        }

        if (utf16_units > 0) {
            /*
             * Pop deletes all local refs belonging to this frame,
             * while creating an equivalent ref in the parent frame.
             */
            return (jstring)(*env)->PopLocalFrame(env, item);
        }

        (*env)->DeleteLocalRef(env, item);
        item = NULL;
    }

    return (jstring)(*env)->PopLocalFrame(env, NULL);
}
```

In the counting method, `GetObjectArrayElement` creates a new local reference for each non-`null` element. All of them are deleted early, so even with 100,000 iterations, the number of simultaneously existing temporary JNI references does not grow linearly with the number of elements. The `values` array held by Java throughout the call can still keep the Strings alive; the direct goal is **not to fill up the JNI references table**.

In the element-finding method, `PushLocalFrame(env, 8)` creates a child scope with a minimum capacity of 8 references. `PopLocalFrame(env, item)` destroys the local references belonging to the child frame **while keeping the object pointed to by `item` as a new local reference in the parent frame**, so that Java receives a valid result. If not found, `PopLocalFrame(env, NULL)` simply cleans up the frame and returns `null`.

Note: the code intentionally cleans up even empty items inside the frame although `PopLocalFrame` will eventually clean them up as well. As a result, if there are a million empty elements before the result, the number of simultaneous local references is still kept under control. **A frame created outside a loop without deleting refs inside the loop does not automatically turn into a per-iteration cleanup mechanism.**

Passing `JNIEnv *` and calling via `(*env)->...` is the JNI syntax for C. In C++, `env->...` is commonly used. The exported function names on the C side match a Java class in the default package; a real application with a package must use the header generated for that package.

### 4.4. Compiling and running on Linux

Prepare JDK 17+ and a C11 compiler; `JAVA_HOME` must point to the JDK directory containing `include/jni.h`. Run in the directory containing both source files:

```bash
javac -h . LocalRefLifecycle.java

cc -std=c11 -Wall -Wextra -Wpedantic -fPIC -shared \
   -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
   LocalRefLifecycle.c -o liblocalrefs.so

java -Djava.library.path=. LocalRefLifecycle
```

**Exact stdout** when run successfully:

```text
nonEmpty=10000
first=hit
```

The name `System.loadLibrary("localrefs")` is mapped by the JVM to `liblocalrefs.so` on Linux. On macOS/Windows, the JNI header paths, compiler flags, and shared library names differ; do not copy the `-I.../linux` flag verbatim to those platforms. If you change the package/native method names, re-run `javac -h` and rebuild the library.

The code uses standard Java 17 APIs, without relying on exceptional JNI features or the internal `Unsafe` API; the C library must match the architecture and ABI of the running JVM.

## 5. How do `PushLocalFrame`, `PopLocalFrame`, and `EnsureLocalCapacity` differ?

| API | Effect | Does it delete created local references? | When to use |
| --- | --- | --- | --- |
| `DeleteLocalRef(env, ref)` | Deletes **one** specific local reference | **Yes**, that ref | Each iteration only needs a few refs |
| `PushLocalFrame(env, n)` | Opens a nested scope, ensuring space for at least `n` new local refs | **Not yet** | A task creates multiple related refs that need group cleanup |
| `PopLocalFrame(env, result)` | Cleans up the current local frame, optionally preserving **one** result in the parent frame | **Yes**, all local refs belonging to the child frame | End of a task/iteration/batch or returning one ref outward |
| `EnsureLocalCapacity(env, n)` | Ensures space for `n` additional local refs on the current thread | **No** | When you need to proactively reserve a number of new refs without creating a frame |
| `NewLocalRef(env, ref)` | Creates **another local reference** pointing to the same object | **No**; even creates an additional ref | Creating a ref in the current scope from a valid ref |

`PushLocalFrame` takes a capacity **greater than 0**. If the frame cannot be opened, the function returns a negative code; in typical allocation failure situations, JNI reports the corresponding error (for example `OutOfMemoryError`). Only call `PopLocalFrame` **after a successful push**; you must ensure every exit path from the pushed scope pops accordingly.

`EnsureLocalCapacity` does not guarantee garbage collection and does not reclaim held references. Calling `EnsureLocalCapacity(env, 1000)` before a one-million-iteration loop **does not replace** deleting refs. Nor does a small local frame "auto-reset" after each iteration if the frame lives outside the loop.

### 5.1. Choosing batch-based frames, avoiding forgotten cleanup on error branches

When an iteration performs multiple JNI calls (creating Strings, getting classes, calling factories returning objects, reading properties), using a per-iteration or per-batch frame helps reduce the risk of leaking refs:

```c
/*
 * Illustrates structure inside a native method, not a standalone
 * translation unit: env/values/work() are assumed to be
 * prepared by the caller and defined separately.
 */
for (jsize i = 0; i < length; ++i) {
    if ((*env)->PushLocalFrame(env, 16) != JNI_OK) {
        return;
    }

    /* work(env, i) is allowed to create local refs in this frame. */
    work(env, i);

    if ((*env)->ExceptionCheck(env)) {
        (*env)->PopLocalFrame(env, NULL);
        return;
    }

    (*env)->PopLocalFrame(env, NULL);
}
```

This pattern shows that each iteration has its own cleanup point. The push/pop overhead may be unnecessary if each iteration creates exactly one ref and it is easy to call `DeleteLocalRef`. Prioritize clarity and benchmark before optimizing.

### 5.2. Keeping a result reference when popping

If an object created in a child frame needs to survive after popping:

```c
jobject result = /* ref created in the child frame */;

/* Transfer the object to the parent frame and clean up the remaining refs. */
jobject survivor = (*env)->PopLocalFrame(env, result);

/* The old result is invalidated; only survivor can be used further. */
```

The snippet above is **illustrative code**, only valid after a corresponding `PushLocalFrame` has succeeded; do not assign `survivor = result` and then pop, because the old handle belongs to the destroyed frame. Only pass a result permitted by the JNI contract; if `survivor == NULL` when you expect an object, check for the appropriate error/exception.

## 6. Long-running calls: "the end of the native method" can be very far away

Imagine JNI processing millions of rows in a single call, with each row calling `NewStringUTF` to create a temporary String. If local refs are not deleted for each row, every String referenced from JNI can remain alive until the method finishes, even though intermediate results were discarded long ago.

The same bug can appear outside loops:

- **Multi-phase pipelines:** the first phase creates a batch of objects for processing, the later phase only uses numeric results, yet all refs remain alive.
- **Java callbacks from C:** `CallObjectMethod` returns a new ref each time; if a loop calls the callback without cleaning up the result, refs accumulate. When the callback throws an exception, it must be handled/cleaned up before continuing JNI.
- **Blocked calls:** a native method holds a local reference to a very large object and then waits on I/O or a mutex for a long time; even though the code no longer uses the object, the ref can continue keeping the object alive.
- **Long-lived attached native worker threads:** there is no natural native-method-return for C logic running on an attached native thread, so refs can be held until detach.

Good design sets lifetime boundaries right at the **moment usage finishes**, without waiting until the end of the entire worker's lifecycle.

You should also consider **the time it takes for JNI functions to detect asynchronous exceptions**. The JNI Design Overview recommends inserting `ExceptionOccurred` checks in long-running native sections, especially tight loops that lack other JNI calls that could throw exceptions. Once a pending exception is detected, the code should clean up and return control to Java or have a clear handling strategy; do not arbitrarily continue calling other JNI functions.

## 7. Handling exceptions while still cleaning up references

JNI does not automatically jump back to Java when a JNI function throws an exception. It marks a **pending exception** on the thread and native C continues running until it returns or handles it itself. After a pending exception occurs, only a small set of JNI functions are allowed to be called before clearing the exception.

Among the allowed cleanup group are `DeleteLocalRef`, `PopLocalFrame`, `DeleteGlobalRef`, the `ReleaseStringChars` / `ReleaseStringUTFChars` / `Release<Type>ArrayElements` functions, `ExceptionCheck`, `ExceptionOccurred`, and `ExceptionClear`. Avoid calling `FindClass`, `CallObjectMethod`, `NewStringUTF`, or creating new objects while an exception is still pending.

A typical linear cleanup structure:

```c
/*
 * Illustration inside a native method with a jint return.
 * "value" is a newly created local reference, or NULL.
 */
jobject value = (*env)->GetObjectArrayElement(env, values, index);

if ((*env)->ExceptionCheck(env)) {
    return 0;       /* No usable ref from the failed call. */
}

/* ... process value ... */

if (value != NULL) {
    (*env)->DeleteLocalRef(env, value);
    value = NULL;
}

if ((*env)->ExceptionCheck(env)) {
    return 0;       /* Let the pending Java exception propagate to the caller. */
}
```

If an intermediate JNI operation can throw an exception, **clean up all acquired refs and resources**, then return while the exception is still pending. Avoid calling `ExceptionClear` just to "keep running" without knowing the state of the data or objects after the error; if you decide to recover, the cause and fallback behavior must be clear.

### 7.1. Do not confuse a local ref with a JNI-allocated C buffer

Example of getting the UTF-8 contents of a `jstring` (this is **illustrative code** inside a native method that already has a valid `env` and `s`):

```c
const char *bytes = (*env)->GetStringUTFChars(env, s, NULL);
if (bytes == NULL) {
    /* JNI may have reported an error: clean up s if we created it. */
    (*env)->DeleteLocalRef(env, s);
    return;
}

/* Use bytes only while s is still valid and not yet released. */

(*env)->ReleaseStringUTFChars(env, s, bytes);
(*env)->DeleteLocalRef(env, s);
```

There are **two separate obligations**:

1. `ReleaseStringUTFChars` frees/unpins the byte data that JNI returned corresponding to `GetStringUTFChars`.
2. `DeleteLocalRef` frees the local reference `s` if the code owns that temporary ref.

Calling only `DeleteLocalRef` **does not replace** `ReleaseStringUTFChars`; calling only `ReleaseStringUTFChars` **does not delete** the local ref. If `s` is a method parameter passed in by Java, you can let the JVM clean up the parameter's ref automatically at the end of the native call, but the UTF-8 buffer must still be released in a proper pair.

`GetStringUTFChars` uses JNI's **Modified UTF-8**, which is not completely identical to standard UTF-8 (especially for NUL and supplementary Unicode characters). If you are only checking for an empty string, `GetStringLength` is simpler and avoids requesting/releasing a native buffer.

## 8. Attached native threads: avoiding reference accumulation in long-lived processes

A self-created native thread (for example via pthread) does not have a valid `JNIEnv *` readily available. It must use `JavaVM *` and `AttachCurrentThread` to attach to the JVM. `JNIEnv *` is only for that specific thread; do not store and use it from another thread.

Conceptual structure:

```c
/*
 * Control-flow illustration, not a standalone program:
 * vm and a concrete workload loop are provided by the caller.
 */
JNIEnv *env = NULL;
if ((*vm)->AttachCurrentThread(vm, (void **)&env, NULL) != JNI_OK) {
    /* Handle attach failure on the native side. */
    return;
}

while (has_more_work()) {
    if ((*env)->PushLocalFrame(env, 16) != JNI_OK) {
        break;
    }

    /* Read/call Java, creating temporary local references. */
    process_one_batch(env);

    jboolean failed = (*env)->ExceptionCheck(env);
    (*env)->PopLocalFrame(env, NULL);

    if (failed) {
        /* Do not continue normal JNI calls while an exception is pending. */
        break;
    }
}

/* At a valid exit point: the thread detaches itself when done. */
(*vm)->DetachCurrentThread(vm);
```

This is a **code skeleton** and cannot be compiled standalone because `vm`, `has_more_work`, and `process_one_batch` are not defined. In a real application, you must also decide how exceptions occurring in the native thread will be reported back to Java, how shutdown/cancellation will be handled, and ensure the thread does not hold any locked Java monitors when detaching. `DetachCurrentThread` is not a "clean up per batch" strategy: a thread running for many hours must clean up refs right within each batch.

If native code needs to keep an object **after the native method finishes**, or needs to share it across attached threads, create a `global reference`:

```c
/* objectRef is a valid JNI reference in the current thread. */
jobject global = (*env)->NewGlobalRef(env, objectRef);
/* Check for NULL/exception and store global according to contract. */

/* When global is no longer needed, on a valid attached thread: */
(*env)->DeleteGlobalRef(env, global);
```

This is an **illustrative** snippet, not a standalone file. Global references must be released **explicitly**, otherwise they can keep an entire object graph alive indefinitely. `NewWeakGlobalRef` is an option when you want GC to be able to reclaim the object, but a weak ref can become `NULL` and must be checked by creating a strong local ref/checking validity per JNI; a weak global is not an automatic replacement for ownership.

## 9. Common mistakes and how to avoid them

| Wrong coding pattern or misconception | Consequence | Correct practice |
| --- | --- | --- |
| Creating a ref in a loop and only assigning `jobject x = NULL` | JNI slot/handle is still held until the invocation ends | `DeleteLocalRef` or pop the corresponding frame |
| "The JVM cleans up local refs automatically" so a one-million-element loop needs no cleanup | Local table may overflow before the native method returns | Delete refs per iteration/batch |
| `PushLocalFrame` once outside the loop without deleting refs | Frame does not auto-clean per iteration | Pop every iteration/batch, or delete individual refs |
| `EnsureLocalCapacity` and then skipping cleanup | Only reserves space, does not release | Distinguish reserve from release |
| `DeleteLocalRef(env, x)` then `return x` | Returns an invalidated handle | Keep the ref to return or `PopLocalFrame(env, x)` |
| `PopLocalFrame(env, NULL)` then using a ref from the old frame | Ref is invalidated upon pop | Create a survivor via `PopLocalFrame(env, result)` |
| Deleting a local ref and believing the Java object has been destroyed | Object may still have other strong refs | Understand GC reachability and ownership |
| Passing a local `jobject` to another thread | Violates thread scope of local references | Global ref when sharing is needed per contract |
| Storing a local `jclass` from `FindClass` in a `static` variable | Using a ref past its lifetime, may crash | `NewGlobalRef` then `DeleteGlobalRef` |
| Calling `FindClass`/`CallObjectMethod` while an exception is pending | Violates JNI rules | Clean up with allowed APIs then return or clear in a controlled manner |
| Deleting a local `jstring` instead of releasing the bytes pointer | Leaks or pins/copies JNI buffer | Pair `Get.../Release...` and ref cleanup properly |
| Calling `DeleteLocalRef` twice on the same handle | Misuse of deleted ref; invalid behavior | One lifetime per handle; set local to `NULL` after deletion |
| Applying `DeleteLocalRef` to a global reference | Wrong reference type | Use `DeleteGlobalRef` |
| Creating local refs in an attached worker throughout its runtime | No native method return to auto-clean per batch | Use frame/delete continuously, detach at thread end |

Beyond correctness, proper ref cleanup clarifies **lifetime**: which code needs the object, which only needs extracted primitive data, and which can let the JVM drop a GC root. However, do not aggressively force cleanup on refs that will be used later, because JNI has no mechanism to "recover" a deleted handle.

## 10. Verification and practical observation

Scenarios that should be included in JNI testing:

1. **Very long loops:** test arrays of 100,000, 500,000, or more elements as heap allows; the native function must return the exact count without increasing live local references per iteration.
2. **Null/empty:** `null` elements must not be passed to `GetStringLength`; empty string `""` has `GetStringLength == 0`.
3. **Exception path:** if `GetObjectArrayElement` or a callback method throws an exception, existing local refs must be cleaned up; do not continue with disallowed JNI calls while pending.
4. **Frame return:** `PopLocalFrame(env, result)` gives a usable result in the parent frame, while temporary refs in the same frame are not reused.
5. **Long-lived threads:** loop in batches on a native-attached thread, comparing ref counts, object lifetimes, and shutdown/detach behavior.
6. **GC behavior:** do not conclude `DeleteLocalRef` "does not work" just because an object has not been GC'd yet: there may still be references from the Java array, stack, global ref, or JVM.
7. **Resource classification:** count JNI local handles, JNI global refs, C heap allocations, and buffers from `GetStringUTFChars` separately; they have different release functions.

When running on a supported HotSpot/JDK, you can enable enhanced JNI checks:

```bash
java -Xcheck:jni -Djava.library.path=. LocalRefLifecycle
```

Depending on the JVM version, `-verbose:jni` may provide additional logs. On Android, CheckJNI helps detect some cases of using the wrong reference type, use-after-delete, and many other JNI violations. Do not rely on a single stress program with good results to prove there are no leaks: review the lifetime of every exit path.

How to reason about reference counts in a loop:

- Not deleting after `GetObjectArrayElement`: the number of *live* temporary refs can grow approximately with the number of processed elements.
- Deleting the ref before the next iteration: the temporary refs directly generated by this API are bounded around 0–1 at any given time.
- Using a per-batch frame: the number of temporarily live refs is bounded by the refs in the **current batch**; `PopLocalFrame` frees the whole group.
- If there are refs in the parent frame or global refs, cleaning up the child frame **does not** make them disappear.

## 11. Checklist when writing JNI

Before handing off a native method that traverses Java objects or performs long-running processing, answer these questions:

- Which **function** generates each temporary `jobject/jclass/jstring/jarray`, and up to what point is it still used?
- How long can the loop run, and what is the maximum number of **simultaneous** local references it creates?
- Use `DeleteLocalRef` per ref or open `PushLocalFrame` per iteration/batch? Can all success, exception, and early return paths clean up?
- After `PopLocalFrame`, which ref is kept via `result` and which refs have become invalid?
- Does the native method return early, wait on long I/O, or run on a long-lived attached native thread?
- Does the code distinguish local/global/weak global references from C pointers, JNI buffers, and `jlong` primitives?
- Are exceptions checked immediately after JNI calls that can fail before using their results, and is cleanup always done with allowed APIs?
- If keeping an object across calls/threads, is there an owner for `NewGlobalRef/DeleteGlobalRef` and a well-defined release point?

**Core rule:** local references automatically expire when a native method returns to Java, but **do not automatically expire at the end of each C loop**. Clean up references **as soon as they are no longer needed**, or group them in a frame with a clear pop point; this bounds the number of live handles, avoids holding extra GC roots, and makes code easier to control in long-running native calls.

### References

- [Oracle Java SE 17 — JNI Design Overview, Global and Local References](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html)
- [Oracle Java SE 17 — JNI Functions: DeleteLocalRef, EnsureLocalCapacity, PushLocalFrame, PopLocalFrame](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
- [Oracle Java SE 17 — Invocation API / AttachCurrentThread](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html)
- [Android Developers — JNI Tips: Local and Global References](https://developer.android.com/ndk/guides/jni-tips)
