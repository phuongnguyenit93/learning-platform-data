# 6.8. Passing AAD Before Data; Distinguishing Authenticated Data from Encrypted Data

## 1. Goal: Understanding the Two Protection Layers in AEAD

In symmetric encryption, "outsiders cannot read the contents" and "outsiders cannot alter the contents undetected" are **two separate requirements**:

- **Confidentiality:** someone without the key cannot feasibly recover plaintext from ciphertext.
- **Integrity/authenticity:** the receiver can detect if data or context was modified without authorization to forge a valid authentication tag.

AEAD (*Authenticated Encryption with Associated Data*) combines both requirements: it **encrypts and authenticates plaintext**, while also authenticating a region of **unencrypted** data called *Additional Authenticated Data* (AAD, sometimes written AD). In Java, a common approach is using `Cipher` with the `AES/GCM/NoPadding` transformation.

Practical example: a system sends an invoice with:

- Header: `version=1;tenant=shop-7`, which must remain readable for routing/format parsing, yet **must not be covertly altered**.
- Payload: `hoa-don:120000 VND`, which must stay **confidential** and unaltered.
- Nonce/IV: a non-secret value; the decryptor must use the exact value used during encryption.
- Authentication tag: cryptographic proof binding ciphertext and AAD to the key/nonce/algorithm.

Passing the **header** into AAD and the **payload** into `Cipher.doFinal` gives AEAD two distinct behaviors: the header stays readable in transit, yet tampering with it fails verification; the payload is both encrypted and authenticated.

**Lesson goal:** know which bytes are encrypted versus merely authenticated; call `Cipher.updateAAD` in the right order; check tag failures; and design complete, safe wire formats.

## 2. How Does AAD Differ from Plaintext, Ciphertext, IV, and Tag?

| Component | Encrypted by AES-GCM? | Bound by AEAD Authentication? | Role |
| --- | --- | --- | --- |
| **Plaintext** passed via `update`/`doFinal` in encrypt mode | **Yes**: becomes ciphertext | **Yes**: receiver accepts plaintext only after tag verification | Data needing both confidentiality and integrity |
| **AAD** passed via `updateAAD` | **No**: remains public plaintext bytes | **Yes**: changing AAD causes tag mismatch | Header, record type, tenant, version, context identifiers |
| **Ciphertext** | Already encrypted data | **Yes** | Encrypted payload output; modifying bytes fails verification |
| **GCM IV/nonce** | **No**; usually stored/transmitted publicly | Must match encryption and participates in tag calculation | Guarantees uniqueness per encryption under the same key; exact nonce needed to decrypt |
| **Authentication tag** | Not secret plaintext; usually appended after ciphertext in `doFinal` output | Checked value deciding authenticity | Detects tampering with data/tag/context |
| Data **neither** passed to AAD **nor** encrypted | No | **No**, unless protected by a separate mechanism | Must not be trusted as AEAD-protected |

A common misconception: **AAD is authenticated, not confidential**. If a header contains customer names, emails, or sensitive fields, passing that header into AAD **does not hide** them. To keep data secret, place it inside plaintext to be encrypted (and authenticated), or protect it separately.

Likewise, "encrypted data" does not automatically imply integrity if using an unauthenticated mode like standalone AES-CBC. Here AES-GCM both encrypts and computes a tag; the decryptor must **verify the tag successfully** before trusting the result.

### Byte Scope Illustration

```text
Transmitted/stored record (example)
+---------------------------+----------------------+---------------------+
| header (AAD, cleartext)   | nonce/IV (cleartext) | ciphertext || tag   |
| version=1;tenant=shop-7   | 12 bytes             | encrypted bytes+tag |
+---------------------------+----------------------+---------------------+
           |                          |                       |
           +----------- feed into ----|------> GCM Cipher <---+
                            updateAAD(header)
                                      init(key, nonce)
                                      doFinal(payload)

On decryption, same key + nonce + AAD + ciphertext/tag:
    valid tag   --> accept plaintext
    invalid tag --> reject entire record
```

