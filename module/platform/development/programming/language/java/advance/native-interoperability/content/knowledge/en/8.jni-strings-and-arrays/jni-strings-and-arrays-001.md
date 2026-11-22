# Java's UTF-16 and JNI's Modified UTF-8 Differ from Standard UTF-8

> **Scope:** Java Advance → Native Interoperability → JNI Strings and Arrays. The goal is to understand exactly what character data crosses the Java–native boundary, when the number of characters differs from the number of bytes, and why strings obtained via `GetStringUTFChars` cannot by default be used as standard UTF-8 for files, networks, or C/C++ libraries.

## 1. Three Concepts That Must Not Be Equated

A **Unicode code point** is an abstract character value, for example `U+0041` (A), `U+00E9` (é), `U+1F600` (😀). **UTF-16** and **UTF-8** are ways of encoding code points. JNI also has **Modified UTF-8 (MUTF-8)**, a variant intentionally different from standard UTF-8.

In Java, `String` is observed through a sequence of **16-bit UTF-16 code units**. `String.length()` counts code units; `charAt(i)` returns one code unit; `codePointCount(...)` counts code points according to surrogate pair rules. A character outside the Basic Multilingual Plane (BMP), such as 😀, requires **two code units** in UTF-16 (a high surrogate and a low surrogate). Therefore:

```java
String smile = new String(Character.toChars(0x1F600));
System.out.println(smile.length());                   // 2 UTF-16 code units
System.out.println(smile.codePointCount(0, 2));        // 1 code point
```

This is an illustrative Java snippet; a complete runnable program is in section 4.

One should not infer that every `String` in the JVM occupies `2 * length()` bytes on the heap. Modern JVMs may use **compact strings** or other internal representations; the Java/JNI API contract still uses the UTF-16 code unit model when accessed via `char`/`jchar`.

Three forms to distinguish:

| Form | Observed unit | Key point | Related APIs |
|---|---|---|---|
| **UTF-16 (Java/JNI)** | 16-bit code unit (surrogate pairs for code points outside BMP) | Allows `U+0000` code unit, has no concept of a C terminating byte | `String.length`, `charAt`, `GetStringChars`, `GetStringRegion`, `NewString` |
| **Standard UTF-8** | Byte sequence of 1–4 bytes/valid code point | `U+0000` → `00`; 😀 → one **4-byte** sequence; used for files, network, JSON, text APIs | `getBytes(StandardCharsets.UTF_8)`, `new String(bytes, UTF_8)`, `CharsetDecoder` |
| **JNI Modified UTF-8** | Byte sequence, encoding each UTF-16 code unit into 1–3 bytes | `U+0000` → `C0 80`; 😀 → **two 3-byte groups**; used by JNI APIs with the `UTF` suffix | `GetStringUTFChars`, `GetStringUTFLength`, `GetStringUTFRegion`, `NewStringUTF` |

**Key takeaway:** The `UTF` suffix in `GetStringUTFChars` does **not** mean standard UTF-8. The JNI Specification defines it as **modified UTF-8**.

## 2. Byte Mechanism: Where Does MUTF-8 Differ from Standard UTF-8?

JNI's MUTF-8 encodes UTF-16 code units:

- `U+0001` to `U+007F` → **1 byte**, same representation as standard UTF-8 (e.g., A → `41`).
- `U+0000` → **2 bytes `C0 80`** instead of `00`. This avoids having a NUL byte inside the character payload.
- `U+0080` to `U+07FF` → **2 bytes**, usually the same as standard UTF-8 (é → `C3 A9`).
- `U+0800` to `U+FFFF` → **3 bytes per UTF-16 code unit**. For valid non-surrogate BMP code points, the three bytes usually match standard UTF-8.
- For code points **outside the BMP**, Java has *two* surrogate code units. MUTF-8 encodes each surrogate into 3 bytes, totaling **6 bytes**. Standard UTF-8 encodes that code point directly into **4 bytes**.

Concrete byte table (hex written in transmission order):

