# Authentication and TLS for Pulsar Connections

When Spring Cloud Stream uses the Apache Pulsar Binder, the application connects to Pulsar through the Pulsar client managed by Spring for Apache Pulsar. Production connections must protect both aspects: client **identity authentication** and **transport encryption via TLS**. After authentication, Pulsar also uses authorization to decide which resources that role may publish to, consume from, or administer.

In Spring Cloud Stream, `Supplier`, `Function`, or `Consumer` functions work with bindings; the Pulsar Binder maps bindings to topics. Pulsar connection settings usually live under `spring.pulsar.client.*`, while the binder's topic administration operations use Pulsar Administration with a separate admin configuration. Both client and admin must be configured properly when the application auto-provisions topics. Never place tokens, passwords, or private keys directly in source code or committed configuration files.

## 1. Three Protection Layers of a Pulsar Connection

Three concepts are often confused:

| Layer | Question to Answer | Mechanism |
|---|---|---|
| TLS transport | Is data in transit encrypted and is the server verified? | TLS, CA certificate, hostname verification |
| Authentication | Who is the client? | Token/JWT, OAuth2, mTLS, Athenz, Basic, or supported plugin |
| Authorization | What is the authenticated role allowed to do? | Pulsar authorization, tenant/namespace/topic permissions |

TLS protects confidentiality and integrity of data in transit, while also verifying the server via its certificate. Authentication binds a connection to a principal/role. Authorization checks that role's permissions on topics, namespaces, or administrative operations.

```text
Spring Cloud Stream application
          |
          v
Pulsar Binder
          |
          +---- PulsarClient ----------------------+
          |      pulsar+ssl://broker:6651          |
          |      TLS + authentication              |
          |                                         v
          |                                    Pulsar Broker
          |                                         |
          |                                  Authentication
          |                                         |
          |                                  Authorization / ACL
          |                                         |
          |                                  Topic / Subscription
          |
          +---- PulsarAdministration ---------------+
                 https://broker:8443                |
                 TLS + admin authentication         v
                                               Pulsar Admin API
```

Do not treat a successful connection as proof that authorization is configured properly. A client can authenticate successfully and still be rejected when publishing or consuming due to missing permissions.

## 2. Pulsar Binder Uses Spring Boot's Pulsar Configuration

The Pulsar Binder is built on Spring for Apache Pulsar. When the binder is on the classpath, a Spring Boot application can use `spring.pulsar.*` properties to configure the client and administration. Binder-level or binding-level producer/consumer properties are also supported to customize individual streams.

Binder dependency in Maven:

```xml
<dependency>
    <groupId>org.springframework.pulsar</groupId>
    <artifactId>spring-pulsar-spring-cloud-stream-binder</artifactId>
</dependency>
```

Gradle:

```groovy
dependencies {
    implementation 'org.springframework.pulsar:spring-pulsar-spring-cloud-stream-binder'
}
```

The dependency version must be compatible with the application's Spring Boot and Spring Cloud Stream release train. Use your project's BOM or dependency management to align versions; do not mix a different Pulsar client version with the binder version without verifying compatibility.

Binding example:

```yaml
spring:
  cloud:
    function:
      definition: publishOrder;processOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: persistent://acme/orders/orders.created
        processOrder-in-0:
          destination: persistent://acme/orders/orders.created
          group: order-processing
```

`destination` specifies the logical topic the binding uses. Authentication and TLS settings for the Pulsar client are placed under `spring.pulsar.client`; settings for the Pulsar Admin client are placed under `spring.pulsar.admin` in modern Spring Boot. The Admin URL property name may differ in older releases, so verify against your project's exact BOM and property metadata.

## 3. Distinguishing Pulsar Client and Pulsar Admin Endpoints

Pulsar has two commonly used connection interfaces:

| Component | Protocol | Example URL | Purpose |
|---|---|---|---|
| Broker binary protocol | `pulsar://` or `pulsar+ssl://` | `pulsar+ssl://pulsar.example.com:6651` | Producers and consumers send/receive messages |
| Admin HTTP API | `http://` or `https://` | `https://pulsar.example.com:8443` | Manage tenants, namespaces, topics, partitions, and permissions |

