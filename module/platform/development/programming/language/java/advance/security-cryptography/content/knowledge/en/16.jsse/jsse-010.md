# 16.10 Avoiding Trust-All Configurations or Skipping Hostname Verification in Application Examples

A Java HTTPS snippet can **complete the TLS handshake, encrypt data, and return HTTP 200** yet still fail to protect users from a man-in-the-middle if the example author deliberately configured **trust-all certificates** or **skipped hostname verification**. This is one of the most dangerous anti-patterns when using **Java Secure Socket Extension (JSSE)**: certificate errors are hidden rather than fixed, "works on my machine" snippets get copied into real applications, and credentials/tokens may be sent to an unauthenticated peer.

**Rule of this lesson:** A secure TLS client must verify **both (1) the certificate path to a trusted trust anchor** and **(2) endpoint identity matching the exact hostname/IP the application intends to connect to**. Never drop either check because of a test environment or certificate error. The complete example here uses **Java's standard trust manager and `HTTPS` endpoint identification**, while actively testing cases where connections **must be rejected** — never building a trust-all implementation that could be copied by mistake.

This lesson belongs to **16. JSSE** and focuses on Java 17+ application examples: choosing a controlled truststore, enabling endpoint verification on low-level `SSLSocket`, preserving secure defaults of HTTPS clients, distinguishing trust errors from hostname errors, and testing/code-review strategies to keep unsafe configurations out of production.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain why **TLS encryption is not enough** if the peer is unauthenticated, and how **PKIX chain validation** and **hostname verification** answer two distinct questions.
2. Recognize anti-patterns: trust managers accepting all certificates, `HostnameVerifier` always returning `true`, disabling endpoint identification, disabling signature/expiration checks, or automatically retrying with an "insecure" configuration.
3. Write a **JSSE client using standard `TrustManagerFactory`**, a defined truststore, and `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` when needed.
4. Understand the behavior of `HttpsURLConnection`, `java.net.http.HttpClient`, `SSLSocket`, and `SSLEngine`, along with the responsibility boundary between `KeyManagerFactory` and `TrustManagerFactory`.
5. Run a demo with a local CA and a certificate having SAN `DNS:localhost`: **right CA + right hostname passes; wrong CA or wrong hostname must fail**.
6. Design negative/CI tests and fix `PKIX path building failed`, hostname mismatches, missing intermediates, and expired certificates at the root cause **without dropping security**.

## 2. What TLS protects, and what TLS cannot do when authentication is dropped

TLS provides multiple properties:

- **Confidentiality:** application traffic is encrypted when the handshake and cipher suite are used properly.
- **Integrity:** messages are protected against tampering within the TLS session.
- **Endpoint authentication:** the client must know it established a secure session with the **intended entity**.
- **Protocol policy:** TLS version, cipher suite, certificate purpose, trust, identity, and constraints are enforced per policy.

If the client **trusts every certificate**, a man-in-the-middle can create a self-signed certificate with their own key, establish a separate TLS session with the client, decrypt requests, and forward them to the real server over a second TLS session. Both sessions can use "strong encryption"; **the flaw is that the client authenticated the wrong party**.

If the client **checks the CA chain yet skips hostname verification**, an attacker holding a valid certificate for **a different hostname** can also be accepted when the application intends to call the target endpoint. For example, an internal CA issued a certificate for `inventory.internal`, while the client is configured to call `payments.internal`: the certificate chain may be valid and still **not the expected identity**.

~~~text
App intends to call: https://payments.example.test
                |
                v
             TLS peer
                |
       +--------+---------+
       |                  |
       v                  v
   PATH TRUST         ENDPOINT NAME
  CA/PKIX chain       DNS/IP in URL
  sig/validity        vs. leaf SAN
       |                  |
       +--------+---------+
                |
           BOTH PASS?
            /       \
          Yes        No
          |           |
   may proceed     ABORT handshake
   per policy      NO insecure fallback
~~~

**Trusting the certificate chain does not mean matching the hostname**, and **matching the hostname does not mean the CA is trusted**. Both conditions are mandatory in a compliant HTTPS client; whether TLS returns an `SSLSession` or uses AES-GCM does not alter this requirement.

### 2.1. Minimum decision table

| Chain/CA trusted | Hostname/IP matches | Right behavior |
| --- | --- | --- |
| Pass | Pass | Acceptable when other TLS checks and policies pass |
| Pass | **Fail** | **Reject**: certificate belongs to another host |
| **Fail** | Pass | **Reject**: inappropriate CA/trust anchor |
| **Fail** | **Fail** | **Reject**: both conditions fail |

The word "may" matters: you must also account for **KeyUsage, EKU, validity, algorithms, revocation, policy**, and application-layer **authorization**. A valid certificate does not implicitly permit executing payments or accessing arbitrary tenants.

## 3. What does a "trust-all" configuration actually break?

In JSSE, the trust manager is responsible for verifying the certificate chain per policy. A normal trust manager uses a pre-selected set of **trusted root CAs/certificates**, checking the chain, algorithms, and related conditions in the TLS context.

The trust-all anti-pattern typically follows this reasoning:

~~~text
If TLS reports "certificate not trusted":
    replace standard trust manager with one that always returns "accept"
    or strip all logic from checkServerTrusted(...)
    or alter accepted issuers to something else to avoid errors
Result: handshake can pass with anyone's certificate.
~~~

This is an **anti-pattern description**, not a guide to writing/installing a check-skipping trust manager. Never put an empty `X509TrustManager` or a trust-all `SSLContext` into practice code because snippets are easily copied. Likewise, `getAcceptedIssuers()` alone **does not decide whether a certificate is valid**; faking data there does not replace actual chain verification.

An application using trust-all can send:

- Bearer tokens, session cookies, API keys, or account credentials;
- User/payment data;
- System control request payloads;
- Critical responses the application believes came from the real server;

to an entity holding the private key of a certificate **never certified by any CA the user trusts**.

**Encryption without properly authenticating the peer cannot be considered secure HTTPS.** Turning on a stronger encryption cipher suite does not restore authentication that was removed.

### 3.1. Is "trust-all for localhost/dev only" okay?

Never use trust-all as an example template or workaround:

1. Dev/test flags can accidentally be enabled in staging/production.
2. A library calling `SSLContext.setDefault` or JVM-wide properties can break security for **other HTTP clients** in the same process.
3. Proxies, network testing tools, public Wi-Fi, or DNS controllers can actively mint arbitrary certificates to intercept traffic.
4. Quick workarounds fail to teach learners the **real cause**: untrusted CA, wrong hostname/SAN, missing intermediate, or expired certificate.
5. Tests passing with trust-all fail to verify the most critical property: whether the app **rejects invalid peers**.

