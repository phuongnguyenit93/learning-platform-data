# 8.2 Generating Key Pairs Using KeyPairGenerator with Explicit Sizes or Parameter Sets

When generating asymmetric keys in Java, it is important not only to call `KeyPairGenerator.generateKeyPair()`, but also to **explicitly specify the algorithm, size or parameter set, and an appropriate source of randomness**. Those choices govern cryptographic strength, interoperability, speed, key format, and intended use.

This lesson focuses on the `java.security.KeyPairGenerator` engine in the Java Cryptography Architecture (JCA): how to initialize **RSA**, **EC/secp256r1**, **Ed25519**, and **X25519** with explicit parameters, inspect keys after generation, distinguish signing keys from secret-agreement keys, and handle common mistakes.

## 1. What Is `KeyPairGenerator`?

A **key pair** consists of:

- **Public key (`PublicKey`):** can be distributed to parties that need to verify signatures, encrypt according to an appropriate protocol, or participate in key exchange.
- **Private key (`PrivateKey`):** must have strictly controlled access; used to sign, decrypt, or perform key agreement depending on the algorithm.
- **`KeyPair`:** an object holding both components via `getPublic()` and `getPrivate()`.

For public-key cryptography, Java distinguishes the following engines:

| Engine / API | Responsibility | Example |
| --- | --- | --- |
| `KeyPairGenerator` | Generates **new key pairs** according to an algorithm/parameters. | `KeyPairGenerator.getInstance("RSA")`. |
| `KeyFactory` | Converts an existing key representation into a key object or vice versa. | Reading `X509EncodedKeySpec` and `PKCS8EncodedKeySpec`. |
| `Signature` | Creates/verifies signatures with an appropriate key. | `SHA256withECDSA`, `Ed25519`, `RSASSA-PSS`. |
| `KeyAgreement` | Establishes a shared secret using private/public keys and the corresponding protocol. | `X25519`. |
| `Cipher` | Encrypts/decrypts when the algorithm/mode allows. | RSA-OAEP in appropriate cases. |
| `KeyGenerator` | Generates **symmetric secret keys**, not public/private pairs. | `KeyGenerator.getInstance("AES")`. |

`KeyPairGenerator` **does not automatically create X.509 certificates, does not put keys into an HSM/KeyStore, does not verify the owner of a public key, and does not decide how keys are distributed**. Those are separate parts of a security design.

General lifecycle:

~~~text
Choose goal (signing / key exchange / protocol-appropriate encryption)
          |
          v
Choose algorithm + security strength + explicit parameters
          |
          v
KeyPairGenerator.getInstance(algorithm)
          |
          v
initialize(keysize, SecureRandom)
     or
initialize(AlgorithmParameterSpec, SecureRandom)
          |
          v
generateKeyPair() -> KeyPair
          |
          +--> PublicKey  -> publish over an identity-verified channel
          |
          +--> PrivateKey -> manage, store, and control access securely
~~~

## 2. Essential API: Three Ways to Initialize

~~~java
KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");

// Option A — specify size explicitly:
generator.initialize(3072, new SecureRandom());

// Option B — specify algorithm-specific parameter set:
generator.initialize(
    new RSAKeyGenParameterSpec(3072, RSAKeyGenParameterSpec.F4),
    new SecureRandom());

// After choosing one initialization approach:
KeyPair pair = generator.generateKeyPair();
~~~

This is an **API illustration snippet**; complete runnable code is presented in later sections. In a real program, choose **one appropriate initialization policy**; there is no need to call both Option A and Option B on the same generator.

Important overloads:

| Method | Meaning |
| --- | --- |
| `KeyPairGenerator.getInstance("RSA")` | Locates a `KeyPairGenerator` service for RSA from suitable JCA providers. |
| `getInstance("RSA", "ProviderName")` | Specifies a provider by name, requiring a registered provider. |
| `getInstance("RSA", providerObject)` | Specifies a provider object directly; can work even when the object is not registered. |
| `initialize(int keysize)` | Sets the size **according to the algorithm's own semantics**; randomness source is chosen by JCA per policy. |
| `initialize(int keysize, SecureRandom rng)` | Sets the size and the provided randomness source. Other parameters, if needed, may be decided by the provider. |
| `initialize(AlgorithmParameterSpec params)` | Initializes with a specific **parameter set**; JCA supplies a default randomness source. |
| `initialize(AlgorithmParameterSpec params, SecureRandom rng)` | Explicitly specifies both parameters and randomness source. |
| `generateKeyPair()` | Generates a new pair; calling it again can generate another new pair using the current state/configuration. |
| `getProvider()` | Returns the generator's provider, useful for verifying the deployment environment. |

