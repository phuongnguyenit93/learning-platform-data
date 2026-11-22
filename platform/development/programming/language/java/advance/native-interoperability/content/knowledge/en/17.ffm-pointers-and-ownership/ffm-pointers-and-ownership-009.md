# Reading C Strings with Character Encodings, Terminating Bytes, and Length Limits

## Objectives

A C library may return a `const char *`, `char *`, or `unsigned char *` containing bytes interpreted as a “string”. When bringing that string into Java via JNI or the Foreign Function & Memory API (FFM), you cannot simply cast a native address to a `String`: you must determine **how long the memory region remains valid**, **how many bytes are permitted to be read**, **which byte terminates the string**, and **which character encoding turns the bytes into Unicode characters**.

This lesson thoroughly explains the three parts of a safe C string reading contract:

1. **Terminating byte:** a typical C string is a sequence of bytes terminated by `'\0'` (a byte with value `0x00`). This byte **is not part of the string's content**.
2. **Length limit:** the program must only search for the terminator **within memory that is definitely accessible**, and at the same time not exceed the byte limit permitted by the application.
3. **Character encoding:** the bytes before `'\0'` may be UTF-8, ISO-8859-1, Windows-1252, or an agreed-upon encoding; a Java `String` uses Unicode character sequences and does not have an “intrinsic encoding” like a raw `byte[]`.

The context of this lesson is **pointers and native memory ownership**: reading the right bytes while using a pointer whose lifetime has expired can still crash the program.

After studying this lesson, you will be able to:

- Distinguish C `char *`, JNI `jstring`, Java `String`, `byte[]`, and `MemorySegment`.
- Read NUL-terminated strings using a scanning loop **with a real bound**, without using `strlen` on a pointer of unknown length.
- Handle data without a terminator, early terminators, empty content, truncated buffers, and byte sequences with invalid encoding.
- Distinguish **standard UTF-8** from **JNI Modified UTF-8** (`NewStringUTF` and `GetStringUTFChars`).
- Compile/run a **Java 17 + JNI C** example that reads a C string via a native pointer, copies it into a Java `byte[]`, and decodes UTF-8 in strict mode.
- Understand how `MemorySegment.getString` works from **JDK 22+** and when to use a custom bounded scan function.
- Design native APIs that clearly specify `pointer + accessibleLength + encoding + ownership`.

## 1. Two Different String Representations

### 1.1. Standard C Strings

In C, the concept of a *null-terminated byte string* is typically an array of `char` with a `0x00` byte marking the end. For example:

~~~c
const unsigned char name[] = {'H', 'i', '!', 0};
~~~

The memory contains **four bytes**, but the string content is only **three bytes**. The function `strlen((const char *)name)` will return 3 in this example because there is indeed a NUL within the valid array.

~~~text
offset       0     1     2     3
byte        0x48  0x69  0x21  0x00
character     H     i     !    \0
payload    [-----------]     terminator
strlen = 3                   total storage = 4 bytes
~~~

However, a standalone `const char *` value **does not tell you the memory capacity**, does not tell you the character encoding, and does not prove that a terminating byte exists at any offset. `strlen(ptr)` must keep scanning until NUL; if there is no NUL before the end of valid memory, it can read past the allocation and lead to undefined behavior.

### 1.2. Java String

A Java `String` is a sequence of Unicode characters accessed as UTF-16 code units (`char`). Java does not need a `'\0'` byte to terminate a string. A `String` can contain the U+0000 character **right in the middle**:

~~~java
String javaText = "A\u0000B";
System.out.println(javaText.length()); // 3
~~~

This is an **illustrative Java snippet**: the U+0000 character is a valid component of a Java `String`, and does not mean the string ends right after the letter A.

If you convert it into a **NUL-terminated** C string using a single-byte-unit encoding such as UTF-8, the `0x00` byte in the middle will be treated as the end of the string by C functions that rely on a terminator. Therefore, “converting a `String` to `char *`” can lose content if the API does not have a separate length.

### 1.3. Do Not Confuse the Four Length Units

Suppose the Unicode string `"café"` is encoded in UTF-8:

~~~text
Java String       "café"
Java length()     4 UTF-16 code units
Unicode scalars   c, a, f, é (4 code points)
UTF-8 bytes       63 61 66 C3 A9        = 5 bytes
C string bytes    63 61 66 C3 A9 00     = 6 bytes, including NUL
~~~

For an emoji character outside the Basic Multilingual Plane such as `"😀"`, `String.length()` returns 2 because of the surrogate pair, whereas standard UTF-8 represents the character in 4 bytes. Do not use `String.length()` as the C buffer capacity when the encoding has variable byte length.

| Unit | API/Concept | Includes NUL? |
|---|---|---|
| Java UTF-16 code units | `String.length()` | Does not use a terminator; U+0000 can be content |
| Unicode code points | `codePointCount(...)` | Not a byte-length |
| Payload bytes per encoding | `str.getBytes(charset).length` | Does not automatically add a C NUL |
| C string length | `strlen(ptr)` **if the pointer is valid and has NUL** | No |
| Storage needed for UTF-8 C string | payload byte count + 1 | Yes, adds `0x00` byte |
| Buffer capacity | size of the allocation the pointer has permission to access | Must be enough for payload **and** terminator |

## 2. Memory Access Rules Before Reading a String

A C pointer is only safe to read when all of the following conditions are met simultaneously:

1. The pointer is **not `NULL`** or the API has a specific rule for null; do not dereference a null pointer.
2. The pointer points to an allocation/buffer that is **alive** and has read permission.
3. The caller knows **the number of bytes that can be validly read from the pointer**; do not guess capacity from the `char *` type.
4. No other thread frees or modifies the memory in violation of the contract while scanning.
5. The character region is read according to the right protocol: a C string must have a terminator within bounds; a binary buffer with a separate length does **not** necessarily have a terminator.
6. After reading is complete, the memory must be released using **the owner's exact API**, not `free` by default.

