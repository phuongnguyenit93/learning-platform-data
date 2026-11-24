# Configuring Per-Client Authentication, SSL, and Timeouts

## 1. Why Does Each HTTP Client Need Its Own Configuration?

In **Spring Boot Integration**, an application may simultaneously call multiple external systems: an inventory REST API, a payment service, a shipping API, an identity provider, or adapters connected to brokers and databases. For **synchronous HTTP**, each call typically sits on the critical path where a user or caller is waiting for the result. Consequently, HTTP client configuration directly affects **information security, latency, and failure recovery**.

Suppose the Order Service has two dependencies:

| Client | Target System | Authentication | TLS Connection | Connect Timeout | Read Timeout |
| --- | --- | --- | --- | --- | --- |
| `inventoryRestClient` | Internal inventory API | HTTP Basic per internal contract | Trusts internal CA | 1 second | 2 seconds |
| `paymentRestClient` | External payment partner API | API key and client certificate identity | Partner CA + **mTLS** | 2 seconds | 5 seconds |

These numbers are **illustrative assumptions**; real values must reflect measured latency, target capacity, and the end-to-end business deadline. Because the two dependencies have distinct contracts and risk profiles, use **two independent `RestClient` beans**, each with its own TLS setup, authentication headers, timeouts, and error policy.

Reusing one shared default client across all destinations makes it easy to accidentally send Payment's API key to Inventory, trust the wrong CA, or apply a slow reporting service's long read timeout to a request-path stock reservation. A shared config tweak can silently break every integration flow.

~~~mermaid
flowchart LR
    O["Order Service"] --> I["inventoryRestClient"]
    O --> P["paymentRestClient"]
    I --> A["TLS + Basic + short timeout"]
    P --> B["mTLS + API key + dedicated timeout"]
    A --> ID[("Inventory API")]
    B --> PD[("Payment API")]
~~~

Examples here use **Java 17+, Spring Boot 3.2+, and Spring Framework 6.1+** with `RestClient`. Specific API signatures vary across release lines, so match your project's versions. The same principles apply to `RestTemplate` and `WebClient`, though each HTTP engine configures TLS, pools, and timeouts differently.

## 2. Distinguishing HTTP Authentication, HTTPS, and Timeouts

Three configuration layers solve three distinct problems:

- **HTTP authentication/authorization**: proves who the caller is and what actions are permitted—for example `Authorization: Basic ...`, `Authorization: Bearer ...`, or `X-API-Key`.
- **Transport-layer TLS/SSL**: encrypts the channel and verifies the endpoint's identity via certificate chain and hostname checks. **mTLS** additionally requires the client to present its own certificate to the server. TLS alone does not grant business authorization.
- **Timeouts and resource bounds**: prevent threads, sockets, or pools from being held too long when DNS, TCP, TLS, request transmission, or response reads stall.

The letters **SSL** still appear in property names and Java APIs, yet modern HTTPS relies on **TLS**. Never re-enable SSLv3 or deprecated protocols to work around handshake errors; fix certificates, protocols, and trust chains properly.

### 2.1. Different Timeout Types Are Not Interchangeable

| Type | Scope | Pitfall to Avoid |
| --- | --- | --- |
| **Connection timeout** | Bounds establishing the network connection to the endpoint (per HTTP engine). | Confusing it with the wait limit for the entire HTTP request. |
| **TLS handshake timeout** | Bounds TLS negotiation, governed by engine/specific settings. | Assuming every library enforces handshake bounds via `connectTimeout`. |
| **Connection pool acquisition timeout** | Waiting for an available connection when the pool is full. | Setting connect/read timeouts while callers still stall indefinitely waiting on the pool. |
| **Read/response timeout** | Bounds waiting for or reading response data per request factory semantics. | Mistaking it for a total request deadline across retries. |
| **Total operation deadline** | End-to-end time budget from business start until final outcome. | Allowing consecutive retries to exceed the caller's wait budget. |
| **Retry backoff** | Delay between valid retry attempts. | Sleeping inside a transaction holding DB locks or connections. |

