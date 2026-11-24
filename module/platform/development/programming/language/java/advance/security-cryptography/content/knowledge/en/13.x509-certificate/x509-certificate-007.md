# 13.7. Distinguishing checkValidity, Certificate Signature verify, and Trust Validation

**An X.509 certificate can be unexpired and have a completely valid cryptographic signature, yet still not be trusted to connect to the server you intend to reach.** This is essential to understand before using `java.security.cert.X509Certificate` in Java.

Three operations are frequently conflated:

1. **`certificate.checkValidity()`**: checks whether **the current time** falls within `notBefore`–`notAfter` of **a specific certificate**.
2. **`certificate.verify(issuerPublicKey)`**: checks whether **the digital signature on that certificate itself** is valid for **the supplied public key**.
3. **Trust validation (certificate path validation / PKIX trust validation)**: determines whether there is **a valid certification path from the target certificate through intermediate CAs to a pre-accepted trust anchor**, while also satisfying policies on time, CA constraints, algorithms, intended usage, revocation, and related restrictions.

When the target is an HTTPS server, there is **yet another** requirement: the validated certificate must represent **the exact server name the client intends to reach**, such as `api.example.com`. And during a TLS handshake, the server must prove possession of the corresponding private key per protocol. Therefore, none of those three operations should **ever be used in isolation as a substitute for complete TLS/PKIX verification**.

## 1. Objectives and Map of the Three Verification Layers

After this lesson, you can:

- Read `notBefore`, `notAfter`, and apply `checkValidity()`/`checkValidity(Date)` properly.
- Use `verify(PublicKey)` accurately as an X.509 signature check with an issuer's key, **not** a check of whether the certificate is trusted.
- Understand why a **self-signed** certificate created by an attacker can still pass both checks above.
- Explain `TrustAnchor`, `KeyStore`/truststore, `CertPath`, `CertPathValidator`, `CertPathBuilder`, and `PKIXParameters`.
- Distinguish a cryptographically valid chain, a trusted path, valid certificate policies, and exact application identity.
- Determine how to handle CA certificates, `BasicConstraints`, `KeyUsage`, `ExtendedKeyUsage`, `SubjectAlternativeName`, policies, revocation, and hostnames.
- Write and run a Java 17+ demonstration using the default truststore, showing that signature/time validity differs from root trust.
- Recognize anti-patterns: trust-all, trusting self-signatures, creating a trust anchor from a client-supplied certificate, skipping hostname verification, and disabling revocation without evaluation.
- Know when to delegate certificate validation to the **JSSE/HttpClient/TLS stack** rather than writing a custom validator.

### 1.1. Comparison Table Upfront

| Question | API or mechanism | What does it answer? | What does it **not** prove? |
| --- | --- | --- | --- |
| Is the certificate within its time window? | `X509Certificate.checkValidity()` | A date falls within `notBefore ≤ date ≤ notAfter` per the API check | Signature, issuer, trust, hostname, permissions |
| Was the certificate content validly signed by the issuer? | `X509Certificate.verify(issuerPublicKey)` | The signature over `tbsCertificate` is valid for the given key | Whether the issuer key is trusted, CA chain is right, cert is unexpired, or hostname |
| Can the target certificate be trusted per config/policy? | `CertPathValidator("PKIX")` and `TrustAnchor`; or TLS trust manager | A PKIX path satisfies validation checks up to a trusted anchor | Exact HTTPS service name without endpoint identity check, or app authorization |
| Is this really the server `api.example.com`? | Endpoint identification/hostname validation in TLS/JSSE | Certificate identity matches **the name the client intends to call** | That the user/app is authorized for every resource |
| Does the server hold the private key matching the certificate? | Proof in the TLS handshake such as `CertificateVerify` in TLS 1.3 | Proof of signing key possession in the session and handshake binding | Business authorization, anti-replay of application requests |
| Is the client authorized to perform the operation? | Application authorization | Authenticated principal has rights on resource/action/tenant | These guarantees never come from `checkValidity`/`verify` |

One rule to remember: **“Unexpired” is not “valid signature”; “valid signature” is not “trusted”; “trusted” is not “right target and authorized”.**

## 2. Minimal X.509 Certificate Structure to Understand

An X.509 certificate typically contains:

```text
Certificate
  tbsCertificate  (to-be-signed certificate)
    version
    serialNumber
    signature algorithm identifier
    issuer name
    validity
      notBefore
      notAfter
    subject name
    subjectPublicKeyInfo
      public key algorithm
      public key bytes
    extensions
      BasicConstraints
      KeyUsage
      ExtendedKeyUsage
      SubjectAlternativeName
      SubjectKeyIdentifier / AuthorityKeyIdentifier
      policies / name constraints / CRL or OCSP metadata...
  signatureAlgorithm
  signatureValue
```

When a CA issues a certificate to a server, the CA **signs the `tbsCertificate` contents** using the CA's private signing key. The server receives the certificate with its assigned public key; the client can verify the signature with **the corresponding CA public key** if it has the issuer certificate.

For example:

```text
Root CA (pre-stored as trusted)
   subject = Example Root CA
   public key = K_root_public
           |
           | signs Intermediate CA certificate
           v
Intermediate CA
   issuer = Example Root CA
   public key = K_intermediate_public
           |
           | signs api.example.com certificate
           v
Leaf / end-entity certificate
   issuer = Example Intermediate CA
   SAN = DNS:api.example.com
   public key = K_server_public
```

To trust the server, checking only the leaf's signature with the intermediate's public key is insufficient. The client must continue checking **the intermediate's issuer**, constraint chains, trusted anchors, constraints, and **the exact server name**.

### 2.1. Self-Issued, Self-Signed, and Trusted Are Not Synonyms

- **Self-issued:** subject name matches issuer name. This concerns only name metadata; it does not prove self-signing.
- **Self-signed:** the certificate's signature can be verified using **the certificate's own public key** (and in typical usage, subject/issuer also match).
- **Trusted:** a trust policy, truststore, or out-of-band configuration has **accepted** that certificate/key as an anchor for the intended purpose.

