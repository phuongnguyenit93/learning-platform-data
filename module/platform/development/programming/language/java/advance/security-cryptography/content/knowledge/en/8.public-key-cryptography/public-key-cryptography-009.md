# 8.9 Limitations of Using Asymmetric Algorithms Instead of Bulk Data Encryption

**Asymmetric encryption (public-key encryption)** solves an important problem: a sender can use the recipient's **public key** to encrypt a secret that only the holder of the corresponding **private key** can decrypt, provided the algorithm and protocol are used properly. However, that **does not mean** RSA or public-key primitives are suitable for directly encrypting a multi-MB/GB file, a video stream, or an entire database.

The practical approach is **hybrid encryption**: an asymmetric algorithm/KEM or key-agreement protocol **establishes/protects a small session key**; a symmetric **AEAD** algorithm such as AES-GCM encrypts and authenticates the **large payload**. This lesson focuses on the technical limits of using asymmetric cryptography for bulk encryption, how to calculate RSA-OAEP limits accurately, why "splitting a file into chunks and RSA-encrypting each chunk" is not a solution, and how to design envelope encryption in Java 17+.

## 1. Asymmetric and Symmetric Cryptography Perform Two Different Jobs

| Aspect | Asymmetric encryption / public-key mechanisms | Symmetric AEAD encryption |
| --- | --- | --- |
| Key material | Public/private keys, or key pairs and a shared secret in key agreement | A shared secret key or data-encryption key (DEK) |
| Typical job | Encrypting/wrapping small session keys, secret establishment/exchange, digital signatures (a separate primitive) | Encrypting arbitrary amounts of data **within each algorithm/protocol's limits**, while authenticating ciphertext and AAD |
| Computational cost | Usually substantially higher per operation; RSA private-key operations are especially expensive | Usually efficient for large byte volumes; hardware acceleration available on many CPUs |
| Direct input length | For RSA-OAEP, bounded by modulus and hash/padding, typically a few hundred bytes | Based on mode and nonce/message limits; not bound by a "190-byte RSA-2048" limit |
| Output size | One RSA encryption returns ciphertext equal to the modulus length, regardless of how short plaintext is | Typically near plaintext length plus tag/nonce/metadata if packaged by a protocol |
| Origin authentication | **RSA encryption using only the recipient's public key does not authenticate sender identity** | AEAD authenticates data under a known key; does not automatically bind sender identity |
| Management needs | Public-key trust, key ID, certificates, private key, padding, algorithm, and key rotation | Key generation/management, unique nonce/IV, AAD, tag, integrity, rotation, and policy |

**Important definition:** RSA encryption, RSA signatures, ECDSA signatures, ECDH key agreement, and KEMs are **different** primitives, even though all belong to the public-key world. You cannot take a digital signature and call it encryption, nor call ECDH a file encryption function.

An easy-to-remember summary:

> **Public keys protect or establish the data key; the symmetric data key protects the bulk bytes of the document.**

## 2. Plaintext Size Limit of RSA-OAEP

RSA operates modulo a modulus `n`, and the ciphertext of a single RSA encryption is a value encoded to the exact modulus size. With **RSA-2048**, the modulus is typically **2,048 bits = 256 bytes**. Yet the **maximum input is not 256 bytes**, because the RSA-OAEP padding mechanism requires space to ensure security.

### 2.1. The RSAES-OAEP Formula

Under the RSAES-OAEP mechanism in PKCS #1 (RFC 8017), if:

- `k` = number of **bytes** required to represent the RSA modulus;
- `hLen` = output byte count of the hash used in OAEP;
- `mLen` = number of plaintext bytes;

then we need:

```text
mLen <= k - 2 * hLen - 2
```

This is a **byte size limit**, not a limit on Unicode characters or Java `String.length()`.

With a 2,048-bit modulus, `k = 256`. When OAEP uses SHA-256, `hLen = 32`, so:

```text
maxPlaintext = 256 - 2 * 32 - 2 = 190 bytes
RSA ciphertext length = 256 bytes
```

If a file contains **191 bytes**, a single direct RSA-2048 + OAEP SHA-256 operation cannot encrypt it. Having a "2,048-bit RSA key" does not mean you can feed 2,048 bits or more of plaintext into that operation.

### 2.2. Comparing Configurations

| RSA Modulus | `k` | OAEP Hash / `hLen` | Max plaintext per RSA-OAEP operation | Ciphertext per operation |
| --- | ---: | --- | ---: | ---: |
| RSA-2048 | 256 bytes | SHA-1 / 20 bytes | 214 bytes | 256 bytes |
| RSA-2048 | 256 bytes | SHA-256 / 32 bytes | **190 bytes** | **256 bytes** |
| RSA-3072 | 384 bytes | SHA-256 / 32 bytes | 318 bytes | 384 bytes |
| RSA-4096 | 512 bytes | SHA-256 / 32 bytes | 446 bytes | 512 bytes |
| RSA-2048 | 256 bytes | SHA-512 / 64 bytes | 126 bytes | 256 bytes |

These values are **size limits**, not security recommendations for every combination. SHA-1 appears in the table only to illustrate the effect of `hLen`; new designs should use algorithms and profiles permitted by current security policy, never picking SHA-1 merely to increase input size. RSA-2048 also does not offer "2,048-bit strength": its estimated classical security level is only around **112 bits**, completely distinct from modulus size. Choosing RSA-3072/4096 or another public-key solution must weigh policy, data protection lifetime, and performance.

