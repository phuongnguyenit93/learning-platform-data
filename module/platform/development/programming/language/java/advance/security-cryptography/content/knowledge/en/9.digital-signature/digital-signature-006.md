# 9.6. Standardizing Signed Data and Avoiding Double Hashing When APIs Already Combine Digests

## Learning objectives

After this lesson, you can:

1. Distinguish **original message bytes**, **digest**, **digital signature**, and **representation of data to sign**; understand which exact byte sequence is protected.
2. Explain why `Signature.getInstance("SHA256withRSA")` already performs SHA-256 as part of the signature algorithm and why calling `MessageDigest.digest(...)` before `Signature.update(...)` can unintentionally cause **double hashing**.
3. Design an explicit **signed-data contract**: field ordering, data types, UTF-8 encoding, Unicode, decimals, timestamps, field separation, domain separation, versioning, metadata, and canonicalization.
4. Use Java 17+ to sign and verify the **exact same byte sequence**, test tampered data, demonstrate the double-hashing bug, and recognize differences among RSA/PKCS#1 v1.5, RSA-PSS, ECDSA, and Ed25519.
5. Integrate with partners, HSMs, KMS, or digest-only APIs without confusing **combined-digest APIs** with **prehashed-digest signing APIs**, while separating signature verification from identity trust, authorization, and replay protection.

**Scope:** This lesson belongs to topic **9. Digital Signatures** in Java Advance – security-cryptography. The focus is input consistency and signing API semantics; demos signing with freshly generated keys only illustrate the mechanics and do not replace PKI or production trust infrastructure.

---

## 1. What data does a digital signature actually sign?

A digital signature does not sign “a Java object” in an abstract sense. The signature API processes a **deterministic sequence of bytes**. For a digest-integrated algorithm such as `SHA256withRSA`, the conceptual flow is:

```text
Business data (order, payload, file, request...)
                         │
                         ▼
          Serialization/canonicalization
                         │
                         ▼
                 Message bytes M
                         │
                         ▼
       Signature("SHA256withRSA").update(M)
                         │
                         ▼
           SHA-256(M)  [inside the engine]
                         │
                         ▼
          RSA / PKCS#1 v1.5 signing mechanism
                         │
                         ▼
                 Signature bytes S

Receiver: reconstruct exact M → Signature.verify(S) with public key
```

This diagram illustrates semantics; the provider handles hashing details, digest encoding, padding, and signing math per the specific algorithm. With `SHA256withRSA`, SHA-256 is already inside “SHA256with...”. With `SHA256withECDSA` or `RSASSA-PSS` configured for SHA-256, the corresponding API likewise handles the digest per scheme. With `Ed25519`, EdDSA performs internal hashing **according to the Ed25519 specification itself**, which does not mean you may replace the message with `SHA-256(M)`.

Key points:

- **Message bytes (`M`)**: bytes agreed upon by both parties as the input.
- **Digest (`H(M)`)**: output of a hash function like SHA-256, typically 32 bytes long; useful as a fingerprint/content check or computed *inside* the signature scheme.
- **Signature (`S`)**: output of the signing algorithm using the private key and input; normally the verifier uses the public key and the **exact bytes M**.
- **Identity authentication**: a signature only proves consistency with a public key and algorithm. Concluding “who signed it” requires a public-key/certificate trust process and policy.

The normal `Signature` workflow is **init → update(message bytes) → sign/verify**. Do not pre-hash manually merely because you heard digital signatures use hash functions.

## 2. Single hashing vs. double hashing differ in semantics

Let `H` be SHA-256 and `M` be the agreed content bytes.

### 2.1. Correct usage with a digest-integrated algorithm

```text
Signature("SHA256withRSA").update(M)
           └── engine computes H(M)
           └── creates RSA signature over digest representation per scheme

Verifier("SHA256withRSA").update(M)
           └── engine computes the same H(M)
           └── verifies signature over the exact message M
```

Java:

```java
Signature signer = Signature.getInstance("SHA256withRSA");
signer.initSign(privateKey);
signer.update(messageBytes);
byte[] signature = signer.sign();

Signature verifier = Signature.getInstance("SHA256withRSA");
verifier.initVerify(publicKey);
verifier.update(messageBytes);
boolean ok = verifier.verify(signature);
```

This is a **non-standalone snippet**: it requires `import java.security.Signature;`, matching keys and `messageBytes`, plus checked exception handling. A complete standalone example is in section 6.

### 2.2. Mismatch when pre-hashing before a digest-integrated algorithm

```java
byte[] digest = MessageDigest.getInstance("SHA-256")
        .digest(messageBytes);

Signature signer = Signature.getInstance("SHA256withRSA");
signer.initSign(privateKey);
signer.update(digest); // Signs H(M) as if it were the entire message.
byte[] signature = signer.sign();
```

This is an **anti-pattern for a protocol expecting M to be signed**. With `SHA256withRSA`, the engine computes SHA-256 again over the **32 digest bytes** passed in, so the signature holds for `H(H(M))` at the internal digest layer instead of the expected `H(M)`.

```text
M ── SHA-256 ──> H(M) ── Signature(SHA256withRSA) ── SHA-256 ──> H(H(M))
^                                                ^
Data both sides want to sign                     Engine treats H(M) as message
```

Practical consequences:

