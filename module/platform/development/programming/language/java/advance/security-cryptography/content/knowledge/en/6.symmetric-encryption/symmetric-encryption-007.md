# 6.7 `GCMParameterSpec`, Tag Length, and the Non-Repeating IV Requirement Under the Same Key

In Java, when using `Cipher.getInstance("AES/GCM/NoPadding")`, you must understand the two parameters represented by `GCMParameterSpec`: the **IV/nonce** for the encryption invocation and the **authentication tag length** used to verify result integrity/authenticity. A syntactically valid API call can still produce an insecure system if **an IV is reused with the same AES key**.

After this lesson, you will be able to:
- Explain the AES-GCM mechanism and the roles of IV/nonce, tag, and AAD.
- Distinguish **tag length in bits** from **IV length in bytes** in `GCMParameterSpec`.
- Choose an appropriate tag length, understanding NIST standard bounds and Java provider constraints.
- Generate, store, and recover an IV for each ciphertext; enforce the **never repeat `(key, IV)`** rule across multiple encryptions, processes, and nodes.
- Write Java 17+ encryption/decryption with `GCMParameterSpec`, handle `AEADBadTagException`, and verify results against a test vector.

## 1. What Is GCM and the Four Data Items to Distinguish

**GCM (Galois/Counter Mode)** is an authenticated symmetric encryption mode (**AEAD**, Authenticated Encryption with Associated Data). The output consists of the encrypted data (**ciphertext**) and an **authentication tag**. On decryption, the tag is verified to detect modifications to ciphertext, AAD, or mismatched cryptographic parameters. Never accept plaintext if verification fails.

| Component | Role | Must Be Kept Secret? | On Decryption |
| --- | --- | --- | --- |
| **AES key** (`SecretKey`) | Secret key used to encrypt and compute the tag. | **Yes.** | Must use the exact key. Manage in a keystore/KMS or appropriate secrets manager. |
| **IV/nonce** | Identifies one encryption under a specific key; feeds GCM state calculation. | **No** in standard AES-GCM. | Must supply the **exact IV** used during encryption. |
| **Plaintext / ciphertext** | Confidential data and its encrypted form. | Plaintext must be protected; ciphertext can be stored/transmitted. | Use plaintext only after authentication succeeds. |
| **Authentication tag** (`T`) | Integrity/authenticity check value, usually appended to ciphertext. | Not a secret key. | Missing or invalid tag must cause decryption to fail. |
| **AAD** (Additional Authenticated Data) | Metadata that is **authenticated but not encrypted**. | Not by default. | Must supply the exact AAD bytes used during encryption. |

The terms IV and nonce refer to the same parameter in this AES-GCM context: **there is no need to create two separate arrays** just because documentation uses both names. The IV is non-secret yet carries a **per-key uniqueness** requirement.

Diagram of a single record:

~~~text
Key K (secret) ─────────────────────────┐
IV N (fresh for K) ─────────────────────┤
AAD (authenticated metadata) ───────────┤ AES-GCM encrypt
Plaintext P ────────────────────────────┘
                                          |
                                          v
                     Ciphertext C + authentication tag T

Store/transmit: {version, keyId, N, C, T, AAD/context}
Decrypt: obtain exact K, N, AAD, C, and T -> verify tag -> plaintext
~~~

**AAD is not ciphertext**, so do not expect AAD to be encrypted. For instance, you can put `recordType` or `tenantId` in AAD when you want to detect metadata tampering. If a system encrypts content for tenant A but omits tenant identification from AAD/context, the ciphertext may be transplanted into the wrong context.

## 2. What Does `GCMParameterSpec` Actually Hold?

The `javax.crypto.spec.GCMParameterSpec` class implements `AlgorithmParameterSpec` and stores **two values**:

- `tLen`: **authentication tag** length, in **bits**.
- `IV`: byte sequence of the initialization vector, stored as a byte array whose length is given by `iv.length`.

Key APIs:

~~~java
// 12-byte IV; 128-bit (16-byte) tag:
byte[] iv = new byte[12]; // ONLY an example of length; never use an all-zero IV for real encryption!
GCMParameterSpec spec = new GCMParameterSpec(128, iv);

