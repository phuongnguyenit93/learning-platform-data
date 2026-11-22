# ABI, Pointer, and C Contract Information That FFM Does Not Automatically Infer

## Objectives

The Foreign Function & Memory API (**FFM**) allows Java to call native functions, manipulate memory outside the Java heap, and pass Java callbacks to C libraries without necessarily writing an intermediate JNI C layer. However, FFM **is not a complete inference engine for C code**: it can only link correctly when the developer provides the information that the ABI and actual function signatures require.

After this lesson, you will:

1. Distinguish **what the native Linker knows about the ABI** from **what FunctionDescriptor, MemoryLayout, and Java code must describe manually**.
2. Know why **C long, size_t, pointers, structs, unions, padding, alignment, by-value aggregates, and variadic arguments** cannot be mapped arbitrarily to Java types.
3. Understand the safety boundaries of **MemorySegment**, **AddressLayout**, **Arena**, **reinterpret**, and callbacks/upcalls: byte bounds in Java do not prove the ownership or lifetime of a C pointer.
4. Read the **ownership, nullability, buffer length, encoding, deallocator, error reporting, thread-safety, and lifetime** contracts before creating bindings.
5. Compile and run a **Java 22+ example combined with a C11 library**: native code provides the sizeof/alignof/offsetof of a struct; Java verifies them before accessing.
6. Design a checklist and tests to detect ABI mismatches, lifetime bugs, pointer errors, and library version compatibility.

**Key takeaway:** FFM provides safety mechanisms based on **the information it is given**. A wrong FunctionDescriptor, a wrong MemoryLayout, or a C pointer freed too early can still cause memory corruption or crash the JVM. Do not interpret "having FFM" as "Java automatically discovers the entire C contract".

## 1. What Does FFM Actually Know?

In JDK 22 and later, the stable API package is **java.lang.foreign**. The main components:

| Component | Knows / Handles | Does Not Automatically Know |
| --- | --- | --- |
| **Linker.nativeLinker()** | The ABI of the current platform, rules for passing arguments and receiving results when the descriptor is correct | The semantics of the C function, whether a parameter is input/output/borrowed, or what side effects the function has |
| **SymbolLookup** | Looks up the address of an exported symbol by name in the selected library | The actual C prototype of the symbol, the ABI of an arbitrary function pointer, or C++ signatures with name mangling |
| **FunctionDescriptor** | Models the layout of parameters/return value that **you declare** | Does not open C headers to verify parameter counts/types/signatures |
| **ValueLayout / MemoryLayout** | Width, alignment, byte order, structure or sequence according to the provided layout | Does not prove the layout matches a struct actually built by a C compiler with specific flags |
| **MemorySegment** | Modeled byte range and checks scope/accessibility according to the Java contract | Does not guarantee an address passed from C is still allocated, long enough, or belongs to the right allocator |
| **Arena** | Allocates and manages the lifecycle of memory owned by the arena | Does not automatically free pointers that C malloc/allocates separately without the proper contract/cleanup |
| **Upcall stub** | Creates a function pointer for C to call a Java MethodHandle with the declared descriptor | Does not automatically know how long C will keep the callback, which thread it will call from, or whether the pointer may be kept after the arena closes |

Brief example:

~~~java
Linker linker = Linker.nativeLinker();
MethodHandle handle = linker.downcallHandle(
    symbol,
    FunctionDescriptor.of(ValueLayout.JAVA_INT, ValueLayout.ADDRESS)
);
~~~

This is only a **snippet**, assuming `symbol` has already been found and is indeed the address of a C function with a 32-bit int-compatible return type and one pointer parameter. FFM uses that descriptor to create the downcall. However, if the actual function takes **two parameters** or returns a **struct by value**, FFM does not inspect the header to detect it. Calling the handle with a wrong descriptor is **unsafe**, and can produce wrong results or crash.

### Visualizing the Boundary

~~~text
           C header / documentation / ABI
           ------------------------------
   C function name, prototype, typedef,
   ownership, buffer length, free function,
   thread safety, error codes, layout
                       |
             YOU verify + represent
                       |
        +--------------v--------------+
        | Java FFM binding            |
        | SymbolLookup                |
        | FunctionDescriptor          |
        | MemoryLayout, Arena         |
        +--------------+--------------+
                       |
              Linker + native ABI
                       |
             Actually built C binary
                       |
              RESULTS / POINTERS
                       |
        YOU continue verifying lifetime,
        bounds, null, errors, output data
~~~

Do not confuse the linker knowing the **platform calling convention** with it knowing the **semantic contract of the library**.

## 2. Version Context: Stable API Since JDK 22

FFM went through incubator/preview phases before stabilizing:

| JDK Group | General Status | Meaning When Writing Documentation and Bindings |
| --- | --- | --- |
| **JDK 17–18** | Incubator versions of the Foreign Function & Memory API | Different API/packages/enabling flags; JDK 22 code cannot be used verbatim |
| **JDK 19–21** | Preview, continuing to evolve across JEPs | Requires build and preview options matching each version |
| **JDK 22+** | FFM API finalized under **JEP 454**, in **java.lang.foreign** | Suitable as the baseline for the code in this lesson |

The hands-on exercise below **requires JDK 22 or newer** and does not claim to run on JDK 17. Some ABI/ownership knowledge applies to all versions, but **API names and language details** must be verified against the target JDK.

Native calls and several FFM operations are marked **restricted**. When running an application on the classpath, for example, you can use:

~~~bash
java --enable-native-access=ALL-UNNAMED AbiContractDemo
~~~

In modularized applications, access should be granted to **specific modules** rather than opening to all unnamed modules. Starting in JDK 24, the **--illegal-native-access** policy has modes such as **warn/deny**; default settings may change in later JDK releases. Do not treat a Java command that launches successfully on one JDK as proof that it will run without permissions on another JDK.

**Do not overgeneralize scope:** The fact that "FFM is stable since JDK 22" does not mean the C ABI, native libraries, or all ownership rules have become invariant across operating systems. The Java API may be stable while the C binary still depends on compiler/OS/CPU/ABI.

## 3. What Is an ABI, and What Can the Linker Not Infer?

An **Application Binary Interface (ABI)** is the binary-level contract: how arguments are passed via registers/stack, return value rules, alignment, data type layouts, calling conventions, struct representation, symbol names, and platform constraints.

