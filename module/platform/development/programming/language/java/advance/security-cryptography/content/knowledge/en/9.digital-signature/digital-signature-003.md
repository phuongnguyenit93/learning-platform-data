# 9.3. Distinguishing Signing with a Private Key from Encrypting with a Public Key

**Digital signatures** and **public-key encryption** both belong to asymmetric cryptography, yet they solve **two different problems**. A digital signature uses the **signer's private key** to create a signature, then uses the **same signer's public key** to verify origin and integrity. Public-key encryption uses the **recipient's public key** to encrypt, then uses the **recipient's private key** to decrypt in order to keep the content confidential.

In Java 21, these two tasks also have **separate APIs, algorithms, and parameter requirements**: `java.security.Signature` is for signing/verifying, while `javax.crypto.Cipher` can perform RSA-OAEP encryption/decryption. This lesson focuses on the right mental model, avoiding the misconception that “signing is encrypting with a private key,” and applying both safely in real protocols.

## Learning objectives

After this lesson, you can:

1. Answer decisively: **who uses which key, for what purpose, and who can verify or decrypt**.
2. Explain why a digital signature protects **origin and integrity** without hiding the message; and why encrypting with the recipient's public key **does not by itself prove the sender's identity**.
3. Distinguish `Signature`, `Cipher`, `KeyPairGenerator`, `PublicKey`, and `PrivateKey` in Java 21; recognize that Ed25519, RSA-PSS, and RSA-OAEP are **different schemes**.
4. Compile/run Java 21 programs demonstrating: Ed25519 sign → verify, altered message → signature fails; RSA-OAEP encrypt → decrypt, a third party can also encrypt with the public key; RSA-PSS signing with explicit parameters.
5. Choose the right mechanism when an application needs **confidentiality**, **tamper detection**, **proof of signer**, or **both simultaneously**.
6. Avoid mistakes in key management, certificate/public-key trust, padding, signed data scope, message size limits, replay protection, and hybrid encryption.

## 1. Four keys to distinguish when Alice sends to Bob

Suppose Alice sends a document to Bob:

- **Alice** has a signing key pair `(sk_A, pk_A)`: `sk_A` is the private key only Alice is authorized to use; `pk_A` is the corresponding public key whose origin Bob must authenticate.
- **Bob** has an encryption key pair `(sk_B, pk_B)`: `sk_B` is the private key only Bob holds; `pk_B` is the public key Alice must verify belongs to Bob.

Signing:

```text
Alice: signature = Sign(sk_A, message)
Alice → Bob: message, signature
Bob: Verify(pk_A, message, signature) → true / false
```

Public-key encryption:

```text
Alice: ciphertext = Encrypt(pk_B, message)
Alice → Bob: ciphertext
Bob: message = Decrypt(sk_B, ciphertext)
```

**Two asymmetric arrows of purpose:** the public key to **verify a signature** must belong to the *signer*; the public key to **encrypt for confidentiality** must belong to the *recipient*. Both are called “public key,” but they are not the same key, the same algorithm, or the same usage authority.

| Question | Digital signature | Public-key encryption |
| --- | --- | --- |
| Primary goal | Verify that a message was created by the holder of the signing private key and was not modified | Keep content secret from anyone lacking the matching decryption private key |
| Creator | **Signer**, using the **signer's private key** | **Sender**, using the **recipient's public key** |
| Verifier / recoverer | Verifier, using the **signer's public key** | **Recipient**, using the **recipient's private key** |
| Transmitted data | Message (readable) + signature | Ciphertext (and metadata/wrapped key if hybrid encryption is used) |
| API output | `Signature.sign()` → signature bytes; `verify()` → boolean | `Cipher.doFinal()` → ciphertext or plaintext |
| Someone else with the public key | Can verify the signature, **cannot create a valid signature without the private key** | Can **encrypt their own data** to send to the recipient, but cannot decrypt received ciphertext without the private key |
| Does this mechanism alone keep data secret? | **No** | Yes, if using a secure scheme/configuration and proper key management |
| Does this mechanism alone prove the sender? | Conditionally: requires verifying that the public key truly belongs to the signer | **No**; anyone who knows the public key can encrypt |
| Automatic replay protection? | **No** | **No** |

