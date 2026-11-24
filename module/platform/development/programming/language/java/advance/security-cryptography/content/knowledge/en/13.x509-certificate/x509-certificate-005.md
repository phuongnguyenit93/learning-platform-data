# 13.5. Subject Alternative Name and DNS or IP Address Identities

## 1. What Problem Does SAN Solve in an X.509 Certificate?

When an HTTPS client connects to `https://api.example.test`, having the server present **an X.509 certificate with a valid signature** is not enough. The client needs to know whether that certificate was issued for **the exact server the client intends to reach**. If you only validate the *certificate path* to a trusted CA and skip **endpoint identity**, an attacker can use a valid certificate issued for a **different** name to deceive the client.

**Subject Alternative Name (SAN)** is an X.509 certificate extension with OID `2.5.29.17`, used to carry one or more explicitly typed identifiers: DNS names, IP addresses, email addresses, URIs, and several other forms. For TLS/HTTPS server identity, two types are critical:

- **dNSName (GeneralName type 2):** DNS name, e.g., `api.example.test` or `*.svc.example.test`.
- **iPAddress (GeneralName type 7):** IPv4/IPv6 address stored as **binary octets** in the extension, e.g., IPv4 `192.0.2.10` or IPv6 `2001:db8::10`.

In Java, `java.security.cert.X509Certificate.getSubjectAlternativeNames()` lets you **read** a certificate's SANs, but **does not itself perform server identity verification**. To protect real connections, all of the following must hold simultaneously:

1. **Certificate trust:** verify the certificate path, CA/trust anchor, validity period, key usage/EKU, and required policies.
2. **Endpoint identity match:** compare the hostname/IP **the client intends to reach** against the appropriately typed SAN per protocol rules.
3. **TLS handshake and policy:** the connection genuinely uses the private key corresponding to the accepted certificate, secure TLS parameters are active, and none of the checks above are disabled.

This lesson explains why **a DNS SAN does not replace an IP SAN**, why you must not rely on `Common Name (CN)`, how to read SANs in Java 17+, and how to make JSSE/HTTP clients verify identity properly rather than writing naive name matchers.

## 2. SubjectAltName Structure in X.509

Per RFC 5280, the extension consists of a sequence of `GeneralName` entries; each element has its own **type** and **value**:

```text
X.509 Certificate
├─ Subject Distinguished Name (DN)
│  └─ CN=legacy.example.test                 <-- part of subject, NOT SAN
├─ Subject Public Key Info (SPKI)
├─ Issuer, serial, validity, signature...
└─ Extensions
   └─ subjectAltName (OID 2.5.29.17)
      ├─ [2] dNSName: api.example.test
      ├─ [2] dNSName: *.svc.example.test
      ├─ [7] iPAddress: 192.0.2.10
      └─ [7] iPAddress: 2001:db8::10
```

This is data from **a test certificate**, not a real public server certificate. The `.test` domain, IPv4 `192.0.2.0/24`, and IPv6 `2001:db8::/32` are reserved for examples/documentation.

A certificate can contain **multiple SANs of the same type** and multiple different types. Having two dNSNames does not mean one “overrides” the other: depending on policy, any valid dNSName matching the expected name may be accepted. Certificates shared across multiple hostnames must be provisioned, controlled, and rotated carefully because a private key compromise affects every name on the certificate.

### Table of Common GeneralName Types

| Type in `getSubjectAlternativeNames()` | ASN.1 name | Purpose and interpretation |
| --- | --- | --- |
| `1` | `rfc822Name` | Email address. Not a DNS-ID substitute for HTTPS. |
| `2` | `dNSName` | DNS-based identity, used when the client connects by domain name. |
| `6` | `uniformResourceIdentifier` | URI identity where specified by protocol; does not automatically replace HTTPS dNSName. |
| `7` | `iPAddress` | IPv4/IPv6 address, used when the reference identity is an IP literal per application rules. |
| `0`, `3`, `4`, `5`, `8` | OtherName, X.400, directoryName, EDI, registeredID | Other structured identifiers, meaningful only under their corresponding protocol and policy. |

**SubjectAltName differs from IssuerAlternativeName.** SAN describes identities related to the certificate's **subject**; the `IssuerAlternativeName` extension describes additional identifiers of the **issuer**. When matching a server hostname, never look for DNS SANs in `IssuerAlternativeName`.

