# Using Linker's canonicalLayouts to match ABI C types

When Java calls a C library through the **Foreign Function & Memory API (FFM)**, you must accurately describe the size, alignment, and value-passing convention of each parameter/return value in the **ABI** (Application Binary Interface) being used. A common misconception is to assume C `long` always corresponds to Java `long` (64-bit). That is true on Linux/x64 under the LP64 model, but **not true on Windows/x64** under LLP64, where C `long` is usually only 32 bits.

Since JDK 22, the stable FFM API provides:

```java
Map<String, MemoryLayout> layouts =
    Linker.nativeLinker().canonicalLayouts();
```

This is **a snippet inside a Java method**, not a standalone program. `canonicalLayouts()` returns the set of standard `MemoryLayout`s for the **native ABI used by the current JVM**. Instead of guessing by Java type name or operating system, we query `Linker` for C `int`, `long`, `size_t`, `wchar_t`, and `void*`, then inspect `byteSize()`, `byteAlignment()`, and the layout's carrier. When high confidence is needed, compare those results with C code compiled **using the exact toolchain that builds the target library**, using `sizeof`, `_Alignof`, and `offsetof`.

This article belongs to the **Data Layout** group of Java Advance — native-interoperability. The key topics are: the ABI source, the list of guaranteed names, why unsigned types do not have universal separate layouts, how to build `FunctionDescriptor` and `structLayout`, a Java ↔ C comparison program, and pitfalls that can cause a downcall with a mismatched signature.

> **Version scope:** Examples use the stable `java.lang.foreign` in **JDK 22 and later** (JEP 454). JDK 21 still used FFM preview; Java 17 does not have this standard API. Commands are demonstrated on **Linux/x86-64**; querying `canonicalLayouts()` works on ABIs supported by the native linker.

## 1. Why does "the same C type" have multiple layouts?

A C declaration:

```c
long calculate(long value);
```

does not describe the entire binary contract. To call it from Java, the runtime needs to know:

1. **The size** of C `long`: typically 4 or 8 bytes.
2. **The alignment** of the value: can affect `struct` layout and how memory is accessed.
3. **How parameters/return values are passed** via registers, stack, and calling convention.
4. **ABI rules** for aggregates, pointers, return-by-value, and varargs.
5. **The symbol and calling convention** of the specific C library, including compiler flags that alter layout.

You cannot simply look at a "64-bit" CPU and deduce that all C integers are 64-bit. Java defines `int` as 32-bit and `long` as 64-bit, whereas C depends on the ABI/implementation. Some common data models:

| Data model | C `int` | C `long` | C `long long` | pointer | Typical examples |
| --- | ---: | ---: | ---: | ---: | --- |
| ILP32 | 32 bit | 32 bit | 64 bit | 32 bit | Common 32-bit environments |
| LP64 | 32 bit | 64 bit | 64 bit | 64 bit | Linux/x64, macOS/x64 |
| LLP64 | 32 bit | 32 bit | 64 bit | 64 bit | Windows/x64 |

These are **common models**, not a substitute for checking a specific ABI. For instance, `wchar_t` is usually 4 bytes on Linux/x64 and 2 bytes on Windows/x64, but you should not infer that solely from `char` or `long`. Nor does a data model specify the calling convention, compiler-specific alignment, or rules for a special `struct`.

FFM has one native linker for the **current OS + processor** combination. `Linker.nativeLinker()` is not a tool to emulate another ABI on the running machine: if the JVM is Linux/x64, it reports the ABI supported by that runtime, rather than switching to Windows/x64 just because you want to read a DLL.

### 1.1. MemoryLayout and ABI are not the same thing

`MemoryLayout` describes size, alignment, data shape, and field layout. `Linker` knows how to use supported layouts when creating a method handle to call a native function according to the ABI. These two concepts have distinct responsibilities:

- `MemoryLayout` answers: how many bytes is this region, how is it aligned, at what offset is a field?
- `ValueLayout` is an atomic layout with a **Java carrier** such as `int.class`, `long.class`, `float.class`, `MemorySegment.class`.
- `FunctionDescriptor` describes the parameter and return layouts of a native signature.
- `Linker` validates/arranges calls from a descriptor according to the calling convention, while also providing **canonical layouts** as a reference point.

A descriptor with matching sizes but the wrong C kind, wrong parameter count, or wrong calling convention can still cause serious program failures. FFM has no metadata from the C symbol to prove that the descriptor you wrote matches the prototype; **the responsibility for verifying the native signature belongs to the integrator**.

## 2. How to access `canonicalLayouts()`

The key APIs:

```java
Linker linker = Linker.nativeLinker();
Map<String, MemoryLayout> canonical = linker.canonicalLayouts();

MemoryLayout cLong = canonical.get("long");
MemoryLayout cSizeT = canonical.get("size_t");
MemoryLayout pointer = canonical.get("void*");
```

This is a snippet inside a Java method that imports `java.lang.foreign.*` and `java.util.Map`. The key names are **exact C type names according to the API syntax**, not Java class syntax. For example:

- Correct: `"long"`, `"long long"`, `"size_t"`, `"void*"`.
- Not guaranteed keys: `"long_long"`, `"java.lang.Long"`, `"sizeT"`, `"void *"` (with a space), `"unsigned long"`.
- In practice, additional keys may exist depending on the native linker; portable code should only **rely on the keys guaranteed by the specification**, or check for presence when using extensions.

### 2.1. Eleven guaranteed standard keys

The Javadoc of `Linker` guarantees that the native linker provides canonical layouts for:

| Exact key | Target C type | Guidance when choosing layout |
| --- | --- | --- |
| `"bool"` | C `_Bool`/`bool` | Java carrier boolean; not an arbitrary pointer or integer |
| `"char"` | C `char` | Describes one C char; signedness of plain char is implementation-defined |
| `"short"` | C `short` | Size and alignment per ABI |
| `"int"` | C `int` | Do not infer just because Java also has `int` |
| `"long"` | C `long` | Notably differs between LP64 and LLP64 |
| `"long long"` | C `long long` | Usually Java `long` carrier on common ABIs |
| `"float"` | C `float` | Usually `ValueLayout.JAVA_FLOAT` |
| `"double"` | C `double` | Usually `ValueLayout.JAVA_DOUBLE` |
| `"size_t"` | C `size_t`, unsigned size type | 32-bit or 64-bit depending on ABI |
| `"wchar_t"` | C `wchar_t` | Width varies by platform, not identical to Java `char` |
| `"void*"` | C pointer | Described by an address layout, Java carrier `MemorySegment` |

Note: checks rely on `Map.get(...) != null` only when the key is in the guaranteed list. For extended C types or custom typedefs, you must check the C header, compiler, and ABI; **do not** assume every C typedef name will appear in the map.

### 2.2. The map is read-only

`canonicalLayouts()` returns an **unmodifiable map**. You can read it, but you cannot use `put` to "fix C long to 8 bytes". If the mapping does not match the actual C binary, the issue lies in an **ABI mismatch or library build**, not a missing map mutation.

Each layout is a descriptive object. When you need a field name in a `struct`, you can create a *derived layout* with `layout.withName("field")`; that **does not modify the original map**. When you need to change alignment for packed data, consider carefully because the layout is no longer the canonical natural-aligned layout supported by the ABI by default.

### 2.3. What is inside each `MemoryLayout`?

```java
MemoryLayout l = canonical.get("size_t");

long bytes = l.byteSize();
long alignment = l.byteAlignment();

if (l instanceof ValueLayout v) {
    Class<?> carrier = v.carrier();
    System.out.println(carrier.getName());
}
```

Illustrative code snippet, not a standalone file. `byteSize()` and `byteAlignment()` are **in bytes**, not bits. `ValueLayout.carrier()` tells you the Java type used when getting/setting or when a `MethodHandle` passes the value by-value across the native boundary. For example, a 4-byte C `long` usually needs the carrier `int.class`, not `long.class`, even though the C name contains the word "long".

Similarly, C `void*` uses `AddressLayout` with carrier `MemorySegment.class`. Just because an ABI pointer is 8 bytes does not mean it should be described with `ValueLayout.JAVA_LONG`; **pointer calling conventions and ownership are not the same as a 64-bit integer**.

## 3. Typical reference table, avoid hard-coding

This table describes the common **Linux/x86-64 LP64**, where the C compiler uses the System V ABI:

| C type | Typically corresponding layout | Java carrier | Common byte size |
| --- | --- | --- | ---: |
| `bool` | `ValueLayout.JAVA_BOOLEAN` | `boolean` | 1 |
| `char` | `ValueLayout.JAVA_BYTE` | `byte` | 1 |
| `short` | `ValueLayout.JAVA_SHORT` | `short` | 2 |
| `int` | `ValueLayout.JAVA_INT` | `int` | 4 |
| `long` | `ValueLayout.JAVA_LONG` | `long` | 8 |
| `long long` | `ValueLayout.JAVA_LONG` | `long` | 8 |
| `float` | `ValueLayout.JAVA_FLOAT` | `float` | 4 |
| `double` | `ValueLayout.JAVA_DOUBLE` | `double` | 8 |
| `size_t` | `ValueLayout.JAVA_LONG` | `long` | 8 |
| `wchar_t` | Usually a 4-byte integer layout | `int` | 4 |
| `void*` | `ValueLayout.ADDRESS` | `MemorySegment` | 8 |

This table is **not an assumption you are allowed to hard-code into every program**. On Windows/x64 LLP64, C `long` is usually 4 bytes (carrier `int`), while `size_t` and C pointers are usually 8 bytes. `wchar_t` is usually 2 bytes and differs from Java `char` in ABI/encoding semantics. If you are linking a C library built by a compiler with different packing/ABI settings, results may differ from expectations.

The programming advice is to **fetch the map and inspect it on the target runtime**:

```java
MemoryLayout cLong = linker.canonicalLayouts().get("long");
System.out.println("C long bytes=" + cLong.byteSize());
```

Let the runtime tell you the real number, instead of writing:

```java
// Non-portable way of writing: assuming C long = Java long.
FunctionDescriptor wrong = FunctionDescriptor.of(
    ValueLayout.JAVA_LONG, ValueLayout.JAVA_LONG);
```

