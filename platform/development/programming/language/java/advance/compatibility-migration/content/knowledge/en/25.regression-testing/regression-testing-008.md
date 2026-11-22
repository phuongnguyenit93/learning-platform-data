# Testing TLS, Certificates, and External Service Integrations

In **Java Advance Compatibility Migration**, a system can build successfully and pass unit tests on a new JDK yet fail when connecting to HTTPS endpoints, databases, message brokers, or partner APIs. The root cause does not necessarily lie in business code: the **TLS protocol**, cipher suites, certificate chain, hostname verification, truststore, mutual TLS, or TLS provider can change across JDKs, security patches, dependencies, and container images.

This lesson belongs to the **Regression Testing** chapter. Its goal is to design a test suite that catches TLS issues before deployment, without weakening certificate verification to force tests to pass, and provides evidence that external services continue to operate properly on both the baseline JDK and the target JDK.

The examples use Java 17 and Java 21 for illustration. In a real system, protocol policies, ciphers, root CAs, disabled algorithms, and provider behavior must be verified against the **actual JDK vendor, release, patch level, and runtime image in use**.

## 1. Why Does TLS Need a Separate Regression Test Suite?

Upgrading a JDK can produce observable changes:

- The new JDK contains a different set of root CAs in its truststore.
- **jdk.tls.disabledAlgorithms** or **jdk.certpath.disabledAlgorithms** policies are updated.
- An external endpoint only supports outdated TLS versions or signature algorithms.
- The server is missing an intermediate certificate, yet a developer machine still connects due to its own truststore/cache.
- The client switches from hostname to IP, causing the **Subject Alternative Name (SAN)** to no longer match.
- A new HTTP client uses a different SSL provider.
- The client certificate for **mutual TLS (mTLS)** is not selected properly after a configuration change.
- A gateway, proxy, or service mesh starts terminating TLS at a different layer.
- ALPN/SNI behavior changes and gRPC/HTTP2 stops working.
- A partner certificate is rotated simultaneously with the JDK upgrade.
- The new container image lacks CA/truststore/secret mounts that existed on the old image.

A TLS failure can increase retries, fill up queues, trip circuit breakers, or cause business transactions to fail. Therefore, **a passing build** and **mocked HTTP 200** are not enough to prove integration readiness.

### 1.1. Connection Layers to Distinguish

~~~text
Java application
       |
       +--> DNS, proxy, routing, TCP
       |
       +--> TLS handshake
       |       |
       |       +--> Protocol/cipher negotiation
       |       +--> Server certificate chain
       |       +--> Trust anchor / path validation
       |       +--> Hostname verification
       |       +--> Client certificate when using mTLS
       |       +--> ALPN/SNI
       |
       +--> HTTP/JDBC/LDAP/Kafka/gRPC
       |
       +--> Application authentication/authorization
       |
       +--> Business response
~~~

HTTP **401/403** is usually an application-layer error after TLS may have already succeeded. **PKIX path building failed** typically appears during the certificate verification stage.

### 1.2. Regression Goals

| Goal | What must be proven | Example |
|---|---|---|
| Confidentiality | Connections use TLS per policy | No automatic fallback to plaintext |
| Server identity | Certificate chain and SAN are valid | Correct partner DNS |
| Client identity | mTLS presents the right certificate | Partner accepts client |
| Protocol | Permitted TLS version/cipher is negotiated | TLS 1.2/1.3 per policy |
| Business integration | Request/response contract has no unexpected changes | REST, JDBC, Kafka |
| Security rejection | Untrusted certificates are rejected | Negative tests |
| Resilience | Timeouts/retries do not cause duplicate side effects | Idempotency |
| Operations | Telemetry, expiry tracking, and rotation runbooks exist | Alerts and rollback |

Compatibility does not mean re-enabling every old protocol. If a new JDK rejects weak algorithms under security policy, that result may be valid and require coordinating a partner upgrade rather than disabling verification.

## 2. JSSE and TLS Providers in Java

**Java Secure Socket Extension (JSSE)** provides the APIs:

- **SSLContext**: configures TLS and key/trust managers.
- **SSLSocket/SSLEngine**: executes TLS connections.
- **SSLParameters**: sets protocols, cipher suites, and endpoint identification.
- **SSLSession**: observes the negotiated protocol/cipher.
- **TrustManagerFactory**: builds trust managers from a truststore.
- **KeyManagerFactory**: selects the private key/certificate for client or server identity.
- **KeyStore**: holds certificates and can hold private key entries.
- **HttpsURLConnection** or **java.net.http.HttpClient**: HTTP clients using TLS.

Libraries such as Apache HttpClient, OkHttp, gRPC/Netty, Kafka, or JDBC drivers may use JSSE or a different provider/configuration. Do not assume changing a single system property affects every outbound connection identically.

### 2.1. Truststore and Keystore