### 2.3. OAEP Parameters Must Be Fully Specified

In Java you often see transformation strings `"RSA/ECB/OAEPPadding"` or `"RSA/ECB/OAEPWithSHA-256AndMGF1Padding"`. The **ECB** token in RSA transformation names is an API convention and **does not mean RSA encrypts data blocks like AES-ECB**; RSA does not use ECB mode for files.

To avoid ambiguity between the **OAEP hash** and the **hash used in MGF1**, specify both explicitly via `OAEPParameterSpec`:

```java
OAEPParameterSpec oaep = new OAEPParameterSpec(
    "SHA-256", "MGF1", MGF1ParameterSpec.SHA256, PSource.PSpecified.DEFAULT
);
Cipher cipher = Cipher.getInstance("RSA/ECB/OAEPPadding");
cipher.init(Cipher.ENCRYPT_MODE, recipientPublicKey, oaep);
```

This is an **illustrative parameter-setup snippet**, not a standalone program: `recipientPublicKey` must be a `PublicKey` whose origin has been verified; the `import` statements appear in the complete program later.

Do not rely on provider defaults and assume every JVM/system picks the exact same OAEP hash/MGF1 hash. Parameter mismatches cause decryption failures or interoperability bugs. RSA-OAEP supports an optional `PSource.PSpecified` label; encryption and decryption must also use the exact same protocol-defined label.

### 2.4. Does Increasing RSA Key Size Solve Large Files?

**No.** RSA-4096 with OAEP SHA-256 still handles at most **446 bytes per plaintext operation**, while files can be millions or billions of bytes long. Increasing the modulus both enlarges keys/ciphertexts and typically slows private-key operations substantially.

With **RSA-2048/OAEP SHA-256**, trying to slice a **1 MiB = 1,048,576-byte** file into chunks of up to 190 bytes would require:

```text
numberOfRSAOperations = ceil(1,048,576 / 190) = 5,519
ciphertextSize = 5,519 * 256 = 1,412,864 bytes
overhead = 1,412,864 - 1,048,576 = 364,288 bytes
```

That is merely the **size cost** of splitting blocks, before even adding framing, sequence numbers, algorithm IDs, key IDs, versions, or integrity protection. The system would also execute **5,519 RSA encrypt operations** and thousands of **RSA private-key decrypt operations** instead of one RSA operation wrapping a small key and one AES pass over the file.

## 3. Why "Splitting a File and RSA-Encrypting Each Chunk" Is a Bad Design

### 3.1. Performance Unsuited for High Throughput

RSA relies on big-integer modular arithmetic, costing far more per byte than symmetric block cipher rounds over large volumes. Splitting a file into 5,519 blocks creates thousands of public-key operations, driving up CPU load and latency with chunk count; with an HSM/KMS, you also incur RPC overhead, throughput limits, and operational cost.

Symmetric algorithms such as **AES-GCM** are optimized for bulk byte processing, with AES/CLMUL hardware acceleration on many platforms. **There is no need to assert a single fixed speed ratio** for all CPUs/providers: benchmark in your real environment, yet the structural difference in workload is stark.

### 3.2. Every RSA Block Adds Significant Overhead

A 190-byte plaintext block becomes a 256-byte ciphertext block. Even if the final block has only 1 byte, it still occupies **256 bytes**. OAEP padding requires randomness, so encrypting the same plaintext with the same public key yields different ciphertexts; you cannot trim overhead after encryption.

For large files, the size of thousands of blocks plus metadata inflates transmission and storage compared to encrypting data with AES-GCM, which adds only a small tag plus header/nonce.

### 3.3. RSA-OAEP Does Not Turn Chunks into an Authenticated File

RSA-OAEP provides secure encryption when used properly in the right model, yet **is not an AEAD protocol for a whole file**. If you split a file into chunks yourself, you must manually solve:

- Chunk ordering and sequence numbers; preventing reordering or splicing chunks from another file.
- Preventing missing chunks, duplicate chunks, tail truncation, and content substitution.
- Authenticating metadata such as file ID, expected length, content type, and version.
- Detecting tampering under one unified policy, rather than only knowing whether each individual RSA operation decrypted some bytes.
- Error handling and padding-oracle/side-channel leaks via error messages or timing.

Missing any one of those layers can introduce severe vulnerabilities. Encrypting individual RSA blocks and concatenating them does not magically create *secure file encryption*. **Never invent an ad-hoc "RSA chunk mode"** to bypass the `mLen` limit.

### 3.4. Design/API Hazards

- Never use `RSA/ECB/NoPadding` as a trick to fit more bytes: **raw/textbook RSA is insecure** and does not solve bulk encryption.
- Never switch to `RSA/ECB/PKCS1Padding` just because its maximum plaintext is slightly longer than OAEP: RSAES-PKCS1-v1_5 carries padding-oracle risks and is not a default choice for new designs.
- Never use RSA **signatures** to "encrypt with a private key". Signatures serve authentication/integrity per signature standards; they **do not provide data confidentiality**.
- Never encrypt a file directly with an EC/ECDSA public key: ECDSA is a digital signature; ECDH/X25519 is a **key-agreement** mechanism, not `Cipher.doFinal(file)` for direct encryption.

