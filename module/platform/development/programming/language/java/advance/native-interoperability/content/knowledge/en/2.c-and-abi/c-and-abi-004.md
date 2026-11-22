# Calling Conventions, Parameter Passing, and Return Values in the C ABI

## 1. What does the ABI determine when calling a native function?

In C, the declaration `int add(int a, int b);` specifies the **source-level interface**: the function name, the number/order of parameters, and the return type. Once the program is compiled, the caller and the called function (callee) must also adhere to an **Application Binary Interface (ABI)** to interpret the exact same call identically.

An ABI typically specifies:

- Which **registers** or **stack locations** integer, floating-point, pointer, and structure parameters are placed in.
- How the stack is aligned, memory regions reserved for the callee, and which registers the caller/callee must preserve.
- Where the **return value** is received; when a `struct` is returned via registers or an implicit result pointer.
- Sizes/alignments of C types, `struct` layout, symbol names, and library linking rules.

A **calling convention** is the part of the ABI specifically concerned with call sequence, argument passing, stack/register usage, and returning results. An ABI is broader than a calling convention because it also includes data representation, symbols, object files, and linking rules.

Two programs using the same C syntax can still be **binary incompatible** if compiled for different ABIs. You must consider the specific **CPU architecture + operating system + ABI/toolchain** triad; there is no single calling rule that applies to every machine.

### 1.1. Conceptual steps of a call

1. The **Caller** evaluates arguments, performs type conversions according to the prototype, prepares registers/stack per the ABI, and issues the call instruction.
2. The **Callee** receives parameters according to that exact rule, saves/restores registers that must be preserved, and executes the function body.
3. The **Callee** places the result in the ABI-specified location (or writes to the result area allocated by the caller), and then returns.
4. The **Caller** reads the result, continues using the registers that remain valid, and cleans up the stack area it is responsible for.

This is a conceptual model: the compiler may optimize, inline, tail-call, or omit creating a conventional stack frame. Those optimizations do not change the **ABI contract** at an actual call boundary.

**Note:** the *order of evaluation of argument expressions* in C is not universally specified as left-to-right. Do not confuse the ABI's argument-passing positions with the evaluation order of expressions in C code.

## 2. Comparing common conventions

The rules below are **generalizations for ordinary scalar parameters**; `struct`, vectors, ABI variants, variadic functions, and special types require separate classification rules.

| Compilation target | Integer/pointer parameters | `float`/`double` parameters | Stack characteristics | Common scalar results |
| --- | --- | --- | --- | --- |
| **x86-64 System V** (most x86-64 Linux, Intel macOS) | Up to 6 registers: `RDI, RSI, RDX, RCX, R8, R9` | Up to 8 registers `XMM0–XMM7`, allocated separately from the integer group | Aligned per ABI; has a 128-byte *red zone* with specific usage conditions | Integer/pointer typically in `RAX`; floating-point in `XMM0` |
| **Windows x64** (default MSVC x64 ABI) | First 4 positions: `RCX, RDX, R8, R9` | `XMM0–XMM3` corresponding to **argument positions** 1–4 | Caller allocates at least 32 bytes of *shadow space*; no red zone like System V | Integer/pointer typically in `RAX`; floating-point in `XMM0` |
| **Base AArch64 AAPCS64** (64-bit ARM) | `x0–x7` | `v0–v7` | Stack 16-byte aligned at required boundaries | Integer typically in `x0`/`x1`; floating-point typically in `v0` |

Do not infer that Windows on ARM64, Apple arm64, or specialized platforms have every detail identical to base AAPCS64. Aggregate classification rules, variadics, and platform exceptions must be checked in the ABI documentation for the exact target.

### 2.1. Example: same prototype, different passing conventions

~~~c
int score(int count, double ratio, int bonus);
~~~

Assume the call is compiled under the default ABI and all arguments are scalars:

- **System V AMD64:** `count → EDI`, `ratio → XMM0`, `bonus → ESI`. The integer and floating-point register groups are allocated relatively independently.
- **Windows x64:** `count → ECX`, `ratio → XMM1`, `bonus → R8D`. `ratio` occupies the **second argument position**, so it uses `XMM1` instead of `XMM0`.
- **Base AAPCS64:** `count → w0`, `ratio → d0`, `bonus → w1`.

The `int` return value is typically in `EAX` (x86-64) or `w0` (AArch64). This is an example illustrating register positions, not assembly code to be written manually.

