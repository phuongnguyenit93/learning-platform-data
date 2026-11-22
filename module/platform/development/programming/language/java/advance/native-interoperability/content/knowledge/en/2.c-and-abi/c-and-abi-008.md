# Representing Error Codes, Sentinel Values, and Memory Ownership in C Contracts

When Java calls a native library via JNI or the Foreign Function & Memory API (FFM), the C/ABI boundary must clearly specify **how success or failure is represented**, **which values are valid data**, and **who must free which memory region, and when**. A non-`NULL` pointer does not prove an operation succeeded; a `-1` code may be a sentinel or normal data depending on the contract. If Java misunderstands this convention, the consequences can be misreported errors, memory leaks, double free, use-after-free, or a JVM crash.

This article focuses on designing, reading, and mapping **C contracts and ABIs**; runnable examples include a C library, a C program, and Java 22+ using FFM. JNI follows the same principles regarding status and ownership, even though the API manages its own resources.

## 1. Distinguishing Results, Error States, and Ownership Obligations

Every function across the ABI should be able to answer five questions:

1. **Input conditions:** which parameters can be `NULL`, does a pointer need to point to a valid memory region, does the string use UTF-8 or another encoding, and does the length include the NUL byte?
2. **Success rules:** which return code indicates success, and under what conditions do the output parameters hold valid values?
3. **Failure rules:** is the error code represented by `int32_t`, `errno`, a sentinel value, or a combination? How can an error message be retrieved?
4. **Memory lifetime:** does the data belong to the caller or the library; who allocates, who frees, which function frees it, and can it be retained after the call ends?
5. **ABI stability:** are type sizes, calling convention, encoding, error code values, and symbol names stable across versions and platforms?

`ABI` describes how functions, parameters, data types, and memory layouts are exchanged at the binary level. Signatures that look identical in C do not guarantee arbitrary mapping to Java: `int32_t` is 32 bits; `size_t` is architecture-dependent; pointers have process-dependent width; `long` can differ between Linux x64 (LP64) and Windows x64 (LLP64).

## 2. Common Ways to Represent Errors

| Convention | Illustration | Advantages | What Must Be Specified |
| --- | --- | --- | --- |
| Status code + output parameter | `int32_t api_read(..., size_t *out_n)` | Data and errors do not collide | Status values; state of `out_n` on error |
| Sentinel value | Function returns `NULL` or `-1` | Fewer parameters, common in traditional APIs | Whether the sentinel belongs to the valid data domain; where to look up error details |
| `errno` accompanying error result | POSIX `read()` returns `-1` | Rich system error descriptions | Only read `errno` per the function contract and after determining the call failed |
| Result struct | `{status, value}` | Can carry multiple fields | Layout, padding, alignment, and ABI rules of the struct |
| Status + callback/message | `api_last_error()` | Deeper error explanation | Message memory, thread-safety, when the message is overwritten |

For a new C API serving Java, an easy-to-manage approach is a **dedicated, fixed status code + output parameter**. For example: `0` success; `1` invalid argument; `2` out of memory; `3` size limit exceeded. Define numbers explicitly; do not change numbers when adding states; the caller must be able to handle unknown codes from newer library versions.

A good contract may specify: if the output pointers are valid but the operation fails, `*out_ptr = NULL` and `*out_len = 0`; only when the status is success may the output be used. If the output pointer itself is `NULL`, the function returns an error without being able to write to that address. Never dereference uninitialized output.

### 2.1. `errno` Is Not a Universal Error Code for Every Library

In C/POSIX, `errno` is an error-reporting mechanism used by many standard APIs, usually with per-thread state. However, not every C function sets `errno` on failure, and a non-zero `errno` value **does not by itself prove** that the call just failed. You must check the sentinel/status described by that specific function first, then read/copy `errno` immediately while it is still relevant; another library call can alter it. Do not rely on `errno` if the API contract does not promise to use it.

POSIX example (not pure ISO C): `read(fd, buf, count)` returns the number of bytes read on success, `0` for EOF, and `-1` to indicate an error; only on `-1` is `errno` used to identify the cause. The byte count can be less than `count` and still be a success.

The `strtol()` function illustrates another trap: values `0`, `LONG_MIN`, or `LONG_MAX` can appear in both valid and error situations depending on the case. You need to examine `endptr`, `errno == ERANGE` (after setting `errno = 0` before the call), and the input conditions; do not treat every `0` result as an error.

## 3. Sentinel: Distinguishing “No Value” from “Error Encountered”

