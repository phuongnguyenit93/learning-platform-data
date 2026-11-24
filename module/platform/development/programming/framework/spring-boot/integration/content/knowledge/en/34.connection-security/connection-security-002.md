# SSL Bundles, Keystores, Truststores, and `spring.ssl.bundle.*` Configuration

## 1. The Problem: Multiple TLS Connections, Multiple Certificate Types

A Spring Boot service may simultaneously:

- Receive HTTPS from an API gateway or other applications.
- Call partner APIs using `RestClient` with a private CA.
- Connect to a broker, database, or cache over TLS.
- Use **mutual TLS (mTLS)** to prove workload identity to an internal system.

If every HTTP client, driver, and embedded server independently reads different certificate/private key paths, configuration becomes hard to audit, hard to vary across environments, and error-prone during certificate rotation.

Spring Boot provides **SSL bundles** to name a set of cryptographic material and TLS options, allowing supported components to **reference the same bundle by name**. The two common declaration styles are **PEM** and **JKS/PKCS12**, placed under `spring.ssl.bundle.*`.

In the **SPRING_BOOT_INTEGRATION** module, this ties directly to real integration boundaries: an HTTP adapter pointing to the wrong truststore may fail to connect; a consumer unable to authenticate a broker may stop receiving events; automatic retries may amplify load during a TLS configuration outage. This lesson focuses on **how to organize and apply SSL bundles** alongside understanding keystores, truststores, mTLS, configuration, testing, and operations.

### After This Lesson, You Can

1. Explain the differences between **keystore**, **truststore**, private key, CA certificate, and SSL bundle.
2. Create PEM and JKS/PKCS12 bundles via `spring.ssl.bundle.*`.
3. Use a bundle as an HTTPS server identity, or as trust material or client identity for `RestClient`.
4. Understand when a bundle **does not automatically apply** to a JDBC, cache, broker, or other HTTP library.
5. Diagnose missing CA, wrong hostname, wrong private key, unreadable secret files, and duplicate configurations.
6. Design rotation workflows, test with real TLS sockets, protect keys, and monitor expiry.

> **Version scope:** Examples use Java 17+, Spring Boot **3.2–3.5**, and compatible Spring Framework versions. SSL bundles arrived in Spring Boot 3.1; `RestClientSsl` used in the examples is available in Spring Boot 3.2+. Some packages, properties, and APIs change in Spring Boot 4; consult the official documentation for your deployed version. Paths and certificates in examples are illustrative.

## 2. From Certificates to SSL Bundles

Before writing YAML, distinguish the following components.

| Component | What Does It Contain? | Role |
| --- | --- | --- |
| **Private key** | The secret key of an identity | Proves key possession; must be strictly protected |
| **Leaf certificate** | Public key, SAN, validity, issuer, CA signature, and usage attributes | Identifies a server or client |
| **Intermediate CA** | Intermediate CA certificate | Helps build a trust path to an accepted CA |
| **Trust anchor** | Root/intermediate CA or certificate explicitly trusted by the verifier | Trusted endpoint of a PKIX validation path |
| **Keystore** | Local identity: private key and associated certificate chain | Presented when a party must prove its own identity |
| **Truststore** | Trusted certificates/CAs for the remote peer | Verifies the peer's certificate chain |
| **SSL bundle** | Key/trust material and TLS options named by Spring Boot | Centralized configuration reused by supported components |

A PKCS12 file (`.p12`, `.pfx`) can store private keys, chains, and trusted certificates. However, **file format does not equal role**: keystore for identity and truststore for trust are two distinct responsibilities. A bundle tells Spring Boot which material serves each responsibility.

```mermaid
flowchart TD
    A["spring.ssl.bundle.*"] --> B["Named SSL bundle<br/>partner-client"]
    B --> C["Key material<br/>client certificate + private key"]
    B --> D["Trust material<br/>Partner CA"]
    B --> E["SSL options<br/>protocol/cipher if configured"]
    C --> F["TLS client authentication (mTLS)"]
    D --> G["Verify server certificate chain"]
    E --> H["SSLContext / supported client"]
    F --> H
    G --> H
    H --> I["RestClient → Partner HTTPS"]
```

A standard HTTPS client only needs **appropriate trust material** to verify the server. Only when the partner requires mTLS does the client also need its own certificate and private key. Conversely, a Spring Boot HTTPS server needs a **keystore** to present its server identity; if the server requires mTLS, it also needs a truststore to verify clients.

## 3. Why Use Bundles Instead of Declaring SSL Everywhere?

Without bundles, an application can accumulate scattered, hard-to-trace settings:

```text
HTTPS server           → key-store=/etc/tls/server.p12
Partner HTTP client    → manually builds SSLContext with /etc/tls/partner-ca.pem
Another HTTP client    → reads another cert directly from the filesystem
Cache client           → each environment uses a separate truststore
```

Bundles allow naming by **connection role**:

```text
public-api-server     → application's HTTPS server identity
partner-orders-client → trust partner CA + client certificate if mTLS
internal-db-client    → CA and identity for DB if driver supports it
```

Key benefits:

- **Centralized and consistent:** avoid repeating paths/passwords across multiple configuration layers.
- **Clear identity:** bundle names express the connection's target and responsibility.
- **Environment separation:** swap file paths, secrets, or certificates across local/staging/production with minimal Java code changes.
- **Controlled application:** supported servers and clients reference bundles; no need to alter the global JVM truststore.
- **Auditable:** clear visibility into which CAs a service trusts, which certificates it presents, and which endpoints a change affects.

