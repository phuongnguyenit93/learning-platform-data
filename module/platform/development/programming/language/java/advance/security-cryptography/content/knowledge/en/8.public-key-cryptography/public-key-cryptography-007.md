# 8.7. RSA-OAEP, Plaintext Size Limits, and the Hybrid Encryption Model

RSA is a public-key algorithm usable in multiple mechanisms. When encrypting with modern RSA, do not take "raw" RSA math or PKCS#1 v1.5 padding and apply it directly to large data. You must use a **standardized encryption scheme**, typically **RSAES-OAEP (Optimal Asymmetric Encryption Padding)**, with an explicitly defined hash algorithm, MGF1, and OAEP label.

However, even properly configured RSA-OAEP is **not a tool for directly encrypting files or long messages**. It limits plaintext size to only a few hundred bytes depending on modulus length and hash. Therefore, the standard application pattern is **hybrid encryption**: generate a random symmetric key to encrypt the data with AEAD (such as AES-GCM), and use RSA-OAEP to **encrypt/wrap the symmetric key** for the recipient.

This lesson helps you answer four practical questions:

1. Why can RSA-OAEP only encrypt short payloads, and how do you compute the exact limit?
2. Which parameters make up OAEP, and why must both sides agree on both the **OAEP hash** and the **MGF1 hash**?
3. In hybrid encryption, what does RSA do, what does AES-GCM do, and what must the envelope format store so the recipient can decrypt?
4. How do you write Java 17+ code using standard JCA/JCE and handle errors when plaintext is too long, the OAEP label mismatches, or ciphertext is modified?

After this lesson, you should be able to compute `mLen ≤ k − 2hLen − 2`, design a hybrid envelope with explicit version/metadata, distinguish **confidentiality**, **integrity**, and **sender authentication**, and test a working encrypt/decrypt flow in Java.

## 1. Public-Key RSA: Key Pair and Purpose

RSA uses a key pair:

- **Public key:** may be shared with senders; in RSA encryption, used to encrypt a key or short data intended for the private-key holder.
- **Private key:** must be protected; in RSA decryption, used to recover a value encrypted with the corresponding public key.

At the mathematical layer, RSA involves modular exponentiation modulo `n`, yet modular exponentiation alone is **not a secure encryption scheme** without proper encoding/padding and validation rules. Always use **RSAES-OAEP** from a trusted crypto library rather than concatenating bytes or implementing OAEP yourself.

```text
             Recipient
           +--------------+
           | RSA public   |----> shared after verifying origin/identity
           | RSA private  |----> stored secretly, used only in recipient environment
           +--------------+

Sender: data/key -- RSA-OAEP(public) --> RSA ciphertext
Recipient: RSA ciphertext -- RSA-OAEP(private) --> data/key
```

Simply having a "public key" does not mean it actually belongs to the intended recipient. If an adversary can substitute the public key during distribution, they can make you encrypt data for **the adversary's key**. Every real deployment must verify the trust path: certificate chain and matching hostname/subject, pinned keys with a rotation policy, or an authenticated public-key distribution channel.

**RSA encryption is different from RSA signature.** RSA-OAEP protects plaintext confidentiality for the private-key holder; it does not create a signature letting the recipient know who sent it. Use RSA-PSS (or a suitable signature scheme) when digital signatures are required; never treat RSA-OAEP output as a "reverse signature".

## 2. What Is RSA-OAEP?

RSAES-OAEP is specified in **RFC 8017 / PKCS #1 v2.2**. OAEP encodes the input message into a structured block using a hash, a mask generation function (typically MGF1), a random seed, and an optional **label**, before applying the RSA public-key operation.

Relevant components:

| Component | Role | What must be agreed upon |
| --- | --- | --- |
| RSA modulus `n` | Determines RSA block size | Matching public/private key, modulus size |
| OAEP digest `Hash` | Hash inside OAEP, determines `hLen` | E.g., `SHA-256` with 32-byte digest |
| Mask generation function | Generates mask inside OAEP | Typically `MGF1` |
| MGF1 digest | Hash used inside MGF1 | E.g., also `SHA-256`, must be explicitly configured |
| Label `L` | Optional context byte string | Both sides use the exact same label bytes |
| Random seed | Makes encryption probabilistic | Appropriate library RNG |
| RSA public/private key | Encryption / decryption | Key must belong to the intended recipient |

Conceptual view:

```text
Message M (byte[<= max]) + Label L
                 |
          OAEP Encoding
      (Hash, MGF1, random seed)
                 |
     Encoded message EM (k bytes)
                 |
        RSA public operation
                 |
     RSA ciphertext C (k bytes)
                 |
     RSA private operation + OAEP Decoding
                 |
            Message M
```

The diagram above conveys the idea; do not use it to implement padding yourself.

### 2.1. OAEP Is Randomized Encryption

Encrypting **the same plaintext with the same public key** twice using RSA-OAEP can yield **different ciphertexts** because OAEP uses randomness. This is expected behavior. Never test RSA-OAEP by asserting that two ciphertexts are equal.

The proper test checks that:
- After encrypting and decrypting with the matching private key and OAEP parameters, the recovered plaintext matches the original bytes.
- If the private key, label, or ciphertext bytes are wrong, decryption is rejected.
- Plaintext longer than the limit is rejected **before or during encryption**, never truncated.

### 2.2. What Is the OAEP Label and Is It Secret?

OAEP takes a label byte string `L`. It can be empty (a standard choice) or explicitly defined in the protocol, for example:

```text
L = UTF-8("hybrid-demo:v1|CEK")
```

The label **does not need to be secret**. It binds the scheme to a specific domain of use when all parties agree on its definition. When encrypting with label `L1`, decryption must use the exact bytes `L1`; changing to `L2` typically causes OAEP verification to fail.

Do not automatically treat the OAEP label as an authorization system. The recipient must still validate keys/certificates, envelope version, who is permitted to send, and which metadata fields are authenticated. If a label is used in a protocol, publish its exact bytes/encoding and keep it stable per version.

### 2.3. Two Hashes in OAEP: An Easily Overlooked Parameter

When configuring:

```text
OAEP digest:   SHA-256
MGF:           MGF1
MGF1 digest:   SHA-256
Label:         "hybrid-demo:v1|CEK" (UTF-8)
```