### 2.2. Caller-saved, callee-saved, and the stack

- **Caller-saved/volatile:** the caller must not assume the value remains intact after the call; if needed, it must save it itself.
- **Callee-saved/nonvolatile:** if the callee uses/modifies a register in this group, it must restore the value before returning.
- **Stack alignment:** the ABI imposes stack alignment constraints at call/function-entry points; hand-written assembly with wrong alignment can fail with SIMD instructions or compiler-generated code.
- **Stack arguments:** when there are not enough registers, parameters may be passed on the stack. The exact location also depends on type classification and the ABI, not just the argument count.
- **Windows x64 shadow space:** 32 bytes prepared by the caller even when the function does not use all four register parameters; the callee may use it to store them.
- **System V red zone:** a 128-byte region below `RSP` that some userspace code may utilize per ABI rules; this assumption must not be carried over to Windows or kernel code.

On **32-bit x86**, historical conventions such as `__cdecl` (typically caller cleans up stack parameters) and `__stdcall` (typically callee cleans up) can differ; using the wrong convention can misalign the stack. On Windows x64, the default calling convention is more standardized, so 32-bit `__stdcall` reasoning cannot be applied mechanically.

## 3. Parameter passing in C: values, pointers, and arrays

**C always passes parameters by value.** An `int` parameter receives a copy of the integer; a `Point` parameter receives the structure value (semantically); a `Point *` parameter receives a **copy of the address**. “Passing a pointer” allows modifying the data it points to, but does not turn the caller's pointer variable itself into a pass-by-reference parameter.

~~~c
void update(int x, int *p) {
    x = 100;       // Only modifies the local copy x
    if (p != NULL) {
        *p = 200;  // Modifies the object whose address the caller passed
    }
}
~~~

The snippet above illustrates semantics and is not a standalone program. If the caller has `int a = 1, b = 2;` and calls `update(a, &b);`, after the call `a` is still `1` and `b` becomes `200`.

Common points of confusion:

- `T *` is a **pointer argument passed by value**; `T **` allows the function to receive the address of the caller's pointer variable and modify that pointer.
- A parameter declared as `int items[]` in a function prototype is adjusted to `int *items`; the array size does not automatically travel with it. A practical interface should include an additional `size_t count` or `size_t capacity`.
- `const T *` restricts operations through that pointer in C code, and **does not automatically guarantee** that the memory region has a sufficient lifetime or is thread-safe.
- `NULL`/a null pointer is only valid if the function contract allows it. Dereferencing null in native code typically causes a process-level fault.
- C does not mandate a universal memory ownership rule: you must explicitly agree on which side allocates, may modify, how long the pointer may be retained, and which API frees it.

### 3.1. Passing and returning a `struct` by value: a runnable C11 example

Save as **`point.c`**:

~~~c
#include <stdio.h>

typedef struct {
    int x;
    int y;
} Point;

static Point moved(Point p, int dx, int dy) {
    p.x += dx;
    p.y += dy;
    return p;
}

static void move_in_place(Point *p, int dx, int dy) {
    if (p != NULL) {
        p->x += dx;
        p->y += dy;
    }
}

int main(void) {
    Point p = {1, 2};
    Point q = moved(p, 3, 4);
    move_in_place(&p, -1, 2);

    printf("p=(%d,%d), q=(%d,%d)\n", p.x, p.y, q.x, q.y);
    return 0;
}
~~~

Compile/run with GCC or Clang (Linux/macOS):

~~~bash
cc -std=c11 -Wall -Wextra -pedantic point.c -o point
./point
~~~

Windows with **Developer Command Prompt** with MSVC:

~~~powershell
cl /W4 point.c
.\point.exe
~~~

Stdout output in both cases:

~~~text
p=(0,4), q=(4,6)
~~~

Explanation: `moved` receives a copy of `p`, modifies the copy, and then **returns a `Point` by value** to initialize `q`. The function `move_in_place` receives the address of `p` and modifies the original object directly. Whether the compiler passes or receives `Point` via registers or memory is an ABI detail; the C-level correctness of the example does not depend on that choice.

## 4. How the ABI passes `struct`, union, and composite types

You cannot generalize from “large `struct`s are always passed on the stack” to a universal rule.