// Read parameters:
int tagBits = spec.getTLen();   // 128
byte[] ivCopy = spec.getIV();   // new array, 12 bytes long
~~~

This is an **API illustration snippet**, not a standalone encryption program. The complete runnable program using a safe IV is in Section 6.

Two primary constructors:

| API | Meaning |
| --- | --- |
| `new GCMParameterSpec(int tLen, byte[] src)` | Copies the entire `src` as the IV and stores the tag length in **bits**. |
| `new GCMParameterSpec(int tLen, byte[] src, int offset, int len)` | Copies `len` bytes starting at `offset` from `src` as the IV; does not pick a random IV itself. |
| `spec.getTLen()` | Returns the tag length in **bits**, not bytes. |
| `spec.getIV()` | Returns a **fresh array** on each call; mutating the returned array does not alter the IV stored in the spec. |

The constructor copies the IV array so callers mutating the source array cannot silently alter the parameters. However, `GCMParameterSpec` **does not generate IVs**, **does not track IV history**, and **does not guarantee IV uniqueness under the same key**. Safe IV allocation is the responsibility of the program/protocol.

**Do not mix up units:**

~~~text
int IV_BYTES = 12;       // 12 bytes = 96 bits (common IV length)
int TAG_BITS = 128;      // 128 bits = 16 bytes (common tag length)

new GCMParameterSpec(TAG_BITS, iv);   // RIGHT if iv is 12 bytes
new GCMParameterSpec(16, iv);         // WRONG semantics: 16 bits, not 16 bytes
new GCMParameterSpec(IV_BYTES, iv);   // WRONG semantics: passing 12 as tag length
~~~

The Java API performs only basic parameter sanity checks when constructing `GCMParameterSpec`. **The provider executing `Cipher.init` decides whether the specific tag/IV values are supported.** Therefore, never treat successful constructor execution as proof of a valid, secure GCM configuration.

## 3. Authentication Tag Length: What Does 128 Bits Mean?

GCM produces an authentication tag `T`, commonly chosen as **128 bits (16 bytes)**. The tag lets the decryptor detect tampered ciphertext, altered AAD metadata, or mismatched key/IV, with forgery success probability depending on both tag length and GCM usage limits.

Per NIST SP 800-38D, standard tag lengths are **128, 120, 112, 104, or 96 bits**. **64 or 32 bits** are permitted only in specialized applications with strict constraints on data length, message count, and key lifetime; never choose them for general systems.

| `tLen` (bits) | Tag Length (bytes) | Guidance |
| --- | --- | --- |
| **128** | **16** | Preferred practical choice in examples and most new applications. |
| 120 | 15 | Standard GCM length, but verify provider/protocol support and interoperability needs. |
| 112 | 14 | Same; shorter tags require analyzing security bounds. |
| 104 | 13 | Same; do not arbitrarily shorten to save a few bytes. |
| 96 | 12 | Standard, lower authentication assurance than a 128-bit tag; use only when mandated by protocol with bounds evaluated. |
| 64 or 32 | 8 or 4 | **Special NIST cases** with strict limits; avoid unless formally designed and approved. |

Notes:
1. `tLen` specifies the **tag**, not the AES key bit length. The key may be AES-128/192/256; `GCMParameterSpec(128, iv)` does not set key length.
2. A 128-bit tag **does not mean** a 128-bit IV. The common pairing is a **96-bit (12-byte) IV** + **128-bit (16-byte) tag**.
3. **Shorter tags increase forgery odds under repeated attacker attempts**, and safety/data-volume bounds become tighter. Never shorten the tag just to squeeze into a small payload without changing the protocol.
4. NIST requires a fixed, supported tag length bound to a key in a GCM configuration; never vary tag length arbitrarily across messages under the same key.
5. Not every Java provider supports every standard `tLen`. When `Cipher.init` encounters an unsupported value, it may throw `InvalidAlgorithmParameterException`. The examples below intentionally use 128 bits to avoid unnecessary differences.
6. Never pass `256` as tag length thinking it gives "double security": standard GCM has no 256-bit tag.

### Where Does the Tag Appear in Java?

With `Cipher.getInstance("AES/GCM/NoPadding")` and `TAG_BITS=128`, Java's `doFinal(plaintext)` returns **ciphertext with the tag appended**, conceptually represented as:

~~~text
ciphertextAndTag = ciphertext || tag
len(ciphertextAndTag) = len(plaintext) + 16 bytes

Example 8-byte plaintext:
  8 bytes ciphertext + 16 bytes tag = 24 bytes ciphertextAndTag

If envelope includes 12-byte IV:
  IV(12) || ciphertextAndTag(24) = 36 bytes
~~~

`NoPadding` is the proper transformation name for GCM—it **does not mean GCM omits the authentication tag**. The tag sits inside the `doFinal` output, not inside `GCMParameterSpec`. `GCMParameterSpec` holds only the **expected parameters** (`tLen` and `IV`), not the generated tag.

If interoperating with a library/protocol that stores ciphertext and tag in separate fields, explicitly define **tag length in bytes**, split/join them in the exact order, and use a versioned format. Never confuse the 16-byte tag with the 12-byte IV.

## 4. The Cardinal Rule: Never Repeat an IV Under the Same Key

**AES-GCM invariant: for each key K, every encryption must use an IV/nonce N never previously used with K.** In other words, the pair **(K, N)** must be unique across the entire encryption lifecycle of that key.

### 4.1. What Happens If It Is Reused?

GCM combines counter-based encryption with authentication tag calculation. If the same `K` and `N` are used for two different plaintexts, the keystream repeats. At matching byte positions, the relationship is:

~~~text
C1 = P1 XOR stream(K, N)
C2 = P2 XOR stream(K, N)

C1 XOR C2 = P1 XOR P2   (at overlapping positions)
~~~

An attacker can deduce relationships between plaintexts and exploit authentication weaknesses; **reusing an IV also leads to tag forgery risks**, not just confidentiality leakage. This cannot be "fixed" by using a 128-bit tag, adding AAD, or changing plaintext. Once the same `(K, N)` has been used for encryption, the design's security guarantees are violated.

**Distinguish these cases:**

| Case | Valid Under the IV Rule? |
| --- | --- |
| Same key, **fresh IV** per encryption | Can be valid, if non-repetition is truly ensured and other GCM conditions are met. |
| Same key, same IV for **two different encryptions** | **Invalid**, even if plaintext/AAD differ. |
| Same key, same IV used to **decrypt the ciphertext just created** | **Required**, since decryption must use the ciphertext's exact IV; this is not another encryption. |
| Rotating to a new key, IV matches a value used with the old key | Uniqueness applies per `(key, IV)` pair; manage keys properly and never assume a key change succeeded without verifying. |
| Two nodes sharing K pick the same N | **Invalid**, even across different nodes and JVMs. |
| Restart resets nonce counter to 0 while reusing the same key | **Invalid**. |
| Creating `new GCMParameterSpec(128, oldIV)` for a new encryption | Still **invalid** if `oldIV` was already used under that key; a new spec object does not make the IV fresh. |

### 4.2. Why Is a 96-Bit (12-Byte) IV Usually Chosen?

GCM processes a **96-bit** IV via a simple, efficient path: the initial counter value is formed by concatenating the IV with a specification-defined constant suffix. When an IV length differs from 96 bits, GCM must process the IV through GHASH before building the counter state; some providers may support other lengths, yet arbitrary lengths should not be treated as default configuration.

96 bits here is the **IV length**, not the tag length. For example, using a **12-byte nonce and 16-byte tag** has no contradiction.

The IV need not be secret. It can be stored publicly right before the ciphertext; however, the exact IV must be supplied during decryption, and **never reused for a new encryption under the same key**.

### 4.3. Random IV Generation Is Not an Absolute Guarantee

For each encryption, 12 bytes can be generated via `SecureRandom.nextBytes`:

~~~java
byte[] iv = new byte[12];
new java.security.SecureRandom().nextBytes(iv);
GCMParameterSpec spec = new GCMParameterSpec(128, iv);
~~~

This is an **illustrative snippet**; in practice, manage the CSPRNG instance and key lifecycle by design. A CSPRNG produces unpredictable bytes; with random IVs, **collision probability is tiny yet non-zero**. In a 96-bit space, collision risk grows over many invocations via the birthday effect (roughly proportional to the square of invocation count). NIST defines invocation limits under a single key and corresponding IV construction rules.

