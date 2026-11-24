# 13.4 Subject, Issuer, Serial Number, Validity Period, and X500Principal

## Learning Objectives

After this lesson, you can:

1. Read and distinguish five core pieces of information in an **X.509** digital certificate: **subject**, **issuer**, **serial number**, **notBefore**, and **notAfter**.
2. Use `javax.security.auth.x500.X500Principal` properly to work with **Distinguished Names (DNs)**, recognize **RDN/AVA**, attributes such as `CN`, `O`, `OU`, `C`, and escaping rules.
3. Understand why **subject DN does not equal hostname**, **issuer DN does not prove a trusted CA**, and **issuer + serial number** is the standard certificate identification scope.
4. Read a real certificate from **PEM/DER** using `CertificateFactory` and `X509Certificate` on **Java 17**, inspecting subject/issuer/serial/time without internal `sun.*` APIs.
5. Use `checkValidity()`/`checkValidity(Date)`, and understand **not yet valid/expired** errors, UTC, and the limits of validity-period checks.
6. Avoid confusing the **certificate serial number** with the `SERIALNUMBER` attribute **inside a DN**; distinguish **self-issued**, **self-signed**, and **trusted**.

## 1. What Fields Does an X.509 Certificate Have?

An X.509 digital certificate binds a **public key** with identity information under a PKI model. A **Certificate Authority (CA)** issues a certificate by signing the data to be certified; the recipient must verify the signature and build and evaluate the certificate chain according to trust policy.

Conceptual structure:

```text
Certificate
├── tbsCertificate (To Be Signed Certificate)
│   ├── version                 (v1/v2/v3)
│   ├── serialNumber            (serial number issued by the CA)
│   ├── signature               (algorithm signing TBS)
│   ├── issuer                  (DN of the issuing entity)
│   ├── validity
│   │   ├── notBefore           (validity start timestamp)
│   │   └── notAfter            (validity end timestamp)
│   ├── subject                 (DN of the subject, may be empty)
│   ├── subjectPublicKeyInfo    (algorithm + public key)
│   └── extensions              (SAN, BasicConstraints, KU, EKU, ...)
├── signatureAlgorithm
└── signatureValue              (CA's signature over TBS)
```

The main scope of this lesson is **issuer, subject, serial number, and validity**. Extensions such as **Subject Alternative Name (SAN)** are mentioned as needed to avoid misinterpreting the subject DN; trust path checks, revocation, and TLS policies are introduced as **boundaries**, not replacements for dedicated certificate/PKIX lessons.

Example of a hypothetical server certificate (not a valid certificate for real connections):

```text
Subject:     CN=api.example.test,O=Example Services,C=VN
Issuer:      CN=Example Issuing CA,O=Example PKI,C=VN
Serial:      0x34A728...              (a BigInteger)
Not Before:  2026-01-01T00:00:00Z
Not After:   2027-01-01T00:00:00Z
Public Key:  EC P-256
SAN:         DNS:api.example.test
```

**Important point:** each line describes a different aspect. Subject is the **subject**'s name, issuer is the **issuer**'s name, serial is an identifier **within the issuer's scope**, and validity is only a **time** interval. No single field on its own is proof that the certificate is trusted.

## 2. Subject: Name of the Entity Holding the Public Key

**Subject** in `TBSCertificate` identifies the entity bound to the public key in `subjectPublicKeyInfo`. It may be an organization, user, CA, or service; how identity is interpreted depends on the certificate type, CA, and verification policy.

A typical subject DN:

```text
CN=api.example.test,OU=Platform,O=Example Corp,L=Hanoi,C=VN
```

| DN attribute | Approximate meaning | Notes |
| --- | --- | --- |
| `CN` — Common Name | Common name of the subject | Do not treat `CN` alone as a verified TLS domain name |
| `O` — Organization | Organization | Do not assume the CA verified it across all profile types |
| `OU` — Organizational Unit | Unit within the organization | May be absent; do not use for access permissions |
| `C` — Country | Country code, e.g., `VN` | Does not prove where the server is hosted |
| `L` / `ST` | Locality / state-province | Identifying data, not an absolute source of trust |
| `DC` / `UID` | Domain component / user ID | **Attribute types**, not equivalent to DNS SAN or an authenticated username |

A name with multiple attributes is called a **Distinguished Name** (DN). A DN is an ASN.1 `Name` structure consisting of ordered **Relative Distinguished Names (RDNs)**; an RDN may contain **multiple Attribute Value Assertions (AVAs)**. Commas and plus signs in text representations have syntactic meaning, not just literal character data.

For example:

```text
CN=Doe\, Jane,O=Example Lab,C=VN
```