A **sentinel** is a reserved value used to convey a special signal. It is only safe when its meaning is unambiguous within the context of the contract.

| Sentinel | Context | Safe Interpretation |
| --- | --- | --- |
| `NULL` | Function returning a pointer | May mean error, not found, absent optional, or empty result; must read the contract |
| `-1` | Function returning an integer | Only an error if `-1` is excluded from the valid data domain or there is an additional error channel |
| `SIZE_MAX` or `(size_t)-1` | Size/index | This is also a valid `size_t` value; avoid using as “not found” if the data domain includes it |
| `EOF` | `fgetc()` in stdio | An `int` value outside the `unsigned char` range; use `feof()`/`ferror()` to distinguish the cause |
| `MAP_FAILED` | POSIX `mmap()` | Specific sentinel, usually `(void *)-1`; check `MAP_FAILED`, not `NULL` |

Do not mix the two questions “was it found?” and “did the operation fail?” into the same sentinel when they have different handling paths. If a function needs to return a valid negative value, use `status + out_value`. For lookup, you can separate `API_OK` + `out_found` + `out_value`, or define a dedicated “not found” code; choose one and describe it clearly.

## 4. Ownership and Memory Lifetime

In native interoperability, **ownership** is the responsibility to maintain and release a resource, not merely read/write permission. `const char *` states that data is not modified through that pointer; it **does not** by itself state who owns it, how long the data lives, or whether `free()` must be called.

| API Form | Who Owns the Memory | What Can the Caller Do? | When Does It Expire? |
| --- | --- | --- | --- |
| Borrowed input: `const char *name` | Caller | Library only reads during the call, does not retain it without agreement | Caller controls; must stay alive throughout the call |
| Borrowed output: `const char *api_status_text(code)` | Library/static | Read; do not free, do not write; copy if long-term retention is needed | Per contract (e.g., static until process ends) |
| Owned output: `char **out_message` | Library transfers ownership to caller on success | Read, then call the exact published release function | From creation until a single release |
| Caller-provided buffer: `char *buf, size_t cap` | Caller | Library writes up to capacity, clearly stating NUL/length | Per caller buffer lifetime |
| Ownership transfer into library | Library receives ownership after a successful call | Caller must no longer use/free after the transfer point | Per specific specification |

Situations requiring special care:

- **Allocator/deallocator must be paired.** Memory created by the library's internal allocator should be returned via the library's own `api_free()`. Do not arbitrarily call `free()` from another runtime on Windows, C++ `delete`, `Unsafe.freeMemory()`, or close a Java `Arena` to free memory that the library `malloc()`'d.
- **Do not return the address of a local stack variable.** The memory region becomes invalid as soon as the C function returns, even though the pointer is non-`NULL`.
- **Do not retain a borrowed pointer past its lifetime.** This includes Java buffers passed into native code, pointers to already-released objects, or pointers to a library cache region that may change on the next call.
- **One ownership, one release.** Reset a local pointer to `NULL` after freeing if it may still be referenced; avoid double free. When a result consists of multiple pointers, a destructor for the entire structure must be specified.
- **Lifetime and thread-safety are two different things.** A static pointer may live long, yet the data can still be mutated concurrently; documentation must clearly state whether concurrent reading/calling from multiple threads is safe.

With Java FFM, `Arena` automatically manages **allocations created by the arena**. It does not inherently know how to reclaim pointers allocated and returned by a C library. With JNI, pairs like `GetStringUTFChars/ReleaseStringUTFChars` or `GetByteArrayElements/ReleaseByteArrayElements` are separate resource-management contracts and do not replace the C library's release function.

## 5. Designing a C ABI Callable from Java

The example below illustrates an API that creates the string `"Hello, " + name`. To separate errors from data, the function returns an `int32_t` status and outputs `char *` and the number of **bytes** via two out parameters. Success transfers ownership of the string to the caller; failure does not transfer ownership. `name` is a NUL-terminated UTF-8 string, alive at least for the duration of the call, and does not contain intentional embedded NULs. `out_length` excludes the trailing NUL byte.

### 5.1. Public Header: `demo_api.h`

