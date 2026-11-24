# Encrypting Sensitive Files in Spring Batch

## 1. Context and objectives

A Spring Batch job frequently ingests and produces large files: transaction CSVs, payroll data, customer records, reconciliation reports, database extracts, or files containing personal identifiers. These files can travel across many locations: SFTP/object storage, worker temp directories, RAM, logs, backup zones, and output directories. A leak at any single point can expose the entire sensitive dataset, even when the application database itself is protected.

**Encrypting sensitive files** is a security requirement across the entire batch lifecycle, not merely calling an encryption function before upload. Designing it properly requires addressing all of the following together:

1. **Confidentiality:** unauthorized parties without the key cannot read file contents.
2. **Integrity and authenticity:** detect tampering, splicing, truncation, or swapping of file contents.
3. **Key management:** store, authorize, rotate, and revoke keys without hardcoding them in source code.
4. **Spring Batch processing flow:** readers/processors/writers must read authorized content without leaving unintended plaintext behind.
5. **Transactions and restarts:** job failures, retries, or restarts must not expose incomplete files or mispublish results.
6. **Performance:** support large files without dangerously decrypting entire payloads into the Java heap.
7. **Observability and testing:** detect wrong keys, tampering, KMS errors, cleanup failures, and sensitive records in logs.

This lesson belongs to *Spring Batch Core Processing → Security*. Concrete examples use **Java 17, Spring Boot 3.x, and Spring Batch 5.2.x**; cryptography uses Java Cryptography Architecture (JCA). The code illustrates algorithms and integration at small-file scale and **does not replace a standardized file encryption format or security-audited cryptography library** for large production datasets.

---

## 2. Identifying which data needs protection

### 2.1. Common data types

| Data | Exposure risk | Batch considerations |
|---|---|---|
| Customer CSVs | Names, contact numbers, addresses, IDs | Never log data lines on error |
| Payroll files | Income, salary deposit accounts | Strict access control, auditing, and retention |
| Payment files | Account numbers, transactions, financial data | Prevent duplicate retries/publishes; verify integrity |
| Production data extracts | May contain internal data from multiple systems | Protect source files, temp files, and backups |
| Reconciliation files | Transaction IDs, partner data | Define sharing rights and per-partner keys |
| Error/quarantine files | May retain full sensitive records | Never treat error files as non-sensitive data |
| Metadata/manifests | Filenames, customer IDs, record counts, timestamps | Portions of metadata can also be sensitive |

Encrypting a file does not automatically make data "anonymous"; anyone authorized to decrypt can still view the original contents. If regulations require field masking, tokenization, pseudonymization, or erasure, those mechanisms must be designed separately.

### 2.2. Data flows to evaluate

Example of a job transferring customer data from a partner into an internal system:

```text
Partner
   │
   │ file.enc over HTTPS/SFTP/TLS
   ▼
Inbound landing zone (encrypted object)
   │
   ▼
Spring Batch worker
   │    ├── fetch key/unwrap DEK from KMS or vault
   │    ├── authenticate + decrypt data
   │    ├── ItemReader → ItemProcessor → ItemWriter
   │    └── produce encrypted output
   ▼
Encrypted output zone
   │
   ├── publish via atomic/idempotent policy
   ├── deliver to authorized consumer
   └── retention/cleanup
```

Easily overlooked locations: `/tmp`, spool files during unzipping, heap dumps, crash dumps, console logs, dead-letter files, FTP client cache directories, incomplete object-storage multipart uploads, and copies created by backup systems.

### 2.3. Encryption layers

| Protection layer | Examples | What it protects | What it leaves open |
|---|---|---|---|
| In transit | HTTPS/TLS, SFTP, mTLS | Data on the wire | Files resting on source/destination disks |
| Disk/storage encryption | LUKS, EBS encryption, SSE-KMS | Storage media, snapshots, certain disk-theft risks | Processes/identities allowed to read the object still receive plaintext |
| File/application-level encryption | AES-GCM, contract-compliant OpenPGP | File remains ciphertext when copied elsewhere | Keys, plaintext in RAM, and during processing |
| Field-level encryption | Field-level encryption/tokenization | Reduces exposure of specific fields even inside processed files | Complicates search, mapping, and aggregation |
| Access control, audit | IAM, ACLs, short-lived credentials | Restricts who can obtain ciphertext/keys | Does not replace encryption and integrity checks |

**Defense in depth:** sensitive files can be encrypted at the application layer **and** stored in an SSE-KMS bucket, accessed over TLS, and restricted via IAM. One mechanism does not automatically substitute for the others.

---

## 3. Threat model for batch files

Before choosing an algorithm, identify who can read or modify files, where keys are supplied, and which actors are trusted.

| Threat scenario | Impact | Controls to consider |
|---|---|---|
| User with bucket read access but not data clearance | Content exposed if file is plaintext | File-level encryption with separated key permissions |
| Attacker modifies ciphertext | Data altered or wrong import | Authenticated encryption + tag verification |
| File truncated during upload | Batch reads missing records | Full-file authentication, manifest/length/final marker |
| Swapping Day A's file with Day B's | Wrong business period imported | Bind identity/date/dataset name into authenticated metadata (AAD) |
| Worker writes plaintext to `/tmp` | Exposed via container, snapshot, diagnostics | Avoid plaintext on disk or use protected staging with cleanup |
| Key lost after encryption | File unrecoverable | KMS, key backup/retention, and rotation procedures |
| Attacker obtains both key and ciphertext | Contents readable | KMS authorization, key separation, auditing, time limits |
| Reusing a nonce with the same AES-GCM key | Breaks cryptographic security | Unique nonce per key, safe nonce generation |
| Retry/restart publishes duplicate file | Consumer processes twice | Business key, conditional publish, manifest, and idempotency |
| Logs/heap dumps contain plaintext | Side-channel leak | Redaction, dump/log access control, retention limits |
| Replaying an old valid file | Re-importing old transactions | Freshness/replay protection bound to business identity |

Anyone permitted to call KMS decrypt and read ciphertext can decrypt; therefore **key access permissions are part of the data model**, not a minor configuration detail.

---

## 4. Choosing algorithms: authenticated encryption

### 4.1. Why confidentiality-only encryption is not enough

Some encryption modes only conceal contents without detecting ciphertext tampering. If a batch job decrypts a tampered file and writes it to the target system, the impact can be severe.

**Authenticated encryption with associated data (AEAD)** provides both confidentiality and authentication. A common choice is **AES-GCM**; in Java JCA:

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
```

Parameters to understand:

- **AES key:** 128-bit or 256-bit generated from a proper cryptographic random source; never derived from a plain password by grabbing string bytes.
- **Nonce/IV:** for AES-GCM, typically 96-bit (12 bytes); **never reuse the same nonce with the same key**.
- **Authentication tag:** typically 128-bit (16 bytes).
- **AAD:** metadata that is authenticated but not encrypted, e.g., format version, file ID, dataset/tenant/businessDate.
- **Ciphertext:** encrypted contents; when tag verification fails, **fail closed** and never emit plaintext as valid data.

```text
Plaintext + AES key + nonce + AAD
                  │
                  ▼
              AES-GCM
                  │
                  ├── ciphertext
                  └── authentication tag