Timeout parameters vary across HTTP engines: read timeout may apply per socket read or per entire response, and DNS resolution is not always bounded by TCP connection timeout. Read the docs for your **active request factory / HTTP client** and verify behavior against a deliberately delayed test server.

## 3. Organizing Properties per Target Destination

Start by separating each client's URL and timeouts under a clear prefix:

~~~yaml
# application.yml
app:
  http:
    inventory:
      base-url: https://inventory.internal.example
      connect-timeout: 1s
      read-timeout: 2s
    payment:
      base-url: https://api.payment.example
      connect-timeout: 2s
      read-timeout: 5s
    auth:
      inventory-username: ${INVENTORY_USERNAME}
      inventory-password: ${INVENTORY_PASSWORD}
      payment-api-key: ${PAYMENT_API_KEY}

spring:
  ssl:
    bundle:
      pem:
        inventory:
          truststore:
            certificate: classpath:tls/inventory-ca.pem
        payment:
          truststore:
            certificate: file:/run/secrets/payment-ca.pem
          keystore:
            certificate: file:/run/secrets/payment-client-chain.pem
            private-key: file:/run/secrets/payment-client-key.pem
~~~

In this example:

1. `app.http.inventory` and `app.http.payment` declare business-level client settings; Spring Boot does not bind these custom prefixes automatically until a `@ConfigurationProperties` bean reads them.
2. `spring.ssl.bundle.pem.inventory` supplies the **trusted certificate used to verify the Inventory server**. If a service uses a certificate signed by a public CA already in the JVM's default truststore, a custom truststore may be unnecessary.
3. `spring.ssl.bundle.pem.payment` supplies the **truststore for the Payment server** plus the **keystore holding the client's certificate and private key** for mTLS.
4. Files under `/run/secrets` represent paths mounted by the deployment platform; ensure real files exist with read-only permissions and rotation support. Public CA certs can be packaged in resources, whereas **private keys and passwords must never be committed to source control**.
5. `${...}` placeholders follow Spring property resolution, pulling values from environment variables or secret stores at deploy time. If a value is missing, the app should **fail fast** at startup rather than booting with an empty string.

Never share Payment's API key or private key with unrelated services. If different accounts or tenants use distinct credentials, reflect those trust boundaries in client separation and secret storage.

> **Truststore note:** Specifying a custom set of CAs may replace the JVM's default root CAs depending on how `SSLContext` is constructed. Always verify the full trust chain for each target, especially when migrating between internal and public CAs.

## 4. Binding Typed Properties Instead of Scattered Strings

Spring Boot binds duration strings like `1s`, `500ms`, or `2m` directly into `Duration`. Group settings in a record:

~~~java
// HttpClientsProperties.java
package com.example.integration.http;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.http")
public record HttpClientsProperties(
        Endpoint inventory,
        Endpoint payment) {

    public record Endpoint(
            URI baseUrl,
            Duration connectTimeout,
            Duration readTimeout) {}
}
~~~

Records give strong typing; add `jakarta.validation` and `@Validated` to enforce valid URLs, positive durations, and required fields—such as `@NotNull`/`@Positive`—so misconfigurations fail before serving traffic.

Never accept `baseUrl` from runtime user input; doing so opens **SSRF** vectors and leaks authentication headers to unintended hosts. Clients talking to fixed partner systems must take URLs solely from deployment configuration.

## 5. Two RestClients with Independent TLS and Timeouts

**Spring Boot SSL bundles** expose `SslBundles` to retrieve named truststore/keystore bundles and construct an `SSLContext`. The example below uses Java's `HttpClient` with `JdkClientHttpRequestFactory`, giving each client its own request factory, SSL context, and timeouts.

~~~java
// DownstreamHttpConfiguration.java
package com.example.integration.http;

import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.ssl.SslBundle;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(HttpClientsProperties.class)
public class DownstreamHttpConfiguration {

    @Bean("inventoryRestClient")
    RestClient inventoryRestClient(
            RestClient.Builder builder,
            HttpClientsProperties properties,
            SslBundles sslBundles,
            @Value("${app.http.auth.inventory-username}") String username,
            @Value("${app.http.auth.inventory-password}") String password) {

        return securedBuilder(
                    builder,
                    properties.inventory(),
                    sslBundles.getBundle("inventory"))
                .defaultHeaders(headers -> headers.setBasicAuth(username, password))
                .build();
    }

