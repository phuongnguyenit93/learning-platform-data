# TLS, cipher suites, and connectivity with legacy systems

When moving an application to a new Java version, there are cases where code still compiles, dependencies still resolve, and TCP connections still succeed, yet HTTPS requests, JDBC over TLS, or connections to a partner system unexpectedly fail. Errors typically occur during the TLS handshake: the two ends fail to agree on a protocol version or cipher suite, the certificate no longer meets security policy, the signature algorithm is restricted, or the hostname on the certificate does not match the actual endpoint.

In particular, a legacy system may only support TLS 1.0/1.1, cipher suites using weak algorithms, certificate chains based on an old CA, or firmware that does not understand extensions sent by modern TLS clients. When Java raises its default security level, connections that previously “still worked” may be rejected. This is expected behavior of security policy evolution and should not be handled by disabling certificate validation or re-enabling all weak algorithms.

This lesson belongs to the **Java Advance Compatibility Migration** topic, chapter **Security and access**. The focus is how TLS works in the Java ecosystem, how to assess compatibility with legacy systems, accurately identify the root cause of handshake failures, design low-risk migration approaches, and test connectivity on the target JDK.

## 1. Distinguishing compatibility layers during a TLS connection

A successful connection must pass through multiple layers of conditions:

~~~text
Java application
      |
      v
DNS / hostname / proxy
      |
      v
TCP connection to endpoint
      |
      v
TLS ClientHello
      |
      +--> Protocol version
      +--> Cipher suites
      +--> Supported groups / key exchange
      +--> Signature algorithms
      +--> SNI / ALPN / extensions
      |
      v
ServerHello and parameter selection
      |
      v
Certificate / authentication / key exchange
      |
      v
Trust chain + hostname verification
      |
      v
TLS connection established
      |
      v
HTTP / database protocol / application data
~~~

Not all steps share the same order between TLS 1.2 and TLS 1.3; the diagram only describes the groups of conditions that must be satisfied.

An error at the network layer such as Connection refused or DNS timeout should not automatically be classified as a TLS error. Conversely, succeeding with telnet or a TCP port check does not prove TLS negotiation will succeed.

Dimensions to verify:

| Compatibility dimension | Question |
|---|---|
| Protocol version | Do client and server share an allowed TLS version? |
| Cipher suite | Is there an algorithm suite supported by both sides and permitted by policy? |
| Key exchange / group | Do both sides have compatible key groups and cryptographic parameters? |
| Signature algorithms | Are the certificate/handshake signature algorithms accepted? |
| Certificate chain | Does the client trust the server's CA chain? |
| Hostname identity | Does the certificate's SAN match the connected hostname? |
| Client certificate / mTLS | Does the server require and trust a client certificate? |
| TLS extensions | Do SNI, ALPN, or other extensions interact properly? |
| Security provider | Do the JSSE provider, crypto policy, and FIPS mode satisfy requirements? |
| Application protocol | After TLS, do HTTP, JDBC, or the application protocol work? |

**A successful TLS handshake does not prove the business application is fully compatible.** Afterward, errors in HTTP/2, authentication, serialization, or database protocols can still occur.

## 2. What is TLS and why does upgrading Java change connections?

Transport Layer Security (TLS) protects data in transit by authenticating peers, agreeing on session keys, and encrypting/integrity-checking application data.

In Java, many applications use TLS through the Java Secure Socket Extension (JSSE), including:

- javax.net.ssl.SSLContext;
- javax.net.ssl.SSLSocket and SSLServerSocket;
- javax.net.ssl.SSLEngine;
- javax.net.ssl.KeyManager and TrustManager;
- HttpsURLConnection;
- Java HttpClient;
- Libraries such as Apache HttpClient, Netty, gRPC, JDBC drivers, or frameworks using their own provider or combining with JSSE.

One dependency may use default JSSE; another dependency may configure its own SSLContext or use a native TLS engine like OpenSSL via an adapter. Therefore, when evaluating migration, you must identify **the library actually performing the TLS handshake**, not just the JDK version.

### 2.1. Java upgrades security policies, not just APIs

Common changes when upgrading the JDK or applying security patches:

- Enabling TLS 1.3 in supported environments.
- Restricting or disabling TLS 1.0/1.1 by default.
- Removing insecure cipher suites from default lists.
- Blocking weak algorithms, key lengths, or signatures.
- Updating the CA list in the default truststore.
- Changing certificate rules and hostname verification.
- Adjusting extensions, signature schemes, and TLS handshake handling.

Some changes are introduced in **security updates of the same JDK line**, not only in major upgrades. Therefore, you should not conclude an environment is compatible based on a label like “Java 8” or “Java 11” without knowing the update level, vendor, provider, and configuration.

## 3. TLS versions and suitability

| Protocol | Modern assessment | Approach when encountering legacy systems |
|---|---|---|
| SSLv2, SSLv3 | Obsolete, unsuitable for use | Do not re-enable; replace endpoint/gateway |
| TLS 1.0 | Obsolete, usually disabled | Prioritize upgrading server; only consider isolated exception if policy permits |
| TLS 1.1 | Obsolete, usually disabled | Similar to TLS 1.0 |
| TLS 1.2 | Widely deployed protocol, can be secure when well configured | Practical baseline for many compatible systems |
| TLS 1.3 | Modern version, redesigned handshake/cipher suites | Prefer when both sides support it and it is tested |

