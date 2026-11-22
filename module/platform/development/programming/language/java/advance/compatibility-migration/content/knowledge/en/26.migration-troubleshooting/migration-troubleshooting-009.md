# TLS Handshake Failures, Disabled Algorithms, and Truststore Mismatches

In **Java Advance Compatibility Migration**, an application may work fine on an old JDK yet fail immediately when upgrading to a new JDK with `SSLHandshakeException`, `PKIX path building failed`, `No appropriate protocol`, or `Algorithm constraints check failed`. These messages are often lumped together as "SSL errors" and temporarily worked around by disabling certificate verification or re-enabling old TLS versions. That is a dangerous approach: **errors can occur at completely different stages of the TLS handshake and require different remediation measures**.

For example, for the same connection to `https://api.partner.example`, the failure may originate from:

- The Java client and server no longer share a common protocol/cipher suite.
- The new JDK disables an algorithm or key size that does not meet policy.
- The server does not send all required intermediate certificates.
- The application truststore does not contain the appropriate trust anchor.
- The application uses a different truststore from the JDK the developer is inspecting.
- The hostname does not match the certificate's Subject Alternative Name (SAN).
- The server requires **mutual TLS (mTLS)**, but the client does not send an appropriate certificate.
- A proxy, load balancer, or service mesh returns a different certificate based on hostname/SNI.
- A new container uses a different JDK/truststore/security provider than the old environment.

This lesson belongs to the **Troubleshooting** group, guiding how to pinpoint exactly where the handshake fails, read JSSE debug logs, inspect `java.security` policies, distinguish keystore from truststore, analyze certificate chains, and establish a safe remediation workflow on the target JDK.

> Principle: **do not disable certificate validation, hostname verification, or disabled-algorithm constraints to make a connection "green"**. Fix the protocol, certificate, truststore, or integration component that genuinely fails to meet requirements.

## 1. What Does the TLS Handshake Do?

TLS is a protocol that helps a client and server establish an authenticated and encrypted transport channel. HTTPS uses TLS to protect HTTP communication.

For an HTTPS connection, the general flow:

```text
Java application / JSSE client
            |
            |  1. TCP connect
            v
TLS server / gateway / reverse proxy
            |
            |  2. ClientHello:
            |     TLS versions, cipher suites,
            |     SNI, supported groups,
            |     signature algorithms, ALPN...
            |
            |  3. ServerHello:
            |     protocol and negotiated parameters
            |
            |  4. Server certificate chain
            |
            |  5. Client verifies:
            |     certificate path, trust anchor,
            |     validity, key usage, algorithms,
            |     hostname / endpoint identity
            |
            |  6. If mTLS: client also presents
            |     certificate and proves possession of private key
            |
            |  7. Key establishment / Finished
            v
         TLS session
            |
            v
        HTTP request
```

This is a conceptual diagram, not the exact message sequence of every TLS 1.2 and TLS 1.3 flow. TLS 1.3 has a different handshake format and procedure from TLS 1.2, in which many messages after ServerHello are encrypted. What matters is identifying the **failing stage**.

### 1.1. Handshake failure differs from an HTTP error

If the TLS handshake fails, the application typically **has not sent the HTTP request yet** and will not receive HTTP status `401`, `403`, or `500` in the normal way.

Conversely, HTTP 401 after a successful handshake may be an authorization/application token error rather than a certificate trust issue.

### 1.2. Verification layers can apply simultaneously

A certificate chain must satisfy multiple checks:

- **Trust:** is there a valid path to an accepted trust anchor?
- **Validity:** is the certificate currently valid in terms of time?
- **Identity:** does the certificate match the hostname/endpoint?
- **Usage:** are Key Usage/Extended Key Usage suitable for a TLS server or client?
- **Algorithm:** do the signature and public key size/curve comply with security policy?
- **Revocation:** if the environment enables revocation checking, is the OCSP/CRL status valid?

These are separate conditions. **Importing a CA into the truststore does not fix an expired certificate or a weak algorithm.**

## 2. Three Core Root-Cause Categories

| Category | Typical signs | Inspection scope | Primary remediation |
|---|---|---|---|
| Protocol/cipher negotiation | `protocol_version`, `handshake_failure`, `No appropriate protocol` | TLS versions, cipher suites, signature schemes, supported groups | Upgrade TLS stack on client/server, select permitted common configuration |
| Restricted algorithm/key | `Algorithm constraints check failed`, key size/signature warnings | `jdk.tls.disabledAlgorithms`, `jdk.certpath.disabledAlgorithms`, certificate/key | Reissue certificate/key, replace with supported algorithm or provider |
| Truststore/certificate path | `PKIX path building failed`, `unable to find valid certification path` | Actual truststore, chain, CA, intermediates, hostname | Configure proper truststore/chain, verify CA via trusted channel |

Beyond these three main categories, mTLS adds a **client authentication dimension**. An error caused by the server not trusting the client certificate should not be handled by modifying the truststore the client uses to trust the server.

### 2.1. An error's symptom can change after a "partial fix"

For example, a server only supports TLS 1.0 and its certificate has expired:

1. The new JDK blocks TLS 1.0, so the handshake fails immediately during negotiation.
2. The administrator enables TLS 1.2 on the server.
3. The client progresses further in the handshake and then reports certificate expired.

This does not mean enabling TLS 1.2 caused the certificate error; it reveals that **multiple layers of problems existed simultaneously**.

## 3. Must Identify the Exact JDK and Connection Path

Before investigating the truststore, you must know **the JVM actually opening the connection**.

### 3.1. Build JVM differs from runtime JVM

A system might have:

```text
Developer IDE:      JDK 21
Gradle daemon:      JDK 17
Java compiler:      JDK 21, --release 11
JUnit test worker:  JDK 17
Production image:   JDK 11
```

When an error occurs in production, `java -version` on a laptop does not tell you the TLS policy of the production process.

Run inside the **exact container/process/environment**:

```bash
java -version
```

Record:

- JDK vendor/distribution.
- Full version and update.
- `java.home` used by the application.
- Application server or launcher.
- Container image digest.
- Custom runtime image if using `jlink`.
- Relevant JVM system properties.

### 3.2. The JVM does not necessarily connect directly to the target server

A request may pass through:

```text
Java client
    |
    v
Corporate outbound proxy
    |
    v
Service mesh egress
    |
    v
Public API gateway / load balancer
    |
    v
Backend service
```