Ciphertext + tag + key + nonce + AAD
                  │
                  ▼
       Verify tag before trusting output
                  │
          ├── valid → valid plaintext
          └── invalid → reject entire file/record
```

Note: **AEAD does not prevent all replay attacks.** Valid ciphertext from yesterday still has a valid tag. Bind the dataset ID/businessDate and maintain a registry of processed periods to prevent re-importing a valid file for the wrong period.

### 4.2. CBC, ECB, and "Base64 encryption"

Never use `AES/ECB` to encrypt file data: it leaks repeating patterns and lacks integrity. AES-CBC only encrypts; making it secure requires proper MAC composition and more complex design—for new problems, prefer AEAD or a standardized encrypted file format. `Base64` is merely **representation encoding**, not security: anyone with the string can Base64-decode it.

Never invent "AES followed by a plain hash" as a substitute for an authentication tag. MACs, AAD, and verification must follow a vetted cryptographic design.

### 4.3. Why nonce uniqueness matters

With GCM, repeating a nonce under the **same key** catastrophically breaks confidentiality and integrity. For separate files sharing a key, a 12-byte nonce from `SecureRandom` is common when file counts and key lifecycle policies are bounded, though collision probability and total volume under a key must still be assessed.

A simpler production policy to limit blast radius is **one data encryption key (DEK) per file**, supplied or generated and wrapped properly by KMS/vault. Nonce uniqueness is then scoped to that file/key. If a file is split into independently encrypted records/chunks, each record must still use a unique nonce with that file's key.

**Never casually use millisecond timestamps or non-durable counters as nonces**: multiple nodes and restarts can produce duplicate values. Counter nonces require protocols guaranteeing uniqueness even across crashes, retries, and worker handoffs.

---

## 5. Java 17 example: size-bounded AES-GCM for small files

The example below teaches explicit, testable JCA usage. It handles **small files only (up to 10 MiB plaintext)** because AES-GCM decryption and authentication can require significant buffering; this is **not a streaming solution for multi-GB files**.

### 5.1. Demo file format

```text
┌──────────────┬────────────────┬───────────────────────┐
│ magic/version│ random nonce   │ ciphertext + GCM tag  │
│ "SBENC1"     │ 12 bytes       │ variable + 16 bytes   │
└──────────────┴────────────────┴───────────────────────┘
       6 B             12 B               N + 16 B
```

The `magic/version` header identifies the format. In the demo, the magic bytes are fed into AAD to detect tampering. The nonce is passed into GCM; altering the nonce causes tag verification to fail (barring cryptographic forgery beyond security assumptions).

**This format is for learning only, not an interoperable cross-organization standard.** Production files should use a standard format or reviewed protocol carrying version, key ID, wrapped DEK, algorithm, AAD rules, and migration support.

### 5.2. AesGcmFileCodec

```java
package com.example.batch.security;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Objects;

import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AesGcmFileCodec {

    private static final byte[] MAGIC =
            "SBENC1".getBytes(StandardCharsets.US_ASCII);

    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int TAG_BYTES = TAG_BITS / 8;

    public static final int MAX_PLAIN_BYTES = 10 * 1024 * 1024;
    public static final int MAX_ENCRYPTED_BYTES =
            MAGIC.length + NONCE_BYTES
                    + MAX_PLAIN_BYTES + TAG_BYTES;

    private final SecureRandom random = new SecureRandom();

    public byte[] encrypt(byte[] plaintext, SecretKey key)
            throws GeneralSecurityException {

        Objects.requireNonNull(plaintext, "plaintext");
        Objects.requireNonNull(key, "key");

        if (plaintext.length > MAX_PLAIN_BYTES) {
            throw new IllegalArgumentException(
                    "File too large for in-memory demo codec");
        }

        byte[] nonce = new byte[NONCE_BYTES];
        random.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));

        // Header is authenticated; not confidential (needs no secrecy).
        cipher.updateAAD(MAGIC);

        byte[] ciphertextAndTag = cipher.doFinal(plaintext);

        return ByteBuffer.allocate(
                        MAGIC.length + nonce.length
                                + ciphertextAndTag.length)
                .put(MAGIC)
                .put(nonce)
                .put(ciphertextAndTag)
                .array();
    }

    public byte[] decrypt(byte[] encoded, SecretKey key)
            throws GeneralSecurityException {

        Objects.requireNonNull(encoded, "encoded");
        Objects.requireNonNull(key, "key");

        int minimumLength =
                MAGIC.length + NONCE_BYTES + TAG_BYTES;

        if (encoded.length < minimumLength
                || encoded.length > MAX_ENCRYPTED_BYTES) {
            throw new IllegalArgumentException(
                    "Invalid encrypted file length");
        }

        ByteBuffer buffer = ByteBuffer.wrap(encoded);

        byte[] magic = new byte[MAGIC.length];
        buffer.get(magic);

        if (!Arrays.equals(magic, MAGIC)) {
            throw new IllegalArgumentException(
                    "Unsupported encrypted file format");
        }

        byte[] nonce = new byte[NONCE_BYTES];
        buffer.get(nonce);

        byte[] ciphertextAndTag = new byte[buffer.remaining()];
        buffer.get(ciphertextAndTag);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));

        cipher.updateAAD(MAGIC);

        // AEADBadTagException if wrong key, wrong nonce,
        // tampered ciphertext/tag, or truncated file.
        return cipher.doFinal(ciphertextAndTag);
    }
}
```

**Notable details:**

1. `SecureRandom` generates a fresh nonce per encryption. A key+nonce pair must never repeat.
2. `GCMParameterSpec(128, nonce)` specifies a 128-bit tag.
3. `cipher.updateAAD(MAGIC)` includes magic/version in the authenticated data.
4. `Cipher.doFinal` on decrypt verifies the tag; exceptions propagate with **no fallback to reading plaintext**.
5. `MAX_PLAIN_BYTES` bounds the demo to avoid accidentally calling `Files.readAllBytes` on large files.
6. The Java `SecretKey` must come from a secure key-management component; **the codec never stores keys in the file**.
7. Ciphertext differs even for identical plaintext because the nonce changes—this is expected.
8. Decryption runs only after format and input size checks. Files with altered magic bytes are rejected before decryption.
9. If changing the format in the future, bump the version and provide a matching decoder; never silently interpret arbitrary bytes under one format.

### 5.3. Generating keys in a test environment

For unit tests or learning examples only:

```java
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(256);

