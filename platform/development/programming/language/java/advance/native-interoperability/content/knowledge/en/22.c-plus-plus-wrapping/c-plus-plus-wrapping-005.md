# Passing Data via Buffer and Length Instead of Exposing Internal Types When Wrapping C++ Libraries

When Java needs to use a C++ library, passing `std::string`, `std::vector`, `std::map`, or C++ class objects directly across the JNI/FFM boundary is a risky choice. These C++ types have layouts, allocators, destructors, copy/move rules, and ABIs affected by the compiler, C++ standard library, and build configuration. Java does not know how to decode a `std::vector` object into a byte array solely from the address of that object.

A more robust design is to **hide the entire C++ implementation behind a C-compatible façade**, exchange data via **buffer pointer + length**, and for results include **buffer capacity + bytes written/required + status code**:

```c
int xb_encode(const uint8_t *input, size_t input_length,
              uint8_t *output, size_t output_capacity,
              size_t *output_length);
```

Inside `xb_encode`, `std::vector<std::uint8_t>`, `std::string`, and complex C++ algorithms can be used. Outside, C/JNI/FFM only sees clearly described C types. This approach separates the **ABI** from **internal data structures**, makes lifetime/ownership transparent, and avoids returning pointers to destroyed C++ temporaries.

**Principle:** `pointer + length` alone is not enough to be safe. The contract must clearly specify **length in bytes**, **maximum capacity**, **null/empty**, **who allocates and frees**, **C++ exceptions**, **encoding**, **output on error**, and **whether pointers are retained after return**.

## 1. Why Not Export Internal C++ Types?

An internal convenient C++ API might look like:

```cpp
#include <string>
#include <vector>

namespace internal {
    class Codec {
    public:
        std::vector<unsigned char> encode(
                const std::vector<unsigned char>& data) const;
        std::string description() const;
    };
}
```

This is an **illustrative declaration snippet**, not a complete class with an implementation. It makes sense for a C++ caller built with a matching ABI, but it is not a contract for Java to infer the binary representation directly.

Common issues:

- `std::vector` is not a byte array placed directly at the object's address. The object holds metadata, while elements typically reside in a separate allocation. The C++ standard does not require all compilers to have the same object layout.
- `std::string` does not guarantee UTF-8 encoding; it can contain binary bytes, embedded NULs, and have different Small String Optimization policies.
- C++ symbol names have name mangling; `extern "C"` gives the function name C linkage, but does **not** make `std::vector` a C ABI type.
- C++ allocators/CRT runtimes may differ; `free`, `delete`, `delete[]`, and library-specific destroy APIs are not interchangeable.
- C++ exceptions must not be allowed to automatically cross the C ABI/JNI/FFM boundary and expect Java to catch them as Java exceptions.
- `std::vector::data()` can be invalidated when the vector reallocates; `std::string::c_str()` becomes invalid when the owner is destroyed or an operation modifies storage.
- Java has GC and JNI references; it does not automatically run a C++ destructor for an address without an owner contract.

Two anti-patterns:

```cpp
// Wrong: returning an address inside a C++ temporary.
extern "C" const char *bad_result() {
    std::string local = "temporary";
    return local.c_str();  // Dangling as soon as local is destroyed.
}

// Wrong: C linkage does not make std::vector a C ABI.
extern "C" std::vector<unsigned char> bad_vector_api();
```

**How to fix:** keep `std::string`/`std::vector` inside the implementation, then **copy the required data into a caller-owned buffer** before the C++ object's lifetime ends. If long-lived C++ state needs to be kept, use an **opaque C handle** with create/destroy; data is still exchanged via buffers.

## 2. Complete Contract for Buffer + Length

| Argument | Exact Meaning | What Caller/Callee Must Guarantee |
| --- | --- | --- |
| `input` | Address of readable byte region | If `input_length > 0`, points to at least that many valid bytes |
| `input_length` | Number of valid input bytes | Do not confuse with Java/Unicode characters or element counts of other types |
| `output` | Address of writable region | Caller-allocated and caller-owned buffer; not an output pointer malloc'd by callee |
| `output_capacity` | Maximum number of bytes allowed to be written | May be larger than actual output; never write beyond capacity |
| `output_length` | Pointer to caller-provided `size_t` | Callee writes required size if capacity is insufficient; written size on success |
| Status `int` | Contracted result code | Do not use length=0 as an error indicator if empty output is valid |

**Contract used in this article:**

1. `input` is **borrowed read-only** during a single call. The callee does not retain the pointer, does not call `free(input)`, and does not overwrite input data.
2. The caller owns `output` and only allows the callee to write at most `output_capacity` bytes. The callee does not `free(output)`.
3. `output_length` is **required to be non-null**; the callee writes the **required** byte count when returning `BUFFER_TOO_SMALL`, or the **written** byte count when returning `OK`.
4. If capacity is insufficient, the callee must not write a truncated partial result; status `BUFFER_TOO_SMALL` must be accompanied by the required length.
5. For `input_length == 0`, `input == NULL` is valid. For `output_capacity == 0`, `output == NULL` is valid to *query* the size.
6. Output is **binary data**; do not add a NUL terminator unless the contract states so.
7. In the public contract, `input` and `output` must be two **non-overlapping** regions. Even if the current implementation uses an intermediate buffer, the caller must not rely on in-place capability when the API has not promised it.
8. All C++ exceptions must be caught in the C façade. Errors are returned via status; the JNI shim can map status to a Java exception.
9. **It is impossible to verify whether a pointer actually points to enough bytes solely from the declared pointer and length.** The caller must ensure correct bounds and lifetime.

