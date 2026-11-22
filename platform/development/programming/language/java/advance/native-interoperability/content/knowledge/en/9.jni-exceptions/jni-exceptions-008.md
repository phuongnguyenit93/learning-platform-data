# Guaranteeing Resource Release on Every Error Branch Using Cleanup Constructs or RAII in JNI

Java code and native C/C++ code have two different error-management mechanisms. Java has exceptions, and exiting a `try` block can trigger `finally`/`try-with-resources`. When JNI invokes a Java method that throws an exception, the JVM records a **pending Java exception on the thread**, but that **does not automatically jump out of the currently running C/C++ function frames**. Native code continues at the next instruction until it actively checks, cleans up, and returns control to Java.

This is why JNI commonly encounters bugs such as: calling `GetStringUTFChars` successfully but exiting early without calling `ReleaseStringUTFChars`; acquiring `GetByteArrayElements` and forgetting `ReleaseByteArrayElements` when a Java callback throws an error; or leaving a native heap allocation/FILE handle/mutex behind on one of many `return` branches.

**Core principle:** every native resource must have an **owner** and a deterministic cleanup operation. In C, consolidate exit paths into a single `cleanup` block (typically using `goto cleanup`). In C++, use **RAII** (*Resource Acquisition Is Initialization*): an object owns the resource and its destructor automatically releases it when leaving scope, including via `return` or when catching a C++ exception at the appropriate layer. Both approaches must respect the **list of JNI operations permitted while a Java exception is pending**.

## 1. What Actually Happens When a Java Callback Throws an Exception?

```text
Java main()
   |
   +--> calls native process(...)
             |
             +--> GetStringUTFChars(...)     [holding lease 1]
             +--> GetByteArrayElements(...)  [holding lease 2]
             +--> malloc(...)                [holding native heap]
             |
             +--> CallStaticVoidMethod(...)  // Java callback throws an error
             |       |
             |       +--> Java: throw new IllegalStateException(...)
             |       +--> JNI thread has a pending Java exception
             |       +--> C/C++ returns to the LINE IMMEDIATELY AFTER CallStaticVoidMethod
             |
             +--> C: goto cleanup
             |       or
             +--> C++: return so RAII destructors execute
             |
             +--> free(native heap)
             +--> ReleaseByteArrayElements(...)
             +--> ReleaseStringUTFChars(...)
             |
             +--> return to JVM
   |
   +--> Java catch (IllegalStateException e) handles the error
```

If native code skips `ExceptionCheck` after `CallStaticVoidMethod`, it may continue performing inappropriate work while an exception is still pending. More dangerously, many JNI functions **are not allowed to be called while an exception is pending**. The JVM may warn, report an error, or crash when JNI checking is enabled.

Distinguish the three mechanisms:

| Mechanism | What triggers it? | Does it automatically release JNI leases? |
| --- | --- | --- |
| Java `throw` from a method called by native code via JNI | Sets the pending Java exception state on the current native thread | **No**. C/C++ must continue cleanup actively |
| C `goto cleanup` | Transfers control to the cleanup label within the same function | Yes, **if** the cleanup label completely frees each allocated resource |
| C++ RAII destructor | Scope ends via `return` or proper C++ stack unwinding | Yes, for **resources actually owned by RAII wrappers** |

A Java exception is **not** a C++ `throw`. C++ `try/catch` does not automatically catch a pending Java `IllegalStateException`, and a Java exception **does not automatically trigger C++ stack unwinding**. RAII still helps if native code **actively returns (`return`) or handles errors with an internal C++ exception**, because at that point the C++ scope ends according to the language mechanism.

## 2. Classifying Owners and Acquire/Release Pairs

Before writing a JNI method, list each resource it may hold:

| Resource allocation/acquisition | Who manages the resource? | Release operation | Notes on error branches |
| --- | --- | --- | --- |
| `GetStringUTFChars` | JVM manages the buffer/lease | `ReleaseStringUTFChars` with the same `jstring` and pointer | Call even when `isCopy == JNI_FALSE` |
| `GetStringChars` | JVM manages `jchar *`/lease | `ReleaseStringChars` | Do not use `free` or swap with ReleaseUTF |
| `Get<PrimitiveType>ArrayElements` | JVM manages the view/copy of the Java primitive array | `Release<PrimitiveType>ArrayElements` | Modes `0`/`JNI_ABORT`/`JNI_COMMIT` have different meanings |
| `GetPrimitiveArrayCritical` | JVM may pin/copy the array in a critical section | `ReleasePrimitiveArrayCritical` | Critical section must be very short; do not make arbitrary JNI calls or block |
| `GetStringCritical` | JVM may pin/copy the UTF-16 string | `ReleaseStringCritical` | Do not use `ReleaseStringChars` instead |
| `NewGlobalRef` | JNI global reference | `DeleteGlobalRef` | Must be cleaned up according to the designed lifetime |
| `NewLocalRef`, `NewStringUTF`, `FindClass` creating local refs | JNI local reference | `DeleteLocalRef` or cleaned up when the frame ends | In long loops, clean up early; a local ref is not a string lease |
| `malloc` / `calloc` | Native heap | `free` | Do not pass a JVM-provided pointer to `free` |
| `new`/`new[]` in C++ | Native heap / C++ objects | `delete`/`delete[]`, preferably via smart pointer/container | Do not let C++ exceptions cross the JNI boundary |
| `fopen`/file descriptor/socket | C runtime or OS | `fclose`/`close`/OS-appropriate close | May need cleanup even when a JNI exception is pending |
| `MonitorEnter` | Java monitor ownership | `MonitorExit` | Must guarantee enter/exit pairing; watch out for errors during cleanup |
| Native mutex | Native synchronization | Unlock and destroy according to owner | Do not hold a lock across an uncontrolled Java callback |

