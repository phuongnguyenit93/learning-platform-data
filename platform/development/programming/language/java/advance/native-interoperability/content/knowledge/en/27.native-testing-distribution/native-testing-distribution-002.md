# Testing boundary values, null, Unicode, short buffers, and size overflows in Java–native interoperability

## Objectives

When Java communicates with C/C++ via **Foreign Function & Memory API (FFM)** or **JNI**, many serious bugs do not appear on the "happy path" but on special inputs: zero count, `NULL` address, multi-byte strings, a buffer short by 1 byte, or the number of bytes to allocate overflowing before calling native code. This lesson guides you through building a **data contract**, a boundary test suite, standalone runnable Java 22+ examples, and how to verify the real native part using memory-error detection tools.

After this lesson, you should be able to:

1. Distinguish Java `null`, C `NULL` pointer, and empty C string; choose consistent handling and write tests for each case.
2. Calculate the exact **byte length** of UTF-8 data, space reserved for the `NUL` terminator, and recognize `NUL` characters embedded in the middle of content.
3. Determine valid boundaries for `offset`, `length`, `capacity`, insufficient buffers, and exact-fit buffers; verify the condition of not writing past the limit.
4. Prevent overflow when computing `count * elementSize + overhead`, avoid silent numeric narrowing, and match C `size_t`/`jsize` with Java signatures.
5. Combine Java tests, C tests, sanitizers, 32/64-bit architectures, and regression testing without equating `MemorySegment` guarantees with native library guarantees.

**Version scope:** The `java.lang.foreign` examples apply to **JDK 22 and later** (FFM was finalized in JDK 22). They only use safe memory segment operations on the Java side without calling C functions, so they **do not require** `--enable-native-access`. Actual downcall integration is a restricted operation and requires the appropriate native access flags/policies for the JDK version.

## 1. Defining the contract before writing test cases

A typical C signature:

```c
int process_bytes(const unsigned char *src,
                  size_t src_len,
                  unsigned char *dst,
                  size_t dst_capacity,
                  size_t *written);
```

Before testing, you need a clear answer for each field:

| Field | Meaning | Question to settle in the API contract |
| --- | --- | --- |
| `src` | Pointer to input buffer | Is `NULL` accepted when `src_len == 0`? |
| `src_len` | Valid **byte count** at `src` | Does it include the C string `NUL`? Can it be 0? |
| `dst` | Pointer to output buffer | Can `NULL` be used to query the required capacity? |
| `dst_capacity` | Number of bytes **actually writable** at `dst` | If insufficient, what status is returned? Is there a partial write? |
| `written` | Bytes written or bytes needed to allocate, per contract | On error, is it reset to 0? Is the unit bytes? |
| `int` result | Status code | What do negative/positive/0 mean? Can it be called repeatedly safely? |

You cannot infer these rules solely from the function name. **The contract must explicitly state**: whether NUL-terminated or `pointer + length` is required; whether the returned byte count includes NUL; whether a short buffer returns an error/truncation/required size; and which side owns and frees pointers and memory.

Four concepts that are very easy to confuse:

- **Java `null`**: no object reference; can cause `NullPointerException` when Java code tries to use it. A wrapper can proactively reject `null` using `Objects.requireNonNull`.
- **FFM `MemorySegment.NULL`**: a `MemorySegment` object representing **native address 0**, with size 0, often used when a C parameter allows a `NULL` pointer. It is different from Java `null`; `MemorySegment.NULL.get(...)` is not a valid memory read operation.
- **Empty C string `""`**: has one terminating byte `0x00` when encoded as UTF-8 NUL-terminated; different from a `NULL` pointer and different from a 0-length buffer.
- **Zero-capacity buffer**: may be a valid request in a binary API (no data), or used to query required capacity. Do not assume the native library allows `NULL, 0` unless the contract explicitly states so.

If the API uses `pointer + length` and allows `0x00` bytes in the middle, test binary data according to the exact `length`, rather than calling `strlen`/`getString` and accidentally truncating data at NUL.

## 2. Mandatory test case matrix

