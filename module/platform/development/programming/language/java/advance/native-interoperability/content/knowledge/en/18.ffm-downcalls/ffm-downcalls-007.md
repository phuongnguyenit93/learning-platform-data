# Passing Structs by Value, Returning Structs, and the Extra SegmentAllocator Parameter in FFM

## 1. Goal: C struct by-value is not C struct pointer

In the **Foreign Function & Memory API (FFM)**, Java can directly call native functions following the C ABI without writing a JNI wrapper for each function. When a C function accepts or returns a `struct` **by value**, the programmer must describe the struct layout using `StructLayout` and use `MemorySegment` as the **carrier** on the Java side.

A special point of this topic: if a C function **returns a struct by value**, the FFM downcall `MethodHandle` **has an additional `SegmentAllocator` argument** so the linker knows where to allocate the memory holding the result. This argument is in the **Java-side MethodHandle signature**, **not** a new parameter in the C function declaration. **Do not modify the C function to add `SegmentAllocator` or a `void* result` argument just because Java needs an allocator.**

C example:

~~~c
typedef struct {
    int x;
    int y;
} Pair;

Pair pair_add(Pair a, Pair b);          /* Takes 2 structs by-value, returns struct by-value */
int pair_sum(Pair p);                  /* Takes struct by-value, returns int */
void pair_shift(Pair *p, int dx, int dy); /* Takes pointer to struct */
~~~

These are **illustrative declarations**, not a complete C file. They have **different ABI contracts**:

- `pair_add(Pair, Pair)`: the linker may pass struct fields via registers, stack, or a combination, depending on the ABI. The two Java arguments are `MemorySegment` instances representing **struct values**, not a C `Pair*` parameter.
- `pair_sum(Pair)`: the input is a struct by-value, but the result is an integer; **no extra allocator is needed** for the return value.
- `pair_shift(Pair*, int, int)`: the first argument is a **pointer address**; the FFM declaration must use `ValueLayout.ADDRESS`, and C can modify data inside Java's memory region.

**Practical goal:** create a small C library with `Pair`, compile it on Linux/macOS/Windows, and then use Java 22+ to call functions that **pass structs by value**, **receive returned structs**, **pass an allocator**, compare with passing pointers, read/write fields using `VarHandle`, and verify `sizeof`/`offsetof` before downcalling.

This is **standard FFM knowledge from JDK 22 (JEP 454)**. On JDK 21, the API is still in preview (JEP 442), requiring `--enable-preview`, and some overload names may differ. The main examples in this lesson are for **JDK 22+**.

## 2. Data model of a struct by value

Suppose in C:

~~~c
typedef struct {
    int x;
    int y;
} Pair;
~~~

Under a common ABI where C `int` is **4 bytes** with 4-byte alignment, the structure has:

~~~text
Pair (sizeof = 8 bytes, alignof = 4 bytes)

byte offset      0 1 2 3   4 5 6 7
                 +-------+-------+
                 |   x   |   y   |
                 +-------+-------+
                   int     int

x at offset 0, y at offset 4
~~~

When passing a `Pair` **by-value**, the C call has the semantics:

~~~c
Pair change_copy(Pair value) {
    value.x += 100;
    return value;
}
~~~

This is an **illustrative snippet**. C receives the value of `Pair` according to the ABI and modifies `value.x` in the parameter copy; the caller's data is not automatically modified. Conversely:

~~~c
void change_pointer(Pair *value) {
    value->x += 100;
}
~~~

This is also just a **snippet**. The function receives an address and directly modifies the backing memory pointed to by the pointer. If the pointer is invalid or has expired, it can cause a crash or memory corruption.

Comparison diagram:

~~~text
Java MemorySegment input --> FFM linker --> C pair_add(Pair input, ...)
                          [by-value]      C receives value/ABI aggregate
                                          C must not treat parameter as Pair*

Java MemorySegment input --> FFM linker --> C pair_shift(Pair *input, ...)
                          [ADDRESS]       C receives address
                                          C can modify backing memory

C pair_make(...) returns Pair by-value
           |
           v
FFM linker applies the ABI calling convention
           |
           +-- uses SegmentAllocator provided by Java to obtain storage for the result
           |
           v
Java receives MemorySegment representing the returned struct
~~~

Do not assume that "by-value" always corresponds to a fixed `memcpy` or a hidden pointer. Depending on the ABI, the C compiler may pass/return small structs via registers and large structs via memory/hidden return pointers. The **FFM native linker** is the component that handles those rules based on a valid `FunctionDescriptor`. Java only sees `MemorySegment` carriers and the extra allocator argument when there is a group return.

## 3. Declaring a StructLayout matching the C ABI

In FFM, a C `struct` is modeled with `MemoryLayout.structLayout(...)`, which returns a `StructLayout` (a form of `GroupLayout`). Integer-typed fields are typically described using a `ValueLayout` matching the ABI.

JDK 22:

~~~java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;

StructLayout PAIR = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("x"),
        ValueLayout.JAVA_INT.withName("y")
).withName("Pair");
~~~

This is a **snippet**, not a complete Java file; the runnable example is in section 7.

- `JAVA_INT` has carrier `int` and size **4 bytes**. In this lesson we choose C `int` and verify with `_Static_assert(sizeof(int) == 4)`.
- `withName("x")` and `withName("y")` are **labels used when accessing the layout**, not names transferred across the C ABI. Omitting these labels does not change the C struct's layout, but it will affect `groupElement("x")`.
- `PAIR.byteSize()` must match `sizeof(Pair)`.
- `PAIR.byteAlignment()` must match the required alignment of the C struct.
- `PAIR.byteOffset(groupElement("y"))` must match `offsetof(Pair, y)`.

Do not use a Java POJO/record to automatically replace `MemorySegment` in `FunctionDescriptor`. FFM does not know how to marshal a Java object with `x`/`y` fields into the proper native aggregate ABI without a binding layer written by you.

### 3.1. Checking the layout from the native side

Comparing actual size and offset is the way to avoid "works on my laptop but fails on another platform" bugs:

~~~c
/* C snippet, requires #include <stddef.h> */
int pair_size(void) {
    return (int) sizeof(Pair);
}

int pair_offset_y(void) {
    return (int) offsetof(Pair, y);
}
~~~

The hands-on exercise will **export these two functions**, calling them via FFM before performing downcalls with struct by-value. If the size/offset is wrong, the program stops instead of passing invalid native data.

C11's `_Alignof(Pair)` can also be used to verify alignment. The exercise will place `_Static_assert` in the C file to fail compilation if running on an ABI that does not meet the assumptions.

### 3.2. StructLayout does NOT automatically add all C padding

Another example:

~~~c
typedef struct {
    char tag;
    double value;
    int count;
} Mixed;
~~~

