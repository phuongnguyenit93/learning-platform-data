# 14.7 Policy When Revocation Status Cannot Be Retrieved and the Consequences of SOFT_FAIL

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish three cases: a certificate **not revoked per valid evidence**, a **revoked** certificate, and a certificate whose **revocation status cannot be determined**.
2. Evaluate **hard-fail/fail-closed** vs **conditional soft-fail**, especially when OCSP/CRL or networking fails.
3. Understand the exact semantics of `PKIXRevocationChecker.Option.SOFT_FAIL` in Java 17, which cases it permits ignoring, and how it interacts with `NO_FALLBACK`, `PREFER_CRLS`, and `ONLY_END_ENTITY`.
4. Configure `CertPathValidator`, `PKIXParameters`, `TrustAnchor`, and `PKIXRevocationChecker`; understand the role of `getSoftFailExceptions()`.
5. Run two Java 17 labs: an unreachable OCSP responder producing `UNDETERMINED_REVOCATION_STATUS` in strict mode yet soft-failed; and a validly signed CRL confirming `REVOKED` that is still rejected even with `SOFT_FAIL` enabled.
6. Design risk-tiered policies, bound fallback/caching/timeouts, monitor soft-fail events, and test rejection of revoked certificates.

## 1. Certificate Revocation Differs from Signature, Validity, or Identity Verification

An **X.509 certificate** can be validly signed by a CA, unexpired, and have a matching Subject Alternative Name, yet **still have been revoked before `notAfter`** due to private key compromise, device loss, service ownership change, or other PKI administrative reasons.

```text
Leaf certificate + chain
            |
            v
Check signatures, trust anchor, validity, policy,
KeyUsage/EKU, hostname/SAN...
            |
            v
Check revocation status via OCSP/CRL
            |
     +------+------+
     |      |      |
    good  revoked  undetermined
     |      |      |
 continue REJECT   apply policy
```

**Undetermined is not good.** A network timeout, DNS failure, or unresponsive OCSP responder means the client **lacks current status evidence**, not that the CA confirmed the certificate is still good.

| Status | Nature | Handling |
| --- | --- | --- |
| **Not-revoked per valid OCSP/CRL** | Trustworthy, matching-cert, fresh, in-scope revocation evidence shows no revocation | May proceed with remaining PKIX checks |
| **REVOKED** | Valid evidence confirms the certificate is revoked | **Reject** |
| **UNDETERMINED** | Unable to retrieve/verify enough evidence to conclude | Hard-fail or soft-fail per policy/API |
| **Bad signature/chain/CA, expired, hostname mismatch** | Error independent of revocation channel | **Reject**, `SOFT_FAIL` does not validate it |
| **No responder or valid CRL** | Missing evidence, possibly due to configuration or profile | Never treat as good by default |

`X509Certificate.checkValidity()` only checks `notBefore` and `notAfter`; it does not query OCSP or CRL. Conversely, revocation checking does not replace chain, identity, or certificate constraint validation.

## 2. Status Delivery Mechanisms: OCSP and CRL

### 2.1 OCSP per RFC 6960

**Online Certificate Status Protocol (OCSP)** queries an OCSP responder for the status of a certificate identified by its certificate ID. You must verify responder signature/authorization, exact certificate ID match, and information freshness.

When an OCSP response is processed successfully, `SingleResponse.certStatus` has three types:

- **`good`**: within the responder's scope, the certificate is not known to be revoked. RFC 6960 notes this **does not by itself prove the certificate was ever issued** or that the trust chain is valid.
- **`revoked`**: the certificate is revoked; some profiles allow this status for non-issued cases as well. The verifier must reject.
- **`unknown`**: the responder does not know about the queried certificate/issuer. This is **a structured status**, not synonymous with a network error.

When an OCSP response has a processing error, `responseStatus` can be:

```text
successful (0)
malformedRequest (1)
internalError (2)
tryLater (3)
sigRequired (5)
unauthorized (6)
```

Among these, `internalError` and `tryLater` have special significance under Java's `SOFT_FAIL` rules. **Never lump `unknown`, `malformedRequest`, `unauthorized`, and `tryLater` together as one generic “no reply”**.

The timestamps `thisUpdate`, `nextUpdate`, and `producedAt` govern response freshness/signing time. A **stale** `good` response cannot automatically serve as current `good` evidence.

### 2.2 CRL per RFC 5280

A **Certificate Revocation List (CRL)** is a list of revoked serial numbers signed by a CA or an authorized CRL issuer. Valid checking requires:

- Verifying the **CRL signature**, authority, and `cRLSign` permission per profile.
- Checking **issuer/scope**, issuing distribution point, reason masks, and delta CRLs if used.
- Checking `thisUpdate`/`nextUpdate` and freshness, never using an expired CRL as clean evidence.
- Looking up the certificate serial within the issuer's scope, never treating “some arbitrary CRL lacks the serial” as clean.
- Handling intermediate/CA certificates per policy; do not check only the leaf if the flow requires checking every path component.