> Quick mnemonic: **Sign = signer's private key → signer's public key verifies. Encrypt = recipient's public key → recipient's private key decrypts.**

## 2. Why is a digital signature not “encrypting with the private key”?

You may encounter the classic folklore explanation: *“RSA signs by encrypting a hash with the private key, and the recipient decrypts the hash with the public key.”* That is a loose analogy for raw textbook RSA math, **not an accurate definition and not a safe way to program cryptography**.

### 2.1 Two primitives/schemes with different designs

- **RSA encryption** uses an encryption scheme such as **RSAES-OAEP**. Its goal is plaintext confidentiality; it has its own padding rules, hash/MGF functions, and error handling.
- **RSA signature** uses a signing scheme such as **RSASSA-PSS** or, for compatibility with existing standards/systems, **RSASSA-PKCS1-v1_5**. Its goal is producing a publicly verifiable, unforgeable signature structure.
- Even though both schemes share the RSA mathematical foundation, **OAEP is not PSS**; you cannot switch `Cipher` to `ENCRYPT_MODE` with a private key and treat the result as a valid RSA-PSS signature.
- **Ed25519/ECDSA** are **signature** algorithms; there is no equivalent “encrypt with an Ed25519 public key” operation. **X25519/ECDH** are key exchange/agreement mechanisms, neither signatures nor standalone message encryption.

**Therefore:** use `Signature` to sign/verify; use an encryption scheme designed for confidentiality. Never use raw RSA (`NoPadding`), “private-key encryption,” or hand-rolled RSA padding/math blocks to create signatures.

### 2.2 “Verifiable” is different from “readable content”

A digital signature is sent alongside the message; the public key only lets the recipient check whether the signature is valid for those **exact message bytes**. A signature does not make the message confidential: an eavesdropper still sees the message if it is sent in cleartext.

Conversely, an RSA-OAEP ciphertext is produced with Bob's public key, but since that public key is public, **Alice, Carol, and an attacker can all encrypt a message to send to Bob**. Bob successfully decrypting it does not mean the message came from Alice.

### 2.3 Example of a document needing a signature without encryption

A publisher releases an installer file and an accompanying signature. Anyone is allowed to download the file and read its contents, but will only accept it if the signature is valid and the public key is confirmed to belong to the publisher. Here **authenticity/integrity** is needed, not confidentiality of a public file.

Conversely, a message containing personal information intended only for Bob needs **confidentiality**, and if Bob must verify Alice truly sent it, a signature or appropriate sender authentication mechanism should be added.

## 3. Trust conditions for a public key

Suppose an attacker swaps `pk_A` with their own public key and signs a forged message themselves. If Bob mistakenly trusts that public key as Alice's, `verify()` still returns `true` — **mathematically valid signature, forged identity**.

Thus a system must have a way to **bind a public key to a trusted identity/entity**:

- X.509 certificates with trust chain validation, target name/identity checks, validity periods, key usage, and appropriate revocation policy.
- A public key distributed over an authenticated channel, or a key fingerprint verified out-of-band.
- A trusted key registry keyed by `keyId`, tenant, principal, issuer, algorithm, and version, with a rotation/revocation lifecycle.
- For encryption, Alice must also verify `pk_B` genuinely belongs to Bob. If an attacker swaps in the attacker's public key, Alice will encrypt **for the attacker**, breaking confidentiality before Bob ever receives anything.

**Private keys** must be kept secret; store them in a keystore, KMS, or HSM as required, restrict separate sign/decrypt permissions, and audit usage. Never place private keys in Git, source code, logs, or API responses. Having a public key without authenticating its source is **not enough** to establish trust.