The two snippets above are illustrative; the second **can be ABI-incorrect** if the native prototype uses C `long` in an LLP64 environment. When a descriptor does not match, the runtime cannot infer from the C symbol to fix it for you.

## 4. Carriers differ in signedness and Java type semantics

### 4.1. Unsigned C types can still use a signed Java carrier

C has `unsigned char`, `unsigned int`, `unsigned long`, `size_t`; Java does not have corresponding unsigned primitive types covering the full value range. A canonical layout usually uses **the same storage/calling convention** as the signed type of the same width. However, Java still interprets `byte/int/long` as signed.

Example of the bit pattern when the ABI of C `unsigned int` is 32 bits:

```java
int raw = -1; // Same 32 bits all 1s when viewed at the bit level.
long unsigned = Integer.toUnsignedLong(raw);

System.out.println(unsigned); // 4294967295
```

This is a Java method snippet. The Java value `-1` and `4294967295` are two interpretations of **the same 32-bit pattern**, not two different memory layouts. For a 32-bit C `size_t`, `Integer.toUnsignedLong` lets you represent lengths larger than `Integer.MAX_VALUE` as a positive Java `long`.

For a 64-bit C `size_t`, the Java carrier is usually `long`. When the high bit = 1, the Java `long` value can be negative; use `Long.toUnsignedString(value)` or `Long.compareUnsigned(...)` when displaying/comparing 64-bit unsigned values. Do not use `Math.abs` to "convert unsigned" because `Long.MIN_VALUE` remains negative and the full 64-bit unsigned range cannot be represented by a positive Java signed long.

A C function taking `size_t length` needs additional business validation: `length` is a byte count, not necessarily equal to Java `String.length()` (number of UTF-16 code units). If accepting a byte buffer, ensure the length does not exceed `MemorySegment.byteSize()` and does not cause native code to read out of bounds.

### 4.2. C `char` and `wchar_t` are not Java `char`

- C `char` is typically an 8-bit byte unit; the signedness of **plain `char`** is implementation-defined.
- Java `char` is an **unsigned 16-bit UTF-16 code unit**; do not blindly use it as the carrier for C `char`.
- C `wchar_t` has OS/toolchain-dependent size and encoding. It can be 2 bytes or 4 bytes, but **does not guarantee the same encoding semantics** as Java `char`.
- For UTF-8/C string APIs, pass a `MemorySegment` containing bytes in the agreed encoding and a NUL terminator when required by the C API.
- For wide-character APIs, clarify the actual encoding and `wchar_t` size; do not directly copy a Java `char[]` and treat it as a portable `wchar_t[]`.

Canonical layouts establish the **binary** format according to the ABI; they do not automatically resolve **character string semantics**.

### 4.3. Pointers differ from `long`

C `void*`, `char*`, `struct Foo*` are described by an address layout with carrier `MemorySegment`. For example:

```java
MemoryLayout pointer = linker.canonicalLayouts().get("void*");
if (!(pointer instanceof AddressLayout)) {
    throw new IllegalStateException("Unexpected pointer layout");
}
```

Even if the pointer's `byteSize()` is 8, you should not replace it with `JAVA_LONG` in `FunctionDescriptor`. When a pointer is returned from C, the Java `MemorySegment` receives the address but **does not automatically know the target memory region's length**. You must have a contract for bounds, ownership, alignment, liveness, and when C is allowed to free it. An invalid pointer can cause a crash even when the descriptor uses the right `AddressLayout`.

## 5. Complete Java 22+ program: print ABI layouts and build a struct

To avoid guessing by intuition, let us write a Java program that queries `canonicalLayouts()` of the current runtime, prints **the 11 required C types**, and builds a `struct` with fields C `char`, `long`, and `size_t`. The program **does not call any native function**, so it needs neither a C library nor restricted native access permission just to inspect layouts.

The C struct to model:

```c
typedef struct AbiRecord {
    char tag;
    long count;
    size_t bytes;
} AbiRecord;
```

This is an illustrative C declaration; the next section has a complete C file to print `sizeof`, `_Alignof`, and `offsetof` of the actual struct.

### 5.1. File `AbiLayoutsDemo.java`

