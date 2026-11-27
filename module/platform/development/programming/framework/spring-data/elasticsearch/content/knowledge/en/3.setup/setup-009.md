# Identifying Connection, Certificate, and Version Incompatibility Errors

A Spring Data Elasticsearch application may compile successfully yet fail to reach Elasticsearch at runtime. Causes generally fall into four categories: the application cannot reach the cluster address, TLS cannot establish a trusted connection, authentication credentials or permissions are invalid, or client and server components are incompatible.

An effective troubleshooting approach is to identify which layer failed before changing configuration. A DNS failure cannot be fixed by swapping certificates; an HTTP authentication failure cannot be fixed by upgrading library versions; and a `NoSuchMethodError` is usually unrelated to networking.

This lesson explains how to identify each error category in a Spring Data Elasticsearch application, how to gather evidence, and how to fix configuration safely for operations.

## 1. Mapping the Connection Path to Inspect

In a Spring application, business code typically calls a repository or `ElasticsearchOperations`. Spring Data classes translate operations into requests for the Elasticsearch Java API Client or the client configured for your project version. The underlying transport exchanges HTTP/HTTPS traffic with an Elasticsearch node.

A conceptual connection path:

~~~text
Controller / Service
        |
        v
Spring Data Repository / ElasticsearchOperations
        |
        v
Query and mapping conversion
        |
        v
Elasticsearch Java API Client
        |
        v
HTTP transport + connection pool + TLS
        |
        v
DNS / network / load balancer / proxy
        |
        v
Elasticsearch node or cluster
~~~

Failures can occur at any boundary:

- **Application:** URI configuration, active profile, environment variables, or dependencies did not load as expected.
- **Network:** hostname does not resolve, port is closed, or routing/firewalls block connections.
- **TLS:** server certificate is untrusted, hostname mismatches, certificate expired, or handshake fails.
- **HTTP authentication/authorization:** server returns 401 or 403.
- **Software compatibility:** Spring Boot, Spring Data Elasticsearch, Java API Client, and Elasticsearch server are not a supported combination.

Before changing anything, record when the failure occurred, the runtime environment, the endpoint the application actually uses, dependency versions, and the full exception stack trace. The final log line is often only a wrapper around a deeper root cause.

### Distinguishing Startup Errors from API Call Errors

Some projects verify connectivity at startup, while others only open connections when the first query runs. Accordingly:

- If the application stops during startup, check bean configuration, dependencies, SSL context, and health checks.
- If the application starts normally but the first request fails, check DNS, network, TLS, authentication, and the endpoint.
- If only one specific query fails, check request DSL, mapping, index permissions, and compatibility of the invoked API.
- If errors appear after an upgrade, compare the dependency tree and server version before and after the change.

Do not conclude the application connected successfully just because the Spring context started. Some clients instantiate objects without opening a connection to the server yet.

## 2. Checking Address, DNS, and Network Path

The application must connect to the right protocol, hostname, and port for Elasticsearch. On TLS-enabled clusters, the endpoint normally uses HTTPS; if the application sends plain HTTP to an HTTPS-only port, the server may close the connection or return a protocol error.

Example URI configuration:

~~~properties
spring.elasticsearch.uris=https://es.example.internal:9200
~~~

This is an illustrative address. In real systems, use the hostname and port provided by the deployment environment. If there are multiple nodes, configuration can list multiple URIs using the syntax supported by your Spring Boot version.

### Points to Confirm

1. Does the hostname match the environment: local, Docker Compose, Kubernetes, staging, or production?
2. Does DNS resolve the hostname from the exact machine/container running the application?
3. Is the port reachable from the application's network namespace?
4. Is the application using HTTP or HTTPS matching the node's configuration?
5. Is there a proxy, load balancer, ingress, or service mesh in between?
6. Does the endpoint require a path prefix?
7. Is the cluster starting up, recovering, or overloaded?