## 3. DNS-ID: When the Client Connects by Hostname

If an application calls `https://api.example.test/orders`, the reference identity is typically **the hostname `api.example.test` from the connection target chosen by the application**, not a string suggested by the certificate itself, produced by arbitrary reverse DNS, or controlled by an attacker's HTTP header.

Suppose a certificate has:

```text
subjectAltName:
  DNS:api.example.test
  DNS:*.svc.example.test
  IP Address:192.0.2.10
```

Under modern DNS-ID rules, this certificate can be used for `api.example.test`; the wildcard `*.svc.example.test` can match **one label** such as `a.svc.example.test`, but must not be interpreted as matching arbitrarily deep subdomains.

### 3.1. DNS Names Match by Name, Not by the IP Returned by DNS

Suppose DNS resolves to:

```text
api.example.test  --DNS A-->  192.0.2.10
```

A client accessing the URL `https://api.example.test` checks **the DNS-ID for `api.example.test`**, even though the TCP connection goes to an IP address after resolution. This is normal when multiple virtual hosts are served on the same IP.

Never take a DNS A/AAAA resolution result and switch the check to IP-ID when the user actually specified a DNS name. The expected identity must come from the trusted target information in the application/protocol.

### 3.2. Wildcard Matching Is Not `String.endsWith()`

Per RFC 9525, wildcards in DNS-ID are accepted only as **an entire leftmost label**. For the pattern `*.svc.example.test`:

| Reference hostname | Matches that wildcard? | Why |
| --- | --- | --- |
| `a.svc.example.test` | Yes, per single-label wildcard rule | `*` stands for label `a` |
| `b.svc.example.test` | Yes | One valid label |
| `svc.example.test` | No | Missing leftmost label |
| `a.b.svc.example.test` | No | Has **two** leftmost labels |
| `not-svc.example.test` | No | Different label structure |
| `192.0.2.10` | No | IP-ID and DNS-ID are different types |

Patterns like `a*.example.test`, `*.*.example.test`, or using `*` as arbitrary globbing do not conform to this standard rule. Checks also depend on protocol/application requirements and wildcard policies; **never hand-roll implementations** based on `replace("*", ".*")`, custom regexes, or suffix checks without understanding the standard.

### 3.3. Case, IDN, and Domain Formatting

DNS names are matched according to proper DNS/IDNA rules, not by naively comparing UTF-8 bytes of display text. Internationalized domains must generally be represented as **ASCII A-labels/Punycode per IDNA** inside `dNSName`, rather than placing raw Unicode U-labels into an `IA5String` extension.

Applications should use standard TLS/hostname verification libraries and the hostname normalization rules specified by the protocol profile. Never call locale-dependent `toLowerCase()` and check suffixes, never strip special characters or dots arbitrarily, and never let clients override the expected identity from untrusted input.

## 4. IP-ID: When the Client Connects by IP Address

If the URL/endpoint is specified directly as `https://192.0.2.10` or `https://[2001:db8::10]`, the reference identity is an **IP address**, not a DNS hostname. Under RFC 9525, IP-ID matches **the exact octets of the IP address** against the `iPAddress` field in SAN.

In X.509 ASN.1:

- An IPv4 `iPAddress` is encoded as **4 octets**.
- An IPv6 `iPAddress` is encoded as **16 octets**.
- It is not the text `"192.0.2.10"` stuffed into `dNSName` and treated as an IP-ID.
- Different IPv6 text representations can map to **the exact same 16 octets**; Java's parser may return IP strings in expanded form rather than the original compressed form.

For example:

```text
DNS SAN: api.example.test
IP SAN: 192.0.2.10

Client A: https://api.example.test  -> requires DNS-ID api.example.test
Client B: https://192.0.2.10        -> requires IP-ID 192.0.2.10
Client C: https://192.0.2.11        -> IP mismatch, must reject
```

**Common mistake:** a certificate has `DNS:192.0.2.10` without `IP Address:192.0.2.10`. That is a `dNSName` containing characters that look like an IP address, **not** a properly typed `iPAddress` SAN. Do not try to “work around” it by comparing text across the two types.

