# 14.9. Limits of PKIX: Hostname Verification Is a Separate Step

## 1. The Problem: A Certificate from a Trusted CA May Not Belong to the Right Server

Suppose a Java application intends to call an API at `https://billing.example.test`. Over the wire, the server presents an X.509 certificate:

- Signed by a valid CA present in the client's configured set of trust anchors.
- Unexpired, with a certificate path and signatures that pass PKIX validation.
- Yet the certificate's **Subject Alternative Name (SAN)** contains only `DNS:service.example.test`, **not** `billing.example.test`.

If the developer merely calls `CertPathValidator.getInstance("PKIX").validate(...)` and concludes “right server”, the application can end up connected to **the wrong identity**. This is the mistake of collapsing two distinct problems into one:

1. **Path validation (PKIX):** can the certificate chain form a valid trust path to an accepted trust anchor while satisfying PKIX constraints and policies?
2. **Endpoint identification / hostname verification:** is that accepted certificate **bound to the DNS name or IP address the application actually intends to connect to**?

**Core takeaway:** `PKIX path valid = true` **does not imply** `hostname matches = true`. A valid TLS connection must satisfy **both conditions** per protocol, while the TLS handshake proves the server possesses the private key corresponding to the accepted certificate.

### Learning Objectives

After this lesson, you will know how to:

- Distinguish `CertPathBuilder`, `CertPathValidator`, `PKIXParameters`, and `TrustAnchor` from the hostname verification step.
- Understand why a valid trust path can still be presented for the **wrong hostname**.
- Identify SAN `dNSName` (type 2), `iPAddress` (type 7), wildcards, and the limits of `Common Name (CN)`.
- Write a Java 17+ example that **genuinely validates a PKIX chain** carrying only another hostname's SAN, and observe the boundary of that result.
- Configure `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` when using JSSE directly, without disabling hostname/trust verification.
- Build a test matrix covering **valid/invalid trust paths** and **matching/mismatching identities**, separating issuer errors from name mismatches.

## 2. Two Different Questions in TLS Authentication

### 2.1. What Does PKIX Path Validation Verify?

**PKIX** (*Public Key Infrastructure using X.509*) is the suite of standards for building and validating certificates. For a typical server certificate chain:

```text
Trust anchor / Root CA pre-trusted by client
           |
           | signs or delegates per CA hierarchy
           v
Intermediate CA (optional)
           |
           | signs leaf certificate
           v
Server leaf certificate
           |
           +-- Subject Public Key
           +-- Subject Alternative Name (SAN)
           +-- KeyUsage / ExtendedKeyUsage
           +-- Validity / signature algorithm / extensions
```

A **PKIX path validation** run with appropriate policy can inspect aspects such as:

- Each certificate's signature and issuer/subject linkage in the path.
- Path termination at a **trust anchor explicitly trusted by the application**, not an arbitrary random CA.
- Time validity (`notBefore`/`notAfter`) at the evaluation instant.
- `BasicConstraints`, CA depth, and `KeyUsage` for CA certification roles.
- Name constraints (`NameConstraints`), certificate policies, and algorithm/key strength per configuration and provider.
- Revocation status (CRL/OCSP) when properly configured and enabled.

**There is no single fixed set of guarantees for every `validate` call:** outcomes depend on trust anchors, PKIX parameters, cert stores, revocation policy, validation time, implementation/provider, and application context. In Java, the configuration you choose is part of your security requirements.

### 2.2. What Does Endpoint Identification Check?

When the application **intends** to connect to `billing.example.test`, the client must verify that the certificate contains a matching **reference identity**. HTTPS typically uses:

- **DNS-ID:** `subjectAltName` of type `dNSName` for a DNS hostname.
- **IP-ID:** `subjectAltName` of type `iPAddress` for a literal IP address.
- Matching rules for wildcards/IDNA defined by the protocol profile.

**The expected name must come from the trusted application/protocol side**, such as the hostname in the client-selected URI or a configured peer identity. Never take the expected name from the received certificate and check whether the certificate “contains that name”—that turns the check into a self-referential loop and fails to protect the destination the user intended to reach.

### 2.3. Conditions for a Secure Connection

```text
Initiate connection to client-trusted hostname H
                    |
                    v
Receive TLS peer's certificate chain
                    |
                    v
[1] Validate PKIX path to an allowed trust anchor?
       | no  --> FAIL: untrusted certificate path
       | yes
       v
[2] Verify endpoint identity H matches right SAN type?
       | no  --> FAIL: wrong server identity
       | yes
       v
[3] TLS handshake/policy/algorithms/key proof succeed?
       | no  --> FAIL
       | yes
       v
Only now accept the TLS channel per policy
and proceed to business authorization checks.
```

The diagram depicts **logical conditions**, without prescribing internal call ordering across all TLS providers. JSSE may coordinate path, endpoint, and handshake parameters together. Never split these manually into three separate steps when a high-level TLS API already enforces them safely.

## 3. Why Can a Valid Certificate Belong to the Wrong Host?

Consider three services:

```text
api.example.test
billing.example.test
files.example.test
```

A CA can issue **three individually valid certificates** for these three services. The fact that the client trusts the CA does not mean every certificate that CA issues represents **every name**.

Failure scenario:

1. A Java client connects to `billing.example.test`.
2. An attacker holds a valid certificate for `api.example.test` from a CA the client also trusts, or intercepts routing/peer addressing.
3. The client checks only the chain: signatures are valid, anchor is trusted, validity and PKIX constraints pass.
4. The client **skips hostname verification** and accepts a certificate with `DNS:api.example.test` as if it were valid for `billing.example.test`.

Even when an attacker **cannot obtain a forged certificate for billing**, they can misuse a genuine certificate for **another name** if the application checks only the chain. With hostname verification, the client must reject because the target identity does not match the SAN.

**Not merely a “rogue CA” issue:** checking the *right* CA is still insufficient without checking the name. And pinning a public key likewise requires a policy binding that key to the exact endpoint and scope, never turning any pinned key into a universal identity across all services.

## 4. PKIX in Java: Which API Does—and Does Not—Do What?

| API | Capability | Cannot be inferred from this call alone |
| --- | --- | --- |
| `CertificateFactory.getInstance("X.509")` | Parses DER/PEM, creates `X509Certificate` or `CertPath` | Does not verify trust chain or hostname. |
| `X509Certificate.checkValidity()` | Checks the certificate's own validity dates | Does not verify issuer, policy, or server identity. |
| `X509Certificate.verify(PublicKey)` | Checks certificate signature with a supplied key | Does not prove the key is trusted; does not check hostname. |
| `X509Certificate.getSubjectAlternativeNames()` | Reads the GeneralName list in the SAN extension | Only a **getter**, not a hostname verifier. |
| `CertPathBuilder.getInstance("PKIX")` | Finds a certificate path matching parameters/target selector and trust policy | Does not automatically take the target URL hostname to protect. |
| `CertPathValidator.getInstance("PKIX")` | Validates a specific `CertPath` under PKIX parameters | Does not automatically compare TLS connection hostname/IP with SAN. |
| `PKIXParameters` / `PKIXBuilderParameters` | Configures trust anchors, date, policy, revocation, cert stores, etc. | Has no built-in “this is my billing URL” check inside `validate`. |
| `TrustAnchor` | Represents a policy-permitted trusted CA/root | Does not verify that the anchor was provisioned by a trusted source. |
| `X509ExtendedTrustManager` + JSSE endpoint algorithm | Has full context during TLS handshake to coordinate trust and endpoint identification | Unsafe if a custom trust manager always passes, or if endpoint identification is left disabled. |
| `HttpClient` / `HttpsURLConnection` (HTTPS) | High-level TLS clients with certificate/hostname verification when safely configured | Loses guarantees if custom SSL/trust/hostname configuration bypasses checks. |

**Distinction between CertPathBuilder and CertPathValidator:** `Builder` discovers a valid path from available certificates/`CertStore`; `Validator` checks a **specific** supplied path. Whether built or validated, “valid path” never turns into “right DNS host” on its own.

### 4.1. A Trust Anchor Is a Security Decision

In the Java example, the program executes `new TrustAnchor(demoRootCertificate, null)`. That means **the program itself declares** that root to be a trusted anchor. The PKIX validator evaluates the chain under that given assumption; it **does not** magically verify why the program chose that root.

In production, trust anchors come from managed truststores/PKI policies: the JDK/system CA store, a securely provisioned internal truststore, or an approved verification/pinning mechanism. If an attacker can insert their own root CA into the truststore, paths to that root validate and break the trust model. **Truststore governance** is part of the security boundary.

### 4.2. PKIX Certificate Revocation Is Not Always Enabled Out of the Box

In Java, `PKIXParameters` exposes `setRevocationEnabled(boolean)`. An offline lab may disable revocation because it supplies no CRL/OCSP and has no real PKI; that approach is **not** a blanket policy for production applications.

At deployment, explicitly decide CRL/OCSP mode, responder sources, cache lifetimes, network failure handling, must-staple/internal requirements if applicable, and fail-open vs fail-closed policy. Never generalize that one successful `CertPathValidator.validate` call checked all live revocation states.

### 4.3. PKIX Path Validation and TLS Usage Constraints

A generic `CertPathValidator` does not know **all TLS protocol context**: target hostname, SNI, `serverAuth` vs `clientAuth`, TLS version, handshake purpose, `authType`, or application authorization. Context-aware JSSE trust managers can apply additional checks such as extended key usage, algorithms, and endpoint identity.

For instance, a code-signing or client certificate with a valid chain does not become a valid server certificate for arbitrary hostnames. You must combine proper **KeyUsage/EKU**, protocol, and identity verification.

## 5. Endpoint Identity: DNS SAN and IP SAN Are Two Distinct Types

### 5.1. DNS Hostname → dNSName (type 2)

For URI `https://billing.example.test`, the normal reference name is `billing.example.test`, matched against the server certificate's `dNSName` SAN.

Suppose a certificate contains `DNS:service.example.test`. That certificate is **not** valid for `billing.example.test` merely because both share the suffix `example.test`. An exact `dNSName` or standard-compliant wildcard must match.

DNS-ID comparisons must follow profile rules: case-insensitive DNS matching per standard, IDN/IDNA ASCII A-labels, and wildcard limits; **never write ad-hoc regexes** to replace the TLS stack's verifier.

### 5.2. IP Literal → iPAddress (type 7)

For `https://192.0.2.10` or `https://[2001:db8::10]`, the reference identity is an IP address. The certificate needs an `iPAddress` SAN with matching binary octets (4 octets for IPv4, 16 octets for IPv6). Putting `DNS:192.0.2.10` does not turn it into `IP Address:192.0.2.10`.