Example on 64-bit platforms:

| C Type / Characteristic | Common Linux x86-64 (LP64) | Common Windows x64 (LLP64) |
| --- | --- | --- |
| **int** | 32 bit | 32 bit |
| **long** | 64 bit | 32 bit |
| **long long** | 64 bit | 64 bit |
| **void \*** | 64 bit | 64 bit |
| **size_t** | Usually 64 bit | Usually 64 bit |
| Calling convention and struct return | System V x86-64 ABI | Microsoft x64 ABI |

The values above are characteristics of **two typical environments**, not rules for every compiler, every CPU, or every build.

### Why Java `long` Is Not Equivalent to C `long`

- Java **long** is always a signed 64-bit type.
- C **long** has a width defined by the data model/ABI, commonly 64-bit on LP64 and 32-bit on LLP64.
- Java **int** is signed 32-bit; whether C **int** has that width depends on the target ABI or a standard typedef such as **int32_t** when available.
- C **size_t** is an unsigned integer suitable for representing sizes in the environment, not a fixed cross-platform Java type.

Therefore, **FunctionDescriptor.of(ValueLayout.JAVA_LONG)** for a function **long f(void)** may be right on Linux/x64 but wrong on Windows/x64. Conversely, **size_t** on Windows/x64 may still be 64-bit even though C long is 32-bit. Do not apply a single mapping to all C names containing the word "long".

### Using `canonicalLayouts` of the Native Linker

FFM provides:

~~~java
Linker linker = Linker.nativeLinker();

MemoryLayout cLong = linker.canonicalLayouts().get("long");
MemoryLayout cSizeT = linker.canonicalLayouts().get("size_t");
MemoryLayout cPointer = linker.canonicalLayouts().get("void*");
~~~

This is a **Java 22+ snippet**, not a standalone `main()`. **canonicalLayouts()** returns a map from basic C type names to layouts for the ABI supported by the current native linker. Names such as **long**, **size_t**, and **void\*** are guaranteed to be supported by the native linker according to the JDK 22 documentation.

**Important limitation:** `canonicalLayouts` does not automatically inspect the headers of a specific library. It does not know a custom typedef **my_count_t**, a struct you defined, or the compiler flags used when building the library. It also does not know whether the C header changed between two binary versions.

For unsigned integers, the Java carrier can be the signed type of the same width. For example, **uint32_t** is commonly represented by **int**/JAVA_INT in bindings. Java must maintain the unsigned semantics itself: appropriate comparisons, range checks, and conversions. With **uint64_t**, some valid values exceed **Long.MAX_VALUE**; do not treat a negative Java long as a valid size value and pass it directly to an allocator.

### ABI Types Harder Than Scalars

Beyond scalars, there are:

- **struct by value:** an ABI may pass/return a small struct in registers, memory, or via a special mechanism; the descriptor must have an appropriate group layout, not an arbitrary ADDRESS substitution.
- **union:** members overlap in memory; the caller must know which branch is currently active and how to interpret it.
- **bit-field:** bit order, allocation unit, and padding can be implementation-dependent; they cannot be inferred from field names.
- **packed struct / pragma pack:** reduces alignment or changes padding; Java's default layout may not match.
- **variadic functions:** require modeling additional arguments and proper C promotions, e.g., small/float types have specific promotion rules.
- **non-default calling conventions** or function pointers from a library following a specialized ABI: the default native linker may not call them correctly.
- **long double, complex types, or vector types:** do not have linker-supported layouts/calling conventions by default.

FFM helps call the descriptors that the linker supports. It **does not prove that the C library actually exports the exact kind of function** you described.

## 4. A C Signature Is a Contract That Must Be Verified

Suppose a C header declares:

~~~c
#include <stddef.h>

size_t library_count(const unsigned char *buffer, size_t n);
~~~

From this signature, Java must know:

1. **buffer** is a pointer: represented by **ValueLayout.ADDRESS** in FunctionDescriptor.
2. **n** is **size_t**, so use the canonical `size_t` layout for the native ABI, do not hardcode JAVA_INT/JAVA_LONG across platforms.
3. The return value is also **size_t**.
4. **const** expresses that the C function must not modify the contents through that pointer under the API's constraint; FFM does not automatically create a "const MemorySegment" to protect the data.
5. The function takes a buffer **of length n bytes**, but the signature does not clarify **whether n can be 0**, **whether a NULL buffer is valid when n=0**, or whether the function **retains the pointer after returning**.
6. The parameter `n` is measured in **bytes** in this function's contract, not Java characters/UTF-16 code units.

An FFM description of the call shape might be:

~~~java
Linker linker = Linker.nativeLinker();
MemoryLayout sizeT = linker.canonicalLayouts().get("size_t");

FunctionDescriptor countDescriptor =
    FunctionDescriptor.of(
        sizeT,                  // return size_t
        ValueLayout.ADDRESS,    // const unsigned char *
        sizeT                   // size_t n
    );
~~~

This is a **Java 22+ snippet**. It tells the linker the argument and result layouts, **has not looked up the symbol**, has not created the handle, and has not resolved nullability/ownership. When calling the handle, the Java carrier for `size_t` depends on the layout (usually `int` on 32-bit, `long` on 64-bit). You cannot always call **invokeExact(ptr, longN)** and expect the linker to coerce it if the handle actually requires **int**.

### `FunctionDescriptor` Cannot Be "Validated" by the Symbol Alone

A native symbol typically only has an address and an export name. It does not necessarily contain complete metadata about:

- Parameter types and count.
- Whether it is a variadic function.
- Actual return type; struct by value or pointer.
- What element the pointer points to.
- The calling convention required by the compiler.
- Error state, side effects, or thread safety.

If you describe **int native_sum(int, int)** when the actual symbol is **double native_sum(double, double)**, Java can still create a MethodHandle with the wrong descriptor; problems only occur when calling it. **Do not treat successful `downcallHandle` creation as proof of a correct signature.**

### C++ Name Mangling and `extern "C"`

FFM looks up symbols by their **actual exported name**. A C++ function may be renamed by the compiler via name mangling; the string **"calculate"** is not necessarily the exported symbol.

To design a more durable FFI surface, consider a C ABI wrapper:

~~~cpp
// Snippet in a C++ file: keep ABI stable for FFM callers.
extern "C" int32_t api_calculate(int32_t input) noexcept {
    return input + 1;
}
~~~