Under a **common 64-bit ABI** where C `double` has 8-byte alignment, the layout is typically:

~~~text
offset 0: char tag       (1 byte)
offset 1..7: padding    (7 bytes)
offset 8: double value  (8 bytes)
offset 16: int count    (4 bytes)
offset 20..23: tail padding (4 bytes)
sizeof(Mixed) = 24, alignof(Mixed) = 8
~~~

It can be described in Java **only when the actual ABI matches**:

~~~java
// JDK 22 snippet, not automatically portable to every ABI.
StructLayout MIXED = MemoryLayout.structLayout(
    ValueLayout.JAVA_BYTE.withName("tag"),
    MemoryLayout.paddingLayout(7),
    ValueLayout.JAVA_DOUBLE.withName("value"),
    ValueLayout.JAVA_INT.withName("count"),
    MemoryLayout.paddingLayout(4)
);
~~~

Without inserting padding according to the C ABI, Java `structLayout` will pack members **contiguously in declaration order**, and the byte count/offsets may not match C. Because the linker needs the exact layout, omitting padding **not only causes data to be read incorrectly**, but can also cause aggregate classification into registers/stack and return form to be wrong, leading to crashes.

**Do not treat the `Mixed` example above as a universal standard.** 32-bit C ABIs, packed structs, pragmas, compiler flags, or other platforms may have different sizes/alignments. Use `sizeof`, `offsetof`, `_Alignof` (and ABI documentation) to confirm. `Linker.canonicalLayouts()` provides some canonical C scalar types of the ABI, but **does not automatically infer the padding of an arbitrary struct from a C header**.

## 4. FunctionDescriptor for by-value and pointer

In this lesson, Java uses a defined `StructLayout PAIR`. Three main forms:

~~~java
// C: Pair pair_add(Pair a, Pair b);
FunctionDescriptor addDesc =
        FunctionDescriptor.of(PAIR, PAIR, PAIR);

// C: int pair_sum(Pair p);
FunctionDescriptor sumDesc =
        FunctionDescriptor.of(ValueLayout.JAVA_INT, PAIR);

// C: void pair_shift(Pair *p, int dx, int dy);
FunctionDescriptor shiftDesc =
        FunctionDescriptor.ofVoid(
                ValueLayout.ADDRESS,
                ValueLayout.JAVA_INT,
                ValueLayout.JAVA_INT
        );
~~~

This is a **snippet**; the imports and `PAIR` variable are in the full example.

Remember three rules:

1. **`FunctionDescriptor.of(returnLayout, argumentLayouts...)`**: the **first element is the return type layout**, not the first C parameter.
2. **`PAIR` represents C `Pair` by-value** in an argument or return position. **`ValueLayout.ADDRESS` represents a pointer** such as `Pair*`.
3. **`FunctionDescriptor.ofVoid(...)`** is only for C functions with a `void` return type. A C `Pair` return is a group layout; never substitute `ADDRESS` as a shortcut.

Mapping table:

| C signature | FFM function descriptor | Java MethodHandle carrier type |
|---|---|---|
| `Pair pair_make(int, int)` | `of(PAIR, JAVA_INT, JAVA_INT)` | `(SegmentAllocator, int, int) -> MemorySegment` |
| `Pair pair_add(Pair, Pair)` | `of(PAIR, PAIR, PAIR)` | `(SegmentAllocator, MemorySegment, MemorySegment) -> MemorySegment` |
| `Pair pair_tweak_copy(Pair)` | `of(PAIR, PAIR)` | `(SegmentAllocator, MemorySegment) -> MemorySegment` |
| `int pair_sum(Pair)` | `of(JAVA_INT, PAIR)` | `(MemorySegment) -> int` |
| `void pair_shift(Pair*, int, int)` | `ofVoid(ADDRESS, JAVA_INT, JAVA_INT)` | `(MemorySegment, int, int) -> void` |
| `int pair_size(void)` | `of(JAVA_INT)` | `() -> int` |

The table uses **downcall handles bound to a function address** (`linker.downcallHandle(symbol, descriptor)`), not unbound handles that take an extra function address argument.

Note: a C `struct` returned by-value may be `struct Pair` or typedef `Pair`; both have the same semantics if they are actually the same type. Conversely, `Pair*` returning a C pointer is a completely different case: Java receives a segment representing an **address**, usually of length 0, and **there is no extra `SegmentAllocator` just because the return type is a pointer**.

## 5. Why does SegmentAllocator additionally appear in Java?

`SegmentAllocator` is an interface with the abstract method `allocate(long byteSize, long byteAlignment)`. It describes **how to provide a native memory region with a given size and alignment**. `Arena` is also a `SegmentAllocator`, so `Arena.ofConfined()` and `Arena.ofShared()` can both be passed to a downcall that needs to receive a struct result.

When the return layout is a **group layout**, FFM must have Java-side memory to represent the returned aggregate. Specifically:

~~~text
C declaration: Pair pair_add(Pair a, Pair b);

Java:
    StructLayout PAIR = ...
    FunctionDescriptor.of(PAIR, PAIR, PAIR)
    MethodHandle add = linker.downcallHandle(symbol, descriptor)

add.type():
    (SegmentAllocator, MemorySegment, MemorySegment)MemorySegment
     ^^^^^^^^^^^^^^^^  ^^^^^^^^^^^^^  ^^^^^^^^^^^^^
     EXTRA ALLOCATOR    C Pair a       C Pair b

Result:
    MemorySegment representing Pair returned by-value
    Has the scope/lifetime of the allocation created by the allocator
~~~

**The allocator is not in the C prototype.** If the C compiler needs a hidden return buffer pointer according to the ABI, that is a detail **handled automatically by the linker/runtime**. Do not add `SegmentAllocator` to the C header, do not rewrite C `Pair pair_add(Pair, Pair)` into `void pair_add(void*, Pair*, Pair*)`, and do not pass a random C result pointer just because the Java handle has an extra leading parameter.

The condition that triggers the allocator is determined by **the layout of the return value (group)**, not by whether an input parameter is a struct. For example, `pair_sum(Pair)` takes a struct by-value but returns `int`, so its handle **does not have an allocator prefix**.

### 5.1. Correct order for a bound downcall handle

~~~java
// Assume MethodHandle add and Arena arena have been validly created.
MemorySegment result = (MemorySegment) add.invokeExact(
        (SegmentAllocator) arena, left, right
);
~~~

This is a **snippet**. When using `invokeExact`, the Java types at the call site must **match `MethodHandle.type()` exactly**:

- The return cast `(MemorySegment)` is required for the compiler to select the right signature when using `invokeExact`.
- Use `(SegmentAllocator) arena` (or declare `SegmentAllocator allocator = arena`) so the call-site type is **`SegmentAllocator`**, not `Arena`.
- The two arguments `left` and `right` must have type **`MemorySegment`** and represent valid structs.
- The result may only be used while the allocator's arena is still alive.

**Common mistake:**

~~~java
// WRONG/shown for explanation, do not run this snippet:
MemorySegment result = (MemorySegment) add.invokeExact(
        arena, left, right
);
~~~

If the variable `arena` has **static type `Arena`**, the compiler will emit the call site signature `(Arena, MemorySegment, MemorySegment) -> MemorySegment`, which does not match the handle expecting `SegmentAllocator`. The result can be `WrongMethodTypeException`. `Arena implements SegmentAllocator` is **not enough** for `invokeExact` without the exact static type at the call site. `MethodHandle.invoke` can perform some compatible conversions, but in this lesson we intentionally choose `invokeExact` to catch type mismatches early.

### 5.2. Handle bound to a function address vs. unbound handle

Two ways to create a downcall:

~~~java
// Bound to symbol: no address prefix at invoke time.
MethodHandle bound = linker.downcallHandle(symbol, descriptor);

// Unbound: requires address prefix at invoke time.
MethodHandle unbound = linker.downcallHandle(descriptor);
~~~

This is a **snippet**. With return `PAIR` and parameters `(PAIR, PAIR)`:

- `bound` has the form **`(SegmentAllocator, MemorySegment, MemorySegment) -> MemorySegment`**.
- `unbound` has the form **`(MemorySegment functionAddress, SegmentAllocator allocator, MemorySegment, MemorySegment) -> MemorySegment`**.

In `unbound`, `functionAddress` **is not a C parameter**; it tells the linker which function address to call on that invocation. `SegmentAllocator` remains the virtual parameter for allocating memory for the struct return. Other options such as capturing call state can add their own prefix arguments; checking `handle.type()` is the source of truth when debugging.

## 6. Which SegmentAllocator should be used to receive a struct?

### 6.1. Arena.ofConfined — the default practical choice

~~~java
try (Arena arena = Arena.ofConfined()) {
    SegmentAllocator allocator = arena;
    MemorySegment result = (MemorySegment) add.invokeExact(
            allocator, left, right
    );
    // Read result right here; arena is still alive.
}
// End of try, arena closes and result is no longer valid.
~~~

This is a **snippet**: variables `add`, `left`, `right` must already exist. `Arena.ofConfined()` has a deterministic lifecycle, allowing timely reclamation of native memory and restricting access outside the owner thread.

A few notes:

- Result allocation may be performed by the linker using `allocator.allocate(PAIR.byteSize(), PAIR.byteAlignment())` or an equivalent mechanism. **Do not rely on the internal number of allocator calls** as a portable contract.
- Segments created by `arena` belong to the same scope; once closed, they must not be used further.
- There is no need to pre-allocate `MemorySegment result = arena.allocate(PAIR)` for a bound downcall returning a group and pass that result as a C parameter. The `SegmentAllocator` parameter lets the runtime manage the return storage itself.
- When there are multiple struct results, one arena can own multiple allocations and clean them up together.

### 6.2. Arena.ofShared — multiple threads with a bounded lifetime

`Arena.ofShared()` is also a `SegmentAllocator`. It is suitable when the created segments may need to be read from multiple Java threads, **but still have a clear closing point**. Do not close the arena while another thread is using the result or a native function still holds a pointer to that region.

**A shared arena does not automatically synchronize mutations** to struct fields. If multiple threads write concurrently, proper memory ordering/concurrency design is still required.

### 6.3. Arena.global and Arena.ofAuto — not defaults for temporary results

- `Arena.global()` has an unbounded lifetime: memory it allocates **is not deallocated by the arena**. Using it for per-request results can cause native memory to grow for the entire JVM lifetime.
- `Arena.ofAuto()` has a lifetime managed by the JVM/GC, and cannot be closed deterministically. It may fit some designs, but do not use it if you need to guarantee native memory is freed right after the downcall.

For a simple `Pair pair_add(...)` call, `ofConfined` is usually the easiest to understand, easiest to QA, and has the clearest cleanup rules.

### 6.4. Custom SegmentAllocator: why be careful?

`SegmentAllocator` is a functional interface, so you can create a custom allocator or use `SegmentAllocator.slicingAllocator(...)`/`prefixAllocator(...)`. However, such allocators may behave differently from `Arena`:

- An allocator might return **overlapping memory segments** if poorly designed. If the linker writes a struct result onto a region still in use, the previous result can be overwritten.
- An allocator might **run out of space** or return memory with the wrong alignment.
- An allocator might **not be thread-safe**.
- The lifetime of the returned segments might not match how long the result is used.

The `SegmentAllocator` documentation advises clients to interact only with allocators they manage and to consider using `Arena` for its guarantees on thread safety, scope, and non-overlapping memory regions.

## 7. Full example: Java 22 + C library, struct by-value and struct return

We write a small library containing the following C functions:

~~~c
Pair pair_make(int x, int y);
Pair pair_add(Pair a, Pair b);
Pair pair_tweak_copy(Pair value);
int pair_sum(Pair value);
void pair_shift(Pair *value, int dx, int dy);
int pair_size(void);
int pair_offset_y(void);
~~~

Meaning table:

| Native function | Purpose | Allocator prefix? |
|---|---|---|
| `pair_make` | Create a `Pair` and return by-value | **Yes** |
| `pair_add` | Take two `Pair` by-value, return `Pair` by-value | **Yes** |
| `pair_tweak_copy` | Modify the by-value copy and return the copy | **Yes** |
| `pair_sum` | Take `Pair` by-value, return `int` | **No** |
| `pair_shift` | Take `Pair*`, modify in-place | **No** |
| `pair_size` / `pair_offset_y` | Verify C ABI before passing aggregates | **No** |

**There is no JNI wrapper in the C code of this lesson.** `System.loadLibrary` and `JNIEnv *` are unnecessary for downcalls via `SymbolLookup.libraryLookup`.

### 7.1. C — file `pairffi.c`

~~~c
#include <stddef.h>

/* Export symbols appropriately for Windows/Linux/macOS. */
#if defined(_WIN32)
#  define FFM_EXPORT __declspec(dllexport)
#else
#  define FFM_EXPORT __attribute__((visibility("default")))
#endif

typedef struct {
    int x;
    int y;
} Pair;

/* This example only targets ABIs with int=4 bytes, align=4, Pair=8 bytes. */
_Static_assert(sizeof(int) == 4, "C int must be 4 bytes");
_Static_assert(_Alignof(int) == 4, "C int alignment must be 4");
_Static_assert(sizeof(Pair) == 8, "Pair must be 8 bytes");
_Static_assert(_Alignof(Pair) == 4, "Pair alignment must be 4");
_Static_assert(offsetof(Pair, y) == 4, "Pair.y offset must be 4");

