# 14.5 Checking Validity Periods, CA Constraints, Path Length, and Key Usage

When verifying an X.509 certificate, confirming that **each certificate's signature is mathematically valid** is only part of the problem. A certificate path (*certification path*) must also satisfy **constraints on validity periods, CA role, intermediate CA depth, and key/certificate usage purposes**. If these constraints are skipped, an application could trust an expired certificate, allow a user certificate to sign other certificates, or accept an email/code-signing certificate as an HTTPS server certificate.

This lesson focuses on four main layers in **PKIX/X.509**:

1. **Validity period:** `notBefore`, `notAfter`, verification timestamp, and clock consistency.
2. **CA constraints:** the `BasicConstraints` extension, the `cA` bit, and `KeyUsage.keyCertSign` for issuers.
3. **Path length:** `pathLenConstraint` limits the number of **non-self-issued** intermediate CAs allowed to follow a CA, not an arbitrary count of certificates.
4. **Usage purpose:** `KeyUsage`, `ExtendedKeyUsage` (EKU) such as `serverAuth`/`clientAuth`, and separate service identity verification such as DNS Subject Alternative Name (*SAN*).

In Java 17+, `CertificateFactory` constructs certificate/`CertPath` objects, while `CertPathValidator` with the `PKIX` algorithm and `PKIXParameters` performs path validation according to configured parameters. **Never equate PKIX path validation with full HTTPS authentication:** hostname/SAN identity, TLS policy, revocation, and authorization must still be enforced in their proper places.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Read, parse, and check `X509Certificate.getNotBefore()`, `getNotAfter()`, `checkValidity(Date)`, `getBasicConstraints()`, `getKeyUsage()`, and `getExtendedKeyUsage()`.
- Explain the difference between a **leaf certificate**, an **issuing CA**, a **root/trust anchor**, and a **certificate chain**.
- Determine why a leaf must be issued by a CA authorized to sign certificates and why CAs in the path must obey `BasicConstraints`, `KeyUsage`, `pathLenConstraint`, and other limits.
- Correctly compute the meaning of `pathLenConstraint = 0`, distinguish non-self-issued intermediate CAs from end-entity certificates, and understand how trust anchors sit outside the path.
- Know why `serverAuth`, `clientAuth`, `codeSigning`, and `emailProtection` are not interchangeable solely based on the public key algorithm name.
- Build a keytool + Java 17 lab creating a test root CA, signed leaf, and unrelated root; validate PKIX at the current time and in the future.
- Write negative tests for expired, not-yet-valid, missing CA flag, wrong keyCertSign, excessive path depth, wrong EKU, wrong SAN, and untrusted issuer.
- Avoid pitfalls such as ignoring critical extensions or disabling TLS peer/hostname verification just to make a handshake succeed.

## 2. The PKIX Model: Where Does Each Certificate Belong?

An example valid path may look like:

```text
      Trust anchor configured outside the path
      Root CA (already trusted)
             |
             | issues / signs
             v
      Intermediate CA 1 (CA=true, KU=keyCertSign, pathLen >= ... )
             |
             | issues / signs
             v
      Intermediate CA 2 (CA=true, KU=keyCertSign, pathLen >= ... )
             |
             | issues / signs
             v
      HTTPS server leaf certificate
      (CA=false; EKU=serverAuth; SAN matches hostname)
```

In many PKIX implementations, the `CertPath` passed to the validator contains **the leaf followed by intermediates in order**, and **excludes the trust anchor**. The trust anchor is supplied separately in `PKIXParameters`. A trust anchor is trusted not because its self-signature verifies or because it sits in some certificate file, but because of **controlled trust configuration** of the application, OS, or runtime.

### Separating Distinct Steps

| Step | What is verified | Typical Java tool |
| --- | --- | --- |
| Parse certificate | Data has valid X.509 syntax and can be instantiated as an object | `CertificateFactory.generateCertificate` |
| Build path | Find suitable issuers/intermediates leading to a trust anchor | `CertPathBuilder("PKIX")` / `CertStore` sources |
| Validate path | Signatures, validity dates, BasicConstraints, CA usage, path length, policies/name constraints, and configured PKIX rules | `CertPathValidator("PKIX")` + `PKIXParameters` |
| Verify TLS endpoint | Certificate represents the **exact target DNS/IP**, TLS server/client purpose, and handshake policy | JSSE/`X509ExtendedTrustManager`/endpoint identification |
| Revocation & operational policy | OCSP/CRL, distrust, algorithm constraints, truststore updates | PKIX revocation checker/JSSE/security policy |
| Business authorization | Whether the client/user/tenant is permitted to perform the action | Application authz/RBAC/ABAC |

**Do not use** `certificate.verify(issuerPublicKey)` or `certificate.checkValidity()` in isolation to decide “trusted”. Those two APIs check only one specific piece of the problem.

## 3. Time Checks: notBefore and notAfter

Every X.509 certificate has a validity window:

```text
notBefore -------------------------- notAfter
           ^ t_valid
```

At time `t_valid`, the validity window must be evaluated according to PKIX/application rules. A certificate with `t_valid` before `notBefore` is **not yet valid**; after `notAfter` it is **expired**. `X509Certificate.checkValidity(Date date)` throws `CertificateNotYetValidException` or `CertificateExpiredException` when invalid at the specified instant.

A certificate signed with a strong algorithm by a trusted CA must still **not be accepted as a currently valid certificate** if the usage time falls outside the validity window per policy.

### Java APIs and Check Timestamps

The following snippet is **illustrative code inside a method** that already has an `X509Certificate certificate`, not a standalone program:

```java
Date notBefore = certificate.getNotBefore();
Date notAfter  = certificate.getNotAfter();
certificate.checkValidity(new Date());
```

For path validation, `PKIXParameters.setDate(Date)` sets the point in time at which the validator evaluates the validity of certificates in the path:

```java
PKIXParameters params = new PKIXParameters(trustedAnchors);
params.setDate(Date.from(Instant.now()));
CertPathValidator.getInstance("PKIX").validate(certPath, params);
```

This is an illustrative snippet, assuming `trustedAnchors` is a controlled `Set<TrustAnchor>`, `certPath` is properly constructed, and imports/checked exceptions are handled. **Other settings** (especially revocation, policies, and algorithm constraints) must still be designed per the threat model.

### Subtle Time Considerations