The `\,` represents a comma **inside the CN value**, not an RDN separator. Therefore, operations like `subjectString.split(",")` are **wrong** when parsing external DNs. Values may also contain `+`, `=`, `#`, significant whitespace, or Unicode/OID encodings; a standard DN parser is required.

### 2.1 The Subject DN Can Be **Empty**

RFC 5280 allows the subject to be represented as an **empty sequence** when identifying information resides in `subjectAltName`. When the subject is empty, the SAN extension must be present and marked **critical** per profile. `X509Certificate.getSubjectX500Principal()` still returns a valid `X500Principal`; `getName()` may return an **empty string**.

Do not write:

```java
// WRONG: assumes every certificate has a CN, and that CN is always the hostname.
String host = cert.getSubjectX500Principal()
        .getName().split(",")[0].substring(3);
```

The snippet above is an **anti-pattern** and must never go into production: the subject may be empty, CN may not be first, values may contain escaped characters, and TLS names must process **SAN** according to service identity verification profiles.

### 2.2 Subject CN and TLS Hostname Verification

**Subject DN is not itself proof of a valid hostname.** In modern TLS, service identity is represented and matched via **Subject Alternative Name** per policy (e.g., `dNSName`, `iPAddress`).

RFC 9525 (superseding RFC 6125) specifies that TLS service identity is no longer taken from the `commonName` RDN in the subject; the proper practice is to compare the expected service name against the appropriate SAN **after** PKI certificate validation.

In Java, never compare `CN=...` against the hostname yourself and disable hostname verification. Use HTTP/TLS clients and the platform's or library's properly configured hostname/trust verification mechanisms. Having `CN=example.com` in the subject **does not guarantee** connecting to `example.com` is trustworthy.

## 3. Issuer: Name of the Issuing/Signing Entity

**Issuer** in `TBSCertificate` is the DN of the CA that issued and signed the certificate. RFC 5280 requires the issuer DN to be **non-empty** for profile-compliant certificates.

Example chain:

```text
Leaf certificate:
    subject = CN=api.example.test,O=Example Services,C=VN
    issuer  = CN=Example Issuing CA,O=Example PKI,C=VN

Intermediate CA certificate:
    subject = CN=Example Issuing CA,O=Example PKI,C=VN
    issuer  = CN=Example Root CA,O=Example PKI,C=VN

Root CA certificate:
    subject = CN=Example Root CA,O=Example PKI,C=VN
    issuer  = CN=Example Root CA,O=Example PKI,C=VN
```

When building a certificate chain, **name chaining** links a child certificate's `issuer` to the parent certificate's `subject` under DN comparison rules. However, **matching names is only a necessary condition, not sufficient**. An attacker can generate a new certificate with a DN identical to a well-known CA; matching names proves neither possession of the CA's private key nor system trust.

A complete verification system also requires:

- Verifying the child certificate's **signature** using the **real public key** of the parent CA.
- Checking **CA BasicConstraints**, `keyCertSign` (KeyUsage), path length, allowed algorithms/keys, and related constraints.
- Building and validating a path to a configured trusted **trust anchor**.
- Checking **validity**, **revocation** (CRL/OCSP per policy), policy/name constraints, and service identity.
- Never trusting a CA merely because the issuer name matches a hardcoded string.

### 3.1 Self-Issued, Self-Signed, and Trusted Are Not Synonyms

| Property | Definition | What must **not** be inferred |
| --- | --- | --- |
| **Self-issued** | `subject` and `issuer` DNs are identical under name comparison rules | Does not prove the signature was made by the key in the certificate |
| **Self-signed** | The signature on the certificate verifies with the public key of **the certificate itself** | Does not prove the certificate is in the trust store |
| **Trusted** | The certificate/chain is accepted by trust policy from a managed trust anchor | Cannot rely solely on `subject == issuer` or `verify(publicKey)` |

A **self-issued certificate** is not necessarily **self-signed** (e.g., certain CA key rollover cases); and a self-signed certificate, even with a valid signature, is **not automatically trusted**. Root certificates become trust anchors only when managed in the verifier's trust store/acceptance policy.

In Java:

```java
boolean selfIssued = cert.getSubjectX500Principal()
        .equals(cert.getIssuerX500Principal());
```

This is an **inline snippet** with an already-loaded `X509Certificate cert` variable; `selfIssued` speaks only to **names**, not signatures or trust.

## 4. Serial Number: Certificate Identifier **Within the Issuer's Scope**

`serialNumber` of X.509 resides in `TBSCertificate`. It is an integer assigned by the **issuing CA** to **each certificate**, distinct from the subject name and distinct from user IDs.

Per RFC 5280:

- The serial must be a **positive integer** assigned by the CA to each certificate.
- Each serial must be **unique among certificates issued by the same CA/issuer**. Hence **issuer DN + serial number** identifies a certificate within the described PKI scope.
- Compliant CAs must not issue serials longer than **20 octets** per profile; implementations must handle large serials up to this limit.
- Non-compliant certificates with `0` or negative serials exist in practice; readers must handle them gracefully without crashing on the assumption that everything is compliant.

### 4.1 Comparing the Right Identification Unit

```text
Issuer A: CN=CA-A,O=Example,C=VN
  serial 0x01  -> certificate A-1

Issuer B: CN=CA-B,O=Example,C=VN
  serial 0x01  -> certificate B-1

Two equal serials can still be **two different certificates**.
```

Never use `serial` alone as a **global** primary key for all certificates. A serious PKI system must also verify the actual chain/issuer, because DNs can be reused and certificate data can be spoofed before verification.

In Java, read the serial via:

```java
BigInteger serial = cert.getSerialNumber();
String serialHex = serial.toString(16);
```

This is an **inline snippet** (requires `java.math.BigInteger`, variable `cert` of type `X509Certificate`). `getSerialNumber()` returns a `BigInteger`, **not a `long`**; do not call `longValue()` because it can lose bits and cause collisions after truncation. `toString(16)` is useful for debugging/lookup, while certificate matching should operate on typed values within a verified issuer scope.

Hex display formatting does not necessarily preserve leading `00` padding bytes from ASN.1 DER; distinguish **numeric value** from **byte representation**. Do not assume a serial is a “random token”, “secret”, or delegatable server ID.

### 4.2 Two Things Named “Serial Number” That Are Easily Confused

A DN can contain a `SERIALNUMBER` attribute with **OID `2.5.4.5`**:

```text
Subject: CN=Device A,SERIALNUMBER=ASSET-123,O=Factory,C=VN
```

That is a **text attribute of the subject DN**, which may represent a device/company code under a specific profile. It is **not** the `TBSCertificate.serialNumber` field assigned by the CA; the two values have different semantics and storage locations.

| Attribute | Where does it live? | Java API |
| --- | --- | --- |
| **Certificate serial number** | `TBSCertificate.serialNumber` | `cert.getSerialNumber()` → `BigInteger` |
| **DN SERIALNUMBER attribute** | An AVA/RDN inside `subject` or `issuer` | `cert.getSubjectX500Principal()` → parse DN/OID appropriately |

Do not extract `SERIALNUMBER=...` from a subject string to feed into CRL/revocation APIs or construct an issuer+serial ID.

## 5. Validity: `notBefore` and `notAfter`

A certificate contains a `Validity` field with two timestamps:

```asn1
Validity ::= SEQUENCE {
    notBefore Time,
    notAfter  Time
}
```

Per RFC 5280, the validity interval is inclusive of the start and end instants; intuitively:

```text
notBefore <= evaluation_time <= notAfter
```

| Field | Meaning | Java API |
| --- | --- | --- |
| `notBefore` | Earliest timestamp the certificate is valid | `getNotBefore()` → `java.util.Date` |
| `notAfter` | Latest timestamp the certificate is valid | `getNotAfter()` → `java.util.Date` |
| Current check | Checks whether “right now” falls within the interval | `checkValidity()` |
| Check at given time | Checks the interval against a passed timestamp | `checkValidity(Date date)` |

Two exceptions have distinct meanings:

- `CertificateNotYetValidException`: evaluation time is **before `notBefore`**.
- `CertificateExpiredException`: evaluation time is **after `notAfter`**.

`checkValidity()` checks the time interval against the runtime clock; `checkValidity(Date)` checks against a caller-supplied timestamp. It does **not** verify signatures, trust chains, hostnames, KeyUsage, EKU, CRL, or OCSP.

### 5.1 UTC, UTCTime, GeneralizedTime, and Timezones

In X.509 ASN.1, `Time` can be encoded as `UTCTime` or `GeneralizedTime`. Under the RFC 5280 profile:

- Years **1950–2049** use `UTCTime`.
- Years **2050 and later** use `GeneralizedTime`.
- Values are represented in **Zulu/UTC** with seconds and their respective standard formats.

Java returns a `Date` — an absolute UTC instant in time, **not a specific timezone string**. To avoid misinterpretation in logs/display due to machine timezone, convert:

```java
Instant start = cert.getNotBefore().toInstant();
Instant end   = cert.getNotAfter().toInstant();
System.out.println(start); // ISO-8601 UTC, ...Z format
```

This is an **inline snippet** (requires `import java.time.Instant;`). `Date.toString()` depends on the default display timezone, so two machines can print different strings while still referring to **the exact same instant**.

### 5.2 Unexpired Does Not Mean “Not Revoked”

Cases:

- Certificate **before `notBefore`**: not yet time-valid.
- Certificate **after `notAfter`**: expired in time.
- Certificate **within validity**: **passes only one time check**; it can still be revoked, signed by an untrusted CA, have the wrong service name, or have an inappropriate key usage.

Never write logic like `if (now < notAfter) allowLogin();`. It ignores `notBefore` and every remaining PKIX requirement. System clock skew can also cause inaccurate checks; synchronize clocks and use the platform's verification mechanisms.

### 5.3 Expiration Records and Certificate Rotation

If `notAfter` is approaching, the application should **renew/replace the certificate** per policy while ensuring the server deploys the leaf along with the appropriate chain. Never “edit the expiration date” of a signed certificate: `notBefore/notAfter` are inside the **CA-signed `TBSCertificate`**. Modifying them invalidates the signature.

A renewed certificate may have a **new serial**, new validity, and sometimes a new public key; do not assume identical subjects mean two certificates are the same record. If certificate inventory is needed, store the certificate fingerprint along with issuer+serial, keyId, and validity timestamps.

## 6. `X500Principal`: Standard Java Type for Distinguished Names

The `javax.security.auth.x500.X500Principal` API represents an **X.500 DN**, replacing ad-hoc string parsing or the older `getSubjectDN()/getIssuerDN()` interfaces.

Two key methods on `X509Certificate`:

```java
X500Principal subject = cert.getSubjectX500Principal();
X500Principal issuer  = cert.getIssuerX500Principal();
```

This is an **inline snippet** inside a method that already has `cert` and imports `X500Principal`.

### 6.1 Display Formats

`X500Principal` provides:

| API | Meaning |
| --- | --- |
| `getName()` | Returns an **RFC2253** string |
| `getName(X500Principal.RFC2253)` | RFC2253 format for integrations requiring text DNs |
| `getName(X500Principal.RFC1779)` | Friendly/RFC1779-style representation |
| `getName(X500Principal.CANONICAL)` | Canonical string used for `X500Principal` equality comparison |
| `getEncoded()` | **ASN.1 DER** encoding of the **Name**, not the entire certificate |
| `new X500Principal(byte[])` | Parses a **DER-encoded DN** |
| `equals(...)` | Compares using **canonical DN** as defined by Java |

Important: **RFC2253 is a DN text format, not a trust algorithm**. If you need to check whether two DNs are equal, prefer `X500Principal.equals(...)` with its defined semantics rather than `String.equalsIgnoreCase(...)` on differently formatted strings.

Canonical strings are useful for logging/lookup, yet **do not turn subject/issuer into access authentication**. Two CAs with the same DN string are still not the same trusted CA if their signatures/trust differ.

### 6.2 RDNs Are Ordered; Values May Have Escaped Characters

A DN can contain commas, plus signs, or international characters in values:

```text
CN=Service\, QA,O=Example Lab,C=VN
```

If you split on commas, you break `CN=Service, QA` into two invalid parts.

Additional notes:

- A DN can have **multi-valued RDNs** joined by `+`.
- Commas inside values must be properly escaped under RFC2253 representation.
- Some attribute types are represented by **numeric OIDs**, not necessarily readable keywords.
- `getName(CANONICAL)` provides a canonical representation for comparison; do not rely on “pretty” text ordering for identity policies.
- If you must query CN/O/OU individually, use a standards-compliant DN parser (e.g., an appropriate LDAP/X.500 library), **never split manually** and never perform authorization based on the CN string.

### 6.3 Practice 1: Creating, Formatting, and Round-Tripping `X500Principal`

File **`X500PrincipalNamesDemo.java`**, running on Java 17+:

```java
import javax.security.auth.x500.X500Principal;

public class X500PrincipalNamesDemo {
    public static void main(String[] args) {
        X500Principal original = new X500Principal(
                "CN=Service\\, QA,O=Example Lab,C=VN");
        X500Principal fromDer = new X500Principal(original.getEncoded());
        X500Principal different = new X500Principal(
                "CN=Another Service,O=Example Lab,C=VN");

        String rfc2253 = original.getName(X500Principal.RFC2253);
        String canonical = original.getName(X500Principal.CANONICAL);
        System.out.println("RFC2253 escaped comma: " + rfc2253.contains("\\,"));
        System.out.println("DER round trip equal: " + original.equals(fromDer));
        System.out.println("canonical stable: " +
                canonical.equals(fromDer.getName(X500Principal.CANONICAL)));
        System.out.println("different DN unequal: " + !original.equals(different));
    }
}
```

Compile/run commands:

```bash
javac --release 17 X500PrincipalNamesDemo.java
java X500PrincipalNamesDemo
```

Verified output:

```text
RFC2253 escaped comma: true
DER round trip equal: true
canonical stable: true
different DN unequal: true
```