- A receiver passing the **original M** into `SHA256withRSA` will fail to verify a signature produced by a sender **who passed `H(M)`**.
- If both sides accidentally pass **`H(M)`** into `SHA256withRSA`, `verify` can return **true**; **`true` does not prove both sides implemented the intended protocol**.
- Double hashing does not automatically mean an attacker can immediately forge RSA; the direct problem is **signing the wrong message/semantics, cross-party incompatibility, and confusion over what data is protected**, which can lead to system vulnerabilities when components apply differing rules.
- Switching to `Signature.getInstance("NONEwithRSA")` or `NONEwithECDSA` as a “quick fix” is **dangerous**: unhashed modes carry strict contracts, padding/encoding rules, and provider constraints; they are not generic drop-in APIs that accept a digest and sign per every scheme.

**Rule:** when `Signature` already integrates a digest, pass the **canonicalized data bytes to sign**, unless the protocol is explicitly designed such that a digest itself is the *message* being signed.

### 2.3. Where should you compute `MessageDigest` yourself?

You should, when you have a **different** purpose:

- Producing a fingerprint for display, audit correlation, or detecting content changes.
- Verifying download integrity over a trusted channel with an independently authenticated digest.
- Integrating with a signing service **whose contract specifies prehashed input** (e.g., an HSM/KMS API accepting a raw digest), in which case you must know the exact bytes and digest-acceptance contract (see section 8).
- Signing **a manifest containing digests** of multiple files: here the manifest itself is the signed message `M`; it needs clear structure/encoding/versioning. This is not a “fix for double hashing” but a manifest-signing protocol design.

Hashing separately for logging does not alter the bytes passed to `Signature.update` in a direct signing protocol.

## 3. Why can the same “content” produce different signatures?

Two parties can look at an order showing “125.50 VND” yet produce **different byte arrays**. A signature algorithm receives bytes—it does not understand objects, field names, or semantics; a single byte difference normally causes verification to fail.

### 3.1. Common discrepancies

| Data source | Side A | Side B | Why signing differs |
| --- | --- | --- | --- |
| Encoding | UTF-8 | UTF-16LE or platform default | Byte arrays differ even when text looks identical |
| Unicode | Accented characters in NFC form | NFD form (base char + combining mark) | Visually identical yet different UTF-8 bytes |
| Newline | `\n` (LF) | `\r\n` (CRLF) | Signed bytes differ |
| BOM | No UTF-8 BOM | With BOM | Input bytes differ |
| JSON | `{"a":1,"b":2}` | `{"b":2,"a":1}` | Field ordering differs |
| JSON whitespace | `{"a":1}` | `{ "a": 1 }` | Bytes differ; signatures do not strip whitespace |
| Decimal | `125.50` | `125.5` or `1.255E2` | Different textual representations |
| Timestamp | UTC `2026-10-31T12:00:00Z` | `2026-10-31T19:00:00+07:00` | Same instant, different strings |
| Collection | Unordered `HashMap` | `SortedMap` / schema-ordered | Serialization output differs |
| Boolean/null | `false`/null written explicitly | Field omitted | Schema differs |
| HTTP request | Different query param / percent-encoding | Different header whitespace / path | Signature input differs |
| File | Raw bytes | Text parsed and re-written | Parser may alter encoding/newlines/formatting |

**Note:** Not every system needs canonicalization to make variants equal. If you sign **raw file bytes**, every byte of the file is the intended protected data: never normalize newlines or Unicode when verifying, as doing so alters the message the author signed.

### 3.2. Canonicalization is a protocol contract

Parties must lock down **data representation rules** *before signing*: which bytes, in what order and format, whether to canonicalize or keep raw bytes, UTF-8 rules, schema version, missing-field handling, and numeric types.

Two distinct choices:

1. **Sign raw bytes:** suitable for binary files, raw HTTP bodies, firmware. Both sides preserve exact bytes; never parse and re-serialize.
2. **Sign a canonical representation of structured data:** suitable for orders, transactions, business messages. Both sides must run the **exact same canonicalization algorithm** to reconstruct identical bytes before verification.

If a protocol requires signing JSON, never rely on `Map.toString()`, accidental `HashMap` iteration order, custom serializer defaults, or “usual” key order. You may reference an explicit canonical JSON standard such as **RFC 8785 (JCS)** where appropriate, mindful of its constraints on numbers and data sets. Java SE 17 **does not ship a built-in general-purpose canonical JSON API**.

Canonicalization must be **versioned** and tested across Unicode, null/optional fields, large numbers, escaping, time zones, and cross-language serializers; never rely on a single trivial JSON example.

## 4. Designing a solid signed-data contract

A transaction-signing protocol should specify at least:

| Component | Rules to state explicitly |
| --- | --- |
| **Purpose/domain** | E.g., `com.example.payment.approve/v1`; distinguishes approval signatures from refund/cancel |
| **Message schema/version** | Field names, types, required vs. optional/null, serialization algorithm version |
| **Field order** | Fixed order or defined canonical ordering |
| **Binary frame** | Length-prefix, fixed width, endianness, delimiters/escaping to avoid ambiguity |
| **Text encoding** | UTF-8; whether Unicode NFC/NFD applies; newline and BOM handling |
| **Numbers** | Currency unit, decimal places, stripping/preserving leading/trailing zeros |
| **Date/time** | UTC timestamp format or epoch integer with explicit unit |
| **Algorithm** | `SHA256withRSA`/`RSASSA-PSS`/`Ed25519`; PSS parameters, signature format |
| **Key identity** | Key ID/certificate and separate trust policy; never trust a client-claimed `keyId` |
| **Context** | User/tenant, object ID, action, API version, nonce, expiry, or sequence number |
| **Verification** | Obtain the *exact signed bytes*, check signature, key trust, and authorization/replay |