The diagram only illustrates field **semantics**; real applications need a binary or JSON structure with explicit schema/version/byte-lengths. Never expect `Cipher` to automatically recognize which header is AAD: the application must **actively** call `updateAAD` with the exact header bytes.

## 3. Mandatory API Call Order in Java

For GCM/CCM, the `javax.crypto.Cipher` documentation mandates that **all AAD must be supplied before processing data** via `update` or `doFinal`. This applies to **both encryption and decryption**.

Correct sequence:

1. `Cipher.getInstance("AES/GCM/NoPadding")` to obtain the engine.
2. `cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, iv))` to set key and parameters.
3. `cipher.updateAAD(headerBytes)` to feed authenticate-only data. `updateAAD` may be called multiple times, yet every call must happen **before** operating on plaintext/ciphertext.
4. `cipher.update(payloadChunk)` optionally when streaming in chunks; or directly `cipher.doFinal(plaintext)` if data fits in one call.
5. `cipher.doFinal(...)` finishes encryption and returns ciphertext plus authentication tag.

For decryption, replace `ENCRYPT_MODE` with `DECRYPT_MODE` and supply the **exact same AAD** before feeding ciphertext. `doFinal(ciphertextAndTag)` verifies the tag; on mismatch, the API may throw `AEADBadTagException`. Never use or expose plaintext before verification succeeds.

```java
// Illustrative snippet assuming key, iv, aad, plaintext already exist.
Cipher encryptor = Cipher.getInstance("AES/GCM/NoPadding");
encryptor.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, iv));
encryptor.updateAAD(aad);                        // 1. Authenticate header
byte[] encrypted = encryptor.doFinal(plaintext); // 2. Encrypt payload + tag
```

**Wrong order** is calling `update(plaintextChunk)` first and then `updateAAD(aad)`. With GCM/CCM, calling `Cipher.updateAAD` after data has been processed is an invalid state and can throw `IllegalStateException`; do not treat this error as "provider-specific whim", since the Java contract requires AAD upfront. Nor can you feed AAD after `doFinal`: the operation is already over.

Reason for this ordering: AEAD modes compute AAD authentication before beginning ciphertext authentication. Providers require all AAD upfront to implement this cleanly without buffering the entire ciphertext just because AAD arrives late.

### Can `updateAAD` Be Called Multiple Times?

Yes, when bytes for the same GCM message are fed in pieces **before the payload**. For example:

```java
cipher.updateAAD(versionBytes);
cipher.updateAAD(tenantBytes);
cipher.updateAAD(headerBytes);
byte[] output = cipher.doFinal(plaintext);
```

This is an **illustrative snippet** assuming `cipher` is initialized and the arrays are defined. Remember that GCM authenticates the **AAD byte sequence in exact order**. If the sender feeds `versionBytes||tenantBytes||headerBytes` while the receiver feeds a different order, verification will fail.

In particular, variable-length fields need **unambiguous serialization**: for instance, tagging each field with type and fixed length or length prefixes. Strings `"ab" + "c"` and `"a" + "bc"` yield identical bytes under naive concatenation; if field boundaries matter semantically, encode field delimiters/lengths into AAD.

## 4. Standalone Java 17+ Example: Cleartext Yet Authenticated Header

The program creates a demo-only AES key, generates a fresh 12-byte random nonce, passes a header into AAD, encrypts the payload with AES-GCM, and decrypts cleanly. It then tampers with **AAD**, **ciphertext**, and **IV** in turn to confirm rejection.

