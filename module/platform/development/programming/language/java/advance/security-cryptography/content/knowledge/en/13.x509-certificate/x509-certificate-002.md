# 13.2 Distinguishing Root, Intermediate, Leaf, and Self-Signed Certificates

## Objectives

This lesson belongs to **13. X.509 Certificates** in Java Advance – security-cryptography. You will:

1. Accurately distinguish **root CA certificates**, **intermediate CA certificates**, **leaf/end-entity certificates**, and **self-signed certificates** by their roles in a trust chain.
2. Understand the difference between **“a certificate with a valid signature”**, **“a chain verified to a trust anchor”**, and **“a certificate belonging to the exact server/user/service the application expects”**.
3. Read important X.509 fields: `Subject`, `Issuer`, `BasicConstraints`, `KeyUsage`, `ExtendedKeyUsage` (EKU), `SubjectAlternativeName` (SAN), `NotBefore/NotAfter`, `SubjectKeyIdentifier` (SKI), and `AuthorityKeyIdentifier` (AKI).
4. Use **`keytool` and Java 17+** to build a simulated root → intermediate → leaf chain, verify signatures, and run `CertPathValidator("PKIX")` with a valid/invalid trust anchor.
5. Identify common bugs in Java TLS, mTLS, PKIX, and trusting self-signed certificates without verifying their origin.

> **Key takeaway:** `self-signed` describes **how a certificate is signed**; `root`, `intermediate`, and `leaf` describe **roles in a certification path**; `trusted` describes **the application's trust policy**. These are related concepts, not synonyms.

## 1. What Information Does an X.509 Certificate Contain?

An **X.509 digital certificate** is a signed data structure that typically contains:

- **Subject:** identifier of the entity the certificate describes; in modern TLS use cases, DNS/IP identity is checked primarily by **SAN**, not just by looking at `CN`.
- **Subject public key information (SPKI):** the subject's public key and associated algorithm; **does not contain the private key**.
- **Issuer:** the entity name stated as the issuer (signer) of the certificate.
- **Serial number:** serial number assigned by the issuer within the issuer's scope.
- **Validity:** `NotBefore` and `NotAfter`, the time interval during which the certificate is intended to be valid.
- **Signature algorithm and signature value:** the issuer's algorithm/signature over the **tbsCertificate** (*to-be-signed certificate*) portion.
- **Extensions:** for example `BasicConstraints`, `KeyUsage`, `ExtendedKeyUsage`, `SubjectAlternativeName`, `NameConstraints`, SKI/AKI, and Certificate Policies.

Every certificate holds the **subject's public key**, but the certificate's signature is verified using the **issuer's public key**, except in the self-signed case where the two keys may be the same.

When a browser sees a certificate with subject `service.example.test`, it does not merely check “there is a signature”; it must build a trust path and check **the exact hostname**, validity period, usage purpose, policy, algorithms, and revocation status per policy.

A certificate is not a secret key. You can send a certificate to other parties; **the corresponding private key must be kept secret** and is not inside a PEM certificate. Do not confuse a `.crt/.cer/.pem` certificate file with a keystore containing a private key or a PKCS#8 private-key file.

## 2. Diagram of a Root → Intermediate → Leaf Chain

A common PKI configuration:

```text
                     APPLICATION TRUST STORE
                     +-----------------------+
                     | Root CA / Trust Anchor|
                     | ALREADY pre-trusted   |
                     +-----------+-----------+
                                 |
           Root private key signs the Intermediate certificate
                                 |
                                 v
                     +-----------------------+
                     | Intermediate CA       |
                     | BasicConstraints CA=1 |
                     | attested by Root      |
                     +-----------+-----------+
                                 |
             Intermediate private key signs the Leaf certificate
                                 |
                                 v
                     +-----------------------+
                     | Leaf / End Entity     |
                     | service.example.test  |
                     | CA=0, SAN and EKU     |
                     +-----------------------+
                                 |
                      Leaf private key used
                     for TLS or app signing
```

In typical TLS networking, the server sends **the leaf and necessary intermediates**; the trusted root is usually already present in the client's trust store and **does not need to be sent by the server**. The chain sent by the server is not necessarily the final path chosen by the validator (for example, when cross-signing exists); the verifier may have to build or select a path matching the client's trust anchors.

### Distinct Roles

| Type | Role in the chain | Typically signs for whom? | Typical extensions needed | Must it be self-signed? |
| --- | --- | --- | --- | --- |
| **Root CA** | Starting point of trust (*trust anchor*) of a PKI system | Intermediates or other CAs | `BasicConstraints: CA=true`, `KeyUsage: keyCertSign` | **Not required by the trust anchor concept**; root CA certificates are usually self-signed |
| **Intermediate CA** | Issues/certifies lower-tier certificates; delegated from root | Other intermediates or leaves | `CA=true`, `keyCertSign`, `pathLenConstraint` if any | **Usually not**; it is signed by an upper issuer |
| **Leaf / End-Entity** | Binds a public key to a host, user, service, or end application | Does not act as a CA in that path | `CA=false`, SAN, EKU, KeyUsage suited to purpose | **Usually not**; however, can be self-signed in some environments |
| **Self-signed certificate** | Describes a **signature property**, not a specific tier | Subject signs its own certificate | May have `CA=true` or `CA=false` depending on purpose | **By definition, self-signed** |

