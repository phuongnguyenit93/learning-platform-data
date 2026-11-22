# Buffer State Transition Table in Java NIO

`Buffer` in `java.nio` is a **stateful data access window** model. When reading or writing through `ByteBuffer`, `CharBuffer`, or other primitive-type buffers, data is managed via four markers: `capacity`, `limit`, `position`, and `mark`. The table below helps predict the exact state before and after each operation, especially in the **write data → `flip()` → read data → `clear()` or `compact()`** cycle.

## 1. Conventions for Reading the State Table

| Symbol | Meaning | Rule |
|---|---|---|
| `C` = `capacity()` | Total number of elements the buffer can hold | Immutable throughout that buffer's lifetime |
| `L` = `limit()` | *Exclusive* upper bound of the currently accessible region | `0 ≤ L ≤ C` |
| `P` = `position()` | Index of the next element for relative read/write | `0 ≤ P ≤ L` |
| `M` = `mark` | Position saved by `mark()`; no public getter | Unset (denoted `—`), or `0 ≤ M ≤ P` |
| `R` = `remaining()` | Number of elements remaining from the current position to the limit | `R = L − P` |

**Invariant:** if a mark exists, then `0 ≤ M ≤ P ≤ L ≤ C`. `P` is only a logical pointer: it **does not necessarily** reflect which elements in memory have been initialized. State-changing operations can discard the mark; Java throws `InvalidMarkException` when calling `reset()` without a valid mark.

For example: `ByteBuffer.allocate(8)` creates `(P=0, L=8, C=8, M=—)`; `remaining() = 8`. The relative operation region is `[P, L)`. The element at index `L` is **not** within the valid region, even when `L < C`.

## 2. Standard State Transition Table

In the table: `P₀, L₀, C₀, M₀` are the state before the operation; `P₁, L₁, M₁` are the state after. `C` is always equal to `C₀`. "Unchanged" means the pointers/mark do not change; it does not assert that memory contents are identical.

| Operation | Condition/meaning | State after | Effect on mark and data |
|---|---|---|---|
| `allocate(C)` | Creates a new buffer with `C ≥ 0` | `P₁=0, L₁=C` | `M₁=—`; initial elements hold the type's default value |
| `put(value)` | **Relatively** writes one element, requiring `P₀ < L₀` | `P₁=P₀+1, L₁=L₀` | Mark unchanged; writes data at index `P₀` |
| `get()` | **Relatively** reads one element, requiring `P₀ < L₀` | `P₁=P₀+1, L₁=L₀` | Mark unchanged; reads data at index `P₀` |
| `put(src)` / `get(dst)` | Relatively writes/reads `n` elements; requires `n ≤ L₀−P₀` | `P₁=P₀+n, L₁=L₀` | Mark unchanged if the operation succeeds; corresponding data region is written/read |
| `get(i)` / `put(i, value)` | **Absolute** access; requires `0 ≤ i < L₀` | `P₁=P₀, L₁=L₀` | Mark unchanged; `put` modifies data at `i` |
| `flip()` | Switches from writing phase to reading **what was written** | `P₁=0, L₁=P₀` | Clears mark; does **not** copy/erase data |
| `clear()` | Prepares to rewrite the entire backing region | `P₁=0, L₁=C₀` | Clears mark; does **not** erase old bytes/characters |
| `rewind()` | Re-reads from the beginning within the current limit | `P₁=0, L₁=L₀` | Clears mark; data unchanged |
| `compact()` | Keeps the **unread** portion `[P₀,L₀)`, prepares for appended writes | `P₁=L₀−P₀, L₁=C₀` | Clears mark; shifts `L₀−P₀` unread elements to the start of the buffer |
| `mark()` | Remembers the current position | `P₁=P₀, L₁=L₀, M₁=P₀` | Sets/overwrites mark; data unchanged |
| `reset()` | Returns to the saved mark | `P₁=M₀, L₁=L₀, M₁=M₀` | Preserves mark; if no mark is set, throws `InvalidMarkException` |
| `position(p)` | Sets a new position, requiring `0 ≤ p ≤ L₀` | `P₁=p, L₁=L₀` | If `M₀ > p`, clears mark; otherwise keeps it |
| `limit(l)` | Sets a new limit, requiring `0 ≤ l ≤ C₀` | `L₁=l, P₁=min(P₀,l)` | If `M₀ > l`, clears mark; otherwise keeps it |
| `remaining()` / `hasRemaining()` | Queries `L−P` / `P<L` | All markers unchanged | Does not modify data |

