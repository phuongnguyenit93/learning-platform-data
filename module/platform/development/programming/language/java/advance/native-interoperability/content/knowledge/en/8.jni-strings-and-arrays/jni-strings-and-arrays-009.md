# JNI: Handling Null Characters, Non-BMP Unicode, Empty Arrays, and Bounds Checking

At the Java–native boundary, text and array data can become corrupted even when the code compiles successfully. The root cause usually does not lie in JNI syntax, but in **different interpretations of length**: the U+0000 character is valid in Java yet terminates a NUL-terminated C string; a Unicode character outside the Basic Multilingual Plane (BMP) occupies two UTF-16 code units but one code point; an empty array has length 0 rather than being a readable pointer; and the calculation `start + count` can overflow an integer before being checked.

This lesson belongs to the **JNI Strings and Arrays** group. The goal is to design the data-passing contract properly, distinguish between UTF-16/UTF-8/Modified UTF-8, handle empty and null strings/arrays, check indices safely, respect the borrowing lifetime of JNI pointers, and then run a **Java 17 + C11** example to verify each boundary.

## 1. Five Concepts That Must Be Kept Separate

| Concept | Example | Meaning When Using JNI |
| --- | --- | --- |
| Unicode character **U+0000** | `'\0'`, code point 0 | Is **valid content** in a Java `String`; not synonymous with Java `null` |
| NUL byte **0x00** | C string terminator byte | In a standard C string, `strlen` stops at the first NUL; in a binary buffer, 0x00 is data |
| Java **null reference** | `String s = null` | There is no `jstring`/`jarray` object; many JNI APIs require non-null arguments |
| **Empty string** | `""` | Has a valid `String` object with `GetStringLength == 0` |
| **Empty array** | `new byte[0]` | Has a valid `jbyteArray` object with `GetArrayLength == 0`; distinct from `NULL` |

Ways of measuring “length” also differ:

- `String.length()` and JNI `GetStringLength` return the **number of UTF-16 code units (16-bit)**, which does not necessarily equal the number of Unicode code points.
- `String.codePointCount(0, text.length())` counts code points according to Java rules; each valid surrogate pair is combined into one code point.
- `text.getBytes(StandardCharsets.UTF_8).length` is the **number of standard UTF-8 bytes** encoded by Java; for strings containing lone surrogates, the default encoder may replace malformed data, depending on configuration.
- `GetStringUTFLength` returns the number of **Modified UTF-8 bytes** per JNI, not the number of standard UTF-8 bytes, and does not include a terminator byte that a specific C protocol might require.
- `GetArrayLength(env, array)` returns the **number of elements** in the Java array, not the number of bytes. Use the right unit when passing `jint *`, `jbyte *`, or addresses to a C library.

Do not infer buffer capacity from a pointer, nor infer the number of Unicode code points from a byte count.

## 2. U+0000 in Java Is Not a String Terminator

A Java `String` can contain NUL in the middle:

~~~java
String data = "A" + '\0' + "B";
System.out.println(data.length());          // 3
System.out.println(data.charAt(1) == 0);    // true
~~~

Output:

~~~text
3
true
~~~

This is a Java snippet that can be placed in `main`, not a standalone file. It illustrates that the character in the middle is still counted toward the length and does not truncate the String. Conversely, a C string is typically a byte sequence terminated at `'\0'`:

~~~c
char bytes[] = {'A', '\0', 'B', '\0'};
/* sizeof bytes == 4, but strlen(bytes) == 1.
   This is an illustrative snippet; requires #include <string.h>. */
~~~

Because `strlen` stops at the first NUL byte, it cannot be used to measure an arbitrary binary buffer, including a buffer containing valid standard UTF-8 with U+0000. When calling a C API that takes `const unsigned char *bytes, size_t byte_count`, pass the **pointer together with the byte count**. If the API only accepts a C string, you must know clearly whether it allows U+0000 in the data; if not, you must reject it or use an API with an explicit length.

**Do not confuse Java `'\0'` with Java `null`.** JNI `GetStringLength(env, (jstring)NULL)` is not a valid call just because “the length seems to be 0.” Check for null separately before calling APIs that require a valid object.

### 2.1. Why Does Modified UTF-8 Handle NUL Differently from Standard UTF-8?

JNI has a family of APIs—`GetStringUTFChars`, `GetStringUTFLength`, `GetStringUTFRegion`, and `NewStringUTF`—that use **Modified UTF-8 (MUTF-8)**, not standard UTF-8. In MUTF-8:

- U+0000 is encoded using **two bytes `C0 80`**, instead of the `00` byte of standard UTF-8.
- UTF-16 code units from U+0001 to U+007F use one byte; many BMP values use two or three bytes.
- A non-BMP character is represented as a **surrogate pair**, and then each surrogate is encoded in three bytes: six bytes in total, instead of four bytes in standard UTF-8.
- You must not assume the returned data has standard UTF-8 encoding; a standard UTF-8 parser may reject `C0 80` and individually encoded surrogates.

For example, the String `"A" + '\0' + emoji U+1F600 + "Z"` has:

| Measurement | Result | Explanation |
| --- | ---: | --- |
| Java `String.length()` / JNI `GetStringLength` | **5** | `A` (1) + U+0000 (1) + emoji (2 surrogate units) + `Z` (1) |
| Unicode code points | **4** | `A`, U+0000, U+1F600, `Z` |
| Standard UTF-8, byte count | **7** | 1 + 1 + 4 + 1 |
| JNI Modified UTF-8, byte count | **10** | 1 + 2 + 6 + 1 |