TLS can be terminated at multiple points; the certificate Java sees may be the certificate presented by a proxy/gateway rather than the backend certificate.

Record:

- Actual hostname and port.
- DNS resolution.
- SNI hostname.
- Proxy settings and `HTTPS_PROXY`/client library configuration.
- Load balancer or service mesh.
- Where TLS termination / re-encryption happens.
- Whether the test endpoint matches production.

Do not copy verbatim production certificates, passwords, or private keys into public bug reports.

## 4. JSSE and Types of Trust Material

Java typically implements TLS via **Java Secure Socket Extension (JSSE)**. Related classes belong to Java SE, for example:

```java
javax.net.ssl.SSLContext
javax.net.ssl.SSLSocket
javax.net.ssl.SSLHandshakeException
javax.net.ssl.TrustManager
javax.net.ssl.KeyManager
```

Even if an application migrates from Java EE to Jakarta EE, **`javax.net.ssl.*` remains a Java SE API**, not changing to `jakarta.net.ssl.*`.

### 4.1. Truststore: who does the client trust?

A truststore holds certificates/trust anchors that one side uses to verify the other side's certificates.

For standard HTTPS:

```text
Java HTTPS client
  |
  +--> Client truststore:
         Root CA or approved trust anchor
         used to verify the server certificate chain
```

Java does not need the server's own certificate in the truststore if the server certificate has a valid chain to a CA that the truststore already trusts.

### 4.2. Keystore: who am I?

A keystore typically contains the private key and certificate chain of **the connecting party itself**.

With mTLS:

```text
Client keystore:
  client private key
  client certificate and chain to send

Client truststore:
  CA/trust anchor to verify the server
```

The server side also has both roles:

```text
Server keystore:
  private key + server certificate/chain

Server truststore (for mTLS):
  trust anchors to verify client certificates
```

A single PKCS#12 file can contain both key entries and trusted certificates, yet **their logical roles remain different**. Assigning the wrong property for the intended purpose can cause confusing errors.

### 4.3. The default truststore is not always the same as the OS

In many typical JDK/JSSE configurations, by default the JVM uses runtime-associated truststores such as `jssecacerts` if it exists per selection rules, or the JDK's `cacerts`.

Some vendors/providers integrate with OS trust or have custom configurations. You should not assume that:

- Because Chrome connects successfully, Java must be able to connect.
- Because a CA was imported into the Windows Certificate Store, every JVM automatically uses that CA.
- Because a CA was added to the JDK on a developer machine, it also exists in the container.
- When upgrading the JDK, the `cacerts` truststore automatically retains all old internal CAs.

You must identify the **actual TrustManagerFactory and truststore of the failing process**.

## 5. Properties Configuring Truststore and Keystore

Common JSSE system properties:

| Property | Role |
|---|---|
| `javax.net.ssl.trustStore` | Path to truststore used by default JSSE trust managers in compatible configurations |
| `javax.net.ssl.trustStoreType` | Truststore type, e.g. `PKCS12`, `JKS` |
| `javax.net.ssl.trustStorePassword` | Password to open/verify the truststore when required |
| `javax.net.ssl.keyStore` | Path to keystore containing the client's own key/certificate |
| `javax.net.ssl.keyStoreType` | Keystore type |
| `javax.net.ssl.keyStorePassword` | Keystore password when required |
| `https.protocols` | Protocols used by certain HTTPS client implementations, scope depends on API |
| `jdk.tls.client.protocols` | Specifies default client protocols for JSSE in supported contexts |

Example of a client using an application-specific truststore:

```bash
java \
  -Djavax.net.ssl.trustStore=/etc/my-app/truststore.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -jar my-app.jar
```

Typically a secure mechanism is also needed to supply the file password if the truststore requires one. **Do not place passwords in shell commands, history, CI logs, or documentation examples as real values.**

### 5.1. Custom truststores can drop default trust anchors

If the application sets:

```text
-Djavax.net.ssl.trustStore=/etc/my-app/partners.p12
```

and the file only contains one internal CA, some HTTPS connections to public services may start reporting `PKIX path building failed`.

Reason: configuring a custom truststore under default JSSE trust management **does not automatically guarantee merging** its contents with the default `cacerts`.

Design an application truststore containing the complete set of approved trust anchors or configure an explicit trust management strategy. Do not write an `X509TrustManager` that accepts every certificate for a "quick merge".

### 5.2. Wrong path or store type

For example:

```text
javax.net.ssl.trustStore=/opt/old-jdk/lib/security/cacerts
```

However, the container does not have that file. JSSE may fail while initializing trust material or use an unexpected trust anchor list depending on the implementation/configuration.

Check:

- Does the file exist in the **container/process filesystem**?
- Does the process user have read permission?
- Is the file in the right JKS/PKCS12 format?
- Is the password valid?
- What aliases/trust anchors does the truststore contain?
- Does the application use a custom `SSLContext` that ignores system properties?

### 5.3. Setting system properties too late may have no effect

An HTTP library may have already initialized and cached `SSLContext` or `SSLSocketFactory` before the application calls:

```java
System.setProperty("javax.net.ssl.trustStore", "...");
```

In that case, changing the property after startup will not necessarily update already-created trust managers. Prefer configuring from **startup time** or creating an explicit `SSLContext` according to the library in use, then re-initializing the client when configuration changes.

Do not test changing a late property and conclude the JVM ignores the truststore without determining the lifecycle first.

## 6. Inspecting Security Policies in the Running JDK

Besides the truststore, the JDK controls certain algorithms/protocols via security properties usually located in `java.security`, which in modern JDKs is commonly placed under `conf/security`.

Important properties:

| Security property | Typical control |
|---|---|
| `jdk.tls.disabledAlgorithms` | Algorithms, protocols, and constraints during JSSE/TLS negotiation |
| `jdk.certpath.disabledAlgorithms` | Constraints during certificate path validation |
| `jdk.security.legacyAlgorithms` | Labels legacy algorithms in certain tools/contexts; does not mean an absolute ban |
| `jdk.jar.disabledAlgorithms` | JAR signature policy, **not the property handling HTTPS handshakes** |
| `crypto.policy` | JCE strength policy, distinct from certpath/TLS algorithm constraints |

### 6.1. Read the actual effective values with Java

