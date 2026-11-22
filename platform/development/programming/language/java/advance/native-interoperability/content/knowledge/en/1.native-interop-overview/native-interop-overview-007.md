# C Knowledge, Pointers, and Resource Management Before Practicing Java–Native

When Java calls native code via JNI or the Foreign Function & Memory (FFM) API, part of the work runs outside the JVM's usual guarantees. Java manages objects with a garbage collector (GC), checks array bounds, and throws exceptions; C manipulates addresses, buffer lengths, ABI-dependent data types, and resource lifecycles directly. A C bug such as accessing freed memory can corrupt data or cause the entire JVM process to terminate.

**Goals after this lesson:** be able to read and write small C snippets; understand `&`, `*`, arrays, pointers, and memory regions; determine who owns a resource and when it must be freed; recognize risks regarding length, strings, alignment, and ABI; and know how to apply these rules to JNI/FFM before writing actual bindings.

## 1. Mental Map When Crossing the Java/C Boundary

| Aspect | Regular Java | C/native |
| --- | --- | --- |
| Objects and lifecycle | GC manages memory of still-reachable objects | Dynamically allocated regions require ownership and deallocation conventions; many non-memory resources must also be closed |
| Arrays | `array.length`, index checking | Pointers usually do not carry length; the programmer must pass `length` and check bounds |
| References | References managed by the JVM | A pointer is a value representing a platform-specific location/address; it can be null, dangling, or invalidated |
| Strings | `String` is an immutable, Unicode-based sequence | `char *` usually points to a byte sequence terminated by `'\0'`; encoding must be specified |
| Types and layout | `int` is always 32 bits, `long` is always 64 bits | The size of `int`, `long`, pointers, and `struct` layout depend on the platform/ABI |
| Errors | Exceptions; most access errors are controlled by the JVM | Error codes, `NULL`, `errno` when specified by the API; invalid memory access can cause undefined behavior |

**Central rule:** for every piece of data crossing the boundary, you must know its **type and layout**, **valid address/length**, **ownership**, **lifetime**, **error handling**, and **which side is responsible for cleanup**. Do not infer that a pointer is safe just because Java holds a reference to a related object.

## 2. Minimum C Foundation Needed to Read Code

### 2.1. Program Structure, Types, and Expressions

A C file typically consists of `#include` directives, type/function declarations, function definitions, and statements. Example:

~~~c
#include <stdint.h>
#include <stddef.h>

int64_t add_values(const int32_t *values, size_t count) {
    int64_t total = 0;
    for (size_t i = 0; i < count; ++i) {
        total += values[i];
    }
    return total;
}
~~~

The function takes the address of the first element and the element count, then returns the sum. This is an **illustrative snippet**, not a standalone runnable program; the caller must provide `values` pointing to at least `count` valid `int32_t` elements. For a valid array with at most `INT32_MAX` `int32_t` elements, the sum still fits within `int64_t`; however, a general API should still clearly document the data domain and perform necessary error checks. The standalone runnable example in Section 8 also checks the pointer and addition overflow.

Important constructs:

- `if/else`, `for`, `while`, `return`, and `{ ... }` blocks control flow; local variables usually have a lifetime until the block ends.
- `T x` declares a value of type `T`; `T *p` declares a pointer to `T`; `T a[n]` declares an array of `n` elements.
- `struct` groups fields, `enum` represents named integer constants; `typedef` creates a type alias.
- `const` forbids modification **through that access path**; it does not allocate, keep alive, or free memory by itself.
- `sizeof x` gives the size in **C bytes**; use `sizeof *p` when allocating a region to hold the type `p` points to.
- `size_t` is used for sizes/element counts (`sizeof` returns `size_t`), printed with `%zu`; `ptrdiff_t` is used for valid pointer differences.
- `int32_t`, `uint8_t`, `int64_t` from `<stdint.h>` express the exact bit width when the platform has the corresponding types. `<inttypes.h>` provides print macros such as `PRId64`.

In Java, `int` and `long` have fixed sizes. In C, do not assume `sizeof(int) == 4`, `sizeof(long) == 8`, or `sizeof(void *) == 8`. Even on 64-bit machines, `long` is typically 32 bits on Windows (LLP64) but 64 bits on many Unix systems (LP64). You must also distinguish signed/unsigned: negative numbers converted to unsigned and size arithmetic can produce very large values; signed integer overflow in C is undefined behavior. When multiplying `count * sizeof(T)`, check for overflow **before** multiplying.