`spring.pulsar.client.service-url` is the URL for the Pulsar client. `spring.pulsar.admin.service-url` is the URL for the Admin client in current Spring Boot. In some older Spring for Apache Pulsar versions, the Admin URL property used the `spring.pulsar.administration.service-url` namespace. Do not declare two property names by guessing; check the property catalog for the version in use.

Example URL configuration with TLS:

```yaml
spring:
  pulsar:
    client:
      service-url: pulsar+ssl://pulsar.example.com:6651
    admin:
      service-url: https://pulsar.example.com:8443
```

Ports `6651` and `8443` are common TLS defaults, though they can be customized in a cluster. Always use the URLs, ports, and hostnames provided by the Pulsar operations team.

If the application only reads/writes pre-provisioned topics, it may not need to call the Admin API during startup. If the Pulsar Binder auto-creates topics or partitioned topics, the binder requires `PulsarAdministration`; in that case, the Admin endpoint and administrative permissions must be configured separately.

## 4. How Does TLS Protect Transport?

When the client uses `pulsar+ssl://`, data between the application and the broker travels over TLS. The client verifies the server certificate using the CA trust chain and hostname verification. For the Admin API, use `https://` to encrypt HTTP requests and responses.

```text
Client                                  Broker
  |                                       |
  |---- ClientHello --------------------->|
  |<--- Server certificate ---------------|
  |                                       |
  |  Verify CA chain and hostname         |
  |                                       |
  |---- TLS handshake completes ----------|
  |                                       |
  |==== Encrypted Pulsar protocol ========|
```

TLS server authentication verifies that the broker is the server the client intends to reach. If using mutual TLS (mTLS), the client also sends its own certificate so the broker authenticates the client's identity via certificate.

TLS does not automatically grant publish or consume permissions. After the TLS handshake completes, Pulsar still enforces authentication and authorization according to broker configuration.

## 5. Never Send Tokens Over Plaintext Connections

A token/JWT is a credential. If sent over a plaintext connection, anyone observing network traffic can capture the token and use it until it expires or is revoked. Therefore, when using token authentication, always enable TLS for Pulsar connections.

Do not use a production configuration like:

```yaml
spring:
  pulsar:
    client:
      service-url: pulsar://pulsar.example.com:6650
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
        param:
          token: ${PULSAR_TOKEN}
```

The example above only illustrates why tokens must not be sent over a plaintext URL. Production configurations use `pulsar+ssl://` together with CA trust and hostname verification.

## 6. Configuring Token/JWT Authentication

Token authentication is a common choice for service-to-service applications. The Pulsar client uses the `AuthenticationToken` plugin; the token represents a principal/role authenticated by the broker.

Spring Boot example:

```yaml
spring:
  pulsar:
    client:
      service-url: pulsar+ssl://pulsar.example.com:6651
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
        param:
          token: ${PULSAR_CLIENT_TOKEN}
```

`PULSAR_CLIENT_TOKEN` is supplied from a secret store or deployment environment. Never put real tokens in Git, Docker images, logs, or exception messages.

The broker must enable the corresponding authentication provider and configure the token verification key. Example with a JWT asymmetric key:

```properties
authenticationEnabled=true
authenticationProviders=org.apache.pulsar.broker.authentication.AuthenticationProviderToken
tokenPublicKey=file:///etc/pulsar/keys/token-public.key
```

The broker property names in the example above belong to `broker.conf` or `standalone.conf`; the key value and provider must match how the cluster issues tokens. With symmetric signing, the broker uses a secret key instead of a public key. Keep the private signing key exclusively in the token-issuing system, never distribute it to every application.

## 7. OAuth2 Authentication

Pulsar supports OAuth2 access tokens. The client uses the `AuthenticationOAuth2` plugin to obtain an access token from an authorization server using issuer, credentials, and audience details. The broker verifies the token according to the configured provider and trust settings.

Spring Boot configuration example:

```yaml
spring:
  pulsar:
    client:
      service-url: pulsar+ssl://pulsar.example.com:6651
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.oauth2.AuthenticationOAuth2
        param:
          issuerUrl: ${PULSAR_OAUTH_ISSUER_URL}
          privateKey: ${PULSAR_OAUTH_PRIVATE_KEY_URI}
          audience: ${PULSAR_OAUTH_AUDIENCE}
          scope: ${PULSAR_OAUTH_SCOPE:}
```

Plugin parameter names like `issuerUrl`, `privateKey`, and `audience` must match the exact casing expected by the plugin. Spring Boot does not apply relaxed binding to individual keys inside the `authentication.param` map. For example, `issuer-url` or `issuerurl` is not equivalent to `issuerUrl`.

If injecting values from environment variables, keep the camelCase keys in YAML and reference the environment variables in the values, as shown above. Do not use `issuerUrl` directly as an environment variable name because variable name normalization can lose internal uppercase letters.

The OAuth2 credential file or private key must be granted least-privilege read access to the application process. Issued tokens have an expiration; applications must handle token refresh and failures when the authorization server is temporarily unreachable.

## 8. Basic Authentication and Other Plugins

Depending on the cluster and installed plugins, Pulsar can support Basic, Athenz, SASL, or extended authentication mechanisms. Example Basic configuration in Spring Boot:

```yaml
spring:
  pulsar:
    client:
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationBasic
        param:
          userId: ${PULSAR_USER}
          password: ${PULSAR_PASSWORD}
```

Basic authentication does not encrypt credentials. Use it only over TLS and when the broker is configured with the corresponding provider. Do not assume every Pulsar cluster enables all plugins; broker and client must agree on the plugin class and parameters.

For Athenz, SASL, or custom plugins, parameters must follow the specific plugin documentation. Do not copy properties from the OAuth2 plugin to a different plugin.

## 9. TLS via `PulsarClientBuilderCustomizer`

Spring Boot auto-configuration in Spring for Apache Pulsar provides `PulsarClientBuilderCustomizer` to customize the Pulsar client builder. In current versions of Spring for Apache Pulsar, TLS/SSL is not fully represented by simple properties; a customizer may be needed to set CA certificates, client certificates, private keys, and verification policies.

Example enabling TLS server authentication only with CA trust:

```java
import org.apache.pulsar.spring.core.PulsarClientBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class PulsarClientTlsConfiguration {

    @Bean
    PulsarClientBuilderCustomizer pulsarClientTlsCustomizer() {
        return clientBuilder -> clientBuilder
            .allowTlsInsecureConnection(false)
            .enableTlsHostnameVerification(true)
            .tlsTrustCertsFilePath("/etc/pulsar/tls/ca.crt");
    }
}
```

The CA path must exist in the filesystem of the container/VM running the application. `allowTlsInsecureConnection(false)` enforces valid certificate checks; `enableTlsHostnameVerification(true)` checks that the hostname in the certificate matches the URL hostname.

Do not use `allowTlsInsecureConnection(true)` or disable hostname verification in production to bypass certificate errors. Fix the CA chain, SAN, or endpoint hostname instead.

## 10. Configuring TLS for the Pulsar Admin Client

The Pulsar Binder can use `PulsarAdministration` to create topics, partitions, or perform administrative tasks during binding initialization. The Admin client has its own builder customizer: `PulsarAdminBuilderCustomizer`.

Example:

```java
import org.apache.pulsar.spring.core.PulsarAdminBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class PulsarAdminTlsConfiguration {

    @Bean
    PulsarAdminBuilderCustomizer pulsarAdminTlsCustomizer() {
        return adminBuilder -> adminBuilder
            .allowTlsInsecureConnection(false)
            .enableTlsHostnameVerification(true)
            .tlsTrustCertsFilePath("/etc/pulsar/tls/ca.crt");
    }
}
```

The Client TLS customizer and Admin TLS customizer are two separate configurations. If the application configures only the client while the binder needs to provision topics via the Admin API, administrative operations may still fail because the Admin client lacks HTTPS/trust/authentication configuration.

When the cluster uses different certificates for the broker and admin endpoints, use the appropriate trust bundle for each customizer. Do not assume the same CA or certificate path applies to every cluster.

## 11. Mutual TLS (mTLS) with PEM Certificates