### 2.1. Four Required Facts

A sufficiently clear contract:

~~~text
pointer:        const unsigned char *data
accessibleSize: 64 bytes (per the SDK's allocation/API)
maxScanBytes:   32 bytes (business limit, including terminator)
encoding:       UTF-8
ownership:      borrowed, alive until returning from the callback
~~~

The application may only read at most:

~~~text
scanLimit = min(accessibleSize, maxScanBytes)
~~~

If `0x00` is found before `scanLimit`, the payload is the bytes before NUL. If NUL is **not** found within the limit, it must reject or report a **TRUNCATED/UNTERMINATED** status per the contract. Do not read the next byte “just to check”.

**A configuration limit does not prove memory exists.** Setting `maxScanBytes=4096` does not allow reading 4096 bytes from a pointer pointing to an allocation of only 12 bytes. `strnlen(ptr, 4096)` or `memchr(ptr, 0, 4096)` can also go out of bounds if 4096 bytes have not been proven accessible.

### 2.2. Scanning Loop Checking Both Limits

~~~c
#include <stddef.h>

static int find_c_string_length(
        const unsigned char *data,
        size_t accessible,
        size_t policy_limit,
        size_t *payload_bytes) {

    if (data == NULL || payload_bytes == NULL ||
        accessible == 0 || policy_limit == 0) {
        return 0;
    }

    size_t limit =
            accessible < policy_limit ? accessible : policy_limit;

    size_t i = 0;
    while (i < limit && data[i] != (unsigned char)0) {
        ++i;
    }

    if (i == limit) {
        return 0;  /* NUL not found within the allowed region. */
    }

    *payload_bytes = i;
    return 1;      /* Success, including empty string i == 0. */
}
~~~

This is a **standalone C11 function**. It is only safe when the caller guarantees that `data` points to at least `accessible` valid bytes throughout the call. The `policy_limit` can be smaller than `accessible` to avoid reading overly long data or exceeding application quotas.

**The order in the `while` condition matters:** C uses short-circuiting for `&&`, so `data[i]` is only read after `i < limit` is true. When `i == limit`, the code does not touch any out-of-bounds element.

If the payload is empty, the first byte is `0x00`, `i = 0`, and the function succeeds. If `limit` equals the exact number of payload bytes **without containing a terminator**, the function reports an error instead of returning an unterminated string as “fully read”.

### 2.3. Using memchr Instead of a Loop?

When you already have a valid bound:

~~~c
#include <string.h>

const unsigned char *end =
        memchr(data, '\0', accessible);

if (end != NULL) {
    size_t payload = (size_t)(end - data);
    /* Data is NUL-terminated at offset payload. */
}
~~~

This is an **illustrative C snippet**: `data` must have the proper pointer type and actually have at least `accessible` valid bytes. If there is also a `maxScanBytes`, pass `min(accessible,maxScanBytes)` to `memchr`. `memchr` searches for a byte, while `strnlen` is a function commonly found on POSIX and **not a mandatory ISO C11 API**; neither can fix an invalid pointer or an overstated bound.

## 3. Character Encodings: Bytes Do Not Automatically Become Unicode Characters

C `char *` typically holds bytes; a byte sequence can represent:

- **UTF-8:** variable-length Unicode encoding, ASCII-compatible for characters U+0000–U+007F.
- **ISO-8859-1 (Latin-1):** maps one byte to one character in a fixed character set.
- **Windows-1252:** an 8-bit encoding similar to Latin-1 in many positions, but differs significantly in the `0x80–0x9F` byte range (for example `0x80` is the euro sign).
- **US-ASCII:** defines only the 0–127 range; bytes outside this range must be handled according to decoder policy.
- **Library-defined encoding:** an SDK may specify a locale-dependent encoding, OEM code page, EBCDIC, or the data may not actually be a string.

There is no guaranteed standard encoding for all `char *` in C. **You must read the API documentation**; a generic label like “ANSI string” is not enough to determine the encoding across Windows/Linux/macOS.

### 3.1. UTF-8 and Byte Limits

Example string `"café"`:

~~~text
UTF-8 payload: c  a  f   é
hex:          63 61 66 C3 A9
C buffer:     63 61 66 C3 A9 00
max=6         successfully reads 5 bytes before NUL
max=5         NUL not found → error, even though 5 payload bytes are valid
max=4         NUL not found; also cuts in the middle of character é
~~~

A 5-byte limit is **not** a 5-character limit. When scanning, you must include the terminator in the number of bytes allowed to be read. When a decoder processes UTF-8, if bytes are accidentally cut in the middle of a multibyte sequence, an encoding error can occur; do not silently treat a truncated string as complete.

### 3.2. Strict Java Decoder

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public static String utf8Strict(byte[] bytes)
        throws CharacterCodingException {
    return StandardCharsets.UTF_8
            .newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
}
~~~

This is **a Java method** that can be placed in a Java 17+ class. It operates on **payload bytes already extracted from the C pointer**, without needing a terminating `0x00` byte.

If the byte sequence is invalid UTF-8, `CharsetDecoder` with `CodingErrorAction.REPORT` throws `CharacterCodingException` (specifically, it may be `MalformedInputException`). Conversely, the `new String(bytes, StandardCharsets.UTF_8)` constructor may **replace** invalid byte sequences with a replacement character; that may be acceptable for UI text, but is unsuitable when corrupted data must be detected or for strict protocols.

### 3.3. Latin-1 and Windows-1252 Are Not Like UTF-8

A single byte `0xE9` in ISO-8859-1 represents the character `é`. In UTF-8, that character must use **two bytes `0xC3 0xA9`**. If you decode a lone `0xE9` byte with strict UTF-8, an error will occur. If you use replacement decoding, the character `` may appear, making the data look like “garbage”.

With Windows-1252, the byte `0x80` is interpreted as `€`, whereas ISO-8859-1 uses a control code point at the corresponding position. Therefore, do not use `StandardCharsets.ISO_8859_1` instead of `Charset.forName("windows-1252")` when the SDK explicitly specifies Windows-1252.

## 4. JNI Modified UTF-8 Is Not Standard UTF-8

JNI has the following APIs:

~~~c
jstring NewStringUTF(JNIEnv *env, const char *utf);
const char *GetStringUTFChars(
        JNIEnv *env, jstring string, jboolean *isCopy);
void ReleaseStringUTFChars(
        JNIEnv *env, jstring string, const char *utf);
~~~

The signatures above are **descriptive patterns of the JNI C interface**. `NewStringUTF` takes a **NUL-terminated Modified UTF-8 (MUTF-8)** byte string. `GetStringUTFChars` returns an MUTF-8 string and must be paired properly with `ReleaseStringUTFChars`.

**Modified UTF-8 differs from standard UTF-8:**

| Case | Standard UTF-8 | JNI Modified UTF-8 |
|---|---|---|
| ASCII without NUL | 1:1 identical bytes | Identical |
| U+0000 | Byte `00` | Two bytes `C0 80` to avoid NUL in the payload |
| Characters outside BMP, e.g. 😀 | One 4-byte sequence | Encodes each UTF-16 surrogate as a 3-byte group (6 bytes total) |
| External NUL terminator | Present if required by C protocol | Present for `NewStringUTF` and strings returned by `GetStringUTFChars` |
| Arbitrary UTF-8 data from a C library | Valid if accepted by a UTF-8 decoder | **Not by default** valid MUTF-8 |

**Do not** pass any arbitrary “UTF-8-looking” `const char *` into `NewStringUTF`. For ordinary bytes like ASCII letters or certain BMP characters, the result may look right, but when encountering U+0000, emojis, or invalidly encoded data, the behavior is no longer equivalent. With CheckJNI, some invalid MUTF-8 can be detected.

When the source is standard UTF-8 or Windows-1252, the easily controllable option is:

1. Perform a bounded NUL scan based on real capacity.
2. Copy the exact **payload bytes** into a Java `byte[]`.
3. Use `CharsetDecoder` or `new String(bytes, charset)` per policy.
4. Do not force a Java `String` into MUTF-8 without a clear contract.

If you want to create a `jstring` entirely in C without going through a Java decoder, you can use a proper transcoding library from the source encoding to UTF-16, then call `NewString(env, jchar*, jsize)`. You must manage the count of **UTF-16 code units**, not the byte count; `NewString` does not require a C terminator. Do not cast raw UTF-8 bytes to `jchar *`.

### 4.1. Data Transfer Direction of the Functions

- **C → Java:** `NewStringUTF` only for MUTF-8, or `NewString` with UTF-16 data; another option is `NewByteArray` + a Java Charset decoder.
- **Java → C:** `GetStringUTFChars` returns MUTF-8, and the result must not be assumed to be standard UTF-8. `ReleaseStringUTFChars` must be called as soon as done.
- **Java → C standard UTF-8:** typically encode with `string.getBytes(StandardCharsets.UTF_8)`, then pass the byte array/FFM memory and length as required by the API. If a C string is needed, append a NUL byte **and** check the content for embedded `0x00` per policy.
- **Java → C UTF-16:** use `GetStringChars`/`ReleaseStringChars` with `jchar` and length; do not treat it as a portable `wchar_t *` across all OSes.

## 5. Complete Java 17 + JNI C Example: Bounded Reading, Charset Decoding

This example intentionally uses native **fixture data in C** so that it does not depend on external libraries and ensures verifiable output. The C code has static strings with different conditions:

| Fixture ID | Source Bytes | Characteristics |
|---|---|---|
| 0 | `63 61 66 C3 A9 00` | Valid UTF-8 C string: `café` |
| 1 | `41 00 42 00` | Early NUL: visible C string is only `A` |
| 2 | `78 79 7A` | No NUL byte in the allocation |
| 3 | `C3 28 00` | Has NUL, but invalid UTF-8 payload |
| 4 | `63 61 66 E9 00` | Latin-1 C string `café`, not UTF-8 |
| 5 | `00` | Empty C string |

The native method receives `fixture` and `maxBytes`, **knows the actual C array size itself**, and uses `min(actualSize,maxBytes)` to scan for NUL. If the terminator is not within bounds, the function throws `IllegalArgumentException`, **without reading past the buffer**.

The native function only returns the payload bytes (`byte[]`). Java decides how to decode according to the charset. This model clearly demonstrates the responsibilities of both sides:

~~~text
const unsigned char *native_pointer
          |
     known capacity + maxBytes
          |
   bounded search for 0x00
          |
    length of payload bytes
          |
    JNI NewByteArray + copy
          |
        Java byte[]
          |
   CharsetDecoder UTF-8 strict
      or ISO-8859-1 decoder
          |
        Java String
~~~

### 5.1. File `CStringReadDemo.java`

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public final class CStringReadDemo {

    static {
        System.loadLibrary("cstringread");
    }

    // Return payload bytes, WITHOUT the NUL byte.
    private static native byte[] readCStringBytes(
            int fixture, int maxBytes);

    private static String decodeUtf8Strict(byte[] data)
            throws CharacterCodingException {
        return StandardCharsets.UTF_8
                .newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(data))
                .toString();
    }

    public static void main(String[] args) throws Exception {

        byte[] valid = readCStringBytes(0, 6);
        System.out.println("utf8=" + decodeUtf8Strict(valid));
        System.out.println("payloadBytes=" + valid.length);

        // Byte 0x00 is the termination point; B after NUL is ignored.
        System.out.println(
                "embeddedNul="
                + decodeUtf8Strict(readCStringBytes(1, 4)));

        // Correct ISO-8859-1 encoding: byte E9 is the character é.
        System.out.println(
                "latin1="
                + new String(readCStringBytes(4, 5),
                             StandardCharsets.ISO_8859_1));

        // Empty string: NUL is right at the first position.
        System.out.println(
                "emptyLength="
                + decodeUtf8Strict(readCStringBytes(5, 1)).length());

        try {
            readCStringBytes(2, 3); // 3-byte buffer without NUL
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "missingNul=" + ex.getClass().getSimpleName());
        }

        try {
            // 5 payload bytes, but the NUL byte is at offset 5.
            readCStringBytes(0, 5);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "limitTooSmall=" + ex.getClass().getSimpleName());
        }

        try {
            decodeUtf8Strict(readCStringBytes(3, 3));
        } catch (CharacterCodingException ex) {
            System.out.println(
                    "invalidUtf8=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

The Java code distinguishes two types of errors: **no terminator within bounds** is detected by C before copying; **byte sequence not matching the charset** is detected by `CharsetDecoder` in Java after copying.

### 5.2. Generating the JNI Header from Real Source

Run on JDK 17 or later:

~~~bash
javac -h . CStringReadDemo.java
~~~

This command creates `CStringReadDemo.class` and `CStringReadDemo.h`. Keep the header file in the same directory as the C code. Native methods in the default package have JNI names generated according to the class; when changing the package or overloading, regenerate the header instead of guessing the exported symbol.

### 5.3. File `cstringread.c`

~~~c
#include "CStringReadDemo.h"

#include <stddef.h>
#include <string.h>

/* Source bytes are in static storage: no need to free. */
static const unsigned char TEXT_UTF8[] = {
    'c', 'a', 'f', 0xC3u, 0xA9u, 0
};
static const unsigned char EMBEDDED_NUL[] = {
    'A', 0, 'B', 0
};
static const unsigned char NO_NUL[] = {
    'x', 'y', 'z'
};
static const unsigned char INVALID_UTF8[] = {
    0xC3u, 0x28u, 0
};
static const unsigned char TEXT_LATIN1[] = {
    'c', 'a', 'f', 0xE9u, 0
};
static const unsigned char EMPTY_TEXT[] = {
    0
};

/* Only call where there is no pending Java exception. */
static void invalid_argument(JNIEnv *env, const char *message) {
    jclass klass = (*env)->FindClass(
            env, "java/lang/IllegalArgumentException");

    if (klass == NULL) {
        return; /* Keep the existing exception if FindClass fails. */
    }

    (*env)->ThrowNew(env, klass, message);
    (*env)->DeleteLocalRef(env, klass);
}

JNIEXPORT jbyteArray JNICALL
Java_CStringReadDemo_readCStringBytes(
        JNIEnv *env, jclass declaringClass,
        jint fixture, jint maxBytes) {

    (void)declaringClass;

    const unsigned char *source = NULL;
    size_t accessible = 0;

    switch (fixture) {
        case 0:
            source = TEXT_UTF8;
            accessible = sizeof TEXT_UTF8;
            break;
        case 1:
            source = EMBEDDED_NUL;
            accessible = sizeof EMBEDDED_NUL;
            break;
        case 2:
            source = NO_NUL;
            accessible = sizeof NO_NUL;
            break;
        case 3:
            source = INVALID_UTF8;
            accessible = sizeof INVALID_UTF8;
            break;
        case 4:
            source = TEXT_LATIN1;
            accessible = sizeof TEXT_LATIN1;
            break;
        case 5:
            source = EMPTY_TEXT;
            accessible = sizeof EMPTY_TEXT;
            break;
        default:
            invalid_argument(env, "unknown fixture");
            return NULL;
    }

    if (maxBytes <= 0) {
        invalid_argument(env, "maxBytes must be positive");
        return NULL;
    }

    /* Dual rule: do not exceed the REAL allocation,
       and do not exceed the application limit. */
    size_t policy = (size_t)maxBytes;
    size_t limit =
            accessible < policy ? accessible : policy;

    size_t payload = 0;

    while (payload < limit && source[payload] != 0) {
        ++payload;
    }

    if (payload == limit) {
        invalid_argument(
                env, "NUL terminator not found within bound");
        return NULL;
    }

    /*
     * All fixtures are <= sizeof(TEXT_UTF8) == 6 bytes.
     * Payload <= 5, so the copy area on the stack is always sufficient.
     * Do not use this approach for data of arbitrarily unbounded length.
     */
    jbyte temp[sizeof TEXT_UTF8];

    if (payload != 0) {
        memcpy(temp, source, payload);
    }

    /* Create Java byte[], excluding the terminator. */
    jbyteArray result =
            (*env)->NewByteArray(env, (jsize)payload);

    if (result == NULL) {
        return NULL; /* Let the JVM handle the allocation error. */
    }

    if (payload != 0) {
        (*env)->SetByteArrayRegion(
                env, result, 0, (jsize)payload, temp);

        if ((*env)->ExceptionCheck(env)) {
            return NULL;
        }
    }

    return result;
}
~~~

**Why does this C code avoid reading out of bounds?**

1. `source` is only selected from static arrays whose **real** length is known in advance via `sizeof array`. It does not use `sizeof pointer` to pretend to be capacity.
2. `limit = min(accessible, policy)` ensures the scan loop neither reads past the C array nor exceeds the limit permitted by the Java caller.
3. `payload < limit` is checked before `source[payload]`. If NUL is not found, it returns an error without calling `strlen` to keep going.
4. `temp` is sized sufficiently for the largest fixture, and `payload < limit <= accessible <= 6`. Data is copied **by byte**, without reading the terminator.
5. `NewByteArray` allocates a Java byte array with a number of elements equal to the payload. `SetByteArrayRegion` copies the bytes from the C stack area before the function returns.
6. `temp` is a stack buffer; Java receives an independent `byte[]`. No stack pointer is retained after returning.
7. `INVALID_UTF8` still passes **the C NUL-scanning step** because it has a valid terminator; the decode error is detected afterward by the Java decoder.
8. When NUL is missing, C uses `ThrowNew` to throw `IllegalArgumentException`, returns immediately, and does not continue calling JNI beyond permitted cleanup operations.

**Scaling to production:** if receiving large buffers from an SDK, do not create a stack array `jbyte temp[bytes]` sized by input. Use `SetByteArrayRegion` with a properly typed buffer of verified capacity, or copy in chunks. Always check that the payload is representable as `jsize` and within `NewByteArray` limits before allocating. In the example all fixtures are under 6 bytes, so the `size_t → jsize` conversion is safe.

### 5.4. Compiling and Running the Library

The commands below use JDK 17+ and a compiler matching the OS/CPU/ABI of the JVM process. Choose **one** platform.

**Linux (GCC):**

~~~bash
gcc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  cstringread.c -o libcstringread.so

java -Djava.library.path=. CStringReadDemo
~~~

**macOS (Clang):**

~~~bash
clang -std=c11 -Wall -Wextra -dynamiclib \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
  cstringread.c -o libcstringread.dylib

java -Djava.library.path=. CStringReadDemo
~~~

**Windows (MSVC Developer Command Prompt):**

~~~bat
cl /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" cstringread.c /Fe:cstringread.dll
java -Djava.library.path=. CStringReadDemo
~~~

`System.loadLibrary("cstringread")` uses the logical library name; the JVM looks up the file name according to the operating system's convention. The JDK headers must match the JVM architecture and the native library must be loadable; errors such as `UnsatisfiedLinkError` occur before the example prints output.

### 5.5. Expected Stdout

~~~text
utf8=café
payloadBytes=5
embeddedNul=A
latin1=café
emptyLength=0
missingNul=IllegalArgumentException
limitTooSmall=IllegalArgumentException
invalidUtf8=MalformedInputException
~~~

Explanation of each case:

- Valid UTF-8: 5 payload bytes become `"café"` (4 UTF-16 code units).
- `embeddedNul`: the first `0x00` byte ends the C string; the letter `B` after the terminator is **not** copied.
- `latin1`: byte `0xE9` is decoded properly as `é` with `ISO_8859_1`.
- `emptyLength`: the first byte is already NUL, so the payload is empty.
- `missingNul`: `NO_NUL` has no `0x00` byte in the scanned allocation.
- `limitTooSmall`: only 5 payload bytes of the UTF-8 fixture can be read, but the 6th byte is needed as the terminator, so an error must be reported.
- `invalidUtf8`: bytes `C3 28` do not form valid UTF-8; the strict decoder throws `MalformedInputException`.

There is no `strlen` on an unknown pointer, no `NewStringUTF` with raw UTF-8, and no native pointer is retained after returning.

## 6. Relationship Between maxBytes and Buffer Capacity

These two quantities are different:

- **Accessible capacity:** the number of actually valid bytes starting from the pointer, confirmed by the allocation or SDK/OS.
- **Policy limit:** the maximum amount the application allows scanning, for example to avoid oversized metadata or consuming too much RAM.

~~~text
Actual native buffer:  32 bytes
Policy maxScanBytes:   12 bytes
NUL at offset:         7
→ success, 7-byte payload

Actual native buffer:  32 bytes
Policy maxScanBytes:   12 bytes
NUL at offset:         20
→ reject, do not read up to offset 20

Actual native buffer:  6 bytes
Policy maxScanBytes:   4096 bytes
No NUL within 6 bytes
→ reject after at most 6 bytes, must not read up to 4096
~~~

**Never increase the policy limit to “fix” a pointer without NUL** when the accessible capacity is unknown. For APIs returning `const char *` **without a length**, it is only safe to call `strlen`-style functions when the documentation guarantees the pointer points to a valid, NUL-terminated, and still-alive C string. If the source is untrusted, it is better to require an API with `pointer + byteCount` or copy into a buffer with an application-controlled limit.

### 6.1. You Cannot “Compute Capacity” from char*

C does not automatically attach runtime metadata to every pointer. When receiving:

~~~c
void consume(const char *ptr);
~~~

`sizeof(ptr)` is the size of the **pointer variable**, not the number of allocation bytes that `ptr` points to. Only `sizeof nativeArray` (when `nativeArray` is actually an array in the same scope) returns the array length in bytes.

For pointers returned by a C SDK, the size usually comes from:

- an accompanying length or capacity parameter;
- a struct describing the buffer;
- an API for retrieving length with a reliable convention;
- documentation guaranteeing NUL within a fixed number of bytes;
- a wrapper allocated by **the application itself**, which therefore knows the exact capacity.

Do not guess capacity by adding/subtracting pointer addresses, looking at a terminator found very far away, or scanning all of virtual memory.

### 6.2. How Should Errors Be Reported When Needed?

Depending on the application, one of the following statuses can be used:

| Status | Meaning | Recommended Behavior |
|---|---|---|
| `OK` | NUL found within bounds, valid decode | Return string |
| `NULL_POINTER` | Pointer is null and API does not define null as valid | Report error or return optional per contract |
| `NOT_TERMINATED` | No NUL before scanLimit | Report error, do not append out-of-bounds bytes |
| `TOO_LONG` | Business quota blocks before NUL | Report error or handle string with explicit length |
| `INVALID_ENCODING` | Payload bytes invalid for charset | Decoder REPORT or replacement per policy |
| `EXPIRED_POINTER` | Native lifetime has ended | Do not read; this is a severe ownership bug |
| `INVALID_CAPACITY` | Declared capacity untrusted/unverified | Reject API, do not attempt to scan |

The runnable example uses `IllegalArgumentException` for the two situations NOT_TERMINATED/TOO_LONG, and `CharacterCodingException` for INVALID_ENCODING. A production API may use more specific exception types or error codes.

## 7. Content Containing Byte 0: C Strings and Binary Data Are Two Different Contracts

If the source contains:

~~~text
41 00 42 00
 A \0  B \0
~~~

A function that reads a **C string** will return `"A"`. If all four bytes are **binary payload** that needs to be processed, use a **pointer + byte length** protocol, not a NUL terminator. A Java `String` can represent `"A\u0000B"`, but a plain C string cannot hold U+0000 in the middle while still using the byte-0 termination rule.

Do not “fix” this by skipping all `0x00` bytes. That alters content, loses data, and also corrupts UTF-16/UTF-32 if the encoding is mistaken. To hold embedded zero bytes, you must have a **separate length**.

Some C libraries return an empty string as `""` (one NUL byte), while others return `NULL` to represent “no value”. The two cases are not equivalent: the contract must distinguish `null`, empty string, and error state.

## 8. If the Encoding Is Not UTF-8

### 8.1. Always Specify the Charset When Decoding

In Java:

~~~java
String utf8 = new String(bytes, StandardCharsets.UTF_8);
String latin1 = new String(bytes, StandardCharsets.ISO_8859_1);
String cp1252 = new String(bytes, java.nio.charset.Charset.forName(
        "windows-1252"));
~~~

This is a **Java snippet**, assuming `bytes` has been copied from native memory within proper bounds. The three statements may return different results if any byte is >= `0x80`. Do not use `new String(bytes)` when the protocol requires consistent encoding across machines: the default charset choice depends on the environment/JDK and is not the C SDK's contract.

### 8.2. Decoder on Data Errors

If the data is protocol text that must be valid, use `CharsetDecoder` with `REPORT` as in the example. If displaying text from a less trusted source, replacement may be a considered policy, but it must be explicitly noted that **information loss** is possible.

For UTF-8, the strict decoder also detects invalid continuation bytes, overlong encodings, and invalid sequences. It does not “fix” the wrong encoding by trying random charsets. If a lot of mojibake data is observed, first verify the encoding declared by the vendor.

### 8.3. Do Not Apply Byte-0 Scanning to UTF-16/UTF-32

A `wchar_t*` is not necessarily UTF-16. On Windows it is usually 16-bit; on many Unix-like platforms `wchar_t` is usually 32-bit. A “wide C string” uses a **zero code unit** of the corresponding width, not “the first byte equal to zero”.

With UTF-16LE, the ASCII character `A` is the byte pair `41 00`; using `memchr(buffer, 0, capacity)` will see the zero byte right at offset 1 and think the string has ended, leading to misreading. You must choose the code unit type, byte order, alignment, and memory accessibility according to the API; use a length or a width-aware terminator scan.

Data with a BOM does not automatically guarantee the right encoding. If the SDK says UTF-16LE, do not take an 8-bit `char*` and decode it as UTF-8 just because the system uses Unicode.

## 9. Ownership: Borrowed C Strings and Owned C Strings

### 9.1. Borrowed Pointer

A C function may return a pointer to memory **owned by the library**, such as internal metadata:

~~~c
const char *get_error_text(void);
~~~

If the documentation says the pointer is valid until **the next API call**, you must copy the bytes within that window; do not cache the pointer in Java as a `long` and decode it later. If the library has other threads modifying the same buffer, you must follow the locking/API contract.

Do not `free` a borrowed pointer, and do not use `ReleaseStringUTFChars` for a pointer not created by `GetStringUTFChars`.

### 9.2. Owned Pointer

Another API may return an allocated buffer and transfer ownership to the caller:

~~~c
char *make_error_text(void);
void release_error_text(char *ptr);
~~~

If `release_error_text` exists, you must call that exact function after copying, even if creating the Java `byte[]` or the decoder fails. Do not substitute `free` on your own if the documentation does not allow it. A pointer created by C++ `new[]` must be destroyed with the matching allocator/deallocator; a pointer from an SDK usually must be released through the SDK.

### 9.3. JNI Object References Are Different from C Pointers

`jstring` and `jbyteArray` are JNI object references managed by the JVM; `jbyteArray result` in the example is a local reference returned to Java. `source` in the example is a native pointer to static memory and is not a JNI reference.

The `DeleteLocalRef` function only manages JNI local references. It **does not** free native `malloc`. Conversely, `free` must not be used on `jbyteArray` or `jstring`.

### 9.4. Do Not Keep a Stack Pointer After Return

If C code returns a pointer to a local array:

~~~c
const char *wrong(void) {
    char temp[] = "hello";
    return temp; /* WRONG: the lifetime of temp ends upon return. */
}
~~~

This is a **C anti-pattern** and must not be used. The pointer becomes dangling as soon as the function ends. A Java wrapper cannot fix this by “scanning for NUL faster” after return. The right options are copying the data while the source is alive, using static storage per contract, or allocating an owned region with a clear release function.

## 10. Java 22+ FFM: MemorySegment.getString and Region Bounds

Starting in JDK 22, `MemorySegment` has the methods:

~~~java
String getString(long byteOffset);
String getString(long byteOffset, java.nio.charset.Charset charset);
~~~

`getString(offset)` uses **UTF-8**; the overload taking a charset lets you specify the encoding. It reads a **null-terminated string** from the segment starting at the given byte offset, within the bounds described by the segment. **It does not create an arbitrary policy limit for you** if the segment is too large; to constrain the byte count, you need to build a size-bounded view or scan manually as in the earlier section.

The `getString(offset, charset)` specification states that malformed encoding data is **replaced** with the replacement string; if strict error reporting is needed, read the valid bytes within bounds and then use `CharsetDecoder` with `REPORT`.

### 10.1. Runnable JDK 22+ Example (Without C)

File `CStringFfmDemo.java`:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.charset.StandardCharsets;

public final class CStringFfmDemo {
    public static void main(String[] args) {
        byte[] cString = {
                'c', 'a', 'f', (byte) 0xC3, (byte) 0xA9, 0
        };

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment nativeMemory = arena.allocate(cString.length);

            for (int i = 0; i < cString.length; i++) {
                nativeMemory.set(
                        ValueLayout.JAVA_BYTE, (long) i, cString[i]);
            }

            System.out.println(
                    "ffm=" + nativeMemory.getString(
                            0L, StandardCharsets.UTF_8));
            System.out.println("native=" + nativeMemory.isNative());
        }
    }
}
~~~

Run with JDK 22 or newer:

~~~bash
javac CStringFfmDemo.java
java CStringFfmDemo
~~~

Expected stdout:

~~~text
ffm=café
native=true
~~~

Here the native memory has **6 bytes** and NUL at offset 5. `getString` reads up to NUL and decodes as UTF-8. The Arena controls lifetime: after `try` finishes, the old segment must not be accessed even if a Java variable still references it.

### 10.2. Why Is a Slice Needed When There Is a Max Length?

Suppose an SDK provides a 4096-byte segment, but the protocol allows a string of at most 32 bytes **including the terminator**. Do not call `segment.getString(0)` on the entire 4096 bytes and only then check `str.length()`: that operation could scan/decode beyond the business limit.

Instead, create a **properly bounded slice**:

~~~java
long maxScanBytes = 32L;
long allowed = Math.min(segment.byteSize(), maxScanBytes);
MemorySegment bounded = segment.asSlice(0L, allowed);

// bounded.getString(0L, StandardCharsets.UTF_8):
// will not be allowed to read beyond bounded's byteSize().
~~~

This is an **illustrative Java snippet** inside a method that already has an alive, accessible `segment` and a valid `maxScanBytes`. If there is no NUL in the slice, handle the bounds error per the API, **do not automatically expand the scan**.

**This limit is only meaningful if `segment.byteSize()` actually describes accessible memory.** Using `reinterpret` to “self-declare” a raw pointer as having 4096 bytes when it really only has 12 bytes is dangerous; restricted FFM APIs cannot automatically know the real allocation or lifetime of a C SDK.

### 10.3. When Strict Decoding and Specific Error States Are Needed

With a segment whose valid bounds are known, scan byte by byte and copy the payload to a Java `byte[]`, then call `CharsetDecoder`. That approach clearly distinguishes:

- NUL not found within bounds;
- valid payload bytes but invalid encoding;
- expired pointer/segment lifetime;
- string exceeding the application quota.

Do not try to infer every kind of error from a single `getString` call, because this overload has a **replacement** policy for malformed bytes. For multibyte encodings with multibyte terminators, apply the proper charset/FFM contract rather than using single-zero-byte checking logic for all encodings.

## 11. Common Mistakes and How to Fix Them

| Mistake | Risk | Correct Approach |
|---|---|---|
| Calling `strlen(ptr)` without knowing the memory region and NUL | Reading past allocation, undefined behavior | Require a contract with capacity + terminator or length |
| Calling `strnlen(ptr, 4096)` on an actual 8-byte buffer | Can still read past 8 bytes | `min(accessibleCapacity, policyLimit)` |
| Treating `sizeof(ptr)` as buffer capacity | Usually only 4/8 bytes of address size | Get size from real array/separate API |
| Treating max length as “number of characters” | Multibyte UTF-8, Java UTF-16 length differs | Define limit **in bytes** |
| Not counting the terminator byte | Accepting a buffer missing NUL or writing out of bounds | Storage needs payload bytes + 1 for UTF-8 C string |
| Reading past a `0x00` byte in the middle | Reading data not belonging to the C string | Stop at the first NUL, or use a length protocol if binary is needed |
| Passing arbitrary UTF-8 to `NewStringUTF` | JNI requires Modified UTF-8 | Decode bytes with explicit charset, or convert to UTF-16 then `NewString` |
| Assuming `GetStringUTFChars` returns standard UTF-8 | Can differ on U+0000, supplementary | Treat as MUTF-8 and release with the right API |
| Using `new String(bytes)` without specifying a charset | Encoding depends on runtime policy, prone to mojibake | Specify `StandardCharsets.UTF_8`/SDK's charset |
| Decoding errors with replacement in strict protocols | Silently loses information | `CharsetDecoder` + `CodingErrorAction.REPORT` |
| Decoding Latin-1 `0xE9` as UTF-8 | Malformed bytes error | Use the charset confirmed by SDK documentation |
| Scanning for byte 0 in UTF-16LE | Byte 0 can appear in normal code units | Use the proper code unit width and byte order |
| Using a pointer after callback/native return | Dangling pointer/UAF | Copy while lifetime is valid, do not cache borrowed pointers |
| Calling `free` on a borrowed/static pointer | Crash/double free | Only free/release when the ownership contract requires it |
| Using `DeleteLocalRef` to free a malloc pointer | Unrelated | `DeleteLocalRef` for JNI refs; `free`/SDK release for native |
| Believing FFM `getString` limits itself by policy | Scans until NUL across the entire segment | Use `asSlice` or bounded scan |
| Ignoring JNI exceptions after `NewByteArray`/`SetByteArrayRegion` | Continuing execution in an error state | Check `NULL`/`ExceptionCheck` and stop |
| Converting large `size_t` length to `jsize` without checking | Overflow/sign flip, allocation failure | Check representable bounds before `NewByteArray` |
| Passing a C pointer as a Java `long` and using it after close | No automatic native lifetime check | Have a clear owner, lease, and release protocol |
| Guessing encoding from OS/locale | Works on one machine, fails on another | Document encoding as part of the API contract |

## 12. Essential Tests Before Going to Production

Test at least the following cases:

1. ASCII string with terminator right at the end of the buffer.
2. UTF-8 string with multibyte characters, e.g. `é`, emoji.
3. Empty string: first byte is `0x00`.
4. Embedded NUL: define policy to truncate at NUL or use a length protocol.
5. No NUL in the entire allocation.
6. NUL located at the last byte of `maxScanBytes`: **valid**.
7. NUL located **just outside** `maxScanBytes`: **invalid**.
8. Max length 0, negative, too large, and byte lengths about to exceed Java array limits.
9. Invalid UTF-8: bad continuation byte, truncated multibyte sequence, overlong byte sequence.
10. Legacy encodings: distinguish Latin-1 and Windows-1252.
11. Null pointer, dangling pointer, or unclear ownership contract: reject instead of guessing.
12. SDK-owned native pointer valid only until callback return: copy before returning.
13. JNI code with pending exception mid-copy: clean up and return properly.
14. Another worker may modify/free the same buffer: proper locking or snapshot/ownership.
15. FFM segment after `Arena.close()`: do not access again and do not retain raw pointers.
16. Large input cases: do not allocate stack memory of unbounded length; bound both scanning and allocation.

### Useful Review Rules

When reviewing a function that converts from `char *` to Java `String`, require the author to answer **with concrete evidence** for:

- How long is the pointer alive and who is allowed to release it?
- How many bytes are actually accessible from the starting position?
- What is the policy limit in bytes, and does it include the terminator?
- Is there a NUL byte; if not, what must be reported?
- What is the payload encoding; does the decoder use replacement or REPORT?
- Can there be embedded NUL; if so, does the API have a separate length?
- Is copying completed before the source's lifetime expires?
- Are JNI references/FFM scopes and native ownership cleaned up properly?

An answer like “every C string is UTF-8 and strlen is always safe” is a sign that the API design needs fixing.

## 13. Self-Practice Exercises with Answers

**Exercise 1 — computing byte length.** How many bytes minimum does the string `"café"` in UTF-8 need to be stored as a C string? **6 bytes**, consisting of 5 payload bytes and 1 NUL byte. `String.length()` in Java returns **4**, not 5 or 6.

**Exercise 2 — NUL not within limit.** The actual buffer is 6 bytes `63 61 66 C3 A9 00` but `maxScanBytes=5`. May `"café"` be returned? **No**, because the NUL byte at offset 5 lies outside the scanned range [0,5). If the contract requires a C string, an error must be reported for missing terminator within bounds.

**Exercise 3 — empty string.** The buffer has one byte `0x00`; `maxScanBytes=1`. Does reading succeed? **Yes**, payload length = 0, Java receives `""`.

**Exercise 4 — binary data.** Buffer `41 00 42` has three payload bytes, but the function uses a C string. What is the read result? **`"A"`**, not `"A\u0000B"`. To keep all three bytes, an API with explicit length is needed, not a NUL string protocol.

**Exercise 5 — wrong encoding.** A byte `E9` in Latin-1 is `é`. What happens if decoded with strict UTF-8? A lone `E9` byte does not form valid UTF-8; the decoder reports `MalformedInputException` or a form of `CharacterCodingException`.

**Exercise 6 — UTF-8 and Modified UTF-8.** Why can't you always pass UTF-8 from C into `NewStringUTF`? Because JNI requires **Modified UTF-8**, which differs on U+0000 and supplementary characters like emojis.

**Exercise 7 — borrowed pointer.** An SDK returns a pointer valid only until the next API call. Can you store the pointer as a `long` and use it in a future Java callback? **No**, you must copy while the pointer is alive or use a retain/lifetime protocol supported by the SDK.

**Exercise 8 — strnlen.** A pointer is proven to have 7 accessible bytes, and you call `strnlen(ptr, 1024)`. Is it safe? **Not guaranteed**; it can still scan past 7 bytes if NUL is not found. The limit must be no greater than the accessible capacity.

**Exercise 9 — UTF-16LE.** Why not use `memchr(bytes, 0, max)` to find the end of a UTF-16LE string? Because a 0 byte can appear in the representation of normal characters; you must search for a **zero code unit** at the proper width/byte order.

**Exercise 10 — FFM.** A 4096-byte `MemorySegment` contains NUL at offset 200, but the policy only allows 64 bytes. Should you call `segment.getString(0)` on the whole segment and then check the string length? **No**. You must limit the view/scan to at most 64 bytes and reject when no terminator is found within bounds.

## References

- [Oracle Java SE 17 — JNI types: Modified UTF-8](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html): MUTF-8 rules and differences from standard UTF-8.
- [Oracle Java SE 17 — JNI functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `NewStringUTF`, `NewString`, `GetStringUTFChars`, `ReleaseStringUTFChars`, `NewByteArray`, `SetByteArrayRegion`, and JNI exception handling.
- [Oracle Java SE 17 — CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): `REPORT`, `REPLACE`, `IGNORE` policies.
- [Oracle Java SE 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8, ISO-8859-1, and standard charsets.
- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): `getString(offset, charset)`, access bounds, lifetime, and native memory management.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): Java `java.lang.foreign` stabilized in JDK 22.

## Takeaways

**Reading C strings safely requires all four pieces of information: `pointer + actually accessible byte count + character encoding + ownership/lifetime`.** An application limit is an extra layer of protection and **does not prove the allocation has enough bytes**.

Recommended order of steps:

1. Check that the pointer is valid and still within its lifetime, and know the real capacity.
2. Scan for the NUL byte within `min(capacity, maxScanBytes)`, **without reading past it**.
3. If NUL is not found within bounds, return an error instead of guessing.
4. Copy the exact payload bytes while the source is alive.
5. Decode with the declared charset, using a strict decoder when corrupted data must be detected.
6. Release the pointer according to the owner/SDK contract; after copying, the Java `byte[]`/`String` no longer depends on the native source.
7. Do not confuse standard UTF-8 with **JNI Modified UTF-8**, and do not use a NUL byte terminator for binary/UTF-16 data with a different format.

**One sentence to remember:** `strlen` does not make a pointer safe; only a clear contract on **bounds, encoding, and lifetime** allows reading and converting C strings to Java properly.
