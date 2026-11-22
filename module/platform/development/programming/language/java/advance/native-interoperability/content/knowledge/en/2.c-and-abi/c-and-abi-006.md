# Pointers, Double Pointers, Contiguous Arrays, and Function Pointers in C/ABI

## 1. Objectives and Why This Matters in Java Native Interoperability

When Java calls a native library via JNI or the Foreign Function & Memory API (FFM), a C signature does not merely describe “data types.” It also specifies **which address is passed**, what that memory region contains, how to read it according to the ABI's size/alignment rules, which side owns the memory, and whether native code can call a function back. The differences among `T *`, `T **`, `T [N]`, `T (*)[N]`, and function pointers are the source of many compilation errors, crashes, and memory corruption bugs.

After this lesson, you should be able to:
- Read pointer declarations accurately and distinguish **a pointer's value (address)** from **the object it points to**.
- Explain double pointers, output parameter cases, and how to distinguish them from two-dimensional arrays.
- Identify contiguous memory regions, pointer arithmetic strides, array lengths, and the type of each address-taking operation.
- Read/declare and pass function pointers; understand callbacks crossing the ABI boundary.
- Design a Java–C contract with complete information about **type, size, length, ownership, lifetime, alignment, and calling convention**.

The primary scope is C and the ABI. The C examples use C11; the Java section shows the corresponding representation when integrating with native code.

## 2. Foundational Model: Objects, Addresses, Pointers, and Dereferencing

Consider:

~~~c
int value = 42;
int *p = &value;
~~~

- `value` is an object of type `int`; `&value` is its address, of type `int *`.
- `p` is **a separate variable**, of type `int *`, holding the address value of `value`.
- `*p` accesses the `int` object at the address that `p` represents. `*p = 7;` changes `value` to `7`.
- `&p` is the address of **the pointer variable** `p`; it has type `int **`, which is completely different from `p`.

Conceptual model (addresses are for illustration only, not guaranteed values):

~~~text
value (int)            p (int *)
address 0x1000         address 0x2000
value 42       <------- content 0x1000

*p  -> read/write value
&p  -> 0x2000 (address where p itself is stored)
~~~

Common syntax:

| Expression | Type (in example) | Meaning |
|---|---|---|
| `value` | `int` | Value of the object |
| `&value` | `int *` | Address of the object |
| `p` | `int *` | Address value stored in the pointer |
| `*p` | `int` (lvalue) | The pointed-to object |
| `&p` | `int **` | Address of the pointer variable |
| `**pp`, with `int **pp = &p` | `int` (lvalue) | The final object after two dereferences |

You can set `p = NULL;` to represent “not pointing to a valid object/function.” **Never dereference** `NULL`. An uninitialized pointer holds an indeterminate value; never read it or use it as a valid address. A pointer pointing to a local variable after the variable's lifetime ends, or to a memory region after `free`, becomes a dangling pointer.

### Where Does `const` Apply?

~~~c
const int *read_only_value = &value;  // Cannot modify *read_only_value through this variable.
int *const fixed_pointer = &value;    // Cannot assign fixed_pointer to another address.
const int *const fixed_read_only = &value; // Both restrictions.
~~~

`const int *` and `int const *` are equivalent. `const` on data does not mean “the memory is always immutable across the entire program”; it restricts modifications through a const-qualified access path. Converting `int **` to `const int **` is not implicitly allowed by C, because doing so would break `const` safety.

## 3. Pointers and Address Arithmetic on Arrays

~~~c
int numbers[] = {10, 20, 30, 40};
int *p = numbers;       // In this expression, numbers converts to &numbers[0].
int second = *(p + 1);  // 20
int third = p[2];       // 30, equivalent to *(p + 2).
~~~

If `p` has type `T *`, `p + i` advances by **i elements of type `T`**, not i bytes. On a platform where `sizeof(int) == 4`, `p + 1` is typically 4 bytes past `p`. Pointer arithmetic is defined when both pointers belong to the same array object (or the position **one past the last element** according to C rules); you may form a one-past pointer, but **must not dereference** it. Going beyond that range is undefined behavior.

A C array has its elements placed contiguously in memory; **a pointer does not store its own length**. For an actual array in the same scope:

~~~c
int a[] = {4, 5, 6};
size_t count = sizeof a / sizeof a[0]; // 3
~~~