**Also wrong:** when connecting to `192.0.2.10`, performing reverse DNS and letting any returned hostname match a DNS SAN. IP-ID matching must rely on the chosen IP reference, not be replaced by a name from untrusted reverse DNS.

If an application must reach a backend by IP while the certificate is issued for a DNS hostname, configure **a trusted canonical hostname** and connect using the proper model/protocol (e.g., opening a TCP connection to the designated IP while configuring TLS endpoint identity and SNI for the known DNS name). Never disable hostname verification to fix certificate errors.

## 5. Is Common Name (CN) Still Used as Server Identity?

Previously, many implementations checked `CN` in `Subject DN` when a certificate lacked a `dNSName` SAN. This practice caused confusion because `CN` lacks explicit typing like SAN, and fallback policies varied across clients and providers.

**RFC 9525 (2023), superseding RFC 6125**, specifies that **the Common Name RDN must not be used to identify services**; server identity is represented in appropriate `subjectAltName` entries. Therefore, for new designs:

- Issue HTTPS certificates with **properly typed `dNSName` and/or `iPAddress` SANs** for every permitted endpoint.
- **Do not rely** on `CN` to validate a hostname/IP when SAN does not match.
- Do not rely on an older client falling back to `CN` as proof that the product will operate securely across other JDKs/clients.
- `Subject DN` still serves as PKI certificate metadata; this rule specifically governs **service endpoint identity** verification, not removing all Subject information.

The fixture in the Java section intentionally sets `CN=legacy.example.test` while **omitting** that name from the DNS SAN. The program will demonstrate that reading SANs **does not automatically include CN**; when using a TLS client under modern policy, CN must never be treated as a fallback identity when a proper DNS-ID is absent.

## 6. SAN Matching Differs from Trusted Certificate Verification

These operations have distinct roles:

| Operation | What does it check? | What is **not** yet proven |
| --- | --- | --- |
| `CertificateFactory.generateCertificate(...)` | Parses DER/PEM into a `Certificate` | Does not prove CA, trust path, validity, or hostname acceptance |
| `X509Certificate.getSubjectAlternativeNames()` | Lists subject SANs encoded in the certificate | Does not perform hostname verification |
| `X509Certificate.getSubjectX500Principal()` | Returns Subject DN as an X.500 principal | CN is not a valid DNS-ID/IP-ID per RFC 9525 |
| `X509Certificate.checkValidity()` | Checks `notBefore`/`notAfter` against time | Does not validate the certificate chain or hostname |
| `X509Certificate.verify(issuerPublicKey)` | Checks certificate signature with the supplied public key | Does not build a trust path or verify server name |
| `CertPathValidator` with PKIX policy | Validates certification path per supplied parameters/trust anchors | Does not automatically match URL hostname against SAN |
| Properly configured JSSE/HTTP TLS client | Handshake, trust manager, and endpoint identification | Does not replace application-level business authorization/identity mapping |

**Both conditions are required**: a certificate chain valid under trust policy **and** a SAN matching the endpoint identity. If a self-signed certificate contains `DNS:api.example.test` but is not trusted by a configured trust anchor, it must still be rejected. Conversely, if a certificate from a trusted CA has a SAN for `other.example.test` while the client connects to `api.example.test`, it must also be rejected.

The SAN extension is **not a separate signature**: it is inside the certificate content signed by the issuer. However, a SAN extension containing matching text **does not create trust on its own**; the client must validate the entire certificate under PKI and know which name it expects.

### 6.1. Chain, Validity, KeyUsage, EKU, and Name Constraints

Beyond SAN, production systems typically need to verify:

- Signatures/certification path leading to an accepted trust anchor; the CA is authorized to issue the corresponding certificate.
- `notBefore`/`notAfter` and time policies, plus certificate revocation when required by profile.
- `BasicConstraints`, `KeyUsage`, and `ExtendedKeyUsage` appropriate for the TLS server role (e.g., EKU `serverAuth` when specified).
- `NameConstraints` on CA/intermediate certificates if present, which may restrict permitted DNS/IP subtrees.
- Algorithm policy, key strength, signature algorithms, key rotation, and pinning if applicable.
- Network connection reaches the intended endpoint and the application is not redirected to another origin while skipping checks.

Do not try to re-implement all PKIX/TLS checks at the application layer using only `X509Certificate` getters. Leverage JSSE/HTTP clients and valid truststores, or an audited TLS implementation.

