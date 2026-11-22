# The put → flip → write and read → flip → process → compact Cycles

## 1. Why Must We Understand These Two Cycles?

In Java NIO, a **ByteBuffer** is a memory region with **position**, **limit**, and **capacity** indices, while a **Channel** performs I/O operations with the bytes in the buffer. When using a **SocketChannel** for TCP, the program:

- Prepares the bytes to send with put(...), switches the buffer to the byte-reading state with flip(), and lets the channel consume the bytes with write(...).
- Receives bytes via channel.read(buffer), switches the buffer to the processing state with flip(), decodes only complete messages, and uses compact() to preserve any incomplete remainder.

Two cycles:

~~~text
SEND:    put(byte[]) → flip() → channel.write(buffer)
                                 |
                      still remaining? → keep buffer, continue writing
                                 |
                      all sent? → clear() to put new batch

RECEIVE: channel.read(buffer) → flip() → parse complete frames
                                     |
                             unprocessed bytes remain
                                     |
                                compact()
                                     |
                         next channel.read(buffer)
~~~

**Important:** TCP is a **byte stream**; it does not preserve boundaries between application write() calls. A single channel.read(...) call may retrieve a partial message or multiple concatenated messages; a single channel.write(...) call may also write only part of the data. Therefore, ByteBuffer state is foundational to avoiding the loss of incomplete bytes.

The terms **write mode** and **read mode** in this article refer to **operations on the buffer**. During channel.read(buffer), the channel is reading from the socket while simultaneously **writing into the buffer**, so the buffer must be in write mode. During channel.write(buffer), the channel is writing to the socket while **reading bytes from the buffer**, so the buffer must be in read mode.

## 2. How Do Position, Limit, and Capacity Work?

Every ByteBuffer always maintains the invariant:

~~~text
0 <= position <= limit <= capacity

remaining()    = limit - position
hasRemaining() = position < limit
~~~

- **capacity:** the total number of bytes it can hold; immutable throughout the lifecycle of a ByteBuffer.
- **position:** the index of the next byte to be put or got. On relative put or get operations, position advances.
- **limit:** the exclusive index of the region currently permitted for put/get.
- **mark:** an optional remembered position to return to via reset(); many state-transition operations discard the mark.

Important transitions:

| Method | Position after call | Limit after call | Meaning |
| --- | --- | --- | --- |
| **put(b)** | Increases by number of bytes put | Unchanged | Inserts bytes into the buffer |
| **get(...)** | Increases by number of bytes got | Unchanged | Reads bytes from the buffer |
| **flip()** | 0 | Old position | Prepares to read the bytes that were put/read from the channel |
| **clear()** | 0 | Capacity | Prepares to overwrite/reuse the entire buffer |
| **rewind()** | 0 | Keeps old limit | Re-reads the existing data region |
| **compact()** | Number of unprocessed bytes before compact | Capacity | Shifts bytes from [position,limit) to the beginning, then prepares to put/read more |
| **mark()/reset()** | reset sets it to the old mark | Unchanged | Returns to a position within the same read phase |

**clear() does not physically erase data in RAM.** It only resets position/limit and discards the mark. Therefore, clear() should not be used as a method for wiping sensitive data.

**flip(), clear(), rewind(), and compact() all discard the mark.** If a parser sets a mark before a header but discovers the body is incomplete, it must call reset() **before compact()**; otherwise, the mark becomes invalid.

Example with ByteBuffer.allocate(8):

~~~text
Initial:           [ . . . . . . . . ]  position=0, limit=8, capacity=8
put("HELLO"):      [ H E L L O . . . ]  position=5, limit=8, capacity=8
flip():            [ H E L L O . . . ]  position=0, limit=5, capacity=8
get 2 bytes:       [ H E L L O . . . ]  position=2, limit=5, capacity=8
compact():         [ L L O . . . . . ]  position=3, limit=8, capacity=8
~~~

