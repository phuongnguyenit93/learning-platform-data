# `allocate`, `wrap`, and Shared Backing Data in Java NIO Buffer

## 1. Why Distinguish Buffer Creation from Data Sharing?

`java.nio.Buffer` is the foundation of NIO buffers; concrete types such as `ByteBuffer`, `CharBuffer`, and `IntBuffer` operate on data through a **backing storage** and a set of control parameters: **position**, **limit**, and **capacity**. Two calls that look nearly identical can carry completely different data-management semantics:

```java
ByteBuffer allocated = ByteBuffer.allocate(4);
byte[] bytes = {10, 20, 30, 40};
ByteBuffer wrapped = ByteBuffer.wrap(bytes);
```

This is an illustrative snippet requiring `import java.nio.ByteBuffer`. Both buffers have `capacity() == 4`, yet:

- `allocate(4)` allocates **new backing storage**. No caller-supplied array is shared at the outset.
- `wrap(bytes)` creates a **buffer viewing the exact existing `bytes` array**. No data is copied. Mutating elements from one side is visible from the other.
- The same backing data can have **multiple buffer views**, each with its own `position`, `limit`, and `mark`. Moving one view's cursor does not move another view's cursor.
- "Independence of read/write position" does **not** mean "independence of contents."

This lesson focuses on `allocate`, `wrap`, identifying shared backing regions, and mistakes made when treating buffers as independent copies.

## 2. Buffer Model: Backing Storage and Access State

A typical buffer has four related concepts:

| Property | Meaning |
|---|---|
| `capacity` | Maximum number of elements the buffer can hold; fixed throughout the buffer's lifetime |
| `limit` | First index not permitted for relative read/write; bounds the active region |
| `position` | Index of the next relative `get()`/`put()` operation |
| `mark` | Saved index for `reset()`; may be unset |

Key invariant: `0 <= position <= limit <= capacity`. In NIO code, an "element index" is **relative to the current buffer**, not automatically an index in the underlying Java array.

Example diagram, a buffer with `capacity=8, position=2, limit=6`:

```text
index:       0    1    2    3    4    5    6    7
           +----+----+----+----+----+----+----+----+
storage:   |    |    |    |    |    |    |    |    |
           +----+----+----+----+----+----+----+----+
                      ^                   ^
                   position              limit
           <----------- capacity = 8 ----------->
                     <remaining = 4>
```

`remaining() == limit - position`. `get()` reads at `position` and increments `position`; `put(value)` writes at `position` and increments it. `get(index)`/`put(index, value)` are **absolute** operations within the valid index range and do not advance `position`. For single-element `get(index)`/`put(index, value)`, the index must be less than `limit`. When creating a new slice, index 0 of the slice can map to a different offset in the shared storage.

**Important distinction:** calling `clear()`, `flip()`, or `rewind()` adjusts read/write state; they do **not** erase physical array contents or allocate new storage.

## 3. `ByteBuffer.allocate(capacity)` — Allocating New Backing Storage

```java
import java.nio.ByteBuffer;

ByteBuffer buffer = ByteBuffer.allocate(5);
System.out.println(buffer.capacity());  // 5
System.out.println(buffer.position());  // 0
System.out.println(buffer.limit());     // 5
System.out.println(buffer.isDirect());  // false
System.out.println(buffer.hasArray());  // true
```

This is an illustrative snippet that can be placed inside `main`. `ByteBuffer.allocate(5)` creates a new **heap byte buffer** with capacity 5. Bytes start initialized to 0. Initial state: `position=0`, `limit=capacity`, `mark` undefined.

Essential points:

- `allocate` creates new backing storage. Creating two buffers via two separate `allocate` calls does not make them share a backing array merely because they have the same capacity.
- A heap `ByteBuffer` created with `allocate` has an underlying `byte[]` accessible via `array()`, and normally `arrayOffset() == 0` for the initial buffer.
- `buffer.array()` returns a **reference to the backing array**, **not a copy**. If you hand that array to other code, you open up data sharing and external mutations outside the buffer.
- A negative capacity throws `IllegalArgumentException`. Very large capacities can cause `OutOfMemoryError`, so allocation should not be assumed to always succeed.

Example of two independently allocated buffers:

```java
ByteBuffer first = ByteBuffer.allocate(2);
ByteBuffer second = ByteBuffer.allocate(2);

first.put(0, (byte) 7);

System.out.println(first.get(0));  // 7
System.out.println(second.get(0)); // 0
```

Here `first` and `second` have distinct storage. Conversely, a variable `byte[] alias = first.array()` accesses `first`'s exact storage; that is reference sharing, even though the original buffer was created with `allocate`.

### 3.1. `allocateDirect` Is a Distinct Case, Not Equivalent to `allocate`

`ByteBuffer.allocateDirect(n)` requests a direct byte buffer. Direct buffers often help perform certain native I/O operations with fewer intermediate copies, though allocation/management overhead differs from heap buffers and is not faster by default for every workload.

```java
ByteBuffer heap = ByteBuffer.allocate(8);
ByteBuffer direct = ByteBuffer.allocateDirect(8);

System.out.println(heap.isDirect());   // false
System.out.println(direct.isDirect()); // true
System.out.println(heap.hasArray());   // true
System.out.println(direct.hasArray()); // false
```

The snippet above can go inside `main` with `ByteBuffer` imported. A direct buffer does not expose a backing `byte[]` via `array()` the way a heap buffer does. `hasArray()==false` is also **not sufficient to conclude a buffer is direct**, because a read-only heap buffer also withholds array access. Direct vs. heap concerns storage placement; shared vs. independent concerns relationships among views and data sources.

## 4. `ByteBuffer.wrap(byte[])` — Sharing the Exact Existing Array

Given a byte array:

```java
byte[] source = {10, 20, 30};
ByteBuffer buffer = ByteBuffer.wrap(source);

buffer.put(1, (byte) 99);
System.out.println(source[1]); // 99

source[2] = 77;
System.out.println(buffer.get(2)); // 77
```

This is an illustrative snippet for `main` with `ByteBuffer` imported. There is no hidden copy in `wrap(source)`; both `buffer` and `source` view the exact same memory elements.

Initial state after calling `wrap(source)`:

```text
position = 0
limit    = source.length
capacity = source.length
backing array = source
arrayOffset = 0
```

`wrap` is especially useful when an API produces or receives `byte[]` while the NIO processing layer needs `get`, `put`, `flip`, `slice`, binary decoding, or channel integration. The "zero-copy" benefit avoids copying, yet requires the author to understand **who owns the array and who has permission to mutate it**.

### 4.1. Why `wrap` Is Not an "Immutable Conversion"

`ByteBuffer.wrap(source)` retains a reference to `source`. Even if the caller no longer holds the `source` variable, other code that already received the array reference can still mutate the data. Conversely, when the buffer is passed to someone else, they can mutate the original array through the buffer if it remains writable.

To obtain an **independent copy of the contents**, copy explicitly, for instance:

```java
byte[] original = {1, 2, 3};
ByteBuffer shared = ByteBuffer.wrap(original);
ByteBuffer detached = ByteBuffer.wrap(original.clone());

original[0] = 9;
System.out.println(shared.get(0));   // 9
System.out.println(detached.get(0)); // 1
```

`clone()` creates a separate byte array before `wrap`. Note that for complex data structures, `clone` can be a shallow copy; however, `byte[]` holds primitive values so it produces an independent byte copy.

## 5. Prominent Trap: `wrap(array, offset, length)` Does Not Create a Buffer with capacity = length

Consider the array:

```java
byte[] bytes = {10, 20, 30, 40, 50, 60};
ByteBuffer view = ByteBuffer.wrap(bytes, 1, 3);
```

