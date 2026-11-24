# 8.1 Public Keys, Private Keys, and Their Relationship to Encryption or Digital Signatures

## Learning Objectives

When encountering a key pair in Java (`PublicKey` and `PrivateKey`), you need to distinguish **who owns the key, who is allowed to know it, and what operations the key is used for**. Two important operations serve different goals:

- **Public-key encryption:** the sender encrypts using the **recipient's public key**; the recipient decrypts using the **corresponding private key**. The primary goal is **confidentiality**.
- **Digital signature:** the signer creates a signature using the **signer's private key**; the verifier uses the **corresponding public key** to verify. The goal is **integrity and origin authentication tied to the identity bound to the key**.

Although both use asymmetric keys, **encryption is not signing**, and **signature verification is not message decryption**. The phrase "encrypting with a private key to sign" is misleading and does not accurately describe modern signature schemes such as RSA-PSS or Ed25519.

This lesson belongs to the **Public-Key Cryptography** topic, focusing on the roles of the two key types, their relationship to encryption/signatures, and how to use the Java Security API. The examples run on Java 17+.

## 1. What Is an Asymmetric Key Pair Really?

**Symmetric cryptography** such as AES uses the same secret key (or directly related keys) for encryption/decryption. **Asymmetric cryptography** uses a **key pair** consisting of:

- `public key`: may be published and distributed to parties that need to encrypt for the owner or verify the owner's signatures.
- `private key`: must be protected by the owner, used for operations that require proving control of the key or recovering secrets in the corresponding scheme.

The two keys are generated together and are **mathematically related**, yet in a secure algorithm with an appropriate key size, knowing the public key is **not sufficient to compute the private key in practice**. "Public key" does not mean you can trust that the key belongs to any arbitrary party claiming it; **the authenticity of the binding between a public key and an identity** is a separate problem.

For example, RSA is based on parameters such as modulus `n`, public exponent `e`, and private exponent `d`; computational hardness tied to the RSA structure helps protect the private key. For elliptic-curve cryptosystems, the construction and operations differ from RSA. Therefore, do not apply RSA formulas or operations to every `PublicKey`/`PrivateKey` pair.

### 1.1 Keys Do Not State Their Own Purpose

`PublicKey` and `PrivateKey` are Java **interfaces**, which does not mean every key works with every engine:

| Algorithm / key pair | Common purpose | Related Java service |
| --- | --- | --- |
| RSA | Key/short-data encryption with RSA-OAEP; signatures with RSA-PSS or an allowed scheme | `Cipher`, `Signature` |
| Ed25519 | EdDSA **digital signature** | `Signature` (`Ed25519`) |
| X25519 | **Key agreement**, producing a shared secret then passing it through a KDF | `KeyAgreement` (`X25519`) |
| EC with ECDSA | Digital signature using an appropriate algorithm | `Signature` (e.g., `SHA256withECDSA`) |
| EC with ECDH | Key agreement, using your own private key and the peer's public key | `KeyAgreement` |

**Ed25519 is not a data encryption algorithm; X25519 is not a signature algorithm.** For RSA, the same key type can support both operations when allowed by the provider and policy, but real-world applications typically use **separate key pairs for encryption and signing** to manage key purpose, permissions, and lifetime.

## 2. Relationship Between Public/Private Keys and Encryption

Suppose **Alice** wants to send a secret to **Bob**. Bob generates a key pair `(Bob.public, Bob.private)` and provides a public key **authenticated as belonging to Bob** to Alice.

```text
Alice (sender)                                 Bob (recipient)
--------------                                 ---------------
Plaintext message
        |
        | Encrypt(Bob.public, plaintext)
        v
   Ciphertext  ------------------------------->  Ciphertext
                                                      |
                                             Decrypt(Bob.private)
                                                      |
                                                      v
                                                   Plaintext
```

With a proper public-key encryption scheme and appropriate parameters:

1. **The sender does not need to know Bob's private key**; only Bob's authentic public key is needed.
2. **Only Bob (or whichever party holds the corresponding private key) can decrypt** under the scheme's security model.
3. Anyone who obtains `Bob.public` can also create ciphertext to send to Bob. Therefore, **encrypting with Bob's public key does not by itself authenticate the sender as Alice**.
4. If an attacker replaces `Bob.public` with their own key, Alice may encrypt for the attacker. You must verify the origin of the public key via certificates, verified fingerprints, a trusted registry, or an authenticated key distribution protocol.

### 2.1 RSA Encryption Must Use a Secure Scheme

RSA operates on integers with mathematical structure; **never use "raw RSA"**. With JCA, a common example is **RSAES-OAEP**:

```java
// Illustrated inside a method with proper exception handling and parameters:
Cipher cipher = Cipher.getInstance(
        "RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
```

The `ECB` in JCE's RSA transformation name is a historical syntax convention of the engine; **it does not mean RSA is encrypting AES blocks in ECB mode**. The scheme must specify the **OAEP hash, MGF1 hash, and label/PSource** with appropriate parameters so both sides interoperate. In particular, do not assume that `OAEPWithSHA-256AndMGF1Padding` automatically sets every MGF1 digest to SHA-256 across all providers; the runnable example below passes `OAEPParameterSpec` explicitly.

**Length limit:** RSA-OAEP only encrypts short plaintexts. With a 2048-bit RSA modulus (`k = 256` bytes) and OAEP using SHA-256 (`hLen = 32` bytes), the message limit is:

\[
mLen \leq k - 2hLen - 2 = 256 - 64 - 2 = 190\ \text{bytes}.
\]

You cannot use RSA-OAEP calls to encrypt an entire large file by arbitrarily splitting it into multiple "RSA blocks". Practical designs typically use **hybrid encryption**: generate a random AES key, encrypt the data with **AES-GCM**, and protect the AES key using an appropriate asymmetric key-encryption/key-wrapping mechanism (such as RSA-OAEP in systems applying RSA). The recipient uses their private key to recover the AES key to decrypt the data. You must specify the format, nonce, tag, key ID, and authenticated metadata.

### 2.2 What Does Encryption Need to Be Secure Beyond the Key Pair?

- The recipient's public key **must belong to the intended recipient**; the recipient's private key must be protected.
- You must choose a secure **scheme and parameters** instead of `Cipher.getInstance("RSA")` and letting the provider decide the padding.
- A ciphertext from an asymmetric encryption scheme **does not constitute proof of who sent it**; when origin authenticity is needed, you must add a signature or an authenticated protocol.
- If using AES-GCM in hybrid encryption, you must ensure a unique nonce per AES key, handle the authentication tag, and bind the necessary context/AAD.
- Encryption alone does not provide **replay protection**: a valid ciphertext can be replayed if the protocol does not track records, sequence numbers, or application nonces.

## 3. Relationship Between Public/Private Keys and Digital Signatures

This time Alice wants Bob to know that the message was indeed signed by **the holder of Alice.private** and that its content has not been altered.

```text
Alice (signer)                                   Bob (verifier)
--------------                                   --------------
Message M
     |
     | Sign(Alice.private, M)
     v
Signature S and M ---------------------------------> M, S
                                                      |
                                           Verify(Alice.public, M, S)
                                                      |
                                                true / false
```

Key steps:

1. Alice holds the private key matching the signature algorithm and creates a `signature` over the **exact data** to be authenticated.
2. Bob already knows the public key **trusted to be bound to Alice's identity**, receives the message and signature, and calls `verify(public, message, signature)`.
3. If verification succeeds, the signature matches the **provided public key** and the verified data bytes. To conclude "Alice signed this," Bob must also **authenticate that the public key truly belongs to Alice**.
4. Modifying the message, critical context, or signature causes verification to fail (with a secure scheme and proper implementation).
5. A digital signature **does not encrypt the message**. Anyone who can read the message can still read it, even with a valid signature.

