# ByteBuffer: capacity, position, limit, and remaining bytes

## 1. Understanding the four most important quantities

`java.nio.ByteBuffer` is a byte container with **read/write state**. It is a core tool when working with `SocketChannel`, `FileChannel`, binary protocol handling, decoders, and many Java NIO APIs. A `ByteBuffer` is not just a `byte[]`: it tracks the region of bytes available for the next operation using **capacity**, **position**, **limit**, and **remaining**.

| Property/API | Description | Key takeaway |
|---|---|---|
| `capacity()` | **Total capacity of the buffer** in bytes, fixed over the object's lifetime | Does not change after `flip()`, `clear()`, or `compact()` |
| `position()` | **Index of the next byte** that a relative operation (`get()`/`put()`) will read/write | Usually advances after a successful relative read/write |
| `limit()` | **Exclusive boundary**: relative operations must not go past this position | Can be smaller than capacity |
| `remaining()` | Number of bytes from position to just before limit, i.e., **`limit() - position()`** | Number of bytes still available to read or write in the current state |
| `hasRemaining()` | `remaining() > 0` | Does not indicate whether the socket/network has more bytes available |

**Invariant:** `0 <= position <= limit <= capacity`. If a valid mark is set, `0 <= mark <= position` also holds. All indices in the API are **0-based**, and `limit` is an **exclusive** upper bound.

~~~text
ByteBuffer capacity = 8, position = 2, limit = 5

index:       0    1    2    3    4    5    6    7
           +----+----+----+----+----+----+----+----+
contents:  | A  | B  | C  | D  | E  | ?  | ?  | ?  |
           +----+----+----+----+----+----+----+----+
                      ^              ^              ^
                   position         limit         capacity
remaining = limit - position = 5 - 2 = 3 (C, D, E)
~~~

The `?` marks illustrate the region that is not part of the **actively used data** after `flip()`; it makes no claim about what byte values are in those memory slots. Bytes before `position` may also still exist physically, but they have already been consumed by relative reading conventions.

### "Remaining bytes" depends on the phase

`remaining()` **does not have a single fixed business meaning**:

- When the buffer is being **filled via `put` or `channel.read(buffer)`**: remaining indicates **how much space is still allowed to be filled up to limit**.
- After `flip()`, when the buffer is **having data consumed via `get` or `channel.write(buffer)`**: remaining indicates **how many bytes have not yet been consumed/transferred out** in the current read window.
- `remaining() == 0` means **position == limit**; it does not prove that a TCP connection has closed, that a complete message has been received, or that EOF has been reached.
- In a `ByteBuffer` that has been `clear()`ed, remaining can equal capacity **even when not a single valid byte of data has been read from the socket**.

Java **does not have a "read mode" or "write mode" flag** in `ByteBuffer`; that is simply how the programmer interprets the three indices: position, limit, and capacity.

## 2. Two typical cycles: filling data and consuming data

Initialization:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(8);
~~~

Initial state: `capacity=8, position=0, limit=8, remaining=8`. The array is allocated and initialized with zero bytes, but **this does not mean the buffer holds eight bytes of input from the network**.

### 2.1. Putting five bytes into the buffer

~~~java
buffer.put(new byte[] {'A', 'B', 'C', 'D', 'E'});
~~~

After the relative `put(byte[])` operation: `position=5, limit=8, remaining=3`. Five bytes have been placed at indices 0..4, and three positions remain writable.

~~~text
WRITE/FILL:
index       0   1   2   3   4   5   6   7
            A   B   C   D   E   .   .   .
                                ^           ^
                           position=5    limit=8
~~~

### 2.2. `flip()` to read the bytes just filled

~~~java
buffer.flip();
~~~

`flip()` performs the exact logic:

~~~java
// Describes the state result; not the internal implementation.
int oldPosition = buffer.position(); // 5
buffer.limit(oldPosition);           // limit = 5
buffer.position(0);                  // position = 0
~~~

After `flip`: `capacity=8, position=0, limit=5, remaining=5`. Only the bytes `A B C D E` are within the relative read range; the remaining three bytes outside limit are not exposed as valid data.

`flip()` does not reverse the byte contents and does not send data over the network. It only changes **the state markers**.

### 2.3. Getting two bytes with `get`

~~~java
byte[] firstTwo = new byte[2];
buffer.get(firstTwo); // A, B
~~~