This snippet also needs the **<cstdint>** header and an OS-specific symbol export mechanism to become a complete library. **extern "C"** avoids C++ name mangling and selects C name linkage; it does **not** automatically guarantee struct layout, exception safety, or version compatibility. Native C++ exceptions must not cross the FFM boundary; the wrapper must catch and convert them into error results per the API contract.

## 5. C Struct Layout: Byte Offsets Must Match the Compiler

One common mistake is describing a C struct by placing Java ValueLayouts consecutively and assuming every compiler lays them out the same way.

C header:

~~~c
#include <stdint.h>

typedef struct Record {
    uint8_t  kind;    // 1 byte
    uint32_t count;   // 4 bytes on platforms supporting uint32_t
} Record;
~~~

On a common ABI with 4-byte alignment for `uint32_t`, the compiler typically lays out:

~~~text
Record memory (common ABI example)
byte offset    0    1    2    3    4    5    6    7
               +----+----+----+----+----+----+----+----+
               |kind|       padding     |   count      |
               +----+----+----+----+----+----+----+----+
offsetof(kind)  = 0
offsetof(count) = 4
sizeof(Record)  = 8
_Alignof(Record)= 4
~~~

However, the **4/8** numbers above are an example, **not something FFM automatically knows from the struct name**. If the compiler uses different packing, a different target ABI, or the header changes, the layout can differ.

### Declaring `MemoryLayout` with Explicit Padding

A description corresponding to the common diagram above:

~~~java
MemoryLayout recordLayout = MemoryLayout.structLayout(
    ValueLayout.JAVA_BYTE.withName("kind"),
    MemoryLayout.paddingLayout(3),
    ValueLayout.JAVA_INT.withName("count")
);
~~~

This is an **ABI-conditional illustrative layout**. **MemoryLayout.structLayout does not automatically insert C-style padding** between members to match the compiler. Each layout must be built from **actual ABI information**.

If the struct is passed **by value** into a foreign call, the linker may require the layout to obey stricter alignment and padding constraints. With a **pointer to struct**, you can use ADDRESS in the descriptor, but you still need the exact layout when accessing fields from Java. Neither approach exempts you from verification.

### Reliable Sources for Layout Verification

The source of truth is not "looks like C" but **the C compiler that built the actual binary**.

Use:

- **sizeof(Record)** to know the total byte size including trailing padding.
- **_Alignof(Record)** or **alignof** per the C standard/compiler to know alignment.
- **offsetof(Record, count)** (from **<stddef.h>**) to know the byte offset of a regular field.
- **Static assertions** in C to check assumptions about types and ABI.
- **A shim exporting these values** for Java to verify at startup if the build supports multiple targets.
- **ABI tests** run on the exact binary/OS/compiler flags that will be deployed, especially with packing/typedefs/macros.

**Note:** **offsetof** cannot be used directly for all bit-fields because bit-fields do not have an address like regular fields. For bit-fields or unusual packed layouts, a wrapper with C getters/setters is usually safer and more maintainable than having Java guess bit offsets.

### Why Checking Only `sizeof` Is Not Enough

Two structs can have the **same total byte size but different field offsets or member types**. When FFM reads at the wrong offset, the value can be wrong without going out of bounds, so Java throws no exception. Therefore, when fields must be accessed directly, verify **size, alignment, offsets, and field types**, not just total size.

## 6. C Pointers Do Not Carry Bounds, Ownership, or Lifetime

In C, both of the following prototypes return a pointer:

~~~c
const char *api_borrow_name(void);
char *api_make_name(void);
~~~

Yet the behavior can be completely different:

- The **borrow_name** function might return a borrowed pointer to a static region, an internal region of an object, or a buffer valid only until the next call.
- The **make_name** function might require the caller to free it with **api_free_name**, **free**, or a custom allocator.
- Either or both could also return **NULL** on error.

**FFM only sees the address and descriptor**; it does not infer those meanings from the function name. Even **const char\*** does not specify length, encoding, whether the data has a NUL terminator, expiration time, or nullability.

### Returned Pointers Are Often Zero-Length Segments

When FFM receives a pointer with no known size, it typically represents the pointer as a **MemorySegment with `byteSize() == 0`**. This is a conservative choice: it cannot determine how many bytes can be read from a raw address.

Example:

~~~java
MemorySegment ptr = /* result of a C function returning void* */;
System.out.println(ptr.byteSize()); // typically 0 for a raw pointer
~~~

This is a **conceptual snippet**, not independently runnable without a real C function and `ptr`. Do not treat **byteSize()==0** as "C actually allocated 0 bytes"; it may simply mean **Java does not yet know the bounds**.

FFM has the restricted method **MemorySegment.reinterpret(...)** to assign new bounds/lifetime when you **already have proof from the C contract**. However, **reinterpret does not allocate more memory and does not prove the address is valid**. If you arbitrarily reinterpret a dangling pointer as 1 GB, FFM's bounds check may allow reads within the 1 GB you declared, while OS/native memory may be invalid; invalid access can cause a crash.

### A Correct Pointer Needs at Least Six Pieces of Information

| Information | Question to Answer |
| --- | --- |
| **Address and nullability** | Can it return NULL? Does NULL mean empty or error? |
| **Size and unit** | How many **bytes**, elements, or code units? Who provides the size? |
| **Element layout** | Does the pointer point to `char`, `int32_t`, a struct, or an opaque byte region? |
| **Ownership** | Does the caller own it, only borrow it, or share it? |
| **Lifetime** | How long does it remain valid? Until freed, until the C object closes, or only during the callback? |
| **Deallocator** | Can `free` be used? Is `api_destroy` required? Can it be freed on another thread? |

Additionally, there are **alignment, mutability, thread-safety, aliasing, and whether the pointer is retained after the call**.

### Do Not Mix the Wrong Allocator

If a C API allocates using **api_create_buffer**, do not assume **Arena.close()** or C **free** is suitable for deallocation. The library might use a custom pool, C++ new/delete, a runtime-versioned allocator, or require calling **api_release_buffer** to decrement a reference count.

**Conceptually right:** a Java wrapper implementing **AutoCloseable**, storing the address and calling the **exact deallocator specified by the C documentation**, exactly once, when no longer in use.

**Conceptually wrong:** attaching an arbitrary address to an arena and treating arena closure as an automatic safe free. An arena cannot free memory it does not own from an address alone.

