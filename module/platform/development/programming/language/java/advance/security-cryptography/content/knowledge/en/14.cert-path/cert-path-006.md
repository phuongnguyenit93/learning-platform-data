# 14.6. Revocation with CRL, OCSP, and `PKIXRevocationChecker`

## Objectives and Scope

When verifying an X.509 certificate, seeing a valid CA signature and `notBefore ≤ now ≤ notAfter` is **not enough**: the CA may have revoked the certificate before its expiration date due to private key compromise, misissuance, usage changes, or service decommissioning. This lesson focuses on **revocation checking in PKIX trust paths**, using **CRL**, **OCSP**, and Java 17+'s `java.security.cert.PKIXRevocationChecker` API.

After completing this lesson, you will be able to:

1. Distinguish **expired**, **revoked**, **undetermined status**, and **untrusted certificate path**.
2. Read X.509 CRLs, understanding CRL issuer, serial number, `thisUpdate`, `nextUpdate`, signature, CRL Distribution Points (CDP), and CRL limitations.
3. Understand OCSP `good/revoked/unknown`, responder URLs via AIA, response signature and freshness checks, OCSP stapling, and network risks.
4. Configure `PKIXRevocationChecker` per policy: `PREFER_CRLS`, `NO_FALLBACK`, `ONLY_END_ENTITY`, `SOFT_FAIL`, and CRL sources via `CertStore`.
5. Use `CertPathValidator` to genuinely validate a certificate path against a **clean CRL** and a **revoked-certificate CRL**; avoid confusing a serial lookup in a CRL with full PKIX validation.
6. Choose **fail-closed/hard-fail** vs **soft-fail** error-handling policies transparently, measure timeouts, and test TLS integration.

**Scope limits:** this lesson is about **certificate revocation and PKIX paths**, not CA issuance, full TLS handshakes, or application protocols. Examples use **lab** keys/certificates—never place self-created example CAs into a production truststore. Java code targets JDK 17+; network behavior and system settings may vary across providers/JDKs/applications.

## 1. A “Valid Certificate” Requires Multiple Conditions

A certificate can satisfy a CA's digital signature and still be rejected because:

- It is before `notBefore` or past `notAfter` (validity period).
- No path can be built from the leaf certificate through intermediates to a **trusted trust anchor**.
- CA ordering/basic constraints/key usage, algorithms/key strength, certificate policies, or name constraints fail requirements.
- Hostname/SAN, Extended Key Usage, or usage purpose does not fit the application, especially in TLS.
- It was **revoked by the CA** prior to expiration with valid revocation evidence.
- **Revocation status cannot be determined** because no trusted CRL/OCSP response is available, data is stale, or the responder is unreachable, depending on policy.

Three revocation states to understand clearly:

| Status | Meaning | Must NOT be interpreted as |
| --- | --- | --- |
| **GOOD / not listed as revoked in a valid source** | Per valid revocation evidence for the right issuer/serial/scope at the evaluation time, the cert is not recorded as revoked | “The certificate is completely valid for every purpose” |
| **REVOKED** | An authorized CA/OCSP responder published revocation of the certificate | “Can be ignored due to flaky networking” |
| **UNKNOWN / UNDETERMINED** | Status could not be proven from available data and current policy | “Not revoked” |

**Revocation does not replace other PKIX and application steps.** OCSP `good` only speaks to revocation status per the responder; it does not prove domain/identity, certificate chain, algorithms, or key usage are valid. A CRL without a serial also does not prove a cert is safe if the CRL is forged, from the wrong issuer, expired, or out of scope.

### A Concrete Scenario

A CA issues certificate `serial=0x42` with a 1-year validity. After 1 month the private key is suspected compromised, so the CA revokes `serial=0x42`. Even though the certificate still has 11 months of validity left and the CA's signature hasn't changed, the verifier must reject it when valid revocation evidence exists. If the OCSP server is down, the verifier must **decide the unknown status per policy**, never silently label it GOOD.

## 2. Where Revocation Checking Fits in a PKIX Path

Suppose:

```text
Trusted Root CA (TrustAnchor, selected via trust policy)
    |
    +-- Intermediate CA (cert signed by Root)
             |
             +-- Leaf certificate: api.example.invalid
                    |
                    v
        Check signatures / chain / validity / purpose
                    |
                    v
             Revocation checks
           (leaf and intermediate CAs if policy requires)
                    |
                    v
            ACCEPT or REJECT
```

In Java, `CertPath` normally lists **leaf → intermediate → ...**, **excluding the trust anchor** at the end. The trust anchor is passed separately via `PKIXParameters`/`TrustAnchor`. Never take a root CA directly from a peer-sent chain and add it to trust anchors: a peer can issue a rogue CA. Trust anchor sources must come from trusted configuration/`KeyStore` or trust policy.

**Revocation scope:** usually both leaf and intermediate matter; if an intermediate is revoked, many leaves issued by that CA lose their chain of trust. `ONLY_END_ENTITY` reduces checking on CA certificates, so consider it only when a clear alternative policy/source covers CAs.

**The trust anchor** is normally trusted directly and not processed like an ordinary certificate path element; root CA/trust anchor status must be managed via truststore updates and trust policy. Never assume “PKIX checks all certs” automatically detects every root CA distrusted outside configuration.

## 3. CRL — Certificate Revocation List

A **CRL** (RFC 5280) is a list **signed by a CA or an authorized CRL issuer**, containing serial numbers revoked under a specific scope/distribution point.

Common fields and concepts:

| Field | Practical meaning |
| --- | --- |
| `issuer` | Identity of the CRL's issuer; usually the certificate's issuing CA, though PKIX also supports indirect CRLs |
| `thisUpdate` | Timestamp when the list status took effect / was issued |
| `nextUpdate` | Expected timestamp of the next CRL issuance; used in freshness policies |
| `revokedCertificates` | List of serial numbers of revoked certs, typically with revocation date and reason |
| `signatureAlgorithm / signature` | Proof the CRL content was signed by an authorized key |
| `CRL Number` | Extension helping identify and version CRLs |
| `Authority Key Identifier (AKI)` | Helps identify the key used to sign the CRL when multiple keys/certificates exist |
| `CRL Distribution Points (CDP)` | X.509 extension in a certificate indicating where the CRL can be fetched (HTTP/LDAP...) |
| `Issuing Distribution Point` | Can narrow a CRL's scope, e.g., end-entity certs only or a subset of reasons |
| `delta CRL` | Contains only changes relative to a base CRL; not usable as a standalone full list if policy needs the base |

