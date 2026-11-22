# Cleanup Operations Permitted While a JNI Exception Is Pending

## Objectives

In JNI, a Java exception is marked as a **pending exception** on the current thread. When native code invokes a Java method via `Call<Type>Method`, or when a JNI API fails and throws an exception, C/C++ **does not automatically unwind out of the function** the way Java executes `throw`. Native code continues running after that call. However, **most JNI functions must not be called while a pending exception exists**.

An apparent contradiction: if you must stop calling JNI immediately, how do you release pointers obtained from `GetStringUTFChars`, arrays obtained from `GetIntArrayElements`, JNI references, or monitors locked earlier? JNI has a **specific list of exceptions**: certain status-checking, resource-releasing, and local-frame management APIs are still permitted while an error is pending.

This lesson helps you:

- Recognize that a JNI call has set a pending exception, without misinterpreting `NULL` or a return value.
- Distinguish between what is **permitted to call** and what **should be called** on the error-handling path.
- Know the JNI cleanup group permitted by the specification while an exception is pending.
- Properly handle `DeleteLocalRef`, `DeleteGlobalRef`, `DeleteWeakGlobalRef`, `ReleaseString...`, `Release<Type>ArrayElements`, `ReleasePrimitiveArrayCritical`, `MonitorExit`, `PushLocalFrame`, and `PopLocalFrame`.
- Distinguish `ExceptionCheck`, `ExceptionOccurred`, `ExceptionClear`, and `ExceptionDescribe`; avoid accidentally losing the original exception.
- Write C code with a **single cleanup path**, releasing partially allocated resources and returning the exception intact to Java.
- Compile and run a Java 17 + JNI C example where a Java callback intentionally throws an error while native cleanup proceeds safely.

## 1. What is a pending exception in JNI really?

Consider the following flow:

~~~text
Java calls native method
       |
       v
C/JNI holds a few resources
       |
       v
C calls back into a Java method
       |
       v
Java throws IllegalStateException
       |
       v
C/JNI regains execution control
       |
       +-- ExceptionCheck() == JNI_TRUE
       |
       +-- CLEAN UP resources using permitted JNI APIs
       |
       v
C returns; exception remains pending
       |
       v
Java caller catches IllegalStateException
~~~

Unlike Java, ordinary C/JNI calls do not have an automatic stack unwinding mechanism for Java exceptions. If an exception occurs after `CallStaticVoidMethod`, the CPU continues executing the next C statement. You must **check and branch to the error path**, or intentionally clear and handle it.

Conceptually correct example:

~~~c
(*env)->CallStaticVoidMethod(env, clazz, callback);

if ((*env)->ExceptionCheck(env)) {
    goto cleanup;  /* Do not call any more Java methods here. */
}

/* Only reach here if no exception is pending. */
~~~

This is an **illustrative C snippet** inside a JNI function that already has `env`, `clazz`, `callback`, and the `cleanup` label. `ExceptionCheck` does not clear the exception. If cleanup finishes and the native method returns **without** calling `ExceptionClear`, the JVM propagates the exception to the Java caller as usual.

### Three error-handling options

1. **Propagate the original error — recommended default:** check, clean up valid resources, and return so the Java caller sees the exact original throwable.
2. **Intentional handling and recovery:** save/observe the exception if needed, call `ExceptionClear`, and execute valid handling logic once no pending exception remains; ensure the application clearly defines recoverable cases.
3. **Intentional exception translation:** after cleaning up and clearing, create/throw a different Java error type if required by the API contract. You must preserve the cause if needed and be careful with new allocation failures. Do not silently replace the exception just to log or "keep running."

**Not** a valid option: skipping `ExceptionCheck` and arbitrarily calling `FindClass`, `NewStringUTF`, `GetMethodID`, `CallObjectMethod`, or `GetArrayLength` while an exception is still pending.

## 2. Official list: which calls are permitted

According to the **Exception Handling** section in the Java SE 17 JNI specification, there are the following groups (names written in JNI interface style; in C, use `(*env)->Method(env, ...)`):

| Group | Permitted APIs while pending | Effect and notes |
|---|---|---|
| Exception checking/control | `ExceptionCheck`, `ExceptionOccurred`, `ExceptionDescribe`, `ExceptionClear` | Inspect state, get throwable reference, print diagnostics, or clear; **the latter two APIs have important side effects** |
| Deleting references | `DeleteLocalRef`, `DeleteGlobalRef`, `DeleteWeakGlobalRef` | Release ownership of the exact JNI reference type created/held |
| Releasing string buffers | `ReleaseStringChars`, `ReleaseStringUTFChars`, `ReleaseStringCritical` | Release the pointer obtained by the corresponding Get, not freeing `jstring` |
| Releasing primitive array buffers | `Release<PrimitiveType>ArrayElements`, `ReleasePrimitiveArrayCritical` | Release the pointer obtained by the corresponding Get; right mode and right array |
| Local frame management | `PushLocalFrame`, `PopLocalFrame` | Listed in the specification; does not mean you should allocate a new frame in the middle of an error path |
| Releasing a monitor | `MonitorExit` | Only used to exit a monitor validly owned by that same thread |
| Special Invocation API | `DetachCurrentThread` | Listed by the Java SE specification; this is a `JavaVM` operation for an **attached native thread**, not a routine native method cleanup call |