JDK 11 brought TLS 1.3 into SunJSSE as official support. Some JDK 8 builds or distributions with backports may support TLS 1.3; thus, do not infer solely from major version. Inspect the actual supported/enabled protocols.

On many modern JDKs, default configuration typically prefers TLS 1.3 and TLS 1.2, yet the specific set of protocols can be altered by providers, security properties, command-line flags, and client library APIs.

### 3.1. Supported differs from enabled

JSSE distinguishes:

- **Supported protocols:** protocols the implementation is capable of supporting.
- **Enabled protocols:** protocols enabled so a specific socket/engine can negotiate them.
- **Permitted by security policy:** protocols not blocked by constraints such as jdk.tls.disabledAlgorithms.

A protocol appearing in getSupportedProtocols() does not guarantee it can connect, because it may be disabled at the security policy layer or have other restrictions.

### 3.2. Why are TLS 1.0/1.1 a problem?

TLS 1.0 and 1.1 do not meet modern security expectations. Newer clients may refuse to negotiate when a server only supports these protocols. Re-enabling old protocols can create attack surface and violate compliance policies.

For partner-owned external endpoints, the best handling is requesting the partner to support TLS 1.2 or above with valid cipher suites and certificates. If immediate upgrade is not yet possible, a risk-assessed transitional solution with network segmentation and a clear retirement deadline is needed.

## 4. What is a cipher suite?

A cipher suite specifies the set of algorithms used for a TLS session. Suite name construction and semantics differ between TLS 1.2 and TLS 1.3.

### 4.1. TLS 1.2 example

A typical cipher suite:

~~~text
TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
~~~

Can be interpreted at a high level:

- ECDHE: ephemeral key exchange mechanism, typically providing forward secrecy.
- RSA: authentication/signature type tied to the cipher suite in TLS 1.2.
- AES_128_GCM: authenticated encryption algorithm (AEAD).
- SHA256: hash component in the corresponding suite structure.

TLS 1.2 suite names can reflect key exchange and authentication. Names like TLS_RSA_WITH_* have a different structure and should not be chosen as a modern baseline when suitable ECDHE and AEAD options exist.

### 4.2. TLS 1.3 example

TLS 1.3 defines suite names such as:

~~~text
TLS_AES_128_GCM_SHA256
TLS_AES_256_GCM_SHA384
TLS_CHACHA20_POLY1305_SHA256
~~~

In TLS 1.3, cipher suites no longer encode full key exchange/authentication information in the TLS 1.2 naming style. Choices such as supported groups and signature algorithms are negotiated in separate fields.

**You cannot infer whether TLS 1.3 is supported simply by looking for TLS_ECDHE_RSA_WITH_... in the suite list.** You need to check the protocol version and corresponding suite list.

### 4.3. Suitable cipher suites for modern systems

Normally, use the updated and tested defaults of the JDK/provider rather than pinning a single suite. Specific choices depend on:

- JDK/security provider.
- Server certificate type.
- Hardware support and performance.
- FIPS or compliance policies.
- Partner compatibility needs.
- Scope of TLS 1.2 and TLS 1.3.

Legacy cipher suites using RC4, 3DES, DES, export-grade crypto, or anonymous key exchange are not safe options for migration.

## 5. TLS negotiation and causes of “no shared cipher”

During the handshake, the client advertises the protocol versions, cipher suites, and algorithms it permits. The server selects a combination supported by both and compatible with the certificate, key exchange, and security policy.

For example:

~~~text
New Java client:
  TLS 1.3
  TLS 1.2
  Modern AEAD cipher suites

Legacy server:
  TLS 1.0
  Legacy 3DES-based cipher suites

Intersection:
  None
~~~

The result can be a handshake failure or a message stating no suitable protocol/cipher suite was found.

Another case:

~~~text
Client:
  TLS 1.2
  TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256

Server:
  TLS 1.2
  Only TLS_RSA_WITH_AES_128_CBC_SHA enabled

Intersection:
  No shared suite
~~~

Even though both support TLS 1.2, they still cannot complete the handshake because the cipher suite lists do not overlap.

**You must distinguish “shared protocol” from “entire shared cryptographic configuration”.** If one end uses an ECDSA certificate while the other only supports incompatible signature schemes, TLS can still fail even though protocol and suite names look compatible.

## 6. How do Java security policies affect the handshake?

The JDK provides security properties in the java.security file and through appropriate configuration mechanisms. Several important properties:

| Property | Impact |
|---|---|
| jdk.tls.disabledAlgorithms | Algorithms, protocols, or crypto factors disallowed in TLS |
| jdk.certpath.disabledAlgorithms | Restricts algorithms when checking certificate paths |
| jdk.tls.legacyAlgorithms | Affects consideration of legacy algorithms in certain negotiation contexts |
| jdk.tls.client.protocols | Affects default protocol versions for certain JSSE client contexts |
| https.protocols | Usually relates to protocol configuration for HttpsURLConnection |
| javax.net.ssl.trustStore | Specifies the default truststore used within applicable JSSE scope |
| javax.net.ssl.keyStore | Specifies the default keystore in corresponding usage contexts |

Property names do not mean every HTTP framework, native TLS provider, or custom SSLContext is forced to use the same configuration. You must read the client library's documentation and verify actual runtime behavior.

### 6.1. Disabled algorithms are constraints, not just a suggested list

