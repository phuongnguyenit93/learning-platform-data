# Integer Type Sizes, Signedness, and Limits Across Platforms (C and ABI)

In Java interoperability with native code, the same type name such as **long** can refer to two different value ranges. Java specifies the widths of its primitive integer types, whereas C allows implementations to choose widths according to the platform and ABI. Therefore, a C library that runs correctly on 64-bit Linux may still receive incorrect data on 64-bit Windows if a programmer equates **C long**, **Java long**, and pointers.

## 1. Which concepts need to be distinguished?

- **Storage size**: **sizeof(T)** returns the number of *C-defined bytes* for an object of type T; the return type is **size_t**.
- **Number of bits in a C byte**: **CHAR_BIT** in **<limits.h>**; the C standard requires at least 8 bits/byte but does not force every system to have an 8-bit byte. **sizeof(char)** is always 1.
- **Value width**: the number of bits used to represent a value; on older implementations padding bits may exist, so one should not infer all limits solely from **sizeof(T) * CHAR_BIT**.
- **Signedness**: signed can represent negative and positive numbers; unsigned represents only non-negative numbers, with arithmetic modulo the width.
- **Limits**: the actual minimum/maximum values published by the implementation through macros such as **INT_MIN**, **INT_MAX**, **UINT_MAX**, **LONG_MAX**.
- **ABI (Application Binary Interface)**: the binary agreement on type sizes/alignments, argument passing, return values, struct layout, and calling conventions between compiled components.

**Key point:** a machine with a 64-bit CPU or a process with 64-bit pointers does not imply that **int** or **long** are 64-bit.

## 2. Basic integer types in C

| C Type | Meaning | Minimum width per C |
| --- | --- | ---: |
| **char**, **signed char**, **unsigned char** | Three distinct types; signedness of **char** usually depends on compiler/target | At least 8 bits |
| **short** / **unsigned short** | Short integer | At least 16 bits |
| **int** / **unsigned int** | Standard integer | At least 16 bits |
| **long** / **unsigned long** | Long integer | At least 32 bits |
| **long long** / **unsigned long long** | Very long integer, since C99 | At least 64 bits |

The standard guarantees the size relationship: **sizeof(char) ≤ sizeof(short) ≤ sizeof(int) ≤ sizeof(long) ≤ sizeof(long long)**. This is a *non-decreasing* relationship, so types may have the same size; the standard does not guarantee that **long** is larger than **int**. When **unsigned** is omitted, **short**, **int**, **long**, and **long long** default to signed. **char** specifically is not synonymous with **signed char**: all three are distinct types.

In addition to the above types, there are **_Bool** (C99; since C23 it can be written as **bool** as a keyword), enumerated types (**enum**), and extended integer types. **_Bool** holds logical values 0 or 1, but **sizeof(_Bool)** must not be assumed to equal 1 on every target. The underlying type and size of **enum**, bit-field layout, the **wchar_t** type, and extensions such as **__int128** do not form a common ABI contract across all compilers. C23 also adds the bit-precise width type **_BitInt(N)**, with support depending on the compiler; do not use them as a default assumption for portable libraries.

## 3. Signed/unsigned value ranges

For an unsigned type with **N value bits**, the value range is **0 .. (2^N − 1)** and unsigned arithmetic results are taken modulo **2^N**. For two's complement signed with **N total bits**, the value range is **−2^(N−1) .. 2^(N−1)−1**. That is the required representation starting from C23 and is common on modern machines; when writing C17 for uncommon systems, one should still use actual limit macros rather than assuming all signed types are two's complement.

| Width and signedness | Minimum value | Maximum value |
| --- | ---: | ---: |
| signed 8 bit | −128 | 127 |
| unsigned 8 bit | 0 | 255 |
| signed 16 bit | −32,768 | 32,767 |
| unsigned 16 bit | 0 | 65,535 |
| signed 32 bit | −2,147,483,648 | 2,147,483,647 |
| unsigned 32 bit | 0 | 4,294,967,295 |
| signed 64 bit | −9,223,372,036,854,775,808 | 9,223,372,036,854,775,807 |
| unsigned 64 bit | 0 | 18,446,744,073,709,551,615 |

