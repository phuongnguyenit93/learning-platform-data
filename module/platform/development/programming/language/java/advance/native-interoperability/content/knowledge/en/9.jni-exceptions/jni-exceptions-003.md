# ExceptionCheck, ExceptionOccurred, and When to Use Them in JNI

In the Java Native Interface (JNI), Java exceptions can occur while C/C++ code is executing: for example, a `CallStaticIntMethod` call invokes a Java method that throws `NumberFormatException`, or `FindClass` cannot find a class, or JNI cannot allocate a new object. That exception **is recorded as a pending exception on the current JNI thread**; it does not automatically cause the C function to jump out of a loop like a `throw` statement in Java.

Therefore, JNI code must proactively observe errors, clean up resources, and choose the next action. The two most common APIs are:

- **`ExceptionCheck(JNIEnv *env)`:** checks **whether there is a pending exception or not**; returns `JNI_TRUE` or `JNI_FALSE`, without creating a local reference to the exception.
- **`ExceptionOccurred(JNIEnv *env)`:** retrieves **the pending `jthrowable` object**, or `NULL`; if an object is present, the result is a JNI local reference that must be managed. This call **does not automatically clear** the pending exception.

The content below explains when to use which API, which operations are permitted when an exception is pending, handling/propagation/recovery patterns, and a runnable Java 17 + C11 program to verify.

## 1. The pending exception model in JNI

Let us distinguish three layers of state:

1. **Java exception object:** an object inheriting from `java.lang.Throwable` such as `IllegalArgumentException`, `IOException`, `OutOfMemoryError`.
2. **Pending-exception state:** the JVM records that the current thread has an exception that needs to be handled or thrown when control returns to Java.
3. **JNI function return value:** may be `NULL`, `0`, or a normal value depending on the API. This value **cannot by itself replace** checking for a pending exception for all JNI calls.

For example: JNI calls a Java method returning `int`. If the method throws an exception, the native caller still receives some `jint` at the interface level, but **must not treat it as a valid business result**. Check `ExceptionCheck` immediately after `CallStaticIntMethod`, then clean up and return so the exception propagates up to Java.

Note: a pending exception is state attached to **the thread using `JNIEnv *`**, not a process-wide global error variable. Do not store `JNIEnv *` for use on another thread; nor call `ExceptionOccurred` on one thread and assume it sees another thread's exception.

### 1.1. What happens when a JNI function causes an error?

A typical sequence of operations:

```text
Java calls native method
       |
       v
C/JNI: CallStaticIntMethod(...) calls back into Java
       |
       v
Java callback throws NumberFormatException
       |
       v
JVM sets pending exception on JNI thread
       |
       v
C/JNI is still executing
       |
       +--> ExceptionCheck(...) == JNI_TRUE
       |    or ExceptionOccurred(...) returns jthrowable
       |
       +--> clean up local references / buffers / C allocations
       |
       +--> return from native method
       |
       v
Java caller receives NumberFormatException
```

Native code **does not** have to call `ThrowNew` again if it wants to pass the original exception from the callback back to Java. It only needs to leave the exception pending and return properly. If it continues calling ordinary JNI APIs such as `FindClass`, `NewStringUTF`, `GetObjectClass`, or `CallObjectMethod` while an exception is still pending, the code can violate the JNI contract.

### 1.2. Not every default value is an error

- A Java method returning `int` can **validly return `0`**, so `result == 0` does not prove it threw an exception.
- `GetObjectArrayElement` can **validly return `NULL`** if the array element is `null`, while it can also raise an exception if the index is invalid. When you need to distinguish them, check the pending state.
- `NewStringUTF` returns `NULL` on failure; you must handle the error path (do not dereference or use the result). For many JNI functions with a clear error-indicating return value, checking the return value first is sufficient to enter cleanup without needing to create a `jthrowable` just to check.
- A JNI API that does not report errors with a useful return value, such as certain array access variants or Java calls returning primitive values, requires an explicit exception check when the result affects subsequent logic.

## 2. Comparing `ExceptionCheck` and `ExceptionOccurred`

### 2.1. C signatures and return values

```c
jboolean ExceptionCheck(JNIEnv *env);
jthrowable ExceptionOccurred(JNIEnv *env);
```

When using `jni.h` in C, they appear as calls through the JNI interface:

```c
jboolean hasPending = (*env)->ExceptionCheck(env);
jthrowable error = (*env)->ExceptionOccurred(env);
```

In C++ JNI, the syntax is `env->ExceptionCheck()` and `env->ExceptionOccurred()`; the following examples use **C11**.

