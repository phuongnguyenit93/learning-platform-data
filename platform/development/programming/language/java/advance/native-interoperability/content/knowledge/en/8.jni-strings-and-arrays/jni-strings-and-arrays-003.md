# Pair GetStringChars or GetStringUTFChars with the Corresponding Release Function in JNI

When a native method receives a `jstring` from Java, C cannot treat `jstring` as a `char *` or `wchar_t *` to read it directly. `jstring` is a **JNI reference to a `java.lang.String` object**. To read character units or encoded bytes, native code must call the appropriate JNI API. The two fundamental pairs are:

- **`GetStringChars(env, text, ...)` → `ReleaseStringChars(env, text, chars)`:** retrieves the string as **UTF-16 code units (`jchar`)**.
- **`GetStringUTFChars(env, text, ...)` → `ReleaseStringUTFChars(env, text, utf)`:** retrieves the **modified UTF-8 (`const char *`)** byte representation of the string.

**Unforgettable rule:** After `Get...` succeeds and returns a non-`NULL` pointer, you must call **the exact `Release...` of the same kind**, passing back **the exact original `jstring` and the pointer received**. Each successful acquisition creates a corresponding release requirement. Returning from the native function is not a reliable substitute for `Release`, even though JNI local references are cleaned up on return.

This lesson explains why this rule exists, what happens when you forget or mismatch `Release`, the difference between UTF-16 and modified UTF-8, how to handle error branches, and a compilable Java 17+ / JNI C program for verification.

## 1. `jstring`, character regions, and three lifecycle layers

Look at the Java declaration:

```java
private static native int[] inspect(String text);
```

The JNI header generated from `javac -h` will have a C parameter of type `jstring` for `text`. That is a **JVM-managed handle**, not a pointer to UTF-8 bytes. Below are the three resource layers that must be distinguished:

| Resource | Who manages it? | When is it usable? | What releases it? |
| --- | --- | --- | --- |
| Java `String` object | JVM/GC | While a valid reference exists | Do not `free` the object; manage JNI local/global references per JNI rules |
| `const jchar *` returned from `GetStringChars` | JVM manages the lease/access to characters | From successful `GetStringChars` until `ReleaseStringChars` | **`ReleaseStringChars(env, sameString, samePointer)`** |
| `const char *` returned from `GetStringUTFChars` | JVM manages the lease/modified UTF-8 representation | From successful `GetStringUTFChars` until `ReleaseStringUTFChars` | **`ReleaseStringUTFChars(env, sameString, samePointer)`** |

The JVM may **copy data**, **pin memory**, or create an intermediate representation suitable for the requested encoding. JNI does not require the application to understand that implementation. `Release` notifies the JVM that native code **is no longer using this character region**, allowing the JVM to reclaim the copy or lift memory retention restrictions. Do not depend on a specific GC/JVM strategy.

`GetStringChars` returns `const jchar *`; `GetStringUTFChars` returns `const char *`. The `const` keyword is part of the contract: do not modify content through that pointer. Java `String` is immutable; to transform a string, create your own buffer and then construct a new `jstring`.

**Do not confuse `ReleaseStringChars` with `DeleteLocalRef`:** `DeleteLocalRef` only releases a **JNI reference**; it does not replace ending the access/copy granted by `GetStringChars`. Similarly, `free(chars)` or `delete[] chars` is wrong: the JVM allocates the pointer, and C code does not own that allocation.

## 2. The two API pairs and parameter meanings

### The UTF-16 pair

```c
const jchar *GetStringChars(
        JNIEnv *env, jstring string, jboolean *isCopy);

void ReleaseStringChars(
        JNIEnv *env, jstring string, const jchar *chars);
```

The return value is a sequence of **16-bit `jchar`s**, corresponding to the UTF-16 code units of the Java `String`. `GetStringLength(env, string)` gives **the number of code units**, the same as Java's `String.length()`, not necessarily the number of Unicode code points.

- `jchar` is an unsigned 16-bit JNI type, not identical to an 8-bit C `char`.
- On many Linux systems, `wchar_t` is typically 32-bit; **do not** cast `const jchar *` to `const wchar_t *` and call `wcslen`.
- Do not assume there is a `0` terminator after the data of length `GetStringLength`; inside a Java `String` itself, a valid U+0000 can also be present.
- A Unicode character outside the BMP (e.g. U+1F603, 😃) occupies **two `jchar`s** forming a surrogate pair; `GetStringLength` counts it as 2.

Example recipe for processing the region:

```c
/* Illustrative snippet in a JNI function with valid env and jstring text. */
jsize count = (*env)->GetStringLength(env, text);
const jchar *units = (*env)->GetStringChars(env, text, NULL);
if (units == NULL) {
    return; /* example only suitable in a native function returning void */
}

for (jsize i = 0; i < count; ++i) {
    /* Only read units[i] in the range 0 .. count - 1. */
    /* Processing uses only ordinary C, without modifying units. */
}

(*env)->ReleaseStringChars(env, text, units);
```