The table above uses the explicitly stated bit counts and does **not** assert that C **int** is always 32-bit or **long** is always 64-bit. For example, a 32-bit **long** has the range **−2,147,483,648 .. 2,147,483,647**; a 64-bit two's complement **long** has the range **−9,223,372,036,854,775,808 .. 9,223,372,036,854,775,807**.

Useful macros in **<limits.h>** include **CHAR_BIT**, **CHAR_MIN/MAX**, **SCHAR_MIN/MAX**, **UCHAR_MAX**, **SHRT_MIN/MAX**, **USHRT_MAX**, **INT_MIN/MAX**, **UINT_MAX**, **LONG_MIN/MAX**, **ULONG_MAX**, **LLONG_MIN/MAX**, and **ULLONG_MAX**. In C23 there are also width macros such as **INT_WIDTH**, **LONG_WIDTH** when supported by the compiler. **INT_MIN** is the right macro for C **int**; do not use Java's **Integer.MIN_VALUE** as a substitute in general C programming.

## 4. Common data models: ILP32, LP64, LLP64

The data model name indicates which types are 32/64 bits long. The following table describes common ABIs with **CHAR_BIT = 8**; values are in C bytes, not a universal constraint of the C standard.

| Type | ILP32 (most 32-bit ABIs) | LP64 (Linux/macOS Unix-like 64-bit) | LLP64 (Windows 64-bit) |
| --- | ---: | ---: | ---: |
| **char** | 1 | 1 | 1 |
| **short** | 2 | 2 | 2 |
| **int** | 4 | 4 | 4 |
| **long** | 4 | 8 | 4 |
| **long long** | 8 | 8 | 8 |
| **void \*** | 4 | 8 | 8 |

- **ILP32**: **int**, **long**, and pointers are usually 32-bit. **long long** is still usually 64-bit.
- **LP64**: **long** and pointers are usually 64-bit, while **int** remains 32-bit.
- **LLP64**: **long long** and pointers are usually 64-bit, while **long** remains 32-bit. This is the Windows 64-bit model.
- There are other models and other ABIs on embedded systems/special architectures. Do not infer the data model solely from the CPU name, operating system, or **System.getProperty("os.arch")**; check the actual ABI/target.

Scenario: a C function declared as **long read_id(void)** returns the value 5,000,000,000. On LP64, a 64-bit **long** can usually hold that number; on LLP64, a 32-bit **long** cannot represent it. Changing the ABI by replacing **long** with **int64_t** in the API is a reasonable option *if* you control both sides and need a signed 64-bit range. If a third-party library already fixes **long**, you must use the library's exact ABI and check bounds when converting.

**Do not equate width and calling convention.** Two platforms that both have a 32-bit **int** can still differ in how arguments are passed via registers/stack, alignment rules, symbol names, and how structs are returned. The data model only addresses part of the ABI.

## 5. Three char types and the signedness trap

In C, **char**, **signed char**, and **unsigned char** are three distinct types. The compiler/target decides whether **char** has the same value range as **signed char** or **unsigned char**. With an 8-bit byte, a byte with the high bit set to 1 may be read as **−1** if **char** is signed, or **255** if **char** is unsigned. There is no single consistent result for the following code across all compilers:

~~~c
char c = (char)0xFF;
/* The value of c depends on the signedness of plain char and conversion when needed. */
~~~

To store binary bytes/values 0..255 on an 8-bit platform, usually use **unsigned char** or **uint8_t** when available. For specific 8-bit negative/positive numbers, use **int8_t** when available; do not switch to **char** just because they have the same size on the current machine. Use **CHAR_MIN < 0** to check the signedness of **char**, and **UCHAR_MAX** to check the actual unsigned range.

**C char differs from Java char.** Java **char** is always an unsigned 16-bit UTF-16 code unit (0..65535); C **char** is the C byte unit, usually 8-bit, carrying no inherent Unicode semantics. C strings may contain UTF-8 by API convention, but each UTF-8 byte is not a Java **char**.

## 6. Choosing portable types with <stdint.h>, <stddef.h>, <inttypes.h>

