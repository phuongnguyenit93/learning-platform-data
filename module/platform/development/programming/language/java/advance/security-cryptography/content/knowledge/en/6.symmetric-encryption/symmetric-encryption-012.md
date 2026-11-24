# 6.12 Packaging IV, Parameters, Ciphertext, and Tag—and Using Plaintext Only After Verification Succeeds

A secure ciphertext must be **stored and transmitted together with the information needed to decrypt and authenticate it properly**. With authenticated encryption such as **AES-GCM**, components typically include: format version, policy-allowed algorithm/parameter suite, key identifier (*key ID*), IV/nonce, ciphertext, authentication tag, and additional authenticated data context (*AAD*, if any). On the receiving side, **plaintext must be passed into business processing only after tag verification succeeds**.

Easily overlooked points: the IV is not a secret key; the tag is not ciphertext; AAD is not encrypted; the packet *header* must also be integrity-bound if it governs how data is interpreted. The fact that `Cipher.update(...)` can emit bytes in some modes/providers **does not mean those bytes are authenticated**. In AES-GCM, the validity of the entire ciphertext and AAD is established only once tag verification in `doFinal(...)` completes successfully.

This lesson uses **Java 17+ and JCA/JCE** to explain the byte contract, propose a versioned envelope, demonstrate AES-GCM encryption/decryption, test tampering each field, and show how to avoid using unauthenticated plaintext in APIs, files, and streaming pipelines.

## 1. Learning Objectives

After studying this lesson, you will be able to:

1. Precisely distinguish **IV/nonce**, algorithm parameters, **ciphertext**, **tag**, **AAD**, **key ID**, and **secret key**.
2. Design an unambiguous, versioned, size-bounded binary envelope format.
3. Understand Java `Cipher.getInstance("AES/GCM/NoPadding")`, `GCMParameterSpec`, `updateAAD`, and `doFinal`, including the `ciphertext || tag` output layout of JCA examples.
4. Decrypt with bounded parsing, resolve the right key, verify AAD/header, and **expose plaintext only after `doFinal` succeeds**.
5. Identify bugs involving nonce reuse under one key, modifiable headers, bit/byte tag-length confusion, information-leaking error handling, and premature plaintext release.
6. Build tests for valid packets, bad tag, bad IV, bad AAD, wrong key, truncation, trailing bytes, version changes, and concurrency.
7. Identify limitations around large files, streaming, cipher providers, storage, and key lifecycles.

## 2. What Does an Encrypted Envelope Actually Contain?

Suppose a Java service needs to store an encrypted document. A packet might look like:

```text
+----------+---------+--------+-------------+----------------+------------+---------+
| Magic    | Version | Key ID | GCM params  | IV / nonce     | Ciphertext | Tag     |
+----------+---------+--------+-------------+----------------+------------+---------+
       \_________________ authenticated header _______________/
                     \_____________ AAD _____________/
                          (other business context may also be AAD)
                                     \____ ciphertext+tag ____/
```

This is a **logical diagram**—it does not mean AAD appears automatically as a separate byte slice inside `Cipher.doFinal` output. The encryptor feeds AAD to `Cipher.updateAAD(...)`; the decryptor must feed the **exact same AAD bytes in the exact same order** to verify the tag. If metadata needs to survive for years, store it in the header and pass those exact header bytes as AAD.

| Component | Function | Is It Secret? | What to Validate |
| --- | --- | --- | --- |
| **Magic/version** | Identifies format and decryption rules | No | Accept valid format/version; security-relevant bytes must be authenticated |
| **Algorithm/profile** | Selects permitted algorithm suite and parameters | No | Use only a trusted allowlist; never downgrade from input |
| **Key ID** | Locates decryption key in key vault | Not necessarily | Restrict allowed IDs, key permissions, and lifecycle; bind ID to ciphertext |
| **IV/nonce** | Unique value required by encryption mode | Usually no | Exact length, strict **non-reuse under the same key** |
| **Ciphertext** | Encrypted payload | Must not be treated as plaintext; still needs access controls | Check structure, length limits, never use unauthenticated |
| **Authentication tag** | Authenticates ciphertext and AAD | No | Exact length, verified in `doFinal`; never ignore |
| **AAD** | Binds unencrypted metadata/context | Not encrypted by AES-GCM | Identical bytes between encrypt/decrypt; include fields affecting interpretation or permissions |
| **Secret key** | Capability to decrypt and produce valid ciphertext/tag | **Yes** | **Never bundle inside the envelope**; retrieve via controlled keystore/KMS/HSM |

An encryption envelope *does not solve authorization automatically*. Even with a valid tag, the service must still check whether the user is allowed to read the document, matches the tenant, action, and business state.

### Why Version?

Never force applications to guess whether leading bytes are a 12- or 16-byte IV, how long the tag is, or which algorithm was used. Once a format ships, old ciphertexts often outlive current source code. **Version** points to a tight specification: field order, encoding, lengths, algorithm, tag length, error handling, and metadata authentication method.