For low-volume systems with proper key rotation policies, random 96-bit IVs are a common choice. For multi-node, high-volume systems, or where **non-collision guarantees stronger than probability** are needed, use a stateful/counter-based nonce allocation design with proper partitioning.

Never invent an infinite "safe" threshold for `SecureRandom`. Actual limits must be grounded in the GCM specification, risk tolerance, data sizes, ciphertext count, architecture, and key management policy.

### 4.4. Counter Nonces Work, But Require System-Wide Management

Another strategy allocates each encryption a **unique value** from a counter or partitioned nonce space:

~~~text
96-bit IV = per-key/node prefix || monotonically increasing counter

Node A -> prefixA || 000001, prefixA || 000002, ...
Node B -> prefixB || 000001, prefixB || 000002, ...
                   ^ prefixA differs from prefixB and is uniquely allocated
~~~

This diagram only illustrates the concept—**it does not prescribe a universal bit split for all systems**. True safety requires defining:

- Who assigns prefixes/namespaces and how two nodes are prevented from receiving the same prefix.
- How counter state is **durably persisted** so it never repeats after crashes, backup restores, scale-outs, or deployment rollbacks.
- How concurrent threads/requests are synchronized so no IV is ever issued twice.
- The maximum counter bound and key rotation before counter wraparound.
- Key lifecycle, version/key ID, and rotation mechanisms coordinated with IV generation.
- Protocol/standard policy: never mix random and deterministic IV constructions under the same key unless formally specified and evaluated.

**Never use a raw timestamp as an IV assuming time always moves forward**: clock resolution, clock skew/adjustments, multiple nodes, and restarts can cause collisions.

### 4.5. `Cipher` Does Not Replace System-Wide Uniqueness Management

Some providers detect if the **same `Cipher` instance** is re-initialized for encryption with the exact `(key, IV)` pair just used. That is not a system-wide anti-reuse mechanism. A new `Cipher` instance, new JVM, or another node has no global registry of every IV ever used with a key. **Never rely on a provider exception as your last line of defense.**

## 5. Correct Lifecycle of an AES-GCM Encryption/Decryption

### 5.1. Encryption

1. Retrieve the right AES key `K` (and key-usage authorization) from the key management system.
2. Allocate a **fresh IV for K** using the chosen strategy; e.g., 12 bytes from CSPRNG within designed load limits.
3. Create `GCMParameterSpec(128, iv)`; obtain `Cipher.getInstance("AES/GCM/NoPadding")`.
4. Call `cipher.init(Cipher.ENCRYPT_MODE, key, spec)`.
5. If AAD exists, call `cipher.updateAAD(aad)` **before** any `update(...)` or `doFinal(...)` calls processing plaintext.
6. Call `doFinal(plaintext)` to obtain ciphertext and tag; store/transmit along with IV, version, key ID, and protocol-defined AAD/context.

### 5.2. Decryption

1. Validate version, minimum length, IV length, and tag length per the **agreed format**; never let an attacker choose an arbitrary tag length.
2. Resolve the right key K using a trusted key ID/version; read the IV accompanying the ciphertext.
3. Call `cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, iv))`.
4. Supply the **exact same AAD bytes** (if any) before processing ciphertext.
5. Call `doFinal(ciphertextAndTag)`: if verification fails, handle `AEADBadTagException` and **reject the data**. Never use unauthenticated plaintext.

**Do not generate a new IV on decryption.** A new IV is only for **new encryptions** under the same key; decryption must use the saved IV from the original ciphertext.

### 5.3. AAD and API Call Ordering

`updateAAD` is for metadata requiring authentication without hiding it. For example, when encrypting data belonging to `"record:v1"`, you must supply the exact bytes `"record:v1"` on decryption; supplying `"record:v2"` fails tag verification. In Java JCE, all GCM AAD must be fed **before processing payload data** via `update`/`doFinal`.

GCM authenticates data **after receiving full input and tag**. When using streaming modes or providers that emit intermediate output before verification, applications must never execute, display, or propagate unauthenticated plaintext; accept it only after `doFinal` succeeds.

## 6. Java 17+: Complete Encrypt/Decrypt Program

The example generates an AES-128 key in memory only, uses a fresh 12-byte IV and 128-bit tag, and stores the envelope as `IV || ciphertext || tag`. The program uses `"xin chao"` (8 UTF-8 bytes) so length results stay fixed even though the IV is randomized each run.