The compact line above only illustrates the meaningful byte region; positions shown with dots are not guaranteed to be cleared. After compact, the three unread bytes **LLO** are at [0,3), and new bytes can be put starting from position 3 onward.

## 3. Outbound Cycle: put → flip → write

Suppose we send the string **HELLO** (5 UTF-8 bytes since all characters are ASCII) through a WritableByteChannel.

### 3.1. Put into a buffer in write mode

~~~java
ByteBuffer send = ByteBuffer.allocate(8);
send.put("HELLO".getBytes(StandardCharsets.UTF_8));
~~~

After put:

~~~text
[H E L L O . . .]
           ^ position=5
limit=8, capacity=8
~~~

If we call channel.write(send) right now, the channel will read from position 5 up to before limit 8, not the HELLO region that was put. That is why we must flip.

### 3.2. Flip to bound the exact region containing data

~~~java
send.flip();
~~~

After flip: **position=0, limit=5, capacity=8**. Only the region [0,5) is data meant for the channel. flip **does not send bytes over the network**; it only transitions the buffer state.

### 3.3. Write may consume only a portion of the bytes

~~~java
// Illustration for a WritableByteChannel that can always make progress.
while (send.hasRemaining()) {
    channel.write(send);
}
~~~

Each call to channel.write(send) returns the number of bytes consumed and advances position by that exact count. For example, if a channel accepts at most two bytes per call:

| Turn | Bytes channel accepts | Position | Limit | Remaining |
| --- | --- | ---: | ---: | ---: |
| Before write | None | 0 | 5 | 5 |
| write #1 | HE | 2 | 5 | 3 |
| write #2 | LL | 4 | 5 | 1 |
| write #3 | O | 5 | 5 | 0 |

At the end, position=limit=5. When **hasRemaining()==false**, clear() can be called to reuse the buffer for a new put.

**Data loss bug:** calling clear() while position is still less than limit discards the tracking of bytes not yet accepted by the channel. Keep the buffer in read mode until the channel has consumed all of them.

### 3.4. If you want to append more bytes while unsent data remains

There are two strategies:

1. **Do not append:** keep position/limit as-is and continue writing when the channel is ready.
2. **Controlled append:** compact() to shift unsent bytes to the front, put additional bytes if capacity allows, then flip() before writing.

~~~java
// Illustration: send is in read mode and still has unsent bytes.
send.compact();       // Preserve remaining bytes, switch to write mode.
send.put(moreBytes);  // Only when there is enough space.
send.flip();          // Switch back to read mode to continue writing.
~~~

compact() **does not send data by itself**. It moves the remaining bytes so you can continue building the outbound buffer. If moreBytes is too large, you need to queue additional buffers or apply backpressure; do not write past capacity.

### 3.5. Specifically for non-blocking SocketChannel: do not spin when write returns 0

~~~java
// Illustration in a write callback; pending is already flipped for sending.
while (pending.hasRemaining()) {
    int n = socketChannel.write(pending);
    if (n == 0) {
        // Keep position/limit; enable OP_WRITE interest and exit callback.
        break;
    }
}
if (!pending.hasRemaining()) {
    // No pending output left: remove OP_WRITE interest
    // if no more buffers need to be sent.
}
~~~

A SocketChannel in non-blocking mode can return **0** if it cannot write more at that moment. A continuous write loop in this case will cause a **busy-spin** and spike CPU usage. Selector.OP_WRITE should only be monitored when there is data waiting to be sent, and cleared once the queue is empty.

**Do not flip a second time** on a buffer already in read mode with position=2, limit=5: flipping again sets limit=2 and position=0, corrupting the region of bytes still left to send.

## 4. Inbound Cycle: read → flip → process → compact

The receiving ByteBuffer starts in write mode (position=0, limit=capacity). Channel.read(buffer) places new bytes into the buffer starting from position and advances position by the number of bytes actually received.

~~~java
ByteBuffer inbound = ByteBuffer.allocate(1024);
int n = socketChannel.read(inbound);
~~~