| Component | Typical data | Role |
|---|---|---|
| Truststore | CA certificates/trust anchors | Verifies the peer |
| Client keystore | Private key and client certificate chain | Presents client identity |
| Server leaf certificate | SAN, validity, key usage, issuer | Verifies server identity |
| Intermediate CA | Intermediate certificate | Builds the trust path |
| Root CA | Approved trust anchor | Terminates the trust path |
| CRL/OCSP | Revocation status | Checks revoked certificates if configured |

A client does not need a client private key for standard one-way HTTPS. Conversely, mTLS requires client key material and the server must accept the corresponding certificate.

### 2.2. Endpoint Authentication Differs from Authorization

A valid certificate for an endpoint does not automatically grant business permissions. A request can complete TLS yet receive HTTP 403 due to scope/account permissions. Similarly, mTLS authenticates the certificate identity, while the application may still perform separate authorization checks.

## 3. TLS Versions, Cipher Suites, and Security Policy

Both ends of a connection must find an intersection between protocols/ciphers that both sides support **and** that policy permits.

- **TLS 1.2** is widely supported.
- **TLS 1.3** is available in many modern JDKs.
- **TLS 1.0/1.1** are deprecated protocols and are typically disabled.

A cipher may appear in the **supported** list yet not be in the **enabled** list, or be rejected by security constraints.

Important security properties:

~~~text
jdk.tls.disabledAlgorithms
jdk.certpath.disabledAlgorithms
~~~

The default contents depend on vendor/version/patch. Do not re-enable weak algorithms JVM-wide just to make one legacy integration work. If an exception is needed, there must be a security owner, risk analysis, and deprecation deadline.

### 3.1. Factors That Cause Handshake Failures

| Factor | Error example | Verification step |
|---|---|---|
| TLS version | protocol_version | Client/server enabled protocols |
| Cipher suite | handshake_failure | Cipher overlap and security constraints |
| Certificate signature | Algorithm constrained | Signature algorithm, key size |
| Certificate path | PKIX failure | Truststore, intermediate, issuer |
| Hostname | SAN mismatch | URL, DNS name, IP SAN |
| SNI | Server returns wrong certificate | Virtual host and hostname |
| ALPN | HTTP/2/gRPC fails to run | Client/server protocol negotiation |
| mTLS identity | bad_certificate | Client keystore, alias, chain |
| Revocation | CertPath validation | CRL/OCSP policy/network |

**handshake_failure** alone does not prove the cause is a cipher mismatch. Inspect the exception chain and peer logs.

## 4. Certificate Chain and Hostname Verification

An HTTPS client typically verifies:

1. The certificate chain provided by the server.
2. Signatures and X.509 constraints.
3. The trust path to a valid trust anchor.
4. Certificate validity and key usages.
5. Whether the hostname/IP in the URL matches the SAN.
6. Revocation status if the corresponding policy mechanism is enabled.

~~~text
Leaf: api.partner.example
          |
          v
Intermediate CA
          |
          v
Root CA in approved truststore
~~~

The server usually sends the leaf and required intermediates; it does not necessarily send the root. A server missing an intermediate might be accepted by machine A yet fail on machine B due to a different truststore/cache.

### 4.1. Untrusted CA and SAN Mismatch Are Different

**Untrusted CA:** the chain does not lead to an accepted trust anchor.

**SAN mismatch:** the chain may be valid, yet the certificate does not represent the hostname the client is connecting to.

For example, calling **https://10.0.0.8** when the certificate only has DNS SAN **api.partner.example** may be rejected even if that IP points to the right server. The fix is to use the proper DNS name or issue a certificate with an appropriate IP SAN, not to disable hostname verification.

### 4.2. Testing SANs

Test cases should include:

- Exact valid DNS hostname.
- DNS alias not covered by the certificate.
- Valid and invalid wildcard hostnames.
- IP literal if the application actually connects by IP.
- Redirect to a different domain.
- Proxy/load balancer returning its own certificate.
- Server selecting certificates via SNI.

Do not rely on Common Name (CN) fallback, as behavior can vary across clients/providers.

### 4.3. Validity and Clock

A certificate has **notBefore** and **notAfter**. A container with an inaccurate system clock can report a certificate as not yet valid or expired. Check time synchronization; changing the log-display timezone does not resolve certificate validity.

### 4.4. Key Usage, EKU, and CA Constraints

Beyond expiration dates, consider:

- Server Authentication/Client Authentication EKU.
- Key Usage.
- Basic Constraints.
- Signature algorithm and key size.
- Intermediate CA chain.
- Name Constraints or policy constraints if present.

A properly signed certificate is not automatically suitable for every TLS purpose.

## 5. Default Truststore and Custom Truststores

Many JDKs include a CA truststore in the runtime image, typically at a path like:

~~~text
$JAVA_HOME/lib/security/cacerts
~~~

The CA list, path, and provider can vary across JDK vendors and container images.

Use keytool to inspect:

~~~bash
keytool -list -cacerts
~~~

Custom truststore:

~~~bash
keytool -list -v \
  -keystore /secure/config/partner-truststore.p12 \
  -storetype PKCS12
~~~

The tool may prompt for a password. Do not put production passwords on the command line or in public logs.

### 5.1. Importing a Test CA into a Custom Truststore

~~~bash
keytool -importcert \
  -alias local-test-ca \
  -file test-ca.pem \
  -keystore test-truststore.p12 \
  -storetype PKCS12
~~~

Import only verified test CAs. Never grab a certificate from a failing connection and trust it without verifying its fingerprint/provenance through an independent channel.

### 5.2. Configuring the Default JSSE Truststore

Some clients using the default SSLContext can read:

~~~text
-Djavax.net.ssl.trustStore=/secure/config/partner-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Passwords should be managed via a secret manager or appropriate mechanism. Not every client library uses the default truststore. A custom SSLContext or a Netty/Kafka client with its own configuration may ignore these properties.

### 5.3. Avoid Overly Broad Trust

If you replace the JVM-wide default truststore with a file containing only a private CA, other HTTPS integrations may lose trust in public CAs. Conversely, copying an entire developer laptop `cacerts` into a container can add trust anchors outside security policy.

Prefer per-client/partner truststores or an explicitly managed organizational trust bundle.

## 6. Creating SSLContext for Java HttpClient

Java 17+ example specifying a truststore for an HTTPS client:

~~~java
package example.tls;

import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.time.Duration;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class PartnerClient {
    public static SSLContext contextFromTruststore(
            Path path, char[] password) throws Exception {

        KeyStore trust = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(path)) {
            trust.load(in, password);
        }

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm()
        );
        tmf.init(trust);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, tmf.getTrustManagers(), new SecureRandom());
        return context;
    }

    public static String get(URI endpoint, SSLContext context)
            throws Exception {

        HttpClient client = HttpClient.newBuilder()
            .sslContext(context)
            .connectTimeout(Duration.ofSeconds(5))
            .build();

        HttpRequest request = HttpRequest.newBuilder(endpoint)
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString()
        );

        response.sslSession().ifPresent(session -> {
            System.out.println("TLS: " + session.getProtocol());
            System.out.println("Cipher: " + session.getCipherSuite());
        });

        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                "Unexpected HTTP status: " + response.statusCode()
            );
        }
        return response.body();
    }
}
~~~

This snippet illustrates a custom truststore without disabling certificate path/hostname verification. Endpoints, paths, and passwords must be managed securely.

### 6.1. Benefits of Per-Client SSLContext

- Partner A's truststore does not affect partner B.
- Tests can use an isolated CA.
- No need to modify JVM-wide trust configuration.
- Easy to document each integration's policy explicitly.
- Certificate rotation can be designed per scope.

In production, reuse the HttpClient/connection pool according to an appropriate lifecycle; there is no need to create a new client per request.

### 6.2. Do Not Use Trust-All

A custom trust manager that always accepts every certificate, or a hostname verifier that always returns true, disables a vital part of TLS authentication. If a regression test passes only thanks to a bypass, that test does not prove the endpoint is secure.

### 6.3. Do Not Hardcode TLS 1.2 Without Reason

**SSLContext.getInstance("TLS")** lets the provider select configured enabled protocols. If the product has a specific protocol policy, inspect/configure it on the appropriate client. Do not pin exclusively to TLS 1.2 when TLS 1.3 support is desired unless explicitly required.

## 7. Mutual TLS and Client Certificates

In **mTLS**, server and client authenticate each other's certificates.

~~~text
Java client                       Partner server
    |                                   |
    |-- ClientHello ------------------->|
    |<-- Server certificate ------------|
    |-- Verify CA + hostname -----------|
    |<-- CertificateRequest ------------|
    |-- Client certificate + proof ---->|
    |<-- Verify client certificate -----|
    |======== TLS established =========|
    |-- Business request -------------->|
~~~

The client needs:

- A truststore to verify the server.
- A keystore with the private key/client certificate.
- A certificate with valid dates, EKU, and proper chain.
- The right alias if multiple key entries exist.
- The server trusting the client CA.
- A rotation/reload mechanism to switch certs without unplanned downtime.

### 7.1. mTLS SSLContext

~~~java
package example.tls;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class MutualTlsContexts {
    private static KeyStore load(Path path, char[] password)
            throws Exception {

        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(path)) {
            store.load(in, password);
        }
        return store;
    }

    public static SSLContext create(
            Path clientStorePath, char[] clientPassword,
            Path trustPath, char[] trustPassword) throws Exception {

        KeyStore identity = load(clientStorePath, clientPassword);
        KeyStore trust = load(trustPath, trustPassword);

        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
            KeyManagerFactory.getDefaultAlgorithm()
        );
        kmf.init(identity, clientPassword);

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm()
        );
        tmf.init(trust);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(
            kmf.getKeyManagers(), tmf.getTrustManagers(),
            new SecureRandom()
        );
        return context;
    }
}
~~~

