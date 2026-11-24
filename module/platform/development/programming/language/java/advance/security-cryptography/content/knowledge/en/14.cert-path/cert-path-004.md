# 14.4 Collecting Certificates or CRLs via CertStore

In a PKI system, **having a syntactically valid certificate is not enough to trust the sender**, and **having a Certificate Revocation List (CRL) is not enough to conclude a certificate has not been revoked**. When building or validating a **certification path**, a Java application often needs to retrieve intermediate CA certificates and CRLs issued by CAs. The standard **`java.security.cert.CertStore`** API handles the **step of searching/collecting candidates** from a repository.

This lesson covers how to use `CertStore` and the selectors `X509CertSelector` and `X509CRLSelector` in Java 17+; how to build a `"Collection"` store from parsed certificates/CRLs; how `"LDAP"` lookups work; how to attach a `CertStore` to **PKIX** parameters; and the critical boundary between **retrieving data**, **verifying a CRL signature**, **validating a CA chain**, and **checking revocation status**. A standalone Java program and `keytool` commands for generating test fixtures are included so learners can reproduce the results without connecting to an external server.

> **Core principle:** `CertStore` supplies **candidate certificates/CRLs**, not a list of automatically trusted certificates. **Trust anchors**, certificate policies, PKIX path validation, and revocation checking are separate steps that must be executed properly.

## 1. Where Does CertStore Fit in X.509 Verification?

A typical TLS certificate chain may look like:

```text
Leaf certificate (server.example)
       |
       | signed by
       v
Intermediate CA certificate
       |
       | signed by
       v
Root CA (configured as trust anchor)
```

When an application receives only the leaf certificate, it may be **missing the intermediate certificate**. In addition, security policy may require looking up a CRL to determine whether a certificate was revoked by the CA before expiration.

`CertStore` provides a read interface:

```text
                  +---------------------------+
                  | CertStore (Collection,    |
                  | LDAP, provider-specific)  |
                  +-------------+-------------+
                                |
                 +--------------+--------------+
                 |                             |
      getCertificates(selector)        getCRLs(selector)
                 |                             |
       candidate certificates              candidate CRLs
                 |                             |
                 +--------------+--------------+
                                |
                PKIX CertPathBuilder / Validator
                   + trust anchors / policy
                   + signature/time checks
                   + revocation checking
                                |
                    ACCEPT / REJECT per policy
```

**Distinguishing the classes:**

| Concept | Role | Does it establish trust on its own? |
| --- | --- | --- |
| `KeyStore` | Stores/accesses keys, private keys, and trusted certificates per provider | A **configured truststore** can hold trust anchors; not every KeyStore is a truststore |
| `CertStore` | Queries certificates and CRLs from a repository | **No**; collected results are unverified data requiring validation |
| `CertificateFactory` | Parses PEM/DER into `Certificate`, `CRL`, or `CertPath` | **No**; successful parsing does not imply trust |
| `X509CertSelector` | Sets filter criteria for X.509 certificates | **No**; filters by attributes, does not replace chain validation |
| `X509CRLSelector` | Sets filter criteria for X.509 CRLs | **No**; issuer/time matching does not prove a valid signature |
| `TrustAnchor` | Root CA certificate/public key approved by the application per trust policy | **Provides the trust foundation** when provisioned properly |
| `CertPathBuilder("PKIX")` | Finds a valid certification chain meeting PKIX parameters | Builds a path based on trust anchors and policy |
| `CertPathValidator("PKIX")` | Validates an existing `CertPath` | Validates the path, with appropriate revocation config |
| `PKIXRevocationChecker` | Controls how revocation checking runs under PKIX | Coordinates CRL/OCSP, network/policy, not a repository itself |

`CertStore` is a **candidate retrieval mechanism**. Never use `getCertificates(...)` instead of `CertPathValidator.validate(...)` or instead of TLS hostname verification.

### 1.1. Why Is “Collecting” Different from “Verifying”?

A configured LDAP directory or file can contain **expired** certificates, certificates from CAs no longer trusted, stale CRLs, or tampered files. A selector can filter accurately by subject/issuer name and **still return an attacker's certificate with a colliding name**. Therefore:

- `getCertificates` only identifies **candidates matching criteria**; it does not tell you “who this party is” at PKIX trust level.
- `getCRLs` only fetches **candidate revocation lists**; it does not confirm the CRL was genuinely signed by a trusted CA.
- `X509CRL.isRevoked(cert)` checks one CRL in hand, which is insufficient to prove a certificate is currently valid for every policy.
- Only **validation** with trust anchors, validation date, algorithms, key usage, name constraints, policies, and revocation rules yields a valid trust conclusion.

## 2. Core API of `java.security.cert.CertStore`

`CertStore` is a **Security Provider–based engine class**. `getInstance(...)` selects the type and configures the repository.

```java
CertStore store = CertStore.getInstance("Collection", parameters);
Collection<? extends Certificate> certs = store.getCertificates(certSelector);
Collection<? extends CRL> crls = store.getCRLs(crlSelector);
```

This is an illustrative excerpt, not a standalone program: `parameters`, `certSelector`, and `crlSelector` must be initialized; the complete program is in Section 6.

### 2.1. Primary Types and Methods

| API | Meaning |
| --- | --- |
| `CertStore.getInstance(String type, CertStoreParameters params)` | Creates a repository by type/provider with initialization parameters |
| `CertStore.getInstance(type, params, provider)` | Selects a specific provider when needed |
| `CertStore.getType()` | Type used, e.g., `Collection` |
| `CertStore.getProvider()` | Provider implementing the repository |
| `CertStore.getCertificates(CertSelector)` | Returns a collection of candidate certificates matching the selector |
| `CertStore.getCRLs(CRLSelector)` | Returns a collection of candidate CRLs matching the selector |
| `CollectionCertStoreParameters` | Specifies an in-memory collection as the repository |
| `LDAPCertStoreParameters` | Specifies LDAP host/port for the corresponding repository |
| `CertStoreException` | Error while querying the repository, including remote source failures |

**Meaning of return values:**

