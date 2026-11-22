# Exporting a Stable C API Layer with extern "C" Around a C++ Library

## 1. Goal and Real-World Problem

A C++ library can use classes, constructors, destructors, templates, `std::string`, `std::vector`, namespaces, overloads, and exceptions. These capabilities are convenient inside C++, but they are not a simple binary contract for C programs, Java/JNI, Rust FFI, Python ctypes, or Java FFM.

For other languages to use the library, we typically build a **C ABI façade**: a layer exported with `extern "C"`, having a header valid for a C compiler, and exposing only functions, opaque pointers, explicitly sized primitives, error codes, and ownership rules. C++ classes and STL are still used **behind the façade**, not crossing the ABI.

After this lesson, you will know:

- How `extern "C"` solves name mangling/language linkage, and does **not** automatically guarantee binary portability across OSes, ABIs, or compilers.
- How to create `counter_api.h` usable from C11 and C++17, with `#ifdef __cplusplus` and symbol-export macros.
- How to hide C++ object layout using `typedef struct counter_handle counter_handle;`.
- How to define `create/get/add/destroy`, matching allocators, borrowed/owned pointers, error handling, and versioning.
- How to catch C++ exceptions at the C boundary and convert them to status; in Java JNI, convert status into a Java exception.
- How to build **one shared library** containing the public C ABI and JNI adapter, calling the same C++ core from a **C client** and a **Java 17 client**.
- How to analyze double-free, use-after-free, class layout, ABI mismatch, thread race, DLL import/export, FFM/JDK 22+, and version compatibility errors.

> **Requirements to run the sample:** Java 17+, C++17, C11, a native compiler suitable for Linux/macOS/Windows, and a JDK with JNI headers. This is a Java 17 + JNI example, **not** using the unstable FFM API in Java 17. From JDK 22, the JNI adapter can be replaced with FFM downcalls to the same C ABI.

## 2. Why Not Export C++ Classes Directly?

An internal class might look like:

~~~cpp
#include <string>

namespace engine {
class Counter {
public:
    explicit Counter(int start);
    int add(int amount);
    int value() const;
    std::string describe() const;
};
}
~~~

This is an **illustrative declaration**, without executable implementation code. A C compiler does not understand constructors, namespaces, or `std::string`. JNI cannot know how to call a C++ non-static member function like a regular C function pointer.

Difficulties at the binary boundary:

| C++ Feature | Risk When Exposed Directly |
|---|---|
| Name mangling | Symbol names depend on compiler/ABI and overloads |
| Class layout/vtable | Size, alignment, inheritance, and field offsets can change |
| STL types | `std::string`/`std::vector` depend on the C++ standard library ABI/allocator |
| Exceptions | No portable protocol for a C caller to receive a C++ exception |
| new/delete | Must not be arbitrarily swapped with malloc/free or another CRT |
| Templates/overloads | Cannot be treated as a fixed set of C symbols |
| C++ references | Not a transparent C ABI contract |
| `long`, `size_t`, calling convention | Bit width and parameter passing depend on target |
| ABI evolution | Changing signatures/layouts can break already-built clients |

The **C ABI façade** hides these details: it only makes public primitive types, pointers, and C functions with a fixed contract. The implementation can continue to use C++ features freely.

## 3. extern "C": What It Does and Does Not Do

~~~cpp
extern "C" int counter_api_version(void);
~~~

In C++, `extern "C"` specifies **C language linkage** for the corresponding function name/type. On common toolchains, the exported symbol will bear a C name such as `counter_api_version` instead of a C++ name-mangled symbol.

It does **not**:

1. Convert `std::string` into a C string.
2. Hide class layout or make a C compiler understand templates.
3. Fix the calling convention for every CPU/OS.
4. Automatically export function names from a Windows DLL.
5. Catch C++ exceptions.
6. Manage the native heap or protect freed pointers.
7. Guarantee a Linux x86-64 DLL can run on Windows ARM64.
8. Preserve compatibility if `int32_t` is changed to `int64_t` on the same exported symbol.

Because `extern "C"` is **C++** syntax, a public header uses a guard:

~~~c
#ifdef __cplusplus
extern "C" {
#endif

/* C-compatible functions here. */

#ifdef __cplusplus
}
#endif
~~~

A C11 compiler skips the language linkage section, while a C++ compiler applies it. This is how a single header can be included from both a C client and a C++ implementation.

## 4. Designing a Public C API for a C++ Counter

Suppose the counter object has its state owned by the C++ library. A small API:

| Function | Meaning | Ownership |
|---|---|---|
| `counter_api_version()` | Returns major ABI version | No resource |
| `counter_create(start, &handle)` | Creates counter; separate status | Transfers **owned handle** to caller on success |
| `counter_get(handle, &out)` | Reads value | Borrowed handle during the call |
| `counter_add(handle, delta, &out)` | Adds and retrieves new value | Borrowed handle |
| `counter_destroy(handle)` | Destroys counter | Consumes owned handle |
| `counter_status_message(code)` | Describes status | Borrowed static string, caller does not free |

