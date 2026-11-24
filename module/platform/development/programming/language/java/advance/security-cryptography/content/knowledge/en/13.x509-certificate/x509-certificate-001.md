# 13.1 Certificates Bind Public Keys to Identities and the Role of CAs

## Learning Objectives and Lesson Placement

After this lesson, you can explain **why a public key needs to be bound to an identity through an X.509 certificate**, **what a CA actually certifies**, and **why a CA's signature is only one step in a trust decision**. You can also read the core structure of a certificate using Java 17 and distinguish a private key, public key, certificate, CSR, and trust anchor without confusing a certificate with an access permission.

Lesson 13.1 is the **conceptual foundation** for Chapter 13. Detailed techniques are covered in dedicated lessons: root/intermediate/leaf hierarchy (13.2), DER/PEM and `CertificateFactory` (13.3), subject/issuer/serial/validity fields (13.4), DNS/IP SANs (13.5), KU/EKU/BC (13.6), `checkValidity`/`verify`/PKIX (13.7), the keytool CSR/reply workflow (13.8), and isolating a test CA (13.9). Conditions mentioned briefly here are sufficient to understand the big picture, but do not replace the in-depth procedures in each lesson.

## 1. The Problem: A Public Key Does Not Self-Declare a Trusted Origin

Alice wants to connect securely to the service `api.example.test`. She receives a public key used in a cryptographic protocol. An adversary Mallory can also generate a key pair and claim to be `api.example.test`. **Receiving only the public key bytes is not enough to distinguish the two cases.**

```text
Alice needs to talk to api.example.test
                 |
                 +--> Public key K1 controlled by the service owner?
                 |
                 +--> Public key K2 presented by an impersonator?
                 |
                 v
Missing piece: trustworthy evidence of the
relationship between the expected identity and the public key.
```

An **X.509 certificate** solves a key part of this: an issuer signs **a data package describing the subject, public key, and usage conditions**. A verifier can check that this information was genuinely signed by the corresponding issuer key and has not been modified since signing. However, who is authorized to issue a certificate for that name and whether the issuer is trusted remain questions of **PKI policy**.

A self-generated public key can be used to verify a mathematical signature, but that does not prove who the key owner is. A self-signed certificate can also have a cryptographically valid signature while still lacking a trusted source to confirm the claimed identity.

## 2. Structure of the Attestation: A CA Signs `TBSCertificate`, Not Just “the Public Key”

High-level X.509 v3 structure:

```text
Certificate
  |
  +-- tbsCertificate  (to-be-signed certificate)
  |     +-- version, serialNumber
  |     +-- issuer, validity
  |     +-- subject
  |     +-- subjectPublicKeyInfo
  |     |     +-- algorithm + PUBLIC KEY
  |     +-- extensions (SAN, KU, EKU, BC, ...)
  |
  +-- signatureAlgorithm
  +-- signatureValue   <-- signs the DER encoding of tbsCertificate
```

Fields included together in the signed portion:

| Component | Role in the key–identity binding | What cannot be inferred by itself |
| --- | --- | --- |
| `subjectPublicKeyInfo` | Contains the **subject**'s public key and associated algorithm | Who the key owner is without a verification process |
| `subject` | Distinguished Name of the subject; may be empty depending on profile | That Subject CN is a verified TLS hostname |
| `subjectAltName` (SAN) | Carries typed identifiers such as DNS/IP/URI, depending on profile | That the SAN value itself proves the CA is trusted |
| `issuer` | States the identity of the certificate-issuing entity | That matching a trusted CA's DN is enough to verify the signature |
| `serialNumber` | Identifies the certificate within the **issuer**'s scope | That the serial is unique across all CAs |
| `notBefore`/`notAfter` | Validity interval declared by the CA | That an unexpired certificate has definitely not been revoked |
| `BasicConstraints`, `KeyUsage`, `ExtendedKeyUsage` | Restricts CA role and key usage purposes | That the certificate can be used for any purpose or grants business permissions |
| `signatureValue` | The issuer's signature over the protected data | That the issuer is necessarily in the recipient's truststore |

