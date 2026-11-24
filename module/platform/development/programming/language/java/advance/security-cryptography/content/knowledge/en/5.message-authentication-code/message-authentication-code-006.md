# 5.6 Tag Verification, Tampered Data, Wrong Keys, and Tag Truncation Limits

A Java application receives a message along with a byte sequence called a **tag**. To decide whether to trust the content, the application must compute or verify the tag using **the right algorithm, the right key, the right bytes, the right parameters, and the right length**. Missing any of those conditions can cause tampered data to be accepted or valid messages to be rejected.

This lesson focuses on three scenarios: (1) tampered data, tag, or metadata; (2) the verifier using the wrong key; (3) truncated tags or a program accepting tag lengths outside policy. These situations arise in webhook HMACs, service-to-service messaging, AES-GCM protecting stored data, and other message authentication protocols.

After this lesson, you should be able to distinguish a **MAC tag** from an **authenticated encryption (AEAD) tag**; understand the limits of each tag; implement verification with JCA/JCE; write negative tests for bad data, wrong keys, and short tags; and design tag-length rules that never let the sender weaken verification.

## 1. What Is a Tag? What Does a Tag Prove?

### 1.1. MAC tag: using a shared secret to authenticate a message

With a **Message Authentication Code (MAC)**, sender and receiver share a secret key. The sender computes a tag from the key and message; the receiver recomputes it over **the exact received byte sequence** and verifies.