```java
import java.security.Security;

public final class JdkSecuritySnapshot {
    public static void main(String[] args) {
        print("jdk.tls.disabledAlgorithms");
        print("jdk.certpath.disabledAlgorithms");
        print("jdk.security.legacyAlgorithms");
        print("crypto.policy");
    }

    private static void print(String key) {
        System.out.println(key + " = " + Security.getProperty(key));
    }
}
```

Run with the **exact failing runtime JDK**:

```bash
javac JdkSecuritySnapshot.java
java JdkSecuritySnapshot
```

If the compiler is missing in a slimmed runtime image, you can compile beforehand with a compatible JDK and then run that class on the image being inspected. Do not demand modifying the production image just to compile a diagnostic tool.

### 6.2. Why is `Security.getProperty` different from `System.getProperty`?

Security properties have their own loading mechanism, typically using:

```java
Security.getProperty("jdk.tls.disabledAlgorithms");
```

Whereas JVM system properties such as the truststore path typically use:

```java
System.getProperty("javax.net.ssl.trustStore");
```

Do not query the wrong kind and conclude the property does not exist.

### 6.3. A constraint may include conditions

The disabled algorithms configuration may contain expressions such as:

```text
RSA keySize < 2048
```

This is a **syntax example**, not a claim that every JDK sets this threshold for every key type or usage. Some constraints also evaluate trust anchor, usage, or timestamp.

Record the **vendor, full JDK update, and actual security properties**, because JDK updates can tighten defaults without changing the major version.

## 7. Legacy TLS Versions and `No appropriate protocol`

TLS 1.0 and TLS 1.1 are obsolete and disabled by default in many modern updated JDKs. Servers supporting only those protocols may no longer be compatible with a new Java client.

Error examples:

```text
javax.net.ssl.SSLHandshakeException:
    Received fatal alert: protocol_version
```

or:

```text
javax.net.ssl.SSLHandshakeException:
    No appropriate protocol
    (protocol is disabled or cipher suites are inappropriate)
```

You cannot be certain the server only supports TLS 1.0 from the message alone. It could also be that there are no common cipher suites, the client configuration accidentally excluded TLS 1.2/1.3, or the server/proxy returned an alert due to policy.

### 7.1. Investigation steps

1. Identify the endpoint behind the proxy, hostname, and port.
2. Check the JSSE client's default enabled protocols and `jdk.tls.disabledAlgorithms` policy.
3. Check the server's or TLS terminator's supported protocols/ciphers.
4. Inspect handshake logs to see `ClientHello`, `ServerHello`, or fatal alerts.
5. Upgrade the outdated party's TLS stack per support policy.
6. Re-verify the certificate, trust chain, and key sizes after negotiation succeeds.

### 7.2. Enabling a protocol in code alone does not bypass policy

For example:

```java
sslSocket.setEnabledProtocols(new String[] { "TLSv1.2" });
```

This configures enabled protocols for the socket; it **does not force JSSE to ignore** `jdk.tls.disabledAlgorithms`. If a protocol or algorithm is blocked, security policy and interoperability of both sides must be addressed.

### 7.3. Why not re-enable TLS 1.0 globally?

Lowering the JVM's policy can weaken other connections that already use modern TLS. If a partner cannot upgrade yet, there must be a risk-assessed transition plan with network/process isolation, monitoring, and a replacement deadline—not silently enabling legacy TLS system-wide.

A transition gateway can limit the blast radius, yet the legacy connection leg still uses a weak protocol; it does not suddenly become secure.

## 8. Cipher Suites, Signature Algorithms, and Supported Groups

The handshake does not only agree on the TLS version. Client and server must negotiate compatible parameters: cipher suites, key-exchange groups, and signature schemes, depending on the TLS version.

### 8.1. TLS 1.2 versus TLS 1.3

In TLS 1.2, cipher suite names usually express multiple components such as key exchange, authentication, and encryption. In TLS 1.3, the cipher suite primarily specifies AEAD/hash; signature schemes and key establishment are negotiated in separate extensions.

Example TLS 1.3 cipher suite:

```text
TLS_AES_128_GCM_SHA256
```

Do not assume that merely having the cipher suite above means any RSA/ECDSA server certificate or named group is accepted. Signature algorithms and supported groups must be checked if the handshake fails at that stage.

### 8.2. Legacy appliances supporting only weak ciphers

An old gateway may only support RC4, 3DES, or cipher suites disabled by modern policies. Upgrading the Java client can expose an error indicating no common ciphers.

The sustainable approach is to upgrade the TLS endpoint, certificates/keys, and select strong ciphers supported by both sides, rather than forcing the client to restore weak ciphers.

### 8.3. `handshake_failure` does not point to a single cause

A `handshake_failure` alert can be caused by:

- No common cipher/protocol.
- Incompatible signature scheme.
- Required client certificate is missing or unsuitable.
- Server configuration error.
- Proxy, WAF, or load balancer policy.
- SNI/ALPN mismatch or TLS extension negotiation difference.

Read the **handshake timeline and server logs** before making fixes.

## 9. Certificate Path, Trust Anchors, and Intermediate CAs

A server typically presents a chain:

```text
Leaf certificate: api.partner.example
               |
               v
Intermediate CA: Partner Issuing CA
               |
               v
Root CA / trust anchor: Partner Root CA
```

The client must build a valid path to a trust anchor it accepts.

### 9.1. The server does not necessarily send the root CA

In real TLS, servers usually send leaf and intermediate certificates; the root CA can be omitted because the client already has the root in its truststore.

Therefore, "the server didn't send the root" does not by itself prove the chain is incomplete. Conversely, a **missing intermediate** often prevents the client from building a path, especially if the intermediate is not available from another source per the implementation.

### 9.2. The truststore must contain the right trust anchor

If the server switches to a new CA, an old JDK or internal custom truststore may not yet have the appropriate root.

Example:

```text
Application A:
  Truststore A has new Root CA -> pass

Application B:
  Truststore B only has old Root CA -> PKIX fail
```

Modifying Java source is not necessarily relevant. You must update the trust material through a trustworthy channel and retry.

### 9.3. Do not blindly import leaf certificates

Directly importing a leaf certificate to "trust the server" can create unintended trust/pinning, impair automatic certificate rotation, and bypass approved CA governance.

For partner connections, clearly choose one of the policies:

- Trust a valid public CA from a managed truststore.
- Trust a verified private enterprise CA.
- Use certificate/public key pinning if designed with managed rotation and fallback.