Saying “the CA signs the public key” is only shorthand. More precisely, **the CA signs the `TBSCertificate` portion**, in which the public key is bound to the subject, issuer, serial, validity period, and extensions. Changing any signed field causes signature verification to fail without a new signature from the issuer's private key.

**A certificate does not encrypt data**: typically, certificates and public keys are distributed publicly. The private key corresponding to the subject must be protected in a keystore, HSM, or appropriate key management system; it is not inside a standard PEM/DER certificate. The **CA**'s private key is a different key: it signs certificates, not a key copied onto every server.

## 3. What Does a CA Do, and Where Does a CA's Authority Come From?

A **Certification Authority (CA)** is an entity/organization operating a certificate issuance process according to policies for identity verification and signing key protection. A CA can verify control over a DNS name, organization, user, or device depending on the certificate type, and then issue an X.509 certificate with the approved contents.

Separate roles:

| Role | Responsibility |
| --- | --- |
| **Subject / applicant** | Generates and protects the private key; submits the public key and issuance request details to the CA via a CSR or other workflow |
| **Registration Authority (RA)**, when present | Assists in vetting the applicant/right to use identifiers and the enrollment process |
| **CA / issuer** | Verifies and approves per policy; assigns serial, validity, extensions; signs `TBSCertificate` with the CA private key |
| **Relying party / verifier** | Decides which trust anchors are accepted; verifies the path, usage conditions, and target identity to connect to |
| **Application owner** | Checks business permissions after identity has been authenticated via the corresponding protocol |

**A CA does not grant login permissions to every system** merely through a certificate signature. For example, an enterprise issuing a client certificate to an employee can prove an mTLS identity; permission to read each order is still decided by the application's IAM/ACL.

In PKI terms, a **root CA** is typically a pre-configured trust anchor, an **intermediate CA** receives issuance authority from an upper CA with specific constraints, and a **leaf/end-entity** certificate is issued to a website/user/application. A self-signed root only has trusted value when the verifier **explicitly places it in the trust anchors set** through a trustworthy channel and policy. Do not infer from `Subject=Issuer` or `CA=true` that a CA is automatically trusted. Roles, pathLen, CA constraints, and the difference between self-issued and self-signed are analyzed in depth in Lesson 13.2.

### 3.1. What Does the Issuer's Signature Prove?

For example, an issuer named `Example Issuing CA` signs a leaf with SAN `DNS:api.example.test`.

- If the `TBSCertificate` bytes are modified after signing, `verify` using the appropriate issuer public key will detect the discrepancy.
- If a **different** public key is used to check the signature, verification typically fails.
- If the issuer key is correct but the issuer is **not on a trust path** accepted by the client, the certificate is **not yet trusted** for the connection.
- If the CA mistakenly issued the wrong SAN, the signature may still be cryptographically valid, yet the certificate can create an impersonation risk. Security therefore also depends on the CA's **vetting and issuance** process.

This explains why a CA needs governance over identity validation, signing key access control, auditing, certificate profiles, revocation/rotation, and handling misissued certificates. The ability to sign does not mean arbitrary issuance authority.

## 4. Flow from Key to Certificate, Then to Acceptance Decision

```text
[1] Subject generates a key pair
    private key is kept secret; public key is shared
               |
               v
[2] Subject sends a CSR (PKCS#10) or corresponding issuance request
    proof of possession + subject/public key + requested extensions
               |
               v
[3] CA/RA checks rights to the identity per policy
    determines the SAN, KU, EKU, BC, validity, and serial to issue
               |
               v
[4] CA signs tbsCertificate -> issues X.509 leaf + issuer chain
               |
               v
[5] Peer receives the certificate and verifies:
    issuer signatures + path to a trusted trust anchor
    + validity period, constraints, purpose, revocation policy
               |
               v
[6] Application checks expected identity and protocol proof that
    the peer actually holds the private key (e.g., TLS handshake)
               |
               v
[7] Application checks its own business permissions before allowing operations
```

This is a **conceptual map**, not an instruction to manually code every TLS check step in order. In a Java HTTPS application, JSSE/trust managers and endpoint identification coordinate multiple steps, applying rules according to the provider and policy. Lesson 13.7 covers `checkValidity`, `verify`, and `CertPathValidator`; Lesson 13.8 goes deep into each `keytool` command for issuing and importing a CSR reply.

