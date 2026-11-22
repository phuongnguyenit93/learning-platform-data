# Creating Strings, Reading Length in Character or Byte Units, and Handling Large Data in JNI

## Lesson Objectives

The Java Native Interface (JNI) allows C/C++ to create **java.lang.String** objects, read the contents of Java strings, and transfer data across the JVM–native boundary. However, string operations are only safe when clearly distinguishing **UTF-16 code units**, **Unicode code points**, **byte counts per encoding**, **memory lifetimes**, and **data sizes**.

After this lesson, you can:

1. Use **NewString** with UTF-16 data and **NewStringUTF** with valid **modified UTF-8** data.
2. Accurately understand that **GetStringLength** counts UTF-16 code units, while **GetStringUTFLength** and **GetStringUTFLengthAsLong** count modified UTF-8 bytes.
3. Distinguish between Java String length, Unicode code point count, standard UTF-8, and JNI modified UTF-8, including the U+0000 character and characters outside the BMP.
4. Read strings using **GetStringChars**, **GetStringUTFChars**, or the **GetStringRegion / GetStringUTFRegion** functions; release resources with the matching API pair.
5. Process large strings in chunks, bound allocations, avoid overflowing size multiplications, and avoid holding a critical region for too long.
6. Build, run, and verify Java 17+ examples combined with C/JNI, with deterministic stdout and explainable results.

## 1. Three Length Concepts That Must Not Be Equated

A Java String represents a sequence of **UTF-16 code units** (16-bit units). Java **String.length()** and JNI **GetStringLength** return the number of those UTF-16 units. A Unicode code point outside the Basic Multilingual Plane (BMP) requires **two code units** (surrogate pair); therefore, the number of code points can differ from the String length.

Length measured in **bytes** only has meaning after choosing an encoding. In practice, there are at least two types to distinguish when working with JNI:

- **Standard UTF-8** used in files, HTTP, JSON, many network protocols, and Java's **String.getBytes(StandardCharsets.UTF_8)**.
- **Modified UTF-8 (MUTF-8)** used by several JNI APIs such as **NewStringUTF**, **GetStringUTFChars**, **GetStringUTFLength**, and **GetStringUTFRegion**. MUTF-8 handles the U+0000 character and supplementary characters differently from standard UTF-8.

For example, the same string consisting of **A**, the Unicode null character **U+0000**, **é**, and the emoji **🙂** (U+1F642):

| Component | UTF-16 code units | Standard UTF-8 bytes | JNI modified UTF-8 bytes |
| --- | ---: | ---: | ---: |
| A (U+0041) | 1 | 1 | 1 |
| U+0000 | 1 | 1 | 2 |
| é (U+00E9) | 1 | 2 | 2 |
| 🙂 (U+1F642) | 2 | 4 | 6 |
| **Total** | **5** | **8** | **11** |

The string has **4 Unicode code points**, but **5 UTF-16 code units**. Standard UTF-8 takes **8 bytes**, while modified UTF-8 takes **11 bytes**. There is no single "character count" value that is right for every need; the unit of measurement must be stated explicitly.

### Why is modified UTF-8 different from standard UTF-8?

In JNI's MUTF-8:

- **U+0000** is encoded as two bytes **C0 80** instead of the **00** byte, so valid MUTF-8 data contains no null byte in the middle of a string. This suits certain C APIs that treat **00** as the string terminator.
- Code points outside the BMP are represented as a **UTF-16 surrogate pair**; each surrogate code unit is encoded into **3 bytes**, totaling **6 bytes** for a code point like 🙂. Standard UTF-8 encodes it in **4 bytes**.
- ASCII characters other than U+0000 still use one byte, so ASCII-only strings often lead us to assume standard UTF-8 and MUTF-8 are completely identical.

**Do not pass arbitrary standard UTF-8 bytes directly into NewStringUTF.** UTF-8 bytes containing 4-byte characters or embedded null bytes do not satisfy this function's MUTF-8 contract. If data comes from a file/network, decode it using a standard charset in a controlled manner, or convert the encoding before calling the corresponding JNI API.

## 2. JNI APIs to Know

| API | Purpose | Unit/data | Important requirements |
| --- | --- | --- | --- |
| **NewString(env, jchar*, len)** | Create Java String | **len** UTF-16 code units | May contain U+0000; pointer remains valid during the call |
| **NewStringUTF(env, char*)** | Create Java String from C string | C null-terminated **MUTF-8** byte sequence | Input must be valid MUTF-8, not arbitrary standard UTF-8 |
| **GetStringLength(env, jstring)** | String length | **jsize** counting UTF-16 code units | Not code points or bytes |
| **GetStringUTFLength(env, jstring)** | Length of MUTF-8 representation | **jsize** MUTF-8 bytes | API deprecated in JDK 24+; has size limit |
| **GetStringUTFLengthAsLong(env, jstring)** | MUTF-8 length for large strings | **jlong** MUTF-8 bytes | **Available since JDK 24**; not present in JDK 17 JNI headers |
| **GetStringChars / ReleaseStringChars** | Borrow/obtain copy of UTF-16 data | **const jchar*** | Always release after success |
| **GetStringUTFChars / ReleaseStringUTFChars** | Borrow/obtain copy of MUTF-8 data | **const char*** | Always release after success |
| **GetStringRegion** | Copy a segment into a C-provided buffer | offset/len in UTF-16 code units | Control memory and boundaries |
| **GetStringUTFRegion** | Convert a UTF-16 segment to MUTF-8 in a buffer | offset/len are code units; output is **bytes** | Buffer needs to be larger than code unit count and NUL terminator is not guaranteed |
| **GetStringCritical / ReleaseStringCritical** | Access UTF-16 inside a critical region | **const jchar*** | Do not block or arbitrarily call JNI APIs inside the critical region |