```c
#ifndef DEMO_API_H
#define DEMO_API_H

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32)
#  if defined(DEMO_BUILD)
#    define DEMO_API __declspec(dllexport)
#  else
#    define DEMO_API __declspec(dllimport)
#  endif
#else
#  define DEMO_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

enum {
    API_OK = 0,
    API_EINVAL = 1,
    API_ENOMEM = 2,
    API_EOVERFLOW = 3
};

/*
 * Returns API_OK on success.
 * name: borrowed, valid NUL-terminated UTF-8 for this call.
 * out_message/out_length: required non-NULL pointers.
 * On success: *out_message is owned by caller and must be
 *              released once with api_free(); length excludes NUL.
 * On failure with valid out pointers: *out_message = NULL,
 *              *out_length = 0; nothing to free.
 * Thread-safe; no shared mutable state in this implementation.
 */
DEMO_API int32_t api_make_message(
    const char *name, char **out_message, size_t *out_length);

/* Accepts NULL; valid only for pointers returned as owned by this API. */
DEMO_API void api_free(void *p);

/* Returns borrowed, immutable, static-lifetime text; never free. */
DEMO_API const char *api_status_text(int32_t status);

#ifdef __cplusplus
}
#endif
#endif
```

Note: status has fixed numbers, `extern "C"` preserves C symbol naming when the header is included from C++, and the export macro handles symbols in a shared library. The header is the **public contract**; changing the allocation method or status meaning without updating callers is a compatibility bug.

### 5.2. Implementation: `demo_api.c`

```c
#include "demo_api.h"

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

int32_t api_make_message(
    const char *name, char **out_message, size_t *out_length) {

    if (out_message == NULL || out_length == NULL) {
        return API_EINVAL;
    }

    *out_message = NULL;
    *out_length = 0;

    if (name == NULL) {
        return API_EINVAL;
    }

    static const char prefix[] = "Hello, ";
    const size_t prefix_len = sizeof(prefix) - 1;
    const size_t name_len = strlen(name);

    if (name_len > SIZE_MAX - prefix_len - 1) {
        return API_EOVERFLOW;
    }

    const size_t total_len = prefix_len + name_len;
    char *result = malloc(total_len + 1);
    if (result == NULL) {
        return API_ENOMEM;
    }

    memcpy(result, prefix, prefix_len);
    memcpy(result + prefix_len, name, name_len);
    result[total_len] = '\0';

    *out_message = result;
    *out_length = total_len;
    return API_OK;
}

void api_free(void *p) {
    free(p);
}

const char *api_status_text(int32_t status) {
    switch (status) {
        case API_OK:        return "ok";
        case API_EINVAL:    return "invalid argument";
        case API_ENOMEM:    return "out of memory";
        case API_EOVERFLOW: return "size overflow";
        default:           return "unknown status";
    }
}
```

Here, `strlen()` is only safe because the precondition requires `name` to point to a valid NUL-terminated C string. Checking `name != NULL` cannot prove that an arbitrary pointer is valid. The `SIZE_MAX - prefix_len - 1` check prevents length addition from overflowing `size_t` before allocation. Setting outputs to empty before error branches prevents the caller from accidentally reading a garbage pointer; both output pointers must be valid.

Do not swap `malloc()` for another allocator and tell the caller to call `free()` in the documentation: the caller only knows the stable rule `api_free()`. `api_status_text()` returns a static string literal: it is **not** owned by the caller.

### 5.3. C Caller: `demo_client.c`

```c
#include "demo_api.h"

#include <inttypes.h>
#include <stdio.h>

int main(void) {
    char *message = NULL;
    size_t byte_count = 0;

    int32_t status =
        api_make_message("Java", &message, &byte_count);

    if (status != API_OK) {
        fprintf(stderr, "error=%s\n", api_status_text(status));
        return 1;
    }

    printf("status=%" PRId32 "\n", status);
    printf("bytes=%zu\n", byte_count);
    printf("text=%s\n", message);

    api_free(message);
    message = NULL;
    return 0;
}
```

Compile and run on Linux/macOS with a C11 compiler (the executable directly uses the two source files):

```bash
cc -std=c11 -Wall -Wextra -Wpedantic demo_api.c demo_client.c -o demo_client
./demo_client
```

Exact output with input `"Java"` (7 bytes `"Hello, "` + 4 bytes `"Java"`):

```text
status=0
bytes=11
text=Hello, Java
```

Even if the caller encounters an exception or must exit early on another branch, it must still pass every pointer whose ownership it received to `api_free()` exactly once. In C, use a unified cleanup structure (e.g., a `cleanup:` label) when multiple exit paths need to release resources.

## 6. Calling the Above ABI from Java Using FFM (JDK 22+, Linux x64)

Java FFM provides `Linker`, `SymbolLookup`, `FunctionDescriptor`, and `MemorySegment` to call C functions directly. This example intentionally targets **Linux 64-bit**, where `int32_t` matches `JAVA_INT`, and `size_t` and pointers are 8 bytes; `size_t *` is read using `JAVA_LONG`. If running on a different ABI, re-verify all layouts and shared library paths before use.