Two core notes:

1. **Omitting `initialize`:** `generateKeyPair()` may still work because providers must supply a default configuration. However, defaults **can differ across providers and JDK versions**, so you should not rely on them when you want to guarantee key sizes or parameter sets.
2. **Calling only `initialize(256)`:** the number `256` is an algorithm-dependent metric and **does not mean every engine chooses the same curve, strength, or usage**. With EC, to use `secp256r1` specifically, pass the curve name.

`SecureRandom` is the API for generating unpredictable bytes for cryptography. `new SecureRandom()` is a common choice in examples; do not seed from time/`Random`/PID to make key generation "reproducible". Production keys require a randomness source and operational policy evaluated on the running platform.

## 3. Choosing Algorithms and Parameter Sets Based on Purpose

| Purpose | `getInstance(...)` for KPG | Parameter set to declare | Example engine using the key |
| --- | --- | --- | --- |
| RSA key for signing/appropriate applications | `"RSA"` | `RSAKeyGenParameterSpec(3072, F4)`, or an explicit size if exponent customization is not needed | `Signature`: `RSASSA-PSS` or protocol-specified method |
| ECDSA signature on a specific NIST curve | `"EC"` | `ECGenParameterSpec("secp256r1")` | `Signature.getInstance("SHA256withECDSA")` |
| EdDSA (Ed25519) signature | `"Ed25519"` | `NamedParameterSpec.ED25519` when stating parameters explicitly | `Signature.getInstance("Ed25519")` |
| Modern X25519 key agreement | `"X25519"` | `NamedParameterSpec.X25519` | `KeyAgreement.getInstance("X25519")` |

**Do not compare bit counts directly across algorithms**: 3072-bit RSA, ECDSA P-256, and Ed25519 do not share the same format or meaning of "key length". Their estimated security strength must be based on security standards and protocol suitability, not simply comparing 3072 to 256.

In Java, whether an algorithm or curve is supported also depends on **the JDK, provider, policy, and hardware environment**. If an application requires portability, test on the target deployment environment and log the provider actually selected. Algorithm names in the examples are standard/commonly supported API names in JDK 17; do not assume every provider supports all of them.

### Distinguishing Key Types by Capability

- An **RSA key** can suit signing, encryption, or certain legacy protocols, but must use a **standard transformation/scheme** and sensible policy; do not "encrypt with a private key" in place of signing.
- An **EC key** generated by `KeyPairGenerator.getInstance("EC")` with `secp256r1` works with ECDSA; do not assume every EC key of any curve is interchangeable with X25519.
- **Ed25519** is for **digital signatures**, not ECDH/X25519.
- **X25519** is for **key agreement**, not signatures. The raw shared secret from `KeyAgreement` normally must still pass through a **KDF and an authenticated protocol** before becoming application keys; X25519 alone does not authenticate the peer's identity.

## 4. Generating RSA Keys with Explicit Size and Public Exponent

### 4.1. Two Levels of Specification

Simple approach:

~~~java
KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
generator.initialize(3072, new SecureRandom());
KeyPair pair = generator.generateKeyPair();
~~~

Stricter approach when specifying the **public exponent**:

~~~java
KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
generator.initialize(
    new RSAKeyGenParameterSpec(3072, RSAKeyGenParameterSpec.F4),
    new SecureRandom());
KeyPair pair = generator.generateKeyPair();
~~~

The snippets above are illustrative, not standalone Java files.