OCSP and CRL have different characteristics; a system may prefer one channel and fall back to the other. However, **both require authenticating the evidence source** and freshness before acting on the result.

## 3. Hard-Fail and Soft-Fail Distribute Risk Differently

### 3.1 Hard-fail / fail-closed

If revocation status cannot be determined per policy, the connection or operation must be **rejected**.

```text
OCSP/CRL timeout
      |
      v
status undetermined
      |
      v
HARD-FAIL --> REJECT
```

Pros: makes it hard for an adversary to force acceptance of a revoked certificate by blocking responder connectivity. Cons: DNS, proxy, internal network, CA responder failures, or wide outages can reject valid certificates and cause service disruption.

### 3.2 Conditional soft-fail / fail-open

With soft-fail, **certain errors retrieving revocation status** can be ignored so verification continues, provided no other PKIX errors occurred.

```text
OCSP/CRL temporarily unreachable
      |
      v
status undetermined
      |
      v
SOFT-FAIL permits ignoring errors in the defined set
      |
      v
validation may proceed / accept path
```

Pros: improves availability during responder or network glitches.

**Security consequence:** suppose a private key is compromised and the corresponding certificate is revoked by the CA. If an attacker disrupts connectivity to OCSP/CRL or waits until the responder is down, a verifier configured with soft-fail can **continue accepting the old certificate despite missing revocation news**. This is a real trade-off, not “equal security with fewer connection errors”.

| Status | Hard-fail | Conditional soft-fail |
| --- | --- | --- |
| Valid evidence confirms not revoked | Proceed to remaining checks | Proceed to remaining checks |
| Valid evidence confirms **REVOKED** | **Reject** | **Reject** |
| Network error within allowed scope | **Reject** | May proceed; must log missing evidence |
| OCSP `internalError` or `tryLater` eligible for soft handling | **Reject** if no other source remains | May proceed per fallback rules |
| OCSP `unknown` | Status unconfirmed | Not automatically treated as a network error |
| Expired cert, bad signature, untrusted chain | **Reject** | **Reject** |

This table illustrates the decision model. Actual outcomes depend on `PKIXRevocationChecker`, provider, fallback options, and available evidence sources.

## 4. Exact Semantics of Java 17 `PKIXRevocationChecker.Option.SOFT_FAIL`

Oracle Java SE 17 documentation scopes `SOFT_FAIL` to these situations:

1. **The CRL or OCSP response cannot be obtained due to a network error**.
2. **The OCSP responder returns `internalError` or `tryLater`** per protocol.

This is not an “ignore all revocation errors” flag. **A certificate known to be revoked must be rejected**; signature/chain/algorithm/validity errors do not become valid.

Per the `PKIXRevocationChecker.Option` API, when `NO_FALLBACK` is not set, the checker can soft-fail only when **both OCSP and CRL fail for one of the permitted reasons** within the checking mechanism. If the fallback source works and confirms revocation, it must reject.

### 4.1 Options That Directly Affect Behavior

| Option | Meaning | Consideration |
| --- | --- | --- |
| `SOFT_FAIL` | Ignores certain undetermined errors from network/transient OCSP failures | Can accept a path without revocation evidence |
| `NO_FALLBACK` | Disables the fallback mechanism | Increases dependence on the preferred channel; unsuitable for many production setups |
| `PREFER_CRLS` | Prefers CRLs over OCSP | Changes lookup order; depends on available CRLs |
| `ONLY_END_ENTITY` | Checks only the leaf, skipping revocation status of CAs in the path | May violate intermediate CA revocation requirements |

The documented API default is **prefer OCSP, fall back to CRL**. `PREFER_CRLS` reverses priority; `NO_FALLBACK` disables fallback.

```java
PKIXRevocationChecker checker =
        (PKIXRevocationChecker) validator.getRevocationChecker();
checker.setOptions(EnumSet.of(
        PKIXRevocationChecker.Option.SOFT_FAIL,
        PKIXRevocationChecker.Option.NO_FALLBACK));
```

This is an **embedded snippet** requiring imports and a `validator` variable, not a standalone program. The `SOFT_FAIL + NO_FALLBACK` pair is used in the lab to cleanly reproduce a failing OCSP channel, **not as a default production recipe**.

### 4.2 `setRevocationEnabled(false)` May **Not** Disable the Checker

The `PKIXRevocationChecker` documentation clearly states: when explicitly adding the checker to `PKIXParameters` via `addCertPathChecker`, the checker is still used **regardless of the `revocationEnabled` value**.

