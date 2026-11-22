# JNI Exceptions: Preventing C++ Exceptions from Escaping Across the JNI Boundary and Translating Them to Java Errors

## 1. The problem: two incompatible exception mechanisms

In the Java Native Interface (JNI), Java calls a `native` method implemented in C/C++, or C++ calls back into a Java method. The two exception systems have different semantics:

- **C++ exception:** the `throw` statement throws a C++ object such as `std::invalid_argument`, `std::runtime_error`, `std::bad_alloc`. The C++ runtime walks through C++ stack frames via **stack unwinding** to find a `catch`, while calling destructors of stack objects.
- **Java exception:** the JVM manages `Throwable`, for example `IllegalArgumentException`, `ArithmeticException`, `OutOfMemoryError`. JNI has a **pending Java exception** state on the current thread. `ThrowNew` or `Throw` sets this state; when the native method returns, the JVM propagates the error to the Java caller.

A C++ exception **must not escape uncontrolled across the JNI boundary** into the JVM. The Java runtime is under no obligation to understand the C++ exception ABI and has no guarantee of safe unwinding through Java frames. The consequences can be `std::terminate`, a crash, or undefined behavior. Therefore, a JNI entry point must **catch C++ exceptions, translate them into Java exceptions via JNI, and then return through the JNI entry/exit point according to normal conventions**.

```text
Java calls native method
          │
          ▼
   C++ JNI entry point
          │
     try { work(); }
          │
     ┌────┴─────────┐
     │              │
   OK, return    C++ throw
                    │
                catch(...) in C++
                    │
                choose Java exception class
                    │
             env->ThrowNew(...)
                    │
              Java exception pending
                    │
             return across JNI
                    │
             JVM throws Java Throwable
                    │
              Java try/catch
```

**The reverse direction also matters:** if C++ calls Java using `CallObjectMethod`/`CallVoidMethod` and the Java method throws a `Throwable`, **C++ `catch (...)` does not automatically catch it**. It is a pending Java exception and must be checked using `ExceptionCheck`.

## 2. Safe workflow at the JNI boundary

1. **Wrap C++ work that may throw inside `try`** at every JNI entry point. Do not leave an allocation, object initialization, library call, or data processing step that can throw outside the protected region.
2. **Catch meaningful exceptions first:** `std::invalid_argument`, `std::overflow_error`, `std::bad_alloc`… Then catch `std::exception`, and place **`catch (...)` last** to also intercept exceptions that do not inherit from `std::exception`.
3. **Map C++ exceptions to Java classes matching the API contract.** For example, input errors → `IllegalArgumentException`, math → `ArithmeticException`, allocation → `OutOfMemoryError`. This is a design choice, **not an automatic JNI mechanism**.
4. **Do not overwrite a pending Java exception** that already exists. Only look up the exception class via `FindClass` and create a new exception via `ThrowNew` when the state allows it.
5. **Clean up C++ resources with RAII**, clean up JNI references according to their type/lifetime, and then **return**. `ThrowNew` does not exit the C++ function by itself.
6. **Have a policy when creating the Java exception itself fails.** Do not let the native method silently return a success value when even the C++ error has not been communicated back to Java.

**Wrong** examples:

```cpp
// WRONG: C++ exception can escape out of the JNI entry point.
JNIEXPORT jint JNICALL Java_demo_jni_Bad_execute(JNIEnv*, jclass) {
    throw std::runtime_error("broken");
}

// WRONG: ThrowNew only sets a pending Java exception, does not unwind C++.
env->ThrowNew(exceptionClass, "broken");
doMoreNativeWork(); // C++ still runs; may violate JNI state.
```

The snippets above **only illustrate errors**, not standalone programs. Section 5 has a correct program that has been compiled and run.

## 3. JNI APIs for reporting and checking Java exceptions

In C++ with `JNIEnv* env`, call `env->Function(...)`; plain C uses the form `(*env)->Function(env, ...)`.

| API | Purpose | Important notes |
| --- | --- | --- |
| `env->ThrowNew(jclass, const char*)` | Creates a new Java exception and sets the pending exception | Message uses **modified UTF-8**; returns `JNI_OK` on success, a negative value on failure |
| `env->Throw(jthrowable)` | Sets an existing Java `Throwable` as pending | Suitable when preserving the exact instance/cause |
| `env->ExceptionCheck()` | Returns `JNI_TRUE` when the thread has a pending Java exception | Does not create an extra local ref |
| `env->ExceptionOccurred()` | Returns a local reference to the pending exception or `NULL` | The local ref must be managed properly |
| `env->ExceptionClear()` | Clears the pending exception | Only do this when **actively handling/replacing** the error |
| `env->ExceptionDescribe()` | Prints the exception and stack trace to the diagnostic channel | **Has the side effect of clearing the pending exception** |
| `env->DeleteLocalRef(ref)` | Cleans up a local JNI reference | Allowed while a Java exception is pending |

