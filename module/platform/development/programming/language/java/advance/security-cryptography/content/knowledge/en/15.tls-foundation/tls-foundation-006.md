# 15.6 Distinguishing Certificate Chain Trust from Hostname Verification

When a Java application connects over HTTPS/TLS, two independent security questions must be answered correctly:

1. **Can this certificate chain (certificate path/chain) be trusted?** Does the server certificate chain back to a **trust anchor** actively trusted by the client, with valid signatures, validity dates, and certificate constraints?
2. **Does that certificate prove the identity of the exact server the application intends to connect to?** Does the reference name from the URL/config (hostname or IP) match a **Subject Alternative Name (SAN)** on the certificate per endpoint verification rules?

A certificate with a valid chain **can still belong to a different hostname**. Checking only the chain while skipping name verification turns an encrypted TLS channel into one that **does not authenticate the right peer**. Conversely, a certificate showing the right hostname issued by an untrusted CA is also invalid. A secure HTTPS connection must satisfy **both conditions**, along with checks for key usage, TLS policy, and certificate status as required.

This lesson sits in **15. TLS Foundation**, focusing on the difference between **trust chain** and **hostname verification**, how Java/JSSE performs them, a runnable Java 17+ example with an internal CA and SAN `DNS:localhost`, and an operational checklist.

## 1. Overview model: "who signed it?" is not the same as "who is it?"

Suppose the application calls:

~~~text
https://payments.example.com/api/charge
~~~

The peer sends a certificate with SAN `DNS:reports.example.com`, yet signed by a trusted CA, valid in dates, and valid as a PKIX path. If you only check signature/CA, the client could trust **a certificate belonging to the reports system** when talking to **payments**.

The two checks are related but take different inputs:

~~~text
                  TLS handshake / peer certificates
                               |
                 +-------------+-------------+
                 |                           |
                 v                           v
        (A) PATH TRUST              (B) ENDPOINT IDENTITY
        certificate chain           intended hostname or IP
        signature/path policy       from URL/config/request
        trusted root                versus leaf SAN
                 |                           |
                 v                           v
           pass / fail                 match / mismatch
                 |                           |
                 +-------------+-------------+
                               |
                      both pass => accept
                   either fails => reject
~~~

**Check A (path trust)** answers: "Under configured trust anchors and policy, does this public key/certificate belong to a valid trust chain?"

**Check B (endpoint identity)** answers: "Does the identity attested by the leaf certificate match the **target name the application intends to contact**?"

**You cannot turn check A into check B** simply by importing more CAs into the truststore. Nor can you turn check B into check A by writing the right hostname into the CN/SAN of an untrusted self-signed certificate.

### 1.1. Outcome table for the four scenarios

| Certificate chain trusted | Hostname matches | Decision |
| --- | --- | --- |
| Yes | Yes | Acceptable after other TLS/policy checks |
| Yes | **No** | **Reject**: the certificate may be valid for a different server |
| **No** | Yes | **Reject**: name matches, but certificate is untrusted |
| **No** | **No** | **Reject**: both conditions fail |

**"Acceptable" does not mean authorized**: TLS authenticates the endpoint per policy, while permission to use APIs/accounts/tenants remains a matter of authorization, tokens, mTLS identity mapping, or other application steps.

## 2. Certificate chains and trust anchors: PKIX's job

An X.509 leaf certificate carries the server's public key. A typical certificate path looks like:

~~~text
server leaf: SAN DNS:api.example.com
      |
      | signature verified with issuer's public key
      v
issuing intermediate CA: BasicConstraints CA=true
      |
      v
root CA (trust anchor configured by client)
~~~

For path validation, the client must evaluate:

- **Signatures** across leaf, intermediates, and an allowed trust anchor. Comparing `Issuer DN` and `Subject DN` strings alone is **insufficient**; two certificates with different keys can share the same name string.
- **BasicConstraints** and `pathLenConstraint` on intermediate CA certificates, plus `KeyUsage keyCertSign` where applicable.
- **NotBefore/NotAfter** and current clock; an expired or not-yet-valid certificate does not become valid just because its CA is trusted.
- **Algorithms, key sizes, signature constraints, certificate policies/name constraints**, and the environment's PKIX/TLS configuration.
- **Leaf intended usage**: e.g., EKU `serverAuth`/`clientAuth` per role when present; corresponding `KeyUsage`.
- **Revocation** (CRL/OCSP and revocation policy) when required; having a signature-valid path does not mean the certificate has not been revoked.
- **Pre-selected trust anchor** and its provenance; a self-signed root does not prove its own trustworthiness.

In Java, commonly involved classes include:

| Component | Role |
| --- | --- |
| `KeyStore` | Stores entries, serving as an identity keystore or truststore |
| `TrustedCertificateEntry` | Public certificate chosen by an administrator as a trust anchor / trust policy input |
| `TrustManagerFactory` | Initializes trust managers from a `KeyStore` or default trust configuration |
| `X509TrustManager` / `X509ExtendedTrustManager` | Verifies certificate chains in the TLS session context and per provider/policy |
| `CertPathValidator("PKIX")` | API for validating a certificate path against trust anchors/policy parameters |
| `CertPathBuilder` | Helps build certificate paths through intermediates/trust anchors when suitable data exists |
| `KeyManagerFactory` | Supplies **the application's own** private key + chain when acting as server or mTLS client |

**Boundary note:** Validating a path with `CertPathValidator("PKIX")` against a known `TrustAnchor` **does not supply the hostname to compare**. That is part A and cannot replace part B. The demo program in section 9 intentionally lets PKIX pass and then lets HTTPS endpoint identification demonstrate a hostname mismatch.

### 2.1. A truststore is not a "list of every allowed hostname"

A truststore holding `Example Internal Root` may trust **many leaf certificates** signed by that CA or its intermediates. A leaf issued for `hr.internal` must never be accepted in place of `payroll.internal` merely because both share the same CA.

**Trusting a CA is not pinning a host.** Public key or certificate pinning (if required by policy) is an additional mechanism with complex lifecycle/rotation, and does not replace HTTPS hostname validation. In particular, trusting a broad internal CA while disabling hostname checks is a high-impact vulnerability.

### 2.2. Root, intermediate, and what chain does the server send?

A TLS server normally sends the **leaf and intermediate(s)** needed to build a path; the root trust anchor is stored locally by the client (not required from the server). If an intermediate is missing, the client may fail to build the path, causing **path building failed** even when the leaf has the right SAN.

