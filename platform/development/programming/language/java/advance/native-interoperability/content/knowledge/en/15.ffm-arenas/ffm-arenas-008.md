# SegmentAllocator, Layout-Based Allocation, and Large Memory Slicing Strategies

## Learning Objectives

In the Foreign Function & Memory API (**FFM**), **MemorySegment** objects describe memory regions; **MemoryLayout** specifies structure, size, and alignment; **Arena** determines the lifetime scope of the memory regions it owns. **SegmentAllocator** abstracts the allocation strategy. It is especially useful when you need many small objects, reusable buffers, or to split a large memory region into parts with separate access bounds.

After this lesson, you can:

1. Distinguish SegmentAllocator, MemoryLayout, MemorySegment, and Arena; explain why **Arena extends SegmentAllocator**.
2. Use **allocate(byteSize, byteAlignment)**, **allocate(MemoryLayout)**, **allocate(elementLayout, count)**, and **allocateFrom**.
3. Use **SegmentAllocator.slicingAllocator** to obtain consecutive slices from an allocated slab, understanding alignment padding and out-of-capacity errors.
4. Use **SegmentAllocator.prefixAllocator** to reuse a scratch buffer, clearly understanding that the memory regions of allocations overlap.
5. Use **MemorySegment.asSlice** to create views for a large region; distinguish a slice's access bounds from the actual backing memory capacity.
6. Design **slab, chunking, batching, and streaming** strategies with checks for overflow, alignment, ownership, concurrency, and arena lifetime.
7. Run a complete Java 22+ example with deterministic stdout; evaluate which allocation choice suits each native workload.

**Version:** The **java.lang.foreign** API was finalized in **JDK 22 (JEP 454)**. The Java code in this lesson uses **JDK 22 or later**. You cannot take the examples as-is and claim they compile on Java 17, because FFM in earlier versions had different API/incubator/preview forms.

## 1. Four Concepts to Separate

| Concept | Question It Answers | Limit to Remember |
| --- | --- | --- |
| **MemoryLayout** | "How many bytes are needed, how is it aligned, where are the fields?" | Java layouts must be verified against the C ABI if used for an actual C struct |
| **SegmentAllocator** | "How do I obtain a MemorySegment with sufficient size/alignment?" | Does not guarantee each allocation has its own backing memory |
| **MemorySegment** | "Which byte range am I allowed to access?" | It may only be a **view**, not owning the memory |
| **Arena** | "Who allocates, and when does the backing memory become invalid?" | When the Arena closes, the segments/slices it owns are no longer accessible |

Diagram:

~~~text
   MemoryLayout
      |  byteSize + byteAlignment
      v
   SegmentAllocator.allocate(layout)
      |
      +--- Arena: allocates managed memory
      |
      +--- slicingAllocator: slices sequentially from an existing slab
      |
      +--- prefixAllocator: reuses the beginning of the slab
      |
      v
   MemorySegment
      |  get/set, asSlice, copy
      v
   Native bytes within the scope of the arena/backing owner
~~~

Key point: **Arena is a type of SegmentAllocator**, so an API that only requires a SegmentAllocator can accept an Arena directly. However, a SegmentAllocator does not have to be an Arena and does not have to call malloc for every allocate call.

### Minimal Allocation Interface

SegmentAllocator is a functional interface with the abstract method:

~~~java
MemorySegment allocate(long byteSize, long byteAlignment);
~~~

Both parameters are in **bytes**. Alignment is an address constraint that must be positive and a power of 2 per the API. The allocator returns a corresponding MemorySegment or throws an error according to the implementation's policy.

Example delegating to an Arena:

~~~java
try (Arena arena = Arena.ofConfined()) {
    SegmentAllocator delegated = (bytes, alignment) ->
            arena.allocate(bytes, alignment);

    MemorySegment value = delegated.allocate(8, 8);
    value.set(ValueLayout.JAVA_LONG, 0, 123L);
}
~~~

This is a **Java 22+ snippet** that can be placed inside a Java method with `import java.lang.foreign.*`. This lambda only forwards the request to the Arena without creating pooling; normally you can use **arena** directly.

## 2. Layout-Based Allocation: Fewer Magic Numbers

The convenience method:

~~~java
MemorySegment result = allocator.allocate(layout);
~~~

uses **layout.byteSize()** and **layout.byteAlignment()**. Therefore, a well-structured layout is better than allocations based on byte counts scattered throughout the code.

### 2.1. A Single Primitive Value

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment counter = arena.allocate(ValueLayout.JAVA_INT);
    counter.set(ValueLayout.JAVA_INT, 0, 42);
    System.out.println(counter.get(ValueLayout.JAVA_INT, 0));
}
~~~