A simple pattern:

```cpp
// Local snippet, does not include all failure branches.
if (!env->ExceptionCheck()) {
    jclass type = env->FindClass("java/lang/IllegalArgumentException");
    if (type != nullptr) {
        env->ThrowNew(type, "invalid native argument");
        env->DeleteLocalRef(type);
    }
}
return; // If this is a void-returning JNI function.
```

**`FindClass` can fail and create a pending exception.** Do not call `ThrowNew` with `jclass == nullptr`. If a Java exception is already pending beforehand, do not arbitrarily call `FindClass`/`ThrowNew` to replace it.

In C++, `ThrowNew` **is not equivalent to `throw`**. It does not automatically perform C++ stack unwinding, does not break out of blocks, and can let C++ continue running. After `ThrowNew` succeeds, clean up with valid operations and return.

## 4. Which Java type should C++ exceptions be mapped to?

| C++ case | Usually appropriate Java Throwable | Meaning |
| --- | --- | --- |
| `std::invalid_argument` | `IllegalArgumentException` | Java caller passed an invalid argument |
| `std::out_of_range` | `IndexOutOfBoundsException` if it is actually an index error | Depends on API contract |
| `std::overflow_error` | `ArithmeticException` | Operation cannot be represented |
| `std::bad_alloc` | `OutOfMemoryError` | Insufficient native memory |
| `std::runtime_error` due to invalid subsystem state | `IllegalStateException` | Runtime state error, not input |
| A C++ exception type not inheriting `std::exception` | Fallback `RuntimeException`, or custom Java exception | Intercepted by `catch (...)` |
| Java callback already has a pending exception | **Preserve the Java error** | Do not remap unless policy requires it |

The table is a **policy example**, not a default JNI mapping. Production libraries should have a clear contract for which Java exceptions callers can rely on and avoid exposing secrets/connection strings/internal paths in messages.

**Encoding issue:** `std::exception::what()` returns `const char*` but does not guarantee the string is encoded in **modified UTF-8** used by `ThrowNew`. The runnable example only uses ASCII messages, so it is safe. For real-world Unicode messages, transcode/escape or construct a valid Java `String` and build the Java Throwable via the appropriate API.

## 5. Runnable example: Java 17+ and C++17

The example includes two `native` methods: `divide` performs division with domain checks; `failNative` simulates C++ errors in two groups. The demo tests four error-translation branches: invalid input, overflow, runtime error, and an exception not belonging to `std::exception`.

### 5.1. File structure

```text
jni-cpp-exceptions/
├── src/
│   └── demo/
│       └── jni/
│           └── ExceptionBridgeDemo.java
├── native/
│   └── cppbridge.cpp
└── build/                        # generated during compilation
    ├── classes/
    ├── headers/
    └── lib/
```

### 5.2. `src/demo/jni/ExceptionBridgeDemo.java`

```java
package demo.jni;

public final class ExceptionBridgeDemo {
    static { System.loadLibrary("cppbridge"); }

    private ExceptionBridgeDemo() {}

    private static native int divide(int numerator, int denominator);
    private static native void failNative(boolean unknown);

    public static void main(String[] args) {
        System.out.println("OK: " + divide(10, 2));

        try {
            divide(7, 0);
        } catch (IllegalArgumentException e) {
            System.out.println("Zero: " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }

        try {
            divide(Integer.MIN_VALUE, -1);
        } catch (ArithmeticException e) {
            System.out.println("Overflow: " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }

        try {
            failNative(false);
        } catch (IllegalStateException e) {
            System.out.println("Standard: " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }

        try {
            failNative(true);
        } catch (RuntimeException e) {
            System.out.println("Unknown: " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }
    }
}
```

Java only knows about Java `Throwable`s translated by native code. `static native` methods have `jclass` as their implicit second JNI parameter, not `jobject`.

### 5.3. Generating the JNI header and Java bytecode

From the `jni-cpp-exceptions` directory on Linux:

```bash
mkdir -p build/classes build/headers build/lib

javac -encoding UTF-8 \
  -h build/headers \
  -d build/classes \
  src/demo/jni/ExceptionBridgeDemo.java
```

The generated header is `build/headers/demo_jni_ExceptionBridgeDemo.h`. The equivalent prototypes:

```cpp
/* Signature: (II)I */
JNIEXPORT jint JNICALL Java_demo_jni_ExceptionBridgeDemo_divide
  (JNIEnv *, jclass, jint, jint);

/* Signature: (Z)V */
JNIEXPORT void JNICALL Java_demo_jni_ExceptionBridgeDemo_failNative
  (JNIEnv *, jclass, jboolean);
```

This is an **illustrative excerpt**, not a replacement for the full `.h` file generated by the JDK. The C++ code below includes this exact header, keeping compatible prototypes and C linkage.

### 5.4. `native/cppbridge.cpp`

```cpp
#include "demo_jni_ExceptionBridgeDemo.h"
#include <exception>
#include <limits>
#include <new>
#include <stdexcept>

namespace {
void raiseJava(JNIEnv* env, const char* className,
               const char* message) noexcept {
    if (env->ExceptionCheck()) {
        return; // Existing Java exception has priority.
    }

    jclass exceptionClass = env->FindClass(className);
    if (exceptionClass == nullptr) {
        // FindClass should have raised a Java exception.
        if (!env->ExceptionCheck()) {
            env->FatalError("Cannot resolve Java exception class");
        }
        return;
    }

    const jint result = env->ThrowNew(exceptionClass, message);
    env->DeleteLocalRef(exceptionClass);

    if (result != JNI_OK && !env->ExceptionCheck()) {
        // Unable even to communicate failure back to Java.
        env->FatalError("Cannot report native exception to Java");
    }
}

// Invoked ONLY from a C++ catch handler with an active exception.
void translateCppException(JNIEnv* env) noexcept {
    try {
        throw;
    } catch (const std::invalid_argument& e) {
        raiseJava(env, "java/lang/IllegalArgumentException", e.what());
    } catch (const std::overflow_error& e) {
        raiseJava(env, "java/lang/ArithmeticException", e.what());
    } catch (const std::bad_alloc&) {
        raiseJava(env, "java/lang/OutOfMemoryError", "native allocation failed");
    } catch (const std::exception& e) {
        raiseJava(env, "java/lang/IllegalStateException", e.what());
    } catch (...) {
        raiseJava(env, "java/lang/RuntimeException", "unrecognized C++ exception");
    }
}
} // namespace

JNIEXPORT jint JNICALL Java_demo_jni_ExceptionBridgeDemo_divide(
        JNIEnv* env, jclass /* owner */, jint numerator, jint denominator) {
    try {
        if (denominator == 0) {
            throw std::invalid_argument("denominator must not be zero");
        }

        const long long result = static_cast<long long>(numerator)
                               / static_cast<long long>(denominator);

        if (result < std::numeric_limits<jint>::min()
                || result > std::numeric_limits<jint>::max()) {
            throw std::overflow_error("quotient out of jint range");
        }

        return static_cast<jint>(result);
    } catch (...) {
        translateCppException(env);
        return 0; // Placeholder result; pending Java exception takes precedence.
    }
}

JNIEXPORT void JNICALL Java_demo_jni_ExceptionBridgeDemo_failNative(
        JNIEnv* env, jclass /* owner */, jboolean unknown) {
    try {
        if (unknown == JNI_TRUE) {
            throw 42; // Deliberately not a std::exception.
        }
        throw std::runtime_error("native worker failure");
    } catch (...) {
        translateCppException(env);
        return;
    }
}
```

**Why does the program properly block C++ exceptions?**

