# Mark, reset, markSupported, and readlimit in Java I/O

> **Context:** Java Core I/O → **Buffering and Stream Composition**. This lesson focuses on the mechanism of **marking a read position, reading ahead, and rewinding**, how wrappers add this capability, the difference between read-ahead limits in **bytes** versus **characters**, and the boundaries you must not ignore when writing parsers. Standalone examples compile with Java 17; the core APIs presented have existed since earlier Java versions.

## 1. Why Mark and Re-read?

Suppose a parser receives a byte stream, needs to inspect the first few bytes to guess the format, and then let the main processor read again **from the exact marked point**:

1. Set a bookmark with `mark(readlimit)`.
2. Tentatively read a slice with `read(...)`.
3. Decide how to handle the stream based on that peeked slice.
4. If that slice must be read again, call `reset()` to move **that same stream's read position** back to the marked point.

This is **lookahead**: reading ahead without treating those bytes as permanently consumed. Some input streams only support sequential reading, with no seek or rewind capability; hence **not every stream supports mark/reset**. A buffer can retain the bytes read so far to replay them without repositioning the underlying file/socket.

Immediately distinguish three things:

- **`mark`** only remembers a position; it does not return a bookmark object, clone the stream, or read data.
- **`reset`** moves the position back to the **most recent still-valid mark**, not by default to the beginning of the stream or file.
- **`markSupported`** reports whether **the specific stream implementation in use** supports the mark/reset protocol; a variable's declared type `InputStream` or `Reader` is not enough to tell.

## 2. Four Components of the API Contract

### 2.1. `InputStream.mark(int readlimit)`

Marks the current position in a byte-input stream. The `readlimit` parameter is the **maximum number of bytes requested to be preserved so reset remains possible** after the mark. For example, `mark(8)` means subsequent code intends to read ahead at most 8 bytes and still replay them.

- This method returns `void` and **does not declare `throws IOException`** on `InputStream`.
- `InputStream`'s default implementation of `mark(int)` **does nothing**. You must check the subclass/wrapper to know whether marking takes effect.
- You can mark multiple times; **a new mark replaces the previous mark**. There is no stack saving multiple marks to reset backward across several marks.
- **`readlimit` is not the number of allowed `read` calls** and is not a read-rate limit. It is a bound on the **span of data that must remain replayable**.
- Once you read **past `readlimit`**, the implementation has **no obligation** to keep data for reset. Reset may fail; some streams can still reset due to their own storage properties. Never write code that depends on a mark definitely invalidating at byte `readlimit + 1`.
- Setting a huge `readlimit` may cause a wrapper to retain/expand a matching buffer, creating memory pressure; it cannot be treated as an unbounded rewind mechanism.

### 2.2. `InputStream.reset()`

Repositions the stream to the most recent mark (if still valid). Bytes read since that mark can be replayed in the same order. `reset()` declares `throws IOException`.

Cases to handle: the stream does not support reset, no mark was set, the mark was invalidated, the stream was closed, or another I/O error occurred. Depending on the stream type, calling `reset` before any `mark` might return to an implementation-specific default state (like the start of an in-memory source), but **you must never assume every stream behaves that way**.

**Reset does not create new data** and does not guarantee the underlying source stayed unchanged if other code interacts with the same underlying resource. In a normal read pipeline, interact only through **the single wrapper being marked and reset**.

### 2.3. `InputStream.markSupported()`

Returns `boolean`. `InputStream`'s contract states that mark/reset support is an invariant property of each instance. The default method returns `false`; capable subclasses/wrappers return `true`.

~~~java
// Fragment: in is an open InputStream.
if (in.markSupported()) {
    in.mark(16);
    // Read ahead only within the designed range.
    in.reset();
} else {
    // Choose buffering, pushback, or an alternative strategy.
}
~~~

This is an **illustrative fragment**: `in` is supplied by surrounding code. In real programs you still must catch or declare `IOException` on `reset()`, even when `markSupported()` is `true`: support does not mean every mark remains valid.

### 2.4. What Unit Does `readlimit` Measure?

In `InputStream.mark(n)`, `n` is measured in **bytes read since the mark**; for `Reader.mark(n)`, the parameter is named **`readAheadLimit`**, measured in **`Reader` characters (UTF-16 code units in Java)**.