### 4.1. Avoiding unframed string concatenation

Dangerous pattern:

```text
serialize(a,b) = UTF8(a + b)

("ab", "c") -> "abc"
("a", "bc") -> "abc"
```

Two distinct field pairs collapse into the **exact same message bytes**, so **one valid signature** could be reinterpreted as a different transaction if one side allows shifting field boundaries. This is an *ambiguous serialization* vulnerability, not a flaw in SHA-256.

A clearer approach:

```text
VERSION || len(field1) || field1 || len(field2) || field2 || ...
```

Where `len` counts **encoded bytes**, not Java's `String.length()`; use fixed-width integers (e.g., 4-byte big-endian), enforce per-field max lengths, fixed field order, a domain marker, and a schema version. The receiver must parse strictly per the matching schema and reject duplicate fields or ambiguous encodings.

### 4.2. Domain separation: which action is the signature for?

Suppose the same key is used for two operations: `approve` and `refund`. If both APIs sign the same generic JSON without an operation code, a signature could be replayed at the other endpoint (depending on endpoint logic) and misinterpreted.

Include an agreed **domain/purpose** in the signed bytes, for example:

```text
"com.example.payment/approve/v1" || orderId || amount || currency || tenantId
```

Fields must use unambiguous encoding/framing; this is only conceptual notation. The verifier must enforce the **domain** matching the active endpoint, right tenant, right action, right object, and all attributes capable of altering business outcomes.

Never reuse the same message bytes/signature for another protocol unintentionally. Domain separation protects the **meaning** of a signature beyond byte-level integrity.

### 4.3. Ordering and units of currency and timestamps

Never sign `double` values for money when two systems need independent textual representations. Choose `BigDecimal` with an exact scale/rounding rule or integer minor units such as cents or VND. For example, `BigDecimal("125.50").setScale(2, RoundingMode.UNNECESSARY).toPlainString()` produces `"125.50"`; never use locale-dependent `NumberFormat` in a byte contract.

Dates and times should follow an explicit convention such as UTC epoch milliseconds as a `long`, or ISO-8601 UTC with fixed precision and formatting. `Instant.toString()` can vary in fractional-second length across cases; for interoperable protocols, share test vectors rather than assuming all ISO strings match.

### 4.4. Unicode and normalization must be agreed upon

In Java:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
```

This is a snippet requiring `import java.nio.charset.StandardCharsets;` and a defined `text`. Calling no-arg `getBytes()` depends on the default charset by JDK version and environment; always specify UTF-8 for cross-platform protocols.

Unicode can represent visually identical strings using different code points—for instance, a precomposed character vs. a base character plus combining mark. If the contract mandates NFC, both sides must invoke an equivalent NFC rule **before encoding**. However, **never normalize raw file contents or identifiers** unless the protocol permits it: normalization can alter data or identifier behavior.

## 5. Exactly how should `java.security.Signature` be called?

With `SHA256withRSA`, the standard flow is:

1. Select an algorithm approved by protocol/policy.
2. Produce the **single canonical signed-byte array** from a canonical serializer or raw bytes.
3. `Signature.getInstance("SHA256withRSA")`.
4. `initSign(privateKey)`, then `update(messageBytes)`, then `sign()`.
5. Transmit/store the signature with the info needed to locate the exact message/schema/algorithm/key in an authenticated format.
6. Receiver reconstructs the exact `messageBytes`, calls `initVerify(publicKey)`, `update(messageBytes)`, and `verify(signature)`.
7. Only after successful verification and trusted key identity should authorization, expiration, replay controls, and business policy be enforced.

`Signature.update(byte[])` expects **message bytes**, not a “digest placeholder.” `verify` returns a boolean; depending on the case, a malformed signature or provider issue may throw `SignatureException` instead of returning false, so handle errors safely.

### 5.1. `MessageDigest` is a different API

`MessageDigest.getInstance("SHA-256")` provides an unkeyed hash for computing a data digest/fingerprint. It does not prove the signer holds a private key; anyone can hash public data.

```java
byte[] digest = MessageDigest.getInstance("SHA-256")
        .digest(messageBytes);
