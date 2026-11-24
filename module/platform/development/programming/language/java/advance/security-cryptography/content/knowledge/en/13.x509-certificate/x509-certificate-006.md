# 13.6 KeyUsage, ExtendedKeyUsage, BasicConstraints, and Critical Extensions

## 1. Why Do X.509 Certificates Need Extensions That Restrict Permissions?

An **X.509 v3** certificate binds a *public key* with a subject, issuing organization, validity period, signature, and various usage conditions. The CA's signature confirms the certificate contents were not altered and were issued by the CA, yet **does not automatically permit using the key for every purpose**. A certificate issued to authenticate a TLS server, sign application code, authenticate a client, or **sign CA certificates** typically requires **different** constraints.

Three key extensions in this lesson:

1. **KeyUsage (KU, OID `2.5.29.15`):** the **basic cryptographic operation groups** the public key in the certificate is allowed to perform, expressed as bits such as `digitalSignature`, `keyEncipherment`, and `keyCertSign`.
2. **ExtendedKeyUsage (EKU, OID `2.5.29.37`):** the permitted **application/protocol purposes**, expressed as a list of OIDs such as TLS server authentication or client authentication.
3. **BasicConstraints (BC, OID `2.5.29.19`):** whether the subject is a **Certificate Authority (CA)** authorized to issue certificates and the depth of subordinate CAs (`pathLenConstraint`).

Each extension also carries a **critical** flag. If an extension is marked critical, the verifier must **understand and properly enforce the semantics** of that extension, or **reject the certificate** when no approved mechanism exists to handle it. This flag **does not mean the certificate is trusted, stronger, or has higher privileges**.

### 1.1 A Certificate with a Valid Signature Can Still Be Rejected

Suppose a trusted CA issued a certificate for `service.example.test`:

- `KeyUsage` does not allow `digitalSignature`, while a TLS 1.3 handshake requires the server to use the key to sign the handshake.
- Or EKU contains only `clientAuth`, omitting `serverAuth` required by the application profile.
- Or the certificate has a custom critical extension that the verifier does not understand.
- Or an intermediate certificate is used as a CA even though `BasicConstraints.cA=false`.
- Or SAN does not match the accessed DNS name; or the certificate is expired, revoked, or does not chain to an accepted trust anchor.

In every case, **checking only the cryptographic signature on the certificate is insufficient** to decide “allow use as a TLS server”. You must perform **PKIX path validation, identity/hostname validation, usage validation, algorithm policy checks, and (when required) revocation checking** per protocol.

## 2. Extension Structure in X.509 v3

Each extension has roughly this ASN.1 structure:

```text
Extension ::= SEQUENCE {
    extnID      OBJECT IDENTIFIER,
    critical    BOOLEAN DEFAULT FALSE,
    extnValue   OCTET STRING
}

TBSCertificate ::= SEQUENCE {
    ...,
    extensions [3] EXPLICIT Extensions OPTIONAL
}
```

- **`extnID`** identifies the extension type by OID. Standard OIDs: KU `2.5.29.15`, BC `2.5.29.19`, EKU `2.5.29.37`, SAN `2.5.29.17`.
- **`critical`** defaults to **false** if omitted in DER. It may be marked true for extensions that verifiers must strictly enforce.
- **`extnValue`** is an `OCTET STRING` containing the **inner DER encoding** of each extension type. Java's `X509Certificate.getExtensionValue(oid)` returns the bytes of the **outer DER-encoded OCTET STRING**, not a parsed Java object directly.

Never parse `getExtensionValue("2.5.29.15")` as a raw boolean array: there is ASN.1 encoding inside. For KU/EKU/BC, **use the typed APIs** on `X509Certificate`; for custom extensions, use a controlled ASN.1 decoder and an OID handling policy.

A certificate has many other extensions: `subjectAltName` (SAN), `authorityKeyIdentifier`, `subjectKeyIdentifier`, `nameConstraints`, `certificatePolicies`, `authorityInfoAccess`, CRL distribution points, etc. Do not ignore all other extensions simply because this lesson focuses on KU/EKU/BC.

## 3. KeyUsage: What Permission Does Each Bit Indicate?

Java reads `boolean[] ku = cert.getKeyUsage()`. Bits have **fixed indices** per ASN.1 and the Java API:

| Index | KU bit | Typical meaning |
| ---: | --- | --- |
| 0 | `digitalSignature` | Verifying signatures on data, entity authentication protocols, handshake signatures; **not** certificate/CRL issuance signatures |
| 1 | `nonRepudiation` / `contentCommitment` | Signatures carrying content-commitment semantics per policy, not an automatic legal guarantee |
| 2 | `keyEncipherment` | Public key used for **key wrapping/transport**, e.g., legacy RSA key transport |
| 3 | `dataEncipherment` | Direct encryption of user data with the public key in certain protocols, rare |
| 4 | `keyAgreement` | Participating in key agreement such as DH/ECDH in appropriate profiles |
| 5 | `keyCertSign` | Public key used to **verify CA certificate issuance signatures** |
| 6 | `cRLSign` | Public key used to **verify CRL signatures** |
| 7 | `encipherOnly` | Restricts purpose to “encipher only” when `keyAgreement` is set |
| 8 | `decipherOnly` | Restricts purpose to “decipher only” when `keyAgreement` is set |