| Group | Inputs/boundaries | What to verify |
| --- | --- | --- |
| Length | `0`; `1`; `capacity - 1`; `capacity`; `capacity + 1` | Status, returned length, no out-of-bounds read/write |
| Offset | `-1`; `0`; `capacity - 1`; `capacity`; `capacity + 1` | `offset == capacity` is only valid for **0-byte** operations, invalid when at least 1 byte must be read/written |
| Null | Java `null`; `MemorySegment.NULL`; empty segment; `""` string | Matches input policy; does not dereference NULL or substitute NULL with an empty string |
| Unicode | ASCII; `é`; Vietnamese; CJK; non-BMP emoji; combining characters | Data round-trips per exact charset; compare **byte length** vs **UTF-16 char length** |
| Embedded NUL byte | `"A\u0000B"` (Java string) or `{65, 0, 66}` (byte[]) | For C strings, result is typically only `"A"`; for length-prefixed data, all 3 bytes must be preserved |
| Invalid Unicode | Unpaired surrogate; malformed UTF-8 byte sequence | Explicit rejection or replacement per contract; do not silently assume round-trip succeeded |
| Short buffer | 1 byte short of payload; missing NUL; 0 buffer | Error/truncation/required-size matches docs; canaries unchanged |
| Size overflow | `count * stride`; adding header/NUL; converting `long` → `int` | Detect overflow **before** allocation/copy; do not require allocating huge memory to create the test |
| ABI/cross-platform | 32/64-bit `size_t`; 32/64-bit pointer; signed/unsigned | `FunctionDescriptor`/`jni` uses the right C type per ABI; no high bits dropped |
| Combined errors | NULL + positive length; short buffer + multi-byte Unicode; overflow + negative length | Clear validation order, stable status, no reliance on undefined behavior |

**Designing tests around `n-1, n, n+1` boundaries** is the way to catch off-by-one errors. For a UTF-8 string needing `B` content bytes and **1 NUL byte**, test buffer sizes `B` (short by exactly 1), `B+1` (exact fit), `B+2` (1 byte to spare). If the API does not use NUL-terminated strings, do not add 1 on your own.

### Range-checking rule avoiding addition overflow

The naive condition `offset + length <= capacity` can be wrong when `offset + length` **overflows**. A safer check on non-negative `long` values:

```java
static boolean fits(long offset, long length, long capacity) {
    return offset >= 0 && length >= 0 && capacity >= 0
            && offset <= capacity && length <= capacity - offset;
}
```

Only compute `capacity - offset` after knowing `offset <= capacity`. For a buffer of length `capacity`, `fits(capacity, 0, capacity)` is `true` while `fits(capacity, 1, capacity)` is `false`.

## 3. Testing null and empty strings

### Java/FFM side

```java
// Illustration inside a Java method with an open arena variable:
MemorySegment nullPointer = MemorySegment.NULL; // native address 0
MemorySegment emptyCString = arena.allocateFrom(""); // one byte 0x00

boolean reallyNull = nullPointer.address() == 0;
boolean reallyEmpty = emptyCString.getString(0).isEmpty();
```

The snippet above depends on the `arena` variable and is not a standalone program; the runnable program is in section 6.

A wrapper accepting a non-nullable Java string should use `Objects.requireNonNull(text, "text")`, or return a documented business-domain error. A wrapper allowing a nullable C pointer must **intentionally** map from the input to `MemorySegment.NULL`. **Do not** use Java `null` as an ambiguous shorthand for C `NULL` across all FFM APIs.

For C APIs of the form `(ptr, len)`: test all of `(NULL, 0)`, `(NULL, 1)`, and `(valid_ptr, 0)`. Which cases are valid depends on the contract; `len == 0` does not automatically allow passing an invalid pointer to libraries with strict preconditions.

### JNI side

JNI has both `jstring` (a Java reference that can be null) and functions returning native character buffers such as `GetStringUTFChars`. Returning a `NULL` pointer on retrieval failure must be handled according to the JNI specification before reading; manage the release pair and lifetime properly. Do not treat `GetStringUTFChars` as standard UTF-8: JNI uses **Modified UTF-8**, which differs from standard UTF-8 for U+0000 and non-BMP characters. String tests must know the exact API doing the encoding/decoding.

## 4. Unicode: distinguishing UTF-16, code points, UTF-8, and NUL

Java `String.length()` counts **UTF-16 code units**, `codePointCount(...)` counts code points, while a C UTF-8 buffer counts **bytes**. For example:

| String | `String.length()` | Unicode code points | UTF-8 bytes (excluding NUL) |
| --- | ---: | ---: | ---: |
| `""` | 0 | 0 | 0 |
| `"A"` | 1 | 1 | 1 |
| `"é"` (U+00E9) | 1 | 1 | 2 |
| `"🌍"` (U+1F30D) | 2 | 1 | 4 |
| `"A🌍ế"` | 4 | 3 | 8 |

