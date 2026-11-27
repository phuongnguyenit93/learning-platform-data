# Securing HTTPS Connections and Verifying Certificates

Spring Data Elasticsearch communicates with Elasticsearch through an HTTP client. When a cluster has TLS enabled, the application must connect over HTTPS and verify the server certificate. HTTPS encrypts data in transit, while certificate validation lets the application know it is connecting to the trusted server.

Simply changing the URL from `http` to `https` is not enough if the JVM does not trust the CA that signed the Elasticsearch certificate, the certificate is expired, the hostname does not match a Subject Alternative Name (SAN), or the certificate chain is incomplete. Disabling hostname verification or using a trust-all `SSLContext` may make connections work during testing, but leaves the application vulnerable to server spoofing and man-in-the-middle attacks.

This lesson explains TLS, the trust chain, hostname verification, preparing a CA/truststore, configuring Spring Data Elasticsearch and the Elasticsearch Java API Client, mutual TLS (mTLS), managing certificate rotation, testing connections, and troubleshooting common errors.

## 1. What Does HTTPS Protect?

HTTP sends requests and responses unencrypted at the transport layer. If a connection traverses an untrusted network, anyone able to observe or intercept traffic can read the data or tamper with the content in transit.

HTTPS uses TLS to provide the following key properties:

- **Confidentiality**: encrypts exchanged content so third parties cannot read data in transit.
- **Integrity**: detects data modification during transmission.
- **Server authentication**: verifies the server based on its certificate and a CA chain trusted by the client.
- **Client authentication (optional)**: with mutual TLS, the server also requires the client to present a certificate to authenticate the application's identity.

In a Spring Data Elasticsearch application, data crossing the connection can include:

- Documents being indexed or updated.
- Queries, filters, and aggregations.
- Username/password or API keys in HTTP headers.
- Search results, metadata, and errors.
- Administrative information if the application is granted corresponding privileges.

HTTPS protects data in transit. It does not replace authentication, authorization, role-based access control, network segmentation, or encryption of data at rest on disk.

## 2. TLS Handshake and Certificate Chain

When a client opens an HTTPS connection, the TLS handshake takes place before any HTTP request is sent.

Simplified flow:

~~~text
Spring Data Elasticsearch application
              |
              | 1. ClientHello
              v
       Elasticsearch endpoint
              |
              | 2. Server certificate chain
              v
     JVM certificate validation
              |
              | 3. Hostname verification
              v
       TLS session established
              |
              | 4. Encrypted HTTP request
              v
          Elasticsearch
~~~

The client checks the following key details:

1. Whether the certificate is within its validity period.
2. Whether the certificate chain leads back to a trust anchor trusted by the client.
3. Whether the certificate signature and algorithms are valid.
4. Whether the certificate is valid for server authentication usage.
5. Whether the hostname in the URL matches a SAN in the certificate.
6. Whether the TLS version and cipher suite are supported by both sides.

If any verification step fails, the client should reject the handshake. Verification failures should never be turned into an unverified connection.

### 2.1. Certificate chain

A certificate chain typically has the following structure:

~~~text
Root CA
   |
   +-- Intermediate CA
           |
           +-- Elasticsearch server certificate
~~~

The server certificate is usually signed by an intermediate CA. The intermediate CA is signed by a root CA. The client typically stores the root CA or trusted internal CA in its truststore; the server must send all intermediate certificates needed for the client to build the chain.

Key concepts:

- **Leaf/server certificate**: the certificate representing the Elasticsearch hostname.
- **Intermediate CA**: an intermediate CA that signs server certificates or subordinate CAs.
- **Root CA**: the trust anchor trusted by the client.
- **Truststore**: where the client stores CAs/certificates used to verify the server.
- **Keystore**: where the application stores its own private key and certificate when client authentication is needed.

Do not confuse a truststore with a keystore. The truststore answers the question "Which CAs does the application trust?". The keystore answers the question "Which private key/certificate does the application hold to present to the peer?".

### 2.2. Self-signed certificates and internal CAs

In development environments, Elasticsearch may use a self-signed certificate or a certificate issued by an internal CA. The JVM does not automatically trust a custom CA just because the certificate was sent by the server during the handshake.