A bundle is **not** a CA, does not self-sign certificates, does not automatically enforce hostname verification on every third-party client, and does not automatically enable TLS on all dependencies.

## 4. Structure of `spring.ssl.bundle.*`

Two main configuration branches:

```yaml
spring:
  ssl:
    bundle:
      pem:
        my-pem-bundle:
          # keystore / truststore / options / reload-on-update...
      jks:
        my-jks-bundle:
          # key / keystore / truststore / options...
```

Names like `my-pem-bundle` and `my-jks-bundle` are application-defined. When a component uses a bundle, it references **the name**, such as `server.ssl.bundle: public-api-server`.

### 4.1. Key Properties Table

| Configuration Branch | Typical Properties | Meaning |
| --- | --- | --- |
| `spring.ssl.bundle.pem.<name>.keystore` | `certificate`, `private-key` | Certificate chain and private key in PEM |
| `spring.ssl.bundle.pem.<name>.truststore` | `certificate` | CA/trust material certificates in PEM format |
| `spring.ssl.bundle.jks.<name>.keystore` | `location`, `password`, `type` | JKS/PKCS12 keystore file |
| `spring.ssl.bundle.jks.<name>.truststore` | `location`, `password`, `type` | JKS/PKCS12 truststore file |
| `spring.ssl.bundle.jks.<name>.key` | `alias`, `password` | Select key entry and key password when needed |
| `spring.ssl.bundle.<pem/jks>.<name>.options` | `enabled-protocols`, `ciphers` | Restrict protocols/cipher suites when supported by the consumer |

Some Spring Boot versions also support `reload-on-update` to watch SSL material file changes. This capability **depends on the consumer and server type**; do not assume every running HTTP client, JDBC driver, or pool will automatically swap its SSL context when a file changes. Section 13 explains how to use this carefully.

### 4.2. PEM vs. JKS/PKCS12

| Criterion | PEM | JKS/PKCS12 |
| --- | --- | --- |
| Format | Text content with `-----BEGIN CERTIFICATE-----` or `-----BEGIN PRIVATE KEY-----` | Binary key/certificate container; PKCS12 is the common choice |
| Deployment | Mount certificate, private key, and CA as separate files | Mount `.p12`/`.jks` file and password |
| Secret manager integration | Easy to provision individual files | Easy to provision a single password-protected container |
| Complexity | Must pair the right certificate chain with the private key | Must match store type, store password, key alias/password |
| During rotation | Swap cert/key/CA as a matching pair, verify reload | Swap store file or entry per procedure |

Neither PEM nor PKCS12 is **inherently more or less secure by default**. What matters is private key protection, file permissions, secret distribution, certificate lifetime, and peer verification settings.

## 5. PEM Configuration: Truststore Containing Only the Partner's CA

Suppose `order-service` calls `https://orders.partner.example` and the partner uses an internal CA. We need to **trust the server's CA** and do not yet need a client certificate.

```yaml
# src/main/resources/application.yml
spring:
  ssl:
    bundle:
      pem:
        partner-orders:
          truststore:
            certificate: file:/etc/order-service/tls/partner-ca-chain.pem

integration:
  partner:
    base-url: https://orders.partner.example
```

Meaning:

1. The bundle is named `partner-orders`.
2. `truststore.certificate` points to the CA/trust material verified by the organization.
3. There is no `keystore` because the partner does not currently require mTLS.
4. Files are mounted from deployment infrastructure instead of hardcoding the CA in source. Trusting an internal CA must follow a source and ownership verification process.

The `file:` path must exist **inside the machine/container running the application**. A path on a developer's laptop will not magically appear inside a Kubernetes pod. With `classpath:`, the file is packaged inside the JAR and changing it requires a build/deploy cycle; for sensitive data, use proper secret deployment.

### 5.1. CA Certificate vs. Server Certificate

When a server presents the chain:

```text
Leaf: orders.partner.example
    ↓ signed by
Intermediate: Partner Issuing CA
    ↓ signed by
Root: Partner Root CA
```

The client should trust **managed trust anchors**, typically the root or designated CA, and the server should present the required intermediates. Importing an unverified endpoint's leaf certificate into the truststore just to "make PKIX errors go away" is risky. Before adding a CA, verify its fingerprint and issuing authority via an independent channel.

**Do not assume a custom truststore automatically merges with the default JVM truststore.** A bundle trusting a private CA may not trust public CAs for another endpoint. Create bundles per upstream boundary rather than forcing all HTTPS clients to share one broad set of CAs.

### 5.2. TLS Still Must Verify the Hostname

The bundle supplies trust material for certificate chain verification. The HTTP client must still compare the **actual hostname called** against the SANs in the server's certificate. For URL `https://orders.partner.example`, a certificate with SAN `DNS:billing.partner.example` is **invalid** for this target name even if signed by the same CA.

Never disable hostname verification or use a trust-all `X509TrustManager`. On mismatch, fix the URL/certificate SAN or the TLS termination endpoint on the proxy/load balancer.

## 6. PEM for Mutual TLS: Adding Client Identity