| Need | Recommended type or macro | Notes |
| --- | --- | --- |
| Exact 32/64-bit signed range in a protocol/API | **int32_t**, **int64_t** | Conditional: exists only if the implementation supports an exact-width type |
| Exact 8/32/64-bit unsigned range | **uint8_t**, **uint32_t**, **uint64_t** | Works well with well-defined byte formats; check availability |
| Need *at least* N bits | **int_leastN_t**, **uint_leastN_t** | Actual width may be larger than N |
| Need a performance-favorable type with *at least* N bits | **int_fastN_t**, **uint_fastN_t** | May be larger than N; do not use as a fixed storage layout |
| Object size and element count | **size_t** from **<stddef.h>** | Unsigned, matches the result of **sizeof**; print with **%zu** |
| Difference between two valid pointers in the same array | **ptrdiff_t** from **<stddef.h>** | Signed; print with **%td**; difference must fit in the representable range |
| Integer that can hold a **void \*** pointer | **intptr_t**, **uintptr_t** if available | Optional; does not replace **size_t** and is not a pointer serialization contract |
| Integer type at least as wide as related standard types | **intmax_t**, **uintmax_t** | Use **PRIdMAX**, **PRIuMAX** when printing |

**<stdint.h>** (C99+) defines standard fixed-width typedefs, corresponding limits such as **INT32_MIN/MAX**, **UINT64_MAX**, along with constant macros such as **INT64_C(123)**, **UINT64_C(123)**. **<inttypes.h>** has format macros **PRId32**, **PRIu64**, **PRIxPTR** for **printf**; the related **SCN...** macros are for reading with **scanf**. Do not assume **int64_t** is typedef'd to **long**: LP64 usually uses **long**, while LLP64 usually uses another 64-bit type. Therefore **printf("%ld", (int64_t)value)** can pass the wrong argument type and even cause undefined behavior; use:

~~~c
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

void print_id(int64_t id, uint64_t flags) {
    printf("id=%" PRId64 ", flags=0x%" PRIx64 "\n", id, flags);
}
~~~

The snippet above is an illustrative function, requiring the implementation to provide **int64_t/uint64_t**. **%zu** applies to **size_t**, **%td** to **ptrdiff_t**, **%ld** only to **long**, and **%lld** only to **long long**. This is a varargs type contract, not an "optional format by bit count".

## 7. Running a measurement program directly on the target

Create the file **c_integer_probe.c**:

~~~c
#include <inttypes.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>

int main(void) {
    printf("CHAR_BIT=%d\n", CHAR_BIT);
    printf("sizeof: char=%zu short=%zu int=%zu long=%zu "
           "long long=%zu void*=%zu\n",
           sizeof(char), sizeof(short), sizeof(int),
           sizeof(long), sizeof(long long), sizeof(void *));
    printf("plain char signed=%s\n", CHAR_MIN < 0 ? "yes" : "no");
    printf("int: %d..%d; unsigned int max=%u\n",
           INT_MIN, INT_MAX, UINT_MAX);
    printf("long: %ld..%ld\n", LONG_MIN, LONG_MAX);
#ifdef INT64_MAX
    printf("int64_t max=%" PRId64 "\n", INT64_MAX);
#else
    puts("int64_t is unavailable");
#endif
    return 0;
}
~~~

Compile with GCC/Clang in an environment supporting C17:

~~~bash
cc -std=c17 -Wall -Wextra -Wpedantic c_integer_probe.c -o c_integer_probe
./c_integer_probe
~~~

With the MSVC Developer Command Prompt, you can use **cl /std:c17 /W4 c_integer_probe.c** and then run **c_integer_probe.exe**. Compiler flags differ across compilers; do not pass GCC flags verbatim to MSVC.

Example output **for Linux x86-64 LP64 with signed plain char**:

~~~text
CHAR_BIT=8
sizeof: char=1 short=2 int=4 long=8 long long=8 void*=8
plain char signed=yes
int: -2147483648..2147483647; unsigned int max=4294967295
long: -9223372036854775808..9223372036854775807
int64_t max=9223372036854775807
~~~

Example output **for Windows x64 LLP64 with MSVC**:

~~~text
CHAR_BIT=8
sizeof: char=1 short=2 int=4 long=4 long long=8 void*=8
plain char signed=yes
int: -2147483648..2147483647; unsigned int max=4294967295
long: -2147483648..2147483647
int64_t max=9223372036854775807
~~~

The results above are *two examples conditioned on ABI/compiler*, not the sole stdout for the program. Running a native build with the right bitness/compiler/target is required to confirm actual results. It is also necessary to distinguish the C library's target from the running JVM: both components in the same process must be architecture- and ABI-compatible.