This is a snippet with output **42**; JAVA_INT has a size of 4 bytes. Do not confuse **byteSize** with the number of elements.

### 2.2. A Sequence of Values

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemoryLayout layout = MemoryLayout.sequenceLayout(
            5, ValueLayout.JAVA_INT
    );
    MemorySegment numbers = arena.allocate(layout);

    for (int index = 0; index < 5; index++) {
        numbers.setAtIndex(ValueLayout.JAVA_INT, index, index + 1);
    }
    System.out.println(numbers.getAtIndex(ValueLayout.JAVA_INT, 4));
}
~~~

The output is **5**. A sequence of 5 ints has a total of 20 bytes. You can use the shorthand:

~~~java
MemorySegment numbers = arena.allocate(ValueLayout.JAVA_INT, 5);
~~~

This is a snippet assuming a live arena already exists. The **allocate(elementLayout, count)** overload constructs a sequence layout from each element's size and count, checking for negative values or multiplication overflow. Do not type **arena.allocate(5)** thinking you have allocated enough for **5 ints**: allocate(5) only requests **5 bytes**.

### 2.3. Initializing Data Upon Allocation

**allocateFrom** helps allocate and copy initial data:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment values =
            arena.allocateFrom(ValueLayout.JAVA_INT, 10, 20, 30);
    System.out.println(
            values.getAtIndex(ValueLayout.JAVA_INT, 1)
    ); // 20

    MemorySegment text = arena.allocateFrom("hello");
    // text contains a UTF-8 C string with a NUL terminator.
}
~~~

**allocateFrom(String)** uses standard UTF-8 on JDK 22 and includes a terminator. A U+0000 character in the middle is still encoded as byte 00, so a C API reading with strlen may treat the text as truncated. For primitive arrays, allocateFrom **does not automatically add a C-protocol terminator element**.

Overloads that copy data may incur conversion/copy overhead. Layout-based allocation is not zero-copy by default and does not guarantee synchronization with the original source.

## 3. StructLayout Requires Explicit Padding and Alignment

Suppose a record consists of a Java int and a Java long, requiring the long at byte offset 8:

~~~java
MemoryLayout record = MemoryLayout.structLayout(
    ValueLayout.JAVA_INT.withName("id"),
    MemoryLayout.paddingLayout(4),
    ValueLayout.JAVA_LONG.withName("amount")
);
~~~

This layout has:

| Component | Offset | Size |
| --- | ---: | ---: |
| **id** | 0 | 4 bytes |
| **padding** | 4 | 4 bytes |
| **amount** | 8 | 8 bytes |
| **Total** |  | **16 bytes** |

The natural byte alignment of the layout is 8 due to JAVA_LONG. You can find the offset using a path:

~~~java
long amountOffset = record.byteOffset(
        MemoryLayout.PathElement.groupElement("amount")
);
~~~

Do not repeat the magic number **8** in multiple places if the field offset is already represented by MemoryLayout. **MemoryLayout.structLayout does not automatically insert C ABI padding.** When describing a C struct, you must check **sizeof, _Alignof, offsetof**, compiler flags, and the data model of the actual native library.

**Important note:** In the demo, the layout is defined using Java ValueLayouts, so the size/offset results are fixed. That **does not prove** every C struct with an int and a long is the same. For example, C `long` on Windows x64 is typically 32 bits, unlike Java's 64-bit `long`.

## 4. Strategy 1: slicingAllocator Cuts Consecutive Slices

Factory in JDK 22:

~~~java
SegmentAllocator allocator =
        SegmentAllocator.slicingAllocator(slab);
~~~

With **slab** being a MemorySegment already allocated from an Arena, the allocator returns consecutive slices. Each allocation may add a small padding gap to ensure alignment.

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment slab = arena.allocate(64, 8);
    SegmentAllocator bump =
            SegmentAllocator.slicingAllocator(slab);

    MemorySegment a = bump.allocate(ValueLayout.JAVA_LONG);
    MemorySegment b = bump.allocate(ValueLayout.JAVA_LONG);

    a.set(ValueLayout.JAVA_LONG, 0, 11L);
    b.set(ValueLayout.JAVA_LONG, 0, 22L);
}
~~~

In the example, the slab starts at an 8-byte aligned address. Both allocations are 8 bytes aligned to 8, so **a** occupies offsets 0–7, and **b** occupies offsets 8–15. They do not overlap when considering only the allocations returned by **bump**.

### 4.1. Bump Allocator Model

~~~text
Slab: 64 bytes, base aligned 8
+-------------+-------------+-------------------------+
|   a: 8 B    |   b: 8 B    |       unallocated       |
+-------------+-------------+-------------------------+
offset 0      8            16                       64
                                  ^
                    cursor moves past b
