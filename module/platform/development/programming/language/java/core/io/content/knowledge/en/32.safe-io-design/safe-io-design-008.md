# Verifying Integrity With Hashes When Required by the Problem (Java I/O)

When an application reads, copies, downloads, extracts, or stores files, the key question is sometimes not just **whether I/O finished**, but also: **"Are the received bytes exactly the bytes I expected?"** If the problem requires detecting altered content, missing bytes, mixed bytes, or wrong versions, we can use a **cryptographic hash function** such as SHA-256 to compute the data's **digest** and compare it against a reference digest.

However, **hashes are not a solution to every security problem**. A SHA-256 value only verifies a match when you have a **sufficiently trusted reference digest**; if an attacker can replace both the file **and the attached hash**, comparison will still pass for the altered data. When you need to authenticate who produced the data, use HMAC or digital signatures with proper key management and source authentication.

This lesson covers: choosing when hashing is truly needed, differences between hashes/CRC/HMAC/signatures, streaming SHA-256 computation with `MessageDigest`, `DigestInputStream`, `FileChannel`, and `ByteBuffer`, post-copy verification, dealing with concurrently modified data, I/O cost, security, and Java 17+ exercises.

## 1. What Is a Hash and What Does It Check?

A cryptographic hash function `H` takes an arbitrary-length byte sequence and produces a fixed-length digest:

```text
Source bytes                   SHA-256                      32-byte digest
"abc" (ASCII)          ──────────────────────>    ba7816bf8f01cfea...
"abd" (ASCII)          ──────────────────────>    a52d159f262b2c6d...

When checking:
actual = SHA-256(bytes actually read)
expected = authenticated/trusted reference digest
PASS only when actual and expected match.
```

SHA-256 outputs **256 bits = 32 bytes**, commonly displayed as **64 hexadecimal characters**. It is not a reversible compression algorithm: you cannot "decrypt a hash" back into the file. A tiny change in input typically changes the digest dramatically.

Properties of a good cryptographic hash include resistance to preimage, second-preimage, and collision attacks within an appropriate security margin; software should not be written assuming collisions are mathematically **impossible**. With SHA-256, accidental collision probability is negligible at ordinary practical scales, though security assessments still depend on the threat model.

A proper verification rule must specify:

- **What is hashed:** raw file bytes, decompressed data, decoded payload, or a serialized representation?
- **When:** before copying, after copying, after downloading, before consumption, or at startup?
- **Source of the expected digest:** signed manifest, trusted database, independent hash over a secure channel, or just an unprotected `.sha256` file downloaded from the same place?
- **Action on mismatch:** reject the file, delete temporary copy, retry from a trusted source, alert, or proceed per policy?

## 2. When Is Hashing Actually Needed?

Hashing is valuable when a **byte-for-byte match** matters for a business decision:

| Scenario | What hashing helps with | What else is needed |
| --- | --- | --- |
| Downloading artifacts/plugins from a publisher | Checks whether the downloaded file matches the published digest. | Digest must come via a trusted channel or digital signature; never trust arbitrary hash files. |
| Copying critical files | Compares source/copy to detect byte corruption or missing bytes. | Manage concurrently changing files, write errors, snapshots, and post-check usage. |
| Syncing, archiving, backups | Detects content drift; content-based deduplication. | Manifests, versioning, identity, recovery; hashes do not replace backups. |
| Data ingestion pipelines | Verifies payload before commit/processing. | Size limits, schema validation, authentication, transactions. |
| Passing data across multiple stages | Compares input and output hashes of the same representation. | Explicitly define whether valid transforms (compression, encoding, newlines) apply. |
| Cache verification | Ensures cached value matches expected content. | Keys/versions, race protection, and invalidation strategy. |

Do not compute SHA-256 on every file read if the problem does not need that guarantee and the CPU/I/O cost is unwarranted. For example, a non-critical temporary log write might only need write-result checking and retry; an artifact used to execute code or update software needs stronger authentication than a checksum.

**Hashing does not replace** checking actual bytes read/written, `IOException`, close/flush, permissions, file format, schema, or input validation. A malformed file still has a valid SHA-256 matching its own hash.