After passing `a` to a function with parameter `int *p`, `sizeof p` only gives **the size of the pointer**, not the number of elements. Native APIs typically need to pass `(pointer, length)` separately.

Important exceptions to array-to-pointer conversion include `sizeof a` and `&a`. For `int a[3]`:
- In most expressions, `a` converts to `int *` pointing to `a[0]`.
- `&a` has type `int (*)[3]`: a pointer to **the entire array of three ints**.
- `sizeof a` gives the size of all three elements; `sizeof &a` gives the size of one pointer.
- An array cannot be assigned as a whole using `=` like a pointer variable.

## 4. Double Pointers (`T **`): An Address Pointing to a Storage Slot for an Address

`int **pp` means `pp` points to an object of type `int *`. Therefore:

~~~c
int x = 10;
int y = 20;
int *p = &x;
int **pp = &p;

**pp = 11;  // Modifies x, because *pp is p and **pp is *p.
*pp = &y;   // Modifies p itself so that it points to y.
**pp = 21;  // Modifies y.
~~~

The crucial difference: when a function receives `int *p` by value, assigning `p = ...` inside the function only changes **the copy of the pointer**. If you want the function to change the caller's pointer, pass the address of the pointer variable via `int **`.

A **standalone** C11 example that also illustrates a one-dimensional array and a pointer to a row of a two-dimensional array:

~~~c
// File: PointerBasics.c
#include <stdio.h>

static void reseat(int **slot, int *new_target) {
    if (slot != NULL) {
        *slot = new_target;
    }
}

int main(void) {
    int a = 10;
    int b = 20;
    int *p = &a;
    int **pp = &p;

    **pp = 11;
    reseat(pp, &b);
    *p = 21;

    int values[] = {3, 5, 7, 9};
    int matrix[2][3] = {{1, 2, 3}, {4, 5, 6}};
    int (*row)[3] = matrix;

    printf("a=%d, b=%d\n", a, b);
    printf("values[2]=%d, *(values+2)=%d\n",
           values[2], *(values + 2));
    printf("row[1][2]=%d\n", row[1][2]);
    return 0;
}
~~~

Compile and run (GCC/Clang, C11):

~~~sh
cc -std=c11 -Wall -Wextra -pedantic PointerBasics.c -o pointer-basics
./pointer-basics
~~~

Exact output:

~~~text
a=11, b=21
values[2]=7, *(values+2)=7
row[1][2]=6
~~~

### `T **out` in Native APIs

A common signature pattern:

~~~c
// Illustrative interface only, not a complete implementation.
int create_buffer(size_t count, unsigned char **out_data);
void release_buffer(unsigned char *data);
~~~

`out_data` points to **a pointer-holding slot** provided by the caller. The C function can allocate a buffer and store the new address into `*out_data`; the caller must pass `&buffer` if `buffer` is an `unsigned char *` variable. The API documentation must state clearly: the error-return convention, the value of `*out_data` on failure, whether `NULL` is accepted, the actual allocated size, who calls `release_buffer`, and whether the address may be retained across subsequent calls. Java FFM represents “a slot holding an address” with a native region having an address layout; JNI typically has to provide a native wrapper function rather than treating a Java array as `T **`.

**Do not confuse `T **` with “a pointer to two dimensions.”** These are two different memory structures.

## 5. Three Types That Look Similar but Have Completely Different Layouts

With `int m[2][3] = {{1,2,3}, {4,5,6}};`, C stores six `int` values contiguously in **row-major** order:

~~~text
m[0][0] m[0][1] m[0][2] | m[1][0] m[1][1] m[1][2]
    1       2       3    |     4       5       6
[      row int[3]      ] [      row int[3]      ]
~~~

When using the name `m` in most expressions, the converted type is `int (*)[3]` (the address of the first row), **not `int **`. Therefore `int (*row)[3] = m;` is correct, while `int **wrong = m;` is type-incompatible and must not be cast to “fix” it.

Comparison:

| Declaration | Read from inside out | Organization |
|---|---|---|
| `int *p` | `p` is a pointer to `int` | One address pointing to an `int` |
| `int **pp` | `pp` points to an `int *` | Address pointing to a slot storing an address |
| `int a[3]` | `a` is an array of 3 `int`s | Three contiguous integers |
| `int *a[3]` | `a` is an array of 3 `int *` pointers | Three contiguous address slots; target data may be scattered |
| `int (*p)[3]` | `p` points to an array of 3 `int`s | One address; incrementing `p` by one advances by one row of 3 `int`s |
| `int (*f)(int, int)` | `f` points to a function taking 2 `int`s, returning `int` | Function address, not an `int` data region |

Example with **an array of pointers**:

~~~c
int x = 1, y = 2, z = 3;
int *slots[3] = {&x, &y, &z};
int **first_slot = slots; // slots converts to a pointer to slots[0].
~~~

Here `slots` genuinely has elements of type `int *`, so converting to `int **` is appropriate. However, you cannot infer that the three objects `x`, `y`, `z` are contiguous.

An `int matrix[2][3]` cannot be interpreted through `int **` because the machine will read **the integer values in the row** as if they were **the address of a row**, causing a fault or undefined behavior. If a dynamic row table `int **rows` is needed, you usually must allocate the pointer table and each row region (or allocate one contiguous buffer and assign each `rows[i]`), and design deallocation accordingly.

### Row/Column Indexing and Flattening Data

Two-dimensional array access `matrix[i][j]` is equivalent to `*(*(matrix + i) + j)` when indices are valid. For dynamic 2D data where the ABI requires **a flat buffer**, you can use:

~~~c
// flat points to at least rows * cols validly allocated int elements.
int element = flat[i * cols + j]; // 0 <= i < rows, 0 <= j < cols
~~~

You must check that the multiplication `rows * cols` does not overflow `size_t` before allocating/accessing. Even though the memory of `int matrix[R][C]` is contiguous, you should not rely on taking `&matrix[0][0]` and incrementing an `int *` past **the first subarray boundary** to traverse the whole matrix: C pointer arithmetic rules apply to the array object that the pointer points to. Use `matrix[i][j]` / `int (*)[C]`, or allocate a true 1D flat buffer when the API takes `int *`.

## 6. Function Pointers: Calling Code via a Function Address

Unlike `int *` which points to data, `int (*operation)(int, int)` points to a function of the matching type. The parentheses around `*operation` are required to declare **a function pointer**:

~~~c
int add(int a, int b) {
    return a + b;
}

typedef int (*binary_operation)(int, int);

binary_operation operation = add;
int result = operation(2, 3); // 5, equivalent to (*operation)(2, 3).
~~~

This is illustrative declaration code; the `qsort` example below is a complete C11 program.

A function pointer must match **the return type, parameter list, and calling convention**. Never call a function through a pointer of an incompatible function type just because the addresses look similar. There is also no general ISO C guarantee that `void *` can hold every function pointer: `void *` is an object pointer; function pointer conversion rules depend on the platform, loader, and ABI. Some OS APIs specify a dedicated bridge for dynamic symbol lookup; you must follow that exact contract.

### Standard Library Callback with `qsort`

`qsort` takes a function pointer that compares two elements. Elements are passed as `const void *`, so the comparator must read them according to the actual element type:

~~~c
// File: FunctionPointerSort.c
#include <stdio.h>
#include <stdlib.h>

static int compare_ints(const void *left, const void *right) {
    int a = *(const int *)left;
    int b = *(const int *)right;
    return (a > b) - (a < b);
}

int main(void) {
    int values[] = {9, -2, 7, 0, 7};
    size_t count = sizeof values / sizeof values[0];

    qsort(values, count, sizeof values[0], compare_ints);
    for (size_t i = 0; i < count; ++i) {
        if (i != 0) {
            putchar(' ');
        }
        printf("%d", values[i]);
    }
    putchar('\n');
    return 0;
}
~~~

~~~sh
cc -std=c11 -Wall -Wextra -pedantic FunctionPointerSort.c -o pointer-sort
./pointer-sort
~~~

Stdout:

~~~text
-2 0 7 7 9
~~~

Do not use `return a - b;` as a general-purpose comparator because it can overflow `int`. The comparison function must return negative/0/positive values according to the ordering relation and handle duplicate elements consistently. When a native API stores a callback to invoke **after the registration call finishes**, the lifetime of the callback and user context must also extend until unregistration.

### Common Callback APIs

~~~c
// Example interface, not a complete implementation:
typedef void (*on_item_fn)(int item, void *user_context);
void native_visit(const int *items, size_t count,
                  on_item_fn callback, void *user_context);