**Important conditions:**

- If KU **is present**, the key must not be used outside purposes permitted by the enabled bits. If KU **is absent**, `getKeyUsage() == null`; that does not automatically mean every system should allow everything, because **EKU, profile/protocol, and local policy** can still restrict usage.
- If KU includes `keyCertSign`, BC must indicate the subject is a **CA** (`cA=true`) per RFC 5280. If BC is absent or `cA=false`, the public key **must not be used to verify certificate issuance signatures** merely because it has the `keyCertSign` bit.
- `encipherOnly` and `decipherOnly` are meaningful only when `keyAgreement` is set; using them without `keyAgreement` violates the RFC 5280 profile.
- When a CA uses a public key to sign certificates/CRLs, KU needs the corresponding `keyCertSign`/`cRLSign` bits. RFC 5280 requires the KU extension on CA certificates with those purposes and recommends marking it critical.
- **TLS 1.3** uses signatures in server certificate authentication, so `digitalSignature` is the relevant KU bit. `keyEncipherment` appears on many RSA certificates for compatibility with older TLS profiles, but **does not replace `digitalSignature` in TLS 1.3**. Exact suitability depends on TLS version, key algorithm, signature scheme, and the active profile.

For example, an RSA leaf certificate for a TLS server might have:

```text
KeyUsage: critical
  digitalSignature = true
  keyEncipherment  = true
  keyCertSign      = false
  cRLSign          = false
```

`keyEncipherment=true` does **not** make the certificate a CA and does not prove `serverAuth` EKU is present. Conversely, a CA certificate typically sets `keyCertSign` and may set `cRLSign`, while also needing BC `cA=true`.

### Java: Reading Bits Safely

```java
// Illustrative snippet inside a Java method, given X509Certificate cert.
boolean[] usage = cert.getKeyUsage(); // null if extension is absent
boolean canSignData = usage != null
        && usage.length > 0 && usage[0];
boolean canIssueCerts = usage != null
        && usage.length > 5 && usage[5];
```

This is a **strict policy** example requiring the bit to be present, rather than interpreting an absent KU as “forbid all operations” in every protocol. For profiles that allow KU to be omitted, implement the rule **“if the extension is present, it must permit the operation”** alongside any mandatory profile-specific requirements.

## 4. ExtendedKeyUsage: Application Purposes

`ExtendedKeyUsage` is a list of **KeyPurposeId OIDs**, not a bit array. Java returns `List<String>` from `cert.getExtendedKeyUsage()` (and may throw `CertificateParsingException` if malformed).

Common OIDs:

| EKU | OID | Use case |
| --- | --- | --- |
| `serverAuth` | `1.3.6.1.5.5.7.3.1` | TLS server authentication |
| `clientAuth` | `1.3.6.1.5.5.7.3.2` | TLS client authentication |
| `codeSigning` | `1.3.6.1.5.5.7.3.3` | Software code signing |
| `emailProtection` | `1.3.6.1.5.5.7.3.4` | Email/S/MIME protection per profile |
| `timeStamping` | `1.3.6.1.5.5.7.3.8` | Time-stamping authority |
| `OCSPSigning` | `1.3.6.1.5.5.7.3.9` | Authorization to sign OCSP responses |
| `anyExtendedKeyUsage` | `2.5.29.37.0` | Special OID; acceptance is governed by profile and relying-party policy |

**Combination rule:** when **both KU and EKU are present**, the intended use must comply **with both**. EKU `serverAuth` does not grant handshake signing permission if KU forbids digital signature in a profile that requires it; likewise, KU `digitalSignature` does not override an EKU listing only `clientAuth` when the application is authenticating a **server**.

**Absent EKU:** `getExtendedKeyUsage()==null` means the certificate **is not constrained by an EKU extension**; it does not mean the certificate is broken, nor **does it prove permission for use in every system**. An application or organization can explicitly require **EKU `serverAuth` to be present**; that is a policy choice and may be stricter than general baseline requirements of some profiles.

**Present EKU:** the OID list specifies the granted purposes. EKU may be marked critical **or non-critical** per RFC 5280; even when non-critical, a verifier **that recognizes** EKU must still enforce its constraints when evaluating purpose. Never treat non-critical as “can always be ignored”.

**`anyExtendedKeyUsage`:** not a “bypass all checks” button. The RFC defines this OID, yet relying parties may require an explicit purpose OID and specific profiles impose stricter rules. For TLS servers under an internal policy requiring `serverAuth`, require the explicit OID rather than inferring from `anyExtendedKeyUsage`.

### Clear Scenario: A `clientAuth` Certificate Used as a Server

```text
Leaf certificate:
  KeyUsage: digitalSignature
  ExtendedKeyUsage: clientAuth
  BasicConstraints: cA=false
  Signature: valid by a trusted CA

Result:
  Pure PKIX path validation: may PASS.
  TLS-server purpose "must have EKU serverAuth": FAIL.
```