When changing profiles, introduce a new version and maintain a policy for reading legacy data and rotating keys. Never "try algorithms one by one until decryption yields something that looks like Vietnamese".

## 3. AES-GCM: Where Are Ciphertext, Tag, and AAD Produced?

AES-GCM is an **AEAD** (*Authenticated Encryption with Associated Data*) mode: it keeps plaintext confidential and produces a tag verifying integrity of ciphertext and AAD. Typical Java API contract:

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, iv));
cipher.updateAAD(aadBytes);
byte[] ciphertextAndTag = cipher.doFinal(plaintextBytes);
```

The snippet above is **illustrative only**, assuming `key` is an AES `SecretKey`, `iv` is a valid `byte[]`, and `aadBytes`/`plaintextBytes` exist. When using JCA AES-GCM this way, `doFinal` output contains **ciphertext followed by the authentication tag**; the tag is appended at the end of encrypted data. In this illustrative profile: tag = **128 bits = 16 bytes**.

Corresponding decryption:

```java
Cipher decipher = Cipher.getInstance("AES/GCM/NoPadding");
decipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, iv));
decipher.updateAAD(aadBytes);
byte[] verifiedPlaintext = decipher.doFinal(ciphertextAndTag);
```

With invalid ciphertext/tag/AAD/key/IV, `doFinal` must fail; many Java providers throw `AEADBadTagException` (in the `BadPaddingException` family), yet applications should treat any authentication error as **failure, returning no plaintext**. Each run needs the exact order `init -> updateAAD -> update/doFinal`; many providers require all AAD to be fed **before processing plaintext/ciphertext**.

### Distinguish Lengths and Units

- `new GCMParameterSpec(128, iv)`: **128 is tag bits**, not 128 bytes.
- `iv.length == 12`: **12-byte = 96-bit** IV/nonce, the standard GCM size.
- Under a 128-bit-tag profile, ciphertext of an `N`-byte plaintext is also `N` bytes, followed by a 16-byte tag. That is the unpadded AES-GCM size relationship, **excluding** headers.
- Base64 or hex merely converts binary envelopes to text; it adds zero cryptographic strength.
- `cipher.getIV()` can return the initialized cipher's IV; `cipher.getParameters()` can represent parameters. For long-term storage and cross-runtime compatibility, **define explicit serialization** rather than relying on an opaque `AlgorithmParameters` encoding.

### Tag vs. Standalone HMAC

With AES-GCM, the tag is computed and verified by the AEAD algorithm bound to ciphertext and AAD. **Never** omit the tag and hope decryption returning plausible text suffices. A standalone MAC/HMAC is a different mechanism with its own key/design/protocol; you cannot arbitrarily glue an HMAC onto AES-GCM output and treat it as the same profile.

## 4. A Simple Bounded, Versioned Binary Format

To ease testing, this lesson uses the following **demo v1** format with contiguous bytes in order:

```text
offset  size    field
0       4       magic = ASCII "GCM1"
4       1       version = 0x01
5       4       keyId = 7 (signed 32-bit big-endian, demo value)
9       1       nonceLength = 12
10      12      nonce (random per encryption)
22      N       ciphertext (same length as plaintext)
22+N    16      GCM authentication tag (128 bits)
```

In the Java code, the fixed header is **22 bytes**, nonce 12 bytes, and tag **16 bytes**; an envelope for a 13-byte plaintext is **22 + 13 + 16 = 51 bytes**. `ByteBuffer` defaults to big-endian; a profile should state this explicitly even when only one 4-byte `keyId` field exists.

**This is an example format**, not a recognized network standard. Never deploy it verbatim as production storage while skipping key lifecycle design, deployment-scale nonce uniqueness, version migration, size caps, provider error handling, and authorization.

Decisions to document in a real spec:

1. **Magic and version:** exact byte values, accepted versions, legacy version retirement policy.
2. **Algorithm:** for v1, `AES/GCM/NoPadding` and 128-bit tag are **fixed**, never letting an envelope request weaker algorithms.
3. **Key ID:** representation, how to resolve the exact key in keystore/KMS, and who is authorized to decrypt.
4. **IV:** 12-byte length, generation source, per-key non-repetition guarantee, and encryption count limits.
5. **AAD:** header bytes and structured business context strings; field order and framing must be unambiguous.
6. **Payload:** plaintext/ciphertext format, size caps, byte order for numeric fields, and large-file handling.
7. **Tag:** trailing 16 bytes of `ciphertextAndTag`; both are needed to decrypt.
8. **Errors:** any format or tag check failure produces zero trusted data.

**Note on headers:** magic, version, key ID, and nonce come from **unauthenticated** input when the parser first reads them. They only guide processing within allowlisted bounds; once the header is fed into AAD, a passing tag proves those bytes match the ciphertext and key. Never construct business objects or grant access from an unauthenticated header.

## 5. Authenticate Everything Before Using Plaintext

The biggest risk in this lesson is **using plaintext before tag verification finishes**. Safe flow for a size-bounded envelope:

```text
receive envelope (untrusted)
         |
         v