- If no items match, the API returns an **empty collection**, **never** `null` per contract.
- `CertStoreException` represents a **collection failure**, completely distinct from “queried successfully and found zero matching items”.
- With remote repositories, the returned collection may be **incomplete** when the provider cannot scan the whole source; selectors act as both **filter criteria** and **query hints**.
- `CertStore.getInstance` may throw `NoSuchAlgorithmException` if the type is unsupported or `InvalidAlgorithmParameterException` if configuration is invalid.
- `getCertificates(null)`/`getCRLs(null)` may be supported to request all records, **but do not assume** every repository—especially LDAP—permits scanning everything when the selector is too vague.

### 2.2. Why Not Use `KeyStore` to Look Up All Intermediates/CRLs?

`KeyStore` typically accesses an **application-managed dataset**: trusted roots, private keys, and imported certificate chains. It is not a general-purpose API for querying an LDAP directory or a potentially huge repository by subject/issuer criteria.

`CertStore` fits when the application holds **many certificates and CRLs in memory**, needs to supply that list to `CertPathBuilder`, or needs a provider to query an external source by selector. Never use `CertStore` to store private keys; `Certificate` and `CRL` objects here are public/distributable PKI artifacts.

## 3. Retrieving Certificates with `X509CertSelector`

`X509CertSelector` implements `CertSelector` and provides many criteria for selecting X.509 certificates. Criteria configured together normally mean **the certificate must satisfy all configured conditions**.

### 3.1. Common Criteria

- `setSubject(X500Principal)`: selects certificates with a specific **Subject DN**.
- `setIssuer(X500Principal)`: selects certificates issued by a specific **Issuer DN**.
- `setCertificate(X509Certificate)`: selects the certificate matching the specified certificate/object per contract.
- `setSerialNumber(BigInteger)`: selects by certificate serial number.
- `setCertificateValid(Date)`: selects certificates whose validity period (`notBefore`, `notAfter`) covers the specified instant.
- `setBasicConstraints(int)`: distinguishes CA and end-entity certificates; **`setBasicConstraints(0)`** in the example selects CAs with matching basic constraints.
- `setKeyUsage(boolean[])`: filters required KeyUsage bits.
- `setSubjectAlternativeNames(...)` or `addSubjectAlternativeName(...)`: filters by SAN with the appropriate structure/type.

Example filtering a CA certificate with a known subject:

```java
// Illustrative, not a standalone program:
X509CertSelector selector = new X509CertSelector();
selector.setSubject(new X500Principal("CN=Training Demo CA,O=Learning"));
selector.setBasicConstraints(0);
Collection<? extends Certificate> matches = store.getCertificates(selector);
```

Most applications **should not compare DN strings manually**, because ordering, encoding, and escaping of X.500 names can vary. Using `X500Principal` and standard selectors/APIs reduces errors.

### 3.2. `setSubject` vs `setIssuer`

Suppose:

```text
Leaf:         Subject = CN=api.example       Issuer = CN=Intermediate CA
Intermediate: Subject = CN=Intermediate CA    Issuer = CN=Root CA
Root:         Subject = CN=Root CA            Issuer = CN=Root CA (self-signed)
```

To **find the intermediate that signed the leaf**, you usually look for a certificate **whose Subject equals the leaf's Issuer**, and then still verify the leaf's signature with the intermediate's public key, check CA/key usage, and build a path to a trust anchor. Setting `setIssuer(leaf.getIssuerX500Principal())` searches for certificates **issued by the intermediate**, not necessarily the intermediate certificate itself.

One way to fetch issuer candidates:

```java
X509CertSelector findIssuer = new X509CertSelector();
findIssuer.setSubject(leaf.getIssuerX500Principal());
findIssuer.setBasicConstraints(0); // Search CA candidates only
Collection<? extends Certificate> issuerCandidates =
        store.getCertificates(findIssuer);
```

This is an excerpt, since `leaf` and `store` must already exist. **Matching DNs do not prove it is the same issuer key**; the PKIX builder/validator also evaluates signatures, AuthorityKeyIdentifier, SubjectKeyIdentifier, policy, name constraints, and trust anchors.

### 3.3. Avoiding Misinterpretation of Results

If the selector returns **one** certificate, it can still be untrusted. If it returns **multiple** certificates, do not blindly pick the first element. If it returns **empty**, the repository may be missing the intermediate or the selector may be too strict; never automatically fall back to “skip certificate chain checking”.

In particular, `setCertificateValid(new Date())` only filters by the certificate's **validity dates** at the current instant; it **does not check revocation, hostname, EKU, policy, or chain**. When verifying historical signatures, the relevant validity instant may not be “now” and must follow business policy.

## 4. Retrieving CRLs with `X509CRLSelector`

A **CRL (Certificate Revocation List)** is an X.509 structure issued by a CA or an appropriately authorized entity listing revoked certificates. It includes metadata such as:

- **Issuer** of the CRL;
- **thisUpdate** — when the CRL was issued/updated;
- **nextUpdate** — when the next list is expected;
- **CRL entries** with serial number, revocation date, and optionally reason;
- **signature**, signature algorithm, and extensions such as CRL Number, Authority Key Identifier, and Issuing Distribution Point.

Not every CRL applies to every certificate with the same issuer name: **scope**, distribution points, certificate types, reason coverage, indirect CRLs, and delta CRLs must be considered when supported by the protocol.

### 4.1. Basic Criteria

`X509CRLSelector` implements `CRLSelector`. Useful methods:

| API | Role |
| --- | --- |
| `addIssuer(X500Principal)` | Selects only CRLs with a matching issuer DN |
| `setIssuers(Collection<X500Principal>)` | Selects a set of accepted issuer DNs |
| `setDateAndTime(Date)` | Accepts only CRLs where `thisUpdate ≤ time < nextUpdate` |
| `setCertificateChecking(X509Certificate)` | Provides a **hint** about the certificate being checked, helping the repository locate the CRL |
| `setMinCRLNumber(BigInteger)` | Selects CRL Numbers not lower than the threshold (if the extension is present) |
| `setMaxCRLNumber(BigInteger)` | Selects CRL Numbers not exceeding the threshold |
| `match(CRL)` | Checks whether a CRL satisfies the filter criteria |