### 2.2. Values, Addresses, Pointers, and Dereferencing

~~~c
int score = 10;
int *ptr = &score;   // & takes the address of score
*ptr = 15;           // * dereferences and assigns through pointer
int copy = *ptr;     // copy == 15; score == 15
~~~

`ptr` holds a location where an `int` can be accessed. `*ptr` reads/writes the object at that location, provided the address is valid, still alive, of the right type, and properly aligned. Although the syntax looks the same, the two `*` tokens have different roles: in a declaration it means "pointer to"; in an expression it means "read/write the pointed-to object".

~~~c
int values[3] = {4, 5, 6};
int *begin = values;       // values usually converts to &values[0]
int second = *(begin + 1); // equivalent to values[1], equal to 5
~~~

Pointer arithmetic steps in **element units**, not byte counts: `begin + 1` advances by `sizeof(int)` bytes in the example. Only perform pointer arithmetic within the same array object (or exactly one position past the last element); do not dereference a "one past end" pointer. Both `values[3]` and `*(begin + 3)` are out-of-bounds reads. An address is not "valid" simply because it is non-`NULL`.

Three easily confused forms of `const`:

~~~c
const int *read_only_value = &score; // do not modify score through this pointer
int *const fixed_pointer = &score;   // do not change the target of this pointer
const int *const both = &score;       // both restrictions above
~~~

`void *` is a data pointer without an associated element type; it cannot be dereferenced directly or used for pointer arithmetic in standard C. `T **` is a pointer to a pointer, commonly used when a function needs to modify the caller's pointer. `NULL` represents a null pointer; check for null before dereferencing, but a null check does **not** verify length, ownership, or lifetime.

### 2.3. Arrays Do Not Carry Their Size When Passed to Functions

A parameter declaration `int x[]` in a function is equivalent to a pointer parameter `int *x`, without `length`. `sizeof(x)` inside the function returns the size of the pointer, **not** the size of the caller's array. Therefore:

~~~c
void process(const int *data, size_t length);
~~~

The caller must ensure `data` has at least `length` readable elements (or both sides agree that `data == NULL` is valid when `length == 0`). In native code, pass the pointer **together with the length** as an inseparable pair; use `size_t` for C element counts, and check types when converting from `jsize`, `jlong`, or Java lengths.

## 3. Memory Lifecycle: Being Alive Matters More Than Having an Address

| Memory/Resource Type | Example | Lifetime and Cleanup |
| --- | --- | --- |
| Automatic storage | `int local;`, `int a[4];` inside a block | Normally ends lifetime when leaving the block/call; must not `free(&local)` |
| Static storage | `static int cache;`, global variables | Exists for the entire program runtime; requires synchronization when shared |
| Dynamic allocation | `malloc`, `calloc`, `realloc` | Exists until `free` per contract; not automatically freed by Java GC |
| OS/library handle | `FILE *`, socket, file descriptor, native library handle | Has `fclose`, `close`, or dedicated release functions |
| Data borrowed from JVM | `GetIntArrayElements`, `GetStringUTFChars` | Valid only per JNI contract until the corresponding `Release...` |
| Foreign memory under FFM | `MemorySegment` with scope managed by `Arena` | Access rights and lifetime are tied to the scope/arena; must not be used after closing the scope |

"Stack" and "heap" are common informal terms for visualization, but the C standard describes **storage duration** and does not require every automatic variable to reside on a physical stack. The key point to retain is the usage lifetime and who has the authority to end it.

### 3.1. Dynamic Allocation and Deallocation

~~~c
size_t count = 100;
int32_t *buffer = NULL;

if (count > SIZE_MAX / sizeof *buffer) {
    /* count * sizeof *buffer will overflow: report error */
} else {
    buffer = malloc(count * sizeof *buffer);
    if (buffer == NULL) {
        /* handle out-of-memory */
    } else {
        /* buffer[0] ... buffer[count - 1] are valid */
        free(buffer);
        buffer = NULL; // avoid accidentally reusing this pointer variable itself
    }
}
~~~

This is an illustrative snippet; `#include <stdint.h>` and `#include <stdlib.h>` are required in an actual program. `malloc` allocates **uninitialized** bytes; only read after writing valid values. `calloc(n, size)` initializes bytes to 0 (still requires checking the result/overflow per API), though zero bytes do not automatically suit every data layout. For an element count of 0, handle it separately because `malloc(0)` has implementation-defined result behavior.