## 7. Java 17+: Reading Real SANs from an X.509 Certificate

In JCA, `X509Certificate.getSubjectAlternativeNames()` returns `Collection<List<?>>` or `null` if the certificate has no SAN extension. Each element is a two-item list:

1. An `Integer` representing the GeneralName type (0–8).
2. A value, typically a `String` for types such as DNS `2`, IPv4/IPv6 `7`, URI `6`, or a DER `byte[]` for certain other types.

In particular, for type `7`, Java returns a displayable IP string, **not necessarily preserving compressed IPv6 text**. The example uses `InetAddress` to compare octets of two **known IP literals** purely to inspect SAN data; this is **not** an HTTPS hostname verification algorithm.

### 7.1. Embedded Test Certificate in Code

So the example runs standalone without depending on a network server, the program embeds **a public, self-signed demo-only certificate** in PEM form. The fixture has:

```text
Subject DN: CN=legacy.example.test, OU=Testing, O=Demo, C=US
SAN:
  DNS:api.example.test
  DNS:*.svc.example.test
  IP Address:192.0.2.10
  IP Address:2001:db8::10
```

**There is no private key in the source**. This is not a valid server certificate on the Internet: it is self-signed and uses documentation names/addresses. The program **only parses** the certificate and prints its SANs. It **does not** check a path to a trusted CA, does not open a TLS connection, and does not prove any server name is accepted.

Create the file `SanCertificateDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;

public final class SanCertificateDemo {
    // Public, self-signed test certificate; no private key is embedded.
    private static final String CERT_PEM = """
            -----BEGIN CERTIFICATE-----
            MIIB+DCCAZ+gAwIBAgIJAJ14rTcMr16LMAoGCCqGSM49BAMDMEwxCzAJBgNVBAYT
            AlVTMQ0wCwYDVQQKEwREZW1vMRAwDgYDVQQLEwdUZXN0aW5nMRwwGgYDVQQDExNs
            ZWdhY3kuZXhhbXBsZS50ZXN0MB4XDTI2MTAzMTEzMjQxMVoXDTI5MDcyNzEzMjQx
            MVowTDELMAkGA1UEBhMCVVMxDTALBgNVBAoTBERlbW8xEDAOBgNVBAsTB1Rlc3Rp
            bmcxHDAaBgNVBAMTE2xlZ2FjeS5leGFtcGxlLnRlc3QwWTATBgcqhkjOPQIBBggq
            hkjOPQMBBwNCAARGSmwZAOpA+2rAEjrl4hYnRfXTYl5cG2hOHfsJs1fPt1B/fxv0
            Saplz7XtuMHGX7uCY+ftWgQlA18JsxMk4oQto2owaDAdBgNVHQ4EFgQU4oNvse+X
            n0vCSxlfkgX1Lp3Tg9cwRwYDVR0RBEAwPoIQYXBpLmV4YW1wbGUudGVzdIISKi5z
            dmMuZXhhbXBsZS50ZXN0hwTAAAIKhxAgAQ24AAAAAAAAAAAAAAAQMAoGCCqGSM49
            BAMDA0cAMEQCIEpTPuvkpgvpAdaxnl2kpOek3cBS4Jl+/xOBcTpBj/NqAiBgfrDl
            ZfNneRagyWvbB3UzpTea0ddr9XAePvhjG/e0BQ==
            -----END CERTIFICATE-----
            """;

    private static boolean hasIp(List<String> ipSans, String literal)
            throws Exception {
        byte[] expected = InetAddress.getByName(literal).getAddress();
        for (String ipSan : ipSans) {
            byte[] actual = InetAddress.getByName(ipSan).getAddress();
            if (Arrays.equals(expected, actual)) return true;
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        byte[] pem = CERT_PEM.getBytes(StandardCharsets.US_ASCII);
        X509Certificate certificate = (X509Certificate) factory
                .generateCertificate(new ByteArrayInputStream(pem));

        Collection<List<?>> sans = certificate.getSubjectAlternativeNames();
        List<String> dnsSans = new ArrayList<>();
        List<String> ipSans = new ArrayList<>();
        if (sans != null) {
            for (List<?> name : sans) {
                int type = ((Integer) name.get(0)).intValue();
                Object value = name.get(1);
                if (type == 2 && value instanceof String dns) dnsSans.add(dns);
                if (type == 7 && value instanceof String ip) ipSans.add(ip);
            }
        }

        System.out.println("Certificate type: " + certificate.getType());
        System.out.println("DNS SANs: " + dnsSans);
        System.out.println("IPv4 SAN present: " + hasIp(ipSans, "192.0.2.10"));
        System.out.println("IPv6 SAN present: " + hasIp(ipSans, "2001:db8::10"));
        System.out.println("Legacy CN in DNS SAN: " +
                dnsSans.contains("legacy.example.test"));
        System.out.println("DNS SAN count: " + dnsSans.size());
        System.out.println("IP SAN count: " + ipSans.size());
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac SanCertificateDemo.java
java SanCertificateDemo
```