Many assume `view` has `capacity=3`, `position=0`, and `limit=3`. That is a **wrong guess**.

Per the `ByteBuffer.wrap(array, offset, length)` contract:

```text
capacity = array.length           = 6
position = offset                 = 1
limit    = offset + length        = 4
mark     = undefined
arrayOffset = 0 (on the buffer wrapping the whole original array)
```

The `offset` and `length` arguments define the **array subrange ready for initial relative operations**, without shrinking the buffer's capacity to `length`. Thus:

```java
System.out.println(view.capacity()); // 6
System.out.println(view.position()); // 1
System.out.println(view.limit());    // 4
System.out.println(view.remaining()); // 3

System.out.println(view.get());      // 20 (position increments to 2)
System.out.println(view.get(0));     // 10 (absolute get, position unchanged)
```

This snippet continues from the `view` declaration. `get(0)` can access elements **before** `offset`, as long as the index is below `limit`; `offset` is not a memory-isolation wall. After `clear()`, this buffer can operate up to capacity 6; `clear()` does not copy or restrict back to the 3-byte range.

### 5.1. Wanting Zero-Based Indexing for the Selected Range: `slice()`

```java
byte[] bytes = {10, 20, 30, 40, 50, 60};
ByteBuffer window = ByteBuffer.wrap(bytes, 1, 3).slice();
```

Because the base buffer has `position=1` and `limit=4`, `slice()` creates a new buffer viewing only the **remaining region** of three bytes `{20, 30, 40}`. It has:

```text
position    = 0
limit       = 3
capacity    = 3
arrayOffset = 1 (for this heap buffer)
```

`window`'s indices are 0..2, yet the bytes are **still shared** with `bytes`:

```java
window.put(0, (byte) 99);
System.out.println(bytes[1]); // 99
```

You can picture the mapping as:

```text
window index:       0     1     2
                    |     |     |
underlying bytes:  [10]  [99]  [30]  [40]  [50]  [60]
array index:         0     1     2     3     4     5
                          ^-----------^
                     window's backing region
```

To locate the underlying index of an accessible array-backed buffer's element, use `buffer.arrayOffset() + bufferIndex`. **Never assume `buffer.array()[0]` is always the byte at `buffer.get(0)`.** That holds only for initial buffers with `arrayOffset() == 0`.

### 5.2. `slice(index, length)` — Selecting a Range by Explicit Index

In modern Java versions (available in Java 17), you can call:

```java
ByteBuffer original = ByteBuffer.wrap(new byte[]{10, 20, 30, 40, 50});
ByteBuffer part = original.slice(1, 3);

System.out.println(part.capacity()); // 3
System.out.println(part.position()); // 0
System.out.println(part.get(0));     // 20
```

The index `1` here is an index **of the `original` buffer**, not an arbitrary array constructor offset. `slice(index, length)` creates a view covering bytes from `index` to `index + length - 1`, bounded by `original`'s `limit` and validated per the API contract. The sliced buffer also shares storage and carries its own cursor state.

## 6. `duplicate`, `slice`, `asReadOnlyBuffer`: Different Cursors, Same Data

From a `ByteBuffer base`, you can create views:

| API | Visible Data Region | Initial `position` / `limit` | Shares Bytes with Base? |
|---|---|---|---|
| `base.duplicate()` | Entire region of the base buffer | Copies initial `position`, `limit`, `mark` values | Yes |
| `base.slice()` | Region from `base.position()` to `base.limit()` | `position=0`, `limit=capacity=base.remaining()` | Yes |
| `base.slice(index, length)` | Specified subrange of base | `position=0`, `limit=capacity=length` | Yes |
| `base.asReadOnlyBuffer()` | Same region as base, but writes through this view are forbidden | Copies initial cursor state values | Yes |
| `ByteBuffer.wrap(base.array().clone())` | Copied array (only valid when `array()` is accessible) | `position=0`, `limit=capacity=copied array length` | No |