**Count by API entry:** 4 exception + 3 reference + 3 string + 2 array + 2 local-frame + 1 monitor + 1 detach = 16 function forms listed in the Java SE specification. `Release<PrimitiveType>ArrayElements` is actually **a family of eight functions** by array type, rather than a single function with that literal name.

Concrete examples of the Release family:

~~~c
(*env)->ReleaseBooleanArrayElements(env, booleans, boolean_ptr, JNI_ABORT);
(*env)->ReleaseByteArrayElements(env, bytes, byte_ptr, JNI_ABORT);
(*env)->ReleaseIntArrayElements(env, ints, int_ptr, JNI_ABORT);
(*env)->ReleaseDoubleArrayElements(env, doubles, double_ptr, JNI_ABORT);
~~~

The snippet above **only illustrates API names**, not standalone runnable code; each `array` and `pointer` must be a pair successfully obtained by the exact corresponding Get function. You can use mode `0` or `JNI_ABORT` depending on whether changes need to be written back; do not pass an arbitrary pointer and do not "release" twice.

### `DetachCurrentThread` does not mean "detach anytime"

`DetachCurrentThread` belongs to the **JNI Invocation Interface** on `JavaVM*`, not the `JNIEnv*` function table. The Java SE specification lists it in the pending exception context; however, it only makes sense in an attached native thread and must obey the JVM's detach conditions. A native method currently being called from Java should not detach that Java thread itself. For most ordinary JNI functions, the cleanup path only needs the exception, reference, release, and monitor groups.

The Android JNI tips documentation lists the relevant `JNIEnv` functions and does not include `DetachCurrentThread` in the same table. When writing a multi-runtime library, check the conditions of the actual environment you run on, rather than treating detach as a cure-all for every exception.

## 3. JNI calls *not* permitted while an exception is pending

| Do not call while pending | Why / alternative |
|---|---|
| `FindClass`, `GetMethodID`, `GetFieldID` | These are lookups that may load/initialize classes or raise errors; if needed, perform them **before** the potentially throwing operation or after an intentional clear |
| `NewObject`, `NewStringUTF`, `New<Type>Array` | Allocating Java objects while the thread has an exception is out of order |
| `Call<Type>Method`, `CallStatic<Type>Method` | Do not continue Java callbacks while an exception is still pending |
| `GetObjectClass`, `GetObjectField`, `SetObjectField` | Do not use to inspect/write Java data in the middle of cleanup |
| `GetArrayLength`, `Get<Type>ArrayRegion`, `Set<Type>ArrayRegion` | Do not fetch more array data while pending; region APIs are **not Release** |
| `GetStringUTFChars`, `Get<Type>ArrayElements`, `GetPrimitiveArrayCritical` | Do not acquire new pointers; only **release** previously acquired pointers with the corresponding Release |
| `NewLocalRef`, `NewGlobalRef`, `EnsureLocalCapacity` | Do not arbitrarily create more references/capacity; `Delete...Ref` is the permitted cleanup group |
| `MonitorEnter` | Do not lock additional monitors while pending; only `MonitorExit` for locks that need releasing |
| `Throw`, `ThrowNew` | Do not arbitrarily replace the pending exception; if replacement is needed, **clear first, then execute the new error-handling flow** |

**Common pitfall:** a function that "looks harmless" is not automatically permitted. `GetArrayLength` only reads the length, yet it is **not on the safe list**. `NewLocalRef` does not invoke a Java callback, yet it is still not on the list. Conversely, `ReleaseIntArrayElements` and `DeleteLocalRef` **are explicitly listed** because cleanup must be allowed in an error state.

Some JNI functions might appear to work on a specific JVM even when misused during a pending exception; that **does not turn such behavior into a portable JNI contract**. When CheckJNI is enabled or when running on another JVM, incorrect code may trigger warnings, errors, or corrupt VM state.

## 4. The four Exception functions: all permitted, but different semantics

| JNI API | Return value | Keeps pending exception? | Use case |
|---|---|---|---|
| `ExceptionCheck(env)` | `jboolean` | **Yes** | Ask "is there currently a pending exception?" without creating a throwable reference |
| `ExceptionOccurred(env)` | `jthrowable` local reference or `NULL` | **Yes** | Obtain a reference to the throwable to preserve or process further |
| `ExceptionClear(env)` | `void` | **No** | **Intentionally** clear the pending state so JNI can be used normally |
| `ExceptionDescribe(env)` | `void` | **No** | Print the exception/backtrace to the system error channel **and clear pending as a side effect** |

**Important warning: `ExceptionDescribe` does not merely "print a log while keeping the error."** The Oracle specification explicitly states that it **clears the pending exception** when printing the information. If you call `ExceptionDescribe` just for debugging and then return, the Java caller may **no longer receive the original exception**.