Do not grab the certificate received from an unverified endpoint and automatically add it to the truststore. Doing so can legitimize a certificate presented by an attacker or an unapproved proxy.

## 10. `PKIX path building failed`: How to Analyze

A common error:

```text
javax.net.ssl.SSLHandshakeException:
    PKIX path building failed:
    sun.security.provider.certpath.SunCertPathBuilderException:
    unable to find valid certification path to requested target
```

This indicates the **certificate path builder could not find a valid path to a trust anchor** in that context. You cannot immediately conclude it is due to a missing root CA; it could also be caused by a missing intermediate or path constraints.

### 10.1. Questions to answer

- Which truststore is the Java process using?
- Does the truststore contain the approved root/intermediate CA?
- Which certificates does the server send for the SNI hostname being used?
- Is the certificate chain in the right order with proper issuer/subject linkage?
- Are the CAs properly marked with Basic Constraints/Key Usage?
- Is any certificate expired/not yet valid?
- Are there key size/signature constraints?
- Is a revocation policy enabled?
- Is a proxy replacing the certificate chain?

### 10.2. `unable to find valid certification path` differs from algorithm constraints

If the nested cause has:

```text
java.security.cert.CertPathValidatorException:
    Algorithm constraints check failed ...
```

investigate key size/signature and `jdk.certpath.disabledAlgorithms`.

If the nested cause says:

```text
unable to find valid certification path to requested target
```

prioritize checking the chain and trust anchors. Both conditions can coexist; read the indicators carefully.

### 10.3. Use the exact same truststore when comparing environments

A developer might test with JDK 21's `keytool`, while the production application uses JDK 11 and a different custom truststore. Different results are entirely possible.

Include the truststore path and alias in the report, not merely "imported CA".

## 11. Disabled Algorithms in the Certificate Chain

A new JDK may reject a certificate using a signature or public key that does not meet current policy.

Legacy cases:

- RSA key too short.
- SHA-1 signatures restricted in a specific context.
- Unsupported DSA/EC parameters or curves.
- Intermediate CA has a weak signature algorithm.
- Incompatible TLS signature schemes between the two ends.

### 11.1. Key size must be evaluated per algorithm

Do not compare AES-256, RSA-256, and EC P-256 solely by bit count. 1024-bit RSA is no longer suitable for many modern security purposes; 2048/3072-bit RSA or EC on a supported named curve are typically considered based on policy and interoperability needs.

**Specific thresholds must be read from the JDK's policy and organizational standards.** Do not assume a security property has the same value across all vendors/updates.

### 11.2. SHA-1 may still be present in APIs yet blocked in a specific usage

Java may still provide:

```java
java.security.MessageDigest.getInstance("SHA-1");
```

for processing legacy data, while the certpath validator restricts SHA-1 certificate signatures under specific conditions.

**Having an algorithm implementation does not mean it is permitted in TLS certificate validation.**

### 11.3. Changing the truststore does not fix a weak key

If the leaf or intermediate certificate has a key/signature that fails policy, merely importing an additional issuer CA might not solve it. A suitable key pair must be generated, the certificate/chain reissued, or the endpoint upgraded.

### 11.4. Do not modify `java.security` globally just to pass tests

Relaxing `jdk.certpath.disabledAlgorithms` or `jdk.tls.disabledAlgorithms` can weaken other connections in the same JVM. If a temporary exception is needed because a legacy system cannot yet be upgraded, it must have approval, isolation, auditing, and a removal date.

## 12. Hostname Verification and Wrong-Identity Certificates

A connection may have a trusted chain yet still be rejected because the certificate is not issued for the hostname the client is calling.

Example:

```text
Called URL:   https://orders.partner.example
Certificate:  DNS:api.partner.example
```

If the SAN has no matching name, a standards-compliant HTTPS client must reject the endpoint identity.

The message may look like:

```text
No subject alternative DNS name matching
orders.partner.example found.
```

or another exception wrapping an endpoint identification error.

### 12.1. Trusting the CA does not replace hostname matching

Adding a certificate to the truststore does not make the SAN match the hostname. Fix the URL/SNI or reissue the certificate with an appropriate SAN.

### 12.2. Connecting by IP easily causes mismatches

If a certificate has the DNS name `api.partner.example` yet the client connects to:

```text
https://10.0.0.25
```

IP-based hostname verification can fail if the certificate does not contain a matching IP SAN.

Do not disable hostname verification. Use the right DNS hostname or issue a certificate covering the endpoint identity in use.

### 12.3. SNI and virtual hosts

When one IP serves multiple TLS sites, the client sends **Server Name Indication (SNI)** so the server/gateway selects the corresponding certificate and configuration.

If the app uses an IP or a custom TLS client does not send the proper SNI, the server may return a default certificate belonging to another hostname.

During debugging, check:

- Hostname passed to `SSLSocket`/HTTP client.
- SNI extension in `ClientHello`.
- Certificate actually sent by the server.
- Which virtual host the proxy/load balancer selects.

Do not conclude the server is misconfigured merely from a test command lacking SNI.

## 13. mTLS: The Client Side Also Needs Its Own Certificate

In **mutual TLS**, the server authenticates the client using a certificate in addition to the client authenticating the server.

```text
Java Client                            Server
    |                                    |
    |<------ Server certificate ----------|
    | Validate server using truststore   |
    |                                    |
    |------- Client certificate --------->|
    |   taken from client keystore       |
    |                                    |
    |<------ Server validates client -----|
    |   using server-side trust config   |
```

An mTLS failure may surface on the client side with the alert:

```text
Received fatal alert: bad_certificate
```

or:

```text
Received fatal alert: unknown_ca
```

Alert messages seen from the client **may indicate the server rejected the client certificate**, not necessarily that the client does not trust the server.

### 13.1. Items to check on the client

- Does the keystore have a `PrivateKeyEntry` with the appropriate client key/certificate?
- Does alias/key selection match the intended identity?
- Is the client certificate chain complete as required?
- Are the key password/keystore password and type correct?
- Does the certificate have the clientAuth EKU and appropriate Key Usage?
- Are the key algorithm/signature supported by the TLS server?
- Does the client send the certificate when requested by the server?
- Does routing through a proxy change where mTLS takes place?

### 13.2. Items to check on the server

- Does the server trust the CA that issued the client certificate?
- Does the server restrict acceptable issuers/client identities?
- Does the server have a different key size, signature algorithm, or revocation policy?
- Is the certificate mapping to user/service identity correct?
- Has the server truststore rotated CAs?

