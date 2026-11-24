# 4.3. The `update`, `digest`, `reset` Cycle and Multi-Part Data Processing

## Objectives

This lesson explains how to use `java.security.MessageDigest` in the Java Cryptography Architecture (JCA) to hash a message in multiple parts, compute the final digest, explicitly discard state, and hash large data without loading the entire file into RAM.

After this lesson, you will be able to:

- Explain the **`update` → `digest` → automatic reset** lifecycle, and distinguish it from an explicit `reset()` call by the programmer.
- Feed data using `byte[]`, slices with `offset/len`, and `ByteBuffer` without hashing extra bytes.
- Hash a file or `InputStream` in chunks and demonstrate that the digest does not depend on chunk size as long as the input bytes are identical.
- Understand the exact differences between `digest()`, `digest(byte[] input)`, and `digest(byte[] buf, int offset, int len)`.
- Avoid improper state reuse, data boundary confusion, and common mistakes involving encoding, concurrency, stream reading, and security.

Examples use **Java 17+** and **SHA-256**. `SHA-256` takes byte input and produces a 256-bit output (= 32 bytes, typically displayed as 64 hex characters). The examples focus on the API and state management, not implementing the SHA-256 algorithm from scratch.

## 1. `MessageDigest` Is a Stateful Engine

Call the factory:

```java
MessageDigest md = MessageDigest.getInstance("SHA-256");
```

The snippet assumes `import java.security.MessageDigest;` and handles `NoSuchAlgorithmException`. JCA selects an implementation from a suitable registered provider. The new object holds **the state of an empty message**.

Call `md.update(...)` to feed bytes into the state, in **order**. Call `md.digest()` once all data has been fed to **finalize the hash**, receive the digest array, and simultaneously have the engine **automatically reset** to its initial state. Call `md.reset()` if you want to **discard already-fed data** without obtaining a result.

```text
New MessageDigest (empty message)
              |
      update(part 1)
              |
      update(part 2)
              |
      update(part n)
              |
           digest()
              |
              +----> returns digest of (part1 || part2 || ... || partN)
              |
              v
      state returns to empty
              |
      ready for the next message
```

At any point before `digest()`:

```text
update(part1) -> update(part2) -> reset()
                                    |
                                    v
                          discards fed data
                          empty state, no digest
```

Therefore:

- `update("ab"); update("c"); digest()` hashes **`abc`**.
- `update("ab"); digest("c")` also hashes **`abc`**: `digest(byte[] input)` feeds `input` first and then finalizes.
- `update("ab"); reset(); digest("c")` hashes **`c`**, because `ab` was discarded.
- `digest(); digest()` on the same instance: the first call hashes the current state, and the second call hashes **the empty message** because the first call reset the state.
- `digest()` does not return a "saved state"; it **terminates the message**. If you want to continue the same message, you must not call `digest()` yet.

## 2. Overloads to Distinguish

| Method | Behavior | State after the call |
| --- | --- | --- |
| `update(byte b)` | Feeds exactly 1 byte. | Keeps state, with the byte added. |
| `update(byte[] input)` | Feeds the **entire array**. | Keeps state, with the array added. |
| `update(byte[] input, int offset, int len)` | Feeds exactly `len` bytes starting at `input[offset]`. | Keeps state, with the byte slice added. |
| `update(ByteBuffer input)` | Feeds from `position` up to before `limit`; advances position to limit. | Keeps state, buffer is consumed. |
| `digest()` | Finalizes the current state. | **Automatically resets**, returns digest `byte[]`. |
| `digest(byte[] input)` | Feeds **`input`** and then finalizes. | **Automatically resets**, returns digest `byte[]`. |
| `digest(byte[] buf, int offset, int len)` | Finalizes and writes the digest into the **destination buffer** at `offset`, up to `len` bytes. | **Automatically resets**, returns number of bytes written (may throw `DigestException`). |
| `reset()` | Discards all fed state without hashing. | Empty state. |
| `getDigestLength()` | Queries the digest length in bytes. | Feeds no bytes; may return 0 if the provider cannot determine it. |

**Very easy-to-confuse overload:** the `byte[]` parameter of `digest(byte[] input)` is **input**; whereas `byte[] buf` in `digest(byte[] buf, offset, len)` is **output**. To hash a slice of an array, use `update(input, offset, len)`, followed by `digest()`.

Each `update` call appends bytes to the same message. Call boundaries are not encoded in the digest; only the **final byte sequence** matters. Thus, splitting `abc` into `a + bc` or `ab + c` yields the same SHA-256 as long as neither `digest` nor `reset` occurs in between.

## 3. Complete Program: `update`, `digest`, and `reset`