| Content | UTF-16 code unit | Standard UTF-8 | JNI Modified UTF-8 |
|---|---|---|---|
| `A` (U+0041) | `0041` | `41` | `41` |
| `NUL` (U+0000) | `0000` | `00` | `C0 80` |
| `é` (U+00E9) | `00E9` | `C3 A9` | `C3 A9` |
| `😀` (U+1F600) | `D83D DE00` | `F0 9F 98 80` | `ED A0 BD ED B8 80` |

Why does 😀 become `ED A0 BD ED B8 80`?

1. Code point `U+1F600` converts to the UTF-16 pair `D83D` (high surrogate) + `DE00` (low surrogate).
2. MUTF-8 encodes `D83D` into `ED A0 BD`.
3. MUTF-8 encodes `DE00` into `ED B8 80`.
4. Concatenated in order into six bytes: `ED A0 BD ED B8 80`.

In standard UTF-8, `ED A0 BD` represents a **surrogate code point**, which is not accepted in Unicode scalar values; `C0 80` is also an invalid **overlong encoding** for U+0000. Therefore, a **strict** UTF-8 decoder must reject these sequences. Do not treat MUTF-8 as a standard UTF-8 string just because the word "UTF-8" appears in the API name.

### Why Does MUTF-8 Exist?

Traditional C uses byte strings terminated by `'\0'` (byte `00`). If Java content containing U+0000 were sent as standard UTF-8, C functions based on `strlen` would treat `00` as the terminator, **truncating** the data after it. MUTF-8 encodes U+0000 as `C0 80` to avoid NUL inside the payload. When an API requires a NUL-terminated C string (such as `NewStringUTF`), the caller still must prepare a `00` byte **at the end of the buffer**.

**Important note:** The JNI documentation does not guarantee that every buffer obtained from `GetStringUTFChars` or `GetStringUTFRegion` is NUL-terminated. Therefore, even though MUTF-8 avoids NUL in the payload, correct native code still uses **explicit lengths**, and only appends a `00` byte itself when the API contract specifically requires a NUL-terminated C string.

## 3. One String, Three Different Counts

Consider the string:

```java
String sample = "A" + '\0' + "\u00E9"
        + new String(Character.toChars(0x1F600));
```

In it there are **4 code points**: A, NUL, é, and 😀. However, the counts for each representation are:

```text
Unicode code points (4) : U+0041 | U+0000 | U+00E9 | U+1F600

UTF-16 code units (5)  : 0041 | 0000 | 00E9 | D83D | DE00

Standard UTF-8 (8 bytes): 41 | 00 | C3 A9 | F0 9F 98 80

JNI MUTF-8 (11 bytes)  : 41 | C0 80 | C3 A9 | ED A0 BD ED B8 80
```

Therefore:

- `sample.length() == 5`, because `String.length()` counts UTF-16 code units.
- `sample.codePointCount(0, sample.length()) == 4`.
- `sample.getBytes(StandardCharsets.UTF_8).length == 8`, because standard UTF-8 encodes valid code points directly.
- The size of the **MUTF-8 payload** is **11 bytes**; not counting the C-terminating NUL byte or framing bytes of another protocol.

One cannot substitute `GetStringLength` with `GetStringUTFLength` or vice versa. One measures code units; the other measures **MUTF-8** bytes, not standard UTF-8. One cannot use the code point count to allocate a byte buffer without accounting for the encoding.

## 4. Java 17+ Practice: Seeing the Bytes Before Writing JNI

We can reproduce the MUTF-8 payload using `DataOutputStream.writeUTF` to study how it encodes. This API writes **two length bytes in front of** MUTF-8, whereas JNI string APIs do **not** use those two prefix bytes. The example strips the prefix to compare. `writeUTF` only supports payloads up to 65,535 bytes; it is **not** a general-purpose MUTF-8 encoder for arbitrarily large `String`s.