The partner may require mTLS: beyond verifying the server, the partner will require the Spring Boot application to present a **client workload** certificate.

```yaml
spring:
  ssl:
    bundle:
      pem:
        partner-orders:
          truststore:
            certificate: file:/etc/order-service/tls/partner-ca-chain.pem
          keystore:
            certificate: file:/etc/order-service/tls/order-service-client-chain.pem
            private-key: file:/etc/order-service/tls/order-service-client.key
```

The main change from section 5 is the `keystore` branch:

- `certificate`: client certificate and chain required by the partner's policy.
- `private-key`: the **client's** corresponding private key, readable only by the workload owner.
- `truststore.certificate`: continues to verify the **server**.

The client certificate must be unexpired, have valid key usage (e.g., client authentication EKU when required), and be **signed by a CA trusted by the server**. Spring Boot still verifies the server hostname; mTLS does not make skipping server authentication safe.

```mermaid
sequenceDiagram
    participant APP as Spring Boot RestClient
    participant PARTNER as Partner HTTPS server
    APP->>PARTNER: TLS ClientHello (SNI)
    PARTNER-->>APP: Server certificate chain
    Note over APP: Truststore verifies CA and hostname in SAN
    PARTNER-->>APP: CertificateRequest (mTLS)
    APP->>PARTNER: Client certificate chain + proof of private key
    Note over PARTNER: Server truststore verifies client identity
    APP->>PARTNER: HTTP request after handshake
    PARTNER-->>APP: HTTP response
```

If the server only authenticates the client certificate without authorizing by role/tenant/scope, a valid identity could still access unauthorized data. **mTLS authenticates a workload; business authorization is a separate responsibility.**

## 7. Configuring a JKS/PKCS12 Bundle

Some organizations distribute private keys and certificate chains in PKCS12 format. Suppose we have:

```text
/etc/order-service/tls/order-service-client.p12
/etc/order-service/tls/partner-truststore.p12
```

Configuration:

```yaml
spring:
  ssl:
    bundle:
      jks:
        partner-orders:
          key:
            alias: order-service
            password: ${CLIENT_KEY_PASSWORD}
          keystore:
            location: file:/etc/order-service/tls/order-service-client.p12
            password: ${CLIENT_KEYSTORE_PASSWORD}
            type: PKCS12
          truststore:
            location: file:/etc/order-service/tls/partner-truststore.p12
            password: ${PARTNER_TRUSTSTORE_PASSWORD}
            type: PKCS12
```

Here `jks` is Spring Boot's **configuration group name** for Java KeyStore-style bundles. The `type: PKCS12` property specifies the actual container format; the legacy JKS format is not required.

The two password levels are not always identical:

- **Store password** opens/inspects the container.
- **Key password** accesses the private key entry, if that entry has a separate password.
- **Alias** selects the key entry in the keystore when multiple certificates/keys exist.

When a keystore contains only one key entry, the alias may not need to be specified. When the key password matches the store password, configuration can be simplified if allowed by the API/format. Do not guess aliases or passwords: inspect the container with the appropriate administration tool.

### 7.1. Creating a PKCS12 Truststore from a Verified CA

An illustrative command:

```bash
keytool -importcert \
  -alias partner-root-ca \
  -file partner-root-ca.pem \
  -keystore partner-truststore.p12 \
  -storetype PKCS12
```

Inspect contents:

```bash
keytool -list -v \
  -keystore partner-truststore.p12 \
  -storetype PKCS12
```

If you only need a **truststore**, you do not need to generate a private key for it. The import command above only adds a trusted certificate; it does not turn a public CA certificate into a client identity. When creating a **keystore for mTLS**, the private key must come from an approved identity provisioning process and never be committed to the repository.

**Note:** `keytool` may prompt for a password and ask for trust confirmation. Verify the CA fingerprint from an independent source before importing. Never put passwords in command-line arguments or CI logs when interactive prompts or secure secret mechanisms can be used.

### 7.2. PEM or PKCS12?

Both examples use the same bundle name `partner-orders` because they represent **two alternatives**, not two simultaneous configurations in the same application. Choose one approach and keep secret management consistent. Do not define the same bundle name under both `pem` and `jks` unless there is a specific reason and you understand how the framework handles name collisions.

## 8. Using an SSL Bundle for a Spring Boot HTTPS Server

In this example, the Spring Boot application itself is the **server** presenting a certificate to clients. The SSL bundle holds the server's private key and certificate:

```yaml
spring:
  ssl:
    bundle:
      pem:
        public-api-server:
          keystore:
            certificate: file:/etc/order-service/tls/api-server-fullchain.pem
            private-key: file:/etc/order-service/tls/api-server.key

server:
  port: 8443
  ssl:
    bundle: public-api-server
```

With a supported embedded web server, `server.ssl.bundle` references the named bundle and uses the corresponding material when creating the HTTPS listener. The server certificate must have SANs matching the name **clients use to connect** to that TLS endpoint. If an ingress/proxy terminates TLS in front, determine where TLS actually terminates; enabling TLS on the backend does not automatically configure TLS on the ingress.

### 8.1. Server Requiring a Client Certificate

To have the server authenticate clients with mTLS, add a truststore containing the CA that signs client certificates and set the client authentication mode:

```yaml
spring:
  ssl:
    bundle:
      pem:
        internal-api-server:
          keystore:
            certificate: file:/etc/order-service/tls/server-chain.pem
            private-key: file:/etc/order-service/tls/server.key
          truststore:
            certificate: file:/etc/order-service/tls/internal-client-ca.pem

server:
  port: 8443
  ssl:
    bundle: internal-api-server
    client-auth: need
```

`client-auth: need` requires a client certificate when supported by the embedded server. `want` can allow connections without a certificate, so it is unsuitable if policy mandates that every client must authenticate via mTLS. **Authorization** based on certificate principal and API rules must still be designed in Spring Security or an authorized layer.

### 8.2. Settings That Should Not Be Mixed

When using `server.ssl.bundle`, let **the bundle own the key/trust material**. Do not simultaneously mix legacy properties such as `server.ssl.key-store`, `server.ssl.key-store-password`, or `server.ssl.certificate` into the same server SSL configuration expecting the framework to pick the right one. Across Spring Boot versions, certain combinations are rejected or have unexpected precedence; the clearest rule is **use one SSL configuration style per endpoint**.

## 9. Using a Bundle for the Synchronous `RestClient` HTTP Client

On the outbound HTTP side, the application needs both the right `baseUrl` and the `partner-orders` bundle. Spring Boot 3.2+ provides `RestClientSsl` to apply an SSL bundle to the builder.

### 9.1. Configuring the URL with `@ConfigurationProperties`

```yaml
integration:
  partner:
    base-url: https://orders.partner.example
```

```java
// PartnerProperties.java
package example.integration.partner;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "integration.partner")
public record PartnerProperties(String baseUrl) {
}
```

In production, verify `baseUrl` is non-empty, starts with `https://`, uses an allowlisted host, and never comes from arbitrary user input. Using a valid truststore while allowing external requests to control the URL still creates SSRF risk.

### 9.2. Creating a `RestClient` Bean from the Spring Boot-Configured Builder

```java
// PartnerRestClientConfiguration.java
package example.integration.partner;

import org.springframework.boot.autoconfigure.web.client.RestClientSsl;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PartnerProperties.class)
public class PartnerRestClientConfiguration {

    @Bean("partnerRestClient")
    RestClient partnerRestClient(
            RestClient.Builder builder,
            RestClientSsl ssl,
            PartnerProperties properties) {

        return builder
                .baseUrl(properties.baseUrl())
                .apply(ssl.fromBundle("partner-orders"))
                .defaultHeader(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE)
                .build();
    }
}
```

Points to note:

1. `RestClient.Builder` is **injected by Spring Boot**, preserving shared `RestClientCustomizer` beans and appropriate integrations rather than always calling `RestClient.builder()` directly.
2. `RestClientSsl` retrieves the SSL bundle by name `partner-orders` and applies certificate/trust material to the client.
3. If the bundle includes a keystore containing client certificate/key, it can be used when the partner requires mTLS.
4. The built `RestClient` is reused, avoiding creating a new client and SSL context per HTTP request.

**Caution about request factory:** `builder.apply(ssl.fromBundle(...))` can replace a previous `ClientHttpRequestFactory` on the builder. If the application also needs connect/read timeouts, proxy, connection pooling, or a specific HTTP client, configure them **together** with SSL using version-compatible APIs and test both SSL and timeouts. Do not assume calling `requestFactory(...)` before or after `ssl.fromBundle(...)` preserves all settings.

### 9.3. The HTTP Adapter Should Only Know the Business Contract

```java
// PartnerOrdersClient.java
package example.integration.partner;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class PartnerOrdersClient {

    private final RestClient restClient;

    public PartnerOrdersClient(
            @Qualifier("partnerRestClient") RestClient restClient) {
        this.restClient = restClient;
    }

    public PartnerOrderDto getOrder(String id) {
        PartnerOrderDto response = restClient.get()
                .uri("/v1/orders/{id}", id)
                .retrieve()
                .body(PartnerOrderDto.class);
        if (response == null) {
            throw new IllegalStateException(
                    "Partner API returned an empty response");
        }
        return response;
    }
}

record PartnerOrderDto(String id, String status) {
}
```

The adapter does not load private keys manually, does not disable hostname verification, and does not let business services know how TLS contexts are built. Identity/trust configuration is managed at the client boundary. On connection errors, the adapter should distinguish TLS/configuration errors from HTTP 4xx/5xx and business data errors.

### 9.4. Multiple Partners Should Have Multiple Bundles

```yaml
spring:
  ssl:
    bundle:
      pem:
        partner-orders:
          truststore:
            certificate: file:/etc/tls/orders-ca.pem
        partner-shipping:
          truststore:
            certificate: file:/etc/tls/shipping-ca.pem
```

Two upstreams may have separate CAs, client certificates, lifetimes, and owners. Create separate `RestClient` beans per upstream and attach the right bundle to each client. Never reuse a **mutable stateful** builder to swap SSL bundles across upstreams sequentially without controlling cloning or separate builder injection.

## 10. Accessing `SslBundles` from the Application

Not every component has a built-in `ssl.bundle` property. Spring Boot provides an API to **look up a bundle by name**, enabling the application to integrate with a library that accepts an `SSLContext` or key/trust managers.

