# Distinguishing Native Error Codes, Special Return Values, and Java Exceptions

## Objectives

When Java calls C/C++ through the Java Native Interface (JNI), errors can appear at **multiple different layers**. A C library may return a status code such as `0`/`-1`, set `errno`, or use a `NULL` pointer to report failure. Meanwhile, the JVM uses **Java exceptions** (`Throwable`) to report errors to Java code. And the JNI functions themselves can both return a special value and leave an exception in a **pending** state on the current Java thread.

These three mechanisms **are not automatically equivalent to one another**. A C error code does not automatically become an `IOException`; a return value of `-1` is not always an error; and a pending Java exception does not turn into a C `throw` or automatically unwind out of the native stack.

After this lesson, you will be able to:

1. Identify **native error codes**, **sentinel/special return values**, and **Java exceptions** by API contract rather than guessing from a number.
2. Distinguish library error codes from OS `errno`/`GetLastError` and JNI constants `JNI_OK`/`JNI_ERR`.
3. Properly handle `ThrowNew`, `ExceptionCheck`, `ExceptionOccurred`, and `ExceptionClear` in a native method.
4. Deliberately translate error states into appropriate Java exceptions; preserve meaning, message, retryability, and diagnostic metadata.
5. Avoid masking a pending exception, misinterpreting a valid sentinel, or calling arbitrary JNI functions while an exception is pending.
6. Run a Java 17+ ↔ JNI C example with **three independent error flows**: returning a status, converting an error into an exception, and letting an exception from a Java callback pass through JNI.

## 1. Three Result Layers to View Separately

| Mechanism | Where error information is placed | Example | What the caller must know |
| --- | --- | --- | --- |
| **Native error code** (native status code) | In the return value or an output parameter defined by the API | `0` success, `7` invalid argument, `9` service busy | The API's own status table; do not infer status from variable names |
| **Special return value** (sentinel) | A value reserved to indicate a state other than normal success | `-1`, `NULL`, `EOF`, a `NOT_FOUND` enum | Whether the sentinel is outside the valid data domain; whether `errno`/out-parameter must be read |
| **Java exception** | Pending exception state of the Java thread or an exception already received by Java code | `IllegalArgumentException`, `IOException`, `OutOfMemoryError` | Check, clean up resources, propagate/handle, and do not call invalid JNI APIs while pending |

For example, two native functions both return `jint` but carry different meanings:

~~~c
/* Custom status: 0 = OK; positive non-zero = error code. */
jint library_process(const unsigned char *data, size_t length);

/* Data: integer result; -1 is reserved as an error sentinel. */
jint legacy_read_value(void);
~~~

You cannot look at `jint` alone to know how to handle it. The **API contract** is what defines whether returning 0 is a data value or success, and whether `-1` is valid in the data domain.

At the JNI boundary, a `native int read()` method also **has no mechanism to automatically wrap a C status into a Java exception**. If the C implementation simply does `return -1;`, Java receives an `int` equal to -1. A Java `catch` block will not run unless an exception is actually set/thrown.

Conversely, when native code successfully calls `ThrowNew` and then `return 0;`, the Java side **does not see 0 as a normal result**: the JVM handles the pending exception upon returning to Java. The `0` value in C is only to exit a function with return type `jint`, not a success result received by Java.

## 2. Native Status Code: Clear Error Representation, Meaningful Only Within Its API

Many C libraries return status according to a contract like this:

~~~c
typedef enum {
    NATIVE_OK = 0,
    NATIVE_INVALID_ARGUMENT = 7,
    NATIVE_TEMPORARILY_UNAVAILABLE = 9
} NativeStatus;

/* out_value is only written when the function returns NATIVE_OK. */
NativeStatus native_get_number(int request, int *out_value);
~~~

Here:

- `NATIVE_OK` is success; `out_value` is only valid in this branch.
- `NATIVE_INVALID_ARGUMENT` is an input error, which should usually be fixed before retrying.
- `NATIVE_TEMPORARILY_UNAVAILABLE` is a state/resource error; it can be retried if the operation is actually safe to retry.
- The numbers 7 and 9 are chosen **specifically for the example**, and are **not** standard `errno` or JNI constants; do not assume they are `E2BIG`, `EBADF`, or any system error code.

A correct calling pattern:

~~~c
int value = 0;
NativeStatus status = native_get_number(request, &value);
if (status == NATIVE_OK) {
    /* Only here is value a valid result. */
} else {
    /* Handle status; do not use value as success data. */
}
~~~

This is a snippet because `native_get_number` and `request` belong to the library context being studied. The main point: **return status and output payload are two separate channels**. This API supports negative data values, 0, and large numbers without mixing them up with errors.

Other libraries choose an enum, a `{status, value}` struct, negative return codes, or an error-reporting callback. There is no global JNI rule that negative numbers are always errors or 0 is always success.

## 3. Sentinels: `-1`, `NULL`, and `EOF` Easily Cause Confusion

A **sentinel** is a return value reserved to represent "no data", "end reached", "failure", or another special condition. It differs from a status code because many APIs still return **data directly** on success.

For example, Java's `indexOf` returns `-1` when the element is not found:

~~~java
static int indexOf(int[] values, int needle) {
    for (int i = 0; i < values.length; i++) {
        if (values[i] == needle) {
            return i;
        }
    }
    return -1;
}
~~~

`-1` is valid as a sentinel because valid Java array indices are always 0 or greater. But imagine a sensor that can actually measure `-1` degrees, or an algorithm that can return any `int`. Then an `int read()` interface where `-1` is both data and an error creates **an ambiguity that cannot be resolved from a single value**.

Some familiar sentinels:

| API or situation | Typical sentinel | What else to check |
| --- | --- | --- |
| POSIX `read` | `-1` reports error, `0` may report EOF for a positive-length read request | `errno` **when** `read` returns -1; distinguish EOF from error |
| POSIX `open` | `-1` error; a successful file descriptor can be `0` | `errno` on failure; do not treat fd 0 as an error |
| `malloc` | `NULL` indicates allocation failed per `malloc` contract | `NULL` is not a Java exception; `malloc(0)` has implementation-specific behavior |
| C `fgetc` | `EOF` when input ends **or** read error | `feof` / `ferror` to distinguish |
| Java index-finding method | `-1` element not present | Per Java API contract, no automatic exception |
| JNI function that can return `NULL` | Can be a valid result or an error, depending on the function | Check the function specification and check for a pending exception when needed |

From this table it follows: **a sentinel is not enough to state the nature of the error**. `NULL` can mean "the object field is currently null" (`GetObjectField`) rather than an exception. `0` can be a valid file descriptor, a calculation result of zero, or a success status code.

When a sentinel **overlaps the data domain**, use a different API: return status + output parameter; a nullable wrapper with a separate error code; an exception; or a result object/record. Do not guess "the user will definitely never enter this value".

### Standalone runnable Java 17+ example: sentinel ambiguity

Create `SentinelOnly.java`:

~~~java
public final class SentinelOnly {
    static int indexOf(int[] a, int needle) {
        for (int i = 0; i < a.length; ++i) {
            if (a[i] == needle) return i;
        }
        return -1;
    }

    static int valueOrThrow(boolean present, int value) {
        if (!present) {
            throw new IllegalStateException("missing measurement");
        }
        return value;
    }

