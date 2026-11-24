# 14.3. Configuring `PKIXParameters`, `PKIXBuilderParameters`, and `X509CertSelector` in Java 21

A seemingly reasonable certificate chain — a leaf signed by an intermediate CA, and the intermediate signed by a root CA — is **not enough** for an application to trust that the certificate belongs to the right party. The application must choose **trust anchors** from its own trusted source, discover or receive a **certificate path**, verify signatures and **PKIX** constraints, validity period, basic constraints, key usage, policies, and revocation status where applicable. In addition, the protocol must verify the **target identity**, such as the hostname in HTTPS.

Java provides distinct building blocks: `X509CertSelector` specifies the target certificate to locate; `PKIXBuilderParameters` configures **discovering and building a path** to a trust anchor; and `PKIXParameters` holds the parameters for **validating an existing path**. They work together with `CertPathBuilder`, `CertPathValidator`, `CertStore`, and `TrustAnchor`.

This lesson belongs to section **“14. Trust Paths”** of Java Advanced – Security & Cryptography. The primary goal is configuring `PKIXParameters`, `PKIXBuilderParameters`, and `X509CertSelector` **in their proper roles**, understanding each parameter's effect, practicing Java 21 with a root → intermediate → leaf chain, and testing an untrusted CA case.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish *certificate path building*, *path validation*, and *application identity verification*; explain why verifying each certificate's signature does not by itself establish trust.
2. Use `TrustAnchor` from a trusted CA **configured outside the untrusted certificate chain**, understanding `KeyStore` or `Set<TrustAnchor>` sources.
3. Construct `X509CertSelector` with a specific leaf, subject, `basicConstraints`, and `extendedKeyUsage`; understand that a selector is only a **target certificate filter**, not a replacement for full path validation.
4. Configure `PKIXBuilderParameters`, add a `CertStore` containing candidate certificates, set `setMaxPathLength` and `setDate`/`setRevocationEnabled` per policy; invoke `CertPathBuilder.getInstance("PKIX")`.
5. Use `PKIXParameters` with `CertPathValidator.getInstance("PKIX")` to validate a built `CertPath`, verifying the root returned in the result.
6. Run a complete Java 21 program and explain the output **path entries = 2**, **root omitted**, **trusted root validated**, and **untrusted root rejected**.
7. Avoid pitfalls such as trusting a root sent by an attacker, disabling revocation in production without evaluation, skipping hostname/SAN checks, confusing a candidate `CertStore` with a truststore, and hand-rolling TLS certificate verification.

## 1. The Trust Path Model: Three Roles in One Chain

Suppose a system needs to validate a certificate for `service.example.test`. Example chain:

```text
             Trust anchor: Lab Root CA
        (independently configured as trusted)
                         |
                         | signs, CA:TRUE, pathLen:1
                         v
             Lab Intermediate CA
                 CA:TRUE, pathLen:0
                         |
                         | signs, issuer CA:TRUE
                         v
    Leaf: CN=service.example.test
      SAN: DNS:service.example.test
      EKU: serverAuth
      BasicConstraints: CA:FALSE
```

Under standard PKIX usage:

- **Leaf (end-entity certificate):** the target certificate to evaluate; carries the service's public key, SAN, EKU, and extensions.
- **Intermediate CA:** intermediate CA certificate used to build the path; it must satisfy certificate-signing conditions, basic constraints, path length, validity, and signature/policy constraints.
- **Trust anchor/root:** a public key or certificate that **the application/truststore has decided to trust**. It is the logical termination point of the chain, not something inferred simply because a certificate is “self-signed”.

A PKIX `CertPath` is ordered **target → intermediates**. **The trust anchor is normally excluded from `CertPath.getCertificates()`**; it is supplied separately via parameters and returned in the build/validate result. In a lab with one intermediate, the number of certificates **in the path is 2**, even though the logical diagram shows 3 certificates including the root.

### 1.1 Three Different Questions

| Step | Question to answer | Java API |
| --- | --- | --- |
| **Target selection** | Which end-entity certificate satisfies the selector (subject, EKU, key usage...)? | `X509CertSelector` |
| **Path building** | Can a chain target → intermediate CA(s) → configured trust anchor be constructed? | `PKIXBuilderParameters` + `CertPathBuilder` |
| **Path validation** | Is an existing chain valid under PKIX, trust anchor, and validation date/policy? | `PKIXParameters` + `CertPathValidator` |
| **Identity/authorization** | Does the valid certificate actually belong to the expected hostname/entity/service and is it authorized for this action? | TLS/JSSE hostname verifier, application policy |

**Note:** Under PKIX, `CertPathBuilder` both discovers the path and performs/requires path validity under the parameters. Calling `CertPathValidator` afterward in the example is an **educational illustration step**, not always mandatory after every successful `CertPathBuilder` call. Do not infer from that that the builder “does not validate anything”.

## 2. `PKIXParameters`: Policy for Validating an Existing Path

`java.security.cert.PKIXParameters` is a parameter class for PKIX algorithms, especially `CertPathValidator`. You can construct it from:

```java
Set<TrustAnchor> anchors = Set.of(new TrustAnchor(rootCertificate, null));
PKIXParameters parameters = new PKIXParameters(anchors);
```

This is an **in-scope illustration** assuming a `rootCertificate` variable of type `X509Certificate`; the full runnable program is in the hands-on section.