**Why?** The PKIX `CertPathValidator` checks the chain/PKIX conditions, yet **is not itself an HTTPS hostname verifier or evaluator of every business purpose**. Developers must use properly configured trust managers/TLS subsystems; the example below intentionally separates both checks so learners see the distinction clearly.

## 5. BasicConstraints: Who Can Issue Certificates?

Structure:

```text
BasicConstraints ::= SEQUENCE {
    cA                 BOOLEAN DEFAULT FALSE,
    pathLenConstraint  INTEGER (0..MAX) OPTIONAL
}
```

- `cA=false`: the subject is not a CA issuing certificates per profile, typically an **end entity (EE)** such as a server or client certificate.
- `cA=true`: the certificate may act as a CA **if** other conditions such as `keyCertSign`, trust, algorithms, and path validation all pass.
- `pathLenConstraint`: the maximum number of **non-self-issued intermediate CA certificates** permitted after this CA in a valid path, before the end entity. Does not count the end-entity leaf. **`pathLen=0` still permits the CA to sign leaves directly**, while disallowing further non-self-issued intermediate CAs beneath it per RFC 5280.
- Absence of `pathLenConstraint` on a `cA=true` CA certificate: no CA-chain depth limit imposed by **this field itself**; the path must still obey other constraints/policies.
- RFC 5280 forbids declaring `pathLen` on a certificate with `cA=false`; and when a CA uses its key to sign certificates, BC must be present and **critical** per profile.

In Java:

```java
// Illustrative snippet: cert is X509Certificate.
int constraint = cert.getBasicConstraints();
boolean isCa = constraint >= 0;
// constraint == -1: not a CA (or BC is absent).
// constraint == 0 : CA with no non-self-issued intermediate CAs allowed after it.
// constraint > 0  : CA with the corresponding depth limit.
// constraint == Integer.MAX_VALUE : CA with no pathLen declared.
```

**Common pitfall:** Java returns `-1` both when BC **is absent** and when BC has `cA=false`; to check whether the extension is present, check `cert.getExtensionValue("2.5.29.19") != null`. `getBasicConstraints()` is a **convenience API**, not a full ASN.1 dump tool.

### CA Chain and Trust Anchor

```text
Trust anchor (configured trusted root CA)
    |
    +--- Intermediate CA (BC cA=true, KU keyCertSign)
             |
             +--- End entity / server (BC cA=false, EKU serverAuth)
```

**Never treat a certificate with `cA=true` as a trusted root automatically.** Any attacker can self-sign a `CA=true` certificate; only trust anchors provisioned via trusted configuration/PKI form the basis of trust. In Java, `TrustAnchor(rootCert,null)` explicitly **treats `rootCert` as trusted**; if you take a root file from an untrusted network and immediately pass it as a `TrustAnchor`, the entire chain check becomes meaningless.

A trust anchor may be processed differently from an intermediate certificate during path validation: many constraints on a root's self-signed certificate are not evaluated in the exact same way as certificates *within* the `CertPath`. Manage trust anchor/`PKIXParameters` policies separately rather than taking `CertPathValidator` output as proof that the root itself was vetted.

## 6. Critical Extensions: “Understand and Enforce, or Reject”

Per RFC 5280, the critical flag is set on **each extension**, not as a certificate-wide flag.

| Situation | Proper verifier behavior |
| --- | --- |
| Extension is **critical** and understood/handled | Apply its constraints within the PKIX/application context |
| Extension is **critical** with no checker handling it | **Reject the certificate/path** |
| Extension is **non-critical** and unrecognized | May ignore the unknown extension per profile |
| Extension is **non-critical**, recognized, and purpose-related (e.g., EKU) | Must not arbitrarily skip enforcing constraints when checking usage |
| Familiar critical extensions present, yet key usage/purpose is inappropriate | **Still reject** even though the parser understands the extension |
| No unknown critical extensions, yet chain/hostname is wrong | **Still reject**; criticality does not replace PKIX/identity validation |

For example:

```text
Certificate A:
  Critical: KeyUsage (2.5.29.15)
  Noncritical: ExtendedKeyUsage (2.5.29.37)
  Outcome: verifier understands KU and checks EKU purpose -> may be valid.

Certificate B:
  Critical: 1.2.3.4.5 (custom OID handled by no one)
  Outcome: X.509 parser reads the file, yet PKIX must reject the path.

Certificate C:
  Noncritical: 1.2.3.4.5
  Outcome: PKIX may ignore the unknown OID if other checks pass.
```

### Related Java APIs

| API | Returns | Notes |
| --- | --- | --- |
| `getCriticalExtensionOIDs()` | `Set<String>` of critical OIDs; may be `null` | Does not itself tell whether the extension was **processed properly** |
| `getNonCriticalExtensionOIDs()` | `Set<String>` of non-critical OIDs | Used to inspect labels, not a substitute for extension semantics |
| `hasUnsupportedCriticalExtension()` | `boolean` | Only reflects support reported by the implementation; **insufficient to replace PKIX/purpose validation** |
| `getExtensionValue(oid)` | DER `byte[]` of the outer OCTET STRING, or `null` | Not a typed parse result; must decode ASN.1 at the proper layer |
| `getKeyUsage()` | `boolean[]` or `null` | Fixed bits 0..8 |
| `getExtendedKeyUsage()` | `List<String>` or `null` | OIDs, not friendly names |
| `getBasicConstraints()` | `int` | `-1` for end entity/not CA; CA value is path length |
| `checkValidity()` | Void when dates are valid | Time only; does not check chain/trust/purpose |