**Rule:** `duplicate` and `slice` do not copy bytes. `asReadOnlyBuffer` does not copy bytes either; "read-only" only blocks **writes through that view**, and does not create an immutable snapshot isolated from mutations via other views.

### 6.1. Independent Cursors

```java
ByteBuffer original = ByteBuffer.wrap(new byte[]{5, 6, 7, 8});
ByteBuffer other = original.duplicate();

original.position(2);
other.position(1);

System.out.println(original.get()); // 7, original position becomes 3
System.out.println(other.get());    // 6, other position becomes 2
```

Both views observe the same underlying bytes without sharing the `position` field. Creating a duplicate copies initial state; **afterward**, cursors move independently. Likewise, changing `limit` or `mark` on one view does not mutate the other view's state.

### 6.2. Non-Independent Data

```java
byte[] bytes = {5, 6, 7};
ByteBuffer a = ByteBuffer.wrap(bytes);
ByteBuffer b = a.duplicate();

b.put(1, (byte) 99);
System.out.println(a.get(1)); // 99
System.out.println(bytes[1]); // 99
```

Even though `a.position()` and `b.position()` are separate, a write through `b` changes the byte seen by both `a` and `bytes`.

### 6.3. A Read-Only View Is Not a Snapshot

```java
ByteBuffer writable = ByteBuffer.wrap(new byte[]{1, 2, 3});
ByteBuffer readOnly = writable.asReadOnlyBuffer();

writable.put(0, (byte) 9);
System.out.println(readOnly.get(0)); // 9

// readOnly.put(0, (byte) 5) would throw ReadOnlyBufferException.
```

The read-only view sees changes from the writable alias. `readOnly.isReadOnly()` is `true`; `readOnly.array()` does not permit access to a writable backing array. A buffer derived directly from a read-only view does not suddenly become writable; subsequent views inherit the read-only restriction.

**If you need stable data**, you must copy the bytes into separate storage and control write access to that copy. Putting a "read-only" label on one view does not eliminate other writable aliases.

## 7. Compilable and Runnable Java 17+ Example

The following example combines `allocate`, `wrap(offset, length)`, `slice`, `duplicate`, `asReadOnlyBuffer`, and an **independent copy**, printing exact numbers for positions and contents.

**File:** `BufferSharingDemo.java`

```java
import java.nio.ByteBuffer;
import java.nio.ReadOnlyBufferException;
import java.util.Arrays;

public class BufferSharingDemo {
    public static void main(String[] args) {
        ByteBuffer allocated = ByteBuffer.allocate(4);
        System.out.printf(
                "allocate: pos=%d limit=%d capacity=%d%n",
                allocated.position(), allocated.limit(), allocated.capacity());

        byte[] bytes = {10, 20, 30, 40, 50, 60};
        ByteBuffer wrapped = ByteBuffer.wrap(bytes, 1, 3);
        System.out.printf(
                "wrap(offset,length): pos=%d limit=%d capacity=%d%n",
                wrapped.position(), wrapped.limit(), wrapped.capacity());

        wrapped.put(2, (byte) 99);
        System.out.println("after wrap.put: " + Arrays.toString(bytes));

        ByteBuffer window = ByteBuffer.wrap(bytes, 1, 3).slice();
        System.out.printf(
                "slice: pos=%d limit=%d capacity=%d arrayOffset=%d%n",
                window.position(), window.limit(), window.capacity(),
                window.arrayOffset());

        window.put(0, (byte) 77);
        ByteBuffer duplicate = window.duplicate();
        duplicate.position(2);
        duplicate.put(1, (byte) 88);

        System.out.println("after views: " + Arrays.toString(bytes));
        System.out.println("positions: window=" + window.position()
                + ", duplicate=" + duplicate.position());

        ByteBuffer readOnly = window.asReadOnlyBuffer();
        System.out.println("read-only: " + readOnly.isReadOnly()
                + ", sees=" + readOnly.get(1));

        try {
            readOnly.put(0, (byte) 1);
        } catch (ReadOnlyBufferException ex) {
            System.out.println("read-only write: ReadOnlyBufferException");
        }

        ByteBuffer independent = ByteBuffer.allocate(window.remaining());
        independent.put(window.duplicate());
        independent.flip();

        window.put(0, (byte) 11);
        System.out.println("copy first=" + independent.get(0)
                + ", source first=" + window.get(0));
    }
}
```

