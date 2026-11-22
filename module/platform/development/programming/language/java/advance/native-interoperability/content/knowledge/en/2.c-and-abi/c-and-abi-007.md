# Null-Terminated Strings, Binary Data, and Length Parameters (C and ABI ↔ Java)

## Learning Objectives

After this lesson, you can distinguish a **C string** (a byte sequence terminated at byte `0`) from **binary data** (any byte can be data), determine when the ABI requires a pointer with a length, safely convert between Java's `String`/`byte[]` and native memory, as well as avoid data truncation, out-of-bounds reads, and length unit confusion.

Core rule: **do not infer the size of a binary buffer using `strlen`**. A pointer by itself carries no information about how many bytes remain valid to read. The format and API contract determine where the data ends.

## 1. Three Concepts to Keep Separate

| Model | Common Representation | Determining the End | What Role Does Byte `0x00` Play? |
| --- | --- | --- | --- |
| C string | `const char *` pointing to a byte sequence | The first `'\0'` byte the function reads | Acts as terminator; not part of string content per `strlen` |
| Binary buffer | `const void *`/`const unsigned char *` + `size_t length` | Length provided by the caller per contract | Normal data; can appear at any position |
| Java `String` | Unicode text object | `String.length()` returns the number of UTF-16 code units | Can contain U+0000 character; does not automatically terminate at this character |

In C, `'\0'` has the numeric value 0; in terms of storage, it is **a byte equal to 0** in an ordinary `char` sequence. C strings have no mandatory metadata to pre-record the length. The `strlen(s)` function scans to the first zero byte and returns **the number of bytes before the terminator**, excluding the terminator byte itself.

For example, memory `['A', 'B', 0, 'C', 'D']` has five bytes, but if treated as a C string, the observed content is `"AB"`, two bytes long. The two bytes `'C'` and `'D'` are still in memory; ordinary C string functions simply do not consider them part of the string starting at `'A'`.

A Java `String` is not synonymous with C's `char *`. To convert it into bytes to call a native library, you must choose an **encoding** (usually UTF-8), determine the **length in bytes**, and then decide whether to append a zero byte according to the C API contract.

## 2. `strlen`, `sizeof`, Data Length, and Buffer Capacity

Create the file `CStringAndBinary.c`:

~~~c
#include <stdio.h>
#include <string.h>

int main(void) {
    const char text[] = "AB";
    const unsigned char binary[] = {'A', 0, 'B', 0xFF};

    printf("strlen(text) = %zu\n", strlen(text));
    printf("sizeof(text) = %zu\n", sizeof text);
    printf("strlen(binary as C string) = %zu\n",
           strlen((const char *) binary));
    printf("sizeof(binary) = %zu\n", sizeof binary);
    return 0;
}
~~~

On a system with a C compiler supporting C11, run:

~~~bash
cc -std=c11 -Wall -Wextra CStringAndBinary.c -o cstring-demo
./cstring-demo
~~~

Output:

~~~text
strlen(text) = 2
sizeof(text) = 3
strlen(binary as C string) = 1
sizeof(binary) = 4
~~~

Explanation:

- `"AB"` is initialized into the `text` array consisting of `'A'`, `'B'`, and the terminating byte `0`. Therefore, the text length is 2, while the array capacity is 3.
- The `binary` array consists of four bytes, of which the second byte equals `0`. Casting to `const char *` does not turn it into complete text data: `strlen` still stops right at that `0` byte.
- `sizeof local_array` only tells the size of an array that still retains its array type in this scope. When passing an array into a pointer-type function parameter, `sizeof(pointer)` gives the size of the **pointer**, not the size of the data it points to.
- `size_t` is the unsigned integer type used for C object sizes; the `%zu` format specifier is used to print `size_t`. The size of `size_t` is an ABI/architecture property and must not be assumed to be fixed at 32 or 64 bits.

**Danger:** calling `strlen` on a buffer not guaranteed to have a terminating byte **within accessible memory** leads to undefined behavior; it may read out of bounds, fault, or accidentally read other memory. `strlen` has no size-limit parameter, so the function itself cannot perform bounds checking.

Distinguish four quantities:

