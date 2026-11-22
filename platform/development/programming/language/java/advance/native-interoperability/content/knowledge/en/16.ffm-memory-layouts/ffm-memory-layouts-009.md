# Verifying sizeof, alignof, and offsetof with an Accompanying C Program

## 1. Goal: Use the Actual ABI as the Standard, Do Not Guess Layout from Java

When Java calls a C library through the **Foreign Function & Memory API (FFM)** or JNI, a C data structure is typically described again as a Java **`MemoryLayout`**. Being off by even one padding byte, an alignment requirement, or a field offset can cause Java to read incorrect data, the native function to receive wrong arguments, or more seriously, invalid memory access.

Three C checks to use:

- **`sizeof(T)`**: the number of bytes of memory required for an object of type `T`, **including padding** inside and at the end of the structure.
- **`_Alignof(T)`**: the alignment requirement of type `T` according to C11, in bytes. The `alignof(T)` macro from `<stdalign.h>` is also supported in C11; in C23, `alignof` is a keyword.
- **`offsetof(T, field)`**: the starting position of the `field` member, in bytes from the beginning of an object of type `T`; standard macro in `<stddef.h>`.

These three checks measure **the exact layout rules that the C compiler is applying**. Compare them with the three corresponding FFM operations in Java 22+:

| C11 | Java FFM (JDK 22+) | Meaning |
| --- | --- | --- |
| `sizeof(Packet)` | `PACKET.byteSize()` | Size of the entire struct |
| `_Alignof(Packet)` | `PACKET.byteAlignment()` | Alignment requirement of the struct |
| `offsetof(Packet, count)` | `PACKET.byteOffset(PathElement.groupElement("count"))` | Position of the `count` field |
| `sizeof(Packet[2]) / 2` | `MemoryLayout.sequenceLayout(2, PACKET).byteSize() / 2` | Stride between two elements in an array |
| `offsetof(Envelope, packet.count)` | `ENVELOPE.byteOffset(groupElement("packet"), groupElement("count"))` | Position of a nested field |

**Principle:** `MemoryLayout.structLayout(...)` **does not automatically insert padding** according to the C compiler. Java must explicitly describe padding bytes, or use a layout generation approach proven to match the actual header/ABI. Do not take a "reasonable-looking" `MemoryLayout.byteSize()` as proof that the layout matches C.

By the end of this lesson, you will have **a standalone C11 program** (`abi_probe.c`), **a standalone Java 22+ program** (`LayoutVerify22.java`), a way to compare results using `diff`, and a workflow to apply to real structs in native libraries.

## 2. Version Context and Testing Environment

The example is designed for:

- **C11** with GCC/Clang on **Linux x86-64**, the common ABI of this platform; `cc`/`gcc` is the compiler used in the example.
- **JDK 22 and later**, using the finalized FFM API in `java.lang.foreign` (JEP 454). Do not use `jdk.incubator.foreign` or `--enable-preview`.
- Java and the C program run on **the same operating system, architecture, and ABI**. Matching output from a Linux/x86-64 C compiler against a Windows/x64 JVM does not validly confirm the same layout.
- The C compiler uses natural alignment rules, **without** enabling `#pragma pack`, `__attribute__((packed))`, `-fpack-struct`, or custom ABI options.

The example uses `uint8_t`, `uint32_t`, and `double`. On typical Linux/x86-64:

| C type | Size (bytes) | C11 alignment (bytes) | Corresponding FFM layout in the example |
| --- | ---: | ---: | --- |
| `uint8_t` | 1 | 1 | `ValueLayout.JAVA_BYTE` |
| `uint32_t` | 4 | 4 | `ValueLayout.JAVA_INT` |
| `double` | 8 | 8 | `ValueLayout.JAVA_DOUBLE` |

**Important limitation:** `uint32_t` is an **unsigned** integer, whereas Java `int` is signed. The two types may share the same **size, alignment, and 32-bit representation** on the ABI being tested, but they do not have the same value semantics. When reading values greater than `Integer.MAX_VALUE`, use `Integer.toUnsignedLong(...)` or an intentional unsigned representation. And `double` must be checked against the ABI and floating-point representation, not just guessed from the type name.

On other platforms, `_Alignof(double)`, the sizeof/alignment of pointers, `long`, or layout conventions may differ. **The example output in this lesson is the expected result on Linux/x86-64**, not a guarantee that the C standard mandates the same across all machines.

## 3. Sample Struct to Clearly Observe Padding

C definition:

~~~c
#include <stdint.h>

typedef struct Packet {
    uint8_t  kind;
    uint32_t count;
    double   factor;
    uint8_t  enabled;
} Packet;
~~~

The member declaration order must be preserved when describing FFM. With typical Linux/x86-64 alignment, the bytes are arranged as follows:

~~~text
Byte offset
0          1      4             8                    16 17          24
| kind: 1  | pad:3 | count: 4    | factor: 8          |enabled| pad: 7 |
+----------+-------+-------------+--------------------+-------+--------+
^                                ^                                      ^
struct start (offset 0)      factor starts (8)                    next Packet
                                                                     starts (24)

sizeof(Packet)      = 24
_Alignof(Packet)    = 8
offsetof(kind)      = 0
offsetof(count)     = 4
offsetof(factor)    = 8
offsetof(enabled)   = 16
~~~

The C compiler needs to insert **three bytes before `count`**: `kind` takes one byte, but `uint32_t` must start at an offset divisible by 4. The `factor` field starts at offset 8, so it already achieves alignment 8 and needs no extra padding before the field. The `enabled` field starts at offset 16. After that, there are **seven bytes of tail padding** so that the struct size is a multiple of alignment 8.

This is why `sizeof(Packet)` is not the sum `1 + 4 + 8 + 1 = 14`; the expected actual size is **24**.

### Why does tail padding matter?

C array:

~~~c
Packet items[2];
~~~

Two elements lie contiguously with stride `sizeof(Packet)`. If the second element started at offset 14, `factor` in the second element might no longer have alignment 8. The C compiler adds tail padding so that **each subsequent element** starts at a valid offset.

With the example C layout:

~~~text
items[0]: offsets  0..23
items[1]: offsets 24..47
total sizeof(items) = 48
stride = sizeof(Packet) = 24
~~~

When using FFM `MemoryLayout.sequenceLayout(n, PACKET)`, **`PACKET.byteSize()` must also include tail padding**. Only matching the offsets of fields within *one* instance while omitting tail padding will cause the second element to be accessed incorrectly.

## 4. Complete C11 Program: `abi_probe.c`

Create the file **`abi_probe.c`** with the exact content below:

~~~c
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

typedef struct Packet {
    uint8_t  kind;
    uint32_t count;
    double   factor;
    uint8_t  enabled;
} Packet;

typedef struct Envelope {
    uint8_t prefix;
    Packet  packet;
} Envelope;

int main(void) {
    Packet sample = {0};

    printf("packet.size=%zu\n", sizeof(Packet));
    printf("packet.align=%zu\n", (size_t)_Alignof(Packet));

    printf("kind.offset=%zu\n",
           offsetof(Packet, kind));
    printf("count.offset=%zu\n",
           offsetof(Packet, count));
    printf("factor.offset=%zu\n",
           offsetof(Packet, factor));
    printf("enabled.offset=%zu\n",
           offsetof(Packet, enabled));

    printf("kind.size=%zu\n", sizeof sample.kind);
    printf("count.size=%zu\n", sizeof sample.count);
    printf("factor.size=%zu\n", sizeof sample.factor);
    printf("enabled.size=%zu\n", sizeof sample.enabled);

    printf("count.align=%zu\n", (size_t)_Alignof(uint32_t));
    printf("factor.align=%zu\n", (size_t)_Alignof(double));

    printf("array.stride=%zu\n", sizeof(Packet[2]) / 2);

    printf("envelope.size=%zu\n", sizeof(Envelope));
    printf("envelope.align=%zu\n", (size_t)_Alignof(Envelope));
    printf("envelope.packet.offset=%zu\n",
           offsetof(Envelope, packet));
    printf("envelope.packet.count.offset=%zu\n",
           offsetof(Envelope, packet.count));

    return 0;
}
~~~

### 4.1. Build and Run

~~~bash
cc -std=c11 -Wall -Wextra -Wpedantic \
  -o abi_probe abi_probe.c

./abi_probe
~~~

`-std=c11` enables the C11 standard so `_Alignof` has its standard definition. `-Wall -Wextra -Wpedantic` helps catch many issues when using GCC/Clang. Do not add a "packed" flag if the original header does not require packed.

**Expected output on typical Linux/x86-64:**

~~~text
packet.size=24
packet.align=8
kind.offset=0
count.offset=4
factor.offset=8
enabled.offset=16
kind.size=1
count.size=4
factor.size=8
enabled.size=1
count.align=4
factor.align=8
array.stride=24
envelope.size=32
envelope.align=8
envelope.packet.offset=8
envelope.packet.count.offset=12
~~~

The `Envelope` part shows that **nested structs** also have padding:

~~~c
typedef struct Envelope {
    uint8_t prefix;  /* offset 0 */
    Packet  packet;  /* offset 8 because Packet requires alignment 8 */
} Envelope;
~~~

In `Envelope`, `packet.count` starts at offset `8 + 4 = 12`. `offsetof(Envelope, packet.count)` allows verifying a nested member designator in this case; unlike misusing the `offsetof` macro for a bit-field.

### 4.2. Why use `%zu`?

The results of `sizeof`, `_Alignof`, and `offsetof` have type `size_t`, not `int` by default. The `%zu` format is the conversion specifier for `size_t` in C99+ and is appropriate for C11.

Avoid:

~~~c
/* Unsafe when size_t does not have the same representation as int. */
printf("%d\n", sizeof(Packet));
~~~

Using `%d` for a `size_t` is a variadic argument type mismatch, causing undefined behavior according to the `printf` contract. You should also not cast `size_t` to `int` when printing structures that could be very large.

### 4.3. `sizeof` does not walk through memory to count

In the normal case `sizeof(Packet)`, `sizeof sample.count` is an operation determined by the C compiler from the type and layout. It does not need to walk through each byte at runtime. For `sizeof` on **variable-length arrays (VLAs)**, some size expressions are evaluated at runtime; this lesson intentionally uses only complete struct types with compile-time-determined layouts.

`_Alignof(Packet)` also reports the **alignment requirement of the type**, not "the largest power of two dividing the address of a specific Packet variable". A variable might happen to sit at an address more strictly aligned than required; that does not change the ABI contract.

## 5. Java FFM: Accurately Describing a C Struct with `MemoryLayout`

With JDK 22+, we model `Packet` using `MemoryLayout.structLayout`. **Do not let the API guess padding:** Java FFM requires you to place `paddingLayout` segments in the exact positions.

~~~java
// Java 22+ excerpt; full class/imports are in section 6.
StructLayout PACKET = MemoryLayout.structLayout(
    ValueLayout.JAVA_BYTE.withName("kind"),
    MemoryLayout.paddingLayout(3),
    ValueLayout.JAVA_INT.withName("count"),
    ValueLayout.JAVA_DOUBLE.withName("factor"),
    ValueLayout.JAVA_BYTE.withName("enabled"),
    MemoryLayout.paddingLayout(7)
).withName("Packet");
~~~

Total bytes: `1 + 3 + 4 + 8 + 1 + 7 = 24`.

The natural alignment of the layout is **8**, because the `ValueLayout.JAVA_DOUBLE` field has alignment 8 on the stated platform. The `JAVA_BYTE`, `JAVA_INT`, and `JAVA_DOUBLE` layouts use sizes of 1, 4, and 8 bytes respectively. In this example, `StructLayout` has elements with padding inserted so that each field starts at the appropriate offset.

Java offsets:

~~~java
// Excerpt using the PACKET variable above.
long a = PACKET.byteOffset(PathElement.groupElement("kind"));    // 0
long b = PACKET.byteOffset(PathElement.groupElement("count"));   // 4
long c = PACKET.byteOffset(PathElement.groupElement("factor"));  // 8
long d = PACKET.byteOffset(PathElement.groupElement("enabled")); // 16
~~~