1. `divide`/`failNative` both wrap operations that can throw in `try` and have `catch (...)`. No C++ exception from those operations escapes the entry point.
2. `translateCppException` runs **only in the context of a catch handler that has an active exception**. `throw;` in the helper rethrows the currently handled exception, and the `catch` branches classify it. **Do not call the helper outside a catch**; `throw;` when there is no active exception causes `std::terminate`.
3. Catch subtypes `std::invalid_argument`, `std::overflow_error`, `std::bad_alloc` before `std::exception`; the final `catch (...)` handles `throw 42`.
4. `raiseJava` checks for a pending Java exception. If one already exists, it does not make further `FindClass`/`ThrowNew` calls and preserves the original Java error.
5. When none is pending, the helper looks up the Java exception class, calls `ThrowNew`, and then `DeleteLocalRef`. Cleaning up a local ref **after setting a pending exception** is a valid JNI operation.
6. If it cannot even find the class or create the Java exception **without a pending exception**, the demo uses `FatalError` as a **last resort** so it does not return a fake success result. `FatalError` terminates the JVM, is only suitable for unrecoverable situations, and must have its own production policy.
7. The helpers `raiseJava`/`translateCppException` are `noexcept`, avoiding dynamic C++ allocations while translating errors. JNI entry points use **the exact signature from the header**: do not arbitrarily add `noexcept` to the JNI definition if it differs from the exception specification of the included declaration.
8. Compute the quotient using `long long` and then check the `jint` bounds. Direct `INT_MIN / -1` in signed 32-bit C++ can be **undefined behavior**, not automatically turning into `std::overflow_error`; the program proactively avoids it.
9. `return 0` in the error branch of `divide` is merely how a `jint`-returning function exits after setting a pending Java exception. Java receives the Throwable instead of using `0` as the division result.

### 5.5. Compiling C++17 and running on Linux

`JAVA_HOME` must be a JDK directory compatible with `javac`, containing `include/jni.h` and `include/linux/jni_md.h`. After the `javac -h` command, run:

```bash
g++ -std=c++17 -Wall -Wextra -Werror -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/headers \
  -o build/lib/libcppbridge.so \
  native/cppbridge.cpp

java -Xcheck:jni \
  -Djava.library.path=build/lib \
  -cp build/classes \
  demo.jni.ExceptionBridgeDemo
```

`g++` links the proper C++ runtime, `-fPIC -shared` creates the shared library `libcppbridge.so`; `System.loadLibrary("cppbridge")` corresponds to the logical name. The `-Ibuild/headers` flag lets the compiler find the JNI header. `-Xcheck:jni` helps detect certain JNI errors.

**Exact stdout, verified with OpenJDK 21 + G++ 14 on Linux (built with `-Wall -Wextra -Werror`, run with `-Xcheck:jni`):**

```text
OK: 5
Zero: IllegalArgumentException: denominator must not be zero
Overflow: ArithmeticException: quotient out of jint range
Standard: IllegalStateException: native worker failure
Unknown: RuntimeException: unrecognized C++ exception
```

On macOS, use `$JAVA_HOME/include/darwin` and library `libcppbridge.dylib`; on Windows, use `%JAVA_HOME%\include\win32`, a compatible C++ compiler/linker, and `cppbridge.dll`. The build command example above is specific to Linux.

## 6. Step-by-step when `ThrowNew` is called

For `divide(7, 0)`:

1. Java calls the native method; C++ receives two `jint`s.
2. C++ checks `denominator == 0` and executes `throw std::invalid_argument(...)`.
3. C++ stack unwinding reaches the `catch (...)` of `divide` **without** crossing the JNI boundary.
4. The translator identifies the error type as `std::invalid_argument` and calls the helper with `java/lang/IllegalArgumentException`.
5. `ThrowNew` sets a pending Java exception on the thread; this **does not immediately stop C++ execution**.
6. The helper returns; the JNI entry point returns across the JVM boundary.
7. The JVM delivers the Java `IllegalArgumentException` to the call site, where the Java `catch` prints the `Zero: ...` line.

**`ThrowNew` is not C++ `throw`:** it does not automatically invoke C++ destructors, does not automatically exit the function, and does not automatically build a C++ stack trace. Conversely, C++ `throw` is only handled by C++ catch and does not automatically form a Java Throwable.

`ThrowNew` takes a **Java exception class + message**. `Throw` takes **an existing `jthrowable`**. When you want to store a Java cause or complex metadata, you must construct the Java Throwable/chain yourself using Java APIs, rather than expecting JNI to automatically convert a C++ exception object and stack trace to Java.

## 7. Java callback throws an error: use `ExceptionCheck`, not just C++ `catch`

Example of native C++ calling a Java method:

```cpp
// Local snippet, not standalone: listener and methodId are already valid.
env->CallVoidMethod(listener, methodId);
if (env->ExceptionCheck()) {
    // Java callback threw a Throwable.
    // Clean up allowed JNI resources then return across the native boundary.
    return;
}
```

The following snippet has **no** effect in catching a Java exception:

```cpp
try {
    env->CallVoidMethod(listener, methodId);
} catch (const std::exception& e) {
    // Cannot automatically catch a pending Java Throwable.
}
```

If a Java callback throws an exception, JNI marks a **pending Java exception**, rather than turning it into a `std::exception`. While one is pending, most JNI functions **must not be called**. Permitted exceptions include certain check/clear and cleanup operations, such as `ExceptionCheck`, `ExceptionOccurred`, `ExceptionClear`, `DeleteLocalRef`, `DeleteGlobalRef`, and valid string/array release functions.

Normally, **preserve the pending exception, clean up, and return** so Java receives the original error. If you want to replace it, do so deliberately and consider keeping the original exception as the cause. `ExceptionDescribe` **clears the pending exception** after printing, so do not use it as a harmless logger.

## 8. Resource cleanup: RAII, destructors, and JNI references

C++ unwinding still requires resource cleanup. Prefer `std::unique_ptr`, `std::vector`, `std::lock_guard`, and RAII classes, avoiding manual `new/delete` across multiple error branches.

```cpp
// Sketch, not standalone: requires <vector> and doNativeWork.
try {
    std::vector<int> buffer(1024);
    doNativeWork(buffer);
} catch (...) {
    translateCppException(env);
    return;
}
```

The destructor of an RAII object must **not throw exceptions**, especially when another exception is already unwinding. If a destructor throws during that time, C++ may call `std::terminate` before the helper translates it to Java.

JNI references have a different lifetime from C++ resources:

- Local `jobject` from a JNI call can be cleaned up with `DeleteLocalRef` before the frame ends; clean up early in long loops.
- Global `jobject` from `NewGlobalRef` must have an owner and be deleted with `DeleteGlobalRef` at the right time; do not delete every global ref just because an exception occurred.
- `DeleteLocalRef`/`DeleteGlobalRef` belong to the cleanup group permitted during a pending Java exception.
- `JNIEnv *` and local references are tied to a thread; do not cache and use them from another thread.

An illustrative local wrapper:

```cpp
struct LocalRefGuard {
    JNIEnv* env;
    jobject ref;

    LocalRefGuard(JNIEnv* e, jobject r) noexcept : env(e), ref(r) {}
    LocalRefGuard(const LocalRefGuard&) = delete;
    LocalRefGuard& operator=(const LocalRefGuard&) = delete;

    ~LocalRefGuard() noexcept {
        if (ref != nullptr) env->DeleteLocalRef(ref);
    }
};
```

This is a separate snippet to explain RAII; it does not replace the program in Section 5. Only use the wrapper within the JNI frame and thread where `env` is valid; do not store it across native calls.

## 9. Failure branches when the exception translator itself fails

### `FindClass` returns `NULL`

Reasons can include the class not being found, lack of resources, or an inappropriate class loader. It may set a pending Java exception. **Do not call `ThrowNew` with an invalid `jclass`.** In the demo, all exception classes belong to Java core. For application-specific exception classes, a self-attached native thread may look up classes under a different context; it may be necessary to cache a global `jclass` from the right class loader or receive the class from Java at an appropriate time.

### `ThrowNew` fails

If native code already threw `std::bad_alloc`, allocating a Java `OutOfMemoryError` may also run into trouble. `ThrowNew` has a return result and needs a policy when a Java exception cannot be reported. The demo uses `FatalError` as an extreme fallback if there is no pending exception and it cannot report the error: that is **unrecoverable fail-fast**, not normal handling. Real projects can organize error data/messages to minimize allocations and have their own fallback strategy.

### Non-C++-exception errors

`catch (...)` does not automatically save you from `SIGSEGV`, memory corruption, `abort()`, `std::terminate`, native stack overflow, or undefined behavior. Prevention at the source is required: bounds checking, arithmetic that avoids UB, clear ownership, and using ASan/UBSan or appropriate tools. `-Xcheck:jni` only catches a subset of JNI violations.

### Compiling C++ without exception support

With `-fno-exceptions`, the `throw/try/catch` pattern cannot be used. You must use error codes/result types and translate them to Java Throwables right at the JNI boundary, while ensuring dependent libraries do not throw across an unsupported ABI.

### Native worker threads and asynchronous errors

`ThrowNew` sets an exception on the **current JNIEnv/thread**; it does not automatically throw onto another Java thread. If C++ spawns its own worker thread, the thread must attach to the JVM, have its own `JNIEnv*`, and report errors via a Java callback, `CompletableFuture`, or message queue per the async contract. A Java callback can leave a pending exception on the worker thread; it must be handled before continuing or detaching, and is not automatically converted into a C++ `catch`.

