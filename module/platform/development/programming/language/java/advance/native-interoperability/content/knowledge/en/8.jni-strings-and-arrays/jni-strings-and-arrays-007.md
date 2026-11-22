# Non-Blocking and No Arbitrary JNI Call Restrictions in Critical Regions

## 1. What Is a Critical Region in JNI?

When C/C++ code processes **primitive arrays** or **Java strings**, JNI provides APIs to obtain pointers for reading/writing data. Two special pairs of APIs are:

- `GetPrimitiveArrayCritical` / `ReleasePrimitiveArrayCritical`: accesses elements of primitive arrays such as `int[]`, `byte[]`, `double[]`.
- `GetStringCritical` / `ReleaseStringCritical`: accesses the **UTF-16 `jchar` code units** of a Java `String`.

The period **after successfully obtaining the pointer and before calling the corresponding Release function** is a **JNI critical region**. During this period, native code must do very little work: **no blocking, no arbitrary JNI calls, and do not hold the Critical region for long**.

Why are there strict restrictions? The JVM may return a **direct pointer into managed memory** and temporarily *pin* the object, or need to restrict garbage collector (GC) activity so the pointer is not invalidated. If a native thread holds a Critical region for too long, GC or other Java threads may be delayed. A thread holding a Critical region while waiting for work that requires the JVM to proceed can create a wait cycle (*deadlock*).

**No zero-copy guarantee:** The JVM **may copy** the data instead of pinning; the name `Critical` expresses a **strict usage contract**, not a guarantee that you will always receive a direct pointer to the Java heap.

Objectives after this lesson:

1. Identify when a Critical region begins/ends.
2. Know what operations are and are not allowed while holding a Critical pointer.
3. Arrange all JNI/IO/synchronization operations **before or after** the Critical region.
4. Write a **runnable Java 17+ and C11** example using both API pairs.
5. Distinguish `0`, `JNI_ABORT`, `JNI_COMMIT` when releasing arrays; handle `NULL`, `isCopy`, and exceptions.
6. Choose other APIs when IO, callbacks, locks, long processing, or chunked work are needed.

## 2. Signatures, Data Types, and Pointer Lifecycle

### 2.1. Primitive Arrays

In C code (from `jni.h`):

~~~c
void *GetPrimitiveArrayCritical(
        JNIEnv *env, jarray array, jboolean *isCopy);

void ReleasePrimitiveArrayCritical(
        JNIEnv *env, jarray array, void *carray, jint mode);
~~~

Used from a JNI function receiving `jintArray`:

~~~c
jint *ptr = (jint *)(*env)->GetPrimitiveArrayCritical(
        env, numbers, NULL);

/* If ptr != NULL: read/write quickly and briefly, no arbitrary JNI calls */

if (ptr != NULL) {
    (*env)->ReleasePrimitiveArrayCritical(
            env, numbers, ptr, JNI_ABORT);
}
~~~

This is an **abbreviated pattern**, not a standalone function. `GetPrimitiveArrayCritical` returns a `void *` pointer corresponding to the elements of a **primitive array**, or `NULL` on failure. It must be cast to `jint *`, `jbyte *`, `jdouble *`... according to the **actual element type**. Do not apply this API to a `jobjectArray` containing Java objects.

Information that must be obtained before calling Get:

- `array` must be a valid, **non-NULL** reference.
- The array size (`GetArrayLength`) must be obtained **before** entering the Critical region.
- Output buffers and required native state should be prepared beforehand.
- You can pass `jboolean *isCopy` to observe whether the JVM is providing a copy (`JNI_TRUE`) or a direct pointer (`JNI_FALSE`). This information **does not change the Release obligation or the Critical restrictions**.

### 2.2. Java Strings

~~~c
const jchar *GetStringCritical(
        JNIEnv *env, jstring string, jboolean *isCopy);

void ReleaseStringCritical(
        JNIEnv *env, jstring string, const jchar *carray);
~~~

`GetStringCritical` provides a sequence of **UTF-16 code units** of type `jchar`, not UTF-8 bytes and **with no guarantee that the string is NUL-terminated**. Use the length from `GetStringLength`, obtained **before** opening the Critical region.

For example, if Java passes `"A😀B"`, Java `String.length()` is **4 UTF-16 units** because the emoji occupies a surrogate pair. C code sees four `jchar`s; you must not infer that there are four Unicode code points. Java strings may contain `'\u0000'`, so do not use `wcslen` or search for NUL to compute the length.

