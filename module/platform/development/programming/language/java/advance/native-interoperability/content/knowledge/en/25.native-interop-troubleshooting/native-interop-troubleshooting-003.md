# Using `-Xcheck:jni` to Detect JNI Contract Violations

## Learning Objectives

After this lesson, you can:

- Explain why errors at the Java ↔ native code (C/C++) boundary can cause warnings, incorrect data, or cause the JVM to terminate abruptly.
- Enable `-Xcheck:jni` when running a Java application that uses the Java Native Interface (JNI), then read and classify the diagnostics.
- Identify the categories of errors that HotSpot's additional checking mechanism can detect: invalid JNI references, using `JNIEnv*` on the wrong thread, incorrect IDs/argument ranges, mismatched `Get...`/`Release...` pairs, skipping exception checks, and misusing critical regions.
- Reproduce a warning with a Java 17 + C example, fix the bug, and verify that the warning disappears.
- Know the limitations of the option: a program that runs cleanly with `-Xcheck:jni` is still not proven completely safe.

Context: the exercises use HotSpot/OpenJDK's JNI implementation, with JDK 17 or later. Message details may vary between JVM versions or vendors.

## 1. What does `-Xcheck:jni` actually do?

JNI allows Java to call native functions and native code to call back into the JVM via `JNIEnv*`. This API has a **contract**: objects/references must remain valid; `jmethodID` and `jfieldID` must match the class, type, and call kind; certain pointers allocated by the JVM must be returned properly; pending exceptions affect which JNI calls are allowed next.

C/C++ code does not automatically receive the same level of memory protection as Java. A JNI bug may only manifest when GC runs, when switching threads, or after very many calls. Running the JVM with:

```bash
java -Xcheck:jni -cp . Main
```

will instruct HotSpot to perform **additional checks on JNI calls**. This is a runtime diagnostic tool; it does not fix native code and does not replace compilers, sanitizers, or business-logic testing. The option is set **at JVM startup**. It has overhead, so it is typically enabled in development, integration testing, or bug-reproduction environments, rather than by default for all production traffic.

For example, for a JAR-packaged application:

```bash
java -Xcheck:jni -jar app.jar
```

You must ensure that the exact JVM process loading the native library receives this flag: if running via an IDE, test runner, service launcher, or script, place it in **VM options/JVM arguments**, not passed as `main(String[] args)` parameters.

## 2. Categories of violations that can be detected

| Category | Incorrect example | Why it is dangerous | Typical diagnostic level on HotSpot |
| --- | --- | --- | --- |
| `JNIEnv*` and threads | Using a `JNIEnv*` obtained on thread A to make JNI calls on thread B; using it from an unattached native thread | `JNIEnv*` is bound to the JVM thread context | Fatal error, the JVM may terminate |
| JNI references | Using a deleted local reference, an invalid reference, or the wrong object type | The JVM can no longer interpret the object validly | Fatal error |
| Method/field ID | Passing a `jmethodID` for the wrong class, wrong method type, confusing static/instance; using an incompatible `jfieldID` | The call or field access violates JVM metadata | Fatal error |
| JNI arguments | `NULL` where not permitted, out-of-bounds array index, mismatched parameter type | Accesses wrong memory region or violates API contract | Fatal error |
| Acquire/release pairs | Calling `Release...` with a pointer not allocated by the corresponding `Get...` | Violates ownership/lifecycle of JVM-managed memory | Fatal error when detected |
| Exception checking | After `Call...Method`, continuing to call unsafe JNI functions without checking for a possible Java exception | A pending exception can make subsequent calls invalid | Usually **WARNING** |
| Critical regions | Calling other JNI functions between `GetPrimitiveArrayCritical` and `ReleasePrimitiveArrayCritical`, or between `GetStringCritical` and `ReleaseStringCritical` | Can affect GC, prolong lock/pinning regions, and cause deadlock | Usually **WARNING** |
| Too many local references | Creating many local refs without freeing them or ensuring sufficient capacity | Increases native/JVM resource pressure | Can be **WARNING** |

These are **detection capabilities**, not a guarantee that every violation will be caught. Some warnings are preventive; serious errors such as corrupted references, wrong IDs, or invalid arguments can cause the JVM to stop immediately.

### Reading the two result types correctly

**WARNING**: HotSpot detected suspicious JNI usage, for example missing an exception check after a Java call. The program may continue and finish, but the native code must still be reviewed. The message and stack trace indicate the point of diagnosis, which is not necessarily the first statement that caused the bug.