### 13.3. Two truststores serve two different directions

In mTLS:

- The client truststore **trusts the server**.
- The server truststore **trusts the client**.

Modifying the client truststore to contain the client CA does not fix the server rejecting the client certificate. You must identify **which side is emitting the fatal alert and which validator is failing**.

## 14. Enabling TLS Logging Properly

JSSE provides logging to assist handshake investigation.

Example:

```bash
java \
  -Djavax.net.debug=ssl,handshake \
  -jar my-app.jar
```

To view additional certificate path debug output:

```bash
java \
  -Djavax.net.debug=ssl,handshake \
  -Djava.security.debug=certpath \
  -jar my-app.jar
```

Depending on the JDK version, additional debug categories can be used to inspect trust manager/key manager and certificate messages. Choose an appropriate log level so as not to generate excessive data.

### 14.1. What should logs focus on?

- `ClientHello`: protocol/cipher lists, SNI, groups/signature schemes.
- `ServerHello`: negotiated protocol/cipher.
- Certificate chain sent by the server.
- CertificateRequest if mTLS.
- Trust manager/certpath and algorithm constraints lines.
- Whether a fatal alert was sent or received.
- Nested Java exception and when it occurred.
- Current hostname/endpoint.
- Which TLS terminator or proxy participated in the handshake.

### 14.2. Reading the direction of a fatal alert

Distinguish:

```text
Received fatal alert: ...
```

from:

```text
Fatal ... / Produced fatal alert ...
```

An alert **received from the peer** usually suggests the peer rejected a handshake step. Do not assume the Java client truststore has an issue if the server is the one sending the alert.

### 14.3. Securing sensitive information in logs

TLS debug output can contain hostnames, certificate metadata, system configurations, and internal communication details. Do not log or share passwords/private keys, session secrets, or tokens. Do not leave overly verbose logging enabled long-term in production.

If production logs must be captured, ensure an owner, scope, retention policy, and redaction process are in place.

## 15. Inspecting Server Certificates with `keytool`

The Java JDK provides `keytool`.

### 15.1. Inspecting a certificate in a file

```bash
keytool -printcert -file server.crt
```

Important fields:

- Subject / Issuer.
- Serial number and SHA-256 fingerprint.
- Valid from/to.
- Signature algorithm.
- Subject public key algorithm and key size.
- SAN DNS/IP.
- Basic Constraints, Key Usage, Extended Key Usage.

### 15.2. Inspecting a TLS endpoint

```bash
keytool -printcert -sslserver api.partner.example:443
```

The command uses the network to fetch certificate info from the endpoint it observes. Results depend on SNI, proxy, load balancer, and network path, so run it from an environment close to the application.

Do not assume the result on a laptop is the certificate the production container definitely sees.

### 15.3. Inspecting the application truststore

```bash
keytool -list -v \
  -keystore /etc/my-app/truststore.p12 \
  -storetype PKCS12
```

The tool may prompt for a password if needed. Do not write the password directly in the shell command.

Determine:

- Does the expected alias exist?
- Is the entry a trusted certificate or a private key entry?
- Does the fingerprint match the approved CA?
- Is the certificate still valid (not expired)?
- Is it the exact store path used by the JVM?

### 15.4. Inspecting the JDK default CA store

You can use the `keytool -list -cacerts` feature on supported JDKs:

```bash
keytool -list -cacerts
```

Remember that the command uses the **JDK containing `keytool`**, which may differ from the application process's JDK. Cross-check the `java.home` path and the `keytool` command on PATH.

## 16. Testing TLS with OpenSSL: Useful, but Does Not Replace JSSE

If the environment has OpenSSL:

```bash
openssl s_client \
  -connect api.partner.example:443 \
  -servername api.partner.example \
  -showcerts
```

The command can display the chain sent by the server along with negotiation details. `-servername` requests the right SNI virtual host.

You can proactively test a specific protocol depending on OpenSSL/server capabilities:

```bash
openssl s_client \
  -connect api.partner.example:443 \
  -servername api.partner.example \
  -tls1_2
```

and:

```bash
openssl s_client \
  -connect api.partner.example:443 \
  -servername api.partner.example \
  -tls1_3
```

### 16.1. Limitations of OpenSSL results

OpenSSL and JSSE:

- May use different trust stores.
- Have different cipher/support policies.
- Have different signature/groups/hostname verification defaults.
- Have different proxy/SNI configurations.
- Have different behavior and versions.

Therefore, **a successful OpenSSL handshake does not prove a Java client will succeed**. It mainly helps determine the server's capabilities and chain.

### 16.2. Verifying hostname/CA with the right policy

If using OpenSSL to validate a chain, specify the CA bundle/verification method and hostname matching the OpenSSL version in use. Do not treat the tool printing certificates or a successful TCP connection as proof that trust validation passed.

In migration conclusions, prioritize **testing with a JSSE client and the application's actual truststore**.

## 17. Java Diagnostic Client Using Default JSSE

A standalone program can perform a handshake and print the negotiated protocol/cipher, while still enforcing trust and hostname verification.

```java
import java.util.List;
import javax.net.ssl.SNIHostName;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSession;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;

public final class TlsProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java TlsProbe <dns-host> <port>");
        }

        String host = args[0];
        int port = Integer.parseInt(args[1]);

        SSLSocketFactory factory =
                (SSLSocketFactory) SSLSocketFactory.getDefault();

        try (SSLSocket socket =
                (SSLSocket) factory.createSocket(host, port)) {

            SSLParameters parameters = socket.getSSLParameters();

            // Require endpoint identity verification per HTTPS.
            parameters.setEndpointIdentificationAlgorithm("HTTPS");

            // Only use a DNS host in this example.
            parameters.setServerNames(List.of(new SNIHostName(host)));
            socket.setSSLParameters(parameters);

            socket.startHandshake();

            SSLSession session = socket.getSession();
            System.out.println("Protocol: " + session.getProtocol());
            System.out.println("Cipher suite: " + session.getCipherSuite());
            System.out.println("Peer: " + session.getPeerPrincipal());
        }
    }
}
```

Example uses Java 11+ APIs. Run with the exact JDK and JVM properties of the application:

```bash
javac TlsProbe.java
java \
  -Djavax.net.debug=ssl,handshake \
  TlsProbe api.partner.example 443
```

### 17.1. Limitations of the probe

