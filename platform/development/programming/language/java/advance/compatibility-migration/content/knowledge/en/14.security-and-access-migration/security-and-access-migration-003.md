# Truststore, root certificates, and server certificate chains

When upgrading the JDK, a Java application that previously connected over HTTPS normally may suddenly fail with `SSLHandshakeException`, `PKIX path building failed`, or `certificate_unknown`. These errors do not necessarily indicate that business code changed. They can arise because **the new runtime's truststore differs from the old runtime's**, a root CA is no longer trusted, the server does not send complete intermediate certificates, a certificate expired, the hostname does not match, or the new JDK's security policy rejects legacy cryptographic algorithms.

Properly understanding **truststores**, **root CAs**, and **server certificate chains** helps distinguish errors belonging to Java client configuration, the TLS server, the PKI system, or intermediate network paths. During **Java Advance Compatibility Migration**, remediation must preserve the security objective: authenticating the server's exact identity, validating a proper certificate path, and never disabling verification just to make requests succeed.

This lesson explains the concepts, PKIX/JSSE architecture, inspection using `keytool` and `openssl`, setting up custom truststores, handling mTLS, and a verification workflow when changing JDK versions.

## 1. Why does the same endpoint work on an old JDK yet fail on a newer JDK?

Suppose a Java service connects to:

~~~text
Java application
       |
       | HTTPS
       v
https://inventory.internal.example:8443
       |
       v
TLS terminator / application server
~~~

On JDK 8, the system runs normally. When moving to a JDK 17 image, the client reports:

~~~text
javax.net.ssl.SSLHandshakeException:
    PKIX path building failed:
    sun.security.provider.certpath.SunCertPathBuilderException:
    unable to find valid certification path to requested target
~~~

This indicates that Java has not found a **valid trusted certificate path** from the server certificate to a trust anchor accepted by the client. Specific causes can include:

- The old runtime had the enterprise's private root CA added, whereas the new JDK image does not.
- The Java app reads a different truststore due to changed paths, JVM properties, or container mounts.
- The server sends only the leaf certificate, omitting intermediate CAs.
- A TLS inspection proxy re-issues the certificate under an enterprise CA not yet trusted by the client.
- A load balancer returns different certificate chains depending on SNI or backend nodes.
- A certificate in the chain has expired or fails constraints.
- The newer JDK enforces stronger key/signature algorithm policies.

Do not fix this by accepting every certificate. First determine **what the server actually sends** and **what the Java client actually trusts**.

## 2. Basic concepts

| Term | Explanation |
|---|---|
| Leaf / end-entity / server certificate | Certificate verifying the identity of a server or TLS endpoint |
| Intermediate CA certificate | Certificate of an intermediate CA signed by a higher-level CA |
| Root CA certificate | Usually a self-signed CA certificate at the top of a PKI hierarchy |
| Certificate chain | Sequence of certificates forming a validation link from the leaf to a higher CA |
| Trust anchor | A CA certificate or trust point explicitly accepted by the validator |
| Truststore | Source of trust anchors that a TrustManager can use |
| Keystore | Key/certificate store; typically holds private keys and identity certificates |
| JSSE | Java Secure Socket Extension, Java's TLS/SSL mechanism |
| PKIX | X.509 certificate path construction and validation model |
| TrustManager | Java-side component validating certificates presented by the peer |
| KeyManager | Component selecting Java's certificate/private key when identity presentation is required |
| Hostname verification | Checking whether the certificate represents the hostname/IP called by the client |

**A truststore is not meant to contain every leaf certificate the application ever encounters.** Normally, a truststore contains approved root CAs or other policy-defined trust anchors. The server supplies the leaf and intermediates so the client can build a path to one of those anchors.

**A Root CA is not always the only trust anchor that can be configured.** Choosing an intermediate CA as a specific trust anchor within a bounded trust scope is also technically possible; however, that choice must follow PKI policy and must not be done arbitrarily to bypass errors.

**Keystores and truststores differ in role** even though both can be represented as `JKS` or `PKCS12`. An identity keystore typically contains private keys; a truststore contains public trust material. If the client only needs to authenticate the server via one-way HTTPS, a client private key is usually unnecessary.

## 3. How does a certificate chain work?

A basic chain:

~~~text
                Java client
              +------------------+
              |  Truststore      |
              |  Root CA (R)     |   <- Approved trust anchor
              +------------------+
                        ^
                        | Intermediate signed by Root
                        |
              +------------------+
              | Intermediate CA  |
              |       (I)        |
              +------------------+
                        ^
                        | Leaf signed by Intermediate
                        |
              +------------------+
              | Server cert (S)  |
              | SAN: api.example |
              +------------------+
                        ^
                        |
                 TLS server sends
                 [ S, I ] typically
~~~