this is **one specific parameter set**. A library might use SHA-256 for the OAEP digest while implicitly choosing a different digest for MGF1 if not explicitly specified. Two implementations nominally both using "RSA-OAEP SHA-256" yet differing in MGF1 digest can **fail to decrypt each other's ciphertexts**.

In Java 17, use `OAEPParameterSpec` for transparent configuration:

```java
OAEPParameterSpec oaep = new OAEPParameterSpec(
    "SHA-256",
    "MGF1",
    MGF1ParameterSpec.SHA256,
    new PSource.PSpecified(
        "hybrid-demo:v1|CEK".getBytes(StandardCharsets.UTF_8)
    )
);
```

When passing `OAEPParameterSpec` into `Cipher.init(...)`, the OAEP digest, MGF1 digest, and label are all specified. `"RSA/ECB/OAEPPadding"` is a widely supported JCA transformation name; the `ECB` token is a provider transformation naming convention and **does not mean RSA is encrypting multiple blocks in ECB mode like AES**.

Never guess parameters solely from the transformation string `"RSA/ECB/OAEPWithSHA-256AndMGF1Padding"`. For cross-interoperability across Java, .NET, OpenSSL, or HSMs, share full test vectors/schemas and verify every parameter.

## 3. RSA-OAEP Plaintext Size Limit

The most important takeaway of this lesson is the RSAES-OAEP formula (RFC 8017):

\[
\boxed{\text{mLen} \le k - 2\,\text{hLen} - 2}
\]

Where:
- `mLen` is the **byte count** of the plaintext to encrypt with RSA-OAEP, not the Java `String.length()` character count.
- `k` is the **RSA modulus length in bytes**: `k = ceil(bitLength(n) / 8)`.
- `hLen` is the **OAEP hash output length in bytes**. For SHA-256, `hLen = 32`; SHA-384 is 48; SHA-512 is 64.
- The `2hLen` and `2` terms are OAEP structural overhead; you cannot use all `k` bytes for plaintext.
- The MGF1 hash must be configured consistently; in this formula `hLen` refers specifically to the **OAEP Hash** output length, not ciphertext length or key bytes.

**Example: RSA-2048 + OAEP SHA-256:**

\[
k = 2048/8 = 256 \text{ bytes}
\]

\[
\text{maxM} = 256 - 2(32) - 2 = \boxed{190\text{ bytes}}
\]

If the input is 191 bytes, it **cannot be directly encrypted** with this exact RSAES-OAEP configuration. This is a scheme limit, not a bug where "Java fails on long strings".

### 3.1. Illustrative Size Table

| RSA modulus | `k` (bytes) | OAEP hash | `hLen` | Max plaintext | RSA ciphertext per op |
| --- | ---: | --- | ---: | ---: | ---: |
| 2048-bit | 256 | SHA-256 | 32 | **190 bytes** | 256 bytes |
| 3072-bit | 384 | SHA-256 | 32 | **318 bytes** | 384 bytes |
| 4096-bit | 512 | SHA-256 | 32 | **446 bytes** | 512 bytes |
| 2048-bit | 256 | SHA-384 | 48 | **158 bytes** | 256 bytes |
| 2048-bit | 256 | SHA-512 | 64 | **126 bytes** | 256 bytes |
| 3072-bit | 384 | SHA-512 | 64 | **254 bytes** | 384 bytes |

This table only shows **data capacity per single OAEP operation**, not whether an RSA key is strong enough for every threat model. Choosing RSA-2048/3072/4096 must follow policy and data lifetime; larger keys also affect performance, ciphertext size, and maximum payload length.

Notably: increasing the modulus from 2048 to 4096 bits only raises OAEP SHA-256 capacity from **190 to 446 bytes**. That is still tiny compared to image files, JSON requests, or typical business payloads.

### 3.2. Byte Length Differs from String Length

In Java, a Vietnamese string can take multiple UTF-8 bytes per character. For example, `"A"` is 1 UTF-8 byte, whereas many non-ASCII characters typically require 2–4 bytes. RSA-OAEP sees a **byte array**, not "190 characters".

When data is text:

```java
byte[] plaintext = value.getBytes(StandardCharsets.UTF_8);
int lengthBytes = plaintext.length;
```

Do not use `value.length()` as the OAEP length. Java `String.length()` counts UTF-16 code units, whereas the OAEP limit is measured in bytes.

### 3.3. What Happens When the Limit Is Exceeded?

A JCA provider typically throws `IllegalBlockSizeException` or a `GeneralSecurityException` subclass when `Cipher.doFinal(...)` receives an oversized OAEP plaintext. Never "fix" this by truncating input or splitting into multiple RSA operations ad hoc.

Logic to compute the limit:

```java
int modulusBits = rsaPublicKey.getModulus().bitLength();
int k = (modulusBits + 7) / 8;
int hLen = 32; // SHA-256 output length
int maximumOaepPlaintext = k - 2 * hLen - 2;
```

If `maximumOaepPlaintext` is negative, the parameter set lacks space to encode any message, so you must select a compatible key/hash and scheme. Never infer that a "2048-bit RSA key" can encrypt 256 bytes of original data; **256 bytes is the RSA ciphertext length**, not the OAEP plaintext limit.

## 4. Why Not Split a File into Small Chunks and Encrypt Each with RSA?

A common mistaken approach:

```text
1 MiB file
   |
split into 190-byte chunks
   |
RSA-OAEP encrypt(block0)
RSA-OAEP encrypt(block1)
...
RSA-OAEP encrypt(blockN)
   |
concatenate RSA ciphertexts
```

Even if each chunk encrypts validly, this design should generally **not be used**:

1. **Very poor performance:** RSA public-key operations cost far more CPU than AES for bulk encryption; private-key decryption is even slower. Encrypting a large file can require thousands of RSA operations.
2. **Severe size bloat:** with RSA-2048 + OAEP SHA-256, every 190 bytes of plaintext expands to 256 bytes of ciphertext, before even adding metadata, indices, and protection.
3. **Lack of whole-message authentication:** OAEP is an asymmetric encryption scheme, not an AEAD stream over blocks. Without extra mechanisms, swapping, reordering, or dropping blocks may go undetected relative to the whole file.
4. **No canonical framing:** you would have to define block counts, lengths, and indices, prevent insertion/swapping/duplication, and handle errors consistently.
5. **No key-management benefit:** multiple RSA decrypts still hit the same private key; you miss out on AES speed and an independent random key per object.

