# 8.6 Distinguishing DER, PEM, Raw Keys, Encrypted Keys, and Certificates

In Java Security/JCA, a file named `server.pem`, `public.der`, `private.key`, or `certificate.crt` does not by itself tell you what kind of key it contains, whether it is password-protected, or whether it is trusted. **DER, PEM, raw key, encrypted key, and certificate describe different dimensions of cryptographic data**. Confusing these dimensions often leads to `InvalidKeySpecException`, TLS failures, private-key leaks, or authenticating the wrong peer.

An RSA public key may reside in an ASN.1 **SubjectPublicKeyInfo (SPKI)** structure encoded as **DER**, then wrapped in **PEM** text with the label `-----BEGIN PUBLIC KEY-----`. An X.509 certificate is also typically DER-encoded and PEM-wrapped, yet carries the label `-----BEGIN CERTIFICATE-----`: inside it contains the public key *along with* subject, issuer, validity, extension fields, and a digital signature. A private key may be unencrypted PKCS#8 (`BEGIN PRIVATE KEY`), encrypted PKCS#8 (`BEGIN ENCRYPTED PRIVATE KEY`), or an RSA/EC-specific format.

This lesson explains from the byte layer up to the trust layer, recommends how to choose parsers and algorithms, provides a compilable/runnable Java 17+ example, and includes an anti-confusion checklist and key-protection practices.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the differences among **key material**, **data structures**, **binary encoding**, **text armor**, **encryption at rest**, and **certificates/trust**.
2. Identify SPKI, PKCS#8, PKCS#1, SEC 1, and X.509 certificate structures from **published conventions**, not merely file extensions.
3. Properly use Java APIs: `PKCS8EncodedKeySpec`, `X509EncodedKeySpec`, `KeyFactory`, `EncryptedPrivateKeyInfo`, `CertificateFactory`, `X509Certificate`, and `KeyStore`.
4. Understand why **PEM is not encryption**, **`X509EncodedKeySpec` does not accept certificates**, and **a public key does not prove identity**.
5. Distinguish an **encryption key** (a key used to encrypt) from an **encrypted key** (a key encrypted for protection) and a **wrapped key**.
6. Design key and certificate import/export flows that enforce algorithms, permissions, trust anchors, hostnames, rotation, and parser error handling.
7. Test DER ↔ PEM round-trips and demonstrate that recovered key pairs can sign/verify, without mistaking that for certificate validation.

## 2. Do Not Compare Things Belonging to Different Layers

Ask five questions before "converting formats":

| Question | Example answer | What not to infer |
| --- | --- | --- |
| **What object is this?** | Public key, private key, symmetric key, CSR, certificate | A `.pem` file does not specify the object |
| **What is its structure?** | SPKI, PKCS#8 PrivateKeyInfo, EncryptedPrivateKeyInfo, X.509 Certificate | An ASN.1 SEQUENCE is not enough to identify the type |
| **How are bytes serialized?** | DER per ASN.1; raw bytes per an algorithm standard | DER is not by default a certificate |
| **Is it wrapped in text/container?** | PEM/Base64, PKCS#12, JWK, OpenSSH | PEM does not automatically provide cryptographic protection |
| **Who has permissions and who is trusted?** | Key held in HSM; certificate chaining to an allowed CA | Successful parsing does not imply trust |

Relationship diagram:

```text
Key material or certificate information
  |
  +-- Raw bytes per algorithm specification (if raw representation is used)
  |
  +-- ASN.1 schema
        +-- SubjectPublicKeyInfo             [public key]
        +-- PrivateKeyInfo / OneAsymmetricKey [private key]
        +-- EncryptedPrivateKeyInfo           [encrypted private key]
        +-- Certificate                      [X.509 certificate]
        +-- RSAPublicKey / RSAPrivateKey     [RSA PKCS#1]
        +-- ECPrivateKey                     [SEC 1]
        |
        v
     DER binary bytes
        |
        +-- binary file per contract
        |
        +-- Base64 + PEM BEGIN/END labels -> text PEM file
```

The same **certificate** can exist in two files, one containing DER bytes and the other containing PEM of those exact DER bytes. Changing only the armor layer does **not** alter the certificate's validity or trustworthiness.

## 3. What Is DER?

**DER** (*Distinguished Encoding Rules*) is the canonical rule set for encoding an ASN.1 value into bytes per ITU-T X.690. Many key and certificate structures in the PKIX/PKCS ecosystem are specified in ASN.1; DER then represents those structures at the binary level.

ASN.1 describes the **data type/schema**, whereas DER describes the **encoding**. For example, SPKI includes an `AlgorithmIdentifier` and a field holding the public key. The PKCS#8 structure typically also has an algorithm identifier, yet holds the private key in a different designated field. An X.509 certificate has a complete certificate structure consisting of the signed `tbsCertificate` data, signature algorithm info, and signature.

DER uses tag/length/value (TLV) formatting rules with stricter canonical constraints than BER (*Basic Encoding Rules*). A tag byte of `0x30` can indicate an ASN.1 SEQUENCE, yet is **not a sufficient marker to distinguish SPKI, private key, or certificate** because all three can start with a SEQUENCE.

What DER does **not** do:

- Does not encrypt data for confidentiality: DER of an unencrypted PKCS#8 private key still exposes the private key.
- Does not tell you who owns a public key or whether the issuer is trustworthy.
- Does not replace certificate chain validation, algorithm policy, and authorization.
- Does not turn raw key bytes into PKCS#8/SPKI by prepending a few arbitrary bytes.
- Does not provide full self-describing metadata if you lack the expected ASN.1 schema.

Never call `new String(derBytes, StandardCharsets.UTF_8)` to "read" DER. Binary DER is not UTF-8 text. When debugging, use ASN.1 tools and hex while ensuring private keys are never exposed.

**BER/CER/DER:** there are multiple ASN.1 encoding rules. A parser might accept broader BER depending on the implementation, yet when a protocol specifies DER, **output and validation must follow DER**, especially for signed data. Proper conversion parses against the source schema and serializes per the target standard, rather than tweaking leading bytes by guesswork.

## 4. What Is PEM?

**PEM** in a key/certificate context is typically text containing **Base64 of a binary payload**, paired with BEGIN/END lines indicating the payload type. The example below is only a **diagram**, not a valid private/public key to copy and run directly:

```text
-----BEGIN PUBLIC KEY-----
Base64 of a valid SPKI DER structure
-----END PUBLIC KEY-----
```

To create a real file, you must obtain valid SPKI DER bytes, Base64-encode them properly, and use the matching label. The runnable Java example in section 11 does this from a generated key.

PEM typically uses armor defined by RFC 7468 and ecosystem conventions. Some formats have different wrapping structures such as OpenSSH; **do not assume every file with BEGIN/END is PKCS#8 or SPKI**.

Key properties to remember:

- PEM is convenient in text configs/emails, yet Base64 **is not security encryption**; anyone who can read an unencrypted PEM can decode the private key.
- Labels carry meaning: `BEGIN PRIVATE KEY` ≠ `BEGIN ENCRYPTED PRIVATE KEY` ≠ `BEGIN CERTIFICATE`.
- A PEM file may contain **multiple blocks**, such as a certificate chain. Parsers must handle the exact count, order, and block types required by the protocol.
- Extensions `.pem`, `.crt`, `.cer`, `.key` are less reliable than **actual structure and format contracts**.
- LF, CRLF, whitespace, and legacy PEM headers can vary; simple line-splitting educational code is usually insufficient for arbitrary external inputs.
- Never rename BEGIN/END labels to turn a private key payload into a public key or certificate. Changing the label does not alter the inner structure.

### Comparing DER and PEM

| Criterion | DER | PEM |
| --- | --- | --- |
| Representation | Binary bytes per ASN.1 rules | Text armor containing Base64 |
| Possible contents | SPKI, PKCS#8, X.509 certificate, etc. | Those same objects wrapped in the proper labels |
| Built-in confidentiality | No | No |
| Easy to display in terminal | No | Yes |
| Reading in Java | Choose parser matching the structure | Decode armor then choose parser matching the structure |
| DER ↔ PEM conversion | Preserves DER payload if armored/unarmored properly | Does not convert key/certificate types |

If an X.509 DER certificate is PEM-armored, the **DER payload** itself represents the certificate; do not hash the newlines/armor and confuse it with the DER certificate fingerprint.

## 5. Raw Keys: No Universal Schema

A **raw key** consists of the key material bytes in an **algorithm-specific representation**, rather than a generic wrapper structure like SPKI/PKCS#8. The meaning of raw bytes varies by algorithm, library, and protocol:

| Case | What raw material usually represents | Information still needed |
| --- | --- | --- |
| AES-256 | 32-byte symmetric key | Algorithm, usage, key ID, entropy source, permissions |
| Ed25519 public | 32-byte public key encoding per RFC 8032 | Algorithm/format, policy, trust binding |
| Ed25519 private | Some protocols use a 32-byte seed; some libraries use another representation | Definition of seed vs. private encoding; do not treat as PKCS#8 |
| X25519 | 32-byte coordinate/secret scalar per RFC 7748 | Public/private, endianness, clamping/handling per API |
| EC P-256 public | Point on curve in compressed/uncompressed form | Curve/domain parameters and point validation |
| RSA public | Two integers `n` and `e`, or an algorithm-specific `RSAPublicKey` structure | Modulus/exponent, padding/signature scheme, key policy |
| RSA private | RSA components, sometimes PKCS#1 `RSAPrivateKey` structure | Parameter consistency check, CRT, length, protection |

**Having the same 32 bytes does not mean two keys are interchangeable.** A raw AES-256 key and a raw Ed25519 public key may be the same size, yet represent completely different cryptographic objects and operations.

Raw keys are not inherently insecure, yet are very easy to misinterpret when transmitted without algorithm/version/curve/usage metadata. Only use raw representations when a protocol specifies them precisely and implement parsers to that exact standard.

### Raw Keys Differ from EncodedKeySpec

`PKCS8EncodedKeySpec` requires a **PKCS#8 private-key structure**, not any raw secret scalar/seed directly. `X509EncodedKeySpec` requires an **SPKI structure**, not any raw public point directly. If you pass 32 raw Ed25519 bytes into `new X509EncodedKeySpec(rawBytes)`, the Java constructor creating the spec object does not validate the bytes; `KeyFactory.generatePublic` will typically reject it for lacking the right wrapper.