1. **Check the whole path, not just the leaf.** Issuing CAs/intermediates in `CertPath` also have validity windows. Treating the root trust anchor as a trusted input **outside the path** can mean some extensions/validity of the root itself are not checked identically to certificates inside the path; govern truststores and remove anchors that are no longer valid or permitted.
2. **Clocks must be trustworthy.** A VM/container with clock skew, broken NTP, wrong timezone assumptions, or a rolled-back clock can reject valid certificates or wrongly accept expired ones. X.509 timestamps are absolute instants, never arbitrarily computed from a user's local time.
3. **Never disable validity checks** just because a certificate expired. Renew/reissue or run an approved migration rather than adding unbounded exceptions in code.
4. **Do not confuse current time with historical validation.** Verifying signatures created in the past, long-term signature validation, or timestamp authorities have their own rules for time evidence and revocation status. Never simply call `setDate` with an old user-supplied date and treat a current certificate as valid.
5. **A revoked certificate may not be expired yet.** `notAfter` does not represent revocation. Conversely, an expired certificate must not be treated as valid just because OCSP reported “good” at another time.
6. **Clock and CA chain updates** must stay synchronized across nodes. One skewed node can report different handshake errors even with the same truststore.

### Illustrative Cases

| Check time | Certificate | Expected outcome |
| --- | --- | --- |
| Before `notBefore` | Not yet valid | Reject |
| Within `notBefore...notAfter` | Valid as to **time** | Can proceed; does not trust the whole chain by itself |
| After `notAfter` | Expired | Reject for live TLS authentication |
| Within window but issuer distrusted | Leaf still unexpired | Reject per trust policy |
| Within window but wrong KU/EKU | Leaf still unexpired | Reject for unpermitted purpose |
| Within window but different SAN hostname | Certificate still unexpired | Reject during TLS endpoint check |

In the lab at the end of this lesson, the leaf is issued with a 90-day validity. Testing at the current time succeeds and testing **120 days later** fails, even though the root is valid for 365 days. This isolates **leaf validity** from the fact that the root is trusted.

## 4. BasicConstraints: Who Is Allowed to Act as a CA?

The `BasicConstraints` extension has two logical parts:

- `cA`: whether this public-key certificate belongs to a CA permitted to issue certificates in the path structure.
- `pathLenConstraint`: if present, limits how many **non-self-issued intermediate CA certificates** may follow in a valid path.

An issuing CA in a certificate path must be evaluated against `BasicConstraints`, have certificate-signing authority, and satisfy applicable constraints. Under modern standard profiles, a CA certificate's `BasicConstraints` should be marked **critical** per RFC 5280. If a critical extension cannot be understood or processed, validation must reject rather than ignore it as decorative metadata.

### Java: getBasicConstraints()

`X509Certificate.getBasicConstraints()` returns:

- **`-1`** if the certificate is **not** a CA per BasicConstraints.
- A value **`>= 0`** if the CA has a finite `pathLenConstraint`, such as 0 or 2.
- A very large integer (e.g., `Integer.MAX_VALUE` per JDK API) when the certificate is a CA with **no published `pathLenConstraint` limit**.

Therefore, **`getBasicConstraints() == 0` does not mean “this is a leaf”**. On the contrary, `0` indicates the certificate **is a CA**, yet allows no non-self-issued intermediate CA below it in the given path (aside from self-issued exceptions per PKIX rules).

Example:

```text
Leaf end entity:   getBasicConstraints() = -1
Intermediate CA:   getBasicConstraints() = 0  (can sign leaves directly)
Intermediate CA:   getBasicConstraints() = 1  (can have 1 non-self-issued CA below)
Unconstrained CA:  getBasicConstraints() = very large per provider/API
```

This describes the common meaning; actual counting follows the PKIX algorithm, including self-issued exceptions and other constraints. Never hand-roll a path validator using a simple integer comparison.

### Checking CA=true Alone Is Not Enough

A CA certificate also needs:

- A signature from an authorized issuer or proper configuration as a trust anchor.
- `KeyUsage` permitting certificate signing when that extension is present.
- Valid validity dates and algorithms.
- Properly enforced `pathLenConstraint`, name constraints, certificate policies, and critical extensions.
- Proper ordering, `issuer/subject` chaining, signature verification, and key usage.

Never accept a user-uploaded `CA=true` certificate and add it as a trust anchor. **Trust is an external policy**, not a self-declared boolean.

## 5. pathLenConstraint: Path Length Is Not an Arbitrary Certificate Count

This is one of the most frequently misunderstood parts of PKIX.

If a CA certificate has `pathLenConstraint=0`, that CA can still sign **end-entity/leaf certificates**. A value of `0` only prohibits **subsequent non-self-issued intermediate CA certificates** below it in the path under the applied rules.

### Visual Example

```text
Case A — permitted by CA A's pathLen rule:

Trust anchor
    |
   CA A [pathLen=0]
    |
   Leaf service.example.test

    Non-self-issued intermediate CAs below CA A: 0


Case B — violates CA A's pathLen=0:

Trust anchor
    |
   CA A [pathLen=0]
    |
   CA B [CA=true, non-self-issued]
    |
   Leaf service.example.test

    Non-self-issued intermediate CAs below CA A: 1 > 0
```

If `CA A` is a **directly supplied trust anchor** rather than a certificate inside `CertPath`, constraints recorded in **the certificate representing the trust anchor** are not necessarily processed by PKIX validation the same way as constraints on a CA in the path. This is a critical distinction! To genuinely test path length in a lab, place the constrained CA as an **intermediate certificate inside the path**, rather than putting `pathLen=0` on a trusted root and assuming JCA enforces that limit on every chain.

### Factors Affecting the Count

- Counts **non-self-issued intermediate CAs** below the constrained CA, excluding end entities.
- **Self-issued certificates** have special handling rules; self-issued does not always mean *self-signed*. Never treat `subject == issuer` as cryptographic proof of self-signing.
- Path length restricts **CA hierarchy depth**, not network limits like “only 3 hops” or certificate byte size.
- A CA with `pathLenConstraint=1` can allow one subsequent non-self-issued CA below it, then a leaf; however, other constraints may tighten limits further.
- A root/trust anchor can be configured outside the path. Do not inspect `getBasicConstraints()` on a root and assume the validator always applies it like an intermediate CA constraint.
- Name constraints, certificate policies, trust-anchor constraints, and algorithm/revocation rules can still cause rejection even when intermediate CA depth is within limits.

### Configuring Path Length When Creating a Test CA