That is why an API receiving `GetStringUTFChars` and an API receiving standard UTF-8 can see the same text as different bytes. If the native API needs standard UTF-8, use an explicit UTF-8 conversion, such as Java `getBytes(StandardCharsets.UTF_8)` and then pass the `byte[]` along with its length. If the native API requires MUTF-8/JNI, use the corresponding JNI API and release the data with the matching release function.

`GetStringUTFChars` returns a pointer borrowed from the JVM, valid until the corresponding `ReleaseStringUTFChars`; do not `free` this pointer. Do not use that pointer after release or keep it as long-lived state in C. For large data lengths, you must also avoid relying on a `jsize` to describe a byte buffer whose size exceeds the 32-bit integer range; check bounds and choose an API/design for large data.

### 2.2. `NewStringUTF` Is Not a Standard UTF-8 Decoder

The `NewStringUTF(env, bytes)` function is specified to take a JNI **Modified UTF-8** byte string. Do not blindly pass a standard UTF-8 buffer containing embedded NUL bytes or four-byte emojis and expect Java to recover the data correctly. UTF-8 data from HTTP, files, JSON, or network protocols needs to be decoded/validated by a standard UTF-8 decoder.

If you intentionally process text as UTF-16 in native code, you can use `NewString(env, jchar_buffer, len)` to create a String with an **explicit length**, preserving U+0000 and code units; you must ensure the buffer is valid, has at least `len` elements, and handle invalid surrogate data according to the application contract.

## 3. Non-BMP Unicode, Surrogate Pairs, and Invalid Characters

The BMP consists of code points from U+0000 to U+FFFF, excluding the U+D800–U+DFFF range reserved for **surrogate code units**, which are not valid Unicode scalar values. A Unicode code point outside the BMP (U+10000–U+10FFFF) is represented in UTF-16 by:

- **High surrogate:** U+D800 to U+DBFF.
- **Low surrogate:** U+DC00 to U+DFFF.
- Two adjacent code units form **one** non-BMP code point.

For example, U+1F600 (😀) is represented by high surrogate `0xD83D` and low surrogate `0xDE00`. For a valid pair, the combining formula is:

~~~c
/* Illustrative snippet; high/low have already been checked to be in the right ranges. */
unsigned int code_point =
    0x10000u +
    (((unsigned int)high - 0xD800u) << 10) +
    ((unsigned int)low - 0xDC00u);
/* Result for D83D DE00: U+1F600. */
~~~

Conversely, a single Java `char` or JNI `jchar` holds only **16 bits**, so it cannot hold all of U+1F600. Do not cast U+1F600 into a C `char`/`jchar` and assume the character has been preserved.

In Java:

~~~java
String smile = new String(Character.toChars(0x1F600));
System.out.println(smile.length()); // 2 UTF-16 code units
System.out.println(smile.codePointCount(0, smile.length())); // 1
System.out.printf("U+%X%n", smile.codePointAt(0)); // U+1F600
~~~

Stdout:

~~~text
2
1
U+1F600
~~~

Additional notes:

1. `GetStringChars` gives a `const jchar *` pointer (UTF-16 code units), not a code point count. When iterating, you must detect high/low pairs and advance the index by an extra unit.
2. `GetStringRegion` also copies by UTF-16 code-unit indices. A slice that cuts in the middle of a surrogate pair produces a string with a lone surrogate, which may not be well-formed Unicode text.
3. A Java `String` can contain an **unpaired surrogate**. If the goal is valid Unicode scalar values, you must check for them yourself and choose an error policy; do not assume every Java String is well-formed Unicode.
4. Java's `codePointCount` treats each unpaired surrogate as one counted unit; this does **not** guarantee the string is valid for a particular standard encoding.
5. A **grapheme cluster** (the user-perceived character) is not synonymous with a code point. Emoji joined by a zero-width joiner or characters with combining marks can consist of multiple code points. JNI processes code units/bytes; if you need to split by “visible character,” you need a Unicode segmentation algorithm at the appropriate layer.

### 3.1. How to Safely Detect Surrogate Pairs in C

~~~c
/* Illustrative snippet: chars points to len valid jchars. */
for (jsize i = 0; i < len; ++i) {
    jchar c = chars[i];
    if (c >= 0xD800 && c <= 0xDBFF &&
        i + 1 < len &&
        chars[i + 1] >= 0xDC00 &&
        chars[i + 1] <= 0xDFFF) {
        /* This is a non-BMP code point. */
        ++i;  /* Skip the paired low surrogate. */
    } else if ((c >= 0xD800 && c <= 0xDBFF) ||
               (c >= 0xDC00 && c <= 0xDFFF)) {
        /* Unpaired surrogate: decide whether to report an error or replace. */
    }
}
~~~

The condition `i + 1 < len` must be checked before reading `chars[i + 1]` to avoid going out of bounds when a high surrogate is at the last element. This code is an illustrative snippet, **not a standalone C program**; the runnable example in section 7 will count zero units, surrogate pairs, and lone surrogates.

## 4. Choosing a JNI String API Based on What You Actually Need