~~~

**Each successful allocation:** the allocator finds a position satisfying the alignment and returns a view. **It does not automatically allocate additional slabs**, and there is no individual free mechanism per view; the lifetime of all views still follows the original slab/arena.

### 4.2. Padding Can Consume Capacity

For example, allocating 1 byte first and then an 8-byte long can produce this layout:

~~~text
offset:  0 1 2 3 4 5 6 7 | 8 9 10 11 12 13 14 15
         [a] [ padding ] | [       b: 8 B        ]
~~~

The total logical data is only 1 + 8 = 9 bytes, yet the cursor has moved to offset 16. Therefore, it is **not always accurate** to take the sum of each request's `layout.byteSize` as the minimum slab capacity. With mixed layouts, you also have to account for alignment padding.

If you use a layout with a suitable stride and a properly aligned base, much waste can be avoided; however, you still must verify the ABI requirements of the real data.

### 4.3. When the Slab Runs Out of Space

~~~java
try (Arena arena = Arena.ofConfined()) {
    SegmentAllocator bump =
            SegmentAllocator.slicingAllocator(
                    arena.allocate(16, 8)
            );

    bump.allocate(ValueLayout.JAVA_LONG);
    bump.allocate(ValueLayout.JAVA_LONG);

    try {
        bump.allocate(ValueLayout.JAVA_LONG);
    } catch (IndexOutOfBoundsException expected) {
        System.out.println("slab full");
    }
}
~~~

This is an illustrative snippet. The third call wants another 8 bytes while the 16-byte slab is already full, so **slicingAllocator** throws **IndexOutOfBoundsException**.

You should not assume you can retry on the **same allocator** and that it will automatically expand. You must create a new slab/allocator or handle the error/quota choice. When the number of records can be estimated, calculating capacity upfront is usually simpler and more efficient than using exceptions as a regular control-flow loop.

### 4.4. Thread Safety of slicingAllocator

According to the JDK 22 documentation, **slicingAllocator is not thread-safe**. Even if the slab comes from **Arena.ofShared()**, that does not automatically make the allocator's cursor concurrent-safe. Two threads allocating through the same allocator without synchronization can race on internal state.

Better design approaches:

- Each worker owns its own slab and slicingAllocator.
- One thread allocates non-overlapping slices and then hands them off to workers when the scope permits.
- Use a custom allocator with tested synchronization/atomic reservation if truly needed.
- If you only need to allocate from a shared arena, you can use the appropriate Arena directly without adding a shared cursor yourself.

## 5. Strategy 2: prefixAllocator Reuses a Buffer

Factory:

~~~java
SegmentAllocator reusable =
        SegmentAllocator.prefixAllocator(scratch);
~~~

Unlike slicingAllocator, **prefixAllocator** returns a slice starting at **offset 0 of the same segment** on every call, provided the size/alignment fits.

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment scratch = arena.allocate(32, 8);
    SegmentAllocator reused =
            SegmentAllocator.prefixAllocator(scratch);

    MemorySegment a = reused.allocate(ValueLayout.JAVA_INT);
    a.set(ValueLayout.JAVA_INT, 0, 10);

    MemorySegment b = reused.allocate(ValueLayout.JAVA_INT);
    b.set(ValueLayout.JAVA_INT, 0, 20);

    System.out.println(a.get(ValueLayout.JAVA_INT, 0));
}
~~~

The output is **20**, not 10. Both views point to the beginning of scratch. This is **intentional overlap**.

### When Is Reuse Valid?

- A parser needs temporary memory to process **one request at a time**.
- A downcall needs a place to write a small result and **the previous result is already done being used** before allocating space for the next one.
- A streaming loop wants to reuse a buffer, **without keeping references/pointers to the next iteration**.

Do not use prefixAllocator when multiple results need to be kept simultaneously. It is especially dangerous when a C API retains a pointer asynchronously: the next write can alter data that a native worker is still reading.

**Common misconception:** The JDK 22 documentation states that **prefixAllocator itself is thread-safe**, but the memory segments it allocates **can overlap**. Multiple threads writing to the same prefix still have a data race; the thread-safety of the allocator **does not automatically synchronize the data inside**.

### Comparing the Two Factories

| Criterion | slicingAllocator | prefixAllocator |
| --- | --- | --- |
| Allocation position | Consecutive slices, cursor advances | Slice always starts at prefix offset 0 |
| Can later allocations overwrite earlier ones? | No, among slices successfully allocated by the allocator | **Yes, by design** |
| Automatically grows slab capacity? | No | No |
| Out of capacity | Throws **IndexOutOfBoundsException** | Throws **IndexOutOfBoundsException** if request does not fit |
| Thread safety of the allocator | **Not thread-safe** | The allocator itself can be called concurrently; overlapping data is still unsafe |
| Best suited for | Multiple records coexisting in a batch | Temporary scratch used sequentially |