Exact stdout:

```text
Certificate type: X.509
DNS SANs: [api.example.test, *.svc.example.test]
IPv4 SAN present: true
IPv6 SAN present: true
Legacy CN in DNS SAN: false
DNS SAN count: 2
IP SAN count: 2
```

### 7.2. Reading the Output Correctly

- `CertificateFactory` parsed an X.509 certificate — **no trust decision has been made**.
- The two type `2` SAN values in fixture order are `api.example.test` and `*.svc.example.test`.
- The two type `7` values hold IPv4 and IPv6. The `hasIp` helper converts **IP literals** to octets to test presence, because IPv6 text can be formatted differently even when the binary values are identical.
- The name `legacy.example.test` is in **CN**, not in the DNS SANs, so `dnsSans.contains(...)` returns `false`.
- `getSubjectAlternativeNames()` can be `null` if no SAN is present; the code handles that with empty lists. A modern hostname verification application should reject a server identity lacking an appropriate SAN rather than falling back to CN.
- Listing SAN data **does not mean** the program verified wildcards, chain, expiration, key usage, or domain control.

**This is a metadata inspection demo, not a hostname verifier.** In particular, never copy `hasIp` or `dnsSans.contains` into a custom TLS verifier: those checks omit trust path, reference identity policy, wildcards, IDNA, certificate constraints, and many other security controls.

## 8. Making Java Actually Verify Hostname/IP on TLS Connections

### 8.1. Prefer Securely Configured Default HTTP Clients

For HTTPS, APIs like `java.net.http.HttpClient` or `HttpsURLConnection` provide TLS and server identity verification with appropriate defaults. When building applications, let the hostname from the **expected URI/endpoint** participate in certificate verification, use a trusted truststore, and do not disable name checking.

**Illustrative snippet**, not a standalone program with the self-signed fixture:

```java
// Only send to a real endpoint with a certificate valid per trust policy.
HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.test/orders"))
        .GET()
        .build();
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
```

Real code needs imports for `java.net.URI` and `java.net.http.HttpClient`, `HttpRequest`, `HttpResponse`. The host `api.example.test` here is **only an example**, not a live public server. Do not run this snippet and mistake DNS or trust errors for errors in the SAN parser above.

**Never** install an “accept all” trust manager, never set a `HostnameVerifier` that always returns true, and never disable endpoint identification to “fix SAN errors”.

### 8.2. With `SSLSocket`/`SSLEngine`, Enable Endpoint Identification Explicitly

When using low-level TLS sockets, developers may need to configure `SSLParameters` to enable endpoint identity checks. **Illustrative snippet for a real server**, not using the demo self-signed fixture:

```java
SSLSocketFactory factory = (SSLSocketFactory) SSLSocketFactory.getDefault();
try (SSLSocket socket =
        (SSLSocket) factory.createSocket("api.example.test", 443)) {
    SSLParameters parameters = socket.getSSLParameters();
    parameters.setEndpointIdentificationAlgorithm("HTTPS");
    socket.setSSLParameters(parameters);
    socket.startHandshake(); // Trust chain + endpoint identity via JSSE.
}
```

Requires importing `javax.net.ssl.SSLSocketFactory`, `SSLSocket`, and `SSLParameters`. An appropriate `SSLContext`/truststore and proper certificate policy remain mandatory. The example explains API usage; `.test` domains are not for live connections.