Never call `free` on the address of a local variable, an element in the middle of an allocation, memory held by Java, or a pointer owned by another API. `free(NULL)` is valid. Calling `free` twice on the same allocation, dereferencing after `free`, reusing an alias pointer after freeing, or forgetting `free` causes serious bugs. Setting one pointer variable to `NULL` **does not invalidate aliases** pointing to the freed region.

**Safe resizing with `realloc`:**

~~~c
void *tmp = realloc(buffer, new_byte_count);
if (tmp == NULL) {
    /* When new_byte_count > 0, the old allocation still exists and must be freed later */
} else {
    buffer = tmp; // allocation may have moved to a different address
}
~~~

Do not assign directly `buffer = realloc(buffer, ...)`: if it fails, you lose the address that needs to be freed. This snippet assumes `buffer` is a live allocation created by a compatible allocator, `new_byte_count > 0`, and the size calculation has already been checked; avoid using `realloc(ptr, 0)` because its semantics are not a good foundation for portable code. After a successful `realloc`, old alias pointers must not be used.

### 3.2. Ownership and Borrowed Pointers

Every native API should clearly answer four questions: **who creates? who owns? who may borrow? who frees and with which function?**

- **Owned:** the caller receives ownership and must call the exact destructor function (`free`, `destroy_handle`, `CloseHandle` depending on the API) on all exit paths.
- **Borrowed:** the caller only reads/writes according to granted permissions; does not free it. The resource must remain alive for the entire duration of the borrow.
- **Transferred:** ownership moves from A to B; A must stop using or freeing it according to the transfer contract.
- **Shared:** multiple parties can access it; there must be reference counting rules, locks, or another lifetime/synchronization mechanism. Multiple pointers to the same address **do not automatically create shared ownership**.

For example: a C function returning `char *` might return a buffer the caller must `free`, an internal buffer the caller must not `free`, or a pointer valid only until the next call. The `char *` signature **cannot describe** ownership; reading and documenting the API contract is mandatory.

### 3.3. Cleanup on Every Error Path

C does not have `try/finally` or automatic destructors like some other languages. With multiple resources, the `goto cleanup` convention helps avoid missing a deallocation step:

~~~c
int run_task(void) {
    int status = -1;
    FILE *file = fopen("input.bin", "rb");
    if (file == NULL) return -1;

    unsigned char *buffer = malloc(1024);
    if (buffer == NULL) goto cleanup;

    /* read/process; if it fails, can goto cleanup */
    status = 0;

    free(buffer);
cleanup:
    fclose(file);
    return status;
}
~~~

This is an illustrative snippet of the cleanup pattern, requiring `#include <stdio.h>` and `#include <stdlib.h>`; no actual I/O is performed. In code with multiple exit paths, arrange corresponding cleanup labels so every initialized resource is freed exactly once, in reverse order of acquisition when dependencies exist. Another approach is splitting into small functions with explicit returns; the goal is to be able to verify all error paths.

## 4. Dangling Pointers, Overflow, and Undefined Behavior

Types of bugs to identify before calling native code:

1. **Null pointer dereference:** `p == NULL` yet still reading `*p`.
2. **Uninitialized/wild pointer:** dereferencing before assigning a valid address; or using uninitialized `malloc` bytes.
3. **Dangling pointer / use-after-free:** the memory region's lifetime has ended; holding the address is useless.
4. **Out-of-bounds:** reading/writing outside the array, confusing element count with byte count, using `strlen` on a buffer missing a terminator.
5. **Double-free / invalid-free / memory leak:** freeing from the wrong source or forgetting to free.
6. **Signed overflow, size overflow, truncation:** converting `jlong` to `int`, multiplying `count * size` or adding offsets without checking.
7. **Misalignment / incorrect type punning:** casting `char *` to `int64_t *` and dereferencing an insufficiently aligned address; violating effective type/strict aliasing.

**Undefined behavior (UB)** means C guarantees no outcome; the program might appear to run correctly, crash, or be optimized by the compiler under the assumption that no UB exists. A `try/catch` in Java cannot fix native code that has already corrupted memory. For untrusted data, check pointers/null, length, capacity, multiplication/addition, and return values **before** each operation.