An address like `localhost:9200` means different things depending on where code runs. Inside an application container, `localhost` points to the application container itself, not the Elasticsearch container. With Docker Compose, use the service name on the shared network; in Kubernetes, use the Service DNS name.

### Distinguishing Common Network Errors

| Symptom | Likely Meaning | What to Check |
|---|---|---|
| UnknownHostException | DNS cannot resolve the hostname | Check DNS, service name, and namespace |
| Connection refused | Host is reachable, but port is not accepting connections | Check port, service, listener, and node state |
| ConnectTimeoutException | Failed to establish connection within allowed time | Check firewall, routing, endpoint, and network load |
| SocketTimeoutException | Connection may exist, but operation waited too long | Check server, query, network, and socket timeout |
| No route to host | No network route to destination | Check routing, network policy, and firewall |
| Connection reset/closed | Connection closed mid-stream | Check protocol, proxy, TLS, and server logs |

Connect timeout and socket/read timeout govern two distinct phases. Raising both to large values will not fix bad DNS or blocked ports. Only adjust timeouts after confirming the operation is valid and the current wait window is simply too short.

### Testing the Endpoint from the Application's Runtime Environment

Run diagnostic commands from the same machine or container where the application actually runs. Testing from a developer laptop does not prove a production pod shares the same network path.

For an HTTPS endpoint with an internal CA, test with curl:

~~~bash
curl --cacert ./ca.crt https://es.example.internal:9200/
~~~

If the endpoint uses Basic Authentication, supply credentials securely via your shell environment or secret manager. Never write passwords directly into command history or shared documentation.

On Linux, inspect TLS and the certificate chain using:

~~~bash
openssl s_client -connect es.example.internal:9200 -servername es.example.internal -showcerts
~~~

These commands only verify the path from the environment running the command. They do not replace verifying that the application loads the right configuration and trust store.

## 3. Identifying TLS and Certificate Errors

TLS protects HTTPS connections by verifying server identity and encrypting exchanged traffic. When a client connects to Elasticsearch over HTTPS, Java must build a trust chain from the server certificate to a CA trusted by the client, and verify the hostname the application is calling.

A handshake can fail even when the port is open and the server is healthy.

### Certificate Chain and CA Trust

A server typically presents its own certificate along with any required intermediate certificates. The client validates that chain to determine whether the certificate was signed by a trusted CA.

Concepts to distinguish:

- **Server certificate:** certificate presented by Elasticsearch upon receiving a TLS connection.
- **CA certificate:** certificate of the issuing authority trusted by the client.
- **Intermediate certificate:** intermediate certificate linking the server certificate to the root CA.
- **Trust store:** where Java or an SSL context stores trusted CAs/certificates.
- **Private key:** secret key paired with a server or client certificate; not something placed into a client trust store merely to verify the server.

If Elasticsearch uses an internal CA or self-signed certificate, the JVM's default trust store may not trust it. The client may then report:

~~~text
javax.net.ssl.SSLHandshakeException
sun.security.validator.ValidatorException:
PKIX path building failed
unable to find valid certification path to requested target
~~~

This message indicates Java could not construct a trusted certificate path. Obtain the proper CA certificate from your administrator or certificate authority and configure the client to trust it.

Do not download an arbitrary certificate from a failing endpoint and blindly trust it without verifying its origin. If a certificate was swapped by an impostor endpoint, blind trust defeats TLS authentication.

### Hostname Verification and Subject Alternative Name

Trusting the CA is not enough. The certificate must also be valid for the hostname used by the client.

For example, the application connects to:

~~~text
https://es.example.internal:9200
~~~

The server certificate needs a Subject Alternative Name (SAN) matching `es.example.internal`. If the certificate only has a SAN for `localhost` or a different hostname, the client may reject the connection even if the CA is trusted.

Common cases:

- Application connects by IP while the certificate only lists DNS names.
- Application uses a load balancer alias while the certificate only lists node names.
- Certificate was issued for a staging domain while the application uses a production domain.
- DNS points to another node carrying an unsuitable certificate.

The proper fix is to use a hostname matching the certificate or issue a certificate whose SAN covers the hostname the application needs. Do not disable hostname verification to hide this error.

### Expired or Not-Yet-Valid Certificates

Certificates have a validity period. If a certificate is expired or system clocks are significantly skewed, Java may reject the handshake.

Check:

- Not Before and Not After dates on the certificate.
- System clock and NTP synchronization on the host/container.
- Whether the certificate was rotated across all nodes or load balancers.
- Whether the application retains old connection pools after certificate rotation.

When rotating certificates, plan trust store updates, appropriate client reloads/restarts, and verification that every endpoint serves the new certificate.

### Other TLS Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| PKIX path building failed | Untrusted CA or missing intermediate | Install the complete CA chain in the trust store |
| No subject alternative DNS name matching | Hostname missing from SAN | Use matching hostname or reissue certificate |
| CertificateExpiredException | Certificate expired | Issue and deploy a new certificate |
| protocol_version or handshake_failure | TLS version/cipher mismatch or handshake misconfiguration | Align TLS policies across JVM, proxy, and server |
| bad_certificate | Invalid client certificate in mTLS or server rejected certificate | Check client certificate, chain, and mTLS config |
| certificate_unknown | One side does not trust the other's certificate | Check trust stores and handshake logs on both sides |

If mutual TLS (mTLS) is enabled, the client must also present a certificate and prove ownership of the corresponding private key. This is distinct from the client trusting the server certificate. Confirm whether the cluster requires standard HTTPS or also requires a client certificate.

### Configuring a Trust Store for Java

A common deployment approach is placing the CA certificate into an application-specific Java trust store. Example creating a PKCS12 trust store from a CA certificate:

~~~bash
keytool -importcert \
  -alias elasticsearch-ca \
  -file ca.crt \
  -keystore es-truststore.p12 \
  -storetype PKCS12
~~~

The command prompts for a trust store password and certificate confirmation. Only confirm after verifying the certificate fingerprint and source.

If configuring the JVM to use this trust store, for example:

~~~text
-Djavax.net.ssl.trustStore=/run/secrets/es-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Exact configuration depends on how the client is constructed. A client with a custom SSL context might ignore the JVM's default trust store. In that case, configure the SSL context/trust material directly on the client or use the SSL bundle mechanism supported by your Spring Boot version.

With Spring Boot, prefer the SSL bundle and client integration mechanism provided by your version when available. Property names and how bundles bind to the Elasticsearch REST client vary across Boot versions; consult the reference documentation for your exact version rather than copying properties from another project.

### Conceptual Java Configuration Example

A client configuration can express connection target, SSL context, and Basic Authentication as follows:

~~~java
// Conceptual example: exact ClientConfiguration/SSL context setup
// depends on the Spring Data Elasticsearch version.
ClientConfiguration configuration = ClientConfiguration.builder()
    .connectedTo("es.example.internal:9200")
    .usingSsl(sslContext)
    .withBasicAuth(username, password)
    .build();
~~~

The critical requirement is that `sslContext` is built from verified trust material with hostname verification intact. Never use a trust-all manager in real environments. Actual builder APIs may differ across client generations; inspect your project's documentation and dependencies.

### Why You Should Not Disable SSL Verification

Some test guides suggest trust-all managers, `NoopHostnameVerifier`, or flags that skip certificate validation. Those may make a short experiment succeed, but they eliminate server verification. The client could then send encrypted traffic to a wrong endpoint or a spoofed intermediary.

If you need to quickly confirm whether an issue is TLS-related, use a dedicated diagnostic tool in an isolated environment and only briefly. Never commit configurations that skip SSL verification, never bake them into deployment images, and never treat disabling checks as a fix.