A root CA in a truststore is usually self-signed; **an attacker can also create a valid self-signed root using their own key**. Self-signature proves only cryptographic consistency with that public key, not that the CA is trustworthy.

### 2.2. Matching Issuer DN Is Not Enough

Even if:

```text
leaf.issuer == intermediate.subject
```

that is still insufficient. Two different CAs can share the same name (or the same name across a key rotation). You must select the right signing certificate/key, verify the signature, and check **the entire path** per PKIX. `AuthorityKeyIdentifier`/`SubjectKeyIdentifier` extensions can assist path building, yet do not replace signatures or trust policies.

## 3. What Does `checkValidity()` Actually Check?

Java provides:

```java
certificate.checkValidity();
certificate.checkValidity(someDate);
```

`checkValidity()` uses the current time from the system clock. `checkValidity(Date)` checks against a caller-specified timestamp. If the certificate passes, it means the evaluated date **falls within the `notBefore` to `notAfter` window of that certificate itself**.

Specific exceptions:
- `CertificateNotYetValidException`: evaluation time is **before `notBefore`**.
- `CertificateExpiredException`: evaluation time is **after `notAfter`**.

API-only illustrative snippet (assuming `cert` is an already-parsed `X509Certificate`):

```java
try {
    cert.checkValidity();
    System.out.println("Certificate is within its validity interval");
} catch (java.security.cert.CertificateExpiredException expired) {
    System.out.println("Certificate expired");
} catch (java.security.cert.CertificateNotYetValidException notYet) {
    System.out.println("Certificate is not yet valid");
}
```

This is a **snippet depending on `cert`**, not a complete program; the full standalone program is in Section 10.

### 3.1. Do Not Confuse It with Determining Trustworthiness

`checkValidity()` does **not**:
- Check the certificate's digital signature.
- Check whether any CA signed the certificate.
- Check a chain leading to a configured trust anchor.
- Check whether the CA has `BasicConstraints: CA=true` or `KeyUsage: keyCertSign`.
- Check whether the server name in SAN matches the hostname.
- Check whether the certificate has been revoked.
- Check whether the signature algorithm or key size meets policy.
- Check whether the certificate has the proper `serverAuth` or `clientAuth` purpose.
- Prove the peer holds the corresponding private key.

Put plainly: **a self-signed certificate generated by Mallory today with a one-year validity will pass `checkValidity()` immediately**. That gives Alice zero reason to trust Mallory as `bank.example.com`.

### 3.2. Checking at Another Timestamp

`checkValidity(Date)` is useful when simulating a timestamp for testing, yet changing the check date does not turn an expired certificate into a valid one for production protocols. Historical signature verification, timestamps, and signing-time policies have their own requirements.

For example:

```java
Date reference = new Date();
cert.checkValidity(reference);
```

For active TLS, clients generally require the certificate to be valid under handshake-time policy. If the client clock is skewed, results may be wrong; operations should synchronize clocks rather than unconditionally relaxing validation.

### 3.3. CA Certificates Also Expire

Checking only `leaf.checkValidity()` misses the validity windows of **intermediate CA certificates**. PKIX path validation evaluates a chain of multiple certificates under specific rules. Trust anchors have special configuration status, and time/constraint checks on anchors may differ from certificates within the path: never assume “the path validator always calls `checkValidity` on the root just like the leaf”.

## 4. What Does `verify(PublicKey)` Actually Check?

`X509Certificate.verify(PublicKey key)` uses **the public key supplied by the caller** to verify the signature on the certificate.

For a leaf whose issuer is an intermediate:

```java
leaf.verify(intermediate.getPublicKey());
```

For an intermediate signed by a root:

```java
intermediate.verify(root.getPublicKey());
```

For a self-signed certificate:

```java
selfSignedRoot.verify(selfSignedRoot.getPublicKey());
```

Cryptographically, the operation checks that `signatureValue` matches `tbsCertificate`, the signature algorithm, and the supplied public key. It never asks “where did this public key come from?”, “is this CA allowed to sign certificates?”, or “is this subject the intended peer?”.

### 4.1. A Valid Signature Can Still Be Untrusted

Suppose Mallory:
1. Generates her own RSA/EC/Ed25519 key pair.
2. Creates a self-signed certificate for `CN=api.example.com`, setting `notBefore` to yesterday and `notAfter` to next year.
3. Self-signs `tbsCertificate` with her own private key.
4. Sends the certificate to Alice.

Alice calls:

```java
malloryCert.checkValidity();
malloryCert.verify(malloryCert.getPublicKey());
```

Both checks **can succeed**. Yet nothing binds Mallory's public key to `api.example.com` under Alice's trust policy. If Alice accepts after those two lines, Alice has skipped **certificate origin authentication** and is vulnerable to MITM.

**An even worse bug:** an application reads a peer-sent certificate and always calls `verify(peerCertificate.getPublicKey())`. For a CA-signed leaf, that usually fails because the leaf is not self-signed; for an attacker's self-signed certificate, it can succeed. This inverts trust-checking logic.

### 4.2. Does `verify` Check Expiration?

No. An expired certificate can still have a completely valid digital signature. The signature states that the certificate contents were signed by a key; it does not decide whether the certificate is still permitted for use right now.

Conversely, an unexpired certificate whose `tbsCertificate` was altered after signing or verified with the wrong public key will be rejected by `verify`.

### 4.3. Does `verify` Check CA/KeyUsage?

Not enough. Even when an intermediate certificate genuinely has a valid signature from a key, you must still determine whether the issuer was allowed to sign certificates under `BasicConstraints`, `KeyUsage`, and other path/policy constraints.

For example:
- An end-entity certificate with `BasicConstraints: CA=false` cannot automatically serve as a valid intermediate merely because it contains a public key capable of verifying a signature.
- A chain with too many CAs beneath a CA with `pathLenConstraint` violates policy even though every individual signature is valid.
- Name constraints can forbid an intermediate from issuing certificates for a particular domain.