```java
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.foreign.StructLayout;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public final class AbiLayoutsDemo {
    private static final String[] C_TYPES = {
        "bool", "char", "short", "int", "long", "long long",
        "float", "double", "size_t", "wchar_t", "void*"
    };

    private AbiLayoutsDemo() {}

    private static MemoryLayout require(
        Map<String, MemoryLayout> abi, String type) {

        MemoryLayout layout = abi.get(type);
        if (layout == null) {
            throw new IllegalStateException(
                "Missing canonical layout: " + type);
        }
        return layout;
    }

    private static long padTo(long offset, long alignment) {
        return (alignment - (offset % alignment)) % alignment;
    }

    private static StructLayout abiRecordLayout(
        Map<String, MemoryLayout> abi) {

        String[] types = {"char", "long", "size_t"};
        String[] names = {"tag", "count", "bytes"};

        List<MemoryLayout> members = new ArrayList<>();
        long offset = 0;
        long maxAlign = 1;

        for (int i = 0; i < types.length; i++) {
            MemoryLayout field = require(abi, types[i])
                .withName(names[i]);
            long align = field.byteAlignment();
            long padding = padTo(offset, align);

            if (padding > 0) {
                members.add(MemoryLayout.paddingLayout(padding));
            }
            members.add(field);

            offset += padding + field.byteSize();
            maxAlign = Math.max(maxAlign, align);
        }

        long trailing = padTo(offset, maxAlign);
        if (trailing > 0) {
            members.add(MemoryLayout.paddingLayout(trailing));
        }

        return MemoryLayout.structLayout(
            members.toArray(MemoryLayout[]::new));
    }

    public static void main(String[] args) {
        Linker linker = Linker.nativeLinker();
        Map<String, MemoryLayout> abi = linker.canonicalLayouts();

        System.out.printf("%-10s %4s %5s%n",
                          "C type", "size", "align");

        for (String type : C_TYPES) {
            MemoryLayout layout = require(abi, type);
            System.out.printf("%-10s %4d %5d%n",
                              type,
                              layout.byteSize(),
                              layout.byteAlignment());
        }

        StructLayout record = abiRecordLayout(abi);

        System.out.printf("record-size=%d%n",
                          record.byteSize());
        System.out.printf("record-align=%d%n",
                          record.byteAlignment());

        for (String name : new String[] {
                "tag", "count", "bytes"}) {
            long offset = record.byteOffset(
                PathElement.groupElement(name));
            System.out.printf("offset-%s=%d%n", name, offset);
        }
    }
}
```

This is a **complete Java file**. Each table row prints `byteSize/byteAlignment` provided directly by the native linker, without hard-coding by OS. It does not use `Map.entrySet()` to print all keys, because beyond the 11 required keys, the order and set of extra keys can differ across JVMs. The fixed `C_TYPES` array keeps the output in a clear order for comparing against C output.

The `AbiRecord` construction uses C layouts **for the current ABI**. It computes the padding needed before each field according to the field's alignment, then adds trailing padding so the struct size is a multiple of the max alignment. For instance, on Linux/x64, `char tag` occupies byte 0, `long count` needs alignment 8 so there are 7 bytes of padding, `size_t bytes` is at offset 16, and the struct is 24 bytes. On Windows/x64, C `long` is usually 4 bytes, so `count` is at offset 4 and `bytes` is at 8, totaling 16 bytes.

**Important:** `MemoryLayout.structLayout(...)` **does not automatically insert padding for you**; if members are unaligned, it can throw an error. The alignment calculation in the code above applies to **normal** structs without `#pragma pack`, bit-fields, or other extensions. A complex ABI may have additional rules for aggregates and argument passing; always verify against the C compiler.

## 6. Complete C11 program: `sizeof`, `_Alignof`, and `offsetof`

The following C code is compiled with the native toolchain to measure **the exact ABI the library uses**. In production, use the compiler, target triple, and packing options matching the C library you are integrating.

### 6.1. File `abi_probe.c`

```c
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <wchar.h>

typedef struct AbiRecord {
    char tag;
    long count;
    size_t bytes;
} AbiRecord;

#define PRINT_TYPE(label, type) \
    printf("%-10s %4zu %5zu\n", \
           label, sizeof(type), (size_t)_Alignof(type))

int main(void) {
    printf("%-10s %4s %5s\n",
           "C type", "size", "align");

    PRINT_TYPE("bool", bool);
    PRINT_TYPE("char", char);
    PRINT_TYPE("short", short);
    PRINT_TYPE("int", int);
    PRINT_TYPE("long", long);
    PRINT_TYPE("long long", long long);
    PRINT_TYPE("float", float);
    PRINT_TYPE("double", double);
    PRINT_TYPE("size_t", size_t);
    PRINT_TYPE("wchar_t", wchar_t);
    PRINT_TYPE("void*", void *);

    printf("record-size=%zu\n", sizeof(AbiRecord));
    printf("record-align=%zu\n",
           (size_t)_Alignof(AbiRecord));
    printf("offset-tag=%zu\n", offsetof(AbiRecord, tag));
    printf("offset-count=%zu\n", offsetof(AbiRecord, count));
    printf("offset-bytes=%zu\n", offsetof(AbiRecord, bytes));

    return 0;
}
```

`sizeof(type)` and `_Alignof(type)` are C11 operators returning values in **bytes**; `offsetof(structType, member)` measures the byte offset from the start of the struct to the field. `<stddef.h>` provides `size_t`/`offsetof`, `<stdbool.h>` gives the `bool` alias in C11, and `<wchar.h>` provides `wchar_t`.

The `PRINT_TYPE` macro simply shortens table printing; every invocation passes a valid **C type**, including `long long` and `void *`. Do not use an `unsigned long` label to claim there is a separate canonical key: unsigned and signed types may share the same layout while differing in value-range interpretation.

### 6.2. Compile and compare on Linux

Requires **JDK 22+** (`javac` and `java` from the same JDK) along with GCC or Clang supporting C11.

```bash
javac AbiLayoutsDemo.java
cc -std=c11 -Wall -Wextra -Wpedantic \
   abi_probe.c -o abi_probe

java AbiLayoutsDemo
./abi_probe
```

