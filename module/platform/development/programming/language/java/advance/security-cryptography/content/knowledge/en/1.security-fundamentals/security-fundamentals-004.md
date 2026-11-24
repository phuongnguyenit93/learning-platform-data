# 1.4 Distinguishing Encryption, Hashing, MAC, Digital Signatures, and Encoding

In Java security, five concepts often transform data into an unreadable-looking byte sequence, yet they solve **different problems**. Calling all of them "encryption" leads to dangerous designs: using Base64 to hide secrets, using SHA-256 instead of authentication, or encrypting data without detecting tampering.

## 1. Objectives and Mental Model

After this lesson, you should be able to answer:

- What should be used when you want to **keep data confidential** from unauthorized readers?
- What should be used to create a **fingerprint** of data to check for changes, and when can that fingerprint be trusted?
- What should be used to know a message came from a party **sharing the same secret key** and has not been modified?
- What should be used to let a third party verify who signed using a **public key**?
- What should be used to convert binary bytes into a convenient string for storage/transmission (Base64, hex, UTF-8)?

First, distinguish the security goals:

| Goal | Question to Answer | Example |
| --- | --- | --- |
| **Confidentiality** | Can someone without the key read the content? | Hiding customer info in backups |
| **Integrity** | Was the content modified relative to the accepted version? | Detecting a tampered request |
| **Authenticity** | Is there evidence the message originated from a trusted principal/key? | Server verifying a webhook |
| **Public verifiability** | Can someone without a secret key verify using a public key? | Verifying a release signed by the developer |
| **Representation** | Does data need conversion to match a transport/storage format? | Embedding bytes in JSON as Base64 |

**Rule:** Hard-to-read output **does not mean** the output is protected. To pick the right technique, start from the goal, the adversary, and who holds the keys.

## 2. Comparison Table of the Five Techniques

| Technique | Key and Main Operation | Output | Core Guarantee | Does Not Guarantee by Itself |
| --- | --- | --- | --- | --- |
| **Encryption** | Usually a shared secret key; public-key encryption also exists. `encrypt → decrypt` | Ciphertext; someone with the appropriate key recovers plaintext | **Confidentiality**; AEAD modes like AES-GCM also authenticate and protect encrypted data integrity | Plain encryption does not necessarily authenticate the sender or prevent tampering |
| **Cryptographic hash** | **Keyless**; `hash(message)` | Fixed-length digest, not designed to be reversed | Fingerprinting, change comparison, and many cryptographic constructions | Not secret, does not prove who sent it, does not stop an attacker from altering data and re-hashing |
| **MAC (Message Authentication Code)** | Both sides share a **secret key**; `MAC(key, message)` and `verify` | Authentication tag | **Integrity + authenticity under shared key** | Does not hide content; does not show a third party which key holder created the MAC |
| **Digital signature** | **Private key** to sign; **public key** to verify | Signature accompanying or referencing the message | **Integrity + authenticity under signing key**, verifiable by third parties trusting the right public key | Does not hide content; does not prove identity if the public key is not reliably bound to the principal |
| **Encoding** | **No security key**; `encode ↔ decode` | Different byte/text representation, recoverable knowing the standard | Format and transport compatibility | **No** confidentiality, integrity, or authenticity |

Two points must be kept separate:

1. **Hash differs from MAC:** a SHA-256 digest involves no secret. Anyone can re-hash altered data. HMAC-SHA256 incorporates a secret key in a purpose-built cryptographic construction.
2. **Encryption differs from authenticated encryption:** an algorithm/mode providing only confidentiality may not detect tampering. For new application data, prefer **AEAD (Authenticated Encryption with Associated Data)**, such as AES-GCM.

## 3. Encryption: Protecting Content That Must Stay Secret

### 3.1. Symmetric and Asymmetric Encryption

**Symmetric encryption** uses the same secret key (or directly related keys) to encrypt and decrypt. Practical examples include AES-GCM and ChaCha20-Poly1305. It is suited for encrypting bulk data. In Java, JCA/JCE's `Cipher` supports `AES/GCM/NoPadding`.