Do not see the name "allocator" and assume all returned results are independent like separate malloc calls.

## 6. MemorySegment.asSlice: Cutting Views Without Allocating More Memory

Besides the two factories, you can choose byte offsets manually:

~~~java
MemorySegment child = parent.asSlice(startByte, lengthByte);
~~~

Or slice to the exact size/alignment of a layout:

~~~java
MemorySegment record = parent.asSlice(startByte, recordLayout);
~~~

Properties:

1. **Views share backing memory**: reading/writing through child sees parent's data at the same byte offset, and vice versa.
2. **Narrower spatial bounds**: child's byteSize is only length/layout, so accesses outside the slice are rejected even if parent still has space.
3. **Inseparable temporal scope**: child is subject to the parent/arena lifetime; closing the arena invalidates both.
4. **Thread accessibility follows scope**: a slice from a confined arena cannot become shared merely via asSlice.
5. **asSlice(offset, layout)** checks the alignment of the slice position against the layout.

Example:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment parent = arena.allocate(1_024, 8);
    MemorySegment child = parent.asSlice(128, 64);

    child.set(ValueLayout.JAVA_INT, 0, 777);
    System.out.println(parent.get(ValueLayout.JAVA_INT, 128));
}
~~~

Output **777**. After closing the arena, neither parent nor child can be accessed anymore. Java holding a reference to child **does not mean** the parent's native backing memory stays alive.

### Slice vs. Copy

- **asSlice**: creates another view over the **same byte region**.
- **MemorySegment.copy** or **copyFrom**: transfers contents from a source segment to an existing destination region, depending on the overload.
- **arena.allocate**: requests a new memory region managed by the arena.
- **SegmentAllocator.slicingAllocator**: distributes views within a base slab.

If an **independent copy** is required for concurrent processing without overwriting, you must allocate separate backing memory and copy; asSlice alone does not create independence.

## 7. Slicing Large Memory: Two Different Kinds of "Savings"

A 1 GiB region can be divided into 64 KiB views using asSlice. That helps **each iteration's code see only 64 KiB** and reduces the risk of reading past a chunk's bounds.

However, **if you have already allocated 1 GiB, the total native allocation is still 1 GiB**. Creating views does not shrink 1 GiB down to 64 KiB.

~~~text
Allocated backing region: 1 GiB
+--------+--------+--------+----------- ... --------+
| chunk0 | chunk1 | chunk2 |                      |
+--------+--------+--------+----------- ... --------+
  view     view     view

No copy or separate malloc per view.
The backing region lives until the owner closes/releases it.
~~~

Distinguish clearly:

| Strategy | Backing Memory | Strengths | Costs/Limits |
| --- | --- | --- | --- |
| One large slab + **asSlice** | Equal to entire slab size | Clear offsets, per-part bounds, zero copy | Peak memory still equals slab |
| Slab + **slicingAllocator** | Equal to slab size | Many small objects with same lifetime, fast allocation | Cursor/capacity, no free per slice |
| One scratch + **prefixAllocator** | Near scratch size | Reuse, few new allocations | Cannot keep multiple results simultaneously |
| **Batch arenas** | Sum of in-flight batches | Can close and release each batch | Requires orchestration and backpressure |
| **Streaming/mapped window** | Only windows currently in use | Bounded working memory | I/O, partial reads, more complex lifecycle |

### Chunk Loop Using long Properly

~~~java
long offset = 0;
while (offset < big.byteSize()) {
    long remaining = big.byteSize() - offset;
    long take = Math.min(chunkBytes, remaining);

    MemorySegment chunk = big.asSlice(offset, take);
    // Process chunk within its byteSize bounds.

    offset += take;
}
~~~

This is a snippet, requiring **big** to be valid and **chunkBytes > 0**. Use **long** because a segment's size can exceed **Integer.MAX_VALUE**. Computing **remaining = total - offset** before calculating take avoids arithmetic bugs like **offset + chunkBytes** overflowing long.

If **chunk** needs to hold int elements, ensure take and offset match alignment/stride. If an element can straddle two chunks, you must carry over the remainder or align chunk boundaries to the record size.

### True Streaming

For files much larger than the native RAM budget, allocate **one 64 KiB buffer**, load a portion, process it, and **only reuse after all consumers are done**. Thus temporary memory can be close to **O(chunkSize)**, without pre-allocating the entire file.