Condition 9 is especially important: C can still crash if the caller claims `length=1000` when the actual allocation is only 8 bytes. A buffer+length API makes the contract clearer and logic easier to validate, rather than replacing memory safety mechanisms for native code.

## 3. Input Length Differs from Output Capacity and Written Length

For a transformation returning a result of `M` bytes, where the caller has an output buffer of `N` bytes:

- If `N >= M`, the callee writes exactly `M` bytes, returns `OK` and `*output_length=M`.
- If `N < M`, the callee returns `BUFFER_TOO_SMALL` and `*output_length=M`, without writing partial output.
- If the caller does not yet know `M`, it can call with `output=NULL` and `capacity=0` to query.

```text
Java/C caller               C façade                  C++ core
     |                          |                         |
     | input,len,NULL,0,&need   |                         |
     |------------------------->| compute bytes needed    |
     |<-------------------------| TOO_SMALL, need=M       |
     |                          |                         |
     | allocate M bytes         |                         |
     | input,len,out,M,&written |                         |
     |------------------------->| -> process data ------->|
     |                          | <- C++ vector result ---|
     |                          | copy ≤ capacity         |
     |<-------------------------| OK, written=M           |
     |                          |                         |
     | Caller uses exact M bytes and manages output buffer|
```

This is called the **two-pass output pattern**. For data with a predetermined result size (e.g., XORing each byte, where output length equals input length), the query pass can be skipped in an optimized version; this example still uses two passes to demonstrate the universal API for compression/serialization/conversion libraries with variable output.

**Note:** if the output size depends on state that changes between the query and fill calls (e.g., database, time-based value, stream), `M` may change. In that case, a snapshot/version token must be designed, or a **bounded** retry when receiving `BUFFER_TOO_SMALL` again. Do not retry infinitely, and do not assume two passes automatically form a transaction.

## 4. Length Is Measured in **Bytes**, Not String Length

Consider binary input containing NUL:

```c
#include <stdint.h>
#include <stddef.h>

const uint8_t data[] = {0x41, 0x00, 0xFF};
const size_t size = sizeof(data); /* 3 bytes */
```

This is **3 bytes**, even though `strlen((const char*)data)` would stop at the first `0x00` byte. **Do not use `strlen` for arbitrary binary data**; always rely on the validated `input_length`.

For text, encoding must be declared separately:

```java
String text = "Cà phê";
int units = text.length(); // 6 UTF-16 code units.
byte[] utf8 = text.getBytes(
        java.nio.charset.StandardCharsets.UTF_8);
int lengthBytes = utf8.length;  // 8 UTF-8 bytes.
```

- Java `String.length()` counts UTF-16 code units; this number is not always equal to Unicode code points or UTF-8 byte count.
- `std::string::size()` counts bytes of the stored string, without stating which standard those bytes were encoded with.
- JNI `GetStringUTFChars` returns **modified UTF-8**, not necessarily standard UTF-8 (differs at U+0000 and supplementary code points). If the C++ library expects standard UTF-8, use a well-defined conversion, such as `String.getBytes(StandardCharsets.UTF_8)`.
- If a C API requires a NUL-terminated string, explicitly specify appending the 0 byte and reject embedded NULs when there is no way to represent them; a binary buffer+length **does not automatically have a terminator**.
- For serialized objects, images, compressed payloads, or protobufs, never convert bytes to `String` just to pass them more easily.

## 5. Practice Architecture: 4 Clearly Separated Layers

```text
NativeBufferDemo.java (Java 17+)
    byte[] input --> xorCopy(input) --> byte[] output
                          |
                          v
jni_bridge.cpp (JNI/C++ shim)
    GetByteArrayRegion (copy, does not pin Java array)
    malloc temporary source/output + RAII free
                          |
                          v
bridge.h / bridge.cpp (C-compatible API)
    int xb_encode(uint8_t*,size_t,uint8_t*,size_t,size_t*)
    validation, buffer-too-small, C status, catch C++ exceptions
                          |
                          v
private_core.hpp / private_core.cpp (internal C++)
    internal::Codec using std::vector<uint8_t>
```

To clearly demonstrate byte length including NUL, the core will **XOR each byte with key `0x5A`**. This is a data transformation for learning purposes, **not encryption or a security mechanism**.

```text
Input:         41 00 FF
XOR key:       5A 5A 5A
Output:        1B 5A A5
Second XOR:    41 00 FF
```

The formula `x ^ key ^ key == x` helps us verify that data is not truncated, including byte 0 and byte FF.

## 6. File `bridge.h`: C ABI Without C++ Types

```c
#ifndef BUFFER_BRIDGE_H
#define BUFFER_BRIDGE_H

#include <stddef.h> /* size_t */
#include <stdint.h> /* uint8_t */

enum {
    XB_OK = 0,
    XB_BUFFER_TOO_SMALL = 1,
    XB_INVALID_ARGUMENT = 2,
    XB_NO_MEMORY = 3,
    XB_INTERNAL_ERROR = 4
};

#ifdef __cplusplus
extern "C" {
#endif

/*
 * input/input_length: borrowed, read-only bytes.
 * output/output_capacity: caller-provided writable buffer.
 * output_length: required length on TOO_SMALL, actual on OK.
 * Query: output=NULL, output_capacity=0.
 * Null input is allowed if input_length=0.
 * Do not write partial output when capacity is insufficient.
 * Do not retain/free input and output pointers.
 * Input/output regions must not overlap per contract.
 * Do not let any C++ exception escape this function.
 */
int xb_encode(const uint8_t *input, size_t input_length,
              uint8_t *output, size_t output_capacity,
              size_t *output_length);

#ifdef __cplusplus
}
#endif

#endif
```

