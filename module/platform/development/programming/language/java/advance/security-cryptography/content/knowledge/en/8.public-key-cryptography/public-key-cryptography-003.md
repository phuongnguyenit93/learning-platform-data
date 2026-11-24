# 8.3 RSA, EC, EdDSA, and XDH: Distinguishing the Purpose of Each Algorithm Family

## Objectives

After this lesson, you will distinguish **public-key encryption**, **digital signatures**, and **key agreement**; know what RSA, EC, EdDSA, and XDH provide; select the right Java Cryptography Architecture (JCA/JCE) engine such as `Cipher`, `Signature`, and `KeyAgreement`; use the right algorithm/curve names in Java 17+; and understand why you must never arbitrarily substitute keys or outputs from one family for another.

These four names are **not at the same level of abstraction**: `RSA` is an algorithm family used for encryption or signatures depending on the scheme; `EC` is the general name for the **classical elliptic-curve key type** used in ECDSA/ECDH; `EdDSA` is a **digital signature family**; and `XDH` is a **Diffie–Hellman key agreement family** using Montgomery curves. Confusing them causes many `NoSuchAlgorithmException`, `InvalidKeyException` errors and protocol designs missing authentication steps.

## 1. First: The Three Tasks of Public-Key Cryptography

Asymmetric cryptosystems use a **public key** (distributable) and a **private key** (must be protected). Although all three use key pairs, the following three operations are completely different:

| Purpose | Operation | Input keys / values | Output | Guarantees designed to provide |
| --- | --- | --- | --- | --- |
| **Public-key encryption** | Sender encrypts with recipient's public key; recipient decrypts with private key | Corresponding public/private key, plaintext | Ciphertext | Only the holder of the right private key can read; requires a secure encryption scheme |
| **Digital signature** | Signer uses private key to create signature; any party trusting the public key can verify | Private/public key, message | Signature bytes and verification result | Integrity and authentication of the holder of the private key |
| **Key agreement** | Both parties use their own private key and the peer's public key to compute a shared secret | Two appropriately generated key pairs | Both parties derive the same shared secret | Foundation for deriving session keys; **does not by itself authenticate identity or encrypt data** |

`Signature` is not "encrypting data with a private key"; conversely, RSA-OAEP is not a signature. `KeyAgreement` has no "sign" API and does not turn a message into ciphertext. A public key only has security value when **it is properly bound to the peer's identity** (certificate, pinning, trust store, handshake signature, or an appropriate authenticated channel).

### Quick Selection Table: RSA, EC, EdDSA, XDH

| Family / name | Typical role | Java engine | Common Java names | Do not misconstrue as |
| --- | --- | --- | --- | --- |
| **RSA** | Key/small-data encryption via **RSA-OAEP**; signatures via **RSA-PSS** | `Cipher`, `Signature` | `RSA` for `KeyPairGenerator`; `RSA/ECB/OAEPPadding`; `RSASSA-PSS` | "RSA" by default only means encryption, or signature is decryption |
| **EC** | **ECDSA** (signatures) and **ECDH** (key agreement) on appropriate EC curves | `Signature`, `KeyAgreement` | `EC`, `SHA256withECDSA`, `ECDH`, `secp256r1` | One algorithm named `EC` doing everything |
| **EdDSA** | Modern digital signatures | `Signature` | `Ed25519`, `Ed448`; general form `EdDSA` | Encryption key or `KeyAgreement` key |
| **XDH** | Modern DH key agreement | `KeyAgreement` | `X25519`, `X448`; general form `XDH` | Signature algorithm or `Cipher` encryption function |

The names in the table belong to different engines: `KeyPairGenerator.getInstance("EC")` generates keys, `Signature.getInstance("SHA256withECDSA")` uses an EC key to sign, and `KeyAgreement.getInstance("ECDH")` uses EC keys for key agreement. Java has no single `getInstance("EC")` call for all operations.

## 2. RSA: One Family Used for Both Encryption and Signatures

### 2.1 RSA-OAEP: Encrypting for the Private-Key Holder

RSA publishes a modulus `n` and a public exponent `e`; the private key holds the required secret parameters. Primitive RSA operations are not secure enough when used directly. When **encrypting with RSA** in modern applications, choose a scheme with secure padding such as **RSAES-OAEP** and use it only to encrypt **small payloads or session keys**, then encrypt large data with an AEAD cipher such as AES-GCM.