The APIs above are **JNIEnv functions** in C. In C++, JNI provides a different call syntax, but the semantics and constraints are equivalent.

**jsize** is JNI's 32-bit signed integer. It is suitable for Java String/array indices and lengths, but is **not sufficient** to represent every possible MUTF-8 byte length: each UTF-16 code unit can require up to 3 bytes.

## 3. Creating Java Strings from Native Code

### 3.1. NewString: UTF-16 input with explicit length

Signature:

~~~c
jstring NewString(JNIEnv *env, const jchar *unicodeChars, jsize len);
~~~

**jchar** is an unsigned 16-bit unit corresponding to Java char. **len** is the number of jchar elements, **not the byte count** and **not the number of Unicode code points**.

Example:

~~~c
const jchar units[] = {
    0x0041,  // A
    0x0000,  // real U+0000, does not terminate the array
    0x00E9,  // é
    0xD83D,  // high surrogate of U+1F642
    0xDE42   // low surrogate of U+1F642
};

jstring value = (*env)->NewString(env, units, 5);
if (value == NULL) {
    return; // JVM may have thrown OutOfMemoryError.
}
~~~

This is a **C snippet inside a native method**, assuming JNIEnv and an appropriate return type are available; the complete program is in section 8.

**NewString** preserves the U+0000 character because the length is passed explicitly. It also preserves UTF-16 surrogate pairs properly, unlike handling a standard UTF-8 byte buffer. JNI does not assume **jchar*** is a null-terminated C string.

If **len = 0**, an empty string can be created per the contract. If memory is insufficient, the function returns **NULL** and may raise **OutOfMemoryError**; do not continue using a NULL reference.

### 3.2. NewStringUTF: MUTF-8 input

Signature:

~~~c
jstring NewStringUTF(JNIEnv *env, const char *bytes);
~~~

Safe example with ASCII (except U+0000, ordinary ASCII is MUTF-8 compatible):

~~~c
jstring message = (*env)->NewStringUTF(env, "JNI ASCII");
if (message == NULL) {
    return; // Check allocation error before using.
}
~~~

**NewStringUTF** looks for the C string terminator (byte 00); the input pointer must point to a valid, terminated MUTF-8 sequence. For example, **"JNI ASCII"** is compatible. By contrast, a standard UTF-8 byte sequence carrying an emoji will contain a 4-byte sequence that MUTF-8 does not encode that way.

Do not use **NewStringUTF** to accept binary payloads. A 00 byte in the data will terminate the input, and bytes that are not valid MUTF-8 can cause unintended behavior. For byte[] or protocol payloads, keep them as byte[]/buffers with explicit lengths.

### 3.3. Allocation and Ownership After Creation

Both NewString and NewStringUTF return a **jstring**, which is a **local Java reference** when called from normal JNI. The JVM manages the String contents; **do not free(jstring)** and do not assume the string is a malloc buffer.

- Returning a local jstring directly from a native method is valid; the JVM transfers the reference to the Java side.
- If creating many local references in a long native loop, use **DeleteLocalRef** or **PushLocalFrame/PopLocalFrame** properly to avoid accumulation.
- If retaining the reference after the native method returns or across another native thread, you must use a reference with an appropriate lifetime, such as **NewGlobalRef**, and delete it with **DeleteGlobalRef** when no longer used.
- Deleting a local reference only deletes the temporary JNI handle; if Java still holds the String object, the data is not lost.

**Note:** Java String is immutable. The JNI operations above create/read a String; they do not turn a jstring into a region that can be arbitrarily written to from C.

## 4. Reading Length: Code Units, Code Points, and Bytes

### 4.1. GetStringLength

~~~c
jsize units = (*env)->GetStringLength(env, input);
~~~

This value corresponds to **input.length()** in Java: the number of UTF-16 units. If a Java String contains an emoji outside the BMP, that emoji counts as 2. This mechanism does **not** iterate grapheme clusters; a user-perceived character can also consist of multiple combining code points.

Standalone Java example:

~~~java
import java.nio.charset.StandardCharsets;

public final class StringLengthUnits {
    public static void main(String[] args) {
        String value = "A" + (char) 0 + (char) 0x00E9
                + new String(Character.toChars(0x1F642));

        System.out.println("utf16=" + value.length());
        System.out.println(
                "codePoints=" + value.codePointCount(0, value.length())
        );
        System.out.println(
                "standardUtf8Bytes="
                        + value.getBytes(StandardCharsets.UTF_8).length
        );
    }
}
~~~

Run with JDK 17+:

~~~bash
javac StringLengthUnits.java
java StringLengthUnits
~~~

**Exact stdout:**

~~~text
utf16=5
codePoints=4
standardUtf8Bytes=8
~~~

This program **uses Java only** to clarify the three units; it does not require a native library. The corresponding **GetStringLength** result will be **5** when passing the same String into JNI.

### 4.2. GetStringUTFLength and the Limit of jsize

~~~c
jsize bytes = (*env)->GetStringUTFLength(env, input);
~~~

The function returns the number of bytes in **modified UTF-8** (excluding the NUL terminator byte). It is not the standard UTF-8 byte count, not String.length, and not the number of code points.

