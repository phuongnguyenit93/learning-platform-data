# Providing Dynamic Configuration, Certificates, and Credentials for Testing

Spring Data Elasticsearch integration tests typically need to know the Elasticsearch address, dynamically assigned port, access account, and TLS certificate. If these values are hardcoded in `application.yml`, tests become tied to a developer machine, hard to run in parallel, and risk accidentally using real-environment credentials.

A sound test design separates three groups of data:

- **Dynamic connection configuration**: URI, host, port, index prefix, and parameters provided when the container or test environment starts.
- **Certificates**: the CA certificate the client trusts, plus the client certificate/private key if the system uses mutual TLS.
- **Credentials**: test-specific username/password or API key with least-privilege permissions.

Spring Boot and Spring Data Elasticsearch support multiple ways to supply configuration to the application context. With Testcontainers, `@DynamicPropertySource` is a common way to register dynamically assigned endpoints before Spring creates the Elasticsearch client. When real TLS and authorization testing is required, you must use an Elasticsearch test instance configured with security enabled; a test container with security disabled cannot prove authentication or certificate validation works properly.

## 1. Why Must Test Configuration Be Provided Dynamically?

An Elasticsearch test may run across many environments:

- A developer machine with local Docker.
- A CI runner with ports randomly assigned by Docker.
- Testcontainers with a fresh container per test suite.
- An integration environment using a separately managed Elasticsearch cluster.
- Security tests requiring HTTPS, a CA certificate, and a dedicated user/API key.

Hardcoding `localhost:9200` can collide with another Elasticsearch instance running on the machine. Hardcoding ports causes port contention when multiple test suites run concurrently. Hardcoding passwords in source risks committing or reusing credentials outside test environments.

Dynamic configuration lets tests obtain connection details after test resources start:

~~~text
Test starts
   |
   v
Start Elasticsearch container / test service
   |
   v
Resolve host, mapped port, URI, credentials and CA
   |
   v
Register dynamic Spring properties
   |
   v
Create Spring ApplicationContext and Elasticsearch client
   |
   v
Run repository / operations tests
   |
   v
Close client and test resources
~~~

Crucially, properties must be registered before Spring initializes beans that depend on them. If the Elasticsearch client has already been created with an old endpoint, changing a Java variable afterward will not reconfigure the existing client.

## 2. Configuration Sources in Spring Tests

There are several ways to supply properties in tests:

| Approach | Best suited when | Characteristics |
|---|---|---|
| `application-test.yml` | Stable, non-secret values | Easy to read and share |
| `@TestPropertySource` | Overriding a few properties in a test class | Static values |
| `@SpringBootTest(properties = ... )` | Test needs small configuration directly on the annotation | Static values, test-scoped |
| `@DynamicPropertySource` | URI/port/secrets generated when the test starts | Registers dynamic suppliers |
| `@ServiceConnection` | Testcontainers service supported by Spring Boot service connections | Auto-wires recognized services |
| Environment variable / secret store | CI or test environment uses external secrets | Keeps secrets out of source |

For endpoints with mapped ports changing on every run, `@DynamicPropertySource` is usually more suitable than a static YAML file.

`@ServiceConnection` can reduce boilerplate when your Spring Boot version and Testcontainers module support that service type. When registering custom properties like CA paths, API keys, index prefixes, or HTTPS URIs, `@DynamicPropertySource` remains useful.

Do not register the same property in multiple places unintentionally. When multiple configuration sources exist, know which source overrides the final value.

## 3. Registering Testcontainers Endpoints with @DynamicPropertySource

Example with Elasticsearch Testcontainers for a basic integration test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.elasticsearch.ElasticsearchContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class ProductSearchIntegrationTest {

    @Container
    static final ElasticsearchContainer elasticsearch =
            new ElasticsearchContainer(
                    "docker.elastic.co/elasticsearch/elasticsearch:8.15.0"
            );

    @DynamicPropertySource
    static void elasticsearchProperties(
            DynamicPropertyRegistry registry
    ) {
        registry.add(
                "spring.elasticsearch.uris",
                elasticsearch::getHttpHostAddress
        );
    }

    @Test
    void applicationContextStarts() {
        // Exercise repository or ElasticsearchOperations here.
    }
}
~~~