mTLS requires both sides to verify each other's certificates. The client must trust the broker's CA and present its own certificate/key. The broker must enable TLS, trust the CA that issued client certificates, and require a client certificate on connect.

Example client customizer with PEM:

```java
@Bean
PulsarClientBuilderCustomizer pulsarClientMtlsCustomizer() {
    return clientBuilder -> clientBuilder
        .allowTlsInsecureConnection(false)
        .enableTlsHostnameVerification(true)
        .tlsTrustCertsFilePath("/etc/pulsar/tls/ca.crt")
        .tlsCertificateFilePath("/etc/pulsar/tls/client.crt")
        .tlsKeyFilePath("/etc/pulsar/tls/client.key");
}
```

The Admin client also needs a certificate if the Admin endpoint requires mTLS:

```java
@Bean
PulsarAdminBuilderCustomizer pulsarAdminMtlsCustomizer() {
    return adminBuilder -> adminBuilder
        .allowTlsInsecureConnection(false)
        .enableTlsHostnameVerification(true)
        .tlsTrustCertsFilePath("/etc/pulsar/tls/ca.crt")
        .tlsCertificateFilePath("/etc/pulsar/tls/client.crt")
        .tlsKeyFilePath("/etc/pulsar/tls/client.key");
}
```

The client certificate must be signed by a CA trusted by the broker and must be valid. The private key must be protected like a secret; never place it in source control or image layers.

## 12. Configuring the Broker for mTLS

On the broker side, you must enable authentication, select the TLS authentication provider, and configure TLS listeners/certificates. Example key properties in `broker.conf`:

```properties
authenticationEnabled=true
authenticationProviders=org.apache.pulsar.broker.authentication.AuthenticationProviderTls

brokerServicePortTls=6651
webServicePortTls=8443

tlsTrustCertsFilePath=/etc/pulsar/tls/ca.crt
tlsCertificateFilePath=/etc/pulsar/tls/broker.crt
tlsKeyFilePath=/etc/pulsar/tls/broker.key

tlsRequireTrustedClientCertOnConnect=true
tlsAllowInsecureConnection=false
```

Port names may differ based on cluster setup. With Pulsar Proxy, configure corresponding TLS/authentication on the proxy and set up proxy roles per Pulsar guidelines. Do not change only the client URL to `pulsar+ssl://` without configuring the broker; both sides must enable TLS and agree on the CA/certificates.

## 13. Distinguishing TLS Server Authentication and mTLS

| Characteristic | TLS Server Authentication | Mutual TLS |
|---|---|---|
| Client verifies server certificate | Yes | Yes |
| Server verifies client certificate | Not required | Yes |
| Client needs its own certificate | Not required | Yes |
| Combined with token/OAuth2 | Yes | Possible, depending on architecture |
| Primary goal | Encrypt transport and verify broker | Add client authentication via certificate |

Tokens or OAuth2 can be used over standard TLS. mTLS is a way to authenticate the client; it is not synonymous with authorization. After the certificate identifies a role, the broker still requires policy rules to determine which resources that role may access.

## 14. Configuring Separate Authentication for the Admin Client

When the binder auto-provisions topics, the Admin client requires separate authentication. Spring Boot currently supports the `spring.pulsar.admin.authentication` branch; do not assume `spring.pulsar.client.authentication` automatically applies to the Admin client.

Example token authentication for both clients:

```yaml
spring:
  pulsar:
    client:
      service-url: pulsar+ssl://pulsar.example.com:6651
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
        param:
          token: ${PULSAR_RUNTIME_TOKEN}
    admin:
      service-url: https://pulsar.example.com:8443
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
        param:
          token: ${PULSAR_PROVISIONER_TOKEN}
```

Example using two tokens to separate privileges:

- `PULSAR_RUNTIME_TOKEN`: a role with permissions only to consume input topics and produce to output topics.
- `PULSAR_PROVISIONER_TOKEN`: a role allowed to create or inspect necessary resources within the assigned namespace.

If your organization prohibits applications from creating topics, infrastructure pipelines can pre-provision topics; the runtime client then only needs publish/consume permissions. Avoid using a superuser token for every application instance.

## 15. Authentication and Authorization on the Broker