Never use reverse DNS results to turn an IP-ID check into a DNS-ID check. Two IPv6 addresses with different text spellings representing the same 16 octets must be compared as IP values; naive string matching can fail.

### 5.3. Common Name (CN) Does Not Replace SAN

Historically, some TLS clients fell back to `Subject CN` when a certificate lacked `dNSName`. **RFC 9525**, obsoleting RFC 6125, specifies that Common Name RDNs must not be used for service identity. For modern designs: issue certificates with proper SANs and do not rely on CN fallback.

A `Subject: CN=billing.example.test` **must not** be accepted as an excuse when the SAN holds only `DNS:service.example.test`. A certificate with a matching CN and wrong SAN still fails to protect the intended identity.

### 5.4. Wildcards Must Not Expand Unboundedly

Per DNS-ID profiles, valid wildcards are constrained (e.g., an entire leftmost label `*.example.test`) and normally match only **one label**. It does not match `example.test` and does not match `a.b.example.test`. Some systems enforce even stricter wildcard policies; follow RFC 9525 and your active profile.

Never use `endsWith(".example.test")` or `replace("*",".*")` as a DIY host verifier. A bug in label, dot, Unicode/IDNA, or wildcard handling creates an endpoint verification vulnerability.

## 6. Java 17+ Demo: PKIX Chain Valid Yet Hostname Needs Separate Checking

### 6.1. Goal and Boundaries of the Demo

The program uses **two public test X.509 certificates**:

- **Demo Root CA:** self-signed, with appropriate CA BasicConstraints and KeyUsage, chosen by the program as its trust anchor solely for this lesson.
- **Leaf certificate:** signed by the Demo Root CA, with SAN `DNS:service.example.test`; `Subject CN` is `legacy.example.test`.

Java's `CertPathValidator` will validate a path containing the **leaf certificate** up to the **root CA** trusted by the program. A successful result **neither contains nor accepts** the parameter `billing.example.test`; therefore it cannot directly answer whether that hostname matches.

The program then reads the SAN to **illustrate** that `service.example.test` is present in the certificate while `billing.example.test` is not. `List.contains` in the demo is used solely because the test certificate contains **a single exact DNS-ID without wildcards or IDNs**. **It is not a general HTTPS hostname verifier.** In real applications, let JSSE verify the endpoint using the `HTTPS` algorithm and an appropriate PKIX trust manager.

The certificate fixture was generated for learning purposes with **public certificates only**, **embedding no private keys**. Its validity runs from **2026-10-31 to 2036-10-28** per the timestamps in the certificates. Past that window, the PKIX example **needs fresh certificates**—never disable validity checks to force a pass.

The program **opens no network connections** and performs no TLS handshake; it illustrates the difference between the two questions at the certificate layer.

### 6.2. Complete Source PkixHostnameDemo.java

