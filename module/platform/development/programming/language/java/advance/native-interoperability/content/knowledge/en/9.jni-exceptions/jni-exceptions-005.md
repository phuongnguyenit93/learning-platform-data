# Propagating Exceptions to Java or Clearing and Handling Them Under an Explicit Policy in JNI

## 1. Objectives and Error Model at the Java ↔ Native Boundary

In Java, when a method throws a `Throwable`, control is transferred to the appropriate `catch` block or continues propagating up the call stack. However, when C/C++ code calls into Java through the **Java Native Interface (JNI)**, a Java exception **does not automatically perform a control-flow jump in C**. The JVM records a **pending exception** on the **current thread**; native code continues executing C unless you explicitly check and branch.

The two main policies that a JNI programmer must choose **explicitly** are:

1. **Propagate the exception to Java (propagate):** keep the pending exception intact, clean up resources using permitted operations, and **return control from the native method to the JVM**. The JVM will let Java code see the exception and handle it with `catch` or continue propagating it upward.
2. **Clear and handle (clear and handle):** determine which errors are **allowed to recover** or need to be **translated into a business exception**; use `ExceptionClear` to remove the pending state before calling normal JNI APIs, then return a fallback, record failure according to the contract, or create/`Throw` a new exception. Errors that **do not belong to the policy** must continue to be propagated and must not be silently swallowed.

**This lesson does not encourage "calling ExceptionClear whenever an error occurs".** Clearing an exception without a recovery rule loses the error signal, easily produces corrupted data, or causes the system to keep running in an invalid state.

After this lesson, you will be able to distinguish `ExceptionCheck`, `ExceptionOccurred`, `ExceptionClear`, `Throw`, and `ThrowNew`, identify which JNI calls are permitted while an exception is pending, write a safe cleanup path, and run a Java 17 + C example for all three scenarios: **propagate**, **selective fallback**, and **translate while preserving the cause**.

## 2. What Is a Pending Exception?

Consider a C-style JNI call:

~~~c
jint result = (*env)->CallStaticIntMethod(
    env, clazz, methodId, divisor
);
~~~

If the called Java method throws `ArithmeticException`, the JVM records the pending exception on the calling thread. **C code does not automatically stop** at this line. The return value of `CallStaticIntMethod` **must not be used as a valid computation result** when an exception is pending; it must be checked immediately:

~~~c
if ((*env)->ExceptionCheck(env)) {
    /* A Java exception is currently pending. */
    return 0;  /* Example in a JNI method returning jint. */
}
return result;
~~~

The snippet above is only an **excerpt** inside a JNI method that has a valid `JNIEnv *env` and `methodId`, not a standalone program.

The right mental model:

~~~text
Java caller
   |
   | calls nativeMethod(...)
   v
C/JNI nativeMethod
   |
   | CallStaticIntMethod(...) calls Java helper
   v
Java helper throws ArithmeticException
   |
   v
Return to C code, thread has a pending exception
   |
   +-- Policy A: permitted cleanup → return to JVM
   |       |
   |       v
   |     Java caller catches ArithmeticException
   |
   +-- Policy B: identify error → ExceptionClear
           |
           +-- expected error → return valid fallback
           |
           +-- error to translate → create new exception with old cause → Throw
           |
           +-- other error → re-Throw original → return to Java
~~~

**A pending exception is not a C error pointer, an `errno` return code, or a C++ exception.** It is the JVM's exception state on the current JNI thread. C++ `try/catch` does not automatically catch a pending Java exception caused by `Call<Type>Method`; and an unexpected C++ exception should never be allowed to escape across the JNI boundary.

### 2.1. Does Returning `0`/`NULL` While an Exception Is Pending "Swallow the Error"?

No. If a native method returns to the JVM **while an exception is still pending**, Java receives the exception rather than treating `0` or `NULL` as a normal return value.

For example, a JNI C function returning `jint` can be written as:

~~~c
if ((*env)->ExceptionCheck(env)) {
    return 0;  /* Placeholder value at the C ABI; Java will see the exception. */
}
~~~

Conversely, if `ExceptionClear` has already been called and then `0` is returned, **there is no longer a pending exception**. Java may receive `0` as a valid result. Therefore, after clearing, there must be a **concrete business contract**: a meaningful fallback, a separate error status, or a replacement exception.

## 3. Exception-Related JNI APIs