This is why you must **never implement path validation with a loop of `cert.verify(issuerKey)` returning true**.

### 4.4. Certificate Signature vs. TLS Handshake Signature

Verifying an X.509 certificate signature establishes that the certificate was signed by **the issuer**. It does not directly prove the connecting server **holds the leaf certificate's private key**.

In TLS 1.3 using certificate authentication, the `CertificateVerify` message proves possession of the corresponding private signing key over the protocol-defined handshake context. `Finished` further authenticates the transcript with handshake secrets. Thus, calling `leaf.verify(issuerPublicKey)` when parsing a PEM **does not replace a full TLS handshake**.

## 5. Trust Validation Is a **Path Validation** Problem

PKI relies on a pre-configured trust relationship:

```text
                 TRUST CONFIGURATION
               (KeyStore / Trust Anchors)
                           |
                       Root CA
                       (trusted)
                           |
                      verifies/signs
                           |
                    Intermediate CA
                    (CA constraints)
                           |
                      verifies/signs
                           |
                      Leaf certificate
                      (server identity)
                           |
               Must additionally match:
                  requested hostname
                  intended key usage/EKU
                  application security policy
```

In Java, the key classes are:

- `KeyStore`: container for certificate/key entries; a truststore is the standard way to configure trusted CAs.
- `TrustAnchor`: represents a root certificate or CA name + public key **explicitly trusted** by the operator.
- `CertPath`: list of certificates **from target/leaf toward the issuer**, in the order expected by the provider; typically **excludes the trust anchor**.
- `CertPathValidator` with algorithm `PKIX`: validates an existing path against trust configuration and constraints.
- `CertPathBuilder`: finds or builds a certification path from certificate stores/candidate chains/constraints.
- `PKIXParameters` / `PKIXBuilderParameters`: trust anchor set, evaluation time, certificate policies, revocation settings, and additional checkers/constraints.
- `X509TrustManager` / `X509ExtendedTrustManager`: JSSE component performing certificate-chain trust decisions in TLS per provider/session context.

**There are three distinct problems:** *finding a chain*, *validating a chain*, and *matching the certificate identity to the service the application intends to reach*. No single API necessarily solves all three.

### 5.1. `CertPath` Structure and Trust Anchor

Example chain:

```text
Certificate path (passed to validator):
    [leaf api.example.com, intermediate Example Issuer]

Trust anchor (trust configuration outside the path):
    Example Root CA
```

The PKIX validator verifies the leaf with the intermediate's key and the intermediate against the corresponding path/anchor, while enforcing all configured constraints.

**Never** place a root certificate from the client's own packet into:

```java
// Anti-pattern: root certificate comes only from untrusted network input.
new TrustAnchor(untrustedRootSentByPeer, null);
```

and claim trust because `CertPathValidator` passed. Doing so effectively **trusts an adversary-chosen CA**. Trust anchors must come from a verified truststore or configuration channel with appropriate policy.

### 5.2. What PKIX Can Check

With proper configuration/implementation, PKIX path validation examines:
- Signatures of certificates in the chain and linkage to issuer/trust anchor.
- Validity windows of certificates in the path at the evaluation time.
- `BasicConstraints`, `KeyUsage`, and whether each certificate is permitted to act as a CA.
- Path length constraints, name constraints, and recognized/critical extensions.
- Whether certificates/algorithms/key types satisfy validator/provider policies and optional checkers.
- Certificate policies and specific constraints when configured.
- Revocation via CRL/OCSP or equivalent mechanisms **when enabled and configured per policy**.

**However, pure PKIX path validation does not inherently know whether the application intends to connect to `api.example.com` or `mail.example.com`.** Hostname/endpoint identification requires additional application/TLS policy.

### 5.3. Path Building Differs from Path Validation

`CertPathBuilder` may need a set of candidate intermediate certificates, CA stores, or AIA retrieval depending on provider/config. `CertPathValidator` is given an already-determined path and applies validation rules.

Do not assume the JDK will automatically download every intermediate from the network for you. If an intermediate is missing and the builder has no configured source/retrieval mechanism, a theoretically valid certificate may still fail to build a chain.

With cross-signing, multiple paths to different roots can exist; the path builder must choose a path matching anchors/policies. Matching issuer/subject strings is not enough to build a correct, secure path manually.

## 6. A Trust Anchor Is Not the Result of `verify`

### 6.1. A Trust Anchor Is a Pre-Established Trust Decision

A root CA in a truststore is placed into a trusted state by the system or administrator for a defined scope of use. That is an **operational/policy decision**, not a mathematical consequence of self-signing.

An attacker can:
- Generate a key pair and self-signed X.509 certificate.
- Set valid `notBefore`/`notAfter` dates.
- Set a subject matching a reputable authority's name.
- Self-verify the signature with their own public key.

Yet Alice has no reason to trust that certificate as a trust anchor without an independent, trustworthy distribution/verification channel.

### 6.2. Truststore Misconfiguration Is a Real-World Bug

Anti-patterns:
- Loading `cacerts` or an empty truststore, and if validation fails, “auto-adding the server certificate to the truststore”.
- Accepting all self-signed certificates.
- Catching `CertificateException` and ignoring it.
- Using a company-wide truststore that accidentally grants trust to an out-of-scope CA.
- Pinning a public key captured on first connection without handling first-connection MITM, yet claiming it equals CA authentication.

For an internal CA, add the CA certificate to a dedicated truststore **only after verifying it via a secure administrative channel**. Handshakes must still verify the chain, endpoint identity, key usages, and rotation/revocation per policy.

### 6.3. Be Careful with Roots Sent Along by the Peer

A TLS server may send a certificate chain and sometimes include the root. A copy of a root transmitted over the network **does not become trusted** merely because the server sent it. The client must match the certification path against pre-configured trust anchors, never “auto-grant trust” to a root from a packet.

## 7. Hostname and Service Identity: A Separate Layer from PKIX

Suppose the client calls:

```text
https://payments.example.com
```

The server presents a certificate with a completely valid chain to a public CA, yet `SubjectAlternativeName` contains:

```text
DNS:files.example.com
```

All of:
- `checkValidity()`,
- `verify(issuerPublicKey)`,
- and even **PKIX path validation** to a valid trust anchor

can pass, while the client **must still reject the certificate for `files.example.com`** because the application expected `payments.example.com`.

### 7.1. Expected Identity Must Be Determined by the Client

Never take the “expected hostname” from an untrusted server-supplied field and ask whether the certificate matches it. If the client intends to connect to `payments.example.com`, that exact name is the reference identity from the target URL or verified service configuration.

Principles:
- DNS names are generally checked in **SAN `dNSName`** per the applicable TLS/service identity standard.
- Connections to IP literals must follow **`iPAddress` SAN** rules, never comparing CN strings or reverse DNS to accept.
- Wildcards, IDNA, and canonicalization must follow library/standard rules; never write custom `endsWith(".example.com")`.
- `CN` in subject should not be treated as a default fallback for modern SANs.
- SNI helps the server pick an appropriate certificate; it is **not** proof that the certificate matches the hostname or is trusted.

### 7.2. Endpoint Identification in JSSE

When using standard HTTPS clients, let the TLS stack perform certificate-chain validation and hostname validation. For example, Java 17's `java.net.http.HttpClient` with default settings uses appropriate TLS verification; **never** disable it with insecure options.

If using `SSLSocket` directly in special cases, ensure endpoint identification (e.g., `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` for HTTPS connections), the right expected host, trust manager, and client/server mode. Directly calling `X509TrustManager.checkServerTrusted(...)` on a certificate array **without endpoint context** usually **does not perform hostname validation**.

### 7.3. Steps for TLS 1.3 Server Authentication

Conceptual diagram:

```text
Client wants: payments.example.com
   |
   v
TLS handshake receives certificate chain
   |
   +--> PKIX / trust manager checks:
   |      signatures, path, anchors, constraints, validity,
   |      revocation/policies according to configuration
   |
   +--> Endpoint identity check:
   |      SAN matches payments.example.com
   |
   +--> TLS handshake proof of possession / transcript:
   |      CertificateVerify and Finished as defined by TLS 1.3
   |
   +--> Security policy:
          key/algorithm rules, TLS version, application authorization
   |
   v
Only then treat channel as connected to expected server
```

**A valid certificate does not by itself create a secure TLS channel.** You must also ensure handshake transcript integrity, key agreement, record protection, and protocol-level identity.

## 8. Revocation: An “Unexpired” Certificate Can Still Be Revoked

A certificate can be **revoked by the CA before `notAfter`**, for instance due to private key compromise, loss of subject authorization, or CA misissuance.

`checkValidity()` only checks the time window; `verify(...)` checks the existing signature; neither **looks up revocation status**.

Common mechanisms:
- **CRL (Certificate Revocation List)**: signed list of revoked certificates published by the CA.
- **OCSP (Online Certificate Status Protocol)**: querying certificate status via a responder per profile.
- **OCSP stapling** and related TLS policies, depending on client/server stack.
- **Short-lived certificates** or private PKI policies reduce exposure windows, though they do not eliminate all compromise scenarios.

### 8.1. `PKIXParameters.setRevocationEnabled(...)`

`PKIXParameters` provides a revocation-checking flag along with `PKIXRevocationChecker`/`CertStore` mechanisms, subject to config and provider capabilities. **Enabling the flag does not guarantee the system has complete CRL/OCSP data or an error-handling policy.** Conversely, calling:

```java
params.setRevocationEnabled(false);
```

**intentionally disables** revocation checking for that PKIX run. The example in Section 10 includes this line **solely for offline, network-independent demonstration**, so never treat it as a default production setting.

Production systems must decide:
- When OCSP/CRL cannot be reached, fail closed or accept under specific exceptions?
- Are CRL/staple age limits and caching policies enforced?
- How is network egress from the trust validator controlled?
- With an internal CA, how does the system issue short-lived/rotated certificates and handle revocation?
- Do incident monitoring and alerts protect identity/certificate data?

If a set of systems uses mTLS with a private CA, failing to configure revocation and rotation can allow an actually revoked certificate to remain accepted until `notAfter`.

## 9. CA, Leaf, and Certificate Extension Policies

### 9.1. BasicConstraints

An intermediate CA generally requires `BasicConstraints: CA=true`. A leaf server certificate is generally `CA=false`. `pathLenConstraint` caps the number of non-self-issued subordinate CAs beneath it per standard rules. `verify` does not replace checking this constraint.

### 9.2. KeyUsage

A CA certificate typically has `keyCertSign` to be used for signing certificates. Leaves have other key usages depending on the scheme, such as `digitalSignature` to prove possession in TLS 1.3. Never infer from a valid certificate signature that a given key usage is permitted.

### 9.3. ExtendedKeyUsage (EKU)

A certificate for a TLS server may need `id-kp-serverAuth`; a client certificate for mTLS may need `id-kp-clientAuth`. Enforcing specific EKUs depends on protocol, policy, and implementation. `checkValidity()` does not know what purpose the service uses the certificate for; `verify(...)` does not check EKU for you either.

### 9.4. Critical Extensions and Name Constraints

X.509 extensions marked **critical** must be understood and enforced per PKIX. Validators must never silently ignore critical extensions affecting security policy. CA name constraints can restrict which domains a certificate may be issued for; checking only step-by-step signatures easily misses them.

### 9.5. Algorithm/Key Strength

A mathematically valid signature using a weakened algorithm or insufficient key size does not mean it is **permitted today**. Systems must enforce JDK/provider algorithm constraints, TLS security policies, and organizational standards, updating as standards evolve. Never automatically fall back to MD5/SHA-1 or disable constraints to “accept legacy certificates”.

## 10. Java 17+: Demonstrating the Three Checks Using the Built-In Truststore

The following program is **a complete class that compiles and runs on Java 17+**, downloading nothing from the Internet and writing no files.

It performs reproducible checks using CA certificates **already present in the Java runtime's default truststore**:

1. Finds two **self-signed, currently valid CA certificates with distinct public keys** in the default configured trust manager.
2. On the first root, calls `checkValidity()` and `verify(root.getPublicKey())`.
3. Shows this root is present in the trusted issuers list, yet **absent** from an empty trust set.
4. Attempts to validate the first certificate using `CertPathValidator("PKIX")` **with only the second, unrelated root as the trust anchor**: validation fails. This demonstrates that even a valid self-signature **does not chain to a different anchor**.
5. Shows that the program **has not checked any hostname**. This is not a complete example for authenticating an HTTPS server.

**Environment note:** the program assumes the default truststore contains **at least two currently valid self-signed root CAs with distinct public keys**. Standard JDKs have many such CAs. If an environment uses a minimal/empty truststore, the program fails explicitly rather than downloading or trusting an unknown root. Certificate order in `getAcceptedIssuers()` is unspecified; the demo avoids printing a specific subject.

File `X509ChecksDemo.java`:

```java
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertPathValidatorException;
import java.security.cert.CertificateEncodingException;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import javax.net.ssl.TrustManager;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.X509TrustManager;

public class X509ChecksDemo {

    static X509TrustManager defaultTrustManager()
            throws GeneralSecurityException {
        TrustManagerFactory factory = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
        );
        factory.init((KeyStore) null); // Runtime's configured default trust store.

        for (TrustManager manager : factory.getTrustManagers()) {
            if (manager instanceof X509TrustManager x509) {
                return x509;
            }
        }
        throw new GeneralSecurityException("No X509 trust manager");
    }

    static boolean selfSignedAndCurrentlyValid(X509Certificate cert) {
        try {
            cert.checkValidity();
            if (!cert.getSubjectX500Principal().equals(
                    cert.getIssuerX500Principal())) {
                return false;
            }
            cert.verify(cert.getPublicKey());
            return true;
        } catch (GeneralSecurityException e) {
            return false;
        }
    }

    static X509Certificate[] chooseRoots(X509TrustManager manager) {
        X509Certificate first = null;

        for (X509Certificate cert : manager.getAcceptedIssuers()) {
            if (!selfSignedAndCurrentlyValid(cert)) {
                continue;
            }
            if (first == null) {
                first = cert;
                continue;
            }
            if (!Arrays.equals(
                    first.getPublicKey().getEncoded(),
                    cert.getPublicKey().getEncoded())) {
                return new X509Certificate[] {first, cert};
            }
        }
        throw new IllegalStateException(
                "Need two distinct currently valid CA certificates"
        );
    }

    static boolean isInTrustSet(
            X509Certificate candidate,
            X509Certificate[] trusted
    ) throws CertificateEncodingException {
        for (X509Certificate c : trusted) {
            if (Arrays.equals(candidate.getEncoded(), c.getEncoded())) {
                return true;
            }
        }
        return false;
    }

    static boolean pkixValidWithUnrelatedAnchor(
            X509Certificate candidate,
            X509Certificate unrelated
    ) throws GeneralSecurityException {
        // Deliberately use this self-signed CA as path target,
        // with a different CA as the only configured trust anchor.
        // This is a negative trust-path test, not normal leaf validation.
        CertPath path = CertificateFactory.getInstance("X.509")
                .generateCertPath(List.of(candidate));

        PKIXParameters params = new PKIXParameters(
                Set.of(new TrustAnchor(unrelated, null))
        );
        // OFFLINE DEMO ONLY: intentionally disables revocation checking.
        params.setRevocationEnabled(false);

        try {
            CertPathValidator.getInstance("PKIX").validate(path, params);
            return true;
        } catch (CertPathValidatorException expected) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        X509TrustManager manager = defaultTrustManager();
        X509Certificate[] roots = chooseRoots(manager);
        X509Certificate selected = roots[0];

        selected.checkValidity();
        selected.verify(selected.getPublicKey());

        System.out.println("Certificate time validity: true");
        System.out.println("Self-signature verifies: true");
        System.out.println("Listed in configured trust anchors: " +
                isInTrustSet(selected, manager.getAcceptedIssuers()));
        System.out.println("Listed in empty trust store: " +
                isInTrustSet(selected, new X509Certificate[0]));
        System.out.println("PKIX validates against unrelated root: " +
                pkixValidWithUnrelatedAnchor(selected, roots[1]));
        System.out.println("This program checked hostname: false");
    }
}
```

Compile and run:

```bash
javac X509ChecksDemo.java
java X509ChecksDemo
```

Stdout verified with Java 17-compatible APIs (on a JDK whose truststore has suitable roots):

```text
Certificate time validity: true
Self-signature verifies: true
Listed in configured trust anchors: true
Listed in empty trust store: false
PKIX validates against unrelated root: false
This program checked hostname: false
```

### 10.1. Interpreting the Results Properly

- `Certificate time validity: true`: `selected` is within its current validity window. It proves nothing about a server's identity.
- `Self-signature verifies: true`: the root's self-signed signature verifies against its own public key; no other CA vouches for the certificate from this operation.
- `Listed in configured trust anchors: true`: the root was **pre-configured as trusted by the runtime**; that is distinct from having a valid self-signature.
- `Listed in empty trust store: false`: without approved trust anchors, a self-signature does not put a certificate into the trusted set.
- `PKIX validates against unrelated root: false`: another root, even if trusted itself by the runtime, **cannot arbitrarily vouch for this certificate**. Path validation depends on **the exact chain and exact anchor**.
- `This program checked hostname: false`: the program has no expected service hostname; even with a trusted CA root, this is **not a TLS server check**.

**Demo limitations:** `isInTrustSet` only checks membership in an array to illustrate the trust anchor definition; **never use it as certificate validation for a leaf**. `pkixValidWithUnrelatedAnchor` intentionally passes a self-signed root as the path target to demonstrate failure; normal systems validate **leaf → intermediates** up to a trusted root.

### 10.2. Evidence Separating Time, Signature, and Trust

Consider three hypotheses:

```text
A. Certificate still within dates?
   -> checkValidity()          [certificate-local test]

B. Certificate signature matches supplied key?
   -> verify(issuerPublicKey)  [cryptographic signature test]

C. Certificate chain accepted by configured PKI?
   -> CertPathValidator/JSSE   [trust-policy/path test]
      + HTTPS hostname match   [endpoint identity test]
```

A failure in A, B, or C can occur independently of the others. Chaining three methods with ad-hoc boolean operators does not replace all PKIX/TLS constraints.

## 11. Java PKIX: Validating a Real Chain Given Trusted Certificates

Suppose the application **has received and properly parsed** the variables:
- `leaf`: X.509 end-entity certificate of the service.
- `intermediate`: CA certificate that directly signed the leaf.
- `configuredTrustedRoot`: root CA obtained from **authorized configuration/truststore**, never from an untrusted packet.

The following is a **Java 17 snippet** requiring the variables above and appropriate imports; it is not a standalone program:

```java
// Imports for this snippet:
// import java.security.cert.*;
// import java.util.*;

CertPath path = CertificateFactory.getInstance("X.509")
        .generateCertPath(List.of(leaf, intermediate));
// Trust anchor is kept OUT of the certificate path.

Set<TrustAnchor> approvedAnchors =
        Set.of(new TrustAnchor(configuredTrustedRoot, null));

PKIXParameters params = new PKIXParameters(approvedAnchors);
// params may also define evaluation date, revocation configuration,
// trusted CertStores, policy constraints, and additional checkers.

// Do NOT disable revocation here for a real security policy.
// Configure PKIXRevocationChecker / CRL / OCSP facilities as required.

CertPathValidator validator = CertPathValidator.getInstance("PKIX");
validator.validate(path, params);

// This success means the supplied path satisfied the configured
// PKIX trust validation. It is NOT by itself HTTPS hostname validation.
```

To avoid misunderstandings:
- If the leaf was signed directly by the root, the path is typically `List.of(leaf)`, with the trust anchor kept separate.
- If there are two intermediates, pass them in order: leaf → intermediate closest to leaf → upper intermediate, **without** mixing the root into the path.
- If the chain lacks intermediates, build a proper path via `CertPathBuilder`/certificate stores per policy; never synthesize issuers by matching subject strings alone.
- Never construct `configuredTrustedRoot` from a certificate just sent by an attacker. Every downstream check becomes meaningless if the anchor lacks a trusted origin.
- PKIX enforces configured rules for BasicConstraints, key usage, policies, extensions, and revocation; never replace them with two `leaf.verify(...)` and `intermediate.verify(...)` calls.
- After validation, you still need **exact service/identity verification**, TLS handshake, application scope, and authorization.

### 11.1. Parsing a PEM or DER Certificate in Java

An X.509 `CertificateFactory` can read a certificate from a stream:

```java
// Snippet, requires java.nio.file.* and java.security.cert.* imports.
try (java.io.InputStream input =
             java.nio.file.Files.newInputStream(
                     java.nio.file.Path.of("server-cert.pem"))) {
    X509Certificate leaf = (X509Certificate)
            CertificateFactory.getInstance("X.509")
                    .generateCertificate(input);
}
```

This only **reads and parses the certificate**; it does not check trust. Never use `CertificateFactory.generateCertificate` as proof a server is trusted: the parser can parse an attacker-created certificate with valid ASN.1/X.509 structure.

When handling PEM bundles, multiple certificates may appear together; you need policies for ordering and path building. Certificate files and private key files are different types of artifacts—publicly sharing a root certificate does not mean its private signing key is public.

## 12. What a Java HTTPS Client Should Do in Production