~~~

`callback` is the address of an ABI-compliant function; `user_context` is a data pointer passed back to the callback, not a function pointer. In Java FFM, an **upcall stub** can create a callable address from a Java method handle; in JNI, an appropriate C/JNI bridge is required. You must handle unregistration, the callback thread, Java exceptions, reentrancy, and the lifetime of the stub/context. Never let a Java exception propagate across a C frame as if it were a C exception.

## 7. The ABI Determines How Types and Calls Actually Cross the Boundary

The ABI (Application Binary Interface) specifies not only C type names, but also how parameters/return values are placed into registers or onto the stack, sizes and alignment, struct layout, calling conventions, symbol rules, and certain platform-specific factors. Two pieces of code that appear valid at the source level can still be incompatible at the binary level.

| C Type / Concept | What to Check Before Mapping to Java |
|---|---|
| `int`, `short`, `long` | Size/signedness per target ABI; Java `int` is fixed at 32 bits, Java `long` is fixed at 64 bits |
| `size_t`, `ptrdiff_t` | Platform-dependent native integer types; do not automatically assume C `long` or Java `long` |
| `T *`, `void *` | Native address type; requires length/layout/lifetime to read the pointed-to region |
| `T **` | An address pointing to a pointer slot; requires reading/writing an additional address indirection |
| `T [N]`, `T (*)[N]` | Shape, stride, and layout; C arrays are contiguous, array parameters typically decay to pointers |
| `T *[N]` | N contiguous pointer slots, different from a buffer containing N `T` values |
| Function pointer | Signature + calling convention + lifetime of code/stub |
| `struct` | Field offsets, padding, alignment, nested layout; do not guess by summing field sizes |

Common example: on LP64 (many 64-bit Unix systems), C `long` is typically 8 bytes; on LLP64 (64-bit Windows), C `long` is typically **4 bytes** even though pointers are 8 bytes. Therefore, assuming “it’s a 64-bit machine so every `long` and pointer is 8 bytes” is wrong. `sizeof` gives the size in C byte units, and `_Alignof` (C11) gives the alignment of a type. `intptr_t`/`uintptr_t` in `<stdint.h>` are **optional integer types if supported by the platform**, used when converting object pointers to integers according to supported rules; they are not a license to fabricate arbitrary addresses or convert function pointers to integers.

When binding a C library, you must verify that **the header and binary were built for the same architecture/ABI**, packing conventions, version, `size_t`/`long` sizes, endianness when interpreting binary data, and error conventions. In particular, do not use `int **` in place of `int (*)[N]` just because both may have the size of a single address.

## 8. How Java Relates: JNI, FFM, Pointer Slots, and Callbacks

### Java Does Not Have `T *` Like C

A Java object reference is not a stable C address that you are allowed to freely add/subtract; the GC can move objects and the JVM manages their lifetime. Nor is `int[]` in Java automatically compatible with a native `int *` parameter under ABI rules. JNI has dedicated APIs to access/copy/pin primitive arrays, accompanied by release obligations and limitations of the API in use; do not retain a pointer to that temporary region after its lifetime ends.

JNI and FFM solve the problem differently:
- **JNI** uses native bridge functions with types such as `jint`, `jlong`, `jobject`, `jintArray`…; the JNI layer handles array/object conversions and manages interaction with the JVM.
- **FFM (finalized in JDK 22, JEP 454)** models memory regions with `MemorySegment`, lifetime with `Arena`, types/layouts with `MemoryLayout`/`ValueLayout`, native calls with `Linker` + `FunctionDescriptor`, and callbacks with upcall stubs. JDK 21 has FFM in preview with different API details/runtime flags; the example below targets **JDK 22+**, and is not expected to compile verbatim on JDK 21.

Conversion table in terms of **semantics**, not automatic casting:

| C | FFM Model (JDK 22+) | Checkpoints |
|---|---|---|
| `const int *data, size_t length` | Buffer address segment + length + compatible C integer layout | Byte size, bounds, alignment, owner |
| `int **out` | Segment allocating space for `ValueLayout.ADDRESS` for C to write a pointer | Second-level pointer; must interpret the returned address and free function |
| `int (*)[3]` | Segment with a 3-element row layout, or equivalent sequence/offset | Row stride and element size |
| `void (*cb)(int, void *)` | Upcall stub from a method handle matching the descriptor | Lifetime, calling thread, context, unregister |
| `int (*fn)(int)` | Downcall handle for a function address with the exact function descriptor | Signature, ABI, native-access requirement |