Signatures provide a foundation for **integrity**, **origin authentication**, and support **non-repudiation** when key management, identity, evidence, and policies are appropriate. They do **not by themselves** provide confidentiality, guarantee who the signer is beyond the authenticated identity, or prevent replay of a valid message.

### 3.1 Why Is Signing Not "Encrypting with a Private Key"?

Saying "encrypt with the private key, decrypt with the public key" is an oversimplified picture derived from certain RSA math and is **wrong for modern digital signatures**:

- RSA-PSS is a **signature** scheme with defined hashing, encoding, salt, and structural verification; the `Signature.sign()` API produces a signature, and `Signature.verify()` checks it.
- `Ed25519` signs and verifies using elliptic-curve operations; **there is no operation that "decrypts a signature into a message"**.
- Most signature schemes verify a signature against the **original message or a scheme-defined digest**; do not use `Cipher` with `ENCRYPT_MODE` and a private key in place of `Signature`.

In Java, use the proper `Signature` engine; with RSA-PSS, agree on the digest, MGF1, salt length, and trailer field, avoiding reliance on provider defaults.

### 3.2 Encryption and Signatures Can Be Used Together

When Alice sends a secret **and** wants Bob to verify Alice, the protocol must provide both **confidentiality** and **origin authentication**:

```text
Bob's secret:          Encrypt(Bob.public, ...)
Alice's identity:      Sign(Alice.private, specified data/context)
```

A combined protocol must clearly specify **which data is signed** (plaintext, ciphertext, or envelope), how identity and metadata are handled, the order of operations, AAD/signature fields, replay protection, and how errors are reported. Do not arbitrarily chain two primitives together and claim all security properties. Deployment standards such as CMS/JWE/JWS/TLS have their own security models and details; choose an appropriate standard for the problem rather than inventing a protocol by guesswork.

## 4. Direct Comparison of the Two Operations

| Question | Asymmetric encryption | Digital signature |
| --- | --- | --- |
| Goal | Keep content/session key **confidential** | Prove **integrity and origin tied to a verified key** |
| Who uses the public key and for what? | **The sender** uses the **recipient's** public key to encrypt | **The verifier** uses the **signer's** public key to verify |
| Who uses the private key and for what? | **The recipient** uses their own private key to decrypt | **The signer** uses their own private key to sign |
| Output | Ciphertext (and required metadata) | Signature (usually sent alongside the message) |
| Is the message publicly readable? | No, if the scheme/key/format is secure | Yes, unless the message is separately encrypted |
| Guarantees sender identity? | No, simply because anyone can use the recipient's public key | Only when the verifier's public key is **trusted to be bound to the signer's identity** |
| Replay protection? | Not built-in | Not built-in |
| Java API | `Cipher` with an encryption scheme such as RSA-OAEP | `Signature` with a signature scheme such as RSA-PSS/Ed25519 |

**Quick mnemonic:** *To encrypt for Bob, use Bob's public key; to sign as Alice, use Alice's private key.* Upon receipt, Bob uses **Bob's private key** to decrypt and **Alice's public key** to verify the signature.

## 5. Java 17: The `KeyPair`, `PublicKey`, `PrivateKey` Model

The relevant APIs are in `java.security`, `java.security.spec`, and `javax.crypto`:

| API | Proper usage |
| --- | --- |
| `KeyPairGenerator` | Generates a new key pair for an algorithm (e.g., `RSA`, `Ed25519`, `X25519`). |
| `KeyPair` | Holds a key pair; `getPublic()` and `getPrivate()` return the corresponding interfaces. |
| `PublicKey` / `PrivateKey` | Key objects for `Cipher`, `Signature`, `KeyAgreement` depending on the algorithm type. |
| `Cipher` | Encryption/decryption using a transformation such as `RSA/ECB/OAEPWithSHA-256AndMGF1Padding`. |
| `Signature` | `initSign(private)`, `update`, `sign`; or `initVerify(public)`, `update`, `verify`. |
| `KeyAgreement` | Shared secret agreement, e.g., with X25519 or ECDH; **not the same as encrypt/verify**. |
| `KeyFactory` | Reconstructs key objects from a `KeySpec` such as X.509 public key or PKCS#8 private key. |
| `KeyStore` / KMS / HSM | Stores or retrieves keys via a protected mechanism; may use **non-exportable** private keys. |

`KeyPairGenerator.getInstance("RSA")` only specifies the algorithm for generating the key pair. To use that key pair for **encryption**, call `Cipher` with RSA-OAEP; to use it for **signatures**, call `Signature` with RSA-PSS. Do not use `KeyPairGenerator` as a substitute for encryption/signing.

You can generate an illustrative RSA key pair as follows:

```java
// Illustrative snippet inside a method handling checked exceptions:
KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
generator.initialize(2048);
KeyPair pair = generator.generateKeyPair();
PublicKey publicKey = pair.getPublic();
PrivateKey privateKey = pair.getPrivate();
```

2048-bit RSA is used here so the exercise runs quickly and output is easy to inspect; production systems select key size, lifecycle, and key protection according to the **applicable security policy** (for example, RSA 3072 when higher long-term security is required). Do not just pick a bit length while ignoring the scheme, provider, and rotation schedule.

## 6. Complete Java 17+ Example: RSA-OAEP and RSA-PSS

The following program uses **two separate RSA key pairs** to clarify the two roles:

- `recipient`: public key encrypts, private key decrypts.
- `signer`: private key signs, public key verifies.

It also configures OAEP **SHA-256 + MGF1(SHA-256)** and PSS **SHA-256 + MGF1(SHA-256), 32-byte salt, trailer 1** explicitly. Explicit parameter configuration avoids mismatches caused by provider defaults. Create the file **`AsymmetricRolesDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;

public final class AsymmetricRolesDemo {
    private static final OAEPParameterSpec OAEP =
            new OAEPParameterSpec(
                    "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
                    PSource.PSpecified.DEFAULT);

    private static final PSSParameterSpec PSS =
            new PSSParameterSpec(
                    "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
                    32, 1);

    private static byte[] encryptFor(PublicKey recipient, byte[] data)
            throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance(
                "RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
        cipher.init(Cipher.ENCRYPT_MODE, recipient, OAEP);
        return cipher.doFinal(data);
    }

    private static byte[] decryptWith(PrivateKey recipient, byte[] ciphertext)
            throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance(
                "RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
        cipher.init(Cipher.DECRYPT_MODE, recipient, OAEP);
        return cipher.doFinal(ciphertext);
    }

    private static byte[] signWith(PrivateKey signer, byte[] data)
            throws GeneralSecurityException {
        Signature signature = Signature.getInstance("RSASSA-PSS");
        signature.setParameter(PSS);
        signature.initSign(signer);
        signature.update(data);
        return signature.sign();
    }

    private static boolean verifyWith(
            PublicKey signer, byte[] data, byte[] signed)
            throws GeneralSecurityException {
        Signature signature = Signature.getInstance("RSASSA-PSS");
        signature.setParameter(PSS);
        signature.initVerify(signer);
        signature.update(data);
        return signature.verify(signed);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        KeyPair recipient = generator.generateKeyPair();
        KeyPair signer = generator.generateKeyPair();

        byte[] message = "Hello public-key crypto"
                .getBytes(StandardCharsets.UTF_8);

        byte[] encrypted = encryptFor(recipient.getPublic(), message);
        byte[] recovered = decryptWith(recipient.getPrivate(), encrypted);
        System.out.println("Decryption matches: " +
                Arrays.equals(message, recovered));

        byte[] signature = signWith(signer.getPrivate(), message);
        System.out.println("Signature valid: " +
                verifyWith(signer.getPublic(), message, signature));

        byte[] changed = message.clone();
        changed[0] ^= 1;
        System.out.println("Modified message valid: " +
                verifyWith(signer.getPublic(), changed, signature));

        System.out.println("RSA ciphertext bytes: " + encrypted.length);
        System.out.println("RSA signature bytes: " + signature.length);
    }
}
```