### 2.1 The Most Important Prerequisite: TrustAnchor from the Right Source

`TrustAnchor` represents a CA/public key that the application **has decided to trust**. It can be constructed from a CA's `X509Certificate` or CA name/public key via the corresponding constructor. *A trust anchor does not gain trustworthiness merely because a Java object was instantiated.*

**Dangerously wrong:** taking the last certificate in a chain sent by an unauthenticated server and writing `new TrustAnchor(peerRoot, null)`. That lets an attacker generate their own root, sign their own leaf, and pass PKIX validation because the application just “self-trusted” the forged root.

**Correct:** trust anchors come from a protected truststore/configuration, a managed CA, pinning, or a trusted out-of-band distribution process. In the lab, the root PEM file represents an **intentionally pre-provisioned trust anchor** to simulate this configuration—it does not mean any arbitrary root PEM file should be accepted.

You can also create `PKIXParameters` from a loaded `KeyStore` when the truststore contains `TrustedCertificateEntry` items:

```java
PKIXParameters parameters = new PKIXParameters(trustStore);
```

The `KeyStore` constructor uses only trusted X.509 certificate entries as trusted CAs, rather than implicitly treating every `PrivateKeyEntry` as a trust anchor. Manage the truststore file separately, controlling CA imports and updates. `new PKIXParameters(Set.of(...))` also requires a non-empty set and valid elements.

### 2.2 Important Configuration Options

| API | Meaning | Guidance |
| --- | --- | --- |
| `getTrustAnchors()` / `setTrustAnchors(...)` | Trusted CAs/public keys | Keep source and update permissions explicit; never take arbitrarily from peers |
| `setDate(Date)` | Point in time used when checking certificates | Use controlled clock/policy; if unspecified, typically defaults to current time |
| `setRevocationEnabled(boolean)` | Whether to perform revocation checking per provider/config capabilities | **Do not disable in production just so the lab runs easily** |
| `addCertStore(CertStore)` | Source of candidate certificates/CRLs for finding/checking paths | Containing candidates **does not imply trust** |
| `setInitialPolicies(Set<String>)` | Initial set of certificate-policy OIDs of interest | Configure only after understanding PKIX policies and domain requirements |
| `setExplicitPolicyRequired(boolean)` | Requires an explicit policy | Can invalidate a path if a required policy is not satisfied |
| `setPolicyMappingInhibited(boolean)` | Controls policy mapping | Part of standardized certificate policy control |
| `setAnyPolicyInhibited(boolean)` | Controls the role of `anyPolicy` | Avoid guessing; follow a concrete profile |
| `addCertPathChecker(PKIXCertPathChecker)` | Custom PKIX checker on the path | Use only when there is a specified and tested requirement |
| `setSigProvider(String)` | Provider used for signature verification when needed | Letting JCA choose by default is usually right; HSM/FIPS policies may differ |

A common mistake is setting `setRevocationEnabled(false)` to “get rid of OCSP/CRL errors” and shipping it to production. The lab **intentionally disables it** because the self-created CAs publish no CRL/OCSP; this is purely to avoid network dependencies in exercises, not a security recommendation.

### 2.3 Do Not Confuse Certificate Validity with Trust Policy

`setDate(...)` affects `NotBefore/NotAfter` validity checking of the certificates under inspection. Using a past timestamp to verify historical signature archives requires proper time, timestamping, and revocation policies; **never** arbitrarily roll back the clock to “make an expired cert valid”. Properties such as certificate policies, name constraints, algorithm constraints, and trust anchors still matter.

A root designated as a **trust anchor** is typically not processed like an ordinary certificate in the path. The organization must govern trust anchors directly regarding provenance, lifecycle, algorithm/key strength, and safe rotation.

## 3. `X509CertSelector`: How to Describe the Target Certificate

`X509CertSelector` implements the `CertSelector` interface and checks whether a certificate meets criteria (`match(Certificate)`). During PKIX building, it is passed to `PKIXBuilderParameters` as `targetConstraints`.

Example in the upcoming program:

```java
X509CertSelector target = new X509CertSelector();
target.setCertificate(leaf);
target.setSubject(leaf.getSubjectX500Principal());
target.setBasicConstraints(-2);
target.setExtendedKeyUsage(Set.of("1.3.6.1.5.5.7.3.1"));
```

Meaning:

- `setCertificate(leaf)` requires the target to be that exact certificate. Suitable when the application already received/holds the leaf and wants to build a path for it; **not** necessarily used when searching among multiple certificates by attributes.
- `setSubject(X500Principal)` constrains the subject distinguished name. In the snippet above it is extra illustration because the exact certificate was already set with `setCertificate`.
- `setBasicConstraints(-2)` means accept only **end-entity certificates**, rejecting CA certificates. In this API, `-1` imposes no basic constraints check, while values **0 or greater** require a CA certificate with the corresponding path length.
- `setExtendedKeyUsage(Set<String>)` takes **OID** strings; `1.3.6.1.5.5.7.3.1` is `id-kp-serverAuth`. If a certificate has an incompatible EKU, the selector will not pick it. Do not confuse the display name `serverAuth` with the API/OID string.
- There are also `setKeyUsage(boolean[])`, `setSubjectAlternativeNames(...)`, `setIssuer(...)`, `setSerialNumber(...)`, `setCertificateValid(...)`, and other specialized selectors—know their exact contract and combination behavior before using them.

