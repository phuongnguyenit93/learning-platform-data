# `PushbackInputStream` and `PushbackReader`

## Lesson Objectives

When reading data sequentially, a program sometimes needs to **look ahead at a few bytes or characters** to decide which branch to take. If those bytes or characters belong to the next step's input, the program needs to "put them back" for the next read. `java.io.PushbackInputStream` and `java.io.PushbackReader` provide a **small pushback buffer** for this purpose.

After this lesson, you will be able to:

- Distinguish pushback at the **byte** level from the **character** level.
- Use `read()`/`unread()` to look ahead while preserving the exact reading order.
- Understand **fixed capacity**, stack-like re-reading (LIFO for individual `unread` calls), behavior at EOF, and exceptions when the pushback buffer fills up.
- Apply `PushbackReader` for token/delimiter parsing and `PushbackInputStream` for inspecting leading bytes—such as a UTF-8 BOM—on an in-memory stream.
- Compare pushback against `mark()`/`reset()`, `BufferedInputStream`, `BufferedReader`, `ByteArrayInputStream`, and maintaining a lookahead character manually in a parser.
- Recognize the boundary: this is **sequential reading with a small undo buffer**, not an arbitrary file-rewinding mechanism.

## 1. Position in Java I/O

Both classes reside in `java.io` and act as **decorators (wrappers)** around another input source:

```text
Byte source InputStream
    │
    ▼
PushbackInputStream ──► read byte ──► process
    ▲                       │
    └──────── unread(byte) ─┘

Character source Reader
    │
    ▼
PushbackReader ─────► read char ──► parse text
    ▲                       │
    └──────── unread(char) ─┘
```

Underlying sources can include `ByteArrayInputStream`, `FileInputStream`, `BufferedInputStream`, `StringReader`, or `InputStreamReader`.

Pushback classes **never write data backward into the original source**. `unread` merely places bytes or characters into the wrapper's internal buffer. The next `read` pulls from that pushed-back data first before resuming reads from the underlying stream/reader. If the source is a file, the actual file descriptor position is not rewound by `unread`; if the source is a network stream, bytes are not sent back over the socket.

### Pushback Is Not "Rewind"

Suppose the source contains `A B C D`, and the reader consumes `A`, `B`, then calls `unread(B)`, `unread(A)`:

```text
Initial source:       A  B  C  D
Read from source:     A  B          (source cursor is at C)
Pushback buffer:     [A, B]         (A is ready to be read next)
Next reads:           A → B → C → D
```

From the wrapper's perspective, A and B appear again, yet the original source **was never rewound**. For individual `unread(int)` calls, the most recently pushed item is read first (LIFO). If you want to push back a multi-byte or multi-char slice in its **original order**, use `unread(byte[], off, len)` or `unread(char[], off, len)` with sufficient capacity, or push items one by one in reverse order.

## 2. `PushbackInputStream`: Pushing Back Bytes

`PushbackInputStream` extends `FilterInputStream` and wraps an underlying `InputStream`:

| Constructor | Meaning |
|---|---|
| `new PushbackInputStream(in)` | Default pushback buffer of **1 byte** |
| `new PushbackInputStream(in, size)` | Fixed pushback buffer of **`size` bytes**; `size <= 0` is invalid |

Important methods:

| Method | Behavior |
|---|---|
| `read()` | Reads from pushback buffer first; if empty, reads from the underlying source; returns `0..255` or `-1` (EOF) |
| `read(byte[], off, len)` | Reads any available pushback bytes, then reads more from the source per `InputStream` contract |
| `unread(int b)` | Pushes back one byte; the next `read` receives that byte |
| `unread(byte[] b)` | Pushes back an entire byte array, preserving element order when re-read |
| `unread(byte[] b, int off, int len)` | Pushes back slice `b[off..off+len)` |
| `available()` | Estimates bytes readable without blocking, including pushback bytes; **not** total remaining bytes |
| `skip(long n)` | Skips bytes per `InputStream` contract, including pushed-back bytes |
| `close()` | Closes the wrapper and the underlying stream |