Do not treat either parameter as grapheme count (user-perceived characters) or Unicode code point count. A supplementary emoji outside the BMP takes **2 UTF-16 code units**, while when UTF-8 encoded it takes **4 bytes**. When building text parsers, calculate read-ahead at the wrapper layer your parser interacts with.

**Key point:** `readlimit` bounds the span of replayable data—it is not a limit on **total stream length**, not an `available()` bound, and does not turn reads into non-blocking operations.

## 3. Which Common Implementations Support It and Which Do Not?

| Stream/Reader | `markSupported()` Typically Returns | What to Know |
| --- | --- | --- |
| Default `InputStream` | `false` | Default `mark` does nothing; default `reset` throws an error. |
| `FileInputStream` | `false` | The file descriptor has a position, yet this stream class does not provide mark/reset; file seeking is a different API. |
| `ByteArrayInputStream` | `true` | Source already resides in memory; can reset to mark even after reading past `readlimit`. |
| `BufferedInputStream` | `true` | Buffer can preserve read bytes; `readlimit` sets the intended lookahead retention. |
| `FilterInputStream` | Depends on the wrapped inner stream | Base class delegates operations; subclasses may change behavior. |
| `DataInputStream` | Depends on the wrapped inner stream | Some methods read multiple bytes; mark on the right wrapper and budget by byte count. |
| `PushbackInputStream` | `false` | Has `unread` to push bytes back into its own buffer, yet does not support mark/reset. |
| `InputStreamReader` | `false` | Byte → character decoder; to re-read characters, typically wrap externally with `BufferedReader`. |
| `BufferedReader` | `true` | `mark(int readAheadLimit)` counts **code units/`char`s**, able to replay after reset. |
| `StringReader` and `CharArrayReader` | `true` | In-memory character source with its own reset mechanism. |
| `PushbackReader` | `false` | Uses `unread` instead of mark/reset. |

This table shows standard API behavior for common classes; it does not replace reading a specific subclass's documentation or calling `markSupported()` when input is an arbitrary third-party stream.

### 3.1. What Does a Wrapper Change?

~~~text
FileInputStream [markSupported = false]
          |
          v
BufferedInputStream [markSupported = true]
          |
          v
Parser receives BufferedInputStream, never reads FileInputStream directly
~~~

`BufferedInputStream` retains read bytes in its buffer when needed. Therefore, even though `FileInputStream` does not support mark, the wrapper can support it on its own **without requiring the base source to be seekable**.

Avoid keeping both variables and interleaving reads:

~~~java
// Bad design fragment: source and buffered share one data source.
InputStream source = /* source from caller */;
BufferedInputStream buffered = new BufferedInputStream(source);
buffered.mark(8);
int peek = buffered.read();
int next = source.read(); // Do not read source directly after wrapping!
// buffered.reset() cannot cleanly restore two divergent read cursors.
~~~

The buffer may already have pulled extra bytes from `source` before the caller reads directly. Correct rule: create the wrapper once and pass that wrapper to all code consuming the source. Closing the wrapper typically closes the inner source too; manage ownership to avoid premature or duplicate closes from tangled lifecycle handling.

## 4. Runnable Example: Peeking and Replaying Bytes

Create **`MarkByteDemo.java`**:

~~~java
import java.io.BufferedInputStream;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class MarkByteDemo {
    public static void main(String[] args) throws IOException {
        byte[] data = "ABCDE".getBytes(StandardCharsets.US_ASCII);

        // bufferSize = 2 to see mark/reset work despite a small buffer.
        try (InputStream in = new BufferedInputStream(
                new ByteArrayInputStream(data), 2)) {

            System.out.println("supported=" + in.markSupported());
            System.out.println("first=" + (char) in.read()); // A

            in.mark(3); // Mark before B, intending to peek up to 3 bytes.
            System.out.println("peek=" + (char) in.read()
                    + "" + (char) in.read());             // BC

            in.reset(); // Return before B.
            System.out.println("replay=" + (char) in.read()
                    + "" + (char) in.read());             // BC
        }
    }
}
~~~