To locate a CRL issued by a specific CA:

```java
X509CRLSelector selector = new X509CRLSelector();
selector.addIssuer(issuerCert.getSubjectX500Principal());
selector.setCertificateChecking(certBeingChecked);
selector.setDateAndTime(new Date());

Collection<? extends CRL> candidates = store.getCRLs(selector);
```

This is an illustrative excerpt; `issuerCert`, `certBeingChecked`, and `store` must be initialized in real code.

**Common misconception:** `setCertificateChecking(cert)` **is not a standalone filter asking “is this cert revoked?”**. It is **supporting information for locating a CRL**; if only `setCertificateChecking` is set without clear issuer/criteria, the provider may fail to query all sources. In practice, add the appropriate issuer and date for the verification goal.

### 4.2. Why Is `setDateAndTime` So Important?

A CRL past `nextUpdate` may **no longer be fresh enough** to make revocation decisions at the current time. `X509CRLSelector.setDateAndTime(now)` requires:

```text
thisUpdate <= now < nextUpdate
```

Per the X.509 selector contract, **if a CRL has no `nextUpdate`, this date criterion does not match**. Therefore, “no CRL found” can happen because the CRL is stale, lacks the field, or due to clock skew; never infer “certificate is not revoked”.

Real PKIX verification systems need policies for clock skew, coverage, CRL freshness, and fallback sources (OCSP), not just a single date filter.

### 4.3. What Is `X509CRL.isRevoked` and Where Does It Fall Short?

Once you have a specific `X509CRL`, `crl.isRevoked(cert)` asks whether that certificate is listed as revoked in **the CRL in hand**.

If it returns `false`, there are at least four possibilities:

1. The certificate is genuinely not revoked and the applicable, current CRL was checked properly;
2. The CRL **does not apply** to that certificate;
3. The CRL is **stale**, lacks recent updates, or is a partial/delta CRL;
4. The CRL's **signature and chain trust have not been verified**, so the data could be forged.

Thus, **`false` does not mean “trusted certificate”**. Beyond the CRL, you must also check validity, chain, BasicConstraints, KeyUsage, EKU, hostname/name constraints, algorithms, and trust policy.

### 4.4. Verifying a CRL Signature

`X509CRL.verify(PublicKey)` verifies the signature of **a CRL** under the provided public key. Yet if that public key comes from an unverified certificate, a “valid” signature is still insufficient to trust the CRL.

When building a complete system, identify the proper **CRL signer**, check its chain to a trust anchor, `cRLSign` KeyUsage, issuer/authority key identifier, scope/IDP, signature algorithm, and CRL validity. Java's PKIX revocation checker handles much more complex rules and selection logic than calling `verify` and `isRevoked` alone.

## 5. Preparing Certificate and CRL Fixtures with `keytool`

So this lesson **runs standalone without LDAP or Internet access**, we create a self-signed **demo-only** CA and a CRL from that CA. `keytool` bundled with the JDK can export PEM certificates and PEM CRLs (`-rfc`).

**Safety note:** the password `samplepass` in the commands below is strictly for a temporary fixture created in an isolated learning directory. Never use commands containing passwords on the command line for production secrets, as shell history, process lists, and CI logs can capture them. **Do not import the demo CA into any real truststore.**

Use a **dedicated empty directory for this lesson**, then run these single-line commands (usable in any shell with `keytool` in `PATH`):

```bash
keytool -genkeypair -alias demo-ca -keyalg RSA -keysize 2048 -validity 365 -dname "CN=Training Demo CA,O=Learning" -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign" -storetype PKCS12 -keystore demo-ca.p12 -storepass samplepass -keypass samplepass -noprompt

keytool -exportcert -rfc -alias demo-ca -keystore demo-ca.p12 -storepass samplepass -file demo-ca.pem

keytool -gencrl -rfc -alias demo-ca -keystore demo-ca.p12 -storepass samplepass -file demo-ca.crl.pem
```

Explanation of each command:

1. **`-genkeypair`:** generates a key pair and self-signed CA certificate with `BasicConstraints=CA:true` and `KeyUsage` containing `keyCertSign`, `cRLSign`. This is a **test CA** and must not be treated as a real CA trusted by browsers or operating systems.
2. **`-exportcert -rfc`:** exports the **public certificate** in PEM format to `demo-ca.pem`; does not export the private key.
3. **`-gencrl -rfc`:** uses the demo CA's private key to issue `demo-ca.crl.pem` in PEM format containing a signed CRL. Without `-id`, the fixture normally lists no revoked certificate serials.

With the commands above, `demo-ca.p12` holds a **test private key**; never commit or publish it. After experimenting, you can delete the entire fixture in the test directory; for demonstration, the Java code reads only **`demo-ca.pem`** and **`demo-ca.crl.pem`**.

### 5.1. How to Recognize the Two PEM Files?

A PEM certificate begins with:

```text
-----BEGIN CERTIFICATE-----
... (base64 encoding of certificate)
-----END CERTIFICATE-----
```

A PEM CRL begins with:

```text
-----BEGIN X509 CRL-----
... (base64 encoding of CRL)
-----END X509 CRL-----
```

The snippets above illustrate **format only**, not valid certificates to import. PEM is a **Base64 representation of ASN.1/DER data with headers**, which does not make a certificate or CRL any more trustworthy. For binary DER data, `CertificateFactory.getInstance("X.509")` can also parse it depending on provider support.

### 5.2. Why Is the Demo CA Used as a `TrustAnchor`?

In the Section 6 code, we register this demo certificate as a `TrustAnchor` **solely to show PKIX parameters accepting a CertStore**. In a real application, trusted CAs must be provisioned/evaluated by policy from a trusted source; **never automatically add arbitrary CAs found via CertStore as TrustAnchors**. Doing so lets an attacker insert their own CA into the trusted list and sign forged certificates.

## 6. Complete Java 17+ Program: `CertStore` from `Collection`

The program below:

- Parses one X.509 certificate and one X.509 CRL from the two generated PEM files;
- Creates `CertStore.getInstance("Collection", CollectionCertStoreParameters(...))`;
- Queries certificates with `X509CertSelector` by Subject and CA BasicConstraints;
- Queries a non-existent subject, producing an empty result;
- Queries CRLs with `X509CRLSelector` by CA issuer, `setCertificateChecking`, and time;
- Illustrates that **verifying the CRL signature** is separate from the lookup operation;
- Attaches `CertStore` to `PKIXParameters` in memory, without claiming to have validated a real TLS chain.

This is **runnable code** with Java 17 or higher and the fixtures from Section 5.

Save with the exact name **CertStoreCollectionDemo.java**:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CRL;
import java.security.cert.CertStore;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import java.security.cert.CollectionCertStoreParameters;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509CRL;
import java.security.cert.X509CRLSelector;
import java.security.cert.X509CertSelector;
import java.security.cert.X509Certificate;
import java.util.Collection;
import java.util.Date;
import java.util.List;
import java.util.Set;
import javax.security.auth.x500.X500Principal;

public class CertStoreCollectionDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "usage: CertStoreCollectionDemo cert.pem issuer.crl.pem");
        }

        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        X509Certificate ca;
        X509CRL crl;
        try (InputStream certificateStream =
                     Files.newInputStream(Path.of(args[0]));
             InputStream crlStream =
                     Files.newInputStream(Path.of(args[1]))) {
            ca = (X509Certificate) factory.generateCertificate(
                    certificateStream);
            crl = (X509CRL) factory.generateCRL(crlStream);
        }

        CertStore store = CertStore.getInstance(
                "Collection",
                new CollectionCertStoreParameters(List.of(ca, crl)));

        X509CertSelector bySubject = new X509CertSelector();
        bySubject.setSubject(ca.getSubjectX500Principal());
        bySubject.setBasicConstraints(0); // Select CA certificate.
        Collection<? extends Certificate> certificates =
                store.getCertificates(bySubject);

        X509CertSelector missingSubject = new X509CertSelector();
        missingSubject.setSubject(
                new X500Principal("CN=Not In Store"));
        Collection<? extends Certificate> missing =
                store.getCertificates(missingSubject);

        X509CRLSelector byIssuer = new X509CRLSelector();
        byIssuer.addIssuer(ca.getSubjectX500Principal());
        byIssuer.setCertificateChecking(ca);
        byIssuer.setDateAndTime(new Date());
        Collection<? extends CRL> crls = store.getCRLs(byIssuer);

        // Signature check on demo CRL only; does NOT replace PKIX.
        crl.verify(ca.getPublicKey());
        ca.checkValidity();

        // Demo pre-trusted anchor. Do not do this with CAs from CertStore.
        PKIXParameters parameters = new PKIXParameters(
                Set.of(new TrustAnchor(ca, null)));
        parameters.addCertStore(store);

        System.out.println("CertStore type: " + store.getType());
        System.out.println("CA certificates matched: "
                + certificates.size());
        System.out.println("unknown subject matched: "
                + missing.size());
        System.out.println("current CRLs matched: " + crls.size());
        System.out.println("CRL issuer equals CA subject: "
                + crl.getIssuerX500Principal()
                     .equals(ca.getSubjectX500Principal()));
        System.out.println("CRL signature verified: true");
        System.out.println("demo CA listed as revoked: "
                + crl.isRevoked(ca));
        System.out.println("PKIX CertStores registered: "
                + parameters.getCertStores().size());
    }
}
```

Compile and run **after creating the fixtures**:

```bash
javac -encoding UTF-8 CertStoreCollectionDemo.java
java CertStoreCollectionDemo demo-ca.pem demo-ca.crl.pem
```

Expected stdout on a JDK with the `Collection` provider and the newly generated demo certificate/CRL:

```text
CertStore type: Collection
CA certificates matched: 1
unknown subject matched: 0
current CRLs matched: 1
CRL issuer equals CA subject: true
CRL signature verified: true
demo CA listed as revoked: false
PKIX CertStores registered: 1
```

The program was checked with Java 17–compatible compilation (`javac --release 17`) and run on a JDK supporting Java 17+ with `keytool` fixtures. **Results may differ if the CRL passes `nextUpdate`, the certificate expires, or fixtures were modified**; generate fresh fixtures before each run.

### 6.1. Analyzing Each Code Block

**X.509 Parsing:** `CertificateFactory.generateCertificate` and `generateCRL` create Java objects from PEM/DER data. Successful parsing **does not** verify trust chains or download sources. `try-with-resources` closes the file streams.

**In-memory repository:** `new CollectionCertStoreParameters(List.of(ca, crl))` places both types of objects into one `Collection`; the provider filters matching certificates and CRLs. Here the certificate and CRL are **not** fetched over the network.

**Certificate selector:** `setSubject(ca.getSubjectX500Principal())` together with `setBasicConstraints(0)` finds the CA certificate with the right Subject. `CN=Not In Store` does not match and returns an empty collection.

**CRL selector:** `addIssuer(ca.getSubjectX500Principal())` matches the demo CRL's issuer; `setDateAndTime(new Date())` selects only CRLs within `thisUpdate/nextUpdate` at runtime. `setCertificateChecking(ca)` provides a hint matching the fixture; it **does not automatically check revocation**.

**Individual checks:** `crl.verify(ca.getPublicKey())` verifies the demo CRL's signature with the demo CA's public key; `ca.checkValidity()` separately checks the certificate's validity dates. **Neither constitutes full PKIX path validation.**

**PKIX registration:** `new PKIXParameters(Set.of(new TrustAnchor(ca, null)))` simply creates parameters with the CA we **explicitly chose to trust in the demo environment**. `parameters.addCertStore(store)` lets a PKIX builder/validator use the repository; this code **does not yet invoke `CertPathBuilder.build` or `CertPathValidator.validate`**.

**`crl.isRevoked(ca) == false`:** the fixture CRL does not contain the demo CA's serial. This output **must not be used as a production security decision mechanism**; a self-signed demo CA is also not a complete model for end-entity CRL checking.

### 6.2. An Especially Important Negative Test

Swapping in another certificate/CRL file, choosing a mismatched issuer DN, or setting `setDateAndTime` past `nextUpdate` can cause the query to return **0**. In that case:

- `getCRLs` returning 0 means **no candidate met the criteria**, not confirmation that “the target is not revoked”.
- A parsed and returned CRL might **not be signed by the right issuer** if an untrusted file was substituted; signature and policy must be verified.
- If a PEM file is corrupted, `generateCertificate` or `generateCRL` may throw `CertificateException`/`CRLException`; that is an input/parsing error, not “no CRL”.
- If an LDAP repository suffers a network error, `CertStoreException` is likewise distinct from returning 0.

For this reason, real code must distinguish **FOUND**, **NO_MATCH/INSUFFICIENT_DATA**, **FETCH_ERROR**, **PARSE_ERROR**, **UNTRUSTED_DATA**, and **VALIDATED** instead of collapsing all of them into a single “certificate valid” boolean.

## 7. Supplying CertStore to `CertPathBuilder` and `CertPathValidator`

Using `CertStore` is most valuable inside a **PKIX certification path** workflow. This section describes how to wire the APIs without pretending a single lookup equals chain validation.

### 7.1. Discovering Paths with `PKIXBuilderParameters`

For the builder to find a chain from leaf to a trusted CA, the application needs:

1. **Trust anchors configured as trusted** from a separate truststore/policy; never promote every certificate returned by the repository into anchors automatically.
2. **Target constraints** identifying the certificate to build a chain for via `X509CertSelector` (e.g., exact certificate, subject, SAN).
3. **CertStores** supplying candidate intermediate certificates and CRLs.
4. **Other PKIX parameters**: validation date, signature/provider policy, path length, certificate policies, revocation policy, and any required checkers.
5. Call `CertPathBuilder.getInstance("PKIX").build(params)`; treat `CertPathBuilderException` as **unable to build a valid chain under configuration**, without automatically retrying by dropping trust or revocation checks.

Excerpt (requires `targetCertificate`, `approvedAnchors`, and `store` from valid application config/certificates):

```java
X509CertSelector target = new X509CertSelector();
target.setCertificate(targetCertificate);

