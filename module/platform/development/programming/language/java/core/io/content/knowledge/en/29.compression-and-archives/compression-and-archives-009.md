# Deflater, Inflater, and the Scope of Compression-Level Control in Java

## 1. The Problem: Compression and Decompression Are Two Directions of a Data Stream

In `java.util.zip`, the `Deflater` and `Inflater` pair provides a low-level interface to the **DEFLATE** algorithm. DEFLATE compresses bytes using a combination of LZ77 and Huffman coding; the goal is to reduce stored or transmitted bytes when data exhibits repetition.

~~~text
Original data: byte[] or ByteBuffer
                  |
                  v
         Deflater (compress)
      level + strategy + state
                  |
                  v
        Compressed byte stream
                  |
      save file / send over network
                  |
                  v
         Inflater (decompress)
                  |
                  v
            Original bytes
~~~

Both classes process **bytes** and do not directly understand characters, lines of text, or Java objects. Before compressing strings, encode them with an explicit charset, e.g., `StandardCharsets.UTF_8`. After decompression, only decode bytes into text if you know the exact charset.

**Main question of this article:** How far does Java allow controlling the *compression level*, what does that level affect, and what lies outside the guarantees of `Deflater`/`Inflater`?

Short answer: **compression level is a compressor-side parameter balancing CPU speed and size reduction**. It does not determine an absolute output size, does not guarantee a compression ratio, does not control decompression with symmetric levels, and does not automatically turn a byte stream into a ZIP or GZIP file.

## 2. Distinguishing the DEFLATE Algorithm from zlib, gzip, and ZIP

These four similar names are **not synonymous**:

| Term | Nature | What to Remember |
| --- | --- | --- |
| DEFLATE | Algorithm/encoding format for compressed data | Can be used as raw DEFLATE |
| zlib | Packaging of DEFLATE with header/trailer and data checksum | `new Deflater(level)` produces a stream with a zlib wrapper; `new Inflater()` decompresses that format |
| gzip | Format with gzip header/trailer supporting appropriate metadata | Java provides `GZIPOutputStream` and `GZIPInputStream` |
| ZIP | Archive format with entries, metadata, and an archive directory table | Java provides `ZipOutputStream`, `ZipInputStream`, `ZipFile`, and the ZIP filesystem |

Example:

~~~text
raw DEFLATE: [deflate payload]

zlib:        [zlib header][deflate payload][Adler-32]

gzip:        [gzip header][deflate payload][gzip trailer]

ZIP:         [local entry headers + data][central directory + metadata]
~~~

Simplified diagram; does not depict every field or format variant.

**Do not feed an entire `.gz` or `.zip` file into `new Inflater()` expecting decompression to succeed.** By default, `Inflater()` expects a zlib-formatted stream and does not automatically parse gzip headers or ZIP archive structures. For gzip use `GZIPInputStream`; for ZIP archives use the appropriate ZIP APIs.

If **raw DEFLATE** without a zlib header/checksum wrapper is needed, overloads `new Deflater(level, true)` and `new Inflater(true)` are available. Both sides must agree on the format. `nowrap=true` does not mean producing a complete gzip/ZIP; container structures must still be handled at the appropriate layer.

## 3. Selectable Compression Levels

`Deflater` lets you specify the compression level at construction or change it for subsequent compressed data:

~~~java
Deflater compressor = new Deflater(Deflater.BEST_SPEED);
compressor.setLevel(Deflater.BEST_COMPRESSION);
~~~

This is an **illustrative Java fragment**; you must import `java.util.zip.Deflater` and call `compressor.end()` once finished.

| Constant | Value | Meaning |
| --- | ---: | --- |
| `Deflater.NO_COMPRESSION` | 0 | Do not apply standard DEFLATE size-reduction strategies; the stream still retains appropriate framing |
| `Deflater.BEST_SPEED` | 1 | Prioritize compression speed |
| Levels 2 through 8 | 2–8 | Tradeoff choices between speed and compression ratio |
| `Deflater.BEST_COMPRESSION` | 9 | Prioritize size reduction |
| `Deflater.DEFAULT_COMPRESSION` | -1 | Let the implementation choose the default level |