Create **`AadGcmDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class AadGcmDemo {
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int TAG_BITS = 128;

    static byte[] encrypt(SecretKey key, byte[] iv, byte[] aad,
            byte[] plaintext) throws Exception {
        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
        cipher.updateAAD(aad); // Must precede update/doFinal on payload.
        return cipher.doFinal(plaintext);
    }

    static byte[] decrypt(SecretKey key, byte[] iv, byte[] aad,
            byte[] ciphertextAndTag) throws Exception {
        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
        cipher.updateAAD(aad); // Supply exactly the same AAD bytes.
        return cipher.doFinal(ciphertextAndTag); // Checks authentication tag.
    }

    static boolean accepted(SecretKey key, byte[] iv, byte[] aad,
            byte[] ciphertextAndTag) throws Exception {
        try {
            decrypt(key, iv, aad, ciphertextAndTag);
            return true;
        } catch (AEADBadTagException rejected) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();

        byte[] iv = new byte[12]; // Fresh IV for this encryption.
        new SecureRandom().nextBytes(iv);

        byte[] aad = "version=1;tenant=shop-7"
                .getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "hoa-don:120000 VND"
                .getBytes(StandardCharsets.UTF_8);

        byte[] ciphertextAndTag = encrypt(key, iv, aad, plaintext);
        byte[] recovered = decrypt(key, iv, aad, ciphertextAndTag);

        System.out.println("AAD visible: " +
                new String(aad, StandardCharsets.UTF_8));
        System.out.println("Decrypted data: " +
                new String(recovered, StandardCharsets.UTF_8));
        System.out.println("Tag overhead: " +
                (ciphertextAndTag.length - plaintext.length) + " bytes");

        byte[] changedAad = aad.clone();
        changedAad[0] ^= 1;
        System.out.println("Changed AAD accepted: " +
                accepted(key, iv, changedAad, ciphertextAndTag));

        byte[] changedCiphertext = ciphertextAndTag.clone();
        changedCiphertext[0] ^= 1;
        System.out.println("Changed ciphertext accepted: " +
                accepted(key, iv, aad, changedCiphertext));

        byte[] changedIv = iv.clone();
        changedIv[0] ^= 1;
        System.out.println("Changed IV accepted: " +
                accepted(key, changedIv, aad, ciphertextAndTag));
    }
}
```

Compile and run (JDK 17 or newer supporting AES/GCM):

```bash
javac AadGcmDemo.java
java AadGcmDemo
```

Exact stdout on every successful run, even though key/IV/ciphertext are randomly generated:

```text
AAD visible: version=1;tenant=shop-7
Decrypted data: hoa-don:120000 VND
Tag overhead: 16 bytes
Changed AAD accepted: false
Changed ciphertext accepted: false
Changed IV accepted: false
```

### Explaining Why All Three Modifications Failed

- **Altered AAD:** ciphertext/tag/key/IV stayed identical, yet the header changed by one byte. Because AAD participates in GCM tag computation, decryption's `doFinal` throws `AEADBadTagException`. This demonstrates **AAD is authenticated despite being unencrypted**.
- **Altered ciphertext:** the AAD header stayed intact, yet one ciphertext byte flipped. The tag is invalidated, rejecting the modified payload.
- **Altered IV:** the IV is a core parameter of an encryption invocation. Decrypting with a different IV fails to recover the valid state/tag; the example shows authentication is rejected.
- **Tag overhead:** with a 128-**bit** tag, the ciphertext returned by `doFinal` includes 16 **bytes** of tag beyond plaintext length. This is the authentication tag, not `PKCS5Padding`; the transformation uses `NoPadding`.
- **Visible AAD value:** the program intentionally prints the raw header to prove AAD is never encrypted. Do not infer that AAD should be printed to screens/logs in real applications; that depends on header privacy requirements.

**Example scope:** the key exists only in-process; this is not a long-term key/ciphertext persistence flow. When decrypting on another machine or after a restart, retrieve the exact key via keystore/KMS and pass/persist the exact IV, AAD header, and ciphertext/tag.

## 5. Distinguishing "Authenticated" from "Encrypted"