~~~text
Sender                           Receiver
------                           --------
Key K + message M                Key K + message M'
          |                                 |
          v                                 v
      MAC(K, M)                        MAC(K, M')
          |                                 |
       tag T ---------------------->  expected T'
                                             |
                                             v
                                check length + match tag
                                             |
                               valid / reject message
~~~

With a secure MAC algorithm, a protected secret key, and a proper verification flow, a valid tag indicates the content was produced by an entity **knowing the shared key**, and that the content was not modified in a way that bypasses the MAC mechanism. Because both parties hold the key, HMAC does not tell a third party which specific side created the tag.

**HmacSHA256** in JCA produces a full output of **32 bytes = 256 bits**. A protocol may choose a fixed leading prefix of the tag by design and security bounds, but must never let the client specify the comparison length arbitrarily.

### 1.2. AEAD tag: verifying encrypted data before using it

With **Authenticated Encryption with Associated Data (AEAD)** such as AES-GCM, the encryptor uses a key, IV/nonce, plaintext, and optionally AAD to produce **ciphertext together with an authentication tag**. The decryptor must verify the tag via the AEAD algorithm itself. If the tag is invalid, decryption is rejected.

~~~text
AES-GCM encrypt:
  key + IV + plaintext + AAD
              |
              v
       ciphertext || tag

AES-GCM decrypt:
  key + IV + ciphertext || tag + AAD
              |
              v
       verify tag via Cipher.doFinal()
              |
       success: authenticated plaintext
       failure: do not use plaintext
~~~

In JCE, **Cipher.getInstance("AES/GCM/NoPadding")** and **GCMParameterSpec** select the transformation and tag length; **Cipher.doFinal** checks the authentication tag during decryption. Authentication failure typically throws **AEADBadTagException**. Do not use MessageDigest.isEqual to replace the GCM verification inside Cipher.

### 1.3. Distinguishing from SHA-256, digital signatures, and checksums

| Mechanism | Has Secret Key? | What Can It Verify? | What Does It Not Solve Automatically? |
| --- | --- | --- | --- |
| Plain SHA-256 | No | Data fingerprint; useful when the reference digest comes from a trusted source | Anyone altering the message can recompute the hash; does not authenticate sender. |
| CRC/checksum | No | Detects certain accidental/transmission errors | Does not resist an active adversary modifying data. |
| HMAC-SHA256 | Yes, shared key | Integrity and authentication of a key-holding party | Does not encrypt content, prevent replay, or attribute solely to one key holder. |
| AES-GCM tag | Yes, AEAD key | Authenticates ciphertext and AAD alongside plaintext confidentiality | Does not check user authorization, nor prevent replay of valid ciphertext. |
| Digital signature | Private key to sign, public key to verify | Integrity and signing origin when the public key is authenticated | Does not keep content confidential by itself and does not replace authorization checks. |

**A valid tag does not mean the business request is authorized to execute.** It only proves specific cryptographic properties for the key, algorithm, and protected bytes. For instance, a payment webhook with a valid HMAC may still be an already-processed webhook or a replayed request.

## 2. Prerequisites for Correct Tag Verification

Tag comparison is meaningful only when both sides agree on a **cryptographic contract**.

| Component | What Must Be Agreed Upon | Consequence When Wrong |
| --- | --- | --- |
| Algorithm | HmacSHA256, AES-GCM, GMAC, or protocol-specified algorithm | Computes a different tag or fails API initialization. |
| Key and version | Correct secret/key ID, usage permission, right version after rotation | Tag mismatch; sometimes reports wrong key on a valid message. |
| Input bytes | UTF-8, field order, spaces, line endings, canonicalization, raw body | Same business meaning yet different tag. |
| Authenticated metadata | Message type, tenant, version, timestamp, nonce, AAD | Attacker can alter fields left outside tag protection. |
| Tag format | Raw bytes, hex, Base64/Base64url, tag placement, padding rules | Mis-decoding, dropped leading zero bytes, or wrong length. |
| Tag length | Fixed policy per protocol/key version | Accidental truncation breaks; silently shrinking length adds forgery risk. |
| AEAD IV/nonce | IV matching the ciphertext, length, and per-key uniqueness rule | Bad tag or catastrophic security failure if IV is reused. |
| Processing order | Parse → policy checks → verify → business execution | Trusting unauthenticated data or returning info-leaking errors. |

In particular, a MAC is computed over **bytes**, not an abstract Java object. Two JSON strings with the same fields but different field orders, whitespace, escaping, Unicode, or line endings can yield different tags. For webhooks, if the provider docs require HMAC over the **raw request body**, preserve the raw bytes instead of parsing JSON and re-serializing.

Avoid building payloads by naively concatenating fields like "a" + "bc" and "ab" + "c": two distinct field tuples can produce the exact same byte sequence. Use deterministic serialization, length prefixes, or a protocol-recognized canonical format.

## 3. Safe Verification Pipeline

A tag verification pipeline should follow an easily auditable order:

1. **Treat incoming data as untrusted.** Bound request size, validate envelope format, accept only allowlisted versions/algorithms/key IDs.
2. **Decode the tag representation once** under a fixed rule (e.g., Base64url). Decoding errors, missing fields, or garbage data must be rejected; never "fix up" a tag to make it valid.
3. **Check the length policy before comparing.** For HMAC-SHA256-128, the tag must be **exact 16 bytes after decoding**; never treat Base64/hex character count as byte count.
4. **Select a trusted key** by configured version, tenant, or partner. An external key ID must never unlock an arbitrary key or downgrade the algorithm to a weak one.
5. **Prepare the exact protected bytes.** For HMAC, that is the spec-defined message; for AES-GCM, supply the exact IV, AAD, ciphertext, and tag.
6. **Verify using the proper primitive.** For HMAC, compute the expected tag per policy and compare while limiting timing leaks; for AEAD, let **Cipher.doFinal** verify the tag.
7. **On failure, reject before using content.** Never fall back from a long tag to a short tag, never return plaintext after GCM fails, and never try multiple canonicalizations until one matches.
8. **On success, proceed to freshness, replay, authorization, and business checks.** A tag does not prove the transaction was not already processed, that the resource belongs to the caller, or that the timestamp is still fresh.

~~~text
Receive message/tag
    |
    v
Check format + version + tag length + key ID
    |
    +-- invalid --> REJECT
    |
    v
Select valid key + prepare exact bytes/AAD
    |
    v
Verify MAC or AEAD tag
    |
    +-- invalid --> REJECT (do not use content)
    |
    v
Check replay / timestamp / authorization / idempotency
    |
    +-- invalid --> REJECT
    |
    v
Execute business logic
~~~

**There is no "half-verified."** All verifications must complete before accepting or executing protected data/operations.

## 4. Tampered Data: What Modifications Must Be Detected?

Suppose the sender computes an HMAC over the bytes corresponding to **order=42;amount=250000**. Later someone alters the amount, swaps the order ID, changes the timestamp, or modifies the tag itself.

| Change in Transit | Expected Outcome | Notes |
| --- | --- | --- |
| Flip a byte in the HMAC-protected message | Reject | Recomputing with the right key differs from the received tag, aside from negligible forgery probability per tag length. |
| Flip a byte in the tag itself | Reject | Tag comparison must check **the entire required length**. |
| Alter metadata bound into HMAC/AAD | Reject | If metadata is outside the authentication scope, the tag **does not protect** that field. |
| Change charset/serialization between sides | Reject tag, even if users see "identical" content | This may be a protocol bug rather than an attack. |
| Alter IV/ciphertext/AAD/tag of AES-GCM | Reject decryption | Let AEAD verify the tag; wrong IV or key can produce the same failure. |
| Replay old unmodified message and tag | Tag may still verify | Anti-replay requires timestamps, nonces, transaction IDs, and business state, tag-protected when relevant. |

**The protection boundary must match the trust boundary.** If HMAC covers only the body while the system trusts an unprotected tenant-id header, an intermediary can alter tenant-id while the tag stays valid. With AEAD, unencrypted metadata that still needs authentication (such as record type, version/tenant) can be placed in **AAD** under exact rules.

### Distinguishing tamper detection from content recovery

Tag verification answers **"is this content valid under the key/protocol?"**, rather than repairing corrupted content. When verification fails, systems typically request retransmission of a valid message or return a controlled error. Never ignore verification failures to "process provisionally" just because part of the message looks readable.

## 5. Wrong Key: Meaning and Common Causes

Using a different key from the tag creator produces a different HMAC or an invalid AEAD tag with overwhelming probability. Even though the symptom resembles data tampering, **a wrong key does not automatically mean an attack**: configuration, key rotation, keystore aliases, or selecting the wrong tenant can also be the cause.

Cases to check:

- **Wrong Key ID:** message specifies key-v2 while verifier picks key-v1; or lookup returns another customer's key.
- **Right ID, different key bytes:** two environments have different secrets, Base64 secret was decoded wrongly, or copy/paste added a newline.
- **Unsynchronized rotation:** sender started using the new key before the receiver distributed/accepted it per policy.
- **Key-purpose separation:** one key should not be mixed across HMAC, encryption, and other protocols without secure key derivation/domain separation.
- **Key handle/provider:** HSM/KMS may manage keys via alias or handle; non-exportable keys are not lost, but the verifier must pick the right key for the right operation.
- **Wrong algorithm or key size:** the API may throw InvalidKeyException right at init, rather than waiting until tag comparison.

**System response:** return a generic public error such as "message authentication failed"; on the operations side, log safely with internally permitted key ID or version, request ID, and technical error category—**never log secrets, sensitive plaintext, or raw tokens**.

### Rotating keys while still verifying old data

An envelope can carry a **key ID/version** defined in the published protocol. The server maps this ID to **the permitted key set**, never following arbitrary URLs/paths or sender-supplied algorithm choices. For stored data, retain the ability to decrypt legacy records until migration or retention expiry. For webhooks, a transition window between old and new keys may exist, but it must be bounded and never silently try unlimited keys or weak algorithms.

When the key is wrong, you cannot "skip tag verification" to decrypt usable data: verification is precisely what stops unauthenticated data from entering business logic.

## 6. How Long Must a Tag Be? Understanding Truncation Correctly

### 6.1. Distinguishing intentional truncation from dropped tag bytes

**Intentional truncation** is when the protocol specifies upfront that both parties use the **leading t bits** of the full MAC output, with fixed t and an accepted security level.

**Unintended byte loss** is when data gets cut off in storage, conversion, logs, Base64, copy/paste, serialization, or network transit. A tag missing bytes **must be rejected**, never treated as a lower-security shorter variant.

Example with HMAC-SHA256:

| Policy | Received Size | How to Verify |
| --- | --- | --- |
| Full HMAC-SHA256 | 32 bytes (256 bits) | Compute full 32 bytes and match all 32 bytes. |
| Protocol-specified HMAC-SHA256-128 | 16 bytes (128 bits) | Compute full 32-byte HMAC, take the **first 16 bytes**, require received tag to be **exact 16 bytes**, then compare. |
| 16-byte protocol, receives 15 bytes | 15 bytes | **Reject immediately**; do not compare first 15 bytes or change policy. |
| 16-byte protocol, receives 0 bytes | 0 bytes | **Reject immediately**; never accept an empty tag. |
| 16-byte protocol, receives 32 bytes | 32 bytes | **Reject**, unless another protocol version is explicitly configured. |

HMAC tag length does not depend on message byte count. HMAC-SHA256 emits a full 32 bytes for empty or long messages alike; truncation is a **protocol policy**, not how short messages are handled.

### 6.2. Why are shorter tags easier to guess?

If a tag has **t sufficiently unpredictable bits** under sound cryptographic assumptions, a single random guess succeeds with probability roughly **2^(-t)**. Over roughly q independent attempts, overall success probability can rise near **q / 2^t** while q is small relative to 2^t. This is only security intuition for an ideal MAC; risk in a concrete mode also depends on message counts, data sizes, nonces, algorithm bounds, and protocol design.

| Tag Length | Byte Count | Guessing Difficulty in Simple Model |
| --- | ---: | --- |
| 32 bits | 4 | Roughly 1 in 2^32 attempts; unsuitable as a default for general applications. |
| 64 bits | 8 | Roughly 1 in 2^64; requires very strict evaluation of forgery budget and key lifetime. |
| 96 bits | 12 | Roughly 1 in 2^96, still subject to algorithm/protocol limits. |
| 128 bits | 16 | Roughly 1 in 2^128 per guess in an ideal model. |
| 256 bits | 32 | Full output of HMAC-SHA256; does not automatically raise overall system security if keys/processes are weak. |

**Do not conclude "a 64-bit tag is always safe" solely from the number 2^64.** A service handling billions of requests, multiple tenants, many keys, or repeated retries must evaluate forgery budgets, rate limits, monitoring, and key lifetimes.

RFC 2104, Section 5, describes HMAC truncation by taking the leftmost bits of the output and gives a historical floor of **not less than half the hash output and not less than 80 bits**. That is not a blank check to pick short tags for every modern system. In this lesson, **16 bytes (128 bits)** is a clear example configuration for HMAC-SHA256 when permitted by a protocol, while using the **full 32 bytes** avoids an unnecessary truncation decision.

### 6.3. AES-GCM: tag length is a parameter of authenticated encryption

With GCM, **GCMParameterSpec(tagLengthBits, iv)** takes **tag length in bits**, not bytes. For example:

- **new GCMParameterSpec(128, iv):** 128-bit tag = 16 bytes.
- **iv.length == 12:** 96-bit IV; that is the IV length, **not the tag length**.
- JCE GCM typically returns **ciphertext followed by tag** from Cipher.doFinal when encrypting. When decrypting with a 128-bit tag configuration, the API verifies the trailing tag portion of the input.

NIST SP 800-38D specifies standard GCM tag lengths of **128, 120, 112, 104, 96 bits**; **64 and 32 bits** are only for specialized applications with strict limits on data length and key lifetime. Implementations may support only a subset of those lengths. Do not lower the GCM tag length just to decrypt a truncated ciphertext; if a valid protocol uses another length, it must be a **fixed decision per key/profile**, tested and separately security-reviewed.

**Another critical limit:** with AES-GCM, never repeat a **(key, IV)** pair when encrypting a new message. Repeating an IV can destroy both authenticity and confidentiality guarantees, even with a 128-bit tag. Never use a large tag length to "compensate" for nonce/IV bugs.

### 6.4. Do not negotiate security levels from untrusted input

Dangerous logical anti-pattern:

~~~text
expectedFullTag = HMAC(secret, message)
compareLength = receivedTag.length
accept = compare(first compareLength bytes of expectedFullTag, receivedTag)
~~~

If compareLength is controlled by the client, an attacker can reduce how many bytes must be guessed; an **empty tag** might even match an empty slice and be accepted in poorly checked code.

Correct rule: **the server selects the algorithm and tag byte count from the configured version/key**, verifies the received tag has that exact length, and compares strictly. Never use receivedTag.length to slice the expected tag. Never fall back like "try 16 bytes, and if wrong try 8 bytes."

## 7. Comparing HMAC Tags in Java: Fixed Length and Minimizing Timing Leaks

For **HMAC**, Java provides **javax.crypto.Mac** to compute tags. When the receiver compares two tags, use a comparison that does not exit early based on content for fixed-length arrays, such as **MessageDigest.isEqual(expected, received)**.

Distinctions to understand:

- **Arrays.equals** is a general array comparison utility, not designed to prevent timing leaks for secret tags.
- **MessageDigest.isEqual** in modern JDKs compares digests in a way that limits timing dependence on array **content**. Do not infer from this that the entire request handler, decoding, key lookup, or all error branches are constant-time.
- **Length must be enforced first**: reject null, shorter, or longer tags than policy allows, then compare two equal-length arrays.
- If the protocol receives hex or Base64, **decode to byte[]** before checking length. A 32-character hex string represents only 16 bytes; character count is not byte count.

In real applications, apply the same rigor in both communication directions, enforce rate limits, and avoid letting outsiders distinguish "key ID exists," "wrong tag," or "wrong tag length" through unnecessary error details.

## 8. Java 17+ Example: HMAC-SHA256-128 Rejecting Tampered Tags, Wrong Keys, and Short Tags

The program generates a 32-byte HMAC key with SecureRandom, uses **HmacSHA256**, and takes the **first 16 bytes** as the tag under an HMAC-SHA256-128 policy. The verifier requires **exact 16 bytes** and uses MessageDigest.isEqual.

To run, create **`TagCheckHmacDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class TagCheckHmacDemo {
    private static final int TAG_BYTES = 16;

    private static byte[] hmac(byte[] key, byte[] message) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        return mac.doFinal(message);
    }

    private static byte[] createTag(byte[] key, byte[] message)
            throws Exception {
        return Arrays.copyOf(hmac(key, message), TAG_BYTES);
    }

    private static boolean verify(
            byte[] key, byte[] message, byte[] receivedTag) throws Exception {
        if (receivedTag == null || receivedTag.length != TAG_BYTES) {
            return false;
        }
        byte[] expected = createTag(key, message);
        return MessageDigest.isEqual(expected, receivedTag);
    }

    public static void main(String[] args) throws Exception {
        byte[] key = new byte[32];
        new SecureRandom().nextBytes(key);
        byte[] original = "amount=250000;order=42"
                .getBytes(StandardCharsets.UTF_8);
        byte[] tag = createTag(key, original);

        byte[] changed = original.clone();
        changed[0] ^= 1;

        byte[] otherKey = key.clone();
        otherKey[0] ^= 1;

        System.out.println("Valid tag: " + verify(key, original, tag));
        System.out.println("Modified message: " + verify(key, changed, tag));
        System.out.println("Wrong key: " + verify(otherKey, original, tag));
        System.out.println("Short 15-byte tag: " +
                verify(key, original, Arrays.copyOf(tag, 15)));
        System.out.println("Empty tag: " + verify(key, original, new byte[0]));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 --release 17 TagCheckHmacDemo.java
java TagCheckHmacDemo
~~~

Output:

~~~text
Valid tag: true
Modified message: false
Wrong key: false
Short 15-byte tag: false
Empty tag: false
~~~

### Security explanation point by point

1. **Mac.getInstance("HmacSHA256")** computes HMAC with the right algorithm; **SecretKeySpec** supplies the secret key for computation. The raw HMAC output is 32 bytes.
2. **Arrays.copyOf(..., TAG_BYTES)** is applied only when **computing the expected tag** under the fixed 16-byte policy. Lengths received from the network never influence how many bytes are checked.
3. **receivedTag == null or length != 16** causes rejection **before comparison**. Thus a 15-byte or empty array cannot lower the verification threshold.
4. **MessageDigest.isEqual** receives two 16-byte arrays. On modern JDKs, differing at the first byte does not cause an immediate early exit like a naive comparison.
5. **Flipping one message byte** changes the expected tag; **flipping a key byte** also changes the expected tag. In reality, theoretical random collision probability is not strictly zero; the test output above reflects a run with a randomly generated key.
6. Each call to **hmac** creates a **separate Mac instance**, avoiding state mixing across concurrent requests. Test keys and data live only in memory for this demonstration program.

**In production:** never use hardcoded keys. Retrieve secrets from a secret manager/KMS or equivalent protected store, identify key versions, add protocol-level replay protection, and never log secrets. Never invent a truncation policy different from your provider's webhook specification.

## 9. Java 17+ Example: AES-GCM Rejecting Bad Ciphertext, Key, AAD, or Tag

Unlike HMAC, **AES-GCM does not just emit a tag**—it also encrypts plaintext. Tag matching is performed by **Cipher.doFinal**. The example below encrypts a message with a **128-bit (16-byte)** tag, then runs valid and invalid decryptions.

Create **`TagCheckGcmDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class TagCheckGcmDemo {
    private static final int TAG_BITS = 128;
    private static final int IV_BYTES = 12;

    private record Sealed(byte[] iv, byte[] ciphertextAndTag) {}

    private static Sealed encrypt(SecretKey key, byte[] plain, byte[] aad)
            throws Exception {
        byte[] iv = new byte[IV_BYTES];
        new SecureRandom().nextBytes(iv);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
        cipher.updateAAD(aad);
        return new Sealed(iv, cipher.doFinal(plain));
    }

    private static boolean opensAs(SecretKey key, Sealed sealed,
            byte[] aad, byte[] expectedPlain) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, sealed.iv()));
        cipher.updateAAD(aad);
        try {
            byte[] plain = cipher.doFinal(sealed.ciphertextAndTag());
            return Arrays.equals(plain, expectedPlain);
        } catch (AEADBadTagException e) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();

        byte[] plain = "order=42;amount=250000"
                .getBytes(StandardCharsets.UTF_8);
        byte[] aad = "tenant=A;v=1".getBytes(StandardCharsets.UTF_8);
        Sealed sealed = encrypt(key, plain, aad);

        byte[] changed = sealed.ciphertextAndTag().clone();
        changed[0] ^= 1;

        byte[] wrongKeyBytes = key.getEncoded().clone();
        wrongKeyBytes[0] ^= 1;
        SecretKey wrongKey = new SecretKeySpec(wrongKeyBytes, "AES");

        byte[] wrongAad = "tenant=B;v=1".getBytes(StandardCharsets.UTF_8);
        byte[] shortTag = Arrays.copyOf(sealed.ciphertextAndTag(),
                sealed.ciphertextAndTag().length - 1);

        System.out.println("Valid GCM: " + opensAs(key, sealed, aad, plain));
        System.out.println("Modified data: " + opensAs(key,
                new Sealed(sealed.iv(), changed), aad, plain));
        System.out.println("Wrong key: " +
                opensAs(wrongKey, sealed, aad, plain));
        System.out.println("Wrong AAD: " +
                opensAs(key, sealed, wrongAad, plain));
        System.out.println("Truncated tag: " + opensAs(key,
                new Sealed(sealed.iv(), shortTag), aad, plain));
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 TagCheckGcmDemo.java
java TagCheckGcmDemo
~~~