Compile and run with JDK 17+ having a provider that supports OAEP/PSS with the parameters used:

```bash
javac --release 17 AsymmetricRolesDemo.java
java AsymmetricRolesDemo
```

**Stdout** (ciphertext and signature bytes change between runs due to randomness, while the following lines remain the same):

```text
Decryption matches: true
Signature valid: true
Modified message valid: false
RSA ciphertext bytes: 256
RSA signature bytes: 256
```

Detailed explanation:

1. `recipient.getPublic()` is passed to `Cipher.ENCRYPT_MODE`; **only** the matching `recipient.getPrivate()` can perform `Cipher.DECRYPT_MODE` on the record in the demo.
2. `signer.getPrivate()` is passed to `Signature.initSign`, and `signer.getPublic()` to `Signature.initVerify`. The code does not use `Cipher` to sign.
3. `Signature.update(message)` feeds the **exact bytes** of the message to the signature scheme; PSS performs internal hashing/encoding according to the specified parameter set. You do not need to hash the message yourself and pass the digest into `update` as if it were the original message.
4. Changing 1 byte of the message makes `verify()` return `false`; using the **public key of another pair** will also not verify as a valid signature.
5. RSA-2048 has a 256-byte modulus, so RSA-OAEP produces a **256-byte** ciphertext, and the RSA-PSS signature is also **256 bytes** long. This size depends on the modulus, **not** on the length of the short message chosen.
6. The two key pairs are **separate** even though both use the RSA algorithm. In production, each key must be bound to an identity, purpose, key usage, and metadata; do not assume every RSA key is allowed for every purpose.
7. The name `RSASSA-PSS` and the OAEP transformation may require a suitable provider. The code runs on environments supporting the requested schemes/parameters; being listed in standard names does not mean every Java SE implementation supports every combination. Check your target JDK/provider.

This is an **in-memory** demo: the program generates fresh keys on each run and has no peers communicating over a network. To deploy in a real service, you need an authenticated public-key distribution mechanism, a secure private-key store, a versioned message/signature/ciphertext format, explicit parameters, and clear error handling.

## 7. Storing Public Keys, Protecting Private Keys, and Verifying Identity

### 7.1 Public Keys Can Be Public, But Must Be Authenticated

A public key only indicates that **the key is mathematically related to some private key**, not that it belongs to Alice or Bob. Ways to establish identity binding:

- **X.509 certificate:** a certificate contains a public key and subject data, signed by an issuer; the verifier must validate the trust chain, validity period, name/identifier, key usage/extended key usage, algorithms, and revocation policy where applicable.
- **Fingerprint or public key pinning:** pre-verified over a trusted channel, taking care to establish a key-update process.
- **Application-managed trusted registry:** look up `key_id` along with owner, status, and purpose; do not choose a key based solely on a self-declared ID from unauthenticated input.

**Successfully verifying a signature with an attacker-supplied key** does not prove the attacker is Alice. **Encrypting with a swapped attacker public key** does not guarantee only Bob can read the data.

### 7.2 Key Encoding/Formats in Java

When public/private keys can be exported as bytes, Java commonly uses:

- **X.509 SubjectPublicKeyInfo (SPKI)** for public keys, typically `PublicKey.getFormat() == "X.509"`.
- **PKCS#8 PrivateKeyInfo** for private keys, typically `PrivateKey.getFormat() == "PKCS#8"` if the private key is exportable.

Illustrative snippet **inside a method** after obtaining `pair`:

```java
byte[] publicEncoded = pair.getPublic().getEncoded();
java.security.KeyFactory factory =
        java.security.KeyFactory.getInstance("RSA");
java.security.PublicKey publicAgain = factory.generatePublic(
        new java.security.spec.X509EncodedKeySpec(publicEncoded));
```

Never treat a well-formed byte array as having **authenticated identity**. PEM strings are merely a Base64/text packaging format; public keys can generally be shared, whereas **private keys must never be placed in logs, source code, repositories, or public APIs**. Private keys stored in an HSM/KMS may be **non-exportable** (`getEncoded()` returns `null`), even though the key object still works with the appropriate provider.

### 7.3 Key Lifecycle Management

A design needs to cover: generating keys with an appropriate RNG, restricting access to private keys, secure backup/recovery procedures, separating signing keys from decryption keys, key rotation, retaining historical public keys/certificates to verify old signatures, revoking keys upon compromise, and recording `key_id`/algorithm IDs in the data format. Do not destroy a private key used to decrypt old ciphertexts if you still need to read them; conversely, retaining old private keys for too long increases risk.

When a signing key pair is compromised, an attacker can forge new signatures; running `verify` alone cannot tell which signatures were issued before compromise without timestamps, audit logs, revocation, and trust policies.

## 8. Connection to Key Agreement and Hybrid Encryption

A `PrivateKey`/`PublicKey` pair can also be used for **key agreement**, which does not fall directly under the two operations above. For example, X25519:

```text
Alice.private + Bob.public    ---> shared secret
Bob.private   + Alice.public  ---> same shared secret
```

The agreement result is passed through an **appropriate KDF** to derive keys for AEAD. Do not treat the raw shared secret as an AES key directly unless specified. Key agreement without authenticating the peer's public key is vulnerable to **man-in-the-middle** attacks; signatures/certificates or an appropriate authenticated protocol are required. In Java, the relevant engine is `KeyAgreement`, not `Signature.verify` or `Cipher.decrypt`.

Three common patterns:

| Problem | Primary primitive | Output needed |
| --- | --- | --- |
| Need to send a secret to a recipient's public key | Public-key encryption or authenticated hybrid encryption | Ciphertext the recipient can decrypt |
| Need anyone to verify a document's origin | Digital signature | Message + signature + trusted public key/certificate |
| Two parties establish a confidential channel | Authenticated key agreement + KDF + AEAD | Session key, ciphertext/tag, and protocol state |

**Do not invent an imaginary "symmetric" operation between public/private keys for every goal.** Different algorithms have distinct functions, formats, security guarantees, and Java engines.

## 9. Common Mistakes and How to Fix Them

| Statement / issue | Problem | How to fix |
| --- | --- | --- |
| "Alice's public key can be used to decrypt everything Alice signs." | A digital signature is not a ciphertext of the message. | Use `Signature.verify(Alice.public, message, signature)`. |
| "Encrypting with Bob.public means Alice proved she sent it." | Anyone who knows `Bob.public` can encrypt for Bob. | Add origin authentication using an appropriate scheme/protocol. |
| "If `verify` succeeds, the message is confidential." | Signatures do not protect confidentiality. | Encrypt separately if data must be hidden. |
| "Any public key labeled Alice can be used." | Keys do not bind identity on their own. | Verify certificates/pinning/trust registry and key usage. |
| "Using `Cipher` with a private key is enough for RSA signatures." | Bypasses the signature security scheme/padding and API. | Use `Signature` with RSA-PSS or an approved scheme. |
| "`Cipher.getInstance("RSA")` is secure RSA." | The provider may apply an unintended default padding. | Explicitly require RSA-OAEP and hash/MGF1 parameters. |
| "RSA can encrypt data of arbitrary length." | RSA-OAEP has a message length limit depending on modulus/hash. | Use hybrid encryption to protect an AES key, encrypting payload with AEAD. |
| "The same key pair should be used for both signing and decryption for convenience." | Mixes purposes, risk lifecycles, and access permissions. | Separate key pairs in production deployments. |
| `InvalidKeyException` when calling `Cipher`/`Signature`. | Wrong key type (public/private), size, or key usage/provider. | Check key role, algorithm, key policy, and `init` parameters. |
| `Signature.verify()` returns `false` | Mismatched message, public key, signature, or PSS params. | Check byte encoding, parameter set, and trusted source key. |
| `BadPaddingException` during OAEP decryption | Invalid ciphertext/key/OAEP params. | Reject the record; do not retry with raw RSA or weak padding. |
| "The signature is valid, so the message cannot be replayed." | Signatures do not prevent replay. | Add nonce/sequence/timestamp/expiry inside the signed data and stateful checks. |

