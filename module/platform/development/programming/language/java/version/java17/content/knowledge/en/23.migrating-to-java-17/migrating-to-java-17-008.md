# Verifying Certificates, Protocols, and Modern Security Configurations

When upgrading an application to Java 17, inspect how it authenticates TLS peers, how the JVM selects protocols and cryptographic algorithms, and which truststore/keystore sources the runtime actually uses. An application can compile and boot normally yet fail to connect to servers because of an untrusted certificate chain, a hostname mismatch, an expired certificate, or an algorithm blocked by security policy.

In Java 17, most TLS configuration goes through **JSSE (Java Secure Socket Extension)**, `SSLContext`, `SSLParameters`, `KeyStore`, `TrustManagerFactory`, `KeyManagerFactory`, and JDK security properties. The `keytool` utility inspects, creates, and imports certificates. Focus on TLS 1.2 and TLS 1.3; never re-enable SSLv3 or TLS 1.0/1.1 to get a legacy connection working.

This lesson covers distinguishing identity from trust, reading certificate chains, verifying SANs and hostnames, configuring TLS clients/servers and mutual TLS, managing truststores/keystores, understanding disabled algorithms, and diagnosing failures when migrating to Java 17. Examples use current JDK 17 APIs and tools; specific values should always be checked against your organization's policies and deployed JDK update level.

## 1. What does TLS protect?

TLS (Transport Layer Security) provides three security properties for a connection between two endpoints:

- **Confidentiality:** data sent over the connection is encrypted so third parties cannot read the contents.
- **Integrity:** data is protected against undetected modification.
- **Authentication:** one or both endpoints can prove their identity using digital certificates.

In HTTPS, TLS protects HTTP traffic between client and server. TLS is also used across many other protocols, such as database connections, SMTP, LDAP, and internal services.

A TLS handshake typically performs the following steps:

1. Both sides negotiate the TLS version and cipher suite.
2. The server presents its certificate chain so the client can verify its identity.
3. Both sides establish session keys via an appropriate key-exchange mechanism.
4. When using mutual TLS (mTLS), the server also requires the client to present a certificate.
5. After the handshake completes, application data flows over the established TLS channel.

TLS does not authorize application-level user permissions on its own. A valid certificate proves identity per PKI and trust policy; the application must still handle authentication, authorization, and input validation at the appropriate layer.

## 2. TLS 1.2 and TLS 1.3 in Java 17

Java 17 supports TLS 1.2 and TLS 1.3 through JSSE. With the default SunJSSE provider, TLS 1.3 and TLS 1.2 are enabled for standard TLS connections. JDK updates, vendors, security properties, or application settings can alter the set of permitted protocols and algorithms.

| Protocol | Status in Java 17 deployments |
| --- | --- |
| TLS 1.3 | Modern protocol, supported and enabled by default in standard JSSE configurations |
| TLS 1.2 | Widely supported and normally enabled by default |
| TLS 1.1 | Obsolete and disabled by default in current JDK configurations |
| TLS 1.0 | Obsolete and disabled by default in current JDK configurations |
| SSLv3 and legacy SSL | Unused; removed from modern security baselines |

TLS 1.3 simplifies cryptographic choices during the handshake and removes many legacy algorithms. TLS 1.2 remains secure when configured with strong cipher suites and parameters.

### 2.1. Protocol and cipher suite are distinct concepts

**Protocol** defines the TLS version and exchange rules, such as `TLSv1.2` or `TLSv1.3`.

**Cipher suite** describes the combination of algorithms used in a TLS session. Depending on the version, a suite covers authentication, key exchange, bulk encryption, and integrity protection. In TLS 1.3, cipher suite names specify the symmetric cipher and hash; key exchange and authentication are negotiated separately.

Common modern TLS 1.3 cipher suites include:

- `TLS_AES_128_GCM_SHA256`
- `TLS_AES_256_GCM_SHA384`
- `TLS_CHACHA20_POLY1305_SHA256`

For TLS 1.2, prefer AEAD suites such as AES-GCM or ChaCha20-Poly1305 paired with strong key exchange and authentication. Do not select suites by name alone; verify peer compatibility, organizational policy, and JDK configuration.

Avoid obsolete or weak algorithms such as RC4, DES, 3DES, MD5, and weak key-exchange setups. Never re-enable them just to get past a handshake failure.

### 2.2. Inspect runtime-supported and default-enabled protocols