```java
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXCertPathValidatorResult;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Set;

public final class PkixHostnameDemo {
    // Public test certificates. Never add this demo CA to a production truststore.
    private static final String CA_PEM = """
            -----BEGIN CERTIFICATE-----
            MIIDMDCCAhigAwIBAgIIdN8VOPntrL4wDQYJKoZIhvcNAQEMBQAwNjELMAkGA1UE
            BhMCVVMxEDAOBgNVBAoTB0V4YW1wbGUxFTATBgNVBAMTDERlbW8gUm9vdCBDQTAe
            Fw0yNjEwMzExMzI4NThaFw0zNjEwMjgxMzI4NThaMDYxCzAJBgNVBAYTAlVTMRAw
            DgYDVQQKEwdFeGFtcGxlMRUwEwYDVQQDEwxEZW1vIFJvb3QgQ0EwggEiMA0GCSqG
            SIb3DQEBAQUAA4IBDwAwggEKAoIBAQDVz/2xjKXNgom5vKohD6AGorxwLk3S/GZo
            KVU900y+GZG18aBjMbUIJAPZIRSykF3QCO5OfGJqHa3aqo6mctBknES2h3wGRw15
            MFjmDenGHl5HqjouG2iXAff9gKbencmgigDHKc5IWHLXx0N00TH0LWF9bf+b71Q1
            5MP8gZ3ad5v9PTNRhBGjli7ywoK68qTGhdSPUarHEYk0Ii5OW4mTtsfYlNZpsU15
            Unxz6ViASsaO96cAt/BD6gZQ7UtFhiwZc5p7B0lQiLFzv+B4YV1bRl3fN6FyV5u4
            gdol+uCSfl1g57bgYqb6JVsSb5pxchAoYLYBYqN7hNMEUwfmOLhZAgMBAAGjQjBA
            MB0GA1UdDgQWBBR8adDvW8CFs/qJKxm38W243usibTAOBgNVHQ8BAf8EBAMCAQYw
            DwYDVR0TAQH/BAUwAwEB/zANBgkqhkiG9w0BAQwFAAOCAQEAg4pxYY0c11RBf+CD
            y1bWEUQzGCKaa5zVkutxoaYSSuDhZEOnxn7+buY/EkMfAEWfttm32jI8HfvVvP5p
            dmF/PqUchpk/GwshauAWuCeWRc490aMudGB5LWgciFtK3L6opSsZYNUI47JJTAY9
            P79ybEgwUDjKm1po7h5o1aJYVzqWW9/8QgLXlb2dpz9gGYum45LpSEa17qEoAwG9
            2ADlnOcLc5OUNjt9Qv5arLzD/lUxkqc97xo4/ziKu/JUczn5qK+PPHuOcIZE39KB
            J6Xfg7dmD26RR0muKcGT80gjFzrdsPjYap6fhKfHRCiGfyhYXmEV3xBsx7a3qFcO
            T5ktkg==
            -----END CERTIFICATE-----
            """;

    private static final String SERVER_PEM = """
            -----BEGIN CERTIFICATE-----
            MIIDgDCCAmigAwIBAgIJALbt87m4xELfMA0GCSqGSIb3DQEBDAUAMDYxCzAJBgNV
            BAYTAlVTMRAwDgYDVQQKEwdFeGFtcGxlMRUwEwYDVQQDEwxEZW1vIFJvb3QgQ0Ew
            HhcNMjYxMDMxMTMyOTAwWhcNMzYxMDI4MTMyOTAwWjA9MQswCQYDVQQGEwJVUzEQ
            MA4GA1UEChMHRXhhbXBsZTEcMBoGA1UEAxMTbGVnYWN5LmV4YW1wbGUudGVzdDCC
            ASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBANhgczqgksY3gGlhNUrb619R
            vR9PuIPa7c1wDdju1jGUlBv86XfjLXNzuVL92YdBI7OGzXcrUlYYdaieyXtNdM4c
            N6hBIFhWHaNxq5O98ljKHeCXSgAixz0FyvCG8odzwjbW8VFXfVlqXT839tZMhcpm
            gayLXW6p5GmGnujV/q1TZxXp4IDqsYLDTD0YSaghm/hFRF9wlNW1eoPS7EKemACV
            i75iY9w9ImdjjPtxr36/1nWKGMhksIzNMw/ClygruwaVb+ROERx8EM8UcMcJg4jn
            w+uhYUQ7uTEM2N+i3BzERt29R6pSHDWc8zuVyB+766YkjK52D7zUnQoPOfNN1rMC
            AwEAAaOBiTCBhjAdBgNVHQ4EFgQU3FgVZYXNv6Ofpywezmb/kZpFWywwDgYDVR0P
            AQH/BAQDAgWgMB8GA1UdEQQYMBaCFHNlcnZpY2UuZXhhbXBsZS50ZXN0MB8GA1Ud
            IwQYMBaAFHxp0O9bwIWz+okrGbfxbbje6yJtMBMGA1UdJQQMMAoGCCsGAQUFBwMB
            MA0GCSqGSIb3DQEBDAUAA4IBAQBOEY35M1IhiI/F4codM6kCBQcjCM3QpB8D1nvL
            nVB4HXZENtIRnDhXVDCzzo3Xko+/SuMiobli5+j4iKDncy/wrwbnhJr/koPGN5jP
            GnpNmwBNw9m4OSH7xjgFdbfH4S0DrNYv/NsvH1dJchdzSVm3ZVFLNDb0Ao/LB7ib
            Gs72BDXNiYxLrByryRDCVdoI6KNqL57Ll7ep2yRs2LGLNvP787rWH1frObGUz4KR
            wR+l0T8A93nPteXO0/P/8K30QdJ9Eyb5bftnBqWDO+aSlDnk2mhSAZ0Trroj68uQ
            Y3IYs9CG3VKGCvopFX+mrgBvVP28BIlyNevP3glqiyO9t1f1
            -----END CERTIFICATE-----
            """;

    private static X509Certificate certificate(CertificateFactory factory, String pem)
            throws Exception {
        return (X509Certificate) factory.generateCertificate(
                new ByteArrayInputStream(pem.getBytes(StandardCharsets.US_ASCII)));
    }

    public static void main(String[] args) throws Exception {
        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        X509Certificate root = certificate(factory, CA_PEM);
        X509Certificate server = certificate(factory, SERVER_PEM);

        CertPath path = factory.generateCertPath(List.of(server));
        PKIXParameters policy = new PKIXParameters(Set.of(new TrustAnchor(root, null)));
        policy.setRevocationEnabled(false); // Test fixture only; not a production policy.
        PKIXCertPathValidatorResult result = (PKIXCertPathValidatorResult)
                CertPathValidator.getInstance("PKIX").validate(path, policy);
        System.out.println("PKIX path valid: " + (result.getTrustAnchor() != null));

        List<String> dnsNames = new ArrayList<>();
        Collection<List<?>> sans = server.getSubjectAlternativeNames();
        if (sans != null) {
            for (List<?> name : sans) {
                if (((Integer) name.get(0)) == 2 && name.get(1) instanceof String dns) {
                    dnsNames.add(dns);
                }
            }
        }

        System.out.println("DNS SANs: " + dnsNames);
        System.out.println("Intended service DNS listed: " +
                dnsNames.contains("service.example.test"));
        System.out.println("Different target DNS listed: " +
                dnsNames.contains("billing.example.test"));
        System.out.println("Legacy CN in DNS SAN: " +
                dnsNames.contains("legacy.example.test"));
    }
}
```

### 6.3. Compile, Run, and Stdout

Requires Java 17 or higher, with no network connection or private key files:

```bash
javac PkixHostnameDemo.java
java PkixHostnameDemo
```

