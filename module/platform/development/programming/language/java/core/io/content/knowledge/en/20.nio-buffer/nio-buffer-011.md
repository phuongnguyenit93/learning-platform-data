# Java NIO Buffer: slice, duplicate, read-only buffer, and Independent Cursor State

## 1. Lesson Goals

When processing binary data with Java NIO, a `ByteBuffer` is not merely a byte array. It consists of two parts you must keep distinct:

- **Content:** the memory region holding the bytes.
- **Per-object buffer state:** `capacity`, `limit`, `position`, `mark`, and properties such as read-only, direct/heap, and byte order.

Three key methods:

- `slice()` creates a **sub-window** starting from the current `position` up to `limit`.
- `duplicate()` creates **another view over the same byte region**, initially having the same `capacity`, `limit`, `position`, and `mark`.
- `asReadOnlyBuffer()` creates a **read-only view** over the same byte region, initially having the same position/limit state.

**Core point:** these views **share data**, yet **do not share `position`, `limit`, and `mark` variables**. Changing view A's `position` does not change view B's `position`. Conversely, modifying a byte in shared memory through a writable view causes other views looking at that byte to see the new value.

This mechanism differs from copying data: creating a view normally does not copy the entire contents. Thus views are great for passing a buffer segment to a processing function without allocating a new byte array, while requiring careful management of write permissions and memory lifecycle.

## 2. Reviewing capacity, limit, position, and mark

Every `Buffer` has indices obeying the invariant:

```text
0 <= position <= limit <= capacity
```

- `capacity`: maximum capacity of **that view**. Does not change during the view's lifetime.
- `limit`: upper bound that normal read/write operations may not cross (exclusive of the element at `limit`).
- `position`: index of the next element to be read/written by relative operations (`get()`, `put(...)`).
- `mark`: optional bookmark recorded by `mark()` at the current `position` for `reset()` to return to. Mark may be unset (undefined).
- `remaining()`: equal to `limit - position`.
- `hasRemaining()`: true if `position < limit`.

Common state transitions:

| Call | Effect |
|---|---|
| `get()` / `put(byte)` | Reads/writes at current `position` then increments `position` by 1 |
| `get(index)` / `put(index, value)` | Absolute access by index within the view; **does not change `position`** |
| `position(n)` | Sets `position`; mark is discarded if greater than the new `position` |
| `limit(n)` | Sets `limit`; if `position` exceeds `limit`, `position` is clamped to `limit`; marks beyond `limit` are discarded |
| `mark()` | Saves current `position` as mark |
| `reset()` | Restores `position` to mark; throws `InvalidMarkException` if mark is unset/invalidated |
| `flip()` | `limit = old position`, `position = 0`, discards mark; typically prepares to read newly written data |
| `clear()` | `position = 0`, `limit = capacity`, discards mark; **does not erase physical bytes** |
| `rewind()` | `position = 0`, keeps `limit`, discards mark |
| `compact()` | Shifts remaining bytes to the front of the view, sets `position` after the shifted portion, `limit = capacity`; **modifies contents** and cannot be used on a read-only buffer |

**Note:** `clear()` is a state operation; its name does not mean zeroing all bytes. A view has its own capacity, so calling `clear()` on a `slice` does not expand the view outside the slice region.

State example for an 8-byte buffer:

```text
ByteBuffer capacity=8, position=2, limit=6

Index:      0   1   2   3   4   5   6   7
Content:  [10, 11, 12, 13, 14, 15, 16, 17]
                   ^               ^
                position          limit
Remaining region: indices [2, 6) = 2, 3, 4, 5.
```

The indices above are **local indices of each view**, not necessarily positions in the original array or in a file.

## 3. `slice()`: Sub-View with Indexing Restarting at 0

`slice()` on `ByteBuffer` creates a view covering the `[position, limit)` region at the **moment of the call**.

If the original buffer has capacity 8, position 2, limit 6:

```text
Original index:  0  1  2  3  4  5  6  7
Original bytes: 10 11 12 13 14 15 16 17
                      |-----------|
                      Region [2,6)

Slice index:           0  1  2  3
Slice bytes:          12 13 14 15

Original: capacity=8, position=2, limit=6
Slice:    capacity=4, position=0, limit=4, mark=undefined
```

Key implications:

