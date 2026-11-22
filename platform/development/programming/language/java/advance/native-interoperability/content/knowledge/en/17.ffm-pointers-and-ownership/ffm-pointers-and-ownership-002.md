# Distinguishing the segment containing an address from the memory region the address points to

## 1. Two different memory regions that can appear in a pointer access

When programming in Java with the Foreign Function & Memory API (FFM API), the statement `slot.get(ValueLayout.ADDRESS, 0)` is very easy to misunderstand. It **reads an address value (pointer value) from the memory region `slot`**, rather than meaning `slot` itself is the data region that the address points to.

Three entities must be distinguished:

1. **Pointer slot** — the memory region *containing the bytes representing an address*, with a size usually equal to `ValueLayout.ADDRESS.byteSize()`. It is equivalent to a storage cell for a pointer variable `int *p` in the C model.
2. **Pointer value / address segment** — the value read from the slot using `get(ValueLayout.ADDRESS, offset)`. Java represents this address value with a `MemorySegment`; normally the resulting segment has **`byteSize() == 0`**, because the JVM does not yet know how wide the target region is.
3. **Pointee / target region** — the real memory region at the address just read, for example three consecutive 32-bit integers. The target region has its own size, access permissions, lifetime, and **owner**. To read data in this region, a segment view with the correct memory bounds is needed, and it must be ensured that the memory region is actually still valid.

Illustrative diagram on a 64-bit pointer platform:

```text
Region A: pointer slot (8 bytes)             Region B: pointee (12 bytes)
illustrative address 0xA000                  illustrative address 0xB000
┌──────────────────────────┐                  ┌────────┬────────┬────────┐
│ stores pointer val 0xB000├───────────────►  │ int 10 │ int 20 │ int 30 │
└──────────────────────────┘                  └────────┴────────┴────────┘
 ^                                             ^
 |                                             |
 slot.address() = 0xA000                       data.address() = 0xB000
 slot.byteSize() = 8                           data.byteSize() = 12

slot.get(ValueLayout.ADDRESS, 0) returns an address segment:
  address()  = 0xB000
  byteSize() = 0 (if ADDRESS has no target layout)
```

**The addresses 0xA000 and 0xB000 are for illustration only**, not actual addresses or guaranteed values when running the program.

Key point: **the address *of* the pointer slot** and **the address value *stored in* the pointer slot** are two different numbers. A segment containing a pointer is not automatically the segment of the memory region that the pointer points to.

### 1.1. Connection to C/C++

```c
int values[3] = {10, 20, 30};
int *p = values;

int first = *p;         /* 10: read data at address p */
int second = p[1];      /* 20: read the next element */
int **pp = &p;          /* pp is the address of pointer variable p */
int viaTwoLevels = **pp;/* 10: traverse two levels of pointers */
```

This is a **C fragment**, not a C file with `main()`. The relationships:

- `&p`: the address where the pointer variable `p` is stored (the level that holds the address).
- `p`: the address value pointing to `values[0]`.
- `*p`: the data at the target region (`values[0]`).
- `pp`: pointer-to-pointer; two levels must be traversed to reach the `int` value.

In FFM, `MemorySegment` can play the role of *slot*, *address wrapper*, or *data view*, depending on how it is created and which API is called. **Having the same Java type `MemorySegment` does not mean having the same purpose or the same ownership.**

> **Version:** This article uses `java.lang.foreign` from **JDK 22+** (official FFM API since JDK 22, JEP 454). JDK 17 does not have the same stable API. Examples using `reinterpret`/`withTargetLayout` are **restricted methods**, which require enabling native access; do not use these JDK 22 snippets verbatim with JDK 17.

## 2. Comparison table: slot, address value, and pointee

| Characteristic | Pointer slot `slot` | Address segment `p` read from slot | Target segment `data` |
| --- | --- | --- | --- |
| Represents | Bytes storing a pointer value | Address retrieved from the pointer value | Actual data bytes pointed to |
| Sample creation source | `arena.allocate(ValueLayout.ADDRESS)` | `slot.get(ValueLayout.ADDRESS, 0)` | `arena.allocate(...bytes...)` |
| `address()` | Address **of the slot** | Address **stored in the slot** | Address **of the data** |
| `byteSize()` | `ADDRESS.byteSize()` | Normally **0**, if there is no target layout | Data size, e.g., 12 bytes |
| Reading type `int` at offset 0 | Reads **bytes of the pointer value**, not the pointee | Rejected due to size 0 | Reads `int` data of the pointee |
| Lifetime | Follows the slot's arena/owner | Default wrapper is attached to **global scope** | Follows the target's arena or native allocator |
| Deallocation | Frees *the region storing the pointer* | Does not automatically own/free the target | Follows the target's actual owner/allocator |

`ValueLayout.ADDRESS` is an `AddressLayout`, with the size/alignment of the address depending on the platform (for example, 8 bytes on common 64-bit systems). **Do not hard-code 8** for all systems.

### 2.1. `segment.address()` is not `segment.get(ADDRESS, 0)`

These two statements do different things:

```java
long addressOfSlot = slot.address();

MemorySegment storedAddress =
        slot.get(ValueLayout.ADDRESS, 0L);
long addressOfTarget = storedAddress.address();
```