- `3072` is the RSA **modulus size** measured in **bits**. RSA-2048 still appears in current systems, while RSA-3072 provides greater security margin at the cost of higher CPU usage and larger keys/signatures. The chosen bit count must align with security lifetime, standards requirements, and compatibility.
- `RSAKeyGenParameterSpec.F4` corresponds to **65537**, the standard public exponent. Do not pick an unusual or very small public exponent thinking it "runs faster".
- `RSAKeyGenParameterSpec` is not a private key object; it only declares **key-generation input parameters**.
- **Modulus size is not the size of a PKCS#8-encoded private key** and not the signature length of every scheme (RSA signatures typically equal the modulus length in standard formats).
- `generateKeyPair()` uses randomness to produce the secret components; **never blindly reuse a private key across incompatible tasks or protocols**.

### 4.2. Java 17+ Program: RSA-3072 and Key Pair Verification

File **`RsaParamsDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.RSAKeyGenParameterSpec;

public class RsaParamsDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        RSAKeyGenParameterSpec parameters =
                new RSAKeyGenParameterSpec(3072, RSAKeyGenParameterSpec.F4);
        generator.initialize(parameters, new SecureRandom());
        KeyPair pair = generator.generateKeyPair();

        RSAPublicKey publicKey = (RSAPublicKey) pair.getPublic();
        System.out.println("Algorithm: " + publicKey.getAlgorithm());
        System.out.println("Modulus bits: "
                + publicKey.getModulus().bitLength());
        System.out.println("Public exponent: "
                + publicKey.getPublicExponent());

        byte[] message = "module".getBytes(StandardCharsets.UTF_8);
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(pair.getPublic());
        verifier.update(message);
        System.out.println("Signature verifies: "
                + verifier.verify(signature));
    }
}
~~~

Run in the directory containing the file:

~~~bash
javac RsaParamsDemo.java
java RsaParamsDemo
~~~

Verified output:

~~~text
Algorithm: RSA
Modulus bits: 3072
Public exponent: 65537
Signature verifies: true
~~~

The result proves the key pair was generated with a 3072-bit modulus, public exponent F4, and compatible private/public components for signing/verifying in the example. It **does not prove the private key has been stored securely**, does not create a certificate, and is not a comprehensive test of a PKI system.

`SHA256withRSA` here serves quick example verification and compatibility. For new RSA signature designs, consider **RSASSA-PSS with an explicit `PSSParameterSpec`** as defined by the chosen protocol; do not unilaterally change schemes when interoperating with systems that mandate another algorithm.

If the protocol requires **RSA-OAEP** to wrap a small key, that is the responsibility of `Cipher` with an explicit transformation/`OAEPParameterSpec`, **not the job of `KeyPairGenerator`**. For large data, design hybrid encryption using an appropriate symmetric key/AEAD rather than using RSA to encrypt the entire plaintext.

## 5. Generating EC Keys: Choose the Curve by Name, Not Just by the Number 256

### 5.1. Why Doesn't `initialize(256)` Say Everything About the Configuration?

With `KeyPairGenerator.getInstance("EC")`, calling `initialize(256)` gives a size metric, but the provider decides how to map it to a parameter set. For protocols that mandate **the NIST P-256 curve**, specify it directly:

~~~java
KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
generator.initialize(
    new ECGenParameterSpec("secp256r1"), new SecureRandom());
KeyPair pair = generator.generateKeyPair();
~~~

`"secp256r1"` is the standard name for the **NIST P-256** curve; do not assume aliases such as `prime256v1` are accepted by every provider. If another curve is required (such as `secp384r1`), verify support and match the protocol. Never take an EC object on curve A and use it with a peer expecting curve B.

`ECGenParameterSpec` is a curve-name-based parameter spec, not a container for a public key point or private key scalar. Once generated, `ECPublicKey` lets you inspect the curve parameters. A **256-bit field size** is only an indicator and is not enough to prove the right curve name without checking detailed parameters/protocol; the program sets the curve name explicitly from the start.

### 5.2. Java 17+ Program: EC/secp256r1 and ECDSA

File **`EcCurveDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.interfaces.ECPublicKey;
import java.security.spec.ECGenParameterSpec;

public class EcCurveDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(
                new ECGenParameterSpec("secp256r1"),
                new SecureRandom());
        KeyPair pair = generator.generateKeyPair();

        ECPublicKey publicKey = (ECPublicKey) pair.getPublic();
        System.out.println("Algorithm: " + publicKey.getAlgorithm());
        System.out.println("Field bits: "
                + publicKey.getParams().getCurve()
                        .getField().getFieldSize());

        byte[] message = "module".getBytes(StandardCharsets.UTF_8);
        Signature signer = Signature.getInstance("SHA256withECDSA");
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("SHA256withECDSA");
        verifier.initVerify(pair.getPublic());
        verifier.update(message);
        System.out.println("Signature verifies: "
                + verifier.verify(signature));
    }
}
~~~