**File `EncodingProbe.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.StringJoiner;

public class EncodingProbe {
    private static final HexFormat HEX =
            HexFormat.ofDelimiter(" ").withUpperCase();

    public static void main(String[] args) throws Exception {
        String sample = "A" + '\0' + "\u00E9"
                + new String(Character.toChars(0x1F600));

        StringJoiner units = new StringJoiner(" ");
        for (int i = 0; i < sample.length(); i++) {
            units.add("%04X".formatted((int) sample.charAt(i)));
        }

        byte[] utf8 = sample.getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeUTF(sample);
        }

        byte[] wire = buffer.toByteArray();
        byte[] modifiedUtf8 = Arrays.copyOfRange(wire, 2, wire.length);

        boolean restored;
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(wire))) {
            restored = sample.equals(in.readUTF());
        }

        System.out.println("UTF-16 units: " + units);
        System.out.println("Length/code points: " + sample.length()
                + "/" + sample.codePointCount(0, sample.length()));
        System.out.println("Standard UTF-8: " + HEX.formatHex(utf8));
        System.out.println("Modified UTF-8: " + HEX.formatHex(modifiedUtf8));
        System.out.println("writeUTF prefix: " + HEX.formatHex(wire, 0, 2));
        System.out.println("readUTF round-trip: " + restored);
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 EncodingProbe.java
java EncodingProbe
```

**stdout (Java 17+):**

```text
UTF-16 units: 0041 0000 00E9 D83D DE00
Length/code points: 5/4
Standard UTF-8: 41 00 C3 A9 F0 9F 98 80
Modified UTF-8: 41 C0 80 C3 A9 ED A0 BD ED B8 80
writeUTF prefix: 00 0B
readUTF round-trip: true
```

The prefix bytes `00 0B` are a 16-bit big-endian integer with value **11**, indicating **11 bytes of MUTF-8 payload**, not the number of UTF-16 code units. `DataInputStream.readUTF` requires such a framing prefix; `NewStringUTF` instead requires a **MUTF-8 payload with a trailing NUL byte**. If you pass `wire` directly (starting with `00 0B`) into `NewStringUTF`, the first `00` byte is treated as the C string terminator: these are two different protocols.

## 5. JNI String APIs and Units of Measurement

| JNI API (C) | Data form | Length/result | Usage rules |
|---|---|---|---|
| `GetStringLength(env, s)` | UTF-16 | `jsize` = **code unit count** | Corresponds to `String.length()` |
| `GetStringChars(env, s, &isCopy)` | `const jchar *`; UTF-16 units | Use `GetStringLength`, **do not assume NUL terminator** | Call `ReleaseStringChars` after use; may be a copy |
| `GetStringRegion(env, s, start, len, buf)` | Copies `jchar` region | `start`, `len` measure UTF-16 code units | Caller allocates at least `len * sizeof(jchar)` and checks bounds |
| `NewString(env, chars, len)` | Input `jchar *` UTF-16 | `len` = code unit count; no NUL terminator needed | Use when you have UTF-16 code units, including U+0000 |
| `GetStringUTFLength(env, s)` | MUTF-8 | `jsize` = **MUTF-8 byte count** | Present since older JDKs; **deprecated since JDK 24** because value can exceed `jsize` |
| `GetStringUTFLengthAsLong(env, s)` | MUTF-8 | `jlong` = **MUTF-8 byte count** | Available since **JDK 24**; suitable for checking large sizes |
| `GetStringUTFChars(env, s, &isCopy)` | `const char *` MUTF-8 | Use explicit MUTF-8 length | Call `ReleaseStringUTFChars`; do not assume standard UTF-8 |
| `GetStringUTFRegion(env, s, start, len, buf)` | Copies MUTF-8 into buffer | `start`/`len` measure **UTF-16 code units**, result has a **different byte count** | Ensure sufficient buffer; do not expect NUL terminator |
| `NewStringUTF(env, bytes)` | Input **MUTF-8 C string** | Reads up to trailing `00` byte | Only pass valid MUTF-8, do not pass arbitrary standard UTF-8 |
| `GetStringCritical / ReleaseStringCritical` | May pin/copy UTF-16 | Use by UTF-16 units | Inside critical region, do not make arbitrary JNI calls or blocking operations |