Example Java naming pair:

```java
Cipher cipher = Cipher.getInstance("RSA/ECB/OAEPPadding");
OAEPParameterSpec params = new OAEPParameterSpec(
        "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
        PSource.PSpecified.DEFAULT);
cipher.init(Cipher.ENCRYPT_MODE, recipientPublicKey, params);
byte[] ciphertext = cipher.doFinal(plaintext);
```

This is an **illustrative snippet inside a method**, not a standalone program. It assumes `recipientPublicKey` and `plaintext` exist, and exceptions from `Cipher.getInstance`/`init`/`doFinal` must be handled. In Java, the string `RSA/ECB/OAEPPadding` contains `ECB` for historical transformation syntax reasons; this is **not a recommendation to use AES ECB mode**. What matters is **OAEP** and the digest/MGF parameters.

**Avoid OAEP parameter ambiguity**: writing only `OAEPWithSHA-256AndMGF1Padding` in the transformation without controlling the MGF1 digest can cause interoperability failures across environments. Declare `OAEPParameterSpec` explicitly (in the example, main digest SHA-256 and MGF1 digest also SHA-256), and agree on the exact parameter set with the recipient.

RSA-OAEP limits the number of plaintext bytes: with a `k`-byte modulus and an `hLen`-byte digest, the limit is **`k - 2*hLen - 2`**. 2048-bit RSA with SHA-256 gives `k=256` and `hLen=32`, so at most **190 bytes** per OAEP operation. **Do not** split a file into multiple chunks and encrypt each chunk with RSA. Instead, generate a random AES key, encrypt the data with AES-GCM, and use RSA-OAEP to protect the AES key inside a clearly formatted envelope.

### 2.2 RSA-PSS: Digital Signatures

To sign, use the `Signature` engine with the **RSASSA-PSS** scheme and explicitly declared parameters. For example, using SHA-256 hash, MGF1 with SHA-256, 32-byte salt, and trailer field 1:

```java
PSSParameterSpec pss = new PSSParameterSpec(
        "SHA-256", "MGF1", MGF1ParameterSpec.SHA256, 32, 1);
Signature signer = Signature.getInstance("RSASSA-PSS");
signer.setParameter(pss);
signer.initSign(privateSigningKey);
signer.update(message);
byte[] signature = signer.sign();
```

This is also only a **snippet**: you must provide a signing private key, message bytes, relevant imports, and exception handling. On the verification side, use `initVerify(publicSigningKey)`, the same PSS parameter set, and `verify(signature)`. If the digest, MGF1 digest, salt length, or scheme disagrees, verification can fail.

`SHA256withRSA` is the name for RSA signatures with the **PKCS#1 v1.5** scheme, which differs from **`RSASSA-PSS`**. You may still need to verify legacy signatures for compatibility, but for new designs where both sides support it, RSA-PSS is generally preferred. **Do not** use `Cipher.DECRYPT_MODE` to "verify an RSA signature" or `Cipher.ENCRYPT_MODE` with a private key in place of `Signature`.

RSA is **not** a `KeyAgreement`/Diffie–Hellman mechanism. In modern security architectures, RSA is typically used for authentication/signatures or key transport per an appropriate protocol; key agreement with forward secrecy is handled by DH mechanisms instead.

### 2.3 Key Size and Purpose Separation

A **2048-bit** RSA modulus is commonly seen as a baseline minimum in many existing systems; actual requirements may be higher depending on data lifetime and policy. Modulus length, hash algorithm, padding scheme, key-generation entropy, and provider capabilities all matter. In production, use **different RSA key pairs** for **encryption** and **signing** if the system requires both, so policies, access permissions, and key lifecycles stay clearly separated.

## 3. EC: Elliptic Curve Key Type, Used for ECDSA or ECDH

`EC` in `KeyPairGenerator.getInstance("EC")` denotes generating a key on an **elliptic curve**. You must specify an appropriate **named curve**, for example:

```java
KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
generator.initialize(new ECGenParameterSpec("secp256r1"));
KeyPair pair = generator.generateKeyPair();
```

This is a snippet; import `java.security.KeyPairGenerator`, `java.security.KeyPair`, and `java.security.spec.ECGenParameterSpec`. `secp256r1` is also commonly called **NIST P-256**; `secp384r1` corresponds to P-384. Providers can differ in the set of curves they support; do not assume every arbitrary curve is available.