~~~bash
javac EcCurveDemo.java
java EcCurveDemo
~~~

Stdout:

~~~text
Algorithm: EC
Field bits: 256
Signature verifies: true
~~~

`Signature` uses the private key to sign and the public key to verify; `KeyPairGenerator` only generates the two keys. ECDSA signatures contain randomness or an internal nonce depending on the implementation, so **do not print or assume fixed signature bytes**. Use the standard signature API; do not implement signature nonces by hand.

Note that a provider's curve support can affect compatibility with HSM/FIPS environments. If an environment does not support `secp256r1`, do not automatically pick an arbitrary curve just to "make it run"; decide based on security requirements and peer compatibility.

## 6. Ed25519 and X25519: `NamedParameterSpec` Instead of Ambiguous Bit Counts

For specifically named algorithms, Java 17 provides `java.security.spec.NamedParameterSpec`, including the constants:

- `NamedParameterSpec.ED25519` — **Ed25519** parameter set, used for signatures.
- `NamedParameterSpec.X25519` — **X25519** parameter set, used for key exchange.
- Other constants such as `ED448` and `X448` are defined, but should only be used when supported by the provider/protocol.

Example:

~~~java
KeyPairGenerator ed = KeyPairGenerator.getInstance("Ed25519");
ed.initialize(NamedParameterSpec.ED25519, new SecureRandom());
KeyPair signingKeys = ed.generateKeyPair();

KeyPairGenerator x = KeyPairGenerator.getInstance("X25519");
x.initialize(NamedParameterSpec.X25519, new SecureRandom());
KeyPair agreementKeys = x.generateKeyPair();
~~~

The snippet above is an API illustration, not a full program. When the algorithm already has a specific name such as `"Ed25519"` or `"X25519"`, the provider may have an appropriate default if `initialize` is not called; here we **specify the parameter explicitly** to express the intended requirement and test whether the provider supports it.

**Avoid `initialize(255)`** under the assumption that 255 is an arbitrary size analogous to RSA `initialize(3072)`. Ed25519 and X25519 define their structure via named parameter sets; requesting by bit count is not a portable contract across providers.

### Java 17+ Program: Ed25519 Signing and X25519 Key Agreement