- This probe uses the default `SSLSocketFactory`; if the application uses a custom `SSLContext`, custom provider, or specifically configured HTTP client, results may differ.
- The probe does not perform full HTTP requests/ALPN negotiation like every HTTP client.
- The probe assumes a valid DNS hostname for SNI; do not use it as-is with IPs or invalid hostnames.
- The probe does not automatically supply a client certificate unless a keystore/KeyManager is configured appropriately.
- This is a diagnostic tool, not a comprehensive test suite for proxies, HTTP/2, auth, or mTLS.

**Do not remove `setEndpointIdentificationAlgorithm("HTTPS")` to allow wrong-hostname certificates when evaluating HTTPS.** If the actual client applies different endpoint identification, that difference must be documented in the conclusion.

## 18. Checking Active Config Without Printing Passwords

A Java diagnostic can print non-sensitive configuration information:

```java
import java.security.Security;

public final class TlsRuntimeSnapshot {
    public static void main(String[] args) {
        printSystem("java.version");
        printSystem("java.vendor");
        printSystem("java.home");
        printSystem("javax.net.ssl.trustStore");
        printSystem("javax.net.ssl.trustStoreType");
        printSystem("javax.net.ssl.keyStore");
        printSystem("javax.net.ssl.keyStoreType");

        printSecurity("jdk.tls.disabledAlgorithms");
        printSecurity("jdk.certpath.disabledAlgorithms");
    }

    private static void printSystem(String name) {
        System.out.println(name + " = " +
                System.getProperty(name, "<not set>"));
    }

    private static void printSecurity(String name) {
        System.out.println(name + " = " + Security.getProperty(name));
    }
}
```

Do not print `javax.net.ssl.trustStorePassword` or `javax.net.ssl.keyStorePassword`, even in test environments if logs are retained long-term.

### 18.1. `trustStore` unset does not mean no truststore

When `javax.net.ssl.trustStore` is not declared, JSSE may apply default truststore lookup logic. Therefore, the line:

```text
javax.net.ssl.trustStore = <not set>
```

does not mean the client accepts every certificate or skips CA validation.

### 18.2. Custom SSLContext may not use these properties

An HTTP client library may load a truststore in code:

```java
SSLContext context = ...
```

or use a separate security provider. In that case, JVM system properties only show environment configuration, without proving which store the actual context uses. You need to inspect how the client is constructed.

## 19. Managing the Truststore Properly and Safely

Once a valid private CA is confirmed missing from the truststore, you can consider adding the verified CA certificate:

```bash
keytool -importcert \
  -alias approved-partner-ca \
  -file approved-partner-ca.crt \
  -keystore /etc/my-app/truststore.p12 \
  -storetype PKCS12
```

The tool may prompt for a password and trust confirmation. The example assumes the path and CA certificate have been approved by the organization.

### 19.1. Verify the fingerprint from a trusted source

Before importing, check the CA's SHA-256 fingerprint via an independent, trustworthy channel:

```bash
keytool -printcert -file approved-partner-ca.crt
```

Do not automatically import a certificate grabbed directly from a trust-failing connection without external verification; that is a circular trust flaw.

### 19.2. Avoid modifying the JDK-wide `cacerts`

If the application needs to trust an internal CA, prefer application-owned trust material or the organization's certificate management solution. Modifying the global `cacerts` can:

- Affect every application sharing the runtime.
- Be lost when replacing the container image/JDK update.
- Make it hard to audit who added the CA.
- Be hard to reproduce in CI and production.

Updating the truststore must be part of deployment and certificate management processes, not manual edits on a running container that get forgotten.

### 19.3. Certificate rotation requires a compatibility window

When a partner CA changes, coordinate:

1. Release a truststore supporting the new CA before the server switches certificates, if policy permits.
2. Verify all JVM instances have picked up the new trust material.
3. Rotate the server certificate/chain on schedule.
4. Monitor handshake failures.
5. Remove the old CA only after no valid endpoint requires it.

If the old root was revoked due to a security incident, the schedule must follow risk assessment; do not keep old trust merely for rollback convenience.

## 20. Scenario A: Java 8 Connects, Java 17 Reports a Protocol Error

Suppose:

```text
Java client JDK 8 (old build) --- TLS 1.0 ---> Device gateway
Java client JDK 17 ----------- X ------------> Device gateway
```

How to investigate:

1. Record full JDK 8/17 updates and security properties, not just major versions.
2. Enable JSSE handshake logging on JDK 17.
3. Check what `ClientHello` is sent and which protocols/ciphers are proposed.
4. Check server capabilities via configuration or OpenSSL.
5. Determine whether it can enable TLS 1.2/1.3 and modern ciphers.
6. Upgrade the endpoint/firmware/proxy first.
7. Re-run the Java client on the target JDK.
8. After negotiation, inspect the certificate chain/hostname next.

**Do not downgrade the JDK or re-enable TLS 1.0 globally as a default fix.** If an appliance cannot be replaced yet, a risk-assessed isolation solution is required.

## 21. Scenario B: Server Reissues Certificate, Java Reports PKIX

Suppose the server just switched from internal CA A to internal CA B:

```text
New server leaf -> Intermediate B -> Root B

Old client truststore:
  Root A
```

The JVM does not yet trust Root B, so the certificate path builder cannot find a valid path.

Remediation approach:

1. Identify the exact truststore of the Java process.
2. Inspect the server chain at the corresponding hostname/SNI.
3. Verify Root B and Intermediate B through a trusted channel.
4. Update the approved trust material in release/container configuration.
5. Reload/restart the client as required by the SSLContext lifecycle.
6. Verify server hostname SAN, validity, usage, and algorithm policy.
7. Test thoroughly on both staging and production deployment paths.

Do not manually import individual leaf certificates into `cacerts` on every machine.

## 22. Scenario C: Valid Chain, but RSA Key Is Too Short

Suppose:

```text
Server:
  Certificate public key: RSA 1024 bit

New client JDK:
  CertPathValidatorException:
    Algorithm constraints check failed...
```

Many modern policies reject 1024-bit RSA in TLS/certpath contexts. In this case:

- Adding the root CA may not resolve it.
- Changing the keystore password is irrelevant.
- An always-true `TrustManager` disables validation and is dangerous.
- Relaxing the disabled-algorithm policy globally increases risk.

The proper fix is usually to **generate a new key pair, reissue the certificate with a policy-compliant key size/algorithm, configure the full chain, and test both ends**.