This is a **fragment** assuming `slot` is a live native memory segment, wide enough and aligned to hold a valid address. `addressOfSlot` is the storage location of the pointer, whereas `addressOfTarget` is the pointer value read out. Do not use `address()` of a heap segment as a C address: the address of a heap segment is virtualized and may be 0, not a stable pointer that can be arbitrarily passed to C.

### 2.2. A pointer value does not carry size information

In C, `int *p` does not contain the `sizeof` of the target array. When FFM reads a pointer via `ValueLayout.ADDRESS`, Java also does not automatically know whether it points to one `int`, 3 `int`s, a C struct, or a memory region that has already been freed.

Therefore, JDK 22 by default returns a **zero-length native segment** from a newly read pointer:

```java
MemorySegment raw = slot.get(ValueLayout.ADDRESS, 0L);

System.out.println(raw.byteSize()); // 0
```

By default, `raw` has **global scope**, and does not automatically inherit the lifetime of `slot` or of the target region. The global scope of the *wrapper* **does not mean the target data lives forever**.

If you try:

```java
// Fragment illustrating an error if raw is a zero-length segment.
int x = raw.get(ValueLayout.JAVA_INT, 0L);
```

the operation is rejected because `raw.byteSize() == 0`, so there are not enough 4 bytes to read an `int`. Expect an `IndexOutOfBoundsException`, **not** an automatic read of the target region.

This is an intentional safety barrier: to dereference a pointer, the programmer must provide information about size and lifetime, instead of having the JVM guess.

## 3. Three key operations with AddressLayout

### 3.1. `set(ADDRESS, offset, value)` writes an **address value**

```java
MemorySegment slot = arena.allocate(ValueLayout.ADDRESS);
MemorySegment data = arena.allocate(
        ValueLayout.JAVA_INT.byteSize(),
        ValueLayout.JAVA_INT.byteAlignment());

data.set(ValueLayout.JAVA_INT, 0L, 123);
slot.set(ValueLayout.ADDRESS, 0L, data);
```

This is a fragment using a live `Arena arena`. `slot.set(ADDRESS, 0, data)` **copies the address value of `data` into the memory region `slot`**. It does not copy the 4 bytes of the number `123` into the slot, does not create new data memory, and does not transfer ownership from the arena to the slot.

### 3.2. `get(ADDRESS, offset)` reads the address value into a MemorySegment

```java
MemorySegment addressValue =
        slot.get(ValueLayout.ADDRESS, 0L);
```

`addressValue.address()` is the address stored in the slot, usually equal to `data.address()` in the example above; **`addressValue.byteSize() == 0`** because the layout is only `ValueLayout.ADDRESS` without a target layout.

Note that `addressValue` **is not** `data`: it is merely a new wrapper representing the same address. The two segments may have different sizes and scopes. Reading/writing a correct address does not make Java detect the allocator, bounds, or free permissions of the target.

### 3.3. `get(JAVA_INT, offset)` on the slot reads the pointer's bytes, not dereferencing

```java
// SEMANTICALLY WRONG if the goal is the int value in data:
int notPointee = slot.get(ValueLayout.JAVA_INT, 0L);
```

If alignment/bounds allow, this statement reads **the first 4 bytes of the region storing the address** and interprets them as an `int`. The value depends on the platform/address layout and is not `data.get(JAVA_INT, 0)`. **Do not use this method to convert a pointer to an `int`**, and do not treat it as a way to dereference.

The correct access path must have a **segment view to the target** with a valid size/lifetime, such as the original `data` still being in scope, or a view intentionally created from the pointer.

## 4. Complete JDK 22+ example: one slot holding a pointer, one region holding data

The example creates an array of 3 `int`s in native memory, creates a separate pointer slot, writes the array's address into the slot, reads the address, and then **explicitly widens the view** to access the target. The program shares `Arena.ofConfined()` for both allocations, so **the target's lifetime is clearly known in the demo**.