**API notes:** `flip()`, `clear()`, `rewind()`, `mark()`, `reset()`, `position(int)`, and `limit(int)` exist on `Buffer`. `get`, `put`, and `compact` are methods on typed buffers such as `ByteBuffer`; `compact()` is not directly callable on a variable typed only as `Buffer`. Not all buffers support writing; a read-only buffer rejects `put` and `compact`.

## 3. Practical Progression Table: Write, Partial Read, Compact, and Continue Writing

With an 8-byte buffer, the following example shows **mark**, the unread data portion, and the state after `compact()`. The symbol `—` means no mark is set; text in the "Relevant data" column only describes the written/remaining-to-read portion and makes no guarantee about cells outside that range.

| Step | Operation | P | L | C | M | R=L−P | Relevant data |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | `allocate(8)` | 0 | 8 | 8 | — | 8 | No application data written yet |
| 2 | `put("ABCD")` | 4 | 8 | 8 | — | 4 | `[0..3] = ABCD` |
| 3 | `flip()` | 0 | 4 | 8 | — | 4 | Read window `ABCD` |
| 4 | `get(2 bytes)` → `AB` | 2 | 4 | 8 | — | 2 | Unread: `CD` |
| 5 | `mark()` | 2 | 4 | 8 | 2 | 2 | Marked before `C` |
| 6 | `get()` → `C` | 3 | 4 | 8 | 2 | 1 | Unread from current position: `D` |
| 7 | `reset()` | 2 | 4 | 8 | 2 | 2 | Returned before `CD` |
| 8 | `compact()` | 2 | 8 | 8 | — | 6 | Shifted `CD` to indices `0,1` |
| 9 | `put("EF")` | 4 | 8 | 8 | — | 4 | `[0..3] = CDEF` |
| 10 | `flip()` | 0 | 4 | 8 | — | 4 | Read window `CDEF` |
| 11 | `get(4 bytes)` → `CDEF` | 4 | 4 | 8 | — | 0 | No valid data left in window |
| 12 | `rewind()` | 0 | 4 | 8 | — | 4 | Can re-read `CDEF` |
| 13 | `clear()` | 0 | 8 | 8 | — | 8 | Old data may still sit in memory, but is no longer treated as a valid record |

Common pitfall at step 8: `compact()` takes the **unread portion starting from the current position**, not all data ever written. Without calling `reset()` at step 7, `compact()` would only shift `D` and leave `P=1`.

## 4. Standalone Java 17+ Program

Save the file with the exact name `BufferStateDemo.java`:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

public class BufferStateDemo {
    private static void state(String action, ByteBuffer buffer) {
        System.out.printf(
                "%s: P=%d, L=%d, C=%d, R=%d%n",
                action,
                buffer.position(),
                buffer.limit(),
                buffer.capacity(),
                buffer.remaining()
        );
    }

    public static void main(String[] args) {
        ByteBuffer buffer = ByteBuffer.allocate(8);
        state("allocate", buffer);

        buffer.put("ABCD".getBytes(StandardCharsets.US_ASCII));
        state("put ABCD", buffer);

        buffer.flip();
        state("flip", buffer);

        byte[] firstTwo = new byte[2];
        buffer.get(firstTwo);
        System.out.println("read 2 = " + new String(firstTwo, StandardCharsets.US_ASCII));
        state("get 2", buffer);

        buffer.mark();
        state("mark", buffer);

        System.out.println("next = " + (char) buffer.get());
        state("get C", buffer);

        buffer.reset();
        state("reset", buffer);

        buffer.compact();
        state("compact", buffer);

        buffer.put("EF".getBytes(StandardCharsets.US_ASCII));
        state("put EF", buffer);

        buffer.flip();
        state("flip 2", buffer);

        byte[] finalBytes = new byte[buffer.remaining()];
        buffer.get(finalBytes);
        System.out.println("final = " + new String(finalBytes, StandardCharsets.US_ASCII));
        state("get all", buffer);

        buffer.rewind();
        state("rewind", buffer);

        buffer.clear();
        state("clear", buffer);
    }
}
~~~

Run inside the directory containing the file:

~~~bash
javac BufferStateDemo.java
java BufferStateDemo
~~~

Exact expected stdout:

~~~text
allocate: P=0, L=8, C=8, R=8
put ABCD: P=4, L=8, C=8, R=4
flip: P=0, L=4, C=8, R=4
read 2 = AB
get 2: P=2, L=4, C=8, R=2
mark: P=2, L=4, C=8, R=2
next = C
get C: P=3, L=4, C=8, R=1
reset: P=2, L=4, C=8, R=2
compact: P=2, L=8, C=8, R=6
put EF: P=4, L=8, C=8, R=4
flip 2: P=0, L=4, C=8, R=4
final = CDEF
get all: P=4, L=4, C=8, R=0
rewind: P=0, L=4, C=8, R=4
clear: P=0, L=8, C=8, R=8
~~~