`setEndpointIdentificationAlgorithm("HTTPS")` is **not** a call to `X509Certificate.getSubjectAlternativeNames()`. It instructs JSSE to perform endpoint verification during the handshake per configuration and provider implementation. Never set the algorithm to `null` or an empty string to skip the check, as doing so can leave identity unverified.

**SNI and endpoint identification differ:** SNI lets the client *tell the server* which virtual host it wants so the server selects the right certificate; endpoint identification is *the client checking* that the received certificate matches the expected target. Sending the right SNI **does not replace** hostname checking.

### 8.3. If the Client Connects by IP Address

For example, with `https://192.0.2.10`, the certificate must contain a type `7` SAN matching that IPv4 address, per application policy. Never substitute `DNS:192.0.2.10` or `CN=192.0.2.10`.

For IPv6 URLs, the address must be enclosed in square brackets in the URI authority, e.g., `https://[2001:db8::10]/`; the `iPAddress` SAN contains **16 IP octets**, without brackets. If connecting by DNS hostname while the socket connects to a known IP, keep the **trusted hostname** as the TLS reference identity and configure socket/peer host appropriately rather than switching to IP and disabling checks.

## 9. How Do SAN Matching, Truststores, and Certificate Pinning Relate?

### Truststore and CA

The truststore holds trust anchors/certificates that the client is permitted to trust per policy. A trusted CA can issue many certificates for different servers; therefore, **a valid trust path is not enough**—you must still match the SAN hostname/IP of **the target the client is accessing**.

### Certificate/Public-Key Pinning

Pinning binds connections to a known certificate or SPKI/public key obtained from a trusted channel. It can reduce certain certificate-substitution risks, yet introduces challenges around **rotation**, revocation, backup pins, and outage configuration. Never “pin” by accepting whatever certificate arrives over an unauthenticated channel and treating trust-on-first-use as universally safe. Pinning is **not** a default excuse to skip hostname verification or chain validation unless the application has an explicitly designed and audited trust profile.

### mTLS (Mutual TLS)

In mTLS, the **client** also presents a certificate to the server. Verifying the **client**'s identity typically follows an application profile (e.g., URI SAN, DNS SAN, service mesh identity, or internal specification) and authorization policy. Never take any arbitrary DNS SAN from a client certificate to grant access across tenants. Client authentication and server hostname authentication are **two distinct directions** requiring separate identity governance.

## 10. Real-World Scenarios and Expected Outcomes

| Client expects | Server SAN | Outcome at identity-matching step | Reminder |
| --- | --- | --- | --- |
| `api.example.test` | `DNS:api.example.test` | DNS-ID matches | Still requires trust chain, validity, and policy |
| `API.EXAMPLE.TEST` | `DNS:api.example.test` | Matches under standard case-insensitive DNS comparison | Do not use arbitrary locales |
| `a.svc.example.test` | `DNS:*.svc.example.test` | Matches single-label wildcard per RFC 9525 | Do not allow wildcard beyond one label |
| `a.b.svc.example.test` | `DNS:*.svc.example.test` | Does not match | Do not use suffix-only matching |
| `svc.example.test` | `DNS:*.svc.example.test` | Does not match | Wildcard does not mean zero labels |
| `192.0.2.10` | `IP:192.0.2.10` | IP-ID matches | Check octets, right type |
| `192.0.2.11` | `IP:192.0.2.10` | Does not match | No subnet/range matching |
| `192.0.2.10` | `DNS:192.0.2.10` | Not an IP-ID per standard rules | Matching text is insufficient |
| `2001:db8::10` | `IP:2001:0db8:0:0:0:0:0:10` | Matches if all 16 octets match | Compressed/expanded text does not change the IP |
| `legacy.example.test` | Only `CN=legacy.example.test` | Insufficient per RFC 9525 | No CN fallback |

This table describes **the standard identity-matching step**; it is not a guarantee that every Java provider/version/application layer handles every edge case identically. For controlled systems, test the exact deployed JDK/provider/TLS stack and follow your chosen security policy; never weaken policy just because a legacy client accepted CN.

### 10.1. Reverse Proxies, Load Balancers, and Service Meshes

An application may connect to a load balancer or sidecar while the service's logical hostname differs from the node IP. A certificate with a DNS SAN for the **canonical service name** remains appropriate if the client verifies that exact name. Never replace the “hostname to verify” with `Host`/`X-Forwarded-Host` headers received from untrusted sources; those headers can be spoofed across misconfigured proxy boundaries.