File **`PointerSlotDemo.java`**:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class PointerSlotDemo {
    public static void main(String[] args) {
        var intLayout = ValueLayout.JAVA_INT;

        try (Arena arena = Arena.ofConfined()) {
            // Target region: 3 int values (12 bytes).
            MemorySegment data = arena.allocate(
                    3L * intLayout.byteSize(),
                    intLayout.byteAlignment());

            data.setAtIndex(intLayout, 0L, 10);
            data.setAtIndex(intLayout, 1L, 20);
            data.setAtIndex(intLayout, 2L, 30);

            // Region holding 1 pointer, not the 3-int region.
            MemorySegment slot =
                    arena.allocate(ValueLayout.ADDRESS);

            // Write the ADDRESS of data into slot.
            slot.set(ValueLayout.ADDRESS, 0L, data);

            // Read the pointer VALUE stored at slot.
            MemorySegment addressValue =
                    slot.get(ValueLayout.ADDRESS, 0L);

            System.out.println(
                    "slot has one pointer: " +
                    (slot.byteSize() ==
                            ValueLayout.ADDRESS.byteSize()));
            System.out.println(
                    "slot and data separate: " +
                    (slot.address() != data.address()));
            System.out.println(
                    "stored pointer targets data: " +
                    (addressValue.address() == data.address()));
            System.out.println(
                    "address view bytes: " +
                    addressValue.byteSize());

            // Zero-length pointer wrapper cannot read int.
            try {
                addressValue.get(intLayout, 0L);
            } catch (IndexOutOfBoundsException ex) {
                System.out.println(
                        "direct read of zero-length view: rejected");
            }

            // RESTRICTED: valid only because we KNOW data was allocated
            // by arena with exactly 12 bytes and has not been freed.
            MemorySegment targetView = addressValue.reinterpret(
                    data.byteSize(), arena, null);

            System.out.println(
                    "target int[1] via pointer: " +
                    targetView.getAtIndex(intLayout, 1L));

            // targetView and data look at the same data region.
            targetView.setAtIndex(intLayout, 2L, 99);
            System.out.println(
                    "original data int[2]: " +
                    data.getAtIndex(intLayout, 2L));

            // Clear the pointer VALUE in slot, does not free data.
            slot.set(ValueLayout.ADDRESS, 0L, MemorySegment.NULL);
            System.out.println(
                    "slot is NULL: " +
                    (slot.get(ValueLayout.ADDRESS, 0L)
                            .address() == 0L));

            System.out.println(
                    "data still valid: " +
                    data.getAtIndex(intLayout, 2L));
        }
        // Close arena: data and slot end their lifetimes together.
    }
}
```

Use **JDK 22+**:

```bash
javac PointerSlotDemo.java
java --enable-native-access=ALL-UNNAMED PointerSlotDemo
```

`reinterpret(...)` is a **restricted method** in JDK 22, so the run command enables native access for classes not belonging to a named module using `--enable-native-access=ALL-UNNAMED`. In a modularized application, grant native access to **the exact module that needs it**, instead of opening everything when unnecessary. Do not ignore restricted-method warnings/errors because this is the control boundary for raw memory access.

**Expected stdout** (not printing specific addresses to avoid platform dependence):

```text
slot has one pointer: true
slot and data separate: true
stored pointer targets data: true
address view bytes: 0
direct read of zero-length view: rejected
target int[1] via pointer: 20
original data int[2]: 99
slot is NULL: true
data still valid: 99
```

### 4.1. Why are the three values above independent of pointer size?

- `slot.byteSize() == ValueLayout.ADDRESS.byteSize()` is true on every platform if `arena.allocate(ValueLayout.ADDRESS)` succeeds.
- `data.byteSize() == 3 * JAVA_INT.byteSize() == 12`; data and slot are two separate allocations, alive at the same time, so their starting addresses are different.
- `addressValue.address() == data.address()` because `set(ADDRESS, 0, data)` wrote the native address of data itself.
- `addressValue.byteSize() == 0` because `get` used ADDRESS **without a target layout**.
- Both `getAtIndex(intLayout, 1)` on the target view and on data access byte offset 4 of the same memory region, returning `20`.
- Setting `int[2] = 99` through the target view modifies **the data allocation itself**, without creating a new array.
- Writing `MemorySegment.NULL` into slot makes **the pointer value** in slot equal to 0. It **does not free the data allocation**, so `data.getAtIndex(..., 2)` still returns `99` until the arena closes.

**Do not use `targetView` after the arena closes.** Calling `reinterpret(..., arena, null)` to bind the temporal bounds of the view to the arena only protects when the lifetime actually matches; it does not create or transfer ownership of the target bytes.

## 5. `reinterpret`: intentionally declaring the target memory region, without allocating

JDK 22 provides `MemorySegment.reinterpret(...)` to create a view with different spatial/temporal bounds. Specifically:

```java
MemorySegment zeroLength =
        slot.get(ValueLayout.ADDRESS, 0L);

// Target data is actually N bytes wide and still alive:
MemorySegment view = zeroLength.reinterpret(
        N, arena, null);
```

This is a **fragment**, assuming `slot` contains a **non-NULL, valid** pointer, `N` is a length verified from the contract, and `arena` actually models the lifetime of the target region. `reinterpret` is marked **restricted**; native access must be enabled.

### 5.1. What changes and what does not change?

| Property | After `reinterpret(N, arena, null)` |
| --- | --- |
| Starting address | **Does not change**; still the pointer address that was read |
| `byteSize()` | Becomes `N` |
| Lifetime scope | Attached to the provided `arena.scope()` |
| Thread confinement | Follows the properties of the new arena |
| Does it copy data? | **No** |
| Does it create a new allocation for the pointee? | **No** |
| Does it verify the address points to N real bytes? | **No** |
| Does it automatically take ownership to free the original memory? | **No** unless a valid cleanup is registered; must still be managed by the real owner |

`reinterpret` gives the JVM an *assumption* about size and lifetime. If the assumption is wrong, virtual bounds do not prevent accessing an address that has already been freed or does not belong to the process. The consequence can be **native memory corruption or a JVM crash**, not necessarily just a Java exception.

### 5.2. Risks of `reinterpret(long)` without an arena

```java
// Fragment only for API comparison; do not execute
// on a pointer not yet proven to be valid.
MemorySegment widened = rawPointer.reinterpret(16L);
```

The `reinterpret(long)` overload creates a native segment with the same address and scope as the pointer wrapper. For a pointer read via `get(ADDRESS, 0)`, the default scope is **global scope**. Therefore, the view has size 16 but **does not automatically know** which arena the pointee belongs to or when it is freed.

If the target region belongs to an `Arena.ofConfined()` that has already closed, `widened` still carries the global scope and may allow an unsafe access to a reclaimed region. **Prefer a view with the proper scope** when the contract allows, and most importantly, manage the owner so the pointee is not freed while the view is in use.

### 5.3. Do not attach an arbitrary arena

If a pointer comes from C `malloc`, you cannot attach `reinterpret(size, arbitraryArena, null)` and assume closing that arena will automatically call the right `free`. If the pointer points to memory managed by another library (database, GPU, mapped buffer, SDK callback), the user must also respect that library's contract.

For example, a public C API:

```c
/* C fragment illustrating ownership contract: */
void *library_allocate(size_t bytes);
void library_release(void *p);
```

Java can create a view with the appropriate size, but to deallocate it must **call `library_release` according to the contract**. Do not call generic `free` if the library uses its own allocator. FFM cleanup callbacks must be designed carefully to avoid freeing while other users remain or double-freeing.

## 6. `AddressLayout.withTargetLayout`: providing the target size directly on the layout

If the **static target layout** is known, the pointer → pointee relationship can be described on `AddressLayout`:

```java
import java.lang.foreign.AddressLayout;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.ValueLayout;

