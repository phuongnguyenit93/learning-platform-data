# 6.6 AEAD, AES/GCM/NoPadding, and the Role of the Authentication Tag

Encrypting data solely for secrecy is **not enough** when data can be altered by an attacker. Ciphertext can still be modified, transplanted across contexts, or swapped with another ciphertext; an application needs to know whether it should **accept and process** the decrypted result. **AEAD (Authenticated Encryption with Associated Data)** combines encryption confidentiality and key-based integrity/authenticity verification in a single unified design. In Java, the common practical variant is **`AES/GCM/NoPadding`**.

This lesson explains AEAD, AES-GCM, the **authentication tag**, nonce/IV, AAD, and safe `Cipher` usage rules. The Java 17+ example in Section 8 demonstrates legitimate data recovery and rejection of tampered inputs.

## 1. What Problem Does AEAD Solve?

### 1.1. Confidentiality and Integrity Are Distinct Requirements

Suppose an application sends a transfer record between services:

~~~text
Plaintext P = "amount=100;currency=VND"
                 |
                 v
              Encrypt
                 |
                 v
Ciphertext C transmitted over the network
~~~

Encryption provides **confidentiality**: someone without the proper key cannot read the plaintext. However, **not every encryption mode authenticates the ciphertext on its own**. With unauthenticated encryption schemes, an attacker can flip bytes, splice blocks, or swap messages and cause the receiver to process forged data without reliable cryptographic evidence that the ciphertext was altered.

AEAD adds an **authentication tag**. The receiver must accept the message only when tag verification succeeds with the **matching key, nonce, ciphertext, and AAD**.

| Property | Meaning in AEAD |
| --- | --- |
| **Confidentiality** | Hides plaintext from anyone without the decryption key. |
| **Integrity** | Detects unauthorized modification of ciphertext and authenticated associated data. |
| **Key-based authenticity** | Gives the receiver evidence that a valid message/tag was produced by a party authorized to use the shared secret key (assuming the key is uncompromised). |
| **Associated-data integrity** | Critical public metadata is still authenticated even though unencrypted. |
| **Does not prevent replay on its own** | An attacker can replay a valid packet verbatim unless the protocol tracks sequence numbers, message nonces, sessions, or request IDs. |
| **Does not prove individual identity** | If multiple parties share the symmetric key, the tag does not identify which party created the message. It does not replace digital signatures/PKI or identity authentication. |

**Important:** "Authenticated" in AEAD means **key-based cryptographic authentication**, not automatically "the user is logged in", "correct tenant", "authorized to transfer funds", or "definitely issued by company X". Applications must still enforce identity authentication, authorization, and key-source trust.

### 1.2. Why Not Just Use AES in Any Mode?

`AES` is only the block cipher primitive; application security also depends on the **mode**, IV/nonce handling, and integrity verification:

- **AES-ECB** fails to protect repeating data patterns; it must not be used for application data.
- **AES-CBC** with padding provides encryption only when used alone; it requires a proper authentication mechanism and careful error handling. Bolting padding/decryption checks onto a protocol ad hoc easily introduces vulnerabilities.
- **AES-CTR** protects confidentiality when nonces are proper, yet ciphertext remains controllably malleable without authentication.
- **AES-GCM** is an **AEAD** mode combining counter-style encryption with a GCM authentication tag; suitable for most new needs when keys and nonces are managed properly.
- **ChaCha20-Poly1305** is also AEAD; algorithm selection must follow your specific library, environment, standards, and protocol rather than mixing components across algorithms.

Prefer **standard AEAD primitives from trusted libraries**; never invent an "AES + hash" construction or assume `SHA-256(ciphertext)` prevents forgery, since an unkeyed digest has no secret key.

## 2. Mathematical Model of AES-GCM

AES-GCM takes the following inputs and outputs:

| Symbol | Name | Must Be Secret? | Role |
| --- | --- | --- | --- |
| `K` | AES secret key | **Yes** | Shared secret of parties permitted to encrypt/decrypt. |
| `N` | Nonce/IV | **No**, but must be unique per encryption under the same key | Seeds GCM encryption state; violating nonce rules can catastrophically break security. |
| `P` | Plaintext | Yes, if the application needs secrecy | Content to be encrypted. |
| `A` | AAD (Additional Authenticated Data) | **No** need for secrecy | Metadata to be bound and authenticated alongside ciphertext. |
| `C` | Ciphertext | No | Encrypted form of `P`, same length as `P` in AES-GCM. |
| `T` | Authentication tag | No | Authentication tag over ciphertext and AAD in the context of key and nonce. |

Conceptual model:

~~~text
                    K (secret key)         N (unique nonce per K)
                             \              /
                              \            /
P (plaintext) ----------------> AES-GCM Encrypt <------- A (AAD)
                                      |
                                      v
                              C (ciphertext) + T (tag)

K, N, A, C, T ----------------> AES-GCM Decrypt/Verify
                                      |
                            +---------+---------+
                            |                   |
                       valid tag           invalid tag
                            |                   |
                        return P           error / reject
~~~

In functional notation:

~~~text
(C, T) = AEAD_Encrypt(K, N, P, A)
P      = AEAD_Decrypt(K, N, C, T, A), if tag is valid
ERROR  = AEAD_Decrypt(K, N, C, T, A), if tag is invalid
~~~

**There is no "decrypt succeeds then optionally check the tag" step.** Accepting data must depend on successful authentication. When using streaming APIs or providers that may emit intermediate output, **never use unauthenticated plaintext** for business logic, DB writes, API responses, or downstream calls before verification finishes.

## 3. What Does `AES/GCM/NoPadding` Mean in JCA/JCE?

In Java, calling:

~~~java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
~~~

The transformation string has three components:

| Component | Meaning |
| --- | --- |
| `AES` | Advanced Encryption Standard symmetric block cipher; keys are typically 128/192/256 bits per system policy. |
| `GCM` | Galois/Counter Mode: an AEAD mode providing encryption and an authentication tag. |
| `NoPadding` | GCM does not use PKCS#5/PKCS#7-style plaintext padding; data need not be padded to a 16-byte multiple. |

GCM pairs **CTR-style** keystream generation for encryption with finite-field authentication, commonly described via **GHASH** and a tag block. Java developers **do not compute GHASH, counters, or tags manually**; `Cipher` and the provider handle the algorithm internals. Reimplementing them manually to "optimize" is prone to severe mistakes.

In standard usage with common JCE providers:

- Configure a 128-bit tag via `new GCMParameterSpec(128, nonce)`.
- On **encryption**, `Cipher.doFinal(plaintext)` returns **ciphertext followed by the tag**; this lesson's example stores them contiguously as `ciphertextAndTag`.
- On **decryption**, pass the combined **ciphertext + tag** to `doFinal(...)`; the provider checks the tag and returns plaintext only if authentication succeeds.
- Because GCM uses `NoPadding`, an `n`-byte plaintext yields an `n`-byte ciphertext; total `ciphertextAndTag` length is `n + 16` bytes for a 128-bit tag.
- **A tag is not a nonce**: a nonce is chosen for one encryption invocation, whereas a tag is the authentication output bound to the content and AAD.
- **A tag is not a SHA-256 hash**: you cannot replace it by calling `MessageDigest.digest(...)`, truncating a few hash bytes, and calling it a tag.

### 3.1. What Does the Authentication Tag Protect?

Suppose the receiver has `K, N, A, C, T`. If any authenticated input is altered without the right key to forge a valid tag, GCM verification fails with overwhelming probability per the algorithm's security bounds.

Illustrative scenarios:

| Modification on Receiver Side | Expected Behavior |
| --- | --- |
| **Ciphertext `C` altered by one byte** | Tag mismatch; rejected. |
| **Tag `T` altered by one byte** | Tag mismatch; rejected. |
| **AAD `A` altered** | Tag mismatch; rejected; unencrypted AAD is still authenticated. |
| **Nonce `N` altered** | Decrypting under a different nonce fails authentication; rejected. |
| **Wrong key `K` used** | Cannot verify valid tag; rejected. |
| **Valid packet re-sent verbatim with matching AAD and key** | Tag **remains valid**. AEAD has no built-in memory of prior messages. |