PKIXBuilderParameters params =
        new PKIXBuilderParameters(approvedAnchors, target);
params.addCertStore(store);

CertPathBuilder builder = CertPathBuilder.getInstance("PKIX");
PKIXCertPathBuilderResult result =
        (PKIXCertPathBuilderResult) builder.build(params);
CertPath path = result.getCertPath();
```

**This is a fragment, not a standalone runnable Java file.** It deliberately does not “auto-trust discovered certificates”. `PKIXCertPathBuilderResult` also carries the trust anchor, public key, and policy tree; a complete flow must verify target identity per application requirements (e.g., TLS hostname) at the appropriate layer.

### 7.2. Validating an Existing Path with `PKIXParameters`

If the application already has a `CertPath`, use `CertPathValidator` with `PKIXParameters`:

```java
PKIXParameters params = new PKIXParameters(approvedAnchors);
params.addCertStore(store);
// Configure appropriate date/policy/revocation before validating.
CertPathValidator validator = CertPathValidator.getInstance("PKIX");
CertPathValidatorResult result = validator.validate(path, params);
```

This is also a fragment, assuming `approvedAnchors` and `path` are already properly provided. Do not set `params.setRevocationEnabled(false)` just to “avoid needing a CRL”. When revocation sources are unavailable, decide according to an evaluated fail-closed/soft-fail policy rather than skipping checks arbitrarily.

### 7.3. What Does `addCertStore` Mean?

`params.addCertStore(store)` registers a repository that the PKIX implementation **may use** to look up intermediates or CRLs during building/validation. It does **not**:

- Run the builder/validator automatically;
- Eagerly download all certificates/CRLs from the repository;
- Create trust anchors;
- Force every discovered CRL to be accepted;
- Guarantee providers query repository types in the same way or order across every JDK.

You must actually call `build(...)`/`validate(...)` and inspect results/errors per policy.

## 8. CertStore Sources: `Collection`, `LDAP`, and Remote Repositories

### 8.1. `Collection` — In-Memory Source

`Collection` is very useful when:

- Intermediate certificates or CRLs were already downloaded through a separate controlled channel;
- You want repeatable test fixtures without networking;
- Supplying specific certificates/CRLs to a PKIX builder/validator;
- You already hold data parsed from PEM, DER, or a bundle file per application trust policy.

`CollectionCertStoreParameters` takes a collection; the application must manage data sources, concurrency, size, lifecycle, and integrity if the dataset can change. A `CertStore` holding items in memory **grants those items no trusted status**.

### 8.2. `LDAP` — External Repository

Java provides `LDAPCertStoreParameters` to configure hostname and port; syntax example:

```java
// API illustration; no real connection is made in this lesson.
LDAPCertStoreParameters ldapParameters =
        new LDAPCertStoreParameters("ldap.example.internal", 389);

CertStore ldapStore =
        CertStore.getInstance("LDAP", ldapParameters);

X509CertSelector subjectSelector = new X509CertSelector();
subjectSelector.setSubject(
        new X500Principal("CN=Intermediate CA,O=Example"));
Collection<? extends Certificate> matches =
        ldapStore.getCertificates(subjectSelector);