// Fragment: pointer to exactly 3 consecutive ints.
AddressLayout pointerToThreeInts =
        ValueLayout.ADDRESS.withTargetLayout(
                MemoryLayout.sequenceLayout(
                        3, ValueLayout.JAVA_INT));

// slot contains a valid native target address, at least 12 bytes:
MemorySegment target = slot.get(
        pointerToThreeInts, 0L);

System.out.println(target.byteSize()); // 12
```

**`withTargetLayout(...)` is also a restricted method** in JDK 22, requiring native access. With target layout `T`, `slot.get(addressLayoutWithT, offset)` will return a segment with `byteSize() == T.byteSize()` instead of 0, while also checking the alignment of the read address against the target layout.

Do not interpret "having a target layout" as "FFM knows the allocator":

- The target layout defines **the shape/size** that you assert yourself.
- The returned segment is still attached to **global scope** according to address-reading rules, and does not automatically inherit the target's owner.
- If the pointer is actually NULL, dangling, shorter than the layout, unaligned, or of the wrong kind, the target layout **cannot prove the memory is valid**.
- If you want the scope attached to an arena proven to be the corresponding owner/lifetime, consider `reinterpret(..., arena, null)` according to the policy for using restricted methods.
- Do not specify a target layout with 3 ints if the function returns a pointer to only **1 int** or a buffer smaller than 12 bytes.

Therefore, `withTargetLayout` is useful for describing the pointer type *when the contract is clear*, not as a way to automatically solve ownership/lifetime issues.

### 6.1. When to use `withTargetLayout` instead of `reinterpret`?

| Case | Recommendation |
| --- | --- |
| C struct has field `int *ptr` known for sure to point to one `int` | `ADDRESS.withTargetLayout(JAVA_INT)` can express the shape |
| Returning a runtime-length array from C (`pointer + length`) | Read zero-length pointer; verify `length`; `reinterpret(length * elementSize, ownerArena, null)` if lifetime contract matches |
| Opaque handle not allowed to be dereferenced | **Do not** create a target layout; keep zero-length segment and pass the handle back to C |
| Pointer to memory that C will modify or free asynchronously | Requires synchronization/lifetime protocol; target layout cannot solve this |
| Pointer-to-pointer | Unwrap each layer: pointer layout for the intermediate slot, then read the final pointer and determine the target |

### 6.2. Target layout and endianness/alignment

A pointer to a data region does not say whether the target bytes are big-endian or little-endian. When reading a native `int`, `ValueLayout.JAVA_INT` uses native byte order by default. If a C API returns a buffer containing network-order values, a layout with `withOrder(BIG_ENDIAN)` must be used per the contract. Similarly, a C `struct` with padding/stride must be accurately described using `MemoryLayout`, not inferred from having `ADDRESS`.

## 7. Null pointer: `MemorySegment.NULL`, not Java `null`

In FFM JDK 22, `MemorySegment.NULL` is a **zero-length native segment with `address() == 0L`**. This is the representation of a C NULL pointer.

```java
slot.set(ValueLayout.ADDRESS, 0L, MemorySegment.NULL);

MemorySegment pointer =
        slot.get(ValueLayout.ADDRESS, 0L);

boolean isNullPointer = pointer.address() == 0L;
```

This is a fragment, with `slot` valid. `pointer` is a **Java object of type `MemorySegment`**, not `null` in Java. Comparing `pointer == null` is not the way to check for a C NULL pointer in this case.

**Mandatory NULL check before dereferencing**:

```java
MemorySegment pointer =
        slot.get(ValueLayout.ADDRESS, 0L);

if (pointer.address() == 0L) {
    throw new IllegalStateException(
            "Native function returned a NULL pointer");
}