With Java `Cipher`, a bad tag on GCM decryption typically throws **`AEADBadTagException`** (a subclass of `BadPaddingException`). Never catch it and silently keep using the data. Never compare tags manually with `==`, `Arrays.equals`, or compute tags yourself—**the provider verifies the tag inside `doFinal`**.

A 128-bit tag is the standard choice. Longer tags make forgery harder within the proper security model; never arbitrarily shorten the tag or let both sides disagree on tag length. **A fixed-length tag does not make forgery mathematically impossible**, rather providing bounded security guarantees when assumptions like unique nonces and key usage limits are respected.

## 4. Nonce/IV: Can Be Public, Must Never Be Reused Under the Same Key

### 4.1. Key Rule

**With AES-GCM, never encrypt two different messages with the same (key, nonce) pair.** Reusing a nonce under the same key can expose relationships between plaintexts and enable tag forgery; you cannot "fix" the damage merely by storing a longer tag.

Java typically uses a **96-bit = 12-byte nonce** for GCM. The nonce **does not need to be secret** and can be placed right at the front of the packet. The decryptor needs the exact same nonce to verify successfully.

~~~text
Key K_A:   N_001, N_002, N_003, ...   (each nonce used only once for encryption)
Key K_B:   has its own nonce space
BUG:       Encrypt(K_A, N_001, P1) and Encrypt(K_A, N_001, P2)
~~~

**Two common nonce strategies:**

1. **Random 96-bit nonce:** generated with `SecureRandom` in demo code. Each invocation has negligible collision probability at moderate volume, yet **does not guarantee absolute uniqueness**. At high record counts/rates, you need key usage limits, collision risk monitoring, and policy-driven key rotation.
2. **Structured counter/identifier nonce:** design an instance/partition prefix paired with a unique counter, with coordination and persistence across restarts. You must prevent two processes sharing a key from issuing the same nonce. Do not invent one without explicit allocation rules, state persistence, volume limits, and thorough testing.

**Never use** a constant nonce for all requests, a timestamp-derived nonce lacking uniqueness guarantees, weak random indices, or `new Random()` to generate nonces. If multiple processes share an AES key, nonce uniqueness must be solved **system-wide**, not just within a single process.

**Do not confuse:** a GCM nonce satisfies the **encryption uniqueness** requirement; a protocol-level nonce/request ID used for anti-replay is a separate concern despite sharing a name. AES-GCM nonce uniqueness **does not automatically prevent replay** of a valid ciphertext + tag.

### 4.2. Why Can't You Decrypt If the Nonce Is Lost?

The nonce is an input parameter to GCM; decryption requires both the **original key and original nonce**. If only ciphertext + tag are saved and the nonce is discarded, a random nonce cannot be reconstructed later. Therefore, storage formats typically include the nonce alongside ciphertext/tag in the record.

To support key rotation, records also need a **key identifier** or secure key-lookup mechanism. Key IDs can be public, yet must be context-validated/authenticated to avoid key confusion or downgrade attacks. Never ship the AES key inside the data packet.

## 5. AAD: Metadata Unencrypted Yet Protected Against Tampering

**AAD (Additional Authenticated Data)** consists of bytes fed into tag computation that are **not present in the ciphertext**. The receiver must reconstruct the **exact same AAD byte sequence** during decryption.

For example, when encrypting a transaction value:

~~~text
P   = "amount=100;currency=VND"  // must remain secret
AAD = "v1|tenant=blue|type=transfer"  // allowed to be public

Encrypt(K, N, P, AAD) → C + T

Decrypt(K, N, C, T, "v1|tenant=red|type=transfer") → tag error
~~~

AAD binds ciphertext to a **context**. If encrypted data from tenant A is moved to tenant B, and tenant B decrypts using AAD containing tenant B from a **trusted context**, the tag will mismatch. However, AAD cannot replace tenant authorization checks: if an application blindly **trusts a tenant value sent by an attacker inside the same packet**, tag verification alone does not enforce authorization.