**Note:** The size of a `StructLayout` is the sum of the sizes of the member layouts you provide. `structLayout` **does not automatically add padding to align the next element**. Example missing padding:

~~~java
// Illustrating a JDK 22+ error; not a valid layout for Packet.
MemoryLayout wrong = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("kind"),
        ValueLayout.JAVA_INT.withName("count"));
~~~

Because `JAVA_INT` starts at offset 1, the layout may be rejected with `IllegalArgumentException` due to an alignment violation, instead of automatically inserting three bytes. If you change it to `JAVA_INT.withByteAlignment(1)` to "make the error go away", you may create a packed-style layout **that does not match the ABI of the original struct**. The proper fix is to insert padding matching the C output.

### 5.1. Using `PathElement.groupElement` to Select a Member

FFM provides:

~~~java
// Excerpt with PACKET and PathElement already available:
long offset = PACKET.byteOffset(
        PathElement.groupElement("factor"));

long fieldSize = PACKET.select(
        PathElement.groupElement("factor"))
        .byteSize();
~~~

`groupElement("factor")` only works if the child layout has `withName("factor")`. Names in Java are **metadata for querying the layout**; they do not automatically cause the C struct to have a corresponding field. Assigning the wrong name or order still produces code that compiles, but the offset can be wrong; compare against `offsetof` from C.

You can also create a `VarHandle` by path to read/write a field:

~~~java
// Illustrating the Java 22+ API, not yet a standalone program.
var handle = PACKET.varHandle(
        PathElement.groupElement("count"));

int count = (int) handle.get(segment, 0L);
handle.set(segment, 0L, 10);
~~~

With a `VarHandle` created from a layout path, `0L` is the **base offset coordinate**; the API will add the offset of `count`. Do not accidentally add the offset to the base **a second time**, or it will double-offset. The complete program below uses `segment.get/set` with the offset computed once to avoid this confusion.

## 6. Complete Java 22+ Program: `LayoutVerify22.java`

Create the file **`LayoutVerify22.java`**. The program has two modes:

- **No arguments:** prints the exact 17 lines with the same keys and the same order as `abi_probe.c` so `diff` can be run automatically.
- **`--memory`:** prints the 17 layout lines as above, then allocates native memory, writes/reads the fields to demonstrate that the offsets are used validly.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;

public final class LayoutVerify22 {
    private static final StructLayout PACKET =
            MemoryLayout.structLayout(
                    ValueLayout.JAVA_BYTE.withName("kind"),
                    MemoryLayout.paddingLayout(3),
                    ValueLayout.JAVA_INT.withName("count"),
                    ValueLayout.JAVA_DOUBLE.withName("factor"),
                    ValueLayout.JAVA_BYTE.withName("enabled"),
                    MemoryLayout.paddingLayout(7)
            ).withName("Packet");

    private static final StructLayout ENVELOPE =
            MemoryLayout.structLayout(
                    ValueLayout.JAVA_BYTE.withName("prefix"),
                    MemoryLayout.paddingLayout(7),
                    PACKET.withName("packet")
            ).withName("Envelope");

    private static long offset(String field) {
        return PACKET.byteOffset(
                PathElement.groupElement(field));
    }

    private static void out(String key, long number) {
        System.out.println(key + "=" + number);
    }

    private static void printLayout() {
        out("packet.size", PACKET.byteSize());
        out("packet.align", PACKET.byteAlignment());

        out("kind.offset", offset("kind"));
        out("count.offset", offset("count"));
        out("factor.offset", offset("factor"));
        out("enabled.offset", offset("enabled"));

        out("kind.size", ValueLayout.JAVA_BYTE.byteSize());
        out("count.size", ValueLayout.JAVA_INT.byteSize());
        out("factor.size", ValueLayout.JAVA_DOUBLE.byteSize());
        out("enabled.size", ValueLayout.JAVA_BYTE.byteSize());

        out("count.align", ValueLayout.JAVA_INT.byteAlignment());
        out("factor.align", ValueLayout.JAVA_DOUBLE.byteAlignment());

        out("array.stride",
                MemoryLayout.sequenceLayout(2, PACKET)
                        .byteSize() / 2);

        out("envelope.size", ENVELOPE.byteSize());
        out("envelope.align", ENVELOPE.byteAlignment());
        out("envelope.packet.offset",
                ENVELOPE.byteOffset(
                        PathElement.groupElement("packet")));
        out("envelope.packet.count.offset",
                ENVELOPE.byteOffset(
                        PathElement.groupElement("packet"),
                        PathElement.groupElement("count")));
    }

    private static void memoryExercise() {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment record = arena.allocate(PACKET);

            record.set(ValueLayout.JAVA_BYTE,
                    offset("kind"), (byte) 7);
            record.set(ValueLayout.JAVA_INT,
                    offset("count"), 9);
            record.set(ValueLayout.JAVA_DOUBLE,
                    offset("factor"), 1.5d);
            record.set(ValueLayout.JAVA_BYTE,
                    offset("enabled"), (byte) 1);

            System.out.println("memory.kind="
                    + Byte.toUnsignedInt(
                            record.get(ValueLayout.JAVA_BYTE,
                                    offset("kind"))));
            System.out.println("memory.count="
                    + Integer.toUnsignedLong(
                            record.get(ValueLayout.JAVA_INT,
                                    offset("count"))));
            System.out.println("memory.factor="
                    + record.get(ValueLayout.JAVA_DOUBLE,
                            offset("factor")));
            System.out.println("memory.enabled="
                    + Byte.toUnsignedInt(
                            record.get(ValueLayout.JAVA_BYTE,
                                    offset("enabled"))));
        }
    }

    public static void main(String[] args) {
        if (args.length > 1 ||
                (args.length == 1 && !args[0].equals("--memory"))) {
            throw new IllegalArgumentException(
                    "Usage: java LayoutVerify22 [--memory]");
        }

        printLayout();

        if (args.length == 1) {
            memoryExercise();
        }
    }
}
~~~

### 6.1. Compile and Run

~~~bash
javac LayoutVerify22.java
java LayoutVerify22
~~~