If multiple batches are processed in parallel, peak memory is close to **running batches × batch size**, plus runtime overhead. You must limit the number of **in-flight** batches to avoid losing control of RSS.

## 8. Capacity Calculation: Size, Alignment, and Overflow

### 8.1. Layout Size and Record Count

For N records of the same layout, logical bytes are:

\[
B = N \times \mathrm{recordLayout.byteSize()}
\]

In code, avoid overflow:

~~~java
long bytes = Math.multiplyExact(
        count,
        recordLayout.byteSize()
);
~~~

This snippet assumes count and recordLayout are already declared. **Math.multiplyExact** throws **ArithmeticException** if the multiplication exceeds the long range. Afterward, you still need to check **bytes ≤ application quota**; a value that fits in long can still exceed RAM/swap/container limits.

### 8.2. Alignment Padding

A slab-based allocator may have to advance the cursor to an aligned address per request requirements. With an 8-aligned base:

~~~text
1 byte of data + 7 bytes of padding + 8 bytes of data
= 16 bytes consumed to store 9 useful bytes
~~~

Therefore, slab capacity may need to be larger than the sum of requests' layout.byteSize if sizes/alignments are mixed. In practice, it also depends on allocation order, base address alignment, and allocator policy.

**Do not use a hand-rolled alignedOffset formula without overflow checks.** Alignment is a power of 2, but adding `offset + align - 1` can still overflow long. Whenever possible, use the official FFM methods with validated layouts, and manage quotas before allocating.

### 8.3. Allocation Exhaustion

- **slicingAllocator**: out of space → **IndexOutOfBoundsException**, needs a new slab or an error report.
- **Arena**: may fail to allocate due to memory pressure or invalid requests; do not turn failures into an infinite retry loop.
- **prefixAllocator**: request larger than the usable prefix → **IndexOutOfBoundsException**.
- **asSlice**: offset/length outside parent → **IndexOutOfBoundsException**.

An error handler should not broadly catch all Throwables and return an "empty buffer": that can mask allocation errors and cause a C API to write past real memory bounds.

## 9. Complete Java 22+ Example

This example does not require a native C library. It demonstrates **allocate(MemoryLayout)**, layout padding, slicingAllocator, prefixAllocator, and asSlice over a 1 MiB region.

Create file **AllocatorSlicingDemo.java**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SegmentAllocator;
import java.lang.foreign.ValueLayout;

public final class AllocatorSlicingDemo {
    private static final MemoryLayout ENTRY =
            MemoryLayout.structLayout(
                    ValueLayout.JAVA_INT.withName("id"),
                    MemoryLayout.paddingLayout(4),
                    ValueLayout.JAVA_LONG.withName("amount")
            );

    private static final long AMOUNT_OFFSET =
            ENTRY.byteOffset(
                    MemoryLayout.PathElement.groupElement("amount")
            );

    private AllocatorSlicingDemo() {
    }

    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            // Slab holding multiple small allocations.
            MemorySegment slab = arena.allocate(
                    256, ENTRY.byteAlignment()
            );
            SegmentAllocator bump =
                    SegmentAllocator.slicingAllocator(slab);

            // Two coexisting records, 16 bytes each.
            MemorySegment first = bump.allocate(ENTRY);
            MemorySegment second = bump.allocate(ENTRY);

            first.set(ValueLayout.JAVA_INT, 0, 7);
            first.set(ValueLayout.JAVA_LONG, AMOUNT_OFFSET, 70L);
            second.set(ValueLayout.JAVA_INT, 0, 8);
            second.set(ValueLayout.JAVA_LONG, AMOUNT_OFFSET, 80L);

            // Array of 4 ints: 4 * 4 = 16 bytes.
            MemoryLayout fourInts =
                    MemoryLayout.sequenceLayout(
                            4, ValueLayout.JAVA_INT
                    );
            MemorySegment numbers = bump.allocate(fourInts);

            int sum = 0;
            for (int i = 0; i < 4; i++) {
                numbers.setAtIndex(ValueLayout.JAVA_INT, i, i + 1);
                sum += numbers.getAtIndex(ValueLayout.JAVA_INT, i);
            }

            // Separate scratch at byte offset 128: avoids the region
            // already used by the 2 records and the array before it.
            MemorySegment scratch = slab.asSlice(128, 32);
            SegmentAllocator reusable =
                    SegmentAllocator.prefixAllocator(scratch);

            MemorySegment oldView =
                    reusable.allocate(ValueLayout.JAVA_INT);
            oldView.set(ValueLayout.JAVA_INT, 0, 111);

            MemorySegment newView =
                    reusable.allocate(ValueLayout.JAVA_INT);
            newView.set(ValueLayout.JAVA_INT, 0, 222);

