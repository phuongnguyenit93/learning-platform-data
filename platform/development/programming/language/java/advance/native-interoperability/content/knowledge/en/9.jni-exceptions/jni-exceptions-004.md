# Throwing Java Exceptions from JNI Using `Throw` or `ThrowNew` with Appropriate Messages

## 1. Goal: Turning Native Errors into Meaningful Java Exceptions

A `native` method may detect invalid arguments, state errors, or errors from C/C++ APIs. If it only prints a message with `printf` and returns a default value, the Java side usually does not know that the operation failed. JNI provides two main APIs to **place a Java exception in a pending state on the current thread**:

- `ThrowNew`: creates **a new exception object** of the specified class, using the provided message string, and marks the exception to be thrown.
- `Throw`: uses **an existing `Throwable` object**, marking that exact object to be thrown. Useful when you want to preserve the cause, suppressed exceptions, custom exception type, or the same exception instance.

After successfully calling either function, **C/C++ code continues executing** until it explicitly `return`s or transfers control flow. JNI does not behave like a `throw` statement in Java/C++ that automatically exits the native method. Typically, the native method **cleans up resources that are safe to clean up, then returns**. The JVM will propagate the pending exception to the Java caller of the native method; Java can catch it with `try/catch` like any other Java exception.

This is the distinction to keep in mind:

```text
Java code calls native method
         │
         ▼
JNI C/C++ detects error
         │
         ├─ ThrowNew(exceptionClass, message)
         │           or
         └─ Throw(existingThrowable)
                     │
                     ▼
       Java exception becomes pending
                     │
          Clean up native resources safely
                     │
           return from native method
                     │
                     ▼
 Java sees exception in try/catch
```

**Do not treat the return code of `Throw`/`ThrowNew` as a business return value.** They return a `jint` equal to `0` when setting the exception succeeds, and a negative number when it fails. That is the status of the JNI operation; the Java exception is carried by the *pending exception* mechanism, not by that `jint` value.

## 2. Signatures, Parameters, and Correct Invocation

### 2.1. `ThrowNew`: New Exception Type and Message

Signature in JNI C:

```c
jint ThrowNew(JNIEnv *env, jclass clazz, const char *message);
```

How to call in C:

```c
jint rc = (*env)->ThrowNew(
        env, exceptionClass, "value must be >= 0");
```

How to call in C++:

```cpp
jint rc = env->ThrowNew(
        exceptionClass, "value must be >= 0");
```

- `env` is the JNI environment of the **current thread**.
- `clazz` must be a valid `jclass` representing a subclass of `java.lang.Throwable`, for example `java.lang.IllegalArgumentException`. Do not pass `NULL` for `clazz`.
- `message` is a C character string **encoded in JNI Modified UTF-8**, or `NULL` when you genuinely do not want to provide a message. It is not a `jstring`.
- The function creates an exception object and sets it as pending, returning `0` on success or a negative value on failure.

A common pattern is to find the exception class using a JNI binary name with forward slashes:

```c
jclass cls = (*env)->FindClass(
        env, "java/lang/IllegalArgumentException");
if (cls == NULL) {
    /* FindClass failed to retrieve the class; keep the current error,
       do not continue calling ThrowNew with cls == NULL. */
    return;
}

(void)(*env)->ThrowNew(
        env, cls, "argument size must be positive");
(*env)->DeleteLocalRef(env, cls);
return; /* Explicitly exit the native method. */
```

This is a **fragment for a native method returning `void`**, not a complete program. `DeleteLocalRef` is one of the JNI functions allowed to be called while an exception is pending. For a native method returning `jint` or `jobject`, you must write a return matching the C signature; while an exception remains pending, the normal business result is not used as a successful result.

### 2.2. `Throw`: Reusing an Existing `Throwable`

JNI C signature:

```c
jint Throw(JNIEnv *env, jthrowable obj);
```

C:

```c
jint rc = (*env)->Throw(env, existingException);
```

C++:

```cpp
jint rc = env->Throw(existingException);
```

`existingException` is a valid `jthrowable`, **non-`NULL`**, and still alive within the scope of the JNI reference. It can be an argument passed down from Java, or an exception object created by JNI using the `NewObject` constructor. If you want to preserve an existing instance, use `Throw` instead of creating another exception with `ThrowNew`.

`Throw` **does not call the constructor again** and does not generate a new message. It throws **the exact object** provided: the existing message, cause, suppressed exceptions, and custom fields remain attached to that object.