| JNI API | Data | Responsibilities and Notes |
| --- | --- | --- |
| `GetStringLength` | Number of UTF-16 code units (`jsize`) | String must be non-null; returns 0 for an empty String |
| `GetStringChars` | Borrowed pointer to `jchar`/UTF-16 | Check for `NULL`; call `ReleaseStringChars` on success |
| `GetStringRegion` | Copies a UTF-16 region into a caller-provided buffer | Needs capacity in `jchar` count; check `start/len` |
| `GetStringUTFLength` | Modified UTF-8 byte length | Not standard UTF-8 byte count; must consider very large sizes |
| `GetStringUTFChars` | Borrowed pointer to MUTF-8 bytes | Check for `NULL`; call `ReleaseStringUTFChars`; do not `free` |
| `GetStringUTFRegion` | Copies a region as MUTF-8 | Output may **not have a NUL terminator**; caller must provide enough byte capacity |
| `NewString` | Creates a Java String from `jchar *` with `len` | Preserves embedded U+0000; if `len==0`, `unicodeChars==NULL` is allowed |
| `NewStringUTF` | Creates a Java String from MUTF-8 | Does not accept arbitrary UTF-8/`byte[]` like a standard parser |
| `GetStringCritical` | Borrows string region in critical mode | Use only for very short sections, following JNI Critical restrictions |

**Note on length/buffer:** `GetStringUTFRegion` takes `start` and `len` **in UTF-16 code units**, but can produce up to three times as many **MUTF-8 bytes** as code units. Do not allocate a `char[len + 1]` buffer without proving it is sufficient. A simple upper bound for a slice of `len` code units is `3 * len` data bytes, plus one byte if the application **itself** needs a terminator; before multiplying/adding, check for `size_t` overflow. JNI does not guarantee `GetStringUTFRegion` will write a terminator for you.

**Important point on resource management:** C code receiving a pointer from `GetStringChars` or `GetStringUTFChars` cannot assume whether it is a direct view or a copy; JNI is free to choose. When borrowing succeeds, always release, even for read-only access and even when the native function is about to return an error. Do not pass this borrowed pointer to asynchronous native code that retains it after release. Do not call `strlen` on data not confirmed to be a NUL-terminated C string.

A useful option for short data or when you need to limit borrowing time is `GetStringRegion`: you allocate the buffer yourself, JNI copies into it, and no Release call is needed. If working with very long text, you can process it in chunks, but you must preserve surrogate pairs at the boundary between two chunks and validate all indices/lengths.

## 5. Empty Arrays, Null, and How to Read Data

The following values are not equivalent:

~~~java
byte[] missing = null;
byte[] empty = new byte[0];
byte[] oneZero = new byte[] {0};

System.out.println(empty.length);   // 0
System.out.println(oneZero.length); // 1
~~~

Stdout:

~~~text
0
1
~~~

In JNI, check `array == NULL` before `GetArrayLength`. If non-null and length is 0, you can return an empty/valid result immediately without obtaining an element pointer. Do not dereference element 0 or do `array[0]` on an empty array.

**Common options for reading primitive arrays:**

- `GetIntArrayRegion(env, array, start, count, buffer)`: copies an int array slice into a caller-provided `jint *`. No Release is needed, but the buffer must hold at least `count` elements and the indices must be valid. `GetByteArrayRegion` works similarly for `jbyte[]`.
- `GetIntArrayElements`/`GetByteArrayElements`: returns a JNI-provided pointer, which may be a copy or pinned; if acquired successfully, you must call the matching `ReleaseIntArrayElements`/`ReleaseByteArrayElements`. For read-only access, `JNI_ABORT` typically avoids unnecessary copy-back.
- `GetPrimitiveArrayCritical`: use with special restrictions—do not perform I/O, long blocking operations, or disallowed JNI calls while holding a critical pointer. Do not choose this API merely assuming it never copies.
- `NewIntArray(0)`/`NewByteArray(0)`: creates a **valid empty array** if successful. When creating an array from `n` native elements, ensure `n >= 0` and within the `jsize` range, without casting a negative number to a large unsigned value.

**Do not attach special meaning to the pointer result on a 0-element array.** Across specific JVMs/APIs, calling array-elements on an empty array may have different buffer allocation behavior; code should not rely on “zero length ⇒ pointer is always NULL” or “pointer is always non-NULL.” The safe path is to check length and handle the empty case before copying/reading.

For a reference array `jobjectArray`, `GetObjectArrayElement` returns a local reference (which can be `NULL` if the Java element is actually null); when iterating over many elements, delete local refs after use or use an appropriate local frame. `GetArrayLength` still returns the number of elements, not the number of bytes.

## 6. Overflow-Safe Index Checking Before Address Calculation

Suppose Java passes `start` and `count` for an array of length `length`. The acceptance rule for a slice is:

~~~text
start >= 0
count >= 0
start <= length
count <= length - start
~~~

If all four conditions hold, the half-open interval `[start, start + count)` lies within the array; an empty slice `count == 0` is allowed to start at `start == length`. Check **before** performing addition, because the following code is buggy:

~~~c
/* WRONG: start + count can signed-overflow before comparison. */
if (start + count > length) {
    /* reject */
}
~~~

Safe checking with `jint`/`jsize`:

~~~c
/* Illustrative C snippet: all parameters are JNI signed 32-bit integers. */
if (start < 0 || count < 0 ||
    start > length || count > length - start) {
    /* Throw IndexOutOfBoundsException, do not access buffer. */
}
~~~