When establishing a TLS connection, the server typically sends **the leaf certificate along with the required intermediate certificates**. The server is not required to send the root certificate; sending a root does not make it trusted by the client. Trust must originate from the client's configuration.

To obtain a valid path, the validator must verify cryptographic signature links between certificates; simultaneously, it must check validity, CA constraints, key usage, algorithm policies, and related PKIX rules.

Example of a missing intermediate:

~~~text
Server provides:      [Leaf S]
Client truststore:    [Root R]
Missing link:         [Intermediate I]

S -> I -> R cannot be built if client lacks I
~~~

Some environments have caches or mechanisms to fetch intermediates via AIA, yet **you must not assume Java always downloads intermediates automatically from URLs inside certificates**. The server must be configured with the complete chain appropriate for the deployment.

### 3.1. A certificate chain is not an arbitrary list

A server may send multiple certificates without all of them forming a valid trust path. There could be an intermediate with the wrong issuer, an expired certificate, a cross-signed chain differing from Java's trust anchors, or unsuitable extensions. You cannot simply count certificates and conclude the chain is valid.

### 3.2. Cross-signed certificates

An intermediate or root may appear in multiple certificate paths because it is cross-signed. Depending on the anchor set and path-building policy, Java may choose a different path than OpenSSL or a browser. When investigating, record subject, issuer, serial, SKI/AKI, and fingerprints rather than relying solely on the subject name.

## 4. Distinguishing trust validation, hostname verification, and TLS negotiation

These three check groups are distinct:

1. **PKIX/trust validation:** Does the certificate have a trust path to a valid trust anchor?
2. **Hostname verification:** Does that certificate match the endpoint name requested by the client?
3. **TLS negotiation:** Can both sides agree on TLS version, cipher suite, key exchange, and signature scheme?

Additionally, the HTTPS response or business authorization are separate verification layers after TLS is established.

~~~text
Java client
   |
   | DNS / TCP / Proxy / SNI
   v
TLS endpoint
   |
   | TLS handshake, certificate chain
   v
JSSE TrustManager + PKIX
   |
   | Build path, verify signatures, constraints, policy
   v
Endpoint identity check
   |
   | Match DNS/IP against SAN
   v
HTTP request / response
~~~

This is a logical model, not the exact order of every implementation in TLS 1.2/1.3.

**Adding a root CA does not fix a hostname mismatch.** Changing a hostname does not make an expired certificate valid either. Lowering the security policy does not make an unapproved private CA trustworthy. Diagnose the exact error layer.

## 5. Where does Java get the default truststore?

In a typical JDK using SunJSSE, the default truststore involves the paths:

~~~text
<JAVA_HOME>/lib/security/jssecacerts
<JAVA_HOME>/lib/security/cacerts
~~~

Typically `jssecacerts` may take precedence if it exists, followed by `cacerts`. This is environment/provider-specific behavior; do not generalize that every vendor and SSL provider behaves identically.

Sources of trust material can vary:

- Default `cacerts` packaged with the JDK image.
- `jssecacerts` added by the platform.
- A file specified by `javax.net.ssl.trustStore`.
- Trust material loaded programmatically by the application into `SSLContext`.
- A PKCS#11 provider, HSM, or dedicated certificate management platform.
- Framework-, HTTP client-, JDBC driver-, or application server-specific trust configuration.

A JDK runtime inside a container may use a different CA set than Java on a laptop or Windows/Linux host. **The OS CA store does not automatically equal `cacerts` in every Java distribution.** Some vendors/images have synchronization mechanisms, but you must verify what is actually present.

### 5.1. Checking the running Java executable

~~~bash
java -version
~~~

The command above only shows `java` in that shell environment. If the system runs under systemd, Docker, Kubernetes, or a Gradle Test task, identify the specific process's JVM executable. `JAVA_HOME` in your terminal may not be the failing service's runtime.

### 5.2. Viewing the default truststore

~~~bash
keytool -list -cacerts
~~~

With detailed information:

~~~bash
keytool -list -v -cacerts
~~~

If using a separate file:

~~~bash
keytool -list -v \
  -keystore /opt/app/config/client-truststore.p12 \
  -storetype PKCS12
~~~

The command may prompt for a password. Never write passwords to logs, repositories, CI output, or public documentation.

### 5.3. JKS and PKCS12

Many legacy systems use `JKS`; modern JDKs use `PKCS12` as the default keystore type in many contexts. **Do not guess the store type solely from the file extension** or assume `cacerts` across all vendors always shares one format. Verify the actual file and configure `-storetype` or `javax.net.ssl.trustStoreType`.

## 6. A custom truststore does not automatically merge with cacerts

Suppose the application calls:

~~~text
1. https://billing.internal.example  (private enterprise CA)
2. https://public-payments.example   (public CA)
~~~