            boolean reused =
                    oldView.get(ValueLayout.JAVA_INT, 0) == 222;

            // 1 MiB divided into 16 views, 64 KiB each.
            MemorySegment large = arena.allocate(
                    1_048_576L,
                    ValueLayout.JAVA_INT.byteAlignment()
            );

            final long chunkSize = 65_536L;
            long offset = 0;
            long chunkCount = 0;
            long markerSum = 0;

            while (offset < large.byteSize()) {
                long remaining = large.byteSize() - offset;
                long take = Math.min(chunkSize, remaining);
                MemorySegment slice = large.asSlice(offset, take);

                int marker = (int) ++chunkCount;
                slice.set(ValueLayout.JAVA_INT, 0, marker);
                markerSum += slice.get(ValueLayout.JAVA_INT, 0);

                offset += take;
            }

            System.out.println("layoutBytes=" + ENTRY.byteSize());
            System.out.println("amountOffset=" + AMOUNT_OFFSET);
            System.out.println(
                    "first=" + first.get(ValueLayout.JAVA_INT, 0)
                    + ":" + first.get(
                            ValueLayout.JAVA_LONG, AMOUNT_OFFSET
                    )
            );
            System.out.println(
                    "second=" + second.get(ValueLayout.JAVA_INT, 0)
                    + ":" + second.get(
                            ValueLayout.JAVA_LONG, AMOUNT_OFFSET
                    )
            );
            System.out.println("arraySum=" + sum);
            System.out.println("prefixReused=" + reused);
            System.out.println("chunks=" + chunkCount);
            System.out.println("chunkMarkerSum=" + markerSum);
        }
    }
}
~~~

### Compile and Run

**JDK 22+** is required. Do not use JDK 17's javac for the class above:

~~~bash
javac AllocatorSlicingDemo.java
java AllocatorSlicingDemo
~~~

The demo operations only use FFM memory allocation/access; there is no Linker.downcall or native symbol loading, so **--enable-native-access is not needed** for this specific example on JDK 22.

**Exact stdout on a successful run:**

~~~text
layoutBytes=16
amountOffset=8
first=7:70
second=8:80
arraySum=10
prefixReused=true
chunks=16
chunkMarkerSum=136
~~~

### Result Analysis

- **layoutBytes=16**: 4-byte int, 4-byte padding, 8-byte long.
- **amountOffset=8**: obtained via layout path; no hardcoded offset when reading/writing amount.
- **first=7:70**, **second=8:80**: slicingAllocator allocates two non-overlapping views of the slab.
- **arraySum=10**: the sequence 1,2,3,4 is stored in a sequence layout and summed using getAtIndex.
- **prefixReused=true**: oldView and newView both point to the prefix; writing 222 through the new view also makes the old view read 222. This is the **intended behavior of prefixAllocator**, but unsuitable if the old data still needs to be used.
- **chunks=16**: 1,048,576 / 65,536 = 16 views.
- **chunkMarkerSum=136**: 1 + 2 + ... + 16 = 136, read from offset 0 of each view.
- **Arena.close** after the try block renders all segments belonging to the arena no longer validly accessible; there is no individual free operation for slices.

### Demo Limitations

This is a **pure-Java FFM allocation** exercise; it does not verify a real C struct's ABI, has no file streaming, uses no multithreading, and does not let native C retain pointers. The output values are derived from the source and API contract; to verify execution on your machine, you still need to run it with an actual JDK 22+.

An important point: the 1 MiB slicing section **still occupies 1 MiB of backing memory**. It demonstrates working view by view, rather than demonstrating peak RAM savings of a streaming pipeline.

## 10. Arena Lifecycle and Thread Accessibility

### 10.1. Arena.ofConfined()

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment block = arena.allocate(256);
    MemorySegment view = block.asSlice(0, 32);
    view.set(ValueLayout.JAVA_INT, 0, 9);
}
~~~

A confined arena allows access on the **thread owning the scope** and controlled release upon closing. This is the right choice for per-request/batch allocation on a single thread.

### 10.2. Arena.ofShared()

~~~java
try (Arena arena = Arena.ofShared()) {
    MemorySegment block = arena.allocate(256);
    // Workers can access according to shared arena rules,
    // but data must still be synchronized and the scope closed at the right time.
}
~~~

A shared arena allows use from multiple threads; **it does not make Java/C data races disappear on their own**. Slices handed to multiple threads should be non-overlapping if processed independently, and the arena must only be closed after the last consumer finishes.

**Extremely important:** A shared arena **does not make slicingAllocator thread-safe**; per JDK 22, this allocator has an unsafe cursor if multiple threads allocate concurrently.