`NULL` for the `isCopy` parameter means "no need to know whether the JVM made a copy"; it does **not** mean skipping the release. If `GetStringChars` fails and returns `NULL`, do not call `ReleaseStringChars` with a `NULL` pointer that was never allocated. Error/exception states must be handled according to the JNI contract.

### The modified UTF-8 pair

```c
const char *GetStringUTFChars(
        JNIEnv *env, jstring string, jboolean *isCopy);

void ReleaseStringUTFChars(
        JNIEnv *env, jstring string, const char *utf);
```

This is **JNI's modified UTF-8** representation, which is not necessarily the same as standard UTF-8 used in files, JSON, HTTP, or external C libraries. Key points:

1. U+0000 is encoded as **two bytes `C0 80`** instead of a `00` byte as in standard UTF-8.
2. Each UTF-16 surrogate code unit is encoded separately in 3-byte form. A supplementary code point like 😃 formed by two surrogates will occupy **6 bytes** in modified UTF-8, whereas standard UTF-8 for this code point occupies 4 bytes.
3. ASCII characters U+0001 through U+007F are represented by their corresponding single byte.
4. Byte length may differ from `String.length()`; use `GetStringUTFLength` on JDK 17 within the `jsize` limit, or `GetStringUTFLengthAsLong` on JDK 24+ when needing to compute the exact byte count for very large strings.
5. The JNI specification does not require every string pointer/buffer returned by these APIs to be **NUL-terminated**. Write portable code using the **known length**, and do not unconditionally use `strlen`/`printf("%s")` on pointers obtained from JNI.

Example of reading a modified UTF-8 region:

```c
/* Illustrative snippet in a JNI function, short string and valid text. */
jsize byteCount = (*env)->GetStringUTFLength(env, text);
const char *bytes = (*env)->GetStringUTFChars(env, text, NULL);
if (bytes == NULL) {
    return; /* only suitable for a native function returning void */
}

for (jsize i = 0; i < byteCount; ++i) {
    unsigned char byteValue = (unsigned char)bytes[i];
    /* Use byteValue according to JNI's modified UTF-8 protocol. */
}

(*env)->ReleaseStringUTFChars(env, text, bytes);
```

Do not pass `bytes` as if it were standard UTF-8 to save to a file or external API if the data may contain U+0000 or supplementary code points. If you want **standard UTF-8**, you can convert from Java using `String.getBytes(StandardCharsets.UTF_8)` and exchange a `byte[]` with native code, or use a proper Unicode transcoder on the C side.

## 3. Matching correctly: pair table, types, and mismatch errors

| Acquisition | Pointer type | How to get length | Required Release | Do not use |
| --- | --- | --- | --- | --- |
| `GetStringChars` | `const jchar *` | `GetStringLength` in UTF-16 units | `ReleaseStringChars` | `ReleaseStringUTFChars` |
| `GetStringUTFChars` | `const char *` | `GetStringUTFLength` (JDK 17) or `GetStringUTFLengthAsLong` (JDK 24+) in modified UTF-8 bytes | `ReleaseStringUTFChars` | `ReleaseStringChars` |
| `GetStringCritical` | `const jchar *` | `GetStringLength` | `ReleaseStringCritical` | The `Release` functions of the two pairs above |
| `GetStringRegion` | Writes into a **caller-provided buffer** | Number of UTF-16 units to copy | **No** `ReleaseStringRegion` | Calling `ReleaseStringChars` on the buffer |
| `GetStringUTFRegion` | Writes modified UTF-8 into a **caller-provided buffer** | Sufficient byte capacity for the requested region | **No** `ReleaseStringUTFRegion` | Calling `ReleaseStringUTFChars` on the buffer |

The `Get...` and `Release...` names must be **symmetric**, and the `string` argument must be the same string object used when calling Get. For example:

```c
/* CORRECT: GetStringChars -> ReleaseStringChars */
const jchar *a = (*env)->GetStringChars(env, text, NULL);
if (a != NULL) {
    /* ... */
    (*env)->ReleaseStringChars(env, text, a);
}

/* CORRECT: GetStringUTFChars -> ReleaseStringUTFChars */
const char *b = (*env)->GetStringUTFChars(env, text, NULL);
if (b != NULL) {
    /* ... */
    (*env)->ReleaseStringUTFChars(env, text, b);
}

/* WRONG (do not execute):
 * (*env)->ReleaseStringUTFChars(env, text, (const char *)a);
 * free((void *)a);
 * (*env)->ReleaseStringChars(env, anotherString, a);
 */
```

Mismatched pairs cause the JVM to receive a pointer and data type **that do not match the resource lease** it granted. The consequence is not just a leak: it can corrupt native memory or crash the process. Using a C cast to "get past the compiler" does not make that behavior valid.

