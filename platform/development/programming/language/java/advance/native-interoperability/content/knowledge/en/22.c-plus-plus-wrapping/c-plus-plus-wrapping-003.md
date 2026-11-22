# Using an opaque handle to create, use, and destroy C++ objects

## 1. Problem: Java cannot arbitrarily control C++ object layout

In the topic **Wrapping C++ Libraries**, a common requirement is to let Java create an object implemented in C++, call its methods multiple times, and destroy the resource at the right time. A C++ class may contain constructors/destructors, `std::string`, `std::vector`, `std::mutex`, virtual methods, inheritance, or templates. **There is no single “C++ class ABI” guaranteeing that Java understands every class layout** across different compilers, versions, OSes, and ABIs.

A common solution: create a **C ABI wrapper** with an **opaque handle**. Java only holds a token/pointer meaning “my C++ object”, and **does not** see the internal structure. C-compatible functions perform all the work:

1. **Create:** call an exported C function to create the C++ object and return the handle.
2. **Use:** pass the handle to exported C functions to manipulate/read state.
3. **Destroy:** call **the exact destroy function provided by the library** after all uses are finished.

~~~text
                Java client                       Native C-compatible wrapper          C++ implementation
       --------------------------------       ------------------------------------     ---------------------
       Java owner private handle --------->  counter_create(initial, &out) ----------> new CounterHandle
                  |                                  |                                     {mutex, value}
                  +--- add(handle, delta) ----------> counter_add(handle, delta, &out) -->  lock, increment value
                  |                                  |
                  +--- get(handle) -----------------> counter_get(handle, &out) ---------> read state
                  |                                  |
                  +--- close()/destroy(handle) -----> counter_destroy(handle) ----------> delete CounterHandle
                                                                                          destructor + free
~~~

**Important warning:** An opaque handle makes the API easy to use and hides the implementation, **it does not guarantee memory safety by itself**. After `counter_destroy(h)`, the bit value of `h` may still be non-NULL, but it has become a **dangling pointer**. Calling a function again with `h` can cause undefined behavior, heap corruption, or crash the JVM. Therefore, this lesson combines the C++ boundary, error codes, Java ownership, and close-once.

### Learning objectives

After this lesson, you can:
- Distinguish the incomplete C type `typedef struct CounterHandle CounterHandle;` from the privately defined C++ struct.
- Design a C ABI with `counter_create`, `counter_add`, `counter_get`, and `counter_destroy` along with an ownership contract.
- Explain `extern "C"`, native symbol export, fixed-width integer types, and why `std::string`/C++ classes should not be exported directly.
- Catch C++ exceptions at the boundary, convert them to status codes; with JNI, map status to a Java exception.
- Use Java `AutoCloseable`, `try-with-resources`, and `synchronized` to destroy exactly once and reject calls after close.
- Pass handles via JNI `jlong` or FFM `MemorySegment`/`ValueLayout.ADDRESS` without reading the private C++ layout.
- Distinguish a lock protecting internal state from a **lifecycle gate** preventing destroy from interleaving with native uses.
- Diagnose double-free, use-after-free, memory leak, wrong ABI, error paths, and library unload.

### Versions and verification scope

**The main JNI path** runs on **Java 17+**. The full codebase has been **compiled/run on Linux with JDK 21, GCC 14.2, C++17, and `java -Xcheck:jni`**, along with a C11 client and native concurrency test. **The supplementary FFM path** uses the finalized `java.lang.foreign` API from **JDK 22+**, which has been **compiled with `javac --release 22` on Windows JDK 24**, but **FFM has not been run with a Windows DLL** because the Windows machine lacks a native C++ compiler. Outputs are marked as observed or expected accordingly; do not assume it runs on all three OSes when evidence only exists on one OS.

## 2. C API header: an opaque type and a stable set of functions

Create **`native/counter_api.h`**:

~~~c
#ifndef COUNTER_API_H
#define COUNTER_API_H

#include <stdint.h>

#ifdef _WIN32
# ifdef COUNTER_BUILD
#  define COUNTER_API __declspec(dllexport)
# else
#  define COUNTER_API __declspec(dllimport)
# endif
#else
# define COUNTER_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef struct CounterHandle CounterHandle;

typedef enum CounterStatus {
    COUNTER_OK = 0,
    COUNTER_BAD_ARGUMENT = 1,
    COUNTER_OVERFLOW = 2,
    COUNTER_NO_MEMORY = 3,
    COUNTER_INTERNAL_ERROR = 4
} CounterStatus;

/* Return fixed-width int32_t; enum is only used for naming constants. */
COUNTER_API int32_t counter_create(
        int32_t initial, CounterHandle **out);
COUNTER_API int32_t counter_add(
        CounterHandle *h, int32_t delta, int32_t *out);
COUNTER_API int32_t counter_get(
        CounterHandle *h, int32_t *out);
COUNTER_API void counter_destroy(CounterHandle *h);

#ifdef __cplusplus
}
#endif

#endif
~~~

**Explanation:**

- `typedef struct CounterHandle CounterHandle;` is an **incomplete type**: C callers know there is a type `CounterHandle` and can hold `CounterHandle *`, but cannot see its fields; they cannot call `sizeof(*h)` or `h->value`. The actual definition is kept private in `.cpp`.
- `CounterHandle *` is a pointer to the allocated resource. `CounterHandle **out` allows `counter_create` to write the new pointer into the caller's variable; passing only a regular `CounterHandle *` cannot change the pointer on the caller's side.
- `int32_t` instead of unsized `int` in the public interface: Java/JNI has a 32-bit `int` carrier, and FFM uses `ValueLayout.JAVA_INT`. The return status also uses `int32_t` instead of returning a C enum directly (because enum size can be affected by compiler options).
- `CounterStatus` provides names for clear errors: invalid argument, overflow, allocation failed, internal failure. The caller checks the status before reading out parameters.
- `extern "C"` gives C language linkage to functions when the header is included by a C++ compiler. It prevents C++ function name mangling, **does not** give a C++ class a stable ABI, and **does not** change memory ownership rules.
- `COUNTER_API` controls export/visibility. For a Windows DLL, use `COUNTER_BUILD` when compiling the library source; for a C caller including the header, `__declspec(dllimport)` helps the linker use the correct export.
- `counter_destroy` has no return type to report errors. The contract must require the owner to pass **a live handle** and call it **exactly once**. It allows NULL, but must not be called twice with **the same non-null pointer**.