## 10. Common mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Crash/`std::terminate` on native error | C++ exception escaped the JNI function | Wrap all throw paths with `try/catch (...)` at the boundary |
| Java catches the wrong type | Wrong mapping or `std::exception` caught before subtype | Catch subtypes first; define a Java exception contract |
| Java callback throws but native does not detect it | Confusing pending Java exception with C++ throw | `ExceptionCheck` after `Call...Method` |
| C++ keeps working after `ThrowNew` | Forgetting that `ThrowNew` does not unwind | Perform valid cleanup then return |
| `FindClass` fails when creating exception | Wrong class name/loader or a pending exception already exists | Use internal class name `java/lang/...`; do not look up while pending |
| `ExceptionDescribe` loses the error | Debug function has a clear side effect | Do not use as a production logger |
| JVM crashes during cleanup | Destructor throws or JNI reference used after delete | `noexcept` RAII destructors; manage references properly |
| Wrong division result/crash at min-int | Signed overflow in C++ before throwing | Compute in a wider type, check `jint` bounds |
| Garbled Unicode characters in message | `what()` is not valid modified UTF-8 | Normalize encoding/Java String before ThrowNew |
| Compile error `noexcept` conflicting | JNI definition differs from header prototype | Use the exact `javac -h` generated prototype, catch-all inside |

**Do not arbitrarily put `noexcept` on a JNI entry point** if the generated header declares a different exception specification; the C++ compiler may reject the definition. Use `try/catch (...)` to guarantee non-escaping behavior; only use `noexcept` for internal helpers that truly do not throw.

## 11. Pre-production checklist

- [ ] The JNI entry point blocks every C++ exception that can arise inside.
- [ ] Catch order is correct, with `catch (...)` last and a clear Java exception mapping.
- [ ] Helpers do not accidentally clear a prior pending Java exception.
- [ ] `FindClass`/`ThrowNew` failures have handling; never return a fake success.
- [ ] After `ThrowNew`, clean up permitted resources and **return**, do not arbitrarily continue calling JNI.
- [ ] Do not pass unsafe/invalid modified UTF-8 messages into `ThrowNew`.
- [ ] RAII destructors do not throw, and local/global JNI references have clear owners.
- [ ] C++ catch is not used in place of `ExceptionCheck` after a Java callback.
- [ ] Consider thread, class loader, and exception propagation for async tasks.
- [ ] Test the success path, invalid argument, overflow, `std::bad_alloc`, non-`std::exception` exceptions, already-pending JNI errors, and cleanup.

## 12. Review questions

1. Why must `throw std::runtime_error(...)` not travel directly from C++ to Java across JNI?
2. Does `ThrowNew` automatically stop a C++ function? Why must you return after setting a pending Java exception?
3. Why must `catch (const std::bad_alloc&)` come before `catch (const std::exception&)`?
4. If C++ executes `throw 42`, which catch branch handles it? Why is `catch (...)` needed?
5. For `divide(Integer.MIN_VALUE,-1)`, why does the code need the `long long` type before division instead of relying on a C++ catch?
6. If a Java callback throws `IOException`, does C++ `catch (...)` automatically catch it? Which JNI API should be called?
7. If `FindClass` returns `NULL`, can `ThrowNew` be called immediately? What needs to be done with the pending exception?
8. Why is creating a Java `OutOfMemoryError` not guaranteed when a `std::bad_alloc` error has already occurred?
9. When a C++ destructor throws while another exception is unwinding, what can happen?
10. What mechanism does a native worker thread need to report an error to another Java thread besides calling `ThrowNew`?

**Remember:** **C++ exceptions must stop inside C++ `catch (...)` before crossing the JNI boundary.** Translate them into a Java `Throwable` via `ThrowNew`/`Throw`, clean up safely, and return. A **pending Java exception is not a C++ exception**; it must be checked and handled separately via JNI.

### Official documentation

- [Oracle JNI Specification JDK 21 — Design Overview / Java Exceptions](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html).
- [Oracle JNI Specification JDK 21 — JNI Functions: Throw, ThrowNew, ExceptionCheck](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html).
- [Android NDK — JNI tips: Exceptions](https://developer.android.com/ndk/guides/jni-tips).
- [JDK 21 javac tool — `-h` header generation](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html).