Even if the server sends its root, it **cannot force the client to trust that root**. The client must obtain trust anchors from an independently verified source and its own policy. Thus, "server sends complete chain" and "client trusts the right CA" are two distinct responsibilities.

## 3. Hostname verification is a separate check

Hostname verification compares the **reference identity** (the name the application intends to contact) against the **presented identity** on the **leaf X.509 certificate**.

Example:

~~~text
URL target:          https://api.example.com
Reference identity:  api.example.com

Leaf SAN:
  DNS: api.example.com
  DNS: api-backup.example.com

=> api.example.com matches an appropriate DNS SAN
~~~

A valid certificate for `admin.example.com` is not automatically valid for `api.example.com`. That the server holds the private key and has a CA signature only proves the server possesses the key of **some identity certified by the CA**; you still need the step matching the target identity.

### 3.1. Where does the reference name come from?

For HTTPS, the reference hostname usually comes from the **hostname in the URL/endpoint configured by the application**, parsed and canonicalized per protocol rules—never arbitrarily taken from:

- `Issuer DN` or `Subject CN` of the server certificate;
- `Host` header suggested by the peer after connecting;
- DNS PTR / reverse DNS of the IP address;
- SNI echoed back by the server;
- Alias names in a `KeyStore`;
- A new name returned by an attacker in a response or redirect that the application blindly treats as the original name.

For example, an HTTPS client connects to `https://api.example.com`; DNS may resolve it to `203.0.113.10`, yet the reference identity remains **api.example.com**, not the resolved IP. If the user **intentionally** calls `https://203.0.113.10`, the reference identity is the **IP literal** and must follow IP SAN rules.

**If the application goes through a proxy, load balancer, or connects by IP while expecting a DNS identity:** preserve the right **logical peer host** when creating the TLS/HTTP client. `SSLSocketFactory.createSocket(tcp, "api.example.com", port, true)` preserves the peer hostname for SNI and endpoint checking when the TCP socket was opened to an IP; this must be designed around the client API and connection policy, never picked from the returned certificate.

### 3.2. SAN is the standard identity source

`Subject Alternative Name` is an X.509 extension supporting several identity types:

| SAN type | Example | When used |
| --- | --- | --- |
| `dNSName` (type 2) | `DNS:app.example.com` | When the client verifies a DNS name over HTTPS |
| `iPAddress` (type 7) | `IP:192.0.2.10`, `IP:2001:db8::1` | When the URL/endpoint uses an IP literal and TLS policy requires IP matching |
| `uniformResourceIdentifier` (type 6) | `URI:spiffe://domain/service` | Specialized workload identity protocols with URI matching rules; **not automatically** a substitute for HTTPS DNS hostnames |
| `rfc822Name` | Email | Not used as an HTTPS DNS hostname |

**Comparison examples:**

| Client requests | Leaf certificate contains | Name check result |
| --- | --- | --- |
| `https://localhost` | `DNS:localhost` | Match |
| `https://127.0.0.1` | Only `DNS:localhost` | **Mismatch** because `IP:127.0.0.1` is missing |
| `https://127.0.0.1` | `IP:127.0.0.1` | Matches by type/name, **provided chain is trusted** |
| `https://api.example.com` | `DNS:api.example.com` | Match |
| `https://api.example.com` | `DNS:other.example.com` | **Mismatch** |
| `https://api.example.com` | Only `CN=api.example.com` | **Do not rely on CN**; issue proper SAN |
| `https://192.0.2.10` | `DNS:192.0.2.10` | **Does not substitute for a valid IP SAN** when an IP literal is requested |

**An IP inside a DNS SAN is not equivalent to an `iPAddress` SAN.** Just because a string has dots and digits looking like an IP does not mean putting it under type DNS will pass HTTPS IP matching.

### 3.3. Common Name (CN) and legacy fallback

Some historical TLS implementations may fall back to `Subject CN` when a certificate lacks a matching DNS SAN; exact rules vary by platform, version, and standard. **Do not treat that fallback as a design target**, and never rely on CN when issuing or evaluating new HTTPS certificates.

For modern server certificates, proactively ask the CA to issue **SAN DNS/IP entries of the right type and matching the real hostname**. If an environment still accepts CN without SAN, treat that as legacy compatibility to manage and harden—**it does not prove every client will accept it**.

### 3.4. Wildcards and IDNs (Internationalized Domain Names)

- `DNS:*.example.com` must be understood only within the wildcard limits accepted by the client/protocol; **never assume** it covers `example.com` or `a.b.example.com`.
- `*.example.com` is not an unlimited grant for every subdomain depth. Standards/clients may impose additional wildcard/public-suffix constraints.
- IDNs (non-ASCII names) normally involve **IDNA/Punycode A-labels**, normalization, and case-insensitive matching per DNS rules; **never substitute `String.equalsIgnoreCase`** for standard algorithms.
- URLs, SNI, certificate SANs, and HTTPS libraries must agree on name representation; if an application must handle names at a low layer, prefer standard APIs or interoperability-tested libraries.

**Never write a naive `hostnameMatches` function** using `endsWith(".example.com")`, as it is prone to label-boundary bugs, wildcard flaws, internationalized-name issues, and string confusion.

## 4. Why is valid PKIX still not enough for HTTPS?

Two scenarios make this crystal clear:

### 4.1. Trusted CA signs a certificate for a different hostname

~~~text
Client truststore:  Root CA R

Certificate X signed by R:
  Subject/SAN = DNS:files.example.com
  Validity    = valid
  Signature   = valid

Client intends to connect to:
  https://payments.example.com

Path trust  = PASS (R is trusted)
Name match  = FAIL (files != payments)
Decision    = REJECT
~~~

If the application disables name checking, any party granted a valid certificate by a trusted CA (such as an internal CA authorized to issue for many hostnames) can be mistaken for the target endpoint. TLS still encrypts traffic to that peer, yet **the peer is not verified as the intended service**.

### 4.2. Right hostname, untrusted CA

~~~text
Self-signed certificate:
  SAN DNS:payments.example.com
  Issuer = itself
  Signature self-verifies

Client truststore:
  Does NOT trust this certificate's public key/root

Name match  = PASS on name
Path trust  = FAIL on trust anchor
Decision    = REJECT
~~~

An attacker can generate a self-signed certificate carrying any hostname. Therefore, **SAN matching does not replace chain trust**. HTTPS errors are only resolved properly when the client has valid trust anchors or the server deploys a chain from an accepted CA with the matching name.

### 4.3. Do not confuse "enabling TLS" with "authenticating the right peer"