When n is positive, switch to read mode:

~~~java
inbound.flip();
parseCompleteFrames(inbound);
inbound.compact();
~~~

This is an API illustration; **parseCompleteFrames** is an application parser method, not a built-in Java API.

- **flip()** sets limit to the number of bytes currently present and position to 0, so the parser does not read unreceived bytes.
- **parseCompleteFrames(...)** consumes only frames with complete headers/bodies, leaving position at the start of the portion that cannot yet be processed.
- **compact()** shifts unprocessed bytes to the beginning of the buffer, sets position right after the remainder, and sets limit=capacity so the next read has room for new bytes.

### 4.1. Why compact instead of clear?

Suppose a protocol has a 4-byte header, and the current read only received **2 bytes of the header**.

~~~text
After read: [H0 H1 . . . . . .]  position=2, limit=capacity
flip:       [H0 H1 . . . . . .]  position=0, limit=2
Parser:     remaining=2 < 4 so header cannot be read yet.
compact:    [H0 H1 . . . . . .]  position=2, limit=capacity
Next read:  [H0 H1 H2 H3 B0 B1 ...]  (new bytes appended after H1)
~~~

If clear() were called before H0/H1 were processed, the next read could overwrite those two bytes and corrupt the header. compact() preserves incomplete data. If the parser has consumed all valid bytes, compact() leaves position=0, which is equivalent to starting the new write region from the beginning.

### 4.2. What if multiple frames are read at once?

A single read can bring multiple messages into the buffer. The parser must decode **each complete frame continuously** until there is not enough data for the next frame. When it stops, the remainder is preserved by compact. Never assume "one read corresponds to one TCP message".

### 4.3. What if the header is complete but the payload is incomplete?

If the parser consumes the header first and then discovers the body is incomplete, it must **return to the start of the header** before compacting (unless it stores the header state separately).

~~~java
// Parser illustration, buffer is already flipped() and in read mode.
while (true) {
    if (buffer.remaining() < Integer.BYTES) {
        break; // Incomplete header.
    }

    buffer.mark();                 // Remember start of header.
    int size = buffer.getInt();    // Read 4 bytes, position advances by 4.
    if (size < 0 || size > MAX_FRAME_BYTES) {
        throw new IOException("Invalid frame length");
    }

    if (buffer.remaining() < size) {
        buffer.reset(); // Preserve both header and incomplete body.
        break;
    }

    byte[] body = new byte[size];
    buffer.get(body);
    processFrame(body); // Process complete messages only.
}
buffer.compact();
~~~

This is a snippet with identifiers **buffer**, **MAX_FRAME_BYTES**, and **processFrame(...)** belonging to application code; it is not a standalone runnable file. The complete example in the next section declares all components.

**Design constraint:** a parser that holds an entire frame in a ByteBuffer must have a capacity of **at least 4 + MAX_FRAME_BYTES**. If a frame is larger than capacity, the buffer can fill up without the parser being able to consume anything; you must reject the frame or design a state machine that reads the body incrementally. On untrusted networks, always validate length limits before allocating.

## 5. Protocol Example to Understand Exact Byte Positions

Suppose two messages are sent in the format **4-byte length (big-endian) + UTF-8 payload**:

~~~text
Frame A, content "A":
  00 00 00 01 41                       = 4-byte header + 1-byte body = 5 bytes

Frame B, content "WORLD":
  00 00 00 05 57 4F 52 4C 44           = 4-byte header + 5-byte body = 9 bytes

Two consecutive frames: 5 + 9 = 14 bytes.
~~~

**ByteBuffer defaults to BIG_ENDIAN byte order**, so putInt() and getInt() on both sides are compatible if byte order is not changed. In real systems, both sides must agree on byte order and the length type in the protocol; length here is the **number of body bytes**, not the number of Java String characters.

