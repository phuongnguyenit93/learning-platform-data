# AddressLayout.withTargetLayout: declaring a typed pointer and the responsibility for accurately determining the target memory region

## 1. The problem: from a machine address to a memory region that Java is allowed to read

When connecting Java with C/C++ libraries, we often encounter pointer-typed arguments or data fields:

```c
int *value;
int values[3];
struct Record *record;
void *data;
char *text;
```

A native pointer essentially holds an **address**, but the address value alone does not answer essential questions: how many bytes large is that memory region, is it actually allocated, what alignment does it require, who owns the right to `free` it, how long is it valid, and is Java allowed to write to it?

In the **Foreign Function & Memory API (FFM)**, `java.lang.foreign.AddressLayout` describes *an address value* stored in memory or passed across a native function call. By default, `ValueLayout.ADDRESS` allows reading the **pointer value**, but Java **does not automatically know** the length of the memory region that the pointer points to.

The method:

```java
AddressLayout typedPointer =
        ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT);
```

allows stating: **“When reading an address using this layout, return a `MemorySegment` whose view length equals the target layout, which here is 4 bytes.”**

**The most important sentence of this lesson:** `withTargetLayout` is **a declaration of how to interpret an address and an assumed size bound**, not an operation that verifies actual native memory. It **does not allocate, does not own, does not keep alive, and does not check the entire pointed-to region**. The programmer must still accurately determine the size, alignment, lifetime, ownership, and C contract of the pointer.

### Java version

The examples use the standard `java.lang.foreign` API finalized in **JDK 22 (JEP 454)**. Use JDK **22+**; the programs were compiled and verified on JDK 24. `AddressLayout.withTargetLayout(MemoryLayout)` is a **restricted method**, so classpath examples are run with:

```bash
java --enable-native-access=ALL-UNNAMED ClassName
```

If the program is placed in a named module, native access must be granted to that exact module name. Do not omit the flag and assume the warning or `IllegalCallerException` is related to pointer size: this is the restricted API permission rule. Unlike FFM examples that only call `Arena.allocate`, this example **contains a restricted operation**.

## 2. Distinguishing where the address is stored and where the pointed-to memory region resides

Suppose a C region has four bytes containing the number `12345` at address A, and a pointer slot contains A at address P:

```text
   pointer storage region (slot)               data region (target)
   address P                                  address A
+-----------------------+            +-----------------------+
|    A (pointer value)  | ----------> |   12345 (4 bytes)     |
+-----------------------+            +-----------------------+
   layout: ADDRESS                          layout: JAVA_INT
   pointer size: 4/8 bytes                  target size: 4 bytes

Java MemorySegment slot                  Java MemorySegment target
  knows the pointer slot location          knows the region allocated by the arena
  only usable while slot owner alive       only usable while target owner alive
```

There are **three different kinds of sizes**:

1. **`slot.byteSize()`:** the size of the view containing one or more pointers. For a single pointer slot, this is usually equal to `ValueLayout.ADDRESS.byteSize()`.
2. **`AddressLayout.byteSize()`:** the size of the **pointer value** when read/written from the slot; ABI-dependent, typically 8 bytes on 64-bit platforms.
3. **`targetLayout.byteSize()`:** the assumed number of bytes at the **target address**, for example `JAVA_INT.byteSize() == 4`. This length is assigned to the `MemorySegment` returned when reading the pointer using an address layout with a target.

Therefore:

```java
AddressLayout addr = ValueLayout.ADDRESS;
AddressLayout intPtr = addr.withTargetLayout(ValueLayout.JAVA_INT);

System.out.println(addr.byteSize() == intPtr.byteSize()); // true
System.out.println(intPtr.targetLayout().orElseThrow().byteSize()); // 4
```

`withTargetLayout` **does not turn a 64-bit pointer into a 32-bit pointer**. Pointer storage still follows `ADDRESS`; only the view **returned when reading the address** changes size.

### Do not confuse the carrier type

`AddressLayout` is a subtype of `ValueLayout`, but its carrier is **`MemorySegment.class`**, not Java `long`:

```java
boolean yes = ValueLayout.ADDRESS.carrier() == MemorySegment.class;
```

`MemorySegment.get(AddressLayout, offset)` returns a `MemorySegment` representing **the address fetched from the slot**, not a Java object that automatically owns that allocation.

## 3. By default ADDRESS returns a 0-byte view; target layout expands the view as declared

If you read a pointer using a layout without a target:

```java
MemorySegment opaque = slot.get(ValueLayout.ADDRESS, 0);
```

FFM creates a **native segment with size 0 bytes**, even if the read address is non-zero. This is an intentional guardrail: Java does not know the allocation size, so it does not allow reading a single byte through normal bounds-checked access.

If you read the same pointer using a layout with a target:

```java
AddressLayout intPointer =
        ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT);

MemorySegment typed = slot.get(intPointer, 0);
```

FFM returns a native segment with:

- `typed.address()` equal to the machine address just read from `slot`.
- `typed.byteSize() == ValueLayout.JAVA_INT.byteSize()` (4 bytes).
- The scope of the **native segment created from a pointer read is the global scope**, not the scope of `slot` or the scope of the original allocation.
- Reading the pointer also checks **alignment of the target address against the target layout**; if incompatible, it may throw `IllegalArgumentException`.

When and **only when** you already know the actual target region is valid, long enough, and has not been freed, you can do:

```java
int value = typed.get(ValueLayout.JAVA_INT, 0);
```