Use `CertificateFactory` to parse certificates, `CertPathValidator.getInstance("PKIX")` to check a `CertPath` against configured trust anchors, and TLS trust managers/hostname verifiers for HTTPS. `certificate.verify(issuerPublicKey)` checks only **the certificate's signature**, without automatically verifying CA chain, KU/EKU, critical extensions, SAN, validity, or revocation.

## 7. Creating a Demo Certificate Set with keytool (Java 17+)

So the example **does not depend on external CAs or secret files**, use JDK's bundled `keytool` to generate a **self-signed test certificate** and leaf certificates signed by the test CA. All key material is strictly for learning.

Use **PowerShell 5.1+ on Windows** or PowerShell 7+; run within a single PowerShell session and save the Java source from section 8 as `X509ExtensionsDemo.java` in the working directory.

**Never use the sample password `changeit` or this test root CA in production.** The demo script creates `root.p12` containing the CA private key in a temporary directory; protect/delete that directory and never commit it to a repository. These certificates **do not belong to any public CA and are not trusted outside the demo program**.

```powershell
# Create a temporary directory and DEMO password. Run consecutively in the same PowerShell session.
$t = Join-Path $env:TEMP ("x509-extension-demo-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $t | Out-Null
$pw = "changeit"

# Root CA: BasicConstraints critical, CA=true, pathLen=0;
# KeyUsage critical, allowing certificate and CRL signing.
keytool -genkeypair -alias root -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=Example Test Root" -validity 365 -storetype PKCS12 -keystore (Join-Path $t "root.p12") -storepass $pw -keypass $pw -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign" -noprompt

# Leaf generates key and CSR; not yet a CA-signed certificate.
keytool -genkeypair -alias leaf -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=service.example.test" -validity 30 -storetype PKCS12 -keystore (Join-Path $t "leaf.p12") -storepass $pw -keypass $pw -noprompt
keytool -certreq -alias leaf -keystore (Join-Path $t "leaf.p12") -storepass $pw -file (Join-Path $t "leaf.csr")

# Export root certificate (not the private key).
keytool -exportcert -alias root -keystore (Join-Path $t "root.p12") -storepass $pw -rfc -file (Join-Path $t "root.pem")

# Common parameters for 4 leaf certificates signed by root.
$base = @("-gencert", "-alias", "root",
  "-keystore", (Join-Path $t "root.p12"), "-storepass", $pw,
  "-infile", (Join-Path $t "leaf.csr"), "-validity", "30", "-rfc",
  "-ext", "KU:critical=digitalSignature,keyEncipherment",
  "-ext", "BC=ca:false", "-ext", "SAN=dns:service.example.test")

# Valid server for demo purpose.
& keytool @base -outfile (Join-Path $t "server.pem") -ext "EKU=serverAuth"

# Critical custom OID: standard validator cannot process it.
& keytool @base -outfile (Join-Path $t "critical.pem") -ext "EKU=serverAuth" -ext "1.2.3.4.5:critical=0101FF"

# Same custom OID non-critical: validator can ignore it.
& keytool @base -outfile (Join-Path $t "noncritical.pem") -ext "EKU=serverAuth" -ext "1.2.3.4.5=0101FF"

# Certificate with only EKU clientAuth, no serverAuth.
& keytool @base -outfile (Join-Path $t "client.pem") -ext "EKU=clientAuth"
```

The `-gencert` commands output leaf certificates signed by root. The option `-ext "1.2.3.4.5:critical=0101FF"` represents a simulated custom OID for this lesson with a small DER value. Do not use arbitrary OIDs like this when designing production extensions; use registered OIDs/schemas and proper handlers.

`keytool` commands may print certificate creation messages to stderr/stdout depending on the JDK; the **exact stdout** listed in section 8 is the output of **the `java` command**, excluding `keytool` messages. If your environment lacks `keytool`, install a supported JDK. When running on macOS/Linux, translate the PowerShell script into equivalent shell syntax, while `keytool` arguments and certificate semantics remain unchanged.

## 8. Java 17+ Program: Reading KU/EKU/BC and Testing Critical vs. Non-Critical

The following program uses **only Java SE** to:

1. Read PEM certificates using `CertificateFactory("X.509")`.
2. Inspect CA `BasicConstraints.cA=true`, `pathLen=0`, KU `keyCertSign`, and BC `critical`.
3. Inspect leaf `cA=false`, KU `digitalSignature/keyEncipherment`, EKU `serverAuth`, critical KU, and non-critical EKU.
4. Set up a test CA trust anchor **intentionally trusted within the demo scope**, build a `CertPath` for the leaf, and call `CertPathValidator("PKIX")`.
5. Compare certificates with a custom OID **critical vs. non-critical**: critical is rejected, while non-critical is accepted by PKIX when all other checks pass.
6. Compare a certificate with only `clientAuth`: pure PKIX path validation still accepts it, yet the separate *server purpose* check rejects it.