**Do not confuse owners:** a `jstring` local reference and the pointer returned from `GetStringUTFChars` are **two different types of resources**. `DeleteLocalRef` does not replace `ReleaseStringUTFChars`. `ReleaseStringUTFChars` does not delete a global reference. `JNIEnv *` belongs to a thread and is not a pointer to `free` or cache for use on another thread.

## 3. Special Rule: Which JNI Operations Can Be Used While an Exception Is Pending?

According to the *JNI Specification, Design Overview*, once a JNI thread has a pending exception, generally only operations for **checking/handling exceptions and cleanup** are permitted before returning to Java or before intentionally clearing the exception. The relevant group in this article:

- `ExceptionCheck`, `ExceptionOccurred`, `ExceptionClear`, `ExceptionDescribe`.
- `ReleaseStringChars`, `ReleaseStringUTFChars`, `ReleaseStringCritical`.
- `Release<PrimitiveType>ArrayElements` and `ReleasePrimitiveArrayCritical`.
- `DeleteLocalRef`, `DeleteGlobalRef`, `DeleteWeakGlobalRef`.
- `MonitorExit`, `PushLocalFrame`, `PopLocalFrame`, and a few JVM/thread operations specified for this case.

**You must not freely call** `FindClass`, `NewStringUTF`, `CallObjectMethod`, `GetMethodID`, or `NewObject` while an exception is still pending. `ExceptionCheck` only checks whether a pending exception exists; it **does not** clear the error. `ExceptionDescribe` is for diagnostics and may **clear** the pending exception as a side effect, so do not insert it indiscriminately in production when you want to propagate the original error back to Java.

Incorrect example:

```c
(*env)->CallStaticVoidMethod(env, clazz, callback);
if ((*env)->ExceptionCheck(env)) {
    /* WRONG: exception is still pending, yet FindClass is called. */
    jclass ex = (*env)->FindClass(env, "java/lang/RuntimeException");
    /* ... */
}
```

The simplest option if a Java callback has already thrown an error: **do not create a new exception**, just release valid native resources and `return`; when the native frame ends, Java sees the pending exception and catches/handles it on the Java side.

If you genuinely need to **translate/convert an exception**, there must be an explicit error contract: hold the original `jthrowable` via a valid reference, call `ExceptionClear` intentionally, perform other JNI operations once no exception is pending, and decide which new Java exception will be thrown. This is not the default behavior of a cleanup mechanism. For resources that can fail when closing (files, sockets, monitors), you need a policy to preserve the initial error and record cleanup errors separately; avoid accidentally masking the original Java exception.

## 4. C: A Single `cleanup` Path Instead of Multiple `return` Statements

C does not have scope-based RAII destructors like C++. The standard pattern is to **initialize every handle to `NULL`**, acquire step by step, `goto cleanup` on failure, and at the end of the function release only the resources **that were successfully acquired**, in the reverse order of acquisition.

```c
/* ILLUSTRATIVE PATTERN, inside a JNI function with a valid env.
 * 'text' is jstring, 'data' is jbyteArray.
 * Input variables have already been checked for non-NULL earlier.
 */
const char *utf = NULL;
jbyte *bytes = NULL;
unsigned char *scratch = NULL;
jint result = 0;

utf = (*env)->GetStringUTFChars(env, text, NULL);
if (utf == NULL) {
    goto cleanup;
}

bytes = (*env)->GetByteArrayElements(env, data, NULL);
if (bytes == NULL) {
    goto cleanup;
}

/* malloc only allocates a native buffer (different from a JNI lease). */
scratch = (unsigned char *)malloc(128);
if (scratch == NULL) {
    /* Only create a new Java exception when no exception is pending.
     * See the throw_if_no_pending helper in the runnable example.
     */
    goto cleanup;
}

/* A Java callback may be called here; the callback may throw an error. */
(*env)->CallStaticVoidMethod(env, clazz, method);
if ((*env)->ExceptionCheck(env)) {
    goto cleanup;
}

result = 42;

cleanup:
free(scratch); /* free(NULL) is safe in C. */
if (bytes != NULL) {
    (*env)->ReleaseByteArrayElements(env, data, bytes, JNI_ABORT);
}
if (utf != NULL) {
    (*env)->ReleaseStringUTFChars(env, text, utf);
}
return result;
```

This is a **structural pattern**, not a standalone function: `clazz`, `method`, and the input values must be defined. The full example in section 7 will include an exception-checking helper and the flow for creating a Java exception on allocation failure.

Why place `cleanup` at the end? If there are 6 resources and 8 failure points, writing `return` immediately after each error makes it easy for some branches to forget releasing a resource. A single cleanup label lets the reader verify **in one place** every resource that needs to be released.

**Never `Release` a pointer that was not successfully acquired via Get.** `NULL` indicates there is no valid lease yet. Once `Release` has been called, treat the pointer as **invalid**; if complex code needs to continue, reset the variable to `NULL` so it is not accidentally released a second time.

### Pattern for Controlling Exceptions When Throwing a New Error