There are two common approaches:

- Import the CA certificate into the truststore used by the application.
- Use a truststore managed and distributed to applications by the platform or organization.

Prefer trusting the issuing CA rather than trusting the leaf certificate if infrastructure reissues certificates periodically. For a self-signed certificate, that certificate itself can act as the trust anchor, but its fingerprint and rotation must be managed carefully.

Do not download a certificate over an unauthenticated connection and trust it immediately without verifying its source/fingerprint through a trusted channel.

## 3. Hostname Verification and Subject Alternative Name

A valid certificate chain alone is not enough. The client must verify that the certificate was issued for the hostname the application is connecting to.

For example, the application calls:

~~~text
https://es-prod.internal.example:9200
~~~

The server certificate must contain the matching hostname in its Subject Alternative Name, for example:

~~~text
DNS:es-prod.internal.example
~~~

If the application connects by IP:

~~~text
https://10.20.30.40:9200
~~~

The certificate needs a corresponding IP SAN, for example:

~~~text
IP Address:10.20.30.40
~~~

SAN is the modern standard used to validate DNS names and IP addresses. Do not rely on the legacy Common Name (CN) as a substitute for SAN.

Hostname mismatch errors can occur when:

- The certificate only has a SAN for a DNS name, but the application connects by IP.
- The application uses an alias different from the hostname in the certificate.
- A load balancer/proxy returns the certificate of another endpoint.
- The certificate was created before the current DNS endpoint existed.
- The application connects directly to a node while the certificate only contains the load balancer's SAN.

The proper solution is to issue a certificate with SANs covering the hostnames/IPs the client actually uses, or change the URL to use a hostname already present in the SAN. Do not disable hostname verification to bypass a mismatch.

### 3.1. SNI

Server Name Indication (SNI) allows the client to send the hostname in the TLS ClientHello. A proxy or load balancer can use SNI to select the appropriate certificate when multiple hostnames share the same IP address.

If the client connects by IP, the server may fail to select the certificate for the intended hostname. Use a DNS hostname that matches the certificate and the endpoint's SNI configuration.

## 4. Ensuring the Elasticsearch Endpoint Uses HTTPS

The application needs to use an HTTPS endpoint:

~~~text
https://elasticsearch.example.internal:9200
~~~

If the cluster only enables HTTP, an HTTPS client cannot complete the handshake. If the cluster enables TLS but the client still calls HTTP, the connection may be rejected or return a protocol error.

Verify these components:

- Elasticsearch HTTP TLS is enabled.
- The server certificate and private key are configured properly.
- The server sends the full required certificate chain.
- The port and proxy endpoint are correct.
- DNS resolves to the intended server.
- Network policy allows the application to reach the HTTPS port.
- The URL in Spring configuration uses the `https` scheme.

For self-managed Elasticsearch, HTTP TLS settings are usually in the node configuration, such as `xpack.security.http.ssl.*` settings. Setting names and certificate provisioning methods depend on the Elasticsearch version and deployment method. Follow the security documentation for your exact cluster version.

Managed Elasticsearch services may enable HTTPS by default and provide a CA or specific trust instructions. In that case, use the endpoint and CA published by the provider through a trusted administrative channel.

## 5. Preparing a Truststore for the JVM

If Elasticsearch uses a CA not present in the JVM's default truststore, the application needs a truststore containing the appropriate CA.

For example, the organization provides a CA file:

~~~text
config/
  certs/
    elasticsearch-root-ca.crt
~~~

You can create a PKCS12 truststore using `keytool`:

~~~bash
keytool -importcert \
  -alias elasticsearch-root-ca \
  -file config/certs/elasticsearch-root-ca.crt \
  -keystore config/certs/elasticsearch-truststore.p12 \
  -storetype PKCS12
~~~

`keytool` will prompt for the truststore password and confirmation to trust the certificate. Before importing, verify the CA fingerprint through a trusted channel:

~~~bash
keytool -printcert -file config/certs/elasticsearch-root-ca.crt
~~~

List the contents of the truststore:

~~~bash
keytool -list \
  -v \
  -keystore config/certs/elasticsearch-truststore.p12 \
  -storetype PKCS12
~~~

Important notes:

- Use the CA certificate for the right environment.
- Do not put the server's private key into the client's truststore.
- Protect the truststore file and its password.
- Do not commit real passwords to Git.
- Do not copy a production truststore into public images or uncontrolled artifacts.
- Verify that the truststore contains the expected alias and required CA chain.

### 5.1. PEM or PKCS12?

PEM is a text format commonly used for certificates and keys. PKCS12 is a binary container that can hold certificates and private keys.

Some client APIs accept an `SSLContext` directly, while some APIs or tools allow configuring PEM. How Spring Boot/Spring Data supports them depends on the version and HTTP client used.

If the application's configuration API expects a Java `KeyStore`, PKCS12 is usually a practical choice. You can use `keytool` to import a PEM CA into a PKCS12 truststore as shown above.

### 5.2. Default JVM truststore vs. dedicated truststore

You can install a CA into the default JVM truststore, but this affects every application running on that JRE and is harder to control when different services require different CAs.

A dedicated truststore for Elasticsearch ensures:

- Only this application trusts the designated CA.
- Rotation can be rolled out independently.
- Trust for other TLS connections is unaffected.
- Management inside containers or secret mounts is easier.

If you use a dedicated truststore, make sure the Elasticsearch client actually uses the `SSLContext` created from that truststore.

## 6. Creating an SSLContext with a Truststore in Java

A Java `SSLContext` can be created from a truststore containing the CA.

Example:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;

import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class ElasticsearchSslContexts {

    private ElasticsearchSslContexts() {
    }

    public static SSLContext fromTrustStore(
            Path trustStorePath,
            char[] trustStorePassword) throws Exception {

        KeyStore trustStore = KeyStore.getInstance("PKCS12");

        try (InputStream input =
                 Files.newInputStream(trustStorePath)) {
            trustStore.load(input, trustStorePassword);
        }

        TrustManagerFactory trustManagerFactory =
            TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
            );

        trustManagerFactory.init(trustStore);

        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(
            null,
            trustManagerFactory.getTrustManagers(),
            new SecureRandom()
        );

        return sslContext;
    }
}
~~~

Explanation:

- `KeyStore` reads the truststore file.
- `TrustManagerFactory` creates trust managers from the stored CAs.
- `SSLContext` uses those trust managers to verify the server certificate.
- No custom `HostnameVerifier` is passed here; hostname verification must remain enabled on the HTTP client.

The example above does not load a client certificate. It only configures client-side trust to verify the server.

In a real application, do not hard-code passwords in source code. Read them from a secret manager or protected environment, convert to a `char` array where possible, and do not log their values.

## 7. Configuring the Spring Data Elasticsearch Imperative Client

Spring Data Elasticsearch provides `ClientConfiguration` to configure endpoints, TLS, and authentication. Exact configuration details depend on the Spring Data Elasticsearch version and the underlying client transport.

Example using the `ClientConfiguration` API common in Spring Data Elasticsearch 5.x:

~~~java
import javax.net.ssl.SSLContext;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;

@Configuration
public class ElasticsearchClientConfig
        extends ElasticsearchConfiguration {

    private final SSLContext sslContext;

    public ElasticsearchClientConfig(SSLContext sslContext) {
        this.sslContext = sslContext;
    }

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo("es-prod.internal.example:9200")
            .usingSsl(sslContext)
            .withBasicAuth(
                System.getenv("ES_USERNAME"),
                System.getenv("ES_PASSWORD")
            )
            .build();
    }
}
~~~

Meaning:

- `connectedTo` takes host and port, without a scheme in typical `ClientConfiguration` usage.
- `usingSsl(sslContext)` enables TLS with the prepared trust configuration.
- `withBasicAuth` adds HTTP Basic Authentication.
- Spring Data creates the client/transport based on this configuration.

Package names, superclasses, methods, and overloads may vary between minor versions. Check the Javadoc for `ClientConfiguration`, `ElasticsearchConfiguration`, and your actual dependencies before applying.

If you use another configuration API or Spring Boot auto-configuration, do not register a second client without knowing which client is used by repositories/`Operations`. Ensure both repositories and `ElasticsearchOperations` use the client with proper TLS.

### 7.1. Using default JVM trust

