# Verifying Integrity with Hashes When the Problem Requires It (Java I/O)

When an application reads, copies, downloads, extracts, or stores files, the crucial question is sometimes not merely **whether I/O finished**, but also: **“Are the bytes received the exact bytes we expected?”**. When the problem requires detecting altered content, missing bytes, mixed bytes, or the wrong version, you can use a **cryptographic hash function** such as SHA-256 to compute a **digest** of the data and compare it against a reference digest.

However, **a hash is not the solution to every security problem**. A SHA-256 value only verifies a match when you have a **sufficiently trusted reference digest**; if an attacker can replace both the file **and the attached hash**, the comparison will still pass for the tampered data. When you need to authenticate who created the data, use an HMAC/digital signature with proper key management and source authentication.

This article covers: choosing the right time to hash, differences between hash/CRC/HMAC/signatures, computing streaming SHA-256 with `MessageDigest`, `DigestInputStream`, `FileChannel`, and `ByteBuffer`, verifying after copying, handling concurrently modified data, I/O cost, security, and Java 17+ exercises.

## 1. What Is a Hash and What Does It Verify?

A cryptographic hash function `H` takes a byte sequence of arbitrary length and produces a fixed-length digest:

```text
Source bytes                   SHA-256                      32-byte Digest
"abc" (ASCII)          ──────────────────────>    ba7816bf8f01cfea...
"abd" (ASCII)          ──────────────────────>    a52d159f262b2c6d...

When verifying:
actual = SHA-256(bytes actually read)
expected = authenticated/trusted reference digest
PASS only when actual and expected match.
```

SHA-256 produces a **256-bit = 32-byte** output, commonly displayed as **64 hexadecimal characters**. It is not a reversible compression algorithm: you cannot “decrypt a hash” to recover the file. A small change in the input typically changes the digest dramatically.

Properties of a good cryptographic hash function include resistance to preimage, second-preimage, and collision attacks within an appropriate security margin; never write software assuming a collision is mathematically **impossible**. For SHA-256, random collision probability is negligible at ordinary practical scales, though security evaluation still depends on the threat model.

A proper verification condition must specify:

- **What is hashed**: raw file bytes, decompressed data, decrypted payload, or serialized representation?
- **When**: before copying, after copying, after downloading, before consumption, or at startup?
- **Source of the expected digest**: signed manifest, trusted database, independent hash over a secure channel, or just an unprotected `.sha256` file downloaded from the same location?
- **Action on mismatch**: refuse to use the file, delete the temporary copy, retry from a trusted source, alert, or proceed per policy?

## 2. When Do You Actually Need a Hash?

Hashing is very useful when a **byte-for-byte match** matters for a business decision:

| Scenario | How Hashing Helps | What Must Be Added |
| --- | --- | --- |
| Downloading an artifact/plugin from a release source | Checks whether the downloaded file matches the published digest. | Digest must arrive via a trusted channel or digital signature; never trust an arbitrary hash file. |
| Copying critical files | Compares source/copy to detect wrong or missing bytes. | Handle concurrently changing files, write errors, snapshots, and post-check usage. |
| Syncing, archiving, backup | Detects content drift; content-based deduplication. | Manifests, versioning, identity, recovery; hashes do not replace backups. |
| Data ingestion pipelines | Verifies payload before commit/processing. | Size limits, schema validation, auth, transactions. |
| Passing data across multiple stages | Compares input and output hashes of the same representation. | Clearly define whether valid transformations (compression, encryption, newlines) occur. |
| Cache verification | Ensures cached values correspond to expected content. | Key/versioning, race protection, and invalidation strategy. |

Do not compute SHA-256 on every file read if the problem does not need that guarantee and the CPU/I/O cost is unjustified. For example, a non-critical temporary log entry might only need write-result checks and retries; an artifact used to execute code or update software needs stronger authentication than a plain checksum.

**A hash does not replace** checking actual bytes read/written, `IOException`, close/flush, permissions, file format, schema, or input validation. A malformed file can still have a SHA-256 matching its own hash.

## 3. How Do Hash, Checksum, CRC, HMAC, and Digital Signatures Differ?