### Can the same `jstring` be acquired twice?

Yes, but **each successful Get must have a corresponding Release**. For example, acquire UTF-16 first to analyze code units, Release it, and only then acquire modified UTF-8 to analyze bytes:

```text
jstring text
  │
  ├── GetStringChars ──> const jchar* u16 ──> read ──> ReleaseStringChars(text,u16)
  │
  └── GetStringUTFChars ──> const char* m8 ──> read ──> ReleaseStringUTFChars(text,m8)
```

This sequential approach reduces resource hold time and helps manage error branches. If you intentionally hold multiple leases simultaneously, you must still call `Release` for **each** pointer; avoid confusing the two pointer names.

## 4. `isCopy` is informational, not permission to skip Release

`GetStringChars`/`GetStringUTFChars` take a third parameter `jboolean *isCopy` (or `NULL`). When passing the address of a `jboolean` variable, the JVM reports whether it created a copy at the time of acquisition:

```c
jboolean isCopy = JNI_FALSE;
const jchar *units = (*env)->GetStringChars(env, text, &isCopy);
if (units == NULL) {
    return; /* example only for a JNI native method returning void */
}

/* JNI_TRUE: JVM made a copy; JNI_FALSE: did not make a copy.
 * Both cases require ReleaseStringChars.
 */
(*env)->ReleaseStringChars(env, text, units);
```

Decision table:

| `isCopy` value after successful Get | What can be inferred | Should Release be called? |
| --- | --- | --- |
| `JNI_TRUE` | JVM provided data via a copy | **Yes** |
| `JNI_FALSE` | JVM did not report allocating a copy | **Yes** |
| Information not requested (`NULL`) | Application does not know the JVM strategy | **Yes** |

Do not infer from `JNI_FALSE` that the memory will "live forever on its own" or that the pointer can be kept after `Release`. Do not use `isCopy` to choose `free` or `DeleteLocalRef`. Those decisions belong to the JNI contract, not to the string's implementation type.

## 5. Pointer hold duration and error branches

A native function can have multiple return points: `null` input, Get failure, error-handling logic, Java object creation failure, or a pending Java exception. If a branch exits the function after a successful `GetStringChars` **without Releasing**, that is a resource management bug.

### Sequential two-lease pattern

```c
/* Illustrative snippet for a native function returning jint; valid text.
 * Returns -1 if there is no data to read; if JNI Get fails, returns 0
 * to exit while the error/exception is handled by the caller per contract.
 */
static jint read_two_forms(JNIEnv *env, jstring text) {
    jsize unitsCount = (*env)->GetStringLength(env, text);
    if (unitsCount == 0) {
        return -1;
    }

    const jchar *units = (*env)->GetStringChars(env, text, NULL);
    if (units == NULL) {
        return 0;
    }

    jint firstUnit = (jint)units[0];
    (*env)->ReleaseStringChars(env, text, units);

    const char *utf = (*env)->GetStringUTFChars(env, text, NULL);
    if (utf == NULL) {
        return 0;
    }

    /* Only access byte 0 because the string has at least one code unit. */
    jint firstByte = (jint)(unsigned char)utf[0];
    (*env)->ReleaseStringUTFChars(env, text, utf);

    return firstUnit + firstByte;
}
```

The code above is an **illustrative helper**, not an exported JNI entry point. Returning `0` when Get fails only means the helper stops; it does not replace an error-reporting mechanism. `Get...` can return `NULL` under JNI error / out-of-memory conditions; higher-level calling code must have a contract for handling `NULL` and pending exceptions. For native APIs with return type `jobject`, returning `NULL` allows a pending Java exception to be propagated back to Java.

### When there are multiple resources, use consistent `cleanup`

```c
/* C pseudocode: not a standalone program. */
const jchar *units = NULL;
const char *utf = NULL;

/* ... acquire units when needed ... */
/* ... acquire utf when needed ... */

cleanup:
if (utf != NULL) {
    (*env)->ReleaseStringUTFChars(env, text, utf);
}
if (units != NULL) {
    (*env)->ReleaseStringChars(env, text, units);
}
/* After cleanup, handle the rest according to contract. */
```

In real code, only assign the pointer after Get succeeds and ensure every `goto cleanup` preserves accurate state. Never Release an unallocated pointer or Release twice.

**JNI Exceptions:** There is no guarantee that native operations continue "normally" when a Java exception is pending. If you need to exit back to Java, clean up borrowed resources before returning; string Release functions are among the operations permitted to complete cleanup during a pending exception. Do not call an unrelated sequence of JNI methods once you know a pending exception exists.

## 6. Runnable program: Java 17+ and JNI C on Linux

Complete example demonstrating:

1. `GetStringChars` iterates over UTF-16 code units, counting code units equal to `0`.
2. Calling `ReleaseStringChars` **before** acquiring another representation.
3. `GetStringUTFChars` iterates over modified UTF-8 bytes, counting `C0 80` pairs, then `ReleaseStringUTFChars`.
4. Another function converts ASCII lowercase letters to uppercase in **its own buffer**, Releasing the read region before `NewString` creates a new string.
5. The lengths of UTF-16, modified UTF-8, and the number of Unicode code points differ.

Place the following files in the same directory on **Linux**, with JDK 17+ having `javac` and a C compiler compatible with the JVM architecture. To make the `jsize` length limit clear in the demo, `metrics` accepts at most 1024 UTF-16 units; handling huge files/strings is a different allocation and API-version problem.

### File 1: `JniStringLeaseDemo.java`

```java
import java.util.Arrays;

public final class JniStringLeaseDemo {
    static {
        System.loadLibrary("jnistringlease");
    }

    private static native int[] metrics(String input);
    private static native String asciiUpper(String input);

    public static void main(String[] args) {
        // a, U+0000, Ω, 😃 (a surrogate pair), z.
        String input = "a\0\u03A9\uD83D\uDE03z";

        System.out.println("javaUnits=" + input.length());
        System.out.println("codePoints="
                + input.codePointCount(0, input.length()));
        System.out.println("native=" + Arrays.toString(metrics(input)));

        String upper = asciiUpper(input);
        System.out.println("upperOk="
                + upper.equals("A\0\u03A9\uD83D\uDE03Z"));
    }
}
```

Java `String.length()` counts UTF-16 units: `a` = 1, U+0000 = 1, `Ω` = 1, `😃` = 2, `z` = 1, total **6**. The number of Unicode code points is **5**. `\0` in the Java string literal in the example is an octal escape for the NUL character; it is **not** a Java String terminator.

### File 2: `jni_string_lease_demo.c`

```c
#include "JniStringLeaseDemo.h"  /* generated by javac -h */
#include <stdint.h>             /* SIZE_MAX */
#include <stdlib.h>             /* malloc, free */

static void throw_java(JNIEnv *env, const char *class_name,
                       const char *message) {
    jclass error_type = (*env)->FindClass(env, class_name);
    if (error_type != NULL) {
        (*env)->ThrowNew(env, error_type, message);
        (*env)->DeleteLocalRef(env, error_type);
    }
}

/*
 * 6-number result:
 * [UTF16 units, modified-UTF8 bytes, zero UTF16 units,
 *  encoded NUL count, first UTF16 unit, last UTF16 unit].
 */
JNIEXPORT jintArray JNICALL
Java_JniStringLeaseDemo_metrics(JNIEnv *env, jclass clazz,
                                jstring input) {
    (void)clazz;
    if (input == NULL) {
        throw_java(env, "java/lang/NullPointerException", "input");
        return NULL;
    }

    jsize units_count = (*env)->GetStringLength(env, input);
    if (units_count > 1024) {
        throw_java(env, "java/lang/IllegalArgumentException",
                   "demo accepts at most 1024 UTF-16 units");
        return NULL;
    }

    /* For input <=1024 units, MUTF-8 is at most 3072 bytes. */
    jsize byte_count = (*env)->GetStringUTFLength(env, input);

    /* PAIR 1: jchar * / ReleaseStringChars */
    const jchar *units = (*env)->GetStringChars(env, input, NULL);
    if (units == NULL) {
        return NULL;
    }

    jint zero_units = 0;
    jint first = units_count == 0 ? -1 : (jint)units[0];
    jint last = units_count == 0 ? -1
                                : (jint)units[units_count - 1];
    for (jsize i = 0; i < units_count; ++i) {
        if (units[i] == 0) {
            ++zero_units;
        }
    }

    (*env)->ReleaseStringChars(env, input, units);
    /* Do not use 'units' after the line above. */

    /* PAIR 2: char * / ReleaseStringUTFChars */
    const char *modified = (*env)->GetStringUTFChars(env, input, NULL);
    if (modified == NULL) {
        return NULL;
    }

    jint encoded_nuls = 0;
    for (jsize i = 0; i + 1 < byte_count; ++i) {
        unsigned char a = (unsigned char)modified[i];
        unsigned char b = (unsigned char)modified[i + 1];
        if (a == 0xC0 && b == 0x80) {
            ++encoded_nuls;
            ++i;  /* Skip the second byte of the C0 80 pair. */
        }
    }

    (*env)->ReleaseStringUTFChars(env, input, modified);
    /* Do not assume modified[byte_count] == '\0'. */

    jint values[6] = {
        (jint)units_count, (jint)byte_count,
        zero_units, encoded_nuls, first, last
    };
    jintArray output = (*env)->NewIntArray(env, 6);
    if (output == NULL) {
        return NULL;
    }

    (*env)->SetIntArrayRegion(env, output, 0, 6, values);
    if ((*env)->ExceptionCheck(env)) {
        return NULL;
    }
    return output;
}

/*
 * Convert ASCII 'a'..'z' to 'A'..'Z' while preserving all
 * other UTF-16 code units, including U+0000 and surrogate pairs.
 */
JNIEXPORT jstring JNICALL
Java_JniStringLeaseDemo_asciiUpper(JNIEnv *env, jclass clazz,
                                   jstring input) {
    (void)clazz;
    if (input == NULL) {
        throw_java(env, "java/lang/NullPointerException", "input");
        return NULL;
    }

    jsize count = (*env)->GetStringLength(env, input);
    const jchar *units = (*env)->GetStringChars(env, input, NULL);
    if (units == NULL) {
        return NULL;
    }

    size_t length = (size_t)count;
    if (length > SIZE_MAX / sizeof(jchar)) {
        (*env)->ReleaseStringChars(env, input, units);
        throw_java(env, "java/lang/OutOfMemoryError",
                   "native UTF-16 buffer too large");
        return NULL;
    }

    /* malloc(0) has implementation-defined behavior: allocate at least 1 slot. */
    size_t allocated = length == 0 ? 1 : length;
    jchar *buffer = (jchar *)malloc(allocated * sizeof(jchar));
    if (buffer == NULL) {
        (*env)->ReleaseStringChars(env, input, units);
        throw_java(env, "java/lang/OutOfMemoryError",
                   "cannot allocate native UTF-16 buffer");
        return NULL;
    }

    for (jsize i = 0; i < count; ++i) {
        jchar ch = units[i];
        if (ch >= (jchar)'a' && ch <= (jchar)'z') {
            ch = (jchar)(ch - (jchar)'a' + (jchar)'A');
        }
        buffer[i] = ch;
    }

    /* From here buffer is a C-owned copy, no longer borrowed from the JVM. */
    (*env)->ReleaseStringChars(env, input, units);
    jstring result = (*env)->NewString(env, buffer, count);
    free(buffer);
    return result;  /* If NewString fails, the Java exception is preserved. */
}
```