```c
/* C: helper used when there is no pending exception.
 * Only use where it has been determined that a new Java error must be reported.
 */
static void throw_if_no_pending(JNIEnv *env,
                                const char *class_name,
                                const char *message) {
    if ((*env)->ExceptionCheck(env)) {
        return; /* do not mask the original error */
    }

    jclass type = (*env)->FindClass(env, class_name);
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
        (*env)->DeleteLocalRef(env, type);
    }
}
```

If `FindClass` fails, it may leave a new exception pending; the helper does not attempt to create another exception. `DeleteLocalRef` in the `type != NULL` branch is allowed when an exception is pending, so it is safe after `ThrowNew`. In C++, the equivalent version uses `env->...` syntax.

### Typical Design Mistake in C

```c
const char *utf = (*env)->GetStringUTFChars(env, text, NULL);
if (utf == NULL) return 0;

jbyte *bytes = (*env)->GetByteArrayElements(env, data, NULL);
if (bytes == NULL) {
    return 0; /* WRONG: forgot ReleaseStringUTFChars(env,text,utf) */
}

(*env)->CallStaticVoidMethod(env, clazz, method);
if ((*env)->ExceptionCheck(env)) {
    return 0; /* WRONG: forgot to Release both bytes and utf */
}
```

The consequence of the two `return` statements above is a **resource leak or holding JVM memory unnecessarily**. In a real program, the cleanup path must both return the right value/error and preserve the original Java exception if one already exists; do not just add a `free` line on the success branch and consider it done.

## 5. C++: RAII Managing Lifetime via Destructors

In C++, RAII places `JNIEnv *`, the owning JNI object, and the borrowed pointer into an object with a destructor. The constructor or factory performs Acquire; the destructor performs Release **once** when the scope ends. Here is a condensed example:

```cpp
class UtfCharsLease {
    JNIEnv *env_;
    jstring source_;
    const char *ptr_;

public:
    UtfCharsLease(JNIEnv *env, jstring source)
        : env_(env), source_(source),
          ptr_(env->GetStringUTFChars(source, nullptr)) {}

    ~UtfCharsLease() noexcept {
        if (ptr_ != nullptr) {
            env_->ReleaseStringUTFChars(source_, ptr_);
        }
    }

    const char *get() const noexcept { return ptr_; }

    UtfCharsLease(const UtfCharsLease &) = delete;
    UtfCharsLease &operator=(const UtfCharsLease &) = delete;
};
```

This is an **illustrative class** that requires `jni.h` and a C++ environment, not a standalone program. When used:

```cpp
UtfCharsLease utf(env, text);
if (utf.get() == nullptr) {
    return 0;
}

/* If the code returns here, the destructor will call ReleaseStringUTFChars. */
```

Two important safeguards:

1. **A `noexcept` destructor**, which does not throw C++ exceptions and only performs cleanup compatible with a pending Java exception state. `ReleaseStringUTFChars` is in the list of operations permitted when an exception is pending.
2. **Disallow copying** the owner object: copying a pointer + owner easily causes two destructors to Release **the same resource** (*double release*). When move semantics are needed, true ownership transfer must be implemented by resetting the old owner to an empty state; this example keeps it simple by deleting copy operations.

RAII also applies to the native heap: `std::unique_ptr<unsigned char[]>` automatically uses `delete[]` via ownership, and `std::vector` manages vector memory. For JNI local references, you can create a wrapper and call `DeleteLocalRef`, but you must clearly account for the local/global distinction, the lifetime of `JNIEnv*`, and thread rules. Do not store a wrapper holding `JNIEnv *` across another thread or beyond the valid duration of the native call.

**Note:** C++ destructors run when C++ code leaves scope. A Java callback throwing a Java exception **does not immediately trigger destructors by itself**. The native method must check `ExceptionCheck` (or the JNI result), and then `return` so RAII cleans up. Do not rely on `catch (std::exception&)` to catch a Java exception.

## 6. Designing a Runnable Example: Two Variants, Same Problem

We create a `NativeCleanupDemo` class with two native methods:

- `processC` using C and a `cleanup:` label.
- `processCpp` using C++ and RAII wrappers.

Both take `String text`, `byte[] payload`, and `boolean fail`. They acquire two JNI resources (`GetStringUTFChars` and `GetByteArrayElements`) along with a native heap buffer, and then:

- If `fail == false`, compute the sum of the unsigned values of the **modified UTF-8 bytes** of `text` and the bytes in `payload`.
- If `fail == true`, invoke a **Java static callback that intentionally throws `IllegalStateException`** after all three resources have been allocated; both versions must release the resources and return to Java so the exception propagates.
- Java calls the method again after catching the exception to demonstrate that the native method still works. This is only an **observation of behavior**, not a leak measurement or proof that no resources remain pinned on every JVM.

The input in the example is limited to at most **1024 UTF-16 units** and **1024 array elements**. This limit ensures `GetStringUTFLength` of type `jsize` on JDK 17 does not overflow and the `jint` sum does not overflow in the demo: each UTF-16 unit produces at most three modified UTF-8 bytes; the total number of bytes summed is at most 4096, with each byte at most 255.

### File 1 — `NativeCleanupDemo.java`