The right approach for large payloads is **hybrid encryption**: **RSA-OAEP once for a short random key**, and **AEAD for the entire payload** in a standard format.

## 5. Hybrid Encryption Model: Session Key + Data

Separate two responsibilities:

- **RSA-OAEP:** protects a random **content-encryption key (CEK)**, e.g., a 32-byte CEK used as an AES-256 key. The recipient's public key encrypts the CEK; the recipient's private key decrypts the CEK.
- **AES-GCM:** uses the CEK to encrypt content with an independent nonce, producing **ciphertext and authentication tag**. The recipient verifies the tag during decryption to confirm data/AAD/key/nonce consistency.

```text
SENDER                                        RECIPIENT
---------                                     ---------
Authenticated RSA public key                  Secure RSA private key
       |                                           |
SecureRandom: 32-byte CEK                          |
       |                                           |
       +---- RSA-OAEP(public, CEK) --> wrappedCEK ---+--> RSA-OAEP(private)
       |                                                  |
       |                                                  +--> 32-byte CEK
       v                                                          |
SecureRandom: 12-byte nonce                                       |
       |                                                          |
AES-256-GCM(CEK, nonce, AAD, plaintext)                           |
       |                                                          |
       +--> ciphertext + tag -----------------------------> AES-GCM decrypt
                         |                                    |
              Hybrid envelope:                             Verify tag
              wrappedCEK                                    |
              nonce                                         v
              ciphertext+tag                        Plaintext (only if valid)
              version, algorithms, keyId, AAD context
```

A recipient needs the **RSA private key matching `wrappedCEK`**, **matching OAEP parameters**, and then uses the decrypted CEK to verify the AES-GCM tag. If passwords/logins or user identity are involved, that is a separate authentication/authorization layer and cannot be replaced by successful decryption.

### 5.1. Distinguishing CEK, KEK, and RSA Keys

In much of the literature:
- **CEK/DEK:** symmetric key encrypting data (content/data encryption key).
- **KEK:** a key encrypting another key (key-encryption key); in this model, the RSA public key is used in an **RSA-OAEP key transport/wrapping scheme**, not as a 32-byte AES KEK.
- **Wrapped key:** the RSA ciphertext of the CEK, not the CEK itself.

RSA-OAEP wrapping a CEK is **not** the **RSA-KEM** algorithm. Both belong to key-protection/hybrid design families, yet their schemes and byte structures differ; never call RSA-OAEP "RSA-KEM" or expect one side using RSA-KEM to be decrypted by OAEP.

### 5.2. Why Use AES-GCM Instead of Homegrown AES-CBC?

AES-GCM is **AEAD (Authenticated Encryption with Associated Data)**. It both encrypts plaintext and detects tampering with ciphertext and AAD. Instead of assembling AES-CBC + padding + MAC in an ambiguous order, standardized AEAD reduces entire classes of bugs.

Sample parameters in this lesson:
- CEK: **32 bytes** (AES-256).
- GCM nonce: **12 bytes** (96 bits), fresh for every encryption under the same CEK.
- Tag: **16 bytes** (128 bits).
- Ciphertext + tag: for `N`-byte plaintext in a JCA demo, typically `N + 16` bytes.
- AAD: context-describing bytes, e.g., `"hybrid-demo:v1|AES-256-GCM"`. AAD **is authenticated but not encrypted**.

Never reuse the same `(CEK, nonce)` pair in AES-GCM. A fresh random CEK per object helps isolate objects, yet you still need a sound nonce mechanism and a limit on encryptions if keys are ever reused. Never arbitrarily use a password KDF salt as a nonce.

### 5.3. What Does the Authentication Tag Protect?

On the receiving side, AES-GCM decryption checks the tag against **the key, nonce, AAD, and ciphertext**. If data is altered, decryption typically fails with a tag error. However:

- Never pass unverified plaintext into business logic.
- If ciphertext is altered, the key is wrong, the nonce is wrong, or the AAD is wrong, the tag check fails identically; do not assume an exception pinpoints a single root cause.
- The tag proves integrity under the CEK; **it does not prove sender identity**, because anyone with the recipient's public key can generate a fresh CEK, create a valid AES-GCM ciphertext/tag, and wrap the CEK with RSA-OAEP.

When **author authentication** is required, integrate a digital signature (such as Ed25519 or RSA-PSS per policy), an authenticated key-distributed MAC, or a security protocol with explicit identity binding. The signature should authenticate **the envelope or full semantic payload** (including version, algorithms, keyId, wrappedKey, nonce, ciphertext/tag, and context) using clear canonical serialization.

## 6. What the Hybrid Envelope Format Must Store and Transmit

An envelope can be described logically as:

```json
{
  "formatVersion": 1,
  "recipientKeyId": "recipient-key-2026",
  "wrap": {
    "scheme": "RSAES-OAEP",
    "oaepHash": "SHA-256",
    "mgf": "MGF1",
    "mgfHash": "SHA-256",
    "labelEncoding": "UTF-8",
    "label": "hybrid-demo:v1|CEK",
    "wrappedKeyBase64Url": "<base64url-of-rsa-ciphertext>"
  },
  "data": {
    "scheme": "AES-256-GCM",
    "nonceBase64Url": "<base64url-of-12-byte-nonce>",
    "ciphertextAndTagBase64Url": "<base64url-of-ciphertext-plus-tag>"
  },
  "aadProfile": "hybrid-demo:v1|AES-256-GCM"
}
```

This is a **descriptive JSON sketch**, not a standardized wire format or an immediately decryptable blob. Tokens in angle brackets describe data types, not real keys. A production protocol must specify exact encoding, parsers, canonicalization rules, and which fields are authenticated.

Minimum items that must stay consistent:

| Field | Purpose | Secret? | Critical rule |
| --- | --- | --- | --- |
| `formatVersion` | Select an exact profile | No | Never arbitrarily try multiple versions |
| `recipientKeyId` | Look up private key per trust policy | No | Never let clients force weak algorithms |
| OAEP hash/MGF1 hash/label | Decrypt RSA with matching parameters | No | Byte values must match identically |
| `wrappedCEK` | Protect CEK in transit/at rest | Not raw CEK | RSA ciphertext has modulus length |
| GCM nonce | AES-GCM parameter | No | Must not repeat under the same CEK |
| `ciphertextAndTag` | Encrypted data + tag | Not separately secret if crypto is sound | Must keep full tag; verify before use |
| `AAD` or AAD profile | Bind metadata/context | No | Encrypt/decrypt must use exact same AAD bytes |
| CEK before/after unwrap | Symmetric key for AES | **Yes** | Never write plaintext key to logs, JSON, DB |
| RSA private key | Recover CEK | **Yes** | Restrict access; store/execute securely |