Run with Java 17 (the code also works on older Java APIs):

~~~bash
javac MarkByteDemo.java
java MarkByteDemo
~~~

Stdout:

~~~text
supported=true
first=A
peek=BC
replay=BC
~~~

**Step-by-step explanation:** The cursor starts before `A`. After the first `read()`, the cursor sits before `B`. `mark(3)` saves this position; two reads yield `B` and `C`. `reset()` moves the logical cursor back to `B`, so the next two reads replay `BC`. No new bytes are added to the source. An initial buffer size of **2** does not prevent marking with `readlimit=3`: the wrapper can retain/expand the needed data when necessary.

The expression `"peek=" + (char)in.read() + "" + (char)in.read()` intentionally starts with a **String**, because adding two `char` values directly would perform integer addition instead of string concatenation. Note especially that if a file holds multi-byte UTF-8 characters, casting `(char) in.read()` byte-by-byte **is not a valid text decoder**. The demo uses ASCII to illustrate byte positions, not as a Unicode parser.

## 5. Counterexample: `readlimit` Is Not an Immediate Mark-Expiration Rule

Create **`MemoryMarkDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;

public class MemoryMarkDemo {
    public static void main(String[] args) throws IOException {
        byte[] values = {10, 20, 30, 40};

        try (ByteArrayInputStream in = new ByteArrayInputStream(values)) {
            System.out.println("supported=" + in.markSupported());

            in.mark(1); // Request 1-byte lookahead.
            System.out.println(in.read()); // 10
            System.out.println(in.read()); // 20
            System.out.println(in.read()); // 30

            in.reset(); // Still works with ByteArrayInputStream.
            System.out.println("afterReset=" + in.read()); // 10
        }
    }
}
~~~

~~~bash
javac MemoryMarkDemo.java
java MemoryMarkDemo
~~~

Stdout:

~~~text
supported=true
10
20
30
afterReset=10
~~~

Even after reading **3 bytes past `mark(1)`**, `ByteArrayInputStream` still remembers the position because all data is already in memory and this implementation does not use `readlimit` to discard the mark. The general contract only says the stream is **not required** to remember once the limit is exceeded. Therefore:

- **Do not** write general unit tests asserting "after reading `readlimit + 1` bytes, `reset` must throw `IOException`."
- **Do not** equate `readlimit` with the exact memory footprint used by every implementation.
- If a parser **must** replay N bytes, choose an implementation with an appropriate contract, set `readlimit` to cover the lookahead, and handle `IOException` when needed.

With `BufferedInputStream`, a mark can be invalidated once data to preserve exceeds the limit and the buffer has to discard the old region. Exactly which call triggers failure depends on buffer state and API contract; never build business logic around internal buffer-eviction timing.

## 6. How `BufferedInputStream` Uses Its Buffer When Marked

Without a mark, `BufferedInputStream` can consume data from the source in chunks and discard already-served bytes, reducing source I/O calls. With a mark active:

1. `mark(readlimit)` records the current **logical position** in the buffer.
2. Further reads may take bytes from the buffer, refill from the source, or shift preserved bytes.
3. While reset may still be needed, the wrapper preserves the region from the mark to the read position; a small buffer may expand to satisfy `readlimit` when needed.
4. Once preserving the mark falls outside the budget, the wrapper is permitted to drop the mark/old region to keep operating efficiently.
5. A valid `reset` only moves the logical read position within the retained data; it does not necessarily alter the underlying file/socket position.

This explains why a mark with a large `readlimit` on a long stream can increase memory consumption. **`new BufferedInputStream(source, 8192)` does not mean lookahead is strictly capped at 8192 bytes**, nor does `mark(1_000_000)` **guarantee** exactly 1 MB is allocated immediately upon `mark`. Internal structures are implementation details; what you should design for is **the actual N bytes that may need replay**.

If you only want to inspect a 4- or 8-byte header, pass a sensible `readlimit` instead of `Integer.MAX_VALUE`. If you need random access on a large file, consider `FileChannel.position(...)` or `RandomAccessFile.seek(...)`, or have your parser save header bytes in its own structure: mark/reset is not an arbitrary seek mechanism.

## 7. `BufferedReader.mark(readAheadLimit)`: Measured in Characters

`Reader` works with data already decoded into characters, so `mark(int readAheadLimit)` measures its limit in **`char`/UTF-16 code units** emitted by the `Reader`. Unlike `InputStream.mark`, `Reader.mark`'s signature **can throw `IOException`**. `BufferedReader` supports mark/reset and can expand its buffer to retain the lookahead span.

Create **`MarkReaderDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class MarkReaderDemo {
    public static void main(String[] args) throws IOException {
        // String containing A + supplementary emoji U+1F642 + B.
        try (BufferedReader reader =
                new BufferedReader(new StringReader("A\uD83D\uDE42B"))) {
            System.out.println("supported=" + reader.markSupported());

            reader.mark(3); // 3 UTF-16 code units, not 3 glyphs.
            System.out.println("first=" + (char) reader.read()); // A

            char high = (char) reader.read();
            char low = (char) reader.read();
            System.out.println("high=" + Character.isHighSurrogate(high));
            System.out.println("low=" + Character.isLowSurrogate(low));

            reader.reset();
            System.out.println("replay=" + (char) reader.read());
        }
    }
}
~~~