**Why are these types suitable?** `uint8_t` is an 8-bit byte on Linux x86-64; `size_t` represents C buffer size according to the process ABI; `int` represents status. `enum` declares C-compatible integral constants (not C++ `enum class`). `extern "C"` is wrapped in `#ifdef __cplusplus` so a C compiler can also read the header.

`size_t` **must not be assumed equal to Java `int`**; on Linux x64 it is typically 64 bits wide. When JNI converts `jsize` to `size_t`, signed values must be checked, and when converting required length back to `jsize`, it must be checked before casting.

## 7. Files `private_core.hpp` and `private_core.cpp` — Pure C++ Implementation

**File `private_core.hpp`:**

```cpp
#ifndef PRIVATE_CORE_HPP
#define PRIVATE_CORE_HPP

#include <cstddef>
#include <cstdint>
#include <vector>

namespace internal {
class Codec final {
public:
    std::vector<std::uint8_t> encode(
            const std::uint8_t *data,
            std::size_t length) const;
};
}

#endif
```

**File `private_core.cpp`:**

```cpp
#include "private_core.hpp"

namespace internal {

std::vector<std::uint8_t> Codec::encode(
        const std::uint8_t *data,
        std::size_t length) const {

    std::vector<std::uint8_t> result(length);
    for (std::size_t i = 0; i < length; ++i) {
        result[i] = static_cast<std::uint8_t>(
                data[i] ^ static_cast<std::uint8_t>(0x5A));
    }
    return result;
}

}
```

The C++ core **is allowed** to use vectors, constructors/destructors, exceptions, and the standard library. It does not export those types to Java. In a real library, `Codec::encode` might perform serialization, image conversion, compression, or complex computation; the way bytes are exchanged through the public C header does not need to change just because an internal container is refactored.

A C++ vector can throw `std::bad_alloc` if it runs out of memory. The bridge must **catch** it and return a status instead of letting a C++ exception cross the JNI/C ABI.

## 8. File `bridge.cpp` — Measure Capacity, Write Accurately, Block C++ Exceptions

```cpp
#include "bridge.h"
#include "private_core.hpp"

#include <cstring>    // std::memcpy
#include <new>        // std::bad_alloc

extern "C" int xb_encode(
        const uint8_t *input,
        size_t input_length,
        uint8_t *output,
        size_t output_capacity,
        size_t *output_length) {

    if (output_length == nullptr) {
        return XB_INVALID_ARGUMENT;
    }
    *output_length = 0;

    if ((input_length > 0 && input == nullptr) ||
        (output_capacity > 0 && output == nullptr)) {
        return XB_INVALID_ARGUMENT;
    }

    // XOR algorithm preserves length, required = input_length.
    *output_length = input_length;
    if (output_capacity < input_length) {
        return XB_BUFFER_TOO_SMALL; // Do not write partial output.
    }
    if (input_length == 0) {
        return XB_OK; // Do not dereference input/output.
    }

    try {
        internal::Codec codec;
        std::vector<std::uint8_t> result =
                codec.encode(input, input_length);

        // Recheck if core changes length in the future.
        if (result.size() > output_capacity) {
            *output_length = result.size();
            return XB_BUFFER_TOO_SMALL;
        }

        std::memcpy(output, result.data(), result.size());
        *output_length = result.size();
        return XB_OK;
    } catch (const std::bad_alloc &) {
        *output_length = 0;
        return XB_NO_MEMORY;
    } catch (...) {
        *output_length = 0;
        return XB_INTERNAL_ERROR;
    }
}
```

Here, **`std::vector` is a local variable** and its destructor frees internal storage when the function returns. The C façade copies bytes to the **caller-owned output before the local vector's lifetime ends**. It does not return `result.data()` or memory carrying `std::vector`'s layout.

**Four invariants to check during code review:**

1. Do not dereference input when length=0.
2. Do not call core/copy if capacity is insufficient; `*output_length` holds required bytes so the caller can reallocate.
3. On success, write no more than capacity and write the actual byte count to `*output_length`.
4. Do not let `std::bad_alloc` or any C++ exception escape the exported C function.

In this example, the required query can be calculated as `input_length`, because XOR is **length preserving**. If the core is replaced with compression or serialization, **the query algorithm must be replaced** (e.g., `measure` or temporary encode) so that required is genuinely accurate; checking after encoding does not replace an accurate query contract.

**Limitation:** if the input pointer points to invalid memory, `catch(...)` does not protect against SIGSEGV/undefined behavior. The caller must still provide valid addresses, sizes, and lifetimes.

## 9. File `jni_bridge.cpp` — JNI Copy, RAII Cleanup, Java Exception

The JNI shim receives a Java `byte[]`, copies it to a native input buffer, calls the C façade using two passes, and copies the output into **a new `byte[]`**.

**File `jni_bridge.cpp`:**