## 4. The Right Solution: Hybrid Encryption / Envelope Encryption

In the RSA-OAEP + AES-GCM model, each file gets a short random **data-encryption key (DEK)**. The asymmetric part **only wraps the DEK**; the symmetric part encrypts the entire file.

### 4.1. Encryption Flow

```text
                   Sender
   [Verified recipient PublicKey]
                     |
    Generate random AES-256 data key (32 bytes)
                     |
             +-------+--------+
             |                |
    RSA-OAEP encrypt(DEK)   AES-GCM encrypt(file, DEK, nonce, AAD)
             |                |
      wrappedKey (256 B)    ciphertext || tag
             |                |
             +-------+--------+
                     |
       Envelope: header + keyId + wrappedKey
                  + nonce + ciphertext + tag
                     |
              Store / send to recipient
```

Steps:

1. **Verify the recipient's public key** via certificate/PKI, pinned key directory, or an authenticated key-delivery channel. If an adversary swaps the public key for theirs, the entire file could be encrypted for the adversary to open.
2. **Generate a fresh random DEK** (e.g., AES-256 = 32 bytes) using a CSPRNG/`KeyGenerator`; never use passwords or `new Random()` as keys.
3. **Wrap the DEK** with the recipient's RSA public key using RSA-OAEP with explicit parameters; output is a small RSA ciphertext, e.g., 256 bytes for RSA-2048.
4. **Generate a nonce/IV meeting AEAD requirements**; AES-GCM typically uses 96 bits = 12 bytes. Under the same AES key, **nonces must never repeat**. Generating a fresh DEK per file simplifies the nonce strategy, though you must still manage against key/nonce pair reuse.
5. **Encrypt the file with AES-GCM** using the DEK, nonce, and standardized AAD; output includes ciphertext and authentication tag, e.g., 128-bit tag = 16 bytes.
6. **Package the envelope** with version, algorithms, key ID, wrapped key, nonce, ciphertext, tag, and required AAD/metadata; enforce length bounds and parsing policies prior to decryption.

### 4.2. Decryption Flow

```text
                  Recipient
     Pre-validated envelope and metadata
                     |
    Resolve keyId + valid version + algorithm
                     |
      PrivateKey --> RSA-OAEP decrypt(wrappedKey)
                     |           |
                     |        AES data key
                     |           |
              ciphertext, nonce, AAD
                     |           |
              AES-GCM decrypt + verify tag
                     |
           Accept plaintext only after
           authentication tag is valid
```

**Security ordering:** never treat plaintext as trustworthy before the AEAD tag is verified; a file with an invalid tag must be rejected in full. When streaming decryption to disk, consider **writing to an isolated temporary file** and publishing/renaming only after authentication completes, preventing business components from reading unverified bytes.

### 4.3. Actual Size of the Example Envelope

With RSA-2048 OAEP SHA-256 wrapping a **32-byte AES-256 key**, and AES-GCM encrypting exactly **1 MiB of plaintext**:

| Component | Bytes |
| --- | ---: |
| AES data key (exists only in memory, **never** sent in plaintext) | 32 |
| RSA-OAEP `wrappedKey` of the DEK | 256 |
| GCM nonce | 12 |
| Ciphertext data for 1 MiB plaintext | 1,048,576 |
| 128-bit GCM tag | 16 |
| `ciphertext \|\| tag` from `Cipher.doFinal` | **1,048,592** |
| `wrappedKey \|\| nonce \|\| ciphertext \|\| tag` | **1,048,860** |
| Header, key ID, version, lengths, AAD metadata | **Extra depending on format** |

Compared to 1,412,864 bytes when encrypting 1 MiB directly across 5,519 RSA blocks, hybrid encryption has **only 284 bytes of binary overhead in the example before headers**, and needs **only one RSA operation** to wrap the DEK; the bulk data passes through AES-GCM.

Do not mistake the "32-byte AES key" for a field transmitted in plaintext; it sits inside `wrappedKey`. Duplicating or writing the raw DEK into the envelope completely destroys confidentiality.

### 4.4. What Belongs in the Header and AAD

A production-ready envelope is not just concatenating four arbitrary byte arrays. You must define an unambiguous schema, for example:

```text
version
suiteId / asymmetricKeyId / recipientId
wrappedKeyLength + wrappedKey
nonceLength + nonce
ciphertextLength + ciphertext || tag
associatedData (authenticated metadata)
```

- **Byte-boundary formatting:** length-prefixed, TLV, or bounded standardized CBOR/protobuf schemas. Never guess lengths based solely on binary delimiters.
- **AAD (additional authenticated data):** place metadata requiring integrity protection (version, algorithm suite, document ID, tenant/recipient context, or key binding) into AAD under explicit canonical rules. AAD **is authenticated but not encrypted**.
- **Do not trust control data from the envelope:** `suiteId`, `keyId`, lengths, and version are untrusted inputs. The server must enforce an allowlist of algorithms, key scopes, and reasonable sizes; never let an attacker control private-key lookup paths or choose weak algorithms.
- **RSA-OAEP and AES-GCM must work in concert:** once the receiver unwraps the right DEK and supplies the right nonce + AAD, AES-GCM authenticates ciphertext/tag. Any metadata requiring authenticity that sits outside AAD risks being tampered with while GCM still succeeds.
- **Recipient binding:** with multiple recipients, policies and identity/key metadata must be bound appropriately; selected asymmetric keys must be verified beforehand.