Pattern to check while keeping the error:

~~~c
if ((*env)->ExceptionCheck(env)) {
    /* Do not call ExceptionClear or ExceptionDescribe. */
    goto cleanup;
}
~~~

Pattern to obtain a reference to the throwable while keeping it pending:

~~~c
jthrowable failure = (*env)->ExceptionOccurred(env);
if (failure != NULL) {
    /* failure is a local JNI reference; the exception is STILL pending. */
    (*env)->DeleteLocalRef(env, failure);
    goto cleanup;
}
~~~

Both are merely **C snippets inside a JNI function** that has `env` and `cleanup`. `ExceptionOccurred` returns a local reference; if you only hold it to check and do not use it, `ExceptionCheck` is cleaner and avoids an extra local reference.

### When you genuinely need to clear and then restore an exception

A pattern usable in specialized error-handling code (unnecessary for a normal return path):

~~~c
jthrowable original = (*env)->ExceptionOccurred(env);
if (original != NULL) {
    (*env)->ExceptionClear(env);

    /*
     * From here, there is no pending exception.
     * Intentional handling can be performed, though JNI calls can
     * still fail; do not assume every operation always succeeds.
     */

    (*env)->Throw(env, original);
    (*env)->DeleteLocalRef(env, original);
}
~~~

This is an **illustrative code snippet**, not a standalone runnable C function. `Throw` here is called **only after `ExceptionClear`**, so it does not violate the list. As soon as `Throw` succeeds, the exception becomes pending again, so `DeleteLocalRef` on the last line is valid. Production code must also check the result of `Throw` and any exception state arising during the intermediate handling.

**If you only want to preserve the throwable, there is no need for a clear/rethrow cycle.** Doing so can lose the original error if the intermediate step fails due to out-of-memory or another lookup failure.

## 5. Resource management principle: only release what was successfully acquired

A native function may have acquired **some** resources before a Java exception occurred. The safe model in C is:

1. Initialize **all owned pointers and JNI references** to `NULL` before any calls that can fail.
2. Acquire sequentially; after each failed step, branch to a **single cleanup label**.
3. When a Java callback throws an exception, only call `ExceptionCheck` or `ExceptionOccurred`; stop all non-whitelisted JNI calls.
4. Clean up (usually in reverse acquisition order) using permitted Release/Delete APIs; call `free`/`fclose`/`close` as appropriate for **C/native** resources, if any.
5. Return with the **pending exception intact**; the Java caller will receive the error.

Common skeleton:

~~~c
const char *utf = NULL;
jint *items = NULL;
jobject global_ref = NULL;
jclass local_cls = NULL;

/* Acquire some resources; check each result. */
/* ... */
/* Call Java callback that may throw an exception. */

if ((*env)->ExceptionCheck(env)) {
    goto cleanup;
}

/* Subsequent steps only when no exception exists. */

cleanup:
    if (global_ref != NULL) {
        (*env)->DeleteGlobalRef(env, global_ref);
    }
    if (items != NULL) {
        (*env)->ReleaseIntArrayElements(
                env, java_array, items, JNI_ABORT);
    }
    if (utf != NULL) {
        (*env)->ReleaseStringUTFChars(env, java_string, utf);
    }
    if (local_cls != NULL) {
        (*env)->DeleteLocalRef(env, local_cls);
    }
    return;
~~~

This is an **illustrative C skeleton**, not independently compilable because it requires `env`, `java_array`, `java_string`, acquisition steps, and a `void`-returning function. It shows that permitted cleanup operations can be executed **right while the exception is still pending**.

**Why initialize to `NULL`?** Any acquisition can fail, so the cleanup branch needs to know exactly which resources were obtained. Do not call `ReleaseStringUTFChars` with a pointer that is not a valid Get result, do not use `DeleteGlobalRef` on a local ref, and do not call `free` on a pointer managed by JNI.

## 6. Runnable Java 17 + JNI C example: Java throws, C still cleans up resources

The example uses a native method `callAndClean` taking a `String` and an `int[]`. It:

1. Looks up the Java method ID **before** any error occurs.
2. Creates a local reference, acquires a UTF string and primitive array elements, and creates a global reference.
3. Calls back into a Java method that intentionally throws `IllegalStateException`.
4. While the exception is pending, uses **only permitted JNI cleanup APIs**.
5. Returns to Java; Java catches the exact original exception.

### 6.1. Java file: `PendingCleanupDemo.java`

~~~java
public final class PendingCleanupDemo {
    static {
        System.loadLibrary("pendingcleanupdemo");
    }

    private static native void callAndClean(
            String text, int[] values);

    private static void alwaysFails() {
        throw new IllegalStateException("boom from Java callback");
    }

    public static void main(String[] args) {
        try {
            callAndClean("hello JNI", new int[] {2, 4, 6});
            System.out.println("unexpected success");
        } catch (IllegalStateException error) {
            System.out.println(
                    "caught=" + error.getClass().getSimpleName());
            System.out.println("message=" + error.getMessage());
        }

        System.out.println("continued=true");
    }
}
~~~