**File: `GcmRecordDemo.java`**

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class GcmRecordDemo {
    static final int IV_BYTES = 12;
    static final int TAG_BITS = 128;
    static final int TAG_BYTES = TAG_BITS / 8;
    static final SecureRandom RNG = new SecureRandom();

    static byte[] seal(SecretKey key, byte[] plaintext, byte[] aad)
            throws GeneralSecurityException {
        byte[] iv = new byte[IV_BYTES];
        RNG.nextBytes(iv);

        Cipher enc = Cipher.getInstance("AES/GCM/NoPadding");
        enc.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
        enc.updateAAD(aad);
        byte[] ciphertextAndTag = enc.doFinal(plaintext);

        return ByteBuffer.allocate(iv.length + ciphertextAndTag.length)
                .put(iv).put(ciphertextAndTag).array();
    }

    static byte[] open(SecretKey key, byte[] envelope, byte[] aad)
            throws GeneralSecurityException {
        if (envelope.length < IV_BYTES + TAG_BYTES) {
            throw new IllegalArgumentException("Envelope too short");
        }

        byte[] iv = Arrays.copyOfRange(envelope, 0, IV_BYTES);
        byte[] ciphertextAndTag = Arrays.copyOfRange(
                envelope, IV_BYTES, envelope.length);

        Cipher dec = Cipher.getInstance("AES/GCM/NoPadding");
        dec.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
        dec.updateAAD(aad);
        return dec.doFinal(ciphertextAndTag);
    }

    public static void main(String[] args) throws GeneralSecurityException {
        KeyGenerator keys = KeyGenerator.getInstance("AES");
        keys.init(128);
        SecretKey key = keys.generateKey();

        byte[] message = "xin chao".getBytes(StandardCharsets.UTF_8);
        byte[] aad = "record:v1".getBytes(StandardCharsets.UTF_8);
        byte[] envelope = seal(key, message, aad);

        System.out.println("Tag bits: " + TAG_BITS);
        System.out.println("IV bytes: " + IV_BYTES);
        System.out.println("Envelope bytes: " + envelope.length);
        System.out.println("Recovered: " + new String(
                open(key, envelope, aad), StandardCharsets.UTF_8));

        byte[] tampered = envelope.clone();
        tampered[tampered.length - 1] ^= 1;
        try {
            open(key, tampered, aad);
            throw new AssertionError("Tampered record was accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("Tampered record rejected: true");
        }

        try {
            open(key, envelope, "record:v2".getBytes(StandardCharsets.UTF_8));
            throw new AssertionError("Wrong AAD was accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("Wrong AAD rejected: true");
        }
    }
}
~~~

Run with Java 17+ in the folder containing the file:

~~~bash
javac GcmRecordDemo.java
java GcmRecordDemo
~~~

Verified stdout (no random IV printed):

~~~text
Tag bits: 128
IV bytes: 12
Envelope bytes: 36
Recovered: xin chao
Tampered record rejected: true
Wrong AAD rejected: true
~~~

**Part-by-part explanation:**

- `keys.init(128)` sets the **128-bit** AES key size; `TAG_BITS=128` sets the **128-bit tag length**; `IV_BYTES=12` sets the **96-bit IV**. These three parameters serve distinct roles.
- `seal` always generates a fresh IV before each encryption. Never use a fixed global IV variable or `new byte[12]` as a real IV.
- `enc.updateAAD(aad)` authenticates unencrypted metadata. `enc.doFinal(message)` returns **8 bytes ciphertext + 16 bytes tag = 24 bytes**. The envelope prepends **12 bytes IV**, totaling **36 bytes**.
- `open` reads the IV from the envelope; it does not generate a new IV. It also checks the minimum length of 12 + 16 bytes before slicing arrays.
- Flipping one bit at the end of the envelope (inside the tag) triggers `AEADBadTagException`; mismatched AAD is also rejected. That is the intended behavior; never handle the exception by returning unauthenticated data.
- This is a **single-process API example**, lacking ciphertext count limits, rotation, key IDs, or cross-node nonce coordination. Do not deploy it verbatim as a large-scale multi-node encryption service.

Each call to `seal` creates a fresh `Cipher`. `Cipher` is stateful and must not be shared across threads for concurrent encrypt/decrypt calls. `SecureRandom` can be managed as a shared CSPRNG per API contract; system-wide nonce safety must still be guaranteed by the application.

## 7. Java 17+: Verifying Tag, IV Copying, and Fixed Test Vector

The second example **is strictly for testing**, using an all-zero AES-128 key, all-zero 96-bit IV, and all-zero 16-byte plaintext. This is a **known-answer test vector** used in AES-GCM specifications/tests; **never use this fixed key/IV to encrypt real data**.

The test demonstrates:
- `getTLen()` returns **bits**, whereas the extracted IV is a **byte array**.
- Both the constructor and `getIV()` copy the IV to prevent silent mutation.
- With 16-byte plaintext, `doFinal` returns 16 bytes ciphertext + 16 bytes tag = 32 bytes.
- Ciphertext and tag match expected standard values.

**File: `GcmKnownAnswerDemo.java`**

~~~java
import java.security.GeneralSecurityException;
import java.util.Arrays;
import java.util.HexFormat;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class GcmKnownAnswerDemo {
    public static void main(String[] args) throws GeneralSecurityException {
        byte[] key = new byte[16];
        byte[] iv = new byte[12];
        byte[] plaintext = new byte[16];

        GCMParameterSpec params = new GCMParameterSpec(128, iv);
        iv[0] = 1; // Source array changes; IV inside params stays unchanged.
        byte[] ivCopy = params.getIV();
        ivCopy[1] = 1; // Returned array changes; params still retains original IV.

        System.out.println("IV is copied: "
                + Arrays.equals(params.getIV(), new byte[12]));
        System.out.println("Tag bits: " + params.getTLen());
        System.out.println("Tag bytes: " + params.getTLen() / 8);

        Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
        encrypt.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(key, "AES"), params);
        byte[] ciphertextAndTag = encrypt.doFinal(plaintext);

        String expected = "0388dace60b6a392f328c2b971b2fe78"
                        + "ab6e47d42cec13bdf53a67b21257bddf";
        System.out.println("Ciphertext+tag bytes: " + ciphertextAndTag.length);
        System.out.println("Known vector matches: " + expected.equals(
                HexFormat.of().formatHex(ciphertextAndTag)));

        Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
        decrypt.init(Cipher.DECRYPT_MODE,
                new SecretKeySpec(key, "AES"), params);
        System.out.println("Recovered zero block: "
                + Arrays.equals(plaintext, decrypt.doFinal(ciphertextAndTag)));
    }
}
~~~

~~~bash
javac GcmKnownAnswerDemo.java
java GcmKnownAnswerDemo
~~~

Stdout:

~~~text
IV is copied: true
Tag bits: 128
Tag bytes: 16
Ciphertext+tag bytes: 32
Known vector matches: true
Recovered zero block: true
~~~

Be careful not to copy the `new byte[12]` fixed-IV idea from a **test vector** into production. The program above **encrypts only once with a test key/IV**, then decrypts that ciphertext with the exact same parameters.

## 8. Designing Ciphertext Formats and Key/IV Management

Real systems generally need a **versioned envelope** to identify supported parameters. Example logical format:

~~~text
Record {
  version: 1,
  algorithm: "AES/GCM/NoPadding",    // fixed by version
  keyId: "key-2026-10",             // resolves exact key in KMS
  tagBits: 128,                    // fixed/checked by version
  iv: 12-byte nonce,
  aadContext: metadata bound to record,
  ciphertextAndTag: ciphertext || 16-byte authentication tag
}
~~~

This is a design model, **not JSON containing a key**; `keyId` is merely an identifier. If encoding bytes as Base64URL/hex, decode and validate exact byte lengths. Never trust sender-supplied policy overrides such as `tagBits=32` to bypass rules; valid parameters must come from the chosen format/protocol. Values like `keyId` and metadata should be properly bound/authenticated, e.g., inside the record's AAD.

If using `Cipher.init(Cipher.ENCRYPT_MODE, key)` and **letting the provider auto-generate an IV**, you must still retrieve the IV after `init` (e.g., via `cipher.getIV()` or `cipher.getParameters().getParameterSpec(GCMParameterSpec.class)` if supported), verify its length/tag per protocol, and persist it with the output. Never assume decryption infers the IV from ciphertext or that Java automatically saves nonces to disk.

Production systems should include:

1. **Key ID and rotation:** know which key encrypted a ciphertext; manage keys before and after rotation.
2. **IV/nonce allocation rules:** issue fresh, non-repeating IVs per key, safe across restarts/rollbacks/multi-node setups.
3. **Per-key usage limits:** encryption count, data size, tag length, algorithm, and NIST/protocol limits.
4. **Metadata and AAD:** context-relevant fields (tenant, record type, version, access scope) authenticated consistently.
5. **Input validation:** enforce size limits before allocating memory, validate IV/tag and version; prevent malformed input from exhausting memory.
6. **Error handling:** log safe metadata about record/error type; never log keys, sensitive plaintext, or treat forged ciphertexts as decrypted.
7. **Business-level rollback/replay protection:** AEAD authenticates a ciphertext yet **does not prevent replaying an older valid ciphertext**. When freshness/version ordering is needed, enforce state/version/sequence checks at the application layer.

## 9. Common Mistakes

| Mistake | Consequence / Cause | Correct Approach |
| --- | --- | --- |
| `new GCMParameterSpec(16, iv)` aiming for a 16-byte tag | `tLen` is in **bits**; passing 16 may be rejected by the provider and weakens security. | `new GCMParameterSpec(128, iv)`. |
| Assuming a 12-byte IV means a 12-byte tag | The two parameters are independent. | 12-byte IV with 16-byte tag is the standard configuration. |
| `new GCMParameterSpec(128, constantIV)` for every encryption | Reuses `(K, IV)` when reusing the key. | Allocate a genuinely fresh IV for **each encryption**. |
| Same key/IV with different AAD or plaintext | Still violates uniqueness; a new tag does not save the design. | `(key, IV)` pairs must never repeat for encryption. |
| Generating 96 random bits assuming "collision is impossible" | Randomness has non-zero collision probability that grows with ciphertext count. | Limit invocations/rotate keys or use a uniqueness-enforcing IV scheme. |
| Counter resets to 0 on service restart | Can regenerate old `(key, IV)` pairs. | Durable counter, rollback protection, non-overlapping node prefixes. |
| Assuming the provider detects all nonce reuse | Providers lack a system-wide registry. | Enforce uniqueness at the protocol/application layer. |
| Failing to save the IV and generating a new one on decryption | Cannot authenticate/decrypt ciphertext. | Store IV publicly alongside ciphertext; pass the exact old IV on decryption. |
| Calling `updateAAD` after `update`/`doFinal` | Violates GCM ordering; may throw `IllegalStateException`. | AAD **before** ciphertext/plaintext data. |
| Dropping the tag or splitting the tag wrong from ciphertext | Verification fails or format breaks. | Fix `tLen`; pass exact `ciphertext + tag`. |
| Catching `AEADBadTagException` and returning "attempted" plaintext | Accepts unauthenticated data. | Reject the record and report a controlled error. |
| Seeing `GCMParameterSpec` construct cleanly and assuming support | Constructor does not check all provider restrictions. | Verify at `Cipher.init` and test on the target environment's provider. |
| Dropping tag to 32/64 bits to save bandwidth | Weakens security and invokes strict NIST limits. | Prefer 128-bit tags unless a specialized evaluated design requires otherwise. |
| Calling `Cipher.getInstance("AES")` without mode | Mode/padding depends on provider, not necessarily GCM. | Specify `"AES/GCM/NoPadding"` explicitly. |
| Treating the IV as more secret than the key or logging plaintext/key | Wrong protection priorities. | Keep keys and plaintext secret; IV is typically public yet must be accurate and unique. |
| Sharing one `Cipher` across threads | `Cipher` is stateful and not thread-safe. | Use a separate instance per operation. |
| Having GCM and assuming replay protection is covered | Old valid ciphertexts can be replayed intact. | Add sequence/version, freshness, and application-level policies as needed. |

## 10. Diagnostic Scenarios

**Scenario A: `InvalidAlgorithmParameterException` on `init`.** First check that `spec.getTLen()` is 128 **bits**, `spec.getIV().length` is 12 **bytes**, and the provider supports the parameters. Distinguish this from `AEADBadTagException` during decryption verification.

**Scenario B: Encryption works, decryption always throws `AEADBadTagException`.** Check that the exact same key and version are used, the exact 12-byte original IV is used, `ciphertext||tag` is joined properly, AAD matches byte-for-byte, and tag length matches. Never try "disabling tag verification" to make decryption succeed.

**Scenario C: Every service creates a `SecureRandom` and generates 12 IV bytes per request.** This yields very low collision odds at moderate load, yet provides no absolute proof of cross-service uniqueness; you must evaluate total encryptions per key and key rotation policies.

**Scenario D: Two nodes share a key and both run a counter starting at 0.** This is a **guaranteed bug**: once both issue nonces 0, 1, 2..., `(K, IV)` reuse occurs. Partition nonce spaces with unique prefixes/namespaces or use a coordinated counter service.

**Scenario E: Tag was 128 bits, then an operator lowers `tLen` to 96 to shrink record size.** Shaving 4 bytes per record is not a harmless formatting tweak; it requires a new protocol/version, security bound review, and provider verification. Never change `tLen` arbitrarily under the same key.

**Scenario F: Modifying a stored record's IV and attempting to decrypt.** GCM rejects mismatched IVs; verification fails with overwhelming probability. This differs from **re-encrypting with the same key + old IV**, which violates usage constraints the moment encryption happens.

## 11. Self-Check Questions (with Answers)

**Q1.** Does `new GCMParameterSpec(128, new byte[12])` mean a 128-bit IV or a 128-bit tag?

**A:** A 128-bit (**16-byte**) tag; the IV is 12 bytes (**96 bits**). The all-zero IV array in the question's snippet must never be reused in real encryption.

**Q2.** Does reusing the same `(key, IV)` to decrypt a stored ciphertext violate the rule?

**A:** No. **Decryption must use the exact key and IV used to encrypt**. The non-repetition rule applies to **new encryption operations** under the same key.

**Q3.** Can nonces be generated from a 64-bit counter?

**A:** Yes, within a proper 96-bit IV protocol design, if combined with a prefix/namespace and counter management ensuring the full IV never repeats under the same key, even across multi-node/restarts. Do not pass a raw 64-bit integer into arbitrary APIs expecting it to work as a default valid IV.

**Q4.** Does a 128-bit tag prevent the harm of reusing an IV under the same key?

**A:** No. Reuse puts GCM at risk of losing both confidentiality and authenticity; a long tag cannot fix nonce reuse.

**Q5.** After GCM encryption, do the bytes returned by `cipher.doFinal` already include the tag?

**A:** Yes. Java's AEAD `Cipher` appends the tag to ciphertext on encryption and verifies the tag on decryption. If the envelope also carries the IV, you must prepend/store the IV per protocol.

**Q6.** Since AAD is not encrypted, can it be omitted during decryption?

**A:** No, if AAD was supplied during encryption. Decryption must supply the exact byte-for-byte AAD for the tag to match.

**Q7.** If `GCMParameterSpec(32, iv)` runs without error, does that mean a 32-bit tag is safe?

**A:** No. The constructor does not verify standards compliance, provider rules, or security policy. A 32-bit tag applies only to specialized scenarios under strict NIST constraints and is unsuitable for general use.

**Q8.** If one record uses key K1 and IV N, and another uses key K2 and IV N, is that a nonce collision under the same key?

**A:** No, provided K1 and K2 are genuinely distinct AES keys. The uniqueness invariant applies to `(K, IV)` pairs. However, key identification and rotation must be reliable.

## 12. References

- [Java SE 17 — GCMParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): `tLen` in bits, constructors, IV copying, and `getIV()`.
- [Java SE 17 — Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): AEAD, `updateAAD` order, tag with ciphertext, non-repeating IV requirement.
- [Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): generating cryptographically strong random bytes.
- [NIST SP 800-38D — GCM and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): valid tag lengths, 96-bit IV construction, and GCM usage limits.
- [RFC 5116 — An Interface and Algorithms for Authenticated Encryption](https://www.rfc-editor.org/rfc/rfc5116): AEAD interface and holistic view of nonce, plaintext, ciphertext, and AAD.