### 3.1 ECDSA: Signing with EC Keys

With an EC key pair on P-256, a common choice is:

```java
Signature signature = Signature.getInstance("SHA256withECDSA");
signature.initSign(signingPrivateKey);
signature.update(message);
byte[] signed = signature.sign();
```

The name `SHA256withECDSA` describes **ECDSA** with **SHA-256** digest. An ECDSA signature has mathematical components `r` and `s`; the byte format exchanged between systems must be agreed upon. Standard Java `SHA256withECDSA` returns an ASN.1 DER signature; some protocols such as JOSE require **P1363 raw r||s** and cannot use DER bytes directly without proper conversion. Java also provides names like `SHA256withECDSAinP1363Format` when supported by the provider.

ECDSA depends critically on the correctness of the **per-signature secret nonce**. Repeated or biased nonces can leak the private key. Let the JCA provider handle the signing mechanism and randomness source; **never implement ECDSA formulas by hand** or reuse nonce values.

### 3.2 ECDH: Agreeing on a Shared Secret with EC Keys

Using the same `EC` key type but with a different engine:

```java
KeyAgreement agreement = KeyAgreement.getInstance("ECDH");
agreement.init(alicePrivateKey);
agreement.doPhase(bobPublicKey, true);
byte[] sharedSecret = agreement.generateSecret();
```

This is a snippet; it requires key variables of the right type/curve and importing `javax.crypto.KeyAgreement`. Bob's side computes the value using `bobPrivateKey` and `alicePublicKey`: both sides obtain the **same shared secret** if the keys and parameters are compatible.

**ECDH does not create signatures, does not encrypt data, and does not by itself authenticate the peer's identity.** If an attacker substitutes a public key during exchange, they can mount a man-in-the-middle attack. You must authenticate the public key (certificate, protocol signature, pinned key, or trusted identity system). **Do not** pass raw ECDH output directly into `SecretKeySpec("AES")` without a key derivation mechanism and context binding; use **HKDF** or an appropriate KDF to derive session keys.

Using one EC key pair to illustrate both engines in a lesson is possible at the API level, but production should **separate signing keys and key-agreement keys** by purpose, especially when policies/certificates distinguish `digitalSignature` and `keyAgreement`.

## 4. EdDSA: Dedicated to Digital Signatures

**EdDSA (Edwards-curve Digital Signature Algorithm)** is a digital signature family; notable variants are:

- **Ed25519**: digital signature on the Edwards25519 curve, popular for application signatures, identity keys, and configuration attestation.
- **Ed448**: another option with different size and security characteristics; support depends on the provider.
- Java 17 supports the general name `EdDSA` as well as specific names like `Ed25519` and `Ed448` in the appropriate engines. Pick the **specific** name when a protocol explicitly specifies the variant.

Java signing/verifying usage:

```java
KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
KeyPair keys = generator.generateKeyPair();

Signature signer = Signature.getInstance("Ed25519");
signer.initSign(keys.getPrivate());
signer.update(message);
byte[] signature = signer.sign();

Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(keys.getPublic());
verifier.update(message);
boolean valid = verifier.verify(signature);
```

This is a snippet inside a method with appropriate imports/exceptions. For Ed25519, a standard signature is **64 bytes** long. A property of the standard Ed25519 variant is that signing is **deterministic** from the key and message per the algorithm; this differs from the unpredictable-nonce requirement of standard ECDSA. Nevertheless, the private key, initial randomness during key generation, and implementation controls must still be strictly protected.

**EdDSA does not provide `Cipher` or `KeyAgreement`.** `Signature.getInstance("Ed25519")` is right; `KeyAgreement.getInstance("Ed25519")` is not a way to derive a shared secret, nor should you pass an Ed25519 public key into `KeyAgreement.getInstance("X25519")` assuming the two key types are equivalent.

Ed25519 and X25519 both relate to Curve25519 in different representations/mathematics, yet they have **different purposes, algorithms, key formats, and security constraints**. Conversion formulas exist in certain protocols/specialized libraries, but they are **not portable JCA rules** and not a reason to share the same key material. Generate **Ed25519 keys for signing** and **X25519 keys for DH** independently.

## 5. XDH: Dedicated to Key Agreement

