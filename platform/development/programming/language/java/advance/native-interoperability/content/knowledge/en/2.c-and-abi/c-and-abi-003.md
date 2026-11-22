# Why C `long`, `size_t`, and Pointers Do Not Automatically Correspond to Java `long`

When calling a C library from Java via JNI or the Foreign Function & Memory API (FFM), you cannot infer the Java type solely from the C type name or from the fact that the machine is running a 64-bit operating system. Java `long`, C `long`, `size_t`, and pointers serve different purposes; their sizes, signedness, argument passing, and data lifecycles are governed by different contracts.

**Key point:** Java `long` is always a **64-bit signed** integer; C `long` has a size that depends on the data model/ABI; C `size_t` is an **unsigned** integer for object sizes; a pointer is an **address/reference to native memory** with constraints on validity and lifetime. Having the same byte count in one environment does not mean having the same type or the same semantics.

## 1. Reading the Four Types of Contracts Correctly

| Concept | Role | Width and Signedness | What Must Be Preserved at the Java–C Boundary |
| --- | --- | --- | --- |
| Java `long` | Java language integer | Always 64-bit, **signed**, from `-2^63` to `2^63 - 1` | Numeric values and Java operations have fixed meaning across all spec-compliant JVMs |
| C `long` / `long int` | C signed integer | **At least 32-bit**; typically 32-bit or 64-bit depending on ABI | Use the exact size, alignment, and calling convention of the target ABI being called |
| C `size_t` | Result type of `sizeof`, allocation/buffer size, element count | Implementation-defined **unsigned** type; typically 32/64-bit | Preserve both width and unsigned semantics; check value range when converting |
| C `T *` / `void *` | Pointer pointing to a native object/memory region | Platform-dependent representation size; typically 32/64-bit | Pass as pointer/address; preserve lifetime, alignment, access rights, and nullability |

Do not use the conclusion “64-bit ⇒ everything is 8 bytes”. CPU, process, Java primitives, and C ABI are separate concepts. The ABI (*Application Binary Interface*) defines how C compiles data types and lays out/calls functions on a specific combination of operating system, architecture, and compiler.

In C, `sizeof(T)` returns the number of **C bytes**; `CHAR_BIT` indicates the number of bits in a C byte (typically 8 on the systems considered here). In Java, `Long.SIZE == 64` and `Long.BYTES == 8` are constants by specification.

## 2. Why Is C `long` Different from Java `long`?

C only guarantees `sizeof(char) <= sizeof(short) <= sizeof(int) <= sizeof(long) <= sizeof(long long)` in order of appropriate width, while `long` has a value range of at least 32 bits. Common ABIs choose the following data models, with figures in **standard 8-bit bytes**:

| Common Model | `int` | C `long` | `size_t` | `void *` | Java `long` |
| --- | ---: | ---: | ---: | ---: | ---: |
| ILP32 (common 32-bit applications) | 4 | 4 | 4 | 4 | 8 |
| LP64 (common 64-bit Linux/macOS) | 4 | 8 | 8 | 8 | 8 |
| LLP64 (common 64-bit Windows) | 4 | 4 | 8 | 8 | 8 |

The name LP64 describes `long` and pointers being 64 bits wide; LLP64 describes `long long` and pointers being 64 bits wide, while `long` remains 32 bits. These are **common models**, not definitions for every C system or every kind of pointer.

For example, a native library exposes:

```c
long calculate(long value);
```

On Linux/x64 LP64, the `long` parameter and result are typically 8 bytes. On Windows/x64 LLP64, they are typically 4 bytes. If you describe this function with an 8-byte Java `long` parameter/result in FFM on Windows, the ABI description is wrong. The fact that “the Java number is also named long” does nothing to determine the native call. Similarly, forcing `4294967296L` from Java into a 32-bit C `long` exceeds the representable range; the result of converting to a signed C type out of range has no guaranteed portable value.

### C Experiment: Measuring the Actual ABI