With `keytool` on a supporting JDK, a CA certificate can be created with the extension:

```text
-ext BC:critical=ca:true,pathlen:0
```

This is a **keytool argument**. If this CA issues a leaf directly, there is no intermediate below the CA. If you test creating another CA B and building a path through CA B, keep **CA A inside `CertPath`**, not solely as the trust anchor, to verify `pathLenConstraint` at the intended position.

## 6. KeyUsage: Which Operations Is the Key Permitted to Perform?

The `KeyUsage` extension is a bit string specifying the permitted functions for the public key in the certificate. Do not equate the fact that a key mathematically **can** verify a signature with the certificate **being permitted** to act as a CA or be used for TLS.

Common bits:

| Bit / name | Typical meaning |
| --- | --- |
| `digitalSignature` | Verifying digital signatures in permitted contexts |
| `nonRepudiation` / `contentCommitment` | Content commitment per profile; does not by itself guarantee legal status |
| `keyEncipherment` | Key encryption/wrapping in applicable protocols |
| `dataEncipherment` | Data encryption in legacy/specific profiles |
| `keyAgreement` | Participating in shared-secret establishment via key agreement |
| `keyCertSign` | **Signing certificates** when the certificate is a CA |
| `cRLSign` | Signing certificate revocation lists |
| `encipherOnly` / `decipherOnly` | Used alongside `keyAgreement` per corresponding rules |

Java's `X509Certificate.getKeyUsage()` returns a `boolean[]` with standard fixed indices:

```text
index 0 digitalSignature
index 1 nonRepudiation / contentCommitment
index 2 keyEncipherment
index 3 dataEncipherment
index 4 keyAgreement
index 5 keyCertSign
index 6 cRLSign
index 7 encipherOnly
index 8 decipherOnly
```

If the extension is absent, `getKeyUsage()` can return **null**. Never index directly into `getKeyUsage()[5]` in a generic verifier without checking for null/length; the lab code in Section 10 accesses it because **the lab itself explicitly issued certificates with that extension**.

### What Does a CA Need to Sign Certificates?

For an intermediate CA in a path:

- `BasicConstraints` must indicate CA status per PKIX rules.
- If `KeyUsage` is present, the `keyCertSign` bit must allow signing certificates.
- The certificate must have a valid signature/issuer/path.
- Other restrictions—including path length, name constraints, validity, and policies—must also hold.

**Do not** look only at `keyCertSign=true` and ignore `CA=false`. Conversely, `CA=true` with a `KeyUsage` that **forbids** `keyCertSign` is also invalid for an issuing CA in the path. Both must be evaluated **together**.

### Leaf KeyUsage Depends on TLS Mode

In modern TLS, a leaf certificate typically needs `digitalSignature` for signature-based authentication. In legacy profiles/protocols, certain key exchanges/cipher suites require `keyEncipherment` or `keyAgreement`. Never apply one protocol/version/algorithm-independent formula to every certificate.

With an RSA public key, a signature may verify mathematically; yet if the certificate was issued only for another purpose per `KeyUsage`/`EKU`, the application **must not** interpret it as a valid TLS server certificate contrary to policy.

## 7. ExtendedKeyUsage (EKU): Application Purpose

**EKU** is an extensible set of OIDs classifying certificate usage purposes, typically:

| Purpose | OID | Example |
| --- | --- | --- |
| `serverAuth` | `1.3.6.1.5.5.7.3.1` | TLS server authentication |
| `clientAuth` | `1.3.6.1.5.5.7.3.2` | TLS client authentication in mTLS |
| `codeSigning` | `1.3.6.1.5.5.7.3.3` | Software/code signing |
| `emailProtection` | `1.3.6.1.5.5.7.3.4` | Email protection |
| `timeStamping` | `1.3.6.1.5.5.7.3.8` | Timestamp signing per service rules |
| `OCSPSigning` | `1.3.6.1.5.5.7.3.9` | Signing OCSP responses per profile |

In Java, `X509Certificate.getExtendedKeyUsage()` returns a `List<String>` of OIDs or `null` when the extension is absent. Its **absence** has no universal allow/deny outcome across all applications; apply the rules of your protocol/CA profile/TLS stack. When present, intended usages must be verified per RFC/application. Broad OIDs like `anyExtendedKeyUsage` have specific semantics; never treat them as a license to skip purpose checks.

### Why Must KeyUsage and EKU Be Combined?

A leaf with:

```text
BasicConstraints: CA=false
KeyUsage: digitalSignature
ExtendedKeyUsage: serverAuth
SubjectAlternativeName: DNS:service.example.test
```

is an **appropriate starting profile** for a TLS server certificate in the right context, yet it still requires a trusted chain, valid timestamps, algorithm constraints, revocation/distrust policy, and **a hostname that genuinely matches the SAN**.

If a leaf has `EKU=clientAuth` while an endpoint uses it as a TLS server, it must be rejected under TLS server policy. If a leaf has `EKU=codeSigning`, never accept it as a TLS server certificate just because both use RSA/ECDSA.

**Purpose does not replace identity:** `serverAuth` specifies the kind of task, **not** which DNS names are allowed. `SAN`/endpoint identification is a separate check. A receiver of an mTLS client certificate must also map the verified certificate identity to an authorized principal/tenant.

### A Warning About the API

Calling `cert.getExtendedKeyUsage()` and comparing OIDs yourself in a demo illustrates **how to read the metadata**; it **does not mean** the code performs full JSSE TLS server authentication. In production, use `X509ExtendedTrustManager`/the TLS stack or an audited API so EKU, KU, and hostname are enforced **per protocol**.

## 8. Name Constraints and Certificate Policies: Constraints You Must Not Skip

Although the lesson title emphasizes time, CA, path length, and usage, a compliant path validator handles other critical extensions as well.

**Name Constraints:** a CA can be restricted in the identity namespaces it may issue for subordinate certificates—such as designated DNS/email/IP ranges. They often appear on intermediate CAs and must be enforced by the PKIX algorithm. **Never** substitute a naive `String.endsWith()` check: DNS suffixes, punycode, wildcards, Unicode, and matching rules involve security-sensitive details.

**Certificate Policies / policy constraints:** a CA/certificate can carry OIDs for issuance policies, explicit policy requirements, policy mappings, and inhibit flags; applications with specialized threat models may require specific OIDs. A path with valid signatures and a trusted root **can still be rejected** if required policy constraints are unmet.