~~~bash
javac MarkReaderDemo.java
java MarkReaderDemo
~~~

Stdout:

~~~text
supported=true
first=A
high=true
low=true
replay=A
~~~

A supplementary emoji outside the BMP uses **two** `char`s. When `BufferedReader` executes three `read()` calls in this example, it consumes 3 code units (A + high surrogate + low surrogate), even though a human sees two characters. `readAheadLimit=3` was chosen specifically for the number of `char`s needing replay.

When the source is bytes from network/file, the usual pattern is:

~~~java
// Fragment: source is an InputStream provided by the caller.
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(source, StandardCharsets.UTF_8))) {
    if (reader.markSupported()) {
        reader.mark(64); // 64 char units at the reader layer.
        // Read characters...
        reader.reset();
    }
}
~~~

This fragment requires importing `java.io.BufferedReader`, `java.io.InputStreamReader`, and `java.nio.charset.StandardCharsets`, and sits in a method handling `IOException`. Call mark **on `BufferedReader`**, since `InputStreamReader` normally does not support mark. Never reset the underlying byte stream once `InputStreamReader` has read ahead bytes to decode; decoder state and buffer would fall out of sync.

### 7.1. `BufferedReader.mark(0)` and Input Preconditions

`BufferedReader.mark(readAheadLimit)` throws `IllegalArgumentException` if `readAheadLimit` is negative. `0` is a valid argument, yet **must not be relied upon to promise replaying even one character**: if you need to read ahead N characters, set a limit of at least N and handle reset failures. For `BufferedInputStream.mark(readlimit)`, the general contract does not guarantee identical handling of unusual values; pass well-calculated valid limits.

Do not confuse `BufferedReader`'s `char` buffer with `BufferedInputStream`'s byte buffer: both cache data, yet sit at **two different layers**. When composing layers, budgeting the limit belongs to the layer the parser reads from.

## 8. Mark After `readLine` or `skip`: Does It Count?

**Possibly yes.** Mark/reset depends on the amount of data read after the mark and on the implementation, not merely the number of `read()` calls.

- `BufferedReader.readLine()` reads characters to the end of a line and normally consumes the line terminator; `readAheadLimit` must account for all **consumed** characters, including newline characters absent from the returned `String`. A Windows `\r\n` terminator is two code units.
- `skip(n)` also advances the read position; depending on the implementation's contract, skipping can consume data needed for reset. Never assume "skip doesn't count."
- `InputStream.read(byte[])` may read fewer bytes than requested; the amount **actually read** is what matters. For `DataInputStream.readInt()`, one integer consumes **4 bytes**, not 1 "character"; `readlimit` belongs to the byte layer.
- `InputStream.readAllBytes()` or `transferTo(...)` can consume all remaining data; setting a mark with a small `readlimit` before an unbounded consumption can render reset unavailable.

For header-sniffing parsers, read a **bounded fixed number of bytes** with an explicit cap rather than relying on `available()`: `available()` only estimates bytes readable/skippable without blocking, **not total stream length**.