For `"A🌍ế"`, a standard UTF-8 C string needs **9 bytes**: 8 content bytes + 1 NUL byte. Using `text.length() + 1` would compute 5, short by 4 bytes. `Arena.allocateFrom(text)` allocates an appropriately sized segment and appends the terminator for the charset; `MemorySegment.getString(0)` reads UTF-8 NUL-terminated.

### Embedded NUL in a string

`"A\0B"` in Java consists of three characters: `A`, U+0000, `B`. `arena.allocateFrom(...)` still encodes the embedded `0x00` byte and appends the final terminator. However, `segment.getString(0)` stops at the first NUL, returning `"A"`. This is **not** a UTF-8 bug; it is the nature of C strings. If `B` is meaningful, pass the data as **`byte[]` + byte length** or a length-prefixed protocol, and test round-trip on the raw bytes.

### Invalid Unicode and normalization

- An unpaired surrogate, such as UTF-16 code unit `0xD800` without a matching low surrogate, is not a valid Unicode scalar. Convenience methods like `String.getBytes(StandardCharsets.UTF_8)` may **replace** unencodable data. For APIs requiring strictness, use a `CharsetEncoder` with `CodingErrorAction.REPORT` and test for `MalformedInputException`.
- Invalid UTF-8 byte sequences also need a clear policy: reject or replace. `MemorySegment.getString(..., Charset)` uses replacement for malformed input; if you want rejection, use a decoder with `REPORT` over the exact byte sequence with length.
- Two visually similar strings such as `"é"` (U+00E9) and `"e\u0301"` (U+0065 + U+0301) can have different bytes. Only normalize (`Normalizer.Form.NFC`, etc.) if the protocol requires it; do not silently alter input data in the JNI/FFM layer.
- **JNI Modified UTF-8** is not equivalent to standard UTF-8; when interfacing with non-JNI C functions that use regular UTF-8, do not assume byte counts from legacy `GetStringUTFLength` or data from `GetStringUTFChars` are standard UTF-8. On JDK 24+, `GetStringUTFLengthAsLong` returns `jlong` to avoid the `jsize` limit of the older API; length/buffer checks according to the contract are still required.

## 5. Short buffers: calculating capacity and proving no out-of-bounds write

For a **UTF-8 NUL-terminated** API, the Java side can compute:

```java
String text = "é";
byte[] payload = text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
long required = Math.addExact((long) payload.length, 1L); // 2 + 1 = 3
```

If only 2 bytes are allocated:

```java
// This example uses an open arena variable:
MemorySegment shortBuffer = arena.allocate(2);
shortBuffer.setString(0, "é");  // IndexOutOfBoundsException
```

If 3 bytes are allocated, `setString(0, "é")` and `getString(0)` work properly. **FFM Java bounds checks** prove that `setString` via the Java API cannot write past the segment bounds. That **does not prove** a native function receiving the pointer will not write past `dst_capacity`; separate C/C++ tests are needed.

When native code returns "buffer too small", tests should check **both content and state**:

- Is `written` 0, the number of bytes written, or the required number of bytes? It must match the contract, not guesswork.
- Was the short buffer partially modified? If the contract guarantees "nothing modified on error", assert that the entire payload and both leading/trailing canaries are **unchanged**.
- If native code supports truncation, only allow truncating at **character boundaries** when the protocol specifies UTF-8 strings, and ensure the trailing NUL byte; binary data may use different semantics.
- APIs like `snprintf`, `strncpy`, and `memcpy` have completely different rules for return values/terminators; do not apply one function's test expectations to another.

A small defensive example for an API we own:

```c
/* copy_bytes.c: binary contract, len/capacity measured in BYTES.
   No NUL required, no partial write when buffer is insufficient.
   Data is allowed to contain 0x00 inside. */
#include <stddef.h>
#include <stdint.h>
#include <string.h>

enum { COPY_OK = 0, COPY_BAD_ARG = 1, COPY_TOO_SMALL = 2 };

int copy_bytes(const uint8_t *src, size_t len,
               uint8_t *dst, size_t capacity,
               size_t *written) {
    if (written == NULL) return COPY_BAD_ARG;
    *written = 0;

    if ((len != 0 && src == NULL) ||
        (capacity != 0 && dst == NULL)) {
        return COPY_BAD_ARG;
    }
    if (len > capacity) return COPY_TOO_SMALL;

    if (len != 0) {
        memmove(dst, src, len);
    }
    *written = len;
    return COPY_OK;
}
```

