# Supported Cryptography in Java

## Objectives

After this lesson, you will be able to understand the groups of cryptographic services provided by Java; distinguish between APIs, algorithms, and providers; look up supported algorithms in a specific JDK; choose the right standard names for `Cipher`, `MessageDigest`, `Signature`, `Mac`, `KeyAgreement`, `KDF`, and `KEM`; understand the difference between an available algorithm and a security-appropriate algorithm; use AES-GCM in a complete Java program; inspect providers, TLS, and security properties; and plan cryptographic testing when upgrading the JDK or deploying across multiple platforms.

## 1. What Does "Supported Cryptography" Mean?

Java does not provide a single monolithic cryptography function. The platform has a set of security APIs and multiple implementations that can be installed via **Cryptographic Service Providers (providers)**.

When saying an algorithm is supported by Java, you need to distinguish at least four aspects:

1. **Standard name:** Java defines names for applications to request services, such as `AES`, `SHA-256`, `SHA256withRSA`, or `TLSv1.3`.
2. **API/engine:** The Java class that provides the operation, such as `Cipher`, `MessageDigest`, `Signature`, `Mac`, `KeyPairGenerator`, or `SSLContext`.
3. **Provider:** The actual implementation that supplies the algorithm, such as `SunJCE`, `SUN`, `SunRsaSign`, `SunEC`, or `SunJSSE`.
4. **Runtime policy:** An algorithm may have an implementation but be restricted or disabled by security properties, key sizes, protocol configurations, provider configurations, or organizational policies.

Therefore, an algorithm name appearing in documentation does not mean every JDK, every provider, or every configuration allows using it. Nor is a third-party provider required to support every algorithm that Java SE requires a Java SE implementation to support.

This lesson uses JDK 26 as the reference baseline for the provider list and newer algorithms. The practical AES-GCM example is compatible with JDK 17 and later.

## 2. Java Cryptography Architecture (JCA) and Providers

**Java Cryptography Architecture (JCA)** is Java's API and provider architecture that lets applications use security services without implementing algorithms themselves. The Java Cryptography Extension (JCE), once distributed separately in older Java versions, is now part of JCA/JDK.

JCA has three core principles:

- **Implementation independence:** Applications call standard APIs; providers implement the algorithms.
- **Interoperability:** Applications do not necessarily depend on a specific implementation; keys and signatures can be exchanged between compatible providers.
- **Algorithm extensibility:** Additional providers can be installed to supply algorithms or cryptographic hardware not included in the default JDK.

### Engine classes

An engine class is a high-level API representing a category of cryptographic service. Common engines include:

| Engine/API | Responsibility |
|---|---|
| SecureRandom | Generates cryptographically strong random numbers |
| MessageDigest | Computes hashes/digests |
| Cipher | Encrypts and decrypts data |
| Mac | Generates and verifies Message Authentication Codes |
| Signature | Signs data and verifies digital signatures |
| KeyPairGenerator | Generates public/private key pairs |
| KeyGenerator | Generates secret keys |
| KeyAgreement | Negotiates a shared secret |
| KEM | Encapsulates/decapsulates a shared secret using a key encapsulation mechanism |
| KDF | Derives keys from input keying material |
| KeyFactory | Converts between keys and key specifications |
| SecretKeyFactory | Converts between secret keys and key specifications |
| KeyStore | Manages keys and certificates |
| CertificateFactory | Reads certificates and CRLs |
| CertPathBuilder / CertPathValidator | Builds and validates certificate paths |
| SSLContext | Configures TLS/DTLS services |

Each engine calls the `getInstance` factory method to request an algorithm. JCA searches for a provider with a matching implementation and returns an engine object.

Example:

~~~java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
Signature signature = Signature.getInstance("SHA256withRSA");
~~~

The algorithm name passed to `getInstance` is a standard name or an alias supported by the provider. Prefer standard names from the Java Security Standard Algorithm Names specification to minimize differences across providers.

### What is a provider?

A provider is an implementation that registers services and algorithms with JCA. A JDK typically includes multiple providers because each provider handles a specific group of functions or bridges to a different platform.