Other APIs to distinguish:

| JNI API | Data received | Is it a Critical pair? |
| --- | --- | --- |
| `GetStringCritical` | `const jchar *`, UTF-16 code units | **Yes**, must `ReleaseStringCritical` |
| `GetStringChars` | `const jchar *`, UTF-16 code units | No, use `ReleaseStringChars` |
| `GetStringUTFChars` | `const char *`, **Modified UTF-8** | No, use `ReleaseStringUTFChars` |
| `GetStringRegion` | Copies a UTF-16 segment into a C-allocated buffer | No Java pointer needs to be held across a Get/Release pair |

Do not mix up Release APIs, do not free JNI pointers with `free`, and **do not use them after Release**.

## 3. Core Rule: Critical Region Restrictions

According to the JNI Specification, while holding a pointer from `GetPrimitiveArrayCritical`, native code **must not arbitrarily call other JNI functions** and **must not make system calls that may block the current thread waiting for another Java thread**. For `GetStringCritical`, similar restrictions apply: **no arbitrary JNI calls, do not cause the thread to block**. Treat both Critical regions as **short CPU segments with bounded execution time**.

| Operation | Inside Critical region? | Reason / proper approach |
| --- | --- | --- |
| Reading a few elements, adding numbers, checking `jchar`, short `memcpy` into a ready buffer | Usually **allowed**, if non-blocking and finishes very quickly | Only processes raw data, does not touch the JVM |
| `GetArrayLength`, `GetStringLength` | **No** | Obtain the length before Get Critical |
| `FindClass`, `NewStringUTF`, `GetObjectClass`, `GetMethodID` | **No** | May involve JVM/GC/class loading; perform after Release |
| `CallObjectMethod`, `CallVoidMethod`, or calling back into Java | **No** | Java callbacks can allocate, block, acquire locks, or trigger GC |
| `ExceptionCheck`, `ThrowNew`, `NewGlobalRef`, `DeleteLocalRef` | **Do not call inside Critical** | Handle errors/references before Get or after Release |
| `Thread.sleep` via Java callback, `sleep`, potentially blocking `read`/`recv`, `accept`, waiting on network/disk | **No** | Thread may sleep/wait when GC needs to complete |
| `pthread_mutex_lock`, `WaitForSingleObject`, `condition_variable::wait` | **No** if it can wait | Acquire/release locks outside; avoid locking inside |
| `printf`/synchronous logging, file writes, sending telemetry, RPC | **Should not** | IO and logging can block, acquire mutexes, or allocate |
| Allocating via `malloc`/`new`, calling C/C++ libraries with unknown behavior | **Avoid** | Allocator/runtime/library may acquire locks and cause waiting |
| Corresponding `ReleasePrimitiveArrayCritical`/`ReleaseStringCritical` | **Required** | Close the Critical region before any JNI/callback/IO |
| Two nested Critical Get/Release pairs | Spec **allows** in some cases | Still must release properly and keep all regions short; do not nest if a simpler solution exists |

The term "non-blocking" does not mean "stop using `synchronized` in Java". It means **native code holding a Critical pointer must not initiate operations that may wait**. Avoid even calls that look lightweight but can actually transition into the JVM, trigger class loading, lock contention, or IO.

### 3.1. Why Is Even a "Small JNI Call" Unsafe?

Suppose after Get Critical, native code calls `GetArrayLength`. This function looks simple, but **the specification does not allow assuming any arbitrary JNI API is safe inside Critical**. Every JNI transition may require special runtime state; GC may need threads to reach a *safepoint*. When a thread holds a pin/critical guard and then uses another JNI call, the JVM may have to wait for a condition that the very same thread is delaying.

Therefore, a more effective review rule than guessing "does this call allocate?" is:

> **After a successful Get Critical, perform only brief C/C++ computation on pre-prepared data, then immediately Release.**

The specification mentions **nesting Critical Get/Release pairs** in certain situations, but this is not a license to make arbitrary JNI calls; each pair must still be fully managed and the restrictions remain in effect until the final Release.

### 3.2. GC and Safepoints: System-Wide Impact

Depending on the JVM and data structures, Get Critical may:

- Pin the array or prevent moving the memory region containing the array.
- Use a temporary copy; in that case Release is still required for the JVM to fulfill the copy/memory contract.
- Make GC/safepoints harder to progress or force waiting in some implementations/collectors.