Thanks to the short-circuit order of `||`, the subtraction `length - start` is only evaluated after confirming `start` is non-negative and not greater than `length`. The case `start == length` and `count == 0` is valid; `start == length` with `count > 0` is rejected. Do not use `start >= length` to reject every slice, as that would accidentally block a valid empty slice.

| length | start | count | Valid? | Reason |
| ---: | ---: | ---: | --- | --- |
| 0 | 0 | 0 | Yes | The only empty slice of an empty array |
| 4 | 4 | 0 | Yes | Empty slice at the end of the array |
| 4 | 1 | 3 | Yes | Reads elements 1, 2, 3 |
| 4 | 3 | 2 | No | Exceeds end of array |
| 4 | -1 | 1 | No | Negative index |
| 4 | 2 | -1 | No | Negative element count |
| 4 | 2147483647 | 2147483647 | No | Exceeds length; must not add before checking |

When converting from `jlong`, `size_t`, `long`, or other C libraries to `jsize`, **check the range before casting**. The `jsize` type is signed 32-bit in JNI, whereas `size_t` is unsigned and can be larger. For native buffers, check `count <= SIZE_MAX / sizeof(T)` **before** multiplying `count * sizeof(T)` and verify capacity in the right units.

**Responsibility takeaway:** Bounds checking in Java is useful for failing early, but the native function must also check because it can be called through other paths or receive invalid data. A bounds-checking bug in C can crash the JVM, rather than merely throwing a safe Java exception.

## 7. Complete JNI Example: Testing NUL, Surrogates, Empty Arrays, and Bounds

The example consists of one Java file and one C file. Java passes text containing **U+0000** and emoji **U+1F600**, JNI counts zero units, valid surrogate pairs, and unpaired surrogates using `GetStringChars`; JNI copies the String back using `NewString` with an explicit length. Two other functions sum an `int[]` slice and sum **unsigned bytes** from a `byte[]` in 64-element chunks using `Get<Type>ArrayRegion`.

Create the directory structure:

~~~text
jni-edges/
├── src/
│   └── demo/
│       └── StringArrayEdges.java
├── native/
│   └── edges.c
└── build/
    ├── classes/
    ├── include/
    └── lib/
~~~

### 7.1. Java 17: file `src/demo/StringArrayEdges.java`

~~~java
package demo;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public final class StringArrayEdges {
    static {
        System.loadLibrary("edges");
    }

    private StringArrayEdges() {
    }

    // [U+0000 units, supplementary pairs, unpaired surrogates].
    private static native int[] inspect(String text);
    private static native String roundTrip(String text);
    private static native long sumIntRange(int[] values, int start, int count);
    private static native long sumUnsignedBytes(byte[] values, int start, int count);

    public static void main(String[] args) {
        String emoji = new String(Character.toChars(0x1F600));
        String sample = "A" + '\0' + emoji + "Z";

        System.out.println("utf16Units=" + sample.length());
        System.out.println("codePoints=" +
                sample.codePointCount(0, sample.length()));
        System.out.println("utf8Bytes=" +
                sample.getBytes(StandardCharsets.UTF_8).length);
        System.out.println("inspect=" + Arrays.toString(inspect(sample)));
        System.out.println("roundTripEqual=" + sample.equals(roundTrip(sample)));

        System.out.println("emptyString=" + Arrays.toString(inspect("")));
        System.out.println("emptyRoundTrip=" + "".equals(roundTrip("")));
        String loneHigh = new String(new char[] {(char) 0xD83D});
        System.out.println("loneSurrogate=" +
                Arrays.toString(inspect(loneHigh)));

        int[] integers = {7, -2, 9};
        System.out.println("sumInts=" + sumIntRange(integers, 1, 2));
        System.out.println("sumEmptyInts=" + sumIntRange(new int[0], 0, 0));

        byte[] bytes = {0, (byte) 0x80, (byte) 0xFF};
        System.out.println("unsignedByteSum=" +
                sumUnsignedBytes(bytes, 0, bytes.length));
        System.out.println("emptyBytes=" +
                sumUnsignedBytes(new byte[0], 0, 0));

        try {
            sumIntRange(integers, 2, 2);
            System.out.println("invalidRangeRejected=false");
        } catch (IndexOutOfBoundsException expected) {
            System.out.println("invalidRangeRejected=true");
        }
    }
}
~~~

Explanation:

- `'\0'` is **a U+0000 character** in Java, not a null reference. Use the appropriate escape literal instead of placing a raw NUL byte in the source file.
- `Character.toChars(0x1F600)` produces two UTF-16 code units. `new String(char[])` preserves the pair.
- `new char[] {(char) 0xD83D}` intentionally creates a high surrogate **without** a low surrogate to test non-well-formed data.
- `byte[]` in Java holds **signed** 8-bit values: `(byte)0x80 == -128`, `(byte)0xFF == -1`. The native function interprets them as unsigned bytes 0–255 per the lesson's contract.
- Both sum calls on empty arrays are valid and return `0`. The arguments `start=2,count=2` on a three-element array are an invalid range; native code explicitly throws `IndexOutOfBoundsException`.

### 7.2. C11: file `native/edges.c`

Run `javac -h` in section 8 first to generate the header `demo_StringArrayEdges.h`; the C source directly includes the generated header so the compiler checks JNI prototypes.

~~~c
#include "demo_StringArrayEdges.h"
#include <stdint.h>