## 3. How Do Hash, Checksum, CRC, HMAC, and Digital Signatures Differ?

| Tool | Primary purpose | Resists deliberate tampering if an adversary can alter both data and checksum? |
| --- | --- | --- |
| Byte count / file size | Detects crude truncation. | No. Two different files can share the same size. |
| CRC-32 (`java.util.zip.CRC32`) | Detects accidental transmission/storage errors at low cost. | No. CRC is not a cryptographic MAC. |
| SHA-256/SHA-512 (`MessageDigest`) | Cryptographic digest for content matching. | Only meaningful for integrity if the expected digest is reliably protected. |
| HMAC-SHA-256 (`javax.crypto.Mac`) | Authenticates integrity with a **shared secret key**. | Yes, provided the key is secure, the protocol is sound, and the algorithm remains suitable. |
| Digital signature (`Signature`) | Authenticates data using a private key, verified with a trusted public key. | Yes, if the public key / trust chain is properly verified. |
| AEAD (e.g., AES-GCM) | Encrypts and verifies an authentication tag with associated data context. | Yes, if key/nonce/AAD follow proper design. |

**Unsafe** example of proving authenticity: downloading `program.jar` alongside `program.jar.sha256` from the same location where an attacker can modify both, then claiming the file is "authenticated." An attacker can compute a new digest for a forged file.

More meaningful example: the application already holds an **expected SHA-256 distributed over an independent trusted channel**, or a manifest signed by the publisher with a pre-verified public key. Comparing digests then detects that received bytes do not match the published release.

**CRC-32** is suited for accidental error detection in ZIPs and many protocols; never use CRC instead of SHA-256/HMAC for security decisions.

**MD5 and SHA-1** have known collision weaknesses and should not be chosen for new systems facing active adversaries. For modern file integrity checks, SHA-256 is a pragmatic default; long-term algorithm policies may need updates per organizational requirements.

## 4. Basic Java API: `MessageDigest` and SHA-256

`java.security.MessageDigest` is the standard API:

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
digest.update(new byte[] {0x61, 0x62, 0x63});
byte[] result = digest.digest();
String hex = HexFormat.of().formatHex(result);
```

This is a **snippet** requiring imports for `java.security.MessageDigest`, `java.util.HexFormat`, and handling `NoSuchAlgorithmException`. Bytes `0x61, 0x62, 0x63` are the ASCII string `abc`. In Java 17+, `HexFormat` is the standard utility to format/parse hexadecimal.

Two usage styles:

- **One-shot:** `digest.digest(allBytes)`, appropriate only when the data is already safely bounded in memory.
- **Chunked:** call `digest.update(chunk...)` repeatedly in the **exact byte order**, then call `digest.digest()` once to obtain the result.

Incremental example:

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
digest.update("a".getBytes(StandardCharsets.US_ASCII));
digest.update("bc".getBytes(StandardCharsets.US_ASCII));
byte[] result = digest.digest(); // Same SHA-256 as bytes "abc".
```

This is a snippet requiring imports and checked-exception handling. There is no need to concatenate chunks into one large array: `MessageDigest` updates hashing state incrementally.

**Lifecycle note:** `digest()` completes the calculation and resets the digest state per the API contract. Continuing to call `update` after `digest()` hashes a brand-new message rather than appending to the previous one. Nor is `MessageDigest` automatically thread-safe: use a separate instance per thread/task unless explicitly synchronized.

## 5. Hash of Bytes, Not "Visually Identical Text"

SHA-256 operates on a **byte sequence**. With text, the exact same rendered sentence can have different bytes due to:

- Charset: UTF-8, UTF-16, legacy code pages.
- Unicode normalization: NFC vs. NFD can represent accented characters differently.
- Line endings: `\n`, `\r\n`, or files with a BOM.
- Trailing whitespace, tabs, differing encodings, extra/missing bytes.
- JSON with reordered keys, spacing, or number serialization; XML with its own canonicalization.

Example:

```java
byte[] a = "abc".getBytes(StandardCharsets.UTF_8);
byte[] b = "abc\n".getBytes(StandardCharsets.UTF_8);
// Two arrays of different lengths, so SHA-256 must be computed independently.
```

This is a snippet. If **file integrity** is required, hash the **raw bytes** as actually stored; do not read text and re-serialize to normalize without an explicit requirement. If the problem requires **logical content equivalence**, define clear canonicalization rules and apply them identically on both publisher and consumer sides before hashing.

For compressed or encrypted formats, clarify whether the hash applies to:

1. **ZIP/compressed bytes** (verifying the exact received archive), or
2. **Decompressed entry bytes** (verifying the exact original content), or
3. **Parsed/canonicalized objects** (verifying logical equivalence).

These three digests are not interchangeable. A ZIP rebuilt with different entry timestamps can have a different raw archive hash even when file payloads are identical.

## 6. Streaming Hash for Large Files With `DigestInputStream`

Do not use `Files.readAllBytes(file)` on very large or untrusted files just to compute SHA-256. Read in chunks and update the digest:

```java
// Snippet: file is a readable, controlled Path.
MessageDigest digest = MessageDigest.getInstance("SHA-256");
try (InputStream in = new DigestInputStream(
        Files.newInputStream(file), digest)) {
    byte[] buffer = new byte[8192];
    while (in.read(buffer) != -1) {
        // DigestInputStream has already updated the digest with bytes actually read.
    }
}
byte[] actual = digest.digest();
```

The snippet above requires importing `java.io.InputStream`, `java.security.DigestInputStream`, `java.security.MessageDigest`, `java.nio.file.Files`, and handling exceptions. `DigestInputStream` updates the digest **during `read`**, so do not call `digest.update(buffer)` again; calling it extra times hashes bytes **twice** and yields a wrong result.

If using a plain `InputStream`:

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

This snippet uses a fresh, unfinalized `digest`; reading must include logic suited to the stream type. Always use **`n`**, never update with the entire `buffer` array: the final read often returns fewer bytes than `buffer.length`, and trailing bytes from the previous read do not belong to the new data.

Chunk sizes such as 8 KiB or 64 KiB affect performance, not the digest result, as long as the exact same sequence of bytes is fed in.

## 7. `FileChannel` and `ByteBuffer`: Hashing the Exact Bytes Written

With NIO, `FileChannel.read(ByteBuffer)` advances `position` by the actual bytes read; after `flip()`, the range `[position, limit)` holds the newly read data. To **copy and hash simultaneously**, create a view of the chunk to feed the digest without changing the original buffer's `position` used by `FileChannel.write()`:

```java
// Snippet: in/out are FileChannels; chunk is a ByteBuffer in write phase.
int n = in.read(chunk);
if (n > 0) {
    chunk.flip();
    digest.update(chunk.asReadOnlyBuffer()); // View with independent position.
    while (chunk.hasRemaining()) {
        int written = out.write(chunk);
        if (written == 0) {
            throw new IOException("No write progress");
        }
    }
    chunk.clear();
}
```

This is a snippet; on ordinary blocking files, a fail-fast policy when `write` returns 0 avoids busy loops. Do not copy that policy verbatim to non-blocking `SocketChannel`: `write() == 0` can be a normal state requiring waiting for `OP_WRITE`.

Core points:

- `asReadOnlyBuffer()` creates a **view sharing the same bytes with independent `position`/`limit`** from the original buffer; `digest.update(ByteBuffer)` consumes the view from `position` to `limit`.
- `FileChannel.write(chunk)` still sees the original `position` at 0 and writes **the exact bytes that were hashed**.
- Because `write` can be partial, loop `while (chunk.hasRemaining())` before calling `clear()`.
- On `n == -1`, that is EOF; stop. On `n == 0` for a blocking file read when the buffer still has space, the application needs a no-progress policy.
- Never hash the entire buffer capacity instead of the actual bytes just read.

**Safety limit:** a digest computed during copy confirms the byte sequence the application **attempted to write**, not that those bytes actually persist in the target file after a system failure or modification by another process. If a decision depends on using the target file, **re-read the target file to hash and verify it against the reference digest** before committing or consuming per policy.