```java
CertPathValidator validator = CertPathValidator.getInstance("PKIX");
PKIXRevocationChecker checker =
        (PKIXRevocationChecker) validator.getRevocationChecker();

PKIXParameters params = new PKIXParameters(trustAnchors);
params.setRevocationEnabled(false);
params.addCertPathChecker(checker);
validator.validate(certPath, params);
```

This is an illustrative snippet; it requires `trustAnchors`, `certPath`, and imports. Here `setRevocationEnabled(false)` disables the **default checker flow**, not the checker explicitly added via API. Conversely, disabling the flag **without adding a checker** can leave the application without revocation checking. Always inspect the overall configuration, not a single line.

### 4.3 `getSoftFailExceptions()` to Distinguish “Good” from “Ignored Errors”

`PKIXRevocationChecker.getSoftFailExceptions()` returns the list of **`CertPathValidatorException` instances ignored** due to `SOFT_FAIL`.

- The list is unmodifiable and is **cleared each time the checker runs `init`**.
- Per API, exceptions are ordered by **certificate index**.
- Useful for recording whether a validation run bypassed any network error, distinct from having valid revocation evidence.

**Caveat:** `PKIXParameters.addCertPathChecker` **clones the checker** and providers may manage/reinitialize instances. Do not assume every `checker` reference reflects the exact validation run; test on your exact production JDK/provider. Also never share a mutable checker across requests/threads because thread safety is not guaranteed.

A metric showing “`soft fail exceptions = 0`” **does not prove revocation was checked**: if someone accidentally disabled checking altogether, it would also be 0.

## 5. Distinguishing Reasons in `CertPathValidatorException`

`CertPathValidatorException.BasicReason` in Java 17 includes:

- `UNDETERMINED_REVOCATION_STATUS` — revocation status could not be determined.
- `REVOKED` — the certificate was revoked.
- `EXPIRED` / `NOT_YET_VALID` — outside validity window.
- `INVALID_SIGNATURE` — invalid signature.
- `ALGORITHM_CONSTRAINED` — algorithm/key constrained by security policy.

**Never write a catch block that “returns true when undetermined”:**

```java
// ANTI-PATTERN, DO NOT USE IN PRODUCTION
try {
    validator.validate(path, params);
    return true;
} catch (CertPathValidatorException e) {
    return e.getReason() ==
            CertPathValidatorException.BasicReason.UNDETERMINED_REVOCATION_STATUS;
}
```

This is an **anti-pattern snippet**, not meant to compile standalone. It bypasses the checker's classification logic, can skip fallback conditions, and makes no guarantees about prior/subsequent errors. Let the checker/validator enforce configured policy; accept only after **full path validation**, never swallowing generic exceptions.

## 6. Lab 1 — Java 17: Unreachable OCSP Responder

We create a **lab-only CA and leaf certificate**, then point the OCSP responder to `http://127.0.0.1:1/ocsp`. In a test environment, nothing listens on port 1, so the request fails with a connection error. No external systems are queried.

**Expected lab outcome:** strict mode returns `UNDETERMINED_REVOCATION_STATUS`; `SOFT_FAIL` can validate and record 1 ignored error. If port 1 has a service on your machine or a provider behaves differently, results/exception counts may vary; pick a loopback port with no real responder and check configuration.

### 6.1 Prepare CA/Leaf with `keytool`

Run in an **empty test directory** using JDK 17+, never with production keystores:

```bash
keytool -genkeypair -alias labca -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=Lab Root CA,O=Example Lab,C=VN" -validity 180 -ext bc:c -ext ku=keyCertSign,cRLSign -keystore ca.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt

keytool -exportcert -alias labca -keystore ca.p12 -storetype PKCS12 -storepass changeit -rfc -file ca.pem

keytool -genkeypair -alias leaf -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=lab.local,O=Example Lab,C=VN" -validity 30 -keystore leaf.p12 -storetype PKCS12 -storepass changeit -noprompt

keytool -certreq -alias leaf -keystore leaf.p12 -storetype PKCS12 -storepass changeit -file leaf.csr

keytool -gencert -alias labca -keystore ca.p12 -storetype PKCS12 -storepass changeit -infile leaf.csr -outfile leaf.pem -rfc -validity 30 -ext ku=digitalSignature -ext EKU=serverAuth -ext SAN=dns:lab.local
```

`ca.p12` and `leaf.p12` contain **practice-only private keys**; never commit, share, or deploy them. The `changeit` password is for the lab only. `ca.pem` is the public CA certificate used as an **explicit lab trust anchor**, and `leaf.pem` is the leaf certificate signed by the lab CA. Importing an arbitrary CA from the network as a production trust anchor is **dangerous**.

### 6.2 `RevocationPolicyLab.java`