This example uses the same password for the keystore and private key entry. Real systems may require two separate passwords and an appropriate secret provider.

### 7.2. Common mTLS Errors

- Failing to send a client certificate.
- Keystore has no private key entry.
- Wrong alias or password.
- Expired certificate.
- Client certificate lacks the proper usage.
- Server does not trust the new CA.
- Chain missing an intermediate.
- Key/signature algorithm unsupported by the provider.
- Old SSLContext/connection pool has not reloaded the new cert.
- mTLS succeeds, yet application authorization rejects the request.

### 7.3. Testing Certificate Rotation

~~~text
T0: Client uses cert A, server trusts A
T1: Server adds trust for cert/CA B
T2: Client switches to B
T3: New TLS connections use cert B
T4: Confirm all instances have switched
T5: Server removes trust for cert/CA A
~~~

Tests must observe new connections and certificate identity after rotation. Updating a secret file does not automatically guarantee the client has reloaded key material.

## 8. HTTPS and Other Integration Protocols

### 8.1. HTTPS/REST

Test:

- Endpoint DNS/port/SNI.
- Truststore/hostname verification.
- Protocol/cipher.
- Proxy, HTTP/2, and ALPN if used.
- HTTP request/response schema.
- OAuth/token scope after TLS.
- Timeouts, redirects, retries.
- mTLS when required.
- Certificate rotation and pooling.

### 8.2. JDBC

JDBC drivers typically have their own SSL settings. With PostgreSQL JDBC, **sslmode=verify-full** is the mode aimed at verifying the chain and hostname per driver documentation. An encryption-only mode does not automatically guarantee server identity.

Check the JDBC driver version and actual TLS settings. Test connection pools, database host failover, server certificate rotation, and mTLS if applicable.

### 8.3. Kafka/Message Brokers

Example Kafka SSL configuration:

~~~properties
security.protocol=SSL
ssl.truststore.location=/secure/kafka/truststore.p12
ssl.truststore.type=PKCS12
ssl.keystore.location=/secure/kafka/client.p12
ssl.keystore.type=PKCS12
~~~

This is not a complete production configuration; credentials/keystore passwords must be managed separately. For **SASL_SSL**, the authentication/configuration mechanism differs.

Test both bootstrap hosts and advertised broker hostnames; certificate SANs must match the hosts the client actually connects to. Test reconnects, consumer rebalancing, and certificate rotation.

### 8.4. LDAP/LDAPS

With LDAPS/StartTLS, test trust chains, SANs, domain controllers, referrals, and bind authentication. Do not fall back to plaintext if security policy requires TLS.

### 8.5. gRPC and HTTP/2

gRPC can rely on **ALPN** to negotiate HTTP/2. Netty may use the JDK or a native TLS provider. A succeeding REST GET does not prove a gRPC channel works.

Test the actual gRPC client library, SSL provider, ALPN, SNI, certificate identity, and application-level status.

### 8.6. SMTP/STARTTLS

When using STARTTLS, verify the client enforces upgrading to TLS if policy requires it. Do not allow connections to silently downgrade to plaintext.

### 8.7. Proxies and Service Mesh

~~~text
Java --TLS--> Partner directly

Java --CONNECT tunnel--> Proxy --TLS--> Partner

Java --TLS--> Gateway --TLS--> Partner
~~~

Each architecture has its own trust boundary. In a gateway-terminating-TLS model, Java verifies the gateway's certificate, while the gateway is responsible for the next hop. Do not use a Java→gateway result to claim that gateway→partner has been verified.

## 9. TLS Regression Matrix Across Old and New JDKs

| Case | Baseline JDK | Target JDK | Expectation |
|---|---|---|---|
| Trusted CA + matching SAN | Test | Test | Succeeds |
| Untrusted CA | Test | Test | Rejected |
| Hostname mismatch | Test | Test | Rejected |
| Expired certificate | Test | Test | Rejected |
| Not-yet-valid certificate | Test | Test | Rejected |
| Missing intermediate | Test | Test | Per chain/trust fixture |
| Valid client mTLS | Test | Test | Server accepts |
| Missing client cert | Test | Test | Server rejects when mTLS is required |
| Client cert with wrong CA/EKU | Test | Test | Server rejects |
| TLS 1.2 | Per policy | Per policy | Connects when allowed |
| TLS 1.3 | Per policy | Per policy | Connects when allowed |
| Weak protocol/cipher | Test | Test | Policy not loosened automatically |
| Certificate rotation | Test | Test | Switches over per plan |
| Proxy/SNI/ALPN | If used | If used | Correct route/protocol |
| Partner business contract | Test | Test | Accurate business outcome |
| Timeout/retry | Test | Test | Bounded and idempotent |

If a new security policy intentionally rejects a legacy endpoint, the test should not have its expected result altered to success at all costs. It must record this as a blocker requiring partner/security resolution.

## 10. Testing with a Local TLS Server and Private CA

