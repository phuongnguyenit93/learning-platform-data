# 14.1 The `CertPath`, `TrustAnchor`, and Intermediate Certificate Model

## 1. Goal: A Certificate with a Valid Signature Is Not Enough to Be Trusted

In Java Security / PKI, an **X.509 certificate** typically binds a **public key** to a **subject** and carries the signature of an **issuer**. The fact that a certificate's signature verifies successfully **does not automatically** mean the application should trust that public key: first, you must determine whether that issuer is authorized to issue certificates, and then trace back through any **intermediate CA certificates** to a **trust anchor (`TrustAnchor`)** previously accepted by the application.

This lesson explains three core components:

- **`CertPath`:** a **certification path**, i.e., the ordered chain of the target certificate and intermediate certificates according to Java's ordering rules.
- **`TrustAnchor`:** the starting point **trusted by policy/configuration outside the path**, usually representing a root CA, which can be represented by a trusted CA certificate or a CA name + public key.
- **Intermediate certificate (`intermediate CA certificate`):** a CA certificate sitting between the target certificate and the anchor; it is **not trusted by default**, but is validated by the CA above it according to PKIX rules.

The content uses the **PKIX / RFC 5280** model and Java 17+. The hands-on example has **root → intermediate → leaf**, using `CertificateFactory`, `CertPathValidator`, `PKIXParameters`, `CertPathBuilder`, `CertStore`, and `TrustAnchor`.

**Most important rule:** *The certificate chain data sent by a peer is not a list of trusted roots.* A root CA is only a trust anchor once **the application itself or the trust environment has approved** it. Never accept any self-signed certificate merely because its signature verifies against itself.

## 2. What Does a Trusted Path Look Like?

Suppose service `demo.example.invalid` has a leaf certificate signed by an **Intermediate CA**; the Intermediate CA is signed by a **Root CA**:

```text
                      ISSUING SIDE / TRUST CONFIGURATION

         +----------------------------------------------------+
         | Root CA: installed and trusted TrustAnchor         |
         | Subject: CN=Training Root CA                       |
         | Root public key is managed, not taken from peer    |
         +---------------------------+------------------------+
                                     |
                      signs Intermediate certificate
                                     v
         +----------------------------------------------------+
         | Intermediate CA certificate                        |
         | Subject: CN=Training Intermediate CA               |
         | Issuer:  CN=Training Root CA                       |
         | BasicConstraints: CA=true, pathLenConstraint=0     |
         | KeyUsage: keyCertSign (+ cRLSign if CRL is used)   |
         +---------------------------+------------------------+
                                     |
                         signs leaf certificate
                                     v
         +----------------------------------------------------+
         | End-entity / leaf certificate                      |
         | Subject: CN=demo.example.invalid                   |
         | Issuer:  CN=Training Intermediate CA               |
         | BasicConstraints: CA=false                         |
         | Used per application purpose and identity          |
         +----------------------------------------------------+

Java CertPath (X.509) object in order:
    [leaf, intermediate]                // DO NOT put root here

Separate trust input:
    Set<TrustAnchor> = {trusted root}
```

The **signature relationship direction** is Root signs Intermediate, Intermediate signs Leaf. The **ordering direction in Java's `CertPath`**, however, goes from the *object to be validated* toward the *CA closest to the anchor*:

```text
getCertificates().get(0)  -> leaf (target)
getCertificates().get(1)  -> intermediate
TrustAnchor               -> root (outside CertPath)
```

The Java SE 17 documentation for `CertPath` and the *Java PKI Programmer's Guide* explicitly state that **the certificate representing the `TrustAnchor` should not be in the certification path**. A path built by `CertPathBuilder` under PKIX also **does not contain** the root/trust anchor; retrieve the anchor via `PKIXCertPathBuilderResult.getTrustAnchor()`.

### 2.1 Roles That Must Not Be Conflated

| Object | What does it represent? | Is it inherently trustworthy? | Where is it placed in Java? |
| --- | --- | --- | --- |
| Leaf / end entity | Identity or public key to verify for the application (TLS server, signer, etc.) | **No**; must have a valid path and matching policy | First certificate in `CertPath` |
| Intermediate CA | CA delegated to issue subordinate certificates | **Not inherently**; must verify signature chain, BasicConstraints, and constraints | Subsequent certificate(s) in `CertPath` |
| Root CA certificate | Usually a self-signed CA certificate containing the root public key | Only when **accepted/pre-installed via a trusted channel** | Usually used to create a `TrustAnchor`, not put into the path |
| `TrustAnchor` | Trusted CA information used to terminate path checking | **Yes, because it was chosen by application policy** | `Set<TrustAnchor>` in `PKIXParameters` |
| `CertPath` | Ordered sequence of certificates to be validated | **Not yet** until PKIX validation succeeds | `java.security.cert.CertPath` |
| `PKIXCertPathValidatorResult` | Successful PKIX validation result along with the trust anchor used | Meaningful under the **anchors + policy + validation date** passed in | Return value of `CertPathValidator.validate` |