    @Bean("paymentRestClient")
    RestClient paymentRestClient(
            RestClient.Builder builder,
            HttpClientsProperties properties,
            SslBundles sslBundles,
            @Value("${app.http.auth.payment-api-key}") String apiKey) {

        return securedBuilder(
                    builder,
                    properties.payment(),
                    sslBundles.getBundle("payment"))
                .defaultHeader("X-API-Key", apiKey)
                .build();
    }

    private RestClient.Builder securedBuilder(
            RestClient.Builder builder,
            HttpClientsProperties.Endpoint endpoint,
            SslBundle bundle) {

        HttpClient jdkHttpClient = HttpClient.newBuilder()
                .connectTimeout(endpoint.connectTimeout())
                .sslContext(bundle.createSslContext())
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        JdkClientHttpRequestFactory factory =
                new JdkClientHttpRequestFactory(jdkHttpClient);
        factory.setReadTimeout(endpoint.readTimeout());

        return builder.clone()
                .baseUrl(endpoint.baseUrl().toString())
                .requestFactory(factory);
    }
}
~~~

Notable details:

- `RestClient.Builder` comes from Spring Boot, retaining application-wide customizations. Calling `clone()` before configuring prevents accidentally mutating builders used elsewhere.
- `SslBundles.getBundle("inventory")` and `getBundle("payment")` load the two named TLS configs, and `createSslContext()` builds each context from its trust/key material.
- `HttpClient.newBuilder().connectTimeout(...)` bounds connection establishment, and `JdkClientHttpRequestFactory.setReadTimeout(Duration)` sets the request read timeout in Spring Framework 6.1+. **This does not create an overall deadline across retries.**
- `followRedirects(HttpClient.Redirect.NEVER)` reduces the risk of forwarding credentials to a different host via `Location`; if business flows require redirects, enforce an allowlist and header-stripping policy.
- `headers.setBasicAuth(...)` fits only if Inventory genuinely mandates HTTP Basic. Basic **Base64-encodes credentials without encrypting them**; always run over HTTPS with verified server certificates.
- `X-API-Key` is an illustrative header name; header names, token formats, and rotation must follow the Payment API contract. Many partners require `Authorization: Bearer` instead.
- `@Bean("inventoryRestClient")` and `@Bean("paymentRestClient")` have distinct names; inject them with `@Qualifier` to avoid picking the wrong client.

To keep the focus on auth/SSL/timeouts, this setup uses the JDK HTTP client and does not expose granular **connection pool acquisition**, proxy, or HTTP/2 multiplexing tuning. For high-throughput workloads needing explicit pool lease timeouts, consider Apache HttpClient 5 (`HttpComponentsClientHttpRequestFactory`) and configure its pool, TLS, and timeouts coherently. **Never mix half of a JDK client config with an Apache factory expecting options to transfer across.**

### 5.1. Injecting the Right Client in Business Services

~~~java
// InventoryClient.java
package com.example.integration.inventory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryClient {
    private final RestClient client;

    public InventoryClient(
            @Qualifier("inventoryRestClient") RestClient client) {
        this.client = client;
    }

    public StockReply stock(String sku) {
        StockReply reply = client.get()
                .uri(uri -> uri.path("/v1/stock/{sku}").build(sku))
                .retrieve()
                .body(StockReply.class);
        if (reply == null) {
            throw new IllegalStateException("Inventory returned no body");
        }
        return reply;
    }
}

record StockReply(String sku, int available) {}
~~~

~~~java
// PaymentClient.java
package com.example.integration.payment;

import java.math.BigDecimal;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class PaymentClient {
    private final RestClient client;

    public PaymentClient(
            @Qualifier("paymentRestClient") RestClient client) {
        this.client = client;
    }

    public PaymentReply authorize(PaymentCommand command) {
        PaymentReply reply = client.post()
                .uri("/v1/authorizations")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Idempotency-Key", command.operationId())
                .body(command)
                .retrieve()
                .body(PaymentReply.class);
        if (reply == null) {
            throw new IllegalStateException("Payment returned no body");
        }
        return reply;
    }
}