**Core contract:**

- The public header only has `counter_handle*`, with no constructors, STL, or C++ exceptions.
- `create` and `destroy` are a pair implemented by **the same library**.
- The function return is an `int32_t` status, and output data goes through a pointer; a result value of 0 is not confused with status 0.
- Status codes must have consistent meaning across minor versions.
- An opaque pointer is not a security token. A forged/stale pointer is still dangerous if the API dereferences it directly.

### Why use int32_t instead of long?

`int32_t` from `<stdint.h>` is exactly 32 bits when present. C `long` can be 64 bits on many Unix x64 systems but 32 bits on Windows x64. Java `long` is 64 bits while JNI `jint` corresponds to Java's 32-bit `int`. For parameters that must have a fixed width, use fixed-width types and verify the ABI rather than guessing.

## 5. Complete File: counter_api.h

~~~c
#ifndef COUNTER_API_H
#define COUNTER_API_H

#include <stdint.h>

/* Symbol visibility: export in library, import in Windows client. */
#if defined(_WIN32)
    #if defined(COUNTER_BUILD_SHARED)
        #define COUNTER_API __declspec(dllexport)
    #else
        #define COUNTER_API __declspec(dllimport)
    #endif
#elif defined(__GNUC__) || defined(__clang__)
    #define COUNTER_API __attribute__((visibility("default")))
#else
    #define COUNTER_API
#endif

#define COUNTER_ABI_VERSION 1u

#define COUNTER_OK            0
#define COUNTER_BAD_ARGUMENT  1
#define COUNTER_NO_MEMORY     2
#define COUNTER_OVERFLOW      3
#define COUNTER_INTERNAL      4

#ifdef __cplusplus
extern "C" {
#endif

/* Incomplete type: client does not know layout. */
typedef struct counter_handle counter_handle;

/* Success: *out is an owned pointer, must be destroyed exactly once. */
COUNTER_API int32_t counter_create(
        int32_t initial, counter_handle **out);

/* Borrowed pointer, does not transfer ownership. */
COUNTER_API int32_t counter_get(
        const counter_handle *handle, int32_t *out_value);

COUNTER_API int32_t counter_add(
        counter_handle *handle, int32_t delta,
        int32_t *out_value);

/* Consumer release; must use the library's matching function. */
COUNTER_API void counter_destroy(counter_handle *handle);

/* Do not free returned pointer: points to a static string literal. */
COUNTER_API const char *counter_status_message(
        int32_t status);

COUNTER_API uint32_t counter_api_version(void);

#ifdef __cplusplus
}
#endif

#endif /* COUNTER_API_H */
~~~

**Explanation of decisions:**

- `#ifdef __cplusplus` keeps the header valid in C11.
- `COUNTER_API` controls export/import: on Windows it uses `__declspec(dllexport)` when building the DLL and `dllimport` in the client; on GCC/Clang it uses visibility.
- `COUNTER_ABI_VERSION` is the major version of the contract, not the C++ class version.
- Status macros use small integers, and exported functions explicitly return `int32_t`.
- `typedef struct counter_handle counter_handle;` is an opaque handle. C clients must not do `sizeof(counter_handle)` or access fields.
- `counter_create` returns ownership via `counter_handle **out`. On error, the implementation attempts to leave `*out=NULL`.
- `counter_get/add` take a borrowed handle and do not retain the pointer after returning.
- `counter_destroy` takes a valid owner; calling it repeatedly with the same non-null pointer is a serious bug.
- `counter_status_message` returns a borrowed literal. Do not `free` in the caller.
- There is no `JNIEnv*`, `jstring`, or `std::string` in the public API: a standalone C client does not need Java or C++ headers.

## 6. C++ Implementation File: counter_api.cpp

~~~cpp
#include "counter_api.h"

#include <cstdint>
#include <limits>
#include <new>

/* Private C++ layout, not in public header. */
struct counter_handle {
    std::int32_t value;

    explicit counter_handle(std::int32_t start) noexcept
        : value(start) {}
};