Verified stdout on a standard PKIX-supporting JDK within the fixture certificate validity window:

```text
PKIX path valid: true
DNS SANs: [service.example.test]
Intended service DNS listed: true
Different target DNS listed: false
Legacy CN in DNS SAN: false
```

**Reading the output properly:**

1. `PKIX path valid: true` shows `CertPathValidator` verified the **demo-CA-signed leaf** against the specified trust anchor and policy, not merely comparing fingerprints or parsing PEM.
2. `DNS SANs` containing `service.example.test` is data **read** from the leaf certificate. No RFC 9525/JSSE hostname matching has occurred in this demo.
3. `Different target DNS listed: false` illustrates that hostname `billing.example.test` **is not represented by the certificate**. This **did not** cause `CertPathValidator.validate` to throw an exception, because `billing.example.test` was never passed into path validation.
4. `Legacy CN in DNS SAN: false` is because CN was set differently from the DNS SAN. Never use CN to “rescue” a name mismatch in modern policy.
5. `setRevocationEnabled(false)` is used solely for **offline fixtures**. Never conclude from the example that production can skip revocation checking or that the demo root is publicly trusted.
6. The PEM pair consists of **public root and leaf certificates**; replacing `SERVER_PEM` with a leaf not signed by this root causes PKIX to fail unless another valid trust path is configured. Altering SAN contents cannot preserve a valid signature on an already-signed certificate.

**What the demo does not do:** no TLS network handshake, no proof-of-possession check from a remote server, no JSSE hostname verifier check, no TLS server usage profile/authorization check, and no proof of a live server. This tests **the boundary of PKIX**, not an example encouraging manual SAN `contains` checks in production.

## 7. Doing It Right in Java TLS: Bring Endpoint Identity into the Handshake

### 7.1. Prefer High-Level HttpClient/HTTPS APIs First

In Java, when using `java.net.http.HttpClient` with HTTPS URLs, the client's standard configuration performs TLS and server identity verification. For new applications, prefer high-level clients with standard truststores and managed TLS policies rather than swapping in an arbitrary `SSLContext` that trusts every certificate.

The snippet below **only illustrates client usage**; the `.test` hostname is a documentation example with no assumption of a live Internet server:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://billing.example.test/orders")).GET().build();
HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());
```

This is **not a standalone Java program**, only a fragment placed inside a method that can throw `Exception`. `HttpClient` still requires valid DNS/networking and a server certificate accepted by PKIX + endpoint verification. `PkixHostnameDemo` above does not connect to this host.

**Never** alter system settings to turn off hostname verification on mismatch, replace the trust manager with “accept-all”, or use custom `SSLContext` / internal properties disabling name checks just to make tests pass.

### 7.2. With SSLSocket, Enable Endpoint Identification

The lower-level `SSLSocket` API requires the developer to configure name verification explicitly. One JDK-supported way is `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`:

```java
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;

SSLSocketFactory factory = (SSLSocketFactory) SSLSocketFactory.getDefault();
try (SSLSocket socket =
        (SSLSocket) factory.createSocket("billing.example.test", 443)) {
    SSLParameters parameters = socket.getSSLParameters();
    parameters.setEndpointIdentificationAlgorithm("HTTPS");
    socket.setSSLParameters(parameters);
    socket.startHandshake();
    // Process data only if the TLS handshake and endpoint verification succeed.
}
```

This is an **illustrative snippet**, not a standalone class. Host `billing.example.test` is documentation data, not a live server. In real SSL/TLS deployments, you must use a trust manager performing proper **PKIX trust validation**; an always-accepting trust manager or check-disabling config undermines or nullifies guarantees even when an endpoint algorithm is set.

Setting `"HTTPS"` requests HTTPS-style name matching in JSSE. Never set the algorithm to `null` or `""` just to get past name errors. If a certificate has the wrong SAN, fix the target hostname or reissue the certificate with the right SAN—never “let it slide temporarily”.

### 7.3. SSLEngine, X509ExtendedTrustManager, and TLS Context

At the `SSLEngine` level, supply a meaningful **peerHost** when creating the engine, enable endpoint identification on `SSLParameters`, configure the right trust manager, and drive the handshake over transport with full SSL state.

An `X509ExtendedTrustManager` provides `checkServerTrusted(chain, authType, SSLEngine)` and a `Socket` overload to access **TLS context** (when used properly in a handshake). That differs from calling `X509TrustManager.checkServerTrusted(chain, "RSA")` directly in business code without host/context: a call passing only `chain` and `authType` **cannot** know which URL was requested.

**Mistake:** writing a custom `X509TrustManager` that accepts every chain and setting `HttpsURLConnection.setDefaultHostnameVerifier((host,session) -> true)`. Both trust and identity are bypassed, opening the door to MITM attacks.

### 7.4. SNI Does Not Replace Endpoint Verification

**Server Name Indication (SNI)** is a TLS ClientHello extension helping the server pick the right certificate for a virtual host. SNI **does not** replace the client's check that the received certificate actually carries the right SAN and trust chain.

Never use attacker-controlled SNI as an identity source instead of a trusted URI. With reverse proxies, load balancers, or sockets connecting directly to an IP while the service identity is DNS, configure TLS peer host/reference identity so you **never lose** the DNS name the client truly intends to verify.

## 8. When Connecting by IP or Systems with Multiple Hostnames

### 8.1. DNS Resolution to IP Does Not Change Reference Identity

If `billing.example.test` resolves via DNS to `192.0.2.10` while the client calls the URL by hostname, the identity to verify is `billing.example.test`, not the IP address returned by the resolver. DNS records can change IPs over time while the DNS-SAN certificate remains valid.

If an application explicitly uses `https://192.0.2.10`, the client expects an `iPAddress` SAN for the IP literal. `DNS:billing.example.test` **does not match** an IP reference identity. `iPAddress` records store raw octets (4 for IPv4, 16 for IPv6), not DNS text strings.