enum { CHUNK_SIZE = 64 };

static void throw_java(JNIEnv *env, const char *class_name,
                       const char *message) {
    jclass ex = (*env)->FindClass(env, class_name);
    if (ex != NULL) {
        (*env)->ThrowNew(env, ex, message);
        (*env)->DeleteLocalRef(env, ex);
    }
}

static int require_text(JNIEnv *env, jstring text) {
    if (text != NULL) {
        return 1;
    }
    throw_java(env, "java/lang/NullPointerException", "text");
    return 0;
}

static int require_array(JNIEnv *env, jarray array) {
    if (array != NULL) {
        return 1;
    }
    throw_java(env, "java/lang/NullPointerException", "array");
    return 0;
}

static int valid_range(JNIEnv *env, jsize length,
                       jint start, jint count) {
    if (start < 0 || count < 0 ||
        start > length || count > length - start) {
        throw_java(env, "java/lang/IndexOutOfBoundsException",
                   "invalid array range");
        return 0;
    }
    return 1;
}

static int is_high(jchar c) {
    return c >= 0xD800 && c <= 0xDBFF;
}

static int is_low(jchar c) {
    return c >= 0xDC00 && c <= 0xDFFF;
}

JNIEXPORT jintArray JNICALL
Java_demo_StringArrayEdges_inspect(JNIEnv *env, jclass owner,
                                   jstring text) {
    (void)owner;
    if (!require_text(env, text)) {
        return NULL;
    }

    jsize length = (*env)->GetStringLength(env, text);
    jint stats[3] = {0, 0, 0};

    if (length > 0) {
        const jchar *chars = (*env)->GetStringChars(env, text, NULL);
        if (chars == NULL) {
            if (!(*env)->ExceptionCheck(env)) {
                throw_java(env, "java/lang/OutOfMemoryError",
                           "GetStringChars failed");
            }
            return NULL;
        }

        for (jsize i = 0; i < length; ++i) {
            jchar c = chars[i];
            if (c == 0) {
                ++stats[0];
            }

            if (is_high(c)) {
                if (i + 1 < length && is_low(chars[i + 1])) {
                    ++stats[1];
                    ++i; /* Valid pair; skip low surrogate. */
                } else {
                    ++stats[2];
                }
            } else if (is_low(c)) {
                ++stats[2];
            }
        }
        (*env)->ReleaseStringChars(env, text, chars);
    }

    jintArray result = (*env)->NewIntArray(env, 3);
    if (result == NULL) {
        return NULL;
    }
    (*env)->SetIntArrayRegion(env, result, 0, 3, stats);
    if ((*env)->ExceptionCheck(env)) {
        return NULL;
    }
    return result;
}

JNIEXPORT jstring JNICALL
Java_demo_StringArrayEdges_roundTrip(JNIEnv *env, jclass owner,
                                     jstring text) {
    (void)owner;
    if (!require_text(env, text)) {
        return NULL;
    }

    jsize length = (*env)->GetStringLength(env, text);
    if (length == 0) {
        /* JNI allows a NULL pointer when len == 0. */
        return (*env)->NewString(env, NULL, 0);
    }

    const jchar *chars = (*env)->GetStringChars(env, text, NULL);
    if (chars == NULL) {
        if (!(*env)->ExceptionCheck(env)) {
            throw_java(env, "java/lang/OutOfMemoryError",
                       "GetStringChars failed");
        }
        return NULL;
    }

    /* NewString uses len, does not search for a NUL terminator. */
    jstring result = (*env)->NewString(env, chars, length);
    (*env)->ReleaseStringChars(env, text, chars);
    return result;
}

JNIEXPORT jlong JNICALL
Java_demo_StringArrayEdges_sumIntRange(JNIEnv *env, jclass owner,
                                       jintArray values, jint start,
                                       jint count) {
    (void)owner;
    if (!require_array(env, values)) {
        return 0;
    }
    jsize length = (*env)->GetArrayLength(env, values);
    if (!valid_range(env, length, start, count)) {
        return 0;
    }
    if (count == 0) {
        return 0; /* Do not call region accessor with an empty buffer. */
    }

    jint chunk[CHUNK_SIZE];
    jlong total = 0;
    jint offset = 0;

    while (offset < count) {
        jint remain = count - offset;
        jint take = remain < CHUNK_SIZE ? remain : CHUNK_SIZE;
        (*env)->GetIntArrayRegion(env, values,
                                  start + offset, take, chunk);
        if ((*env)->ExceptionCheck(env)) {
            return 0; /* Exception propagates to Java. */
        }
        for (jint i = 0; i < take; ++i) {
            total += (jlong)chunk[i];
        }
        offset += take;
    }
    return total;
}

JNIEXPORT jlong JNICALL
Java_demo_StringArrayEdges_sumUnsignedBytes(JNIEnv *env, jclass owner,
                                            jbyteArray values, jint start,
                                            jint count) {
    (void)owner;
    if (!require_array(env, values)) {
        return 0;
    }
    jsize length = (*env)->GetArrayLength(env, values);
    if (!valid_range(env, length, start, count)) {
        return 0;
    }
    if (count == 0) {
        return 0;
    }

    jbyte chunk[CHUNK_SIZE];
    jlong total = 0;
    jint offset = 0;

    while (offset < count) {
        jint remain = count - offset;
        jint take = remain < CHUNK_SIZE ? remain : CHUNK_SIZE;
        (*env)->GetByteArrayRegion(env, values,
                                   start + offset, take, chunk);
        if ((*env)->ExceptionCheck(env)) {
            return 0;
        }
        for (jint i = 0; i < take; ++i) {
            /* jbyte is signed 8-bit; uint8_t interprets 0..255. */
            total += (jlong)(uint8_t)chunk[i];
        }
        offset += take;
    }
    return total;
}
~~~