`read()` returns **`int`**, even though the data consists of bytes: `0..255` indicates a valid byte, while `-1` indicates end of stream. When calling `unread`, **only unread a byte that was successfully read**, never the `-1` EOF sentinel.

### Example 1 — Peeking Two Bytes and Restoring Them in Order

Save this Java 17 program as **`PushbackByteDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.PushbackInputStream;
import java.nio.charset.StandardCharsets;

public class PushbackByteDemo {
    public static void main(String[] args) throws IOException {
        byte[] source = "ABCDE".getBytes(StandardCharsets.UTF_8);

        try (PushbackInputStream input = new PushbackInputStream(
                new ByteArrayInputStream(source), 2)) {
            int first = input.read();
            int second = input.read();

            System.out.println("peeked: " +
                (char) first + (char) second);

            // unread byte-by-byte: push the last element first.
            input.unread(second);
            input.unread(first);

            byte[] replayed = input.readNBytes(2);
            System.out.println("replayed: " +
                new String(replayed, StandardCharsets.UTF_8));
            System.out.println("remaining: " +
                new String(input.readAllBytes(), StandardCharsets.UTF_8));
        }
    }
}
```

Run:

```bash
javac PushbackByteDemo.java
java PushbackByteDemo
```

Exact output:

```text
peeked: AB
replayed: AB
remaining: CDE
```

**Explanation:** `first` holds the byte code for `A`, and `second` holds the byte code for `B`. To re-read A then B, the program calls `unread(B)` **first** and `unread(A)` **second**. The buffer has capacity 2, so both bytes fit. `readNBytes(2)` (Java 9+) retrieves exactly those two pushed-back bytes in this case; the subsequent read pulls `CDE` from the source. Because the example uses ASCII only, casting bytes to `char` for printing is valid here; **never cast individual UTF-8 bytes to characters** when data is multi-byte.

Use `try-with-resources` to close `PushbackInputStream`; closing the wrapper also closes the underlying `ByteArrayInputStream` (for in-memory streams there are no OS resources to release).

### Pushing Back an Array Instead of Multiple Calls

When looking ahead over a slice:

```java
byte[] prefix = new byte[4];
int n = input.read(prefix, 0, prefix.length);
if (n > 0) {
    input.unread(prefix, 0, n);
}
```

This is an **illustrative snippet**, assuming `input` is a `PushbackInputStream` with pushback capacity of at least 4 and `IOException` is declared or handled. The slice `prefix[0..n)` is pushed back so subsequent reads continue in the **exact original order**. `read(...)` may return **fewer than 4 bytes** even before EOF; real code must loop if a protocol requires waiting for all 4 bytes.

Never call `input.unread(prefix, 0, 4)` when `n` is only 2: doing so injects uninitialized bytes that were never read from the source into the stream.

## 3. `PushbackReader`: Pushing Back UTF-16 `char`s

`PushbackReader` extends `FilterReader` and wraps a `Reader`:

| Constructor | Meaning |
|---|---|
| `new PushbackReader(reader)` | Default pushback buffer of **1 `char`** |
| `new PushbackReader(reader, size)` | Fixed buffer capable of holding **`size` `char` units** |

Corresponding methods:

- `read()` reads one `char` unit and returns it as an `int` (`0..65535` or `-1` for EOF).
- `read(char[], off, len)` reads a slice of characters.
- `unread(int c)`, `unread(char[] c)`, `unread(char[] c, int off, int len)` push back previously read characters.
- `ready()` indicates whether the buffer/reader is ready to be read; do not treat its result as a guarantee that an entire line of input is available.
- `close()` closes the wrapper and the underlying reader.

Important: `Reader` operates on **UTF-16 `char` code units**, not automatically on grapheme clusters or Unicode code points. For example, the emoji 😀 uses **two `char`s** in a `String`. If a parser reads per `char`, it must handle surrogate pairs when the language grammar operates on code points.

`PushbackReader` is well suited when a text parser needs to inspect a character to decide: "this character belongs to the next token; I must put it back." It does **not** reverse byte decoding inside an `InputStreamReader`.

### Example 2 — Peeking Delimiters While Tokenizing

Save **`PushbackCharDemo.java`**:

```java
import java.io.IOException;
import java.io.PushbackReader;
import java.io.StringReader;

public class PushbackCharDemo {
    private static String readToken(PushbackReader reader)
            throws IOException {
        StringBuilder token = new StringBuilder();
        int ch;

        while ((ch = reader.read()) != -1) {
            if (ch == ',') {
                reader.unread(ch); // The next token will handle the delimiter.
                break;
            }
            token.append((char) ch);
        }
        return token.toString();
    }

    public static void main(String[] args) throws IOException {
        try (PushbackReader reader = new PushbackReader(
                new StringReader("alpha,beta"), 1)) {
            String first = readToken(reader);
            int delimiter = reader.read();
            String second = readToken(reader);

            System.out.println("first: " + first);
            System.out.println("delimiter: " + (char) delimiter);
            System.out.println("second: " + second);
        }
    }
}
```

Run:

```bash
javac PushbackCharDemo.java
java PushbackCharDemo
```

Output:

```text
first: alpha
delimiter: ,
second: beta
```

During the first `readToken` call, the parser reads the comma and sees it is not part of the token content. `unread(',')` lets the caller read that comma itself. After the caller consumes the delimiter, the parser proceeds to read `beta`. Because only one delimiter character needs to be peeked, a **1-character** buffer suffices.

This is a simple ASCII parser example. In real CSV files, commas can appear inside quoted fields, quotes can be escaped, CRLF line endings occur, and many other rules apply. Do not use `readToken` above as a complete CSV parser.

## 4. The Pushback Buffer Has a Fixed Capacity

When constructed:

```java
PushbackInputStream bytes = new PushbackInputStream(source, 2);
PushbackReader chars = new PushbackReader(reader, 2);
```

This is an **illustrative snippet**, where `source` is an `InputStream` and `reader` is a `Reader`. A wrapper created with capacity 2 has at most **2 free slots for `unread`** and never grows automatically.

Example (illustrative only):

```java
PushbackInputStream pb = new PushbackInputStream(source, 1);
int a = pb.read();
int b = pb.read();
pb.unread(b); // One pushback slot is now occupied.
pb.unread(a); // IOException: pushback buffer is full.
```

Do not match against the error message string `"push back buffer is full"` in business logic; handle `IOException` properly and size the buffer appropriately. To peek up to N bytes, allocate capacity of at least N **whenever all N bytes might need to be pushed back**. The minimum valid capacity for `(source, size)` is 1.

Calling `read()` consumes a pushed-back byte and frees a slot for another `unread()`. The buffer only needs to hold **currently unread-back items**; it does not have to hold all bytes ever read by the program.

### LIFO Order and Array Unread

Suppose you read A then B:

| Operation | Next Two Items Read |
|---|---|
| `unread(B)` then `unread(A)` | A, B |
| `unread(A)` then `unread(B)` | B, A |
| `unread(new byte[]{'A', 'B'})` | A, B |

With `PushbackReader`, the exact same principle applies to `char[]`. `unread(byte[])` preserves order because the API pushes back **the entire slice** in sequence; you do not have to reverse the array yourself beforehand.

Do not confuse a **pushback buffer** with a **read buffer for performance**. A pushback buffer exists for lookahead correctness; the buffer in `BufferedInputStream`/`BufferedReader` reduces small reads against the underlying source. An application can use both buffers together, provided the wrapper ordering is understood.

## 5. Byte Lookahead Use Case: UTF-8 BOM

A practical scenario is checking the leading three bytes `EF BB BF` (UTF-8 BOM). If the format permits a BOM, the program can skip those exact three bytes; if there is no BOM, it must **push back the probed bytes** so the text does not lose its opening characters.

```text
                  Read up to 3 leading bytes
                        │
             ┌──────────┴───────────┐
             │                      │
      Matches EF BB BF          Not a BOM
             │                      │
      Discard 3 bytes        unread exact count
             │               of bytes read (0..3)
             └──────────┬───────────┘
                        ▼
               Decode the remainder
                     as UTF-8
```