- On **System V AMD64**, 8-byte chunks of an aggregate are classified (`INTEGER`, `SSE`, `MEMORY`, …); small structures can go through multiple registers, while other cases must go through memory.
- On **Windows x64**, many eligible small aggregates are passed as integers of the same size; ineligible aggregates are passed indirectly via a pointer to a caller-allocated temporary. A single argument is not split across multiple registers like the SysV rule.
- On **AArch64**, how they are passed depends on size, layout, and aggregate classification, including special rules for *homogeneous floating-point aggregates* in ABIs where applicable.

### 4.1. Memory layout is part of the contract

~~~c
#include <stddef.h>
#include <stdint.h>

typedef struct {
    uint8_t kind;
    uint32_t value;
} Packet;

// When debugging, check on the exact target:
// sizeof(Packet), _Alignof(Packet), offsetof(Packet, value)
~~~

On many common ABIs, `value` sits after **padding** for alignment, so you cannot assume `sizeof(Packet) == 5`. Sizes and offsets must be measured/verified on the actual target, not based on manually summing bytes.

When exchanging structures across FFI:

1. Synchronize the **C header declaration**, field sizes, order, alignment, padding, and aggregate passing/returning rules.
2. Use `sizeof`, `_Alignof`, `offsetof`, or appropriate static assertions to verify; check both 32-bit and 64-bit variants.
3. Avoid passing **bit-fields, complex unions, flexible array members, C++ classes, `long double`, vectors** directly across the FFI boundary unless accurately modeled for the ABI.
4. Do not arbitrarily add `#pragma pack` or the `packed` attribute: packing alters alignment/layout and can cause unaligned accesses.
5. The same `struct` *by value* may be passed differently from a pointer to `struct`. Changing `Point` to `Point *` **changes the signature/ABI**, not an internal optimization.

## 5. Return values and hidden result parameters

| C declaration | C-level meaning | How the ABI typically implements it |
| --- | --- | --- |
| `int f(void)` | Returns an integer scalar | Integer result register (e.g., `EAX` on x86-64) |
| `double f(void)` | Returns a floating-point scalar | Floating-point register (e.g., `XMM0` or `v0`) |
| `void *f(void)` | Returns a copy of the pointer value | Pointer result register; lifetime and ownership are defined by the API |
| `void f(int *out)` | Returns no C value; writes through the passed-in pointer | `out` is a normal parameter; caller allocates memory |
| `Big f(void)` | Returns `struct Big` **by value** | May go via registers, or caller-allocated result area and a *hidden* address parameter (*sret*) |

**Hidden sret pointer:** For certain aggregate return types, the caller prepares the result memory and the ABI arranges to pass that region's address according to a special rule. The hidden address can shift the positions of visible parameters. However, this is **how the compiler lowers the call**, and does not mean you can arbitrarily change the C prototype to `void f(Big *out)` and assume binary compatibility. To ensure a stable ABI, explicitly design out-parameters directly in the C API.

### 5.1. Distinguishing the result pointer from the pointed-to data

~~~c
// Illustrative C contract examples:
int read_value(int32_t *out_value);  // 0: success; non-zero code: error
char *make_text(void);               // Must specify who frees and using which function
const char *current_text(void);      // Must specify how long the pointer remains valid
~~~

- Do not return the address of an automatic local variable: `return &local;` creates an invalid pointer when the function exits.
- Returning a pointer to dynamically allocated memory is only safe if the caller has an appropriate deallocation API, ideally through the same library that allocated it.
- A returned pointer may only be valid until the **next call**, until the **arena** closes, or until the native object is freed; the contract must state this clearly.
- When needing to report errors and return data, a **status code + out-parameter** is usually clearer than an ambiguous sentinel, such as a null pointer or `-1` which might itself be a valid result.

## 6. Variadics and default argument promotions

For functions declared with `...` like `printf`, arguments in the variadic part undergo **default argument promotions**:

- `float` is promoted to `double`.
- `char`, `short`, and certain narrow integer types undergo *integer promotion* to `int` or `unsigned int` per C rules.
- The callee must read the promoted types. Choosing the wrong format in `printf` or reading the wrong type with `va_arg` is **undefined behavior**.

~~~c
#include <stdio.h>

int main(void) {
    float rate = 1.25f;
    printf("%.2f\n", rate);  // printf receives double after default promotion
    return 0;
}
~~~

Stdout:

~~~text
1.25
~~~