**An organization may also actively configure an intermediate as a `TrustAnchor`.** In that case, the anchor is the approved intermediate, and the path can be shorter. The difference is a **policy role** (*anchor*) versus a **structural role** (*CA inside the path*), not merely the `BasicConstraints` field.

## 3. X.509 Foundations: Subject, Issuer, Signatures, and CA Authority

An X.509 certificate has fields/extensions used for path verification:

| Field/extension | Role in path checking | Notes |
| --- | --- | --- |
| `subject` | X.500 identity of the issued subject | Does not automatically mean hostname/application identity matches |
| `issuer` | Identity of the issuing party | Helps link to the upper CA; **matching names alone is insufficient** |
| `subjectPublicKeyInfo` | Public key of the leaf or CA | Used to verify the signature at the corresponding lower tier |
| `signatureAlgorithm` and `signatureValue` | Issuer's algorithm/signature over TBSCertificate | PKIX must verify the signature using the issuer's public key and algorithm constraints |
| `notBefore` / `notAfter` | Validity period | Validated against the configured date; must not be skipped |
| `BasicConstraints` | `CA=true/false`, plus `pathLenConstraint` if present | An intermediate signing subordinate certificates must have CA authority |
| `KeyUsage` | Key permissions: `keyCertSign`, `digitalSignature`, `keyEncipherment`, ... | A CA signing certificates needs `keyCertSign` if the extension is present |
| `ExtendedKeyUsage` | End-entity usage purposes: TLS `serverAuth`, `clientAuth`, `codeSigning`, ... | Applications need to verify the right purpose |
| `SubjectAlternativeName` (SAN) | Alternative DNS/IP/identity names of the leaf | TLS hostname matching **is a separate step**, not just path validation |
| `NameConstraints` | Restricts the namespaces a CA may issue for | PKIX enforces constraints per RFC |
| `CertificatePolicies`, `PolicyConstraints` | Controls certificate policies | Important for many specialized PKI systems |
| `AuthorityKeyIdentifier` (AKI), `SubjectKeyIdentifier` (SKI) | Hints for finding the corresponding issuer/key | Aids path building; **not the sole cryptographic proof** |
| CRL Distribution Points / AIA OCSP | Information for querying revocation status | Does not mean the runtime will automatically query successfully |

**`BasicConstraints` example:** root has `CA=true, pathLenConstraint=1`; intermediate has `CA=true, pathLenConstraint=0`. An intermediate with `pathLen=0` can still sign a **leaf end-entity**, but does not allow another **non-self-issued** intermediate CA below it in an allowed path. The path-length constraint is not a limit on the number of leaf certificates a CA may issue.

**`KeyUsage` example:** the intermediate has `keyCertSign`, and the root also has `keyCertSign`; the leaf uses `digitalSignature` as required by the application. Do not conflate a leaf's `digitalSignature` with CA signing authority. A CA merely having “CA” in its subject name is not enough to legitimize certificate issuance.

### 3.1 Why Is a Self-Signed Root Not Automatically Trustworthy?

A self-signed certificate means the certificate's own public key can verify the signature on **that very certificate**. This proves **self-consistency**, not CA identity or application approval. A `TrustAnchor` comes from a configuration file, an administrator-provisioned truststore, certificate pinning via a verified mechanism, or an equivalent trust policy.

If an attacker sends a chain:

```text
attacker leaf <- attacker self-signed root
```

then every signature may be mathematically valid. But if the attacker root **is not in the approved set of trust anchors**, PKIX validation must fail to terminate at that root. **Never create a `TrustAnchor` directly from an arbitrary root present in a peer-sent chain.**

### 3.2 A Trust Anchor Is Not Always a Full Certificate

Java `TrustAnchor` has common constructors:

```java
// Illustrated inside a method that has access to trustedRoot:
TrustAnchor byCertificate = new TrustAnchor(trustedRoot, null);

// Conceptual equivalent: specify CA name + trusted public key
TrustAnchor byNameAndKey =
        new TrustAnchor(
                trustedRoot.getSubjectX500Principal(),
                trustedRoot.getPublicKey(),
                null);
```

The second/third `null` argument here is **optional name constraints**. The name + public key constructor does not carry the full self-signed certificate. Both construction forms must only be used with **pre-trusted data**, never turning an arbitrary downloaded certificate into an accepted CA.

## 4. How Is `CertPath` Created and Read in Java?

The relevant components are in `java.security.cert`:

- `X509Certificate`: represents an X.509 certificate, allowing reading subject, issuer, extensions, public key, signature, and validity dates.
- `CertificateFactory.getInstance("X.509")`: parses DER/PEM certificates and creates a `CertPath` from a collection/list.
- `CertPath.getCertificates()`: reads the immutable list of certificates in the path.
- `CertPathValidator.getInstance("PKIX")`: **validates an already-determined path**.
- `CertPathBuilder.getInstance("PKIX")`: **discovers a valid path** from a certificate source and trust anchors under constraints.
- `PKIXParameters`: configures anchors, date, policy, revocation, and checkers for the validator.
- `PKIXBuilderParameters`: extends `PKIXParameters`, adding target selector, `CertStore`, and `maxPathLength`.
- `CertStore.getInstance("Collection", ...)`: provides candidate certificates (and possibly CRLs) from memory to the path builder.