The example pins the image version so tests behave repeatably. Choose a version compatible with the Spring Data Elasticsearch and Elasticsearch Java API Client versions used by your project; do not use time-varying tags like `latest` for stable CI.

`getHttpHostAddress()` returns the container's HTTP address with its mapped port. The test does not need to assume Elasticsearch always runs on host port 9200.

Key points to remember:

- The container is declared `static` so it can be used inside the `static` `@DynamicPropertySource` method.
- The supplier `elasticsearch::getHttpHostAddress` is invoked when the property is resolved.
- Properties must be registered before Spring creates the Elasticsearch client.
- The container and Spring context must have aligned lifecycles; do not stop the container while the context still uses the client.
- If a test requires an HTTPS endpoint, register an HTTPS URI and configure the corresponding trust certificate.

The Testcontainers Elasticsearch module and image may configure security differently by version. Many simple test setups run unauthenticated HTTP to reduce startup time. That suits basic mapping/query tests but does not verify TLS, passwords, API keys, or role authorization.

## 4. Separating Test Properties from Default Configuration

Non-sensitive values can be placed in `src/test/resources/application-test.yml`:

~~~yaml
app:
  elasticsearch:
    index-prefix: test-products
    connect-timeout: 2s
    socket-timeout: 5s
~~~

For profile-based tests:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class ProductRepositoryIntegrationTest {
}
~~~

Dynamic endpoints can still be overridden by `@DynamicPropertySource`. Do not write randomly assigned container URIs into YAML files because each run may receive a different port.

`@TestPropertySource` works well for static values:

~~~java
@SpringBootTest
@TestPropertySource(properties = {
        "app.elasticsearch.index-prefix=it-products",
        "app.elasticsearch.request-timeout=3s"
})
class ProductSearchTest {
}
~~~

If using custom properties to configure multiple Elasticsearch clients, group them into `@ConfigurationProperties` instead of scattering many `@Value` fields:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.elasticsearch")
public record TestElasticsearchProperties(
        String uri,
        String username,
        String password,
        String apiKey,
        String caCertificate,
        Duration connectTimeout,
        String indexPrefix
) {
}
~~~

This is an example property structure. Only one authentication method—such as Basic Auth or an API key—should be selected per client, unless Elasticsearch configuration intentionally requires a combined mechanism.

## 5. Providing Dynamic Username/Password for Tests

For test instances with Basic Authentication enabled, register the username/password from a test fixture or secret store:

~~~java
@DynamicPropertySource
static void elasticsearchProperties(DynamicPropertyRegistry registry) {
    registry.add(
            "app.elasticsearch.uri",
            () -> securedElasticsearchUri()
    );
    registry.add(
            "app.elasticsearch.username",
            () -> "test_search_user"
    );
    registry.add(
            "app.elasticsearch.password",
            () -> testPassword()
    );
}
~~~

`testPassword()` should read the secret from a managed test source or obtain it from the initialized container fixture. Never use production passwords or commit real credentials to the repository.

If using Spring Boot auto-configuration, standard properties usually look like:

~~~yaml
spring:
  elasticsearch:
    uris: https://localhost:9200
    username: test_search_user
    password: test-only-password
~~~

Property names and support depend on the Spring Boot version. If tests use a custom Elasticsearch client or Spring Data `ClientConfiguration`, you can use a custom prefix like `app.elasticsearch` and pass values into the client factory.

Do not set both Basic Auth and an API key simultaneously in a single client configuration unless the code explicitly defines precedence. Avoid causing different authentication behavior between local and CI due to leftover properties.

## 6. Dedicated API Keys for Testing

Elasticsearch API keys can scope permissions to a test workload. For instance, search integration tests only need read access on `test-products-*`; writer tests need write access on a dedicated index.