A socket using TLS 1.3 and a strong cipher suite with encryption **does not guarantee** the application is talking to the intended party if CA validation or hostname verification is skipped.

- **Trust-all certificate**: bypasses path trust verification.
- **Always-true `HostnameVerifier`** or a raw `SSLSocket` without endpoint identification: bypasses name verification.
- **Both are dangerous**, yet they are two separate bugs. Fixing a CA error never requires disabling hostname checks; fixing a hostname error never requires trust-all.

## 5. Where does Java/JSSE perform the two checks?

Java APIs have different defaults; distinguish **high-level HTTPS clients** from **raw TLS sockets**.

### 5.1. `HttpsURLConnection`

`javax.net.ssl.HttpsURLConnection` is designed for HTTPS and by default performs certificate/trust verification and hostname verification using standard mechanisms (unless the application installs a custom trust manager, custom hostname verifier, or insecure config). Never write:

~~~java
// DANGEROUS ANTI-PATTERN - DO NOT USE
connection.setHostnameVerifier((host, session) -> true);
~~~

That turns hostname checking into "always accept". It is not a fix for a certificate name mismatch. If the URL is `https://api.example.com` while the server only has SAN `DNS:localhost`, the right fix is to **request a certificate for `api.example.com`** or fix the URL/target per verified requirements.

Do not replace `HttpsURLConnection`'s `SSLSocketFactory` with a trust-all factory. Configure a truststore with the right root CA and let the client perform endpoint verification via the API.

### 5.2. `java.net.http.HttpClient` (JDK 11+)

Modern `HttpClient` uses TLS and performs HTTPS endpoint verification under standard configurations. You can configure an `SSLContext` using an internal truststore when connecting to services with a private CA—**never create an `X509TrustManager` that ignores all errors**.

Note that internal JVM flags or properties can affect hostname verification in specific implementations; **never use "disable hostname verification" switches to fix production**. Run real HTTPS tests using the actual URL hostname and CA chain matching your deployment environment.

### 5.3. Raw `SSLSocket` and `SSLEngine`

**Common pitfall:** Creating a raw `SSLSocket` or `SSLEngine` with a standard trust manager **does not automatically enable HTTPS hostname checking**. Lower-level TLS APIs do not know which application protocol you are running or which reference hostname to compare against.

When using a raw `SSLSocket` as an HTTPS client and applying HTTPS endpoint identification:

~~~java
SSLSocket socket = /* client socket connected to the right peer */;
SSLParameters parameters = socket.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(parameters);
socket.startHandshake();
~~~

**This is only an excerpt**, not a standalone class. With `SSLEngine`, configure `SSLParameters` similarly before the handshake, and ensure the engine has the right peer host and peer port per the API.

`"HTTPS"` is JSSE's endpoint-identification algorithm name, not an argument to `Cipher.getInstance` and not an HTTP request header. The reference name must come from the **trusted target chosen by the application**, never from a value sent back by the server.

### 5.4. `TrustManagerFactory` vs. `HostnameVerifier`

| API | Primary role | Do not misunderstand as |
| --- | --- | --- |
| `TrustManagerFactory.init(trustStore)` | Builds trust managers from a set of trust anchors | **Does not pick a URL hostname** from the application automatically |
| `X509TrustManager.checkServerTrusted` | API verifying trust/cert chain per provider and context; base interface takes no hostname | Do not write a "path-only custom check" and treat it as a hostname check |
| `X509ExtendedTrustManager` | Socket/engine-aware trust check; can enforce endpoint identity when JSSE is configured | Must not be bypassed via arbitrary overrides |
| `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` | Instructs JSSE to verify endpoint name per HTTPS rules during handshake | Does not add a missing trust anchor |
| `HttpsURLConnection` | HTTPS stack with default hostname verification | A custom `HostnameVerifier` returning true breaks the policy |
| `CertPathValidator("PKIX")` | Evaluates certificate path per policy | Does not know the URL's DNS/IP reference unless supplied at the proper layer |

Some JSSE implementations invoke name checking inside socket/engine-aware trust checking; the check may share a call stack with chain validation. **Security-wise they remain two separate conditions**, not "calling one method makes the certificate automatically match any hostname".

### 5.5. `KeyManagerFactory` does not replace `TrustManagerFactory`

- A server identity keystore contains a **`PrivateKeyEntry`** with private key + leaf/chain so the server proves possession of the certificate's private key.
- A client truststore contains root/intermediate CAs actively accepted for path trust.
- `KeyManagerFactory` lets a server or mTLS client present its own identity.
- `TrustManagerFactory` lets the **verifying** side evaluate the peer's certificate.
- Reference hostname is determined by the **connection target**/endpoint, not by an alias or CN inside the server keystore.

A single PKCS12 file can hold multiple entry types, yet **responsibilities and policies** for identity vs. trust must stay separate.

## 6. Lab setup: one trusted CA, one DNS SAN

To see checks A and B differ clearly, we use a **self-created demo CA** (actively trusted by the client) and a server certificate signed by that CA whose SAN contains only **`DNS:localhost`**.

We then connect to the **same server** over loopback TCP `127.0.0.1`, passing two **different reference identities** to TLS:

- `localhost` with `HTTPS` endpoint identification → **succeeds**.
- `127.0.0.1` with `HTTPS` endpoint identification → **fails**, because the certificate **lacks `IP:127.0.0.1`**.
- `127.0.0.1` **without** hostname identification → **succeeds on chain**, yet **unsafe for verifying the right target**; included solely as a negative control in the lab.

**Prerequisites:** JDK 17+, `keytool`, and write permission in a fresh test directory. **Never use a production keystore**. The commands below pass a sample fixed password on the command line for reproducibility; in production, retrieve passwords from a secret manager/callback—never place them in Git, CI logs, shell history, or process listings.

### 6.1. Create a local root CA

~~~bash
keytool -genkeypair -alias demo-root -keyalg RSA -keysize 2048 -dname "CN=Local Demo Root,O=Learning,C=VN" -validity 7 -ext "bc=ca:true" -ext "ku=keyCertSign,cRLSign" -keystore ca.p12 -storetype PKCS12 -storepass demo-pass-123 -keypass demo-pass-123 -noprompt
~~~

The demo CA has `BasicConstraints CA=true` and `KeyUsage keyCertSign`; this is **not** a publicly browser-trusted certificate. RSA 2048 and a 7-day validity are for lab use only; a production root CA must follow policy, protect its CA private key (typically HSM), and enforce issuance/revocation procedures.

