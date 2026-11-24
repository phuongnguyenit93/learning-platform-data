# PEM, PKCS#8 formats, and keystores in Spring Security SAML 2.0 deployment environments

## 1. Lesson objectives

In **Spring Security – federation** systems, a Spring Boot application typically acts as a **Service Provider (SP/Relying Party)** and integrates with one or more **Identity Providers (IdP/Asserting Party)**. The SP needs certificates/keys for different tasks:

- Use the **SP private key** to **sign AuthnRequest** or SP-issued SAML messages if required by configuration.
- Use the **SP private key** to **decrypt EncryptedAssertion/EncryptedID** that the IdP encrypted for the SP.
- Use the **IdP public certificate** to **verify the SAML Response/Assertion signature** sent by the IdP.
- If the system requires **signed metadata**, use a separately provisioned and verified **metadata signer trust anchor** to validate the metadata document before trusting the certificates inside it.

A very common difficulty: having all the `.pem`, `.key`, `.crt`, `.p12` files yet Spring Security still throws errors reading the private key, reports mismatched certificates, cannot sign AuthnRequest, or cannot decrypt assertions. The reason is that **encoding representation**, **key structure**, **storage location**, **intended purpose**, and **trust policy** are distinct concepts.

This lesson belongs to **Keys and certificates** and systematically explains:

1. How **PEM, DER, PKCS#8, PKCS#1, X.509, PKCS#12, JKS, and PKCS#11** differ.
2. How to distinguish public certificates, public keys, and private keys; recognizing the right `BEGIN ...` labels.
3. How to convert keys safely with OpenSSL and verify key–certificate pairs.
4. How Spring Boot/Spring Security reads **PEM/PKCS#8 files** as signing/decryption credentials, or uses **Java PKCS#12 KeyStore** in code.
5. How to manage keys across servers, containers, Kubernetes, HSM/secret managers, multi-IdP environments, and rotation periods.
6. Testing misconfigurations, certificate rollover, access permissions, algorithms, and secure deployment workflows.

**Guiding principle:** parsing a private key file is only the first step. Only when **the keypair matches, the registration is right, the purpose is right, trust is established, and access permissions are governed** is cryptographic material fit for SAML2 production.

## 2. Separating three layers: encoding, structure, and keystore

Look at these terms along three independent axes:

| Layer | Examples | Question it answers |
| --- | --- | --- |
| **Representation/encoding** | PEM, DER | Is the key/certificate data represented as Base64 text or binary? |
| **Inner structure** | PKCS#8 PrivateKeyInfo, PKCS#1 RSAPrivateKey, X.509 certificate, SubjectPublicKeyInfo | What kind of cryptographic object do the decoded bytes contain? |
| **Container / access store** | PKCS#12 `.p12/.pfx`, JKS, HSM PKCS#11, secret manager | How many entries, aliases/chains, passwords, access controls, and where is the key held? |

For example, the **same RSA private key** can exist in several forms:

```text
RSA private key
   |
   +-- ASN.1 PKCS#1 -> DER -> PEM "BEGIN RSA PRIVATE KEY"
   |
   +-- ASN.1 PKCS#8 -> DER -> PEM "BEGIN PRIVATE KEY"
   |
   +-- PKCS#8 encrypted -> DER -> PEM "BEGIN ENCRYPTED PRIVATE KEY"
   |
   +-- PrivateKeyEntry in PKCS#12 keystore (with X.509 certificate chain)
   |
   +-- Non-exportable key in HSM, seen by Java app via PKCS#11 provider
```

**`.pem`, `.key`, and `.crt` are filename conventions**, not guarantees of actual format. A `server.key` file can still hold PKCS#1 or PKCS#8; an `idp.crt` file can be PEM X.509 or DER X.509. To know for sure, read the label, parse the structure properly, and verify with appropriate tools.

### 2.1. PEM vs. DER

**DER** (*Distinguished Encoding Rules*) is a **binary ASN.1** format. **PEM** wraps binary content (usually DER) into **Base64 with BEGIN/END labels**, suitable for transport in text files.

Example PEM structure:

```text
-----BEGIN CERTIFICATE-----
MIIB...base64-encoded-X509-certificate...
-----END CERTIFICATE-----
```

The Base64 string in the example is **an illustrative placeholder only**, not a real certificate.

PEM **does not by itself indicate** whether a key is PKCS#8 or PKCS#1; that is expressed by the DER object type and label. Renaming `.key` to `.pem` **does not convert the key structure**. Likewise, putting PKCS#1 bytes into a file and renaming it `pkcs8.pem` does not make it valid PKCS#8.

## 3. Reading PEM labels and their technical meaning

| PEM header | Typical content | Compatibility with Spring/Java |
| --- | --- | --- |
| `-----BEGIN CERTIFICATE-----` | Public X.509 certificate (Base64-encoded ASN.1 DER) | Typically readable by `CertificateFactory.getInstance("X.509")` |
| `-----BEGIN PRIVATE KEY-----` | **PKCS#8 PrivateKeyInfo unencrypted by passphrase** | Suitable for `PKCS8EncodedKeySpec` or `RsaKeyConverters.pkcs8()` if algorithm is supported |
| `-----BEGIN ENCRYPTED PRIVATE KEY-----` | **Encrypted PKCS#8** with PBE/password algorithm | Requires a compatible decrypting loader; do not pass directly to APIs expecting unencrypted PKCS#8 |
| `-----BEGIN RSA PRIVATE KEY-----` | Traditional **PKCS#1 RSA private key** | Must not be assumed to be PKCS#8; needs a supporting converter or format conversion |
| `-----BEGIN EC PRIVATE KEY-----` | Traditional **SEC1 EC private key** | Not RSA PKCS#8; loader/provider must support EC |
| `-----BEGIN PUBLIC KEY-----` | **SubjectPublicKeyInfo (SPKI)** of a public key | Usable with `X509EncodedKeySpec`, yet **not an X.509 certificate** |
| `-----BEGIN RSA PUBLIC KEY-----` | PKCS#1-structured RSA public key | Differs from SPKI; do not pass raw into `X509EncodedKeySpec` |
| `-----BEGIN CERTIFICATE REQUEST-----` | PKCS#10 Certificate Signing Request (CSR) | Used to request cert issuance, not a certificate issued for a SAML partner |

**Distinguish two uses of "X.509":**

- `X509Certificate` is a **certificate** with subject, issuer, validity, public key, certificate signature, etc.
- JCA's `X509EncodedKeySpec` represents an **SPKI public key**. It **does not** parse a `BEGIN CERTIFICATE` into a certificate.

Never take a certificate's DER bytes and pass them to `new X509EncodedKeySpec(bytes)`; if you need a certificate, use `CertificateFactory`. Conversely, `BEGIN PUBLIC KEY` only contains the public key—no chain, validity window, or partner identity attestation equivalent to an X.509 certificate.

### 3.1. PEM is not a security mechanism