The function above has a **contract designed specifically for learning**, not as a wrapper for every C API. `memmove` is chosen to handle potentially overlapping source/destination regions; a real API may forbid overlap and require different checks. In particular, C **does not know on its own** how many bytes `src`/`dst` actually point to: the caller must ensure `len` and `capacity` are truthful.

A C test harness named `copy_bytes_test.c`:

```c
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "copy_bytes.c"  /* Only include .c in standalone learning example. */

int main(void) {
    uint8_t src[] = {0x41, 0x00, 0xE2, 0x82, 0xAC};
    uint8_t dst[7];
    size_t written = 99;
    memset(dst, 0xA5, sizeof dst);

    assert(copy_bytes(src, 5, dst + 1, 5, &written) == COPY_OK);
    assert(written == 5);
    assert(memcmp(dst + 1, src, 5) == 0);
    assert(dst[0] == 0xA5 && dst[6] == 0xA5);

    memset(dst + 1, 0x7E, 5);
    written = 99;
    assert(copy_bytes(src, 5, dst + 1, 4, &written) == COPY_TOO_SMALL);
    assert(written == 0);
    for (size_t i = 1; i < 6; ++i) assert(dst[i] == 0x7E);
    assert(dst[0] == 0xA5 && dst[6] == 0xA5);

    assert(copy_bytes(NULL, 0, NULL, 0, &written) == COPY_OK);
    assert(written == 0);
    assert(copy_bytes(NULL, 1, dst, sizeof dst, &written) == COPY_BAD_ARG);
    assert(copy_bytes(src, 5, dst, sizeof dst, NULL) == COPY_BAD_ARG);

    puts("C contract PASS");
    return 0;
}
```

On Linux/macOS with GCC/Clang (with sanitizer support), in the directory containing the two C files:

```bash
cc -std=c11 -Wall -Wextra -Werror -g -fsanitize=address,undefined \
  -o copy_bytes_test copy_bytes_test.c
./copy_bytes_test
```

**Stdout when all asserts succeed:**

```text
C contract PASS
```

When using sanitizers, monitor both exit code and stderr: an AddressSanitizer/UndefinedBehaviorSanitizer error must fail the test even if logical asserts have not caught it. Environments or compilers without sanitizer support need the corresponding build command; sanitizer guarantees apply only to executed paths. The C test above explicitly verifies the embedded `0x00` byte at the second position and the destination canaries. In a real project, separate prototypes into a header instead of including `.c`.

## 6. Java 22+ Lab: 27 standalone test cases

Create the file **`NativeBoundaryLab.java`**. The following code does not require JUnit, loads no native library, and can be run with JDK 22+ `javac`/`java`:

```java
import java.lang.foreign.*;
import java.nio.CharBuffer;
import java.nio.charset.*;
import java.util.Objects;

public class NativeBoundaryLab {
    private static int passes = 0;

    @FunctionalInterface
    interface Action { void run() throws Throwable; }

    private static void ok(String name, boolean valid) {
        if (!valid) throw new AssertionError("FAIL " + name);
        passes++;
        System.out.println("PASS " + name);
    }

    private static void expect(String name,
                               Class<? extends Throwable> expected,
                               Action action) {
        try {
            action.run();
        } catch (Throwable ex) {
            if (!expected.isInstance(ex)) {
                throw new AssertionError("Wrong exception: " + name, ex);
            }
            passes++;
            System.out.println("PASS " + name + " -> "
                    + ex.getClass().getSimpleName());
            return;
        }
        throw new AssertionError("Missing exception: " + name);
    }

    private static long requiredBytes(long count, long stride, long extra) {
        if (count < 0 || stride <= 0 || extra < 0) {
            throw new IllegalArgumentException("invalid size");
        }
        return Math.addExact(Math.multiplyExact(count, stride), extra);
    }

    private static boolean fits(long offset, long length, long capacity) {
        return offset >= 0 && length >= 0 && capacity >= 0
                && offset <= capacity && length <= capacity - offset;
    }

    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment eight = arena.allocate(8);
            ok("last-byte", eight.get(ValueLayout.JAVA_BYTE, 7) == 0);
            expect("offset-at-capacity", IndexOutOfBoundsException.class,
                    () -> eight.get(ValueLayout.JAVA_BYTE, 8));
            ok("empty-slice-end", eight.asSlice(8, 0).byteSize() == 0);
            expect("slice-past-end", IndexOutOfBoundsException.class,
                    () -> eight.asSlice(8, 1));

            ok("null-address", MemorySegment.NULL.address() == 0
                    && MemorySegment.NULL.byteSize() == 0);
            expect("null-dereference", IndexOutOfBoundsException.class,
                    () -> MemorySegment.NULL.get(ValueLayout.JAVA_BYTE, 0));
            expect("java-null-policy", NullPointerException.class,
                    () -> Objects.requireNonNull(null, "text"));

            MemorySegment empty = arena.allocateFrom("");
            ok("empty-c-string", empty.byteSize() == 1
                    && empty.getString(0).isEmpty());

            String unicode = "A" + Character.toString(0x1F30D)
                    + Character.toString(0x1EBF);
            byte[] utf8 = unicode.getBytes(StandardCharsets.UTF_8);
            ok("utf16-vs-codepoints", unicode.length() == 4
                    && unicode.codePointCount(0, unicode.length()) == 3);
            ok("utf8-bytes", utf8.length == 8);
            MemorySegment encoded = arena.allocateFrom(unicode);
            ok("encoded-capacity", encoded.byteSize() == 9);
            ok("utf8-round-trip", encoded.getString(0).equals(unicode));

            MemorySegment embedded = arena.allocateFrom("A\0B");
            ok("embedded-nul-stops-c-string", embedded.byteSize() == 4
                    && embedded.getString(0).equals("A"));
            expect("no-zero-terminator", IndexOutOfBoundsException.class,
                    () -> MemorySegment.ofArray(new byte[]{65, 66}).getString(0));

            String accent = Character.toString(0x00E9);
            expect("buffer-too-short", IndexOutOfBoundsException.class,
                    () -> arena.allocate(2).setString(0, accent));
            MemorySegment exact = arena.allocate(3);
            exact.setString(0, accent);
            ok("buffer-exact", exact.getString(0).equals(accent));

            byte[] canary = {9, 0, 0, 9};
            MemorySegment body = MemorySegment.ofArray(canary).asSlice(1, 2);
            body.set(ValueLayout.JAVA_BYTE, 0, (byte) 7);
            body.set(ValueLayout.JAVA_BYTE, 1, (byte) 8);
            ok("canary-untouched", canary[0] == 9 && canary[3] == 9);
            expect("canary-guarded-write", IndexOutOfBoundsException.class,
                    () -> body.set(ValueLayout.JAVA_BYTE, 2, (byte) 1));

            ok("zero-count", requiredBytes(0, 8, 0) == 0);
            ok("checked-size", requiredBytes(4, 8, 1) == 33);
            expect("negative-count", IllegalArgumentException.class,
                    () -> requiredBytes(-1, 8, 0));
            expect("product-overflow", ArithmeticException.class,
                    () -> requiredBytes(Long.MAX_VALUE, 8, 0));
            expect("sum-overflow", ArithmeticException.class,
                    () -> requiredBytes(Long.MAX_VALUE, 1, 1));
            expect("narrowing-overflow", ArithmeticException.class,
                    () -> Math.toIntExact((long) Integer.MAX_VALUE + 1));
            expect("unpaired-surrogate", MalformedInputException.class,
                    () -> StandardCharsets.UTF_8.newEncoder()
                            .onMalformedInput(CodingErrorAction.REPORT)
                            .encode(CharBuffer.wrap(
                                    Character.toString((char) 0xD800))));
            ok("range-at-end-empty", fits(8, 0, 8));
            ok("range-at-end-nonempty-rejected", !fits(8, 1, 8));
        }
        System.out.println("TOTAL=" + passes);
    }
}
```

Run in the directory containing `NativeBoundaryLab.java`:

```bash
javac -encoding UTF-8 NativeBoundaryLab.java
java NativeBoundaryLab
```

**Verification stdout:**