```java
import java.io.InputStream;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.*;
import java.util.*;

public class RevocationPolicyLab {
    private static X509Certificate load(String filename) throws Exception {
        try (InputStream stream = Files.newInputStream(Path.of(filename))) {
            return (X509Certificate) CertificateFactory.getInstance("X.509")
                    .generateCertificate(stream);
        }
    }

    private static void check(X509Certificate leaf, X509Certificate root,
                              boolean allowSoftFail) throws Exception {
        CertPathValidator validator = CertPathValidator.getInstance("PKIX");
        PKIXRevocationChecker checker =
                (PKIXRevocationChecker) validator.getRevocationChecker();

        checker.setOcspResponder(URI.create("http://127.0.0.1:1/ocsp"));
        checker.setOptions(allowSoftFail
                ? EnumSet.of(PKIXRevocationChecker.Option.NO_FALLBACK,
                             PKIXRevocationChecker.Option.SOFT_FAIL)
                : EnumSet.of(PKIXRevocationChecker.Option.NO_FALLBACK));

        PKIXParameters params = new PKIXParameters(
                Set.of(new TrustAnchor(root, null)));
        params.setRevocationEnabled(false);
        params.addCertPathChecker(checker);

        CertPath certPath = CertificateFactory.getInstance("X.509")
                .generateCertPath(List.of(leaf));
        try {
            validator.validate(certPath, params);
            System.out.println((allowSoftFail ? "soft" : "strict") +
                    ": VALIDATED");
        } catch (CertPathValidatorException e) {
            System.out.println((allowSoftFail ? "soft" : "strict") +
                    ": REJECTED reason=" + e.getReason());
        }
        System.out.println("original checker ignored: " +
                checker.getSoftFailExceptions().size());
        for (PKIXCertPathChecker candidate : params.getCertPathCheckers()) {
            if (candidate instanceof PKIXRevocationChecker) {
                System.out.println("params checker ignored: " +
                        ((PKIXRevocationChecker) candidate)
                                .getSoftFailExceptions().size());
            }
        }
    }

    public static void main(String[] args) throws Exception {
        X509Certificate leaf = load(args[0]);
        X509Certificate root = load(args[1]);
        leaf.verify(root.getPublicKey());
        System.out.println("leaf signed by trusted CA: true");
        check(leaf, root, false);
        check(leaf, root, true);
    }
}
```

Compile and run in the same directory as `leaf.pem`/`ca.pem`:

```bash
javac --release 17 RevocationPolicyLab.java
java RevocationPolicyLab leaf.pem ca.pem
```

**Run and verified** output on our test JDK/provider:

```text
leaf signed by trusted CA: true
strict: REJECTED reason=UNDETERMINED_REVOCATION_STATUS
original checker ignored: 0
params checker ignored: 0
soft: VALIDATED
original checker ignored: 1
params checker ignored: 1
```

**Explanation:**

1. `leaf.verify(root.getPublicKey())` checks the leaf signature against the lab CA's key. It does not prove the root is trusted; the program **intentionally creates the trust anchor** `new TrustAnchor(root,null)`.
2. `setOcspResponder` **overrides** the OCSP endpoint in AIA/security properties if any; the loopback address simulates a network error.
3. `NO_FALLBACK` disables fallback to CRL; thus the strict pass fails when OCSP cannot be reached.
4. The `SOFT_FAIL` pass ignores the API-scoped connection error; the path validates even **without an OCSP `good` response**.
5. On the test JDK, `getSoftFailExceptions()` records the ignored error; do not assume identical counts or object state across every provider or across `init` calls.
6. `params.setRevocationEnabled(false)` does not block the explicitly added checker. Had checking actually been disabled, the strict pass would not have returned a revocation reason in stdout.

What the lab proves is **the policy difference when evidence is missing**. Do not hardcode `NO_FALLBACK` or loopback OCSP in real applications. Let the provider reach authoritative OCSP/CRL sources and enforce approved policy/monitoring.

## 7. Lab 2 — SOFT_FAIL Still Rejects a REVOKED Certificate

To prove `SOFT_FAIL` **never accepts explicit revocation evidence**, reuse `ca.p12`/`ca.pem`/`leaf.pem` from above. Generate a lab-CA-signed CRL listing the leaf's **actual serial**, add the CRL to `CertStore`, and test with `PREFER_CRLS + NO_FALLBACK + SOFT_FAIL`.

### 7.1 Generate a CRL with the Certificate's Serial

`keytool -gencrl -id` takes a decimal serial. Because X.509 serials can exceed `long`, read the hex serial from `keytool -printcert` and convert to decimal using `BigInteger`.

Commands below use **PowerShell 5.1+** in the lab directory:

```powershell
$serialLine = (keytool -printcert -file leaf.pem |
    Select-String 'Serial number:' | Select-Object -First 1).ToString()
$serialHex = ($serialLine -split 'Serial number:')[1].Trim()
$serialDecimal = [System.Numerics.BigInteger]::Parse(
    ('0' + $serialHex),
    [System.Globalization.NumberStyles]::AllowHexSpecifier
).ToString()
keytool -gencrl -alias labca -keystore ca.p12 -storepass changeit -file revoked.crl -rfc -id $serialDecimal
```

`revoked.crl` is strictly a lab CRL. Timestamps/serials vary per generation. **Never run these commands against a production CA**; the lab creates and uses isolated test keys.

### 7.2 `KnownRevokedLab.java`

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.*;
import java.util.*;

public class KnownRevokedLab {
    public static void main(String[] args) throws Exception {
        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        X509Certificate leaf;
        X509Certificate ca;
        X509CRL crl;
        try (InputStream in = Files.newInputStream(Path.of(args[0]))) {
            leaf = (X509Certificate) factory.generateCertificate(in);
        }
        try (InputStream in = Files.newInputStream(Path.of(args[1]))) {
            ca = (X509Certificate) factory.generateCertificate(in);
        }
        try (InputStream in = Files.newInputStream(Path.of(args[2]))) {
            crl = (X509CRL) factory.generateCRL(in);
        }

        crl.verify(ca.getPublicKey());
        System.out.println("CRL signature verifies: true");
        System.out.println("leaf on CRL: " + crl.isRevoked(leaf));

        CertPathValidator validator = CertPathValidator.getInstance("PKIX");
        PKIXRevocationChecker checker =
                (PKIXRevocationChecker) validator.getRevocationChecker();
        checker.setOptions(EnumSet.of(
                PKIXRevocationChecker.Option.PREFER_CRLS,
                PKIXRevocationChecker.Option.NO_FALLBACK,
                PKIXRevocationChecker.Option.SOFT_FAIL));

        PKIXParameters params = new PKIXParameters(
                Set.of(new TrustAnchor(ca, null)));
        params.setRevocationEnabled(false);
        params.addCertStore(CertStore.getInstance("Collection",
                new CollectionCertStoreParameters(List.of(crl))));
        params.addCertPathChecker(checker);
        CertPath path = factory.generateCertPath(List.of(leaf));

        try {
            validator.validate(path, params);
            System.out.println("soft fail accepts revoked: true");
        } catch (CertPathValidatorException e) {
            System.out.println("soft fail rejects revoked: " +
                    (e.getReason() ==
                            CertPathValidatorException.BasicReason.REVOKED));
            System.out.println("reason: " + e.getReason());
        }
    }
}
```

Compile and run after generating `revoked.crl`:

```bash
javac --release 17 KnownRevokedLab.java
java KnownRevokedLab leaf.pem ca.pem revoked.crl
```

Verified output with the lab CA and CRL:

```text
CRL signature verifies: true
leaf on CRL: true
soft fail rejects revoked: true
reason: REVOKED
```

Explanation:

- `crl.verify(ca.getPublicKey())` verifies the CRL signature; in production, also check authority/scope/validity/distribution point and other CRL rules.
- `crl.isRevoked(leaf)` confirms the leaf is listed.
- The checker has `SOFT_FAIL` enabled, yet the PKIX result is still `REVOKED`, because **valid revocation evidence is not a network error**.
- `PREFER_CRLS + NO_FALLBACK` intentionally forces the CRL channel for testing and does not represent a complete production policy.

## 8. Why Can SOFT_FAIL Be Exploited via Network Failures?

A dangerous scenario:

1. A device's or service's private key is stolen.
2. The CA detects the compromise and publishes `revoked` via OCSP/CRL.
3. The attacker still holds the old certificate and compromised private key.
4. At the exact moment the verifier checks, the connection to the revocation source fails (either induced by the attacker or from a coincidental outage).
5. If a soft-fail policy allows proceeding without evidence, the service may **continue accepting the revoked certificate**.

This demonstrates that responder availability is part of the security model. Blocking the network does not break the CA's private key, yet it can **undermine revocation enforcement** if the verifier fails open.

Risk grows when:

- Soft-fail is enabled system-wide without distinguishing privilege levels.
- There are no timeouts/budgets; undetermined states persist for days.
- There is no monitoring, or every `validator.validate() == success` is assumed to prove not-revoked.
- There are no CRL/OCSP mirrors or verified fallback sources.
- `ONLY_END_ENTITY` is used even when policy requires checking intermediate CAs.
- Application code swallows generic exceptions and grants login regardless.
- Attacker-induced DNS/proxy failures are dismissed as routine operational noise.

The answer is not necessarily “hard-fail everywhere”. Evaluate **asset value**, availability needs, authority scope, and fallback mechanisms so that any soft-fail exception is **approved and observable**.

## 9. Risk-Tiered Policy

| System/context | Generally suitable design | Conditions |
| --- | --- | --- |
| mTLS auth for admin, payment, HSM, or transaction-signing services | **Hard-fail** when revocation cannot be determined if policy mandates checking | Redundant evidence sources/unexpired caching, clear errors, avoiding unnecessary outages |
| Device certificate provisioning, admin/privileged access | **Hard-fail**, with controlled outage handling | Preserve key/issuer/chain trust; never drop checks |
| Clients connecting to public, low-privilege services | May allow **conditional soft-fail** per applicable standard/threat model | Audit logging, time limits, never ignore revoked |
| Periodically offline devices with cached CRL/OCSP responses | Use only **still-valid** evidence; apply explicit offline policy afterward | Define max age, allowed devices, and recovery process |
| Internal network with managed CRL mirror/OCSP proxy | Prefer trusted/available internal sources | Verify signatures and freshness; never trust an endpoint solely because it is internal |
| Intermediate CA chains authorized to sign many services | Usually check full path per policy | Never accidentally skip CA revocation with `ONLY_END_ENTITY` |

No single default fits all cases. Industry regulations, protocol specs, or internal policies may mandate hard-fail or specific evidence collection.

### 9.1 If Choosing Soft-Fail, Define the Exception Explicitly

A controlled soft-fail decision should specify:

- **Eligible errors:** only causes supported by `SOFT_FAIL`; never treat revoked/invalid responses as “minor”.
- **Scope:** workload classes, certificates/CAs, accounts, privileges, and permitted actions; e.g., read-only may differ from privilege-granting operations.
- **Time limit:** how long operations may proceed without fresh evidence; consecutive thresholds and recovery conditions.
- **Alternate sources:** signed, valid fallback mechanisms, monitored mirrors/caches.
- **Telemetry:** validation counts, reasons, timestamps, responders, soft-fail rates, and evidence age.
- **Circuit-break / emergency stop:** thresholds to switch to hard-fail or block sensitive actions; CA/key-leak incident controls.
- **Approvers:** PKI/security owners, policy change history, and periodic review requirements.

**Soft-fail does not mean returning true when the network breaks.** Full chain, identity, and all other checks must still pass.

## 10. Fallback, Caching, Retries, and Timeouts

### 10.1 Fallback Must Rely on Valid Evidence

If OCSP fails to reply, a valid CRL can serve as an alternate check; conversely, if a CRL is unreachable, a valid OCSP response can confirm status. However, fallback **must never** accept evidence with a bad signature, wrong issuer, expired timestamps, or non-matching coverage.

`NO_FALLBACK` helps isolate behavior in a lab, yet **can reduce both availability and the ability to detect `revoked` status** when the preferred source fails.

### 10.2 Caching Does Not Mean Keeping “Good” Forever

- OCSP carries `thisUpdate`, `nextUpdate`, and `producedAt`.
- CRLs carry `thisUpdate` and typically `nextUpdate` per profile.
- An **expired** cached `good` status is no longer trustworthy fresh evidence. If policy allows continuing, record it explicitly as a **degraded exception**, not “OCSP currently good”.
- Never set a TTL longer than the source's freshness window, and never treat `HTTP 200` as proof of a valid signature.

### 10.3 Timeouts and Retries Can Turn an Outage into a DoS

A slow responder can stall thousands of concurrent requests/handshakes or retries. Therefore enforce:

- Bounded DNS/TCP/HTTP/OCSP timeouts aligned with SLOs and policy.
- Backoff/jitter, retry limits, and concurrency caps to avoid thundering herds.
- Caching/deduplication for concurrent validations of the same certificate.
- Circuit breakers with **explicit** outcomes (fail-closed or approved soft-fail), never faking success.
- Network egress controls to CRL/AIA URLs since URLs can come from external certificates; prevent arbitrary internal network probing.
- Clock and response-freshness monitoring. Clock drift causes certificates or status evidence to be misjudged as valid/expired.

Too short a timeout spikes soft-fails; too long raises latency and DoS risk. Benchmark on real environments and providers.

## 11. OCSP Stapling and Must-Staple Are Separate Concerns

**OCSP stapling** lets the server deliver an OCSP response during the TLS handshake, avoiding direct client-to-responder queries in many cases. Clients must still verify its signature, responder authority, exact certificate match, and freshness.

The **TLS Feature extension — RFC 7633**, sometimes called “must-staple”, is a separate protocol signal/constraint, **not equivalent** to Java's `PKIXRevocationChecker.Option.SOFT_FAIL`.

Do not assume a Java JSSE/HTTPS client automatically enforces must-staple just because `SOFT_FAIL`/`setRevocationEnabled` is present. If your product's TLS policy requires revocation or stapling, check the trust manager/provider, security properties, and **test end-to-end**. The standalone `CertPathValidator` lab proves only the behavior of the configured PKIX API, not that every HTTP/TLS client on the host follows it.

## 12. Monitoring and Incident Handling

Useful metrics:

| Suggested metric / field | Role |
| --- | --- |
| `pkix_soft_fail_total` | Total revocation errors bypassed by policy |
| `revocation_check_total{method,outcome}` | Separates OCSP/CRL and good/revoked/undetermined/error |
| `ocsp_crl_error_total{endpoint,reason}` | Breaks down DNS, timeout, HTTP, and responder errors |
| `revocation_evidence_age_seconds` | Alerts when evidence approaches staleness/expiry |
| `revocation_next_update_remaining_seconds` | Tracks remaining valid cache lifetime |
| `cert_validation_total{reason}` | Separates `REVOKED`, `EXPIRED`, `INVALID_SIGNATURE`, `UNDETERMINED` |
| `soft_fail_duration_seconds` | Tracks duration spent operating in degraded state |

Audit logs may record CA/issuer ID, certificate serial/fingerprint, responder, policy version, and basic reason. Enforce access controls; never log private keys/credentials; avoid putting per-user DNs or serials into unbounded high-cardinality metric labels.

**Note:** a zero soft-fail metric does not prove the checker is enabled. Run **synthetic tests** with an actually revoked certificate to ensure the live system rejects it even during network faults.

### 12.1 Runbook When a Responder Becomes Unavailable

1. Confirm whether the issue is responder/DNS/proxy/circuit vs another PKIX error; do not rush to disable all validation.
2. Check fallback CRL/OCSP and caches that are **unexpired and match issuer/scope**.
3. Segment high-privilege flows; enforce hard-fail unless a valid approved exception policy exists.
4. If any group is permitted soft-fail, document the approver, time limit, affected assets, metrics, and exit criteria.
5. Restore responder access or sync fresh evidence; confirm the soft-fail rate drops.
6. After the outage, audit logs to identify sessions accepted **while revocation was undetermined** and evaluate whether credentials/certificates need rotation or revocation.

## 13. Required Test Matrix

| Scenario | Expected outcome |
| --- | --- |
| Trusted chain, valid OCSP/CRL confirms not revoked | Proceed if remaining checks pass |
| Valid OCSP confirms `revoked` | REJECT despite SOFT_FAIL |
| Valid CRL lists leaf as revoked | REJECT despite SOFT_FAIL (Lab 2) |
| OCSP network error, `NO_FALLBACK`, strict | `UNDETERMINED_REVOCATION_STATUS` (Lab 1) |
| OCSP network error, `NO_FALLBACK`, SOFT_FAIL | Can validate; ignored error audited (Lab 1) |
| OCSP fails yet fallback CRL is valid | Use CRL result; do not skip prematurely |
| OCSP `internalError` / `tryLater` | Per `SOFT_FAIL` scope and fallback rules |
| OCSP `unknown` or `unauthorized` | Do not automatically treat as a network error |
| OCSP response with bad signature, wrong serial/issuer, wrong timestamps | Do not accept as `good` evidence |
| Expired CRL or CRL not covering certificate | Do not treat as revocation verified |
| Expired cert or wrong trust anchor | REJECT independently of SOFT_FAIL |
| Intermediate CA revoked | Per path/policy scope; never skip unintentionally |
| Prolonged outage / failover / JDK or provider upgrade | Verify timeouts, config, and actual behavior |
| Production TLS client | Test full handshake/trust manager, not just PKIX unit tests |

If an unexpected exception arises, the test must fail and trigger investigation rather than being silenced with `catch(Exception) return true`.

## 14. Common Mistakes

1. **“Unreachable OCSP means not revoked.”** False: that is undetermined status.
2. **“SOFT_FAIL ignores all certificate errors.”** False: only specific network/transient OCSP errors per API.
3. **“Known REVOKED can still pass with SOFT_FAIL.”** False: REVOKED always rejects.
4. **“OCSP `unknown` is the same as `tryLater`.”** False: one is a certificate status, the other is a responder error.
5. **“NO_FALLBACK is safer because it makes fewer requests.”** Not necessarily: losing the alternate source can leave you without evidence.
6. **“`setRevocationEnabled(false)` guarantees no checker runs.”** False when a checker is explicitly added.
7. **“Empty `getSoftFailExceptions` proves the certificate is good.”** No: the checker may not have run or you may be inspecting the wrong instance/invocation.
8. **“OCSP `good` means the website is trustworthy.”** No: PKIX chain, identity, EKU, and algorithm constraints still apply.
9. **“A cached `good` response can be reused until the certificate expires.”** False: responses have their own validity windows.
10. **“Adding infinite retries improves reliability.”** False: causes availability/DoS issues without fixing a broken responder.
11. **“OCSP stapling means Java enforces it for all clients automatically.”** Depends on implementation and policy.
12. **“Use the same SOFT_FAIL policy for administrators and guests.”** Lacks risk tiering.
13. **“Validation success metrics prove revocation evidence was obtained.”** False: soft-fail can return success without evidence.
14. **“Cert not found in an arbitrary CRL means good.”** False: requires right scope, issuer, timestamps, and authority.
15. **“Catching UNDETERMINED outside and returning true equals PKIX SOFT_FAIL.”** False: loses the checker's security conditions and semantics.

## 15. Self-Check Questions

**1.** Are `UNDETERMINED_REVOCATION_STATUS` and `REVOKED` the same?  
**Answer:** No. Undetermined means insufficient evidence; revoked means confirmed revoked and must be rejected.

**2.** What causes does Java `SOFT_FAIL` allow?  
**Answer:** Network errors fetching OCSP/CRL and OCSP `internalError`/`tryLater`, subject to fallback constraints; not every error.

**3.** Does `SOFT_FAIL` make a certificate listed on a valid CRL trustworthy?  
**Answer:** No. The CRL lab returns reason `REVOKED` even with `SOFT_FAIL` enabled.

**4.** What is the role of `NO_FALLBACK`?  
**Answer:** Disables switching to the backup revocation source, making failure of the chosen channel decisive.

**5.** What does `PREFER_CRLS + NO_FALLBACK` mean?  
**Answer:** Prefer CRLs and do not fall back to OCSP.

**6.** Why did `setRevocationEnabled(false)` in the example still check OCSP?  
**Answer:** Because a `PKIXRevocationChecker` was explicitly added to `PKIXParameters`, and the API specifies it runs regardless of that flag.

**7.** What is `getSoftFailExceptions()` used for?  
**Answer:** Reading errors ignored by the checker due to `SOFT_FAIL`, aiding auditing when inspecting the right instance after validation.

**8.** Can a cached OCSP `good` response past `nextUpdate` still report “verified now”?  
**Answer:** No; fresh evidence must be retrieved or a bounded degraded exception applied.

**9.** Why do high-privilege mTLS services lean toward hard-fail?  
**Answer:** Accepting a CA-revoked credential can be far worse than a temporary outage, especially if an attacker deliberately blocks the responder.

**10.** Why can't you extrapolate an entire JSSE TLS client from a `CertPathValidator` lab?  
**Answer:** Trust managers, revocation config, providers, and TLS policies differ; you must test along the actual production call path.

## Summary

```text
OCSP/CRL:
  VALID not-revoked evidence -> continue PKIX
  REVOKED evidence           -> REJECT
  UNDETERMINED               -> requires explicit policy