If the application creates a custom SSLContext trusting only the enterprise root, internal endpoints may succeed while public endpoints fail even though public CAs exist in default JDK `cacerts`.

| Configuration | Can trust | Risk |
|---|---|---|
| Default JDK cacerts | Public roots bundled with runtime | Usually does not include private enterprise roots |
| Custom truststore containing only private root | Services issued by private CA | Loses trust in public CAs if replacing default |
| Managed truststore with appropriate roots | Approved trust domains | Requires explicit CA updates and auditing |
| Per-integration SSLContext | Separates trust policies by partner | Requires accurate configuration/testing |

**Configuring a custom truststore typically replaces the trust anchor set of the corresponding TrustManager; do not assume it appends to `cacerts`.** If both private and public roots are needed, design an approved CA set or use separate SSL contexts with clear boundaries and controls.

Do not copy an entire `cacerts` file from an old JDK to a new image just to keep “everything as before”. A newer JDK release may have removed unsafe CAs or updated policies to reduce risk.

## 7. Checks for X.509 certificates

### 7.1. Validity period

A certificate has `Not Before` and `Not After`. A leaf or intermediate certificate that is not yet valid or has expired can be rejected. An inaccurate system/VM/container clock can also cause `CertificateNotYetValidException` or `CertificateExpiredException`.

### 7.2. Signatures and path building

The client must verify the leaf's signature using the issuer's public key, checking intermediates similarly up to the trust anchor. Subject/issuer names help find candidates, yet do not replace cryptographic signature validation.

### 7.3. BasicConstraints and KeyUsage

Certificates acting as CAs must satisfy constraints permitting certificate signing, such as `BasicConstraints CA=true` and `keyCertSign` when the relevant extension is present/required. Path length constraints may also limit CA depth.

### 7.4. ExtendedKeyUsage

If a certificate declares Extended Key Usage, the purpose must match: a TLS server leaf typically uses `serverAuth`; an mTLS client certificate may require `clientAuth`. You cannot reuse a certificate signed for a different purpose merely because its chain to a root is valid.

### 7.5. Signature algorithms and key sizes

JDK cryptographic policies can reject chains using weak signatures/hashes or inadequate key sizes. Specific conditions depend on JDK version/vendor, provider, and security policy; do not lump every SHA-1 certificate into the exact same case.

### 7.6. Revocation

CRL and OCSP can be used to check certificate revocation. Capabilities, defaults, and enforcement depend on JSSE/PKIX configuration. Do not assume Java and browsers use the same revocation mechanisms. Nor should you disable revocation checking to bypass infrastructure errors without reviewing security requirements.

## 8. Hostname verification: a trusted root is still not enough

Suppose the leaf certificate has Subject Alternative Name:

~~~text
DNS: billing.internal.example
~~~

Yet the Java client calls:

~~~text
https://inventory.internal.example
~~~

The chain can be completely valid and the root trusted by the truststore, yet hostname verification still fails.

Cases to examine:

- The DNS hostname in the URL must match a DNS SAN per the HTTPS client's rules.
- If the client connects by IP literal, an appropriate IP-type SAN is required.
- Wildcard certificates have bounded scope and do not match arbitrary subdomain levels.
- Do not rely on Common Name (CN) as a substitute for SAN; fallback behavior differs across libraries/JDKs.
- SNI can cause a reverse proxy to return a different certificate when one IP serves multiple hostnames.

Error example:

~~~text
javax.net.ssl.SSLHandshakeException:
No subject alternative DNS name matching
inventory.internal.example found
~~~

The fix is to issue a certificate with the right SAN, call the proper hostname, or fix the gateway/SNI. **Do not fix it by disabling HostnameVerifier**, because doing so removes verification of the server's true identity.

## 9. Common impacts of upgrading the JDK

### 9.1. Changes in the root CA set

A new JDK release or container image may add, remove, or update trust anchors. Internal roots that the team manually imported into the old JDK do not automatically appear in the new image.

### 9.2. Changes in algorithm policies

Java security configuration contains properties such as:

~~~text
jdk.certpath.disabledAlgorithms
jdk.tls.disabledAlgorithms
~~~

They can affect certificate acceptance or TLS negotiation. If an `Algorithm constraints check failed` error occurs, find the offending certificate/key/signature and update the server configuration or certificate chain. **Do not disable all disabled algorithms** to bypass the error.

### 9.3. Changes in TLS version and cipher policy

Legacy servers supporting only weak protocols/ciphers may be rejected by a newer JDK even when the certificate chain is valid. This is a negotiation failure, not necessarily a root CA error.

### 9.4. Different runtime images and security providers