### 8.2. Wildcard SANs and Multiple Names

A certificate can hold multiple `dNSName` entries:

```text
DNS:billing.example.test
DNS:reports.example.test
DNS:*.svc.example.test
IP Address:192.0.2.10
```

Only a name matching the **requested reference identity** per the protocol profile is accepted. Wildcard `*.svc.example.test` does not match `svc.example.test` or `a.b.svc.example.test`. One certificate holding many valid names can serve multiple endpoints, yet a **private key leak** expands the blast radius; govern provisioning, issuance authority, and rotation.

### 8.3. Internationalized Domain Names (IDN)

Internationalized domains show Unicode in UIs, whereas X.509 `dNSName` entries per profile store ASCII IA5String (IDNA A-labels like `xn--...` where needed). Ensure clients, URI libraries, and TLS stacks normalize/match per standard. Never use locale-dependent `String.toLowerCase()` or suffix matching as a verifier.

### 8.4. Never Take the Peer's SAN as the Hostname to Connect To

Never handle it as: “the certificate has DNS SAN `api.example.test`, so let's treat our target as `api.example.test`”, when the application actually meant to call `billing.example.test`. That inverts identity verification, turning a claim inside the certificate into the requirement without checking an external expected identity.

## 9. Factors Outside PKIX and Hostname Matching That Still Matter

### 9.1. Authorization and Service Identity

Even when `billing.example.test` is accurately represented by the certificate and the TLS handshake is secure, the application must still verify the peer is **authorized for the business operation**: API scopes, tenant, JWT audience, mutual TLS client identity, quotas, data read permissions, replay/idempotency protection. Hostname verification never replaces authorization.

### 9.2. mTLS and Other Identity Forms

In **mutual TLS**, the server also verifies the client's certificate. Client identity may follow internal profiles: DNS SAN, URI SAN (such as service identity models), user certificates, or other organization-defined bindings. Never treat an arbitrary hostname in a client certificate's SAN as “a user allowed to access all APIs”.

HTTPS server hostname verification and **mTLS client** identity verification are two different trust directions. A PKIX chain remains foundational, yet each direction requires **its own identity and authorization policy**.

### 9.3. Does Certificate Pinning Replace PKIX?

Certificate or SPKI pinning can add extra trust constraints when provisioned over a trusted channel, yet introduces rollover/renewal challenges and requires backup pins. Never treat a “public pin” captured on an unverified connection as authenticating that first connection. Pinning for an organization also does not mean the key may represent **every hostname/tenant**; valid policy binding is still needed.

### 9.4. Revocation and Evaluation Time

When a server private key is compromised, the certificate may still be unexpired and have a matching SAN. If the client lacks policy-compliant revocation/compromise detection, checking only “chain and hostname” may miss the new state. Maintain certificate lifecycle management, trust updates, CRL/OCSP where applicable, and incident response.

### 9.5. Redirects, Proxies, and DNS Caches

When an HTTP client follows a redirect from `billing.example.test` to another origin, TLS verification must apply to the **new hostname**; meanwhile, the application must govern **where redirects are allowed to go**. DNS caching, split-horizon DNS, service meshes, or proxies are never excuses to skip endpoint validation.

**Separate layers:** TLS verifies *endpoint identity*; the application decides whether to trust that endpoint with sensitive data/credentials. Redirecting to a server with a completely valid certificate may still violate the application's policy for sending bearer tokens.

## 10. Decision Table: Path and Hostname Are Two Independent Checks

| PKIX trust/path | Hostname/IP identity | Required outcome | Meaning |
| --- | --- | --- | --- |
| **Pass** | **Match** | Acceptable **if** remaining TLS/policy conditions hold | Both trust source and exact endpoint were verified. |
| **Pass** | **Mismatch** | **Reject** | Valid certificate, yet belongs to a different server. |
| **Fail** | **Match** | **Reject** | Right SAN, yet certificate is untrusted/expired/invalid path/policy. |
| **Fail** | **Mismatch** | **Reject** | Both trust and identity fail. |
| **Unchecked** | **Match** | **Reject** | Matching hostname on an untrusted certificate is insufficient. |
| **Pass** | **Unchecked** | **Reject** | Skipping hostname verification cannot be compensated by PKIX. |

Never use `ignoreSslErrors` flags or an always-true trust manager to turn “Reject” cells into “Accept”. In tests, use an isolated test CA and test server instead of weakening global JVM settings.

## 11. Common Mistakes When Writing Java