`memcpy(dst, src, n)` copies **n bytes**, and is only safe when both regions contain at least `n` valid bytes and do not overlap; for regions that may overlap, use `memmove`. Do not infer capacity from a pointer. When an API takes `void *buffer, size_t bytes`, the unit is bytes; when it takes `int32_t *buffer, size_t elements`, the unit is elements.

## 5. Strings, Byte Buffers, and Unicode at the Java/Native Boundary

A typical C string is a sequence of `char` terminated by a NUL byte `'\0'`. For example, `char name[] = "Java";` occupies at least 5 C bytes consisting of 4 ASCII characters and NUL. `strlen(name)` returns the number of bytes before the first NUL; it does not know capacity and will read out of bounds if the terminator is missing. A binary blob may contain NUL in the middle, so **do not** use `strlen` to compute blob length. For binary data, pass a (`pointer`, `byte_length`) pair.

Java `String` is based on Unicode; a Java `char` is a UTF-16 code unit. In C, `char` is a C byte, not equivalent to a Unicode character. UTF-8 has variable byte length; the number of code points, Java `char`s, and UTF-8 bytes often differ. You must specify the encoding when converting and handle NUL in the data.

**JNI has two common string paths:**

- `GetStringChars` returns `jchar`s (UTF-16 code units) and pairs with `ReleaseStringChars`.
- `GetStringUTFChars` returns a string in JNI's **Modified UTF-8 (MUTF-8)**, and must use `ReleaseStringUTFChars`; MUTF-8 is not entirely standard UTF-8 (for example, in how U+0000 and supplementary characters are represented). Do not automatically pass that result into a protocol requiring standard UTF-8.

`const char *` does not mean the pointer always points to a valid string or lives forever. A native API that returns UTF-8 must specify who creates/frees the buffer, its byte length, whether there is a NUL terminator, and how encoding errors are reported. When receiving a buffer from Java, avoid holding onto that pointer past the borrow lifetime.

## 6. Layout, Alignment, Endianness, and ABI

The ABI (Application Binary Interface) defines how functions are called and data is represented at the machine level: type sizes/alignment, parameter passing/returning, struct layout, symbol names, and calling conventions. The same source code can have different layouts on two operating systems or architectures.

~~~c
#include <stddef.h>
#include <stdint.h>

struct Packet {
    uint8_t tag;
    uint32_t length;
};

size_t bytes = sizeof(struct Packet);
size_t length_offset = offsetof(struct Packet, length);
~~~

Do not assume `bytes == 5` or `length_offset == 1`; the compiler typically inserts **padding** to satisfy alignment. Do not write a `struct` directly with `fwrite` and treat its bytes as a stable network wire format: padding, endianness, and ABI can differ. Define the interchange layout byte-by-byte/field-by-field, use fixed-width sizes, and specify byte order (network byte order is typically big-endian).

For example, the 32-bit number `0x01020304` has byte order `01 02 03 04` on big-endian and `04 03 02 01` on little-endian. When reading native memory with Java FFM or `ByteBuffer`, you must select the right `ByteOrder`; when defining a `MemoryLayout`, explicitly account for alignment/padding. Arbitrarily casting a pointer to another type does not solve ABI issues and can create UB; to read byte representations, use `unsigned char *` or `memcpy`, provided the memory region is valid.

**Mappings to remember when working with JNI:**

| Java / JNI | Meaning | What to Avoid |
| --- | --- | --- |
| Java `int` / JNI `jint` | 32-bit integer value | Assuming every C `int` on every ABI has the same layout |
| Java `long` / JNI `jlong` | 64-bit integer value | Using C `long` as a substitute across all systems |
| Java `char` / JNI `jchar` | 16-bit unsigned UTF-16 code unit | Casting to C `char` and treating it as a single-byte character |
| Java `boolean` / JNI `jboolean` | JNI boolean | Inferring size/layout from C `bool` |
| `jobject`, `jarray`, `jstring` | JNI reference/handle managed by the JVM | Casting to `T *` and accessing as a C pointer |
| `jint *` after `GetIntArrayElements` | Borrowed pointer to JNI data within the allowed lifetime | Keeping the pointer after `ReleaseIntArrayElements` |

