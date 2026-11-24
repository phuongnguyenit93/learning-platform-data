# mTLS and Mutual Authentication Between Services

## Goals and Context

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot orchestrates integrations across HTTP clients, databases, caches, message brokers, and Spring Integration adapters. An order-taking service may call an Inventory API, query PostgreSQL, use Redis, and publish events to Kafka. Every connection needs data protection, yet for sensitive flows encrypting the transport is not enough: **the receiving service also needs to verify who the calling service is**.

**Mutual TLS (mTLS)** is **bidirectional authentication using X.509 certificates during the TLS handshake**. In standard TLS, the client verifies the server's certificate. In mTLS, the server also requests and verifies **the client's certificate**. After a successful handshake, both parties establish an encrypted TLS channel; the application then continues enforcing its own **authorization** policies.

This lesson belongs to the **Connection Security** chapter and focuses on **mTLS and mutual authentication between services**, with examples covering a Spring Boot inbound server, `RestClient`, `WebClient`, PKI certificates, SSL bundles, and SQL/cache/broker integration boundaries. The focus is not just "getting HTTPS working", but consistent configuration, identity contracts, certificate rotation, error classification, testing, and observability.

After this lesson, you can:

1. Distinguish TLS encryption, server authentication, mutual authentication, and application authorization.
2. Understand private keys, certificate chains, CA trust, SAN, EKU, keystores, and truststores.
3. Enable `server.ssl.client-auth=need` and configure SSL bundles for a Spring Boot service.
4. Build outbound mTLS clients using `RestClient` or `WebClient` without disabling hostname verification.
5. Understand mTLS at load balancers/service meshes and the risk of trusting spoofable forwarded identity headers.
6. Design identity policies, expiry/rotation, secrets management, observability, and failure handling.
7. Test both successful and rejected handshakes: missing client cert, wrong CA, wrong host, and expired cert.
8. Separate mTLS transport security from retries, idempotency, and transactions in integration flows.

> **Boundary:** mTLS verifies the peer via certificates within a **TLS connection**; it does not authenticate end users, grant business permissions, prevent replay of an already-valid request, or replace transactions/outbox patterns.

## 1. Why Is Standard One-Way HTTPS Not Enough?

Suppose Order Service calls Inventory Service:

~~~text
Order Service  ── HTTPS ──>  Inventory Service
    client                      server
~~~

With one-way HTTPS, Order Service verifies Inventory Service's domain name and certificate chain. Inventory Service may only see the caller's IP and a bearer token; if the token leaks or network policies are loose, another party could attempt to call the endpoint.

With mTLS:

~~~text
Order Service  ══ mTLS ══>  Inventory Service
 client certificate            server certificate
  + private key                 + private key
  verifies server              verifies client
~~~

The caller must prove possession of the **private key** matching the client certificate during the handshake; the server verifies the chain and certificate policy. Meanwhile, the client checks the server certificate and hostname.

### 1.1. Different Security Objectives

| Mechanism | Provides | Does Not Guarantee by Itself |
| --- | --- | --- |
| TLS/HTTPS | Encryption and integrity on the connection; server auth when properly configured | Client identity |
| mTLS | Authenticates both client and server using certificate chains/private keys | Caller's business permissions |
| OAuth2/JWT | Claims, scopes, audience, and token-based authorization | Transport safety if TLS is skipped |
| NetworkPolicy/Firewall | Restricts which sources and destinations can connect | Cryptographic service identity |
| Signed request/message | Can authenticate payload content per scheme | Automatic TLS/transport configuration |
| Idempotency key | Prevents duplicate processing per contract | Peer authentication or encryption |
| Authorization policy | Permits a service identity to perform specific actions | Encryption and TLS handshake |

**mTLS and OAuth2 complement each other.** For example, the certificate proves the caller is `order-service`, while the token carries `aud=inventory-api` and `scope=inventory:reserve`. The server should validate certificate identity, token validity, audience, and resource access rights when required by the contract.

## 2. How Does the mTLS Handshake Work?

~~~mermaid
sequenceDiagram
    participant C as Order Service (client)
    participant S as Inventory Service (server)
    C->>S: ClientHello + SNI + TLS options
    S-->>C: ServerHello + server certificate chain
    C->>C: Validate CA chain, SAN/hostname, validity, EKU
    S-->>C: CertificateRequest (request client cert)
    C->>S: Client certificate chain + proof of private key
    S->>S: Validate client CA chain, validity, EKU, identity policy
    C->>S: Finished / handshake confirmation
    S-->>C: Finished / handshake confirmation
    Note over C,S: TLS channel established
    C->>S: HTTPS request (business payload)
    S->>S: Application authentication + authorization
    S-->>C: HTTPS response
~~~

The diagram intentionally simplifies TLS 1.2/1.3 message ordering. In TLS 1.3, certificate and Finished messages are arranged and encrypted differently than in TLS 1.2; the core meaning remains the same: **each side verifies its peer's identity** against appropriate trust chains before allowing application data exchange.

### 2.1. What If the Client Does Not Send a Certificate?

When the server requires a client certificate as mandatory policy, the TLS handshake fails **before any request reaches a Controller**. You will see `SSLHandshakeException`, a TLS alert, or a connection reset on the client side; typically **there is no HTTP 401 from a controller** because the connection never reaches the HTTP layer.

This is why we must distinguish:

- **TLS handshake failure:** certificates, CA, SAN, protocol, keys, and trust.
- **HTTP 401:** application failed to authenticate request/token after TLS succeeded.
- **HTTP 403:** application authenticated caller, yet denies the action.
- **HTTP 404/409/422:** HTTP/business errors, not automatically mTLS errors.

## 3. PKI and Essential Concepts

An mTLS architecture usually uses an internal **private CA/PKI** or an identity platform issuing workload certificates. A certificate holds a public key and identity metadata; **the private key must remain secret** on the owning workload.