An API key created during test setup or a separate provisioning step can be supplied to the client via a property:

~~~java
@DynamicPropertySource
static void elasticsearchProperties(DynamicPropertyRegistry registry) {
    registry.add("app.elasticsearch.uri", RowTestEnvironment::uri);
    registry.add("app.elasticsearch.api-key", RowTestEnvironment::encodedApiKey);
}
~~~

The Elasticsearch REST API uses the header:

~~~http
Authorization: ApiKey BASE64_ENCODED_ID_AND_KEY
~~~

When the create-key API returns an `encoded` field, that value is designed to be sent in the Authorization header. Do not manually concatenate ID and secret arbitrarily if the response already provides the encoded value.

Some principles:

- Each test suite or test role uses its own key.
- Grant permissions only on the required test indices.
- Do not use cluster-admin API keys to run repository tests.
- Revoke keys after tests if created on a shared cluster.
- Do not print keys or Authorization headers to logs when tests fail.
- Do not store keys in CI artifacts or public reports.

Running tests against a container using a single admin user does not substitute for role/API key testing. Maintain a dedicated security suite to verify read, write, and denied actions.

## 7. Distinguishing HTTP TLS and Transport TLS

Elasticsearch has two distinct TLS channels:

| Channel | Purpose | Used directly by Spring Data client? |
|---|---|---|
| HTTP layer TLS | Protects the REST API between the application and Elasticsearch | Yes |
| Transport layer TLS | Protects node-to-node communication inside the cluster | Not directly |

Spring Data Elasticsearch communicates with the cluster via an HTTP REST client. Therefore, test clients need to trust the **HTTP endpoint** certificate.

Transport TLS may still be required for cluster security to function properly, especially in multi-node deployments. However, the transport layer certificate is not automatically the trust certificate the Java application needs to call the REST API.

When testing application connectivity, obtain the CA certificate used to sign the HTTP server certificate. Do not mistakenly grab the node transport certificate or a certificate from another endpoint.

## 8. CA Certificates and Server Certificates

Over HTTPS, Elasticsearch sends its server certificate to the client. The client must verify:

1. The certificate is valid (not expired).
2. The certificate is signed by a CA trusted by the client.
3. The hostname/IP in the URI matches the certificate's Subject Alternative Name (SAN).
4. The certificate chain is complete and valid.
5. The TLS protocol/cipher is supported by both sides.

In a test environment, you can create a dedicated CA and use it to sign the server certificate for the Elasticsearch test node.

Diagram:

~~~text
Test CA
   |
   +---- signs ----> Elasticsearch HTTP server certificate
                           |
                           v
                 HTTPS endpoint: es-test.local
                           |
                           v
                 Java client trusts Test CA
~~~

Clients usually only need to trust the CA certificate. There is no need to place the server's private key inside the test application.

Never use production certificates/private keys for tests. Nor should you disable certificate validation just to make tests run; doing so hides TLS misconfigurations and fosters unsafe habits.

## 9. Hostname and SAN Must Match the Endpoint

A common error is having a valid certificate whose hostname does not match.

For example, the certificate has SANs:

~~~text
DNS: es-test.internal
DNS: elasticsearch
~~~

Yet the test connects to:

~~~text
https://localhost:39217
~~~

The client may reject the certificate because `localhost` is not in the SAN, even though the CA is trusted.

Solutions:

- Generate certificates with SANs matching the hostname the test uses.
- Use a hostname/container network alias included in the SAN.
- If using a host-mapped port, include the corresponding hostname/IP in the SAN appropriately.
- Keep hostname verification enabled.

Do not use `NoopHostnameVerifier` or disable endpoint identification to bypass errors. A TLS test is only meaningful when it verifies the hostname just as the production application will.

## 10. Creating a Truststore from a CA Certificate

Java can use a truststore containing the CA certificate to verify the Elasticsearch server.

Example creating a PKCS12 truststore with `keytool`:

~~~bash
keytool -importcert \
  -alias elasticsearch-test-ca \
  -file test-ca.crt \
  -keystore elasticsearch-test-truststore.p12 \
  -storetype PKCS12