Do not pass a `struct` "by value" across FFI without confirming the convention/layout of the exact target ABI. With unions/bitfields/compiler packing, the risk of mismatch is even greater. Native types used as handles should be represented as opaque handles with create/destroy APIs, rather than forcing Java to guess internal layouts.

## 7. Resource Boundaries in JNI and FFM

### 7.1. JNI: Borrowed Data Must Be Returned With a Release Pair

In JNI, `Get<Type>ArrayElements` and `GetString...Chars` functions may return a pointer to a copy or a pinned region; the caller **must not assume** which one. On success, you must call the corresponding `Release...` function, even when only reading. `JNI_ABORT` in `ReleaseIntArrayElements` requests skipping copy-back when read-only; it does not mean skipping the release.

`GetPrimitiveArrayCritical`/`ReleasePrimitiveArrayCritical` has stricter constraints because it can affect the GC: keep the critical section short, avoid blocking I/O, and avoid disallowed JNI calls inside the critical section. Read the API documentation carefully before using it; do not replace every `GetArrayElements` with Critical just to "optimize".

JNI local references are usually only valid within the current native call/frame. If you need to keep a Java object after the native function returns, use `NewGlobalRef` or an equivalent reference mechanism, then `DeleteGlobalRef` when no longer needed; also address lifetime/thread-safety. `JNIEnv *` is thread-bound; **do not** cache it for use on another thread. Self-created native threads wishing to call the JVM must attach via the JNI Invocation API, then detach according to the contract.

When a JNI API reports an error by returning `NULL` or leaving a pending Java exception, clean up borrowed resources before returning; do not continue calling arbitrary JNI APIs while an exception is pending. When you need to throw an error proactively, use `ThrowNew` with the appropriate exception class and return immediately after cleaning up resources.

### 7.2. FFM: Addresses Still Need Valid Scopes and Layouts

FFM uses concepts such as `MemorySegment` (memory region), `Arena` (lifetime management), `MemoryLayout` (data interpretation), and `Linker` (linking native functions), depending on the JDK version's API support. These abstractions help constrain access by scope and layout; they **do not automatically guarantee** that the native library respects buffer length, ownership, calling conventions, or thread safety. If C retains an address after the arena is closed, native code may dereference an invalidated region.

Do not mix allocators/deallocators: regions allocated by `malloc` must use a compatible deallocation mechanism; regions allocated by a library need the library's exact `library_free` function; regions managed by an arena are terminated by the arena mechanism. Java GC does not replace closing handles/sockets/native allocations. If native code stores a callback pointer or user-data pointer, you must keep the callback/segment and underlying data alive **until native confirms it has stopped using them**.

### 7.3. Pre-Call Contract Table

| Question | Example of Required Answer |
| --- | --- |
| What units are the pointer and size measured in? | `const uint8_t *bytes` + `size_t byte_count`, or `int32_t *items` + `size_t element_count` |
| Who owns the buffer? | "caller allocates, callee only borrows during the call" / "callee allocates, caller calls `library_free`" |
| Can the pointer be retained after returning? | "no" / "yes, until `release_callback` returns and the thread stops" |
| Does native modify the data? | "read-only"; `const` in C expresses intent but does not replace JNI/FFM validation |
| What happens on invalid input or out-of-memory? | return value, exception, error code, `errno` if specified by the API |
| Are any threads/callbacks shared? | which threads may call, synchronization, JNI attach/detach, whether scope supports multithreaded access |

## 8. Standalone C Example: Controlled Pointer Usage and Buffer Ownership

Save the following code as `native_basics.c`. The example runs on its own without JNI; it demonstrates size checking, allocation, borrowing a `const` pointer, summing, and single-point cleanup.

~~~c
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static bool sum_i32(const int32_t *data, size_t count, int64_t *result) {
    if (result == NULL || (count != 0 && data == NULL)) {
        return false;
    }

    int64_t total = 0;
    for (size_t i = 0; i < count; ++i) {
        int64_t value = data[i];
        if ((value > 0 && total > INT64_MAX - value) ||
            (value < 0 && total < INT64_MIN - value)) {
            return false;
        }
        total += value;
    }
    *result = total;
    return true;
}