| JNI API | Effect | Changes pending exception? |
|---|---|---|
| `ExceptionCheck(env)` | Checks whether an exception is pending, returns `JNI_TRUE`/`JNI_FALSE` | Does **not** clear; does not create a local reference for the throwable |
| `ExceptionOccurred(env)` | Gets a `jthrowable` local reference to the pending exception (or `NULL` if none) | Does **not** clear |
| `ExceptionClear(env)` | Clears the pending exception state on the thread | **Yes**; use before handling errors with normal JNI APIs |
| `ExceptionDescribe(env)` | Prints error details and stack trace to the diagnostic channel | **Yes: it clears the pending exception as a side effect!** |
| `Throw(env, throwable)` | Sets an existing `Throwable` object as the exception to be thrown | Creates pending state; call when no exception is pending |
| `ThrowNew(env, clazz, message)` | Creates and throws an exception from a `Throwable` class and message (modified UTF-8) | Creates pending state; should prepare the class/call in a valid state |

Distinguish two operations that are often confused:

~~~c
/* Does not create a local ref; suitable when you only want to know whether an error occurred. */
jboolean hasError = (*env)->ExceptionCheck(env);

/* Creates a jthrowable local ref if an exception is currently pending. */
jthrowable error = (*env)->ExceptionOccurred(env);
~~~

`ExceptionOccurred` is used when you need to **inspect the exception type, record the cause, or rethrow**. If a local handle is obtained, its lifecycle must be managed; call `DeleteLocalRef(env, error)` when no longer needed, or let the JVM reclaim it when the native method returns.

**Important warning:** Do not use `ExceptionDescribe` as a "side-effect-free logger" and then `return` expecting Java to catch the original exception. According to the JNI specification, `ExceptionDescribe` **prints and clears** the pending exception. If you only need to know whether an error occurred, use `ExceptionCheck`; if you need to preserve the cause, use `ExceptionOccurred` and handle it according to the chosen policy.

## 4. The "Do Not Arbitrarily Call JNI While an Exception Is Pending" Rule

Once a Java exception is pending, **most JNI APIs are not permitted to be called**; certain APIs used to check status and release resources are exceptions.

The groups **permitted** by the JNI specification include:

- Exception checking and control: `ExceptionCheck`, `ExceptionOccurred`, `ExceptionDescribe`, `ExceptionClear`.
- Releasing references: `DeleteLocalRef`, `DeleteGlobalRef`, `DeleteWeakGlobalRef`.
- Releasing string/array access regions: `ReleaseStringChars`, `ReleaseStringUTFChars`, `ReleaseStringCritical`, `Release<Type>ArrayElements`, `ReleasePrimitiveArrayCritical`.
- Cleaning up JNI state/scope: `MonitorExit`, `PushLocalFrame`, `PopLocalFrame`, and `DetachCurrentThread` under the conditions of those APIs.

This list **does not include** `FindClass`, `GetMethodID`, `GetFieldID`, `NewStringUTF`, `NewObject`, `CallObjectMethod`, `CallStaticIntMethod`, or `ThrowNew`. If you want to call normal APIs to recover or create another exception, **you must clear the exception first**, and then check for new errors that may arise.

Incorrect example (**do not run**):

~~~c
/* WRONG: after a CallStaticIntMethod that throws an exception,
   continuing to call FindClass while the exception is still pending. */
jint answer = (*env)->CallStaticIntMethod(env, clazz, methodId, 0);
jclass otherClass = (*env)->FindClass(env, "java/lang/String");
return answer;
~~~

Correct example for the **original error propagation path**:

~~~c
jint answer = (*env)->CallStaticIntMethod(env, clazz, methodId, 0);
if ((*env)->ExceptionCheck(env)) {
    /* Cleanup refs, release buffers if any; DO NOT clear. */
    return 0;
}
return answer;
~~~

These are all excerpts inside a JNI method, not standalone C files. In real code, always check the result of obtaining `methodId` beforehand.

**When native resources have been acquired:** clean them up using the exact release mechanism permitted while pending; for example `ReleaseStringUTFChars` or `DeleteLocalRef`. `ExceptionClear` **does not** free a `malloc` buffer, file descriptor, JNI global reference, or local frame. Those resources must be managed separately.

## 5. Policy A: Keep Pending and Propagate the Original Error to Java

This is the default choice when JNI is only a thin bridge layer and **there is no explicit recovery rule**.

Pattern in a JNI method returning `jint`:

~~~c
jmethodID id = (*env)->GetStaticMethodID(
    env, clazz, "divide", "(I)I"
);
if (id == NULL) {
    /* Usually has a pending NoSuchMethodError: let Java receive the error. */
    return 0;
}

jint value = (*env)->CallStaticIntMethod(env, clazz, id, 0);
if ((*env)->ExceptionCheck(env)) {
    /* Java helper threw an error; clean up resources then return.
       Do not call ExceptionClear. */
    return 0;
}
return value;
~~~

**This is only an excerpt**; full runnable code is in the hands-on section. Note:

1. `GetStaticMethodID` can fail and usually leaves a pending Java exception; do not call `CallStaticIntMethod` when `id == NULL`.
2. `CallStaticIntMethod` may invoke a Java method that throws an error. C code must check `ExceptionCheck` **before using the result**.
3. If an error occurs, `return` from the native method so the JVM passes the exception back to Java. Java `catch` can handle the exact **same original error type and message**; there is no need to create an additional exception in JNI.
4. Calling `return 0` is not a false success, as long as the pending exception remains. If cleared before returning, the meaning is completely different.

Example Java caller:

~~~java
try {
    int value = NativeExceptionPolicy.propagate(0);
    System.out.println(value); // Does not run if the Java exception is propagated back.
} catch (ArithmeticException ex) {
    System.out.println("Caught: " + ex.getMessage());
}
~~~

This is an excerpt from the program that will be written in section 8. Java receives and handles the exception at the appropriate place, while JNI is only responsible for **preserving and propagating** it.

## 6. Policy B: Clear and Return Fallback — But Only for Expected Errors

Sometimes the Java layer specifies an error that is **recoverable**: for example, a trial calculation that divides by 0 is allowed to use a default value. With such a requirement, the native layer can:

1. Identify the error type allowed for recovery, such as only `ArithmeticException`.
2. **Hold a local reference to the throwable** using `ExceptionOccurred` while the error is still pending.
3. Call `ExceptionClear` before using `IsInstanceOf` or any normal JNI API.
4. If it matches the expected type: clean up refs and return the fallback according to the contract.
5. If it is another type (e.g., `OutOfMemoryError`, `NoSuchMethodError`): **rethrow the original exception** using `Throw`, then return.

Diagram:

~~~text
CallStaticIntMethod -> pending exception?
    |
    +-- No  --> use computation result
    |
    +-- Yes --> original = ExceptionOccurred()
                |
                v
             ExceptionClear()
                |
                v
          IsInstanceOf(original, ArithmeticException)
                |
                +-- true  --> cleanup --> return fallback
                |
                +-- false --> Throw(original) --> cleanup --> return
                               (Java still receives the unexpected error)
~~~

Why **not clear unconditionally**? An unexpected exception may indicate a class loader configuration error, missing method, resource exhaustion, bug in the Java helper, or inconsistent state. If you swallow it and return a fallback, the system may continue with corrupted data.

### 6.1. Why Must the Throwable Be Obtained Before Clearing?

`ExceptionClear` only clears **the currently thrown exception state**; it does not automatically make a copy or guarantee you can retrieve the cleared error. Therefore, when you need to inspect or rethrow the error, obtain the reference first:

~~~c
jthrowable original = (*env)->ExceptionOccurred(env);
if (original == NULL) {
    /* No throwable to analyze; decide the error based on context. */
    return 0;
}

(*env)->ExceptionClear(env);

/* Only now call normal JNI APIs on original. */
/* Finally: DeleteLocalRef(env, original). */
~~~

This is an excerpt. `ExceptionOccurred` returns a local reference; after clearing, `original` still references the throwable object until the local ref goes out of scope. However, **do not keep `original` in a C global variable** for use after the native method returns; storing across multiple calls requires a properly managed global reference.

### 6.2. Why Should the Recoverable Class Be Looked Up Before the Java Call?

`IsInstanceOf` requires a `jclass`. `FindClass` cannot be called while an exception is still pending. Therefore, the hands-on program **looks up `java/lang/ArithmeticException` before calling the Java helper**, and then only checks the throwable type after clearing.

This approach distinguishes "expected error on the allowlist" from other errors without making invalid JNI calls in the pending state.

## 7. Policy C: Clear and Translate to Another Exception While Preserving the Cause

Sometimes a low-level error does not fit the public API: a component receiving an "invalid" argument may want to report `IllegalArgumentException` to the Java caller, even though the internal Java helper throws `ArithmeticException`.

If you **change the error type**, you should preserve the **cause chain** instead of destroying the error history:

~~~text
ArithmeticException("divide by zero")    (original error)
             |
             v  JNI capture -> clear -> create IllegalArgumentException
IllegalArgumentException("divisor must not be zero")
             |
             v  cause = ArithmeticException("divide by zero")
Java catches IllegalArgumentException
   -> getCause() can still retrieve the original exception
~~~

JNI can:

1. Look up the target class `java/lang/IllegalArgumentException` and constructor `(Ljava/lang/String;Ljava/lang/Throwable;)V` while no exception is pending.
2. Call the Java helper; if the error belongs to the type to be translated, `ExceptionOccurred` gets `jthrowable original` and then `ExceptionClear`.
3. `NewStringUTF` creates the message; `NewObject` creates `IllegalArgumentException(message, original)`; `Throw` sets the new exception as pending; then clean up local references (permitted while pending) and return.
4. If the original exception does not belong to the specified type: `Throw(original)` to propagate the original error as-is, **do not translate all exceptions**.
5. If constructing the new exception fails (for instance `OutOfMemoryError`), do not arbitrarily clear the new error and continue as if it succeeded.