JDK vendor, patch level, JSSE/PKCS#11 provider, FIPS policy, or custom runtime image can affect truststore loading and accepted algorithms. Record **Java vendor/version, security properties, provider, truststore path, and file content**.

### 9.5. Frameworks creating their own SSLContext

An HTTP client, gRPC client, JDBC driver, or application server may use its own trust configuration instead of default JSSE properties. Merely changing `-Djavax.net.ssl.trustStore` may not affect it.

## 10. Common TLS errors and how to distinguish them

| Symptom | Possible cause | Check first |
|---|---|---|
| `PKIX path building failed` / `unable to find valid certification path` | Cannot build a path to a trust anchor under config/policy | Actual truststore, CAs, intermediate chain, proxy |
| `PKIX path validation failed` | Path was considered but failed validation rules | Validity, key usage, constraints, revocation |
| `CertificateExpiredException` | A required certificate has expired | Leaf/intermediate dates and clock |
| `CertificateNotYetValidException` | Certificate is not yet valid or clock is wrong | Time sync, validity |
| `No subject alternative ... matching` | Hostname does not match certificate | SAN, URL, DNS, SNI |
| `Algorithm constraints check failed` | Incompatible key/signature/policy | Security properties and chain |
| `handshake_failure` / `protocol_version` | TLS version/cipher/key exchange mismatch | Server/client TLS capabilities |
| `Received fatal alert: bad_certificate` | Peer rejected certificate; often check mTLS | Server logs, client identity chain |
| `trustAnchors parameter must be non-empty` | Usable trust anchors are empty in config | Store path/type/content and custom TrustManager |
| `Keystore was tampered with, or password was incorrect` | Mismatched password/type/file | Store validity and secret |
| Fails only in container | Image, truststore mount, or proxy differs from local | Process environment and endpoint chain |

An `SSLHandshakeException` can wrap many different causes. Read `Caused by` and debug logs rather than searching for a single message and blindly running a certificate import command from the Internet.

## 11. Inspecting the server's certificate chain with OpenSSL

In environments with OpenSSL:

~~~bash
openssl s_client \
  -connect api.example.com:443 \
  -servername api.example.com \
  -showcerts
~~~

Notes:

- `-connect` specifies the endpoint and port.
- `-servername` sends TLS SNI; very important when the server uses virtual hosts.
- `-showcerts` displays the certificates sent by the peer during the handshake.
- Inspect subject, issuer, SAN, dates, and intermediate certificates.
- The command returning certificate data does not mean it validated hostname and PKIX under the same policy as Java.
- An environment using a proxy may present a different certificate than the public endpoint.

For a leaf certificate saved in PEM format:

~~~bash
openssl x509 -in server-leaf.pem \
  -noout -subject -issuer -dates -fingerprint -sha256
~~~

To inspect detailed extensions:

~~~bash
openssl x509 -in server-leaf.pem -noout -text
~~~

The SHA-256 fingerprint helps cross-check the received certificate's identity. **Do not treat seeing a fingerprint over the suspect connection itself as proof of trust**; for a new trust anchor, verify it via a trusted PKI source and independent channel.

### 11.1. Using keytool to inspect an endpoint

Some JDK releases support:

~~~bash
keytool -printcert \
  -sslserver api.example.com:443 \
  -rfc
~~~

This command is useful for observing certificates from an endpoint with a JDK tool. However, it does not replace testing the connection with the actual application and SSLContext.

### 11.2. OpenSSL and Java results can differ

OpenSSL may use the OS CA store, policies, and a path builder different from Java. Furthermore, not every OpenSSL command performs hostname verification by default. A successful OpenSSL command is not enough to prove the Java client will succeed.

## 12. Inspecting the exact truststore Java uses

During migration, accurately answer these questions:

1. Which Java executable is the process running?
2. Which specific truststore file is being loaded?
3. Does that file exist in the container/VM and does the process have read permission?
4. Is the store type `PKCS12`, `JKS`, or another provider?
5. Which approved trust anchors are inside the truststore?
6. Do the CA fingerprints match PKI policy?
7. Does the Java app have a custom `SSLContext` or framework trust bundle?
8. Is a proxy, service mesh, or TLS terminator re-issuing certificates?
9. Which hostname/SNI is the client connecting to?
10. Do local tests run with the same Java image/truststore as production?

Example inspecting a store with alias `company-root-ca`:

~~~bash
keytool -list -v \
  -keystore /opt/app/config/client-truststore.p12 \
  -storetype PKCS12 \
  -alias company-root-ca
~~~

The alias name is merely an administrative label and does not determine signature validity. When checking, verify the certificate fingerprint and CA purpose.

If the `javax.net.ssl.trustStore` property points to a nonexistent path, exact behavior can depend on the JSSE/provider and how the context is initialized. Do not assume it will safely fall back to `cacerts`. Check logs, file existence, and how many anchors the trust manager actually loaded.