If an algorithm or protocol is blocked by security policy, calling setEnabledProtocols or setEnabledCipherSuites does not guarantee it can be used. JSSE must obey algorithm constraints and provider rules.

For example, if a program calls:

~~~java
socket.setEnabledProtocols(new String[] { "TLSv1.2" });
~~~

yet the library or system policy does not allow a required cipher suite, the handshake still fails.

### 6.2. Do not rush to edit java.security to re-enable weak crypto

Modifying the global JDK security policy can affect **every application using that runtime**, not just one legacy endpoint. This can increase the attack surface for connections that were already secure.

Do not treat removing TLSv1, TLSv1.1, or weak algorithms from disabledAlgorithms as a default compatibility measure. If a genuinely approved exception exists, it must isolate the environment, undergo security assessment, and establish an exception retirement milestone.

For production systems, prioritize fixing on the server side, via a dedicated gateway, or explicit endpoint configuration rather than lowering the policy of the entire JVM.

## 7. Certificates and truststores: errors often mistaken for cipher mismatch

Many SSLHandshakeException errors are unrelated to cipher suites. A client may negotiate algorithms yet fail to verify the server's identity.

Several scenarios:

- Server certificate is expired or not yet valid.
- Incomplete CA chain.
- Root CA is not in the appropriate truststore.
- Hostname does not match Subject Alternative Name (SAN).
- Certificate uses a weak signature algorithm or key size blocked by the JDK.
- Certificate is revoked under the environment's checking policy.
- Server selects a different certificate than expected due to SNI.
- Client uses a custom truststore missing a CA that the default JDK originally had.

### 7.1. Truststores and keystores have different roles

A **Truststore** holds trusted certificates/CAs used to verify peers. A **Keystore** can hold private keys and certificate chains that the program uses when proving its own identity, such as a TLS server or mTLS client.

Some common filenames:

~~~text
cacerts
client-keystore.p12
partner-truststore.p12
~~~

These are illustrative names. Many JDKs use a default truststore packaged with the runtime, yet path and contents depend on vendor and configuration.

### 7.2. Inspecting certificates with keytool

List a keystore/truststore:

~~~bash
keytool -list -v -keystore partner-truststore.p12 -storetype PKCS12
~~~

List a certificate by alias:

~~~bash
keytool -list -v -alias partner-ca -keystore partner-truststore.p12
~~~

When working with partner certificates, verify fingerprint, subject, issuer, validity, and the exact CA via a trusted channel. Do not import a certificate merely because the current handshake is failing.

### 7.3. Why do custom truststores break new connections?

If the application specifies:

~~~bash
-Djavax.net.ssl.trustStore=/config/partner-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

then certain default SSLContext initialization paths may use the specified truststore instead of the default CA set operators expect. If this truststore contains only an internal CA, connections to public services may fail.

Therefore, before adding a custom truststore, decide whether to use a dedicated truststore for one specific client or whether a CA set suitable for all application connections is needed.

## 8. Hostname verification must not be disabled to “fix TLS”

A CA-valid certificate is insufficient if the endpoint name does not match the verified identity.

For example, the application connects to:

~~~text
https://payments.example.internal
~~~

yet the certificate only has SAN:

~~~text
DNS:old-payments.example.internal
~~~

The HTTPS client may report a hostname verification error, even though the CA is trusted and the cipher suite negotiated successfully.

Remediation:

1. Reissue the certificate with a valid SAN.
2. Update DNS or endpoint to match the name on the certificate.
3. Check proxy/load balancer/SNI configuration.
4. Ensure the client performs hostname verification in HTTPS contexts.

**Do not install a TrustManager that trusts every certificate or a HostnameVerifier that always returns true.** These two approaches can turn a channel believed to be secure TLS into a connection vulnerable to impersonation or man-in-the-middle attacks.

For systems using IP addresses instead of DNS names, identity verification and SAN requirements must be reviewed according to the exact identifier type. You should not assume a certificate for a DNS name is also valid when connecting via IP.

## 9. SNI and ALPN with legacy systems

### 9.1. SNI

Server Name Indication (SNI) allows the client to send the expected hostname during the TLS handshake, enabling one server sharing the same IP address to serve multiple certificates/services.

For example:

~~~text
Client requests:
  payments.example.org

Gateway on 203.0.113.10:
  payments.example.org -> certificate A
  reports.example.org  -> certificate B
  default              -> certificate C
~~~

If the client does not send SNI properly or connects by IP literal, the gateway may return the default certificate that does not match the hostname. This causes hostname verification errors or the server may reject the handshake.

When testing legacy endpoints, use the actual hostname and corresponding SNI. A test targeting only an IP may produce different results from the production application.

### 9.2. ALPN

Application-Layer Protocol Negotiation (ALPN) helps peers agree on an application-layer protocol such as h2 or http/1.1.

An endpoint can complete the TLS handshake yet the application fails because:

- The client requests HTTP/2 yet the server/proxy does not operate properly.
- The reverse proxy selects a protocol not expected by the application.
- The client library changed defaults after an upgrade.

Therefore, when an error occurs **after the TLS handshake**, inspect the selected application protocol. Do not blame every HTTPS error on newer Java on cipher suites.

## 10. mTLS: when both server and client need certificates

Mutual TLS (mTLS) requires both sides to authenticate identity with certificates. A legacy system may request a client certificate from the Java application.