PEM is purely a **text representation**. A `BEGIN PRIVATE KEY` file can hold an **unencrypted** private key: anyone who can read the file can use the key. "File ends in `.pem`" or "file is Base64-encoded" **does not** mean it is secured. Confidentiality comes from storage protection, encryption at rest, secret management, access controls, auditing, and lifecycle management.

## 4. What is PKCS#8? Is RSA mandatory?

**PKCS#8** defines a structure for storing **private-key information** including an algorithm identifier and key bytes. It supports multiple key types (RSA, EC, and provider-supported types), not just RSA.

Distinguish two cases:

1. **Unencrypted PrivateKeyInfo**: typically `BEGIN PRIVATE KEY`; Java's `PKCS8EncodedKeySpec` is designed for this data.
2. **EncryptedPrivateKeyInfo**: typically `BEGIN ENCRYPTED PRIVATE KEY`; requires the matching **password and PBE decryption algorithm** to recover PrivateKeyInfo before building a PrivateKey object.

**PKCS#8 does not mean "encrypted key".** An unencrypted PKCS#8 file is still dangerous if stolen. Nor is PKCS#8 **a multi-entry keystore** like PKCS#12.

### 4.1. How do PKCS#1 and PKCS#8 differ?

**PKCS#1 RSAPrivateKey** holds RSA-specific parameters such as modulus and CRT coefficients. **PKCS#8 PrivateKeyInfo** wraps the private key with generic algorithm metadata (such as the RSA OID), letting systems read keys through a unified structure.

Representation:

```text
PKCS#1 RSA key:
  RSAPrivateKey { version, modulus, publicExponent,
                  privateExponent, prime1, prime2, ... }

PKCS#8:
  PrivateKeyInfo {
      version,
      privateKeyAlgorithm = rsaEncryption,
      privateKey = OCTET STRING containing algorithm-specific data,
      ...
  }
```

When using `KeyFactory.generatePrivate(new PKCS8EncodedKeySpec(bytes))`, the bytes must be valid PKCS#8 and the algorithm must be supported by `KeyFactory`. Passing PKCS#1 typically triggers `InvalidKeySpecException`, `InvalidKeyException`, or ASN.1 parsing errors.

Never solve this by "wrapping `BEGIN PRIVATE KEY` lines" around PKCS#1 bytes. You must **convert the structure** with proper tools, not just change the header.

### 4.2. What about PKCS#12?

**PKCS#12** is a **keystore/container** that typically carries private keys, certificates, and certificate chains, can hold multiple entries by alias, and is password-protected. Files usually have `.p12` or `.pfx` extensions.

PKCS#8 is a **private key object**; PKCS#12 is a **container holding keys and certs**. The two standards cannot substitute for each other merely by renaming extensions.

| Need | Usually appropriate choice |
| --- | --- |
| One private key + certificate pair read by Spring Boot by location | PEM PKCS#8 and PEM X.509 with secure secret mount |
| Multiple keypairs, certificate chains, aliases, and passwords managed via Java | PKCS#12 KeyStore |
| Legacy Java project using an older keystore | JKS, consider migrating appropriately |
| Key must never be exported to files | HSM/PKCS#11 or KMS/remote signer integrated via provider |
| Only trusting IdP public certificate to verify assertions | Public cert/pinned trust config; no IdP private key needed |

JDK 17 documentation confirms **PKCS12 is the default recommended keystore type since JDK 9**, whereas JKS is a Java-proprietary format. PKCS11 is an interface to tokens/HSMs, **not a `.p11` file used like `.p12`**.

## 5. Distinguishing SP keys and IdP certificates in SAML2

In `RelyingPartyRegistration`, always look at both sides:

```text
RelyingPartyRegistration "corp"
│
├── Relying party (SP)
│   ├── entityId: urn:example:portal:prod:sp
│   ├── signing credential:
│   │      SP private key + SP X.509 certificate
│   └── decryption credential:
│          SP private key + SP X.509 certificate
│
└── Asserting party (IdP)
    ├── entityId: https://idp.example.test/saml
    ├── verification credentials:
    │      IdP public X.509 certificate
    └── SSO endpoint, metadata, and binding
```

| Role | Who holds the private key? | When used? | Common confusion |
| --- | --- | --- | --- |
| SP signing | **SP** | SP signs AuthnRequest/LogoutRequest per profile | Mistakenly using IdP public cert for signing |
| SP decryption | **SP** | SP decrypts EncryptedAssertion sent to SP | Having only SP cert without private key |
| IdP verification | **IdP** | SP verifies response/assertion signed by IdP | Blindly importing an unknown certificate from response |
| IdP encryption recipient (if any) | **IdP** | SP encrypts assertion/message sent to IdP when profile requires | Confusing with SP decryption private key |
| Metadata signature verification | Metadata signer/aggregator | SP verifies signed metadata | Blindly trusting a signer certificate supplied by unverified metadata |

**The SP's public certificate and private key must match in public key**, though the certificate may be self-signed or CA-issued depending on the SAML agreement. In SAML federation, the IdP usually **pins/registers specific certificates per SP Entity ID**, rather than automatically treating any arbitrary TLS cert as a trusted SP signing credential.

Conversely, the SP must know the exact IdP certificate from a **verified metadata/trust configuration source**. A certificate with a valid X.509 chain does not by itself prove that the IdP entityId is authorized to issue assertions for the application.

### 5.1. Why separate signing and decryption?

An organization may share the same keypair for SP signing and decryption if both parties and libraries support it. However, separating the two purposes allows:

- Rotating the SP signing private key without simultaneously breaking decryption of in-flight assertions.
- Limiting blast radius if one private key is compromised.
- Keeping distinct audit trails for signing vs. decryption operations.
- Retaining multiple decryption keys during the IdP's certificate rollover window while signing only with the current key.

If choosing to share, explicitly document the **purpose** and key rotation policy. Never configure the same certificate for both signing and decryption merely because the two properties sit next to each other.

## 6. OpenSSL commands: safe inspection and format conversion

The following commands assume execution **in a test environment or authorized administrative host** using modern OpenSSL. Do not run against production private keys without authorization, an approval process, and secure output storage.

### 6.1. Identifying file types

For PEM, inspect **BEGIN/END labels** with a suitable text viewer, yet **never paste or send full private keys to chat, tickets, logs, or web tools**.

Inspect a public certificate:

```bash
openssl x509 -in sp-cert.pem -noout -subject -issuer -dates -fingerprint -sha256
```

This displays the certificate's subject, issuer, validity dates, and SHA-256 fingerprint. It **does not print private keys**. However, a matching fingerprint only identifies the partner if checked against an **independent trusted source**, not an arbitrary fingerprint supplied by the sender over the same controlled channel.

Check that a private key parses cleanly without printing the private key to stdout:

```bash
openssl pkey -in sp-private.pem -check -noout
```

This command may prompt for a passphrase if the key is encrypted. It does not replace checking keypair match with the certificate or evaluating key-usage policy.

### 6.2. Converting PKCS#1/traditional key to unencrypted PKCS#8