This is the **complete** C code for the example's JNI library, not a standalone C program with `main`. It uses `jni.h` included by the generated header, and `stdint.h` for `uint8_t`. Common platforms running JDK 17 support 8-bit integers, but the build must still use a compiler and JDK matching the ABI.

### 7.3. Why Does the C Code Avoid Boundary Bugs?

**Strings:** `inspect` retrieves `GetStringLength` and only borrows `GetStringChars` if length is positive; every successful borrow has a matching `ReleaseStringChars`. The loop detects a high surrogate followed by a low surrogate by checking `i + 1 < length` before reading. It counts U+0000 by comparing `c == 0` without truncating at NUL. `roundTrip` passes `length` explicitly to `NewString`, so both NUL and surrogate pairs are preserved. For an empty string, `NewString(env, NULL, 0)` is valid per JNI.

**Arrays:** Both sum functions check null, length, and start/count, then return 0 early for an empty slice. When there is data, `GetIntArrayRegion`/`GetByteArrayRegion` copies at most 64 elements at a time; the native destination uses a stack buffer with an exact capacity of 64 elements and requires no `Release...`. JNI region accessors can throw without signaling via a return code, so the code checks `ExceptionCheck` before reading the chunk. No JVM-managed pointer is retained after the call.

**Overflow:** `start + offset` is only computed after `valid_range`, with `0 <= offset <= count` and `start + count <= length <= INT32_MAX`; it cannot exceed the `jint` range in the example. `total` uses `jlong`, which is sufficient to hold the sum of up to `INT32_MAX` `jint` integers, since the maximum magnitude is approximately `2^62`, smaller than the `jlong` limit. The maximum sum of unsigned bytes `255 * INT32_MAX` also fits in `jlong`. If an algorithm multiplies multiple sizes or adds larger values, that algorithm's own range must still be checked.

**JNI Errors:** The code explicitly throws `NullPointerException` or `IndexOutOfBoundsException` on invalid input. After a failed JNI operation, native code does not proceed to read unavailable data; a pending exception is propagated by the JVM back to Java when native returns. `GetStringChars` returning `NULL` can indicate an allocation failure; the example checks for a pending exception before throwing a fallback `OutOfMemoryError`.

## 8. Building and Running on Java 17+

Run from the `jni-edges` directory. You need a JDK containing `jni.h`, a C11 compiler, and a native binary with the same CPU architecture as the JVM. Set `JAVA_HOME` to the JDK path, not the `bin` directory.

### 8.1. Linux + GCC/Clang

~~~sh
mkdir -p build/classes build/include build/lib
javac -h build/include -d build/classes src/demo/StringArrayEdges.java

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -Ibuild/include native/edges.c \
  -o build/lib/libedges.so

java -Djava.library.path=build/lib -cp build/classes demo.StringArrayEdges
~~~

### 8.2. macOS + Clang

~~~sh
mkdir -p build/classes build/include build/lib
javac -h build/include -d build/classes src/demo/StringArrayEdges.java

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
  -Ibuild/include native/edges.c \
  -o build/lib/libedges.dylib

java -Djava.library.path=build/lib -cp build/classes demo.StringArrayEdges
~~~

### 8.3. Windows x64 + MSVC Developer Command Prompt

~~~bat
mkdir build\classes
mkdir build\include
mkdir build\lib
javac -h build\include -d build\classes src/demo/StringArrayEdges.java

cl /nologo /W4 /O2 /LD ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  /I"build\include" native\edges.c ^
  /link /OUT:build\lib\edges.dll

java -Djava.library.path=build\lib -cp build\classes demo.StringArrayEdges
~~~

The Windows commands above are for **Command Prompt**, using `^` for line continuation. `System.loadLibrary("edges")` automatically maps the logical name to `libedges.so`, `libedges.dylib`, or `edges.dll` depending on the platform. `javac -h` generates `build/include/demo_StringArrayEdges.h`; when changing a Java method signature or package, you must rebuild the header and library.

### 8.4. Expected Stdout

When built/loaded successfully and running the `demo.StringArrayEdges` class, the exact stdout is:

~~~text
utf16Units=5
codePoints=4
utf8Bytes=7
inspect=[1, 1, 0]
roundTripEqual=true
emptyString=[0, 0, 0]
emptyRoundTrip=true
loneSurrogate=[0, 0, 1]
sumInts=7
sumEmptyInts=0
unsignedByteSum=383
emptyBytes=0
invalidRangeRejected=true
~~~

Verification:

- `inspect=[1, 1, 0]`: there is one U+0000, one surrogate pair (emoji), and no lone surrogates.
- `loneSurrogate=[0, 0, 1]`: a lone high surrogate is counted as one UTF-16 structural error if the API requires well-formed Unicode.
- `roundTripEqual=true`: `NewString` with an explicit length preserves the string exactly, including NUL and surrogate pairs.
- `sumInts=7`: takes `-2 + 9` from the slice `start=1,count=2`.
- `unsignedByteSum=383`: the bytes interpreted as unsigned are 0, 128, 255. Java `byte[]` still stores the corresponding bits even though the type is viewed as signed.
- `invalidRangeRejected=true`: native code throws `IndexOutOfBoundsException` and Java catches the expected exception.