```text
PASS last-byte
PASS offset-at-capacity -> IndexOutOfBoundsException
PASS empty-slice-end
PASS slice-past-end -> IndexOutOfBoundsException
PASS null-address
PASS null-dereference -> IndexOutOfBoundsException
PASS java-null-policy -> NullPointerException
PASS empty-c-string
PASS utf16-vs-codepoints
PASS utf8-bytes
PASS encoded-capacity
PASS utf8-round-trip
PASS embedded-nul-stops-c-string
PASS no-zero-terminator -> IndexOutOfBoundsException
PASS buffer-too-short -> IndexOutOfBoundsException
PASS buffer-exact
PASS canary-untouched
PASS canary-guarded-write -> IndexOutOfBoundsException
PASS zero-count
PASS checked-size
PASS negative-count -> IllegalArgumentException
PASS product-overflow -> ArithmeticException
PASS sum-overflow -> ArithmeticException
PASS narrowing-overflow -> ArithmeticException
PASS unpaired-surrogate -> MalformedInputException
PASS range-at-end-empty
PASS range-at-end-nonempty-rejected
TOTAL=27
```

**Explanation of notable assertions:**

- `arena.allocate(8)` creates an 8-byte buffer with valid offsets from 0 to 7. `asSlice(8, 0)` is valid because an empty slice can start right at the end of the segment; `asSlice(8, 1)` goes out of bounds.
- `MemorySegment.NULL` has address 0 and size 0; attempting to read 1 byte results in `IndexOutOfBoundsException`. Whether a nullable pointer may be passed to native code still depends on the C function contract.
- The string `"A🌍ế"` is constructed from Unicode code points so the source code does not depend on terminal encoding; it has 4 UTF-16 units, 3 code points, and 8 UTF-8 bytes. The C string segment has 9 bytes due to the NUL terminator.
- `"A\0B"` has an embedded NUL so `getString(0)` returns `"A"`. This is a test for "C strings", not a full binary data round-trip.
- A buffer for `"é"` needs 2 UTF-8 bytes plus 1 NUL byte. `setString` into 2 bytes is blocked; 3 bytes succeeds.
- Canaries `9` sit on both sides of the body on a `byte[]`; after two valid writes, the canaries remain intact, while writing at an offset outside the body is rejected by Java FFM bounds checks. **Native C given the raw pointer can bypass this FFM fence**, so C tests/sanitizers must still be run.
- `requiredBytes(...)` checks for negative input and uses `Math.multiplyExact`/`Math.addExact`; out-of-range operations throw `ArithmeticException` instead of wrapping around to a small or negative value. `Math.toIntExact` catches cases where a real C/JNI API only accepts a 32-bit integer.
- The test suite **does not attempt to allocate** `Long.MAX_VALUE` bytes. Overflow is proven with pure arithmetic to avoid `OutOfMemoryError`, process hangs, or exhausting CI machine RAM.

## 7. Sizes: multiplication overflow, addition overflow, and ABI type conversion

A common bug:

```java
// Wrong: may overflow int BEFORE assigning to long.
long total = itemCount * elementBytes;

// Wrong: the sum may overflow even when the product has not overflowed.
long withHeader = total + headerBytes;
```

If `itemCount` and `elementBytes` are both `int`, the first multiplication is evaluated as `int`. Casting to `long` **after** the multiplication does not recover lost bits. The right way:

```java
// This is an illustrative snippet, not a standalone program.
if (itemCount < 0 || elementBytes <= 0 || headerBytes < 0) {
    throw new IllegalArgumentException("Invalid sizes");
}
long payloadBytes = Math.multiplyExact((long) itemCount, (long) elementBytes);
long totalBytes = Math.addExact(payloadBytes, (long) headerBytes);

// Only when the native API actually accepts 32-bit int/jsize:
int nativeLength = Math.toIntExact(totalBytes);
```

**Do not use `Math.toIntExact` mechanically** for APIs accepting 64-bit `size_t`: it can reject valid data. Conversely, even if Java `long` holds a positive number, C `size_t` in a 32-bit environment can be smaller and `size_t` is **unsigned**. You must check C limits per ABI (especially if converting from `long` to 32-bit C `size_t`) and actual memory scale before calling native code.

FFM supports querying standard ABI layouts:

```java
// Snippet for JDK 22+, does not call a native function by itself.
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;

Linker linker = Linker.nativeLinker();
MemoryLayout cSizeT = linker.canonicalLayouts().get("size_t");
MemoryLayout cInt = linker.canonicalLayouts().get("int");
System.out.println("size_t bytes=" + cSizeT.byteSize());
```

