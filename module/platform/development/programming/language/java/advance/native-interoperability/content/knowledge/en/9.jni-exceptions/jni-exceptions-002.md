# Checking Pending Exceptions After JNI Calls a Java Method

## 1. The Problem: Calling Java from C/C++ via JNI Is Not Like Calling a Normal C Function

In **Java Native Interface (JNI)**, C/C++ code can call back into Java methods using functions such as `CallObjectMethod`, `CallIntMethod`, `CallVoidMethod`, `CallStaticIntMethod`, `CallNonvirtualObjectMethod`, and their corresponding `A`/`V` variants. That Java method may execute normally, return a value, **or throw a Java exception**.

Common point of confusion: when a Java method throws an exception during a call through JNI, the JVM marks a **pending exception** on the thread executing JNI. Native code **does not automatically exit the C function**, and the Java exception **does not automatically become a C++ exception**. Control returns right after the JNI call, where the programmer must check the state and then choose how to handle it.

For example:

```text
Java main()
    |
    v
native method (C)
    |
    +-- CallStaticIntMethod(...) ----> Java compute(8, 0)
    |                                    |
    |                               ArithmeticException
    |                                    |
    |<---- return to C, exception pending -+
    |
    +-- ExceptionCheck(env) == JNI_TRUE
    |
    +-- Option A: cleanup, return -> Java receives the exception
    |
    +-- Option B: ExceptionClear -> intentional handling -> return fallback
```

If you **ignore the pending state** and continue calling JNI APIs that are not permitted in this state, the program may produce warnings under `-Xcheck:jni`, yield unreliable results, or fail severely. Therefore, **after a JNI call into Java returns, check for exceptions before using the result or making further JNI calls**.

This article focuses specifically on the scenario where **native code calls a Java method**, receives an error via a pending exception, and chooses to **propagate**, **handle**, or **convert** the error in a controlled manner.

## 2. The "Pending Exception" Mechanism on a JNI Thread

A Java thread entering a native method carries the `JNIEnv *env` interface pointer. When native code calls back into a Java method:

1. The JVM executes the method specified by `jmethodID`.
2. If the method finishes normally, the JNI function returns the corresponding value, with no exception from that call.
3. If the method throws a `Throwable`, the JVM marks this exception as **pending** on the current thread and returns control to native code.
4. Native code checks using `ExceptionCheck` or `ExceptionOccurred`; the return value of `Call*Method` must not be treated as a normal result while a pending exception exists.
5. If the native method **returns to Java without clearing** the exception, the JVM propagates that exception in Java like a normal throw.
6. If native code calls `ExceptionClear`, the pending exception is removed; native code can proceed with subsequent valid JNI operations according to the chosen handling policy.

**A pending exception is the state of a single JNI thread**, not a global variable shared across all threads. `JNIEnv*` is also bound to its corresponding thread; do not store or pass it to another thread to check for exceptions. Each native thread attached to the JVM has its own `JNIEnv*` interface.

Do not confuse three concepts:

- **Return value of the JNI function:** `jint`, `jobject`, `jboolean`, `void`..., which only has normal meaning when the call succeeds.
- **Pending exception state:** the JVM knows an unhandled Java error exists on the current thread, even though native code has not exited yet.
- **Local reference to the exception object:** can be obtained with `ExceptionOccurred` to reference `jthrowable`; obtaining it alone does not automatically clear the pending exception.

An exception raised from a Java callback can be a checked exception, an unchecked exception, or an `Error`. JNI does not automatically force C code to distinguish between these types before returning. When Java resumes from the native method call, Java's normal `try/catch` mechanism will handle it if the type matches.

## 3. JNI APIs for Checking and Handling Exceptions

| JNI API (C) | Meaning | Pending state after the call |
| --- | --- | --- |
| `(*env)->ExceptionCheck(env)` | Returns `JNI_TRUE` if there is a pending exception, otherwise `JNI_FALSE`; does not create a local reference to the error | **Preserved** |
| `(*env)->ExceptionOccurred(env)` | Returns a `jthrowable` which is a **local reference** to the pending exception, or `NULL` | **Preserved** |
| `(*env)->ExceptionClear(env)` | Clears the pending exception on the thread | **Cleared** |
| `(*env)->ExceptionDescribe(env)` | Prints the exception and stack trace to a diagnostic channel such as stderr | **Cleared as a side effect** per the JNI Specification |
| `(*env)->Throw(env, throwable)` | Makes a `Throwable` object become the pending exception | **Sets a new exception** on success |
| `(*env)->ThrowNew(env, clazz, message)` | Creates and sets a new exception of the selected class | **Sets a new exception** on success |