Common constructors:

~~~java
new Deflater();                              // Default level, zlib wrapper
new Deflater(Deflater.BEST_SPEED);           // Level 1, zlib wrapper
new Deflater(Deflater.BEST_COMPRESSION);     // Level 9, zlib wrapper
new Deflater(Deflater.NO_COMPRESSION);       // Level 0, zlib wrapper
new Deflater(6, true);                       // Raw DEFLATE with level 6
~~~

Values outside the allowed range, such as `-2` or `10`, throw `IllegalArgumentException`. `-1` is the constant for the default level, **not a compression level stronger than 9**.

### Does Level 0 Mean Returning the Input Verbatim?

No. `NO_COMPRESSION` uses DEFLATE's uncompressed block option, yet **the output is still a packaged compressed stream** in the chosen format. With a zlib wrapper, there is header/trailer overhead and block framing. Output bytes do not equal raw input bytes verbatim; you must still decompress according to the format to recover the original bytes.

For small or incompressible data, output can be **larger than the input** due to overhead. Therefore, level 9 also **does not guarantee** a smaller output than level 1 in every case.

### Does Level 9 Always Produce the Smallest File?

There is no such universal guarantee in the API. Output size depends on:

- Data type: repetitive text generally compresses much better than already-compressed or randomly encrypted data.
- Input block size and how data is fed over time.
- Underlying zlib version/library and implementation.
- Compression level, strategy, and stream flushing behavior.
- Container format, metadata, and framing overhead.

Level 9 typically burns more CPU trying to shrink bytes, yet **offers no fixed compression ratio promise**. Level 1 is usually faster and suits latency-sensitive compression, yet offers no fixed time bound either.

## 4. Boundaries of Compression-Level Control

Distinguish what compression level **can affect** from what it **does not directly guarantee**:

| Aspect | Affected by Compression Level? | Explanation |
| --- | --- | --- |
| Compression CPU cost | Yes, often noticeably | Higher levels typically search harder for compression matches |
| Output size | Potentially | Result depends on data, overhead, flushing, implementation |
| Decompression speed | Potential indirect differences | There is no symmetric decompression level to pick |
| Correctness of decompressed data | Should not change | Valid streams must decompress to exact original bytes |
| Text charset/encoding | No | Character encoding is chosen before/outside the compressor |
| Security encryption | No | DEFLATE is not encryption |
| ZIP/GZIP metadata | No | The container format determines metadata |
| Ensuring archive has CRC and entries | No | Managed by the ZIP/GZIP container/API |
| Maximum size after decompression | No | Must enforce explicit output limits to stop decompression bombs |
| Identical compressed bytes across all JDKs | No | API does not guarantee byte-for-byte reproducibility across implementations |

These boundaries guide API design. If you want to give users a "fast" vs. "thorough" choice, you can map to level 1 or 9. However, if a business rule requires size not exceeding 100 KiB, **picking level 9 does not replace checking the actual resulting size**.

Good design measures CPU time, output size, and compression ratio on **your application's actual data types** rather than relying on level labels for absolute predictions.

## 5. `Deflater` Is a Stateful Compressor

Lifecycle flow:

~~~text
new Deflater(level)
        |
        v
setInput(bytes)
        |
        v
deflate(outBuffer) ── returns compressed byte count ──> save/send
        |
        +── needsInput() ? supply next input
        |
        +── finish() when no more input remains
        |
        v
loop deflate(...) until finished() == true
        |
        v
end() releases native resources
~~~

Key APIs:

- `setInput(byte[])` or offset/length overloads: feeds source bytes into the compressor.
- `needsInput()`: indicates the compressor has consumed available input and may need more.
- `deflate(byte[])` and offset/length overloads: writes compressed bytes to output and returns **the actual number of bytes produced**.
- `finish()`: signals that **all input has been supplied**, requesting stream termination in subsequent `deflate` calls.
- `finished()`: becomes true only when the compressor has finished emitting all output.
- `reset()`: resets state to begin a new compressed stream with the same object; never concatenates old and new streams into one.
- `end()`: releases resources; do not use afterward.

**`finish()` does not automatically return all compressed bytes.** After calling `finish()`, you must still loop `deflate(...)` until `finished()`. If the output buffer is small, multiple iterations are needed to drain all data.

Similarly, a single `deflate(...)` call is not guaranteed to consume all input or emit the entire compressed stream. Check the returned byte count and compressor state; never write code calling it once assuming data fits when inputs can be large.

For streaming compression, call `setInput` whenever `needsInput()` becomes true, write all generated output to file/network, and repeat; at source EOF call `finish()` and keep draining output. In small utilities, you can feed all input bytes at once as shown in the example below.

## 6. How Does `Inflater` Decompress?

`Inflater` accepts a **compressed byte stream** and produces original bytes. It does not accept a compression level like `Deflater`.

~~~text
new Inflater()                  // zlib wrapper
        |
setInput(compressedBytes)
        |
inflate(uncompressedBuffer)
        |
        +── n > 0: new original bytes available
        |
        +── needsInput(): needs more compressed input
        |
        +── needsDictionary(): requires matching dictionary
        |
        +── DataFormatException: invalid compressed data
        |
        v
finished() == true
        |
        v
end()
~~~

States to understand:

- `inflate(byte[])` returns the number of original bytes produced in that call.
- `finished()` confirms the end of the compressed stream has been reached.
- `needsInput()` means `Inflater` has no compressed input left to consume; if the file/network source still has data, feed more. If the source reached EOF while `finished()` is still false, data may be truncated.
- `needsDictionary()` signals the stream requires a preset dictionary; the application must supply the exact dictionary used during compression.
- `getRemaining()` tells how many compressed input bytes remain unconsumed in `Inflater` after decompression, useful when parsing trailers or concatenated segments.
- `DataFormatException` indicates an invalid stream or format error. Never conflate every decompression failure with a charset error.

**There is no `new Inflater(level)`.** The decoder must read any valid DEFLATE stream regardless of whether the compressor picked level 0, 1, or 9. Compression level does not lose original data; this is **lossless** compression.

After finishing decompression of a stream, to reuse the same object, call `reset()` and then feed input for the **new stream** in the matching format. Never call `reset()` midway through an unfinished stream.

## 7. Complete Java 17+ Program: Compressing at Multiple Levels and Decompressing Accurately

This program generates repetitive ASCII data, compresses the same payload at three different compression levels, decompresses each result, and compares byte-for-byte against the source.

The example intentionally **does not print compressed byte counts**, because exact byte counts can vary across runtimes/zlib implementations. The boolean round-trip results are what should be verified.

Save as `DeflaterInflaterDemo.java`:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.zip.DataFormatException;
import java.util.zip.Deflater;
import java.util.zip.Inflater;

public class DeflaterInflaterDemo {
    private static final int MAX_DECOMPRESSED_BYTES = 1_000_000;

    static byte[] compress(byte[] input, int level) throws IOException {
        Deflater encoder = new Deflater(level); // zlib wrapper
        try {
            encoder.setInput(input);
            encoder.finish();

            ByteArrayOutputStream result = new ByteArrayOutputStream();
            byte[] buffer = new byte[128];

            while (!encoder.finished()) {
                int n = encoder.deflate(buffer);
                if (n == 0) {
                    throw new IOException("Deflater made no progress");
                }
                result.write(buffer, 0, n);
            }
            return result.toByteArray();
        } finally {
            encoder.end();
        }
    }