## 13. Creating a custom truststore to trust a private CA

If an internal endpoint uses an enterprise CA and the client must trust it, obtain the approved root/intermediate trust anchor from **your organization's PKI system**.

Example importing a CA certificate into a custom PKCS12 truststore:

~~~bash
keytool -importcert \
  -alias company-root-ca \
  -file company-root-ca.pem \
  -keystore client-truststore.p12 \
  -storetype PKCS12
~~~

When run, keytool typically prompts for a password and/or confirmation to trust the certificate. Do not use `-noprompt` to bypass certificate source verification without a controlled automated workflow.

Re-read the store:

~~~bash
keytool -list -v \
  -keystore client-truststore.p12 \
  -storetype PKCS12 \
  -alias company-root-ca
~~~

Steps to perform before promoting to production:

- Cross-check the SHA-256 fingerprint with an independent, trusted source.
- Identify the CA owner and permitted certificate issuance scope.
- Check validity and CA constraints.
- Manage the file via configuration management or approved images/versions.
- Establish rotation, rollback, and audit procedures.
- Grant only necessary read permissions to the Java process.
- Do not unnecessarily copy private keys into the client truststore.

### 13.1. Should you import the root or the intermediate?

Normally the server must send the intermediate, while the truststore holds a trust anchor such as an approved root CA. Designing to trust an intermediate as a dedicated anchor is possible, yet that is an intentional trust-boundary change, not a quick trick for every PKIX error.

### 13.2. Why should you not arbitrarily import leaf server certificates?

Importing a leaf may get one connection working yet breaks when the leaf renews or rotates, can mask a server missing intermediates, and risks trusting a certificate fetched from an unauthenticated path. Certificate/public-key pinning is suitable only if the project explicitly designs and manages rotation.

### 13.3. Why should you not manually modify the JDK's cacerts directly?

Adding CAs directly into the JDK image can be lost during upgrades, affects multiple applications sharing the runtime, is hard to audit, and is non-reproducible across CI/production. Some environments intentionally manage roots at the platform image level; in that case, ensure the image is governed by versioning and explicit change control.

## 14. Using JVM system properties to specify a truststore

In many applications relying on JSSE defaults, you can configure:

~~~bash
java \
  -Djavax.net.ssl.trustStore=/opt/app/config/client-truststore.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -jar app.jar
~~~

The `javax.net.ssl.trustStorePassword` property exists to supply the store password when needed. However, **putting a real password on the command line can expose it via process listings, shell history, or logs**. Choose an appropriate platform secret-handling solution, such as programmatic configuration or protected secret management and lifecycle.

Example property names, not a deployment command with real secrets:

~~~text
javax.net.ssl.trustStore=/opt/app/config/client-truststore.p12
javax.net.ssl.trustStoreType=PKCS12
javax.net.ssl.trustStorePassword=<supplied securely>
~~~

Do not assume every HTTP library uses these properties. If the application creates custom trust managers or framework-specific SSL configuration, update that exact configuration point.

## 15. Java example creating an SSLContext from a PKCS12 truststore

Sometimes an application wants an outbound client to use custom trust anchors, separate from the default JSSE context. For example:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class ClientTlsConfiguration {

    private ClientTlsConfiguration() {
    }

    public static SSLContext createContext(
            Path truststorePath, char[] password) throws Exception {

        KeyStore truststore = KeyStore.getInstance("PKCS12");

        try (InputStream input = Files.newInputStream(truststorePath)) {
            truststore.load(input, password);
        }

        TrustManagerFactory factory = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());

        factory.init(truststore);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, factory.getTrustManagers(), null);

        return context;
    }
}
~~~

Steps:

1. `KeyStore` reads the PKCS12 store.
2. `TrustManagerFactory` creates trust managers from the anchors in the store.
3. `SSLContext` is configured with those trust managers.
4. `null` for the KeyManager parameter means the example does not yet supply a client identity, so it is not an mTLS client configuration.
5. This context **does not automatically include default cacerts**.
6. Successful context creation does not prove the endpoint certificate and hostname will be valid.

If the password is held in a `char[]`, you can zero out the array contents after initialization when appropriate for the lifecycle, though you should not claim that guarantees every secret copy in memory is erased.

### 15.1. Using with Java HttpClient from Java 11

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import javax.net.ssl.SSLContext;

public final class TlsClientExample {

    public static void main(String[] args) throws Exception {
        String path = System.getenv("CLIENT_TRUSTSTORE_PATH");
        String password = System.getenv("CLIENT_TRUSTSTORE_PASSWORD");

        if (path == null || password == null) {
            throw new IllegalStateException("Missing TLS configuration");
        }

        SSLContext context = ClientTlsConfiguration.createContext(
                Path.of(path), password.toCharArray());

        HttpClient client = HttpClient.newBuilder()
                .sslContext(context)
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.internal.example/health"))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        System.out.println(response.statusCode());
    }
}
~~~