**Warning for large data:** Starting in **JDK 24**, **GetStringUTFLength** is deprecated because it returns a 32-bit jsize. If the MUTF-8 representation is longer than jsize can hold, current JNI documentation specifies that the old function only returns the byte count up to the last character that fits completely within that limit; therefore the result can be **incomplete** and must not be used to allocate a buffer for an entire large string.

Replacement function on JDK 24+:

~~~c
jlong bytes = (*env)->GetStringUTFLengthAsLong(env, input);
~~~

**GetStringUTFLengthAsLong is not available in JDK 17–23.** Do not insert it into a native library built with JDK 17 JNI headers and claim the program still compiles on JDK 17. When you need to support JDK 17 and very large strings, you can:

- Configure a small input limit so that the multiplication **3 × code unit count** still does not exceed INT_MAX, as in the full example below.
- Or process in chunks with a bounded buffer, accumulating the byte count in **jlong**/**size_t** using a verified encoding algorithm.
- Or avoid converting the entire string to MUTF-8 in the first place: perform the work over UTF-16 regions or use a properly encoded byte stream.

### 4.3. Comparing APIs Across Environments

| What to measure | Java | JNI |
| --- | --- | --- |
| UTF-16 units | **s.length()** | **GetStringLength** |
| Unicode code points | **s.codePointCount(0, s.length())** | Iterate code units following surrogate rules yourself or handle on the Java side |
| Standard UTF-8 bytes | **s.getBytes(UTF_8).length** for small strings, or bounded encoder/stream | Convert encoding explicitly then measure bytes; do not use GetStringUTFLength instead |
| Modified UTF-8 bytes | Not the result of StandardCharsets.UTF_8 | **GetStringUTFLengthAsLong** (JDK 24+); **GetStringUTFLength** for bounded small data |

Byte metrics change depending on the encoding. Do not measure bytes with **strlen** on a jchar*; that is a 16-bit pointer. Even with a char* from a JNI API, only use C-string measurement when there is a guaranteed contract on encoding, terminator, and buffer size.

## 5. Reading String Contents: Borrow Data or Copy by Region?

### 5.1. GetStringChars / ReleaseStringChars (UTF-16)

~~~c
const jchar *chars = (*env)->GetStringChars(env, input, NULL);
if (chars == NULL) {
    return; // There may be a pending OutOfMemoryError.
}

jsize units = (*env)->GetStringLength(env, input);
for (jsize i = 0; i < units; i++) {
    // Read chars[i] as a UTF-16 code unit.
}

(*env)->ReleaseStringChars(env, input, chars);
~~~

This is a snippet, applicable when input is valid. Do not use **strlen(chars)**: each jchar is 16 bits long and the sequence is not guaranteed to have a NUL terminator. The **isCopy** parameter of GetStringChars can be passed to know whether the JVM returned a copy or a view, but it **does not change the release rule**.

Because the JVM may copy, calling GetStringChars for a very large string can create a large temporary buffer. Evaluate actual needs rather than treating the API as zero-copy.

### 5.2. GetStringUTFChars / ReleaseStringUTFChars (MUTF-8)

~~~c
const char *bytes = (*env)->GetStringUTFChars(env, input, NULL);
if (bytes == NULL) {
    return;
}

/* Process bytes according to JNI's modified UTF-8 contract. */

(*env)->ReleaseStringUTFChars(env, input, bytes);
~~~

**GetStringUTFChars** provides MUTF-8 data; it does not automatically turn it into standard UTF-8. If you need bytes to send over HTTP/file/protocol using standard UTF-8, encode to that standard properly. The pointer obtained from JNI is only valid per the contract until ReleaseStringUTFChars is called; do not keep the pointer for another thread or use it after release.

The JNI specification does not require every region returned from string access APIs to have a terminator; use an explicitly determined length instead of arbitrarily calling **strlen** or reading out of bounds.

### 5.3. GetStringRegion: reading UTF-16 in chunks

Function:

~~~c
void GetStringRegion(
    JNIEnv *env, jstring str, jsize start, jsize len, jchar *buffer
);
~~~

Here **start and len are both measured in UTF-16 code units**. JNI copies into a buffer provided by native code; there is no need to obtain a full-string copy and hold it for a long time.

Example reading up to 1,024 code units at a time:

~~~c
enum { CHUNK = 1024 };
jchar buffer[CHUNK];

jsize total = (*env)->GetStringLength(env, input);
for (jsize offset = 0; offset < total; ) {
    jsize remaining = total - offset;
    jsize take = remaining < CHUNK ? remaining : CHUNK;

    (*env)->GetStringRegion(env, input, offset, take, buffer);
    if ((*env)->ExceptionCheck(env)) {
        return;
    }

    for (jsize i = 0; i < take; ++i) {
        /* Process buffer[i], only within [0, take). */
    }
    offset += take;
}
~~~

This is an illustrative snippet inside a void native method with valid input, not a standalone program. Using **total - offset** before adding avoids index overflow; the buffer on the stack only takes **1,024 × sizeof(jchar)** bytes and always has enough room for the requested number of elements.

**Be careful with surrogate pairs at chunk boundaries.** If the algorithm needs to compute Unicode code points rather than UTF-16 units, a high surrogate may land at the end of a chunk while the low surrogate lands at the start of the next chunk. You must save state between two chunks or process using proper code point logic.