**Expected stdout on Linux/x86-64** — identical to the 17 lines from C:

~~~text
packet.size=24
packet.align=8
kind.offset=0
count.offset=4
factor.offset=8
enabled.offset=16
kind.size=1
count.size=4
factor.size=8
enabled.size=1
count.align=4
factor.align=8
array.stride=24
envelope.size=32
envelope.align=8
envelope.packet.offset=8
envelope.packet.count.offset=12
~~~

Also run the read/write mode:

~~~bash
java LayoutVerify22 --memory
~~~

After the 17 layout lines, the program will additionally print:

~~~text
memory.kind=7
memory.count=9
memory.factor=1.5
memory.enabled=1
~~~

Explanation:

- `arena.allocate(PACKET)` allocates native memory with the size and alignment of the layout within the scope of a confined arena.
- `record.set(ValueLayout.JAVA_INT, offset("count"), 9)` writes the number at offset 4 according to the Java model; `get` reads it back via the corresponding layout.
- `Byte.toUnsignedInt` helps print a `uint8_t`-like value as a number 0–255, instead of mistaking it for a signed Java `byte`.
- `Integer.toUnsignedLong` is used to interpret the bits of a Java `int` as an unsigned 32-bit value at the read value level.
- `try (Arena arena = Arena.ofConfined())` ensures the allocation is freed after the test; do not return the `MemorySegment` outside its lifetime.

**Note on scope of proof:** Writing and reading *with the exact same Java layout* and getting the right result is **not enough** to prove C compatibility. Java can write and read back successfully by itself even when the layout is completely different from C. The more important evidence is comparing **C's `sizeof`, `_Alignof`, `offsetof`** against **Java's `byteSize`, `byteAlignment`, `byteOffset`**. With real data, add two-way Java→C and C→Java tests to confirm value semantics also match.

## 7. Automated Verification with `diff` Instead of Eyeballing

Build both executables from the exact same checkout/source version and the same target environment. On Linux:

~~~bash
cc -std=c11 -Wall -Wextra -Wpedantic \
  -o abi_probe abi_probe.c

javac LayoutVerify22.java

./abi_probe > c.layout
java LayoutVerify22 > java.layout

diff -u c.layout java.layout
~~~

**Result when matching:** `diff -u` prints no lines and returns exit status `0`. In CI, a non-`0` status should fail the ABI validation step.

To see the status clearly:

~~~bash
diff -u c.layout java.layout
echo "diff_exit=$?"
~~~

Final stdout when the two files are identical:

~~~text
diff_exit=0
~~~

If the outputs differ, `diff` shows which line mismatched. For example, **an intentional hypothetical error**:

~~~diff
-packet.size=24
+packet.size=17
~~~

That can appear if the Java model omits tail padding or groups members in the wrong order. **Do not fix this by forcing the comparison to ignore that line**; trace from the actual C ABI to member offsets and the right `MemoryLayout.paddingLayout(...)`.

It is generally good practice to keep a measured output from C in CI artifacts for **each target ABI**, rather than only checking pre-printed expected numbers in documentation. When developing cross-platform, run the probe with the real compiler/linker on each platform; **do not copy Linux/x86-64 results as expected values for Windows/x64 or ARM**.

### 7.1. Why use two separate programs?

- The C probe is independent of the JVM and does not call `java.lang.foreign`; it checks the **compiler view** of `Packet` and `Envelope`.
- The Java verifier does not call a native library; it checks the **Java layout model intended to be passed to C**.
- Comparing the two outputs detects discrepancies before calling a real native function, avoiding crashes from wrong struct layouts.
- When needing to check the ABI on a specific machine, both can be built/run in the same CI job to avoid comparing across mismatched architectures.

### 7.2. Precision of the Comparison

The comparison only proves that **the measured quantities** match on that environment. It does not automatically prove:

- Signed/unsigned integers have compatible semantics for all values.
- Endianness/bitfield order/float representation match.
- Packing/options when building the **real library** are the same as the options when building the C probe.
- Native memory lifetime and thread confinement are correct.
- Pointers remain alive, in the right scope, with proper allocation/free ownership.
- Calling convention, `FunctionDescriptor`, and passing structs by value match the ABI.

To test more deeply, add a native function that takes/returns `Packet`, check values on both sides according to the library contract, and build with **the same headers/compiler flags** as the production library.

## 8. Mathematical Explanation of Padding

At a C field with alignment requirement `a`, the next offset typically must be rounded up to an appropriate multiple of `a`. In the natural struct model of the example, we can use:

\[
\operatorname{alignUp}(x,a)=\left\lceil \frac{x}{a}\right\rceil a
\]

Applying it:

| Field | Current offset | Alignment | Rounded offset | Size | Offset after field |
| --- | ---: | ---: | ---: | ---: | ---: |
| `kind` | 0 | 1 | 0 | 1 | 1 |
| `count` | 1 | 4 | 4 | 4 | 8 |
| `factor` | 8 | 8 | 8 | 8 | 16 |
| `enabled` | 16 | 1 | 16 | 1 | 17 |
| End of struct | 17 | struct alignment 8 | 24 | — | 24 |

From the table:

- **Internal padding** between `kind` and `count` = `4 − 1 = 3` bytes.
- No padding between `count` and `factor` = `8 − 8 = 0`.
- **Tail padding** after `enabled` = `24 − 17 = 7` bytes.
- Total member sizes = 14 bytes.
- Total padding = 3 + 7 = 10 bytes.
- Total `sizeof(Packet) = 14 + 10 = 24` bytes.

The calculation above reflects the **natural ABI model** of the example and should not be treated as a portable formula replacing the C compiler in all cases. Packed attributes, explicit alignment, ABI extensions, and compiler specifics can change the result. That is why the exercise starts with **a C probe measuring reality**, rather than starting with the assumption that the formula is always right.

### 8.1. FFM does not automatically "align-up" each field

Java FFM:

~~~java
// Error: JAVA_INT requires alignment 4 but is at offset 1.
MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE,
        ValueLayout.JAVA_INT);
~~~