Output:

~~~text
Valid GCM: true
Modified data: false
Wrong key: false
Wrong AAD: false
Truncated tag: false
~~~

### How to read the results accurately

- **Valid GCM: true** because key, IV, AAD, and ciphertext||tag all match. In the example, opensAs also compares the resulting plaintext with expectedPlain to illustrate a test. **Actual cryptographic authentication is performed by Cipher.doFinal**, while Arrays.equals here is just a test assertion.
- **Modified data: false** because a ciphertext byte was altered and the old tag no longer matches.
- **Wrong key: false** because the verifier initialized with a different AES key. Applications should not tell clients "wrong key" or "attack detected" based on a tag failure.
- **Wrong AAD: false** because AAD is authenticated even though unencrypted. If tenant/version is security metadata, include those corresponding bytes in the authentication policy.
- **Truncated tag: false** because the input array no longer contains a valid ciphertext/tag under the configured 128-bit GCM profile; **Cipher.doFinal** rejects it.
- **new GCMParameterSpec(TAG_BITS, iv)** takes **128 bits** and a 12-byte IV; never confuse TAG_BITS with IV_BYTES.
- **new SecureRandom().nextBytes(iv)** generates a random IV for a single encryption. The example uses it once with a fresh key; applications with high message volumes or multiple nodes must design a **per-key unique** nonce strategy, collision budget, and proper key lifecycle.
- **Sealed** here is a simple record holding mutable byte arrays for testing convenience. Java records do not make arrays deeply immutable; production code must control data ownership/copying and package version, key ID, IV, ciphertext, and tag cleanly.