**Asymmetric encryption** uses a public/private key pair. For instance, one party uses the recipient's public key to protect a session key, and the recipient uses their private key to open it. RSA-OAEP is an example of public-key encryption, though unsuitable for directly encrypting large payloads. Systems typically use **hybrid/envelope encryption**: protect a session key via public-key cryptography or KMS, and use AES-GCM to encrypt the payload. Key pairs used for **signing** are also asymmetric cryptography, yet are a **different operation** from encryption.

Do not assume "encrypting with private key, decrypting with public key" is a digital signature. Signatures use dedicated algorithms and sign/verify rules, not an inverted key operation of encryption.

### 3.2. Why AES-GCM Is Often a Suitable Choice

Conceptually, one AES-GCM operation is:

~~~text
Inputs:  secret key K, plaintext P, nonce N, associated data AAD
AES-GCM(K, N, P, AAD)  → ciphertext C and authentication tag T
AES-GCM-decrypt(K, N, C, AAD, T) → P or authentication error
~~~

- **Ciphertext** hides the content. **Tag** detects modifications to ciphertext, tag, or AAD when verified with the right key.
- **AAD (Associated Authenticated Data)** is data that is **authenticated but not encrypted**, such as protocol version, message type, or tenant ID, when that metadata must be bound to the ciphertext.
- **The nonce/IV is not a key and need not be hidden**, yet you must **never reuse the same nonce with the same key** in AES-GCM. Nonce reuse can break both confidentiality and authenticity. A common pattern is a 96-bit (12-byte) nonce; under high throughput, design a guaranteed-unique nonce allocation strategy rather than relying solely on collision probability.
- When storing/transmitting, include `version/keyId + nonce + ciphertext + tag` (plus AAD or how to reconstruct AAD identically). These bytes may be **encoded** with Base64; Base64 here is merely a packaging layer.

**Common mistake:** picking `AES/ECB/PKCS5Padding` (leaks data patterns) or encrypting with an unauthenticated mode and assuming "encrypted means unmodifiable." For new systems, use AEAD via vetted protocols/libraries instead of composing primitives by hand.

### 3.3. Keys Require Lifecycle Management

Generate keys from a secure random source; store them in a secret manager/KMS, never hardcoded in repositories or logs. Define who can decrypt, how keys rotate, how old ciphertexts are read by `keyId`, and how keys are revoked. Demo keys generated in the sample program below **disappear when the process exits**, so they must not be used for persistent storage.

## 4. Cryptographic Hash: A Fingerprint, Not a Lockbox

With `H = SHA-256`:

~~~text
m = "abc"
SHA-256(m) = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
~~~

SHA-256 takes arbitrary-length input and returns **256 bits (32 bytes)**. The hex string above has 64 characters because each byte is represented by two hex digits. Good cryptographic hash functions aim for these properties:

- **Preimage resistance:** given a digest, finding a message with that digest is computationally infeasible.
- **Second-preimage resistance:** given a message, finding a different message with the same digest is computationally infeasible.
- **Collision resistance:** finding **any two** distinct messages with the same digest is computationally infeasible. Collisions still exist mathematically because the input space is larger than the output space.

Using a hash to verify a file has not been altered **only provides security against an attacker** if the expected digest arrives via a trusted channel. If an attacker modifies both the file and the digest published alongside it, matching still succeeds. Digests are great for detecting accidental corruption, content addressing, and building protocols; they **do not prove origin** on their own.

**Hash is not encryption:** there is no decryption key to "reverse a hash." Brute-force or lookup-table attacks can still guess low-entropy inputs, like weak passwords, even though SHA-256 cannot be directly inverted.

**Password storage:** never use SHA-256/MD5/SHA-1 directly, even with a custom concatenated salt string. Use an appropriate password/key derivation function such as **Argon2id** (where supported), **scrypt**, or **PBKDF2** with suitable cost parameters and a **unique, random salt per password**. This is password hashing/KDF, distinct from file checksums. MD5 and SHA-1 are also no longer suitable for collision-resistant applications such as digital signatures.