**Lifecycle check in the C example:**

- `metrics` acquires `GetStringChars`, reads, Releases, and only then calls `GetStringUTFChars`. On every success path, no borrowed pointer remains open when creating `jintArray`.
- Each `Get... == NULL` branch returns immediately because there is no valid lease to Release. When a JNI API call fails, the application must let the error/exception be handled by the caller per contract.
- `asciiUpper` has two allocation failure branches; **both Release `units` before throwing a Java exception**. On the success branch, it also Releases before `NewString`.
- `buffer` was allocated with `malloc`, so `free(buffer)` is valid. Never `free(units)` because `units` is managed by JNI.
- `NewString` takes a `jchar` array and **the number of UTF-16 units `count`**, without needing a NUL terminator. Preserving U+0000 and surrogate pairs is intentional.

The case-conversion function in the example only uppercases **ASCII**. It is not a full Unicode uppercase algorithm (locale rules, characters that map to multiple code points, etc.); for Unicode uppercasing, prefer `String.toUpperCase(Locale.ROOT)` or an appropriate Unicode library at the Java layer.

### Compile and run

Make sure `JAVA_HOME` points to an installed JDK (containing `include/jni.h`), and the `cc` compiler builds a library matching the Java process architecture. The following commands run on Linux, in the directory containing the two files listed above:

```bash
javac -encoding UTF-8 -h . JniStringLeaseDemo.java

cc -std=c11 -Wall -Wextra -shared -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libjnistringlease.so jni_string_lease_demo.c

java -Djava.library.path=. JniStringLeaseDemo
```

`javac -h .` compiles `JniStringLeaseDemo.class` and generates `JniStringLeaseDemo.h` with the exported C function signatures. `System.loadLibrary("jnistringlease")` corresponds to `libjnistringlease.so` on Linux. The `-Djava.library.path=.` option must be passed **before** the main class so the JVM finds the native library. Windows uses `.dll` and the appropriate build process; macOS uses the corresponding native library conventions.

**Expected exact stdout when compiled and loaded successfully:**

```text
javaUnits=6
codePoints=5
native=[6, 12, 1, 1, 97, 122]
upperOk=true
```

Explanation of the `12` modified UTF-8 bytes:

| Component | UTF-16 units | Modified UTF-8 bytes | Why |
| --- | ---: | ---: | --- |
| `a` (U+0061) | 1 | 1 | ASCII |
| U+0000 | 1 | 2 | Special encoding `C0 80` |
| `Ω` (U+03A9) | 1 | 2 | Character in the 2-byte range |
| `😃` (U+1F603) | 2 | 6 | Two surrogates, 3 bytes each |
| `z` (U+007A) | 1 | 1 | ASCII |
| **Total** | **6** | **12** | Differs from code point count = 5 |