/* Return Pair by-value: Java downcall will require SegmentAllocator. */
FFM_EXPORT Pair pair_make(int x, int y) {
    Pair result = {x, y};
    return result;
}

/* Both input and output are by-value: C does NOT take Pair*. */
FFM_EXPORT Pair pair_add(Pair a, Pair b) {
    Pair result = {a.x + b.x, a.y + b.y};
    return result;
}

/* Modify copy of parameter, do not modify Pair in caller. */
FFM_EXPORT Pair pair_tweak_copy(Pair value) {
    value.x += 100;
    return value;
}

/* Input by-value but scalar result => no allocator prefix. */
FFM_EXPORT int pair_sum(Pair value) {
    return value.x + value.y;
}

/* Unlike by-value: takes pointer and modifies backing memory in-place. */
FFM_EXPORT void pair_shift(Pair *value, int dx, int dy) {
    if (value != NULL) {
        value->x += dx;
        value->y += dy;
    }
}

/* Provide actual numbers for Java to verify layout before by-value calls. */
FFM_EXPORT int pair_size(void) {
    return (int) sizeof(Pair);
}

FFM_EXPORT int pair_offset_y(void) {
    return (int) offsetof(Pair, y);
}
~~~

This is a **complete C file**, using **C11** features (`_Static_assert`, `_Alignof`). When building on an OS that does not satisfy `int` 4-byte, alignment 4, `Pair` 8-byte, the compiler will stop with a static assert error instead of running incompatible bindings. This is a **more reliable** safeguard than silently assuming the C ABI is always the same.

The results in the example are small, avoiding signed `int` overflow in C. With untrusted data, an overflow-checking policy should be defined to avoid undefined behavior in native C during addition.

**Why is there no allocator in the C function?** C `Pair pair_add(Pair, Pair)` returns a real struct according to the C ABI. The JVM's native linker handles the rules for passing/returning aggregates, including a hidden return pointer if the ABI requires one. `SegmentAllocator` is merely the interface for Java to choose the scope and destination memory for the result.

### 7.2. Java — file `StructByValueDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SegmentAllocator;
import java.lang.foreign.StructLayout;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;
import java.nio.file.Path;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;
import static java.lang.foreign.ValueLayout.JAVA_INT;

public class StructByValueDemo {
    private static final StructLayout PAIR = MemoryLayout.structLayout(
            JAVA_INT.withName("x"),
            JAVA_INT.withName("y")
    ).withName("Pair");

    private static final VarHandle X = PAIR.varHandle(groupElement("x"));
    private static final VarHandle Y = PAIR.varHandle(groupElement("y"));

    private static MemorySegment newPair(Arena arena, int x, int y) {
        MemorySegment pair = arena.allocate(PAIR);
        X.set(pair, 0L, x);
        Y.set(pair, 0L, y);
        return pair;
    }

    private static int x(MemorySegment pair) {
        return (int) X.get(pair, 0L);
    }

    private static int y(MemorySegment pair) {
        return (int) Y.get(pair, 0L);
    }

    private static String show(MemorySegment pair) {
        return "(" + x(pair) + "," + y(pair) + ")";
    }

    private static MethodHandle bind(
            Linker linker, SymbolLookup lookup,
            String name, FunctionDescriptor descriptor
    ) {
        MemorySegment symbol = lookup.find(name).orElseThrow();
        return linker.downcallHandle(symbol, descriptor);
    }

    private static void requireType(
            MethodHandle handle, MethodType expected
    ) {
        if (!handle.type().equals(expected)) {
            throw new AssertionError(
                    "wrong handle type: " + handle.type()
                    + ", expected: " + expected
            );
        }
    }

    public static void main(String[] args) throws Throwable {
        Path nativeLibrary = Path.of(
                System.mapLibraryName("pairffi")
        ).toAbsolutePath();

        MemorySegment resultOutsideArena;

        try (Arena arena = Arena.ofConfined()) {
            Linker linker = Linker.nativeLinker();
            SymbolLookup lookup = SymbolLookup.libraryLookup(
                    nativeLibrary, arena
            );

            MethodHandle size = bind(
                    linker, lookup, "pair_size",
                    FunctionDescriptor.of(JAVA_INT)
            );
            MethodHandle offsetY = bind(
                    linker, lookup, "pair_offset_y",
                    FunctionDescriptor.of(JAVA_INT)
            );

            int cSize = (int) size.invokeExact();
            int cOffsetY = (int) offsetY.invokeExact();
            long javaOffsetY = PAIR.byteOffset(groupElement("y"));

            // Stop before passing/receiving structs if layout mismatches.
            if (cSize != PAIR.byteSize()
                    || cOffsetY != javaOffsetY
                    || PAIR.byteAlignment() != 4L) {
                throw new AssertionError("C/Java Pair layout differs");
            }

            MethodHandle make = bind(
                    linker, lookup, "pair_make",
                    FunctionDescriptor.of(PAIR, JAVA_INT, JAVA_INT)
            );
            MethodHandle add = bind(
                    linker, lookup, "pair_add",
                    FunctionDescriptor.of(PAIR, PAIR, PAIR)
            );
            MethodHandle tweak = bind(
                    linker, lookup, "pair_tweak_copy",
                    FunctionDescriptor.of(PAIR, PAIR)
            );
            MethodHandle sum = bind(
                    linker, lookup, "pair_sum",
                    FunctionDescriptor.of(JAVA_INT, PAIR)
            );
            MethodHandle shift = bind(
                    linker, lookup, "pair_shift",
                    FunctionDescriptor.ofVoid(
                            ValueLayout.ADDRESS, JAVA_INT, JAVA_INT
                    )
            );

            // Bound handle returning Pair: allocator IS the first argument.
            requireType(add, MethodType.methodType(
                    MemorySegment.class,
                    SegmentAllocator.class,
                    MemorySegment.class,
                    MemorySegment.class
            ));
            requireType(make, MethodType.methodType(
                    MemorySegment.class, SegmentAllocator.class,
                    int.class, int.class
            ));
            requireType(sum, MethodType.methodType(
                    int.class, MemorySegment.class
            ));

            // Java prepares two input structs in native memory.
            MemorySegment a = newPair(arena, 3, 4);
            MemorySegment b = newPair(arena, 10, 20);

            // SegmentAllocator is a MethodHandle parameter, not a C parameter.
            SegmentAllocator allocator = arena;

            MemorySegment made = (MemorySegment) make.invokeExact(
                    allocator, 7, 8
            );
            MemorySegment added = (MemorySegment) add.invokeExact(
                    allocator, a, b
            );
            MemorySegment tweaked = (MemorySegment) tweak.invokeExact(
                    allocator, a
            );

            int total = (int) sum.invokeExact(added);

            System.out.println("C size = " + cSize);
            System.out.println("Java size = " + PAIR.byteSize());
            System.out.println("offset y = " + javaOffsetY);
            System.out.println("allocator first = "
                    + (add.type().parameterType(0)
                            == SegmentAllocator.class));
            System.out.println("a = " + show(a));
            System.out.println("b = " + show(b));
            System.out.println("made = " + show(made));
            System.out.println("added = " + show(added));
            System.out.println("tweaked copy = " + show(tweaked));
            System.out.println("sum(added) = " + total);

            // This C function takes Pair* (ADDRESS), modifies in-place.
            shift.invokeExact(added, 1, 2);
            System.out.println("shifted by pointer = " + show(added));
            System.out.println("a unchanged = " + show(a));

            resultOutsideArena = added;
        }

        // Only check scope, DO NOT dereference after arena closes.
        System.out.println("result alive after close = "
                + resultOutsideArena.scope().isAlive());
    }
}
~~~