Do not expect the `structLayout` factory to automatically add `paddingLayout(3)`. The JDK 22 specification explicitly states that padding must be inserted when needed; layouts that do not meet alignment requirements may be rejected.

Solution:

~~~java
// JDK 22+, illustration:
MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE,
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT);
~~~

**However**, the result is only `1+3+4=8` bytes long; for a real struct with more subsequent fields, you must also calculate subsequent padding gaps and the **tail padding** of the final struct. Do not just fix the first exception and stop verifying.

## 9. `sizeof`: Measuring Structs, Arrays, and Fields

### 9.1. `sizeof(T)` differs from the sum of member sizes

`Packet` example:

~~~c
/* Illustrative C11 snippet within the same file/translation unit. */
size_t full = sizeof(Packet);         /* expected 24 */
size_t part = sizeof(uint8_t)
            + sizeof(uint32_t)
            + sizeof(double)
            + sizeof(uint8_t);       /* expected 14 */
~~~

The difference between 24 and 14 is the internal/tail padding in the example ABI. `sizeof(Packet)` is the operation needed to allocate a buffer or calculate the stride for an **array of structs**.

### 9.2. `sizeof(array)` differs from `sizeof(pointer)`

~~~c
/* Illustrative C11 excerpt, not standalone. */
Packet samples[3];
Packet *pointer = samples;

size_t arrayBytes   = sizeof samples;    /* 3 * sizeof(Packet) */
size_t pointerBytes = sizeof pointer;    /* pointer size */
~~~

On Linux/x86-64, typically `arrayBytes=72` and `pointerBytes=8`, but the value of `sizeof(pointer)` does not determine the layout of `Packet`. An array passed to a function parameter like `Packet items[]` will **decay into a pointer**, so `sizeof(items)` inside the function is no longer the size of the whole array.

In Java FFM, `MemoryLayout.sequenceLayout(3, PACKET).byteSize()` logically corresponds to **3 elements**. `ValueLayout.ADDRESS.byteSize()` only relates to the carrier of **one pointer**, not the size of any structure behind the pointer.

### 9.3. `sizeof` on Nested Arrays

C:

~~~c
Packet matrix[2][3];
// sizeof(matrix) = 2 * 3 * sizeof(Packet) on the measured ABI.
~~~

FFM:

~~~java
// JDK 22+ excerpt, PACKET is already defined.
MemoryLayout matrix = MemoryLayout.sequenceLayout(
        2, MemoryLayout.sequenceLayout(3, PACKET));
~~~

Do not treat C `Packet[2][3]` as the layout of `Packet**`. This C array is a contiguous region with stride `sizeof(Packet)`; pointer-to-pointer is a completely different model.

## 10. `_Alignof`: Checking Alignment Requirements, Not Just byteSize

### 10.1. Equal `sizeof(T)` can still have different alignment

Two layouts with the same size of 8 do not by default have the same alignment:

~~~text
C struct A: sizeof(A) = 8, alignof(A) = 4
C struct B: sizeof(B) = 8, alignof(B) = 8
~~~

Both are "8 bytes long", yet their valid positions in memory, aggregate rules, and behavior when passed through the native ABI can differ. Comparing `byteSize()` while omitting `byteAlignment()` is incomplete.

FFM:

~~~java
// JDK 22+ illustrating the meaning of the two metadata values:
long bytes = layout.byteSize();
long requiredAlignment = layout.byteAlignment();
~~~

If a layout with non-default alignment is needed, `withByteAlignment(long)` can change the alignment metadata. However, **changing the alignment on a Java layout does not change the real C struct**. The C compiler/header is the source of truth. Simply forcing alignment to "make diff pass" without checking C can cause subtle bugs.

### 10.2. `_Alignof` with Different Types

C11:

~~~c
/* Illustrative only; measured values must come from the target compiler. */
_Alignof(char);
_Alignof(uint32_t);
_Alignof(double);
_Alignof(Packet);
~~~

Some compilers may print the same sizeof for two types while their alignments differ. `_Alignof(T)` is a property of **type T**; it should not be measured by taking the address of a variable, because the actual address may be placed at a more strictly aligned boundary than required.

In C23, `alignof` is a keyword; in C11, you can include `<stdalign.h>` and use the equivalent `alignof` macro. To be explicit about the C11 baseline and avoid macro dependencies, the accompanying program directly uses **`_Alignof`**.

## 11. `offsetof`: Reaching the Exact Member, Including Nested Structs

### 11.1. Member offset differs from arbitrary pointer arithmetic

C11:

~~~c
/* Excerpt checking field offsets from the real header. */
offsetof(Packet, kind);
offsetof(Packet, count);
offsetof(Packet, factor);
offsetof(Packet, enabled);
~~~

This is the standard macro designed for determining offsets. You should not write:

~~~c
/* WRONG/non-portable: attempting to take an address from a null pointer. */
size_t offset = (size_t)&(((Packet*)0)->count);
~~~

Although many compilers have extensions for some such expressions, dereferencing through a null pointer manually is not a portable solution. Use `offsetof`, which is implemented in a compiler-appropriate way.

### 11.2. Nested Field

C:

~~~c
offsetof(Envelope, packet);        /* expected 8  */
offsetof(Envelope, packet.count);  /* expected 12 */
~~~

Java:

~~~java
// JDK 22+, ENVELOPE is a nested StructLayout with a member named "packet".
long packetStart = ENVELOPE.byteOffset(
        PathElement.groupElement("packet"));

long nestedCount = ENVELOPE.byteOffset(
        PathElement.groupElement("packet"),
        PathElement.groupElement("count"));
~~~

Select the right **nested layout path**. For `ENVELOPE`, only calling `groupElement("count")` at the outer level will fail because `count` is a member of `Packet`, not a direct member of `Envelope`.

### 11.3. Do Not Use `offsetof` on Bit-Fields

C:

~~~c
/* Illustrative C11 example; DO NOT call offsetof(Flags, a). */
typedef struct Flags {
    unsigned int a : 3;
    unsigned int b : 5;
} Flags;
~~~