```cpp
#include "NativeBufferDemo.h" // javac -h generates JNI prototype.
#include "bridge.h"

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <limits>
#include <memory>

static constexpr jsize MAX_INPUT = 1024 * 1024;

static void throw_if_no_pending(
        JNIEnv *env, const char *class_name,
        const char *message) {
    if (env->ExceptionCheck()) {
        return;
    }

    jclass type = env->FindClass(class_name);
    if (type != nullptr) {
        env->ThrowNew(type, message);
        env->DeleteLocalRef(type);
    }
}

static void throw_status(JNIEnv *env, int status) {
    if (status == XB_NO_MEMORY) {
        throw_if_no_pending(
                env, "java/lang/OutOfMemoryError",
                "native allocation failed");
    } else if (status == XB_INVALID_ARGUMENT) {
        throw_if_no_pending(
                env, "java/lang/IllegalArgumentException",
                "invalid native buffer argument");
    } else {
        throw_if_no_pending(
                env, "java/lang/IllegalStateException",
                "native buffer conversion failed");
    }
}

extern "C" JNIEXPORT jbyteArray JNICALL
Java_NativeBufferDemo_xorCopy(
        JNIEnv *env, jclass owner, jbyteArray input) {

    (void)owner;

    if (input == nullptr) {
        throw_if_no_pending(
                env, "java/lang/NullPointerException", "input");
        return nullptr;
    }

    const jsize java_length = env->GetArrayLength(input);
    if (env->ExceptionCheck()) {
        return nullptr;
    }
    if (java_length > MAX_INPUT) {
        throw_if_no_pending(
                env, "java/lang/IllegalArgumentException",
                "demo input exceeds 1 MiB");
        return nullptr;
    }

    const std::size_t n =
            static_cast<std::size_t>(java_length);

    using Buffer = std::unique_ptr<
            std::uint8_t, decltype(&std::free)>;

    Buffer source(static_cast<std::uint8_t *>(
            std::malloc(n == 0 ? 1 : n)), &std::free);

    if (!source) {
        throw_if_no_pending(
                env, "java/lang/OutOfMemoryError",
                "malloc input failed");
        return nullptr;
    }

    if (java_length > 0) {
        env->GetByteArrayRegion(
                input, 0, java_length,
                reinterpret_cast<jbyte *>(source.get()));
        if (env->ExceptionCheck()) {
            return nullptr; // unique_ptr frees source.
        }
    }

    std::size_t required = 0;
    const int query = xb_encode(
            source.get(), n, nullptr, 0, &required);

    if ((query != XB_OK && query != XB_BUFFER_TOO_SMALL) ||
        required != n) {
        throw_status(env, query);
        return nullptr;
    }

    if (required > static_cast<std::size_t>(
            std::numeric_limits<jsize>::max())) {
        throw_if_no_pending(
                env, "java/lang/IllegalArgumentException",
                "native output exceeds Java array size");
        return nullptr;
    }

    Buffer output(static_cast<std::uint8_t *>(
            std::malloc(required == 0 ? 1 : required)),
            &std::free);

    if (!output) {
        throw_if_no_pending(
                env, "java/lang/OutOfMemoryError",
                "malloc output failed");
        return nullptr;
    }

    std::size_t written = 0;
    const int status = xb_encode(
            source.get(), n,
            output.get(), required, &written);

    if (status != XB_OK || written != required) {
        throw_status(env, status);
        return nullptr;
    }

    jbyteArray result = env->NewByteArray(
            static_cast<jsize>(written));
    if (result == nullptr) {
        return nullptr; // OutOfMemoryError may be pending.
    }

    if (written > 0) {
        env->SetByteArrayRegion(
                result, 0, static_cast<jsize>(written),
                reinterpret_cast<const jbyte *>(output.get()));
        if (env->ExceptionCheck()) {
            return nullptr;
        }
    }

    return result; // source/output freed via RAII.
}
```

**Why does this code clean up resources properly?**

- `GetByteArrayRegion` **copies** from the Java array into a caller-allocated buffer; it is not a JNI lease like `GetByteArrayElements`, so there is **no `ReleaseByteArrayRegion`**.
- `std::unique_ptr` with deleter `std::free` properly manages allocations created by `std::malloc`. On early return or when a Java exception is pending, the destructor still performs cleanup.
- `NewByteArray` creates a Java-owned output; the JVM manages that object. JNI does not call `free` on a Java array.
- The JNI shim never accesses `std::vector` directly; it calls the C ABI `xb_encode` and only knows buffer/length/status.
- If a JNI call sets a pending exception, `throw_if_no_pending` does not mask the original error with a new exception. `DeleteLocalRef` is allowed to be called in the cleanup path when an exception is pending.
- `required == n` is an invariant specific to **XOR**; if the core changes to an algorithm with a different output length, the JNI client must be updated to use the exact required byte count (and retry policy).

The example sets an input limit of 1 MiB to avoid huge allocations in the lesson. Production should have memory limits, concurrent call limits, error policies, and cancellation appropriate for the workload.

## 10. File `NativeBufferDemo.java` — Caller Only Sees `byte[]`

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

public final class NativeBufferDemo {
    static {
        System.loadLibrary("bufferbridge");
    }

    private static native byte[] xorCopy(byte[] input);

    private static String hex(byte[] bytes) {
        return HexFormat.ofDelimiter(" ")
                .withUpperCase()
                .formatHex(bytes);
    }

    public static void main(String[] args) {
        byte[] input = {
                (byte) 0x41,
                (byte) 0x00,
                (byte) 0xFF
        };
        byte[] original = input.clone();

        byte[] encoded = xorCopy(input);
        byte[] decoded = xorCopy(encoded);

        System.out.println("input=" + hex(input));
        System.out.println("encoded=" + hex(encoded));
        System.out.println("decoded=" + hex(decoded));
        System.out.println("unchanged=" +
                Arrays.equals(input, original));
        System.out.println("emptyLength=" +
                xorCopy(new byte[0]).length);

        String text = "Cà phê";
        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
        System.out.println("utf16Units=" + text.length());
        System.out.println("utf8Bytes=" + utf8.length);
    }
}
```

`HexFormat` has been available since Java 17, so this code needs no external libraries. Java only knows **Java arrays**; it does not know C++ types, pointers, or allocators. The XOR demo is a binary operation, not cryptography.

## 11. Build and Run on Linux with JDK 17+ and C++17

Create the six listed files in the **same directory**:

```text
native-buffer-lab/
  NativeBufferDemo.java
  bridge.h
  bridge.cpp
  private_core.hpp
  private_core.cpp
  jni_bridge.cpp
  NativeBufferDemo.h   <-- generated by javac -h
  libbufferbridge.so   <-- generated by c++