### 3.1. Use ExceptionCheck When You Only Need to Know Whether an Error Occurred

```c
jint result = (*env)->CallStaticIntMethod(
    env, clazz, methodId, 8, 0);

if ((*env)->ExceptionCheck(env)) {
    /* Java error occurred. Do not use result as a successful division. */
    return 0; /* Placeholder for C return type; Java receives the exception. */
}

/* No pending exception from the call: result is meaningful. */
return result;
```

This is **an illustrative code snippet**, not a complete JNI library; `clazz`/`methodId` must have been validly looked up beforehand. When `ExceptionCheck` returns `JNI_TRUE`, it **does not clear** the exception. `return 0` only satisfies the C function's `jint` return type; Java **does not receive 0 as a successful result**, but receives the pending exception instead.

### 3.2. Use ExceptionOccurred When You Need to Keep the Throwable Object

```c
jthrowable error = (*env)->ExceptionOccurred(env);
if (error != NULL) {
    /* error is a local reference; pending exception still exists. */
    /* Can clean up local reference using DeleteLocalRef. */
    (*env)->DeleteLocalRef(env, error);
    return 0;  /* Pending exception continues to be passed back to Java. */
}
```

`ExceptionOccurred` is suitable when you later need to classify, store, log, or rethrow an exception. It **differs** from `ExceptionCheck` in that it creates a new local reference, so local ref lifecycle rules must be followed. Simply calling `ExceptionOccurred` and then using `error` to call any Java method while the pending exception is still present **is still wrong**; if you want to perform normal operations through JNI, you must handle the pending state first.

### 3.3. ExceptionDescribe Does Not Only "Print Logs"

The JNI Specification states that `ExceptionDescribe` prints the exception and backtrace to an error-reporting channel, **and simultaneously clears the pending exception**. Therefore, the following snippet is a trap:

```c
if ((*env)->ExceptionCheck(env)) {
    (*env)->ExceptionDescribe(env);
    return 0;
}
```

The author might think the error will continue propagating up to Java after printing the log, but `ExceptionDescribe` has already **cleared the error**. If the goal is **original propagation**, do not use `ExceptionDescribe` as a "harmless" logger. You can let Java receive/catch/log the exception at the Java boundary; or save the `jthrowable` object, clear, process according to an intentional workflow, and then use `Throw` to rethrow it (Section 8).

## 4. Why Is Checking Required After Call*Method?

Many JNI functions return explicit error codes on failure; for example, a lookup API may return `NULL` and set a pending exception. However, Java-calling functions such as `CallIntMethod` or `CallStaticIntMethod` **return primitive Java value types**, so the return value alone is not enough to signal an error.

For example:

- `CallIntMethod(...)`: `0` could be a valid success value or merely an unusable value because the callback threw an exception. **Do not infer success from `result == 0` or `result != 0`.**
- `CallObjectMethod(...)`: `NULL` could correspond to a valid Java `null` result, or there could be a pending exception. **You must check `ExceptionCheck`** when you need to distinguish them.
- `CallVoidMethod(...)`: the function has no return value, yet the Java method can still throw an exception.
- The `CallStatic<Type>Method`, `CallNonvirtual<Type>Method`, and `A` (`jvalue` array)/`V` (`va_list`) variants share the same pending exception issue.

A principled safe sequence of JNI calls:

```text
[Already have valid env, obj, methodId]
  -> Call<Type>Method(...)
  -> ExceptionCheck / ExceptionOccurred
       +-- has exception: permitted cleanup + return (propagate)
       |                    or clear + intentional handling
       +-- no exception: use result, continue JNI normally
```

**Check immediately after any boundary that can throw an exception.** Do not defer checking across a chain of `GetFieldID`, `NewStringUTF`, or other `Call*Method` calls, because those APIs are not guaranteed to be safe when the thread has a pending exception.

Additionally, `GetMethodID`/`GetStaticMethodID`/`FindClass` can also fail with Java exceptions such as `NoSuchMethodError`/`NoClassDefFoundError`. You must check the lookup result **before calling the method**, and if the lookup has already created an exception, return/clean up instead of trying to continue.

## 5. Which JNI Calls Are Safe When a Pending Exception Already Exists?

The JNI specification lists a set of APIs that are safe when a pending exception is present. Key groups:

- **Observing/controlling exceptions:** `ExceptionOccurred`, `ExceptionCheck`, `ExceptionDescribe`, `ExceptionClear`.
- **Releasing local/global/weak JNI references:** `DeleteLocalRef`, `DeleteGlobalRef`, `DeleteWeakGlobalRef`.
- **Returning resources borrowed from the JVM:** `ReleaseStringChars`, `ReleaseStringUTFChars`, `ReleaseStringCritical`, `Release<Type>ArrayElements`, `ReleasePrimitiveArrayCritical`.
- **Exiting monitors or local frames:** `MonitorExit`, `PopLocalFrame`, and `PushLocalFrame` within the permitted list.
- **Detaching an attached thread:** `DetachCurrentThread` under applicable conditions.

Do not interpret this as a license to call them arbitrarily. For example, `MonitorExit` must match a previously successful `MonitorEnter`, `ReleaseStringUTFChars` must have a buffer allocated by the corresponding API, and `DeleteLocalRef` must receive a valid local ref.

In particular, while a pending exception has not been cleared, **do not call** as if normal APIs such as `FindClass`, `GetObjectClass`, `GetMethodID`, `CallObjectMethod`, `NewStringUTF`, or `NewGlobalRef`. They are not among the APIs specified as safe in this state.

**Pure C functions** such as `free`, closing an OS file descriptor, or freeing native buffers you manage yourself are not JNI calls; you can still clean up C resources in the error branch. Avoid calling native functions with complex side effects if the program logic is already in an error state.

## 6. Two Standard Strategies After JNI Calls Java and Encounters an Exception

### A. Let the Original Exception Propagate to Java (Propagate)

Apply when the native method cannot or should not recover:

```c
jint result = (*env)->CallStaticIntMethod(env, cls, mid, x, y);

if ((*env)->ExceptionCheck(env)) {
    /* Clean up JNI references/borrowed buffers if any. */
    return 0; /* Do not call ExceptionClear. */
}
return result;
```

After the native method returns, the JVM continues propagating the exception to the Java caller. The caller can handle it with `try/catch`, and the stack trace preserves the original cause. The C value `0` on the error branch **is ignored as a success value**.

**Prefer this approach** if the callback violates its contract or throws an unrecoverable error; do not swallow exceptions on your own just to continue the native workflow.

### B. Clear the Exception for Intentional Recovery (Handle/Recover)

Apply when a specific Java error is a **pre-designed** scenario and the caller should receive a fallback:

```c
jint result = (*env)->CallStaticIntMethod(env, cls, mid, x, y);

if ((*env)->ExceptionCheck(env)) {
    (*env)->ExceptionClear(env);
    return fallback;
}
return result;
```

After `ExceptionClear`, JNI can continue along the recovery branch. However, this operation **swallows the original exception**, which can hide programming bugs or `OutOfMemoryError`. Used in lessons to illustrate the mechanism, whereas production code should **only clear after classifying and deciding the error is recoverable**, logging/recording per policy, or wrapping into a new exception with cause information.

| Need | Action with pending exception | Consequence on Java side |
| --- | --- | --- |
| Want Java caller to catch the exact callback exception | Do not clear; clean up resources and return | Java sees the original exception |
| Error is acceptable and fallback is defined | Clear after deciding to handle | Java sees the fallback instead of an exception |
| Want to turn error A into error B | Retrieve Throwable, clear, create/`Throw` appropriate error | Java sees error B (depending on how cause is preserved) |
| Only want to capture debug info | Do not carelessly call `ExceptionDescribe` and return | Avoids accidentally clearing the error |
| Want to continue calling normal JNI APIs | Clear before continuing | Must ensure important error information is not lost |

## 7. Complete Practical Example Java 17+ / JNI C

The example uses a `demo.jni.PendingDemo` class with three `native` methods, illustrating all three scenarios:

1. **Java call succeeds:** the division result is used.
2. **Java call throws ArithmeticException:** native code detects it with `ExceptionCheck` and **clears** it per policy to return a fallback.
3. **Another Java call throws ArithmeticException:** native code detects it but **does not clear** it, letting Java `try/catch` catch the original error.
4. **Java method returns an object:** check for errors after `CallStaticObjectMethod`, without confusing the object result with the exception state.

### 7.1. File src/demo/jni/PendingDemo.java