```java
package example.integration.security;

import javax.net.ssl.SSLContext;
import org.springframework.boot.ssl.SslBundle;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.stereotype.Component;

@Component
public class PartnerSslContextProvider {

    private final SslBundles sslBundles;

    public PartnerSslContextProvider(SslBundles sslBundles) {
        this.sslBundles = sslBundles;
    }

    public SSLContext createContext() {
        SslBundle bundle = sslBundles.getBundle("partner-orders");
        return bundle.createSslContext();
    }
}
```

Use this snippet only when the integration library **truly requires** an `SSLContext`. Clients directly supported by Spring Boot usually offer cleaner ways to attach bundles. Do not create a new `SSLContext` per message/request; consider lifecycle management and rotation behavior of the client using that context.

**Important:** an `SSLContext` with the right CA is not enough to guarantee hostname verification. Some libraries require separate endpoint identification configuration on the socket or HTTP client. When using a custom client, verify **both chain and hostname**, and do not assume hostname verification is enabled just because `createSslContext()` succeeds.

Depending on the version, `SslBundle` also exposes `getStores()`, `getManagers()`, and `getOptions()` for deeper integration. These are low-level APIs: prefer Boot-supported bundle mechanisms first to avoid managing `KeyManagerFactory`, `TrustManagerFactory`, and rotation manually.

## 11. Bundles and Non-HTTP Integrations

In real applications, keystores/truststores are also needed for databases, caches, and brokers. Distinguish:

| Integration | How to Consider Bundles | What to Verify |
| --- | --- | --- |
| Embedded HTTPS server | `server.ssl.bundle` | TLS port, cert SAN, client-auth, supported server |
| Spring Boot `RestClient` | `RestClientSsl` and injected builder | Request factory, timeout, trust/hostname, client cert |
| `WebClient` | Reactive client SSL mechanism per Spring Boot/Netty version | SSL provider, connection pool, TLS context |
| Redis | SSL/SSL bundle properties if starter and client are Boot-supported | Client driver, TLS endpoint, hostname/CA |
| JDBC / R2DBC | Driver-specific SSL properties or Boot-supported bundle mechanism | PKIX, hostname, mTLS, URL mode, and driver version |
| Kafka / RabbitMQ / Pulsar | Driver/broker properties or bundle binding if supported | Broker advertised hostname, TLS auth, separate trust/keystore |
| Spring Integration | Configure the underlying connection factory/client below the adapter | A channel does not turn a connection into TLS |

**There is no universal guarantee** that declaring `spring.ssl.bundle.pem.partner-orders` will automatically be picked up by every dependency. Each client must be explicitly pointed to its bundle, SSL context, or trust/key material using the API supported by **that exact library version**.

### 11.1. Example: PostgreSQL JDBC Has Its Own Mechanism

A typical PostgreSQL JDBC driver configuration:

```yaml
spring:
  datasource:
    url: "jdbc:postgresql://db.internal.example:5432/orders?sslmode=verify-full&sslrootcert=/etc/tls/db-root-ca.pem"
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
```

This is **PostgreSQL driver** configuration, not evidence that the driver reads `spring.ssl.bundle.*`. `verify-full` requires certificate chain and hostname verification per driver semantics. Another driver may use different truststores, connection properties, and SSL mode names. Never use `sslmode=require` as an equivalent substitute for `verify-full`.

### 11.2. Example: Brokers Advertising Multiple Hostnames

Kafka/Pulsar may use a bootstrap endpoint and then receive metadata containing different broker hostnames. A bundle with the right CA for the bootstrap host **does not guarantee** another broker has a SAN matching the name the client is instructed to connect to.

When only some consumers/producers hit TLS errors:

- Record the **actual broker name** from logs/metadata.
- Inspect the certificate SAN of each endpoint/proxy.
- Determine whether the driver enables hostname verification and which truststore it uses.
- Fix certificates/DNS/`advertised.listeners` per cluster architecture; do not disable verification.

### 11.3. Independent Server and Client SSL Bundles

A service that both serves HTTPS and calls outbound APIs typically needs **two bundles**. An inbound TLS identity should not accidentally be sent to outbound partners. A partner's truststore should not become the list of CAs allowed to authenticate all clients calling an internal server. Name bundles by role and control private key read permissions.

## 12. Configuring TLS Protocols, Ciphers, and Security Policies

In some environments, security teams require restricting allowed TLS versions. Bundles support the `options` group:

```yaml
spring:
  ssl:
    bundle:
      pem:
        partner-orders:
          truststore:
            certificate: file:/etc/tls/partner-ca.pem
          options:
            enabled-protocols:
              - TLSv1.3
              - TLSv1.2
```

This example only illustrates the **scope of TLS option configuration**, not a mandatory policy for every system. The JDK version, SSL provider, server, and client implementation determine which protocols/ciphers are actually supported. If a partner only supports outdated versions, assess the risk and upgrade plan rather than arbitrarily enabling weak protocols.

Do not copy a cipher suite list from another machine without checking the names supported by your JVM/provider. After deployment, inspect an actual handshake to confirm the negotiated protocol/cipher matches expectations.

### Limitations Regarding 0-RTT, ALPN, and HTTP/2

An SSL bundle does not alone determine all HTTP/2, ALPN, connection reuse, or early data behavior. Those capabilities also depend on the HTTP server/client, TLS version, and proxies. If an API mutates state, do not assume TLS 1.3 makes replaying a request safe: **idempotency and business replay protection** must still be designed separately.