The output above is verified by source logic; actual compiler/toolchain behavior depends on the machine and must be tested on the target platform. On load errors, check `java.library.path`, the OS-specific library name, and architecture; on `UnsatisfiedLinkError` when calling, check exported JNI symbols and the header generated from the Java source.

## 9. Buffer-Based APIs: Capacity and Ownership Checklist

Ask these questions before connecting a Java String/array to a C library:

1. **Length unit:** Java UTF-16 units, Unicode code points, UTF-8 bytes, MUTF-8 bytes, or array element count?
2. **NUL:** Is U+0000 allowed in the data? Does the C API take an explicit length or only a C string?
3. **Encoding:** Does the C library require standard UTF-8, UTF-16, MUTF-8, or an arbitrary byte payload? Is there a policy for lone surrogates/invalid input?
4. **Capacity:** Is the native buffer large enough to hold the data plus a terminator if a **specific protocol** requires one? Is checked multiplication/addition used when allocating?
5. **Ownership:** Pointers returned by `GetStringChars`/`GetStringUTFChars`/`Get<Type>ArrayElements` belong to the JVM; call the matching Release when done; do not `free`.
6. **Thread:** Is the borrowed pointer passed to another thread or an asynchronous callback? If so, copy the data into self-owned memory with an appropriate lifetime; do not retain a JNI pointer after release.
7. **Bounds:** Are null, negative start/count, `start<=length`, `count<=length-start`, and type conversions checked before reading?
8. **Failure:** If `Get...` returns `NULL`, `NewString` returns `NULL`, or `Get...Region` throws, does native code return immediately and avoid using uninitialized buffers?

### 9.1. When You Need to Copy Part of a String into a C Buffer

`GetStringRegion(env, string, start, count, jchar_buffer)` operates in UTF-16 code units. If the buffer has `capacity` `jchar` elements, the minimum condition is `capacity >= count`. To avoid overflow when calling `malloc`:

~~~c
/* Illustrative snippet with count >= 0; buffer owned by C. */
size_t n = (size_t)count;
if (n > SIZE_MAX / sizeof(jchar)) {
    /* reject size overflow */
} else {
    jchar *buf = malloc(n * sizeof(jchar));
    /* check malloc; handle n=0 separately before calling GetStringRegion */
}
~~~

An actual C file needs to include `<stdint.h>`/`<stdint.h>` or `<stdint.h>` depending on the `SIZE_MAX` macro and `<stdlib.h>` for `malloc`; the important part is the pattern of checking before multiplication. For `n=0`, there is no need to call the accessor or allocate: handle the empty result separately, avoiding assumptions about `malloc(0)`.

When copying MUTF-8 with `GetStringUTFRegion`, one code unit can produce up to three bytes, so up to `3*n` payload bytes are needed, plus one if **you** want to add a terminator. Do not read with `strlen` unless you have actively ensured a valid terminator, and do not confuse `3*n` with the size of standard UTF-8.

### 9.2. Creating Java Arrays from Native Code

`NewByteArray(env, length)` and `NewIntArray(env, length)` take a non-negative `jsize`; both can create an empty array if length is 0. After creating a new array, only call `SetByteArrayRegion`/`SetIntArrayRegion` with a valid range and a buffer with enough elements; for length 0, no copy is needed.

A native API returning a pointer together with `size_t length` must check `length <= INT32_MAX` (or a meaningful `jsize` limit) before `NewByteArray((jsize)length)`. Do not cast a 64-bit `size_t` to a 32-bit `jsize` first and check afterward, because the value may already be truncated/become negative. When data truly exceeds Java array size, streaming/chunking or another explicitly designed buffer mechanism is needed.

## 10. Boundary Matrix Testing

| Input | Correct Result | Common Mistake |
| --- | --- | --- |
| `""` | `GetStringLength=0`; round-trip yields `""` | Mistaking for null String, accessing element 0 |
| `"A\0B"` | Length 3, U+0000 at index 1 | Using `strlen` and truncating to `"A"` |
| `"A" + U+1F600 + "Z"` | UTF-16 length 4, code points 3 | Counting `jchar`s as code points |
| High surrogate at end of string | Does not read `chars[i+1]` | Out-of-bounds/UB |
| Lone low surrogate | Detected as invalid Unicode scalar sequence | Wrongly paired with previous element |
| `new int[0], start=0,count=0` | Sum 0, reads no elements | Dereferencing `data[0]` |
| `new byte[]{0}` | One element 0, not an empty array | Using NUL sentinel to compute array length |
| `byte[]{(byte)0xFF}` | Unsigned interpretation 255 if API requires | Computing -1 by ignoring signedness |
| `start=length,count=0` | Valid empty slice | Using `start>=length` and wrongly rejecting |
| `start=length,count=1` | Throws range error | Ignoring capacity |
| `start<0` or `count<0` | Throws error before unsigned cast | Casting to `size_t` creating a huge number |
| `start=INT_MAX,count=INT_MAX` on small array | Throws error, does not perform addition | Signed overflow in `start+count` |
| `null` String/array | Reports `NullPointerException` clearly | Calling JNI API that disallows null |
| `GetStringChars==NULL` | Exits with error handling; does not dereference | Continuing to use invalid pointer |
| `Get...Region` with pending exception | Exits before reading destination buffer | Reading incompletely copied data |

