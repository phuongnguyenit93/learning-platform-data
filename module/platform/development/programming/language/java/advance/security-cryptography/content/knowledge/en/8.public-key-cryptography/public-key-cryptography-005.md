# 8.5 Importing and Exporting X.509 SubjectPublicKeyInfo Public Keys and PKCS#8 Private Keys

## 1. Objectives and Scope

In the Java Cryptography Architecture (JCA), an asymmetric key pair has a **public key** (`PublicKey`) and a **private key** (`PrivateKey`). The public key can be distributed through trusted workflows; the private key must be protected. To store keys or exchange them between Java, OpenSSL, and other systems, you must agree on the **ASN.1 structure type**, **DER/PEM encoding**, and **algorithm**.

Java uses two common formats:

- **X.509 SubjectPublicKeyInfo (SPKI):** the standard format representing a *public key*, used with `X509EncodedKeySpec` and `KeyFactory.generatePublic(...)`.
- **PKCS#8 PrivateKeyInfo (or a matching private key representation accepted by the provider):** the standard format representing an *unencrypted private key*, used with `PKCS8EncodedKeySpec` and `KeyFactory.generatePrivate(...)`.

This lesson covers **key representation encoding and import/export**. Having valid DER or PEM **does not by itself authenticate the key owner's identity, trust, usage permissions, or revocation status**. PEM is merely a Base64 textual representation of the structure's bytes; `-----BEGIN PRIVATE KEY-----` **does not mean the key is encrypted with a password**.

After this lesson, you should be able to generate RSA/EC keys with `KeyPairGenerator`, export standard structures with `getEncoded()`, reconstruct them with `KeyFactory`, recognize PEM headers accurately, avoid confusing PKCS#1/SEC1/PKCS#12/certificates with SPKI or PKCS#8, and know how to handle `ENCRYPTED PRIVATE KEY`.

## 2. Three Layers to Separate: Algorithm, Binary Format, Text Form

A Java object such as `RSAPublicKey` or `ECPrivateKey` carries the key's mathematical information and may have a provider-specific implementation. If the key is exportable, `key.getEncoded()` returns a **byte array** in a standard format and `key.getFormat()` typically gives the standard format name:

| Java object | Default representation format when encoded | Storage unit |
| --- | --- | --- |
| Exportable RSA/EC/Ed25519 `PublicKey` | X.509, specifically the `SubjectPublicKeyInfo` structure | DER bytes |
| Exportable RSA/EC/Ed25519 `PrivateKey` | PKCS#8, specifically `PrivateKeyInfo` or a supported form | DER bytes |
| `SecretKey` such as AES | `RAW` or another provider-specific format | Symmetric secret key; SPKI/PKCS#8 does not apply |
| Key handle in HSM/PKCS#11 | May have `getEncoded() == null` | Material is not exported from the provider |

**DER** (Distinguished Encoding Rules) is ASN.1's deterministic binary encoding. **PEM** is the text wrapper: header, Base64 of the DER bytes, footer. Changing Base64 line breaks does not alter the key as long as the decoder recovers the exact bytes. In JCA, `X509EncodedKeySpec(byte[])` and `PKCS8EncodedKeySpec(byte[])` require **DER bytes**, not a PEM `String` directly or the bytes of the characters `-----BEGIN ...`.

Conceptual structure example (ASN.1 conceptual diagram, not Java source code):

```text
SubjectPublicKeyInfo ::= SEQUENCE {
    algorithm        AlgorithmIdentifier,
    subjectPublicKey BIT STRING
}

PrivateKeyInfo ::= SEQUENCE {
    version                   INTEGER,
    privateKeyAlgorithm       AlgorithmIdentifier,
    privateKey                OCTET STRING,
    attributes           [0]  IMPLICIT SET OF Attribute OPTIONAL
}
```

`AlgorithmIdentifier` typically contains an OID (object identifier) and may include algorithm parameters. For EC, parameters can specify the named curve; for RSA, the algorithm identifier indicates the RSA form and parameters per the corresponding rules. Do not treat just the `BIT STRING` containing an EC point or a pair of RSA numbers as the *entire* SPKI: the outer structure also records the algorithm and parameters so parsers interpret it properly.

For private keys, `privateKey` sits inside PKCS#8's OCTET STRING; **inside** that, it may contain an algorithm-specific format (such as RSAPrivateKey or ECPrivateKey). Therefore, "having RSA private key bytes inside" is **different from** "holding a bare PKCS#1 file". `KeyFactory.generatePrivate(new PKCS8EncodedKeySpec(bytes))` expects the **full PKCS#8 wrapper**.