## 5. Java 17+: Testing RSA-OAEP Limits and Hybrid Encryption of a 1 MiB File

This is a **standalone, compilable, runnable** Java 17+ program executing both tests:

- Generate RSA-2048 and use OAEP with **explicitly declared SHA-256 hash + MGF1 SHA-256**. Directly encrypting 190 bytes succeeds; 191 bytes is rejected.
- Generate a random AES-256 key, **RSA-OAEP encrypts only the 32-byte DEK**, while AES-GCM encrypts **1,048,576 bytes of data**. Decrypts back, verifies round-trip, and detects ciphertext modification.

The program prints only measurements and boolean conclusions, **without printing secret keys or ciphertexts**. For simplicity, it holds 1 MiB in RAM; this is **not code for multi-GB files or a production envelope format**.

Save the file **HybridCryptoDemo.java**:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.spec.MGF1ParameterSpec;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.IllegalBlockSizeException;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;
import javax.crypto.spec.SecretKeySpec;

public class HybridCryptoDemo {
    static final OAEPParameterSpec OAEP = new OAEPParameterSpec(
            "SHA-256", "MGF1",
            MGF1ParameterSpec.SHA256,
            PSource.PSpecified.DEFAULT);
    static final byte[] AAD =
            "file-envelope:v1".getBytes(StandardCharsets.UTF_8);

    public static void main(String[] args) throws Exception {
        // Recipient: illustrative 2048-bit RSA key pair generation.
        KeyPairGenerator rsaGen = KeyPairGenerator.getInstance("RSA");
        rsaGen.initialize(2048);
        KeyPair receiver = rsaGen.generateKeyPair();

        Cipher rsa = Cipher.getInstance("RSA/ECB/OAEPPadding");
        rsa.init(Cipher.ENCRYPT_MODE, receiver.getPublic(), OAEP);
        byte[] direct = rsa.doFinal(new byte[190]);
        boolean tooLargeRejected = false;
        try {
            rsa.doFinal(new byte[191]);
        } catch (IllegalBlockSizeException expected) {
            tooLargeRejected = true;
        }
        System.out.println("RSA-OAEP 190-byte input -> "
                + direct.length + "-byte ciphertext");
        System.out.println("RSA-OAEP 191-byte input rejected: "
                + tooLargeRejected);

        // Sender: a fresh symmetric key, wrapping only the key with RSA.
        KeyGenerator aesGen = KeyGenerator.getInstance("AES");
        aesGen.init(256);
        SecretKey dataKey = aesGen.generateKey();
        // Re-initialize Cipher after the oversized input test.
        rsa.init(Cipher.ENCRYPT_MODE, receiver.getPublic(), OAEP);
        byte[] wrappedKey = rsa.doFinal(dataKey.getEncoded());

        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);
        byte[] file = new byte[1024 * 1024];
        new SecureRandom().nextBytes(file);

        Cipher gcm = Cipher.getInstance("AES/GCM/NoPadding");
        gcm.init(Cipher.ENCRYPT_MODE, dataKey,
                new GCMParameterSpec(128, nonce));
        gcm.updateAAD(AAD);
        byte[] sealed = gcm.doFinal(file);

        System.out.println("AES key: "
                + dataKey.getEncoded().length + " bytes");
        System.out.println("RSA-wrapped key: "
                + wrappedKey.length + " bytes");
        System.out.println("nonce: " + nonce.length + " bytes");
        System.out.println("file: " + file.length + " bytes");
        System.out.println("AES-GCM ciphertext+tag: "
                + sealed.length + " bytes");
        System.out.println("envelope binary bytes (without header): "
                + (wrappedKey.length + nonce.length + sealed.length));

        // Recipient: unwrap key then verify/decrypt with GCM.
        rsa.init(Cipher.DECRYPT_MODE, receiver.getPrivate(), OAEP);
        byte[] unwrapped = rsa.doFinal(wrappedKey);
        SecretKeySpec recoveredKey = new SecretKeySpec(unwrapped, "AES");

        gcm.init(Cipher.DECRYPT_MODE, recoveredKey,
                new GCMParameterSpec(128, nonce));
        gcm.updateAAD(AAD);
        byte[] restored = gcm.doFinal(sealed);
        System.out.println("round-trip OK: "
                + Arrays.equals(file, restored));

        // If a single ciphertext byte is modified, GCM must reject it.
        byte[] changed = sealed.clone();
        changed[0] ^= 1;
        gcm.init(Cipher.DECRYPT_MODE, recoveredKey,
                new GCMParameterSpec(128, nonce));
        gcm.updateAAD(AAD);
        boolean tamperRejected = false;
        try {
            gcm.doFinal(changed);
        } catch (AEADBadTagException expected) {
            tamperRejected = true;
        }
        System.out.println("tampered ciphertext rejected: "
                + tamperRejected);