**Each constraint set on a selector is normally an additional requirement**, not an “if any one condition passes, that is enough” rule. For example, matching subject names does not prove a cert is trusted; an attacker can put `CN=service.example.test` into a self-signed certificate.

### 3.1 Selector Is Not Hostname Verification

Selecting a certificate with `subject == X` or `EKU == serverAuth` does not verify **which hostname you are connecting to**—whether `api.example.test` or `service.example.test`. HTTPS requires verifying identity from SANs and protocol rules; a TLS JSSE client should be configured with **endpoint identification/hostname verification** per profile. A certificate chain can be PKIX-valid yet issued for a **different domain**. Application policy may also independently require tenant, purpose, and authorization checks.

`X509CertSelector.setSubjectAlternativeNames(...)` is a useful **filter** during selection, but does not replace full standard TLS hostname verification (wildcards, DNS/IP, internationalized names, SAN types, and endpoint context). Avoid writing custom hostname verifiers when a standard TLS stack is available.

### 3.2 Selector Does Not Equal PKIX Validation

`selector.match(cert) == true` only confirms conformance to **the configured filter criteria**. Issuer signatures, CA path length, trust anchor, CRL/OCSP, and other PKIX policies must be checked by the builder/validator. Never build a selector with one matching criterion and treat the certificate as trusted.

## 4. `PKIXBuilderParameters`: From Target to Trusted Root

`PKIXBuilderParameters` **extends** `PKIXParameters` and adds constraints so the path builder can select the target, search issuer certificates, and stop at a trust anchor.

Initialization:

```java
Set<TrustAnchor> anchors =
        Set.of(new TrustAnchor(root, null));
PKIXBuilderParameters builderParams =
        new PKIXBuilderParameters(anchors, target);
```

Here `root` is a certificate obtained from a valid trust repository, and `target` is the configured `X509CertSelector`. An instance can also be created from a `KeyStore` plus a `CertSelector`. The builder has a default path length limit; the lab sets it explicitly to demonstrate policy.

### 4.1 Using `CertStore` as the Intermediate Certificate Source

The builder needs to find certificates that can link the leaf to a trust anchor. In the lab, no HTTP or LDAP calls are required:

```java
CertStore candidates = CertStore.getInstance(
        "Collection",
        new CollectionCertStoreParameters(
                List.of(leaf, intermediate)));
builderParams.addCertStore(candidates);
```

`CollectionCertStoreParameters` takes an in-memory collection of certificates/CRLs, useful for labs and many already-received data flows. **CertStore is only a candidate source, not a trust source!** You can add peer-sent certificates to `CertStore` for the builder to discover paths, as long as trust anchors come from an independent source. Adding a self-signed CA to the collection does not make it trusted.

Besides Collection, providers may offer other certificate/CRL sources; selection and issuer-fetching behavior via AIA/network should not rely on guesswork. In real systems, explicitly design how issuers and CRLs/OCSP are fetched, caching, timeouts, offline behavior, and network access permissions.

### 4.2 `setMaxPathLength` Limits Intermediates

Lab code:

```java
builderParams.setMaxPathLength(1);
```

In `PKIXBuilderParameters`, this parameter limits the **number of non-self-issued intermediate CA certificates** in the path—it is not simply `chain.length` and does not count the leaf or root trust anchor as though they were intermediates.

- `0`: disallows ordinary intermediates; the path must have only an end-entity certificate under the trust anchor where possible.
- `1`: allows one intermediate, such as `Lab Intermediate CA` in the fixture.
- `-1`: imposes no limit from this property; does **not** bypass CA certificate basic constraints.
- Less than `-1`: invalid.

A CA's `BasicConstraints.pathLenConstraint` extension also imposes its own constraint and can be stricter than builder policy. For instance, the lab root allows one intermediate, and the intermediate allows **0 subordinate CAs below it**. Thus you cannot arbitrarily add another CA just because the builder allows a larger path length.

### 4.3 What Algorithm Does the Builder Run?

```java
PKIXCertPathBuilderResult result =
    (PKIXCertPathBuilderResult)
        CertPathBuilder.getInstance("PKIX").build(builderParams);
```

The result holds the selected `CertPath`, the `TrustAnchor` used, and the associated policy tree/public key. If no valid chain is found, the builder throws `CertPathBuilderException` (which may carry a provider-specific cause). Failure can occur because the target is absent, an intermediate is missing, the trust anchor is wrong, a cert is expired, constraints fail, revocation is unavailable, or policy mismatches; never conclude “wrong password” or “wrong public key” from a generic message alone.

**A successful build does not mean the hostname matches or the user is authorized.** It is strictly PKIX verification against the supplied parameter set.

## 5. Practice: Creating Root CA → Intermediate → Leaf with `keytool`

We create a **single lab file** `lab.p12` containing CA and service private keys **solely to issue test certificates**. Then we export **four public certificates** to PEM so Java can build PKIX paths; the Java program **does not read private keys**. This keeps the focus squarely on trust path construction and validation.

> Never co-locate CA signing private keys in the same file as service keys in production. A real PKI requires CA key isolation (HSM/offline or appropriate policy), role separation, certificate issuance auditing, revocation, and protected backups.

### 5.1 Prepare Directory and Lab Password

Use an **empty directory** with JDK 21 `keytool` and `javac` on your PATH. Two ways to set the environment variable:

PowerShell (Windows):