| Tool | Primary Purpose | Resists Intentional Tampering When an Adversary Can Alter Both Data and Checksum? |
| --- | --- | --- |
| Byte count / file size | Crude detection of missing data. | No. Two different files can have the same size. |
| CRC-32 (`java.util.zip.CRC32`) | Low-cost detection of accidental transmission/storage errors. | No. CRC is not a cryptographic MAC. |
| SHA-256/SHA-512 (`MessageDigest`) | Cryptographic digest for content matching. | Only meaningful for authentication if the expected digest is reliably protected. |
| HMAC-SHA-256 (`javax.crypto.Mac`) | Integrity authentication with a **shared secret key**. | Yes, provided the key is secure, the protocol is sound, and the algorithm remains suitable. |
| Digital signature (`Signature`) | Authenticates data with a private key, verified via a trusted public key. | Yes, if the public key/trust chain is properly verified. |
| AEAD (e.g., AES-GCM) | Encryption plus authentication tag over data context. | Yes, if key/nonce/AAD are used per sound design. |

An **unsafe** example claiming authenticity: downloading `program.jar` alongside `program.jar.sha256` from the same location where an attacker can modify both, then saying the file is “authenticated”. The attacker can generate a new digest for the forged file.

A more meaningful example: the application already holds an **expected SHA-256 distributed over an independent trusted channel**, or a manifest signed by the publisher with a pre-verified public key. When comparing digests, the application detects that received bytes do not match the released build.

**CRC-32** is suited for accidental-error checks in ZIPs and many protocols; never use CRC in place of SHA-256/HMAC for security decisions.

**MD5 and SHA-1** have known collision weaknesses and should not be chosen for new systems facing active adversaries. For modern file integrity checks, SHA-256 is a pragmatic default; long-term algorithm policies may need updates per organizational requirements.

## 4. Basic Java API: `MessageDigest` and SHA-256

`java.security.MessageDigest` is the standard API:

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
digest.update(new byte[] {0x61, 0x62, 0x63});
byte[] result = digest.digest();
String hex = HexFormat.of().formatHex(result);
```

This is a **snippet** requiring imports for `java.security.MessageDigest`, `java.util.HexFormat`, and handling `NoSuchAlgorithmException`. Bytes `0x61, 0x62, 0x63` are the ASCII string `abc`. In Java 17+, `HexFormat` is the standard utility for formatting/parsing hexadecimal.

Two usage modes:

- **One-shot**: `digest.digest(allBytes)`, suitable only when data is already in memory with a safe size.
- **Chunked**: call `digest.update(chunk...)` multiple times in **exact byte order**, then call `digest.digest()` once to obtain the result.

Example of incremental feeding:

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
digest.update("a".getBytes(StandardCharsets.US_ASCII));
digest.update("bc".getBytes(StandardCharsets.US_ASCII));
byte[] result = digest.digest(); // Same SHA-256 as bytes "abc".
```

This is a snippet requiring imports and checked-exception handling. There is no need to concatenate all chunks into one large array: `MessageDigest` maintains hash state incrementally.

**Watch the lifecycle:** `digest()` completes the computation and resets the digest state per the API contract. Calling `update` again after `digest()` hashes a brand-new message rather than continuing the old one. `MessageDigest` is also not automatically thread-safe: use a separate instance per thread/task unless explicitly synchronized.

## 5. Hash of Bytes, Not “Visually Identical Characters”

SHA-256 operates on a **byte sequence**. For text, the exact same displayed sentence can have different bytes due to:

- Charset: UTF-8, UTF-16, legacy code pages.
- Unicode normalization: NFC and NFD can represent accented characters differently.
- Line endings: `\n`, `\r\n`, or files with a BOM.
- Trailing whitespace, tabs, differing encodings, extra/missing bytes.
- JSON with reordered keys, spacing, or number serialization; XML has its own canonicalization.

Example:

```java
byte[] a = "abc".getBytes(StandardCharsets.UTF_8);
byte[] b = "abc\n".getBytes(StandardCharsets.UTF_8);
// Two arrays of different lengths, so SHA-256 must be computed independently.
```

This is a snippet. If the requirement is **file integrity**, hash the **raw bytes** as actually stored; do not read text and re-serialize it to normalize without an explicit requirement. If the problem requires equivalence of **logical content**, define clear canonicalization rules and apply them identically on both publisher and receiver before hashing.

For compressed/encoded formats, specify whether the hash covers:

1. **ZIP/compressed bytes** (verifies the exact archive received), or
2. **Decompressed entry bytes** (verifies the exact original content), or
3. **Parsed/canonicalized objects** (verifies logical equivalence).

Those three digests are not interchangeable. A ZIP rebuilt with different timestamps can have a different raw archive hash even when the file payloads are identical.