```

This is an illustrative fragment and **cannot run without an appropriate LDAP server**. The hostname is example data; do not send requests to this host during the lesson.

Key points to keep in mind:

- The LDAP provider may need a sufficiently specific **Subject DN, Issuer DN, or issuer info** to locate the target DN/entry. `getCertificates(null)` or an empty selector may be unsupported and lead to `CertStoreException`.
- For CRLs, use `X509CRLSelector` with issuer and `setCertificateChecking` when appropriate so the provider has hints on which CA to query.
- LDAP repositories must have data and schemas compatible with the provider; not every LDAP/Active Directory setup exposes the exact expected certificate/CRL attributes.
- Port 389 in the example merely illustrates API configuration; **it does not imply an encrypted or authenticated connection**. For real use, design LDAP connection protection, TLS/certificates, authentication, credential storage, and anti-spoofing per provider/infrastructure.
- Network failures, timeouts, authentication failures, and malformed directory data are distinct states requiring policy handling—never silently treat them as “not revoked”.

### 8.3. Are AIA and CRL Distribution Points Fetched Automatically?

X.509 certificates may contain:

- **AIA — Authority Information Access:** may indicate where to find the issuer certificate or OCSP service, depending on the extension.
- **CRL Distribution Points (CDP):** may indicate where to fetch the relevant CRL.

**Do not assume** that creating a `CertStore("Collection")` or reading a certificate with AIA/CDP makes Java automatically connect to those URLs. Automatic AIA/CDP/OCSP retrieval depends on the **PKIX provider, runtime configuration, and protocol policy**. Some JDKs have specific properties/provider behavior; do not rely on them as a portable `CertStore` contract.

If an application downloads certificates/CRLs itself from URIs inside extensions, treat those URIs as **untrusted**: enforce domain/protocol allowlists, size/time/redirect caps, protections against SSRF, DNS rebinding, internal networks/metadata endpoints, loops, and cache poisoning. After downloading, still parse and PKIX-validate as usual.

### 8.4. Caching and Freshness

CRLs have `thisUpdate/nextUpdate`; a cache holding a CRL past `nextUpdate` can cause incorrect revocation decisions. Distinguish **HTTP cache TTL, LDAP provider cache**, and **CRL validity/freshness**. “Cached data exists” does not mean “data is still valid”.

If the app builds a `Collection` from its own cached data, the app must ensure proper cache invalidation and rotation. If the LDAP provider maintains an internal cache, its timing/configuration depends on the JDK/provider; never treat cache TTL as a substitute for PKIX revocation validation.

## 9. CRL, OCSP, and `PKIXRevocationChecker` Verification Policy

### 9.1. How CRL and OCSP Differ

- **CRL:** a revocation list issued by a CA/CRL signer, which may be stored/cached and distributed via LDAP/HTTP.
- **OCSP:** a mechanism for querying a certificate's status (typically by serial/issuer) from an OCSP responder, with signed responses and distinct metadata.
- PKIX systems may use one or both per policy. `CertStore.getCRLs` is **not** an OCSP API. Java uses `PKIXRevocationChecker`/provider to control revocation checking in PKIX.

### 9.2. `PKIXRevocationChecker`

From a `PKIX` `CertPathBuilder` or `CertPathValidator`, you can obtain a checker supporting revocation:

```java
CertPathValidator validator = CertPathValidator.getInstance("PKIX");
PKIXRevocationChecker checker =
        (PKIXRevocationChecker) validator.getRevocationChecker();

// Example: prefer CRLs. Evaluate policy/fallback before using.
checker.setOptions(EnumSet.of(
        PKIXRevocationChecker.Option.PREFER_CRLS));