You can inspect which protocols `SSLContext` supports and which are enabled by default:

~~~java
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import java.util.Arrays;

public class TlsProtocolInfo {
    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getDefault();

        SSLParameters supported = context.getSupportedSSLParameters();
        SSLParameters defaults = context.getDefaultSSLParameters();

        System.out.println("Supported: "
                + Arrays.toString(supported.getProtocols()));

        System.out.println("Default enabled: "
                + Arrays.toString(defaults.getProtocols()));
    }
}
~~~

`getSupportedSSLParameters()` reports protocols supported by the provider; `getDefaultSSLParameters()` reports the provider's defaults at that time. A supported protocol is not necessarily permitted: disabled-algorithm policies and other constraints can still reject it.

Never extrapolate from a single developer laptop to assume every production host shares identical settings. Verify on the exact JDK vendor, update level, and runtime configuration deployed.

## 3. Digital certificates and certificate chains

A certificate binds a public key to an identity vouched for by a CA or trust anchor. X.509 certificates typically contain:

- Subject: the identity described by the certificate.
- Issuer: the CA that signed the certificate.
- Subject Public Key Info: the public key and its algorithm.
- Validity: start (`Not Before`) and end (`Not After`) timestamps.
- Serial number: the certificate's serial identifier.
- Key Usage and Extended Key Usage: permitted purposes for the key.
- Subject Alternative Name (SAN): DNS names, IP addresses, or other identities certified.
- Signature Algorithm and the issuer's signature.
- Basic Constraints: whether the certificate represents a CA.

### 3.1. Leaf, intermediate, and root CAs

A typical certificate chain:

~~~text
Server certificate (leaf)
          |
          | signed by
          v
Intermediate CA
          |
          | signed by
          v
Root CA (trust anchor)
~~~

Servers normally send their leaf certificate along with any required intermediate certificates. Clients hold trusted root CAs in their truststore to validate the certificate path. Root certificates are pre-installed or separately managed trust anchors; servers do not need to send the root certificate in every case.

If a server omits an intermediate certificate, clients may fail to build the chain even when the root CA is in the truststore. This is a common cause of `PKIX path building failed`.

### 3.2. Verify validity and intended key usage

Certificates must satisfy the relevant checks:

- The current time falls between `Not Before` and `Not After`.
- Signatures and the chain verify cleanly.
- The issuer chains to an accepted trust anchor.
- Key Usage and Extended Key Usage match the endpoint's role.
- Key size and signature algorithm satisfy security policy.
- The certificate has not been revoked under the active revocation policy.

A server certificate typically needs Extended Key Usage `serverAuth`; a client certificate in mTLS typically needs `clientAuth`. Specific Key Usage extensions depend on key type and TLS setup. Never reuse a single certificate across unrelated roles merely because a test handshake worked.

### 3.3. SAN and hostname verification

When connecting to `api.example.com`, the client must verify that the certificate actually represents that hostname. The DNS name or IP address must appear in **Subject Alternative Name (SAN)**.

SAN example:

~~~text
X509v3 Subject Alternative Name:
    DNS:api.example.com
    DNS:api.internal.example.com
~~~

If a client connects by IP address, the certificate needs an IP SAN matching that address. Do not rely on Common Name (CN) as a substitute for SAN in modern designs.

Hostname verification is separate from chain verification:

- Chain verification confirms the certificate was issued by an accepted trust anchor.
- Hostname verification confirms the identity inside the certificate matches the host the client connected to.

Disabling hostname verification lets clients accept a valid certificate issued to a completely different server. Never install a trust-all `TrustManager` or disable hostname checks to work around an environment issue.

## 4. Truststores and keystores

These two store types are frequently confused:

- A **truststore** holds certificates or trust anchors that the application trusts when verifying peers.
- A **keystore** holds the application's own private key and certificate chain when the application must prove its identity.

| Store | Typical contents | Used for |
| --- | --- | --- |
| Truststore | Trusted root CAs or internal CAs | Verifying a peer's certificate chain |
| Keystore | Application private key and certificate chain | Presenting a server or client certificate |
| JDK `cacerts` | Trust anchors bundled with the JDK | Default JSSE trust in many setups |

For example:

- An HTTPS client needs a truststore trusting the CA that issued the server's certificate.
- An HTTPS server needs a keystore holding the server's private key and certificate chain.
- With mTLS, the client needs a keystore with its identity certificate/private key; the server needs a truststore trusting the CA that issued client certificates. The server also keeps its own keystore to prove its identity.