**FATAL ERROR**: HotSpot detected a serious violation; the JVM may print thread/stack trace information, generate a crash log such as `hs_err_pid<PID>.log`, and terminate. Do not design code relying on Java `try/catch` to catch this JVM-level error. Not seeing a `FATAL ERROR` also does not confirm that native code is correct.

## 3. Lab: generate a warning and then fix it

This example intentionally skips the exception-checking step after C code calls a Java method. The callback actually succeeds, but JNI still requires native code to check for a possible exception before continuing to call an unsafe JNI operation. This is a way to observe a **WARNING** without intentionally passing a corrupted reference to crash the JVM.

**Prerequisites:** Linux, JDK 17+ including `java`, `javac`, and the `jni.h` header, along with a C compiler (`cc` or `gcc`). Set `JAVA_HOME` to point to the JDK directory, for example `/opt/jdk-17`. Create the following two files in the same empty directory.

**File `JniCheckDemo.java`:**

```java
public final class JniCheckDemo {
    static {
        System.loadLibrary("jnicheckdemo");
    }

    private static native void runNative();

    private static void callback() {
        System.out.println("Callback OK");
    }

    public static void main(String[] args) {
        runNative();
        System.out.println("Completed");
    }
}
```

**File `jnicheckdemo.c`, version intentionally missing the check:**

```c
#include <jni.h>
#include "JniCheckDemo.h"

JNIEXPORT void JNICALL Java_JniCheckDemo_runNative(JNIEnv *env, jclass cls) {
    jmethodID callback = (*env)->GetStaticMethodID(
        env, cls, "callback", "()V");
    if (callback == NULL) {
        return; /* Lookup failed: let the exception propagate to Java. */
    }

    (*env)->CallStaticVoidMethod(env, cls, callback);

    /* BUG: did not check for exception after CallStaticVoidMethod. */
    jclass stringClass = (*env)->FindClass(env, "java/lang/String");
    if (stringClass != NULL) {
        (*env)->DeleteLocalRef(env, stringClass);
    }
}
```

Compile on Linux, from the directory containing the two files:

```bash
javac -h . JniCheckDemo.java
cc -shared -fPIC -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" jnicheckdemo.c -o libjnicheckdemo.so
java -Xcheck:jni -Djava.library.path=. JniCheckDemo
```

`javac -h .` generates the header file `JniCheckDemo.h` with the native function declaration using the exact JNI name. The compiler builds `libjnicheckdemo.so` so that `System.loadLibrary("jnicheckdemo")` can find it via `java.library.path`. If you rename the native method, class name, or package, you must regenerate the header and use the exact generated function name.

Lines **printed by the application** when the callback runs normally:

```text
Callback OK
Completed
```

With HotSpot and `-Xcheck:jni`, a warning similar to the following may appear between/beside those lines:

```text
WARNING in native method: JNI call made without checking exceptions when required to from CallStaticVoidMethod
```

The actual message may include a stack trace and differ slightly by build/JDK; the ordering when merging stdout with stderr may also differ. Note: even when the callback **does not throw an exception**, the warning can still appear, because the issue is that the native code skipped **the operation to check whether an exception occurred**.

### Proper fix

Replace the contents of `jnicheckdemo.c` with the complete version:

```c
#include <jni.h>
#include "JniCheckDemo.h"

JNIEXPORT void JNICALL Java_JniCheckDemo_runNative(JNIEnv *env, jclass cls) {
    jmethodID callback = (*env)->GetStaticMethodID(
        env, cls, "callback", "()V");
    if (callback == NULL) {
        return; /* If NoSuchMethodError occurs, let the exception propagate. */
    }

    (*env)->CallStaticVoidMethod(env, cls, callback);
    if ((*env)->ExceptionCheck(env)) {
        return; /* Let the pending exception be thrown back to Java. */
    }

    jclass stringClass = (*env)->FindClass(env, "java/lang/String");
    if (stringClass == NULL) {
        return; /* If an exception occurs, let the JVM propagate it. */
    }
    (*env)->DeleteLocalRef(env, stringClass);
}
```

Recompile the native library (no need to change the Java code) and run again:

```bash
cc -shared -fPIC -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" jnicheckdemo.c -o libjnicheckdemo.so
java -Xcheck:jni -Djava.library.path=. JniCheckDemo
```

Expected result: the program still prints `Callback OK` and `Completed`; the warning **missing exception check after `CallStaticVoidMethod`** no longer appears. `ExceptionCheck` only checks the status; if the Java callback throws an exception, return from the native method so the exception is propagated to Java—do not arbitrarily continue calling JNI functions while an exception is pending.