Negative tests should use a server controlled by the testing team rather than sending adversarial requests to a production partner.

~~~text
Java test runner 17/21
          |
          +--> Valid TLS server
          +--> Untrusted CA server
          +--> Wrong SAN server
          +--> Expired cert server
          +--> mTLS-required server
          +--> Protocol policy test server
          |
          v
JUnit/integration assertions
~~~

You can use embedded Jetty/WireMock or Testcontainers with certificates signed by a test CA.

Fixtures include:

- A separately managed test CA and private key.
- A server certificate with a valid SAN.
- A certificate signed by another CA.
- A certificate with a wrong SAN.
- Expired/not-yet-valid certificates.
- Valid and invalid client certificates.
- Protocol/cipher configurations per security policy.

Do not place production private keys into the test repository. If storing test fixture keys in source control, ensure they are strictly for testing environments and create no production trust.

### 10.1. Testing Fail-Closed Behavior

With a server certificate signed by a CA not trusted by the client, the client must reject it. If the test still receives a business response, investigate whether the truststore was improperly broadened or verification was disabled.

### 10.2. Do Not Arbitrarily Modify Global SSLContext in Tests

A test that changes the JVM-wide truststore/default SSLContext can affect other tests and cause flakiness. Use an isolated SSLContext or a separate JVM process if global properties must be tested.

### 10.3. Tests Must Handle Certificate Validity in a Controlled Manner

Do not let test certificates accidentally expire after one year and break all of CI without explanation. Manage fixtures, validity windows, and renewal procedures; for negative expiry tests, generate or store fixtures deliberately.

## 11. JUnit 5 Example Verifying a TLS Session

Assume the test server is created and CI supplies the endpoint/truststore:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Set;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSession;
import org.junit.jupiter.api.Test;

final class PartnerTlsIT {
    @Test
    void validCertificateAndApprovedTlsMustWork()
            throws Exception {

        String url = System.getProperty("tls.test.endpoint");
        String store = System.getProperty("tls.test.truststore");
        String secret = System.getenv("TLS_TEST_STORE_PASSWORD");

        assertNotNull(url);
        assertNotNull(store);
        assertNotNull(secret);

        SSLContext context = PartnerClient.contextFromTruststore(
            Path.of(store), secret.toCharArray()
        );

        HttpClient client = HttpClient.newBuilder()
            .sslContext(context)
            .connectTimeout(Duration.ofSeconds(3))
            .build();

        HttpResponse<String> response = client.send(
            HttpRequest.newBuilder(URI.create(url))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build(),
            HttpResponse.BodyHandlers.ofString()
        );

        assertEquals(200, response.statusCode());

        SSLSession session = response.sslSession()
            .orElseThrow(() ->
                new AssertionError("Expected TLS session"));

        assertTrue(Set.of("TLSv1.2", "TLSv1.3")
            .contains(session.getProtocol()));
        assertNotNull(session.getCipherSuite());
    }
}
~~~

The accepted protocols in the example are merely an illustrative policy. If the endpoint requires TLS 1.3, assert per that contract. **PartnerClient** from the earlier section must be on the test classpath.

### 11.1. Negative Tests

For untrusted CA, wrong SAN, or expired certificate cases, tests expect TLS validation to fail. **SSLHandshakeException** may appear, though other transport/async layers can wrap the exception.

Do not assert exact JSSE exception message text unless the application intentionally guarantees a stable message. Inspect the appropriate exception type/cause and confirm that **no HTTP business response** was received from the untrusted connection.

## 12. Diagnosing with OpenSSL and keytool

### 12.1. Viewing the Certificate Chain with OpenSSL

~~~bash
openssl s_client \
  -connect api.partner.example:443 \
  -servername api.partner.example \
  -showcerts \
  -verify_return_error
~~~

**-servername** sends SNI so the server picks the right virtual host. The command reveals the certificate chain, negotiated protocol/cipher, and verification diagnostics.

**OpenSSL does not use the application's Java truststore by default.** OpenSSL succeeding while JSSE reports a PKIX error can still be the expected result of two differing trust configurations.

### 12.2. Inspecting TLS Versions

~~~bash
openssl s_client \
  -tls1_2 \
  -connect api.partner.example:443 \
  -servername api.partner.example
~~~

~~~bash
openssl s_client \
  -tls1_3 \
  -connect api.partner.example:443 \
  -servername api.partner.example
~~~

Results depend on the OpenSSL build and local security configuration, and do not replace testing with the target Java runtime.

### 12.3. Viewing Certificate Metadata

~~~bash
openssl x509 -in server.pem -noout -text
~~~

Check issuer, SAN, notBefore/notAfter, key usage, EKU, signature algorithm, and key size.

### 12.4. keytool Printing Server Certificates

~~~bash
keytool -printcert \
  -sslserver api.partner.example:443 \
  -rfc
~~~

Being able to print the certificate does not automatically prove a client with a custom SSLContext will trust that certificate. Test the actual handshake with the exact provider/path.