It is impossible to promise "Get Critical is always faster than `GetIntArrayRegion`" or "GC will always stop completely when Critical is active". **Strategies vary across JVMs/collectors and versions.** Precisely because of this implementation-dependent risk, native code must obey the restrictions even when `isCopy == JNI_TRUE`.

## 4. Safe Workflow: Prepare → Get → Compute → Release → Continue

~~~text
Java calls native method
         |
         v
[BEFORE CRITICAL]
- Check null parameters / size / bounds
- GetArrayLength or GetStringLength
- Allocate needed C memory and handle JNI exceptions
- Prepare callbacks, classes, method IDs, locks if needed
         |
         v
GetPrimitiveArrayCritical / GetStringCritical
         |
       ptr == NULL ? ---> [Outside Critical] check exception, report error
         |
         v
[INSIDE CRITICAL]
- Short loop, non-blocking
- Only read/write primitive data or jchar
- No other JNI calls, no IO, no Java callbacks
         |
         v
ReleasePrimitiveArrayCritical / ReleaseStringCritical
         |
         v
[AFTER CRITICAL]
- Check/report exceptions, logging, call Java
- Write results, handle IO, return value to JVM
~~~

Once Get succeeds, **every exit path must go through Release**. Avoid `return`, `goto`, `break`, C++ exceptions, or long jumps that skip Release. If processing can fail, store the result/error in a C variable and Release before moving to JNI error handling.

You should structure the code into three clearly bounded parts: **preparation**, **critical section**, **post-processing**. Helper function names do not guarantee safety; inspect what those helpers call internally as well.

## 5. Complete Example: Java 17+ and C11

The example has two methods:

- `sum(int[])` sums five integers using `GetPrimitiveArrayCritical`, **reading only** the array.
- `countA(String)` counts ASCII `'a'` characters in `"banana"` using `GetStringCritical`.

Both obtain the length **before** Critical, make no other JNI calls between Get/Release, and then return the result to Java. Addition uses `jlong` to avoid 32-bit overflow for example values; the string part counts by **UTF-16 code units**.

### 5.1. Java: File `CriticalRegionDemo.java`

~~~java
import java.util.Objects;

public final class CriticalRegionDemo {
    static {
        System.loadLibrary("jnicritical");
    }

    private CriticalRegionDemo() {
    }

    private static native long sumNative(int[] values);

    private static native int countANative(String text);

    public static long sum(int[] values) {
        return sumNative(Objects.requireNonNull(values, "values"));
    }

    public static int countA(String text) {
        return countANative(Objects.requireNonNull(text, "text"));
    }

    public static void main(String[] args) {
        int[] values = {1, 2, 3, 4, 5};
        System.out.println("sum=" + sum(values));
        System.out.println("count a=" + countA("banana"));
    }
}
~~~

`Objects.requireNonNull` lets Java reject null in the public API before entering JNI. The native C function still has defensive checks so `NULL` is never passed into a Critical API.

### 5.2. Generate the JNI Header

In the directory containing `CriticalRegionDemo.java`, using **JDK 17+**:

~~~bash
javac -h . CriticalRegionDemo.java
~~~

`javac` generates `CriticalRegionDemo.class` and `CriticalRegionDemo.h`. The two important prototypes in the header:

~~~c
/* Equivalent declarations in the header generated by javac -h */
JNIEXPORT jlong JNICALL Java_CriticalRegionDemo_sumNative(
        JNIEnv *, jclass, jintArray);

JNIEXPORT jint JNICALL Java_CriticalRegionDemo_countANative(
        JNIEnv *, jclass, jstring);
~~~

Do not manually edit export names; use the JDK-generated header so signatures do not break when the Java class or methods change.

### 5.3. C: File `critical_demo.c`

~~~c
#include "CriticalRegionDemo.h"
#include <stddef.h>

/* Only call outside Critical regions. */
static void throw_null_pointer(JNIEnv *env, const char *message) {
    jclass type = (*env)->FindClass(
            env, "java/lang/NullPointerException");
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
        (*env)->DeleteLocalRef(env, type);
    }
}

/*
 * Get Critical may return NULL. The spec does not require
 * every NULL failure to come with a pending exception.
 * This helper is only called WHEN Get has failed,
 * meaning no Critical region is currently held.
 */
static void throw_oom_if_needed(JNIEnv *env) {
    if ((*env)->ExceptionCheck(env)) {
        return;
    }

    jclass type = (*env)->FindClass(
            env, "java/lang/OutOfMemoryError");
    if (type != NULL) {
        (*env)->ThrowNew(
                env, type, "Cannot obtain JNI critical data");
        (*env)->DeleteLocalRef(env, type);
    }
}