1. The slice view looks at the **exact same four bytes** at original indices 2–5. `slice.get(0)` is the same byte that `original.get(2)` sees.
2. `slice.put(0, value)` (if writable) updates the byte at original index 2; both sides see the new value.
3. Changing `slice.position(...)`, `slice.limit(...)`, or `slice.mark()` only updates **slice** state. The original's position remains unchanged.
4. Changing `original.position`/`limit` **after creation** does not change the size or memory region the slice already represents.
5. The slice has its capacity bounded by the selected segment. It cannot access bytes outside that segment using normal index APIs.
6. If original is read-only, the slice is also read-only; if original is direct, the slice is also direct.

Illustrative snippet (not a standalone program):

```java
ByteBuffer original = ByteBuffer.wrap(
        new byte[]{10, 11, 12, 13, 14, 15, 16, 17});

original.position(2);
original.limit(6);

ByteBuffer slice = original.slice();

System.out.println(slice.capacity()); // 4
System.out.println(slice.get(0));      // 12

slice.put(1, (byte) 99);
System.out.println(original.get(3));   // 99
System.out.println(original.position()); // 2
```

Note: `ByteBuffer.slice(int index, int length)` also lets you create a view of a specific segment by **absolute index in the target buffer**, without changing `position` beforehand. This overload has existed since Java 13, so it is available in Java 17:

```java
ByteBuffer selected = original.slice(2, 3);
// selected contains original at indices 2, 3, 4.
// selected.position() == 0, selected.limit() == selected.capacity() == 3.
```

Here `index` is an index in the current `original`, **not an offset added onto `original.position()`**. It requires `0 <= index` and `0 <= length <= original.limit() - index`; violations throw `IndexOutOfBoundsException`.

### Nested Slice Layers

If `first = root.slice()` and then `second = first.slice()`, every index of `second` is measured from `first`'s position at the time `second` was created. The view layers share the corresponding byte region while maintaining separate positions. When translating indices for debugging, record each layer's offset:

```text
root absolute index = rootOffsetOfFirst + firstOffsetOfSecond + secondIndex
```

This is a formula for computing indices in a slice tree over a **known backing memory region**, not an automatic `ByteBuffer` API. When building multi-layer parsers, pass explicit offsets and lengths to avoid confusion.

## 4. `duplicate()`: Full-Region View with Independent Cursor

`duplicate()` creates a new buffer pointing to the **same underlying data region** as the source buffer. For `ByteBuffer`, the new view initially has:

- `capacity` **equal** to source.
- `limit` **equal** to source.
- `position` **equal** to source.
- `mark` **copied by value** from source if defined; afterward, each view's mark operates independently.
- Direct/heap and read-only attributes are preserved accordingly.
- **Data remains shared**, with no separate copy of bytes.

The big difference from `slice` is that `duplicate` retains the **same indexing/capacity** as the source buffer. It is well suited when two components need independent traversal cursors referencing the same set of bytes.

```java
ByteBuffer original = ByteBuffer.wrap(new byte[]{10, 20, 30, 40, 50});
original.position(1);
original.limit(4);
original.mark();

ByteBuffer duplicate = original.duplicate();
duplicate.position(3);  // original stays at position=1

duplicate.put(2, (byte) 99);  // absolute put: does not change duplicate position
System.out.println(original.get(2));  // 99
System.out.println(original.position()); // 1

duplicate.reset(); // Mark was copied when duplicate() ran: returns to position=1.
```

This snippet illustrates Java with `import java.nio.ByteBuffer`. Since `duplicate` and `original` share bytes, changing `limit` on `duplicate` does not forbid `original` from accessing the corresponding data region if `original` still has a valid range.

**Warning about `clear()` on duplicate:** `duplicate` has the same capacity as `original`. If `original` had `limit` set lower than `capacity` to denote valid data bytes, calling `duplicate.clear()` expands **`duplicate`'s** limit up to `capacity`. That does not copy or "create" new valid data; it can expose stale bytes in the buffer if the program loses track of logical bounds.

## 5. `asReadOnlyBuffer()`: Blocks Writes Through the View, Does Not Freeze Data

`asReadOnlyBuffer()` creates a **read-only view** over the same memory, initially sharing the source's capacity/position/limit/mark (like `duplicate`). The view's `isReadOnly()` method returns `true`.