The ABI for variadic calls also has specific details: for example, **Windows x64** duplicates floating-point values into the corresponding integer register at variadic positions; **System V AMD64** uses information about the number of vector registers used per ABI convention. An FFM binding calling a variadic function must declare the appropriate variadic option/boundary; **do not** just copy the descriptor of a function with fixed parameters.

Prefer C wrappers with a **fixed, non-variadic signature** when designing APIs for Java or other languages.

## 7. Data types and representation at the ABI boundary

Do not assume that a Java type matches a C type by name:

| C type/contract | What to check when binding |
| --- | --- |
| `int` | Typically 32-bit on modern x86-64/AArch64 platforms; standard C does not guarantee 32-bit on every target |
| `long` | **LP64** (common 64-bit Linux/macOS): typically 64-bit; **LLP64** (Windows x64): 32-bit |
| `long long` | At least 64-bit, typically 64-bit; verify per ABI when needed |
| `int32_t`, `uint64_t` | Fixed width when these types exist; pay attention to signed/unsigned and value range on the Java side |
| `size_t`, `ptrdiff_t` | Depends on data model/address width; do not assume equivalent to Java `int` |
| `float`, `double` | Requires exact size, ABI classification, and result type; do not swap merely because both are floating-point |
| `void *`, `T *` | Native address; **not** a Java reference; must check null, alignment, lifetime, and memory bounds |
| `char *` | Points to bytes; must specify encoding, length, and presence/absence of a NUL terminator byte |
| `_Bool`, `enum`, bit-field | Must consider size/format determined by the ABI, compiler, and specific enum type |

In particular, **Java `char` is a 16-bit UTF-16 code unit**, whereas C `char` is an addressable byte unit (typically 8 bits on the targets under consideration). Do not map Java strings directly to `char *`; you need native memory holding the chosen encoding, typically UTF-8 with a NUL terminator byte if the C API expects a C string.

When serializing data into a byte buffer for sharing, you must also determine **endianness** and binary representation. Passing an `int` properly across the ABI is not equivalent to manually copying bytes in an arbitrary order.

## 8. End-to-end example: Java calling a C function with FFM (JDK 22+)

The Foreign Function & Memory API (FFM) is an official API starting in **JDK 22**. `Linker.nativeLinker()` knows the native function calling rules for the platform's ABI; `FunctionDescriptor` describes the parameter/return types. The following example uses a **fixed** signature with only two 32-bit integers to focus on the calling convention.

### 8.1. Writing the C library

Save as **`abidemo.c`**:

~~~c
#include <stdint.h>

#if defined(_WIN32)
#  define API_EXPORT __declspec(dllexport)
#else
#  define API_EXPORT __attribute__((visibility("default")))
#endif

API_EXPORT int32_t add_i32(int32_t a, int32_t b) {
    return a + b;
}
~~~

The exported function has the C name `add_i32`, takes two `int32_t` values, and returns `int32_t`. The example uses small values only to avoid signed integer overflow. The `API_EXPORT` macro handles symbol export on the illustrated toolchains.

Compile the library for the **exact OS/architecture running the JVM**:

~~~bash
# Linux: requires GCC/Clang
cc -std=c11 -O2 -fPIC -shared abidemo.c -o libabidemo.so

# macOS: use the corresponding command instead of the Linux command
cc -std=c11 -O2 -dynamiclib abidemo.c -o libabidemo.dylib
~~~

On Windows, run in **x64 Native Tools Command Prompt for VS**:

~~~powershell
cl /LD /W4 abidemo.c /Fe:abidemo.dll
~~~

Run only **one** command matching your platform. Place the resulting library in the directory where Java will be run in the next step.

### 8.2. Writing Java 22+

Save as **`FfmDemo.java`**:

~~~java
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;

public class FfmDemo {
    public static void main(String[] args) throws Throwable {
        System.loadLibrary("abidemo");

        MemorySegment symbol = SymbolLookup.loaderLookup()
                .find("add_i32")
                .orElseThrow();

        MethodHandle add = Linker.nativeLinker().downcallHandle(
                symbol,
                FunctionDescriptor.of(
                        ValueLayout.JAVA_INT,  // int32_t return (target in example)
                        ValueLayout.JAVA_INT,  // int32_t a
                        ValueLayout.JAVA_INT   // int32_t b
                )
        );

        int answer = (int) add.invokeExact(20, 22);
        System.out.println(answer);
    }
}
~~~