Fields commonly considered for AAD when appropriate to the design:

- **Format/protocol version** to prevent format or algorithm confusion.
- **Record ID, object ID, tenant ID** when ciphertext must be bound to a specific entity/context.
- **Content type, endpoint, key purpose** if one key serves multiple flows requiring domain separation.
- **Other identifying metadata** requiring integrity without secrecy.

Notes:

- AAD **is not secret**: never place sensitive data in AAD thinking it is encrypted.
- **One byte different means different AAD**: UTF-8/UTF-16, newlines, JSON field ordering, whitespace, number formatting, and Unicode normalization all matter. Design a clear **canonical** byte representation.
- In the Java API, call `cipher.updateAAD(aad)` **after `init` and before feeding plaintext/ciphertext to `update` or `doFinal`**. Wrong call ordering triggers API errors.
- If there is no metadata to bind, AAD can be empty; do not force dummy AAD. Yet if the protocol requires authenticating metadata, omitting `updateAAD` is a design flaw.
- AAD is used for both encryption and decryption; **both sides must match 100% byte-for-byte**. Do not switch ad hoc from string to JSON without versioning.

## 6. Wire/Storage Format: Where Do Nonce, Ciphertext, and Tag Live?

In the Java example, the binary record has the layout:

~~~text
+-------------------+--------------------------+----------------+
| nonce (12 bytes)  | ciphertext (n bytes)     | tag (16 bytes) |
+-------------------+--------------------------+----------------+
<--------------------- packet = 12 + n + 16 bytes --------------->
~~~

The combined `nonce + ciphertext + tag` can be **Base64-encoded** to embed inside JSON. Base64 is strictly an **encoding**, providing no security on its own. AAD in the example is a byte string derived from **application context**, transmitted or reconstructed separately rather than placed inside the packet.

In systems with multiple versions and keys, real-world records typically need extra metadata, such as:

~~~text
version | keyId | nonce | ciphertext | authenticationTag
             \                       /
              format metadata with defined authentication rules
~~~

If `version` or `keyId` governs how decryption proceeds, bind that metadata into **AAD and/or a trusted verification contract** so attackers cannot swap contexts. Specifications must define exact field types/lengths, byte order, payload limits, nonce allocation mode, and key resolution rules. **Never guess** where the tag sits if another system stores the tag separately from ciphertext; that is a protocol format difference, not license to drop the tag.

**Size example:** ASCII plaintext `"amount=100;currency=VND"` is 23 bytes. With a 16-byte AES-GCM tag and 12-byte nonce, the demo packet is **51 bytes** (`12 + 23 + 16`). Packet sizes vary if headers or extra fields are added.

## 7. Security Preparation Before Coding

1. **Key:** generate via `KeyGenerator.getInstance("AES")` with `SecureRandom`. AES-128 or AES-256 can be chosen per requirements and system policy; the sample below uses AES-128 for broad compatibility—**never store keys in source code**.
2. **Nonce:** fresh 12 bytes per encryption under the same key; generated by CSPRNG in the example. For multi-process production, design system-wide non-repeating nonce allocation.
3. **Tag:** use 128 bits via `GCMParameterSpec(128, nonce)` on both sides.
4. **AAD:** define deterministic bytes using `StandardCharsets.UTF_8` and a consistent format convention; derive critical business attributes from verified context.
5. **Cipher:** instantiate a separate `Cipher` per operation; `Cipher` objects are stateful and must not be shared unsynchronized across requests/threads.
6. **Errors:** never return plaintext if authentication fails. Do not let clients distinguish fine-grained tag/key/AAD failures in API responses; log only necessary metadata, avoiding plaintext, secrets, keys, or sensitive details.
7. **Data limits:** validate packet length before allocating/decrypting; enforce size caps per business logic and system GCM limits. One `doFinal` over the whole payload fits short examples; large payloads require dedicated chunked/record AEAD framing authenticating each chunk and its ordering.

## 8. Complete Java 17+ Example: Encrypt, Decrypt, and Detect Tampering