**Right alternative for development:** create a **dedicated dev CA**, issue leaves with SANs matching the endpoint, put the verified dev CA certificate into a **dev-only truststore**, use the default trust manager on that store, and keep hostname verification enabled.

### 3.2. Why not "pin certificates" using trust-all?

Pinning a public key/certificate (when required by the threat model) is **an additional constraint**, not a license to drop default CA/hostname validation. Pinning implementations must plan for backup pins, rotation, avoiding accidental lockouts, and clearly defining the relationship to trust anchors. Trust-all code followed by comparing Subject strings or a fingerprint grabbed dynamically from a connection **is not secure pinning**; it can pin the attacker's certificate on first contact.

## 4. What failure does skipping hostname verification cause?

A client can **trust the CA** of a certificate yet be calling the **wrong host**:

~~~text
Target URL: https://pay.example.com
Leaf signed by trusted CA:
    SAN DNS: files.example.com

Chain validation = PASS
Name verification = FAIL
Safe decision = REJECT
~~~

Turning off hostname verification means the client **no longer requires the certificate to prove the target name**. With an internal CA capable of signing for many services, another valid server can accidentally or maliciously impersonate the target endpoint.

Anti-patterns to detect:

- A `HostnameVerifier` on `HttpsURLConnection` that **always returns `true`**;
- A client library flag or policy named `NoopHostnameVerifier`, `allowAllHosts`, or similar (exact API varies by library/version);
- Raw `SSLSocket` using a standard trust manager while **omitting endpoint identification** when used as an HTTPS client;
- `SSLEngine` without an endpoint identification algorithm configured or missing the exact peer host;
- "Retry fallback": after `SSLHandshakeException`, retrying with a client that has hostname checking disabled;
- Taking the hostname to check from the **peer-sent certificate** instead of the URL/trusted config;
- Writing custom DNS matching with `endsWith` or accepting arbitrary wildcards.

Never treat Subject `CN` or a `KeyStore` **alias** name as sufficient in place of **SAN**. For modern HTTPS certificates, the certificate needs the matching `dNSName SAN` or `iPAddress SAN` type per the client's chosen reference identity.

### 4.1. DNS SAN and IP SAN are not interchangeable

| Target client intends to connect to | Leaf SAN | Name check |
| --- | --- | --- |
| `https://localhost` | `DNS:localhost` | Passes if chain is trusted |
| `https://127.0.0.1` | `DNS:localhost` only | **Fails**: missing IP SAN |
| `https://127.0.0.1` | `IP:127.0.0.1` | Name passes if chain is also trusted |
| `https://api.example.test` | `DNS:api.example.test` | Name passes |
| `https://api.example.test` | `DNS:another.example.test` | **Fails** |
| `https://192.0.2.10` | `DNS:192.0.2.10` | Does not substitute for a valid `iPAddress` SAN |

DNS may resolve `api.example.test` to a specific IP address, yet **the reference name remains the URL hostname**, not reverse DNS of the IP. If the app connects via TCP to an IP while expecting a DNS identity, preserve the proper **logical peer hostname** at the TLS/HTTP layer per API.

**SNI (Server Name Indication)** only helps the server pick a certificate when serving multiple virtual hosts; SNI **does not verify the certificate returned by the server**. The client must still verify the trust chain and SAN.

### 4.2. CN fallback, wildcards, and IDN

- `CN=api.example.com` in the Subject should not be used instead of SAN. Some historical implementations had special fallbacks when SAN was absent, yet **never rely on that fallback for issuing certificates or new HTTPS tests**.
- Wildcards like `*.example.com` must not be treated as valid for unlimited subdomains or arbitrary label depths. Use the standard HTTPS client endpoint identification algorithm rather than custom simple regexes.
- Internationalized domain names require IDNA/Punycode rules and proper name-matching standards; `equalsIgnoreCase` on Unicode strings is not a complete solution.
- URI/email/workload-identity SANs have their own rules and do not automatically replace DNS SANs for HTTPS.

## 5. JSSE: who is responsible for verification?

Common Java APIs seen in code:

| API | Role | What must be kept right |
| --- | --- | --- |
| `KeyStore` | Stores identity key/cert or trusted CA certificates | Proper file/type/password/access permissions |
| `KeyManagerFactory` | Loads private key and certificate chain to **present the app's own identity** | Never use key manager instead of peer trust checking |
| `TrustManagerFactory` | Creates standard trust manager from a truststore | Import only verified CAs/peer certs; no trust-all |
| `X509TrustManager` | Interface verifying server/client chains per provider | Never replace with an accept-all implementation |
| `X509ExtendedTrustManager` | Handles certificates with `Socket`/`SSLEngine` context | Never bypass JSSE endpoint constraints |
| `SSLContext` | Aggregates key managers, trust managers, randomness/TLS session policy | Never mutate JVM-wide default or use insecure managers |
| `SSLParameters` | Configures protocols, ciphers, endpoint identification, SNI, etc. | Raw HTTPS TLS requires `setEndpointIdentificationAlgorithm("HTTPS")` |
| `SSLSocket` / `SSLEngine` | Lower-level TLS APIs | Must know logical peer name and actively enable proper endpoint checks |
| `HttpsURLConnection` | HTTPS client API | Keep default hostname verifier and legitimate trust |
| `java.net.http.HttpClient` | Modern JDK HTTP client | Keep default HTTPS verification; customize trust only within scope |

**Important:** Endpoint checks may be invoked inside the trust manager's call stack when the handshake carries hostname info, yet **security-wise they remain two separate conditions**. If calling `CertPathValidator("PKIX")` directly, recognize that API does not automatically take a URL hostname to check.

### 5.1. High-level HTTPS clients vs. raw TLS

- `HttpsURLConnection` includes default HTTPS hostname verification; installing an always-true verifier strips this protection.
- JDK 11+ `HttpClient` is also designed for HTTPS endpoint verification under secure defaults; never use properties or library options to disable it for dev certs.
- **Raw `SSLSocket`** does not inherently know which application protocol you are using it for. Using a standard trust manager **is not enough** if you omit HTTPS endpoint identity configuration.
- **`SSLEngine`** is similar; ensure peer host/port and `SSLParameters` carry the required policy before handshaking.

Example of safe raw client configuration:

~~~java
SSLSocket tls = /* created with proper peer host/connection */;
SSLParameters p = tls.getSSLParameters();
p.setEndpointIdentificationAlgorithm("HTTPS");
tls.setSSLParameters(p);
tls.startHandshake();
~~~

This is only an **API snippet**, not a standalone program. Crucially, `"HTTPS"` is set before `startHandshake()`, and **the hostname must come from the validated URL/config**, never copied from the server-sent certificate.

### 5.2. Never call `SSLContext.setDefault(...)` indiscriminately

`SSLContext.setDefault(...)` alters the default context beyond the scope of a single HTTP request/client. An unsafe change in test code can make the entire process trust bad certificates.

Prefer building a **dedicated `SSLContext` for clients needing an internal CA** and passing it to the specific builder/client. Configuring a custom truststore makes **trusted CAs differ from the default set** without automatically merging default roots. If an app needs both sets, design an explicit trust-anchor inclusion policy and test interoperability; never merge stores by writing a trust-all wrapper.

## 6. Configuring a dedicated truststore properly

To connect to a service whose certificate is issued by a **verified internal CA**:

1. Obtain the **public root CA certificate** through a trusted administrative channel. Verify its fingerprint and the CA's governing authority.
2. Create an environment/service-scoped truststore, such as PKCS12, containing **only the approved trust anchor(s)**.
3. In Java, use `KeyStore.load` and `TrustManagerFactory.init(trustStore)` to create **standard** trust managers.
4. Use `SSLContext.init(null, tmf.getTrustManagers(), new SecureRandom())` to obtain a TLS context for that **specific client**.
5. For raw HTTPS TLS, enable `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`. For high-level HTTPS clients, keep default hostname verification and never override with an unconditional verifier.
6. Test both the **valid** endpoint and the **invalid** endpoint. "Connection succeeded" is an insufficient test.

Standard truststore-loading snippet:

~~~java
KeyStore trust = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(trustStorePath)) {
    trust.load(in, password);
}
TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trust);

SSLContext clientContext = SSLContext.getInstance("TLS");
clientContext.init(null, tmf.getTrustManagers(), new SecureRandom());
~~~

This is an **illustrative fragment**, not a standalone program: `trustStorePath`/`password` must be declared and exceptions handled. The complete verified program is in section 8.

**Never hardcode production passwords.** The password protects the truststore file, while **choosing which root certificates to trust is the core security decision**: protecting the password while importing an attacker's CA into the store still destroys authenticity.

### 6.1. An identity keystore is not a truststore

~~~text
Server:
    identity keystore
       PrivateKeyEntry: private key + server cert chain

Client:
    truststore
       TrustedCertificateEntry: approved root CA certificate
       (and application trust policy)

Client checks: chain to approved trust anchor + URL hostname to leaf SAN
~~~

`KeyManagerFactory` helps the server prove possession of its private key, whereas `TrustManagerFactory` helps the client verify the peer's certificate. Moving the server private key into the client truststore to "make certificate errors go away" is wrong and can leak secrets. With mTLS, each side has its own identity and its own trust policy.

### 6.2. Internal CAs and the default truststore

The JDK typically ships a default CA set such as `cacerts` (location, contents, and policy may vary across JDKs/distributions). An `SSLContext` initialized with a custom truststore **does not automatically merge** the internal CA with all JDK roots. Never assume an API falls back to default roots after receiving custom trust managers.

Applications needing internal CAs should define their scope clearly:

- **Client used within one security domain:** a dedicated truststore restricts trusted CAs and is usually the simplest option.
- **Client needing both public and internal CAs:** use a trust policy configuration designed/reviewed per platform or library; document root sources rather than writing a trust manager that loops arbitrarily over CAs without controls.
- **Multiple microservices:** each environment/tenant has issuance and rotation policies; never trust dev CAs in production.

## 7. Hands-on: creating a local CA and certificates while keeping verification intact

This lab runs entirely on **localhost/loopback** inside a **fresh test directory**, using JDK 17+ and `keytool`. We create:

- `root.p12`: trusted demo root CA for the positive branch.
- `other-root.p12`: an unrelated **other CA**, used as a **wrong** trust anchor to prove JSSE rejects it.
- `server.p12`: server private key and leaf signed by **root.p12**, with SAN `DNS:localhost` only.
- `trusted.p12`: client truststore containing the **actual root that issued the leaf**.
- `untrusted.p12`: client truststore containing only **other-root**, so the server chain is untrusted.

**Never use demo certificates/keystores in production**; CA and server private keys in this exercise are protected by a sample fixed, guessable password, short validity, and no real CRL/OCSP infrastructure. Run every command in a **temporary empty directory**, without touching active keystore files.

### 7.1. Create a demo root CA permitted for trust in the lab

~~~bash
keytool -genkeypair -alias lab-root -keyalg RSA -keysize 2048 -dname "CN=Trusted Demo Root,O=Training,C=VN" -validity 7 -ext "bc=ca:true" -ext "ku=keyCertSign,cRLSign" -keystore root.p12 -storetype PKCS12 -storepass demo-pass-123 -keypass demo-pass-123 -noprompt
~~~

The root CA certificate is signed by the CA private key itself. Self-signed **does not mean automatically trusted**; in this lab, the **client explicitly selects this root** by importing it into `trusted.p12`.

### 7.2. Export the public root certificate

~~~bash
keytool -exportcert -alias lab-root -keystore root.p12 -storepass demo-pass-123 -rfc -file root.crt
~~~

`root.crt` contains only the **public certificate**, not the CA private key. In real systems, verify the **fingerprint and certificate distribution source** over an independent channel before importing.

### 7.3. Create another CA for the negative trust test

~~~bash
keytool -genkeypair -alias other-root -keyalg RSA -keysize 2048 -dname "CN=Unrelated Demo Root,O=Training,C=VN" -validity 7 -ext "bc=ca:true" -ext "ku=keyCertSign,cRLSign" -keystore other-root.p12 -storetype PKCS12 -storepass demo-pass-123 -keypass demo-pass-123 -noprompt
~~~

~~~bash
keytool -exportcert -alias other-root -keystore other-root.p12 -storepass demo-pass-123 -rfc -file other-root.crt
~~~

The second root being self-signed and also having `CA=true` **gives it no authority to trust the server certificate** issued by the first root. The `untrusted.p12` truststore holding only this other root provides a reproducible negative test.

### 7.4. Create the server identity with SAN DNS localhost