| Aspect | `ExceptionCheck` | `ExceptionOccurred` |
| --- | --- | --- |
| Question answered | "Is there a pending exception?" | "What is the pending exception object?" |
| Return type | `jboolean` | `jthrowable` (a JNI object reference) |
| No exception | `JNI_FALSE` | `NULL` |
| Exception present | `JNI_TRUE` | Local reference to the exception |
| Creates a new local reference? | **No** | **Yes, when returning an exception** |
| Automatically clears pending exception? | **No** | **No** |
| Needs `DeleteLocalRef`? | No object to delete | Yes, if holding a local `jthrowable` and not returning it |
| Use case | Quick check, deciding cleanup/return | Need to hold, classify, handle, or rethrow the same throwable |

**Prefer `ExceptionCheck`** if you only need a yes/no answer, especially in a hot loop. It does not accumulate additional local references. **Choose `ExceptionOccurred`** if you truly need the error object to hold temporarily, distinguish error types, or pass the original exception to another handling flow according to JNI rules.

Example when only checking:

```c
jint value = (*env)->CallStaticIntMethod(env, clazz, method, input);
if ((*env)->ExceptionCheck(env)) {
    /* Clean up acquired resources; keep exception pending. */
    return 0; /* This value is ignored if the exception propagates to Java. */
}
return value;
```

This is **a snippet inside a native method with a `jint` return type**, not a standalone C program. The `0` in the error branch only satisfies the C signature; Java observes the exception instead of treating it as a normal result.

Example if the error object is needed:

```c
jthrowable problem = (*env)->ExceptionOccurred(env);
if (problem != NULL) {
    /* Holds a local reference; the exception is STILL pending. */
    (*env)->DeleteLocalRef(env, problem);
    return 0;
}
```

`DeleteLocalRef` only deletes the extra local reference returned by `ExceptionOccurred`; **it does not clear the pending state**. This snippet is also only code inside a native method with a `jint` return.

### 2.2. Why does `ExceptionOccurred` easily leak local references?

In a loop or long-running native thread, each time `ExceptionOccurred` returns a new `jthrowable`, JNI creates a local handle. Failing to delete the newly created handles can fill up the local reference table, even when you are trying to handle errors.

Do not confuse this:

```c
jthrowable e = (*env)->ExceptionOccurred(env);
e = NULL;  /* Only changes the C variable, does not release the local reference! */
```

Use `DeleteLocalRef(env, e)` when you no longer need it. For logic that only needs a boolean, use `ExceptionCheck` to avoid creating a ref in the first place.

## 3. Situations where exceptions must be checked

### 3.1. Immediately after calling a Java method via JNI

Functions like `CallObjectMethod`, `CallIntMethod`, `CallStaticIntMethod`, and `Call<Type>Method` variants can execute **arbitrary Java code**, where exceptions can arise due to input, application state, or VM errors.

Safe pattern:

```c
jint parsed = (*env)->CallStaticIntMethod(env, cls, parseMethod, text);
if ((*env)->ExceptionCheck(env)) {
    /* Do not use parsed. Clean up acquired resources. */
    return 0;
}

/* Only here can parsed be used as the result of the Java callback. */
```

Do not rely on `parsed == 0` or a sentinel guessed by the program. If the Java callback returns `void`, you still need to check when you want to make subsequent JNI calls or update native state that depends on the callback.

### 3.2. When a JNI API reports an error with `NULL` or an error code

Example:

```c
jclass cls = (*env)->FindClass(env, "java/lang/String");
if (cls == NULL) {
    /* There may be a pending exception. Do not use cls. */
    return;
}
(*env)->DeleteLocalRef(env, cls);
```

Here the return value is sufficient for the error branch; **there is no need to call `ExceptionOccurred` just to know that `cls == NULL`**. When building a message or needing to determine the specific error type, you can observe the exception according to the API contract.

The ambiguous case where `GetObjectArrayElement` returns `NULL`: null could be an element that truly has no object; if the code needs to distinguish, check `ExceptionCheck` after the call:

```c
jobject element = (*env)->GetObjectArrayElement(env, array, index);
if ((*env)->ExceptionCheck(env)) {
    /* Invalid index or other JNI error; do not use element. */
    return;
}
if (element == NULL) {
    /* Valid null element. */
} else {
    /* Use element, then DeleteLocalRef(env, element). */
    (*env)->DeleteLocalRef(env, element);
}
```

The two snippets above illustrate **the body of a JNI function returning `void`**, with `env`, `array`, and `index` already validly defined; they do not compile standalone.

### 3.3. When a JNI API has no useful separate error channel

Some JNI APIs operate by side effect or return a value that can also be valid data. For example, a setter method returns `void`, yet the JNI invocation can still lead to an exception; the return value does not help with checking. Before calling the next step, observe the pending state.

The key point is not "always call `ExceptionOccurred` after **every** JNI call", but rather **check according to the contract of the function just called** and every point that could raise an exception where the code will still do dependent work.

### 3.4. In a native loop or long-running call