Java PKIXRevocationChecker.SOFT_FAIL:
  only ignores errors within the permitted scope
  never ignores REVOKED / bad chain / invalid signature
  affected by NO_FALLBACK / PREFER_CRLS
  getSoftFailExceptions helps observe ignored errors

Trade-off:
  HARD_FAIL -> better defense against network-disruption bypass,
               but carries outage risk
  SOFT_FAIL -> improves availability,
               but may accept a revoked cert if
               evidence is blocked or unreachable

Safe practice:
  classify privilege -> choose policy -> verified fallback/caching
  -> metrics/audit -> bound soft-fail -> test with real revoked certs.
```

**Key takeaway:** `SOFT_FAIL` does not mean “certificate confirmed good”. It is **a risk-bearing exception when revocation status cannot be fetched**. If used, be explicit about its scope, duration, monitoring, and strict rejection whenever evidence confirms `REVOKED`.

## Official References

- [Oracle Java 17 — PKIXRevocationChecker](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXRevocationChecker.html): OCSP/CRL, fallback, `getSoftFailExceptions`, cloning, and thread-safety.
- [Oracle Java 17 — PKIXRevocationChecker.Option](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXRevocationChecker.Option.html): exact options `SOFT_FAIL`, `NO_FALLBACK`, `PREFER_CRLS`, `ONLY_END_ENTITY`.
- [Oracle Java 17 — CertPathValidatorException.BasicReason](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidatorException.BasicReason.html): `REVOKED` and `UNDETERMINED_REVOCATION_STATUS`.
- [Oracle Java 17 — PKIXParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXParameters.html): trust anchors and cert-path checkers.
- [Oracle Java 17 — Java PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/17/security/java-pki-programmers-guide.html): using `PKIXRevocationChecker` with validator/builder.
- [RFC 5280 — Certificate/CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): CRL profile, path validation, and revocation.
- [RFC 6960 — OCSP](https://www.rfc-editor.org/rfc/rfc6960): good/revoked/unknown, error responses, freshness/authorized responder.
- [RFC 7633 — TLS Feature Extension](https://www.rfc-editor.org/rfc/rfc7633): TLS feature/must-staple, a mechanism distinct from Java `SOFT_FAIL`.