        Arrays.fill(unwrapped, (byte) 0);
    }
}
```

Compile and run with Java 17 or higher:

```bash
javac -encoding UTF-8 HybridCryptoDemo.java
java HybridCryptoDemo
```

Expected stdout (lengths do not depend on randomly generated key/nonce bytes; verified with Java):

```text
RSA-OAEP 190-byte input -> 256-byte ciphertext
RSA-OAEP 191-byte input rejected: true
AES key: 32 bytes
RSA-wrapped key: 256 bytes
nonce: 12 bytes
file: 1048576 bytes
AES-GCM ciphertext+tag: 1048592 bytes
envelope binary bytes (without header): 1048860
round-trip OK: true
tampered ciphertext rejected: true
```

### 5.1. Why Are the Results Like This?

1. **190 bytes:** the OAEP SHA-256 formula on RSA-2048 allows up to 190 bytes input; `doFinal(new byte[190])` encrypts into 256 bytes.
2. **191 bytes:** `IllegalBlockSizeException` is thrown on standard JDK providers because the message is too large. The demo catches it as a test; never turn `doFinal` overflow into normal business control flow.
3. **AES-256:** `KeyGenerator.init(256)` takes **bit** length; an exportable secret key in the software demo provider is 32 bytes. Non-exportable HSMs/providers may return `getEncoded() == null`; in production, avoid forcing raw key export when wrap/unwrap/derive APIs can operate inside the HSM.
4. **Wrapped key:** RSA processes only the 32-byte input, staying well below the 190-byte limit; output is 256 bytes.
5. **AES-GCM:** 128-bit tag = 16 bytes. For 1 MiB plaintext, `doFinal` produces 1,048,576 + 16 = **1,048,592 bytes**. The 12-byte nonce is stored separately and is not embedded in `Cipher.doFinal()` output.
6. **Binary total:** 256-byte wrapped key + 12-byte nonce + 1,048,592-byte GCM result = **1,048,860 bytes**, excluding header/schema/key ID.
7. **Authentication:** flipping one byte in the ciphertext causes a tag mismatch, raising `AEADBadTagException` on decryption. Both ciphertext **and AAD** must match what was used during encryption.

### 5.2. Limitations of the Demonstration Program

- It generates a fresh RSA keypair and random file on each run; production must **authenticate the recipient's public key**, manage private keys, and enforce key IDs/rotation.
- It holds the entire 1 MiB file, `sealed`, and `restored` in RAM; **never use this prototype directly for huge files**.
- It does not serialize/parse an envelope, store version/key IDs, or construct AAD from dynamic headers. Real deployments require a canonical format and strict policy.
- It uses a static AAD solely to demonstrate the API; production AAD often must include file and recipient metadata, canonicalized identically on both sides.
- It creates a new DEK on every run; never reuse `(key, nonce)`. **Repeating a nonce under the same GCM key can break confidentiality and integrity**.
- `Arrays.fill(unwrapped, (byte) 0)` zeroes the temporary array on a best-effort basis; it cannot prove every copy inside `SecretKeySpec`, the JVM, or the provider is erased. For high key-protection requirements, consider HSM/KMS and non-exportable keys.
- Even though AES-GCM verifies data under the DEK, the demo **does not verify sender identity** or prove who created the envelope, because anyone with the recipient's public key could generate a new DEK and encrypt a different file. A separate sender authentication layer is needed if business rules require it.

## 6. Handling Truly Large Files: Streaming, Memory, and Tag Verification

Hybrid encryption solves RSA's size limit, yet **"using AES-GCM" does not mean a system can allocate a byte array the size of a multi-GB file**. When files exceed memory, I/O streaming design, per-message length limits, and plaintext release discipline are critical.

### 6.1. Streaming Encryption

Conceptually, the system reads the file via an `InputStream` in small buffers, feeds them into `Cipher.update(...)` or an appropriate stream-encryption mechanism, and writes ciphertext to a temporary/destination file in a versioned framing format. At end-of-stream, it calls `doFinal()` to obtain the final tag and finalize the envelope.

**Never use `new byte[(int)file.length()]`** as the default path for multi-GB files: it can overflow `int` or trigger `OutOfMemoryError`. Bound inputs, use files/streams, separate metadata from ciphertext, and handle I/O errors and cleanup cleanly.

Conceptual structure (**pseudocode**, not runnable Java):

```text
create fresh DEK and unique nonce
wrap DEK with recipient's verified public key
write validated envelope header
initialize AEAD encryptor with DEK, nonce and exact AAD
while input has more bytes:
    read bounded chunk
    encrypt and write bytes (preserve order)