## 8. Standalone Java 17+ Example: Copy, Compare, and Detect Tampering

This test uses the known-answer vector `SHA-256("abc")` with standard hex value:

```text
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

The program creates two temporary files, writes `abc` to the source file, uses `FileChannel` with a **2-byte** buffer to force multi-pass processing, computes SHA-256 while copying, and then verifies both source and target digests. Finally, it alters the target content to `abd` to demonstrate that the digest no longer matches. In the example, the reference SHA-256 is **hardcoded for practice**; in real applications, obtain expected values from an authenticated source.

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

1. `Files.writeString(source, "abc", US_ASCII)` produces the exact three bytes `61 62 63`. The standard digest serves as `expected` from a known test vector.
2. `copyAndHash` opens two `FileChannel`s inside `try-with-resources`, reads up to two bytes per pass, and updates `MessageDigest` via a read-only view.
3. `while (chunk.hasRemaining())` ensures each chunk is fully transferred to the target file based on `ByteBuffer` position before reading the next chunk.
4. `MessageDigest.isEqual` compares the actual digest byte arrays. `source-valid=true` and `copied-valid=true` show the source data and copied stream bytes match `expected`.
5. `destination-valid=true` because the program **re-reads the target file** and hashes it independently; this adds a control beyond merely trusting written byte counts.
6. When `abc` is changed to `abd`, the target file's digest changes; comparing against the old `expected` yields `after-tamper-valid=false`.
7. Both temporary files are deleted in `finally`, with channels/input streams safely closed before cleanup.

**Demo limitation:** only a single program operates on the temporary files, with no concurrent external writers. It properly demonstrates hashing and comparison techniques, **not** TOCTOU immunity, `fsync` durability, or protection against post-check tampering. In production, refer to the lifecycle and trust-source sections below.

## 9. Comparing Digests Properly and Reading Expected Hashes

An actual SHA-256 digest is **32 bytes**. For hex reference strings, validate length/encoding before use:

```java
// Snippet: expectedHex obtained from an authenticated manifest.
String expectedHex = expectedHexFromTrustedManifest;
if (!expectedHex.matches("[0-9a-fA-F]{64}")) {
    throw new IOException("Invalid expected SHA-256");
}
byte[] expected = HexFormat.of().parseHex(expectedHex);
byte[] actual = sha256(downloadedFile);
if (!MessageDigest.isEqual(expected, actual)) {
    throw new IOException("Integrity check failed");
}
```

This is a snippet assuming `downloadedFile`, `expectedHexFromTrustedManifest`, and `sha256(...)` are declared externally; `HexFormat` is built into Java 17. If the manifest specifies `SHA-512`, the digest length differs; do not guess the algorithm from an arbitrary hash string's length.

`MessageDigest.isEqual(byte[], byte[])` is a more appropriate digest comparison utility than manually formatting strings and comparing with branching logic; never claim from this API alone that the entire workflow has perfect timing side-channel resistance. When authentication relies on secrets and timing-sensitive protocols, follow thoroughly reviewed MAC/signature designs.

Compute **hashes with a fresh `MessageDigest` per object/task**; avoid sharing a global instance across concurrent threads calling `update`. Log hashes alongside algorithm, schema version, file/version identity, and context; never accidentally use digests for password hashing or secret token storage.

## 10. Where Are Hashes Stored and Where Does Trust Come From?

Decision table:

| Source of expected hash | Trustworthy against file tampering? | Reason |
| --- | --- | --- |
| SHA-256 downloaded from the same attacker-controlled URL | **No**. | Adversary can generate both a fake file and a matching fake hash simultaneously. |
| Hash in a trusted DB with access control/auditing | Usable, depending on DB protection and hash-generation pipeline. | Integrity of the reference is the key factor. |
| Hash hardcoded in a trusted distributed application build | Usable for a specific artifact/version. | The hash does not protect the application binary itself from tampering. |
| Digitally signed manifest with pinned/verified public key | Usable for publisher authentication if protocol and keys are sound. | The signature protects the manifest's hashes and bound metadata. |
| HMAC of payload with an unexposed secret key | Usable for authentication between parties sharing the key. | Unsuitable if every public recipient must verify without knowing the secret. |

Bind the digest to the right **object**. With only a bare list of SHA-256 hashes without knowing which artifact name, version, size, or context each digest belongs to, a verifier could accept a valid file of the **wrong version**. Manifests should authenticate logical path, version, algorithm, digest, and key identifying metadata as needed.

**A bare hash does not prove who the sender is.** It is purely a deterministic calculation over bytes; **trust** comes from protected manifests, MACs, signatures, TLS/authentication, and properly designed access controls.

## 11. HMAC and Digital Signatures When Anti-Forgery Is Required

When two systems hold a **shared secret key**, HMAC verifies data was created by a party holding that key and was not altered in transit:

```java
// Illustrative snippet: secret is byte[] from a secure key store,
// do not hardcode keys in code or logs.
Mac mac = Mac.getInstance("HmacSHA256");
SecretKeySpec key = new SecretKeySpec(secret, "HmacSHA256");
mac.init(key);
byte[] tag = mac.doFinal(payload);
```

This snippet requires importing `javax.crypto.Mac`, `javax.crypto.spec.SecretKeySpec`, and handling exceptions; `payload` is bytes. Do not reuse the same secret key across unrelated purposes; design protocols binding identity/version/nonce or context per the threat model. A valid HMAC does not by itself prevent replay if the application accepts repeated identical messages without checking sequence/expiry/idempotency.

When publishing for many verifiers **without** sharing a private key, use **digital signatures**. The publisher signs a structured manifest or digest; recipients verify the signature using the proper public key/trust chain. Never fetch a public key from the same unauthenticated source and consider forgery solved.

**Do not invent signatures by writing `SHA-256(key || message)`.** Use standard HMAC or signature algorithms and established crypto libraries. For storing passwords, never use plain SHA-256: password hashing requires salts and specialized algorithms with appropriate work factors (e.g., Argon2id, scrypt, PBKDF2 per policy).

## 12. Hashing in a Safe Download/Copy Workflow

A sample workflow to publish a target file:

```text
authenticated expected hash + identity/version
             |
             v