### 6.2. Export the public root CA certificate

~~~bash
keytool -exportcert -alias demo-root -keystore ca.p12 -storepass demo-pass-123 -rfc -file root.crt
~~~

`root.crt` is the public certificate, **without the CA private key**. For a real CA, verify the certificate fingerprint and provenance over an independent trusted channel before importing.

### 6.3. Create the server private-key identity

~~~bash
keytool -genkeypair -alias server-id -keyalg RSA -keysize 2048 -dname "CN=localhost,O=Learning,C=VN" -validity 7 -ext "san=dns:localhost" -keystore server.p12 -storetype PKCS12 -storepass demo-pass-123 -keypass demo-pass-123 -noprompt
~~~

At this step `server-id` holds a private key and self-signed placeholder. The DNS SAN `localhost` is **what the lab will check against**; there is no `IP:127.0.0.1`.

### 6.4. Create a CSR from that alias and have the CA sign the leaf

~~~bash
keytool -certreq -alias server-id -file server.csr -rfc -keystore server.p12 -storepass demo-pass-123 -ext "san=dns:localhost"
~~~

~~~bash
keytool -gencert -alias demo-root -infile server.csr -outfile server-issued.crt -rfc -keystore ca.p12 -storepass demo-pass-123 -validity 7 -ext "san=dns:localhost" -ext "ku=digitalSignature,keyEncipherment" -ext "eku=serverAuth"
~~~

The PKCS#10 CSR carries the public key, subject, and requested extensions; the private key **is not sent to the CA**. `-gencert` issues the actual leaf with DNS SAN `localhost` and lab-appropriate KU/EKU. Production CAs must validate name ownership and issuance policy rather than blindly signing any SAN requested by a CSR.

### 6.5. Install the CA certificate and signed reply into the server KeyStore

~~~bash
keytool -importcert -alias demo-root -file root.crt -keystore server.p12 -storepass demo-pass-123 -noprompt
~~~

~~~bash
keytool -importcert -alias server-id -file server-issued.crt -keystore server.p12 -storepass demo-pass-123 -noprompt
~~~

The second command **installs the certificate reply into the matching `PrivateKeyEntry` alias `server-id`**. The private key remains in `server.p12`; the leaf/chain is updated to the CA-issued certificate chaining to the demo root.

### 6.6. Create a client truststore holding only the demo root certificate

~~~bash
keytool -importcert -alias demo-root -file root.crt -keystore trust.p12 -storetype PKCS12 -storepass demo-pass-123 -noprompt
~~~

`trust.p12` is used by the client to trust the lab root. **Never** copy the CA private key in `ca.p12` to the client. The truststore is built from a certificate originating from a trusted lab environment; never blindly use `-noprompt` for an arbitrary root downloaded off the network.

### 6.7. Verify metadata before running Java

~~~bash
keytool -list -v -alias server-id -keystore server.p12 -storetype PKCS12 -storepass demo-pass-123
keytool -list -v -alias demo-root -keystore trust.p12 -storetype PKCS12 -storepass demo-pass-123
~~~

You should see:

- `server-id` is a `PrivateKeyEntry`, leaf SAN `DNSName: localhost`, issuer demo root, and matching chain.
- `demo-root` in `trust.p12` is a `TrustedCertificateEntry`, with no CA private key.
- The leaf contains **only DNS SAN `localhost`**, with **no IP SAN `127.0.0.1`**. This is **intentional** to test mismatch.

## 7. Complete Java 17+ program: same trusted CA, different name outcomes

Save the following program as **`TlsNameCheckDemo.java`** in the same directory as `server.p12` and `trust.p12`. The program runs over local loopback and makes no Internet connections.

### 7.1. Code

~~~java
import java.net.InetAddress;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.InputStream;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLHandshakeException;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

