# 8.4 Converting Keys with KeyFactory and KeySpec

In the Java Cryptography Architecture (JCA), asymmetric algorithms operate on `PublicKey` and `PrivateKey`, yet keys can appear in many forms: provider-created objects, mathematical components (such as RSA's modulus/exponent), DER byte arrays, or PEM strings in configuration files. **`KeyFactory`** is the API used to construct key objects from a **`KeySpec`**, extract a matching specification from a key, and translate keys between representations supported by a provider. Mastering the boundary between these three concepts — **key object**, **key specification**, and **encoding** — helps prevent importing the wrong format, mixing up public/private keys, leaking private keys, or assuming DER decoding authenticates the key's origin.

This lesson focuses on the Java 17+ API for **asymmetric public and private keys**. The examples generate temporary in-memory keys to verify round-trips with RSA, EC, Ed25519, and PEM; the operational sections explain non-exportable keys, certificates, providers, and input errors.

## 1. Four Types of Objects to Distinguish

| Component | Java API | Role | What not to infer |
| --- | --- | --- | --- |
| **Key object** | `Key`, `PublicKey`, `PrivateKey` | Object used by `Signature`, `Cipher`, `KeyAgreement`, or other APIs per algorithm | A `Key` does not necessarily allow exporting key material via `getEncoded()`. |
| **Key specification** | `KeySpec` and its implementing classes | Describes data used to construct a key or a representation extracted from a key | A `KeySpec` does not mean the key is accepted by a provider or protected from reading. |
| **Converter** | `KeyFactory` | `KeySpec → Key`, `Key → KeySpec`, `Key → Key` via `translateKey` | Does not generate random key pairs, does not sign, and does not verify the owner's identity. |
| **Key pair generator** | `KeyPairGenerator` | Generates new `PublicKey`/`PrivateKey` pairs from algorithm parameters | Not a tool for importing an existing key from DER/PEM. |

Common data flow:

```text
      KeyPairGenerator("RSA")                file/public API
                |                                  |
                v                                  v
        KeyPair(PublicKey, PrivateKey)         DER/PEM bytes
                |                                  |
         getEncoded()                                |
                |                                  v
          DER byte arrays             X509EncodedKeySpec (public)
                |                      PKCS8EncodedKeySpec (private)
                |                                  |
                v                                  v
     X509EncodedKeySpec                     KeyFactory("RSA")
     PKCS8EncodedKeySpec                      generatePublic
                |                            generatePrivate
                +--------------+-------------------+
                               |
                  PublicKey / PrivateKey
                               |
                       Signature / Cipher
```

**The algorithm name must match**: `KeyFactory.getInstance("RSA")` handles RSA keys; `KeyFactory.getInstance("EC")` handles elliptic curve keys supported by the provider; `KeyFactory.getInstance("Ed25519")` is for Ed25519 on a suitable JDK. `KeyFactory` does not accept signing operation names like `SHA256withRSA` or `SHA256withECDSA`: those are names for `Signature`, not key factory names.

### 1.1 Key vs. SecretKey

`Key` is the common interface, but `KeyFactory` belongs to the **asymmetric key** workflow (`PublicKey`/`PrivateKey`). For secret keys derivable from `KeySpec` types such as `PBEKeySpec`, Java provides **`SecretKeyFactory`** and dedicated symmetric key mechanisms. Do not call `KeyFactory.getInstance("AES")` to import a raw AES byte array; when policy allows a raw AES key, JCE workflows typically use `SecretKeySpec` or an appropriate `KeyGenerator`/KMS.

## 2. Core API of KeyFactory

```java
// The lines below only illustrate the API signatures and usage flow;
// key, spec, and providerName must be created/obtained in a real program.
KeyFactory factory = KeyFactory.getInstance("RSA");
PublicKey publicKey = factory.generatePublic(publicKeySpec);
PrivateKey privateKey = factory.generatePrivate(privateKeySpec);
RSAPublicKeySpec rsaSpec =
        factory.getKeySpec(publicKey, RSAPublicKeySpec.class);
Key translated = factory.translateKey(publicKey);
```

Core methods:

| Call | Input | Primary output / exception |
| --- | --- | --- |
| `KeyFactory.getInstance("RSA")` | Algorithm name of the **key factory** | `KeyFactory`; may throw `NoSuchAlgorithmException` if no implementation is available. |
| `KeyFactory.getInstance("RSA", "providerName")` | Algorithm and registered provider name | May throw `NoSuchProviderException` if the provider name does not exist, or `NoSuchAlgorithmException` if the provider lacks support. |
| `generatePublic(KeySpec)` | Appropriate public key spec | `PublicKey`, or `InvalidKeySpecException`. |
| `generatePrivate(KeySpec)` | Appropriate private key spec | `PrivateKey`, or `InvalidKeySpecException`. |
| `getKeySpec(Key, Class<T>)` | Key object and desired KeySpec **class** | A `T extends KeySpec`, or `InvalidKeySpecException` if it cannot be represented/converted. |
| `translateKey(Key)` | Key object possibly from another provider | `Key` object handled by the target factory/provider, or `InvalidKeyException`. |
| `getProvider()` | None | Backing provider of the factory; useful for diagnosing the environment. |

Primary directions:

```text
spec  --generatePublic/generatePrivate-->  key
key   --getKeySpec(Class<T>)----------->  spec
key   --translateKey------------------->  key of target provider/factory
```

`translateKey` does **not** turn an RSA algorithm into EC, does not derive a private key from a public key, and does not guarantee exporting an HSM key into Java memory. It only converts a **compatible** key object to a representation/provider supported by the factory, if permitted.

Depending on the implementation/provider, multiple valid `KeySpec` types may exist for the same key. Passing `X509EncodedKeySpec.class` or `RSAPublicKeySpec.class` tells the factory **which output form you want**, not to generate a new key pair.

## 3. Two Useful Groups of KeySpec

### 3.1 EncodedKeySpec: Structured Byte Representations of Keys

Two common classes:

| Class | Expected input | `getFormat()` | Used to |
| --- | --- | --- | --- |
| `X509EncodedKeySpec` | DER of **SubjectPublicKeyInfo** (SPKI) in X.509 | `"X.509"` | Construct a **public key** via `generatePublic`. |
| `PKCS8EncodedKeySpec` | DER of **PrivateKeyInfo/PKCS #8** unencrypted at the outer wrapper | `"PKCS#8"` | Construct a **private key** via `generatePrivate`. |

Both implement `KeySpec` via `EncodedKeySpec`. Constructors accept `byte[]`; **constructing a spec does not prove the DER is valid**. The provider typically decodes and validates the structure when `generatePublic`/`generatePrivate` is called. If the DER is invalid, has the wrong algorithm, or is unsupported, `InvalidKeySpecException` is typically thrown.

An RSA key represented as SPKI (public) has an **AlgorithmIdentifier wrapper** identifying the algorithm and a BIT STRING containing the key data. PKCS #8 for private keys has its corresponding structure and algorithm metadata. Therefore, even though both are byte arrays, `X509EncodedKeySpec` and `PKCS8EncodedKeySpec` **cannot be swapped**.

### 3.2 TransparentKeySpec: Mathematical Components

RSA examples:

- `RSAPublicKeySpec`: big integers `modulus` (`n`) and `publicExponent` (`e`), plus optional algorithm parameters per the API.
- `RSAPrivateKeySpec`: `modulus` (`n`) and `privateExponent` (`d`), which may omit full CRT optimization parameters.
- `RSAPrivateCrtKeySpec`: includes RSA CRT parameters (`p`, `q`, `dP`, `dQ`, `qInv`, etc.) for a complete private key representation.
- Other algorithms have corresponding specs, such as `ECPublicKeySpec` and `ECPrivateKeySpec`; curve/point parameters must be valid for the algorithm and provider.

Mathematical descriptions are useful when integrating specialized formats or inspecting key components. However, **private key `BigInteger` values are secret data**. Never print them to logs, JSON, exception messages, or telemetry; do not manually copy private key components across systems without clear justification and controls.

### 3.3 Opaque Keys and KeySpec

Under JCA, `Key` exposes `getAlgorithm()`, `getFormat()`, and `getEncoded()`. However, **not every key returns an encoding**:

- `getFormat()` may return `null` when the key has no exportable format.
- `getEncoded()` may return `null` (for example, keys residing in an HSM, smart card, or hardware-backed keystore).
- `getKeySpec` may also be **rejected** if the provider prohibits exporting the corresponding key material.
- `translateKey` may throw `InvalidKeyException` when a key cannot be moved to the target provider.

Do not write `Objects.requireNonNull(privateKey.getEncoded())` and write the private key out to disk as a default pattern. When working with an HSM/KMS, typically **keep the key inside the provider** and perform signing/decryption according to allowed capabilities. Being unable to export a private key is a security property to respect.

## 4. DER, PEM, X.509, PKCS #8, and Easily Confused Forms

### 4.1 DER Is Bytes, PEM Is Text Armor

**DER** is ASN.1's deterministic binary encoding. **PEM** typically presents DER in Base64 between `-----BEGIN ...-----` / `-----END ...-----` labels. Converting PEM to DER is **stripping header/footer and Base64-decoding**, not cryptographic decryption.

Example PEM labels:

```text
-----BEGIN PUBLIC KEY-----
(Base64 of SubjectPublicKeyInfo DER)
-----END PUBLIC KEY-----
```

```text
-----BEGIN PRIVATE KEY-----
(Base64 of unencrypted PKCS #8)
-----END PRIVATE KEY-----
```

The examples above illustrate **label structure**, not real keys, and cannot be executed. The `PRIVATE KEY` content remains a secret **even when Base64-encoded** and must be protected like the underlying key.

| Label / data source | Usually represents | Can be passed directly into `X509EncodedKeySpec` or `PKCS8EncodedKeySpec`? |
| --- | --- | --- |
| `BEGIN PUBLIC KEY` | SPKI DER after Base64 decode | **Yes**, `X509EncodedKeySpec` if the algorithm matches. |
| `BEGIN PRIVATE KEY` | PKCS #8 private-key DER unencrypted at the outer wrapper | **Yes**, `PKCS8EncodedKeySpec` if the algorithm matches. |
| `BEGIN RSA PUBLIC KEY` | RSA public key in PKCS #1 structure (only `n`, `e`) | **Not directly** into X.509 SPKI; requires a parser/structural conversion. |
| `BEGIN RSA PRIVATE KEY` | RSA private key per PKCS #1 | **Not directly** into `PKCS8EncodedKeySpec`; requires a valid parser/converter or tool to re-export as PKCS #8. |
| `BEGIN EC PRIVATE KEY` | SEC1 `ECPrivateKey` | **Not directly** into PKCS #8; requires format conversion and accurate curve parameters. |
| `BEGIN ENCRYPTED PRIVATE KEY` | PKCS #8 **encrypted** at the outer wrapper | **Not directly**. Must decrypt the protection wrapper with password/key and an appropriate API/library before constructing the private key. |
| `BEGIN CERTIFICATE` | X.509 certificate containing many fields and a CA signature, with an SPKI public key inside | **Not directly** into `X509EncodedKeySpec`. Use `CertificateFactory` to parse the certificate then call `getPublicKey()`; **verifying chain/trust** is a separate step. |

Be sure to distinguish **`X509EncodedKeySpec` and `X509Certificate`**: the spec only contains the SPKI public-key encoding; a certificate also contains subject, issuer, validity, extensions, and signature. Parsing a public key from SPKI does **not** prove who the sender or key owner is.

### 4.2 PKCS #8 Does Not Mean the Key Is Encrypted for Protection

The name `PKCS8EncodedKeySpec` describes a **private key structure**, not password encryption. A private key in `BEGIN PRIVATE KEY` is usually only **packaged**, not protected by file-level encryption. `BEGIN ENCRYPTED PRIVATE KEY` is a different structure involving `EncryptedPrivateKeyInfo` and a secure decryption flow.

Therefore:

- Do not send `PRIVATE KEY` files over email/chat/logs simply because they are in PEM or Base64 form.
- Do not put PEM private key strings in source code, public configurations, or build artifacts.
- For long-term key storage, consider Java `KeyStore`, hardware keystores, KMS/HSM, and access controls instead of writing a custom parser and storing raw private keys.
- Password protection on a keyfile does not by itself guard against unauthorized access if the application exposes the key after decrypting it into RAM.

## 5. Java 17+ Example: RSA KeyFactory Round-Trip and Mathematical KeySpec

This example generates a 2048-bit RSA pair with `KeyPairGenerator`, exports **SPKI DER** for the public key and **PKCS #8 DER** for the private key, reconstructs them with `KeyFactory`, extracts `RSAPublicKeySpec`, and signs/verifies to prove the reconstructed key objects match.

Save as **`RsaKeyConversionDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.interfaces.*;
import java.security.spec.*;
import java.util.*;

public final class RsaKeyConversionDemo {
    public static void main(String[] args) throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair original = generator.generateKeyPair();

        byte[] publicDer = original.getPublic().getEncoded();
        byte[] privateDer = original.getPrivate().getEncoded();

        KeyFactory factory = KeyFactory.getInstance("RSA");
        PublicKey restoredPublic =
                factory.generatePublic(new X509EncodedKeySpec(publicDer));
        PrivateKey restoredPrivate =
                factory.generatePrivate(new PKCS8EncodedKeySpec(privateDer));

        RSAPublicKeySpec math =
                factory.getKeySpec(restoredPublic, RSAPublicKeySpec.class);
        PublicKey fromMath = factory.generatePublic(math);
        Key translated = factory.translateKey(restoredPublic);

        Signature signature = Signature.getInstance("SHA256withRSA");
        byte[] data =
                "KeyFactory lesson".getBytes(StandardCharsets.UTF_8);
        signature.initSign(restoredPrivate);
        signature.update(data);
        byte[] signed = signature.sign();

        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(fromMath);
        verifier.update(data);

        System.out.println("Public format: "
                + original.getPublic().getFormat());
        System.out.println("Private format: "
                + original.getPrivate().getFormat());
        System.out.println("Public key round-trip: "
                + Arrays.equals(publicDer, restoredPublic.getEncoded()));
        System.out.println("RSA modulus bits: "
                + math.getModulus().bitLength());
        System.out.println("RSA verify: " + verifier.verify(signed));
        System.out.println("Translated algorithm: "
                + translated.getAlgorithm());

        Arrays.fill(privateDer, (byte) 0);
    }
}
```

```bash
javac -encoding UTF-8 RsaKeyConversionDemo.java
java RsaKeyConversionDemo
```

On common JDKs with RSA KeyFactory and `SHA256withRSA`:

```text
Public format: X.509
Private format: PKCS#8
Public key round-trip: true
RSA modulus bits: 2048
RSA verify: true
Translated algorithm: RSA
```

**Detailed breakdown:**

1. `KeyPairGenerator` **generates** new keys. `KeyFactory` **reconstructs/converts** existing keys; the two APIs have different purposes.
2. `getEncoded()` returns the DER encoding when the provider allows export; the example uses exportable software keys. Do not assume private key material always exists as bytes.
3. `new X509EncodedKeySpec(publicDer)` and `new PKCS8EncodedKeySpec(privateDer)` pick the **right spec for the right key type**.
4. `generatePublic`/`generatePrivate` reconstructs key objects from specs. Successful sign/verify proves the pair corresponds; it does **not** prove the key belongs to an external identity.
5. `getKeySpec(restoredPublic, RSAPublicKeySpec.class)` extracts the two RSA mathematical components `n` and `e`; `generatePublic(math)` builds a public key from them.
6. `translateKey(restoredPublic)` converts a key into an object compatible with the active factory, which here is still RSA. The default provider is chosen, so the example does **not** demonstrate translating keys between two specific providers.
7. `Arrays.equals(publicDer,...)` returns `true` on the tested implementation, yet **identical byte encodings should not be treated as a cross-provider contract** for all algorithms. Functional signature verification and proper mathematical parameters reflect actual key behavior.
8. `Arrays.fill(privateDer, 0)` clears the **DER array owned by the program**, not internal copies inside `PKCS8EncodedKeySpec`, the `PrivateKey` object, signatures, or the provider. Exporting the private key here is strictly educational; never write `privateDer`, private modulus/CRT factors, or private PEM to stdout.

**RSA 2048** is an example key size for fast execution; key sizes, padding/signature modes (such as RSA-PSS with `Signature`), certificate rules, and lifetimes must follow your specific policy. `KeyFactory` does not decide whether a signing algorithm or key size satisfies business security requirements.

## 6. When Is `RSAPublicKeySpec` Useful?

Suppose a trusted protocol supplies the two RSA numbers `n` and `e` in a validated canonical form. You can build an `RSAPublicKeySpec` from them:

```java
// Illustrated inside a method declaring throws GeneralSecurityException.
// n and e are valid BigIntegers obtained from parsed/validated input.
RSAPublicKeySpec spec = new RSAPublicKeySpec(n, e);
PublicKey publicKey = KeyFactory.getInstance("RSA").generatePublic(spec);
```

This is an **illustrative snippet, not a standalone program**: `n` and `e` are not declared. It shows the `RSAPublicKeySpec → PublicKey` relationship. In real integration:

- Validate format and length limits on serialized input before constructing `BigInteger`; do not let huge inputs spike memory/CPU consumption.
- Validate modulus, exponent, key size, and policy compliance. `KeyFactory.generatePublic` may reject invalid key specs, but the provider does not replace full protocol validation/trust policy.
- Do not confuse `RSAPublicKeySpec` with a CA certificate, an identity-bound public key, or a valid signature. Successfully constructing a key object does not mean the key's source is trustworthy.
- Do not mirror this pattern with `RSAPrivateKeySpec` and print `d`, `p`, `q` to JSON/console. RSA private components must be treated as secret key material.

If the input is already standard SPKI DER, **prefer `X509EncodedKeySpec`** instead of parsing ASN.1 manually to extract `n`/`e`. That avoids bugs in lengths, algorithm/parameters, and formatting.

## 7. Java 17+ Example: EC and Ed25519 Also Use KeyFactory

`X509EncodedKeySpec` and `PKCS8EncodedKeySpec` are **format wrapper classes**, not exclusive to RSA. Many other public-key algorithms can use them if the JDK/provider implementation supports them and the bytes contain the right algorithm identifier.

The following example generates an EC key on `secp256r1` and an Ed25519 key, reconstructs them, and verifies signatures. It also intentionally feeds the EC public key into an RSA KeyFactory to illustrate **algorithm mismatch**.

Save as **`EcEdKeyConversionDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.spec.*;

public final class EcEdKeyConversionDemo {
    public static void main(String[] args) throws GeneralSecurityException {
        byte[] data =
                "Open standard key formats".getBytes(StandardCharsets.UTF_8);

        KeyPairGenerator ecGen = KeyPairGenerator.getInstance("EC");
        ecGen.initialize(new ECGenParameterSpec("secp256r1"));
        KeyPair ecPair = ecGen.generateKeyPair();

        KeyFactory ecFactory = KeyFactory.getInstance("EC");
        PublicKey ecPublic = ecFactory.generatePublic(
                new X509EncodedKeySpec(ecPair.getPublic().getEncoded()));
        PrivateKey ecPrivate = ecFactory.generatePrivate(
                new PKCS8EncodedKeySpec(ecPair.getPrivate().getEncoded()));

        Signature ecSigner = Signature.getInstance("SHA256withECDSA");
        ecSigner.initSign(ecPrivate);
        ecSigner.update(data);
        byte[] ecSignature = ecSigner.sign();
        ecSigner.initVerify(ecPublic);
        ecSigner.update(data);
        System.out.println("EC round-trip verify: "
                + ecSigner.verify(ecSignature));

        KeyPairGenerator edGen = KeyPairGenerator.getInstance("Ed25519");
        KeyPair edPair = edGen.generateKeyPair();
        KeyFactory edFactory = KeyFactory.getInstance("Ed25519");
        PublicKey edPublic = edFactory.generatePublic(
                new X509EncodedKeySpec(edPair.getPublic().getEncoded()));
        PrivateKey edPrivate = edFactory.generatePrivate(
                new PKCS8EncodedKeySpec(edPair.getPrivate().getEncoded()));

        Signature edSigner = Signature.getInstance("Ed25519");
        edSigner.initSign(edPrivate);
        edSigner.update(data);
        byte[] edSignature = edSigner.sign();
        edSigner.initVerify(edPublic);
        edSigner.update(data);
        System.out.println("Ed25519 round-trip verify: "
                + edSigner.verify(edSignature));

        boolean rejected = false;
        try {
            KeyFactory.getInstance("RSA").generatePublic(
                    new X509EncodedKeySpec(
                            ecPair.getPublic().getEncoded()));
        } catch (InvalidKeySpecException expected) {
            rejected = true;
        }
        System.out.println("Wrong key algorithm rejected: " + rejected);
    }
}
```

```bash
javac -encoding UTF-8 EcEdKeyConversionDemo.java
java EcEdKeyConversionDemo
```

Stdout on common JDK 17+ supporting EC/secp256r1 and Ed25519:

```text
EC round-trip verify: true
Ed25519 round-trip verify: true
Wrong key algorithm rejected: true
```

**Observations:**

- EC uses `KeyPairGenerator("EC")`, `ECGenParameterSpec("secp256r1")`, `KeyFactory("EC")`, and signature `SHA256withECDSA`. The curve name is a **parameter of the EC algorithm**, not the name of the KeyFactory.
- Ed25519 has `KeyPairGenerator("Ed25519")`, `KeyFactory("Ed25519")`, and `Signature("Ed25519")`. Do not convert Ed25519 into ECDSA or RSA by swapping factory strings.
- A raw 32-byte Ed25519 public key is **not** DER SPKI; raw seed/secret bytes are also **not** PKCS #8 DER. Importing raw keys requires the appropriate KeySpec/API or parser; do not stuff raw `byte[]` into `X509EncodedKeySpec`.
- `InvalidKeySpecException` in the final case shows that parsing a **valid SPKI structure** still requires the **matching algorithm**. This differs from `NoSuchAlgorithmException`, which occurs when Java cannot find an implementation of the `KeyFactory` itself.
- If an application uses a provider/HSM that disallows exporting keys or lacks a specific curve, `getEncoded()` may be unusable; do not fall back to another algorithm when policy requires Ed25519 or a specific EC curve.

## 8. Java 17+ Example: Importing a PEM Public Key

The `KeyFactory` API accepts **DER bytes**, not directly a string containing `-----BEGIN PUBLIC KEY-----`. We need to verify the PEM envelope, Base64-decode it, and construct an `X509EncodedKeySpec`.

The example below only supports **a single SPKI PEM public key generated by the program**. It does not accept certificates, private PEMs, PKCS #1 RSA keys, multiple PEM blocks, or every PEM formatting variant in the wild. A production parser should enforce size limits before decoding, strict input policies, and a trusted library if multiple formats must be supported.

Save as **`PublicPemImportDemo.java`**:

```java
import java.security.*;
import java.security.spec.*;
import java.util.*;

public final class PublicPemImportDemo {
    private static String toPem(PublicKey key) {
        String base64 =
                Base64.getMimeEncoder(64, new byte[]{(byte)'\n'})
                        .encodeToString(key.getEncoded());
        return "-----BEGIN PUBLIC KEY-----\n" + base64
                + "\n-----END PUBLIC KEY-----\n";
    }

    private static PublicKey fromPem(String pem, String algorithm)
            throws GeneralSecurityException {
        String header = "-----BEGIN PUBLIC KEY-----";
        String footer = "-----END PUBLIC KEY-----";
        String value = pem.replace("\r\n", "\n").strip();
        if (!value.startsWith(header) || !value.endsWith(footer)) {
            throw new IllegalArgumentException("Expected PUBLIC KEY PEM");
        }
        String base64 = value.substring(
                header.length(), value.length() - footer.length())
                .replaceAll("\\s", "");
        byte[] der = Base64.getDecoder().decode(base64);
        return KeyFactory.getInstance(algorithm)
                .generatePublic(new X509EncodedKeySpec(der));
    }

    public static void main(String[] args) throws GeneralSecurityException {
        KeyPairGenerator g = KeyPairGenerator.getInstance("RSA");
        g.initialize(2048);
        PublicKey key = g.generateKeyPair().getPublic();
        PublicKey restored = fromPem(toPem(key), "RSA");

        System.out.println("PEM import matches: "
                + Arrays.equals(key.getEncoded(), restored.getEncoded()));

        boolean rejected = false;
        try {
            fromPem("-----BEGIN CERTIFICATE-----\nAAA=\n"
                    + "-----END CERTIFICATE-----", "RSA");
        } catch (IllegalArgumentException ex) {
            rejected = true;
        }
        System.out.println("Certificate header rejected: " + rejected);
    }
}
```

```bash
javac -encoding UTF-8 PublicPemImportDemo.java
java PublicPemImportDemo
```

Stdout:

```text
PEM import matches: true
Certificate header rejected: true
```

**Why not use `Base64.getMimeDecoder()` and ignore all characters outside the alphabet?** An overly permissive decoder can silently swallow unexpected characters in the input; here the parser explicitly checks the header/footer and strips **whitespace** inside the body before calling `Base64.getDecoder()`. Even so, the example only illustrates a valid SPKI envelope and does not replace a hardened PEM parser implementing all RFC 7468 rules, size caps, and multi-block checks.

If the input is `-----BEGIN CERTIFICATE-----`, the right approach is to use `CertificateFactory.getInstance("X.509")` to read the certificate, call `certificate.getPublicKey()`, and then perform **certificate chain/trust validation** per application policy. Never simply rename the header from `CERTIFICATE` to `PUBLIC KEY`: the DER bytes are still a certificate, not SPKI.

## 9. KeySpec and Format Must Match Algorithm, Key Type, and Provider

A proper key import workflow is more than `Base64.decode` and `getInstance`. You should check the following conditions:

1. **What is the key source?** It could be a public SPKI file, private PKCS #8, certificate, JWK, keystore alias, or HSM handle. Each type needs the matching parser API.
2. **What is the key algorithm?** RSA, EC, Ed25519, X25519... `KeyFactory` must be chosen by algorithm; never substitute cipher/signature names.
3. **What is the key type?** Public keys go strictly through `generatePublic`, private keys through `generatePrivate`. Mathematical specs must also match the type.
4. **Is the encoding right?** DER SPKI, DER PKCS #8, Base64-wrapped PEM, PKCS #1, SEC1, or encrypted PKCS #8 are not interchangeable merely by renaming files.
5. **Is the provider capable and permitted?** Non-exportable keys cannot be forced to return bytes from `getEncoded()`; `translateKey` may be refused.
6. **Does the key satisfy security policy?** Check key size, curve, algorithm parameters, and usage; do not accept weak keys simply because the parser accepted them.
7. **Is the key source trusted?** Parsing a public key does **not** authenticate its owner. You need a certificate chain, trusted pinned fingerprint, trust store, or authenticated key exchange.
8. **How are private key export and storage restricted?** Do not expose private keys for debugging convenience; use keystores/KMS/HSM and approved key lifecycles.

### 9.1 KeyStore and CertificateFactory Do Not Replace KeyFactory

`KeyStore` stores/looks up keys and certificates by alias with appropriate protection; `CertificateFactory` reads certificate formats; `KeyFactory` converts key representations. They can be used together:

```text
Trusted KeyStore  --> Certificate --> getPublicKey() --> PublicKey
KeyStore alias    --> getKey(password) ----------------> PrivateKey/SecretKey
DER SPKI          --> X509EncodedKeySpec --> KeyFactory --> PublicKey
DER PKCS #8       --> PKCS8EncodedKeySpec --> KeyFactory --> PrivateKey
```

Receiving a `PrivateKey` object from `KeyStore.getKey` **does not require** exporting it and calling `KeyFactory.generatePrivate`. If the provider allows signing directly with that key handle, pass the key straight to `Signature`. Pointless export/import can break hardware security boundaries.

### 9.2 Certificates and Trust

Suppose a peer sends an SPKI public key and you import it successfully with `KeyFactory.generatePublic`. That proves the DER is valid and the provider understands the algorithm, **not that the peer actually owns the key**. An attacker can also generate a valid RSA key to trick an application into verifying signatures forged by that attacker. You must bind keys to identities via an authenticated channel, certificate verification, pinning, or a well-defined trust framework.

Avoid treating `PublicKey.getEncoded()` as a self-sufficient identifier across all contexts. If using fingerprints, standardize the exact encoding type, hash algorithm, and trust anchor/source. Mathematical equivalence does not automatically mean every provider exports **identical DER byte arrays**.

## 10. Handling Exceptions by Type

| Error | Where it occurs | Interpretation and handling |
| --- | --- | --- |
| `NoSuchAlgorithmException` | `KeyFactory.getInstance("RSA" / "EC" / "Ed25519")` | The algorithm has no implementation in available providers. Check JDK/providers and deployment policy; do not assume installing a library makes it compatible. |
| `NoSuchProviderException` | `getInstance(algorithm, "providerName")` overload | Provider name is not registered. Check provider registration and configuration. |
| `InvalidKeySpecException` | `generatePublic`, `generatePrivate`, `getKeySpec` | Spec does not match key type, invalid/unsupported DER, wrong algorithm, or spec cannot be exported. |
| `InvalidKeyException` | `translateKey` | Provider/factory cannot translate the provided key object. |
| `IllegalArgumentException` | PEM parser / `Base64.getDecoder().decode` and some validation APIs | Input violates envelope/base64 or invalid application argument. Do not assert all KeyFactory APIs throw the same exception. |
| `NullPointerException` | Null input to constructors/methods requiring non-null | Input contract bug; validate inputs before calling crypto APIs. |
| Error when using key after import | `Signature.initSign/initVerify` or `Cipher.init` | A parseable key object may still be unsuitable for the operation, provider, scheme, key usage, or policy. |

Layering recommendations:

- **At startup:** load configured algorithms/providers/keys; detect missing capabilities or bad keys; fail fast and preserve `cause` in secure logs.
- **When receiving external keys:** cap size before decoding; separate PEM syntax/Base64 errors from DER/spec errors and policy/chain validation errors. Return appropriate input errors without leaking sensitive stack traces.
- **When a private key is locked in an HSM:** do not request `getKeySpec(privateKey, RSAPrivateCrtKeySpec.class)` to "debug". Use only operations allowed by the provider.
- **When record formats change:** store version + algorithm identifier with a clear migration path; avoid randomly trying multiple parsers/algorithms, which makes errors hard to trace.
- **When changing providers:** test `getKeySpec`/`translateKey` capabilities in the real environment; do not assume all providers can translate keys back and forth.

### 10.1 An Error-Handling Pattern to Avoid

```java
// Anti-pattern: loses the root cause and can produce null in downstream layers.
try {
    return KeyFactory.getInstance("RSA")
            .generatePrivate(new PKCS8EncodedKeySpec(bytes));
} catch (Exception ex) {
    return null;
}
```

This is **illustrative code inside a method** (`bytes` and the return type are undeclared), **not a standalone Java program**. The proper approach is to validate inputs, separate parsing errors from configuration errors, preserve `cause` for investigation, and never return ambiguous `null`. Nor should you silently switch to another key algorithm just to "make it work".

## 11. Security Boundaries to Remember When Exporting and Importing Private Keys

**Nature of private keys:** If `privateKey.getEncoded()` returns PKCS #8 bytes, anyone who can read those bytes may be able to use the private key. Base64, PEM, `PKCS8EncodedKeySpec`, or a `byte[]` in the JVM does not encrypt it.

**Memory:** `PKCS8EncodedKeySpec` copies bytes on construction and may copy them on `getEncoded()`. Zeroing an original `byte[]` does not guarantee that copies on the heap, in key objects, or inside providers are gone. For high-assurance needs, prefer non-extractable keys in HSM/KMS, short lifetimes, and platform protection mechanisms.

**Encapsulated keys:** `Key.getEncoded()` can return `null`. This usually signals a key that is not allowed or unable to be exported, and should not be worked around with reflection or provider-specific serialized objects.

**Provider differences:** Some providers accept the same DER yet produce different key objects; some support only a subset of `KeySpec` classes; some require specific algorithm parameters. Always test on the exact target runtime and handle `InvalidKeySpecException`/`InvalidKeyException` explicitly.

**Trustworthiness:** Conversion only changes **representation**. It does not verify the key owner, check certificate revocation, automatically decrypt encrypted PKCS #8, or confirm a key was issued for the intended purpose.

## 12. Scenario-Based Self-Check

**Scenario A.** You receive a `-----BEGIN PUBLIC KEY-----` string and pass the entire string into `new X509EncodedKeySpec(pem.getBytes())`. Why is this wrong?  
**Solution:** The spec expects **DER bytes**, not Base64 text with header/footer. You must validate the PEM type, Base64-decode to obtain SPKI DER first, and then call `generatePublic`.

**Scenario B.** A file has the label `-----BEGIN CERTIFICATE-----`. Can you use `X509EncodedKeySpec`?  
**Solution:** Not directly; that is **certificate DER**, not SPKI DER. Use `CertificateFactory` to read the certificate, call `getPublicKey()`, and validate trust/chain per policy.

**Scenario C.** A `BEGIN RSA PRIVATE KEY` file is passed into `PKCS8EncodedKeySpec`, throwing `InvalidKeySpecException`. Is RSA missing?  
**Solution:** Not necessarily. That is usually **PKCS #1**, which differs from PKCS #8. You need to convert the format with a trusted parser/tool before building the key. Only suspect a missing factory if `KeyFactory.getInstance("RSA")` itself fails.

**Scenario D.** Code calls `KeyFactory.getInstance("SHA256withRSA")`.  
**Solution:** Wrong algorithm name category: `SHA256withRSA` is for `Signature`. To construct an RSA key, use `KeyFactory.getInstance("RSA")`.

**Scenario E.** A `PrivateKey` retrieved from an HSM has `getEncoded() == null`. How do you "fix" it?  
**Solution:** Do not try to export it. Verify the key handle and usage permissions, and perform `Signature.initSign(privateKey)` or allowed operations via the provider. Not every private key has exportable PKCS #8 bytes.

**Scenario F.** `KeyFactory.getKeySpec(publicKey, RSAPublicKeySpec.class)` extracts `n` and `e`. Can you reconstruct the private key from them?  
**Solution:** No. Public components do not contain enough information for the private key. `KeyFactory` does not solve recovering a private key from a public key.

**Scenario G.** An RSA private key imports successfully, yet verifying a partner's signature still fails.  
**Solution:** Importing a valid key does **not** guarantee it is the partner's key, nor that `Signature` is using the same scheme, data, or canonicalization. Check public key identity, signing algorithm, parameters, and signed bytes rather than blaming `KeyFactory` for every failure.

**Scenario H.** You want to construct an EC key using an `X509EncodedKeySpec` containing an Ed25519 public key. Will `KeyFactory.getInstance("EC")` figure it out automatically?  
**Solution:** No. Ed25519 is an algorithm with its own factory name; choose the right KeyFactory/provider and do not treat all elliptic curve keys as ECDSA/EC.

**Scenario I.** A tool produces an `ENCRYPTED PRIVATE KEY`, yet Java directly calls `generatePrivate(new PKCS8EncodedKeySpec(bytes))`.  
**Solution:** `PKCS8EncodedKeySpec` expects an unencrypted outer PKCS #8 private-key structure. You must run the proper encrypted PKCS #8 decryption flow first while protecting the password and memory.

## 13. Production Application Checklist

1. **Know the format:** SPKI/X.509 public, PKCS #8 private, certificate, PKCS #1, SEC1, or provider handle; whether an encryption wrapper is present.
2. **Choose the right KeyFactory algorithm:** `RSA`, `EC`, `Ed25519`, etc., based on a verified contract, not an arbitrary user-supplied string.
3. **Use the right spec:** `X509EncodedKeySpec` for SPKI public; `PKCS8EncodedKeySpec` for unencrypted PKCS #8 private; mathematical specs only when truly needed.
4. **Verify trust:** public key origin, certificate chain/pinning, key usage, and expiration; successful parsing does not prove identity.
5. **Bound inputs:** file length, PEM block count, Base64/DER structure, key size, algorithm, and parameters per policy.
6. **Protect private keys:** never log/commit/export casually; prefer `KeyStore`, KMS/HSM, and appropriate permissions.
7. **Test with real providers:** including `getEncoded()` returning `null`, `getKeySpec`/`translateKey` rejections, missing algorithms, and malformed key specs.
8. **Verify functionality:** e.g., sign/verify on expected key pairs; test valid, malformed, and mismatched-key inputs, without copying test secret keys into production.
9. **Maintain interoperability:** clearly define DER/PEM, algorithm identifiers, curves, key formats, and versions when exchanging keys across Java/OpenSSL/partners.

## Official Java Documentation

- [Java SE 21 — `KeyFactory`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyFactory.html): Key/KeySpec conversion directions, providers, `generatePublic`, `generatePrivate`, `getKeySpec`, `translateKey`.
- [Java SE 21 — `Key`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Key.html): `getAlgorithm`, `getFormat`, and `getEncoded`, including non-exportable encodings.
- [Java SE 21 — `X509EncodedKeySpec`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/spec/X509EncodedKeySpec.html): ASN.1 SubjectPublicKeyInfo public-key encoding.
- [Java SE 21 — `PKCS8EncodedKeySpec`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/spec/PKCS8EncodedKeySpec.html): PKCS #8 private-key encoding.
- [Java SE 21 — `RSAPublicKeySpec`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/spec/RSAPublicKeySpec.html) and [`RSAPrivateCrtKeySpec`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/spec/RSAPrivateCrtKeySpec.html): RSA mathematical components.
- [Java SE 21 — `CertificateFactory`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertificateFactory.html) and [`KeyStore`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.html): distinguishing certificate parsing and key storage.
- [RFC 7468 — Textual Encodings of PKIX Structures](https://www.rfc-editor.org/rfc/rfc7468.html): PEM envelopes for public/private keys/certificates.

**Remember:** `KeyFactory` helps **convert representations** of asymmetric keys, with `KeySpec` as either the input or output of conversion. Valid **SPKI/PKCS #8** format, the right algorithm, and the right provider are prerequisites for building a key; **trust, private-key protection, and usage permissions** must still be enforced separately.