**XDH** is the DH family name with variants **X25519** and **X448**, based on RFC 7748. It is the technique for two parties to compute a shared secret from their own private key and the peer's public key:

```java
KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
KeyPair alice = generator.generateKeyPair();
KeyPair bob = generator.generateKeyPair();

KeyAgreement ka = KeyAgreement.getInstance("X25519");
ka.init(alice.getPrivate());
ka.doPhase(bob.getPublic(), true);
byte[] secretA = ka.generateSecret();
```

This is an illustrative snippet inside a method; Bob performs the corresponding step with Bob's private key + Alice's public key to obtain the same shared secret. `XDH` is also a general algorithm name whose parameters can be chosen via `NamedParameterSpec.X25519` when supported by the provider; using the explicit name `X25519` is usually simpler when specified by the protocol. X25519 produces a **32-byte** shared secret, yet **those 32 raw secret bytes are not an application AES key yet**.

### From Shared Secret to Session Key

In a sound protocol, two parties:

1. Generate two appropriate DH key pairs, e.g., **ephemeral X25519** per session.
2. Exchange public keys in an **authenticated** handshake message (certificate/Ed25519/RSA-PSS/ECDSA or an appropriate trusted mechanism). Use the peer's exact public key and validate key format and parameters.
3. Compute the raw secret with `KeyAgreement`; if the implementation rejects a weak public key or produces an invalid result, **fail closed**. RFC 7748 defines an all-zero output case for small-order inputs; many providers check and throw an exception, but applications should not assume all providers behave identically.
4. Derive keys via **HKDF** with properly formatted salt/info and session context, optionally binding the transcript, both parties' roles, and protocol version.
5. Use the derived session keys in an **AEAD** cipher such as AES-GCM/ChaCha20-Poly1305 with unique nonces, and zeroize/isolate intermediate secrets where feasible.

Note: `HKDF-Extract(secret)` and `HKDF-Expand(info, length)` here are **process descriptions**, not built-in methods of that name in the standard Java 17 API. Use a vetted HKDF library or a separately reviewed implementation; never replace a KDF by taking the first 16 bytes of the raw shared secret.

**X25519 does not by itself prove who the peer is.** If both public keys can be swapped on the wire, both parties can end up establishing shared secrets with an attacker instead of each other. Digital signatures, certificates, or handshake authentication are a mandatory separate part of the protocol.

### Forward Secrecy Is a Protocol Property, Not Just an Algorithm Name

With **ephemeral** DH where temporary keys are deleted after completion, if long-term identity keys are compromised later, past session data may remain protected under the protocol's assumptions. This depends on the complete protocol design, authentication method, transcript management, key derivation, and secret erasure; simply using `X25519` in an application **does not automatically guarantee forward secrecy**.

## 6. Runnable Java 17 Program: Demonstrating All Four Families

The program below uses **each engine for its intended purpose**. It generates separate RSA pairs for **encryption** and **signing**, separate EC keys for **ECDSA** and **ECDH**, plus an Ed25519 pair and two X25519 pairs. The code demonstrates JCA/JCE API capabilities; it does **not** build a network protocol or production key storage system.