This Java source does not need to create JNI references itself; the `String` and `int[]` arguments are passed by the runtime to C via `jstring` and `jintArray`. Java `alwaysFails()` is called from C via JNI, and its body is fixed to test exception propagation.

### 6.2. Generate header and define JNI C

Run with JDK 17+:

~~~bash
javac -h . PendingCleanupDemo.java
~~~

The command generates `PendingCleanupDemo.class` and the header `PendingCleanupDemo.h`. Keep the header and C source in the same directory so the build commands below find each other.

File `pendingcleanupdemo.c`:

~~~c
#include "PendingCleanupDemo.h"

JNIEXPORT void JNICALL
Java_PendingCleanupDemo_callAndClean(
        JNIEnv *env, jclass declaring_class,
        jstring text, jintArray values) {

    jmethodID fail_method = NULL;
    jclass local_class = NULL;
    const char *utf = NULL;
    jint *elements = NULL;
    jobject global_text = NULL;

    /* Validate arguments before any pending exception exists. */
    if (text == NULL || values == NULL) {
        jclass npe = (*env)->FindClass(
                env, "java/lang/NullPointerException");
        if (npe != NULL) {
            (*env)->ThrowNew(env, npe,
                    "text and values must be non-null");
            (*env)->DeleteLocalRef(env, npe);
        }
        return;
    }

    /* Lookup must finish BEFORE the callback that can throw. */
    fail_method = (*env)->GetStaticMethodID(
            env, declaring_class, "alwaysFails", "()V");
    if (fail_method == NULL) {
        return; /* Leave lookup/class initialization error intact. */
    }

    /* Illustrative local reference: owned and needs DeleteLocalRef. */
    local_class = (*env)->FindClass(env, "java/lang/Object");
    if (local_class == NULL) {
        goto cleanup;
    }

    /* JNI-owned buffer: must call ReleaseStringUTFChars. */
    utf = (*env)->GetStringUTFChars(env, text, NULL);
    if (utf == NULL) {
        goto cleanup;
    }

    /* JNI-owned buffer: must call ReleaseIntArrayElements. */
    elements = (*env)->GetIntArrayElements(env, values, NULL);
    if (elements == NULL) {
        goto cleanup;
    }

    /* Global JNI reference: must call DeleteGlobalRef. */
    global_text = (*env)->NewGlobalRef(env, text);
    if (global_text == NULL) {
        goto cleanup;
    }

    /*
     * The Java callback always throws IllegalStateException.
     * C does NOT automatically unwind when the callback throws.
     */
    (*env)->CallStaticVoidMethod(
            env, declaring_class, fail_method);

    if ((*env)->ExceptionCheck(env)) {
        goto cleanup; /* Keep the pending exception intact. */
    }

cleanup:
    /*
     * Every JNI operation below is permitted while an exception is pending.
     * Reverse acquisition order, releasing only acquired resources.
     */
    if (global_text != NULL) {
        (*env)->DeleteGlobalRef(env, global_text);
    }
    if (elements != NULL) {
        (*env)->ReleaseIntArrayElements(
                env, values, elements, JNI_ABORT);
    }
    if (utf != NULL) {
        (*env)->ReleaseStringUTFChars(env, text, utf);
    }
    if (local_class != NULL) {
        (*env)->DeleteLocalRef(env, local_class);
    }

    /*
     * Do NOT call ExceptionClear or ExceptionDescribe.
     * The Java caller will receive the exact IllegalStateException.
     */
}
~~~

**Explanation of correctness:**