Run with JDK 17+ from the directory containing the source file:

```bash
javac BufferSharingDemo.java
java BufferSharingDemo
```

**Exact expected stdout:**

```text
allocate: pos=0 limit=4 capacity=4
wrap(offset,length): pos=1 limit=4 capacity=6
after wrap.put: [10, 20, 99, 40, 50, 60]
slice: pos=0 limit=3 capacity=3 arrayOffset=1
after views: [10, 77, 88, 40, 50, 60]
positions: window=0, duplicate=2
read-only: true, sees=88
read-only write: ReadOnlyBufferException
copy first=77, source first=11
```

**Why do these results occur?**

1. `allocate(4)` creates a new buffer in write mode with `position=0`, `limit=capacity=4`.
2. `wrap(bytes, 1, 3)` does not shrink the array's capacity; it sets `position=1` and `limit=4`. Absolute `put(2, 99)` writes to `bytes[2]` without changing `position`.
3. `slice()` creates a view over `bytes[1..3]`, hence capacity 3 and `arrayOffset=1`.
4. `window.put(0, 77)` changes `bytes[1]`; `duplicate.put(1, 88)` changes `bytes[2]`, even though `duplicate`'s cursor was set to 2. Neither `put(index, value)` changes `position`.
5. The read-only view forbids writing through it, yet still reads 88 from shared storage.
6. `independent` allocates new storage and copies the three bytes. After `window` changes its first byte from 77 to 11, the copied buffer still holds 77.

The code uses synchronous single-threaded operations for deterministic output, without relying on a scheduler or filesystem.

## 8. `get`, `put`, `flip`, `clear` When Buffers Share an Array

With a regular buffer:

```java
ByteBuffer buffer = ByteBuffer.allocate(4);
buffer.put((byte) 10);
buffer.put((byte) 20);
buffer.flip();

System.out.println(buffer.get()); // 10
System.out.println(buffer.get()); // 20
```

`flip()` sets `limit` to the old `position` and then `position=0` to prepare to read the data just written. If a buffer has multiple views, `flip()` updates only the state of **the view it was called on**, without automatically updating cursors on any other views.

### 8.1. Does `clear()` Truly Erase Data?

No. `clear()` normally sets `position=0`, `limit=capacity`, and discards mark, preparing for overwrites. Old data can remain in backing storage until replaced:

```java
byte[] bytes = {1, 2, 3};
ByteBuffer wrapped = ByteBuffer.wrap(bytes);
wrapped.clear();
System.out.println(Arrays.toString(bytes)); // [1, 2, 3]
```

This illustrative snippet requires importing `java.util.Arrays` and `java.nio.ByteBuffer`. For sensitive data, `clear()` is **not** a secure wipe or memory zeroing mechanism.

### 8.2. When Do `BufferOverflowException` and `BufferUnderflowException` Occur?

A view's `position` and `limit` govern how many elements remain. A relative `put` when no space remains in `remaining()` throws `BufferOverflowException`; a relative `get` when no elements remain throws `BufferUnderflowException`. Never assume that because space remains in the **original array**, the buffer can always read/write further: a view enforces its own limit.

For example, with `ByteBuffer.wrap(bytes, 1, 3)`, only three bytes are initially available for relative operations; after three `get()` calls, a fourth `get()` will underflow. Changing `limit` or using absolute access is another option, provided it matches business rules and bounds checks.