On **common Linux/x86-64 with GCC/Clang under the System V LP64 ABI**, both programs are expected to print **the exact same stdout** as below. This is illustrative output for the specified environment, **not a constant across all platforms**:

```text
C type     size align
bool          1     1
char          1     1
short         2     2
int           4     4
long          8     8
long long     8     8
float         4     4
double        8     8
size_t        8     8
wchar_t       4     4
void*         8     8
record-size=24
record-align=8
offset-tag=0
offset-count=8
offset-bytes=16
```

Key takeaways from the output:

- `long` has size 8, `size_t` has size 8, pointer has size 8 → they **have the same size** but remain different C types in signedness/semantics.
- `wchar_t` is 4 bytes in this environment; do not apply the number 4 to Windows.
- `record-size=24` because of padding after `char tag`, and `offset-count=8` due to the alignment of `long`.
- Java and C results must match in **size, alignment, and field offsets** when truly using the same ABI. If they do not match, do not ignore it and use the descriptor anyway; investigate compiler flags, architecture, and the target library itself.

In Bash, you can compare byte-for-byte without creating intermediate files:

```bash
diff -u <(java AbiLayoutsDemo) <(./abi_probe)
```

If both results are identical, `diff` prints nothing and returns exit code 0. On another ABI, **both outputs may differ from the Linux example** while still matching each other; compare Java with C on the actual target environment, not against a fixed table.

### 6.3. How should discrepancies be handled?

Suppose Java prints `long=8` while the C probe prints `long=4`. That indicates at least one assumption is wrong: perhaps Java is running 64-bit Linux LP64 while C was compiled for a 32-bit ABI, or you compiled C for a different target. Do not try to "force" Java to use `JAVA_LONG` just because the name is `long`.

Check the following:

1. `java -version`, `javac -version`, and the actual JVM architecture.
2. `cc -v` or the target triple; compiler/linker flags such as `-m32`, `-m64`, and ABI variants.
3. Whether the C header used by the library has typedefs, alignment attributes, `#pragma pack`, or macros that alter structs.
4. Which x86-64/ARM64/x86-32 build the loaded binary library actually is, and whether cross-compilation or compatibility mode is involved.
5. Whether the Java FFM linker was created in **the same JVM running the application** or queried from a different JVM.

Only after confirming the same ABI and the same header/compiler version should you use the results as the basis for production FFM descriptors.

## 7. From canonical layout to an accurate `FunctionDescriptor`

Suppose the C header declares:

```c
size_t strlen(const char *s);
```

The input is a pointer to a NUL-terminated C string; the return is **C `size_t`**, not a fixed "Java long" by definition.

One way to write it for the current ABI:

```java
Linker linker = Linker.nativeLinker();
Map<String, MemoryLayout> abi = linker.canonicalLayouts();

MemoryLayout cSizeT = abi.get("size_t");
MemoryLayout cPointer = abi.get("void*");

FunctionDescriptor fd = FunctionDescriptor.of(
    cSizeT, cPointer);
```

This is a **Java snippet inside a method**; it requires importing `java.lang.foreign.*` and `java.util.Map`. `FunctionDescriptor.of(returnLayout, argumentLayouts...)` uses the canonical layouts of the C return type and pointer parameter. `FunctionDescriptor.ofVoid(...)` is used when the native function returns C `void`.

For a pointer that is actually `const char*`, the layout can still use the address layout of `void*` for ABI calling purposes, but **constness, string length, encoding, NUL termination, and ownership do not come from the layout**. You must pass a valid `MemorySegment` and not mutate data through the pointer just because the Java API allows writing.

### 7.1. Do not turn `size_t` into `JAVA_LONG` on every platform

On common 64-bit systems, `size_t` is usually 8 bytes with Java carrier `long.class`. On 32-bit systems, `size_t` can be 4 bytes with carrier `int.class`. The downcall `MethodHandle` will have a type matching the descriptor.

Pseudocode illustrating the idea:

```java
MemoryLayout layout = abi.get("size_t");
if (layout instanceof ValueLayout value) {
    Class<?> carrier = value.carrier();
    // If carrier == long.class -> invokeExact returns long.
    // If carrier == int.class  -> invokeExact returns int.
}
```

The actual code in Section 8 branches based on the carrier rather than calling `invokeExact` with the wrong return type. `MethodHandle.invokeExact` requires the static Java method type to **match exactly**; a branch casting to `long` when the handle returns `int` can throw `WrongMethodTypeException`. With native link errors at the C level, a wrong descriptor is even more severe than a normal Java type check error.

### 7.2. Describing structs with canonical fields

If C accepts:

```c
void consume_record(const struct AbiRecord *r);
```

You need to describe the pointer with an `AddressLayout` (usually from `"void*"`) and the `AbiRecord` data with a `StructLayout` whose field offsets have been verified. You can use `AddressLayout.withTargetLayout(recordLayout)` when you want to attach target region information to support pointer operations via the FFM API.

However:

- `withTargetLayout` **does not verify** that the C pointer actually points to a region of that size/type.
- A pointer read from native memory must have a valid lifetime; if C has already freed the target region, a correct Java layout will not save a dangling pointer.
- For C functions **passing a struct by value**, the ABI may have special rules for registers/stack. You cannot simply substitute a `struct` for a pointer or vice versa.
- FFM requires downcall layouts to be in the linker's **supported** set; a `structLayout` with wrong padding or unusual alignment can be rejected.

## 8. A real downcall example: `strlen` with the ABI's C `size_t`

This section **makes an actual native call**, so it differs from the layout-inspection-only program in Section 5. It is intended for **Linux/x86-64 with `strlen` in the default symbol lookup**, JDK 22+, and native access granted.

### 8.1. File `CanonicalStrlenDemo.java`

```java
import java.lang.foreign.AddressLayout;
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.util.Map;

public final class CanonicalStrlenDemo {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        Map<String, MemoryLayout> abi = linker.canonicalLayouts();

        MemoryLayout returnLayout = abi.get("size_t");
        MemoryLayout pointerLayout = abi.get("void*");

        if (!(returnLayout instanceof ValueLayout sizeT)
                || !(pointerLayout instanceof AddressLayout)) {
            throw new IllegalStateException(
                "Unexpected canonical layouts");
        }

        MemorySegment symbol =
            linker.defaultLookup().find("strlen").orElseThrow();

        FunctionDescriptor signature =
            FunctionDescriptor.of(sizeT, pointerLayout);

        MethodHandle strlen =
            linker.downcallHandle(symbol, signature);

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment text = arena.allocateFrom("Hello");

            if (sizeT.carrier() == long.class) {
                long n = (long) strlen.invokeExact(text);
                System.out.println("strlen(Hello)="
                                   + Long.toUnsignedString(n));
            } else if (sizeT.carrier() == int.class) {
                int n = (int) strlen.invokeExact(text);
                System.out.println("strlen(Hello)="
                                   + Integer.toUnsignedLong(n));
            } else {
                throw new IllegalStateException(
                    "Unsupported size_t carrier: "
                        + sizeT.carrier());
            }
        }
    }
}
```

This is a **complete Java file** using `Linker` and a native library symbol. It requires `strlen` to be present in the default native lookup; this is common on Linux with a suitable libc, but not **guaranteed** on every OS/JVM. If the default lookup cannot find the symbol, the code throws an exception instead of calling a guessed address.

`arena.allocateFrom("Hello")` creates a UTF-8 encoded, NUL-terminated C string whose bytes remain alive until the arena closes. The `strlen` value is **the number of bytes before NUL**, which for ASCII `"Hello"` is 5. If the string contains multi-byte non-ASCII Unicode characters, the byte count can differ from Java `String.length()`.

`Long.toUnsignedString` and `Integer.toUnsignedLong` here do not change the ABI; they simply **interpret the unsigned C number** appropriately when the Java carrier is signed.

### 8.2. Run commands

```bash
javac CanonicalStrlenDemo.java
java --enable-native-access=ALL-UNNAMED CanonicalStrlenDemo
```

With a suitable Linux runtime and successful symbol lookup, the **exact stdout** is:

```text
strlen(Hello)=5
```

`--enable-native-access=ALL-UNNAMED` grants native access to code on the classpath/unnamed module when using FFM restricted methods like `downcallHandle`. In applications with named JPMS modules, permission must be granted to that module per JDK rules. Reading `canonicalLayouts()` and `byteSize()` alone as in Section 5 **does not call native functions** and usually does not require this flag.

**Important note:** FFM cannot check whether the address of `strlen` actually has the function prototype you declared in `FunctionDescriptor`. If you fetch the wrong symbol or pass the wrong descriptor, the result can be undefined or crash the JVM. Do not grab a C function name from the internet and guess the ABI/descriptor for an unverified internal binary.

## 9. Comparing with C structs and understanding real padding

Let us return to the example:

```c
typedef struct AbiRecord {
    char tag;
    long count;
    size_t bytes;
} AbiRecord;
```

On Linux/x64 LP64, the typical layout is:

```text
Byte offset:    0        1..7         8..15         16..23
                +---------+-----------+-------------+
AbiRecord:      | tag (1) | padding 7 | count (8)   |
                +---------+-----------+-------------+
                | bytes (8)                          |
                +------------------------------------+
sizeof(AbiRecord) = 24, alignof(AbiRecord) = 8
offsetof(tag) = 0; offsetof(count) = 8; offsetof(bytes) = 16
```

The diagram depicts **byte offsets**; this is not the bit order of individual fields. When C `long` shrinks to 4 bytes on Windows/x64 LLP64, the offsets will differ. The same header can produce different struct binaries if the ABI differs.

If you construct:

```java
MemoryLayout wrong = MemoryLayout.structLayout(
    abi.get("char").withName("tag"),
    abi.get("long").withName("count"),
    abi.get("size_t").withName("bytes"));
```

then `MemoryLayout.structLayout` does not insert padding automatically; when the `long` field requires alignment greater than offset 1, the layout may be rejected for a misaligned field. Do not fix it by arbitrarily forcing `long.withByteAlignment(1)` if the C struct is not actually packed; doing so can mask bugs and produce a layout outside the linker's supported set.