## 10. Self-Check Questions

**1. Alice wants Bob to be the only person who can read a message. Which key does Alice use?**  
**Bob's authenticated public key** to encrypt under an appropriate scheme; Bob uses Bob's private key to decrypt.

**2. Bob wants to verify a message signed by Alice. Which key does Bob use?**  
**Alice's authenticated public key** along with the message and signature. Alice uses Alice's private key to sign.

**3. Does a valid signature guarantee that no one can read the message?**  
No. A signature checks integrity and origin relative to the key; encryption is needed for confidentiality.

**4. If you have a public key but do not know its real owner, can you assert who the sender is?**  
No. You must verify the **key → identity binding** through a trusted mechanism.

**5. Why shouldn't RSA-OAEP directly encrypt large files?**  
The data limit is low (for example, RSA-2048 + OAEP SHA-256 allows at most **190 bytes**). Use hybrid encryption/AEAD for large payloads.

**6. Can Ed25519 and X25519 be used interchangeably?**  
No. Ed25519 is a signature scheme and X25519 is key agreement; their names look similar, but their operation types and goals differ.

**7. If both signatures and encryption are needed, must you use one key pair or two?**  
A protocol may use multiple algorithms/keys; key management best practice typically **separates key pairs by function** and authenticates the public keys of both sender and recipient according to their roles.

## Authoritative References

- [Java SE 17 — `KeyPairGenerator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyPairGenerator.html): key pair generation and key generation parameters.
- [Java SE 17 — `Signature`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html): `initSign`, `initVerify`, `update`, `sign`, `verify`.
- [Java SE 17 — `Cipher`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): encryption/decryption, transformations, and `init` usage.
- [Java SE 17 — `OAEPParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/OAEPParameterSpec.html): OAEP hash, MGF1, and PSource; do not rely on SHA-1 defaults.
- [Java SE 17 — `PSSParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/PSSParameterSpec.html): digest, MGF, salt length, and trailer field.
- [Java SE 17 — Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): `RSA`, `RSASSA-PSS`, `Ed25519`, `X25519` names and naming/implementation scope.
- [RFC 8017 — PKCS #1: RSA Cryptography Specifications v2.2](https://www.rfc-editor.org/rfc/rfc8017): RSAES-OAEP, RSASSA-PSS, and message length limits.
- [NIST — Glossary: Digital Signature](https://csrc.nist.gov/glossary/term/digital_signature): integrity/authentication, supports non-repudiation; does not provide confidentiality.
- [NIST — Glossary: Public Key](https://csrc.nist.gov/glossary/term/public_key): public key used to verify signatures, encrypt keys, or participate in key agreement depending on the scheme.

**Key takeaway:** **A public key is used for operations that others are permitted to perform; a private key is used for operations that only the owner is authorized to perform.** In encryption, it is *encrypt with recipient's public key → decrypt with recipient's private key*; in signatures, it is *sign with signer's private key → verify with signer's public key*. Those two relationships serve **different security goals**, so they must be accompanied by identity authentication, proper schemes, explicit parameters, and sound key management.