First, build the shared library from the same C source:

```bash
cc -std=c11 -fPIC -shared -DDEMO_BUILD demo_api.c -o libdemo_api.so
```

File `DemoFFM.java`:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.invoke.MethodHandle;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

import static java.lang.foreign.ValueLayout.*;

public class DemoFFM {
    public static void main(String[] args) throws Throwable {
        try (Arena arena = Arena.ofConfined()) {
            Linker linker = Linker.nativeLinker();
            SymbolLookup lib = SymbolLookup.libraryLookup(
                Path.of("libdemo_api.so").toAbsolutePath(), arena);

            MethodHandle make = linker.downcallHandle(
                lib.find("api_make_message").orElseThrow(),
                FunctionDescriptor.of(
                    JAVA_INT, ADDRESS, ADDRESS, ADDRESS));
            MethodHandle release = linker.downcallHandle(
                lib.find("api_free").orElseThrow(),
                FunctionDescriptor.ofVoid(ADDRESS));

            MemorySegment input = arena.allocateFrom("Java");
            MemorySegment ptrSlot = arena.allocate(ADDRESS);
            MemorySegment lenSlot = arena.allocate(JAVA_LONG);
            ptrSlot.set(ADDRESS, 0, MemorySegment.NULL);
            lenSlot.set(JAVA_LONG, 0, 0L);

            int status = (int) make.invokeExact(
                input, ptrSlot, lenSlot);
            if (status != 0) {
                throw new IllegalStateException(
                    "Native status=" + status);
            }

            MemorySegment nativePtr = ptrSlot.get(ADDRESS, 0);
            long byteCount = lenSlot.get(JAVA_LONG, 0);

            try {
                if (nativePtr.equals(MemorySegment.NULL)
                        || byteCount < 0
                        || byteCount > Integer.MAX_VALUE) {
                    throw new IllegalStateException(
                        "Native result violates the ABI contract");
                }

                // The returned ADDRESS has unknown bounds.
                // Trust the documented length only while the allocation lives.
                byte[] bytes = nativePtr.reinterpret(byteCount)
                    .toArray(JAVA_BYTE);

                System.out.println("status=" + status);
                System.out.println("bytes=" + byteCount);
                System.out.println("text=" +
                    new String(bytes, StandardCharsets.UTF_8));
            } finally {
                // The C library owns the allocator and exports the release.
                release.invokeExact(nativePtr);
            }
        }
    }
}
```

Run with JDK 22+ in the directory containing `libdemo_api.so`:

```bash
javac DemoFFM.java
java --enable-native-access=ALL-UNNAMED DemoFFM
```

The result matches the C program: status `0`, length `11` bytes, and string `Hello, Java`. `Arena` frees `input`, `ptrSlot`, and `lenSlot` allocated by Java; `api_free(nativePtr)` **separately** frees the string allocated by the C library. A pointer retrieved from native memory is typically represented as a `MemorySegment` of length 0 because Java does not inherently know its size; only `reinterpret(byteCount)` while the allocation is alive allows copying the exact number of bytes. A `reinterpret` with the wrong size can cause memory access errors, so the length must be a trustworthy part of the contract.

Use `try/finally` to release even if string decoding or Java processing throws an exception. Check status **before** using the output. The example uses 64-bit native `size_t`; do not copy this `JAVA_LONG` descriptor to a 32-bit process. On Windows, a corresponding DLL and matching ABI are needed; on macOS, a library with the `.dylib` extension is needed.

### 6.1. If Using JNI Instead of FFM

The same C API still needs status and ownership as above. JNI typically has a `native` layer that converts status into a Java exception, then returns managed data. When JNI obtains a copy or pins a Java string/array using JNI functions, the corresponding `Release...` function must be called. In particular, `GetStringUTFChars()` / `NewStringUTF()` use JNI's **Modified UTF-8**; it is not completely identical to standard UTF-8 in a C ABI, especially regarding NUL and supplementary Unicode characters. Specify the encoding conversion explicitly rather than implicitly assuming the two formats are the same.

If JNI calls `api_make_message()`, the bridge layer should: prepare input in the proper encoding → call C → check status → convert/copy content into a Java object → free the C pointer via `api_free()` in all valid branches. Do not store a raw C pointer in a Java `long` without clearly designing handles, synchronization, and closing time.

## 7. Design Smells That Easily Lead to Incidents

| Error Smell | Why It Is Dangerous | How to Fix |
| --- | --- | --- |
| Returning `-1` when `-1` is also valid data | Cannot distinguish result from error | Separate status and out parameter |
| Only checking `errno != 0` | `errno` may be a leftover value from a previous call | Detect failure per the contract first, then read `errno` |
| Dereferencing output when status is error | Out parameter may not be valid yet | Initialize output consistently; only read on success |
| Treating `malloc(0) == NULL` as definitely out of memory | C allows multiple behaviors for zero-size allocations | Define empty-result / zero-size cases separately |
| C returning a stack pointer or freed region | Dangling pointer, can crash the JVM | Return owned heap, static borrowed, or caller-provided buffer |
| Java closing `Arena` and then using native input | Pointer has exceeded its lifetime | Keep the arena alive throughout the call and access needs |
| Java only closing `Arena` for output from C `malloc` | Leak because the arena does not own that allocation | Call `api_free()` explicitly |
| Java calling `free` from the wrong allocator/runtime | Heap corruption, especially across DLL/CRT boundaries | Use the `api_alloc/api_free` pair from the same library |
| Mapping `size_t` to a fixed `int` | Length overflow/truncation, especially on 64-bit | Choose layout per ABI and validate size |
| Interpreting `const char *` as “no need to free” | `const` only restricts write permission through the pointer | Explicitly document borrowed/owned and the release function |
| Retaining pointers across callbacks/threads without rules | Possible use-after-free or data race | Define lifetime, synchronization, and ownership transfer |
| Forcing a C `struct` into a Java layout without verification | Padding/alignment and calling convention may differ | Use simple scalars + pointers or verify the ABI layout |

It is also necessary to distinguish **business errors** (e.g., key not found, invalid data) from **system errors** (out of memory, I/O error) and **contract violations** (invalid input pointer, caller double free). Do not try to “catch” a use-after-free by checking status: undefined behavior may occur before any status is returned.

## 8. Testing the Contract and Compatibility

When testing the C/Java layer, prioritize cases that accurately reflect the boundary:

1. **Success path:** `api_make_message("Java",...)` returns `API_OK`, non-`NULL` pointer, length `11`, NUL byte at position `11`; `api_free()` called exactly once.
2. **Invalid arguments:** `name == NULL` with two valid output pointers returns `API_EINVAL`, output pointer equals `NULL`, length equals `0`. Passing a `NULL` output pointer also returns `API_EINVAL` without dereferencing.
3. **Empty string:** input `""` is valid data; returns string `"Hello, "` with length `7`, not mistaken for an error.
4. **Size edges:** must test overflow-resistant addition; test simulated allocation failure via a fake/mocked allocator or fault injection, do not blindly attempt to allocate a huge region.
5. **Lifetime:** test release across all Java exception branches; tools like AddressSanitizer/LeakSanitizer/UBSan (when supported by the toolchain) help detect C leaks, invalid frees, and undefined behavior.
6. **ABI:** build/test at least each actually supported architecture and OS; confirm `size_t`/pointer width, symbol names, calling convention, UTF-8, and how exported functions are called.
7. **Threads:** run concurrently only when the contract promises thread-safety; test error paths from multiple threads, avoid sharing `Arena.ofConfined()` across other threads.
8. **Versioning:** preserve old status codes and release behavior; for unknown statuses, Java can report a generic error instead of assuming success.

A minimal contract table should be maintained right alongside the header:

| Property | Commitment of `api_make_message` |
| --- | --- |
| Input | `name` borrowed, NUL-terminated UTF-8 C string; both output pointers must be valid |
| Success | Returns `API_OK (0)`; `*out_message` is owned by caller; `*out_length` is byte count excluding NUL |
| Failure | Returns non-zero status; for valid output pointers, they are set to `NULL` and `0` |
| Allocation | Library allocates using its own allocator |
| Release | Caller calls `api_free(*out_message)` exactly once |
| Status string | `api_status_text()` is borrowed static, read-only, no need to free |
| Threads | Illustrative implementation uses no shared mutable state |
| ABI | `int32_t` status, `char*`, `size_t*`; binding must match the active ABI |

## 9. Principles for Applying in Real-World Projects

When standardizing a C library for Java, document alongside the header: **status and fixed enum numbers**, **when output data is valid**, **meaning of each sentinel**, **encoding and size**, **owner/lifetime of each pointer**, **the exact release function**, **thread-safety**, and **supported ABIs/versions**. Only map to Java exceptions or result objects after reading that entire contract.

Official API references for FFM: [Java SE 22 – `java.lang.foreign`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html), [`SymbolLookup`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html), [`MemorySegment`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html).