Because the string starts with `a` and ends with `z`, the first and last code units have values **97** and **122**, respectively. There is exactly one U+0000 and exactly one `C0 80` pair. `asciiUpper` converts `a`/`z` to `A`/`Z`, while keeping U+0000, `Ω`, and the two surrogates intact, so the Java comparison evaluates to `true`.

This code intentionally relies on **byte count**, without calling `strlen(modified)` or `printf("%s", modified)`. The JNI specification states that returned string regions are not required to be NUL-terminated; assuming a terminator makes code JVM-dependent or causes out-of-bounds reads. `GetStringUTFLength` on JDK 17 returns a `jsize` byte count; for extremely large strings, avoid this limit. In JNI of JDK 24+, `GetStringUTFLengthAsLong` returns `jlong` for the full modified UTF-8 length. The current example limits to 1024 units, so `jsize` is sufficient.

## 7. Why are Java `String.length()`, `strlen`, and `GetStringUTFLength` not interchangeable?

A Java String is a sequence of **UTF-16 code units**, not a sequence of UTF-8 bytes. The NUL character U+0000 is completely valid in a Java `String` and does not mark the end. For example:

```java
String s = "A\0B";
System.out.println(s.length());      // 3 UTF-16 units
System.out.println(s.codePointCount(0, s.length())); // 3 code points
```

Conversely, C's `strlen` only counts the number of bytes before a `0` byte **when a valid C NUL terminator is present**; it does not count Java characters, does not count Unicode code points, and is not guaranteed to be safe on a buffer that is not NUL-terminated. For a Java String containing U+0000, JNI modified UTF-8 encodes it as `C0 80` to give it a distinct representation, but that does not turn `const char *` from JNI into standard UTF-8.

The quantities:

- `GetStringLength(env, text)`: number of UTF-16 code units, type `jsize`. Used with `const jchar *`.
- `GetStringUTFLength(env, text)`: number of **modified UTF-8 bytes**, type `jsize` in JDK 17. Used to determine byte count when the length is known not to exceed the supported range.
- `GetStringUTFLengthAsLong(env, text)`: number of modified UTF-8 bytes as `jlong` in **JDK 24+**, solving the byte count limit of the older API; **cannot** compile as-is with `jni.h` from JDK 17.
- `String.codePointCount(...)`: number of Unicode code points in a Java String range, not directly a byte count and not the number of UTF-16 units when surrogate pairs are present.

Do not use `sizeof(pointer)` to infer capacity: `sizeof(chars)` is only the size of the pointer variable in C. Also do not infer from `GetStringLength` that a `char *` buffer has that exact number of bytes, because modified UTF-8 can require more than one byte per UTF-16 unit.

## 8. Standard encoding and data from external C libraries

If a C library expects **standard UTF-8** (JSON, HTTP, file path protocols, HTTP requests, database clients...), passing the pointer from `GetStringUTFChars` directly can corrupt data:

- U+0000: JNI MUTF-8 uses `C0 80`; standard UTF-8 uses `00`.
- Supplementary characters: JNI MUTF-8 encodes the two surrogates separately; standard UTF-8 uses a single 4-byte sequence for the code point.
- If the C library assumes a NUL-terminated C string, the JNI pointer is not guaranteed by the spec to have a terminator. You need an application-owned buffer with properly constructed capacity and terminator.

A clear way when you must pass **standard UTF-8** from Java:

```java
// Java 17+: explicitly encode standard UTF-8 and pass byte[].
byte[] bytes = value.getBytes(java.nio.charset.StandardCharsets.UTF_8);
sendUtf8Bytes(bytes); // separate native method taking jbyteArray
```

The snippet above is **illustrative** and does not define `sendUtf8Bytes`. A native `jbyteArray` has its own length via `GetArrayLength`; do not measure it with `strlen` because standard UTF-8 of a Java String containing U+0000 can contain `00` bytes. On the C side, if a library requires a C string, you must specify the policy for embedded NULs and allocate an extra terminator byte when valid. For binary/network data, it is best to use a **pointer + length** pair.

In the reverse direction, `NewStringUTF(env, cBytes)` expects **modified UTF-8**, not an arbitrary standard UTF-8 buffer. In real data containing emojis or NUL characters, do not assume the two encodings are interchangeable. For Unicode input from an external library, decode properly to UTF-16 `jchar`s and then call `NewString(env, chars, count)`, or use a `byte[]` bridge and decode explicitly in Java.

## 9. Exceptions, null, local references, and thread safety

### Check null input before calling Get

The JNI specification requires a valid, non-`NULL` `jstring string` for the Get string APIs. Java may pass `null`; native code must choose a policy (for example, throwing `NullPointerException`) **before** calling `GetStringChars`/`GetStringUTFChars`. The runnable example does this using `FindClass("java/lang/NullPointerException")` and `ThrowNew`.

### Get can fail