Example flow:

```text
Leaf certificate -> CRL Distribution Points URI (if present)
                  -> fetch CRL from distribution point
                  -> verify signature and issuer/authorization
                  -> check thisUpdate/nextUpdate and scope
                  -> match serial number and reason
                  -> conclude revocation per PKIX rules
```

Key properties:

- CRLs can be **cached** and used offline once a still-valid copy is obtained. The advantage is avoiding an OCSP connection per check; the drawback is CRL size and update latency—actual revocation may occur after the latest CRL timestamp.
- **Absence of a serial in a CRL is insufficient to conclude safety** if the CRL has the wrong issuer/scope or is stale. A “clean” CRL from another issuer does not make a certificate valid either.
- `X509CRL.isRevoked(cert)`/`getRevokedCertificate(serial)` is a **membership lookup** on a parsed CRL object, not a replacement for `CertPathValidator`: never just call `isRevoked` and skip trust/freshness/signature/chain checks.
- **Never fetch URLs from untrusted certificates arbitrarily:** CDPs in X.509 input can point to internal networks or unintended addresses. Enforce egress/proxy/SSRF controls and appropriate timeouts; behavior depends on the provider.
- CRLs signed by a CA may be partitioned by distribution point, reason, or issuer. Never grab an arbitrary CRL from that CA and assume it covers every certificate.

### Reading a CRL Manually in Java

The snippet below **only illustrates parsing and checking a few isolated properties**, not a standalone validator:

```java
CertificateFactory factory = CertificateFactory.getInstance("X.509");
X509CRL crl;
try (InputStream in = Files.newInputStream(Path.of("issuer.crl"))) {
    crl = (X509CRL) factory.generateCRL(in);
}
System.out.println(crl.getIssuerX500Principal());
System.out.println(crl.getThisUpdate());
System.out.println(crl.getNextUpdate());
System.out.println(crl.getRevokedCertificates());
```

Requires `java.io.InputStream`, `java.nio.file.Files/Path`, and `java.security.cert.CertificateFactory/X509CRL`, plus handling checked exceptions. `getRevokedCertificates()` can return `null` when there are no entries; the data may contain operationally sensitive information, so avoid logging full partner serial lists unnecessarily. **Successful parsing alone does not prove a CRL is trusted**.

If you already hold a genuinely trusted CA certificate, `crl.verify(issuerPublicKey)` checks the CRL signature, yet you must still verify issuer/CRL-signing authority (`cRLSign`), validity dates, scope, and trust path. The PKIX API is responsible for handling this more thoroughly; never stitch together piecemeal checks and label it “validated”.

## 4. OCSP — Online Certificate Status Protocol

**OCSP** (RFC 6960, superseding RFC 2560) is a mechanism for querying a responder about the status of **a specific certificate**, instead of downloading an entire CRL.

An OCSP message typically carries a `CertID` containing issuer identifiers (hashes of issuer name/key) and the certificate's **serial**. The responder returns a signed response containing status, timestamps, and responder identity; the verifier must check **authority to sign OCSP responses**, signature, timestamps, exact cert/issuer association, and other rules.

| Outcome | Content | Interpretation |
| --- | --- | --- |
| `good` | Responder does not report the certificate as revoked per responder data | Does not replace certificate signature/chain/hostname verification |
| `revoked` | Evidence of revocation exists, possibly with revocationTime/reason | **REJECT** when response is valid |
| `unknown` | Responder has no reliable status for the requested CertID | **Never treat as GOOD by default** |
| Response error/timeout | No usable evidence received | Handle as **UNDETERMINED / policy fallback**, never treat as `good` |
| Response has invalid signature / unauthorized signer | No trustworthy evidence | Reject or apply another checking mechanism per policy, **never** treat as `good` |

In a certificate, the **Authority Information Access (AIA)** extension can hold an OCSP responder URL. An application configuration can also specify a fixed responder (such as an internal CA). With `PKIXRevocationChecker.setOcspResponder(URI)`, the configured URI **overrides** the AIA OCSP URL for that checker; use only URLs approved for the specific trust boundary.

**Freshness and replay protection:** check `thisUpdate`, `nextUpdate`, `producedAt`, and allowed clock skew/cache TTL rules. An OCSP nonce is a profile-dependent extension binding request and response, with compatibility and performance trade-offs; never enable nonces blindly without checking responder/stapling/cache support. A stale OCSP response or one for the wrong certificate must not be treated as `good`.

### OCSP Stapling in TLS

Instead of having the client query the responder itself, the TLS server can include a **signed OCSP response** in the handshake (stapling). Benefits can include lower latency, reduced exposure of client browsing to the responder, and server-side caching. However, the client must still **actually verify** the signature, timestamps, cert association, and policy; bytes sent as “stapled” by the server are not trustworthy merely by delivery.

Some certificates carry an extension requiring stapling (TLS Feature, commonly called Must-Staple); support/enforcement varies across clients. **Never assume your Java JSSE stack checks revocation or Must-Staple** without configuring, testing, and verifying the exact implementation.

## 5. Comparing CRL and OCSP in Operations

| Criterion | CRL | OCSP |
| --- | --- | --- |
| Query granularity | List for an issuer/scope | Status of a single certificate (or batch of CertIDs) |
| Updates | Per CRL cycle, possibly with deltas | Per response and cache/responder validity window |
| Data size | Can be large when many certs are revoked | Responses are typically small, though requests are frequent |
| Offline operation | Can use a valid cached trusted CRL | Can use a still-valid cached/stapled response |
| Privacy | Fetching a CRL does not necessarily reveal which cert is checked | Client querying a responder can leak cert/timing; stapling mitigates this |
| Network failures | CRL fetch fails / CRL expired -> unknown | OCSP timeout, `tryLater`, responder unreachable -> unknown |
| Trust conditions | CRL signature/issuer/authorization/scope/timestamps | Response signature/responder authorization/CertID/timestamps |
| Java PKIX | `CertStore` CRLs, CRLDP if supported by provider | `PKIXRevocationChecker`, AIA/responder, OCSP responses |

**Do not choose a single mechanism based on one benchmark.** Define requirements first for freshness, outage handling, CA ecosystem, egress, intermediate certificates, caching, observability, and threat model. A fallback mechanism helps availability, yet only when the **alternate source genuinely validates** status rather than masking errors.

## 6. Java Classes Involved in Revocation Checking