### 2.3. Decision Table

| Need | Usually Appropriate Approach | Reason |
| --- | --- | --- |
| Native checks negative arguments, out-of-range values, invalid state | `ThrowNew` with a specific exception type and clear message | Concise, no need to manually construct a `Throwable` object |
| Java passes an existing `Throwable` that needs to be rethrown | `Throw` | Preserves the exception instance, cause, and metadata |
| Need an exception with a specific constructor, cause, or custom fields | Create `Throwable` with `NewObject`, then `Throw` | `ThrowNew` only accepts a class and a message string; it does not allow passing a cause directly |
| Java callback just threw an exception and native cannot handle it | **Keep the pending exception, clean up, then return** | No need to throw a second time or mask the original error |
| Want to convert an old exception into a new domain type | Inspect/capture the exception, intentionally `ExceptionClear`, create a wrapper with cause, then `Throw` | Preserves the causal chain and error contract |
| Error actually originates in the C/C++ layer | Convert to a Java exception at the JNI boundary after C/C++ cleanup | Do not let C++ exceptions arbitrarily cross the C/JNI ABI |

You do not need to use `ThrowNew` for every error; and do not call `Throw` when you do not yet have a valid `Throwable` object.

## 3. Choosing Classes and Messages for Easy Debugging

### 3.1. Choosing a Meaningful Exception Type

A good message with the wrong exception type still makes the Java API difficult to use. You should use the appropriate standard class, or a public domain exception of the library when there is a clear reason.

| Context | Suggested Java Class | Message Better Than Generic Notice |
| --- | --- | --- |
| Argument outside valid domain | `IllegalArgumentException` | `"batchSize must be > 0; received -4"` |
| Operation cannot be performed in current state | `IllegalStateException` | `"decoder is closed; cannot read frame"` |
| Index or length out of bounds | `IndexOutOfBoundsException` | `"index 12 outside [0, 9]"` |
| Feature not supported by backend | `UnsupportedOperationException` | `"native codec AV1 is unavailable on this platform"` |
| Resource access permission error | `SecurityException` when genuinely permission-related | `"access denied for requested resource"` |
| I/O error in native layer | `java.io.IOException` (checked) or appropriate subclass | `"cannot read header from input stream"` |
| Need to preserve backend error with cause and custom error code | Domain exception with appropriate fields and constructor | Message describes operation + code, cause holds original error |

The Java method should **declare checked exceptions** in its contract when expected to be thrown from native, for example `native byte[] read() throws IOException;`. JNI can throw a `Throwable` at runtime if permitted even if the Java declaration does not list it, but intentionally omitting checked exception declarations makes it hard for API users to handle them properly.

Do not use `Error` (`OutOfMemoryError`, `LinkageError`, `InternalError`) as a convenient label for routine input errors. `Error` typically indicates a serious problem that an application should not treat as a normal handling branch. If a JNI operation itself fails and the VM has already set `OutOfMemoryError` pending, typically **return control to Java** rather than trying to create another exception, because any additional allocation risks failing.

### 3.2. What Information Should an Appropriate Message Contain?

A message helps the caller know **the expected condition, the received value, and the operation being performed**. For example:

```text
Unclear:  "invalid input"
Better:   "bufferLength must be >= 16; received 8"
Unclear:  "operation failed"
Better:   "cannot decode JPEG header: unsupported marker 0xD8"
```

Practical guidelines:

1. **Parameter or operation name:** `length`, `offset`, `nativeDecode`, `openDevice`...
2. **Constraint and relevant value:** `"expected 0..255; received 300"`. Only include values that are necessary and safe to expose.
3. **Do not hide the cause:** if the Java side needs deep context analysis, use a `Throwable` with a cause (via the appropriate constructor) and then `Throw`.
4. **Avoid sensitive data:** do not copy passwords, access tokens, full payloads, raw memory addresses, or sensitive user data into messages; logs may travel to many systems.
5. **Stability by exception type:** clients should rely on the exception class, error code, and contract; do not parse messages with regex for business branching.
6. **Language and encoding:** `ThrowNew` messages are Modified UTF-8; control encoding before passing data from the backend. For complex Unicode messages or localized messages, you may prefer creating `jstring`/`Throwable` from Java.

A message does not have to be long. When the `IllegalArgumentException` class and the `batchSize` value are already present, `"batchSize must be positive; received -4"` is usually sufficient.