```powershell
$env:PKIX_DEMO_PASS = 'LabOnly-TrustChain42'
```

Bash (Linux/macOS):

```bash
export PKIX_DEMO_PASS='LabOnly-TrustChain42'
```

The string above is **for the lab only**. `-storepass:env PKIX_DEMO_PASS` reads the password from an environment variable instead of putting the value directly on the command line; this is not a production secret management system.

Verify:

```text
java -version
javac -version
keytool -help
```

### 5.2 Create a Self-Signed Root CA

```text
keytool -genkeypair -alias lab-root -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=Lab Root CA,O=Training,C=VN" -ext "BC:critical=ca:true,pathlen:1" -ext "KU:critical=keyCertSign,cRLSign" -validity 60 -keystore lab.p12 -storetype PKCS12 -storepass:env PKIX_DEMO_PASS -keypass:env PKIX_DEMO_PASS -noprompt
```

The Root CA has `BasicConstraints CA:TRUE`, `pathLen:1`, and `keyCertSign`. A self-signed root certificate **is not inherently trustworthy**: it becomes the lab's trust anchor only because we **explicitly pre-provision** it in code.

### 5.3 Create an Intermediate Signed by the Root

```text
keytool -genkeypair -alias lab-intermediate -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=Lab Intermediate CA,O=Training,C=VN" -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign" -signer lab-root -signerkeypass:env PKIX_DEMO_PASS -validity 45 -keystore lab.p12 -storetype PKCS12 -storepass:env PKIX_DEMO_PASS -keypass:env PKIX_DEMO_PASS -noprompt
```

`-signer lab-root` uses the private key at the root alias to sign the intermediate, creating the chain for alias `lab-intermediate`. The `pathlen:0` extension prevents this intermediate from acting as a parent CA for **another intermediate CA**, while still permitting end-entity certificate issuance per policy.

### 5.4 Create a Service Certificate (Leaf) Signed by the Intermediate

```text
keytool -genkeypair -alias lab-service -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=service.example.test,O=Training,C=VN" -ext "BC:critical=ca:false" -ext "KU:critical=digitalSignature,keyEncipherment" -ext "EKU=serverAuth" -ext "SAN=dns:service.example.test" -signer lab-intermediate -signerkeypass:env PKIX_DEMO_PASS -validity 20 -keystore lab.p12 -storetype PKCS12 -storepass:env PKIX_DEMO_PASS -keypass:env PKIX_DEMO_PASS -noprompt
```

The leaf has `BasicConstraints CA:FALSE`, EKU `serverAuth`, and DNS SAN `service.example.test`. This is a lab certificate, **not for use as a production TLS certificate**, and browsers will not trust it because the self-signed root CA is not in their truststores.

Inside `lab.p12`, `lab-service` can show chain length **3**: leaf + intermediate + root. Yet when Java builds a path using root as the `TrustAnchor`, the resulting `CertPath` contains only leaf + intermediate.

### 5.5 Create an Untrusted Root to Test Failure

```text
keytool -genkeypair -alias lab-untrusted -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=Untrusted Root,O=Training,C=VN" -ext "BC:critical=ca:true,pathlen:1" -ext "KU:critical=keyCertSign,cRLSign" -validity 50 -keystore lab.p12 -storetype PKCS12 -storepass:env PKIX_DEMO_PASS -keypass:env PKIX_DEMO_PASS -noprompt
```

`lab-untrusted` is a separate CA that signed neither the leaf nor the intermediate above. When replacing the trusted root with this certificate, the builder **must fail** even though the leaf and intermediate have valid internal signatures.

### 5.6 Export PEM Certificates for Java

Run four commands, exporting only **public certificates**, never private keys:

```text
keytool -exportcert -rfc -alias lab-root -keystore lab.p12 -storetype PKCS12 -storepass:env PKIX_DEMO_PASS -file lab-root.pem
keytool -exportcert -rfc -alias lab-intermediate -keystore lab.p12 -storetype PKCS12 -storepass:env PKIX_DEMO_PASS -file lab-intermediate.pem
keytool -exportcert -rfc -alias lab-service -keystore lab.p12 -storetype PKCS12 -storepass:env PKIX_DEMO_PASS -file lab-service.pem
keytool -exportcert -rfc -alias lab-untrusted -keystore lab.p12 -storetype PKCS12 -storepass:env PKIX_DEMO_PASS -file lab-untrusted.pem
```

Inspect the service alias:

```text
keytool -list -v -alias lab-service -keystore lab.p12 -storetype PKCS12 -storepass:env PKIX_DEMO_PASS
```

Expected structural lines:

```text
Alias name: lab-service
Entry type: PrivateKeyEntry
Certificate chain length: 3
Owner: CN=service.example.test, O=Training, C=VN
Issuer: CN=Lab Intermediate CA, O=Training, C=VN
...
Owner: CN=Lab Intermediate CA, O=Training, C=VN
Issuer: CN=Lab Root CA, O=Training, C=VN
...
Owner: CN=Lab Root CA, O=Training, C=VN
Issuer: CN=Lab Root CA, O=Training, C=VN
```

`keytool -list` displays the **chain stored in the KeyStore**, not the `CertPath` that the validator later receives. The two concepts have related ordering yet **different endpoints**.

## 6. Java 21: Builder + Validator + Selector, Including Wrong-CA Check