A segment is simply a region with **an address, a byteSize, and an access scope**. There is not enough information to infer “how many elements” from a C address alone. If you read an address with `ValueLayout.ADDRESS` **without declaring a target layout**, the segment representing that address defaults to `byteSize() == 0`. Do not dereference it as a bounded buffer without reliable bounds and lifetime; FFM operations that change the bounds/description of the underlying region may be restricted and can cause memory corruption if declared incorrectly.

### Java FFM Example: Contiguous Buffer and Pointer Slot

The following program uses **JDK 22+**, with no external C library required. It demonstrates two native regions: a buffer of three `int`s and a pointer slot of type `ADDRESS`. It **does not** automatically dereference the returned raw pointer:

~~~java
// File: PointerSlotDemo.java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class PointerSlotDemo {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            long intBytes = ValueLayout.JAVA_INT.byteSize();
            MemorySegment values = arena.allocate(
                    3L * intBytes, ValueLayout.JAVA_INT.byteAlignment());

            values.setAtIndex(ValueLayout.JAVA_INT, 0, 10);
            values.setAtIndex(ValueLayout.JAVA_INT, 1, 20);
            values.setAtIndex(ValueLayout.JAVA_INT, 2, 30);

            MemorySegment pointerSlot = arena.allocate(ValueLayout.ADDRESS);
            pointerSlot.set(ValueLayout.ADDRESS, 0, values);

            MemorySegment rawAddress = pointerSlot.get(ValueLayout.ADDRESS, 0);
            System.out.println("values[1] = "
                    + values.getAtIndex(ValueLayout.JAVA_INT, 1));
            System.out.println("address view bytes = " + rawAddress.byteSize());
        }
    }
}
~~~

~~~sh
javac PointerSlotDemo.java
java PointerSlotDemo
~~~

Stdout per the JDK 22 contract:

~~~text
values[1] = 20
address view bytes = 0
~~~

`values` is allocated in the arena, so it is bounded to three elements and invalidated after the arena closes. `pointerSlot` holds **the address value** to that buffer, conceptually equivalent to an `int *` variable that C can use via `int **`. `rawAddress` defaults to only a zero-sized address view; when it is read out, that view's access scope **does not automatically inherit** the lifetime/bounds of the original buffer. Do not use `rawAddress` after the buffer is freed. The example uses `JAVA_INT` for 32-bit Java values; when binding real C code, only use that layout if you have verified that the target ABI's C `int` matches.

## 9. Designing a Correct C–Java Contract When Receiving Pointers

Suppose a library exposes the interface:

~~~c
// Illustrative header for contract analysis, no implementation:
typedef int (*transform_fn)(int value, void *user_context);

int transform_buffer(const int *input, size_t count,
                     int **output, transform_fn fn,
                     void *user_context);
void transform_free(int *output);
~~~

Let us break down each item:
1. `input`: starting address of **count `int` elements**; Java must ensure the read region exists and is sufficiently sized during the call, and C will not modify it because the parameter carries `const`.
2. `count`: a `size_t` per the ABI; check for overflow of `count * sizeof(int)`, and do not automatically equate it with Java `int`.
3. `output`: a **pointer slot** (`int **`); C writes the result pointer into `*output`. Java must not pass the address of a result buffer directly as if it were a double pointer.
4. `fn`: callback function pointer matching the native signature; if C retains it, the upcall stub must stay alive across all invocations.
5. `user_context`: caller context/handle data passed verbatim; it must be stated whether C dereferences it or only forwards it; do not assume it is a Java object reference.
6. `transform_free`: function to free the result using the library's exact allocator; do not use `free` from a different runtime/CRT if the contract requires a dedicated release function.

Because the illustrative interface does not state error cases, the length of `output`, whether the callback runs synchronously or asynchronously, or the ownership of `user_context`, **a complete safe binding cannot yet be written** from the signature alone. You must read the library contract or add APIs that return the length and lifetime policy.