If a provider does not support the requested variant or parameters, the application may throw an exception on initialization. **Do not silently catch every Exception and return false**: distinguish configuration/capability errors for operations while still keeping external responses free of sensitive details.

## 10. Risks of Multi-Step Decryption and Using Plaintext Before Tag Verification

In AEAD, decryption flows must ensure **unauthenticated plaintext is never released to business logic, logs, files, or other systems**. Some providers/APIs may buffer decrypted data and release plaintext only after the tag validates; never assume every provider and every streaming usage pattern guarantees that behavior.

Easily verifiable rules:

1. Call **updateAAD** with all AAD before processing ciphertext for GCM/CCM.
2. Provide the exact ciphertext and tag with **the protocol-mandated tag length**.
3. Finalize and verify via **doFinal**.
4. **Only after doFinal succeeds**, allow business logic to consume plaintext.
5. When **AEADBadTagException** (or an API authentication error) occurs, discard temporary data, do not try to inspect/recover plaintext, and do not reuse a Cipher left in an error state as a fresh operation.
6. If streaming decryption of large files is needed, use a chunked/record-based AEAD format with per-record nonces and tags plus explicit termination rules; never treat processed chunks as valid prior to proper authentication.

Homegrown **MAC-then-encrypt** or **encrypt-then-MAC** designs can introduce ordering, key-separation, MAC-scope, and error-handling bugs. For new problems, prefer a supported **standard AEAD** mechanism rather than assembling an unvetted cryptographic protocol.