## 4. Pending Exceptions: The Mechanism That Determines Safe Code

### 4.1. Throwing in JNI Does Not Mean C Has Stopped

The following snippet has incorrect control flow:

```c
if (length < 0) {
    (*env)->ThrowNew(env, excClass, "length < 0");
}
/* WRONG: C code continues running, may still access buffer. */
read_bytes(buffer, length);
```

Correct snippet:

```c
if (length < 0) {
    (void)(*env)->ThrowNew(env, excClass, "length must be >= 0");
    return;  /* Example native method returning void. */
}

/* Only execute if data is valid. */
read_bytes(buffer, length);
```

Both snippets are **fragments** assuming `excClass` is valid and `read_bytes` is an application-defined native function, not standalone programs. After `ThrowNew` succeeds, a Java exception is pending; if C code continues executing as if no error occurred, it may corrupt data or cause a crash.

### 4.2. When Are `ExceptionCheck` / `ExceptionOccurred` Needed?

The following JNI APIs help manage pending exceptions on the current thread:

- `ExceptionCheck(env)`: returns `JNI_TRUE` or `JNI_FALSE` without **creating a local reference to the exception object**. Very suitable when you only need a quick branch.
- `ExceptionOccurred(env)`: returns the pending `jthrowable`, or `NULL` if none. This is a local JNI reference; its lifetime must be managed, especially if used across multiple steps.
- `ExceptionClear(env)`: **explicitly clears the pending exception**. Only use when native code has a proper error-handling or conversion strategy; do not clear to hide errors.
- `ExceptionDescribe(env)`: prints the exception and stack trace to the system error channel and **clears the pending exception as a side effect**. Useful for debugging, but careless calls can swallow Java errors.
- `Throw` / `ThrowNew`: sets a pending exception if valid and the operation succeeds.

Standard example when native calls back into a Java method:

```c
(*env)->CallVoidMethod(env, callback, runMethod);
if ((*env)->ExceptionCheck(env) == JNI_TRUE) {
    /* Callback threw a Java exception.
       Do not call arbitrary JNI APIs; clean up safely and return. */
    return;
}
```

A JNI callback may throw `IllegalStateException`, `IOException`, or other errors. If there is no explicit conversion requirement, **preserve the original exception**. Do not proceed to call `FindClass` and `ThrowNew` while the old exception is still pending to arbitrarily "wrap" it.

### 4.3. Which JNI Functions Can Still Be Used While an Exception Is Pending?

The JNI specification allows **a limited set** of operations while an exception has not been cleared, for example:

- `ExceptionCheck`, `ExceptionOccurred`, `ExceptionDescribe`, `ExceptionClear`.
- `DeleteLocalRef`, `DeleteGlobalRef`, `DeleteWeakGlobalRef`.
- `ReleaseStringChars`, `ReleaseStringUTFChars`, `ReleaseStringCritical`, `Release<Type>ArrayElements`, `ReleasePrimitiveArrayCritical`.
- `MonitorExit`, `PushLocalFrame`, `PopLocalFrame`, and `DetachCurrentThread` (when appropriate for the lifecycle).

Most other JNI operations, such as `FindClass`, `GetMethodID`, `NewObject`, or calling Java methods, **must not be called while an exception is still pending**. If you need to handle or convert the exception, you must first retrieve the necessary information and call `ExceptionClear` at the right time before using other JNI functions.

Pure C/C++ code to `free` memory, close a file descriptor, or release private resources can still run if the operation itself is safe. However, if you want to make additional JNI calls for cleanup, you must choose only from the allowed functions.

**Default rule:** see pending exception → minimal cleanup using allowed APIs → return, so Java catches it. Only clear when there is a specific reason, complete handling code, and error semantics are preserved.

## 5. Runnable Example: `ThrowNew`, `Throw`, and Errors from a Java Callback

The following standalone example demonstrates three cases in the same JNI library:

1. Native validates input values, throwing a new `IllegalArgumentException` or `ArithmeticException` using `ThrowNew`.
2. Java passes an `IllegalStateException` **that already has a cause** down to native; `Throw` preserves the exact same object and cause.
3. Native calls `Runnable.run()`; the callback throws a Java error, so native detects the pending exception, cleans up, and returns without **throwing a second exception**.