Private keys must be tightly protected. Never commit keystores or passwords to source control, never log passwords, and never ship a shared private key inside a desktop application for all users.

### 4.1. PKCS12 and JKS formats

Java 17 supports both PKCS12 and JKS. PKCS12 is the default KeyStore format in modern JDKs and interoperates broadly with other tools.

| Format | Characteristics |
| --- | --- |
| PKCS12 (`.p12`, `.pfx`) | Standard cross-tool format supporting private keys and certificates |
| JKS (`.jks`) | Legacy Java KeyStore format; still readable/writable in Java 17 |

When creating new stores, prefer PKCS12 unless a specific compatibility constraint dictates otherwise. An existing JKS store does not necessarily require immediate conversion if properly managed and secured; plan conversion when operational or integration needs arise.

### 4.2. JSSE default truststore

JSSE follows a defined default truststore lookup. In standard JDK setups, the runtime checks `jssecacerts` first and then `cacerts` in the JDK security directory when no custom truststore is specified.

You can list `cacerts`:

~~~bash
keytool -list -cacerts
~~~

The command may prompt for the store password. Do not embed passwords in command lines or shared scripts.

When an application points `javax.net.ssl.trustStore` at a custom store, that store becomes the configured truststore for JSSE; do not assume it automatically merges with all CAs in `cacerts`. If an application needs both public CAs and internal CAs, construct and manage a combined truststore intentionally.

Avoid manually editing the JDK's `cacerts` file on servers without automation. A JDK patch update or runtime image replacement can overwrite it. For internal CAs, an application- or deployment-managed truststore is usually easier to govern.

## 5. Use keytool to inspect and manage certificates

`keytool` ships with the JDK for managing key pairs, certificates, signing requests, and keystores/truststores.

Inspect a certificate file:

~~~bash
keytool -printcert -file server-cert.pem
~~~

List a keystore:

~~~bash
keytool -list -v -keystore server.p12 -storetype PKCS12
~~~

Export a certificate in PEM format:

~~~bash
keytool -exportcert -rfc -alias server -keystore server.p12 -storetype PKCS12 -file server-cert.pem
~~~

Commands inspecting stores may prompt for passwords. Keep real passwords out of shell history and shared scripts.

### 5.1. Generate a key pair for testing

Example generating a private key and self-signed certificate for test environments:

~~~bash
keytool -genkeypair -alias server -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -validity 365 -dname "CN=api.example.com, O=Example, C=VN" -ext "SAN=dns:api.example.com" -keystore server.p12 -storetype PKCS12
~~~

This creates:

- An RSA key pair.
- A self-signed certificate under alias `server`.
- A SAN entry for hostname `api.example.com`.
- A PKCS12 keystore storing the private key and certificate.

A self-signed certificate is accepted by a peer only if that peer explicitly trusts it. This is for controlled testing, not standard production certificate issuance.

### 5.2. Create a CSR for CA signing

In production, private keys are generally created and kept within organization-controlled systems; the public key is sent in a Certificate Signing Request (CSR) for CA issuance.

~~~bash
keytool -certreq -alias server -keystore server.p12 -storetype PKCS12 -file server.csr -ext "SAN=dns:api.example.com,dns:api.internal.example.com"
~~~

A CSR holds the public key and requested attributes, never the private key. The CA validates domain ownership/authorization per its process and returns the signed leaf certificate and chain.

When importing the signed reply, ensure the chain matches the key pair under the created alias. If intermediate CAs exist, import the necessary CA certificates into the keystore following `keytool` procedures before importing the reply, or import a CA-supplied chain file in a supported format.

### 5.3. Import a CA certificate into a truststore

Example importing an organization-verified root CA:

~~~bash
keytool -importcert -alias company-root-ca -file company-root-ca.pem -keystore truststore.p12 -storetype PKCS12
~~~

Before trusting any certificate, verify its fingerprint and issuer through an out-of-band trusted channel. Never click through trust prompts simply because a file arrived in a ticket or unauthenticated email.

Inspect the fingerprint:

~~~bash
keytool -printcert -file company-root-ca.pem
~~~

Compare the SHA-256 fingerprint against the value published through an independent organizational channel.

### 5.4. Inspect the certificate chain inside a keystore