```

Requires `JAVA_HOME` pointing to a JDK with `include/jni.h` and `include/linux/jni_md.h`, and a C++ compiler compatible with the JVM.

### Generate JNI header

```bash
javac -encoding UTF-8 -h . NativeBufferDemo.java
```

Because the Java class `NativeBufferDemo` is not placed in a package and the method is `static native byte[] xorCopy(byte[])`, the generated header declares a JNI entry named `Java_NativeBufferDemo_xorCopy`. If moving the class into a package, regenerate the header and update the implementation to the new symbol name; do not guess.

### Compile shared library

```bash
c++ -std=c++17 -O2 -Wall -Wextra -Wpedantic \
  -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libbufferbridge.so \
  private_core.cpp bridge.cpp jni_bridge.cpp
```

Although the exported façade uses a **C ABI**, the implementation has `std::vector` and C++ RAII, so use a **C++ compiler/linker**. `extern "C"` on `xb_encode` ensures the C-side name and language linkage, reusable from C callers/FFM. File `jni_bridge.cpp` additionally exports the JNI method `Java_NativeBufferDemo_xorCopy`.

### Run the application

```bash
java -Djava.library.path=. NativeBufferDemo
```

`-Djava.library.path=.` is a JVM option that must be placed **before** the main class name. `System.loadLibrary("bufferbridge")` looks for `libbufferbridge.so` on Linux. If the shared library depends on other native libraries, the OS loader must also find the corresponding dependencies; the Java classpath does not handle that.

### Expected stdout

```text
input=41 00 FF
encoded=1B 5A A5
decoded=41 00 FF
unchanged=true
emptyLength=0
utf16Units=6
utf8Bytes=8
```

Verification:
- `0x41 ^ 0x5A = 0x1B`, `0x00 ^ 0x5A = 0x5A`, `0xFF ^ 0x5A = 0xA5`.
- XORing with the same key twice returns the original bytes.
- `unchanged=true` because Java input is copied, not overwritten.
- `emptyLength=0` tests empty input and not dereferencing the pointer when length is 0.
- `"Cà phê"` has 6 UTF-16 code units and 8 UTF-8 bytes.

This is a **complete example designed to compile on Linux/JDK17+/C++17**, not the result of an actual build run across all environments. On macOS/Windows, the shared-library filename, compiler flags, and JNI platform include path must be changed.

## 12. Ownership: Who Allocates, Who Frees?

| Region | Owner | When to Free? | Must Not Do |
| --- | --- | --- | --- |
| `byte[] input` | JVM/Java | Per Java lifecycle | C `free` on Java array |
| `source` allocated with `malloc` in JNI shim | C++ `unique_ptr` during JNI call | Destructor calls `free` on return | Retain pointer after JNI call |
| Internal `std::vector` of `Codec` | C++ local object | C++ destructor when out of scope | Return `result.data()` to Java |
| `output` allocated with `malloc` in JNI shim | C++ `unique_ptr` | Destructor calls `free` | C façade freeing caller's buffer |
| `byte[] result` created via JNI `NewByteArray` | Java/JVM | Per Java lifecycle | C `free` on result |
| `input`/`output` of `xb_encode` | Caller of C façade | Per caller's owner | Callee retaining/freeing after return |
| `output_length` | Caller providing address of `size_t` | Per caller's lifetime | Retain pointer after return |

JNI `GetByteArrayRegion` and `SetByteArrayRegion` are **copy operations**, not creating a JNI pinned array lease that requires `ReleaseByteArrayElements`. Conversely, if choosing `GetByteArrayElements` to get a pointer to access the array, you **must** call `ReleaseByteArrayElements` regardless of whether `isCopy` reports true or false. Do not use `free` on a JVM-provided pointer.

When the C façade needs to allocate output itself and transfer ownership to Java, there must be a matching `xb_free` / `destroy` API published by the same library, a Java `AutoCloseable` wrapper, or an appropriate owner protocol. Never let Java arbitrarily call `free` on memory from C++ `new[]` or a custom allocator.

## 13. Alternative Designs When Output Is Complex

### A. Caller buffer + length (currently used)

```c
int transform(const uint8_t *in, size_t in_len,
              uint8_t *out, size_t cap, size_t *written);
```

**Pros:** does not export C++ types; caller decides buffer allocation/pooling/reuse. **Cons:** may need a two-pass query; caller must handle insufficient capacity.

### B. Callee allocation + explicit free

```c
/* Illustrative alternative API; not implemented in this article. */
int transform_alloc(const uint8_t *in, size_t len,
                    uint8_t **out, size_t *out_len);
void transform_free(uint8_t *out);
```

**Pros:** callee can allocate the exact size once. **Cons:** caller must hold ownership and call `transform_free` exactly once; missing it causes a leak, calling it early/twice causes UAF/double-free. The API must document error cases (on error, is `*out==NULL` or has ownership been transferred?).

### C. Streaming/chunk callback

```c
typedef int (*on_chunk_fn)(
        void *context, const uint8_t *bytes, size_t length);

int transform_stream(const uint8_t *in, size_t len,
                     on_chunk_fn on_chunk, void *context);