Receiving 14 bytes using a ByteBuffer with capacity=12 is **completely feasible** because the parser consumes each 5- or 9-byte frame and then compacts. There is no need to fit both messages at the same time. The requirement is that **each complete frame** must fit in the buffer under this model.

An easily reproducible test plan is to create a mock ReadableByteChannel that returns at most **3 bytes at a time**: the parser must preserve incomplete header/body portions until a full frame is available. A mock WritableByteChannel that accepts at most **2 bytes at a time** will verify the outbound side.

## 6. Standalone Java 17+ Example with Verifiable Output

The following program tests both cycles without depending on TCP packet arrival timing. **LimitedWriter** consumes at most 2 bytes/call; **LimitedReader** returns at most 3 bytes/call. These are **simulated channels**, with no TCP sockets or assumptions about real segmentation.

**File BufferCycleDemo.java**

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.ClosedChannelException;
import java.nio.channels.ReadableByteChannel;
import java.nio.channels.WritableByteChannel;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

public class BufferCycleDemo {
    static class LimitedWriter implements WritableByteChannel {
        private final ByteArrayOutputStream bytes =
                new ByteArrayOutputStream();
        private boolean open = true;
        int calls;

        @Override
        public int write(ByteBuffer src) throws IOException {
            if (!open) {
                throw new ClosedChannelException();
            }
            int n = Math.min(2, src.remaining());
            byte[] part = new byte[n];
            src.get(part);
            bytes.write(part);
            calls++;
            return n;
        }

        String text() {
            return bytes.toString(StandardCharsets.UTF_8);
        }

        @Override
        public boolean isOpen() {
            return open;
        }

        @Override
        public void close() {
            open = false;
        }
    }

    static class LimitedReader implements ReadableByteChannel {
        final byte[] wire;
        private int offset;
        private boolean open = true;
        int calls;

        LimitedReader(byte[] wire) {
            this.wire = wire;
        }

        @Override
        public int read(ByteBuffer dst) throws IOException {
            if (!open) {
                throw new ClosedChannelException();
            }
            if (offset == wire.length) {
                return -1;
            }

            int n = Math.min(
                    3, Math.min(dst.remaining(), wire.length - offset));
            dst.put(wire, offset, n);
            offset += n;
            if (n > 0) {
                calls++;
            }
            return n;
        }

        @Override
        public boolean isOpen() {
            return open;
        }

        @Override
        public void close() {
            open = false;
        }
    }

    static byte[] frame(String text) {
        byte[] body = text.getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(4 + body.length)
                         .putInt(body.length)
                         .put(body).array();
    }

    public static void main(String[] args) throws Exception {
        // Outbound: put -> flip -> write -> clear.
        ByteBuffer send = ByteBuffer.allocate(8);
        send.put("HELLO".getBytes(StandardCharsets.UTF_8));
        send.flip();

        LimitedWriter writer = new LimitedWriter();
        while (send.hasRemaining()) {
            writer.write(send);
        }
        System.out.println("Sent: " + writer.text());
        System.out.println("Write calls: " + writer.calls);

        send.clear();
        System.out.println("Ready for next put: " +
                (send.position() == 0 && send.limit() == 8));
        writer.close();

        // Inbound: two frames, 14 bytes total.
        byte[] first = frame("A");
        byte[] second = frame("WORLD");
        byte[] wire = new byte[first.length + second.length];
        System.arraycopy(first, 0, wire, 0, first.length);
        System.arraycopy(second, 0, wire, first.length, second.length);

        LimitedReader reader = new LimitedReader(wire);
        ByteBuffer receive = ByteBuffer.allocate(12);
        List<String> messages = new ArrayList<>();
        int incomplete = 0;
        int n;

        // read -> flip -> parse -> compact.
        while ((n = reader.read(receive)) != -1) {
            if (n == 0) {
                throw new IllegalStateException("Receive buffer full");
            }

            receive.flip();
            while (true) {
                if (receive.remaining() < 4) {
                    if (receive.hasRemaining()) {
                        incomplete++;
                    }
                    break;
                }

                receive.mark();
                int length = receive.getInt();
                if (length < 0 || length > 8) {
                    throw new IOException("Invalid message length");
                }
                if (receive.remaining() < length) {
                    receive.reset();
                    incomplete++;
                    break;
                }

                byte[] body = new byte[length];
                receive.get(body);
                messages.add(
                        new String(body, StandardCharsets.UTF_8));
            }
            receive.compact();
        }

        if (receive.position() != 0) {
            throw new IOException("Truncated message at EOF");
        }
        reader.close();

        System.out.println("Read calls: " + reader.calls);
        System.out.println("Incomplete-frame waits: " + incomplete);
        System.out.println(
                "Decoded messages: " + String.join("|", messages));
        System.out.println(
                "Pending bytes after compact: " + receive.position());
    }
}
~~~