~~~

The command will prompt for a truststore password. In CI, passwords should be provided via secret variables or test setup, not recorded in shared command histories or public logs.

You can configure the truststore path in test settings:

~~~yaml
app:
  elasticsearch:
    ca-certificate: classpath:certs/test-ca.crt
    truststore: file:/workspace/test-certs/elasticsearch-test-truststore.p12
~~~

If you only need to trust a single CA certificate, the client can build an SSL context directly from the certificate without generating a truststore file. This is convenient when Testcontainers generates certificates in a temporary directory.

Do not put the CA's private key into the client truststore. A truststore holds trusted certificates; a keystore holds the client identity's private key/certificate presented during mutual TLS.

## 11. Creating an SSLContext from a CA Certificate in Java

You can read a CA certificate and build an `SSLContext` without modifying the global JVM truststore:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;

import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class TestSslContexts {

    private TestSslContexts() {
    }

    public static SSLContext trustCertificate(Path caCertificate)
            throws Exception {

        CertificateFactory certificateFactory =
                CertificateFactory.getInstance("X.509");

        Certificate ca;
        try (InputStream input = Files.newInputStream(caCertificate)) {
            ca = certificateFactory.generateCertificate(input);
        }

        KeyStore trustStore = KeyStore.getInstance("PKCS12");
        trustStore.load(null, null);
        trustStore.setCertificateEntry("elasticsearch-test-ca", ca);

        TrustManagerFactory trustManagerFactory =
                TrustManagerFactory.getInstance(
                        TrustManagerFactory.getDefaultAlgorithm()
                );
        trustManagerFactory.init(trustStore);

        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(
                null,
                trustManagerFactory.getTrustManagers(),
                null
        );

        return sslContext;
    }
}
~~~

This code:

- Parses the CA certificate in X.509 format.
- Creates an in-memory-only truststore.
- Adds the CA certificate to the truststore.
- Creates a TrustManager from the truststore.
- Initializes an SSL context using TLS.

This SSL context still verifies the certificate chain. Hostname verification must remain enabled on the HTTP client.

Do not create a `TrustManager` that always trusts everything or use an `SSLContext` that accepts any certificate. Those approaches prevent tests from verifying server identity.

## 12. Configuring the Spring Data Elasticsearch Client with SSLContext

In Spring Data Elasticsearch versions using `ClientConfiguration`, you can pass the SSL context into the client configuration:

~~~java
import javax.net.ssl.SSLContext;

import org.springframework.data.elasticsearch.client.ClientConfiguration;

ClientConfiguration clientConfiguration(
        String hostAndPort,
        String username,
        String password,
        SSLContext sslContext
) {
    return ClientConfiguration.builder()
            .connectedTo(hostAndPort)
            .usingSsl(sslContext)
            .withBasicAuth(username, password)
            .build();
}
~~~

`hostAndPort` has the form `hostname:port`; the HTTPS scheme is chosen when SSL is configured. Builder methods and integration with the Elasticsearch Java API Client may vary across Spring Data Elasticsearch versions. Place this configuration in `ElasticsearchConfiguration` or the client factory appropriate for your project's dependencies.

If using Spring Boot SSL Bundles, you can declare the CA certificate in a bundle and retrieve the SSL context from `SslBundles`:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        elasticsearch-test:
          truststore:
            certificate: classpath:certs/test-ca.crt
~~~

Example retrieving the context:

~~~java
import org.springframework.boot.ssl.SslBundles;

SSLContext sslContext =
        sslBundles.getBundle("elasticsearch-test").createSslContext();
~~~

Then pass the SSL context into the Elasticsearch client configuration. Bundle declaration and direct property integration with Elasticsearch auto-configuration depend on the Spring Boot version; if no direct integration property exists, use a custom client configuration as shown above.

## 13. Basic Authentication and API Keys Do Not Replace TLS

Basic Authentication and API keys are HTTP-layer credentials. TLS protects the transport channel and verifies the server.