## 9. Safe Lookahead Patterns by Processing Direction

### 9.1. Bounded Byte Header

~~~java
// Fragment inside a method that can throw IOException.
// source is an InputStream not consumed outside the wrapper.
try (BufferedInputStream in = new BufferedInputStream(source)) {
    if (!in.markSupported()) {
        throw new IllegalStateException("Missing mark/reset");
    }

    in.mark(4);
    int b1 = in.read();
    int b2 = in.read();
    // b1/b2 may be -1; check for EOF before comparing header bytes.
    boolean gzip = b1 == 0x1F && b2 == 0x8B;
    in.reset();

    if (gzip) {
        // Pass 'in' to the appropriate gzip handler layer.
    } else {
        // Pass 'in' to the alternative format handler layer.
    }
}
~~~

This is a **fragment**, not a standalone program. A 4-byte limit suffices for two peek reads; to sniff more formats, recalculate N and actual bytes read. A production parser must also handle EOF, proper readers, and ownership of the passed stream. If `reset()` fails, **never swallow it and proceed as if the cursor were still unchanged**.

### 9.2. Only Need to Push Back a Few Bytes: `PushbackInputStream`

`PushbackInputStream` can call `unread(byte)` or `unread(byte[],...)` to push bytes back into a pushback buffer. It fits when you have read a small prefix and want to hand that exact prefix back to a consumer, though `markSupported()` remains **false**.

~~~java
// Fragment: source is an InputStream; try-with-resources manages the resource.
try (PushbackInputStream in = new PushbackInputStream(source, 2)) {
    int first = in.read();
    if (first != -1) {
        in.unread(first); // The next read will return the same byte.
    }
    // Continue processing with 'in', do not switch back to 'source'.
}
~~~

This fragment requires importing `java.io.PushbackInputStream`, declaring/catching `IOException`, and never calling `unread(-1)` at EOF. The pushback buffer capacity must hold the pushed-back data; exceeding capacity causes `unread` to throw `IOException`. Pushback is not equivalent to multi-step mark/reset: it injects specific bytes ahead of the read cursor rather than returning to a saved bookmark.

### 9.3. Need Arbitrary Seeking on Files

- `RandomAccessFile.seek(long)` or `FileChannel.position(long)` lets you reposition on a **file/channel** supporting random access; this is a different mechanism from `InputStream.mark/reset`.
- A file can be reopened and skipped past the prefix to re-read, though that is inefficient for large files and may not reflect the same snapshot if the file is modified.
- Socket streams generally cannot seek; to re-read, use buffering, pushback, or save a bounded header yourself. If unbounded rewinding is required, design a bounded memory/temp-file spool with cleanup.

## 10. Failure Modes and Proper Handling

| Situation | Possible Outcome | How to Handle |
| --- | --- | --- |
| `markSupported() == false` | `mark` may be ignored, `reset` throws `IOException` | Use a supporting wrapper, pushback, or another data structure. |
| Calling `reset` before `mark` | Implementation-dependent: error or special default state | Mark before peeking; never rely on a default. |
| Reading past `readlimit` | Mark may become invalid; some implementations still allow reset | Choose a limit large enough for lookahead; do not treat the limit as a guaranteed failure boundary. |
| Mark/Reset after `close()` | I/O error or no-op mark per class contract | Keep the stream open across the entire peek-and-parse transaction. |
| `BufferedReader.mark(-1)` | `IllegalArgumentException` | Validate lookahead character count; never pass negative numbers. |
| Multiple `mark` calls | Most recent mark replaces the previous one | Design around a single active mark or save data yourself for nested backtracking. |
| Marking a wrapper while reading `source` directly | Logical cursor and buffer data fall out of sync | Have only one consumer use the chosen wrapper. |
| Reading raw UTF-8 bytes and splitting mid-sequence | Corrupted characters if decoded piecemeal | Decode with a stateful Reader; mark at the character layer when parsing text. |
| `readLine` strips newline from its return value | Limit calculation misses consumed `\n` or `\r\n` | Budget `readAheadLimit` in actual code units read, including line terminators. |
| `mark(Integer.MAX_VALUE)` on arbitrary sources | Wrapper may retain a huge buffer | Set explicit protocol caps, reject untrusted input, and choose a proper seek/spool strategy. |