Diagram:

~~~text
Java client                          Partner server
    |                                      |
    |-------- TLS ClientHello ----------->|
    |<------- Server certificate ---------|
    |                                      |
    |   Verify server trust + hostname     |
    |                                      |
    |<------- Request client cert --------|
    |-------- Client certificate -------->|
    |-------- Proof of key ownership ---->|
    |                                      |
    |<------- TLS handshake finished ---->|
~~~

The diagram is high-level; exact message ordering differs between TLS 1.2 and TLS 1.3.

Common issues during migration:

- Client keystore fails to load due to different format/type/password.
- Client certificate chain is missing an intermediate.
- Server only trusts an old CA.
- Client certificate uses an algorithm no longer accepted.
- Server restricts the list of signature algorithms or certificate types.
- Application switches to another SSLContext and therefore no longer uses the key manager containing the client key.
- TLS version or cipher suite is unsuitable even when the certificate is valid.

### 10.1. Do not mix up trust managers and key managers

In JSSE:

- **TrustManager** decides whether to trust the peer's certificate.
- **KeyManager** provides the key/certificate for the application to authenticate itself when requested.

A “client certificate not accepted” error cannot be fixed simply by importing the server CA into the truststore. You must check the client keystore, certificate chain, private key, algorithms, and server authentication policy.

## 11. Simple Java code to observe protocols and cipher suites

Using a small diagnostic program can help verify connectivity from **the exact JDK and network environment** that the application will use.

Example using SSLSocket:

~~~java
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;

public final class TlsProbe {
    public static void main(String[] args) throws Exception {
        String host = args.length > 0
            ? args[0] : "example.org";
        int port = args.length > 1
            ? Integer.parseInt(args[1]) : 443;

        SSLSocketFactory factory =
            (SSLSocketFactory) SSLSocketFactory.getDefault();

        try (SSLSocket socket = (SSLSocket)
                factory.createSocket(host, port)) {

            socket.setSoTimeout(5000);

            SSLParameters parameters = socket.getSSLParameters();
            parameters.setEndpointIdentificationAlgorithm("HTTPS");
            socket.setSSLParameters(parameters);

            socket.startHandshake();

            System.out.println(
                "Protocol: " + socket.getSession().getProtocol());
            System.out.println(
                "Cipher: " + socket.getSession().getCipherSuite());
            System.out.println(
                "Peer: " + socket.getSession().getPeerPrincipal());
        }
    }
}
~~~

Notes:

- This is a TLS diagnostic example for an endpoint with an HTTPS certificate; not a complete HTTP client.
- Using getDefault() makes results depend on the runtime's JSSE provider and truststore/keystore configuration.
- SSLParameters.setEndpointIdentificationAlgorithm("HTTPS") requires peer identity verification according to the appropriate HTTPS algorithm.
- The example lets JSSE choose allowed protocols/cipher suites, without forcing old TLS.
- The timeout in the example is a read timeout; production applications need connection timeouts, deadlines, and appropriate network policies.
- When running with a hostname, JSSE may use SNI depending on provider/implementation conditions. Verify actual SNI in handshake logs if the endpoint depends on it.

### 11.1. Viewing supported and enabled protocols

A configuration check snippet:

~~~java
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;

public final class TlsCapabilities {
    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getDefault();
        SSLEngine engine = context.createSSLEngine();

        System.out.println(
            "Supported protocols: " +
            Arrays.toString(engine.getSupportedProtocols()));

        System.out.println(
            "Enabled protocols: " +
            Arrays.toString(engine.getEnabledProtocols()));

        System.out.println(
            "Enabled suites: " +
            Arrays.toString(engine.getEnabledCipherSuites()));
    }
}
~~~

The supported/enabled lists reflect information of the engine/default context at inspection time. They do not themselves prove a remote endpoint will accept a particular suite.

### 11.2. Do not force suites without justification

For example:

~~~java
socket.setEnabledCipherSuites(
    new String[] { "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256" }
);
~~~

should only be applied if the team actively manages policy, verifies the suite is supported, and understands protocol/certificate compatibility. With TLS 1.3, pinning a TLS 1.2 suite can break desired negotiation capabilities.

For normal clients, prioritize JDK-updated defaults and verified centralized configuration.

## 12. Using OpenSSL to cross-check endpoints

OpenSSL is a useful tool for observing the server side, yet OpenSSL results **do not replace** results from JSSE. The two implementations can differ in suite lists, security policies, CA stores, and extensions.

Check an endpoint with SNI:

~~~bash
openssl s_client \
  -connect legacy.example.org:443 \
  -servername legacy.example.org \
  -showcerts
~~~

Proactively test TLS 1.2:

~~~bash
openssl s_client \
  -connect legacy.example.org:443 \
  -servername legacy.example.org \
  -tls1_2
~~~

Test TLS 1.3 when the server supports it:

~~~bash
openssl s_client \
  -connect modern.example.org:443 \
  -servername modern.example.org \
  -tls1_3
~~~

The commands above are practice samples, not checks run in this lesson.

Analyze:

- Negotiated protocol.
- Final cipher suite.
- Certificate chain sent by the server.
- Subject, issuer, validity, and SAN.
- TLS alert or handshake error.
- TLS extensions and application protocol selection when needed.

OpenSSL may display cipher suite names different from Java conventions. Do not compare text strings without understanding the two naming schemes and corresponding versions.