### Why must the exact destroy function of the library be used?

An object created by C++ `new`/`std::make_unique` needs `delete` to invoke the destructor, release `std::mutex`/resource members, and use the library's exact allocator. Java **must not** use libc `free` to destroy that object, should not take the raw address and compute destructor offsets manually, and must not assume the JVM GC automatically knows the C++ object is alive.

### The header is only a contract, not an implementation

The C library can replace `std::mutex` with another mechanism, add fields, change algorithms, or optimize storage **without modifying the Java ABI** as long as the four exported functions keep compatible signatures and semantics. This is why “opaque” is more useful than trying to map a C++ class with `MemoryLayout.structLayout`.

## 3. C++ implementation: private object, status codes, no exceptions thrown across the C boundary

Create **`native/counter_api.cpp`**:

~~~cpp
#include "counter_api.h"

#include <cstdint>
#include <limits>
#include <memory>
#include <mutex>
#include <new>

struct CounterHandle {
    std::mutex mu;
    std::int32_t value;

    explicit CounterHandle(std::int32_t initial) : value(initial) {}
};

extern "C" COUNTER_API int32_t counter_create(
        int32_t initial, CounterHandle **out) {
    if (out == nullptr) return COUNTER_BAD_ARGUMENT;

    *out = nullptr;
    if (initial < 0) return COUNTER_BAD_ARGUMENT;

    try {
        auto ptr = std::make_unique<CounterHandle>(initial);
        *out = ptr.release();
        return COUNTER_OK;
    } catch (const std::bad_alloc&) {
        return COUNTER_NO_MEMORY;
    } catch (...) {
        return COUNTER_INTERNAL_ERROR;
    }
}

extern "C" COUNTER_API int32_t counter_add(
        CounterHandle *h, int32_t delta, int32_t *out) {
    if (h == nullptr || out == nullptr || delta < 0)
        return COUNTER_BAD_ARGUMENT;

    try {
        std::lock_guard<std::mutex> lock(h->mu);

        if (delta > std::numeric_limits<std::int32_t>::max() - h->value)
            return COUNTER_OVERFLOW;

        h->value += delta;
        *out = h->value;
        return COUNTER_OK;
    } catch (...) {
        return COUNTER_INTERNAL_ERROR;
    }
}

extern "C" COUNTER_API int32_t counter_get(
        CounterHandle *h, int32_t *out) {
    if (h == nullptr || out == nullptr)
        return COUNTER_BAD_ARGUMENT;

    try {
        std::lock_guard<std::mutex> lock(h->mu);
        *out = h->value;
        return COUNTER_OK;
    } catch (...) {
        return COUNTER_INTERNAL_ERROR;
    }
}

extern "C" COUNTER_API void counter_destroy(CounterHandle *h) {
    // Owner calls exactly once after all users stop using h.
    delete h;
}
~~~

This is the **complete C++ source** to compile with `counter_api.h`. In actual tests, GCC 14.2 compiled with `-std=c++17 -Wall -Wextra -Werror -pedantic` with zero warnings/errors.

### 3.1. Details about constructor and ownership transfer

`counter_create` does not return the pointer directly: it writes via `CounterHandle **out` and returns a status. At the beginning of the function, after verifying `out!=nullptr`, it sets `*out=nullptr` so the caller does not have a garbage pointer on error. `std::make_unique<CounterHandle>(initial)` holds temporary ownership; `release()` transfers ownership **to the native C ABI caller**. If `new` fails, `std::bad_alloc` is mapped to `COUNTER_NO_MEMORY`.

Contract after create:

~~~text
COUNTER_OK:
   *out != NULL
   caller owns exactly ONE CounterHandle*
   caller must call counter_destroy(*out) after stopping use

non-COUNTER_OK:
   *out == NULL
   caller does not own a new object
   caller must not call add/get with the out pointer
~~~

`COUNTER_OK` only represents the native function status, not a Java `boolean`. Every caller (JNI, FFM, or C) is responsible for checking it.

### 3.2. Details about use and overflow

`counter_add` requires a non-negative delta. With a non-negative counter value from the constructor, the condition `delta > INT32_MAX - value` is checked **before** addition so it does not cause signed integer overflow. If invalid, the function returns `COUNTER_BAD_ARGUMENT` or `COUNTER_OVERFLOW`, while `value` remains unchanged. On success, `*out` contains the new value.

`std::lock_guard<std::mutex>` locks/unlocks the mutex via RAII. It protects the **mutable value** when multiple threads call `counter_add/get` on the same still-live object. However, if another thread calls `counter_destroy`, the destructor will also destroy the mutex — **no internal lock can replace a lifecycle gate/lease** that ensures the object is not deleted while users exist.

### 3.3. Details about destroy

`counter_destroy` calls `delete h`, running the `CounterHandle` destructor and reclaiming memory. `delete nullptr` is valid, so `counter_destroy(nullptr)` is a no-op. **A second call with an old non-null pointer is invalid**, because the object has already been deleted; the pointer still holding the old number does not indicate it is still live.

C ABI functions must not let C++ exceptions cross the JNI/FFM boundary. `counter_create/add/get` catch exceptions and report status. `CounterHandle` in this lesson only contains `std::mutex` and an integer, so its destructor does not throw; for complex classes, keep the destructor non-throwing (usually `noexcept`) and provide a separate cleanup API that reports errors if needed. Never let an unhandled C++ exception escape through a native C ABI call.

## 4. Java 17+ owner: an opaque jlong, AutoCloseable, and close-once

Create the file **`src/CounterJni.java`**:

~~~java
public final class CounterJni implements AutoCloseable {
    static {
        System.loadLibrary("counterbridge");
    }

    private long handle;

    private static native long nativeCreate(int initial);
    private static native int nativeAdd(long handle, int delta);
    private static native int nativeGet(long handle);
    private static native void nativeDestroy(long handle);

    public CounterJni(int initial) {
        this.handle = nativeCreate(initial);
        if (handle == 0L) {
            throw new IllegalStateException(
                    "nativeCreate returned null");
        }
    }