Explanation:

1. The Java string literal requires `\\,` to pass a single `\` before the comma to the DN parser; without escaping, the comma would be interpreted as an RDN separator.
2. `getEncoded()` produces the DER bytes of **just the DN**; reconstructing `new X500Principal(bytes)` preserves name semantics.
3. `equals` returns true for two objects representing the same DN. It does not check any certificate signature or issuer trustworthiness.
4. The DN `CN=Another Service,...` differs in subject → not equal to the original.
5. The program does not “extract just CN” with string split because that is not a safe way to process X.500 structures.

**Do not confuse `X500Principal.getEncoded()` with `X509Certificate.getEncoded()`**: one is the DER of the **DN**, the other is the DER of the **entire certificate**.

## 7. Practice 2: Reading a Certificate from PEM in Java 17

A practical way to study these fields is using JDK's `keytool` to generate **a self-signed lab certificate** and reading it via `CertificateFactory.getInstance("X.509")`. For example, create a 2048-bit RSA key for illustration with subject/issuer `CN=localhost,O=Example Lab,C=VN`, SAN `DNS:localhost`, and 30-day validity from issuance. **Never use lab certificates as production certificates or trusted roots.**

### 7.1 Generating a Certificate Fixture with `keytool`

In an **empty directory dedicated to this lab**, run the following commands with a JDK containing `keytool`:

```bash
keytool -genkeypair -alias lesson -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=localhost,O=Example Lab,C=VN" -validity 30 -keystore sample.p12 -storetype PKCS12 -storepass changeit -keypass changeit -ext SAN=dns:localhost -noprompt

keytool -exportcert -alias lesson -keystore sample.p12 -storetype PKCS12 -storepass changeit -rfc -file sample-cert.pem
```

- `sample.p12` contains the **lab private key** and certificate; **never commit, share, or deploy** it to real systems. The password `changeit` is strictly a test password, **not a production password**.
- `sample-cert.pem` contains only the **public certificate** and can be read by `CertificateFactory`.
- `-rfc` produces a PEM representation (`-----BEGIN CERTIFICATE-----` + Base64 of DER); Java parses it via `CertificateFactory("X.509")`.
- `-validity 30` simply gives the lab an unexpired certificate at creation time; if you re-run the program after 30 days, `checkValidity()` will report expiration as expected.

You can visually inspect it with:

```bash
keytool -printcert -file sample-cert.pem
```

The serial value and timestamps **differ across runs**. Do not copy a random serial from one run as a stable assertion across machines.

### 7.2 Java Code Reading the Five Fields

Create **`X509CertificateFieldsDemo.java`**:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.time.Instant;
import javax.security.auth.x500.X500Principal;

public class X509CertificateFieldsDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: java X509CertificateFieldsDemo <cert.pem>");
        }
        X509Certificate certificate;
        try (InputStream in = Files.newInputStream(Path.of(args[0]))) {
            certificate = (X509Certificate) CertificateFactory
                    .getInstance("X.509").generateCertificate(in);
        }

        X500Principal subject = certificate.getSubjectX500Principal();
        X500Principal issuer = certificate.getIssuerX500Principal();
        String serialHex = certificate.getSerialNumber().toString(16);
        Instant notBefore = certificate.getNotBefore().toInstant();
        Instant notAfter = certificate.getNotAfter().toInstant();

        certificate.checkValidity();
        System.out.println("subject: " + subject.getName(X500Principal.RFC2253));
        System.out.println("issuer: " + issuer.getName(X500Principal.RFC2253));
        System.out.println("serial positive: " +
                (certificate.getSerialNumber().signum() > 0));
        System.out.println("serial hex nonempty: " + !serialHex.isEmpty());
        System.out.println("validity ordered: " + notBefore.isBefore(notAfter));
        System.out.println("valid now: true");
        System.out.println("self-issued names: " + subject.equals(issuer));
        certificate.verify(certificate.getPublicKey());
        System.out.println("self-signature verifies: true");
        System.out.println("SAN extension present: " +
                (certificate.getSubjectAlternativeNames() != null));
    }
}
```

Compile and run after creating `sample-cert.pem` in the same directory:

```bash
javac --release 17 X509CertificateFieldsDemo.java
java X509CertificateFieldsDemo sample-cert.pem
```

Output verified on a JDK with a compatible keytool:

```text
subject: CN=localhost,O=Example Lab,C=VN
issuer: CN=localhost,O=Example Lab,C=VN
serial positive: true
serial hex nonempty: true
validity ordered: true
valid now: true
self-issued names: true
self-signature verifies: true
SAN extension present: true
```

**Explanation:**