RFC 5958 defines newer structures around `OneAsymmetricKey`, which may include an optional public key part. Do not assume every optional variant, extension field, or encoding from another provider is accepted by the running Java/provider; test on your exact deployment environment.

## 3. Identifying PEM Headers Accurately

Valid PEM content typically has lines such as:

```text
-----BEGIN PUBLIC KEY-----
<Base64 of DER SubjectPublicKeyInfo>
-----END PUBLIC KEY-----

-----BEGIN PRIVATE KEY-----
<Base64 of unencrypted DER PKCS#8 PrivateKeyInfo>
-----END PRIVATE KEY-----
```

The lines in between are **illustrative placeholders**, not valid Base64 to copy and run. The following table is especially important when receiving PEMs from OpenSSL, legacy Java systems, or external libraries:

| Header / data type | Nature | Which spec imports it directly? |
| --- | --- | --- |
| `BEGIN PUBLIC KEY` | X.509 SPKI, Base64-wrapped DER | PEM decode → `X509EncodedKeySpec` |
| `BEGIN PRIVATE KEY` | Unencrypted PKCS#8, Base64-wrapped DER | PEM decode → `PKCS8EncodedKeySpec` |
| `BEGIN ENCRYPTED PRIVATE KEY` | PKCS#8 `EncryptedPrivateKeyInfo`, with PBE and ciphertext | Must decrypt with matching algorithm/password first, then `PKCS8EncodedKeySpec` |
| `BEGIN RSA PUBLIC KEY` | PKCS#1 RSA `RSAPublicKey`, without SPKI wrapper | **Do not** pass directly into `X509EncodedKeySpec` |
| `BEGIN RSA PRIVATE KEY` | PKCS#1 RSA `RSAPrivateKey`, without PKCS#8 wrapper | **Do not** pass directly into `PKCS8EncodedKeySpec` |
| `BEGIN EC PRIVATE KEY` | SEC1 `ECPrivateKey` | Needs conversion/wrapping to PKCS#8 or a dedicated parser |
| `BEGIN CERTIFICATE` | X.509 certificate including SPKI and metadata/signature | `CertificateFactory` to parse certificate, then `getPublicKey()` |
| `BEGIN CERTIFICATE REQUEST` | Certificate signing request (CSR) | Neither raw SPKI nor PKCS#8 |
| `BEGIN OPENSSH PRIVATE KEY` | OpenSSH-proprietary format | Needs OpenSSH-compatible parser/converter; not PKCS#8 |
| `.p12`/`.pfx` | PKCS#12 container (keystore) | Use `KeyStore` with appropriate password/permissions |

**The word "X.509" in `X509EncodedKeySpec` does not mean this object is a certificate.** An X.509 certificate contains subject/issuer, validity period, extensions, certificate signature, and SPKI. `X509EncodedKeySpec` only represents the public key's SPKI; it has no certificate chain validation mechanism.

A `.der` or `.pem` extension is only a filename hint; you must determine the actual structure from the data contract and parser. Using the wrong PEM header, copying headers/footers into Base64, or confusing **PKCS#1** with **PKCS#8** are common causes of `InvalidKeySpecException`.

## 4. Java APIs to Remember

| Task | API | Input / output values |
| --- | --- | --- |
| Generate key pair | `KeyPairGenerator.getInstance("RSA")` / `"EC"` | `generateKeyPair()` → `PublicKey`, `PrivateKey` |
| Export DER data | `key.getEncoded()` | `byte[]` or `null` if non-exportable |
| Inspect encoding | `key.getFormat()` | Typically `"X.509"` for public, `"PKCS#8"` for private when exportable |
| Build public spec | `new X509EncodedKeySpec(spkiDer)` | DER bytes of **SPKI** |
| Build private spec | `new PKCS8EncodedKeySpec(privateKeyInfoDer)` | DER bytes of **unencrypted PKCS#8** |
| Import public | `KeyFactory.getInstance("RSA").generatePublic(spec)` | `PublicKey` |
| Import private | `KeyFactory.getInstance("RSA").generatePrivate(spec)` | `PrivateKey` |
| Armor PEM | `Base64.getMimeEncoder(64, new byte[]{'\n'})` | Base64 lines at most 64 characters long |
| Unarmor PEM | Check labels then `Base64.getDecoder().decode(body)` | DER bytes before creating `KeySpec` |
| Import X.509 certificate | `CertificateFactory.getInstance("X.509")` | `X509Certificate` then `getPublicKey()` |
| Import encrypted PKCS#8 | `EncryptedPrivateKeyInfo` and PBE `Cipher` | After decryption: `PKCS8EncodedKeySpec` |