| Concept | Meaning | Note |
| --- | --- | --- |
| Private key | Secret key proving certificate ownership | Never commit to Git, never log, restrict read access |
| Leaf certificate | Certificate for a specific client/server | Carries SAN, validity, and Key Usage/EKU |
| Intermediate CA | Intermediate CA signing workload certificates | Sender typically presents the required chain |
| Root CA / trust anchor | Trust anchor configured on the peer | Must be organization-controlled and rotated on schedule |
| Certificate chain | Signing path from leaf to trusted CA | Missing intermediates often cause PKIX path errors |
| Keystore | Container holding private key + certificate chain (and optionally other entries) | JKS/PKCS12 or PEM files |
| Truststore | Container holding certificates/CAs trusted by the process | Does not contain the peer's private key |
| SAN | Subject Alternative Name: DNS/IP/URI identities | Critical for server hostnames |
| EKU | Extended Key Usage | Server auth and client auth are distinct purposes |
| CSR | Certificate Signing Request | Used to ask a CA to issue a cert, not a private key |
| SNI | Server Name Indication in TLS ClientHello | Allows server/gateway to select the right certificate |

### 3.1. Keystores and Truststores in Both Directions

Order Service calling Inventory Service:

~~~mermaid
flowchart TB
    subgraph C["Order Service — client"]
      CK["Keystore: order-client key + cert chain"]
      CT["Truststore: CA signing inventory-server"]
    end
    subgraph S["Inventory Service — server"]
      SK["Keystore: inventory-server key + cert chain"]
      ST["Truststore: CA signing order-client"]
    end
    CT -. "verifies server chain" .-> SK
    ST -. "verifies client chain" .-> CK
~~~

**Do not swap roles:**

- Order Service's keystore holds **Order Service's own key/cert**.
- Order Service's truststore holds the **trusted CA for verifying Inventory Service**.
- Inventory Service's keystore holds **Inventory Service's own key/cert**.
- Inventory Service's truststore holds the **trusted CA for verifying Order Service**.

A keystore can technically contain trusted cert entries as well, yet architecturally you should keep **private key material** and **trust anchors** clearly separated.

### 3.2. SAN and Endpoint Names

If the client calls `https://inventory.internal:8443`, the server certificate must carry a DNS SAN matching `inventory.internal`. If connecting by IP, the certificate needs the matching IP SAN; having only `CN=inventory.internal` generally fails modern hostname verification.

Example:

~~~text
Subject: CN=inventory.internal
SAN:
  DNS: inventory.internal
  DNS: inventory.svc.cluster.local
EKU: TLS Web Server Authentication (serverAuth)
~~~

A client certificate can carry workload identity via a URI SAN or DNS SAN depending on PKI/mesh policy, for example:

~~~text
URI SAN: spiffe://corp.example/ns/orders/sa/order-service
EKU: TLS Web Client Authentication (clientAuth)
~~~

**Important:** a SPIFFE-style URI SAN **does not automatically become an authenticated application principal** in Spring Boot. There must be an identity verifier/mapper and proper trust policy. Never treat arbitrary text inside subject or SAN as a valid identity if a CA could issue it unchecked.

### 3.3. A Trusted Certificate Is Not Enough to Grant Permissions

Trusting the root CA only proves the certificate was issued by an accepted CA. If that CA issues certificates for both `billing-service` and `order-service`, Inventory API must check **which service identity** is allowed to call `POST /reservations`.

A viable policy:

~~~text
Authenticated peer identity: order-service
Allowed operation: inventory.reserve
Allowed environment: production
Allowed target: inventory-service
Decision: ALLOW

Authenticated peer identity: reporting-service
Allowed operation: inventory.reserve
Decision: DENY
~~~

This policy may live in the application, API gateway, or service mesh, but it must be **enforced and tested**, not merely drawn on an architecture diagram.

## 4. Configuring Inbound TLS/mTLS in Spring Boot

Spring Boot 3.1+ provides **SSL bundles** to group key/trust material used across connections. Java package names and some integration APIs change across Boot lines, so use the BOM/guide for your running version.

Example: Inventory Service accepting mTLS HTTPS on port 8443 with **PKCS#12**:

~~~yaml
# application.yml — Inventory Service
server:
  port: 8443
  ssl:
    enabled: true
    bundle: inventory-server
    client-auth: need

spring:
  ssl:
    bundle:
      jks:
        inventory-server:
          key:
            alias: inventory-server
          keystore:
            location: ${INVENTORY_KEYSTORE_LOCATION}
            password: ${INVENTORY_KEYSTORE_PASSWORD}
            type: PKCS12
          truststore:
            location: ${CLIENT_CA_TRUSTSTORE_LOCATION}
            password: ${CLIENT_CA_TRUSTSTORE_PASSWORD}
            type: PKCS12
~~~

This is an intentional configuration:

1. `server.ssl.enabled=true` enables TLS on the embedded server.
2. `server.ssl.bundle=inventory-server` selects the SSL bundle holding the **server identity** and trusted client CA.
3. `server.ssl.client-auth=need` makes client certificates mandatory.
4. `key.alias` selects the private key entry (when the keystore holds multiple entries).
5. `keystore` holds Inventory Service's private key and certificate chain.
6. `truststore` holds the trusted CA authorized to sign client certificates under PKI policy.

`*_LOCATION` values should be Spring-supported resource URIs such as `file:/...` or classpath locations for tests. In production, keep private keys out of public artifacts and never hardcode passwords. If a private key has its own password, Spring Boot SSL bundles provide `key.password` to declare it separately.

**Compatibility note:** `spring.ssl.bundle.jks.*` and `server.ssl.bundle` apply to Boot releases with SSL bundles. On older Boot versions, `server.ssl.key-store`/`server.ssl.trust-store` and related properties may be needed; **do not** mix legacy keystore properties with `server.ssl.bundle` on the same embedded server without verifying compatibility.

### 4.1. Differences Between `need`, `want`, and `none`

| `server.ssl.client-auth` Value | Behavior | Suitable for Mandatory mTLS? |
| --- | --- | --- |
| `none` | Does not request a client certificate | No |
| `want` | May request a certificate but allows clients that omit one | Insufficient if policy requires every client to present a cert |
| `need` | Client must present a valid certificate for handshake to succeed | Yes, when combined with proper trust/identity policies |

`want` fits certain migration scenarios but must not be treated as mandatory mTLS enforcement; requests without certificates can still reach the application. With `need`, clients lacking a valid cert are rejected at the TLS layer.

### 4.2. PEM Instead of PKCS12