## 8. Conversions, promotion, overflow, and subtle bugs

### 8.1. Integer promotions and mixing signed/unsigned

In most operations, **char**, **signed char**, **unsigned char**, **short**, and **unsigned short** undergo *integer promotion* to **int** if **int** can represent the entire source value range; otherwise, to **unsigned int**. When two operands have different conversion ranks and signedness, *usual arithmetic conversions* choose a common type according to C's rules. Therefore, the initial storage size is not enough to guess the type of an expression's result.

Standalone C17 example:

~~~c
#include <stdio.h>

int main(void) {
    int debt = -1;
    unsigned int one = 1U;
    printf("%d\n", debt < one);
    return 0;
}
~~~

Output:

~~~text
0
~~~

Because **int** and **unsigned int** have the same conversion rank, **debt** is converted to **unsigned int**; the value **−1** becomes **UINT_MAX**, so comparing with 1U evaluates to false. The **-Wsign-compare** warning helps catch this common bug, but it does not replace designing consistent value ranges. Check for negative values/range *before* converting to unsigned; do not cast arbitrarily just to "silence the warning".

### 8.2. Signed overflow differs from unsigned overflow

~~~c
#include <limits.h>
#include <stdio.h>

int main(void) {
    unsigned int wrapped = UINT_MAX;
    wrapped++;
    printf("%u\n", wrapped);
    return 0;
}
~~~

Output guaranteed by the C standard:

~~~text
0
~~~

In contrast, **INT_MAX + 1** evaluated as signed **int** causes **undefined behavior**; hardware using two's complement does not make signed overflow safe under the C standard (including C23). One must check before adding, for example **if (b > 0 && a > INT_MAX - b)** when a and b are of type **int** and b is positive; for negative b, one must check **a < INT_MIN - b**. Left-shift operations can cause undefined behavior if the width is wrong or the result is not representable; for bit masks, use an unsigned type of sufficient width and check that the shift count is less than the width of the promoted type.

### 8.3. Out-of-range casts

Casting a positive/negative signed integer to an unsigned type produces a result modulo the target unsigned type's range. When converting an integer value to a **signed** type that cannot represent it, the behavior is implementation-defined or may raise a signal according to C's conversion rules; one should not expect the value to always "wrap around". This differs from overflow *of signed arithmetic operations*, which is undefined. For example, converting **jlong** (signed 64-bit) to C **long** on LLP64 can lose values: one must compare against **LONG_MIN/LONG_MAX** before casting.

A helper function when writing JNI (illustrative snippet requiring the JNI header, not a standalone C program):

~~~c
#include <jni.h>
#include <limits.h>

static int checked_jlong_to_long(jlong input, long *result) {
    if (result == NULL) {
        return 0;
    }
    if (input < LONG_MIN || input > LONG_MAX) {
        return 0;
    }
    *result = (long)input;
    return 1;
}
~~~

If a native API needs to accept the full signed 64-bit range, consider using **int64_t** or the corresponding C type **jlong** instead of forcing a cast to 32-bit **long**; changing a public API's signature must be coordinated with callers to preserve ABI compatibility.

## 9. Direct comparison with Java and JNI

Java defines the bit widths of primitive integer types independently of LP64/LLP64: **byte** 8 signed; **short** 16 signed; **int** 32 signed; **long** 64 signed; **char** 16 unsigned (UTF-16 code unit); **boolean** is not a C integer with a specified storage layout like **_Bool**.

Create the file **JavaWidths.java**:

~~~java
public class JavaWidths {
    public static void main(String[] args) {
        System.out.printf(
                "byte=%d short=%d int=%d long=%d char=%d%n",
                Byte.BYTES, Short.BYTES, Integer.BYTES,
                Long.BYTES, Character.BYTES);
        System.out.println(
                "Java long: " + Long.MIN_VALUE + ".." + Long.MAX_VALUE);
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac JavaWidths.java
java JavaWidths
~~~

Exact stdout:

~~~text
byte=1 short=2 int=4 long=8 char=2
Java long: -9223372036854775808..9223372036854775807
~~~

Java **Byte.BYTES** is measured in Java 8-bit octets; do not use it in place of C's **CHAR_BIT**. **64-bit Java long** still does not prove **64-bit C long**.

JNI defines native types with widths matching Java, using the names in **jni.h**:

| Java primitive | JNI C type | Range/width |
| --- | --- | --- |
| **boolean** | **jboolean** | unsigned 8-bit, use **JNI_FALSE/JNI_TRUE** |
| **byte** | **jbyte** | signed 8-bit |
| **char** | **jchar** | unsigned 16-bit |
| **short** | **jshort** | signed 16-bit |
| **int** | **jint** | signed 32-bit |
| **long** | **jlong** | signed 64-bit |

**jsize** is defined as **jint** and is commonly used for lengths/indices in JNI; do not arbitrarily switch to **size_t**, especially when element counts may exceed the **jint** range. When writing JNI signatures, use **jint/jlong/jchar** instead of assuming "coincidental equal sizeof" of **int/long/char**. The Java signature **(J)I** means taking **long** and returning **int**; the letter **J** here is not synonymous with C **long**.

For example, a native function that needs to add two **jint** values and return a wider result can do so by widening the type *before addition*:

~~~c
#include <jni.h>

/* The function name must match the Java class/package and JNI naming rules. */
JNIEXPORT jlong JNICALL
Java_example_NativeMath_sumWide(JNIEnv *env, jclass owner, jint a, jint b) {
    (void)env;
    (void)owner;
    return (jlong)a + (jlong)b;
}
~~~

This is a JNI function, not a C program with **main**; to run it, you need a Java class declaring **static native long sumWide(int a, int b)** in package **example**, build a shared library for the right JDK headers/target, and then load the library. Casting both operands to **jlong** *before adding* avoids 32-bit overflow when the sum exceeds **jint**.

With the Foreign Function & Memory API in supported JDK versions, layouts for calling C must also match the *native ABI*: do not assume every C **long** is a 64-bit Java **long** layout. You must cross-check the linker/canonical layouts documentation of the JDK version in use and the actual library signature.

## 10. ABI, structs, alignment, and data formats

Type size is part of the ABI, while **alignment** and **padding** affect struct member offsets. For example:

~~~c
#include <stdint.h>

struct Record {
    uint8_t kind;
    uint32_t count;
};
~~~

Even if **uint8_t** is 1 byte and **uint32_t** is 4 bytes, **sizeof(struct Record)** is not necessarily 5; the ABI may insert padding bytes before **count** or at the end of the struct. Byte order (endianness) also cannot be inferred from **LP64/LLP64**. Do not **memcpy** an entire struct and send it over the network/save to a file as a durable format without defining and controlling the full layout, packing, endianness, and versioning.

For a fixed 8-bit/octet protocol and a big-endian 32-bit unsigned integer field, encode each byte with a clear convention:

~~~c
#include <limits.h>
#include <stdint.h>

/* This example requires 8-bit bytes and the uint32_t type to be available. */
_Static_assert(CHAR_BIT == 8, "wire format requires 8-bit bytes");

static void write_u32_be(uint8_t out[4], uint32_t value) {
    out[0] = (uint8_t)(value >> 24);
    out[1] = (uint8_t)(value >> 16);
    out[2] = (uint8_t)(value >> 8);
    out[3] = (uint8_t)value;
}
~~~

With **value = 0x01020304**, the four resulting bytes are **01 02 03 04** on both little-endian and big-endian machines. This is a C helper (no **main**); the caller must provide an array of at least 4 elements. If the library must support environments without **uint32_t** or where **CHAR_BIT != 8**, choose an alternative protocol/type or reject the target, rather than silently emulating with **long**.

At the Java–native boundary, clearly determine:
1. Whether a data field is signed or unsigned; if a C **uint64_t** enters **Java long**, Java has no separate unsigned long primitive to represent the full 0..2^64−1 range in a signed sense. You can preserve the *bit pattern* in **long** with unsigned operations (**Long.compareUnsigned**, **Long.toUnsignedString**) or use **BigInteger** when you need to represent the full positive mathematical value.
2. That the native API receives the exact type and calling convention, without inferring solely from **sizeof**.
3. That there is a standard byte order, encoding, and range-checking rule if data crosses files/sockets/shared memory.
4. Do not unconditionally cast pointers to **int** or C **long**; Windows LLP64 has 64-bit pointers but 32-bit **long**. **intptr_t/uintptr_t**, if available, is the option for holding a pointer representation; do not turn pointers into IDs that can be persisted or transmitted long-term.

## 11. Common mistakes and fixes

| Mistake | Why it breaks | Safer approach |
| --- | --- | --- |
| “64-bit OS ⇒ 64-bit C long” | LLP64 keeps **long** 32-bit | Check the ABI and measure **sizeof(long)**/**LONG_MAX** |
| Using C **long** to match Java **long** | Java **long** is always 64-bit, C **long** varies | Use **jlong** in JNI; check range when converting C **long** |
| Using **char** for binary bytes and comparing against 128..255 | Plain **char** may be signed | Use **unsigned char**/**uint8_t** |
| Relying on **sizeof(int) == 4** as a C standard guarantee | C only guarantees **int** is at least 16-bit | Check runtime limits via **limits.h** or use appropriate fixed-width types |
| Printing **sizeof** with **%d**, printing **int64_t** with **%ld** | Wrong argument type for **printf** | **%zu**, **PRId64** respectively |
| Computing signed **a + b** and only then casting to a wider type | Overflow can occur *before* the cast | Cast/check *before* the operation |
| Comparing negative **int** with **unsigned** | Conversion can turn negative into a very large positive number | Unify value ranges, check negative before converting |
| Assuming a struct layout equals the sum of member **sizeof** values | ABI applies alignment/padding/packing | Explicit ABI or field-by-field encoding |
| Treating **size_t**, **ptrdiff_t**, **intptr_t** as the same type | Each type has a different contract | Choose by role: size, pointer difference, holding an address |
| Casting out-of-range numbers to signed and expecting wrap-around | Conversion result is implementation-defined; signed arithmetic overflow is undefined | Check MIN/MAX macros, handle errors |

How to verify when porting JNI/JNA/FFM or C libraries: record the target triple/compiler, word size, data model, and ABI headers; run the probe program on *each build target*; verify input/output types of each function, varargs format specifiers, struct offsets, endianness, and value ranges before any narrowing conversion. Unit tests should cover **MIN**, **MAX**, **0**, **−1**, and values around **2^31** and **2^32** where appropriate for the API's range.

## 12. Self-check questions

**Scenario A.** Both Linux x86-64 and Windows x64 run a 64-bit JVM. Java sends the number **3,000,000,000L** to a C function taking **long**. Can it be cast directly on both operating systems?

**Answer:** On LP64, C **long** is usually signed 64-bit so it can represent the value. On LLP64, C **long** is signed 32-bit so the value is out of range; you must report an error or change the API contract to a native type with sufficient range. Both JVMs having a 64-bit Java **long** does not change that.

**Scenario B.** Why can **printf("%ld", x)** with **int64_t x** work on Linux but fail on Windows, even though **sizeof(x) == 8** on both?

**Answer:** **int64_t** is an alias for a target-appropriate 64-bit type, not guaranteed to alias **long**. **%ld** requires **long** per the varargs contract; use **"%" PRId64** to print the actual type correctly.

**Scenario C.** A network byte with hex value **FF** is placed into a **char** variable; why does the **if (c < 0)** branch execute on one compiler but not on another?

**Answer:** Plain **char** has implementation-defined signedness. You need **unsigned char** or **uint8_t** to work with octets 0..255; if you want a signed 8-bit interpretation, convert with explicit checking/definition instead of relying on plain **char**.

## Standard reference documentation

- C arithmetic integer types, data models: https://en.cppreference.com/w/c/language/arithmetic_types
- C integer limits, **CHAR_BIT**, **LONG_MAX**: https://en.cppreference.com/w/c/types/limits
- C fixed-width integer types, **stdint.h/inttypes.h**: https://en.cppreference.com/w/c/types/integer
- Windows ILP32/LLP64 data model: https://learn.microsoft.com/en-us/windows/win32/winprog64/abstract-data-models
- JNI primitive/native type mapping: https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html
- GCC integer representation and C23 notes: https://gcc.gnu.org/onlinedocs/gcc/Integers-implementation.html

**Learning takeaway:** When crossing the Java/C boundary, determine **types and limits according to the actual ABI contract**, use fixed-width types when needed, read C limit macros, perform checked conversions, and verify on the exact target platform.