**Non-repudiation** is often cited as a benefit of digital signatures, but it is a conditional property: private key protection, owner identification, and business policies/records are what establish accountability. A single valid signature byte array does not by itself constitute absolute legal proof.

## 4. Which Java 21 APIs are used for each job?

| API / algorithm name | Proper role | Key input |
| --- | --- | --- |
| `KeyPairGenerator.getInstance("Ed25519")` | Generates key pair for Ed25519 signatures | No existing key; generates a new pair |
| `Signature.getInstance("Ed25519")` | Ed25519 signing and verification | `initSign(PrivateKey)` / `initVerify(PublicKey)` |
| `KeyPairGenerator.getInstance("RSA")` | Generates RSA key pair | Appropriate size such as 3072 bits in the example |
| `Signature.getInstance("RSASSA-PSS")` | RSA-PSS signing and verification | Signer's private key / signer's public key, plus PSS parameters |
| `Cipher.getInstance("RSA/ECB/OAEPWithSHA-256AndMGF1Padding")` | RSA-OAEP encrypting a small payload / session key | `ENCRYPT_MODE` with recipient's public key; `DECRYPT_MODE` with recipient's private key |
| `OAEPParameterSpec`, `MGF1ParameterSpec` | Specifies hash, MGF, and parameters for OAEP | Identical configuration on both sides |
| `PSSParameterSpec` | Specifies digest, MGF1, salt length, and trailer for PSS | Identical configuration on both sides |

These algorithms are supported by common Oracle/OpenJDK 21 providers such as **SunEC**, **SunRsaSign**, and **SunJCE**. Other providers, HSMs, or FIPS-constrained environments may support different algorithm sets and policies; always verify on the target runtime. “Having the `Signature` API” does not mean a provider supports whatever scheme string you pass in.

**Reading the RSA transformation accurately:** the word “`ECB`” in the RSA transformation `RSA/ECB/OAEPWithSHA-256AndMGF1Padding` is largely a syntactic convention in some providers' naming; **do not confuse it with AES-ECB**, a block-cipher mode that should not be used for sensitive data. With RSA, pay close attention to **OAEP padding** and MGF1 parameters.

## 5. Java 21 practice: Ed25519 signing, RSA-OAEP encryption

The demo creates **two separate key pairs**:

- `senderKeys` for Alice's **Ed25519 signature**. An Ed25519 key pair cannot be used for RSA encryption.
- `recipientKeys` for **RSA-OAEP encryption** sent to Bob. The example only encrypts a short message, not a large file.

This is a standalone program requiring no libraries beyond standard JDK 21. Create **`SignVsEncryptDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.spec.MGF1ParameterSpec;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;

public class SignVsEncryptDemo {
    // Explicit OAEP: SHA-256 hash and MGF1-SHA256 on both sides.
    private static final OAEPParameterSpec OAEP_SHA256 =
            new OAEPParameterSpec("SHA-256", "MGF1",
                    MGF1ParameterSpec.SHA256, PSource.PSpecified.DEFAULT);

    public static void main(String[] args) throws Exception {
        byte[] message = "Transfer 100".getBytes(StandardCharsets.UTF_8);
        byte[] altered = "Transfer 900".getBytes(StandardCharsets.UTF_8);

        // 1) Ed25519: signer uses private key.
        KeyPair senderKeys = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(senderKeys.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(senderKeys.getPublic());
        verifier.update(message);
        System.out.println("signature valid: " + verifier.verify(signature));

        verifier.initVerify(senderKeys.getPublic());
        verifier.update(altered);
        System.out.println("altered message valid: " +
                verifier.verify(signature));

        // 2) RSA-OAEP: sender uses recipient's public key.
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(3072);
        KeyPair recipientKeys = generator.generateKeyPair();

        Cipher encryptor =
                Cipher.getInstance("RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
        encryptor.init(Cipher.ENCRYPT_MODE,
                recipientKeys.getPublic(), OAEP_SHA256);
        byte[] ciphertext = encryptor.doFinal(message);

        Cipher decryptor =
                Cipher.getInstance("RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
        decryptor.init(Cipher.DECRYPT_MODE,
                recipientKeys.getPrivate(), OAEP_SHA256);
        byte[] recovered = decryptor.doFinal(ciphertext);
        System.out.println("decryption restored original: " +
                Arrays.equals(message, recovered));

        // Anyone with Bob's public key can encrypt and send to Bob.
        encryptor.init(Cipher.ENCRYPT_MODE,
                recipientKeys.getPublic(), OAEP_SHA256);
        byte[] outsiderCiphertext = encryptor.doFinal(altered);
        decryptor.init(Cipher.DECRYPT_MODE,
                recipientKeys.getPrivate(), OAEP_SHA256);
        System.out.println("outsider can encrypt: " +
                Arrays.equals(altered, decryptor.doFinal(outsiderCiphertext)));
    }
}
```