### 8.3. `compact()` Can Affect Other Views Because It Moves Bytes

`compact()` copies unread elements to the start of **the current buffer's storage region**, sets `position` for subsequent writes, and can alter backing-array contents observed by other views. Thus, `compact()` is not merely a cursor update like `clear()` or `flip()`; with shared storage, it is an operation that mutates data.

## 9. Shared Data Regions and Backing-Array Access

For a **writable heap `ByteBuffer`**, you can usually do:

```java
ByteBuffer heap = ByteBuffer.allocate(6);
byte[] backing = heap.array();
int offset = heap.arrayOffset();
```

`backing` is the exact same byte array, not a copy. `offset` must be added to indices when the buffer is a slice whose storage starts partway into the array.

There are three cases to distinguish:

| Buffer | `hasArray()` | `array()` |
|---|---|---|
| Initial writable heap `ByteBuffer.allocate(...)` | `true` | Returns the exact backing `byte[]` |
| Writable heap slice/duplicate with accessible array | `true` | Returns the same backing array; `arrayOffset` may differ |
| Read-only view of a heap buffer | `false` | Throws `ReadOnlyBufferException` |
| Direct `ByteBuffer` | `false` | Throws `UnsupportedOperationException` |

`hasArray()` only tells you whether an **accessible backing array per contract** exists; it does not mean the memory is "unshared." A read-only buffer can share bytes with another writable view; a direct buffer can share storage via direct slices even without an accessible `byte[]`.

When writing general-purpose libraries accepting a `ByteBuffer`, the solid approach is using `get`/`put`/`slice`/`duplicate` and optimizing to `array()` only when `hasArray()` applies, while properly handling `position`, `remaining`, `arrayOffset`, and read-only constraints.

### 9.1. Converting a ByteBuffer to a New Array Without Moving the Caller's Cursor

Example method copying **only the remaining region**:

```java
import java.nio.ByteBuffer;

public class BufferBytes {
    public static byte[] remainingBytes(ByteBuffer source) {
        ByteBuffer reader = source.duplicate();
        byte[] result = new byte[reader.remaining()];
        reader.get(result);
        return result;
    }
}
```

This is a standalone compilable helper class (`BufferBytes.java`), with no `main` and no stdout. `duplicate()` shares the same storage with a separate cursor; `get(result)` reads data into a **new** array, so `source.position()` is not altered. Note that `source` could be mutated concurrently via another alias, causing the copied bytes to reflect an intermediate state; this API does not provide an atomic snapshot under concurrent writes.

**Why not use `source.array()`?** Because it can throw on direct/read-only buffers, returns the entire large backing array rather than just `remaining`, and can expose data outside the range the caller intended to make readable.

## 10. `CharBuffer.wrap` and Other Buffer Types

The idea of "wrapping existing storage" does not apply only to `ByteBuffer`:

```java
char[] letters = {'J', 'a', 'v', 'a'};
CharBuffer characters = CharBuffer.wrap(letters);

characters.put(0, 'K');
System.out.println(letters[0]); // K
```

Illustrative snippet with `import java.nio.CharBuffer;`. `CharBuffer.wrap(char[])` shares the `char[]` array. For `IntBuffer`, `ShortBuffer`, `LongBuffer`, `FloatBuffer`, and `DoubleBuffer`, wrapping the corresponding primitive array follows the exact same shared-backing-storage model.

**Important exception when wrapping a `CharSequence`:**

```java
CharBuffer text = CharBuffer.wrap("Java");
System.out.println(text.isReadOnly()); // true, for String
```

`CharBuffer.wrap(CharSequence)` creates a char buffer that reads from the sequence; it is not like wrapping a mutable `char[]`. With an immutable `String`, the view does not permit mutating contents the way an array does; attempting `put` on a char buffer created by this overload throws `ReadOnlyBufferException`. With a mutable `CharSequence`, review the sequence and provider contracts before reasoning about the stability of observed data.