## 5. MAC: Authenticating with a Shared Secret

A **MAC** takes a secret key `K` and message bytes `M`, producing tag `T = MAC(K, M)`. A receiver sharing the key computes the expected tag and compares:

~~~text
Client holds K                          Server holds K
M + K → HMAC-SHA256 → tag             Received M + K → HMAC-SHA256 → tag'
Send M and tag  ────────────────────→   Compare tag and tag' → accept/reject
~~~

**HMAC-SHA256** is a MAC built on SHA-256, **not** a homemade `SHA-256(key + message)`. Naive key-plus-hash concatenations suffer from issues like **length-extension attacks**; use `Mac.getInstance("HmacSHA256")`.

Conditions for a MAC to be meaningful:

1. The key must be **secret, sufficiently strong, and securely distributed**; if leaked, attackers can forge valid tags.
2. Both sides must compute the MAC over the **exact same bytes**: UTF-8 convention, field order, canonicalization, HTTP path, body, timestamp, version number. Two semantically equivalent JSON documents can have different bytes and yield different tags.
3. Compare tags using a standard constant-time library function, such as `MessageDigest.isEqual(...)` for fixed-length tag bytes; never use comparisons that short-circuit at the first differing byte.
4. **MAC does not prevent replay on its own.** A request with a valid tag can be replayed verbatim. Protocols must bind timestamps, nonces/request IDs, validity windows, or anti-replay state stores as needed.

Because **both sides hold the key**, a third party cannot determine which side created the MAC. This is a critical difference from digital signatures: **MAC fits authentication between parties sharing a secret; signatures fit scenarios needing public-key verification**. MACs do not hide message content.

## 6. Digital Signatures: Sign with Private Key, Verify with Public Key

Conceptual workflow:

~~~text
Signer:
  M + privateKey → Sign → signature
  Send M + signature (+ key identification info)

Verifier:
  M + signature + trustedPublicKey → Verify → true/false
~~~

- **Private key** is kept solely by the authorized signer. **Public key** can be distributed for verification.
- A message's signature must **become invalid** if the message changes, when verified with the right public key and a secure algorithm.
- **Ed25519** is a modern signature algorithm supported in Java 17 via `Signature.getInstance("Ed25519")`. Other systems use RSA-PSS or ECDSA for compatibility requirements.
- Digital signatures **do not encrypt the message**. Anyone receiving the plaintext can still read it.
- Mathematical verification only says the signature corresponds to **a key**. To claim "signed by Company X," you must **trust that the public key truly belongs to Company X** via certificates/PKI, pinned keys, a protected registry, or a trusted distribution process.
- Private key loss, key theft, certificate revocation, ownership changes, and signing timestamps are governance concerns **outside the Verify operation**. "Non-repudiation" is a conditional goal, **not an automatic legal conclusion** just because `verify == true`.

Example: releasing `app.jar` with a signature. Users fetch a **trusted public key** to verify that exact file. Unlike HMAC, users **do not possess a key capable of creating signatures**.

## 7. Encoding: Representation for Transport/Storage, Not Security

**Encoding** is a rule for converting representation, for example:

- **UTF-8:** converts character strings to bytes; both sides must agree on encoding when computing hashes/MACs/signatures.
- **Base64:** converts binary bytes into ASCII characters for JSON, configs, or text. `"hello"` (UTF-8) → `aGVsbG8=`; anyone can decode it.
- **Base64URL:** a variant suited for URLs/tokens, using `-` and `_` instead of certain characters; often omits padding depending on protocol. JWT/JWS signatures are usually **encoded** in Base64URL, yet Base64URL does not encrypt the JWT.
- **Hex:** represents each byte as two hexadecimal digits; SHA-256 digests are commonly displayed in hex.

Clearly separate the three layers:

~~~text
Text message    --UTF-8-->    raw bytes
raw bytes       --SHA-256-->  digest bytes   --hex/Base64--> printable string
raw bytes       --AES-GCM-->  ciphertext     --Base64-->     transmittable string
raw bytes       --HMAC-->     tag            --Base64-->     transmittable string
~~~