**This is a complete Java 22 file**, not pseudocode. It uses `SymbolLookup.libraryLookup` and `Linker.downcallHandle` to link C symbols, without using native declarations in Java.

A few points intentionally made clear:

1. `PAIR` is a `StructLayout` with **two 4-byte `int`s**, member names x/y matching C.
2. `X` and `Y` are `VarHandle`s accessing fields via the `groupElement` path. `X.set(pair, 0L, x)` uses base offset `0L` matching the VarHandle's method type.
3. `newPair` creates a native segment with `arena.allocate(PAIR)`, ensuring size/alignment according to the layout; it does not rely on any unaligned memory.
4. `pair_size`/`pair_offset_y` are called before creating or using downcalls that handle structs, checking runtime consistency.
5. `requireType` checks the **actual MethodType** that FFM generates: `add` and `make` require `SegmentAllocator` in the first position; `sum` only has a `MemorySegment` input and scalar result.
6. The variable `allocator` is declared with **static type `SegmentAllocator`**, giving `invokeExact` the right signature; the object itself is still `Arena.ofConfined()`.
7. `made`, `added`, `tweaked` are **result segments** with scopes provided by the allocator. They are only dereferenced while the arena is still open.
8. `pair_tweak_copy(Pair)` modifies the C copy and returns a new struct; `a` is unchanged.
9. `pair_shift(Pair*)` takes an address and directly modifies `added`, helping distinguish pointer semantics from by-value.
10. `resultOutsideArena.scope().isAlive()` is read after the try block to prove the result follows the allocator's scope. The code does not attempt to access fields after `arena.close()`.

**The technique of reading `MethodHandle.type()`** is very useful when debugging `WrongMethodTypeException`: do not rely on the number of C parameters to guess the Java signature of a downcall. A struct return has an allocator prefix, an unbound handle also has an address prefix; some linker options also add parameters.

### 7.3. Building the C library

Choose a compiler that supports C11 and build the library for the **exact OS and architecture** of the JVM. `jni.h` is not needed.

**Linux (GCC/Clang):**

~~~bash
cc -std=c11 -fPIC -shared pairffi.c -o libpairffi.so
~~~

**macOS (Clang):**

~~~bash
cc -std=c11 -fPIC -dynamiclib pairffi.c -o libpairffi.dylib
~~~

**Windows (Visual Studio 2022 Developer Command Prompt, cmd.exe):**

~~~bat
cl /std:c11 /LD pairffi.c /Fe:pairffi.dll
~~~

The Windows command assumes MSVC supports C11 (`/std:c11`). `_Static_assert` and `_Alignof` may not be available if using an older C compiler; upgrade the toolchain rather than removing the ABI verification conditions just to make the build pass.

The binary needs to be placed **in the current working directory** when running Java, or change how `Path nativeLibrary` is constructed to point to an actual absolute path. `System.mapLibraryName("pairffi")` produces `libpairffi.so` (Linux), `libpairffi.dylib` (macOS), or `pairffi.dll` (Windows).

**Checking exports** (platform-dependent):

~~~text
Linux:   nm -D libpairffi.so
macOS:   nm -g libpairffi.dylib
Windows: dumpbin /EXPORTS pairffi.dll
~~~

These are **suggested inspection commands**, not a portable script to run verbatim on every OS. Confirm that C symbol names like `pair_make`, `pair_add`, and `pair_shift` appear properly. On macOS, `nm` may display a leading `_` character per the Mach-O symbol convention.

### 7.4. Compiling and running Java

Run in the directory containing `StructByValueDemo.java` and the built library:

~~~bash
java -version
javac -version
javac --release 22 StructByValueDemo.java
java --enable-native-access=ALL-UNNAMED StructByValueDemo
~~~

**JDK 22** is required when using `--release 22`, and FFM is finalized so **`--enable-preview` is not needed**. The `--enable-native-access=ALL-UNNAMED` flag grants Java code on the classpath permission to perform restricted native operations, including `SymbolLookup.libraryLookup` and `Linker.downcallHandle`.

**Expected stdout on an ABI satisfying the static asserts:**

~~~text
C size = 8
Java size = 8
offset y = 4
allocator first = true
a = (3,4)
b = (10,20)
made = (7,8)
added = (13,24)
tweaked copy = (103,4)
sum(added) = 37
shifted by pointer = (14,26)
a unchanged = (3,4)
result alive after close = false
~~~

Explanation:

- `pair_make(7, 8)` returns a struct from C and Java receives a segment with fields `(7,8)`.
- `pair_add(Pair(3,4), Pair(10,20))` returns `(13,24)`; Java uses **`SegmentAllocator`** to obtain native storage for the result.
- `pair_tweak_copy(Pair(3,4))` increments field `x` of the **by-value parameter** and returns `(103,4)`; `a` remains `(3,4)`.
- `pair_sum(Pair(13,24))` returns **scalar** 37; no allocator is passed to this handle.
- `pair_shift(&added, 1,2)` modifies the struct inside segment `added` via **pointer**, yielding `(14,26)`.
- `arena.close()` at the end of try makes the result segments invalid; `scope().isAlive()` subsequently returns `false`.

**Verification status:** the program is designed against the Java SE 22 API and has deterministic stdout for the declared C ABI, but this section does not replace running tests on the actual target machine/ABI. If the linker rejects a group layout or the C compiler stops on `_Static_assert`, **do not arbitrarily alter the descriptor** to force it to run; check the ABI, FFM-supported platforms, and compiler flags.

## 8. Three call flows with different signatures

### 8.1. Accepting struct by-value, returning struct by-value

~~~text
C:
    Pair pair_add(Pair a, Pair b)