record PaymentCommand(String operationId, BigDecimal amount) {}
record PaymentReply(String authorizationId, String status) {}
~~~

Place each class in its proper file and package, promoting DTOs to separate files if shared outside the package. Never merge `PaymentClient` and `InventoryClient` onto one credential-sharing client; `@Qualifier` wiring enforces credential isolation.

Payment's `Idempotency-Key` contract must be **supported by the partner**. Sending the header alone does not prevent duplicates: the caller must reuse the same `operationId` when retrying the same operation, and the partner must bind the key to the payload and retain results long enough.

## 6. Common HTTP Authentication Methods

| Method | How It Is Sent | Best Fit | What Must Be Controlled |
| --- | --- | --- | --- |
| **Basic Authentication** | `Authorization: Basic base64(user:pass)` | Internal/legacy APIs contracted for Basic. | HTTPS only; protect passwords and block cross-host leaks. |
| **API key** | Partner-specified header, e.g., `X-API-Key`. | Partner APIs using shared secrets. | Scoped permissions and rotation per environment/tenant; never log keys. |
| **OAuth2 Bearer token** | `Authorization: Bearer <access_token>`. | APIs protected by OAuth2/OIDC. | Token scopes/audiences, expiry, caching, refresh, 401 handling. |
| **mTLS** | Client certificate during TLS handshake. | B2B and service-to-service requiring workload identity. | Certificate chains, private keys, expiration, and rotation. |
| **Request signature/HMAC** | Signature header computed from payload and timestamp per contract. | Partners requiring payload integrity and replay defense at the app layer. | Canonicalization, clock skew, nonces, secrets, and protocol versions. |

Production systems often **combine** methods: Payment might require mTLS **and** an API key, or mTLS **and** a Bearer token. Never treat an mTLS client certificate alone as proof the caller is authorized for every action; servers must still enforce authorization.

### 6.1. Dynamic Bearer Tokens: Attached at Request Time

Never bake a short-lived Bearer token into `defaultHeader` at bean startup and reuse it indefinitely. Obtain valid tokens **per request** from a provider that caches and refreshes safely:

~~~java
// Provider contract implemented by an OAuth2 client component.
public interface AccessTokenSource {
    String validAccessToken();
}

// Example interceptor wired inside the corresponding RestClient bean:
return securedBuilder(builder, endpoint, sslBundle)
        .requestInterceptor((request, body, execution) -> {
            request.getHeaders().setBearerAuth(tokenSource.validAccessToken());
            return execution.execute(request, body);
        })
        .build();
~~~