Relationship model:

```text
Data already has a path
    [leaf, intermediate]
            |
            v
  CertificateFactory.generateCertPath(List)
            |
            v
  CertPathValidator("PKIX")
      + PKIXParameters(
            trusted anchors,
            date, revocation, policy, checkers
        )
            |
          success? ---- no ---> CertPathValidatorException
            |
           yes
            v
  PKIXCertPathValidatorResult
      .getTrustAnchor()
      .getPublicKey()
      .getPolicyTree()

Data has many candidate certificates, path not yet chosen
    leaf + intermediates in CertStore
            |
            v
  CertPathBuilder("PKIX")
      + PKIXBuilderParameters(anchors, X509CertSelector)
      + CertStore containing candidates
            |
          success?
            |
           yes
            v
  PKIXCertPathBuilderResult
      .getCertPath()      // order leaf -> intermediates; no anchor
      .getTrustAnchor()
```

`CertificateFactory.generateCertPath(List.of(leaf, intermediate))` **only builds the structure**; it does not perform PKIX validation. Likewise, `X509Certificate.checkValidity()` only checks the individual certificate's validity dates; `leaf.verify(intermediate.getPublicKey())` only checks the leaf's single signature. **Neither operation replaces full path validation.**

### 4.1 Wrong Order and Missing Intermediate

In a Java X.509 `CertPath`, the path is typically:

```java
// Illustrated; leaf and intermediate are loaded X509Certificates:
CertificateFactory factory = CertificateFactory.getInstance("X.509");
CertPath correct = factory.generateCertPath(
        java.util.List.of(leaf, intermediate)); // leaf first
```

Common mistakes:

- `[intermediate, leaf]` reversed order, even when both certificates are individually valid.
- `[leaf]` missing intermediate when the leaf is not directly issued by the root.
- `[leaf, intermediate, root]` placing the root into the path while also using the root as the `TrustAnchor`, violating Java PKIX convention.
- `[leaf, wrongIntermediate]` mismatched issuer name/key/signature or constraints.
- Only checking `leaf.getIssuerX500Principal().equals(intermediate.getSubjectX500Principal())` and accepting: matching names do not prove the signature is valid, the CA is authorized, or the path terminates at a trusted anchor.

Sometimes TLS or PEM data arrives in a different order, or there are multiple cross-signed intermediates. Use a **path builder** to find a valid path instead of assuming simple index/issuer-name checks suffice. The PKIX Builder only searches within **configured `CertStore` sources/mechanisms**; it is not guaranteed to automatically fetch all intermediates from the Internet.

## 5. Differences Between `CertPathValidator` and `CertPathBuilder`

| Aspect | `CertPathValidator` | `CertPathBuilder` |
| --- | --- | --- |
| Question | *Is this given path valid?* | *Can a valid path to a trust anchor be built?* |
| Primary input | Already-ordered `CertPath` + `PKIXParameters` | `PKIXBuilderParameters` with target `CertSelector`, `CertStore`, and anchors |
| Return on success | `PKIXCertPathValidatorResult` | `PKIXCertPathBuilderResult` |
| Discovers intermediates automatically? | No, because the path is already supplied | Yes, within the configured certificate sources/constraints |
| Is the trust anchor the last element of `CertPath`? | **No** | **No** |
| If an intermediate is missing | Validation usually cannot chain the path to a trusted root | Builder can find it if the candidate intermediate is in `CertStore` |
| Goal | Verify a specific path | Discover and verify a valid path |

**Quick mnemonic:** *Builder finds a path; Validator checks a path.* A PKIX `CertPathBuilder` builds a path that has already been verified during the build process, so it returns both the path and the selected trust anchor; when validating an existing path, you still must choose the right anchors/policies.

## 6. Java 17 Lab: Creating Three Certificates with `keytool`

This section uses a **completely local fixture**, does not download anyone else's private key, and needs no real CA connection. All `changeit` passwords are strictly for the lab—**never use them in production systems**.

### 6.1 Preparation and Generating Three Key Pairs

Open a shell with `keytool`, `javac`, and `java` from JDK 17+, and create a **dedicated lab directory**:

```bash
mkdir pkix-lab
cd pkix-lab
```

Create a **self-signed Root CA** with CA authority and room for one intermediate below it (`pathlen:1`). The command works in shells that handle standard double quotes (Bash, PowerShell):

```bash
keytool -genkeypair -alias root -dname "CN=Training Root CA, O=Local Demo" -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 365 -keystore root.p12 -storetype PKCS12 -storepass changeit -keypass changeit -ext "BC:critical=ca:true,pathlen:1" -ext "KU:critical=keyCertSign,cRLSign" -noprompt
```