**Error-handling principle:** `markSupported()` only verifies a stream's capability; it **does not eliminate** exceptions on `reset()`, `read()`, or close. In a parser, a rewind failure usually means you are **no longer at the expected position**; falling through to normal processing without fixing the cursor is a bug.

## 11. Distinguishing mark/reset from Easily Confused APIs

| Mechanism | Similarity | Core Difference |
| --- | --- | --- |
| `mark` + `reset` | Peek ahead and return to a checkpoint | Most recent logical checkpoint; conditional replay bound by stream and `readlimit`. |
| `PushbackInputStream.unread` | Re-provides consumed bytes | Caller explicitly pushes **specific bytes** into a buffer, bounded by pushback capacity. |
| `FileChannel.position` / `RandomAccessFile.seek` | Can re-read from an earlier offset | Relies on a random-access source; not constrained by stream-style `readlimit`. |
| `BufferedInputStream` | Caches bytes to reduce source I/O | Buffering does not mean infinite rewind; marking has its own conditions. |
| `BufferedReader` | Caches decoded text | Marks in `char` code units, not encoded byte counts. |
| `available()` | Queries immediately readable data | Does not return position, set a mark, or report total length. |
| `skip(long)` | Advances read position forward | Sets no bookmark; actual bytes skipped may be fewer than requested. |
| `InputStream.transferTo` | Sends bytes to an output | Consumes the stream with no promise of resetting afterward. |

## 12. Self-Check Questions

1. `FileInputStream` returns `markSupported() == false`. Can wrapping it with `BufferedInputStream` make mark/reset work? Why?
2. You mark with `readlimit = 5`, read 7 bytes, and then reset successfully on `ByteArrayInputStream`. Does this violate the contract?
3. Does `reset()` jump to the start of the file or to the most recent `mark` call?
4. A parser uses `BufferedReader` and reads a supplementary emoji after marking. How many `char` units does one emoji normally consume?
5. Why is `readAheadLimit=10` not always enough for `readLine()` to read a 10-character returned string?
6. If someone else reads `FileInputStream` directly while you mark its `BufferedInputStream`, what can go wrong?
7. When you need to push back an exact 2-byte header and the source does not support mark, what options remain?
8. Can you rely on reading byte `readlimit + 1` to assert that every `reset` will throw an exception?

**Suggested answers:**

1. **Yes**; the wrapper retains read bytes for replay without requiring the underlying file stream to seek.
2. **No**; `readlimit` is the threshold beyond which the stream is no longer required to retain the mark, not a mandatory command to erase it.
3. It returns to the most recent valid mark, not automatically to the beginning.
4. Usually **two** UTF-16 code units (`char`), even though it is one code point.
5. `readLine()` may also consume `\n` or `\r\n`, which are omitted from the returned string.
6. The two layers no longer share a consistent logical position; the buffer may already have read ahead from the source.
7. `BufferedInputStream` + mark/reset, `PushbackInputStream` + `unread`, or saving the prefix yourself and coordinating a reader.
8. **No**; the mark may still remain usable depending on the implementation and state.

## 13. Standard API References

- [`InputStream` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html): `mark(int)`, `reset()`, `markSupported()`, and `readlimit` contract bounds.
- [`BufferedInputStream` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/BufferedInputStream.html): buffering, logical mark position, and mark invalidation conditions.
- [`ByteArrayInputStream` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ByteArrayInputStream.html): in-memory stream where mark/reset is always supported.
- [`BufferedReader` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/BufferedReader.html): `mark(int readAheadLimit)` and character-based mark semantics.
- [`Reader` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Reader.html): general reader contract, `mark`, and `reset`.
- [`PushbackInputStream` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PushbackInputStream.html): `unread` and `markSupported() == false`.

**Takeaway:** Check `markSupported()` on the **exact object** being read; call `mark(N)` before lookahead, ensuring N is measured in the right unit and large enough for the replay span; expect `reset()` to possibly throw `IOException`; never interleave raw reads underneath a wrapper; and do not treat mark/reset as unbounded random access.