| Common provider | Primary role |
|---|---|
| SUN | Digest, SecureRandom, certificate/path services, and certain signature/key services |
| SunRsaSign | RSA and RSASSA-PSS |
| SunJCE | Cipher, MAC, key generation, key agreement, KDF/KEM, and password-based crypto |
| SunEC | Elliptic curve and Edwards-curve services |
| SunJSSE | TLS/DTLS, KeyManagerFactory, and TrustManagerFactory |
| SunPKCS11 | Bridge to configured PKCS#11 libraries, HSMs, and smart cards |
| SunMSCAPI | Bridge to Windows cryptographic services and certificate/key stores |
| Apple | Integrates Apple platform cryptographic services on supported JDKs |
| Third-party provider | Additional algorithms, HSMs, FIPS-validated modules, or specialized implementations |

Never assume every provider is present on every Java runtime. For example, `SunMSCAPI` depends on Windows; `SunPKCS11` requires a native PKCS#11 library and token configuration; third-party providers must be installed and registered.

### How JCA selects a provider

If you call:

~~~java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
~~~

JCA searches registered providers in preference order and selects the first provider offering a matching service.

You can request a specific provider:

~~~java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding", "SunJCE");
~~~

Typical applications should let JCA choose the provider. Only specify a provider when explicitly required—for instance, when you must use an HSM, token, evaluated/certified provider, or a specific compatibility configuration. Hard-coding a provider name ties the application to one runtime implementation and can prevent the use of other hardware acceleration.

## 3. Cryptographic Algorithm Groups in Java

### Hash / message digest

A hash takes data of arbitrary length and produces a fixed-length digest. Hashes do not use a secret key.

Common standard names:

- SHA-256
- SHA-384
- SHA-512
- SHA3-256
- SHA3-384
- SHA3-512

Using `MessageDigest`:

~~~java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
byte[] hash = digest.digest(data);
~~~

Hashes are suitable for integrity checking when the digest value is protected or compared over a trusted channel. A plain hash does not authenticate the sender: an attacker can modify both the data and the hash if there is no protective mechanism.

Do not use MD5 or SHA-1 for new designs requiring collision resistance. The fact that a JDK still lists a legacy algorithm for compatibility does not mean that algorithm is still suitable for modern security purposes.

### Symmetric encryption

Symmetric encryption uses the same secret key for encryption and decryption. Java commonly uses `Cipher` with AES or ChaCha20-Poly1305.

Common transformations:

| Transformation | Meaning |
|---|---|
| AES/GCM/NoPadding | AES in Galois/Counter Mode, with authentication |
| AES/CBC/PKCS5Padding | AES-CBC with padding; requires a separate MAC and proper authentication workflow |
| ChaCha20-Poly1305 | Authenticated encryption combining ChaCha20 and Poly1305 |

For new application data, prefer authenticated encryption modes such as AES-GCM or ChaCha20-Poly1305 when supported by all parties. These modes both encrypt and detect data tampering.

Do not use `AES/ECB` for multi-block data. ECB exposes repeating patterns in plaintext. Do not call `Cipher` with just `"AES"` and rely on default mode/padding: defaults can vary across providers. Always specify the full `algorithm/mode/padding`.

### MAC (Message Authentication Code)

A MAC uses a shared secret key to generate a message authentication tag. A recipient with the same key can verify whether the data was altered and whether it was created by a party holding the key.

Common names:

- HmacSHA256
- HmacSHA384
- HmacSHA512

Using `Mac`:

~~~java
Mac mac = Mac.getInstance("HmacSHA256");
mac.init(secretKey);
byte[] tag = mac.doFinal(message);
~~~

A MAC is appropriate when parties share a secret. A MAC cannot be used to prove identity publicly to a third party because any party with the same key can generate a valid tag.

### Digital signatures

Digital signatures use a private key to sign and a public key to verify. They support origin authentication and data integrity.

Common algorithm names:

- SHA256withRSA
- RSASSA-PSS
- SHA256withECDSA
- SHA384withECDSA
- Ed25519 / Ed448
- ML-DSA in supported JDK 26 providers

Using `Signature`:

~~~java
Signature signer = Signature.getInstance("SHA256withRSA");
signer.initSign(privateKey);
signer.update(message);
byte[] signed = signer.sign();
~~~