Because a **BOM is byte-level**, `PushbackInputStream` is the right tool. `PushbackReader` operates **after decoding** and cannot undo bytes already consumed by a decoder. Do not apply the three-byte UTF-8 BOM rule to UTF-16 or UTF-32: those encodings have different BOMs, endianness rules, and byte lengths.

### Example 3 — Reading an Optional BOM Without Losing the Prefix

Save **`Utf8BomPushbackDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.PushbackInputStream;
import java.nio.charset.StandardCharsets;

public class Utf8BomPushbackDemo {
    private static String decodeOptionalBom(byte[] data)
            throws IOException {
        try (PushbackInputStream input =
                 new PushbackInputStream(
                     new ByteArrayInputStream(data), 3)) {
            byte[] prefix = new byte[3];
            int count = 0;

            // Read byte-by-byte to handle even very short sources accurately.
            while (count < prefix.length) {
                int next = input.read();
                if (next == -1) {
                    break;
                }
                prefix[count++] = (byte) next;
            }

            boolean isBom = count == 3
                && (prefix[0] & 0xff) == 0xEF
                && (prefix[1] & 0xff) == 0xBB
                && (prefix[2] & 0xff) == 0xBF;

            if (!isBom) {
                // Push back the exact bytes read, in order.
                input.unread(prefix, 0, count);
            }

            return new String(
                input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    public static void main(String[] args) throws IOException {
        byte[] plain =
            "Xin chào".getBytes(StandardCharsets.UTF_8);
        byte[] withBom = new byte[3 + plain.length];
        withBom[0] = (byte) 0xEF;
        withBom[1] = (byte) 0xBB;
        withBom[2] = (byte) 0xBF;
        System.arraycopy(
            plain, 0, withBom, 3, plain.length);

        System.out.println("plain: " + decodeOptionalBom(plain));
        System.out.println("with BOM: " + decodeOptionalBom(withBom));
        System.out.println(
            "empty: [" + decodeOptionalBom(new byte[0]) + "]");
    }
}
```

Run with Java 17+:

```bash
javac Utf8BomPushbackDemo.java
java Utf8BomPushbackDemo
```

Output:

```text
plain: Xin chào
with BOM: Xin chào
empty: []
```

The program reads up to three bytes. When **there is no BOM**, `unread(prefix, 0, count)` preserves every byte peeked, even for 1- or 2-byte inputs. When a BOM matches, the program does not push back those three bytes and proceeds to decode the rest. When input is empty, `count == 0` and nothing is pushed back.

**Limitation of this example:** `readAllBytes()` loads all remaining data into memory; this is fine for demonstrating with `ByteArrayInputStream`, not as a default for huge files or network streams. If continuous streaming is needed, after BOM detection wrap with `InputStreamReader(input, StandardCharsets.UTF_8)` and `BufferedReader` to read incrementally. A strict decoder can use `StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)`; `new String(bytes, UTF_8)` substitutes invalid bytes with replacement characters per its contract. Strip a BOM only when the format permits it; some protocols mandate UTF-8 **without a BOM**.

### Read Boundaries Are Not UTF-8 Character Boundaries

For UTF-8 text with Vietnamese diacritics or emojis, a single character can span 2–4 bytes. `PushbackInputStream` sees only raw bytes and does not understand Unicode. If you read just the first byte of an emoji and treat it as a complete character, decoding breaks. For text content, typically place an `InputStreamReader` to handle the charset, and wrap `PushbackReader` on top to look ahead at decoded characters.

Never split "messages" by the byte count returned by each socket `read()`: one message can span multiple reads, and multiple messages can arrive in a single read. Pushback only helps with **local lookahead** and does not replace a properly framed protocol parser.

## 6. How Does `mark()/reset()` Differ from Pushback?

Many applications need short lookahead; besides pushback, Java offers **mark and reset**:

| Mechanism | How It Works | Best Fit |
|---|---|---|
| `PushbackInputStream` / `PushbackReader` | After reading, call `unread` to place **chosen data** into a front-of-stream buffer of fixed capacity | Peeking a few bytes/characters, detecting prefixes/delimiters |
| `BufferedInputStream.mark(readlimit)` / `reset()` | Remembers a logical position and returns to it while the mark remains valid | Trial-reading a section and rewinding to the mark |
| `BufferedReader.mark(readAheadLimit)` / `reset()` | Same concept for characters | Parsers needing to rewind to a marked character position |
| Storing the read value in a `lookahead` variable | The parser holds the next character itself without unreading | Parsers with state machines or complex tokenizing |
| `ByteArrayInputStream` / `StringReader` | In-memory sources with built-in mark/reset | Small inputs already loaded completely in memory |
| `SeekableByteChannel` / `RandomAccessFile` | Re-reads at arbitrary offsets when the source supports seeking | Files requiring random access |

**`PushbackInputStream` and `PushbackReader` do not support `mark/reset`**: `markSupported()` returns `false`; `reset()` throws `IOException`; `mark(...)` does not enable rewinding. Never call `mark()` "just in case" on a pushback wrapper expecting `reset()` to bail out the parser. Pick **one lookahead mechanism** suited to your needs.

An important difference: `mark/reset` always returns to **a previously marked position**, whereas `unread` lets you insert **specific bytes or characters**. A program could even `unread` values different from what it originally read; the API allows injecting values into the buffer, though doing so synthesizes new stream data rather than rewinding. Keep **stream transformation** logic separate from **peek-and-unread-original-data** logic.

### Regarding In-Memory Data Sources

`ByteArrayInputStream` and `StringReader` already provide mark/reset support. If all data is already in memory and you merely need to re-read from an earlier position, an extra pushback wrapper is often unnecessary. Still, pushback remains handy when you want one uniform parser interface across both in-memory sources and **non-seekable** file or network streams.

For complex parsers requiring deep lookahead, a lexer/token stream with its own cursor, state, and clear bounds is far easier to maintain than continually enlarging a pushback buffer.

## 7. Combining `PushbackInputStream` and `PushbackReader` with Other Buffers

Wrapper ordering affects behavior:

```text
Raw byte stream
    ↓
BufferedInputStream         (improves byte read efficiency)
    ↓
PushbackInputStream         (byte lookahead, e.g., header check)
    ↓
InputStreamReader(UTF-8)    (decodes byte → char)
    ↓
PushbackReader              (char lookahead, e.g., delimiter parsing)
    ↓
Parser
```

This is a **conceptual diagram**, not a mandatory stack. Not every parser needs both pushback layers. For pure text parsing, `InputStreamReader` + `PushbackReader` or `BufferedReader` + a state machine usually suffices. If you must inspect a byte-level BOM, peek via `PushbackInputStream` **before** constructing the decoder.

When pushing back at the byte level, the layer receiving `unread` must be the exact wrapper through which the next read flows. If an outer `BufferedInputStream` has already prefetched bytes into its own buffer, calling `unread` on an inner pushback stream may not surface those bytes on the next read from the outer buffered stream. Define wrapper ownership clearly and never mix direct reads on the underlying stream once a wrapper is in place.

### Readers and Byte Streams Should Not Alternate Arbitrarily

Once `InputStreamReader` reads bytes from an underlying stream, its decoder may hold internal buffers and state. If one piece of code reads characters through the reader while another reads bytes directly or pushes back onto the stream beneath the reader, the byte/character alignment easily breaks.

Choose one clear point of control:

- **Handle protocol/header bytes first**, finish any peek/unread steps, and only then hand off to the decoding reader.
- **Process character content** through a single reader, wrapping `PushbackReader` over that reader if lookahead is needed.
- If both byte-level and character-level parsing are needed, define the transition boundary explicitly and **never interleave** both read paths on the same source.

Especially with Unicode, each `PushbackReader.read()` returns **one UTF-16 code unit**, not necessarily a full Unicode code point. Code points outside the BMP span two `char`s; the parser must handle them as a pair if the grammar operates on code points.

## 8. EOF, I/O Errors, and Resource Lifecycles

### EOF Is Not a Byte or Character to Unread

`read()` returns `-1` when no more data exists. `unread(-1)` is **not a command to "put EOF back"**; it can insert a byte or character derived from the lower bits of `-1` into the buffer, corrupting the stream. Always check:

```java
int next = input.read();
if (next != -1) {
    input.unread(next);
}
```

This illustrative snippet assumes `input` is a `PushbackInputStream` with buffer room available and `IOException` handled. The same `-1` check applies to `PushbackReader`.

Even if the underlying source has already reached EOF, you **can still read newly pushed-back valid bytes/characters** before `read()` returns `-1` again. Thus "having seen EOF once" does not guarantee every subsequent wrapper read returns `-1` if the application pushes data back afterward.

### `read(byte[])` May Return Fewer Bytes Than Requested

With files, networks, or multi-layered buffered streams, `read(buffer, off, len)` is not guaranteed to fill all `len` bytes in one call. If a parser needs an exact N-byte header, loop until N bytes arrive, EOF occurs, or an error is raised, while bounding wait time/length against incomplete inputs. `InputStream.readNBytes(n)` reads up to `n` bytes, though it can still return fewer at EOF. For text, `Reader.read(char[], off, len)` must likewise handle partial reads and EOF.

### `IOException`, Buffer Overflow, and Closing Resources

`unread` can throw `IOException` if the buffer lacks space or the stream/reader is closed. Read calls can also propagate errors from the underlying source. In production code:

1. Determine the **maximum number of bytes/characters of lookahead** so you allocate sufficient capacity.
2. Call `unread` **only with data successfully read**, in the proper order.
3. Check for EOF and partial reads.
4. Manage the resource-owning wrapper with `try-with-resources`.
5. Never share the same wrapper across multiple reader/writer threads without explicit synchronization and ownership design.

Closing `PushbackInputStream`/`PushbackReader` also closes the underlying source. If the source is `System.in` or a shared reader, do not wrap it in a closing scope carelessly without understanding ownership, as doing so can break reads elsewhere in the program.

## 9. Common Mistakes

### Mistake 1: Creating the Default 1-Byte Buffer and Unreading More

```java
PushbackInputStream pb = new PushbackInputStream(source);
pb.unread(new byte[] {0x01, 0x02}); // IOException because only 1 slot exists.
```

This is an **anti-pattern**, assuming `source` is an `InputStream` and `IOException` is handled. If the parser needs two bytes of lookahead, use `new PushbackInputStream(source, 2)`. Do not expect Java to resize the buffer automatically.

### Mistake 2: Unreading Multiple Single Items in Read Order

If you read A then B and call `unread(A)` followed by `unread(B)`, the next reads return **B, A**. To restore A before B, call `unread(B)` then `unread(A)`, or call `unread(new byte[]{'A', 'B'})` when space permits.

### Mistake 3: Relying on `mark/reset` on a Pushback Wrapper

Both pushback wrappers report `markSupported() == false`. `reset()` does not substitute for `unread`. If you need to return to a marked position, pick a wrapper supporting marks or manage an explicit cursor.

### Mistake 4: Reading Unicode Bytes and Casting Them to `char`

Many UTF-8 code points take multiple bytes—for example, `é` is `C3 A9`. Two bytes are not two standalone characters. Decode **only after** assembling the proper byte sequence or use a streaming decoder/`Reader`. `PushbackReader` works post-decode and fits character-based syntax.

### Mistake 5: Checking for a BOM and Losing Leading Bytes

Probing 3 bytes and discarding them when they do not match `EF BB BF` drops the first three bytes of real content. You must `unread` the exact count of bytes read, even when the source has only 1–2 bytes. Never use `available()` as total file length or as a check that a full header has arrived.

### Mistake 6: Stacking Wrappers in the Wrong Order and Mixing Underlying Reads

If a parser reads from an outer `BufferedInputStream` while code calls `unread` on an inner `PushbackInputStream`, pushed-back bytes may not appear immediately because the outer buffer still holds prefetched data. Never read directly from `source` while also reading through a wrapper over `source`; avoid bypassing buffered data.

### Mistake 7: Treating Pushback as a "Seek" Feature

Pushback does not move a file position backward, roll back network protocol state, or allow unbounded rewinding. When arbitrary offset access in a file is required, use `SeekableByteChannel`/`FileChannel` or `RandomAccessFile`.