**You cannot store only the ciphertext and drop the nonce or OAEP parameters**; there would not be enough data and rules to decrypt later. When formats evolve, version them clearly.

### 6.1. What Metadata Should AAD Cover?

In the Java example, AAD is the constant `"hybrid-demo:v1|AES-256-GCM"` for easy verification. In a real protocol, build AAD in a **canonical byte format** binding every attribute that affects data semantics, such as:
- `formatVersion`, algorithm suite, digest selection, tag length.
- `recipientKeyId`/trusted key ID, application domain.
- Tenant, resourceId/documentId, content type, logical ownership.
- Header/framing fields needing protection, including wrappedKey or a well-defined hash/framing if required by design.

The recipient must reconstruct the **exact AAD bytes** independently rather than blindly trusting unverified metadata as self-authenticating. The contract must avoid the fallacy that "the tag checked the body" while routes, tenants, or algorithm versions sit outside the protected boundary.

For multi-recipient protocols, design key-wrap entries, recipient binding, and authentication of the recipient list explicitly. Never automatically swap wrappedKey or redirect recipients simply because the ciphertext data "looks right".

### 6.2. Nonce, Label, and Salt Serve Different Roles

Here:
- **OAEP label:** context bytes affecting OAEP decoding, not an IV and does not need to be random.
- **GCM nonce:** an independent parameter required never to repeat under the same AES key.
- **Salt:** usually appears in password KDFs or other key derivation; random-CEK RSA-OAEP hybrid **does not require a KDF salt**. Do not add a salt merely because you saw one in password-based encryption examples.
- **Authentication tag:** AEAD verification data, not a key, and cannot be ignored to release plaintext.

Generate CEK and nonce with `SecureRandom`; never use `Random` or current time as the CEK source. Never take a number from `System.currentTimeMillis()` as a "random secret".

## 7. Java 17+: Runnable Hybrid Encryption Example

This example uses purely standard JDK APIs:

- `KeyPairGenerator` generates a **2048-bit RSA key pair for demo purposes**.
- `Cipher` with `RSA/ECB/OAEPPadding` and **explicit `OAEPParameterSpec`**: OAEP digest SHA-256, MGF1 digest SHA-256, label `hybrid-demo:v1|CEK`.
- `SecureRandom` creates a 32-byte AES-256 CEK and 12-byte GCM nonce.
- `Cipher` with `AES/GCM/NoPadding`, 128-bit tag, constant AAD.
- A **2,000-byte** plaintext is encrypted with AES-GCM; RSA-OAEP only encrypts the 32-byte CEK.
- Verifies round-trip, detects ciphertext tampering, rejects wrong OAEP label, and rejects encrypting an oversized payload directly with RSA-OAEP.

Create the file **`HybridEncryptionDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.MGF1ParameterSpec;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;
import javax.crypto.spec.SecretKeySpec;

public class HybridEncryptionDemo {
    static final SecureRandom RNG = new SecureRandom();

    static final byte[] AAD =
            "hybrid-demo:v1|AES-256-GCM".getBytes(StandardCharsets.UTF_8);

    static OAEPParameterSpec spec(String label) {
        return new OAEPParameterSpec(
                "SHA-256",
                "MGF1",
                MGF1ParameterSpec.SHA256,
                new PSource.PSpecified(label.getBytes(StandardCharsets.UTF_8))
        );
    }

    static final OAEPParameterSpec OAEP = spec("hybrid-demo:v1|CEK");

    // For a simple demo only: records containing arrays are not immutable.
    record Packet(byte[] wrappedKey, byte[] nonce, byte[] ciphertextAndTag) {}

    static Packet encrypt(PublicKey publicKey, byte[] plaintext)
            throws GeneralSecurityException {
        byte[] cek = new byte[32];      // AES-256 content-encryption key
        byte[] nonce = new byte[12];    // AES-GCM 96-bit nonce

        RNG.nextBytes(cek);
        RNG.nextBytes(nonce);
        try {
            Cipher rsa = Cipher.getInstance("RSA/ECB/OAEPPadding");
            rsa.init(Cipher.ENCRYPT_MODE, publicKey, OAEP);
            byte[] wrapped = rsa.doFinal(cek);

            Cipher aes = Cipher.getInstance("AES/GCM/NoPadding");
            aes.init(
                    Cipher.ENCRYPT_MODE,
                    new SecretKeySpec(cek, "AES"),
                    new GCMParameterSpec(128, nonce)
            );
            aes.updateAAD(AAD);
            byte[] ciphertextAndTag = aes.doFinal(plaintext);
            return new Packet(wrapped, nonce, ciphertextAndTag);
        } finally {
            Arrays.fill(cek, (byte) 0);
        }
    }

    static byte[] decrypt(
            PrivateKey privateKey,
            Packet packet,
            OAEPParameterSpec parameters
    ) throws GeneralSecurityException {
        Cipher rsa = Cipher.getInstance("RSA/ECB/OAEPPadding");
        rsa.init(Cipher.DECRYPT_MODE, privateKey, parameters);
        byte[] cek = rsa.doFinal(packet.wrappedKey());

        try {
            if (cek.length != 32) {
                throw new GeneralSecurityException("Invalid CEK length");
            }

            Cipher aes = Cipher.getInstance("AES/GCM/NoPadding");
            aes.init(
                    Cipher.DECRYPT_MODE,
                    new SecretKeySpec(cek, "AES"),
                    new GCMParameterSpec(128, packet.nonce())
            );
            aes.updateAAD(AAD);
            return aes.doFinal(packet.ciphertextAndTag());
        } finally {
            Arrays.fill(cek, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator gen = KeyPairGenerator.getInstance("RSA");
        gen.initialize(2048, RNG);
        KeyPair recipient = gen.generateKeyPair();

        int modulusBytes =
                (((RSAPublicKey) recipient.getPublic()).getModulus().bitLength() + 7) / 8;
        int oaepMax = modulusBytes - 2 * 32 - 2;

        byte[] plaintext = new byte[2000];
        Arrays.fill(plaintext, (byte) 'A');

        Packet packet = encrypt(recipient.getPublic(), plaintext);
        byte[] recovered = decrypt(recipient.getPrivate(), packet, OAEP);

        System.out.println("RSA modulus bytes: " + modulusBytes);
        System.out.println("OAEP-SHA-256 plaintext limit: " + oaepMax);
        System.out.println("Payload bytes: " + plaintext.length);
        System.out.println("Wrapped CEK bytes: " + packet.wrappedKey().length);
        System.out.println("AES-GCM nonce bytes: " + packet.nonce().length);
        System.out.println("Ciphertext plus tag bytes: " + packet.ciphertextAndTag().length);
        System.out.println("Round trip: " + Arrays.equals(plaintext, recovered));

        byte[] tampered = packet.ciphertextAndTag().clone();
        tampered[0] ^= 1;
        boolean tamperRejected = false;
        try {
            decrypt(
                    recipient.getPrivate(),
                    new Packet(packet.wrappedKey(), packet.nonce(), tampered),
                    OAEP
            );
        } catch (AEADBadTagException expected) {
            tamperRejected = true;
        }
        System.out.println("Tampered ciphertext rejected: " + tamperRejected);

        boolean wrongLabelRejected = false;
        try {
            decrypt(recipient.getPrivate(), packet, spec("wrong-context"));
        } catch (GeneralSecurityException expected) {
            wrongLabelRejected = true;
        }
        System.out.println("Wrong OAEP label rejected: " + wrongLabelRejected);

        boolean oversizedRejected = false;
        try {
            Cipher directRsa = Cipher.getInstance("RSA/ECB/OAEPPadding");
            directRsa.init(Cipher.ENCRYPT_MODE, recipient.getPublic(), OAEP);
            directRsa.doFinal(plaintext);
        } catch (GeneralSecurityException expected) {
            oversizedRejected = true;
        }
        System.out.println("Oversized direct RSA rejected: " + oversizedRejected);
    }
}
```