- Allows `get()`, `get(index)`, and changing `position`, `limit`, `mark`, `reset`, `flip`, `clear`, `rewind`. Read-only does **not** mean cursor state is locked.
- Forbids operations that mutate contents through this view, such as `put(...)` or `compact()`: they throw `ReadOnlyBufferException`.
- If the source or another writable view updates the shared bytes, the read-only view **still sees the new contents**. Read-only protects **the access path through that view**, without creating an immutable snapshot.
- Creating `duplicate()` or `slice()` from a read-only view still yields a read-only view; they cannot be used to regain write access.
- A read-only heap `ByteBuffer` does not directly expose the backing array via `array()`; `hasArray()` returns `false`. Likewise, direct buffers generally have no accessible `byte[]`.

Example:

```java
ByteBuffer writable = ByteBuffer.wrap(new byte[]{1, 2, 3});
ByteBuffer readOnly = writable.asReadOnlyBuffer();

readOnly.position(1);      // Valid: changes only the view's cursor.
writable.put(1, (byte) 9); // Valid: source still has write permission.

System.out.println(readOnly.get(1));  // 9: sees shared modification
System.out.println(readOnly.isReadOnly()); // true

// readOnly.put(1, (byte) 8); // Throws ReadOnlyBufferException.
```

If **truly immutable data** is needed, you must create a **detached copy** and control every reference to that copy. For example: allocate `ByteBuffer.allocate(source.remaining())`, transfer data from a `duplicate` view, `flip()`, and then distribute only a read-only view of that copy without exposing the writable `copy` buffer.

> **Read-only view ≠ immutable storage ≠ thread-safe storage.** Read-only only prevents writes through that specific view object.

## 6. Comparison Table of State Upon Creation

Assume `src` is a writable `ByteBuffer` with capacity=8, position=2, limit=6, and mark set at position=2.

| New View | Shares Bytes with src? | New Capacity | New Position | New Limit | New Mark | Writable via View? |
|---|---|---:|---:|---:|---|---|
| `src.slice()` | Yes, region [2,6) | 4 | 0 | 4 | Undefined | Yes, if src is writable |
| `src.slice(1,3)` | Yes, region [1,4) | 3 | 0 | 3 | Undefined | Yes, if src is writable |
| `src.duplicate()` | Yes, entire src region | 8 | 2 | 6 | Copies mark 2 | Yes, if src is writable |
| `src.asReadOnlyBuffer()` | Yes, entire src region | 8 | 2 | 6 | Copies mark 2 | **No** |
| `ByteBuffer.allocate(8)` | **No** | 8 | 0 | 8 | Undefined | Yes |

Each state column shows the **initial values of the newly created view object**, not shared variables; after creation, each object maintains its own `position`/`limit`/`mark`. When calling `duplicate()` or `asReadOnlyBuffer()` on a buffer that is already read-only, the new view is also read-only.

Calls that mutate `original`'s metadata before creating a view change the **initial state** of views created afterward. Views created earlier keep their own independent states.

## 7. Complete Java 17+ Example: Same Data, Independent Cursors

The example below demonstrates four objects: `root`, `slice`, `duplicate`, and `readOnly`. All results are deterministic and independent of filesystem or hardware.

Save as **`BufferViewsDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.ReadOnlyBufferException;

public class BufferViewsDemo {
    public static void main(String[] args) {
        ByteBuffer root = ByteBuffer.wrap(
                new byte[]{10, 11, 12, 13, 14, 15, 16, 17});

        root.position(2);
        root.limit(6);
        root.mark(); // root's mark placed at position=2

        ByteBuffer slice = root.slice();
        ByteBuffer duplicate = root.duplicate();
        ByteBuffer readOnly = root.asReadOnlyBuffer();

        System.out.printf("root: p=%d, l=%d, c=%d%n",
                root.position(), root.limit(), root.capacity());
        System.out.printf("slice: p=%d, l=%d, c=%d%n",
                slice.position(), slice.limit(), slice.capacity());
        System.out.printf("duplicate: p=%d, l=%d, c=%d%n",
                duplicate.position(), duplicate.limit(), duplicate.capacity());
        System.out.printf("readOnly: p=%d, l=%d, c=%d%n",
                readOnly.position(), readOnly.limit(), readOnly.capacity());

        slice.position(1);
        duplicate.position(4);
        readOnly.position(3);

        System.out.printf("positions: root=%d, slice=%d, duplicate=%d, readOnly=%d%n",
                root.position(), slice.position(),
                duplicate.position(), readOnly.position());

        slice.put(0, (byte) 99); // slice index 0 -> root index 2
        root.put(3, (byte) 88);  // root index 3 -> slice index 1

        System.out.println("root[2]=" + root.get(2));
        System.out.println("readOnly[2]=" + readOnly.get(2));
        System.out.println("slice[1]=" + slice.get(1));
        System.out.println("readOnly.isReadOnly=" + readOnly.isReadOnly());

        try {
            readOnly.put(2, (byte) 7);
            System.out.println("unreachable");
        } catch (ReadOnlyBufferException ex) {
            System.out.println("write through readOnly: rejected");
        }

        duplicate.reset(); // duplicate copied mark=2 on creation
        root.reset();      // root's own mark is still 2

        System.out.printf("after reset: root=%d, duplicate=%d, slice=%d%n",
                root.position(), duplicate.position(), slice.position());
    }
}
```