```java
package demo.jni;

public final class PendingDemo {
    static {
        System.loadLibrary("pendingdemo");
    }

    private static int compute(int a, int b) {
        return a / b;
    }

    private static String compose(String who) {
        return "Hi " + who;
    }

    public static native int recover(int a, int b, int fallback);
    public static native int propagate(int a, int b);
    public static native String greeting(String who);

    public static void main(String[] args) {
        System.out.println("Normal: " + recover(8, 2, -1));
        System.out.println("Recovered: " + recover(8, 0, -1));

        try {
            propagate(8, 0);
            System.out.println("Unexpected: no exception");
        } catch (ArithmeticException error) {
            System.out.println("Propagated: " + error.getMessage());
        }

        System.out.println("Object: " + greeting("JNI"));
    }
}
```

`compute(8, 0)` throws `ArithmeticException` because of integer division by 0. The `compute` and `compose` methods are regular Java methods, yet C can call them using `GetStaticMethodID` and `CallStatic<Type>Method` even when they are declared `private` in the class where the JNI methods are defined.

### 7.2. Generate Class Files and JNI Header

Run from the root directory of the example, on a Linux/macOS shell:

```bash
mkdir -p build/classes build/include build/native

javac -h build/include \
  -d build/classes \
  src/demo/jni/PendingDemo.java
```

`javac -h` generates `build/include/demo_jni_PendingDemo.h`. The exact prototype section was verified with `javac -h` on JDK 24:

```c
JNIEXPORT jint JNICALL Java_demo_jni_PendingDemo_recover
  (JNIEnv *, jclass, jint, jint, jint);

JNIEXPORT jint JNICALL Java_demo_jni_PendingDemo_propagate
  (JNIEnv *, jclass, jint, jint);

JNIEXPORT jstring JNICALL Java_demo_jni_PendingDemo_greeting
  (JNIEnv *, jclass, jstring);
```

Signatures generated from the native methods:

- `recover(int,int,int):int` → `(III)I`.
- `propagate(int,int):int` → `(II)I`.
- `greeting(String):String` → `(Ljava/lang/String;)Ljava/lang/String;`.

### 7.3. File PendingDemo.c

```c
#include <jni.h>
#include "demo_jni_PendingDemo.h"

/* Recover with fallback: intentionally clears exception for illustration.
   Production: only clear error types that have been classified as allowed. */
JNIEXPORT jint JNICALL Java_demo_jni_PendingDemo_recover(
        JNIEnv *env, jclass cls, jint a, jint b, jint fallback) {
    jmethodID mid = (*env)->GetStaticMethodID(
            env, cls, "compute", "(II)I");

    if (mid == NULL) {
        /* Lookup may have set a pending NoSuchMethodError.
           Do not call normal JNI APIs when there is a pending exception. */
        return 0;
    }

    jint result = (*env)->CallStaticIntMethod(env, cls, mid, a, b);

    if ((*env)->ExceptionCheck(env)) {
        (*env)->ExceptionClear(env);
        return fallback;
    }

    return result;
}

/* Keep pending exception intact for the Java caller to catch. */
JNIEXPORT jint JNICALL Java_demo_jni_PendingDemo_propagate(
        JNIEnv *env, jclass cls, jint a, jint b) {
    jmethodID mid = (*env)->GetStaticMethodID(
            env, cls, "compute", "(II)I");

    if (mid == NULL) {
        return 0; /* Let lookup error propagate. */
    }

    jint result = (*env)->CallStaticIntMethod(env, cls, mid, a, b);

    if ((*env)->ExceptionCheck(env)) {
        return 0; /* Do NOT call ExceptionClear. */
    }

    return result;
}

/* Call Java method returning String and check pending exception. */
JNIEXPORT jstring JNICALL Java_demo_jni_PendingDemo_greeting(
        JNIEnv *env, jclass cls, jstring who) {
    jmethodID mid = (*env)->GetStaticMethodID(
            env, cls, "compose",
            "(Ljava/lang/String;)Ljava/lang/String;");

    if (mid == NULL) {
        return NULL;
    }

    jstring result = (jstring) (*env)->CallStaticObjectMethod(
            env, cls, mid, who);

    if ((*env)->ExceptionCheck(env)) {
        return NULL; /* Let Java receive the original exception. */
    }

    return result;
}
```

**Note on return values:** in `propagate`, `return 0` while an exception is pending does not mean "return 0 to Java". It only exits the C function validly and lets the JVM pass `ArithmeticException` up to Java. In `recover`, after `ExceptionClear`, `fallback` is **truly the value Java receives**.