Compile and run on JDK 21, or a compiler supporting `--release 21` with a sufficiently recent runtime:

```text
java -version
javac -version
mkdir out
javac --release 21 -encoding UTF-8 -d out SignVsEncryptDemo.java
java -cp out SignVsEncryptDemo
```

Stdout:

```text
signature valid: true
altered message valid: false
decryption restored original: true
outsider can encrypt: true
```

Line-by-line explanation:

1. **`signature valid: true`**: `signer.initSign(senderKeys.getPrivate())` creates a signature for the exact `message` bytes; `verifier.initVerify(senderKeys.getPublic())` uses the **signer's** public key to verify.
2. **`altered message valid: false`**: changing “100” to “900” while keeping the original signature causes verification to fail. This illustrates **integrity and authentication via signature**, not tamper detection via encryption.
3. **`decryption restored original: true`**: Bob uses **Bob's private key** and the matching `OAEPParameterSpec` to decrypt the ciphertext created with Bob's public key.
4. **`outsider can encrypt: true`**: any third party holding Bob's public key can encrypt another message to Bob. Therefore, Bob's successful decryption **does not prove the sender is Alice**.

The program generates random keys and ciphertexts on each run, but does not print random values, so the output lines are always predictable when the provider supports the algorithms. The public keys come from the same key pairs within the demo, so the program **does not test** public-key distribution or authentication over a network.

### 5.1 Important notes on OAEP parameters

The code **explicitly** passes `OAEPParameterSpec("SHA-256", "MGF1", MGF1ParameterSpec.SHA256, PSource.PSpecified.DEFAULT)`. This makes explicit that both the **OAEP hash** and the **hash used in MGF1** are SHA-256; do not assume the string `OAEPWithSHA-256AndMGF1Padding` forces every provider to choose the same MGF digest if left unconfigured. Both encrypting and decrypting ends must use compatible configurations.

Never use `RSA/ECB/NoPadding`, “raw RSA,” or arbitrarily swap OAEP for obsolete padding. If the ciphertext, key, or parameters are wrong, decryption can throw `BadPaddingException` or a related exception; handle errors uniformly internally and avoid creating a **decryption oracle** through responses, timing, or logs.

With RSA-OAEP, **plaintext size is bounded by the modulus and hash**. Per PKCS #1, the maximum limit is:

```text
messageLength <= k - 2*hLen - 2
k    = length of RSA modulus in bytes
hLen = byte length of OAEP hash (SHA-256 = 32)
```

3072-bit RSA has `k = 384` bytes; with SHA-256, the maximum is **384 - 64 - 2 = 318 bytes**. This is a scheme limit, not “the length of file you can encrypt.” To encrypt files or long messages, use **hybrid encryption** (see section 8).

## 6. Same RSA family, separate signing scheme: RSA-PSS

If an application uses **RSA for signatures** instead of Ed25519, choose `Signature.getInstance("RSASSA-PSS")` and specify `PSSParameterSpec`. The fact that both RSA-PSS and RSA-OAEP carry the name RSA **does not turn the two operations into one**.