Create **`PkixPathDemo.java`** in the same directory as the four `*.pem` files. The program uses no private keys and needs no dependencies outside the JDK.

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertPathBuilder;
import java.security.cert.CertPathBuilderException;
import java.security.cert.CertPathValidator;
import java.security.cert.CertStore;
import java.security.cert.CollectionCertStoreParameters;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXBuilderParameters;
import java.security.cert.PKIXCertPathBuilderResult;
import java.security.cert.PKIXCertPathValidatorResult;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509CertSelector;
import java.security.cert.X509Certificate;
import java.util.List;
import java.util.Set;

public final class PkixPathDemo {
    static X509Certificate read(Path directory, String name) throws Exception {
        CertificateFactory cf = CertificateFactory.getInstance("X.509");
        try (InputStream in = Files.newInputStream(directory.resolve(name))) {
            return (X509Certificate) cf.generateCertificate(in);
        }
    }

    public static void main(String[] args) throws Exception {
        Path directory = Path.of(args.length == 1 ? args[0] : ".");
        X509Certificate root = read(directory, "lab-root.pem");
        X509Certificate intermediate = read(directory, "lab-intermediate.pem");
        X509Certificate leaf = read(directory, "lab-service.pem");
        X509Certificate otherRoot = read(directory, "lab-untrusted.pem");

        // Policy: trust is provisioned from outside the untrusted chain.
        Set<TrustAnchor> anchors = Set.of(new TrustAnchor(root, null));
        X509CertSelector target = new X509CertSelector();
        target.setCertificate(leaf);
        target.setSubject(leaf.getSubjectX500Principal());
        target.setBasicConstraints(-2); // End-entity, not a CA.
        target.setExtendedKeyUsage(Set.of("1.3.6.1.5.5.7.3.1")); // serverAuth

        CertStore issuerCandidates = CertStore.getInstance("Collection",
                new CollectionCertStoreParameters(List.of(leaf, intermediate)));
        PKIXBuilderParameters buildParams =
                new PKIXBuilderParameters(anchors, target);
        buildParams.addCertStore(issuerCandidates);
        buildParams.setMaxPathLength(1);
        buildParams.setRevocationEnabled(false); // Lab only!

        PKIXCertPathBuilderResult path =
                (PKIXCertPathBuilderResult) CertPathBuilder
                        .getInstance("PKIX").build(buildParams);
        System.out.println("path entries: " +
                path.getCertPath().getCertificates().size());
        System.out.println("root omitted from path: " +
                !path.getCertPath().getCertificates().contains(root));
        System.out.println("path starts at leaf: " +
                path.getCertPath().getCertificates().get(0).equals(leaf));

        PKIXParameters validationParams = new PKIXParameters(anchors);
        validationParams.setRevocationEnabled(false); // Lab only!
        PKIXCertPathValidatorResult verified =
                (PKIXCertPathValidatorResult) CertPathValidator
                        .getInstance("PKIX").validate(
                                path.getCertPath(), validationParams);
        System.out.println("validated with trusted root: " +
                verified.getTrustAnchor().getTrustedCert().equals(root));

        PKIXBuilderParameters wrongAnchors =
                new PKIXBuilderParameters(
                        Set.of(new TrustAnchor(otherRoot, null)), target);
        wrongAnchors.setRevocationEnabled(false); // Lab only!
        wrongAnchors.addCertStore(issuerCandidates);
        boolean rejected = false;
        try {
            CertPathBuilder.getInstance("PKIX").build(wrongAnchors);
        } catch (CertPathBuilderException expected) {
            rejected = true;
        }
        System.out.println("untrusted root rejected: " + rejected);
    }
}
```

### 6.1 Compile and Run

When `lab-root.pem`, `lab-intermediate.pem`, `lab-service.pem`, and `lab-untrusted.pem` are in the current directory:

```text
javac --release 21 -encoding UTF-8 PkixPathDemo.java
java PkixPathDemo .
```

Stdout from the generated fixture:

```text
path entries: 2
root omitted from path: true
path starts at leaf: true
validated with trusted root: true
untrusted root rejected: true
```

This output has been tested with a compiler supporting `--release 21` and a standard JDK PKIX provider. Key generation uses `SecureRandom` and `keytool`, so certificate bytes and fingerprints differ across runs, whereas the **booleans and path length** above remain consistent if the fixture and policy are kept intact.

### 6.2 Step-by-Step, Line-by-Line Output Explanation

1. `CertificateFactory.getInstance("X.509")` parses PEM certificates. **Being able to parse a certificate does not mean the certificate is verified.** Never import an attacker-supplied root as a trust anchor.
2. `new TrustAnchor(root, null)` declares the root trusted **under the lab's pre-provisioned trust assumption**. The `null` argument is optional name constraints on the trust anchor (not a password or key).
3. `X509CertSelector` selects the exact leaf, requiring end-entity and `serverAuth` EKU; this is the **target constraint** for the path builder.
4. `CollectionCertStoreParameters(List.of(leaf, intermediate))` supplies certificates **for path discovery**, without elevating trust. The root does not need to be in `CertStore` because it is passed separately in `anchors`.
5. `buildParams.setMaxPathLength(1)` permits one intermediate CA. The CA's `BC.pathLen` extension is also checked under PKIX.
6. `build(...)` returns `PKIXCertPathBuilderResult`, where `getCertPath().getCertificates()` has **leaf first, intermediate second**. Because the root is a trust anchor outside the path, `path entries: 2` and `root omitted from path: true`.
7. `new PKIXParameters(anchors)` and `validate(path, params)` verify the **already-built cert path**, without discovering a new path. `verified.getTrustAnchor()` points to the accepted root.
8. Replacing the trust anchors with `otherRoot`—which has no issuing relationship to the leaf/intermediate—causes the builder to fail to find a valid path. The program catches `CertPathBuilderException` and prints `untrusted root rejected: true`.
9. `setRevocationEnabled(false)` appears in both build and validate **solely so the offline lab produces reproducible results**. For real systems, establish a revocation policy and CRL/OCSP sources matching your profile; do not copy this setting without security analysis.

### 6.3 A Potential Point of Confusion: Root PEM Next to Leaf PEM

In the demo, we save all four PEM files in the same directory for convenience. **Being physically in the same directory does not make the root trusted**; the code intentionally designates `lab-root.pem` as the trust anchor assuming that root was provisioned securely prior to receiving any message. If an attacker controlled the directory and replaced both `lab-root.pem` and `lab-service.pem` simultaneously, the demo could accept the attacker's new chain. Production needs a write-protected truststore/configuration store, root governance/pinning policy, and proper filesystem paths.

Do not store CA private keys in a store that the validation application has read access to. The Java demo takes only public PEM certificates; `lab.p12` is only for generating the certificates and should be deleted after the lab.

## 7. Testing Failures: Knowing Which Layer Failed

A real PKIX program encounters many failures beyond a simple “bad signature”.

| Change in the lab | What you should observe | Explanation |
| --- | --- | --- |
| Supply only `otherRoot` as trust anchor | `CertPathBuilderException` | No chain from leaf to a trusted root |
| Remove intermediate from `CertStore` (no other source) | Typically fails to build | Missing issuer certificate to chain up to root |
| Keep root, swap leaf for another certificate | Possible selector mismatch or different path | Target constraints identify the desired certificate |
| Set `setMaxPathLength(0)` when one intermediate is needed | Builder rejects the path | Policy disallows the required intermediate CA |
| Use a leaf cert expired at validation date | `CertPathValidatorException` or builder failure | Date window is no longer valid |
| Intermediate lacks `CA:TRUE` / `keyCertSign` | Invalid path | BasicConstraints/KeyUsage disallow signing certificates |
| Intermediate has `pathLen:0` yet another CA is placed below it | Invalid path | Exceeds issuer's CA path length |
| Wrong EKU in selector | Target cannot be selected | Target selector does not match |
| No CRL/OCSP service yet revocation is enabled | May fail because status cannot be verified | Must configure policy/sources, not disable arbitrarily |
| PKIX passes yet URL hostname differs from SAN | PKIX may pass, **TLS identity check must reject** | Path trust is distinct from endpoint identity |
| Valid root CA yet app policy rejects client type | PKIX may pass, application must reject | Chain validation does not equal authorization |

Systematic troubleshooting steps:

1. **Parsing:** verify correct DER/PEM format, whether certificates parse cleanly, and whether the path has duplicate/missing elements.
2. **Target selector:** use `match(...)`/inspect constraints to see whether the leaf satisfies the criteria.
3. **Candidates:** is the intermediate supplied/retrievable in `CertStore`, and do issuer subject/key identifiers match?
4. **Trust anchors:** does the root come from a **trusted administrative source** or from the peer? Is it a root permitted by the system?
5. **PKIX constraints:** validity date, CA basic constraints, signature algorithm, key size/algorithm constraints, policies, name constraints, revocation.
6. **Identity/application:** hostname/SAN, EKU/service role, authorization, pinning if used.
7. **Operations:** JDK/provider and crypto policy, network access, timeouts, clock skew, CRL/OCSP cache.

**Do not return full diagnostic certificate chains, CA names, or stack traces over a public HTTP API.** Emit structured internal logs at an appropriate sensitivity level, return a safe validation error to clients, and never fall back automatically to “accept all” when validation fails.

## 8. Constructors and APIs That Are Easy to Confuse

### 8.1 `PKIXParameters` from `Set<TrustAnchor>` vs `KeyStore`

From a set:

```java
PKIXParameters validationParams =
        new PKIXParameters(Set.of(new TrustAnchor(root, null)));