### 12.1. OpenSSL succeeds yet Java still fails?

Possibilities:

- The Java truststore does not contain the corresponding CA.
- Java security properties block the algorithm or key length.
- The Java client sends a different SNI.
- The Java client uses a provider other than OpenSSL.
- The Java library restricts enabled protocols/suites.
- Java checks hostname identity that the OpenSSL command did not execute as expected.
- Java uses mTLS or a different proxy route.

You must test from the exact container, host, DNS, network path, and JDK of the application. A test from a laptop may take a different path than production.

## 13. Enabling TLS debugging in JSSE

JSSE has a useful debugging mechanism during investigation.

For example:

~~~bash
java -Djavax.net.debug=ssl:handshake -jar app.jar
~~~

Depending on the JDK version and desired detail level, use the appropriate debug configuration per JSSE documentation. Some cases require adding:

~~~bash
java -Djavax.net.debug=ssl:handshake:verbose -jar app.jar
~~~

Important information typically includes:

- ClientHello/ServerHello.
- Proposed and selected TLS versions.
- Lists of cipher suites, signature schemes, and supported groups.
- Certificates and validation steps.
- Unaccepted algorithms.
- TLS alerts and the moment the handshake fails.

**Security warning:** handshake debugging can print sensitive identifiers, hostnames, certificates, and metadata. Do not enable detailed debugging indefinitely in production; restrict duration, collection location, access permissions, and log retention policies.

### 13.1. When needing to inspect the certificate path

Separate debugging for Java security/certpath can be used per appropriate JDK documentation, for example:

~~~bash
java -Djava.security.debug=certpath -jar app.jar
~~~

The output helps determine why a certificate chain was rejected: missing trust anchor, algorithm constraints, path building, or other conditions.

Do not add multiple debug flags at once if you do not know which events to look for. Excessive logs can obscure necessary signals and increase exposure risk.

## 14. Map of common TLS error messages

| Symptom | Possible cause | Investigation direction |
|---|---|---|
| SSLHandshakeException: handshake_failure | No matching parameter set, client auth, or server policy | Protocols, suites, signatures, mTLS, handshake debug |
| Received fatal alert: protocol_version | Two sides do not agree on TLS version | Enabled protocols on both sides |
| No appropriate protocol | Protocol disabled or incompatible suite | Security policy and enabled configuration |
| No cipher suites in common | No compatible suite | Suite lists, provider, certificate |
| PKIX path building failed | Cannot build trusted certificate path | Chain, CA, truststore, proxy |
| CertificateExpiredException | Certificate expired | Validity and system time |
| Certificates do not conform to algorithm constraints | Certificate/algorithm restricted | jdk.certpath.disabledAlgorithms, key/signature |
| No subject alternative DNS name matching | Hostname does not match SAN | Endpoint name, certificate, SNI |
| bad_certificate / certificate_required | Peer rejected or needs client certificate | mTLS, keystore, and server-side CA |
| Connection reset / EOF | Peer/proxy closed connection, possibly before/during handshake | Network trace, gateway logs, TLS alerts |
| Unsupported or unrecognized SSL message | Possibly speaking TLS to plaintext endpoint or wrong port/proxy | Check protocol scheme and routing |
| HTTP/2 stream/protocol error after handshake | TLS may have finished, application protocol error | ALPN and HTTP version |

The table is only an isolation guide. The same error can have multiple causes; **stack traces, handshake logs, and configurations from both sides** confirm the root cause.

## 15. Process for identifying root cause from a handshake failure

A practical process can follow this order.

### Step 1 — Identify the exact endpoint

Record:

- Hostname, port, URL, or JDBC URL.
- Whether an HTTPS proxy, reverse proxy, ingress, or service mesh is used.
- Whether TLS termination happens at a load balancer.
- Whether differences exist between staging and production.
- Whether the connection path is Java client → server or Java server ← another client.
- Whether mTLS is used.

### Step 2 — Identify the JDK and JSSE provider

Record:

- Java major/update/build and vendor.
- Actual Java executable running inside the container.
- Security provider in use.
- Whether FIPS mode or a custom crypto policy is active.
- JVM properties and custom SSLContext.
- HTTP/JDBC/gRPC library versions.

Do not only read java -version output from a developer's machine; verify the actual runtime of the service.

### Step 3 — Collect handshake results

Run a TLS probe from the same network path, or collect bounded JSSE logs. Record the protocol, suite, certificate chain, and alerts. Use OpenSSL to cross-check server configuration, without treating it as a substitute for Java client results.

### Step 4 — Classify the error

~~~text
TCP connection established?
    |
    +-- No --> DNS, routing, firewall, proxy, port
    |
    +-- Yes --> TLS handshake started?
                   |
                   +-- No --> Wrong protocol/endpoint/termination
                   |
                   +-- Yes --> Protocol overlap?
                                  |
                                  +-- No --> Upgrade TLS endpoint
                                  |
                                  +-- Yes --> Crypto overlap?
                                                 |
                                                 +-- No --> Suites/groups/signatures/policy
                                                 |
                                                 +-- Yes --> Certificate/identity valid?
                                                                |
                                                                +-- No --> CA/SAN/mTLS/algorithm
                                                                |
                                                                +-- Yes --> Check ALPN/application layer
~~~

The diagram is diagnostic, not a standard handshake state machine.

### Step 5 — Compare results on the old JDK and new JDK