A native loop running for many seconds, especially when not going through other JNI APIs that could throw exceptions, may need reasonable checkpoints to detect asynchronous exceptions recorded by the JVM. JNI documentation recommends checking at necessary points in long-running tasks; across JNI/JVM versions, the details of async exception checking may vary.

```c
/*
 * Illustrates a long native processing loop:
 * do_work_unit() and total are defined by the owning program.
 */
for (size_t i = 0; i < total; ++i) {
    do_work_unit(i);

    if ((i & 1023u) == 0u && (*env)->ExceptionCheck(env)) {
        /* Clean up native resources, then return to Java. */
        break;
    }
}
```

This **is not a standalone runnable file**, but a structure illustrating a periodic checkpoint. Do not treat the check as a general cancellation mechanism or a way to "catch" every asynchronous exception at the exact moment it is requested; an exception can appear after the check. Also do not use `Thread.stop()` as a mechanism to stop a worker because it is deprecated and can leave application state inconsistent.

## 4. What is permitted and not permitted when an exception is pending

Practical rule: **with a pending exception, do not continue calling most ordinary JNI APIs**. You must clean up before exiting, or proactively clear the exception before proceeding further.

According to the Java JNI Design Overview, JNI APIs that can be safely called while pending include:

| Group | Permitted APIs | Purpose |
| --- | --- | --- |
| Observing, controlling exceptions | `ExceptionCheck`, `ExceptionOccurred`, `ExceptionDescribe`, `ExceptionClear` | Inspect state, log, clear |
| Cleaning up JNI references | `DeleteLocalRef`, `DeleteGlobalRef`, `DeleteWeakGlobalRef` | Release JNI handles |
| Cleaning up JNI strings | `ReleaseStringChars`, `ReleaseStringUTFChars`, `ReleaseStringCritical` | Return pointers/buffers obtained from JNI |
| Cleaning up JNI arrays | `Release<Type>ArrayElements`, `ReleasePrimitiveArrayCritical` | Unpin/copy back/release per contract |
| Cleaning up monitors | `MonitorExit` | Release held JNI monitor |
| Managing local frames | `PushLocalFrame`, `PopLocalFrame` | Manage scope of local refs |
| Managing thread attachment | `DetachCurrentThread` | End native thread attachment as specified |

Even if an operation is in the permitted list, you must still ensure valid inputs and follow proper lifetimes. In typical code, **only call the cleanup APIs that are actually needed**, then return and let Java receive the exception.

Conversely, while pending, avoid calling `FindClass`, `GetObjectClass`, `GetMethodID`, `IsInstanceOf`, `NewObject`, `NewStringUTF`, `CallObjectMethod`, `CallStaticIntMethod`, or any other sequence of JNI operations not permitted. If you want to check the class of the throwable with `IsInstanceOf`, you must **clear the pending state first**, then call it.

Non-JNI C code such as `free()`, `fclose()`, or releasing an application-created mutex is not prohibited by the list of JNI functions, but native cleanup must still uphold its contract and must not cause a new error that masks the original exception.

### 4.1. Three common handling approaches

**A. Propagate:** leave the exception pending, release all resources that can be safely released, then return. The Java caller receives the exact original exception.

**B. Recover:** retrieve the throwable if needed, clear pending, verify the error type, and produce a valid fallback result. Apply only to errors **explicitly permitted to be recovered from**. For `OutOfMemoryError`, `LinkageError`, or unexpected errors, do not "swallow" them by default.

**C. Translate/rethrow:** retrieve the throwable, clear pending, inspect or create new context using ordinary JNI APIs, then `Throw` or `ThrowNew` so Java receives the exception. If you want to keep the original error object, use `Throw(env, throwable)` after clearing and delete the temporary local reference at the right time.

In all three approaches, you must clearly decide ownership of local/global references, JNI-acquired pointers, and C heap allocations.

### 4.2. `ExceptionDescribe` is not a harmless logger

`ExceptionDescribe(env)` prints the exception and stack trace to a system error-reporting channel (usually `stderr`), but **at the same time clears the pending exception**. Therefore:

```c
if ((*env)->ExceptionCheck(env)) {
    (*env)->ExceptionDescribe(env); /* Prints and CLEARS pending. */
    return 0; /* Java may no longer receive the original exception. */
}
```

This is an **anti-pattern if the goal is to propagate the original exception**. `ExceptionDescribe` is useful for debugging, but you must understand its side effect before using it. To preserve the exception, you can leave it pending and return; there is no need to print the stack trace yourself from native code.

### 4.3. `ExceptionClear` also does not destroy the `Throwable` object whose local ref you obtained

Valid sequence to handle a specific exception:

```c
jthrowable saved = (*env)->ExceptionOccurred(env);
if (saved != NULL) {
    (*env)->ExceptionClear(env);

    /* Cleared: now ordinary JNI APIs may be called
       to inspect saved if truly needed. */

    /* ... or Throw(env, saved) to rethrow the old exception ... */

    (*env)->DeleteLocalRef(env, saved);
}
```