If `GetStringChars` or `GetStringUTFChars` returns `NULL`, do not dereference it. There may be an allocation failure or pending exception; do not continue executing character-processing code, and do not call Release for a pointer you do not have. If the function returns a reference to Java, returning `NULL` when an exception is pending is a common pattern. In library code, you need a clear contract for the case where the JVM simply returns `NULL` without setting an exception (the spec does not require every Get failure to also throw a Java exception); when needed, report an appropriate Java error after confirming there is no pending exception.

### Java exception after successful Get

If, after borrowing a character region, C code performs more JNI operations that can throw an exception, an error path can easily miss Release. You should minimize JNI calls while holding the pointer, copy necessary data into your own native buffer, Release early, and only then perform operations like `NewString`, `NewIntArray`, `CallObjectMethod`. If an exception is pending, prioritize cleanup (Releasing borrowed regions, cleaning up permitted local refs) and then return control to Java.

### Local/global refs do not replace Release

The `jstring text` of a native method is typically a valid local JNI reference for the duration of the call. Upon return, local refs may be cleaned up automatically, but **that does not mean the JVM automatically releases every access lease properly**. If you need to keep a `jstring` longer than a single native call, create a global reference with `NewGlobalRef` according to a designed lifecycle and `DeleteGlobalRef` later; you must still Release every character region you acquired with Get. Do not pass `JNIEnv *` or a local `jstring` to another thread for use after returning: a native thread must be attached via JNI and obtain its own thread's `JNIEnv *`.

### Do not keep pointers after Release

This is **use-after-release**:

```c
const jchar *p = (*env)->GetStringChars(env, text, NULL);
if (p == NULL) {
    return;  /* illustrative snippet for a void-returning function */
}
(*env)->ReleaseStringChars(env, text, p);

/* WRONG: reading p[0] after Release, even if a previous run worked. */
/* printf("%u", (unsigned)p[0]); */
```

Copy the values you actually need **before Release**. The compiler and GC/JVM can cause use-after-release bugs to appear only intermittently or on another platform.

## 10. Distinguishing from `GetStringCritical` and Region functions

### `GetStringCritical` requires its own `ReleaseStringCritical` pair

`GetStringCritical` returns `const jchar *`, but has **stricter constraints** than `GetStringChars`: between Get and Release, native code must not call arbitrary other JNI functions or cause the current thread to block. The JVM may use pinning to avoid copying, which affects GC progress if the critical region is held for long. Therefore, only use it for **short, non-blocking** processing sections, and Release with the exact `ReleaseStringCritical`.

```c
/* Illustrative snippet in a JNI function; valid text. */
jsize n = (*env)->GetStringLength(env, text);
const jchar *ptr = (*env)->GetStringCritical(env, text, NULL);
if (ptr == NULL) {
    return; /* example C function returning void */
}
jint zeros = 0;
for (jsize i = 0; i < n; ++i) {
    if (ptr[i] == 0) ++zeros;  /* compute in C only */
}
(*env)->ReleaseStringCritical(env, text, ptr);
/* Further JNI calls may be made here if needed. */
```

Do not call `ReleaseStringChars` for `ptr` from `GetStringCritical` even though both have type `const jchar *`. If only processing a small character array, `GetStringRegion` may be simpler.

### `GetStringRegion` and `GetStringUTFRegion` do not create leases needing Release

`GetStringRegion(env, text, start, len, jcharBuffer)` copies the UTF-16 units of the selected region **into a buffer you allocate**. Because this is not a pointer borrowed from the JVM, there is no `ReleaseStringRegion`; the owner of the buffer will `free` or manage it according to how it was allocated.

`GetStringUTFRegion(env, text, start, len, charBuffer)` writes **modified UTF-8** into a C-allocated buffer. In this function, `len` is measured in **UTF-16 units**, while the output capacity must be measured in **bytes**, which can be up to `3 * len` bytes. Do not assume the result has a NUL terminator; if you need a C string, allocate sufficient byte capacity and ensure NUL termination yourself after knowing the actual byte count. Check bounds and pending `StringIndexOutOfBoundsException` if the region is invalid.

Region functions are suitable when the range is known to be small or when you want to own the memory directly, avoiding a Get/Release cycle. Choose based on the contract rather than trying to "skip Release" on the Get functions.

## 11. Common mistakes: symptoms and fixes