## 11. Tag Length, Encoding, and Transport Protocols: Common Java Pitfalls

### 11.1. Comparing strings instead of tag bytes

If an API transmits tags in Base64url, the server should decode and compare **byte[]**. Base64 (and hex) only encode display representation; they add no entropy and do not turn a tag into a different secret. Never convert a tag to BigInteger because leading zero bytes can be stripped, sign bytes added, or formatting altered.

If the contract mandates a canonical Base64url representation, validate that exact format before decoding; never silently accept a range of variant inputs outside the protocol. If the contract specifies raw bytes, never convert to String and back using the JVM's default charset.

### 11.2. Altering the message before verification

Never trim, lowercase, strip newlines, parse numbers and re-stringify, or re-serialize JSON before HMAC if the protocol signs the raw body. For example:

~~~text
Raw body A: {"amount":250000,"order":42}
Raw body B: { "order": 42, "amount": 250000 }

The data meaning may be equivalent,
yet HMAC(raw A) and HMAC(raw B) will generally differ.
~~~

For true canonicalization, both parties must follow **the exact same clearly defined rule**. Never retry multiple transformations until one "happens" to match the tag.

### 11.3. Tags truncated by column limits, buffers, or serialization

Verify units of measurement:

- **32-byte** HMAC-SHA256 has **64 hex characters**, or a Base64 string length depending on padding/profile.
- **16-byte** HMAC-SHA256-128 has **32 hex characters**; a shorter string may indicate a transit or encoding bug—never silently change policy.
- AES-GCM with a 16-byte tag usually outputs **ciphertext||tag**; if trailing bytes are cut off, treat the envelope as invalid.
- In JCE, **GCMParameterSpec(128, iv)** selects a 128-**bit** tag, not 128 bytes. IV length is specified separately.
- In storage APIs, the character limit of a Base64 field does not equal the decoded byte limit.