public class TlsNameCheckDemo {
    static KeyStore load(String filename, char[] password) throws Exception {
        KeyStore ks = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(Path.of(filename))) {
            ks.load(in, password);
        }
        return ks;
    }

    static SSLContext serverContext(KeyStore server, char[] password)
            throws Exception {
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(server, password);
        SSLContext ctx = SSLContext.getInstance("TLS");
        ctx.init(kmf.getKeyManagers(), null, new SecureRandom());
        return ctx;
    }

    static SSLContext clientContext(KeyStore trusted) throws Exception {
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trusted);
        SSLContext ctx = SSLContext.getInstance("TLS");
        ctx.init(null, tmf.getTrustManagers(), new SecureRandom());
        return ctx;
    }

    static boolean connect(SSLContext client, int port,
                           String peerName, boolean hostnameCheck)
            throws Exception {
        // Physical connection is always 127.0.0.1; peerName represents
        // the LOGICAL IDENTITY that the certificate must authenticate.
        Socket tcp = new Socket(InetAddress.getByName("127.0.0.1"), port);
        try (SSLSocket ssl = (SSLSocket) client.getSocketFactory()
                .createSocket(tcp, peerName, port, true)) {
            SSLParameters parameters = ssl.getSSLParameters();
            if (hostnameCheck) {
                parameters.setEndpointIdentificationAlgorithm("HTTPS");
            }
            ssl.setSSLParameters(parameters);
            ssl.startHandshake();
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        char[] password = "demo-pass-123".toCharArray();
        try {
            KeyStore server = load("server.p12", password);
            KeyStore trust = load("trust.p12", password);
            X509Certificate leaf = (X509Certificate)
                    server.getCertificate("server-id");
            X509Certificate root = (X509Certificate)
                    trust.getCertificate("demo-root");

            // STANDALONE PATH TRUST: verify leaf up to configured root.
            // Root is the trust anchor; do not include it in CertPath list.
            CertPath path = CertificateFactory.getInstance("X.509")
                    .generateCertPath(List.of(leaf));
            PKIXParameters pkix = new PKIXParameters(
                    Set.of(new TrustAnchor(root, null)));
            pkix.setRevocationEnabled(false); // Offline demonstration only!
            CertPathValidator.getInstance("PKIX").validate(path, pkix);
            System.out.println("PKIX trusted        = true");

            SSLContext serverTls = serverContext(server, password);
            SSLContext clientTls = clientContext(trust);
            try (SSLServerSocket listener = (SSLServerSocket)
                    serverTls.getServerSocketFactory().createServerSocket(
                            0, 10, InetAddress.getByName("127.0.0.1"))) {
                Thread responder = new Thread(() -> {
                    for (int i = 0; i < 3; i++) {
                        try (SSLSocket accepted =
                                (SSLSocket) listener.accept()) {
                            accepted.startHandshake();
                        } catch (Exception ignored) {
                            // Demo: client abort on hostname mismatch is expected.
                        }
                    }
                });
                responder.start();
                int port = listener.getLocalPort();

                System.out.println("HTTPS localhost     = " +
                        connect(clientTls, port, "localhost", true));

                boolean mismatchRejected = false;
                try {
                    connect(clientTls, port, "127.0.0.1", true);
                } catch (SSLHandshakeException expected) {
                    mismatchRejected = true;
                }
                System.out.println("HTTPS IP rejected   = " +
                        mismatchRejected);

                // DELIBERATELY UNSAFE: trust chain is still checked,
                // yet endpoint name verification is skipped.
                System.out.println("Chain-only IP       = " +
                        connect(clientTls, port, "127.0.0.1", false));
                responder.join();
            }
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
~~~

### 7.2. Compile and run

~~~bash
javac TlsNameCheckDemo.java
java TlsNameCheckDemo
~~~

Verified output after running the `keytool` commands in section 6 inside an **empty test directory**:

~~~text
PKIX trusted        = true
HTTPS localhost     = true
HTTPS IP rejected   = true
Chain-only IP       = true
~~~

**Accurate interpretation of each output line:**

1. `PKIX trusted = true`: leaf `server-id` was signed by the demo CA in `trust.p12` and `CertPathValidator` accepted the path **under lab conditions**. This call **does not check hostnames** and intentionally disables revocation because the demo CA has no CRL/OCSP.
2. `HTTPS localhost = true`: the TCP client connects to loopback `127.0.0.1`, while the TLS **reference name** is `localhost`; leaf SAN `DNS:localhost` matches and the trust chain is valid, so the handshake succeeds.
3. `HTTPS IP rejected = true`: the client uses the **exact same CA root, same server, and same TLS context**, except the reference name is IP literal `127.0.0.1`. The certificate has only a **DNS SAN**, lacking a matching `iPAddress SAN`. JSSE rejects it with `SSLHandshakeException` when endpoint algorithm `HTTPS` is enabled.
4. `Chain-only IP = true`: same IP and truststore, yet **deliberately skipping hostname checking**, so the handshake succeeds. **This line illustrates an anti-pattern for learning**, not safety; it proves chain validation **does not guarantee the right endpoint**.

**Key detail of the demo:** `createSocket(tcp, peerName, port, true)` keeps the TCP connection to `127.0.0.1` while passing logical name `peerName` to TLS for endpoint identity checking. **Changing the logical name** here is solely a differential test—**never let an application arbitrarily pick a name suggested by the server**. In real systems, the name must come from a verified URL or configuration.

**The program prints no private keys**; the demo password is wiped in the `char[]` held by the program, though literals/passwords on command lines or inside provider objects can leave copies in RAM/logs. Never treat sample code as a production password-storage pattern.

### 7.3. Why doesn't the program send a real HTTPS request?

`SSLServerSocket` only runs a **local TLS handshake**, without implementing an HTTP parser or sending responses; what we need to prove is the two verification conditions directly at the TLS layer.

A high-level HTTPS client may also handle URL parsing, redirects, hostname validation, connection reuse, proxies, and other HTTP mechanics. The demo does not simulate all of those. It simply shows the independence of **PKIX trust** and **endpoint identification** using standard JSSE APIs.

In the branch simulating disabled hostname checks, the server still presents a CA-signed certificate, and the client's `TrustManagerFactory` still runs. Thus `Chain-only IP=true` is direct visual proof that **trusting the CA is not enough**.

### 7.4. Security boundaries of the lab

- The root CA and server cert were created in an environment you control; they are not a real CA or public PKI.
- `PKIXParameters.setRevocationEnabled(false)` is set **only for offline testing**. In real deployments, revocation policies and failure behavior must be defined.
- The certificate SAN contains only `localhost`, validity is very short, and the sample password is fixed; unsuitable for public HTTPS.
- `SSLSocket` is not a complete HTTPS/mTLS client; it does not demonstrate HTTP redirects, cookies, proxies, authorization, or session caching.
- Beyond name and chain, clients still require strong TLS algorithms, protected private keys, proper certificate usage, and expiration/revocation policies.

## 8. How to configure properly when internal CA and hostname mismatch

Suppose a company has an internal CA issuing certificates:

~~~text
Target URL: https://orders.internal.example
Server SAN: DNS:orders.internal.example
CA:        Company Issuing CA -> Company Root CA
~~~

The client must enforce both:

1. **Trust chain:** Obtain the appropriate root CA through a trusted administrative channel, verify its fingerprint/trust chain, and place it in the client truststore or matching trust manager; ensure the full intermediate chain is present.
2. **Name match:** Connect via `orders.internal.example` (the right reference identity), with a matching SAN on the leaf certificate; keep endpoint identification enabled.

If you need direct IP access, there are two clear design choices:

- **Use the endpoint's real DNS name** and let DNS/TCP route to the needed IP; the reference identity remains that hostname.
- If the real endpoint is officially identified by an IP literal, **issue a certificate with an `iPAddress` SAN matching that IP** and configure the application to connect by that IP, with a valid trust chain.

**Never fix this with** `HostnameVerifier((host, session) -> true)`, an empty `X509TrustManager.checkServerTrusted`, enabling trust-all, or accepting all hostnames just for `dev`. Such shortcuts frequently get copied into staging/production and open MITM vulnerabilities.

### 8.1. SNI is not hostname verification

**Server Name Indication (SNI)** is an extension in TLS `ClientHello` allowing the client to indicate the desired hostname so a multi-virtual-host server picks the right certificate.

- SNI helps the **server choose** a leaf certificate.
- **Hostname verification** is the **client verifying** that the chosen certificate carries a name matching the endpoint the client requested.
- That the server saw the right SNI does not guarantee it returned the right certificate; the client must still verify chain and SAN.
- With IP literals, SNI sending behavior varies by API/implementation; never rely on SNI to "save" a certificate missing an IP SAN.

SNI is a routing/certificate-selection hint, **not cryptographic proof of server identity**.

### 8.2. DNS lookup, connecting by IP, and logical names

An application can resolve `api.example.com` to `10.0.0.8` and open TCP to that IP, while keeping `api.example.com` as the reference identity. That is normal behavior.

Conversely, if the application only uses `https://10.0.0.8` while the certificate only has `DNS:api.example.com`, **never disable hostname checks**; fix the target config, issue an IP SAN per policy, or route via DNS.

**Be careful:** A hostname in an HTTP `Host` header does not grant trust after the TLS handshake completes; an attacker controlling the HTTP layer must never be allowed to "switch" the reference identity to legitimize an already-presented certificate.

### 8.3. Redirects and connection reuse

An HTTPS client may encounter a redirect `Location: https://another.example.com/...`. Every HTTPS endpoint the client actually connects to must be verified against **that endpoint's hostname** and a valid trust chain.

Never reuse an old certificate from endpoint A to trust endpoint B while skipping hostname checks. With HTTP/2 connection coalescing or pooling, high-level clients must enforce origin security rules per standard/implementation; applications must never bypass this by sharing raw sockets without name verification.

## 9. Distinguishing error messages in Java

Trust-chain failures and hostname failures can both surface under `SSLHandshakeException` at the outer layer, yet their root causes differ.

| Typical message / symptom | Failing check | Proper remediation |
| --- | --- | --- |
| `PKIX path building failed` | Cannot build chain to an accepted trust anchor | Check truststore, root/issuer/intermediate, chain sent by server, policy |
| `unable to find valid certification path` | No path satisfies trust policy | Import properly sourced CA into truststore; install complete intermediates |
| `No subject alternative DNS name matching ... found` | DNS SAN does not match hostname | Issue cert with right DNS SAN, or fix target URL/config |
| `No subject alternative names matching IP address ... found` | Missing `iPAddress SAN` matching IP literal | Issue proper IP SAN when using IP identity, or use standard DNS endpoint |
| `certificate expired` / `not yet valid` | NotAfter/NotBefore or system clock | Renew certificate / fix clock after checking source |
| `Extended key usage does not permit ...` | EKU unsuitable for TLS purpose | Have CA issue leaf with profile-appropriate EKU |
| `Algorithm constraints check failed` | Key/signature/cipher rejected by policy/JDK | Reissue compliant cert/key; never disable constraints carelessly |
| `certificate revoked` | Rejected by policy-configured revocation checker | Investigate CA/revocation; follow key compromise procedures |
| TLS handshake succeeds, yet raw socket client called wrong hostname | Likely **endpoint identification is not enabled** | Check `SSLParameters`/client TLS stack and identity reference |
| Error vanishes after setting `HostnameVerifier` to always true | **Disabled name checking**, did not fix certificate | Remove bypass; fix SAN/trust/URL at root cause |
| Error vanishes after trust-all manager | **Disabled CA/path trust**, did not fix chain | Restore standard trust manager; supply verified trust anchors |

**Never catch `SSLHandshakeException` and retry with `SSLParameters` lacking endpoint identification.** A "downgrade security on retry" pattern lets an attacker deliberately trigger the first error to force skipping verification on the retry. When logging causes, record the exception class, configured target URL/hostname, appropriately filtered certificate metadata, truststore version, and policy; **never log private keys, passwords, session secrets, or tokens**.

### 9.1. Why do chain errors sometimes hide name errors?

If the server sends a certificate from an untrusted CA, the handshake can fail **before reaching the name check**, so you only see the path error. Once you fix the truststore properly, you then see the hostname mismatch. This is not "fixing A caused bug B"—**both conditions failed from the start**.

Diagnostic strategy: determine the reference hostname/IP; inspect the chain and leaf SAN independently; never turn off one check to look for the other on a system serving real requests.

## 10. Inspecting certificate SANs and chains during investigation

Useful technical commands in authorized environments:

~~~bash
# Inspect leaf and chain stored in PKCS12:
keytool -list -v -alias server-id -keystore server.p12 -storetype PKCS12 -storepass demo-pass-123

# Inspect root trusted by client in the lab:
keytool -list -v -alias demo-root -keystore trust.p12 -storetype PKCS12 -storepass demo-pass-123

# Inspect CA-signed leaf certificate:
keytool -printcert -file server-issued.crt -v
~~~

In production, avoid passing `-storepass` directly on the command line; use secure credential-entry methods appropriate to your tools and environment. Never use `-noprompt` to add unverified root CAs.

If authorized to inspect public/offline servers, `openssl s_client` can display chains, yet **you must understand its flags**: simply printing certificates does not necessarily perform hostname verification; flags like `-verify_hostname`/`-verify_ip` along with CA trust/policy must be explicitly configured when checking names. Never treat `Verify return code: 0` from an `s_client` run lacking hostname verification as proof that all HTTPS checks passed.

### 10.1. Do not use `CN` or aliases to work around SAN errors

If `keytool -list` shows:

~~~text
Alias: backend-key
Owner: CN=api.example.com
SubjectAlternativeName:
  DNSName: old.example.com
~~~

You cannot treat the matching CN as sufficient for all clients, especially when a DNS SAN is present yet **does not match the reference hostname**. Have the CA issue a certificate with the right SAN. Alias `backend-key` is neither a TLS endpoint DNS name nor a grant of additional trust.

### 10.2. Verify the exact truststore actually used by the client

A Java runtime may use the **default truststore** (e.g., `cacerts` depending on JDK/distribution) or a **custom truststore** via JSSE configuration. Importing a root into a file the application **does not use** will not change trust decisions.

Inspect the actual runtime/container configuration: exact file/path, type, password, permissions, process restart/reload, and whether the client library uses that `SSLContext`. Never modify global JVM security properties just to fix a single endpoint when a scoped `SSLContext` truststore meets policy with narrower blast radius.

**Adding a root to a truststore must be a controlled security decision**; if a root has overly broad authority, every leaf endpoint it signs will pass path trust, making hostname verification even more critical.

## 11. HTTPS, mTLS, and bidirectional identity

In standard HTTPS, **the client verifies the server**. In mTLS, **the server also verifies the client's certificate**.

~~~text
HTTPS:
  Client --> checks server chain + URL's server hostname
  Server --> presents private key + certificate chain

mTLS:
  Client --> still checks server chain + server hostname
  Server --> checks client chain + clientAuth/identity policy
  Application --> maps client identity to specific permissions
~~~

Principles:

- mTLS **does not exempt the client** from server hostname verification. If the client trusts the CA yet skips name checking, it still risks connecting to the wrong valid service.
- An mTLS server normally verifies the client certificate chain against an accepted CA, `clientAuth` purpose, and **authorized identity** (e.g., URI/DNS SAN or subject per policy). The server does not "check a server hostname" on the client; it must identify and authorize the **client identity** per policy.
- A workload identity URI SAN such as SPIFFE follows its own verification and mapping rules, not to be confused with HTTPS DNS name matching.
- When one CA issues certificates to many services, the server needs an **authorization policy** deciding which client identity may call which API—never "signed by company CA means access everything".

On a TLS server receiving a client cert, a trusted chain does not make the caller an admin. On a TLS client verifying a server, a matching hostname and trusted chain do not guarantee a response belongs to the right tenant or is authorized at the application layer.

## 12. Certificates for localhost, dev, staging, and production

**Why do developers often turn off hostname checking?** A certificate was issued for `dev.example.com` while accessed via `localhost`, `127.0.0.1`, or a container IP, causing a mismatch.

The right approach:

- If dev uses `https://localhost`, issue a dev cert with **`DNS:localhost`** and a dev CA trusted strictly within dev scope.
- If a dev client connects to `https://127.0.0.1`, the certificate needs **`IP:127.0.0.1`**; having `DNS:localhost` is not enough.
- If staging uses `staging-api.example.test`, issue a cert with matching SANs rather than copying `api.example.com`'s certificate and disabling name checks.
- If production uses a load balancer/ingress, the certificate at the **TLS termination point** must match the URL hostname clients call. Any separate LB→backend connection also needs proper TLS/endpoint-verification policy if protected by TLS.
- In containers, internal cluster DNS service names can differ from public hostnames; clearly design the **reference identity for each hop** and its corresponding SAN/CA.

**Never share a dev root CA with production** unless under an explicit controlled process, as broad trust could allow dev certificates to be accepted in production. Scope CAs/truststores to each security domain with controlled rotation.

## 13. Common security mistakes

| Mistake | What actually breaks | Proper fix |
| --- | --- | --- |
| "Chain signed by trusted CA ⇒ right server" | Omits endpoint name binding | Verify SAN against reference hostname/IP |
| "Having `CN=api.example.com` ⇒ every client accepts it" | CN fallback is insufficient/inconsistent | Have CA issue proper DNS/IP SAN |
| "`DNS:127.0.0.1` equals `IP:127.0.0.1`" | Wrong SAN type | Use `iPAddress` SAN for IP literals |
| "Imported new root, still hostname error → disable name check" | Accepts wrong peer | Fix URL/hostname or request cert with right SAN |
| "Server sent root, so client must trust it" | Breaks trust anchor model | Manage truststore from trusted sources |
| "`CertPathValidator` passed ⇒ HTTPS verified" | PKIX path knows no URL host | Enforce separate HTTPS hostname identification |
| "Raw `SSLSocket` with default truststore checks host automatically" | Endpoint identification may be off | Set `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` |
| "Just check `SSLSession.isValid()` for identity" | Session validity does not prove right hostname | Enforce endpoint check in handshake/connection policy |
| "Use always-true `HostnameVerifier` to bypass error" | Disables name check | Keep default verifier; issue matching cert |
| "Trust-all `X509TrustManager` in dev is harmless" | Disables path trust, leaks into prod | Create separate dev CA and scoped truststore |
| "Take hostname from peer certificate" | Attacker picks target name instead of app | Take hostname from trusted URL/config |
| "SNI is set right, so cert needs no SAN" | SNI only helps select cert | Client still verifies SAN |
| "Connecting to `api.example.com`'s IP means check only IP" | Loses intended DNS identity | Keep URL hostname as reference identity |
| "mTLS has internal CA ⇒ no authorization needed" | Any client leaf under that CA may be accepted | Map identity→permissions, EKU/role checks |
| "Skip revocation because path is valid" | Revoked certificates remain usable | Apply revocation policy per threat model |
| "Tested on one machine ⇒ works everywhere" | Truststores/JDKs/policies differ | Test across every supported runtime/client |

**Critical anti-pattern:** Never create a `HostnameVerifier` always returning `true`, never install an unvalidating `X509TrustManager`, and never retry handshakes in an "allow insecure" mode. These are not harmless workarounds—they **disable authentication** in TLS.

## 14. Application testing and CI

A solid test suite requires two **independent** test groups:

### 14.1. Path trust tests

1. Leaf signed by client-trusted CA, full chain ⇒ path passes.
2. Leaf signed by untrusted CA ⇒ path fails.
3. Missing intermediate ⇒ path building fails if client cannot construct a valid chain.
4. Intermediate lacks required `CA=true`/`keyCertSign` ⇒ path fails.
5. Expired/not-yet-valid cert ⇒ fails.
6. Signature/certificate algorithm forbidden by policy ⇒ fails.
7. Revoked certificate ⇒ fails when revocation policy requires it.

Never run tests by disabling hostname verification and conclude the app is secure; isolated path tests are one technical test layer, while integration tests must enforce both conditions.

### 14.2. Endpoint identity tests

1. Trusted leaf SAN `DNS:localhost`, reference `localhost` ⇒ passes.
2. Same leaf and CA, reference `127.0.0.1` without IP SAN ⇒ fails.
3. Trusted leaf SAN `IP:127.0.0.1`, matching IP reference ⇒ passes.
4. Trusted leaf SAN `DNS:files.example.com`, reference `payments.example.com` ⇒ fails.
5. Cert has only CN without matching SAN ⇒ do not accept via CN fallback as a production test requirement.
6. Wildcard at wrong level or hostname outside wildcard scope ⇒ fails.
7. IDN/Punycode, case/label, and canonicalization cases ⇒ verified using standard HTTPS libraries.
8. SNI/virtual hosting selects a different cert ⇒ endpoint checker catches mismatched SAN.

**A high-value test:** Same CA/truststore, same TCP endpoint, varying only the **reference identity** ⇒ one case passes and one fails, just like the section 7 program. This catches "trust-chain-only" client misconfigurations before deployment.

### 14.3. Testing real HTTPS clients

Beyond raw socket labs, run integration tests against the APIs actually deployed: `HttpsURLConnection`, `HttpClient`, OkHttp/Apache HttpClient, Netty, or service frameworks. Inspect `SSLContext`, truststore, proxies, redirects, SNI, and hostname verification. If a framework offers an option to disable hostname verification, CI/policy should reject that configuration in environments holding real data.

**Never verify visually by looking at certificate Subject.** Test handshakes against two specific reference identities, log pass/fail outcomes, and never output private keys or session secrets.

## 15. Self-check questions and answers

**Question 1.** A leaf has SAN `DNS:billing.example.com`, a valid CA, and is unexpired. The client calls `https://pay.example.com`. Will it be accepted?

**Answer:** **No.** Path trust may pass, yet reference hostname `pay.example.com` is not in a matching SAN. You need a certificate with the right name or a policy-aligned URL/target.

**Question 2.** Leaf SAN matches `DNS:api.example.com`, but the certificate is self-signed and the client does not trust the root. Can it be accepted because the hostname matches?

**Answer:** **No.** Name matching does not replace chain/trust-anchor validation. You need an appropriate CA/truststore and verified trust provenance.

**Question 3.** Is `DNS:localhost` valid when the application calls `https://127.0.0.1`?

**Answer:** **No**, under HTTPS IP-literal matching: an `iPAddress` SAN matching `127.0.0.1` is required, or connect using DNS `localhost` if that is the intended target name.

**Question 4.** Why doesn't a successful `CertPathValidator.getInstance("PKIX").validate(...)` prove it's the right server?

**Answer:** It validates the certificate path against supplied trust anchors and policy; it has no URL reference hostname for HTTPS endpoint identity. Separate SAN/hostname verification via HTTPS/JSSE is required.

**Question 5.** A raw `SSLSocket` uses a standard `TrustManagerFactory` and TLS 1.3, without calling `setEndpointIdentificationAlgorithm("HTTPS")`. Is HTTPS hostname checking guaranteed?

**Answer:** No. A raw socket may only verify the certificate trust chain. Supply the right peer name and enable endpoint identification per protocol, or use a high-level HTTPS client that does so.

**Question 6.** SNI carries `api.example.com`; the server returns a certificate with `DNS:other.example.com`. Can it be accepted because SNI was right?

**Answer:** No. SNI only helps select the certificate; the client must still verify that the returned certificate's SAN matches the reference identity.

**Question 7.** Is importing an arbitrary root CA from an email into the truststore safe to fix `PKIX path building failed`?

**Answer:** No. Roots/CAs must have their source and fingerprint verified through a trusted channel; trusting a rogue CA lets an attacker issue certificates for target endpoints.

**Question 8.** An mTLS server gets a valid client certificate chain from an internal CA. Does that make every client certificate from that CA an admin?

**Answer:** No. The server still needs to map certificate identity (and EKU/policy) to the permitted rights of each client/service. Trust never grants application permissions automatically.

**Question 9.** A certificate has `CN=api.example.com` yet SAN `DNS:old.example.com`. How should a client calling `api.example.com` handle this?

**Answer:** Never rely on CN to override an issued SAN; obtain a certificate with a SAN matching the target name. Legacy fallback rules may differ, yet are not a safe modern deployment path.

**Question 10.** Does the Java lab printing `PKIX trusted = true` and `HTTPS IP rejected = true` contradict itself?

**Answer:** No. CA/path checking and endpoint name checking are independent. The leaf is trusted for `localhost` yet **invalid for IP literal `127.0.0.1`**.

**Question 11.** Why shouldn't hostname be taken from reverse DNS of the TCP connection's IP?

**Answer:** Because the reference identity must be the target the application intends to contact (URL/config), whereas reverse DNS is not proof that a certificate was issued for that target and can be wrong or attacker-controlled under the threat model.

**Question 12.** What vulnerability can disabling `HostnameVerifier` to "fix" a TLS error create?

**Answer:** Accepting a trusted certificate belonging to a different hostname, leading to connecting to the wrong peer and MITM risk. Fix the SAN/URL/truststore root cause instead of disabling verification.

**Question 13.** The server has the right leaf and intermediate, yet the client still reports untrusted. What other causes are possible?

**Answer:** Client truststore does not trust the root, algorithm policy rejects the chain, certificate expired or was revoked, or another PKIX constraint failed. The server sending the root does not force the client to accept it.

**Question 14.** Why did the demo set `pkix.setRevocationEnabled(false)`, and why shouldn't that be copied to production?

**Answer:** The offline demo CA has no CRL/OCSP; disabling revocation gives deterministic test results, **not a safe production default**. Production must define revocation mechanisms and failure policies suited to the business/threat model.

## 16. Checklist for Java TLS applications

- [ ] Determine **reference hostname/IP from a trusted URL/config** before the handshake, never from the server certificate.
- [ ] Verify certificate **path/chain to an actively trusted root anchor**; never trust-all and never add unverified roots.
- [ ] Verify leaf **SAN has the right type**: `dNSName` for DNS hosts, `iPAddress` for IP literals; never substitute CN/aliases for SAN.
- [ ] For raw `SSLSocket`/`SSLEngine`, enable **`SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`** when performing HTTPS endpoint identity checks.
- [ ] For `HttpsURLConnection`/`HttpClient`, keep default hostname verification; never install an always-true custom verifier.
- [ ] Ensure SNI/virtual hosting selects an appropriate certificate **and still check names** client-side.
- [ ] Verify full chain/issuer signatures, validity dates, BasicConstraints, KU/EKU, algorithm constraints, and revocation policy.
- [ ] Never use a server-sent root as a reason to trust; truststores and CA policies need independent provenance.
- [ ] On hostname mismatch, **reissue with the right SAN or fix the endpoint name**; never disable verification to "clear the error".
- [ ] When accessing by IP literal, use an IP SAN; when accessing by DNS host, keep the DNS reference even though TCP connects to the resolved IP.
- [ ] Separate TLS authentication from authorization/tokens/tenants; in mTLS also verify client identity and permissions.
- [ ] Test both **trusted wrong-host** and **correct-host untrusted**, plus CA/revocation policies.
- [ ] Never log passwords, private keys, or session secrets; manage keys/truststores/rotation and inspect handshake errors safely.
- [ ] Test on the exact **client API/JDK/framework version going to production**, because raw TLS and HTTPS clients have different defaults.

## 17. Summary

**Certificate chain trust** and **hostname verification** answer **two different questions**. PKIX/trust managers determine whether a certificate path leads to an accepted trust anchor, while hostname verification compares the **client's intended target name** against a **matching SAN on the leaf**. Having a certificate from a trusted CA only proves the identity **issued by the CA in that certificate**, not that it matches the hostname you called. In Java, high-level HTTPS clients normally enable hostname verification by default; with raw `SSLSocket`/`SSLEngine`, you must explicitly configure endpoint identification when using HTTPS. The JDK 17+ example demonstrates clearly: **PKIX passes, `localhost` passes, IP mismatch is rejected, whereas chain-only without name checking passes unsafely**.

Foundational reading: [RFC 5280 — PKIX Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280), [RFC 6125 — service identity verification](https://www.rfc-editor.org/rfc/rfc6125), [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525), and [Java 17 JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html).