**Note for other platforms:** macOS uses the `include/darwin` header directory and typically builds the `libjnicheckdemo.dylib` library with `clang -dynamiclib`; Windows uses `include/win32` and the `jnicheckdemo.dll` library (for example, compiled with MSVC). The `cc` command above is written specifically for Linux and should not be copied verbatim to Windows.

## 4. Fix rules by category

### 4.1. Local/global references and lifecycle

- Local references (such as the result of `FindClass`) are normally valid within the current native invocation and are freed by the JVM when the native function returns. If you create many inside a long loop, call `DeleteLocalRef` on each iteration or manage local frames with `PushLocalFrame`/`PopLocalFrame`.
- Do not store a local reference in a static/native cache variable to reuse after the native method has returned to Java. If you need to keep an object longer or across appropriate calls/threads, create a `NewGlobalRef` and free it with `DeleteGlobalRef` at the right time.
- Do not use a reference after `DeleteLocalRef`/`DeleteGlobalRef` has invalidated it. `-Xcheck:jni` can detect an invalid JNI reference, but checking does not replace proper lifecycle design.

### 4.2. `JNIEnv*` belongs to the right thread

`JNIEnv*` is the JNI interface for the **current thread**. Do not cache it and pass it to a worker thread. For a native thread created by C/C++ itself that needs to call into the JVM, obtain `JavaVM*` through the appropriate JNI mechanism, attach the thread with `AttachCurrentThread`, get a dedicated `JNIEnv*` for that thread, and detach when finished if the native code itself attached the thread. Do not arbitrarily detach JVM-managed threads. Check return values when attaching/detaching.

### 4.3. Checking exceptions at the JNI → Java boundary

`Call<Type>Method`/`CallStatic<Type>Method` functions can cause the Java method to throw an exception. After the call, use `ExceptionCheck` (or the appropriate exception-checking API) **before a subsequent JNI operation that is unsafe while an exception is pending**. For functions that return `NULL` to signal an error such as `GetStaticMethodID` or `FindClass`, check the result before using the ID/reference; do not clear the exception with `ExceptionClear` unless you actually handle the error and have chosen an alternative control flow. `ExceptionDescribe` is useful when printing information in a diagnostic environment, but it is not an exception-handling mechanism to replace Java's.

### 4.4. `Get...` and `Release...` pairs

When a JNI function such as `GetStringUTFChars` returns a pointer, the pointer is only valid under that function's contract and must be returned via `ReleaseStringUTFChars` with the **exact same `jstring` and exact same pointer**. `GetStringUTFChars` may return `NULL` (for example, when allocation fails); you must check before using it. Do not call `free()` on a pointer returned by the JVM and do not release it multiple times. Similarly, pay attention to `Get<Type>ArrayElements`/`Release<Type>ArrayElements` pairs and critical functions. Strings in APIs with the `UTF` suffix use **modified UTF-8** per the JNI specification; do not assume every standard UTF-8 byte sequence is valid when passing to `NewStringUTF`.

Resource management pattern, C snippet inside a JNI method that has received valid `env` and `value`:

```c
const char *chars = (*env)->GetStringUTFChars(env, value, NULL);
if (chars == NULL) {
    return; /* OutOfMemoryError may be pending. */
}

/* Read chars while the pointer is still valid; do not free(chars). */
consume_utf8_bytes(chars);

(*env)->ReleaseStringUTFChars(env, value, chars);
```

`consume_utf8_bytes` here is just an **illustrative function that the application must define itself**, not part of JNI. If the native processing function can fail, design cleanup paths so that release always happens exactly once before exiting; this snippet is not a standalone program.

### 4.5. Critical regions

`GetPrimitiveArrayCritical`/`GetStringCritical` can grant access to data that the JVM needs to keep pinned/stable. Between the corresponding Get and Release, keep the work **very short**, avoid blocking threads, and avoid other JNI operations that could force the VM to need GC or deadlock. `-Xcheck:jni` can detect other JNI calls within this interval and print a warning. Do not dismiss the warning as mere "noise" and ignore it.

## 5. Investigation workflow when a WARNING or FATAL ERROR occurs