File **`NamedKeysDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.spec.NamedParameterSpec;
import java.util.Arrays;
import javax.crypto.KeyAgreement;

public class NamedKeysDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator ed =
                KeyPairGenerator.getInstance("Ed25519");
        ed.initialize(NamedParameterSpec.ED25519, new SecureRandom());
        KeyPair signingPair = ed.generateKeyPair();

        byte[] data = "module".getBytes(StandardCharsets.UTF_8);
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(signingPair.getPrivate());
        signer.update(data);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(signingPair.getPublic());
        verifier.update(data);
        System.out.println("Ed25519 signature verifies: "
                + verifier.verify(signature));

        KeyPairGenerator x = KeyPairGenerator.getInstance("X25519");
        x.initialize(NamedParameterSpec.X25519, new SecureRandom());
        KeyPair a = x.generateKeyPair();
        KeyPair b = x.generateKeyPair();

        KeyAgreement sideA = KeyAgreement.getInstance("X25519");
        sideA.init(a.getPrivate());
        sideA.doPhase(b.getPublic(), true);
        byte[] secretA = sideA.generateSecret();

        KeyAgreement sideB = KeyAgreement.getInstance("X25519");
        sideB.init(b.getPrivate());
        sideB.doPhase(a.getPublic(), true);
        byte[] secretB = sideB.generateSecret();

        System.out.println("X25519 secrets equal: "
                + Arrays.equals(secretA, secretB));
        System.out.println("X25519 raw secret bytes: "
                + secretA.length);

        Arrays.fill(secretA, (byte) 0);
        Arrays.fill(secretB, (byte) 0);
    }
}
~~~

~~~bash
javac NamedKeysDemo.java
java NamedKeysDemo
~~~

Stdout:

~~~text
Ed25519 signature verifies: true
X25519 secrets equal: true
X25519 raw secret bytes: 32
~~~

Both X25519 sides arrive at the same **raw shared secret** by using their own private key and the other side's public key. **Do not use `secretA` directly as an AES key or session key in a custom protocol**; real systems require a KDF, transcript/context binding, peer authentication, and MITM protection according to a vetted protocol. This demo does not authenticate party A or B's identity and does not include a full handshake such as TLS.

## 7. Verifying That Parameters Were Applied

Several properties should be checked after `generateKeyPair()`:

| Key type | API check | What it proves |
| --- | --- | --- |
| RSA | `RSAPublicKey.getModulus().bitLength()` | Actual modulus length matches policy (e.g., 3072 bits). |
| RSA | `RSAPublicKey.getPublicExponent()` | Actual exponent matches `RSAKeyGenParameterSpec.F4` (65537). |
| EC | `ECPublicKey.getParams()` | Actual curve parameter set matches the desired curve/protocol; field size is only a preliminary check. |
| Ed25519 | Key algorithm + sign/verify operation `Signature("Ed25519")` | Key serves signing via the right mechanism. |
| X25519 | Two-party agreement via `KeyAgreement("X25519")` | Two key pairs can derive the same secret per the protocol. |
| All types | `generator.getProvider().getName()` | Provider chosen by JCA, useful for environment and policy checks. |

**Do not treat a sign/verify test on one message as a complete key security audit.** It only verifies functional compatibility. A system also needs sound entropy sources, proper private key handling, public key identity management, and a rotation lifecycle.

### Distinguishing Bit Size and Security Level

- RSA `3072` is the **bit length of the modulus**, not equivalent to "3072-bit security".
- EC `secp256r1` has a ~256-bit field; its estimated security strength is lower than 256 bits due to the nature of the discrete logarithm problem.
- Ed25519 has its own parameter set and does not turn into "RSA-255" or "ECDSA with default curve".
- X25519 belongs to the key-exchange family; directly comparing its shared secret length with RSA modulus bit counts does not help select the right algorithm.

To protect a long-lived system, refer to organizational policy, accepted standards, and peer compatibility. **Do not assume RSA is stronger than EC simply because 3072 is greater than 256.**

## 8. When Should You Pass `SecureRandom`?

Two common forms:

~~~java
// Use the randomness source chosen by JCA:
generator.initialize(3072);

// Pass an explicit CSPRNG source:
generator.initialize(3072, new SecureRandom());
~~~

If entropy source selection needs to be audited, passing a `SecureRandom` object can make the policy more explicit. However, **passing `new SecureRandom()` does not by itself guarantee the entire platform is FIPS-compliant or hardware-backed**; if specific compliance is required, you must configure and verify the allowed provider/mechanism.

Do not do any of the following:

- Use `java.util.Random` or `Math.random()` to generate a private exponent/seed and assemble keys manually.
- Call `random.setSeed(System.currentTimeMillis())` thinking it increases security; predictable values do not improve CSPRNG quality, and trying to make key generation reproducible is dangerous.
- Embed private keys in source code, Git config, or log files to save deployment steps.
- Reuse the same key pair without a policy: distinguish signing keys, agreement keys, key wrapping, lifetimes, and key rotation.

`SecureRandom.getInstanceStrong()` may be appropriate when policy requires it, but it can vary by provider and OS and may exhibit entropy-blocking behavior unsuitable for request-handling paths. Do not treat it as mandatory for every application without evaluation.

## 9. Private Keys, Public Keys, Encoding, and KeyStore

### 9.1. Public Keys Do Not Imply Verified Identity

Public keys can usually be distributed publicly. But if an application fetches a public key from an unauthenticated endpoint, an adversary can **substitute the key** and spoof identity. Therefore, you need certificates, key pinning, signed metadata, a trust store, or an appropriate authentication protocol. `KeyPairGenerator` only generates **cryptographic key values**, not proof of who owns them.

### 9.2. Common Formats

- Public keys in `SubjectPublicKeyInfo` / `X.509` format: typically `publicKey.getFormat()` returns `"X.509"` and `getEncoded()` returns bytes in the corresponding encoding.
- Private keys in `PKCS#8` format: for exportable software keys, `privateKey.getFormat()` is typically `"PKCS#8"` and `getEncoded()` can provide the PKCS#8-encoded bytes.
- **Not every private key is exportable**. If a key resides in an HSM/security token, `getEncoded()` may return `null`; use the appropriate API/provider/keystore.
- Base64/PEM **only encodes to text** and does not protect the private key itself; dumping a Base64 or raw PKCS#8 private key into logs or disk still leaks it.
- `KeyFactory` is used to read/reconstruct key representations when policy permits, with `X509EncodedKeySpec` for public keys and `PKCS8EncodedKeySpec` for private keys. This is an **import/export** operation, not generating a new key pair.
- `KeyStore` or an HSM/KMS helps manage/store keys depending on the provider and system, though exportability, certificate chains, passwords, and usage policies have their own requirements.