Bit-fields have **bit-level** placement and their own compiler/ABI rules; you cannot take the address of a bit-field with `&obj.a`, and `offsetof` does not apply. If a C API has bitfields, creating a correct Java layout requires understanding packing, bit order, storage units, and compiler conventions, and using masks/shifts or C getters rather than treating a bit-field as a separate byte-aligned `ValueLayout`.

## 12. ABI Variations: Why Not Measure on One Machine and Use Everywhere?

Three factors determine the C side:

1. **Real header/library:** field types, order, nested arrays, macros, `#pragma pack`, conditional typedefs.
2. **Compiler/ABI/build flags:** GCC/Clang/MSVC, x86-64/ARM64/32-bit architectures, packing, alignment, and calling convention.
3. **Build version:** the header may change depending on feature macros or the library version.

Examples of changes that can alter probe output:

- Changing `uint32_t` to C `long`: on Linux/x64 typically 8 bytes, on Windows/x64 typically 4 bytes.
- Replacing `uint8_t` with an enum: enum size and ABI rules may differ from assumptions.
- Adding `#pragma pack(push, 1)` around the struct: offset 4 may become 1; the overall struct alignment may decrease.
- Using `_Alignas(16)`/alignment attributes: struct size/align may increase.
- Using compiler flags that affect the ABI: the C probe and the library may no longer be compatible if built with different flags.
- Using `long double` or SIMD vectors: alignment and representation vary significantly by platform.
- Using conditional fields in the header: build version/parameters determine the actual layout.

That is why the workflow should **compile the probe with the exact C compiler, flags, and headers** that the production native binary uses. If the Java code runs on multiple OSes, you need **a set of expected C measurements per target ABI** or dynamic checking at build/package time.

### 12.1. Pointer Types and `size_t`

Do not assume `sizeof(void*) == sizeof(long)`. This is usually true on LP64 Linux/x86-64, but can be false on LLP64 Windows/x64.

Additional C probe:

~~~c
/* Add to main if the struct contains pointers or size_t. */
printf("pointer.size=%zu\n", sizeof(void*));
printf("pointer.align=%zu\n", (size_t)_Alignof(void*));
printf("size_t.size=%zu\n", sizeof(size_t));
printf("size_t.align=%zu\n", (size_t)_Alignof(size_t));
~~~

Java FFM JDK 22+ has `ValueLayout.ADDRESS` to represent a pointer-sized C address. For `size_t` or C `long`, check `Linker.nativeLinker().canonicalLayouts()` and the C ABI; do not hardcode `ValueLayout.JAVA_LONG` as a cross-platform truth. Some ABIs have multiple C typedef names representing different widths, so descriptors/layouts must be determined by the actual C type, not by a similar-looking Java name.

### 12.2. Endianness and Unsigned

Two layouts with the same `sizeof/alignof/offsetof` can still differ in **byte interpretation**. For example, Java `ValueLayout.JAVA_INT` uses the native byte order by default, whereas `withOrder(ByteOrder.BIG_ENDIAN)` can change how the layout interprets bytes when reading/writing.

If a C library accepts a network packet or file format with a fixed byte order, you need to check the **format specification** and apply the right layout order; you cannot conclude compatibility solely from `byteSize` equaling `sizeof`.

C `uint32_t` has values up to `2^32 − 1`; signed Java `int` only goes up to `2^31 − 1`. The layout matches, but value semantics may require handling with `Integer.toUnsignedLong`, masks, or an appropriate type.

## 13. Packed Structs: When Natural Alignment No Longer Holds

Consider C code using a compiler extension:

~~~c
/* GCC/Clang-specific illustration, not portable C11. */
typedef struct __attribute__((packed)) PackedPacket {
    uint8_t  kind;
    uint32_t count;
    double   factor;
    uint8_t  enabled;
} PackedPacket;
~~~

A typical GCC/Clang target may produce:

~~~text
sizeof(PackedPacket)      = 14
_Alignof(PackedPacket)    = 1
offsetof(count)           = 1
offsetof(factor)          = 5
offsetof(enabled)         = 13
~~~

This is an **extension-driven variant**, not the natural `Packet` in section 3. C code reading packed fields may have to handle unaligned access depending on architecture/compiler; on some CPUs, taking a raw pointer to an unaligned member and dereferencing it improperly can be dangerous.

Java may need `ValueLayout.JAVA_INT_UNALIGNED` or a layout with `withByteAlignment(1)`, plus padding/offsets matching the exact C output. **Do not** silently replace `JAVA_INT` with unaligned just to bypass `IllegalArgumentException` in a design that is not actually packed.

For MSVC, `#pragma pack`, or platform-specific definitions, you must probe on that exact compiler. If a C library wants a portable ABI, consider exposing getters/setters or serialization functions instead of exposing an unstable packed struct layout.

## 14. What Other Complex Layout Types Need Checking?

### 14.1. Union

A C union has members **overlapping from offset 0**; `sizeof(union)` and alignment depend on the largest member and ABI padding rules. In FFM, use `MemoryLayout.unionLayout(...)`, not `structLayout(...)`.

~~~c
/* C11 illustration: union, not in the main probe. */
typedef union Number {
    uint32_t integer;
    double   floating;
} Number;
~~~

~~~java
// Java 22+ illustrating the corresponding layout type under the assumed ABI.
MemoryLayout NUMBER = MemoryLayout.unionLayout(
        ValueLayout.JAVA_INT.withName("integer"),
        ValueLayout.JAVA_DOUBLE.withName("floating")
).withName("Number");
~~~

You must check `sizeof(Number)` and `_Alignof(Number)` with C. Do not assume a union's size is always equal to a single field's size while ignoring alignment.

### 14.2. Flexible Array Member

~~~c
/* C99+ illustration of a type with a trailing flexible array. */
typedef struct Message {
    uint32_t length;
    uint8_t  payload[];
} Message;
~~~

`sizeof(Message)` **does not include** the bytes of the dynamically sized array for the payload length. The offset of `payload` is obtained via `offsetof(Message, payload)`; the actual allocation size when holding N bytes must be calculated according to the contract and alignment requirements. With FFM, do not use `sequenceLayout(0,...)` or `sizeof(Message)` as a guarantee for the entire allocated payload region; you must calculate the exact total size and bounds.