`KeyFactory` is selected by **key algorithm** (`"RSA"`, `"EC"`, `"Ed25519"`, etc.), not by PEM header. Both RSA and EC can share the `BEGIN PUBLIC KEY` label; inside, `AlgorithmIdentifier` distinguishes them. If the contract is known in advance to be RSA, use `KeyFactory.getInstance("RSA")`; if the source can be multiple types, determine the trusted algorithm from metadata/schema or ASN.1 via a safe library rather than guessing from file extensions.

Although `X509EncodedKeySpec` and `PKCS8EncodedKeySpec` copy bytes into the key spec, the constructor is **not a full algorithm validator**; primary parsing and validation occur during `KeyFactory.generatePublic/generatePrivate`. Import can throw `InvalidKeySpecException` due to malformed DER, wrong algorithm, wrong parameters, or invalid key data.

## 5. Runnable Program: RSA and EC → SPKI/PKCS#8 → PEM → Re-import

The Java 17+ program below performs **two round-trips**:

1. Generate RSA-2048 and EC on curve `secp256r1` (P-256).
2. Call `getEncoded()` to obtain **SPKI DER** for the public key and **PKCS#8 DER** for the private key.
3. Wrap each DER into standard `PUBLIC KEY` or `PRIVATE KEY` PEM using 64-character line-wrapped Base64.
4. Check header/footer, decode PEM back to DER, and use `KeyFactory` + the matching `EncodedKeySpec` to import the keys.
5. Sign a message with the re-imported private key and verify with the re-imported public key.
6. Attempt to **pass PKCS#8 private bytes into `X509EncodedKeySpec`** to illustrate that structural mismatch is rejected.

Save as **`KeyEncodingRoundTripDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;
import java.security.spec.InvalidKeySpecException;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;
import java.util.Base64;

public final class KeyEncodingRoundTripDemo {
    private static String toPem(String label, byte[] der) {
        String base64 = Base64.getMimeEncoder(
                64, new byte[] { '\n' }).encodeToString(der);
        return "-----BEGIN " + label + "-----\n"
                + base64 + "\n-----END " + label + "-----\n";
    }

    private static byte[] fromPem(String pem, String expectedLabel) {
        String begin = "-----BEGIN " + expectedLabel + "-----";
        String end = "-----END " + expectedLabel + "-----";
        String normalized = pem.replace("\r\n", "\n").trim();
        if (!normalized.startsWith(begin + "\n")
                || !normalized.endsWith("\n" + end)) {
            throw new IllegalArgumentException("Unexpected PEM type");
        }
        String body = normalized.substring(
                begin.length() + 1,
                normalized.length() - end.length() - 1);
        String base64 = body.replace("\n", "");
        return Base64.getDecoder().decode(base64);
    }

    private static void roundTrip(
            String name, String signatureAlgorithm, KeyPair pair)
            throws Exception {
        byte[] publicDer = pair.getPublic().getEncoded();
        byte[] privateDer = pair.getPrivate().getEncoded();
        if (publicDer == null || privateDer == null) {
            throw new IllegalStateException("Key is not exportable");
        }
        try {
            String publicPem = toPem("PUBLIC KEY", publicDer);
            String privatePem = toPem("PRIVATE KEY", privateDer);

            KeyFactory factory = KeyFactory.getInstance(name);
            PublicKey publicKey = factory.generatePublic(
                    new X509EncodedKeySpec(fromPem(publicPem, "PUBLIC KEY")));
            PrivateKey privateKey = factory.generatePrivate(
                    new PKCS8EncodedKeySpec(fromPem(privatePem, "PRIVATE KEY")));

            byte[] message = "signature test".getBytes(StandardCharsets.UTF_8);
            Signature signer = Signature.getInstance(signatureAlgorithm);
            signer.initSign(privateKey);
            signer.update(message);
            byte[] signature = signer.sign();
            Signature verifier = Signature.getInstance(signatureAlgorithm);
            verifier.initVerify(publicKey);
            verifier.update(message);

            System.out.println(name + " publicFormat=" + pair.getPublic().getFormat());
            System.out.println(name + " privateFormat=" + pair.getPrivate().getFormat());
            System.out.println(name + " publicRoundTrip="
                    + Arrays.equals(publicDer, publicKey.getEncoded()));
            System.out.println(name + " privateRoundTrip="
                    + Arrays.equals(privateDer, privateKey.getEncoded()));
            System.out.println(name + " signatureValid=" + verifier.verify(signature));
        } finally {
            Arrays.fill(publicDer, (byte) 0);
            Arrays.fill(privateDer, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator rsa = KeyPairGenerator.getInstance("RSA");
        rsa.initialize(2048);
        KeyPair rsaPair = rsa.generateKeyPair();
        roundTrip("RSA", "SHA256withRSA", rsaPair);

        KeyPairGenerator ec = KeyPairGenerator.getInstance("EC");
        ec.initialize(new ECGenParameterSpec("secp256r1"));
        KeyPair ecPair = ec.generateKeyPair();
        roundTrip("EC", "SHA256withECDSA", ecPair);

        KeyFactory factory = KeyFactory.getInstance("RSA");
        try {
            factory.generatePublic(new X509EncodedKeySpec(
                    rsaPair.getPrivate().getEncoded()));
            System.out.println("wrongContainerRejected=false");
        } catch (InvalidKeySpecException expected) {
            System.out.println("wrongContainerRejected=true");
        }
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 KeyEncodingRoundTripDemo.java
java KeyEncodingRoundTripDemo
```