Environment: **JDK 17+**, C compiler supporting C11, **Linux** with GCC/Clang and JNI headers. The code snippets are separated by filename so you can create a project directory and run them.

### 5.1. Project Structure

```text
jni-errors/
├── src/
│   └── demo/
│       └── NativeErrors.java
├── native/
│   └── native_errors.c
└── build/                  # Created during compilation
```

### 5.2. File `src/demo/NativeErrors.java`

```java
package demo;

import java.io.IOException;

public final class NativeErrors {
    static {
        System.loadLibrary("native_errors");
    }

    private NativeErrors() {
    }

    private static native int squareChecked(int value);

    private static native void rethrow(Throwable existing);

    private static native void invokeCallback(Runnable callback);

    public static void main(String[] args) {
        System.out.println("square(6): " + squareChecked(6));

        try {
            squareChecked(-2);
        } catch (IllegalArgumentException error) {
            System.out.println("invalid: " + error.getMessage());
        }

        try {
            squareChecked(50_000);
        } catch (ArithmeticException error) {
            System.out.println("overflow: " + error.getMessage());
        }

        IllegalStateException original = new IllegalStateException(
                "operation failed", new IOException("disk unavailable"));

        try {
            rethrow(original);
        } catch (IllegalStateException error) {
            System.out.println("same instance: " + (error == original));
            System.out.println(
                    "cause: " + error.getCause().getMessage());
        }

        try {
            invokeCallback(() -> {
                throw new IllegalStateException("callback failed");
            });
        } catch (IllegalStateException error) {
            System.out.println("callback: " + error.getMessage());
        }
    }
}
```

In the program, the native method `squareChecked` returns `int` on the success path. When an exception is pending, the native implementation will `return 0` as a technical value to satisfy the C signature; Java receives the exception and **does not treat 0 as a successful calculation result**.

### 5.3. File `native/native_errors.c`

```c
#include <stdio.h>
#include "demo_NativeErrors.h"

/* Helper fragment in the same C file:
   className uses JNI binary name, e.g. java/lang/...
   Only call when no Java exception is pending. */
static jint raise_new(
        JNIEnv *env,
        const char *className,
        const char *message) {

    jclass exceptionType = (*env)->FindClass(env, className);
    if (exceptionType == NULL) {
        /* Do not try to throw another error if FindClass fails;
           keep the error already reported by the JVM if any. */
        return JNI_ERR;
    }

    jint rc = (*env)->ThrowNew(env, exceptionType, message);

    /* DeleteLocalRef is allowed even when an exception is pending. */
    (*env)->DeleteLocalRef(env, exceptionType);
    return rc;
}

JNIEXPORT jint JNICALL Java_demo_NativeErrors_squareChecked(
        JNIEnv *env, jclass ignored, jint value) {
    (void)ignored;

    if (value < 0) {
        char message[96];
        (void)snprintf(message, sizeof(message),
                "value must be >= 0; received %d", (int)value);

        (void)raise_new(env, "java/lang/IllegalArgumentException",
                        message);
        return 0;
    }

    /* 46340^2 is still within signed Java int range.
       46341^2 exceeds Integer.MAX_VALUE. */
    if (value > 46340) {
        char message[96];
        (void)snprintf(message, sizeof(message),
                "value must be <= 46340; received %d", (int)value);

        (void)raise_new(env, "java/lang/ArithmeticException",
                        message);
        return 0;
    }

    return value * value;
}

JNIEXPORT void JNICALL Java_demo_NativeErrors_rethrow(
        JNIEnv *env, jclass ignored, jthrowable existing) {
    (void)ignored;

    if (existing == NULL) {
        (void)raise_new(env, "java/lang/IllegalArgumentException",
                        "existing exception must not be null");
        return;
    }

    /* Reuse the exact Throwable passed in by Java. */
    (void)(*env)->Throw(env, existing);
    return;
}

JNIEXPORT void JNICALL Java_demo_NativeErrors_invokeCallback(
        JNIEnv *env, jclass ignored, jobject callback) {
    (void)ignored;

    if (callback == NULL) {
        (void)raise_new(env, "java/lang/IllegalArgumentException",
                        "callback must not be null");
        return;
    }

    jclass callbackClass = (*env)->GetObjectClass(env, callback);
    if (callbackClass == NULL) {
        /* JNI operation failed: preserve the error. */
        return;
    }

    jmethodID run = (*env)->GetMethodID(
            env, callbackClass, "run", "()V");
    if (run == NULL) {
        (*env)->DeleteLocalRef(env, callbackClass);
        return;
    }

    (*env)->CallVoidMethod(env, callback, run);

    if ((*env)->ExceptionCheck(env) == JNI_TRUE) {
        /* Java Runnable.run() threw an error.
           Do not call ThrowNew to mask the original error. */
        (*env)->DeleteLocalRef(env, callbackClass);
        return;
    }

    (*env)->DeleteLocalRef(env, callbackClass);
}
```