In automated test suites, you should check both **content and length units**. Tests that compare text after round-trip without U+0000 or surrogates can miss truncation bugs. Tests that only use arrays with at least one element also fail to exercise the `length==0` path.

When you need to inspect JNI behavior more thoroughly, run:

~~~sh
java -Xcheck:jni -Djava.library.path=build/lib \
  -cp build/classes demo.StringArrayEdges
~~~

`-Xcheck:jni` helps detect some incorrect JNI calls depending on the JVM, but does not guarantee catching every C bug such as invalid pointers, buffer overflows, or data races. With a suitable compiler, also run AddressSanitizer/UndefinedBehaviorSanitizer and test with large inputs on the target OS/architecture.

## 11. Common Mistakes and How to Fix Them

**Mistake 1: Using `GetStringUTFChars` to send standard UTF-8.** MUTF-8 is not standard UTF-8 when U+0000 or non-BMP characters are present. A standard UTF-8 encoder/decoder and explicit byte length are needed for non-JNI APIs.

**Mistake 2: Using `strlen` to measure a Java String.** Java Strings have NUL and UTF-16; C `strlen` measures bytes before a terminator in a C string. Choose `GetStringLength` for UTF-16 units, `codePointCount` when code points are needed, and `byte[].length` when a specific UTF-8 encoding is used.

**Mistake 3: Treating two `jchar`s as two emojis.** One non-BMP code point consists of two surrogate units. When Unicode scalar values are needed, pair them properly and reject/define a policy for unpaired surrogates.

**Mistake 4: Passing a 4-byte UTF-8 emoji into `NewStringUTF`.** JNI `NewStringUTF` expects MUTF-8; non-JNI UTF-8 input must be decoded explicitly first.

**Mistake 5: Treating an empty array as a pointer with at least one element.** `GetArrayLength == 0` means no elements may be read; return an empty/sum-0 result without dereferencing.

**Mistake 6: Checking `start + count <= length` using signed types.** The addition can overflow before comparison. Replace with the guards `start>=0, count>=0, start<=length, count<=length-start`.

**Mistake 7: Forgetting to release JNI pointers.** `GetStringChars` and `Get...ArrayElements` require a matching Release when returning a valid pointer, even for read-only access. Do not treat `NULL` or an empty array as a reason to call Release with a pointer that was not validly acquired.

**Mistake 8: Confusing bytes with elements.** `memcpy` and UTF-8 measure bytes, `GetIntArrayRegion` measures `jint` counts, and `GetStringRegion` measures UTF-16 units. Each API has its own unit.

**Mistake 9: Mixing Java errors and native errors.** A JNI region accessor returning void can still throw; check for a pending exception before using the destination buffer. Native code must not arbitrarily ignore an exception and continue reporting success.

**Mistake 10: Splitting graphemes by code point.** A glyph/emoji can consist of multiple code points; surrogate/code-point parsing only solves encoding, not display-level language rules.

## 12. Self-Check List Before Implementing a JNI String/Array API

- Java `null` and empty String/array have **distinct** handling paths, reporting errors per contract.
- NUL U+0000 is intentionally allowed or rejected; no data loss due to C string functions.
- **UTF-16**, **standard UTF-8**, or **MUTF-8** is chosen according to the consumer; they are not treated as interchangeable.
- Length is **bytes / UTF-16 code units / code points / elements**, documented directly in prototypes and docs.
- Surrogate pairs, unpaired surrogates, and the policy for non-well-formed Unicode are checked.
- Buffers are allocated with capacity in the right units; overflow is checked before `count*sizeof(T)`, `3*len+1`, or offset addition.
- An empty slice `(start==length,count==0)` is valid if specified by the API; accessors are not called carelessly with zero length.
- No dereferencing null pointers, no accessing `index==length`, no overflow in `start+count`.
- Every JNI borrowed pointer is released in a matching pair on all exit paths.
- Errors are checked after JNI functions returning `NULL` and after `Get...Region` returning void; exceptions are propagated to Java appropriately.
- Empty arrays, non-BMP Unicode, embedded U+0000, negative/oversized slices, and byte data containing 0x00/0x80/0xFF are tested.
- The native library is built for the right OS/ABI; real tests are run with the target JDK and JNI checks enabled when appropriate.

**Core principle:** JNI does not automatically know whether you are counting bytes or Unicode, nor does it turn empty data into a dereferenceable buffer. Clearly defining the encoding, length unit, ownership, and index range **before** accessing native memory is how you avoid data loss and out-of-bounds bugs.

### References

- Oracle, [JNI Specification — Functions (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): String Operations, Array Operations, Get/Release, Region, NewString, and exception contracts.
- Oracle, [JNI Specification — Types (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html): `jchar`, `jsize`, `jstring`, and primitive array types.
- Oracle, [JNI Specification — Design Overview (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): Java exceptions and JNI calling conventions.
- Oracle, [Java Language Specification `3.1–3.2 (Java 17)](https://docs.oracle.com/en/java/javase/specs/jls/se17/html/jls-3.html): UTF-16 and supplementary characters.
- Oracle, [Java SE 17 String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `length`, `codePointCount`, `getBytes`.