Do not send usernames/passwords or API keys over unencrypted HTTP across untrusted networks. Base64 in Basic Auth or API key headers is not encryption; TLS is what protects credentials in transit.

Options:

| Mechanism | Client sends | When appropriate |
|---|---|---|
| Basic Auth | Username/password in Authorization header | Simple test users, service identities |
| API key | Encoded API key in Authorization header | Narrow roles, independently revocable credentials |
| Mutual TLS | Client certificate and private key in TLS handshake | Environments requiring certificate-based client identity |
| Combining TLS with Basic/API key | HTTPS + one auth mechanism | Common for service-to-service communication |

If tests only use unauthenticated HTTP, you cannot conclude that production authentication or TLS is configured correctly.

## 14. Mutual TLS and Client Certificates

In mutual TLS (mTLS), the client also presents a certificate so the server verifies the client's identity. This is a separate layer from the client trusting the server certificate.

Distinguish between:

- **Truststore**: CA certificate trusted by the client when verifying the server.
- **Keystore**: client certificate and private key used by the client to prove its identity.
- **Server trust configuration**: CA trusted by Elasticsearch to verify client certificates.

In Elasticsearch, certificate-based client authentication generally requires configuring a PKI realm and appropriate trust chain. Simply enabling HTTPS does not mean Elasticsearch automatically uses client certificates as user identities.

Example client configuration structure needing both truststore and key material:

~~~java
SSLContext sslContext = buildSslContext(
        serverCaCertificate,
        clientCertificate,
        clientPrivateKey
);
~~~

`buildSslContext(...)` here is an illustrative function. Loading certificates/private keys depends on PEM/PKCS12 formats and the TLS client API in use. Do not place client private keys in the truststore; keep them in a keystore or secret mount readable only by the test process.

If production does not use mTLS, do not add mTLS just to test repository queries. Maintain a dedicated suite for mTLS when the application genuinely relies on that mechanism.

## 15. Dynamic Configuration for a Secured Elasticsearch Test Instance

A secured test environment needs to provide at least:

- HTTPS URI and mapped port.
- Test username/password or API key.
- CA certificate path or SSL bundle.
- Hostname matching the SAN.
- Role suited to the test.
- Certificate lifetime covering the entire test run.

Properties can be registered as:

~~~java
@DynamicPropertySource
static void securedElasticsearchProperties(
        DynamicPropertyRegistry registry
) {
    registry.add(
            "app.elasticsearch.uri",
            SecuredElasticsearchTestEnvironment::httpsUri
    );
    registry.add(
            "app.elasticsearch.username",
            () -> "test_search_user"
    );
    registry.add(
            "app.elasticsearch.password",
            SecuredElasticsearchTestEnvironment::password
    );
    registry.add(
            "app.elasticsearch.ca-certificate",
            SecuredElasticsearchTestEnvironment::caCertificatePath
    );
}
~~~

`SecuredElasticsearchTestEnvironment` represents the project's fixture managing the container/certificates. The fixture must start Elasticsearch with HTTP TLS and security configured before the Spring context creates the client.

Do not just add an `ELASTIC_PASSWORD` variable and assume HTTP TLS, CA trust, and roles are completely set up. Security settings and certificate files must be compatible with the exact Elasticsearch image version.

For secured test containers, use a Docker image or Compose fixture with versioned configuration, test certificates, and explicitly provisioned test users/roles. This is more repeatable than mutating settings with ad-hoc scripts in every test class.

## 16. Distinguishing Non-Security Tests and Security Tests

Split tests by objective:

| Test group | Elasticsearch setup | What to verify |
|---|---|---|
| Mapping/repository integration | Simple HTTP container | Queries, mappings, converters, repositories |
| TLS integration | HTTPS with test CA | Trust chain, hostname, protocol |
| Authentication integration | HTTPS + test user/API key | Valid and invalid credentials |
| Authorization integration | Distinct read/write/admin roles | Allowed and denied permissions |
| mTLS integration | HTTPS + client certificate | Server verifies client identity |
| Production smoke test | Production-like test/staging environment | Real configuration and secret injection |