Create an **Intermediate CA key pair** and a **leaf key pair**. At keypair generation time, `keytool` attaches a temporary self-signed certificate to the entry; the certificates with real CA relationships in the lab will be **signed via CSR in the next step**:

```bash
keytool -genkeypair -alias intermediate -dname "CN=Training Intermediate CA, O=Local Demo" -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 365 -keystore intermediate.p12 -storetype PKCS12 -storepass changeit -keypass changeit -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign" -noprompt
keytool -genkeypair -alias leaf -dname "CN=demo.example.invalid, O=Local Demo" -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 365 -keystore leaf.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt
```

### 6.2 Root Issues Intermediate; Intermediate Issues Leaf

**Step 1 — Intermediate CSR:** generate a certificate signing request from the Intermediate's public key / subject:

```bash
keytool -certreq -alias intermediate -keystore intermediate.p12 -storepass changeit -file intermediate.csr
```

**Step 2 — Root signs and issues the Intermediate certificate:**

```bash
keytool -gencert -alias root -keystore root.p12 -storepass changeit -infile intermediate.csr -outfile intermediate.pem -rfc -validity 365 -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign"
```

**Step 3 — Leaf CSR:**

```bash
keytool -certreq -alias leaf -keystore leaf.p12 -storepass changeit -file leaf.csr
```

**Step 4 — Intermediate signs the leaf certificate**, marking end entity, `serverAuth`, and an illustrative DNS SAN:

```bash
keytool -gencert -alias intermediate -keystore intermediate.p12 -storepass changeit -infile leaf.csr -outfile leaf.pem -rfc -validity 365 -ext "BC:critical=ca:false" -ext "KU:critical=digitalSignature,keyEncipherment" -ext "EKU=serverAuth" -ext "SAN=dns:demo.example.invalid"
```

**Step 5 — Export the Root's public certificate to serve as the trusted anchor in the lab:**

```bash
keytool -exportcert -alias root -keystore root.p12 -storepass changeit -file root.pem -rfc
```

Expected files:

```text
pkix-lab/
  root.p12                (contains root PRIVATE KEY: keep secret)
  intermediate.p12        (contains intermediate PRIVATE KEY: keep secret)
  leaf.p12                (contains leaf PRIVATE KEY: keep secret)
  intermediate.csr        (for certificate issuance only)
  leaf.csr
  root.pem                (public certificate; lab approves as anchor)
  intermediate.pem        (intermediate certificate signed by root)
  leaf.pem                (leaf certificate signed by intermediate)
```

The `.pem` files are **public X.509 certificates** without private keys; `.p12` files contain private keys and **must not** be uploaded to the Internet or committed to a repository. `keytool`'s `-rfc` flag exports PEM (Base64 with header/footer). These commands create **learning** data; production PKI requires CA issuance procedures, signing key protection, key ceremonies, certificate policies, revocation, and strict key management.

**Common lab pitfall:** `intermediate.p12` initially holds a keypair and a temporary self-signed certificate; `-gencert` uses the **corresponding private key** to sign `leaf.pem`. The path to validate in the next step must use **the Root-signed CA certificate `intermediate.pem`**, not the temporary self-signed certificate inside the keystore entry.

## 7. Complete Java 17 Program: Validate Path, Test Failures, Then Build Path

Create **`CertPathTrustModelDemo.java`** in the same directory as the three PEM files. The program:

1. Loads `root.pem`, `intermediate.pem`, and `leaf.pem` as `X509Certificate` using `CertificateFactory`.
2. Checks the CA attribute (`getBasicConstraints()`).
3. Creates a `CertPath` in **`[leaf, intermediate]`** order, creates `TrustAnchor(root, null)`, and validates using `CertPathValidator("PKIX")`.
4. Tests missing intermediate and reversed order: expects rejection.
5. Creates a `CertStore` with candidate certificates and uses `CertPathBuilder("PKIX")` to **find** the path.
6. Observes the result showing the path has **2 certificates**, with root appearing only in `TrustAnchor`.

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.cert.CertPath;
import java.security.cert.CertPathBuilder;
import java.security.cert.CertPathValidator;
import java.security.cert.CertPathValidatorException;
import java.security.cert.CertificateFactory;
import java.security.cert.CertStore;
import java.security.cert.CollectionCertStoreParameters;
import java.security.cert.PKIXBuilderParameters;
import java.security.cert.PKIXCertPathBuilderResult;
import java.security.cert.PKIXCertPathValidatorResult;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509CertSelector;
import java.security.cert.X509Certificate;
import java.util.List;
import java.util.Set;

public final class CertPathTrustModelDemo {
    private static X509Certificate readCert(String name) throws Exception {
        try (InputStream in = Files.newInputStream(Path.of(name))) {
            CertificateFactory factory = CertificateFactory.getInstance("X.509");
            return (X509Certificate) factory.generateCertificate(in);
        }
    }

    private static PKIXParameters validationParams(X509Certificate root)
            throws GeneralSecurityException {
        PKIXParameters params = new PKIXParameters(
                Set.of(new TrustAnchor(root, null)));
        // Lab-only: no CRL/OCSP infrastructure for these training certificates.
        params.setRevocationEnabled(false);
        return params;
    }