// Proceed only when there is a sufficient contract on size and lifetime.
// Do not arbitrarily reinterpret an unknown address.
```

A non-zero pointer **does not guarantee** it points to a live allocation. It could be a dangling pointer, an unreadable address, an opaque handle, or a pointer only valid during a short callback.

### 7.1. Does a NULL pointer slot mean the slot region does not exist?

No. `slot` is still an allocation containing bytes (for example 8 bytes). It is merely storing the number 0 in the pointer cell. Writing `MemorySegment.NULL` into the slot is completely different from closing the arena containing the slot.

In C, `p = NULL` does not automatically free the old `malloc`; if no reference to the allocation remains, it can lead to a **memory leak**. In Java FFM, `slot.set(ADDRESS, 0, NULL)` also does not automatically free the target.

## 8. Ownership and lifetime: a live slot does not mean a live pointee

This is the most important distinction after understanding the two address levels. There can exist **two arenas** or two independent allocators:

```text
Arena A (owns pointer slot)         Arena B (owns pointee)
        │                                   │
        ▼                                   ▼
     slot ------------------------------► data
        │                                   │
        │ still alive                       │ already closed/freed
        ▼                                   ▼
Can read pointer value              Target region MUST NOT be accessed
but that pointer may be dangling.
```

Conceptual scenario example:

```java
// Fragment with two independent arenas, DO NOT dereference after close:
Arena slotArena = Arena.ofConfined();
Arena dataArena = Arena.ofConfined();

MemorySegment slot =
        slotArena.allocate(ValueLayout.ADDRESS);
MemorySegment data =
        dataArena.allocate(ValueLayout.JAVA_INT);

data.set(ValueLayout.JAVA_INT, 0L, 42);
slot.set(ValueLayout.ADDRESS, 0L, data);

dataArena.close();  // Pointee lifetime ends.

// slotArena is still open; the pointer value is still in slot.
// Strictly DO NOT reinterpret and dereference the stale pointer.
MemorySegment dangling =
        slot.get(ValueLayout.ADDRESS, 0L);

slotArena.close();
```

This is a **fragment illustrating the hazard only**, not a pattern to use in production. The variable `dangling` receives a physical address that was once valid, which does not mean the target is still alive. To handle this kind of scenario in practice, design clear owner and borrow durations; if the owner has already freed it, any dereference is forbidden.

### 8.1. A segment with global scope does not automatically keep the pointee alive

A pointer read with `get(ADDRESS, 0)` has global scope. That only says **the address wrapper is not closed by any arena**. It does not create a GC root or a reference to an allocation of `Arena.ofConfined()` and does not prevent a native library from freeing the memory region.

**Common mistake:** "`pointer.scope().isAlive()` is true, so the pointer is safe." When the wrapper has global scope, that check does not prove the target memory exists.

For targets allocated by a Java arena, keep a reference to the proper arena/owner and only access while the arena is alive. For pointers returned by C, follow the C API's documentation on ownership accurately; do not infer from the `MemorySegment` return type.

### 8.2. Owner, borrower, and ownership transfer

An API design should clearly state who deallocates:

| Situation | Who owns it? | What Java needs to do |
| --- | --- | --- |
| `arena.allocate(...)` | The arena that allocated it | Keep within the arena's lifetime; the arena closes and cleans up once |
| C returns a pointer to memory self-managed by the library | Native library | Use within the scope allowed by the library; **do not free it yourself** |
| C returns a pointer from `malloc` and requires the caller to call `free` | Caller per contract | Call the right deallocator (possibly `free`), at the right time, once |
| C returns an opaque handle | Native library managing hidden structure | Only pass the handle to public APIs; **do not dereference** |
| Java sends a buffer pointer for native to read temporarily | Java arena/owner | Ensure the segment remains alive until native finishes |
| C callback function provides a pointer valid only during the callback | Native callback lifetime | Copy the data if it must be kept for later; do not cache the pointer indefinitely |

**Do not infer "returned pointer = Java owns the data".** A `T*` field in a C struct often only represents a data link; the right to free must be described separately.

### 8.3. No double-free and no use-after-free

- If `data` was allocated by `Arena.ofConfined()`, do not call `free(data.address())` and then let the arena close and free it again.
- If a C native function requires `library_free(handle)`, do not replace it with `free(handle)` if the library has its own allocator.
- When converting from a raw pointer to a bounded view with `reinterpret`, **there is no hidden free call**. A cleanup callback can be registered with an arena via the appropriate API, but only when the owner contract grants permission and avoiding simultaneous cleanup elsewhere.
- Do not let an asynchronous native thread continue using the target when Java has already closed the arena; you must stop/drain/join or have a synchronization/ownership policy.

**Ownership is an API rule, and cannot be fully inferred from the address, size, or `MemorySegment` type.**

## 9. Pointer-to-pointer: from `int **` through two address reads

When C declares `int **pp`, the data follows two levels:

```text
ppSlot (contains address of pSlot)
      │
      ▼
pSlot (contains address of int value)
      │
      ▼