### 5.4. GetStringUTFRegion: parameters are UTF-16 characters, output is MUTF-8 bytes

Function:

~~~c
void GetStringUTFRegion(
    JNIEnv *env, jstring str, jsize start, jsize len, char *buffer
);
~~~

**Very dangerous mistake:** allocating a buffer of exactly **len** bytes and calling GetStringUTFRegion. **len** is the number of UTF-16 code units, whereas MUTF-8 output can be up to **3 bytes per code unit**. For a segment of length **k** code units, you need a buffer large enough for up to **3k bytes**, plus **1 byte** if the program wants to place a C-string terminator itself. Before multiplying/adding sizes, integer overflow must be prevented.

Example with chunks of up to 1,024 code units (without creating a full MUTF-8 string):

~~~c
#include <string.h>

/* Snippet inside native method, input is a valid jstring. */
enum { CHUNK = 1024 };
char bytes[3 * CHUNK + 1];

jsize total = (*env)->GetStringLength(env, input);
for (jsize offset = 0; offset < total; ) {
    jsize remaining = total - offset;
    jsize take = remaining < CHUNK ? remaining : CHUNK;

    /*
     * Buffer is zeroed so there is always a 00 byte after the MUTF-8 data.
     * Valid MUTF-8 input does not contain an embedded 00 byte.
     */
    memset(bytes, 0, sizeof(bytes));
    (*env)->GetStringUTFRegion(env, input, offset, take, bytes);
    if ((*env)->ExceptionCheck(env)) {
        return;
    }

    size_t encodedBytes = strlen(bytes);
    /* encodedBytes <= 3 * take. Use immediately then continue to next chunk. */
    (void)encodedBytes;
    offset += take;
}
~~~

The approach above uses a fixed-size buffer, cleared by itself to place a terminator safely as guided in the JNI spec. Because MUTF-8 does not contain a 00 byte inside its content, strlen after the buffer preparation step can measure the encoded part. **Do not** apply this pattern to arbitrary byte data or standard UTF-8 with embedded U+0000 characters, because those bytes can contain real 00 bytes.

If streaming at the Unicode code point level, do not concatenate standard UTF-8 chunks by encoding each surrogate half separately; you must keep state or use an encoder that handles boundaries properly.

## 6. Large Data: Streaming Design, Bounds, and Lifetimes

### 6.1. Avoid copying the entire string when unnecessary

If the goal is only to search for an ASCII character, count delimiters, compute a checksum, or check a simple condition, it is not necessary to call GetStringUTFChars to create MUTF-8 for the entire String. You can use **GetStringRegion** to process small blocks, keeping temporary memory at **O(chunk size)**.

With n code units and chunk size k:

- Additional native memory for one region read: **O(k)**.
- Number of JNI region calls: approximately **ceil(n/k)**.
- Total scanning work: **O(n)**, excluding conversion/encoding if any.

Too small a k increases JNI crossing overhead. Too large a k increases stack/heap buffer usage and can affect cache; measure on the target workload. A block of **4,096 jchar** is often an easy-to-explain starting point, **not a universal optimal parameter**.

### 6.2. Byte length limits and arithmetic checks

**jsize** is used for Java String/array length (32-bit signed); whereas MUTF-8 encoded bytes can be up to roughly 3 times the number of code units. Do not write:

~~~c
/* UNSAFE if n is large: multiplication can overflow. */
jsize bytesNeeded = 3 * n + 1;
char *buffer = malloc((size_t)bytesNeeded);
~~~

This is an **intentionally wrong** example, not for real use. In production code with dynamic multiplication/addition, check against **SIZE_MAX**, memory limit policies, and the **size_t** type before allocating. Sample check example:

~~~c
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>

static char *allocate_mutf8_capacity(size_t units) {
    if (units > (SIZE_MAX - 1u) / 3u) {
        return NULL;
    }
    size_t bytes = units * 3u + 1u;
    return malloc(bytes);
}
~~~

The function above only illustrates the **overflow check**, not a production allocation mechanism: you still need application quotas, malloc failure handling, freeing in the right place, and distinguishing the encoded buffer from the original String. You should not allocate a multi-gigabyte region just because the multiplication does not overflow.

### 6.3. GetStringCritical is only for very short sections

**GetStringCritical / ReleaseStringCritical** may give the JVM an opportunity to avoid some copies, but **does not guarantee zero-copy**. Between the two calls, native code **must not call arbitrary JNI APIs or perform operations that may block**, because the JVM may need to restrict GC/object movement.

Do not hold a critical pointer while:

- Reading/writing files or waiting on the network.
- Calling JNI methods, allocating Java objects, or executing callbacks.
- Waiting on another thread's mutex/condition or doing long-running computation.
- Passing the pointer to an asynchronous task.

For large string scanning tasks, **GetStringRegion** is usually a clearer choice when you want to manage temporary memory and avoid holding a critical region for long. Only optimize with GetStringCritical when you have benchmarks and clearly understand the JNI constraints.

### 6.4. When data is actually a byte stream

Not every large payload should be converted into a Java String:

| Data | Suitable representation |
| --- | --- |
| Decoded Unicode text needing code unit processing | **String / GetStringRegion** |
| Text needing output to file/API in standard UTF-8 | **CharsetEncoder / String.getBytes(UTF_8)** when appropriate, or encode in chunks |
| Binary, compressed, images, protocol frames | **byte[]**, stream, or ByteBuffer; preserve exact bytes and length |
| Large buffers exchanged repeatedly across native | Consider **DirectByteBuffer** and ownership/lifetime contract, measure overhead and check bounds |