check format, version, length, quota, and allocation bounds
         |
         v
parse header -> select allowed key, extract IV, construct AAD
         |
         v
Cipher.init(DECRYPT_MODE, key, GCMParameterSpec)
         |
         v
updateAAD(exact header and agreed context)
         |
         v
doFinal(full ciphertext || tag)
       /   \
   error    success
    |           |
return no    authenticated plaintext
plaintext       |
                v
     validate schema/authorization
                |
                v
     now store/return/display/process
```

`Cipher.doFinal(...)` returning successfully is a **necessary condition** to treat decrypted bytes as having passed tag verification. In some implementations, chunked decryption with `update` can emit output **before the trailing tag is checked**. Therefore, never send those bytes to HTTP responses, public files, loggers, side-effecting parsers, or payment systems.

### What Counts as "Already Using Plaintext"?

Returning plaintext to the client is not the only hazard. The following also constitute using unauthenticated plaintext if done before `doFinal`:

- Writing data to a file another component can read.
- Inserting a DB record, publishing to Kafka/events, or executing a payment from newly decrypted data.
- Parsing and executing commands/expressions, calling downstream services, or running queries based on unauthenticated content.
- Logging plaintext or recording it in accessible traces/metrics.
- Using plaintext to authorize or select resources before verifying the tag.

Practical rule: **do not publish**, **do not commit side effects**, and **do not interpret as trusted** until complete decryption/authentication succeeds. Afterward, still validate schema and enforce business authorization; a cryptographically valid message does not automatically make the sender's action authorized.

### Why Is "try/catch Yet Still Writing Bytes" a Bug?

```java
// BAD CODE — anti-pattern illustration, not a standalone program
try {
    byte[] tentative = cipher.update(ciphertextChunk);
    response.write(tentative);  // May leak plaintext before tag is verified
    cipher.doFinal(tagBytes);
} catch (GeneralSecurityException ex) {
    log.warn("Decryption failed");
}
```

The failure may be detected **after** sensitive data has already crossed the trust boundary. Catching the exception cannot recall an HTTP response, emitted event, or DB write. This snippet also simplifies `Cipher`/streaming to spotlight the design flaw: **never rely on whether a provider buffers or emits early** to argue a system is safe.

## 6. Runnable Java 17+: Creating and Verifying an AES-GCM Envelope

The example below uses AES-256-GCM, a random 12-byte nonce, 128-bit tag, 22-byte header, fixed demo key ID, and context AAD. It **never returns plaintext to callers before `doFinal` verifies successfully**. The sample caps envelopes at 1,000,000 bytes to reject oversized input; that limit is purely for demonstration—production systems must size limits to their threat model and requirements.

Save as **`GcmEnvelopeDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class GcmEnvelopeDemo {
    private static final int MAGIC = 0x47434D31; // "GCM1"
    private static final byte VERSION = 1;
    private static final int KEY_ID = 7;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int TAG_BYTES = TAG_BITS / 8;
    private static final int HEADER_BYTES = 4 + 1 + 4 + 1 + NONCE_BYTES;
    private static final int MAX_ENVELOPE_BYTES = 1_000_000;
    private static final SecureRandom RANDOM = new SecureRandom();

    static byte[] frameContext(byte[] context) {
        return ByteBuffer.allocate(4 + context.length)
                .putInt(context.length).put(context).array();
    }

    static byte[] encrypt(SecretKey key, byte[] plaintext, byte[] context)
            throws GeneralSecurityException {
        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);
        byte[] header = ByteBuffer.allocate(HEADER_BYTES)
                .putInt(MAGIC).put(VERSION).putInt(KEY_ID)
                .put((byte) NONCE_BYTES).put(nonce).array();

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(header);
        cipher.updateAAD(frameContext(context));
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);
        return ByteBuffer.allocate(header.length + ciphertextAndTag.length)
                .put(header).put(ciphertextAndTag).array();
    }

    static byte[] decrypt(SecretKey key, byte[] envelope, byte[] context)
            throws GeneralSecurityException {
        if (envelope == null || envelope.length < HEADER_BYTES + TAG_BYTES
                || envelope.length > MAX_ENVELOPE_BYTES) {
            throw new GeneralSecurityException("Invalid envelope size");
        }
        ByteBuffer input = ByteBuffer.wrap(envelope);
        int magic = input.getInt();
        byte version = input.get();
        int keyId = input.getInt();
        int nonceLength = Byte.toUnsignedInt(input.get());
        if (magic != MAGIC || version != VERSION || keyId != KEY_ID
                || nonceLength != NONCE_BYTES) {
            throw new GeneralSecurityException("Unsupported envelope");
        }
        byte[] nonce = new byte[NONCE_BYTES];
        input.get(nonce);

        byte[] header = Arrays.copyOfRange(envelope, 0, HEADER_BYTES);
        byte[] ciphertextAndTag =
                Arrays.copyOfRange(envelope, HEADER_BYTES, envelope.length);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(header);
        cipher.updateAAD(frameContext(context));

        // Only this successful doFinal yields plaintext to the caller.
        return cipher.doFinal(ciphertextAndTag);
    }

    @FunctionalInterface
    interface Attempt {
        void run() throws GeneralSecurityException;
    }

    static boolean rejected(Attempt attempt) {
        try {
            attempt.run();
            return false;
        } catch (GeneralSecurityException ex) {
            return true;
        }
    }

    public static void main(String[] args) throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey key = generator.generateKey();
        byte[] message = "Hello AES-GCM".getBytes(StandardCharsets.UTF_8);
        byte[] aad = "tenant-A/document-7".getBytes(StandardCharsets.UTF_8);

        byte[] packed = encrypt(key, message, aad);
        String verified = new String(decrypt(key, packed, aad), StandardCharsets.UTF_8);

        byte[] badTag = packed.clone();
        badTag[badTag.length - 1] ^= 1;
        byte[] badNonce = packed.clone();
        badNonce[HEADER_BYTES - 1] ^= 1;
        KeyGenerator anotherGenerator = KeyGenerator.getInstance("AES");
        anotherGenerator.init(256);
        SecretKey wrongKey = anotherGenerator.generateKey();
        byte[] truncated = Arrays.copyOf(packed, HEADER_BYTES + TAG_BYTES - 1);

        System.out.println("Header bytes: " + HEADER_BYTES);
        System.out.println("Nonce bytes: " + NONCE_BYTES);
        System.out.println("Tag bytes: " + TAG_BYTES);
        System.out.println("Ciphertext bytes: " + (packed.length - HEADER_BYTES - TAG_BYTES));
        System.out.println("Envelope bytes: " + packed.length);
        System.out.println("Verified plaintext: " + verified);
        System.out.println("Modified tag rejected: " +
                rejected(() -> decrypt(key, badTag, aad)));
        System.out.println("Modified nonce rejected: " +
                rejected(() -> decrypt(key, badNonce, aad)));
        System.out.println("Wrong AAD rejected: " +
                rejected(() -> decrypt(key, packed,
                        "tenant-B/document-7".getBytes(StandardCharsets.UTF_8))));
        System.out.println("Wrong key rejected: " +
                rejected(() -> decrypt(wrongKey, packed, aad)));
        System.out.println("Truncated envelope rejected: " +
                rejected(() -> decrypt(key, truncated, aad)));
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac --release 17 GcmEnvelopeDemo.java
java GcmEnvelopeDemo
```

**Exact stdout** (no random nonces/ciphertexts printed):

```text
Header bytes: 22
Nonce bytes: 12
Tag bytes: 16
Ciphertext bytes: 13
Envelope bytes: 51
Verified plaintext: Hello AES-GCM
Modified tag rejected: true
Modified nonce rejected: true
Wrong AAD rejected: true
Wrong key rejected: true
Truncated envelope rejected: true
```

### 6.1 Part-by-Part Explanation

**`encrypt`:**

1. Generates a fresh 12-byte nonce via `SecureRandom` for **each encryption**. Under the same AES-GCM key, never deliberately reuse a nonce; see Section 8 for real-world uniqueness requirements.
2. Builds the header with magic, version, key ID, and nonce. Demo key ID = 7; in real products, the ID resolves the secret key from a key management store rather than copying secrets into the header.
3. Initializes `Cipher` with `AES/GCM/NoPadding`, the AES key, and `GCMParameterSpec(TAG_BITS, nonce)`.
4. `updateAAD(header)` protects format-describing bytes; `updateAAD(frameContext(context))` protects context (e.g., tenant/document) without encrypting it.
5. `doFinal(plaintext)` produces `ciphertext || tag`. Prepending the header yields the envelope.

**`decrypt`:**

1. Rejects null envelopes, envelopes too short to contain header+tag, or envelopes exceeding allowed size **before large allocations or decryption**.
2. Parses exact header bytes and checks the profile allowlist (magic/version, demo ID, nonce length). These initial checks inspect unauthenticated input; never base authorization decisions on them.
3. Extracts the exact nonce, header bytes, and trailing `ciphertextAndTag`. Feeds identical AAD bytes in identical order.
4. Calls **one** `cipher.doFinal(ciphertextAndTag)`, letting the provider verify the tag. The `decrypt` method **returns `byte[]` only after `doFinal` succeeds**; throwing an exception guarantees no plaintext leaves via return value.
5. The caller decodes valid bytes to UTF-8 for display **after authentication**, and must continue validating schema/authorization if data originated externally.

**Negative tests:** flipping bits in the tag or header nonce, changing AAD context, swapping the key, or truncating the envelope are all rejected. The same message produces different ciphertext/tag bytes across runs due to random nonces; what matters is decrypting the right message and detecting any unauthorized change.

### 6.2 Limitations of the Example

- `MAX_ENVELOPE_BYTES` is intentionally small to illustrate bounded input; never use `readAllBytes` on unbounded input.
- The example generates an in-process key without persistence. Real systems need a keystore/KMS, decrypt authorization, versioning, and rotation. Restarting the program generates a new key that **cannot decrypt old envelopes**.
- Key ID = 7 is hardcoded strictly for demo purposes. Production needs a resolver checking configuration/key IDs, least-privilege access, safe logging, and multi-version support. Never treat an input-supplied ID as authenticated prior to `doFinal`.
- The example operates purely on in-memory buffers; large data requires quarantining unauthenticated plaintext and preventing leaks while streaming.
- A valid tag for the demo context does not prove the caller has permission to read the object. Authenticate identity and enforce authorization using trusted metadata separately from tag checks.
- The example does not attempt to guarantee every key/plaintext copy is scrubbed from JVM memory. That depends on runtime, provider, secrets manager, and storage design.

## 7. Appending the Tag vs. Separating the Tag Field

Libraries and protocols represent the tag in one of two ways:

**Concatenated form (e.g., JCA AES-GCM):**

```text
header || ciphertext || tag
           \___________/
             doFinal output