A **root CA** is a role defined by *the chosen trust anchor*, not “any certificate with `Subject=Issuer`”. A self-signed certificate with `CA=true` still **does not become a trust anchor merely by being self-signed**. Conversely, an organization can explicitly trust a non-self-signed certificate/key as an internal trust anchor or trust an intermediate as an anchor by policy; `TrustAnchor` in Java supports either a certificate or a CA name/public key.

### How Does a CA Differ from an End Entity?

A certificate with `BasicConstraints` **CA=true** can act as a CA if path/KeyUsage/policy conditions match. A typical **leaf** has `BasicConstraints CA=false` or no CA authority. With Java `X509Certificate.getBasicConstraints()`:

- Returns **`-1`** if the certificate is not a CA.
- Returns a number **`>=0`** if the certificate is a CA; this number reflects the declared `pathLenConstraint` or a representative value when unconstrained.
- `pathLenConstraint=0` on an intermediate means no **additional non-self-issued intermediate CAs** are allowed below that intermediate in the path, though it can still issue certificates for **leaves**.
- In path validation, path length semantics must follow RFC 5280, including rules for self-issued CAs. Do not implement path length checks manually by counting all certificates in an array.

A CA certificate also commonly has the **`KeyUsage.keyCertSign`** bit, and the validator must enforce the appropriate constraints. **`CA=true` alone does not mean the application should trust it or that the certificate is necessarily authorized to issue every type of certificate.**

## 3. Self-Issued and Self-Signed Are Not Exactly the Same

This is a distinction easily overlooked:

- **Self-issued:** `Subject` and `Issuer` have the same Distinguished Name (DN). That is a **name** comparison, not signature proof.
- **Self-signed:** the signature on the certificate was created with the private key corresponding to the **public key contained in the certificate itself**, and the signature can be verified with that public key. Usually the subject and issuer also share the same name.

A **self-issued but non-self-signed** certificate can appear during key transition (*CA key rollover*): the CA name does not change, but the certificate is signed by another key of the same CA. Therefore, `subject.equals(issuer)` must not be treated as a complete self-signed check.

**Self-signed does not mean self-trusted.** For example:

```text
Root-A is validly self-signed. Client has installed Root-A as a trust anchor.
=> A path terminating at Root-A CAN be trusted if other policies pass.

Root-B is validly self-signed. Client has never approved/installed Root-B.
=> Root-B is NOT trusted merely because its self-signature is valid.
```

An adversary can generate countless key pairs and self-signed certificates with valid signatures. No mathematical problem stops them from doing so. Only **distributing trust anchors from a controlled source** determines which roots are trusted by the application.

### Why Are Root CAs Usually Self-Signed?

A certificate path must have a stopping point. A self-signed root certificate provides a convenient packaging format for **the public key and metadata of the trust point**; however, **trust does not come from the root's signature on itself**. It comes from the application/OS/organization **having selected that key/certificate as a trust anchor** via an out-of-band trust mechanism.

In many PKIs, the root private key is kept offline or in an HSM, while intermediates handle day-to-day certificate signing. If an intermediate is compromised, administrators can revoke/replace the intermediate without necessarily replacing the entire root; yet it remains a serious incident affecting issued leaves and requiring revocation/rotation procedures.

## 4. A Signature Link Differs from a Trusted Path

Consider three certificates:

```text
Root:         Subject = CN=Training Root CA
              Issuer  = CN=Training Root CA
Intermediate: Subject = CN=Training Intermediate CA
              Issuer  = CN=Training Root CA
Leaf:         Subject = CN=service.example.test
              Issuer  = CN=Training Intermediate CA
```

The cryptographic links that can be checked:

- `intermediate.verify(root.getPublicKey())`: intermediate's signature matches root's public key.
- `leaf.verify(intermediate.getPublicKey())`: leaf's signature matches intermediate's public key.
- `root.verify(root.getPublicKey())`: root's signature self-verifies if root is self-signed.

**However, those three `verify` calls alone do not establish trust**:

- You may have obtained `root.pem` from the attacker. All three signatures may be valid, yet the root is not **trusted**.
- An intermediate might have `CA=false` or `keyCertSign` disallowed. Individual signatures can still match while **the path fails constraints**.
- A certificate may be expired, not yet valid, revoked, or use an algorithm disallowed by policy.
- The leaf may be valid for hostname `service-b.example.test`, while the client needs to connect to `service-a.example.test`.
- A root trusted in one **purpose/namespace** does not imply authority to issue certificates for all purposes or tenants.

**Verifying a certificate signature** is a local operation. **PKIX path validation** evaluates a certificate path in the context of trust anchors and constraints. **Verifying service/user identity** is the subsequent application/TLS constraint.

## 5. X.509 Fields to Read to Determine Roles