With a **jbyteArray**, JNI uses **GetArrayLength**, **GetByteArrayRegion**, and **SetByteArrayRegion** when operating in chunks; byte data does not carry charset information by itself. If choosing **DirectByteBuffer**, you must clearly manage native memory lifetime, capacity limits, and read/write positions; this is a separate design choice, not a reason to force Unicode strings into arbitrary bytes.

For text input from network/file, you should specify **encoding, decode/encode error policy, maximum size, how to handle malformed surrogates, and when to normalize if required**. These properties are not decided by JNI on behalf of the application.

## 7. Unicode Pitfalls When Chunking

### 7.1. UTF-16 code units differ from Unicode code points

An algorithm checking "character count" may require one of three concepts:

- **UTF-16 code units:** the contract of Java String.length, GetStringLength, and the position/length of GetStringRegion.
- **Unicode code points:** a Unicode unit that can take one or two UTF-16 code units; for example, an emoji.
- **Grapheme clusters:** user-perceived characters; can consist of multiple code points, combining marks, or emojis joined by zero-width joiners. Requires a separate segmentation algorithm.

Do not call **GetStringLength** and label it "number of user-visible characters". JNI does not segment grapheme clusters automatically.

### 7.2. Splitting code units safely when only counting ASCII

If the task only counts UTF-16 code units equal to U+0041 (**A**), splitting at any jchar boundary still gives the right result: the letter A is not a surrogate half. The full example in section 8 uses that operation.

However, if you need to read code points one by one:

1. When encountering a high surrogate at the end of a block, save it and wait for the next block.
2. If the next block starts with a low surrogate, combine them into the corresponding code point.
3. If there is no valid low surrogate, handle it according to the defined error/replacement policy.
4. Do not count each surrogate half as a separate emoji.

If you want to produce **standard UTF-8**, the two surrogate halves must be handled together. **GetStringUTFRegion** produces **modified UTF-8**, in which the two surrogate code units are encoded separately, so the result still differs from standard UTF-8.

### 7.3. Embedded NUL is an important test

A Java String can contain an embedded U+0000, for example **"A" + (char) 0 + "B"**, and its length is 3. If converted to a standard UTF-8 byte array, the byte sequence can be **41 00 42**. Using **strlen** on this byte sequence returns 1, not 3.

By contrast, MUTF-8 represents U+0000 as **C0 80**; if you need to send data to a standard UTF-8 system, you must convert the encoding and pass an **explicit byte length**, not rely on a C-style terminator.

## 8. Standalone Runnable Example: Java 17+ with C/JNI

The program demonstrates three groups of APIs:

- **NewString** creates a string consisting of **A, U+0000, é, 🙂** from jchar[].
- **NewStringUTF** creates an ASCII String.
- **GetStringLength / GetStringUTFLength** measures code units and **modified UTF-8 bytes** of a small bounded string.
- **GetStringRegion** processes **1,000,001 UTF-16 code units** in blocks of 4,096 without creating a full-string copy in a native buffer.

For the program to run properly on **JDK 17+**, the C code **does not call GetStringUTFLengthAsLong**, because that function is only available from JDK 24. Instead, the nativeLengths method caps input at **1,000,000 UTF-16 code units** before using GetStringUTFLength; even in the worst case (3 bytes/code unit), the result stays within jsize range.

### Step 1 — Create JniStringMetrics.java

~~~java
import java.nio.charset.StandardCharsets;

public final class JniStringMetrics {
    static {
        System.loadLibrary("jnistringmetrics");
    }

    private JniStringMetrics() {
    }

    private static native String nativeFromUtf16();

    private static native String nativeFromAscii();

    // Only for small strings; limit is checked on the native side.
    private static native long[] nativeLengths(String value);

    // Scan string in chunks without copying the entire String to C.
    private static native long nativeCountAsciiA(String value);

    public static void main(String[] args) {
        String mixed = nativeFromUtf16();
        long[] lengths = nativeLengths(mixed);

        System.out.println("ascii=" + nativeFromAscii());
        System.out.println("utf16Units=" + lengths[0]);
        System.out.println(
                "codePoints=" + mixed.codePointCount(0, mixed.length())
        );
        System.out.println(
                "standardUtf8Bytes="
                        + mixed.getBytes(StandardCharsets.UTF_8).length
        );
        System.out.println("modifiedUtf8Bytes=" + lengths[1]);

        String large = "A".repeat(1_000_000) + "\u00E9";
        System.out.println("largeUtf16Units=" + large.length());
        System.out.println("countA=" + nativeCountAsciiA(large));
    }
}
~~~

In Java, the String **mixed** is the result of **NewString** from native code. The standard **StandardCharsets.UTF_8** part is only used to measure standard UTF-8; modified UTF-8 is measured via JNI. The string **large** has one million letter A's and one letter é; it contains **1,000,001 UTF-16 code units**.

### Step 2 — Compile and Generate the JNI Header

~~~bash
javac -h . JniStringMetrics.java
~~~

The command creates **JniStringMetrics.class** and **JniStringMetrics.h**. To avoid wrong JNI symbol names and signatures, use the header generated by **javac -h** itself from the same source version. The native methods are all **static**, so the JNI entry points receive **JNIEnv \*** and **jclass** as their first two arguments.

### Step 3 — Create jni_string_metrics.c

~~~c
#include "JniStringMetrics.h"