### Pointer-to-Pointer and Output Parameters

An API like:

~~~c
int api_read_data(unsigned char **out, size_t *out_len);
~~~

has **two levels of pointers** and an output parameter. FFM cannot automatically infer:

- Who allocates memory for **\*out**?
- Does the value **\*out_len** measure bytes or elements?
- On an error result, is **\*out** initialized?
- Must the caller free **\*out**?
- Can it return **\*out == NULL** and **\*out_len == 0**?
- What is the size of **size_t** on this ABI?

Java must allocate space for **one address** and **one `size_t`**, read them after the function returns successfully, check bounds/overflow, and then free the result properly. **ValueLayout.ADDRESS** for **out** does not supply those rules on its own.

## 7. `Arena` Only Manages What Belongs to Its Scope

**Arena** helps Java allocate native memory and manage when that memory is reclaimed according to the scope contract. However, it does not turn a borrowed C pointer into an owned pointer or protect a pointer that C has already freed outside Java.

| Arena | Characteristics | Caution |
| --- | --- | --- |
| **Arena.ofConfined()** | Native segment accessible only from the owning thread, explicitly closeable | Do not hand the segment to an async native worker and close the arena before the worker finishes |
| **Arena.ofShared()** | Segment can be used from multiple Java threads, explicitly closeable | Being shareable does not mean data access is automatically synchronized |
| **Arena.ofAuto()** | Memory managed via automatic reclamation | Reclamation timing is non-deterministic; hard to use for matching callback lifetimes |
| **Arena.global()** | Unbounded lifetime scope in the JVM | Cannot be closed; easy to create process-lifetime memory if allocated indiscriminately |

Example:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment buffer = arena.allocate(128, 8);
    buffer.set(ValueLayout.JAVA_INT, 0, 42);

    // Only pass buffer to a C function confirmed
    // NOT to retain the pointer after the downcall completes.
}
// Arena.close() renders buffer invalid.
~~~

This is a **Java 22+ snippet**, with no real C downcall. FFM's lifetime/bounds checks help catch **invalid accesses performed by Java after the scope closes**. However, if C code saved the address into a queue and continues using it after the arena closes, Java cannot block all such accesses because they happen outside the JVM.

### Borrowed During One Call vs. Async Retention

**C contract A:** "The function only reads the buffer while the call is in progress; does not retain the pointer." You can allocate the buffer from a confined arena, make the synchronous downcall, return, and close the arena.

**C contract B:** "The function stores the pointer and may use it after returning; the callback is invoked on a worker." You must not automatically close the arena when the downcall returns. You need a long enough scope, shutdown/unregister logic, a guarantee that callbacks finish before freeing, and synchronization management.

**C contract C:** "The function returns an internal pointer, valid only until the next call." Do not keep the pointer across other calls and access it later; copy the needed data immediately within the valid window or use a copy API provided by the library.

FFM cannot distinguish A/B/C when it only sees C pointer parameters and return types.

## 8. Strings, Null Terminators, and Buffer Lengths: The C Contract Is Mandatory

A C signature:

~~~c
int api_parse(const char *text);
~~~

is **not enough** to know whether `text` must be UTF-8, ASCII, Latin-1, UTF-16, or a specialized encoding. C may also require a **00** byte terminating the string. In Java, `String` is Unicode data (represented in UTF-16), not directly equivalent to **char\***.

FFM supports creating **C strings** with an allocator (e.g., **Arena.allocateFrom(String)** in JDK 22), using the encoding per that Java API and a NUL terminator. This is useful **if** the C API actually requires a C-string in the corresponding encoding.

However, you must check:

- Does the C API need **standard UTF-8** or another encoding?
- Can the C string contain **U+0000** in the middle? If C uses `strlen`, a 00 byte will terminate it early.
- Does the C API use **byte count**, character count, element count, or a delimiter to determine length?
- Does the API modify **char\***? Does the Java-allocated buffer have enough capacity for the output and terminator?
- Does a **size_t length** variable measure **input**, **output capacity**, or **actual bytes written**?
- Can the C API retain the pointer to `text` after the call?

In particular, do not take **Java String.length()** (number of UTF-16 code units) and pass it as the UTF-8 byte count. A non-BMP emoji can be 2 code units but 4 UTF-8 bytes. Conversely, a C API using **modified UTF-8** per JNI has a different contract from standard UTF-8.

**FFM cannot automatically change the meaning of a `length` parameter just because it has type `size_t`.** The C documentation must define the unit of measurement and the relationship between pointer and length.

## 9. Callback, Error Handling, and Threading Contracts

A C API may accept a function pointer:

~~~c
typedef void (*event_cb)(int code, void *user_data);

int api_register_callback(event_cb cb, void *user_data);
void api_unregister_callback(void);
~~~

An **FFM upcall stub** can create a function pointer pointing to a Java `MethodHandle`. However, the C prototype above does not state:

- How long will C keep `cb`?
- Can the callback run **on a native thread**?
- Can multiple callbacks be invoked concurrently?
- Can the callback re-enter the C API?
- After `unregister`, does C guarantee no callbacks are still running?
- Is **user_data** owned by Java or C, and who frees it?
- Can the callback throw a Java exception? In practice, callbacks must have an explicit catch/translate error policy; never let an arbitrary Java exception "fly across" the C ABI.

If an upcall stub belongs to an arena that has already closed, and C still holds and calls that function pointer, the program can crash. You must match the **stub's scope** to the duration C uses the callback and have an unregister/drain protocol before freeing.

### Error Codes, `errno`, and Partial Results

C APIs commonly report errors in several ways:

| Style | What You Need to Know |
| --- | --- |
| Return **int status** | Which values mean success/failure? Are output parameters valid on error? |
| Return **NULL** | Does NULL mean error, no data, or a valid value? |
| Set **errno** | Must it be read immediately after the downcall on the same thread? Is the appropriate linker capture-call-state option used? |
| Return **size_t** | Is there a sentinel like `SIZE_MAX`, and how does Java handle unsigned values? |
| Use an **error callback** | Which thread does the callback run on, and what ordering/delivery guarantees exist? |
| C++ throws exceptions | The wrapper must translate them into a C ABI error model; never let exceptions cross the FFM ABI |