Create TEMPORARY target file in controlled directory/permissions
             |
             v
Download or copy bytes in chunks, checking n and quota
             |
             v
Close/flush corresponding resources, check for I/O errors
             |
             v
Re-hash temporary file, compare against expected SHA-256
             |
     +-------+--------+
     |                |
  MISMATCH           MATCH
     |                |
Delete/quarantine Optional: force/sync and atomic publish
Do not commit     verified file, manage access permissions
                      |
                      v
                Consumers use that exact version
```

Principles:

1. Write to a **temporary file not yet treated by other clients as valid**; never overwrite a production file directly before verifying.
2. Use a trusted expected digest obtained through a separate mechanism or signed manifest.
3. Process the file only after the actual digest matches; failures must **fail closed** for critical data.
4. Choose a publishing mechanism with platform atomicity, e.g., `Files.move(..., ATOMIC_MOVE)` if supported by the provider and replace semantics fit. Handle `AtomicMoveNotSupportedException`, permission errors, and differing target-replacement behaviors.
5. If durability across power loss is required, consider `FileChannel.force(true)` for the file and directory-sync mechanisms permitted by the OS/provider. Atomic rename does not automatically mean data has been `fsync`ed.
6. Prevent other producers from modifying the temporary file after checking; coordinate ownership, access permissions, locking/renaming, and consumption timing.

**TOCTOU:** checking a hash at T1 and reopening the same path at T2 **does not guarantee** the bytes remain unchanged if the file can be replaced/overwritten in between. Prefer storing verified files in immutable areas per policy, using versioned identifiers or content-addressed storage, managing handles and write permissions, and verifying close to use when needed.

## 13. Source Data Changing During Hashing or Copying

A tough problem arises with large files when another writer is updating them:

```text
T0: SHA-256 starts reading file X
T1: Another writer modifies the middle of X
T2: SHA-256 reads the remaining part
T3: Resulting digest comes from a byte sequence that may not
    correspond to a consistent snapshot of the file at any point in time.