Create the file `abi_probe.c` (C99 or later):

```c
#include <limits.h>
#include <stddef.h>
#include <stdio.h>

int main(void) {
    printf("CHAR_BIT=%d\n", CHAR_BIT);
    printf("sizeof(int)=%zu\n", sizeof(int));
    printf("sizeof(long)=%zu\n", sizeof(long));
    printf("sizeof(long long)=%zu\n", sizeof(long long));
    printf("sizeof(size_t)=%zu\n", sizeof(size_t));
    printf("sizeof(void*)=%zu\n", sizeof(void *));
    printf("LONG_MAX=%ld\n", LONG_MAX);
    return 0;
}
```

With GCC or Clang: `cc -std=c11 -Wall -Wextra -o abi_probe abi_probe.c`, then `./abi_probe` (on Windows, run the corresponding executable). The `%zu` format specifier is for a `size_t` value/`sizeof` result; `%ld` is for `long`. Do not use `%ld` to print `size_t`.

**Example output on common Linux/x64 LP64:**

```text
CHAR_BIT=8
sizeof(int)=4
sizeof(long)=8
sizeof(long long)=8
sizeof(size_t)=8
sizeof(void*)=8
LONG_MAX=9223372036854775807
```

**Example output on common Windows/x64 LLP64:**

```text
CHAR_BIT=8
sizeof(int)=4
sizeof(long)=4
sizeof(long long)=8
sizeof(size_t)=8
sizeof(void*)=8
LONG_MAX=2147483647
```

These are two **ABI-conditional** outputs, not fixed results for all systems. Compile for the exact native target where the library will run; do not use the sizes on the development machine to infer sizes on another system.

### Java Experiment: Fixed Size, Signed Value

Create `JavaLongProbe.java` (Java 17+):

```java
public class JavaLongProbe {
    public static void main(String[] args) {
        long rawBits = Long.parseUnsignedLong("18446744073709551615");

        System.out.println("int bytes=" + Integer.BYTES);
        System.out.println("long bytes=" + Long.BYTES);
        System.out.println("signed bits=" + rawBits);
        System.out.println("unsigned bits=" + Long.toUnsignedString(rawBits));
    }
}
```

Run `javac JavaLongProbe.java` and `java JavaLongProbe`. The result is **identical across Java 17+ compliant JVMs**:

```text
int bytes=4
long bytes=8
signed bits=-1
unsigned bits=18446744073709551615
```

The same 64-bit pattern of all 1s is interpreted as signed `-1` by Java `long`; the unsigned method only **reinterprets the bit pattern** into an unsigned numeric string. It does not turn the primitive `long` type into a new unsigned type.

## 3. `size_t`: Same 8 Bytes Can Still Have a Different Value Range

`size_t` is declared via `<stddef.h>` and is an **unsigned** integer type used for `sizeof`, `malloc`, `strlen`, and object/buffer sizes. On a common 64-bit system, `size_t` typically represents `0 … 2^64-1`, whereas signed Java `long` represents `-2^63 … 2^63-1`.

Therefore, when native code returns a `size_t` whose highest bit is 1, putting those same 64 bits into a Java `long` yields a **negative value when viewed as signed**. Do not use the condition `result < 0` to infer a native error if the C function specification defines the result as a valid `size_t`. You must read the API contract: for example, `strlen` does not use negative numbers as error codes, whereas many other APIs use `ssize_t` (a signed type distinct from `size_t`) or a dedicated sentinel.

Important handling operations:

- If `size_t` is **32 bits** wide and FFM uses a Java `int` carrier: `Integer.toUnsignedLong(rawInt)` gives the unsigned value in `0 … 2^32-1`.
- If `size_t` is **64 bits** wide and FFM uses a Java `long` carrier: `Long.toUnsignedString(rawLong)`, `Long.compareUnsigned`, `Long.divideUnsigned`, or `BigInteger` help process/display the unsigned range. Some ordinary signed arithmetic operations are no longer appropriate.
- When **passing a Java size down to native**, check the limits of the target type and the actual byte/buffer count. For APIs that only accept non-negative lengths within the signed Java `long` range, `Math.toIntExact` is useful if the target requires signed 32-bit; it **does not automatically replace range checking for unsigned `size_t`**.
- When C uses `size_t` to describe a byte count, Java must allocate a memory region of sufficient size; type-correct arithmetic that reads out of bounds is still a memory error.