```java
public final class NativeCleanupDemo {
    static {
        System.loadLibrary("jnicleanupc");
        System.loadLibrary("jnicleanupraii");
    }

    private static native int processC(
            String text, byte[] payload, boolean fail);

    private static native int processCpp(
            String text, byte[] payload, boolean fail);

    // C/C++ calls this method back into Java when fail=true.
    private static void failFromJava() {
        throw new IllegalStateException("callback failure");
    }

    public static void main(String[] args) {
        byte[] bytes = {1, 2, 3};

        System.out.println("C sum="
                + processC("AB", bytes, false));
        try {
            processC("AB", bytes, true);
            System.out.println("C unexpected success");
        } catch (IllegalStateException e) {
            System.out.println("C failure=" + e.getMessage());
        }
        System.out.println("C after failure="
                + processC("AB", bytes, false));

        System.out.println("C++ sum="
                + processCpp("AB", bytes, false));
        try {
            processCpp("AB", bytes, true);
            System.out.println("C++ unexpected success");
        } catch (IllegalStateException e) {
            System.out.println("C++ failure=" + e.getMessage());
        }
        System.out.println("C++ after failure="
                + processCpp("AB", bytes, false));
    }
}
```

The JNI generated header (`javac -h`) declares the two native functions returning `jint`; `String` is `jstring`, `byte[]` is `jbyteArray`, and `boolean` is `jboolean`. The Java methods are marked `static`, so the second JNI argument is `jclass`, not a `jobject` receiver.

### File 2 — `jni_cleanup_c.c` (C11, cleanup via `goto cleanup`)

```c
#include "NativeCleanupDemo.h"  /* generated by javac -h, includes jni.h */
#include <stddef.h>
#include <stdlib.h>

static void throw_if_no_pending(JNIEnv *env,
                                const char *class_name,
                                const char *message) {
    if ((*env)->ExceptionCheck(env)) {
        return;
    }
    jclass type = (*env)->FindClass(env, class_name);
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
        (*env)->DeleteLocalRef(env, type);
    }
}

JNIEXPORT jint JNICALL
Java_NativeCleanupDemo_processC(JNIEnv *env, jclass clazz,
                                jstring text, jbyteArray payload,
                                jboolean fail) {
    const char *utf = NULL;            /* JVM lease */
    jbyte *elements = NULL;           /* JVM lease */
    unsigned char *scratch = NULL;    /* Native heap */
    jint sum = 0;
    jsize array_len = 0;
    jsize utf_len = 0;

    if (text == NULL || payload == NULL) {
        throw_if_no_pending(env, "java/lang/NullPointerException",
                            "text or payload is null");
        goto cleanup;
    }

    jsize units = (*env)->GetStringLength(env, text);
    array_len = (*env)->GetArrayLength(env, payload);
    if ((*env)->ExceptionCheck(env)) {
        goto cleanup;
    }
    if (units > 1024 || array_len > 1024) {
        throw_if_no_pending(env, "java/lang/IllegalArgumentException",
                            "demo input too large");
        goto cleanup;
    }
    utf_len = (*env)->GetStringUTFLength(env, text);
    if ((*env)->ExceptionCheck(env)) {
        goto cleanup;
    }

    utf = (*env)->GetStringUTFChars(env, text, NULL);
    if (utf == NULL) {
        throw_if_no_pending(env, "java/lang/OutOfMemoryError",
                            "GetStringUTFChars failed");
        goto cleanup;
    }

    elements = (*env)->GetByteArrayElements(env, payload, NULL);
    if (elements == NULL) {
        throw_if_no_pending(env, "java/lang/OutOfMemoryError",
                            "GetByteArrayElements failed");
        goto cleanup;
    }

    size_t scratch_len = (size_t)utf_len + (size_t)array_len;
    scratch = (unsigned char *)malloc(
            scratch_len > 0 ? scratch_len : 1);
    if (scratch == NULL) {
        throw_if_no_pending(env, "java/lang/OutOfMemoryError",
                            "malloc failed");
        goto cleanup;
    }

    if (fail != JNI_FALSE) {
        jmethodID callback = (*env)->GetStaticMethodID(
                env, clazz, "failFromJava", "()V");
        if (callback == NULL) {
            goto cleanup;  /* lookup failure, an exception may be pending */
        }
        (*env)->CallStaticVoidMethod(env, clazz, callback);
        /* failFromJava() throws Java IllegalStateException. */
        goto cleanup;     /* do not call disallowed JNI functions */
    }

    for (jsize i = 0; i < utf_len; ++i) {
        unsigned char value = (unsigned char)utf[i];
        scratch[i] = value;
        sum += (jint)value;
    }
    for (jsize i = 0; i < array_len; ++i) {
        unsigned char value = (unsigned char)elements[i];
        scratch[utf_len + i] = value;
        sum += (jint)value;
    }

cleanup:
    /* Clean up in reverse acquire order; valid even when an exception is pending. */
    free(scratch);  /* C allows free(NULL). */

    if (elements != NULL) {
        (*env)->ReleaseByteArrayElements(
                env, payload, elements, JNI_ABORT);
        elements = NULL;
    }
    if (utf != NULL) {
        (*env)->ReleaseStringUTFChars(env, text, utf);
        utf = NULL;
    }
    return sum;
}
```

`scratch` is allocated with `malloc`, so it is freed with `free`; the two pointers `utf` and `elements` are provided by the JVM, so they must use the **exact JNI Release functions**. `JNI_ABORT` indicates **not to copy back** any changes to the byte array because the code only reads the data; this is an actual release, unlike `JNI_COMMIT`.