When the goal is calling HTTPS, the best approach is usually **not** a custom class calling `checkValidity` and `verify`, but using the **standard JSSE/HTTP client**:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class SecureHttpExample {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.com/")
        ).GET().build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString()
        );
        System.out.println("HTTP status: " + response.statusCode());
    }
}
```

This is a **standalone program**, though it requires network access, DNS, and an active server; **no fixed stdout is assumed**. Its purpose is to show you can delegate certificate chain/hostname/TLS handshake duties to the standard client instead of writing a custom validator. Actual trust policy also depends on the JDK, TLS config, custom truststores, and system settings.

Do not do this:

```java
// ANTI-PATTERNS: not safe for production.
// TrustManager.checkServerTrusted(...) { /* do nothing */ }
// HostnameVerifier.verify(host, session) { return true; }
// Ignore SSLHandshakeException and continue insecurely.
```

If you encounter `SSLHandshakeException`/`PKIX path building failed`, find the cause: missing intermediate in chain, truststore lacking the right CA, expired certificate, server name mismatch, cipher/protocol policy, or revocation. Never “fix” it by disabling SSL verification.

### 12.1. Caution with Custom `SSLContext` and Truststores

If the application must trust an internal CA:
- Import the CA certificate **authenticated out-of-band** into a dedicated truststore, or use a properly configured standard trust manager.
- Verify that **only the intended CAs** and permitted scopes reside in the truststore; never add every client-submitted certificate to the truststore.
- Keep endpoint identification/hostname verification enabled.
- Define procedures for CA rotation, expiration, revocation, and truststore versioning.
- Test with real certificate chains and negative tests for wrong hostnames and untrusted roots.

If you replace `TrustManager` with an implementation that accepts all certificates, you may be **disabling entire chain validation** without realizing it.

## 13. Scenarios Distinguishing the Three Verification Levels

### Scenario A — Stranger's Self-Signed Certificate

`notBefore` yesterday, `notAfter` next year; valid self-signature; absent from truststore.

- `checkValidity()`: **pass**.
- `verify(cert.getPublicKey())`: **pass**.
- PKIX against a truststore without that root: **fail**.
- Conclusion: **not trusted to represent a server** merely because time and signature are valid.

### Scenario B — Certificate Signed by a Trusted CA, Yet Expired

- `checkValidity()`: **fail**, e.g., `CertificateExpiredException`.
- `verify(correctIssuerPublicKey)`: may **pass**; the signature still exists.
- Standard PKIX at current time: **fail** when leaf is outside its validity window.
- Conclusion: a valid signature does not “extend” a certificate's lifetime.

### Scenario C — Valid Leaf, Expired Intermediate

- `leaf.checkValidity()`: may pass.
- `leaf.verify(intermediate.getPublicKey())`: may pass.
- PKIX path validation: may **fail** because a certificate in the chain is invalid at evaluation time (barring standardized policy exceptions).
- Conclusion: never check only the leaf and forget intermediates.

### Scenario D — Invalid Signature or Wrong Issuer Key

- `checkValidity()`: may still pass.
- `verify(wrongPublicKey)`: **fail**.
- Corresponding PKIX path: rejected.
- Conclusion: validity does not prove the certificate is untampered or signed by the right signer.

### Scenario E — Valid Chain, Wrong Hostname

- `checkValidity()`: pass.
- `verify(issuerPublicKey)`: pass.
- PKIX path to trusted root: pass.
- Certificate SAN contains `files.example.com`, while the client calls `payments.example.com`: **TLS identity check fails**.
- Conclusion: a trusted chain does not mean the right peer.

### Scenario F — Certificate Revoked Mid-Lifecycle

- `checkValidity()`: may pass.
- `verify(issuerPublicKey)`: may pass.
- PKIX/TLS with **fully enforced revocation policy**: must handle the revoked state per policy.
- Conclusion: time and signature do not substitute for revocation status.

### Scenario G — Self-Signed Root Securely Pinned

- Root certificate has a valid self-signature and was **independently configured as trusted** after verifying its key/fingerprint.
- Path to root can be accepted if constraints and policies are satisfied.
- When used for HTTPS, SAN hostname and TLS proof of possession must still be verified.
- Conclusion: a root is a trust anchor due to **a grounded trust decision**, not its “self-signed” property.

### Scenario H — Right Server Certificate, Yet Unauthorized Application Action

- TLS handshake, certificate validation, and hostname all pass.
- User sends a request to an unauthorized resource.
- Application must return an authorization denial.
- Conclusion: trusting a server certificate does not grant clients all business permissions.

### Scenario I — Attacker Substitutes Their Own Certificate Chain

- If the application uses a root from **the payload** as `TrustAnchor`, the path may “succeed” under the attacker's root.
- If trust anchors come solely from verified configuration, the attacker's chain cannot link to a valid root.
- Conclusion: trust anchor provenance is an **invariant in the threat model**.

### Scenario J — CSR and Certificate Signing

A CSR with a valid signature proves the request matches the corresponding private key, yet does not prove a CA issued a trusted certificate. CSR parsing/verification is not certificate path validation. This is an analogous example of the difference between **cryptographic signature verification** and **a trust decision**.

## 14. Anti-Patterns to Recognize

| Error | Why it is wrong | Fix |
| --- | --- | --- |
| Calling only `cert.checkValidity()` and treating as “trusted” | Only checks the time window | PKIX/trust manager and expected identity |
| Calling only `cert.verify(cert.getPublicKey())` | May only verify an attacker's self-signature | Use the right issuer key; validate chain to a trusted anchor |
| Chaining `verify` calls by issuer string | Skips CA constraints, policies, revocation, path issues | Use `CertPathValidator/Builder` |
| Auto-trusting a self-signed root sent in the TLS chain | Attacker can send their own root | Load trust anchors from independent config |
| Calling `new TrustAnchor(receivedRoot, null)` | Trusts untrusted input | Use valid pinned/configured CAs |
| PKIX passes yet SAN hostname is ignored | Trusts certificate for a different domain | Endpoint identification |
| CN matches so SAN is ignored | Modern rules require SAN and standard matching | Use standard TLS hostname verification |
| Using a `HostnameVerifier` that always returns true | Loses verification of the right server | Use the default verifier |
| Always-accept `TrustManager` | Loses PKIX authentication, MITM risk | Use a standard trust manager |
| Permanently disabling revocation without policy | Fails to detect compromised certs promptly | Design CRL/OCSP/short-lived cert policy |
| Wrong CA key usage even though `verify` passes | Valid signature does not grant CA authority | Enforce BasicConstraints/KeyUsage via PKIX |
| Using a `CA=false` leaf cert to sign an intermediate | Wrong usage | Never replace PKIX with signature-only checks |
| Swallowing `CertificateExpiredException` | Expired certs get accepted | Enforce validity per policy |
| Ignoring `SSLHandshakeException` | May indicate active MITM or PKI misconfig | Diagnose chain/trust/name properly |
| Valid cert chain = server holds private key | CA signature does not prove handshake PoP | TLS certificate proof |
| PKIX passes = user authorized to call API | Trusting the server differs from app authorization | Enforce separate authorization |
| Logging full certs/key material and sensitive headers | Data exposure and retention issues | Log only necessary metadata per policy |

## 15. Testing Checklist for Java Certificate Validation

### 15.1. Unit Tests

- [ ] Unexpired certificate: `checkValidity()` passes; `expired`/`notYetValid` are distinguished properly.
- [ ] Test `checkValidity(Date)` with timestamps before/after to verify time logic without suppressing errors.
- [ ] `verify(correctIssuerPublicKey)` passes; `verify(wrongIssuerPublicKey)` fails.
- [ ] Newly generated **untrusted** self-signed certificate is rejected for production servers.
- [ ] X.509 certificate parser is never confused with trust validation.
- [ ] Validator rejects chains with invalid signatures, missing intermediates, exceeded path length, or `CA=false` at an issuer position.
- [ ] Critical extensions/KeyUsage/EKU/name constraints are handled per applicable policy.
- [ ] Trust anchors are controlled from configuration rather than arbitrarily copied from client requests.

### 15.2. HTTPS/mTLS Integration Tests

- [ ] Valid chain + matching SAN hostname is accepted per TLS policy.
- [ ] Valid chain + **wrong hostname** is rejected.
- [ ] Valid dates + untrusted self-signed cert is rejected.
- [ ] Valid leaf + expired intermediate is rejected per path policy.
- [ ] Revoked certificate is rejected when revocation policy requires it.
- [ ] Server failing to prove possession of the matching private key in handshake is rejected.
- [ ] Expired/replaced roots and key rotation are tested across truststores.
- [ ] Custom truststore does not disable hostname verification and is not “trust all”.
- [ ] mTLS client certificates map to the right principal and tenant/role; permissions are never granted solely because TLS succeeded.
- [ ] Weak algorithms/certificates are rejected per current security policy.

### 15.3. Operational QA

- [ ] Truststore CA list, update schedule, modification permissions, and audits are well defined.
- [ ] Clock/NTP synchronized; alerts exist for upcoming certificate expirations.
- [ ] Procedures exist for issuing/rotating certificates and recovering if an intermediate is replaced.
- [ ] Revocation, certificate lifetimes, and soft-fail/hard-fail rules align with the threat model.
- [ ] TLS error logs avoid exposing private keys, session keys, tokens, request bodies, and plaintext; include correlation IDs.
- [ ] Never use “insecure TLS” flags or trust-all as a temporary workaround for an incident.
- [ ] Internal CAs and public CAs have appropriately separated trust scopes.

## 16. Self-Check Questions

**1. Does passing `checkValidity()` prove the certificate was signed by a trusted CA?**  
No. It only checks the certificate's `notBefore/notAfter` at a given timestamp.

**2. Does passing `leaf.verify(issuer.getPublicKey())` prove the issuer is in the truststore?**  
No. It only verifies the signature against the key you supplied. Whether that key is trusted or authorized as a CA is a separate question.

**3. Why can an attacker's self-signed certificate pass both `checkValidity` and `verify`?**  
The attacker picks the validity dates and self-signs with the private key matching the certificate's own public key. There is no configured trust anchor or external identity binding.

**4. If a real root CA has a valid self-signature, is it trusted solely because of `verify(root.getPublicKey())`?**  
No. Trust rests on configuration and out-of-band verification; self-signing does not grant authority.

**5. For a leaf → intermediate → root certification path, which elements go into `CertPath`?**  
Typically `List.of(leaf, intermediate)`; the root is supplied separately as a `TrustAnchor` from a trusted source.

**6. If PKIX path validation passes, is the HTTPS hostname automatically valid?**  
No. You must compare the expected service name against the certificate identity per endpoint identification rules; standard TLS clients combine these steps.

**7. Why must you not take a root from the server's packet to build a `TrustAnchor`?**  
An attacker can generate and send their own root; building an anchor directly from untrusted input makes validator results no longer reflect client trust.

**8. A certificate is unexpired with a valid signature, yet revoked. Which two APIs can still pass?**  
`checkValidity()` and `verify(...)` can still pass. Revocation requires additional mechanisms/policies.

**9. What is the impact of `BasicConstraints: CA=false` on an intermediate certificate?**  
It cannot be used as an intermediate CA under valid PKIX; a mathematically valid signature does not grant certificate-signing authority.

**10. Is certificate `verify` proof that the server holds the private key during a TLS handshake?**  
No. The certificate signature was created by the issuer; TLS `CertificateVerify`/handshake authentication proves possession of the matching private key and binds the session.

**11. If the server certificate has SAN `files.example.com` while the client wants `payments.example.com`, what is the conclusion?**  
Even with a trusted chain and valid time/signature, endpoint identity fails and the connection must be rejected per HTTPS policy.

**12. Should you bypass certificate errors in production with a `TrustManager` that accepts all certificates?**  
No. It eliminates channel authentication and introduces MITM risk; fix the truststore, chain, SAN, clock, or valid configuration instead.

## 17. Memory Diagram

```text
                  X.509 CERTIFICATE FROM PEER
                             |
                             v
                checkValidity()?
                   /             \
               time OK       time NOT OK
                 |              reject
                 v
        verify(issuerPublicKey)?
             /              \
        signature OK      mismatch
             |              reject
             v
       PKIX path validation:
       - chain signatures / CA rules
       - constraints / validity / policies
       - trusted configured root
       - revocation as configured
             |
             v
       Endpoint identity:
       - expected HTTPS DNS/IP
       - SAN / protocol matching
             |
             v
       TLS handshake:
       - proof of key possession
       - transcript / Finished
             |
             v
       App authorization:
       - principal, tenant, resource, action
             |
             v
         ACCEPT ONLY IF POLICY SATISFIED

  WARNING: Diagram is a conceptual dependency list.
  Correct PKIX/JSSE validates many elements together;
  do not reimplement the protocol as ad-hoc sequential checks.