### 10.2. Certificates with Multiple SANs

One certificate for `api.example.test` and `admin.example.test` lets clients use it for both hostnames (when all other checks pass), yet expands the blast radius if the private key leaks. Group services/tenants by risk, plan certificate rotation and key management, and restrict SAN issuance permissions.

### 10.3. When SAN Is Absent

The Java API can return `null`. Treat the absence of an appropriate SAN as a certificate issuance defect to fix per modern standards. Never switch to accepting all hostnames, never fall back to CN as a crutch, and never trust-all to bypass the error.

## 11. Common Java/TLS Errors and Fixes

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `getSubjectAlternativeNames() == null` | Certificate lacks a SAN extension | Re-issue certificate with proper DNS/IP SANs and trust profile |
| DNS hostname mismatch | Certificate has another service's SAN or wildcard label count mismatch | Set the right reference hostname; fix certificate/SAN |
| HTTPS by IP fails despite valid DNS SAN | Missing type 7 `iPAddress`, client checks IP-ID | Issue proper IP SAN or connect properly via trusted hostname |
| IPv6 strings look different | Text may be compressed/expanded yet represent identical octets | Let the TLS verifier compare IPs per standard; never compare raw strings |
| `CertificateException`/PKIX path building failure | Untrusted CA/chain, missing intermediate, or wrong truststore | Fix trust anchors/chain; never disable trust validation |
| Certificate parses yet TLS rejects | Parsing does not check trust, hostname, or EKU | Identify failure category: chain, validity, SAN/identity, policy |
| `SSLHandshakeException` citing name mismatch | Endpoint identification rejected certificate | Check expected hostname and properly typed SAN |
| Wildcard `*.example.test` rejected for `a.b.example.test` | Wildcard covers only a single label | Issue a specific SAN for the served hostname |
| CN matches hostname yet client rejects | CN fallback is disabled under modern profiles | Put hostname into a properly typed DNS/IP SAN |
| `X509Certificate.verify(issuerKey)` passes yet wrong host URL | Signature check neither compares hostnames nor validates full trust path | Use JSSE client endpoint verification + PKIX |
| Custom `HostnameVerifier` returning `true` to silence error | Disables MITM protection at the name layer | Remove bypass; fix cert or client reference identity |
| Raw `SSLSocket` TLS client runs without checking hostname | Endpoint identification not enabled/configured | Set `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` appropriately |
| Connecting by IP while cert is for DNS | SNI, peer host, and reference identity do not align | Configure verified logical name and connection properly; never disable checks |
| Using self-signed fixture in real environments | No chain to a policy-approved trust anchor | Use real PKI/truststore; fixtures are only for inspecting SANs |

**Safe debugging:** log the expected hostname, SAN types and public values, appropriate issuer/subject, chain path, and exception type; never log private keys, credentials, or session secrets, and never bypass verification to get past errors. Distinguish **name mismatch** from **untrusted issuer**, as each requires a fix in a different place.

## 12. Test Actual Behavior, Not Just the Parser

A thorough test suite for an HTTPS client should cover:

1. Certificate trusted by truststore with a **matching DNS SAN** → handshake accepted if all other policies pass.
2. Valid chain but **DNS SAN differs from target** → rejected.
3. Valid chain, only **CN matches** without SAN → rejected under modern policy.
4. Wildcard DNS `*.svc.example.test` with one label, zero labels, and two labels → outcomes compliant with RFC 9525.
5. Connecting by IP with an exact IP SAN → accepted if other checks pass; only a DNS SAN holding IP text → rejected.
6. Equivalent compressed/expanded IPv6 → matched by octets, not raw text.
7. Untrusted self-signed certificate → rejected even when DNS/IP SAN matches.
8. Expired certificate, revocation/policy failure, or inappropriate KeyUsage/EKU → rejected.
9. Wrong SNI yet selected certificate still holds expected SAN → evaluate using actual received certificate checks; do not treat SNI as replacing identity checks.
10. Verify raw TLS sockets enable endpoint identification and HTTP clients have no "trust-all"/"hostname verifier always true" configurations.