Another buffer type can also be a **typed view** over a byte buffer, such as `byteBuffer.asIntBuffer()`: it provides a view of `int` elements over the same byte storage (following the corresponding byte order and alignment rules). Modifying bytes through this view changes the data visible in other views over the same region. Do not assume all buffers share the same element-based capacity: `IntBuffer` measures capacity in `int` values, not bytes.

## 11. Design and Concurrency Risks

### 11.1. Sharing Backing Storage Means Sharing Mutability

Suppose an API accepts an array and keeps a reference:

```java
static ByteBuffer parseLater(byte[] packet) {
    return ByteBuffer.wrap(packet);
}
```

If the caller modifies `packet` after passing it, the buffer used later by the parser will observe the new data. Whenever a parser wants to "freeze input" to verify checksums, signatures, protocol frames, or cache entries, it must establish clear **array ownership** and consider explicit copying. Never rely solely on a `ByteBuffer` parameter type to assume exclusive ownership.

Common strategies:

- **Intentional sharing:** document clearly that callers must not mutate data while the parser uses the buffer, avoiding copies at the cost of lifecycle coordination.
- **Private copy:** `ByteBuffer.wrap(array.clone())` or copying `remaining` into a fresh array; increases memory/copy cost while eliminating input aliasing.
- **Providing only a read-only view:** restricts writes by the recipient, though it does not prevent the owner or another writable alias from modifying backing storage.
- **Streaming data:** if random access is unnecessary, consider streams/channels and source lifecycle rules; not every API needs a shared backing array.

### 11.2. Buffers Are Not Thread-Safe by Default

A mutable `ByteBuffer` has mutable cursors and storage. Using the same instance or views sharing backing storage from multiple threads without synchronization can cause data races, inconsistent observed state, or broken read logic.

Using `duplicate()` creates independent cursors that isolate read/write position state, yet **does not make shared bytes thread-safe**. `asReadOnlyBuffer()` blocks writes through one alias while another alias can still mutate data concurrently. When concurrent tasks are involved, establish ownership/handoff, synchronization, or separate data structures and coordination compliant with the Java Memory Model.

### 11.3. Reading Stable Data Requires More Than Setting Limit

`position` and `limit` govern `get`/`put` API calls on a view, **not security boundaries over backing storage**. Another view or the original array can still reach elements outside this view's bounded region. If private data lies before or after a sliced region, never hand the whole array via `array()` to untrusted components; pass an exact copy of the permitted range.

### 11.4. Lifetime of Direct Buffers and Mapped Buffers

For direct buffers, keep native memory allocation costs and JVM-managed lifetimes in mind; do not accumulate direct allocations unboundedly. For a file-backed `MappedByteBuffer`, operations through views can interact with mapped file contents, and syncing/durability follow their own contracts. These cases still illustrate that a "buffer" is a data-access model, while data location and lifecycle depend on how the buffer was created.

## 12. Common Mistakes and Fixes