## 4. Distinguishing TLS from Authentication and Authorization

TLS establishes a secure channel. Afterward, Elasticsearch may still require authentication and check permissions.

HTTP status codes help isolate the layer:

- 401 Unauthorized: missing credentials, wrong credentials, expired token, or incorrect authentication mechanism.
- 403 Forbidden: identity was verified, but lacks permission for the requested operation.
- TLS error prior to receiving any HTTP response: communication never reached Elasticsearch's Basic Auth or index permission checks.

Example URI configuration with externally supplied credentials:

~~~properties
spring.elasticsearch.uris=https://es.example.internal:9200
# Username/password loaded from a secret manager or environment variables.
~~~

Verify property names against your Spring Boot version. Supply username/password from a secret manager or platform-managed environment variables; never write passwords into Git, shared config files, or logs.

An account may authenticate successfully yet lack permission to search an index. Verify the corresponding roles, index privileges, and API privileges. Do not grant broader cluster-wide privileges than the application needs just to silence a 403 error.

### Quick Differentiation Table

| Observation | Likely Failure Layer |
|---|---|
| No HTTP status received, `SSLHandshakeException` | TLS/certificate |
| No HTTP status received, `UnknownHostException` | DNS |
| HTTP 401 | Authentication |
| HTTP 403 | Authorization |
| HTTP 404 for index or endpoint | Index name, API path, anonymous access rules, or missing API |
| HTTP 400 with query parse error | Request DSL, mapping, or API payload |
| HTTP 5xx | Server, cluster, shard, or proxy |

For HTTP 404, read the response body and server logs before concluding. Elasticsearch can return different details depending on the API, permissions, and security setup.

## 5. Identifying Version Incompatibilities

Spring Data Elasticsearch sits within the Spring Data ecosystem. The application also depends on Spring Boot, Spring Framework, the Elasticsearch Java API Client, and the Elasticsearch server. These components release on independent cadences, so you cannot look at one version number and guess whether the entire stack is compatible.

A typical stack consists of these layers:

| Component | Role |
|---|---|
| Spring Boot | Manages application configuration and default dependencies |
| Spring Data Elasticsearch | Repository abstractions, mappings, and operations |
| Elasticsearch Java API Client (elasticsearch-java) | Java API and request/response types |
| HTTP transport/REST client | Sends requests over HTTP/HTTPS |
| Elasticsearch server | Receives and executes APIs on the cluster |

Additionally, another library in the application might transitively pull in a different Elasticsearch client version. That is why inspecting the runtime dependency tree is essential rather than only reading `build.gradle` or `pom.xml`.

### Checking the Compatibility Matrix

When selecting versions, consult the official compatibility documentation of Spring Data Elasticsearch and Elasticsearch for your exact release train. Check at minimum:

1. The running Spring Boot version.
2. The Spring Data Elasticsearch version managed by Boot or declared explicitly.
3. The `elasticsearch-java` version actually present on the runtime classpath.
4. The cluster's Elasticsearch server version.
5. The Java runtime version required by these libraries.

Do not assume every newer client is compatible with every older server, or that upgrading `elasticsearch-java` alone suffices. Spring Data may rely on specific Java client types and APIs.

### Preferring Spring Boot Dependency Management

In Spring Boot applications, Boot's dependency management selects Spring Data and related libraries that have been tested together. Unless there is a specific requirement, keep that managed version set.

Gradle example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-elasticsearch'
}
~~~

Maven example:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-elasticsearch</artifactId>
</dependency>
~~~

Do not arbitrarily specify an `elasticsearch-java` version if the starter already manages it. If overriding is necessary, confirm the version fits a supported combination and check transitive dependencies as well.

### Avoiding Mixing Client Generations

Legacy projects may use `RestHighLevelClient`; modern projects use the Elasticsearch Java API Client. These are distinct APIs and configuration models.

Signs of mixed clients or dependencies:

- Code imports classes from `org.elasticsearch.client.RestHighLevelClient` while configuration only creates a Java API Client.
- Runtime contains multiple generations of `elasticsearch-rest-client` or Elasticsearch modules with mismatched versions.
- Another library pulls an old client version into runtime.
- Spring Data was upgraded while custom client configuration still uses removed or changed APIs.
- Code compiles against one dependency graph while the application runs with a different classpath.

Do not keep both client generations around merely because part of the legacy code has not been migrated. If migrating, scope usage of each client, plan the conversion, and remove the legacy dependency once no callers remain.

### Common Errors from Dependency Mismatches

| Exception or Symptom | Likely Meaning |
|---|---|
| ClassNotFoundException | Class is missing from the runtime classpath |
| NoClassDefFoundError | Class was referenced at compile time but cannot be loaded at runtime |
| NoSuchMethodError | Class exists, but runtime version lacks the method expected by caller |
| NoSuchFieldError | Field does not exist in the loaded version of the class |
| AbstractMethodError | Implementation does not match the runtime interface/abstract class |
| Compile errors with `co.elastic.clients...` | Java API Client missing or version lacks the invoked API |
| HTTP 400 reporting unsupported API parameter | Request uses a feature or parameter incompatible with the server |
| Response parse/deserialization error | Client and server differ on schema/API response, or data differs from expectations |

`NoSuchMethodError` is strong evidence of binary incompatibility on the classpath. Raising timeouts or changing URIs will not resolve it.

### Inspecting the Dependency Tree

With Gradle, view Elasticsearch dependencies at runtime:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

To see why a specific version was selected:

~~~bash
./gradlew dependencyInsight \
  --dependency elasticsearch-java \
  --configuration runtimeClasspath
~~~

You can similarly inspect `spring-data-elasticsearch`, `elasticsearch-rest-client`, and related modules. With Maven:

~~~bash
mvn dependency:tree
~~~

Focus on the final resolved versions, which dependency pulled them in, and conflict/omitted lines. A directly declared dependency is not always the version chosen at runtime.

### Verifying the Server Version

You can query the cluster's root endpoint:

~~~http
GET /
~~~

The response usually contains `version.number`, alongside cluster name and node name. Record the actual version from the exact endpoint the application connects to. In a cluster behind a load balancer or with multiple nodes, also confirm nodes share compatible versions during rolling upgrades per support policies.

If the application uses a managed Elasticsearch service, retrieve the version and API limitations from the provider's documentation or console.

## 6. Checking Spring Boot Configuration and Profiles

A common mistake is having a valid config file while the application runs under a different profile or has values overridden by environment variables.

Example configuration:

~~~yaml
spring:
  elasticsearch:
    uris: https://es.example.internal:9200
    connection-timeout: 2s
    socket-timeout: 10s
~~~

Property names in examples must be verified against your actual Spring Boot version. Across releases, SSL bundles, transport, and custom client configuration may differ. Usernames and passwords should be loaded from external secret sources.

Verify:

- Which profile is active.
- Final URI after placeholder resolution.
- Whether environment variables exist inside the process/container.
- Whether any custom Java configuration overrides auto-configuration.
- Whether multiple client/operations beans exist simultaneously.
- Whether secret mounts have the right paths and read permissions.
- Whether the application is running the latest image/build rather than a stale artifact.

Never print passwords, private keys, or secret contents into logs for debugging. You may log hostname, port, scheme, active profile, client version, and whether credentials are configured without exposing secret values.

### When Using Custom Configuration

If the project constructs its own client, determine which bean is injected into `ElasticsearchOperations` and repositories. URI settings in `application.yml` might not affect a manually created client.

Trace bean wiring:

- Where is the client created?
- Where does the SSL context load trust material from?
- At which layer is Basic Auth/API key attached?
- Which client does the operations bean use?
- Is `@Primary` or a qualifier causing a service to receive the wrong bean?