Do not enable full security for every unit test. Separating suites keeps regular tests fast while preserving dedicated checks for TLS and authorization.

## 17. Testing Read and Write Permissions with Different Credentials

You can provision test identities such as:

- `test_search_user`: read-only permission on the test index.
- `test_writer_user`: write permission on the test index.
- `test_index_admin`: used only in migration/admin test suites.

Scenario:

~~~text
Search credential
   ├── Search products-test: allowed
   ├── Index document: denied
   └── Delete index: denied

Writer credential
   ├── Index/update document: allowed
   ├── Search: only if read was granted
   └── Delete index: denied

Index admin credential
   ├── Create test index: allowed
   ├── Update mapping: allowed
   └── Access production index: denied
~~~

A test should verify both success and failure:

~~~java
@Test
void searchCredentialCanReadButCannotWrite() {
    // Searching with test_search_user must succeed.
    // Attempting to index a document with the same credential must return 403.
}
~~~

The snippet above describes the scenario. In an implementation, you can use two client beans or instantiate separate clients per credential to verify real permissions on Elasticsearch.

Do not use admin credentials for all tests and only check Spring Security endpoints. That does not test Elasticsearch roles.

## 18. Testing Invalid Certificates and Wrong Credentials

Important negative test cases:

| Case | Expected outcome |
|---|---|
| Valid CA, matching hostname, valid credential | TLS handshake and request succeed |
| Untrusted CA | TLS handshake fails |
| Expired certificate | Client rejects certificate |
| Hostname does not match SAN | Hostname verification fails |
| Wrong username/password | HTTP 401 |
| Expired or revoked API key | Request denied |
| User lacks index permission | HTTP 403 or corresponding authorization error |
| Search user calls write API | Denied |
| Writer calls delete index | Denied if role lacks permission |

Do not only assert a generic exception. Where possible, verify the failure reason at the appropriate layer: SSL handshake, hostname verification, authentication, or authorization.

Negative tests should use dedicated test endpoints and credentials to avoid accidentally locking out or revoking shared-environment credentials.

## 19. Managing Certificates and Secrets in CI

CI needs a way to supply certificates and credentials without checking them into source control.

A suitable workflow:

1. Generate a short-lived test CA and server certificate per test run, or use a dedicated test fixture.
2. Store certificate files in a job temporary directory or mount them read-only into the container.
3. Supply test passwords/API keys from a secret store or generate them during test setup.
4. Register URIs, credentials, and CA paths via dynamic properties.
5. Run integration/security tests.
6. Close clients and containers, and delete temporary certificate directories.
7. Revoke API keys if using a shared cluster.
8. Never upload private keys, passwords, or API keys into test reports/artifacts.

If certificates are reused across multiple jobs, establish a rotation policy and short lifetimes. Never keep a long-lived CA private key in the repository to arbitrarily sign certificates for every test.

For committed certificate fixtures, only commit public certificates dedicated to tests. Test private keys must still be controlled; never use a private key capable of granting access to real environments.

## 20. Do Not Mutate the Global JVM Truststore per Test

You can configure the JVM via system properties:

~~~text
-Djavax.net.ssl.trustStore=...
-Djavax.net.ssl.trustStorePassword=...
~~~

This affects every TLS client using the default JVM trust manager in the process. When test suites run in parallel or multiple clients talk to different endpoints, changing global properties causes unpredictable side effects.

Prefer creating a dedicated SSL context for the Elasticsearch client:

~~~java
SSLContext elasticsearchSslContext =
        TestSslContexts.trustCertificate(caPath);
~~~

Then attach that SSL context to the test's dedicated client configuration.

If using the JVM truststore is unavoidable, configure it at process startup rather than toggling it between test methods. Ensure the test process does not share a JVM with other workloads requiring a different truststore.

## 21. Using @ServiceConnection When Appropriate