1. **Thinking `wrap(array)` makes a copy.** In reality, the buffer shares the array. If independence is needed, use `array.clone()` or copy explicitly.
2. **Thinking `allocate` returns a buffer without a backing array.** Heap buffers from `ByteBuffer.allocate` have a backing array; `allocateDirect` is what uses direct storage.
3. **Thinking `wrap(array, offset, length)` sets capacity = length.** It keeps capacity equal to `array.length` and sets `position`/`limit` accordingly. For a 0-based window, follow with `slice()`.
4. **Forgetting `arrayOffset` on a slice.** `buffer.get(0)` can point to `backing[arrayOffset]`, not `backing[0]`.
5. **Thinking `slice` and `duplicate` copy bytes.** They create views sharing storage; cursors are independent while contents are linked.
6. **Thinking `asReadOnlyBuffer` freezes data.** A read-only view does not stop another writer from mutating backing bytes.
7. **Assuming `hasArray() == false` means direct.** A read-only heap buffer also withholds array access; use `isDirect()` when asking whether storage is direct.
8. **Confusing `clear()` with zeroing/resetting data.** It updates cursor state, without overwriting the array.
9. **Accessing `array()` without considering bounds.** It returns the entire backing array, which may be larger than the `position..limit` range intended for export.
10. **Calling relative `put` without checking `remaining()`.** Hitting `limit` throws overflow even when the underlying array still has indices outside the view.
11. **Confusing absolute access with relative access.** `put(index, value)` does not increment `position`; `put(value)` does.
12. **Assuming shared backing is safe across threads.** Synchronization and ownership rules are required; separate cursors do not prevent data races.
13. **Thinking storage is shared only via `wrap`.** `duplicate`, `slice`, and `array()` from `allocate` also create sharing paths.
14. **Using `wrap(CharSequence)` like `wrap(char[])` for writing.** The `CharSequence` overload has read-only semantics depending on the sequence; choose the right overload.
15. **Equating `capacity` with valid readable bytes.** After writing, call `flip()` or set `limit` appropriately; bytes sitting in the backing array do not automatically belong to the intended readable region.

## 13. Quick Check on Predicting Shared Storage

**Question 1.** Given:

```java
byte[] a = {1, 2, 3, 4};
ByteBuffer b = ByteBuffer.wrap(a, 1, 2);
```

What are `b.capacity()`, `b.position()`, and `b.limit()`?  
**Answer:** `4`, `1`, `3`. `offset` and `length` only set the initial cursor/range.

**Question 2.** If `ByteBuffer c = b.slice()` is called immediately afterward, what are `c.capacity()` and `c.arrayOffset()`?  
**Answer:** `2` and `1` for this array-backed buffer; `c.position()=0` and `c.limit()=2`. `c.get(0)` corresponds to `a[1]`.

**Question 3.** Does `c.put(0, (byte) 8)` mutate `a`?  
**Yes.** `a[1]` becomes 8. The slice still shares backing storage.

**Question 4.** After `ByteBuffer d = c.duplicate()`, does calling `d.position(1)` change `c.position()`?  
**No.** Cursors are independent; storage is shared.

**Question 5.** Does `c.asReadOnlyBuffer()` prevent modifying data via `a[1]=9`?  
**No.** It only blocks writes through that read-only view; the view itself will observe the value 9.

**Question 6.** Does `ByteBuffer.allocate(4).array()` create a new copy when reading `array()`?  
**No.** That is the buffer's own backing array.

**Question 7.** To create an exact copy of the `remaining` portion of a buffer that may be direct or read-only, what should you use?  
**Hint:** `source.duplicate()` so the caller's cursor stays unchanged, allocate a `byte[]` of size `duplicate.remaining()`, and call `duplicate.get(bytes)`.

## 14. Takeaways and References

**Rule to memorize:** `allocate` creates new storage, `wrap` uses existing storage; `slice`/`duplicate` create views sharing storage while managing separate `position`/`limit`; `asReadOnlyBuffer` blocks writes through that view without creating a snapshot. For `wrap(array, offset, length)`, remember `capacity=array.length`, and if you want a truly 0-based segment, follow with `slice()`. When complete independence is required, copy the data intentionally.

Official Java SE 21 Documentation:

- `ByteBuffer` — `allocate`, `allocateDirect`, `wrap`, `slice`, `duplicate`, `asReadOnlyBuffer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html
- `Buffer` — position, limit, capacity, mark, `flip`, `clear`, `rewind`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/Buffer.html
- `CharBuffer` — wrapping arrays and CharSequence: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/CharBuffer.html
- `ReadOnlyBufferException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ReadOnlyBufferException.html