Java FunctionDescriptor:
    of(PAIR, PAIR, PAIR)

Java bound MethodHandle:
    (SegmentAllocator, MemorySegment, MemorySegment) -> MemorySegment

Java invoke:
    add.invokeExact(allocator, a, b)

Result:
    Segment containing the struct created by the allocator
~~~

The two passed `MemorySegment`s are the data sources that the linker uses to construct the **struct values** according to ABI rules. Do not use `ValueLayout.ADDRESS` for them: doing so would turn the described native type into `Pair*`, differing from the actual prototype.

### 8.2. Accepting struct by-value, returning an integer

~~~text
C:
    int pair_sum(Pair value)

Java FunctionDescriptor:
    of(JAVA_INT, PAIR)

Java bound MethodHandle:
    (MemorySegment) -> int

Java invoke:
    int answer = (int) sum.invokeExact(pair)

No SegmentAllocator prefix!
~~~

**Passing a struct by-value** itself does not trigger an extra allocator. It only appears because the **return value** is a group layout.

### 8.3. Accepting a pointer, modifying struct in place

~~~text
C:
    void pair_shift(Pair *value, int dx, int dy)

Java FunctionDescriptor:
    ofVoid(ADDRESS, JAVA_INT, JAVA_INT)

Java bound MethodHandle:
    (MemorySegment, int, int) -> void

Java invoke:
    shift.invokeExact(pair, 1, 2)

Java sees the segment's fields change.
~~~

Here `MemorySegment` represents the **native address** for the C `Pair*` parameter. FFM checks segment liveness/thread conditions as far as the API allows, but **does not automatically verify that the native function respects byteSize or does not retain the pointer after the call**. Ensuring the pointer remains valid for the duration of the C invocation and any remaining native consumers is the responsibility of the binding.

## 9. Why can't struct by-value be replaced with ADDRESS?

There are two very different C signatures:

~~~c
Pair make_pair(int x, int y);
Pair *allocate_pair(int x, int y);
~~~

This is a **declaration snippet**, not a program providing both functions.

- For `make_pair`, C returns an **aggregate value**. The Java descriptor must have a **`StructLayout` return layout**, the handle has an extra `SegmentAllocator` and returns a `MemorySegment` representing the **by-value result**.
- For `allocate_pair`, C returns **a pointer**. The Java descriptor uses **`ValueLayout.ADDRESS`**, and the handle **has no allocator prefix from a group return**. Java receives a segment representing an address; if the library allocates dynamic memory, a separate contract is needed to know the size and release function.

If `Pair make_pair(...)` is described using `FunctionDescriptor.of(ADDRESS, JAVA_INT, JAVA_INT)`, caller and callee **disagree on the ABI**. Depending on OS/CPU, a struct may be returned via registers/stack/hidden pointer in a way unlike a pointer return. The failure may be garbage values, silent corruption, or a JVM crash.

**There is no general reflection mechanism for the JVM to look up the "actual C return type" from a symbol address.** `FunctionDescriptor` is the description you provide; the linker trusts it. Wrong signature means wrong native contract.

### 9.1. SegmentAllocator is not C's malloc()

Some people confuse `SegmentAllocator` with `malloc` because it creates memory. However:

- `SegmentAllocator` is a **Java interface**, letting the linker choose where to place the aggregate result.
- The C compiler handles the ABI, potentially using registers or an internal hidden result pointer; Java does not need to guess.
- `Arena` owns the storage for the result it allocates; when closed, the result becomes invalid.
- For the C function `Pair* allocate_pair(...)`, memory allocation happens in the **C library** and may require `free_pair(...)`. Passing a Java `SegmentAllocator` does not automatically free a pointer created by C.

Use the right return layout kind to distinguish **value** from **address**.

## 10. Lifecycle of struct results and ownership issues

A result `MemorySegment` from a downcall with a group return is tied to the **storage allocated by `SegmentAllocator`**. Do not be mistaken:

~~~java
// Snippet assumes handle add is validly bound.
MemorySegment result;

try (Arena arena = Arena.ofConfined()) {
    SegmentAllocator allocator = arena;
    MemorySegment a = arena.allocate(PAIR);
    MemorySegment b = arena.allocate(PAIR);
    result = (MemorySegment) add.invokeExact(allocator, a, b);
}

// WRONG: result is out of scope; reading fields here is invalid.
// int x = (int) X.get(result, 0L);
~~~

This is a **lifecycle-illustrative snippet**, not complete code because `PAIR`, `add`, and `X` are not declared in the snippet. Upon exiting the try block, the arena is closed; Java FFM may throw `IllegalStateException` if `result` is accessed.

### 10.1. How to bring the result out of scope?

Reasonable approaches:

1. **Read fields into Java primitives/records** while the arena is alive; return a Java object containing the copied data, rather than returning a short-lived segment.
2. **Copy to another arena** with an appropriately managed lifetime if the native representation must be kept longer. Ensure the new owner stays alive and data is copied with the right layout.
3. **Use a shared arena** if the result must live across multiple threads and has a deterministic cleanup point.
4. **Do not default to the global arena** just to avoid "segment closed" errors: doing so can turn a lifetime bug into a **process-lifetime native memory leak**.

If the C library retains the address of an input/result struct after the downcall finishes, Java closing the arena early will cause a dangling pointer. A normal by-value C signature passes **values**, but a native function might try to retain the address of an internal copy; that is a different C contract that must be reviewed and is usually invalid once the stack/local copy expires.

### 10.2. Return allocator can be a separate arena from input arenas

In principle, input `MemorySegment`s and the result allocator **do not have to share the same arena**, as long as they are all valid throughout the downcall and have appropriate lifetimes. For example, inputs may live in a shared arena while output is allocated in a request-scoped confined arena. The important thing is that the **return value belongs to the lifetime of the provided allocator**, not automatically to the scope of each input.

Do not close an input scope while the native call is still running; likewise, do not close the result allocator before reading or transferring the data.

### 10.3. By-value result vs. view pointing into C memory

A C `Pair` returned by value is an **aggregate value**. Java receives a `MemorySegment` containing the result data provided by the allocator. Do not infer that the result segment points directly to a local variable of the C callee.

If a C function returns `Pair*`, the Java segment may just be a wrapper around an address into C memory; you need to know **who frees it**, **when to free it**, and its **length**. Do not call `reinterpret(sizeof(Pair))` on a pointer of unknown origin and assume the data is safe. `reinterpret` changes metadata but **does not verify the backing allocation**.

## 11. Padding, alignment, and struct ABI portability

### 11.1. Why can matching sizeof alone still be wrong?

Two structs can have the same `sizeof` yet different field offsets. For example, packed structs, compiler pragmas, bit fields, or C unions can cause different interpretations even when the total byte count matches.