### 5.1. Data Both Encrypted and Authenticated

In AES-GCM, **payload** passed through `Cipher.update`/`doFinal` becomes ciphertext; anyone without the proper key cannot read the plaintext under the algorithm's security assumptions. Simultaneously, the GCM tag binds payload, AAD, key, and nonce during verification. The decryptor **accepts results only after tag validation**.

"Encrypted" alone does not mean "any ciphertext is safe": you need the right AEAD mode, nonce/IV discipline, tag length, key management, and verification flow.

### 5.2. Data Authenticated Yet Unencrypted

**AAD** does not pass through plaintext encryption, so observers can read AAD contents if the record carries them in cleartext. However, the receiver passes those exact bytes to `updateAAD` before `doFinal` to verify their integrity alongside the payload.

Use cases: format version, record type, non-sensitive tenant name, document ID, sequence number, or content type that the receiver needs to inspect *early* for routing. Make security decisions from these fields **only after authentication succeeds**; if used preliminarily for routing/key lookup, treat them as untrusted until verified.

### 5.3. Data Completely Outside AEAD Scope

If an accompanying field is **neither** fed into AAD **nor** placed into encrypted plaintext, GCM does not protect it. For example, a `tenantId` in JSON outside the ciphertext omitted from `updateAAD` can be modified while tag verification still passes for the old ciphertext. This is a very easy-to-miss context-binding flaw.

Fix: identify upfront every metadata field affecting interpretation, permissions, or record identity; serialize them into a versioned AAD byte sequence and feed those exact bytes into AEAD.

### 5.4. AAD Does Not Replace Encryption or Digital Signatures

- AAD does not protect the **confidentiality** of the header itself.
- AEAD does not prove legal sender identity on its own: if multiple parties share a symmetric key, any holder can produce a valid tag.
- Does not solve **replay**: a valid ciphertext/tag/AAD/IV record can be replayed verbatim. Replay protection needs an authenticated sequence number/business nonce/timestamp **plus** reuse/expiry tracking in the application.
- Does not replace **authorization**: a valid tag does not mean the caller is permitted to read or modify that tenant's record.

## 6. Designing Records with AAD: Which Bytes Must Match?

For example, a record might include:

| Field | Protection Mechanism | Notes |
| --- | --- | --- |
| `formatVersion` | AAD | Prevents senders from silently switching formats; verify version is supported before deep parsing. |
| `tenantId` | AAD if public; plaintext if confidential | Tenant identifier must be bound to ciphertext and actual access control. |
| `contentType` | AAD | Prevents altering how decrypted payload is parsed. |
| `keyId` | AAD or bound via secure protocol | May be needed to look up the key **before verification**, when `keyId` is still untrusted; restrict to allowlists/bounded lookup and re-verify. |
| `iv` | Separate public field | Must ensure per-key uniqueness on encryption; pass exact IV on decryption. |
| `ciphertextAndTag` | Confidential ciphertext and auth tag | Store full tag; never drop or miscount bytes. |
| `payload` | Plaintext passed to `doFinal` | Encrypted + authenticated; e.g., monetary amounts, descriptions, private data. |

Define **consistent byte serialization**: a display-oriented JSON record can vary in field ordering, whitespace, Unicode normalization, or numeric formatting between runtimes. If the sender computes AAD from UTF-8 of `"version=1;tenant=shop-7"` while the receiver uses UTF-8 of `"tenant=shop-7;version=1"`, the byte arrays differ and authentication fails.

Two sound approaches:

1. **Store/transmit the exact authenticated header bytes verbatim.** The receiver feeds those exact bytes into `updateAAD`, trusting parsed fields only after the tag passes.
2. **Use strict canonical serialization.** Define UTF-8 encoding, field order, lengths, field types, and canonicalization; both sides reconstruct **the exact same bytes**.