## 13. JSSE Debugging and Error Classification

Some JVM diagnostic properties:

~~~text
-Djavax.net.debug=ssl,handshake
-Djava.security.debug=certpath
~~~

Use in a controlled manner because logs can be large and contain sensitive details. Do not leave debugging enabled continuously in production without an explicit requirement.

### 13.1. Common Exceptions

| Symptom | Possible cause | Investigation |
|---|---|---|
| SSLHandshakeException | Handshake failed | Cause chain, peer logs |
| PKIX path building failed | Trust path invalid | CA/intermediate/truststore |
| CertPathValidatorException | Certificate failed policy | Validity, constraints, revocation |
| CertificateExpiredException | Expired | Validity/clock |
| CertificateNotYetValidException | Not yet valid | Validity/clock |
| No subject alternative names | SAN does not match | Hostname/IP |
| bad_certificate | Peer rejected certificate | mTLS/CA/EKU |
| handshake_failure | Negotiation failed | Protocol/cipher/cert/SNI |
| protocol_version | Protocol unsupported | Enabled protocols |
| No appropriate protocol | Local security policy rejected | Disabled algorithms |
| UnrecoverableKeyException | Cannot open key entry | Key password/alias |
| SocketTimeoutException | Timeout | TCP/handshake/response |
| ConnectException | Cannot connect TCP | DNS/port/firewall |

Not every **SSLHandshakeException** is caused by a certificate. It can also stem from protocol/cipher negotiation or peer policy.

### 13.2. Triage Sequence

1. Confirm hostname, port, route, and proxy.
2. Record JDK vendor/version/patch.
3. Record HTTP/JDBC/Kafka client and TLS provider.
4. Identify the exact SSLContext/truststore/keystore.
5. Inspect SAN, issuer, chain, and validity.
6. Compare enabled protocols/ciphers.
7. Inspect the exception cause chain and peer logs.
8. Re-run on baseline and target runtime images.
9. Fix the root cause without disabling security.
10. Re-run positive and negative regressions.

## 14. Certificate Revocation, CRL, and OCSP

Depending on security policy, the client may need to check whether a certificate has been revoked via CRL or OCSP. **Do not assume every JDK/client enables revocation checking by default in the same way.**

If revocation checking is mandatory, test:

- Proper CRL/OCSP configuration exists.
- Revocation responders are reachable via network/proxy.
- Revocation service timeouts/caching.
- Fail-open/fail-closed behavior when responders are unreachable.
- Which certificates in the chain are checked.
- Whether a fixture with a revoked certificate is rejected.

Merely setting a property without positive/negative tests does not prove the policy works.

## 15. Certificate Pinning and Rotation

Some clients pin a certificate fingerprint or public key. When a partner rotates certificates, the new certificate may be valid according to the CA yet fail to match the old pin.

Requirements:

- Define the pinned target: leaf certificate, SPKI/public key, or CA.
- Backup pin mechanism per policy.
- Overlap period trusting certificates A/B.
- Update clients before the partner switches certs.
- Rollback plan if the new pin is wrong.
- Positive/negative tests for certs A and B.

Do not silently remove pinning to get past a migration if it is an intentional security control.

## 16. Timeouts, Retries, and Idempotency

Not every network error happens before the server processes the request:

~~~text
Client sends payment request
       |
       v
Server has recorded the transaction
       |
       v
Connection drops before response reaches client
       |
       v
Client receives I/O timeout
~~~

Automatically retrying without an idempotency key can create duplicate transactions.

Approaches:

- Distinguish pre-request handshake failures from post-send read timeouts.
- Bound retries with backoff/jitter.
- Do not infinitely retry deterministic trust/SAN validation errors.
- Use an idempotency key for operations with side effects if the API supports it.
- Test circuit-breaker/retry behavior against controlled endpoints.
- Do not create real transactions to test negative connectivity.

## 17. Runtime Container and Network Path

Local Java21 may pass while container Java21 fails because:

- JDK vendor/patch inside the image differs.
- CA bundle differs.
- Truststore mount path is wrong.
- Client uses a different default context.
- DNS/proxy/SNI routing differs.
- Gateway certificate differs.
- System clock is wrong.
- Image is missing secrets or permissions.
- Network policy blocks CRL/OCSP.
- HTTP library/provider differs on the classpath.

Therefore, **production-like runtime image tests** are necessary, not just running unit tests on the CI host.

### 17.1. Illustrative CI Matrix

~~~text
PR verification
    |
    +--> JDK baseline:
    |      - Unit tests
    |      - Valid TLS fixture
    |      - Invalid CA/SAN/expiry fixtures
    |      - mTLS tests when needed
    |
    +--> JDK target:
           - Same test suite
           - Same TLS policy assertions

Pre-release
    |
    +--> Docker image smoke
    +--> Staging partner connectivity
    +--> Proxy/SNI/ALPN
    +--> Certificate rotation rehearsal
    +--> Business contract tests