```bash
openssl pkcs8 -topk8 -nocrypt \
  -in sp-traditional-key.pem \
  -out sp-private-pkcs8.pem
```

`-topk8` writes PKCS#8. `-nocrypt` writes **unencrypted PKCS#8**, typically with header `BEGIN PRIVATE KEY`. It suits loaders that only support unencrypted PKCS#8 **provided the private key is thoroughly protected on the filesystem/volume**.

**Warning:** this operation **creates a new plaintext private key copy**. Convert only in controlled areas with appropriate `umask`/file permissions; never write to shared directories, synced workspaces, container layers, CI artifacts, or logs. Do not keep multiple unnecessary plaintext copies. If policy forbids unencrypted private keys on disk, use PKCS#12/HSM/appropriate providers rather than `-nocrypt` in production.

### 6.3. Converting to password-protected PKCS#8

```bash
openssl pkcs8 -topk8 \
  -in sp-private.pem \
  -out sp-private-encrypted-pkcs8.pem
```

OpenSSL normally prompts for a passphrase when creating EncryptedPrivateKeyInfo by default. The output file typically has header `BEGIN ENCRYPTED PRIVATE KEY`. **Do not assume** Spring Boot's `private-key-location` or `RsaKeyConverters.pkcs8()` in your running version supports every EncryptedPrivateKeyInfo PBE algorithm/password. You need a tested PBE loader, keystore, or secret integration.

Avoid passing passwords directly on the command line where they can leak via process listings, shell history, or CI logs. If using a password file/secret manager, access permissions to the password must be protected **separately** from the private key.

### 6.4. Packaging key/cert into a PKCS#12 store

Given an existing valid private key and X.509 certificate pair:

```bash
openssl pkcs12 -export \
  -inkey sp-private.pem \
  -in sp-cert.pem \
  -out sp-keys.p12 \
  -name sp-signing
```

OpenSSL will prompt for an export password (and the input key passphrase if needed). If a proper certificate chain exists, you can add `-certfile chain.pem` per agreement; never bundle unrelated CAs. Exporting PKCS#12 produces **a container holding a private key**; protect both `.p12` and its password as secrets rather than assuming "having a password" is enough.

Inspect aliases/entries/chains without printing the private key:

```bash
keytool -list -v -storetype PKCS12 \
  -keystore sp-keys.p12
```

`keytool` may prompt for the password. Check the alias, entry type (e.g., `PrivateKeyEntry`), certificate subject/issuer, validity, chain, and ensure the alias used by Java code exists. **Do not** use `keytool -list` as proof that the cert matches the private key without verifying the keypair.

### 6.5. Matching public key of private key with certificate

A private key and certificate pair must share the **same public key**. Check without displaying the private key:

```bash
openssl pkey -in sp-private.pem -pubout -outform DER \
  | openssl dgst -sha256

openssl x509 -in sp-cert.pem -pubkey -noout \
  | openssl pkey -pubin -outform DER \
  | openssl dgst -sha256
```

Both SHA-256 digests of the **identically normalized SPKI DER** must be equal for a matching keypair. The commands illustrate POSIX shell binary pipelines; older PowerShell versions may require special binary handling to prevent altering piped bytes.

Matching public keys **does not by itself authenticate the partner**, nor does it prove the certificate is still valid/accepted or that the private key has not been compromised. It is strictly a keypair consistency check.

### 6.6. Generating a test RSA pair to understand the pipeline

In a **lab environment**, you can generate an illustrative RSA key and self-signed certificate:

```bash
openssl genpkey -algorithm RSA \
  -pkeyopt rsa_keygen_bits:3072 \
  -out lab-sp-private.pem

openssl req -new -x509 \
  -key lab-sp-private.pem \
  -out lab-sp-certificate.pem \
  -days 30 \
  -subj "/CN=lab-saml-sp"
```

A self-signed certificate **does not automatically make the SP a trusted partner**. The IdP must have an agreement/config importing the exact public cert; lab setups are for testing parsers, certificate/key matching, and credential creation flows. Lab private keys must still be protected and never committed to repositories.

## 7. Spring Boot: declaring PEM and PKCS#8 via Resource location

The example below targets Spring Boot 3.x / Spring Security 6.x and a **Servlet SAML2 Relying Party** application with `spring-security-saml2-service-provider`. Production configs must pair with verified IdP metadata/certificates.

File `src/main/resources/application.yml`:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "urn:example:portal:prod:sp"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-sign-pkcs8.pem"
                  certificate-location: "file:/etc/saml/certs/sp-sign.crt"
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-decrypt-pkcs8.pem"
                  certificate-location: "file:/etc/saml/certs/sp-decrypt.crt"
            assertingparty:
              metadata-uri: "file:/etc/saml/idp-metadata.xml"
```

**Exact explanation:**

- `corp` is the **registrationId** of the SP–IdP relationship, not a PKCS#12 alias and not the SP Entity ID.
- `entity-id` is the SP Entity ID that the IdP must use as audience and SP identifier per agreement.
- `signing.credentials[*]` loads the **SP signing private key** and matching X.509 certificate to sign AuthnRequest/appropriate messages.
- `decryption.credentials[*]` loads the **SP decryption private key** and matching X.509 certificate for EncryptedAssertion/EncryptedID.
- `assertingparty.metadata-uri` points to IdP metadata; it is **not** a private key path and does not by itself prove the metadata signature was verified. Manage metadata sources/trust separately.
- `file:` references a filesystem path inside the **container or machine running the JVM**, not a developer's local folder.
- `classpath:` references resources packaged on the classpath; **unsuitable for embedding production private keys into JARs/images**, because artifacts are broadly readable.
- `sp-sign-pkcs8.pem` and `sp-decrypt-pkcs8.pem` in the example must be in a key format supported by the loader; do not put encrypted PKCS#8 into location properties and assume Boot will handle passphrases automatically.

When an IdP does not require signed AuthnRequests or does not send EncryptedAssertions, the minimum credential set differs. **You are not forced to add private keys just to receive signed SAML Responses**: the SP still needs the **IdP public verification certificate**. This lesson configures both signing and decryption as an example of a system having **both requirements**.

### 7.1. Classpath vs. file across environments

| Environment | Common practice | What to avoid |
| --- | --- | --- |
| Local development | Self-generated demo keys kept outside source tree or in test profile | Committing demo private keys and reusing them in staging/prod |
| VM/bare metal | Files/keystores in secured directory readable only by service account | `chmod 777`, shared home folders, unencrypted backups |
| Docker/Kubernetes | Secret volume or CSI/Vault mount; container file path | `COPY private.key` into image, putting secrets in build args/layers |
| HSM/PKCS#11 | Signing/decryption handle/provider/API; key non-exportable | Forcing plaintext private key export to match YAML |
| Cloud KMS | Signing/decryption API/provider supporting required algorithms | Confusing "secret storage" APIs with compatible XMLDSig/RSA-OAEP signing |

**Important note:** The Spring Boot `private-key-location` property is convenient when the key exists as a file supported by converters. It **does not imply automatic support for arbitrary PKCS#12 aliases, HSM handles, or encrypted PEMs**; those typically require supplying `RelyingPartyRegistration`/credentials via Java config and an appropriate provider.

## 8. Spring Security Java: reading PEM X.509 and RSA PKCS#8

Spring Security documentation shows `RsaKeyConverters.pkcs8()` for reading RSA private keys and `CertificateFactory.getInstance("X.509")` for reading certificates.

The snippet below is **a method/fragment inside a Spring project that already has imports/dependencies**, not a standalone Java file:

```java
import java.io.InputStream;
import java.security.interfaces.RSAPrivateKey;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.security.converter.RsaKeyConverters;
import org.springframework.security.saml2.core.Saml2X509Credential;