The recipient creates a `Signature` with the same algorithm, calls `initVerify(publicKey)`, `update(message)`, and `verify(signed)`.

Hash, MAC, and digital signatures are not interchangeable. A hash has no secret; a MAC uses a shared secret; a signature uses a private/public key pair.

### Key generation and key agreement

Commonly used engines:

- `KeyPairGenerator`: generates RSA, EC, EdDSA, X25519, or other provider-supported key pairs.
- `KeyGenerator`: generates secret keys such as AES or ChaCha20.
- `KeyAgreement`: enables two parties using private/public keys to derive a shared secret, such as ECDH or X25519.
- `KeyFactory`: converts key encodings into Java key objects and vice versa.

Common algorithm names include `RSA`, `EC`, `Ed25519`, `X25519`, `DiffieHellman`, and `ECDH`. Key sizes, curves, and parameters must comply with security policies and the interoperability capabilities of all parties.

### KDF and KEM

A KDF (Key Derivation Function) derives keys from input keying material and context. Examples in JDK 26 providers are `HKDF-SHA256`, `HKDF-SHA384`, and `HKDF-SHA512`. For passwords, `PBKDF2WithHmacSHA256` is a common `SecretKeyFactory` name.

A KEM (Key Encapsulation Mechanism) allows a sender to encapsulate a shared secret so the recipient can decapsulate it using their private key. It is a building block for key establishment protocols, not a file encryption API replacing `Cipher`.

JDK 26 providers support post-quantum algorithms:

- `ML-KEM-512`, `ML-KEM-768`, and `ML-KEM-1024` in `SunJCE`.
- `ML-DSA-44`, `ML-DSA-65`, and `ML-DSA-87` in `SUN`.
- `HKDF-SHA256/384/512` in `SunJCE`.

ML-KEM is the key encapsulation algorithm standardized in FIPS 203; ML-DSA is the digital signature algorithm standardized in FIPS 204. These are supported by specific JDK 26 providers and should not be assumed to exist in older JDKs or every third-party provider. When using them in production systems, verify APIs, providers, key formats, interoperability, and protocol support on both ends.

## 4. Algorithms Required by Java SE Implementations

Java Security Standard Algorithm Names defines standard names and a set of algorithms that Java SE implementations must support. This is a platform compatibility requirement, not a security strength ranking.

Notable examples in Java SE 26:

| Service | Selected required names/variants |
|---|---|
| Cipher | AES/GCM/NoPadding, ChaCha20-Poly1305, certain AES-CBC/ECB and RSA-OAEP transformations |
| MessageDigest | SHA-1, SHA-256, SHA-384 |
| Mac | HmacSHA1, HmacSHA256 |
| KeyGenerator | AES 128/256, ChaCha20, HmacSHA1, HmacSHA256 |
| KeyAgreement | DiffieHellman, ECDH with secp256r1/secp384r1, X25519 |
| Signature | SHA256withRSA, SHA384withRSA, SHA256withECDSA, SHA384withECDSA, RSASSA-PSS |
| SecretKeyFactory | PBKDF2WithHmacSHA256 |
| SSLContext | TLSv1.2, TLSv1.3 |
| KeyStore | PKCS12 |

The full specification includes additional services, parameters, key sizes, curves, and encodings. Do not copy this table into a fixed security configuration: requiring an implementation to support an algorithm does not mean every algorithm should be used.

JDK 26 includes providers that support many algorithms beyond the Java SE minimum, including SHA-3, EdDSA, ML-DSA, ML-KEM, and HKDF. The exact list depends on the provider and JDK version.

## 5. Available Does Not Mean Secure

A JDK may still provide legacy algorithms to read old data or maintain compatibility. A successful `getInstance` call only indicates that a provider found an implementation; it does not confirm that the algorithm is appropriate for your security goals.