#define CHUNK 4096
#define MAX_SMALL_UNITS 1000000

/* Throw a Java exception in a controlled manner; do not swallow prior errors. */
static void throw_by_name(
        JNIEnv *env, const char *class_name, const char *message) {
    jclass exception_class = (*env)->FindClass(env, class_name);
    if (exception_class == NULL) {
        return; /* FindClass already has a pending exception. */
    }
    (*env)->ThrowNew(env, exception_class, message);
    (*env)->DeleteLocalRef(env, exception_class);
}

/* UTF-16: len is jchar count, U+0000 does not truncate the string. */
JNIEXPORT jstring JNICALL
Java_JniStringMetrics_nativeFromUtf16(JNIEnv *env, jclass cls) {
    const jchar units[5] = {
        0x0041, 0x0000, 0x00E9, 0xD83D, 0xDE42
    };
    (void)cls;
    return (*env)->NewString(env, units, 5);
}

/* NewStringUTF accepts MUTF-8; ordinary ASCII is valid input. */
JNIEXPORT jstring JNICALL
Java_JniStringMetrics_nativeFromAscii(JNIEnv *env, jclass cls) {
    (void)cls;
    return (*env)->NewStringUTF(env, "JNI ASCII");
}

/* Only measure MUTF-8 with GetStringUTFLength when input is bounded. */
JNIEXPORT jlongArray JNICALL
Java_JniStringMetrics_nativeLengths(
        JNIEnv *env, jclass cls, jstring value) {
    (void)cls;

    if (value == NULL) {
        throw_by_name(env, "java/lang/NullPointerException",
                      "value must not be null");
        return NULL;
    }

    jsize units = (*env)->GetStringLength(env, value);
    if (units > MAX_SMALL_UNITS) {
        throw_by_name(env, "java/lang/IllegalArgumentException",
                      "nativeLengths accepts at most 1000000 UTF-16 units");
        return NULL;
    }

    /* At most 3 * 1000000 bytes so jsize will not overflow. */
    jsize bytes = (*env)->GetStringUTFLength(env, value);
    jlong metrics[2] = {(jlong)units, (jlong)bytes};

    jlongArray result = (*env)->NewLongArray(env, 2);
    if (result == NULL) {
        return NULL; /* Possible OutOfMemoryError. */
    }

    (*env)->SetLongArrayRegion(env, result, 0, 2, metrics);
    if ((*env)->ExceptionCheck(env)) {
        return NULL;
    }
    return result;
}

/* Count UTF-16 code units matching letter A on large data. */
JNIEXPORT jlong JNICALL
Java_JniStringMetrics_nativeCountAsciiA(
        JNIEnv *env, jclass cls, jstring value) {
    (void)cls;

    if (value == NULL) {
        throw_by_name(env, "java/lang/NullPointerException",
                      "value must not be null");
        return 0;
    }

    jsize total = (*env)->GetStringLength(env, value);
    jchar buffer[CHUNK];
    jlong count = 0;

    for (jsize offset = 0; offset < total; ) {
        jsize remaining = total - offset;
        jsize take = remaining < CHUNK ? remaining : CHUNK;

        (*env)->GetStringRegion(env, value, offset, take, buffer);
        if ((*env)->ExceptionCheck(env)) {
            return 0; /* Exception propagates to Java. */
        }

        for (jsize i = 0; i < take; i++) {
            if (buffer[i] == (jchar)0x0041) {
                count++;
            }
        }
        offset += take;
    }
    return count;
}
~~~

**Points to verify in the native code:**

1. **NewString** receives exact **5 jchar**; the embedded U+0000 character does not shorten the string.
2. **NewStringUTF** only receives a valid ASCII sequence, without confusing arbitrary standard UTF-8 with MUTF-8.
3. **nativeLengths** guards the jsize byte-length API with an explicit limit. It returns **long[2]** for Java to display easily; if you need to work with truly large MUTF-8 on JDK 24+, use **GetStringUTFLengthAsLong** in an appropriate compilation branch.
4. **nativeCountAsciiA** allocates a fixed **4,096 jchar** buffer on the stack, iterates region by region, and accumulates into **jlong**; it does not allocate a buffer growing with the full string length.
5. After **GetStringRegion**, the code calls **ExceptionCheck** to stop if the JNI operation fails; it does not continue reading a buffer that may not have been validly populated.
6. **ThrowNew** propagates the error to Java; the native side returns a value only to finish the C function and is not a success result when there is a pending exception.
7. No code holds a pointer into String data after a JNI call finishes, there is no unbalanced Get/Release, and there is no long-held critical region.
8. The demo code counts **U+0041** accurately in UTF-16; this is not a grapheme cluster counter or a UTF-8 converter.

### Step 4 — Build the Native Library

Make sure **JAVA_HOME** points to a JDK containing the **jni.h** header and the compiler produces the matching OS/CPU/ABI for the JVM running the program.

**Linux (GCC):**

~~~bash
gcc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  jni_string_metrics.c -o libjnistringmetrics.so
~~~

**macOS (Clang):**

~~~bash
clang -std=c11 -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  jni_string_metrics.c -o libjnistringmetrics.dylib
~~~

**Windows (MSVC Developer Command Prompt):**

~~~bat
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" jni_string_metrics.c /link /OUT:jnistringmetrics.dll
~~~