| Mistake | Risk | How to handle |
| --- | --- | --- |
| `GetStringChars` succeeds then returns early without Release | Leak / hinders JVM memory management and GC | Every branch must go through `ReleaseStringChars` |
| `GetStringUTFChars` but calling `ReleaseStringChars` | Resource/type mismatch; undefined behavior, possible crash | Call `ReleaseStringUTFChars` |
| `isCopy == JNI_FALSE` so skipping Release | Confusing implementation detail with ownership contract | **Always Release** if Get succeeds |
| `free((void *)chars)` | Freeing memory not owned by C | Only use JNI Release for JNI-allocated pointers |
| `DeleteLocalRef(text)` instead of Release | Only deletes reference, does not end string access lease | Release first, manage local ref separately |
| `strlen` on `jchar *` or on a buffer without NUL guarantee | Wrong units / over-read | `GetStringLength`/`GetStringUTFLength` and loop bounds |
| Treating modified UTF-8 as standard UTF-8 | U+0000 / emoji represented differently | Encode/decode according to protocol standard |
| Casting `jchar *` to `wchar_t *` | `wchar_t` is often not 16-bit | Use `jchar` and UTF-16 units |
| Accessing `ptr[0]` when Java String is empty | Out-of-bounds | Check `GetStringLength > 0` |
| Keeping pointer after `Release` | Use-after-release | Copy necessary data before Release |
| Holding pointer too long during I/O | Increases memory/pinning pressure, hard to handle errors | Release early; perform I/O after copying |
| Using `ReleaseStringCritical` for `GetStringChars` | Wrong API pair | Match exact symmetric names |
| Passing `NULL jstring` to Get | Violates JNI contract, may crash | Check for null and throw Java exception |
| Calling `GetStringUTFLengthAsLong` when building with JDK 17 `jni.h` | New API introduced in JDK 24 | Use version-appropriate API or upgrade JDK |
| Using `NewStringUTF` with standard UTF-8 from network | Invalid MUTF-8, may fail or lose data | Decode standard UTF-8 properly then create Java String |

**Diagnostics:** on supported JVMs, use `java -Xcheck:jni -Djava.library.path=. JniStringLeaseDemo` to enable extra JNI checks. This mode can detect invalid JNI operations but does not guarantee catching every C pointer bug. If a native crash occurs, keep `hs_err_pid*.log`/backtrace and inspect both the Get/Release code as well as Java exceptions.

## 12. Self-check questions

**Question 1.** `GetStringUTFChars` returns a pointer and `isCopy == JNI_FALSE`. Can `ReleaseStringUTFChars` be skipped?

**No.** `isCopy` only indicates whether the JVM made a copy; notifying the JVM that you are done using the pointer is the JNI caller's obligation.

**Question 2.** Native code receives `"A\u0000B"`. Can `strlen` be called to determine `String.length()`?

**No.** The Java String has 3 UTF-16 units, including U+0000. `GetStringLength` returns 3; modified UTF-8 encodes U+0000 in 2 bytes, so the byte count is 4. All byte measurements must use the appropriate API/length, not `strlen` on a buffer lacking a NUL guarantee.

**Question 3.** `GetStringChars` returns a pointer with 6 `jchar`s for `"a\0\u03A9\uD83D\uDE03z"`. Why does the string only have 5 code points?

**Because** the supplementary U+1F603 requires two UTF-16 surrogate units. `GetStringLength` counts units while `codePointCount` counts code points.

**Question 4.** After `GetStringChars` succeeds, `malloc` in C fails. Can the function throw `OutOfMemoryError` and return immediately?

**You must Release before returning.** The correct pattern is `ReleaseStringChars(env, text, chars)`, then create/throw the appropriate exception (if no exception is already pending), then return. Do not use `free(chars)`.

**Question 5.** Can `ReleaseStringChars` be used for a `GetStringCritical` pointer because both have type `jchar *`?

**No.** Each API has its own pair. `GetStringCritical` must be paired with `ReleaseStringCritical` and is also subject to strict restrictions on blocking/arbitrary JNI calls.

**Question 6.** Can the `const char *` from `GetStringUTFChars` be passed directly to a C JSON function that requires standard UTF-8?

**Not guaranteed.** JNI uses modified UTF-8; it differs from standard UTF-8 for U+0000 and supplementary characters. If the API requires standard UTF-8, you need to transcode properly and pass the length or a validly prepared C-string buffer.

## Official documentation

- Oracle JNI Specification — [String Operations, `GetStringChars`/`ReleaseStringChars`, `GetStringUTFChars`/`ReleaseStringUTFChars`](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html#string-operations)
- Oracle JNI Specification — [`GetStringCritical` and `ReleaseStringCritical`](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html#getstringcritical-releasestringcritical)
- Oracle JNI Specification — [`GetStringRegion` and `GetStringUTFRegion`](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html#getstringregion)
- Oracle JNI Specification — [`GetStringUTFLengthAsLong`, since JDK 24](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html#getstringutflengthaslong)
- Oracle JNI Specification — [Modified UTF-8 Strings](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/types.html#modified-utf-8-strings)
- Oracle Java SE 17 — [`String`, `length()`, `codePointCount()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- Oracle Java SE 17 — [`javac -h` generating native headers](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)

**Key takeaway:** `GetStringChars` borrows **UTF-16 units**, `GetStringUTFChars` borrows **modified UTF-8 bytes**. Every borrowed pointer must be released **once with the exact corresponding Release function, with the exact same string and pointer**, regardless of `isCopy`. Measure length in the right units, Release on every error branch, and do not keep pointers after Release.