1. `CertificateFactory.getInstance("X.509").generateCertificate(...)` parses the PEM/DER certificate; cast to `X509Certificate` to use specialized APIs. **Parsing success does not create trust**.
2. `getSubjectX500Principal` and `getIssuerX500Principal` return properly typed DNs; since the fixture is self-signed, subject and issuer **match**.
3. `getSerialNumber()` reads the `BigInteger` assigned by `keytool`; the example checks positivity and non-empty hex for stable stdout rather than printing a specific serial.
4. `getNotBefore().toInstant()` and `getNotAfter().toInstant()` read the two timestamps; the program checks ordering and calls `checkValidity()` at runtime.
5. `certificate.verify(certificate.getPublicKey())` **only** checks the signature using the key inside the certificate; in the self-signed fixture, it succeeds. **It does not turn the certificate into a trusted root**, nor does it check PKIX path/hostname/revocation.
6. `getSubjectAlternativeNames()!=null` confirms the fixture has a SAN extension; **it does not verify localhost according to TLS standards**.

The example intentionally prints stable assertions rather than exact serial and timestamps because those two fields change each time `keytool` creates a certificate. In an inventory application, you can log **serial hex and ISO timestamps** per system data policy:

```java
String serial = certificate.getSerialNumber().toString(16);
Instant validFrom = certificate.getNotBefore().toInstant();
Instant validUntil = certificate.getNotAfter().toInstant();
```

This is an **inline snippet** inside a method that already has `certificate` of type `X509Certificate` and imports `Instant`. Never use these values for access-control decisions without PKIX policy verification.

## 8. Practice 3: Checking Exact Validity Boundaries

You can use `checkValidity(Date)` to test **the same certificate** at multiple points in time, independent of the machine's current date. With the 30-day fixture from the previous step, we test:

- 1 second **before `notBefore`** → `CertificateNotYetValidException`.
- **Midpoint** of the validity interval → time-valid.
- 1 second **after `notAfter`** → `CertificateExpiredException`.

Create **`X509ValidityBoundsDemo.java`**:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertificateExpiredException;
import java.security.cert.CertificateFactory;
import java.security.cert.CertificateNotYetValidException;
import java.security.cert.X509Certificate;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;

public class X509ValidityBoundsDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: java X509ValidityBoundsDemo <cert.pem>");
        }
        X509Certificate cert;
        try (InputStream in = Files.newInputStream(Path.of(args[0]))) {
            cert = (X509Certificate) CertificateFactory
                    .getInstance("X.509").generateCertificate(in);
        }

        Instant from = cert.getNotBefore().toInstant();
        Instant to = cert.getNotAfter().toInstant();
        Instant midpoint = from.plusMillis(Duration.between(from, to).toMillis() / 2);

        boolean earlierRejected = false;
        try {
            cert.checkValidity(Date.from(from.minusSeconds(1)));
        } catch (CertificateNotYetValidException expected) {
            earlierRejected = true;
        }
        cert.checkValidity(Date.from(midpoint));

        boolean laterRejected = false;
        try {
            cert.checkValidity(Date.from(to.plusSeconds(1)));
        } catch (CertificateExpiredException expected) {
            laterRejected = true;
        }

        System.out.println("before notBefore rejected: " + earlierRejected);
        System.out.println("midpoint accepted: true");
        System.out.println("after notAfter rejected: " + laterRejected);
    }
}
```

Compile and run:

```bash
javac --release 17 X509ValidityBoundsDemo.java
java X509ValidityBoundsDemo sample-cert.pem
```

Verified output:

```text
before notBefore rejected: true
midpoint accepted: true
after notAfter rejected: true
```

Significance:

- Independent of display timezone because `Instant` and `Date.from` both represent **absolute instants**.
- Catching the two distinct exceptions separates the **validity boundary** reasons.
- `midpoint` is computed from the certificate's own validity bounds and falls between the fixture's two boundaries.
- Checking **at a simulated timestamp** is useful for unit tests and expiry testing, but **never pass an arbitrary past date to “bypass expiration” of a certificate in a live TLS connection**.
- A passing `checkValidity` call still does not verify trust chain, revocation, or service identity.

## 9. From X.509 Fields to Real Certificate Verification

A minimal diagram:

```text
certificate bytes (PEM/DER)
           |
           v
CertificateFactory: parse X.509 structure
           |
           v
Read subject / issuer / serial / validity
           |
           v
       checkValidity
           |
           v
  Only metadata and timestamps are known
           |
           +--> CA signature not yet proven valid
           +--> Trusted trust anchor not yet found
           +--> policy/KU/EKU/name constraints not yet checked
           +--> hostname/SAN not yet checked
           +--> revocation not yet evaluated