This example is for understanding the API; production requires proper secret sources, timeouts, error handling, monitoring, and endpoint protections matching actual requirements. Environment variables are used for illustrative simplicity, not as an optimal security solution for every environment.

**Do not write an `X509TrustManager` that accepts every chain** just to make the example run. If the application has a PKIX failure, find the root cause in trust/path validation.

## 16. mTLS: truststore and keystore on both sides

In **mutual TLS (mTLS)**, the server also requires the client to present a certificate. Thus there are at least two authentication flows:

~~~text
Java client                               TLS server
-----------                               ----------

Client truststore   -- trust server CA --> Server identity cert
                                              + private key

Client identity cert + private key         Server truststore
                    -- trust client CA -->   validates client cert
~~~

| Side | Store | Role |
|---|---|---|
| Java client | Truststore | Trusts the CA issuing the server certificate |
| Java client | Identity keystore | Presents the client certificate and private key |
| TLS server | Identity keystore | Presents the server certificate and private key |
| TLS server | Truststore | Trusts the CA issuing the client certificate |

If the server rejects the client cert with `bad_certificate`, modifying the **client truststore** will likely have no effect: the client truststore authenticates the server, whereas the server truststore decides whether to trust the client cert.

Determine which peer rejected, that peer's certificate chain, KeyUsage/EKU, validity, and algorithm policy. Do not assume every PKIX error happens on the Java client side.

The identity keystore's private key must be protected via access controls, secret management, and rotation processes. Public root CA certificates can be distributed more broadly, yet **trusting** a root must be controlled.

## 17. Configuring the server to send complete intermediate certificates

When the server chain lacks intermediates, the proper fix usually lies on the **server or TLS terminator**, not asking every Java client to import the leaf.

Basic requirements:

- Present a leaf certificate matching the served hostname.
- Send the necessary intermediate certificates.
- Use the private key matching the leaf.
- Do not place the root private key into the TLS deployment.
- Ensure SAN, validity, EKU, and key usage are correct.
- Configure policy-compliant TLS protocols/ciphers.
- Serve a consistent chain across nodes and availability zones.
- Maintain a renewal/rotation plan before expiration.

Some server products use the concept of a `fullchain.pem` file containing leaf + intermediate. Exact names and formats depend on the server; read deployment documentation and inspect the actual sent chain with `openssl s_client -showcerts` or an equivalent tool.

### 17.1. SNI and load balancers

If multiple virtual hosts share an IP, SNI determines which certificate is selected. Connections without SNI or with another name may receive a mismatched default certificate. When investigating, use the exact hostname the Java client calls, not just a direct IP connection.

### 17.2. Gateways and service meshes

If TLS terminates at an ingress/gateway/sidecar, the certificate may not live inside the backend application. Identify the TLS termination point, certificate rotation controller, and where the chain is actually configured.

## 18. Corporate proxies and TLS inspection

An outbound proxy may re-sign server certificates under an enterprise CA in a TLS inspection model:

~~~text
Java client
   |
   | TLS to certificate issued by corporate proxy
   v
Corporate TLS inspection proxy
   |
   | Separate TLS to public destination
   v
Internet HTTPS endpoint
~~~

Java may see an entirely different chain than a browser or an OpenSSL command run on a laptop bypassing the proxy.

In that case:

- The client truststore needs to trust the enterprise CA per organizational policy.
- Certificates presented by the proxy must have a SAN matching the hostname.
- The proxy must have its own process to validate upstream servers.
- The proxy's trust anchor widens certificate issuance scope, so auditing is required.
- Debugging must run along the actual network path and runtime environment.

Do not work around TLS inspection by disabling hostname checks or trusting all certificates. If the proxy is corporate-managed, certificates and CAs must be provided through a trusted management channel.

## 19. Certificate rotation: leaf, intermediate, and root

A JDK upgrade may coincide with certificate rotation:

- Leaf renewal.
- Transition to a new intermediate CA.
- Replacing a root or changing a cross-sign path.
- Old root removed from the truststore.
- Signature algorithms upgraded.
- Internal PKI modifying SAN/EKU configuration.
- mTLS client certificates re-issued.

A rotation process should consider:

1. Inventory endpoints, current chains, owning CAs, and expiration dates.
2. Prepare new trust anchors and distribute per policy before changing chains if needed.
3. Verify both old and new JDKs during the overlap support period.
4. Deploy the new server certificate/chain as planned.
5. Check each load balancer node and hostname/SNI.
6. Monitor handshake errors, mTLS alerts, and latency.
7. Remove old trust anchors only when no consumers remain.
8. Save evidence and a rollback plan.