Create **`RsaPssSignatureDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;

public class RsaPssSignatureDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(3072);
        KeyPair pair = generator.generateKeyPair();
        byte[] message = "Order 123".getBytes(StandardCharsets.UTF_8);

        // SHA-256 digest, MGF1 SHA-256, 32-byte salt, trailerField=1.
        PSSParameterSpec params = new PSSParameterSpec(
                "SHA-256", "MGF1", MGF1ParameterSpec.SHA256, 32, 1);

        Signature signer = Signature.getInstance("RSASSA-PSS");
        signer.setParameter(params);
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] tag = signer.sign();

        Signature verifier = Signature.getInstance("RSASSA-PSS");
        verifier.setParameter(params);
        verifier.initVerify(pair.getPublic());
        verifier.update(message);
        System.out.println("RSA-PSS valid: " + verifier.verify(tag));
    }
}
```

```text
javac --release 21 -encoding UTF-8 RsaPssSignatureDemo.java
java RsaPssSignatureDemo
```

Stdout:

```text
RSA-PSS valid: true
```

In the example, `Signature` handles hashing and encoding per the RSA-PSS scheme, then verifies with the public key. You **do not** write `Cipher.init(ENCRYPT_MODE, privateKey)` as a substitute. For RSA-PSS, both ends must match on **digest, MGF, salt length, trailer field**, and the chosen scheme. If signatures must interoperate with another system, specify parameters and signature format explicitly.

*Note:* a single RSA pair does not have to be used for both signing and encryption. Good practice is **separating keys by purpose**, restricting private key permissions, managing rotation, and selecting schemes per policy. X.509 certificates also carry `keyUsage` or `extendedKeyUsage` attributes to govern key usage in relevant contexts.

## 7. When to sign, when to encrypt?

| Scenario | What is needed? | Reason |
| --- | --- | --- |
| Publisher releases a public update and signature | **Digital signature** | The file may be public; downloaders must know it was not altered and came from the right publisher |
| Sending secrets to a recipient with a trusted public key | **Public-key / hybrid encryption** | Others cannot read the content without the recipient's private key |
| Transaction order that is both sensitive and needs signer proof | **Sign + encrypt or an authenticated protected channel** | Requires both origin/integrity and confidentiality |
| Proving who approved a document for auditing | **Digital signature + identity binding, timestamp, approval records** | Encryption only hides content; it does not prove who signed |
| HTTPS API communication with TLS and client authentication | **TLS + application authentication mechanisms per requirements** | TLS protects the transport channel; message-level signatures are an extra decision based on the threat model |
| Encrypting a large file | **AES-GCM with a session key + key wrapping/agreement** | RSA-OAEP cannot directly encrypt large files |
| Valid signature replayed causing duplicate action | **Bind nonce, timestamp, request ID, and replay state** | A valid signature does not mean a fresh request |

**No single mechanism automatically satisfies every goal.** Choices must stem from security properties and the threat model: who can read, who can send, who is allowed to verify, and who is allowed to open the data.

### 7.1 Are signatures and MAC/HMAC the same?

Both digital signatures and MACs can check integrity/authenticity under key assumptions, but:

- **MAC/HMAC** uses a **symmetric secret key**: any party knowing the key can generate tags. There is no public verification analogous to digital signatures; accountability between two parties holding the same key is very different.
- **Digital signatures** use a **private key to sign** and a **public key to verify**. Verifiers typically cannot create valid signatures; this is useful when many parties need to verify while only one entity is authorized to sign.
- **Public-key encryption** hides the message from anyone lacking the decryption private key; by itself, it does not perform the job of a signature or HMAC.

## 8. If you need both confidentiality and sender authentication: envelope design

Suppose Alice must send Bob a confidential order and Bob must verify that Alice herself issued it. A typical design includes:

1. Alice creates a payload containing **protocol version, senderId, recipientId, requestId, timestamp, and content**; following an agreed serialization/canonicalization rule.
2. Alice uses **Alice's signing private key** to sign the agreed bytes. The signature must cover all data affecting transaction meaning and context.
3. Generate a **random session key** for **AES-GCM**, encrypting the payload and signature with AES-GCM using a unique nonce/IV and appropriate AAD. This protects confidentiality and ciphertext integrity.
4. Use **Bob's encryption public key** with RSA-OAEP to **wrap the session key** (not the whole large file), or use a standardized KEM/HPKE mechanism. Transmit the envelope containing metadata, wrapped key, nonce, ciphertext, and GCM tag.
5. Bob uses **Bob's decryption private key** to unwrap the session key, decrypt/verify the AEAD tag, and extract the message and signature.
6. Bob retrieves **Alice's trusted signing public key**, verifies the signature, and only then executes business logic. If transactions must not repeat, add **anti-replay state/idempotency**.

```text
Alice                                 Bob
------                                ------
Sign(sk_A, payload)                   trust(pk_A)
  |                                      ^
  v                                      |
payload + signature                  Verify(pk_A, payload, signature)
  |                                      ^
Encrypt_AES_GCM(random sessionKey)       |
  |                                      |
Wrap_RSA_OAEP(pk_B, sessionKey)          |
  |                                      |
  +------------ envelope ------------> Unwrap(sk_B), AES-GCM decrypt
```

This is an **architectural diagram**, not a protocol specification or standalone code to implement from scratch. In practice you must define exact AAD, version, key ID, canonical bytes, nonce/IV rules, error responses, and replay defenses. In particular, **an AES-GCM IV/nonce must never be reused with the same key**. Using an established standard library/protocol is usually safer than inventing a custom envelope.

Options like **X25519** provide *key agreement*, not direct “public-key encryption”; the shared secret then needs a KDF and AEAD. **HPKE** is a standard design integrating KEM/KDF/AEAD steps. Choosing among RSA-OAEP, HPKE, or TLS depends on the protocol, interoperability, and system policy.

### 8.1 Sign before or after encryption?

Signing plaintext and encrypting message + signature, or signing an envelope containing ciphertext and metadata, each carry trade-offs regarding identity, exposed information, verifier scope, and forwarding risks. There is no single “sign-first / encrypt-first” rule right for every protocol.

When evaluating, ask clearly: **who needs to verify the signature and at which step**, what metadata must be signed/AAD-protected, whether a recipient could forward the signature into another context, whether the signer could be turned into a signing oracle, and whether the signature is checked **before any business side effects**. If using an existing standard such as CMS/JWS/JWE, follow the standard's profile and processing rules rather than composing an arbitrary order yourself.

## 9. Correctness depends on the exact signed bytes and context

A signature verifies a **byte sequence**, not “human intent.” For example, JSON:

```json
{"amount":100,"currency":"VND"}
```

and

```json
{ "currency": "VND", "amount": 100 }
```

May represent the same logical data yet have **different UTF-8 bytes**; if the system signs the JSON string bytes, the signature for the first version does **not** automatically apply to the second. If canonicalization is used, both signer and verifier must agree on an explicit specification.

When signing a request, consider including in scope:

- Version and message type to prevent protocol/algorithm confusion (*domain separation*).
- Principal/sender, intended recipient/audience, tenant/keyId/issuer where relevant.
- HTTP method, URL/path/query/meaningful headers, or business identifier.
- Body bytes or agreed canonical representation.
- Timestamp and nonce/requestId/sequence if the protocol requires expiration and replay protection.

**A valid signature can be replayed verbatim.** An attacker does not need to forge the signature: they simply capture `message + signature` and send it again. Replay defense is a separate protocol responsibility, such as storing processed nonces/requestIds scoped to principal/key, performing atomic check-and-claim, and checking signed timestamps. **Encryption** likewise does not automatically reject an old ciphertext if the recipient decrypts it a second time.

## 10. Distinguishing keys, algorithms, formats, and certificates in practice

### 10.1 Keys and algorithms must match their purpose