### How to Compile and Run

Save the file with the exact name **BufferCycleDemo.java**, using JDK 17 or newer:

~~~bash
javac --release 17 -encoding UTF-8 BufferCycleDemo.java
java BufferCycleDemo
~~~

**Exact stdout of the program upon success:**

~~~text
Sent: HELLO
Write calls: 3
Ready for next put: true
Read calls: 5
Incomplete-frame waits: 4
Decoded messages: A|WORLD
Pending bytes after compact: 0
~~~

The program logic has been tested in a Java runtime. The numbers are results **produced by the simulated channels capped at n=2/n=3**, not fixed behavior of a real TCP SocketChannel.

### Why does writing HELLO require exactly three write calls?

HELLO is 5 bytes long. LimitedWriter accepts at most 2 bytes/call: call 1 accepts HE, call 2 accepts LL, call 3 accepts O. **ByteBuffer.position** advances by the number of bytes actually accepted, so no bytes are sent twice or skipped. After sending everything, clear() sets position=0, limit=8, printing **Ready for next put: true**.

### Why does receiving two frames require five read calls?

Both frames total 14 bytes. LimitedReader delivers at most three bytes/call: the first four calls deliver 12 bytes, and the last call delivers 2 bytes. The parser must retain incomplete header/body portions and only consume complete frames.

| Read turn | New bytes | Bytes available after read | Processing | Position after compact |
| --- | ---: | ---: | --- | ---: |
| 1 | 3 | 3 | Missing 4-byte header | 3 |
| 2 | 3 | 6 | Decoded frame "A" (5 bytes), kept 1st byte of frame B | 1 |
| 3 | 3 | 4 | Complete header B but no body yet; reset to start of header | 4 |
| 4 | 3 | 7 | Header B + 3/5 body bytes; reset keeping all 7 bytes | 7 |
| 5 | 2 | 9 | Complete frame "WORLD" (9 bytes); decoded | 0 |

Turns 1–4 all end on an **incomplete frame**, so it prints **Incomplete-frame waits: 4**. After turn 5, both frames are decoded into **A|WORLD** and the buffer has no incomplete bytes left.

**A detail about frame(...):** The helper allocates an exact 4+N byte heap buffer, fills in the header/body, and accesses the backing array. Because the helper retrieves the byte array directly and does not call channel.write on that ByteBuffer, it does not need to flip before reading the array. When sending a ByteBuffer through a Channel, you must still follow put → flip → write.

## 7. Applying the Model to a Real SocketChannel

### Sending Side

A non-blocking SocketChannel must retain the outbound buffer across multiple callbacks if unsent bytes remain.

~~~java
// Illustration in OP_WRITE handler: pending is already flipped.
while (pending.hasRemaining()) {
    int written = socketChannel.write(pending);
    if (written == 0) {
        // Cannot write more right now: keep pending, wait for OP_WRITE.
        break;
    }
}
if (!pending.hasRemaining()) {
    // Remove OP_WRITE if the entire output queue is empty.
}
~~~