In environments requiring TLS or enterprise signing certificates, the workflow may be to **generate the private key inside an HSM**, create a certificate signing request (CSR) or key attestation, and obtain a certificate from a CA. The issued certificate is a **separate object** and does not automatically appear after `generateKeyPair()`.

### 9.3. Key Lifecycles Require Policy

1. **Generate** using approved algorithms and parameters; record metadata such as `keyId`, purpose, timestamp/version.
2. **Store** the private key in an access-controlled boundary, restricting export, encrypting at rest, and backing up per policy.
3. **Distribute** the public key with identity/trust-source verification.
4. **Use** strictly for the intended purpose and algorithm suite, verifying provider/operational capabilities.
5. **Rotate** keys and handle older keys that still have ciphertexts or signatures needing verification; do not delete old keys before inventorying dependencies.
6. **Revoke/destroy** via proper procedures, updating certificates/trusted keys and access states; do not merely drop references in code.

**Never log private key material**, even during "temporary debugging" or when reporting to error-tracking systems. In Java demos, it is best to print only the algorithm and verifiable **public** attributes.

## 10. Providers, Compatibility, and Common Errors

### 10.1. What Does the Provider Determine?

`getInstance("EC")` asks JCA to obtain an engine by name. `initialize(new ECGenParameterSpec("secp256r1"))` asks the engine to use a specific curve. A provider might support the `"EC"` algorithm without supporting the required curve.

In general-purpose applications, letting JCA choose the provider often improves portability. If a system must generate keys **inside an HSM/PKCS#11 or a provider enforcing a specific compliance policy**, specify/configure the provider by design and verify the private key is created in the right place. Specifying a provider by name does not by itself guarantee the private key is non-exportable; that depends on the actual implementation and configuration.

`KeyPairGenerator.getInstance("RSA", "SomeProvider")` uses the **exact registered provider** by name; if the name does not exist, a `NoSuchProviderException` is thrown. Do not silently fall back to a software provider when policy requires an HSM.

### 10.2. Error and Troubleshooting Table

| Issue | Common symptom | How to check / resolve |
| --- | --- | --- |
| Keygen algorithm unavailable | `NoSuchAlgorithmException` from `getInstance` | Check algorithm name, JDK version, and installed providers. |
| Named provider unavailable | `NoSuchProviderException` | Check provider registration, Java security policy, and exact name. |
| `initialize(int)` with invalid/unsupported keysize | `InvalidParameterException` | Check sizes supported by the provider/algorithm. |
| Unsuitable `initialize(AlgorithmParameterSpec)` | `InvalidAlgorithmParameterException` | Use the right spec type, curve name, and provider configuration. |
| Passed `GCMParameterSpec` to initialize `KeyPairGenerator` | Incompatible parameter type; may be rejected | GCM parameters are for symmetric encryption, not RSA/EC key generation. |
| `initialize(256)` when peer requires `secp256r1` | Provider may pick another curve or fail | Use `ECGenParameterSpec("secp256r1")`. |
| `initialize(3072)` for `"Ed25519"` | Incompatible/unsupported metric | Use `NamedParameterSpec.ED25519` or the specified default. |
| 1024-bit RSA for new data | Does not meet common modern security standards | Choose RSA 2048/3072+ per policy; weigh cost and lifetime. |
| Generated X25519 key then passed to `Signature` | Wrong algorithm purpose | Use Ed25519 for signatures, X25519 for key agreement. |
| Logging private key or storing unencrypted Base64 | Risks leaking private key | Use keystore/HSM and protect per policy; never log secrets. |
| Using public key downloaded from untrusted source | Vulnerable to MITM or key substitution | Verify identity and trust source of the public key/certificate. |
| `getEncoded()` returns `null` | Key may be non-exportable | Do not force cast/read raw key; use provider/HSM API as intended. |
| `KeyPairGenerator` used concurrently across threads | Engine is stateful; should not rely on thread safety | Create a separate generator per operation/worker or synchronize properly. |
| Falling back to another provider after failure | May leave HSM/FIPS boundary or violate policy | Handle errors explicitly; do not silently switch providers. |