Example key pair generation command for illustration:

```bash
keytool -genkeypair \
  -alias tls-server \
  -keyalg RSA \
  -keysize 3072 \
  -sigalg SHA256withRSA \
  -storetype PKCS12 \
  -keystore server-keystore.p12 \
  -validity 365
```

The command creates an initial self-signed certificate as `keytool` operates; it does not automatically become a trusted production certificate. Proper CSR, CA, SAN, usage, and issuance processes are required.

## 23. Scenario D: Java mTLS Client Reports `bad_certificate`

An application calls a bank API via mTLS. After moving to a new container, outbound calls receive:

```text
javax.net.ssl.SSLHandshakeException:
    Received fatal alert: bad_certificate
```

The server may have rejected the client's certificate. Check:

1. Does the client process load the right PKCS12/JKS keystore?
2. Does the keystore have the private key entry and chain?
3. Does the selected alias match the expected business identity?
4. Is there a key password/permissions or HSM token failure?
5. Is the certificate expired, revoked, or missing clientAuth EKU?
6. Does the server trust the client's CA and accept its signature algorithms?
7. Is a proxy terminator altering the mTLS flow?
8. What do server client-authentication logs say?

**Do not modify the truststore that trusts the server when evidence shows the server does not trust the client identity.**

### 23.1. Keystore and truststore can reside in the same PKCS12 file

That is valid when designed so, yet the properties and KeyManager/TrustManager still must use the appropriate entries. A file with a `trustedCertEntry` without a `PrivateKeyEntry` is insufficient to prove the client possesses the private key for mTLS.

## 24. Scenario E: Browser and curl Succeed, Yet Java Fails

A user tests:

```text
Chrome: PASS
curl: PASS
Java: SSLHandshakeException
```

Possibilities to examine:

- Browser/curl uses the OS truststore or a different CA bundle from the JVM.
- `curl` uses a different proxy from Java.
- The JVM has a custom truststore missing public CAs.
- JSSE security policy differs from curl's TLS library.
- The Java HTTP client does not send the same SNI/ALPN/protocol.
- The Java process in the container has a different DNS route.
- The client uses a dedicated mTLS certificate that the browser does not use.

How to investigate:

1. Record the exact host/port/route of all three clients.
2. Inspect the certificate chain observed through each path.
3. Compare trust anchors and TLS protocols.
4. Test using a Java JSSE probe with the default/actual client configuration.
5. Conclude based on Java and server logs, not on the browser showing a padlock.

## 25. Scenario F: Only One Container Pod Fails After Image Upgrade

Suppose 9/10 pods connect to the API, while the new pod after rollout reports PKIX.

Investigate along differing variables:

- Image digest and JDK update.
- Truststore file mounted into the container.
- Kubernetes Secret/ConfigMap version and mount path.
- File permissions, symbolic links, and read-only mounts.
- Environment variables and JVM flags.
- Service mesh sidecar/proxy configuration.
- Process startup time and SSLContext caching.
- DNS resolution, egress policy, and node network.

An old pod may still be running an earlier version whose truststore contained the new CA due to a manual workaround, whereas the clean new image lacks that certificate. Trust material must be placed in **managed configuration**, not "patched" pod by pod.

## 26. Ordered Diagnostic Workflow

### Step 1 — Record the full exception

Do not save only the `SSLHandshakeException` line. You need:

- Stack trace and nested causes.
- Fatal alert direction.
- Time, release version, and endpoint.
- Java process/runtime JDK version.
- Whether a proxy or mTLS is involved.

### Step 2 — Determine how far the handshake progressed

From JSSE debug:

- No TCP connection: investigate network/DNS first.
- No ServerHello yet: protocol/cipher/SNI/gateway.
- Certificate received: trust chain, hostname, algorithm, usage.
- CertificateRequest seen: mTLS client identity.
- TLS completed yet HTTP fails: move to application/auth diagnostics.

This is a classification guide, not a complete handshake model for every TLS version.

### Step 3 — Snapshot security properties

Read `jdk.tls.disabledAlgorithms`, `jdk.certpath.disabledAlgorithms`, vendor/update. Do not edit policies before having evidence.

### Step 4 — Inspect the actual truststore

Identify the path/type and CA entries used by the TrustManager. Confirm that a custom truststore did not drop default roots.

### Step 5 — Inspect the server certificate chain

Use `keytool`, OpenSSL, and server-side configuration. Pay attention to SNI, proxy, SAN, intermediates, key size, validity.

### Step 6 — Inspect client identity if mTLS

Inspect the client keystore, private key alias, client chain, EKU, and server trust policy. Separate server trust errors from client trust errors.

### Step 7 — Fix the right side

- TLS negotiation failure: upgrade server/client TLS stack.
- Weak certificate/key: rotate keys and reissue certificates.
- Missing trust anchor: update approved truststore.
- Missing intermediate: fix the chain sent by the server.
- Hostname mismatch: fix DNS/URL or SAN.
- Client certificate rejected: fix mTLS keystore, chain, or server trust mapping.
- Wrong proxy/SNI: fix routing or hostname handling.

### Step 8 — Test with the real JVM and artifact

Run on the exact runtime image, proxy path, and HTTP client of the product. A simple JDK probe helps isolate the issue, yet integration tests are what confirm the full flow works.

### Step 9 — Record post-fix state

Record JDK version, security properties, endpoint, issuer/fingerprints (do not store secrets), truststore version, negotiated protocol, and test outcome.

## 27. Quick Lookup Table for Common Errors

| Log/exception | Initial direction | Do not jump to concluding |
|---|---|---|
| `Received fatal alert: protocol_version` | Peer rejected protocol | Definitely only TLS 1.0 |
| `No appropriate protocol` | Protocol/cipher disabled or unsuitable | Simply setting `TLSv1.2` in code fixes it |
| `handshake_failure` | No matching parameters or peer policy | Only caused by root certificate |
| `PKIX path building failed` | Could not build trust path | Definitely only missing root CA |
| `unable to find valid certification path` | Truststore/chain/certpath | Blindly importing leaf is enough |
| `Algorithm constraints check failed` | Key/signature/policy non-compliant | Adding a CA always fixes it |
| `certificate expired` | Invalid validity period | Simply changing truststore fixes it |
| `No subject alternative DNS name matching` | Endpoint identity/SAN mismatch | Disable hostname verification |
| `Received fatal alert: bad_certificate` | Peer rejected cert/handshake step | Only the client truststore is wrong |
| `Received fatal alert: unknown_ca` | Peer does not trust received cert's CA | Definitely Java missing server root |
| `UnrecoverableKeyException` | Private key/password/keystore issue | Only caused by server certificate |
| `Keystore was tampered with, or password was incorrect` | Store/password/type or file | Only caused by TLS protocol |
| `NoSuchAlgorithmException` | Provider/algorithm availability | Every algorithm of that name is banned in TLS |
| `SSLPeerUnverifiedException` | Peer identity not yet verified | Definitely a CA error |
| `Connection reset` before TLS complete | Network/proxy/server closed socket | Only a wrong truststore |