Explanation of notable points:

- `FindClass` uses JNI names like `java/lang/IllegalArgumentException`, not dots or `Ljava/...;` notation.
- `raise_new` creates a local `jclass`, calls `ThrowNew`, and then deletes the local ref using an operation **allowed while an exception is pending**. It returns `0` if `ThrowNew` succeeds, a negative number on error; the helper does not generate an extra exception to replace the original error if `FindClass` fails.
- `squareChecked` checks the range **before multiplying**, avoiding undefined signed integer overflow in C and matching Java `int`.
- `rethrow` receives a valid `jthrowable`, so `Throw` uses the exact exception instance, including the `IOException` cause attached by Java when creating the object.
- `invokeCallback` checks `GetObjectClass` and `GetMethodID`. `CallVoidMethod` can leave an exception pending without **returning a distinguishing error code**; `ExceptionCheck` verifies this before native cleans up and returns.
- The sample only illustrates normal success/exception paths. In extreme resource situations, `ThrowNew` or class lookup can still fail (negative return code or appropriate error condition); a production library needs a policy for handling critical errors rather than assuming every `ThrowNew` can allocate an object.
- All C messages here are ASCII, which are also valid in Modified UTF-8. This helps keep stdout predictable across systems.

### 5.4. Compiling and Running on Linux

From inside the `jni-errors` directory; `JAVA_HOME` points to a **JDK** containing `include/jni.h`:

```bash
mkdir -p build/classes build/include

javac -h build/include -d build/classes \
  src/demo/NativeErrors.java

cc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/include \
  native/native_errors.c -o libnative_errors.so

java -Djava.library.path=. \
  -cp build/classes demo.NativeErrors
```

`javac -h` generates the header `build/include/demo_NativeErrors.h` according to the Java signatures. Using the auto-generated header reduces the risk of wrong JNI symbols, hidden `JNIEnv *`/`jclass` parameters, or function names. `cc` builds the Linux shared library and `System.loadLibrary("native_errors")` looks for `libnative_errors.so` in `java.library.path`.

**Expected stdout:**

```text
square(6): 36
invalid: value must be >= 0; received -2
overflow: value must be <= 46340; received 50000
same instance: true
cause: disk unavailable
callback: callback failed
```

If running on JDK versions with native access restrictions, you may need to grant permission according to that JDK's mechanism; for classpath applications on JDK 24+, examples are commonly run with `--enable-native-access=ALL-UNNAMED` to avoid warnings or errors due to the native access policy. This **does not affect** `Throw`/`ThrowNew` semantics. Windows/macOS must use the library format, file extension, JNI includes, and build commands appropriate for that OS/CPU.

### 5.5. Why Does `same instance: true` Matter?

In Java, `original` is a specific `IllegalStateException` with a cause. When native uses `Throw(env, original)`, the Java side catches **the exact same instance**; `error == original` is `true`. Therefore, the message `"operation failed"` and the cause `IOException("disk unavailable")` remain attached to the object. If replaced by `ThrowNew` with the same exception class and message, it would be a **different object**, not preserving the cause unless the programmer reconstructs it.

## 6. How to Include a Cause or Complex Unicode Messages?

`ThrowNew` does not accept a `jthrowable cause` parameter. If you want to provide a cause, suppressed exceptions, or custom fields, typically follow this process:

1. Identify the appropriate Java exception class (with the desired constructor).
2. Create a `jstring` message using the correct encoding method; get the constructor with `GetMethodID`.
3. Create the `Throwable` with `NewObject`, passing the `String` argument and possibly `Throwable cause`.
4. Call `Throw` with the new object.
5. Delete valid **local references** after throwing; do not delete strong refs belonging to Java outside your scope.

**Illustrative JNI C example** to create `IllegalStateException(message, cause)` when **no exception is pending before starting**; `cause` is already a valid `jthrowable` or `NULL`:

```c
/* Fragment, assuming env is valid and no exception is pending. */
jclass cls = (*env)->FindClass(
        env, "java/lang/IllegalStateException");
if (cls == NULL) {
    return; /* Keep exception from FindClass if any. */
}

jmethodID ctor = (*env)->GetMethodID(
        env, cls, "<init>",
        "(Ljava/lang/String;Ljava/lang/Throwable;)V");
if (ctor == NULL) {
    (*env)->DeleteLocalRef(env, cls);
    return;
}

jstring message = (*env)->NewStringUTF(
        env, "native operation failed");
if (message == NULL) {
    (*env)->DeleteLocalRef(env, cls);
    return;
}

jthrowable wrapped = (jthrowable)(*env)->NewObject(
        env, cls, ctor, message, cause);
if (wrapped != NULL) {
    (void)(*env)->Throw(env, wrapped);
    (*env)->DeleteLocalRef(env, wrapped);
}

(*env)->DeleteLocalRef(env, message);
(*env)->DeleteLocalRef(env, cls);
return;
```

This is a **fragment inside a native method returning `void`**, not a standalone C program. The `DeleteLocalRef` steps remain valid while an exception is pending, for example if the `NewObject` constructor itself throws an error. `NewObject` may return `NULL` when allocation fails; do not call `Throw` with `NULL`. If you need to create an error with a message containing Unicode characters not easily represented as an ASCII string, `NewStringUTF` also requires Modified UTF-8; do not pass arbitrary UTF-8 bytes without validating the encoding.

### 6.1. Modified UTF-8 Is Not Exactly the Same as Standard UTF-8

JNI `ThrowNew` and `NewStringUTF` use **Modified UTF-8** for C character strings. The representation of `U+0000` and Unicode characters outside the BMP (via surrogate pairs) differs from standard UTF-8. Therefore:

- Pure ASCII messages in examples are safe and compatible.
- Byte strings read from files or external APIs are not automatically valid strings for `ThrowNew`.
- If you need messages with Vietnamese content, special characters, or user-supplied data, you should convert the encoding properly, or create a `jstring` from valid UTF-16 data using `NewString` and then construct the exception object via a Java constructor and `Throw`.
- Do not concatenate arbitrary C content past buffer limits; use `snprintf` with the proper size and consider the required length. When truncating messages, ensure encoding boundaries are not cut mid-character.

The key point is that **messages aid diagnostics**, not serve as a channel for transmitting all error data. Complex information should reside in the exception class/fields/cause defined in the Java API.

## 7. Preserve or Convert a Pending Exception from a Previous JNI Call?

### 7.1. Default: Preserve the Exception

Functions like `FindClass`, `NewObject`, `GetMethodID`, and `CallVoidMethod` can leave an exception pending. In most cases, unless there is an explicit conversion requirement:

```c
jobject result = (*env)->CallObjectMethod(
        env, service, methodID);

if ((*env)->ExceptionCheck(env) == JNI_TRUE) {
    /* Do not call ThrowNew additionally; preserve the exception. */
    return NULL; /* Example native method returning jobject. */
}

/* result is only processed as success when there is no error. */
return result;
```

This is a fragment assuming `service` and `methodID` are valid. If previous JNI references/resources were held, they must be released using operations permitted while pending before returning.

### 7.2. When Wrapping Is Required: Capture → Clear → Construct → Throw

If the public API wants to convert an `IOException` from a callback into a `NativeOperationException` with a cause, you cannot simply call `FindClass`/`NewObject` while the old error is still pending. The sequence must be:

```text
1. ExceptionOccurred(env) → obtain local reference to old Throwable.
2. ExceptionClear(env) → explicitly clear, since new JNI operations will follow.
3. FindClass/GetMethodID/NewObject → create wrapper containing old cause.
4. Throw(env, wrapper) → new pending exception.
5. DeleteLocalRef(env, refs) and return.
```

In step (3), if lookup/constructor fails and throws a new error, you must clean up safely and let that error propagate; avoid automatically clearing and creating another exception loop. If you intend to keep the old cause across operations, ensure the local ref remains valid. If you call `ExceptionClear` and then **forget to `Throw`**, the original error will be swallowed and the Java side may think the operation succeeded.

Another strategy is often simpler: **let the error propagate to Java and wrap it with Java code** in a wrapper method, where full `try/catch` syntax, constructors, and logging mechanisms are available. JNI may only need to detect the error and return.