Compile and run with JDK 17+:

```bash
javac HybridEncryptionDemo.java
java HybridEncryptionDemo
```

**Stdout output:** (verified with JDK 24 via JShell on Java 17-compatible APIs; because the RSA key pair, CEK, and nonce are randomly generated, specific ciphertexts are not printed):

```text
RSA modulus bytes: 256
OAEP-SHA-256 plaintext limit: 190
Payload bytes: 2000
Wrapped CEK bytes: 256
AES-GCM nonce bytes: 12
Ciphertext plus tag bytes: 2016
Round trip: true
Tampered ciphertext rejected: true
Wrong OAEP label rejected: true
Oversized direct RSA rejected: true
```

Where:
- `OAEP-SHA-256 plaintext limit: 190` comes from `256 − 2 × 32 − 2`.
- `wrappedKey` is **256 bytes** due to the 2048-bit RSA modulus, even though the original CEK is only 32 bytes.
- `Ciphertext plus tag bytes: 2016` comes from 2,000 bytes of plaintext plus the 16-byte AES-GCM tag; this is the output of `Cipher.doFinal` for a single unpadded message.
- `Round trip: true` proves that with the matching key pair, OAEP params, nonce/AAD, and valid ciphertext, the exact plaintext bytes are recovered.
- Flipping one bit of the AES-GCM ciphertext invalidates the **authentication tag**, so decryption is rejected.
- Using OAEP label `wrong-context` during decryption does not match the encryption label and fails to decrypt the wrapped CEK.
- Attempting to encrypt **all 2,000 bytes with RSA-OAEP** throws an error, recorded as `true` on the final line. **Never** silently truncate input to 190 bytes.

### 7.1. Key Java Details

**Initializing RSA-OAEP with explicit parameters:**

```java
Cipher rsa = Cipher.getInstance("RSA/ECB/OAEPPadding");
rsa.init(Cipher.ENCRYPT_MODE, publicKey, OAEP);
byte[] wrapped = rsa.doFinal(cek);
```

Keep the exact same OAEP configuration when decrypting. In Java, explicit `OAEPParameterSpec` prevents provider default mismatches. MGF1-SHA-256 is an independent parameter from OAEP SHA-256 even though the lesson chooses the same hash.

**AES-GCM must have a nonce and tag:**

```java
Cipher aes = Cipher.getInstance("AES/GCM/NoPadding");
aes.init(
    Cipher.ENCRYPT_MODE,
    new SecretKeySpec(cek, "AES"),
    new GCMParameterSpec(128, nonce)
);
aes.updateAAD(AAD);
byte[] ciphertextAndTag = aes.doFinal(plaintext);
```

`GCMParameterSpec(128, nonce)` specifies a **128-bit tag length**, not the AES key length. AES-256 comes from the 32-byte CEK. Do not confuse the tag parameter 128 with using AES-128.

**Private key is used only on the receiver:**

```java
rsa.init(Cipher.DECRYPT_MODE, privateKey, OAEP);
byte[] cek = rsa.doFinal(packet.wrappedKey());
```

Never send private keys over the network or embed them in envelopes. Public keys must be authenticated before encryption. In production, private keys may live in a KeyStore, HSM, or KMS and may not be exportable as bytes.

**Comparing errors:** if OAEP unwrap fails, there is no CEK to decrypt AES-GCM. If unwrap succeeds yet ciphertext/tag/AAD mismatch, AEAD rejects. Do not build public APIs returning granular errors that create padding oracles or leak decryption behavior; design error handling and rate limiting according to your threat model.

### 7.2. Boundary Between Demo and Production

The example is deliberately minimal to teach the two responsibilities of RSA-OAEP and AES-GCM; for production, address these additional concerns:

1. **RSA keys:** do not regenerate keys on every startup and lose the private key if long-term stored data must be decrypted. Use a keystore/HSM/KMS with policy-driven backup, rotation, and destruction.
2. **Key size choice:** 2048-bit is for fast demo runs; choose 3072-bit or another profile when policy/data-security lifetime requires it, based on current guidance rather than blindly copying bit counts.
3. **Serialization:** `record Packet` holds mutable `byte[]` arrays. In production, make defensive/immutable copies, validate sizes, encode/decode in a standard format, and enforce payload/envelope size limits.
4. **AAD:** the demo uses a constant; if variable headers exist (`recipientKeyId`, `tenantId`, `resourceId`), include them in AAD via a canonical schema or protect the whole envelope equivalently.
5. **Lengths/tag:** readers must verify `wrappedKey` length equals `k`, nonce is 12 bytes per profile, tag has full length, algorithm suite/version are allowlisted, and never decrypt before verification.
6. **Nonce lifecycle:** generate fresh nonces on encryption; never repeat under the same CEK. If reusing a CEK across multiple messages, enforce uniqueness statefully or per standard.
7. **Ephemeral keys:** `Arrays.fill(cek,(byte)0)` reduces retention time of program-owned arrays, yet cannot guarantee erasing copies inside the provider/JVM. Never log CEKs, confidential plaintexts, private keys, or memory dumps.
8. **Authenticated sender:** RSA-OAEP and AES-GCM in the example **do not authenticate the sender**. Add signatures/protocol with identity binding if required.
9. **Large objects and streaming:** do not load multi-GB files into a single array; use properly designed AEAD chunking/streaming APIs with bounded nonces/sequences, per-chunk authentication, and ordering/total-chunk protection. Never turn a single-shot demo into an ad-hoc unverified streaming scheme.
10. **External errors:** validate framing/version/length before crypto, return opaque errors without sensitive root causes, and never fall back to RSA PKCS#1 v1.5 simply because OAEP failed.

## 8. Design Example: Sending a File to a Recipient

Suppose an application uploads a 10 MiB file readable only by user B.

### 8.1. Recommended Workflow

**Step 1: Verify B's public key.** Fetch the certificate or public-key mapping from a trusted source; verify identity/`keyId` and policy. If the key is swapped, every subsequent protection may still succeed **for the attacker**, not B.

**Step 2: Generate a fresh CEK.** The sender uses a CSPRNG to generate a 32-byte CEK; never use a short password or timestamp instead of a CEK.

**Step 3: Generate an AEAD nonce.** Generate a nonce per the AES-GCM profile; if each file has its own CEK, a 96-bit random nonce per message is a reasonable demo pattern, though uniqueness guarantees must still be evaluated against encryption volume and policy.

**Step 4: Encrypt the file with AES-GCM.** Choose AAD binding format version, fileId, owner, and context. Obtain ciphertext + tag. For large files, use a properly specified streaming AEAD library rather than encrypting chunks and concatenating them unauthenticated.

**Step 5: Wrap the CEK for B using RSA-OAEP.** The key to wrap is 32 bytes, well under the 190-byte limit of RSA-2048 OAEP SHA-256. Standardize OAEP digest, MGF1 digest, and label.

**Step 6: Store an envelope.** Include required metadata, wrappedCEK, nonce, ciphertext/tag, version, and AAD profile. Never store the raw CEK or private key inside the envelope.

**Step 7: Recipient B decrypts.** B selects the trusted private key, unwraps the CEK via RSA-OAEP, decrypts AES-GCM, verifies the tag, and only then uses the plaintext. On failure, reject; never skip the tag or "try another cipher" arbitrarily.

**Step 8: Verify sender if required.** If the app also needs B to know the file truly came from A, add A's signature over the canonicalized envelope and verify A's certificate/key, or adopt a standard authenticated multi-party encryption protocol.

### 8.2. Size Overhead

For a 10 MiB file (10 × 1,048,576 bytes), AES-GCM with a 16-byte tag adds negligible overhead for a single message (excluding nonce/header). RSA-OAEP wrapping one CEK adds only **256 bytes** with a 2048-bit modulus.

By contrast, splitting a file into 190-byte OAEP blocks and encrypting each block would produce tens of thousands of 256-byte RSA ciphertexts, wasting CPU and inflating size. There is no sound operational reason to pick block-RSA over CEK + AES-GCM for normal file encryption.

## 9. RSA-OAEP Does Not Provide All Guarantees of a Secure Channel

### 9.1. Confidentiality Does Not Mean Sender Authentication

RSA-OAEP ensures only the matching private key can recover the CEK (assuming sound security and key management). However, anyone knowing the public key can:
- generate their own CEK,
- encrypt a message with AES-GCM,
- wrap their CEK with the recipient's public key,
- send a validly decryptable envelope.

Thus, the recipient cannot infer "A definitely sent this" merely from successful decryption. Add digital signatures/certs/identity binding, or use a complete protocol with origin authentication.

An unsigned hybrid envelope also does not guarantee "replay protection". An adversary can capture a valid envelope and resend it; the receiver needs IDs, timestamps, nonce/replay tracking, and business policies if duplicate execution is dangerous.

### 9.2. Forward Secrecy and Future Private-Key Compromise

In the **RSA-OAEP wrapping CEK** model stored alongside ciphertext, if B's RSA private key is compromised one day, an attacker who captured earlier `wrappedCEK` values can unwrap those CEKs and decrypt historical ciphertexts. This model does **not** inherently provide perfect forward secrecy.

If a system must protect past data against long-term key compromise, use an **ephemeral key agreement / authenticated KEM** design or a protocol with proven forward secrecy and proper key lifecycle management. Never label RSA-OAEP hybrid as "PFS" just because each file uses a random CEK.

### 9.3. Preventing Public-Key Substitution Is a Separate Requirement

An attacker who compromises a public-key store can replace B's key with the attacker's key before the sender encrypts. The ciphertext will encrypt cleanly under an RSA key and AES-GCM will validate, yet the attacker will be the one able to unwrap it. No OAEP equation verifies B's name. Key authenticity must come from PKI or a trust mechanism external to RSA encryption.

### 9.4. RSA-OAEP Decryption Requires Quiet Error Handling

Never expose an endpoint allowing strangers to submit unlimited `wrappedKey` values and observe granular errors, timing differences, or whether the server proceeded to AES-GCM. Use crypto providers with proper mitigations, enforce rate limits, and unify public API error responses.

Never write raw RSA modular exponentiation to "debug padding" on untrusted input; never fall back to `RSA/ECB/PKCS1Padding` when OAEP fails. Bleichenbacher-style / padding-oracle attacks are precisely why strict APIs and protocols must be respected.

## 10. Common Mistakes and Fixes