Some Kubernetes/secret management environments provision **PEM certificates + private keys** instead of PKCS12 files. Spring Boot SSL bundles support PEM configuration in compatible releases:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        inventory-server:
          keystore:
            certificate: ${SERVER_CERT_LOCATION}
            private-key: ${SERVER_KEY_LOCATION}
          truststore:
            certificate: ${CLIENT_CA_CERT_LOCATION}
server:
  ssl:
    bundle: inventory-server
    client-auth: need
~~~

These three values are **resource paths or content supported by your Boot version**; do not assume all path strings have identical semantics. In production, secrets might be mounted at `file:/etc/ssl/...` with strict permissions. Choose **either** PEM or JKS/PKCS12 for a bundle; never declare both under the same name expecting Boot to guess.

### 4.3. TLS Versions and Cipher Suites

In production, use TLS **1.2/1.3** per organizational and runtime policy. A server configuration can restrict protocols:

~~~yaml
server:
  ssl:
    enabled: true
    enabled-protocols: TLSv1.3,TLSv1.2
    client-auth: need
~~~

Actual ciphers, signature algorithms, and protocols vary across JDKs, server containers, and TLS providers. Never copy an old cipher list from outdated docs onto a newer JDK. Test both positive and negative handshakes and follow enterprise crypto policies.

## 5. Configuring Outbound mTLS for RestClient

In the Order Service → Inventory Service flow, Order Service must:

- Trust **Inventory Server's certificate chain**.
- Present **Order Service's client certificate/private key** when requested by the server.
- Verify hostname `inventory.internal` matches SAN.
- Preserve SNI, TLS versions, and proper client connection pooling.

Create a dedicated SSL bundle in the **client application**:

~~~yaml
# Order Service application.yml
spring:
  ssl:
    bundle:
      jks:
        inventory-client:
          key:
            alias: order-client
          keystore:
            location: ${ORDER_CLIENT_KEYSTORE_LOCATION}
            password: ${ORDER_CLIENT_KEYSTORE_PASSWORD}
            type: PKCS12
          truststore:
            location: ${INVENTORY_SERVER_CA_TRUSTSTORE_LOCATION}
            password: ${INVENTORY_SERVER_CA_TRUSTSTORE_PASSWORD}
            type: PKCS12