### About Memory Release

`GetStringChars` and `GetStringUTFChars` may return a pointer to a copy or to a native region managed by the JVM. The pointer is only valid until the corresponding `Release...` is called. **Do not** call `free()` on the pointer returned by JNI. The boolean `isCopy` is diagnostic information and does **not** change the release responsibility. If JNI fails allocation and returns `NULL`, handle the pending exception/error condition and do not dereference.

`GetStringRegion` and `GetStringUTFRegion` write into a buffer **provided by the caller**, so no corresponding `Release` call is needed; conversely, the caller must ensure capacity, lifetime, and how length is measured.

### About Large Sizes

A `String` can have `GetStringLength` (UTF-16 units) within the `jsize` limit while its MUTF-8 representation is **many more bytes** long, so 32-bit `GetStringUTFLength` cannot always represent the required size. Starting in JDK 24, `GetStringUTFLengthAsLong` allows measuring as `jlong`; before creating a `jbyteArray` or allocating a C buffer, one must still check array/`size_t`/overflow limits and use a chunking strategy if necessary. All demo snippets here use very short strings, so the older API suffices to illustrate Java 17+.

## 6. Complete JNI Practice: Getting UTF-16, MUTF-8, and Creating a String from MUTF-8

This example builds a small native library, lets Java see **the exact MUTF-8 bytes that JNI produces**, and verifies that `NewStringUTF` recreates a Java string containing NUL and an emoji.

Build environment: **JDK 17+, Linux, GCC, and `JAVA_HOME` pointing to the JDK**. On other operating systems, substitute the corresponding compiler, library extension, and JNI header paths.

### 6.1. File `UtfBridgeDemo.java`

```java
import java.util.HexFormat;
import java.util.StringJoiner;

public class UtfBridgeDemo {
    static {
        System.loadLibrary("utfbridge");
    }

    private static native char[] utf16Units(String value);
    private static native byte[] modifiedUtf8Bytes(String value);
    private static native String createFromModifiedUtf8();

    public static void main(String[] args) {
        String input = "A" + '\0' + "\u00E9"
                + new String(Character.toChars(0x1F600));

        char[] units = utf16Units(input);
        StringJoiner unitsHex = new StringJoiner(" ");
        for (char unit : units) {
            unitsHex.add("%04X".formatted((int) unit));
        }

        byte[] modified = modifiedUtf8Bytes(input);

        System.out.println("JNI UTF-16: " + unitsHex);
        System.out.println("JNI MUTF-8: "
                + HexFormat.ofDelimiter(" ").withUpperCase()
                        .formatHex(modified));
        System.out.println("NewStringUTF round-trip: "
                + input.equals(createFromModifiedUtf8()));
    }
}
```

The first two methods take a `String` and return data as `char[]`/`byte[]` solely to observe the encoding. The last method creates a new `String` from a valid MUTF-8 byte sequence with a NUL terminator.

### 6.2. Generating the JNI Header

```bash
javac -encoding UTF-8 -h . UtfBridgeDemo.java
```

The command generates `UtfBridgeDemo.class` and `UtfBridgeDemo.h`. Do not guess JNI symbols when changing packages, overloads, or return types; take prototypes from the header generated by `javac -h`.

### 6.3. File `UtfBridgeDemo.c`