Never "recover" by zero-padding or appending characters to a truncated tag. Fix the underlying transit/storage bug and re-verify with the sender.

### 11.4. Parameter mismatches when changing provider/JDK

A provider might not support a specific GCM tag length even when permitted by the standard; transformation, key type, IV length, and AAD choices also depend on the implementation. Record the provider and compatibility test results in the target environment; **never shorten tag length when a provider rejects parameters**.

### 11.5. Content-independent byte comparison is not enough for the whole system

Even when using MessageDigest.isEqual, timing can still vary in Base64 parsing, key lookup, database reads, exceptions, or KMS/HSM calls. Mitigate with controlled error design, rate limiting, and avoiding secret disclosure; never claim an entire endpoint is constant-time solely because of one array-comparison function.

## 12. Applied Example: Verifying a Payment Webhook

Suppose a payment gateway sends requests with a timestamp, transaction ID, raw body, and HMAC. A proper verification pipeline needs:

1. Receive **raw body bytes** within a size limit; read tag, timestamp, and key ID from **protocol-defined** headers.
2. Parse headers safely, validating format and decoded tag length **strictly per policy**.
3. Look up the secret for the right partner and key version from trusted configuration; never take secrets from the request.
4. Construct the HMAC-protected byte sequence per the provider's spec (e.g., timestamp + body with explicit delimiter/canonicalization). Never improvise if the sender specifies a different format.
5. Compute HMAC and compare the exact byte count; on failure, reject **without processing payment**.
6. Check timestamp/freshness and transaction ID per policy; ensure replay-protection fields are also covered by authentication or bound to a trusted context.
7. Check current transaction state and process **idempotently**. A replayed valid webhook must never credit funds or ship goods multiple times.
8. Return an appropriate generic response to the sender and log safely for traceability without keys or sensitive details.