Error branches during and after acquisition all pass through `cleanup`:

| Stop point | What is already owned? | What does `cleanup` do? |
| --- | --- | --- |
| Null input / exceeds limit | No lease/heap yet | `free(NULL)`, skips both Releases |
| `GetStringUTFChars` fails | No valid `utf` | Skips string Release; reports error if none pending |
| `GetByteArrayElements` fails | `utf` | `ReleaseStringUTFChars` |
| `malloc` fails | `utf` + `elements` | Release array, Release string |
| `GetStaticMethodID` fails | All three resources | Free heap, Release array, Release string |
| Java callback throws exception | All three resources, with a pending Java exception | Performs only valid cleanup then returns; Java sees original error |
| Success | All three resources | Full cleanup then returns `sum` |

Whether an error occurs after the first, second, or third acquire step, the exit path remains uniform. Note that `GetStaticMethodID` can cause a lookup error; if it fails, you must not call the callback or disallowed JNI calls while an exception is pending.

### File 3 — `jni_cleanup_raii.cpp` (C++17, cleanup via RAII)

```cpp
#include "NativeCleanupDemo.h"
#include <cstddef>
#include <memory>
#include <new>

namespace {

void throwIfNoPending(JNIEnv *env, const char *className,
                      const char *message) {
    if (env->ExceptionCheck()) {
        return;
    }
    jclass type = env->FindClass(className);
    if (type != nullptr) {
        env->ThrowNew(type, message);
        env->DeleteLocalRef(type);
    }
}

/* Do not copy owner to avoid calling ReleaseStringUTFChars twice. */
class UtfCharsLease final {
    JNIEnv *env_;
    jstring text_;
    const char *ptr_;

public:
    UtfCharsLease(JNIEnv *env, jstring text) noexcept
        : env_(env), text_(text),
          ptr_(env->GetStringUTFChars(text, nullptr)) {}

    ~UtfCharsLease() noexcept {
        if (ptr_ != nullptr) {
            env_->ReleaseStringUTFChars(text_, ptr_);
        }
    }

    const char *get() const noexcept { return ptr_; }

    UtfCharsLease(const UtfCharsLease &) = delete;
    UtfCharsLease &operator=(const UtfCharsLease &) = delete;
};

/* Read-only array access, Release with JNI_ABORT even when an exception is pending. */
class ByteArrayLease final {
    JNIEnv *env_;
    jbyteArray array_;
    jbyte *ptr_;

public:
    ByteArrayLease(JNIEnv *env, jbyteArray array) noexcept
        : env_(env), array_(array),
          ptr_(env->GetByteArrayElements(array, nullptr)) {}

    ~ByteArrayLease() noexcept {
        if (ptr_ != nullptr) {
            env_->ReleaseByteArrayElements(array_, ptr_, JNI_ABORT);
        }
    }

    const jbyte *get() const noexcept { return ptr_; }

    ByteArrayLease(const ByteArrayLease &) = delete;
    ByteArrayLease &operator=(const ByteArrayLease &) = delete;
};

}  // namespace

extern "C" JNIEXPORT jint JNICALL
Java_NativeCleanupDemo_processCpp(JNIEnv *env, jclass clazz,
                                  jstring text, jbyteArray payload,
                                  jboolean fail) {
    if (text == nullptr || payload == nullptr) {
        throwIfNoPending(env, "java/lang/NullPointerException",
                         "text or payload is null");
        return 0;
    }

    const jsize units = env->GetStringLength(text);
    const jsize arrayLen = env->GetArrayLength(payload);
    if (env->ExceptionCheck()) {
        return 0;
    }
    if (units > 1024 || arrayLen > 1024) {
        throwIfNoPending(env, "java/lang/IllegalArgumentException",
                         "demo input too large");
        return 0;
    }
    const jsize utfLen = env->GetStringUTFLength(text);
    if (env->ExceptionCheck()) {
        return 0;
    }

    UtfCharsLease utf(env, text);
    if (utf.get() == nullptr) {
        throwIfNoPending(env, "java/lang/OutOfMemoryError",
                         "GetStringUTFChars failed");
        return 0;
    }

    ByteArrayLease bytes(env, payload);
    if (bytes.get() == nullptr) {
        throwIfNoPending(env, "java/lang/OutOfMemoryError",
                         "GetByteArrayElements failed");
        return 0;  // ~utf() will Release the UTF pointer.
    }

    const std::size_t count = static_cast<std::size_t>(utfLen)
                            + static_cast<std::size_t>(arrayLen);
    std::unique_ptr<unsigned char[]> scratch(
            new (std::nothrow) unsigned char[count > 0 ? count : 1]);
    if (!scratch) {
        throwIfNoPending(env, "java/lang/OutOfMemoryError",
                         "native allocation failed");
        return 0;  // ~bytes() and ~utf() still run.
    }

    if (fail != JNI_FALSE) {
        jmethodID callback = env->GetStaticMethodID(
                clazz, "failFromJava", "()V");
        if (callback == nullptr) {
            return 0;  // RAII cleans up even if JNI lookup fails.
        }
        env->CallStaticVoidMethod(clazz, callback);
        return 0;      // Do not clear exception; destructors still run.
    }

    jint sum = 0;
    for (jsize i = 0; i < utfLen; ++i) {
        const unsigned char value =
                static_cast<unsigned char>(utf.get()[i]);
        scratch[i] = value;
        sum += static_cast<jint>(value);
    }
    for (jsize i = 0; i < arrayLen; ++i) {
        const unsigned char value =
                static_cast<unsigned char>(bytes.get()[i]);
        scratch[utfLen + i] = value;
        sum += static_cast<jint>(value);
    }
    return sum;
}
```