```c
#include <jni.h>
#include "UtfBridgeDemo.h"

JNIEXPORT jcharArray JNICALL Java_UtfBridgeDemo_utf16Units(
        JNIEnv *env, jclass owner, jstring value) {
    (void) owner;
    // Example requires value != NULL.
    jsize count = (*env)->GetStringLength(env, value);
    const jchar *units = (*env)->GetStringChars(env, value, NULL);
    if (units == NULL) return NULL;

    jcharArray result = (*env)->NewCharArray(env, count);
    if (result != NULL && count > 0) {
        (*env)->SetCharArrayRegion(env, result, 0, count, units);
    }

    // Always release, even if NewCharArray/SetCharArrayRegion fails.
    (*env)->ReleaseStringChars(env, value, units);
    if ((*env)->ExceptionCheck(env)) return NULL;
    return result;
}

JNIEXPORT jbyteArray JNICALL Java_UtfBridgeDemo_modifiedUtf8Bytes(
        JNIEnv *env, jclass owner, jstring value) {
    (void) owner;
    // Only use GetStringUTFLength with short strings in the demo.
    jsize count = (*env)->GetStringUTFLength(env, value);
    const char *bytes = (*env)->GetStringUTFChars(env, value, NULL);
    if (bytes == NULL) return NULL;

    jbyteArray result = (*env)->NewByteArray(env, count);
    if (result != NULL && count > 0) {
        (*env)->SetByteArrayRegion(
                env, result, 0, count, (const jbyte *) bytes);
    }

    (*env)->ReleaseStringUTFChars(env, value, bytes);
    if ((*env)->ExceptionCheck(env)) return NULL;
    return result;
}

JNIEXPORT jstring JNICALL Java_UtfBridgeDemo_createFromModifiedUtf8(
        JNIEnv *env, jclass owner) {
    (void) owner;

    // Payload: A + U+0000 + U+00E9 + U+1F600.
    // MUTF-8 has 11 data bytes and one 00 byte terminating the C string.
    const char encoded[] = {
        0x41,
        (char) 0xC0, (char) 0x80,
        (char) 0xC3, (char) 0xA9,
        (char) 0xED, (char) 0xA0, (char) 0xBD,
        (char) 0xED, (char) 0xB8, (char) 0x80,
        '\0'
    };

    return (*env)->NewStringUTF(env, encoded);
}
```

The native code does **not** use `strlen` to measure MUTF-8 obtained from JNI; it copies the exact `count` bytes using `SetByteArrayRegion`. When creating a `String` with `NewStringUTF`, the C code ensures a `00` byte **outside the payload** (which is the `'\0'` at the end of the array). Java returns a `String` with U+0000 **inside** and the emoji surrogate pair intact.

The example assumes `value != NULL`; in production systems, check Java inputs and exception state. `NewCharArray`/`NewByteArray` can fail allocation; after releasing, the function returns a `NULL` reference if an exception is pending.

### 6.4. Building the Library and Running

On Linux:

```bash
gcc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libutfbridge.so UtfBridgeDemo.c

java -Djava.library.path=. UtfBridgeDemo
```

On **JDK 24+**, if the JVM requires/warns about JNI native access permission, use:

```bash
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. UtfBridgeDemo
```

**Expected stdout:**

```text
JNI UTF-16: 0041 0000 00E9 D83D DE00
JNI MUTF-8: 41 C0 80 C3 A9 ED A0 BD ED B8 80
NewStringUTF round-trip: true
```

Note: `System.loadLibrary("utfbridge")` uses the logical name `utfbridge`; on Linux the default file is `libutfbridge.so`. On macOS it may require `libutfbridge.dylib` with JNI header `include/darwin`, and on Windows `utfbridge.dll` with header `include/win32`. Do not use the GCC/Linux command verbatim on Windows without an equivalent toolchain.

## 7. The RIGHT Conversion Path When Native Needs Standard UTF-8

Many native APIs use **standard UTF-8**, such as JSON libraries, network protocols, filesystem APIs, or a C/C++ function taking `(const uint8_t *data, size_t length)`. Do not pass the pointer from `GetStringUTFChars` into these APIs as if it were standard UTF-8.

### 7.1. Java → Native API Requiring Standard UTF-8

In Java, encode with an **explicit charset** before crossing JNI:

```java
import java.nio.charset.StandardCharsets;

String text = "A" + '\0' + new String(Character.toChars(0x1F600));
byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);

// nativeSendUtf8(utf8, utf8.length); // user-declared native method.
```