SecretKey testKey = generator.generateKey();
```

Never generate a random key on each application restart to encrypt files that must be decrypted later: without saving/wrapping the key securely, files become unreadable. In production, use KMS/vault and a plan to store `keyId`/wrapped DEKs in file metadata.

---

## 6. Safe file reading and writing: size bounds and atomic publishing

Cryptographically sound encryption can still fail operationally if consumers read half-written outputs or temporary plaintext files leak.

### 6.1. Bounded reading without loading unbounded data

For the 10 MiB demo codec, use a helper:

```java
package com.example.batch.security;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class BoundedFileReader {

    private BoundedFileReader() {}

    public static byte[] readLimited(Path path, int maximum)
            throws IOException {

        if (maximum < 0
                || maximum == Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid maximum");
        }

        try (InputStream stream = Files.newInputStream(path)) {
            byte[] value = stream.readNBytes(maximum + 1);

            if (value.length > maximum) {
                throw new IOException("Input exceeds size limit");
            }

            return value;
        }
    }
}
```

Reading up to `maximum+1` detects oversized files without loading the entire file into RAM. When an oversized input is disallowed, **fail clearly** instead of blindly raising `-Xmx`.

### 6.2. Encrypting to a temp file then publishing

Below is a helper illustrating publishing an **encrypted file**. It assumes the target directory is inside an approved area, already exists, and resides on a filesystem supporting atomic rename; source/target paths are already validated and inputs are small.

```java
package com.example.batch.security;

import java.io.IOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.GeneralSecurityException;

import javax.crypto.SecretKey;

public final class EncryptedPublisher {

    private final AesGcmFileCodec codec;

    public EncryptedPublisher(AesGcmFileCodec codec) {
        this.codec = codec;
    }