**Why doesn't the C++ code need `goto cleanup`?** Upon returning, C++ automatically destroys variables in the reverse order of construction: `scratch` frees the `new[]` buffer, `bytes` calls `ReleaseByteArrayElements(...JNI_ABORT)`, and then `utf` calls `ReleaseStringUTFChars`. The JNI wrapper destructors use operations **permitted when an exception is pending** and are marked `noexcept`.

In this snippet, `std::nothrow` prevents a normal `new[]` allocation failure from turning into a C++ `std::bad_alloc` crossing the JNI boundary; the code creates an `OutOfMemoryError` itself when appropriate. Real-world C++ code may have other functions/libraries that throw `std::exception`; you must catch them **inside** the JNI entry point, release resources via RAII, and convert them into a Java exception when no exception is pending. Never let a C++ exception cross the JVM boundary.

**Do not let a wrapper outlive the scope of `JNIEnv *`:** the owners `UtfCharsLease`/`ByteArrayLease` only live within that exact native call/thread. The rule that thread A's `JNIEnv *` is invalid for use on thread B is a JNI rule independent of RAII.

## 7. Compiling and Running on Linux (JDK 17+, C11, C++17)

The following commands run in a directory containing the three files described. `JAVA_HOME` must point to a **JDK with JNI headers**; `cc` and `c++` must produce binaries compatible with the architecture of the Java process. The first step generates `NativeCleanupDemo.h`:

```bash
javac -encoding UTF-8 -h . NativeCleanupDemo.java

cc -std=c11 -Wall -Wextra -shared -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libjnicleanupc.so jni_cleanup_c.c

c++ -std=c++17 -Wall -Wextra -shared -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libjnicleanupraii.so jni_cleanup_raii.cpp

java -Djava.library.path=. NativeCleanupDemo
```

On Windows/macOS, filenames and shared-library build steps differ; the example is **runnable on Linux with a compatible toolchain/JDK**, without claiming the same compile commands apply to every OS. `-Djava.library.path=.` is a JVM argument placed **before** the main class.

**Expected stdout:**

```text
C sum=137
C failure=callback failure
C after failure=137
C++ sum=137
C++ failure=callback failure
C++ after failure=137
```

Explanation:

- `"AB"` has two ASCII bytes `65` and `66` in modified UTF-8; `payload` has `1, 2, 3`. Total `65 + 66 + 1 + 2 + 3 = 137`.
- With `fail == true`, native code has already acquired the resources and then calls `failFromJava()`. The callback throws `IllegalStateException("callback failure")`; native code cleans up the leases and buffer, **preserves the pending exception**, and then Java's `catch` block prints the message.
- The subsequent call runs from Java after the previous exception has been handled by Java, so it can return `137` again. This is not an independent proof that there are no leaks in a large program; the cleanup guarantee is established by the logic in the illustrated branches.

You can also run:

```bash
java -Xcheck:jni -Djava.library.path=. NativeCleanupDemo
```

`-Xcheck:jni` on supporting JVMs helps detect many JNI violations, such as calling disallowed APIs while an exception is pending or misusing references/critical regions. It **does not** replace native testing with AddressSanitizer, Valgrind, or an appropriate leak-detection tool.

## 8. Other Cases: Array Writes, `JNI_COMMIT`, and `JNI_ABORT`

`Release<PrimitiveType>ArrayElements` takes a `mode` argument and often causes confusion in cleanup code:

| Mode | Meaning | Is the resource actually finished being released? |
| --- | --- | --- |
| `0` | Commit changes that need copying back, then free/unpin the elements region | **Yes** |
| `JNI_ABORT` | Do not copy back the copy; release the elements region; suitable for read-only or discarding changes | **Yes** |
| `JNI_COMMIT` | Copy back changes but **retain** access/the elements buffer | **No**; requires a final Release with `0` or `JNI_ABORT` per the contract |

In the example, the byte array is read-only so `JNI_ABORT` is used. For code that modifies a Java array and wants changes applied, choose `0` on the final Release (or combine `JNI_COMMIT` followed by a final Release when needed). Choosing `JNI_ABORT` after modifying the buffer in order to "discard changes" does not guarantee restoring data if the JVM returned a direct pointer to memory; algorithm design should avoid mutating in place when rollback is required.

Common mistake:

```c
jint *elems = (*env)->GetIntArrayElements(env, array, NULL);
if (elems != NULL) {
    /* ... read/modify data ... */
    (*env)->ReleaseIntArrayElements(env, array, elems, JNI_COMMIT);
    /* WRONG: assuming JNI_COMMIT has completely released it and returning. */
}
```

An appropriate final Release (for example, `0`) is required to end access. When writing an RAII wrapper for a primitive array, you must **document its purpose** clearly: a read-only wrapper can always use `JNI_ABORT`, whereas a mutating wrapper should use `0` if changes are meant to be saved. Do not hide an inappropriate commit mode inside a generic destructor used for every situation.

## 9. Critical Regions, Local References, and Native Locks

### `GetPrimitiveArrayCritical` / `GetStringCritical`