    static byte[] decompress(byte[] compressed)
            throws IOException, DataFormatException {
        Inflater decoder = new Inflater(); // zlib wrapper
        try {
            decoder.setInput(compressed);
            ByteArrayOutputStream result = new ByteArrayOutputStream();
            byte[] buffer = new byte[128];

            while (!decoder.finished()) {
                int n = decoder.inflate(buffer);

                if (n > 0) {
                    if (result.size() + n > MAX_DECOMPRESSED_BYTES) {
                        throw new IOException("Decompressed data too large");
                    }
                    result.write(buffer, 0, n);
                    continue;
                }

                if (decoder.needsDictionary()) {
                    throw new IOException("Preset dictionary required");
                }
                if (decoder.needsInput()) {
                    throw new EOFException("Compressed stream truncated");
                }
                throw new IOException("Inflater made no progress");
            }
            return result.toByteArray();
        } finally {
            decoder.end();
        }
    }

    public static void main(String[] args)
            throws IOException, DataFormatException {
        byte[] source = "JAVA-NIO-COMPRESSION;".repeat(500)
                .getBytes(StandardCharsets.UTF_8);

        byte[] noCompression =
                compress(source, Deflater.NO_COMPRESSION);
        byte[] fast = compress(source, Deflater.BEST_SPEED);
        byte[] dense = compress(source, Deflater.BEST_COMPRESSION);

        System.out.println("level 0 round-trip: "
                + Arrays.equals(source, decompress(noCompression)));
        System.out.println("level 1 round-trip: "
                + Arrays.equals(source, decompress(fast)));
        System.out.println("level 9 round-trip: "
                + Arrays.equals(source, decompress(dense)));
        System.out.println("same original bytes: "
                + Arrays.equals(decompress(fast), decompress(dense)));
        System.out.println("input bytes: " + source.length);
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac DeflaterInflaterDemo.java
java DeflaterInflaterDemo
~~~

Stdout:

~~~text
level 0 round-trip: true
level 1 round-trip: true
level 9 round-trip: true
same original bytes: true
input bytes: 10500
~~~

Explanation of results:

1. The ASCII string `JAVA-NIO-COMPRESSION;` is **21 bytes**; repeating 500 times yields **10,500 input bytes**.
2. `NO_COMPRESSION` (level 0) still produces a **valid zlib stream** that decompresses back to the exact input.
3. `BEST_SPEED` (level 1) and `BEST_COMPRESSION` (level 9) produce compressed streams with different priorities; both must restore the identical payload.
4. `Arrays.equals` compares original bytes rather than just checking size or decoded text.
5. The output buffer is only 128 bytes; both compressor and decoder are called in loops, avoiding the assumption that one compression/decompression call always completes.
6. `end()` in `finally` releases resources even if an error occurs.
7. Decompression caps output at 1,000,000 bytes to illustrate defending against a tiny compressed stream expanding into massive data.

The example uses known input and requires no dictionary, so dictionary or truncated-stream errors do not occur during normal execution. If you manually corrupt compressed bytes or truncate midway, the decoder may throw `DataFormatException`, `EOFException`, or a related exception instead of printing all five lines.

**Why not print "level 9 is guaranteed smaller than level 1"?** On this data there is usually a size difference, yet the API does not guarantee a strict ordering for every input and implementation. When optimizing a system, measure actual `compressed.length` and compression time on a representative dataset.

## 8. What Does `setLevel()` Change?

`Deflater.setLevel(int level)` adjusts the level for **subsequent data segments to be compressed**. The right mental model is treating the `Deflater` object as a state machine:

~~~java
Deflater encoder = new Deflater(Deflater.BEST_SPEED);
try {
    encoder.setInput(firstChunk);
    // Drain generated data in a streaming loop.
    // After processing this input, you can change priority:
    encoder.setLevel(Deflater.BEST_COMPRESSION);
    encoder.setInput(nextChunk);
    // Continue calling deflate(...) until finished.
} finally {
    encoder.end();
}
~~~

This is **Java-like pseudocode**, not a standalone runnable program: `firstChunk`, `nextChunk`, and draining logic must be defined. Do not copy verbatim while omitting input consumption, `needsInput()` checks, and output draining.

Important limitations:

- `setLevel` does not recompress bytes already emitted earlier; it affects subsequent compression.
- Changing level does not switch codecs, turn zlib into gzip, or create a new ZIP entry.
- Any valid DEFLATE stream still decompresses without passing the compression level to `Inflater`.
- When changing levels mid-stream, follow the input/deflate/flush sequence cleanly to avoid confusing state; never treat the setter as retroactively applying to previous bytes.
- If the requirement is "a different level per file" in a ZIP archive, use the archive API supporting per-entry levels semantically rather than blindly concatenating arbitrary `Deflater` streams into a ZIP file.

In practice, **choosing one compression level at stream startup** and keeping it fixed is easier to test than changing levels repeatedly. Change levels mid-stream only when a clear streaming need exists and measurements justify it.

## 9. Strategy Is Not Compression Level

Besides `setLevel`, `Deflater` provides `setStrategy(int strategy)`. Common strategies:

| Strategy | Goal |
| --- | --- |
| `DEFAULT_STRATEGY` | Default choice for general-purpose data |
| `FILTERED` | Can help with certain pre-filtered data or specific symbol distributions |
| `HUFFMAN_ONLY` | Uses Huffman coding without relying on default LZ77 string-matching searches |

Example:

~~~java
Deflater encoder = new Deflater(Deflater.BEST_SPEED);
try {
    encoder.setStrategy(Deflater.FILTERED);
    // Compress appropriate data with setInput/deflate/finish.
} finally {
    encoder.end();
}
~~~

This is an illustrative fragment, not a complete compression routine. Strategy **does not replace level**: a high level paired with an unsuitable strategy can yield worse results than expected.

Depending on input, changing strategy can increase or decrease speed or output size. Never pick `FILTERED` or `HUFFMAN_ONLY` simply because the name sounds faster or "deeper". Benchmark on real data and stick with the default strategy unless a clear reason is proven.

## 10. Flush Modes Also Affect Compression Efficiency

`Deflater` has `deflate(...)` overloads accepting a flush mode, such as:

- `NO_FLUSH`: normal state; prioritizes exploiting data already buffered in the stream.
- `SYNC_FLUSH`: makes output synchronizable/decompressible up to a clean boundary without terminating the stream.
- `FULL_FLUSH`: besides flushing, resets compression history so a decompressor can recover from a clean boundary; can reduce compression ratio.

These are **streaming process controls**, not three new compression levels. Flushing too often adds overhead and reduces the ability to exploit repeated data across chunk boundaries.

Some real-time data transfer apps lower latency by flushing frequently; large-file archival apps wanting smaller sizes avoid unnecessary flushes. The choice must be driven by the receiver protocol, target latency, and benchmarks.

**Distinguishing `finish()` from flush:** `finish()` marks the end of input and end of stream. `SYNC_FLUSH`/`FULL_FLUSH` create sync points inside **an ongoing stream**; they do not replace `finish()`.

## 11. Dictionaries Are a Separate Mechanism

For data with small, known recurring patterns, DEFLATE supports a **preset dictionary** in suitable stream formats. The compressor calls `Deflater.setDictionary(...)`; the decompressor may encounter `Inflater.needsDictionary()` and must call `Inflater.setDictionary(...)` with the exact matching dictionary bytes.

Setting compression level 9 **does not transmit a dictionary** to the decoder. If the decoder lacks the required dictionary, a stream cannot be decompressed even if the payload is intact.

In protocol design:

1. Decide whether a dictionary is used.
2. Ensure the receiver knows the exact same dictionary version via shared config or protocol metadata.
3. Handle `needsDictionary()` explicitly.
4. Never expect dictionary strategies to work identically across every container/format; standard ZIP entries, for example, carry specific constraints.

Preset dictionaries are an advanced optimization, not a default requirement for most Java compression tasks.

## 12. DeflaterOutputStream and Higher-Level APIs

When you just want to compress data written to a stream, `DeflaterOutputStream` manages the input/output loop:

~~~java
import java.io.ByteArrayOutputStream;
import java.util.zip.Deflater;
import java.util.zip.DeflaterOutputStream;

ByteArrayOutputStream destination = new ByteArrayOutputStream();
Deflater encoder = new Deflater(Deflater.BEST_SPEED);

try (DeflaterOutputStream compressed =
        new DeflaterOutputStream(destination, encoder)) {
    compressed.write(payload);
}

// Compressed data is in destination.toByteArray().
// Manage Deflater lifecycle per stream/constructor contract.
~~~

This is an **illustrative fragment** using a pre-existing `payload` variable; it is not a standalone program. When passing your own `Deflater` instance to a stream, check who is responsible for closing/`end()` according to the constructor overload used to avoid leaking native resources. `close()` or `finish()` on the stream must finalize compressed output before reading the final result.

To decompress a matching zlib stream, use `InflaterInputStream`. For gzip format use `GZIPOutputStream`/`GZIPInputStream`. For ZIP format use `ZipOutputStream` or `ZipFile`/`ZipInputStream`.

### Controlling Compression Level When Packaging ZIPs

`ZipOutputStream` has `setLevel(int)` to choose the compression level for **subsequent DEFLATED entries** per API semantics. This differs from creating a standalone `Deflater` and writing raw bytes directly into an archive.

A ZIP archive also contains entry names, timestamps, metadata, CRCs, and a central directory. Plain `Deflater` does not create those structures. When data only needs compressing into a zlib blob, `Deflater` fits; for multiple files in one archive, use archive APIs.

## 13. Data Safety and Performance During Decompression

Aggressive compression does not imply safe decompression on untrusted data. A tiny compressed payload can produce massive output. If an application receives compressed data from external sources, bound:

- **Decompressed output size** in bytes, not just compressed input size.
- **Maximum time/CPU** spent decompressing per policy.
- **Memory usage**, buffer sizes, and concurrent task counts.
- **Number of streams or archive entries** allowed if the input is a ZIP container.
- **Nested decompression depth** if the protocol permits layered compression.

The example above caps output at 1,000,000 bytes. In real systems, the threshold depends on the domain, and you may need to stream to storage and abort immediately when exceeding the quota instead of holding all output in RAM.

Check `Inflater.finished()`. If input runs out before `finished()`, the data may be truncated; if `DataFormatException` is thrown, the input/format is invalid. Additionally, if the protocol requires **all compressed input bytes to be consumed**, check `getRemaining()` or inspect trailers/containers per the active spec; never silently ignore trailing bytes.

**Compression is not security.** DEFLATE neither encrypts nor authenticates the sender. When confidentiality/integrity is required, combine dedicated encryption/authentication protocols instead of expecting high compression levels to hide content.

In protocols where secrets and attacker-controlled data share a single compression context, compressed output size can even leak information; evaluate compression side-channel risks per your architecture.

## 14. Choosing a Level in Applications

| Need | Starting Point to Try | What Must Still Be Measured |
| --- | --- | --- |
| Low latency, limited CPU | `BEST_SPEED` | Latency, CPU, transmitted bytes |
| Large archival files that rarely change | `BEST_COMPRESSION` or medium-high level | Compression time, ratio, storage cost |
| Already-compressed or incompressible data | Low level or skip compression | Overhead, whether size increases |
| General-purpose balance | `DEFAULT_COMPRESSION` | Real data, system CPU capacity |
| Real-time streaming | Low/medium level and intentional flushing | Per-chunk latency, flush overhead |
| Packaging multiple files | ZIP API with suitable per-entry level | Metadata/CRC/archive, per-entry CPU and size |

These are **starting points to benchmark**, not absolute rules. Measure on representative data: total bytes before/after, compression time, decompression time, peak RAM, and round-trip correctness.

For instance, on repetitive text logs, higher levels can reduce size significantly; on JPEG, MP4, or already-compressed data, higher levels yield minimal benefit while burning CPU. Skipping compression altogether at the application layer sometimes saves more resources.

## 15. Common Mistakes

**Mistake 1 — Thinking Inflater needs the same level configured.** The decoder has no symmetric level parameter. Configuring `Inflater` with the matching **wrapper format and dictionary** is what matters.

**Mistake 2 — Thinking level 9 always yields smaller output than level 1.** There is no universal guarantee. Always measure output size on your specific data.

**Mistake 3 — Calling finish() and not draining all output.** `finish()` does not emit all bytes by itself; keep calling `deflate(...)` until `finished()`.

**Mistake 4 — Calling deflate/inflate only once.** Output buffers may be smaller than the data. Loop based on state and returned byte counts.

**Mistake 5 — Confusing zlib wrappers with gzip or ZIP archives.** `new Deflater(level)` does not create a complete `.gz` or `.zip` file.

**Mistake 6 — Using nowrap=true on one side and nowrap=false on the other.** Mismatched formats cause decompression failures.

**Mistake 7 — Treating NO_COMPRESSION as keeping every input byte verbatim.** Even without payload compression, the stream still carries framing/overhead.

**Mistake 8 — Forgetting end().** `Deflater` and `Inflater` can hold native resources; use `finally` or appropriate lifecycle management.

**Mistake 9 — Ignoring needsInput/needsDictionary.** The decoder may need more compressed input or a dictionary; spinning on `inflate` when it repeatedly returns 0 hangs the CPU.

**Mistake 10 — Decompressing untrusted input without size limits.** Risks a decompression bomb exhausting RAM/CPU.

**Mistake 11 — Flushing every chunk hoping for a smaller file.** Frequent flushing adds overhead and can hurt compression efficiency.

**Mistake 12 — Assuming compression level replaces checksums or encryption.** Security and integrity belong to separate layers; wrappers like zlib only perform format-level data error checks, not attack-resistant authentication codes.

## 16. Self-Check

1. What are the values of `BEST_SPEED` and `BEST_COMPRESSION`? **1** and **9**.
2. What is the value of `DEFAULT_COMPRESSION`? **-1**, representing the default configuration.
3. Does `NO_COMPRESSION` return raw input bytes verbatim? **Not necessarily**, because output still includes framing.
4. Does `Inflater` need to know the level used during compression? **No**.
5. Why must `deflate` be looped after `finish()`? **Because compressed output may still remain inside the compressor** waiting to be drained.
6. What does `needsDictionary()` mean? **The compressed input requires a preset dictionary**, not a request to try a higher level.
7. Does `nowrap=true` produce a gzip file? **No**; it selects raw DEFLATE without a zlib wrapper, whereas gzip has its own header/trailer.
8. Is `setStrategy(HUFFMAN_ONLY)` the same as `setLevel(9)`? **No**; strategy and level are two distinct controls.
9. If 100 KiB compresses down to 4 KiB, does that prove decompression always takes under 100 KiB RAM? **No**; overhead exists and actual output limits are needed.
10. A truncated stream causes `Inflater.needsInput() == true` before `finished()`. What should you do? **Try reading more if the source still has data; if true EOF was reached, report an incomplete input error**.
11. To archive multiple files, should you concatenate multiple `Deflater` outputs into a `.zip` file yourself? **No**; use ZIP APIs to create valid entries and metadata.
12. If level 9 saves only 1% more space while costing many times more CPU, what is the practical choice? **Evaluate against the application's CPU budget, latency, bandwidth, and storage costs**, rather than assuming the highest level is always best.

**Remember:** `Deflater` controls DEFLATE compression, where **levels 0–9 or DEFAULT_COMPRESSION** primarily tune the speed vs. byte-reduction tradeoff. `Inflater` decompresses valid streams **without needing to know the level**. Beyond level, there are strategy, flush mode, dictionary, and wrapper format, each with its own contract. Always complete the `setInput → deflate → finish/finished → end` cycle, bound decompression, and verify round-trips; never treat compression level as a guarantee of size, performance, or security.