JNIEXPORT jlong JNICALL Java_CriticalRegionDemo_sumNative(
        JNIEnv *env, jclass declaringClass, jintArray values) {
    (void) declaringClass;

    if (values == NULL) {
        throw_null_pointer(env, "values must not be null");
        return 0;
    }

    /* All preparatory JNI calls happen BEFORE Critical. */
    const jsize length = (*env)->GetArrayLength(env, values);
    if (length == 0) {
        return 0;
    }

    jint *elements = (jint *)(*env)->GetPrimitiveArrayCritical(
            env, values, NULL);
    if (elements == NULL) {
        /* No pointer is held; allowed to use JNI for error handling. */
        throw_oom_if_needed(env);
        return 0;
    }

    /* BEGIN Critical region: only C computation on data. */
    jlong total = 0;
    for (jsize i = 0; i < length; i++) {
        total += (jlong) elements[i];
    }

    /* END Critical region before returning to Java. */
    (*env)->ReleasePrimitiveArrayCritical(
            env, values, elements, JNI_ABORT);
    return total;
}

JNIEXPORT jint JNICALL Java_CriticalRegionDemo_countANative(
        JNIEnv *env, jclass declaringClass, jstring text) {
    (void) declaringClass;

    if (text == NULL) {
        throw_null_pointer(env, "text must not be null");
        return 0;
    }

    /* Number of UTF-16 units, obtained BEFORE Critical. */
    const jsize length = (*env)->GetStringLength(env, text);
    if (length == 0) {
        return 0;
    }

    const jchar *chars = (*env)->GetStringCritical(
            env, text, NULL);
    if (chars == NULL) {
        throw_oom_if_needed(env);
        return 0;
    }

    /* BEGIN Critical region: no JNI, IO, or blocking. */
    jint count = 0;
    for (jsize i = 0; i < length; i++) {
        if (chars[i] == (jchar) 'a') {
            count++;
        }
    }

    /* END Critical region. */
    (*env)->ReleaseStringCritical(env, text, chars);
    return count;
}
~~~

**Why `JNI_ABORT` in `sumNative`?** The function only reads the array. If the JVM uses a copy, `JNI_ABORT` frees the copy **without copy-back**. If the JVM returns a direct pointer, this mode does not destroy the array and there is no copy to discard; Release is still required. `countANative` has no mode because the `ReleaseStringCritical` API only accepts `env, text, chars`.

**Why check `length == 0`?** Returning directly avoids opening an unnecessary Critical region. The code does not rely on pointer behavior for an empty array/string.

**Why use `throw_oom_if_needed`?** The JNI Specification allows some functions to return `NULL` to indicate failure without necessarily throwing an exception. This code only runs **after Get has failed**, is not inside the Critical region, and ensures Java does not mistake `0` for a successful result if Get fails to obtain the data.

### 5.4. Compiling the Library on Linux

Set `JAVA_HOME` to the root directory of the **JDK running the JVM**; `jni.h` must exist in `$JAVA_HOME/include`. Using GCC/Clang:

~~~bash
cc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  critical_demo.c -o libjnicritical.so
~~~

### 5.5. Compiling on macOS

~~~bash
cc -std=c11 -Wall -Wextra -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  critical_demo.c -o libjnicritical.dylib
~~~

### 5.6. Compiling on Windows x64

In **x64 Native Tools Command Prompt for Visual Studio**, with `JAVA_HOME` pointing to an x64 JDK:

~~~bat
cl /nologo /std:c11 /W4 /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" critical_demo.c /link /OUT:jnicritical.dll
~~~

Choose **one** command group matching your OS; do not use an x86 library on an x64 JVM, or binaries from another OS. Place the library file in the same directory as `CriticalRegionDemo.class`.

### 5.7. Running and Reading the Output

~~~bash
java -Djava.library.path=. CriticalRegionDemo
~~~

Expected stdout:

~~~text
sum=15
count a=3
~~~

Explanation: `1 + 2 + 3 + 4 + 5 = 15` and `"banana"` has three `'a'` characters. The result does not depend on whether the JVM pins or copies, because the code follows the JNI contract and always calls Release after each successful Get.