Do not clear the buffer while remaining bytes exist. Do not flip a partially read/sent buffer a second time. If multiple messages are queued to be sent, you need a specific queue or buffer management mechanism that preserves order and bounds the backlog size. A slow-reading peer will require **backpressure**; do not accumulate unbounded bytes in RAM.

### Receiving Side

~~~java
// Illustration: inbound stays in write mode between callbacks.
int count = socketChannel.read(inbound);
if (count > 0) {
    inbound.flip();
    parseCompleteFrames(inbound);
    inbound.compact();
} else if (count == 0) {
    // Non-blocking: no new bytes yet; wait for OP_READ event.
} else {
    // count == -1: EOF; check if there is an incomplete frame.
    // Then terminate/close the connection according to the protocol.
}
~~~

**This is a snippet, not a standalone Java file**: the variables socketChannel, inbound, the method parseCompleteFrames(...), and the selector mechanism must be declared in the server. Keeping the ByteBuffer in **write mode after compact()** is the prerequisite for the next read to append new data into the free space.

Note: if the parser cannot process any bytes because a frame is longer than capacity, compact will leave the buffer with no remaining space; the next read cannot make progress. Enforce frame limits, choose a sufficiently large buffer, or design a streaming parser. On EOF, if the buffer still contains data that does not form a complete frame, that is a **truncated frame** and must not be silently ignored.

## 8. Edge Cases and Common Mistakes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Put then forget to flip before write | Channel may read an unprepared region | Flip at the right time when switching to reading bytes |
| Channel.read then forget to flip | Parser sees position/limit not matching received bytes | Flip before parsing |
| Write returns less than remaining then clear | Drops unsent bytes | Keep in read mode, wait to continue writing |
| Read only half a header/body then clear | Loses bytes of the frame | Compact to preserve incomplete bytes |
| GetInt header, body incomplete, compact without reset | Loses the header | Mark/reset or independent parser state |
| Treat read 0 as EOF | Closes non-blocking connection prematurely | 0 is different from -1; wait for OP_READ |
| Write 0 then loop infinitely with while | High CPU, does not make peer receive faster | Break loop, wait for OP_WRITE |
| Keep OP_WRITE enabled when no data is waiting | Selector wakes up continuously | Only express OP_WRITE interest when output is pending |
| Call flip twice in a row | Second flip may set limit=0 | Only flip when transitioning write mode → read mode |
| Use rewind instead of clear to write new data | Limit does not become capacity, easy overflow | Clear when no bytes need to be preserved |
| Assume clear wipes RAM clean | Old bytes may remain in backing storage | Use proper data-wiping measures if security requires it |
| Split a UTF-8 character across two reads and decode separately | Unicode characters may be corrupted | Assemble bytes by frame before decoding or use a stateful CharsetDecoder |
| Accept arbitrary length from network and allocate | Can exhaust RAM | Validate length/limit payload size |
| Call .array() on a direct buffer | May throw UnsupportedOperationException | Use get/put or channel API |
| Share a mutable ByteBuffer across multiple threads | Races on position/limit and data | Define clear ownership or synchronize |

### read(...) returning -1 and timeouts

- **-1** is the channel EOF, not an automatically complete application message.
- **0** in non-blocking mode usually indicates no new bytes yet; it does not mean the peer has closed.
- **Read timeout** or application deadlines are separate mechanisms; do not use a pause in receiving bytes as a reliable delimiter.
- When the peer closes mid-header/mid-body, report a **truncated frame** or protocol error; do not process a half-received payload as complete.

### Heap buffers, direct buffers, and multiple connections

- **ByteBuffer.allocate(...)** allocates a heap buffer.
- **ByteBuffer.allocateDirect(...)** allocates a direct buffer, which does not have an accessible backing array by default; choose based on I/O needs and allocation cost.
- **slice()/duplicate()** have independent position/limit indices but may share the underlying byte region; do not modify the payload while another channel is sending the same region.
- **ByteBuffer is not thread-safe**. Each connection should have its own inbound/outbound state or clear ownership and synchronization mechanisms.