**Critical extensions:** RFC 5280 requires not ignoring any critical extension that path processing does not understand. If you hand-roll “verify signature then accept” using only `PublicKey` and `Signature`, you bypass `BasicConstraints`, KU, path length, name constraints, and mandatory extensions. Use a maintained PKIX engine.

## 9. Java APIs: Reading Metadata vs PKIX Validation Are Two Different Tasks

Key APIs:

| Java API | Role | Key caveat |
| --- | --- | --- |
| `CertificateFactory.getInstance("X.509")` | Parses X.509 DER/PEM, creates `CertPath` | Parsing does not establish trust |
| `X509Certificate.checkValidity(Date)` | Checks one certificate's validity dates | Does not check chain or hostname |
| `X509Certificate.getBasicConstraints()` | Reads CA/pathLen metadata | `-1` is non-CA; root anchor has special semantics |
| `X509Certificate.getKeyUsage()` | Reads KeyUsage bitset | Nullable, standard bit order |
| `X509Certificate.getExtendedKeyUsage()` | Reads EKU OIDs | Nullable; requires protocol-specific policy |
| `CertPathBuilder.getInstance("PKIX")` | Finds a path to a trust anchor given parameters and cert stores | A built path does not replace endpoint identification |
| `CertPathValidator.getInstance("PKIX")` | Validates an already-constructed path | Needs trusted anchors, date, revocation/policy |
| `PKIXParameters` | Configures trust anchors, date, revocation, cert stores, policies | Never take trust anchors from user requests |
| `TrustAnchor` | Represents a trusted root/trust anchor | Configured outside the path; trust is never inferred from the cert |
| `PKIXCertPathChecker` | Extends path processing via standard API | Never write a custom checker to bypass validation |
| `X509ExtendedTrustManager` | TLS chain validation with socket/engine context | Tied to JSSE for protocol context |

Example reading metadata (illustrative snippet, not standalone):

```java
int basic = cert.getBasicConstraints();
boolean isCa = basic >= 0;

boolean[] ku = cert.getKeyUsage();
boolean canSignCertificates = ku != null && ku.length > 5 && ku[5];

List<String> eku = cert.getExtendedKeyUsage();
boolean explicitServerAuth = eku != null
        && eku.contains("1.3.6.1.5.5.7.3.1");

cert.checkValidity(new Date());
```

Requires importing `java.util.List`, `java.util.Date` and assumes an `X509Certificate cert` is available; some calls throw checked exceptions. **This is isolated metadata inspection**, not a substitute for `PKIX` path validation or TLS endpoint verification. Seeing `getBasicConstraints() >= 0` does not prove a CA is an issuer authorized by policy.

## 10. Java 17+ Lab: Creating Root, Leaf, and Testing Verification

This lab runs **entirely with keytool + JDK 17+**, requiring no external website or third-party certificates. We create:

- `root.pem`: self-signed RSA 2048 **test root CA**, `BasicConstraints CA=true, pathLen=0`, `KeyUsage keyCertSign,cRLSign`, valid 365 days.
- `leaf.pem`: service certificate `service.example.test` signed by root, valid 90 days, `CA=false`, `KeyUsage digitalSignature`, `EKU serverAuth`, `SAN DNS:service.example.test`.
- `other.pem`: **another test root** that did not sign the leaf.

Java creates a `CertPath` containing only the leaf, configures `root` as the trust anchor, and validates at the current date and 120 days later. Testing with the unrelated root must fail. **The root's `pathLen=0` in the lab is read/printed but must not be mistaken for a test enforcing `pathLenConstraint` on an intermediate**, because the root here is the trust anchor outside `CertPath`.

### 10.1 Generating Lab Certificates with keytool

Run in a **dedicated test directory, never a directory containing production keystores**. Generated keys/passwords are strictly for the lab. The password `changeit` below is a **public demo password—never use it for real keys or environments**. In production, use prompts/secret managers instead of command-line passwords.