Use the same endpoint, certificate, network path, and request payload if possible. Record:

- Which version/suite the old Java negotiated.
- Which protocols/suites the new Java offered.
- Whether the CA store or chain changed.
- At which step the error appeared.
- Whether library/client configuration changed.

This comparison helps avoid wrongly concluding that “new Java does not support the server”, when the cause was truststore configuration changing when switching container images.

## 16. Scenario 1: server only supports TLS 1.0

Suppose a legacy device only exposes:

~~~text
TLS 1.0
RSA key exchange
3DES-based cipher suites
~~~

A modern Java client using TLS 1.2/1.3 and a policy removing weak algorithms will have no compatible configuration.

### Priority handling

1. Check firmware or updates for the server/device.
2. Request the vendor to add TLS 1.2+ and supported suites.
3. If the device cannot be upgraded, consider a **dedicated gateway** in a restricted network zone.
4. Document the security exception and retirement deadline.
5. Do not re-enable weak TLS across the entire main Java application.

### Bounded transition gateway

~~~text
Modern Java application
      |
      | TLS 1.2/1.3 (full verification)
      v
Isolated gateway
      |
      | Restricted legacy connection,
      | approved under policy
      v
Legacy device
~~~

The gateway does not make the legacy leg safe. It only isolates the risk scope so the main application does not have to lower security across the whole JVM. You need network ACL restrictions, monitoring, authentication, secret protection, endpoint controls, avoiding Internet exposure, and a retirement plan.

In systems with strict compliance requirements, this exception may **not be allowed**. In that case, the device must be replaced or upgraded.

## 17. Scenario 2: TLS 1.2 is supported yet cipher suites do not intersect

A legacy server has TLS 1.2 yet only enables old suites. Upgrading firmware/server configuration usually solves this better than downgrading the Java client.

Process:

1. List the server-side enabled suites.
2. List the Java client-side enabled suites.
3. Confirm certificate type and signature algorithms.
4. Identify modern suites both sides can support.
5. Enable an appropriate set of AEAD/ECDHE suites on the server.
6. Test the connection with the target JDK.
7. Check that other legacy clients remain compatible with the new configuration.

You should not conclude all TLS 1.2 suites are equally secure. The TLS version itself cannot replace cipher suite evaluation.

### 17.1. Why not pin a single suite?

Fixing a single suite can cause errors when:

- Server certificates switch RSA ↔ ECDSA.
- Client or server prefers AES-GCM over ChaCha20.
- The JDK adds or changes default algorithms.
- A cluster has nodes not yet updated with the same configuration.
- Changing security providers or FIPS mode.

Configuration should define a **valid set of options**, reviewed and tested, rather than pinning without justification.

## 18. Scenario 3: CA or certificate is no longer trusted

After upgrading a container image or JDK, the application encounters:

~~~text
PKIX path building failed
unable to find valid certification path to requested target
~~~

Questions to answer:

- Did the server send the full certificate chain?
- Does the new truststore have the required CA?
- Is the javax.net.ssl.trustStore path correct?
- Do the keystore/truststore have the right type/password?
- Is an internal proxy injecting another certificate?
- Is the certificate restricted by algorithm or key size?
- Is the system clock accurate?

If a valid internal CA needs to be trusted, add that CA to the truststore via an approval process, verify fingerprints, and manage its lifecycle. If the server is missing an intermediate certificate, prioritize fixing the server's certificate chain.

Do not fix this with a TrustManager that accepts every certificate. That removes a core component of TLS verification.

## 19. Scenario 4: partner system uses mTLS

A Java client may connect successfully to a server in tests that do not require client certificates, yet fail in production when the partner enforces mTLS.

Cross-check both trust directions:

~~~text
Java client                        Partner
  truststore CA partner     <---  server certificate
  client key + cert chain   --->  truststore CA client
~~~

Information to align with the partner:

- Client certificate issuer, SAN/subject, and intended usage.
- Private key type, signature algorithm, and key length.
- Certificate chain that must be sent.
- TLS versions and cipher suites.
- Server's trusted CA list.
- Rotation policy and overlap period between old/new certificates.

If a client certificate is nearing expiration, a rotation plan is needed. A JDK change should not turn into an incident due to different keystore paths across environments.

## 20. Scenario 5: TLS handshake succeeds yet requests still fail

If logs show the handshake completed, continue checking:

- Whether ALPN selected HTTP/1.1 or HTTP/2.
- Whether HTTP host header and SNI are consistent.
- Whether the reverse proxy has a different path/routing configuration.
- Application-level authentication or tokens.
- JDBC protocol version.
- Request timeouts, session resumption, and connection pooling.
- Reused TLS sessions when certificates or endpoints change.

A Java 11+ application using java.net.http.HttpClient may have different negotiation behavior than an old client using HttpsURLConnection, even when both use JSSE. When switching HTTP libraries simultaneously with upgrading the JDK, record both changes instead of blaming everything on TLS.

## 21. Configuring Java with the right scope

Not every TLS path is configured by the same property.

| Configuration level | Scope | Risk |
|---|---|---|
| JVM security properties | Can affect multiple connections in the JVM | Broad security changes |
| JSSE system properties | Applies in corresponding JSSE contexts | May differ from custom providers/clients |
| Dedicated SSLContext | A group of clients/sockets/engines | Requires managing key/trust managers |
| SSLParameters on socket/engine | One connection or connection type | Easy to configure too tightly |
| Framework-specific TLS config | Framework clients/servers | Depends on version and implementation |
| Gateway/server TLS policy | Endpoint or network boundary | Requires centralized operational management |