| Field / extension | Role | What must not be inferred |
| --- | --- | --- |
| `Subject` | Subject name | The name can be self-asserted; does not prove identity by itself |
| `Issuer` | Declared issuer name | Matching a root's name does not prove the certificate was signed by that root |
| `AuthorityKeyIdentifier` (AKI) | Helps locate the appropriate issuer public key/certificate | AKI is not itself a trust anchor or proof of a valid path |
| `SubjectKeyIdentifier` (SKI) | Identifies the subject key, assists path building | Having the same SKI does not prove trust |
| `BasicConstraints` | Distinguishes CA, constrains number of CAs below | `CA=true` does not automatically grant trust |
| `KeyUsage` | Key purposes such as `digitalSignature`, `keyCertSign`, `keyEncipherment` | A certificate simply holding an RSA public key does not automatically allow every usage |
| `ExtendedKeyUsage` (EKU) | Purposes such as `serverAuth`, `clientAuth`, `codeSigning` | `serverAuth` does not grant permission to sign application updates |
| `SubjectAlternativeName` (SAN) | DNS/IP/email/URI identity per profile | Looking only at CN or an arbitrary SAN is insufficient to match a hostname |
| `NotBefore` / `NotAfter` | Validity interval | Being within the interval does not mean it has not been revoked |
| `CRLDistributionPoints` / `AuthorityInfoAccess` | Hints where to fetch CRL/OCSP/issuer certificate | Having a URL in an extension does not guarantee the client performed revocation checks |
| `CertificatePolicies` / `NameConstraints` | Policy and namespace constraints | Cannot ignore an unrecognized critical extension and still treat the path as valid |

A proper chain must also have **valid signatures between every tier**, **issuer/subject linkage**, supported algorithms, properly processed critical extensions, BasicConstraints/KeyUsage/policy compliance, and a **selected trust anchor**.

### Root / Intermediate Is Not Determined by Name Alone

Seeing the word `Root` in a subject does not mean that certificate is a root. Seeing `Issuer=Subject` does not guarantee it is self-signed. Seeing a certificate with `CA=true` does not guarantee it sits at the intermediate tier; **the same CA certificate can be an intermediate in one path, yet actively used as a trust anchor by another organization in a different path**. Role depends on **path/policy**, not labels in the DN.

### A Leaf Is Not Necessarily a TLS Server Certificate

A leaf can be a certificate for an **mTLS client**, code signing, document signing, user authentication, or device authentication. EKU/KeyUsage and identification rules must match the specific use case. For example, `serverAuth` has OID **`1.3.6.1.5.5.7.3.1`**, while `clientAuth` is **`1.3.6.1.5.5.7.3.2`**. A leaf may or may not have a specific EKU depending on profile; do not automatically assume “leaf” means “web server”.

## 6. PKIX Path Validation in Java

Java provides standard APIs to parse certificates and validate paths:

- `CertificateFactory.getInstance("X.509")`: parses PEM/DER certificates, or creates a `CertPath` from a list of certificates.
- `X509Certificate`: reads `getSubjectX500Principal()`, `getIssuerX500Principal()`, `getBasicConstraints()`, `getKeyUsage()`, `getExtendedKeyUsage()`, `getSubjectAlternativeNames()`, `getNotBefore()/getNotAfter()`.
- `X509Certificate.verify(issuerPublicKey)`: checks the signature **of the certificate** with the issuer public key; does **not** check path, trust, hostname, or full revocation.
- `CertPathValidator.getInstance("PKIX")`: validates an **existing certificate path** with `PKIXParameters`.
- `CertPathBuilder.getInstance("PKIX")`: attempts to **build a path** from certificates/CertStores and configured trust anchors; does not mean “always fetches intermediates automatically from the Internet”.
- `TrustAnchor`: a certificate/CA key that the application **has decided to trust**, not a certificate merely because it is self-signed.
- `KeyStore` and `TrustManagerFactory`: stores/provisions trust anchors and integrates with JSSE/TLS; do not confuse a **truststore** with a **private-key keystore**.

**Typical `CertPath` order for PKIX:** leaf first, followed by intermediates, and **the trust anchor is usually omitted from the path's certificate list** because it is supplied separately in `PKIXParameters`. Some servers send an extra root certificate; the root's presence in the handshake does not mean the client considers it trusted.

### Three Independent Checks

```text
X509Certificate.verify(issuerKey)
         |
         v
[Certificate signature valid?]
         |
         v
PKIX path validation with client's trust anchors
         |
         v
[Trusted root? CA constraints? time/policy? revocation policy?]
         |
         v
Endpoint / identity verification
         |
         v
[DNS SAN/IP/issuer identity/role matches expected target?]
         |
         v
Authorization / application policy
         |
         v
[Allowed to access this resource/action?]
```

If the **endpoint identity** step is missing, a valid certificate in the CA chain may be accepted for the **wrong server**. If the **trust anchor** step is missing, an attacker can issue a chain to themselves. If the **authorization** step is missing, a valid certificate can still perform unauthorized actions.

## 7. Java 17 Hands-On: Building Root → Intermediate → Leaf and an Untrusted Root

This lab uses **`keytool` bundled with the JDK** and **Java 17**. You create four key pairs **strictly for testing**:

1. `root`: self-signed CA with `BasicConstraints CA=true` and `pathLen=1`.
2. `intermediate`: initially has a temporary self-signed certificate upon keypair generation; then you create a CSR, **root signs the new certificate**, and you import the certificate reply into the same alias. The result is **no longer self-signed**.
3. `leaf`: similarly, the end certificate is signed by **intermediate**, with `SAN=dns:service.example.test` and `EKU=serverAuth`. The leaf is **not a CA**.
4. `rogue`: an independent self-signed CA with a completely valid signature, but **not a selected trust anchor** when verifying the root → intermediate → leaf chain.

**Do not use test keystores, the password `changeit`, mock roots, or lab private keys in production.** Work only in a dedicated directory that can be deleted after testing.

### 7.1 Creating Certificates with PowerShell on Windows

Open PowerShell in a terminal that has `keytool.exe` from the JDK and run the **entire snippet** below. The script creates a dedicated directory in `%TEMP%`, a PKCS#12 keystore `chain.p12`, and four PEM files. It does not access the internet. If re-run, the **lab** keystore in the temp directory is recreated; avoid placing personal documents in the same directory.