**The Linker does not guess error semantics.** A return value of type **int** is just an integer at the ABI level. Whether **-1** is an error or a valid result depends entirely on the contract.

### Thread-Safe Does Not Mean Usable From Any Thread

Even when **Arena.ofShared()** allows Java threads to access a `MemorySegment`, the C library may require all APIs to be called on the same native thread, an event loop, or while holding a library-managed mutex.

If the API has thread affinity, Java must dispatch downcalls on the right executor/thread. If the API stores pointers into a worker, Java must keep the memory alive long enough. These things **cannot be inferred from `FunctionDescriptor` or `MemorySegment` alone**.

## 10. A Minimal C Contract Checklist Table Before Writing Bindings

For each native function, record at least:

| Item | Questions to Answer | Source of Verification |
| --- | --- | --- |
| **Symbol name** | What is the exact exported name? Is there C++ mangling? | Header, binary symbols, export map |
| **Prototype** | Return/argument types, by-value or by-pointer, varargs? | Version-matched header |
| **ABI** | OS/CPU/compiler, calling convention, typedef widths? | Build/toolchain docs, linker canonical layouts |
| **Struct layout** | `sizeof`, `alignof`, `offsetof`, padding/packing? | `sizeof`/`_Alignof`/`offsetof` from binary/shim |
| **Pointer length** | How many bytes/elements? Who provides the length? | Docs, header comments, tests |
| **Nullability** | Is NULL allowed in parameters/return? | API contract |
| **Ownership** | Borrowed, returned owned, or ownership transfer? | API contract |
| **Deallocator** | Call `free`, `destroy`, `release`, or must not free? | API contract, allocator docs |
| **Lifetime** | How long is the pointer valid? | Docs, callback/worker lifecycle |
| **Encoding** | UTF-8, ASCII, UTF-16, or binary? NUL terminator? | API contract |
| **Mutability** | `const`/input/output/in-out? Buffer capacity? | API contract |
| **Threading** | Reentrant/thread-safe, thread affinity, async callbacks? | Docs/tests |
| **Errors** | Status, NULL, `errno`, sentinel, partial output? | Docs/tests |
| **Versioning** | Which releases change struct ABI/symbols? | SDK version, changelog, ABI tests |

If answers are missing, a **thin C adapter** can turn a hard-to-call interface into a clearer API: fixed-width types like **int32_t/uint32_t** where appropriate, pointer+byte-length, stable error codes, consistent release functions, and `sizeof`/`offsetof` probes. An adapter **does not replace lifecycle documentation**, but it reduces the ABI surface that FFM must describe.

## 11. Complete Example: Java 22+ and C11 Self-Verifying ABI Before Reading a Struct

This example illustrates the difference between:

- **Information FFM can get from the native Linker:** the canonical layout of **size_t**.
- **Information that must come from the actual C binary:** **sizeof**, **alignment**, and **offsetof** of the struct.
- **Contract that must be published by the C API:** the function only **borrows** the pointer during the downcall and does not retain it after returning; negative value **-1** signals an error.
- **What FFM can do once it has the information:** allocate a buffer with the right size/alignment, write fields at the right offsets, and call the native function.

### 11.1. C Header/Implementation: `ffm_contract.c`

Create the file **ffm_contract.c**:

~~~c
#include <stddef.h>
#include <stdint.h>
#include <limits.h>

#if defined(_WIN32)
#  define API __declspec(dllexport)
#else
#  define API __attribute__((visibility("default")))
#endif

/*
 * Example intentionally requires uint8_t to be 1 byte and uint32_t to be 4 bytes.
 * Does not use pragma pack; layout is determined by the actual C compiler.
 */
_Static_assert(CHAR_BIT == 8, "this demo requires 8-bit bytes");
_Static_assert(sizeof(uint32_t) == 4, "uint32_t must be 4 bytes");

typedef struct Record {
    uint8_t kind;
    uint32_t count;
} Record;

/* Returns metadata matching the compiled C binary. */
API size_t record_size(void) {
    return sizeof(Record);
}

API size_t record_alignment(void) {
    return _Alignof(Record);
}

API size_t record_count_offset(void) {
    return offsetof(Record, count);
}

/*
 * CONTRACT:
 * - p is borrowed, not retained after the function returns.
 * - p != NULL, points to a valid, properly aligned Record.
 * - delta >= 0.
 * - count, kind are unsigned.
 * - Returns non-negative result or -1 if p/delta is invalid
 *   or sum exceeds int32_t range.
 * - Function does not allocate/free and does not retain callbacks.
 */
API int32_t record_score(const Record *p, int32_t delta) {
    if (p == NULL || delta < 0) {
        return -1;
    }

    uint64_t sum = (uint64_t)p->count
                 + (uint64_t)p->kind
                 + (uint64_t)(uint32_t)delta;

    if (sum > INT32_MAX) {
        return -1;
    }
    return (int32_t)sum;
}
~~~

**C contract explanation:**

- **size_t** is a native ABI-dependent type; FFM must obtain its layout from the native linker. Do not hardcode "size_t = C long".
- **uint8_t** and **uint32_t** represent fixed-width integers in environments where they are available; static assertions reject incompatible builds.
- **Record** has two fields, but Java code does not assume field `count` is at offset 4: C provides **record_count_offset()**.
- **record_alignment()** lets Java allocate with the right alignment. C does not require Java to guess from field names.
- **record_score** only reads the pointer, without retaining or freeing it. Thus Java can use a confined arena for the scope of a synchronous call.
- Error **-1** is used explicitly per the contract; valid return values of the function are restricted to non-negative integers.

### 11.2. Compiling the Native Library

**Linux (GCC or Clang, C11):**

~~~bash
cc -std=c11 -O2 -fPIC -shared \
  ffm_contract.c -o libffmcontract.so
~~~

**macOS (Clang, C11):**

~~~bash
clang -std=c11 -O2 -fPIC -dynamiclib \
  ffm_contract.c -o libffmcontract.dylib
~~~

**Windows (Visual Studio 2022 Developer Command Prompt, C11 support):**

~~~bat
cl /nologo /W4 /std:c11 /LD ffm_contract.c /link /OUT:ffmcontract.dll
~~~

The commands above are **OS-specific build alternatives**, not sequential steps. Choose a native toolchain compatible with the JDK/OS/CPU/ABI in use. The library name produced by the build command matches **System.mapLibraryName("ffmcontract")** on common platforms.