finalize AEAD encryption and append authentication tag
finish/commit envelope only after successful completion
```

Pseudocode does not replace vetted libraries/protocols. For a single very large AES-GCM message, adhere to **message size and key/nonce usage limits** of the standard and provider; beyond those thresholds, design a chunked/record AEAD protocol rather than streaming unboundedly into one GCM invocation.

### 6.2. Streaming Decryption: Never Use Unauthenticated Plaintext

When decrypting AES-GCM, the integrity tag is typically verified completely **only at the end of the message**. A streaming API/provider might emit bytes before final verification or buffer them depending on implementation; **never assume "receiving output bytes means they are authenticated"**.

For large files:

- Write temporary plaintext to an isolated area inaccessible to other applications, with restricted permissions.
- Commit, rename, or distribute plaintext only once the AEAD tag for **the entire message** is valid.
- If the tag fails, delete the temporary output and report a generic error; never allow partial files to be consumed downstream.
- Never ignore exceptions from `Cipher.doFinal()`, and never manually compare only 16 tag bytes while skipping AAD verification.
- With multiple AEAD messages/chunks, **each chunk must be authenticated**, and the whole sequence must bind order, position, file ID, total chunks, and length/end-of-file to prevent reordering, rollback, and truncation.

### 6.3. Proper Chunked Encryption

If an application needs random access or files exceed a single AEAD message limit, use a properly designed and vetted **record/chunk encryption format**:

- Each chunk has a **unique** nonce/sequence under the same key.
- AAD binds **file ID, version, sequence index, total length, or final marker** per design.
- The system verifies **whole-file** integrity and chunk continuity; "each individual chunk has a valid tag" is not enough to prevent dropped or reordered chunks without sequence/finality binding.
- Bound chunks per DEK, total bytes encrypted under a key, and nonce state; comply with algorithm/protocol limits.
- Whenever a supported, vetted authenticated streaming encryption library/protocol exists, prefer it over inventing custom nonce, index, tag, or metadata schemes.

## 7. ECC, ECDH, KEM, and HPKE: Symmetric Algorithms Are Still Needed for Large Payloads

Not every public-key primitive works like RSA encryption. Modern systems also establish shared secrets or encapsulate key material:

| Mechanism | Purpose | Directly encrypts MB/GB files? |
| --- | --- | --- |
| **RSA-OAEP** | Encrypt small secrets/DEKs for a recipient's public key | **Unsuitable**; RSA has `mLen` limits and high cost |
| **ECDH / X25519** | Two parties compute a shared secret from each other's private and public keys | **No**; requires a KDF and AEAD to encrypt data |
| **KEM (key encapsulation mechanism)** | Encapsulate a secret and decapsulate at recipient | **No**; after KEM, typically uses a KDF and AEAD |
| **HPKE (RFC 9180)** | Combines KEM, KDF, and AEAD per standardized suites and modes | **Usable for application encryption via protocol**, though large payloads are still handled by AEAD; must follow suite/context limits |

### 7.1. ECDH Is Not "AES with EC Keys"

ECDH/X25519 lets two parties compute a shared secret via key agreement. **Never use the raw shared secret directly as an AES key by slicing arbitrary bytes**; apply a specified KDF (typically HKDF) with required context to derive keys/nonces, while ensuring public keys, recipient, and protocol are authenticated.

If an ECDH design lacks authentication, **a man-in-the-middle can substitute public keys** and establish separate secrets with each side. Using ECDH does not by itself prove you are talking to the intended recipient.

### 7.2. Hybrid Does Not Mean Both Algorithms Encrypt the Entire File

A KEM + KDF + AEAD model is also hybrid encryption:

```text
KEM.encapsulate(recipientPublicKey) -> encapsulation + sharedSecret
HKDF(sharedSecret, protocolContext) -> AEAD key/nonce material
AEAD.encrypt(file, key, nonce, AAD) -> ciphertext + tag
envelope -> encapsulation + ciphertext + tag + metadata
```

You do not need to "RSA-encrypt(file) then AES-encrypt(file again)" to get two layers. What matters is **authenticating public-key origin, protecting/establishing the DEK, and properly encrypting/authenticating the payload**. The term "hybrid encryption" applies to many algorithm suites; designs must state the exact suite and security goals.

## 8. System Security: What Does Hybrid Solve and What Does It Not Solve?

### 8.1. Data Confidentiality at Rest

If the recipient's public key is trusted and the private key is protected, wrapping the DEK with RSA-OAEP combined with AES-GCM can provide **file confidentiality** when only ciphertexts/envelopes are stored. For real security, never let DEKs leak into logs, unmanaged caches, exceptions, metadata, or plaintext storage.

However, if the RSA private key is compromised, old DEKs wrapped under that key can be unwrapped from stored envelopes. Hence this **does not inherently provide forward secrecy** for stored data. Protocols using ephemeral secrets and proper key erasure offer different properties, which must be analyzed per protocol.

### 8.2. Verifying the Public Key Is Part of Encryption

Using a public key fetched from an attacker-controlled path does not provide confidentiality **for the intended recipient**. You need a trust mechanism: valid certificates, key pinning, authenticated directory, HSM/KMS identity, or protected provisioning.

Never select a key solely by a self-declared `kid` in a file while ignoring tenant/recipient scope; never fetch a URI from an untrusted header to retrieve a public key and treat it as trusted.

### 8.3. AEAD Does Not Automatically Authenticate Sender Identity

An AES-GCM file with a valid tag only proves the file/metadata was not modified relative to the AEAD key used (assuming sound cryptography). In a public-key hybrid model where **anyone** with the recipient's public key can generate a fresh DEK, **a valid ciphertext does not prove who sent it**.

When business rules require sender identity, add separate origin authentication: an authenticated TLS endpoint, a digital signature over the payload/envelope with matching context, or a standardized authenticated messaging protocol. Digital signatures require a matching distribution/trust mechanism for the signer's public key.

### 8.4. Security Level Does Not Mechanically Equal the AES Key Size

An RSA-2048 + AES-256 pairing can be **weaker than 256-bit security** due to RSA-2048's classical security level and private-key management risks. Overall system security depends on the weakest link: algorithm strength, key lengths, key distribution, AEAD nonces, lifecycle, software bugs, authorization, and threat model. Never pick "AES-256" and assume everything achieves 256-bit security.

### 8.5. When There Are Multiple Recipients

To send **the same file** to multiple recipients, you can typically encrypt the payload **once** with a single DEK and **wrap the DEK separately** under each recipient's public key:

```text
file --AEAD(DEK)--> ciphertext+tag
             DEK --recipient A public key--> wrappedKeyA
             DEK --recipient B public key--> wrappedKeyB
             DEK --recipient C public key--> wrappedKeyC
