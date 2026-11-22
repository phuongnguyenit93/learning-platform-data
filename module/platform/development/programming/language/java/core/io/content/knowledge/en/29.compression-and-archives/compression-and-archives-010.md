# CRC32, Adler32, and the Limits of Checksums in Java I/O

## 1. What Are Checksums Used For?

A **checksum** is a short value computed from a byte sequence to help detect whether data was altered during transmission, storage, or decompression. Instead of re-comparing every byte against the original, the receiver can compute the checksum over the received bytes and compare it against a previously stored or transmitted value.

Example:

~~~text
Sender:      "HELLO" --[compute checksum]--> 32-bit number X
               |                              |
               +---------- transmit ----------+
                                              |
Receiver:    "HELXO" --[compute checksum]--> 32-bit number Y
                                              |
                                    X != Y => mismatch detected

If X == Y: data MAY match, but is NOT
           guaranteed identical to the original data.
~~~

In Java Core I/O, `CRC32` and `Adler32` are two 32-bit checksums in the `java.util.zip` package. They commonly appear in compression and archiving contexts because formats such as ZIP, GZIP, and zlib use checksums to check decompressed data.

Three key ideas to grasp:

1. **Checksums operate on bytes**, so character encoding, byte order, and the exact byte range being summed must be agreed upon by both sides.
2. **CRC32 and Adler32 catch many accidental errors**, yet because their output is only 32 bits, *collisions* always exist: different data can produce the same checksum.
3. **A checksum is not a digital signature, HMAC, or authentication mechanism**. An adversary can modify data and recompute the matching checksum, especially when the checksum lives alongside the data in an unprotected file.

## 2. Comparing CRC32 and Adler32

| Criterion | CRC32 | Adler32 |
| --- | --- | --- |
| JDK class | `java.util.zip.CRC32` | `java.util.zip.Adler32` |
| Value width | 32 bits | 32 bits |
| Core mechanism | Polynomial division over GF(2), commonly implemented via lookup tables or hardware. | Two cumulative sums modulo 65521, packed into a 32-bit integer. |
| Characteristics | Designed to detect many bit-error patterns, especially structured burst errors in transmission. | Simple formula, often fast in certain environments; error detection on short messages can be weaker than CRC32. |
| Format association | ZIP entries and GZIP trailers use IEEE-style CRC32. | The zlib wrapper around DEFLATE streams uses Adler-32. |
| Java API | `update(...)`, `getValue()`, `reset()` | Same `Checksum` contract. |
| Protection against intentional tampering | No | No |

**No algorithm is "as strong as SHA-256" merely because its output looks random.** A 32-bit value is insufficient as a unique identifier or integrity check against a deliberate attacker; the purpose of these algorithms is **low-cost detection of ordinary accidental corruption**.

### 2.1. How Do Checksums Differ from Hashes, CRCs, and Signatures?

The term *hash* is sometimes used broadly for any function mapping data to a short value. However, in system design, distinguish:

- **Non-cryptographic checksums:** CRC32, Adler32; suitable for checking data after transmission/decompression.
- **Cryptographic hashes:** SHA-256, SHA-512; far stronger collision resistance than 32-bit checksums, yet by themselves **do not prove who created the data** if an attacker can replace both data and hash.
- **HMAC:** e.g., HmacSHA256, uses a shared secret key to verify content and a key-holding origin; requires secure key management.
- **Digital signatures:** use a private key to sign and a public key to verify; provide origin authentication and tamper detection under an appropriate trust model.

To protect networked data against adversaries, use authenticated, integrity-protected protocols like TLS rather than simply appending a CRC32 to a packet.

## 3. How Does CRC32 Work?

CRC stands for **Cyclic Redundancy Check**. A CRC treats a bit sequence as a polynomial over the binary field `GF(2)` and performs division by a generator polynomial to obtain the remainder. Addition/subtraction here corresponds to XOR.

`java.util.zip.CRC32` implements the CRC-32 widely used in ZIP/GZIP (often called CRC-32/ISO-HDLC or CRC-32/IEEE). Common parameters of this variant include:

- Width: **32 bits**.
- Standard-form polynomial: `0x04C11DB7`; bit-reflected form used in LSB-first implementations: `0xEDB88320`.
- Internal initial value: `0xFFFFFFFF`.
- Input and output are reflected per the common CRC-32 variant.
- Final result is XORed with `0xFFFFFFFF`.

Not every algorithm named "CRC32" shares the same **CRC parameters**. Another variant such as CRC32C (Castagnoli) uses a different polynomial and typically yields a different checksum for identical input bytes. When reading a protocol specification, identify the **exact CRC variant**, not just the label "CRC".

### 3.1. Standard Test Vector

For the ASCII byte sequence:

~~~text
123456789
~~~

JDK's `CRC32` produces:

~~~text
0xCBF43926
~~~

This is a very common *test vector* for catching mismatched polynomials, initial values, reflection, or final XOR. In Java, `getValue()` returns a non-negative `long` holding the lower 32 bits; format with `%08X` to print all eight hex digits including leading zeros.

### 3.2. Error-Detection Capabilities of CRC

A CRC with a well-chosen polynomial offers better bit-error detection than simple byte summation, particularly for *burst* errors in transmission/storage protocols. However, concrete guarantees still depend on:

- The CRC polynomial/variant.
- Maximum message length.
- Error distribution; independent bit errors differ from structured errors.
- Number of flipped bits and minimum Hamming distance of the code over the message length in question.

Never assume "CRC32 always detects every 3-bit error" or "changing a few bits is always caught" without verifying that property for the exact variant and data length. CRC is not designed to resist intentional data tampering.

## 4. How Does Adler32 Work?

Adler-32 uses **two sums modulo the prime 65521** over unsigned bytes. Initialization:

~~~text
A = 1
B = 0
MOD = 65521
~~~

For each byte valued from 0 to 255:

~~~text
A = (A + byte) mod 65521
B = (B + A) mod 65521

Adler32 = (B << 16) | A
~~~

In illustrative Java code, treat bytes as unsigned via `byteValue & 0xFF`. Both cumulative sums depend on byte order; the same bytes in reversed order can produce a different result.

Example for a single ASCII byte `'A'` with value 65:

~~~text
A = (1 + 65) mod 65521 = 66 = 0x0042
B = (0 + 66) mod 65521 = 66 = 0x0042
Adler32 = 0x00420042
~~~

For the ASCII string `123456789`:

~~~text
Adler32 = 0x091E01DE
~~~

Adler32 was chosen for ease of fast computation, though it has weaker distribution than CRC32 on many very short messages. Do not conclude it is always faster across all modern JDKs/CPUs: performance depends on implementation, SIMD/hardware support, block sizes, and memory behavior.

### 4.1. Why Does A Start at 1?

If both A and B started at 0, a sequence consisting purely of 0 bytes would yield checksum 0 for every length and suffer from undesirable degenerate cases. Initializing A=1 avoids that issue; it is a fixed parameter of the standard Adler-32 algorithm rather than an option for Java callers to change.

## 5. The `Checksum` API in Java

`CRC32` and `Adler32` implement `java.util.zip.Checksum`. Common methods:

| API | Meaning |
| --- | --- |
| `update(int b)` | Updates with **one byte**, taking the low 8 bits of the `int` parameter. |
| `update(byte[] b)` | Updates over the entire byte array. |
| `update(byte[] b, int off, int len)` | Updates over a slice starting at `off` for `len` bytes. |
| `update(ByteBuffer buffer)` | Updates with remaining bytes; advances the buffer's position per the API contract. |
| `getValue()` | Returns the current checksum as `long`; for CRC32/Adler32, the value is in the unsigned 32-bit range. |
| `reset()` | Resets the checksum to its initial state to compute over new data. |

Quick example:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.zip.CRC32;

byte[] bytes = "abc".getBytes(StandardCharsets.US_ASCII);
CRC32 crc = new CRC32();
crc.update(bytes, 0, bytes.length);
long result = crc.getValue();
System.out.printf("CRC32=%08X%n", result);
~~~