Do not rely on adding each leaf certificate to every client's truststore on every renewal. That increases operational overhead and easily misses nodes.

## 20. Debugging JSSE and certificate path validation

You can enable JSSE debugging to observe the trust manager and handshake:

~~~bash
java \
  -Djavax.net.debug=ssl,handshake,trustmanager \
  -jar app.jar
~~~

You can also inspect certificate path validation activity:

~~~bash
java \
  -Djava.security.debug=certpath \
  -jar app.jar
~~~

Debug output depends on the JDK/provider/options. Logs can reveal endpoint names, certificate details, or sensitive information; enable only under control, retain only as long as needed, and restrict access.

Error-reading workflow:

1. Record the exact JDK version, vendor, and JVM flags.
2. Identify which truststore the TrustManager loaded.
3. Inspect the chain the server presents over the exact SNI/hostname/proxy.
4. Check the leaf issuer and intermediates.
5. Check the root CA/trust anchor inside the store.
6. Read validity, CA constraints, algorithm policies, and revocation errors.
7. Separate hostname mismatch from trust path failure.
8. For mTLS, identify which authentication direction was rejected.
9. Re-run the exact client under the target runtime after fixing.

**A successful OpenSSL check does not replace a Java test.** Java may use a different store, provider, algorithm restrictions, SNI, or hostname rules; conversely, OpenSSL without proper verification flags can give non-equivalent conclusions.

## 21. Typical migration scenarios

### A. Public HTTPS succeeds but a private endpoint fails with PKIX

**Likely cause:** The new JDK has public roots, yet lacks the enterprise root CA previously added manually to the old JDK.

**Fix:** Verify the root's certificate fingerprint with the PKI team, build/distribute an appropriate truststore, verify the path, and re-read the truststore inside the running image itself.

### B. Root CA is present yet chain building still fails

**Likely cause:** The server does not send the intermediate, the chain is wrong, or the path builder lacks required data.

**Fix:** Check with `openssl s_client -showcerts` and fix the TLS server/gateway to send the right intermediates. Do not default to importing the leaf.

### C. Error when accessing by IP instead of DNS

**Likely cause:** The leaf has a DNS SAN but no IP SAN, or the client calls a hostname different from the certificate.

**Fix:** Use the proper DNS endpoint or issue a certificate with the required SAN. Do not disable hostname verification.

### D. Newer JDK reports an invalid algorithm

**Likely cause:** Key size/signature algorithm or path validation policy differs from the baseline.

**Fix:** Replace the certificate/chain/cipher to comply with policy. Do not weaken overall JVM security settings.

### E. App trusts only the private CA and loses ability to call public gateways

**Likely cause:** A custom TrustManager uses a store containing only the private root, completely replacing default roots.

**Fix:** Separate SSLContexts per integration or construct an appropriate, approved anchor set.

### F. mTLS encounters `bad_certificate` when server authenticates client

**Likely cause:** The server-side truststore does not trust the client CA, the client sends an incomplete chain, or the cert has the wrong EKU or is expired.

**Fix:** Investigate server logs as well as the client identity keystore/server truststore. Do not just add the CA to the client truststore.

### G. Fails only in production container

**Likely cause:** Image/truststore mount, proxy, SNI, runtime JDK, or outbound routing differs from local/CI.

**Fix:** Compare file hashes, CA aliases, process JVM flags, and the certificate chain observed directly from the production network path.

## 22. Controlled migration workflow

### Step 1: Inventory TLS connections

List outbound HTTPS, gRPC, JDBC over TLS, Kafka, AMQP, LDAP/LDAPS, service meshes, proxies, and mTLS. Identify which client libraries use default JSSE and which have custom truststores.

### Step 2: Capture baseline

Save JDK distribution/version, truststore path/type/fingerprints, endpoint certificate chains, SAN/validity, proxy settings, and test results. Do not save private keys or passwords in the report.

### Step 3: Compare policies before/after upgrading JDK

Identify differences in CA roots, `java.security` policies, enabled TLS protocols/ciphers, security providers, and JDK images. Avoid changing multiple variables simultaneously when possible.

### Step 4: Diagnose at the right layer

| Root error | Priority place to fix |
|---|---|
| Missing intermediate | TLS server, gateway, or load balancer |
| Missing approved private trust anchor | Java client truststore / platform CA distribution |
| Hostname/SAN mismatch | Certificate issuance or URL/SNI |
| Expired certificate | PKI certificate renewal |
| Weak algorithm | CA/server TLS configuration |
| Wrong truststore file/type | Application/container deployment config |
| Wrong mTLS client identity | Client keystore and server-side trust |
| Untrusted corporate proxy CA | Enterprise PKI policy and client trust config |