### 21.1. Do not overuse https.protocols

Some applications use:

~~~bash
-Dhttps.protocols=TLSv1.2
~~~

This property usually relates to HttpsURLConnection. It does not necessarily affect every HTTP library or custom SSLContext.

If the application uses Apache HttpClient, Netty, gRPC, or JDBC, inspect the TLS configuration API of **the exact library and version**.

### 21.2. Configuring enabled protocols when truly necessary

For example:

~~~java
javax.net.ssl.SSLParameters parameters =
    socket.getSSLParameters();

parameters.setProtocols(new String[] {
    "TLSv1.3",
    "TLSv1.2"
});

socket.setSSLParameters(parameters);
~~~

This is an example proactively restricting protocols for one socket. It requires the provider to support those protocols; in multi-JDK code, check getSupportedProtocols before requesting a nonexistent protocol.

Normally, let modern TLS libraries/JDKs choose defaults automatically, unless the product has an official and verified policy.

### 21.3. Safe custom TrustManager

When a client needs an internal CA, a dedicated SSLContext can be created using a TrustManagerFactory initialized from a governed truststore. That is a better choice than replacing the global truststore or disabling certificate validation for all connections.

A safe design needs:

- A truststore containing approved CAs.
- Not skipping hostname verification.
- Separate mTLS configuration if client certificates exist.
- Rotation and expiry monitoring.
- Logging sufficient to identify endpoint and trust configuration without printing secrets.
- Testing the failure path when certificates are invalid.

Do not hard-code keystore passwords in source code or command lines that get logged.

## 22. Testing matrix when upgrading the JDK

Build a test matrix based on **actual endpoints**, not only a modern mock server.

| Client runtime | Endpoint | Requirement | Check |
|---|---|---|---|
| Old JDK | Legacy server | Baseline | Negotiated protocol/suite/cert |
| New JDK | Legacy server | Detect incompatibility | Handshake and exact error |
| New JDK | Server upgraded to TLS 1.2 | Target compatibility | Handshake, request, timeout |
| New JDK | TLS 1.3 server | Leverage new protocol | TLS version, response |
| New JDK | mTLS endpoint | Mutual authentication | Client key, chain, trust |
| New JDK | Endpoint behind proxy | Exact production path | SNI, certificate, ALPN |
| New JDK | Expired cert / wrong host | Negative test | Must reject |
| New JDK | Legacy-TLS-only server | Negative test | Must reject per policy |
| New JDK | Rollout with mixed-node cluster | Consistency | No node handshake errors |

One successful test request is not enough if it goes through a load balancer to only one node. Check all endpoint groups or inspect logs to verify nodes share consistent TLS configuration.

### 22.1. Security testing must include negative cases

To prove you are not trading security for compatibility, verify that connections fail properly when:

- The certificate is untrusted.
- The hostname mismatches.
- The certificate is expired.
- The algorithm/signature is blocked by policy.
- The protocol is disallowed.
- The server requests a client certificate yet the client does not provide one.
- SNI points to the wrong virtual host.

If negative tests succeed after a “TLS fix”, the application may have disabled an essential validation step.

## 23. TLS migration process for a large system

### Step 1 — Catalog endpoints and ownership

Clearly record:

- Related URL, port, DNS, and IP.
- Environment: dev, staging, production, disaster recovery.
- Server owner or partner.
- TLS, mTLS, and client certificate requirements.
- Connection library.
- Usage frequency and criticality.
- Certificate/firmware support expiration dates.

### Step 2 — Measure the baseline on the current JDK

Save:

- JDK vendor/version/update.
- JSSE/native TLS provider.
- Negotiated protocol and cipher suite.
- Certificate chain and truststore.
- JVM flags.
- Endpoint network path, SNI, and proxy.
- Integration test results.

Real data is needed rather than relying solely on old server documentation.

### Step 3 — Run smoke tests on the target JDK

Test each endpoint group and collect error messages. Do not start by editing jdk.tls.disabledAlgorithms. Determine whether the error is protocol, cipher, certificate, hostname, mTLS, or application layer.

### Step 4 — Classify actions

| Category | Recommended solution |
|---|---|
| Server can upgrade TLS/ciphers | Upgrade server/gateway configuration |
| Missing or wrong certificate chain | Fix chain, CA, SAN, and rotation |
| Application truststore misconfigured | Fix trust configuration by scope |
| Old client library | Upgrade library supporting target JDK |
| Server supports only weak crypto | Replace/upgrade endpoint, or approved isolated gateway |
| Unsuitable mTLS certificate | Update keystore/chain/signature |
| Incompatible proxy/SNI/ALPN | Fix routing and protocol configuration |
| Incompatible native TLS provider | Upgrade provider and dependencies |

### Step 5 — Prioritize upgrading the legacy side rather than downgrading the new side

Enabling TLS 1.2 or above, suitable cipher suites, and valid certificates on the server usually benefits all clients. Lowering the global JVM policy to be compatible with one old server can weaken many other connections.

### Step 6 — Re-test and deploy in phases