A minimal specification for each native parameter should answer: what type and layout; whether `NULL` is allowed; how many bytes are read/written; what alignment; who allocates/frees; how long it is used; whether the callback/address is retained; whether it may be called from another thread; the meaning of errors and how to recover. For `struct`s, verify offsets/padding instead of relying on guesswork.

## 10. Common Mistakes and How to Detect Them

| Mistake | Consequence | Fix |
|---|---|---|
| `int **p = matrix;` with `int matrix[R][C]` | Interprets integers as addresses, UB | Use `int (*p)[C] = matrix;` or a flat buffer per contract |
| Passing `int *p` when the function requires `int **out` | Function writes an address into target data instead of a pointer slot | Create an `int *p` variable and pass `&p`; in FFM allocate a pointer slot |
| Using `sizeof(pointer)` to compute element count | Wrong length, out-of-bounds read/write | Pass `length` separately and check size multiplication |
| Returning the address of a local variable whose lifetime has ended | Dangling pointer / use-after-scope | Caller provides buffer, or allocate with clear ownership |
| Using a pointer after `free`/closing an Arena | Use-after-free, crash, or data corruption | Bind lifetimes and do not retain addresses past expiration |
| Casting pointers arbitrarily to “match” `T **` / `T (*)[N]` | Wrong layout and dereference UB | Fix the actual signature/layout |
| Calling a callback with the wrong descriptor/calling convention | Wrong arguments, return value, and possible crash | Match prototype + ABI exactly |
| C retains a Java callback after the Arena closes | Calling into a no-longer-live stub | Keep the arena/stub alive until native unregistration completes |
| Assuming C `long` is always 64 bits | Reading wrong bytes/passing wrong arguments | Check LP64/LLP64 and canonical layout |
| Casting an unverified integer address to a pointer | Violates alignment/lifetime/provenance | Only use valid addresses from a native allocator/API |
| Using one `free` for all native regions | Wrong allocator/heap boundary | Call the provider's official release function |

When debugging, prioritize checking **the actual C prototype, target ABI, byte count, addresses, ownership, and callback timing**; a segmentation fault occurring later is often just a symptom. On the C side, you can enable compiler warnings and AddressSanitizer/UndefinedBehaviorSanitizer when supported by the toolchain, but sanitizers do not replace a correct native contract.

## 11. Self-Check

**Question 1.** Given `int v[4]`, `int *a = v;`, and `int (*b)[4] = &v;`, how do `a + 1` and `b + 1` differ?

**Answer:** `a + 1` advances by one `int` in the array; `b + 1` advances by one **array of four ints**, i.e., to the position immediately after the `v` object if the arithmetic is valid. Do not dereference a one-past pointer.

**Question 2.** Why can't `int m[2][3]` be passed to an `int **rows` parameter?

**Answer:** `m` converts to `int (*)[3]`, a pointer to a contiguous row. `rows`, however, expects a region containing `int *` slots. Native code will read the bytes of `int`s as addresses on the first-level dereference.

**Question 3.** When a native C function has parameter `int **result` and the caller needs to receive a new `int *`, what does the caller pass?

**Answer:** Pass **the address of a pointer variable** (`&ptr` in C), or allocate a pointer slot with an ADDRESS layout in FFM and let C write the new address into it. You must verify how to obtain the length and free the buffer.

**Question 4.** When can a Java callback via FFM not close its arena immediately after registration?

**Answer:** When native code retains the function pointer to call back asynchronously or after the registration call has returned; the stub and context must remain alive until native code confirms unregistration/no more callbacks are running.

## 12. Summary as a Chain of Reasoning

When reading a C signature, first determine **whether it is an object, a pointer slot, an array, or a function**. Next, determine the element count/stride, valid addressing rules, target ABI, and only then choose the Java representation. `T *` is an address to `T` data; `T **` is an address to **a pointer**; `T (*)[N]` steps by rows of `N` elements; `T *[N]` is an array of `N` pointers; `R (*)(Args...)` is a pointer to a function with the matching signature. Even types that share the same address size still have **different dereferencing semantics and layouts**.

**References for cross-checking Java APIs:** JEP 454 (https://openjdk.org/jeps/454); [Java SE 22 `java.lang.foreign` package](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html); [`AddressLayout`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/AddressLayout.html); [`MemorySegment`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html). For C code, cross-check the actual prototype and the rules of the C standard/target ABI rather than inferring from pointer size.