This code snippet only illustrates the sequence, **not a standalone translation unit**. `ExceptionClear` changes the pending state; `saved` remains a valid local reference within the current scope until it is deleted or the native method returns. Conversely, `DeleteLocalRef(env, saved)` does not automatically clear the pending exception.

## 5. Complete Java 17 + C11 example: propagate, observe, recover

We create three native methods that receive the same input string and call back into the Java method `parsePositive`:

1. `nativeCheckAndPropagate` uses **`ExceptionCheck`** to detect an error and let Java receive the exception.
2. `nativeObserveAndPropagate` uses **`ExceptionOccurred`** to obtain the local `jthrowable`, deletes the local ref, and still leaves the exception pending.
3. `nativeRecoverFormat` retrieves the throwable, clears pending, verifies the error is specifically of type `NumberFormatException` and then returns the sentinel `-1`; if it is another error, it rethrows the original throwable.

Here `parsePositive` defines a valid number as a **positive** integer (greater than 0), so `-1` can be reserved as a fallback result. For real-world APIs where negative numbers are valid, **do not** use a sentinel that collides with data; return a separate status or a Java result object instead.

### 5.1. File `ExceptionProbe.java`

```java
public final class ExceptionProbe {
    static {
        System.loadLibrary("exceptionprobe");
    }

    private ExceptionProbe() {}

    private static int parsePositive(String text) {
        int value = Integer.parseInt(text);
        if (value <= 0) {
            throw new NumberFormatException("must be positive");
        }
        return value;
    }

    private static native int nativeCheckAndPropagate(String text);
    private static native int nativeObserveAndPropagate(String text);
    private static native int nativeRecoverFormat(String text);

    public static void main(String[] args) {
        System.out.println(
            "check-good=" + nativeCheckAndPropagate("42"));

        try {
            nativeCheckAndPropagate("bad");
        } catch (NumberFormatException error) {
            System.out.println(
                "check-error=" + error.getClass().getSimpleName());
        }

        System.out.println(
            "occurred-good=" + nativeObserveAndPropagate("21"));

        try {
            nativeObserveAndPropagate("bad");
        } catch (NumberFormatException error) {
            System.out.println(
                "occurred-error=" + error.getClass().getSimpleName());
        }

        System.out.println(
            "recover-good=" + nativeRecoverFormat("7"));
        System.out.println(
            "recover-error=" + nativeRecoverFormat("bad"));
        System.out.println(
            "recover-negative=" + nativeRecoverFormat("-3"));
    }
}
```

There are no races or external data dependencies: the parser is a pure static Java method using `Integer.parseInt`. The string `"bad"` always causes `NumberFormatException`; `"-3"` parses as a negative number and is then rejected by the problem's contract.

### 5.2. Generating the JNI header with `javac -h`

In the directory containing the Java source:

```bash
javac -h . ExceptionProbe.java
```

The command generates `ExceptionProbe.class` and `ExceptionProbe.h`. The corresponding prototypes look like:

```c
JNIEXPORT jint JNICALL
Java_ExceptionProbe_nativeCheckAndPropagate(
    JNIEnv *, jclass, jstring);

JNIEXPORT jint JNICALL
Java_ExceptionProbe_nativeObserveAndPropagate(
    JNIEnv *, jclass, jstring);

JNIEXPORT jint JNICALL
Java_ExceptionProbe_nativeRecoverFormat(
    JNIEnv *, jclass, jstring);
```

This is an **illustrative signature excerpt**; the full C file below includes the actual header generated by `javac -h`. If you add a package, rename the class, or overload a native method, re-run this step to avoid mismatched symbol names/descriptors.

### 5.3. File `ExceptionProbe.c`