| API | Responsibility |
| --- | --- |
| `CertificateFactory.getInstance("X.509")` | Parses certificates, CRLs, and constructs `CertPath` |
| `X509Certificate` | Represents a certificate, issuer/serial/validity/extensions |
| `X509CRL` | Represents a CRL, issuer, timestamps, entries, standalone signature check |
| `TrustAnchor` | CA/public key chosen by the application as trusted root |
| `CertPath` | Certificate chain in leaf → intermediate order, excluding trust anchor |
| `CertStore` + `CollectionCertStoreParameters` | Supplies CRLs/certificates for discovery and checking |
| `PKIXParameters` | Trust anchors, validation date, CertStore, policies, checkers |
| `PKIXBuilderParameters` | Similar, plus target constraints to **build** a path |
| `CertPathValidator.getInstance("PKIX")` | Validates an existing path per PKIX |
| `CertPathBuilder.getInstance("PKIX")` | **Builds** a path from candidate certificates and trust anchors |
| `PKIXRevocationChecker` | Configures OCSP/CRL preference, fallback, soft-fail, responder, and OCSP responses |
| `CertPathValidatorException` | Reports PKIX failure reason, certificate index, and cause |

Distinguish **builder** and **validator**: `CertPathBuilder` finds a path from a leaf cert to a trust anchor through candidate certificates/`CertStore`; `CertPathValidator` checks an already-supplied `CertPath`. **Both** can use `PKIXRevocationChecker` when added to the appropriate parameters. When an application receives a chain from a TLS handshake, never assume it is a valid path just because the peer sent all certificates.

## 7. `PKIXRevocationChecker`: Configuring It Properly

The checker cannot be instantiated with `new PKIXRevocationChecker()` because it is an **abstract** class. Obtain it from a PKIX engine:

```java
CertPathValidator validator = CertPathValidator.getInstance("PKIX");
PKIXRevocationChecker checker =
        (PKIXRevocationChecker) validator.getRevocationChecker();
```

Standard options:

| Option | Meaning | Warning |
| --- | --- | --- |
| `PREFER_CRLS` | Prefer CRLs over OCSP | Does **not** disable OCSP fallback unless `NO_FALLBACK` is also set |
| `NO_FALLBACK` | Disables the secondary fallback mechanism | Combine with `PREFER_CRLS` to enforce CRL-only without falling back to OCSP |
| `ONLY_END_ENTITY` | Checks revocation only on the leaf certificate | Skips intermediate CA revocation checks; weigh the risk carefully |
| `SOFT_FAIL` | Allows ignoring certain undetermined-status errors from network/OCSP `tryLater`/`internalError` per Javadoc | Does **not** turn `revoked` into `good`; ignoring unknown carries risk |

Per the Java SE 17 API, when using this checker explicitly, **OCSP is preferred by default and CRL is the fallback**; `PREFER_CRLS` swaps the order, and `NO_FALLBACK` disables fallback. This is the contract of the **checker API**; **default revocation driven by system/security properties** in the Oracle/SUN provider has separate legacy configuration covered in Section 11, so never conflate the two configuration paths.

**Set options before adding to parameters.** `PKIXParameters.addCertPathChecker(checker)` clones the checker, so mutating `checker` **after** adding it will not update the already-created parameters. If policy changes, create a fresh checker/parameters for that operation.

### What Does `setRevocationEnabled(false)` Mean?

`PKIXParameters` defaults to `isRevocationEnabled()==true`. Calling `setRevocationEnabled(false)` disables the provider's **default revocation checking mechanism**. However, when you **explicitly add a `PKIXRevocationChecker`** via `addCertPathChecker`, the Javadoc specifies that the checker **is still invoked** regardless of the `RevocationEnabled` flag.

This explains the snippet in the offline demo:

```java
params.setRevocationEnabled(false); // Disables default checker, NOT explicitly added checkers.
params.addCertPathChecker(checker);  // This checker still performs checking.
```

The goal is to avoid duplicate checking paths while explicitly controlling the CRL source and options. **Never copy `setRevocationEnabled(false)` while omitting `addCertPathChecker`**: doing so can accidentally **disable all revocation checking** in that pipeline.

### `SOFT_FAIL` Does Not Equal “Automatically Safe”

Per the Java SE 17 API, `SOFT_FAIL` only ignores certain cases where **CRLs/OCSP cannot be retrieved due to network errors** or an OCSP responder returns `internalError`/`tryLater`. If fallback is permitted, typically both mechanisms must fail under applicable soft-fail conditions before validation proceeds under this option. **Valid `REVOKED` evidence is never ignored.**

`checker.getSoftFailExceptions()` can list exceptions ignored during checking, yet note that the checker is **cloned** when added to `PKIXParameters`; do not assume calling the getter on **the original checker variable** after `validate` reflects the internal instance used by the provider. When accurate telemetry is needed, design logging/instrumentation at the validation layer, test the provider, and verify metrics in a real environment.

For high-assurance authentication, key signing, or sensitive authorization, enforce a **fail-closed** policy when revocation cannot be verified, with bounded timeouts/UX/retries. In availability-sensitive systems, soft-fail may be an accepted risk decision, but must be metered, scoped, and clearly distinguished from known-good status. Never use soft-fail to “fix” a misconfigured CA/CRL.

## 8. Java 17: Network-Free Example Inspecting Checker Configuration

**`RevocationCheckerOptionsDemo.java`** runs immediately on JDK 17+ with a PKIX provider. It only retrieves a checker, sets options and an illustrative `.invalid` responder URI; it **makes no OCSP requests and validates no certificates**.

```java
import java.net.URI;
import java.security.cert.CertPathValidator;
import java.security.cert.PKIXRevocationChecker;
import java.util.EnumSet;

public final class RevocationCheckerOptionsDemo {
    public static void main(String[] args) throws Exception {
        CertPathValidator validator = CertPathValidator.getInstance("PKIX");
        PKIXRevocationChecker checker =
                (PKIXRevocationChecker) validator.getRevocationChecker();

        checker.setOptions(EnumSet.of(
                PKIXRevocationChecker.Option.PREFER_CRLS,
                PKIXRevocationChecker.Option.NO_FALLBACK));
        checker.setOcspResponder(URI.create("https://ocsp.example.invalid"));

        System.out.println("prefersCRL=" + checker.getOptions()
                .contains(PKIXRevocationChecker.Option.PREFER_CRLS));
        System.out.println("fallbackDisabled=" + checker.getOptions()
                .contains(PKIXRevocationChecker.Option.NO_FALLBACK));
        System.out.println("softFailEnabled=" + checker.getOptions()
                .contains(PKIXRevocationChecker.Option.SOFT_FAIL));
        System.out.println("responderConfigured=" +
                (checker.getOcspResponder() != null));
        System.out.println("noNetworkRequestWasSent=true");
    }
}
```