Save as **`X509ExtensionsDemo.java`**:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertPathValidatorException;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.Collection;
import java.util.List;
import java.util.Set;

public final class X509ExtensionsDemo {
    private static final String KU = "2.5.29.15";
    private static final String EKU = "2.5.29.37";
    private static final String BC = "2.5.29.19";
    private static final String SERVER_AUTH = "1.3.6.1.5.5.7.3.1";
    private static final String CUSTOM = "1.2.3.4.5";

    private static X509Certificate read(String path) throws Exception {
        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        try (InputStream in = Files.newInputStream(Path.of(path))) {
            return (X509Certificate) factory.generateCertificate(in);
        }
    }

    private static boolean bit(boolean[] bits, int index) {
        return bits != null && bits.length > index && bits[index];
    }

    private static boolean has(Set<String> oids, String oid) {
        return oids != null && oids.contains(oid);
    }

    private static boolean hasDnsSan(X509Certificate certificate,
                                     String host) throws Exception {
        Collection<List<?>> names = certificate.getSubjectAlternativeNames();
        if (names == null) return false;
        for (List<?> item : names) {
            if (item.size() >= 2 && Integer.valueOf(2).equals(item.get(0))
                    && item.get(1) instanceof String dns
                    && host.equalsIgnoreCase(dns)) {
                return true;
            }
        }
        return false;
    }

    private static boolean pkixAccepts(X509Certificate root,
                                       X509Certificate leaf) throws Exception {
        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        CertPath path = factory.generateCertPath(List.of(leaf));
        PKIXParameters params = new PKIXParameters(
                Set.of(new TrustAnchor(root, null)));
        params.setRevocationEnabled(false); // Test fixture only.
        try {
            CertPathValidator.getInstance("PKIX").validate(path, params);
            return true;
        } catch (CertPathValidatorException rejected) {
            return false;
        }
    }

    private static boolean demoServerPurpose(X509Certificate certificate)
            throws Exception {
        List<String> purposes = certificate.getExtendedKeyUsage();
        return certificate.getBasicConstraints() == -1
                && bit(certificate.getKeyUsage(), 0)
                && purposes != null
                && purposes.contains(SERVER_AUTH)
                && hasDnsSan(certificate, "service.example.test");
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 5) {
            throw new IllegalArgumentException(
                    "Usage: java X509ExtensionsDemo root.pem server.pem "
                    + "critical.pem noncritical.pem client.pem");
        }
        X509Certificate root = read(args[0]);
        X509Certificate server = read(args[1]);
        X509Certificate unknownCritical = read(args[2]);
        X509Certificate unknownNoncritical = read(args[3]);
        X509Certificate client = read(args[4]);

        root.checkValidity();
        server.checkValidity();
        System.out.println("rootIsCa=" + (root.getBasicConstraints() >= 0));
        System.out.println("rootPathLen=" + root.getBasicConstraints());
        System.out.println("rootKeyCertSign=" + bit(root.getKeyUsage(), 5));
        System.out.println("rootBcCritical=" + has(
                root.getCriticalExtensionOIDs(), BC));

        System.out.println("leafIsEndEntity="
                + (server.getBasicConstraints() == -1));
        System.out.println("leafDigitalSignature="
                + bit(server.getKeyUsage(), 0));
        System.out.println("leafKeyEncipherment="
                + bit(server.getKeyUsage(), 2));
        System.out.println("leafServerAuthEku="
                + server.getExtendedKeyUsage().contains(SERVER_AUTH));
        System.out.println("leafKuCritical=" + has(
                server.getCriticalExtensionOIDs(), KU));
        System.out.println("leafEkuNonCritical=" + has(
                server.getNonCriticalExtensionOIDs(), EKU));
        System.out.println("serverPkixAccepted="
                + pkixAccepts(root, server));
        System.out.println("serverPurposeForDemo="
                + demoServerPurpose(server));

        System.out.println("unknownCriticalDeclared=" + has(
                unknownCritical.getCriticalExtensionOIDs(), CUSTOM));
        System.out.println("unknownCriticalRejected="
                + !pkixAccepts(root, unknownCritical));
        System.out.println("unknownNoncriticalDeclared=" + has(
                unknownNoncritical.getNonCriticalExtensionOIDs(), CUSTOM));
        System.out.println("unknownNoncriticalAccepted="
                + pkixAccepts(root, unknownNoncritical));