```c
#include "ExceptionProbe.h"

static jmethodID find_parser(JNIEnv *env, jclass clazz) {
    return (*env)->GetStaticMethodID(
        env, clazz, "parsePositive", "(Ljava/lang/String;)I");
}

/*
 * A. Only need to know whether an error is pending.
 * Leave the exception intact and return to Java.
 */
JNIEXPORT jint JNICALL
Java_ExceptionProbe_nativeCheckAndPropagate(
    JNIEnv *env, jclass clazz, jstring text) {

    jmethodID parser = find_parser(env, clazz);
    if (parser == NULL) {
        return 0; /* Lookup error: let pending exception propagate up. */
    }

    jint value = (*env)->CallStaticIntMethod(
        env, clazz, parser, text);

    if ((*env)->ExceptionCheck(env)) {
        return 0; /* Discard value, Java will receive the exception. */
    }

    return value;
}

/*
 * B. Retrieve the error object, but do not clear the pending state.
 * Delete the local reference returned by ExceptionOccurred.
 */
JNIEXPORT jint JNICALL
Java_ExceptionProbe_nativeObserveAndPropagate(
    JNIEnv *env, jclass clazz, jstring text) {

    jmethodID parser = find_parser(env, clazz);
    if (parser == NULL) {
        return 0;
    }

    jint value = (*env)->CallStaticIntMethod(
        env, clazz, parser, text);

    jthrowable observed = (*env)->ExceptionOccurred(env);
    if (observed != NULL) {
        /* DeleteLocalRef is permitted while an exception is pending. */
        (*env)->DeleteLocalRef(env, observed);
        return 0; /* Pending exception remains. */
    }

    return value;
}

/*
 * C. Recover only for NumberFormatException.
 * Other exceptions are rethrown as the exact same object.
 */
JNIEXPORT jint JNICALL
Java_ExceptionProbe_nativeRecoverFormat(
    JNIEnv *env, jclass clazz, jstring text) {

    /* Resolve class before the callback can throw an exception. */
    jclass expected = (*env)->FindClass(
        env, "java/lang/NumberFormatException");

    if (expected == NULL) {
        return 0;
    }

    jmethodID parser = find_parser(env, clazz);
    if (parser == NULL) {
        (*env)->DeleteLocalRef(env, expected);
        return 0;
    }

    jint value = (*env)->CallStaticIntMethod(
        env, clazz, parser, text);

    if (!(*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, expected);
        return value;
    }

    jthrowable pending = (*env)->ExceptionOccurred(env);
    if (pending == NULL) {
        (*env)->DeleteLocalRef(env, expected);
        return 0; /* Do not handle when throwable is missing. */
    }

    (*env)->ExceptionClear(env);

    /* Call IsInstanceOf only after clearing. */
    jboolean isFormatError = (*env)->IsInstanceOf(
        env, pending, expected);

    (*env)->DeleteLocalRef(env, expected);

    if ((*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, pending);
        return 0; /* Keep the new exception if inspection fails. */
    }

    if (isFormatError == JNI_TRUE) {
        (*env)->DeleteLocalRef(env, pending);
        return -1; /* Valid fallback for the positive value domain. */
    }

    /* Error outside allowed type: preserve the original throwable. */
    (void)(*env)->Throw(env, pending);
    (*env)->DeleteLocalRef(env, pending);
    return 0;
}
```

Every important detail in the C file:

- `GetStaticMethodID` retrieves a `jmethodID`, **not** a local reference; do not call `DeleteLocalRef` on a `jmethodID`. The descriptor string `(Ljava/lang/String;)I` means it takes a `java.lang.String` and returns `int`.
- `clazz` is the class reference passed by the JVM to a `static` native method. The example does not have to call `FindClass` itself to locate the class containing the parser in the first two methods.
- When `CallStaticIntMethod` calls the parser and it throws an error, `value` is no longer trustworthy. `nativeCheckAndPropagate` uses `ExceptionCheck` and returns; **it does not call `ExceptionClear`**.
- `nativeObserveAndPropagate` calls `ExceptionOccurred` exactly once; if there is a `jthrowable`, it deletes the local ref. The pending exception **is not lost**.
- `nativeRecoverFormat` prepares the local `jclass expected` **before the callback**; calling `FindClass` only after there is already a pending exception would violate JNI rules. When an exception occurs, it retrieves `pending`, clears, and then calls `IsInstanceOf`.
- `IsInstanceOf` allows handling `NumberFormatException` specifically. Only errors permitted by the contract are converted to `-1`. If it is another exception type, `Throw(env, pending)` rethrows the same object and `DeleteLocalRef` deletes the temporary handle.
- After a successful `Throw`, the exception is pending again; `DeleteLocalRef` is still in the permitted API group in this state. In a production library, you must also handle the special case where `Throw` reports an error (negative value) according to the library's error policy.
- If class or method lookup fails, the return branches preserve the exception reported by JNI. When holding a valid local reference, the function cleans it up before returning; do not make new JNI lookups on the error path.

The sample program is written with a deterministic callback and minimal resources. In real applications, there may be native mutexes, file descriptors, buffers from `GetStringUTFChars`, local frames, and heap allocations that must also be released on both the success and exception branches.

### 5.4. Compiling and running (Linux, JDK 17+)

Place `ExceptionProbe.java` and `ExceptionProbe.c` in the same directory. Set the `JAVA_HOME` variable to the JDK in use so that `$JAVA_HOME/include/jni.h` exists. Compile:

```bash
javac -h . ExceptionProbe.java

cc -std=c11 -Wall -Wextra -Wpedantic -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  ExceptionProbe.c -o libexceptionprobe.so

java -Djava.library.path=. ExceptionProbe
```

**Expected stdout, exact for the inputs in `main`:**

```text
check-good=42
check-error=NumberFormatException
occurred-good=21
occurred-error=NumberFormatException
recover-good=7
recover-error=-1
recover-negative=-1
```