### 11.3. Creating `AbiContractDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class AbiContractDemo {
    private AbiContractDemo() {
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        // size_t is a C ABI type; do not hardcode JAVA_LONG.
        MemoryLayout sizeT =
                linker.canonicalLayouts().get("size_t");
        if (!(sizeT instanceof ValueLayout)) {
            throw new IllegalStateException("No size_t layout");
        }

        // Arena keeps the native library lookup and buffer alive together.
        try (Arena arena = Arena.ofConfined()) {
            Path library = Path.of(
                    System.mapLibraryName("ffmcontract")
            ).toAbsolutePath();

            SymbolLookup symbols =
                    SymbolLookup.libraryLookup(library, arena);

            // C size_t record_size(void)
            MethodHandle sizeof = linker.downcallHandle(
                    symbols.find("record_size").orElseThrow(),
                    FunctionDescriptor.of(sizeT)
            );

            // C size_t record_alignment(void)
            MethodHandle alignof = linker.downcallHandle(
                    symbols.find("record_alignment").orElseThrow(),
                    FunctionDescriptor.of(sizeT)
            );

            // C size_t record_count_offset(void)
            MethodHandle offsetof = linker.downcallHandle(
                    symbols.find("record_count_offset").orElseThrow(),
                    FunctionDescriptor.of(sizeT)
            );

            /*
             * C size_t has carrier int or long depending on the ABI.
             * invokeWithArguments returns a boxed Number matching the carrier,
             * instead of a mistyped invokeExact on one platform.
             * These are small metadata values, not SIZE_MAX.
             */
            long size = ((Number) sizeof.invokeWithArguments())
                    .longValue();
            long alignment = ((Number) alignof.invokeWithArguments())
                    .longValue();
            long countOffset =
                    ((Number) offsetof.invokeWithArguments())
                            .longValue();

            /*
             * Application policy: only supports small Records, with
             * alignment at least 4 and field count 4-byte aligned.
             * Catch ABI/probe mismatches before reading or writing memory.
             */
            boolean valid = size >= 8
                    && size <= 1024
                    && alignment >= 4
                    && (alignment & (alignment - 1)) == 0
                    && countOffset >= 1
                    && countOffset % 4 == 0
                    && countOffset <= size - Integer.BYTES;

            if (!valid) {
                throw new IllegalStateException(
                        "Unsupported native Record layout"
                );
            }

            MemorySegment record = arena.allocate(size, alignment);

            // kind is uint8_t, count is uint32_t in C.
            // Values 3 and 7 are within the signed range of the Java carriers.
            record.set(ValueLayout.JAVA_BYTE, 0, (byte) 3);
            record.set(ValueLayout.JAVA_INT, countOffset, 7);

            // C int32_t record_score(const Record*, int32_t)
            MethodHandle score = linker.downcallHandle(
                    symbols.find("record_score").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS,
                            ValueLayout.JAVA_INT
                    )
            );

            // invokeExact: (MemorySegment, int) -> int.
            int result = (int) score.invokeExact(record, 2);
            if (result < 0) {
                throw new IllegalStateException(
                        "Native record_score failed"
                );
            }

            System.out.println("abiVerified=true");
            System.out.println("result=" + result);
        }
    }
}
~~~

### 11.4. Compiling and Running on JDK 22+

Place **AbiContractDemo.java** and the native library in the same working directory. No JNI header or JNI native method is needed; this application uses FFM directly.

~~~bash
javac AbiContractDemo.java
java --enable-native-access=ALL-UNNAMED AbiContractDemo
~~~

If the C binary matches the contract on an ABI accepted by the demo, the **exact stdout** is:

~~~text
abiVerified=true
result=12
~~~

Because Java writes **kind=3**, **count=7**, and passes **delta=2**, the C function returns **3 + 7 + 2 = 12**.

The values **size, alignment, countOffset** are retrieved from the C binary at runtime, so the code **does not print assumed values** like "sizeof=8" that would make the output platform-dependent. If the platform does not satisfy the sample layout policy, Java stops with an exception **before calling record_score**, instead of guessing offsets.

### 11.5. What Does the Demo Prove and Not Prove?

**Proves:**

- The Linker lets you obtain the **canonical layout of `size_t`** for the native ABI.
- `SymbolLookup` finds function pointers by symbol names exported by C.
- The C functions **record_size/record_alignment/record_count_offset** provide metadata that FFM does not know from the name **Record**.
- Java uses the verified size/alignment/offset to allocate and write native memory in an arena.
- The descriptor for **record_score** is declared explicitly and is only correct thanks to the actual C source/binary contract.
- For a C function that only borrows the pointer during the call, the arena can be closed after the downcall.

**Does not prove:**

- That any C layout other than **Record** is automatically correct; each must be probed/tested separately.
- That every **size_t** fits in a signed `long` or can be converted via `Number.longValue` for large values; the demo only reads small metadata.
- That every C function returning a pointer has safe bounds/lifetime; the example has no pointer return or async usage.
- That FFM will detect a wrong descriptor if the C library is replaced with a different binary.
- That a successful Java/C call means the C library is thread-safe or ready for concurrency.
- That the demo is compatible with JDK 17–21; it requires **JDK 22+**.

**Verification scope:** This is a source-complete Java/C example. The stdout output is determined from the code when built/deployed successfully; integration must be run on the actual JDK/toolchain before going to production.

## 12. Why Native Probes and Headers Are Still Not Enough

Having compiler probes does not replace reading the entire C contract.

### 12.1. Pointer Lifetime Is Not in `sizeof`

You can know **sizeof(Record)=8** and still pass C a pointer into an arena and then **close the arena before an async callback**. A right layout does not save you from use-after-free. Type/layout metadata does not answer the question "Does C still use the pointer after the function returns?".

### 12.2. A Correct Field Offset Does Not Validate Semantics

For example, field **count** is at offset 4 in both versions of a C library, but version 2 changes the unit from **bytes** to **elements**. Java still reads an `int` at the right offset, but the logic is wrong. Versioning and semantic contract tests are required.

### 12.3. The ABI Can Change Without Changing Java Source

Many factors can make the native ABI differ:

- Changing the compiler, target triple, compiler flags, or packing.
- Changing typedef/macro configuration when building the library.
- Changing the JDK runtime architecture relative to the library.
- Changing how the compiler exports C++ symbols.
- Upgrading the library version without synchronizing headers.
- Changing the calling convention or an optimized build with different assumptions.