## 6. Streaming Hashes of Large Files with `DigestInputStream`

Do not use `Files.readAllBytes(file)` on very large or untrusted files just to compute SHA-256. Read in chunks and update the digest:

```java
// Snippet: file is a readable, validated Path.
MessageDigest digest = MessageDigest.getInstance("SHA-256");
try (InputStream in = new DigestInputStream(
        Files.newInputStream(file), digest)) {
    byte[] buffer = new byte[8192];
    while (in.read(buffer) != -1) {
        // DigestInputStream already updated the digest for the actual bytes read.
    }
}
byte[] actual = digest.digest();
```

The snippet above requires imports for `java.io.InputStream`, `java.security.DigestInputStream`, `java.security.MessageDigest`, `java.nio.file.Files`, and exception handling. `DigestInputStream` updates the digest **during `read`**, so you must not call `digest.update(buffer)` again; doing so would hash the bytes **twice** and produce a wrong result.

If using a plain `InputStream` directly:

```java
try (InputStream in = Files.newInputStream(file)) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = in.read(buffer)) != -1) {
        if (n > 0) {
            digest.update(buffer, 0, n);
        }
    }
}
```

This snippet uses a fresh, unfinalized `digest`; reading logic must match the stream type. Always use **`n`**, never update the whole `buffer` array: the final read usually yields fewer bytes than `buffer.length`, and the tail still holds old bytes from the previous read that do not belong to the new data.

Chunk sizes such as 8 KiB or 64 KiB affect performance, not the hash result, provided the exact same byte sequence and order are fed.

## 7. `FileChannel` and `ByteBuffer`: Hashing the Exact Bytes Written Out

With NIO, `FileChannel.read(ByteBuffer)` advances `position` by the actual bytes read; after `flip()`, the range `[position, limit)` holds the newly received data. To **copy and hash simultaneously**, create a view of the chunk to feed the digest without advancing the `position` of the original buffer used for `FileChannel.write()`:

```java
// Snippet: in/out are FileChannels; chunk is a ByteBuffer in write phase.
int n = in.read(chunk);
if (n > 0) {
    chunk.flip();
    digest.update(chunk.asReadOnlyBuffer()); // View has its own position.
    while (chunk.hasRemaining()) {
        int written = out.write(chunk);
        if (written == 0) {
            throw new IOException("Không có tiến triển khi ghi");
        }
    }
    chunk.clear();
}
```

This is a snippet; for ordinary blocking files, a fail-fast policy when `write` returns 0 avoids busy loops. Do not copy this policy verbatim to a non-blocking `SocketChannel`: `write() == 0` can be a normal state requiring waiting for `OP_WRITE`.

Key points:

- `asReadOnlyBuffer()` creates a **view sharing the same bytes with an independent position/limit** from the original buffer; `digest.update(ByteBuffer)` consumes the view from position to limit.
- `FileChannel.write(chunk)` still sees the original position at 0 and writes **the exact bytes that were hashed**.
- Because `write` can be partial, loop `while (chunk.hasRemaining())` before calling `clear()`.
- If `n == -1`, that is EOF; stop. If `n == 0` on a blocking file read while the buffer still has space, the application needs a no-progress policy.
- Never hash the full buffer capacity instead of the actual data just read.

**Safety limitation:** a digest computed during copy confirms the byte sequence the application **attempted to write**, without guaranteeing those bytes actually persist in the destination file after a system crash or modification by another process. If deciding whether to consume the destination file, **re-read the destination file to hash it and compare against the reference digest** before committing/consuming per policy.

## 8. Standalone Runnable Java 17+ Example: Copy, Verify, Detect Tampering

This exercise uses the known-answer vector `SHA-256("abc")` with the standard hex value:

```text
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

The program creates two temporary files, writes `abc` to the source file, uses `FileChannel` and a **2-byte** buffer to force multi-pass chunk processing, and computes SHA-256 while copying. It then checks the source digest and destination digest. Finally, it changes the destination data to `abd` to prove the digest no longer matches. In the example, the reference SHA-256 is **hardcoded for practice**; in real applications, obtain the expected value from a verified source.

Save as **`FileHashIntegrityDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.DigestInputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public class FileHashIntegrityDemo {
    private static final String TRUSTED_SHA256 =
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";

    private static MessageDigest newSha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException impossibleOnStandardJdk) {
            throw new IllegalStateException(impossibleOnStandardJdk);
        }
    }

    private static byte[] sha256(Path file) throws IOException {
        MessageDigest digest = newSha256();
        try (InputStream stream = new DigestInputStream(
                Files.newInputStream(file), digest)) {
            byte[] chunk = new byte[8192];
            while (stream.read(chunk) != -1) {
                // DigestInputStream updates the digest as bytes are read.
            }
        }
        return digest.digest();
    }

    private static byte[] copyAndHash(Path source, Path target)
            throws IOException {
        MessageDigest digest = newSha256();
        ByteBuffer chunk = ByteBuffer.allocate(2);
        try (FileChannel in = FileChannel.open(source,
                     StandardOpenOption.READ);
             FileChannel out = FileChannel.open(target,
                     StandardOpenOption.WRITE,
                     StandardOpenOption.TRUNCATE_EXISTING)) {
            while (true) {
                int n = in.read(chunk);
                if (n == -1) break;
                if (n == 0) throw new IOException("Read without progress");
                chunk.flip();

                // Read-only duplicate has independent position.
                digest.update(chunk.asReadOnlyBuffer());
                while (chunk.hasRemaining()) {
                    if (out.write(chunk) == 0) {
                        throw new IOException("Write without progress");
                    }
                }
                chunk.clear();
            }
        }
        return digest.digest();
    }

    public static void main(String[] args) throws IOException {
        Path source = Files.createTempFile("hash-src-", ".txt");
        Path target = Files.createTempFile("hash-dst-", ".txt");
        try {
            Files.writeString(source, "abc", StandardCharsets.US_ASCII);
            byte[] expected = HexFormat.of().parseHex(TRUSTED_SHA256);
            byte[] copiedDigest = copyAndHash(source, target);
            System.out.println("sha256=" +
                    HexFormat.of().formatHex(copiedDigest));
            System.out.println("source-valid=" +
                    MessageDigest.isEqual(expected, sha256(source)));
            System.out.println("copied-valid=" +
                    MessageDigest.isEqual(expected, copiedDigest));
            System.out.println("destination-valid=" +
                    MessageDigest.isEqual(expected, sha256(target)));

            Files.writeString(target, "abd", StandardCharsets.US_ASCII,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING);
            System.out.println("after-tamper-valid=" +
                    MessageDigest.isEqual(expected, sha256(target)));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 FileHashIntegrityDemo.java
java FileHashIntegrityDemo
```

Stdout verified by compiling and running on JDK 17+:

```text
sha256=ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
source-valid=true
copied-valid=true
destination-valid=true
after-tamper-valid=false
```

**Explanation:**

1. `Files.writeString(source, "abc", US_ASCII)` writes the exact three bytes `61 62 63`. The standard digest is used as expected from a known test vector.
2. `copyAndHash` opens two `FileChannel`s inside `try-with-resources`, reads at most two bytes per iteration, and updates `MessageDigest` via a read-only view.
3. `while (chunk.hasRemaining())` ensures each chunk is transferred completely to the destination file according to `ByteBuffer` position before reading the next chunk.
4. `MessageDigest.isEqual` compares two raw digest arrays. `source-valid=true` and `copied-valid=true` indicate that the source data and the bytes passed through the copy pipeline match `expected`.
5. `destination-valid=true` because the program **re-reads the destination file** and hashes it independently; this adds a verification step beyond merely trusting the written byte count.
6. When `abc` is replaced with `abd`, the destination file's digest changes; comparing against the old `expected` produces `after-tamper-valid=false`.
7. Both temporary files are deleted in `finally`, with channels/input streams safely closed before cleanup.

**Demo limitation:** only a single program operates on the temp files, with no concurrent external writers. It properly demonstrates hashing and matching, **without** automatically guaranteeing TOCTOU immunity, fsynced durability, or immutability after the check time. In production, see the lifecycle and trust-source sections below.

## 9. Comparing Digests Properly and Parsing Expected Hashes

An actual SHA-256 digest is **32 bytes**. When the reference comes in hex form, validate length/encoding before use:

```java
// Snippet: expectedHex comes from a verified manifest.
String expectedHex = expectedHexFromTrustedManifest;
if (!expectedHex.matches("[0-9a-fA-F]{64}")) {
    throw new IOException("Expected SHA-256 không hợp lệ");
}
byte[] expected = HexFormat.of().parseHex(expectedHex);
byte[] actual = sha256(downloadedFile);
if (!MessageDigest.isEqual(expected, actual)) {
    throw new IOException("Integrity check failed");
}
```

This is a snippet with `downloadedFile`, `expectedHexFromTrustedManifest`, and `sha256(...)` declared externally; `HexFormat` is included in Java 17. If the manifest specifies `SHA-512`, the digest length differs; never guess the length from an arbitrary hash string.

`MessageDigest.isEqual(byte[], byte[])` is a cleaner digest-comparison utility than building strings and branching manually; never claim from this API alone that the whole workflow has perfect timing side-channel resistance. When authentication uses secrets and timing-sensitive protocols, follow thoroughly reviewed MAC/signature designs.

Compute the **hash with a fresh `MessageDigest` per object/task**; avoid sharing a global instance updated concurrently by multiple threads. When logging hashes, include the algorithm, schema version, file/version identity, and context; never accidentally use plain digests as password hashing or secret token storage.

## 10. Where Are Hashes Stored and Where Does Trust Come From?

Decision table:

| Expected Hash Obtained From | Trustworthy Against File Tampering? | Reason |
| --- | --- | --- |
| SHA-256 downloaded alongside from an attacker-controlled URL | **No**. | Adversary can forge both the file and the hash simultaneously. |
| Hash in a trusted DB with access control/auditing | Usable, depending on DB protection and hash-generation workflow. | Integrity of the reference is the decisive factor. |
| Hash hardcoded in a reliably distributed application build | Usable for a specific artifact/version. | The hash itself does not protect the app binary from modification. |
| Digitally signed manifest with pinned/reliably verified public key | Suitable for publisher authentication if protocol and keys are sound. | Signature protects the manifest hashes and bound metadata. |
| HMAC of payload with an unexposed secret key | Suitable for authentication among parties sharing the key. | Unsuitable if any public recipient must verify without knowing the secret. |

Bind the digest to the right **object**. If you only have a list of SHA-256 hashes without knowing which digest corresponds to which artifact name, version, size, or context, the verifier might accept a valid file of the **wrong version**. A manifest should authenticate logical path, version, algorithm, digest, and critical identifying metadata as needed.

**A standalone hash does not prove who the sender is.** It is merely a deterministic calculation over bytes; **source trust** comes from protected manifests, MACs, signatures, TLS/authentication, and properly designed access controls.

## 11. HMAC and Digital Signatures When Forgery Resistance Is Required

When two systems share a **secret key**, HMAC verifies that data was produced by a key holder and was not altered in transit:

```java
// Illustrative snippet: secret is a byte[] retrieved from a secure key store,
// never hardcode keys in code or logs.
Mac mac = Mac.getInstance("HmacSHA256");
SecretKeySpec key = new SecretKeySpec(secret, "HmacSHA256");
mac.init(key);
byte[] tag = mac.doFinal(payload);
```

The snippet requires `javax.crypto.Mac`, `javax.crypto.spec.SecretKeySpec`, and exception handling; `payload` is bytes. Do not reuse the same secret key across unrelated purposes; define a protocol binding identity/version/nonce or context per threat model. A valid HMAC alone does not prevent replay if the application accepts repeated copies of the same message without checking sequence/expiry/idempotency.

When distributing to many verifiers **without** sharing a private key, use **digital signatures**. The publisher signs a structured manifest or digest; recipients verify the signature with the right public key/trust chain. Never fetch the public key from the same unauthenticated source and consider forgery solved.

**Do not invent signatures by writing `SHA-256(key || message)`.** Use standardized HMAC or signature algorithms and standard crypto libraries. For storing passwords, never use plain SHA-256: password hashing requires salts and specialized algorithms with appropriate work factors (e.g., Argon2id, scrypt, PBKDF2 per policy).

## 12. Hashes in a Safe Download/Copy Workflow

A template workflow for publishing a target file:

```text
verified expected hash + identity/version
             |
             v
Create TEMP target file in a controlled directory/permissions
             |
             v
Download or copy bytes in chunks, check n and quota
             |
             v
Close/flush resources, check for I/O errors
             |
             v
Re-hash temp file, compare with expected SHA-256
             |
     +-------+--------+
     |                |
  MISMATCH           MATCH
     |                |
Delete/quarantine  As required: force/sync and atomically publish
Do not commit      verified file, manage access permissions
                      |
                      v
                Consumers use that exact version
```

Principles:

1. Write to a **temporary file not yet visible to clients as a valid artifact**; never overwrite production files directly before verification.
2. Use a trusted expected digest obtained via a separate mechanism or signed manifest.
3. Process the file only after verifying the actual digest matches; failures must **fail closed** for critical data.
4. Choose a publish mechanism with platform-appropriate atomicity, such as `Files.move(..., ATOMIC_MOVE)` if supported by the provider and replacement contract matches. Handle `AtomicMoveNotSupportedException`, permission errors, and different target-replacement semantics.
5. If durability across power loss is needed, consider `FileChannel.force(true)` on the file and whatever directory sync mechanism the OS/provider allows. Atomic rename does not automatically mean data was fsynced.
6. Prevent other producers from modifying the temp file after checking; coordinate ownership, access permissions, lock/rename, and consumption timing.

**TOCTOU:** checking a hash at T1 and then re-reading the same path at T2 **does not guarantee** the bytes remain unchanged if the file was replaced/overwritten between those times. Prefer storing verified files in policy-immutable areas, using versioned/content-addressed storage identifiers, managing handles and write permissions, and verifying close to use time when needed.

## 13. Source Data Changing During Hashing/Copying

A hard case arises when a file is large and another writer is updating it concurrently:

```text
T0: SHA-256 starts reading file X
T1: Another writer modifies the middle of X
T2: SHA-256 reads the remainder
T3: Resulting digest comes from a byte stream that may not
    correspond to a consistent snapshot of the file at any point in time.
```

Important notes:

- Chunked file reading does not provide **snapshot isolation**.
- Checking `Files.size()` and `Files.getLastModifiedTime()` before/after can assist in detecting changes, but it is not a safety proof: timestamps have coarse granularity, can be altered, and a file can change and change back.
- `FileChannel.lock()` works according to OS/filesystem rules and writer cooperation; it does not guarantee every program obeys it.
- If you need the hash of an **immutable version**, use snapshots, copy-on-write, a producer write-then-rename/publish workflow, content-addressed objects, or a controlled synchronization protocol.
- Even holding an open file handle does not automatically block all modifications by other processes to file contents; you must understand OS locking and sharing semantics.

For backups: never hash a file being continuously modified and assume you backed up a valid database state. Use database snapshots or the database's dedicated backup protocol.

## 14. Performance Cost and Optimization Strategies

SHA-256 is computed linearly in input size: **O(n)** time and can use **O(1)** auxiliary memory with a fixed-size buffer. However, real tools also pay disk-read overhead, network I/O, and target verification costs.

| Approach | Data Passes | Strengths | Weaknesses |
| --- | --- | --- | --- |
| Copy then hash both source and target | Copy + at least two read passes to hash | Detects discrepancies on both sides; easy to explain. | Extra read I/O cost. |
| Hash while copying via `MessageDigest.update` | Hashes bytes being copied | Fewer passes; streaming-friendly. | Does not verify bytes persisted at target after write. |
| Re-hash target file after copy | One extra target read pass | Independently verifies re-read content. | Extra I/O; still races with concurrent writers. |
| Block/chunk hashing with manifest | Each block has its own digest | Supports resume/dedup/local verification. | Must authenticate manifest and chunk order/index. |
| Hash entire file before every use | Reads all bytes each time | Checks content close to use time. | Expensive for large data; does not fully eliminate TOCTOU. |

Do not optimize by skipping verification when business risk requires it. On the other hand, for internal caches with clear semantics, metadata/version/content IDs can avoid re-hashing when trustworthy immutability proof already exists; measure workloads before choosing.

A shared `MessageDigest` has no reason to be updated byte by byte; read reasonably sized buffers to reduce syscall overhead. In Java 17, `MessageDigest.update(ByteBuffer)` directly supports heap/direct buffers without needing to copy into `byte[]`.

## 15. Limitations That Hashing Does Not Solve

**Hashing does not validate format.** A file whose SHA-256 matches `expected` can still contain dangerous instructions or schema-invalid data. Always validate JSON/ZIP/protocols after integrity checks.

**Hashing does not encrypt data.** SHA-256 does not hide bytes or provide confidentiality. When content secrecy is needed, use appropriate encryption/authenticated encryption.

**Hashing does not prove timestamps or filenames.** Two differently named files with identical bytes share the exact same SHA-256. If identity/version/name matter, protect and verify that metadata via an authenticated manifest.

**Hashing does not equal durability.** A matching digest upon re-reading does not confirm the disk will retain it across power loss; `force` and storage protocols are a separate responsibility.

**Hashing does not prevent replay.** A sender can re-transmit an older valid artifact with its valid digest; preventing downgrade/replay requires monotonic versions, expiry, nonces, signature context, and application rules.

**Hashing does not stop malicious paths.** Even if a ZIP archive has a matching SHA-256, extraction must still defend against Zip Slip, symlinks, zip bombs, and resource exhaustion.

**Hashing does not auto-repair errors.** On mismatch, never “ignore the warning and continue”. The system must retry/quarantine/recover from a safe source; a hash contains no information to reconstruct corrupted data.

## 16. Common Mistakes and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Hash changes even though text looks identical | Different charset, BOM, newline, Unicode normalization, whitespace. | Decide whether to hash raw bytes or canonicalized content; unify rules. |
| Wrong hash on final chunk | Calling `digest.update(buffer)` on whole array instead of just `n` new bytes. | Use `update(buffer, 0, n)` or `DigestInputStream`. |
| Different hash when using NIO | Hashing full capacity/extra bytes, or buffer position already consumed by `write`. | `flip()` properly; use duplicate/read-only view before `write`. |
| Hash only right the first time | Calling `digest()` then continuing updates on reset state, or sharing across threads. | Fresh instance per hash; finalize once. |
| Copied file missing bytes | Calling `FileChannel.write()` once without handling partial writes. | `while (buffer.hasRemaining())` before `clear()`. |
| Modified file goes undetected | Expected digest was altered alongside the file. | Protect `expected` with signature/HMAC/trusted channel. |
| Reader treats matching SHA-256 as proof of sender | Hash lacks keys/authentication. | HMAC or digital signature with proper key verification. |
| Source file hash matches yet target is wrong | Target modified after copy or write failed. | Re-hash target, write to private temp file, publish after verification. |
| Digest matches yet content differs when used | TOCTOU between hash and open/consume; path swapped. | Manage immutable artifacts/handles/ownership; verify close to use. |
| File being written yields inconsistent results | No snapshot and writer mutates during read. | Use snapshots/producer publish protocol. |
| Using MD5/CRC to verify code downloads | Does not resist intentional tampering. | Trusted reference SHA-256 + signature/HMAC per threat model. |
| Storing raw SHA-256 of passwords | Too fast; lacks brute-force resistance design. | Dedicated password hashing with salt/cost per policy. |
| Hex string fails to parse | Stray newline, spaces, prefix, or wrong length. | Normalize input under strict format control; validate exact 64 hex chars for SHA-256. |
| Hash after decompression differs from ZIP file hash | Hashing two different representations. | Define data layer and processing order consistently. |

## 17. Testing Systems That Use Hashes

A solid test suite should cover:

1. **Known answer:** `SHA-256("abc")` matches the exact hex value in the article. Use standard test vectors rather than generating expected values with your own function and calling it an independent test.
2. **Roundtrip:** copy data, hash source, hash target, compare against verified expected. Verify size, bytes, and hash.
3. **Empty file:** hashing an empty file still produces a valid SHA-256 digest, not an empty string.
4. **Mismatched file sizes:** the application detects mismatch not only via digest but also via I/O/size errors when appropriate.
5. **Single-byte modification:** alter one byte at the start, middle, and end; digest must fail to match `expected`.
6. **Renamed file with identical bytes:** raw byte digest does not change; the manifest must define policy for names/paths.
7. **Chunking:** compute with buffer sizes 1, 2, 8192 bytes and direct buffers; digests must be identical.
8. **Permissions and disk full:** catch `IOException` and never publish an unverified temporary file.
9. **Concurrent writer:** simulate a file modified mid-copy to verify snapshot policies or commit rejection.
10. **Tampered expected:** demonstrate that plain file hash + forged hash **does not** authenticate; test the real signature/HMAC path.
11. **TOCTOU:** after verification, swap the file/path before consumption; design controls around using the verified artifact.
12. **Resource limits:** large files, slow reads, network timeouts, deadlines, queue backlogs, and quotas.
13. **Replay/version:** an older file version still has a valid hash yet must be rejected when policy requires a newer version.

If a program outputs `hash-valid=true`, clearly define “valid against which expected, and where did expected come from”. A test that hashes the same input twice and compares the two **proves nothing** about integrity relative to an independent source.

## 18. Practice Exercises

**Exercise 1 — Hash file bytes instead of text.** Create two files: one containing `"Xin chào\n"` in UTF-8, the other containing `"Xin chào\r\n"` in UTF-8. Compute SHA-256 with `DigestInputStream`; explain why the hashes differ even though they may look identical when displayed.

**Exercise 2 — Streaming chunk sizes.** Change `ByteBuffer.allocate(2)` to `allocate(1)`, `allocate(16)`, and `allocate(8192)`. Verify that the digest of `abc` and the copied file stay identical; state how `flip/clear/hasRemaining` prevent missing or duplicated bytes.

**Exercise 3 — Single-byte modification.** In the sample program, try `"abc"` → `"aBc"`, `"abd"`, and `"abc\n"`. Compare SHA-256 before and after. Why would checking only `Files.size()` miss the `abc → abd` change?

**Exercise 4 — Manifest authentication.** Define a manifest containing `artifactId`, `version`, `length`, `algorithm`, `digest`. Describe how to obtain a signed manifest and verify it with a trusted public key; never treat a manifest downloaded from the same unprotected source as proof.

**Exercise 5 — Safe download.** Write a method receiving streamed data into a temporary file with a 50 MiB total quota, a deadline, and byte counting. After downloading, re-hash the temp file, compare against expected SHA-256, and publish only via a move checking atomicity; on mismatch, delete/quarantine.

**Exercise 6 — Distinguish CRC32 and SHA-256.** Compute both on the same payload. Explain why CRC32 works for routine ZIP error checks yet fails to stop an intentional archive tamperer who also recomputes the CRC.

**Exercise 7 — Race and immutable source.** Have one thread/process modify a file while another hashes it; observe the discrepancy. Design a producer that creates a temp file → flushes/closes → publishes to a fixed name → sends a trusted manifest, so consumers never hash a file still being written.

**Exercise 8 — HMAC.** Use `javax.crypto.Mac` and a key from a test key store to generate HMAC-SHA-256 for a payload. Flip one byte and verify the tag no longer matches; explain why HMAC requires a secret key while plain SHA-256 does not.

**Exercise 9 — Replay protection.** Create two artifacts v1/v2 that both have valid signatures/hashes. Design a policy rejecting v1 once v2 is activated. Why is a matching digest insufficient to decide whether a version is allowed?

**Exercise 10 — Hashing ZIPs.** Create two ZIPs containing the same text file but with different entry timestamps. Compare the SHA-256 of the **entire ZIP** and the SHA-256 of the **decompressed entry bytes**; explain the difference and choose the right representation for the requirement.

### Self-Check Questions

- How does streaming `MessageDigest.update` differ from reading the entire file into an array?
- When `read` returns only `n=7` into an 8192-byte array, how many bytes must be fed to the digest?
- With `DigestInputStream`, do you also need to call `digest.update(buffer)` after each read?
- Why does hashing the source file during copy not by itself prove the destination file was not altered?
- If the expected digest is supplied by an attacker alongside the file, does comparing them provide authentication?
- When confirming that the true publisher released an artifact, in which contexts do you use HMAC vs. digital signatures?
- What is the role of CRC32 compared to SHA-256?
- Why might a file being modified by a writer lack a stable snapshot while hashing?
- Does a matching hash mean the file format is valid, the version is not replayed, and the data has been fsynced?
- Why do raw ZIP bytes and decompressed entry bytes usually have different SHA-256 hashes?

## 19. Official References

- [Java SE 21 — MessageDigest](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html): creating SHA-256, `update`, `digest`, `isEqual`.
- [Java SE 21 — DigestInputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/DigestInputStream.html): automatically hashing data read from a stream.
- [Java SE 21 — FileChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html): read/write, buffer position, force, and lifecycle.
- [Java SE 21 — ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): `flip`, `remaining`, `asReadOnlyBuffer`.
- [Java SE 21 — HexFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HexFormat.html): converting digests to and from hexadecimal strings.
- [Java SE 21 — Mac](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Mac.html): HMAC with a secret key.
- [Java SE 21 — Signature](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Signature.html): signing and verifying digital signatures.
- [NIST FIPS 180-4 — Secure Hash Standard](https://csrc.nist.gov/pubs/fips/180-4/upd1/final): specification of SHA-256 and the Secure Hash Algorithm family.

**Remember:** When the problem requires byte-for-byte integrity, compute SHA-256 over the **exact bytes** in a streaming fashion and compare against a **trusted reference digest**. A hash helps detect differences, yet it does not by itself authenticate the source, prevent post-check modification, stop replay, or guarantee physical durability. Integrate it into a workflow with temp file management, access controls, versioning, signatures/HMAC, and a risk-appropriate fail-closed policy.