If the certificate is signed by a CA already in the default JVM truststore, you can configure TLS without creating a custom truststore:

~~~java
ClientConfiguration.builder()
    .connectedTo("es-prod.internal.example:9200")
    .usingSsl()
    .build();
~~~

This uses the runtime/client's default trust configuration. It must still verify the certificate chain and hostname. Do not use `usingSsl()` assuming every CA is trusted.

### 7.2. Configuring the endpoint via properties

You can externalize the hostname, port, and connection details into configuration:

~~~yaml
app:
  elasticsearch:
    host: es-prod.internal.example
    port: 9200
    tls:
      enabled: true
      trust-store: /run/secrets/elasticsearch-truststore.p12
~~~

Truststore passwords, usernames, and passwords should be supplied via a secret manager or managed environment variables. Do not store production secrets in committed YAML files.

If Spring Boot auto-configuration is used, verify which TLS properties are supported by the exact Boot version you are running. Do not assume an SSL bundle property or truststore path has the same name across all versions.

## 8. Using Elasticsearch Java API Client Directly

If the application creates an `ElasticsearchClient` directly instead of using the Spring Data-configured client, you must ensure the HTTP transport is also configured for TLS.

The Elasticsearch Java API Client uses an underlying transport. The `SSLContext` configuration must be passed to the HTTP client/transport matching your client version.

One approach is creating a low-level `RestClient` with the `SSLContext`, then wrapping it with an Elasticsearch transport. Exact API details depend on the Elasticsearch Java client version and the Apache HttpClient integration used by your dependencies.

Architectural pattern:

~~~text
Truststore
   |
   v
TrustManagerFactory
   |
   v
SSLContext
   |
   v
HTTP low-level client
   |
   v
RestClientTransport
   |
   v
ElasticsearchClient
~~~

Do not create a default `ElasticsearchClient` through a builder and assume it automatically picks up the `SSLContext` from Spring Data configuration. If there are two client beans, name them clearly and ensure each service injects the right client.

When using Spring Data Elasticsearch, prefer the client/transport managed by Spring Data configuration to avoid having two inconsistent connection pools, TLS settings, and lifecycles.

## 9. Configuring Truststore via JVM System Properties

Another approach is configuring the truststore for the entire JVM:

~~~bash
java \
  -Djavax.net.ssl.trustStore=/run/secrets/elasticsearch-truststore.p12 \
  -Djavax.net.ssl.trustStorePassword="$ES_TRUSTSTORE_PASSWORD" \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -jar application.jar
~~~

These properties affect the JVM's default JSSE trust configuration. They can impact other TLS connections in the same process, not just Elasticsearch.

The advantage is simple configuration if the entire application trusts the same set of CAs. The drawback is broad scope and lack of isolation. For applications connecting to multiple systems with different trust policies, a dedicated `SSLContext` is usually clearer.

Do not pass passwords directly on the command line if the environment can expose process arguments to other users. Prefer secret injection appropriate for your deployment platform.

## 10. Mutual TLS (mTLS)

In standard one-way TLS, the client verifies the server certificate. With mutual TLS, the server also requires the client to present a certificate to authenticate the application.

Flow:

~~~text
Client                                    Elasticsearch
  |                                             |
  |----------- ClientHello ------------------->|
  |<---------- Server certificate -------------|
  |----------- Verify server ----------------->|
  |<---------- CertificateRequest -------------|
  |----------- Client certificate ------------>|
  |----------- CertificateVerify ------------->|
  |<---------- Handshake complete -------------|
  |                                             |
  |========== Encrypted HTTP requests =========>|
~~~

mTLS is commonly used when:

- The cluster requires client certificates.
- An internal network needs workload authentication via certificates.
- The system does not want to rely solely on username/password or API keys.
- A zero-trust policy exists between services and Elasticsearch.

mTLS does not automatically replace authorization. The cluster still needs to map the client certificate to an identity and assign appropriate privileges according to the deployment's security mechanism.

### 10.1. Keystore containing the client certificate and private key

The application needs a keystore containing the client certificate and its private key, for example a PKCS12 file:

~~~text
/run/secrets/es-client-keystore.p12
~~~

At the same time, the application still needs a truststore containing the CA used to verify the server.