~~~bash
keytool -list -v -alias server -keystore server.p12 -storetype PKCS12
~~~

Verify:

- Is the entry a `PrivateKeyEntry` when a private key is needed?
- Does the certificate chain contain both the leaf and required intermediates?
- Are Subject, Issuer, validity, and SAN accurate?
- Are Key Usage and Extended Key Usage appropriate?
- Do signature algorithm and key size comply with policy?

Never display or export private keys to files just to inspect certificate metadata. `keytool -list` and `-printcert` expose all needed public details.

## 6. Configure JSSE via system properties

JSSE supports standard system properties for configuring key and trust stores:

| Property | Role |
| --- | --- |
| `javax.net.ssl.trustStore` | Path to truststore |
| `javax.net.ssl.trustStoreType` | Truststore format, e.g., `PKCS12` |
| `javax.net.ssl.trustStorePassword` | Truststore password |
| `javax.net.ssl.keyStore` | Path to identity keystore |
| `javax.net.ssl.keyStoreType` | Keystore format |
| `javax.net.ssl.keyStorePassword` | Keystore password |
| `javax.net.ssl.keyStoreProvider` | Keystore provider if explicit selection is required |

Example launching with a custom truststore:

~~~bash
java -Djavax.net.ssl.trustStore=/opt/app/security/truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12 -jar application.jar
~~~

When a client identity certificate is needed, add the keystore properties:

~~~bash
java -Djavax.net.ssl.keyStore=/opt/app/security/client.p12 -Djavax.net.ssl.keyStoreType=PKCS12 -jar application.jar
~~~

Passwords can be supplied through deployment mechanisms, yet secrets should never appear directly on command lines where process listings, shell history, or logs could expose them. Use a secret manager, mounted secret files, and restricted file permissions per system policy.

### 6.1. File paths and permissions

A valid truststore setup can still fail if:

- The file is missing inside the container or host.
- The process user lacks read permissions.
- The password or store type mismatches.
- The alias or certificate chain is wrong.
- The file was overwritten during deployment.

Configure paths per environment rather than hardcoding them in source. Keystores holding private keys require tighter filesystem permissions than truststores holding only public CA certificates.

### 6.2. Does a custom truststore replace default trust?

Yes. When specifying a custom truststore via `javax.net.ssl.trustStore`, do not assume JSSE automatically merges certificates from `cacerts` into it. If both public CAs and internal CAs must be trusted, build a store containing all required trust anchors or design a deliberate composite `TrustManager`.

Never build a truststore by blindly importing whatever certificate an arbitrary peer presents. A truststore must represent CAs the organization intentionally trusts.

## 7. Use SSLContext in Java code

`SSLContext` is the central configuration point for TLS connections. It holds key managers, trust managers, and a random source for the TLS provider.

Obtain the default context:

~~~java
import javax.net.ssl.SSLContext;

SSLContext context = SSLContext.getDefault();
~~~

The default context uses the process's default JSSE configuration, including default trust/key managers resolved via runtime mechanisms and relevant system properties.

Pass the context into the Java HTTP Client:

~~~java
import java.net.http.HttpClient;
import javax.net.ssl.SSLContext;

HttpClient client = HttpClient.newBuilder()
        .sslContext(SSLContext.getDefault())
        .build();
~~~

HTTPS in `HttpClient` performs hostname verification under its default security behavior. Never disable hostname verification just to make a misnamed certificate succeed.

### 7.1. Restrict protocols with SSLParameters when required

If an application has explicit compatibility requirements, configure client protocols:

~~~java
import java.net.http.HttpClient;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;

SSLParameters parameters = new SSLParameters();
parameters.setProtocols(new String[] {"TLSv1.3", "TLSv1.2"});

HttpClient client = HttpClient.newBuilder()
        .sslContext(SSLContext.getDefault())
        .sslParameters(parameters)
        .build();
~~~

This illustrates explicitly specifying modern protocols. Unless special requirements dictate otherwise, prefer the JDK-managed defaults. Never add obsolete protocols to accommodate a legacy server; upgrade the server or terminating proxy to support modern TLS.

Settings in `SSLParameters` interact with other client and provider settings. Test real handshakes on the actual JDK 17 runtime against target endpoints.

## 8. Hostname verification with SSLSocket

When using low-level APIs like `SSLSocket`, ensure endpoint identification is configured properly. HTTPS example:

~~~java
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;