int main(void) {
    const size_t count = 4;
    int32_t *items = NULL;
    int64_t total = 0;
    int status = EXIT_FAILURE;

    if (count > SIZE_MAX / sizeof *items) {
        fputs("size overflow\n", stderr);
        return EXIT_FAILURE;
    }

    items = malloc(count * sizeof *items);
    if (items == NULL) {
        fputs("allocation failed\n", stderr);
        return EXIT_FAILURE;
    }

    for (size_t i = 0; i < count; ++i) {
        items[i] = (int32_t)((i + 1) * 10);
    }

    const int32_t *borrowed_view = items;
    if (!sum_i32(borrowed_view, count, &total)) {
        fputs("invalid data or sum overflow\n", stderr);
        goto cleanup;
    }

    printf("count=%zu\n", count);
    printf("sum=%" PRId64 "\n", total);
    printf("second=%" PRId32 "\n", borrowed_view[1]);
    status = EXIT_SUCCESS;

cleanup:
    free(items);
    items = NULL;
    return status;
}
~~~

Compile with GCC/Clang supporting C11:

~~~sh
cc -std=c11 -Wall -Wextra -Wpedantic -O0 -g native_basics.c -o native_basics
./native_basics
~~~

On Windows, use an environment with GCC/Clang and run the corresponding executable (for example `.\native_basics.exe`). On the success path, stdout is exact:

~~~text
count=4
sum=100
second=20
~~~

`items` is an **owned pointer**; `borrowed_view` is a read-only alias, must not be `free`d separately, and becomes invalid after `free(items)`. `&total` is the out-parameter address, and `result` in `sum_i32` is only used while the function is running. The guard `count > SIZE_MAX / sizeof *items` protects the size multiplication; the guard inside the loop protects `int64_t` addition. Printing uses `PRId64`/`PRId32` instead of guessing format specifiers by ABI.

If AddressSanitizer/UndefinedBehaviorSanitizer is available with a supported compiler, you can compile this exercise with `-fsanitize=address,undefined -fno-omit-frame-pointer` and intentionally test errors in an isolated sandbox. Sanitizers help find bugs but do not make native code memory-safe; modes/support vary on Windows and across compilers.

## 9. Small Java 17 + JNI Example: Borrowing a Java Array Properly

This example directly connects the rules above to JNI, using **one** native method to sum an `int[]` array. Create the file `NativeSum.java`:

~~~java
package demo;

public final class NativeSum {
    static {
        System.loadLibrary("nativesum");
    }

    public static native long sum(int[] values);

    public static void main(String[] args) {
        System.out.println(sum(new int[] {10, 20, 30, 40}));
    }
}
~~~

Running `javac -h .` will generate the header `demo_NativeSum.h` with the exact JNI signature. Create the file `nativesum.c` in the same directory:

~~~c
#include "demo_NativeSum.h"

JNIEXPORT jlong JNICALL
Java_demo_NativeSum_sum(JNIEnv *env, jclass ignored, jintArray values) {
    (void)ignored;

    if (values == NULL) {
        jclass exception_class =
            (*env)->FindClass(env, "java/lang/NullPointerException");
        if (exception_class != NULL) {
            (*env)->ThrowNew(env, exception_class,
                             "values must not be null");
            (*env)->DeleteLocalRef(env, exception_class);
        }
        return 0;
    }

    jsize length = (*env)->GetArrayLength(env, values);
    jint *elements = (*env)->GetIntArrayElements(env, values, NULL);
    if (elements == NULL) {
        return 0; // failed; check JNI pending exception
    }

    jlong total = 0;
    for (jsize i = 0; i < length; ++i) {
        total += (jlong)elements[i];
    }

    (*env)->ReleaseIntArrayElements(env, values, elements, JNI_ABORT);
    return total;
}
~~~

On **Linux** with JDK 17+ and a C compiler (setting `JAVA_HOME` to point to the same JDK in use), run in the directory containing the two files:

~~~sh
javac -h . -d . NativeSum.java
cc -std=c11 -Wall -Wextra -Wpedantic -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  nativesum.c -o libnativesum.so
java -Djava.library.path=. demo.NativeSum
~~~

Stdout of the example:

~~~text
100
~~~

On macOS, use the `darwin` include and build `libnativesum.dylib` with the appropriate shared library flags; on Windows, use the `win32` include and build `nativesum.dll` with the appropriate toolchain. The library name must follow the convention of `System.loadLibrary("nativesum")`. Multi-platform builds require configuring the corresponding toolchain/JDK headers; do not use the exact Linux command line for every OS.

Explanation of ownership in the JNI call:

1. `values` is a **JNI handle**, not a `jint *`. The JVM still controls the array and its representation.
2. `GetArrayLength` gets the **element** count; `GetIntArrayElements` gives a temporary pointer that may be a copy or pinned storage.
3. While the borrow is valid, the loop only reads `elements[i]` with `0 <= i < length`. The sum is safe in `jlong` because `length` is `jsize` and each element is a 32-bit `jint`; even the largest positive bound does not exceed the `jlong` range.
4. `ReleaseIntArrayElements(..., JNI_ABORT)` releases the borrow without copying data back to Java, which is appropriate because elements were not modified. If data is modified and needs to be returned to Java, an appropriate release mode must be chosen.
5. When `GetIntArrayElements` fails, do not dereference `NULL`; the API may have left a pending exception (e.g., out of memory). When `values == NULL`, the code proactively throws `NullPointerException`.

The example uses a simple access method to illustrate ownership; for very large arrays, measure pin/copy costs and consider `GetIntArrayRegion`, direct buffers, or FFM for the specific problem. Do not cache `elements` across multiple Java calls. Do not `free(elements)`, because this is not an allocation created by your `malloc`.

## 10. Common Bugs and How to Fix Them

| Bug | Why It Is Wrong | Correct Approach |
| --- | --- | --- |
| Unchecked `malloc(count * sizeof(T))` | `size_t` multiplication can wrap into a small allocation | Check `count <= SIZE_MAX / sizeof(T)` before multiplying |
| `return pointer_to_local;` | Automatic variable ends its lifetime when the function returns | Caller provides buffer, or return an owned allocation with a clear free function |
| `free(pointer_from_GetStringUTFChars)` | Pointer borrowed from JNI, does not belong to caller's C allocator | Call the paired `ReleaseStringUTFChars` |
| `(int *)jintArray_handle` | JNI reference is not a pointer to elements | Use JNI array access API, `Release...`, and length |
| `strlen(bytes)` on a binary buffer | NUL in the middle of payload truncates wrongly; missing NUL can read out of bounds | Pass length explicitly |
| Calling `free` then continuing to use an alias | Another pointer still points to the dead allocation | Unify ownership/lifetime; end all borrows before freeing |
| Assuming `sizeof(struct)` equals sum of fields | Padding/alignment may add bytes | Verify `sizeof`, `offsetof`, ABI, and serialize in a defined format |
| Using `JNIEnv *` on another thread | JNI environment pointer is per-thread | The corresponding thread attaches and obtains its own env |
| Native retains pointer after arena closes | Memory segment's lifetime has ended | Design scope/ownership to span all native tasks |
| Missing cleanup on mid-way error | Leaks or unreleased locks/handles | Write a single cleanup path, verify each success/failure branch |

## 11. Checklist Before Writing a Real Native Call

- **Types and ABI:** what bit width is each parameter/return value? Signed or unsigned? Pointer or handle? Are calling convention, alignment, endianness, and layout confirmed?
- **Memory bounds:** is length measured in bytes or elements? Are checked conversions and checked multiplications in place? Can the pointer be null? Does the buffer have sufficient capacity and is it still alive?
- **Ownership:** which side creates, which side borrows, which side destroys? Which exact release/close function is used? Can native retain the pointer or callback after returning?
- **Strings:** UTF-8, UTF-16, or Modified UTF-8? Is there a NUL terminator? Can there be embedded NULs? Are length/capacity passed separately?
- **Errors:** where are return codes and pending exceptions checked? Do all error paths clean up everything borrowed/allocated? Is there a risk of returning uninitialized data?
- **Multithreading:** is the resource accessed concurrently? Which thread does the JNI environment belong to? How long do callbacks and scopes live? Is there a race when Java and C modify the buffer simultaneously?
- **Testing:** test empty input, null per contract, boundary lengths, Unicode characters, allocation failures, and repeated operations; test on the exact target OS/CPU/JDK/ABI, using sanitizers or memory checkers when supported.

**Readiness criterion for practice:** when looking at a prototype like `int native_process(const uint8_t *input, size_t input_len, uint8_t **output, size_t *output_len)`, you must be able to ask: which buffer does the caller own, which pointer is only borrowed, who allocates `*output`, which function frees it, what units are the lengths in, how are errors reported, and when does the pointer become invalid. If the library documentation does not answer these questions, there is not enough information to write safe Java bindings yet.