### 7.3. `ExceptionDescribe` Is Not Harmless Logging

`ExceptionDescribe` prints the stack trace to the JVM error channel and **clears the pending exception**. If you write:

```c
if ((*env)->ExceptionCheck(env)) {
    (*env)->ExceptionDescribe(env); /* Side effect: clears. */
    return;
}
```

the Java side may **not receive an exception**, even though native code just printed a stack trace. For diagnostics in production, prefer letting the exception reach the Java logger; if using `ExceptionDescribe` during debugging, understand and explicitly handle the fact that it clears the exception. Do not swallow an error just to add a log line.

## 8. Cleanup, Resources, and Performance Considerations

Native code may hold buffers from `malloc`, string pointers via `GetStringUTFChars`, local refs, or locks. When an error occurs, resources must be released using the appropriate APIs:

```c
/* Fragment: assuming chars was obtained from GetStringUTFChars. */
const char *chars = (*env)->GetStringUTFChars(env, input, NULL);
if (chars == NULL) {
    return; /* There may be a pending exception. */
}

/* ... native operations that may detect an error ... */

(*env)->ReleaseStringUTFChars(env, input, chars);
```

`ReleaseStringUTFChars` is in the group of JNI functions safe to call while an exception is pending. So is `DeleteLocalRef`. Conversely, do not call a new `NewObject` just for logging/cleanup while pending, unless cleared according to a valid strategy.

For native memory:

```c
/* Common C pattern: label-based cleanup, suitable for error paths. */
void *buffer = allocate_buffer_somehow();
if (buffer == NULL) {
    /* Choose an appropriate Java exception before returning,
       if prior JNI calls have not already left a pending exception. */
    return;
}

/* ... processing ... */
free_buffer_somehow(buffer);
```

The above is a **pseudo-fragment with application-defined allocation/free functions**, not a runnable program. Never use `free` to release a JNI object reference; use the appropriate `DeleteLocalRef`/`DeleteGlobalRef`. If working inside a JNI critical region or holding a monitor, you must follow their specific release/exit rules even when an error occurs.

### 8.1. Is ThrowNew Free?

No. It requires accessing the class and creating an exception object/stack trace at runtime. If every normal element in a loop throws an exception as control flow, the cost is usually much higher than a return code or normal Java handling. Use exceptions when **there is genuinely a contract error**, not to signal each valid step of a hot loop. At the same time, do not sacrifice diagnosability by always throwing `RuntimeException("failed")`.

If a native call can fail very frequently and belongs to a normal business branch (for example, trying to find a missing element), consider an API returning `Optional`/status in Java or a well-defined result code, rather than catching exceptions continuously. The boundary between errors and valid results must be stated in the API contract.

## 9. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `ThrowNew` and continuing to use invalid input | Native code keeps running, may read invalid memory | Clean up properly and return immediately |
| Calling `FindClass` with `java.lang.IllegalStateException` | Wrong JNI class name format | Use `java/lang/IllegalStateException` |
| Using `ThrowNew` to "rethrow" a Throwable with a cause | Creates a new instance and loses old exception data | `Throw(env, existing)` |
| Passing `NULL` as `jthrowable` to `Throw` | JNI parameter violation, risk of fatal error | Check for null before calling |
| `FindClass` failed yet still calling `ThrowNew` with null class | Overwrites/stacks errors, may crash | Keep the pending exception and return |
| Not checking pending exception after `CallVoidMethod` | Misses callback error, makes invalid subsequent JNI calls | `ExceptionCheck` before further JNI steps |
| Calling `ExceptionClear` to "dismiss warnings" | Swallows errors that Java needs to see | Only clear when you will actually handle/wrap |
| Calling `ExceptionDescribe` thinking Java will still catch the old error | `ExceptionDescribe` clears the pending exception | Be aware of the side effect; let Java log/catch |
| Using arbitrary UTF-8 bytes as a `ThrowNew` message | May be invalid Modified UTF-8 | Convert encoding or create `jstring` properly |
| Using `ThrowNew` without checking critical allocation errors | If the throw operation fails, the program may return a sentinel | Design appropriate error/failure paths; do not assume it always succeeds |
| Holding native pointers or local JNI refs after returning | Leak or use-after-release | Clean up resources with the proper JNI/C API |
| Letting a C++ exception cross a JNI frame | Not a guaranteed way to throw a Java exception | Catch C++ at the native boundary, map to Java Throwable |

