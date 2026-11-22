# SequenceInputStream: Concatenating Multiple Byte Sources in Java I/O

## 1. Purpose and Scope

`java.io.SequenceInputStream` represents **a single input byte stream formed by sequentially concatenating multiple `InputStream` instances**. When reading reaches the end of the first source, it switches to the next source; external consuming code only interacts with **one** `InputStream`.

This topic belongs to the **In-Memory I/O** section of Core Java. The primary examples use `ByteArrayInputStream` to illustrate the concatenation mechanism clearly; the same principle works with file streams and other byte sources when resources are managed carefully.

After this lesson, you will be able to:

- Distinguish **sequential concatenation** from interleaving, merging, or reading multiple streams in parallel.
- Use both constructors: `SequenceInputStream(InputStream, InputStream)` and `SequenceInputStream(Enumeration<? extends InputStream>)`.
- Explain when `read()` returns EOF, when it switches sources, how empty sources behave, and how `close()` handles component streams.
- Concatenate binary data and UTF-8 bytes without implicitly inserting delimiters or corrupting multi-byte sequences.
- Choose bounded-memory reading/writing strategies for large data rather than overusing `readAllBytes()` or `ByteArrayOutputStream` when source sizes are unknown upfront.
- Identify scenarios where `SequenceInputStream` should not be used and how to handle I/O errors, resource lifecycles, and concurrent sources.

**Core idea:** `SequenceInputStream` is an ordered, **read-only InputStream** that yields the exact byte sequence as if the bytes of each source were placed end-to-end. It has no awareness of file formats, characters, records, delimiters, or protocols.

## 2. How Does Sequential Concatenation Work?

Suppose there are three sources:

```text
InputStream A: [10, 20]
InputStream B: []          (empty source)
InputStream C: [30, 40]

SequenceInputStream:
   A hits EOF -> closes A, switches to B
   B hits EOF -> closes B, switches to C
   C hits EOF -> closes C, all sources exhausted

Read result: [10, 20, 30, 40]
```

Switching to the next source happens when reading hits **EOF on the current source**, not when a single `read(byte[])` call returns fewer bytes than requested. In Java, `InputStream.read()` returns a value from 0 to 255 when a byte is read; only `-1` signals end of data. With `read(byte[], off, len)`, the return value is the actual number of bytes received (or `-1` at EOF when the requested length is non-zero). Never assume a single `read(byte[])` call always fills the array.

### 2.1. Key Characteristics to Remember

| Characteristic | `SequenceInputStream` |
| --- | --- |
| Data type | **Bytes**; every byte keeps its exact value |
| Ordering | Reads all of source 1, then source 2, 3, ... |
| Interleaving | No; no round-robin or time-based merging |
| Auto-inserted separators | No; adds no spaces, newlines, headers, or metadata |
| Auto encoding/decoding | No; attach a reader/decoder at the proper boundary for text |
| Auto total-length discovery | No; the combined stream only knows EOF after exhausting all sources |
| Read state | Forward-only; does not support rewinding in general |
| Concurrency | Does not read sources in parallel for higher throughput |
| Closing sources | Closes each component input stream upon exhaustion or when the combined stream is closed |
| Blocking source behavior | May block on the current source; provides no built-in timeout |
| API type | Extends `InputStream`, usable with any API accepting `InputStream` |

A key detail about **empty data**: if a source has zero bytes, it is skipped as soon as EOF is detected; subsequent sources are still read normally. Once no sources remain, `SequenceInputStream.read()` returns `-1`.

### 2.2. Is Combined Data Necessarily a Valid File?

**Not necessarily.** Byte concatenation yields an accurate sequence of bytes in order, yet the resulting format may no longer be valid if the pieces are standalone files:

- Concatenating two UTF-8 text files can yield readable text if structured appropriately, but it **does not insert a newline** between the two files.
- Concatenating *byte fragments split from the same binary file* can reconstruct the original file accurately.
- Concatenating two standalone ZIP, PNG, PDF, or compressed files does not automatically produce a valid "merged file"; that depends on format structure and what the reader expects.
- For protocols with headers, checksums, lengths, frames, or boundaries, raw byte concatenation can break boundaries; dedicated framing/encoding rules are required.