**Lock header and binary versions** into an explicit deployment package, record checksums/build metadata, and check the ABI in CI/at startup when appropriate.

### 12.4. Generated Bindings Do Not Replace Contract Review

Tools like **jextract** can read headers using a C parser and generate appropriate Java bindings/layouts for supported declarations. It helps reduce typos in descriptors and offsets, but **does not automatically clarify every meaning** such as:

- Does the caller own the pointer?
- Does the function retain the buffer after returning?
- Should `free` or a custom `destroy` be called?
- Which threads can the API callback run from?
- Which value is the error sentinel?
- Does a length field use bytes or code points in the protocol?
- Did any version change semantics?

Therefore, generated code must be accompanied by **tested contract wrappers**. Do not interpret "the binding compiles" as "memory safety is proven".

## 13. Some Real-World Scenarios

### Scenario A — Wrong C `long` on Windows x64

A Java wrapper writes:

~~~java
FunctionDescriptor.of(ValueLayout.JAVA_LONG)
~~~

for the function **long get_total(void)** because the code was developed on Linux/x64. When running on Windows/x64, **C long is typically 32-bit**; the descriptor can skew how the result is passed/received.

**How to handle:** use the canonical layout **"long"** for the native ABI and let the code pick the right carrier; better yet, for a controlled public C API, consider exporting the function with a fixed-width type **int64_t** if that fits the contract.

### Scenario B — Pointer + Length Confuses Bytes and Elements

A C API requires:

~~~c
void api_write(const uint16_t *items, size_t item_count);
~~~

Java passes **buffer.byteSize()** into **item_count**, causing C to potentially read twice as many elements.

**How to handle:** document `count` as **the number of `uint16_t` elements**, computed as total bytes **divided by `sizeof(uint16_t)`** after checking divisibility and range, rather than blindly sending the byte count.

### Scenario C — Borrowed Pointer Freed Incorrectly

A C API returns **const char\*** pointing into a static/internal region. A Java wrapper registers a cleanup action calling **free(pointer)** when the arena closes.

**Consequence:** attempting to free memory not owned by the caller, which can crash or corrupt the allocator.

**How to handle:** document the borrowed pointer, **do not free**; if it needs to live longer, copy the data into Java/caller-owned memory within its valid lifetime.

### Scenario D — C Writes Output Past Buffer

A C API takes **char *out, size_t capacity**, and can write up to **capacity** bytes and insert a terminator depending on state. Java allocates a small **capacity** but reports a larger number.

**Consequence:** C overflows the buffer. FFM cannot block direct writes from C using only the Java segment's bounds if C was already passed the wrong pointer and length.

**How to handle:** pass a `capacity` matching the exact `byteSize` of the allocated region (or a verified smaller capacity), have a separate output-length protocol, and fuzz test with bad inputs.

### Scenario E — Callback Used After Arena Closes

Java creates an upcall stub in a confined arena, C saves the callback and uses it after registration completes. Java exits the try-with-resources block and then a C worker invokes the pointer.

**Consequence:** pointer to the stub has expired; can crash.

**How to handle:** separate a long-lived callback scope, provide an unregister function, and ensure no callbacks are still running before closing the arena. Use appropriate synchronization and a Java exception policy.

### Scenario F — Struct Field Read Incorrectly Without Crashing

C changes packing, moving **offsetof(count)** from 4 to 1. The Java wrapper still uses offset 4. The segment still has enough bytes and Java `get` does not go out of bounds, but it reads garbage values.

**How to handle:** retrieve/verify **offsetof**, **alignment**, and **size** of the actual binary or wrap the struct with C accessor functions. Do not rely on Java exceptions as a method of ABI validation.

## 14. Testing and Verification in CI

For FFM bindings, test categories should be separated clearly:

1. **Header/binary identity:** verify the exact native library, version, export names, and checksum.
2. **ABI probe:** compare **sizeof, _Alignof, offsetof** of structs; check widths of C typedefs in use.
3. **Function signature smoke test:** call each function with simple inputs, sentinel values, and real return structures; especially functions taking/returning structs by value.
4. **Pointer contract tests:** NULL/zero-length, small buffers, output capacity, alignment, ownership, double-free, and controlled use-after-free in test environments.
5. **Error handling tests:** error codes, `errno`/call-state, partial writes, and cleanup paths.
6. **Threading/callback tests:** concurrent calls, unregister, late callbacks, arena lifetime, thread affinity.
7. **Boundary tests:** `SIZE_MAX`/overflow, Unicode characters, empty strings, large data, and malformed input.
8. **Platform matrix:** the Linux/macOS/Windows and CPU/ABI/JDK combinations the product actually supports.
9. **Native diagnostics:** compiler ASan/UBSan and JVM crash logs can be used when appropriate; Java exceptions do not prevent all memory corruption in C.
10. **Upgrade/rollback:** swap native binaries or header versions, verifying the wrapper rejects incompatible ABIs before processing real data.

If the library is third-party code, prefer running complex tests in a **separate process**. A native bug can crash the entire JVM running the tests, so the test harness should tolerate crashes and classify results clearly.

## 15. Common Mistakes

| Mistake | Why It Is Dangerous | How to Fix |
| --- | --- | --- |
| Mapping every **C long** to `JAVA_LONG` | LP64 and LLP64 differ | Use linker canonical layout **long** or fixed-width APIs |
| Assuming every **size_t** is a Java `long` | On 32-bit it can be 32-bit, unsigned semantics differ | Use canonical **size_t** and the right carrier |
| Finding a symbol means the signature is exact | Symbols do not carry full prototypes | Cross-check header/binary, build ABI smoke tests |
| Using `ADDRESS` means knowing how many bytes the pointer points to | An address does not carry length | Obtain size from contract, check before accessing |
| Reinterpreting 1 GB yields 1 GB of valid memory | `reinterpret` only changes modeled bounds | Only reinterpret per verified allocation/owner info |
| `Arena.close()` frees any C pointer | Arena only manages regions it owns or properly configured cleanups | Call the deallocator specified by the C API |
| Seeing **const char\*** and assuming UTF-8 and owned | `const` does not state charset/lifetime | Read the contract, check encoding and ownership |
| Copying struct fields consecutively without padding | Compilers have padding/alignment | Probe **sizeof/alignof/offsetof** |
| Correct struct `sizeof` means offsets must be right | Same size can still have different layout | Compare every field offset/type needed |
| Passing Java `String.length` as UTF-8 byte count | Java `length` counts UTF-16 units | Encode first, then take byte count |
| Letting C store an arena pointer past return | Use-after-free when arena closes | Use a long enough scope and free after draining |
| Using a callback after the stub's arena closes | Function pointer expires | Unregister/join callbacks before closing |
| C library is not thread-safe but using a shared `Arena` | Shared arena only allows multithreaded segment access | Synchronize and respect C thread affinity |
| Ignoring `errno`/status because `MethodHandle` exists | FFM does not automatically convert C errors to Java exceptions | Read the contract and check errors explicitly |
| Using C++ functions directly without checking ABI/mangling | Fails to find symbol or calls with wrong ABI | Create a tested **extern "C"** adapter |
| Generated binding from header = already safe | Headers do not fully describe lifetime/semantics | Review ownership, errors, callbacks, and versioning |