```

**Pros:** avoids holding huge output in RAM; can emit chunk by chunk. **Cons:** callback ABI, error propagation, concurrency, reentrancy, and lifetime complexity. The chunk pointer is usually **borrowed only during the callback**, so if needed later it must be copied.

### D. Opaque handle for stateful C++ object

```c
typedef struct xb_session xb_session;

int xb_session_create(xb_session **out);
int xb_session_process(xb_session *session,
                       const uint8_t *input, size_t length,
                       uint8_t *output, size_t capacity,
                       size_t *written);
void xb_session_destroy(xb_session *session);
```

**Pros:** can keep private C++ class state behind a C handle; still passes data via buffer+length. **Cons:** requires create/destroy, ownership, thread-safety, synchronization, and lifecycle protocol. Do not dereference an incomplete C type from Java.

## 14. Using Java 22+ FFM with the Same C ABI

FFM `java.lang.foreign` was finalized in **JDK 22** (JEP 454). Given `bridge.h`, Java 22+ can call `xb_encode` directly using `Linker.downcallHandle` without a JNI shim. However, **the public API model does not change**: Java still sees C pointers, sizes, and statuses; it never sees `std::vector`.

On Linux x86-64 (64-bit C `size_t`), an illustrative descriptor:

```java
// Illustrative snippet in Java 22+, not a complete class.
import java.lang.foreign.FunctionDescriptor;
import static java.lang.foreign.ValueLayout.*;

FunctionDescriptor xbDesc = FunctionDescriptor.of(
        JAVA_INT,   // C int return status
        ADDRESS,    // const uint8_t* input
        JAVA_LONG,  // size_t input_length (Linux x86-64)
        ADDRESS,    // uint8_t* output
        JAVA_LONG,  // size_t output_capacity
        ADDRESS     // size_t* output_length
);
```

The corresponding Java carrier type is typically `(MemorySegment,long,MemorySegment,long,MemorySegment)int`. To actually run, you need `SymbolLookup` to obtain the `xb_encode` symbol, `Linker.downcallHandle`, an arena to allocate native buffers (including space for `size_t output_length`), copy input, `invokeExact`, read status/required/written, and copy valid output back to Java. Restricted native access operations require flags like `--enable-native-access=ALL-UNNAMED` on the classpath when appropriate.

**Do not assume `size_t == Java long` on all architectures.** On 32-bit ABIs, `size_t` may be 32 bits; check linker canonical layouts and the target ABI. `MemorySegment` has scope/bounds, but if C retains a raw pointer after the arena closes, it can still cause a crash. If only calling C synchronously and not retaining pointers, `Arena.ofConfined()` can manage native input/output buffers and close after the downcall.

Java 17 does not compile the finalized FFM snippet above: the **runnable Java17+** practice above uses JNI instead.

## 15. Text, Binary, and Serialization: Length Is Not Enough Without a Format Contract

A byte region may contain UTF-8 text, compressed data, a serialized C struct, or arbitrary binary. The contract needs to describe the **format**, not just the size:

- **Text:** encoding (UTF-8, UTF-16LE, Latin-1...), invalid sequence policy, embedded NUL, presence/absence of trailing terminator.
- **Integer data:** little/big-endian byte order, signedness, width; do not assume C `long` is the same on Windows/Linux.
- **Records/structs:** field order, type, alignment, packing, version, length of variable-sized fields.
- **Binary protocol:** magic/version header, payload length, checksum if needed, max size.
- **Strings from C++:** `std::string` is just a byte container; it does not implicitly promise valid UTF-8.

Do not copy the raw bytes of a `std::string` object (the object's metadata) as a wire format; copy **`s.data()` for `s.size()` bytes while the object is alive**. Likewise, do not copy a `std::vector` object; only copy `v.data()` for `v.size() * sizeof(element)` when elements have a defined binary format, considering padding/endianness if not bytes.

If a C++ API handles protobuf/JSON or versioned structures, expose **serialized bytes + length**, letting Java use an appropriate parser/codec. This avoids long-term coupling to C++ class layout.

## 16. Protecting Against Size Overflow and Untrusted Data

Native-side errors are more severe than a normal Java exception: out-of-bounds C memory access can corrupt the heap or crash the JVM.

**Check before casting Java length:**

```cpp
// Illustration in JNI with required of type size_t.
if (required > static_cast<std::size_t>(
        std::numeric_limits<jsize>::max())) {
    // Java array cannot hold this length.
    return nullptr; // Must report appropriate Java error.
}
```

For size calculations:

```c
/* Illustration: header + payload, using size_t. */
if (payload_bytes > SIZE_MAX - header_bytes) {
    return XB_INVALID_ARGUMENT;
}
size_t required = header_bytes + payload_bytes;
```

For element counts: check `count <= SIZE_MAX / element_size` before `count * element_size`. `size_t` to `jsize`/Java `int` should be validated before casting to avoid truncation. Do not trust an untrusted input claiming compressed/decompressed output needs several GiB and allocate unconditionally; set a **memory budget** and check maximum size. With signed/unsigned mixing, avoid comparing a negative number cast to a huge positive number.

**Exceptions:** `catch(...)` handles C++ exceptions; it does not turn a SIGSEGV/undefined behavior from an invalid pointer into a safe Java exception. Root causes must still be prevented via pointer bounds/lifetime, format validation, and native memory sanitizers in tests.

## 17. Recording Errors in Status Instead of Throwing C++ Exceptions Across the Boundary

An exported C API should have a stable error policy:

| Status | When | `output_length` per Demo Contract |
| --- | --- | --- |
| `XB_OK` | Write succeeded / valid empty output | Number of bytes written |
| `XB_BUFFER_TOO_SMALL` | Caller buffer lacks capacity | Number of bytes needed to retry |
| `XB_INVALID_ARGUMENT` | Invalid pointer/length/null combination | 0 if `output_length` is non-null |
| `XB_NO_MEMORY` | C++ `std::bad_alloc` | 0 |
| `XB_INTERNAL_ERROR` | Other C++ exception | 0 |

Benefit: the Java client can map status to Java `IllegalArgumentException`, `OutOfMemoryError`, or `IllegalStateException` per policy. A valid empty result is not mistaken for a failure just because length=0.

**Never** return the `std::exception::what()` pointer of a temporary exception to Java and use it after the catch block ends. If diagnostic text is needed, provide a separate **buffer+length error-message API**, or log/return error codes with an explanation table. Separating the error channel from the data channel makes testing more accurate.

## 18. Concurrent Calls and Async Ownership

If the C++ core has shared mutable state, it must be synchronized; merely having a buffer+length API **does not make the library thread-safe**. If the caller concurrently writes to input while the callee is reading, that is a native-side data race or data consistency bug. A read-only input contract only restricts **callee** behavior; it does not protect against the caller modifying the buffer mid-call.

For **synchronous** calls, it is simplest:

```text
Caller owns input/output
    |
    +-- calls C API
           |
           +-- callee borrows pointers
           +-- processes/copies result
           +-- returns status
    |