Never concatenate variable-length values without boundaries: `"ab" + "c"` and `"a" + "bc"` yield identical byte strings despite representing different field pairs. Use length prefixes or tagged/length-prefixed fields with versioning to prevent ambiguity.

## 7. Streaming Data Without Violating Order

Java provides overloads:

- `cipher.updateAAD(byte[])`;
- `cipher.updateAAD(byte[], offset, len)`;
- `cipher.updateAAD(ByteBuffer)`.

And payload methods such as `update(...)` and `doFinal(...)`. Valid ordering when encrypting/decrypting in chunks:

```text
Cipher.init(...)
  |
  +-- updateAAD(headerPart1)
  +-- updateAAD(headerPart2)
  +-- updateAAD(headerPart3)   <-- END OF AAD
  |
  +-- update(payloadPart1)
  +-- update(payloadPart2)
  +-- doFinal(lastPayloadPart)
       |
       +-- encrypt: final ciphertext + authentication tag
       +-- decrypt: verifies tag; accept plaintext only on success
```

With `ByteBuffer`, `updateAAD(ByteBuffer)` consumes bytes in the buffer's `remaining()` slice and advances `position` to `limit`; it does not mean the buffer's full physical capacity if position/limit changed.

### Never Use Decrypted Plaintext Before Tag Verification

In GCM, final tag verification occurs in `doFinal`. Some implementations buffer decrypted output, whereas others may emit plaintext bytes from `update` before the trailing tag is verified. Therefore, **never send partially decrypted data over the network, write it to a DB as trusted data, or execute it** before full verification succeeds. For large data, use a staging buffer/area and commit/publish only once `doFinal` succeeds; if verification fails, discard temporary data.

If `doFinal` throws `AEADBadTagException`, never try to "keep decrypting" or bypass the tag to salvage plaintext. Reject the record, scrub sensitive buffers appropriately, and handle errors at the application boundary.

### Must You Always Call `updateAAD`?

No. AAD is **optional** in AES-GCM: if no extra metadata needs authentication, an application can omit `updateAAD` and still encrypt/authenticate the payload with GCM. However, once a header is **designed** to be protected as AAD, both encryptor and decryptor must pass exact header bytes via `updateAAD` before processing payload. Forgetting this on **both sides** lets encryption/decryption run while leaving the header unauthenticated!

## 8. Associated Risks and Security Principles

1. **Never reuse `(key, IV)` when encrypting with AES-GCM.** Random 96-bit IVs from `SecureRandom` are a common nonce strategy; high-load systems must manage collision probabilities, encryptions per key, and rotation. Never use constant IVs or reuse old records' IVs for new messages.
2. **Keep IV and AAD distinct.** The IV drives GCM state; AAD is optional authenticated metadata bytes. They are not interchangeable. A public IV does not mean decryption succeeds with a wrong IV.
3. **Use a sufficiently strong tag per protocol.** E.g., 128-bit tag and 12-byte IV; `GCMParameterSpec(128, iv)` takes **bits**, not bytes. Never let clients request short tags outside policy.
4. **Protect keys.** AAD, IV, and ciphertext/tag can be stored/transmitted publicly per design, whereas AES keys must be managed securely via keystore/KMS, access controls, and lifecycle policies. Never hardcode real keys.
5. **Never grant permissions from an unauthenticated header.** You may preliminarily parse `version`/`keyId` for routing, yet restrict permitted algorithms/keys and **re-verify** all context once the tag passes.
6. **Never store data you expect hidden inside AAD.** User names, addresses, accounts, or private content in AAD are visible to observers. Put secrets inside plaintext.
7. **Never treat standalone AES-CBC encryption as equivalent to AEAD.** CBC lacks GCM's AAD/tag authentication. To authenticate full messages, use AEAD or a properly designed Encrypt-then-MAC protocol.
8. **Enforce size and input bounds.** Validate IV length, version, tag length, ciphertext size, header length, charset, and required fields before allocating memory or decrypting. Reject transformations outside an allowlist.
9. **Avoid leaking detailed authentication failure causes.** Wrong AAD, wrong key, wrong IV, or altered ciphertext/tag may all trigger tag failures. Return uniform rejection responses and avoid logging plaintext or keys.
10. **Never reuse a `Cipher` to encrypt a new message with the same key/IV.** Each encryption must initialize with a unique fresh IV. `Cipher` is not safe to share arbitrarily across threads.