```powershell
$ErrorActionPreference = "Continue"
$qaPath = Join-Path $env:TEMP 'x509-roles-training'
New-Item -ItemType Directory -Force -Path $qaPath | Out-Null
Set-Location $qaPath
$p = "changeit"

function Invoke-Keytool([string[]]$params) {
    $result = & keytool.exe @params 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ("keytool failed: " + ($params -join " ")
               + " :: " + ($result -join " "))
    }
}

if (Test-Path -LiteralPath 'chain.p12') {
    Remove-Item -LiteralPath 'chain.p12' -Force
}

Invoke-Keytool @("-genkeypair","-alias","root","-keyalg","RSA",
    "-keysize","2048","-validity","3650",
    "-dname","CN=Training Root CA,O=Training",
    "-ext","BC=ca:true,pathlen:1",
    "-ext","KU=keyCertSign,cRLSign",
    "-storetype","PKCS12","-keystore","chain.p12",
    "-storepass",$p,"-keypass",$p,"-noprompt")

Invoke-Keytool @("-genkeypair","-alias","intermediate","-keyalg","RSA",
    "-keysize","2048","-validity","3650",
    "-dname","CN=Training Intermediate CA,O=Training",
    "-ext","BC=ca:true,pathlen:0",
    "-ext","KU=keyCertSign,cRLSign",
    "-storetype","PKCS12","-keystore","chain.p12",
    "-storepass",$p,"-keypass",$p,"-noprompt")

Invoke-Keytool @("-certreq","-alias","intermediate",
    "-file","intermediate.csr","-keystore","chain.p12","-storepass",$p)

Invoke-Keytool @("-gencert","-alias","root",
    "-infile","intermediate.csr","-outfile","intermediate-signed.pem",
    "-rfc","-validity","600",
    "-ext","BC=ca:true,pathlen:0",
    "-ext","KU=keyCertSign,cRLSign",
    "-keystore","chain.p12","-storepass",$p)

Invoke-Keytool @("-importcert","-alias","intermediate",
    "-file","intermediate-signed.pem",
    "-keystore","chain.p12","-storepass",$p,"-noprompt")

Invoke-Keytool @("-genkeypair","-alias","leaf","-keyalg","RSA",
    "-keysize","2048","-validity","3650",
    "-dname","CN=service.example.test,O=Training",
    "-ext","SAN=dns:service.example.test",
    "-ext","EKU=serverAuth",
    "-ext","KU=digitalSignature,keyEncipherment",
    "-storetype","PKCS12","-keystore","chain.p12",
    "-storepass",$p,"-keypass",$p,"-noprompt")

Invoke-Keytool @("-certreq","-alias","leaf","-file","leaf.csr",
    "-keystore","chain.p12","-storepass",$p)

Invoke-Keytool @("-gencert","-alias","intermediate",
    "-infile","leaf.csr","-outfile","leaf-signed.pem",
    "-rfc","-validity","90",
    "-ext","SAN=dns:service.example.test",
    "-ext","EKU=serverAuth",
    "-ext","KU=digitalSignature,keyEncipherment",
    "-keystore","chain.p12","-storepass",$p)

Invoke-Keytool @("-importcert","-alias","leaf",
    "-file","leaf-signed.pem",
    "-keystore","chain.p12","-storepass",$p,"-noprompt")

Invoke-Keytool @("-genkeypair","-alias","rogue","-keyalg","RSA",
    "-keysize","2048","-validity","3650",
    "-dname","CN=Untrusted Root CA,O=Training",
    "-ext","BC=ca:true,pathlen:1",
    "-ext","KU=keyCertSign,cRLSign",
    "-storetype","PKCS12","-keystore","chain.p12",
    "-storepass",$p,"-keypass",$p,"-noprompt")

foreach ($alias in @("root","intermediate","leaf","rogue")) {
    Invoke-Keytool @("-exportcert","-alias",$alias,"-rfc",
        "-file",("$alias.pem"),"-keystore","chain.p12","-storepass",$p)
}
Get-ChildItem -Name '*.pem'
```

The output should list the files:

```text
intermediate-signed.pem
leaf-signed.pem
root.pem
intermediate.pem
leaf.pem
rogue.pem
```

Filenames are listed according to filesystem sorting; do **not** rely on the display order. `intermediate-signed.pem` and `leaf-signed.pem` are intermediate certificate replies; the four files `root.pem`, `intermediate.pem`, `leaf.pem`, and `rogue.pem` are read by the Java class below. Output such as “Generating...” or “Certificate reply was installed...” from `keytool` depends on the JDK/OS and is not fixed stdout for this lesson.

**Note:** In this lab, root/intermediate/leaf are initially created in a keystore containing **private keys** so they can sign CSRs. After replacing the certificate reply, each alias's private key remains stored in the keystore. **PEM certificates exported with `-exportcert` contain only public certificates**, not private keys. A real CA must enforce strict controls over root/intermediate keys (HSM, roles, key ceremonies, issuance, and revocation).

On Linux/macOS, the idea is the same using `keytool` and equivalent shell commands; the block above is a **PowerShell script for Windows** and cannot be pasted verbatim into Bash.

### 7.2 Java 17: Reading Certificates, Checking CA Status, and Validating PKIX

In the same directory containing the four PEM files, create **`CertificateRolesDemo.java`** with the following content:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertPathValidatorException;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.List;
import java.util.Set;