// Unencrypted RSA PKCS#8 private key protected by a secret volume.
Resource keyFile = new FileSystemResource(
    "/run/secrets/saml/sp-sign-pkcs8.pem");
Resource certificateFile = new FileSystemResource(
    "/etc/saml/certs/sp-sign.crt");

RSAPrivateKey privateKey;
try (InputStream in = keyFile.getInputStream()) {
    privateKey = RsaKeyConverters.pkcs8().convert(in);
}

X509Certificate certificate;
try (InputStream in = certificateFile.getInputStream()) {
    certificate = (X509Certificate)
        CertificateFactory.getInstance("X.509")
            .generateCertificate(in);
}

Saml2X509Credential signingCredential =
    Saml2X509Credential.signing(privateKey, certificate);
```

Key takeaways:

- `RsaKeyConverters.pkcs8()` is a **dedicated converter for RSA PKCS#8** per the Spring Security API; it does not automatically understand PKCS#1, EC, encrypted PKCS#8, or HSM keys.
- `CertificateFactory` parses **public X.509 certificates** and needs no private key to read them.
- `Saml2X509Credential.signing(...)` represents **SP signing of SAML messages**. For **SP decryption**, use `Saml2X509Credential.decryption(privateKey, certificate)`.
- Successfully loading key/cert does not prove the keypair matches; verify before the system starts taking traffic.
- `try-with-resources` closes the stream, yet the private key object remains in process memory for the credential's lifecycle; manage host/container and heap/dump access accordingly.

Never load the IdP private key into the SP. The SP only needs the trusted provisioned IdP public certificate for **verification**, via `Saml2X509Credential.verification(idpCert)` or policy-verified IdP metadata.

### 8.1. Putting credentials into RelyingPartyRegistration

The next example uses `signingCredential` and `decryptionCredential` created from secure sources:

```java
RelyingPartyRegistration registration = RelyingPartyRegistrations
    .fromMetadataLocation("file:/etc/saml/idp-metadata.xml")
    .registrationId("corp")
    .entityId("urn:example:portal:prod:sp")
    .signingX509Credentials(
        credentials -> credentials.add(signingCredential))
    .decryptionX509Credentials(
        credentials -> credentials.add(decryptionCredential))
    .build();
```

This is a **Java configuration fragment in Spring Security**, requiring a `RelyingPartyRegistrationRepository` bean, Java imports, and the matching API version. `fromMetadataLocation(...)` is only a metadata import mechanism; **it does not mean signed metadata verification policy has been satisfied**. When using a custom repository instead of Spring Boot auto-configuration, verify the filter chain **actually references that repository**.

## 9. Reading a PKCS#12 KeyStore in Java

If the organization provisions `sp-keys.p12` instead of PEM files, JCA provides `KeyStore.getInstance("PKCS12")`. A PKCS#12 store can contain a **PrivateKeyEntry** under alias `sp-signing` and a certificate chain.

**Java snippet for use in an application with a provisioned keystore**:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.Key;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.cert.Certificate;
import java.security.cert.X509Certificate;

char[] storePassword = obtainPasswordFromProtectedSource();
char[] keyPassword = obtainKeyPasswordFromProtectedSource();

KeyStore store = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(
        Path.of("/run/secrets/saml/sp-keys.p12"))) {
    store.load(in, storePassword);
}

Key key = store.getKey("sp-signing", keyPassword);
Certificate certificate = store.getCertificate("sp-signing");

if (!(key instanceof PrivateKey privateKey)
        || !(certificate instanceof X509Certificate x509Certificate)) {
    throw new IllegalStateException(
        "sp-signing must be a PrivateKeyEntry with X509Certificate");
}

Saml2X509Credential credential =
    Saml2X509Credential.signing(privateKey, x509Certificate);
```

**Example limitations:** `obtainPasswordFromProtectedSource()` is an illustrative name for retrieving passwords from a secret manager/protected file implemented by the app, **not a JDK API**; the snippet does not run standalone. In real apps, handle `UnrecoverableKeyException`, missing aliases, file permissions, and zeroing **copied `char[]` passwords** when no longer needed where controllable. If PKCS#12 shares the store/key password, both variables may come from the same secure source; never assume all keystores allow distinct passwords or that all providers handle aliases identically.

**PKCS#12 advantages:** multiple aliases, certificate chains, passwords, and standard Java KeyStore API. **Limitation:** Spring Boot `private-key-location: file:/.../sp-keys.p12` typically **does not resolve alias `sp-signing` like the KeyStore API**. To use `.p12`, load it via KeyStore/provider and pass `Saml2X509Credential` into `RelyingPartyRegistration` (or use a verified integration provided by your version/framework).

### 9.1. Keystore vs. truststore: different purposes, not necessarily different formats

- A **keystore** usually holds the **application's own private keys**, certificates, and chains.
- A **truststore** usually holds **other parties' certificates/public trust anchors** for the app to verify them.
- **PKCS#12** can serve as either a **keystore or truststore**; "store" describes usage role, not a mandatory file type.
- The **JVM's default TLS truststore** normally holds many CAs trusted for HTTPS. It **is not automatically the list of IdPs allowed to sign SAML assertions**. SAML trust must bind certificates to an **IdP Entity ID/registration** and approved policy.

For example, a public IdP certificate can be imported into a dedicated PKCS#12 truststore:

```bash
keytool -importcert -storetype PKCS12 \
  -alias corp-idp-signing \
  -file idp-signing.crt \
  -keystore saml-idp-trust.p12
```

**Only import after verifying the certificate source** via trusted IdP metadata/admin channel. If you import a certificate supplied by an unverified response or email, even a heavily protected truststore can end up holding an **attacker's key**.

## 10. Standalone Java 17: PEM and PKCS#8 round-trip without external libraries

This program is designed to **compile/run with JDK 17+**, without needing Spring Security or OpenSSL. It demonstrates:

- Generating a 2048-bit test RSA keypair.
- Extracting the private key in **PKCS#8 DER** form via `PrivateKey.getEncoded()`.
- Wrapping private DER into **PEM `BEGIN PRIVATE KEY`**.
- Wrapping `SubjectPublicKeyInfo` public key into **PEM `BEGIN PUBLIC KEY`**.
- Parsing back with `PKCS8EncodedKeySpec` and `X509EncodedKeySpec`.
- Signing/verifying a mock string; altering the data causes verification to fail.
- Rejecting a PEM labeled `PUBLIC KEY` when used where `PRIVATE KEY` is expected.