## 16. Checklist Before Putting FFM Bindings into Production

- [ ] Locked **JDK baseline** and verified native access settings (JDK 22+ for the API in this lesson).
- [ ] Have the **exact header and exact binary** for the target OS/CPU/ABI/compiler.
- [ ] Identified exported names/C++ name mangling and calling conventions.
- [ ] Every `FunctionDescriptor` accurately describes parameter count, return type, by-value/by-pointer, and variadics if any.
- [ ] For **long, size_t, wchar_t** and C typedefs: used ABI canonical layouts/probes, not inferred from Java types.
- [ ] For **struct/union/array**: verified size, alignment, field offsets, padding/packing, and endianness when needed.
- [ ] For every pointer: documented **length + unit + nullability + ownership + lifetime + deallocator**.
- [ ] Do not use `reinterpret` to fabricate bounds; know clearly when a C pointer can become invalid.
- [ ] Do not close an arena before native workers/callbacks finish using the pointer/stub.
- [ ] Every C function has its error model, failure state, and cleanup path verified.
- [ ] Buffer lengths and capacities guard against integer overflow, avoiding overflow/over-read/over-write.
- [ ] Confirmed encoding/terminator and handling of embedded NUL when converting Strings.
- [ ] Reviewed thread-safety/reentrancy, callback threads, unregister, and shutdown.
- [ ] Have smoke tests & ABI tests on each target release, toolchain, and native runtime.
- [ ] Have crash isolation and rollback strategy when upgrading the native library.

## 17. Self-Check Questions

**1. Why does the native Linker know the ABI yet still not automatically validate a `FunctionDescriptor`?**

**Answer:** The Linker knows how to **execute** a call per the ABI when given the declared layouts; symbols usually do not provide complete prototype information. The binding author must supply the exact layout of the actual C function.

**2. Why should C `long` on Windows x64 usually not be mapped with `ValueLayout.JAVA_LONG`?**

**Answer:** The LLP64 data model typically has 32-bit C `long`, whereas Java `long` is 64-bit. Use the ABI's canonical layout **long** or a wrapper with fixed-width types.

**3. A C function returns `void*`; FFM returns a `MemorySegment` with `byteSize` equal to 0. Does this mean C allocated 0 bytes?**

**Answer:** No. FFM may only know the address without knowing the size or lifetime. To read it, you need the actual size contract and proper `reinterpret`/target layout operations, still bearing the risk if the pointer is invalid.

**4. Why is `sizeof(struct)` not enough to access fields safely?**

**Answer:** Two layouts can have the same total size but different offsets or field types. You must verify alignment, `offsetof`, field types, and version/packing.

**5. When can `Arena.ofConfined` be closed immediately after a downcall?**

**Answer:** When the C API only **borrows the pointer during the synchronous call**, without storing the pointer or launching async callbacks that use that buffer after returning.

**6. Why does `const char*` not imply UTF-8, NUL-terminated, and borrowed?**

**Answer:** `const` only constrains modifying data through the pointer under the C contract. Charset, string termination, size, nullability, and ownership must be defined separately by the C documentation.

**7. Does using `jextract` eliminate the responsibility of managing memory ownership?**

**Answer:** No. Generated bindings can help represent types/layouts from headers, but do not automatically prove deallocators, pointer lifetimes, callback concurrency, or error semantics.

**8. If a C API takes `uint16_t*` and `item_count`, should Java pass `byteSize` as `item_count`?**

**Answer:** No. `item_count` is the number of `uint16_t` elements per the contract. You must compute the exact element count, check that the byte count is divisible by the element size, and ensure it does not exceed `size_t` capacity.

**9. Can FFM's `MemorySegment` bounds checks prevent C from writing past a buffer?**

**Answer:** Not guaranteed. C receives a raw address and can access outside the allocated region if the caller passes the wrong capacity or native code has a bug. Contracts, validation, and native diagnostics are required.

**10. In the demo, why does C export the `record_count_offset` function instead of Java assuming the offset is 4?**

**Answer:** Because C layout is determined by the compiler/ABI/packing. Probing from the **actual C binary** gives Java a verifiable value instead of guessing.

## Official Documentation

- [JEP 454 — Foreign Function & Memory API, finalized in JDK 22](https://openjdk.org/jeps/454).
- [Java SE 22 — java.lang.foreign package](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html).
- [Java SE 22 — Linker: ABI, canonicalLayouts, FunctionDescriptor, and safety considerations](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html).
- [Java SE 22 — MemorySegment: bounds, alignment, zero-length pointers, reinterpret](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html).
- [Java SE 22 — Arena: scope and lifetime](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html).
- [Java SE 22 — SymbolLookup and native library loading](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html).
- [JDK 24 Restricted Methods — Native access permissions](https://docs.oracle.com/en/java/javase/24/core/restricted-methods.html).

**Conclusion:** **FFM enforces the bridge that the declared ABI and layouts permit; it does not automatically know the entire specific ABI of a binary, descriptor correctness, pointer sizes, ownership, deallocators, lifetimes, encoding, callbacks, or error contracts.** To use FFM sustainably, combine **version-matched headers + ABI/probes from the C binary + accurate Java layouts/descriptors + verified ownership/lifetime + tests on real platforms**. When information is missing, add a C adapter/probe function instead of guessing.