**`ThrowNew` cannot be used arbitrarily while another exception is still pending.** If you want to replace an error, handle/clear the old error according to policy first. `ThrowNew` is convenient for an exception with a simple message, but if you need to preserve the cause, use a constructor that accepts `Throwable` or chain the cause appropriately via Java/JNI APIs.

An architecturally simpler approach, when JNI does not need to handle the error, is to **let the original exception travel back to Java and translate it at the Java boundary**:

~~~java
static int api(int divisor) {
    try {
        return NativeExceptionPolicy.propagate(divisor);
    } catch (ArithmeticException ex) {
        throw new IllegalArgumentException("divisor must not be zero", ex);
    }
}
~~~

This snippet is **illustrative**, not a method belonging to the hands-on file; in section 8 we will also try translating directly in C. Translating in Java is usually less risky because `try/catch`, constructors, and automatic resource management are available. Only translate in native code when the boundary/architectural contract requires it.

## 8. Complete Example: Java 17 + JNI C with Three Policies

We create one Java class, one JNI C library, and **three native methods**. The Java helper `divide(int divisor)` intentionally throws an error when the divisor is 0 to compare the three policies.

Directory structure:

~~~text
jni-exception-policy/
├── NativeExceptionPolicy.java
├── NativeExceptionPolicy.h       (generated by javac -h)
├── nativeexceptionpolicy.c
├── NativeExceptionPolicy.class   (generated by javac)
└── native library                (generated by compiler per OS)
~~~

### 8.1. Java — File `NativeExceptionPolicy.java`

~~~java
public final class NativeExceptionPolicy {
    static {
        System.loadLibrary("nativeexceptionpolicy");
    }

    private NativeExceptionPolicy() {
    }

    private static int divide(int divisor) {
        if (divisor == 0) {
            throw new ArithmeticException("divide by zero");
        }
        return 20 / divisor;
    }

    public static native int propagate(int divisor);

    public static native int recover(int divisor, int fallback);

    public static native int translate(int divisor);

    public static void main(String[] args) {
        System.out.println("normal propagation = " + propagate(4));

        try {
            propagate(0);
        } catch (ArithmeticException ex) {
            System.out.println(
                "propagated = " + ex.getClass().getSimpleName()
                + ": " + ex.getMessage()
            );
        }

        System.out.println("normal fallback = " + recover(4, -1));
        System.out.println("fallback = " + recover(0, -1));
        System.out.println("normal translation = " + translate(4));

        try {
            translate(0);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                "translated = " + ex.getClass().getSimpleName()
                + ": " + ex.getMessage()
            );
            Throwable cause = ex.getCause();
            System.out.println(
                "cause = " + cause.getClass().getSimpleName()
                + ": " + cause.getMessage()
            );
        }
    }
}
~~~

This is a **complete Java file, compiled with JDK 17+**. The `divide` method is `private static` but can still be found and called by JNI via `GetStaticMethodID`, as long as the name `divide` and descriptor `(I)I` match. There is no direct Java call from `main` to the helper; the three JNI methods themselves call the helper using `CallStaticIntMethod`.

When `divisor == 0`, the helper throws `ArithmeticException("divide by zero")`. When `divisor == 4`, it returns `20 / 4 = 5`. Small numbers are chosen to avoid integer division overflow issues in the example.

### 8.2. Generating the Header with the JDK

Run in the directory containing the Java file:

~~~bash
javac -h . NativeExceptionPolicy.java
~~~

The JDK generates `NativeExceptionPolicy.class` and `NativeExceptionPolicy.h`. The core function declarations in the header look like:

~~~c
JNIEXPORT jint JNICALL Java_NativeExceptionPolicy_propagate
  (JNIEnv *, jclass, jint);

JNIEXPORT jint JNICALL Java_NativeExceptionPolicy_recover
  (JNIEnv *, jclass, jint, jint);

JNIEXPORT jint JNICALL Java_NativeExceptionPolicy_translate
  (JNIEnv *, jclass, jint);
~~~

This is a header **excerpt**; the actual header also has include guards and `#include <jni.h>`. All three Java methods are `static native`, so the second implicit JNI parameter is `jclass`. If `static` were removed in Java, the C signature would have to change to `jobject`.

### 8.3. C — File `nativeexceptionpolicy.c`

~~~c
#include "NativeExceptionPolicy.h"

/* Returns the normal result, or leaves the pending Java exception intact. */
static jint callDivide(JNIEnv *env, jclass clazz, jint divisor) {
    jmethodID method = (*env)->GetStaticMethodID(
        env, clazz, "divide", "(I)I"
    );
    if (method == NULL) {
        /* Keep pending exception, such as NoSuchMethodError. */
        return 0;
    }

    return (*env)->CallStaticIntMethod(
        env, clazz, method, divisor
    );
}