This output illustrates the difference between **keeping pending** (Java catch receives the exception) and **deliberate clearing** (Java receives the fallback number). On Windows/macOS, the library requires the corresponding OS's file extension, compiler flags, and JNI header include paths; Linux commands cannot be copied verbatim to MSVC. If you encounter `UnsatisfiedLinkError`, check `System.loadLibrary`, `java.library.path`, the JDK/native library architecture, and the newly generated header.

You can enable HotSpot's JNI checks when debugging:

```bash
java -Xcheck:jni -Djava.library.path=. ExceptionProbe
```

`-Xcheck:jni` helps detect many JNI misuse bugs, especially calling invalid functions while an exception is pending. This is a supplementary checking tool, not a replacement for reading the contract and testing error paths.

## 6. Handling resources when a callback throws an exception

Real-world bugs are often not in `ExceptionCheck` itself, but in how cleanup is done after it returns true. For example, a native method holding native memory and a JNI string buffer:

```c
/*
 * Illustrates the structure inside a native method with valid JNI env
 * and jstring input; not a standalone program.
 */
char *scratch = malloc(4096);
if (scratch == NULL) {
    /* Can report OutOfMemoryError via JNI before anything is pending. */
    return;
}

const char *utf8 = (*env)->GetStringUTFChars(env, input, NULL);
if (utf8 == NULL) {
    free(scratch);  /* No JNI buffer to release. */
    return;
}

/* Work that may call back into Java and throw an exception. */
(*env)->CallVoidMethod(env, target, callbackMethod);

if ((*env)->ExceptionCheck(env)) {
    (*env)->ReleaseStringUTFChars(env, input, utf8);
    free(scratch);
    return; /* Keep exception pending. */
}

(*env)->ReleaseStringUTFChars(env, input, utf8);
free(scratch);
```

This snippet requires including `<stdlib.h>` and having valid `target`/`callbackMethod` prepared by the owning program; it only describes **the cleanup path**, and is not advertised as a standalone compilable C file.

Remember that:

- `ReleaseStringUTFChars` must be paired with `GetStringUTFChars` if a buffer was obtained; `DeleteLocalRef` does not replace this release operation.
- `free(scratch)` is the C allocator's responsibility, distinct from deleting a local JNI reference.
- When a JNI callback creates a pending exception, `ReleaseStringUTFChars` is in the group of functions permitted to be called for cleanup.
- If a JNI monitor was acquired with `MonitorEnter`, you must make sure to call `MonitorExit` exactly once. Do not continue calling Java methods to "close" resources while an exception is pending.
- For temporary local refs created by `NewStringUTF`, `FindClass`, or `GetObjectClass`, call `DeleteLocalRef` when they are no longer needed. In particular, a local `jthrowable` obtained from `ExceptionOccurred` also needs cleanup if it is not returned out.
- If `PushLocalFrame` succeeded, you must call `PopLocalFrame` before leaving the scope when managing refs by frame, including on the error path; only use the exact APIs permitted while pending.

A good practical design usually centralizes cleanup in a single unified branch, controls the release order, and only returns after no caller-owned native resources remain.

## 7. When do you need to retrieve the `Throwable` object?

Most JNI calls only need to know success or failure; `ExceptionCheck` is simpler. `ExceptionOccurred` makes sense when the error object itself is **data to resolve the handling policy**.

Reasonable cases:

1. **Error classification:** need to distinguish `NumberFormatException` from unexpected exceptions before choosing a fallback. Retrieve the throwable, clear, then `IsInstanceOf` with a prepared class.
2. **Keeping and rethrowing the exact exception:** when you need to complete cleanup that involves additional normal processing after clearing, you can keep the local `jthrowable` and then call `Throw` when done. If only simple cleanup is needed, keeping it pending and returning is cleaner.
3. **Translating the exception into another wrapper:** you can clear, construct a new Java throwable using `ThrowNew`/an appropriate constructor, and attach the cause according to policy. The sequence must avoid calling JNI APIs that are prohibited while pending. You should not lose the stack trace/cause without reason.
4. **Managing errors on a native-attached worker thread:** if a native thread has no direct Java caller waiting for an exception, the code must have an error-reporting channel for the owner. This requires dedicated design regarding JavaVM, attaching, local/global refs, synchronization, and thread rules; merely calling `ExceptionOccurred` does not automatically transfer an exception to another thread.
5. **Controlled diagnostics:** when you genuinely need the exception's type/message/stack, you must clear before ordinary JNI method calls, then handle or rethrow according to policy. Do not let debug code silently alter production behavior.

Do not keep a local `jthrowable` after the native method finishes or pass it to another thread. To keep a Java object long-term, you need a global reference via `NewGlobalRef` (once pending has been properly handled); then `DeleteGlobalRef` at the appropriate time. A global ref keeps the object alive, so it must not be lost.