Do not use the server CA truststore to store the client private key. These two types of material have different purposes and access permissions.

### 10.2. Creating an SSLContext for mTLS

Example creating an `SSLContext` from a truststore and client keystore:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;

import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class MutualTlsContextFactory {

    private MutualTlsContextFactory() {
    }

    public static SSLContext create(
            Path trustStorePath,
            char[] trustStorePassword,
            Path keyStorePath,
            char[] keyStorePassword) throws Exception {

        KeyStore trustStore = KeyStore.getInstance("PKCS12");
        try (InputStream input =
                 Files.newInputStream(trustStorePath)) {
            trustStore.load(input, trustStorePassword);
        }

        TrustManagerFactory trustManagers =
            TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
            );
        trustManagers.init(trustStore);

        KeyStore keyStore = KeyStore.getInstance("PKCS12");
        try (InputStream input =
                 Files.newInputStream(keyStorePath)) {
            keyStore.load(input, keyStorePassword);
        }

        KeyManagerFactory keyManagers =
            KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm()
            );
        keyManagers.init(keyStore, keyStorePassword);

        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(
            keyManagers.getKeyManagers(),
            trustManagers.getTrustManagers(),
            new SecureRandom()
        );

        return sslContext;
    }
}
~~~

This `SSLContext` contains both:

- Trust managers to verify the Elasticsearch server.
- Key managers to present the client certificate when requested by the server.

The client certificate must have the appropriate key usage, the private key must be protected, and Elasticsearch must be configured to trust the CA that issued the client certificate.

Do not enable mTLS on the client alone and expect the server to accept it automatically. Both sides must configure corresponding trust and certificate policies.

## 11. Authentication Differs from Certificate Validation

An HTTPS connection can pass certificate verification and still have requests rejected due to missing authentication or authorization.

| Protection Layer | Question |
|---|---|
| TLS encryption | Is data encrypted in transit? |
| Server certificate validation | Does the client trust the right server? |
| Hostname verification | Does the certificate belong to the hostname being called? |
| Client certificate (mTLS) | Does the client present a certificate trusted by the server? |
| HTTP authentication | Which identity sent the request? |
| Authorization/RBAC | What is that identity allowed to do? |

For example, the application may use Basic Authentication:

~~~java
.withBasicAuth(username, password)
~~~

Or an API key according to the mechanism supported by your Elasticsearch/client version.

Basic Authentication does not encrypt the password itself. Only send credentials over HTTPS with verified certificates. Do not log the `Authorization` header or secrets in requests.

With mTLS, the certificate authenticates the client at the TLS layer. HTTP authentication or role mapping may still be required depending on cluster policy.

## 12. Certificate Expiry and Rotation

Certificates have an expiration date. When a certificate expires, the TLS handshake can fail and the application can no longer connect to Elasticsearch.

Rotation needs to be planned ahead:

1. Generate the new CA/certificate following governance procedures.
2. Update the truststore so the application trusts the new CA, optionally keeping the old CA during the transition period.
3. Deploy the updated truststore to the application.
4. Confirm all instances have loaded the new truststore.
5. Replace the server certificate on Elasticsearch/proxy.
6. Verify connections from all application instances.
7. Once no server uses the old CA, remove the old CA per policy.

If client certificates are used for mTLS, rotate both the client keystore and the server's trust policy.

### 12.1. Avoiding downtime when rotating CAs

If a CA is replaced abruptly, clients whose truststores have not been updated can lose connectivity. An overlap period helps avoid this:

~~~text
Old truststore:          [CA-old]
Transitional truststore: [CA-old, CA-new]
Server certificate:      [CA-old] -> [CA-new]
Final truststore:        [CA-new]
~~~

This is a high-level workflow. The exact sequence must align with your infrastructure, certificate chain, truststore reload capability, and organizational policies.

### 12.2. Does SSLContext reload the truststore automatically?

Do not assume an already created `SSLContext` will automatically re-read the truststore file when the file changes. Typically, trust managers are initialized from the truststore contents at the time `SSLContext` is created.

Depending on the HTTP client and Spring Data version, you may need to recreate the `SSLContext`/client or restart the application to pick up a new truststore. Some platforms have dedicated reload mechanisms; verify them before relying on them for rotation.