**Scope:** this is strictly an encoding/PKCS#8 and RSA signature test example. It **does not create X.509 certificates**, does not build PKCS#12 keystores, does not sign XML AuthnRequests, does not configure SAML federation, and **must not log `privatePem` in production**.

File `PemPkcs8Demo.java`:

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
import java.util.Base64;

public class PemPkcs8Demo {
    static String toPem(String label, byte[] der) {
        String body = Base64.getMimeEncoder(
            64, new byte[] {'\n'}).encodeToString(der);
        return "-----BEGIN " + label + "-----\n" + body
            + "\n-----END " + label + "-----\n";
    }

    static byte[] fromPem(String pem, String label) {
        String header = "-----BEGIN " + label + "-----";
        String footer = "-----END " + label + "-----";
        String cleaned = pem.trim();
        if (!cleaned.startsWith(header) || !cleaned.endsWith(footer)) {
            throw new IllegalArgumentException("Unexpected PEM label");
        }
        String content = cleaned.substring(
            header.length(), cleaned.length() - footer.length());
        return Base64.getMimeDecoder().decode(content);
    }

    static byte[] sign(PrivateKey key, String value) throws Exception {
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(key);
        signer.update(value.getBytes(StandardCharsets.UTF_8));
        return signer.sign();
    }