Distinguish **trailing padding**: a struct whose last field is smaller than the largest alignment usually has trailing padding so that elements in a C array of structs are always aligned. Computing only the last field's position is not enough; you must compare `sizeof(CStruct)` with `layout.byteSize()`.

### 9.1. Cases where canonicalLayouts alone is not enough to build a struct

The specification only guarantees canonical **scalar/pointer** layouts; it does not automatically generate everything for:

- `struct`, `union`, C arrays, and deeply nested aggregates.
- Bit-fields, anonymous aggregates, flexible array members.
- `#pragma pack`, `__attribute__((packed))`, compiler-specific alignas/align attributes.
- Platform typedefs like `DWORD`, `HANDLE`, `off_t`, `ssize_t`, `time_t` when there is no corresponding standard key.
- Calling conventions for varargs, return-by-value, function pointer callbacks.
- Compiler/OS/toolchain-specific ABIs that do not match the JVM native linker.

For those cases, verify with C `sizeof/_Alignof/offsetof`, read the header and ABI specification, and build `MemoryLayout`/`FunctionDescriptor` according to the real contract. You can use a small C shim to expose verification values or wrap complex aggregates into a stable C API with pointer/size parameters, rather than passing structs by value through FFM if uncertain.

## 10. Varargs and default argument promotions

An easily misunderstood example is C:

```c
int printf(const char *format, ...);
```

The C compiler performs **default argument promotions** for variadic arguments: `float` is typically promoted to `double`; small integer types like `char` and `short` are promoted to `int` or `unsigned int` depending on value range.

The FFM linker does not perform those promotions for you. With `Linker.Option.firstVariadicArg(index)`, you must declare the argument layouts of the **specialized signature**, corresponding to the types actually passed according to the ABI.

Illustrative code on Linux/x64 (not a complete Java file):

```java
Linker linker = Linker.nativeLinker();
Map<String, MemoryLayout> abi = linker.canonicalLayouts();

FunctionDescriptor formatAndTwoInts = FunctionDescriptor.of(
    abi.get("int"),
    abi.get("void*"),
    abi.get("int"),
    abi.get("int"));

Linker.Option firstVariadic =
    Linker.Option.firstVariadicArg(1);
```

The two variadic integers are described as C `int`. If you want to pass a C `float` as a variadic argument, you must describe the promoted form (usually C `double`) according to C and ABI rules. This is a **descriptor** example; it does not execute a downcall and does not pass a specific format string. Do not use `printf` with an uncontrolled user-supplied format: format string vulnerabilities exist independently of FFM.

Do not conclude from `canonicalLayouts().get("char")` that using the C `char` layout for a variadic argument holding a `char` value is valid. The C ABI sees the **promoted type** of the argument at the call site.

## 11. Common mistakes when using canonicalLayouts

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Hard-coding `JAVA_LONG` for C `long` | Wrong on LLP64 or other ABIs | Use `canonicalLayouts().get("long")` |
| Hard-coding `JAVA_LONG` for `size_t` | Wrong with 32-bit `size_t` | Fetch key `"size_t"` and check carrier |
| Calling `get("void *")` (with space) | May return `null` | Use standard key `"void*"` |
| Assuming key `"unsigned long"` always exists | Key is not guaranteed | Use signed counterpart layout + unsigned handling |
| Seeing an 8-byte C pointer and using `JAVA_LONG` | Wrong carrier/calling semantics | `AddressLayout`, carrier `MemorySegment` |
| Treating C `char` as Java `char` | Wrong width/encoding | C `char` usually maps to byte; query linker |
| Assuming C `wchar_t` is always 2 bytes | Wrong on Linux/x64 (usually 4 bytes) | Query canonical layout and encoding contract |
| Treating `byteSize` as bit count | Severely wrong struct offsets and ABI | All size/alignment APIs here are in bytes |
| Using `structLayout` without padding | Wrong alignment/offsets or rejected | Insert appropriate padding and trailing padding |
| Comparing only struct size, ignoring offsets | Two layouts can match in size with wrong field order | Compare `offsetof` for every field as well |
| Using Java signed `int/long` as C unsigned without handling | Large values treated as negative | Use unsigned conversions and bounds checks |
| Using JVM's standard layout for a library cross-compiled for another ABI | FFM calls wrong ABI | Match JVM/toolchain/library ABI or use process boundary |
| Changing alignment arbitrarily to "make it run" | Can create packed layout not matching C | Follow C header/ABI; measure with C probe |
| Passing a pointer with too short a lifetime | Dangling pointer, crash | Clear ownership, Arena scope, and native lifetime |
| Assuming `Map` has every typedef/platform type | Null lookup or wrong inference | Rely only on 11 guaranteed keys; check extras |
| Calling `invokeExact` expecting `long` when handle returns `int` | `WrongMethodTypeException` | Branch on `ValueLayout.carrier()` |
| Using right canonical layout with wrong C prototype | Undefined behavior/native crash | Verify against actual header, arity, and return |
| Not checking variadic promotions | Calling wrong calling convention | Specialize descriptor to promoted types |
| Assuming `strlen` is always in default lookup | Not portable across all OS/VMs | Check symbol, use appropriate lookup/library |
| Changing compiler packing without re-checking | Struct offsets change while Java layout stays old | Run ABI probe in CI with production toolchain |