This table is an **investigation guide**, not a 1-to-1 mapping from one error to one exact cause. Read the full stack trace and handshake logs.

## 28. Dangerous Workarounds to Avoid

### 28.1. TrustManager trusting every certificate

A commonly seen anti-pattern example:

```java
@Override
public void checkServerTrusted(
        java.security.cert.X509Certificate[] chain,
        String authType) {
    // DO NOT DO THIS: accepts every certificate.
}
```

If the application does not verify the chain, it becomes easier for an attacker to spoof an endpoint. Never use this in production, not even "just temporarily to get the migration running".

### 28.2. Disabling hostname verification

Another anti-pattern is configuring a `HostnameVerifier` that always returns true. It allows a certificate valid for another hostname to be accepted for the wrong endpoint.

Issue a certificate with the right SAN or call the right hostname; do not skip identity checks.

### 28.3. Re-enabling weak algorithms JVM-wide

Relaxing `jdk.tls.disabledAlgorithms` or `jdk.certpath.disabledAlgorithms` to get past a legacy server can weaken many other connections. Consider an exception only in an isolated environment, with security approval and a removal deadline.

### 28.4. Embedding passwords/private keys into source

Do not:

- Commit keystore passwords to the repository.
- Send private keys via chat/logs for debugging.
- Write secrets into long-lived command-line arguments.
- Copy production keystores onto uncontrolled laptops.
- Bake unverified CAs/private keys into images.

Use secret management and proper filesystem permissions.

### 28.5. "Fixing" by reverting to a very old JDK indefinitely

Downgrading can help isolate a regression, yet giving up all security patches to preserve weak protocols is not a sustainable migration path.

## 29. Regression Testing After Fixing TLS

After the endpoint connects, you must prove the change did not only fix one test path.

### 29.1. Environment matrix

| Environment | What to confirm |
|---|---|
| Developer | Actual JDK and truststore, not just browser |
| CI | Right runtime/toolchain, test network path |
| Staging | Proxy/gateway and certificates equivalent to production |
| Production canary | Handshake failure rate and latency, mTLS identities |
| Production full | All pods/regions have consistent trust material |
| Failover | Alternative endpoint/certificate/CA chain |
| Renewal window | Certificate rotation and truststore rollout |

### 29.2. Test negative cases as well

- Untrusted certificates must be rejected.
- Mismatched hostnames must be rejected.
- Expired certificates must be rejected.
- mTLS clients without an appropriate certificate must be rejected.
- Servers supporting only forbidden protocols must not trigger automatic downgrade.
- Wrong truststore or missing CA must report a diagnosable error.

If all connections "pass" including invalid certificates, validation mechanisms were very likely disabled.

### 29.3. Monitor by version

Track:

- SSL/TLS handshake failure count and error types.
- PKIX/certpath errors.
- mTLS reject rate.
- Endpoint-specific failures.
- JDK/container image version.
- TLS negotiated protocol/cipher if approved telemetry is available.
- Certificate expiration alerts.
- Post-handshake API error rate/latency.

A handshake incident occurring by region/instance may point to a truststore or proxy mismatch on part of the fleet.

## 30. Pre-Closure Checklist

- [ ] Confirmed exact JVM, JDK vendor/update, and runtime image of the failing process.
- [ ] Distinguished TCP/network errors from TLS handshake and HTTP responses.
- [ ] Identified hostname, port, SNI, proxy, and TLS termination points.
- [ ] Read all nested causes and fatal alert direction.
- [ ] Distinguished protocol/cipher negotiation, certpath policy, and truststore mismatch.
- [ ] Recorded effective `jdk.tls.disabledAlgorithms` and `jdk.certpath.disabledAlgorithms`.
- [ ] Reviewed appropriate TLS versions, cipher suites, signature schemes, and supported groups.
- [ ] Checked the leaf/intermediates/trust anchor certificate chain at the exact endpoint.
- [ ] Checked SAN, validity, Key Usage/EKU, and key sizes/signatures.
- [ ] Identified the truststore actually used by JSSE, including custom SSLContext if present.
- [ ] Checked keystore/private key and server trust policy if the application uses mTLS.
- [ ] Checked the container's JDK/cacerts, not just the developer machine.
- [ ] Verified CA fingerprint via a trusted source before importing.
- [ ] Avoided permissive TrustManager, disabling hostname verification, and re-enabling weak TLS.
- [ ] Tested the actual JSSE/HTTP client after fixing.
- [ ] Tested negative cases to confirm security is still enforced.
- [ ] Updated trust material in versioned deploy configuration, not manually per pod.
- [ ] Established a certificate rotation plan and expiration date monitoring.
- [ ] Recorded test evidence, redacted logs, and canary/production results.
- [ ] Prepared rollback/roll-forward aligned with security policy.

## 31. Conclusion

An `SSLHandshakeException` error after a JDK upgrade is not a single problem. It can stem from **no longer having a common protocol/cipher**, **keys/signatures not complying with security properties**, **the truststore lacking a CA or an incomplete chain**, **hostname/SNI mismatch**, or **mTLS client identity rejected by the server**. The same outward exception can originate from many different stages of the TLS handshake.

In Java Advance Compatibility Migration, effective diagnosis starts from the **exact JVM and exact endpoint**, then reading JSSE handshake logs, analyzing fatal alerts and nested causes, identifying security policies, inspecting certificate chains/truststores/keystores, and retesting with the actual client and runtime. Once the root cause is found, update the TLS endpoint, reissue certificates/keys, or configure approved trust anchors, rather than bypassing the verification mechanisms that the new JDK protects. The goal is not merely a successful connection, but **connecting successfully with the right identity, the right trust chain, and an appropriate security level**.