extern "C" {

COUNTER_API int32_t counter_create(
        int32_t initial, counter_handle **out) {

    if (out == nullptr) {
        return COUNTER_BAD_ARGUMENT;
    }
    *out = nullptr;

    try {
        *out = new counter_handle(initial);
        return COUNTER_OK;
    } catch (const std::bad_alloc &) {
        return COUNTER_NO_MEMORY;
    } catch (...) {
        return COUNTER_INTERNAL;
    }
}

COUNTER_API int32_t counter_get(
        const counter_handle *handle, int32_t *out_value) {

    if (handle == nullptr || out_value == nullptr) {
        return COUNTER_BAD_ARGUMENT;
    }

    try {
        *out_value = handle->value;
        return COUNTER_OK;
    } catch (...) {
        return COUNTER_INTERNAL;
    }
}

COUNTER_API int32_t counter_add(
        counter_handle *handle, int32_t delta,
        int32_t *out_value) {

    if (handle == nullptr || out_value == nullptr) {
        return COUNTER_BAD_ARGUMENT;
    }

    try {
        const std::int64_t wide =
                static_cast<std::int64_t>(handle->value)
                + static_cast<std::int64_t>(delta);

        if (wide < std::numeric_limits<std::int32_t>::min()
                || wide > std::numeric_limits<std::int32_t>::max()) {
            return COUNTER_OVERFLOW;
        }

        handle->value = static_cast<std::int32_t>(wide);
        *out_value = handle->value;
        return COUNTER_OK;
    } catch (...) {
        return COUNTER_INTERNAL;
    }
}

COUNTER_API void counter_destroy(counter_handle *handle) {
    /* Trivial destructor does not throw, delete nullptr is valid. */
    delete handle;
}

COUNTER_API const char *counter_status_message(
        int32_t status) {
    switch (status) {
        case COUNTER_OK: return "ok";
        case COUNTER_BAD_ARGUMENT: return "bad argument";
        case COUNTER_NO_MEMORY: return "out of memory";
        case COUNTER_OVERFLOW: return "integer overflow";
        case COUNTER_INTERNAL: return "internal C++ error";
        default: return "unknown status";
    }
}

COUNTER_API uint32_t counter_api_version(void) {
    return COUNTER_ABI_VERSION;
}

} // extern "C"
~~~

**Mechanism:**

1. `counter_handle` is a real C++ struct in the implementation; the C caller only holds an opaque pointer.
2. `counter_create` allocates with `new` and catches `std::bad_alloc` as well as other exceptions. It does not let C++ exceptions escape across the C ABI.
3. `counter_get` and `counter_add` only borrow; they do not free the handle.
4. `counter_add` widens operands to `int64_t` **before** addition to avoid undefined behavior from 32-bit signed overflow; it checks bounds before updating state.
5. If overflow occurs, it returns `COUNTER_OVERFLOW` **without changing** the counter value.
6. `counter_destroy` uses `delete`, matching the `new` allocator; the object in the demo has a trivial/no-throw destructor.
7. `counter_status_message` returns a static string literal with a lifetime managed by the library.

**Limitation:** `catch (...)` does not turn a forged pointer, stale handle, concurrent destroy, or memory corruption into a safe Java/C error. Those situations can be undefined behavior. For APIs that accept untrusted handles, you must use a registry or generation tokens and synchronize lookup-to-use.

### If a destructor can fail

Do not copy `void counter_destroy` to an SDK whose destructor/callback can throw or whose resource close can fail. Define the destructor as `noexcept` and handle errors deliberately, or add a `counter_close` function that returns a status before releasing. The C ABI must not let exceptions pass through C callers/JNI frames.

## 7. C11 Client File: c_client.c

This is an important check: **the client is compiled with a C compiler**, without needing C++ syntax.

~~~c
#include "counter_api.h"

#include <inttypes.h>
#include <stdio.h>

int main(void) {
    counter_handle *handle = NULL;
    int32_t current = 0;

    int32_t status = counter_create(10, &handle);
    if (status != COUNTER_OK) {
        fprintf(stderr, "create: %s\n",
                counter_status_message(status));
        return 1;
    }

    int exit_code = 0;
    do {
        printf("c-api-version=%u\n",
               (unsigned)counter_api_version());

        status = counter_add(handle, 5, &current);
        if (status != COUNTER_OK) {
            exit_code = 1;
            break;
        }
        printf("c-after-add=%" PRId32 "\n", current);

        status = counter_add(handle, INT32_MAX, &current);
        printf("c-overflow-status=%" PRId32 "\n", status);
        if (status != COUNTER_OVERFLOW) {
            exit_code = 1;
            break;
        }

        status = counter_get(handle, &current);
        if (status != COUNTER_OK) {
            exit_code = 1;
            break;
        }
        printf("c-still=%" PRId32 "\n", current);

    } while (0);

    counter_destroy(handle);
    handle = NULL;
    return exit_code;
}
~~~

### C client stdout

~~~text
c-api-version=1
c-after-add=15
c-overflow-status=3
c-still=15
~~~

The counter starts at 10; adding 5 makes 15. Then `15 + INT32_MAX` does not fit in a signed 32-bit integer, so status is 3 (`COUNTER_OVERFLOW`). Because the function checks for overflow **before writing**, `counter_get` still returns 15. The client calls destroy exactly once even if an intermediate operation fails.

Using `PRId32` from `inttypes.h` avoids assuming the format specifier of `int32_t`; the public header is completely C-compatible. If a client wants to share a handle across multiple threads, it needs a lock/refcount/lease — this sample has one owner and one thread.

## 8. Java 17 Using the Same C ABI via JNI

Architecture of the example:

~~~text
Java CounterDemo.Counter (AutoCloseable)
            |
        JNI methods
            |
            v
counter_jni.cpp
  - receives jint / jlong
  - converts status to Java exception
            |
            v
counter_api.h (PUBLIC C ABI)
            |
            v