- `GetStaticMethodID`, `FindClass`, `GetStringUTFChars`, `GetIntArrayElements`, and `NewGlobalRef` are all called **before** the callback that creates the exception. If an acquisition fails, it jumps to `cleanup`; a JNI error may already be pending, so cleanup must still use the whitelist.
- `local_class` is a local reference created by `FindClass`; it must be released with `DeleteLocalRef` when no longer needed. `declaring_class` is supplied by the JVM to the native method; the code does not delete it.
- `utf` is only valid after `GetStringUTFChars` succeeds; `elements` is only valid after `GetIntArrayElements` succeeds. Do not use `free(utf)` or `free(elements)`.
- `global_text` has its own ownership and must be released with `DeleteGlobalRef`; it must not be replaced by `DeleteLocalRef`.
- In this example `elements` is not modified, so `JNI_ABORT` is chosen to discard copying back a **copy**. Do not use `JNI_ABORT` to promise reverting modified data if the JVM grants direct access to pinned storage.
- `ExceptionCheck` allows branching to `cleanup`; all JNI functions called in `cleanup` appear on the list permitted while pending. There are no additional `FindClass` calls or Java callbacks on this error path.
- `goto cleanup` here does not skip uninitialized variables: all resource-owning variables are set to `NULL` right at the start of the function.
- If the callback did not throw (unlike the demo's `alwaysFails`), execution still flows into `cleanup` and returns normally.

### 6.3. Build by operating system

The library must be compiled with the **JDK headers** and a compiler matching the architecture of the running JVM process. The commands below are independent alternatives; choose the one for your operating system.

**Linux — GCC:**

~~~bash
gcc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  pendingcleanupdemo.c -o libpendingcleanupdemo.so

java -Djava.library.path=. PendingCleanupDemo
~~~

**macOS — Clang:**

~~~bash
clang -std=c11 -Wall -Wextra -dynamiclib \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
  pendingcleanupdemo.c -o libpendingcleanupdemo.dylib

java -Djava.library.path=. PendingCleanupDemo
~~~

**Windows — MSVC Developer Command Prompt:**

~~~bat
cl /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" pendingcleanupdemo.c /Fe:pendingcleanupdemo.dll
java -Djava.library.path=. PendingCleanupDemo
~~~

Make sure `JAVA_HOME` points to a full JDK, not just a JRE; on Windows, run inside an MSVC Developer Command Prompt with the compiler configured. `System.loadLibrary("pendingcleanupdemo")` uses the logical name, while the JVM maps it to `libpendingcleanupdemo.so`/`libpendingcleanupdemo.dylib`/`pendingcleanupdemo.dll` depending on the platform.

### 6.4. Expected output

With the binary compiled and loaded successfully:

~~~text
caught=IllegalStateException
message=boom from Java callback
continued=true
~~~

The program does **not** print `unexpected success` because the exception from the Java callback propagates through the native method back to `main`. The Java `catch` handles the error and then executes `System.out.println("continued=true")`.

The output verifies that **the original exception is still propagated back to Java**; it is not a tool that proves every resource was released on every rare failure. Code review, native leak detectors, and testing acquisition-failure cases remain necessary for real applications.

## 7. Cleanup groups and related traps

### 7.1. `DeleteLocalRef`, `DeleteGlobalRef`, and `DeleteWeakGlobalRef`

**Three different reference types, three different lifetimes:**

- Local reference: e.g., `FindClass`, `NewObject`, `ExceptionOccurred`; valid within the thread's local reference frame. Cleaned up manually with `DeleteLocalRef` or via `PopLocalFrame`; the JVM automatically cleans up remaining local refs when the native method returns, though in loops or long-running calls early cleanup may be needed.
- Global reference: created with `NewGlobalRef`, persists across native calls until `DeleteGlobalRef`; not auto-deleted when the current function returns.
- Weak global reference: created with `NewWeakGlobalRef`; cleaned up with `DeleteWeakGlobalRef` and not treated as a strong reference keeping the object alive.

The delete APIs do **not** require `ExceptionClear` first. However, deletion must target a valid reference with proper ownership. A deleted reference must not be used again; do not delete the same reference twice. `DeleteLocalRef` is not a way to "free a Java object": objects are managed by the GC; deleting only removes a JNI root/reference.

### 7.2. `ReleaseStringChars`, `ReleaseStringUTFChars`, `ReleaseStringCritical`

Whichever Get you used, use its **paired Release**:

| Successfully acquired before error | Valid Release while pending |
|---|---|
| `GetStringChars(env, str, ...)` | `ReleaseStringChars(env, str, chars)` |
| `GetStringUTFChars(env, str, ...)` | `ReleaseStringUTFChars(env, str, utfChars)` |
| `GetStringCritical(env, str, ...)` | `ReleaseStringCritical(env, str, chars)` |

Pointers returned by Get may be copies or regions held/pinned by the JVM; do not `free` them yourself, and do not keep using them after Release. `GetStringUTFChars` provides JNI modified UTF-8, which does not necessarily match standard UTF-8 in all special-character cases.

With `GetStringCritical`, the critical region carries **additional constraints**: avoid other JNI calls and blocking operations while holding the pointer. When an error occurs, prioritize releasing the critical pointer quickly via `ReleaseStringCritical` (permitted while pending), and only then perform unrelated native work if truly needed.

### 7.3. `Release<PrimitiveType>ArrayElements` and release modes

APIs such as `GetIntArrayElements` may return a copy or a pointer to data held by the JVM. Once successfully acquired, you **must** call `ReleaseIntArrayElements` with the same `array` and `elements`, even when a Java callback throws an error.

| `mode` | Meaning when `elements` is a copy | Notes |
|---|---|---|
| `0` | Copy contents back and free the buffer | Typically chosen when native code wants to commit changes |
| `JNI_ABORT` | Free the copy **without** copying back | Suitable for read-only; cannot "undo" changes written directly when there is no copy |
| `JNI_COMMIT` | Copy back but **do not free the copy buffer** | If it is a copy, a final Release with `0` or `JNI_ABORT` is still needed to free it |

Example when only reading the array and a Java callback throws:

~~~c
if (elements != NULL) {
    (*env)->ReleaseIntArrayElements(
            env, array, elements, JNI_ABORT);
}
~~~

This is an **illustrative code snippet** where `elements` came from a successful `GetIntArrayElements(env, array, ...)`. Do not call `ReleaseIntArrayElements` with a pointer from `malloc` or with a pointer from an array of a different type. Even if the pending exception is completely unrelated to the array, Release remains a lifetime-management obligation.

Other types use the matching family member: `ReleaseByteArrayElements`, `ReleaseLongArrayElements`, `ReleaseFloatArrayElements`, ... There is no generic JNI API literally named `ReleaseArrayElements`.

### 7.4. `ReleasePrimitiveArrayCritical`

If `GetPrimitiveArrayCritical` was called, `ReleasePrimitiveArrayCritical` must be called as soon as finished, even when there is a pending exception. `GetPrimitiveArrayCritical` is **not** on the whitelist for pending exceptions; only **Release** is. While inside a critical region, avoid operations that might block or JNI calls disallowed by the critical access contract. Do not hold a critical region to perform network logging, allocate more Java objects, or wait on long locks.

### 7.5. `MonitorExit`

`MonitorExit` is a permitted JNI function while an exception is pending, intended to release a monitor that **the current thread validly acquired**, for example from an earlier successful `MonitorEnter` call.

~~~c
jint entered = (*env)->MonitorEnter(env, lock);
if (entered != JNI_OK) {
    return; /* Do not call MonitorExit if not acquired. */
}

/* ... Call Java code that may throw an exception ... */

/* MonitorExit is permitted even though the callback just threw an exception. */
(*env)->MonitorExit(env, lock);
return;
~~~

This is an **illustrative C snippet**, not a self-contained function. It assumes `env` and `lock` are valid, and no invalid JNI calls intervene. In real code, you must still check the result of `MonitorExit`. Do not call `MonitorExit` on an unowned monitor or call it extra times, as that can raise `IllegalMonitorStateException` and make the error harder to diagnose. **`MonitorEnter` is not on the list** of functions callable after an exception is already pending.

In addition, native code must not arbitrarily release monitors automatically managed by Java `synchronized` methods. Only clean up locks that native code actually owns according to its protocol.

### 7.6. `PushLocalFrame` and `PopLocalFrame`

JNI permits both of these APIs in the pending-exception list. However, on the cleanup path, the operation usually needed is **`PopLocalFrame` for a frame created before the error**, not `PushLocalFrame` to create a new one.

A standard pattern:

~~~c
if ((*env)->PushLocalFrame(env, 16) < 0) {
    return; /* An error may already exist; no new frame was created. */
}

/* Inside this frame: create local refs, call Java callback... */

if ((*env)->ExceptionCheck(env)) {
    (*env)->PopLocalFrame(env, NULL);
    return; /* Keep pending exception. */
}

(*env)->PopLocalFrame(env, NULL);
~~~

This is an **illustrative snippet inside a `void`-returning native method**, not a standalone program. `PushLocalFrame` is performed **before** the callback, when no exception exists. `PopLocalFrame(env, NULL)` cleans up the frame's local refs even while an error is pending. Do not use any local ref belonging to that frame after the frame has been popped.

**Distinction:** `PopLocalFrame` handles local references; it **does not automatically release** pointers obtained from `GetStringUTFChars` or `GetIntArrayElements`, nor does it delete global refs or free native `malloc`. Those release obligations exist independently and must be executed in the proper order before/after frame cleanup according to which references are needed.

## 8. Non-JNI native resources: still must be cleaned up

A pending exception is a restriction **on JNI calls**; it does not automatically forbid native C statements such as `free(buffer)` or appropriate cleanup operations for file descriptors, sockets, `FILE*`, or native mutexes. However, C resource management must follow proper ownership:

~~~c
void *heap = malloc(1024);
if (heap == NULL) {
    /* Report error per contract before continuing. */
    return;
}

/* ... A pending Java exception may occur ... */

free(heap);  /* Not a JNI call. */
return;
~~~

This is a **C code snippet** assuming `#include <stdlib.h>`. It has no `JNIEnv*` and therefore only illustrates native ownership.

**Do not conflate the two kinds of pointers:**

- `malloc`/`calloc` -> use `free` when owned.
- `GetStringUTFChars` -> use `ReleaseStringUTFChars`.
- `GetIntArrayElements` -> use `ReleaseIntArrayElements`.
- `NewGlobalRef` -> use `DeleteGlobalRef`.
- `NewLocalRef`/`FindClass`/`NewObject` -> clean up with `DeleteLocalRef` or a proper local frame.

C++ RAII can wrap these release operations in destructors to avoid forgetting cleanup, but a destructor running on a pending-exception path must still **call only permitted JNI APIs**, and destructors must not throw C++ exceptions across the JNI boundary. Java exceptions **do not automatically trigger** C++ stack unwinding; for RAII destructors to run, C++ control flow must leave scope normally or via its own C++ mechanism.

## 9. Preserving the original error when logging and translating exceptions

### Do not call `ExceptionDescribe` just to "take a look"

Wrong with respect to preserving the exception:

~~~c
if ((*env)->ExceptionCheck(env)) {
    (*env)->ExceptionDescribe(env);
    return; /* ExceptionDescribe already cleared the pending exception! */
}
~~~

This usually causes the Java caller not to receive the intended exception. `ExceptionDescribe` is useful during debugging, but if you want both to print a stack trace and to keep the throwable, you must explicitly handle saving/restoring the state; that approach is complex and can introduce new errors. In production, it is usually better to **return with the pending exception intact so Java logs it** using standard logging/handler mechanisms.

### Do not call `ThrowNew` before clearing

Wrong:

~~~c
if ((*env)->ExceptionCheck(env)) {
    /* Wrong: a Java exception is already pending. */
    (*env)->ThrowNew(env, cached_exception_class, "different error");
}
~~~

The snippet above only illustrates an **anti-pattern** and must not be put into runnable code. `ThrowNew` is not on the whitelist. Rather, let the original throwable propagate, or when the API contract genuinely requires mapping, **save the necessary information and intentionally clear** before making normal JNI calls in a non-pending state. Mapping must preserve the cause and not arbitrarily attempt to "recover" from serious JVM errors.

### Multiple errors at once

If a Java callback has thrown an exception and native cleanup of a file or monitor also fails, you must clearly define which error takes precedence. Do not default to creating a new Java exception while the original exception is still pending. For native resources, you can record an error code in pure native telemetry if safe; let Java handle the original exception first. If replacement is mandatory, do so via a controlled `ExceptionClear`/`Throw` flow and thoroughly test the secondary error path as well.

Do not call `GetObjectClass` or `CallObjectMethod` on `jthrowable` while an exception is pending just to retrieve its message. If you need deep inspection, clear intentionally first; if you only need to know whether an error occurred, use `ExceptionCheck`.

## 10. When acquisition fails midway

It is not only Java callbacks that cause pending exceptions. JNI acquisition functions themselves can fail:

~~~text
GetStaticMethodID        -> succeeds
FindClass(Object)        -> creates localClass
GetStringUTFChars        -> succeeds, yields utf
GetIntArrayElements      -> fails (e.g., out of memory)
NewGlobalRef             -> NOT YET CALLED
CallStaticVoidMethod     -> NOT YET CALLED
           |
           v
cleanup:
  globalText == NULL  => skip DeleteGlobalRef
  elements == NULL    => skip ReleaseIntArrayElements
  utf != NULL         => ReleaseStringUTFChars
  localClass != NULL  => DeleteLocalRef
           |
           v
return, preserving original error
~~~

Designing a **single cleanup label** handles this case. If you only write cleanup after the callback while earlier calls use direct `return`, you can leak string pointers or local/global references. Therefore, every acquisition step after other resources are already owned must share a common exit path.

Some JNI functions can signal failure by returning `NULL` without necessarily always having a pending exception; production code must specify how to handle that case separately. If after cleanup there is **no** pending exception yet execution cannot continue, you can create a new Java error *after ensuring nothing is pending*, or return a status code per the API contract. The runnable example mainly illustrates the **callback throws a Java exception** path and therefore does not create optional errors in each acquisition branch.

## 11. Distinguishing valid cleanup from dangerous cleanup situations

| Situation | Do | Do not |
|---|---|---|
| `CallStaticVoidMethod` throws `IllegalStateException`, UTF buffer held | `ReleaseStringUTFChars` then return keeping error | `NewStringUTF` to log a message while pending |
| `GetIntArrayElements` succeeded and read-only | `ReleaseIntArrayElements(..., JNI_ABORT)` | `free(elements)` or skip Release |
| Global reference created | `DeleteGlobalRef` when ownership is no longer needed | Use `DeleteLocalRef` instead |
| Many local refs created in a local frame | `PopLocalFrame` on the right frame or `DeleteLocalRef` | Reuse references after Pop or arbitrarily create more references |
| JNI `MonitorEnter` succeeded | Corresponding `MonitorExit`, checking result | Call another `MonitorEnter` while pending or release an unowned monitor |
| Want Java to see original error | Do not clear, run valid cleanup and return | Call `ExceptionDescribe` then return assuming error is still pending |
| Want to translate error to another type | Design clear mapping; clear before non-whitelisted JNI calls | Call `ThrowNew` while the old exception is still pending |
| Critical pointer is held | `Release...Critical` early, avoid blocking | Arbitrarily call other JNI functions or wait long before Release |
| Native thread self-attached to JVM | Clean up references, monitors, and thread lifecycle per Invocation API; detach when genuinely valid | Detach a Java-created thread, or detach while active Java frames remain |

**Being on the whitelist does not mean every call is safe with invalid arguments.** Calling `MonitorExit` on an unowned monitor or `ReleaseIntArrayElements` with a mismatched pointer is still a native programming bug; the whitelist only says JNI accepts that *kind of operation* while an exception is pending.

## 12. CheckJNI, error testing, and cross-platform testing

To test JNI code, use a JVM build capable of checking JNI misuse. With HotSpot/OpenJDK, you can enable CheckJNI diagnostics using the option:

~~~bash
java -Xcheck:jni -Djava.library.path=. PendingCleanupDemo
~~~

Supported options and warning formats depend on the JVM. CheckJNI can detect many JNI bugs such as using an inappropriate API while pending, bad references, or non-standard JNI management, but **it does not prove the program leaks zero C resources**. Also run sanitizers/native leak detectors and real-world tests if high reliability is required.

Tests you should have:

1. Callback succeeds: cleanup still runs, no leaks.
2. Callback throws `RuntimeException`: Java caller receives the **exact type and message**; native does not clear the error.
3. UTF buffer acquisition succeeds but array acquisition fails: UTF must be released.
4. Global ref created successfully and callback throws: global ref is deleted properly.
5. Many local references created in a loop: no local ref table overflow; proper local frame lifetime.
6. JNI monitor acquired before callback: matching `MonitorExit` is guaranteed, even when the callback throws.
7. Critical pointer held: hold duration is short, release is not skipped even on error paths.
8. Code runs on supported JVMs and ABIs; native library loading errors like `UnsatisfiedLinkError` must be handled separately, not confused with a pending exception from a Java callback.

For multithreaded environments, remember that a pending exception is **per-thread** state and `JNIEnv*` is also an interface pointer dedicated to its corresponding thread; do not pass `JNIEnv*` or local references to another thread to "clean up on its behalf."

## 13. Self-check questions

**1. Does `ExceptionCheck` clear a pending exception?** No. It only returns `JNI_TRUE`/`JNI_FALSE`.

**2. What does `ExceptionOccurred` return when an exception exists?** A local reference to `jthrowable`; the pending exception remains intact. If the local ref is no longer needed, `DeleteLocalRef` is permitted.

**3. Does `ExceptionDescribe` only log, or does it also change state?** It prints the exception/stack trace to the error channel and **clears the pending exception**. Do not use it as side-effect-free logging.

**4. When a callback fails, are `ReleaseByteArrayElements` and `DeleteLocalRef` permitted?** Yes, provided the pointer/reference was validly created beforehand and is released/deleted with the matching type.

**5. Is `GetArrayLength` on the whitelist?** No. Despite being a read-only function by name, do not call it while an exception is pending.

**6. Should you call `NewGlobalRef` in cleanup to save the exception?** Not while pending. If you need to keep the throwable, `ExceptionOccurred` provides a local ref; if you want deeper manipulation or to create a global ref, design an explicit `ExceptionClear` flow first.

**7. Does `JNI_ABORT` guarantee reverting all changes written to a primitive array?** No. When the JVM returns a direct pointer to the array instead of a copy, in-place writes may have already affected the array. `JNI_ABORT` mainly avoids copying back when a copy buffer exists.

**8. Does `PopLocalFrame` automatically call `ReleaseStringUTFChars`?** No. Local references and buffer pointers owned via Get/Release are two separate mechanisms; each must be released appropriately.

**9. If a JNI function returns `NULL` without a pending exception, does cleanup-and-return guarantee reporting an error to Java?** No. A separate contract is needed to translate the failure into a Java exception or status code if the operation cannot continue.

**10. Why is `goto cleanup` often sensible in C/JNI?** It consolidates the resource-cleanup path from multiple failure points, avoids forgetting Release/Delete when an exception occurs mid-acquisition, and does not require calling JNI outside the whitelist.

## Authoritative references

- [Oracle Java SE 17 — JNI Design Overview, Exception Handling](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): list of JNI functions permitted while an exception is pending.
- [Oracle Java SE 17 — JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `ExceptionCheck`, `ExceptionOccurred`, `ExceptionDescribe`, `ExceptionClear`, Release families, local/global refs, local frames, and monitors.
- [Oracle Java SE 17 — JNI Invocation API](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): attach/detach lifecycle of native threads.
- [Android NDK — JNI tips, Exceptions](https://developer.android.com/ndk/guides/jni-tips): practical guidance on restricting JNI calls while an exception is pending and permitted cleanup operations.

## Takeaways

**While a Java exception is pending, you must not call JNI arbitrarily.** The standard handling path is: **check for error -> release buffers / delete references / exit monitors or local frames using permitted APIs -> return without clearing**, so the Java caller receives the exact original throwable.

Remember the clear distinctions:

- `ExceptionCheck` / `ExceptionOccurred`: **observe, do not clear**.
- `ExceptionClear`: **clear intentionally**.
- `ExceptionDescribe`: **print diagnostics and simultaneously clear the pending exception**.
- `Release...` and `Delete...Ref`: **clean up validly acquired resources**; not a way to create new resources or continue Java logic.
- `PopLocalFrame`: cleans up local references, **does not replace** string/array Release or native resource cleanup.

In C, track ownership clearly with pointers/references initialized to `NULL` and a single `cleanup` label. That is a simple, review-friendly way to handle JNI exceptions without losing the original error or leaking resources.