- **Payload length:** the number of actual data bytes to process, e.g., 4.
- **C-string length:** the number of bytes before the first `0` byte, e.g., 1.
- **Capacity:** the number of memory bytes allocated and permitted to be used, e.g., 8.
- **Terminator storage:** one additional byte for `'\0'` when building a C string; not included in the `strlen` result.

## 3. Choosing an ABI Contract: Terminator or Pointer + Length?

Two C function styles have very different meanings:

~~~c
/* Requires name to be a valid NUL-terminated C string. */
int use_name(const char *name);

/* Processes exactly length bytes, including zero bytes. */
int consume_bytes(const unsigned char *data, size_t length);
~~~

With `use_name`, the caller must allocate at least `n + 1` bytes if the encoded name occupies `n` bytes, set `data[n] = '\0'`, and ensure there are no unintended zero bytes before the terminating position. The native function reads up to the terminator per contract.

With `consume_bytes`, the caller must ensure `data` points to at least `length` valid bytes for the entire duration of execution. The native function **does not call `strlen`, `strcpy`, or `strcmp` on binary data**. The length usually does not include any terminating marker byte, because this kind of API does not need a terminator. A binary buffer that happens to have a trailing zero byte is still processed in full according to `length`.

A clear way to wrap data when designing a C API:

~~~c
#include <stddef.h>

typedef struct {
    const unsigned char *data;
    size_t length;
} ByteSpan;

int parse_packet(ByteSpan packet);
~~~

`ByteSpan` does not own the memory itself. The caller and callee must still agree on who allocates, who frees, whether the data can be mutated, how long the pointer remains alive, and whether the function retains the pointer after returning. With callbacks/asynchronous calls, never let a C library retain a pointer to a Java buffer whose lifetime has ended or that has been released by JNI.

For a buffer with a known capacity where you want to find a C string, use a **bounded search**, such as `memchr`:

~~~c
#include <stddef.h>
#include <string.h>

/* Returns 0 if NUL is present within capacity bytes; -1 otherwise. */
int bounded_c_string_length(const char *buffer,
                            size_t capacity,
                            size_t *out_length) {
    if (out_length == NULL || (buffer == NULL && capacity != 0)) {
        return -1;
    }
    if (capacity == 0) {
        return -1;
    }
    const char *end = memchr(buffer, '\0', capacity);
    if (end == NULL) {
        return -1;
    }
    *out_length = (size_t) (end - buffer);
    return 0;
}
~~~

Here `memchr` reads at most `capacity` valid bytes; if no terminator is found, we refuse to treat the buffer as a C string. `strnlen` exists on many POSIX systems, but should not be assumed to be an ISO C standard function available in every environment. Only search for NUL when **the contract actually states this is C-string text**, do not use it as a way to compute packet length.

## 4. Bytes and Characters: UTF-8, UTF-16, and Which Length to Use

The question "how long is the string?" must specify the **unit**. A single letter `é` has one Unicode code point, one UTF-16 code unit in Java, but **two UTF-8 bytes** (`C3 A9`). An emoji outside the BMP typically has two UTF-16 code units and four UTF-8 bytes. Therefore:

- `javaString.length()` returns the number of UTF-16 code units; do not use this result as the byte count of a `UTF-8 char *`.
- `javaString.getBytes(StandardCharsets.UTF_8).length` returns the number of bytes after UTF-8 encoding.
- `strlen(utf8CString)` counts the number of bytes up to NUL, not Unicode code points.
- `byte[].length` is the number of byte elements; each element has Java's signed `byte` type (-128…127), but the bit pattern `0xFF` is still the same eight bits when converted to C `unsigned char`. Do not use the sign of Java `byte` to infer protocol content.

Memory layout for the text `"é"` encoded in UTF-8 as a C string:

~~~text
offset      0      1      2
byte       C3     A9     00
           └─ "é" ─┘     NUL
payload length = 2 bytes
allocated capacity = at least 3 bytes
strlen = 2
~~~

If the protocol uses `(pointer, length)`, you typically pass **2** as the payload length and do not need a zero byte. If the C function expects a NUL-terminated `char *`, you need a **3**-byte buffer as shown. You should not use the platform default charset by calling `getBytes()` with no arguments; choose the charset according to the library/protocol contract.