    private long openHandle() {
        if (handle == 0L) {
            throw new IllegalStateException("Counter closed");
        }
        return handle;
    }

    public synchronized int add(int delta) {
        return nativeAdd(openHandle(), delta);
    }

    public synchronized int get() {
        return nativeGet(openHandle());
    }

    @Override
    public synchronized void close() {
        if (handle != 0L) {
            long old = handle;
            handle = 0L;
            nativeDestroy(old);
        }
    }

    public static void main(String[] args) {
        try (CounterJni c = new CounterJni(10)) {
            System.out.println("added=" + c.add(7));
            System.out.println("value=" + c.get());

            try {
                c.add(-1);
                throw new AssertionError("negative delta accepted");
            } catch (IllegalArgumentException expected) {
                System.out.println("negative=IllegalArgumentException");
            }

            try {
                c.add(Integer.MAX_VALUE);
                throw new AssertionError("overflow accepted");
            } catch (ArithmeticException expected) {
                System.out.println("overflow=ArithmeticException");
            }

            if (c.get() != 17) {
                throw new AssertionError("value changed on error");
            }
        }

        CounterJni c = new CounterJni(1);
        c.close();
        c.close();

        try {
            c.get();
            throw new AssertionError("use after close accepted");
        } catch (IllegalStateException expected) {
            System.out.println("afterClose=IllegalStateException");
        }

        try {
            new CounterJni(-1);
            throw new AssertionError("negative initial accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalidCreate=IllegalArgumentException");
        }

        System.out.println("RESULT: PASS");
    }
}
~~~

**This pattern runs on Java 17+**, as JNI has existed for a long time. `System.loadLibrary("counterbridge")` requires the JVM to locate `libcounterbridge.so` on Linux, `libcounterbridge.dylib` on macOS, or `counterbridge.dll` on Windows.

### 4.1. Why `private long handle`?

A JNI `jlong` holds a 64-bit integer that the C++ adapter can use to round-trip a pointer bit pattern on supported platforms. It is **not** a JNI `jobject` (Java reference), is not a stable identifier across process restarts, and should not be exposed in public JSON/APIs for users to modify.

`openHandle()` throws an exception when the handle is already closed. `add/get/close` are all `synchronized`, meaning close cannot interleave with an add/get command **on this exact Java wrapper**. `close()` sets `handle` to 0 before calling the native destructor, ensuring a second close **does not repeat destroy**. This can be safely tested with `get()` after close — the wrapper will throw `IllegalStateException` **before the native call**.

**Limitation:** `synchronized` only locks the monitor of **one Java instance**. If you copy the raw pointer to another wrapper or C++ workers hold the pointer after the Java method returns, the two owners do not share this lock and can cause use-after-free. Production requires a single-ownership contract or a broader registry/refcount/gate.

### 4.2. Why use try-with-resources instead of a finalizer?

`try (CounterJni c = ...)` ensures `close` is called when exiting the block, even on a Java exception. Native resources need cleanup at a deterministic time; Java GC does not promise to run a finalizer/Cleaner right when needed. `finalize()` has been deprecated for removal. `Cleaner` can be considered as a **fallback** in specialized designs, but it does not replace explicit close and does not solve races with in-flight native calls.

## 5. JNI adapter: converting jlong to CounterHandle* and mapping errors

Create the file **`native/counter_jni.cpp`**:

~~~cpp
#include "CounterJni.h"
#include "counter_api.h"

#include <cstdint>

static_assert(sizeof(jlong) >= sizeof(void*),
              "jlong cannot store pointers");

static CounterHandle *fromHandle(jlong raw) {
    return reinterpret_cast<CounterHandle*>(
            static_cast<std::uintptr_t>(raw));
}

static jlong toHandle(CounterHandle *ptr) {
    return static_cast<jlong>(
            reinterpret_cast<std::uintptr_t>(ptr));
}

static void throwJava(JNIEnv *env,
                      const char *name,
                      const char *message) {
    jclass cls = env->FindClass(name);
    if (cls != nullptr) {
        env->ThrowNew(cls, message);
        env->DeleteLocalRef(cls);
    }
}

static bool checkStatus(JNIEnv *env, int32_t s) {
    if (s == COUNTER_OK) return true;

    switch (s) {
        case COUNTER_BAD_ARGUMENT:
            throwJava(env, "java/lang/IllegalArgumentException",
                      "bad counter argument");
            break;
        case COUNTER_OVERFLOW:
            throwJava(env, "java/lang/ArithmeticException",
                      "counter overflow");
            break;
        case COUNTER_NO_MEMORY:
            throwJava(env, "java/lang/OutOfMemoryError",
                      "native counter allocation");
            break;
        default:
            throwJava(env, "java/lang/IllegalStateException",
                      "native counter failure");
            break;
    }
    return false;
}

extern "C" JNIEXPORT jlong JNICALL Java_CounterJni_nativeCreate(
        JNIEnv *env, jclass, jint initial) {
    CounterHandle *ptr = nullptr;
    int32_t s = counter_create(
            static_cast<int32_t>(initial), &ptr);
    if (!checkStatus(env, s)) return 0L;
    return toHandle(ptr);
}

extern "C" JNIEXPORT jint JNICALL Java_CounterJni_nativeAdd(
        JNIEnv *env, jclass, jlong raw, jint delta) {
    int32_t output = 0;
    int32_t s = counter_add(
            fromHandle(raw), static_cast<int32_t>(delta), &output);
    if (!checkStatus(env, s)) return 0;
    return static_cast<jint>(output);
}

extern "C" JNIEXPORT jint JNICALL Java_CounterJni_nativeGet(
        JNIEnv *env, jclass, jlong raw) {
    int32_t output = 0;
    int32_t s = counter_get(fromHandle(raw), &output);
    if (!checkStatus(env, s)) return 0;
    return static_cast<jint>(output);
}

extern "C" JNIEXPORT void JNICALL Java_CounterJni_nativeDestroy(
        JNIEnv *, jclass, jlong raw) {
    counter_destroy(fromHandle(raw));
}
~~~

### 5.1. Details that must not be overlooked