```

To verify the full path in Java, the relevant APIs include `CertPathValidator`, `PKIXParameters`, `TrustAnchor`, and TLS `TrustManager` components, usually invoked by configured TLS/HTTPS libraries. **Never build your own verification policy out of DN strings and expiration dates**.

Important boundaries:

1. **`getIssuerX500Principal()` does not retrieve the CA public key.** The issuer name is just a field. The CA public key must come from a verified chain/trust anchor.
2. **`certificate.verify(publicKey)` does not build a chain**. It only checks the current certificate's signature against **the supplied key**; if you take that key from untrusted input, the signature check can pass without any trust.
3. **`checkValidity()` does not check revocation**. An unexpired certificate may still have been revoked by the CA.
4. **Subject DN does not replace SAN** in modern TLS hostname verification.
5. **Issuer + serial** is useful for referencing in PKI/revocation, yet **does not replace issuer/trust verification**.
6. **`X500Principal.equals(...)` only compares DN identity** via canonical strings; it does not verify public keys or certificates.

### 9.1 How to Look Up a Certificate by Issuer + Serial?

In an inventory or CRL system, the business key can consist of:

```text
(canonical issuer DN, certificate serial BigInteger)
```

This matches per-issuer serial uniqueness under RFC 5280. However, in multi-PKI databases, pair it with an **issuer key identifier or certificate fingerprint** when needed to reduce ambiguity between CAs with similar names; certificate acceptance must still rely on chain and policy validation.

If you only have RFC1779/2253 text representations, do not compare them with `String.equalsIgnoreCase`. Use standard `X500Principal` and key/chain metadata per protocol.

### 9.2 Distinguishing Certificate Serial from Certificate Fingerprint

- **Serial number** is assigned by the CA and is unique **within the issuer's scope**.
- **Fingerprint** (e.g., SHA-256 over the entire DER certificate) is a digest of **the certificate bytes themselves**. It is useful for file identification/comparison or policy-based pinning, not as a serial.
- A certificate parsed from PEM or DER has the same internal DER bytes (`getEncoded()`), so a proper DER fingerprint does not depend on PEM wrapper whitespace.
- A fingerprint is not automatically a trust anchor: accepting a fingerprint is a **policy decision** and requires update/rotation procedures.

## 10. Common Mistakes and Fixes

| Mistake | Why is it wrong? | Correct approach |
| --- | --- | --- |
| “Issuer has a famous CA name, so it is trusted.” | Names can be spoofed; signature/chain not verified. | Use PKIX/trust store. |
| “`subject.equals(issuer)` = trusted certificate.” | That is only **self-issued** by name. | Distinguish self-issued, self-signed, trust anchor. |
| “CN is the DNS hostname.” | Modern TLS matches identity via SAN, not CN fallback. | Use TLS hostname verification per RFC 9525. |
| “Serials are globally unique.” | Serials are unique **per CA/issuer**. | Combine issuer + serial and trust metadata. |
| “The serial is in subject `SERIALNUMBER=...`.” | That is a **different DN attribute**. | `getSerialNumber()` for the certificate serial. |
| “Serial is small; cast `longValue()` for convenience.” | Can lose bits / collide. | Keep `BigInteger`. |
| “Every subject has a CN.” | Subject may be empty; SAN may carry all identifiers. | Use `getSubjectX500Principal`, process SAN. |
| “Split DN by commas.” | Commas can be escaped inside values. | Use an X.500/DN parser. |
| “Compare DN text character by character.” | Formats and escaping/canonicalization differ. | Use `X500Principal.equals` with proper semantics. |
| “Expiration only needs `notAfter`.” | There is also `notBefore` and many other PKIX checks. | Use `checkValidity` + path validation. |
| “`checkValidity()` = completely valid certificate.” | Checks only timestamps. | Check signature/chain/trust/policy/revocation/identity. |
| “`Date.toString()` in local time is the certificate's canonical date.” | Display timezone varies, instant does not. | Use `toInstant()` and ISO-8601 UTC. |
| “A certificate self-signed with a valid key is a trusted root.” | Proving self-signing does not mean trust. | Only accept managed trust anchors. |
| “Dates/subjects in a DER certificate can be edited.” | Those fields are signed by the CA in TBS. | Re-issue/renew a new certificate. |

## 11. Diagnostic Workflow for “Certificate Rejected”

A Java log saying “certificate expired”, “PKIX path building failed”, or “No subject alternative names matching” can originate from **different verification layers**. To analyze:

1. **Parse certificate**: Did `CertificateFactory` read PEM/DER properly? Was a private key file mistaken for a certificate?
2. **Subject/issuer**: Print DNs using `getSubjectX500Principal().getName(RFC2253)` and the corresponding issuer; never treat names as trust.
3. **Serial**: Retrieve `BigInteger`/hex to look up in CA/CRL or inventory, without mixing it up with the DN's `SERIALNUMBER`.
4. **Validity**: Check `notBefore` and `notAfter` in UTC; inspect machine/server clock, NTP, and evaluation time.
5. **Signature/chain**: Is the leaf → intermediate → trust anchor chain complete, do issuer DNs chain properly, and do signatures verify with the exact CA keys?
6. **Policy**: Do BasicConstraints, KeyUsage, ExtendedKeyUsage, name constraints, and algorithms satisfy the application?
7. **Revocation**: Is CRL/OCSP configured and is the status acceptable under policy?
8. **TLS service identity**: Does SAN have a DNS/IP matching the accessed service name? Was hostname verification disabled?
9. **If custom code is used**: verify it **does not** merely compare subject strings, validity, or serials and bypass the trust manager.

Never log private keys, tokens, or secret contents. Public certificates are generally non-secret, yet can still contain identifying information; apply organizational logging and access-control policies.

## 12. Self-Check Exercises

**Question 1.** How do subject and issuer differ?  
**Answer:** Subject identifies the entity bound to the public key; issuer identifies the CA entity that issued/signed the certificate.

**Question 2.** Is `CN=example.com` in the subject enough for a Java TLS client to trust `https://example.com`?  
**Answer:** No. Trust chain/policy and service identity via SAN must be verified according to modern TLS mechanisms.