Design deployments so client connection pools can be safely replaced or instances can undergo a rolling restart when new certificates need to be loaded.

## 13. TLS Versions and Cipher Suites

TLS has multiple protocol versions. Use a modern version supported by both the JVM and Elasticsearch, in accordance with your organization's security policy. Avoid enabling deprecated or insecure legacy protocols.

Things to verify:

- JDK version.
- Elasticsearch version.
- TLS protocols enabled on the server.
- Cipher suites mutually supported by client and server.
- Certificate algorithms and key lengths.
- FIPS policies or crypto providers if required by the environment.

Do not narrow cipher suites manually without verifying compatibility with the JDK, OS, and Elasticsearch. If handshakes fail after a JDK or cluster upgrade, inspect TLS debug logs to identify protocol/cipher mismatches.

## 14. Testing Connectivity Before Running the Application

You can test TLS independently of Spring Data to isolate issues.

### 14.1. openssl s_client

~~~bash
openssl s_client \
  -connect es-prod.internal.example:9200 \
  -servername es-prod.internal.example \
  -CAfile elasticsearch-root-ca.crt \
  -verify_return_error
~~~

This command inspects the certificate chain, SANs, issuer, validity period, and verification result. `-servername` sends SNI. `-CAfile` specifies the CA used for verification.

If the endpoint uses mTLS, you may need to pass the client certificate and private key using the `openssl` flags appropriate for your files.

### 14.2. curl with a CA certificate

~~~bash
curl \
  --cacert elasticsearch-root-ca.crt \
  -u "$ES_USERNAME:$ES_PASSWORD" \
  https://es-prod.internal.example:9200/
~~~

Do not use `-k` or `--insecure` in production verification. That option disables certificate and hostname verification, hiding the exact problem you need to fix.

If `curl` succeeds while Java fails, compare the CA store, hostname, TLS protocol, proxy, and client configuration. `curl` may use an operating system trust store different from the JVM truststore.

### 14.3. keytool

Inspect a certificate:

~~~bash
keytool -printcert -file elasticsearch-root-ca.crt
~~~

Inspect a truststore:

~~~bash
keytool -list -v \
  -keystore elasticsearch-truststore.p12 \
  -storetype PKCS12
~~~

These tools verify the files and chain. They do not prove Spring Data is using the intended truststore file; always verify runtime configuration.

## 15. Enabling TLS Handshake Debugging in the JVM

When diagnosing TLS errors from Java, you can enable debugging temporarily:

~~~bash
java \
  -Djavax.net.debug=ssl,handshake,trustmanager \
  -jar application.jar
~~~

The logs contain detailed information about the handshake, certificate chain, trust manager, and protocol negotiation. Only enable this in a controlled environment and disable it after investigation because output is verbose and may reveal internal metadata.

Do not post raw TLS logs publicly if they contain internal hostnames, certificate metadata, or sensitive operational information.

## 16. Common HTTPS Errors

| Error | Common Cause | Resolution |
|---|---|---|
| `PKIX path building failed` | JVM cannot build a chain to a trusted CA | Check CA, intermediate certificates, and truststore |
| `unable to find valid certification path` | Truststore lacks the CA or client uses a different truststore | Verify runtime `SSLContext`/truststore |
| `No subject alternative DNS name matching` | URL hostname is not in SAN | Use the correct hostname or issue a certificate with matching SAN |
| `No subject alternative names matching IP address` | Connecting by IP without an IP SAN in the certificate | Use a DNS SAN or issue an IP SAN |
| `CertificateExpiredException` | Certificate is expired | Rotate the certificate |
| `NotYetValidException` | Certificate is not yet valid or clock skew | Check validity dates and synchronize clocks |
| `handshake_failure` | Protocol, cipher, client cert, or server policy mismatch | Inspect TLS debug output and server logs |
| `bad_certificate` | Server rejects client certificate or chain | Check mTLS, client keystore, and CA trust |
| `HTTP 401` | TLS succeeded, but authentication is missing/invalid | Check credentials/API key |
| `HTTP 403` | Identity authenticated, but lacks privileges | Check roles/privileges |
| `Connection refused` | Wrong host/port or service not listening | Check endpoint and network |
| `HTTP plaintext sent to HTTPS port` | Client uses `http://` against a TLS port | Switch to HTTPS and configure TLS |
| `Unsupported or unrecognized SSL message` | HTTP/HTTPS mix-up or misrouted proxy | Check scheme and endpoint |
| `Certificate chain incomplete` | Server missing intermediate certificate | Configure server to send the full chain |