### 14.3. Pointer Members and Ownership

~~~c
/* C11 illustration; a pointer is not an inline char array. */
typedef struct View {
    const char *data;
    size_t length;
} View;
~~~

FFM can model the `data` member with `ValueLayout.ADDRESS`, but reading `data` from the native struct returns **a pointer value**, which does not mean Java has the right to read `length` bytes arbitrarily. A contract is needed specifying who allocates the pointer, whether there is a NUL terminator, whether bounds are valid, when it is freed, and whether Java must create a restricted view or copy.

**Do not** turn a pointer into inlined data to "match the size" when comparing structs. And do not use `reinterpret` to guess the size of a pointer target if it has not been confirmed by the C API.

### 14.4. Nested Arrays

C:

~~~c
typedef struct Grid {
    uint8_t  tag;
    uint32_t cells[3];
} Grid;
~~~

FFM uses `MemoryLayout.sequenceLayout(3, ValueLayout.JAVA_INT)` at the aligned offset position, and padding must be inserted before the array if needed. `offsetof(Grid, cells)` gives the starting offset, `sizeof(((Grid*)0)->cells)` or `sizeof(uint32_t[3])` gives the inline array size; avoid mistaking it for `uint32_t*`.

For complex layouts, run a C probe **field by field** before creating the Java layout; do not try to interpret the entire struct with an unverified `ByteBuffer`.

## 15. C11 Compile-Time Assertions as an ABI Guardrail

The C probe provides runtime numbers, while `_Static_assert` rejects the build immediately if the layout does not match a published ABI. Example **specifically** for the natural Linux/x86-64 layout of this lesson:

~~~c
/* Illustration added to the C TU where Packet is defined.
   Enable only when the project intentionally locks this ABI. */
_Static_assert(sizeof(Packet) == 24, "Packet size changed");
_Static_assert(_Alignof(Packet) == 8, "Packet alignment changed");
_Static_assert(offsetof(Packet, count) == 4, "count offset changed");
_Static_assert(offsetof(Packet, factor) == 8, "factor offset changed");
_Static_assert(offsetof(Packet, enabled) == 16, "enabled offset changed");
~~~

Do not treat these numeric values as "portable C standard". If another target has a valid ABI but a different layout, the `_Static_assert` above will fail by design, and the project must update the contract for that target.

The equivalent in Java can be checked programmatically:

~~~java
// Java 22+, illustration in a scope that has PACKET and offset(...).
if (PACKET.byteSize() != 24 ||
        PACKET.byteAlignment() != 8 ||
        offset("count") != 4 ||
        offset("factor") != 8 ||
        offset("enabled") != 16) {
    throw new IllegalStateException("FFM Packet layout mismatch");
}
~~~

However, **comparing C and Java outputs on the build target** is stronger than merely hardcoding numbers not measured by the C compiler. Best practice: the C probe is the source of truth, the Java layout is the implementation, and CI compares both sides and tests memory values.

## 16. Common Mistakes When Performing This Verification

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Computing `sizeof` by summing field sizes | Omits internal/tail padding | Get real `sizeof(struct)` via C probe |
| Comparing only `sizeof`, ignoring align/offset | Fields may be misplaced even if total size matches | Compare both `_Alignof` and each `offsetof` |
| Assuming `structLayout` auto-adds padding | May be rejected for alignment or have wrong offsets | Insert `paddingLayout` explicitly |
| Inserting padding before fields but forgetting tail padding | `sequenceLayout`/array stride is wrong | Compare `sizeof(T[2]) / 2` with `layout.byteSize()` |
| Comparing C output on Linux with Java on Windows | Two different ABIs | Same target OS/architecture/toolchain |
| C probe includes a different header than the native library | ABI probe does not represent production binary | Use the same header, flags, and version |
| Forcing `withByteAlignment(1)` to "avoid exception" | Changes layout into a fake packed one | Measure C alignment and preserve the real ABI |
| Using `sizeof(pointer)` instead of `sizeof(array)` | Missing size for multiple elements | Probe the exact array type, compute stride |
| Using `%d` to print `size_t` | Format/argument type mismatch | Use `%zu` |
| Using `offsetof` on bit-fields | Invalid because bit-fields are not addressable | Switch to C accessors/masks per ABI |
| Reading `uint32_t` as signed Java int without conversion | Large values become negative | `Integer.toUnsignedLong` or unsigned contract |
| Only reading/writing Java with the same layout and claiming it matches C | Java offset errors can cancel themselves out | Compare with C probe output and run two-way tests |
| Using a raw pointer after closing the arena | Use-after-free/native crash | Maintain proper lifetime and ownership |
| Measuring on debug compiler while library is built packed | Different flags/ABI | Probe matching production toolchain |
| Writing into tail padding and relying on its contents | Padding carries no contract field meaning | Only read/write named fields, do not depend on padding bytes |
| Confusing `byteAlignment` with the width of `JAVA_INT` | Size 4 is not align 4 on every ABI | Measure C type `_Alignof` on the target |

## 17. Practical Workflow for a Native Library You Did Not Write

1. **Find the real struct** from the public C header used by the library binary. Check typedefs, `#ifdef`, packing macros, and version.
2. Create `abi_probe.c` including the **real header** instead of copying a hand-rewritten struct when checking production. Copying definitions can hide differences.
3. Run the probe with the compiler/flags/cross-compiler matching the target. If using cross-compilation where the binary cannot execute on the host, run on the target or via a reliable runner/emulator.
4. Record `sizeof`, `_Alignof`, `offsetof`, and the sizes of member types. If the struct contains nested arrays, unions, or pointers, measure the corresponding characteristics as well.
5. Build FFM `MemoryLayout.structLayout/unionLayout/sequenceLayout`, inserting `paddingLayout` according to the C ABI. Choose the right `ValueLayout`, order, alignment, and pointer layouts.
6. Run the Java program describing the layout and `diff` against the probe output. If there is a mismatch, fix **the Java layout or build target**, do not change the C output to imaginary numbers.
7. Test real native interoperability on an instance: C creates data → Java reads; Java writes → C reads. Check fields, signed/unsigned, floating point, pointer ownership, arrays, and lifetime.
8. Put verification into CI for the targets actually supported. When headers, compiler flags, or architecture change, the probe must be re-run instead of trusting an old snapshot.
9. When the API supports teardown/shutdown, do not let a C callback use a pointer from an arena after `arena.close()`.
10. Document the target ABI and verification limitations in the binding's documentation.