params.addCertPathChecker(checker);
CertPathValidatorResult result = validator.validate(path, params);
```

The **fragment** above assumes `params` and `path` already exist with valid trust anchors and CertStores. Depending on the implementation, when an explicit checker is attached, revocation behavior is governed by the checker and its interaction with `setRevocationEnabled` must be understood per the API. Never attach a checker without evaluating its policy impact.

Common options:

| Option | Meaning | Risks/notes |
| --- | --- | --- |
| `PREFER_CRLS` | Prefers CRLs over OCSP per provider behavior | Preference only; does not guarantee an appropriate CRL is always available |
| `NO_FALLBACK` | Does not try the alternate mechanism if the preferred one fails | Can increase failures when a source is unreachable; suitability depends on policy |
| `SOFT_FAIL` | Under specified revocation-source unreachability/failure conditions, allows validation to proceed | **Can accept a certificate while revocation status is unknown**; use only if your threat model allows it |
| `ONLY_END_ENTITY` | Checks revocation only for the end-entity per option semantics | Unsuitable if policy requires checking intermediates |

Do not enable `SOFT_FAIL` to “handle all certificate errors”. It is **not** a switch to ignore invalid signatures, expiration, untrusted chains, or certificates already known to be revoked. Cases lacking revocation data must **fail closed** where environment policy requires it.

### 9.3. When Must “CRL Not Found” Block Access?

A financial system or internal mTLS service with strict revocation policy may require **rejection** if revocation status cannot be determined. Another system may adopt a softer policy to prioritize availability. This is an **explicit security design decision**, backed by monitoring and auditing, not a hidden fallback inside `catch (CertStoreException e) { return true; }`.

You must distinguish:

```text
Certificate explicitly revoked         => REJECT
CRL signature invalid / scope invalid  => REJECT candidate; status unresolved
No current CRL or OCSP status           => UNKNOWN; handle by policy
Validated status good/not revoked      => Continue chain & identity checks
CertPath invalid for another reason    => REJECT
```

A certificate “absent from a fetched CRL” is not automatically `GOOD` if the CRL is unverified, out of scope, or stale.

## 10. Errors, Resource Limits, and Source Data Protection

### 10.1. Java Error Diagnosis Table

| Symptom | Likely cause | Resolution |
| --- | --- | --- |
| `CertStore.getInstance("LDAP",...)` throws `NoSuchAlgorithmException` | Unsupported type/provider | Check provider/JDK and approved algorithm list |
| `InvalidAlgorithmParameterException` when creating store | Wrong parameter type/schema | Use `CollectionCertStoreParameters` or `LDAPCertStoreParameters` of the right type |
| `getCertificates(...)` returns empty | No match or repository cannot find by criteria | Inspect selector, subject/issuer, and data source; do not auto-trust |
| `getCRLs(...)` returns empty | No CRL matching issuer/time/scope, or data missing | Check `nextUpdate`, issuer, policy, CRL/OCSP sources |
| `CertStoreException` during query | Repository/provider/network error or selector too broad | Log non-secret details, classify status as UNKNOWN |
| `CertificateException` / `CRLException` when parsing | Corrupted PEM/DER data or wrong type | Check encoding and source, fail safely |
| `crl.verify(...)` fails | Invalid signature, mismatched key, or unsupported algorithm | Do not use CRL as revocation evidence |
| `CertPathBuilderException` | No valid chain found under trust/policy | Inspect trust anchors, intermediates, and constraints; do not skip validation |
| `CertPathValidatorException` | Path violates PKIX constraints | Fail safely, inspect cause/reason and policy |
| Different results across providers | Differing support for type/query/cache/schema | Verify provider contracts and test interoperability |

### 10.2. Input Validation

Certificates/CRLs can arrive from the network or third-party files. Before parsing:

- Bound file/response sizes, item counts, redirects, timeouts, and retry counts.
- Never pass URLs from AIA/CDP directly into a fetcher with access to metadata services or internal networks.
- Use appropriate TLS/LDAP channels and authenticate distribution sources when policy requires; still **verify certificate/CRL signatures**.
- Never let an attacker arbitrarily control `provider`, LDAP host/port, file paths, or trust anchors.
- Use exact Java `X509Certificate`/`X509CRL` types, restrict parsed formats, and avoid unbounded object creation in caches.
- Ensure thread safety for source collections if updated concurrently; never assume a mutable backing collection can be modified safely while providers read it.
- Log sufficient diagnostic fields such as issuer, serial, CRL number, timestamps, and correlation IDs per policy; avoid logging full certificates/CRLs if they contain personal data or increase data exposure.

### 10.3. Preventing Downgrades and Bypasses

Never rewrite logic into:

```java
try {
    return store.getCRLs(selector).isEmpty(); // WRONG
} catch (CertStoreException problem) {
    return true; // WRONG
}
```

An empty query **does not prove** a certificate is good, and an exception proves it even less. Answering “trust this certificate?” must go through a **PKIX validator/revocation checker** with an explicit policy. Never degrade from CRL checking to “check nothing at all” when LDAP temporarily errors.

## 11. Applied Scenarios

### 11.1. Server Sends a Chain Missing an Intermediate Certificate

A TLS server sends a leaf without its intermediate. A Java client may fail certification path building. You may fetch the intermediate through a policy-permitted source and supply that candidate in a `Collection CertStore` or repository available to the path builder.

**Never** add an arbitrary discovered intermediate as a trust anchor just to make the chain pass. The builder must find a validly signed path to an **already-trusted root**.

### 11.2. Internal System Issuing User Certificates

An enterprise CA publishes CRLs via a directory. `LDAP CertStore` helps fetch candidate CRLs for the right issuer. Yet to decide whether a certificate remains valid for mTLS, the validator must check the signature, issuer/key usage, scope, CRL freshness, and revocation status. If the directory is unreachable, apply the appropriate UNKNOWN policy rather than letting it pass automatically.

### 11.3. Offline PKIX Testing Without Network Dependencies

CI can maintain dedicated certificate/CRL test fixtures parsed with `CertificateFactory` and placed into `CertStore("Collection")`. This keeps selector and path-builder tests stable when network conditions vary.

To specifically test “certificate revoked” logic, you need a CA + leaf fixture with a known serial and a **CRL containing that leaf serial** along with valid signing evidence. The demo in Section 6 intentionally **does not** claim to test full revocation workflows; it focuses on **collection via CertStore**.

### 11.4. Refreshing CRLs in a Cache

A CRL approaching `nextUpdate` must be refreshed before being used for new decisions. Cache failures must return an explicit status rather than retaining a “stale yet still secure” CRL. Track issuer, CRL number, `thisUpdate/nextUpdate`, and source; no secret keys need storing because CRLs are **signed public data**.

### 11.5. Multiple Collection Sources

A PKIX builder can be given **multiple CertStores**, such as a Collection containing an available certificate chain plus an LDAP repository for locating intermediates or CRLs. Every source may contain untrusted candidates; **the anchor of truth remains trust anchors and validation policy**, not the number of sources.

## 12. Common Mistakes and How to Fix Them

| Misconception | Consequence | Correct approach |
| --- | --- | --- |
| “`CertStore` is like a truststore.” | Trusts unverified collected certificates | CertStore is only a repository; trust anchors are configured separately |
| “`getCertificates` returning one result means it's trusted.” | Skips chain/signature/identity checks | Use `CertPathBuilder/Validator` with PKIX |
| “A returned CRL means the certificate is revoked.” | Fails to check serial/issuer/scope | Check revocation for the specific certificate and validation policy |
| “`crl.isRevoked(cert)==false` means the certificate is safe.” | Could be using a forged/stale/out-of-scope CRL | Verify CRL, chain, dates, scope, and PKIX status |
| “`setCertificateChecking(cert)` checks revocation immediately.” | No revocation decision is made | It is a hint to locate CRLs; use the PKIX revocation checker |
| “Setting `setIssuer` is enough to verify the CRL signature.” | Matching Issuer DN does not guarantee the right key | Verify signer and chain/authorization |
| “A CRL lacking `nextUpdate` still matches by date.” | Selector may return 0 | Understand `setDateAndTime` requires a complete time window |
| “LDAP queries don't need a selector.” | Provider may not know which DN to look up | Supply appropriate subject/issuer/`certificateChecking` |
| “Collection returning empty = LDAP failed.” | Conflates distinct states | Distinguish empty collection from `CertStoreException` |
| “Put discovered certificates into `TrustAnchor` to fix errors.” | Attackers can install rogue CAs | Trust anchors come only from separate trusted configuration |
| “`getCRLs(null)` scans the whole Internet.” | The API is not a crawler and LDAP has limits | Query against configured selectors/repositories |
| “AIA/CDP are always auto-fetched by Java.” | Application misses intermediates/CRLs | Check provider/config and explicit retrieval policy |
| “Fetching a CRL over HTTP is safe enough.” | Could receive tampered data | Verify signature/issuer/scope and network policy |
| “If LDAP errors, allow through for availability.” | Uncontrolled revocation bypass | Fail closed or soft-fail per approved policy |
| “Only use CRLs, ignore OCSP.” | Misses revocation sources that may be required | Choose CRL/OCSP strategy per PKIX and policy |
| “`setCertificateValid(now)` is the entire verification.” | Missing chain, revocation, hostname, EKU | Only filters validity; follow with PKIX and identity checks |

## 13. CertStore Design Review Checklist

1. **Purpose:** do you need intermediate certificates, CRLs, or both? Is repository search separated from trust decisions?
2. **Sources:** are Collection/LDAP/providers compatible, and are data sources and access permissions controlled?
3. **Selectors:** do Subject/Issuer, serial/CA/validity or CRL issuer/date/scope match requirements; is `setCertificateChecking` understood as a hint only?
4. **Errors:** are empty matches, parsing errors, repository exceptions, and revocation status UNKNOWN handled distinctly?
5. **Trust:** are trust anchors provisioned separately, never auto-promoting candidates into trusted roots?
6. **PKIX:** is `CertStore` supplied to `PKIXParameters`/`PKIXBuilderParameters`, and is the proper validator/builder actually invoked?
7. **CRLs:** are signature, issuer, `thisUpdate/nextUpdate`, `cRLSign`, delta/IDP/scope (when applicable), and algorithm policy checked?
8. **Revocation:** is the CRL/OCSP/fallback/soft-fail policy documented and tested? Does an unknown status follow policy?
9. **Identity:** does a TLS application verify hostname and certificate usage purpose at the proper layer, not just the chain?
10. **Network:** are timeouts, redirects, sizes, SSRF/AIA/CDP risks, cache expiry, and access permissions bounded?
11. **Testing:** do fixtures cover valid/expired/wrong issuer/bad signature/truncated file/revoked leaf/LDAP unavailable?
12. **Operations:** are there safe logs, freshness/cache monitoring, CA/CRL rotation, rollback, and auditing?

## 14. Self-Check Exercises

**Question 1.** `CertStore.getCertificates(selector)` returns a certificate with the right `Subject DN`. Is this certificate guaranteed to be trusted?  
**Answer:** **No.** The selector only finds candidates; PKIX chain/trust anchor and identity validation must still run.

**Question 2.** When using `CollectionCertStoreParameters`, can both `X509Certificate` and `X509CRL` be placed in the same collection?  
**Answer:** **Yes.** `CertStore("Collection")` uses `getCertificates` for certificates and `getCRLs` for matching CRLs.

**Question 3.** A CRL has the right issuer, yet `nextUpdate` has passed. Will `setDateAndTime(new Date())` normally return that CRL?  
**Answer:** **No.** The CRL must cover the requested time according to `thisUpdate ≤ date < nextUpdate`.

**Question 4.** Does `setCertificateChecking(cert)` on `X509CRLSelector` mean “immediately check if cert is revoked”?  
**Answer:** **No.** It is a hint for the repository when searching for CRLs; revocation validation must still run.

**Question 5.** `getCRLs` returns an empty collection. Can the certificate be considered good?  
**Answer:** **No.** No matching CRL means **missing applicable revocation data**, not a GOOD status.

**Question 6.** Is a successful `crl.verify(key)` result enough to trust that CRL?  
**Answer:** **Not enough.** You must know the key belongs to a signer authorized to issue CRLs per trust chain/policy, and check validity time and scope.

**Question 7.** To find the intermediate that signed the leaf, do you filter with `setSubject(leaf.getIssuerX500Principal())` or `setIssuer(leaf.getIssuerX500Principal())`?  
**Answer:** Usually start with **`setSubject`** to find certificates whose subject matches the leaf's Issuer DN; then verify the signature and PKIX path.

**Question 8.** Does `CertStore("LDAP")` automatically download CRLs from every CDP URL in a certificate?  
**Answer:** **Do not assume so.** LDAP stores query per configuration/provider; AIA/CDP retrieval has separate mechanisms and network security requirements.

**Question 9.** A developer calls `params.addCertStore(store)` and immediately accepts the certificate. Is that sufficient?  
**Answer:** **Not yet.** `addCertStore` only registers the source; you must still `build`/`validate` with trust anchors, revocation, and other checks.

**Question 10.** When a repository throws `CertStoreException`, should you return `true` to skip CRL checking?  
**Answer:** **Never arbitrarily.** Record an UNKNOWN status and follow an approved fail-closed/soft-fail policy.

**Question 11.** Does `SOFT_FAIL` in `PKIXRevocationChecker` mean all invalid certificate signatures are ignored?  
**Answer:** **No.** The option applies only to specified failures where revocation status cannot be determined; it never permits accepting chains with other security errors.

**Question 12.** Why shouldn't you import a CA just found in CertStore into the truststore to fix “unable to find valid certification path”?  
**Answer:** Doing so turns **untrusted data** into a **trust anchor**; an attacker could exploit that to establish a rogue CA. Trust anchor provenance/provisioning must be verified under formal policy.

### References

- [Oracle Java 21 — Java PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/21/security/java-pki-programmers-guide.html): `CertStore` model, selectors, PKIX builder/validator, and LDAP sources.
- [Java SE 21 — CertStore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertStore.html): `getInstance`, `getCertificates`, `getCRLs`, and error contract.
- [Java SE 21 — CollectionCertStoreParameters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CollectionCertStoreParameters.html): collection source.
- [Java SE 21 — X509CertSelector](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/X509CertSelector.html): subject, issuer, validity, and BasicConstraints.
- [Java SE 21 — X509CRLSelector](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/X509CRLSelector.html): issuer, time, `setCertificateChecking`.
- [Java SE 21 — PKIXRevocationChecker](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/PKIXRevocationChecker.html): CRL/OCSP and policy.
- [RFC 5280 — Internet X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): certificate/CRL structure, scope, trust path, and revocation semantics.

### Key Takeaway

**`CertStore` is used to find certificates or CRLs; `X509CertSelector` and `X509CRLSelector` filter candidates; `PKIX` and trust anchors decide whether a certificate or path is accepted.** For CRLs, finding data is not enough: you must check **signature, issuer, validity time, scope, and revocation policy**, and never turn “CRL not found” into “certificate valid” without an explicit security policy.