Decoding Base64 only yields the **input bytes to Base64**. If those bytes are ciphertext, you still need the right key and algorithm to decrypt them; if they are a digest, there is no "unhashing" operation.

**Quick sanity check:** If a stranger can decode a string with a web or local tool without any secret key, that string **is not secured by the encoding layer alone**.

## 8. Runnable Java 17+ Example: Same Data, Five Different Operations

This example uses built-in JDK APIs: `MessageDigest` (hash), `Mac` (MAC), `Cipher` with AES-GCM (authenticated encryption), `Signature` with Ed25519 (signature), and `Base64` (encoding). It generates demo keys via a secure random source, so **no keys are hardcoded**.

Save the complete program as **`CryptoPrimitivesDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;
import javax.crypto.*;
import javax.crypto.spec.*;

public class CryptoPrimitivesDemo {
    static final byte[] DATA = "hello".getBytes(StandardCharsets.UTF_8);

    public static void main(String[] args) throws Exception {
        // 1) Hash: anyone can compute the exact same digest.
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest("abc".getBytes(StandardCharsets.UTF_8));
        System.out.println("SHA-256(abc) = "
                + HexFormat.of().formatHex(digest));

        // 2) HMAC: both sides share a secret key.
        SecureRandom random = new SecureRandom();
        byte[] macKey = new byte[32];
        random.nextBytes(macKey);
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(macKey, "HmacSHA256"));
        byte[] tag = mac.doFinal(DATA);
        System.out.println("HMAC valid = "
                + MessageDigest.isEqual(tag, mac.doFinal(DATA)));
        System.out.println("HMAC altered valid = "
                + MessageDigest.isEqual(tag, mac.doFinal(
                        "HELLO".getBytes(StandardCharsets.UTF_8))));

        // 3) AES-GCM: encryption + authentication; use a fresh nonce for every encryption
        // with the same key. AAD must match between encryption and decryption.
        KeyGenerator aesKeys = KeyGenerator.getInstance("AES");
        aesKeys.init(128, random);
        SecretKey aesKey = aesKeys.generateKey();
        byte[] nonce = new byte[12];
        random.nextBytes(nonce);
        byte[] aad = "header:v1".getBytes(StandardCharsets.UTF_8);

        Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
        encrypt.init(Cipher.ENCRYPT_MODE, aesKey,
                new GCMParameterSpec(128, nonce));
        encrypt.updateAAD(aad);
        byte[] ciphertextAndTag = encrypt.doFinal(DATA);

        Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
        decrypt.init(Cipher.DECRYPT_MODE, aesKey,
                new GCMParameterSpec(128, nonce));
        decrypt.updateAAD(aad);
        System.out.println("AES-GCM restored = "
                + new String(decrypt.doFinal(ciphertextAndTag),
                        StandardCharsets.UTF_8));

        // 4) Ed25519: sign with private key, verify with public key.
        KeyPair pair = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(pair.getPrivate());
        signer.update(DATA);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(pair.getPublic());
        verifier.update(DATA);
        System.out.println("Ed25519 valid = "
                + verifier.verify(signature));

        verifier.initVerify(pair.getPublic());
        verifier.update("HELLO".getBytes(StandardCharsets.UTF_8));
        System.out.println("Ed25519 altered valid = "
                + verifier.verify(signature));

        // 5) Base64: no key needed, anyone can encode/decode.
        String encoded = Base64.getEncoder().encodeToString(DATA);
        System.out.println("Base64 = " + encoded);
        System.out.println("Base64 decoded = "
                + new String(Base64.getDecoder().decode(encoded),
                        StandardCharsets.UTF_8));
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac CryptoPrimitivesDemo.java
java CryptoPrimitivesDemo
~~~

**Stdout** (independent of the random keys since only verification results are printed):

~~~text
SHA-256(abc) = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
HMAC valid = true
HMAC altered valid = false
AES-GCM restored = hello
Ed25519 valid = true
Ed25519 altered valid = false
Base64 = aGVsbG8=
Base64 decoded = hello
~~~

Explaining what was observed:

1. The hash of `abc` is deterministic; it has no key and **cannot tell who created the data**.
2. HMAC succeeds with the exact message and key; changing `hello` to `HELLO` invalidates the tag. Note that the example reuses the `Mac` instance after `doFinal` because JCA resets it to its initialized state.
3. AES-GCM restores `hello` using the right key, nonce, and AAD. If ciphertext/tag/AAD is modified, `doFinal` during decryption fails authentication (typically `AEADBadTagException`); never ignore the exception to use plaintext.
4. The Ed25519 signature is valid for the original message and invalid for the altered message. The verifier only needs a trusted **public key**.
5. Base64 converts `hello` to `aGVsbG8=` and back, requiring **no key** whatsoever.

**Sample limitation:** This program demonstrates primitives, not a complete storage/exchange protocol. Production systems must store nonce and tag with ciphertext; distribute/look up keys securely; define message formats, length limits, identity verification, and error handling that avoids leaking sensitive information.

## 9. Choosing Techniques for Real-World Scenarios

| Problem | Recommended Choice | Why and Conditions |
| --- | --- | --- |
| Storing a backup copy containing secrets | **AES-GCM / AEAD** with keys managed by KMS/secret manager | Parties without the key cannot read it; tag detects tampering, nonce must be unique per key |
| Checking if a downloaded file matches the published release | **SHA-256** if digest comes from a trusted channel; **digital signature** if publisher verification is needed | A standalone hash does not stop an attacker from replacing both file and digest |
| Authenticating webhooks between partner and server sharing a secret | **HMAC-SHA256** over canonicalized request bytes | Protects integrity/authenticity under the secret; add timestamp, request ID, or nonce against replay |
| Publishing updates for many parties to verify independently | **Digital signature** (e.g., Ed25519) | Anyone with the trusted public key can verify without holding signing privilege |
| Representing signature/tag bytes in JSON or URLs | **Base64/Base64URL or hex** | Formatting only; appropriate cryptographic primitives must be applied in an earlier layer |
| Storing password verifiers | **Argon2id/scrypt/PBKDF2** with unique salt | Resists offline password guessing far better than direct fast hashes |
| Sending data securely over a network | **TLS** implemented by a standard library | Protocol combining peer authentication, key exchange, and AEAD; never assemble custom hash/MAC/encryption into a "DIY TLS" |

A system often needs **multiple** techniques together. A simple example for a signed confidential document:

~~~text
Original doc → issuer signs → (document + signature)
             → encrypt with recipient's key → ciphertext
             → Base64 if JSON is needed
Recipient: Base64-decode → decrypt + check tag → verify signature
           using trusted public key → read document
~~~

Which layer owns which responsibility? **Encryption/AEAD** keeps content confidential in transit/at rest; **signature** verifies the signing author; **Base64** packs bytes into transport formatting. Real ordering and framing must follow standard protocols to avoid metadata leaks, validation bugs, or ambiguity over what is signed.

**TLS 1.3 perspective:** a TLS connection uses asymmetric cryptography and certificate/signature authentication during the handshake to agree on session secrets, then uses symmetric AEAD cryptography for application data. Thus, "HTTPS uses RSA to encrypt every HTTP byte" is not an accurate description of modern TLS.

**JWT perspective:** A typical **JWS** token has Base64URL-encoded header/payload/signature sections; **the payload remains readable**, and the signature only protects authenticity/integrity within proper key and validation scope. **JWE** is the encrypted token format. Applications must pin allowed algorithms, verify the right key, and validate claims like `iss`, `aud`, `exp` per context; decoding the payload alone is not token validation.

## 10. Dangerous Misconceptions and How to Fix Them

| Misconception | Consequence | How to Fix |
| --- | --- | --- |
| "Base64/hex is secure encryption" | Anyone can decode the secret | Use encryption for confidentiality; Base64 only represents ciphertext |
| "Having a file's SHA-256 proves who published it" | Attackers swap both file and digest | Fetch digest from a trusted channel or verify a digital signature with a validated public key |
| "Hashing passwords with SHA-256 is enough" | Fast hashes enable massive password guessing rates | Use a proper password KDF, unique salts, and up-to-date cost parameters |
| "HMAC uses SHA-256 so it's just like a hash" | Omitting the key makes forged digests easy to accept | Use standard HMAC construction with a secret key and tag verification |
| "HMAC stops repeated requests" | Attackers replay valid signed requests | Bind timestamps/nonces/request IDs and enforce anti-replay policies |
| "AES-GCM has a nonce so reusing it is fine" | Duplicate nonces under the same key severely break security | Guarantee unique nonces per key, designing allocation for expected load |
| "Ciphertext can never be modified" | Unauthenticated encryption modes can be deliberately altered | Prefer AEAD; reject data if the tag is invalid |
| "`verify(signature) == true` means Company X signed it" | Accepting a public key provided by an imposter | Verify trust chain/identity or pin keys through a clear process |
| "Only different strings count as different messages" | Text normalization, Unicode, JSON serialization, charset mismatches | Canonicalize exact **bytes hashed/MACed/signed** and encoding before computation |

**Distinguishing errors when debugging:** `BadPaddingException`/`AEADBadTagException` at decryption differs from an HMAC mismatch, `signature verification false`, or a Base64 decode error. All share the symptom "cannot read data," yet causes and fixes differ: missing key, wrong nonce/AAD, altered data, bad tag, untrusted public key, or malformed transport string. Never "fix" it by disabling verification or guessing algorithms randomly.

## 11. Self-Check Exercises with Answers

**Scenario A.** An API returns a Base64 string containing a payment card number; any user reading the response can decode it. Has the data been kept confidential?

**Answer:** No. Base64 is a publicly reversible representation. Enforce access control and, if data-layer encryption is required, use proper encryption with key management.

**Scenario B.** A software download page hosts `app.zip` and `SHA256SUMS` in the same directory. If the site is compromised and the attacker replaces both, will SHA-256 detect it?

**Answer:** Not necessarily. The new digest can match the malicious file completely. You need a digest from an independent trusted channel or a digital signature verified via a trusted public key.

**Scenario C.** Servers A and B share a secret to verify webhooks. Party C lacks the secret but knows the HMAC tag of an old request. Can C forge an arbitrary valid new request? Can C resend the old request?

**Answer:** C cannot forge a valid MAC for a new request if HMAC/key are secure; **C can replay the old request verbatim** if the protocol lacks replay protection.

**Scenario D.** Customers must verify update notices signed by the publisher without having the ability to forge valid signed notices. Choose HMAC or digital signature?

**Answer:** Digital signature. The publisher holds the private key; customers hold only the authenticated public key.

**Scenario E.** You encrypt with AES-GCM, keeping the key fixed while reusing the same 12-byte nonce for every record. Is the system secure?

**Answer:** No. The unique-nonce-per-key rule is violated. Change the nonce allocation design and re-evaluate the security of data encrypted under the misused key.

## 12. Takeaways to Apply in Java

- **Need confidentiality:** `Cipher` with AEAD such as `AES/GCM/NoPadding`, plus proper key and nonce management.
- **Need a fingerprint:** `MessageDigest` with SHA-256/SHA-3; authenticity of the expected digest must be ensured **by another trusted source**.
- **Need shared-key authentication:** `Mac` with `HmacSHA256`; canonicalize bytes, protect the secret, and prevent replay at the protocol layer.
- **Need public-key verification:** `Signature` with Ed25519/RSA-PSS/ECDSA per ecosystem; verify the identity/certificate bound to the public key.
- **Need bytes as text:** `Base64` or `HexFormat`, and standardize on `StandardCharsets.UTF_8` when converting text to bytes.

Each operation produces a different kind of evidence. When designing APIs, storage, software updates, or network communication, explicitly state: **which data stays confidential, which bytes are authenticated, which keys are trusted by whom, and who can verify**. Answering those four questions prevents most confusion among encryption, hashing, MACs, digital signatures, and encoding.