The three commands are OS-specific alternatives, not three steps to run together. They assume the compiler and **JAVA_HOME** are validly configured. If loading the DLL/SO/dylib fails, check **java.library.path**, native dependencies, architecture, and libc/runtime before suspecting length measurements.

### Step 5 — Run Java

In the directory containing the compiled class and library:

~~~bash
java -Djava.library.path=. JniStringMetrics
~~~

**Exact stdout if build and load succeed:**

~~~text
ascii=JNI ASCII
utf16Units=5
codePoints=4
standardUtf8Bytes=8
modifiedUtf8Bytes=11
largeUtf16Units=1000001
countA=1000000
~~~

If running on **JDK 24+** with native access restrictions and the adapter on the classpath, you may need to grant native access permission explicitly:

~~~bash
java --enable-native-access=ALL-UNNAMED -Djava.library.path=. JniStringMetrics
~~~

On different JDKs, lacking native access permission may result in warnings on **stderr** or rejection depending on configuration; those lines are not part of the sample **stdout**. Permission options are declared per module when the application is modularized.

### Step 6 — Reading the Results by Unit

- **utf16Units=5**: NewString created **5 UTF-16 code units**; matches Java String.length and GetStringLength.
- **codePoints=4**: one emoji outside the BMP uses 2 code units but 1 code point.
- **standardUtf8Bytes=8**: standard UTF-8 encodes U+0000 as 1 byte and 🙂 as 4 bytes.
- **modifiedUtf8Bytes=11**: JNI MUTF-8 encodes U+0000 as 2 bytes and the surrogate pair of 🙂 as 6 bytes.
- **largeUtf16Units=1000001**: Java created 1,000,000 letter A's and one letter é.
- **countA=1000000**: the native method walked the entire string in blocks of 4,096 jchar and counted the exact number of letter A's without reading elements past the buffer.

## 9. Processing Options When Data Is Truly Very Large

### Scenario A — Native code only needs to analyze text

For example: counting ASCII characters, finding delimiters, computing a hash at the UTF-16 level, or analyzing decoded text structure.

**Preferred:** GetStringRegion in chunks and an algorithm keeping minimal state. Check surrogate boundaries if the algorithm works with code points. Do not force the entire String into an MUTF-8 char* just to scan it.

### Scenario B — Native code interfaces with a library requiring standard UTF-8

For example: a JSON library's C API requires **standard UTF-8 + byte length**.

**Preferred:** define an explicit encoding conversion step, provide the exact byte length, and pass a byte[]/buffer or stream. Do not use **GetStringUTFChars** and assume the bytes it returns are standard UTF-8.

If compatibility with a C API accepting null-terminated strings is required, there must be a policy for **U+0000** in the content, because standard UTF-8 has real 00 bytes and can cause the C API to read truncated data. Prefer APIs that allow passing a buffer along with a length.

### Scenario C — Native code builds large Unicode text

It is not necessary to build a huge MUTF-8 char* and then call NewStringUTF. You can:

- Build parts at the Java level with **StringBuilder**, bounding the result size; or pass UTF-16 chunks using an API with explicit length.
- If a single String must be created, understand that a Java String must hold the entire content and has its own length limit and memory overhead.
- When data is a stream that does not yet need to be materialized as a String, keep it as a stream/buffer and consume it in chunks.

To increase throughput, measure JNI crossing overhead, number of data copies, latency, native RSS, Java heap, and GC. **GetStringCritical** is not the best default; only use it when the critical section is short and the benefit has been verified.

### Scenario D — Untrusted input or unusual sizes

Apply validation at the Java/native boundary: maximum limits, byte capacity calculation checks, explicit charset, malformed input handling, and rejecting payloads exceeding quota. For buffers received from native code, only use **NewString** if they are valid UTF-16 code units with a valid size; only use **NewStringUTF** if the bytes are valid MUTF-8 with a C terminator.

## 10. Common Mistakes and Fixes

| Mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| "GetStringLength is the number of user-visible Unicode characters" | JNI counts UTF-16 code units; emojis and graphemes can be multiple units | Distinguish code units, code points, grapheme clusters |
| Using GetStringUTFLength to measure standard UTF-8 | The API computes **modified UTF-8**, which has different rules for U+0000 and supplementary characters | Encode properly with UTF-8/CharsetEncoder then measure bytes |
| Using GetStringUTFLength with very large strings | jsize cannot hold every byte length | JDK 24+: GetStringUTFLengthAsLong; or chunking/capping |
| Passing UTF-8 bytes with emojis into NewStringUTF | 4-byte standard UTF-8 is not how MUTF-8 encodes them | Convert encoding or use NewString from UTF-16 |
| Passing a buffer containing 00 bytes in content into NewStringUTF | Byte 00 terminates a C-string | Use a length-aware API and the right encoding |
| Calling strlen on jchar* | jchar is 16-bit, not a C char string | Use GetStringLength and index-based access |
| Allocating a len-byte buffer for GetStringUTFRegion | len counts code units, but output can be 3× len bytes | Allocate up to 3×len (plus terminator if needed), check overflow |
| Assuming a GetStringUTFRegion buffer is NUL-terminated | Spec does not guarantee a terminator | Use explicit byte length or zero/place terminator safely yourself |
| Forgetting ReleaseStringChars/UTFChars | Holds resources/pins/copies too long | Pair Get with Release accurately on every branch |
| Freeing data returned by GetStringChars | Memory belongs to the JNI contract, not self-owned malloc | ReleaseStringChars, do not free |
| Scanning an entire large String via GetStringUTFChars without consideration | Can create a large copy in native memory | Prefer region by chunk when appropriate |
| Splitting a chunk right between two surrogates but processing each chunk as independent code points | Splits one code point into two halves | Carry high surrogate state across boundaries |
| Holding GetStringCritical during I/O or callbacks | Can block JVM/GC and violate restricted region | Keep critical region very short or use regions |
| Using signed int size to compute 3×length+1 | Can overflow before malloc | Check against size_t/SIZE_MAX and quota |
| Turning binary into String without knowing charset | Loses or corrupts data bytes | Use byte[]/ByteBuffer; decode with explicit charset when needed |
| Calling further JNI APIs when there is a pending exception | Violates the contract on many subsequent calls | Stop, clean up allowed APIs, return exception to Java |