Afterward, `position=2, limit=5, remaining=3`. The remaining region is `C D E`. If you call `buffer.get()` three more times, position will become 5 and remaining will become 0. The next call throws `BufferUnderflowException`; it **does not automatically wait for the socket to send more**.

### 2.4. `compact()` when unprocessed bytes remain

After consuming `A B` with `C D E` still remaining:

~~~java
buffer.compact();
~~~

`compact()` **shifts all bytes from `position` to `limit - 1` to the beginning of the buffer**, and then:

- `position = number of retained bytes = oldRemaining = 3`.
- `limit = capacity = 8`.
- `remaining = 8 - 3 = 5`, which is the space available to continue filling with new data.
- `mark` is discarded.

~~~text
BEFORE compact:              AFTER compact:
[A][B][C][D][E][?][?][?]     [C][D][E][?][?][?][?][?]
       ^        ^                     ^                 ^
    pos=2     lim=5                 pos=3             lim=8
~~~

From here you can `put('F')`, then `flip()` and read `CDEF`. This is useful when **a message does not yet have enough bytes** or when **`SocketChannel.write` only sends a partial chunk**.

**Do not confuse `compact()` with `clear()`:** `compact` **preserves unconsumed bytes**, whereas `clear` only resets the indices and allows overwriting the entire region.

## 3. Distinguishing `flip()`, `clear()`, `rewind()`, and `compact()`

| Method | `position` after call | `limit` after call | Byte contents | When to use |
|---|---:|---:|---|---|
| `flip()` | `0` | Old position | Bytes unchanged | Just finished writing/receiving a batch, preparing to read/send |
| `clear()` | `0` | `capacity` | **Does not erase bytes** | Done with all data that needed to be kept, preparing to overwrite |
| `rewind()` | `0` | **Keeps old limit** | Bytes unchanged | Want to re-read/re-send the portion currently within limit |
| `compact()` | Old `remaining` | `capacity` | Moves **unconsumed** portion to the start | Need to keep leftover data and continue filling |
| `mark()` | Unchanged | Unchanged | Bytes unchanged | Save the current position to return to later |
| `reset()` | Back to previous mark | Unchanged | Bytes unchanged | Return to the marked position |

`flip()`, `clear()`, `rewind()`, and `compact()` all discard any existing mark; calling `reset()` when no valid mark is set throws `InvalidMarkException`.

An easy-to-miss detail: if you call `flip()` on a buffer with `position=0`, it sets `limit=0`; then `remaining()=0`. Therefore, do not call `flip` twice in a row expecting the same data to still be there. If you only need to re-read the data in the current window, use `rewind()`.

### Quick comparison example

Suppose initially `capacity=10, position=4, limit=7`:

| Call on a separate buffer with this initial state | Result |
|---|---|
| `flip()` | `position=0, limit=4, remaining=4` |
| `clear()` | `position=0, limit=10, remaining=10` |
| `rewind()` | `position=0, limit=7, remaining=7` |
| `compact()` | `position=3, limit=10, remaining=7`; keeps bytes at indices 4..6 |

The table assumes **each call is tested independently on a buffer with the same prior state**, rather than calling the four methods sequentially on one object.

## 4. Runnable Java 17+ example: tracking each change

The program does not use the network so that the output is deterministically reproducible. It goes through the cycle write → `flip` → partial read → absolute access → `compact` → further write → `flip` → full read, then demonstrates `rewind`, `clear`, `wrap`, and `slice`.