## 3. Two Constructors and Source Ownership

### 3.1. Concatenating Exactly Two `InputStream`s

```java
InputStream joined = new SequenceInputStream(first, second);
```

Here `first` and `second` are two already-created `InputStream`s. When reading, the order is always **first then second**. The two component streams may be `ByteArrayInputStream`, `FileInputStream`, streams from `Files.newInputStream(...)`, or any other byte source.

A common usage pattern:

```java
try (InputStream joined =
        new SequenceInputStream(first, second)) {
    // Read from joined until EOF.
}
```

**This is an illustrative snippet:** `first` and `second` must be created beforehand, and error handling when opening the sources must be defined where those sources are opened.

`SequenceInputStream` takes ownership of the sources it receives under the stream-closing contract: when one source runs dry, it closes the finished source and moves to the next; calling `close()` on the combined stream closes the current source and any remaining sources in the sequence. Therefore, once ownership is handed to the combined stream, treat the combined stream as the resource to close. Avoid reusing the underlying sources after handing them over.

### 3.2. Concatenating Multiple Sources via `Enumeration`

The second constructor:

```java
SequenceInputStream joined =
        new SequenceInputStream(enumerationOfInputStreams);
```

`enumerationOfInputStreams` has type `Enumeration<? extends InputStream>`. Each source is pulled in the order returned by `Enumeration.nextElement()`. Whether there are 3, 10, or 100 sources, the external consumer still sees a single `InputStream`.

Java can adapt a `List` to an `Enumeration` via `Collections.enumeration(list)`:

```java
// Illustrative; first, second, third are already-created InputStreams.
java.util.List<java.io.InputStream> sources =
        java.util.List.of(first, second, third);
java.util.Enumeration<java.io.InputStream> inputs =
        java.util.Collections.enumeration(sources);

try (java.io.SequenceInputStream joined =
        new java.io.SequenceInputStream(inputs)) {
    // Read all sources in exact list order.
}
```

Chunks are concatenated **in the order supplied**; if order matters, establish that order in the input collection. Never iterate over an unordered collection and casually assume the order is right.

**Important when handling many files:** if you eagerly open thousands of streams before constructing the `Enumeration`, you may hold thousands of file descriptors open simultaneously and must handle failures occurring partway through initialization. `SequenceInputStream` only reads sequentially; it does not solve opening large batches of files efficiently. See alternatives in Section 8.

## 4. Java 17+ Example: Joining Two Byte Fragments Containing Multi-Byte UTF-8

This is an important scenario: the Unicode string `A😀B` encoded in UTF-8 takes **6 bytes** (1 byte for `A`, 4 bytes for the emoji, and 1 byte for `B`). We intentionally split the bytes right in the **middle** of the emoji and rejoin them using `SequenceInputStream`. The correct approach is to join the bytes first and decode text afterward.