**Local reference in `greeting`:** `jstring result` is a local reference returned from JNI; the native function can `return result` to Java. Do not call `DeleteLocalRef(result)` before returning it. If additional temporary references are used, they must be managed separately.

**Error-catching scope of `recover`:** in this short example, `ExceptionClear` handles any exception that `compute` might throw. Because `compute` only performs division, the test branch with `b=0` is intentional. In a real system, do not automatically swallow every `Throwable`; see Section 8 to classify before clearing/converting errors.

### 7.4. Compiling the Native Library on Linux

Requires JDK 17+ and GCC. `JAVA_HOME` must point to a **JDK** containing the `include/jni.h` directory:

```bash
gcc -std=c11 -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/include \
  -o build/native/libpendingdemo.so \
  PendingDemo.c

java -Djava.library.path=build/native \
  -cp build/classes \
  demo.jni.PendingDemo
```

**Exact expected stdout when compiled, library loaded, and executed successfully:**

```text
Normal: 4
Recovered: -1
Propagated: / by zero
Object: Hi JNI
```

Why?

- `recover(8,2,-1)` calls `compute` successfully, `ExceptionCheck` returns `JNI_FALSE`, and the result is `4`.
- `recover(8,0,-1)` calls `compute` which throws `ArithmeticException`, native code calls `ExceptionClear` and returns the fallback `-1`.
- `propagate(8,0)` receives the pending `ArithmeticException`, does not clear it, and returns; Java catches the error, and `getMessage()` is `/ by zero` per standard Java integer behavior.
- `greeting("JNI")` calls `compose` and returns the string `Hi JNI`.

In cases where a modern JVM warns about native access permissions, a message may be emitted **on stderr**, without changing the four stdout lines above when the program has permission to call JNI. Depending on the JDK/module policy, the `--enable-native-access=ALL-UNNAMED` argument may be needed for classpath programs if the runtime supports or requires it.

### 7.5. Compiling on macOS or Windows

**macOS:** after running `javac -h` and creating the `build/native` directory:

```bash
clang -O2 -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Ibuild/include \
  -o build/native/libpendingdemo.dylib \
  PendingDemo.c

java -Djava.library.path=build/native \
  -cp build/classes \
  demo.jni.PendingDemo
```

**Windows:** open Visual Studio Developer Command Prompt with `cl`, JDK, and `JAVA_HOME`:

```bat
mkdir build\classes
mkdir build\include
mkdir build\native

javac -h build\include -d build\classes src\demo\jni\PendingDemo.java

cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" /I"build\include" PendingDemo.c /Febuild\native\pendingdemo.dll

java -Djava.library.path=build\native -cp build\classes demo.jni.PendingDemo
```

The library Java requests with `System.loadLibrary("pendingdemo")` commonly has the name `libpendingdemo.so` (Linux), `libpendingdemo.dylib` (macOS), or `pendingdemo.dll` (Windows). Ensure the JDK and C compiler have the same architecture (x64/ARM64...). If the build directories already exist, the `mkdir` command on Windows may report that they already exist; this does not change the example logic.

## 8. Selective Handling: Only Recover Known Errors, Preserve Other Errors

The `recover` example in Section 7 prioritizes demonstrating `ExceptionCheck`/`ExceptionClear` clearly. A reliable library needs a narrower policy: **only recover from error types already deemed recoverable**, without accidentally swallowing `OutOfMemoryError`, `LinkageError`, or bugs from Java callbacks.

If you want to classify exceptions, you can:

1. Prepare the `jclass` of the expected error type **before** the Java call that may throw an exception.
2. After the call, obtain the `jthrowable` using `ExceptionOccurred` (this is a **local reference**; pending still exists).
3. Call `ExceptionClear` **before** normal JNI operations such as `IsInstanceOf`.
4. If the error is of the expected type, clean up local references and return the fallback.
5. If the error is unexpected, `Throw(env, savedThrowable)` to make it pending again, clean up local references (permitted while pending), and then return.

The following C snippet **is only an illustration of handling inside a function that already has valid `env`, `cls`, `mid`, `a`, `b`, and `fallback`**; it is not a standalone function to compile on its own:

```c
/* Look up the class when there is no pending exception yet. */
jclass arithmeticClass =
        (*env)->FindClass(env, "java/lang/ArithmeticException");

if (arithmeticClass == NULL) {
    return 0;  /* Lookup error may be pending. */
}

jint value = (*env)->CallStaticIntMethod(env, cls, mid, a, b);

jthrowable original = (*env)->ExceptionOccurred(env);
if (original == NULL) {
    (*env)->DeleteLocalRef(env, arithmeticClass);
    return value;
}

/* original is a local ref; at this point the exception is still pending. */
(*env)->ExceptionClear(env);

/* Normal JNI APIs may only be called after clearing. */
jboolean expected =
        (*env)->IsInstanceOf(env, original, arithmeticClass);

if ((*env)->ExceptionCheck(env)) {
    /* If the classification step encounters a new error, preserve the new error. */
    (*env)->DeleteLocalRef(env, arithmeticClass);
    (*env)->DeleteLocalRef(env, original);
    return 0;
}

(*env)->DeleteLocalRef(env, arithmeticClass);

if (expected == JNI_TRUE) {
    (*env)->DeleteLocalRef(env, original);
    return fallback;
}

/* Error is not of an allowed type: restore the original exception. */
(*env)->Throw(env, original);
(*env)->DeleteLocalRef(env, original);
return 0;
```

This approach also illustrates **distinguishing state from handle**: `ExceptionClear` removes the pending status, but `original` is a valid local reference to the exception and can still be used to `Throw` it again. If during handling a JNI operation throws a new exception, you need a policy to avoid overwriting or losing that new error. A production system must also address subclass classification, contextual logging, and preserving *cause* if converting to another error type.

**Do not use this complex mechanism just to propagate.** When you do not want to handle the error, after `ExceptionCheck` simply perform permitted cleanup and return; this is the simplest and least error-prone path.

## 9. Cleanup When a Callback Has Thrown an Exception

In JNI, native code often holds resources allocated by JNI APIs: local references, string buffers, primitive arrays, monitors, or C memory. When a Java callback throws an exception, these resources must still be cleaned up **without calling unsafe JNI APIs**.

Example of an **illustrative C snippet** (not a standalone runnable method; assumes `env`, `array`, `clazz`, and `methodId` are valid; `array` is `jintArray`):

```c
jint *elements = (*env)->GetIntArrayElements(env, array, NULL);
if (elements == NULL) {
    /* OutOfMemoryError may already be pending; do not use elements. */
    return;
}

/* Call Java callback (void method) that may throw an exception. */
(*env)->CallStaticVoidMethod(env, clazz, methodId);

if ((*env)->ExceptionCheck(env)) {
    /* ReleaseIntArrayElements belongs to the safe cleanup group during pending.
       JNI_ABORT: do not copy changes from native buffer back to Java array. */
    (*env)->ReleaseIntArrayElements(env, array, elements, JNI_ABORT);
    return; /* Do not clear => Java receives the original error. */
}

/* Success branch: release the buffer. */
(*env)->ReleaseIntArrayElements(env, array, elements, JNI_ABORT);
```

Similarly, when data has been borrowed from `GetStringUTFChars`, the corresponding `ReleaseStringUTFChars` must be called; when creating local references, consider `DeleteLocalRef`; when `MonitorEnter` succeeds, `MonitorExit` must be called on the error path. With `GetPrimitiveArrayCritical`/`GetStringCritical`, also follow *critical region* restrictions and release resources early, avoiding arbitrary callbacks during the critical period; the example above uses regular `GetIntArrayElements`.

**Note:** cleanup is not an operation that "swallows exceptions". `DeleteLocalRef`, `ReleaseStringUTFChars`, or `ReleaseIntArrayElements` only release their respective resources and do not automatically clear a pending exception. The goal is both to avoid leaking memory/locks and to allow Java to receive the original error.

### Do Not Ignore Exceptions to Make Further JNI Calls

Common wrong pattern:

```c
jobject result = (*env)->CallObjectMethod(env, obj, methodId);
jclass type = (*env)->GetObjectClass(env, result); /* WRONG if pending exists. */
```

More correct:

```c
jobject result = (*env)->CallObjectMethod(env, obj, methodId);

if ((*env)->ExceptionCheck(env)) {
    /* Safe cleanup, then return; or clear per policy. */
    return;
}

if (result != NULL) {
    jclass type = (*env)->GetObjectClass(env, result);
    if (type == NULL || (*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, result);
        return;
    }

    /* Use type here when there is no exception. */
    (*env)->DeleteLocalRef(env, type);
}
if (result != NULL) {
    (*env)->DeleteLocalRef(env, result);
}
```

The second snippet is also **only an example in the context of a `void`-returning native method**, not a complete function. It demonstrates that errors must be checked not only after `CallObjectMethod`, but also after subsequent JNI APIs that can fail.