Spring Boot supports `@ServiceConnection` for certain Testcontainers services. When a container is recognized, Boot can automatically generate connection details and feed them into the corresponding auto-configuration.

Conceptual example:

~~~java
@Testcontainers
@SpringBootTest
class ProductRepositoryTest {

    @Container
    @ServiceConnection
    static final ElasticsearchContainer elasticsearch =
            new ElasticsearchContainer(
                    "docker.elastic.co/elasticsearch/elasticsearch:8.15.0"
            );
}
~~~

Support and connection-detail types depend on the Spring Boot and Testcontainers module versions. Check your dependencies before using it.

`@ServiceConnection` is convenient for basic endpoints. When customizing username/password, API keys, CA paths, SSL bundles, or index prefixes, you can supplement it with `@DynamicPropertySource` for the remaining properties.

Do not register the same URI via both `@ServiceConnection` and a dynamic property with two different values. Choose one authoritative source for each property.

## 22. Using DynamicPropertySource with Custom Spring Data Clients

If the application defines a custom client configuration, let dynamic properties supply the inputs and let the bean configuration build the client.

Example:

~~~java
@ConfigurationProperties(prefix = "app.elasticsearch")
public record ElasticsearchTestClientProperties(
        String hostAndPort,
        String username,
        String password,
        String caCertificate
) {
}
~~~

Register values in the test:

~~~java
@DynamicPropertySource
static void elasticsearchProperties(DynamicPropertyRegistry registry) {
    registry.add(
            "app.elasticsearch.host-and-port",
            SecuredElasticsearchTestEnvironment::hostAndPort
    );
    registry.add(
            "app.elasticsearch.username",
            () -> "test_writer"
    );
    registry.add(
            "app.elasticsearch.password",
            SecuredElasticsearchTestEnvironment::password
    );
    registry.add(
            "app.elasticsearch.ca-certificate",
            SecuredElasticsearchTestEnvironment::caCertificatePath
    );
}
~~~

The client configuration reads properties and creates the SSL context:

~~~java
@Bean
ClientConfiguration elasticsearchClientConfiguration(
        ElasticsearchTestClientProperties properties
) throws Exception {

    SSLContext sslContext = TestSslContexts.trustCertificate(
            Path.of(properties.caCertificate())
    );

    return ClientConfiguration.builder()
            .connectedTo(properties.hostAndPort())
            .usingSsl(sslContext)
            .withBasicAuth(
                    properties.username(),
                    properties.password()
            )
            .build();
}
~~~

This is a structural pattern for configuring a Spring Data client. In a real application, place the bean in the configuration class suited to your Spring Data Elasticsearch version and avoid creating multiple clients when only one connection is needed.

`@DynamicPropertySource` registers properties during test context construction; it does not create certificates, users, or roles by itself. The fixture must provision those resources before the supplier is invoked.

## 23. Cleaning Up Clients and Test Resources

When tests finish, close resources:

- Elasticsearch containers.
- Elasticsearch clients/transports.
- Low-level HTTP clients if manually created by the application.
- PIT or scroll contexts if created by tests.
- Temporary certificates and keystores.
- API keys created on shared clusters.
- Test indices if the container is not destroyed.

If using Spring context caching, the container must outlive the test contexts reusing it. Stopping a container too early can cause another test to reuse a context whose client points to a dead endpoint.

You can use JUnit or Testcontainers lifecycles to manage containers. For resources created programmatically such as API keys and indices, clean them up in `@AfterAll` or an appropriate lifecycle fixture.

Do not delete shared indices outside a test-dedicated prefix. Create indices with distinguishable names such as `it-products-<run-id>` to avoid impacting other tests.

## 24. Common Pitfalls

### Hardcoding localhost:9200

CI may assign a different mapped port, or the container may not bind to a fixed port. Obtain the URI from Testcontainers and register it with `@DynamicPropertySource`.

### Registering Properties After Client Initialization

The Spring client may retain the old endpoint. Register dynamic properties before the ApplicationContext creates client beans.

### Assuming Test Containers Test TLS by Default