/* A. Do not clear: propagate the original Java exception back to the Java caller. */
JNIEXPORT jint JNICALL Java_NativeExceptionPolicy_propagate(
    JNIEnv *env, jclass clazz, jint divisor
) {
    jint value = callDivide(env, clazz, divisor);
    if ((*env)->ExceptionCheck(env)) {
        return 0; /* Pending exception remains. */
    }
    return value;
}

/* B. Recover only ArithmeticException with an explicit fallback. */
JNIEXPORT jint JNICALL Java_NativeExceptionPolicy_recover(
    JNIEnv *env, jclass clazz, jint divisor, jint fallback
) {
    /* Look up the class for classification BEFORE the call that may throw. */
    jclass arithmetic = (*env)->FindClass(
        env, "java/lang/ArithmeticException"
    );
    if (arithmetic == NULL) {
        return 0; /* Keep error from FindClass. */
    }

    jint value = callDivide(env, clazz, divisor);
    if (!(*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, arithmetic);
        return value;
    }

    /* Capture original while pending; cannot call IsInstanceOf yet. */
    jthrowable original = (*env)->ExceptionOccurred(env);
    if (original == NULL) {
        (*env)->DeleteLocalRef(env, arithmetic);
        return 0;
    }

    (*env)->ExceptionClear(env);

    jboolean expected = (*env)->IsInstanceOf(
        env, original, arithmetic
    );
    if ((*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, original);
        (*env)->DeleteLocalRef(env, arithmetic);
        return 0; /* Keep new error if the check step fails. */
    }

    if (!expected) {
        /* Must not swallow exceptions outside the recovery policy. */
        (void) (*env)->Throw(env, original);
        (*env)->DeleteLocalRef(env, original);
        (*env)->DeleteLocalRef(env, arithmetic);
        return 0;
    }

    /* This is an ArithmeticException allowed for recovery. */
    (*env)->DeleteLocalRef(env, original);
    (*env)->DeleteLocalRef(env, arithmetic);
    return fallback;
}

/* C. Translate ArithmeticException -> IllegalArgumentException, preserving cause. */
JNIEXPORT jint JNICALL Java_NativeExceptionPolicy_translate(
    JNIEnv *env, jclass clazz, jint divisor
) {
    jclass arithmetic = (*env)->FindClass(
        env, "java/lang/ArithmeticException"
    );
    if (arithmetic == NULL) {
        return 0;
    }

    jclass illegal = (*env)->FindClass(
        env, "java/lang/IllegalArgumentException"
    );
    if (illegal == NULL) {
        (*env)->DeleteLocalRef(env, arithmetic);
        return 0;
    }

    jmethodID ctor = (*env)->GetMethodID(
        env, illegal, "<init>",
        "(Ljava/lang/String;Ljava/lang/Throwable;)V"
    );
    if (ctor == NULL) {
        (*env)->DeleteLocalRef(env, illegal);
        (*env)->DeleteLocalRef(env, arithmetic);
        return 0;
    }

    jint value = callDivide(env, clazz, divisor);
    if (!(*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, illegal);
        (*env)->DeleteLocalRef(env, arithmetic);
        return value;
    }

    jthrowable original = (*env)->ExceptionOccurred(env);
    if (original == NULL) {
        (*env)->DeleteLocalRef(env, illegal);
        (*env)->DeleteLocalRef(env, arithmetic);
        return 0;
    }

    (*env)->ExceptionClear(env);

    jboolean expected = (*env)->IsInstanceOf(
        env, original, arithmetic
    );
    if ((*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, original);
        (*env)->DeleteLocalRef(env, illegal);
        (*env)->DeleteLocalRef(env, arithmetic);
        return 0;
    }

    if (!expected) {
        (void) (*env)->Throw(env, original);
        (*env)->DeleteLocalRef(env, original);
        (*env)->DeleteLocalRef(env, illegal);
        (*env)->DeleteLocalRef(env, arithmetic);
        return 0;
    }

    jstring message = (*env)->NewStringUTF(
        env, "divisor must not be zero"
    );
    if (message == NULL) {
        /* If OOM occurs while creating message, let the new error propagate to Java. */
        (*env)->DeleteLocalRef(env, original);
        (*env)->DeleteLocalRef(env, illegal);
        (*env)->DeleteLocalRef(env, arithmetic);
        return 0;
    }

    jthrowable translated = (jthrowable) (*env)->NewObject(
        env, illegal, ctor, message, original
    );
    if (translated != NULL && !(*env)->ExceptionCheck(env)) {
        (void) (*env)->Throw(env, translated);
    }

    /* DeleteLocalRef is permitted while an exception is pending. */
    if (translated != NULL) {
        (*env)->DeleteLocalRef(env, translated);
    }
    (*env)->DeleteLocalRef(env, message);
    (*env)->DeleteLocalRef(env, original);
    (*env)->DeleteLocalRef(env, illegal);
    (*env)->DeleteLocalRef(env, arithmetic);
    return 0;
}
~~~