### Suggested CI Build Organization

~~~text
binding/
  native/
    include/
      mylibrary.h
    abi_probe.c       # include the real header
  java/
    LayoutVerify22.java
  scripts/
    verify-abi.sh    # build C + Java then diff output
~~~

This is an **illustrative structure**; projects are not required to have these exact directories. For the lesson's sample programs, only the two files `abi_probe.c` and `LayoutVerify22.java` are needed, with no shared C library or JNI library required.

## 18. Checklist Before Marking a C Layout as Verified

- [ ] C probe uses `sizeof`, `_Alignof`/`alignof`, and `offsetof` from standard headers properly.
- [ ] `%zu` is used for all `size_t` results.
- [ ] C program is built with the same C ABI/compiler flags as the native library to integrate.
- [ ] `Packet` has full **internal padding and tail padding**.
- [ ] Java `PACKET.byteSize()` equals `sizeof(Packet)`.
- [ ] Java `PACKET.byteAlignment()` equals `_Alignof(Packet)`.
- [ ] Every `byteOffset(groupElement(field))` equals `offsetof(Packet, field)`.
- [ ] `sequenceLayout` stride equals `sizeof(Packet)`.
- [ ] Nested offsets in `Envelope` also match.
- [ ] `byteSize/byteAlignment` metadata is not used to infer byte order/value semantics.
- [ ] Signed vs unsigned and float/pointer formats have been checked where needed.
- [ ] `offsetof` is not used for bitfields.
- [ ] When a struct is packed or has alignment extensions, the exact target compiler is probed and Java describes it accurately.
- [ ] Segments or native pointers do not outlive the arena lifetime.
- [ ] CI compares both outputs **automatically** and fails on mismatch.
- [ ] If headers/versions change, measurements are re-run rather than keeping old numbers.

## 19. Self-Check Questions

1. Why is the sum of the sizes of the four `Packet` members 14 bytes, while `sizeof(Packet)` is typically 24 bytes on Linux/x86-64?
2. What property does `_Alignof(Packet)` measure? Is it the same as taking the address of a Packet variable and counting trailing 0 bits?
3. What is `offsetof(Packet, count)` in the example and why?
4. The `enabled` field starts at offset 16 and ends at 17. Why does the struct have a total size of 24?
5. Does Java `MemoryLayout.structLayout` automatically add padding before `JAVA_INT`?
6. Is `MemoryLayout.paddingLayout(3)` measured in bits or bytes in JDK 22?
7. Why must you compare `byteAlignment()` and each `byteOffset(...)` instead of only `byteSize()`?
8. How do you measure the offset of `Envelope.packet.count` from C and Java?
9. If `diff` prints nothing and returns status 0, what does that prove? What does it not prove?
10. Do Java `int` and C `uint32_t` have the same semantics for all values?
11. Can the expected `packet.size=24` of Linux/x86-64 be applied to every platform?
12. Why might a packed C struct need Java unaligned layouts?
13. Is `offsetof` valid for a bit-field?
14. In Java's `--memory` mode, does writing and reading back the right values prove that the layout matches C?
15. Why is `sizeof(Packet[2]) / 2` a useful check?
16. Why should a production C probe program include the real header instead of copying the struct?
17. In FFM, what is the difference to avoid between a `VarHandle` created from a layout path and `MemorySegment.get` with an offset?
18. If a native function receives a pointer to a segment, can C be allowed to keep the pointer after the arena closes?

**Suggested answers:** (1) 3 bytes internal and 7 bytes tail padding; (2) alignment requirement of the C type, not a random address; (3) 4, because `uint32_t` must be aligned to a multiple of 4; (4) tail padding so sizeof is a multiple of align 8 and array stride is right; (5) no; (6) bytes; (7) the same size can still have wrong field layout and alignment; (8) `offsetof(Envelope, packet.count)` and a nested `byteOffset` path; (9) the measured quantities match on that target, not full ABI/endianness/ownership verification; (10) no; (11) no, it depends on the target ABI; (12) the compiler reduces alignment, so Java must reflect that accurately; (13) no; (14) not yet, because both operations use the same Java layout; (15) checks stride/tail padding; (16) avoids definition drift from the binary; (17) a `VarHandle` path adds the offset internally, so do not add it manually again; (18) no, it risks a dangling pointer/use-after-free.

## 20. Official References

- [Oracle Java SE 22 — `MemoryLayout`, `structLayout`, `paddingLayout`, `byteOffset`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html)
- [Oracle Java SE 22 — `StructLayout`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/StructLayout.html)
- [Oracle Java SE 22 — `ValueLayout`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [Oracle Java SE 22 — `MemorySegment`, `get/set` and `byteSize`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Oracle Java SE 22 — `Arena`, `allocate` and lifetime](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- [OpenJDK JEP 454 — Foreign Function & Memory API (Final), JDK 22](https://openjdk.org/jeps/454)
- [C reference — `sizeof`](https://en.cppreference.com/w/c/language/sizeof)
- [C reference — `_Alignof` / `alignof`](https://en.cppreference.com/w/c/language/alignof)
- [C reference — `offsetof`](https://en.cppreference.com/w/c/types/offsetof)
- [C reference — Objects, alignment and padding](https://en.cppreference.com/w/c/language/object)

**Conclusion:** A Java FFM struct layout is only trustworthy when **an actual C compiler confirms** the size, alignment, offsets, and stride of that layout. Use a C11 `sizeof` + `_Alignof` + `offsetof` program, explicitly describe padding in `MemoryLayout.structLayout`, run the Java verifier on the same target ABI, and compare outputs automatically. Do not guess field offsets by intuition, do not use `structLayout` as if it auto-pads, and do not conclude "safe interop" just because Java succeeds at writing/reading its own data.