The commands below run in **bash/POSIX shells** (trailing `\` continues the line):

```bash
# Test Root CA, signs certificates and CRLs, pathLenConstraint=0
keytool -genkeypair -alias root -keyalg RSA -keysize 2048 \
  -sigalg SHA256withRSA -dname "CN=Training Root CA" \
  -validity 365 -ext "BC:critical=ca:true,pathlen:0" \
  -ext "KU:critical=keyCertSign,cRLSign" \
  -keystore root.p12 -storetype PKCS12 \
  -storepass changeit -keypass changeit -noprompt

keytool -exportcert -rfc -alias root \
  -keystore root.p12 -storepass changeit -file root.pem

# Generate separate keypair for leaf, create CSR
keytool -genkeypair -alias leaf -keyalg RSA -keysize 2048 \
  -sigalg SHA256withRSA -dname "CN=service.example.test" \
  -validity 90 -keystore leaf.p12 -storetype PKCS12 \
  -storepass changeit -keypass changeit -noprompt

keytool -certreq -alias leaf -keystore leaf.p12 \
  -storepass changeit -file leaf.csr

# Root signs leaf certificate with lab KU/EKU/SAN profile
keytool -gencert -alias root -keystore root.p12 \
  -storepass changeit -infile leaf.csr -outfile leaf.pem \
  -rfc -validity 90 -ext "BC:critical=ca:false" \
  -ext "KU:critical=digitalSignature" \
  -ext "EKU=serverAuth" \
  -ext "SAN=dns:service.example.test"

# Another root, does not sign leaf: negative control
keytool -genkeypair -alias other -keyalg RSA -keysize 2048 \
  -sigalg SHA256withRSA -dname "CN=Unrelated Root CA" \
  -validity 365 -ext "BC:critical=ca:true,pathlen:0" \
  -ext "KU:critical=keyCertSign,cRLSign" \
  -keystore other.p12 -storetype PKCS12 \
  -storepass changeit -keypass changeit -noprompt

keytool -exportcert -rfc -alias other \
  -keystore other.p12 -storepass changeit -file other.pem
```

If using PowerShell, enter each command on a single line or use PowerShell line continuation; **do not** paste POSIX trailing `\`. Never import these test roots into `cacerts`/production truststores. Delete all test key files per policy after the lab. `root.p12`/`leaf.p12`/`other.p12` hold **demo private keys**, whereas `root.pem`/`leaf.pem`/`other.pem` are only public certificates.

### 10.2 Standalone Java Source

Save as **`PkixPolicyDemo.java`** in the **same directory** containing the three generated PEM certificates:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertPathValidatorException;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Date;
import java.util.List;
import java.util.Set;

public class PkixPolicyDemo {
    static X509Certificate readCertificate(String name) throws Exception {
        try (var stream = Files.newInputStream(Path.of(name))) {
            return (X509Certificate) CertificateFactory
                    .getInstance("X.509").generateCertificate(stream);
        }
    }

    static boolean validate(CertPath path, X509Certificate root, Date at)
            throws Exception {
        PKIXParameters params = new PKIXParameters(
                Set.of(new TrustAnchor(root, null)));
        params.setRevocationEnabled(false); // Lab only.
        params.setDate(at);
        try {
            CertPathValidator.getInstance("PKIX").validate(path, params);
            return true;
        } catch (CertPathValidatorException ex) {
            return false;
        }
    }

    static boolean hasDnsSan(X509Certificate cert, String name)
            throws Exception {
        var sans = cert.getSubjectAlternativeNames();
        if (sans == null) return false;
        for (var entry : sans) {
            if (Integer.valueOf(2).equals(entry.get(0))
                    && name.equals(entry.get(1))) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        X509Certificate root = readCertificate("root.pem");
        X509Certificate leaf = readCertificate("leaf.pem");
        X509Certificate unrelated = readCertificate("other.pem");
        CertPath path = CertificateFactory.getInstance("X.509")
                .generateCertPath(List.of(leaf));

        System.out.println("Root is CA: " + (root.getBasicConstraints() >= 0));
        System.out.println("Root pathLenConstraint: " + root.getBasicConstraints());
        System.out.println("Root keyCertSign: " + root.getKeyUsage()[5]);
        System.out.println("Leaf is CA: " + (leaf.getBasicConstraints() >= 0));
        System.out.println("Leaf digitalSignature: " + leaf.getKeyUsage()[0]);
        System.out.println("Leaf serverAuth EKU: " + leaf.getExtendedKeyUsage()
                .contains("1.3.6.1.5.5.7.3.1"));
        System.out.println("Expected DNS SAN present: " +
                hasDnsSan(leaf, "service.example.test"));
        System.out.println("Path valid today: " +
                validate(path, root, Date.from(Instant.now())));
        System.out.println("Path valid after 120 days: " +
                validate(path, root,
                        Date.from(Instant.now().plus(120, ChronoUnit.DAYS))));
        System.out.println("Path with unrelated root valid: " +
                validate(path, unrelated, Date.from(Instant.now())));
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac --release 17 PkixPolicyDemo.java
java PkixPolicyDemo
```

**Verified stdout in the lab using the commands above:**

```text
Root is CA: true
Root pathLenConstraint: 0
Root keyCertSign: true
Leaf is CA: false
Leaf digitalSignature: true
Leaf serverAuth EKU: true
Expected DNS SAN present: true
Path valid today: true
Path valid after 120 days: false
Path with unrelated root valid: false
```

**Conditions for this output:** the certificates must be freshly generated when running the lab, the provider/JDK must support the keytool extensions/algorithms, and no extra security policy may block RSA-2048/SHA256withRSA. If old certificates sit on disk past 90 days, `Path valid today` will flip—which is the expected behavior of validity checking. On a different provider or security policy, constraint sets can cause validation to fail. **Do not** treat the output as a constant string across all times and runtimes.

### 10.3 Why Does Each Line Appear?

1. `Root is CA: true` because root was generated with `BasicConstraints.cA=true`.
2. `Root pathLenConstraint: 0` is root metadata. In this test, root is a **TrustAnchor**, not an intermediate in the path; it is **not proof** that the validator enforced `pathLen=0` on an intermediate chain.
3. `Root keyCertSign: true` is `KeyUsage` bit 5 set on root by keytool.
4. `Leaf is CA: false` because leaf has `BasicConstraints.cA=false`; `getBasicConstraints()` returns `-1`.
5. `Leaf digitalSignature: true` is KU bit 0.
6. `Leaf serverAuth EKU: true` reads the EKU OID `1.3.6.1.5.5.7.3.1`. **Just reading an OID**, not a TLS handshake test.
7. `Expected DNS SAN present: true` looks up a **literal string** in the SAN of the lab-created certificate. It does not replace JSSE hostname verification across all DNS/IP types, wildcards, or IDNs.
8. `Path valid today: true` because the leaf was newly issued, signed by the right root anchor, valid under lab conditions, and revocation checking was **explicitly disabled for the lab**.
9. `Path valid after 120 days: false` because the leaf was issued for only 90 days; root for 365 days. The path check is rejected at the future date due to leaf validity.
10. `Path with unrelated root valid: false` because the second root did not sign the leaf and no valid path leads to that anchor.
11. `validate` catches only `CertPathValidatorException` to convert validation failure into `false`. I/O, parsing, provider, misconfiguration, or programming errors still propagate; never conflate every exception with “untrusted certificate”.
12. `hasDnsSan` is strictly for learning; all production certificates must be verified using proper TLS endpoint identification and securely configured CA policies.

### 10.4 Intentional Security Limitations

`PKIXParameters.setRevocationEnabled(false)` is a setting **strictly for an offline lab without CRL/OCSP**. It is **not** a production configuration template. Enabling/disabling revocation and handling unreachable OCSP/CRL must be driven by your threat model, policy, and infrastructure.

The `keytool`-generated Root CA is a **new self-signed root**. It is trusted in the lab only because we explicitly configured `TrustAnchor(root, null)`. A valid self-signature or the name `Training Root CA` does not make the root trustworthy to other applications. **Never import** these roots into default `cacerts`.

`CertificateFactory.generateCertPath(List.of(leaf))` builds an already-known path. For chains with multiple intermediates and paths built from a certificate store, use `CertPathBuilder`/`CertStore` or a maintained JSSE/TLS stack rather than guessing the issuer from subject strings.

## 11. Properly Testing pathLenConstraint Enforcement for Intermediates

The main lab tests validity dates, CA metadata, KU/EKU, and trust anchors. To **genuinely** test `pathLenConstraint`, build a chain with at least one intermediate:

```text
Root R           (TrustAnchor; outside CertPath)
   |
   v
Intermediate A   (BasicConstraints CA=true, pathLenConstraint=0)
   |
   +--> Leaf L1  (CA=false)        : depth OK
   |
   +--> Intermediate B (CA=true, non-self-issued)
                |
                +--> Leaf L2       : exceeds A's pathLen=0
```

Test design:

1. Generate test root R and import into the validator's trust anchors (test only).
2. Generate CA A with `CA=true, pathLen=0, KU=keyCertSign`, signed by root R.
3. Generate leaf L1 signed directly by A. Validate `[L1,A]` with anchor R: if all other conditions hold, **A's own pathLen** permits this because no non-self-issued CA sits under A.
4. Generate intermediate CA B with `CA=true` signed by A, and leaf L2 signed by B.
5. Validate `[L2,B,A]` with anchor R: barring self-issued exceptions and with standard test certs, **A's `pathLen=0` is violated**.
6. Run a control test with `A.pathLen=1` to confirm `[L2,B,A]` is not rejected for path length (remaining constraints must still pass).
7. Test an intermediate missing `BasicConstraints CA=true` or missing `KeyUsage.keyCertSign` while KU is present: the path may have mathematically valid RSA/ECDSA signatures yet **must still be rejected** because the CA is unauthorized to sign certificates.
8. Do not place A as `TrustAnchor` when testing constraints on certificate A itself in the path; doing so can bypass checking the trust anchor certificate's constraints as an intermediate.

This exercise requires **purpose-built test certificates**; you cannot deduce it from a single `getBasicConstraints()` value. Prefer a standard library/PKIX engine to handle non-self-issued CA counting, self-issued exceptions, name constraints, and certificate policies.

## 12. Checking TLS Server/Client Purpose at the Right Layer

An HTTPS handshake does not merely ask “is there a path from leaf to a trusted root?” but also:

```text
Peer sends leaf + intermediate(s)
         |
         v
Build & validate PKIX path
         |
         v
Check server/client TLS certificate profile
  - KU appropriate for handshake/algorithm
  - EKU appropriate: serverAuth vs clientAuth
  - algorithm/key sizes/sig schemes allowed
         |
         v
Check endpoint identity (hostname/IP in SAN)
         |
         v
Check revocation/distrust policies as configured
         |
         v
TLS authentication success
         |
         v
Application authorization still required
```

Actual internal ordering can vary across TLS providers/handshakes, yet **required controls must not be omitted**.

### HTTPS Client

Suppose a client connects to `https://api.example.test`. The server may present a leaf with:

```text
SAN DNS: api-other.example.test
EKU: serverAuth
CA/path: valid to a trusted root
```

Even though the chain and EKU may be valid, **the hostname does not match**, so the connection must be rejected. Never use `getSubjectX500Principal().getName().contains("api")` to verify names yourself. For HTTPS, use the TLS stack's endpoint identification, including supported wildcard and IDN rules.

### mTLS Server Authenticating Clients

In mTLS, the server validates the client certificate against permitted CAs and a different policy:

- Leaf matches `clientAuth` and TLS profile KU.
- Certificate path validates to a trust anchor dedicated to client identities.
- Client identity in SAN/Subject matches the issued profile and maps to a trusted principal.
- **Authorization** decides which API actions and tenants/resources that principal may access.

Adding a public CA to a truststore used for mTLS client authentication can unintentionally widen which client certificates are accepted. Trust only the exact issuing CAs and profiles authorized by your system.

### Code Signing and Email

A certificate with `EKU=codeSigning` or `emailProtection` is not automatically valid as a TLS server. Trust anchors/policies for software signing or email can also differ from HTTPS root trust. Never share one purpose-blind truststore simply because everything uses X.509.

## 13. CA and Trust Anchor Lifetimes: Distinguishing Policy from PKIX Engine

Here is a subtle pitfall when checking validity dates:

- **End-entity/leaf** and **intermediates in `CertPath`** must satisfy validity at PKIX validation time.
- **Trust anchors** are typically configured separately and may not have all certificate extensions/validity checked like a certificate inside the path. A trust anchor can be declared by CA name/public key or a representative certificate.
- Consequently, if a trusted root expires or policy distrusts it, you cannot expect every `CertPathValidator` invocation to automatically handle it per your root program policy. Manage truststores, root expiry, algorithm policy, and revocation/distrust separately as appropriate.
- During path building, multiple valid paths to different anchors may exist; an expired/removed root does not always cause all paths to fail if a cross-signed/alternate path remains permitted.
- For historical verification, standards/evidence like timestamps, archived validation data, and policies for older signatures differ from live TLS authentication.

**What never to do:** pass a root certificate provided by a remote peer into `new TrustAnchor(root,null)`, validate the leaf, and conclude the remote peer is trustworthy. That is the **“trust-on-input”** flaw: the attacker supplies both the root and the chain, so valid math only validates attacker-chosen data.

## 14. Revocation and Evaluation Time: Essential to the Threat Model

A certificate can be **unexpired yet revoked** due to key compromise, misissuance, or inaccurate identity. CRL and OCSP are mechanisms for evaluating revocation status per profile. Java PKIX provides `PKIXRevocationChecker` and related parameters/cert stores, yet you must not assume every JSSE client enables revocation identically.

Decisions required:

1. Who provides CRL/OCSP, URLs, and caching mechanisms?
2. **Fail-closed** or **soft-fail** policy when the responder/CRL is unreachable?
3. Is OCSP stapling or vendor distrust mechanism available?
4. Is the verification timestamp current time or a historical instant bound by a trusted timestamp?
5. With private PKI, do PKI operations guarantee timely revocation and CRL issuance?
6. Are intermediates and trust anchors checked under dedicated CA policy?
7. Protection against requests causing network dependencies/unbounded I/O during path building or external revocation lookups.

If a system **is required** to check revocation and disables `setRevocationEnabled(false)` to avoid latency/outages, that is not an acceptable “optimization”. The lab disables it because generated certificates have no CRL/OCSP infrastructure; production must follow policy.

## 15. When Path Validation Fails: Reading Reasons Properly

Java's `CertPathValidatorException` can supply `getReason()`, `getIndex()` (certificate position in the path), and the underlying cause. Common reasons include:

- `BasicReason.EXPIRED` or `NOT_YET_VALID`
- `BasicReason.INVALID_SIGNATURE`
- `BasicReason.REVOKED` or `UNDETERMINED_REVOCATION_STATUS`
- `PKIXReason.NOT_CA_CERT`
- `PKIXReason.PATH_TOO_LONG`
- `PKIXReason.INVALID_KEY_USAGE`
- `PKIXReason.INVALID_POLICY` / `INVALID_NAME` / `UNRECOGNIZED_CRIT_EXT`

Exact reason names and exception mappings can vary across providers/JDKs/cases. Never depend on **a specific exception text string** as a stable API contract; log reason/index to a controlled internal channel and inspect the actual path.

### Troubleshooting Table

| Error/symptom | Possible cause | Check first |
| --- | --- | --- |
| Certificate expired | Leaf/intermediate is past `notAfter` | Runtime clock, per-cert validity, active chain |
| Not yet valid | `notBefore` is in the future | Clock/NTP, provisioning/rollout timing |
| Not a CA | Intermediate has `CA=false` or lacks compliant BasicConstraints | Issuing CA certificate profile |
| Invalid key usage | Issuer KU does not allow `keyCertSign` | KU bits and certificate issuance policy |
| Path too long | Intermediate CAs exceed `pathLenConstraint` | Count non-self-issued CAs below the constrained CA in the path |
| No valid path | Missing issuer/bad cross-sign/untrusted root | Truststore, intermediates, signatures, path builder |
| Invalid purpose | Leaf has only `clientAuth`/`codeSigning` for a TLS server | EKU and TLS certificate profile |
| Hostname mismatch | SAN does not contain matching endpoint DNS/IP | URL/SNI, SAN, TLS endpoint identification |
| Revocation/OCSP error | Certificate revoked or status undetermined | Revocation policy, OCSP/CRL, clock/caching |
| Disabled algorithm | RSA key size/signature algorithm violates policy | Security properties, JDK policy, and CA migration |
| Root trusted yet still fails | Root does not bypass KU/EKU/time/name constraints in path | Full chain and policy |
| Cert parses yet fails | Parsing does not equal validation | Separate parse vs path vs TLS purpose failures |

When errors occur, **never** turn on “trust all”, disable hostname verification, skip CA/KU/EKU checks, or pass a fake `PKIXParameters.setDate` to “fix” them. Fix the certificate, CA chain, truststore, or system clock via approved procedures.

## 16. Designing Comprehensive Tests

A test suite should cover both **valid paths** and **intentionally rejected paths**:

| Test | Input | Expected outcome |
| --- | --- | --- |
| Valid path | TLS server leaf, valid issuing CA, right root | PKIX passes under configured policy |
| Not yet valid | `date` before `leaf.notBefore` | Reject |
| Expired | `date` after `leaf.notAfter` | Reject |
| Leaf without trusted issuer | Unrelated root as anchor | Reject |
| CA=false signing certificate | Intermediate issuer lacks CA flag | Reject |
| CA has KU without keyCertSign | Intermediate KU forbids cert signing | Reject |
| CA A pathLen=0 signs leaf directly | `[leaf,A]` with A as intermediate | A's own pathLen does not block leaf |
| CA A pathLen=0 signs CA B then leaf | `[leaf,B,A]`, A/B as intermediates | Reject due to path length |
| CA A pathLen=1 signs CA B then leaf | One non-self-issued CA B below A | A's pathLen permits it; other checks must still pass |
| EKU serverAuth | Leaf used as TLS server | Proceeds if KU/chain/SAN are valid |
| EKU clientAuth-only | Leaf used for HTTPS server | TLS server policy rejects |
| Different SAN hostname | Chain and KU/EKU valid yet DNS differs | TLS endpoint rejects |
| CA name constraints | Leaf outside permitted domain | PKIX rejects |
| Unrecognized critical extension | Issuer/leaf contains unsupported critical extension | Reject |
| Revoked certificate | CA publishes revoked status per policy | Reject |
| Untrusted root | User supplies self-signed root | Do not add as trust anchor |
| Valid trusted root yet expired leaf | Root still unexpired | Reject due to leaf |
| Time skew | Two nodes with skewed clocks | Detect via monitoring; never drop validation |
| Alternate chain | Same leaf has multiple paths to permitted anchors | Accept/reject based on full path policy |
| mTLS wrong client tenant | Client cert valid yet lacks business permissions | Reject at authorization |
| CA rotation | Trust bundle holds Old/New during transition | Defined by policy, never trust-all |
| Disabled revocation in lab | Offline test CA without OCSP/CRL | Allowed strictly in lab with explicit exception |

**Important:** CA `pathLen` tests must include **at least one intermediate in `CertPath`** to test that intermediate's policy. Testing only root (`TrustAnchor`) and leaf does not prove the path length algorithm ran below the root.

### Golden Vectors and Interoperability

Do not test solely with the same library that generated the certificates. Use `keytool`, OpenSSL, or a controlled PKI lab to build independent fixtures; store **public DER/PEM certificates** and document generation steps/tool versions. Never commit real private keys to repositories. Tests should construct targeted truststores without modifying the developer machine's `cacerts`.

## 17. Practical Deployment in JSSE / HTTPS

Java HTTPS clients typically use a JSSE trust manager and **endpoint identification** via standard APIs. When writing a custom `SSLContext` or `X509TrustManager`, never accidentally drop hostname verification/TLS purpose checks; a generic `CertPathValidator.validate` call is not enough to build a secure HTTPS client yourself.

Recommended model:

```text
HTTPS client configured with trusted root store
        |
        v
JSSE handshake / trusted CA path
        |
        v
certificate time + CA BasicConstraints + pathLen + KeyUsage
        |
        v
TLS purpose (EKU/KU) and endpoint identification (SAN)
        |
        v
connection authenticated
        |
        v
application checks service identity, authz and resource permissions
```

This is a functional diagram; internal sequencing varies by TLS stack/provider. When using `SSLSocket` directly, configure `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` per use case. With `java.net.http.HttpClient`, rely on built-in HTTPS/endpoint identity verification instead of creating a no-op `checkServerTrusted` trust manager.

**CA scope:** Provision root trust within the appropriate client/tenant/protocol scope—never add arbitrary peer-sent intermediates/CAs to the truststore. Modifying a truststore changes which chains can be accepted, not merely a file-parsing detail.

## 18. Common Conceptual Mistakes

1. **“If the signature is valid, the certificate is trusted.”** False: requires a trusted trust anchor and path policy.
2. **“CA=true is enough to sign certs.”** False: also requires `keyCertSign` if KU is present, validity, `pathLen`, name constraints, signature, and algorithm policy.
3. **“pathLen=0 means it cannot sign leaves.”** False: a leaf is not a non-self-issued intermediate CA.
4. **“Path length = number of certificates in the list.”** False: counts qualifying non-self-issued CAs, excluding leaves and subject to self-issued rules.
5. **“Setting root pathLen=0 and running root-anchor + leaf tests pathLen.”** Unproven: trust anchor constraints may sit outside path validation constraints.
6. **“If the leaf has serverAuth, the hostname matches.”** False: `serverAuth` is usage purpose; SAN/endpoint identification is identity.
7. **“If a leaf has keyCertSign, it's a CA.”** False: requires `BasicConstraints CA=true` and full PKIX rules.
8. **“X509EncodedKeySpec is a certificate.”** False: it is a public-key SPKI spec; `CertificateFactory` parses certificates.
9. **“Expired but validly signed means we can ignore the date.”** Forbidden for live TLS authentication.
10. **“Root is in cacerts, so every cert under it is valid.”** False: leaf/intermediate can fail KU/EKU/validity/hostname/algorithm/revocation.
11. **“`getExtendedKeyUsage()==null` means allowed for any task.”** Not automatically true; depends on certificate profile/TLS policy.
12. **“One `getBasicConstraints()` check validates the path.”** False: requires path processing, signatures, and policies.
13. **“Disabling revocation is always safe because the cert isn't expired.”** False: compromise can occur prior to expiry; handle revocation per threat model.
14. **“Build a TrustAnchor from the peer-sent root.”** False: an attacker can send their own root; trust anchors must come from trusted configuration.
15. **“A single `verifyIssuer` Java call is all of PKIX.”** False: that only checks one digital signature on one certificate.
16. **“Hostname mismatch is just a DNS bug.”** False: names are checked between the requested endpoint and certificate identity; it can indicate a MITM attack.
17. **“Accepting an mTLS client certificate grants admin rights.”** False: still requires principal/tenant mapping and authorization.
18. **“All JDKs/providers emit the exact same exception message.”** False: use typed APIs/reasons/index and test on your target runtime.
19. **“You can use a client-supplied date to verify HTTPS.”** False: evaluation time must come from policy/trusted sources.
20. **“Ignoring unknown critical extensions improves compatibility.”** False: breaks security invariants; use a compliant PKIX implementation.

## 19. Practice Exercises

### Exercise 1 — Reading Metadata

Run the lab in Section 10 and explain why `root.getBasicConstraints() == 0` while `leaf.getBasicConstraints() == -1`. Print `getNotBefore/getNotAfter` for each certificate; construct `Date` values before and after validity to observe `checkValidity`.

### Exercise 2 — Expired Yet Validly Signed

Keep the root-signed leaf unchanged. Shift the test date to 120 days later. Explain why the mathematical signature remains valid while PKIX rejects it. Try changing the system clock inside an **isolated lab environment** and restoring it; never alter NTP/clocks on production hosts.

### Exercise 3 — Unauthorized Issuing CA

Create an intermediate with `BasicConstraints CA=false` and sign a leaf using its private key. A mathematically valid signature can be produced; what causes PKIX to reject that intermediate as an issuer? Also test a KU missing `keyCertSign` and compare the failure reasons.

### Exercise 4 — True pathLenConstraint Testing

Build R → A(pathLen=0) → L and R → A(pathLen=0) → B(CA=true) → L. Configure **R as TrustAnchor**, keep **A inside CertPath**, and do not use A as TrustAnchor. Explain why the second path must be rejected for intermediate depth. Try A(pathLen=1) and check remaining constraints.

### Exercise 5 — EKU serverAuth and clientAuth

Create two leaves with the same issuer and distinct SANs: one `EKU=serverAuth`, one `EKU=clientAuth`. Set up a policy-compliant JSSE HTTPS/mTLS test. Is passing the PKIX chain alone enough to use a `clientAuth`-only leaf as a server? Describe the role of TLS usage checks.

### Exercise 6 — SAN and Hostname

The leaf has SAN `service.example.test`. Connect to `other.example.test` in the lab using the same leaf; the chain still validates. Measure/explain the TLS stack's hostname mismatch error, and why substring matching Subject CN is unsafe.

### Exercise 7 — Revocation and Evaluation Time

In a private PKI lab with OCSP/CRL, issue a valid leaf and then revoke it. Define a fail-closed or soft-fail policy, cache duration, and status handling when the responder is unreachable. Never remove revocation checking in production just to make tests pass.

### Exercise 8 — CI Integration

Create a fixture suite `root.pem`, `leaf-valid.pem`, `leaf-expired.pem`, `leaf-wrong-eku.pem`, `intermediate-no-ca.pem`, `intermediate-depth0.pem` along with trust anchor config. Test PKIX and TLS endpoints separately. All test private keys must be generated in a controlled environment and never reused in production.

### Exercise 9 — Analyzing Cross-Signed Paths

An intermediate has two certificate variants signed by two different roots. Depending on truststore and policy, the builder may find multiple paths. How do you ensure CA constraints, validity, name constraints, algorithm requirements, and leaf EKU are enforced on **the path actually selected**, rather than just checking a root name?

**Completion criteria:** You can inspect a certificate path and identify **which certificates must be CAs, which key usage permits issuance, which intermediates `pathLenConstraint` bounds, which timestamps must be checked, and which EKU/SAN fit the TLS endpoint**. Most importantly, you know how to **use PKIX/JSSE properly** rather than checking a few fields manually and calling it complete certificate verification.

## 20. References

- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): `BasicConstraints`, `KeyUsage`, `ExtendedKeyUsage`, validity, `pathLenConstraint`, and `6.1` path validation.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): verifying service identity via SAN/hostname.
- [Java 17 — X509Certificate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html): `checkValidity`, `getBasicConstraints`, `getKeyUsage`, `getExtendedKeyUsage`.
- [Java 17 — CertPathValidator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html): API for validating certificate paths.
- [Java 17 — PKIXParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXParameters.html): `TrustAnchor`, `setDate`, revocation/policy options.
- [Java 17 — CertPathBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathBuilder.html): path construction.
- [Java 17 — CertPathValidatorException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidatorException.html): reason and index of failing certificate.
- [Java 17 — TrustAnchor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/TrustAnchor.html): trust boundary.
- [Java 17 — X509ExtendedTrustManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/X509ExtendedTrustManager.html): certificate checking in TLS context.
- [Java 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): endpoint identification.
- [Java 17 — keytool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): generating test CAs and leaves with BasicConstraints, KU/EKU/SAN.
- [Oracle Java 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): TLS, trust managers, and path validation.