Pulsar distinguishes between the authentication provider and the authorization provider. Authentication identifies the token role; authorization checks the role's operations on resources. If authentication is enabled without authorization, authenticated roles may have broad cluster permissions under default broker settings.

Example enabling authorization:

```properties
authenticationEnabled=true
authenticationProviders=org.apache.pulsar.broker.authentication.AuthenticationProviderToken
authorizationEnabled=true
superUserRoles=admin
```

The `admin` role is reserved for administrative tasks. The `order-stream` application should use a dedicated role and be granted permissions on the required namespaces/topics.

In Pulsar, a full topic name has the form:

```text
persistent://tenant/namespace/topic
```

Permissions can be granted at the namespace or topic level depending on the required scope. Granting at the namespace level is convenient when a service needs multiple topics in the same namespace; granting at the topic level provides tighter scoping.

## 16. Granting Produce and Consume Permissions by Least Privilege

Suppose an order-processing function:

```text
Input:  persistent://acme/orders/orders.created
Output: persistent://acme/orders/orders.enriched
Role:   order-stream
```

This role needs to consume the input and produce to the output. Example granting permissions at the namespace level:

```bash
pulsar-admin namespaces grant-permission acme/orders \
  --role order-stream \
  --actions consume,produce
```

If separating input and output into different namespaces, grant only `consume` on the input namespace and `produce` on the output namespace. Do not grant tenant admin or superuser permissions to a runtime role simply because the application needs to publish/consume.

Example permission matrix:

| Role | Namespace/Topic | Required Permissions |
|---|---|---|
| `order-stream` | `acme/orders` | Consume input and produce output |
| `order-provisioner` | `acme/orders` | Create/check topics per provisioning workflow |
| `platform-admin` | Cluster/tenant | Administer tenants, namespaces, policies, and permissions |

Actual permissions must be verified against the operations performed by the binder. Schema lookup, subscription administration, or topic provisioning may require additional permissions. Start with minimal permissions, run integration tests, and grant additional permissions only when specific authorization errors occur.

## 17. Binder Topic Provisioning and Admin API Permissions

The Pulsar Binder includes a topic provisioner. When a topic does not exist, the binder can create basic topics; for partitioned topics, the binder uses `PulsarAdministration` and the Admin API. Therefore, separate the permissions of the Pulsar client from those of the Admin client:

| Component | Task | Credential |
|---|---|---|
| `PulsarClient` | Publish/consume messages | Runtime token or certificate |
| `PulsarAdministration` | Create/inspect tenants, namespaces, topics, partitions per config | Admin/provisioning token or certificate |

If topics are pre-created via IaC, the runtime role may not need topic creation permissions. If the binder auto-provisions, the Admin client needs the appropriate permissions on the namespace. Do not solve provisioning failures by turning the runtime role into a superuser.

In Spring Cloud Stream, destinations are declared on bindings:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: persistent://acme/orders/orders.created
        processOrder-out-0:
          destination: persistent://acme/orders/orders.enriched
```

Client/Admin authentication and TLS are still configured through the corresponding Spring Pulsar client/admin properties and builder customizers.

## 18. Complete Configuration Template for Token + TLS

Example application using token authentication, TLS server verification, and separating the runtime token from the provisioning token:

```yaml
spring:
  pulsar:
    client:
      service-url: pulsar+ssl://pulsar.example.com:6651
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
        param:
          token: ${PULSAR_RUNTIME_TOKEN}
    admin:
      service-url: https://pulsar.example.com:8443
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
        param:
          token: ${PULSAR_PROVISIONER_TOKEN}

  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: persistent://acme/orders/orders.created
          group: order-processing
        processOrder-out-0:
          destination: persistent://acme/orders/orders.enriched