### 16.1. Distinguishing TLS errors from Elasticsearch errors

If the TLS handshake succeeds, the client can proceed to receive HTTP responses:

- `401`: authentication.
- `403`: authorization.
- `404`: resource/index/path.
- `429`: throttling or overload.
- `5xx`: server/proxy error.

Do not treat all connection errors as certificate errors. Identify which layer failed before changing configuration.

## 17. Why Not Use Trust-All or Disable Hostname Verification?

Some code snippets online create a `TrustManager` that accepts any certificate or a `HostnameVerifier` that always returns `true`. These bypass the very mechanism that verifies server identity.

Consequences:

- An attacker can stand up a spoofed server and be accepted by the client.
- Traffic is encrypted, but may be encrypted to the wrong server.
- Credentials, queries, and documents can be stolen.
- The application loses the ability to detect a replaced certificate.
- Production misconfigurations are masked.

TLS encryption without peer verification does not guarantee the client is talking to the real Elasticsearch cluster.

Do not use any of the following in production:

- A `TrustManager` accepting every `X509Certificate`.
- A `HostnameVerifier` always returning `true`.
- `curl -k` to bypass checks.
- Disabling certificate validation via system properties.
- Importing a certificate without verifying its source/fingerprint.
- Plaintext HTTP over an untrusted network.

If development uses self-signed certificates, create a dedicated development CA, sign certificates with appropriate SANs, and import that CA into the development truststore.

## 18. Managing Secrets and Certificates in Deployment Environments

Sensitive values include:

- Truststore password.
- Client keystore password.
- Client private key.
- Elasticsearch username/password.
- API key.
- Certificate private material.

Principles:

- Use a secret manager or platform secret mounts.
- Restrict read permissions on truststore/keystore files to the minimum required.
- Do not commit passwords/private keys into the repository.
- Do not bake secrets into Docker image layers.
- Do not log `Authorization` headers, passwords, or private keys.
- Do not pass secrets via query parameters.
- Rotate credentials and certificates according to policy.
- Use a dedicated identity per service.
- Separate development, staging, and production trust policies.

Public CA certificates or certificate chains may not be confidential, but you still need to ensure their integrity and a trusted distribution source. Private keys must always be protected.

## 19. HTTPS for the Reactive Elasticsearch Client

Reactive Spring Data Elasticsearch uses a reactive HTTP client stack. TLS must still perform the same checks:

- The endpoint uses HTTPS.
- The truststore contains the appropriate CA.
- Hostname verification is enabled.
- mTLS is configured if required by the server.
- Authentication/authorization are configured separately.

Do not take the imperative client's `SSLContext` and assume the reactive client uses it automatically. Reactive and imperative stacks may use different transport/client configurations depending on the Spring Data Elasticsearch version.

When configuring the reactive client, inspect the API of `ReactiveElasticsearchConfiguration`, `ReactiveRestClients`, or whichever client configuration mechanism your current dependencies expose. Confirm the trust manager and hostname verifier are actually wired into the reactive HTTP client.

If the application uses both reactive and imperative repositories/templates, test both connection paths independently. One client having proper TLS does not guarantee the other does.

## 20. Testing TLS in the Application

Testing should be divided into layers:

### 20.1. Certificate and endpoint checks

- Verify the certificate chain against the trusted CA.
- Verify SANs match the hostname.
- Check certificate validity.
- Verify the server sends all intermediate certificates.
- Verify endpoint and SNI behavior.

### 20.2. Integration tests with TLS

Use an Elasticsearch test instance configured with HTTPS or a test environment with its own CA certificate.

Verify:

- The application connects using HTTPS.
- The right truststore is used.
- A valid certificate for the hostname succeeds.
- An untrusted certificate is rejected.
- A hostname mismatch is rejected.
- Invalid authentication returns 401.
- An under-privileged identity returns 403.
- The mTLS client certificate is sent if required by configuration.