        System.out.println("clientOnlyPkixAccepted="
                + pkixAccepts(root, client));
        System.out.println("clientOnlyServerPurpose="
                + demoServerPurpose(client));
    }
}
```

Compile and run (in **the same PowerShell session** that still holds `$t`):

```powershell
javac --release 17 -encoding UTF-8 X509ExtensionsDemo.java
java X509ExtensionsDemo (Join-Path $t "root.pem") (Join-Path $t "server.pem") (Join-Path $t "critical.pem") (Join-Path $t "noncritical.pem") (Join-Path $t "client.pem")
```

**Verified output** on JDK 17+ with standard PKIX/keytool providers:

```text
rootIsCa=true
rootPathLen=0
rootKeyCertSign=true
rootBcCritical=true
leafIsEndEntity=true
leafDigitalSignature=true
leafKeyEncipherment=true
leafServerAuthEku=true
leafKuCritical=true
leafEkuNonCritical=true
serverPkixAccepted=true
serverPurposeForDemo=true
unknownCriticalDeclared=true
unknownCriticalRejected=true
unknownNoncriticalDeclared=true
unknownNoncriticalAccepted=true
clientOnlyPkixAccepted=true
clientOnlyServerPurpose=false
```

After finishing the lesson, remove the demo private keys/certificates in the temporary directory:

```powershell
# Run only when $t is indeed the newly created DEMO directory containing nothing you need to keep.
if ($t -like (Join-Path $env:TEMP "x509-extension-demo-*")) {
    Remove-Item -LiteralPath $t -Recurse -Force
}
```

**Warning:** normal file deletion is not secure erasure from SSDs/snapshots/backups. Test fixtures must never use real keys; the created directory is strictly for practice.

### 8.1 Why Does Each Group of Results Matter?

**`rootIsCa=true`, `rootPathLen=0`, `rootKeyCertSign=true`:** the test root has BC `CA=true`, forbids non-self-issued intermediate CAs beneath it, yet can still sign end-entity leaves directly. `rootBcCritical=true` confirms the critical flag on BC is present in the fixture.

**`leafIsEndEntity=true`:** `getBasicConstraints() == -1` shows Java treats the leaf as not a CA. **Never** use a leaf to sign child certificates even if its key is technically capable of generating an RSA signature.

**`leafDigitalSignature=true` and `leafKeyEncipherment=true`:** both KU permissions are enabled in the fixture. That does not mean the leaf has `keyCertSign` permission; that is a separate permission at bit 5.

**`leafServerAuthEku=true`, `leafKuCritical=true`, `leafEkuNonCritical=true`:** confirms `serverAuth` EKU was issued, KU is marked critical, and EKU is marked non-critical. EKU being non-critical does not disable its purpose constraint.

**`serverPkixAccepted=true`:** the leaf → root chain **with the test root configured as a `TrustAnchor`** via `PKIXParameters` passes general runtime checks. This does **not** mean the root is naturally trusted on the Internet. In the example `params.setRevocationEnabled(false)` only avoids needing CRL/OCSP for the fixture; **never disable revocation by default in real systems** without an appropriate compensating policy.

**`unknownCriticalRejected=true`:** having a critical OID with no checker handling it causes `CertPathValidator` to throw `CertPathValidatorException` and reject the path. Simply parsing a certificate with `CertificateFactory` **does not prove** it can be accepted.

**`unknownNoncriticalAccepted=true`:** an unrecognized non-critical OID can be ignored, provided all other requirements pass. This does not mean a known non-critical EKU like `serverAuth`/`clientAuth` can be ignored when evaluating purpose.

**`clientOnlyPkixAccepted=true` yet `clientOnlyServerPurpose=false`:** the generic PKIX path validator **does not automatically verify every business purpose**. In the fixture, the leaf has EKU `clientAuth`, while the illustrative policy requires EKU `serverAuth`; therefore it is disallowed as a TLS server certificate.

### 8.2 Intentional Limitations of the Example

- `demoServerPurpose` checks only **a single exact DNS SAN** without wildcard/IDNA, KU `digitalSignature`, EKU `serverAuth`, and EE BC. This is an **educational illustration**, **not a production hostname verifier**. TLS must use `TrustManagerFactory`, `X509ExtendedTrustManager`/JSSE, and proper endpoint identification.
- `CertPathValidator` in the example validates only **one leaf** signed by the demo root. Real systems have intermediate CAs, name constraints, certificate policies, algorithm constraints, revocation, trust store constraints, TLS EKU, and identity/hostname handling per protocol.
- `params.setRevocationEnabled(false)` is only for test environments without CRL/OCSP. Production needs an evaluated revocation policy, appropriate caching/failure modes, potentially via `PKIXRevocationChecker` or a configured JSSE provider.
- `TrustAnchor(root, null)` assumes the root is already trusted. **Never take a root from an unauthenticated sender and add it as a trust anchor.**
- `keytool` and how different providers recognize custom extensions can vary. The code and output above were tested on a JDK environment with those components and do not promise identical diagnostic messages across every provider.
- Never use test private keys from the demo PKCS12 in any real system. The password `changeit` is trivial to guess; all production secrets must use dedicated storage and lifecycles.

## 9. How KU/EKU/BC Work Together in Real-World Scenarios

| Certificate | Important KU | EKU by purpose | BC | Notes |
| --- | --- | --- | --- | --- |
| TLS server key signing handshake | `digitalSignature` | `serverAuth` when required by profile | EE `cA=false` | Requires SAN/hostname + PKIX + algorithm/signature scheme |
| TLS mutual-auth client | `digitalSignature` | `clientAuth` | EE | Do not use as server if policy requires `serverAuth` |
| Certificate-issuing CA | `keyCertSign` (and `cRLSign` if signing CRLs) | Per CA policy; often omitted or constrained | CA `cA=true`, BC critical | Must have valid trust/path and obey `pathLen` |
| Intermediate CA | `keyCertSign` | If EKU is present, check chain purpose restrictions per profile | CA `cA=true` | `pathLen` caps maximum non-self-issued subordinate CAs |
| Source code/software signing | `digitalSignature` or appropriate profile | `codeSigning` | EE | Must not be used as a TLS server |
| S/MIME email | KU per signing/encryption function | `emailProtection` | EE | Requires policy and relevant address/subject checks |
| OCSP delegated responder | `digitalSignature` | `OCSPSigning` | Per OCSP profile | Must verify OCSP delegation/responder chain |
| Fake CA certificate with only KU `keyCertSign` enabled | `keyCertSign` | Any | `cA=false` | **Must not** be used to issue certificates per RFC 5280 |

**Never blindly copy KU/EKU templates** across products. TLS, S/MIME, CMS, code signing, OCSP, CA/B Forum, and internal PKI standards have different detailed requirements that evolve over time. Select extensions according to **key purpose, signature/encryption mechanism, and relying-party profile**.

A CA certificate with `pathLen=0` can issue leaves directly; if a new intermediate CA is needed beneath it, a CA with an appropriate `pathLen` and proper key hierarchy must be re-issued. `BasicConstraints` is not an access-control tool for all certificate types; it primarily restricts **certificate issuance authority** and chain depth.

## 10. Troubleshooting Errors and Preventing Misconfigurations

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `InvalidCertificate` or `CertificateParsingException` reading EKU | Malformed ASN.1 DER in extension | Reject certificate, identify issuer, use safe parser/provider |
| `getKeyUsage()==null` | Certificate has no KU | Distinguish “unrestricted by KU” from a policy requiring KU presence |
| `getExtendedKeyUsage()==null` | Certificate has no EKU | Evaluate profile/purpose; do not assume every app permits it |
| `getBasicConstraints()==-1` | EE `cA=false` or BC absent | Do not use as CA; check extension presence if distinguishing is needed |
| `Integer.MAX_VALUE` from `getBasicConstraints` | CA has no `pathLenConstraint` | No depth limit **from the `pathLen` field**, though other constraints still apply |
| KU `keyCertSign=true` yet BC `cA=false` | Conflicting extensions | Refuse to use as CA; fix certificate issuance |
| Generic PKIX PASS yet HTTPS fails | SAN/hostname, `serverAuth` EKU, KU/signature algorithm, or other TLS policy | Use full JSSE trust manager and endpoint verification |
| PKIX fails on `UNRECOGNIZED_CRIT_EXT` / critical error | Critical extension OID not handled by any checker | Add valid checker or ask issuer for compatible certificate; never strip critical flag at runtime |
| Unknown non-critical is ignored | Expected behavior when extension does not affect purpose/profile | Do not confuse with a recognized extension that restricts usage |
| Test self-signed root “passes” despite untrusted root | App arbitrarily added root as `TrustAnchor` | Only use trust stores/anchors managed through an authenticated channel |
| `CertificateFactory` parses cert yet validation fails | Syntax parsing does not equal chain/trust verification | Invoke `CertPathValidator`/TLS engine for its intended job |
| Leaf KU/EKU mismatches purpose | CA used wrong extension template | Re-issue with proper purpose and algorithms; do not bypass policy |
| PKIX fails on expiration or crypto policy | Expired cert, weak key, disabled algorithm | Rotate/re-issue, update PKI safely; never disable algorithm constraints |
| Revocation not checked | CRL/OCSP unconfigured or intentionally disabled for demo | Design revocation policy for production environments |

### Recommended Verification Workflow

1. **Parse:** `CertificateFactory("X.509")`, bound input size, never treat a valid PEM file as a trusted certificate.
2. **Inspect extensions:** `getKeyUsage()`, `getExtendedKeyUsage()`, `getBasicConstraints()`, critical/non-critical OIDs; pay attention to absent extensions and defaults.
3. **Verify chain:** configure real trusted anchors, intermediate certificates, validity period, algorithm constraints, policies, critical extensions, and revocation per profile.
4. **Verify purpose:** KU/EKU match the operation and system, e.g., TLS server vs. client. When both are present, both must be satisfied simultaneously.
5. **Verify identity:** SAN hostname/IP or other protocol-mandated identifier; never use bare CN as a substitute for SAN in modern TLS systems.
6. **Permit the operation only after all relevant steps PASS.** Log selectively for audit (subject, issuer, serial, public certificate fingerprint); never log private keys or sensitive tokens.

## 11. Misconceptions to Remember

**“If KeyUsage is critical, is the certificate automatically trusted?”** No. Critical only requires the verifier to understand and enforce the extension; trust anchor, chain, validity, identity, and purpose must still be checked.

**“Does non-critical EKU mean `serverAuth` can be ignored?”** No. If an application verifier recognizes EKU, it must evaluate permitted usage under the profile; non-critical only permits ignoring **unrecognized extensions** per policy.

**“Does `CA=true` mean a trusted root CA?”** No. `cA=true` is a structural issuance capability; trust anchors must be established outside the certificate via trustworthy mechanisms.

**“Does `pathLen=0` mean no leaves can be issued?”** No. It restricts **non-self-issued intermediate CAs** below it, without forbidding direct end-entity issuance.

**“Does having KU `digitalSignature` allow acting as a CA?”** No. Signing certificates requires `keyCertSign` and `BasicConstraints.cA=true`, plus valid path/trust/policy.

**“Does having KU `keyEncipherment` suffice for a TLS 1.3 server?”** Insufficient. TLS 1.3 certificate authentication uses signatures; certificate algorithm, `digitalSignature`, EKU, and SAN/hostname must be evaluated.

**“If `getExtendedKeyUsage() == null`, is the certificate unusable?”** Not automatically. It simply has no declared EKU restriction; the protocol or policy may still require a specific one.

**“Does `certificate.verify(publicKey)` perform PKIX checks?”** No. That only checks the certificate's signature, not full path validation or hostname/purpose checks.

**“If `getCriticalExtensionOIDs()` is empty, is HTTPS safe?”** No. Having no unknown critical extensions eliminates only one error category; all other trust/identity requirements remain mandatory.

## 12. Self-Check Knowledge Questions

1. **OIDs of KU, BC, and EKU?** `2.5.29.15`, `2.5.29.19`, and `2.5.29.37`, respectively.
2. **Bit indices of `digitalSignature`, `keyEncipherment`, and `keyCertSign`?** `0`, `2`, `5`.
3. **What does Java return if KU is absent?** `X509Certificate.getKeyUsage()==null`.
4. **What does Java return if EKU is absent?** `getExtendedKeyUsage()==null`.
5. **How many situations can produce `getBasicConstraints()==-1`?** `cA=false` or BC absent; neither permits granting CA authority.
6. **What does `getBasicConstraints()==Integer.MAX_VALUE` usually mean?** A CA with `cA=true` and no `pathLenConstraint` specified.
7. **Can a root CA with `pathLen=0` sign a leaf directly?** Yes; it cannot have additional non-self-issued intermediate CAs below it under that constraint.
8. **Is KU `keyCertSign=true` enough to use a key as a CA?** No; it requires `BasicConstraints.cA=true`, trust/path, and policy.
9. **Does EKU `serverAuth` replace KU `digitalSignature` for TLS 1.3?** No; when both are present, both must align.
10. **If a certificate has only EKU `clientAuth`, can generic PKIX chain validation pass?** Yes; a server-purpose verifier must still reject it when `serverAuth` is required.
11. **Can an unrecognized critical extension be ignored?** No; a compliant verifier must understand and enforce it or reject.
12. **Can an unknown non-critical extension be ignored?** Yes, when unsupported and allowed by profile; that does not mean known EKU/KU constraints can be ignored.
13. **Does `getExtensionValue(oid)` return the raw extension content or the outer OCTET STRING bytes?** The outer **DER-encoded OCTET STRING** bytes.
14. **Is using `TrustAnchor(rootFromNetwork,null)` arbitrarily safe?** No, because it blindly trusts an unverified CA.
15. **Does `checkValidity()` verify hostname/EKU/CRL?** No; it only checks the validity period.
16. **Why does the demo disable revocation?** So the temporary fixture needs no CRL/OCSP infrastructure; real systems must configure an appropriate revocation policy.
17. **Is a certificate successfully parsed by `CertificateFactory` guaranteed to be accepted by `CertPathValidator`?** No; it can fail critical extensions, chain, signature, constraints, or policy.
18. **To use a certificate for HTTPS, should you just call a few KU/EKU getters yourself?** Never replace JSSE/`TrustManager` and hostname verification with ad-hoc checks; use a complete protocol verifier.

## Standards and Official API Documentation

- [RFC 5280 — Internet X.509 PKI Certificate and CRL Profile: `4.2.1.3 Key Usage; `4.2.1.9 Basic Constraints; `4.2.1.12 EKU](https://www.rfc-editor.org/rfc/rfc5280.html)
- [X509Certificate (Java SE 21): getKeyUsage, getExtendedKeyUsage, getBasicConstraints](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/X509Certificate.html)
- [X509Extension: getCriticalExtensionOIDs, hasUnsupportedCriticalExtension, getExtensionValue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/X509Extension.html)
- [CertificateFactory: parsing X.509 certificates and CertPath](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertificateFactory.html)
- [CertPathValidator and PKIXParameters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertPathValidator.html)
- [TrustAnchor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/TrustAnchor.html)
- [X509CertSelector (filtering by KU, EKU, constraints — does not replace path validation)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/X509CertSelector.html)
- [JSSE Reference Guide — TLS validation and trust managers](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html)
- [keytool: managing and issuing demo certificates](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html)