**Question 3.** Can two different CAs issue the same serial number `42`?  
**Answer:** Yes. Serials are unique **within each issuer/CA**, not across the entire Internet.

**Question 4.** Is `SERIALNUMBER=ASSET-123` in the subject DN the same as `getSerialNumber()`?  
**Answer:** No. One is an AVA/OID in the DN, while the other is the CA-assigned certificate serial number.

**Question 5.** When encountering `CertificateNotYetValidException` vs. `CertificateExpiredException`, how do they differ?  
**Answer:** Evaluation time is before `notBefore` versus after `notAfter`.

**Question 6.** If `cert.checkValidity()` returns normally, does that prove the certificate is trusted?  
**Answer:** No; it only checked the certificate's validity window at the current time.

**Question 7.** Why is `X500Principal` better than `String.split(",")`?  
**Answer:** DNs have ASN.1/RDN syntax, escaped commas, multi-valued RDNs, OIDs, and canonical forms; naive string splitting does not understand the structure.

**Question 8.** What is a certificate with `subject == issuer`?  
**Answer:** **Self-issued** by name. Signature verification is still needed to determine self-signed status, and a trust policy is still required.

**Question 9.** Does `getNotAfter()` return a `Date` in Vietnam timezone or UTC?  
**Answer:** It represents an **absolute instant**; `Date.toString()` formatting depends on the machine timezone. Convert via `toInstant()` for clear UTC display.

**Question 10.** Why can a subject DN be empty?  
**Answer:** RFC 5280 allows the subject to be identified via SAN; when the subject DN is empty, SAN must be present and marked critical.

## Summary

```text
X509Certificate
  ├─ getSubjectX500Principal() -> subject DN
  ├─ getIssuerX500Principal()  -> issuer DN
  ├─ getSerialNumber()         -> BigInteger (unique per issuer)
  ├─ getNotBefore()            -> Date -> Instant
  ├─ getNotAfter()             -> Date -> Instant
  └─ checkValidity([Date])     -> checks time interval only

X500Principal
  ├─ getName(RFC2253/CANONICAL) -> DN representation
  ├─ getEncoded()               -> DER of the Name
  └─ equals(...)                -> canonical DN comparison

Issuer + serial + validity + subject
  = essential information about the certificate
  ≠ complete signature/PKIX/hostname/revocation verification
```

Key takeaway: **subject** is the entity's name, **issuer** is the issuing party's name, **serial** is unique **per CA**, **notBefore/notAfter** define the time window; `X500Principal` handles structured DNs. When deciding whether to **trust** a certificate, use **PKIX and service authentication policies** rather than descriptive fields in isolation.

## Official References

- [Java 17 — X509Certificate API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html): subject, issuer, serial, validity, SAN, and `checkValidity`.
- [Java 17 — X500Principal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/x500/X500Principal.html): DN, RFC2253/RFC1779/CANONICAL, DER, and `equals`.
- [Java 17 — CertificateFactory API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertificateFactory.html): reading PEM/DER certificates.
- [RFC 5280 `4.1.2.2–`4.1.2.6](https://www.rfc-editor.org/rfc/rfc5280#section-4.1.2.2): serial number, issuer, validity, subject, and empty/critical SAN rules.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): TLS service identity based on SAN, superseding RFC 6125.
- [Java 17 — CertPathValidator API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html): validating certification paths instead of merely inspecting DN/Date.