- `CounterJni.h` must be **generated with `javac -h`** from `CounterJni.java`; do not guess the prototype. When changing the package/class/native method, regenerate the header and adjust the export names.
- `JNIEXPORT`/`JNICALL` are JNI macros; `extern "C"` ensures the exported JNI entry point name is not C++ mangled. `jclass` is the second parameter because the Java methods are `static native`; an instance native method would have `jobject` instead.
- `std::uintptr_t` is an integer large enough to hold a pointer when supported by the platform; `static_assert` checks that `jlong` is wide enough for a pointer. This is common practice on 32/64-bit systems, but it does not turn an arbitrary `long` into a valid pointer or a stable external ID. Avoid casting between integers/addresses without understanding the platform ABI.
- `checkStatus` converts the C status into a pending Java exception using `FindClass`/`ThrowNew`. When an exception occurs, the JNI function returns a dummy `0` to satisfy the native return type; Java sees the **exception**, not the dummy value. If `FindClass` fails, JNI may already have a pending exception; do not arbitrarily continue calling JNI functions.
- Never let C++ exceptions cross the `extern "C"`/JNI boundary. The C ABI library already catches errors in create/add/get. `counter_destroy` uses a non-throwing destructor in this example.
- The adapter **cannot verify** that `raw` is a live pointer. If a caller directly fakes a `jlong`, a non-null check in C++ is not enough protection. That is why the native methods are `private`, and the Java wrapper controls the usage scope.

## 6. Build/run JNI end-to-end on three platforms

The files:

~~~text
opaque-counter/
  src/CounterJni.java
  native/counter_api.h
  native/counter_api.cpp
  native/counter_jni.cpp
  out/                   <- javac generates .class
  native/CounterJni.h   <- javac -h generates JNI header
  libcounterbridge.so   <- Linux
  libcounterbridge.dylib<- macOS
  counterbridge.dll     <- Windows
~~~

There is only **one form** of binary output matching the OS being built. The JNI header `CounterJni.h` is a generated file, not hand-written source.

### 6.1. Linux + GCC/G++ C++17 + JDK 17+

Run from the project root, where the `src` and `native` directories are located:

~~~sh
mkdir -p out native
javac --release 17 -h native -d out src/CounterJni.java

export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"

g++ -std=c++17 -Wall -Wextra -Werror -pedantic \
  -O2 -fPIC -shared -DCOUNTER_BUILD \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -Inative \
  -o libcounterbridge.so \
  native/counter_api.cpp native/counter_jni.cpp

java -Xcheck:jni -Djava.library.path=. -cp out CounterJni
~~~

`-DCOUNTER_BUILD` enables the proper export macro in the header. `-Xcheck:jni` checks some JNI API usage errors, **it does not prove the native heap is free of use-after-free/double-free**. `JAVA_HOME` here finds the JDK containing `javac` on Linux; environments without `readlink -f` need to manually set the JDK root containing `include/jni.h`.

### 6.2. macOS + Clang C++17 + JDK 17+

~~~sh
mkdir -p out native
javac --release 17 -h native -d out src/CounterJni.java

export JAVA_HOME="$(/usr/libexec/java_home)"

c++ -std=c++17 -Wall -Wextra -Werror -pedantic \
  -fPIC -dynamiclib -DCOUNTER_BUILD \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
  -Inative \
  -o libcounterbridge.dylib \
  native/counter_api.cpp native/counter_jni.cpp

java -Xcheck:jni -Djava.library.path=. -cp out CounterJni
~~~

The native compiler/JDK must share the same architecture (arm64 or x86_64). If the macOS linker cannot find symbols, check the export table and JDK headers. This is an **instructional template not yet run in the Linux test session**, and does not claim every macOS machine produces the exact same output without building.

### 6.3. Windows + MSVC C++17 + JDK 17+

Open the **x64 Native Tools Command Prompt** matching the JVM architecture, set `JAVA_HOME` to the JDK. After creating the sources and the `native` directory:

~~~bat
mkdir out
javac --release 17 -h native -d out src\CounterJni.java

cl /nologo /std:c++17 /EHsc /W4 /LD /DCOUNTER_BUILD ^
  /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" /Inative ^
  native\counter_api.cpp native\counter_jni.cpp ^
  /link /OUT:counterbridge.dll

java -Xcheck:jni -Djava.library.path=. -cp out CounterJni
~~~

If `out` already exists, omit `mkdir out`. `/LD` builds a DLL; `counterbridge.dll` must be locatable by the JVM loader via `java.library.path`/OS dependencies. In the test session, the Windows environment had JDK 24 but **no C++ compiler `cl`/`g++` in PATH**, so these commands **have not been executed**. The main practice was run on Linux.

### 6.4. Observed valid JNI stdout

~~~text
added=17
value=17
negative=IllegalArgumentException
overflow=ArithmeticException
afterClose=IllegalStateException
invalidCreate=IllegalArgumentException
RESULT: PASS
~~~

**Test details:** Linux JDK 21, `javac --release 17 -h` generated the header; GCC 14.2 C++17 with `-Wall -Wextra -Werror -pedantic` compiled the shared object; `java -Xcheck:jni` produced **exactly seven lines**. Exports `Java_CounterJni_nativeCreate/nativeAdd/nativeGet/nativeDestroy` and `counter_create/add/get/destroy` were verified with `nm -D --defined-only`.

### 6.5. Reading the output lines as a lifecycle test

1. The constructor uses `nativeCreate(10)`, C++ creates a `CounterHandle`.
2. `add(7)` returns 17 and `get()` also returns 17: the handle points to **the same object**.
3. `add(-1)` is rejected with status `COUNTER_BAD_ARGUMENT`, JNI converts it to `IllegalArgumentException`.
4. `add(Integer.MAX_VALUE)` has overflow prevented before addition, JNI converts it to `ArithmeticException`. Counter remains 17, verified by assertion `get()==17`.
5. When `try-with-resources` exits, the wrapper calls `close()` and destroys the object.
6. The second owner is closed **twice**; only the first call invokes native destroy.
7. `get()` after close throws `IllegalStateException` at the **Java-side openHandle check**, before any native pointer dereference.
8. `new CounterJni(-1)` causes create to fail; JNI throws `IllegalArgumentException` and returns no object.
9. `RESULT: PASS` confirms the conditions of this test, **it does not mean every ABI or all C++ code is guaranteed memory-safe**.