```

**Conclusion:** `checkValidity` checks **time**, `verify` checks **the certificate signature against a public key**, while “trusted” requires **a PKIX path to a pre-configured trust anchor** along with appropriate certificate and application constraints. For HTTPS, you must also verify **the exact hostname, TLS proof of possession, and authorization**. Never mistake two Java methods not throwing exceptions for “the certificate has been verified as trusted”.

### References

- RFC 5280 — *Internet X.509 Public Key Infrastructure Certificate and CRL Profile*: https://www.rfc-editor.org/rfc/rfc5280
- RFC 9525 — *Service Identity in TLS* (DNS/IP identification, name matching): https://www.rfc-editor.org/rfc/rfc9525
- RFC 8446 — *The Transport Layer Security (TLS) Protocol Version 1.3*: https://www.rfc-editor.org/rfc/rfc8446
- RFC 6960 — *X.509 Internet Public Key Infrastructure Online Certificate Status Protocol - OCSP*: https://www.rfc-editor.org/rfc/rfc6960
- Java SE 17, `X509Certificate`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html
- Java SE 17, `Certificate` / `verify(PublicKey)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/Certificate.html
- Java SE 17, `CertPathValidator`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html
- Java SE 17, `CertPathBuilder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathBuilder.html
- Java SE 17, `PKIXParameters` / `TrustAnchor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXParameters.html
- Java SE 17, `TrustManagerFactory`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html
- Java SE 17, `SSLParameters` / endpoint identification: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html
- Java SE 17, `HttpClient`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