```

Add `PulsarClientBuilderCustomizer` and `PulsarAdminBuilderCustomizer` to configure CA trust, hostname verification, and certificates if needed. The Admin URL property name must match the project's Spring Boot/Spring Pulsar version.

## 19. Configuring TLS with Customizers for Both Client and Admin

Example Java configuration combining both customizers in the same class:

```java
import org.apache.pulsar.spring.core.PulsarAdminBuilderCustomizer;
import org.apache.pulsar.spring.core.PulsarClientBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class PulsarTlsConfiguration {

    @Bean
    PulsarClientBuilderCustomizer pulsarClientTlsCustomizer() {
        return builder -> builder
            .allowTlsInsecureConnection(false)
            .enableTlsHostnameVerification(true)
            .tlsTrustCertsFilePath("/etc/pulsar/tls/ca.crt");
    }

    @Bean
    PulsarAdminBuilderCustomizer pulsarAdminTlsCustomizer() {
        return builder -> builder
            .allowTlsInsecureConnection(false)
            .enableTlsHostnameVerification(true)
            .tlsTrustCertsFilePath("/etc/pulsar/tls/ca.crt");
    }
}
```

If using mTLS, add `tlsCertificateFilePath` and `tlsKeyFilePath` to both client/admin builders when the corresponding endpoints require client certificates. Ensure the file paths exist in the runtime container and the private key has least-privilege read permissions.

## 20. Managing Secrets and Certificates

Tokens, OAuth credentials, passwords, private keys, and client certificates are sensitive data. A production workflow should:

- Retrieve secrets from Vault, Kubernetes Secrets, a cloud secret manager, or platform secret injection.
- Avoid putting credentials in Git, source code, Dockerfiles, image layers, or log files.
- Never print tokens or private keys in exceptions, debug logs, or Actuator details.
- Use short-lived tokens and narrowly scoped roles.
- Schedule token/certificate rotation before expiration.
- Monitor certificate expiration dates and CA rotations.
- Revoke tokens/certificates when a service is decommissioned or during an incident.
- Restrict private key file read permissions to the application's UID/GID.
- Do not mount private keys into containers that do not need Pulsar access.

For OAuth2, credential files must be provisioned securely and be replaceable during rotation. For JWT, the private signing key belongs to the token-issuing system; the broker only needs the corresponding verification material. For mTLS, client private keys must not be shared across applications if distinct identities and independent revocation are required.

## 21. Hostname Verification and Certificate SAN

The server certificate must contain a Subject Alternative Name (SAN) matching the hostname the client uses in the URL. For example, if the client connects to `pulsar+ssl://pulsar.example.com:6651`, the certificate needs a SAN matching `pulsar.example.com`.

Common mistakes:

- The certificate only has internal DNS names while the client connects via IP.
- The client uses a DNS alias not listed in the SAN.
- The certificate is expired or not yet valid.
- An intermediate CA is missing from the trust chain.
- The client trusts the wrong CA or mounts the wrong certificate file.
- The Admin endpoint uses a different certificate than the broker endpoint.

Do not disable hostname verification to ignore these errors. Fix the certificate SAN, DNS, or URL so they match.

## 22. Proxies and TLS Termination

Some clusters have clients connect through a Pulsar Proxy or gateway. In that case, distinguish certificates and identities at each hop:

```text
Application -- TLS/auth --> Pulsar Proxy -- TLS/auth --> Broker
```

The proxy authenticates the client and then uses its own credentials to connect to the broker. The broker may need `proxyRoles` and forwarded original principal configuration. Both the proxy role and the original principal may need permissions on resources depending on authorization configuration.

When using mTLS through a proxy, the certificate the broker sees may be the proxy's certificate, not the original client's certificate. Proxy roles, original authentication data, and authorization configuration must follow Pulsar's guidelines; do not make the proxy role a superuser to avoid errors.

## 23. Testing Connections with the Pulsar CLI

Before debugging Spring Cloud Stream, you can use the CLI with the same endpoint, TLS, and credentials to isolate infrastructure issues from application configuration issues. Example token over TLS:

```bash
pulsar-client --url pulsar+ssl://pulsar.example.com:6651 \
  --auth-plugin org.apache.pulsar.client.impl.auth.AuthenticationToken \
  --auth-params 'token:<TOKEN_FROM_SECRET_STORE>' \
  produce persistent://acme/orders/orders.created \
  -m '{"eventId":"evt-1","orderId":"order-1"}'
```

Do not put real tokens in shell history or shared command logs. In production, prefer configuring the CLI via a protected client.conf file or administrative environment secret injection.