## 13. Certificate Rotation, Reload, and Connection Lifecycle

Expired certificates and revoked keys can halt all integration connections. Therefore, bundles must be paired with a rotation process.

### 13.1. Swapping a File vs. Swapping the SSL Context

Suppose `/etc/tls/partner-ca.pem` is replaced with a new CA while the application is running. There are at least three layers of state:

1. **The file on the filesystem** has changed.
2. **The `SslBundle`/`SSLContext`** used by the application may still hold the previously loaded material.
3. **Sockets/connection pools** may continue reusing old TLS connections with no new handshake until connections are recreated.

Therefore, **updating a file does not guarantee every client immediately picks up the new certificate**. Spring Boot supports bundle reloading in certain supported versions/scenarios, but consumers must know how to consume those updates. For servers or HTTP clients without reload support, perform controlled redeploy/restarts or client/connection pool recreation per procedure.

### 13.2. `reload-on-update` When Supported by Version

PEM bundle example:

```yaml
spring:
  ssl:
    bundle:
      pem:
        public-api-server:
          reload-on-update: true
          keystore:
            certificate: file:/etc/order-service/tls/server-chain.pem
            private-key: file:/etc/order-service/tls/server.key

server:
  ssl:
    bundle: public-api-server
```

This illustrates the **reload when file material changes** feature in supported Boot versions. You must verify:

- Whether the embedded server/client type supports updating SSL material after startup.
- Whether the way mounted files are updated (in-place overwrite, atomic rename, Kubernetes Secret symlinks, etc.) emits changes detected by the file watcher.
- Change detection delay, behavior for existing sessions/connections, rollback, and errors if certificate/key mismatch.
- Whether the reload property is available **in your exact version**; do not assume all Boot 3.x releases share identical behavior.

For mTLS, deploy the certificate chain and private key **as an atomic consistent set** to avoid a window containing a new cert with an old key.

### 13.3. Practical Rotation Workflow

```mermaid
flowchart TD
    A["Inventory certs/CAs, SANs, EKUs,<br/>expiry, and bundle owners"] --> B["Issue new cert/key and verify source"]
    B --> C["Prepare trust overlap if changing CA"]
    C --> D["Distribute cert/key to staging"]
    D --> E["Test server/client + mTLS handshakes"]
    E --> F["Roll out production in waves"]
    F --> G["Monitor handshake/timeout/errors"]
    G --> H["Retire old CA/cert when safe"]
```

When changing CAs, many systems need an overlap window where both old and new CAs are trusted to prevent outages. Bound the transition window and retire the old CA per policy once all parties have switched. For client certificates, the partner must trust the new certificate's chain before the client starts presenting it.

**Never place private keys in logs, emails, or issue trackers** during rotation. Debugging should focus on public fingerprints, issuer, SANs, serial, expiry, alias, and redacted certificate chains.

## 14. Testing SSL Bundles Properly

A unit test mocking `RestClient` can prove the adapter handles JSON and HTTP statuses, but it does **not** prove certificate chains or hostname verification work. TLS tests must exercise a **real TLS socket** between client and test server.

### 14.1. Required Test Matrix

| Scenario | Expectation |
| --- | --- |
| Trusted CA, server SAN matches hostname, cert unexpired | Handshake succeeds |
| Server uses a CA not in truststore | Handshake fails with trust path verification error |
| Server has valid CA but wrong SAN | Handshake rejected by hostname verification |
| Server certificate expired/not yet valid | Connection rejected |
| mTLS server requires client cert, client presents none | Handshake or connection setup fails |
| Valid client cert but wrong private key | Cannot establish valid mTLS identity; config or handshake error |
| Client cert accepted by server but lacks API permissions | TLS succeeds; application layer returns 401/403 or equivalent authorization failure |
| Bundle key/trust file missing in container | Configuration error detected early; no silent fallback to trust-all |
| Bundle changed at runtime | Explicitly verify whether reload occurs for the server/client in use |
| HTTP client applies bundle after timeout configuration | Verify both TLS and timeouts are preserved |

### 14.2. Creating Isolated Test CAs

In CI, you can use a test CA and issue a leaf certificate for `localhost`, or use a TLS-capable test server such as WireMock/MockWebServer/embedded server. Ensure the certificate has SANs:

```text
DNS:localhost
IP Address:127.0.0.1
```

Use the exact name/address matching the test URL. Never disable hostname verification to make tests "pass". Never copy production keys and certificates into test environments.

Pattern:

```text
Test CA (managed by CI)
  ├─ issues certificate for HTTPS stub server
  ├─ stores public CA in test-client bundle
  └─ if mTLS: issues test client cert/key

Spring Boot RestClient + test-client bundle
  → https://localhost:<random-port>
  → assert response or assert TLS failure per case
```

When testing multiple instances, observe handshakes from **the same network namespace, DNS, and proxy path** as the real application, because certificates presented at a load balancer/ingress can differ from backend certificates.

### 14.3. Distinguishing HTTP Tests from TLS Tests

- `MockRestServiceServer` is suitable for testing URL, method, headers, body, and error mapping; it does not open a TLS socket to a server.
- HTTPS integration tests validate the SSL bundle, trust chain, hostname, and client certificate.
- Staging tests validate secret mounts, DNS, proxies, CAs/truststores, and real deployment configurations.
- Failure/rotation tests verify how the application handles expired certificates, missing files, key swaps, and retries.