Run:

```bash
javac BufferViewsDemo.java
java BufferViewsDemo
```

**Exact Stdout:**

```text
root: p=2, l=6, c=8
slice: p=0, l=4, c=4
duplicate: p=2, l=6, c=8
readOnly: p=2, l=6, c=8
positions: root=2, slice=1, duplicate=4, readOnly=3
root[2]=99
readOnly[2]=99
slice[1]=88
readOnly.isReadOnly=true
write through readOnly: rejected
after reset: root=2, duplicate=2, slice=1
```

Walkthrough:

1. `root.slice()` selects root indices 2–5; seen from `slice`, that range has indices 0–3.
2. `duplicate` and `readOnly` were created when `root` was at `position=2, limit=6`; they start with those same position and limit values, without binding to each other afterward.
3. `slice.position(1)`, `duplicate.position(4)`, and `readOnly.position(3)` do not move `root.position()` away from 2.
4. `slice.put(0, 99)` updates root index 2. `readOnly.get(2)` sees 99 even though `readOnly` forbids writing through itself.
5. `root.put(3, 88)` updates the byte corresponding to `slice.get(1)`. Absolute `get(index)`/`put(index, ...)` calls do not change `position`.
6. `readOnly.put(...)` throws `ReadOnlyBufferException`, which is caught; `unreachable` is not printed.
7. `duplicate`'s mark was copied at creation time, so `duplicate.reset()` moves `duplicate` from position 4 back to 2; `root` resets independently to 2; `slice` remains at 1.

## 8. Byte Order Pitfall Specific to ByteBuffer Views

This detail is easy to overlook when buffers hold `short`, `int`, `long`, or `double` rather than only bytes:

**Per the Java 17 API, `ByteBuffer.slice()`, `slice(index, length)`, `duplicate()`, and `asReadOnlyBuffer()` create views whose initial byte order is `BIG_ENDIAN`**, even when the source buffer had selected `LITTLE_ENDIAN`. Never assume a newly created view automatically inherits the source's byte order setting.

Illustrative snippet:

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

ByteBuffer base = ByteBuffer.allocate(8);
base.order(ByteOrder.LITTLE_ENDIAN);

ByteBuffer view = base.duplicate();
System.out.println(base.order()); // LITTLE_ENDIAN
System.out.println(view.order()); // BIG_ENDIAN per Java 17 spec

view.order(base.order());        // Set explicitly when reading the same format.
```

This snippet is **not a standalone program**; `import` statements must sit at the top of a file when placed in a class. Safe habit when working with multi-byte values: explicitly call `view.order(expectedOrder)` right after creating a view; do not treat the default value as an implicit assumption.

Distinct from that, a **typed view** such as `asIntBuffer()` follows its own byte-order and indexing rules: it views bytes as `int`s (four bytes per element) and uses the source's byte order **at the moment the view is created**. When comparing `ByteBuffer` and `IntBuffer`, keep the index unit in mind (bytes vs. integers) and avoid applying one offset formula indiscriminately to both.

## 9. Slicing to Valid Data Rather Than Full Capacity

A common NIO processing pattern is:

1. Write bytes into `ByteBuffer` via `put(...)`; `position` advances by the number of bytes written.
2. `flip()` to set `limit` to the number of valid bytes and `position` to 0.
3. Create views over segments such as header or payload.
4. Pass each view to reader functions; each maintains its own `position`.

Example (illustrative):

```java
ByteBuffer packet = ByteBuffer.allocate(32);
packet.put(new byte[]{1, 2, 3, 4, 5, 6});
packet.flip(); // position=0, limit=6, capacity=32