Therefore, for `Pair` we check:

~~~text
C sizeof(Pair)                  == Java PAIR.byteSize()
C offsetof(Pair, y)             == Java PAIR.byteOffset(groupElement("y"))
C _Alignof(Pair)                == Java PAIR.byteAlignment()
C type int width/alignment      == Java JAVA_INT width/alignment per ABI
~~~

The example's C file applies `_Static_assert` for width, alignment, size, and offset. Java checks size/offset before using `Pair` by-value. For more complex structs, **all necessary offsets** and alignment must be checked, not just the last field.

### 11.2. Why does GroupLayout affect the calling convention?

On a 64-bit ABI, a small struct may be classified into groups passed via general-purpose registers, floating-point/SIMD registers, or the stack. A struct containing two `int`s is often passed differently from a struct containing two `double`s. A large struct may also use a hidden return buffer.

The C linker does not rely on the Java name `"Pair"`; it relies on **size, alignment, and layout members**. If you describe a struct with wrong padding or replace `double` with `long`, native ABI classification may differ and the call becomes unsafe even if `byteSize()` is the same.

### 11.3. C bitfields, packed structs, and unions

C bitfields have compiler/ABI-dependent layouts; Java `MemoryLayout` does not automatically understand every bitfield convention in C source. Some packed structs have alignment smaller than natural alignment and **not every native linker supports** passing/returning them by-value. The linker may throw `IllegalArgumentException` when a descriptor has an unsupported group layout, but not every ABI error is caught.

When encountering complex types, consider a C wrapper under your control that converts them to a simpler interface such as scalar parameters or a pointer to a clearly declared struct, accompanied by explicit allocation/deallocation APIs.

**Do not replace by-value with a pointer in Java while keeping the C prototype unchanged**; if you need to simplify the ABI, you must write a C wrapper **that actually has the new prototype** and bind Java to that wrapper.

## 12. invokeExact pitfalls and debugging MethodType

`MethodHandle.invokeExact` is signature-polymorphic: the call site is bound by the **static types of the argument/return expressions**. Common mistakes:

| Wrong call | Why it is wrong | Fix |
|---|---|---|
| `add.invokeExact(a,b)` | Missing `SegmentAllocator` prefix for group return | `add.invokeExact(allocator,a,b)` |
| `add.invokeExact(arena,a,b)` when `arena` has static type `Arena` | Handle expects `SegmentAllocator`, `invokeExact` does not auto-upcast | Declare `SegmentAllocator allocator = arena` or cast |
| `int x = (int) add.invokeExact(...)` | Handle return is `MemorySegment`, not `int` | Cast `(MemorySegment)` then read field |
| `sum.invokeExact(allocator,pair)` | Function returns scalar, no allocator prefix | `int n = (int) sum.invokeExact(pair)` |
| `shift.invokeExact(allocator,pair,1,2)` | Void function taking pointer, no group return | `shift.invokeExact(pair,1,2)` |
| `make.invokeExact(allocator,7L,8L)` | C `int` maps to Java `int`, not `long` | Pass `7,8` of type `int` |
| Using `FunctionDescriptor.of(ADDRESS, PAIR, PAIR)` for C `Pair` return | Mixes up pointer return and by-value | Use `FunctionDescriptor.of(PAIR, PAIR, PAIR)` |
| Using `FunctionDescriptor.ofVoid(PAIR, PAIR)` when C returns `Pair` | Wrong return ABI | Use `of(PAIR, PAIR, PAIR)` or the real signature |

Safe debugging tip, in a real program:

~~~java
System.out.println(add.type());
System.out.println(sum.type());
System.out.println(shift.type());
~~~

This is a **snippet**, requiring three validly linked handles. Compare `handle.type()` with `MethodType.methodType(...)` before invoking, as the full code does.

If unsure about a C signature, check the **actual C header**, do not guess from the number of Java parameters that appear. The `SegmentAllocator` parameter and the function address for an unbound handle are FFM *virtual parameters*, not the C parameter list.

## 13. Common runtime errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| `WrongMethodTypeException` | Missing allocator; incorrect `Arena` cast; wrong return carrier; confusing bound/unbound | Print `handle.type()`, compare each type and order |
| `IllegalArgumentException` when creating downcall | Struct layout/ABI unsupported by linker, wrong descriptor, or symbol is not a native address | Check `Linker`, layout, native symbol, and ABI |
| `NoSuchElementException` from `find(...).orElseThrow()` | C symbol name not exported or wrong library version | Check `nm`/`dumpbin` and loaded library file |
| Library load failure | Wrong path, OS/architecture, native dependency | Build for the right platform and use an absolute path |
| `IllegalCallerException` / restricted native access warning | Module lacks native permission | Use `--enable-native-access=ALL-UNNAMED` for classpath or the appropriate module |
| `IllegalStateException` when reading result | Allocator arena is already closed | Read/copy result while arena is alive |
| `WrongThreadException` | Confined segment used from a non-owning thread | Use owner thread or shared arena with synchronization management |
| Scrambled field results | StructLayout has wrong padding, offset, type, or alignment | Verify against `sizeof`/`offsetof`/`_Alignof` |
| JVM crash or memory corruption | Wrong C ABI signature, passing ADDRESS instead of group, or invalid pointer | Compare native header and descriptor; do not keep testing with real data |
| Earlier result overwritten by later result | Custom allocator returns overlapping memory | Use separate Arena or an allocator guaranteeing non-overlap |
| Native memory steadily growing | Using global allocator for every call, forgetting to close bounded arenas | Apply try-with-resources and memory budgets |
| Wrong return cast | Confusing `MemorySegment` with `int`/Java POJO | Receive `MemorySegment`, read via layout/VarHandle |
| C compiler reports `_Static_assert` failure | Platform does not meet example's assumptions | Adjust layout and ABI after understanding compiler target; do not delete assertions |

**A native call with the wrong ABI does not necessarily throw a clear Java exception.** It can crash the JVM before Java has a chance to handle it. Use layout/handle type checks and run integration tests on the exact deployment OS/CPU/compiler.

### 13.1. What should automated tests cover?

At minimum, test:

1. `pair_size`, `pair_offset_y`, and `_Alignof` from the native side match the Java layout.
2. `add.type()` has exact one `SegmentAllocator` prefix when the result is a `StructLayout`.
3. `sum.type()` **does not** have an allocator prefix even though it takes a struct.
4. Inputs and results are correct for positive, negative, and zero cases within the non-overflowing C int range.
5. `pair_tweak_copy` does not mutate the caller's struct; `pair_shift` does mutate it when passing `Pair*`.
6. Results are not used after the arena closes; if results must be returned up to Java layers, copy fields into Java records/primitives before closing.
7. Run on target platforms, including Linux/macOS/Windows CI if the product supports them, not just one compiler.
8. When supporting packed/union/complex structs, test offsets, sizes, alignment, and ABI classification of those specific types.