The example runs with the **standard JDK** and zero external dependencies. It creates an ephemeral key, generates a fresh nonce for **one encryption**, prepends the nonce to `ciphertextAndTag`, then tests valid decryption and tampered variants. The stdout lines below **print no random keys, nonces, or ciphertexts**, making them deterministic to verify.

Save with the exact name **`AeadGcmDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class AeadGcmDemo {
    static final int NONCE_BYTES = 12;
    static final int TAG_BITS = 128;
    static final SecureRandom RANDOM = new SecureRandom();

    static byte[] encrypt(SecretKey key, byte[] plain, byte[] aad)
            throws GeneralSecurityException {
        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);
        byte[] ciphertextAndTag = cipher.doFinal(plain);

        // Example format: 12-byte nonce || ciphertext || 16-byte tag.
        return ByteBuffer.allocate(nonce.length + ciphertextAndTag.length)
                .put(nonce)
                .put(ciphertextAndTag)
                .array();
    }

    static byte[] decrypt(SecretKey key, byte[] packet, byte[] aad)
            throws GeneralSecurityException {
        if (packet.length < NONCE_BYTES + TAG_BITS / 8) {
            throw new IllegalArgumentException("Packet too short");
        }

        ByteBuffer source = ByteBuffer.wrap(packet);
        byte[] nonce = new byte[NONCE_BYTES];
        source.get(nonce);
        byte[] ciphertextAndTag = new byte[source.remaining()];
        source.get(ciphertextAndTag);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);

        // Returns plaintext only on success; invalid tag throws AEADBadTagException.
        return cipher.doFinal(ciphertextAndTag);
    }

    static boolean rejected(SecretKey key, byte[] packet, byte[] aad)
            throws GeneralSecurityException {
        try {
            decrypt(key, packet, aad);
            return false;
        } catch (AEADBadTagException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128, RANDOM);
        SecretKey key = generator.generateKey();

        byte[] plain = "amount=100;currency=VND"
                .getBytes(StandardCharsets.UTF_8);
        byte[] aad = "v1|tenant=blue|type=transfer"
                .getBytes(StandardCharsets.UTF_8);
        byte[] packet = encrypt(key, plain, aad);

        System.out.println("Plain bytes     = " + plain.length);
        System.out.println("Packet bytes    = " + packet.length);
        System.out.println("Tag bytes       = " + TAG_BITS / 8);
        System.out.println("Restored        = " + new String(
                decrypt(key, packet, aad), StandardCharsets.UTF_8));

        byte[] changedCiphertext = packet.clone();
        changedCiphertext[NONCE_BYTES] ^= 1;
        byte[] changedTag = packet.clone();
        changedTag[changedTag.length - 1] ^= 1;
        byte[] changedNonce = packet.clone();
        changedNonce[0] ^= 1;

        System.out.println("Changed data    = " +
                rejected(key, changedCiphertext, aad));
        System.out.println("Changed tag     = " +
                rejected(key, changedTag, aad));
        System.out.println("Changed nonce   = " +
                rejected(key, changedNonce, aad));
        System.out.println("Changed AAD     = " + rejected(key, packet,
                "v1|tenant=red|type=transfer"
                        .getBytes(StandardCharsets.UTF_8)));

        SecretKey wrongKey = generator.generateKey();
        System.out.println("Wrong key       = " +
                rejected(wrongKey, packet, aad));
    }
}
~~~

Compile and run:

~~~bash
javac AeadGcmDemo.java
java AeadGcmDemo
~~~

Expected output:

~~~text
Plain bytes     = 23
Packet bytes    = 51
Tag bytes       = 16
Restored        = amount=100;currency=VND
Changed data    = true
Changed tag     = true
Changed nonce   = true
Changed AAD     = true
Wrong key       = true
~~~

**Accurate explanation:**

1. `encrypt` generates a 12-byte nonce using `SecureRandom`, creates an AES-GCM `Cipher` with a 128-bit tag, and supplies AAD before encrypting.
2. `doFinal(plain)` produces ciphertext concatenated with a 16-byte tag. The packet is **nonce + ciphertext + tag**; 23-byte plaintext yields a 51-byte packet.
3. `decrypt` reads the nonce from the packet, sets the same tag length and AAD, and passes `ciphertextAndTag` into `doFinal`. With a valid tag, exact plaintext bytes are returned.
4. Flipping the first ciphertext byte, last tag byte, a nonce byte, or changing the tenant in AAD causes verification failure; `rejected` catches `AEADBadTagException`, so the `Changed ...` lines print `true` (meaning **rejected**, not authenticated successfully).
5. Generating a different AES key yields `Wrong key = true`, proving an attacker cannot decrypt with another key merely by knowing the nonce/ciphertext/tag.

**This is a learning example:** the ephemeral key vanishes after execution, the random nonce has no cross-instance coordination, and the packet omits version/key ID. Real systems must add key storage rules, nonce allocation, schema versioning, payload limits, and replay protection where needed. The code demonstrates tag verification principles, not a complete ciphertext persistence library.

## 9. Role of the Tag Compared to MAC and Digital Signatures

AES-GCM is **AEAD**: a party holding the secret key can create ciphertext/tag; anyone holding the same key can decrypt and verify. The tag is integrated into the GCM operation, **not a standalone object proving an individual signer's identity**.

| Mechanism | Hides Plaintext? | Authenticity / Integrity? | Who Can Verify? | Notes |
| --- | --- | --- | --- | --- |
| **AES-GCM (AEAD)** | **Yes**, if key is secret and nonce is proper | **Yes**, for ciphertext and AAD | Parties holding the matching secret key | Tag is bound to encryption; nonce must be unique per key |
| **AES-CTR without MAC** | Yes assuming proper mode/nonce | **No** | No tag check step | Ciphertext can be deliberately modified |
| **HMAC-SHA256** | **No** | Yes, under shared key | Parties holding the HMAC secret | HMAC does not decrypt or encrypt |
| **Digital signatures (Ed25519, RSA-PSS...)** | **No** | Yes, bound to signing key and message | Anyone with the trusted public key | Signed with private key; meant for public verification |
| **Unkeyed SHA-256** | No | Produces digest; does not authenticate origin alone | Anyone can compute it | Does not replace tag, HMAC, or signature |
| **Base64** | No | No | Anyone can encode/decode | Text representation of packet only |

**Do not "upgrade" AES-GCM by appending `SHA-256(ciphertext)`** and discarding the tag. An unkeyed digest does not stop an attacker from modifying ciphertext and recomputing the digest. Conversely, there is no need to bolt a separate HMAC onto GCM just to "protect the tag better" without a formal protocol spec and independent review; properly using standard AEAD suffices for its purpose.

## 10. Four Typical Application Scenarios

### 10.1. Encrypting a Database Record

~~~text
DB row:
  id = 42
  tenant = blue
  keyId = k2026-10
  nonce = ...
  ciphertextAndTag = ...

Decrypt:
  key = KMS.resolve(keyId)
  aad = canonical("v1", tenant from trusted context, row id)
  plaintext = AES-GCM-Decrypt(key, nonce, ciphertextAndTag, aad)
~~~

If someone swaps ciphertexts between two rows while the application populates `row id`/tenant from the **verified row/context** into AAD, swapping will fail with an invalid tag. You must bind `keyId` and version properly to prevent attackers from controlling untrusted input metadata. Encryption does not replace DB read permissions, disk encryption, or access policies.

### 10.2. Receiving Replayable API Requests

A valid AES-GCM packet **can be re-sent** using the same key, nonce, ciphertext/tag, and AAD. The tag contains no history of prior receipts. For APIs that trigger payments or mutate state, bind request IDs, timestamps/expiry, or sequence numbers into the protocol/AAD, **then validate freshness and prevent reuse via trusted state**. Merely placing a timestamp into AAD without checking time or recording seen IDs still fails to stop replay.

### 10.3. Encrypting Large Files or Streaming Data

Never load huge files into RAM just to make one `doFinal` call when system memory cannot support it. You can use `Cipher`'s `update(...)` and `doFinal(...)` APIs per protocol rules, **provided you never trust/consume intermediate plaintext before the tag completes**. Large-file AEAD chunk/record designs generally need:

- A unique nonce per chunk under the same key;
- Binding **file ID, chunk index, total chunks, and position/order** via AAD;
- Verifying **all chunks and global finality metadata** to prevent truncation, reordering, or chunk substitution;
- Volume limits and proper key quota management.

You cannot simply treat "each chunk decrypted" as proof the entire file is intact if an attacker can delete or permute chunks.

### 10.4. Encrypted Data Base64-Encoded Inside JSON

~~~json
{
  "version": 1,
  "keyId": "k2026-10",
  "payloadBase64": "..."
}
~~~

In the illustrative example, `payloadBase64` is Base64 of **nonce || ciphertext || tag**. The API must define AAD rules and verify version/key ID per contract. **Base64 decoding is not AES-GCM decryption**; matching key, nonce, ciphertext, tag, and AAD are still required.

## 11. Common Security and API Mistakes

| Mistake | Why It Is Wrong / Dangerous | Proper Practice |
| --- | --- | --- |
| **Reusing same key + nonce on encrypt** | Can break both confidentiality and GCM authenticity. | Allocate unique nonces per key, monitor quotas, rotate keys, and coordinate across processes. |
| **Using a 12-byte all-zero nonce for every message** | Reuses the exact same nonce under the same key on every run. | Generate/coordinate a fresh nonce per encryption; nonces need not be secret. |
| **Thinking the nonce must be hidden** | Losing the nonce makes decryption impossible; hiding it does not excuse reuse. | Store/transmit nonce with ciphertext/tag while enforcing uniqueness. |
| **Dropping the 16-byte tag when saving ciphertext** | Cannot verify ciphertext authenticity; decryption will fail. | Preserve ciphertext **and** tag intact per format. |
| **Comparing tags manually with Java `==`/`equals`** | GCM authentication must be performed by the primitive with key and nonce; naive comparison is meaningless. | Pass full ciphertext+tag into `Cipher.doFinal` on decrypt. |
| **Catching `AEADBadTagException` and using buffered output anyway** | Unauthenticated data can drive harmful business side effects. | Reject the entire message; never commit side effects from unauthenticated plaintext. |
| **Confusing AAD with ciphertext** | AAD is unencrypted, exposing sensitive fields placed there. | Put only public metadata needing integrity in AAD; confidential plaintext goes into encrypt. |
| **Mismatched AAD across sides** | Tag fails due to encoding, field order, or tenant mismatch. | Specify canonical AAD bytes, UTF-8, and matching schema/version. |
| **Calling `updateAAD` after feeding input to `update`** | Violates AEAD API ordering. | `init` → `updateAAD` → `update/doFinal`. |
| **Using `AES/GCM/NoPadding` while believing "NoPadding = no tag"** | "NoPadding" only means no plaintext padding; GCM still creates a tag. | Always verify the full-length tag. |
| **Encrypting with 128-bit tag, decrypting with 96-bit tag** | Both sides disagree on tag length/format; verification fails. | Fix `GCMParameterSpec` in the protocol. |
| **Sharing one `Cipher` instance across threads/requests** | Cipher state and IV/tag get corrupted or raced. | Create/init separately per operation; never share mutable `Cipher` across threads. |
| **Assuming AES-GCM prevents replayed requests** | A valid tag for an old packet stays valid. | Use protocol state for replay defense with checked expiry/sequence/request IDs. |
| **Hardcoding keys or logging keys** | Key compromise invalidates all protected records. | Use KMS/secret manager, access control, rotation, auditing; never log secrets. |
| **Omitting version and key ID management** | Breaks decryption after rotation and invites protocol confusion. | Records carry schema version/key ID, with context-sensitive metadata authenticated. |
| **Dumping full authentication error details in responses** | Creates information leaks about key/data state useful to attackers. | Return safe generic errors; maintain controlled internal logs free of secrets. |

**On error handling:** `IllegalArgumentException` for a short packet in the demo is an **input-format check**, distinct from `AEADBadTagException` on tag mismatch. Production systems should normalize both into an invalid-request error at untrusted boundaries while keeping internal telemetry free of sensitive data.

## 12. Self-Check Questions (with Answers)

**Q1.** A network eavesdropper sees a 12-byte nonce, ciphertext, and 16-byte tag. Can they decrypt immediately just because the nonce is not secret?

**A:** No. The nonce is a public parameter; the matching AES key is needed to decrypt and verify the tag. Security depends on the secret key, proper nonce discipline, and algorithm strength.

**Q2.** Is AAD kept secret in AES-GCM? What happens if AAD changes from `tenant=blue` to `tenant=red` while ciphertext/tag stay identical?

**A:** AAD **is not encrypted**. Changing AAD bytes causes tag verification to fail when decrypting under the same key/nonce/ciphertext/tag. Applications must take the tenant from a trusted context and check authorization separately.

**Q3.** With 128-bit-tag AES-GCM, 23-byte plaintext, and 12-byte nonce, how long is the `nonce || ciphertext || tag` packet?

**A:** `12 + 23 + 16 = 51` bytes. Since GCM uses `NoPadding`, ciphertext has the same length as plaintext in the example format.

**Q4.** A service encrypts two different records with the same key and same nonce, using a different AAD for each record. Is that secure?

**A:** **No.** Different AAD does not substitute for nonce uniqueness under the same key. Every encryption under a key must avoid repeating the `(key, nonce)` pair.

**Q5.** `decrypt` throws `AEADBadTagException`. Should you return any plaintext that might have been processed before the exception occurred?

**A:** No. Discard all unauthenticated data; never use intermediate plaintext in business calculations, commit transactions, or write it elsewhere before the tag succeeds.

**Q6.** A client re-sends verbatim a valid GCM payment packet that the server processed yesterday. Will the tag fail because the request is old?

**A:** No. If key/nonce/AAD/ciphertext/tag still match, the tag remains valid. The server needs anti-replay tracking via request IDs/sequences and expiration windows.

**Q7.** Should you attach `SHA-256(ciphertext)` alongside the AES-GCM tag to verify data was not modified?

**A:** Unnecessary for that goal. Unkeyed SHA-256 does not stop someone from modifying ciphertext and re-hashing it. The AES-GCM tag is already the built-in authentication mechanism; prefer standard primitives and protocols.

**Q8.** When 20 workers encrypt with the same AES key and each worker uses a counter nonce starting at 0, is that safe?

**A:** No, because different workers will emit colliding nonces under the same key. You need nonce partitioning, coordinated counters, or instance prefixes guaranteed not to collide even across restarts—or an evaluated nonce generation strategy with appropriate quotas and key rotation.

## 13. Checklist for Applying AES-GCM in Java

- **Right primitive:** `AES/GCM/NoPadding` via standard `Cipher`; 128-bit authentication tag via `GCMParameterSpec`, never replacing the tag with a checksum/hash.
- **Right secret:** AES key with proper entropy and access control, never hardcoded; lifecycle/rotation managed.
- **Right nonce:** 12 bytes in common format; **unique per encryption under the same key**; coordinated system-wide.
- **Right AAD:** only public metadata requiring authentication; deterministic UTF-8/canonical bytes, bound to trusted context, `updateAAD` called before data.
- **Right wire format:** preserve nonce, ciphertext, tag, and any needed version/key ID metadata; do not confuse Base64 with security.
- **Right decryption:** pass full ciphertext+tag to `doFinal`, use plaintext only after verification succeeds; reject all tag failures.
- **Right protocol:** add replay defense, size limits, authorization/identity checks, safe error handling, and monitoring; AEAD does not replace other security layers.
- **Right operations:** for large data, design chunked/record AEAD with authenticated ordering/indices and completion checks; never consume streaming plaintext before tag verification.

**Conclusion:** **AEAD = authenticated encryption with associated data**. With `AES/GCM/NoPadding`, **ciphertext** protects plaintext confidentiality, the **authentication tag** detects modifications to ciphertext and AAD, the **nonce** is a public input that must remain unique under the same key, and **AAD** binds critical metadata without hiding it. In Java, tag verification occurs inside `Cipher.doFinal` on decryption: **if the tag is invalid, there is no trustworthy data to process**.