Save the following program to **`SequenceInputStreamDemo.java`** using UTF-8 source encoding:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.SequenceInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class SequenceInputStreamDemo {
    public static void main(String[] args) throws IOException {
        byte[] original = "A😀B".getBytes(StandardCharsets.UTF_8);

        // Index 3 falls in the middle of the emoji's encoded byte sequence.
        byte[] part1 = Arrays.copyOfRange(original, 0, 3);
        byte[] part2 = Arrays.copyOfRange(
                original, 3, original.length);

        try (InputStream joined = new SequenceInputStream(
                new ByteArrayInputStream(part1),
                new ByteArrayInputStream(part2))) {

            byte[] result = joined.readAllBytes();
            System.out.println("Bytes: " + result.length);
            System.out.println("Match: " + Arrays.equals(original, result));
            System.out.println("Text: "
                    + new String(result, StandardCharsets.UTF_8));
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 SequenceInputStreamDemo.java
java SequenceInputStreamDemo
```

**Exact stdout:**

```text
Bytes: 6
Match: true
Text: A😀B
```

**Explanation:**

1. `getBytes(StandardCharsets.UTF_8)` produces 6 bytes. `part1` receives the first three bytes, and `part2` receives the last three bytes.
2. `ByteArrayInputStream` reads directly from an existing byte array in memory; the two parts act as separate byte sources.
3. `SequenceInputStream` emits the bytes of `part1` followed immediately by the bytes of `part2`, dropping no bytes and inserting no characters between them.
4. `Arrays.equals` returns `true` because the byte order matches the original exactly.
5. Only after the data is joined does `new String(result, UTF_8)` decode the complete UTF-8 sequence into `A😀B`.

If instead you decoded each UTF-8 fragment separately and concatenated two `String`s, splitting inside a code point's byte sequence would produce replacement characters or decoding errors depending on the decoder. For byte-fragmented text data, **decode over the joined byte stream** or after restoring the full byte sequence.

**Limitation of this example:** `readAllBytes()` keeps the entire result in RAM, which fits this tiny example. For large sources, read in chunks or use `transferTo` into a destination that does not accumulate everything in memory.

## 5. Java 17+ Example: Joining Multiple Sources and Transferring Bytes Without a Loop

This example uses an `Enumeration` of three byte sources; the middle source is empty to test source switching and confirm no delimiter is inserted automatically. The destination is a `ByteArrayOutputStream` so we can inspect the result directly in memory.

Save to **`MultiSourceSequenceDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.SequenceInputStream;
import java.io.IOException;
import java.util.Arrays;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;

public class MultiSourceSequenceDemo {
    public static void main(String[] args) throws IOException {
        List<InputStream> parts = List.of(
                new ByteArrayInputStream(new byte[] {1, 2}),
                new ByteArrayInputStream(new byte[0]),
                new ByteArrayInputStream(new byte[] {3, 4, 5})
        );
        Enumeration<InputStream> sources =
                Collections.enumeration(parts);

        try (InputStream joined = new SequenceInputStream(sources);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            long transferred = joined.transferTo(output);

            System.out.println("Transferred: " + transferred);
            System.out.println("Result: "
                    + Arrays.toString(output.toByteArray()));
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 MultiSourceSequenceDemo.java
java MultiSourceSequenceDemo
```

**Stdout:**

```text
Transferred: 5
Result: [1, 2, 3, 4, 5]
```

Here `transferTo` (available on `InputStream` since Java 9) forwards bytes to an `OutputStream` and returns the **total number of bytes transferred**. The empty source emits no values and does not halt reading of subsequent sources. The result is printed using `Arrays.toString` so you can verify both order and element count.

**Important distinction:** `ByteArrayOutputStream` accumulates all bytes in RAM, which is fine for lessons and small bounded data. If sources are large or come from a network, swap the target for a file stream, socket stream, or streaming sink and enforce quotas where needed. `transferTo` does not impose a byte limit on its own.

## 6. Managing EOF, `close()`, and Exceptions

### 6.1. When Is a Source Closed?

When `SequenceInputStream` finishes reading a source, it moves to the next source and closes the exhausted one. When the combined stream itself is closed, any remaining managed streams are also closed per the class contract. This differs from manually creating and holding a list of independent `InputStream`s and forgetting to close each one.

Keep two cases in mind:

- **Reading to completion:** as each EOF is reached, used sources are closed and the next source is selected. When no sources remain, the combined stream returns EOF.
- **Early exit / exceptions:** aborting midway **without closing** the combined stream can leak file handles or network streams. Wrap the combined stream in `try-with-resources`, even if you intend to read only part of the data.

The `ByteArrayInputStream` instances in our examples hold bytes in memory, so their `close()` calls do not release OS file handles. With `FileInputStream` or network streams, proper closing is especially critical.

### 6.2. Responsibility When Source Creation Fails Midway

Suppose you want to join two files as follows:

```java
// Illustrative idea; risks leaking a resource if opening the second file fails.
InputStream first = Files.newInputStream(path1);
InputStream second = Files.newInputStream(path2);
InputStream joined = new SequenceInputStream(first, second);
```

This is **not a safe complete pattern**: if opening `path2` throws `IOException`, `first` is already open but has not yet been handed to the combined stream; the code must ensure `first` is closed when the second step fails. With real files, wrap each source in `try-with-resources` as it is opened or use a helper that cleans up on failure; define clear closing responsibility so no handle is left behind.

A **simple, reliable** approach when you just need to concatenate multiple files (without requiring a single combined `InputStream`) is to process each file in a loop and close each source right after transferring it—see Section 8. For large numbers of sources, that also avoids holding too many files open simultaneously.

### 6.3. Behavior When Reading a Source Fails

If `read()` on a component stream throws `IOException`, reading from `SequenceInputStream` will fail. Do not assume it will "skip the broken source" like an empty source and automatically move on to the next one. When data integrity matters, treat an error as a failure: avoid publishing an incomplete concatenated file or reporting success.

If the destination writer throws during `transferTo`, the destination may already contain **partial bytes**. `SequenceInputStream` does not provide transactions, rollback, checksums, or atomic replacement. When protecting destination files, write to a temporary file, verify byte count/checksum/format, and then apply an appropriate publishing strategy.

### 6.4. Do Not Rely on `available()` to Determine Total Bytes

`InputStream.available()` estimates how many bytes can be read from the stream without blocking at that moment; it is **not a measure of total capacity across all sources** and not an EOF signal. A value of 0 does not prove input is exhausted. With `SequenceInputStream`, stop the read loop only when `read()`/`read(byte[])` signals EOF per contract.

## 7. Streaming Reads and Memory Limits

`SequenceInputStream` merely provides a concatenated view over streams. It does not force the application to hold every byte. Still, actual memory usage depends on both the **sources** and the **destination**:

| Pipeline | Memory Characteristics |
| --- | --- |
| Two `ByteArrayInputStream`s over existing `byte[]`s | Bytes are already in RAM prior to joining; `SequenceInputStream` does not merge them into one big array |
| `SequenceInputStream` → `readAllBytes()` | Allocates an in-RAM result sized to all read data; unsuitable for unbounded input |
| `SequenceInputStream` → `ByteArrayOutputStream` | Output accumulates all data in RAM |
| `SequenceInputStream` → `Files.newOutputStream(...)` via `transferTo` | Transfers in chunks without holding every byte in RAM |
| Many pre-opened files in a `List<InputStream>` | Holds many file descriptors simultaneously regardless of individual file sizes |
| Multiple network streams | May block on reads; requires protocol-level quotas, timeouts, and cancellation |

### 7.1. When to Use `transferTo`?

In Java 17+, if you only need to **forward all bytes** to an `OutputStream`, you can write:

```java
// Illustrative; input is an open SequenceInputStream;
// output is an open OutputStream.
long copied = input.transferTo(output);
```

This method transfers bytes in chunks and returns the total bytes written, yet it reads **all the way to EOF** and enforces no quota, timeout, or destination policy. If your problem requires a size cap, enforce it before or during transfer so the threshold is never exceeded; checking `copied` after the transfer finishes does not prevent the destination from already receiving too many bytes.

### 7.2. Chunked Reading When Processing Data

If you want to compute a checksum or process chunks in a controlled loop, reading in blocks is clear and explicit:

```java
// Illustrative: input and output must be managed with try-with-resources.
byte[] buffer = new byte[16 * 1024];
int count;
while ((count = input.read(buffer)) != -1) {
    if (count > 0) {
        output.write(buffer, 0, count);
    }
}
```

`count` can be smaller than the buffer size, especially near the end of a source or the end of the sequence. Pass **exactly `count` bytes** to the destination, never `buffer.length` (since the remainder may still hold stale bytes from the previous iteration).

**Do not treat a short read as the end of a component stream.** `SequenceInputStream` is responsible for detecting real EOF and switching sources. In your outer loop, the termination condition is `-1`.

### 7.3. Guarding Large or Untrusted Sources

If sources come from user-uploaded files, networks, or untrusted storage, enforce:

- **A total byte quota** across the joined stream and, if needed, per-source quotas.
- **Timeouts/deadlines/cancellation** for sources that might stall or never emit EOF.
- **A cap on source count** in the `Enumeration`/`List` to avoid exhausting handles.
- **Validation of chunk order and identity** (such as chunk index, version, size, checksum); `SequenceInputStream` only honors the order given and cannot verify chunk correctness.
- **Handling missing or failing chunks:** never publish a concatenated result as complete.
- **Temporary output staging:** for critical files, write to a temp file and verify integrity before replacing existing output.

## 8. Alternatives

`SequenceInputStream` fits when **an API strictly requires a single `InputStream`** representing multiple sequential sources. Not every data-joining task calls for this class.

### 8.1. Concatenating a Large Number of Files

If your goal is simply to append many files sequentially into one output file, a loop opening **one file at a time** gives much tighter control over file handles. In the snippet below, `paths` is a valid `List<Path>` and `outputPath` is the target `Path`; caller code must verify that `outputPath` is not included in `paths`:

```java
// Illustrative snippet (paths and outputPath must be provided).
try (java.io.OutputStream target =
        java.nio.file.Files.newOutputStream(outputPath)) {
    for (java.nio.file.Path path : paths) {
        try (java.io.InputStream source =
                java.nio.file.Files.newInputStream(path)) {
            source.transferTo(target);
        }
    }
}
```

Advantage: only one source stream is open per iteration and it closes right away; error handling easily pinpoints the exact failing filename. Trade-off: if the consumer demands **one `InputStream`** rather than letting you control the target `OutputStream`, `SequenceInputStream` is more convenient.

Note: this is still raw **byte concatenation** and does not synthesize a valid ZIP/PDF/PNG out of independent files. If the target already exists, `Files.newOutputStream(outputPath)` with default options overwrites/truncates existing contents; consider a temporary file if the old version must remain intact on failure.

### 8.2. Joining Data Already in Memory

If the total data is **small and bounded**, you can use `ByteArrayOutputStream` with `writeBytes(byte[])` to build the combined array:

```java
// Illustrative using small existing byte arrays.
java.io.ByteArrayOutputStream output =
        new java.io.ByteArrayOutputStream();
output.writeBytes(firstBytes);
output.writeBytes(secondBytes);
byte[] joined = output.toByteArray();
```

`writeBytes` has been available since Java 11. This **materializes** the result into a new `byte[]`; it is easy to store or reuse, at the cost of memory proportional to total bytes. `SequenceInputStream` provides a **stream view**, better suited when consuming incrementally without building an intermediate concatenated array.

### 8.3. Reading Text Data

If the sources are **text properly encoded in the same charset** but split at arbitrary byte boundaries, join the bytes with `SequenceInputStream` first and wrap **one** `InputStreamReader` on the outside:

```java
// Illustrative; first and second are source InputStreams,
// transferring close ownership to SequenceInputStream.
try (java.io.Reader reader = new java.io.InputStreamReader(
        new java.io.SequenceInputStream(first, second),
        java.nio.charset.StandardCharsets.UTF_8)) {
    char[] characters = new char[1024];
    while (reader.read(characters) != -1) {
        // Process each character chunk (use actual char count read
        // if forwarding or storing data).
    }
}
```

The key point is having **a single decoder outside the joined byte stream**, because a UTF-8 code point may have bytes split across two sources. For complete code, instantiate `first`/`second` and handle setup failures as discussed in Section 6. Do not use this pattern if the sources actually use different charsets; decode each source with its own charset and define joining rules at the character level.

### 8.4. When You Need Interleaving or Structured Merging

If you want one byte from source A followed by one byte from B (round-robin), `SequenceInputStream` does not do that. If you want to merge by timestamp or sort key, implement a data-driven merge algorithm. If you need headers, length prefixes, delimiters, checksums, or multi-file archives, use a writer/parser tailored to the required format.

## 9. Key Technical Pitfalls

1. **Confusing sequential concatenation with parallel reading:** `SequenceInputStream` finishes one source before moving to the next; it does not boost throughput using multiple threads.
2. **Calling `readAllBytes()` on large sources:** allocates an array growing with total data; can exhaust heap memory.
3. **Believing concatenating two standalone files yields one valid file:** formats with headers/footers, frames, or indexes require format-aware handling.
4. **Forgetting delimiters:** `"hello"` + `"world"` becomes `"helloworld"`; explicitly emit newlines if required.
5. **Decoding UTF-8 per chunk before joining:** can split inside a code point's byte sequence and corrupt text.
6. **Failing to close the combined stream:** unconsumed sources can still hold open resources.
7. **Pre-opening too many files:** even though reading is sequential, eagerly opened sources hold file descriptors simultaneously.
8. **Not cleaning up failed source initialization:** failing to open the second file can leak the already-opened first file.
9. **Writing missing or extra bytes by ignoring `read(byte[])`'s return value:** always use the actual byte count received.
10. **Stopping when `available() == 0`:** that is not EOF, especially for network streams.
11. **Failing to enforce chunk ordering:** concatenating chunks out of order produces corrupt content with no I/O error.
12. **Ignoring partial-write failures:** if output fails midway, the destination may already hold partial data.
13. **Treating `SequenceInputStream` as seekable/resettable:** it is a sequential stream without random access like a file channel.
14. **Assuming `ByteArrayInputStream` frees off-heap OS resources:** byte-array sources hold no file descriptors; `close()` behaves differently from files/sockets.
15. **Calling full-transfer APIs on sources that never emit EOF:** can block indefinitely; timeouts and limits belong at the source/protocol layer.

## 10. Practice Exercises and Self-Check Questions

### Exercise 1 — Ordering and Empty Sources

Concatenate three `ByteArrayInputStream`s containing `{5, 6}`, `{}`, and `{7}`. Read with `read()` until `-1` and print each byte; the output must be `5`, `6`, `7` in order. Explain why the empty source does not stop the entire sequence.

### Exercise 2 — Multiple Fragments from One Original Payload

Take the UTF-8 `byte[]` of `"Tiếng Việt 😀"`, split it into three slices at **arbitrary byte offsets**, and rejoin them with `SequenceInputStream`. Compare the resulting byte array against the original array, then decode once after joining. If you split right inside the emoji, why is the text still recovered accurately?

### Exercise 3 — Memory Comparison

Using a bounded total source size, compare:
- `SequenceInputStream` → `readAllBytes()`;
- `SequenceInputStream` → `ByteArrayOutputStream`;
- `SequenceInputStream` → `Files.newOutputStream(...)` via `transferTo`.

Identify which approaches keep the full result on the heap and which transfer in chunks. Do not test against unbounded sources or huge files without resource quotas.

### Exercise 4 — Detecting Concatenation Failures

Simulate three sources where the second source throws an `IOException` midway. Verify that the exception propagates out, the combined stream is closed via `try-with-resources`, and temporary output is discarded. Why must you not report success just because bytes from the first source were copied?

### Exercise 5 — Choosing the Right API

Explain the appropriate tool for each scenario:

- An API accepts only one `InputStream`, yet the data is split across several ordered byte sources.
- 10,000 files must be concatenated into one destination file; opening 10,000 file descriptors simultaneously must be avoided.
- Two standalone ZIP files need to be combined into one valid archive.
- Frames from two sources need to be interleaved by timestamp.
- A few small byte arrays need to be combined into one `byte[]` for further processing.

**Guided answers:** `SequenceInputStream`; a loop opening and closing one source at a time; a standard archive library/writer; a timestamp-based merge algorithm; `ByteArrayOutputStream` or array copying.

## 11. Summary of Core Concepts

- `SequenceInputStream` provides **a single InputStream** representing multiple byte sources **concatenated in order**.
- Its two constructors accept **two streams** or an **Enumeration of streams**; EOF on each source triggers advancing to the next, while final EOF ends the sequence.
- It inserts no delimiters, creates no compound file format, does not read in parallel, and performs no Unicode/charset processing.
- When joining text bytes split mid-character, **concatenate the bytes first and decode afterward** with the proper charset.
- `try-with-resources` ensures the combined stream is closed; for real resources, also handle initialization errors before handing over ownership.
- For large sources, stream in chunks to a non-accumulating destination; avoid `readAllBytes()` and `ByteArrayOutputStream` when the combined output may exceed memory.
- When simply appending many files sequentially into one file, a loop that opens and closes **one file at a time** is simpler and saves file descriptors.

Good engineering comes from picking the right tool for **sequential byte concatenation**, **resource lifecycles**, **memory limits**, and **format correctness**, rather than reaching for `SequenceInputStream` for every kind of "data merging."