Test the Admin API using `pulsar-admin` with HTTPS and matching authentication. If the CLI cannot connect with the same certificate/role, the issue likely lies in the cluster, network, TLS, or permissions rather than Spring Cloud Stream.

## 24. Verifying Authorization with Real Operations

A connection test should verify at least:

1. The client opens a TLS connection to the broker.
2. The broker authenticates the token/certificate and resolves the expected principal.
3. The principal has `produce` permission on the output topic.
4. The principal has `consume` permission on the input topic/subscription.
5. The Admin principal has the required permissions if the binder auto-provisions topics.
6. Schema lookup/registration works if the application uses a schema registry or native Pulsar schemas.
7. The role cannot access topics/namespaces outside its granted scope.

Testing negative cases is equally important: use a role with only `consume` to try publishing and confirm the broker rejects it; use a role with only `produce` to try consuming and confirm it is rejected. This confirms ACLs are truly enforced.

## 25. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `Connection refused` | Wrong host/port, broker TLS listener not enabled, or network policy blocking | Check service URL, port, and broker listener |
| TLS handshake failure | Wrong CA, expired certificate, incompatible protocol/cipher | Check certificate chain and TLS config on both sides |
| Hostname verification failed | URL hostname does not match SAN | Fix DNS/URL or issue a certificate with the right SAN |
| Token authentication failed | Expired token, wrong signing key, or wrong provider | Check token issuer, key, and broker auth provider |
| OAuth2 token request failed | Wrong issuer URL, private key, audience, or clock skew | Check OAuth credentials and system clock |
| Plugin does not receive param | Wrong camelCase key name in map | Use exact parameter names such as `issuerUrl` |
| Client connects but publish is rejected | Role lacks `produce` permission | Grant least-privilege permission on output namespace/topic |
| Consume is rejected | Role lacks `consume` permission or subscription policy blocks | Check namespace/topic permissions and subscription |
| Binder startup fails when creating topic | Wrong Admin URL, missing Admin TLS/auth, or role lacks permissions | Configure Admin client separately and grant provisioning permissions |
| Producer runs but topic provisioning fails | Runtime token can publish, but Admin token lacks admin permissions | Separate runtime identity and provisioner identity |
| Client TLS works but Admin TLS fails | Only `PulsarClientBuilderCustomizer` present, missing Admin customizer | Configure `PulsarAdminBuilderCustomizer` |
| `401`/authentication error on Admin API | Admin credentials/provider mismatch | Check `spring.pulsar.admin.authentication` |
| `403`/authorization error | Principal is authenticated but lacks permissions | Check role and ACLs; do not switch to superuser |
| Works via proxy but rejected at broker | Incorrect proxy role/original principal or forwarded credentials | Check `proxyRoles` and original principal flow |
| Fails only after cert rotation | Client/admin customizer still uses old path or cached cert | Sync secret mounts, trust bundles, and restart/refresh as designed |

## 26. Integration Testing for TLS and Authentication

You should include integration test scenarios against a Pulsar cluster configured with production-equivalent security:

| Scenario | Action | Expected Result to Verify |
|---|---|---|
| TLS server verification | Connect with valid CA and matching hostname | Handshake succeeds |
| Untrusted CA | Use wrong CA | TLS handshake is rejected |
| Hostname mismatch | Use hostname not present in SAN | Hostname verification fails |
| Valid token | Connect with valid token | Broker authenticates principal |
| Expired/invalid signature token | Use invalid token | Authentication is rejected |
| OAuth2 credentials | Obtain token from valid issuer | Client connects and refreshes as configured |
| Valid mTLS | Use client certificate signed by trusted CA | Broker accepts certificate |
| Missing mTLS certificate | Omit client certificate when broker requires it | Handshake/authentication fails |
| Missing produce permission | Use consume-only role | Publish is rejected |
| Missing consume permission | Use produce-only role | Subscribe/consume is rejected |
| Admin client | Use provisioner credentials | Admin API executes permitted operations |
| Admin missing permissions | Use runtime role to create topic | Provisioning is rejected |
| Secret rotation | Rotate token/certificate per procedure | Application reconnects using new credentials |
| Proxy path | Connect through auth-enabled proxy | Broker receives right original principal and enforces authorization |