    public void publishSmallFile(
            Path plaintextInput,
            Path encryptedOutput,
            SecretKey encryptionKey)
            throws IOException, GeneralSecurityException {

        // Example accepts only new outputs; does not replace published files.
        if (Files.exists(encryptedOutput)) {
            throw new IOException("Output already exists");
        }

        Path directory = encryptedOutput.getParent();
        if (directory == null) {
            throw new IllegalArgumentException(
                    "Output path must have a parent directory");
        }

        byte[] plaintext = BoundedFileReader.readLimited(
                plaintextInput, AesGcmFileCodec.MAX_PLAIN_BYTES);

        byte[] encrypted = codec.encrypt(
                plaintext, encryptionKey);

        // Create temp file on the same filesystem as destination.
        Path temporary = Files.createTempFile(
                directory, ".encrypted-", ".tmp");

        try {
            Files.write(temporary, encrypted);

            try {
                Files.move(temporary, encryptedOutput,
                        StandardCopyOption.ATOMIC_MOVE);
            } catch (AtomicMoveNotSupportedException unsupported) {
                throw new IOException(
                        "Atomic publish is required", unsupported);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }
}
```

Security and operational limitations of this example:

- `Files.move(..., ATOMIC_MOVE)` requires filesystem support and compatible targets. Under some providers, existing-destination behavior is provider-specific; **a pre-check is not a race-free lock**. When guaranteed non-overwrite is required, use immutable/unique destination names, locks/conditional create, or conditional object-upload APIs.
- The directory holding temp files must have strict access permissions; temp files here already hold **ciphertext**, lowering risk compared to plaintext.
- This snippet does not validate whether `plaintextInput` sits in an allowlisted directory or is a dangerous symlink. Production code must guard against path traversal, symlinks, hardlinks, and ownership issues.
- Completed `Files.write` does not guarantee power-loss durability by itself; when high durability is required, apply fsync/file-channel sync, directory sync, and storage-specific verification.
- Java byte arrays `plaintext` and `encrypted` may linger in heap until GC; zeroing every copy in memory is not guaranteed. Arrays can be cleared when done, yet `Arrays.fill` cannot scrub all copies and does not replace memory isolation.
- If `encryptedOutput` already exists from a prior run, never blindly overwrite on retry. Inspect the manifest, checksum, business key, and publish state to decide replay/reconciliation.

### 6.3. Preferred operation sequence

```text
Write data into unpublished area
             │
             ▼
Complete encryption + authentication tag
             │
             ▼
Verify file format / checksum / manifest
             │
             ▼
Atomic publish or conditional object PUT
             │
             ▼
Record result and audit
             │
             ▼
Clean up temporary area per policy
```

**Never let downstream receive a file before the writer or encryptor completes.** On object storage, use a temp name/prefix or conditional manifest object as the "ready" signal, letting consumers read only confirmed published objects.

---

## 7. Decrypting before ItemReader processing

A standard `FlatFileItemReader` expects a `Resource` containing plaintext CSV text. If the input file is encrypted, you cannot feed raw ciphertext into the tokenizer and expect the reader to understand it.

There are two architectural approaches:

1. **Small files, bounded in-memory:** decrypt and verify the entire file first, then pass a `ByteArrayResource` to the reader. Easy to illustrate, though heap usage scales with file size.
2. **Large files:** use a standardized streaming encryption format with proper authentication, or decrypt into a tightly secured staging area and pass to Spring Batch only after full-file verification. Design so unverified plaintext is never committed to the database.

### 7.1. @StepScope bean for small files

Assuming `AesGcmFileCodec`, a `KeyProvider` supplying `SecretKey` by config reference, and a `Payment` model:

```java
package com.example.batch.security;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.io.IOException;

import javax.crypto.SecretKey;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ByteArrayResource;

@Configuration(proxyBeanMethods = false)
class SensitiveInputConfig {

    @Bean
    @StepScope
    FlatFileItemReader<Payment> encryptedPaymentReader(
            @Value("#{jobParameters['encryptedInputFile']}")
                    String inputFile,
            AesGcmFileCodec codec,
            KeyProvider keyProvider) throws IOException,
                    GeneralSecurityException {

        byte[] ciphertext = BoundedFileReader.readLimited(
                Path.of(inputFile),
                AesGcmFileCodec.MAX_ENCRYPTED_BYTES);

        // Reference identifies KMS-managed key, not a raw key.
        SecretKey key = keyProvider.loadDecryptKey(
                "batch-payments-v1");

        // Entire GCM tag is verified before building the reader.
        byte[] plaintext = codec.decrypt(ciphertext, key);

        return new FlatFileItemReaderBuilder<Payment>()
                .name("encryptedPaymentReader")
                .resource(new ByteArrayResource(plaintext))
                .encoding(StandardCharsets.UTF_8.name())
                .strict(true)
                .linesToSkip(1)
                .delimited()
                .names("id", "amount")
                .fieldSetMapper(fs -> new Payment(
                        fs.readLong("id"),
                        fs.readBigDecimal("amount")))
                .build();
    }
}
```

In this example, `Payment` is a model with a constructor taking `long` and `BigDecimal`; `KeyProvider` is an application-defined interface:

```java
package com.example.batch.security;

import javax.crypto.SecretKey;

public interface KeyProvider {
    SecretKey loadDecryptKey(String keyReference);
}
```

**This is a small-file demo architecture**, not the default recommendation for all sensitive data. `ByteArrayResource` keeps plaintext in the Java heap until the resource/reader becomes unreachable; `@StepScope` lives for the duration of a `StepExecution`. For a 5 GiB file, this approach is unsuitable and risks `OutOfMemoryError`.

An improvement for small files is passing AAD carrying `businessDate`/`fileId`, though the format and codec must then change consistently across both encrypt and decrypt to authenticate that metadata.

### 7.2. Why not decrypt before verifying and write to DB immediately?

With whole-file authenticated encryption, results are trustworthy only after verifying **the entire authentication tag**. If code reads a decrypted stream and lets the item writer commit chunks before checking the final tag, an attacker could inject forged rows into the database before causing an integrity failure at the end.

For whole-block encrypted files, safer patterns are:

- **Verify/decrypt the entire file before exposing plaintext to the reader** (bounded memory or secure staging).
- Use a **standardized streaming encryption format** with per-frame authentication and whole-file validation, ensuring commits/publishing do not finalize until the entire file validates per contract.
- Publish results only after a complete integrity check; if written temporarily to DB, staging must be isolated with dedicated rollback/discard/publish controls rather than going straight to live business tables.

Spring Batch chunk commits cannot automatically "undo" previously committed chunks if an invalid tag is discovered at the end of the file.

---

## 8. Large files: streaming encryption and authentication

### 8.1. Pitfalls of CipherInputStream with AES-GCM

Java includes `CipherInputStream` and `CipherOutputStream`. While useful for some modes, **you should not rely on `CipherInputStream` by default to decrypt AES-GCM data requiring integrity verification**.

Java's Javadoc warns that `CipherInputStream` may catch certain integrity-related exceptions (such as `BadPaddingException`) **without propagating them to callers**, making it unsuitable for authenticated decryption modes like GCM in some scenarios. A program reading until EOF might remain unaware that verification failed if it relies on a wrapper that swallows errors unexpectedly.

The guarantee required is: **tag verification failure must fail the job and never release data**. Use APIs or vetted libraries with explicit authentication contracts; never equate "read to end of stream" with "valid file."

### 8.2. Whole-file AES-GCM and memory

With `Cipher.doFinal` over the entire payload, the `AesGcmFileCodec` demo loads the file into a byte array. Some JCA providers buffer large amounts of ciphertext/decoded output until tag verification, so do not assume calling `Cipher.update` in a loop automatically creates a constant-heap streaming decryptor for multi-GB files.

To process large files, choose a format/protocol with **built-in streaming authentication**, or use tools/libraries audited for file encryption.

### 8.3. Record/frame-based AEAD

A streaming format can split plaintext into size-bounded frames, encrypting each frame with its own key/nonce/AAD:

```text
File header:
  version, algorithm, key reference/wrapped DEK,
  fileId, declared dataset/business identity

Frame 0:
  index=0, nonce0, ciphertext0, tag0
Frame 1:
  index=1, nonce1, ciphertext1, tag1
...
Final authenticated record:
  final marker, frame count, total length,
  manifest/digest per protocol
```

A sound design must at minimum solve:

- **Nonce uniqueness** for every frame under the same key, including across crashes/restarts.
- **Frame ordering:** reject reordered frames.
- **Truncation detection:** reject files containing only initial frames even if each frame is valid.
- **Replay/mix-and-match:** reject frames spliced from another file encrypted with the same key.
- **Version/key ID binding:** relevant metadata must be authenticated via AAD.
- **Atomic completion:** know when the entire file is complete and safe to publish.
- **Maximum frame size:** never let callers allocate unbounded buffers from untrusted length headers.
- **Restart semantics:** never reuse nonces or resume from under-authenticated crypto state.

**This describes the requirements, not an invitation to invent a custom crypto format.** A minor flaw in frame counts, final markers, or nonces can let a truncated or spliced file pass validation. For production, prefer reviewed formats/libraries compatible with the receiving party.

### 8.4. Secure staging when full-file verification is required before processing

If an external file contract uses a single trailing AES-GCM tag and files are very large, you may need a carefully reviewed decryption step writing plaintext to a **disk-encrypted, tightly permissioned staging zone**, transitioning to "verified" only after full-file authentication succeeds.

```text
encrypted input
       │
       ▼
restricted staging process
  ├── decrypt to protected temporary area
  ├── verify complete authentication tag
  └── if invalid: delete/quarantine, never publish
       │
       ▼ only verified
      ItemReader
       │
       ▼
 Spring Batch processing
       │
       ▼
 encrypted output + atomic publish
```

Limitations of this approach:

- Plaintext **resides on disk** temporarily; if regulations forbid it, this option is disallowed.
- You must govern ACLs, filesystem encryption, mount options, symlinks, snapshots, backups, swap, page cache, and diagnostics.
- Deleting a temp file does not mean bytes are physically erased from SSDs, copy-on-write filesystems, or cloud snapshots.
- Decrypt privileges and staging read privileges should be separated into least-privilege roles.
- Transitioning to verified and publishing must rely on tamper-resistant manifests/audits.

**If plaintext staging is prohibited**, use a pipeline built on standard streaming AEAD with appropriate staging data/commit modeling, or delegate decryption to a dedicated security service.

---

## 9. Key management: what actually determines system security

### 9.1. Never hardcode keys

Never store real keys in:

- Source code, Git repositories, or committed `application.yml` files.
- Command-line arguments visible in process listings.
- URLs, query strings, logs, traces, or exception messages.
- `JobParameters`, `ExecutionContext`, or `BATCH_*` metadata tables.
- Docker images, container layers, or build artifacts.
- Plaintext companion files sitting next to ciphertext.

Bad example:

```java
byte[] key = "my-secret-password-32-bytes....."
        .getBytes(StandardCharsets.UTF_8);
SecretKey unsafeKey = new SecretKeySpec(key, "AES");
```

An ordinary password does not become a secure AES key merely by padding/truncating to 16 or 32 bytes. If deriving from a password, use a standard key derivation function with proper salt/parameters; for production batch systems, prefer keys from KMS/vault rather than building custom password-based encryption.

### 9.2. Envelope encryption

A standard pattern:

- **DEK (data encryption key):** key used to encrypt one file's data.
- **KEK (key encryption key):** key managed by KMS/HSM used to wrap/unwrap the DEK.
- **Encrypted DEK:** wrapped DEK stored alongside the ciphertext header/manifest by design.
- **Key ID/version:** indicates which key unwraps it—not a secret.

```text
KMS/HSM holds KEK
      │
      ├─ Generate/wrap a DEK for the file
      ▼
     DEK ─────────────► AES-GCM(plaintext, nonce, AAD)
      │                          │
      │                          ▼
      └─ wrap under KEK      encrypted file + auth tag
               │                 │
               ▼                 │
        wrapped DEK + key ID ─────┘
                  │
              store in manifest/header

On decrypt:
  read key ID → KMS unwraps DEK → verify AEAD → process
```

Benefits:

- Issue a distinct DEK per file, bounding exposure of any single DEK.
- No need to hold the same raw master key inside every worker.
- KMS IAM/auditing governs who can unwrap.
- KEKs can rotate or DEKs can be rewrapped via supported workflows without always decrypting and re-encrypting all data.

**Distinction:** rotating KEK / rewrapping DEKs does not necessarily change file ciphertext; rotating DEKs usually requires decrypting and re-encrypting the file. Every change must match the format, AAD, and readability of historical files.

### 9.3. Choosing KMS permissions

Apply least privilege:

| Principal | Required permissions | Should not have |
|---|---|---|
| Inbound worker | Unwrap/decrypt specific key/dataset | Raw KEK export, access to all data zones |
| Output worker | Generate data key or encrypt/wrap for approved key | Decrypt all historical files unless needed |
| Monitoring dashboard | Read job status, masked metadata | Decrypt data or read plaintext |
| Operator | View audits, coordinate, and request recovery per role | Raw keys or other tenants' secrets |
| File consumer | Decrypt only authorized files/datasets | Keys of other partners/regions |

Identity can come from workload identity/roles attached to the process, avoiding long-lived secrets in config files. In multi-tenant setups, verify tenant/file ownership before requesting decryption; **a key ID declared inside an external file must never bypass authorization policies**.

### 9.4. Key rotation, retention, and recovery

If files must be retained for seven years, decryption capability must also survive for that retention window. Deleting keys too early permanently loses files. Conversely, retaining keys indefinitely after data expires increases risk.

Define policies for:

1. Which key version encrypted which file.
2. Who can decrypt and during which time window.
3. Upon rotation, whether old files retain old keys or are rewrapped/re-encrypted.
4. Upon key compromise, scope of affected files and replacement workflow.
5. Upon data deletion/crypto-shredding, impact on backups and object versions.
6. Disaster recovery of KMS/keys and metadata; periodic recovery drills.

Never log raw `SecretKey.getEncoded()` or emit unwrapped DEKs to observability systems. The JVM can retain key copies in memory; minimize lifetime and restrict memory dump access.

---

## 10. Integrating encryption at Spring Batch step boundaries

### 10.1. Integration models

| Model | Approach | Strengths | Considerations |
|---|---|---|---|
| Decrypt first, process later | Dedicated Tasklet verifies input and produces verified resource | Separation of concerns, fails fast | Plaintext staging if not in-memory |
| Reader reads encrypted format | Custom `ItemStreamReader` or standard crypto library adapter | Can minimize plaintext staging | Must guarantee auth, restart, nonce/frame ordering |
| Encrypt after writer finishes | Step writes temp output → encrypt/publish step | Can validate output and publish only when complete | Temp plaintext output must be protected |
| Writer emits ciphertext directly | Custom writer/standard streaming encryption | Avoids plaintext output files | Authentication, commits, and failure/restart are complex |

For sensitive workloads needing checkpoints, establish a clear architecture:

```text
Job: secureTransferJob
  │
  ├─ Step A: verifyAndPrepareInput
  │     ├─ check identity/manifest
  │     ├─ fetch key per authorization
  │     └─ verify decrypt integrity
  │
  ├─ Step B: processData
  │     ├─ ItemReader
  │     ├─ ItemProcessor
  │     └─ ItemWriter writes to unpublished zone
  │
  └─ Step C: encryptAndPublish
        ├─ produce complete ciphertext
        ├─ verify format/tag/manifest
        ├─ conditional/atomic publish
        └─ record audit + cleanup policy
```

**Each step must have a clear contract for temp data and completion state.** If Step C fails after publishing the file but before `JobRepository` commits status, a restart may re-run Step C. Publishing must therefore be **idempotent and reconcilable**, not relying on an assumption that the filesystem rolls back alongside the database.

### 10.2. JobParameters must not contain secrets

Example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("fileId", "payments-2026-11-15", true)
        .addString("inputObjectKey", "incoming/2026-11-15.enc", false)
        .addString("outputObjectKey", "outgoing/2026-11-15.enc", false)
        .toJobParameters();
```

Never pass raw DEKs, API tokens, private keys, or plaintext in `JobParameters`; they are persisted in metadata and can surface in monitoring APIs. `fileId`/`businessDate` are business identifiers; `inputObjectKey` is strictly controlled and masked in logs/UIs if sensitive itself.

Likewise, `ExecutionContext` should hold small checkpoints (confirmed offset, segment ID, file version/manifest digest) rather than keys or decrypted record payloads.

### 10.3. Restart, retry, and output encryption

Identify these scenarios:

| Failure point | Possible leftover state | Required recovery |
|---|---|---|
| KMS denies permission | File not decrypted | Fail closed; fix permissions before restart |
| Input fails tag check | Untrusted file | Quarantine ciphertext, commit no data |
| Process fails mid-job | Some chunks committed | Restart from checkpoint, handle temp output appropriately |
| Writer did not finish flushing | Incomplete temp output | Delete/rebuild or resume per supported format |
| Encrypted but not published | Valid temp ciphertext | Reconcile and publish safely |
| Publish succeeded but step metadata commit failed | Destination already has file despite `StepExecution` FAILED | Check business key/manifest before republishing |
| Worker crashes during plaintext cleanup | Temp file may remain | Audited sweeper with TTL and restricted access |
| Key rotated between attempts | Output has different ciphertext | Stable key version/manifest or controlled re-encryption |

With AES-GCM, **never resume an encryption session mid-file using unverified nonce/cipher state**. Without a strict frame/checkpoint protocol, the safer approach is rewriting a **new temp output with a fresh nonce/DEK**, then publishing conditionally and reconciling.

### 10.4. Batch commit vs. file publish

Spring Batch database transactions and filesystems/S3 generally do not share a single transaction:

```text
Chunk commit in DB ─────────────── Done
       │
       │   (does not auto-commit/roll back file publish)
       ▼
Output file object ─────────────── May not be published yet

Or:
Output published ───────────────── Done
       │
       ▼
JobRepository metadata update ──── Failed
```

Design one of these strategies: staging + final manifest, atomic rename, conditional object creation, outbox/saga, or reconciliation by business key. Never assume `@Transactional` covers remote object storage.

---

## 11. AAD and protecting exact file identity

### 11.1. What is authenticated metadata?

AAD (associated authenticated data) is **not encrypted**, yet it is folded into AEAD authentication. For instance, a file containing data for:

- `tenantId=merchant-12`
- `businessDate=2026-11-15`
- `dataset=customer-balance`
- `schemaVersion=4`
- `fileId=balance-2026-11-15-merchant-12`

If these fields govern which table/tenant/date receives the data, they must be **cryptographically bound** to the ciphertext. Otherwise, someone able to rename objects could swap tenant A's valid ciphertext into tenant B's path.

JCA-level example:

```java
byte[] aad = ("v1|tenant=merchant-12"
        + "|date=2026-11-15"
        + "|dataset=customer-balance")
        .getBytes(StandardCharsets.UTF_8);

cipher.updateAAD(aad);
byte[] encrypted = cipher.doFinal(plaintext);
```

Decryption must pass **the exact same AAD bytes**, not merely a "similar-looking" string with different ordering, Unicode normalization, or encoding. Define an explicit canonical serialization including field lengths/delimiters rather than ad-hoc string concatenation.

### 11.2. Where does metadata come from?

If all AAD comes from an untrusted file header, an attacker could swap both header and ciphertext from another file encrypted under the same key and still pass per-file authentication. To prevent file swapping, match **expected AAD from a trusted source** (signed manifest, controlled job parameters, authorized mapping table) against file metadata before importing.

### 11.3. Do not put sensitive info into AAD arbitrarily

AAD is not secret. Customer names, emails, account numbers, or special attributes placed in headers/AAD remain readable in plaintext. Include only minimal required IDs or metadata; if an identity itself must stay confidential, encrypt it inside the payload or protect the manifest separately.

---

## 12. PGP/OpenPGP, AES-GCM, KMS, and storage-layer encryption

Rolling a custom AES-GCM format with a proprietary header is not always right.

| Requirement | Common approach | Notes |
|---|---|---|
| Periodic partner file exchange | Contract-agreed OpenPGP/PGP | Public/private keys, signing, integrity, interoperability |
| Small internal files, system-owned format | AEAD with standard key management | Do not build a weak custom protocol; ensure nonce/AAD/version |
| Cloud object storage mainly against storage theft | SSE-KMS and IAM | Authorized object reads still yield plaintext; may still need app encryption |
| Very large internal service-to-service files | Audited streaming encryption format/library | Frame auth, truncation, key rotation, restart |
| Multiple recipients for the same file | Envelope encryption/public key wrapping | Per-recipient access, manage wrapped DEKs |
| Sender authenticity required | Digital signatures or contract-defined sender auth | Symmetric AES-GCM alone cannot prove a single sender if multiple parties share the key |

**PGP encryption and PGP signing are distinct functions.** An encrypted file does not necessarily carry a digital signature proving who sent it. When sender identity verification is required, properly verify signatures/certificates/public keys and trust policies.

**Cloud SSE-KMS** protects data at rest on storage; it is valuable yet does not replace sharing ciphertext with partners. Any recipient authorized to read the storage-decrypted object sees plaintext.

Select solutions based on file-sharing contracts, audit/compliance requirements, interoperability, and operational readiness—not algorithm names alone.

---

## 13. Testing cryptography and file security

Do not test AES against one fixed ciphertext "golden answer" and call the system secure. Test **behavior** and error paths using dedicated test keys and synthetic data—never production keys.

### 13.1. Codec unit tests

JUnit Jupiter example:

```java
package com.example.batch.security;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Arrays;

import javax.crypto.AEADBadTagException;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class AesGcmFileCodecTest {

    private AesGcmFileCodec codec;
    private SecretKey key;

    @BeforeEach
    void setUp() throws GeneralSecurityException {
        codec = new AesGcmFileCodec();

        KeyGenerator generator =
                KeyGenerator.getInstance("AES");
        generator.init(256);
        key = generator.generateKey();
    }

    @Test
    void roundTripRestoresOriginalBytes()
            throws GeneralSecurityException {

        byte[] input = "id,amount\n1,100.00\n"
                .getBytes(StandardCharsets.UTF_8);

        byte[] encrypted = codec.encrypt(input, key);
        byte[] decrypted = codec.decrypt(encrypted, key);

        assertArrayEquals(input, decrypted);
        assertFalse(Arrays.equals(input, encrypted));
    }

    @Test
    void tamperedTagFailsAuthentication()
            throws GeneralSecurityException {

        byte[] encrypted = codec.encrypt(
                "confidential".getBytes(StandardCharsets.UTF_8),
                key);

        encrypted[encrypted.length - 1] ^= 0x01;

        assertThrows(AEADBadTagException.class,
                () -> codec.decrypt(encrypted, key));
    }

    @Test
    void wrongKeyCannotDecrypt()
            throws GeneralSecurityException {

        KeyGenerator generator =
                KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey otherKey = generator.generateKey();

        byte[] encrypted = codec.encrypt(
                "private".getBytes(StandardCharsets.UTF_8),
                key);

        assertThrows(AEADBadTagException.class,
                () -> codec.decrypt(encrypted, otherKey));
    }

    @Test
    void truncatedFileIsRejected()
            throws GeneralSecurityException {

        byte[] encrypted = codec.encrypt(
                "1234567890".getBytes(StandardCharsets.UTF_8),
                key);

        byte[] shortened = Arrays.copyOf(
                encrypted, encrypted.length - 4);

        assertThrows(GeneralSecurityException.class,
                () -> codec.decrypt(shortened, key));
    }

    @Test
    void oversizedPlaintextIsRejected() {
        byte[] oversized =
                new byte[AesGcmFileCodec.MAX_PLAIN_BYTES + 1];

        assertThrows(IllegalArgumentException.class,
                () -> codec.encrypt(oversized, key));
    }
}
```

Assertions illustrated:

- Round trip restores exact bytes without altering encoding or newlines.
- Altering tag/ciphertext fails decryption.
- Wrong keys never produce "garbage plaintext that keeps processing."
- Truncated files are rejected.
- Size bounds are enforced.

For `AEADBadTagException`, exact exceptions depend on cryptographic APIs/providers and wrapping. The unit test above calls `Cipher.doFinal` directly via the JCA codec, so asserting tag failure directly is appropriate; if adding wrappers, assert the exception chain or safe error code rather than relying solely on message strings.

### 13.2. Spring Batch integration tests

Create a small CSV fixture, encrypt it with a test key, and write it as encrypted input. Run the job with the decrypting reader and output writer; verify:

1. Valid key/tag files are read with expected `readCount`/`writeCount`.
2. Invalid tag files fail the step/job (`FAILED`) and commit **no** business data.
3. Wrong-key files are not retried infinitely.
4. Files with invalid magic/version are clearly rejected.
5. Oversized files are rejected without heap growing proportionally to file size.
6. When the job fails mid-run, encrypted output is not published to consumers.
7. Restarting with the same identifying `JobParameters` does not overwrite published outputs or unsafely reuse nonces/key state.
8. Logs, `ExitDescription`, quarantine files, and metrics leak no record contents or raw keys.

For large pipelines, also test missing final frames, reordered frames, spliced frames from another file, and mismatched manifests. These tests must match the **actual streaming format** in use; do not generalize assumptions from the full-file AES-GCM demo to every library.

### 13.3. Key management tests

Important operational scenarios:

| Scenario | Verification outcome |
|---|---|
| KMS/Vault denies decrypt | Job fails closed without processing the file |
| Key ID does not belong to authorized tenant | Rejected before or at key retrieval |
| Key rotated while old file remains valid | Readable using old key version per policy |
| Key revoked | No longer decryptable by unauthorized principals |
| Transient KMS timeout | Bounded retries without turning errors into empty plaintext |
| Worker restarts after fetching DEK | Proper key lifecycle and recovery without logging the DEK |
| File decrypted under different AAD context | Authentication fails |
| Manifest points to a different file ID | Reject importing under wrong business identity |

Do not use production KMS in tests; use a fake provider or low-privilege test KMS environment with isolated keys.

### 13.4. Path, permission, and cleanup tests

- `../` paths or symlinks escaping the allowlisted root must be blocked.
- Workers must not read files belonging to other tenants.
- Temporary directories must not grant read/write access to unrelated users.
- Failures mid-encrypt/decrypt must delete or quarantine temp files per policy.
- Post-crash temp cleanup uses an audited sweeper without deleting files actively in use by a worker.
- Never log plaintext by default.
- Once an encrypted file is published, consumers never observe a half-written version.

---

## 14. Security monitoring and auditing

### 14.1. Events to record

| Event | Safe data to log | Do not log |
|---|---|---|
| FILE_RECEIVED | fileId, dataset, timestamp, size | File contents |
| DECRYPT_STARTED | executionId, key reference, fileId | Raw key/DEK |
| AUTHENTICATION_FAILED | fileId, error type, correlationId | Full ciphertext/plaintext, key material |
| DECRYPT_COMPLETED | fileId, elapsed, byte count | PII inside records |
| OUTPUT_ENCRYPTED | fileId, algorithm/version, keyId, size | Secret keys |
| FILE_PUBLISHED | controlled object key, manifest hash, businessDate | Credential URLs |
| CLEANUP_FAILED | temp object ID, error category | Secrets, record contents |
| KMS_ACCESS_DENIED | principal, key reference, operation | Key bytes |

Metrics should track encrypted file counts, tag verification failures, encrypt/decrypt durations, KMS errors, queue wait times, unprocessed file backlogs, lingering temp files, and publish outcomes. Use low-cardinality labels; never attach per-customer `fileId`s or private data as high-cardinality metric tags.

### 14.2. Distinguishing cryptographic errors from data errors

| Error | Classification |
|---|---|
| `AEADBadTagException` | Integrity violation/wrong key/wrong AAD; do not retry into plaintext |
| Unknown key version | Configuration or key lifecycle error; fail and investigate |
| KMS throttling/timeout | Infrastructure error eligible for bounded retries |
| Wrong file magic/version | Input violates format contract |
| Invalid CSV schema after valid decrypt | Data error, not a crypto failure |
| Filesystem full during output encryption | Storage error; keep state unpublished |
| Atomic move unsupported | Publish capability error; never silently downgrade if atomicity is mandatory |
| Access denied on staging zone | Permission error; do not broaden global permissions |
| Missing ciphertext file | Ingestion/scheduling error, not a wrong key |

If tag verification fails, never "salvage a few readable lines" and mark the job successful. For financial or PII datasets, the safe response is quarantining the **ciphertext** and opening an incident to verify file origin and keys.

---

## 15. Performance: security and chunk memory

### 15.1. AES-GCM does not manage chunk memory by itself

A line-by-line `FlatFileItemReader` keeps the working set small. Yet if prior code calls `Files.readAllBytes()` to decrypt a 5 GiB file, memory overflows **before chunk processing even starts**.

Separate these budgets:

- **Encrypted file size**: may be many GiB.
- **Cryptographic framing buffer size**: bounded per reviewed design.
- **Spring Batch chunk size**: items/transaction.
- **Reader prefetch/page size**: items retained by the reader.
- **Writer buffer**: bytes awaiting flush/encryption.
- **Concurrency**: simultaneous active files/steps/partitions.

A mental model:

```text
Peak memory ≈
  Spring/JVM baseline
  + activeFiles × crypto working buffer
  + activeChunks × chunk object graph
  + reader/writer/ORM buffer
  + native/off-heap memory
  + GC headroom
```

Measure these values on realistic workloads. Never shrink `chunkSize` while ignoring a whole-file crypto buffer.

### 15.2. Where to compress

Normally, if compression is needed to save space, **compress before encrypting**, because ciphertext has high entropy and compresses poorly afterward. However, decompressing untrusted inputs requires output size limits to prevent decompression bombs. If plaintext mixes secrets with attacker-controlled data in a protocol with observable responses, also assess compression side channels in your threat model.

### 15.3. Tracking throughput and timeouts

Security introduces overhead:

- Calling KMS to generate/unwrap DEKs.
- CPU for encryption/decryption.
- Writing temp files and publishing.
- Hashing/checksums, manifests, and auditing.
- Verifying authentication tags before releasing data downstream.

For small files, KMS/network overhead can outweigh AES cost. For large files, I/O is usually the bottleneck; benchmark the AES-GCM implementation, buffer sizes, storage throughput, and concurrent job count.

Never raise concurrency so high that a single worker holds multiple large plaintexts in RAM or exhausts KMS quotas. Short-term DEK caching may be used if policy permits and lifecycle/auditing are clear, but never cache raw KEKs or retain keys indefinitely.

---

## 16. Retention, backups, and data deletion compliance

Sensitive files can exist in many copies:

- Encrypted input file.
- Temporary decrypted representation.
- Pre-encryption temp output.
- Encrypted output.
- Quarantine/error files.
- Bucket version history.
- Filesystem snapshots/backups.
- Logs, tracing payloads, heap dumps.
- Caches/CDNs or partner-side copies.

A retention plan must specify **how long each copy is kept**, who deletes it, how deletion is verified, and whether key deletion impairs legitimate recovery.

### 16.1. Secure deletion is not trivial

`Files.deleteIfExists(path)` removes the directory entry, not necessarily the plaintext bytes on SSDs, snapshots, copy-on-write filesystems, cloud backups, or page caches. Avoiding plaintext on disk altogether is therefore preferred when the threat model is strict; if unavoidable, use encrypted volumes, tight permissions, and lifecycle policies.

### 16.2. Decrypting after many years

If files are archived for seven years, the ability to unwrap DEKs must remain intact for that entire period; maintain key backup/recovery procedures, versioning, and periodic archive readability drills. If a KMS key is deleted, ciphertext may become unrecoverable even when file backups remain intact.

### 16.3. Do not equate encryption with compliance

Encryption is one technical control. Obligations around notification, classification, data minimization, authorization, auditing, retention periods, and data access/deletion requests must still be evaluated independently under applicable contracts and laws.

---

## 17. Sensitive file incident runbook

### Step 1 — Scope the incident

Record `jobName`, `jobExecutionId`, `fileId`, `businessDate`, key reference, file origin, and output state. Never attach plaintext files to tickets or chat.

### Step 2 — Classify the failure

- Wrong format/header/version?
- Tag authentication failed?
- KMS access denied, key disabled, or timeout?
- File truncated in transit?
- Filesystem/storage out of space?
- Publish happened while JobRepository failed to update?
- Plaintext staging cleanup failed?

### Step 3 — Fail closed and isolate

If integrity fails verification, **do not let data enter business systems**. Move ciphertext and manifests into a controlled quarantine zone, preserve evidence for investigation, and never brute-force decrypt with arbitrary keys outside policy.

### Step 4 — Controlled recovery

- Ask the partner to resend the file if corrupted.
- Restore a valid key version through KMS governance if permitted.
- Verify manifest/AAD/business identifiers.
- If output was already published, reconcile state before rerunning to prevent duplicates.
- If restarting, use the exact identifying `JobParameters`.
- Never bypass tag verification just to hit an SLA.

### Step 5 — Check for plaintext traces

Inspect temp files, logs, error/quarantine files, heap dumps, backups, and whether consumers already read outputs. If exposure is possible, trigger security incident response and restrict access per policy.

### Step 6 — Reconcile and close

Verify checksums/manifests, record counts, alignment with `businessDate`/tenant, file permissions, and complete audit trails. Close the incident only once data is confirmed processed and published accurately.

---

## 18. Common mistakes

| Mistake | Risk | Right approach |
|---|---|---|
| Treating Base64 as encryption | No security | AEAD/reviewed encryption format |
| Using AES/ECB | Leaks patterns, no integrity | AES-GCM or standard format |
| Using AES-CBC without authentication | Silent data tampering possible | Authenticated encryption |
| Reusing AES-GCM nonce with same key | Breaks confidentiality and integrity | Nonce uniqueness and key lifecycle |
| Hardcoding raw AES keys in YAML/Git | Exposes key and all files | KMS/vault, least privilege |
| Putting raw keys in JobParameters | Key persisted in `BATCH_*` | Key reference, KMS authorization |
| Encrypting only output, forgetting input/temp | Plaintext lingers in multiple places | Evaluate the entire data flow |
| Using `CipherInputStream` without checking AEAD integrity | May silently swallow auth errors | API/format guaranteeing tag verification |
| Streaming decrypt and committing chunks before full-file auth | May commit forged ciphertext data | Verify before publishing or staging isolation |
| Reading huge files with `readAllBytes` | OOM, GC pressure | Bounded input + proper streaming format |
| Writing ciphertext directly to public output name | Consumer reads incomplete file | Temp + atomic/conditional publish |
| Assuming `@Transactional` rolls back external files | File/object store is not in the DB transaction | Idempotent publish and reconciliation |
| Reusing nonces/cipher state on restart | Cryptographic failure risk | Reviewed restart protocol or re-encrypt new file |
| Checking only file magic/header | Does not prove integrity | GCM tag/signature/manifest verification |
| Taking AAD solely from untrusted sources | Swapping files across tenants/periods | Expected AAD from manifest/trusted business identity |
| Logging decrypted records on error | Leaks PII and secrets | Structured logs, masking, audit |
| Deleting temp and assuming physical erasure | Snapshots/SSDs retain copies | Avoid plaintext disk, lifecycle/crypto controls |
| Not retaining key versions | Archived files become unreadable | Key ID/version, rotation, and retention |
| Inventing ad-hoc streaming AEAD | Easy to miss truncation/ordering/replay | Reviewed libraries/formats |
| Ignoring KMS permission errors to proceed | Fail-open and corrupted state | Fail closed |

---

## 19. Hands-on exercises

### Exercise 1 — Data classification

Diagram a job receiving customer CSVs over SFTP, cleansing them, and writing to object storage. List every place holding ciphertext/plaintext, authorized principals, and retention policies for input, temp, output, backups, and error/quarantine files.

### Exercise 2 — AES-GCM round trip

Use `AesGcmFileCodec` to encrypt and decrypt a small UTF-8 file. Verify output bytes match the input, including Vietnamese diacritics, newlines, and commas inside fields.

### Exercise 3 — Tamper detection

Encrypt a small file, flip one byte in the ciphertext/tag, and attempt decryption. Verify the exception propagates; the job calls no writer and publishes no data from the tampered file.

### Exercise 4 — Wrong key and key versions

Generate two AES keys in a test. Encrypt with key A, attempt decrypting with key B, and confirm failure. Design `keyId`/wrapped DEK metadata and explain how old files stay readable after KMS rotation per policy.

### Exercise 5 — Authenticating business identity

Extend the demo codec to accept AAD containing `tenantId`, `businessDate`, and `fileId` in canonical serialization. Verify decrypting with different AAD fails tag verification. Explain why AAD metadata must be cross-checked against a trusted expectation.

### Exercise 6 — Spring Batch reader

Write a `@StepScope` reader using `ByteArrayResource` for encrypted files under 10 MiB. Run integration tests: valid file → accurate read/write counts; invalid tag → `FAILED` and no output published.

### Exercise 7 — Large files

Suppose a 20 GiB file must be processed under a 1 GiB heap. Compare a bounded-memory streaming encryption format against secure staging. Detail the required nonce rules, frame ordering, truncation detection, final marker, AAD, and commit boundaries.

### Exercise 8 — Crash during publish

Simulate a file already published while updating `StepExecution` in the repository fails. Design manifest/conditional publishing so restarts do not overwrite improperly and consumers never receive two files for the same `businessDate`.

### Exercise 9 — KMS outage

Use a `KeyProvider` simulating access denied and timeouts. Verify the system refuses decryption when unauthorized, applies bounded retries only to transient errors, and never logs keys.

### Exercise 10 — Security runbook

Write a runbook for a partner file failing tag authentication combined with plaintext staging cleanup failure. Specify evidence to preserve, what operations roles may view, and how to confirm no invalid file was published.

---

## 20. References

- [NIST SP 800-38D — Galois/Counter Mode (GCM)](https://csrc.nist.gov/pubs/sp/800/38/d/final): AES-GCM principles, IV/nonce, and authentication.
- [NIST SP 800-57 — Key Management](https://csrc.nist.gov/projects/key-management/key-management-guidelines): key management, lifecycle, and authorization.
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): algorithm selection, authenticated encryption, and key management.
- [Java 17 — Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): `AES/GCM/NoPadding`, `updateAAD`, and `doFinal`.
- [Java 17 — GCMParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): authentication tag length and IV.
- [Java 17 — CipherInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/CipherInputStream.html): integrity exception propagation limits when decrypting authenticated modes.
- [Java 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): cryptographic random generation.
- [Spring Batch — Flat File Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files.html): file reading/writing and `Resource`.
- [Spring Batch — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `open/update/close` lifecycle and checkpoint/restart.
- [Spring Batch — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): chunk transactions and per-item processing.
- [Spring Batch — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): metadata and transactions.
- [Spring Security Reference](https://docs.spring.io/spring-security/reference/): application authorization and relevant service identities.
- [OpenPGP — RFC 9580](https://www.rfc-editor.org/rfc/rfc9580.html): OpenPGP message format for contract-based data exchange.

**Summary:** encrypting sensitive files in Spring Batch is more than turning plaintext into ciphertext. A secure solution requires **authenticated encryption**, tightly governed and permissioned keys, controls over every place plaintext may surface, full file verification before trusting data, and idempotent publish/restart mechanics. For small files, JCA AES-GCM examples clarify the fundamentals; for large files or partner exchanges, choose standard formats/libraries with reviewed authentication and key lifecycles. Only when these boundaries are designed together can a batch job process sensitive data while preserving correctness, recoverability, and end-to-end security.