| Algorithm/Mode | Guidance for new designs |
|---|---|
| AES-GCM | Common authenticated encryption choice; manage nonces properly |
| ChaCha20-Poly1305 | Suitable AEAD when supported by all parties |
| AES-ECB | Avoid for multi-block data |
| AES-CBC | Use only with secure padding and authentication; never assume ciphertext is authenticated on its own |
| RSA-OAEP | Use when RSA encryption is needed; never use raw RSA |
| RSASSA-PSS | RSA signature with randomized padding, generally preferred over PKCS#1 v1.5 for new designs when supported |
| SHA-256/SHA-384/SHA-512 | Modern hashes for general purposes |
| SHA-1/MD5 | Do not use for new signatures/hashes requiring collision resistance |
| DES/3DES/RC4 | Legacy algorithms; avoid in new designs |
| HmacSHA256 | Common MAC when parties share a secret |
| PBKDF2WithHmacSHA256 | Password-based key derivation; requires unique salt and appropriate cost factor |

Key principles:

- Never design your own cryptographic algorithms, modes, or protocols.
- Never use a fast hash like SHA-256 directly to store passwords. Use a password KDF with a random salt and tuned cost; consider dedicated password hashing algorithms through an evaluated provider if policy requires it.
- Never use Base64 as encryption; Base64 is only an encoding.
- Never use `Random` to generate keys, nonces, or security tokens; use `SecureRandom`.
- Never hard-code keys in source code, public configs, or logs.
- Manage the key lifecycle: generation, distribution, storage, rotation, backup, revocation, and destruction.
- Prefer high-level libraries/protocols such as JSSE/TLS over assembling your own protocol from `Cipher` and `KeyAgreement`.

## 6. How to Inspect Algorithms on a Running Runtime

JDK documentation describes the capabilities of a release/provider; applications still need to verify the actual runtime.

### Listing providers

The following program lists registered providers and the number of services each provider advertises:

~~~java
import java.security.Provider;
import java.security.Security;