Example: an attacker captures a validly signed webhook and resends it **verbatim**. HMAC remains valid because bytes and tag are unchanged; the application must use transaction ID, timestamp, nonce, or business state to reject duplicate execution. Conversely, if an attacker alters the amount without the key, the tag is invalid and rejected at verification.

If the protocol uses **digital signatures** instead of HMAC, the flow is similar in principle for byte verification and freshness, but uses **Signature.verify** with an origin-verified public key; never force messages into HMAC.

## 13. Designing Envelopes and Versioning for Stored Data

For a Java application storing AES-GCM ciphertexts, you can design a versioned application-level record:

~~~text
RecordV1:
  version       = 1
  keyId         = key ID used to select the authorized AES key
  iv            = 12 bytes per nonce policy
  ciphertext    = encrypted bytes
  tag           = trailing 16 bytes of AES-GCM output
  aad           = bytes binding tenant + record type + version
~~~

This is an **application contract example**, not a standard storage format automatically produced by JCA. Points to lock down:

- If placing version/keyId/tenant into AAD, define **exact byte serialization rules**, avoiding ambiguous string concatenation.
- Decryption keys must be fetched by **permitted identifiers** and matching tenant; senders must never control arbitrary secret lookup locations.
- The verifier must obtain **tag length** from the configured profile, never reading an arbitrary length from untrusted data.
- IVs must be unique **across the entire scope of the same AES key during encryption**, even across multiple nodes, restarts, and backups/restores.
- Legacy records need sufficient key version/format version metadata to decrypt or migrate after rotation; never override tag length/algorithm ambiguously.
- A corrupted record, bad tag, or missing valid key must be classified as unverifiable; never recover plaintext by skipping verification.

**A MAC tag does not protect information outside the MAC/AAD input.** If key ID or version must be protected from tampering, bind prescribed metadata into AAD/authenticated structure per policy and validate it against the application's trusted context.

## 14. Test Plan: Happy Paths and Rejection Cases

Testing only a valid tag is insufficient. Tests must demonstrate **acceptance only when all conditions are met**.

| Test Case | Input | Expected Outcome |
| --- | --- | --- |
| Valid HMAC | Exact message bytes + right key + exact 16-byte tag per profile | Accept. |
| HMAC 1-byte message tamper | Keep old tag, alter message bytes | Reject. |
| HMAC 1-byte tag tamper | Keep message, alter tag bytes | Reject. |
| HMAC wrong key | Different key from creator's | Reject. |
| HMAC empty tag | byte[0] | Reject before comparison. |
| HMAC 15-byte tag | One byte short under 16-byte policy | Reject; do not match prefix. |
| HMAC 17- or 32-byte tag | Longer than 16-byte policy | Reject unless another profile is explicitly agreed. |
| HMAC encoding mismatch | Body re-serialized into different bytes | Reject; fix canonicalization bug in protocol. |
| Valid GCM | Right key, IV, AAD, ciphertext, and 128-bit tag | Decrypt successfully then use plaintext. |
| GCM tampered ciphertext/tag | Flip bit while keeping old metadata | Reject via doFinal, do not process plaintext. |
| GCM wrong AAD | Mismatched tenant/version | Reject via doFinal. |
| GCM wrong IV | IV not the one used to encrypt | Reject via doFinal. |
| GCM wrong key | Different key | Reject or fail initialization cleanly depending on cause. |
| GCM truncated ciphertext/tag | Fewer bytes than envelope/tag policy | Reject; do not lower tagLength. |
| Replay | Resend previously valid message + tag | MAC may still verify; replay/idempotency must block repeat execution. |
| Key rotation | v1/v2 messages and matching key IDs | Use key permitted by active version and policy. |
| Concurrent load | Many distinct verification requests via thread pool | No mixing of Mac/Cipher state or buffers across requests. |

A practical test suite should run on the target deployment provider/JDK. Include non-ASCII bytes, Vietnamese diacritics, newlines, combining Unicode characters, and large inputs to uncover encoding/canonicalization disagreements. Failure tests must assert that **no business side effects occur** before verification; merely asserting an exception after already recording a payment is insufficient.

### Distinguishing false accepts from false rejects