This is the **entire C file** of the example, not pseudocode. `#include "NativeExceptionPolicy.h"` ensures the exported functions have prototypes matching the JNI header generated from the Java code.

Note the three key points:

- **`propagate`:** if `CallStaticIntMethod` causes an error, C returns **without clearing**. The Java caller catches the exact `ArithmeticException`.
- **`recover`:** looks up `ArithmeticException` first; captures `original` then clears; classifies using `IsInstanceOf`. Only the matching type returns `fallback`, while other types are re-thrown via `Throw` so Java sees them. Normal results are returned intact when there is no exception.
- **`translate`:** looks up both the target exception class and constructor before calling the helper; when receiving the expected error type, clears, creates `IllegalArgumentException(String, Throwable)` with `original` as the **cause**, and uses `Throw` to set the new exception pending. If creating the string or new exception fails, keeps the newly raised error instead of returning a "false success".

In branches that already have a pending exception, only `ExceptionCheck`, `ExceptionOccurred`, `ExceptionClear`, and `DeleteLocalRef` are used. Steps such as `IsInstanceOf`, `NewStringUTF`, `NewObject`, and `Throw` are performed **after clearing** and after checking valid state.

This is an academic example with the expected error condition `divisor == 0`. In real systems, the recoverable error types should be clearly specified; do not automatically treat `OutOfMemoryError`, `LinkageError`, `NoSuchMethodError`, or inconsistent data errors as ignorable cases.

### 8.4. Compiling the Native Library and Running on Each Operating System

You need JDK 17+ with `jni.h`, a C compiler, the `JAVA_HOME` environment variable pointing to the JDK matching the JVM that will run, and the library compiled for the right OS/architecture/ABI.

**Linux with GCC:**

~~~bash
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  nativeexceptionpolicy.c -o libnativeexceptionpolicy.so

java -Djava.library.path=. NativeExceptionPolicy
~~~

**macOS with Clang:**

~~~bash
cc -dynamiclib -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  nativeexceptionpolicy.c -o libnativeexceptionpolicy.dylib

java -Djava.library.path=. NativeExceptionPolicy
~~~

**Windows with MSVC in Developer Command Prompt (`cmd.exe`):**

~~~bat
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" nativeexceptionpolicy.c /Fe:nativeexceptionpolicy.dll

java -Djava.library.path=. NativeExceptionPolicy
~~~

Run only **one set of commands** corresponding to your operating system after running `javac -h . NativeExceptionPolicy.java`. Place `-Djava.library.path=.` before the class name. The logical name `System.loadLibrary("nativeexceptionpolicy")` maps to `nativeexceptionpolicy.dll` (Windows), `libnativeexceptionpolicy.so` (Linux), or `libnativeexceptionpolicy.dylib` (macOS).

**Exact stdout when compiled and loaded successfully:**

~~~text
normal propagation = 5
propagated = ArithmeticException: divide by zero
normal fallback = 5
fallback = -1
normal translation = 5
translated = IllegalArgumentException: divisor must not be zero
cause = ArithmeticException: divide by zero
~~~

Line-by-line explanation:

1. `propagate(4)` does not cause an error; the Java helper returns `20/4 = 5`.
2. `propagate(0)` creates a pending `ArithmeticException`, JNI does not clear it, so Java `catch` receives the original error.
3. `recover(4, -1)` succeeds normally so it returns 5.
4. `recover(0, -1)` clears only the policy-allowed `ArithmeticException`, then returns `-1` as the fallback.
5. `translate(4)` succeeds normally so it returns 5.
6. `translate(0)` converts the confirmed error into `IllegalArgumentException` with a business message.
7. `getCause()` on the new exception still returns `ArithmeticException("divide by zero")`, preserving the origin trace.

**Clear distinction:** The fallback in the example is **not** the `0` returned due to a pending exception; it is **`-1` explicitly decided by the Java caller**. If the JVM encounters another error not permitted for recovery, C lets that error propagate back to Java instead of quietly returning `-1`.

## 9. State Diagram: Where Are Normal JNI APIs Permitted?

~~~text
STATE: CLEAR (no pending exception)
   |
   +-- GetStaticMethodID / CallStaticIntMethod / FindClass ...
   |          |
   |          +-- success --> continue
   |          |
   |          +-- failure --> STATE: PENDING
   |                                  |
   |                                  +-- Policy PROPAGATE
   |                                  |      valid cleanup -> return JNI
   |                                  |      Java catches original exception
   |                                  |
   |                                  +-- Policy RECOVER/TRANSLATE
   |                                         ExceptionOccurred: get original
   |                                         ExceptionClear: STATE=CLEAR
   |                                             |
   |                                             +-- classify exception
   |                                             +-- fallback
   |                                             +-- Throw(original) -> PENDING
   |                                             +-- NewObject + Throw(new) -> PENDING
   |
   +-- normal return when not pending