counter_api.cpp (C++17 private state)
  - new / delete
  - overflow check

c_client.c --------> counter_api.h (same contract)
~~~

The JNI adapter does not allocate a separate implementation of its own: it uses `counter_create/get/add/destroy` just like the C client. Therefore, the public C API is independent of the JVM. If the C++ core is changed from a simple struct to a complex class, the Java JNI code still uses the same façade.

### Why does Java need AutoCloseable?

A Java `long` only holds a **numeric value**. The GC does not automatically know that the number is the address of an object allocated by C++ `new`. The wrapper needs to explicitly call release via `close()`:

~~~java
try (CounterDemo.Counter counter =
         new CounterDemo.Counter(40)) {
    System.out.println(counter.value());
} // close() -> JNI -> counter_destroy()
~~~

This is an illustrative Java snippet. The complete class below ensures that closing multiple times on one wrapper does not call delete again.

## 9. Complete Java File: CounterDemo.java

~~~java
public final class CounterDemo {
    static {
        System.loadLibrary("counterbridge");
    }

    private CounterDemo() {}

    private static native int nVersion();
    private static native long nCreate(int initial);
    private static native int nGet(long handle);
    private static native int nAdd(long handle, int delta);
    private static native void nDestroy(long handle);

    public static final class Counter implements AutoCloseable {
        private long handle;

        public Counter(int initial) {
            long created = nCreate(initial);
            if (created == 0L) {
                throw new IllegalStateException(
                        "Native allocation failed");
            }
            handle = created;
        }

        private void requireOpen() {
            if (handle == 0L) {
                throw new IllegalStateException("Counter is closed");
            }
        }

        public synchronized int value() {
            requireOpen();
            return nGet(handle);
        }

        public synchronized int add(int delta) {
            requireOpen();
            return nAdd(handle, delta);
        }

        public synchronized boolean isClosed() {
            return handle == 0L;
        }

        @Override
        public synchronized void close() {
            if (handle == 0L) {
                return;
            }

            long owned = handle;
            handle = 0L;
            nDestroy(owned);
        }
    }