A `PrivateKey` object may represent Ed25519, RSA, or EC depending on `getAlgorithm()` and provider; that does not mean every `Signature`/`Cipher` accepts that key.

- **Ed25519**: primarily for signing/verifying; never use an Ed25519 public key for RSA-OAEP encryption.
- **RSA**: has signing schemes (RSA-PSS, RSA PKCS#1 v1.5 signature) and encryption schemes (RSA-OAEP). Define dedicated key types/key pairs per role.
- **X25519/ECDH**: shared-secret agreement; does not sign and does not directly output ciphertext.
- **AES-GCM**: authenticated symmetric encryption using `SecretKey` and IV/nonce; does not use `PublicKey`/`PrivateKey`.

In an application with multiple keys, map `keyId` → algorithm → purpose → identity → public-key trust. Never let a request declare an algorithm and have the system trust it unconditionally. Pin/allowlist the schemes and parameters permitted for each message type.

### 10.2 Key encoding is not encryption

A public key can be exported as **X.509 SubjectPublicKeyInfo** (`getEncoded()` with `X.509`), and a private key can be in **PKCS#8** format (`getEncoded()` with `PKCS#8`) depending on provider and exportability. These are **serialization formats**, not automatic encryption or owner verification; an unencrypted PKCS#8 file containing a private key exposes the secret. When exporting a private key, protect it appropriately, or better yet use a keystore/HSM/KMS when available.

**An X.509 digital certificate** contains a public key along with identity fields and a CA signature; a bare public key is not a valid certificate. You must validate the chain, trust anchors, key usage, and context (e.g., hostname or signer identity). A public key may match mathematically while the certificate is expired, revoked, or invalid for the intended usage.

### 10.3 Separating keys and permissions

A system can use separate key pairs for **signing requests** and **decrypting documents**. This enables:

- Revoking/rotating a signing key without affecting documents encrypted under the decryption key.
- Restricting KMS/HSM permissions: a signing service has no permission to decrypt customer data, and a decryption service has no permission to sign on behalf of the organization.
- Applying expiration, key usage, auditing, and backup/recovery policies tailored to each goal.
- Avoiding designs tied to one multipurpose key pair that a provider policy or certificate forbids.

## 11. Common misconceptions and how to fix them

| Misconception | Why it is wrong | Right mental model / practice |
| --- | --- | --- |
| “Signing with private key = encrypting data with private key” | Signing and encryption schemes differ in encoding, checks, padding, and goals | `Signature.initSign`/`initVerify` for signatures; RSA-OAEP/AEAD for encryption |
| “Having a public key proves it is Alice” | An attacker can substitute a public key | Verify key ownership via trusted cert/registry/fingerprint |
| “Bob decrypted it, so Alice must have sent it” | Anyone with `pk_B` can encrypt | Authenticate the sender separately with a signature or equivalent |
| “A signature prevents others from reading the content” | Messages are often sent in cleartext alongside the signature | Add encryption when confidentiality is required |
| “RSA-OAEP directly encrypts large files” | RSA has a strict plaintext size limit and high cost | Hybrid encryption with AES-GCM + key encapsulation/wrapping |
| “RSA-PSS is just another mode of RSA Cipher” | Signing and encryption are distinct schemes | Use `Signature` and `Cipher` with the right APIs and parameters |
| “An Ed25519 public key can be used to encrypt” | Ed25519 is a signature algorithm | Choose an appropriate encryption/KEM/HPKE mechanism and separate keys |
| “Any valid signature is a fresh request” | Replaying the exact message preserves the signature | Signed nonce/timestamp/requestId + state tracking |
| “Same JSON text always yields the same signature” | Serialization/bytes can differ | Sign exact bytes or enforce canonical form |
| “Just use `SHA256withRSA` or `RSASSA-PSS` without checking policy” | Scheme, parameters, provider, and certificate key usage must align | Pick standard, make params explicit, and test end-to-end |
| “Use RSA/NoPadding to learn and ship to production” | Raw RSA lacks safe security padding | Use standardized OAEP/PSS and tested libraries |
| “Since TLS is used, message signatures are never needed” | TLS protects the session channel; some systems require multi-hop auditing/delegation | Analyze the threat model and bind signatures to operations when needed |

## 12. Self-check prompts

1. **Two key pairs:** Alice signs a file for Bob to verify. State which key is used for `sign()` and which for `verify()`. If Carol has Alice's public key, can Carol read the original file sent with the signature? Can Carol create a new valid signature?
2. **Encryption:** Alice wants Bob to be the only one able to read a message. Whose public key does Alice use? Whose private key does Bob use? If Carol has Bob's public key, can Carol send her own ciphertext that Bob decrypts?
3. **Modeling:** Explain why `Sign(sk_A, m)` and `Encrypt(pk_B, m)` cannot be collapsed into “one reversible encryption operation” even though both belong to asymmetric cryptography.
4. **Java lab:** Run `SignVsEncryptDemo.java` with `--release 21` and explain all four stdout lines. Change `altered` to equal `message` and explain why `verify` will return `true`.
5. **RSA:** Run `RsaPssSignatureDemo.java`, identify what `PSSParameterSpec` does, and explain why `OAEPParameterSpec` is not a parameter for PSS signatures.
6. **Large payloads:** Calculate the maximum plaintext size for 3072-bit RSA-OAEP with SHA-256 (answer: 318 bytes). Sketch a hybrid encryption flow to send a 10 MB file without encrypting the entire file directly with RSA.
7. **Public-key substitution:** Diagram a scenario where an attacker swaps Alice's public key on Bob's side and signs forged data. Explain how PKI or an out-of-band fingerprint blocks this attack.
8. **Application design:** A payment API requires hidden contents, proof of who issued the command, and no double-charging. Name the mechanism needed for each property: confidentiality, signature/authentication, anti-replay, and idempotency.
9. **Code review:** You spot `Cipher.getInstance("RSA/ECB/NoPadding")` and `cipher.init(ENCRYPT_MODE, privateKey)` being used to “sign.” Explain the issues and replace it with `Signature` using a standard signing scheme.
10. **Trust & lifecycle:** Distinguish “signature verify returns true” from “the trusted organization genuinely signed this” when a certificate is expired, a key is revoked, or the public key is unauthenticated.

You have mastered this lesson when you can immediately answer three questions: **(1) Does the data need confidentiality or authentication? (2) Does this public key belong to the signer or the recipient? (3) Which Java API and cryptographic scheme fit that goal?**

## Official references

- [Java SE 21 — `java.security.Signature`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Signature.html): `initSign`, `initVerify`, `update`, `sign`, and `verify`.
- [Java SE 21 — `javax.crypto.Cipher`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html): `ENCRYPT_MODE`, `DECRYPT_MODE`, transformations, and `doFinal`.
- [Java SE 21 — `OAEPParameterSpec`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/OAEPParameterSpec.html): OAEP, MGF, PSource.
- [Java SE 21 — `PSSParameterSpec`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/spec/PSSParameterSpec.html): RSASSA-PSS parameters.
- [Java SE 21 — Standard Algorithm Names](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html): Ed25519, RSASSA-PSS, and RSA transformation names.
- [Java 21 — JDK Providers Documentation](https://docs.oracle.com/en/java/javase/21/security/oracle-providers.html): SunEC/SunRsaSign/SunJCE support scope.
- [RFC 8017 — PKCS #1 v2.2](https://www.rfc-editor.org/rfc/rfc8017): distinguishing RSAES-OAEP and RSASSA-PSS, conditions, and message lengths.
- [RFC 8032 — Edwards-Curve Digital Signature Algorithm](https://www.rfc-editor.org/rfc/rfc8032): Ed25519 and Ed448.
- [NIST CSRC — Digital Signature](https://csrc.nist.gov/glossary/term/digital_signature): concept, authentication/integrity goals, and confidentiality limitations.