## 14. Practical API design: when should a struct be returned by-value?

By-value is usually suitable for small, stable structs with clear ABIs, such as coordinates, 2D vectors, colors, C timestamps, or small records. Advantages: clear C semantics, does not force the caller to manage pointers to callee-allocated memory, and Java can receive the value using `SegmentAllocator`.

However:

- Large structs may incur copy overhead or be placed into a hidden result buffer by the ABI.
- Some complex ABIs are not supported by every FFM linker.
- Structs with pointers inside still carry **their own ownership issues**. The struct itself by-value may be copied, but pointer fields inside **are not deep-copied**; do not assume the entire object graph is safe.
- Structs containing unions/bitfields/special packing can be hard to describe portably.
- If a large struct needs to be mutated directly where the caller already allocated it, sometimes an explicit C API taking `Pair*`/`void*` is more appropriate — **provided the C prototype is designed that way from the start**.

The choice between by-value and by-pointer should be based on the **native library's contract**. FFM does not allow swapping them just because both cases use the `MemorySegment` carrier in Java.

### 14.1. Struct return containing a pointer: returning by-value still does not solve ownership

C example:

~~~c
typedef struct {
    const char *data;
    size_t length;
} BufferView;
~~~

This is a **snippet**, not a runnable library. Even when `BufferView` is returned by C by value and Java receives the segment using `SegmentAllocator`, the `data` member inside is still a **native pointer**.

- Java must know whether `data` actually points to `length` valid bytes.
- The owner could be the C library, the caller, a file mapping, or a handle.
- `SegmentAllocator` only allocates storage for the **copy of the struct metadata** (pointer + length), and does not automatically copy all the bytes pointed to by `data`.
- Closing the allocator frees the storage of the **struct result**, and does not automatically call a deallocator for C pointer fields.

This is a common architectural mistake when lifting an API with complex pointer ownership to FFM. If an independent string/array is needed, copy the data into Java-owned memory or establish a clear contract for native lifetime.

## 15. SegmentAllocator, Arena, JNI, and JDK versions

Final FFM was released in **JDK 22** via **JEP 454**. JDK 21 had **FFM third preview (JEP 442)**; if you need to run JDK 21 preview source, preview flags are required and API signatures must be checked against JDK 21. Do not take JDK 22 final FFM source, just change `--release 21`, and expect it to compile.

For the files in this lesson, run with JDK 22:

~~~bash
javac --release 22 StructByValueDemo.java
java --enable-native-access=ALL-UNNAMED StructByValueDemo
~~~

**`--enable-native-access` is not `--enable-preview`.** FFM in 22 does not need preview, but creating downcall handles and library lookups are restricted operations. Warning/deny policies may change in newer JDKs; production execution should grant permissions per module according to official runtime documentation.

In **JNI**, an author can pass `jobject` or manipulate fields via `JNIEnv`, but when interfacing directly with C struct by-value, an appropriate C wrapper must be written. FFM creates downcall handles from C signatures and `MemoryLayout`, reducing JNI glue for many C ABI operations. It **does not make the C ABI self-describing**: you must still accurately verify struct layout, ownership, and calling conventions.

## 16. Self-practice

1. For `Pair pair_add(Pair, Pair)`, what is the appropriate `FunctionDescriptor`? Why not use `ADDRESS` for the two arguments?
2. For `int pair_sum(Pair)`, why does the bound `MethodHandle` **not have a `SegmentAllocator`**?
3. Where does `SegmentAllocator` appear in a bound handle returning `Pair`? Is it in the C prototype?
4. When using `invokeExact`, why can passing a variable with static type `Arena` throw `WrongMethodTypeException` even though `Arena implements SegmentAllocator`?
5. If `Pair pair_make(int,int)` is changed to `Pair* pair_make(int,int)` in C, how must the descriptor and Java ownership change?
6. Does `MemoryLayout.structLayout(...)` automatically insert 7 bytes of padding after `char` before `double` on every ABI?
7. Why is matching `sizeof(struct)` alone not enough to confirm the field layout is correct?
8. A struct returned by-value contains `char* data`: does closing the `Arena` used for the return automatically `free(data)`?
9. Should `Arena.global()` be passed as the return allocator for an API called thousands of times per second? Why?
10. What is the difference between `Pair change_copy(Pair)` and `void change_pointer(Pair*)`?
11. If a handle is created with `linker.downcallHandle(descriptor)` instead of `linker.downcallHandle(symbol, descriptor)`, what extra parameter is needed at invoke time?
12. When the C compiler puts a struct return into registers or a hidden pointer, who is responsible for performing the ABI conversion?
13. Why must you not keep a `MemorySegment result` from a confined arena and read it after the arena closes?
14. If the native linker rejects a packed struct, what is a better approach than "changing every group layout to ADDRESS"?
15. Why are checking `MethodHandle.type()` and the native `sizeof`/`offsetof` functions two separate layers of checks that are both necessary?
16. Extend the `Pair` example with `Pair pair_sub(Pair,Pair)`: what changes are needed in the C file, `FunctionDescriptor`, `MethodHandle`, and `invokeExact` call?

**Conclusion:** When a C function **accepts a struct by value**, use an **ABI-valid `StructLayout`** in the argument position of `FunctionDescriptor` and pass a `MemorySegment` in Java. When a C function **returns a struct by value**, the downcall handle has an extra **`SegmentAllocator`** on the Java side to allocate storage for the result; the C prototype **does not** have this argument. Conversely, C `Pair*` uses **`ValueLayout.ADDRESS`** and has its own pointer/ownership semantics. Always verify `sizeof`, offsets, alignment, `MethodHandle.type()`, and arena lifecycle before trusting that an interop program is correct.

### Official documentation

- [Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): C ABI, group/struct layout support, downcall handle type, and the extra `SegmentAllocator` parameter for group returns.
- [Java SE 22 — SegmentAllocator](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SegmentAllocator.html): allocation contract and role as return allocator.
- [Java SE 22 — MemoryLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html): `structLayout`, padding, alignment, `byteSize`, `byteOffset`, and VarHandle access.
- [Java SE 22 — StructLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/StructLayout.html): group layouts arranging members in order.
- [Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): bounded scope, lifetime, and cleanup for FFM allocations.
- [Java SE 22 — Foreign Function & Memory API Developer Guide](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html): memory layout and native downcalls.
- [JEP 454 — FFM Final](https://openjdk.org/jeps/454): finalized release in JDK 22.
- [JEP 442 — FFM Third Preview](https://openjdk.org/jeps/442): preview status in JDK 21.