~~~bash
keytool -genkeypair -alias server-id -keyalg RSA -keysize 2048 -dname "CN=localhost,O=Training,C=VN" -validity 7 -ext "san=dns:localhost" -keystore server.p12 -storetype PKCS12 -storepass demo-pass-123 -keypass demo-pass-123 -noprompt
~~~

When first created, `server.p12` holds a `PrivateKeyEntry` and a temporary self-signed certificate. That is not yet the demo-CA-signed leaf. The alias `server-id` is preserved in the next steps.

### 7.5. Create a PKCS#10 CSR and have the trusted CA sign the certificate

~~~bash
keytool -certreq -alias server-id -file server.csr -rfc -keystore server.p12 -storepass demo-pass-123 -ext "san=dns:localhost"
~~~

~~~bash
keytool -gencert -alias lab-root -infile server.csr -outfile issued.crt -rfc -keystore root.p12 -storepass demo-pass-123 -validity 7 -ext "san=dns:localhost" -ext "ku=digitalSignature,keyEncipherment" -ext "eku=serverAuth"
~~~

The demo CA signs a leaf with `SAN DNS:localhost` and `EKU serverAuth`. A real CA must verify authorization over the identity, certificate, and issuance policy before signing, never blindly trusting every SAN requested in a CSR.

### 7.6. Install the root and certificate reply into the right server alias

~~~bash
keytool -importcert -alias lab-root -file root.crt -keystore server.p12 -storepass demo-pass-123 -noprompt
~~~

~~~bash
keytool -importcert -alias server-id -file issued.crt -keystore server.p12 -storepass demo-pass-123 -noprompt
~~~

The second step installs the **certificate reply into the exact `PrivateKeyEntry` alias `server-id`** so the leaf's public key matches the held private key. Do not import the leaf under a new alias and assume the server identity was updated properly.

### 7.7. Create two client truststores with explicit policies

~~~bash
keytool -importcert -alias lab-root -file root.crt -keystore trusted.p12 -storetype PKCS12 -storepass demo-pass-123 -noprompt
~~~

~~~bash
keytool -importcert -alias other-root -file other-root.crt -keystore untrusted.p12 -storetype PKCS12 -storepass demo-pass-123 -noprompt
~~~

- `trusted.p12` trusts only the root that signed the leaf → connecting to `localhost` can pass.
- `untrusted.p12` trusts only the other root → the server certificate has no path to that root → **JSSE must reject**.
- `server.p12` contains the server private key and certificate chain; it **contains neither root's private key**.

**Warning:** `-storepass` on the command line can leak via process listings/history; use only in an isolated demo environment. `-noprompt` skips `keytool` confirmation; never use it to auto-import CAs from unverified sources in production.

### 7.8. Inspect certificates/aliases

~~~bash
keytool -list -v -alias server-id -keystore server.p12 -storetype PKCS12 -storepass demo-pass-123
keytool -list -v -alias lab-root -keystore trusted.p12 -storetype PKCS12 -storepass demo-pass-123
keytool -list -v -alias other-root -keystore untrusted.p12 -storetype PKCS12 -storepass demo-pass-123
~~~

What to verify: the leaf actually has `DNSName: localhost` and chains to `lab-root`, while `untrusted.p12` contains the **other root**. The root in `trusted.p12` is a `TrustedCertificateEntry`, not a CA private key.

## 8. Complete Java 17+: right CA/name passes, wrong CA/name fails

This is a **runnable** program that can be compiled/run on JDK 17+ in the same directory as `server.p12`, `trusted.p12`, and `untrusted.p12` from section 7.

The program contains zero lines of trust-all or disabled hostname-verifier code:

1. Creates a local TLS server using `KeyManagerFactory` from `PrivateKeyEntry` in `server.p12`.
2. Creates two clients using **standard `TrustManagerFactory`**: one with the right root and one with only the unrelated root.
3. Opens TCP loopback via `InetAddress.getLoopbackAddress()` while assigning a **logical `peerName`** to `SSLSocket`.
4. Always enables **`SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`** before handshaking.
5. Proves all three expected outcomes: **trusted + localhost** succeeds; **unrelated CA + localhost** is rejected; **trusted + 127.0.0.1** is rejected due to missing IP SAN.

### 8.1. Source `SafeJsseDemo.java`

~~~java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLHandshakeException;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