```

Important notes:

- Chunked file reads do not provide **snapshot isolation**.
- Checking `Files.size()` and `Files.getLastModifiedTime()` before and after can assist change detection, but is not a safety proof: timestamps have coarse granularity, can be spoofed, and files can be changed back and forth.
- `FileChannel.lock()` operates according to OS/filesystem rules and writer cooperation; it does not guarantee every program respects it.
- To attest the hash of an **immutable version**, use snapshots, copy-on-write, a producer workflow that finishes then renames/publishes, content-addressed objects, or a controlled synchronization protocol.
- Even holding an open file handle does not automatically block other processes from modifying contents; understand OS locking and sharing semantics.

For backups: never compute SHA-256 of a continuously mutated file and assume you backed up a valid database state. Use database snapshots or dedicated backup protocols.

## 14. Performance Cost and Optimization Strategies

SHA-256 runs linearly in input size: **O(n)** time and **O(1)** auxiliary memory with a fixed-size buffer. However, real tools also incur disk read, network I/O, and target verification overhead.

| Approach | Passes over data | Strengths | Weaknesses |
| --- | --- | --- | --- |
| Copy then hash source and target | Copy + at least two read passes to hash | Detects discrepancies on both sides; easy to reason about. | Extra read I/O cost. |
| Hash while copying via `MessageDigest.update` | Hashes bytes being copied | Fewer passes, streaming-friendly. | Does not verify bytes persisted at target after write. |
| Re-hash target file after copy | One extra target read pass | Independently checks persisted target content. | Extra I/O; still has races if another writer exists. |
| Block/chunk hashing with manifest | Each block has its own digest | Supports resume, dedup, localized checks. | Must authenticate manifest and chunk order/indices. |
| Hash whole file before every use | Reads all bytes every time | Verifies content close to use time. | Expensive for large data; does not eliminate TOCTOU completely. |

Do not optimize by skipping verification when business risk requires it. Conversely, for internal caches with clear semantics, metadata/version/content IDs can avoid re-hashing when reliable immutability proof exists; measure workloads before choosing.

A single `MessageDigest` has no reason to be updated byte by byte; read with a sufficiently large buffer to reduce syscall overhead. In Java 17, `MessageDigest.update(ByteBuffer)` directly accepts heap and direct buffers without requiring copies to `byte[]`.

## 15. Limitations That Hashing Does Not Solve

**Hashing does not validate format.** A file whose SHA-256 matches `expected` can still contain dangerous instructions or schema-invalid data. Always validate JSON/ZIP/protocols after the integrity check.

**Hashing does not encrypt data.** SHA-256 does not hide bytes or provide confidentiality. When content secrecy is needed, use proper encryption or authenticated encryption.

**Hashing does not prove timestamps or filenames.** Two differently named files with identical bytes produce the same SHA-256. If identity, version, or name matters, protect and verify that metadata via an authenticated manifest.

**Hashing does not equal durability.** A matching digest on re-read does not prove a disk will retain data across power loss; `force` and storage protocols are a separate responsibility.

**Hashing does not prevent replay.** A sender can retransmit an older valid version with its valid digest; preventing downgrade/replay requires monotonic versions, expiration, nonces, signature context, and application rules.

**Hashing does not prevent malicious paths.** Even if a ZIP archive's SHA-256 matches, extraction must still guard against Zip Slip, symlinks, zip bombs, and resource exhaustion.

**Hashing does not auto-repair corruption.** On mismatch, never "ignore the warning and continue." Systems must retry, quarantine, or recover from a safe source; hashes contain no redundancy to reconstruct damaged data.

## 16. Common Pitfalls and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Hash changes despite visually identical text | Different charset, BOM, newlines, Unicode normalization, whitespace. | Decide raw bytes vs. canonicalized content; unify rules. |
| Wrong hash on final chunk | Calling `digest.update(buffer)` on the whole array instead of just `n` new bytes. | Use `update(buffer, 0, n)` or `DigestInputStream`. |
| Different hash when using NIO | Hashing full capacity/stale bytes, or buffer `position` already consumed by `write`. | `flip()` properly; use a duplicate/read-only view before writing. |
| Hash only right the first time | Calling `digest()` then continuing to update the reset state, or sharing across threads. | Fresh instance per hash computation; finalize once. |
| Copied file is missing bytes | Calling `FileChannel.write()` once without handling partial writes. | Loop `while (buffer.hasRemaining())` before `clear()`. |
| Tampered file goes undetected | Expected digest was replaced alongside the file. | Protect expected digest with signature/HMAC/trusted channel. |
| Reader treats matching SHA-256 as proof of sender | Hash has no key or authentication. | Use HMAC or digital signatures with proper key verification. |
| Source hash matches but target differs | Target modified after copy or write failed. | Re-hash target, keep private temp file, publish after verification. |
| Digest matched yet content differs at use time | TOCTOU between hashing and open/consume; path swapped. | Manage immutable artifacts/handles/ownership; verify close to use. |
| File being written gives inconsistent hash | No snapshot and writer mutates during read. | Use snapshots or producer publish protocols. |
| Using MD5/CRC to verify downloaded code | Does not resist deliberate tampering. | Trusted reference SHA-256 + signature/HMAC per threat model. |
| Storing SHA-256 of passwords | Too fast, lacks brute-force resistance design. | Specialized password hashing with salt/cost per policy. |
| Hex string fails to parse | Contains newlines, spaces, prefixes, or wrong length. | Normalize input under controlled format; validate exact 64 hex chars for SHA-256. |
| Hash after decompression differs from ZIP file hash | Hashing two different representations. | Clarify data layer and consistent processing order. |

## 17. Testing Hash-Verified Systems

A solid test suite should include:

1. **Known answer:** `SHA-256("abc")` matches the standard hex value in this lesson. Use standard fixtures rather than generating `expected` with the function under test and calling it an independent test.
2. **Roundtrip:** copy data, hash source, hash target, compare against authenticated `expected`. Check size, bytes, and hash.
3. **Empty file:** the hash of an empty file is a valid SHA-256 digest, not an empty string.
4. **Mismatched size:** the application detects mismatches via I/O/size errors as well as digests where appropriate.
5. **Single-byte modification:** flip one byte at the start, middle, and end; digest comparison against `expected` fails.
6. **Rename keeping identical bytes:** raw byte digest stays the same; manifests must define name/path policies.
7. **Chunking:** compute with 1-, 2-, and 8192-byte buffers and direct buffers; digests must match.
8. **Access permissions and disk full:** catch `IOException` and never publish an unverified temp file.
9. **Concurrent writer:** simulate file mutation during copy to test snapshot policies or commit rejection.
10. **Replaced expected digest:** demonstrate that plain file hash + forged hash **does not** provide authentication; test the real signature/HMAC path.
11. **TOCTOU:** after verification, swap the file/path before consumption; verify controls over using checked artifacts.
12. **Resource limits:** large files, slow reads, network timeouts, deadlines, queue backlogs, and quotas.
13. **Replay/versioning:** an older file still has a valid hash but must be rejected if policy requires a newer version.

If a program outputs `hash-valid=true`, explicitly define "valid against which `expected`, and where did `expected` come from?" A test that hashes the same input twice and compares them **does not prove** integrity against an independent source.

## 18. Practice Exercises

**Exercise 1 — Hash file bytes rather than text.** Create two files: one containing UTF-8 `"Xin chào\n"`, the other UTF-8 `"Xin chào\r\n"`. Compute SHA-256 using `DigestInputStream`; explain why the hashes differ even though both may render similarly.

**Exercise 2 — Streaming chunk sizes.** Change `ByteBuffer.allocate(2)` to `allocate(1)`, `allocate(16)`, and `allocate(8192)`. Verify that the digest of `abc` and the copied file remain identical; explain how `flip/clear/hasRemaining` prevent dropped or duplicated bytes.

**Exercise 3 — Flip one byte.** In the sample program, try `"abc"` → `"aBc"`, `"abd"`, and `"abc\n"`. Compare SHA-256 before and after. Why would checking only `Files.size()` miss `abc → abd`?

**Exercise 4 — Manifest verification.** Define a manifest containing `artifactId`, `version`, `length`, `algorithm`, and `digest`. Describe how to obtain a signed manifest and verify it with a trusted public key; never treat a manifest downloaded from the same unprotected source as proof.

**Exercise 5 — Safe download.** Write a function streaming data into a temporary file with a 50 MiB total quota, deadline, and byte counter. After downloading, re-hash the temporary file, compare against expected SHA-256, and publish only via an atomicity-checked move; on mismatch, delete or quarantine.

**Exercise 6 — Distinguish CRC32 and SHA-256.** Compute both on the same payload. Explain why CRC32 suits ordinary ZIP error detection yet fails to stop an intentional archive tamperer who also recomputes the CRC.

**Exercise 7 — Race and immutable source.** Have one thread/process modify a file while another hashes it; observe the discrepancy. Design a producer that creates a temp file → flushes/closes → publishes a fixed name → sends a trusted manifest so consumers never hash a file still being written.

**Exercise 8 — HMAC.** Use `javax.crypto.Mac` with a key from a test key store to compute HMAC-SHA-256 for a payload. Alter one byte and verify the tag fails; explain why HMAC requires a secret key while plain SHA-256 does not.

**Exercise 9 — Replay protection.** Create two artifacts v1/v2 that both carry valid signatures/hashes. Design a policy rejecting v1 once v2 is active. Why is a matching digest insufficient to decide whether a version is allowed?

**Exercise 10 — Hashing ZIPs.** Create two ZIPs containing the same text file but different entry timestamps. Compare the SHA-256 of the **entire ZIP** versus the SHA-256 of the **decompressed entry bytes**; explain the difference and choose the right representation for a requirement.

### Self-Check Questions

- How does streaming bytes via `MessageDigest.update` differ from reading the whole file into an array?
- When `read` returns only `n=7` into an 8192-byte array, how many bytes must update the digest?
- Does `DigestInputStream` require an extra `digest.update(buffer)` call after each read?
- Why does hashing the source file during copy not prove the target file was not altered?
- If the expected digest is supplied alongside the file by an attacker, does comparing them establish authentication?
- When proving the publisher itself released an artifact, in which contexts do you use HMAC versus digital signatures?
- What is CRC32's role compared to SHA-256?
- Why might a file actively modified by a writer lack a stable snapshot during hashing?
- Does a matching hash imply valid file format, no replay, and `fsync`ed durability?
- Why do raw ZIP bytes and decompressed entry bytes usually have different SHA-256 digests?

## 19. Official References

- [Java SE 21 — MessageDigest](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html): creating SHA-256, `update`, `digest`, `isEqual`.
- [Java SE 21 — DigestInputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/DigestInputStream.html): automatic hashing of bytes read from a stream.
- [Java SE 21 — FileChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html): read/write, buffer position, `force`, and lifecycle.
- [Java SE 21 — ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): `flip`, `remaining`, `asReadOnlyBuffer`.
- [Java SE 21 — HexFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HexFormat.html): converting digests to and from hexadecimal strings.
- [Java SE 21 — Mac](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Mac.html): HMAC with a secret key.
- [Java SE 21 — Signature](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Signature.html): signing and verifying digital signatures.
- [NIST FIPS 180-4 — Secure Hash Standard](https://csrc.nist.gov/pubs/fips/180-4/upd1/final): specification for SHA-256 and the Secure Hash Algorithm family.

**Remember:** When a problem requires byte-for-byte integrity, compute SHA-256 over the **exact bytes** in streaming fashion and compare against a **trusted reference digest**. Hashes detect discrepancies, yet do not by themselves authenticate origin, prevent post-check tampering, stop replay, or guarantee physical durability. Integrate hashing into a workflow with temporary file management, access permissions, versioning, signatures/HMAC, and risk-appropriate fail-closed policies.