| Misconception / design | Why it is wrong | Right direction |
| --- | --- | --- |
| "RSA-2048 directly encrypts 256 bytes of plaintext" | 256 is the ciphertext/modulus byte count; OAEP SHA-256 adds overhead | Use `max = k - 2hLen - 2`, e.g., 190 bytes |
| "A 190-character string is under the limit" | OAEP takes UTF-8 bytes, not Java UTF-16 length | Compute `getBytes(UTF_8).length` |
| "Split file into RSA blocks and concatenate" | Slow, bloated, lacks proper whole-file framing/integrity | RSA-OAEP wraps CEK, AES-GCM encrypts bulk data |
| "Use raw RSA/no padding for speed" | Not a secure encryption scheme | RSAES-OAEP via standard library |
| "Both sides saying SHA-256 OAEP is enough" | MGF1 digest/label may still differ | Specify `OAEPParameterSpec` explicitly, test interop |
| "OAEP label is a random IV" | Label is public context; AEAD IV/nonce is a separate parameter | Keep matching label bytes and separate nonce |
| "Use RSA OAEP encryption to prove A sent it" | Anyone with B's public key can encrypt | Use separate signatures/identity binding |
| "AES-GCM needs no tag if plaintext looks right" | Loses integrity check, risks accepting tampered plaintext | Enforce tag verification, fail closed |
| "With a GCM tag, all envelope metadata is safe" | Only data bound into AAD/ciphertext is authenticated | Canonicalize/bind meaningful fields |
| "AES-GCM can repeat nonces as long as plaintext differs" | Reusing key/nonce is a catastrophic flaw | Enforce nonce uniqueness under the same key |
| "Encrypting a file with any public key suffices" | Attacker swaps public key → attacker decrypts | Authenticate key belongs to recipient |
| "Generating a key pair each run still opens old files" | Lost private key → cannot unwrap CEK | Persist securely and manage backup/rotation per policy |
| "If OAEP fails, fall back to PKCS1 v1.5" | Weakens policy, risks creating an oracle | Reject strictly per version, never downgrade |
| "Random CEK means forward secrecy" | Compromised long-term RSA private key unwraps past keys | Pick an ephemeral protocol if PFS is required |
| "WrappedCEK is a secret that cannot be stored" | Wrapped key is RSA ciphertext meant to be stored/transmitted | Store `wrappedCEK`, never store raw CEK |
| "`GCMParameterSpec(128)` means AES-128" | 128 is tag bit length; key length comes from CEK | Use 32-byte CEK for AES-256 |
| "RSA can directly stream large data" | One OAEP operation holds only a tiny payload | Standard AEAD streaming/format for files |
| "Hybrid encryption is RSA-KEM regardless of scheme" | OAEP key transport differs from RSA-KEM | Name exact scheme; never mix byte formats |

## 11. Practice Scenarios to Classify

**Scenario A — An 8 KiB API payload must be stored confidentially for one recipient.** RSA-2048 OAEP SHA-256 is limited to 190 bytes, so do not encrypt the payload directly. Generate a random AES CEK, encrypt the JSON with AES-GCM, and wrap the CEK with RSA-OAEP. Protect context in AAD and authenticate the recipient public key.

**Scenario B — A client wants to send an AES-256 key (32 bytes) to a server.** RSA-OAEP can encrypt the 32-byte CEK because 32 ≤ 190. You need matching OAEP hash/MGF1/label, an authenticated public key, envelope version, and secure AES-GCM decryption. However, if the goal is ordinary API transport over a network, consider **properly configured TLS** instead of inventing an application protocol unless encryption at rest is specifically needed.

**Scenario C — Sender and recipient both use RSA-OAEP SHA-256, yet decryption fails.** Check MGF1 digest, OAEP label bytes, key pair, ciphertext encoding (hex/Base64/byte length), provider restrictions, and format version. Never switch to SHA-1 or RSA PKCS1 v1.5 just to "try it".

**Scenario D — One byte of the GCM ciphertext is modified.** The receiver can still unwrap a valid CEK, yet the AES-GCM tag will mismatch on decryption and reject. Never use unverified plaintext; never infer who modified it or when solely from a tag failure.

**Scenario E — One byte of the wrapped CEK is modified.** OAEP decryption will almost certainly reject; or in the vanishingly rare event an unsuitable CEK were produced, the AES-GCM tag would still mismatch. Never rely on detailed OAEP errors to return private-key information to clients.

**Scenario F — B's private key leaks five years later.** An attacker who saved old hybrid envelopes can decrypt the old `wrappedCEK` values with that key, exposing historical data. Envelopes using RSA-OAEP alone do not automatically provide forward secrecy.

**Scenario G — B receives a validly decrypting hybrid envelope with no signature.** B knows the ciphertext/AAD matches the CEK and format, not whether A sent it; anyone possessing B's public key could build such an envelope.

**Scenario H — A 50 GiB file to encrypt in chunks.** Do not repeat RSA-OAEP per chunk; build a standardized streaming AEAD protocol where each chunk has its own nonce/sequence, authenticates order and end-of-stream, and wrap one or more CEKs per the key structure. Never treat an in-memory `byte[]` demo as a complete streaming solution.

## 12. Self-Check Questions

**1. With RSA-2048 and OAEP SHA-256, what is the maximum plaintext in bytes?**  
**Answer:** `k=256`, `hLen=32`, so `mLen ≤ 256−64−2 = 190` bytes.

**2. With RSA-3072 and OAEP SHA-512, what is the limit?**  
**Answer:** `k=384`, `hLen=64`, limit `384−128−2 = 254` bytes.

**3. How long is the RSA ciphertext of a 32-byte CEK under RSA-2048?**  
**Answer:** 256 bytes; OAEP ciphertext length equals the modulus length, not the CEK length.

**4. Why must RSA-OAEP not be used to directly encrypt a 1 MiB file?**  
**Answer:** Each OAEP operation holds only a short payload, RSA is CPU-expensive, and it does not replace whole-file AEAD authentication. Use a random CEK and AES-GCM for data, with RSA-OAEP wrapping the CEK.

**5. Both sides choose OAEP hash SHA-256, yet sender uses MGF1-SHA-256 and receiver uses MGF1-SHA-1. Can it decrypt?**  
**Answer:** Not under the same parameter set. OAEP and MGF1 digests must match exactly; saying only "OAEP SHA-256" is insufficient for an interoperable spec.

**6. Must the OAEP label `L` be kept secret?**  
**Answer:** No; it is optional context bytes. However, encryption and decryption must use the exact same label and encoding.