### 10.3. Arena.ofAuto() and Arena.global()

- **Arena.ofAuto()** has automatic lifetime management; the exact time when native memory is reclaimed is nondeterministic.
- **Arena.global()** lives for the lifetime of the VM and is not closed with try-with-resources.

For large native data that needs explicit per-batch release, Arena.ofConfined/ofShared with controlled close generally makes peak memory easier to predict.

### 10.4. Slices Inherit the Owner's Scope

Keeping a MemorySegment slice in a Java List does not keep the backing memory alive independently. If the arena owning the parent is closed, all related views become invalid. **There is no free(slice)** in FFM; to release part of the data early, allocate that part in a separate arena/batch with its own lifetime from the start.

## 11. Slab, Batch, and Streaming Strategies in Practice

### A. Many Small Records Living in the Same Batch

- Allocate a slab with an Arena within budget.
- Use slicingAllocator to create records by layout.
- Do not close the arena while any record is still in use.
- Close the entire arena when the whole batch finishes.

Advantages are locality and fewer small allocation operations. Disadvantages are **the inability to free an individual record**, and the need to know the quota and reserve for padding.

### B. Temporary Buffer for Sequential Tasks

- Allocate a small scratch buffer.
- Use prefixAllocator or asSlice to obtain an appropriate view.
- Finish processing, then overwrite the old portion for the next task.

The advantage is reuse without growing memory with the number of requests. The disadvantage is **old results must not be shared while the buffer is being reused**.

### C. Very Large Existing Region Needing Chunk-by-Chunk Processing

- Obtain the actual total **byteSize**.
- Determine a positive chunkSize compatible with alignment.
- Loop with a long offset; use **remaining = total - offset** and asSlice.
- Operate only within the slice's bounds.
- Do not assume creating slices reduces the parent's allocation.

Work can be split across workers using non-overlapping slices from a shared arena, but synchronization, lifetime, and error policies must be managed.

### D. Data Larger Than the RAM Budget

Do not allocate an entire 200 GiB file just to create 64 KiB views. Instead, use streaming, mapped windows, or multiple batches with a bounded number running concurrently. This approach can keep native working memory close to **O(chunkSize × number of in-flight buffers)**.

A batch may only be released when no worker, callback, or native library is still using its pointers.

### E. C API Retaining a Pointer After Returning

If native C stores a MemorySegment address for asynchronous use, **do not close the arena or reuse the prefix** as soon as the downcall finishes. FunctionDescriptor and SegmentAllocator do not infer this contract automatically; an unregister/drain API or explicit ownership transfer mechanism is needed.

## 12. Notes on ABI, C Pointers, and Deallocators

If memory is allocated by a Java Arena, the Arena is responsible for releasing it according to scope. If a C API **allocates memory itself and returns a pointer**, do not assume Arena.close can free that address. You must know the deallocator provided by the library (free, release, destroy, or a custom allocator).

Similarly, Java's **MemoryLayout.structLayout** does not prove compatibility with a compiled C struct. When passing a struct pointer to C, verify:

- **sizeof**, **_Alignof**, **offsetof** of the fields to be used.
- C types with ABI-dependent widths such as **long** and **size_t**.
- Endianness if the data is a binary format/ABI with specific requirements.
- Whether the pointer can be null; whether length is in bytes or elements.
- Whether the native function only borrows the pointer during the call or stores it for later use.
- Who closes the arena, and who is responsible for unregistering callbacks and cleanup.

FFM checks bounds/lifetime when Java code accesses a MemorySegment, but **cannot protect against all native C code bugs** once a raw pointer is handed to C. A C function receiving a wrong pointer and capacity can still write out of bounds or hold a dangling pointer.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating every allocate as an independent malloc | Wrong ownership/free | Distinguish arena-owned memory from slices of a slab |
| Passing element count as byteSize | Under-allocated bytes | Use allocate(elementLayout,count) |
| Forgetting alignment padding in a slab | Runs out of space early | Calculate capacity with padding, check quota |
| Thinking structLayout adds C padding automatically | Wrong layout or invalid layout | Explicit padding and verify against ABI |
| Sharing slicingAllocator across multiple threads | Cursor race | Per-thread instance or synchronization |
| Using prefixAllocator to keep multiple results | Later call overwrites earlier one | Use slicingAllocator/arena when non-overlap is needed |
| Assuming prefix thread-safety means data is thread-safe | Data race | Protect data or use per-thread scratch |
| Thinking asSlice allocates new memory | Misjudging RSS | Note that the backing region remains intact |
| Closing arena while native worker uses pointer | Use-after-free | Wait for worker/drain before closing |
| Using int offset for regions >2 GiB | Overflow | Use long, Math.multiplyExact |
| Using get/set at a misaligned offset | Access exception | Choose valid layout/offset/alignment |
| Using unaligned layout to mask a wrong C ABI | Native function may still violate contract | Verify ABI, only use unaligned when format allows |
| Letting C retain pointer to prefix scratch across requests | Reading overwritten data | Buffer with dedicated ownership or completion protocol |
| One giant slab for streaming data | High peak native RSS | Chunk/batch/reuse with backpressure |
| Ignoring allocation exhaustion | Invalid writes or improper recovery | Limit capacity and handle errors explicitly |