- **False accept:** the system accepts an invalid tag; the most dangerous failure because it can allow forgery or tampering.
- **False reject:** a valid tag is rejected due to wrong key, format, IV, AAD, or canonicalization; breaks integration, yet must never be "fixed" by disabling verification.
- **Provider/configuration error:** unsupported algorithm/key/parameters or unavailable key store; treat as a system error while preserving the rule to reject unauthenticated data.

## 15. Thinking and Coding Mistakes to Avoid

1. **Comparing prefixes based on client-supplied tagLength:** creates a downgrade risk, especially with empty or very short tags.
2. **Allowing 8, 12, or 16 bytes per message without a trusted version/profile:** eliminates a clear authentication threshold.
3. **Using equals/toString to compare encoded tags:** prone to encoding bugs, dropped bytes, or non-timing-safe comparisons.
4. **Using SHA-256(message) as a MAC:** has no secret key, and an adversary can recompute it after modifying the message.
5. **Including only part of a request in HMAC while trusting the whole request:** fields outside tag scope can be altered.
6. **Ignoring AEADBadTagException to still use plaintext:** defeats AEAD's core protection.
7. **Confusing tag length with IV length:** GCMParameterSpec(128, iv) specifies a 128-bit tag, while 12 bytes is a common IV size.
8. **Reusing an AES-GCM key/IV pair:** can enable severe attacks regardless of tag length.
9. **Switching from 128-bit to 64-bit tag to "read old data":** lowers guarantees and may violate policy/protocol; fix the root format or key/parameter mismatch instead.
10. **Not distinguishing verification failure from technical errors:** error handling must stay safe while helping operations diagnose without leaking secrets.
11. **Testing only valid inputs:** misses tag truncation, wrong keys, wrong tenant/AAD, or replay.
12. **Believing a tag equals authorization:** a tag only authenticates bytes under a key; business logic still needs authorization, state checks, and duplicate prevention.

## 16. Knowledge Check

**Question 1.** The protocol uses HMAC-SHA256-128, yet 15 bytes are received. Should we compare the first 15 bytes of the expected tag?  
**Answer:** No. Policy requires **exact 16 bytes**. Reject the 15-byte tag even if the first 15 bytes match, because tag length is never negotiated by the client.

**Question 2.** The body's HMAC is valid, but the tenant ID header was modified. What can happen?  
**Answer:** If tenant ID is not protected by the MAC or bound to a trusted context, the body tag can still verify. You must explicitly specify which metadata HMAC covers and enforce server-side tenant authorization.

**Question 3.** Using the right AES-GCM key and ciphertext, but different AAD. What does Java return?  
**Answer:** Tag verification fails; with JCE GCM, **Cipher.doFinal** can throw **AEADBadTagException**. You cannot conclude with certainty that an attack occurred from the exception alone, since wrong AAD produces the same error.

**Question 4.** Does GCMParameterSpec(128, iv) with a 12-byte iv mean the tag is 128 bytes long?  
**Answer:** No. 128 is **tag bits = 16 bytes**; the 12-byte IV is a separate parameter.

**Question 5.** If the server sees an 8-byte tag, why not automatically switch to a 64-bit GCM tag to try decrypting?  
**Answer:** Tag length is a protocol and key-policy decision; shorter lengths carry strict security limits and may not be supported by the provider. Truncated data must not be legitimized through downgrades.

**Question 6.** Does a valid tag prove a webhook was never processed before?  
**Answer:** No. You also need timestamps/nonces, transaction IDs, state checks, and idempotency built into the protocol.

**Question 7.** HMAC-SHA256 returns 32 bytes, yet the system uses 16 bytes. When verifying, do we compute HMAC over "half the message"?  
**Answer:** No. **Always compute HMAC over the entire message bytes**; only take the **first 16 output bytes** per the defined HMAC-SHA256-128 profile.

**Question 8.** Does MessageDigest.isEqual make the entire endpoint constant-time?  
**Answer:** No. It helps compare digests with reduced content-based timing leaks under suitable conditions, whereas decoding, key lookup, rate limiting, exceptions, and other steps have their own timing behavior.

## 17. Conclusion and References

A sound tag verification mechanism requires all three invariants: **(1) right key and exact protected bytes; (2) fixed policy-defined algorithm/parameters and tag length; (3) never use content when authentication fails**. HMAC verifies by computing a MAC and comparing tags; AES-GCM verifies inside Cipher.doFinal itself. Longer tags defend better against guessing forgeries within algorithm limits, yet never replace key management, unique IVs, authorization, replay protection, and operational controls.

Recommended technical references:

- [RFC 2104 — HMAC: Keyed-Hashing for Message Authentication, Section 5 on truncated output](https://www.rfc-editor.org/rfc/rfc2104.html)
- [NIST SP 800-38D — Galois/Counter Mode (GCM) and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final)
- [Java SE 21 — Mac API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Mac.html)
- [Java SE 21 — Cipher API, GCM/AEAD](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html)
- [Java SE 21 — MessageDigest.isEqual](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html)
- [Java SE 21 — GCMParameterSpec](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html)