Result on standard OpenJDK supporting RSA/EC:

```text
RSA publicFormat=X.509
RSA privateFormat=PKCS#8
RSA publicRoundTrip=true
RSA privateRoundTrip=true
RSA signatureValid=true
EC publicFormat=X.509
EC privateFormat=PKCS#8
EC publicRoundTrip=true
EC privateRoundTrip=true
EC signatureValid=true
wrongContainerRejected=true
```

Because each run generates fresh keys, **DER bytes and signatures vary**, while these checks produce the results above when the provider functions properly. The example chooses RSA-2048 for broad compatibility; algorithm/key-size choices in new systems must match specific security requirements and protection lifetimes.

### 5.1 Explaining Key Points of the Program

**Matching container class:** `toPem("PUBLIC KEY", spkiDer)` pairs with `X509EncodedKeySpec`; `toPem("PRIVATE KEY", pkcs8Der)` pairs with `PKCS8EncodedKeySpec`. Wrong labels are rejected by the example's helper before JCA parsing. `wrongContainerRejected=true` comes from `KeyFactory.generatePublic` rejecting a private-key structure as SPKI.

**Deliberately scoped PEM helper:** `fromPem` handles a single PEM block produced by `toPem`, using LF or CRLF newlines, exact header/footer, and simple Base64 lines. This is an **educational parser** and does not handle every real-world PEM variant (such as multiple PEM blocks in one file, comments or arbitrary metadata, or unbounded size). In production, use a PEM parser with strict controls on labels, block count, encoding, byte limits, and validation.

**Encoding indicators:** `getFormat()` normally returns `"X.509"` or `"PKCS#8"` for exportable software keys. However, `getEncoded() == null` is valid for non-exportable key handles/providers, and `getFormat()` can also be `null`. Do not treat provider-specific bytes as a portable contract without testing.

**Byte equality vs. identity:** when round-tripping DER within the same provider, `Arrays.equals(originalDer, reconstructedKey.getEncoded())` typically returns `true`. Across providers, two equivalent keys may re-encode with valid minor differences; *verifying a signature created with the re-imported private key using the re-imported public key* is a meaningful complementary behavioral test. Never use simple DER byte comparison to prove a sender is trustworthy or a public key belongs to an identity.

**Sensitive data:** the program puts private bytes into `byte[]` and a PEM `String` in memory for demonstration. `Arrays.fill(privateDer, (byte)0)` only clears the held array and **cannot erase** internal copies inside Java objects, the PEM `String`, or the provider. In production, use key handles/keystores where possible, avoid exporting private keys merely for inspection, and never print or log PEM private keys.

## 6. Importing PEM/DER from Real Files

Basic conversions when reading data from files:

```text
public.pem
  -> verify exact BEGIN PUBLIC KEY / END PUBLIC KEY
  -> Base64-decode to SubjectPublicKeyInfo DER
  -> new X509EncodedKeySpec(der)
  -> KeyFactory.getInstance(algorithm).generatePublic(spec)

private.pem
  -> verify exact BEGIN PRIVATE KEY / END PRIVATE KEY
  -> Base64-decode to PKCS#8 DER
  -> new PKCS8EncodedKeySpec(der)
  -> KeyFactory.getInstance(algorithm).generatePrivate(spec)

public.der / private.der
  -> pass DER bytes directly into the matching KeySpec type
```

Example reading files with the standard Java library (**illustrative snippet**, called inside a method with declared exceptions and imports):

```java
// public.der contains exact SPKI DER; private.der contains exact PKCS#8 DER.
byte[] spkiDer = java.nio.file.Files.readAllBytes(
        java.nio.file.Path.of("public.der"));
byte[] privateDer = java.nio.file.Files.readAllBytes(
        java.nio.file.Path.of("private.der"));
try {
    java.security.KeyFactory factory =
            java.security.KeyFactory.getInstance("RSA");

    java.security.PublicKey publicKey = factory.generatePublic(
            new java.security.spec.X509EncodedKeySpec(spkiDer));
    java.security.PrivateKey privateKey = factory.generatePrivate(
            new java.security.spec.PKCS8EncodedKeySpec(privateDer));
    // Use publicKey/privateKey for permitted operations.
} finally {
    java.util.Arrays.fill(spkiDer, (byte) 0);
    java.util.Arrays.fill(privateDer, (byte) 0);
}
```

`Files.readAllBytes` is only suitable for small, **size-bounded** key files. For user-supplied files, enforce a byte limit before reading to guard against huge files and only parse **exact expected formats**; never accept an arbitrary string containing `BEGIN` and strip lines with `replaceAll`. For PEM files, read using an ASCII charset and use a header/footer-aware parser to extract the Base64 body before creating a `KeySpec`; **never** call `new PKCS8EncodedKeySpec(Files.readAllBytes("private.pem"))`.

When writing DER or PEM files in a real application, set restrictive read permissions on private key files **before publishing or placing them in directories accessible to others**. POSIX permissions like `0600` do not apply identically on Windows; design file protection for your ACLs, process user, and environment. Typically, private keys are better managed via `KeyStore`, HSM, or KMS than plain `private.pem` files.

To import a **public key from a certificate**, use `CertificateFactory`:

```java
// Illustrative snippet: certDer is the full certificate DER (not SPKI).
java.security.cert.CertificateFactory certificates =
        java.security.cert.CertificateFactory.getInstance("X.509");
java.security.cert.X509Certificate certificate =
        (java.security.cert.X509Certificate) certificates.generateCertificate(
                new java.io.ByteArrayInputStream(certDer));
java.security.PublicKey publicKey = certificate.getPublicKey();
```

**Merely parsing a certificate does not verify trust.** You must check the chain, trust anchor, validity period, constraints, key usage, hostname, and revocation per protocol. `certificate.getPublicKey()` returns the public key from the certificate; `certificate.getEncoded()` is the encoding of the **entire certificate**, not SPKI.

## 7. Unencrypted PKCS#8 and Encrypted PKCS#8 Are Two Different Types

`BEGIN PRIVATE KEY` represents **unencrypted PKCS#8 PrivateKeyInfo**. Base64 does not make it confidential; anyone who can read the file can extract the key material.

`BEGIN ENCRYPTED PRIVATE KEY` represents **EncryptedPrivateKeyInfo**, structured conceptually as:

```text
EncryptedPrivateKeyInfo ::= SEQUENCE {
    encryptionAlgorithm AlgorithmIdentifier,
    encryptedData       OCTET STRING
}
```

To import the encrypted form, you must identify the PBE algorithm and its parameters (e.g., PBES2, salt, iteration count, cipher parameters), authenticate/supply the required password, and decrypt to **unencrypted PKCS#8 DER**; only then can you pass it to `PKCS8EncodedKeySpec` with `KeyFactory`. Passing `EncryptedPrivateKeyInfo.getEncoded()` directly into `PKCS8EncodedKeySpec` is a format mismatch.

Having a password-protected private key file **does not mean** it includes integrity authentication against tampering or a strong password. Some legacy PBE schemes are weak, and some PBES2 schemes use AES-CBC and depend on padding/DER validation; you need an algorithm policy, a strong password, format validation, and resource limits. A weak password can be brute-forced offline as soon as an attacker obtains the encrypted PKCS#8 blob.

### 7.1 Runnable Program: Protecting and Recovering PKCS#8 with PBE/PBES2