try (SSLSocket socket = (SSLSocket) SSLContext.getDefault()
        .getSocketFactory()
        .createSocket("api.example.com", 443)) {

    SSLParameters parameters = socket.getSSLParameters();
    parameters.setProtocols(new String[] {"TLSv1.3", "TLSv1.2"});
    parameters.setEndpointIdentificationAlgorithm("HTTPS");

    socket.setSSLParameters(parameters);
    socket.startHandshake();

    System.out.println("TLS protocol: "
            + socket.getSession().getProtocol());
}
~~~

`setEndpointIdentificationAlgorithm("HTTPS")` enforces HTTPS hostname verification rules during the handshake. If the connection speaks a non-HTTPS application protocol, apply that protocol's endpoint identification rules; do not assume HTTPS hostname checks apply identically to every protocol.

When creating a socket with a hostname, JSSE can send that hostname via SNI (Server Name Indication) in the handshake. SNI lets servers pick the matching certificate when multiple hostnames share an IP address. If constructing sockets manually or connecting via raw IP instead of DNS name, verify how SNI and SAN are handled.

## 9. Mutual TLS (mTLS)

In standard TLS, the server presents a certificate so the client verifies the server. With **mutual TLS**, the server also requests a client certificate to verify the client's identity.

~~~text
Client                              Server
  |                                   |
  | -------- ClientHello ----------> |
  | <------- Server certificate ---- |
  | -------- Client certificate ---> |  (when requested by server)
  | <------ Handshake complete ----> |
  |                                   |
  | ======= Encrypted channel ====== |
~~~

mTLS is commonly used for service-to-service communication, internal APIs, or systems requiring transport-layer workload authentication.

### 9.1. What do client and server need?

An mTLS client typically needs:

- A truststore trusting the CA that issued the server certificate.
- A keystore containing the client's private key and certificate chain.
- Key Usage/EKU on the client certificate compatible with `clientAuth`.
- Protection for the private key and password.

The server needs:

- A keystore containing the server's private key and certificate chain.
- A truststore trusting the CA that issued client certificates.
- Configuration requiring client authentication.
- Identity verification and authorization checks after the TLS handshake completes.

A CA-trusted certificate does not automatically grant a client permission to call every API. The application must still map the certificate identity to business authorization.

### 9.2. Create an SSLContext with KeyManager and TrustManager

Example illustrating building an `SSLContext` for an mTLS client. Secret-retrieval methods are placeholders; never hardcode real passwords in source code:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

char[] keyStorePassword = obtainKeyStorePassword();
char[] privateKeyPassword = obtainPrivateKeyPassword();
char[] trustStorePassword = obtainTrustStorePassword();

KeyStore identity = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(Path.of("client.p12"))) {
    identity.load(in, keyStorePassword);
}

KeyManagerFactory keyManagers = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
keyManagers.init(identity, privateKeyPassword);

KeyStore trust = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(Path.of("truststore.p12"))) {
    trust.load(in, trustStorePassword);
}

TrustManagerFactory trustManagers = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
trustManagers.init(trust);

SSLContext context = SSLContext.getInstance("TLS");
context.init(
        keyManagers.getKeyManagers(),
        trustManagers.getTrustManagers(),
        null
);
~~~

Then pass `context` to the client:

~~~java
HttpClient client = HttpClient.newBuilder()
        .sslContext(context)
        .build();
~~~

This snippet illustrates wiring `KeyManagerFactory` and `TrustManagerFactory`. In production code, retrieve passwords via secret management, zero out `char[]` arrays once no longer needed, close streams, pick the right alias when a keystore holds multiple identities, and test the certificate chain.

### 9.3. Require client certificates on the server

On a server using `SSLServerSocket`, enforce client certificates:

~~~java
SSLServerSocket serverSocket = (SSLServerSocket)
        context.getServerSocketFactory().createServerSocket(8443);

serverSocket.setNeedClientAuth(true);
~~~

`setNeedClientAuth(true)` mandates a client certificate; the handshake fails if the client does not present an accepted certificate. `setWantClientAuth(true)` only requests one optionally, so it is not equivalent to mandatory mTLS.

In real server frameworks, mTLS is usually configured through framework connectors or server settings. Regardless of the API used, verify the truststore, client certificate, hostname/identity policy, and post-handshake authorization.

## 10. JDK security properties

Beyond system properties, Java reads **security properties** from runtime security configuration. In JDK 17, the main file usually lives at:

~~~text
JAVA_HOME/conf/security/java.security
~~~

Key security properties related to TLS and certificates:

| Property | Role |
| --- | --- |
| `jdk.tls.disabledAlgorithms` | Disabled TLS protocols, ciphers, key sizes, or algorithms |
| `jdk.certpath.disabledAlgorithms` | Restricted algorithms and parameters during certificate path verification |
| `jdk.jar.disabledAlgorithms` | Restricted algorithms when verifying JAR signatures |
| `crypto.policy` | JCE cryptographic strength policy; modern JDKs default to unlimited |

Disabled algorithm lists evolve across JDK security updates. Never copy a property string from an old blog post or another host to overwrite the security file without understanding every entry.

### 10.1. jdk.tls.disabledAlgorithms

This property blocks unacceptable TLS protocols and algorithms. Default JDK configurations typically disable TLS 1.0/1.1, SSLv3, RC4, DES, and weak key/signature setups.

Do not remove disabled entries just to connect to a legacy server. If a server supports only TLS 1.0, weak ciphers, or certificates with deprecated algorithms, upgrade the server, certificate, or intermediary proxy.

### 10.2. jdk.certpath.disabledAlgorithms

This property governs certificate path validation. A certificate can have a structurally valid chain yet still be rejected if a signature algorithm or key size violates policy.

For example, an older CA signing certificates with a weak algorithm or short RSA key triggers algorithm constraint errors. Reissue the certificate/chain with compliant algorithms and key sizes rather than disabling JVM-wide constraints.

### 10.3. Unlimited cryptographic policy

Modern JDKs, including Java 17, enable the unlimited JCE policy by default. You normally do not need to download or install "unlimited strength jurisdiction policy files" as required in legacy JDKs.

If your application or vendor runtime overrides security configuration, check the live runtime. Do not apply outdated policy-file installation steps to Java 17.

### 10.4. Modify security properties with control

Supplemental security properties can be supplied via `java.security.properties` at JVM launch. A single `=` appends/overrides specified properties; a double `==` replaces the entire default security properties file.

General example:

~~~bash
java -Djava.security.properties=/opt/app/security/extra.security -jar application.jar
~~~

Replacing the entire security configuration with `==` can strip away essential JDK protections. Use it only when you understand the complete file and have testing, approval, and patching processes. Most applications should preserve the JDK baseline and override only what is strictly necessary.

## 11. Certificate revocation and status checking

Validating a certificate chain and validity dates does not automatically mean revocation status was checked online. PKI deployments use CRL (Certificate Revocation List) or OCSP (Online Certificate Status Protocol) to publish revocation state.

Java PKIX/JSSE exposes options and providers for revocation checking, yet enabling them depends on CA infrastructure, network reachability of OCSP/CRL responders, and fail-open vs. fail-closed policy.

Before enabling revocation checks in production, verify:

- Does the CA publish a CRL or OCSP responder?
- Can the runtime reach the responder endpoint from the production network?
- How should the system behave when the responder is unreachable?
- Does checking latency impact handshake budgets?
- Does organizational policy mandate fail-closed or another strategy?

Do not assume every JSSE TLS connection always performs online revocation checking identically. Configure and verify according to your organization's actual PKI.

## 12. Diagnose TLS and certificate failures

When upgrading to Java 17, read the exact exception rather than tossing in multiple JVM flags at once.

| Error or symptom | Common cause | Where to inspect |
| --- | --- | --- |
| `PKIX path building failed` | Could not build chain to a trust anchor | Check truststore, root/intermediate CAs, and chain sent by server |
| `unable to find valid certification path` | CA is untrusted or chain is incomplete | Verify CA/fingerprint and import the right trust anchor |
| `No subject alternative DNS name matching` | Hostname missing from SAN | Issue certificate with SAN matching the hostname the client connects to |
| `CertificateExpiredException` | Certificate expired | Renew/reissue certificate and verify host clock |
| `NotBefore` not yet reached | Certificate not yet valid or skewed clock | Check system time and certificate validity |
| `protocol_version` or similar alert | Endpoints share no common protocol | Verify server supports TLS 1.2/1.3 and check client policy |
| `handshake_failure` | Cipher, certificate, client auth, or policy mismatch | Enable TLS debug in test environment and inspect handshake |
| `Algorithm constraints check failed` | Algorithm or key size blocked by security policy | Check disabled algorithms and reissue compliant certificate |
| `bad_certificate` | Peer rejected certificate or chain | Check EKU, Key Usage, trust, and client/server identity |
| `UnrecoverableKeyException` | Wrong password or private key entry | Check store/key passwords, alias, and entry type |
| `No available authentication scheme` | Server found no compatible certificate/algorithm | Check key manager, key type, certificate chain, and TLS version |