public final class CertificateRolesDemo {
    public static void main(String[] args) throws Exception {
        X509Certificate root = load("root.pem");
        X509Certificate intermediate = load("intermediate.pem");
        X509Certificate leaf = load("leaf.pem");
        X509Certificate untrustedRoot = load("rogue.pem");

        root.checkValidity();
        intermediate.checkValidity();
        leaf.checkValidity();

        System.out.println("Root self-signed: " + selfSigned(root));
        System.out.println("Intermediate self-signed: " + selfSigned(intermediate));
        System.out.println("Leaf self-signed: " + selfSigned(leaf));
        System.out.println("Other root self-signed: " + selfSigned(untrustedRoot));
        System.out.println("Root is CA: " + (root.getBasicConstraints() >= 0));
        System.out.println("Intermediate is CA: "
                + (intermediate.getBasicConstraints() >= 0));
        System.out.println("Leaf is CA: " + (leaf.getBasicConstraints() >= 0));

        intermediate.verify(root.getPublicKey());
        leaf.verify(intermediate.getPublicKey());
        System.out.println("Intermediate signature by root: true");
        System.out.println("Leaf signature by intermediate: true");

        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        CertPath path = factory.generateCertPath(List.of(leaf, intermediate));
        System.out.println("PKIX with trusted root: " + validates(path, root));
        System.out.println("PKIX with unrelated root: "
                + validates(path, untrustedRoot));

        boolean dnsMatch = leaf.getSubjectAlternativeNames().stream()
                .anyMatch(entry -> Integer.valueOf(2).equals(entry.get(0))
                        && "service.example.test".equals(entry.get(1)));
        boolean serverAuth = leaf.getExtendedKeyUsage() != null
                && leaf.getExtendedKeyUsage()
                        .contains("1.3.6.1.5.5.7.3.1");
        System.out.println("Leaf SAN contains expected DNS: " + dnsMatch);
        System.out.println("Leaf EKU allows serverAuth: " + serverAuth);
    }

    private static X509Certificate load(String name) throws Exception {
        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        try (InputStream in = Files.newInputStream(Path.of(name))) {
            return (X509Certificate) factory.generateCertificate(in);
        }
    }

    private static boolean selfSigned(X509Certificate certificate) {
        if (!certificate.getSubjectX500Principal()
                .equals(certificate.getIssuerX500Principal())) {
            return false;
        }
        try {
            certificate.verify(certificate.getPublicKey());
            return true;
        } catch (GeneralSecurityException e) {
            return false;
        }
    }