This Java 17+ example uses a common provider supporting `PBEWithHmacSHA256AndAES_256`, a random salt, and 210,000 iterations **to illustrate the API**, not as standard security parameters for all situations. Actual algorithms/`AlgorithmParameters` depend on the provider; the example makes the outer `PBES2` layer explicit so `EncryptedPrivateKeyInfo` receives a valid ASN.1 AlgorithmIdentifier.

Save as **`EncryptedPkcs8Demo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.AlgorithmParameters;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.PKCS8EncodedKeySpec;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.EncryptedPrivateKeyInfo;
import javax.crypto.SecretKey;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.PBEParameterSpec;

public final class EncryptedPkcs8Demo {
    private static final String PBE = "PBEWithHmacSHA256AndAES_256";

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();
        byte[] original = pair.getPrivate().getEncoded();
        char[] password = "demo-password-only".toCharArray();
        byte[] salt = new byte[16];
        new SecureRandom().nextBytes(salt);
        PBEKeySpec passwordSpec = new PBEKeySpec(password);

        try {
            SecretKeyFactory keyFactory = SecretKeyFactory.getInstance(PBE);
            SecretKey pbeKey = keyFactory.generateSecret(passwordSpec);

            Cipher encrypt = Cipher.getInstance(PBE);
            encrypt.init(Cipher.ENCRYPT_MODE, pbeKey,
                    new PBEParameterSpec(salt, 210_000));
            byte[] ciphertext = encrypt.doFinal(original);

            AlgorithmParameters pbes2 = AlgorithmParameters.getInstance("PBES2");
            pbes2.init(encrypt.getParameters().getEncoded());
            EncryptedPrivateKeyInfo container =
                    new EncryptedPrivateKeyInfo(pbes2, ciphertext);
            EncryptedPrivateKeyInfo parsed =
                    new EncryptedPrivateKeyInfo(container.getEncoded());

            Cipher decrypt = Cipher.getInstance(PBE);
            decrypt.init(Cipher.DECRYPT_MODE, pbeKey,
                    parsed.getAlgParameters());
            PKCS8EncodedKeySpec plain = parsed.getKeySpec(decrypt);
            PrivateKey restored = KeyFactory.getInstance("RSA")
                    .generatePrivate(plain);

            Signature signer = Signature.getInstance("SHA256withRSA");
            signer.initSign(restored);
            signer.update("signed data".getBytes(StandardCharsets.UTF_8));
            byte[] signature = signer.sign();

            Signature verifier = Signature.getInstance("SHA256withRSA");
            verifier.initVerify(pair.getPublic());
            verifier.update("signed data".getBytes(StandardCharsets.UTF_8));

            System.out.println("encryptedContainerParsed=true");
            System.out.println("restoredMatches="
                    + Arrays.equals(original, restored.getEncoded()));
            System.out.println("signatureValid=" + verifier.verify(signature));
            Arrays.fill(ciphertext, (byte) 0);
        } finally {
            passwordSpec.clearPassword();
            Arrays.fill(password, '\0');
            Arrays.fill(salt, (byte) 0);
            Arrays.fill(original, (byte) 0);
        }
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 EncryptedPkcs8Demo.java
java EncryptedPkcs8Demo
```

```text
encryptedContainerParsed=true
restoredMatches=true
signatureValid=true
```

**Takeaway:** `EncryptedPrivateKeyInfo` holds the protection scheme metadata and ciphertext. `getKeySpec(decrypt)` produces `PKCS8EncodedKeySpec` **only after the Cipher decrypts**. Only after `KeyFactory.generatePrivate` do you obtain a usable `PrivateKey`. Never print or log private key material; the `Arrays.equals(...)` expressions here only verify data internally.

**Example limitations:** the hardcoded password is for demo only; use secure password input and real guessing-resistance policies. The `PBES2` + `PBEWithHmacSHA256AndAES_256` flow was tested on OpenJDK supporting these names; other providers/versions may require a vetted PKCS#8 library or `KeyStore`/KMS. `PBEWithHmacSHA256AndAES_256` describes the HMAC-SHA256 KDF PRF and AES encryption; **it does not mean the ciphertext carries an independent authenticating HMAC**. For highly sensitive key files, prefer a policy-protected keystore rather than inventing a custom private-key file encryption protocol.

## 8. Converting from Common Formats Using Dedicated Tools