```bash
javac -encoding UTF-8 RevocationCheckerOptionsDemo.java
java RevocationCheckerOptionsDemo
```

**Verified stdout:**

```text
prefersCRL=true
fallbackDisabled=true
softFailEnabled=false
responderConfigured=true
noNetworkRequestWasSent=true
```

Key takeaways:

1. `getRevocationChecker()` must be called on a compatible PKIX validator.
2. `EnumSet.of(PREFER_CRLS, NO_FALLBACK)` selects **CRL-only** for the checker in the example; the OCSP responder URI is set yet **will not be used** when the checker runs CRL-only.
3. `SOFT_FAIL` is **not enabled**: if status cannot be determined, path validation will not treat it as success.
4. Getters only verify configuration—**not security outcomes**: there are no `PKIXParameters`, `CertPath`, trust anchor, CRL, or response here. The `noNetworkRequestWasSent=true` line is an assertion because the code only called setters/getters, not proof that an OCSP endpoint works.
5. `example.invalid` is **not** a real responder; in a `CRL-only` lab demo, no network request is sent to that URI.

## 9. Java 17: Actually Validating a Path with Clean and Revoked CRLs

The second example, **`OfflineCrlValidationDemo.java`**, takes four files **from a lab CA you manage**: `root.pem` (trust anchor), `leaf.pem` (certificate issued by root), `clean.crl` (root-signed CRL not revoking leaf), and `revoked.crl` (root-signed CRL containing leaf's serial).

**Input requirements:** the CA must have `BasicConstraints CA=true` and CRL-signing permission in `KeyUsage` when those constraints apply. The leaf must be signed by the matching root; CRLs must have the right issuer, valid dates, and valid signatures. This is an **offline test fixture**, not a real-world trust system; the test app explicitly chooses `root.pem` as the anchor.

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.*;
import java.util.EnumSet;
import java.util.List;
import java.util.Set;

public final class OfflineCrlValidationDemo {
    private static X509Certificate certificate(String file) throws Exception {
        try (InputStream input = Files.newInputStream(Path.of(file))) {
            return (X509Certificate) CertificateFactory.getInstance("X.509")
                    .generateCertificate(input);
        }
    }

    private static X509CRL crl(String file) throws Exception {
        try (InputStream input = Files.newInputStream(Path.of(file))) {
            return (X509CRL) CertificateFactory.getInstance("X.509")
                    .generateCRL(input);
        }
    }

    private static String evaluate(X509Certificate root, X509Certificate leaf,
            X509CRL list) throws Exception {
        list.verify(root.getPublicKey());

        CertPath chain = CertificateFactory.getInstance("X.509")
                .generateCertPath(List.of(leaf));

        PKIXParameters params = new PKIXParameters(
                Set.of(new TrustAnchor(root, null)));
        params.setRevocationEnabled(false);
        params.addCertStore(CertStore.getInstance("Collection",
                new CollectionCertStoreParameters(List.of(list))));

        CertPathValidator validator = CertPathValidator.getInstance("PKIX");
        PKIXRevocationChecker checker =
                (PKIXRevocationChecker) validator.getRevocationChecker();
        checker.setOptions(EnumSet.of(
                PKIXRevocationChecker.Option.PREFER_CRLS,
                PKIXRevocationChecker.Option.NO_FALLBACK));
        params.addCertPathChecker(checker);

        try {
            validator.validate(chain, params);
            return "ACCEPT";
        } catch (CertPathValidatorException e) {
            if (e.getReason() ==
                    CertPathValidatorException.BasicReason.REVOKED) {
                return "REVOKED";
            }
            if (e.getReason() ==
                    CertPathValidatorException.BasicReason
                            .UNDETERMINED_REVOCATION_STATUS) {
                return "UNKNOWN";
            }
            throw e;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            System.err.println(
                    "Usage: java OfflineCrlValidationDemo root.pem leaf.pem clean.crl revoked.crl");
            return;
        }

        X509Certificate root = certificate(args[0]);
        X509Certificate leaf = certificate(args[1]);
        X509CRL clean = crl(args[2]);
        X509CRL revoked = crl(args[3]);

        System.out.println("issuerMatches=" +
                clean.getIssuerX500Principal()
                        .equals(root.getSubjectX500Principal()));
        System.out.println("cleanListsLeaf=" +
                (clean.getRevokedCertificate(leaf.getSerialNumber()) != null));
        System.out.println("revokedListsLeaf=" +
                (revoked.getRevokedCertificate(leaf.getSerialNumber()) != null));
        System.out.println("cleanPath=" + evaluate(root, leaf, clean));
        System.out.println("revokedPath=" + evaluate(root, leaf, revoked));
    }
}
```

Compile and run once you have **the matching set of four files**:

```bash
javac -encoding UTF-8 OfflineCrlValidationDemo.java
java OfflineCrlValidationDemo root.pem leaf.pem clean.crl revoked.crl
```

**Verified stdout on lab certificates/CRLs generated specifically for this example:**

```text
issuerMatches=true
cleanListsLeaf=false
revokedListsLeaf=true
cleanPath=ACCEPT
revokedPath=REVOKED
```

**Reading the code by verification layer:**

- `CertificateFactory` parses `root.pem`, `leaf.pem`, and the two CRLs from disk. No CA or OCSP connections are opened.
- `crl.getRevokedCertificate(serial)` illustrates **membership**: the clean CRL omits the serial, the revoked CRL includes it. This is purely an observation, not PKIX verification.
- `list.verify(root.getPublicKey())` verifies the CRL signature using the key of the root **selected by the application as its trust anchor**. If the CRL were signed by another unauthorized key, this short example is not a general model for indirect/delegated CRLs; use full PKIX validation for real CAs.
- `CertPath` contains only **leaf**, because **root is a separate `TrustAnchor`** and must not be added to the chain list.
- `CollectionCertStoreParameters(List.of(list))` supplies the parsed CRL to the PKIX validator without depending on connecting to a CDP. `PREFER_CRLS + NO_FALLBACK` ensures the checker uses CRLs rather than OCSP.
- `params.setRevocationEnabled(false)` disables the **default mechanism**, yet `params.addCertPathChecker(checker)` registers the explicit checker which still runs per Java API; both **ACCEPT** and **REVOKED** are genuinely exercised on the PKIX engine.
- `validate` can throw `CertPathValidatorException`. Only two reasons are classified in the example: `REVOKED` and `UNDETERMINED_REVOCATION_STATUS`; errors such as bad certificate signature, constraints, or invalid algorithms are **rethrown**, not disguised as “not revoked”.
- `cleanPath=ACCEPT` means only that **the PKIX path with the lab's trust anchor and parameters passed validation**. It does not prove hostname/TLS identity, access permissions, or that an external real-world CA is trustworthy.

### What If the CRL File Is Invalid?

You may encounter `CRLException`, `SignatureException`, `InvalidKeyException`, or `CertPathValidatorException` depending on the flaw and step. Never catch broad `Exception` and return `ACCEPT`. When a CRL is unusable, ensure you **fail per policy**; never interpret “cannot read CRL” as “clean CRL”.

## 10. Preparing Lab Fixtures to Test CRL Revocation

The offline program needs four files. A self-created test CA can generate `root.pem`, issue `leaf.pem`, produce a clean CRL, and produce a CRL containing the leaf's serial.

**Step A — create the CA and leaf certificate with standard `keytool` commands** (assuming the lab password is safely provided in the `LAB_PASS` environment variable):

```bash
# Generate CA key pair for lab; DO NOT put this CA into a production truststore.
keytool -genkeypair -alias ca -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=Test Root CA" -validity 30 -ext "BC:critical=ca:true" -ext "KU:critical=keyCertSign,cRLSign" -keystore ca.p12 -storetype PKCS12 -storepass:env LAB_PASS -keypass:env LAB_PASS

# Export CA public certificate.
keytool -exportcert -rfc -alias ca -file root.pem -keystore ca.p12 -storetype PKCS12 -storepass:env LAB_PASS

# Generate private key and CSR for the lab leaf certificate.
keytool -genkeypair -alias leaf -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=leaf.example.invalid" -validity 30 -keystore leaf.p12 -storetype PKCS12 -storepass:env LAB_PASS -keypass:env LAB_PASS
keytool -certreq -alias leaf -file leaf.csr -keystore leaf.p12 -storetype PKCS12 -storepass:env LAB_PASS -keypass:env LAB_PASS

# Lab CA signs the CSR and outputs leaf.pem.
keytool -gencert -alias ca -infile leaf.csr -outfile leaf.pem -rfc -validity 30 -ext "KU:critical=digitalSignature" -ext "EKU=serverAuth" -keystore ca.p12 -storetype PKCS12 -storepass:env LAB_PASS -keypass:env LAB_PASS

# Inspect leaf serial and issuer field.
keytool -printcert -file leaf.pem
```

These commands ran successfully in this lesson's lab environment. A generated `leaf.pem` may not satisfy every requirement of a real production CA/TLS profile, such as name/SAN, CRLDP/AIA, certificate policies, and real trust workflows. Because this is an **offline revocation** lesson, `OfflineCrlValidationDemo` performs no hostname check.

**Step B — produce CRLs signed by the lab CA:**

- **Prefer your test CA tool** to issue a fresh CRL with no revoked entries and one containing the leaf's revoked entry, ensuring valid issuer/signature/`thisUpdate`/`nextUpdate`. With an OpenSSL CA, generate CRLs from the test CA config and its revocation database; with an enterprise CA, use its test revocation management function.
- **Option only for JDKs supporting `keytool -gencrl`**: some JDK builds include this subcommand even if not listed in every public man page; verified in our test JDK environment. You can generate `clean.crl` and `revoked.crl` with the lab CA:

```bash
# Only when "keytool -gencrl -help" on your JDK reports support.
keytool -gencrl -alias ca -file clean.crl -keystore ca.p12 -storetype PKCS12 -storepass:env LAB_PASS -keypass:env LAB_PASS

# SERIAL_DEC is the leaf serial in decimal (NOT hex string).
# Replace SERIAL_DEC with the value converted from leaf.pem's Serial number.
keytool -gencrl -alias ca -id SERIAL_DEC:1 -file revoked.crl -keystore ca.p12 -storetype PKCS12 -storepass:env LAB_PASS -keypass:env LAB_PASS
```

`keytool -printcert` typically displays the serial in **hexadecimal** (e.g., `7d52...`), while `-id` in this lab utility accepts a **decimal serial number**. When using a supporting JDK, convert hex to decimal before substituting `SERIAL_DEC`. Example snippet in JShell:

```java
import java.math.BigInteger;
new BigInteger("7d52d72e6d72b894", 16).toString();
// This example prints "9030516797235968148" for the hex serial above.
```

**The serial example above is purely illustrative**; every newly generated certificate has a different serial. `:1` is the revocation reason code in this lab utility. Because `-gencrl` is not in all official `keytool` documentation, **do not rely on this command in production workflows** and never treat it as a CA revocation management system. If your JDK lacks support, use a standard CA tool to issue CRLs.

**Step C — inspect the fixtures:** use `keytool -printcrl -file clean.crl` and `-printcrl -file revoked.crl` to inspect contents, then run the program. Verify the right CA issuer, the leaf's serial in the second CRL, and freshness before use. These files are strictly for testing and must be created/stored in a **dedicated lab directory**; lab passwords are not real credentials.

## 11. Integrating with `PKIXParameters` and CRL/OCSP Data

### Supplying CRLs to the Checker via `CertStore`

A `Collection` `CertStore` is convenient for offline testing (used in Section 9). With multiple CRLs and intermediate certificates, add them to the collection:

```java
CertStore store = CertStore.getInstance(
        "Collection",
        new CollectionCertStoreParameters(
                List.of(intermediateCert, currentCrl)));
params.addCertStore(store);
```

This snippet assumes `intermediateCert`, `currentCrl`, and `params` are already declared with the right types; import `java.security.cert.*` and `java.util.List`. `CertStore` helps PKIX locate certificates/CRLs; it does not make every object added to the collection trusted. PKIX must still verify issuer, signature, constraints, and timestamps per the provider's algorithm.

### Configuring an Explicit OCSP Responder

```java
PKIXRevocationChecker checker =
        (PKIXRevocationChecker)
                CertPathValidator.getInstance("PKIX").getRevocationChecker();

checker.setOcspResponder(URI.create("https://ocsp.example.org"));
checker.setOptions(EnumSet.noneOf(PKIXRevocationChecker.Option.class));
params.addCertPathChecker(checker);
```

This is a **non-standalone** illustrative snippet where `params` is a `PKIXParameters` already holding trust anchors and the chain under validation; `example.org` is a documentation placeholder URL, **not a real service**. With a default checker (without `PREFER_CRLS`), the API prefers OCSP and can fall back to CRL. Real responders must be approved by the CA/protocol; if a delegated responder is needed, use `setOcspResponderCert(X509Certificate)` and trust the responder per applicable RFC/PKIX rules.

You can pass already-received OCSP responses (properly fetched/stapled by the system) into `checker.setOcspResponses(Map<X509Certificate, byte[]>)`. These are **DER-encoded OCSP response bytes keyed by certificate**, not a boolean `good` map. The engine still needs to check signature, responder authority, CertID, and time validity per the implementation. Never fake `good` by putting `"true"` bytes in the map.

**Distinction:** `setOcspResponder(URI)` only selects the endpoint—**it does not assert a request was sent or a response was verified**. Only calling `validator.validate(certPath,params)` performs actual validation (given valid data and configuration).

### Differences Between Explicit Checker and Security Properties

Per Oracle's Java 17 PKI Programmer's Guide for the SUN implementation:

- `PKIXParameters.setRevocationEnabled(true)` enables the provider's **default revocation mechanism** (defaults to true when constructing `PKIXParameters`).
- Some default provider configurations use the `ocsp.enable` security property (in `java.security` or `Security.setProperty`): when revocation is enabled, this can make the default mechanism try OCSP followed by CRL fallback. If the property is off, the default path may use CRLs.
- A `PKIXRevocationChecker` obtained directly from a PKIX validator has **its own contract**: by default it prefers OCSP and falls back to CRL per Javadoc, regardless of how the legacy default mechanism is configured.

Therefore, never claim “OCSP is always enabled across all of Java” or “setting `ocsp.enable=true` makes every TLS client check CRL/OCSP”. **Identify the exact API path and provider**; a framework's trust manager/builder configuration can behave very differently from a manual `CertPathValidator` example.

### CRL Distribution Points and Network Queries

The Oracle PKI Programmer's Guide describes the `com.sun.security.enableCRLDP=true` system property to enable automatic CDP-based CRL fetching in the SUN provider; some configurations leave it off by default for compatibility. When supplying CRLs via `CertStore` with `PREFER_CRLS`, the demo **needs no network**, keeping test results deterministic.

Automatic CDP/OCSP fetching requires evaluating:

- **Network egress** and proxies: responders may be external Internet hosts.
- **Timeouts and retries**: libraries have their own defaults; `com.sun.security.crl.timeout` is an example property documented by Oracle for CRLs, which is provider-specific.
- **SSRF and metadata leakage**: certificates may be peer-supplied, and URLs may be unsafe. Enabling automatic fetches from untrusted certificate URLs requires egress boundaries.
- **Caching and clocks**: cached data is usable only within freshness/clock-skew bounds. Broken NTP clocks can cause valid responses to fail evaluation.
- **Check scope**: leaf cert, intermediates, and chain—not merely the first convenient certificate.

Avoid mutating global `java.security` just for one test if you can configure via a dedicated API. Changing runtime security properties can affect unrelated components and may have no effect if an implementation already cached settings. Test in an isolated process in the lab before planning any production rollout.

## 12. Classifying `CertPathValidatorException` Errors

For a PKIX path configured with revocation, `CertPathValidator.validate(...)` can throw `CertPathValidatorException`. Inspect `getReason()`, `getIndex()`, and `getCause()` instead of printing only the message:

| Reason (example) | Meaning | Application policy |
| --- | --- | --- |
| `BasicReason.REVOKED` | Certificate confirmed revoked | **Reject**; never fall back to success |
| `BasicReason.UNDETERMINED_REVOCATION_STATUS` | Missing evidence to determine revocation status | Reject, or soft-fail **only if policy permits and it is metered** |
| `BasicReason.EXPIRED` | Certificate expired | Reject per current policy; not a “CRL bug” |
| `BasicReason.NOT_YET_VALID` | Certificate not yet within validity window | Reject |
| `BasicReason.INVALID_SIGNATURE` | Certificate/path signature invalid | Reject; never downgrade to soft-fail |
| `BasicReason.ALGORITHM_CONSTRAINED` | Algorithm/key violates security constraints | Reject, fix policy/certificate rather than skipping checks |
| `BasicReason.UNSPECIFIED` or other reason | Other/provider-specific failure | Log safely and investigate |

`getIndex()` is the certificate index in `CertPath` order, not a row in a keystore. `-1` can occur when the failure does not pinpoint a single certificate. Never treat `BasicReason.REVOKED` as the detector for all “invalid” cases; the enum values are distinct.

**Code anti-pattern:**

```java
try {
    validator.validate(path, params);
    return true;
} catch (CertPathValidatorException error) {
    return true; // WRONG: ignores all failures, including REVOKED!
}
```

This snippet illustrates a bug, not recommended code; `validator`, `path`, and `params` are assumed declared. If policy demands fail-closed, an unknown revocation error must prevent acceptance. If soft-fail is approved, permit only the exact policy-accepted failure categories, bound durations/states, and emit telemetry.

## 13. Policy When OCSP or CRL Is Unavailable

### Fail-closed / hard-fail

**Fail-closed** means disallowing operations that require a trusted certificate whenever required revocation status **cannot be determined**. Benefit: prevents an attacker from bypassing checks by blocking the responder. Trade-off: a CA responder/egress outage can cause application downtime.

Mitigations: policy-compliant caching, verified CRL/OCSP fallback, redundant egress, bounded timeouts, capacity planning, liveness/health monitoring, clear error messaging, and recovery runbooks.

### Controlled soft-fail

**Soft-fail** permits proceeding under specific **undetermined** conditions matching an allowlisted set of errors, and only as an accepted risk—never for `REVOKED`. For example, an Internet-facing app might prioritize availability in certain use cases, whereas key-management systems, software release signing, or sensitive internal mTLS may impose stricter rules.

If applying `SOFT_FAIL`:

- Record that **soft-fail occurred** rather than telling operators “OCSP GOOD”.
- Define explicit application scope, endpoints/roles, and policy lifetime.
- Increase alerting for prolonged responder/CRL unavailability.
- Define cache TTL bounds, retries/timeouts, and handling when status flips to `REVOKED`.
- Re-evaluate security implications if an attacker can actively disrupt responder connectivity.

### No Single Configuration Fits Every Protocol

| Context | Decisions to make |
| --- | --- |
| Internal mTLS for admin/production key access | Identity integrity may favor hard-fail; deploy highly available internal revocation distribution |
| Public application TLS client | Balance UX, OCSP availability, responder outage impact, and client/provider behavior |
| Long-term document/software signing | Requires status evidence at **signing time**, timestamping/certification policy, and archiving OCSP/CRL evidence per applicable standards |
| Offline signing verification | Requires pre-collected revocation data and verifying appropriate freshness/validation time |
| Air-gapped systems | Cannot “query OCSP online” at verification time; bundle CRL/OCSP evidence into trust bundles or define an approved exception policy |

Do not hastily make `SOFT_FAIL` the server-wide default just to reduce error logs. If revocation is a non-negotiable security requirement, Unknown must be rejected.

## 14. Integrating in TLS/JSSE: Do Not Confuse Manual PKIX Validation with Handshakes

The examples above invoke `CertPathValidator` directly. They **do not automatically configure** revocation checking for:

- `HttpsURLConnection` / `java.net.http.HttpClient` using the default `SSLContext`.
- Servers accepting mTLS via `SSLServerSocket` or frameworks.
- Applications using a custom `X509TrustManager` or one created via `TrustManagerFactory`.
- HTTP/TLS libraries with their own verifiers or native TLS stacks.

If your application's TLS needs revocation checking, properly configure the **trust manager / PKIXBuilderParameters / CertPath policy** used by the TLS stack, alongside trust anchors, hostname verification, and revocation options. One provider-dependent approach initializes `TrustManagerFactory` with `CertPathTrustManagerParameters` wrapping configured `PKIXBuilderParameters`; verify algorithm/provider support and real behavior before using.

Configuration skeleton (snippet, not standalone runnable):

```java
PKIXBuilderParameters params =
        new PKIXBuilderParameters(trustAnchors, targetSelector);
params.setRevocationEnabled(false);
params.addCertPathChecker(configuredRevocationChecker);

TrustManagerFactory tmf =
        TrustManagerFactory.getInstance("PKIX");
tmf.init(new CertPathTrustManagerParameters(params));
```

`trustAnchors`, `targetSelector`, and `configuredRevocationChecker` must be constructed from **trusted sources and approved policies**; on some providers, you may need specific target constraints or different constructors. Never treat this snippet as the sole recipe for every JSSE implementation. When using `SSLEngine` and a custom trust manager, protocol-level hostname verification/endpoint identification is still required.

**Important:** properties like `ocsp.enable`, `com.sun.security.enableCRLDP`, or `-D...` prove nothing for TLS clients/servers until tested end-to-end with unrevoked certificates, revoked certificates, responder timeouts, and chains missing intermediates. Test using the exact framework and JVM/runtime headed to production.

## 15. Testing and Operating Revocation Checking

### Minimum Test Matrix

| Test | Condition | Expected result under hard-fail |
| --- | --- | --- |
| Happy path CRL | Valid leaf, signed/fresh CRL, serial absent | PKIX validation succeeds |
| Revoked leaf | CA includes leaf serial in valid CRL | `REVOKED` and reject |
| Missing CRL + no OCSP | No source to determine status | Must not accept under hard-fail |
| Expired/stale CRL | `nextUpdate` passed or freshness unmet | Never treat stale data as GOOD evidence |
| Wrong issuer CRL | CRL not signed by authorized issuer | Reject, do not use membership |
| Forged CRL signature | Tampered CRL bytes, invalid signature | Reject or fail validation per provider |
| Valid OCSP `good` | Matching CertID, signature/responder trust, timestamp | Passes **revocation layer**, continues remaining PKIX/TLS checks |
| OCSP `revoked` | Authorized responder reports revoked | Reject even if CRL fallback exists |
| OCSP `unknown` | No reliable status | Never treat unknown as good |
| OCSP network failure | Timeout/`tryLater` | Fall back if permitted and valid alternate source exists; otherwise hard-fail |
| Revoked intermediate cert | Intermediate is in chain | Reject if policy checks CA certs |
| Leaf-only checking | `ONLY_END_ENTITY` | Explicitly document risk of skipping intermediates and test policy |
| Hostname/SAN mismatch | PKIX path may validate | TLS identity verifier must still reject |
| JDK/provider change | Different provider, options/fetch/timeouts | Re-run integration tests |

CRL/OCSP tests must use **lab-environment** data and responders. Never craft/alter public CA CRLs or target production mTLS endpoints as test targets; the goal is reproducing security behavior in an environment you control.

### Useful Telemetry Without Over-Exposing Data

- `algorithm=PKIX`, provider/JDK version, checker/options profile, source type (CRL/OCSP/cache/stapled), check duration, timeouts.
- Failure reason enum, certificate index, CA/trust anchor identifier per policy, responder status (avoid logging sensitive URLs if risky).
- Separate **REVOKED / UNDETERMINED / OTHER_INVALID**. Record fallback counts and accepted soft-fails.
- Track p50/p95/p99 latency and error rates per issuer/responder to detect revocation source outages.
- Restrict logs containing subject/SAN/serial and response bytes to avoid excessive collection of personal data/keys/metadata.

To debug on Oracle/OpenJDK, you can enable **only in controlled environments**:

```bash
java -Djava.security.debug=certpath YourApplication
```

This is an implementation debugging mechanism; logs can be verbose and contain certificate/path details. Never leave it enabled long-term in production without reviewing logging/performance impact and sensitive data exposure.

## 16. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| Calling only `checkValidity()` and concluding certificate is trusted | Ignores chain, trust anchor, revocation, purpose | Use PKIX validation and application-layer verification |
| `getRevokedCertificate(serial)==null` ⇒ immediately GOOD | CRL may be stale, wrong issuer, out of scope, or forged | Validate CRL/path and RFC 5280 rules |
| Creating a trust anchor from a peer-sent root CA | Attackers can self-issue rogue CAs | Trust anchors must come from approved config/truststore |
| Adding root to `CertPath` while also configuring it as trust anchor | Misunderstands path trust boundary | `CertPath` holds leaf/intermediates; anchor is passed separately |
| Calling `setRevocationEnabled(false)` and forgetting a checker | Disables default revocation checking | Attach an explicit checker or keep default mechanism per policy |
| Setting options after `params.addCertPathChecker(checker)` | Parameters clone the checker | Configure everything before adding |
| Using `PREFER_CRLS` and assuming OCSP is never queried | Default fallback still exists | Add `NO_FALLBACK` if CRL-only is required |
| Using `SOFT_FAIL` and expecting REVOKED to be ignored | Violates Java contract | REVOKED still rejects; soft-fail covers bounded undetermined errors |
| Testing only clean CRLs, never revoked CRLs | Does not prove revocation works | Test both clean and revoked CRLs, verifying reason |
| Using a CRL from a different issuer | Does not reflect the cert's status | Match issuer/AKI/CRL scope and verify signature |
| Mixing an OCSP response from another serial/issuer | Status does not apply to the checked cert | Verify CertID, responder authority, and freshness |
| Valid OCSP response signature yet unauthorized responder | Valid signature alone is not enough trust | Verify delegation/EKU, issuer, and policy |
| Treating `unknown` as `good` when OCSP server is down | Attackers can exploit outages | Enforce explicit failure policy with telemetry |
| Enabling CDP fetch with unrestricted egress | SSRF, latency, data leakage risks | Network policy, proxy, timeouts, allowlists as appropriate |
| Assuming manual validator's `PKIXRevocationChecker` covers all JSSE | TLS pipeline may differ | Test the real trust-manager/framework |
| Trusting `getSoftFailExceptions` on the original checker is always the used instance | `PKIXParameters` clones the checker | Use instrumentation/provider-aware diagnostics |
| Skipping intermediate revocation checks | Intermediate CAs can be revoked | Avoid `ONLY_END_ENTITY` unless justified |
| Not preserving revocation evidence for long-term signatures | Today's status differs from historical signing time | Design timestamping/archival validation per appropriate standards |
| Hard-fail without caching or timeouts | CA outage causes widespread downtime | Bounded cache, monitoring, valid fallback, budgets |
| Testing unauthorizedly against real CAs/CRLs | Causes operational risk | Use dedicated fixtures and responders in a lab environment |

## 17. Self-Assessment Exercises

1. **Distinguishing states:** an unexpired cert has its serial in a valid CRL. What must the outcome be? If the CRL cannot be fetched and OCSP times out, how does that differ from `REVOKED`?
2. **Reading CRLs:** identify issuer, `thisUpdate`, `nextUpdate`, revoked serial, and reason on a lab CRL. Why is reading `revokedCertificates` without verifying CRL issuer/signature/freshness insufficient?
3. **Understanding OCSP:** why does `good` differ from “TLS hostname and chain are completely valid”? What conditions must be checked for a delegated responder?
4. **Comparison:** design CRL distribution for an app with millions of offline clients; then propose when OCSP/stapling helps more.
5. **API practice:** run `RevocationCheckerOptionsDemo` and change `PREFER_CRLS` to only `NO_FALLBACK`. Which mechanism becomes preferred? Why does merely setting an OCSP URI not mean a request was sent?
6. **PKIX practice:** in `OfflineCrlValidationDemo`, explain why `root` is the trust anchor, `leaf` is in `CertPath`, and `params.setRevocationEnabled(false)` does not disable the explicit checker.
7. **Revoked test:** generate a CRL containing the leaf serial, verify `revokedListsLeaf=true` and `revokedPath=REVOKED`. If one byte of the CRL is modified, should the outcome be accept or reject?
8. **Policy:** enable `SOFT_FAIL` on a high-assurance mTLS endpoint with strict revocation requirements. Explain the risk and propose an alternate runbook if the responder is unavailable.
9. **Intermediates:** if an intermediate CA is revoked while the leaf is not yet listed, why can `ONLY_END_ENTITY` be dangerous?
10. **SSRF:** a leaf certificate has a CDP URL pointing to a server's internal network address. Design an egress policy and timeout when an app uses CRLDP auto-fetch.
11. **JSSE:** you ran the manual demo, yet the HTTPS client still accepts a revoked cert. What step might be missing? How should you test the trust manager and hostname verification layers?
12. **Archival:** a document was signed 5 years ago, and the signing certificate is now expired. Why does historical signature verification require archived validation time/timestamps and revocation evidence per dedicated standards?
13. **Exception analysis:** distinguish `BasicReason.REVOKED`, `UNDETERMINED_REVOCATION_STATUS`, `INVALID_SIGNATURE`, and `ALGORITHM_CONSTRAINED`. Which cases can never turn into success by retrying OCSP?
14. **Operational review:** define metrics for revoked, unknown, soft-fail, fallback, and per-responder latency rates. Which metrics would trigger a configuration rollback?

**Completion criteria:** you accurately explain **revoked vs unknown**, know CRL/OCSP must be checked using trusted sources and freshness, construct and configure `PKIXRevocationChecker` with the right options, handle paths with the trust anchor outside `CertPath`, test accept/revoked against fixtures, and understand that production TLS stacks require separate integration and verification.

## Official References

- [Java SE 17 — `PKIXRevocationChecker` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXRevocationChecker.html): OCSP/CRL preference, fallback, `setOcspResponder`, and checker methods.
- [Java SE 17 — `PKIXRevocationChecker.Option`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXRevocationChecker.Option.html): `PREFER_CRLS`, `NO_FALLBACK`, `ONLY_END_ENTITY`, `SOFT_FAIL`.
- [Java SE 17 — `PKIXParameters`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXParameters.html): trust anchors, CertStore, revocation enabled, and adding custom checkers.
- [Java SE 17 — `CertPathValidatorException.BasicReason`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidatorException.BasicReason.html): `REVOKED`, `UNDETERMINED_REVOCATION_STATUS`, and other reasons.
- [Oracle Java 17 — PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/17/security/java-pki-programmers-guide.html): PKIX, CertStore, CRL Distribution Points, and SUN provider OCSP properties.
- [Java SE 17 — `X509CRL`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509CRL.html), [`CertificateFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertificateFactory.html), [`CertStore`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertStore.html).
- [RFC 5280 — X.509 Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280), especially path/CRL processing algorithms.
- [RFC 6960 — Online Certificate Status Protocol](https://www.rfc-editor.org/rfc/rfc6960), superseding RFC 2560 and describing OCSP statuses/responses.
- [Java SE 17 — `keytool`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): issuing lab certificates and CRL inspection commands.