```

From a loaded truststore (illustrative snippet; `trustStore` must contain `TrustedCertificateEntry` entries):

```java
PKIXParameters validationParams = new PKIXParameters(trustStore);
```

Both construct trust anchor policies. **Do not** pass an identity keystore holding service private keys and assume the constructor will treat every private-key alias's certificate chain as trusted roots.

### 8.2 `PKIXBuilderParameters` Requires a Target

```java
PKIXBuilderParameters buildParams =
        new PKIXBuilderParameters(anchors, target);
```

This constructor requires appropriate target constraints. With an empty selector and a broad candidate pool, the builder may select an unintended target; the application must specify **who/which cert needs proving**. With the `KeyStore` constructor, trust anchors likewise come from trusted entries as described above.

### 8.3 `X509CertSelector` Only Filters Certificates

```java
X509CertSelector selector = new X509CertSelector();
selector.setSubject(leaf.getSubjectX500Principal());
selector.setBasicConstraints(-2);
boolean matches = selector.match(leaf);
```

This snippet is **not standalone**: it requires an already-loaded `leaf` variable. `matches == true` only confirms the leaf matches the selector; a self-signed certificate with the same subject can also match if the selector does not pin the key/certificate. Only PKIX path + trust policy decides whether a certificate lies on a trusted path.

### 8.4 Existing `CertPath` vs `CertPathBuilder`

When a peer sends a complete chain, you can construct a `CertPath` using `CertificateFactory.generateCertPath(List<? extends Certificate>)` in the proper order, then invoke `CertPathValidator` with `PKIXParameters`. When no complete chain is available, `CertPathBuilder` combines the candidate `CertStore` and trust anchors to **discover** a suitable path.

Do not place the root into the path and expect the element count to always match the logical diagram. The PKIX contract keeps the trust anchor **separate from the cert path**, and the builder demo demonstrates this clearly.

## 9. Strengthening PKIX Policy Beyond the Lab

### 9.1 Trust Anchor Governance

Manage trust anchors as critical security assets: who can add/remove CAs, how truststores are updated, auditing, key strength, lifetimes, revocation/compromise response, environment-specific policies (test/staging/prod), and rollover. **A trusted CA can usually sign many leaf certificates** within its name constraints/policies, so granting root trust has broad blast radius.

If an application only needs to trust one specific service, consider pinning with proper management/rotation procedures, or a private PKI with explicit name constraints and issuance policy. Never extract a root from an external handshake and turn it into a trust anchor.

### 9.2 Revocation, CRL, and OCSP

PKIX path validation commonly applies revocation checking. `PKIXParameters.setRevocationEnabled(true)` is an important flag, yet **it does not guarantee** everything will work if CRL/OCSP providers/networking are not configured. You may need a `PKIXRevocationChecker` from the validator/provider or official trust manager, a `CertStore` containing CRLs, an OCSP responder, caching, timeouts, and a **hard-fail/soft-fail** policy aligned with your threat model. Never treat a cert as “good” merely because an API call succeeded without an actual revocation status source.

Enabling/disabling revocation is a system decision, not an exception-handling trick. If studying offline, mark it explicitly as “LAB ONLY” as in the code. When deploying, inspect how the JSSE stack uses CRL/OCSP and related system/security properties for your exact JDK version.

### 9.3 Application Identity and Usage Purpose

Even a trusted path must be bound to its intended target:

- **HTTPS:** DNS/IP SAN must match the hostname; check protocol version and `serverAuth` EKU per policy.
- **Mutual TLS:** verify the client certificate against an appropriate trust policy, then map certificate identity to a principal/tenant and authorize the request.
- **Code signing:** key usage/EKU/signing policy differs from TLS; do not treat a leaf with only `serverAuth` as an authorized code signer.
- **Document signing:** must know the expected signer/organization, timestamping policy, and signing evidence; path validation alone still does not establish business authority.

In real Java applications, let **JSSE/HTTPS** perform standard TLS verification via `SSLContext`, `TrustManagerFactory`, a `PKIX` trust manager, and proper hostname verification; never swap in an “accept any certificate” TrustManager or check CN manually.

### 9.4 Algorithm Constraints and Clocks

RSA-3072/SHA-256 signatures in the lab were chosen for JDK 21 compatibility and educational clarity. Real systems must enforce profile algorithm constraints, update when algorithms/keys become weak, handle expired/not-yet-valid certificates, and synchronize clocks. Do not try to “fix” failures by accepting arbitrary signatures or disabling certificate validity checks.

`setDate` should be used purposefully (e.g., point-in-time testing or standardized historical signature verification profiles); never roll the date backward arbitrarily just to pass an expired certificate.

### 9.5 A PKIX Path Builder Is Not a Complete Trust Protocol

`CertPathBuilder` and `CertPathValidator` handle their PKIX responsibilities properly, yet they do not by themselves handle TLS channel security, proof of possession of the private key during handshake, application-level replay protection, authorization, business payloads, or idempotency. The layers must work together:

```text
Truststore / managed CA roots
              |
              v