    public static void main(String[] args) {
        int[] values = {8, 5, 9};
        System.out.println("found=" + indexOf(values, 5));
        System.out.println("not-found=" + indexOf(values, 1));
        System.out.println("real-minus-one=" + valueOrThrow(true, -1));

        try {
            valueOrThrow(false, 0);
        } catch (IllegalStateException ex) {
            System.out.println("missing=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 SentinelOnly.java
java SentinelOnly
~~~

Stdout:

~~~text
found=1
not-found=-1
real-minus-one=-1
missing=missing measurement
~~~

In `indexOf`, -1 cannot be a valid index. In `valueOrThrow`, -1 is **preserved as success data**; the "missing measurement" state is reported via a Java exception.

## 4. `errno` on POSIX: Error Details Accompanying Some Native APIs

On POSIX systems, many system calls/C library functions report errors via a return value such as `-1` and then set `errno` (defined in `<errno.h>`). **Not every C function uses `errno`.** In particular, many pthread functions return the error number directly and do not set `errno`. Each API decides how it reports errors.

POSIX example (illustrative, **not** a standalone program with `main`):

~~~c
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>

/* Success: returns file descriptor >= 0 and caller must close(fd).
   Failure: returns -1, writes captured errno code to *out_error. */
int open_read_only(const char *path, int *out_error) {
    int fd = open(path, O_RDONLY);
    if (fd == -1) {
        int saved = errno;   /* Capture IMMEDIATELY after the failing call. */
        *out_error = saved;
        return -1;
    }
    *out_error = 0;
    return fd;
}
~~~

The example contract requires `path` and `out_error` to be valid pointers. The caller must `close(fd)` on success, and also handle it if closing the file fails. On Windows, native APIs may use `GetLastError`, `HRESULT`, or another mechanism; **do not substitute `errno` for those codes** if the API does not define it that way.

Four rules for `errno`:

1. **Read it only when the API states it is meaningful.** Success does not guarantee `errno == 0`; some functions may modify `errno` even when succeeding.
2. **Capture immediately** (`int saved = errno;`) after the failing call and before calling logging/JNI/allocating/formatting functions; subsequent calls may overwrite it.
3. **Do not assume the same number has the same meaning across all OSes/ABIs.** Compare against macro names like `ENOENT`/`EACCES` on supported platforms; numeric codes are not a portable wire protocol.
4. **`errno` is thread-local** in modern POSIX environments. When native code offloads work to another thread, do not expect the new thread to "read back" the old thread's error; pass the error code in a specific result/context.

Example of how to classify a POSIX error after catching a failure status:

~~~c
int saved_errno = errno;   /* Only valid immediately after an API reports an error. */

if (saved_errno == ENOENT) {
    /* File/path does not exist. */
} else if (saved_errno == EACCES) {
    /* Access denied. */
} else {
    /* Other error; keep the original code for logs/diagnostics. */
}
~~~

The codes above only have meaning under the POSIX contract. When designing a Java API, you can map `ENOENT` to `NoSuchFileException`, `EACCES` to `AccessDeniedException`, or fall back to `IOException` **if the operation is actually file access** and you have all the necessary information. There is no universal table saying "every errno X always equals Java exception Y" for every library and every problem.

### Special case: `-1` can still be success

Some documented APIs can return `-1` **as a valid result** (for example `getpriority` on POSIX). For these APIs, you must follow the API's instructions, typically **setting `errno = 0` before the call**, and then checking both the return value and `errno`. That is a contract-specific exception, not advice to set `errno = 0` before every C call.

## 5. JNI Status Constants Are Not Java Exceptions Either

JNI has return codes such as `JNI_OK` (success, 0), `JNI_ERR` (general error, -1), `JNI_EDETACHED` (thread not attached), and `JNI_EVERSION` (JNI version not supported) in appropriate APIs such as the JavaVM Invocation API. These are **JNI API status codes**, not Java `Throwable`s.

Do not write:

~~~c
/* Wrong when the function "calculate" is meant to return numeric data. */
return JNI_ERR; /* Java sees the integer -1, without automatically getting an exception. */
~~~

If a Java method is declared `native int calculate()`, returning `JNI_ERR` as an integer still just returns -1 unless there is a pending exception. `JNI_ERR` is also not a POSIX `errno` error code, and is completely unrelated to a specific cause such as a missing file, failed connection, or invalid input.

On the other hand, if a JNI API returns `NULL` and has a pending exception, C code must **check for the exception**, not arbitrarily replace it with another exception or treat `NULL` as a normal value.

## 6. A Pending Java Exception Is a State of the Java Thread

Java has `try/catch/finally` and exception classes. JNI defines a **stateful** interaction model:

- Native code can ask the JVM to throw a `Throwable` using `Throw` or `ThrowNew`.
- JNI APIs such as `FindClass`, `NewObject`, `CallObjectMethod`, and `GetObjectArrayElement` can also cause exceptions, depending on the function and conditions.
- Inside a native method, an exception typically sits in a **pending** state on the current Java thread. After `ThrowNew`, C **does not automatically jump** to any `catch` block and does not automatically exit the function.
- Upon returning to Java, the JVM transitions the pending exception into Java's normal exception mechanism; the Java side can `catch` the appropriate type.

Conceptual diagram:

~~~text
Java calls native method
        |
        v
C calls JNI or native library
        |
        +--> Native status code? ----> C decides to check and translate error
        |
        +--> Sentinel? --------------> C interprets per API; may be data
        |
        +--> JNI exception pending --> C performs valid cleanup and returns
                                          |
                                          v
                                  JVM returns to Java
                                          |
                                          v
                                    Java catch/finally
~~~

**Common mistake:** thinking `ThrowNew` behaves like C++ `throw` and that C statements immediately following it will not execute. In reality, if C code keeps running, it may operate on uninitialized data or call JNI functions that are forbidden while an exception is pending.

## 7. Core JNI Exception APIs

| JNI API | Primary function | Things to remember |
| --- | --- | --- |
| `Throw(env, throwable)` | Sets an existing `jthrowable` as the pending exception | Requires a valid `jthrowable` |
| `ThrowNew(env, exceptionClass, message)` | Creates a throwable from class and message, then sets it pending | `message` uses JNI **Modified UTF-8**; returns `0` on success, negative on failure |
| `ExceptionCheck(env)` | Returns `JNI_TRUE` if a pending exception exists | Does not need to create a new local reference; usually the concise choice |
| `ExceptionOccurred(env)` | Gets a local reference to the pending throwable, or `NULL` | Can be used to inspect/keep the throwable; must respect local-reference lifetime |
| `ExceptionClear(env)` | Clears the pending exception | Use only when you have **intentionally handled or replaced** the error |
| `ExceptionDescribe(env)` | Prints diagnostic/backtrace to the system error channel | **Has the side effect of clearing the pending exception**; do not use accidentally on a normal propagation path |
| `FatalError(env, message)` | Reports a fatal error and does not expect the JVM to recover | Do not use for business errors or recoverable I/O errors |

These functions require a valid `JNIEnv *` for the current thread. A JNI native function normally has `JNIEnv *env` as its first parameter.

Pattern for creating a Java exception from native C (the snippet has a complete helper, but needs to be called inside a native method with a valid `env`):

~~~c
#include <jni.h>

/* Only call this helper when no exception is pending. */
static void throw_illegal_argument(JNIEnv *env, const char *message) {
    jclass type = (*env)->FindClass(env, "java/lang/IllegalArgumentException");
    if (type == NULL) {
        /* FindClass failed; keep any pending error if present. */
        return;
    }

    (void) (*env)->ThrowNew(env, type, message);
    (*env)->DeleteLocalRef(env, type); /* Valid cleanup while pending. */
}
~~~

In production code, also check the branch where a JNI API fails **without** creating a pending exception (some JNI functions may just return an error value depending on the implementation) and ensure you do not silently turn a throwable-creation failure into a valid result. Handling OOM/low-memory in JNI is harder than the happy path; the examples here focus on distinguishing error models.

A C native method returning `jint` usually needs to return a dummy value to exit the function after `ThrowNew`:

~~~c
/* Snippet only inside a JNI function with return type jint. */
throw_illegal_argument(env, "invalid request");
return 0;  /* While an exception is pending, Java does not receive 0 as success. */
~~~

**Final condition:** the helper must actually create a pending exception. If the helper fails completely and leaves no exception pending, returning 0 could be interpreted as success data; this is why errors during exception creation matter.

## 8. What Can Be Called When an Exception Is Pending?

JNI rule: **do not call most JNI functions while an exception is still pending**. Two common handling approaches:

1. **Propagate:** perform cleanup using only allowed APIs, then return from the native method; let the JVM deliver the error to Java.
2. **Handle/translate:** decide that native code owns handling the error, retain necessary information, intentionally call `ExceptionClear`, and then execute the new handling/mapping path. Doing so can change the original semantics; never clear an exception just to "keep running".

Some JNI functions for checking and cleanup are allowed while pending, for example:

~~~text
ExceptionCheck, ExceptionOccurred, ExceptionClear, ExceptionDescribe
DeleteLocalRef, DeleteGlobalRef, DeleteWeakGlobalRef
ReleaseByteArrayElements, ReleaseStringChars, ReleaseStringUTFChars
ReleasePrimitiveArrayCritical, ReleaseStringCritical
MonitorExit, PopLocalFrame, PushLocalFrame
~~~

This is an **illustrative list**, not a replacement for the full list in the [JNI Design Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html). In practice, `FindClass`, `NewStringUTF`, `GetMethodID`, and `Call...Method` functions **must not** be called arbitrarily while an exception is pending.

**Wrong** example:

~~~c
jobject result = (*env)->CallObjectMethod(env, service, method_id);
if ((*env)->ExceptionCheck(env)) {
    /* WRONG: an exception is pending; FindClass cannot be used right now. */
    jclass type = (*env)->FindClass(env, "java/io/IOException");
    /* ... */
}
~~~

**Correct example when propagating**:

~~~c
jobject result = (*env)->CallObjectMethod(env, service, method_id);
if ((*env)->ExceptionCheck(env)) {
    /* Release owned native resources / local refs,
       using only allowed JNI cleanup functions. */
    return 0; /* For a native method with return type jint. */
}
/* Only use result after confirming there is no error. */
~~~

If a Java callback function throws an exception, the return value from `Call...Method` may **no longer be meaningful**; do not use it as success data. For callbacks with side effects, an exception does not automatically roll back what C has already done before that point.

### Avoid a special trap: `ExceptionDescribe`

During debugging, `ExceptionDescribe` prints the error/stack trace to the diagnostic channel, **and also clears the pending exception**. If you call it and return without restoring or replacing the exception, Java may see **the native method succeed or return a sentinel**, instead of the original exception. Logging an error is not the same as handling it.

### When to use `ExceptionClear`?

Only when intentionally choosing a different policy—for example, native code calls a Java callback that can fail and **there is a contract stating callback errors are ignored and the operation recovers**; or native code wants to translate the exception into another type with an appropriate cause/context. When replacing an exception, be careful to preserve the original information and handle errors that occur while constructing the new exception. Do not use `ExceptionClear` as a default "fix error" step.

## 9. Complete JNI Example: Status, Exception, and Callback

This example uses **custom error codes defined by the illustrative library**, so stdout is stable across multiple OSes. It does not need real files, networking, or system `errno` to trigger errors. The goal is to clearly observe all three error channels.

Simulated C library contract:

- `read_number(request, &value)` returns `STATUS_OK=0` and value `request * 2` when valid.
- Negative request returns `STATUS_INVALID=7`.
- Request equal to 13 returns `STATUS_BUSY=9`.
- A request too large to double within `jint` is treated as invalid to avoid signed C overflow.
- `out_value` is **only valid when status = STATUS_OK**.

JNI exposes three Java methods:

1. `rawStatus`: returns the **native error code**, Java must read the code.
2. `checkedValue`: on the success branch returns the numeric value; on the error branch translates status to a **Java exception**.
3. `callJava`: calls back into a Java callback via JNI; if the callback throws an exception, **preserves the pending exception** for the Java caller.

### 9.1. Java source: `NativeErrorModels.java`

~~~java
import java.util.function.IntSupplier;

public final class NativeErrorModels {
    static {
        System.loadLibrary("nativeerrormodels");
    }

    // 0 = OK, 7 = invalid request, 9 = simulated busy.
    private static native int rawStatus(int request);

    // Returns payload on success; throws Java exception on failure.
    private static native int checkedValue(int request);

    // May receive an exception from a Java callback invoked in C.
    private static native int callJava(boolean fail);

    private static int javaCallback(boolean fail) {
        if (fail) {
            throw new IllegalStateException("Java callback failed");
        }
        return 41;
    }

    private static void show(String label, IntSupplier operation) {
        try {
            System.out.println(label + "=" + operation.getAsInt());
        } catch (RuntimeException ex) {
            System.out.println(label + "="
                    + ex.getClass().getSimpleName()
                    + ": " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        System.out.println("status-ok=" + rawStatus(7));
        System.out.println("status-invalid=" + rawStatus(-1));
        System.out.println("status-busy=" + rawStatus(13));

        show("value-ok", () -> checkedValue(7));
        show("value-zero", () -> checkedValue(0));
        show("value-invalid", () -> checkedValue(-1));
        show("value-busy", () -> checkedValue(13));

        show("callback-ok", () -> callJava(false));
        show("callback-fail", () -> callJava(true));
    }
}
~~~

Note: `show` only catches `RuntimeException` to make the example's expected output clear. Real applications should not catch broadly and swallow all errors; for I/O and resource management, callers need to classify errors, propagate when appropriate, and preserve the cause.

### 9.2. C source: `NativeErrorModels.c`

~~~c
#include <jni.h>
#include <stdint.h>
#include "NativeErrorModels.h"  /* Generated by javac -h . */

enum {
    STATUS_OK = 0,
    STATUS_INVALID = 7,
    STATUS_BUSY = 9
};

/* Simulates a C library with return=status, out_value=payload. */
static jint read_number(jint request, jint *out_value) {
    if (request < 0 || request > INT32_MAX / 2) {
        return STATUS_INVALID;
    }
    if (request == 13) {
        return STATUS_BUSY;
    }
    *out_value = request * 2;
    return STATUS_OK;
}

/* Only call this helper when no exception is pending. */
static void raise_java(JNIEnv *env,
                       const char *exception_class,
                       const char *message) {
    jclass type = (*env)->FindClass(env, exception_class);
    if (type == NULL) {
        /* Do not create a new exception: leave any existing JNI error as-is. */
        return;
    }
    (void) (*env)->ThrowNew(env, type, message);
    (*env)->DeleteLocalRef(env, type);
}

/* Java receives status 0/7/9 intact, with no automatic exception. */
JNIEXPORT jint JNICALL Java_NativeErrorModels_rawStatus(
        JNIEnv *env, jclass cls, jint request) {
    (void) env;
    (void) cls;
    jint ignored_value = 0;
    return read_number(request, &ignored_value);
}

/* Java receives payload or exception, never status as data. */
JNIEXPORT jint JNICALL Java_NativeErrorModels_checkedValue(
        JNIEnv *env, jclass cls, jint request) {
    (void) cls;
    jint value = 0;
    jint status = read_number(request, &value);

    if (status == STATUS_INVALID) {
        raise_java(env, "java/lang/IllegalArgumentException",
                   "negative or oversized request");
        return 0;  /* Dummy value; Java will receive the exception. */
    }
    if (status == STATUS_BUSY) {
        raise_java(env, "java/lang/IllegalStateException",
                   "simulated native busy");
        return 0;
    }
    if (status != STATUS_OK) {
        raise_java(env, "java/lang/IllegalStateException",
                   "unexpected native status");
        return 0;
    }
    return value; /* Only read payload on success. */
}

/* Native invokes Java callback; Java exception is preserved. */
JNIEXPORT jint JNICALL Java_NativeErrorModels_callJava(
        JNIEnv *env, jclass cls, jboolean fail) {
    jmethodID method = (*env)->GetStaticMethodID(
            env, cls, "javaCallback", "(Z)I");

    if (method == NULL) {
        /* JNI lookup failed; a pending exception may exist. */
        return 0;
    }

    jint result = (*env)->CallStaticIntMethod(env, cls, method, fail);
    if ((*env)->ExceptionCheck(env) == JNI_TRUE) {
        /* Keep callback exception; DO NOT call FindClass/ThrowNew. */
        return 0;
    }
    return result;
}
~~~

**Check the key points:**

- `read_number` is a **pure C function** returning a custom status. It does not use `JNIEnv` and cannot "throw a Java exception" on its own without a JNI context/different contract.
- `rawStatus` is a wrapper passing status across the JNI boundary. Java will see the numbers `0`, `7`, `9` as normal `int` values.
- `checkedValue` chooses to map status to `IllegalArgumentException` or `IllegalStateException`. That is a **wrapper design decision**. For real file errors, the appropriate type might be `IOException` or a specific subtype.
- `raise_java` calls `FindClass` before any pending exception exists, then `ThrowNew`. `DeleteLocalRef` is an allowed cleanup after `ThrowNew`.
- `GetStaticMethodID` looks up the exact callback `(Z)I` (one `boolean`, returning `int`). `CallStaticIntMethod` can execute Java code and trigger an exception; C uses `ExceptionCheck` and returns.
- It does **not** clear the callback exception or replace it with another `IllegalStateException`, so the Java caller receives the exact `"Java callback failed"` exception.

This is a simple learning pattern; in production you need to harden the branch where creating a Java exception fails without a pending exception, logging/telemetry strategies, and ownership of all native resources. The example intentionally does not place JNI methods across multiple threads and does not hold pointers long-term.

### 9.3. Compiling and Running on Linux

Place `NativeErrorModels.java` and `NativeErrorModels.c` in the same directory. Requires JDK **17 or newer**, a C compiler supporting C11, and `JAVA_HOME` pointing to the right JDK.

~~~bash
javac -encoding UTF-8 -h . NativeErrorModels.java

cc -std=c11 -Wall -Wextra -Werror -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  NativeErrorModels.c -o libnativeerrormodels.so

java -Djava.library.path=. NativeErrorModels
~~~

Stdout of the `java` command:

~~~text
status-ok=0
status-invalid=7
status-busy=9
value-ok=14
value-zero=0
value-invalid=IllegalArgumentException: negative or oversized request
value-busy=IllegalStateException: simulated native busy
callback-ok=41
callback-fail=IllegalStateException: Java callback failed
~~~

In practice, `javac -h .` generates the `NativeErrorModels.h` header so the C prototype is checked by the compiler. The `cc` command above uses Linux include paths and a `.so` shared library name. On Windows/macOS, you need the corresponding compiler, platform include directory, and shared library build flags; do not use the exact Linux command as a cross-platform instruction.

This lesson does not require calling `System.gc()`, networking, or triggering real OS errors. The three result channels are tested **deterministically**:

- `status-invalid=7` is a **native error code** received directly by Java.
- `value-invalid=IllegalArgumentException...` is **a Java exception** created by the wrapper from error code 7.
- `callback-fail=IllegalStateException...` is a **Java exception originating from the callback**, where native code only detects pending and propagates it.

### 9.4. Note on the Throwable-Creation Failure Branch

The `raise_java` pattern above illustrates the common case; in production systems, you must clearly define how to handle cases where `FindClass` cannot find the class, `ThrowNew` fails, or the system is critically low on memory. Some JNI functions can report failure via `NULL`/negative values without simultaneously creating a pending exception. If the wrapper always does `return 0` after the helper regardless of whether an exception is pending, Java risks seeing **a valid-looking but wrong 0 value**.

Design-level precautions:

1. Use standard Java exception classes that can be loaded reliably by the appropriate class loader.
2. Check the results of `FindClass` and `ThrowNew`; if they fail, **do not silently treat the operation as succeeding**.
3. Design a result contract capable of representing failure when a throwable cannot be constructed (for example, status + out parameter, or a result object created by Java at the wrapper layer), and define a fallback for low-memory conditions.
4. Do not call `FindClass`/`ThrowNew` if **an exception is already pending** from a previous step; prefer propagating the original error when there is no clear reason to replace it.

For simpler code, many library wrappers map native status **at the Java layer** instead of directly in JNI C. That can make testing/class loading easier, especially when the native side does not need to know the exception hierarchy.

## 10. Alternative Pattern: JNI Returns Status, Java Wrapper Throws Exception

A variant that is often clearer when a lot of native information needs to be preserved: C only writes `status` and `output`, and the Java wrapper is responsible for throwing the exception. For instance, a JNI API could declare:

~~~java
// Contract: status 0/7/9; if status != 0, output[0] is invalid.
private static native int readRaw(int request, int[] output);

public static int readNumber(int request) {
    int[] output = new int[1];
    int status = readRaw(request, output);

    switch (status) {
        case 0:
            return output[0];
        case 7:
            throw new IllegalArgumentException("invalid request");
        case 9:
            throw new IllegalStateException("native busy");
        default:
            throw new IllegalStateException("native status: " + status);
    }
}
~~~

**This is a design illustration**, not standalone runnable because it lacks the enclosing class and the C implementation of `readRaw`. The success branch uses `output[0]` after status is verified; the error branch does not touch output. If native code reads/writes `int[]`, it must use the proper paired JNI array functions; `jintArray` is not `jint *`.

Advantage of this approach: Java code directly controls the exception type, cause, retry policy, stack trace, and logging. However, when the underlying JNI call itself creates a pending Java exception (for example, `SetIntArrayRegion` fails), the Java wrapper **cannot receive a normal status** for that call; the exception must be propagated or handled in JNI according to the contract.

## 11. Choosing a Java Exception by Error Meaning

When native code detects an error, choose the exception type based on **the meaning the Java API is providing**, not just the status number.

| Condition | Typical Java choice | Why |
| --- | --- | --- |
| Invalid Java argument | `IllegalArgumentException` (or an appropriate subtype) | Caller needs to fix the input |
| Inappropriate object/operation state | `IllegalStateException` | Caller needs to change state/call order |
| File or stream access hits an I/O error | `IOException`, `FileNotFoundException`, or `java.nio.file` subtype | Expresses I/O error in the right domain |
| Malformed native data | `IllegalArgumentException`, specific parser exception, or checked type | Depends on parser contract |
| Operation timed out | A timeout exception meaningful to the Java API | May require retry with timeout/cancellation |
| Data not found when the API considers that normal | Well-documented `Optional`/`null`/sentinel | Not necessarily an exception |
| Critical out-of-memory | `OutOfMemoryError` per appropriate JVM/native policy | Do not disguise it as an ordinary input error |

**Checked vs unchecked:** `IOException` is a checked exception. If a Java native method can throw this type, it should normally declare `throws IOException` so the caller knows the contract:

~~~java
public native byte[] readFile(String path) throws java.io.IOException;
~~~

JNI can create a checked exception even when the Java declaration omits `throws` (the JVM does not enforce compile-time checked-exception rules on JNI). However, do not intentionally omit `throws` from a public Java API for that reason; doing so distorts the library's contract and makes it harder for callers to handle.

**Preserve the cause:** if the native library provides an OS error code, subsystem name, and operation, preserve that information in the exception message, custom fields, or cause according to API policy. Do not lump all errors into `RuntimeException("native failed")`, which makes root-cause investigation impossible.

## 12. When a Java Callback Throws an Exception While C Is Running

The call flow can go in the reverse direction:

~~~text
Java caller
  -> JNI native method
       -> C calls CallStaticIntMethod / CallObjectMethod
            -> Java callback throws IllegalStateException
       <- C regains control and sees a PENDING exception
  <- Native returns (after valid cleanup)
Java caller catches IllegalStateException
~~~

Important: **an exception from a callback does not automatically unwind the native C stack**. Native code must call `ExceptionCheck` or check the JNI result per contract, and then actively exit the function. Do not continue work as if the callback had succeeded.

Wrong snippet:

~~~c
jint result = (*env)->CallIntMethod(env, callback, method_id);
/* WRONG: the callback may have thrown an exception.
   Using result as valid data is wrong and can corrupt state. */
native_commit(result);
~~~

Better pattern:

~~~c
jint result = (*env)->CallIntMethod(env, callback, method_id);
if ((*env)->ExceptionCheck(env)) {
    /* Roll back native state if the contract requires it, clean up resources.
       Do not call disallowed JNI functions while pending. */
    return 0; /* For a native method with return type jint. */
}
native_commit(result); /* Only runs when the callback actually succeeded. */
~~~

Both snippets are illustrative; `callback`/`method_id`/`native_commit` are defined by the real application. If invoking the callback already performed side effects before throwing, do not assume native code can roll back all Java side effects.

## 13. C++ Exceptions and Native Crashes: Not Identical to Java `Throwable`

A native C++ function may `throw std::runtime_error`. However, **a C++ exception must not be allowed to escape across the JNI boundary** into the JVM as if it would automatically turn into a Java exception. Catch it in the C++ adapter, clean up resources via RAII, and then map it to a Java status/exception according to policy. Illustrative code (fragment inside a C++ JNI method; `translateToJava` is an application helper):

~~~cpp
try {
    run_native_operation();
} catch (const std::bad_alloc&) {
    /* Translate to an appropriate memory-error policy for Java. */
    translateToJava(env, "java/lang/OutOfMemoryError", "native allocation failed");
} catch (const std::exception& ex) {
    translateToJava(env, "java/lang/IllegalStateException", ex.what());
}
~~~

**Do not compile this snippet standalone:** it needs `run_native_operation`, `translateToJava`, and a JNI method definition. It only illustrates the C++ exception-catching boundary.

Similarly, a segmentation fault or undefined behavior in C/C++ can **crash the entire JVM process**; they are not Java `NullPointerException`s that you can always `catch`. JNI `FatalError` is also a fatal error path, not for handling "file not found" or a normal `BUSY` status.

This highlights another difference: **checking native error codes** is mandatory even when the Java side has `try/catch`. Java `try/catch` cannot protect against memory, pointer, and ABI mistakes in C code.

## 14. JNI Resources When Errors Occur

A native function may be holding:

- Local/global JNI references;
- Data from `GetByteArrayElements`, `GetStringUTFChars`, or `GetPrimitiveArrayCritical`;
- File descriptors, socket handles, mutexes, native `malloc` buffers;
- A callback or transaction with state that needs rollback.

When an error occurs, clean up **the right resource handles** before returning:

~~~c
/* Snippet: data is jbyte* obtained from GetByteArrayElements,
   array is a valid jbyteArray, and a callback threw a Java exception. */
if ((*env)->ExceptionCheck(env)) {
    (*env)->ReleaseByteArrayElements(env, array, data, JNI_ABORT);
    /* If holding a valid native fd, close(fd) per POSIX contract. */
    return 0; /* Current JNI function returns jint. */
}
~~~

`ReleaseByteArrayElements` is an allowed cleanup API while an exception is pending; `JNI_ABORT` tells JNI not to copy the native buffer contents back to the array if the operation was read-only. Cases where native code already modified data and requires partial commit on error must be designed specifically.

**Cleanup order matters:** if a native operation fails and sets `errno`, capture `errno` before calling other cleanup functions that might overwrite it; then use the captured code to create a Java exception (when no exception is pending) or return a status. When a Java callback has already caused a pending exception, clean up with allowed JNI functions and avoid constructing a second Java exception unless intentionally handling/translating the first one.

Example control-flow strategy:

~~~text
acquire native resource
try native operation
    success -> produce result
    native status failure -> capture code -> release resources -> map error
    Java callback pending -> release allowed resources -> return (propagate)
release resources
return result
~~~

In pure C with multiple exit points, a `cleanup:` label with `goto cleanup` can help ensure every error path releases resources; however, that does **not** mean that once cleanup finishes you can continue calling arbitrary JNI functions while pending. In C++, RAII is useful for releasing native resources once C++ exceptions are caught properly at the boundary.

## 15. Separating "No Data" from "Could Not Execute"

A lookup API might return `FOUND`, `NOT_FOUND`, and `ERROR` states. Do not use a single Java exception type for all cases if "not found" is normal business behavior:

~~~java
// Suggested Java API: the native method already classified real errors in the wrapper.
public java.util.OptionalInt findValue(int key) {
    // return OptionalInt.empty() when the data genuinely does not exist;
    // throw an exception when the database/native library cannot query.
    throw new UnsupportedOperationException("illustrative API shape");
}
~~~

This snippet **only describes the contract**, not an implementation; do not put that placeholder into production code. If a Java API chooses `OptionalInt.empty()` for absence, it still needs a separate path to report "query failed" (such as an exception), because absence and failure are two different states.

A full result type can also carry metadata:

~~~text
Outcome:
  success(value)
  not_found
  invalid_input(details)
  temporary_failure(native_code, operation, can_retry)
  permanent_failure(native_code, operation)
~~~

This is a **conceptual model**, not Java syntax. You do not have to force every API to use a result object; the choice depends on error frequency, caller handling needs, binary compatibility requirements, and Java API conventions.

## 16. When Should You Retry?

A native error code may indicate "temporarily unavailable", such as a busy service or transient I/O interruption. However, retrying is only valid when you simultaneously verify:

1. **Is the operation idempotent?** Submitting a payment, writing a record, or consuming a message may already have had a side effect even though the caller received an error.
2. **What does the error code say exactly?** Not every `EAGAIN`/`BUSY` should be retried indefinitely; check the API contract and deadline.
3. **Are there cancellation, deadline, backoff, and retry limits?** Unbounded retries can overload the service.
4. **Is error context preserved?** Record the attempt, operation, native status, and final cause without exposing sensitive data.

At the Java boundary, turning every status into the same `IllegalStateException` while discarding the original code can lose the ability to classify retryability. If automated logic is needed, consider exception subtypes or a result with a stable error kind instead of parsing string messages.

## 17. Common Implementation Mistakes

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| Java `catch` does not run when C returns `-1` | C only returned a number, no Java exception is pending | Design a Java wrapper to check status or intentionally use `ThrowNew` |
| File error reported as value 0 | JNI code returns 0 after failure without creating an exception | Check exception-creation result; keep a fail-closed contract in the wrapper |
| `errno` gives a strange value even though `open` failed | Reading `errno` after JNI calls/logging/cleanup | Save `int saved = errno;` immediately after the error |
| Function reports success but `errno != 0` | Assuming `errno` is always reset on success | Only read `errno` when the contract says an error occurred |
| Java callback throws but C keeps using result | C++/C does not unwind automatically on a pending Java exception | `ExceptionCheck` then cleanup/return |
| `FindClass`/`NewStringUTF` crashes while pending | Calling disallowed JNI functions in a pending state | Propagate and clean up using only allowed JNI APIs, or clear intentionally |
| After logging, Java no longer sees the exception | `ExceptionDescribe` cleared the pending exception | Do not use it as a routine logger on the propagation path |
| `NULL` from `GetObjectField` treated as an error | The Java field actually has value `null` | Distinguish valid null from a pending exception |
| `JNI_ERR` treated as `IOException` | Confusing JNI API codes with filesystem error classification | Rely on the specific API and map at the boundary |
| C++ exception escapes JNI entry point | Not caught in the native wrapper | Catch in C++ and translate to the Java contract |
| Native error thrown twice | Already had a pending exception and called another `ThrowNew` | Prefer keeping the original error, clear/translate intentionally if needed |
| JNI leaks resources when callback fails | Cleanup only on the success branch | Unify cleanup paths for all exits, check pending |

### Anti-pattern: constructing an exception when JNI already has one pending

~~~c
jclass cls = (*env)->FindClass(env, "com/example/LibraryClass");
if (cls == NULL) {
    /* WRONG: FindClass may already have created a pending exception.
       Do not call FindClass again here to force another error. */
    jclass replacement =
        (*env)->FindClass(env, "java/lang/IllegalStateException");
    (void) replacement;
}
~~~

The right approach is to **check pending, perform allowed cleanup, and return** or intentionally handle/clear the old error according to a carefully designed mapping.

## 18. Test Matrix for the JNI Error Boundary

| Scenario | Expected outcome | Test idea |
| --- | --- | --- |
| Success with output = 0 | `0` is success data, not treated as an error | `checkedValue(0)` |
| Input error status | Java wrapper throws the right exception or returns a status checked by caller | `rawStatus(-1)`, `checkedValue(-1)` |
| Native busy/temporarily unavailable | Status is preserved and mapped per contract | `rawStatus(13)`, `checkedValue(13)` |
| Sentinel -1 is valid data | Not mistaken for an error | `valueOrThrow(true, -1)` |
| Java callback throws exception | C does not use callback result; Java receives original exception | `callJava(true)` |
| JNI API lookup fails | Propagates pending exception, does not make further arbitrary JNI calls | Intentionally test `GetStaticMethodID`/signature |
| Native allocation fails | Does not return fake success; cleans up and classifies appropriately | Simulate allocator failure via dependency injection |
| POSIX call reports -1/`errno` | Captures `errno` accurately, preserves metadata | Fake native wrapper or test on POSIX |
| Error path through JNI array/string | Balanced acquire/release pairs | Valgrind/ASan or CheckJNI when available |
| Multiple threads | Per-thread error codes and exceptions on the right thread | Concurrency tests per bridge design |
| C++ exception/native crash | No C++ exception crosses JNI; crashes investigated natively | Native unit tests and sanitizers |

**Do not try to trigger a segmentation fault in the JVM just to prove `try/catch` cannot catch it.** Use unit tests/sanitizers at the appropriate native layer and analyze crash logs when real errors occur.

## 19. Self-Check Questions

**Question 1.** A C function returns `-1` and the Java native method also has return type `int`. Will `catch(IOException)` run automatically?

No. If C only does `return -1;`, Java receives the number -1; for `catch` to run, there must be an actual Java exception (created by Java/JNI) or the Java wrapper must check the value and throw.

**Question 2.** A native function succeeds with data `0`, while status `0` also denotes success. How do you tell them apart?

By the contract. If the return value only holds status, data goes through an out-parameter; if the return value holds data, do not treat 0 as a status. Distinguish the two functions by contract, not just by the `jint` type.

**Question 3.** Is `errno` always 0 after a successful C call?

No. `errno` is only meaningful per the API's contract when there is an error indication, and success does not necessarily reset `errno`.

**Question 4.** A Java callback throws `IllegalStateException` via `CallStaticIntMethod`. Can C call `NewStringUTF` before returning?

Normally no. While an exception is still pending, do not call most JNI functions; clean up with allowed APIs and return to propagate, or intentionally clear it when genuinely handling the error.

**Question 5.** Is `ThrowNew` like C++ `throw` and does it stop the C function immediately?

No. It sets a pending Java exception; C keeps executing if more code follows. Native code must choose the appropriate control flow and exit after cleanup.

**Question 6.** Can `ExceptionDescribe` be used to log an exception and still let Java catch that same exception?

Do not assume that. `ExceptionDescribe` **clears the pending exception** as a side effect, so to preserve the original exception you must choose a different diagnostic strategy or intentionally manage restoration.

**Question 7.** If a JNI call returns `NULL`, is there definitely a Java exception?

No. Some APIs allow `NULL` as a normal result or may only report an error without setting an exception. You must check each function's contract and check for pending exceptions when needed.

**Question 8.** When POSIX `open` returns an error, should raw `errno` always be converted to `IllegalArgumentException`?

No. Classify according to the operation's meaning and the Java API contract; it may be `IOException`/`NoSuchFileException`/`AccessDeniedException`. Capture `errno` at the right time and preserve error kind/context.

**Question 9.** Native thread A has a pending Java exception. Can thread B read `ExceptionCheck` using thread A's `JNIEnv *`?

No. `JNIEnv *` is thread-bound. Native thread B must have its own JNI environment after being properly attached; pending exceptions belong to their respective threads.

**Question 10.** Why should a C++ `throw std::runtime_error` not cross the JNI boundary?

Because JNI does not define C++ stack unwinding through JVM frames to become a Java `Throwable`. Catch C++ exceptions in the native adapter and translate them to the Java contract before returning to the JVM.

## 20. Decision Checklist at the Java ↔ Native Boundary

- [ ] Determine for **each C API** whether it returns a status, sentinel, or payload; is there an `errno`/out-parameter branch?
- [ ] Distinguish `JNI_OK`/`JNI_ERR` from errno/native library codes; do not try to use one code for everything.
- [ ] Only use output values when the function reports success; do not let `-1`/`NULL` be mistaken for errors if they are valid.
- [ ] Capture OS errors **immediately** when the contract indicates an error; preserve native code/context if needed for diagnostics.
- [ ] Define Java API policy: return result, absence, checked/unchecked exception, mapping/retry.
- [ ] After a JNI call that can throw, check the return value and `ExceptionCheck`/`ExceptionOccurred` per contract.
- [ ] While an exception is pending, clean up using allowed JNI APIs; avoid calling `FindClass`/`Call...Method`/`NewStringUTF` arbitrarily.
- [ ] If using `ThrowNew`, end the C flow clearly; ensure a throwable-creation failure does not turn into a fake success return.
- [ ] If using `ExceptionClear` or `ExceptionDescribe`, do so with clear intent; do not accidentally swallow the original Java error.
- [ ] Native resources and JNI references are released on all success/error/exception paths.
- [ ] C++ exceptions are caught at the native boundary; do not let undefined behavior/crashes mix into the Java error flow.
- [ ] Test success=0, data=-1, missing, native error, JNI pending, callback failure, resource cleanup, OOM fallback, and concurrency when relevant.

## References

- [Oracle JNI Specification: Design Overview — Exceptions and Error Codes](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): pending exceptions, JNI control flow, JNI functions valid while pending.
- [Oracle JNI Specification: Functions — `ThrowNew`, `ExceptionCheck`, `ExceptionOccurred`, `ExceptionDescribe`, and `ExceptionClear`](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): detailed contract for each function.
- [Oracle JNI Specification: Types and Data Structures](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html): `jint`, `jobject`, `JNIEnv`, and JNI type usage.
- [Linux man-pages `errno(3)`](https://man7.org/linux/man-pages/man3/errno.3.html): when to read `errno` and meaning of POSIX error codes.
- [POSIX `errno`](https://man7.org/linux/man-pages/man3/errno.3p.html): validity limits and conditions of `errno`.
- [Java SE 17 `IOException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html): typical Java checked exception for I/O.

**Remember:** Native error codes and sentinels are **return-value contracts of the native API**; Java exceptions are **error states managed by the JVM**. The JNI bridge must actively classify, check, translate, and clean up. Do not let an integer, `NULL`, or `errno` implicitly decide Java semantics; and do not let a pending Java exception be masked by subsequent JNI calls.