```

This avoids re-encrypting the large payload with RSA for each recipient; overhead grows mainly with the number of wrapped keys. However, you must bind recipients/key IDs and metadata in the envelope design and account for recipient revocation. Anyone who already obtained the DEK or plaintext **cannot have access to their existing copy revoked merely by removing their entry**.

## 9. Java System Design: API Boundaries, Tool Selection, and Operations

### 9.1. Assigning APIs by Role

- **RSA:** `Cipher.getInstance("RSA/ECB/OAEPPadding")`, `OAEPParameterSpec`, and public/private keys from managed keystores/KMS. For random 16/32-byte DEKs, RSA-OAEP is far better suited than bulk data encryption.
- **AES-GCM:** `Cipher.getInstance("AES/GCM/NoPadding")`, `GCMParameterSpec`, random keys, and unique nonces; verify the AEAD tag on decryption.
- **Key generator:** `KeyGenerator.getInstance("AES")` with policy-supported bit lengths; `SecureRandom` for nonces and other random bytes as needed.
- **Key management:** private keys belong in an access-controlled keystore/HSM/KMS/secret manager; applications do not need to export private keys if the provider executes required operations directly.
- **Key rotation:** envelopes need key IDs and versions to unwrap DEKs with the right private key; files that must remain readable need an appropriate old-key retention or rewrap strategy.

Never store the RSA private key next to ciphertexts in a public directory. If both private keys and data are exposed, asymmetric protection is lost. When backup/restore is needed, maintain policies to retain and protect old keys long enough to recover documents.

### 9.2. RSA/KMS Cost Still Exists, But Only on Small Data

Hybrid encryption does not eliminate RSA cost completely; it reduces public-key operations from **thousands per file** down to **one or a few DEK wrap/unwrap operations** depending on recipient count. When using HSM/KMS, you must still consider latency, API quotas, failover, auditing, and caching policies—just without calling RSA on every 190 bytes of a file.

In architectures where a KMS supports symmetric data-key/envelope encryption, you can use the service's generate-DEK and wrap-DEK capabilities instead of running RSA yourself. The "envelope" model **does not mandate RSA**; KMS symmetric wrapping or appropriate KEMs can also fit depending on architecture.

### 9.3. Large Files, API Responses, and Errors

- Enforce **request/file size limits**, valid formats, and per-field length caps on the envelope before allocating memory.
- Never let differing RSA/OAEP/GCM errors create an oracle leaking secret details via responses, logs, or timing.
- With GCM, a tag error must be treated as **file authentication failure**; never use partially emitted plaintext.
- Separate key-encryption/wrapping keys from data-encryption keys to simplify **DEK rewrapping during rotation** instead of always decrypting/re-encrypting entire files, where policy and format allow.
- Store algorithm version, key ID, suite, and metadata in a validated structure rather than relying on arbitrary transformation strings supplied by clients.
- When random-access updates or partial file downloads are needed, design a dedicated authenticated chunking format; **never slice a GCM tag and try to verify parts manually**.

## 10. Common Mistakes

| Flawed assumption or practice | Problem | Right approach |
| --- | --- | --- |
| "RSA-2048 encrypts 2,048 bits of plaintext." | Modulus length is not allowed payload length | Use the OAEP formula `k - 2*hLen - 2` |
| "If it doesn't fit, split the file into RSA chunks." | CPU/size overhead and lacks whole-file authentication | Wrap a small DEK with RSA; encrypt file with AEAD |
| "Pick RSA-4096 to encrypt a 1 GB file directly." | Still only a few hundred bytes per operation | Choose hybrid/envelope or a proper file-encryption protocol |
| "RSA encryption with a public key proves the sender." | Anyone with the public key can encrypt | Use digital signatures or an authenticated channel for sender |
| "RSA signature with a private key is encryption." | Signatures do not keep plaintext confidential | Distinguish digital signatures from encryption |
| "An EC public key can go straight into an AES Cipher." | ECDH does not directly encrypt payloads | Standard key agreement/KEM + KDF + AEAD |
| "Use RSA/NoPadding to remove the size limit." | Raw RSA is insecure | Use standard padding schemes and hybrid encryption |
| "Use RSA/PKCS1Padding because max plaintext is longer." | Legacy/padding-oracle risks | Prefer properly parameterized RSA-OAEP for new designs |
| "`OAEPWithSHA-256` means MGF1 matches across all providers." | Parameter mismatch and interop bugs | Explicit `OAEPParameterSpec` for digest, MGF1, and label |
| "A GCM nonce just needs to be 12 bytes." | Reusing nonces under the same key is catastrophic | Design and enforce **nonce uniqueness** |
| "GCM returning plaintext means it is verified." | Data may be consumed before tag verification | Commit only after full AEAD verification |
| "Headers/key IDs don't need MACs because they are metadata." | Context or key lookup can be tampered with | Bind AAD/metadata and validate key scope/version |
| "AES-256 makes RSA-2048 256-bit strong." | System security depends on the whole chain, not just DEK | Evaluate public-key strength, policy, and lifecycle |
| "Once a file is encrypted, key rotation is done." | Old private keys are still needed to unwrap old DEKs | Maintain key versioning/rewrap/retention policies |
| "Just check the tag on each chunk independently." | Chunks can be reordered, truncated, or substituted | Bind sequence, length, file ID, and finalization in authenticated structure |

## 11. Checklist Before Implementing Bulk Encryption

1. **Goal:** against whom must data stay confidential? Who are the recipients, and must sender identity be authenticated?
2. **Key trust:** do public keys come from a verified source? Are private keys stored in a securely managed boundary?
3. **Algorithms:** have you chosen an explicit suite for key encapsulation/wrapping + AEAD? Have you avoided raw RSA/legacy padding?
4. **RSA capacity:** if using RSA-OAEP, are only small key materials fed to RSA and is `mLen <= k - 2*hLen - 2` verified?
5. **Data keys:** does each file/envelope use an appropriate random DEK? Is logging or transmitting plaintext DEKs prevented?
6. **AEAD nonce/tag:** unique nonce per key; standard tag length; exact-byte AAD/metadata authenticated?
7. **Envelope:** do version/key ID/lengths/algorithm suite have a size-bounded parser preventing ambiguity and ensuring integrity?
8. **Large files:** using proper authenticated streaming/chunking, avoiding loading entire files into RAM, never releasing plaintext before tag validation?
9. **Operations:** are rotation, rewrap, backup/recovery, revocation, auditing, KMS quotas, and safe error handling in place?
10. **Testing:** tested valid/wrong public keys, wrong OAEP params, modified ciphertext/tag bytes, differing nonces, differing AAD, missing/truncated chunks, large files, and multiple recipients?

## 12. Self-Check Exercises

**Question 1.** How many plaintext bytes does RSA-2048 + OAEP SHA-256 allow in a single RSA operation?  
**Answer:** **190 bytes** because `256 - 2*32 - 2 = 190`; ciphertext is **256 bytes** long.

**Question 2.** Someone wants RSA-OAEP to encrypt a 500-character Unicode string in one shot thinking "500 characters is small." Is this valid?  
**Answer:** **No.** You must count **bytes after UTF-8 encoding** and apply the modulus/padding formula; RSA-2048 OAEP SHA-256 allows at most 190 **bytes**, and even a few dozen multi-byte Unicode characters can take many bytes.

**Question 3.** For a 1 MiB file split into 190-byte blocks and RSA-2048-encrypted per block, how many ciphertext bytes result?  
**Answer:** `ceil(1,048,576/190) = 5,519` blocks × 256 bytes each = **1,412,864 bytes**, excluding metadata.

**Question 4.** With RSA-2048 wrapping an AES-256 key, AES-GCM encrypting a 1 MiB file, a 16-byte tag, and a 12-byte nonce, what is the minimum byte count for `wrappedKey + nonce + ciphertext + tag`?  
**Answer:** **256 + 12 + 1,048,576 + 16 = 1,048,860 bytes**, excluding headers.

**Question 5.** A file is encrypted with AES-GCM under a DEK wrapped with Bob's public key. Does that prove Alice is the sender?  
**Answer:** **No.** Anyone with Bob's public key can create their own DEK and encrypt a file. Sender authentication requires a dedicated mechanism.

**Question 6.** Can the nonce and GCM tag be stored alongside the ciphertext?  
**Answer:** **Yes**; nonces and tags do not need to be secret. However, the nonce must be unique under the same key, and the tag and metadata must be properly processed/verified.

**Question 7.** If streaming decryption emits some plaintext before verifying the final tag, can another program use that plaintext immediately?  
**Answer:** **It should not.** Keep it isolated/unreleased until the entire message tag verifies, or use a proper authenticated chunking protocol.

**Question 8.** Is increasing the RSA modulus from 2,048 to 4,096 bits the main optimization for encrypting a 5 GB file?  
**Answer:** **No.** That only adds a couple hundred bytes per RSA-OAEP operation while increasing computational cost; use hybrid encryption.

**Question 9.** Why is hybrid encryption efficient when encrypting one file with one DEK and wrapping that DEK for multiple recipients?  
**Answer:** The payload is symmetrically encrypted **once**; only wrapping the small DEK is repeated per recipient. You must still protect metadata and recognize that anyone who already received the DEK can keep their own copy.

**Question 10.** If RSA unwraps the key successfully yet the GCM tag is invalid, should you accept partial data because "RSA already verified the key"?  
**Answer:** **No.** Successful RSA unwrap does not replace AEAD integrity. Treat the file as invalid and never release plaintext.

### Key Takeaway

**Asymmetric encryption does not replace bulk data encryption.** RSA-OAEP has modulus- and padding-bounded plaintext limits, high computational cost, and provides no file-level authentication across ad-hoc chunks. The right design is **public-key/KEM to protect or establish a small DEK + symmetric AEAD to encrypt the large payload**, paired with public-key verification, proper nonce/AAD handling, clean envelope formatting, safe streaming, and sound key lifecycle management.