```

In the example, `Cipher.doFinal(plaintext)` returns bytes containing ciphertext followed by the trailing tag; on decryption, pass the entire `ciphertext || tag` slice into `doFinal`.

**Separate-field form (some SDKs/APIs/protocols):**

```text
envelope = { version, keyId, iv, ciphertext, tag }
```

If an API expects separate `ciphertext` and `tag`, a parser can slice off the trailing 16 tag bytes after validating length; when feeding back into JCA, re-concatenate them in the exact order expected by the active provider contract. Never assume every AES-GCM API returns the exact same object layout or tag placement.

### Why Not Omit "Recomputable" Metadata?

Once ciphertext is stored, key ID, IV, tag length, and AAD context can govern whether decryption is even possible. An IV **cannot be inferred** from ciphertext in general. The tag must be preserved in full. Losing AAD-bound values such as tenant ID or schema version makes future tag verification fail even when key and ciphertext remain intact.

For long-lived formats, specify **version** and AAD reconstruction rules explicitly; metadata fields are not automatically included in the tag unless properly passed to `updateAAD` or authenticated plaintext.

## 8. Nonce/IV: GCM's Hardest-to-Ignore Invariant

**GCM requires a unique IV/nonce per key**. The IV need not be secret, yet **reusing the same nonce with the same key** in GCM can catastrophically break security, impacting both confidentiality and forgery resistance. This is an operational requirement—not something `GCMParameterSpec` enforces for you.

- **Never** hardcode `new byte[12]` as the IV for every encryption.
- **Never** use bare timestamps or collision-prone IDs when multiple nodes/processes encrypt under one key.
- **Never** assume a `Cipher.init` check on one instance detects every IV reuse across the entire system.
- **Never** use random IVs while ignoring message caps and collision odds when a single key handles massive volume.
- **Do** establish an IV allocation policy matched to your load model: high-quality random 96-bit nonces with strict encryption caps, or coordinated, rollback-safe unique counter/nonce allocation per protocol and GCM standards.
- **Do** implement key rotation, usage-limit telemetry, cross-node key distribution, and plans to prevent reuse after crashes/snapshot restores.

In the demo, `SecureRandom` creates 12 bytes per call. That only illustrates random generation; for high-traffic, multi-region/instance apps, or where strict uniqueness proofs are required, evaluate the nonce strategy across **the key's entire lifetime**.

**New key, reused IV?** Uniqueness applies per **(key, IV) pair**. Even so, never treat key management or IV allocation casually: track exactly which key is active and avoid reusing a key if a counter resets.

## 9. AAD Must Bind Exact Business Metadata/Context

AAD is authenticated, unencrypted data. In multi-tenant systems, a valid ciphertext for tenant A must never be accepted when attached to tenant B's context. Typical uses:

- Header bytes containing version, key ID, nonce, and profile.
- `tenantId`, `documentId`, usage purpose (e.g., `document-storage:v1`), and business-distinguishing fields.
- Schema version info if needed to parse plaintext consistently.

These fields can be combined via explicit **length-prefixing** or canonical serialization. Never concatenate raw strings without boundaries, since `("ab", "c")` and `("a", "bc")` both yield `"abc"`. The `frameContext` helper prepends a 32-bit length for one context; in real products with multi-field contexts, define framing across every field completely.

Special point: **AAD order must match**. The encryptor calls `updateAAD(header)` then `updateAAD(frameContext(context))`; the decryptor must pass the exact same bytes in the exact same order. Tags can fail when Unicode normalization, charset, JSON field order, version numbers, or whitespace shift. AAD should use a stable canonical byte representation backed by golden vectors.

Never pass a user-editable tenant string from a query parameter and treat it as trusted context. Tenant/document context must be **bound to an authenticated and authorized resource** via real identity/metadata; AAD only detects tampering relative to the supplied context.

### When Metadata Changes

If `documentId`/tenant/metadata is in AAD and needs changing, you cannot simply edit the header or context and expect the old tag to hold. You need a workflow: **authenticated decryption under old context -> authorization/migration rule check -> re-encryption under new context with a fresh IV**. Keep audit trails and appropriate key IDs/versions.

## 10. Format Validation and Authentication Errors Are Two Distinct Layers

Before invoking cryptography, the parser is responsible for validating partner/user-controlled input:

1. **Total byte limits:** max request/file size, timeouts, and memory quotas; never allocate based on an unchecked header length.
2. **Valid magic/version/algorithm:** reject unsupported profiles. Never read transformation strings directly from untrusted data.
3. **Valid sizes:** 12-byte nonce, 16-byte tag, minimum `22+16` envelope bytes in demo; sums must not integer-overflow.
4. **Valid key ID:** within allowlist/namespace and permissions; safe lookup preventing IDs from pointing outside the tenant/allowed vault.
5. **Deterministic AAD construction:** never pull loose context from untrusted sources; keep versioning and canonical serialization.
6. **No arbitrary trailing bytes:** define the full envelope belonging to one message. If a format packs multiple messages, add explicit framing boundaries.
7. **Tag verified and never bypassed:** never return content from an "unauthenticated fallback" mode if GCM fails.

These are **syntactic and resource** checks, performed early to prevent DoS. Yet parsed magic/version/key ID/IV remain unproven metadata until tag verification passes. Only after `doFinal` succeeds do you have integrity proof for the bytes fed into AAD and ciphertext.

### Exception Handling

Depending on the failure, Java may throw:

- `IllegalArgumentException` / internal parse error on malformed API inputs; catch at boundaries and convert to invalid-request errors.
- `InvalidKeyException`, `InvalidAlgorithmParameterException`, or `NoSuchAlgorithmException` when key/algorithm/parameters mismatch.
- `AEADBadTagException` (subclass of `BadPaddingException`) when tag verification fails.
- `GeneralSecurityException` as a convenient checked family for demo APIs; in production, separate internal logging from external responses.

Never return **partial plaintext** on any error path. Never patch tags, try slicing tags, fall back to `AES/CBC/PKCS5Padding`, or run unauthenticated decryption just to "salvage data". Return consistent external errors avoiding oracles across status codes, timing, or messages. Log request IDs, key versions, and sanitized error codes; never log raw secrets, plaintext, or sensitive full envelopes.

## 11. Storage and HTTP: Never Push Unauthenticated Plaintext Outward

### 11.1 Small Files or Objects with Clear Limits

A straightforward strategy:

1. Authenticate caller and verify object read authorization before touching keys or making large allocations.
2. Read the envelope into memory **only if size is within bounds**.
3. Parse header, call `decrypt` as shown, and hold the resulting `byte[]` in a tightly scoped buffer.
4. Once `doFinal` returns cleanly, validate content schema and remaining authorization rules.
5. Only then send the response or write data to its target destination.

Never share a `ByteArrayOutputStream` that flushes unauthenticated output chunks into an open response. Never feed unauthenticated bytes into parsers that automatically write DB records or emit events.

### 11.2 Large Data and Streaming AEAD

For multi-GB files, holding all ciphertext and plaintext in heap may be infeasible; yet streaming AEAD decryption faces a constraint: **the tag is normally verified only at the very end**. You cannot simultaneously emit plaintext to an irreversible sink and uphold "only after authentication" merely by calling `update` followed by `doFinal`.

Design options to evaluate:

- **Small/medium encrypted files:** enforce size caps and verify completely in memory before returning. Simplest to audit.
- **Private, inaccessible staging area:** if an implementation emits plaintext early, write strictly to an isolated temporary area with tight access controls and zero side effects; **only after `doFinal` succeeds**, publish or atomically commit. On error, delete staging and emit no events. Account for crashes, temp-file permissions, backups, cleanup, and pre-commit leaks.
- **Splitting data into independent structured AEAD records/chunks:** each chunk has its own nonce/sequence and tag, authenticated individually before use, protecting order, count, EOF/truncation, metadata, and an authenticated final manifest/commitment. Never assume decrypting each chunk individually guarantees the whole file is complete; protocol design and nonce allocation are critical.
- **Dedicated, reviewed streaming AEAD libraries/constructions:** use abstractions with explicit authentication contracts rather than inventing tag-chaining formats.

Never rely on `CipherInputStream` as a guarantee that all integrity exceptions propagate intact to callers. JDK documentation warns this class may catch integrity exceptions (such as `BadPaddingException`) without rethrowing them; consequently, it may be **unsuitable for authenticated decryption when full integrity error reporting is required**. Choose verified APIs and control exact tag verification boundaries.

### 11.3 Side Effects That Must Be Deferred

- HTTP response bodies, download links, or public object storage writes.
- Event buses, queues, emails/webhooks, or side-effecting calls to other services.
- DB commits, order status updates, permission grants, or balance updates.
- Parsers capable of running commands or triggering logic based on plaintext.
- Logs/traces, crash reports, and caches containing sensitive data.

If an app must show download progress, it may report ciphertext bytes received or verification state, yet must never mark content as verified before reading and validating the protocol's full tag/commitment.

## 12. Comparing AES-GCM with Legacy Encryption Formats

Some systems still store:

```text
AES-CBC: IV || ciphertext
AES-CBC + HMAC: header || IV || ciphertext || macTag
```

**AES-CBC has no built-in authentication tag.** Bare `IV || ciphertext` without MAC/AEAD fails tamper-detection requirements. If a legacy system uses standard **Encrypt-then-MAC**, it must compute the MAC over a structure covering all relevant fields (typically version/IV/ciphertext and context), **verify the MAC before CBC decryption**, and only then decrypt and unpad. Never leak padding error details to attackers to avoid padding oracles. This demands key separation and vetted algorithms/protocols; never slap an arbitrary HMAC onto CBC and call it safe AEAD.

For new designs, prefer standard AEAD such as AES-GCM when requirements fit and nonce/key management are sound. Never "fall back to CBC" if a GCM tag fails, nor accept an out-of-policy legacy version merely because it decrypts.

## 13. Operations: Key ID, Rotation, and Migration

A long-lived envelope typically needs to record **which key** was used, while **never embedding the key**. On encryption, the service obtains an authorized key, writes the key ID/version into the header, and feeds the header into AAD. On decryption, the service parses the ID to **route to an allowed key**, and a passing tag confirms the header was legitimately bound to the ciphertext.

Operational requirements:

- **Namespace and identity bounds:** clients must never specify arbitrary key file paths, URIs, or another tenant's key by forging a key ID.
- **Key rotation:** new keys encrypt; old keys remain decrypt-enabled conditionally during migration, then are retired per policy.
- **Re-encryption:** decrypt+authenticate with old key/IV/AAD, then encrypt with the new key and a **fresh nonce**; never copy raw ciphertext/tag and merely swap the key ID.
- **Bound metadata:** key ID, version, tenant, and document ID must stay stable or migrate deliberately; altering AAD invalidates old tags.
- **Avoid unnecessary raw key bytes in app memory** when KMS/HSM supports required operations; whether using direct AES-GCM or envelope encryption must fit the provider's API.
- **Audit:** record sanitized key version, action, resource, and success/failure outcome; never log keys, plaintext, sensitive full AAD, or secret-leaking data.

In practice, AES-GCM does not replace storage access controls. IAM, service permissions, tenant isolation, backup protection, and anomaly detection remain essential.

## 14. Common Mistakes and Fixes

| Mistake | Consequence | Proper Practice |
| --- | --- | --- |
| Storing only ciphertext, dropping IV/tag | Cannot decrypt/authenticate reliably | Store complete envelope with version and required parameters |
| Bundling secret key with ciphertext | Anyone holding the packet can decrypt | Keep keys in key manager/KMS/HSM; envelope carries only key ID |
| Confusing 128-**bit** tag with 128-**byte** tag | Parsing bugs or provider errors | Specify tag bits in `GCMParameterSpec`, bytes in storage |
| Reusing IV under the same key | Severely breaks GCM security | Enforce per-key uniqueness across entire key lifecycle |
| Treating nonce as password or secret | Wrong purpose; leaves key unprotected | Nonces may be public; keys must remain secret |
| Omitting header/context from AAD | Metadata can be swapped outside auth scope | Cover all fields affecting interpretation and permissions |
| Trusting fields parsed before decryption | Attacker alters version/key ID/tenant | Apply allowlists/bounds early; trust only after auth and access checks |
| Calling `update` and streaming plaintext to HTTP | Leaks plaintext before tag verification | Isolate buffer/staging or use per-record AEAD with clear contracts |
| Catching `AEADBadTagException` and returning partial output | Accepts tampered data | Fail closed; publish zero plaintext |
| Using `CipherInputStream` without checking integrity handling | May silently hide tag/padding failures | Use verifiable complete-authentication APIs |
| Re-serializing JSON/AAD before decryption | Changes AAD bytes, causing tag failure | Fixed canonical byte format and versioning |
| Falling back to unauthenticated algorithm after failure | Opens downgrade/oracle paths | Version allowlist; reject on tag failure |
| Unbounded key ID | Can steer decryption outside scope | Constrain key namespace, IAM/KMS permissions, and tenant |
| Unbounded envelope length | Causes huge allocations/DoS | Validate length, quotas, and timeouts before allocating |
| Treating a valid tag as caller authorization | Authorization bypass | Check identity/ACL/tenant/action separately |
| Reusing valid tagged packets repeatedly unchecked | Action replay | Protocol nonce/sequence/time + idempotency where needed |
| Changing key ID or AAD while keeping old tag | Tag fails verification | Authenticated decrypt first, then re-encrypt with new context/key |

## 15. Required Test Suite

Design at least these cases using **test** keys and data, never production secrets:

| Case | Action | Expected Result |
| --- | --- | --- |
| Round trip | Encrypt then decrypt with envelope's key/IV and exact AAD | Returns exact plaintext bytes; only after verification |
| Modified tag | Flip one bit in trailing tag | Decryption fails, zero plaintext returned |
| Modified ciphertext | Flip one bit inside ciphertext | Tag fails, zero side effects |
| Modified nonce | Flip a nonce byte in header | Rejected; tag mismatch |
| Altered AAD | Change tenant/document context | Rejected; plaintext not interpreted |
| Different key | Decrypt with another key of same algorithm | Rejected |
| Altered header | Change version/key ID/magic | Rejected by profile or tag; no fallback |
| Truncation | Missing header, IV, ciphertext, or tag | Syntax or auth rejection, no out-of-bounds read |
| Trailing garbage | Append extra byte at end of envelope | Never silently ignored; rejected on tag failure |
| Empty plaintext | Encrypt 0 bytes | Envelope still carries tag; decrypts to empty array |
| Unicode plaintext | Explicit UTF-8 encoding rules | Exact byte round trip; no implicit charset shifts |
| Canonical header/AAD | Two runtimes frame identical context identically | AAD bytes and verification match |
| Multiple encryptions | Same key and plaintext with fresh nonces | Nonces never repeat; ciphertext/tag differ |
| Key rotation | Old version permitted or revoked | Follows policy; no blind key brute-forcing |
| Oversized envelope | Input exceeds quota | Rejected before large allocation |
| Streaming I/O failure | Receive 90% ciphertext then error | Zero plaintext committed/published |
| Concurrency | Many simultaneous encrypt/decrypt requests | Separate `Cipher` per request; zero state mixing |

**One security test more important than tag checks:** attach a mock sink (HTTP response, DB commit, event publisher) and feed decryption bad ciphertext/tag. Assert **the sink receives zero plaintext**, even before the exception is thrown. That directly verifies "use plaintext only after authentication succeeds".

For cross-language interoperability, use **independent golden vectors** of the algorithm/profile: known key, IV, AAD, plaintext, and expected ciphertext/tag in tests. Do not rely solely on one method's encrypt/decrypt agreeing with itself.

## 16. Practice Exercises

### Exercise 1 — Inspect Envelope Byte Boundaries

Using `GcmEnvelopeDemo`, record exact byte offsets for magic/version/key ID/nonce/ciphertext/tag. For plaintext `Hello AES-GCM` (13 UTF-8 bytes), explain why header = 22, tag = 16, and envelope = 51 bytes. Flip a byte at offset 22 inside ciphertext and confirm zero plaintext is returned. Flip the final byte and show it belongs to the tag.

### Exercise 2 — Protecting Tenant and Key ID

Suppose storage has metadata `tenantId`, `documentId`, and `keyVersion`. Design a length-prefixed AAD framing scheme and test metadata swapping. Verify context comes from trusted identity/metadata; if a user changes tenant in a request, the service must never switch to another tenant's key just from the header.

### Exercise 3 — From `byte[]` to Real Storage

Design a `readAndVerify` method for objects capped at 1 MiB:

1. Verify caller read permission via trusted metadata.
2. Read envelope with size quota.
3. Parse version/ID/nonce and resolve exact key.
4. Authenticate the full tag.
5. Only after success, parse JSON/binary, write audit log, and return response.
6. On bad tag, wrong key, I/O error, or swapped metadata, return no plaintext and emit zero side-effect events.

### Exercise 4 — Designing for Large Files

Suppose you must decrypt a 4 GiB file and serve it for download. Explain why calling `Cipher.update` and streaming bytes straight to an HTTP response before `doFinal` is unsafe. Propose an isolated staging area with atomic publish after verification, or an AEAD record protocol with sequence/tag/EOF commitment; describe how to handle crashes, retries, nonce uniqueness, and truncated files.

**Completion criteria:** you can accurately extract IV, version, key ID, ciphertext, tag, and AAD from an envelope; know which bytes are truly authenticated; have test proof that a bad tag rejects all plaintext; and distinguish **authenticated encryption** from **access authorization**.

## 17. References

- [Java SE 17 — Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): `init`, `updateAAD`, `update`, `doFinal`, and AEAD.
- [Java SE 17 — GCMParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): tag length in bits and IV.
- [Java SE 17 — AEADBadTagException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/AEADBadTagException.html): tag verification error.
- [Java SE 17 — CipherInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/CipherInputStream.html): notes on exceptions during integrity verification.
- [NIST SP 800-38D — Galois/Counter Mode (GCM)](https://csrc.nist.gov/pubs/sp/800/38/d/final): AEAD model and IV/nonce requirements.
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): mode selection, key management, and nonces.