Caller can reuse or free buffers after return
```

If an **asynchronous** API retains pointers after returning, the entire contract must change:

- Who keeps the allocation alive until the final callback completes?
- Is there `retain/release`, an opaque handle, task completion, or a cancel/await API?
- Does C need to copy input before returning?
- When may the caller free/reuse output?
- Can the pointer be used from another thread?
- Does the C++ library/unload/native callback pointer stay alive until completion?

Never pass a JNI `GetByteArrayElements` pointer and return without Releasing, or keep a pointer into a closed FFM arena for a native worker. With async, it is usually necessary to **copy into a native-owned buffer with an explicit owner** or use a shared arena and a coordinator waiting for in-flight work to finish.

## 19. Performance: Should Every Copy Be Avoided?

The demo example performs multiple copies:

```text
Java byte[] 
   -> GetByteArrayRegion -> native input
   -> std::vector (XOR)
   -> memcpy -> native output
   -> SetByteArrayRegion -> Java byte[]
```

This is not zero-copy. However, lifetime, ownership, and error handling are simple, which can work very well for small/medium payloads.

Optimization directions **without exposing internal types**:

1. Reuse native output buffers with a clear owner/pool to reduce malloc/free.
2. When output size is known in advance (like XOR), skip the two-pass query and allocate once based on input length.
3. Have the C++ core write directly into the caller-owned output buffer; the public C ABI remains the same.
4. With C++20, use `std::span<std::byte>` **internally**, without exporting `span` across the C ABI.
5. Use FFM native memory segments/DirectByteBuffer with explicit lifetimes if throughput genuinely requires zero-copy.
6. Use streaming/chunks when payloads are too large.
7. Batch multiple small calls to reduce JNI/FFM crossing overhead.

Do not optimize by intuition. Measure throughput, P95/P99 latency, allocation rate, RSS, and total C++/Java conversion time before paying the price of ownership complexity. A single UAF/double-free bug is usually more expensive than a few copies.

## 20. Negative Testing Matrix

### C façade

| Input | Expected Status |
| --- | --- |
| `input=NULL`, `input_length=0`, query output | `XB_OK`, required=0 |
| `input=NULL`, `input_length>0` | `XB_INVALID_ARGUMENT` |
| `output_length=NULL` | `XB_INVALID_ARGUMENT` |
| `output=NULL`, cap=0, length=3 | `XB_BUFFER_TOO_SMALL`, required=3 |
| Output cap=2, required=3 | `XB_BUFFER_TOO_SMALL`, no partial-write |
| Output cap=3, required=3 | `XB_OK`, written=3, correct bytes |
| Bytes containing `00`, `FF` | No truncation, correct output length |
| C++ core throws `std::bad_alloc` | `XB_NO_MEMORY`, no exception crosses C ABI |
| Core throws another exception | `XB_INTERNAL_ERROR` |
| Invalid pointer or lying size | **Caller contract violation**; do not test in production JVM |

### Java/JNI

| Test | Expectation |
| --- | --- |
| `xorCopy(new byte[0])` | Java output length 0 |
| `xorCopy(new byte[]{0, -1})` | Both bytes processed, no NUL truncation |
| `xorCopy(null)` | `NullPointerException` |
| Input longer than 1 MiB | `IllegalArgumentException` |
| JNI array creation fails due to low memory | Preserves pending Java exception, RAII cleans up buffers |
| Run multiple times | Does not retain native input/output pointers after return |
| Multiple Java threads calling concurrently | Demo core holds no shared mutable state |
| Vietnamese text test | UTF-8 byte length obtained from `getBytes(UTF_8)`, not `String.length()` |

When possible, run the JVM with `-Xcheck:jni` and test native code with AddressSanitizer/UndefinedBehaviorSanitizer. A single correct stdout run does not prove all allocation, race, or overflow bugs have been tested; appropriate fault injection and load testing are needed.

## 21. Checklist for Designing a C++ Wrapper for Java

- [ ] Public C header contains no `std::string`, `std::vector`, templates, C++ references, or C++ exceptions.
- [ ] `extern "C"` is properly declared for function symbols, readable by both C and C++ headers.
- [ ] Input has pointer + length **in bytes**; output has pointer + capacity + required/written count.
- [ ] Do not use NUL terminator for binary data; text APIs publish their own encoding/NUL policy.
- [ ] Caller/callee ownership is clear; callee does not retain/free borrowed buffers.
- [ ] Size query has exact semantics; insufficient capacity writes no partial output.
- [ ] If the result can change between query and fill, there is a retry/snapshot/version protocol.
- [ ] Check null/zero-length and size/offset overflow before dereferencing/casting.
- [ ] C++ exceptions are caught and converted to C status, never crossing JNI/FFM.
- [ ] Native temporary buffers have RAII/cleanup on all error branches.
- [ ] If callee allocates output itself, there is a matching destroy API and matching allocator/module.
- [ ] Do not return pointers to expired C++ local vectors/strings.
- [ ] Struct/object data is serialized/versioned or uses a C-compatible layout with ABI review.
- [ ] FFM/JNI conversions agree on C types, byte width, alignment, and target OS/ABI.
- [ ] Memory/CPU budgets exist for untrusted lengths and large payloads.
- [ ] Async/native callbacks do not retain pointers beyond lifetime and have a mechanism to await completion.
- [ ] Benchmarked before optimizing for zero-copy.
- [ ] Unit/native tests exist for empty, NUL, FF, short capacity, null, OOM, unicode, and concurrency.
- [ ] Generated JNI headers and native library binary are built for the target OS/architecture.
- [ ] The C header is a **versioned contract**; the C++ implementation can change without exposing internals.

## 22. Self-Check Questions

**1. Why doesn't `extern "C" std::vector<uint8_t> encode(...)` create a safe Java API?**

Because `extern "C"` only controls language linkage; it does not create a C-compatible layout/allocator/destructor contract for `std::vector`. Java cannot decode a vector object and does not know how to destroy it. Use a C façade with buffer+length.

**2. If we already have `output_length`, why do we still need `output_capacity`?**

`output_capacity` is the write limit **allocated by the caller**; `output_length` is the number of bytes the callee **needs or has written**. Failing to compare them before copying risks a buffer overflow.

**3. Why are two passes needed for output of unknown size?**

The query pass returns the required size so the caller can allocate enough, and the fill pass writes bytes into the caller's buffer. However, if input/state changes between the two passes, you must use a snapshot/bounded retry or a streaming design.

**4. Does `input={0x41,0x00,0xFF}` have length 1 byte because NUL appears at position 2?**

No. The binary input is **3 bytes** long. Only C string operations like `strlen` stop at NUL; binary APIs use explicit length.

**5. Does JNI `GetByteArrayRegion` need `ReleaseByteArrayRegion`?**

No. It **copies** into a caller-provided buffer and does not create a JNI lease. `GetByteArrayElements` requires a matching `ReleaseByteArrayElements`.

**6. If the C++ core returns `result.data()` of a local `std::vector`, can it be used after the C function returns?**

No. When the vector is destroyed, the pointer becomes invalid. Copy into a caller-owned buffer before the local vector goes out of scope, or create an explicit callee-allocated output + matching free API.

**7. Why isn't `String.length()` the UTF-8 buffer length?**

Java counts UTF-16 code units, whereas UTF-8 has a different byte count. `"Cà phê"` has 6 UTF-16 units but 8 UTF-8 bytes.

**8. Does C++ `std::bad_alloc` automatically become Java `OutOfMemoryError`?**

Do not rely on that. Catch it at the C façade, return status `XB_NO_MEMORY`, and have the JNI shim proactively raise a Java error if no exception is pending.

**9. If `size_t` is 64-bit but `jsize` is 32-bit, what should be done?**

Check that required/output size does not exceed `jsize::max` **before** casting; overflow and signed/unsigned conversions must be validated. FFM mappings must also follow the target ABI.

**10. Does using a buffer+length C façade guarantee no crashes from bad pointers?**

No. It helps express the contract more clearly, but C cannot verify that a pointer actually has enough bytes and is still alive. The caller must guarantee allocation, bounds, lifetime, and thread-safety.

**11. If a C++ class has long-lived state, must its class layout be exposed?**

No. Use an **opaque C handle** with create/process/destroy, and keep bytes going in/out via buffer+length. Clear owner/thread lifecycles are needed.

**12. Can Java 17 use the finalized FFM `java.lang.foreign` directly?**

No; the runnable Java17+ code in this article is JNI. FFM was finalized in JDK 22; Java 17 has an incubator with a different API.

## 23. Reference Sources

- Oracle JNI Specification — [Get/Set Primitive Array Region and managing byte buffers](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#getprimitivetypearrayregion-routines).
- Oracle JNI Specification — [Array operations, Get/Release array elements](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#array-operations).
- Oracle Java 17 — [`HexFormat`, `ofDelimiter` and `withUpperCase`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html).
- cppreference — [C++ language linkage and `extern "C"`](https://en.cppreference.com/w/cpp/language/language_linkage).
- cppreference — [`std::vector` and managing contiguous storage](https://en.cppreference.com/w/cpp/container/vector).
- Oracle Java 22 — [FFM Linker and C ABI downcalls](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html).
- Oracle Java 22 — [FFM Arena and memory lifetime](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html).
- OpenJDK — [JEP 454: FFM API finalized in JDK 22](https://openjdk.org/jeps/454).

**Conclusion:** when wrapping a C++ library for Java, keep `std::vector`/`std::string`/C++ classes **completely internal**. Publish a **simple C ABI with input pointer+byte length, output pointer+capacity, actual/required length, and status**; check null/size/overflow, catch C++ exceptions in the bridge, and ensure ownership/lifetime of all buffers. This works across both JNI and FFM and avoids tying the Java API to the changing layout of a C++ implementation.