Create the file **`KeyFamilyDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyAgreement;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;

public final class KeyFamilyDemo {
    private static final byte[] MESSAGE =
            "Java public-key roles".getBytes(StandardCharsets.UTF_8);

    public static void main(String[] args) throws Exception {
        KeyPairGenerator rsaGenerator = KeyPairGenerator.getInstance("RSA");
        rsaGenerator.initialize(2048);
        KeyPair rsaEncryption = rsaGenerator.generateKeyPair();
        KeyPair rsaSigning = rsaGenerator.generateKeyPair();

        OAEPParameterSpec oaep = new OAEPParameterSpec(
                "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
                PSource.PSpecified.DEFAULT);
        Cipher rsaEncrypt = Cipher.getInstance("RSA/ECB/OAEPPadding");
        rsaEncrypt.init(Cipher.ENCRYPT_MODE, rsaEncryption.getPublic(), oaep);
        byte[] wrappedMessage = rsaEncrypt.doFinal(MESSAGE);
        Cipher rsaDecrypt = Cipher.getInstance("RSA/ECB/OAEPPadding");
        rsaDecrypt.init(Cipher.DECRYPT_MODE, rsaEncryption.getPrivate(), oaep);
        System.out.println("RSA-OAEP decrypt: "
                + Arrays.equals(MESSAGE, rsaDecrypt.doFinal(wrappedMessage)));

        PSSParameterSpec pssParams = new PSSParameterSpec(
                "SHA-256", "MGF1", MGF1ParameterSpec.SHA256, 32, 1);
        System.out.println("RSA-PSS verify: "
                + signAndVerify("RSASSA-PSS", rsaSigning, pssParams));

        KeyPairGenerator ecGenerator = KeyPairGenerator.getInstance("EC");
        ecGenerator.initialize(new ECGenParameterSpec("secp256r1"));
        KeyPair ecSigning = ecGenerator.generateKeyPair();
        KeyPair ecAlice = ecGenerator.generateKeyPair();
        KeyPair ecBob = ecGenerator.generateKeyPair();
        System.out.println("ECDSA verify: "
                + signAndVerify("SHA256withECDSA", ecSigning, null));
        System.out.println("ECDH shared secret matches: "
                + sameSecret("ECDH", ecAlice, ecBob));

        KeyPairGenerator edGenerator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair edSigning = edGenerator.generateKeyPair();
        System.out.println("Ed25519 verify: "
                + signAndVerify("Ed25519", edSigning, null));

        KeyPairGenerator xGenerator = KeyPairGenerator.getInstance("X25519");
        KeyPair xAlice = xGenerator.generateKeyPair();
        KeyPair xBob = xGenerator.generateKeyPair();
        System.out.println("X25519 shared secret matches: "
                + sameSecret("X25519", xAlice, xBob));
    }

    private static boolean signAndVerify(
            String algorithm, KeyPair keyPair, PSSParameterSpec pss)
            throws Exception {
        Signature signer = Signature.getInstance(algorithm);
        if (pss != null) {
            signer.setParameter(pss);
        }
        signer.initSign(keyPair.getPrivate());
        signer.update(MESSAGE);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance(algorithm);
        if (pss != null) {
            verifier.setParameter(pss);
        }
        verifier.initVerify(keyPair.getPublic());
        verifier.update(MESSAGE);
        boolean original = verifier.verify(signature);

        verifier.initVerify(keyPair.getPublic());
        if (pss != null) {
            verifier.setParameter(pss);
        }
        verifier.update("modified".getBytes(StandardCharsets.UTF_8));
        boolean modified = verifier.verify(signature);
        return original && !modified;
    }

    private static boolean sameSecret(
            String algorithm, KeyPair alice, KeyPair bob) throws Exception {
        KeyAgreement agreementA = KeyAgreement.getInstance(algorithm);
        agreementA.init(alice.getPrivate());
        agreementA.doPhase(bob.getPublic(), true);
        byte[] a = agreementA.generateSecret();

        KeyAgreement agreementB = KeyAgreement.getInstance(algorithm);
        agreementB.init(bob.getPrivate());
        agreementB.doPhase(alice.getPublic(), true);
        byte[] b = agreementB.generateSecret();

        boolean same = MessageDigest.isEqual(a, b);
        Arrays.fill(a, (byte) 0);
        Arrays.fill(b, (byte) 0);
        return same;
    }
}
```

Compile and run:

```bash
javac --release 17 KeyFamilyDemo.java
java KeyFamilyDemo
```

Output **on a Java 17+ environment with providers supporting the requested services**:

```text
RSA-OAEP decrypt: true
RSA-PSS verify: true
ECDSA verify: true
ECDH shared secret matches: true
Ed25519 verify: true
X25519 shared secret matches: true
```

**Meaning of each line:**

- `RSA-OAEP decrypt: true`: RSA public key for encryption, paired RSA private key decrypts the **short message**. OAEP uses explicitly specified SHA-256/MGF1 SHA-256.
- `RSA-PSS verify: true`: RSA-PSS signature verifies with the public signing key; the helper also checks that this signature is **not** valid for the message `"modified"`.
- `ECDSA verify: true`: EC key on `secp256r1` creates/verifies an ECDSA-SHA256 signature; the helper also tests detecting a modified message.
- `ECDH shared secret matches: true`: Alice/Bob use their own private key and the peer's public key on the same curve type, producing matching shared secrets.
- `Ed25519 verify: true`: a dedicated Ed25519 key pair signs/verifies and tests tampering.
- `X25519 shared secret matches: true`: two X25519 pairs produce identical secrets when DH succeeds.