### 4.1. A CSR Is a Request, Not a Certificate

A **Certification Signing Request (PKCS#10)** contains the public key, subject/attributes, and a signature created by the applicant using the corresponding private key. The CSR's signature shows that the requester controls the key in a signing context; it does **not** prove they own a domain. A CSR can request a SAN, but the CA must **independently vet** it before issuance; it can reject, modify, or omit those extensions.

A CA-signed **certificate reply** is a different object. When receiving a reply for a CSR, the certificate's public key must match the private key that generated the CSR. A server intending to use a certificate in TLS must store the **leaf certificate chain together with the private key**. Using `keytool` to import a reply into the right alias is covered in full in 13.8.

### 4.2. A Trust Anchor Is the Verifier's Decision, Not “Just Any Root”

A public root CA is usually provided in a truststore by the operating system/JDK or application policy. A private CA can be explicitly added by an organization into a **dedicated purpose-built truststore**. A self-signed certificate may be explicitly pinned/trusted in a narrow design after verifying its origin; self-signing **does not grant trust by itself**.

Do not import a root sent by the unauthenticated server itself just because of `PKIX path building failed`. Doing so allows an attacker to generate both a valid self-signed root and leaf for arbitrary names. Use verified trust anchors and always keep endpoint hostname verification enabled.

## 5. An Intuitive Example: Valid Certificate, Yet Unverified or Wrong Identity

Suppose Alice wants to communicate with `payments.example.test`:

| Case | Leaf signature | Trust/identity per client | Conclusion |
| --- | --- | --- | --- |
| Leaf issued by a client-trusted CA for `payments.example.test`, DNS SAN matches, other conditions pass | Valid | Path and target name match | Can be accepted in TLS per policy |
| Leaf issued by a trusted CA for `files.example.test`, client calls `payments.example.test` | Valid | Path may be valid, **SAN targets wrong endpoint** | Reject connection due to endpoint mismatch |
| Self-signed leaf with `CN=payments.example.test` created by Mallory | Self-signed validly with Mallory's key | No matching trust anchor | Reject; self-declared name does not create trust |
| Leaf issued by a trusted CA but expired or revoked | Signature may be valid | Violates validity/status policy | Reject per policy |
| mTLS client has a certificate issued by a trusted internal CA but calls an API beyond its role | Signature/path may be valid | Fails resource authorization | Deny operation |

Three misconceptions to eliminate immediately:

1. **“I parsed the certificate.”** Parsing only reads the structure; `CertificateFactory` does not automatically trust the CA.
2. **“I verified the signature.”** `X509Certificate.verify(publicKey)` only checks the certificate's signature with the provided key; it does not choose a trust anchor, check the hostname, or perform comprehensive revocation checking.
3. **“I found a root.”** If the root comes from the untrusted input itself, setting it as a `TrustAnchor` breaks the PKI model.

In HTTPS, clients must typically match DNS/IP **against the appropriately typed SAN** for the hostname/IP the client intends to access; Subject CN does not replace modern name identification. Lesson 13.5 is dedicated to DNS/IP/wildcard/IDNA and endpoint identification mechanisms.

## 6. Java 17+ Hands-On Foundation: Inspecting a CA Certificate Without Self-Granting Trust

This is a small experiment to **see the binding and signer firsthand**. The code creates a self-signed demo CA, exports **only the public certificate** to PEM, and uses Java to read the fields. It **does not** issue a leaf, does not import the root into any truststore, and does not open TLS. A cryptographically successful self-signed lab root still **has no default trusted authority**.

In a fresh directory used only for this lesson, run JDK 17+ `keytool`. The commands prompt for passwords interactively; do not pass real passwords on the command line:

```bash
keytool -genkeypair -alias lab-ca -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=Learning CA,O=Training,C=VN" -validity 30 -ext BC:critical=ca:true,pathlen:0 -ext KU:critical=keyCertSign,cRLSign -keystore ca-demo.p12 -storetype PKCS12
keytool -exportcert -alias lab-ca -rfc -file ca-demo.pem -keystore ca-demo.p12 -storetype PKCS12
```

- `ca-demo.p12` contains the **CA's private signing key**, which must be kept secret and used only in the lab.
- `ca-demo.pem` contains only the certificate/public key and is readable; **having the file does not mean the client trusts the CA**.
- `BasicConstraints CA=true` and `KeyUsage keyCertSign` express the role granted in the certificate. Using it as a trusted root is a separate decision by the verifier.
- `-validity 30` creates a validity interval from the time the lab is created; after 30 days, generate a new fixture to test unexpired conditions.

Create the file **`CaBindingInspect.java`**:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

public final class CaBindingInspect {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java CaBindingInspect <certificate.pem>");
        }

        X509Certificate cert;
        try (InputStream in = Files.newInputStream(Path.of(args[0]))) {
            cert = (X509Certificate) CertificateFactory
                    .getInstance("X.509").generateCertificate(in);
        }

        System.out.println("X.509 parsed: " + "X.509".equals(cert.getType()));
        System.out.println("Self-issued DN: " +
                cert.getSubjectX500Principal()
                    .equals(cert.getIssuerX500Principal()));
        System.out.println("Certificate is CA: " +
                (cert.getBasicConstraints() >= 0));

        cert.checkValidity();
        System.out.println("Within current validity interval: true");
        cert.verify(cert.getPublicKey());
        System.out.println("Self-signature verifies: true");

        // Do not treat the lines above as trust or hostname verification.
        System.out.println("Issuer trusted by this program: not evaluated");
        System.out.println("Endpoint hostname verified: not evaluated");
    }
}
```

Compile and run after generating `ca-demo.pem` (the Java command below is a standalone program):

```bash
javac --release 17 CaBindingInspect.java
java CaBindingInspect ca-demo.pem
```

With the **newly created fixture** on a JDK with `keytool` and the necessary providers, expected output:

```text
X.509 parsed: true
Self-issued DN: true
Certificate is CA: true
Within current validity interval: true
Self-signature verifies: true
Issuer trusted by this program: not evaluated
Endpoint hostname verified: not evaluated
```

What has been demonstrated?

- `CertificateFactory("X.509")` reads the certificate structure; it does **not** determine whether the CA is trusted by the application.
- `Subject=Issuer` reflects **self-issued**; `verify(cert.getPublicKey())` checks only the fixture's self-signature. These are two distinct properties and will be analyzed further in 13.2.
- `checkValidity()` only indicates that the current date is within the validity interval; it does **not** check identity or revocation status.
- The program intentionally prints **not evaluated** for trust and hostname because it has not used trust anchors/PKIX or made an HTTPS connection.
- A public root PEM can be distributed over an appropriate channel, but do not automatically install it as a system or browser trusted root. From this experiment, learners should distinguish **a valid signature** from **a valid trust decision**.

**Do not import a demo CA into production truststores/`cacerts`, and do not use lab private keys outside the practice environment.** Lesson 13.9 details how to isolate a lab CA, manage passwords and truststores, and write negative tests.

## 7. Diagnostic Checklist When Receiving a Certificate

When handed a new certificate file, answer these in order:

1. **What is the file really?** Is it a public X.509 certificate, a CSR, a raw public key, or a keystore containing a private key? Do not rely on the file extension. Lesson 13.3 guides how to read DER/PEM.
2. **Who are the subject, issuer, and granted identities?** Read the signed fields; the issuer name does not guarantee signature validity or trust. Lesson 13.4 explains DN, serial, and validity.
3. **What usage scope did the CA declare?** Are SAN, KeyUsage, ExtendedKeyUsage, BasicConstraints, and any critical extensions appropriate? Lessons 13.5–13.6 examine each group.
4. **Whom does the verifier explicitly trust?** Which root/intermediate forms a valid PKIX path to a trust anchor, and is the certificate revoked under policy? Lessons 13.2 and 13.7 go deeper.
5. **Is this the exact service/role to authenticate?** Check expected identity, TLS proof-of-possession, and protocol-level authorization; do not take the expected identity from the unverified certificate itself.
6. **Was the certificate issued through the proper process?** Check CSR, CA reply, private-key alias, chain, validity period, review/audit, and lab/prod separation. Lessons 13.8–13.9 clarify this.

This is an **evaluation checklist**, not code to replace the TLS/PKIX verifier. When programming real HTTPS connections, prefer properly configured JSSE/`HttpClient`/`HttpsURLConnection`; never create an `X509TrustManager` that accepts all certificates or a `HostnameVerifier` that always returns true.

## 8. Scenarios to Explain Instead of Memorizing Definitions

**Scenario A.** A CA issues a certificate with `SAN=DNS:api.example.test` for a service's public key. An attacker changes the SAN to `admin.example.test` in the issued DER without knowing the issuer's private key. What must happen?

> The SAN is part of the signed `TBSCertificate`, so the signature no longer matches. A proper verifier will reject the tampered certificate.

**Scenario B.** Mallory creates a valid self-signed root CA and sets `CN=Example Trusted CA`. Should Alice trust a server certificate signed by that root?

> No. The name and self-signature are both controlled by Mallory. Alice only accepts a root if it has been established as a trust anchor through an independent, trustworthy channel and policy.

**Scenario C.** A certificate issued by a trusted CA is for `files.example.test`, while the client needs to call `payments.example.test`. Should it connect?

> Not if the SAN does not cover the right target. The trust chain may be valid, but the endpoint identity is wrong.

**Scenario D.** An mTLS client certificate is issued by a trusted CA and has a valid path. Does it automatically have permission to modify all invoices?

> No. Identity authentication does not grant business permissions; the service must check principal/tenant/role for each operation.

**Scenario E.** A CSR requests `CA:true` and `DNS:service.prod.example`. Should the CA copy the request verbatim because the CSR signature is valid?

> No. A CSR signature only proves the requester controls the private key; the CA must vet the request, identity, and certificate profile constraints before signing.

## 9. Core Misconceptions to Avoid

| Misconception | Why it is wrong | Accurate statement |
| --- | --- | --- |
| “The CA only signs the public key.” | The signature covers `TBSCertificate`, which contains many fields | The CA signs the issued certificate data structure, including the public key, identity, and constraints |
| “A certificate contains the private key.” | `subjectPublicKeyInfo` is the public key | The private key is kept separate in a keystore/HSM |
| “If a certificate parses, it is safe.” | A parser only reads the X.509 format | Trust, path, purpose, and identity must be verified for the scenario |
| “The Issuer DN matches a trusted CA, so the signature is valid.” | Anyone can set an identical DN | The signature must be verified with the matching CA public key and path policy |
| “A self-signed root is automatically a trust anchor.” | A self-signature is only a cryptographic fact | A trust anchor is configured by the relying party from a trusted source |
| “Having a CA signature means the hostname is right.” | A CA can issue a certificate for a different name | Verify the expected DNS/IP via SAN and a standard verifier |
| “A client certificate issued by the CA grants admin privileges.” | CA binding relates to identity, not ACLs | After authentication, authorization must be checked in the application |
| “A certificate itself encrypts HTTP.” | X.509 only carries a public key and attributes | TLS establishes a secure channel per protocol, with endpoint authentication |

## 10. Summary and Boundaries with Subsequent Lessons

An X.509 certificate is **a signed attestation by an issuer that a public key is bound to a subject/identifier within a defined usage scope**. The CA must enforce issuance policy; the verifier must choose trust anchors, check the path, purpose, and exact endpoint; and the application must still enforce permissions after authentication.

Lesson 13.1 helps learners ask the right questions about public key provenance and CA roles. Subsequent lessons provide specialized verification: **13.2** root/intermediate/leaf roles, **13.3–13.6** reading and understanding X.509 fields, **13.7** separating validity/signature/trust, **13.8** CSR/chain workflow in keytool, and **13.9** isolated test CA models.

**Standards and Documentation:**

- [RFC 5280 — Internet X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280) — `TBSCertificate` structure, issuer/subject, extensions, path validation.
- [Java SE 17 — X509Certificate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html) — API for inspecting fields, signatures, and validity.
- [Java SE 17 — CertificateFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertificateFactory.html) — reading DER/PEM into certificates.
- [Java SE 17 — keytool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html) — creating, exporting, and viewing certificates.