### 12.1. Enable JSSE debugging safely

Handshake logging can be enabled in dev or test environments:

~~~bash
java -Djavax.net.debug=ssl,handshake,trustmanager -jar application.jar
~~~

Logs print protocol negotiation, certificate chains, trust manager decisions, and handshake steps. Output is verbose, impacts performance, and can reveal sensitive infrastructure details. Enable only during active diagnosis, restrict log access, and disable immediately afterward.

To inspect certificate path validation:

~~~bash
java -Djava.security.debug=certpath -jar application.jar
~~~

This is deep diagnostic logging; never leave it permanently enabled in production without evaluating overhead and log volume.

### 12.2. Verify inputs with keytool

Before altering JVM flags, inspect the certificates and stores directly:

~~~bash
keytool -printcert -file server-cert.pem
keytool -list -v -keystore truststore.p12 -storetype PKCS12
keytool -list -v -keystore client.p12 -storetype PKCS12
~~~

Confirm aliases, chains, validity, SANs, issuers, and entry types. If fetching a server certificate, retrieve it over a trusted path and verify its fingerprint; never blindly import a certificate simply because a handshake failed.

## 13. Configurations to avoid

Several legacy workarounds weaken security and must be avoided on Java 17:

- Re-enabling SSLv3, TLS 1.0, or TLS 1.1.
- Permitting RC4, DES, 3DES, MD5, or weak signature algorithms.
- Installing a `TrustManager` that accepts every certificate.
- Disabling hostname verification.
- Trusting a certificate merely because it shipped with the app without verifying its fingerprint/origin.
- Embedding private key or truststore passwords in source code or logs.
- Adding certificates of unknown origin to a truststore.
- Overwriting all of `java.security` just to bypass one algorithm constraint.
- Calling private JDK internals to alter TLS instead of using public JSSE APIs.

If a system only works when certificate checks are disabled or TLS is downgraded, fix the certificate, PKI, or server endpoint. Never treat a weakened configuration as a completed upgrade.

## 14. Review workflow when upgrading to Java 17

Follow this sequence:

1. **Verify the runtime:** record JDK 17 vendor, version, and update level across build, test, and production.
2. **Inspect protocols:** check default protocols and disabled-algorithm policies on the exact runtime.
3. **List all endpoints:** document hostnames, ports, protocols, server owners, and mTLS requirements.
4. **Inspect certificates:** validity, SAN, EKU, Key Usage, key size, signature algorithm, and chains.
5. **Inspect trust:** identify which truststore is loaded; verify CAs/fingerprints and intermediate chains.
6. **Inspect identity:** for mTLS clients/servers, confirm keystores hold the right private keys and chains.
7. **Audit configuration:** check system properties, custom `SSLContext`, trust/key managers, and security properties.
8. **Run integration tests:** execute handshakes to every endpoint on the exact JDK 17 and deployment configuration.
9. **Diagnose failures:** enable JSSE/certpath debugging in test environments when handshakes fail.
10. **Verify operations:** confirm processes exist for certificate renewal, secret rotation, truststore updates, and expiry alerting.
11. **Eliminate weak configs:** remove temporary exceptions, old protocols, trust-all managers, and hostname bypasses.
12. **Repeat on the final artifact:** test the actual deployed container/runtime image/installer, not just a developer laptop.

### 14.1. Minimum test matrix

| Scenario | Expected outcome |
| --- | --- |
| Server has valid certificate chain and matching SAN | Handshake succeeds |
| Server omits intermediate CA | Client rejects or fails chain build; succeeds once chain is fixed |
| Certificate is expired | Client rejects |
| SAN does not match hostname | Client rejects hostname |
| Server supports only TLS 1.0/1.1 | Connection fails under modern security baseline |
| Server supports TLS 1.2 or 1.3 with strong suites | Handshake succeeds |
| mTLS client lacks certificate when server mandates it | Handshake fails |
| mTLS client presents CA-trusted cert with valid EKU | Handshake succeeds; app proceeds to authorization |
| Custom truststore lacks required CA | Client rejects chain |
| Certificate uses disabled algorithm | Certificate/protocol rejected by policy |