## 11. Pre-Production Checklist

- [ ] State the unit being measured: **UTF-16 code units**, **Unicode code points**, **grapheme clusters**, **UTF-8 bytes**, or **MUTF-8 bytes**.
- [ ] Use **NewString** with jchar[]/UTF-16 with length; **NewStringUTF** only with valid modified UTF-8.
- [ ] Have tests for U+0000, multi-byte BMP characters, supplementary Unicode, and empty input.
- [ ] For JNI strings, use the proper Get/Release pair and do not keep pointers beyond their lifetime.
- [ ] Check for NULL after APIs that can fail; do not continue normal JNI calls when there is a pending exception.
- [ ] For GetStringUTFRegion, prove **buffer byte capacity** is sufficient, with overflow checks and terminator when needed.
- [ ] For large Strings, consider region/chunk or stream; avoid unnecessary full-string copies.
- [ ] If a large MUTF-8 byte length is needed, prefer **GetStringUTFLengthAsLong on JDK 24+**; do not treat the old GetStringUTFLength as an unconditionally complete byte count source.
- [ ] For network/file data, use standard UTF-8 or a clearly specified charset, without mixing with JNI's MUTF-8.
- [ ] If Unicode code points must be processed, maintain surrogate pair state across chunk boundaries.
- [ ] Benchmark batch size, copy/encode time, CPU, heap, native memory, and p95 latency in real workloads.
- [ ] Test against target binaries and JDK; use **-Xcheck:jni** in appropriate test environments.
- [ ] Document size limits and behavior when limits are exceeded; do not perform unbounded allocations.

## 12. Self-Check Questions

**1. A Java String consisting of one emoji outside the BMP has length 2. What does JNI GetStringLength return?**

**Answer:** 2, because that emoji occupies two UTF-16 code units (surrogate pair). The String's Unicode code point count is 1.

**2. Why can GetStringUTFLength and Java String.getBytes(UTF_8).length differ?**

**Answer:** JNI uses modified UTF-8, whereas Java StandardCharsets.UTF_8 is standard UTF-8. U+0000 is encoded by MUTF-8 as 2 bytes instead of 1; a supplementary code point is encoded as two 3-byte sequences instead of one 4-byte sequence.

**3. Which API should be used to create a Java String containing an embedded U+0000 character from a jchar[] array?**

**Answer:** **NewString(env, chars, len)**, because it passes the UTF-16 length explicitly; U+0000 does not terminate the input.

**4. How many bytes minimum does GetStringUTFRegion with len=1000 need in the worst case?**

**Answer:** It may need up to **3000 bytes** for MUTF-8 data; if you want a safe NUL terminator byte, allocate **3001 bytes** after checking for overflow and ensuring the terminator yourself. Here len is 1000 UTF-16 code units.

**5. C code called GetStringChars successfully and then exited the native method. Can it keep the pointer for another thread to use?**

**Answer:** No. The pointer is only valid under the Get/Release contract and requires ReleaseStringChars in a timely manner. If data needs to be kept long-term, copy the needed part into memory owned by native code with its own lifetime.

**6. Why should large data consider GetStringRegion instead of GetStringUTFChars?**

**Answer:** Region allows using a small fixed buffer and reading in chunks, avoiding converting the entire String into a large MUTF-8 region when unnecessary. In return, there are more JNI calls and chunk boundaries must be handled properly by the algorithm.

**7. Code needs to send standard UTF-8 bytes to a C library. Should it call GetStringUTFChars and send them directly?**

**Answer:** No, if the protocol requires standard UTF-8. It must encode according to the standard and pass the byte length; especially check U+0000 and characters outside the BMP.

**8. Can GetStringUTFLengthAsLong be compiled against JDK 17 JNI headers?**

**Answer:** No. This API was added in JDK 24. For native source to support JDK 17, another compatibility mechanism must be used, such as input limits and region-based processing.

## Official References

- [JNI Specification — String Operations, NewString, NewStringUTF, GetStringLength, GetStringUTFLength, GetStringUTFLengthAsLong, GetStringRegion, GetStringUTFRegion](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html).
- [JNI Specification — Modified UTF-8 Strings](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/types.html).
- [Java Character — Unicode code points and UTF-16 surrogate pairs](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html).
- [Java String — length, codePointCount, getBytes](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html).
- [Java StandardCharsets — UTF_8](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/StandardCharsets.html).

**Remember:** **GetStringLength measures UTF-16 code units; GetStringUTFLength measures modified UTF-8 bytes; standard UTF-8 is a different encoding.** When creating a String, choose NewString/NewStringUTF appropriately; when processing large data, prefer region-based algorithms and explicitly control memory bounds, encoding, lifetime, and Unicode boundaries.