When receiving an RSA key in `BEGIN RSA PRIVATE KEY` (PKCS#1) or EC key in `BEGIN EC PRIVATE KEY` (SEC1), **do not** rename the header to `BEGIN PRIVATE KEY` while keeping the Base64 unchanged: changing the header does not change the ASN.1 structure. You must build the **PKCS#8 wrapper** using a tool/library that understands the algorithm.

Example OpenSSL commands (illustrative commands for environments with OpenSSL installed; substitute your paths and protect private key files per policy):

```bash
# Convert an RSA PKCS#1 or EC SEC1 private key to unencrypted PKCS#8.
openssl pkcs8 -topk8 -nocrypt -in legacy-private.pem -out private-pkcs8.pem

# Export SPKI public key from a private key recognized by OpenSSL.
openssl pkey -in private-pkcs8.pem -pubout -out public-spki.pem

# Inspect structural details without printing the private key to logs:
openssl pkey -in private-pkcs8.pem -noout -text_pub
```

Converting with `-nocrypt` creates an **unencrypted private key**, which is highly sensitive: use a permission-restricted temporary location, securely delete it per storage lifecycle rules, and prefer performing conversions in a secure environment. Depending on the OpenSSL version, `-text_pub` may not be supported in that combination; check `openssl pkey -help` for your version. To create encrypted PKCS#8, use a tool configured with secure PBE and strong password policies; `-nocrypt` **strips password protection**.

**Do not** assume every `openssl rsa -pubout` or `openssl pkey -pubout` command always outputs PEM with the same label across all modes/versions/flags; **read the actual header** and verify the SPKI structure. Traditional `RSA PUBLIC KEY` output is PKCS#1, unlike `PUBLIC KEY` SPKI.

If you want to exchange a key pair in a protected container, Java `KeyStore` with PKCS12 may be better suited than separate PEM files; PKCS#12 includes multiple entries, certificate chains, and protection mechanisms, and is **not PKCS#8 bytes** to pass directly into `PKCS8EncodedKeySpec`.

## 9. Common Errors When Importing or Exporting Keys

| Symptom | Common cause | How to resolve |
| --- | --- | --- |
| `InvalidKeySpecException`: cannot parse key | Passing PKCS#1, SEC1, certificate, CSR, or wrong DER into X.509/PKCS#8 spec | Identify the actual structure; convert to the proper format first |
| `InvalidKeySpecException`: algorithm mismatch | `KeyFactory("RSA")` given an EC/Ed25519 key, or mismatched OID/params | Pick algorithm from trusted protocol/metadata and verify provider support |
| `IllegalArgumentException` during Base64 decode | Copied header/footer with body, stray characters, truncated Base64 | Parse PEM with exact label, decode body, enforce size limits |
| `getEncoded() == null` | Key is non-exportable (HSM/token/provider) | Use `Key` directly inside the provider; do not fabricate bytes |
| `NoSuchAlgorithmException` | Runtime/provider lacks `RSA`/`EC`/PBE algorithm | Check provider, JDK, algorithm name, and deployment compatibility |
| `InvalidKeyException` or `SignatureException` when signing | Wrong key type, mode, or incompatible signature parameters | Use the right private/public key, signature algorithm, and parameters |
| `BadPaddingException` / encrypted PKCS#8 decryption error | Wrong password, cipher parameters, or ciphertext | Reject the key, handle errors uniformly, never expose raw secrets |
| Importing certificate as public DER | `certificate.getEncoded()` is the full X.509 certificate | Use `CertificateFactory` then `cert.getPublicKey()` |
| Importing `BEGIN OPENSSH PRIVATE KEY` as PKCS#8 | OpenSSH container differs from ASN.1 PKCS#8 | Convert or use a proper OpenSSH parser |
| Have private key DER but unknown key type | PEM `PRIVATE KEY` is a generic label | Determine from ASN.1 algorithm identifier / contract, not filename |
| Signature created, but verification fails | Mismatched key pair, altered message, different encoding, or signature params | Check signed/verified bytes byte-for-byte and confirm matching keys |

**Never use successful parser execution as proof of trust.** For public keys received from others, you need a process binding keys to identity: certificate chains, fingerprints verified out-of-band, pinned public keys, or protocol identity verification. For private keys, control which users/apps can access them, backups, rotation, access audit logs, and storage protection. Reading externally supplied key files always requires size limits, consistent parse errors, and avoiding sensitive leaks.

## 10. Key Misconceptions

- **"Having an X.509 public key means having an X.509 certificate."** No. SPKI is only the structure holding the public key and algorithm identifier; a certificate also carries identity, issuer, validity, and signature.
- **"PKCS#8 is a private-key algorithm."** No. It is a **container** for multiple algorithms; RSA/EC/Ed25519 are the algorithms.
- **"PEM is encrypted."** Not by default. `BEGIN PRIVATE KEY` is unencrypted PKCS#8; `BEGIN ENCRYPTED PRIVATE KEY` indicates an encrypted PKCS#8 protection wrapper.
- **"Just strip the Base64 header and call KeyFactory for any private key."** No. Decoding only yields bytes of the original format and does not convert PKCS#1/SEC1 into PKCS#8.
- **"Since it is Base64, I can use `String.getBytes()` to build a KeySpec."** No. You must Base64-decode into the underlying DER bytes.
- **"If it is RSA, `KeyFactory("RSA")` can read certificates or PKCS#1 arbitrarily."** No. Both the algorithm and the container format must match.
- **"Storing a PEM private key in an app file is always safe."** No. You must manage access permissions, encryption protection where appropriate, KMS/HSM, and lifecycle policy.
- **"`getEncoded()` always returns bytes."** No. Providers may hold non-exportable keys; `null` is a valid API outcome.
- **"Renaming the PKCS#1 label to PKCS#8 is enough."** No. You must convert the actual ASN.1 structure using a proper converter.
- **"Successfully importing a public key means you can trust and use it immediately."** No. The key's origin and identity must be verified per protocol.

## 11. Self-Check Questions

1. Which ASN.1 object does `X509EncodedKeySpec` hold? **`SubjectPublicKeyInfo`**, including algorithm identifier and public key bits.
2. Which format's bytes does `PKCS8EncodedKeySpec` normally take? **Unencrypted PKCS#8 PrivateKeyInfo**.
3. Is `BEGIN RSA PRIVATE KEY` PKCS#8? **No**; it is typically the PKCS#1 RSA private structure.
4. Are `BEGIN PUBLIC KEY` and `BEGIN CERTIFICATE` directly interchangeable? **No**; one is SPKI, the other is a full certificate.
5. How does PEM differ from DER? **PEM is Base64 text armor + labels; DER is ASN.1 binary bytes**.
6. To import RSA SPKI public DER, what are the two main APIs? **`new X509EncodedKeySpec(der)` and `KeyFactory.getInstance("RSA").generatePublic(...)`**.
7. If a private key is in `ENCRYPTED PRIVATE KEY` form, can you pass it straight to `PKCS8EncodedKeySpec`? **No**; you must parse/decrypt `EncryptedPrivateKeyInfo` first.
8. Does `getEncoded() == null` mean the key is broken? **No**; it may be a non-exportable key.
9. Why doesn't successfully importing a public key prove identity? Because **key bytes carry no inherent trust binding to an owner**; you need certificates/chains/pinning/authentication workflows.
10. Is converting a PKCS#1 RSA private key to PKCS#8 by changing the PEM header valid? **No**; you must convert the actual DER structure.
11. Does `Arrays.equals(original.getEncoded(), restored.getEncoded())` passing prove everything? **No**; you still need to verify cryptographic operations, key origin, storage, and provider behavior.
12. When exporting a PEM private key, what is the first thing to control? **Preventing private-key leakage**, protecting file/memory permissions, avoiding unintended logs/backups, and managing lifecycle.

## Authoritative Documentation and Java SE 21 APIs

- [X509EncodedKeySpec: SubjectPublicKeyInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/spec/X509EncodedKeySpec.html)
- [PKCS8EncodedKeySpec](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/spec/PKCS8EncodedKeySpec.html)
- [KeyFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyFactory.html)
- [KeyPairGenerator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyPairGenerator.html)
- [Key.getEncoded/getFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Key.html)
- [EncryptedPrivateKeyInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/EncryptedPrivateKeyInfo.html)
- [CertificateFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertificateFactory.html)
- [Java KeyStore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.html)
- [RFC 5280: X.509 Public Key Infrastructure, SubjectPublicKeyInfo](https://www.rfc-editor.org/rfc/rfc5280.html)
- [RFC 5958: Asymmetric Key Packages / PKCS#8](https://www.rfc-editor.org/rfc/rfc5958.html)
- [RFC 7468: PKIX Textual Encodings (PEM)](https://www.rfc-editor.org/rfc/rfc7468.html)