## 10. Scenarios to Distinguish and Remember

### Scenario 1: Callback Returns a Valid Java null

`CallStaticObjectMethod` returns `NULL`, but `ExceptionCheck` returns `JNI_FALSE`. This may simply be that the Java method executed `return null`. Do not fabricate an exception just because `NULL` was returned if the API contract allows returning null.

### Scenario 2: Callback Throws an Error but the C Value Looks Normal

`CallStaticIntMethod` returns some `jint`, but `ExceptionCheck` returns `JNI_TRUE`. Do not use that value; only handle the exception. There is no guarantee of a useful return value on the error branch.

### Scenario 3: A JNI Lookup Already Failed Before Calling Java

`GetStaticMethodID` returns `NULL` and sets a pending `NoSuchMethodError`. Do not continue calling `CallStaticIntMethod` with a `NULL` `jmethodID`. Return to let the error propagate or clear per policy.

### Scenario 4: Calling ExceptionDescribe for Debugging and Losing the Error

`ExceptionDescribe` prints the backtrace and **clears pending**. If native code returns immediately, Java no longer has the original exception. To propagate, avoid calling that API or intentionally build a proper save/clear/rethrow workflow.

### Scenario 5: One Callback Has an Exception, Then a Second JNI Callback Is Also Called

Wrong in that another `Call*Method` is continued while the pending exception has not been cleared. Choose one of two: finish handling/clearing the first error before making further calls, or return and let Java handle the first error.

### Scenario 6: Multiple Native Threads Calling Back into the JVM Simultaneously

A pending exception belongs to **the thread that created it**. One thread cannot read or clear another thread's pending exception simply by reusing `JNIEnv*`. A native worker must attach to the JVM and obtain its own `JNIEnv*`; cross-thread error reporting mechanisms must be designed like passing data/a valid Java Throwable reference, not sharing env pointers.

## 11. Debugging and Verification with -Xcheck:jni

On HotSpot/OpenJDK, `-Xcheck:jni` helps detect many JNI violations. For example:

```bash
java -Xcheck:jni \
  -Djava.library.path=build/native \
  -cp build/classes \
  demo.jni.PendingDemo
```

It additionally checks conditions such as JNI arguments, invalid references, and certain cases of calling unsafe JNI APIs while a pending exception exists. Typically used in **dev/test**, it carries performance overhead and is not guaranteed to catch every bug. Some severe JNI misuses can cause the JVM to halt or report errors.

When diagnosing a real system:

1. Identify **which JNI call called into Java** and can throw: `Call<Type>Method`, `CallStatic<Type>Method`, or `CallNonvirtual<Type>Method`.
2. Check whether `ExceptionCheck` is placed **immediately after the call**; check whether the `GetMethodID`/`GetStaticMethodID` lookup before the call was valid.
3. If an exception is pending, take the propagate or clear branch; **do not** continue calling unsafe JNI APIs.
4. If clearing, verify a clear rationale: which errors are allowed to recover, and does it hide unexpected errors?
5. If propagating, ensure C resources, local JNI refs, borrowed buffers, and monitors are cleaned up.
6. Verify that the Java caller handles the right error type and preserves the stack trace/cause as required.
7. Check the C compiler, JDK headers, library loading, and architecture; an error failing to find `.so`/`.dll` is a different issue from a pending exception after a callback.

**Note:** `-Xcheck:jni` is not a substitute for code review and testing error paths. Placing `ExceptionCheck`/`ExceptionOccurred` in the right spots and controlling the lifecycle of JNI resources remains the responsibility of the native code author.

## 12. Common Mistakes and Fixes

| Mistake | Cause/Consequence | Fix |
| --- | --- | --- |
| Calling `CallIntMethod` and immediately using the returned number | Java callback may have thrown an exception | `ExceptionCheck` before using the result |
| Only checking `result == NULL` after `CallObjectMethod` | Valid `null` and pending exception are two different states | Check `ExceptionCheck`, only then evaluate null |
| Continuing `FindClass`/`GetMethodID` while pending | Unsafe according to the JNI Specification | Return or `ExceptionClear` before other JNI calls |
| Thinking the exception is cleared because `ExceptionOccurred` returned an object | The API only returns a local reference | To clear, explicitly call `ExceptionClear` |
| Calling `ExceptionDescribe` to log and then returning | Specification states the API **clears** the exception | Do not use it if automatic propagation is desired |
| Calling `ExceptionClear` for every error | Swallows even unrecoverable errors | Classify errors, clear intentionally |
| Forgetting `DeleteLocalRef` for obtained `jthrowable` | Accumulates local references in loops | Clean up local ref when no longer needed |
| Cleaning up resources with JNI APIs not on the allowlist while pending | May cause warnings or native errors | Only clean up through permitted APIs |
| Calling `ThrowNew` while an old exception is already pending | Unsafe JNI operation rule | Preserve the old error, or clear intentionally first |
| Using another thread's `JNIEnv*` | Violates JNI thread-affinity | Attach the thread and use the thread's own env |
| Assuming `return 0` reaches Java even when pending | Java receives the exception, not the normal value | Properly distinguish propagate vs recover |
| Testing only the success branch | Misses JNI bugs, cleanup, and exception policy | Test normal, recover, propagate, object-null, lookup-failure |