X509CertSelector + CertStore candidates
              |
              v
PKIXBuilderParameters ----> CertPathBuilder("PKIX")
              |                        |
              |                        v
              |                 path + trust anchor
              |                        |
              v                        v
 PKIXParameters ------------> CertPathValidator("PKIX")
                                       |
                                       v
               Hostname/SAN + EKU + endpoint/application policy
                                       |
                                       v
                       Authenticated channel / authorization
```

In a typical HTTPS client, these steps are orchestrated by the framework and JSSE stack on the application's behalf; you do not need to call `CertPathBuilder` manually on every request. Still, understanding these three classes helps when auditing **CA selection, truststore configuration, and certificate-chain failures** and avoiding trust-bypass vulnerabilities.

## 10. Common Mistakes to Remember

1. **“Having three certificates in the chain is enough for trust.”** False: a complete chain whose root is not in a protected truststore could be self-signed by an attacker.
2. **“Take the root from the peer's bundle and call `new TrustAnchor(root,null)`.”** False: that lets an attacker manufacture a trusted root.
3. **“`CertStore` is a truststore.”** False: `CertStore` is a source of candidate certificates/CRLs; trust anchors are an independent policy.
4. **“`X509CertSelector` returning `true` means PKIX succeeded.”** False: matching does not verify the path, trust, validity, or comprehensive revocation.
5. **“`PKIXParameters` and `PKIXBuilderParameters` are the same.”** False: builder parameters add target and path-length policies for path discovery; validator uses an existing path.
6. **“CertPath contains leaf, intermediate, root.”** Not by default: the trust anchor is passed separately, so the demo path has only leaf and intermediate.
7. **“Lower `setMaxPathLength` to cap the total number of certificates.”** False: it counts **non-self-issued intermediate CAs**, not simply every certificate.
8. **“Just calling `setRevocationEnabled(true)` guarantees OCSP/CRL works.”** False: mechanisms/sources and failure policy must be configured.
9. **“Disabling revocation when offline is safe in production.”** False without a corresponding security decision; disabling in the example is strictly for the lab.
10. **“A certificate signed by a trusted CA definitely belongs to the hostname I am calling.”** False: endpoint identity/SAN verification is required.
11. **“Every certificate with the same subject CN belongs to the same entity.”** False: subjects can be created by multiple CAs or attackers; trust and policy are required.
12. **“If a self-signed root verifies with its own public key, it is trusted.”** False: self-signature validity says nothing about the root's provenance.
13. **“Because the path builder succeeded, the user is authorized to call the API.”** False: application permissions require principal mapping and authorization.
14. **“The lab proves the PKIX provider works on every JDK/HSM.”** False: you must test against your real provider/runtime/policy and CA/CRL/OCSP infrastructure.

## 11. Practice Exercises

1. **Target filtering:** remove `setCertificate(leaf)` and use only subject + EKU + basic constraints. What happens if `CertStore` holds two leaves with the same subject/EKU? What extra constraint would you add, or how would you verify identity?
2. **Missing intermediate:** remove `lab-intermediate.pem` from the `CertStore` collection. With no other issuer source, what does the builder throw? Distinguish a missing issuer error from an untrusted root.
3. **Wrong trust anchor:** change the trusted root to `lab-untrusted.pem`; run the code and explain why the builder fails even though the intermediate's signature on the leaf is still valid.
4. **Path length limit:** change `setMaxPathLength(1)` to `setMaxPathLength(0)`; is the leaf→intermediate→root path allowed? If you had a leaf signed directly by the root, how would the result differ?
5. **Certificate validity:** print `getNotBefore()/getNotAfter()` of the leaf, use `setDate(...)` in a test with a date past `NotAfter`, and verify path status. Do not manipulate production machine clocks to simulate expiration.
6. **EKU:** change the selector from the `serverAuth` OID to the `clientAuth` OID `1.3.6.1.5.5.7.3.2`; why does the lab leaf no longer match?
7. **Subject vs SAN:** build a path successfully for `service.example.test`, then assume an HTTP client connects to `api.example.test`. Does the PKIX builder automatically raise a hostname mismatch error? At which layer do you configure endpoint identification?
8. **Truststore:** design a separate PKCS12 holding only a `TrustedCertificateEntry` for the root, load it with `KeyStore`, and pass it to `new PKIXParameters(trustStore)`. Why is passing a peer-supplied private-key keystore to that constructor wrong?
9. **Revocation:** sketch a configured CRL/OCSP provider workflow for a real system; choose hard-fail or soft-fail per policy, and describe the expected outcome when the responder fails to reply.
10. **Troubleshooting:** a Java container throws `CertPathBuilderException` while a laptop builds the path cleanly. List possible causes involving truststore, certificates/candidates, JDK/provider, clock, revocation/network, and hostname verification without hastily disabling PKIX.
11. **mTLS application:** explain three tasks separately: validating the client certificate path; mapping the certificate to an identity; deciding whether that identity may invoke a sensitive endpoint.
12. **CA certificate:** why is an intermediate with `pathLen:0` still allowed to sign a leaf yet prohibited by policy from creating another subordinate intermediate CA? Distinguish the `pathLenConstraint` extension from `setMaxPathLength`.

**Completion criteria:** you can point out **where the trust anchor comes from**, what constraints select the leaf, which `CertStore` holds the intermediate, how the builder limits the path, what policy the validator applies, how revocation/hostname are checked, and why **a properly constructed path does not mean every application security goal is satisfied**.

## Official Reference Documentation

- [Java SE 21 — `PKIXParameters`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/PKIXParameters.html): configuring trust anchors, validation date, revocation, policies, CertStore.
- [Java SE 21 — `PKIXBuilderParameters`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/PKIXBuilderParameters.html): selector, intermediate CA limit, constructors from truststore/anchors.
- [Java SE 21 — `X509CertSelector`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/X509CertSelector.html): subject/issuer/EKU/basic constraints/key usage/SAN selectors.
- [Java SE 21 — `TrustAnchor`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/TrustAnchor.html): trusted CA and name constraints.
- [Java SE 21 — `CertStore`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertStore.html): certificate/CRL collection; not synonymous with truststore.
- [Java SE 21 — `CertPathBuilder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertPathBuilder.html), [`CertPathValidator`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertPathValidator.html): building and validating paths.
- [Java SE 21 — `CertificateFactory`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertificateFactory.html): parsing X.509 PEM/DER.
- [Java SE 21 — `PKIXRevocationChecker`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/PKIXRevocationChecker.html): provider-based revocation checking support.
- [JDK 21 — `keytool`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html): `-genkeypair -signer`, export certificate, PKCS12, extensions.
- [RFC 5280](https://www.rfc-editor.org/rfc/rfc5280): X.509 PKI certificate and CRL profile, certificate path validation.
- [Java 21 JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): TLS, trust managers, and endpoint identity.