Do not write tests that only assert a request succeeds with a trust-all manager. Such tests do not verify certificate validation.

### 20.3. Testing certificate rotation

You can test the CA overlap procedure:

1. Run the server with the old CA certificate.
2. Update the test truststore to contain both the old and new CAs.
3. Switch the server to the new CA certificate.
4. Confirm the client continues to connect.
5. Remove the old CA and confirm the new certificate is still trusted.

If the client does not support reloading `SSLContext`, the test should simulate how the application recreates the client or performs a rolling restart.

## 21. HTTPS Deployment Workflow for Spring Data Elasticsearch

A deployment workflow can follow these steps:

1. Confirm the Elasticsearch endpoint is serving HTTPS.
2. Obtain the CA certificate from a trusted administrative source.
3. Verify the fingerprint and certificate chain.
4. Confirm SANs include the hostname/IP used by the application.
5. Create a dedicated truststore or choose the appropriate JVM truststore.
6. Create an `SSLContext` with `TrustManagerFactory`.
7. Configure Spring Data `ClientConfiguration` or client transport to use that `SSLContext`.
8. Configure authentication separately using Basic Auth, API key, or mTLS per policy.
9. Protect the truststore password and private keys using secret management.
10. Test with `openssl`/`curl` with certificate verification enabled.
11. Run integration tests through the exact client used by repositories/`Operations`.
12. Test 401/403 errors separately from TLS errors.
13. Set up certificate expiry monitoring and a rotation plan.
14. Repeat configuration for the reactive client if the application uses a reactive stack.

Do not treat opening a TCP socket or receiving an HTTP response as proof that TLS is verified properly. Verification must cover both the certificate chain and the hostname.

## 22. Operational Checklist

| Item | Desired State |
|---|---|
| Connection URL | HTTPS |
| Server certificate | Valid, not expired |
| Certificate chain | Complete intermediates leading to a trusted CA |
| SAN | Matches hostname/IP in the URL |
| Hostname verification | Enabled |
| TLS protocol | Supported and approved version |
| Truststore | Correct environment, contains trusted CA |
| Private key | Protected, not committed |
| Basic Auth/API key | Stored in secret manager |
| mTLS | Client cert and server trust configured on both sides if required |
| Logs | Free of credentials/private keys |
| Certificate rotation | Overlap and deployment procedure in place |
| Imperative client | TLS verified |
| Reactive client | Verified separately if used |
| Integration tests | Reject untrusted certificates and hostname mismatches |

## 23. Quick Reference Table

| Need | How |
|---|---|
| Encrypt connection | Use HTTPS/TLS |
| Trust internal CA | Create a truststore containing the CA |
| Verify hostname | Certificate has SAN matching the URL |
| Use PKCS12 truststore | `keytool` import CA and Java `KeyStore` API |
| Configure `SSLContext` | `TrustManagerFactory` + `SSLContext` |
| Configure Spring Data | `ClientConfiguration.usingSsl(sslContext)` per version |
| Use default JVM trust | `usingSsl()` if the CA is already trusted by runtime |
| HTTP authentication | Basic Auth or API key over HTTPS |
| Client certificate authentication | mTLS with key managers and client keystore |
| Inspect TLS endpoint | `openssl s_client` |
| Test HTTP with CA | `curl --cacert` |
| View certificate | `keytool -printcert` |
| Inspect truststore | `keytool -list` |
| Debug Java handshake | Temporary `javax.net.debug` |
| Rotate CA safely | Truststore overlap and controlled rotation |
| Prevent MITM | Never use trust-all or disable hostname verification |

HTTPS secures Spring Data Elasticsearch connections when TLS is configured properly on both server and client. The application must trust the right CA, verify the certificate chain and hostname SAN, use an HTTPS endpoint, and keep hostname verification enabled. The truststore holds the CAs trusted by the client; the keystore holds the client private key/certificate when mTLS is needed. Wire the `SSLContext` into whichever imperative or reactive client is actually in use, keep certificate validation separate from HTTP authentication/authorization, manage secrets and certificate rotation intentionally, and test both valid certificates and untrusted/mismatched cases.