int value = 7
```

To read `**pp`, FFM must traverse **two pointer values** and only at the final step read `int`. If you call `ppSlot.get(JAVA_INT, 0)`, you will read the bytes of the address, not the value `7`.

### 9.1. Standalone Java 22+ example

File **`PointerToPointerDemo.java`**:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class PointerToPointerDemo {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment value = arena.allocate(
                    ValueLayout.JAVA_INT);
            value.set(ValueLayout.JAVA_INT, 0L, 7);

            MemorySegment pSlot = arena.allocate(
                    ValueLayout.ADDRESS);
            pSlot.set(ValueLayout.ADDRESS, 0L, value);

            MemorySegment ppSlot = arena.allocate(
                    ValueLayout.ADDRESS);
            ppSlot.set(ValueLayout.ADDRESS, 0L, pSlot);

            // *pp: read pSlot address (returns zero-length).
            MemorySegment pSlotAddress =
                    ppSlot.get(ValueLayout.ADDRESS, 0L);

            // Need to know pSlot is actually ADDRESS.byteSize() wide.
            MemorySegment pSlotView = pSlotAddress.reinterpret(
                    ValueLayout.ADDRESS.byteSize(), arena, null);

            // *p: next read value address (returns zero-length).
            MemorySegment valueAddress =
                    pSlotView.get(ValueLayout.ADDRESS, 0L);

            // **pp: create view of exact sizeof(int), then read int.
            MemorySegment valueView = valueAddress.reinterpret(
                    ValueLayout.JAVA_INT.byteSize(), arena, null);

            System.out.println(
                    "**pp = " + valueView.get(
                            ValueLayout.JAVA_INT, 0L));
        }
    }
}
```

Commands with JDK 22+:

```bash
javac PointerToPointerDemo.java
java --enable-native-access=ALL-UNNAMED PointerToPointerDemo
```

Stdout:

```text
**pp = 7
```

**Safety conditions of the demo:** each allocation is created by **the same arena**, has a known size/alignment, and remains alive throughout the entire access process. In a real program, if a pointer at one level comes from a native library or from file bytes, you **must not by default** widen the view without verifying the target region's contract.

### 9.2. Pointer arrays and element index

If a segment stores **an array of pointers**, then:

```java
// Fragment: pointerArray contains n consecutive native pointer slots.
MemorySegment ptr = pointerArray.getAtIndex(
        ValueLayout.ADDRESS, index);
```

`index` is the index of the **pointer slot**, multiplied by `ValueLayout.ADDRESS.byteSize()` (4 or 8 bytes depending on the platform). It is **not** the index of the `int` element in the pointee. To access the `j`-th `int` element of the array pointed to by that pointer, you must have an appropriate bounded target view, and only then call `targetView.getAtIndex(JAVA_INT, j)`.

## 10. Changing a pointer in a slot does not make old views automatically change targets

Suppose:

```java
// Fragment: dataA/dataB/slot are all valid allocations.
slot.set(ValueLayout.ADDRESS, 0L, dataA);
MemorySegment oldPointer =
        slot.get(ValueLayout.ADDRESS, 0L);

slot.set(ValueLayout.ADDRESS, 0L, dataB);
MemorySegment newPointer =
        slot.get(ValueLayout.ADDRESS, 0L);
```

`oldPointer.address()` is still the address of **dataA** read at the earlier time; `newPointer.address()` is the address of **dataB** after the change. The two view objects are **not** a pointer capable of "automatically tracking" future changes to the slot.

This is why it is worth distinguishing:

- **Pointer slot:** a location that can be overwritten with another address.
- **Snapshot pointer value:** the address value read at a point in time.
- **Target view:** the memory region that the snapshot pointer is interpreted to point to, with its own lifetime conditions.

If a C native thread modifies the slot remotely while Java is reading, a **data race and synchronization** problem also arises; using `MemorySegment` does not replace locks, volatile/atomic protocols, or thread constraints of the native library.

## 11. Opaque handles: have an address but must not be dereferenced

Many C APIs do not return a pointer to a public structure, but instead return `void *handle` or `struct Engine *` with a private definition. Java can represent the handle as a `MemorySegment` with an address and pass it back to a downcall, but **should not `reinterpret` and randomly read fields**.

Example C contract:

```c
/* C API fragment, no implementation yet. */
typedef struct Engine Engine;

Engine *engine_create(void);
void engine_run(Engine *engine);
void engine_destroy(Engine *engine);
```

`Engine *` is an opaque handle. Java FFM can store the pointer from `engine_create` as a segment without target bounds, use it as an argument to `engine_run`, and then call `engine_destroy` exactly once per the contract.

**It cannot be inferred** that `Engine` has a field at offset 0 or has a size of 64 bytes just from the handle value. `withTargetLayout` or `reinterpret` does not turn a private C struct into a valid layout. Let the native library own and access the hidden data.

### 11.1. A C pointer value is not a Java object reference

A `MemorySegment` containing a raw native address **is not** a JNI `jobject` handle, and is not a Java heap object. In JNI, `jobject` is managed by the JVM and has local/global reference and GC rules; you must not arbitrarily cast a `MemorySegment` address to a `jobject` or vice versa.

- A Java heap array can be moved by the GC.
- `MemorySegment.ofArray(byte[])` does not represent a fixed C address that can be passed via `ADDRESS` as a native pointer.
- A `MemorySegment` from `Arena.allocate` points to real native memory; it still requires lifetime, alignment, and ownership contracts.
- If you need to pass a Java array down to C, use proper JNI methods or supported FFM marshalling/copy/pinning; do not take the "address" of a heap segment and cast it to a C pointer.

## 12. Cases easily confused with `asSlice` and `copyFrom`