**Biggest trap:** even though `typed.byteSize() == 4` allows access within the view range, FFM **does not automatically deduce** that those 4 bytes actually belong to a live allocation. If the pointer is stale, dangling, or forged, dereferencing it can cause a **JVM crash or memory corruption**, rather than always producing a polite `IllegalStateException`.

### Brief comparison

| Read method | `byteSize()` of returned pointer view | Can the target region be interpreted? | Risk |
| --- | ---: | --- | --- |
| `slot.get(ValueLayout.ADDRESS, 0)` | 0 | Cannot read target bytes with normal `get(JAVA_BYTE,0)` | Safer to keep pointer opaque when size is unknown |
| `slot.get(ADDRESS.withTargetLayout(JAVA_INT),0)` | 4 | Allows accessing 4 bytes if pointer is actually valid | Size is only an **assumption supplied by the caller** |
| `slot.get(ADDRESS.withTargetLayout(sequenceLayout(3,JAVA_INT)),0)` | 12 | Allows reading 3 `int`s within declared bounds | Does not verify actual allocation contains at least 3 `int`s |
| `ofAddress(rawAddress)` without expansion | 0 | Cannot read bytes without valid information | Only represents an opaque address |
| `reinterpret` on an address | User-specified size | Can create a new view, but is also restricted/unsafe | Does not automatically verify lifetime or provenance |

## 4. What withTargetLayout actually does and does not do

### What it does

- Creates a **new, immutable `AddressLayout`** with an associated target `MemoryLayout`.
- **Preserves** the carrier, the alignment of the address layout itself, byte order, name, and pointer value size.
- Allows `slot.get(typedAddressLayout, offset)` to return a `MemorySegment` whose `byteSize` equals `targetLayout.byteSize()` instead of 0.
- Checks alignment of the **target address** against `targetLayout.byteAlignment()` at the pointer read step.
- Allows describing a pointer to a typed value/sequence/struct of a specific size in certain FFM APIs such as `MemorySegment.get`, or function descriptors for downcalls or upcalls.

### What it completely does not guarantee

- **Does not create an allocation:** does not call `malloc`, does not call `Arena.allocate`, and does not allocate additional bytes at the target address.
- **Does not validate the address:** an address could be garbage, a freed pointer, a pointer into unmapped memory, or null.
- **Does not verify actual size:** declaring a 16-byte target does not prove the allocation actually has at least 16 bytes.
- **Does not know ownership:** does not determine who must call `free`/`delete`/`munmap` or a library-specific destructor.
- **Does not protect referent lifetime:** a pointer view with global scope does not keep another arena's allocation alive.
- **Does not check the actual C type:** declaring `JAVA_LONG` does not make a C `long` automatically 8 bytes on every ABI.
- **Does not control mutability or native synchronization:** a target layout does not replace constness contracts, locks, thread-affinity, and memory barriers.
- **Does not automatically check non-overlapping/non-aliasing target regions:** multiple pointers can point to the same region.
- **Does not prove dereferencing is safe just because alignment is valid:** alignment is necessary, not sufficient.

Think of `targetLayout` as a **promise from the Java author to FFM**. If the promise is wrong about spatial or temporal bounds, the consequences go beyond normal Java checks.

## 5. Program 1: reading a pointer with and without a target layout

This program intentionally creates **both the data region and the pointer slot** using an arena that is still open. That way, dereferencing inside the `try` block is valid and testable. After the arena closes, the program **only observes metadata** and strictly never dereferences the freed pointer.

### 5.1. File `AddressTargetDemo.java`

```java
import java.lang.foreign.*;
import static java.lang.foreign.ValueLayout.*;

public class AddressTargetDemo {
    private static final AddressLayout INT_POINTER =
            ADDRESS.withTargetLayout(JAVA_INT);

    public static void main(String[] args) {
        System.out.println("Pointer layout bytes: " + ADDRESS.byteSize());
        System.out.println("Target layout bytes: "
                + INT_POINTER.targetLayout().orElseThrow().byteSize());
        System.out.println("Carrier: "
                + (INT_POINTER.carrier() == MemorySegment.class));

        MemorySegment typed;
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment value = arena.allocate(JAVA_INT);
            value.set(JAVA_INT, 0, 12345);

            MemorySegment slot = arena.allocate(ADDRESS);
            slot.set(ADDRESS, 0, value);

            MemorySegment opaque = slot.get(ADDRESS, 0);
            typed = slot.get(INT_POINTER, 0);

            System.out.println("Without target bytes: " + opaque.byteSize());
            System.out.println("With target bytes: " + typed.byteSize());
            System.out.println("Same address: "
                    + (typed.address() == value.address()));
            System.out.println("Read while owner open: "
                    + typed.get(JAVA_INT, 0));
            System.out.println("Typed scope alive while open: "
                    + typed.scope().isAlive());

            MemorySegment larger = arena.allocate(8, 8);
            MemorySegment misaligned = larger.asSlice(1, 4);
            slot.set(ADDRESS, 0, misaligned);

            try {
                slot.get(INT_POINTER, 0);
                System.out.println("Unexpected aligned");
            } catch (IllegalArgumentException expected) {
                System.out.println("Misaligned target: blocked");
            }

            slot.set(ADDRESS, 0, MemorySegment.NULL);
            MemorySegment nullPtr = slot.get(ADDRESS, 0);
            MemorySegment nullTyped = slot.get(INT_POINTER, 0);

            System.out.println("Null raw address: "
                    + (nullPtr.address() == 0));
            System.out.println("Null typed address: "
                    + (nullTyped.address() == 0));
            System.out.println("Null typed bytes: " + nullTyped.byteSize());
            // Do not dereference nullTyped!
        }

        System.out.println("Typed global scope remains alive: "
                + typed.scope().isAlive());
        // Do not dereference typed: the value region was freed by arena.close().
    }
}
```