## 7. C client proving that the wrapper actually uses a C ABI

The C API above is not just JNI glue. A C program can include the public header without **seeing or compiling the C++ class definition**. Create **`native/client.c`**:

~~~c
#include "counter_api.h"
#include <stdio.h>

int main(void) {
    CounterHandle *h = NULL;
    int32_t current = -1;

    if (counter_create(10, &h) != COUNTER_OK || h == NULL)
        return 1;

    if (counter_add(h, 7, &current) != COUNTER_OK || current != 17)
        return 2;

    if (counter_get(h, &current) != COUNTER_OK || current != 17)
        return 3;

    if (counter_add(h, -1, &current) != COUNTER_BAD_ARGUMENT)
        return 4;

    printf("cValue=%d\n", (int) current);

    counter_destroy(h);
    h = NULL;
    counter_destroy(h); /* NULL no-op, DO NOT reuse old pointer. */

    puts("C_ABI_RESULT: PASS");
    return 0;
}
~~~

Linux, after building `libcounterbridge.so`:

~~~sh
gcc -std=c11 -Wall -Wextra -Werror -pedantic \
  -Inative native/client.c -L. -lcounterbridge \
  -Wl,-rpath,'$ORIGIN' -o client

./client
~~~

Tested stdout:

~~~text
cValue=17
C_ABI_RESULT: PASS
~~~

The key point: the C source only contains `CounterHandle*`, knows no fields, yet creates/reads/modifies/destroys the object. This is proof that **the C ABI is more stable than C++ internals**, requiring neither JNI nor a JDK on the C client. `-Wl,-rpath,'$ORIGIN'` helps the Linux loader find the shared library in the same directory as the executable in many configurations; production must follow OS loader/dependency policies.

## 8. Native concurrency: mutex helps, but join is needed before destroy

To test that the value remains accurate when multiple native threads call add, create **`native/concurrent.cpp`**:

~~~cpp
#include "counter_api.h"
#include <iostream>
#include <thread>
#include <vector>

int main() {
    CounterHandle *h = nullptr;
    if (counter_create(0, &h) != COUNTER_OK) return 1;

    std::vector<std::thread> threads;
    for (int i = 0; i < 4; ++i) {
        threads.emplace_back([h] {
            for (int j = 0; j < 1000; ++j) {
                int32_t next = -1;
                if (counter_add(h, 1, &next) != COUNTER_OK)
                    std::terminate();
            }
        });
    }

    for (auto &thread : threads) thread.join();

    int32_t total = -1;
    if (counter_get(h, &total) != COUNTER_OK) return 2;

    std::cout << "parallelValue=" << total << '\n';
    counter_destroy(h);

    if (total != 4000) return 3;
    std::cout << "CONCURRENT_RESULT: PASS\n";
}
~~~

Linux:

~~~sh
g++ -std=c++17 -Wall -Wextra -Werror -pedantic -pthread \
  -Inative native/concurrent.cpp -L. -lcounterbridge \
  -Wl,-rpath,'$ORIGIN' -o concurrent

./concurrent
~~~

Run result:

~~~text
parallelValue=4000
CONCURRENT_RESULT: PASS
~~~

Four threads × 1,000 increments = 4,000. The internal mutex prevents lost updates. However, **main only calls `counter_destroy(h)` after joining all four threads**. If destroy is called while workers are still using the pointer, the mutex inside the object is also destroyed — that is a race that cannot be fixed by that same mutex.

### Boundary of Java synchronized

Similarly, Java `synchronized` on `CounterJni.add/get/close` ensures lifecycle safety **within one Java instance**. If a native callback uses the handle asynchronously, C++ code holds the handle in a worker thread, or two wrappers share a copied pointer, locking one Java object does not prevent all in-flight uses. Service design requires a shared owner/gate.

## 9. FFM JDK 22+ path: an opaque handle is still just an ADDRESS

Opaque handles do not depend on JNI. Using the **Foreign Function & Memory API (FFM)** from JDK 22+, Java can directly call the **C ABI wrapper** above via `SymbolLookup.libraryLookup` and `Linker.downcallHandle`. There is no need to know the private struct layout; `ValueLayout.ADDRESS` represents the pointer.

Two kinds of memory must be distinguished:
- **The `Arena` of `libraryLookup`** keeps the FFM library/symbol code alive for the appropriate lifetime.
- **The `Arena` of each call** only allocates output slots: `CounterHandle **out` or `int32_t *out`.
- **The C++ object** is allocated by `counter_create` using C++ `new`, **not** inside callArena; Java must call `counter_destroy`.
- If reading a pointer from `ValueLayout.ADDRESS`, it typically has a zero-length segment view; do not treat the C++ object as a `MemorySegment` with a public layout. Keep the pointer as an **opaque token**, only passing it back to C ABI functions.

### 9.1. Complete FFM program: `CounterFfm.java`

The source below **has been compiled on Windows x64 JDK 24.0.2 with `javac --release 22`**, but because the Windows machine lacks a matching native C++ compiler/DLL, **`CounterFfm` has not been runtime-tested**. Once a library for the right OS/architecture is available, run according to the next section.