Random values (keys, OAEP ciphertext, RSA-PSS/ECDSA signatures, DH raw secrets) **differ across runs**; the program does not print them. The `true` lines check correctness and **do not prove that the peer's public key was authenticated or that a protocol is holistically secure**.

**Note on the code:** `sameSecret` compares the two secrets for testing, then attempts to overwrite the two local byte arrays. Java and providers may retain copies in memory that cannot be cleared by this operation. Production must derive session keys with HKDF and manage secret lifecycles appropriately; never feed raw DH output straight into AES. The RSA-OAEP demo directly encrypts a small message for clarity; large data should use hybrid encryption.

## 7. Choosing Mechanisms for Real-World Problems

| Problem | Consider | Why |
| --- | --- | --- |
| Signing configuration files, releases, or messages | Ed25519, ECDSA, or RSA-PSS per ecosystem and protocol standard | Recipients verify with public key; can manage trust chain |
| Encrypting an AES content key for a recipient with an RSA public key | RSA-OAEP + AES-GCM in a defined format | RSA protects the short key, AEAD protects large data |
| Two parties establishing a session key during a handshake | X25519 or ECDH + HKDF + public key authentication | DH agrees on a secret, HKDF derives keys, and authentication prevents MITM |
| Need to combine signing identity keys and DH session keys | Ed25519 for signatures and X25519 for DH, or RSA-PSS/ECDSA + ECDH | Pick each algorithm for its role; do not use one key type for everything |
| Using an existing EC certificate | Check key usage and supported algorithms of the certificate | An ECDSA certificate cannot by default be used for ECDH |
| TLS for web/app | Use a vetted JSSE/TLS stack | TLS manages handshake, certificates, DH, KDF, and AEAD; avoid rolling your own protocol |

**Example handshake diagram (conceptual model):**

```text
Alice creates ephemeral X25519 A             Bob creates ephemeral X25519 B
         |                                              |
         +---- public(A), context ---->                 |
         |                 <---- public(B), auth -------+
         |                                              |
 DH(privateA, publicB)                       DH(privateB, publicA)
         |                                              |
         +---- same raw DH secret when valid -----------+
         |                                              |
 HKDF(secret, transcript, roles)              HKDF(secret, transcript, roles)
         |                                              |
       AEAD session keys, protocol-defined nonces + auth checks
```

The diagram intentionally omits details of TLS/HPKE. What **must not be omitted** in a real implementation is how ephemeral public keys and transcripts are **authenticated**, preventing downgrade/replay, restricting algorithms, validating inputs, and deriving separate keys/nonces per send/receive direction.

## 8. Easily Confused JCA Names and Key Formats

### Engines and Algorithm Names

| Java API | Suggested names | What it does |
| --- | --- | --- |
| `KeyPairGenerator.getInstance(...)` | `RSA`, `EC`, `Ed25519`, `X25519` | Generates the right type of key pair |
| `Cipher.getInstance(...)` | `RSA/ECB/OAEPPadding` | RSA-OAEP encryption/decryption of small inputs |
| `Signature.getInstance(...)` | `RSASSA-PSS`, `SHA256withECDSA`, `Ed25519` | Signing/verifying |
| `KeyAgreement.getInstance(...)` | `ECDH`, `X25519` | Raw secret agreement |
| `KeyFactory.getInstance(...)` | `RSA`, `EC`, `Ed25519`, `X25519` | Reconstructs key objects from matching encoding/spec |

`getInstance` creates an engine by **service type + algorithm name**, selecting from current providers; whether a provider offers a specific service must be tested on the target deployment environment. `Security.getAlgorithms("Signature")` and `Security.getAlgorithms("KeyAgreement")` help discover registered names, but are not sufficient to prove that a system's **key/curve/params** are accepted.

### X.509 and PKCS#8 Are Not Signature Algorithm Names

A public key exported as SubjectPublicKeyInfo is usually handled with `X509EncodedKeySpec`; a `PrivateKeyInfo` private key usually uses `PKCS8EncodedKeySpec`. Here, **X.509** and **PKCS#8** are *key data formats*, whereas **RSA**, **EC**, **Ed25519**, and **X25519** are *algorithms/key types*. PEM strings with `-----BEGIN PUBLIC KEY-----` or `-----BEGIN PRIVATE KEY-----` lines typically wrap Base64 around DER; you must decode, validate the format, and then use `KeyFactory` with the matching algorithm type.