~~~

Do not use `ThrowNew`/`FindClass`/`NewObject`/`Call...Method` in **STATE: PENDING**. Before calling them to recover, you must intentionally clear. With the propagate policy, avoid doing anything other than **controlled cleanup** and returning to the JVM.

Do not infer from a non-`NULL` JNI value that all Java calls did not raise an exception: `Call<Type>Method` invokes a Java method that can throw any error, so **check `ExceptionCheck`** after the call if the result is used.

## 10. Local Reference Lifecycle and Cleanup When an Error Is Pending

Error paths need to clean up previously acquired resources. Certain release operations are permitted in the pending state:

~~~c
/* Excerpt: assume resources were acquired successfully. */
if ((*env)->ExceptionCheck(env)) {
    if (utfChars != NULL) {
        (*env)->ReleaseStringUTFChars(env, inputString, utfChars);
    }
    if (temporaryRef != NULL) {
        (*env)->DeleteLocalRef(env, temporaryRef);
    }
    return 0;
}
~~~

This is an **illustrative excerpt**: `utfChars`, `inputString`, and `temporaryRef` must be defined and validly allocated/obtained beforehand; do not paste this snippet verbatim into `nativeexceptionpolicy.c`.

If you have called `PushLocalFrame` successfully, `PopLocalFrame(env, NULL)` is also a permitted cleanup method when an exception is pending. Do not pop a frame that was not pushed successfully. If you called `GetPrimitiveArrayCritical` or `GetStringCritical`, you must follow the specific restrictions of critical regions and release properly; do not arbitrarily call other APIs while holding a critical pointer.

**The local handle of `original = ExceptionOccurred(env)` also needs to be cleaned up.** In the example above, after recovering/translating/re-throwing, the C code calls `DeleteLocalRef(env, original)` even while the new exception is pending. Deleting the **local handle** does not destroy the throwable object that the JVM is holding as the pending exception or cause.

Native memory `malloc`, file handles, C++ locks, and other resources must be freed using their own acquire/release mechanisms; `ExceptionClear`, `DeleteLocalRef`, or `PopLocalFrame` do not replace `free`, `fclose`, or mutex unlock.

## 11. Choosing a Policy by API Contract

| Situation | Appropriate policy | What to preserve |
|---|---|---|
| JNI acts as a thin bridge, Java caller knows how to `catch` | **Propagate** | Original exception type and message; do not clear |
| Experimental data error is allowed to use a default value | **Recover** on exact type | Clear only the specified error; fallback must be explicit |
| JNI maps infrastructure layer into a business API | Controlled **Translate** | Classify original error, preserve `cause` if needed |
| `OutOfMemoryError`, linkage error, JNI misconfiguration, or unknown error | **Propagate/fail** | Do not swallow into a "valid result" |
| Java code is easier for deciding recovery/translation | **Let JNI propagate then `catch` in Java** | Keep native layer simple, reduce JNI calls during errors |
| Need to log while still propagating the error | **Log without losing pending exception**, or let Java log after catch | Avoid `ExceptionDescribe` if you do not want to clear |

**Recovery is a business decision, not a trick to avoid exceptions.** For example, "if the network is slow, return a non-expired cache" is completely different from "if out of memory, treat as success". With JNI, the closer you are to system resources, the clearer the rules must be about which layer handles which errors.

You can design a Java API to return a result type such as `OptionalInt` or `Result` instead of throwing exceptions for routine errors; however, that is a Java API contract, not a license for JNI to clear every underlying error.

## 12. Common Mistakes and How to Detect Them