## 14. Pre-Production Checklist

- [ ] Use **JDK 22+** if relying on stable FFM such as the APIs in the example.
- [ ] Have **layouts** with correct byteSize, byteAlignment, padding, and actual ABI if interacting with C.
- [ ] Choose **Arena** based on owner and release timing; do not let slices escape scope invalidly.
- [ ] Allocate by layout/count instead of confusing element count with byte count.
- [ ] With slicingAllocator, account for alignment padding and handle capacity exhaustion.
- [ ] Do not freely share non-thread-safe slicingAllocator.
- [ ] With prefixAllocator, ensure prior data is no longer used when reusing.
- [ ] With asSlice, clearly understand that the view shares memory/scope with the parent.
- [ ] Use **long offsets**, overflow-safe arithmetic, and native byte quota limits.
- [ ] For large data, distinguish **slicing views over a large backing** from **streaming to reduce peak memory**.
- [ ] If multithreaded, choose shared/confined arena properly and add synchronization.
- [ ] If using a C API, confirm ownership, pointer retention, length, and deallocator.
- [ ] Test bounds, misalignment, allocation exhaustion, arena close, races, and native crashes.
- [ ] Benchmark slab size, allocation rate, copy cost, RSS, and latency on real workloads.

## 15. Self-Check Questions

**1. Are Arena and SegmentAllocator two names for the same object?**

**Answer:** No. Arena **extends SegmentAllocator** and manages the lifetime of allocations. However, a SegmentAllocator may simply return slices of a slab owned by another Arena.

**2. What information does allocate(MemoryLayout) use?**

**Answer:** It uses **layout.byteSize()** and **layout.byteAlignment()** to issue the allocation request. The layout can be primitive, sequence, or struct.

**3. Does slicingAllocator automatically allocate another slab when it runs out of space?**

**Answer:** No. It throws **IndexOutOfBoundsException** if it cannot find a slice matching the size/alignment in the given backing segment.

**4. When prefixAllocator returns a second result, is the first result still independent?**

**Answer:** No. It reuses the prefix; both views can point to the same bytes and be overwritten.

**5. Does slicing a 1 GiB MemorySegment into 64 KiB views reduce native allocation to 64 KiB?**

**Answer:** No. Slicing only restricts the access bounds of each view; the backing memory is still 1 GiB.

**6. Does Arena.ofShared make slicingAllocator thread-safe?**

**Answer:** No. A shared arena allows threads to access memory according to scope, but an individual slicingAllocator's cursor is still not thread-safe.

**7. Why must Math.multiplyExact be used for count × recordSize?**

**Answer:** To avoid long overflow causing an incorrect allocation capacity. Afterward, you still need quota limits and memory pressure handling.

**8. When is prefixAllocator a suitable choice?**

**Answer:** When needing a scratch buffer reused **sequentially**, prior data is no longer used, and no native callback/worker retains the pointer.

**9. Can you manually free a single slice of a slab before the Arena closes?**

**Answer:** Not as an independent allocation. A slice is a view sharing backing/lifetime; to release per batch, you must separate ownership/arenas by design.

**10. If a C library retains a pointer after a downcall returns, can the Arena be closed immediately?**

**Answer:** No. The memory must stay alive until C no longer uses the pointer, which may require unregistering/draining workers/callbacks before closing.

## Official Documentation

- [Java SE 22 — SegmentAllocator](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SegmentAllocator.html).
- [Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html).
- [Java SE 22 — MemoryLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html).
- [Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html).
- [JEP 454 — Foreign Function & Memory API finalized in JDK 22](https://openjdk.org/jeps/454).

**Conclusion:** **SegmentAllocator** decides how views/memory are allocated on request, **MemoryLayout** decides size/alignment, and **Arena** manages ownership/lifetime. **slicingAllocator** is good for many objects living together in a slab, **prefixAllocator** for sequential scratch reuse, and **asSlice** for bounded views over a large backing. To truly save native RAM, you must manage **backing size, the number of in-flight buffers, and release timing**, not just create many slices.