1. **Reproduce in a controlled manner.** Record the JDK/vendor/version, operating system, actual run command, `.so`/`.dll`/`.dylib` library version, and input data. Use a native build with debug symbols when possible.
2. **Enable the flag on the right JVM.** For example `java -Xcheck:jni -Djava.library.path=. JniCheckDemo`; for real applications, put the flag in the VM arguments of the launcher/test runner. Run the reproduction scenario and capture all stdout, stderr, and the exit code.
3. **Read the message type and stack.** WARNING usually indicates a questionable contract usage; FATAL is a serious error that can stop the JVM. Locate the native method name, the immediately preceding JNI call, the current thread, and the exception state; for crashes, also look for `hs_err_pid*.log` if generated by the JVM.
4. **Trace back to the root cause.** For exception errors, review `Call...Method` calls before the warning. For bad references, check local/global references, lifetime, and threads. For ID/type mismatches, review the JNI signature (for example `()V` is a method with no parameters returning `void`), and whether the class/method is static or instance. For release mismatches, match the pointer against the original object.
5. **Fix the contract at the source.** Check results/exceptions before continuing to use them; release resources properly; use the `JNIEnv*` of the right thread; bound lifetimes; minimize work inside critical regions.
6. **Re-run the same test and expand paths.** Verify that the target warning disappears, the application still produces correct results, and no other warnings/errors appear. Test exception paths, many iterations, multiple threads, and resource lifecycles, because JNI bugs are often timing-dependent.

For rare errors, try multiple runs and keep the logs from the failing run. When the JVM aborts, do not assume that statements after the abort point ran or that output was flushed in time.

## 6. What `-Xcheck:jni` does NOT guarantee

- **Does not detect all JNI bugs.** Oracle explicitly states that the additional checks are not guaranteed to find every invalid argument or logic error; an unexecuted code path has not been checked.
- **Does not check general C/C++ memory safety.** Buffer overflows in the native heap, use-after-free on pointers allocated by `malloc`, native leaks, C/C++ data races, or undefined behavior outside JNI calls can slip through. Use AddressSanitizer/UndefinedBehaviorSanitizer, debuggers, leak/race tools, and appropriate crash analysis.
- **Does not prove business logic is correct.** Incorrect encoding conversion, unit mix-ups, wrong error handling, or type conversions that still satisfy the JNI contract can produce wrong results without triggering a warning.
- **Does not guarantee identical behavior across all JVMs/JDKs.** The list of checks, log wording, and severity levels depend on the version/implementation. Examples and classifications here are based on HotSpot/JDK 17 documentation.
- **Does not replace Java + native testing.** You need to test success paths, exception paths, multi-threaded scenarios, GC pressure, and heavy load. Enabling `-Xcheck:jni` increases runtime checking overhead, so measure its impact before enabling it long-term.

## 7. Checklist for applying to a project

- [ ] Ensure the service/test runner starts the **JVM executing native code** with `-Xcheck:jni`.
- [ ] Save the run command, Java version, native library version, stdout/stderr, and exit code.
- [ ] After `Call...Method`, properly handle any potential pending exception before the next JNI call.
- [ ] `JNIEnv*` is not passed between threads; native threads are attached/detached properly.
- [ ] `jmethodID`/`jfieldID`, signatures, static/instance, and arguments match.
- [ ] Local/global references remain valid and are freed according to their lifecycle.
- [ ] Every `Get...`/`Release...` is paired with the exact object/pointer and cleaned up on all exit paths.
- [ ] Critical regions are short and contain no dangerous JNI calls inside.
- [ ] After fixing, re-run the same test checking business output, warning/fatal logs, and error paths.

## 8. Self-check questions

**Question 1.** A Java callback runs successfully, yet `-Xcheck:jni` warns after `CallStaticVoidMethod`. Did a Java exception necessarily occur?  
**Answer:** No. The warning may mean that the native code has not **checked for the possibility** of an exception before the next JNI call; calling `ExceptionCheck` in the right place resolves that violation.

**Question 2.** Why should you not pass a `JNIEnv*` obtained from thread A to thread B?  
**Answer:** This interface is bound to the current thread; thread B needs its own JNI environment (attaching if necessary), otherwise it can violate the contract and be terminated by HotSpot.

**Question 3.** Does a test running cleanly with `-Xcheck:jni` prove that the native library has no memory bugs?  
**Answer:** No. C/C++ bugs outside the scope of JNI checks, or unexecuted code paths, can still exist. Sanitizers, debuggers, and additional tests are still needed.

## Authoritative references

- Oracle JDK 17, *The java Command* (`-Xcheck:jni` section): https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle JDK 17, *Troubleshooting Guide – Command-Line Options*: https://docs.oracle.com/en/java/javase/17/troubleshoot/command-line-options1.html
- Oracle, *JNI Specification – JNI Functions* (reference lifecycle, string APIs, exceptions): https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html
- Oracle, *Secure Coding Guidelines for Java SE* (JNI boundary input validation/exception handling): https://www.oracle.com/java/technologies/javase/seccodeguide.html