Simple containers may run plain HTTP with security disabled. Use a dedicated secured suite to verify certificates, authentication, and authorization.

### Trusting All Certificates

This lets tests pass even with untrusted certificates. Trust the specific test CA and keep hostname verification enabled.

### Certificate Lacking a Matching SAN

The CA may be right while the hostname/IP in the URI does not match the SAN. Keep endpoints and SANs consistent.

### Confusing HTTP TLS with Transport TLS

Spring Data applications use the HTTP REST endpoint. Trust the certificate for the HTTP layer.

### Committing Passwords or API Keys

Credentials can leak through Git, logs, and CI artifacts. Use secret injection or generate fresh test credentials per lifecycle.

### Using an Admin User for All Tests

Mapping/query tests may need broad permissions, while authorization tests need identities with realistic roles. Separate test credentials by responsibility.

### Checking Only Successful Requests

Overly broad roles or disabled TLS validation go unnoticed. Add negative tests for wrong CA, wrong hostname, wrong password, and missing privileges.

### Changing the JVM Truststore Between Tests

Global SSL properties affect other clients and tests running in parallel. Prefer a dedicated SSL context for the Elasticsearch client.

### Stopping the Container While a Spring Context Still Uses It

The context cache may hold a client pointing to a stopped container. Align lifecycles between containers and test contexts.

### Using Production Certificates or Secrets in Tests

Test logs, reports, and artifacts can expose credentials. Only use CAs, keys, and credentials dedicated to testing.

## 25. Implementation Workflow

When providing dynamic configuration, certificates, and credentials for Spring Data Elasticsearch tests:

1. Choose the test type: repository integration, TLS, authentication, authorization, or mTLS.
2. Pick a compatible Elasticsearch image/version and pin it.
3. Start the container or test service before Spring creates the context.
4. Retrieve URI/host/port from the fixture instead of hardcoding.
5. Register endpoints and custom properties using `@DynamicPropertySource` or `@ServiceConnection` as appropriate.
6. Create test users/API keys with least-privilege permissions.
7. Provide the CA certificate so the client verifies the HTTPS server.
8. Ensure the hostname in the URI matches the server certificate's SAN.
9. If using mTLS, provision client certificate/private key and configure server trust/PKI realm separately.
10. Create a dedicated SSL context for the Elasticsearch client.
11. Run positive and negative tests for TLS, authentication, and authorization.
12. Never use trust-all, never disable hostname verification, and never use production credentials.
13. Use a dedicated test index prefix.
14. Close clients/containers, delete temporary files, and revoke API keys when needed.
15. Monitor logs without printing credentials, private keys, or Authorization headers.

## References

- [Spring Framework — DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
- [Spring Boot — Testcontainers and service connections](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Spring Boot — SSL bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Spring Data Elasticsearch — Client configuration](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html)
- [Testcontainers — Elasticsearch module](https://java.testcontainers.org/modules/elasticsearch/)
- [Elasticsearch — Encrypt HTTP client communications](https://www.elastic.co/guide/en/elasticsearch/reference/current/configuring-stack-security.html)
- [Elasticsearch — API key authentication](https://www.elastic.co/guide/en/elasticsearch/reference/current/security-api-create-api-key.html)
- [Elasticsearch — PKI realm](https://www.elastic.co/guide/en/elasticsearch/reference/current/pki-realm.html)
- [Java — SSLContext API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLContext.html)

## Conclusion

Spring Data Elasticsearch tests should obtain endpoints, ports, credentials, and certificates from fixtures or secret sources at startup. Use `@DynamicPropertySource` to register URIs and dynamic values before Spring builds the client; use `@ServiceConnection` when supported by your Boot/Testcontainers version. With HTTPS, the client must trust the right CA and verify the hostname against the SAN; with mTLS, also provide client certificates/private keys and matching server configuration. Separate non-security tests from TLS/authentication/authorization suites, use least-privilege test users/API keys, never disable certificate validation, and never put production secrets in source, logs, or artifacts.