## 12. Workflow for applying in real projects

A safe workflow for Java ↔ C in a system with multiple CPU architectures:

**Step 1 — Record the contract from the C header.** Read the exact declarations, typedefs, struct definitions, calling convention, ownership contract, and compiler/architecture target. Do not build descriptors by guessing names.

**Step 2 — Query the runtime linker.** Get `Linker.nativeLinker().canonicalLayouts()` and select the standard key for each C scalar/pointer type. Use `byteSize()`, `byteAlignment()`, and `carrier()` to build descriptors dynamically or select the right platform branch.

**Step 3 — Verify real C.** Compile a C ABI probe with the same compiler flags and headers used for the native library, printing `sizeof`, `_Alignof`, and `offsetof`. Compare Java measurements with C measurements, especially for `long`, `size_t`, `wchar_t`, pointers, and structs.

**Step 4 — Build aggregate layouts.** Insert explicit padding, name fields, and compare offsets and total size. If the compiler uses packing or a different ABI, write a dedicated contract instead of arbitrarily lowering alignment.

**Step 5 — Build `FunctionDescriptor`.** Choose the right return layout, argument layouts, static MethodHandle type, vararg specialization, and pointer target if needed. Do not treat C unsigned semantics as Java signed semantics without conversions.

**Step 6 — Manage memory and safety.** Allocate `MemorySegment` via `Arena` or a valid source; keep segments alive long enough, handle out-of-bounds, and avoid dangling pointers and memory corruption. Do not treat canonical layouts as a native memory ownership verifier.

**Step 7 — Test per ABI.** Run both the probe and downcall smoke tests on Linux/x64, Windows/x64, ARM64, or whichever targets are actually supported. Save target artifacts/diagnostics, not just CI running on one developer's machine.

### 12.1. Test checklist to include in CI

1. All 11 canonical keys exist on the current native linker.
2. Size/alignment of each key matches the C probe on the same target.
3. `long` and `size_t` are tested separately, without assuming they always have the same size.
4. Pointer layout has Java carrier `MemorySegment`, not `long`.
5. Struct offsets `tag/count/bytes` and total size/alignment match C `offsetof/sizeof`.
6. For 32-bit unsigned, bit pattern 0xFFFFFFFF is correctly interpreted by Java as 4294967295 when the application needs a positive number.
7. For 64-bit unsigned, display/comparison uses unsigned APIs when the high bit is set.
8. Downcall `strlen("Hello")` returns 5 on the native lookup of a supported target.
9. Calling with the wrong method type is caught by tests before production (do not deliberately call the wrong native prototype to "see how it crashes").
10. C structs with packing/bit-fields are not silently handled with layouts meant for normal structs.
11. On other operating systems, symbol lookup and compiler build rules are separated instead of hard-coding Linux commands.
12. Errors such as missing symbol, unsupported layout, invalid pointer, and resource lifetime return clear statuses instead of being turned into valid data.

## 13. Questions to answer before shipping

- Which **ABI** is the C library binary using, and which compiler/flags built it?
- How many bytes and what alignment do C `long`, `size_t`, `wchar_t`, and `void*` have on the real target?
- Are you hard-coding `JAVA_INT/JAVA_LONG` due to matching names instead of using canonical C layouts?
- Are you using the exact spaceless map keys, such as `"void*"` and `"long long"`?
- If `Map.get` returns `null` for an extension type, does the system report a clear error or fall back dangerously?
- Are you checking `ValueLayout.carrier()` before calling `MethodHandle.invokeExact`?
- For unsigned values, does business logic handle bit patterns and value ranges properly?
- For C structs, have offsets, tail padding, and alignment been compared against C `offsetof`?
- Are there differences across Windows LLP64, Linux LP64, or 32-bit targets that need testing?
- Does pointer data have clear ownership, bounds, writable/read-only state, and arena lifetime?
- Does the downcall descriptor match the **exact C prototype**, argument count, varargs promotions, and calling convention?
- Can the ABI probe run as part of CI on each supported architecture/OS?

**Conclusion:** `Linker.nativeLinker().canonicalLayouts()` is the authoritative source for knowing how the JVM native linker maps basic C types to `MemoryLayout` for the running ABI. Use it to avoid wrong assumptions about `long`, `size_t`, `wchar_t`, and pointers; then **verify in practice with C `sizeof/_Alignof/offsetof`** before describing structs or calling functions. Canonical layouts help build an accurate binary contract, but they **do not verify the C header, do not replace ownership/lifetime management, and do not eliminate crash risks if a downcall is declared incorrectly**.

### References

- [Oracle Java SE 22 — Linker: canonicalLayouts, native ABI, supported layouts](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html)
- [Oracle Java SE 22 — MemoryLayout, byteSize, byteAlignment, structLayout, paddingLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html)
- [Oracle Java SE 22 — ValueLayout and Java carrier](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [Oracle Java SE 22 — FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html)
- [Oracle Java SE 22 — Arena, native memory lifetime](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454)