ByteBuffer header = packet.slice(0, 2);
ByteBuffer payload = packet.slice(2, 4);

// header  holds two bytes [1,2]
// payload holds four bytes [3,4,5,6]
// packet.position() remains 0.
```

These views have capacity equal to their logical region. If a parser reads past `limit`, it gets `BufferUnderflowException` (relative read) or `IndexOutOfBoundsException` (absolute access past limit). Do not rely on catching those exceptions as a substitute for validating packet format; always check protocol lengths before slicing.

If using zero-argument `slice()`:

```java
packet.position(2);
ByteBuffer payload = packet.slice();
// Starts at packet's index 2, up to packet's current limit().
```

Difference: `slice()` relies on **current `position`**, whereas `slice(2, 4)` uses an **explicitly supplied index `2`** without moving `position`. Pick the appropriate overload to minimize side effects on the caller's read cursor.

## 10. Designing Safe Views in APIs

When designing an API that accepts or returns `ByteBuffer`, decide whether the function is allowed to advance the caller's `position`.

### Pattern A: Read-Only Function Preserving Caller's position/limit

```java
static int sumRemainingUnsignedBytes(ByteBuffer source) {
    ByteBuffer cursor = source.duplicate();
    int sum = 0;
    while (cursor.hasRemaining()) {
        sum += Byte.toUnsignedInt(cursor.get());
    }
    return sum;
}
```

The function above is an **illustrative method snippet**; it needs `import java.nio.ByteBuffer` and must reside in a class. It uses `duplicate()` to move a **private** cursor without changing `source.position`/`limit`. It does not prevent another thread from mutating the shared content concurrently; if stable data is required, coordinate ownership or copy.

### Pattern B: Granting Only Read Access to the Recipient

```java
static ByteBuffer payloadView(ByteBuffer packet, int offset, int length) {
    return packet.slice(offset, length).asReadOnlyBuffer();
}
```

This returns a read-only view with local indices `0..length-1`. The recipient cannot write through the returned view, yet if the producer still holds a reference to the source buffer, the producer can still mutate the data. Do not advertise "immutable data" or "snapshot" for this style of API.

### Pattern C: Needing an Independent Snapshot

```java
static ByteBuffer readOnlySnapshot(ByteBuffer source) {
    ByteBuffer cursor = source.duplicate();
    ByteBuffer copy = ByteBuffer.allocate(cursor.remaining());
    copy.put(cursor);
    copy.flip();
    return copy.asReadOnlyBuffer();
}
```

This is an **independent copy** of the `remaining` region at the moment of copying. It allocates corresponding memory while leaving `source`'s position untouched. To truly guard the snapshot across the API boundary, never expose the writable `copy` view anywhere else, and ensure the source is not mutated concurrently during copying if a consistent snapshot is needed.

If the data contains multi-byte primitive types, set `order` explicitly on received/returned views since byte views may default to `BIG_ENDIAN`.

## 11. Concurrency and Memory Lifecycle

**Independent position does not equal thread safety.** Java NIO `Buffer`s are generally not designed for concurrent manipulation by multiple threads on **the same object** without coordination.

Creating a separate `duplicate` per task keeps tasks from **contending over a single `position` field**. However, they still share bytes. If one thread writes to `root` while another reads a read-only view, data races, inconsistent reads, or memory-visibility issues can still occur. A read-only view does not provide locking or snapshot guarantees.

Practical guidelines:

- For multiple threads **only reading immutable data**, each thread can be given its own `duplicate`/`read-only` view for independent cursors, once the data has been safely published.
- If shared memory may be mutated, use proper synchronization, disjoint regions with clear contracts, or copying to isolate data.
- Both direct buffers (`ByteBuffer.allocateDirect`) and heap buffers support `slice`/`duplicate`/`asReadOnlyBuffer`. A view holds a reference to the shared memory region; do not infer exact resource-release timing merely from dropping one reference.
- For buffers backed by memory mapping or externally managed lifecycles, account for file/source changes, syncing, and memory availability. A read-only view does not guarantee the underlying file stays unchanged.

## 12. Common Mistakes and How to Avoid Them

1. **Thinking `slice()` copies data.** Wrong: `slice` shares bytes; writing on one side shows up on the other. To detach data, copy it.
2. **Thinking `duplicate()` shares `position`.** Wrong: it copies initial state, and afterward the cursors are independent.
3. **Thinking a read-only view is a snapshot.** Wrong: anything with write access to the same backing storage can still alter the contents observed by the read-only view.
4. **Confusing `slice.get(0)` with `root.get(0)`.** Wrong: `slice.get(0)` corresponds to **`root.position` when `slice()` was called** (for `slice()`) or the passed `root` index (for `slice(index, length)`).
5. **Adding the offset twice.** `slice(index, length)` already selects the region by the receiver buffer's index; do not add `buffer.position()` a second time.
6. **Failing to check `limit` before calling `slice(index, length)`.** Exceeding `limit` throws `IndexOutOfBoundsException`; larger `capacity` will not save it.
7. **Expecting `clear()` to erase bytes.** Wrong: `clear` only resets `position`/`limit`/`mark`. To scrub sensitive data, follow an explicit overwrite/zeroing policy suited to the memory type and security requirements.
8. **Reading wrong byte order after `duplicate`/`slice`.** On Java 17 `ByteBuffer`s, set `order(...)` explicitly when reading/writing multi-byte primitives.
9. **Calling `array()` on a read-only or direct buffer.** `hasArray()` may be `false`; `array()` may throw `ReadOnlyBufferException` or `UnsupportedOperationException`.
10. **Changing `limit` and assuming other views update too.** Every view has its own `limit`. When applying a new logical boundary across multiple views, manage/update each view explicitly.
11. **Expecting an old mark to survive `flip/clear/rewind`.** Those operations discard the mark of **the buffer they are called on**; a subsequent `reset()` may throw `InvalidMarkException`.
12. **Letting multiple threads read and write shared memory without coordination.** Views have independent cursors, yet **do not isolate contents**.

## 13. Self-Check Questions

**Question 1.** Buffer A has `position=3, limit=9, capacity=12`. Call `B=A.slice()`. What is B's state?  
**Answer:** B has `capacity=limit=6`, `position=0`, and an undefined mark. Byte `B.get(0)` corresponds to byte `A.get(3)`.

**Question 2.** Create `B=A.duplicate()`, then call `B.position(5)`. Does `A.position()` change?  
**Answer:** No. Each buffer keeps its own position even though data is shared.

**Question 3.** `B=A.asReadOnlyBuffer()`. Call `A.put(0, (byte) 7)`—can `B.get(0)` see 7?  
**Answer:** Yes, because contents are shared; B only blocks writes **through B**. Condition: index 0 is within both views' valid limits and no other write intervenes.

**Question 4.** If A has byte order `LITTLE_ENDIAN`, does a newly created `A.slice()` inherit it by default?  
**Answer:** Under the Java 17 `ByteBuffer` contract, the new view starts with `BIG_ENDIAN`. For multi-byte data, call `view.order(A.order())` or set the protocol's byte order.

**Question 5.** You want a parser to advance its own `position` without changing the caller's—what do you choose?  
**Answer:** `duplicate()` if you want the same initial indexing/limit; `slice()` if you want the parser to see only the remaining segment with new indices starting at 0. If writes through the view must be blocked, add `asReadOnlyBuffer()`.

**Question 6.** `slice()` was created at root position 2, limit 6. Later root changes to position 0, limit 8. Does the slice expand to 8 bytes?  
**Answer:** No. The slice keeps capacity 4 and shares the exact region selected when it was created.

## 14. Summary

- `slice`: **same bytes, a sub-region, new position = 0**.
- `duplicate`: **same bytes, entire region, copies initial cursor state**.
- `asReadOnlyBuffer`: **same bytes, forbids writes through the view**, though data can still be modified via another writable view.
- **Position, limit, and mark are independent across views; contents are shared.**
- On Java 17 `ByteBuffer`, **set byte order explicitly** on new views when working with multi-byte primitives.
- Do not use a read-only view as a substitute for an immutable snapshot or multi-thread synchronization.

### API References

- Java SE 17, `ByteBuffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17, `Buffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html