This is an **illustrative snippet, not a standalone Java file** (the `import` statements go at the top of the file when placed in a program). The printed value depends on the platform, typically 4 bytes on a 32-bit ABI and 8 bytes on a 64-bit ABI; do not assume a fixed stdout across all operating systems. When creating a `FunctionDescriptor`, use the proper layouts of `size_t` and `int` from `Linker.canonicalLayouts()` instead of assuming every C `long` has the same width on Linux and Windows.

On the C side, when computing `count * stride + extra` with `size_t`:

```c
#include <stddef.h>
#include <stdint.h>

int compute_bytes(size_t count, size_t stride,
                  size_t extra, size_t *out) {
    if (out == NULL || stride == 0) return 0;
    if (count > SIZE_MAX / stride) return 0;
    size_t payload = count * stride;
    if (extra > SIZE_MAX - payload) return 0;
    *out = payload + extra;
    return 1;
}
```

This function returns 0 when it cannot compute safely, 1 on success; it does not read/write data and does not allocate. It checks multiplication first and then addition, using `SIZE_MAX` instead of assuming C `size_t` has the same limit as Java `long`. When inputs are `jlong`, `jint`, or an unsigned C size, design explicit compatible conversions and bounds at the boundary.

## 8. FFM/JNI integration: testing with a real native library

`MemorySegment` tests are a useful layer of protection, but they do not replace **integration tests** using an actually built library.

### 8.1. Correct ABI signature and native access

For the C function `copy_bytes` in section 5, the ABI signature must be described accurately:

```c
int copy_bytes(const uint8_t *src, size_t len,
               uint8_t *dst, size_t capacity,
               size_t *written);
```

On the FFM side: return `int`, parameters `src`/`dst`/`written` are addresses, while `len`/`capacity` are `size_t`. Use `Linker.canonicalLayouts()` to determine `size_t` and the corresponding Java carrier type. Do not try to force a handle with 32-bit `size_t` into a 64-bit `long` call via `invokeExact` expecting the JVM to convert automatically; check `methodHandle.type()`. The module performing restricted downcalls must be granted native access when required by the JDK; for example, a classpath application can use `--enable-native-access=ALL-UNNAMED`.

**Testing workflow**: build the library for the target OS/CPU, load the symbol, verify the handle type, allocate native buffers via an arena, pass the exact addresses/capacities, check status + `written` + returned bytes, and close the arena after the call finishes. Do not hard-code `size_t == long` or an assumed charset.

### 8.2. Maintaining the boundary between Java memory and C memory

- `MemorySegment.get/set` blocks out-of-bounds segment access through the Java API. **A pointer passed through FFM down to C does not carry that size guarantee to C**; buggy C code can still write past capacity, corrupting the heap/stack or crashing the JVM.
- A native library may retain a pointer after the function returns. Tests must know whether the API uses a **borrowed pointer** (used only during the call) or a **retained pointer** (kept for later use), who frees it, and which callbacks and worker threads continue using it. Do not close the `Arena` before native code has stopped using the buffer.
- `MemorySegment.ofAddress(...)`/`reinterpret(...)` does not verify that the memory behind the pointer is actually alive or large enough. Do not use `reinterpret` as a way to make an undersized-pointer test "pass".
- Some JNI/FFM errors can crash the process instead of throwing a Java exception. Run risky native tests in a **separate JVM process** and inspect exit status/ASan/UBSan/`hs_err_pid*.log` if generated. Do not use try/catch as proof of catching raw memory access errors.

### 8.3. Platform matrix

| Target | Conditions to check |
| --- | --- |
| Windows x64 | C `long` is typically 32-bit in the LLP64 ABI; `size_t` is 64-bit; matching architecture DLL |
| Linux x64 | C `long` and `size_t` are typically 64-bit in the LP64 ABI; matching ELF and dependencies |
| macOS ARM64 | AArch64 ABI, matching dylib/architecture; layout/alignment and charset per contract |
| 32-bit environments (if product supports) | `size_t`/pointers typically 32-bit; test values exceeding `UINT32_MAX` without allocating |
| JDK 22+ | Standard FFM; test `java.lang.foreign` API and native access configuration per version |
| Legacy JNI | `GetStringUTFChars` Modified UTF-8 rules, references, and local/global refs; check ownership/release |

Do not test fake pointers by writing through `MemorySegment.ofAddress(1).reinterpret(...)`: that operation can crash. Test arithmetic and ABI limits independently first, then test memory **actually allocated** by the library.

## 9. Organizing the test suite and PASS/FAIL criteria

Design three tiers:

1. **Java unit/contract**: test `null`/empty, encoding, byte size, checked arithmetic, range guards. Runs fast, no native binary dependency; the 27-test lab in section 6 fits at this tier.
2. **Native unit + sanitizer**: test C functions directly with 0-byte, 1-short, exact-fit, embedded NUL, canary, overflow, and error paths. Run ASan/UBSan or equivalent tools, preferring debug builds.
3. **Java ↔ native integration**: load the real library, configure ABI/FFM/JNI, verify status, out-params, returned lengths, byte data, lifecycle, threads, and error paths. Run on all actually supported OS/JDK/CPUs; isolate tests that risk crashing the JVM.

Add **property-based/fuzz tests** with reproducible seeds: generate random `byte[]` (including `0x00`), boundary-adjacent lengths/capacities, and multi-byte Unicode; require exact byte-for-byte round-trip when the contract is binary, or exact charset/terminator compliance when the contract is strings. Record the seed and minimal input on failure. For Java–C, compare **bytes**, status, `written`, and canaries, not just string display output.

**Acceptance criteria for a case** include: right error code/exception per contract; no corruption of data outside the buffer; no wrong byte count or illegal Unicode truncation; no arithmetic overflow; no leaks/double-frees; no sanitizer errors; no JVM hangs/crashes outside intentionally isolated tests. If the API allows partial writes, verify exactly which part may change.

### Common mistakes when writing tests

- Using `String.length()` as the UTF-8 byte count, forgetting the trailing `NUL` byte.
- Treating Java `null`, `MemorySegment.NULL`, and `""` as the same state.
- Testing only ASCII; skipping emoji (surrogate pairs), Vietnamese, and embedded NULs.
- Testing a 100-byte buffer while forgetting `required - 1`, `required`, `required + 1`.
- Using `int total = count * stride` or casting to `long` after the product has already overflowed.
- Assuming C `size_t`, C `long`, and Java `long` have the same width/ABI on all platforms.
- Testing only on the Java side, missing C buffer overruns even when `MemorySegment` bounds-checked properly.
- Forgetting that `getString` is a NUL-terminated API and does not carry the length of binary data.
- Using a default `CharsetEncoder` that replaces invalid surrogates while claiming "lossless round-trip".
- Only testing "no exception thrown" without checking status, bytes, canaries, ownership, and leaks.

## 10. Practice questions

**Exercise 1.** Java `String s = "A🌍ế";` has `s.length() == 4`. A C API requires UTF-8 NUL-terminated. What is the exact sufficient capacity? **9 bytes**: 1 for `A`, 4 for the emoji, 3 for `ế`, 1 for NUL.

**Exercise 2.** A buffer has `capacity=8`. A call needs to write 1 byte at `offset=8`. Is this valid? **No.** The last byte is at offset 7; `offset=8` is only valid for a 0-byte operation if the API allows it.

**Exercise 3.** A binary API receives bytes `{65,0,66}` and length 3. Can `getString(0)` be used to verify all 3 bytes are intact? **No.** The string function stops at NUL and only returns `"A"`; you must compare the three bytes by length.

**Exercise 4.** Is `int count=1_100_000_000; int stride=8; long bytes=count*stride;` correct? **No.** `int * int` overflows before assignment. Use `Math.multiplyExact((long)count, (long)stride)`.

**Exercise 5.** Java `MemorySegment` blocks `setString` on a buffer short by 1 byte. Does that prove a C function called via FFM cannot overflow a buffer? **No.** C only receives the address/capacity per ABI and can write incorrectly; native tests, sanitizers, and a clear contract are still required.

## References

- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): Official FFM since JDK 22.
- [Java SE 25 — MemorySegment](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/MemorySegment.html): `NULL`, `byteSize`, `getString`/`setString`, bounds checks, zero-length segments.
- [Java SE 25 — SegmentAllocator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/SegmentAllocator.html) and [Arena](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Arena.html): `allocateFrom(String)`, memory lifecycle, allocation patterns.
- [Java SE 25 — Linker](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html): canonical C layouts, `size_t`, ABI, and downcall risks.
- [Java SE 25 — JNI Functions](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html): `GetStringUTFChars`, `GetStringUTFLength`, `GetStringUTFLengthAsLong` (since JDK 24), and JNI string behavior.
- [Java SE 25 — JNI Types](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/types.html): `jsize`, Modified UTF-8, and primitive data types.