You should also distinguish `ptrdiff_t` (the difference between two valid pointers, a signed type) and `ssize_t` (a common signed type in POSIX, not `size_t`). In JNI, `jsize` is defined as `jint` (signed 32-bit) to represent Java array lengths/indices; it is **not** a direct alias of `size_t`. Therefore, do not pass an arbitrary 64-bit `size_t` into `jsize` while skipping range checks.

## 4. Pointers: Addresses and Access Rights, Not Long Integers

`void *` or `char *` represents a location in the process's address space and the semantics of pointing to an object. Even though `sizeof(void *) == 8` and `sizeof(long) == 8` on LP64, C still distinguishes pointers from integers. A pointer is also tied to:

1. **Null and validity:** a null pointer does not point to an object; a non-null address may also have become invalid.
2. **Lifetime/ownership:** memory allocated with `malloc` needs `free` according to the contract; a pointer to a stack variable becomes invalid when the variable's lifetime scope ends; Java heap regions can be managed/moved by the JVM.
3. **Bounds and alignment:** knowing the address is not enough to read N bytes or interpret it as a `struct`; you must know the size, layout, alignment, and permitted access.
4. **Type and calling convention:** `void *` (data pointer) and function pointers must not be assumed to have the same representation on every C implementation.

C has `intptr_t` / `uintptr_t` types in `<stdint.h>` **if provided by the implementation** to support an integer representation that can hold a `void *` pointer; even when round-tripping the exact bits, that numeric value does not by itself guarantee the memory region is still alive. `size_t` is meant to store object sizes, **not** the standard type for converting pointers to numbers. C `long` is even less of a portable choice for pointers because on LLP64 pointers are 64-bit while `long` is 32-bit.

In Java 22+ FFM, native pointers typically use `ValueLayout.ADDRESS` with a `MemorySegment` carrier, rather than forcing them into `ValueLayout.JAVA_LONG`. When native code returns an address, Java needs a contract defining how long the pointed-to memory region remains valid and within what bounds it may be read/written. Choosing the right layout is only the first step; managing lifetime and access bounds remains mandatory.

## 5. Choosing Layouts by ABI with FFM (Java 22+)

FFM became a standard API in Java 22 (package name `java.lang.foreign`). `ValueLayout.JAVA_LONG` describes an **8-byte Java long**; `ValueLayout.ADDRESS` describes a native address with platform-dependent width. `Linker.nativeLinker().canonicalLayouts()` provides standard layouts for C type names of the **running ABI** such as `long`, `size_t`, `void*`.

Create `NativeLayouts.java` and run with JDK 22+:

```java
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.ValueLayout;
import java.util.Map;

public class NativeLayouts {
    public static void main(String[] args) {
        Map<String, MemoryLayout> abi = Linker.nativeLinker().canonicalLayouts();

        System.out.println("Java long=" + ValueLayout.JAVA_LONG.byteSize());
        System.out.println("C long=" + abi.get("long").byteSize());
        System.out.println("C size_t=" + abi.get("size_t").byteSize());
        System.out.println("C void*=" + abi.get("void*").byteSize());
        System.out.println("Address=" + ValueLayout.ADDRESS.byteSize());
    }
}
```

Command: `javac NativeLayouts.java` then `java NativeLayouts`. On common x64 JVMs, the `Java long`, `C size_t`, `C void*`, and `Address` lines are `8`; the `C long` line is typically `8` on Linux and `4` on Windows. The snippet above **only inspects layouts**, does not call a native function, and therefore does not require a custom C library.

If a C header declares the hypothetical function:

```c
long count_matches(size_t length, const void *data);
```

then the signature description in Java can be:

```java
// Illustrative snippet, placed in code that already has the 'abi' variable from the example above.
var descriptor = java.lang.foreign.FunctionDescriptor.of(
        abi.get("long"),
        abi.get("size_t"),
        ValueLayout.ADDRESS
);
```

This is **an illustrative snippet**, not a standalone program, and does not yet perform a downcall because there is no native symbol/library address. When building a real `MethodHandle`, the Java carrier of the `length` parameter can be `int` (32-bit native `size_t`) or `long` (64-bit native `size_t`); the pointer is passed via `MemorySegment`. The fact that `size_t` is unsigned must also be handled at the **value level**, in addition to choosing the byte layout. Read the actual header, determine the ABI, and check `MethodHandle.type()` before calling; declaring an incorrect function descriptor can cause severe errors, including crashing the process.

**Do not use `ValueLayout.JAVA_LONG` for every name containing “long”, “size”, or “pointer”.** For a C `long` argument on Windows/x64, the corresponding ABI layout is typically `ValueLayout.JAVA_INT`; only on Linux/x64 is it typically `ValueLayout.JAVA_LONG`. Meanwhile, a data pointer still uses `ADDRESS` on both systems, even though the size of C `long` differs.

## 6. JNI: `jlong` Is Not C `long`

JNI fixes primitive types corresponding to Java: `jint` is signed 32-bit, `jlong` is signed 64-bit, and `jsize` is a typedef of `jint`. Therefore, a native function written to a JNI signature may receive a 64-bit `jlong` on Windows/x64, while **another C API** that the function calls still has a 32-bit `long` parameter.

Suppose Java passes a `long requestCount` value to JNI, and JNI then needs to call `long process(long count)` from a C library. The proper flow is:

1. JNI receives `jlong requestCount` per the JNI signature.
2. Check `LONG_MIN <= requestCount <= LONG_MAX` according to `<limits.h>` of the **target C ABI**, and handle the error explicitly if out of range.
3. Only after the condition is met, convert to C `long` and call `process`.
4. When returning the result, determine whether C returns a signed `long`, an unsigned size, or an error code, and convert to the Java type according to that **semantics**.

JNI does not automatically convert every C `size_t` into `jsize`, and `jlong` is not a promise that every handle/pointer can be stored directly in a Java `long`. Some libraries choose to use a `jlong` number as an **opaque native handle**, but that must be an explicit API contract: create/destroy handles, recognize closed handles, validate them, and synchronize access. Avoid letting Java perform arithmetic on a handle as if it were an ordinary size or address.

## 7. Common Mistakes and How to Fix Them

| Incorrect Writing/Reasoning | Why It Is Wrong | How to Handle It |
| --- | --- | --- |
| “64-bit application so C `long` = Java `long`” | Windows/x64 LLP64 uses 4-byte C `long` | Check ABI/header; get canonical layout from native linker |
| “`size_t` is `long` because both are usually 8 bytes” | `size_t` is unsigned; C `long` is signed and can be 4 bytes | Keep `size_t` layout and check/interpret as unsigned |
| “`void *` is `long` because both are 64-bit” | Pointers have different carrier, lifetime, alignment, and access rights than integers | Use pointer/address layout; manage native memory region |
| “`jlong` is an alias for C `long`” | `jlong` is fixed 64-bit, C `long` depends on ABI | Convert types with range checking at the JNI boundary |
| “FFM `JAVA_LONG` represents all 64-bit values” | Signed carrier does not directly represent the unsigned range `2^63 … 2^64-1` | Use unsigned helpers or `BigInteger` per contract |
| “`sizeof(ptr)` is the capacity of the pointed-to region” | `sizeof(ptr)` measures the size of the **pointer variable**, not the buffer | Pass size separately; `sizeof(*ptr)` only measures the pointed-to object type |
| “Works on Linux so it is safe on Windows” | Headers, ABI, calling convention, and byte order may differ | Check each native target and test boundary cases |