```

This snippet requires `import java.security.MessageDigest;`. After computing a digest for audit purposes, if the signature algorithm is `SHA256withRSA`, you still pass **`messageBytes`** to `Signature.update`; do not pass `digest` unless the protocol explicitly specifies signing a **digest-as-message** with dedicated semantics.

### 5.2. There is no “default signature algorithm”

Java requires `Signature.getInstance(algorithm)`. Java 17 has no universal default signing mode suited to every key type. Pick the name according to key type and policy, for example:

| `Signature` algorithm | Digest handled by scheme? | Important characteristics |
| --- | --- | --- |
| `SHA256withRSA` | **Yes**, SHA-256 | RSA PKCS#1 v1.5 signature scheme; commonly used for compatibility |
| `RSASSA-PSS` + `PSSParameterSpec` SHA-256 | **Yes**, per PSS config | MGF1 hash, salt length, and trailer must match; PSS introduces randomness into signatures |
| `SHA256withECDSA` | **Yes**, SHA-256 | ECDSA signature, typically DER encoded per provider/API; separate `inP1363Format` variant exists |
| `Ed25519` | Internal EdDSA hashing, **not `SHA256with...`** | Signs message bytes directly per Ed25519; do not pre-hash with SHA-256 |
| `NONEwithRSA` / `NONEwithECDSA` | No integrated digest per algorithm name | Use only when protocol/provider precisely defines input and encoding; not an automatic fix |

**Never use MD5/SHA-1 to create new signatures.** Provider support for an algorithm does not mean modern security policies allow it; consult deprecation lists and environment compliance requirements.

## 6. Java 17+ program: proper signing, erroneous double hashing, and Ed25519

The program below demonstrates a **deterministic** signing protocol for a payment approval request. We build a byte sequence from **domain + orderId + amount + currency**, then sign it with `SHA256withRSA`. Simultaneously, the program intentionally signs pre-hashed data to show that such a signature only verifies if the receiver makes the exact same input mistake.

**Note:** RSA-2048 is generated in memory purely for the demo; the public key is taken from the same key pair. The program does not address certificate trust, key storage, authorization, replay, signature envelope versioning, or real payments. No fixed key or signature values are printed.

Create **`SigningBytesDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.text.Normalizer;
import java.util.Arrays;

public class SigningBytesDemo {
    private static void writeField(DataOutputStream out, String value)
            throws IOException {
        byte[] utf8 = Normalizer.normalize(value, Normalizer.Form.NFC)
                .getBytes(StandardCharsets.UTF_8);
        // Big-endian 4-byte length prefix + UTF-8 data.
        out.writeInt(utf8.length);
        out.write(utf8);
    }

    // Returns canonical bytes for an action belonging to the specified domain.
    private static byte[] canonicalPayment(
            String orderId, BigDecimal amount, String currency)
            throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        writeField(out, "com.example.payment/approve/v1");
        writeField(out, orderId);
        writeField(out, amount.setScale(2, RoundingMode.UNNECESSARY)
                .toPlainString());
        writeField(out, currency);
        out.flush();
        return bytes.toByteArray();
    }

    private static byte[] sign(PrivateKey key, byte[] message)
            throws Exception {
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(key);
        signer.update(message); // Engine performs SHA-256(message) internally.
        return signer.sign();
    }

    private static boolean verify(
            PublicKey key, byte[] message, byte[] signed)
            throws Exception {
        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(key);
        verifier.update(message);
        return verifier.verify(signed);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();

        byte[] message = canonicalPayment(
                "ORDER-104", new BigDecimal("125.50"), "VND");
        byte[] rebuilt = canonicalPayment(
                "ORDER-104", new BigDecimal("125.5"), "VND");

        byte[] signature = sign(pair.getPrivate(), message);
        System.out.println("canonicalBytesEqual=" +
                Arrays.equals(message, rebuilt));
        System.out.println("signatureValid=" +
                verify(pair.getPublic(), rebuilt, signature));

        // Same schema, different amount => different bytes => verification fails.
        byte[] changed = canonicalPayment(
                "ORDER-104", new BigDecimal("125.51"), "VND");
        System.out.println("changedAmountRejected=" +
                !verify(pair.getPublic(), changed, signature));

        // BUG: calling SHA-256 externally and then signing with SHA256withRSA.
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(message);
        byte[] doubleHashedSignature = sign(pair.getPrivate(), digest);

        System.out.println("wrongDigestSignatureRejectsOriginal=" +
                !verify(pair.getPublic(), message, doubleHashedSignature));
        System.out.println("wrongDigestSignatureAcceptsDigest=" +
                verify(pair.getPublic(), digest, doubleHashedSignature));
        System.out.println("originalSignatureRejectsDigest=" +
                !verify(pair.getPublic(), digest, signature));

        // Ed25519 also takes canonical message bytes; do not prehash.
        KeyPairGenerator edGenerator =
                KeyPairGenerator.getInstance("Ed25519");
        KeyPair edKeys = edGenerator.generateKeyPair();
        Signature edSigner = Signature.getInstance("Ed25519");
        edSigner.initSign(edKeys.getPrivate());
        edSigner.update(message);
        byte[] edSignature = edSigner.sign();

        Signature edVerifier = Signature.getInstance("Ed25519");
        edVerifier.initVerify(edKeys.getPublic());
        edVerifier.update(message);
        System.out.println("ed25519Valid=" +
                edVerifier.verify(edSignature));
    }
}
```

Compile/run with a standard JDK 17+ supporting RSA and Ed25519:

```shell
javac SigningBytesDemo.java
java SigningBytesDemo
```

**Expected stdout:**

```text
canonicalBytesEqual=true
signatureValid=true
changedAmountRejected=true
wrongDigestSignatureRejectsOriginal=true
wrongDigestSignatureAcceptsDigest=true
originalSignatureRejectsDigest=true
ed25519Valid=true
```

### 6.1. Why are these lines deterministic?

- `canonicalBytesEqual=true`: both `125.50` and `125.5` become `125.50` thanks to `setScale(2, RoundingMode.UNNECESSARY)`. `writeField` applies identical NFC, UTF-8, field ordering, and length-prefix rules.
- `signatureValid=true`: RSA signs the canonical message, and the verifier uses the reconstructed canonical message; the bytes match.
- `changedAmountRejected=true`: changing `125.50` to `125.51` produces a different message; the valid signature for the original value fails on the modified content.
- `wrongDigestSignatureRejectsOriginal=true`: a buggy signature (signing a digest with an algorithm that already computes SHA-256) **is invalid** when the verifier behaves properly and supplies the original message bytes.
- `wrongDigestSignatureAcceptsDigest=true`: both sides passed the digest as the message into `SHA256withRSA`; `verify` still returns **true**, demonstrating why “green tests” do not prove protocol compliance.
- `originalSignatureRejectsDigest=true`: a valid signature over the message does not verify when the verifier mistakenly feeds digest bytes as input.
- `ed25519Valid=true`: Ed25519 takes the exact canonical message bytes; the algorithm handles its internal procedure per spec, with no extra `MessageDigest("SHA-256")` step added by the application.

Because RSA and Ed25519 key pairs are randomly generated on each run, no concrete signature bytes appear in the expected stdout. These booleans remain independent of actual key and signature values when the JDK/provider implements the standards properly.

### 6.2. The demo is not a production canonical protocol

`writeField` and `canonicalPayment` are merely an **illustrative format**. A real implementation must enforce maximum field sizes, validate currency types/codes, handle null/empty values, unify Unicode normalization, and manage versioning. Real payments must also include account/tenant, identifier, action, replay nonce/expiry, and every field affecting business outcomes in the signed data.

Using a sample domain name does not make an application a secure payment system; decisive factors also include who issues and trusts public keys, signing authority, authorization, key storage, replay defense, auditing, expiration limits, and protocol interoperability.

## 7. Handling large files and streaming with `Signature.update`

For large files, there is no need to load the entire file into RAM and **no need to manually SHA-256 the file and feed the digest to `SHA256withRSA`**. Java allows calling `update` repeatedly on sequential byte chunks:

```java
Signature signer = Signature.getInstance("SHA256withRSA");
signer.initSign(privateKey);