Save the file as **`DigestLifecycleDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;

public final class DigestLifecycleDemo {
    private DigestLifecycleDemo() {}

    private static byte[] utf8(String s) {
        return s.getBytes(StandardCharsets.UTF_8);
    }

    private static String hex(byte[] bytes) {
        return HexFormat.of().formatHex(bytes);
    }

    public static void main(String[] args) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");

        md.update(utf8("a"));
        md.update(utf8("b"));
        System.out.println("chunks-abc = " + hex(md.digest(utf8("c"))));

        System.out.println("after-digest-empty = " + hex(md.digest()));

        md.update(utf8("discard"));
        md.reset();
        System.out.println("after-reset-abc = " + hex(md.digest(utf8("abc"))));

        byte[] src = utf8("abc");
        md.update(src, 0, 1);
        md.update(src, 1, 2);
        System.out.println("slices-abc = " + hex(md.digest()));

        ByteBuffer buffer = ByteBuffer.wrap(utf8("__abc__"));
        buffer.position(2);
        buffer.limit(5);
        md.update(buffer);
        System.out.println("buffer-remaining = " + buffer.remaining());
        System.out.println("bytebuffer-abc = " + hex(md.digest()));

        md.update(utf8("abc"));
        byte[] destination = new byte[40];
        int written = md.digest(destination, 4, 32);
        System.out.println("written-bytes = " + written);
        System.out.println("destination-abc = " +
                HexFormat.of().formatHex(destination, 4, 4 + written));
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 DigestLifecycleDemo.java
java DigestLifecycleDemo
```

**Exact stdout:**