    private static boolean validates(CertPath path, X509Certificate anchor)
            throws GeneralSecurityException {
        PKIXParameters params = new PKIXParameters(
                Set.of(new TrustAnchor(anchor, null)));
        // Only for an offline teaching example without CRL/OCSP.
        params.setRevocationEnabled(false);
        try {
            CertPathValidator.getInstance("PKIX").validate(path, params);
            return true;
        } catch (CertPathValidatorException e) {
            return false;
        }
    }
}
```

Compile and run in PowerShell (still in the `x509-roles-training` directory):

```powershell
javac --release 17 CertificateRolesDemo.java
java -cp . CertificateRolesDemo
```

**Java stdout tested on the `keytool` fixture created above:**

```text
Root self-signed: true
Intermediate self-signed: false
Leaf self-signed: false
Other root self-signed: true
Root is CA: true
Intermediate is CA: true
Leaf is CA: false
Intermediate signature by root: true
Leaf signature by intermediate: true
PKIX with trusted root: true
PKIX with unrelated root: false
Leaf SAN contains expected DNS: true
Leaf EKU allows serverAuth: true
```

Note that results depend on JDK/provider support for RSA, X.509, PKIX, keytool options, and the validity of the certificates in the example; the newly generated certificates have 90/600/3650-day validity periods, so they will normally be valid when run immediately. This lab does **not** connect to the domain `service.example.test` and does **not** register this mock root with the operating system.

### 7.3 Why Does Each Line Matter?

1. **`Root self-signed: true`**: the root has matching subject/issuer names **and** a signature verifiable with the root's own public key. This is a cryptographic fact, **not the reason the root is trusted**.
2. **`Intermediate self-signed: false` and `Leaf self-signed: false`**: after importing certificate replies, they are issued by the upper CA, even though `keytool` initially generated self-signed placeholder certificates during keypair creation.
3. **`Other root self-signed: true`**: the self-signed “rogue” root has a valid signature; self-signature alone cannot distinguish an application-approved CA from a CA generated by someone else.
4. **`Root is CA: true`; `Intermediate is CA: true`; `Leaf is CA: false`**: `getBasicConstraints()` reflects CA authority in the certificate, rather than relying on the words “root/intermediate/leaf” in the subject.
5. **`Intermediate signature by root: true`; `Leaf signature by intermediate: true`**: two individual `verify` calls prove *certificate signature links*, **insufficient to replace PKIX**.
6. **`PKIX with trusted root: true`**: the `leaf → intermediate` path passes PKIX validation when `root` is **explicitly chosen by the application** as the `TrustAnchor`.
7. **`PKIX with unrelated root: false`**: the exact same path fails when the trust anchor is swapped for another self-signed CA; the path does not terminate at the trusted root, so it is rejected. This is the most important proof in the lesson.
8. **`Leaf SAN contains expected DNS: true` and `Leaf EKU allows serverAuth: true`**: reads two extensions relevant to the TLS use case individually. **They are not a complete hostname/endpoint verifier**; the code only checks one literal DNS name in the fixture.

**Important note on `selfSigned`:** the example method requires `Subject DN=Issuer DN` and then calls `certificate.verify(certificate.getPublicKey())`. Verifying cryptographic self-signing does **not** create trust. For certificates/providers with special DN/key representations or unsupported signature algorithms, additional error handling may be needed; this is a standard illustrative method for the created fixture.

### 7.4 Why Does the Lab Disable Revocation?

The call `params.setRevocationEnabled(false)` is only for an **offline** demo because the self-generated certificates here have no real CRL/OCSP infrastructure. It is **not a production recommendation**. In real environments, define an appropriate revocation checking policy, CRL/OCSP sources, timeouts, caching, fail-open/fail-closed modes according to the threat model, as well as incident handling for revoked CAs/keys. Every step—path, identity, role, and freshness—requires explicit decisions; demo code with `PKIX validates==true` **does not automatically satisfy all TLS requirements**.

**Trust anchor validity:** the root certificate in the code has `root.checkValidity()` called explicitly. A trust anchor is a pre-trusted input to `CertPathValidator`; do not assume it is checked for all fields/conditions under the same rules as certificates inside the path. Root/trust store lifecycle is a separate application policy.

## 8. Which Java API Answers Which Question?

| API | What does it check/do? | What does it **not** do? |
| --- | --- | --- |
| `CertificateFactory.generateCertificate` | Parses PEM/DER X.509 into an object | Does not validate issuer or trust |
| `X509Certificate.getSubjectX500Principal` | Returns the subject DN | Does not prove the subject is the true identity |
| `X509Certificate.getIssuerX500Principal` | Returns the issuer DN | Does not prove the issuer actually signed it |
| `X509Certificate.getBasicConstraints` | Returns CA/path length constraint, or `-1` | Does not decide whether the CA is trusted |
| `X509Certificate.getKeyUsage/getExtendedKeyUsage` | Returns purposes declared by the extensions | Does not replace full chain/policy validation |
| `X509Certificate.getSubjectAlternativeNames` | Reads SAN entries by type | Does not match hostnames per TLS rules automatically |
| `X509Certificate.checkValidity` | Checks NotBefore/NotAfter at the time of evaluation | Does not check signature, revocation, trust, or identity |
| `X509Certificate.verify(issuerKey)` | Checks the certificate's signature with the issuer key | Does not build/validate a chain or select a trust anchor |
| `CertPathValidator.validate(path, params)` | Applies the PKIX algorithm to a path with trust anchors/params | Is not a hostname checker, app authorization, or trust generator |
| `CertPathBuilder.build(params)` | Finds a valid path from configured certificates/cert stores/constraints | Does not guarantee fetching every issuer over the network |
| `TrustManagerFactory` / JSSE | Integrates certificate chain trust policy into TLS | Still requires configuring endpoint identification and service policy per use case |

The snippet below **only illustrates initializing a PKIX validator**; it is not standalone and does not execute path validation yet:

```java
CertPathValidator validator = CertPathValidator.getInstance("PKIX");
// Requires a CertPath, PKIXParameters, and reliably prepared trust anchors.
// Also requires identity/hostname, purpose, and revocation policy per use case.
```

Never create `new TrustAnchor(certFromNetwork, null)` and use it to “verify” the certificate sent from the network: doing so turns **untrusted data** into a trust point and defeats the purpose of PKI.

## 9. TLS, mTLS, and Certificate Identity

### 9.1 HTTPS Server: A Valid Chain Is Not Enough

An HTTPS client may encounter two certificates both signed by a trusted root:

```text
CN=service-a.example.test, SAN=DNS:service-a.example.test
CN=service-b.example.test, SAN=DNS:service-b.example.test
```

Both can have valid PKIX paths. Yet when the client connects to **`service-a.example.test`**, **service-b**'s certificate must not be accepted merely because it shares the same CA. **Endpoint identity verification** must match the DNS/IP from the URL/connection against the SAN according to applicable standards; do not simply compare raw `CN`.

In JSSE, how endpoint identification is configured depends on the API/socket/engine and client setup. The snippet below is for an **existing client `SSLSocket` or `SSLEngine`**, not a standalone program:

```java
SSLParameters parameters = sslSocket.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
sslSocket.setSSLParameters(parameters);
// Then perform the TLS handshake with a policy-compliant trust manager.
```

You must import `javax.net.ssl.SSLParameters` and have a valid `sslSocket` and secure truststore. Standard HTTP clients usually have built-in hostname verification behavior; **never disable hostname verification or the trust manager to fix certificate errors**. If a custom hostname verifier is used, it must conform to the protocol instead of `return true`.

### 9.2 mTLS Client: A Valid Cert Chain Does Not Grant Permissions

mTLS authenticates certificates on **both sides** when configured to require a client certificate. Even when a client cert has a valid path, the server must still map the permitted identity from SAN/subject/PKI policy to **an account, service, role, tenant, and resource permissions**. A client with a valid cert from the same CA is not automatically allowed to read another tenant's data.

Similarly, `ExtendedKeyUsage=serverAuth` for a TLS server differs from `clientAuth` for a client. A certificate suited only for one purpose is not automatically accepted for another. Use a trust manager and certificate policy tailored to the role, not just “any cert chaining to a common CA”.

### 9.3 Self-Signed Certs in Dev Environments

A self-signed certificate for localhost/dev can be acceptable within **a narrow trust model** if its fingerprint/public key has been reliably distributed and the application intentionally trusts it. However:

- Do not use an `X509TrustManager` that always accepts every chain.
- Do not disable hostname checking globally.
- Do not blindly import certificates from emails/URLs sent by an unauthenticated party.
- Restrict trust by environment and hostname/purpose; avoid putting test CAs into production trust stores.

## 10. Diagnosing Certificate and Chain Errors

| Symptom | Root cause to inspect | Appropriate action |
| --- | --- | --- |
| `PKIX path building failed` or `unable to find valid certification path` | Client cannot find a path to an installed trust anchor; missing intermediate, wrong issuer, or policy issue | Check truststore/trust anchors, sent intermediates, path constraints, and diagnostic logs; **do not** automatically trust a server-sent root |
| `CertPathValidatorException` on a specific path | Signature, validity, constraints, policies, revocation, or trust mismatch | Inspect the reason/`index` for internal debugging; verify the chain and policy |
| `CertificateExpiredException` / `CertificateNotYetValidException` | `NotAfter/NotBefore` timestamps invalid for the evaluation time | Check system clock; renew/replace the cert through proper procedures |
| Certificate is self-signed and `verify(selfPublicKey)` passes | Self-signed certificate has a valid signature | **Not enough to trust**; must have a properly provisioned pin/trust anchor |
| `CA=false` on an intermediate | BasicConstraints extension does not allow issuing lower-tier certificates | Re-issue a valid intermediate; do not bypass constraints |
| CA has `KeyUsage` but lacks `keyCertSign` when required | Key was not issued with the proper CA role | Fix the CA profile rather than merely adding the CA to the truststore |
| Trusted root but hostname mismatch | Certificate has a SAN different from the target hostname | Fix SAN issuance or the accessed hostname; do not disable endpoint identification |
| Chain OK but leaf lacks `serverAuth` when policy requires it | EKU/usage purpose is inappropriate | Issue the leaf with the proper profile; do not treat the chain alone as sufficient |
| Valid chain but missing CRL/OCSP in a required environment | Revocation data unavailable or misconfigured | Design policy, network/cache/timeouts; do not disable all verification |
| Works on another machine, fails on this one | Different truststore, clock skew, provider, algorithms, intermediates, or policy | Compare JDK, trust anchors, endpoint, versions/chain; never log private keys |
| Self-issued with `Subject=Issuer` but `verify(selfKey)` fails | Not self-signed, or different data/signature | Consider rollover/cross-sign; do not conclude from DN strings alone |

**Never return secret information or enable “trust all” features in real environments.** Logs should include certificate fingerprints (never private keys), appropriate issuer/subject details, key IDs, expected hostnames, failure categories, and correlation IDs. Be careful with logs containing sensitive identities or metadata; sanitize and control access to logs.

## 11. Cross-Signing, Root Rollover, and New Trust Anchors

An organization can issue certificates for **the same intermediate public key** under multiple different issuers (*cross-signing*) or issue self-issued certificates for **CA key rollover**. Consequences:

- **There is not always a single unique path** from leaf to root. Clients with different trust stores may select different valid paths.
- A root can be replaced via OS/JDK truststore updates or an organization's policy distribution process. That distribution **must be trustworthy**, never based on a new self-signed root sent by an arbitrary peer.
- A CA **can act as an intermediate in path A yet be treated as a trust anchor in path B** because organization B directly trusts that CA. A trust anchor is **a policy input to the validator**.
- SKI/AKI help select an issuer but do not guarantee signature or trust; subject/issuer DNs may be identical during key rollover. The exact key and signature must still be verified.
- Changing a root/intermediate's certificate, key, or algorithm can prevent older devices with un-updated truststores from building a path, even while the server still has a valid chain for other clients.
- **Cross-signed certificates do not mean “both CAs are trusted equally”**; only trust anchors actually configured on the client are permitted to terminate a path.

When deploying a CA or intermediate replacement, test across multiple clients/JDKs/truststores, check expirations and weak algorithms in the path, order intermediates properly, and prepare backups and rollbacks; never test by disabling certificate checks and shipping to production.

## 12. Conceptual Errors to Avoid

1. **“Subject=Issuer, so this is a trusted root.”** False: that is only a self-issued indicator. Self-signing must be verified separately; the trust anchor must be chosen by the application.
2. **“Self-signed certificates are always dangerous or always invalid.”** Inaccurate: they can be trusted intentionally after secure provisioning; the danger is *automatically trusting a newly received certificate*.
3. **“The intermediate certifies the leaf, so the intermediate is the root.”** False: an intermediate has authority granted by an upper CA and is subject to path constraints; a root is a trust anchor per policy.
4. **“A leaf cannot issue certs, so it cannot sign anything.”** False: a leaf can use its private key to **sign messages/TLS handshakes** per KeyUsage/EKU, but must not be used as a CA to issue certificates if `CA=false`.
5. **“If `leaf.verify(intermediateKey)` succeeds, HTTPS is safe.”** False: it lacks root trust, path constraints, hostname, EKU, validity, revocation, and proper application policy.
6. **“The root is in the certificate chain sent by the server, so it is a trusted root.”** False: trust does not come from the server. The root must come from a provisioned truststore/policy.
7. **“`CertPathValidator` checks the hostname for me.”** False in general API usage: path validation does not replace JSSE endpoint identification or a proper hostname verifier.
8. **“`getBasicConstraints() >= 0` is enough for a CA to issue any cert.”** False: KeyUsage, pathLen, name constraints, policies, signature, validity, and trust also apply.
9. **“If path validation fails, just import the unfamiliar certificate into `cacerts`.”** False: modifying trust anchors is a high-impact security decision that requires verifying origin and trust scope.
10. **“Revocation causes errors, so disable it permanently.”** False: that is a risky policy choice that must be designed and evaluated, not an automatic fix.
11. **“Having a PEM cert means the application has the private key to sign.”** False: a public certificate does not contain the private key; key material is stored elsewhere.
12. **“An X.509 certificate is the same as an SPKI public key.”** False: a certificate adds issuer, validity, signature/extensions; an SPKI public key carries only the key and algorithm parameters.
13. **“Wildcard SAN/DNS just needs simple string matching.”** False: hostname verification uses specific rules for DNS/IP, wildcards, encoding, and IDNA; never replace it with `String.contains(...)`.
14. **“A self-signed root certificate with a valid signature proves the organization's identity.”** False: any party can generate a self-signed certificate with arbitrary `O`/`CN`; only the trust anchor source establishes trust.

## 13. Checklist for Java Applications

- [ ] Determine the **expected identity** (hostname, service name, client identity) from a trusted context, not from an unverified certificate or claim.
- [ ] Trust anchors come from a reliably distributed and managed truststore/policy, never directly from the peer's chain.
- [ ] Leaves and intermediates are parsed properly and a valid path is built; roots/trust anchors are never assigned solely by subject string.
- [ ] Evaluate link signatures, `BasicConstraints`, `KeyUsage`, `pathLenConstraint`, name/policy constraints, and algorithms.
- [ ] Check `NotBefore/NotAfter` against current time, renewal plans, and revocation policy.
- [ ] TLS server: verify the SAN for the **actual connected hostname**; do not disable JSSE endpoint identification.
- [ ] mTLS: distinguish `serverAuth`/`clientAuth` and map the authenticated identity to tenant/role/authorization.
- [ ] Test root/intermediate rotation, cross-signing, and truststore updates across clients/JDKs.
- [ ] Never trust a self-signed certificate merely because `cert.verify(cert.getPublicKey())` succeeds.
- [ ] Never let the application dynamically add roots to the truststore from a URL, request body, or attacker-supplied certificate.
- [ ] Check CRL/OCSP/short-lived certificates per policy; do not use offline demo settings in production.
- [ ] Protect CA keys, keep roots offline/in HSMs, enforce separation of duties for leaf issuance, and manage audits, backups, revocation, and key-compromise response.

## 14. Practice Exercises

1. Run the `keytool` script and `CertificateRolesDemo`. Why does **`Other root self-signed: true`** simultaneously produce **`PKIX with unrelated root: false`**? Which distinction does this illustrate?
2. After generating the temporary certificate for `intermediate` with `-genkeypair`, before importing the certificate reply, is it self-signed? Why does the answer change to `false` after the root signs and you import the reply?
3. Inspect `root.getBasicConstraints()`, `intermediate.getBasicConstraints()`, and `leaf.getBasicConstraints()`. Explain the meaning of pathLen root 1, intermediate 0, leaf -1. Why can the intermediate still sign the leaf?
4. Try calling `leaf.verify(root.getPublicKey())` instead of the intermediate public key. Predict the result and explain why the issuer name and signature link must match the issuing key.
5. Change the trust anchor from `root` to a new self-signed certificate you create. Why does path validation fail even though the new root's `verify(selfKey)` succeeds?
6. Change `SAN=dns:service.example.test` to a different name when issuing the leaf. Keep the same root/intermediate and check PKIX path validation and expected hostname separately; why do **the two conclusions differ**?
7. Try issuing an intermediate **without BasicConstraints CA=true** and have it sign the leaf. What does PKIX protect against, and why is `leaf.verify(intermediateKey)` alone insufficient?
8. Design an mTLS service issuing client certs from the same CA. What steps turn a “valid path” into “client is authorized to call the admin API”?
9. Write a trust anchor inventory record including owner, SPKI/cert fingerprint, algorithm, purpose, expiration date, rotation plan, how trust is updated, and how it is revoked.
10. Describe the process of rotating an intermediate in a system with thousands of services and multiple JDKs: served certificate chain, truststore, compatibility, CRL/OCSP, versions, cutover timing, and rollback procedure.

## References

- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): defines BasicConstraints, KeyUsage, CA/pathLen, path validation, self-issued/self-signed.
- [Java SE 17 — X509Certificate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html): `getBasicConstraints`, `verify`, SAN, KeyUsage, EKU, validity.
- [Java SE 17 — CertificateFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertificateFactory.html): parsing certificates and creating `CertPath`.
- [Java SE 17 — CertPathValidator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html): validating a path with the PKIX algorithm.
- [Java SE 17 — CertPathBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathBuilder.html): building certificate paths.
- [Java SE 17 — PKIXParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXParameters.html): trust anchors, revocation, and path validation parameters.
- [Java SE 17 — TrustAnchor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/TrustAnchor.html): representing an application-configured trust point.
- [Java SE 17 — KeyStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html): storing certificates/trust material and key entries.
- [Java SE 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): configuring endpoint identification.
- [JDK `keytool` reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): `-genkeypair`, `-certreq`, `-gencert`, `-importcert`, and `-exportcert`.