### Distinguishing Exceptions from C/C++ Code and Java

- `Throw`/`ThrowNew` creates a **Java pending exception**. Do not use C++ `try/catch` expecting it to be automatically thrown on the C++ side.
- C++ `throw std::runtime_error(...)` is a **C++ exception**, and does not automatically become `java.lang.RuntimeException`. In a JNI C++ wrapper, catch at the boundary, translate appropriate error info to JNI `ThrowNew` or `Throw`, clean up, and return. Avoid letting C++ exceptions cross runtime frames without compatibility guarantees.
- Calling `FatalError` is not equivalent to throwing a Java exception: it is a critical error operation from which the VM is not expected to recover; do not use it to handle routine argument errors.

## 10. Self-Check Questions

**Question 1.** Native detects `length = -5`. Use `ThrowNew` or `Throw`?  
**Answer:** If there is no existing exception object, choose `ThrowNew` with `IllegalArgumentException`, message like `"length must be >= 0; received -5"`, then clean up and return.

**Question 2.** Native received `jthrowable existing` from Java, which has a cause and suppressed exceptions. How to rethrow while preserving the exact same instance?  
**Answer:** `(*env)->Throw(env, existing)` (C) or `env->Throw(existing)` (C++), with a valid and non-null reference.

**Question 3.** `CallVoidMethod` called a Java callback that threw an exception. Should you immediately call `FindClass` and `ThrowNew` to create `RuntimeException("callback failed")`?  
**Answer:** Usually no. Keep the pending exception, clean up resources using allowed APIs, and return. If wrapping is truly required, follow capture/clear/construct/throw in the proper order.

**Question 4.** If `ThrowNew` returns `0`, has the native method automatically returned?  
**Answer:** No. `0` is the success status of the JNI function; C/C++ code must explicitly `return`.

**Question 5.** After `ThrowNew`, are `DeleteLocalRef` and `ReleaseStringUTFChars` allowed?  
**Answer:** Yes, both are in the group of JNI cleanup functions permitted while an exception is pending. Do not arbitrarily call `FindClass` or `NewObject` without clearing first.

**Question 6.** Does `ExceptionDescribe` only print a log and keep the pending exception?  
**Answer:** No. The JNI specification states that it prints details and **clears the pending exception**.

**Question 7.** To throw a new exception with an existing `Throwable cause`, is passing a message to `ThrowNew` enough?  
**Answer:** No. You must create the exception object with the cause using the appropriate constructor/API and then `Throw`; or let a Java wrapper create/wrap the exception.

**Question 8.** Can every native error code be turned into `IllegalStateException("error")`?  
**Answer:** In terms of JNI mechanics it can create a valid exception class, but a quality API should choose the class corresponding to the error and a message with sufficient context, avoiding dropping useful causes/error codes.

## 11. Key Takeaways

- `ThrowNew`: **creates a new** Java exception using a class + Modified UTF-8 message; `Throw`: **throws an existing object**.
- Both set a **pending exception** on the current thread; they **do not automatically exit** the native method. Clean up safely, then `return`.
- When a JNI operation or Java callback has created a pending exception, **do not arbitrarily call further JNI functions**. `ExceptionCheck` and permitted release/delete functions help with handling/cleanup; `ExceptionClear` is only used when there is a clear strategy.
- Messages should describe the **parameter/operation, expected condition, and actual value**, without containing secrets; the exception class is the stable part of the error contract.
- `ThrowNew` has no cause parameter. To preserve a cause or instance, use `Throw` with an appropriate `Throwable`.
- `ExceptionDescribe` prints the error and **clears** the pending exception; do not accidentally swallow errors.
- C++ exceptions, native errno, and Java exceptions are distinct mechanisms; convert explicitly at the JNI boundary.

### Official Documentation

- [Oracle JNI Functions — Throw, ThrowNew, ExceptionCheck, ExceptionOccurred, ExceptionClear (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#exceptions): signatures, parameters, return codes, and exception APIs.
- [Oracle JNI Design Overview — Java Exceptions (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html#java-exceptions): propagation, pending exceptions, and JNI functions permitted while an exception is pending.
- [Oracle JNI Types and Data Structures — Modified UTF-8 (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html#modified-utf-8-strings): encoding rules for JNI strings.
- [Java SE 17 API — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): message, cause, suppressed exceptions, and exception object lifecycle.