## 8. Coordinating `Throw`, `ThrowNew`, `ExceptionClear`, and `ExceptionDescribe`

| API | Meaning | Effect on pending state |
| --- | --- | --- |
| `ExceptionCheck` | Boolean check | Does not clear |
| `ExceptionOccurred` | Retrieve local `jthrowable` | Does not clear |
| `ExceptionClear` | Clear current exception state | Clears; Java no longer automatically receives that error |
| `ExceptionDescribe` | Print exception and stack trace for debugging | **May clear pending as a side effect described in the JNI spec** |
| `Throw(env, throwable)` | Set an existing Throwable object as the exception to throw | Sets that throwable as pending; returns status |
| `ThrowNew(env, clazz, message)` | Create an exception from class and message | Sets new exception as pending; message uses Modified UTF-8 |

### 8.1. Do not create a second exception while the first exception is still pending

Anti-pattern:

```c
(*env)->CallVoidMethod(env, receiver, method); /* May throw. */
/* Wrong: looking up a class and throwing another error without checking pending. */
jclass c = (*env)->FindClass(env, "java/lang/IllegalStateException");
(*env)->ThrowNew(env, c, "wrapper error");
```

This snippet is **an incorrect illustration**, has no cleanup, and does not compile standalone. If the callback already threw an error, `FindClass` is outside the list of JNI calls permitted while pending. The right way starts with `ExceptionCheck`, then:

- Propagate: keep pending, clean up resources, return.
- Translate: retrieve the exception if you want to preserve the cause, clear, find the class/instantiate the new exception, and ensure it does not mask unexpected errors.
- Recover: only when permitted by the contract, clear after retaining necessary information, then return a valid fallback.

### 8.2. The difference between "observed" and "handled"

`ExceptionOccurred` does not mean the exception has been caught/consumed. JNI still keeps the error pending. Merely reading the local `jthrowable` and deleting that reference also does not change the pending state.

`ExceptionCheck` also has no automatic Java "try-catch" mechanism. It only returns a boolean so native code can decide the next path.

`ExceptionClear` actually discards the pending exception; calling it without a handling policy turns an error into a false success. If an API still returns an old numeric result when an exception occurs, that result is not allowed to be treated as valid just because the error was cleared.

## 9. Edge cases and common mistakes

| Mistake or wrong assumption | Consequence | Fix |
| --- | --- | --- |
| Calling `ExceptionOccurred` after every JNI call just for a boolean | Creates unnecessary local refs on error | Use `ExceptionCheck` if throwable is not needed |
| Calling `ExceptionOccurred` and not calling `DeleteLocalRef` | Accumulates local references in long-running functions | Release each local handle |
| Using the `jint` value from `CallIntMethod` after the callback throws | Unreliable data | Check immediately; discard result and clean up |
| Concluding there is an exception upon seeing `NULL` from an array read | A `null` element is also valid | Check `ExceptionCheck` if you need to distinguish |
| Calling `GetObjectClass`/`FindClass` while pending | Violates JNI contract | Deliberately clear before the inspection step |
| Calling `ExceptionDescribe` and expecting the error to propagate to Java | Pending may have been cleared | Do not use to propagate; understand side effect when debugging |
| Calling `ExceptionClear` to continue running without checking the error type | Swallows errors, misses `OutOfMemoryError` or logic errors | Selective recovery; rethrow unexpected |
| Using `ThrowNew` to "wrap" an error while the callback is still pending | Prohibited JNI operation / overlapping error | Retrieve/clear before constructing wrapper |
| Calling `DeleteLocalRef` and thinking the exception is cleared | Java still receives the pending exception | Distinguish handle lifetime from pending state |
| Passing `JNIEnv *`/local `jthrowable` to another thread | Wrong thread/lifetime | Attach separate thread; use global ref per contract |
| Failing to release `GetStringUTFChars` on exception | Native buffer held/leaked | Release in permitted cleanup |
| Failing to pop local frame on exception path | Local refs persist for a long time | Pop frame after a successful push |
| Using `ExceptionCheck` as a microsecond-accurate cancel signal | Async exception can appear between checks | Place checks appropriately; cancellation has its own contract |
| Making repeated JNI calls while pending to log more details | Can lead to undefined behavior/crash | Only call permitted APIs and return |
| Catching every `Throwable` as a normal parse error | Masks system errors | Only recover errors specified by the business contract |

### 9.1. Pay attention to JNI results and C error codes

C's `errno` error code, return codes from C libraries, and Java pending exceptions are **three different mechanisms**. `ExceptionCheck` does not report that `fopen()` failed; `errno != 0` does not mean Java is throwing an exception. If calling a C library encounters an error, the JNI layer can proactively construct a Java exception using `ThrowNew` according to a defined mapping, but this must be done when no other exception is pending.