Do not confuse `X509EncodedKeySpec` with an **X.509 certificate**: a public-key object holds the key, whereas a certificate also contains identity, issuer, validity period, and an attesting signature. Importing a public key from a file does not make it a trusted identity.

Do not call `getEncoded()` on an HSM/keystore key and log it: many hardware/keystore-protected private keys cannot be exported (`getEncoded()` can return `null`), which is an intended security feature. To check what a key supports, use the appropriate JCA engine and verify `KeyUsage`/policy rather than merely reading `key.getAlgorithm()`.

### Common Naming Mistakes

- `Signature.getInstance("RSA")`: to sign with RSA, choose **`RSASSA-PSS`** (with PSS parameters) or a specific signature name required by the protocol.
- `Cipher.getInstance("EC")`, `Cipher.getInstance("Ed25519")`, `Cipher.getInstance("X25519")`: not valid ways to get application encryption with those key types.
- `Signature.getInstance("X25519")`: X25519 is for DH; there is no X25519 signature.
- `KeyAgreement.getInstance("Ed25519")`: Ed25519 is for signatures; there is no DH named Ed25519.
- `Signature.getInstance("ECDH")`: ECDH is key agreement; there is no ECDH signature.
- Passing an Ed25519 key pair to `KeyAgreement("X25519")` or an X25519 pair to `Signature("Ed25519")`: wrong key type, usually throws `InvalidKeyException`.
- Comparing ECDSA signature bytes across two signing runs to conclude the algorithm is buggy: ECDSA usually uses randomness so bytes differ; use **`verify`**.
- `SHA256withRSA` and `RSASSA-PSS` are different signature schemes and cannot be swapped during verification unless metadata/protocol specifies it.

## 9. Verifying Support and Handling Errors at the Right Layer

A more meaningful check than just reading algorithm name lists is running tests with the **exact APIs, curves, and parameter sets** the application will use:

1. Create the right `KeyPairGenerator` for the algorithm and curve: RSA modulus, `ECGenParameterSpec("secp256r1")`, or `Ed25519`/`X25519`.
2. Check `getInstance` on the **right engine**: `Cipher`, `Signature`, or `KeyAgreement`.
3. Run full `init` and operations: RSA encrypt/decrypt; signature sign/verify on both valid and tampered messages; two-way ECDH/X25519 and compare shared secrets.
4. Check alignment with policy: provider/HSM, key usage, key ID, OAEP/PSS params, encoding, curve, and key access permissions.
5. Separate configuration errors from verification failures or invalid input; never silently fall back to weaker options.

| Symptom | Causes to check |
| --- | --- |
| `NoSuchAlgorithmException` | Engine/algorithm name not supported by providers (e.g., calling `Signature("X25519")`); check standard name and provider |
| `NoSuchPaddingException` from `Cipher.getInstance` | Transformation not provided; check exact OAEP padding and provider |
| `InvalidKeyException` on `initSign/initVerify/init/doPhase` | Wrong key type, wrong curve, missing HSM permission, rejected public key |
| `InvalidAlgorithmParameterException` | Curve/OAEP/PSS spec not accepted or violates policy |
| `SignatureException` or `verify == false` | Input, signature, encoding, algorithm, params, or public key mismatch; a forged signature causes the same result |
| `BadPaddingException` / `IllegalBlockSizeException` in RSA-OAEP | Corrupted ciphertext/wrong key/wrong params or input exceeds limit; do not reveal details to clients |
| ECDH/X25519 yields different secrets | Mismatched private/public peers, altered curve/format, or implementation bug; reject session |
| `KeyFactory` cannot read public/private key | Wrong X.509/PKCS#8 format, wrong algorithm OID, parameters, or provider |

**Do not expose internal details to clients that could leak keys or create an oracle.** At API boundaries, return generic error messages for invalid decryption/signatures, combined with controlled internal logging. If a protocol-mandated algorithm is unsupported by a provider, treat it as a configuration error or fail fast; never automatically switch RSA-OAEP to raw RSA, or XDH to a default key.

## 10. Key Management and Long-Term Choices