The output demonstrates that `reset()` restores `P=2` without changing `L=4`, then `compact()` preserves `CD` accurately; `clear()` only resets the logical bounds.

## 5. Frequently Overlooked Transition Branches

### Decreasing position or limit can invalidate the mark

Suppose the state is `(P=5, L=8, C=8, M=4)`.

- Calling `position(2)` ⇒ `(P=2, L=8, M=—)` because mark `4 > 2`. Calling `reset()` now throws `InvalidMarkException`.
- Calling `limit(3)` **on the original state** ⇒ `(P=3, L=3, M=—)`; position is clamped down to `3` and mark `4` is discarded.
- Calling `limit(6)` **on the original state** ⇒ `(P=5, L=6, M=4)`; the mark remains valid.
- Calling `position(6)` **on the original state** ⇒ `(P=6, L=8, M=4)`; the mark remains valid.

Both setters only change state if the argument is within the valid range. `position(p)` with `p > limit`, or `limit(l)` with `l > capacity`, throws `IllegalArgumentException`.

### Absolute access vs. relative access

Suppose `(P=2, L=5, C=8)`:

- `get()` reads index `2` and increments `P` to `3`.
- `get(4)` reads index `4` and **does not increment `P`**.
- `put(1, (byte) 7)` writes index `1` and **does not increment `P`**.
- `get(5)` is invalid because `limit` is an exclusive bound, even though `5 < capacity`.

With `ByteBuffer`, relative reading when insufficient data remains throws `BufferUnderflowException`; relative writing when insufficient space remains throws `BufferOverflowException`; an absolute index outside `[0, limit)` typically throws `IndexOutOfBoundsException`. Writing to a read-only buffer throws `ReadOnlyBufferException`. Checking `hasRemaining()` or `remaining()` helps prevent reading/writing past the window.

### `slice()`, `duplicate()`, and view states

Views share the **backing storage contents** while maintaining independent position markers:

| Created from source buffer | View's Position | View's Limit / Capacity | Relationship with data and mark |
|---|---|---|---|
| `slice()` | `0` | Equal to source's `remaining()` at creation time | Maps only the source's `[P,L)` region; new mark is undefined; shares data |
| `duplicate()` | Equal to source's `P` | Equal to source's `L/C` | Copies state including mark (if any); shares data, and markers update independently thereafter |
| `asReadOnlyBuffer()` on `ByteBuffer` | Equal to source's `P` | Equal to source's `L/C` | Shares data and copies initial markers/mark; disallows writing via the view |

For example: if the source has `(P=2, L=5, C=8)`, `slice()` creates a view `(P=0, L=3, C=3)`. After `slice()`, changing the view's position does not move the source's position. Modifying **contents** through a writable view is still visible from another view because they share the backing storage.

## 6. Choosing the Right Operation in an I/O Pipeline

| Need | Operation | Reason |
|---|---|---|
| Wrote into an empty buffer and ready to consume the written data | `flip()` | Bounds the read region to the previous `position` |
| Re-read data within the current limit | `rewind()` | Keeps `limit`, sets `position` back to `0` |
| Finished processing all data, want to receive a fresh batch from the start | `clear()` | Opens full capacity for writing; no need to keep unread data |
| Consumed part of the data, need to append a new batch after the unprocessed remainder | `compact()` | Shifts the `remaining()` portion to the beginning and opens space for the next batch |
| Want to read speculatively and return | `mark()` → read → `reset()` | Restores position if the mark has not been invalidated |
| Only want to inspect the element at a specific index | `get(index)` | Does not shift the position of the next relative read |

When receiving fragmented data from a `SocketChannel`, the typical pattern is **read from channel → `flip()` → consume complete messages → `compact()` → read more**. If a message is still missing bytes, `compact()` keeps the incomplete part to combine with the next read. Only use `clear()` when you are sure nothing remaining is needed. When writing a buffer to a channel, a single `write(buffer)` call may not consume all of `remaining()`; you must inspect the post-write state to handle any remainder rather than assuming all bytes were sent.

**Quick rule of thumb:** `flip` sets `limit = old position` for reading; `clear` sets `limit = capacity` for rewriting; `compact` keeps `remaining` and sets `position = number of shifted elements`. None of these three operations performs I/O on a file/socket by itself.