    private static boolean isRejected(CertPath path, X509Certificate root)
            throws GeneralSecurityException {
        try {
            CertPathValidator.getInstance("PKIX").validate(
                    path, validationParams(root));
            return false;
        } catch (CertPathValidatorException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: java CertPathTrustModelDemo root.pem intermediate.pem leaf.pem");
        }
        X509Certificate root = readCert(args[0]);
        X509Certificate intermediate = readCert(args[1]);
        X509Certificate leaf = readCert(args[2]);

        System.out.println("Intermediate is CA: " +
                (intermediate.getBasicConstraints() >= 0));
        System.out.println("Leaf is CA: " +
                (leaf.getBasicConstraints() >= 0));

        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        CertPath supplied = factory.generateCertPath(
                List.of(leaf, intermediate)); // Target first; no root.
        PKIXCertPathValidatorResult checked =
                (PKIXCertPathValidatorResult)
                CertPathValidator.getInstance("PKIX").validate(
                        supplied, validationParams(root));
        System.out.println("Supplied path size: " +
                supplied.getCertificates().size());
        System.out.println("Validated trust anchor is root: " +
                root.equals(checked.getTrustAnchor().getTrustedCert()));

        CertPath missingIntermediate = factory.generateCertPath(List.of(leaf));
        System.out.println("Missing intermediate rejected: " +
                isRejected(missingIntermediate, root));

        CertPath reversed = factory.generateCertPath(
                List.of(intermediate, leaf));
        System.out.println("Wrong certificate order rejected: " +
                isRejected(reversed, root));

        X509CertSelector target = new X509CertSelector();
        target.setCertificate(leaf);
        PKIXBuilderParameters builderParams = new PKIXBuilderParameters(
                Set.of(new TrustAnchor(root, null)), target);
        builderParams.setRevocationEnabled(false); // Lab only.
        builderParams.setMaxPathLength(1);
        builderParams.addCertStore(CertStore.getInstance(
                "Collection", new CollectionCertStoreParameters(
                        List.of(leaf, intermediate))));
        PKIXCertPathBuilderResult built = (PKIXCertPathBuilderResult)
                CertPathBuilder.getInstance("PKIX").build(builderParams);
        System.out.println("Builder path size: " +
                built.getCertPath().getCertificates().size());
        System.out.println("Builder path starts with leaf: " +
                leaf.equals(built.getCertPath().getCertificates().get(0)));
        System.out.println("Builder trust anchor is root: " +
                root.equals(built.getTrustAnchor().getTrustedCert()));
    }
}
```

Compile and run:

```bash
javac --release 17 CertPathTrustModelDemo.java
java CertPathTrustModelDemo root.pem intermediate.pem leaf.pem
```

**Verified** stdout with the three certificates generated by the lab commands:

```text
Intermediate is CA: true
Leaf is CA: false
Supplied path size: 2
Validated trust anchor is root: true
Missing intermediate rejected: true
Wrong certificate order rejected: true
Builder path size: 2
Builder path starts with leaf: true
Builder trust anchor is root: true
```

**Line-by-line explanation:**

- `Intermediate is CA: true` because `intermediate.pem` has valid CA BasicConstraints.
- `Leaf is CA: false`: the leaf does not have CA certificate-issuing authority.
- `Supplied path size: 2`: the path contains only **leaf and intermediate**; the root sits in the `TrustAnchor` set.
- `Validated trust anchor is root: true`: `validate` completed and returned the exact anchor configured in the lab.
- `Missing intermediate rejected: true`: the leaf was issued by **intermediate**, not directly by root; the path `[leaf]` cannot chain to the root anchor.
- `Wrong certificate order rejected: true`: `CertPath` is in the wrong order, not a path from target to anchor.
- `Builder path size: 2`: the builder found the intermediate from `CertStore` with the selector targeting the leaf.
- `Builder path starts with leaf: true`: confirms Java's ordering convention.
- `Builder trust anchor is root: true`: the builder returns the trusted root information separately.

**Intentional limitations:** `setRevocationEnabled(false)` in **both the validator and the builder** avoids setting up CRL/OCSP for self-created lab CAs. In production, **do not disable revocation just because the environment lacks network access**. You must implement an appropriate revocation policy (OCSP/CRL, timeouts, caching, offline and error handling) and test it realistically. Likewise, this program **does not perform TLS hostname verification**, does not enforce CT certificates, and does not automatically check all business requirements on the leaf: this is a **PKIX path model** example, not a complete HTTPS client.

One more note: the fixture validity is **365 days from creation time**. If you leave the files for years and rerun, it may fail due to expiration; regenerate the fixture or set a validation date for an intentional test scenario rather than “skipping” validity dates in production.

## 8. Placing `TrustAnchor` in the Right Spot: `PKIXParameters` and `KeyStore`

At the API level there are two common approaches:

### 8.1 Passing the Anchor Set Directly

```java
// Illustrated inside a method that throws GeneralSecurityException.
Set<TrustAnchor> anchors =
        Set.of(new TrustAnchor(trustedRootCertificate, null));