**Run on JDK 22+ on the classpath:**

```bash
javac AddressTargetDemo.java
java --enable-native-access=ALL-UNNAMED AddressTargetDemo
```

**Verified stdout on JDK 24, 64-bit system:**

```text
Pointer layout bytes: 8
Target layout bytes: 4
Carrier: true
Without target bytes: 0
With target bytes: 4
Same address: true
Read while owner open: 12345
Typed scope alive while open: true
Misaligned target: blocked
Null raw address: true
Null typed address: true
Null typed bytes: 4
Typed global scope remains alive: true
```

**Explanation of each observation:**

1. The pointer is 8 bytes long on the 64-bit platform used for verification. A 32-bit platform may report 4 bytes; **the `JAVA_INT` target remains 4 bytes**.
2. `slot.set(ADDRESS, 0, value)` writes **the address of `value`** into `slot`. It **does not transfer ownership** of the allocation from the arena to the slot.
3. `slot.get(ADDRESS, 0)` returns a 0-byte view, safe as an opaque pointer.
4. `slot.get(INT_POINTER, 0)` returns a 4-byte view. While the arena is open, the pointer points to a valid 4-byte allocation with 4-byte alignment, so it reads `12345`.
5. The pointer `larger.asSlice(1,4)` is not 4-byte aligned; `slot.get(INT_POINTER,0)` rejects it with `IllegalArgumentException` **before using the target**.
6. A null address when read with a target layout **can still have `byteSize() == 4`**. **Do not dereference it!** `byteSize` is an annotation for the view, not proof of allocation.
7. After close, `typed.scope().isAlive()` remains true because the pointer view returned from `get(AddressLayout)` is a **global-scope segment**. **This does not keep the allocation alive.** Reading `typed` after close is a use-after-free and is intentionally omitted from the example.

The last line is especially important evidence: **the global scope of a view constructed from an address does not certify the lifetime of the memory region at that address**.

## 6. Lifetime risks: pointer view and original allocation do not share a scope

### 6.1. Source slot and target allocation can have two different owners

A pointer can be stored in a memory region belonging to arena A while pointing to a memory region belonging to arena B:

```text
Arena A (owns pointer slot)              Arena B (owns actual data)
+-----------------------------+         +----------------------------+
| slot holds address X         | ------> | data at X, 3 ints          |
+-----------------------------+         +----------------------------+

slot.get(ADDRESS.withTargetLayout(...),0)
                |
                v
        pointer-derived segment
          size = declared target
          scope = GLOBAL, not A or B
```

When arena A closes, Java no longer has permission to read **the address storage slot** `slot`. But if arena B is still open and the program still guarantees address X is valid, the target data still exists.

Conversely, when arena B closes, data X expires **even though** the pointer-derived segment has a global scope that still reports alive. **Do not equate the lifetime of the pointer slot, the lifetime of the view, and the lifetime of the actual allocation.**

### 6.2. A pointer-derived segment does not automatically close with its owner

Unlike the original `MemorySegment` returned by `Arena.ofConfined().allocate`, a segment constructed from a **raw address read with `get(AddressLayout)`** carries the global scope by specification. It can remain present after the owner frees the memory, and `scope().isAlive()` will still be true.

That makes a design relying solely on:

```java
if (pointer.scope().isAlive()) {
    int x = pointer.get(ValueLayout.JAVA_INT, 0);
}
```

**unsafe** for pointer-derived segments. Checking the global scope provides virtually no information about the actual allocation's lifecycle.

**It is the application's responsibility** to keep the owner arena/handle alive at least until all dereferences finish, prevent other code from freeing it early, and not use the pointer after the C library has invalidated it.

## 7. Program 2: pointer to an array and two different arenas

This exercise uses `MemoryLayout.sequenceLayout(3, JAVA_INT)` as the target. The pointer has a 12-byte view, allowing `getAtIndex` from 0 to 2 while the allocation is still alive.

### 7.1. File `PointerOwnershipDemo.java`

```java
import java.lang.foreign.*;
import static java.lang.foreign.ValueLayout.*;

public class PointerOwnershipDemo {
    private static final SequenceLayout THREE_INTS =
            MemoryLayout.sequenceLayout(3, JAVA_INT);

    private static final AddressLayout INT_ARRAY_POINTER =
            ADDRESS.withTargetLayout(THREE_INTS);

    public static void main(String[] args) {
        MemorySegment loaded;

        try (Arena dataOwner = Arena.ofConfined()) {
            MemorySegment data = dataOwner.allocate(THREE_INTS);
            data.setAtIndex(JAVA_INT, 0, 10);
            data.setAtIndex(JAVA_INT, 1, 20);
            data.setAtIndex(JAVA_INT, 2, 30);

            try (Arena slotOwner = Arena.ofConfined()) {
                MemorySegment slot = slotOwner.allocate(ADDRESS);
                slot.set(ADDRESS, 0, data);

                loaded = slot.get(INT_ARRAY_POINTER, 0);

                System.out.println("Array target bytes: " + loaded.byteSize());
                System.out.println("Value index 1: "
                        + loaded.getAtIndex(JAVA_INT, 1));
                System.out.println("Pointer global scope: "
                        + loaded.scope().isAlive());
            }

            System.out.println("Source slot closed, data alive: "
                    + data.scope().isAlive());
            System.out.println("Value index 2: "
                    + loaded.getAtIndex(JAVA_INT, 2));

            try {
                loaded.getAtIndex(JAVA_INT, 3);
            } catch (IndexOutOfBoundsException expected) {
                System.out.println("Outside declared target: blocked");
            }
        }

        System.out.println("Loaded pointer scope alive after free: "
                + loaded.scope().isAlive());
        // Do not dereference loaded after dataOwner closes!
    }
}
```