~~~

A staging partner downtime may be an environment incident, but it must not be worked around by bypassing certificate validation. Classify failures and assign owners clearly.

## 18. Observing TLS After Rollout

Monitor:

- Handshake failures by endpoint.
- Server/client mTLS certificate expiry.
- Connection timeouts.
- Negotiated protocol/cipher (if telemetry provides it).
- Partner API errors.
- Retries and circuit breakers.
- Queue backlogs caused by connectivity failures.
- Business success rate and latency.
- Metric availability to avoid mistaking missing data for zero errors.

Do not log private keys, passwords, or tokens. Certificate fingerprints/aliases and expiry can aid diagnostics per policy provided no unnecessary sensitive data is exposed.

## 19. Scenario: New JDK Rejects a Legacy Endpoint

**Symptom:** Baseline JDK connects fine; target JDK encounters a handshake failure.

Investigate:

1. Do both JDKs use the same hostname/port/proxy?
2. Do security policy/disabledAlgorithms differ?
3. Does the server have overlapping TLS 1.2/1.3 and ciphers?
4. Are the chain/signature/key lengths compliant?
5. Do truststores differ?
6. Does SNI select the right certificate?
7. Does the partner need to upgrade protocols/certificates?
8. Has a security owner approved a temporary exception?

Do not re-enable deprecated algorithms JVM-wide by default.

## 20. Scenario: Container PKIX Fails While Local Passes

Possibilities:

- Container truststore is missing a private CA.
- A local developer manually imported the CA.
- Production proxy swaps the certificate.
- Server sends a different chain by region/SNI.
- Secret volume is unmounted or store type is wrong.
- Runtime image uses a different vendor.

Resolution: capture the chain along the exact network path, verify the truststore the Java process is actually using, inspect SANs and CAs from an independent source, and adjust configuration cleanly. Do not arbitrarily copy an entire `cacerts` from a laptop.

## 21. Scenario: mTLS Fails After Rotation

Possibilities:

- Some pods still use the old secret.
- SSLContext/connection pool has not reloaded.
- Client alias is wrong.
- New cert is missing ClientAuth EKU.
- Server does not yet trust the new CA on all backends.
- Client chain is missing an intermediate.
- Rotation overlap window closed too early.

Inspect cert fingerprint/expiry, key entry, alias, secret version, connection refresh, and confirm with the partner. Do not share private keys in chat/email for debugging.

## 22. Scenario: gRPC Fails Even Though HTTPS GET Succeeds

If REST HTTPS returns 200 yet gRPC fails:

- Did ALPN negotiate HTTP/2?
- Is gRPC using the JDK provider or native provider?
- Does the proxy support HTTP/2 on the right hop?
- Do SNI and certificate share the same route?
- Are channel credentials and timeouts accurate?
- What gRPC status/metadata does the server return?

Test the actual gRPC client/channel; do not draw conclusions from a Java HttpClient GET result.

## 23. Release Gates for TLS Regression

### Gate A — Inventory

- List of TLS integrations/owners exists.
- Baseline/target JDK and client versions documented.
- Truststores, client certificates, and security policy documented.
- Certificate expiry and rotation owners assigned.

**GO:** boundaries requiring protection are known.

### Gate B — Controlled Tests

- Trusted endpoint accepted.
- Untrusted CA rejected.
- Hostname mismatch rejected.
- Expired certificate rejected.
- mTLS positive/negative tests pass if used.
- Protocol/cipher policy preserved.
- No trust-all or disable-hostname-verification.

**GO:** JSSE/client genuinely verifies the peer properly.

### Gate C — Integration

- Runtime image connects to staging partner.
- Proxy/SNI/ALPN work properly.
- Business contract works properly.
- Timeout/retry/idempotency tested.
- Certificate rotation path has evidence.
- Monitoring/alerts ready.

**GO:** integration works in a production-like environment.

### Gate D — Canary

- Target JDK running in canary.
- TLS handshake error rate stable.
- SLO/business metrics met.
- Runbooks and partner contacts in place.
- Rollback/forward-fix plan ready for trust bundles/client certs.

**GO:** traffic ramp-up permitted as planned.

### Gate E — Cleanup

- Remove temporary workarounds.
- Retire old trust anchors after the overlap window per policy.
- Update certificate expiry alerts.
- Archive test results and owners.
- Clean up test secrets per procedure.

## 24. Common Anti-Patterns

### 24.1. Only Checking HTTP 200

Fails to detect trust bypasses. **Solution:** add negative CA/SAN tests.

### 24.2. Using Trust-All to Fix PKIX

Breaks peer authentication. **Solution:** verify the chain/truststore properly.

### 24.3. Disabling Hostname Verification to Use an IP

Masks SAN errors and opens MITM risk. **Solution:** use an appropriate hostname/certificate.

### 24.4. Confusing OpenSSL Trust with Java Trust

The two tools have different trust/configurations. **Solution:** run the real Java client.