This is an **illustrative fragment placed inside a method**. `getValue()` does not reset state: you can inspect intermediate values after each chunk. Calling `update(...)` repeatedly across consecutive slices is equivalent to computing over the entire byte sequence in the same order.

**Important note on `update(int)`:** `crc.update(256)` does not feed four bytes of an integer 256; per contract, it feeds only the low byte `0x00`. To checksum binary data containing a 32-bit integer, choose a byte order, convert it to four exact bytes, and update with that byte array/`ByteBuffer`.

## 6. Complete Java 17+ Example: CRC32, Adler32, Chunking, and Detecting Modification

The example uses the `123456789` test vector, intentionally reading via `ByteArrayInputStream` with a 4-byte buffer to yield three chunks: 4 + 4 + 1. It then compares single-shot calculation against incremental calculation, verifies `reset()`, and flips one byte to simulate accidental corruption.

Save file `ChecksumDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.zip.Adler32;
import java.util.zip.CRC32;
import java.util.zip.Checksum;

public class ChecksumDemo {

    static long calculate(Checksum checksum, byte[] data, int chunkSize)
            throws IOException {
        checksum.reset();

        try (ByteArrayInputStream input = new ByteArrayInputStream(data)) {
            byte[] buffer = new byte[chunkSize];
            int n;
            while ((n = input.read(buffer)) != -1) {
                checksum.update(buffer, 0, n);
            }
        }
        return checksum.getValue();
    }

    static String hex32(long value) {
        return String.format(Locale.ROOT, "%08X", value);
    }

    public static void main(String[] args) throws IOException {
        byte[] original =
                "123456789".getBytes(StandardCharsets.US_ASCII);

        long crc = calculate(new CRC32(), original, 4);
        long adler = calculate(new Adler32(), original, 4);

        System.out.println("bytes=" + original.length);
        System.out.println("crc32=" + hex32(crc));
        System.out.println("adler32=" + hex32(adler));

        // Different chunk sizes, while byte order and contents remain unchanged.
        long crcOneChunk =
                calculate(new CRC32(), original, original.length);
        long adlerOneByteAtATime =
                calculate(new Adler32(), original, 1);

        System.out.println("crcChunksEqual=" + (crc == crcOneChunk));
        System.out.println("adlerChunksEqual=" +
                (adler == adlerOneByteAtATime));

        byte[] changed = original.clone();
        changed[0] = (byte) 'X';

        long crcChanged = calculate(new CRC32(), changed, 4);
        long adlerChanged = calculate(new Adler32(), changed, 4);

        System.out.println("crcDetectsChange=" + (crc != crcChanged));
        System.out.println("adlerDetectsChange=" + (adler != adlerChanged));

        CRC32 reusable = new CRC32();
        reusable.update(changed, 0, changed.length);
        reusable.reset();
        reusable.update(original, 0, original.length);

        System.out.println("resetReusesInstance=" +
                (reusable.getValue() == crc));
    }
}
~~~

Compile and run commands:

~~~bash
javac ChecksumDemo.java
java ChecksumDemo
~~~

**Deterministic stdout for the program's data:**

~~~text
bytes=9
crc32=CBF43926
adler32=091E01DE
crcChunksEqual=true
adlerChunksEqual=true
crcDetectsChange=true
adlerDetectsChange=true
resetReusesInstance=true
~~~

### 6.1. Code Explanation

1. `ByteArrayInputStream` feeds data from a 9-byte array. The 4-byte temporary buffer reads three times; each `checksum.update(buffer, 0, n)` call **uses only the `n` bytes actually read**.
2. `Checksum.reset()` before processing ensures data from a prior computation does not leak into the new one.
3. `crc32=CBF43926` and `adler32=091E01DE` match the standard test vectors for ASCII `123456789`.
4. Passing identical content into `update` across different chunk sizes in the same byte order yields identical results.
5. Changing the first character from `'1'` to `'X'` changes both checksums in **this specific case**. This illustrates error detection, **not a proof that every byte change is always detected**.
6. `resetReusesInstance=true` confirms a `CRC32` instance can be reused after `reset` without carrying over previously processed data.

In the example, `calculate` accepts any `Checksum` implementation. That lets the same streaming logic work for both `CRC32` and `Adler32`, avoiding two separate loops.

## 7. Computing a Large File's Checksum Without Loading It All into RAM

For real files, avoid `Files.readAllBytes(path)` on very large files since it requires memory proportional to the entire file. Streaming lets you use a fixed buffer.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.zip.Checksum;
import java.util.zip.CRC32;

public final class FileChecksumExample {
    public static long crc32(Path file) throws IOException {
        Checksum checksum = new CRC32();
        byte[] chunk = new byte[8192];

        try (InputStream input = Files.newInputStream(file)) {
            int n;
            while ((n = input.read(chunk)) != -1) {
                if (n > 0) {
                    checksum.update(chunk, 0, n);
                }
            }
        }

        return checksum.getValue();
    }
}
~~~

This snippet is a **compilable utility class** once saved as `FileChecksumExample.java`; it has no `main` method, so there is no standalone `java FileChecksumExample` run command. To use it, call `FileChecksumExample.crc32(path)` from an appropriate program.

Important points:

- Pass the returned `n` instead of always passing `chunk.length`. The final read may return fewer than 8192 bytes; the remainder of the array still holds stale data.
- Temporary memory is `O(chunkSize)`, independent of file size.
- The checksum is computed over **the bytes actually read**. If the file is modified concurrently while being read, the result can reflect a mix of bytes from different points in time; a checksum does not create a consistent snapshot.
- Recomputing the checksum of the same file repeatedly is meaningful only when data is held stable or the workflow tolerates concurrent changes.
- If an application needs to verify a downloaded file, it must have a trusted **expected** checksum or another authentic source. Reading a file, computing its checksum, and storing that checksum in the same untrusted place does not prove the file matches the original.

## 8. Checksums and Compression/Archiving: ZIP, GZIP, and zlib

Compression formats commonly include metadata to detect corrupted data after decompression. CRC32 and Adler32 **are not compression algorithms**: they do not shrink data; they only compute a short check value.

### 8.1. ZIP: CRC32 per Entry

In the ZIP format, each entry carries metadata including the CRC32 of **uncompressed data**, compressed size, and uncompressed size. Java supports ZIP via `ZipOutputStream`, `ZipInputStream`, `ZipFile`, and `ZipEntry`.

~~~text
archive.zip
   |
   +-- notes.txt
   |     CRC32 = checksum of decompressed notes.txt bytes
   |
   +-- image.bin
         CRC32 = checksum of decompressed image.bin bytes
~~~

With `ZipOutputStream` using `DEFLATED`, the JDK can compute the entry's CRC32 while writing. With `STORED` (uncompressed) entries, the caller must supply required metadata such as size/CRC before writing the entry per API contract.

`ZipInputStream` verifies an entry's CRC/size once the entry's entire content has been read and entry verification completes. If you read only part of an entry and stop, never assume full-entry checksum verification occurred. `ZipFile` provides random access to entries, yet if a workflow requires strict verification, the application should verify read data against the entry's expected checksum per the active API contract.

### 8.2. Example Creating a ZIP and Verifying CRC32 Yourself

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.zip.CRC32;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

byte[] text = "hello".getBytes(StandardCharsets.UTF_8);
CRC32 expected = new CRC32();
expected.update(text);

ByteArrayOutputStream archive = new ByteArrayOutputStream();
try (ZipOutputStream zip = new ZipOutputStream(archive)) {
    ZipEntry entry = new ZipEntry("hello.txt");
    zip.putNextEntry(entry);
    zip.write(text);
    zip.closeEntry();
}

System.out.printf("uncompressed-crc=%08X%n", expected.getValue());
~~~

This is an **illustrative fragment inside a method**, with necessary imports. `expected` is computed from the original bytes; `ZipOutputStream` automatically writes the CRC metadata for the `DEFLATED` entry. There is no need to append checksum bytes into `hello.txt` itself. The example omits printing archive size since size can depend on metadata and runtime implementation choices.

### 8.3. GZIP Uses CRC32

A GZIP stream has a trailer containing the CRC32 of **uncompressed data** and `ISIZE` (uncompressed size modulo `2^32`), encoded according to the GZIP multi-byte field layout. `GZIPOutputStream` writes GZIP streams; `GZIPInputStream` decompresses and checks the checksum/trailer when read completely.

Do not compute CRC32 over the **compressed `.gz` file** and compare it with the CRC stored in the GZIP trailer. The trailer protects the **pre-compression** data; those two byte sequences are different.

### 8.4. zlib Wrapper Uses Adler32

A zlib-formatted stream normally consists of a header, DEFLATE payload, and an **ADLER32** field over the uncompressed data. In Java, `DeflaterOutputStream`/`InflaterInputStream` operate on the format configured on `Deflater`/`Inflater`; distinguish:

- **Raw DEFLATE**: core compressed stream without wrapper checksum fields.
- **zlib wrapper**: contains wrapper metadata and Adler32.
- **GZIP wrapper**: contains GZIP metadata and CRC32; not interchangeable with Adler32.
- **ZIP archive**: multi-entry container where each entry has its own CRC32 and metadata.

Mixing up *wrapper formats* typically triggers errors like "incorrect header check" or "incorrect data check" during decompression. Choose the matching class/format rather than guessing based solely on the name "DEFLATE".

## 9. What Are the Limitations of Checksums?

### 9.1. Cannot Guarantee Different Data Yields Different Checksums

CRC32 and Adler32 have at most **2^32** possible outputs. Since the number of possible byte sequences longer than a few bytes is vastly larger, by the pigeonhole principle two distinct inputs must exist with the same checksum.

~~~text
Data A  -> CRC32 X
Data B  -> CRC32 X   (collision)
A != B yet CRC32(A) == CRC32(B)
~~~

For random errors modeled nearly uniformly, the probability of matching a fixed 32-bit checksum is commonly described as approximately **1 / 2^32**. Yet this **is not a guarantee independent of data, error type, or error-generation mechanism**. Specifically for CRC, error-detection properties depend on polynomial structure and message length.

If you create many objects and assign checksums as unique IDs, the probability of **at least one colliding pair** rises rapidly due to the *birthday paradox*. With nearly uniform 32-bit outputs, collision risk becomes non-trivial around tens of thousands of objects — roughly 50% at around 77,000 independent samples. In practice, CRC/Adler need not follow a uniform distribution across every dataset.

### 9.2. Does Not Prevent Intentional Modification

If an attacker alters a ZIP file and updates the corresponding CRC32 metadata, the CRC check can still pass. There is no secret in the CRC32 or Adler32 formulas: anyone who knows the bytes can recompute the checksum.

~~~text
Original file + CRC32(original)
          |
       attacker modifies payload
          |
Modified file + CRC32(new)
          |
       CRC32 check still MATCHES
       yet integrity/security is NOT guaranteed.
~~~

Therefore:

- For detecting accidental transmission/storage bit errors, CRC32 or Adler32 can be appropriate.
- For preventing unauthorized tampering, use HMAC/digital signatures or an authenticated protocol such as TLS, depending on your trust model.
- For installers or releases, verifying signatures from a trusted publisher matters far more than merely matching a checksum posted on the same untrusted channel.

### 9.3. Does Not Correct Errors or Pinpoint Corrupted Bytes

A checksum signals that **data likely differs**, without telling which byte failed or correcting the data itself. Error-correcting codes like ECC/FEC serve different purposes and use different structures.

Some protocols pair checksums with retransmission; retransmission belongs to the protocol, not to `CRC32`/`Adler32` itself.

### 9.4. Does Not Guarantee Byte Order or Scope

If the sender computes CRC over the payload alone while the receiver includes the header, or one side uses UTF-8 and the other uses UTF-16LE, results differ even when displayed text looks identical. Both sides must agree on:

- Raw byte sequence and charset.
- Inclusion or exclusion of headers, padding, delimiters, and metadata.
- Byte order and integer serialization.
- Algorithm/variant and checksum field representation in the format.
- When it is computed: over compressed or uncompressed data.

In ZIP/GZIP/zlib, use the format-specific APIs and understand **which data is checksummed** instead of rolling your own assumptions without spec guarantees.

## 10. When to Choose Which Algorithm?

| Scenario | Reasonable Choice | Reason |
| --- | --- | --- |
| Standard ZIP entry reading/writing | CRC32 via ZIP API | ZIP metadata specifies CRC32 per entry. |
| Standard GZIP reading/writing | CRC32 via GZIP API | GZIP trailer specifies CRC32. |
| Working with zlib wrappers | Adler32 per format | zlib wrappers use Adler32 over uncompressed data. |
| Internal protocol needing accidental-error detection without adversaries | Checksum per **protocol spec**, possibly CRC32/CRC32C or another type. | Match algorithm and message length uniformly. |
| Comparing downloads when checksum comes from a trusted channel | SHA-256 or spec checksum; still verify provenance. | Risk level and distribution channel dictate choice. |
| Authenticating sender and preventing tampering | HMAC or digital signature, appropriate TLS | CRC32 and Adler32 lack keys/authentication. |
| Using checksum as a unique ID across many objects | Not recommended | Only 32 bits; collisions are unavoidable. |
| Data may be modified concurrently while reading | Ensure snapshot/locking/versioning first | Checksums do not solve read consistency. |

If a protocol specifies **CRC32C**, use `java.util.zip.CRC32C` (available since Java 9), not `CRC32` expecting equivalent output. In Java 17, both have dedicated implementation classes.

## 11. Common Programming Mistakes

### 11.1. Forgetting `reset()` When Reusing an Instance

~~~java
CRC32 crc = new CRC32();
crc.update(firstBytes);
long first = crc.getValue();

crc.update(secondBytes); // Computed over firstBytes + secondBytes.
long combined = crc.getValue();
~~~

To compute a separate CRC for `secondBytes`, call `crc.reset()` before updating with them, or create a new instance. `getValue()` only retrieves the current value; it does not reset state.

### 11.2. Updating with the Whole Buffer Instead of Actual Bytes Read

~~~java
int n = input.read(chunk);
checksum.update(chunk); // Wrong if n < chunk.length.
~~~

The right approach is `checksum.update(chunk, 0, n)` after checking `n > 0`. The snippet above is not standalone: `input`, `chunk`, and `checksum` are created elsewhere.

Without checking `n`, the unwritten tail of the array from the final read still holds bytes from the previous read, corrupting the checksum.

### 11.3. Comparing Against a Negative Signed `int`

CRC32 is an unsigned 32-bit value; Java `int` is signed, while `getValue()` returns a `long` in `[0, 0xFFFFFFFFL]`. If metadata is stored in an `int` with the sign bit set, convert properly:

~~~java
long unsigned = Integer.toUnsignedLong(storedInt);
boolean matches = (checksum.getValue() == unsigned);
~~~

Never directly compare a negative signed `int` against an unsigned `long` without converting.

### 11.4. Confusing Compressed File CRC with Decompressed Data CRC

In ZIP/GZIP, metadata checksums are normally defined over **uncompressed bytes**. Calling `CRC32.update` over the raw bytes of `archive.zip` or `file.gz` usually does not yield the CRC of a ZIP entry or GZIP trailer.

### 11.5. Confusing CRC32 with CRC32C

These two variants use different polynomials; identical payloads produce different checksums. Reading a 32-bit checksum field without knowing the variant causes constant check failures or incompatible protocol encoding.

### 11.6. Using Checksums as Security

Never use a checksum as a "signature" for files downloaded from untrusted sources. You need a trusted source for the expected value and an authentication mechanism such as HMAC or digital signatures.

### 11.7. Assuming Equal Checksums Guarantee Identical Bytes

Equal checksums **do not prove byte equality**. For critical data, requirements may demand checking length, cryptographic hashes, byte-by-byte comparison, or signatures.

### 11.8. Mixing Up `ByteBuffer` State and Checksum Scope

When calling `checksum.update(ByteBuffer)`, only **remaining bytes from position to limit** are processed. If the buffer was just populated with `put`, call `flip()` before checksumming the written region; otherwise you may checksum unwritten capacity. And because `update` advances position, if you still need to read that content, use `duplicate()` or manage position deliberately.

### 11.9. Splitting Data into Chunks and Resetting Mid-Stream

To checksum an entire file, call `reset()` **once before starting**. Resetting on every chunk leaves the final result reflecting only the last chunk, not the whole file.

### 11.10. Extracting ZIPs Without Bounding Data Size

CRC does not stop **ZIP bombs** or payloads with massive decompressed sizes. When accepting archives from untrusted sources, limit entry count, total decompressed size, compression ratio, depth/processing time, and validate entry paths to prevent Zip Slip. A valid checksum does not mean a file is safe.

## 12. Practice Exercises and Self-Check Questions

1. **Are CRC32/Adler32 compression algorithms?** No. They are byte-sequence checksums and do not reduce data size.
2. **When computing CRC32 for ASCII `"123456789"`, what is the result?** `CBF43926`.
3. **What is Adler32 for that same test vector?** `091E01DE`.
4. **Does computing CRC in chunks of 4, 4, 1 bytes differ from computing over all 9 bytes at once?** No, provided byte order and bytes match and `reset` happens only at the start.
5. **Does `getValue()` automatically reset the checksum?** No. You must call `reset()` or create a new instance.
6. **How many bytes does `update(0x12345678)` feed?** One low byte `0x78`, not four bytes.
7. **Which checksum does a GZIP trailer use?** CRC32 of uncompressed data.
8. **Which checksum does a zlib wrapper use?** Adler32 of uncompressed data.
9. **Is a ZIP entry's CRC32 computed over compressed or uncompressed bytes?** Over the **uncompressed** data of the entry.
10. **Must two files with the same CRC32 be identical?** No, collisions are always possible.
11. **Can someone who modifies a file and recomputes its checksum pass a checksum check?** Yes; checksums have no secret key or authentication.
12. **If you need sender verification and tamper resistance, what should you consider?** HMAC, digital signatures, or authenticated protocols like TLS, paired with trusted key management.
13. **Why is `Files.readAllBytes` not the default for very large files?** It requires memory for the entire content; streaming with a fixed buffer saves RAM.
14. **Why can continuously reading a file being modified by another writer produce an unreliable checksum?** Read bytes may come from different versions; a checksum does not create a snapshot.
15. **Should CRC32 be used as a unique identifier for millions of files?** No, 32-bit space is too small, making collisions likely.
16. **Are CRC32 and CRC32C interchangeable?** No, they are two different variants.
17. **Does reading part of a ZIP entry and stopping prove the entry's checksum was fully checked?** No. You must read completely and verify per the library/format contract.
18. **Does a checksum protect against a ZIP file containing a malicious payload?** No. Content validation, resource limits, and extraction path protection are required.

## 13. Java 17 Reference Documentation

- [Checksum](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/Checksum.html): `update`, `getValue`, `reset`.
- [CRC32](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/CRC32.html) and [CRC32C](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/CRC32C.html): distinguishing the two CRC variants.
- [Adler32](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/Adler32.html): Adler-32 checksum.
- [ZipInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipInputStream.html), [ZipOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipOutputStream.html), [GZIPInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPInputStream.html): working with corresponding compression formats.

**Remember:** `CRC32` and `Adler32` are 32-bit checksums for catching many unintentional data errors, not security mechanisms. Both implement `Checksum`, enabling incremental computation over streams; ZIP/GZIP typically use CRC32, whereas zlib wrappers use Adler32. Always compare **exact byte sequences, exact variants, and trusted expected values**, and use HMAC/digital signatures when intentional tampering must be prevented.