**Run prerequisites:** JDK 17+; a C compiler for the right OS/CPU; run in the directory containing `.class` and the shared library; `JAVA_HOME` pointing to the JDK. The example performs no IO, logging, callbacks, or JNI calls **inside** a Critical region.

## 6. Bad Snippet: Why Does It Easily Deadlock or Slow Down GC?

This is an **illustrative anti-pattern, do not run and do not put into production**:

~~~c
/* WRONG: placed inside a JNI method with env, array, callback... */
jint *p = (jint *)(*env)->GetPrimitiveArrayCritical(
        env, array, NULL);
if (p == NULL) {
    return;
}

/* All three operations below are wrong inside a Critical region. */
jsize length = (*env)->GetArrayLength(env, array);
(*env)->CallVoidMethod(env, callback, methodId);
log_to_file_or_network(p, length);

(*env)->ReleasePrimitiveArrayCritical(env, array, p, 0);
~~~

Problems:

- `GetArrayLength` is another JNI call between Get/Release.
- `CallVoidMethod` can run Java code, allocate, wait on locks, or trigger GC.
- `log_to_file_or_network` can wait on disk, sockets, internal locks, or the heap allocator.
- If the callback throws an exception/jumps out of the code flow, the pointer may be held too long or Release may be forgotten.

**How to fix:** obtain `length` and prepare callback arguments **before Get**; inside Critical only perform the planned small copy/computation; **Release**; only then invoke callbacks and log. If IO is needed directly on the data, copy a portion into a separate C buffer and Release before doing IO.

### 6.1. Fixed Flow Example (Code Diagram)

~~~c
/* Illustrates ordering; helper/variable names depend on the application. */
jsize length = (*env)->GetArrayLength(env, array);
prepare_noncritical_state();     /* Can allocate, check errors */

jint *p = (jint *)(*env)->GetPrimitiveArrayCritical(
        env, array, NULL);
if (p == NULL) {
    handle_error_outside_critical();
    return;
}

/* Fast CPU only, avoid callbacks/IO/locks and arbitrary JNI. */
compute_a_small_result(p, length);

(*env)->ReleasePrimitiveArrayCritical(env, array, p, JNI_ABORT);

/* Now outside Critical. */
call_java_callback_or_log();
~~~

This is **C pseudocode**, not standalone compilable code; `prepare_noncritical_state`/`compute_a_small_result`/`call_java_callback_or_log` are descriptive function names. In real code, verify that `compute_a_small_result` **does not hide** JNI calls, locks, or IO.

## 7. Release: Modes `0`, `JNI_ABORT`, `JNI_COMMIT`

With `ReleasePrimitiveArrayCritical`, the `mode` parameter handles the case where the JVM **uses a copy**:

| `mode` | When JVM creates a copy | When JVM returns a direct pointer |
| --- | --- | --- |
| `0` | Copies back changes (if any), frees the copy | Ends holding the pointer; no copy-back |
| `JNI_ABORT` | Discards changes in the copy, frees the copy | Mode is ignored because there is no copy; **cannot use this mode to roll back direct writes** |
| `JNI_COMMIT` | Copies back but **does not free the copy**; a final Release is still required | Mode has no effect on a non-copy buffer |

**Very common mistake:** `JNI_ABORT` is a sensible choice for **read-only** access, not a transaction/rollback mechanism. If you **have written to a direct pointer to the Java array**, `JNI_ABORT` cannot undo the changes. Code that intends to **modify an array** should normally Release with `mode = 0` and handle error logic itself.

Do not use `JNI_COMMIT` thinking "Release is done" when in fact a copy still remains unfreed; to finish, there must be a final Release per the contract. When there are no special requirements, **`0`** is the simple choice for array-writing regions; **`JNI_ABORT`** for read-only regions. `ReleaseStringCritical` **has no** mode parameter because Java strings are immutable from Java's perspective and the read-only pointer is `const jchar *`.

### 7.1. What Does `isCopy` Mean?

~~~c
/* Illustration: check isCopy AFTER Release, do not call JNI while holding. */
jboolean is_copy = JNI_FALSE;
jint *p = (jint *)(*env)->GetPrimitiveArrayCritical(
        env, array, &is_copy);

if (p != NULL) {
    /* Only read data; no arbitrary JNI calls here. */
    jint first = p[0];  /* Only valid when array is non-empty! */
    (*env)->ReleasePrimitiveArrayCritical(
            env, array, p, JNI_ABORT);

    /* Can inspect is_copy and first outside Critical. */
}
~~~