## 13. Self-Check

**Question 1.** After `CallStaticIntMethod`, you get `0` and `ExceptionCheck` returns `JNI_TRUE`. Should the Java caller interpret this as `0` or an exception?

**Answer:** Exception. Primitive results are only meaningful when there is no pending exception; if native returns without clearing, Java sees the exception.

**Question 2.** Does `ExceptionCheck` lose the error?

**Answer:** No. It only returns a boolean reflecting the current state, creates no local exception ref, and does not clear.

**Question 3.** How does `ExceptionOccurred` differ from `ExceptionCheck`?

**Answer:** It returns a `jthrowable` which is a local reference to the pending exception; pending remains intact. You must manage the local reference lifecycle if you store `jthrowable`.

**Question 4.** After calling a Java callback that throws `ArithmeticException`, what must C code do if it wants Java to handle it?

**Answer:** Check pending, clean up using permitted operations, **do not clear**, and return from the native method. Java receives `ArithmeticException` and can `catch` it.

**Question 5.** What must C code do if it wants to ignore the exception to return a fallback?

**Answer:** Only do so when policy allows, call `ExceptionClear` to clear pending, and then return the fallback. In real systems, errors must be classified; do not swallow every `Throwable`.

**Question 6.** Is `ExceptionDescribe` an API that logs while keeping pending intact?

**Answer:** No. According to the JNI Specification, it prints the exception/backtrace and **clears pending** as a side effect.

**Question 7.** While pending, can you call `ReleaseStringUTFChars` to return a borrowed buffer? Should you call `NewStringUTF` right away?

**Answer:** `ReleaseStringUTFChars` is a permitted cleanup; `NewStringUTF` is not on the allowlist while pending remains, so you must clear/return first.

**Question 8.** `CallStaticObjectMethod` returns `NULL` but `ExceptionCheck` returns `JNI_FALSE`. Is that necessarily an error?

**Answer:** No. The Java callback may legitimately return `null`; handle according to the API contract.

## 14. Quick Takeaways

- **After every JNI call into Java**, check for a pending exception **before using the result or making further JNI calls**.
- `ExceptionCheck` only reads a boolean; `ExceptionOccurred` returns a local `jthrowable`; neither **clears**.
- `ExceptionClear` actively clears; `ExceptionDescribe` **also clears** the pending exception.
- **Propagate:** clean up permitted resources and return without clearing; Java catches the original exception.
- **Recover:** clear per policy before using a fallback or continuing JNI; do not swallow unexpected errors.
- While pending, only use JNI APIs that are safe per the specification (especially the **release/delete/exception** groups).
- `-Xcheck:jni` is useful in testing, but does not replace logic checks and native resource lifecycle management.

## Official Documentation

- [JNI Specification, Java 17 — Design Overview: Java Exceptions, Exception Handling](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html#java-exceptions)
- [JNI Specification, Java 17 — ExceptionOccurred / ExceptionDescribe / ExceptionClear / ExceptionCheck](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#exceptions)
- [JNI Specification — Calling Static Methods](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#calling-static-methods)
- [JNI Specification — Calling Instance Methods](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#calling-instance-methods)
- [Java SE 17 — javac -h (JNI headers)](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [Oracle Java SE 17 Troubleshooting — -Xcheck:jni](https://docs.oracle.com/en/java/javase/17/troubleshoot/command-line-options1.html)

**Conclusion:** a pending exception is the signal that a Java callback **has not finished successfully** from JNI's perspective. Check immediately with `ExceptionCheck`/`ExceptionOccurred`, then choose to **preserve it to propagate** or **clear it for intentional recovery**. Only use the result and call subsequent JNI APIs once the exception state has been properly handled.