## 9. Error Symptoms and Troubleshooting

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `IllegalStateException` on `updateAAD` | Called after `update`, after finalization, before `init`, or mode/provider does not accept AAD in current state | Initialize cipher and supply all AAD before feeding any payload/ciphertext |
| `IllegalArgumentException` | Passing `null` AAD `byte[]` or invalid offset/length | Validate data and array bounds before calling |
| `AEADBadTagException` from `doFinal` | AAD/key/IV/ciphertext/tag differs from encryption, or data truncated/altered | Reject entire record; verify byte contract and metadata; never bypass authentication |
| Payload decrypts accurately yet header changes undetected | Header omitted from AAD on both sides, or application reads a field different from what was authenticated | Audit exact bytes fed to `updateAAD` and which metadata is actually protected |
| Reordering header fields breaks decryption | AAD serialization/canonicalization differs between sides | Define explicit byte representation and add round-trip tests |
| Tag appears longer than expected 16 bytes | Confusing `GCMParameterSpec` tag length **bits** with bytes, or slicing tag wrongly | Verify 128-bit = 16-byte tag and how `doFinal` returns `ciphertext+tag` |
| Replayed record still decrypts cleanly | AEAD protects integrity, **does not prevent replay itself** | Use authenticated sequence/messageId/timestamp with application duplicate checks |

Never "fix" `AEADBadTagException` by deleting `updateAAD` from both sides just to make decryption succeed; that defeats header protection. Nor switch GCM to an unauthenticated mode merely to avoid tag errors.

## 10. Self-Check Checklist and Exercises

Before deploying AEAD with AAD, answer:

- Which components are **authenticated only** (AAD), which are **encrypted and authenticated** (payload), and which fields sit outside AEAD scope?
- Under which encoding/schema is AAD serialized to bytes? Do both sender and receiver produce the **exact same byte sequence** and order?
- Is `updateAAD` called **before** `update`/`doFinal` on **both sides**?
- Is a fresh, per-key unique IV generated for every encryption? How is the key stored and resolved?
- Is plaintext exposed/used **only after** decryption `doFinal` succeeds?
- Are headers used for authorization, routing, or key lookup re-checked after tag validation?
- Are wrong AAD, wrong IV, flipped ciphertext/tag bytes, truncated payload, wrong version, and replay all tested?

**Exercise 1:** add a `contentType=application/json` field to AAD with explicit length encoding; make the decryptor use the same bytes, then alter `contentType` while keeping ciphertext/tag unchanged to verify failure.

**Exercise 2:** switch payload processing from `doFinal(plaintext)` to multiple `update` calls ending with `doFinal`. Keep `updateAAD` before all `update` calls and compare round-trip results; try calling `updateAAD` after `update` to observe the provider's state exception.

**Exercise 3:** build a record with version, keyId, IV, AAD, and ciphertext/tag. Establish stable serialization/canonicalization rules; test after persisting/reading via file or database. Never put real AES keys into exercises or source repositories.

## 11. Official Documentation

- [Cipher — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): `updateAAD`, `update`, `doFinal`, requirement for GCM/CCM to feed all AAD before data and tag checking.
- [GCMParameterSpec — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): IV and tag length in bits.
- [AEADBadTagException — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/AEADBadTagException.html): authentication tag mismatch error during AEAD decryption.
- [Java Security Developer's Guide — Oracle](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): provider architecture and cryptographic engines, including AEAD modes.