This snippet is **illustrative, not standalone runnable**; it assumes `array` has at least one element. `JNI_TRUE` indicates the JVM created a copy, `JNI_FALSE` indicates data may be accessed directly. Regardless of the value, you still **must Release**, and must not block or make arbitrary JNI calls inside the Critical region. Measure performance on real workloads rather than using `isCopy` to build implementation-dependent logic.

## 8. Exceptions, Null Pointers, Exit Paths, and C++

For both Get Critical functions:

- The `jarray`/`jstring` argument must be valid and non-`NULL`. Check in Java or before Get using valid JNI.
- Get functions may return **`NULL`** on failure (such as out of memory). Do not read or Release a `NULL` pointer as if Get succeeded.
- If Get returns `NULL`, **no** critical pointer is held by that Get call. That is when you may check `ExceptionCheck`, preserve a pending exception, or report an error per the contract.
- If Get succeeds, **every branch** must Release before returning or handling JNI errors/exceptions.
- In C++ code, use appropriate scoping/RAII to ensure Release across multiple branches. However, do not let C++ exceptions cross the JNI boundary and **do not** perform cleanup using functions that can block inside a critical destructor.

Flow pattern with an error status variable:

~~~c
/* Idea inside a JNI function; not a standalone program. */
jint status = 0;
jint *elements = (jint *)(*env)->GetPrimitiveArrayCritical(
        env, array, NULL);
if (elements == NULL) {
    return 0;      /* Handle error after Get failure in real code */
}

/* Only perform safe raw operations. */
if (elements[0] < 0) {
    status = 1;    /* Record status, DO NOT ThrowNew here */
}

(*env)->ReleasePrimitiveArrayCritical(
        env, array, elements, JNI_ABORT);

/* Outside Critical, now JNI error handling is allowed. */
if (status != 0) {
    /* Can ThrowNew or invoke callback here. */
}
~~~

This snippet assumes a non-empty array and is used to explain **processing order**, not to replace null/length and error checks in the runnable code in section 5.

**Do not assume JNI Critical is a lock against concurrent access:** the array can be observed/modified by other Java threads according to their own memory and synchronization rules; JNI does not turn operations on a shared array into atomic or thread-safe operations. If you need a consistent snapshot, design synchronization **outside the Critical region** or copy the data into independent native memory.

## 9. When Long Processing or Blocking Is Needed: Choose Other APIs

Critical restrictions are the reason to **avoid holding a Java array/string pointer while running IO or long-running processing**. Some alternatives:

| Need | Suitable choice | What to control |
| --- | --- | --- |
| Read a small `int[]` slice into C | `GetIntArrayRegion` | Sufficient C buffer space, valid offset/length |
| Write an `int[]` slice back to Java | `SetIntArrayRegion` | Bounds checks and pending exceptions |
| Read multiple chunks and do IO between chunks | Copy each slice with `GetIntArrayRegion`, process **outside Critical region** | Chunk size, overflow, data synchronization |
| Read UTF-16 from a Java String | `GetStringRegion` or `GetStringChars` / `ReleaseStringChars` | `jchar` is a UTF-16 code unit, appropriate lifetime |
| Read string as bytes for C APIs | `GetStringUTFChars` / `ReleaseStringUTFChars` or explicit transcoding | JNI uses **Modified UTF-8**, not identical to standard UTF-8 |
| Exchange large native buffers with independent lifetime | `ByteBuffer.allocateDirect` + JNI DirectBuffer API or FFM depending on JDK | Ownership, GC reachability, alignment, and thread safety |

`Get<PrimitiveType>ArrayElements` and `GetStringChars` do not have the **same strict Critical constraints** by API, but the JVM can still use copies/pinning. Therefore, you should also Release early and avoid holding pointers longer than necessary. If processing time can grow depending on input, it is usually easier to control by **copying into native-owned memory**, Releasing, and then processing.

### 9.1. Example: Chunked Copy, Then IO Processing

The following C snippet is an **algorithmically self-contained** helper; it has no IO inside and only illustrates structure. IO processing can be added after each `GetIntArrayRegion` completes, because no Critical region is open.

~~~c
#include <jni.h>
#include <stddef.h>