**Run:**

```bash
javac PointerOwnershipDemo.java
java --enable-native-access=ALL-UNNAMED PointerOwnershipDemo
```

**Verified stdout on JDK 24:**

```text
Array target bytes: 12
Value index 1: 20
Pointer global scope: true
Source slot closed, data alive: true
Value index 2: 30
Outside declared target: blocked
Loaded pointer scope alive after free: true
```

Scenarios learned:

- **When `slotOwner` closes:** the slot can no longer be read, but `dataOwner` is still open; target data remains, so `loaded.getAtIndex(...,2)` here is valid.
- **When `dataOwner` closes:** the actual allocation is freed. `loaded.scope()` is still global and alive, but it has become a **dangling view**. Any further dereference is considered invalid under the ownership contract, even though the layout and `byteSize` still look right.
- `getAtIndex(JAVA_INT,3)` is blocked because the target view is 12 bytes long; this is a **bounds check against the declared length**, not a verification of the physical allocation. If the actual target only allocated 8 bytes while 12 were declared, accessing index 2 also risks memory corruption that the view check **will not detect**.

### 7.2. Why not test by reading after free?

Because misusing a raw native pointer can **crash the JVM**, corrupt memory, or cause undefined behavior on the native side. A test should not intentionally trigger a use-after-free as a way to prove a contract.

To verify owner logic, check `data.scope().isAlive()` on the **original arena-managed segment** and structure the code so that all dereferences of the pointer-derived view occur only while `dataOwner` is still open. Tests for invalid layouts can use a **valid address with misaligned offset**, or an offset outside the **declared view**, without putting the JVM into a state of reading from freed memory.

## 8. C structs: declaring an ABI-accurate target layout

In C code, a `struct Record *` pointer is interpreted according to the size, alignment, and field offsets of the struct that the C compiler actually uses. Java needs a `MemoryLayout` matching the **C ABI**. Calling `withTargetLayout(structLayout)` does not make Java guess it right automatically.

Example illustrating a concrete layout:

```c
/* Illustrates an ABI where int is 4 bytes, int64_t is 8 bytes,
   total is at offset 8, and sizeof(Record) equals 16. */
struct Record {
    int32_t code;
    /* 4 bytes of padding per the illustrated ABI */
    int64_t total;
};
```

Do not assume C `long` is always 8 bytes: on 64-bit Windows, `long` is typically 4 bytes under LLP64, whereas on 64-bit Unix-like systems it is typically 8 bytes under LP64. You must rely on the library's headers and ABI (e.g., `int32_t`, `int64_t`), or a binding generator / checks for `sizeof`, `alignof`, and `offsetof`.

### 8.1. File `PointerStructDemo.java`

```java
import java.lang.foreign.*;
import static java.lang.foreign.ValueLayout.*;
import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

public class PointerStructDemo {
    private static final StructLayout RECORD = MemoryLayout.structLayout(
            JAVA_INT.withName("code"),
            MemoryLayout.paddingLayout(4),
            JAVA_LONG.withName("total"));

    private static final AddressLayout RECORD_POINTER =
            ADDRESS.withTargetLayout(RECORD);

    public static void main(String[] args) {
        System.out.println("Pointer carrier: "
                + (RECORD_POINTER.carrier() == MemorySegment.class));
        System.out.println("Address target present: "
                + ADDRESS.targetLayout().isPresent());
        System.out.println("Record target present: "
                + RECORD_POINTER.targetLayout().isPresent());
        System.out.println("Target bytes: "
                + RECORD_POINTER.targetLayout().orElseThrow().byteSize());
        System.out.println("Pointer bytes unchanged: "
                + (RECORD_POINTER.byteSize() == ADDRESS.byteSize()));
        System.out.println("Without target: "
                + RECORD_POINTER.withoutTargetLayout().equals(ADDRESS));

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment record = arena.allocate(RECORD);
            record.set(JAVA_INT, RECORD.byteOffset(groupElement("code")), 7);
            record.set(JAVA_LONG, RECORD.byteOffset(groupElement("total")), 500L);

            MemorySegment slot = arena.allocate(ADDRESS);
            slot.set(ADDRESS, 0, record);

            MemorySegment throughPointer = slot.get(RECORD_POINTER, 0);
            System.out.println("Record bytes: " + throughPointer.byteSize());
            System.out.println("Code: " + throughPointer.get(JAVA_INT, 0));
            System.out.println("Total: " + throughPointer.get(JAVA_LONG, 8));
        }
    }
}
```

**Compile/run:**

```bash
javac PointerStructDemo.java
java --enable-native-access=ALL-UNNAMED PointerStructDemo
```

**Verified stdout on JDK 24:**

```text
Pointer carrier: true
Address target present: false
Record target present: true
Target bytes: 16
Pointer bytes unchanged: true
Without target: true
Record bytes: 16
Code: 7
Total: 500
```

Explanation:

- `RECORD_POINTER.targetLayout()` contains `RECORD`, whereas `ValueLayout.ADDRESS.targetLayout()` is empty by default.
- `RECORD_POINTER.byteSize()` remains the pointer storage size, equal to `ADDRESS.byteSize()`.
- `RECORD_POINTER.withoutTargetLayout()` returns a layout identical to `ADDRESS` in its remaining attributes; **it has no side effect on `RECORD_POINTER`**, because layouts are immutable.
- `MemoryLayout.paddingLayout(4)` represents four padding bytes, placing `total` at offset 8.
- `arena.allocate(RECORD)` creates a **valid actual native allocation** matching the layout; then the pointer is written into `slot` and read back as a 16-byte view.
- Only read `throughPointer` while `arena` is still open. Returning `throughPointer` outside the `try` block and reading it after close is wrong, even though the view uses the global scope.

### 8.2. Confusing a field layout with a pointer layout

Do not use `JAVA_LONG` to read a *pointer value* just because a 64-bit pointer is 8 bytes wide. An address layout has carrier `MemorySegment` and follows pointer size/ABI; `JAVA_LONG` is the layout of an 8-byte **Java long**. A size coincidence on one platform does not make the two ABI types equivalent.

To read a `T*` pointer stored in a C struct, the corresponding field typically uses an `AddressLayout` (with target layout `T` if the contract truly knows T's size and lifetime). To read the contents of `T` after verifying the contract, use `ValueLayout`/`MemoryLayout` for the data, not continuing to read it as pointer bytes.

## 9. Slot alignment and target alignment are two different conditions

For an `AddressLayout` with a target:

1. **Pointer storage slot:** must have at least `ADDRESS.byteSize()` bytes, and the read position must satisfy `ADDRESS.byteAlignment()`.
2. **Pointer pointing to target:** the read address must satisfy `targetLayout.byteAlignment()` if the layout requires it.
3. **Actual data region:** must still be valid and have the right size, which **cannot** be inferred from those two alignment checks alone.

For example: an 8-byte-aligned pointer slot can hold the address of a buffer shifted by 1 byte. When read with `ADDRESS.withTargetLayout(JAVA_INT)` (target requires 4-byte alignment), FFM rejects it with `IllegalArgumentException` because the target address is unaligned. This is the safety case exercised in `AddressTargetDemo`.

If the C data is actually *packed* without alignment and the API contract allows it, the target layout can use `ValueLayout.JAVA_INT_UNALIGNED` (alignment 1). However, **do not** switch to an unaligned layout to mask a corrupt pointer, wrong offset, or wrong ABI.

**Correct alignment does not prove a pointer is valid.** A pointer that has been `free`d can still be divisible by 8; dereferencing it risks a crash, even if `withTargetLayout` reports no error.

## 10. Null pointer: a sized view with no backing memory

C pointer data can take the value `NULL`. In FFM:

```java
slot.set(ValueLayout.ADDRESS, 0, MemorySegment.NULL);
MemorySegment ptr = slot.get(ValueLayout.ADDRESS, 0);

if (ptr.address() == 0) {
    // No valid referent to read.
}
```

**In particular:** when read with `AddressLayout.withTargetLayout(JAVA_INT)`, a null pointer in JDK 24 experiments is returned as a view with:

```text
nullTyped.address() == 0
nullTyped.byteSize() == 4
```

The number `byteSize() == 4` comes solely from your **target declaration**; it does not prove 4 bytes at address 0 are allocated. **Never call `nullTyped.get(JAVA_INT, 0)`.** Accessing invalid native memory can crash the JVM or cause severe errors and must not be treated as a normal test to catch with `try/catch`.

Procedure for handling a nullable pointer:

```java
MemorySegment readPointer = slot.get(INT_POINTER, 0);
if (readPointer.address() == 0) {
    // Null value: handle per the native contract (return Optional.empty,
    // skip, or throw a Java exception at the boundary).
} else {
    // Must verify size, lifetime, ownership, alignment, and thread
    // before dereferencing readPointer.
}
```

This is an **illustrative snippet** in a context that already has `slot`, `INT_POINTER`, and a valid owner; it is not a standalone application.

## 11. Ownership: who allocates, who frees, and how long does the pointer live?

`withTargetLayout` does not answer ownership at all. A C API can have different contracts:

| Pointer source | Common contract | What Java must do |
| --- | --- | --- |
| Points to a region created by Java's `Arena.allocate` | Java arena owns the allocation | Keep arena open until all native users finish; close at the right time |
| Native function returns a **borrowed pointer** | C library retains ownership, may invalidate on owner close or next call | Dereference only within the documented validity window; **do not free** |
| Native function returns an **owned pointer** | Caller receives ownership and must use the appropriate native release | Use the library's exact release function, usually not arbitrary Java `free` |
| Points to library static data | Lifetime matches library/process | Do not free; avoid using after unload or invalidation |
| Pointer to buffer + separately returned length | Actual length known at runtime | Check length, overflow, capacity; create a matching view **only while** pointer is alive |
| Nullable pointer | `NULL` is a valid value indicating no data | Check for address 0 **before dereferencing** |
| Pointer-to-pointer `T**` | Pointer slot holds a pointer to another region | Read each level with its own layout and ownership, do not confuse target `T` with `T*` |

**This is a guide to reading ABI contracts, not automatic inference from Java's `AddressLayout`.** In real systems, obtain this information from C headers, native library documentation, public source code, or a reliable binding generator. If the library does not specify ownership/lifetime, **there is insufficient basis** for a safe dereference.

### 11.1. Borrowed pointer

Suppose C returns `const char *get_name()`, but the library states the memory is only valid until the next `update_name()` call:

- The pointer belongs to the library; Java does not `free` it.
- If you need to keep the string after the next update, **copy the bytes/string** while the pointer is still valid.
- `withTargetLayout` does not extend lifetime and cannot protect against callbacks/native threads invalidating it.
- A C string may be NUL-terminated in a region of unknown length; **do not arbitrarily pick a huge target size and scan blindly**.

### 11.2. Owned pointer

Suppose C returns `Widget *widget_create()` and provides `void widget_destroy(Widget*)`:

- The Java caller needs a wrapper or owner record that holds the handle and carries the `widget_destroy` obligation.
- It should provide `close()`/`AutoCloseable`, calling release at the right time; `Cleaner`, if used, is only a best-effort fallback.
- Avoid double-free and concurrent use-after-free across threads.
- Do not assume `Arena.close()` automatically calls `widget_destroy` on a returned native pointer unless an appropriate cleanup mechanism is registered.

FFM code often needs a linker/downcall handle for the library's destroy function. The exact choice depends on the ABI and owner rules; do not call `free` on every pointer, because the library may use a custom allocator/destructor.

### 11.3. Struct containing a pointer field inside

Example:

```c
struct BufferView {
    const unsigned char *data;
    size_t length;
};
```

Java needs both pieces of information: `data` and `length`. An `AddressLayout` with a fixed target layout **does not automatically recognize** `length` at runtime. You must read `length` from the corresponding field according to the ABI, check bounds, and only create a view as long as the number of bytes actually alive. Across 32-bit/64-bit platforms, the width and alignment of `size_t` can differ, so the Java layout must match the **C ABI**, not assume `size_t == JAVA_LONG`.

## 12. Determining dynamic data size: do not guess from pointer size

If a library returns a `T*` along with an element count `count`, the theoretical byte count is:

\[
\text{bytes} = \text{count} \times \text{sizeof}(T)
\]

But the formula is only useful when all three conditions hold:

1. `count` comes from a trusted native contract, is non-negative, and does not exceed the maximum allocated by the library.
2. `sizeof(T)` is the exact size per the ABI/MemoryLayout (including struct padding).
3. The allocation remains valid throughout the entire time Java reads/writes it.

Example preparing a target sequence layout by count with overflow checking:

```java
static AddressLayout pointerToInts(long count) {
    if (count < 0 || count > 1_000_000) {
        throw new IllegalArgumentException("Untrusted count");
    }

    long bytes = Math.multiplyExact(
            count, ValueLayout.JAVA_INT.byteSize());

    MemoryLayout target = MemoryLayout.sequenceLayout(
            count, ValueLayout.JAVA_INT);

    if (target.byteSize() != bytes) {
        throw new AssertionError("Wrong layout size");
    }

    return ValueLayout.ADDRESS.withTargetLayout(target);
}
```

This is an **illustrative helper** in a class that has imported `java.lang.foreign.*`; calling it requires native-access permission because `withTargetLayout` is restricted. The one-million limit is only an **example policy**, not proof that the library allocated that many bytes. If `count` comes from untrusted input, it must also be verified against the library's actual capacity/contract.

**Do not use** a target sequence of size `Long.MAX_VALUE` just to bypass bounds checks. The Javadoc describes the ability to create an ultra-large view using a target sequence, but that is an **unsafe declaration**, not a guarantee that such a huge memory region actually exists.

## 13. The scope of a pointer view cannot substitute for the scope of the real allocation

The `MemorySegment.get(AddressLayout,long)` specification explicitly states that the pointer value is wrapped in a native segment **associated with the global scope**, with or without a target. From this follows:

```text
    MemorySegment target = dataOwner.allocate(...)
        |
        +-- scope = dataOwner.scope()
        |
        +-- slot.set(ADDRESS, 0, target)
                |
                +-- slot.get(ADDRESS.withTargetLayout(...), 0)
                        |
                        +-- pointer-derived segment
                              scope = global scope
                              byteSize = targetLayout.byteSize()
```

When `dataOwner.close()` runs:

- `target.scope().isAlive()` becomes false; access through `target` will be blocked.
- The pointer-derived view **does not** switch its scope to false, because it is not directly tied to `dataOwner`.
- The address value and size of the pointer-derived view may still look normal.
- **Do not dereference the pointer-derived view**, because the actual allocation has been freed.

This difference is not a “bug in FFM”: a native pointer **does not carry owner/lifetime metadata**. The API intentionally treats interpreting a pointer as a memory region as restricted and delegates spatial/temporal bounds responsibility to the code author.

### When should you use the original segment directly instead of a pointer-derived view?

If Java **already holds the original `MemorySegment target`** returned by `Arena.allocate`, prefer using `target.get/set` directly. It preserves the arena's exact bounds and scope. There is no need to round-trip through `slot.set(ADDRESS,...); slot.get(withTargetLayout,...)` just to read data that Java already owns.

Only decode a pointer into a typed view when the pointer actually originates from a native ABI or a data structure that requires reading a pointer. In that case, there must be an accompanying owner contract.

### A reasonable guard pattern

When the Java API is the owner or has permission to borrow a pointer from an owner, place all dereferences inside a lifecycle-managed operation:

```java
try (Arena dataOwner = Arena.ofConfined()) {
    MemorySegment target = dataOwner.allocate(ValueLayout.JAVA_INT);
    target.set(ValueLayout.JAVA_INT, 0, 42);

    // While target is alive: related pointers can be created/read.
    // Any pointer-derived view must only be used
    // within the window guaranteed before dataOwner closes.

    System.out.println(target.get(ValueLayout.JAVA_INT, 0));
}
```

If multiple threads use a shared arena, you need a protocol to block close while there are in-flight users. Checking `scope().isAlive()` once and dereferencing afterward is not an atomic reservation. With raw native pointers, the JVM cannot detect all native workers still using the allocation.

## 14. Pointers and JNI: two handle models that must not be mixed

In the native interoperability module, clearly distinguish:

- **FFM pointer:** `AddressLayout`/`MemorySegment` represents a native machine address and memory view. `withTargetLayout` declares the target region by `MemoryLayout`, and does not own the actual allocation.
- **JNI reference:** `jobject`, `jweak`, `jclass` are **JNI handles** managed by the JVM, **not** raw C pointers to Java objects that can be dereferenced arbitrarily.
- **JNI direct buffer:** `GetDirectBufferAddress` can provide a native address under API-specified conditions, but the backing buffer's lifetime must still be protected per contract; do not assume you can `free` that address.
- **C library pointer:** `void*`, `char*`, or struct pointers may carry their own ownership; the appropriate native destructor must be used if ownership is transferred.

Do not store a `jobject` into memory and interpret it as an `AddressLayout` native pointer to an object. Do not convert a `jweak` into `MemorySegment.ofAddress` and dereference it. They are **two completely different mechanisms**; mistakes can corrupt the JVM.

`AddressLayout.withTargetLayout` cannot protect the lifecycle of JNI global/local references or replace `DeleteGlobalRef`/`DeleteWeakGlobalRef`.

## 15. Common mistakes

| Mistake | What actually happens | How to fix |
| --- | --- | --- |
| “withTargetLayout(JAVA_INT) allocates 4 bytes of memory” | Only creates layout metadata and a 4-byte view when reading a pointer | Allocate/obtain a valid allocation separately, verify ownership |
| “Having byteSize() == 4 guarantees reading 4 bytes is safe” | View bounds are a caller-declared promise, not verification of actual allocation | Cross-check the C contract: real size and lifetime |
| “A pointer just read from a slot in an arena shares its scope” | Pointer-derived segments carry the **global scope** | Track the actual target owner with a separate mechanism |
| “loaded.scope().isAlive() is true, so the allocation is not freed” | Global scope can remain alive even after the target owner closes | Do not use after free; guard with owner/borrow |
| “Valid pointer alignment means the address is valid” | A dangling pointer can still be aligned | Verify provenance, lifetime, and valid allocation from contract |
| “A null pointer with a target having byteSize>0 means there is a buffer” | A null address still has no valid referent | Check `address()==0` before dereferencing |
| “withTargetLayout changes the pointer size stored in a struct” | Pointer size remains `ADDRESS.byteSize()` | Use target layout to describe data, not a new pointer width |
| “Use JAVA_LONG to read pointers on every ABI” | C pointer width may differ from Java long width | Use `ValueLayout.ADDRESS` for pointers |
| “C long is always the same as Java long” | LP64/LLP64 ABIs differ | Use a layout matching the struct header / `int64_t` / ABI |
| “A C string pointer always points to at least N bytes I pick” | Length and NUL position depend on contract | Use length-aware APIs, apply size caps and lifetime |
| “withTargetLayout allows reading across a closed arena” | It can allow access to a stale address and cause a crash | Never dereference after deallocation |
| “Just declare Long.MAX_VALUE to avoid bounds errors” | Extremely unsafe, view does not reflect actual allocation | Only declare accurate memory bounds |
| “If the slot owner closes, the target is immediately freed” | Source slot and target can belong to two different owners | Track each allocation's lifecycle separately |
| “If the target owner closes, the typed view automatically closes” | Pointer-derived views have global scope, no automatic invalidation | Block all uses after owner close |
| “A layout with names/types guarantees C data has the right type” | Layout only interprets bytes, does not verify struct ABI | Match byte order, field sizes, padding, alignment |

## 16. Review checklist when encountering AddressLayout.withTargetLayout

When reviewing code that uses a restricted target layout, answer **every question**:

1. **Address source:** where does the pointer come from? `Arena.allocate`, a struct field, a native return, a JNI direct buffer, or a foreign library?
2. **NULL:** is the pointer nullable? Is `address()==0` checked before every dereference?
3. **Allocation:** is it certain this is **real native memory**, not a virtualized address of a heap segment or a JNI handle?
4. **Size:** does the target layout match the exact `sizeof`/count/capacity allocated by the library? Are there overflow/input limits?
5. **Alignment:** do the pointer address and field targets satisfy the layout/ABI alignment? Is the data packed?
6. **Lifetime:** what determines when the pointer expires? `Arena.close`, `free`, another callback, the next C API call, or library unload?
7. **Ownership:** who is supposed to call the destructor? If borrowed, never free; if owned, which exact cleanup function?
8. **Threading:** are native workers/callbacks using the pointer when Java might close it? Is there thread affinity?
9. **Scope:** does the code mistake the global scope of a pointer-derived view for the owner scope of the actual allocation?
10. **Error paths:** when the pointer is null, target size is insufficient, allocation has expired, or native errors occur… what must the Java API return/throw?
11. **Copy timing:** if data is needed beyond a short lifetime, is it copied into an owned Java array or longer-lived arena memory?
12. **Restricted methods:** does the application configure native access appropriately and understand the unsafe responsibility of `withTargetLayout`?
13. **Tests:** do tests verify layout properties, correct alignment, view bounds, and ownership while alive; **and never test by dereferencing a freed pointer**?

### Quick decision table

| Case | Recommended choice |
| --- | --- |
| Java already holds the original `MemorySegment` with valid scope | Use the original segment directly, do not round-trip through a pointer |
| Only need to pass an opaque pointer to another native function | `ValueLayout.ADDRESS` without target, 0-byte view |
| Target is known to be a single `int` and lifetime is managed | `ADDRESS.withTargetLayout(JAVA_INT)` with native access enabled |
| Target is known to be 3 `int`s in a valid allocation | `ADDRESS.withTargetLayout(sequenceLayout(3,JAVA_INT))` |
| C returns a pointer to a struct with a known ABI | Create `MemoryLayout.structLayout` with exact fields/padding/size/alignment |
| Target length is determined at runtime | Verify count and capacity, then build the matching sequence layout |
| Pointer is nullable | Check `address()==0`; do not dereference when null |
| Native data must be kept after owner frees it | Copy to storage with an independent lifetime before freeing |
| Native pointer can expire asynchronously | Design owner/lease/copy/synchronization; target layout is not enough |
| No ownership/lifetime documentation | Do not dereference; verify the contract first |

## 17. Self-check exercises

**Question 1.** Does `AddressLayout p = ValueLayout.ADDRESS.withTargetLayout(JAVA_INT)` make `p.byteSize()` equal to 4?

**Answer:** Not necessarily; `p.byteSize()` is still the **pointer size** (e.g., 8 on a 64-bit system). When using `get(p,offset)`, the returned segment has `byteSize()` equal to the target size 4.

**Question 2.** Reading `slot.get(ADDRESS,0)` yields a non-zero address, but the result has `byteSize() == 0`. Why?

**Answer:** There is no target layout, so the API does not know the actual allocation size. A 0-byte view allows holding/passing the pointer opaquely without automatically granting permission to read target bytes.

**Question 3.** `slot.get(ADDRESS.withTargetLayout(sequenceLayout(3,JAVA_INT)),0)` can return a 12-byte view. Does that prove the C library allocated at least 12 bytes?

**Answer:** No. The view length is assigned from the target layout **declared by Java**. You must verify count/capacity and the C allocation contract; an incorrect declaration risks memory corruption.

**Question 4.** The pointer slot is allocated in `Arena A`, while the pointed-to data belongs to `Arena B`. Does closing A expire B?

**Answer:** Not automatically. A only owns the slot; the data's lifetime depends on B. While B is alive, a pointer previously read from the slot can still be valid (assuming no other invalidation condition).

**Question 5.** When B closes, `loaded.scope().isAlive()` is still true because `loaded` is a pointer-derived global-scope view. Can `loaded` be read?

**Answer:** No. The pointer-derived global scope **does not track the lifetime of the actual allocation**. Reading after `B.close` is a use-after-free and must be avoided.

**Question 6.** `slot` holds a null pointer. If a target layout is used, the result has `byteSize() = 4`; can `get(JAVA_INT,0)` be called?

**Answer:** No. Address 0 is not a valid referent; size is an annotation. Check `address()==0` and handle null per the contract.

**Question 7.** A pointer targets address +1, which is not 4-byte aligned. How does `withTargetLayout(JAVA_INT)` help?

**Answer:** When reading the address with the target layout, FFM can throw `IllegalArgumentException` if the target pointer is incompatible with 4-byte alignment. But this does not check whether the pointer is still alive or its actual size.

**Question 8.** A native method returns a pointer owned by the C library that only lives until the next native call. What must Java do to keep the contents long-term?

**Answer:** Copy the valid data **before** the next native call or invalidation occurs. Do not `free` a borrowed pointer; target layout does not extend lifetime.

**Question 9.** A C struct has `int32_t code`, `int64_t total` at offset 8, and total size 16. Can you just use `JAVA_INT` + `JAVA_LONG` back-to-back and assume it is right?

**Answer:** No. You must describe the 4-byte padding or equivalent ABI layout; use `structLayout(JAVA_INT, paddingLayout(4), JAVA_LONG)` as in the example. Then verify offsets, alignment, and sizeof.

**Question 10.** Should you use a `Long.MAX_VALUE` target sequence to avoid `IndexOutOfBoundsException` when reading a native pointer?

**Answer:** No. That declares overly broad bounds disproportionate to the actual allocation, easily leading to crashes/corruption. Only declare sizes based on a verified contract.

**Question 11.** Why is `withTargetLayout` marked restricted?

**Answer:** Because it can turn a zero-length pointer view into a memory region of a caller-declared size. If the declared size or lifetime does not match actual memory, accesses can escape the JVM's safety guarantees and cause severe errors.

**Question 12.** If Java already holds the original segment `MemorySegment data` from `Arena.allocate`, should it always convert to a pointer and use `withTargetLayout` to read?

**Answer:** No. The original segment already carries the exact size and scope managed by the arena. Using it directly reduces the risk of losing lifecycle information. A pointer-derived view is only needed when actually receiving an address from a native ABI.

## Official documentation

- [Java SE 22 — AddressLayout: withTargetLayout, targetLayout, withoutTargetLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/AddressLayout.html)
- [Java SE 24 — AddressLayout: restricted access and alignment](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/AddressLayout.html)
- [Java SE 22 — MemorySegment: zero-length pointers, get(AddressLayout), global scope](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Java SE 24 — MemorySegment: pointer read and access safety](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Java SE 24 — ValueLayout.ADDRESS](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [Java SE 24 — Arena: lifetime and deallocation rights](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html)
- [JEP 454 — Foreign Function & Memory API, finalized in JDK 22](https://openjdk.org/jeps/454)

**Remember:** `AddressLayout.withTargetLayout` declares **the expected view size and alignment of a pointer target**. It does not verify **whether the target memory region is real, accurately sized, alive, accessible, or owned by Java**. Every dereference must obey the native contract and lifecycle management of the actual allocation — **do not confuse a “typed pointer” with a “safe pointer”.**