## 15. Tools for Inspecting Keystores, Truststores, and Server Certificates

The following commands are **diagnostic only** and do not replace verifying real connections from the application.

### 15.1. Inspecting a PEM Certificate

```bash
openssl x509 \
  -in partner-server-leaf.pem \
  -noout -subject -issuer -dates -fingerprint -sha256 \
  -ext subjectAltName
```

Check SANs, issuer, expiry, and SHA-256 fingerprint. If a file holds multiple certificates, standard `openssl x509` reads only the first certificate; inspect the full chain with an appropriate tool/script when handling multi-entry files.

### 15.2. Inspecting the Chain Actually Presented by the Server

```bash
openssl s_client \
  -connect orders.partner.example:443 \
  -servername orders.partner.example \
  -verify_hostname orders.partner.example \
  -CAfile partner-ca-chain.pem \
  -verify_return_error \
  -showcerts
```

OpenSSL verification results depend on the CA file and options you pass. It does not prove the JVM/HTTP client uses **the same truststore and hostname verifier**. Run from the same network/proxy path as the application to avoid observing the wrong endpoint.

### 15.3. Inspecting a PKCS12 Store and Alias

```bash
keytool -list -v \
  -keystore order-service-client.p12 \
  -storetype PKCS12
```

Check aliases, entry types, certificate chains, validity, and fingerprints. Never pass passwords as command-line arguments saved in CI logs or shell history; use prompts or secure secret mechanisms.

### 15.4. Java JSSE Debugging

When errors occur only in Java:

```text
-Djavax.net.debug=ssl,handshake
-Djava.security.debug=certpath
```

Enable only in investigative environments or for a bounded window, as logs can be huge and contain sensitive metadata. Record the timestamp, called hostname, referenced bundle, and root exception.

## 16. Typical Error Table and Troubleshooting

| Symptom | Common Cause | Check |
| --- | --- | --- |
| `Could not find SSL bundle` or bundle name not found | Referenced name differs from declared name or profile didn't load config | Check `spring.ssl.bundle.*`, `server.ssl.bundle`/code name, active profiles |
| `FileNotFoundException`, `NoSuchFileException` on cert/key | File missing in container or wrong path/mount | Check `file:` location, read permissions, and volume mount |
| `Keystore was tampered with, or password was incorrect` | Wrong store password, wrong store format, or corrupt file | Verify JKS/PKCS12 type and password with admin tools |
| `Cannot recover key` / private key unavailable | Wrong key password, alias, or key entry | Check key alias, entry type, key password |
| `PKIX path building failed` | Missing trust anchor/intermediate or different actual truststore | Inspect chain and truststore actually used by the client |
| `No subject alternative DNS name matching` | URL hostname does not match SAN | Fix URL, DNS, or issue certificate with right SAN |
| `CertificateExpiredException` | Expired certificate or clock skew | Check expiry, `notBefore`, clock, and chain |
| `Received fatal alert: bad_certificate` | Peer rejected certificate, common in mTLS | Check client cert/key, EKU, server-side CA trust, policy |
| `handshake_failure` | Incompatible TLS version/cipher, cert chain, mTLS, or policy | Check logs on both sides and negotiated protocol/cipher |
| Only some instances fail after rotation | Secret mounts, truststores, or SSL contexts updated unevenly | Inventory instances, file versions, and reload/restart plan |
| TLS succeeds but request returns 403 | Certificate authenticated, but caller lacks authorization | Check principal/role/tenant and API authorization |
| Timeouts after applying SSL bundle | Request factory or pool/timeout replaced in client config | Check SSL application order and factory settings; test real timeouts |

### Systematic Error Analysis Workflow

1. Identify the **final endpoint** the client actually calls: hostname, port, protocol, proxy, and broker lookup path if any.
2. Identify **which bundle** the client uses, what key/trust material it contains, and whether files are mounted.
3. Compare the certificate presented in the handshake against SAN, issuer, validity, and the client's trust anchor.
4. For mTLS, verify the client's certificate/key is accepted by the server, not only that the client trusts the server.
5. If errors follow rotation, inspect reload/restart/connection pools and instance consistency.
6. After fixing, run real integration tests; never fix by disabling verification.

## 17. Environment-Based Configuration and Trust Boundaries

An operationally clean structure uses stable bundle names while **varying content/paths per environment**:

```yaml
# application.yml
spring:
  ssl:
    bundle:
      pem:
        partner-orders:
          truststore:
            certificate: ${PARTNER_CA_LOCATION}
```

```text
# Runtime example values, do not commit credentials:
PARTNER_CA_LOCATION=file:/etc/order-service/tls/partner-ca.pem
```

With Spring Boot property binding, placeholders point to environment variables or other configuration sources. The bundle name `partner-orders` stays consistent across local, staging, and production while secret files are distributed by each deployment environment.

### 17.1. Bundle Naming Is Also a Design Decision

Name by purpose:

```text
public-api-server
partner-orders-client
partner-shipping-client
internal-mtls-client
```

Avoid a bundle like `all-trusted-cas` lumping together all internal and external CAs without scope separation. Even when multiple apps/partners share a CA, define who has authority to alter trust material and which connections are affected.

### 17.2. Separating Secrets and Access Permissions