Compile and run with **JDK 22+**, from the directory containing `FfmDemo.java` and the native library:

~~~bash
javac FfmDemo.java
java --enable-native-access=ALL-UNNAMED -Djava.library.path=. FfmDemo
~~~

Expected stdout:

~~~text
42
~~~

Step-by-step explanation:

1. `System.loadLibrary("abidemo")` loads the appropriately named file for the OS (`libabidemo.so`, `libabidemo.dylib`, or `abidemo.dll`).
2. `SymbolLookup.loaderLookup()` looks up the address of the `add_i32` symbol from the loaded library via the class-loader-associated mechanism.
3. `FunctionDescriptor.of(returnLayout, arg1Layout, arg2Layout)` provides the **exact count, order, and ABI types**; `ValueLayout.JAVA_INT` is 32 bits wide, corresponding to `int32_t` on the illustrated target.
4. `Linker.nativeLinker().downcallHandle(...)` creates a `MethodHandle` that performs the Java → C transition according to the system calling convention.
5. `invokeExact(20, 22)` requires the exact method type `(int, int) -> int`; the native addition returns `42`.

**Environment limitations:** JDK 17 does not have the official FFM release as in the JDK 22 example. The `--enable-native-access=ALL-UNNAMED` flag permits restricted native operations from the unnamed module. If the library or symbol is not found, the JVM will report a load/symbol lookup error; if the descriptor is wrong yet still links, the consequence can be corrupted data or a JVM crash.

### 8.3. If parameters are pointers/`struct`s

This example intentionally uses scalars only. For `const uint8_t *data, size_t length`, the binding must also:

- Pass the native address properly via `ValueLayout.ADDRESS` and ensure the data region stays alive throughout the call.
- Choose the layout for `size_t` **per the ABI** (FFM provides `Linker.nativeLinker().canonicalLayouts()` to look up C types); do not hard-code `JAVA_LONG` across all targets.
- If a `struct` is passed by value or returned by value, declare a `MemoryLayout` with exact fields/padding and let the native linker apply aggregate rules, including the hidden return area if needed.
- Do not free an `Arena` holding a buffer or upcall stub while native code still retains and may access that address.

## 9. JNI and FFM do not have the same signature at the C boundary

For Java 17 or projects using JNI, a method such as:

~~~java
public final class NativeCalc {
    public static native int add(int a, int b);
}
~~~

has a JNI entry point according to the **header generated by `javac -h`**, conceptually taking the form:

~~~c
JNIEXPORT jint JNICALL Java_NativeCalc_add(
    JNIEnv *env, jclass clazz, jint a, jint b);
~~~

This is an **illustrative signature template**, not a complete standalone linkable JNI file. A `static native` method receives the implicit `JNIEnv *` and `jclass` parameters; an instance method uses `jobject` instead of `jclass`. `JNIEXPORT` and `JNICALL` are JNI macros that depend on the platform/toolchain. Symbol names have specific mangling rules and may differ from the example when using packages, overloads, or different linking mechanism versions; use the **actually generated header**.

Do not take this JNI prototype and assign it directly to an FFM descriptor for a plain C function `int32_t add_i32(int32_t, int32_t)`. Both the **implicit parameters** and the **runtime/ownership contract** are different.

## 10. Designing a stable and testable native interface

A clean C API for the Java ↔ native boundary can be designed as follows (**interface declaration, not a complete program**):

~~~c
#include <stddef.h>
#include <stdint.h>

// 0: success; non-zero: error.
// data points to n readable int32_t elements.
// out_sum points to writable int64_t storage; must not be NULL.
int32_t sum_i32(const int32_t *data, size_t n, int64_t *out_sum);
~~~

This design choice helps control:

- **Width and order:** `int32_t`/`int64_t` are clearer than `long`; `size_t` still must be mapped per the actual data model.
- **Returned data:** status is returned as a scalar, while larger/different-type results are written into `out_sum` storage provided by the caller.
- **Lifetime:** the caller allocates `data` and `out_sum`; the callee does not retain addresses after returning unless the contract permits it.
- **Errors:** document error codes and avoid throwing C++ exceptions across the C/FFI boundary.
- **Stability:** changing the types, order, parameter count, or return type of a public symbol can break the ABI even while keeping the same function name.