try (InputStream in = Files.newInputStream(path)) {
    byte[] buffer = new byte[8192];
    int read;
    while ((read = in.read(buffer)) != -1) {
        if (read > 0) {
            signer.update(buffer, 0, read);
        }
    }
}
byte[] signature = signer.sign();
```

This is a **non-standalone snippet**: it requires imports `java.security.Signature`, `java.io.InputStream`, `java.nio.file.Files`, and valid `privateKey` and `path` variables inside an exception-handling method. The verifier opens the **exact original file bytes** and calls `Signature.update(buffer, 0, read)` in order, followed by `verify(signature)`. Splitting into 8192-byte chunks or any other size **does not change** the message stream as long as order and bytes are identical; the engine maintains internal digest state for algorithms with digests.

Important rules when signing files:

- Do not strip zero bytes, newlines, BOMs, or metadata that genuinely belong to the signed file scope.
- Do not read a file once to hash it and then inadvertently read a modified file to sign: under concurrency/snapshot threats, guarantee the signed data is the exact version published.
- Never issue a signature for file A and then publish file B whose contents changed after signing.
- For binary files, prefer signing raw bytes; if signing a manifest of hashes, define the manifest structure and verification checks explicitly.

### 7.1. Signing file hashes in a manifest vs. signing files directly

Suppose you have a list of artifacts:

```text
manifestVersion = 1
artifactA.sha256 = H(rawArtifactA)
artifactB.sha256 = H(rawArtifactB)
metadata = product, version, size, path, ...
signature = Sign(canonicalManifestBytes)
```

Here, **`canonicalManifestBytes`** is the signed message; the manifest contains the file digests. If `Sign` uses `SHA256withRSA`, it computes SHA-256 over the **manifest**, which is not buggy double hashing if that is the agreed protocol.

The receiver must: verify the manifest signature using a trusted public key → safely parse the manifest → recompute each artifact's digest and compare → enforce path, version, scope, and policy constraints. Verifying only the manifest without checking the artifacts leaves the integrity flow incomplete.

## 8. Real-world exception: HSM/KMS or prehashed-input signing APIs

Some interfaces expect **message bytes**, while others expect a **precomputed digest**. Especially when working with PKCS#11, HSMs, KMS, cloud APIs, or third-party SDKs, read the **specific contract** instead of guessing from a method named `sign`.

### 8.1. Two API types that must never be mixed

**Type A – sign message:**

```text
Input: raw/canonical M
Algorithm: SHA256withRSA (SHA-256 computed internally)
Output: signature per scheme
```

**Type B – sign prehashed digest:**

```text
Input: H(M), exact length per algorithm
Algorithm/service: API specifies input is PREHASHED DIGEST
Output: signature corresponding to M per specified scheme
```

In Type B, the service *may* construct the proper `DigestInfo`/padding or PSS encoding for the client-supplied digest, or follow another provider-specific contract; never assume it merely calls `Signature("SHA256withRSA").update(digest)` on the server. You must confirm the **exact digest scheme, digest length, parameter spec, encoding, padding, key type, wire format**, and provider test vectors.

A field like `messageType = DIGEST` in some API only carries meaning where that API's documentation defines digest handling. Never map that concept onto Java `Signature`, because JCA `update(...)` **has no flag saying “the input is already a digest.”**

### 8.2. Specifically for RSA/PKCS#1 v1.5

An RSA PKCS#1 v1.5 signature with SHA-256 normally wraps the SHA-256 digest in **DigestInfo** before applying the signature primitive. **Raw RSA modular exponentiation of a 32-byte digest is not equivalent to `SHA256withRSA`**. Prehashing manually and picking `NONEwithRSA` does not guarantee the provider encodes `DigestInfo` properly or interoperates with the other party.

The safe practice in JCA is normally: **pass the original message bytes to `SHA256withRSA`**. When forced to use a digest-accepting API, the protocol must clarify whether the SDK builds `DigestInfo` and padding or which part the HSM performs. Never hand-roll RSA padding or encoding when vetted libraries/schemes exist.

### 8.3. RSA-PSS: parameters that must align

RSA-PSS requires knowing more than “SHA-256.” Signer and verifier must agree on:

- message digest, e.g., SHA-256;
- MGF algorithm (typically MGF1) and MGF1 digest;
- salt length, e.g., 32 bytes;
- trailer field and PSS signature format.

Illustrative Java 17 configuration example:

```java
PSSParameterSpec spec = new PSSParameterSpec(
        "SHA-256", "MGF1", MGF1ParameterSpec.SHA256, 32, 1);