- Issue private keys only to workloads that must present that identity.
- Truststores hold public certificates, yet **deciding to trust a CA** remains a security decision requiring control.
- Keep private keys and passwords out of source control, shared build images, and application logs.
- Restrict file permissions; only the process running the application should read its key.
- Use separate identities per environment and workload; avoid reusing keys between staging and production.
- Define an owner and rotation schedule for each certificate/CA.

### 17.3. Managing Multiple TLS Boundaries

A flow may look like:

```text
External client → API gateway → Spring Boot → Partner API
                            └──→ Kafka/DB/Redis
```

Each arrow can be a **different TLS hop**, with its own client identity, server identity, truststore, and network policy. An embedded server bundle does not protect gateway → backend if the gateway terminates TLS differently; a `RestClient` bundle does not configure Kafka/DB. Inventory every hop carrying sensitive data.

## 18. Real-World Scenario: Same CA, Two Different Error Types

**Context:** `order-service` calls `https://orders.partner.example` over mTLS. After rotation:

- Instance A reports `PKIX path building failed`.
- Instance B reports `No subject alternative DNS name matching`.
- Instance C completes TLS successfully, but the API returns 403.

**Analysis:**

1. Instance A may not have received the new CA/intermediate or may be using an old SSL context. Check the actually loaded bundle and server chain.
2. Instance B trusts the chain, but the server certificate was issued for a **different hostname**; the endpoint/SAN must be fixed. Importing another CA will not fix a hostname error.
3. Instance C completed TLS, yet the client certificate may lack the required role/scope, or the application-level token lacks permissions. This is an authorization error and should not be "fixed" by disabling mTLS.

**Remediation plan:** resynchronize certificate material and config across all instances, verify SAN/chain with real TLS tests, verify client principal/roles, then roll out and monitor handshake errors alongside HTTP 4xx/5xx. When an HTTP adapter retries, avoid infinite automatic retries on PKIX/hostname/permission errors since those are configuration or authorization failures.

## 19. Pre-Production SSL Bundle Checklist

1. **Assets:** know who owns each certificate, CA, private key, bundle name, and expiry.
2. **Format:** choose PEM or JKS/PKCS12 matching your secret distribution workflow; avoid ambiguous duplicate bundle names.
3. **Roles:** keystore for the application's own identity; truststore for the peer's CAs/certificates.
4. **Identity:** leaf certificates have SANs matching the hostname/IP peers use; never disable hostname verification.
5. **mTLS:** verify both sides trust the appropriate CAs; private key matches cert; server enforces business authorization independently.
6. **Spring Boot APIs:** confirm whether each endpoint supports bundles directly or needs driver/client-specific config; check exact version.
7. **Timeouts and pooling:** applying a bundle does not strip HTTP request factory or connection pool settings.
8. **Secrets:** file mounts, passwords/aliases, read permissions, environment variables, and no-key-logging policies.
9. **Testing:** run real TLS sockets with valid/wrong CA, valid/wrong SAN, expired certs, and mTLS when used.
10. **Rotation:** implement trust overlap, clear reload/restart behavior, and verify the new cert on all instances.
11. **Observability:** monitor handshake failures, TLS errors, expiry, connection timeouts, and impact on consumers/outbox.

### Self-Check Questions

**1.** Why is a bundle declaring only `truststore.certificate` sufficient for many standard HTTPS calls? When is `keystore.private-key` needed?

**2.** What is the difference between Spring Boot using `server.ssl.bundle` and `RestClient` using `ssl.fromBundle(...)`?

**3.** A `.p12` file contains both a CA certificate and a private key. Why is it still necessary to separate keystore and truststore roles?

**4.** A client connects to `https://payments.example`, but the server presents a valid CA-signed certificate with SAN `DNS:reports.example`. Is fixing the truststore enough?

**5.** Why does calling `bundle.createSslContext()` not prove that a custom library has hostname verification enabled?

**6.** Why might updating a certificate file in a Kubernetes Secret not cause all existing connections to use the new certificate? How would you verify reload support?

**7.** A service receives HTTPS requests and calls two different partners over mTLS. How many bundles would you organize and why?

## References

- [Spring Boot 3.5 — SSL bundles](https://docs.spring.io/spring-boot/3.5/reference/features/ssl.html): configuring PEM/JKS, named bundles, and SSL lifecycle.
- [Spring Boot 3.5 — Calling REST Services](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html): using SSL bundles with REST clients.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): look up `spring.ssl.bundle.*` names and defaults by version.
- [Java 17 JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): SSLContext, KeyManager, TrustManager, certificate paths, and TLS debugging.

## Conclusion

Spring Boot SSL bundles let you manage **key material, trust material, and TLS options by name**, instead of repeating certificate/private key loading logic on every connection. PEM fits when infrastructure distributes separate certificate/key files; JKS/PKCS12 fits when managing keystore containers and aliases/passwords. For an HTTPS server, reference the bundle via `server.ssl.bundle`; for `RestClient`, use a Spring Boot-configured `RestClient.Builder` combined with `RestClientSsl`. For databases, caches, and brokers, check the SSL mechanism of the **specific driver/client**. A sound setup verifies chains and hostnames, protects private keys, tests over real TLS sockets, plans rotation, and monitors connection failures—keeping HTTP, database, cache, and messaging integrations reliable as configs and certificates change.