With a C++ implementation, provide an `extern "C"` export layer for the C API to avoid C++ name mangling (this does **not** automatically turn a C++ class layout into a stable C layout). When callbacks from native to Java are needed, you must create an upcall/JNI bridge with the matching signature and ensure threads, lifetime, and error reporting conform to the callback mechanism.

## 11. Common errors and diagnosis

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Parameters receive strange values, especially when mixing `int` and `double` | Wrong ABI or register position; FFM descriptor has wrong order/types | Re-check the actual C prototype, target ABI, `FunctionDescriptor`, and corresponding register example |
| Returned `struct` is corrupted or crashes | Wrong aggregate description; ignored hidden result/packing/alignment | Verify `sizeof`, `offsetof`, return classification; consider a C wrapper using an out-parameter |
| Works on Linux, fails on Windows x64 | Assumed C `long` is always 64-bit or used SysV convention on Windows | Cross-check LP64/LLP64 and use the linker's canonical layouts |
| Crashes after the function returns | Native code retained a pointer to a buffer/arena whose lifetime ended or returned a local variable's address | Make lifetime/ownership explicit; extend scope or copy data per contract |
| Returned text has garbled characters or is truncated | Confused Java UTF-16 with `char *`, missing encoding/length/NUL | Choose UTF-8, specify length and who frees the string memory |
| Errors only appear with variadics | Wrong default promotions/`va_arg`/ABI variadic rules | Use a fixed-signature wrapper and verify each type |
| `UnsatisfiedLinkError`, symbol not found | Wrong library name, path, architecture, export, or name mangling | Check the actual file, exported symbols, and target architecture; for JNI use the header generated by `javac -h` |

**Pragmatic debugging workflow:**

1. Note the exact OS, CPU architecture, compiler/toolchain, JDK, library path, and target ABI.
2. Obtain the **actually compiled C header** and the FFM/JNI declaration; compare the signature in order, return type, signedness, and parameter count.
3. Check sizes/layouts with `sizeof`, `_Alignof`, `offsetof`, and a small native test on each target.
4. Use the appropriate symbol tool (`nm -D`/`readelf` on ELF, `nm` on Mach-O, `dumpbin /exports` on PE) to inspect exports; do not guess C++ symbol names.
5. Separate ABI issues from ownership issues: test first with two scalars like `add_i32`, and only then add pointers, buffers, structs, or callbacks.
6. Inspect assembly/disassembly when needed, but rely on the **ABI specification**, not by inferring general rules from a single compiler version or optimization level.

## 12. Self-check questions

1. Why does the same `score(int, double, int)` use `XMM0` for `double` on SysV AMD64 but `XMM1` on Windows x64?
2. When `void set(int *p)` modifies `*p`, is C passing by reference or passing a copy of the pointer?
3. Why can changing a parameter type from `int32_t` to `long` break a binding on Windows x64?
4. Why **cannot** a `struct` returned by value be arbitrarily mapped to a returned pointer at the binding layer?
5. What must Java FFM know besides the symbol's address to call a C function correctly? What lifetime contract do buffers/pointers need?
6. Why is `printf("%f", 1.25f)` valid for variadic types, while a similar descriptor for a function taking a fixed `float` is wrong?

**Short answers:** (1) SysV allocates integer and FP groups separately, whereas Windows x64 ties XMM to argument position; (2) a copy of the address value; (3) `long` is 32-bit in LLP64 but typically 64-bit in LP64; (4) aggregate returns are subject to ABI classification and may use a hidden sret; (5) a descriptor with the right types/order/return and memory that remains alive; (6) varargs promotes `float` to `double`, whereas a fixed `float` parameter does not.

## References

- [Microsoft: x64 calling convention](https://learn.microsoft.com/en-us/cpp/build/x64-calling-convention?view=msvc-170) — parameters, shadow space, return values, and register preservation on Windows x64.
- [Arm: Procedure Call Standard for AArch64 (AAPCS64)](https://github.com/ARM-software/abi-aa/blob/main/aapcs64/aapcs64.rst) — conventions for AArch64 and aggregate classes.
- [Oracle JDK 22: Foreign Function & Memory API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html) — `Linker`, `FunctionDescriptor`, `SymbolLookup`, `Arena`.
- [Oracle JDK 22: Calling a C Library Function with FFM](https://docs.oracle.com/en/java/javase/22/core/calling-c-library-function-foreign-function-and-memory-api.html) — Java → native workflow and signature description.