Signature pss = Signature.getInstance("RSASSA-PSS");
pss.setParameter(spec);
pss.initSign(rsaPrivateKey);
pss.update(canonicalBytes);
byte[] signature = pss.sign();
```

This is **not a standalone program**: it requires `java.security.Signature`, `java.security.spec.PSSParameterSpec`, `java.security.spec.MGF1ParameterSpec`, an RSA private key, and message bytes; providers may have specific requirements on support/configuration order. Notably, with `RSASSA-PSS` configured for SHA-256, the application **does not prehash M before calling `update`**. The verifier uses `initVerify` and the **exact same parameters** with identical canonical bytes.

Two RSA-PSS signatures of the same message can have **different signature bytes** due to the random salt while both verify true. Hence a test asserting “PSS signature must equal the bytes from the last signing call” is invalid; test via `verify` and controlled standard vectors.

### 8.4. ECDSA: same digest, yet signature encoding can differ

`SHA256withECDSA` hashes the message with SHA-256 internally per the scheme. However, the signature representation may be **ASN.1 DER** (DER-encoded `(r, s)` pair) or **IEEE P1363 fixed-width** depending on algorithm name/contract. Both sides can sign the same `M`, with the same key and SHA-256, yet expect **different signature byte formats**.

When integrating Java, OpenSSL, JWT/JWS, HSMs, or other SDKs, do not ask only “is it ECDSA SHA256?”; verify **DER vs. P1363/raw `r||s`**, curve, key format, and contract. **Never** use `NONEwithECDSA` instead of `SHA256withECDSA` without understanding the provider's raw/prehashed contract.

### 8.5. Ed25519: do not add SHA-256 yourself

`Ed25519` is an EdDSA scheme defining precisely how messages are processed and hashed internally. `Ed25519ph` is a *prehash* variant with distinct domain separation and is **not equivalent** to taking SHA-256 of `M` and calling Java `Ed25519.update(digest)`. Java 17 `Signature.getInstance("Ed25519")` normally takes `M` directly; if a protocol requires a prehashed variant, use an implementation genuinely supporting that standard rather than simulating it with `MessageDigest`.

**Mandatory integration questions:** Does the API take **message** or **digest**? Do exact algorithm, params, prehash variant, signature encoding, and byte canonicalization match?

## 9. Do not decouple the algorithm from data structure and authorization checks

A signature requires an explicit **verification context**. At minimum, a signed envelope may contain:

```text
version
message-type/domain
canonicalization-id
payload or stable payload reference
signature-algorithm and parameters
signing-key-id / certificate chain reference
signature bytes
timestamp / nonce / request-id if protocol requires
```

Outer fields may be needed to decide how to parse, yet they are **not automatically integrity-protected**. If an attacker can alter `algorithm`, `domain`, `keyId`, `canonicalizationId`, or payload references to manipulate verification/processing, the design must enforce an **allowlist and metadata authentication bindings**, typically incorporating critical fields inside the signed message itself or protecting them per a standardized format.

### 9.1. Verifiers validate more than the signature

Proper verification workflow:

1. Enforce packet structure/size bounds and accepted versions to avoid parse ambiguity/DoS.
2. Determine the expected **domain/action** from the actual endpoint; never trust a client-modifiable claim like `"operation=approve"`.
3. Reconstruct the **exact message bytes** per the canonicalization version; confirm all critical fields are included in the input.
4. Select the algorithm and public key per **server-side policy/allowlist**, verifying that `keyId`/certificate belongs to an approved identity.
5. Invoke `Signature.initVerify`, `update(M)`, `verify(S)`; treat any mismatch/exception as an appropriate verification failure.
6. Validate **trust chain, validity, certificate usage, and revocation policy** when using PKI; a valid signature under an anonymous public key does not prove who signed.
7. Check business authorization (is the signer permitted to approve this item?), tenant/object binding, expiry, and nonce/sequence/replay controls.
8. Only after all required checks pass should side effects/writes occur; emit appropriate audit logs without exposing private keys.

**Signatures do not prevent replay automatically**: an identical valid message and signature can be re-sent. Putting a timestamp/nonce into the signed payload must be paired with **expiration and unused-state checks** on the verifier.

### 9.2. Signatures do not encrypt data

A signature verifies integrity and private-key possession, **not message confidentiality**. A signed JSON payload remains readable if transmitted in the open. When confidentiality is needed, use TLS or proper encryption/AEAD separately from the signature.

## 10. Integrating HTTP request/JSON signing: an explicit contract

An HTTP signing protocol might sign:

```text
METHOD + "\n" +
CANONICAL_PATH + "\n" +
CANONICAL_QUERY + "\n" +
CANONICAL_HEADERS + "\n" +
BODY_DIGEST + "\n" +
TIMESTAMP + "\n" +
NONCE
```

**This is a conceptual structure example, not a standard HTTP signature specification for direct production use.** The protocol must explicitly specify canonical path, percent-encoding, query key sorting, duplicate query params, header trimming, host, newlines, charset, method casing, whether body bytes or digest are signed, timestamp bounds, nonces, and which headers are protected.

If the protocol **explicitly defines `BODY_DIGEST = SHA256(rawBody)` as a field**, signing the canonical request containing that field with `SHA256withRSA` is valid: the signer signs the **canonical request bytes**, and the engine computes SHA-256 over the whole request. This is **different** from taking `SHA256(canonicalRequest)` and feeding that digest into an engine that already runs SHA-256.

Likewise, if signing canonical JSON per RFC 8785, signer and verifier must share the same standard/version and be especially careful with numeric values outside JSON number ranges supported by the spec. For financial data, signing a dedicated byte schema with decimal-string/minor-unit amounts is often preferable to applying generic canonical JSON without checking its bounds.

### 10.1. Cross-system test vector synchronization

To test Java ↔ JavaScript/Python/Go/HSM, prepare an agreed test vector suite containing:

- **Input business fields** and the meaning of each field.
- **Canonical bytes** in hex/Base64 and exact byte length.
- **Digest of the canonical bytes** in hex solely for diagnostics, never as input to a combined `Signature`.
- **Fixed test algorithm/key/public key/cert**, plus RSA-PSS parameters or ECDSA encoding if applicable.
- **Expected signature** when the scheme is deterministic under matching conditions, or **expected verification result** for randomized schemes.
- Negative cases: 1-byte diff, changed order/amount/tenant/domain, Unicode NFC vs. NFD, LF vs. CRLF, null/empty, JSON key ordering, timestamp format, unknown version, altered `keyId`, and replay.

On mismatch, compare **canonical bytes first**, then algorithm/params/key and signature format. Do not waste time suspecting the provider when one side signs UTF-8 LF and the other signs UTF-16LE CRLF.

## 11. Common errors and troubleshooting guide

| Symptom | What to check | Typical root cause |
| --- | --- | --- |
| Java signs and self-verifies true, peer returns false | Canonical byte arrays on **both sides**, algorithm/params, signature encoding | Sides sign different bytes, or one prehashes while the other does not |
| `SHA256withRSA` receives 32-byte digest and peer verification fails | Who called `MessageDigest` before `Signature.update`? | Double hashing / inconsistent input |
| Same displayed payload, verification fails | UTF-8, Unicode NFC, newlines, BOM, number/date format, JSON ordering | Displayed text matches while underlying bytes differ |
| ECDSA signature fails to verify | DER vs. P1363 signature; curve/format/key | Different signature wire formats |
| RSA-PSS reports invalid signature | Digest, MGF1 hash, salt length, trailer, provider | Mismatched PSS params or wrong signed input |
| Java Ed25519 does not match peer | Pure Ed25519 or Ed25519ph? Manual SHA-256 beforehand? | Confused scheme / prehash variant |
| `InvalidKeyException` | Private/public key type vs. chosen algorithm | RSA key passed to ECDSA algorithm or key/provider mismatch |
| `NoSuchAlgorithmException` | Runtime/provider and algorithm name | Provider does not support the specified algorithm name |
| `SignatureException` during verify | Signature bytes, length, format/provider | Malformed signed data or wrong signature encoding |
| Verify true yet business logic wrong | Signed fields and signer permissions | Omitted amount, tenant, action, expired request, replay |
| Changing a field still verifies true | Is that field actually inside canonical bytes? | Critical business data omitted from signature scope |
| Test comparing two PSS/ECDSA signatures fails | Algorithm uses randomness in signing nonce/salt | Test with `verify`, never compare signature bytes |
| Signature valid with an unknown key | Trust store/PKI, key↔identity binding | Public key not authenticated as belonging to an authorized entity |

### 11.1. Effective debugging steps

1. Print the **byte length** of the canonical message on both sides, and a hash fingerprint of canonical bytes **only in controlled environments**. Never log sensitive plaintext, secrets, keys, or tokens.
2. When debugging in tests, compare canonical bytes in hex/Base64 or binary diff to pinpoint the first differing byte; ensure test data is harmless.
3. Inspect `Signature.getAlgorithm()`, `getProvider()`, and `PSSParameterSpec` where applicable.
4. Check public key type, curve, certificate chain, and signature encoding.
5. Write negative tests for business-critical fields to verify they are genuinely covered by the signed data.
6. If failures occur only on Unicode or decimal data, inspect normalization, encoding, and canonical schema before changing algorithms.

**Never** “fix verify false” by adding an extra hash on the receiver until it returns true. That masks a protocol mismatch. Instead, identify the exact canonical input the protocol intends to protect and align both signing and verification contracts.

## 12. Self-check questions and answers

**1. With `Signature("SHA256withRSA")`, should `update` receive the message or the digest?**  
In standard usage, pass the **raw/canonical message bytes**, because the engine already handles SHA-256. Pass a digest only if a digest itself is defined as the signed message, or a dedicated API has an explicit prehash contract; never treat `Signature.update` as a prehash API.

**2. If both signer and verifier call `SHA256(M)` and then use `SHA256withRSA`, does `verify == true` prove correctness?**  
No. Both sides agree on signing `H(M)` as the message—yielding `H(H(M))` internally—which violates the protocol contract if the contract specifies signing `M`.

**3. Why shouldn't you concatenate `orderId + amount + currency` and sign?**  
Field boundaries can be ambiguous and number formatting unfixed; you need explicit ordering, length-prefixing/escaping, schema, and representation.

**4. Should you sign JSON-like text from `HashMap.toString()`?**  
No. Relying on `Object.toString()` formatting and `Map` iteration order does not produce a stable serialization protocol. Choose a canonical serializer or sign raw bytes per contract.

**5. Can two timestamps representing the same instant with different offsets verify under the same signature?**  
No if their byte strings differ. For equivalence, define a canonical time representation prior to signing.

**6. Does `RSASSA-PSS` with SHA-256 require a separate `MessageDigest.digest(M)` call?**  
No when using Java `Signature("RSASSA-PSS")` with a `PSSParameterSpec` specifying SHA-256; the engine handles the digest per the PSS scheme.

**7. Is Ed25519 the same as `SHA256withEd25519`?**  
No. Ed25519 is its own scheme with internal processing; never pre-hash with SHA-256 before calling `Signature("Ed25519")`.

**8. Does a valid signature under a public key taken from the request prove the sender is trusted?**  
No. You need key/certificate binding validation and authorization; if an attacker generates a key pair and sends their own public key, `verify` returns true for their forged signature.

**9. Do signatures prevent replay?**  
No. You must sign a nonce/timestamp/sequence and check state and time windows on the receiver.

**10. Is signing a manifest containing file hashes always a double-hashing bug?**  
No. The manifest is a distinct message `M`; file digests are **data fields** inside the manifest. Do not confuse signing a manifest with passing `SHA256(manifest)` into a digest-integrated signing API.

**11. Why do two PSS signatures of the same payload have different signature bytes?**  
PSS uses a random salt during signing. Comparing raw signature bytes is an invalid test; verify using the matching algorithm/params/key/message.

**12. When signing a digest via an HSM, can you always just use `NONEwithRSA`?**  
No. You must follow the exact HSM/PKCS#11 contract regarding message vs. digest, padding/DigestInfo/PSS encoding, digest length, and algorithm. Use the official SDK and provider test vectors.

## 13. Production readiness checklist for digital signatures

1. **Define M precisely:** raw bytes or canonical schema? Test vectors specifying byte length, hex, and encoding.
2. **Sign complete context:** domain/purpose, version, user/tenant, action, resource, amount, timestamp, nonce/expiry as needed.
3. **Eliminate serialization ambiguity:** avoid naive string concatenation; enforce field order, types, numeric/time formatting, Unicode, and length prefixes.
4. **Match algorithm to key:** `SHA256withRSA`, `RSASSA-PSS`, `SHA256withECDSA`, `Ed25519`, with compatible params and encodings.
5. **Avoid unintended double hashing:** for digest-integrated `Signature` APIs, pass message bytes; never feed `MessageDigest.digest(M)` to `update`.
6. **Never use raw signature schemes as shortcuts:** prehashed APIs require explicit padding/encoding contracts and test vectors.
7. **Authenticate signer identity:** trust public key/certificate, algorithm allowlist, `keyId` binding, validity/revocation policy, and authorization.
8. **Prevent replay:** sign nonce/time/sequence and enforce verification checks on the verifier.
9. **Operate securely:** protect private keys, prefer keystore/KMS/HSM as needed; never log keys/sensitive messages, and do not expose debug digests publicly if payloads are confidential.
10. **Test cross-system:** success, 1-byte edit, altered domain/tenant/amount, wrong key, wrong params, Unicode, newlines, JSON ordering, replay, and downgrade.

## Authoritative references

- [Java SE 17 – Signature](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html): `initSign/initVerify → update → sign/verify` stages, algorithm names, and engine state.
- [Java SE 17 – MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): standalone hashing and `digest/update` calls.
- [Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): providers, engines, signatures/digests, and Java API model.
- [Java SE 17 – PSSParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/PSSParameterSpec.html) and [MGF1ParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/MGF1ParameterSpec.html): parameters that must align for RSA-PSS.
- [Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): `SHA256withRSA`, `SHA256withECDSA`, `RSASSA-PSS`, `Ed25519`, and variants.
- [RFC 8017 – PKCS #1 v2.2](https://www.rfc-editor.org/rfc/rfc8017): RSA signature schemes and EMSA encoding rules.
- [RFC 8032 – Edwards-Curve Digital Signature Algorithm (EdDSA)](https://www.rfc-editor.org/rfc/rfc8032): Ed25519, Ed25519ph, and prehash/domain separation rules.
- [RFC 8785 – JSON Canonicalization Scheme (JCS)](https://www.rfc-editor.org/rfc/rfc8785): one specification for canonical JSON, with its scope and representation constraints.