### Mistake 8: Parsers Missing Malformed or Truncated Input Handling

Headers may be truncated, delimiters may never appear, text may contain unpaired surrogates or invalid UTF-8 bytes. Pushback does not validate any of those conditions. Always validate formats, bound memory and read time, and handle `IOException`/EOF cleanly.

### Mistake 9: Adding Pushback to Every Stream Thinking It Speeds Things Up

Pushback is a **lookahead control mechanism**, not a general I/O performance optimization. For ordinary sequential reading, `BufferedInputStream`, `BufferedReader`, or block reads are better choices. Add pushback only when logic genuinely needs to put data back.

## 10. Selection Decision Table

| Need | API to Consider | Reason |
|---|---|---|
| Peek the first 1–4 bytes of a binary protocol | `PushbackInputStream` with sufficient capacity | Push back prefix if it does not match magic/header |
| Check for a UTF-8 BOM before decoding | `PushbackInputStream`, then `InputStreamReader` | BOM detection happens at the byte level |
| Peek delimiters while tokenizing text | `PushbackReader` | Operates on decoded characters |
| Tokenizer with complex grammar and deep lookahead | Parser maintaining its own token/cursor state | Easier to express state and backtracking |
| Trial-read and return to a marked position | `BufferedInputStream.mark/reset`, `BufferedReader.mark/reset` | Built specifically for positional marks |
| Small data already in a byte array | `ByteArrayInputStream` with cursor/mark | Fewer wrappers; still use pushback if a parser API requires it |
| Seek to arbitrary file offsets | `FileChannel.position`, `SeekableByteChannel` | Real positional access, not a pushback buffer |
| Ordinary line-by-line text reading | `BufferedReader.readLine` | No manual lookahead needed when line-delimited |
| Reading UTF-8 characters across chunks | `InputStreamReader`/streaming decoder | Preserves charset state instead of decoding isolated bytes |

## 11. Self-Check Exercises

**Question 1.** A source contains `XYZ`. You read X and Y, then call `unread(X)` and `unread(Y)` on a large enough buffer. What are the first two characters read next?

**Answer:** Y then X. Single-item `unread` calls behave in LIFO order. To read X then Y, call `unread(Y)` first.

**Question 2.** By default, how many `char`s can `new PushbackReader(reader)` push back at once?

**Answer:** 1 `char`. When more is needed, specify `size` in the constructor.

**Question 3.** Why is calling `unread(-1)` after EOF wrong?

**Answer:** `-1` is the end-of-data sentinel, not a read byte or character. `unread` pushes a value derived from `-1` into the buffer, injecting bogus data.

**Question 4.** Why should you not use `PushbackReader` to inspect the three bytes `EF BB BF`?

**Answer:** `PushbackReader` operates on characters **after decoding**; those three values are UTF-8 BOM bytes. Detect them at the byte level with `PushbackInputStream` before constructing the reader.

**Question 5.** If a `PushbackInputStream` has capacity 3 and `read` returns 2 bytes, can you call `unread(prefix, 0, 2)` and re-read them?

**Answer:** Yes, provided the buffer is currently empty and not closed. The two re-read bytes preserve the exact order from `prefix`.

**Question 6.** What does `PushbackInputStream.markSupported()` return? Does `reset()` return the stream to the start of a trial read?

**Answer:** `false`. `reset()` throws `IOException`; use `unread` or choose a wrapper that supports mark/reset.

**Question 7.** Why should `PushbackInputStream` not be used as a large read buffer?

**Answer:** Its purpose is strictly to push back **a small amount of lookahead data**; its buffer has fixed capacity and does not replace performance buffering strategies or framed streaming parsers.

**Key takeaway:** `PushbackInputStream` pushes back **bytes**, and `PushbackReader` pushes back **`char`s**. Both place data into a small buffer at the **front of the wrapper**, never writing backward into the source and never supporting `mark/reset`. Size the buffer for your lookahead depth, handle `unread` ordering, EOF, and charsets carefully, and use these classes when a parser needs short lookahead while continuing to read sequentially through a standard stream interface.