Do not catch broad `Exception` and downgrade to a weaker algorithm or key size just to succeed. Provider restrictions and security policies are operational constraints to be resolved through configuration and procedures, not bypassed by silent fallbacks.

## 11. Self-Check Knowledge

**Question 1.** Does calling `KeyPairGenerator.getInstance("EC")` followed by `initialize(256)` guarantee the key uses `secp256r1`?

**Answer:** **No.** The number 256 is an algorithm-defined size; the parameter set may be a provider default. To require a specific curve, use `ECGenParameterSpec("secp256r1")` and inspect the generated key.

**Question 2.** For RSA, what does `new RSAKeyGenParameterSpec(3072, RSAKeyGenParameterSpec.F4)` specify?

**Answer:** A 3072-bit modulus and public exponent 65537. The parameter spec does not contain a private key and does not generate the pair on its own.

**Question 3.** Is a key whose `getAlgorithm()` returns `"EC"` and field size is 256 sufficient to prove the exact curve and purpose?

**Answer:** Not sufficient. You must check the actual curve parameter set and the protocol using the key; field size alone does not verify curve identity or usage restrictions.

**Question 4.** Can you take an Ed25519 `KeyPair` and immediately use it with `KeyAgreement.getInstance("X25519")`?

**Answer:** No. Ed25519 is for signatures and X25519 is for key agreement; their parameters, key formats, and usage differ.

**Question 5.** Two X25519 parties compute the same 32-byte secret. Is the protocol immune to man-in-the-middle attacks?

**Answer:** **No.** That only proves the agreement math works; you still need peer authentication, transcript/KDF binding, and a complete protocol.

**Question 6.** If `initialize` is not called, will `KeyPairGenerator.generateKeyPair()` always produce RSA-3072?

**Answer:** No. The default is determined by the provider; to enforce an explicit size policy, call `initialize` appropriately.

**Question 7.** Why must a `PublicKey` still have its source verified even though it can be published?

**Answer:** The public key is not secret, but **the identity bound to the public key** must be verified. A swapped key can lead to spoofing or MITM.

**Question 8.** If `privateKey.getEncoded()` returns a byte array, can you print it in Base64 for debugging?

**Answer:** No. Base64 does not encrypt secrets; that byte array can be PKCS#8 containing the private key. Do not log or expose this value.

**Question 9.** Is passing a `SecureRandom` instance enough to conclude key generation meets FIPS/HSM requirements?

**Answer:** No. You must verify the provider, hardware mechanism, parameters, deployment policy, and associated operational evidence.

## 12. References

- [Java SE 17 — KeyPairGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyPairGenerator.html): `getInstance` overloads, size/parameter initialization, provider defaults.
- [Java SE 17 — KeyPair](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyPair.html): representation of `PrivateKey` and `PublicKey` pair.
- [Java SE 17 — RSAKeyGenParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/RSAKeyGenParameterSpec.html): modulus size, public exponent, and `F4`.
- [Java SE 17 — ECGenParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/ECGenParameterSpec.html): named EC curve parameters.
- [Java SE 17 — NamedParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/NamedParameterSpec.html): `ED25519`, `X25519`, and named parameter specs.
- [Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): cryptographic randomness source.
- [Java SE 17 — KeyAgreement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyAgreement.html): public-key secret agreement.
- [JDK 17 Providers Documentation](https://docs.oracle.com/en/java/javase/17/security/oracle-providers.html): provider-specific support, limitations, and defaults.