~~~java
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class CounterFfm {
    private static MethodHandle bind(Linker linker, SymbolLookup lib,
                                     String name, FunctionDescriptor signature) {
        MemorySegment address = lib.find(name)
                .orElseThrow(() -> new IllegalStateException(
                        "symbol missing: " + name));
        return linker.downcallHandle(address, signature);
    }

    private static void requireOK(int status) {
        if (status != 0) {
            throw new IllegalStateException("native status=" + status);
        }
    }

    public static void main(String[] args) throws Throwable {
        Path binary = Path.of(
                System.mapLibraryName("counterbridge")).toAbsolutePath();

        try (Arena libraryArena = Arena.ofConfined()) {
            Linker linker = Linker.nativeLinker();
            SymbolLookup lib =
                    SymbolLookup.libraryLookup(binary, libraryArena);

            MethodHandle create = bind(linker, lib, "counter_create",
                    FunctionDescriptor.of(ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT, ValueLayout.ADDRESS));

            MethodHandle add = bind(linker, lib, "counter_add",
                    FunctionDescriptor.of(ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS, ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS));

            MethodHandle get = bind(linker, lib, "counter_get",
                    FunctionDescriptor.of(ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS, ValueLayout.ADDRESS));

            MethodHandle destroy = bind(linker, lib, "counter_destroy",
                    FunctionDescriptor.ofVoid(ValueLayout.ADDRESS));

            MemorySegment opaque;
            try (Arena callArena = Arena.ofConfined()) {
                MemorySegment slot = callArena.allocate(
                        ValueLayout.ADDRESS);
                requireOK((int) create.invokeExact(10, slot));

                opaque = slot.get(ValueLayout.ADDRESS, 0L);
                if (opaque.address() == 0) {
                    throw new IllegalStateException(
                            "native create returned null");
                }
            }

            try {
                try (Arena callArena = Arena.ofConfined()) {
                    MemorySegment output =
                            callArena.allocate(ValueLayout.JAVA_INT);

                    requireOK((int) add.invokeExact(opaque, 7, output));
                    System.out.println("ffiAdded="
                            + output.get(ValueLayout.JAVA_INT, 0L));

                    requireOK((int) get.invokeExact(opaque, output));
                    System.out.println("ffiValue="
                            + output.get(ValueLayout.JAVA_INT, 0L));
                }
            } finally {
                destroy.invokeExact(opaque);
            }

            System.out.println("FFM_RESULT: PASS");
        }
    }
}
~~~

### 9.2. Commands and expected output

Place `CounterFfm.java` and the corresponding native library in the working directory; build and run with JDK 22+:

~~~sh
mkdir -p out
javac --release 22 -d out CounterFfm.java
java --enable-native-access=ALL-UNNAMED \
  -cp out CounterFfm
~~~

**Expected output** on a platform with the proper binary/exports:

~~~text
ffiAdded=17
ffiValue=17
FFM_RESULT: PASS
~~~

**Only compile QA was performed for the FFM source in this session**; the three lines above are expected results based on the tested native API, **not observed FFM stdout**. `--enable-native-access=ALL-UNNAMED` permits restricted FFM operations on the classpath. If using a named Java module, grant access to the appropriate module.

### 9.3. Do not confuse Arena with C++ object ownership

~~~text
Library Arena OPEN
  |
  +-- SymbolLookup + MethodHandles
  |
  +-- Call Arena #1: allocate ADDRESS slot -> counter_create(10, &slot)
  |      |
  |      +-- read pointer h, then close call arena
  |
  +-- C++ object h is STILL ALIVE (allocated by new, not call arena)
  |
  +-- Call Arena #2: allocate INT output -> counter_add/get
  |      |
  |      +-- close output arena
  |
  +-- counter_destroy(h)  [must happen before unload]
  |
Library Arena CLOSE (function addresses must not be used)
~~~

An FFM `MemorySegment` pointer only represents an address. Even if the Java object holding the pointer still exists, the C++ resource becomes invalid immediately after `counter_destroy`. Conversely, `callArena.close()` **does not** delete the C++ object allocated by the native library. In production, wrap the pointer in a Java `AutoCloseable` owner, reset the handle to `MemorySegment.NULL` after destroy, and block concurrent uses.

## 10. JNI vs FFM: different bridges, same lifetime contract

| Aspect | JNI (Java 17+) | FFM (JDK 22+) |
|---|---|---|
| Java holds native handle | `private long handle` | `MemorySegment` address |
| What does C++ receive? | `CounterHandle*` after JNI adapter converts `jlong` | C ABI `CounterHandle*` via `ValueLayout.ADDRESS` |
| Mechanism to call C functions | JNI `Java_CounterJni_native*` adapter | `SymbolLookup` + `FunctionDescriptor` + `Linker` |
| Protecting the Java object | `AutoCloseable`, `synchronized` | Java owner + close gate/`AutoCloseable` |
| Protecting C++ data | C++ `std::mutex` | Still the same C++ `std::mutex` |
| Who destroys the object? | `counter_destroy` in C++ lib | Still `counter_destroy` |
| C++ class directly over ABI? | No | No |
| Runtime requirements | JNI native library + JDK | FFM finalized JDK 22+, native access + library |
| When C++ creates pointer for out arg | JNI adapter holds `CounterHandle **` | FFM call arena holds ADDRESS slot |

Use JNI when the project must support Java 17/older JDKs, needs deep JNI APIs with Java objects, or already has an adapter. FFM is convenient on JDK 22+ when you want to bind C ABI functions without writing an extra JNI adapter. **Neither bridge allows Java to bypass ownership or safely dereference a private C++ class layout.**

## 11. Ownership and threading for production

### 11.1. One owner, multiple borrows

If a native resource must live across multiple Java calls, have **one owner** created at creation and destroyed at close. Each method call only *borrows* the handle while the owner is OPEN. A borrower must not call `counter_destroy`. When close is requested, the owner rejects new borrows, waits for all active borrows to finish, and then destroys. This resembles a resource lease more than “a pointer passed around freely”.

~~~text
OPEN
  accept borrows -> activeCount++
  native operation
  release borrow -> activeCount--

request close:
  mark CLOSING
  reject new borrows
  wait activeCount == 0
  unregister callbacks / stop native workers
  counter_destroy(handle) exactly once
  mark CLOSED

CLOSED:
  no future native calls using old handle
~~~

`synchronized` in `CounterJni` is a simplified version for **one Java owner and synchronous calls**. When there are multiple owners, aliases, C++ async workers, or callbacks, proper native registries/locks/refcounts are needed instead of pretending all methods go through a single Java monitor.

### 11.2. Why is a native mutex not enough?

The mutex is a **member of the C++ object**. `counter_add` locks it to modify `value`. However, `counter_destroy` frees both the object and the mutex. If thread A is about to `lock(h->mu)` while thread B deletes `h`, thread A may dereference freed memory. Allow destroy only after all native operations have stopped/joined, or use a lifecycle gate **external to the object being destroyed** for protection.

### 11.3. When to use a handle registry instead of a raw pointer?

If the handle can be forged by untrusted input, copied into multiple Java objects, or reused long-term, a raw pointer has no validation. A **registry** can issue tokens consisting of **slot index + generation ID**:

~~~text
token = (slotIndex, generation)
          |