With AES, `new SecretKeySpec(rawAesBytes, "AES")` follows a different model: it wraps existing bytes as a **symmetric key**. It does not prove the key has sufficient entropy or proper authorization. For RSA/EC from raw components, Java offers algorithm-specific specs such as `RSAPublicKeySpec`, `RSAPrivateCrtKeySpec`, `ECPublicKeySpec`, and `ECPrivateKeySpec`, which require complete parameters and validation.

## 6. SPKI, PKCS#8, PKCS#1, and SEC 1: Only the Right Structure Works with the Right API

Important identification table:

| Structure | Object | Common PEM label | Java 17 |
| --- | --- | --- | --- |
| **SubjectPublicKeyInfo (SPKI)** | Public key with AlgorithmIdentifier | `PUBLIC KEY` | `X509EncodedKeySpec` then `KeyFactory.generatePublic` |
| **PKCS#8 PrivateKeyInfo / OneAsymmetricKey** | Private key with algorithm info | `PRIVATE KEY` | `PKCS8EncodedKeySpec` then `KeyFactory.generatePrivate` |
| **PKCS#8 EncryptedPrivateKeyInfo** | Encrypted private key with encryption parameters | `ENCRYPTED PRIVATE KEY` | Decrypt via appropriate provider first, then parse private key |
| **PKCS#1 RSAPublicKey** | RSA public modulus + exponent | `RSA PUBLIC KEY` | Not SPKI; must parse/convert properly |
| **PKCS#1 RSAPrivateKey** | RSA private key in algorithm-specific structure | `RSA PRIVATE KEY` | Not PKCS#8; must parse/convert properly |
| **SEC 1 ECPrivateKey** | Traditional EC private key | `EC PRIVATE KEY` | Not PKCS#8; must parse/convert properly |
| **X.509 Certificate** | Public key + subject/issuer/validity/extensions/signature | `CERTIFICATE` | `CertificateFactory.getInstance("X.509")` |

**Watch out for confusing names:**