The critical APIs may allow the JVM to pin memory to avoid copying, with a strict restriction: **you must not hold a critical region across blocking operations or arbitrary JNI calls**. Holding a critical pointer during `CallStaticVoidMethod` is an example to avoid. Read/transfer data briefly, Release with the matching `ReleasePrimitiveArrayCritical` or `ReleaseStringCritical`, and **only then** invoke the Java callback.

RAII for a critical region can help guarantee Release, but it **does not remove the prohibition against blocking/callbacks while the scope remains open**. The design should separate scopes:

```cpp
/* Illustrative idea, not a standalone program. */
{
    CriticalArrayLease lease(env, array); // wrapper must be implemented yourself
    if (!lease.ok()) {
        return; // destructor handles it if already acquired
    }
    // Only a short native operation, no blocking/no arbitrary JNI calls.
} // ReleasePrimitiveArrayCritical here.

/* Only after leaving the critical section, call the Java callback. */
```

### Local References

`jobject`, `jstring`, and `jclass` from many JNI APIs are **local references**. They are normally cleaned up by the JVM when the native frame returns to Java, but in loops processing thousands of elements, you must call `DeleteLocalRef` early or manage a local frame. `DeleteLocalRef` is allowed when an exception is pending. An RAII `LocalRef<T>` can hold `JNIEnv *` and the reference; its destructor calls `DeleteLocalRef` if non-`nullptr`, and copying is deleted to prevent double-delete.

Note that `PopLocalFrame(result)` has a contract that allows preserving one local reference across the frame, **unlike** simply deleting all references. Do not return a pointer from `GetStringUTFChars` outside the native frame after Release; do not use a local `jobject` after its owning native frame becomes invalid. `jmethodID`/`jfieldID` are opaque IDs, **not** local references to pass to `DeleteLocalRef`.

### Native Heap, File Handles, and Locks

Standard C++ RAII can be combined:

- `std::unique_ptr<T>` or `std::unique_ptr<T, Deleter>` for native allocations/custom handles.
- `std::vector<T>`/`std::string` for C++ memory instead of manual `malloc`/`free`, provided C++ exceptions are controlled.
- `std::unique_ptr<FILE, FileCloser>` for `FILE *` if a deleter calling `fclose` is designed.
- `std::lock_guard<std::mutex>` or `std::unique_lock<std::mutex>` for C++ mutexes.

Not every destructor is completely "error-free": `fclose`, flushing, releasing an OS resource, or `MonitorExit` can have error conditions. The rule is **never throw a C++ exception from a destructor running while handling another error**; if cleanup fails, record it according to the logging/error-propagation contract and preserve the initial Java exception whenever possible. Avoid holding a native lock across a Java callback if the callback can re-enter native code, block, or cause a deadlock.

## 10. Properly Converting C++ Errors to Java

C++ code can throw `std::bad_alloc`, `std::runtime_error`, or custom exceptions. They **must not** accidentally escape across the JNI entry boundary and be expected to behave as a Java `Exception`. A C++ boundary must catch C++ exceptions at the outer layer and convert them into a corresponding Java error when appropriate:

```cpp
/* Conceptual pattern, not a complete function:
 * runNativeWork may throw a C++ exception; no pending Java exception.
 * RAII owners inside runNativeWork will be cleaned up as the stack unwinds.
 */
try {
    runNativeWork(env);
} catch (const std::bad_alloc &) {
    if (!env->ExceptionCheck()) {
        // Find class and ThrowNew OutOfMemoryError; see helper in the C++ example.
        throwIfNoPending(env, "java/lang/OutOfMemoryError",
                         "native allocation failed");
    }
} catch (const std::exception &) {
    if (!env->ExceptionCheck()) {
        throwIfNoPending(env, "java/lang/RuntimeException",
                         "native operation failed");
    }
}
```

This is an **illustrative snippet** requiring `#include <exception>` and appropriate C++ helpers/logic. Do not use `ExceptionClear` just so you can throw another exception; replacing the original error cause must be a deliberate decision. If native code calls Java and produces a pending exception, you should **clean up and return** as in the runnable example, rather than trying to convert it into a C++ exception to trigger RAII.

A subtle note: **a pending Java exception does not automatically unwind the C++ stack**, so C++ code should not keep calling `env->Call...` or JNI functions outside the safe list and "expect destructors to run". You must check the state and transfer control via `return`/C++ scopes so destructors run at the right time.

## 11. Testing Error Branches Instead of Only Looking at the Happy Path

The "every error branch" problem requires a test matrix organized by **how many resources have been acquired at that point**. For the three resources `utf`, `elements`, and `scratch` in this article:

| Scenario | Expected result | What to observe |
| --- | --- | --- |
| `text == null` or `payload == null` | Java `NullPointerException` | Do not call JNI Get on a null object; no leases acquired |
| String/array exceeds demo limit | Java `IllegalArgumentException` | Stops before Acquire |
| `GetStringUTFChars` returns no pointer | Java error if appropriate, or JNI pending exception | Do not Release a non-existent pointer |
| `GetByteArrayElements` returns no pointer | Exits JNI boundary with error | `utf` is Released |
| Native allocation fails | Java `OutOfMemoryError` if none pending | Both leases are Released |
| `GetStaticMethodID` fails | Java lookup exception continues | Already-acquired resources are cleaned up |
| Java callback actively throws | Java receives original `IllegalStateException` | Cleans up resources while pending, no unsafe JNI calls |
| Success | Java receives `137` | Resources are also released, not only on error |