registry.lookup(token)
          |
validate slot occupied and generation matches
          |
acquire active-use lease
          |
operate C++ CounterHandle
          |
release lease

destroy(token) -> mark closing -> reject new leases
               -> wait current leases -> delete C++ object
               -> increment generation, recycle slot
~~~

The generation helps reject stale tokens even when the allocator reuses an old address (ABA problem). However, the registry itself must be synchronized, ensure the generation does not wrap within the threat model, and require explicit cleanup. **Simply turning a raw pointer into an integer does not make everything safe.**

### 11.4. Native callbacks and complex destructors

If an object's destructor stops workers, joins threads, or invokes a Java callback, avoid holding a Java monitor/write lock across a native function that might reenter Java and need that same lock; it easily **deadlocks**. The general pattern is to transition to CLOSING, block new calls, release necessary locks, stop/unregister callbacks, wait for in-flight work, and then destroy when quiescent. The simple Counter example has no callbacks, so synchronous close is acceptable within the demo scope.

### 11.5. Should Cleaner be used for automatic cleanup?

`Cleaner` can act as a safety net if code forgets to close, but it provides no deadline and can be problematic if the cleaner runs while the resource is still in native use. `finalize` is deprecated for removal. For native memory with clear ownership, default to `AutoCloseable`/try-with-resources; if adding a Cleaner, it must integrate with the state machine/close-once and ensure no strong reference prevents the object from reaching GC.

## 12. Common errors and how to diagnose them

| Symptom | Root cause | Resolution |
|---|---|---|
| JVM reports `UnsatisfiedLinkError` when loading JNI | Missing `libcounterbridge.so`/DLL, wrong `java.library.path`, incorrect JNI exports | Check binary location, dependencies, bitness, `javac -h`, and `nm/dumpbin` |
| C ABI exported symbol name is mangled | Forgot `extern "C"` | Check `nm -D --defined-only`, rebuild with C linkage |
| `new CounterJni(-1)` throws exception | `counter_create` returned `COUNTER_BAD_ARGUMENT` | Expected behavior; do not use handle when create fails |
| Java `IllegalArgumentException` on add(-1) | Invalid delta mapped by C ABI status | Validate input and keep state unchanged |
| Java `ArithmeticException` when adding too much | Native check prevented signed overflow | Check before arithmetic, do not rely on undefined behavior |
| `IllegalStateException` after close | Java wrapper blocked use-after-close | Matches contract; create a new owner to continue using |
| Double-free, heap corruption | Two `counter_destroy(h)` calls with same non-null h | Single owner, close-once wrapper, do not expose handle |
| Use-after-free | Dereferencing h after destroy, h is still non-null | Gate and reset token; do not rely on C++ null check |
| Memory leak | Forgot close, partial create failure, unowned copies | try-with-resources, rollback/cleanup, leak tests |
| `free` used to destroy memory created by C++ `new` | Allocator/destructor mismatch | Call the library's `counter_destroy` |
| Deadlock on shutdown | Destructor callback waits for lock held by Java close | Lifecycle state, quiesce callbacks, design lock order |
| Native status ignored | Caller uses out pointer/output when function returns error | Always check status before using out |
| C++ exception crosses boundary | C++ errors not caught | Catch at C ABI, map status, non-throwing destructor |
| JNI `jlong` faked as pointer | No validation before deref | Private owner or registry/generation IDs |
| FFM `WrongMethodTypeException` | Wrong MethodHandle carrier/arity | Compare `FunctionDescriptor` and `MethodHandle.type()` |
| `Arena.close()` yet C++ object still alive | C++ `new` is not an arena allocation | Call `counter_destroy` separately, before library unload |
| Multi-thread test passes but shutdown crashes | Mutex protects value, not destroy lifecycle | Join/leases/gate to protect resource lifetime |
| Java native function returns 0 on error | JNI has pending exception or code didn't map status | Fix JNI error mapping; do not use dummy value if exception |
| Windows DLL build linker error | Wrong `/LD`, compiler/arch, or unresolved JNI/C++ runtime deps | MSVC Developer Prompt and export/dependency checks |

**Distinguishing errors:**
- **Java-side predictable**: `IllegalStateException` after close is a handled state error.
- **Native status**: argument/overflow/oom are C API errors with codes that can be mapped to Java exceptions.
- **Native memory corruption**: stale pointer, double delete, pointer race can crash the JVM **without** a safe Java exception. Do not use `try/catch(Throwable)` as a mechanism to rescue the JVM from C++ heap errors.

## 13. Testing and observability by layer

**Native C ABI:** use `gcc` to compile a C client that only knows the header; `nm -D --defined-only libcounterbridge.so`/`dumpbin /EXPORTS` verifies names; run direct C++ tests to check new/use/delete. The header must parse under a **C compiler**, not just g++.

**JNI:** use `javac --release 17 -h` to generate the header, build the JNI adapter with the right JDK include dirs, run `java -Xcheck:jni`; test create/get/add, negative/overflow, close twice, get after close. `-Xcheck:jni` helps detect some JNI API misuses, **it does not** mean all C++ memory bugs are eliminated.

**Concurrency:** N threads use a live handle, wait for join, then destroy; ThreadSanitizer/ASan/native heap profilers can be used in test environments. Do not write a normal test that intentionally dereferences a freed pointer just to see if it crashes.

**FFM:** compile with Java 22+; once a native binary of the right architecture is available, enable `--enable-native-access=ALL-UNNAMED` if code is on the classpath, verify exported C symbols, int32_t↔JAVA_INT and pointer↔ADDRESS mappings. Ensure callArena is not closed before C finishes using output slots, and libraryArena is not closed before `counter_destroy`. Do not force Java to create a `MemoryLayout` for an opaque C++ class.

### Debugging workflow when native code crashes

1. Log the owner's lifecycle state before each create/add/get/destroy; do not log raw pointers to untrusted places.
2. Check whether `counter_destroy` is called once and whether there are outstanding C++ threads/callbacks.
3. Verify C ABI symbols and signatures. `javac -h` helps compare JNI exports; FFM `FunctionDescriptor` must match the C header.
4. Run the C client to isolate the C++ implementation from the JVM bridge.
5. Run sanitizers/native debuggers: Linux `gdb`/`ldd`/`nm`, macOS `lldb`/`otool`, Windows debugger/`dumpbin`.
6. Under multi-threaded load, look at gates/leases and destructors, not just the mutex inside the C++ object.
7. Do not attempt to keep running the JVM after severe native memory corruption; prioritize fixing the root cause.