integrations:
  inventory:
    base-url: ${INVENTORY_BASE_URL:https://inventory.internal:8443}
~~~

With **Spring Boot 3.2–3.x**, Boot provides the `RestClientSsl` helper to apply an SSL bundle to a Boot-managed `RestClient.Builder`.

~~~java
// API example for Spring Boot 3.2–3.x.
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.web.client.RestClientSsl;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class InventoryHttpClientConfiguration {

    @Bean
    RestClient inventoryRestClient(
            RestClient.Builder bootBuilder,
            RestClientSsl restClientSsl,
            @Value("${integrations.inventory.base-url}")
            String baseUrl) {

        return bootBuilder
                .baseUrl(baseUrl)
                .apply(restClientSsl.fromBundle("inventory-client"))
                .build();
    }
}
~~~

**Check imports and class locations if using Boot 4.x**, because some auto-configuration packages were reorganized. The core mechanism stays the same: use the **Boot-managed builder/SSL bundle** and apply client key/trust config to the transport.

Using the `RestClient` built from that builder:

~~~java
import org.springframework.web.client.RestClient;
import org.springframework.stereotype.Component;

@Component
public class InventoryGateway {

    private final RestClient inventoryRestClient;

    public InventoryGateway(RestClient inventoryRestClient) {
        this.inventoryRestClient = inventoryRestClient;
    }

    public InventoryResponse reserve(
            InventoryRequest request) {

        return inventoryRestClient.post()
                .uri("/v1/reservations")
                .body(request)
                .retrieve()
                .body(InventoryResponse.class);
    }
}
~~~

`InventoryRequest` and `InventoryResponse` are downstream contract DTOs omitted here since the lesson focuses on mTLS. In a real application, configure timeouts, response validation, HTTP 4xx/5xx error handling, idempotency keys, and observability. You can use `@HttpExchange` + `HttpServiceProxyFactory` instead of calling `RestClient` directly: **TLS lives on the `RestClient`/HTTP transport underneath the proxy**, not on interface annotations.

### 5.1. Never "Fix" TLS Errors with Trust-All

The following approaches destroy mTLS guarantees and **must never be used in production**:

- A `TrustManager` accepting any X.509 certificate.
- A `HostnameVerifier` always returning `true`.
- Disabling hostname verification to call a server by an IP missing from SAN.
- Using a truststore containing arbitrary uncontrolled CAs and treating every leaf cert as authorized.
- Reading a client certificate from an unverified HTTP header without a validated TLS chain.

If the hostname is wrong, reissue the certificate with the right SAN or switch the endpoint to the DNS name in the certificate. If the CA is untrusted, install the right CA chain/trust anchor and verify its validity. Never skip verification.

### 5.2. An SSL Bundle Does Not Automatically Configure Other Clients

Merely defining `spring.ssl.bundle.jks.inventory-client` **is not enough** to make every `RestClient`/`WebClient` in the application use it. You must **apply the bundle to the specific client or message sender** through the API supported by your Boot/transport version.

This prevents security leaks when different downstreams need **different client identities**. For example, the Payment client should use its own certificate rather than Inventory client credentials. Setting one global `SSLContext` for the whole JVM easily breaks scope and leaks identities across services.

## 6. WebClient and mTLS via Reactor Netty

`WebClient` is often used in WebFlux applications or async flows. TLS lives in the **HTTP connector** (such as Reactor Netty), not in `Mono`/`Flux` or `@GetExchange`.

An illustrative setup using Spring Boot `SslBundles` and Reactor Netty/Netty SSL context:

~~~java
// Reactor Netty example; check signatures for your version.
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;
import java.util.function.Consumer;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLException;
import org.springframework.boot.ssl.SslBundle;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

@Configuration(proxyBeanMethods = false)
public class InventoryWebClientConfiguration {

    @Bean
    WebClient inventoryWebClient(
            WebClient.Builder bootBuilder,
            SslBundles sslBundles) throws SSLException {

        SslBundle bundle = sslBundles.getBundle("inventory-client");

        SslContext context = SslContextBuilder.forClient()
                .keyManager(
                        bundle.getManagers().getKeyManagerFactory())
                .trustManager(
                        bundle.getManagers().getTrustManagerFactory())
                .build();

        HttpClient httpClient = HttpClient.create()
                .secure(spec -> spec
                        .sslContext(context)
                        .handlerConfigurator(handler -> {
                            SSLParameters parameters =
                                    handler.engine().getSSLParameters();
                            parameters.setEndpointIdentificationAlgorithm(
                                    "HTTPS");
                            handler.engine().setSSLParameters(parameters);
                        }));

        return bootBuilder
                .baseUrl("https://inventory.internal:8443")
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
~~~

This snippet demonstrates **client key material + trusted CA + hostname verification** while using the Boot-injected `WebClient.Builder`. Depending on Spring Boot 3.x/4.x, Reactor Netty/Netty and SSL bundle APIs may vary; verify signatures before running.

**Note on hostname verification:** some Reactor Netty versions/paths enable hostname verification by default on secure clients, yet whenever supplying a custom SSL context or handler you must verify that `HTTPS endpoint identification` remains active. Never assume a custom `SslContext` inherits name verification automatically.

Building the connector manually can also alter the connection pool/shared resources/observation used by the default builder; test real runtime behavior. If your Boot version provides a helper applying bundles directly to `WebClient`, prefer that helper to reduce misconfiguration risk.

### 6.1. Reactive Does Not Change the Meaning of mTLS

~~~java
import reactor.core.publisher.Mono;

public Mono<InventoryResponse> reserve(
        WebClient inventoryWebClient,
        InventoryRequest request) {

    return inventoryWebClient.post()
            .uri("/v1/reservations")
            .bodyValue(request)
            .retrieve()
            .bodyToMono(InventoryResponse.class);
}
~~~

The TLS handshake normally occurs when a connection is established upon subscription. HTTPS connections may be **reused** from the pool, so not every HTTP request performs a new handshake. Do not treat "TLS handshake count" as "request count", and do not assume a new client certificate appears on an already-open connection if configuration is swapped mid-flight.

## 7. Generating Demo Certificates in Development

To understand key/trust setup, you can generate two **self-signed certificates strictly for local testing** and configure matching truststores. This is **not production PKI**; never commit private keys/passwords or use demo names/secrets in real environments.

The commands below use `keytool` bundled with the JDK. Run them inside an isolated test directory you control.

### 7.1. Server Key/Certificate

~~~bash
keytool -genkeypair \
  -alias inventory-server \
  -keyalg RSA -keysize 3072 \
  -validity 30 \
  -storetype PKCS12 \
  -keystore inventory-server.p12 \
  -storepass changeit \
  -dname "CN=inventory.internal" \
  -ext "SAN=dns:inventory.internal,dns:localhost" \
  -ext "EKU=serverAuth"

keytool -exportcert \
  -alias inventory-server \
  -keystore inventory-server.p12 \
  -storepass changeit \
  -rfc -file inventory-server.crt
~~~

### 7.2. Client Key/Certificate

~~~bash
keytool -genkeypair \
  -alias order-client \
  -keyalg RSA -keysize 3072 \
  -validity 30 \
  -storetype PKCS12 \
  -keystore order-client.p12 \
  -storepass changeit \
  -dname "CN=order-service" \
  -ext "EKU=clientAuth"

keytool -exportcert \
  -alias order-client \
  -keystore order-client.p12 \
  -storepass changeit \
  -rfc -file order-client.crt
~~~

### 7.3. Creating Truststores in Both Directions

Inventory Service trusts the test client certificate:

~~~bash
keytool -importcert -noprompt \
  -alias order-client \
  -file order-client.crt \
  -storetype PKCS12 \
  -keystore inventory-truststore.p12 \
  -storepass changeit
~~~

Order Service trusts the test server certificate:

~~~bash
keytool -importcert -noprompt \
  -alias inventory-server \
  -file inventory-server.crt \
  -storetype PKCS12 \
  -keystore order-truststore.p12 \
  -storepass changeit
~~~

Local demo mapping:

| Application | Keystore | Truststore |
| --- | --- | --- |
| Inventory Service | `inventory-server.p12` | `inventory-truststore.p12` |
| Order Service | `order-client.p12` | `order-truststore.p12` |

In production, use a **CA issuing workload certificates**, restrict CA scope, and enforce identity policies. Importing a self-signed leaf cert directly into a truststore as shown above is only for verifying mechanics in a lab; it complicates rotation and does not match the trust model of a versioned, chained PKI.

**Safety:** `changeit` in the example is a well-known test password, not a production-grade secret. Private key files must stay out of repositories, release artifacts, and have restricted file permissions.

### 7.4. When Using a Real PKI

A reliable certificate issuance lifecycle usually involves:

1. Workload/gateway generates a keypair or receives managed key provisioning.
2. Creates a CSR with the exact SANs and EKU for its identity.
3. CA verifies the service identity/permission to request a certificate before signing.
4. Workload receives its certificate chain and corresponding trust bundle.
5. Deploys cert/key through controlled secret delivery.
6. Automatically/periodically rotates before expiry and monitors failures.
7. Revokes/blocks compromised certificates, or uses short validity windows to limit exposure.

A CA must never sign arbitrary CSRs simply because a requester can reach the CA API. Workload identity must tie back to real provisioning/authorization such as service account, namespace, and platform policy.

## 8. Testing Real Handshakes with curl and OpenSSL

mTLS tests must cover **both success and rejection**. Never verify only that an endpoint returns HTTP 200 using a trust-all client.

Suppose Inventory Service runs at `https://inventory.internal:8443` and the DNS name appears in the server SAN.

### 8.1. Client with a Valid Certificate

If you have PEM client key/cert issued by a test CA:

~~~bash
curl --verbose \
  --cacert inventory-server.crt \
  --cert order-client.crt \
  --key order-client.key \
  https://inventory.internal:8443/actuator/health
~~~

If using PKCS12 from `keytool`, you can use `--cert-type P12` and `--cert inventory-client.p12:...` depending on build/libcurl, or safely convert to PEM for testing. The snippet above assumes `order-client.key` **actually exists**; `keytool -exportcert` in section 7 exports only the **public certificate**, not the private key. Never confuse `.crt` with `.key`.

### 8.2. Client Without a Certificate

~~~bash
curl --verbose \
  --cacert inventory-server.crt \
  https://inventory.internal:8443/actuator/health
~~~

When the server genuinely uses `client-auth: need` and you hit **that TLS endpoint directly**, the handshake must be rejected or the request must fail to complete normally due to the missing client certificate.

### 8.3. Checking Chain and SNI with OpenSSL

~~~bash
openssl s_client \
  -connect inventory.internal:8443 \
  -servername inventory.internal \
  -CAfile inventory-server.crt \
  -cert order-client.crt \
  -key order-client.key \
  -verify_return_error
~~~

`openssl s_client` shows the chain, issuer, subject, verify result, and TLS version. That does not mean application-level authorization passed. If the connection succeeds yet the application returns HTTP 403, investigate **identity mapping/permissions** rather than trying to "fix" the CA.

### 8.4. Testing Hostname Mismatch

Call the server with a hostname **not listed in SAN** while keeping hostname verification enabled. The client must reject the certificate even when signed by a valid CA. This is a critical test to catch trust-all configurations or disabled `HostnameVerifier`s.

If a test connects via `localhost` while the cert only has `inventory.internal`, a hostname mismatch error is the **correct** behavior. The fix is to include `localhost` in the test SAN or use the right DNS name—never disable hostname verification.

## 9. Application Authorization After TLS

A successful handshake passes the request to Spring MVC/Servlet or WebFlux, yet the application must still extract **peer identity** and enforce permissions.

A policy model:

~~~text
TLS:
  - Verify certificate chain issued by approved internal CA
  - Verify client certificate validity and EKU
  - Extract trusted peer identity from validated certificate

Application:
  - Map identity to service principal
  - Check access to endpoint / operation / tenant
  - Validate OAuth2 token when contract requires
  - Audit decision without logging private key or raw credentials
~~~

### 9.1. Spring Security X.509

Spring Security supports X.509 client certificate authentication in the servlet stack when **the TLS endpoint supplies the verified certificate chain** to the application. This step *translates a peer certificate into an application principal*; it does not replace `server.ssl.client-auth=need`.

A **directional example**, not a complete production configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class InventorySecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/internal/reservations/**")
                    .hasAuthority("INVENTORY_RESERVE")
                .anyRequest().authenticated())
            .x509(Customizer.withDefaults());

        return http.build();
    }
}
~~~

This example assumes the Spring Security web starter and a configured **`UserDetailsService`/identity mapping** assigning `INVENTORY_RESERVE` to the client certificate identity. Enabling `.x509()` without a trusted principal mapping can fail login or assign incorrect permissions.

**Do not default to using subject CN as the sole principal** in multi-tenant/multi-CA production environments: identical CNs could be issued in different contexts. Prefer mapping SAN/URI or certificate identity per PKI policy, trusted issuer, environment, and required constraints. If using SPIFFE/SVID, use a component that actually verifies SPIFFE identity rather than merely parsing strings from a certificate.

### 9.2. `server.ssl.client-auth` Does Not Replace Spring Security

An endpoint can be in one of several states:

| TLS Handshake | Principal/Authorization | Outcome |
| --- | --- | --- |
| Fail | No valid HTTP request | TLS alert/connection error |
| Pass | No matching mapping/authentication | HTTP 401 or auth failure |
| Pass | Authenticated but lacks permission | HTTP 403 |
| Pass | Authorized identity, valid payload | 2xx per contract |
| Pass | Authorized identity, invalid payload | Business 4xx |
| Pass | Authorized identity, downstream outage | 5xx or appropriate error |

You cannot convert a TLS failure into an HTTP 403 "from a Java controller" because the handshake failed before the application processed HTTP.

## 10. mTLS Through a Reverse Proxy, Ingress, and Service Mesh

In Kubernetes/service meshes, TLS may terminate at a **load balancer, ingress proxy, or sidecar** instead of directly inside the JVM.

~~~mermaid
flowchart LR
    A["Order Service"] --> B["Order Sidecar"]
    B == "mTLS between proxies" ==> C["Inventory Sidecar"]
    C --> D["Inventory Application"]
    E["Mesh identity policy"] -.-> B
    E -.-> C
    C -.-> F["Peer identity / authorization policy"]
~~~

In this architecture, the JVM app may receive **plain-text HTTP from localhost/sidecar** while traffic between workloads is protected by mTLS at the proxies. `server.ssl.client-auth=need` might not be enabled inside the JVM, **but that is only sound when the trust boundary up to the sidecar is strictly enforced**.

### 10.1. Ask the Right Question: Where Does TLS Terminate?

A request may cross multiple hops:

~~~text
Client -> Ingress -> Gateway -> Service Mesh Sidecar -> JVM
~~~

To know whether mTLS is truly effective, answer:

1. Does every hop use TLS?
2. Which hop verifies the **client certificate**?
3. What identity does the certificate carry, and which CA issued it?
4. Which hop enforces authorization policy?
5. Can another workload bypass the proxy and call the JVM hop directly?
6. Is there a NetworkPolicy/loopback/Unix domain socket protecting any unencrypted hop?
7. Does the application blindly trust forwarded identity headers from any client?

An ingress checking certificates only **at the edge** does not prove mTLS between all internal services. Define policies per hop according to your threat model.

### 10.2. Forwarded Client Identity Headers Can Be Spoofed

A gateway may forward a header like `X-Client-Cert` or `X-Forwarded-Client-Cert` after verifying the peer. The application **must not trust** that header merely because it appears in the HTTP request.

If users can directly send `X-Forwarded-Client-Cert: CN=order-service`, they can impersonate callers. Trust forwarded identity only when:

- A trusted ingress/gateway actually **verified the certificate chain** and identity.
- The gateway **strips client-supplied headers and sets its own**.
- The hop from gateway to app is secured or restricted so only the gateway can call it.
- The application knows the exact **trusted proxy chain** and forwarding policy.
- Negative tests verify bypassing the gateway/spoofing headers fails.

If you need direct end-to-end mTLS between JVMs, do not terminate TLS at a proxy and assume the application still sees the peer certificate. Once terminated at a gateway, the Servlet request may no longer have the original TLS peer's real certificate.

### 10.3. Mesh mTLS Does Not Replace Data-Level Authorization

A service mesh can provide workload identity (e.g., SPIFFE), service-to-service authentication, and policies. Yet accessing `GET /orders/{id}` also depends on user/tenant ownership. Being allowed as a service to call an API **does not grant read access to every resource**.

The application still needs authorization by user, business scope, tenant, or resource, and should validate delegated tokens when acting on behalf of an end user.

## 11. Databases, Caches, and Message Brokers Have Separate TLS

This lesson focuses on **service-to-service mTLS**, yet the integration module also covers non-HTTP connections. Do not infer from `server.ssl.bundle` that JDBC/Redis/Kafka are already secured.

| Integration Layer | TLS/mTLS Mechanism | What to Verify |
| --- | --- | --- |
| Spring Boot HTTP inbound | Embedded server TLS + client auth | Server bundle, client CA, `need` |
| `RestClient` outbound | HTTP transport SSL context/bundle | Client key, server trust, hostname SAN |
| `WebClient` outbound | Reactor Netty/HTTP connector SSL | mTLS context, hostname verification |
| Kafka producer/consumer | Kafka client `security.protocol=SSL` or `SASL_SSL` and SSL properties | Broker trust, optional client cert, hostname identification |
| RabbitMQ/AMQP | AMQP client SSL options/factory | Broker trust, client cert if required by broker |
| PostgreSQL JDBC | Driver SSL modes, key/cert/trust config | Server verification, client cert config, connection URL |
| Redis | Driver TLS config and optional client cert | TLS endpoint, CA, certificate credentials |
| Spring Integration adapters | Rely on each adapter's transport factory/client | Do not automatically inherit all `server.ssl` settings |

Exact configuration keys **depend on client library, vendor, and version**. Configure and test **each connector independently**.

### 11.1. Conceptual Kafka mTLS Example

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    properties:
      security.protocol: SSL
      ssl.truststore.location: ${KAFKA_TRUSTSTORE_PATH}
      ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
      ssl.keystore.location: ${KAFKA_KEYSTORE_PATH}
      ssl.keystore.password: ${KAFKA_KEYSTORE_PASSWORD}
      ssl.keystore.type: PKCS12
~~~

This example only shows basic Kafka client properties. Kafka SSL paths are typically filesystem paths per Kafka client implementation, **not necessarily Spring resource URIs**. The Kafka broker must require/vet client certs per its own policy; `security.protocol=SSL` on the client alone does not prove the broker enforces client authentication. Verify broker config and ACLs for the mapped principal.

### 11.2. PostgreSQL mTLS Is Not HTTP mTLS

PostgreSQL JDBC uses parameters like `sslmode=verify-full`, trust/root certificates, and client cert/key per driver/connection settings. Specifically:

- `verify-full` checks server cert and hostname.
- `verify-ca` checks the CA chain but is not equivalent to full hostname verification.
- Client certs only take effect if the PostgreSQL server requires them and the client supplies the right format/identity.
- SQL privileges remain governed by database authentication/roles/GRANTs.

Never use `sslmode=require` assuming server identity is verified for production needs; understand exact driver semantics and use hostname-verifying modes where needed.

### 11.3. Redis and RabbitMQ

Redis TLS/RabbitMQ TLS encrypt the channel and can require client certificates when supported by the server/driver. However, Redis ACLs or RabbitMQ users/permissions still govern authorization; mTLS certificate identity may need explicit mapping.

All Spring Integration adapters must use transport clients configured with proper TLS. For example, HTTP outbound gateways via `RestClient`, AMQP outbound adapters via `RabbitTemplate`, or Kafka outbound adapters via the Kafka client—there is no single global `mTLS=true` property covering all of Spring Integration.

## 12. Secrets Management and Rotation

Certificates are credentials with expiration dates. A production mTLS deployment must have a **certificate lifecycle**, not just static config files.

### 12.1. Recommended Practices

- Issue short-lived certificates and automate rotation whenever possible.
- Separate CA/trust bundles across production, staging, and dev per policy.
- Never commit private keys, PKCS12 files, passwords, or key-bearing PEMs to Git.
- Mount secrets into filesystems/volumes with least-privilege permissions or use managed secret delivery.
- Restrict who/what processes can export private keys; consider HSM/KMS if required.
- Ensure app containers only read the trust/key material they need.
- Maintain a dashboard alerting on upcoming certificate expiry.
- Maintain a revoke/reissue procedure if a private key is compromised.
- Audit who issued/changed certificates and when applications loaded new keys.

### 12.2. Zero-Downtime Rotation

A safe CA rotation path:

~~~mermaid
flowchart LR
    A["Old CA trusted"] --> B["Add new CA to trust bundles"]
    B --> C["Issue new certs from new CA"]
    C --> D["Rolling restart/reload workloads"]
    D --> E["Verify handshakes succeed"]
    E --> F["Remove old CA after migration window"]
~~~

Condition: all participating clients/servers must accept the new chain **before** new certs appear; then wait long enough for old workloads to stop presenting the old chain.

**Never assume updating a key/trust file on disk makes every active TLS connection immediately use it.** Some Spring Boot SSL bundle/embedded server integrations support reload under specific conditions, yet HTTP client connection pools, custom `SSLContext`s, Reactor Netty, and certain Boot versions may require explicit restarts/rebuilds to adopt new certs.

Rotation tests must verify:

1. New connections use the new certificate.
2. Old connections do not outlive operational policy.
3. The new trust chain is accepted by all peers.
4. Authorization policies still map the identity correctly.
5. Rollback of certs/CA has a safe window.

### 12.3. Certificate Expiry and Clock Skew

`NotBefore` and `NotAfter` checks rely on system clocks. Significant clock skew can trigger "not yet valid" errors even on freshly issued certs. Container/VM nodes must keep synchronized time. Monitors should alert days ahead of expiry based on criticality, not wait until handshakes fail.

## 13. Monitoring Handshakes and Connection Security

Micrometer/Actuator helps observe HTTP layers, yet **not every TLS handshake failure produces an HTTP server observation**, because errors can happen before an HTTP request is created.

Combine signals:

| Signal Source | Information |
| --- | --- |
| Embedded server/TLS provider logs | Handshake alerts, certificate errors |
| Proxy/load balancer/mesh metrics | TLS handshake success/failure, peer identity, policy denies |
| HTTP client metrics | Request latency, connect/timeout errors |
| Spring Security audit | Authenticated principal, authorization decision |
| Certificate inventory | Certificate expiry, issuer, SAN, and chain version |
| Business metrics | Order sync success, retries, DLQ, outbox lag |
| JVM/connection pool | Threads, connection usage, resource saturation |

**Never log private keys, session secrets, full bearer tokens, full client certificates in request logs, or raw handshake secrets.** For auditing, log certificate fingerprint/serial/issuer or workload identity under proper access control and retention. Avoid fingerprints/serials as metric labels due to high cardinality.

### 13.1. Distinguishing mTLS Errors from Business Errors

~~~text
Connection failed before HTTP:
    TLS handshake/certificate/protocol issue

HTTP 401/403 after TLS:
    authentication/authorization issue

HTTP 429/503 or timeout:
    rate limit/downstream availability issue

HTTP 2xx but business rejected:
    payload/contract/business status issue

HTTP 2xx and business applied:
    verify persistence/outbox/downstream ack as needed
~~~

When mTLS fails, repeatedly increasing `retryCount` does not help if a certificate is expired or a CA is untrusted. That is a **configuration/operational error** requiring fail-fast, alerting, and fixing certificates/trust. Use bounded retries only for transient connection failures within business deadlines.

### 13.2. Low-Cardinality Metric Labels

Good tags: `downstream=inventory`, `transport=https`, `result=success/error`, `environment=prod`. Never put dynamic client IPs, certificate serials, user IDs, or request IDs into metric labels.

A practical dashboard might include panels for:

- Outbound TLS/connection error rate per downstream.
- HTTP client p95 latency, timeouts, and 5xx.
- Proxy mTLS handshake failures/policy denies.
- Nearest certificate expiry threshold.
- Retry/DLQ counts and business integration lag.
- Deployment/rotation timeline to correlate incidents with cert changes.

Never conclude "mTLS is healthy" solely because `/actuator/health` returns UP. Health checks may use a special caller that does not represent all service identities.

## 14. End-to-End mTLS Testing and Negative Cases

A unit test mocking `RestClient` cannot prove `SSLContext` actually presents a client certificate. You need at least one **integration test using real TLS**, with a server requiring client auth.

### 14.1. Test Matrix

| Case | Expectation |
| --- | --- |
| Client cert has valid CA, unexpired, valid EKU | Handshake succeeds |
| Missing client cert | Handshake rejected when server is `need` |
| Client cert signed by wrong CA | Handshake rejected |
| Client cert expired/not yet valid | Handshake rejected |
| Server cert lacks SAN matching host | Client rejects hostname verification |
| Server cert wrong/untrusted CA | Client rejects chain |
| Server omits intermediate chain | Client may reject PKIX path |
| Valid client cert but lacks application permission | Handshake passes, HTTP 403 |
| Expired/invalid JWT when contract also requires token | Handshake may pass, application auth fails |
| Incompatible TLS protocol/cipher | Handshake fails cleanly, no insecure downgrade |
| New CA/new cert rotation | Trust overlap window and zero-downtime rollout |
| Two services under same CA, different identities | Only policy-authorized identity is allowed |
| Caller-injected `X-Client-Cert` header | Rejected as identity unless from trusted proxy |

### 14.2. Spring Boot Integration Example

In a `@SpringBootTest(webEnvironment=RANDOM_PORT)`, test configuration can enable:

~~~yaml
server:
  ssl:
    bundle: inventory-server
    client-auth: need

spring:
  ssl:
    bundle:
      jks:
        inventory-server:
          keystore:
            location: file:/tmp/test-certs/inventory-server.p12
            password: changeit
            type: PKCS12
          truststore:
            location: file:/tmp/test-certs/inventory-truststore.p12
            password: changeit
            type: PKCS12
~~~

This is a **test fixture**; do not rely on a hardcoded `/tmp/test-certs` path in real CI without provisioning it. Use a temp directory/protected test resources and dynamic properties, then create a `RestClient` with the `inventory-client` bundle in the test. Assertions must prove:

1. A connection with a valid client certificate reaches the controller.
2. A connection without a client certificate fails at TLS.
3. An untrusted CA or wrong hostname is rejected.
4. A valid certificate whose principal lacks permissions gets HTTP 403.
5. No test installs a trust-all manager or disables hostname verification.

Note that `RANDOM_PORT` only randomizes the port—it **does not disable TLS**. If the test calls `localhost`, the certificate must include `DNS:localhost` or the matching IP SAN for the URL.

### 14.3. Testing at the Service Mesh/Proxy Layer

When TLS terminates at a proxy, JVM-level application integration tests **are not enough**. You also need to:

- Verify mesh policies require mTLS between the two workloads.
- Test calls from a workload lacking identity or holding an unauthorized identity.
- Test sidecar/gateway bypass paths and header injection.
- Test end-to-end application authorization using trusted forwarded identity.
- Exercise workload certificate and CA changes per the rollout plan.
- Observe certificate/handshake metrics at the proxy, not only in the JVM.

A test returning HTTP 200 through a gateway that skipped client auth at ingress **does not prove** the system's mTLS works.

## 15. Troubleshooting and Remediation

| Symptom | Possible Cause | Where to Check |
| --- | --- | --- |
| `PKIX path building failed` | Server/client CA untrusted or missing intermediate | Check chain, truststore, CA rotation |
| `bad_certificate` | Peer rejected certificate by trust/usage/policy | Check issuer, EKU, validity, key match |
| `certificate_required` / handshake failure | Server requires client cert, client sent none | Check client keystore, alias, key password |
| `No subject alternative DNS name matching` | URL host missing from server SAN | Reissue cert with matching SAN or fix DNS name |
| `No name matching ... found` | Hostname verification failed | Never disable verification |
| `keystore password was incorrect` | Wrong password or store format | Check env/PKCS12/JKS type |
| `Cannot recover key` | Wrong key password or corrupt key entry | Check `key.password` and alias |
| `No available certificate or key corresponds to SSL cipher suites` | Incompatible keypair/algorithm/alias | Check key/cert match, TLS version/ciphers |
| `handshake_failure` | Could be protocol/cipher/cert/trust | Read TLS logs/openssl; do not guess |
| `HTTP 403` after TLS success | Service principal lacks permission | Check application/mesh policy |
| Test OK, prod fails | Hostname/CA/keystore/JDK/ingress mismatch | Compare SANs, bundles, routing, and secrets |
| Some pods fail after rotation | Nodes still hold old CA/cert or pools didn't reload | Check cert serial/version and restart policy |
| Mesh mTLS enabled yet JVM sees no X509 cert | TLS terminated at sidecar | Use trusted proxy identity or passthrough |
| Spoofed `X-Client-Cert` succeeds | Blindly trusting caller headers | Strip/rewrite at trusted proxy; secure the hop |
| Kafka/Redis/JDBC still lack TLS | Only `server.ssl` was configured | Configure TLS on each connector |

### 15.1. Ordered Diagnostic Runbook

1. Identify the exact **failing TLS hop**: client→ingress, sidecar→sidecar, or JVM→JVM.
2. Confirm endpoint DNS/port, SNI, and TLS version; never log secrets.
3. Inspect the server certificate: chain, issuer, SAN, EKU, `NotBefore`/`NotAfter`.
4. Inspect the client certificate/key: was it sent, alias/key password, EKU.
5. Check that each side's truststore holds the right CA and is not stale.
6. Verify `client-auth=need` is actually applied on the **server accepting the connection**.
7. If the handshake passes, inspect Spring Security/mesh authorization.
8. Inspect reverse proxy forwarded identity and bypass risk.
9. Run negative-case tests to ensure the fix didn't turn into trust-all.
10. Check timeouts, retries, outbox backlog, and requests that may have caused side effects during the incident.

**Do not leave verbose SSL debug enabled long-term in production** if logs can expose certificate/session details; enable temporarily under incident procedures and redaction policies. Java TLS debug `javax.net.debug=ssl,handshake` is useful in controlled environments, yet output must be protected.

## 16. mTLS Does Not Replace Error Handling, Transactions, and Idempotency

An mTLS connection can protect Order Service calling Payment Service, yet it **does not** guarantee a POST request is applied only once.

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant P as Payment Service (mTLS)
    participant D as SQL Database
    O->>P: HTTPS/mTLS POST pay(orderId)
    P->>D: COMMIT payment
    Note over P,O: Response lost due to timeout
    O->>O: Does not know whether payment committed
    O->>P: Retry with same operationId
    P->>D: Check idempotency key
    P-->>O: Return stored result
~~~

To stay safe:

- Use a stable operation ID/idempotency key tied to the business event, never a certificate serial or TLS session ID.
- Distinguish TLS config errors (no rapid infinite retries) from transient HTTP 503s and business rejections.
- Reconcile on timeouts **after** the remote side may have executed.
- When writing SQL and then calling HTTP/broker, use transactional outbox or saga/reconciliation as required.
- Avoid holding SQL transactions open while waiting on mTLS handshakes or remote HTTP responses.
- Design logs/audit to correlate business operations with downstream outcomes without leaking sensitive data.

mTLS protects the **channel and peer identity**, whereas exactly-once semantics, transaction consistency, and audit trails must be handled in the application/data architecture.

## 17. Service-to-Service mTLS Implementation Checklist

- [ ] Identify exact hops requiring mTLS and where TLS terminates (JVM/gateway/mesh).
- [ ] Establish clear PKI/CA ownership and rules for issuing each workload identity.
- [ ] Keep private keys secret; ensure cert chain, SAN, and EKU match server/client roles.
- [ ] Server has identity keystore and client CA truststore; enable `client-auth=need` if mTLS is mandatory.
- [ ] Client has identity key/cert and server CA truststore; enable hostname verification.
- [ ] Choose Spring Boot SSL bundles/transport APIs matching your version; avoid arbitrary mixing with legacy config.
- [ ] Never use trust-all `TrustManager`, disabled hostname verifiers, or unverified proxy identity headers.
- [ ] Enforce application/mesh authorization policies rather than checking only shared CA membership.
- [ ] If using OAuth2/JWT, validate audience/scope/expiry and never treat mTLS as replacing user auth.
- [ ] Configure TLS separately on Kafka/RabbitMQ/JDBC/Redis connectors where needed.
- [ ] Maintain certificate issuance, rotation, expiry alerting, revocation, and rollback plans.
- [ ] Verify connection pools/reload behavior across rotation.
- [ ] Include positive/negative TLS tests, identity permissions, hostname/SAN, CA trust, and proxy spoofing tests.
- [ ] Track handshake/authorization/HTTP error metrics, redacted logs, business retries, and backlogs.
- [ ] Design business retries/idempotency/transactions independently of mTLS.

**Remember:** mTLS creates an encrypted channel authenticating **both ends of the connection**, yet it is only trustworthy when certificates carry proper identities, chains and hostnames are verified, private keys are protected, and application permissions are explicitly enforced. With Spring Boot, SSL bundles manage key/trust material; inbound servers use `server.ssl.client-auth=need`, and outbound clients must bind bundles properly to their transports. Production integrations also require **rotation, negative testing, observability, retries, and idempotency**.

## References

- [Spring Boot — SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html): SSL bundles, JKS/PKCS12/PEM, and TLS integration.
- [Spring Boot — Embedded Web Servers](https://docs.spring.io/spring-boot/reference/web/servlet.html): server SSL configuration and client authentication.
- [Spring Boot — Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): `RestClient`/`WebClient` builders and customizations.
- [Spring Security — X.509 Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html): creating principals/authorization from client certificates.
- [Java JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): `TrustManager`, `KeyManager`, keystores, certificate verification, and TLS.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): TLS 1.3 protocol and certificate-based authentication.
- [RFC 5280 — PKI Certificate Profile](https://www.rfc-editor.org/rfc/rfc5280): X.509, certificate paths, extensions, and constraints.
- [SPIFFE — Workload Identity](https://spiffe.io/docs/latest/spiffe-about/overview/): workload identity/SVID concepts in service-to-service security.
- [Reactor Netty — HTTP Client SSL](https://projectreactor.io/docs/netty/release/reference/http-client.html#_ssl_and_tls): TLS/SSL for reactive HTTP clients.
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS policies, cipher suites, and configuration safety.