This is an **illustrative configuration snippet**; `tokenSource`, `builder`, `endpoint`, and `sslBundle` are supplied by the enclosing bean. For machine-to-machine calls, implement `AccessTokenSource` using Spring Security OAuth2 Client (`client_credentials` grant via `OAuth2AuthorizedClientManager` or your version's equivalent API).

The provider must:

1. Cache tokens keyed by **client registration, principal/service identity, and scope**.
2. Refresh or fetch tokens ahead of expiry (leaving clock-skew margin), avoiding stampedes where many threads fetch tokens concurrently.
3. Never send tokens to endpoints outside the intended audience/scope or expose them in logs/traces.
4. On `401 Unauthorized`, diagnose why; if expired, **invalidate cache and perform one controlled retry** when safe. `403 Forbidden` indicates missing permissions/scopes and should not be treated like an expired token.
5. Separate token-server errors from business API errors, and apply dedicated timeouts to the token endpoint if it uses an HTTP client.

Using Spring Security avoids hand-rolling the OAuth2 lifecycle. For user-delegated tokens, never mix user tokens across requests or tenants; resolve principals and client registrations strictly within the security context.

### 6.2. Preventing Accidental Credential Leaks via Redirects and Logs

Restrict target hosts, mandate HTTPS, and audit redirect policies. Never log full `Authorization`, `X-API-Key`, cookies, or client private keys. If wire-level HTTP logging is needed during troubleshooting, enable it only briefly in secured environments with header masking. Trace ID, operation ID, HTTP status, and latency usually suffice for root-cause analysis without logging credentials.

## 7. TLS, Truststores, Keystores, and Hostname Verification

Under HTTPS, the client validates the server certificate against configured trust anchors:

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant S as HTTPS Server
    C->>S: ClientHello, supported TLS versions
    S-->>C: ServerHello and certificate chain
    C->>C: Verify chain, validity, and hostname
    opt Server requires mTLS
        S-->>C: Request client certificate
        C->>S: Client certificate and proof of private key possession
        S->>S: Verify client certificate and permissions
    end
    C->>S: HTTP request over TLS channel
    S-->>C: HTTP response over TLS channel
~~~

The **truststore** holds certificates/CAs the client trusts to verify the **server**. The **keystore** in our example holds the **client's** identity certificate and private key for mTLS. Each serves a distinct purpose:

- **Trusting the server:** the chain must terminate at an accepted trust anchor, and the URL's host must match a **Subject Alternative Name (SAN)** on the certificate. Calling `https://inventory.internal.example` fails if the certificate covers only a different hostname, even with a trusted CA.
- **mTLS client certificates:** the server verifies the certificate and the client's proof of key ownership. Certificates may also require specific Extended Key Usage, issuers, and server-side allowlists.
- **Rotation:** rotating certificates, CAs, or private keys requires an overlap window, verifying reload behavior, and restarting beans/processes if the HTTP engine caches the `SSLContext`. Never assume editing a mounted certificate file on disk updates running HTTP clients automatically.
- **Protocols/ciphers:** enforce TLS 1.2/1.3 per organizational policy and server support. Never downgrade security just to work around a handshake failure.

**Never "fix" TLS errors with a "trust all" TrustManager or by disabling hostname verification.** Doing so destroys peer authentication and opens the door to man-in-the-middle attacks. For self-signed certificates in development, import the test CA/certificate into a **dev/test-only truststore**.

### 7.1. PEM vs. JKS/PKCS12

Spring Boot supports both **PEM** and **JKS** SSL bundles. PEM works well as in Section 3; when trust material lives in JKS/PKCS12 archives, configure a JKS bundle:

~~~yaml
spring:
  ssl:
    bundle:
      jks:
        legacy-partner:
          truststore:
            location: file:/run/secrets/legacy-truststore.p12
            password: ${LEGACY_TRUSTSTORE_PASSWORD}
            type: PKCS12
          keystore:
            location: file:/run/secrets/legacy-client.p12
            password: ${LEGACY_KEYSTORE_PASSWORD}
            type: PKCS12
~~~

Then retrieve `sslBundles.getBundle("legacy-partner")` inside that partner's client bean. Before deployment, confirm the files contain the right chains/keys, passwords, aliases (if needed), and bundle formatting. Never merge every partner's truststore into a single global bundle just to make one client connect.

## 8. Timeouts, Deadlines, and Latency Budgets

Suppose the Order endpoint has a 3-second SLO for most requests. If local processing and DB work take ~600 ms, the remaining time **cannot** be granted in full to every dependency:

~~~text
Total request deadline:         3000 ms
  Internal checks/auth:          150 ms
  Orders DB transaction:         450 ms
  Inventory call:               1200 ms
  Mapping & buffer:              200 ms
  Variance headroom:            1000 ms
~~~

Numbers are illustrative; inspect real p95/p99s, concurrency, and sequential dependencies. If Inventory reads for 2 seconds and Payment reads for 5 seconds **sequentially**, combined latency breaks the 3-second deadline even though each client's timeout looked "reasonable".

Good practices:

1. Keep **connect timeouts short** based on real network conditions; long connect timeouts hold threads when hosts are unreachable.
2. Size **response/read timeouts from each operation's latency budget**, not engine defaults.
3. Across sequential calls or retries, track an **end-to-end deadline**. Check remaining budget before starting each attempt.
4. When using connection pools, budget for pool acquisition waits and cap pool size / concurrent calls.
5. Offload slower work to durable queues/workers with status tracking instead of holding synchronous HTTP requests open.

**Never equate a timeout with a business failure.** If Payment recorded an authorization and the response was lost, the client sees a read timeout. Retrying with a new operation ID risks double-charging. Rely on idempotency keys, status lookup APIs, and contract reconciliation.

### 8.1. Timeouts and Database Transactions

Never hold a JPA/JDBC transaction open across multi-second partner HTTP calls unless explicitly designed and reviewed: DB connections and locks remain held, while local DB rollbacks **cannot** undo HTTP side effects. For longer payment flows, persist a `PENDING` state and use outboxes/sagas or explicit confirmation steps instead of pretending distributed ACID transactions exist.

## 9. Handling HTTP Statuses, Retries, and Auth Failures

`RestClient.retrieve()` throws exceptions for 4xx/5xx statuses by default. Never catch `Exception` and retry everything blindly: auth errors, invalid payloads, and timeouts after side effects have completely different meanings.

| Situation | Common Cause | How to Handle |
| --- | --- | --- |
| `401 Unauthorized` | Missing/invalid credentials, expired or invalid token. | Check config; refresh token if appropriate with bounded attempts. |
| `403 Forbidden` | Authenticated caller lacks permission/scope or hits policy block. | Fix permissions/config with API owner; never retry blindly. |
| `429 Too Many Requests` | Target quota exceeded. | Honor `Retry-After`, rate-limit per target, enforce retry budgets and backoff. |
| `400`/`422` | Contract or validation violation per API. | Fix the payload; never retry identical bad data. |
| `409 Conflict` | Business/state conflict. | Interpret per contract and idempotency status. |
| `500`/`502`/`503` | Transient error or target unavailable. | Bounded retries when safe; circuit breakers and reconciliation. |
| `SocketTimeoutException`/I/O timeout | Slow response, network, proxy; uncertain whether target processed it. | Verify idempotency or look up status before retrying side-effecting writes. |
| `SSLHandshakeException` | Chain, hostname, protocol, or client cert mismatch. | Fix TLS; retrying the same broken config achieves nothing. |

To handle `429` on the Payment client while preserving `Retry-After`, use `onStatus`:

~~~java
PaymentReply reply = client.post()
        .uri("/v1/authorizations")
        .body(command)
        .retrieve()
        .onStatus(
                code -> code.value() == 429,
                (request, response) -> {
                    String retryAfter =
                            response.getHeaders().getFirst("Retry-After");
                    throw new PaymentRateLimitedException(retryAfter);
                })
        .body(PaymentReply.class);
~~~

`PaymentRateLimitedException` is an application-defined exception; this snippet demonstrates where to intercept the status rather than a complete client. `Retry-After` can be **seconds** or an **HTTP-date**, requiring safe parsing, deadline checks, and wait caps. Never assume every `429` can be retried immediately.

**Retries must share the outbound rate budget:** if an application allows 50 operations/sec and each operation retries HTTP 3 times internally, actual outbound traffic can surge to 150 attempts/sec. Coordinate retry layers across HTTP clients, services, and broker consumers to prevent retry storms.

## 10. Per-Client Configuration in Spring Integration Flows

Spring Integration commonly places HTTP clients behind a `Gateway` or `Service Activator`. Whether invoking REST from an `IntegrationFlow` or directly from a service, always reuse the dedicated clients:

~~~mermaid
flowchart LR
    Q["Inbound HTTP / Broker"] --> C["MessageChannel"]
    C --> V["Validate + Transform"]
    V --> R{"Route by target"}
    R -->|Inventory| I["InventoryClient"]
    R -->|Payment| P["PaymentClient"]
    I --> IB["inventoryRestClient"]
    P --> PB["paymentRestClient"]
    IB --> D1[("Inventory")]
    PB --> D2[("Payment")]
~~~

What matters is not the number of flows, but **keeping credentials and SSL contexts strictly inside their assigned client scope**. When routing across channels or adapters, define clear request/reply contracts, response timeouts, and error-propagation paths.

On a `DirectChannel`, service handlers usually run on the sender's thread; long read timeouts block callers directly. On an `ExecutorChannel`, hopping threads **does not make calls durable** and does not automatically propagate transactions or thread-local security contexts. Configure timeouts, concurrency limits, bounded queues, and error handling to match each channel type.

When calling Payment after committing an Order, prefer an outbox/queue over making a slow HTTP call inside the Orders DB transaction. Even over Kafka or RabbitMQ, duplicate deliveries and uncertain outcomes still require idempotency keys and reconciliation.

## 11. Testing Authentication, TLS, and Timeouts

Give each `RestClient` its own test suite since their security configurations are independent. Test both **happy paths** and **rejection scenarios**:

| Test | What to Verify |
| --- | --- |
| Inventory sends Basic Auth | Valid header reaches only Inventory host; secrets redacted in logs. |
| Payment sends API key + mTLS | Accurate header, client presents right cert, server accepts chain. |
| Server cert signed by unknown CA | TLS handshake fails per truststore policy; no bypass. |
| Cert has valid CA yet wrong hostname/SAN | Connection rejected by hostname verification. |
| mTLS cert missing/expired/wrong key | Connection rejected with proper observability signals. |
| Inventory slower than read timeout | Client aborts per request factory; caller gets classified error. |
| Connection cannot be established | Connect timeout triggers cleanly without holding threads indefinitely. |
| Payment returns 401/403 | No infinite retries; never retries using another client's credentials. |
| Payment returns 429 + `Retry-After` | Retries honor rate limits and deadlines without bursts. |
| Payment times out after committing | Preserves operation ID/idempotency key; queries status before acting again. |
| Client redirected to unfamiliar host | Auth headers are not forwarded automatically. |
| Two clients running concurrently | Timeouts, truststores, and credentials never cross between clients. |

Use `MockRestServiceServer` for headers, URIs, bodies, and status mappings where suitable. **RestClient-level mocks cannot verify real TLS handshakes or network timeouts**; test those against an HTTPS test server (configured with certificates and artificial delays), such as an embedded server or sandbox with test truststores/keystores.

A reliable strategy maintains a dedicated HTTPS test suite covering: trusted CA, untrusted CA, wrong SAN cert, mTLS-required server, and slow-responding server. Exercise both connect and read timeouts, confirming only the targeted client is affected. Keep test certificates and keys isolated from production material.

### 11.1. Observability and Error Diagnosis

Tag metrics by target name and operation—never by URLs containing high-cardinality dynamic IDs:

- HTTP request rates, error rates, p50/p95/p99 latencies, timeouts, retry counts, and active in-flight calls.
- 401/403 rates, 429 rates, TLS handshake failures, and upcoming certificate expirations.
- Connection pool utilization and acquisition wait times where measurable.
- End-to-end deadline misses, circuit breaker states, and counts of operations awaiting reconciliation due to unknown outcomes.

On TLS errors, inspect endpoints, DNS, chains, and SANs with trusted certificate tools. Verbose TLS handshake logs can aid diagnosis in controlled environments, yet avoid leaving them enabled long-term in production due to volume and metadata exposure. Never print private keys, tokens, or payment request bodies.

## 12. Per-Target HTTP Client Design Checklist

- [ ] Does every target system have a clearly named client bean, URL, credentials, SSL bundle, and timeouts?
- [ ] Does HTTP auth match the API contract (Basic/API key/Bearer), with safe caching/refresh/expiry for dynamic tokens?
- [ ] Does HTTPS verify chains and hostnames, with mTLS certs/keys and rotation planned and zero trust-all bypasses?
- [ ] Are connection, response, pool acquisition, and total deadlines verified against the actual HTTP engine?
- [ ] Do side-effecting calls use idempotency keys, workflow states, and reconciliation for unknown outcomes?
- [ ] Are retries, rate limits, bulkheads/circuit breakers, and broker orchestration bounded within target capacity?
- [ ] Are auth, TLS failures, timeouts, and redirects tested per client with secret-free observability?
- [ ] Are secrets delivered via secure secret stores with least privilege, versioning, and rotation?

**Configuring authentication, SSL, and timeouts per client** makes dependency boundaries explicit in Spring Boot Integration. Dedicated `RestClient` beans for Inventory and Payment enforce each system's exact security contract and deadline. Combined with clear error classification, bounded retries, idempotency, disciplined transactions, and real TLS tests, synchronous HTTP integrations become straightforward to diagnose and resilient under network or partner failures.