## 9. Self-Check Exercises

**1.** A buffer has capacity=12; after putting 5 bytes, what are position/limit? After flip?  
**Answer:** After put: position=5, limit=12. After flip: position=0, limit=5.

**2.** A send buffer has position=2, limit=9; channel.write returns 3. How many bytes remain?  
**Answer:** Position becomes 5, remaining=9-5=4 bytes. Do not clear before sending those 4 bytes.

**3.** A receive buffer in read mode has position=3, limit=8; what will compact do?  
**Answer:** Shifts the 5 unread bytes [3,8) to [0,5), sets position=5, limit=capacity, so more bytes can be received.

**4.** Why does channel.read use a buffer in write mode?  
**Answer:** The channel reads from the source but **writes bytes into the buffer**; position indicates where to place the next byte.

**5.** A header is 4 bytes and only 2/10 body bytes have arrived; should the request be processed?  
**Answer:** Not yet. Keep the header/body and receive more until the full length arrives; do not discard incomplete bytes.

**6.** Why can calling compact without reset after getInt cause a bug?  
**Answer:** Position has already moved past the header; compact only keeps bytes from position onward, causing the header to be lost if the parser has not saved the length in separate state.

**7.** Two frames total 14 bytes; can a buffer with capacity=12 handle them?  
**Answer:** Yes, as long as each individual frame is at most 12 bytes and the parser processes complete frames then compacts. For example, A (5 bytes) and WORLD (9 bytes) produce the correct result.

**8.** After clear, do old bytes disappear from RAM?  
**Answer:** No, clear only resets position/limit/mark.

**9.** Why might a non-blocking SocketChannel write require multiple callbacks?  
**Answer:** The socket may accept only part of the bytes, or even return 0; you must keep the buffer and wait for further writability.

**10.** When should compact be used instead of clear?  
**Answer:** When there are still **unsent** or **unprocessed** bytes that must be kept to append with new data. If everything has been processed/sent and you want to start a new batch, clear is simpler.

## 10. Java NIO Implementation Checklist

1. Clearly identify when a buffer is in write mode versus read mode; do not mix the two meanings.
2. Send: put → flip → write until no remaining bytes; for non-blocking, wait for OP_WRITE instead of spinning.
3. Receive: read → flip → parse complete frames → compact, preserving incomplete data.
4. The parser must have a framing convention, length/UTF-8 validation, EOF handling, and size limits.
5. Never assume one read = one message or that one write is fully consumed.
6. If the buffer is full without a complete frame, reject it or switch to a state machine/streaming approach.
7. Manage OP_WRITE interest at the right time and apply backpressure to the output queue.
8. Avoid sharing a ByteBuffer across multiple threads or connections without clear ownership.
9. Test fragmented headers/bodies, multiple consecutive frames, partial writes, read/write returning 0, and EOF mid-frame.
10. Always inspect position, limit, and remaining when debugging instead of only printing buffer capacity.

## Conclusion

**put → flip → write** transitions bytes from the **putting data into ByteBuffer** phase to the **channel consuming bytes** phase. **read → flip → process → compact** transitions bytes from the **channel receiving data** phase to the **parser reading complete messages** phase, while preserving incomplete bytes for the next round.

Mastering **position/limit/capacity**, flipping at the right time, compacting when bytes must be preserved, and handling partial reads/writes is the foundation for writing reliable Java NIO networking code.

### References

- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): buffers and put/get, heap/direct, byte order.
- [Java SE 17 — Buffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html): position, limit, capacity, flip, clear, compact/rewind, mark/reset.
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): reading/writing and non-blocking mode.
- [Java SE 17 — WritableByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/WritableByteChannel.html): write(ByteBuffer).
- [Java SE 17 — ReadableByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ReadableByteChannel.html): read(ByteBuffer).
- [Java SE 17 — SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): OP_READ and OP_WRITE.