PKIXParameters params = new PKIXParameters(anchors);
```

- `PKIXParameters(Set<TrustAnchor>)` requires a **non-empty** set; if empty, an `InvalidAlgorithmParameterException` is thrown.
- `setDate(Date)` can be used to verify at a specific point in time; the default `null` value means the current time at validation, not “skip time checks”.
- `setInitialPolicies`, `setExplicitPolicyRequired`, `setAnyPolicyInhibited`, `setPolicyMappingInhibited`, etc. allow configuring policy-based PKIX constraints.
- `setRevocationEnabled(boolean)` controls revocation checking; proper configuration requires trusted data sources and a failure policy.
- `PKIXRevocationChecker` can provide OCSP/CRL control and options such as `PREFER_CRLS`, `ONLY_END_ENTITY`, or `SOFT_FAIL`. `SOFT_FAIL` is an intentional security decision, **not a default flag to ignore incidents**.

### 8.2 Loading Anchors from a Managed Truststore

```java
// Illustrated inside a method with access to a loaded trustStore:
PKIXParameters params = new PKIXParameters(trustStore);
```

The `PKIXParameters(KeyStore)` constructor treats **trusted certificate entries** in the truststore as anchor sources (per the API specification). It does not treat arbitrary certificates in keypair entries as trusted roots. On a JVM server, the truststore may be configured by the system, container, or application and must be managed as **security configuration**.

**Do not** build a truststore by downloading certificates from a TLS peer and calling `setCertificateEntry` on all of them, because that **turns untrusted data into trust anchors**. An internal truststore used for mTLS or testing should contain only CAs/peers approved by policy.

### 8.3 `TrustAnchor` and a Root Certificate in the Chain

If a TLS peer sends a root certificate along with its chain, the receiver **does not automatically trust that root**. The trust manager must look up an anchor in an **independently configured** truststore. A root in the peer chain may match a trusted anchor, but matching bytes are not the source of trust authority; the anchor is selected from the truststore.

An application with multiple anchors may find **multiple different valid paths** to different roots when cross-signing exists. The builder is allowed to choose one valid path according to provider constraints and candidates; applications should not assume “there is only one exact path”, or compare root names by display string to infer trust.

## 9. What Does PKIX Validation Check — and What Remains at the Application Layer?

According to RFC 5280 and provider algorithm/policy restrictions, path verification typically includes:

1. **Issuer–subject chaining and digital signatures:** a subordinate certificate can be verified using the public key of the corresponding superior CA.
2. **Validity periods** for the certificates in the path at the validation date.
3. **CA authority:** `BasicConstraints: CA=true` on issuer intermediates, appropriate `pathLenConstraint`, and `KeyUsage.keyCertSign` when the extension is present.
4. **Name constraints** inherited from CAs per RFC rules.
5. **Certificate policies/policy mappings** and recognized critical extensions.
6. **Runtime/policy algorithm constraints**, e.g., `jdk.certpath.disabledAlgorithms` for deprecated algorithms or key sizes.
7. **Revocation status** if enabled and configured with sufficient information/handling mechanisms.

Yet a successful `CertPathValidator.validate()` **is not enough** to accept a leaf for every application:

| What the application needs | Does PKIX path validation handle it fully? | What else must be checked |
| --- | --- | --- |
| Certificate has a valid chain to a trusted CA | **Yes**, within PKIX parameters and provider scope | Selecting the right anchors/policy for the application |
| Certificate matches the **TLS hostname** | **No**, checking only the path does not match the DNS name you connect to | SAN DNS/IP and endpoint identity per TLS/JSSE rules |
| Certificate is authorized for **TLS serverAuth** or **codeSigning** | Not automatically for every purpose | EKU/KeyUsage and application/JSSE policy |
| Whether the certificate has been revoked | Depends on `setRevocationEnabled` and checker/CRL/OCSP config | Revocation policy, offline/failure handling |
| Whether the root should be trusted for this tenant | Does not choose trust store policy automatically | Trust anchors partitioned by tenant/purpose |
| Whether the subject is authorized to perform a business action | **No** | Authorization, mapping identity → role/account |
| Replay protection / ensuring channel data is untampered? | Not by path alone | TLS handshake + record protection / other protocols |

**Distinguishing `CertPathValidator` from HTTPS verification:** JSSE `X509TrustManager`/`X509ExtendedTrustManager` handles chain validation in a TLS context; `HttpsURLConnection`/HTTP clients and endpoint identification configuration add protocol-specific hostname/purpose verification. An exercise calling `CertPathValidator` directly **does not replace a secure HTTPS client**.

## 10. Common Errors When Working with Intermediates and Roots

| Symptom/error | Common cause | Correct resolution |
| --- | --- | --- |
| `CertPathValidatorException` due to inability to chain to an anchor | Missing intermediate, wrong issuer/key, or root not in trusted set | Provide the right intermediate, **do not auto-trust peer-sent roots** |
| Using `CertPath [root, intermediate, leaf]` | Wrong order, putting trust anchor in the path | Create `[leaf, intermediate]`, pass root separately in `PKIXParameters` |
| Builder cannot find a path | `CertStore` missing intermediate or selector/constraints too strict | Check target `X509CertSelector`, candidate store, issuer/cert extensions |
| Intermediate certificate rejected | `BasicConstraints CA=false`, missing `keyCertSign`, wrong `pathLenConstraint` or critical extensions | The CA must reissue a valid intermediate certificate, **do not disable checks** |
| Certificate expired | `notAfter` has passed or `notBefore` is in the future | Reissue/renew properly, synchronize clocks; do not skip validity checks |
| `InvalidAlgorithmParameterException: trustAnchors must be non-empty` | Empty anchor set or truststore has no trusted cert entries | Install approved anchors before creating `PKIXParameters` |
| Revocation error due to network/missing CRL | Policy enabled but status source unavailable | Configure OCSP/CRL, cache/timeout, and approved fail-open/closed rules |
| `validate` succeeds but hostname is wrong | Code checks only the path, not server identity | Verify SAN/endpoint identification at the TLS/application layer |
| Auto-trusting a peer-sent root | Accidentally expanding trust anchors with untrusted data | Roots must come from an independently managed truststore/pinning |
| Matching `issuer.getName()` and treating as valid | Does not check signatures/policy/constraints | Use PKIX validator/builder |
| Using `getBasicConstraints() >= 0` as the entire check | Only indicates CA bit/depth, **does not prove a valid chain** | Must validate the entire path |
| Using the wrong Java certificate entry/keystore type | `KeyStore` contains key entries/certs other than trusted entries | Distinguish `isCertificateEntry`/entry policy, inspect actual truststore |

### 10.1 Diagnosing Exceptions Instead of Accepting Anyway

`CertPathValidatorException` can provide:

```java
// Illustrative snippet inside catch (CertPathValidatorException ex):
int index = ex.getIndex();  // position of failing cert in path, may be -1
CertPathValidatorException.Reason reason = ex.getReason();
```

The `index` value can help pinpoint which leaf/intermediate is involved, but **not every error is tied to an index**. Do not catch all exceptions and `return true` or automatically fall back to an untrusted self-signed CA. If validation fails, **do not accept the certificate**.

Do not use `jdk.certpath.disabledAlgorithms` to weaken policy as a compatibility “fix”. If an application uses weak algorithms or an invalid root, **migrate properly** (reissue certificates/keys, configure appropriate trust anchors) instead of turning off protections.

## 11. Exercises Using the Fixture

**Exercise A — Identify the three roles.** Run `keytool -printcert -file root.pem`, `-file intermediate.pem`, and `-file leaf.pem` to inspect subject, issuer, BasicConstraints, KeyUsage, SAN/EKU. Verify:

- The self-signed Root has identical subject/issuer; yet what makes it trusted is that the application selected it as a `TrustAnchor`.
- The Intermediate has its own subject, issuer is Root, `CA=true`, `pathlen:0`, and `keyCertSign` permission.
- The Leaf has issuer Intermediate, `CA=false`, and the lab DNS SAN.

**Exercise B — Reverse `CertPath` order.** Change `List.of(leaf, intermediate)` to `List.of(intermediate, leaf)` in the validate step. Why do the same two certificates fail to form a path from target to anchor? Use `getIndex()`/`getReason()` to understand the error without relying on a fixed provider text message.

**Exercise C — Drop the intermediate.** Pass only `[leaf]` to the validator, keeping Root as the anchor. Observe that the leaf cannot chain directly to the root. Add the intermediate to `CollectionCertStoreParameters` for the builder so it rediscovers the right path.

**Exercise D — Wrong anchor.** Generate **another root CA** in the lab and replace `TrustAnchor` with the new root. The `CertPath` still has valid internal signatures under the old root, yet **cannot terminate at the new anchor**. This is the difference between “a certificate with a valid signature” and “the application trusts the final issuer”.

**Exercise E — CA stripped of issuing authority.** Try replacing the Root-signed intermediate with a version lacking `CA=true` or missing `keyCertSign` (when KeyUsage is present), then verify the PKIX validator rejects it. Do not add that certificate to the truststore to bypass the error.

**Exercise F — Validity period and revocation.** Create a short-lived fixture and test after expiration; observe `CertPathValidatorException`. Explore `PKIXRevocationChecker` (which requires OCSP/CRL infrastructure) and explain why `setRevocationEnabled(false)` is only for closed lab experiments.

**Exercise G — Purpose and hostname.** Change the leaf's SAN to a different DNS name while keeping a valid root/intermediate. `validate()` alone is not enough to conclude the server matches the hostname. Also check endpoint identification/TLS rules and EKU/KeyUsage.

## 12. Checklist for Designing Trust Paths in Java

- [ ] **Never take a trust anchor from untrusted data**; trust CAs/identities via a managed truststore/policy.
- [ ] Distinguish **leaf, intermediate, and root**; X.509 `CertPath` orders leaf → intermediate; root/anchor **stays outside** the path.
- [ ] With `CertPathValidator("PKIX")`, pass the **right `PKIXParameters`**, date, anchors, policies, and revocation settings.
- [ ] With `CertPathBuilder("PKIX")`, provide the **right target** selector and a `CertStore` containing intermediate candidates; do not expect all intermediates to auto-download.
- [ ] Do not hand-roll an “issuer → subject name matching” algorithm and treat it as path validation; signatures, BasicConstraints, KeyUsage, validity, constraints, and policies must all be checked.
- [ ] Do not confuse `KeyStore` trusted cert entries with keypair/private-key entries or peer-presented certificates.
- [ ] Do not skip hostname/EKU/purpose checks when using certificates for TLS, mTLS, code signing, or business identities.
- [ ] Revocation must be a **real policy decision** with OCSP/CRL and error handling; disabling it is strictly for labs.
- [ ] Monitor algorithms/key sizes rejected by JDK policy; **do not disable protections** to run weak certificates.
- [ ] Include negative tests: missing intermediate, reversed order, wrong root, CA=false, missing keyCertSign, expired certificate, hostname mismatch.
- [ ] Do not put CA private keys from fixtures or production systems into source code, logs, repositories, or publicly downloadable files.

## 13. Knowledge Self-Check

**1. In Java, how is the `CertPath` for root → intermediate → leaf ordered?**  
Under Java's X.509 path convention: **`[leaf, intermediate]`** from target toward the trust anchor. `root` is supplied separately as a `TrustAnchor`, not added to the list.

**2. Is `TrustAnchor` just any self-signed certificate?**  
**No.** It is CA information configured as **trusted outside the path**. A self-signed certificate sent by an attacker cannot become an anchor on its own.

**3. Once an Intermediate is signed by Root, does it automatically become a trusted root?**  
**No.** The intermediate is a CA certificate in the path; its signature/constraints must be verified and it must chain up to an existing trusted anchor.

**4. Does `pathLenConstraint=0` on an intermediate forbid issuing leaf certificates?**  
**No.** It forbids additional **non-self-issued** intermediate CAs below it in a valid path; it does not forbid issuing leaf certificates.

**5. Does `CertificateFactory.generateCertPath` automatically validate the chain?**  
**No.** It creates the representation. Use `CertPathValidator("PKIX").validate` to verify a path; the builder can discover and validate a path according to constraints.

**6. How do `CertPathValidator` and `CertPathBuilder` differ?**  
Validator **validates a given path**. Builder **discovers a path** from source certificates/`CertStore` and trust anchors, returning a valid path when building succeeds.

**7. Does a successful `validate()` guarantee the hostname in the URL matches the certificate?**  
**No.** SAN/endpoint identity along with key usage/purpose checks must still be performed at the application/TLS layer.

**8. Why does the example set `setRevocationEnabled(false)`, and should production copy it as-is?**  
The lab has no CRL/OCSP infrastructure to test revocation. Production must have an appropriate revocation policy; disabling it for convenience can allow revoked certificates to still be accepted.

## Official References

- [Java SE 17 — `CertPath`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPath.html): certificate collection, X.509 ordering rules, and the separate role of the trust anchor.
- [Java SE 17 — `TrustAnchor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/TrustAnchor.html): trusted CA model with certificate or CA name + public key, name constraints.
- [Java SE 17 — `CertPathValidator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html): PKIX validation engine and exceptions.
- [Java SE 17 — `CertPathBuilder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathBuilder.html): building paths using target constraints, source certificates, and trust anchors.
- [Java SE 17 — `PKIXParameters`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXParameters.html): anchors, date, policies, revocation.
- [Java SE 17 — `PKIXBuilderParameters`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXBuilderParameters.html): target selector, CertStore, max path length.
- [Java SE 17 — `PKIXCertPathValidatorResult`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXCertPathValidatorResult.html): result containing `getTrustAnchor`, public key, policy tree.
- [Java SE 17 — `PKIXCertPathBuilderResult`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXCertPathBuilderResult.html): built path and separate trust anchor.
- [Java SE 17 — Java PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/17/security/java-pki-programmers-guide.html): official guide on building and validating certification paths.
- [Java SE 17 — `keytool` reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): `-genkeypair`, `-certreq`, `-gencert`, `-ext BC`, `-ext KU`, `-exportcert`.
- [RFC 5280 — X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): §4.2.1.9 BasicConstraints; §4.2.1.3 KeyUsage; §6 path validation and trust anchors.

**Conclusion:** `CertPath` is **the sequence of certificates to inspect**, an intermediate is **a link that must be validated**, and `TrustAnchor` is **the policy-trusted starting point**. `CertPathValidator` checks a given path; `CertPathBuilder` discovers a valid path from candidate certificates. Never accept a certificate solely because its signature verifies — trust it only when it has a **valid path to an approved anchor and satisfies your application's own constraints**.