This is an **illustrative snippet**, not a standalone program. On the C side, receive a `jbyteArray`, call `GetArrayLength` and `GetByteArrayRegion` (or `GetByteArrayElements` paired with `ReleaseByteArrayElements`), and pass **the exact byte count** to the target API. If the native API requires a NUL-terminated C string, you must still understand that **standard UTF-8 allows `00` inside text**; that specific C API's contract may not be able to represent embedded NUL. You must reject NUL characters, use a length-based API, or change the protocol rather than silently losing data with `strlen`.

Native libraries expecting `wchar_t *` are also not synonymous with `jchar *`. On some operating systems `wchar_t` is 16-bit, elsewhere 32-bit; you must convert according to the ABI/platform rather than casting arbitrarily.

### 7.2. Native Standard UTF-8 → Java String

If C has standard UTF-8 data, especially containing 4-byte emoji sequences, **do not** pass it directly to `NewStringUTF`. A simple path is to bring those bytes back to Java as a `byte[]`, then decode with:

```java
String decoded = new String(utf8Bytes, StandardCharsets.UTF_8);
```

The line above is a snippet where `utf8Bytes` is a `byte[]` received from native. This constructor has a policy of replacing certain invalid byte sequences. If input data needs **strict validation**, use a decoder with `CodingErrorAction.REPORT`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictUtf8 {
    public static String decode(byte[] bytes)
            throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
    }
}
```

This is a **standalone utility class** (can be compiled with `javac StrictUtf8.java`) but contains no `main`. Call `StrictUtf8.decode(bytes)` from your application/test. When passing an MUTF-8 payload containing `C0 80` or surrogate bytes into the strict decoder, it reports the data as **invalid according to standard UTF-8**, instead of silently replacing characters.

Another C-native → Java path is to decode UTF-8 into valid UTF-16 `jchar`s (via a transcoding library), then call `NewString(env, units, codeUnitCount)`. `NewString` takes UTF-16 code units and an **explicit length**, requiring no terminating NUL.

## 8. Special Traps with NUL, Surrogates, and Buffer Lengths

### Trap A: U+0000 Is Not the Same as Java String Termination

In Java, `"A" + '\0' + "B"` has a length of **3 UTF-16 code units** and preserves U+0000 in the middle. When encoded as standard UTF-8, the bytes are `41 00 42`. Passing it to a C API that only uses `strlen` yields a length of **1 byte**, because it stops at `00`. JNI MUTF-8 uses `41 C0 80 42` so there is no `00` in the payload; to send standard UTF-8, you must have an explicit length or a clearly defined NUL policy.

### Trap B: An Emoji Is Neither One `char` Long Nor Three Bytes Long

An emoji outside the BMP has `String.length() == 2` but may have only **1 code point**; in standard UTF-8 it is usually **4 bytes**, whereas in MUTF-8 it is **6 bytes**. Allocating `length * 3` can serve as an upper bound for MUTF-8 of short strings, but it is not the actual size and still requires checking for overflow, NUL terminator, or prefix. Measure accurately using the corresponding encoding API.

### Trap C: Strings Containing Lone Surrogates

A `String`/`char` can hold an **unpaired high or low surrogate**. MUTF-8 can encode that single code unit into 3 bytes; **strict UTF-8** does not accept surrogate code points. When Java converts to standard UTF-8 via `getBytes(UTF_8)`, unmappable/malformed UTF-16 input may be replaced according to the default encoder policy; if you need to prevent data loss, choose a `CharsetEncoder` with `onMalformedInput(CodingErrorAction.REPORT)`.

Therefore, if the requirement is "preserve every code unit of the String absolutely", use UTF-16 `jchar[]` or a protocol with explicit rules for unmatched surrogates; do not assume that round-tripping Unicode scalar values will preserve invalid UTF-16 codes.

### Trap D: The Buffer of `GetStringUTFRegion`

`len` is **the number of UTF-16 code units to convert**, not the number of bytes written out. A segment with multi-byte characters may write **more than `len` bytes**. The result is also **not guaranteed to be NUL-terminated**. Therefore:

- Do not allocate exactly `len` bytes for `GetStringUTFRegion`.
- Do not pass the copied buffer directly to `strlen`/`printf("%s")` without knowing the size and adding a terminator yourself.
- If using the entire small String, you can get the byte count via `GetStringUTFLength` first; for a substring, you must calculate/allocate enough for **that segment** (and check overflow), not mistakenly use the whole string's byte count as the actual byte count of the region.
- When you only need to copy a few UTF-16 characters, `GetStringRegion` provides `jchar` with a clearer unit length.

### Trap E: Holding JNI Pointers Too Long

`GetStringChars` / `GetStringUTFChars` may allocate a copy or pin resources. Do not hold pointers after `Release...`, do not pass pointers to another thread without designing lifecycle management, and do not confuse `isCopy == JNI_FALSE` with data ownership. `GetStringCritical` has strict restrictions on JNI calls/blocking while inside a critical region; only use it when truly necessary and with extremely short code blocks.

## 9. Choosing an API by Purpose

| Practical need | Approach |
|---|---|
| Reading **UTF-16 code units** from `jstring`, preserving U+0000 and surrogates | `GetStringLength` + `GetStringChars` + `ReleaseStringChars` or `GetStringRegion` |
| Creating a `jstring` from a 16-bit UTF-16 buffer | `NewString(env, chars, length)` |
| Interfacing with native code designed for **JNI MUTF-8** | `GetStringUTFChars` + `ReleaseStringUTFChars`; create from valid MUTF-8 using `NewStringUTF` |
| Measuring the number of **MUTF-8 bytes** | `GetStringUTFLength` in older JDKs, `GetStringUTFLengthAsLong` from JDK 24 |
| Writing JSON files, sending HTTP/gRPC, or calling APIs requiring **standard UTF-8** | `String.getBytes(StandardCharsets.UTF_8)` → `jbyteArray` + length; or a standard decoder/encoder in native |
| Receiving standard UTF-8 bytes from native | `jbyteArray` → `new String(bytes, UTF_8)` or strict decoder; optionally transcode to UTF-16 then `NewString` |
| Needing a C API taking a NUL-terminated string while text has U+0000 | Adjust the API contract or reject NUL; **do not** sneakily use MUTF-8 if the C API requires standard UTF-8 |
| Wanting to cache/allocate large buffers | Check byte count, `jsize`/`size_t` type limits, addition overflow, and lifecycle; consider streaming/chunking |

Determine the **target API's encoding**, **unit of length**, and **who is responsible for freeing/releasing** before choosing a JNI function. JNI cannot guess whether an external C library expects standard UTF-8, UTF-16, UTF-32, or a locale-dependent encoding.

## 10. Common Debugging Errors

| Symptom | Possible cause | How to verify |
|---|---|---|
| String truncated at U+0000 | Passing standard UTF-8 containing `00` to a C API using `strlen` | Print hex, check for a length-based API |
| Emoji turns into question marks/replacement characters | Reading MUTF-8 with a UTF-8 decoder or faulty surrogate encoding | Compare 4-byte UTF-8 hex with 6-byte MUTF-8 hex |
| `NewStringUTF` crashes or produces wrong characters | Passing standard UTF-8 with 4-byte sequences, invalid MUTF-8, or missing terminator | Only pass valid MUTF-8; try `-Xcheck:jni` |
| Length value is larger than expected | Counting bytes instead of code units, or vice versa | Distinguish `GetStringLength` / `GetStringUTFLength` |
| Native buffer written past bounds | Using UTF-16 unit count as byte capacity for `GetStringUTFRegion` | Allocate enough output bytes, check overflow |
| Memory grows over multiple calls | Forgetting `ReleaseStringChars` / `ReleaseStringUTFChars` | Pair acquire/release across all error branches |
| `readUTF` does not understand bytes from network | `readUTF` expects a 2-byte prefix and MUTF-8; network uses standard UTF-8 without that prefix | Use a charset decoder and the actual framing protocol |
| Content is wrong but only for a few characters | BMP ASCII/Latin have identical encodings; NUL and non-BMP reveal the difference | Test A, U+0000, é, 😀, unmatched surrogate |

When debugging JNI, in addition to regular logs, you can enable `java -Xcheck:jni ...` to detect some JNI usage errors; it does **not** replace byte protocol checks or memory safety mechanisms. Do not log binary buffers directly with `%s` when you do not know whether they have a NUL terminator; use a length-bounded hex dump.

## 11. Exercises with Answers

**Exercise 1.** What is `s.length()` for `String s = "A" + '\0' + "B";`? How many bytes in standard UTF-8 and MUTF-8?

**Answer:** 3 UTF-16 units. Standard UTF-8: `41 00 42` (3 bytes). MUTF-8: `41 C0 80 42` (4 bytes). If encoded with `DataOutputStream.writeUTF`, there is also a 2-byte prefix `00 04` on the wire.

**Exercise 2.** Given `String s = new String(Character.toChars(0x1F600));`. Predict `s.length()`, code point count, standard UTF-8 byte count, and JNI MUTF-8 byte count.

**Answer:** `length()=2`, `codePointCount(...)=1`, standard UTF-8 4 bytes `F0 9F 98 80`, MUTF-8 6 bytes `ED A0 BD ED B8 80`.

**Exercise 3.** A C API accepts standard UTF-8 JSON with an explicit length. Should you pass `GetStringUTFChars(env, text, ...)` or a `jbyteArray` encoded with `StandardCharsets.UTF_8`?

**Answer:** Choose standard `jbyteArray` + length. `GetStringUTFChars` returns MUTF-8 and can violate the standard for NUL/supplementary characters.

**Exercise 4.** Why can `GetStringUTFRegion(env, s, 0, s.length(), buf)` into a buffer of length `s.length()` corrupt memory?

**Answer:** `s.length()` is the number of UTF-16 code units, whereas MUTF-8 output often has multiple bytes per unit. You must know/assign capacity by the **encoded byte count**, check overflow, and not assume a terminating NUL byte.

**Exercise 5.** Can you pass the byte array from `DataOutputStream.writeUTF` directly into `NewStringUTF`?

**Answer:** No. `writeUTF` adds a **2-byte length prefix**; `NewStringUTF` takes a NUL-terminated **MUTF-8 C string**. You must strip the framing and prepare a valid terminator. For strings larger than 65,535 MUTF-8 bytes, `writeUTF` also throws `UTFDataFormatException`.

## 12. Practical Conclusion and Primary References

Rules sufficient to avoid most encoding bugs at the Java–JNI boundary:

1. **Java `String` / `jchar`:** observed as **UTF-16 code units**; `length()` is not necessarily the number of characters a reader sees.
2. **JNI `...UTF...`:** is **Modified UTF-8**, with U+0000 → `C0 80` and supplementary code points → **6 bytes**, because each surrogate is encoded separately.
3. **I/O, web, files, JSON use standard UTF-8:** encode/decode with a standard charset or equivalent converter; do not pass MUTF-8 directly into standard UTF-8 protocols.
4. **Memory and length:** byte count differs from unit count, buffer pointers must be released per the JNI contract, and a C string terminator and a framing prefix are two different concepts.

Official documentation for cross-checking APIs and behavior:

- [Oracle JNI Specification — Types and Data Structures / Modified UTF-8 Strings](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/types.html#modified-utf-8-strings)
- [Oracle JNI Specification — JNI Functions / String Operations](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html#string-operations)
- [Java 17 — `DataOutputStream.writeUTF`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html#writeUTF(java.lang.String))
- [Java 17 — `String`, `length`, `codePointCount`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java 17 — `StandardCharsets.UTF_8`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [Java 17 — `CharsetDecoder` and `CodingErrorAction`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