**Tip for test fixtures:** in development, you can use `keytool` with `-ext SAN=dns:...,ip:...` to create a self-signed certificate for **unit/integration tests** and provide a **test-only** truststore. Never bring test CAs/root keys into production. When verifying PKIX/SAN failures, run tests against an isolated network/test runner or controlled local server rather than assuming documentation `.test` hostnames exist on the Internet.

### Pre-Deployment Checklist

- [ ] Every service hostname is listed with an exact **type 2 `dNSName` SAN**.
- [ ] If clients connect by IP literal, the certificate has the exact **type 7 `iPAddress` SAN**.
- [ ] No reliance on CN fallback; no skipping hostname verification.
- [ ] Client derives reference identity from a trusted endpoint, not attacker-controlled input.
- [ ] Truststore/PKIX chain validation and policies for issuer, validity, EKU, key usage, and revocation are in place.
- [ ] Wildcards conform to standard scope and are tested at single and multiple label depths.
- [ ] IDN/ASCII A-labels and Unicode handling follow protocol/provider rules.
- [ ] Plans exist to update SANs when DNS/service hosts/IPs change, with zero-downtime certificate rotation.
- [ ] No test certificates, self-signed demos, or test private keys in production.
- [ ] Logs distinguish trust chain failures from endpoint name failures without leaking secrets.

## 13. Self-Check Questions

1. What is the OID of the SAN extension, and how does it differ from Subject CN?
2. Which GeneralName types are `dNSName` and `iPAddress`? Are they interchangeable when a text value looks like an IP address?
3. A client accesses `https://api.example.test` and DNS resolves to `192.0.2.10`: should it check DNS-ID or IP-ID? Why?
4. A client accesses `https://192.0.2.10` and the cert only has `DNS:api.example.test`: why is the certificate not automatically accepted under IP-ID?
5. If a certificate has `CN=legacy.example.test` and `DNS:api.example.test`, may a client requesting `legacy.example.test` fall back to CN under RFC 9525?
6. Why does `*.svc.example.test` not match `a.b.svc.example.test`?
7. What type does `X509Certificate.getSubjectAlternativeNames()` return, and when does it return `null`?
8. Why does successful parsing by `CertificateFactory` not mean the certificate is trusted or the hostname matched?
9. How does `X509Certificate.verify(...)` differ from `CertPathValidator` and endpoint identification?
10. If you disable hostname verification while still checking the CA chain, what risk remains?
11. What does SNI help the server do? Does it verify server identity for the client?
12. Why can a certificate containing both a DNS SAN and an IP SAN serve multiple access paths while still requiring private-key risk management?

**Exercise A:** Replace the PEM in the demo with another test certificate containing multiple `dNSName` and IP SANs. Read types 2/7 and inspect the values using the proper APIs. Do not infer a trust decision from the printed output.

**Exercise B:** Create one certificate with only CN and no DNS SAN, and another with a matching DNS SAN. Write an integration test using an HTTPS client with a test truststore to verify endpoint identity policy is enforced.

**Exercise C:** Test `https://hostname` and `https://IP` against a local TLS server you control using a certificate with both a DNS SAN and an IP SAN. Observe the difference between name mismatch and untrusted CA.

**Exercise D:** Write unit tests for single-label, zero-label, and multi-label wildcards against your provider's real TLS hostname verifier, without substituting `String.endsWith`.

## 14. Official Documentation

- [Java SE 17 — X509Certificate.getSubjectAlternativeNames](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html#getSubjectAlternativeNames()): `Collection<List<?>>` structure, SAN types 2/7, value representation, and `null` case.
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): `GeneralName` and `subjectAltName` extension (OID 2.5.29.17), certificate chains, and name constraints.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): DNS-ID, IP-ID, single-label wildcards, IDNA, and no CN fallback; obsoletes RFC 6125.
- [Java SE 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): `setEndpointIdentificationAlgorithm`, configuring endpoint verification.
- [Java SE 17 — SSLSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html): `getSSLParameters`/`setSSLParameters` and handshake.
- [Java SE 17 — CertificateFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertificateFactory.html): parsing X.509 certificates from DER/PEM.
- [Java SE 17 — CertPathValidator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html): validating certificate paths per PKIX parameters, distinct from hostname matching.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP/HTTPS client and TLS configuration.