**Embedded NUL:** Java allows `"ab\0cd"`, but when encoded to standard UTF-8, the U+0000 character produces the byte `00`. A terminator-based C API will only see `"ab"`. Therefore, you must **reject U+0000** if a name/path/identifier must pass through a C-string ABI that does not support this case, or switch to a length-accepting API if you want to preserve the data.

## 5. Java 17+: Runnable Example Separating C String and Binary

Create `CStringVsBinary.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class CStringVsBinary {
    // Use only when the buffer must actually be a C string within the array bounds.
    static int boundedCStringLength(byte[] buffer) {
        for (int i = 0; i < buffer.length; i++) {
            if (buffer[i] == 0) {
                return i;
            }
        }
        throw new IllegalArgumentException("Missing NUL terminator");
    }

    // Contract accepts a UTF-8 C string, rejecting NUL in the middle of the content.
    static byte[] encodeCString(String text) {
        if (text.indexOf('\0') >= 0) {
            throw new IllegalArgumentException("Embedded NUL");
        }
        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
        return Arrays.copyOf(utf8, utf8.length + 1); // new byte = 0
    }

    // Binary contract: length determines exactly how many bytes are kept.
    static byte[] copyBinary(byte[] source, int length) {
        if (length < 0 || length > source.length) {
            throw new IllegalArgumentException("Invalid length");
        }
        return Arrays.copyOf(source, length);
    }

    public static void main(String[] args) {
        byte[] payload = {65, 0, 66, (byte) 0xFF};

        int textLength = boundedCStringLength(payload);
        System.out.println("C text: " + new String(
                payload, 0, textLength, StandardCharsets.UTF_8));
        System.out.println("Binary bytes: "
                + Arrays.toString(copyBinary(payload, payload.length)));
        System.out.println("Encoded C: "
                + Arrays.toString(encodeCString("Hi")));
        System.out.println("UTF-8 bytes for é: "
                + "é".getBytes(StandardCharsets.UTF_8).length);

        try {
            boundedCStringLength(new byte[] {65, 66});
        } catch (IllegalArgumentException e) {
            System.out.println("Missing terminator rejected");
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac CStringVsBinary.java
java CStringVsBinary
~~~

Stdout:

~~~text
C text: A
Binary bytes: [65, 0, 66, -1]
Encoded C: [72, 105, 0]
UTF-8 bytes for é: 2
Missing terminator rejected
~~~

Observations:

1. A C string views the buffer `{65, 0, 66, 255}` as `"A"` because it stops at the second byte. The binary form still has all four bytes; Java prints the bit pattern `0xFF` as `-1` due to signed `byte`.
2. `encodeCString("Hi")` yields `[72, 105, 0]`; byte 0 is the terminator storage, while the payload is only two bytes.
3. You cannot infer a C-string length from an array without NUL by scanning indefinitely; the example actively rejects it.
4. `Arrays.copyOf` in the example creates a new array. When using JNI/FFM, you must check whether the native API copies the data or holds a reference to the memory region.

This example illustrates **byte representation** precisely; it does not call native code itself. The next section uses JNI to pass a binary buffer across the Java ↔ C boundary.

When decoding an untrusted byte buffer, `new String(bytes, UTF_8)` may replace malformed UTF-8 byte sequences with replacement characters. If the protocol requires rejecting invalid UTF-8, use `CharsetDecoder` with `CodingErrorAction.REPORT` instead of silently accepting altered data.

## 6. JNI: Passing `byte[]` as Binary, Preserving Actual Length

Suppose Java calls native code to count bytes with value 0. This API **must count bytes after NUL as well**, so use `jbyteArray` together with `GetArrayLength`, not `strlen`.

File `BinaryBridge.java`:

~~~java
public final class BinaryBridge {
    static {
        System.loadLibrary("binarybridge");
    }

    private native int countZeros(byte[] bytes);

    public static void main(String[] args) {
        byte[] packet = {65, 0, 66, 0};
        System.out.println(new BinaryBridge().countZeros(packet));
    }
}
~~~

File `BinaryBridge.c`:

~~~c
#include <jni.h>
#include "BinaryBridge.h"

JNIEXPORT jint JNICALL Java_BinaryBridge_countZeros(
        JNIEnv *env, jobject receiver, jbyteArray bytes) {
    (void) receiver;

    if (bytes == NULL) {
        jclass type = (*env)->FindClass(env, "java/lang/NullPointerException");
        if (type != NULL) {
            (*env)->ThrowNew(env, type, "bytes");
        }
        return 0;
    }

    jsize length = (*env)->GetArrayLength(env, bytes);
    jbyte *data = (*env)->GetByteArrayElements(env, bytes, NULL);
    if (data == NULL) {
        if (!(*env)->ExceptionCheck(env)) {
            jclass type = (*env)->FindClass(env, "java/lang/OutOfMemoryError");
            if (type != NULL) {
                (*env)->ThrowNew(env, type, "Cannot access byte array");
            }
        }
        return 0;
    }

    jint zeros = 0;
    for (jsize i = 0; i < length; i++) {
        if (data[i] == 0) {
            zeros++;
        }
    }

    (*env)->ReleaseByteArrayElements(env, bytes, data, JNI_ABORT);
    return zeros;
}
~~~

On **Linux** with JDK 17+ and a C compiler, set `JAVA_HOME` to point to the JDK in use and run in the directory containing the two files:

~~~bash
javac -h . BinaryBridge.java
cc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  BinaryBridge.c -o libbinarybridge.so
java -Djava.library.path=. BinaryBridge
~~~

Stdout:

~~~text
2
~~~

`javac -h .` generates the exact JNI header from the native declaration. On macOS/Windows, the library name, build flags, and platform header directory change; the command above is **specific to Linux** and must not be treated as a cross-platform build command.

Explanation of the JNI mechanism:

- `GetArrayLength` returns the number of elements of `jbyteArray`, with type `jsize`. It includes all zero bytes because Java arrays do not use a terminator.
- `GetByteArrayElements` may allocate a copy or allow direct access to the array data depending on the JVM. Do not assume this is a stable pointer that can be saved after the function returns.
- `ReleaseByteArrayElements(..., JNI_ABORT)` releases access **without copying changes back** if the JVM used a copy buffer; this is appropriate because the example only reads. If native code needs to modify the array and return changes to Java, you must choose the appropriate release mode.
- `jbyte` is JNI's signed byte type. For binary-formatted data, when you need values 0..255, cast to `unsigned char` or mask properly instead of comparing as negative/positive numbers.
- If native code wants to read an array slice via a short copy, `GetByteArrayRegion` is also a good choice; it takes an explicit **start** and **length**, which can avoid managing a get/release pair. You still must check JNI exceptions and read bounds.

**Do not let `data` escape the acquire/release lifetime**. Do not store the pointer in a global variable, C object, or task running after the native method has finished. If the C library needs to own the data longer, allocate/copy it to native storage it manages and define responsibility for freeing it.

### JNI `String` and the Modified UTF-8 Trap

JNI has the functions `GetStringUTFChars`, `ReleaseStringUTFChars`, and `NewStringUTF`. They use JNI's **Modified UTF-8 (MUTF-8)**, which is not identical to standard UTF-8 used by `StandardCharsets.UTF_8`. For instance, U+0000 is encoded according to modified UTF-8 rules rather than a normal 0 byte; characters outside the BMP also have a different representation from standard UTF-8.

Therefore, **do not** automatically pass `GetStringUTFChars` output into a C API requiring standard UTF-8 if the input may contain characters affected by the encoding difference. Conversely, do not call `NewStringUTF` with arbitrary UTF-8 data or binary packets. If the C contract truly requires standard UTF-8, convert `String` to `byte[]` using `StandardCharsets.UTF_8`, then add a terminator or pass the length according to the API type; on the return path, decode exact `length` bytes.

## 7. FFM in Modern JDK and Differences from JNI

Since **JDK 22**, the Foreign Function & Memory API (FFM, package `java.lang.foreign`) has been the standard API for Java to call native libraries and work with off-heap memory. In JDK 17, FFM was still in incubator status; across versions before JDK 22, APIs/signatures changed. Therefore, do not apply a JDK 22 FFM snippet to a Java 17 program expecting it to compile directly.

Whether using JNI or FFM, **the C contract remains the same**:

- A function taking a C-string `const char *` must have NUL in valid memory; encoding and embedded NUL characters must be controlled.
- A function taking `(void *, size_t)` must have the exact number of bytes, including NUL; the size declared to native code must not exceed the actual memory capacity.
- With FFM, `MemorySegment` describes the memory region and access bounds; `Arena` manages the lifetime. Native pointers must not be used after the arena/segment expires.
- The native function descriptor must match the target's ABI. `size_t` must not be assumed to be identical to Java `int`; when converting sizes, check architecture, signedness, and value limits.

Choosing JNI or FFM is a technology decision; **choosing between C-string and pointer-plus-length is a data and ABI decision**, independent of the native invocation technology.

## 8. Length, Capacity, and Bounds Checking Before Native Calls

A reliable contract should specify six points:

1. **Unit:** is `length` measured in bytes, UTF-16 code units, element count, or code points? In C byte buffer APIs, it is normally bytes.
2. **Meaning of length:** does it include or exclude the terminator, is it input-only or also output capacity? For example, `inputLength` might be the number of payload bytes; `outputCapacity` is the capacity of the writable output region—completely different things.
3. **Nullability:** is `data == NULL` valid when `length == 0`? Which functions reject it, which accept it? This is a contract that must be stated explicitly, not guessed.
4. **Ownership and lifetime:** who allocates/frees; may the callee retain the pointer; can the buffer be overwritten?
5. **Encoding:** standard UTF-8, JNI's MUTF-8, UTF-16, ASCII, or raw binary? Who encodes/decodes?
6. **Limits and errors:** check `length <= capacity`, check that `length + 1` does not overflow, check casts between `size_t` and `jsize`/Java `int`, and specify how errors are reported.

For example, the following C snippet is only allowed to run if `capacity` has enough room for the payload **and** the terminator:

~~~c
#include <stddef.h>
#include <string.h>

int write_c_string(char *destination, size_t capacity,
                   const char *source, size_t source_length) {
    if (destination == NULL || source == NULL) {
        return -1;
    }
    /* This condition also prevents source_length + 1 from overflowing. */
    if (source_length >= capacity) {
        return -1;
    }
    /* source must point to at least source_length readable bytes. */
    memcpy(destination, source, source_length);
    destination[source_length] = '\0';
    return 0;
}
~~~

The sample function intentionally **does not determine** `source_length` itself with `strlen`: the caller has already determined how many bytes to copy. The caller must also ensure the source/destination regions do not overlap (a requirement of `memcpy`) and that the input contains no embedded NUL if the destination is used as a single C string. If the caller passes a length measured in Java characters instead of UTF-8 bytes, the copy may split in the middle of a multi-byte sequence and cause decoding errors.

**Regarding overflow:** if you need to compute `payloadLength + 1` for allocation, check `payloadLength < SIZE_MAX` before adding. If you need `count * elementSize`, check the multiplication before allocating. When casting `size_t` to `int`/`jsize`, verify the size is representable in the target; direct casting can lose data.

**Regarding signedness:** Java `byte` is signed; C `char` may be signed or unsigned depending on the implementation; `unsigned char` is appropriate when working with binary octets/bytes. Do not rely on comparisons or implicit casts of bytes greater than `0x7F` if the semantics require 0..255.

## 9. Real-World Failure Cases at the Java ↔ C Boundary

**Case 1 — packet content gets truncated.** Java creates `byte[] {0x50, 0x00, 0x4B, (byte) 0xFF}` (four bytes), but C uses `strlen((char *)ptr)` and sees only one byte `0x50`. The parser receives incomplete data, checksum fails, or the message is misinterpreted. Fix: choose an API `parse(ptr, 4)` and process all four bytes.

**Case 2 — Java and C validate differently.** Java validates the name `"admin\0guest"` as an intact string, while a `char *`-based C API reads only `"admin"`. If access control rules, filenames, or allowlists use two different interpretations, a vulnerability can arise. Fix: use the same normalization/validation according to **the format actually transmitted**, reject embedded NUL when going through a C-string ABI, and validate right before the call.

**Case 3 — `String.length()` used as byte length.** `"café"` has four UTF-16 code units but five UTF-8 bytes. Sending `length = 4` to a binary native C API will chop off the last byte of `é`. Fix: encode first, use `utf8Bytes.length`.

**Case 4 — using `sizeof` on a pointer parameter.** C code receives `const unsigned char *bytes` and then uses `sizeof(bytes)` to infer packet length. The result is the ABI pointer size, not the packet length. Fix: pass a `size_t length` parameter or a struct containing an explicit length.

**Case 5 — forgetting the terminator or allocating exact `n` bytes.** A buffer holds `n` bytes of content but has no room for `'\0'`. C string functions scan past the boundary or the caller writes the terminator out of bounds. Fix: satisfy `capacity >= n + 1`, check for overflow, and write the terminator at index `n`.

**Case 6 — native retains a released Java pointer.** Native passes the result of `GetByteArrayElements` into an asynchronous callback, then calls `ReleaseByteArrayElements` before the callback finishes using it. The pointer is no longer valid. Fix: copy to memory with an appropriate lifetime or design the API to process synchronously while the pointer is still valid.

## 10. Self-Check Questions and Answers

**Question 1.** Given `unsigned char p[] = {'A', 0, 'B'};`, what is `sizeof p`? If cast to `const char *` to call `strlen`, what is the result?

Answer: `sizeof p == 3` bytes in the same scope as the array declaration. `strlen((const char *)p) == 1` because byte 0 is at index 1. You must not use the result 1 to substitute for the binary array's length.

**Question 2.** To pass `"é"` as a UTF-8 C string, how many bytes must be allocated, and what length is passed if another C API requires pointer + payload length?

Answer: 3 bytes if storing the terminator (`C3 A9 00`); payload length is 2 bytes when calling a pointer-plus-length API excluding the terminator.

**Question 3.** When receiving a `byte[]` from Java that has a NUL in the middle, should you use a `const char *` API or `(const void *, size_t)`?

Answer: if the data needs all bytes preserved, use pointer + length; if it is actually C-string text, you must confirm the encoding and handle/reject embedded NUL according to the contract.

**Question 4.** A C buffer has capacity 8, and a UTF-8 payload occupies exactly 8 bytes. Can you write the terminator at `buffer[8]`?

Answer: no; valid indices of a capacity-8 buffer are 0..7. To also hold a terminator, you need capacity at least 9 and to check for overflow when computing the size.

**Question 5.** Does `GetStringUTFChars` automatically produce standard UTF-8 bytes like `String.getBytes(StandardCharsets.UTF_8)`?

Answer: no; JNI uses Modified UTF-8. For requirements to exchange standard UTF-8 or binary bytes, you must choose the appropriate encode/decode path, not substitute them for each other because of similar names.

## Checklist When Designing or Reviewing a Java/Native Boundary

- Has the data been classified as **text** or **binary** before choosing parameter types?
- If text, what is the charset; does the C ABI require NUL; is embedded NUL accepted?
- If binary, is **pointer + length** passed; is length measured in bytes; are all zero bytes preserved?
- Is `length` within buffer bounds and the ABI's numeric type range? Does `capacity` have enough room for the terminator when needed?
- Is the pointer valid throughout the entire time native uses it? Are JNI get/release, FFM arena, or manually allocated memory managed properly?
- Have you tested empty strings, missing NUL, embedded NUL, multi-byte Unicode, `0xFF` bytes, length-0 buffers, and boundary sizes?

## References

- [ISO C library `strlen`: behavior and NUL requirement](https://en.cppreference.com/c/string/byte/strlen).
- [Java SE 17 JNI Functions: arrays, strings, and release modes](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html).
- [Java SE 22 Foreign Function & Memory API](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html).

**Remember:** `'\0'` is the termination convention of a **C string**, whereas `length` is part of a **binary buffer contract**. Preserving data across the ABI depends on encoding, actual size, valid memory, and pointer lifetime — not on whether a zero byte happens to be found.