### 12.1. `asSlice` does not automatically dereference a pointer

`slot.asSlice(0L, ValueLayout.ADDRESS.byteSize())` creates a **view of the bytes storing the pointer in the slot**. It does not go to the target region. The slice's address still lies within the slot allocation.

Conversely:

```java
MemorySegment rawPointer =
        slot.get(ValueLayout.ADDRESS, 0L);
```

returns a wrapper whose address equals **the stored pointer value**, even though that wrapper is zero-length. Only when there is already a bounded view to the pointee does `asSlice` on the pointee slice the actual data at the target.

### 12.2. `copyFrom` can copy the slot's bytes, not the pointee

If you copy:

```java
// Fragment: bothSlots have enough ADDRESS.byteSize() bytes and are valid.
anotherSlot.copyFrom(slot);
```

then you copy **the bytes of the pointer value** to another slot. The result is that both slots store the same target address. There is no cloning of the data in the pointee; no new allocation for the target, and no automatic shared ownership/reference counting.

Copying pointer bytes also carries the risk of double-free if subsequent code treats the two slots as two independent owners of one allocation. This is an ownership bug, not a bug of `copyFrom`.

## 13. Scenario table: right / wrong and why

| Intent | Wrong or insufficient approach | Correct approach / condition |
| --- | --- | --- |
| Read the address stored in slot | `slot.address()` | `slot.get(ADDRESS, 0).address()` |
| Get the physical address of slot | `slot.get(ADDRESS, 0).address()` | `slot.address()` if slot is a native segment |
| Read `int` at pointee | `slot.get(JAVA_INT, 0)` | `data.get(JAVA_INT, 0)`, or a verified bounded target view |
| Write a pointer into slot | `slot.copyFrom(data)` | `slot.set(ADDRESS, 0, data)` |
| Write value 123 into pointee | `slot.set(JAVA_INT, 0, 123)` | `data.set(JAVA_INT, 0, 123)` or a valid target view |
| Read an `int *` via ADDRESS | Expect a 4-byte view automatically | Receive zero-length view; `reinterpret` or target layout per contract |
| Check for NULL pointer | `pointer == null` | `pointer.address() == 0L` |
| Free the target region | Close the arena containing only slot | Close the actual owner of data or call the official deallocator |
| Pointer from native library | `reinterpret(Long.MAX_VALUE)` without verification | Obtain size and lifetime from the API, bound reasonably, control ownership |
| Pointer to opaque handle | Guess field offset and read | Only pass back to the native API managing the handle |
| Pointer-to-pointer | Read `JAVA_INT` at offset 0 of outer slot | Read each address level, create properly sized views, then read data |

## 14. Exceptions you may see, and dangerous cases with no exception

| Case | What usually happens |
| --- | --- |
| `pointer.get(JAVA_INT, 0)` on pointer view of size 0 | `IndexOutOfBoundsException` |
| `slot.get(ADDRESS, offset)` out of slot's bounds | `IndexOutOfBoundsException` |
| `slot.get(ADDRESS, 0)` on slot whose arena is closed | `IllegalStateException` |
| Using confined slot from a non-owning thread | `WrongThreadException` |
| `slot.set(ADDRESS, 0, data)` where `data` is a heap segment unusable as a native pointer | `IllegalArgumentException` per the address access contract |
| Reading/writing a layout with incompatible alignment | `IllegalArgumentException` |
| Calling restricted `reinterpret` / `withTargetLayout` without native access enabled | `IllegalCallerException` on a JDK with enforced restrictions |
| Assigning a view that is too large and reading beyond the actual C-allocated region | Possible **segfault, JVM crash, or silent memory corruption** |
| Dereferencing a dangling pointer after native has freed the memory | Possible **crash or memory corruption**, do not expect a safe Java exception |
| Dereferencing a NULL pointer after reinterpreting it to size >0 | Dangerous behavior; must check NULL first |

Segment bounds checks **only rely on known or declared bounds**. If you supply wrong bounds via a restricted API, Java cannot verify how wide the external physical allocation actually is.

### 14.1. Do not read pointers from untrusted data as process addresses

Any four or eight bytes in a file, network packet, or untrusted memory **do not** automatically become a valid process pointer. Do not take an integer from untrusted data, create `MemorySegment.ofAddress(number)`, then `reinterpret` and dereference it. `ofAddress` creates a zero-length wrapper **without verifying** that the address is readable, has ownership, or lies in the appropriate address space.

File formats should usually store **relative offsets** or **IDs**, not raw process pointers. Raw pointers only make sense within a process's address space and within a defined lifetime.

## 15. Safe workflow when working with pointers returned from a native API

1. **Identify the data type:** is this a pointer slot, pointer value, array-of-pointers, struct field `T *`, or opaque handle?
2. **Confirm the owner:** was the allocation created by a Java arena or a C allocator; who is allowed to free it; which API frees it?
3. **Confirm the lifetime:** is the pointer valid until the callback ends, until `release` is called, or until the arena closes?
4. **Confirm the size:** if it is a buffer, the size comes from a separate parameter or a clear layout; check `0 <= size`, overflow, and application limits.
5. **Confirm NULL:** if `pointer.address() == 0L`, stop and handle according to the API contract.
6. **Confirm alignment, byte order, stride:** know the exact C/ABI type, do not blindly apply `JAVA_INT` to an unverified struct.
7. **Choose how to create the view:** use the original bounded segment when possible; if only a raw pointer is available, restricted `reinterpret`/target layout requires the right size and temporal contract.
8. **Keep the owner alive throughout usage:** do not let native free abruptly, do not close the arena in the middle of a callback or worker.
9. **Clean up exactly once:** clear the handle, close the arena, or call the deallocator, without mixing allocators; do not treat setting a pointer to NULL as freeing.
10. **Only pass pointers across threads when the contract allows:** synchronize native writes and respect confined segments.