public class ProviderInventory {
    public static void main(String[] args) {
        for (Provider provider : Security.getProviders()) {
            System.out.println(
                    provider.getName() + " " + provider.getVersionStr()
                    + " services=" + provider.getServices().size());
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 ProviderInventory.java
java ProviderInventory
~~~

Names, versions, and service counts depend on the JDK vendor, version, OS, installed providers, and runtime configuration. Do not assert a fixed output in tests if environments support different providers.

### Listing algorithms by provider

You can extend the program to inspect the services registered by each provider:

~~~java
import java.security.Provider;
import java.security.Security;

public class AlgorithmInventory {
    public static void main(String[] args) {
        for (Provider provider : Security.getProviders()) {
            for (Provider.Service service : provider.getServices()) {
                System.out.printf(
                        "%s | %s | %s%n",
                        provider.getName(),
                        service.getType(),
                        service.getAlgorithm());
            }
        }
    }
}
~~~

Run with similar commands:

~~~bash
javac --release 17 AlgorithmInventory.java
java AlgorithmInventory
~~~

The output can be long and varies by runtime. Providers may register aliases; therefore, a service list is a diagnostic tool, not complete proof that every transformation or key parameter will work.

### Checking a specific transformation

The simplest approach is to request the exact engine/algorithm your application intends to use:

~~~java
Cipher.getInstance("AES/GCM/NoPadding");
~~~

If no matching implementation exists, the API may throw `NoSuchAlgorithmException` or `NoSuchPaddingException`. Obtaining the object alone does not prove that key sizes, parameters, modes, certificates, or environment policies are valid. You must initialize it and run a real test with the expected keys and parameters.

### Using the `java` command to inspect security configuration

JDK 26 supports:

~~~bash
java -XshowSettings:security:providers -version
java -XshowSettings:security:tls -version
java -XshowSettings:security:properties -version
~~~

- `security:providers` displays statically configured providers.
- `security:tls` displays TLS-related information.
- `security:properties` displays security properties.

These commands are useful when comparing local, CI, and production environments. Providers can also be added dynamically at runtime; in that case, check via `Security.getProviders()` inside the application's own JVM.

## 7. Complete Example: AES-GCM Encryption and Decryption

The following example generates a random AES key, creates a 96-bit nonce with `SecureRandom`, encrypts data using AES-GCM, and decrypts it to verify that the plaintext is recovered.

File `SupportedCryptoDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class SupportedCryptoDemo {
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int NONCE_LENGTH = 12;
    private static final int TAG_LENGTH_BITS = 128;

    public static void main(String[] args) throws GeneralSecurityException {
        byte[] plaintext = "Java security".getBytes(StandardCharsets.UTF_8);

        KeyGenerator keyGenerator = KeyGenerator.getInstance("AES");
        keyGenerator.init(256, new SecureRandom());
        SecretKey key = keyGenerator.generateKey();

        byte[] nonce = new byte[NONCE_LENGTH];
        new SecureRandom().nextBytes(nonce);

        Cipher encryptor = Cipher.getInstance(TRANSFORMATION);
        encryptor.init(
                Cipher.ENCRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_LENGTH_BITS, nonce));
        byte[] ciphertext = encryptor.doFinal(plaintext);

        Cipher decryptor = Cipher.getInstance(TRANSFORMATION);
        decryptor.init(
                Cipher.DECRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_LENGTH_BITS, nonce));
        byte[] recovered = decryptor.doFinal(ciphertext);

        System.out.println("algorithm=" + encryptor.getAlgorithm());
        System.out.println("plaintext="
                + new String(recovered, StandardCharsets.UTF_8));
        System.out.println("verified=" + Arrays.equals(plaintext, recovered));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 SupportedCryptoDemo.java
java SupportedCryptoDemo
~~~

Expected output:

~~~text
algorithm=AES/GCM/NoPadding
plaintext=Java security
verified=true
~~~

### Explanation

1. `KeyGenerator` creates a 256-bit AES secret key.
2. `SecureRandom` generates a 12-byte (96-bit) nonce.
3. `Cipher` is requested with the full transformation `AES/GCM/NoPadding`.
4. `GCMParameterSpec` sets the authentication tag length to 128 bits and supplies the nonce.
5. `doFinal` encrypts the plaintext and appends the authentication tag to the ciphertext.
6. The decryption `Cipher` uses the same key and nonce; if the ciphertext or tag is modified, decryption fails with an authentication error, typically `AEADBadTagException`.
7. `Arrays.equals` confirms the decrypted plaintext matches the original data.

### Mandatory rule for GCM nonces

Never reuse the same nonce with the same key for two GCM encryptions. Nonce reuse can reveal relationships between plaintexts and break GCM's authentication guarantees.

In this example, the nonce is generated randomly for demonstration. Systems encrypting large volumes of data under the same key must design nonce generation and uniqueness according to the system's volume, storage, and distribution constraints. Storing the nonce alongside the ciphertext is normal; nonces do not need to be secret, but they must be managed properly.

This example is solely for learning the API. Production applications also need secure key storage, metadata/AAD binding where appropriate, ciphertext format versioning, key rotation, and access control.

## 8. Choosing the Right API by Purpose

Select the engine based on your security goal:

| Need | Appropriate API | Example |
|---|---|---|
| Create a data fingerprint | MessageDigest | SHA-256 |
| Authenticate messages between parties sharing a key | Mac | HmacSHA256 |
| Encrypt data with authentication | Cipher | AES/GCM/NoPadding |
| Sign and verify data | Signature | SHA256withRSA, Ed25519 |
| Generate symmetric keys | KeyGenerator | AES |
| Generate key pairs | KeyPairGenerator | RSA, EC, Ed25519 |
| Exchange a shared secret | KeyAgreement | ECDH, X25519 |
| Derive keys from input keying material | KDF | HKDF-SHA256 |
| Key encapsulation | KEM | ML-KEM |
| Generate cryptographic random numbers | SecureRandom | DRBG |
| Secure network communication | JSSE/SSLContext | TLSv1.2, TLSv1.3 |
| Manage keys/certificates | KeyStore | PKCS12 |
| Validate certificate chains | CertPathValidator | PKIX |

When transmitting data over a network, you should generally use TLS with JSSE and proper certificate validation rather than building a custom encryption protocol out of `Cipher`, `Signature`, and `KeyAgreement`.

## 9. TLS and Runtime Security Algorithms

TLS is the protocol for securing network connections. In Java, JSSE provides `SSLContext`, `SSLSocket`, `SSLEngine`, `TrustManagerFactory`, and `KeyManagerFactory`. JSSE also uses JCA providers for underlying cryptographic algorithms.

In Java SE 26, `TLSv1.2` and `TLSv1.3` are the `SSLContext` algorithm names that Java SE implementations must support. The `SunJSSE` provider supplies these implementations. TLS 1.0 and TLS 1.1 are legacy and disabled by default in JDK 26.

Common TLS 1.3 cipher suites:

- TLS_AES_128_GCM_SHA256
- TLS_AES_256_GCM_SHA384
- TLS_CHACHA20_POLY1305_SHA256

Note: `Cipher` transformation names such as `AES/GCM/NoPadding` differ from TLS cipher suite names. TLS negotiates the protocol, key exchange, signature scheme, and cipher suite based on both endpoints' configurations.

A cipher suite being known to an implementation does not mean it is enabled by default. The `jdk.tls.disabledAlgorithms` security property and TLS configurations can exclude protocols, key sizes, or cipher suites.

Do not re-enable SSLv3, TLS 1.0, TLS 1.1, or weak algorithms just to allow an old peer to connect. Upgrade the peer or establish an approved, tightly scoped compatibility exception.

## 10. Security Properties and Restricted Algorithms

The JDK has security properties to control algorithms and protocols. Important properties include:

| Property | Scope |
|---|---|
| jdk.tls.disabledAlgorithms | Restricts protocols, cipher suites, key sizes, or algorithms in TLS |
| jdk.certpath.disabledAlgorithms | Restricts algorithms and keys in certificate path validation |
| jdk.jar.disabledAlgorithms | Restricts algorithms used to verify JAR signatures |
| jdk.security.legacyAlgorithms | Classifies legacy algorithms in certain security operations |
| crypto.policy | Configures JDK cryptographic strength policy limits |

Security properties are typically set in the `java.security` file under the `conf/security` directory of Java home or in additional configuration loaded at runtime. Some can be read via `Security.getProperty`.

Do not remove algorithms from `disabledAlgorithms` just to make a program run. If legacy data must be supported, separate the legacy read/migration workflow from new data creation, and document the scope, expiration, and policy approval.

Permitted key sizes also depend on the provider, runtime, policy, and algorithm. Do not assume that 256-bit keys are supported everywhere or that every 2048-bit key is sufficiently secure for every algorithm.

## 11. Cross-Environment Compatibility Checks

When developing applications that use cryptography, test on the exact runtime where you will deploy:

- JDK vendor and full version.
- Operating system and CPU architecture.
- Provider list and preference order.
- Third-party providers, HSMs, or PKCS#11 configurations.
- Security properties and crypto policy.
- Key sizes, curves, modes, padding, and algorithm parameters.
- TLS protocols, cipher suites, and certificate chains.
- Interoperability of keys/ciphertexts/signatures with other systems.

An algorithm may exist in JDK 26 but not in JDK 17. A provider may exist on Windows but not on Linux. An HSM may support only a specific subset of ciphers/signatures and key sizes.

For distributed systems, test interoperability across providers and JDK versions. Do not only test encrypt/decrypt within the same JVM; verify that data produced by one implementation can be read or verified by the other implementation according to the same standard.

## 12. Common Errors and Troubleshooting

### NoSuchAlgorithmException

**Symptom:** `getInstance` reports that the algorithm cannot be found.

**Cause:** Wrong name, provider lacks the service, provider is not registered, or the runtime does not support the algorithm.

**Resolution:** Check the standard name in Java Security Standard Algorithm Names; list providers/services; verify the JDK version and install required providers.

### NoSuchPaddingException

**Symptom:** The `Cipher` transformation has a valid algorithm, but the padding is unsupported.

**Cause:** Incorrect transformation or the provider does not support the requested mode/padding.

**Resolution:** Use a full transformation advertised by the provider; verify the exact mode and padding names; test on the target runtime.

### InvalidKeyException or InvalidAlgorithmParameterException

**Symptom:** Key size, key type, curve, IV, nonce, or parameter is invalid.

**Cause:** Key is incompatible with the algorithm, key size exceeds policy limits, or parameters are missing/incorrect.

**Resolution:** Verify the key algorithm, key size, and parameter spec; check the provider and crypto policy; generate keys using the appropriate engine.

### AEADBadTagException

**Symptom:** AES-GCM or ChaCha20-Poly1305 fails to decrypt data.

**Cause:** Ciphertext, tag, key, nonce, or AAD mismatch; data may have been tampered with.

**Resolution:** Check format and metadata; confirm the correct key/nonce/AAD; treat authentication failures as untrusted data and never return partial plaintext to the application.

### Algorithm exists in the JDK but cannot be used

**Symptom:** The provider lists the algorithm, yet `getInstance`/`init`/handshake still fails.

**Cause:** The algorithm is disabled by a security property, the key size is invalid, the transformation is missing mode/padding, or the provider does not support the specific parameters.

**Resolution:** Read security properties, inspect provider services, and initialize the engine with proper parameters; run tests in the same runtime/configuration as production.

### TLS handshake failure or no cipher suites in common

**Symptom:** Two peers fail to complete a TLS handshake.

**Cause:** No overlap in protocols, cipher suites, signature schemes, named groups, certificate/key types, or trust chains.

**Resolution:** Inspect TLS configurations on both ends; check `java -XshowSettings:security:tls`; verify certificates, hostnames, providers, and disabled algorithms. Do not broadly weaken security policies.

### Provider differences across machines

**Symptom:** The application runs on a developer machine but fails in a container/server.

**Cause:** Different JDK vendor/version, OS providers, third-party providers, or native libraries.

**Resolution:** Log the runtime/provider inventory in diagnostics; pin the JDK toolchain; install and configure providers/native dependencies per official documentation; add integration tests on the target environment.

## 13. Algorithm Selection and Verification Checklist

- [ ] Identify the goal: hash, MAC, encryption, signature, key agreement, KDF, KEM, or TLS.
- [ ] Choose the right engine API for the goal.
- [ ] Use standard names from Java Security Standard Algorithm Names.
- [ ] Verify the actual JDK version and providers.
- [ ] Specify explicit mode/padding for `Cipher`.
- [ ] Prefer authenticated encryption for new data.
- [ ] Never reuse a nonce with the same key in AEAD.
- [ ] Use `SecureRandom` for keys, nonces, and tokens.
- [ ] Use a password KDF for passwords, never a single fast hash.
- [ ] Do not use weak algorithms just because the JDK still lists them.
- [ ] Check security properties, key sizes, and crypto policies.
- [ ] Check certificates, key formats, and interoperability.
- [ ] Test on the exact JDK/OS/provider used in production.
- [ ] Manage key storage, rotation, backup, revocation, and secret access.
- [ ] Use TLS/JSSE for network communication instead of building a custom protocol.
- [ ] Evaluate provider/HSM/FIPS requirements with the security team when compliance is required.

## 14. Official References

- [Java Cryptography Architecture (JCA) Reference Guide — Java SE 26](https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html) — engine classes, provider architecture, `SecureRandom`, `Cipher`, `Signature`, `Mac`, and key management.
- [Java Security Standard Algorithm Names — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html) — standard names for ciphers, digests, MACs, keys, signatures, KDFs, KEMs, TLS, and algorithms required of Java SE implementations.
- [JDK Providers Documentation — Java SE 26](https://docs.oracle.com/en/java/javase/26/security/oracle-providers.html) — specific algorithms in `SUN`, `SunJCE`, `SunRsaSign`, `SunJSSE`, `SunEC`, `SunPKCS11`, and platform providers.
- [Java Security Developer's Guide — Java SE 26](https://docs.oracle.com/en/java/javase/26/security/) — configuring security properties, providers, PKCS#11, JSSE, PKI, and security tools.
- [The java Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — `-XshowSettings:security:providers`, `security:tls`, and `security:properties` options.
- [FIPS 203: Module-Lattice-Based Key-Encapsulation Mechanism Standard](https://csrc.nist.gov/pubs/fips/203/final) — ML-KEM standard.
- [FIPS 204: Module-Lattice-Based Digital Signature Standard](https://csrc.nist.gov/pubs/fips/204/final) — ML-DSA standard.

Java provides many cryptographic algorithms through JCA and its providers. Choose the right engine, standard name, mode, and provider; verify actual capabilities on your target runtime; and evaluate cryptographic strength and security policy independently of whether an algorithm is listed.