Deliberately testing failure scenarios confirms the application genuinely enforces trust and hostname checks rather than merely passing happy-path endpoints.

## 15. Operational certificate and secret management

Certificates generally have shorter lifetimes than applications. TLS configuration must therefore operate alongside renewal and rotation processes:

- Track expiration dates for both leaf and intermediate certificates.
- Alert well ahead of expiration to allow renewal and rollout.
- Identify who owns private keys, who issues certificates, and who updates truststores.
- Maintain procedures to rotate private keys and replace certificate chains.
- Update truststores through verified procedures when CAs change.
- Test rolling updates so instances do not temporarily run mismatched chains or truststores.
- Never store passwords or private keys in repositories, image layers, or logs.
- Restrict keystore/truststore read permissions to the process user.
- Maintain a certificate rollback plan that does not revert to weak algorithms.

Truststores also need updates when root/intermediate CAs change or trust policies evolve. Never copy `cacerts` from an old JDK and freeze it for years without security update maintenance.

## 16. Hands-on exercises

### Exercise 1 — Inspect default protocols

Run `TlsProtocolInfo` on JDK 17. Compare supported protocols with default enabled protocols. Explain why "supported" does not automatically mean "permitted by security policy."

### Exercise 2 — Inspect a certificate

Use `keytool -printcert -file` to inspect a certificate. Record Subject, Issuer, validity, SAN, Key Usage, Extended Key Usage, key size, and signature algorithm.

### Exercise 3 — Distinguish truststore and keystore

Create a PKCS12 keystore for a test server and a separate truststore. Explain where the private key lives, where the CA certificate lives, and why the two stores serve distinct purposes.

### Exercise 4 — Create a CSR

Generate a key pair, then use `keytool -certreq` to create a CSR with SANs. Inspect the CSR contents and explain why the private key is not sent to the CA.

### Exercise 5 — Verify SANs

Configure two test hostnames: one listed in the SAN and one absent. Connect with an HTTPS client and observe hostname verification results.

### Exercise 6 — Test mTLS

Issue a client certificate signed by a test CA, configure a server to require client authentication, and configure a client keystore. Test handshakes both with and without the client certificate.

### Exercise 7 — Read disabled algorithm policies

Open `JAVA_HOME/conf/security/java.security` and locate `jdk.tls.disabledAlgorithms` and `jdk.certpath.disabledAlgorithms`. Note which protocols/algorithms are restricted in your JDK build and explain why they should not be removed arbitrarily.

### Exercise 8 — Investigate a handshake

Introduce a controlled failure such as a truststore missing a CA or a hostname mismatch. Enable `javax.net.debug` in a test environment, pinpoint the failing handshake step, and fix the certificate/trust configuration properly.

## 17. Principles to remember

- Java 17 supports TLS 1.2 and TLS 1.3; active protocols and algorithms depend on providers, updates, and security policies.
- TLS protocol, cipher suite, certificate path, and hostname verification are distinct layers of a secure connection.
- A truststore defines trusted CAs; a keystore holds the application's private key and identity certificate.
- Certificate chains must lead to an accepted trust anchor; servers should send required intermediate certificates.
- Use SANs matching hostnames/IPs, and check validity, EKU, Key Usage, key size, and signature algorithm.
- Use `keytool` to inspect, generate CSRs, import certificates, and verify keystores/truststores; confirm fingerprints over a trusted channel.
- Use `SSLContext`, `SSLParameters`, `KeyManagerFactory`, and `TrustManagerFactory` for JSSE configuration.
- For HTTPS, never disable hostname verification; for mTLS, certificate authentication still requires application-level authorization.
- `jdk.tls.disabledAlgorithms` and `jdk.certpath.disabledAlgorithms` are part of the security baseline; do not remove constraints to accommodate obsolete endpoints.
- JDK 17 defaults to unlimited cryptographic policy; do not follow legacy policy-file installation steps.
- Enable TLS debugging under tight control, restrict log access, and turn it off after investigation.
- Maintain processes for certificate renewal, truststore updates, and private key rotation.

When upgrading to Java 17, validate connections against modern protocols, certificate chains, hostnames, and real trust policies. Managing keystores/truststores deliberately, preserving secure algorithm defaults, and testing both successful and rejected handshakes ensures stable TLS connectivity without weakening security.