A quality API should provide, instead of a bare raw pointer:

- `Pointer + length` for dynamic arrays.
- `Pointer + release function` for memory allocated by C with ownership transfer.
- `Opaque handle + native methods` when the internal layout is not public.
- `Arena + MemorySegment` when Java is the allocator and holds the lifetime.

## 16. Self-check questions

**Question 1.** How do `slot.address()` and `slot.get(ADDRESS, 0).address()` differ?  
**Answer:** The former is the address of the region storing the pointer variable; the latter is the pointer value stored in that region, i.e., the target address (if the value is valid).

**Question 2.** Why does `slot.get(ADDRESS, 0)` usually have `byteSize() == 0`?  
**Answer:** The JVM can only read the address value, and does not know how wide the target is. A zero-length segment prevents implicit dereferencing; to read, a view with reliable bounds must be created.

**Question 3.** Does `slot.set(ADDRESS, 0, data)` copy the `int` values of `data` into slot?  
**Answer:** No. It writes **the address of data** into slot, without copying the contents or transferring ownership.

**Question 4.** After calling `addressValue.reinterpret(12)`, does the JVM guarantee the target allocation is at least 12 bytes long?  
**Answer:** No. `reinterpret` is a restricted method declaring bounds based on the caller's assumption; a wrong assumption can cause a crash/corruption.

**Question 5.** If `slot` is managed by Arena A, and `data` is managed by Arena B, does closing Arena B turn the pointer value in slot into NULL?  
**Answer:** No. The pointer value may still remain in slot, but it is a **dangling pointer**. Do not dereference it anymore.

**Question 6.** Is `MemorySegment.NULL` a Java `null` reference?  
**Answer:** No. It is a native segment wrapper with `address()==0L`, modeling a C NULL pointer.

**Question 7.** Does `withTargetLayout(MemoryLayout.sequenceLayout(3, JAVA_INT))` automatically manage freeing the 12-byte buffer?  
**Answer:** No. It only specifies the target size/layout to create a view; ownership and lifetime must still be verified separately.

**Question 8.** A C function returns `void *handle` to a private struct. Should you call `reinterpret(64)` and read the first field?  
**Answer:** No. An opaque handle has no public layout to dereference; only pass it to the appropriate native APIs.

**Question 9.** In `int **pp`, how many levels of addresses must be read to reach the integer?  
**Answer:** Two pointer levels: read from the outer slot to find the intermediate pointer slot, then read the pointer from the intermediate slot to find the region containing `int`.

**Question 10.** Does copying bytes from slot A to slot B create a copy of the target region?  
**Answer:** No. Two slots can store the same target address; copying pointer bytes does not copy the pointee, and does not create two independent owners.

**Question 11.** The target region has been freed, but the pointer wrapper still has global scope. Does `pointer.scope().isAlive()` prove dereferencing is safe?  
**Answer:** No. The global scope of the wrapper does not control the lifetime of the external allocation.

## 17. Key takeaways

- **Pointer slot** is the memory region storing an address value; **pointee** is the data region pointed to. The two regions can be at different addresses, with different allocators and different lifetimes.
- `slot.address()` = address **of the slot**; `slot.get(ADDRESS, 0).address()` = address **read from the slot**.
- `slot.get(ADDRESS, 0)` normally returns a zero-length segment, and does not automatically provide bounds/owner of the pointee.
- `reinterpret` and `AddressLayout.withTargetLayout` are **restricted/unsafe operations** requiring the right size, alignment, and lifetime; they **do not allocate**, **do not copy**, and **do not automatically free** the target data region.
- `slot.set(ADDRESS, 0, data)` writes a **pointer value**, not the data contents. `slot.set(ADDRESS, 0, NULL)` only clears the pointer value, and does not free the pointee.
- An **opaque handle** must only be passed through the owner's APIs, and not reinterpreted to read a private layout.
- A read pointer carries the value **at the time of reading**, and does not automatically track subsequent writes to the slot.
- When creating a bounded target view, always **check NULL, size, ownership, lifetime, thread confinement, and allocator** before dereferencing.

### Official references

- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): zero-length segments when reading addresses, `get(AddressLayout, offset)`, `set(AddressLayout, offset, value)`, `reinterpret`, and lifetime scopes.
- [Oracle Java SE 22 — AddressLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/AddressLayout.html): platform-dependent pointer size/alignment, `withTargetLayout` as a restricted method.
- [Oracle Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): allocator, confined scope, arena closing time, and owned resources.
- [Oracle Java SE 22 — MemoryLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html): target/struct/sequence layouts and value access paths.
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): JDK 22 final FFM API, restricted operations, and native interoperability conditions.