static jlong sum_chunks(JNIEnv *env, jintArray array) {
    enum { CHUNK = 1024 };
    jint buffer[CHUNK];

    jsize n = (*env)->GetArrayLength(env, array);
    jlong total = 0;

    for (jsize start = 0; start < n; ) {
        jsize size = n - start;
        if (size > CHUNK) {
            size = CHUNK;
        }

        (*env)->GetIntArrayRegion(
                env, array, start, size, buffer);
        if ((*env)->ExceptionCheck(env)) {
            return 0;  /* Pending exception will be handled by caller. */
        }

        for (jsize i = 0; i < size; ++i) {
            total += (jlong) buffer[i];
        }
        start += size;
    }

    return total;
}
~~~

The helper assumes `array != NULL`; if used in a real JNI method, check beforehand and ensure the type/caller contract. `GetIntArrayRegion` copies immediately into the C buffer, so after the call returns **no pointer into the Java heap is held**. Logging/IO can be inserted between chunks if the application contract allows, though consistency when the Java array has other writers still requires separate synchronization.

### 9.2. Safe IO Workflow with Java Data

If a native API needs to send `byte[]` over a socket:

1. Check length and socket permissions before using the data.
2. Use `GetByteArrayRegion` to **copy a chunk** into a C buffer.
3. Once the JNI copy call has finished, you can `send`/`write` on that C buffer, even if IO must block.
4. Continue with the next chunk as needed; verify bounds and consistency.

If Critical is used only to copy a very small chunk, you must **Release immediately after copying**, and only then `send`. Never pass a pointer from `GetPrimitiveArrayCritical` directly into a potentially blocking `send` while still holding Critical.

## 10. Performance: Critical Is Not Always Optimal

The goal of the Critical APIs is to give the JVM an opportunity to provide an efficient access path to data, but that **does not guarantee zero-copy**. Whether a piece of code is faster depends on:

- The JVM/collector, Java version, and GC mode.
- Array/string size, number of JNI calls, number of bytes to process.
- Copy frequency and pin/GC/safepoint overhead.
- Contention among Java threads, length of the critical section.
- Whether the processing is truly short and CPU-only.

A loop over a huge array inside Critical, even without JNI calls, can still be too long. You should **limit the amount of work per Critical hold**; for large workloads, consider chunked copying. Do not blindly adopt "whenever `GetPrimitiveArrayCritical` exists, use it" or benchmark without GC pressure and draw conclusions for production.

Benchmark with representative data and measure GC pauses/throughput/tail latency, not just a microbenchmark of a single small call.

## 11. Debugging Critical Region Bugs

### 11.1. `-Xcheck:jni` on HotSpot/OpenJDK

With the example in section 5:

~~~bash
java -Xcheck:jni -Djava.library.path=. CriticalRegionDemo
~~~

`-Xcheck:jni` can print a warning when it detects **other JNI calls between Get Critical and Release Critical**, for example:

~~~text
Warning: Calling other JNI functions in the scope of
Get/ReleasePrimitiveArrayCritical or Get/ReleaseStringCritical
~~~

This is an **example warning**, not the stdout of a correct program. With the valid source in section 5, the application stdout remains the two lines `sum=15` and `count a=3`; the warning above is not expected. CheckJNI is a tool that detects many JNI bugs, but **does not prove code never blocks** and does not replace reviewing C/C++ calls for hidden IO/locks.

### 11.2. Signs to Investigate

| Symptom | Diagnostic question | Action |
| --- | --- | --- |
| Longer GC pauses or increased latency when native code runs | Is any thread holding Critical too long? | Reduce computation, copy chunks then Release |
| Native method hangs when Java threads are busy | Are Java callbacks, locks, or IO called under Critical? | Move callbacks/IO/locks outside |
| `-Xcheck:jni` warns about JNI calls inside Critical | Is `GetArrayLength`, `ExceptionCheck`, or `FindClass` after Get before Release? | Move preparation/checks before or after |
| Array unchanged after native code wrote to copy | Accidentally Released with `JNI_ABORT` | For changes to keep, use `mode = 0` |
| Data modified even though Release used `JNI_ABORT` | JVM returned direct pointer, no copy to discard | Do not treat `JNI_ABORT` as rollback |
| Crash / memory corruption after Release | Native code still using invalidated pointer | Stop all access immediately upon Release |
| String received wrong characters/count | Treating `jchar` as UTF-8 bytes or as code points | `GetStringCritical` gives UTF-16 units; check surrogates |
| Get returned `NULL` but Java sees result `0` | Code did not handle failed Get branch per contract | Check pending exception and report error **outside Critical** |
| Runs well on one JDK but slowly on another JDK/GC | Implementations may pin/copy differently | Re-benchmark, consider Region APIs |