| Symptom / anti-pattern | Why it is wrong | Resolution |
| --- | --- | --- |
| Calling `CertPathValidator.validate` and assuming right server | Validator takes no HTTPS reference hostname | Pair with JSSE endpoint verification. |
| Calling `X509Certificate.verify(caKey)` and accepting | Checks only one signature against caller-supplied key | Verify chain, trust anchor, usage, and hostname. |
| `new TrustAnchor(anyCert, null)` with a peer-sent cert | Client self-trusts an attacker-controlled root | Trust anchors must be securely provisioned. |
| `CertificateFactory` parses the certificate | Parsing verifies neither chain nor name | Use proper JSSE/PKIX, never a parser as a trust verifier. |
| Seeing a DNS name in `getSubjectAlternativeNames()` and accepting | Only lists SANs; does not match against expected hostname | Use a profile-compliant endpoint matcher. |
| SAN matches yet chain fails | Missing root/intermediate, revoked, expired, policy error | Fix PKI/truststore/cert chain; never disable trust. |
| Chain passes yet hostname fails | Leaf is for another DNS/IP or mismatched wildcard | Fix certificate SAN or trusted endpoint name. |
| Only `CN=billing.example.test` present | CN is not a valid reference identity per RFC 9525 | Issue a proper `dNSName` SAN. |
| URL uses IP yet certificate only has `DNS:IP-text` | Wrong type `iPAddress` | Add IP SAN or use a properly verified hostname. |
| Calling `SSLSocket.startHandshake` without endpoint identification | Low-level TLS may skip hostname checking by default | Use `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`. |
| Installing custom `HostnameVerifier` returning true | Ignores mismatch, enabling MITM | Remove bypass; fix certificate and endpoint. |
| Disabling revocation in production “because demo ran” | Weakens policy security, skips revocation status checks | Define appropriate CRL/OCSP and failure behavior. |
| Using SNI as proof of endpoint identity | SNI helps server pick a cert; does not verify cert on client | Still verify SAN after handshake. |
| Treating mTLS client certificate as automatic access | Trust/identity differs from authorization | Enforce role/scope/tenant checks after mTLS. |
| Connecting to proxy/IP and losing logical hostname | Wrong peer identity or unchecked identity | Configure trusted reference identity for TLS. |

### 11.1. Concrete Errors and Signals

- `CertPathValidatorException` with path-validation reason: can stem from signature, validity, policy, trust anchor, or revocation. Do not automatically assume hostname mismatch.
- `SSLHandshakeException` in JSSE: can wrap a PKIX error **or** an endpoint identity error. Inspect root cause and diagnostics without leaking secrets.
- `CertificateException` mentioning something like “No subject alternative DNS name matching ...” or “No subject alternative names present”: usually points to a SAN name/type error, though exact wording varies by JDK/provider.
- Errors like “unable to find valid certification path”: usually indicate trust anchors/chain building, **not** whether the hostname matched.
- If a test calls only `CertPathValidator` and succeeds, there is **no** evidence hostname verification ever ran.

Debug logs should record **chosen reference hostname/IP**, public SAN types, issuer/trust policy, certificate status, and exception category; never log private keys, session secrets, bearer tokens, or private data.

## 12. Two-Way Testing So Vulnerabilities Do Not Slip Through

### 12.1. Minimum Test Matrix

Use a test CA trusted **only in the test environment** with tailored leaf certificates. Never add test CAs to production truststores.

| Case | Certificate chain | Leaf DNS/IP SAN | Expected client target | Expected outcome |
| --- | --- | --- | --- | --- |
| 1 | Valid trust | `DNS:billing.example.test` | `billing.example.test` | TLS accepted if other policies pass |
| 2 | Valid trust | `DNS:service.example.test` | `billing.example.test` | TLS must reject **name mismatch** |
| 3 | Untrusted self-signed | `DNS:billing.example.test` | `billing.example.test` | TLS must reject **untrusted chain** |
| 4 | Expired | `DNS:billing.example.test` | `billing.example.test` | TLS must reject |
| 5 | Valid trust | `IP:192.0.2.10` | `192.0.2.10` | IP-ID matches if remaining policy holds |
| 6 | Valid trust | `DNS:192.0.2.10` | `192.0.2.10` | Reject due to wrong SAN type |
| 7 | Valid trust | `DNS:*.svc.example.test` | `a.svc.example.test` | Can match one label per RFC/profile |
| 8 | Valid trust | `DNS:*.svc.example.test` | `a.b.svc.example.test` | Reject because wildcard spans beyond one label |
| 9 | Valid trust | Matching CN only, no SAN | `billing.example.test` | Reject per RFC 9525 |
| 10 | Valid chain for right hostname | Wrong TLS server EKU/KeyUsage | `billing.example.test` | Reject per TLS policy |

**Most important test point of this lesson:** build a chain that **passes PKIX** yet whose SAN **does not** match the hostname. That is the case unit tests calling only `CertPathValidator` commonly miss. The Java demo above creates that scenario at the certificate layer; an integration test over JSSE must confirm the handshake **is rejected**.

### 12.2. Testing Over Real JSSE, Not Just Getters

A proper integration test should run a **local TLS server with the leaf certificate's private key**, paired with a client configured with a truststore trusting only the test CA and the right reference hostname. When the client connects using the scenario's fixed hostname, verify:

- Right chain + right hostname → handshake accepted.
- Right chain + wrong hostname → `SSLHandshakeException`/`CertificateException` depending on provider.
- Wrong chain + right hostname → must reject.
- When testing `SSLSocket`, enable `setEndpointIdentificationAlgorithm("HTTPS")` to verify this lesson's goal.