public class SafeJsseDemo {
    static KeyStore load(String file, char[] password) throws Exception {
        KeyStore ks = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(Path.of(file))) {
            ks.load(in, password);
        }
        return ks;
    }

    static SSLContext serverContext(KeyStore identity, char[] password)
            throws Exception {
        KeyManagerFactory km = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        km.init(identity, password);
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(km.getKeyManagers(), null, new SecureRandom());
        return context;
    }

    static SSLContext clientContext(KeyStore trust) throws Exception {
        TrustManagerFactory tm = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tm.init(trust);
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, tm.getTrustManagers(), new SecureRandom());
        return context;
    }

    static void handshake(SSLContext context, int port, String peerName)
            throws Exception {
        // TCP always connects to loopback. peerName is the trusted logical identity
        // that TLS must check against the leaf's Subject Alternative Name.
        Socket tcp = new Socket(InetAddress.getLoopbackAddress(), port);
        try (SSLSocket tls = (SSLSocket) context.getSocketFactory()
                .createSocket(tcp, peerName, port, true)) {
            SSLParameters params = tls.getSSLParameters();
            params.setEndpointIdentificationAlgorithm("HTTPS");
            tls.setSSLParameters(params);
            tls.startHandshake();
        }
    }

    static boolean rejected(SSLContext context, int port, String name)
            throws Exception {
        try {
            handshake(context, port, name);
            return false; // ERROR: bad connection was not rejected.
        } catch (SSLHandshakeException expected) {
            return true; // PASS: JSSE rejected right at handshake.
        }
    }

    public static void main(String[] args) throws Exception {
        char[] password = "demo-pass-123".toCharArray();
        try {
            SSLContext server = serverContext(
                    load("server.p12", password), password);
            SSLContext trusted = clientContext(
                    load("trusted.p12", password));
            SSLContext untrusted = clientContext(
                    load("untrusted.p12", password));

            try (SSLServerSocket listener = (SSLServerSocket)
                    server.getServerSocketFactory().createServerSocket(
                            0, 10, InetAddress.getLoopbackAddress())) {

                Thread responder = new Thread(() -> {
                    for (int i = 0; i < 3; i++) {
                        try (SSLSocket accepted =
                                (SSLSocket) listener.accept()) {
                            accepted.startHandshake();
                        } catch (Exception ignored) {
                            // Demo only: negative tests can cause client
                            // to abort handshake; server continues testing.
                        }
                    }
                });
                responder.start();
                int port = listener.getLocalPort();

                handshake(trusted, port, "localhost");
                System.out.println("Trusted + localhost = accepted");

                System.out.println("Wrong CA rejected   = " +
                        rejected(untrusted, port, "localhost"));

                System.out.println("Wrong name rejected = " +
                        rejected(trusted, port, "127.0.0.1"));

                responder.join(10000);
                if (responder.isAlive()) {
                    throw new IllegalStateException("Server not finished");
                }
            }
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
~~~

Compile and run:

~~~bash
javac SafeJsseDemo.java
java SafeJsseDemo
~~~

**Stdout verified with JDK, `keytool`, `javac`, and `java` in a temporary directory** after running section 7 commands:

~~~text
Trusted + localhost = accepted
Wrong CA rejected   = true
Wrong name rejected = true
~~~

Even though key pairs and signatures are randomly generated each run, these three outcomes remain stable for the demo certificate/KeyStore set and policy. A Java environment or JCE provider with special algorithm policies might reject even the positive case; if so, inspect the real error rather than **downgrading verification to "make output match."**

### 8.2. Accurate analysis of the stdout lines

**`Trusted + localhost = accepted`**:

- Server presents the leaf certificate signed by root `lab-root`.
- Client uses `trusted.p12` containing that exact root, with the standard trust manager.
- `peerName="localhost"` matches `dNSName SAN localhost` on the leaf.
- `SSLSocket.startHandshake()` succeeds. Here no HTTP request or application authorization is performed yet; only the TLS layer is tested.

**`Wrong CA rejected = true`**:

- The target name is still `localhost`, still matching the SAN.
- However, the client uses `untrusted.p12` containing only a root **unrelated** to the leaf's issuer.
- There is no valid path to a client-accepted trust anchor; JSSE throws `SSLHandshakeException`.
- The program treats **rejection** as a **passing** test outcome. It does not retry with trust-all.

**`Wrong name rejected = true`**:

- The client still uses `trusted.p12`, so the chain is trusted.
- Logical peer identity changes to IP literal `127.0.0.1`.
- The leaf has only `DNS:localhost`, lacking `iPAddress SAN:127.0.0.1`.
- `HTTPS` endpoint identification causes JSSE to reject even when the CA chain is valid. This is a separate defense layer that **must not be omitted**.

### 8.3. Why doesn't the example print exception details?

To keep tests simple and independent of provider-specific message text, `rejected` catches `SSLHandshakeException` and returns a boolean. Specific messages/exception chains can vary across JDKs, CA profiles, and algorithms; **never assert exact exception message strings**.

In production, preserve stacks/causes with sensitive details filtered and log appropriately for operations. Never catch all exceptions and "return success"; tests must fail if unexpected errors occur. The demo server thread intentionally ignores handshake errors during **negative tests** and prints no sensitive data; **never use such exception-swallowing in production servers**.

### 8.4. Why not write trust-all code for comparison?

To prove a system is right, **you do not need to build an insecure setup** and show it accepting a fake CA. Instead, negative tests require Java to **reject** a different root and wrong hostname; tests will fail if anyone accidentally swaps the trust manager or turns off HTTPS endpoint identification.

This is stronger testing than a "demo that works with every server," because it verifies the **security-critical rejection behavior**.

## 9. What should you do with `HttpClient` or `HttpsURLConnection`?

### 9.1. `java.net.http.HttpClient`

On JDK 11+ (including JDK 17), when an internal CA is needed, create an `SSLContext` holding a standard trust manager as in section 6 and pass it to **`HttpClient.Builder`**:

~~~java
HttpClient client = HttpClient.newBuilder()
        .sslContext(clientContext)
        .build();
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.test/status"))
        .GET()
        .build();
HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());
~~~

**This is an API fragment**, not a standalone program: `clientContext` must be securely initialized, and real imports/exceptions/URLs provided. Default HTTPS endpoint identification must remain intact; never enable switches that disable hostname verification.

**Right fix:** if the API at `https://api.example.test` uses an internal CA, place the verified CA in the truststore; the leaf certificate must carry a SAN for `api.example.test`. If calling `https://10.0.0.20`, supply an appropriate IP SAN or fix the URL/logical name per policy. Never use "insecure mode" requests just because you are in staging.

### 9.2. `HttpsURLConnection`

`HttpsURLConnection` uses default hostname verification for HTTPS. You can supply an `SSLSocketFactory` created from an `SSLContext` trusting the right CA:

~~~java
HttpsURLConnection connection = (HttpsURLConnection)
        new URL("https://api.example.test/status").openConnection();
connection.setSSLSocketFactory(clientContext.getSocketFactory());
// Keep default HostnameVerifier; NEVER override to always-true.
int status = connection.getResponseCode();
~~~

This is a **snippet** requiring imports, a secure `clientContext`, I/O checks, and connection lifecycle handling in a real program. The right approach is **replacing the trust anchor source under control**, not skipping hostname verification.

### 9.3. OkHttp, Apache HttpClient, Netty, Spring, and other libraries

Libraries vary in flag/API names across versions. Invariant rules:

- The trust manager genuinely checks the chain against the chosen CA source, with no `acceptAll`/trust-all.
- Default hostname verification or an equivalent validation policy remains active.
- Never create a "once for the whole system" SSLContext replacing all clients with an unsafe trust manager.
- Any `NoopHostnameVerifier`, `TrustAllStrategy`, `InsecureTrustManagerFactory`, or similar concept must be **flagged in code review**, especially in apps with real data.
- Test on the exact **client library version and JDK** being deployed; a configuration proven safe in one API is not guaranteed to copy verbatim to another.

## 10. Debugging TLS without downgrading security

An exception can arise from multiple layers. Investigate the real cause rather than applying a "universal fix" of dropping trust/hostname checks.

| Symptom | Root-cause group | Remediation |
| --- | --- | --- |
| `PKIX path building failed` | Client cannot build a path to a trust anchor | Verify CA/truststore, intermediate chain, and actual runtime in use |
| `unable to find valid certification path` | No policy-accepted trust anchor/path | Select the vetted root; never import certificates arbitrarily |
| `No subject alternative DNS name matching ...` | Leaf SAN lacks the expected DNS host | Have CA reissue with right SAN, or use the identity-matched URL |
| `No subject alternative names matching IP address ...` | URL uses IP while leaf lacks IP SAN | Use matching IP SAN or a certified DNS URL |
| `certificate expired` / `not yet valid` | Leaf/issuer validity window or clock skew | Renew certificate, check time; never disable validity checks |
| `Extended key usage does not permit use for TLS server authentication` | Leaf lacks proper `serverAuth` purpose | Request certificate with right EKU |
| `Algorithm constraints check failed` | Key/signature fails policy | Upgrade key/CA profile/cipher suites accordingly |
| `Certificate revoked` | Certificate revoked per policy | Investigate key/CA incident, rotate, and handle properly; never skip revocation |
| Failure after switching Docker/JDK | Different store/type/CA bundle/provider | Inspect exact truststore file, permissions, JDK distribution, and process config |
| "Works after allow-all-hosts" | Name checking was disabled | **Roll back the bypass** and issue a certificate with right SAN |
| "Works after trust-all manager" | Chain trust was disabled | **Roll back the bypass** and configure a trusted CA |
| Intermittent errors after redirect/proxy | Actual endpoint host differs or proxy terminates TLS | Check each hop's URL, trust anchors, and certificate SAN at TLS termination |

### 10.1. Structured investigation workflow

~~~text
1. Identify the exact URL/hostname or IP the client intends to call.
2. Identify the HTTPS client API, SSLContext, and truststore in use.
3. Check leaf SAN, issuer, validity, KU/EKU, and chain/intermediates.
4. Check the root CA from a trusted source; cross-check the runtime's truststore.
5. Test chain trust independently; test hostname matching independently.
6. Fix certificate/URL/truststore at the real root cause.
7. Re-run positive + negative tests.
8. Never retry with trust-all or skip-hostname.
~~~

Use `keytool -list -v` or organization-approved tools to inspect truststore contents. When using `openssl s_client`, remember that **merely printing certificates/`Verify return code` does not guarantee hostname verification ran**; pass appropriate options/trust if checking identity. Never extrapolate from one path-valid check that an entire HTTPS client is secure.

### 10.2. JSSE debug logs can contain sensitive data

The JDK offers several TLS debug modes, such as:

~~~bash
java -Djavax.net.debug=ssl,handshake,trustmanager YourApplication
~~~

This is a **conceptual command**, not a command to run `SafeJsseDemo`, since the class name represents an arbitrary app. Use in controlled environments and review log contents before sharing: TLS traces can expose system metadata, hostnames, certificate details, and info unsuitable for public disclosure. **Never leave verbose debugging on indefinitely in production**, and never put passwords, private keys, tokens, or full auth bodies into logs.

**Never "debug" by disabling verification to "keep observing the request."** When you need to reproduce a service error, create a proper test CA/certificate or test endpoints in an isolated lab like sections 7–8.

## 11. Do not trust an unknown CA just because importing succeeded

A mistake close to trust-all is **importing every CA/certificate sent by a server** into the client's truststore. Even without installing a trust-all manager, this turns the trust anchor set into an unverified list.

**Risk example:**

~~~text
Client reports: issuer untrusted
Operator downloads root.crt from that exact unverified connection
Operator imports root.crt with -noprompt
Client connects successfully
=> No proof this root belongs to the expected CA.
~~~

An attacker can serve a fake root and a leaf signed by themselves. **Signatures verify cleanly against the newly imported fake root**, yet the initial decision to trust that root was compromised.

The right approach:

1. Verify the CA fingerprint/public key through an independent administrative channel.
2. Verify CA ownership, certificate issuance scope, constraints, expiration, and CA governance policy.
3. Import **only the approved certificate** into the environment-specific truststore.
4. Check file permissions, backups, reviews, and rotation; never use a global truststore if only one client needs that CA.
5. Keep hostname verification enabled and test end-to-end.
6. Audit trust anchor changes; never auto-update truststores from peer-sent network certificates.

**Proper certificate pinning** (if needed) also relies on values distributed **from a trusted source**, not fingerprints grabbed automatically from an unauthenticated connection and treated as permanently safe.

## 12. Security model across dev/staging/production

### 12.1. Dev localhost

If testing `https://localhost`, generate a dev cert with SAN `DNS:localhost` and trust the dev CA **only in the dev truststore**. If testing `https://127.0.0.1`, issue SAN `IP:127.0.0.1` or use DNS `localhost` consistently.

Never ask developers to disable all HTTPS validation just because a local server has a self-signed certificate. A dev CA may be self-signed, yet it must be **explicitly trusted within a bounded scope**—unlike trusting every certificate on the network.

### 12.2. Staging and integration testing environments

Staging should have a stable hostname like `staging-api.example.test`, proper certificate SAN, and a dedicated staging CA/truststore or public CA per design. CI negative tests must confirm:

- Different roots are rejected.
- Mismatched certificate SANs are rejected.
- Expired/non-compliant certificates are rejected.
- After redirects/proxies, the new endpoint is still verified.
- No verification-bypass configuration flags exist in deployable artifacts.

### 12.3. Production and load balancers

When an ingress/LB terminates TLS, the certificate at the TLS termination point must match the URL hostname seen by clients. If the LB opens a separate TLS connection to the backend, the LB→backend hop **also has its own identity/trust policy**; never "inherit" client→LB authentication without designing it.

In microservices, service A calling service B over internal DNS may need an enterprise CA, matching SAN identities, scoped truststores, and mTLS. **mTLS does not replace client hostname verification**, and a client certificate signed by an enterprise CA **does not automatically authorize** calling every endpoint: identity-to-role authorization must be checked separately.

### 12.4. Corporate proxies and TLS inspection

A proxy may present certificates issued by a **proxy CA** instead of the origin server's certificate. If an organization has a legitimate TLS inspection policy, the client must manage that CA via dedicated procedures while still checking target URL hostnames, scope, logging, and operational risks.

Never auto-import a proxy CA delivered by an untrusted connection. Adding a proxy CA widens trust anchors and can allow the proxy to terminate many connections; that is a **security governance decision**, not a one-line code workaround.

## 13. Preventing bugs in code review and testing

### 13.1. Red flags to look for in pull requests

| Signal | Review question |
| --- | --- |
| Custom `X509TrustManager` | Does it genuinely check chains, algorithms, and trust anchors? Why not use the standard provider? |
| `checkServerTrusted` has no verification logic | Is this a trust-all hidden behind try/catch? |
| `HostnameVerifier` always returns true | Is it stripping all endpoint identity checks? |
| `NoopHostnameVerifier` or `allowAllHosts` | Are there negative mismatch tests to catch bypasses? |
| `SSLContext.setDefault` | Could this inadvertently alter TLS policy process-wide? |
| Raw `SSLSocket`/`SSLEngine` | Are endpoint identification enabled and the right peer name passed? |
| `SSLParameters.setEndpointIdentificationAlgorithm("")` or omitted | Does this drop name checking in an HTTPS context? |
| `disableHostnameVerification` config | Could this reach production builds/runtimes? |
| Auto-importing certs into truststore on error | Where did the CA come from and who verified the fingerprint? |
| Retrying after `SSLHandshakeException` | Does the retry relax trust/hostname checks? |
| HTTPS test asserting only HTTP 200 | Are there negative tests for wrong CA and wrong hostname? |
| Shared SSL factory wrapper across clients | Does it grant broader trust scope than intended? |

**Good reviews go beyond grepping keywords.** Libraries may use different names or YAML/properties configuration instead of Java code. Inspect **effective TLS settings**, dependency versions, container images, and smoke tests.

### 13.2. Mandatory test matrix

| Test | Chain trust | Hostname | Expected outcome |
| --- | --- | --- | --- |
| Positive | Right CA | SAN matches | **Accept** |
| Wrong root | Different CA | SAN matches | **Reject** |
| Wrong DNS | Right CA | SAN mismatches | **Reject** |
| Wrong IP | Right CA | Missing `iPAddress` SAN | **Reject** |
| Invalid date | Right CA | SAN matches | **Reject** |
| Missing intermediate | Path cannot build | SAN matches | **Reject** if valid chain cannot be built |
| Wrong EKU | Chain/usage policy fails | SAN matches | **Reject** |
| Tampered certificate | Invalid signature | SAN matches | **Reject** |
| Revoked certificate | Revocation policy rejects | SAN matches | **Reject** |
| Wrong client identity (mTLS) | Client cert may be valid | Unauthorized | **Deny** at the appropriate layer |

The two negative tests **Wrong root** and **Wrong DNS** are the most valuable for this topic because they directly catch a developer accidentally enabling trust-all or dropping name checks.

### 13.3. Never make tests "pass" by accepting errors

A dev machine lacking the right CA is an **incomplete test setup**, not a reason to alter the verifier:

- Never disable certificate verification just to get an HTTP status.
- Never catch `SSLHandshakeException` and simulate success.
- Never use a global insecure client in test fixtures if that fixture is reused in production.
- Never auto-import root certificates returned by a server without verifying the source.
- When tests need a self-signed CA, **create and pin the trust anchor in a dedicated test fixture**, issue leaves with valid SANs, and keep verification enabled.

**At least one test is supposed to fail as expected.** If connecting with an untrusted CA or wrong hostname succeeds, the system **has an authentication vulnerability**, not "flexible tests."

## 14. Commonly confused certificate trust vs. hostname errors

### 14.1. `PKIX path building failed`

This is typically a path-validation error, not a hostname error. Resolution: check the server-sent certificate chain, intermediates, the root the client actually trusts, JDK policy, validity, and algorithms. Importing the right CA fixes a trust issue; **never touch the hostname verifier**.

### 14.2. `No subject alternative DNS name matching ...`

The trust chain may already be valid, yet the SAN lacks the reference hostname. Fix: the certificate must have the right DNS SAN (CA reissues), or the app must use the hostname actually issued per design. **Never swap the trust manager to handle mismatches** and never turn off hostname verification.

### 14.3. Using IP instead of DNS during testing

The server certificate was issued for `DNS:api.example.test`, yet the developer tests `https://10.10.0.20`. That is a different reference identity. Use the matching DNS endpoint and route DNS to the IP, or obtain an IP SAN if policy permits IP-based identification.

### 14.4. Root imported into the wrong Java runtime

Machines often have multiple JDKs/containers. You imported the CA into JDK A's `cacerts`, while the app runs on JDK B or uses its own custom truststore. Check **actual paths, types, user permissions, and effective config**. Never build trust-all because you couldn't find the right truststore.

### 14.5. Server returning different certificates by SNI

If SNI does not match or a reverse proxy picks a default certificate, the chain may be valid yet the SAN belongs to a different hostname. Fix SNI routing/server certificate config, ensure the client sends the right hostname, and **keep name checking on**. Never drop SAN checks just because the CA signed it.

### 14.6. Only one HTTP library fails

`HttpClient`, `HttpsURLConnection`, OkHttp, Netty, or Apache HttpClient may use different SSLContexts/truststores/hostname policies. Investigate the **specific client and version**, never applying a JVM-wide "insecure SSL" flag or disabling name checks across all clients.

### 14.7. Expired or revoked certificates

A certificate with the right SAN and trusted CA can expire or be revoked. Never use trust-all or spoof clocks to bypass. Renew/rotate keys/certs, handle CA incidents, verify clock sync, and enforce revocation policies.

## 15. Passwords/keys, logging, and secure governance

PKCS12 passwords protect the file per provider; they **do not replace CA validation and hostname verification**. Leaf/root certificates may be public, while private keys, trust policies, and credential copies must be protected.

- **Never commit** `.p12` files containing private keys, key passes, secret manager tokens, `javax.net.ssl.keyStorePassword`, or truststore passwords into repositories.
- Manage keystores/truststores with secret managers, deployment policies, volume permissions, or HSM/KMS as required.
- Root/CA certificates from official sources must be treated as a **security policy list**, reviewed/audited/rotated; never import uncontrollably.
- Avoid mutating the JVM-wide default `SSLContext`; prefer per-client configuration.
- On TLS errors, log at an appropriate level: target hostname, error category, policy-filtered cert issuer/SAN/expiry; **never log private keys, passwords, session keys, bearer tokens**, or full requests containing credentials.
- Never disable revocation out of habit: CRL/OCSP mechanisms and hard/soft-fail policies depend on the application and must be explicitly decided.
- For mTLS servers/clients, monitor certificate expiry, rotation, cert usage, and identity-to-permission mappings; both directions retain separate trust policies.

The demo code wipes the application-held `char[] password` after use. This reduces the lifetime of application-controlled copies without proving the JVM/provider wiped every copy; **literal** passwords in examples are intentionally simplified and **never for production**.

## 16. Self-check exercises (with answers)

**Q1.** An HTTPS app connects successfully after replacing the trust manager with an implementation accepting every certificate. What was lost?

**Answer:** **Certificate path/issuer authentication** was lost. An attacker can use a self-signed certificate or one they control as the peer, while the session still appears encrypted.

**Q2.** A Java client trusts the corporate CA, calls `payments.internal`, and the peer presents a `DNS:reports.internal` certificate. Should it be accepted?

**Answer:** **No.** A valid chain does not replace hostname matching. The client needs a cert with SAN `payments.internal` or must fix the target endpoint; never disable name checking.

**Q3.** A certificate has SAN `DNS:localhost` and the client uses URL `https://127.0.0.1`. What is missing?

**Answer:** An **`iPAddress` SAN for `127.0.0.1`** is missing. Having a DNS SAN `localhost` does not make an IP-based URL the same reference identity.

**Q4.** Should you install a `HostnameVerifier` that always returns true since TLS still checks the CA?

**Answer:** No. A valid certificate for a different hostname could be accepted for the target endpoint; that is an endpoint authentication failure separate from path trust.

**Q5.** A raw `SSLSocket` uses a standard `TrustManagerFactory`. Does that automatically guarantee HTTPS hostnames are checked?

**Answer:** **Not necessarily.** Raw TLS does not assume an application protocol by default; you need the right peer name and `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` configured before handshaking when enforcing HTTPS identity.

**Q6.** Why is a test asserting only HTTP 200 from an HTTPS server insufficient for security QA?

**Answer:** A trust-all or hostname-skipping client can still receive HTTP 200. You need **negative tests** with untrusted CAs and mismatched hostnames verifying the client rejects them.

**Q7.** Can you import a root certificate grabbed from the very connection failing TLS to "fix PKIX"?

**Answer:** Never arbitrarily. That root could belong to an attacker; trust anchors must be selected and verified for fingerprint/source via a trusted channel before importing.

**Q8.** SNI is `api.example.test`, yet the server returns a leaf with `DNS:other.example.test`. Is that safe enough?

**Answer:** No. SNI only helps the server select a certificate; the client must still check that the leaf SAN matches the reference hostname.

**Q9.** The test with the other CA fails with `SSLHandshakeException`. Is that a bug in `SafeJsseDemo`?

**Answer:** No. That is an **expected failure** and is reported as `Wrong CA rejected = true`. Rejecting the wrong trust anchor is the right behavior.

**Q10.** In the demo, right CA + `localhost` passes, while right CA + `127.0.0.1` fails. Why?

**Answer:** Because the **endpoint identities differ**. The leaf has only `DNS:localhost` SAN. CA validation passes in both, yet the IP literal lacks a matching `iPAddress` SAN so the handshake is rejected.

**Q11.** If `PKIX path building failed` appears after moving to a container, should you enable skip-verify?

**Answer:** No. Verify the truststore actually used by the JDK/container, CA/intermediates, file permissions, and algorithm policy; fix the CA chain/config at the real cause.

**Q12.** A client needs both public CAs and an internal CA. Does using a custom truststore automatically retain the JDK's default roots?

**Answer:** Not by default. `TrustManagerFactory.init(customStore)` uses the supplied store per provider/policy; design explicitly how to manage the trusted CA set. Never fall back to trust-all.

**Q13.** An mTLS server trusts the client's CA; does every client certificate signed by that CA get to call all APIs?

**Answer:** No. Trusting the certificate chain verifies the identity source per policy; the app must still perform **authorization** mapping identity to role/tenant and check certificate purposes like `clientAuth` where appropriate.

**Q14.** Can CA and hostname errors be fixed by lowering the TLS version/cipher suite so the handshake succeeds?

**Answer:** No. Version/cipher suite is a different layer; weakening algorithms does not replace chain trust or SANs. Fix certificates/truststores/endpoints per policy.

**Q15.** If a team wants to include a TLS example in public documentation, how should it illustrate it so learners don't copy dangerous shortcuts?

**Answer:** Use an **explicitly trusted test CA, proper SAN hostname, standard trust manager, and enabled endpoint identification**, plus negative tests. Describe trust-all/skip-hostname strictly as anti-patterns without providing copyable insecure helpers.

## 17. Checklist before merging/deploying JSSE code

- [ ] **No** check-skipping trust managers, trust-all SSLContexts, or "always accept" certificate verifiers.
- [ ] **No** `HostnameVerifier` always returning true, `NoopHostnameVerifier`, or disabled endpoint identification for HTTPS.
- [ ] No insecure retries after `SSLHandshakeException`; TLS errors must fail closed.
- [ ] Trusted CA certificates are selected from **verified sources**, with truststore scope matching the environment/client.
- [ ] Server certificates have the **right-type DNS/IP SAN** matching the actual hostname from URL/config; never use Subject CN/alias instead of SAN.
- [ ] High-level clients preserve default hostname verification; raw `SSLSocket`/`SSLEngine` enable `"HTTPS"` endpoint identification when required by protocol.
- [ ] Never mutate JVM-wide `SSLContext.setDefault` with careless trust configs.
- [ ] Full chains/intermediates are handled, and certificate validity, KU/EKU, algorithm constraints, and revocation policies are properly enforced.
- [ ] Includes test: **right CA + right hostname ⇒ accept**.
- [ ] Includes test: **wrong CA + right hostname ⇒ reject**.
- [ ] Includes test: **right CA + wrong hostname/IP ⇒ reject**.
- [ ] Dev/staging/production maintain separate CAs, truststores, and SANs/endpoints per policy; never use broad dev roots in production.
- [ ] HTTPS through proxies/LBs, redirects, and mTLS still verifies the exact logical peer identity.
- [ ] Never hardcode production passwords/keystores or log private keys/session keys/API tokens; maintain auditing and certificate rotation.
- [ ] CI or code reviews catch insecure configurations across Java source, YAML/properties, system properties, and active HTTP libraries.

## 18. Conclusion

**Never turn a TLS error into an excuse to drop authentication.** An HTTPS/JSSE client must prove **two things**: a valid certificate chain to **explicitly trusted** trust anchors, and a leaf certificate describing the **exact hostname/IP to connect to**. Trust-all drops CA authentication; skipping hostname drops endpoint identity binding. Both allow a man-in-the-middle to impersonate the peer even while traffic remains encrypted.

The Java 17+ example in this lesson avoids those shortcuts: it configures a standard trust manager, enables `HTTPS` endpoint identification, and **enforces rejection of wrong CAs and wrong hostnames** alongside passing valid cases. When facing real-world errors, fix the certificate source, CA, SAN, URL, or client configuration **at the root cause**—never lower verification just to get a "successful" connection.

**References:** [Java 17 JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html), [RFC 5280 — PKIX Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280), [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525), [Java 17 keytool documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html).