Do not use `ExceptionDescribe`/`printf` to log while holding a pointer; only check/log **after Release**. If an error is detected inside Critical, store a flag or error code in a C variable, Release, and only then use JNI to report the exception.

## 12. JNI Critical Code Review Checklist

- **Before Get:** `jarray`/`jstring` is non-null, length is known, required output pointers/buffers are ready.
- **After Get:** always check `ptr != NULL` before accessing; on failure, handle outside Critical.
- **Inside Critical:** only short C/C++ loops; **no arbitrary JNI calls**, no Java callbacks, no waiting on mutexes/conditions, no potentially blocking file/socket IO.
- **Every branch:** Release matches the exact Get, exact object, exact pointer; never skipped on error.
- **Read-only arrays:** may Release with `JNI_ABORT`; **written arrays:** usually use `0`, do not expect `JNI_ABORT` to undo direct writes.
- **Strings:** `const jchar *`, UTF-16 length obtained beforehand; `ReleaseStringCritical` has no mode.
- **After Release:** only then handle exceptions, log, invoke callbacks, do IO, and continue using JNI.
- **Long holds:** consider `Get/Set<PrimitiveType>ArrayRegion`, `GetStringRegion`, chunked copies, or separate native memory.
- **Performance evaluation:** check both GC behavior and tail latency on the target JVM; do not infer zero-copy from the API name.

## 13. Review Questions

**1.** Does calling `GetPrimitiveArrayCritical` guarantee always receiving a direct pointer to the Java heap?  
**Answer:** No. The JVM may pin or return a copy; you must Release in both cases and obey Critical restrictions.

**2.** Can you call `GetArrayLength` after Get Critical to know how many elements to read?  
**Answer:** You should not; `GetArrayLength` is another JNI API. Obtain the length **before** opening Critical.

**3.** Why is `printf` or socket `recv` inside Critical a dangerous idea?  
**Answer:** IO/logging can block or wait on locks; the thread may hold state that impedes GC/safepoints, increasing latency or causing deadlocks.

**4.** If only reading `int[]` and the JVM provides a copy, why does `JNI_ABORT` make sense?  
**Answer:** There are no changes to copy back; the JVM can free the copy while skipping write-back.

**5.** Can `JNI_ABORT` be used to revert changes after modifying array elements through a Critical pointer?  
**Answer:** No. If the pointer points directly to the original array, the changes have already occurred; the mode is ignored when there is no copy.

**6.** Does `GetStringCritical` return UTF-8 bytes or UTF-16 units? Is NUL termination required?  
**Answer:** `const jchar *` contains UTF-16 units; you must use `GetStringLength` to get the length, do not assume a NUL-terminated string.

**7.** You need to call `CallVoidMethod` to report progress to Java after each processed chunk. Where should this call be placed?  
**Answer:** **After** `Release...Critical`; if there are more chunks, you can Get/Release each small chunk and invoke callbacks between pairs.

**8.** Why is `-Xcheck:jni` not enough to confirm code is safe?  
**Answer:** It can warn about JNI calls inside Critical, but it does not prove that every indirectly called C/C++ function is non-blocking and does not replace lifetime/GC review.

## 14. Reference Documentation

- [Oracle Java SE 17 — JNI: GetPrimitiveArrayCritical/ReleasePrimitiveArrayCritical](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#getprimitivearraycritical-releaseprimitivearraycritical): pointer contract, hold duration, JNI/blocking restrictions, and Release modes.
- [Oracle Java SE 17 — JNI: GetStringCritical/ReleaseStringCritical](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#getstringcritical-releasestringcritical): UTF-16 access and similar restrictions.
- [Oracle Java SE 17 — JNI: Get/Release Primitive Array Elements](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#releaseprimitivetypearrayelements-routines): meaning of `0`, `JNI_COMMIT`, `JNI_ABORT`.
- [Oracle Java SE 17 — Troubleshooting: -Xcheck:jni](https://docs.oracle.com/en/java/javase/17/troubleshoot/command-line-options1.html): JNI checking and warnings for JNI calls in critical regions.
- [Oracle Java SE 17 — JNI Specification Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/index.html): JNI API catalog and native caller responsibilities.

**Remember when writing production code:** Keep Critical regions as short and verifiable as possible. Obtain lengths and prepare beforehand, hold the pointer only for raw non-blocking computation, always Release, and only then use the JVM, callbacks, IO, or locks again.