Similarly, `JNI_FALSE` from `ExceptionCheck` does not prove all native operations succeeded: it only proves **there is no Java exception pending at the time of the check**. C code still needs to check null pointers, bounds, closed resources, return codes, and lifetimes.

## 10. Testing JNI behavior on errors

A test suite should cover:

1. **No error:** `nativeCheckAndPropagate("42")` returns `42`; `nativeObserveAndPropagate("21")` returns `21`; `nativeRecoverFormat("7")` returns `7`.
2. **Error present, propagate via Check:** `nativeCheckAndPropagate("bad")` must throw `NumberFormatException` to Java, not return `0` as a success result.
3. **Error present, retrieve Throwable:** `nativeObserveAndPropagate("bad")` must also throw the same exception type, even though the local reference obtained from `ExceptionOccurred` was deleted.
4. **Recover matching type:** `nativeRecoverFormat("bad")` and `nativeRecoverFormat("-3")` return `-1`; no pending exception remains after the function returns.
5. **Outside allowed error type:** when the callback simulates `IllegalStateException` or `OutOfMemoryError`, the recover path must preserve/propagate the exception up to Java, not turn it into `-1`.
6. **Cleanup:** create JNI local refs and `GetStringUTFChars` buffers before the callback, deliberately trigger an exception; verify every return path properly releases resources.
7. **Long loop:** use many callbacks, check after JNI calls that can fail; do not accumulate `jthrowable` local refs in the loop.
8. **Thread isolation:** generate exceptions on multiple Java threads, ensuring each check uses that thread's own `JNIEnv *`.
9. **Debug behavior:** enable `-Xcheck:jni` when supported by the JVM to detect prohibited JNI calls while pending and invalid references.

A Java test snippet independent of the article's JNI implementation can be written as:

```java
// Example is only a snippet inside an existing test class,
// not a standalone source file.
try {
    nativeCheckAndPropagate("bad");
    throw new AssertionError("Expected NumberFormatException");
} catch (NumberFormatException expected) {
    // Pending exception was received and handled by Java.
}
```

JUnit can be used in a real project, but the sample above already has `main` and deterministic stdout for quick verification.

## 11. Decision workflow when a pending exception occurs

```text
After a JNI call that can raise an exception
                |
                v
   Clear error sentinel? -------- Yes ---> enter error branch
                |                            |
                No                           |
                |                            |
                v                            v
      ExceptionCheck(env) ? <--------- is pending?
          |          |
       FALSE        TRUE
          |          |
          v          v
   Use result    Need Throwable object?
                    |             |
                   No            Yes
                    |             |
                    v             v
                 Safe        ExceptionOccurred()
                 cleanup          |
                    |             v
                    |       Hold local ref
                    |       (manage lifetime)
                    |             |
                    +-------+-----+
                            |
                            v
             Propagate or Recover/Translate?
                    |                 |
                Propagate         Recover/Translate
                    |                 |
             Keep pending         Deliberately clear
             Cleanup, return      Inspect/handle/rethrow
                                      |
                                      v
                              Clean local refs, return
```

This is a mental model diagram, not a replacement for each API's contract. If a return value indicates an error without a pending exception, the native method must still handle the error according to that API; if the return value is normal but the Java callback threw, the pending exception must take priority.

Checklist before handoff:

- After every `Call<Type>Method` or JNI API that can fail, does the check branch distinguish **pending exception** and **result value**?
- Do you only need to know if there is an error, or do you truly need the `jthrowable` object? If you only need a boolean, use `ExceptionCheck`.
- If using `ExceptionOccurred`, is the local reference deleted at the right time? Is the ref used after deletion or across another thread?
- Do any ordinary JNI calls happen while an exception is pending?
- Is `ExceptionClear` called **only when** actually choosing recover/translate, and does it avoid swallowing unexpected `Error`s?
- Is `ExceptionDescribe` used in production causing pending to be lost automatically?
- Are resources from JNI and the C allocator handled on all success/exception paths?
- For long native loops, are error checkpoints reasonable and free of extra local ref creation?
- Does the fallback result have a clear value domain, unambiguous with valid data?

**Rule to remember:** `ExceptionCheck` answers "is there an exception?" with low reference-management overhead. `ExceptionOccurred` answers "which exception?" and creates a local reference when an error is present. **Neither clears the pending state.** After detecting an error, clean up using permitted APIs and return so Java receives the error, or perform a deliberate clear/inspect/rethrow sequence.

### References

- [Oracle Java SE 17 — JNI Design Overview, Java Exceptions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html)
- [Oracle Java SE 17 — JNI Functions: ExceptionCheck, ExceptionOccurred, ExceptionClear, Throw](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
- [Android Developers — JNI Tips: Exceptions](https://developer.android.com/ndk/guides/jni-tips)
- [Oracle Java SE 17 — javac -h to generate JNI headers](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