- **Separate keys by purpose**: signing keys differ from decryption keys; long-term identity keys differ from ephemeral agreement keys. Enforce proper key usage in certificates, key stores, and KMS/HSM permissions.
- **Generate keys with a cryptographic randomness source** and a trusted provider. Do not derive private keys from passwords or predictable bytes. Do not copy keys merely because they share the same length.
- **Bind public keys to identity**: a public key is not a secret, yet an attacker replacing a public key breaks the security of encryption, signatures, or DH if the origin is not verified.
- **Choose explicit schemes and parameters**: RSA-PSS needs MGF1/salt/digest, RSA-OAEP needs digest and MGF1, EC needs a named curve, XDH needs explicit X25519/X448, and EdDSA needs explicit Ed25519/Ed448.
- **Derive session keys from DH**: use a KDF and protocol context; do not arbitrarily slice the raw shared secret. Prevent replay and downgrade, authenticate transcripts, and use AEAD with unique nonces.
- **Check ecosystem constraints**: compatibility across TLS, certificates, JOSE/JWT, DER/P1363 signature formats, HSM/FIPS platforms, or peer libraries may dictate different algorithm choices.
- **Do not equate public-key/signature byte sizes with security level**: RSA-2048, P-256, Ed25519, and X25519 have very different mathematical structures and costs; follow standards/policies to choose the required security level.
- **Evaluate algorithm lifecycle**: classical RSA/ECC do not provide post-quantum security. If long-term data confidentiality or post-quantum readiness is required, consult standardized choices such as post-quantum KEMs/signatures within an appropriate protocol; do not mix keys/algorithms outside an evaluated protocol.

## 11. Practice Exercises

1. In `KeyFamilyDemo.java`, identify which lines use `Cipher`, which use `Signature`, and which use `KeyAgreement`. Why can't `X25519` directly replace `Ed25519`?
2. Replace `SHA256withECDSA` with `Ed25519` while still passing an `EC` key to `Signature.initSign`. Predict and check the exception type, then explain which key type is wrong.
3. Build a policy table: an application needs to **sign configuration files**, **agree on session keys**, **encrypt large files**, and **protect an AES content key with RSA**. For each requirement, choose the right scheme, engine, and key management approach.
4. Why can't RSA-OAEP with a 2048-bit modulus and SHA-256 arbitrarily encrypt 1 MiB of plaintext in one call? Compute the 190-byte limit using `k - 2*hLen - 2`.
5. If raw ECDH and X25519 secrets match between two parties, can you conclude they are talking to the right peer? Propose how to authenticate the transcript/public keys.
6. Add a mechanism to save and load a trusted public key using `X509EncodedKeySpec`. Distinguish a raw public key from a file from an X.509 certificate with a trust chain.
7. Test support for `RSASSA-PSS`, `Ed25519`, and `X25519` on your target JVM/provider. Record the Java version, provider, params, and test results, **without recording any private key**.

## References

- [Java SE 17 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): standard names `RSA`, `EC`, `RSASSA-PSS`, `EdDSA`, `Ed25519`, `XDH`, `X25519`, and service types.
- [Java SE 17 — JCA Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): JCA providers, `KeyPairGenerator`, `Signature`, `KeyAgreement`, and `Cipher`.
- [Java SE 17 — `Signature`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html): signing and verifying with RSA-PSS, ECDSA, EdDSA.
- [Java SE 17 — `KeyAgreement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyAgreement.html): key agreement protocol and usage of `doPhase`/`generateSecret`.
- [Java SE 17 — `OAEPParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/OAEPParameterSpec.html): OAEP and MGF1 parameters.
- [Java SE 17 — `PSSParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/PSSParameterSpec.html): digest, MGF, salt length, trailer field.
- [RFC 8017 — PKCS #1 v2.2](https://www.rfc-editor.org/rfc/rfc8017): RSAES-OAEP and RSASSA-PSS.
- [RFC 8032 — Edwards-Curve Digital Signature Algorithm](https://www.rfc-editor.org/rfc/rfc8032): Ed25519/Ed448.
- [RFC 7748 — Elliptic Curves for Security](https://www.rfc-editor.org/rfc/rfc7748): X25519/X448 and the all-zero output issue.
- [RFC 5869 — HKDF](https://www.rfc-editor.org/rfc/rfc5869): key derivation from shared secrets.