    public static void main(String[] args) {
        System.out.println("apiVersion=" + nVersion());

        Counter counter = new Counter(40);
        try (counter) {
            System.out.println("initial=" + counter.value());
            System.out.println("afterAdd=" + counter.add(2));

            try {
                counter.add(Integer.MAX_VALUE);
            } catch (ArithmeticException ex) {
                System.out.println(
                        "overflow=" + ex.getClass().getSimpleName());
            }

            System.out.println("unchanged=" + counter.value());
        }

        System.out.println("closed=" + counter.isClosed());

        counter.close();
        System.out.println("closedTwice=" + counter.isClosed());

        try {
            counter.value();
        } catch (IllegalStateException ex) {
            System.out.println(
                    "afterClose=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

**Thread/lifetime contract of the wrapper:**

- `value`, `add`, and `close` are all synchronized on the same Java object. `close` cannot run between `requireOpen` and the JNI call of a method that has acquired the monitor.
- When the resource closes, `handle=0L` and new operations from Java are blocked with `IllegalStateException` before entering JNI.
- Repeated `close` on **the same wrapper** is a no-op. This does **not** make native `delete` idempotent.
- `try (counter)` is valid in Java 17; it automatically calls close when leaving the block.
- If the native resource can be used by another C worker or a second Java wrapper, a synchronized instance is **not enough**: a native-side lease/refcount or registry is required.

**Do not expose a public `long getHandle()` if users could forge/copy the value and call destroy independently.** In the example, all native methods are private; that is encapsulation, not a defense against malicious Java code with reflection/Unsafe privileges.

## 10. JNI Adapter: counter_jni.cpp

First generate the header from the actual Java declarations:

~~~bash
javac -h . CounterDemo.java
~~~

The command creates `CounterDemo.class`, `CounterDemo$Counter.class`, and `CounterDemo.h`. Because the `native` methods are declared on the **outer CounterDemo class**, the JNI export names are `Java_CounterDemo_nCreate`, not the name of the nested class.

~~~cpp
#include "CounterDemo.h"
#include "counter_api.h"

#include <cstdint>

static_assert(sizeof(std::uintptr_t) <= sizeof(jlong),
              "Example requires pointer width <= 64 bits");

/*
 * Only for a trusted wrapper and a single process/ABI.
 * Do not serialize the pointer or let callers fabricate values.
 */
static jlong to_java_handle(counter_handle *handle) noexcept {
    return static_cast<jlong>(
            reinterpret_cast<std::uintptr_t>(handle));
}

static counter_handle *from_java_handle(jlong handle) noexcept {
    return reinterpret_cast<counter_handle *>(
            static_cast<std::uintptr_t>(handle));
}

/* Only call when there is no pending Java exception. */
static void throw_status(JNIEnv *env, int32_t status) {
    const char *klass = "java/lang/IllegalStateException";

    if (status == COUNTER_OVERFLOW) {
        klass = "java/lang/ArithmeticException";
    } else if (status == COUNTER_NO_MEMORY) {
        klass = "java/lang/OutOfMemoryError";
    } else if (status == COUNTER_BAD_ARGUMENT) {
        klass = "java/lang/IllegalArgumentException";
    }

    jclass cls = env->FindClass(klass);
    if (cls != nullptr) {
        env->ThrowNew(cls, counter_status_message(status));
        env->DeleteLocalRef(cls);
    }
}

extern "C" {

JNIEXPORT jint JNICALL
Java_CounterDemo_nVersion(JNIEnv *env, jclass klass) {
    (void)env;
    (void)klass;
    return static_cast<jint>(counter_api_version());
}

JNIEXPORT jlong JNICALL
Java_CounterDemo_nCreate(
        JNIEnv *env, jclass klass, jint initial) {
    (void)klass;

    counter_handle *created = nullptr;
    const int32_t status =
            counter_create(static_cast<int32_t>(initial), &created);

    if (status != COUNTER_OK) {
        throw_status(env, status);
        return static_cast<jlong>(0);
    }

    return to_java_handle(created);
}

JNIEXPORT jint JNICALL
Java_CounterDemo_nGet(
        JNIEnv *env, jclass klass, jlong handle) {
    (void)klass;

    int32_t value = 0;
    const int32_t status =
            counter_get(from_java_handle(handle), &value);

    if (status != COUNTER_OK) {
        throw_status(env, status);
        return static_cast<jint>(0);
    }

    return static_cast<jint>(value);
}

JNIEXPORT jint JNICALL
Java_CounterDemo_nAdd(
        JNIEnv *env, jclass klass, jlong handle, jint delta) {
    (void)klass;

    int32_t value = 0;
    const int32_t status =
            counter_add(
                    from_java_handle(handle),
                    static_cast<int32_t>(delta), &value);

    if (status != COUNTER_OK) {
        throw_status(env, status);
        return static_cast<jint>(0);
    }

    return static_cast<jint>(value);
}

JNIEXPORT void JNICALL
Java_CounterDemo_nDestroy(
        JNIEnv *env, jclass klass, jlong handle) {
    (void)env;
    (void)klass;
    counter_destroy(from_java_handle(handle));
}

} // extern "C"
~~~

### Important JNI Rules

- `jint` is a 32-bit Java integer; the C ABI uses the corresponding `int32_t` on supported targets.
- `jlong` is Java 64-bit. Pointer → `uintptr_t` → `jlong` is only suitable for ABIs where pointers can round-trip through an integer within 64 bits. Capability-pointer platforms may require a different registry/token.
- `JNIEnv*` is bound to the current thread. Do not store it for use from another native thread.
- `FindClass` returns a JNI local reference; `DeleteLocalRef` only deletes this reference, **not** the C++ allocation.
- `ThrowNew` sets a pending Java exception; the adapter returns immediately with a dummy value if the status is an error. Java will receive the exception.
- `nDestroy` calls the matching public `counter_destroy`; do not use `free` from the wrong allocator.
- `JNIEXPORT` handles exporting JNI symbols, while public `COUNTER_API` exports C ABI symbols; the two groups of functions have different roles.
- The C ABI catches C++ exceptions before JNI receives them, but if the JNI adapter adds C++ logic that can throw, the adapter must also catch before returning.
- A forged nonzero `jlong` can be cast into an invalid pointer and cause a crash. Only grant usage through a wrapper that controls lifetime or build a native registry for untrusted input.

## 11. Build and Run on Linux

In a directory containing exactly five files:

~~~text
counter_api.h
counter_api.cpp
c_client.c
CounterDemo.java
counter_jni.cpp
~~~

Commands with JDK 17+, GCC/G++:

~~~bash
javac -h . CounterDemo.java

g++ -std=c++17 -Wall -Wextra -fPIC -shared \
  -DCOUNTER_BUILD_SHARED \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  counter_api.cpp counter_jni.cpp \
  -o libcounterbridge.so

gcc -std=c11 -Wall -Wextra \
  c_client.c -L. -lcounterbridge \
  -Wl,-rpath,'$ORIGIN' \
  -o c_client

./c_client
java -Djava.library.path=. CounterDemo
~~~

`g++` builds the C++ core + JNI adapter into **one shared library** `libcounterbridge.so`. `gcc -std=c11` builds the pure C client; this demonstrates that the public header does not require C++ syntax. `javac -h` generates the JNI header before the C++ adapter compiles. `-Wl,-rpath,'$ORIGIN'` helps the C executable find the library next to it, while the JVM uses `-Djava.library.path=.` to find the JNI library.

## 12. Build and Run on macOS

~~~bash
javac -h . CounterDemo.java

clang++ -std=c++17 -Wall -Wextra -dynamiclib \
  -DCOUNTER_BUILD_SHARED \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  counter_api.cpp counter_jni.cpp \
  -Wl,-install_name,@rpath/libcounterbridge.dylib \
  -o libcounterbridge.dylib

clang -std=c11 -Wall -Wextra \
  c_client.c -L. -lcounterbridge \
  -Wl,-rpath,@loader_path \
  -o c_client

./c_client
java -Djava.library.path=. CounterDemo
~~~

`clang++` creates `libcounterbridge.dylib`, while `clang` compiles the C consumer. The native library/JVM need the same CPU architecture (Apple Silicon or Intel). An application with hardened runtime/code signing may need additional loader configuration; the sample assumes a development environment that allows loading self-built dylibs.

## 13. Build and Run on Windows

In MSVC's **x64 Native Tools Developer Command Prompt** (if the JVM is x64):

~~~bat
javac -h . CounterDemo.java

cl /nologo /W4 /EHsc /std:c++17 /LD ^
  /DCOUNTER_BUILD_SHARED ^
  /I "%JAVA_HOME%\include" ^
  /I "%JAVA_HOME%\include\win32" ^
  counter_api.cpp counter_jni.cpp /Fe:counterbridge.dll

cl /nologo /W4 /TC c_client.c /link counterbridge.lib

c_client.exe
java -Djava.library.path=. CounterDemo
~~~

Windows creates `counterbridge.dll` and the import library `counterbridge.lib` from the C API exports. `System.loadLibrary("counterbridge")` uses the logical name. Make sure the JVM, DLL, MSVC runtime dependencies, and C executable match 32/64-bit; do not mix architectures or incompatible calling conventions.

**In production:** you can separate the core `libcounter_core` from JNI `libcounter_jni`, but you must handle dependency paths/load order and still keep the C ABI as a layer independent of Java.

## 14. Expected Java 17 Stdout

~~~text
apiVersion=1
initial=40
afterAdd=42
overflow=ArithmeticException
unchanged=42
closed=true
closedTwice=true
afterClose=IllegalStateException
~~~

Breakdown:

1. `nVersion` calls `counter_api_version` and receives 1.
2. `Counter(40)` calls JNI → C ABI → C++ `new`.
3. `add(2)` updates 40 to 42.
4. `add(Integer.MAX_VALUE)` is blocked for overflow by `counter_add`; JNI converts `COUNTER_OVERFLOW` to Java `ArithmeticException`.
5. Value remains 42 because native state was not modified on the error path.
6. Leaving `try (counter)`, Java `close` invalidates the handle and calls `counter_destroy` exactly once.
7. The second close does not destroy again.
8. Calling value after close throws `IllegalStateException` in **Java** before calling JNI.

**Verification note:** this is the deterministic stdout according to the example logic when built/loaded properly. This does not claim the code has been actually compiled on every OS/CPU; runtime testing and sanitizers still need to be performed on the target toolchain.

## 15. What Must a Stable C ABI Preserve Besides Symbol Names?

**Symbol contract:** exported names like `counter_create` must remain unchanged, without being name-mangled or having hidden symbols. On Linux use `nm -D`/`readelf -Ws`; on macOS use `nm -gU`; on Windows use `dumpbin /exports`.

**Calling convention:** if a Windows API requires `__cdecl`, `__stdcall`, or another convention, it must be expressed consistently in public declarations and implementation. `extern "C"` does not resolve all calling convention differences.

**Type/layout contract:** avoid C++ classes, STL, templates, references, exceptions, and C bitfields in the ABI. Public C structs, if unavoidable, must have explicit size/version/alignment; opaque handles are usually easier to keep stable.

**Lifetime contract:** an allocation function must be paired with a deallocation function. Do not return a buffer from `new[]` and ask the C client to `free` it. Static message pointers must not be freed by the client. Double-destroy and using a pointer after destroy are bugs.

**Semantic contract:** success/failure, output values, and whether state changes on error must not be changed arbitrarily. Versioning must reflect breaking changes.

### Keeping the symbol while changing parameter types can still break the ABI

Version 1:

~~~c
int32_t process_data(const uint8_t *data, uint32_t size);
~~~

Version 2:

~~~c
int32_t process_data(const uint8_t *data, uint64_t size);
~~~

These are **two illustrative signatures belonging to two different versions**. C linkage can still export the same name `process_data`, but an old client binary passes `uint32_t` while the new library expects `uint64_t`. A successful link **does not prove binary compatibility**. Keep v1 and export a `process_data_v2` or make a major ABI change according to your release policy.

### Practical Versioning

- `counter_api_version()` returns the major ABI version and can be supplemented with capability-query APIs.
- Adding new functions usually breaks old clients less than changing old signatures.
- Do not reuse an old status code with a new meaning.
- If a public struct is unavoidable, consider `struct_size`, `version`, and reserved fields, while still managing packing/alignment.
- Test **old binary clients** against the new shared library, not just rebuilding everything and calling it compatible.

## 16. Do Not Let C++ Exceptions Escape Across the Boundary

Bad pattern:

~~~cpp
extern "C" int32_t bad_export(void) {
    throw std::runtime_error("failed");
}
~~~

This is an **anti-pattern**, not a function that should be exported. A C caller has no C++ unwind/exception contract; a JNI caller should not receive a C++ exception either. The risk is termination or undefined behavior.

Good pattern:

~~~cpp
extern "C" int32_t safe_export(void) noexcept {
    try {
        /* C++ code that may throw. */
        return 0;
    } catch (const std::bad_alloc &) {
        return 2;
    } catch (...) {
        return 4;
    }
}
~~~

This is an **illustrative snippet**. `noexcept` can be placed on the C++ definition but not directly in a C11 header; `catch` and not throwing across the boundary are what must be guaranteed. Do not assume `catch (...)` protects against invalid native pointers or signed overflow — those issues require separate memory safety design and arithmetic checks.

In the JNI adapter, throw a Java exception with `ThrowNew` when there is no pending exception; then the native method returns immediately. JNI local refs are cleaned up with `DeleteLocalRef`, and C++ resources are released via façade destroy. The two mechanisms cannot replace each other.

## 17. String Data and Buffers: Do Not Export std::string

Example that should not cross the C ABI:

~~~cpp
extern "C" std::string counter_name();
~~~

Language linkage is C, but the return type is still a C++ object with an implementation-dependent destructor/allocator/layout. Replace it with a **caller-owned buffer**:

~~~c
int32_t counter_name_copy(
    const counter_handle *handle,
    char *buffer,
    uint64_t capacity_bytes,
    uint64_t *required_bytes);
~~~

Or a **library-owned buffer with a release function**:

~~~c
int32_t counter_name_alloc(
    const counter_handle *handle,
    char **out_utf8,
    uint64_t *out_size);

void counter_string_release(char *owned_utf8);
~~~

These are **illustrative signatures**, not implemented in the counter program. You must document the encoding (e.g. UTF-8), byte length, NUL terminator, error when the buffer is too small, and ownership rights. A string pointer allocated by the library must not be `free`d by the caller unless the contract allows it. The JNI adapter can copy bytes/UTF-16 into a Java `String`, but Java-specific types do not appear in the core C header.

## 18. Thread Safety Is Completely Different from C ABI Stability

A library with a stable C ABI can still suffer from data races:

~~~text
Thread A: counter_get(handle)
                   |
                   +-- C++ dereference
Thread B: counter_destroy(handle)
                   |
                   +-- C++ delete
Thread A: continues using freed pointer
~~~

In the Java example, synchronized instance methods prevent close from interleaving with operations on **one Java wrapper**. However, if a C client/native worker already holds its own pointer, the Java lock does not protect it.

Options when sharing is needed:

- Unique ownership and a mutex coordinating get/add/destroy.
- Shared ownership via `retain/release` and refcount on the native side.
- Scoped borrow/lease where close waits for all in-flight users.
- Opaque numeric registry tokens with generation/type checks to detect stale/ABA handles.
- Thread-affinity contract when an SDK requires a resource to be used only on one event loop.

A `handle != NULL` check does not prove the handle is still alive. A pointer can remain non-null after destroy or be reused by the allocator for another allocation.

## 19. Common Mistakes and How to Handle Them

| Mistake | Consequence | Fix |
|---|---|---|
| Using `extern "C"` directly in a C11 header | C compiler error | Guard with `#ifdef __cplusplus` |
| Thinking `extern "C"` makes the ABI completely portable | Calling convention/layout still differ | Design a C-compatible API per target ABI |
| Not exporting symbols from a Windows DLL | Linker/loader cannot find them | `dllexport` and import library |
| Public API returning a C++ class/`std::string` | Caller has no compatible ABI | Opaque handles or C buffers |
| C++ exception escaping a C/JNI function | Termination/undefined behavior | Catch at the C++ façade |
| C++ `new` but C `free` | Allocator mismatch/UB | Matching exported destroy |
| Two owners destroying the same handle | Double-free | Unique owner/refcount |
| Java forgetting to close | Native leak | `AutoCloseable`/try-with-resources |
| Copying C++ pointer as `jlong` to another process | Meaningless address | Do not serialize raw pointers |
| Forged pointer passed to `counter_get` | Crash | Registry/validated opaque token |
| Mismatched JNI method name | `UnsatisfiedLinkError` | `javac -h` then include header |
| Treating C `long` like Java `long` | Wrong width on Windows x64 | Explicit `int32_t`/`uint64_t` |
| Java close racing with get/add | Use-after-free | synchronized/lock/lease |
| Changing public signature while keeping symbol | Old binary clients may break ABI | API version/new function |
| Assuming `catch (...)` protects stale pointers | C++ exceptions do not catch UB | Lifetime/validation |
| Putting `JNIEnv*` into the core public C ABI | C clients must depend on JVM | Separate JNI adapter |
| C calling JNI from another thread with cached env | JNI thread misuse | Attach proper thread, do not share `JNIEnv*` |
| Loading DLL of wrong architecture or missing runtime | Load failure | Check OS/CPU/ABI/dependencies |

## 20. Testing and QA When Releasing a Library

1. Compile `c_client.c` with a real C11 compiler (do not secretly use g++).
2. Compile `counter_api.cpp` with C++17; inspect exported C symbols and ensure no unintended mangling.
3. Run the C client, verifying version/add/overflow/state unchanged and single destroy.
4. Run `javac -h`, build the JNI adapter, and run the full output with Java 17.
5. Call Java close multiple times and operations after close; confirm no double-free/UAF.
6. Test API null pointers/invalid arguments per the contract; do **not** fuzz raw forged pointers without a registry/isolated testing.
7. Add tests for allocation failure, overflow, JNI exceptions, and C++ destructor policy.
8. Test concurrency separately: read/write/destroy on the same handle must be synchronized or forbidden.
9. Check ABI against **a client binary from an older version**, not just by rebuilding the client.
10. Inspect exported names with `nm`/`readelf`/`dumpbin`, and dependencies with `ldd`/`otool`/`dumpbin`.
11. Use `java -Xcheck:jni -Djava.library.path=. CounterDemo` to detect some JNI misuse; use AddressSanitizer/Valgrind accordingly to analyze C++ memory bugs.
12. Test x86-64/ARM64, Windows/MSVC, Linux/GCC, macOS/Clang within your actual target scope; identical symbol names do not prove binary portability across platforms.

## 21. Exercises and Self-Check Questions

**1. Does `extern "C"` turn `std::string` into a C ABI type?** No. It affects language linkage, not making STL layout portable.

**2. Why must the header have `#ifdef __cplusplus`?** C11 does not understand `extern "C"`, whereas C++ needs it to keep C linkage.

**3. Why use an opaque handle?** To hide C++ object layout from the client so the implementation can be changed without breaking the public struct ABI.

**4. Who frees the object created by `counter_create`?** The caller owns the owned handle and must call `counter_destroy` exactly once.

**5. Why doesn't Java call `free` on the native pointer?** C++ allocates with `new`; it must be released by the implementation's matching allocator/module.

**6. Why does `counter_add` compute the sum in `int64_t`?** To check for overflow before casting/writing a signed 32-bit value.

**7. If overflow occurs, does the state change?** No; the implementation returns the status before updating.

**8. Why does the JNI bridge convert error codes to Java exceptions?** The C core does not depend on Java, while Java callers expect errors according to Java API conventions.

**9. Are `AutoCloseable.close()` and `Arena.close()` the same?** They are different APIs. The wrapper in the demo allows repeated close; a native destroy must not be assumed to be automatically idempotent.

**10. Can `uint32_t length` be changed to `uint64_t length` while keeping the old C symbol?** Unsafe; that is a breaking ABI change even if the linker still finds the name.

**11. Is a C API thread-safe just because it is a C ABI?** No. Data races and resource lifetimes must be designed separately.

**12. Can Java 22+ use the same core C ABI?** Yes, via FFM downcalls through `Linker`/`SymbolLookup`, but you still must manage opaque pointers and close on time.

**13. Does `counter_status_message` return an owned string?** No; it is a borrowed static literal, and the caller does not free it.

**14. If a raw pointer is still non-NULL after destroy, can it be used?** No; the pointer is already dangling.

**15. Why use a C compiler to build c_client.c?** To verify that the public header is truly usable by C and does not accidentally depend on C++ syntax.

## References

- [Oracle Java SE 17 — JNI Design](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): native method naming, linking, and JNI ABI.
- [Oracle Java SE 17 — JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): exceptions and local references.
- [Oracle Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): explicit resource closing.
- [Oracle Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): FFM downcalls through the native ABI.
- [Oracle Java SE 22 — SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html): looking up exported functions.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM becoming a standard API in Java 22.
- [cppreference — Language linkage](https://en.cppreference.com/w/cpp/language/language_linkage): `extern "C"` and linkage semantics.
- [Microsoft Learn — dllexport/dllimport](https://learn.microsoft.com/en-us/cpp/cpp/dllexport-dllimport): Windows DLL symbol export/import.

## Takeaways

**A stable C ABI layer around a C++ library consists of many elements, not just `extern "C"`.** It requires a C-compatible public header, exported symbols/calling convention, fixed-width types, opaque handles, exception containment, matching allocators, ownership, and API versioning.

A useful design workflow:

1. Keep C++ classes, STL, and exceptions **inside the implementation**.
2. Export a C header compilable from C11, with an `extern "C"` guard for C++.
3. Return status codes and data via output pointers; document success/failure semantics.
4. Allocate/destroy resources in the same library; Java uses a JNI adapter instead of touching the C++ allocator.
5. The Java 17 wrapper uses `AutoCloseable` and protects operations from close races.
6. Test symbols and ABI with both a C client and a JNI client, using old binary tests when upgrading versions.
7. When JDK 22+ FFM is needed, keep the C façade unchanged and change how Java calls it rather than creating a new public C++ ABI.

**Key takeaway:** *C++ is free to change behind the shell; the outward contract must be a small C ABI with clear versioning and ownership.*