Special note on `sizeof`: for `char *p`, `sizeof(p)` is the size of the pointer, **not** the length of the string at `p`; use `strlen(p)` only when `p` points to a valid null-terminated C string. When accessing arrays, the **element** count differs from the **byte** count: `sizeof(array) / sizeof(array[0])` only makes sense when `array` is actually an array right at that expression, not when it has decayed into a pointer when passed to a function.

## 8. Process for Designing a Safe Java ↔ C API

1. **Start from the real C header:** record exact return/parameter types, including pointer levels, `const`, `size_t`, `stdint.h` types (such as `int64_t`), and ownership/error contracts.
2. **Lock down the native target:** operating system, architecture, ABI, and how the native library/JVM is compiled. Measure types with a C program or consult ABI documentation; do not infer from the OS name alone.
3. **Map types by semantics:** 64-bit signed integer ⇄ Java `long` when the range matches; C `long` ⇄ ABI layout; `size_t` ⇄ unsigned native size; `T *` ⇄ native address/segment or managed opaque handle.
4. **Check ranges before converting:** avoid narrowing, sign extension, overflow, and false negative numbers from unsigned interpretation; verify that length is compatible with actual memory region size.
5. **Respect calling conventions:** the FFM descriptor or JNI signature must reflect the native signature; do not assume struct layout, packing, or pointers solely from matching scalar sizes.
6. **Test per platform:** at least cross-check LP64 and LLP64 if supporting both Linux and Windows x64; test boundary values `0`, `LONG_MAX`, `2^31`, `2^32`, and high-bit unsigned patterns (only when meaningful per contract).
7. **Test lifetime:** can native code retain the pointer after the function returns, who frees it, when does the segment become invalid, and how are repeated calls/double closes handled?

If you control the C API you design, `int32_t`/`int64_t` types (when supported) help state **integer width** more clearly than `long`; however, they do not replace handling signedness, struct layout, calling convention, or pointer lifetime. Do not unilaterally change an external C library's `size_t`/pointer into `int64_t` just to match Java.

## 9. Self-Check Questions

**Scenario A.** Java runs on Windows x64, `Long.BYTES == 8`. A C function returns `long`. Should `ValueLayout.JAVA_LONG` be used for the return? **No**: under the common LLP64 ABI, C `long` is 4 bytes; choose the layout published by the native linker for `long` (typically `JAVA_INT`).

**Scenario B.** C returns a 64-bit `size_t` with bit pattern `0xFFFFFFFFFFFFFFFF`. Java views it as `long` and gets `-1`. Can we conclude native code reported an error? **No**: if the C contract returns an unsigned size, the same bit pattern represents `18446744073709551615`. You must decode it according to the contract and check whether that value is actually valid in the specific scenario.

**Scenario C.** `sizeof(void*) == sizeof(long) == 8` on Linux x64. Can we put a pointer into a Java `long` and treat it as a safe 8-byte memory region? **No**: matching size does not grant read permission, does not indicate how many bytes were allocated, and does not keep the memory alive. You must use a pointer/handle interface with defined bounds and lifetime.

**Scenario D.** JNI has a `jlong` parameter; can it be cast directly to C `long` and passed to a C library on every platform? **No**: check the range of the target C `long` before converting and handle out-of-range cases.

## Reference Documentation

- Oracle Java 22 `Long`: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/Long.html
- Oracle Java 22 `Linker`, section “Describing C signatures” and `canonicalLayouts()`: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html
- Oracle Java 22 `ValueLayout` and `ADDRESS`: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html
- Java Native Interface Specification, primitive types and `jsize`: https://docs.oracle.com/en/java/javase/26/docs/specs/jni/types.html
- C `size_t`: https://cppreference.com/c/types/size_t

**Technical conclusion:** Choose types across the Java–C boundary based on **semantics + width + signedness + ABI + lifetime**, never based on two types having the same name or the same byte count on the current machine.