Use appropriate test DNS host mapping/local resolvers or configure peer host properly on `SSLEngine`/`SSLSocket`; never use an untrusted self-signed certificate to demonstrate a hostname error, because the handshake may fail **before** name comparison runs.

### 12.3. Mandatory Security QA Questions

- Where does the hostname to verify come from? Is it the application's chosen destination, not an attacker-supplied field?
- Does the client use a trusted TLS trust manager and the right anchors?
- Is endpoint identification actually enabled across every client type, every code path, and every environment?
- Do any APIs retry/fall back to “insecure mode” upon SSL errors?
- Do proxies/redirects/reverse proxies alter reference identity or send credentials to a different origin?
- Are SAN DNS type 2 and IP type 7 checked properly?
- Are CN fallback, overly broad wildcards, and inconsistent IDNA avoided?
- Are certificate validity/revocation/algorithms/EKU checked per policy?
- Do negative tests cover both chain-valid-but-host-wrong and host-right-but-chain-invalid?

## 13. Exercises and Self-Check Questions

1. What inputs does `CertPathValidator.validate` take? Why can it not automatically know you are calling `billing.example.test`?
2. In the demo, why is `PKIX path valid: true` at the same time `Different target DNS listed: false`?
3. If a leaf certificate signed by a trusted CA for `other.example.test` is presented to an HTTPS client connecting to `billing.example.test`, should it be accepted or rejected?
4. Distinguish `X509Certificate.verify`, `CertPathBuilder`, `CertPathValidator`, `X509Certificate.getSubjectAlternativeNames`, and JSSE endpoint identification.
5. Who selects `TrustAnchor`? Why is “client auto-trusts server-sent root” wrong?
6. If `PKIXParameters.setRevocationEnabled(false)` is used in an offline demo, what does that imply about safety in real deployments?
7. For `https://192.0.2.10`, against which SAN type is hostname identity checked? Why does `DNS:192.0.2.10` not substitute?
8. When can a DNS-ID wildcard match a hostname? Why not use `String.endsWith`?
9. Where in an `SSLSocket` flow must `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` be applied?
10. If a high-level HTTP client has an always-true trust manager and always-true hostname verifier attached, what guarantees remain from PKIX/hostname checks?
11. Why does SNI not prove a certificate's identity was verified?
12. When configuring mTLS, is the PKIX step on the client certificate enough to grant all business permissions?

**Exercise A:** run `PkixHostnameDemo` and record `PKIX path valid` and `Different target DNS listed`. Explain why “passing at the certificate path layer” and “failing hostname match” do not contradict each other.

**Exercise B:** keep the test CA/leaf unchanged, and suppose the target endpoint is `service.example.test`. Describe why the **reference identity** step changes while PKIX path validation stays identical. Never take the desired URL from the certificate's SAN.

**Exercise C:** use a local TLS test server/truststore to create a PKIX-valid yet hostname-mismatching case, then toggle `setEndpointIdentificationAlgorithm("HTTPS")` in an **isolated lab environment**. Compare the difference, then always restore the secure setting. Never ship check-disabling modes to production.

**Exercise D:** design a test matrix with a CN-only certificate, an IP SAN certificate, an expired cert, and a chain from an untrusted CA. Passing only one of PKIX or name matching must still reject.

## 14. Pre-Deployment Checklist

- [ ] Trust only roots/intermediates/trust anchors per organizational PKI policy.
- [ ] Use trusted HTTPS clients/JSSE with endpoint identification active on **every** code path needing TLS server authentication.
- [ ] Reference hostname/IP comes from a trusted endpoint source, never from peer-sent certificate/server data.
- [ ] SAN `dNSName`/`iPAddress` have the right type, wildcards follow rules, and CN fallback is not relied upon.
- [ ] No trust-all managers, always-true `HostnameVerifier`, insecure fallbacks, or identity-verification-disabling flags.
- [ ] Check algorithms, key strengths, validity, usage, policies, and revocation per standards and policy.
- [ ] Include negative tests for both PKIX-pass/hostname-fail and hostname-pass/PKIX-fail.
- [ ] Separate hostname verification, TLS cryptographic authentication, and business **authorization**.
- [ ] Maintain procedures for certificate rotation, truststore config, proxy/redirect/SNI handling, and multi-environment testing.
- [ ] Never use the lesson's demo root/leaf as production certificates or trust anchors.

## 15. Official References

- [RFC 5280 — Internet X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): certificate paths, trust anchors, extensions, policies, and SAN names.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): matching reference identity against presented identity, DNS-ID/IP-ID, wildcards, deprecating Common Name RDN.
- [CertPathValidator — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html): `getInstance("PKIX")`, `validate(CertPath, CertPathParameters)`.
- [CertPathBuilder — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathBuilder.html): discovering certificate paths per policy.
- [PKIXParameters — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXParameters.html): trust anchors, revocation, date, and path policies.
- [TrustAnchor — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/TrustAnchor.html): representing trusted CAs/roots.
- [X509Certificate — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html): SAN and certificate metadata.
- [SSLParameters — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): `setEndpointIdentificationAlgorithm("HTTPS")`.
- [X509ExtendedTrustManager — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/X509ExtendedTrustManager.html): trust checks with `Socket` or `SSLEngine` context.
- [HttpClient — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTPS client and TLS configuration.