Create the file **`ByteBufferStateDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

public class ByteBufferStateDemo {
    static void state(String label, ByteBuffer b) {
        System.out.printf("%s cap=%d pos=%d lim=%d rem=%d%n",
                label, b.capacity(), b.position(),
                b.limit(), b.remaining());
    }

    public static void main(String[] args) {
        ByteBuffer b = ByteBuffer.allocate(8);
        state("new", b);
        b.put("ABCDE".getBytes(StandardCharsets.US_ASCII));
        state("put5", b);
        b.flip();
        state("flip", b);

        byte[] firstTwo = new byte[2];
        b.get(firstTwo);
        System.out.println("read=" +
                new String(firstTwo, StandardCharsets.US_ASCII));
        state("get2", b);

        System.out.println("absolute=" + (char) b.get(2));
        state("absolute-get", b);

        b.compact();
        state("compact", b);
        b.put((byte) 'F');
        b.flip();

        byte[] remaining = new byte[b.remaining()];
        b.get(remaining);
        System.out.println("result=" +
                new String(remaining, StandardCharsets.US_ASCII));
        state("consumed", b);

        b.rewind();
        state("rewind", b);
        b.clear();
        state("clear", b);

        byte[] source = {10, 20, 30, 40, 50};
        ByteBuffer view = ByteBuffer.wrap(source, 1, 3);
        state("wrap", view);
        ByteBuffer slice = view.slice();
        state("slice", slice);
        slice.put(0, (byte) 99);
        System.out.println("shared=" + source[1]);
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac --release 17 ByteBufferStateDemo.java
java ByteBufferStateDemo
~~~

**Verified stdout** by compiling with `--release 17` and running on OpenJDK 24:

~~~text
new cap=8 pos=0 lim=8 rem=8
put5 cap=8 pos=5 lim=8 rem=3
flip cap=8 pos=0 lim=5 rem=5
read=AB
get2 cap=8 pos=2 lim=5 rem=3
absolute=C
absolute-get cap=8 pos=2 lim=5 rem=3
compact cap=8 pos=3 lim=8 rem=5
result=CDEF
consumed cap=8 pos=4 lim=4 rem=0
rewind cap=8 pos=0 lim=4 rem=4
clear cap=8 pos=0 lim=8 rem=8
wrap cap=5 pos=1 lim=4 rem=3
slice cap=3 pos=0 lim=3 rem=3
shared=99
~~~

Breaking down the key points:

- `new`: capacity 8, position 0, limit 8. `remaining=8` means **eight bytes can be written**, not that eight valid bytes have been received from the network.
- `put5`: `position` moves from 0 to 5, remaining is 3.
- `flip`: `limit` becomes 5, position returns to 0; remaining now represents the five bytes available to read.
- `get2`: consumes two bytes `AB`; only `CDE` remains in the window.
- `absolute=C`: `get(2)` returns the byte at index 2 **without changing position**; therefore the `absolute-get` line still shows `pos=2`.
- `compact`: the three bytes `CDE` are kept at the start; `pos=3` allows writing `F` immediately at index 3.
- `result=CDEF`: after `flip` and reading everything, `position=limit=4` so remaining is 0, even though capacity is still 8.
- `rewind`: position 0 and limit 4, allowing `CDEF` to be read again.
- `clear`: position 0, limit 8, ready to **overwrite**; clear does not erase the characters CDEF already in memory.
- `wrap`: with an array of length 5 and offset 1, length 3, the state is **capacity=5, position=1, limit=4**, not capacity=3.
- `slice`: the slice from `view`'s remaining region has capacity=3, position=0, limit=3; writing at index 0 sets `source[1]` to 99 because both buffers share the same underlying byte region.

## 5. Formulas and index operations: relative vs. absolute

### 5.1. Exact calculation

For ByteBuffer:

~~~text
remaining = limit - position
hasRemaining = remaining > 0
0 <= position <= limit <= capacity
~~~

`remaining()` indicates the number of **bytes**, because this is a `ByteBuffer`. For `CharBuffer` or `IntBuffer`, remaining is measured in **the number of elements of that respective type**, not bytes by default.

**Do not** use `capacity - position` in place of remaining in all situations. After `flip`, limit is usually smaller than capacity, so `capacity-position` can **include bytes outside the valid window**.

### 5.2. Relative `get()/put()` and absolute `get(index)/put(index, value)`

| API | Position state | Constraint |
|---|---|---|
| `get()` | Advances by 1 if successful | Requires `remaining() >= 1` |
| `put(byte)` | Advances by 1 if successful | Requires `remaining() >= 1`, buffer must be writable |
| `get(byte[] dst)` | Advances by number of bytes read | Requested byte count must not exceed remaining |
| `put(byte[] src)` | Advances by number of bytes written | Requested byte count must not exceed remaining |
| `get(index)` | **Unchanged** | `0 <= index < limit` |
| `put(index, byte)` | **Unchanged** | `0 <= index < limit`, buffer writable |
| `getInt()` / `putInt(int)` | Advances by **4 bytes** | Requires remaining of at least 4 |
| `getInt(index)` / `putInt(index, int)` | **Unchanged** | Four bytes starting from index must lie within limit |

Small example:

~~~java
ByteBuffer b = ByteBuffer.allocate(4);
b.put(new byte[] {10, 20, 30});
b.flip();                          // pos=0, lim=3
byte x = b.get(2);                 // x=30, pos is still 0
byte y = b.get();                  // y=10, pos=1
b.put(1, (byte) 99);               // modifies index 1, pos is still 1
~~~

This is a **snippet**; the state calculations are predictable without needing to create a separate program. `get(index)` must not exceed **limit**, even if that position is still less than capacity. When you need to operate on part of an array and avoid moving position multiple times, you can use the `get/put` overloads with offset and length, but you must manually check both the array bounds **and** remaining.

### 5.3. Exceptions when reading/writing outside the window

| Situation | Common exception | Cause |
|---|---|---|
| `get()` when position == limit | `BufferUnderflowException` | No elements left for relative read |
| `put(...)` when remaining is insufficient | `BufferOverflowException` | Not enough space in the write window |
| `get(index)` with index < 0 or index >= limit | `IndexOutOfBoundsException` | Invalid absolute index |
| `put(...)` on a read-only ByteBuffer | `ReadOnlyBufferException` | Read-only view |
| `reset()` when mark is undefined or has been discarded | `InvalidMarkException` | Invalid mark |
| `position(n)` with n > limit, `limit(n)` with n > capacity | `IllegalArgumentException` | Invariant violation |

`BufferUnderflowException` and `BufferOverflowException` are errors of the **ByteBuffer memory window**, not signals that TCP/UDP has run out of data or that a network connection has dropped packets.

## 6. Manually changing `position` and `limit`, `mark/reset`

You can change the bounds according to the protocol, as long as the markers remain valid:

~~~java
ByteBuffer b = ByteBuffer.allocate(10);
b.limit(6);        // cap=10, pos=0, lim=6, rem=6
b.position(2);     // cap=10, pos=2, lim=6, rem=4
b.mark();          // Sets mark at position 2
b.get();           // position=3
b.reset();         // position returns to 2
~~~

If you lower limit below position, Java automatically **lowers position to the new limit** to preserve the invariant. If you lower position below mark, or lower limit below mark, **the mark is discarded**. If you call `clear/flip/rewind/compact`, the mark is also discarded.

In a parser, `mark` and `reset` are useful when attempting to read a header: if the payload is not yet complete, restore position to the start of the header before calling `compact()` to preserve **the entire incomplete frame**.

**Do not treat `mark` as a permanent checkpoint**: it is just an index within the current buffer, is discarded by many state-changing operations, and does not manage transactions or synchronization across threads.

## 7. `allocate`, `allocateDirect`, `wrap`, `slice`, and `duplicate`

| Creation method | Where data is stored / how it is shared? | Typical initial state |
|---|---|---|
| `ByteBuffer.allocate(n)` | Heap buffer with its own backing `byte[]` | cap=n, pos=0, lim=n |
| `ByteBuffer.allocateDirect(n)` | Direct buffer for more efficient JVM/I/O interaction in some contexts | cap=n, pos=0, lim=n |
| `ByteBuffer.wrap(array)` | **Shares** the given `byte[]` | cap=array.length, pos=0, lim=array.length |
| `ByteBuffer.wrap(array, off, len)` | Shares the entire array, selects window via position/limit | cap=array.length, pos=off, lim=off+len |
| `buffer.slice()` | New window **sharing bytes** of the remaining region | cap=old remaining, pos=0, lim=new cap |
| `buffer.duplicate()` | Another view **sharing data** with the original buffer, but with independent position/limit/mark | Initial position/limit/capacity equal to the original |
| `buffer.asReadOnlyBuffer()` | Read-only view, **shares bytes**, cannot call `put` | Disallows writing through the view |

**Sharing bytes does not mean sharing position/limit indices**. When you change position in a `slice`, the parent buffer's position does not move with it; when you modify **byte contents**, the parent buffer can see that change.

### The `wrap(array, offset, length)` trap

The Java example we ran in section 4:

~~~java
byte[] source = {10, 20, 30, 40, 50};
ByteBuffer view = ByteBuffer.wrap(source, 1, 3);
// capacity=5, position=1, limit=4, remaining=3
ByteBuffer smallView = view.slice();
// capacity=3, position=0, limit=3, remaining=3
~~~

**Common mistake:** thinking `wrap(array, 1, 3)` creates a buffer with capacity 3 and position 0. According to the Javadoc, it keeps **the capacity of the entire array** and uses position/limit to describe the sub-range; `slice()` is what creates a view with **capacity equal to the remaining region** and position 0.

`slice()` **does not copy data**. If you need an independent copy, allocate a separate array/buffer and copy the exact `remaining` region. For direct buffers, `hasArray()` is usually false and `array()` may throw `UnsupportedOperationException`; for read-only heap buffers, `array()` is also not necessarily accessible. Do not assume every ByteBuffer has an accessible `byte[]`.

### When to choose a direct buffer?

Direct buffers can help some I/O operations avoid copying through the heap, especially when reused over a long period. On the flip side, allocating/reclaiming direct buffers has overhead and affects off-heap memory. **There is no rule that "allocateDirect is always faster"**: you need to benchmark on your specific workload, JDK, and operating system. Do not allocate a new direct buffer for every small message without a measured performance reason.

## 8. Connection with `SocketChannel`: partial reads and writes

ByteBuffer is the direct partner of channel APIs. This is why **`flip` and `compact`** are crucial in networking code.

### 8.1. Reading from a channel into a buffer

~~~java
// Illustrative snippet; channel is an open SocketChannel.
ByteBuffer buf = ByteBuffer.allocate(4096); // pos=0, lim=4096
int n = channel.read(buf);                  // places bytes from pos onward
if (n > 0) {
    buf.flip();                             // limit to only the bytes actually received
    while (buf.hasRemaining()) {
        byte oneByte = buf.get();
        // Process the exact received byte, which may be part of a message.
    }
    buf.compact();                          // keep any unprocessed portion
} else if (n == -1) {
    // Reached EOF on the read side; check for any incomplete message.
} else {
    // n == 0: no bytes were transferred in this call.
}
~~~

This is **not a standalone program**. On a **non-blocking** `SocketChannel`, `read` can return 0 because no bytes are ready yet. In both blocking and non-blocking models, `read` can return 0 when the buffer has no remaining space. `-1` indicates end-of-stream; it is **not** a return value of `ByteBuffer.get()`.

To read a message frame, the code must also include protocol framing (length/delimiter), handling of partial bytes, EOF, and timeouts. `n > 0` **does not by itself mean a complete message has been received**, consistent with how a TCP stream works.

### 8.2. Writing a buffer to a channel

~~~java
// Illustrative snippet; channel is a connected SocketChannel.
ByteBuffer outgoing = java.nio.charset.StandardCharsets.UTF_8
        .encode("PING\n"); // Already in a state with data ready to be read out.
while (outgoing.hasRemaining()) {
    int written = channel.write(outgoing);
    if (written == 0) {
        // For a non-blocking channel: wait for OP_WRITE from Selector
        // instead of spinning the CPU in a real loop.
        break;
    }
}
~~~

`channel.write(outgoing)` consumes **at most** `outgoing.remaining()` bytes at the time of the call; it **may write fewer** than that. `ByteBuffer.position` advances by the number of bytes accepted by the channel. If the buffer still `hasRemaining()`, the application must **keep the buffer and continue writing once the channel is writable**, rather than calling `clear` and discarding the remaining bytes. With a non-blocking channel, trying to write once and then `break`ing is a **control-flow illustration**; you need a selector/event loop mechanism to actually complete the send.

This is also where many bugs arise: seeing `channel.write` return a positive number and assuming the entire buffer has gone out over the socket. The returned number is **the number of bytes written in that call**, not confirmation that the remote peer has read or processed it.

### 8.3. `compact` when the parser only reads a partial frame

For example, a protocol starting with a **4-byte big-endian length**, followed by the payload. After `channel.read(buffer)` puts more bytes into the buffer while it is in the fill phase, the parser can use this logic:

~~~java
// Core parser snippet, assuming buffer is in the fill phase,
// and channel.read(buffer) was handled beforehand.
// MAX_FRAME is an application-defined guard threshold, such as 4096.
buffer.flip(); // Start reading the accumulated data region.
while (buffer.remaining() >= Integer.BYTES) {
    buffer.mark();                      // Remember the start of the header
    int length = buffer.getInt();       // 4 bytes, BIG_ENDIAN by default
    if (length < 0 || length > MAX_FRAME) {
        throw new java.io.IOException("Invalid length");
    }
    if (buffer.remaining() < length) {
        buffer.reset();                 // Keep the incomplete header as well
        break;                          // Wait for more bytes from the next read
    }
    byte[] payload = new byte[length];
    buffer.get(payload);
    handleFrame(payload);
}
buffer.compact(); // Keep all unparsed data, prepare to receive more.
~~~

This is a **parser snippet**, not a self-contained runnable program: `buffer`, `MAX_FRAME`, and `handleFrame` must be defined. If **fewer than 4 header bytes are available**, the loop does not start and `compact` preserves all remaining bytes. If the header is complete but the payload is incomplete, `reset` restores position to the start of the header so `compact` preserves both the header and the partial payload.

Important limitation: if **a frame is longer than the buffer's capacity**, this logic cannot make progress because there is no room left to receive more data. A production parser must choose a buffer large enough for the max frame, grow the buffer within a bounded limit, or process the payload incrementally without holding the entire frame in one buffer. `compact()` **does not automatically increase capacity**.

## 9. Byte order, multi-byte data types, and text

`ByteBuffer` provides numeric read/write operations such as `getShort`, `getInt`, `getLong`, and `putInt`. These operations use **byte order**. By default, a newly created ByteBuffer has **BIG_ENDIAN** order, which can be changed with:

~~~java
ByteBuffer b = ByteBuffer.allocate(4);
b.order(java.nio.ByteOrder.LITTLE_ENDIAN);
b.putInt(0x01020304); // Internal bytes in order 04 03 02 01
b.flip();
int n = b.getInt();  // n=0x01020304 with the same byte order
~~~

The four bytes of an `int` occupy **4 units of remaining**. If `remaining() < 4`, `getInt()` throws `BufferUnderflowException` rather than automatically reading more from the network. For binary protocols, both sides must **agree on byte order**, signed/unsigned representation, and field lengths before parsing.

**One byte is not necessarily one character.** UTF-8 has multi-byte characters; the boundary of `channel.read(ByteBuffer)` can cut right through the middle of a character. Do not decode each chunk independently into a String and assume no characters are corrupted. When processing a text stream, preserve trailing incomplete bytes or use a stateful `CharsetDecoder`. When converting a ByteBuffer into a byte array for decoding, copy only the valid `position..limit` region rather than the entire `capacity`.

Example:

~~~java
byte[] bytes = new byte[buffer.remaining()];
buffer.get(bytes); // Only takes the remaining region, advancing position.
String text = new String(
        bytes, java.nio.charset.StandardCharsets.UTF_8);
~~~

This is the right approach **if** remaining already corresponds to a complete UTF-8 string according to the protocol. It does not automatically fix splitting across multiple network reads.

## 10. Common misconceptions that cause bugs

| Misconception | Reality | How to fix |
|---|---|---|
| `remaining() == capacity - position()` at all times | Only true when limit == capacity | Use `remaining()` directly |
| `capacity()` is the number of bytes received from the network | Capacity is just the memory buffer size | Use the return value of `channel.read` and the proper `flip` sequence |
| `flip()` clears the buffer | Flip only sets limit=old position, position=0 | Use when switching from filling to consuming |
| `clear()` erases all bytes because it is named clear | Clear **does not erase contents** | Do not use clear to wipe sensitive data |
| `rewind()` is the same as `clear()` | Rewind keeps limit, clear sets limit=capacity | Choose the appropriate operation |
| `compact()` discards all read bytes and resets position=0 | Compact moves **unconsumed bytes** to the front; position=old remaining | Continue reading/writing after compact, then flip at the right time |
| `get(index)` advances position | Absolute access leaves position unchanged | Distinguish relative vs. absolute |
| `wrap(array, off, len)` creates a buffer with capacity=len | Capacity still equals `array.length` | Use `slice` if you need a sub-view with pos 0 and cap=len |
| `slice()` creates an independent copy | Slice shares bytes with the parent | Copy the data if isolation is needed |
| `hasRemaining()` tells whether the socket has bytes ready to receive | Only tells whether the buffer window still has elements | Track channel readiness/read result |
| `channel.write(buf)` always writes all remaining bytes | Can write partially, especially in non-blocking mode | Keep the buffer and wait for writable to continue writing |
| A ByteBuffer from `allocateDirect` always has `array()` | Direct buffers usually do not have an accessible backing array | Check `hasArray()` or use `get` to copy |
| Every buffer allows `put` | Read-only buffers throw `ReadOnlyBufferException` | Check `isReadOnly()` and design ownership |

### Read or write loop bugs

Wrong:

~~~java
// Illustrative buggy snippet:
ByteBuffer b = ByteBuffer.allocate(1024);
channel.read(b);
handle(b); // WRONG: not flipped yet, position is after the data just read.
~~~

Correct in terms of state management, though `handle` must still parse frames carefully:

~~~java
// State-management snippet; not a complete program:
ByteBuffer b = ByteBuffer.allocate(1024);
int n = channel.read(b);
if (n > 0) {
    b.flip();
    handle(b);  // Consume only the data within position..limit.
    b.compact();
}
~~~

If you have finished processing the entire buffer and do not need to keep any bytes, `clear()` can also make sense. If you need to keep a leading or trailing part of a frame, you must use `compact()` or an equivalent buffer management mechanism.

### Do not share a buffer arbitrarily across multiple threads

`ByteBuffer` and its views have **independent position/limit per object**, but having multiple threads simultaneously modify the data or state of **a single** ByteBuffer without synchronization can cause race conditions. Some applications create a `duplicate` for each reader to separate position/limit, yet the underlying content is still shared; you must design ownership and data synchronization properly.

A buffer passed to an async task must remain alive and not be `clear`ed/`compact`ed/overwritten by the caller before the task completes. Otherwise, even if remaining looked right at one moment, the data may be altered before it is sent.

## 11. Self-check questions

**1. A buffer has capacity=100, position=20, limit=45. What is remaining?** **25 bytes**, calculated as `45 - 20`; not 80.

**2. A buffer just created with `allocate(1024)` has remaining=1024. Does it definitely hold 1024 bytes of valid input?** **No.** That is 1024 bytes **available to be filled** before limit.

**3. `put` 7 bytes into a buffer with capacity=10 and then `flip`. What are the three indices?** `capacity=10, position=0, limit=7`, remaining=7.

**4. Read 3 bytes after the `flip` above; how much is left?** `position=3, limit=7, remaining=4`.

**5. In that state, what will `compact()` do?** Keeps the 4 unread bytes, `position=4, limit=10, remaining=6`; you can continue putting more data.

**6. Does `clear()` guarantee that old bytes are overwritten with 0?** **No.** It only resets position/limit/mark.

**7. Does `rewind()` after reading 3 of 7 bytes reset limit to capacity?** **No.** Position goes to 0 and limit remains 7.

**8. Does `get(5)` advance position to 6?** **No.** This is an absolute get; position does not change if the operation succeeds.

**9. Does `SocketChannel.read` returning 0 guarantee `buffer.remaining() == 0`?** **No.** With non-blocking I/O, there may simply be no data available; and if the buffer has no space left, it can also return 0. You must check both the mode and the state.

**10. What will `ByteBuffer.wrap(array, 2, 4)` on an array of length 10 have for capacity, position, limit, and remaining?** **10, 2, 6, 4**; not 4, 0, 4, 4.

**11. Does `compact()` guarantee that unread data will be preserved?** For a writable buffer in a valid state, it moves the remaining region to the beginning without erasing those bytes. If the buffer is **read-only**, it throws an exception.

**12. Can you call `flip()` once after every byte retrieved with `get` to keep reading?** Usually **no**. Flip switches from the filling phase to the consuming phase; calling it again at the wrong time can shrink limit and lose the desired data window.

## Official documentation

- [Java SE 17 – ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `allocate`, `wrap`, `slice`, `compact`, relative/absolute get/put, and byte order.
- [Java SE 17 – Buffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html): mark/position/limit/capacity invariants, `remaining()`, `hasRemaining()`, `flip`, `clear`, `rewind`.
- [Java SE 17 – SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): partial reads/writes with ByteBuffer, blocking and non-blocking.
- [Java SE 17 – CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): decoding text when UTF-8 bytes may span multiple reads.

**Remember:** `capacity` is the **fixed** capacity; `position` is the index for the next relative operation; `limit` is the **exclusive** upper bound; `remaining = limit - position`. Along the `fill → flip → consume → compact/clear → fill again` path, updating these four quantities is what enables proper handling of TCP NIO reads/writes that do not align with message boundaries.