### Step 5: Test under the exact runtime

Run the Java client inside the target image/container/VM and through the exact DNS/proxy/load balancer. Test successful endpoints as well as wrong SAN, missing chain, and certificate rotation cases in an appropriate test environment.

### Step 6: Deploy and observe

Monitor `SSLHandshakeException`, TLS alerts, HTTP errors, connection retries, latency, and business impact. Ensure rollback remains viable while retaining all necessary chains/trust anchors.

### Step 7: Clean up workarounds, record ownership

Remove temporary trust entries, flags, and unused configurations. Clearly assign CA owners, rotation schedules, truststore storage locations, deployment procedures, and contacts for upcoming certificate expirations.

## 23. Anti-patterns to avoid

### 23.1. Trust-all TrustManager

A TrustManager that leaves `checkServerTrusted` empty or accepts every chain removes certificate identity validation. It may make requests “work” yet increases man-in-the-middle risk and does not prove TLS is properly configured at all.

### 23.2. HostnameVerifier always returning true

Disabling hostname verification lets the client accept another endpoint's certificate. This is not a safe way to fix `No subject alternative DNS name matching ...`.

### 23.3. Importing certificates from an endpoint without verifying the source

If the connection was intercepted, copying the certificate presented by that endpoint and trusting it directly can put a forged certificate into the truststore. CAs must be verified through an independent PKI channel.

### 23.4. Copying all old cacerts to a new JDK

This can preserve roots whose trust was revoked or that violate new policies. Manage CAs accurately instead of disabling security improvements shipped with the JDK.

### 23.5. Clearing all disabledAlgorithms

Do not weaken algorithms across the entire JVM just to connect to one outdated server. Fix the certificate/key/TLS configuration according to policy.

### 23.6. Hardcoding passwords or private keys

Do not store secrets in Java source, Git, command logs, or screenshots. Truststore public certificates and identity keystore private keys differ in sensitivity, yet both need appropriate file management policies.

### 23.7. Testing with a browser and concluding Java is fine

Browsers may use OS trust roots or different intermediate caches; Java has its own cacerts and providers. Test with the exact intended Java client/runtime.

## 24. Suggested test matrix

| Scenario | Expected outcome |
|---|---|
| Public HTTPS endpoint with valid chain | Java client trusts via approved public roots |
| Enterprise PKI endpoint | Java client trusts approved internal CA |
| Server missing intermediate | Error detected and chain fixed at server |
| Wrong certificate SAN | Client rejects properly |
| Expired leaf | Client rejects properly |
| Weak key/signature | Rejected per security policy |
| Connection through corporate proxy | Enterprise trust policy and SAN are verified |
| mTLS with valid client certificate | Mutual authentication succeeds |
| mTLS with invalid client certificate | Server rejects |
| Server certificate rotation | Client continues operating per trust overlap plan |
| Load balancer failover | Backends provide proper chains |
| Container missing truststore mount | Misconfiguration detected, without trust-all or uncontrolled fallback |

The results table should record PASS, FAIL, BLOCKED, or NOT RUN, along with test timestamp, JDK image, endpoint, fingerprint, and relevant logs. Do not mark PASS simply because the application started successfully without executing a TLS request.

## 25. Key principles to remember

- **A truststore is the set of trust anchors used by the client**, not the server's entire certificate chain.
- **Root CAs and intermediate CAs serve different roles.** Roots usually reside in the client truststore; the server should send the leaf and needed intermediates.
- **Sending a root from the server does not make the root trusted.** Trust must come from client policy.
- **PKIX path validation, hostname verification, and TLS negotiation are semantically independent.** Read errors at the exact stage.
- **A JDK upgrade can change the root set, algorithm policy, providers, and runtime image.** Do not draw conclusions from a green build.
- **A custom truststore can replace default cacerts.** Consider public/private trust domains.
- **mTLS involves both a client identity keystore and a server-side truststore.** Distinguish the authentication direction.
- **Missing intermediates should usually be fixed at the server/gateway**, rather than importing the leaf across all clients as a workaround.
- **Never use trust-all or disable hostname verification.** That removes safety guardrails rather than fixing TLS errors.
- **Verify CA fingerprints through a trusted source** before adding a trust anchor.
- **Debugging must run in the actual network/runtime context**, including proxies, SNI, and containers.
- **Certificate lifecycles require owners, rotation, and rollback.** Trust is not a configure-once-and-forget setting.

In Java Advance Compatibility Migration, TLS connectivity cannot be evaluated solely by whether the application compiles with a new JDK. You must verify the server certificate chain, Java trust anchors, hostname, cryptographic policy, and actual connection path. A sustainable migration must **keep strict TLS verification intact**, fix errors on the proper server/client side, and provision trust material through reliable governance, rather than trading security validation for compatibility.