| Mistake | Harm | How to fix |
|---|---|---|
| Not checking for exception after `CallStaticIntMethod` | Uses invalid return value, makes further JNI calls while pending | `ExceptionCheck` or check value per contract |
| Clearing every exception and returning `0` | Swallows `OutOfMemoryError`/`NoSuchMethodError`, produces false success | Clear only classified and permitted errors |
| Calling `FindClass` before clearing on the error path | Violates the pending exception rule | Look up class before the risk, or capture → clear → look up |
| Using `ExceptionDescribe` to log then returning | `ExceptionDescribe` **clears** the original exception | Use `ExceptionCheck`; Java logging after catch |
| Using `ExceptionOccurred` without managing the local ref | Can accumulate handles in native loops | `DeleteLocalRef` when done or manage local frames |
| `ThrowNew` while another exception is pending | Invalid per JNI rules when pending | Clear per policy first, then create/Throw the new error |
| Translating an exception but losing the cause | Hard to investigate the root cause of the error | Use `(String, Throwable)` constructor or equivalent |
| Recovering even non-whitelisted errors | Hides bugs/corrupts state | Rethrow original with `Throw` |
| Not cleaning up resources when an error is pending | Leaks native memory, references, or locks | Use permitted release/cleanup APIs then return |
| Expecting C++ `catch` to catch Java exceptions | Mixes two different exception mechanisms | Use JNI exception APIs |
| Calling `ExceptionClear` just to continue the happy-path code | Loses error-handling mechanism | Clear only after choosing an explicit fallback/recovery/translation |
| Using `Throw` to "rethrow" before clearing the old exception | Violates JNI contract for pending exceptions | Capture → clear → `Throw(original)` |
| Assuming every JNI call signals errors with `NULL` | Some `Call<Type>Method` calls can raise an exception with an untrusted C value | Check pending state after Java invocation |

### 12.1. Checking with HotSpot

After building the library, you can enable JNI checking mode on HotSpot:

~~~bash
java -Xcheck:jni -Djava.library.path=. NativeExceptionPolicy
~~~

`-Xcheck:jni` can help detect some JNI calls made while an exception is pending or with invalid references. It **does not guarantee** all C/C++ bugs are detected, and does not replace testing recovery/translation policies. When the code is valid, the application stdout remains the seven lines from the hands-on section; the JVM may print additional warnings if misuse is detected.

If you encounter `UnsatisfiedLinkError`, distinguish **native library not found** from **JNI symbol/function not found**. This is a linking/library-loading error, not a valid reason to clear it yourself and pretend the computation result is correct.

### 12.2. Four Questions to Answer When Reviewing a JNI Error Branch

1. **Which API did the error originate from?** Did a Java-calling API throw an exception, or did a JNI call return `NULL`/an error code?
2. **Before calling the next JNI API, is there still a pending exception?** If so, is the API you intend to call on the permitted cleanup/check list?
3. **Where is the error policy explicitly specified?** Keep as-is for Java to catch, recover on an exact type, or translate while preserving cause?
4. **Which resources need cleanup on every branch?** Local/global refs, pinned arrays, native strings, C pointers, file handles, locks.

If you cannot answer these, **keeping and propagating the original error to Java is usually safer** than clearing and continuing.

## 13. Self-Check Questions and Exercises

1. When `CallStaticIntMethod` causes the Java helper to throw `ArithmeticException`, what happens to the C execution flow right after the call?
2. Why is `return 0` while an exception is pending different from `ExceptionClear` followed by `return 0`?
3. How do `ExceptionCheck` and `ExceptionOccurred` differ in terms of creating a local reference?
4. Why is `ExceptionDescribe` unsuitable if the goal is to preserve the error for Java to `catch`?
5. After an exception becomes pending, can `FindClass`, `NewStringUTF`, or `ThrowNew` be called immediately?
6. In a fallback policy, why must errors be classified instead of clearing all exceptions?
7. If `GetStaticMethodID` cannot find the Java method `divide(I)I`, should `recover` return the fallback `-1`?
8. If you have captured a `jthrowable original` and then called `ExceptionClear`, does the throwable object immediately disappear?
9. When translating `ArithmeticException` to `IllegalArgumentException`, what does the constructor taking `Throwable cause` solve?
10. In a branch with a pending Java exception, which JNI APIs can be used to clean up a local `jstring` and a buffer from `GetStringUTFChars`?
11. If creating a new exception during translation causes `OutOfMemoryError`, why should you not clear the new error and treat the operation as successful?
12. In what cases should a Java wrapper be responsible for `catch` and translating errors instead of implementing extensive exception-handling logic in C?

**Conclusion:** JNI requires an **explicit decision** at each error boundary: either **keep the pending exception and return for Java to handle**, or **capture → clear → handle according to policy**. A recovery policy applies only to permitted errors, must clean up resources properly, and must not hide other errors. If translating the error type, preserve `cause` to maintain diagnostic capability. When unsure whether recovery is safe, **propagating the original error** is the safer and more verifiable behavior.

### Standard References

- [JNI Specification — Design Overview, Java Exceptions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): pending exceptions, the two ways of handling them, and the list of JNI functions permitted while an exception is pending.
- [JNI Specification — Exception APIs](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `ExceptionCheck`, `ExceptionOccurred`, `ExceptionDescribe`, `ExceptionClear`, `Throw`, and `ThrowNew`.
- [Java SE 17 — IllegalArgumentException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalArgumentException.html): constructor accepting `String` and `Throwable cause`.
- [Android NDK — JNI Tips, Exceptions](https://developer.android.com/ndk/guides/jni-tips): checking for pending exceptions after Java callbacks and restrictions on permitted JNI APIs.