**7. Does RSA-OAEP + AES-GCM prove A is the sender?**  
**Answer:** No. Anyone holding B's public key can create an envelope for B. Sender authentication requires signing/origin certification or an appropriate protocol.

**8. If the GCM nonce is lost while the RSA private key and wrapped CEK remain, can the file be decrypted?**  
**Answer:** Not via the standard decryption flow without the nonce required by GCM; the nonce and required metadata must be stored.

**9. If the RSA private key leaks in the future, does old data have PFS merely because each file used a fresh CEK?**  
**Answer:** No. Old `wrappedCEK` values encrypted under the same RSA public key can be unwrapped by the compromised private key; an ephemeral protocol is needed if forward secrecy is required.

**10. In Java, why doesn't `GCMParameterSpec(128, nonce)` mean AES-128 is being used?**  
**Answer:** `128` is the tag length in bits. The AES key size is determined by the CEK byte count; a 32-byte CEK means AES-256.

**11. What happens if the same CEK and same GCM nonce encrypt two different plaintexts?**  
**Answer:** It severely violates GCM's nonce-uniqueness requirement and can compromise confidentiality and integrity; design proper nonce management.

**12. Can you fall back from OAEP to PKCS#1 v1.5 if a message fails to decrypt?**  
**Answer:** No. Algorithm/version contracts must be fixed, allowlisted, downgrade-resistant, and fail safely.

## 13. Pre-Release RSA-OAEP Hybrid Implementation Checklist

### Sender

- [ ] Verified public key belongs to the intended recipient; checked lifecycle/revocation/algorithm policy.
- [ ] Agreed on RSA modulus, OAEP hash, MGF1 digest, label encoding, and version.
- [ ] Used `SecureRandom` to generate a **random 32-byte CEK** or policy-approved cipher key size.
- [ ] Used an appropriate AEAD (e.g., AES-GCM) with a safe nonce policy and context-bound AAD.
- [ ] RSA-OAEP encrypts only CEK/short payload within `k - 2hLen - 2`.
- [ ] Stored/transmitted wrappedCEK, nonce, ciphertext, tag, version, keyId, and required metadata.
- [ ] Never logged CEK/private data; zeroed erasable byte array copies on a best-effort basis.
- [ ] If authorship is required, added signatures/identity binding outside confidentiality.

### Recipient

- [ ] Enforced version/cipher/keyId allowlist, envelope size caps, and no downgrade on failure.
- [ ] Retrieved authorized private key from KeyStore/KMS/HSM; never accepted private keys from payloads.
- [ ] Enforced matching OAEP digest + MGF1 digest + label; considered opaque error responses.
- [ ] Unwrapped CEK, verified key length and data encryption algorithm against profile.
- [ ] Verified nonce, AAD, and authentication tag; never used plaintext until tag is valid.
- [ ] Checked sender/tenant/resource/authorization/replay per business requirements.
- [ ] Avoided granular decryption errors that create oracles or leak sensitive metadata.
- [ ] Planned key rotation, backup, and authorized decryption of historical data.

### Interoperability and Security Regression Testing

- [ ] RSA 2048 OAEP SHA-256: encrypting 32-byte CEK succeeds; 190-byte plaintext succeeds, 191 bytes rejected.
- [ ] Wrong label / wrong MGF1 digest / wrong private key / malformed wrappedKey rejected.
- [ ] Corrupted/truncated AES-GCM tag or modified AAD/nonce/ciphertext rejected.
- [ ] Encrypting the same plaintext twice produces different ciphertexts due to randomness.
- [ ] Key rotation and historical decryption handle version/keyId properly.
- [ ] JSON/CBOR/binary encoding, Base64URL, byte order, and nonce/tag lengths have golden vectors across peers.
- [ ] Tested identity, authorization, key substitution, and replay separately from crypto "passing tests".
- [ ] Tested file size limits, streaming/chunk framing, memory/CPU pressure, and side-channel/error behavior.

## 14. Remember with One Diagram

```text
                  RSA-OAEP SHA-256 (RSA-2048)
                  max plaintext = 190 bytes
                          |
                     CEK 32 bytes  <---- SecureRandom
                          |
         +----------------+--------------------+
         |                                     |
    RSA-OAEP(public)                       AES-256-GCM
         |                              + nonce 12 bytes
    wrappedCEK 256 bytes                 + AAD + plaintext
         |                                     |
         +----------------+--------------------+
                          |
                   Hybrid envelope
               [wrappedCEK, nonce,
                ciphertext+tag, metadata]
                          |
               RSA-OAEP(private) -> CEK
                          |
              AES-GCM decrypt + verify tag
                          |
                       Plaintext

  Key principle:
  RSA protects a short symmetric key;
  AEAD protects large data and authenticates ciphertext/AAD.
  Neither alone proves who sent the message.
```

**Conclusion:** RSA-OAEP has a small plaintext limit and is best used for **short messages or symmetric keys**, not for encrypting thousands of data blocks directly. With RSA-2048/OAEP SHA-256, the limit is **190 bytes**, plenty to wrap a 32-byte AES-256 CEK. Hybrid encryption combining **RSA-OAEP for the key** and **AEAD for the data** solves size, performance, and integrity requirements. A complete design must also clearly define **format, OAEP parameters, public-key trust, metadata binding, nonce management, and authentication/anti-replay policies**.

### References

- RFC 8017, *PKCS #1: RSA Cryptography Specifications Version 2.2* — RSAES-OAEP, `mLen ≤ k−2hLen−2` formula, and encoding: https://www.rfc-editor.org/rfc/rfc8017
- NIST SP 800-56B Rev. 2 — key establishment methods using integer-factorization cryptography: https://csrc.nist.gov/pubs/sp/800/56/b/r2/final
- NIST SP 800-38D — GCM/GMAC, AEAD nonces and tags: https://csrc.nist.gov/pubs/sp/800/38/d/final
- NIST SP 800-57 Part 1 Rev. 5 — key management and key strength estimation: https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final
- Java SE 17, `OAEPParameterSpec`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/OAEPParameterSpec.html
- Java SE 17, `MGF1ParameterSpec`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/MGF1ParameterSpec.html
- Java SE 17, `Cipher`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html
- Java SE 17, `GCMParameterSpec`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html
- Java SE 17, `SecureRandom`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html