    static boolean verify(PublicKey key, String value, byte[] signed)
            throws Exception {
        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(key);
        verifier.update(value.getBytes(StandardCharsets.UTF_8));
        return verifier.verify(signed);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();

        String privatePem = toPem("PRIVATE KEY",
            pair.getPrivate().getEncoded());
        String publicPem = toPem("PUBLIC KEY",
            pair.getPublic().getEncoded());

        KeyFactory factory = KeyFactory.getInstance("RSA");
        PrivateKey privateKey = factory.generatePrivate(
            new PKCS8EncodedKeySpec(
                fromPem(privatePem, "PRIVATE KEY")));
        PublicKey publicKey = factory.generatePublic(
            new X509EncodedKeySpec(
                fromPem(publicPem, "PUBLIC KEY")));

        byte[] signature = sign(privateKey, "AuthnRequest");
        System.out.println("privateFormat=" + privateKey.getFormat());
        System.out.println("privateHeader="
            + privatePem.startsWith("-----BEGIN PRIVATE KEY-----"));
        System.out.println("publicHeader="
            + publicPem.startsWith("-----BEGIN PUBLIC KEY-----"));
        System.out.println("validSignature="
            + verify(publicKey, "AuthnRequest", signature));
        System.out.println("tamperingDetected="
            + !verify(publicKey, "ChangedRequest", signature));

        boolean rejected = false;
        try {
            fromPem(publicPem, "PRIVATE KEY");
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        System.out.println("wrongPemLabelRejected=" + rejected);
    }
}
```

Run with JDK 17 or later:

```bash
javac --release 17 PemPkcs8Demo.java
java PemPkcs8Demo
```

Exact stdout in a standard JDK 17 implementation with default RSA provider:

```text
privateFormat=PKCS#8
privateHeader=true
publicHeader=true
validSignature=true
tamperingDetected=true
wrongPemLabelRejected=true
```

**Output explanation:**

- `privateFormat=PKCS#8`: the parsed private key object has PKCS#8 format.
- `privateHeader=true`: the string is wrapped with the **PRIVATE KEY** label, valid for unencrypted PKCS#8 in the example.
- `publicHeader=true`: the public key has the **PUBLIC KEY** label, yet is **not a CERTIFICATE**.
- `validSignature=true`: private/public keys belong to the same RSA pair.
- `tamperingDetected=true`: the signature for "AuthnRequest" does not verify on "ChangedRequest".
- `wrongPemLabelRejected=true`: the application does not interpret a public PEM as a private PEM.

The `fromPem` helper intentionally **handles only a single self-generated PEM block**, not production PEM parsing. Never pass attacker-supplied file/XML data into it as a full format-validating parser. It does not support encrypted PKCS#8, multiple PEM blocks, passwords, arbitrary comments, certificate chains, or EC algorithms.

In production, **never print PEM private keys** to debug. If an HSM key is non-exportable, `getEncoded()` may return `null` or be blocked by the provider; that can be a **security feature**, not a bug to work around by exporting the key.

## 11. Secret files, environment variables, HSM, and KMS: choosing key delivery

When deploying an application, there are several ways to deliver cryptographic material to the JVM:

| Delivery method | Advantages | Risks and conditions |
| --- | --- | --- |
| Read-only secret file/volume | Compatible with `file:` Resource, easy filesystem permissions | If mount/host is read illegally, key leaks; requires permissions and rotation |
| PKCS#12 file + password | Single container with aliases/chain; easy JCA KeyStore use | Password must be protected separately; file can be copied |
| Environment variable | Easy orchestration | Can leak via process inspection, debug dumps, logs; multiline PEM may hit encoding issues |
| Kubernetes Secret | Integrates with RBAC and volume projection | Base64 in manifests **is not encryption**; needs encryption at rest, RBAC, node isolation |
| CSI Secret Store/Vault | Reduces secrets stored in images; supports access/rotation flows | Must manage identity, sync, availability, caching, and restart/reload |
| HSM/PKCS#11 | Private key **non-exportable** from device; supports signing/decryption ops | Provider integration, sessions, algorithms, and performance; not all libraries support every mode |
| Cloud KMS/remote signer | Uses IAM and auditing to restrict crypto operations | KMS API may not inherently support XMLDSig/RSA-OAEP or needed key types; requires vetted adapter |

**Do not confuse "storing a secret" with "performing signing/decryption".** A secret manager can hand a PEM file to the app, yet the private key still sits in JVM memory. An HSM/KMS can keep the private key outside the process and perform operations remotely, yet Spring Security/OpenSAML must be able to use the corresponding Key/provider. Never expect `file:/...` to invoke an HSM automatically.

### 11.1. Avoiding common key leaks

- Never commit keys/certificates containing private keys to Git, even on internal branches or "private repos". Git history can retain old versions after deletion.
- Never place secrets in Dockerfile `COPY`, `ENV`, build args, image layers, public Helm values, or CI artifacts.
- Never print key contents, keystore passwords, Base64 secrets, or full heap dumps into logs/traces/tickets.
- Never share the same production key across dev, UAT, and staging.
- Never pass passphrases directly as CLI arguments where they can appear in process listings/shell history.
- Never set file permissions to `0777` just to work around `Permission denied`.
- Never assume a reverse proxy's TLS cert can double as an SP SAML signing certificate; they have **different lifecycles, owners, and trust policies**.

## 12. Kubernetes example: mounting keys safely for the JVM

Suppose the application runs as a non-root account with secrets provisioned via an approved governance mechanism.

**PodSpec snippet** (placed under a Deployment's `spec.template.spec`; this is not a complete Kubernetes manifest):

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 2000
  fsGroup: 2000

containers:
  - name: portal
    image: registry.example.test/portal:stable
    volumeMounts:
      - name: saml-key-files
        mountPath: /run/secrets/saml
        readOnly: true

volumes:
  - name: saml-key-files
    secret:
      secretName: portal-saml-keys
      defaultMode: 0440
```

Conditions:

- `portal-saml-keys` must be created beforehand by an authorized secret management system; **never** put private key bytes in READMEs/manifests.
- The example uses `runAsUser` 10001, group 2000, and `fsGroup` 2000 to illustrate group-read file access. Effective permissions depend on container runtime, CSI/driver, security policy, and volume ownership; **verify inside a real Pod**.
- Secret mounted at `/run/secrets/saml`; Spring Boot `file:/run/secrets/saml/sp-sign-pkcs8.pem` must point to the **exact key name/file** projected in the volume.
- `defaultMode: 0440` permits owner/group reads; it is not complete protection if other processes share the group. Enforce RBAC, namespaces, node isolation, restricted service accounts, and auditing.
- Base64-encoded Kubernetes Secrets are not cryptography on their own; configure **encryption at rest**, API server/etcd permissions, and backup security.
- When the volume updates, files may change while Spring Security **does not automatically reload credentials loaded into `RelyingPartyRegistration`**. Design an explicit repository reload/rebuild, rolling restart, or caching strategy, and avoid swapping keys mid-flight during an active SAML flow.

If keys serve multiple purposes, keep **file names/key ring configs distinct**, and do not mount every namespace secret into one container merely for convenience.

### 12.1. Docker and Linux services

On VM/Linux hosts, grant private key read permissions only to the service process. Example paths:

```text
/run/secrets/saml/sp-sign-pkcs8.pem
/etc/saml/certs/sp-sign.crt
/etc/saml/idp-metadata.xml
```

Place private keys in a secret volume/protected file tier, and place public certificates and metadata where sources can be governed/audited. Mode `0400` works when the file belongs to the exact owner, yet fails if the process runs as another user. Set valid ownership/group rather than relaxing permissions to world-readable.

**Do not treat a read-only mount as leak-proof**: if the process is compromised and has permission to read the key, an attacker can still read it. Read-only only limits file tampering; confidentiality requires defense in depth.

## 13. Keystores across multiple IdPs and environments

An application may have multiple `RelyingPartyRegistration` entries:

```text
registration employee:
  SP entityId      = urn:example:portal:prod:sp
  SP signing key   = sp-employee-sign-2026
  SP decryption    = sp-employee-dec-2025 / sp-employee-dec-2026
  IdP verification = idp-employee-signing

registration partner:
  SP entityId      = urn:example:portal:prod:sp
  SP signing key   = sp-partner-sign-2026
  SP decryption    = sp-partner-dec-2026
  IdP verification = idp-partner-signing
```

Sharing the same SP Entity ID across two registrations can be valid if agreements with each IdP permit it; sharing private keys is **not mandatory**. Conversely, you may intentionally reuse one SP signing key across multiple registrations, yet that must be approved and explicitly configured.

**Credential selection rules:**

1. Determine the trusted registration first, using Spring Security mechanisms and proper request/correlation context.
2. Select SP signing/decryption credentials belonging to **that registration**.
3. When decrypting `EncryptedAssertion`, only try private keys in the **authorized key ring**; `KeyName` in a SAML Response is an **untrusted hint**, not authorization to unlock a secret.
4. When verifying SAML Response/Assertion, only trust IdP certificates bound to the **approved IdP/registration**.
5. When using a multi-alias keystore, aliases must be mapped by governed configuration, **never** taken directly from user-supplied HTTP parameters.
6. Check tenant membership/business authorization **after** authentication; never infer user privileges from key/cert names.

### 13.1. Never let DEV and PROD share private keys

A production private key used in test environments widens the blast radius: someone with low debug access in DEV could steal a key that PROD also trusts. Always:

- Separate secret stores / namespaces / IAM principals / keystores by environment.
- Use meaningful aliases, e.g., `portal-prod-saml-sign-2026`.
- Block accidental import of DEV certificates into PROD IdPs.
- Automatically check fingerprints and SP Entity IDs in deployment pipelines against an **allowlist**.

## 14. Rotation: updating keys without disrupting SSO

**Key rotation** involves both SP and IdP, not merely swapping `.pem`/`.p12` files.

### 14.1. SP signing key rotation

1. Generate a new signing private key/certificate through an approved process and store it in the secret store.
2. IdP imports/trusts the **new SP public certificate** for the matching SP Entity ID, with overlap if supported by the partner.
3. SP begins signing AuthnRequests with the new private key **after the IdP is ready to verify**.
4. Verify HTTP-Redirect `SigAlg/Signature` or POST XMLDSig against the new certificate.
5. Once the transition window ends, remove the old cert/key from trust stores and live backups per policy.

Switching the private key before the IdP is updated causes the IdP to reject AuthnRequests due to signature mismatch. **Never disable signing requirements to work around rotation errors**.

### 14.2. SP decryption key rotation

1. Load the **new private key on the SP** before the IdP switches to encrypting assertions with the new public certificate.
2. IdP adds/switches to the **new SP encryption certificate**.
3. SP retains both old and new private keys during the approved transition window if needed to handle ciphertext encrypted by the IdP using the old cert.
4. Test EncryptedAssertions for both certificates and monitor unwrap/decryption errors.
5. Once the IdP no longer encrypts with the old cert and in-flight requests have completed, retire the old private key.

This order differs from signing: **the new decryption key must be in place before the IdP sends new ciphertext**.

### 14.3. IdP verification certificate rotation

The IdP owns the private key signing assertions. The SP must obtain the **new IdP public certificate** via trusted metadata/configuration, support overlap per policy, and verify signatures. **Never** automatically trust a new X.509 certificate merely because it appears in an unverified XML Response.

### 14.4. Keystore reload and certificate expiry

Some Spring Security registrations are built and cached in memory on application startup. Replacing a `.p12` file or secret volume **does not mean** the running registration loaded the new key. You must:

- Check how the provider/repository caches credentials.
- Design controlled rolling restarts, registration refresh/rebuilds, or tested dynamic keystore mechanisms.
- Make file swaps atomic so the process never reads a half-written file.
- Provide safe health checks/tracing for active key status and expiration milestones.
- Avoid publishing a new cert in metadata before the new private key is ready.

Certificate expiry, private key rotation, and metadata refresh are **three related yet distinct operational flows**. Never simply edit an expiration date in config; certificates are signed artifacts governed by dedicated policies.

## 15. Troubleshooting: format, trust, and deployment errors

| Symptom | Common cause | Safe investigation path |
| --- | --- | --- |
| `InvalidKeySpecException` when parsing private key | PKCS#1 passed to PKCS#8 loader; wrong algorithm or corrupt DER | Inspect PEM label/ASN.1 with proper tools; convert properly to PKCS#8 |
| `IllegalArgumentException` / "invalid PEM" | Missing header/footer, `PUBLIC KEY` confused with `PRIVATE KEY`, bad newlines/structure | Check object type and mounted file without printing the key |
| `EncryptedPrivateKeyInfo` unreadable | Loader only supports unencrypted PKCS#8 or missing passphrase/PBE provider | Use a secure loader with proper password/keystore support |
| `NoSuchAlgorithmException` / `InvalidKeyException` | Provider lacks RSA/EC algorithm; incompatible key type | Check JDK/provider, key type, and algorithm policy |
| Spring reports unreadable resource | Wrong `file:`/`classpath:`, host path differs from container path | Inspect paths from inside the process/container |
| `AccessDeniedException` / `Permission denied` | Secret file ownership/group/mode denies app user read access | Check UID/GID, fsGroup, file mode; never use 0777 |
| PKCS#12 has alias yet `getKey` returns null | Wrong alias or entry is `trustedCertEntry` | Run `keytool -list` and select exact `PrivateKeyEntry` |
| `UnrecoverableKeyException` | Wrong keystore/key password or PBE/provider issue | Check secret source and password mapping; never log passwords |
| `.p12` file passed to `private-key-location` yet Boot fails to read | Property expects a private-key file, does not auto-lookup PKCS#12 aliases | Use Java `KeyStore` or compatible keystore integration |
| Private key and certificate load yet signing/decryption fails | Keypair mismatch; IdP holds old cert | Compare public key fingerprints/cert currently active at IdP |
| IdP reports AuthnRequest signature invalid | SP signing key/cert mismatch or IdP pinned a different cert | Verify keypair, imported certificate, and algorithm/binding |
| SP cannot decrypt EncryptedAssertion | SP decryption key does not match cert used by IdP | Check SP encryption cert/fingerprint and key ring in registration |
| SP reports assertion signature invalid | Wrong IdP verification cert/issuer | Check trusted IdP metadata and verification credential; never pull arbitrary cert from response |
| Valid certificate yet still rejected | Wrong SAML issuer, audience, recipient, key purpose, or policy | Separate SAML trust from TLS/PKIX and federation conditions |
| Fails only right after rotation | Pod hasn't reloaded secret, IdP not updated, missing overlap | Check runtime key version/fingerprint and transition plan |
| Fails only on Kubernetes | Key permissions, volume projection, service account, fsGroup | Inspect UID, GID, mode, and mount path directly inside the Pod |
| Fails only on newer JVM | Provider/algorithm or keystore compatibility differences | Compare JDK versions, KeyStore types, and PKCS#12 algorithms |
| Using HSM yet `getEncoded()` returns null | Key is non-exportable per HSM policy | Use signing/decryption provider via handle; never force export |
| Secret leaked in build logs | Script ran `cat` on private key or echoed environment password | Revoke/rotate key and scrub logs; treat as a security incident |

### 15.1. Troubleshooting procedure without exposing keys

1. Confirm `registrationId`, SP Entity ID, IdP Entity ID, and expected **credential purpose**.
2. Inspect **PEM label/keystore type** or `keytool -list`; never print private key contents.
3. Verify the Java process reads the exact **container path**, file permissions, owner, and secret version.
4. Compare public key/certificate fingerprints using safe tools.
5. Distinguish **parse errors**, **password errors**, **signing/decryption errors**, and **SAML validation errors**; never lump them together as "SSO broken".
6. Check signing algorithm, XML Encryption transport/content algorithm, or JCA provider version compatibility.
7. Verify **which public certificate the IdP currently stores**, not just what sits on the SP.
8. Confirm whether the registration was reloaded/restarted after rotation.
9. Log only error codes, registration, public certificate fingerprint, alias, algorithm, and timestamps as allowed by policy.
10. Never add `print(privateKey)`, `cat sp-private.pem`, full heap dumps, or plaintext SAML assertions to logs to debug errors.

**Layer separation:** unparseable private key ⇒ format/loader issue; parseable private key yet signature fails ⇒ keypair/trust/binding issue; decryption succeeds yet authentication fails ⇒ SAML signature/issuer/audience/conditions issue. Never work around errors by disabling signature validation, dropping encryption policy, or accepting arbitrary certificates.

## 16. Practical test matrix

| Test case | Input/configuration | Expected |
| --- | --- | --- |
| Valid unencrypted PKCS#8 | `BEGIN PRIVATE KEY` RSA, PKCS#8 DER | Readable by JCA/Spring loader |
| Traditional PKCS#1 | `BEGIN RSA PRIVATE KEY` passed to PKCS#8 converter | Rejected/fails to parse; conversion required |
| Encrypted PKCS#8 | `BEGIN ENCRYPTED PRIVATE KEY` without passphrase loader | Fails cleanly; never strips encryption silently |
| Swapped private/public PEM | `BEGIN PUBLIC KEY` in private key slot | Rejected |
| PEM certificate | Valid X.509 `BEGIN CERTIFICATE` | Parseable by `CertificateFactory` |
| DER certificate | Binary DER supplied in proper place | Readable by DER-supporting loaders; never assume all properties accept all inputs |
| Matching key/cert | Public key derived from private = cert public key | PASS keypair check |
| Mismatched key/cert | SP A private key, SP B certificate | Fails pre-deploy keypair check |
| Keystore right alias | PKCS#12 with valid `PrivateKeyEntry` | `getKey`/`getCertificate` return proper objects |
| Wrong alias | `sp-signing` missing | Fails safely; never picks arbitrary alias |
| Wrong password | Wrong PKCS#12 or encrypted key password | Fails without printing secret |
| Unreadable private key | Service user lacks read permission | Fails health/startup clearly; never change to world-readable |
| Java provider lacks algorithm | Unsupported RSA/EC/HSM mode | Fails with compatibility error; no weak fallback |
| Right signing credential | SP sends AuthnRequest signed with IdP-trusted key | IdP verifies successfully |
| Old SP signing cert | IdP pins a different certificate | IdP rejects until synchronized |
| Old/new decryption keys | IdP uses new cert; SP holds both old and new keys | Decrypts with new key; honors overlap window |
| IdP assertion cert changes | SP receives valid metadata/trust update | Accepts only assertions signed by allowed keys |
| Secret volume updated | Pod sees new file yet repository still caches old key | Test detects reload/restart is needed |
| Non-exportable HSM key | `PrivateKey.getEncoded() == null` | Works via provider/HSM; not treated as broken key |
| Two registrations | IdP A and B use separate key rings | Never opens wrong registration's key/trust |
| DEV/PROD | DEV certificate used in PROD | Rejected per policy; never share private keys |
| SAML response from unknown IdP | Response embeds arbitrary certificate | Not auto-trusted; rejected before Authentication |
| Leak detection | Key appears in Git/CI artifact/log | Pipeline alerts, revokes, and initiates incident response |

**Key format tests do not replace end-to-end SAML tests**. Once keys load successfully, test against a staging IdP to verify Signed AuthnRequests, EncryptedAssertions, Response signature validation, and business conditions.

## 17. Operational deployment checklist

- [ ] Distinguished PEM/DER (encoding), PKCS#8/PKCS#1 (structure), X.509 certificate/SPKI public key, and PKCS#12 (container).
- [ ] Private keys supplied in exact algorithms and formats supported by Spring/JCA loaders.
- [ ] Never feed raw `BEGIN RSA PRIVATE KEY` into a PKCS#8 loader, and never rewrite PEM headers to "convert".
- [ ] Verified that the certificate's public key **matches** the corresponding private key.
- [ ] SP signing, SP decryption, IdP verification, and metadata verification each have **dedicated credential purposes**, never swapped.
- [ ] Selected `file:` resources using **actual paths inside the JVM/container**, avoiding host vs. container mix-ups.
- [ ] Never embedded production private keys in classpath/JAR/images/source control.
- [ ] For PKCS#12, verified alias/password/entry type/chain; if Boot does not support alias locations directly, used Java KeyStore.
- [ ] Passwords/secrets supplied via secure governance channels; never logged to stdout, exception messages, or CI artifacts.
- [ ] Private keys have minimal permissions and explicit runtime identity, including UID/GID/fsGroup in Kubernetes.
- [ ] Kubernetes Secrets protected by RBAC, encryption at rest, and secure backups; Base64 is not treated as encryption.
- [ ] If using HSM/PKCS#11/KMS, signing/decryption providers tested for compatibility with algorithms and OpenSAML.
- [ ] Defined cert/key lifecycle, rotation schedule, signing/decryption overlap, cutover, and rollback.
- [ ] Verified active registration/trusted certificates after reload/rolling restart.
- [ ] Tested wrong keys, mismatched certificates, wrong passwords, compromised keys, and expired certificates.
- [ ] Even after credentials work, Spring Security still validates SAML issuer, signature, audience, recipient, timestamps, correlation, and replay.
- [ ] All IdP/partner keys/certificates onboarded through trusted processes; never add unknown certs to truststores to silence SSO errors.
- [ ] Monitoring/alerting configured for certificate expiry, secret freshness, and signing/decryption failures per registration.

## 18. Self-check questions

**1. Is a `sp.key` file guaranteed to be PKCS#8?**

No. File extensions are just conventions. Inspect the PEM label and DER structure; `BEGIN RSA PRIVATE KEY` is typically PKCS#1, whereas `BEGIN PRIVATE KEY` is typically unencrypted PKCS#8.

**2. Are PEM and PKCS#8 two interchangeable formats?**

No. PEM is a **text wrapper/encoding**; PKCS#8 is a **private key structure**. A PKCS#8 key can be stored as binary DER or Base64 PEM.

**3. Why can't `BEGIN ENCRYPTED PRIVATE KEY` be passed directly to `PKCS8EncodedKeySpec`?**

Because its bytes hold **EncryptedPrivateKeyInfo**. It must be decrypted with the proper password/PBE provider first to extract PrivateKeyInfo for KeyFactory. Not all Spring Boot private-key loaders do this automatically.

**4. Is `BEGIN PUBLIC KEY` equivalent to `BEGIN CERTIFICATE`?**

No. An SPKI public key does not carry X.509 certificate metadata/signatures. JCA `X509EncodedKeySpec` parses public SPKI, whereas `CertificateFactory` parses certificates.

**5. If you already have the SP certificate, is that enough to sign AuthnRequests or decrypt EncryptedAssertions?**

No. The SP needs the **matching private key**, while the IdP needs the **SP public certificate** to verify signatures or encrypt for the SP.

**6. How does PKCS#8 differ from PKCS#12?**

PKCS#8 describes private-key information; PKCS#12 is a container/keystore holding private keys, certificate chains, and aliases. Java reads PKCS#12 via `KeyStore`.

**7. Does Spring Boot automatically understand `file:/run/secrets/sp-keys.p12` as a private key and auto-select an alias?**

Do not assume so. `private-key-location` normally targets key files in loader-supported formats; PKCS#12 requires KeyStore/provider and explicit alias selection unless your specific version/integration documents otherwise.

**8. If the certificate and private key parse cleanly yet their public keys do not match, how do you fix it?**

Use the exact matching key/certificate pair; never skip validation or substitute an IdP certificate. Verify via public-key fingerprints and compare against IdP config.

**9. If an HSM key has `getEncoded() == null`, is it broken?**

No. Many HSMs intentionally prevent exporting private keys; the application must use the appropriate JCA provider/handle or crypto service.

**10. What must happen when the IdP switches to encrypting assertions with a new SP certificate?**

The new private key must be loaded on the SP **before** the IdP emits new ciphertext. Maintain an old/new key overlap period if permitted, then retire the old key after synchronization.

**11. If HTTPS is enabled, is it safe to bundle the SP private key inside the JAR?**

No. TLS protects the transport channel; it does not stop anyone who can read the JAR/image or host from extracting the private key. Keys must be stored and permissioned separately.

**12. Why might a valid TLS truststore still be insufficient for SAML response verification?**

SAML trust must bind **approved public certificates** to an IdP entityID/registration and assertion verification policy. Being issued by a public CA does not prove an IdP is authorized to issue assertions for your SP.

## 19. Official references

- Spring Security, **SAML 2.0 Login Overview**, Credentials section, `RsaKeyConverters.pkcs8()`, `Saml2X509Credential`: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security, **Authenticating SAML Responses**, Customizing Decryption section: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security, **Saml2X509Credential API**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/core/Saml2X509Credential.html
- Spring Boot 3.4, **SAML 2.0 Relying Party**, `signing.credentials` and `decryption.credentials`: https://docs.spring.io/spring-boot/3.4/reference/web/spring-security.html
- Oracle Java 17, **JCA Reference Guide**, KeyStore, PKCS12, JKS, and PKCS11: https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html
- Oracle Java 17, **CertificateFactory API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertificateFactory.html
- Oracle Java 17, **PKCS8EncodedKeySpec API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/PKCS8EncodedKeySpec.html
- OpenSSL, **openssl-pkcs8** — PKCS#8 conversion and `-topk8/-nocrypt`: https://docs.openssl.org/master/man1/openssl-pkcs8/
- OpenSSL, **openssl-pkcs12** — packaging private keys/certs into PKCS#12: https://docs.openssl.org/master/man1/openssl-pkcs12/
- Kubernetes, **Secrets** — volumes, permissions, RBAC, and encryption at rest: https://kubernetes.io/docs/concepts/configuration/secret/

**Key takeaway:** PEM is a **text wrapper**, PKCS#8 is a **private key structure**, PKCS#12 is a **keystore container**, an X.509 certificate is **public material binding a public key to an identity**, and HSM/PKCS#11 is a **key access model**. In Spring Security SAML2, load the right **SP signing/decryption private keys + certificates** and **IdP verification certificate**, protect keys in deployment environments, and test **keypairs, registration config, SAML trust, and rotation**.