## 14. Self-check questions and answers

**1. What is an opaque handle?**  
A pointer/token to a native resource whose type is **not internally defined in the public header**. Callers may only pass it back to public C API functions; fields cannot be accessed.

**2. Does `extern "C"` make a C++ class portable between MSVC and GCC?**  
No. It gives exposed functions C linkage. C++ class layout, exception ABI, and allocator remain private and do not cross the boundary directly.

**3. Why does create need `CounterHandle **out`?**  
Because the function must write the new pointer into **the caller's handle variable**, so a pointer-to-pointer is required.

**4. Why is status separated from result?**  
Because 0 or negative numbers can be valid data; returning `int32_t status` and writing the result via an output pointer avoids confusing values with errors.

**5. After destroy, does `h!=NULL` prove h is still alive?**  
No. `delete` does not set variables/aliases to NULL; a pointer can be non-null yet dangling.

**6. Can `counter_destroy(h)` be replaced with `free(h)`?**  
No; the object was allocated with C++ `new` and has a destructor. Always use the destroy function exported by the library.

**7. Does closing the Java wrapper twice cause a double-free?**  
Not in this example: `close` is `synchronized`, the first call sets `handle=0`; the second is a no-op. However, calling raw `counter_destroy` twice with the same non-null pointer is still wrong.

**8. Is a mutex inside the object enough to destroy concurrently with add?**  
No. The destructor destroys the mutex/object itself. A lifecycle gate or ensuring all users join/release before delete is required.

**9. Does closing an FFM Arena automatically delete CounterHandle?**  
No. The Arena only owns memory it allocates and the scope of linked libraries/symbols, and has no knowledge of C++ `new` inside `counter_create`. `counter_destroy` must be called explicitly.

**10. When should a registry be used instead of a raw pointer?**  
When tokens may come from untrusted callers, be aliased across multiple owners, or need stale-handle rejection. Registry + generation + lease helps prevent many bugs, but must itself be synchronized.

**11. Can a C++ exception propagate automatically through JNI to Java?**  
Do not rely on that. C ABI/JNI wrappers must catch C++ exceptions and map them to error codes/Java exceptions, never letting a C++ exception escape the boundary.

**12. Which JDK is required for FFM according to the code in this lesson?**  
The code uses finalized `java.lang.foreign` from JDK **22**; the JNI example runs on JDK 17+. The FFM source compiled on JDK 24 with `--release 22` but has not been runtime-tested on a Windows native DLL.

## 15. Checklist before using in a real project

- [ ] Public header exposes only the `CounterHandle*` incomplete type and C-compatible API, without exposing C++ STL/classes.
- [ ] Functions are exported with `extern "C"` and proper visibility, verified in the symbol table on each OS.
- [ ] ABI uses fixed-width types, clear return status, pointer out parameters, and ownership.
- [ ] `counter_create` sets out=null on failure, catches exceptions, and does not leak objects.
- [ ] `counter_add/get` check null/arguments/overflow; native state is protected when multiple valid threads use it concurrently.
- [ ] `counter_destroy` is called by the right native library exactly once, after all borrows; no mismatched-allocator `free` is used.
- [ ] Java JNI owner uses `private long`, `AutoCloseable`, `synchronized` or a lifecycle gate, and close-once.
- [ ] JNI header is generated by `javac -h` from Java native declarations; matching class/package, generated prototypes, JNI include paths.
- [ ] JNI error mapping has `ThrowNew` for invalid arguments/overflow/OOM; no C++ exception crosses the C boundary.
- [ ] FFM Java only uses `ValueLayout.ADDRESS` for the opaque pointer, without reading private object layout; proper JDK 22+ native-access flags.
- [ ] FFM library arena and call arena separate lifetimes; C++ object is destroyed before library unload.
- [ ] Do not expose raw pointers/`jlong` to untrusted code; if a public token is needed, consider a generation registry.
- [ ] Do not destroy while C++ threads, callbacks, or JNI/FFM calls are still in-flight; lock order avoids deadlock.
- [ ] Tests exist for native C ABI, JNI status, close twice/after-close, concurrency, and leak checks.
- [ ] Compile on the target OS/arch/compiler ABI, run `nm`/`dumpbin`, and check native dependencies.
- [ ] Do not treat `-Xcheck:jni`, Java `synchronized`, or GC as proof that native memory is completely safe.

## 16. Summary and references

~~~text
Opaque handle = permission to borrow/own a C++ resource, NOT a Java object.
C header      = create / use / destroy C ABI contract, hiding C++ layout.
C++ source    = new, methods, mutex, delete, and exception catching.
Java wrapper  = AutoCloseable, private handle, close-once, and reject after-close.
JNI           = jlong handle + JNI exported methods.
FFM JDK22+    = ADDRESS handle + Linker downcalls.
~~~

**When well-designed**, Java does not need to know how many bytes the C++ object allocates or what virtual methods it has. **When poorly designed**, an opaque pointer merely hides double-delete and use-after-free until the JVM crashes. Therefore, every binding needs a clear contract: **create succeeds → use within valid scope → block new borrows → wait for calls to finish → destroy exactly once**.

References:
- [Oracle Java SE 21 — Java Native Interface Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/index.html)
- [Oracle Java SE 21 — JNI Design Overview](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html)
- [Oracle Java SE 21 — JNI Functions](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html)
- [OpenJDK JEP 454 — Foreign Function & Memory API finalized in JDK 22](https://openjdk.org/jeps/454)
- [Oracle Java SE 22 — java.lang.foreign package](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html)
- [Oracle Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html)
- [Oracle Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- [Oracle Java SE 22 — SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html)

QA limitation: JNI/native C ABI was **built and run** on Linux, JDK 21/GCC 14; the FFM alternative was **compiled** on Windows JDK 24 with `--release 22` but **not run** with a Windows DLL. When deploying to production, recompile and re-run on the project's target OS/architecture/ABI; do not assume a single PASS proves all toolchain variants are safe.