### 24.5. Importing Arbitrary Certificates into cacerts

Widens trust uncontrollably. **Solution:** verify fingerprint/origin and manage CAs.

### 24.6. Enabling TLS 1.0/1.1 JVM-Wide

Weakens security posture. **Solution:** partner upgrade or controlled security decision.

### 24.7. Not Rehearsing Certificate Rotation

Application runs on cert A yet crashes when cert B takes effect. **Solution:** rotation tests and overlap.

### 24.8. Retrying Certificate Errors Infinitely

Configuration errors do not self-heal. **Solution:** classify exceptions, bound retries.

### 24.9. Confusing HTTP 403 with a TLS Failure

Fixes the wrong layer. **Solution:** separate handshake from application auth.

### 24.10. Not Testing Production-Like Containers

CAs, DNS, mounts, and providers differ from the CI host. **Solution:** smoke test in the real image.

### 24.11. Logging Passwords/Private Keys

Leaks secrets. **Solution:** secret manager and log sanitization.

### 24.12. Treating a Successful Handshake as a Successful Integration

Business protocols/schemas can still fail. **Solution:** test the request/response contract after TLS.

## 25. Migration Completion Checklist

### JDK and TLS Settings

- [ ] Baseline and target JDK vendor/version/patch recorded.
- [ ] Client library and TLS provider recorded.
- [ ] Actual truststore/keystore in use identified.
- [ ] Protocol/cipher/algorithm policy defined.
- [ ] DNS/SNI/ALPN and proxy tested where relevant.
- [ ] Secrets are absent from source, logs, or public commands.

### Certificate Validation

- [ ] Trusted CA + matching SAN succeeds.
- [ ] Untrusted CA is rejected.
- [ ] Hostname mismatch is rejected.
- [ ] Expired/not-yet-valid certificates are rejected.
- [ ] Key usage/EKU appropriate.
- [ ] Revocation tested per policy.
- [ ] Certificate rotation rehearsed.
- [ ] No trust-all/hostname-verifier bypasses exist.

### Integration

- [ ] REST/JDBC/Kafka/LDAPS/gRPC tested where used.
- [ ] Business status/schema/auth accurate after TLS.
- [ ] Retry/idempotency verified.
- [ ] Staging partner tested.
- [ ] Production-like container smoke test executed.
- [ ] Both baseline and target JDKs tested.
- [ ] Negative tests cause no impact to production partners.

### Operations

- [ ] Handshake failure metrics/alerts in place.
- [ ] Expiry and rotation owners assigned.
- [ ] Partner contacts and incident runbooks in place.
- [ ] Rollback policy in place for truststores/client certificates.
- [ ] Evidence recorded by JDK/image/certificate identity.
- [ ] Security exceptions have approvers and deprecation deadlines.

## 26. Regression Report Template

~~~text
Test ID:
Integration/Partner:
Owner:
Endpoint DNS and port:
Proxy/Network path:
JDK baseline:
JDK target:
JDK vendor/build:
Client library and TLS provider:
Truststore source (no password):
Client cert alias/fingerprint if mTLS:
Allowed protocol/cipher policy:
Negotiated protocol/cipher:
Server certificate issuer/SAN/expiry:
Positive certificate test:
Untrusted CA test:
Hostname mismatch test:
Expired cert test:
mTLS tests:
Rotation test:
Business contract test:
Timeout/retry test:
Exception category:
SLO/Telemetry:
Evidence:
Security approval:
GO/NO-GO:
~~~

A result marked PASS without JDK, truststore, certificate identity, and endpoint route provides weak evidence when investigating after rotation or a JDK update.

## 27. Official Reference Documentation

- **JSSE Reference Guide:** https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html
- **SSLContext API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLContext.html
- **SSLParameters API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLParameters.html
- **SSLSession API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLSession.html
- **Java HttpClient API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html
- **TrustManagerFactory API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html
- **KeyManagerFactory API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html
- **KeyStore API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.html
- **keytool command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html
- **OpenSSL s_client:** https://docs.openssl.org/master/man1/openssl-s_client/
- **PostgreSQL JDBC SSL:** https://jdbc.postgresql.org/documentation/ssl/
- **Kafka security documentation:** https://kafka.apache.org/documentation/#security
- **TLS 1.3, RFC 8446:** https://www.rfc-editor.org/rfc/rfc8446

JDK and library releases may continue updating security defaults. When applying to a real project, verify policies and documentation against the exact deployed runtime.

---

**Conclusion:** Testing TLS and certificates is an indispensable part of **Java migration regression testing**. An application that builds successfully is not guaranteed to remain connected to external systems. A reliable test suite must verify both positive trust and negative trust, inspect certificate chains/SANs, TLS protocols/ciphers, mTLS, certificate rotation, and application contracts across both JDKs along with a production-like runtime image. When failures occur, resolve the proper trust boundary and coordinate with partners according to security policy, rather than disabling certificate verification to make tests green.