- `X509EncodedKeySpec` is not a certificate parser. It represents **SPKI public key encoding**. The "X.509" name reflects the syntax origin of public-key information, not that the input parameter is a full X.509 certificate.
- `PKCS8EncodedKeySpec` is used for **unencrypted private keys**. `BEGIN ENCRYPTED PRIVATE KEY` is a different container and must be decrypted according to the right format/algorithm/password first.
- `RSA PRIVATE KEY` may be unencrypted legacy PKCS#1, or carry legacy PEM encryption headers depending on the header lines; do not assume a label containing "PRIVATE" decodes as PKCS#8.
- `PUBLIC KEY` (SPKI) differs from `RSA PUBLIC KEY` (PKCS#1). Both can describe the same mathematical RSA public key, yet their **bytes and schemas differ**.

### Connection to Ed25519, X25519, and EC

RFC 8410 defines algorithm identifiers/encodings for Ed25519/Ed448/X25519/X448 keys inside SPKI/PKCS#8. If a protocol supplies a **raw 32-byte Ed25519 public key**, convert it per the standard rather than prepending an arbitrary "fixed prefix". Similarly, PKCS#8 Ed25519 private key data is not simply a 32-byte seed Base64-wrapped under `PRIVATE KEY`.

For EC, an encoded point lacking domain parameters can cause curve mismatches. You must specify the representation standard, public-key validation, and algorithm rather than assuming every EC point belongs to P-256.

## 7. "Encryption Key" vs. "Encrypted Key"

The phrase "encryption key" is sometimes confused with "encrypted key": an **encryption key** is a key used to encrypt data, whereas in file-format discussions an **encrypted key** is a key itself encrypted for protection at rest/in transit.

1. **Encryption key / decryption key:** a key used by an algorithm, such as an AES key or an RSA public/private key for encryption/decryption under an allowed scheme. Depending on type, it may be stored as raw, DER, PEM, or inside an HSM.
2. **Encrypted private key:** a blob holding an encrypted private key, such as PKCS#8 `EncryptedPrivateKeyInfo`, opened with a password or matching key mechanism per algorithm and policy. You cannot use a key's ciphertext directly as a `PrivateKey` object.
3. **Wrapped key:** a key wrapped by a *key encryption/wrapping key (KEK)* or a KMS wrapping operation, such as AES Key Wrap or envelope encryption. It is not by default PKCS#8 nor does it use the same PEM label.
4. **Certificate:** a certificate contains a **public key**, not a private key; it does not "encrypt the private key" and does not replace protecting the real key.

Always write explicitly "encryption key" (key used to encrypt), "encrypted key" (key that has been encrypted), or "wrapped key" in technical documentation to avoid assigning the wrong API or access permissions.

## 8. Encrypted PKCS#8: Not Synonymous with PEM

An unencrypted PKCS#8 private key typically takes the form:

```text
PrivateKeyInfo
  -> version + AlgorithmIdentifier + privateKey data
  -> DER bytes
  -> optional PEM armor "PRIVATE KEY"
```

When protecting a private key at rest with a password/secret:

```text
PrivateKeyInfo DER
  -> encryption/KDF/protection algorithm + parameters
  -> EncryptedPrivateKeyInfo (algorithmIdentifier, encryptedData)
  -> DER bytes
  -> optional PEM armor "ENCRYPTED PRIVATE KEY"
```

**Security lies in the algorithm and password/key management**, not in adding PEM armor. A weak password can be brute-forced offline if the blob falls into an attacker's hands. Moreover, an encrypted key does not by itself state who is authorized to use it or whether the algorithm is sufficiently strong.

### Factors to Understand When Opening an Encrypted Key

- **KDF and parameters:** salt, iteration count, PRF algorithm, or other profile; choose appropriately for your workload and current recommendations.
- **Protection algorithm:** pick a strong one; avoid weak legacy profiles unless strictly necessary. Know whether the format provides authenticated encryption or only encryption+padding.
- **Provider compatibility:** Java has `EncryptedPrivateKeyInfo`, `Cipher`, and `SecretKeyFactory`, yet PBES2 encodings/algorithm names/parameters between OpenSSL and JDK/providers can differ; do not assume every OpenSSL file opens with a generic JCA call.
- **Password source:** secure input or secret manager; avoid hardcoding, CLI history, or logs. With KMS/HSM, there may never be a raw private key copy in the application.
- **Validation:** after decrypting, validate private key structure, algorithm, and policy. Never treat decrypted bytes as a safe key regardless of format.
- **Legacy PEM encryption:** some `BEGIN RSA PRIVATE KEY` files carry PEM headers `Proc-Type: 4,ENCRYPTED`, `DEK-Info`. That is not PKCS#8 `BEGIN ENCRYPTED PRIVATE KEY`. Use a parser/migration tool that understands the exact format.

### OpenSSL Command Examples (CLI Illustration, Not Java)

Suppose you have a valid private key in `private.pem` and a suitable OpenSSL installation:

```bash
# Extract SPKI PEM public key from private key
openssl pkey -in private.pem -pubout -out public.pem

# Encrypt private key into encrypted PKCS#8; the tool prompts for a password
openssl pkcs8 -topk8 -in private.pem -out private-encrypted.pem \
  -v2 aes-256-cbc -v2prf hmacWithSHA256 -iter 200000

# Read certificate metadata without needing the private key
openssl x509 -in certificate.pem -noout -subject -issuer -dates
```

These commands require valid input files, permissions, and system policy compliance. The iteration count is illustrative, not a permanent recommendation for every workload and threat model. AES-CBC in this PBE configuration does not equal a full authenticated AEAD envelope. Never pass passwords in `argv` or commit an encrypted private key with a weak password thinking "it's encrypted so it's safe".

## 9. X.509 Certificate: A Public Key with Signed Assertions

An X.509 certificate holds a public key in an SPKI structure *and* many assertion fields about subject, issuer, validity, and usage. Structurally, a certificate includes the signed portion `tbsCertificate`, signature algorithm info, and signature bits.

| Field | Meaning |
| --- | --- |
| Serial number, version | Issuer-managed serial number and structure version |
| Subject, Issuer | Issued entity and issuing/signing entity |
| NotBefore / NotAfter | Validity window of the certificate |
| SubjectPublicKeyInfo | Public key along with algorithm identifier |
| Subject Alternative Name (SAN) | DNS/IP/other identifiers, especially critical for TLS hostname checks |
| Key Usage / Extended Key Usage | Permitted purposes for the certificate and key |
| Basic Constraints | Whether it is a CA, path length limits |
| Issuer signature | Allows verifying certificate data was not altered using the issuer's public key per the trust model |

**A certificate does not carry the corresponding private key.** The private key stays on the server, HSM/KMS, or protected keystore; clients receive the certificate/public key for protocol authentication.

### Being Parseable Is Not Trust

Separate three questions:

1. **Valid parse:** `CertificateFactory` constructs an `X509Certificate` object from DER/PEM certificate bytes.
2. **Does the certificate signature match a specific issuer public key?** `certificate.verify(issuerPublicKey)` checks the signature against the specified key, which by itself does not prove the issuer key is trusted.
3. **Can the subject be trusted to perform this task?** You need **PKIX path validation to an authorized trust anchor**, validity checks, algorithm constraints, basic constraints, key usage/EKU, revocation per policy, and for HTTPS, **hostname/SAN matching**.

A self-signed certificate can verify its own signature; that does **not** put it into a truststore. An expired certificate still parses cleanly. A certificate whose Subject looks just like a company's name does not constitute proof of identity.

Java uses `CertificateFactory`, `CertPathValidator`, `PKIXParameters`, and JSSE/`TrustManager` components to verify trust. For normal HTTPS, prefer a trusted client/TLS stack with hostname verification enabled rather than rebuilding PKIX logic from a few `verify` calls.

### CSR vs. Certificate

`BEGIN CERTIFICATE REQUEST` is a CSR/PKCS#10: a request for a CA to issue a certificate, containing a public key and a signature proving possession of the private key. A CSR is **not yet a CA-issued certificate**. A CA-issued certificate has its own issuer, validity period, and signature/usage semantics. Never use a CSR in place of a certificate to authenticate a TLS peer.

## 10. PKCS#12/PFX and Other Formats

Many systems store private keys + certificate chains in **PKCS#12** (`.p12`/`.pfx`), a **container** capable of holding multiple entries, password protection, and metadata. It is neither a plain SPKI DER file nor a single PEM certificate. In Java, `KeyStore.getInstance("PKCS12")` reads entries when given appropriate permissions/passwords.

Other formats requiring dedicated recognition:

- **OpenSSH:** `BEGIN OPENSSH PRIVATE KEY` and public-key lines like `ssh-ed25519 AAAA...` belong to the SSH format, not PKCS#8/SPKI PEM by default.
- **JWK/JWKS:** keys represented in JSON/JSON Web Key with `kty`, `crv`, `n`, `e`, or `x` depending on type; Base64url values do not turn JSON into DER.
- **Legacy PKCS#1 / SEC 1:** traditional RSA/EC keys, convertible to PKCS#8 using schema-aware tools; merely changing `BEGIN` is wrong.
- **PEM certificate chain:** multiple `CERTIFICATE` blocks in one file, requiring identification of leaf/intermediate/anchor and policy checks. Never treat a peer-sent root as a trust anchor automatically.

With PKCS#12, the private key still needs protection even when the container is password-protected: the file could be copied and attacked offline, and a certificate chain inside the container is not automatically a trusted chain.

## 11. Complete Java 17+ Example: SPKI/PKCS#8 DER ↔ PEM

The following program generates an **RSA** pair for demonstration, exports the private key as **PKCS#8 DER** and public key as **SPKI DER**, builds PEMs, imports them back with `KeyFactory`, and verifies a signature. It intentionally **does not create a certificate**: an ASN.1 SPKI key is not an X.509 certificate.

Save the file as **`KeyFormatsDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;
import java.util.Base64;

public class KeyFormatsDemo {
    static String toPem(String label, byte[] der) {
        String b64 = Base64.getMimeEncoder(64, new byte[] {'\n'})
                .encodeToString(der);
        return "-----BEGIN " + label + "-----\n"
                + b64 + "\n-----END " + label + "-----\n";
    }

    // A deliberately narrow parser for one PEM block produced by toPem.
    static byte[] fromPem(String pem, String expectedLabel) {
        String begin = "-----BEGIN " + expectedLabel + "-----";
        String end = "-----END " + expectedLabel + "-----";
        String[] lines = pem.replace("\r\n", "\n").split("\n");
        if (lines.length < 3 || !begin.equals(lines[0])
                || !end.equals(lines[lines.length - 1])) {
            throw new IllegalArgumentException("Wrong PEM label or boundaries");
        }
        StringBuilder base64 = new StringBuilder();
        for (int i = 1; i < lines.length - 1; i++) {
            if (!lines[i].matches("[A-Za-z0-9+/=]+")) {
                throw new IllegalArgumentException("Invalid Base64 line");
            }
            base64.append(lines[i]);
        }
        return Base64.getDecoder().decode(base64.toString());
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();

        byte[] privateDer = pair.getPrivate().getEncoded();
        byte[] publicDer = pair.getPublic().getEncoded();
        String privatePem = toPem("PRIVATE KEY", privateDer);
        String publicPem = toPem("PUBLIC KEY", publicDer);

        KeyFactory factory = KeyFactory.getInstance("RSA");
        PrivateKey privateKey = factory.generatePrivate(
                new PKCS8EncodedKeySpec(fromPem(privatePem, "PRIVATE KEY")));
        PublicKey publicKey = factory.generatePublic(
                new X509EncodedKeySpec(fromPem(publicPem, "PUBLIC KEY")));

        Signature signature = Signature.getInstance("SHA256withRSA");
        byte[] message = "Format != trust".getBytes(StandardCharsets.UTF_8);
        signature.initSign(privateKey);
        signature.update(message);
        byte[] signed = signature.sign();

        signature.initVerify(publicKey);
        signature.update(message);
        boolean verified = signature.verify(signed);

        System.out.println("Private format: " + pair.getPrivate().getFormat());
        System.out.println("Public format: " + pair.getPublic().getFormat());
        System.out.println("Private label: " + privatePem.split("\n")[0]);
        System.out.println("Public label: " + publicPem.split("\n")[0]);
        System.out.println("Private DER SEQUENCE tag: " + (privateDer[0] == 0x30));
        System.out.println("Public DER SEQUENCE tag: " + (publicDer[0] == 0x30));
        System.out.println("Private DER round trip: "
                + Arrays.equals(privateDer, privateKey.getEncoded()));
        System.out.println("Public DER round trip: "
                + Arrays.equals(publicDer, publicKey.getEncoded()));
        System.out.println("Signature valid: " + verified);
        try {
            fromPem(publicPem, "CERTIFICATE");
            System.out.println("Certificate label accepted: true");
        } catch (IllegalArgumentException e) {
            System.out.println("Certificate label accepted: false");
        }
    }
}
```

Compile/run with **JDK 17 or higher**:

```bash
javac --release 17 KeyFormatsDemo.java
java KeyFormatsDemo
```

**Verified stdout:**

```text
Private format: PKCS#8
Public format: X.509
Private label: -----BEGIN PRIVATE KEY-----
Public label: -----BEGIN PUBLIC KEY-----
Private DER SEQUENCE tag: true
Public DER SEQUENCE tag: true
Private DER round trip: true
Public DER round trip: true
Signature valid: true
Certificate label accepted: false
```

### Example Analysis

1. `getEncoded()` on exportable software keys created by the provider in the demo returns bytes per `getFormat()`. `PKCS#8` is private encoding, and `X.509` in `PublicKey.getFormat()` is **SPKI public-key encoding**, not a certificate.
2. `toPem` Base64-encodes DER and adds the proper label. There is no password-based encryption in this step. The generated private PEM file remains a **secret to protect**.
3. `fromPem` is *deliberately limited*: a single block, exact label, validated Base64 lines. This is **not a full PEM parser** for partner files; production uses RFC 7468-compliant libraries/logic with limits on size/headers and block count.
4. `KeyFactory.getInstance("RSA")` parses both structures properly via `PKCS8EncodedKeySpec` and `X509EncodedKeySpec`. If private DER is replaced with encrypted PKCS#8 or raw PKCS#1, this does **not apply directly**.
5. `Signature` only confirms the reconstructed key pair can sign/verify on the exact message bytes. It does **not** prove a third party or certificate chain is trustworthy.
6. Both DER byte arrays in the demo start with `0x30` because both are ASN.1 SEQUENCEs, yet they follow **two different schemas**. Never use the leading tag as a parser-type detector.
7. A `PUBLIC KEY` PEM fails a parser expecting the `CERTIFICATE` label; the right label is only one step—using certificates still requires a certificate parser and trust policy.
8. The example uses RSA-2048 for broad runnability, not to dictate that every use case must use RSA-2048; algorithms, sizes, and full lifecycles must follow policy.

For non-exportable HSM/KMS keys, `getEncoded()` may return `null`. Do not treat that as an error to bypass; instead use provider-permitted key handles and signing/decryption APIs.

## 12. Java: Parsing X.509 Certificates with the Right API

The snippet below **illustrates code inside a method** with proper imports and exception handling; assume `certificate.pem` exists and holds a syntactically valid X.509 certificate:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PublicKey;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

try (InputStream input = Files.newInputStream(Path.of("certificate.pem"))) {
    CertificateFactory factory = CertificateFactory.getInstance("X.509");
    X509Certificate certificate =
            (X509Certificate) factory.generateCertificate(input);
    PublicKey key = certificate.getPublicKey();
    String subject = certificate.getSubjectX500Principal().getName();
    String issuer = certificate.getIssuerX500Principal().getName();

    // Parsing, extracting key/subject/issuer do NOT establish trust.
}
```

Returning a `PublicKey` from `getPublicKey()` does not replace chain validation. If this is a TLS endpoint certificate, check the trust anchor, chain, SAN/hostname, validity period, and usage policy via JSSE or standard PKIX validation. `certificate.checkValidity()` only checks the validity dates; `certificate.verify(somePublicKey)` only checks the signature against that key, without proving `somePublicKey` belongs to a trusted issuer.

### Distinguishing Certificate DER and PEM

Both forms can contain **the exact same certificate**:

```text
cert.der    = DER bytes of the X.509 Certificate
cert.pem    = BEGIN CERTIFICATE + Base64 of those exact DER bytes + END CERTIFICATE
```

Converting PEM ↔ DER does **not** grant extra trust. A certificate fingerprint normally hashes the **DER certificate bytes**, not the line breaks and PEM armor. If a certificate file is swapped, signatures and trust paths must be re-validated per trust policy.

## 13. Java: A PKCS#12 Keystore Is Not a Private-Key PEM

A service may receive an identity as `identity.p12` containing a private key and certificate chain. Illustrative Java API usage (not a standalone program; requires `password` and `alias` from trusted configuration and exception handling):

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.Key;
import java.security.KeyStore;
import java.security.cert.Certificate;

KeyStore store = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(Path.of("identity.p12"))) {
    store.load(in, password);
}
Key privateKey = store.getKey(alias, password);
Certificate[] chain = store.getCertificateChain(alias);
```

Do not assume every PKCS#12 contains a private key; entries may be certificates or keys depending on configuration. Having a private key and certificate chain in the same container does not mean the chain is **trusted**; the receiving side must still run required validation rather than trusting a peer-sent root as a CA.

The container password protects contents at rest per provider/profile and is **not an application data encryption key**. With non-exportable HSM/KMS keys, a service typically references a key handle and keeps the certificate chain separately without exporting the private key into a `.p12`.

## 14. Workflow for Identifying Files and Choosing a Parser

First establish the **data source contract**, then inspect the actual input:

```text
Does input have BEGIN/END lines?
  |
  +-- Yes:
  |   |
  |   +-- PUBLIC KEY            -> SPKI DER -> KeyFactory / X509EncodedKeySpec
  |   +-- PRIVATE KEY           -> PKCS#8 DER -> KeyFactory / PKCS8EncodedKeySpec
  |   +-- ENCRYPTED PRIVATE KEY -> decrypt outer PKCS#8 first
  |   +-- CERTIFICATE           -> X.509 CertificateFactory + trust validation
  |   +-- RSA/EC PRIVATE KEY    -> separate legacy parser / proper conversion
  |   +-- OPENSSH ...           -> SSH format parser
  |
  +-- No:
      |
      +-- Binary DER SPKI/PKCS#8/Certificate -> schema-matching parser
      +-- Raw key bytes                     -> algorithm-specific spec/format
      +-- PKCS#12                           -> PKCS12 KeyStore
      +-- JWK/JWKS JSON                     -> JWK parser + policy
```

**Do not guess solely from file extensions.** An ASN.1 DER blob holding a certificate might use `.cer`, `.crt`, or `.der`; a `.pem` file might hold multiple certificate blocks. When receiving untrusted input:

- Bound input size before Base64 decoding or ASN.1 parsing; limit block count, structural depth, and processing time.
- Reject labels outside an allowlist and algorithm OIDs/sizes/curves that violate policy.
- If an SPKI public key is expected, reject certificates or PKCS#1 RSA public keys unless specified and handled by a dedicated parser.
- If a certificate is required, do not stop at parsing—validate chain, identity, and usage.
- If a private key is required, control permissions and unlocking/storage, avoiding unnecessary exposure in logs/heap.
- If multiple blocks exist, follow a format specifying **exactly how** to select leaf/intermediate and private keys rather than grabbing the first block arbitrarily.

## 15. Common Java Errors and How to Fix Them

| Symptom | Likely cause | How to resolve |
| --- | --- | --- |
| `InvalidKeySpecException` reading `RSA PRIVATE KEY` with `PKCS8EncodedKeySpec` | PKCS#1 RSA private differs from PKCS#8 | Use a standard schema parser/converter |
| `InvalidKeySpecException` passing 32-byte raw Ed25519 public key to `X509EncodedKeySpec` | Raw key lacks SPKI wrapper | Use a matching raw-key API or convert per RFC 8410 |
| `CertificateFactory` rejects `PUBLIC KEY` | SPKI public key is not an X.509 certificate | `KeyFactory` for SPKI; `CertificateFactory` for certificates |
| Opening `ENCRYPTED PRIVATE KEY` as `PRIVATE KEY` | `EncryptedPrivateKeyInfo` has not been decrypted | Use the matching password/algorithm/provider |
| OpenSSL encrypted key fails in current Java provider | Different or unsupported PBES2/algorithm identifiers/parameters | Check compatibility or migrate with safe tooling |
| `getEncoded() == null` | Key is non-exportable due to HSM/provider | Use the key handle to perform crypto operations |
| Certificate parses, yet HTTPS fails | Invalid chain/SAN/hostname/expiry/EKU/trust policy | Run proper PKIX/endpoint identification checks |
| Signature verification fails after key conversion | Wrong key pair, algorithm, message bytes, or scheme | Verify keys and signed bytes before blaming PEM |
| Changing only the PEM label causes parser failure | Inner ASN.1 payload does not match label | Actually parse and re-serialize into target structure |
| PKCS#12 opens, yet expected private key alias is missing | Different container/alias/entry than expected | List/inspect entries per policy and permissions |

Never resolve trust errors by disabling TLS verification, disabling hostname verification, blindly adding arbitrary certificates to a truststore, or falling back to weak algorithms. Never resolve key format errors by printing raw private keys to logs to inspect them.

## 16. Operations: Key Lifecycle and Certificate Lifecycle

**Private key:**

1. Generate with a trusted CSPRNG/provider or HSM/KMS per algorithm/length policy.
2. Keep confidential and restrict export; if file-stored, use ACLs, strong private-key encryption/passwords, backups, and auditing.
3. Never store plaintext private keys in source control, issue trackers, chat, or unprotected configs.
4. Use key IDs/versions to manage rotation; never mix secret key material with public metadata.
5. During conversion/backup, protect temporary files and delete per procedure; converting to PEM does not encrypt them.
6. Separate encryption keys and signing keys; never reuse one key across protocols not designed for it.
7. If private key compromise is suspected, execute revocation/rotation and reissue required certificates.

**Certificate and public key:**

1. Verify origin via chain/trust anchor or pinning with a proper lifecycle; never trust simply because parsing succeeded.
2. Validate SAN/hostname and intended key usage per application; check validity and revocation per policy.
3. Verify public/private key correspondence when deploying server identity; certificates do not hold private keys.
4. Automate expiry/renewal monitoring in operations without leaking private keys externally.
5. When converting DER ↔ PEM, preserve exact bytes and re-check format; do not mistake conversion for trust validation.
6. For CSRs, verify requests and issuance authorization; a CSR is not an issued certificate.

**Key wrapping/containers:**

1. Know clearly where the key encryption key (KEK) and data encryption key (DEK) reside, protecting them with KMS/HSM where appropriate.
2. Never treat an encrypted blob as an unlocked private key; it must go through authorized decrypt/unwrap first.
3. Version KDF/algorithms and test interoperability prior to rotation/migration.
4. Prevent profile downgrade or accepting disallowed keys specified by a request.
5. Never pass passwords on command lines or in logs; never confuse a container password with an algorithm key.

## 17. Recommended Technical Test Suite

| Test | Input | Expected result |
| --- | --- | --- |
| PKCS#8 round trip | Exportable RSA private key → DER → PEM → DER | DER bytes and parsed key match |
| SPKI round trip | RSA public key → DER → PEM → DER | DER bytes and parsed key match |
| Sign/verify | Parsed PKCS#8 private and SPKI public | Signature verifies on exact message |
| Wrong PEM label | SPKI `PUBLIC KEY` fed to parser expecting `CERTIFICATE` | Rejected |
| PKCS#1/PKCS#8 confusion | `RSA PRIVATE KEY` fed to PKCS#8 parser | Rejected / not parsed under wrong schema |
| Raw Ed25519 vs. SPKI | Raw bytes per RFC 8032 | Not parsed as SPKI when wrapper is missing |
| Encrypted PKCS#8 | Valid/invalid password, policy KDF/algorithm | Unlocks only with valid credentials/password; errors handled safely |
| Certificate parse | X.509 DER and PEM of the same certificate | Both parse; public key/SPKI match |
| Certificate trust | Self-signed not in truststore | Parses, yet is not automatically trusted |
| Hostname | Certificate for DNS A used to access DNS B | Endpoint identification rejects |
| Expired certificate | Certificate outside validity window | Rejected per policy even though ASN.1 parses |
| Input bounds | Oversized PEM/ASN.1 or excessive blocks | Rejected early per quota |
| PKCS#12 container | Matching entry/cert chain/password | Retrieves right entry without blindly trusting chain |
| Non-exportable key | Hardware/provider key with `getEncoded() == null` | Uses handle without attempting export |
| Cross-language format | Java and OpenSSL sharing SPKI/PKCS#8 | Parses and cross-signs/verifies per standard |

**Trust distinction test:** let the application parse a self-signed certificate and verify it against the public key extracted from that same certificate. Mathematical success must not promote the peer to trusted. Thoroughly test trust anchors/chains, SANs, and authorization.

## 18. Practice Exercises

### Exercise 1 — Reading Labels and Selecting APIs

You receive five data sources: `BEGIN PUBLIC KEY`, `BEGIN PRIVATE KEY`, `BEGIN ENCRYPTED PRIVATE KEY`, `BEGIN CERTIFICATE`, and `BEGIN RSA PRIVATE KEY`. For each source, identify the payload/schema, whether it definitely contains a private key, whether a password is involved, the right Java parser/KeySpec, and risks if received from an untrusted client.

### Exercise 2 — Running KeyFormatsDemo

Compile with `javac --release 17`. Explain why the public format displays `X.509` even though the program never creates a certificate. Try changing the public key's PEM label to `CERTIFICATE` without altering the DER, and explain why that is not a valid conversion.

### Exercise 3 — Migrating Legacy RSA Keys

A partner sends an unencrypted `BEGIN RSA PRIVATE KEY`. Design a migration workflow to encrypted PKCS#8: select a standard parser, bound inputs, verify matching public key, encrypt with policy-compliant password/algorithm, protect temporary files, test compatibility, and track rotation. Specify where secrets must never be logged.

### Exercise 4 — Raw Ed25519

A protocol returns a 32-byte Ed25519 public key. You need to verify with Java JCA. Document the byte input standard, how to build the public-key object or SPKI via an appropriate spec, the algorithm allowlist, and how to establish **which party owns the key** (trust binding) before verifying messages.

### Exercise 5 — Certificate with a Spoofed Name

An endpoint sends a self-signed certificate whose Subject lists a company name and whose public key works normally. Why are `getPublicKey()` and `verify(ownPublicKey)` still insufficient to trust the API? Describe trust anchor, chain, hostname/SAN, validity, KU/EKU, revocation policy, and task authorization.

### Exercise 6 — Operating Server Keys + Certificates

Compare three options: (a) `PRIVATE KEY` PEM + certificate PEM, (b) password-protected PKCS#12, (c) HSM/KMS non-exportable key + certificate chain. Analyze deployment, backup, rotation, permissions, and secret-exposure risks. When a certificate expires, why doesn't the private key's algorithm/format necessarily have to change, yet rotation policy still applies?

**Completion criteria:** you accurately identify **data types, schemas, encodings, protection layers, and trust policies**; distinguish "converting PEM/DER" from "converting PKCS#1/PKCS#8", "decrypting a private key" from "using a key to encrypt", and "reading a certificate" from "trusting a certificate".

## 19. References

- [RFC 7468 — Textual Encodings of PKIX, PKCS, and CMS Structures](https://www.rfc-editor.org/rfc/rfc7468): PEM textual encoding and labels.
- [ITU-T X.690 — ASN.1 Encoding Rules](https://www.itu.int/rec/T-REC-X.690/): BER, CER, and DER.
- [RFC 5280 — Internet X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): X.509 certificates and PKIX.
- [RFC 5958 — Asymmetric Key Packages](https://www.rfc-editor.org/rfc/rfc5958): OneAsymmetricKey, EncryptedPrivateKeyInfo.
- [RFC 5208 — PKCS#8 Private-Key Information Syntax](https://www.rfc-editor.org/rfc/rfc5208): traditional PrivateKeyInfo/EncryptedPrivateKeyInfo.
- [RFC 8017 — PKCS #1: RSA Cryptography Specifications](https://www.rfc-editor.org/rfc/rfc8017): RSA structures and algorithms.
- [RFC 8410 — Algorithm Identifiers for Ed25519, Ed448, X25519, X448](https://www.rfc-editor.org/rfc/rfc8410): SPKI/PKCS#8 for modern algorithms.
- [RFC 7292 — PKCS#12](https://www.rfc-editor.org/rfc/rfc7292): key/certificate container.
- [Java SE 17 — PKCS8EncodedKeySpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/PKCS8EncodedKeySpec.html) and [X509EncodedKeySpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/X509EncodedKeySpec.html): key specs to distinguish.
- [Java SE 17 — EncryptedPrivateKeyInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/EncryptedPrivateKeyInfo.html): encrypted private keys.
- [Java SE 17 — CertificateFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertificateFactory.html), [X509Certificate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html), [CertPathValidator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html): parsing and validating certificates.
- [Java SE 17 — KeyStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html): PKCS#12 and keystore providers.