The two callback success/failure scenarios can be run using the given code. *Memory allocation failure* scenarios require **fault injection**, mocks, or a controlled native test harness to prove, rather than unreliably trying to exhaust machine RAM. Real-world testing should wrap Acquire steps in wrappers capable of simulating failures and counting each acquire/release pair to detect double-free or missing-release.

On JVMs supporting `-Xcheck:jni`, verify compliance with JNI rules; combine with AddressSanitizer/UndefinedBehaviorSanitizer for C/C++ when possible, leak-detection tools, and Java tests that catch exceptions after each error. A single successful compile/run **does not** prove all exit paths have been exercised. Code review must account for every `return`, `goto`, `throw`, every destructor, and every corresponding release.

### Code Review Checklist Before Shipping JNI to Production

1. **Inventory:** every `Get...`/`NewGlobalRef`/`malloc`/`new`/open/lock call has a defined owner and Release function.
2. **Acquisition:** unallocated pointers are initialized to `NULL`/`nullptr`; ownership is recorded only after Acquire succeeds.
3. **Release:** cleanup only frees owned resources, using the right function, right object, and right thread/lifetime; no double-release.
4. **Order:** when multiple resources depend on each other, typically clean up in reverse acquire order.
5. **Exception:** after a JNI callback or a JNI function that can fail, check the return value/pending exception and stop unsafe execution paths.
6. **Pending-safe:** cleanup code while pending uses only JNI calls specified for that situation; do not call `FindClass`/`NewStringUTF`/method callbacks arbitrarily.
7. **Exception priority:** preserve the original Java exception; if none is pending, convert native errors to Java errors per the contract.
8. **RAII:** `noexcept` destructors, no accidental copying of ownership, do not retain `JNIEnv *` across threads.
9. **Arrays:** choose mode `0`/`JNI_ABORT` according to read-only vs. write; `JNI_COMMIT` does not end the lease.
10. **Critical:** do not hold a critical region across callbacks/blocking sections; Release with the matching `Critical` API.
11. **Validation:** at minimum, have tests for the success branch, throwing callback, null input, and errors before/after acquire; test with native tools if available.

## 12. Self-Check Questions

**Question 1.** Why does `CallStaticVoidMethod` calling a Java method that throws `IllegalStateException` not cause C to automatically jump to `cleanup`?

Because the Java error is recorded as a **pending exception** in the JNI thread; it is not a C `longjmp` or C++ stack unwinding. Native code needs `ExceptionCheck`/result checking per the contract and then actively performs `goto cleanup` or `return`.

**Question 2.** `GetByteArrayElements` fails after `GetStringUTFChars` has already succeeded. What needs to be done?

Do not Release the `NULL` byte pointer; you must call `ReleaseStringUTFChars` for the acquired pointer, while propagating the pending Java error or reporting a new error if none is pending. Both C `goto cleanup` and C++ destructors handle this.

**Question 3.** Why does C++ `UtfCharsLease` delete its copy constructor?

Two objects must not independently own and Release **the same JNI string pointer**. If the raw pointer were copied, both destructors could Release it twice; the wrapper needs unique ownership, or proper move semantics.

**Question 4.** Can `FindClass` be used inside an RAII destructor to create a message while a Java exception is pending?

No. `FindClass` is not in the group of JNI calls permitted to be used arbitrarily while an exception is pending. Destructors should only perform cleanup and be `noexcept`; creating/replacing Java exceptions must be handled outside the destructor mechanism in the appropriate place.

**Question 5.** Is `JNI_COMMIT` enough to finish `GetIntArrayElements`?

No. `JNI_COMMIT` copies back changes but does not completely release access. A final Release with `0` or `JNI_ABORT` is required per the contract. If only reading data, `JNI_ABORT` is usually more appropriate.

**Question 6.** When a Java callback throws an error, does RAII need to call `ExceptionClear` for destructors to run?

No. Destructors use JNI cleanup calls that are **permitted while an exception is pending**; the code only needs to exit the scope for destructors to run. Calling `ExceptionClear` unintentionally will swallow the original Java error.

**Question 7.** If all JNI leases have been cleaned up but a file handle from `fopen` still remains, can cleanup be considered complete?

No. A file handle is a C runtime/OS resource that requires `fclose` or a corresponding RAII wrapper, even if the error originated from a Java callback. The resource inventory must include both JNI and non-JVM resources.

## References

- Oracle JNI Specification — *Java Exceptions, Exception Handling* and the list of JNI functions permitted while a pending exception exists: https://docs.oracle.com/en/java/javase/25/docs/specs/jni/design.html#exception-handling
- Oracle JNI Specification — *JNI Functions*, `ExceptionCheck`/`ExceptionClear`/`ThrowNew`, `ReleaseStringUTFChars`, `Release<PrimitiveType>ArrayElements`, and `MonitorExit`: https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html
- Android NDK — *JNI tips: Exceptions; Local and global references*: https://developer.android.com/ndk/guides/jni-tips
- Oracle Java 17 `javac` — `-h` for generating native headers: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- C++ Core Guidelines — *Resource management (R), RAII, unique ownership*: https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines#S-resource

**Remember:** A Java exception does not automatically clean up C/C++ resources. Build **a clear cleanup path in C** or **RAII ownership in C++**, clean up every acquired resource on **all** exit paths, use only permitted JNI calls while an exception is pending, and preserve the original Java error for the caller to handle.