Only modify one configuration source after confirming which beans are active. When two configurations compete, editing properties files may have no effect on runtime behavior.

## 7. Step-by-Step Diagnostic Procedure

Follow this order to avoid changing multiple variables at once.

### Step 1: Collect Evidence

Record the full exception, nested causes, HTTP status, and response body if present. Record the endpoint, scheme, profile, and versions of Java, Spring Boot, Spring Data Elasticsearch, Java client, and Elasticsearch server.

Do not put credentials, access tokens, private keys, or sensitive document payloads into shared logs.

### Step 2: Verify DNS and TCP

From the exact environment running the application, verify that the hostname resolves and the port accepts connections. If this fails, resolve DNS, routing, firewalls, service discovery, or the endpoint before looking at certificates.

### Step 3: Verify TLS

If the endpoint uses HTTPS, inspect the certificate chain, CA trust, SAN/hostname, certificate validity dates, and TLS policy. Use the CA from a trusted source and keep hostname verification enabled.

### Step 4: Verify HTTP Authentication

Once TLS succeeds, examine 401 and 403 separately. Verify credentials, tokens, roles, and index/cluster privileges.

### Step 5: Verify Versions and Dependencies

Read the `runtimeClasspath` dependency tree, cross-check the compatibility matrix, and check the server version. Resolve classpath conflicts before altering query code.

### Step 6: Inspect the Elasticsearch Request

If connectivity and the client work yet a query fails, inspect the request DSL, endpoint, mapping, and API support. An HTTP 400 query parse error is completely different from TLS failure or binary incompatibility.

### Step 7: Re-verify with a Minimal Operation

After fixing, test a lightweight request to the cluster or a simple query against a test index. Only then test business queries involving sorting, aggregations, highlighting, or pagination.

## 8. Comprehensive Troubleshooting Table

| Symptom | Layer to Check First | Evidence to Gather |
|---|---|---|
| UnknownHostException | DNS/service discovery | Hostname and resolution output from container |
| Connection refused | Port/listener | Endpoint, port, service status |
| Connect timeout | Network/firewall/routing | TCP connectivity check from runtime |
| PKIX path building failed | CA trust chain | Server chain, CA fingerprint, trust store |
| Hostname mismatch | SAN/hostname verification | Hostname called by app and certificate SANs |
| Certificate expired | Certificate lifecycle/clock | Validity period and system clock |
| TLS protocol/handshake failure | TLS policy | JVM version, TLS/cipher policy, server/proxy logs |
| HTTP 401 | Authentication | Auth mechanism and credential state |
| HTTP 403 | Authorization | Roles and index privileges |
| NoSuchMethodError | Runtime dependency conflict | Dependency tree and actual classpath |
| ClassNotFoundException | Missing dependency | Runtime classpath, packaging |
| HTTP 400 parse error | Query/API/mapping | Request body, server version, mapping |
| HTTP 5xx or shard failure | Elasticsearch cluster | Cluster health, shard state, server logs |

This table helps choose where to investigate first. One symptom can have multiple causes; always verify with the root exception and server-side logs.

## 9. Real-World Scenario Examples

### Scenario A: Containerized App Cannot Connect to `localhost:9200`

Log:

~~~text
java.net.ConnectException: Connection refused
~~~

The application runs in its own container while Elasticsearch runs in another container. `localhost` points to the application container itself, so the connection goes to the wrong target.

Resolution:

1. Identify the Docker network shared by both containers.
2. Use Elasticsearch's service name and internal port in the URI.
3. Confirm Elasticsearch listens on the appropriate interface.
4. Retest connectivity from inside the application container.

### Scenario B: HTTPS Reports `PKIX path building failed`

The application reaches the host and port, but Java does not trust the CA that signed Elasticsearch's certificate.

Resolution:

1. Obtain the CA certificate from a trusted administrative source.
2. Verify its fingerprint or issuing chain.
3. Add the CA to the trust store/SSL bundle used by the client.
4. Confirm that trust store is actually loaded at runtime.
5. Reconnect with hostname verification kept enabled.

If a hostname mismatch appears after adding the CA, that is a separate verification step: check SANs and the URI hostname.

### Scenario C: TLS Succeeds, but Server Returns 401

TLS established the HTTPS channel, yet Elasticsearch rejects the credentials or the client is not sending credentials as expected.

Resolution:

1. Confirm the authentication mechanism required by the cluster.
2. Check username/password or API key via your secret manager.
3. Check whether custom client configuration attaches credentials.
4. Confirm the application uses the right profile and client bean.
5. Never print secrets into logs to debug.

If the response is 403, check the principal's permissions on indices and APIs instead of repeatedly changing passwords.

### Scenario D: `NoSuchMethodError` Appears After Upgrading Dependencies

The application compiles, yet runtime loads a different class version than the one the calling library was compiled against.

Resolution:

1. Generate the dependency tree for `runtimeClasspath`.
2. Identify the dependency pulling in the unwanted Elasticsearch client version.
3. Check supported Spring Boot/Spring Data/client versions.
4. Remove overrides or lock versions to a compatible set.
5. Clean build and deploy the new artifact.
6. Verify the classpath in the actual runtime environment.

### Scenario E: Connection Succeeds, but Queries Return HTTP 400

The client and transport successfully delivered the request to the server. The problem likely lies in Query DSL syntax, a missing field, a wrong field type, or an API parameter unsupported by the server.

Resolution:

1. Capture the actual request body.
2. Run the request in Dev Tools against the exact cluster.
3. Check the field mapping.
4. Cross-check API parameters against the server version.
5. Fix the query or upgrade according to the compatibility matrix if needed.

## 10. Operational and Security Principles

**Manage certificates as part of the deployment lifecycle.** Track expiration dates, issuers, SANs, CA chains, and rotation schedules. Update trust material in sync with server certificate changes.

**Do not disable TLS verification in production.** Keep CA and hostname verification enabled. Never use trust-all managers or hostname verifiers that bypass checks.

**Protect secrets.** Store passwords, API keys, trust store passwords, and private keys in a secret manager or platform secret mechanism. Never commit them to repositories or write them to logs.

**Keep dependencies aligned.** Prefer Spring Boot dependency management and check the compatibility matrix before overriding or upgrading an individual module.

**Set intentional timeouts.** Connect timeout bounds connection establishment; socket/read timeout bounds response waiting. Choose values based on real latency and application SLAs.

**Observe errors on both sides.** Client logs reveal where the request failed; Elasticsearch and proxy logs confirm whether the server received the request. Use request IDs or correlation IDs when supported by your platform to correlate logs.

**Verify again after deployment.** Confirm the application uses the right URI, certificates, secrets, and dependencies of the new release. A working local setup is insufficient proof that containers or production share the same trust store and network.

## 11. Connection Incident Checklist

When receiving an error report from a runtime environment, walk through this checklist:

- [ ] Record the root exception and the full `Caused by` chain.
- [ ] Verify the actual URI: scheme, hostname, port, and path prefix.
- [ ] Verify DNS and TCP from the exact container/host.
- [ ] If HTTPS, check chain, CA, SAN, expiration, and TLS policy.
- [ ] Confirm whether authentication returned 401 or authorization returned 403.
- [ ] Record versions of Spring Boot, Spring Data, Java client, and server.
- [ ] Inspect the `runtimeClasspath` dependency tree.
- [ ] Confirm which client/operations bean is actually in use.
- [ ] Execute a minimal test request and read the response body.
- [ ] Re-verify after deployment, not solely on a developer machine.

Each step rules out one layer of potential causes. Once you know whether a request stops at DNS, TCP, TLS, HTTP authentication, API parsing, or runtime linkage, you can fix the exact configuration or dependency causing the incident.