```text
chunks-abc = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
after-digest-empty = e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
after-reset-abc = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
slices-abc = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
buffer-remaining = 0
bytebuffer-abc = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
written-bytes = 32
destination-abc = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

How to read each result:

1. `md.update("a")` and `md.update("b")` accumulate `ab`; `md.digest("c")` **also feeds `c`**, returns SHA-256(`abc`), and resets.
2. `md.digest()` immediately afterward yields the SHA-256 of **0 bytes** (the empty message): proof that the state was reset after `digest`.
3. `md.update("discard"); md.reset(); md.digest("abc")` discards the partially fed data and hashes only `abc`.
4. `md.update(src,0,1)` and `md.update(src,1,2)` hash the exact slices `a` and `bc`, which also equals `abc`.
5. `ByteBuffer.wrap("__abc__")` contains two `_` bytes at the start and end; setting position=2 and limit=5 selects exactly `abc`. `md.update(buffer)` consumes `remaining()` and advances position to limit.
6. `md.digest(destination,4,32)` writes **32 OUTPUT bytes** starting at index 4 of the 40-byte array. `written = 32`, and `HexFormat.of().formatHex(destination,4,4+written)` prints only the written region.

Note: `HexFormat` was added in **Java 17+**. In older Java versions you can use `String.format` or custom hex formatting, but this example intentionally requires Java 17+.

## 4. Feeding Data from an `InputStream` into a Single Digest

`MessageDigest` does not care whether data comes from a byte array, a file, or a network socket: the requirement for a correct result is that every byte is passed to `update` **exactly once, in order**, before calling `digest()`. This section illustrates stream usage to demonstrate the state rules; designing, benchmarking, and testing multi-GiB files, `FileChannel`, and `ByteBuffer` are covered separately in lesson **4.4 Hashing Large Files with Streams or ByteBuffer**.

The illustrative method below accepts an already-opened `InputStream`; place it inside a class that imports `java.io.InputStream` and `java.security.MessageDigest`, handling exceptions according to the signature. This is a **method snippet**, while `DigestLifecycleDemo` in Section 3 is the standalone program for this lesson:

```java
static byte[] sha256(InputStream source) throws Exception {
    MessageDigest md = MessageDigest.getInstance("SHA-256");
    byte[] buffer = new byte[8192];
    int n;
    while ((n = source.read(buffer)) != -1) {
        if (n > 0) {
            md.update(buffer, 0, n);
        }
    }
    return md.digest();
}
```

A single `read` call can return fewer than 8192 bytes, especially on the final chunk; therefore `update(buffer, 0, n)` feeds only the bytes actually read. If replaced with `update(buffer)`, leftover bytes in the buffer would also be hashed, corrupting the digest. If `digest()` is called inside the loop, the state resets between chunks and the output is no longer the digest of the whole stream.

This method **does not close** the caller-owned source: invoke it inside `try-with-resources`, and use the result only if reading reached EOF cleanly. With a `ByteArrayInputStream` containing the exact UTF-8 bytes of `abc`, the hex result is `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad`. Changing the chunking does not change the digest as long as the byte sequence is unchanged. For sources without EOF (infinite streams), the application must determine the message boundary before finalizing.

## 5. Using `DigestInputStream` as an Alternative

The JDK includes `java.security.DigestInputStream`: bytes **read through the wrapper** are automatically fed into the attached `MessageDigest`. The snippet below belongs inside a method where `Path path` is declared and checked exceptions are handled:

```java
MessageDigest md = MessageDigest.getInstance("SHA-256");
try (DigestInputStream input =
             new DigestInputStream(Files.newInputStream(path), md)) {
    input.transferTo(OutputStream.nullOutputStream());
}
byte[] result = md.digest();
```

Required imports: `java.security.MessageDigest`, `java.security.DigestInputStream`, `java.nio.file.Files`, `java.nio.file.Path`, and `java.io.OutputStream`.

`transferTo(OutputStream.nullOutputStream())` reads the entire file through the wrapper without keeping the whole file in RAM. `DigestInputStream` feeds bytes **as they are read**, rather than finalizing the hash in the constructor or `close()`; therefore you must call `md.digest()` after reading finishes. If you read only a prefix and stop, the digest reflects only that prefix; reading directly from the underlying stream (bypassing the wrapper) also omits those bytes from the wrapper's digest. The wrapper can save code, while a manual `update` loop gives clearer control over byte counts and data boundaries.

## 6. `ByteBuffer` Details and Data Boundaries

### `position`, `limit`, and `remaining`

`MessageDigest.update(ByteBuffer)` hashes bytes in the buffer's current `[position, limit)` range; afterward `position` advances to `limit`, without hashing unused capacity. With NIO, you typically must call `flip()` after writing into a buffer to switch from write mode to read mode. Forgetting `flip()` or setting the wrong `limit` can hash the wrong bytes.

When you want to preserve the original buffer's position, you can pass a **duplicate**:

```java
ByteBuffer view = original.duplicate();
md.update(view);        // Modifies view's position; original retains its position.
```

This snippet assumes `original` of type `ByteBuffer` and `md` of type `MessageDigest` already exist. `duplicate()` creates an independent view for position/limit while **still sharing the underlying byte storage**, without copying backing data; do not let another thread modify the contents concurrently. For direct or read-only `ByteBuffer`s, the semantics of position/limit and `update` are the same.

### Chunk Boundaries Are Not Encoded

If two programs feed the same byte stream `abc`—one calling `update("a"); update("bc")` and the other calling `update("ab"); update("c")`—the digests are identical. Do not assume the number of `update` calls preserves field boundaries.

For example, when hashing a record by directly concatenating UTF-8 strings: both pairs (`"ab"`, `"c"`) and (`"a"`, `"bc"`) yield the byte sequence `abc`. To distinguish them, you must use a **structured record encoding format**, such as feeding each field's length as a fixed-size integer before feeding the field's bytes. When encoding lengths, count **encoded bytes**, not `String.length()` (which counts UTF-16 code units).

**When hashing multiple independent messages**, each message requires its own finalization. `update(A1); update(A2); digest()` hashes message A; then `update(B1); digest()` hashes message B. If you want to branch two hashes that share a common prefix, consider `clone()` **only if the provider supports it**, or create two instances and re-feed the prefix, because `reset()` does not save checkpoints.

## 7. Text, Encoding, and Reproducibility

`MessageDigest` operates solely on **bytes**. Different representations of the same visually displayed text can produce different bytes:

- Different encodings, such as UTF-8 vs. UTF-16.
- Different Unicode normalization forms.
- Line endings `\n` (LF) vs. `\r\n` (CRLF).
- Whitespace, BOM, hidden characters, byte order, or passing data through a text decoder/encoder layer.

Always choose an explicit encoding when converting strings:

```java
byte[] data = text.getBytes(StandardCharsets.UTF_8);
md.update(data);
```

This snippet assumes `text` is a `String` and `md` has been created. Avoid `String.getBytes()` without a charset when consistent byte output across runtimes is needed. In particular, to verify the hash of a **binary file**, hash the file's bytes directly rather than converting them to a `String` and re-encoding. To match digests between two systems, agree on the **exact byte representation** before inspecting providers or hash code.

## 8. Reuse and Real-World Pitfalls

### When Do You Need to Call `reset()`?

- **Not needed** between two hashes completed with `digest()`: JCA resets automatically.
- **Needed** if you want to discard partially fed state and start a new message on the same instance.
- **Do not use** to finalize a digest, checkpoint state, or attempt to securely erase sensitive data from the heap; `reset()` does not guarantee memory wiping.

### Concurrency and Ownership

`MessageDigest` is a **mutable** object. Never assume it is safe for multiple threads to call `update`/`digest` concurrently; state can interleave across messages, causing unpredictable results. The simplest pattern is **one dedicated instance per hashing operation**, or maintaining strict synchronized ownership. For workloads requiring optimization, measure instance creation cost and design a clear lifecycle before considering pooling. Do not use `clone()` unless provider support has been verified.

### Read Errors or Concurrent Source Modification

If an `InputStream` fails mid-read, the hash of the partially received bytes must not be treated as the hash of the whole. Report the error and discard the instance; if reusing the instance, reset it before the next operation. If a file is modified while being read, the hash may span an inconsistent state even if `read` throws no exception. For tasks requiring consistency, control the source or how the input snapshot is captured.

### A Digest Is Not Authentication

Plain `SHA-256` provides a byte fingerprint and does not prove who sent the data: anyone who can alter the payload can also recompute the hash. For integrity requirements **with a secret key**, consider `Mac`/HMAC; for password storage, use a salted password-hashing scheme with appropriate cost rather than plain SHA-256. These differ in security goals, while leaving the `update/digest/reset` rules unchanged.

## 9. Common Mistakes Table

| Mistake / Bug | Symptom | Correct Fix |
| --- | --- | --- |
| Calling `digest()` on every `read` iteration | Produces multiple per-chunk hashes; state resets continuously. | `update` for all blocks, `digest` once after reading finishes. |
| Calling `update(block)` with a reused array | Final block includes stale bytes; wrong hash. | Use `update(block, 0, n)` accurately. |
| Calling `reset()` between two parts of one message | The first part is discarded. | Call `reset` only when intentionally aborting an incomplete hash. |
| Calling `digest()` and then continuing `update` | Subsequent parts become a new message. | Finalize only after all parts are fed. |
| Assuming `digest(bytes)` discards previously fed data | Hash accidentally combines pending state and `bytes`. | Create a new instance or reset if you need to hash only `bytes`. |
| Mistaking `digest(out, off, len)` for an input update | Fails to feed the desired input into state. | Use `update(input, off, len)`; that `digest` overload writes output. |
| Forgetting `ByteBuffer.flip()` or mismanaging position/limit | Hashes an unintended memory region. | Check `remaining()` before `update`. |
| Using `String.length()` as the byte length of a UTF-8 field | Wrong length prefix, ambiguous record encoding. | Encode to bytes first and use `byte[].length`. |
| Not fixing charset/line-ending normalization | Digests differ across environments. | Standardize exact bytes/encoding/protocol. |
| Sharing an instance across threads | State races/interleaves. | Dedicated instance per hashing operation. |
| Returning a hash as complete when a stream fails | Hash covers only a prefix. | Discard the result, report the error, and reinitialize cleanly. |
| Treating a plain hash as sender authentication | Cannot stop forgery if an attacker alters both data and hash. | Use HMAC or digital signatures as required by the security model. |

## 10. Check Your Understanding

1. Create two independent SHA-256 instances. Instance A calls `update("a")`, `update("bc")`, `digest()`; instance B calls `digest("abc")`. Why are their outputs identical? Under what condition would they differ?
2. Feed `a`, call `reset()`, feed `bc`, then call `digest()`. Compare against SHA-256(`abc`) and SHA-256(`bc`) to confirm the prefix was discarded.
3. Write a `main` method calling `sha256(InputStream)` from Section 4 on the same data with buffer sizes 1, 7, 8192, and 65536 bytes; explain why the digest must stay unchanged and identify the bug in `read`/`update` if it differs.
4. Use a `ByteBuffer` containing `__abc__`, set `position=2` and `limit=5`, and verify the result against `digest("abc")` on another instance. Check `position` after `update`.
5. Create a 40-byte output array, feed `abc`, and call `digest(output, 4, 32)`. Explain the return value 32 and which region holds the digest. Try a smaller output slice to observe the exception.
6. Explain why the two string pairs (`ab`, `c`) and (`a`, `bc`) produce the same hash when bytes are concatenated directly. Propose a length-prefixed encoding that preserves boundaries.
7. Hash a file as a binary stream and compare the result with a standalone SHA-256 tool on your machine. If there is a mismatch, check for concurrent file modification, byte count, encoding, BOM, and line endings.

You have met the objectives when you can explain that **`update` accumulates**, **`digest` finalizes and auto-resets**, **`reset` discards uncommitted data**, and chunking uses **exact bytes read**, keeping the digest invariant when only the chunk size changes.

## Official Java 17 Documentation

- [`MessageDigest`: `update`, `digest`, `reset`, `getDigestLength`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html)
- [`DigestInputStream`: updates a digest when reading through a wrapper](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/DigestInputStream.html)
- [`InputStream`: `read`, `transferTo`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html)
- [`ByteBuffer`: `position`, `limit`, `remaining`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [JCA Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html)