Function unit tests do not verify TLS handshakes or broker ACLs. These scenarios require a real broker or a Pulsar test environment configured with matching TLS/authentication/authorization.

## 27. Production Deployment Checklist

1. Identify compatible versions of Spring Boot, Spring Cloud Stream, and Spring for Apache Pulsar.
2. Use `pulsar+ssl://` for the binary client endpoint and `https://` for the Admin endpoint.
3. Provide a valid CA trust bundle and keep hostname verification enabled.
4. Choose the right authentication plugin: token, OAuth2, mTLS, or organization-supported plugin.
5. Enable the corresponding broker authentication provider.
6. Enable authorization and assign a dedicated role for the service.
7. Grant `consume` for inputs and `produce` for outputs; avoid runtime superuser roles.
8. Configure the Admin client separately if the binder auto-provisions topics.
9. Separate runtime client permissions from provisioner/admin permissions.
10. Use a secret manager or secret injection to supply tokens, passwords, and private keys.
11. Schedule token/certificate rotation and monitor expiration.
12. Verify SANs, CA chain, TLS ports, Admin ports, and proxy paths.
13. Test positive/negative authorization, TLS failures, and broker recovery.
14. Monitor authentication failures, authorization denials, reconnects, and certificate expiration.

## 28. Self-Check

- [ ] Distinguish TLS, authentication, and authorization.
- [ ] Distinguish Pulsar binary service URL from Admin HTTP URL.
- [ ] Configure `spring.pulsar.client.service-url` using `pulsar+ssl://`.
- [ ] Configure the `AuthenticationToken` token plugin.
- [ ] Configure the OAuth2 plugin with exact camelCase keys such as `issuerUrl`.
- [ ] Know when to use `PulsarClientBuilderCustomizer` for TLS.
- [ ] Configure `PulsarAdminBuilderCustomizer` separately when the Admin endpoint uses TLS.
- [ ] Distinguish TLS server authentication from mTLS.
- [ ] Enable the corresponding broker authentication provider.
- [ ] Enable authorization and grant least-privilege produce/consume permissions.
- [ ] Distinguish runtime credentials from Admin/provisioner credentials.
- [ ] Never store tokens/private keys in source code or logs.
- [ ] Verify hostname verification, CA chain, and certificate expiration.
- [ ] Design integration tests for TLS, authentication, and ACLs.

## Conclusion

To secure the Spring Cloud Stream Pulsar Binder, configure TLS for both the Pulsar client and Admin client, then select an authentication plugin such as token/JWT, OAuth2, or mTLS. Spring Boot provides `spring.pulsar.client.*` and `spring.pulsar.admin.*`; TLS often requires `PulsarClientBuilderCustomizer` and `PulsarAdminBuilderCustomizer` to configure trust certificates, hostname verification, and client certificates. The broker must enable the matching provider along with authorization to restrict roles by topic/namespace. The runtime client only needs permissions to consume inputs and produce outputs; the Admin client uses a separate identity if the binder auto-provisions. Protecting secrets, verifying hostnames, rotating tokens/certificates, and testing both allowed and denied cases are essential steps before production deployment.

## References

- Spring Cloud Stream — Pulsar Binder: https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html
- Spring Boot — Apache Pulsar Support: https://docs.spring.io/spring-boot/reference/messaging/pulsar.html
- Spring for Apache Pulsar — Pulsar Client and Authentication: https://pulsar.apache.org/pulsar-spring/reference/pulsar/pulsar-client.html
- Apache Pulsar 5.0 — Authentication using mTLS: https://pulsar.apache.org/docs/5.0.x/security-tls-authentication/
- Apache Pulsar 5.0 — Authentication using JWT: https://pulsar.apache.org/docs/5.0.x/security-jwt/
- Apache Pulsar 5.0 — Authentication using OAuth2: https://pulsar.apache.org/docs/5.0.x/security-oauth2/
- Apache Pulsar 5.0 — Authentication and Authorization: https://pulsar.apache.org/docs/5.0.x/security-authorization/