- Test all endpoints.
- Test certificate negative cases.
- Canary a group of instances with the new JDK.
- Compare TLS handshake error rates and latency.
- Have a rollback plan for both the JDK and TLS server configuration.
- Avoid changing the JDK, HTTP client, gateway, and certificates all at once without isolated tests.

### Step 7 — Remove legacy exceptions

After partners upgrade their systems, remove the temporary measures:

- Legacy gateways no longer needed.
- JVM flags enabling old crypto permissions.
- Custom trust or cipher policies no longer suitable.
- Old client library versions.
- Low-security fallback branches.

## 24. Post-migration operational monitoring

Useful metrics:

- Number of failed handshakes by endpoint.
- Error classification: protocol, cipher, PKIX, hostname, mTLS, timeout.
- Negotiated TLS version/cipher at an aggregate level when appropriate collection mechanisms exist.
- Handshake and connection establishment time.
- Retry rate due to connection resets.
- Certificate expiry horizon.
- Number of endpoints still relying on legacy TLS/ciphers.
- Number of security exceptions without a removal milestone.
- Impact on business latency and error rate.

Limit logs to avoid exposing sensitive certificate details, tenant hostnames, tokens, private keys, and unnecessary application information. Do not include private keys in diagnostic reports.

## 25. Evaluation profile template for a TLS endpoint

~~~text
APPLICATION
  Service name:
  Java runtime/vendor/build:
  HTTP/JDBC/TLS client library:
  JSSE or native provider:
  Container/base image:
  Network path and proxy:

ENDPOINT
  Hostname / port:
  Environment:
  Server owner:
  Business criticality:
  SNI name:
  mTLS required?:

CURRENT HANDSHAKE
  Negotiated TLS version:
  Negotiated cipher suite:
  Certificate subject/SAN:
  Issuer/chain:
  Client certificate:
  Truststore configuration:
  JVM TLS properties:

TARGET CHECK
  Target JDK:
  Supported/enabled protocols:
  Security policy constraints:
  Handshake result:
  Error/alert:
  Certificate validation:
  Application request result:

DECISION
  Server upgrade:
  Certificate/truststore repair:
  Client library upgrade:
  Isolated gateway exception:
  Risk owner:
  Time limit / removal milestone:

VALIDATION
  Positive handshake:
  Negative certificate tests:
  mTLS test:
  SNI/ALPN test:
  Full application flow:
  Canary metrics:
  Rollback tested:
~~~

The record should clearly state **which endpoint**, **which JDK**, **which TLS version/cipher**, **which certificate is verified**, and **which evidence shows the risk has been addressed**. Do not write vaguely “SSL enabled” or “TLS OK”.

## 26. Common misconceptions

### “TCP connection success means TLS has no issues”

False. TCP is only a precondition before the handshake; it does not prove protocol, cipher, certificate, or application-layer compatibility.

### “Server supports TLS 1.2 so modern Java can definitely connect”

Insufficient. There must be compatible cipher suites, key exchange, signatures, certificates, and security policy.

### “Setting enabled protocols will bypass disabledAlgorithms”

Incorrect. The JVM's security policy can still exclude protocols or algorithms.

### “SSLHandshakeException is always a cipher error”

Incorrect. This error can be due to certificate path, hostname, mTLS, protocol, or other constraints.

### “A TrustManager that trusts every certificate is a safe quick fix”

Incorrect. It breaks peer authentication and can create opportunities for server impersonation. Do not use it as a workaround.

### “If OpenSSL can connect, Java must be able to connect too”

Incorrect. The two clients have different providers, truststores, permitted algorithms, extensions, and validation.

### “TLS 1.3 uses cipher suite names like TLS 1.2”

Incorrect. TLS 1.3 separates key exchange/signature from the TLS 1.2-style cipher suite naming structure.

### “Only need to fix the Java application, no need to ask the server-owning team”

Incorrect. The cause is often a legacy server lacking valid protocols/algorithms. Upgrading the server is usually the best direction.

### “Enabling weak TLS for the entire JVM only affects legacy partners”

Incorrect. Changing global security policy can affect multiple connections and violate security requirements of other flows.

### “A successful handshake means migration testing is done”

Incorrect. You must test requests, application protocols, mTLS, load balancers, certificate rotation, timeouts, and production routing.

## 27. Key takeaways

When handling TLS in Java compatibility migration, answer seven questions:

1. **Do both ends share an allowed protocol?** Prefer TLS 1.2/1.3; do not re-enable obsolete SSL/TLS out of habit.
2. **Are there suitable cipher suites and algorithms?** Check protocols, groups, signature schemes, and policies.
3. **Are certificates verified properly?** Trust CAs, chains, validity, keys/signatures, and hostname identity.
4. **Are mTLS, SNI, ALPN, or proxies involved?** Inspect the exact network path and client library.
5. **Which JDK is actually running?** Confirm vendor, update level, provider, security properties, and truststore.
6. **Does the solution weaken other systems?** Prioritize upgrading servers, libraries, or using an isolated exception gateway, rather than modifying global policy.
7. **Have both success and rejection cases been verified?** Run handshakes, integration tests, certificate negative tests, and canary deployments on the target runtime.

A good TLS migration does not merely make connections with legacy systems work again. It must preserve **identity verification, transport confidentiality, operability, and a roadmap to retire obsolete protocols**. When decisions rely on handshake evidence, certificate validation, and clear risk boundaries, upgrading Java can proceed without turning a legacy exception into a long-term vulnerability.
