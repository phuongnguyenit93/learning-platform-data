# Connection Pools, Timeouts, and Limiting Calls to the Issuer

In a **Spring Security OAuth 2.0 / OIDC Resource Server**, the API often has to communicate with the Authorization Server (AS), also known as the **token issuer**, to fetch trust material and verify tokens. These calls sit on the request-handling path or on the initialization/key-rotation path. Without bounds on connections, timeouts, and concurrency, a slow issuer can exhaust connection pools, tie up requests for too long, and degrade the entire Resource Server.

Common outbound requests include:

- **OIDC discovery:** fetching metadata from the well-known endpoint to learn the issuer, JWKS URI, and other endpoints.
- **JWKS retrieval:** fetching public signing keys to verify JWT signatures. In a JWT Resource Server, this is typically cached; the issuer does not necessarily need to be called on every request.
- **Token introspection:** sending an opaque Access Token to the introspection endpoint to check whether the token is still active. This is typically an online call during authentication, unless the application caches results.
- **Token endpoint or token exchange:** typically belongs to an OAuth Client/BFF or a separate delegation flow. A Resource Server that solely verifies tokens does not need to call the token endpoint for each API request.

The operational goal is to ensure each call type has **an appropriately sized connection pool, bounded timeouts, a concurrency cap, a retry budget, and a safe failure policy**. Keep JWKS caching distinct from introspection caching, because the two cache types have different security implications.

This lesson belongs to the **Performance and Operations** chapter and uses **Java 17+, Spring Boot 3.x, Spring Security 6.x, WebFlux/Servlet, and Reactor Netty** as its context.

## 1. When Does the Resource Server Call the Issuer?

The JWT and opaque token flows differ:

~~~text
JWT Access Token
Client
  |
  | Authorization: Bearer <JWT>
  v
Resource Server
  |
  +-- Does JWT have a kid matching a cached key?
  |       |
  |       +-- Yes --> verify signature offline
  |       |
  |       +-- No  --> fetch/refresh JWKS from issuer
  |
  +-- validate iss, aud, exp, nbf, scope...
  |
  v
API response

Opaque Access Token
Client
  |
  | Authorization: Bearer <opaque>
  v
Resource Server
  |
  +-- call introspection endpoint
  |       |
  |       +-- active=true --> build Authentication
  |       +-- active=false --> reject
  |       +-- timeout/unavailable --> cannot verify
  |
  v
API response
~~~

### 1.1. JWT: Do Not Call JWKS on Every Request

In a JWT Resource Server, `JwtDecoder` verifies signatures using public keys fetched from a JWK Set URI. Keys are cached by the JWT decoder/JWK source library according to its configuration and version. Once keys are cached, verifying a typical JWT can happen locally without calling the issuer.

JWKS calls typically occur when:

- The Resource Server starts up or performs discovery/key loading depending on implementation.
- The key cache expires or needs a refresh.
- A JWT arrives with a kid not yet in the cache.
- The issuer rotates signing keys.
- A previous key fetch failed and the decoder retries per its mechanism.

Therefore, API requests per second do not necessarily equal JWKS requests per second. However, many concurrent requests carrying an unknown kid or a key rotation can produce a burst toward the issuer.

### 1.2. Opaque Token: Introspection Typically Sits on the Authentication Path

An opaque token cannot be decoded by the Resource Server itself to verify a signature and claims. The Resource Server typically calls the introspection endpoint to receive metadata such as active, scope, sub, aud, and expiration. If every incoming request introspects, load on the issuer scales nearly linearly with authenticated requests, unless caching or a custom batching mechanism is used.

Introspection is an online dependency. When the AS does not respond, the Resource Server has no fresh evidence to conclude the token is active. Never turn a network error into active=true or issue a default Authentication.

### 1.3. Discovery Is Not the Same as JWKS

OIDC discovery returns issuer metadata, including `jwks_uri`. Metadata discovery is typically performed when configuring/initializing the provider or when the application needs to refresh metadata, depending on configuration. JWKS retrieval fetches the public key set at that URI. There is no need to download the discovery document on every API request.

You can configure `issuer-uri` so Spring Security auto-discovers metadata, or declare a static `jwk-set-uri` and configure issuer validation explicitly. Either way, trusted URIs must come from managed configuration, never from the token or client request.

## 2. Why Separate Connection Pools?

A connection pool reuses TCP/TLS connections instead of performing a new handshake for every call. It lowers DNS/TCP/TLS overhead and bounds concurrent connections to the issuer.

~~~text
Resource Server instances
       |
       +-- JWT key retrieval client
       |       |
       |       +-- JWKS pool
       |
       +-- opaque introspection client
       |       |
       |       +-- introspection pool
       |
       +-- business downstream clients
               |
               +-- pool per service group
~~~

Separating pools by **purpose and trust boundary** helps ensure:

- Introspection calls do not starve JWKS of connections.
- One slow downstream does not block all outbound traffic.
- Each issuer can have distinct limits and timeouts.
- Connection acquisition, active connections, and pending requests are observable per dependency.
- TLS, proxy, mTLS, or credentials are configured appropriately per endpoint.

You do not necessarily need a separate pool for every minor URL if they share the same host and policy; however, never use an unbounded pool or one uncontrolled shared pool for every dependency.

## 3. Limits to Configure in a Pool

| Limit | Meaning | When Missing |
| --- | --- | --- |
| Max connections | Maximum number of open connections. | Too many sockets may open and pressure the issuer. |
| Pending acquire max | Maximum requests waiting for a connection. | Queue grows unboundedly. |
| Pending acquire timeout | Max wait time for an idle connection. | Requests wait on the pool indefinitely. |
| Max idle time | Maximum idle age of a connection. | Keeps stale connections after proxy/server closes them. |
| Max life time | Maximum total lifetime of a connection. | Connections outlive network or certificate changes. |
| Idle eviction | Interval for removing expired/idle connections. | Old connections may linger beyond policy. |
| Per-host/per-route cap | Dedicated limit for a single host. | One issuer can consume all capacity. |

A bounded pool does not create throughput on its own. When all connections are busy, new requests must wait or be rejected after the pending-acquire timeout. This is the desired behavior under overload: **queues must be bounded and wait times must be finite**.

### 3.1. Max Connections and Concurrency

Suppose each Resource Server instance has an issuer pool of 20 connections. With 8 instances, there could theoretically be up to 160 connections to the issuer, not counting other clients. Calculate totals cluster-wide, not just for a single JVM.

HTTP/2 can multiplex multiple streams over a single TCP connection. Thus connection count does not equal concurrent request count; stream limits, flow control, and server capacity also matter. Measure against the actual protocol and connector.

### 3.2. Pending Acquire Must Be Capped

If a pool has 20 connections and 10,000 requests want to introspect simultaneously, do not let 9,980 requests queue up in heap. Configure a max pending acquire count, a pending acquire timeout, a concurrency limit/bulkhead at the calling layer, and appropriate rate limits.

When capacity is exhausted, return a dependency overload/timeout error per the error contract. Never hold requests and memory indefinitely waiting for the issuer to recover.

### 3.3. Idle Time and Connection Lifetime

`maxIdleTime` should be weighed against the idle timeouts of the load balancer, proxy, and issuer. If the client keeps a connection idle longer than the server allows, the next use may hit a connection reset. `maxLifeTime` rotates connections periodically, which helps across proxy, DNS, or certificate changes.

Do not pick values solely from examples. Measure connection churn, TLS handshake cost, and timeouts on your actual infrastructure.

## 4. Configuring Pools and Timeouts with Reactor Netty

For WebFlux and reactive HTTP clients, you can configure a `ConnectionProvider` for Reactor Netty:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
public class IssuerHttpClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider issuerConnectionProvider() {
        return ConnectionProvider.builder("issuer-pool")
            .maxConnections(32)
            .pendingAcquireMaxCount(64)
            .pendingAcquireTimeout(Duration.ofSeconds(2))
            .maxIdleTime(Duration.ofSeconds(20))
            .maxLifeTime(Duration.ofMinutes(5))
            .evictInBackground(Duration.ofSeconds(30))
            .build();
    }

    @Bean
    WebClient issuerWebClient(
            ConnectionProvider issuerConnectionProvider) {

        HttpClient httpClient =
            HttpClient.create(issuerConnectionProvider)
                .option(
                    ChannelOption.CONNECT_TIMEOUT_MILLIS,
                    2_000)
                .responseTimeout(Duration.ofSeconds(3));

        return WebClient.builder()
            .clientConnector(
                new ReactorClientHttpConnector(httpClient))
            .build();
    }
}
~~~

The values 32 connections, 64 pending requests, and the timeouts in this example are illustrative only. Recalculate them from concurrency, instance count, issuer latency, server limits, and your API SLA.

### 4.1. Distinguish Pool Acquire, Connect, and Response Timeouts

In the example:

- `pendingAcquireTimeout` caps how long to wait for a connection from the pool.
- `CONNECT_TIMEOUT_MILLIS` bounds establishing the TCP connection.
- `responseTimeout` bounds waiting for a response per Reactor Netty semantics.
- A publisher `timeout(Duration)` can enforce an overall deadline for the operation.

These timeouts protect different phases. A request can time out at the acquire step before any TCP connection is opened, or after connecting while waiting for the issuer's response. When investigating incidents, specify which layer timed out.

### 4.2. Configuring the TLS Handshake

Reactor Netty allows TLS configuration via `HttpClient.secure(...)`. If you need to bound the handshake, configure `handshakeTimeout` per your Reactor Netty version's API. If introspection uses mTLS, certificates, key material, and trust configuration must be managed like credentials—never placed in source code.

### 4.3. Managing Pool Lifecycle

`ConnectionProvider` is a resource tied to the application context lifecycle. Dispose of it on shutdown to close the pool and release resources. Never create a new `ConnectionProvider` per request or per token decode.

## 5. Configuring a Pooled Servlet Client

For a Servlet Resource Server, the decoder/introspector typically uses `RestOperations`. One option is providing a `RestTemplate` backed by Apache HttpClient 5 with a bounded connection manager.

Example configuration for Spring Framework 6 and Apache HttpClient 5:

~~~java
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.Timeout;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

@Configuration
public class IssuerRestClientConfiguration {

    @Bean(destroyMethod = "close")
    CloseableHttpClient issuerHttpClient() {
        ConnectionConfig connectionConfig =
            ConnectionConfig.custom()
                .setConnectTimeout(Timeout.ofSeconds(2))
                .setSocketTimeout(Timeout.ofSeconds(3))
                .build();

        PoolingHttpClientConnectionManager connectionManager =
            PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(32)
                .setMaxConnPerRoute(16)
                .setDefaultConnectionConfig(connectionConfig)
                .build();

        RequestConfig requestConfig =
            RequestConfig.custom()
                .setConnectionRequestTimeout(
                    Timeout.ofSeconds(2))
                .setResponseTimeout(Timeout.ofSeconds(3))
                .build();

        return HttpClients.custom()
            .setConnectionManager(connectionManager)
            .setDefaultRequestConfig(requestConfig)
            .evictExpiredConnections()
            .build();
    }

    @Bean
    RestTemplate issuerRestTemplate(
            CloseableHttpClient issuerHttpClient) {
        return new RestTemplate(
            new HttpComponentsClientHttpRequestFactory(
                issuerHttpClient));
    }
}
~~~

This is an example of pooling and timeouts for a Servlet client; exact builder APIs must match the Apache HttpClient 5 and Spring Framework versions in your project. `setMaxConnTotal` and `setMaxConnPerRoute` set pool bounds; `setConnectionRequestTimeout` caps waiting for a connection from the pool; connect/socket/response timeouts control the I/O phases.

Do not substitute `SimpleClientHttpRequestFactory` and assume connection pooling is in place. That simple factory can set connect/read timeouts, but does not provide the same pooling mechanism as Apache HttpClient.

## 6. Wiring the HTTP Client into the JWT Decoder or Opaque Introspector

### 6.1. Reactive JWT Decoder

Spring Security allows supplying a `WebClient` to `NimbusReactiveJwtDecoder`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReactiveJwtConfiguration {

    @Bean
    ReactiveJwtDecoder jwtDecoder(WebClient issuerWebClient) {
        return NimbusReactiveJwtDecoder
            .withJwkSetUri(
                "https://identity.example.test/oauth2/jwks")
            .webClient(issuerWebClient)
            .build();
    }
}
~~~

`issuerWebClient` should use the configured pool and timeouts. The JWKS URI is trusted server configuration. Continue validating issuer, audience, timestamps, and required claims; network limits do not replace token validation.

### 6.2. Servlet JWT Decoder

With `NimbusJwtDecoder`, you can supply a `RestOperations` configured with timeouts and pooling:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.web.client.RestTemplate;

@Configuration
public class ServletJwtConfiguration {

    @Bean
    JwtDecoder jwtDecoder(RestTemplate issuerRestTemplate) {
        return NimbusJwtDecoder
            .withJwkSetUri(
                "https://identity.example.test/oauth2/jwks")
            .restOperations(issuerRestTemplate)
            .build();
    }
}
~~~

Builder method names and configuration options depend on the Spring Security version; use the API matching your project's pinned dependency. If the decoder was created by auto-configuration, verify that replacing the decoder/transport does not drop issuer, audience, and timestamp validators.

### 6.3. Opaque Token Introspection

An introspection client needs a fixed AS URI, client authentication dedicated to the Resource Server, its own connection pool/timeouts or clearly partitioned capacity, TLS trust (plus mTLS if required by the AS), and safeguards so introspected tokens and client secrets are never logged.

In the Servlet stack, `NimbusOpaqueTokenIntrospector` can be configured with `RestOperations` depending on API version. In the Reactive stack, use `ReactiveOpaqueTokenIntrospector` or its reactive implementation with a configured `WebClient`. Check the exact constructor/API for your minor version; never wrap a blocking HTTP client inside a reactive pipeline.

## 7. Separate Pools for JWKS and Introspection

The two traffic types have different profiles:

| Characteristic | JWKS | Introspection |
| --- | --- | --- |
| HTTP operation | Usually GET public key set. | Usually POST token to inspect. |
| Frequency | Usually driven by cache/refresh/key rotation. | Potentially per opaque-token request. |
| Sensitive payload | Public key set, not user tokens. | Request contains Access Token; response contains claims/metadata. |
| Cache | Caches key set per library/policy. | Positive/negative cache directly affects revocation. |
| Timeout | Must suffice for key retrieval/rotation, yet stay short. | Must fit within the authentication latency budget. |
| Failure | If a new key cannot be fetched, tokens needing it cannot verify. | If introspection fails, the token cannot be confirmed active. |

Separating pools—or at least concurrency budgets—prevents an introspection traffic spike from starving JWKS refreshes of connections, and vice versa.

## 8. Timeouts Aligned with the Request Budget

Suppose an API has an 800 ms SLA. If authentication introspection consumes 700 ms, the controller has very little time left. Allocate the deadline:

~~~text
Incoming request deadline: 800 ms
   |
   +-- pool acquire:       <= 50 ms
   |
   +-- issuer connect/TLS: <= 150 ms (when a new connection is needed)
   |
   +-- introspection:      <= 250 ms
   |
   +-- authorization + app logic + response: remainder
~~~

This is an allocation example, not universal recommended numbers. When connections are reused, connect/TLS does not run per request. When JWKS keys are cached, JWT requests may need no network call to the issuer.

### 8.1. Timeouts Must Not Exceed the Remaining Deadline

A downstream call should receive the request's **remaining budget**. If only 100 ms remain on the request while the client uses a 3-second timeout, work may continue after the caller has already given up. Use deadline propagation or compute remaining duration before calling the dependency.

### 8.2. Transport-Layer Timeouts and Publisher Timeouts

You can combine pool acquire timeout, connect timeout, TLS handshake timeout, response/read timeout, and a publisher deadline. The outer timeout protects the use case; inner timeouts protect transport resources. Keep them consistent and sensibly ordered—for example, a 5-second pool acquire timeout inside a 1-second overall request deadline is unhelpful.

## 9. Concurrency Limits and Bulkheads

Pools cap connection counts, yet many publishers can still queue or execute at other layers. A **bulkhead** caps the number of active in-flight calls to a dependency.

~~~text
Incoming requests
      |
      v
Introspection bulkhead (max 40 in-flight)
      |
      +-- permit available --> call issuer
      |
      +-- no permit ---------> reject quickly / overload response
~~~

In reactive code, you can use concurrency-limiting operators or a non-blocking reactive semaphore/bulkhead. For example:

~~~java
Flux<OAuth2AuthenticatedPrincipal> principals =
    Flux.fromIterable(tokens)
        .flatMap(introspector::introspect, 20);
~~~

This snippet illustrates a concurrency limit when processing a batch of tokens. It is not how you automatically wrap every WebFlux request; for individual endpoints, apply a bulkhead/resilience policy at the client or service boundary.

### 9.1. Why Not Rely on the Pool Alone?

If a pool has 32 connections and 50,000 waiting requests, the pool can still accumulate a huge queue unless pending count and pending time are capped. A bulkhead limits how much work is allowed to enter the dependency path; the pending queue has its own ceiling.

### 9.2. Per-Instance and Cluster-Wide Limits

If each instance allows 40 introspection calls and a deployment runs 20 instances, the AS can receive up to 800 concurrent calls. As you scale out, total concurrency grows with instance count. Plan cluster-wide capacity, check whether the AS enforces its own request/connection limits, use a centralized gateway/rate limiter when a global quota is needed, and ensure autoscaling cannot push call volume past issuer capacity.

## 10. Rate Limits and Backpressure

A **concurrency limit** caps simultaneous calls; a **rate limit** caps calls per unit of time. The two complement each other.

For example:

- At most 40 concurrent introspection calls in flight.
- At most 200 calls/second from one Resource Server deployment.
- At most 20 calls/second to a specific issuer tenant.

Actual limits must come from AS quotas and load testing. If the AS returns 429 Too Many Requests, honor `Retry-After` if present while throttling down and applying backoff. Never immediately burst retries upon receiving 429.

Reactive backpressure regulates controllable publishers, but does not automatically rate-limit incoming HTTP traffic to your server. Place ingress rate limits, concurrency gates, and bounded queues at the right boundaries.

## 11. JWKS Caching, Key Rotation, and Request Amplification

JWKS caching keeps JWT validation from calling the issuer on every request. Still, caching must work cleanly with key rotation:

~~~text
Issuer publishes keys:
  K1 (old) + K2 (new)
       |
       v
Resource Server fetches JWKS and caches K1,K2
       |
       v
Issuer starts signing with K2
       |
       v
Resource Server validates JWT kid=K2 locally
       |
       v
Issuer eventually retires K1 after overlap window
~~~

### 11.1. Overlap During Key Rotation

The issuer should publish the new key before signing with it and keep the old key long enough for already-issued tokens. The Resource Server must be able to refresh JWKS when it encounters a new key.

Never delete the old key immediately upon switching to a new key while valid JWTs signed with the old key are still in circulation.

### 11.2. Unknown kids Can Cause Bursts

If requests carry JWTs with a nonexistent kid, the decoder may attempt to refresh JWKS. An attacker could exploit this to trigger request amplification toward the issuer without proper caching, rate limits, or refresh controls.

Mitigations:

- Use a decoder/JWK source with well-understood caching and refresh behavior.
- Cap outbound concurrency and pool pending queues.
- Monitor JWKS fetch counts and unknown-kid rates.
- Consider rate-limiting or negative caching at the appropriate layer if supported by your library/architecture.
- Never issue an ad-hoc JWKS HTTP request on every decode.

Never build custom cache keys solely on token strings or ignore kids; respect JWK selection and signature verification rules.

### 11.3. Cache TTL and Stale Keys

Overly short caches increase issuer traffic; overly long caches delay recognizing replaced or revoked keys. Choose TTLs and refresh behavior based on key rotation policy, token lifetimes, incident response requirements, and issuer capacity.

Do not confuse caching public JWKS with caching active token status. A JWKS cache stores public verification material; an introspection cache can keep a revoked token accepted until the cache expires.

## 12. Introspection Cache and Revocation Window

Opaque tokens are usually introspected online. To reduce load, an application may cache results by token fingerprint or secure cache key. However, caching positive results delays revocation visibility.

~~~text
10:00:00  Introspection: active=true, exp=10:10
10:01:00  AS revokes token
10:01:05  Resource Server still has cached active result
10:02:00  Cache entry expires
10:02:01  New introspection: active=false
~~~

In this example, revocation takes nearly a minute to reach the Resource Server. This is a trade-off that must be accepted under your risk policy.

### 12.1. Bounding the Positive Cache TTL

The TTL should not exceed the smallest of: the application-configured positive cache TTL, remaining time until exp minus a safety margin (if introspection returns a trustworthy exp), and the business-approved revocation propagation window.

If the response lacks exp, do not assume infinite token life; use a bounded policy TTL or skip caching.

### 12.2. Cache Keys Must Not Expose Raw Tokens in Logs

Never place tokens in cache key logs, metric labels, or distributed traces. You can use an HMAC/hash with a properly managed secret to derive a stable cache key; avoid using raw tokens as keys that could leak through diagnostics.

### 12.3. Negative Caching

Caching `active=false` for a brief period can cut repeated introspection of invalid tokens. Keep the TTL short and bounded, since tokens or states can change per AS behavior. Never cache timeout errors as long-lived inactive results if doing so would keep rejecting valid tokens after the AS recovers.

## 13. Retries, Circuit Breakers, and Failure Policies

Retries can ride out brief network glitches, yet can also amplify load when an issuer is overloaded.

| Scenario | Handling Approach |
| --- | --- |
| Transient DNS/connect reset | May retry a few times with backoff/jitter. |
| HTTP 429 | Honor Retry-After, throttle rate. |
| HTTP 5xx | Bounded retries if operation is safe and deadline permits. |
| HTTP 4xx from bad credentials/config | Do not retry unboundedly; alert on configuration error. |
| Introspection timeout | Do not treat token as active; fail closed. |
| JWKS timeout when key is cached | May continue verifying tokens using trusted/cached keys per decoder policy. |
| JWKS timeout with unknown new kid | Cannot verify signature; reject requests needing that key. |
| Circuit breaker open | Fail fast per dependency policy; never skip verification. |

### 13.1. Retry Budget

For example, one retry after a 100 ms backoff may make sense for a transient connection error. Three retries inside a 500 ms request deadline may leave no time for application logic. Compute:

~~~text
totalBudget >=
  attempts * perAttemptTimeout
  + sum(backoff)
  + localProcessingBudget
~~~

This is an estimation model; actual elapsed time also depends on pool acquisition, DNS, TLS, and response transfer.

### 13.2. Circuit Breakers Must Not Fail Open

A circuit breaker can pause calls to a failing issuer to protect resources. When the breaker is open:

- Opaque tokens cannot be successfully introspected: do not create Authentication.
- JWTs whose keys are already cached can still verify locally per trust/cache policy.
- JWTs needing a new key when JWKS cannot be fetched: never skip the signature check.
- Never return a default principal just to preserve availability.

**Availability must never be achieved by accepting unverified tokens.**

### 13.3. Never Retry Business or Credential Errors

Wrong client authentication at the introspection endpoint, wrong issuer URI, broken TLS trust, or malformed responses are configuration/integration errors. Continuous retrying only inflates logs and issuer load. Alert and fix the configuration.

## 14. Isolating Failure Domains per Issuer

An application may trust multiple issuers or tenants. Never let one slow issuer exhaust capacity for others:

~~~text
Resource Server
    |
    +-- issuer-A pool + bulkhead + timeout
    |
    +-- issuer-B pool + bulkhead + timeout
    |
    +-- issuer-C pool + bulkhead + timeout
~~~

Each issuer needs its own trust configuration: issuer ID, metadata/JWKS/introspection URI, client credentials for introspection, TLS trust, and capacity budget.

Never pick an issuer endpoint from a token's `iss` claim and call an arbitrary URL without a trust registry. Where multi-issuer is supported, use a configured resolver/registration and verify the issuer is in the allowlist before touching the network.

## 15. Multi-Tenant and Protecting Issuer Endpoints

When each tenant has its own issuer:

- Cap the number of registered issuers.
- Cache metadata/JWKS per trusted issuer.
- Cap both total pool size and per-issuer pool size.
- Rate-limit discovery when new tenants appear.
- Never run discovery against user-supplied URLs.
- Evict metadata/pools when a tenant is removed.
- Verify TLS hostnames and issuer identity.

An endpoint that takes an `issuerUrl` from a request and fetches a discovery document creates an SSRF vector. The trust registry must dictate which issuers are permitted; caller-supplied identifiers may only look up an existing registration, never grant open network access.

## 16. Spring Boot Configuration and Responsibility Boundaries

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test
          jwk-set-uri: https://identity.example.test/oauth2/jwks
        opaquetoken:
          introspection-uri: https://identity.example.test/oauth2/introspect
          client-id: orders-resource-server
          client-secret: SECRET_FROM_SECRET_MANAGER
~~~

This illustrates the endpoints and configuration keys. In an application, pick JWT or opaque token according to your supported authentication mode; you do not necessarily declare both for the same filter chain. With Spring Boot, property namespaces and auto-configuration must match your version; custom decoders or introspectors can change how Boot applies properties.

The properties above **do not configure the full connection pool budget**. When granular pooling and timeouts are needed, provide a custom HTTP client, decoder, or introspector for your Servlet or Reactive stack.

## 17. Timeouts and Pools Must Not Break TLS

When configuring an issuer client:

- Keep certificate chain validation enabled.
- Keep hostname verification enabled.
- Use managed truststores/CAs.
- For mTLS introspection, supply the client certificate matching the registration.
- Rotate client certificates and close/refresh pools as needed so new connections pick up new credentials.
- Never disable TLS verification to work around handshake errors.

An established connection may continue using an older session/certificate context after certificate configuration changes, depending on the connector. Rotation plans must specify when to reload the SSL context and evict/close old connections.

## 18. Observability: Measuring Issuer Calls

Emit dedicated metrics per issuer and operation:

| Metric | Meaning |
| --- | --- |
| Request count | Number of JWKS/discovery/introspection calls. |
| Latency histogram | p50/p95/p99 for each operation. |
| Timeout count | Timeouts by acquire/connect/TLS/response/deadline. |
| Connection active/idle | Pool utilization. |
| Pending acquire | Requests waiting for a connection. |
| Acquire timeout/rejection | Pool saturation signals. |
| HTTP status | 2xx, 4xx, 429, 5xx. |
| Retry count | Transient failure level and retry amplification. |
| Circuit breaker state | Closed/open/half-open. |
| JWKS refresh/unknown kid | Key rotation and cache behavior. |
| Introspection cache hit/miss | Cache effectiveness and real load on the AS. |

Never log raw Access Tokens, Refresh Tokens, Authorization headers, client secrets, full introspection responses, or sensitive token claims. Metric labels must not include tokens, subject IDs, or unbounded dynamic URLs.

### 18.1. Distinguish Issuer Errors from Resource Server Errors

A 401 may indicate a bad token; a 503 may indicate an unavailable issuer; a 500 may be a mapping or application bug. Preserve exception categories and dependency names in internal logs/traces for analysis, while returning only safe minimal information to clients.

## 19. Testing Connection Pools and Timeouts

Unit tests on publishers are not enough to verify pools, TLS, HTTP status handling, connection reuse, and pending acquires. Use an HTTP stub server such as MockWebServer or WireMock to control issuer responses and delays.

### 19.1. Test Matrix

| Scenario | Expected Outcome |
| --- | --- |
| JWKS responds quickly, key cached | JWT decoding does not emit a JWKS request on every API call. |
| JWT carries new kid | Decoder refreshes JWKS per policy and verifies signature. |
| Slow JWKS endpoint | Fetch times out; tokens needing the new key are rejected. |
| JWKS returns 500 | Dependency error classified; signature check is not skipped. |
| Many concurrent unknown kids | Outbound concurrency and pool pending queue stay bounded. |
| Introspection returns active=true | Principal created per claims and authorization policy. |
| Introspection returns active=false | Authentication fails. |
| Introspection timeout | No principal created; dependency error observed. |
| Pool connections exhausted | Waiting requests are bounded then fail/reject. |
| Issuer returns 429 | Client honors rate-limit/backoff policy. |
| Issuer returns 401 for bad client secret | No unbounded retries; configuration alert triggered. |
| Circuit breaker open | Fails fast; does not fail open on authentication. |
| Introspection positive cache | Cache hits cut calls while TTL stays within revocation budget. |
| Token revoked | Cache invalidation/expiry reflects chosen SLA. |
| Untrusted issuer certificate | TLS validation fails. |
| mTLS certificate rotation | New connections use the updated certificate/context. |

### 19.2. Testing Pool Saturation

Create a stub issuer that holds responses for a controlled duration. Fire concurrent calls exceeding `maxConnections` and `pendingAcquireMaxCount`. Verify that active connections never exceed pool max, pending acquisitions never exceed queue max, requests waiting longer than the pending timeout fail, connections are returned to the pool or disposed properly once responses complete, and saturating one issuer pool does not starve another independent pool.

Never use `Thread.sleep` for synchronization in tests; use latches in the test harness, controllable responses, or publisher test utilities.

### 19.3. Testing Timeouts and Cancellation

With reactive clients, confirm timeouts raise the expected error and upstream HTTP exchanges are disposed/cancelled as supported by the connector. With servlet clients, confirm threads/requests are released after timeout; note that some blocking I/O operations cannot abort immediately upon thread interrupt.

### 19.4. Testing That JWT Requests Do Not Call the Issuer Every Time

Send multiple valid JWTs signed by the same key after the initial JWKS fetch. Count requests hitting the stub JWKS server. The count must match the decoder's cache/refresh policy rather than incrementing once per API call. Do not hardcode a default TTL if your library/version uses different settings.

## 20. Rough Capacity Estimation

Little's Law helps estimate average concurrent in-flight requests:

~~~text
in_flight ≈ arrival_rate × average_latency
~~~

Example:

- 100 introspection calls/second.
- Average latency 100 ms (0.1 seconds).

~~~text
in_flight ≈ 100 × 0.1 = 10
~~~

This is average concurrency assuming steady state. Production capacity needs headroom for p95/p99 latency, bursts, retries, connection churn, and instance count. Never size pool max equal to the average.

### 20.1. Cluster-Wide Sizing

With 10 instances each capped at 20 connections, total connection capacity can reach 200. Add other services calling the same issuer. Coordinate quotas with the AS operations team; per-instance pools alone do not enforce a global system quota.

### 20.2. Capacity When the Issuer Slows Down

When latency climbs from 100 ms to 2 seconds at 100 calls/s:

~~~text
in_flight ≈ 100 × 2 = 200
~~~

If the pool has only 32 connections, the pending queue fills rapidly. The pool acquire timeout and bulkhead reject excess requests early, protecting heap and other dependencies. This is why load tests must test elevated latency, not only nominal issuer speed.

## 21. Implementation Checklist

1. **Inventory issuer endpoints:** discovery, JWKS, introspection, and token endpoint if client/delegation flows exist.
2. **Distinguish JWT and opaque:** identify which calls happen online vs. cached.
3. **Fix trusted configuration:** issuer/JWKS/introspection URIs, TLS, and client credentials.
4. **Match HTTP client to stack:** pooled blocking client for Servlet; WebClient/reactive connector for WebFlux.
5. **Cap pools:** max connections, per-route caps, pending queue counts, and pending timeouts.
6. **Layer timeouts:** acquire, connect, TLS, response/read, and overall deadline.
7. **Isolate failure domains:** separate pools/bulkheads/concurrency per issuer and operation.
8. **Bound retries:** backoff/jitter, Retry-After, retry budgets, and idempotency where side effects exist.
9. **Stay fail closed:** unavailable introspection/JWKS never becomes evidence of a valid token.
10. **Define cache policies:** separate JWKS rotation from revocation-bounded introspection TTLs.
11. **Measure telemetry:** pool utilization, pending acquires, latency, timeouts, 429/5xx, refreshes, and cache hits.
12. **Load and failure test:** slow issuer, pool saturation, key rotation, unknown kids, 429, 5xx, TLS failures, and certificate rotation.

**Key takeaway:** A JWT Resource Server typically verifies offline using cached public keys; the issuer is only called when discovery/JWKS must be loaded or refreshed. An opaque Resource Server typically introspects tokens online, so load scales directly with request rate and cache policy. Use **bounded connection pools, finite pending queues, layered timeouts, bulkheads, and retry budgets**. JWKS caches and introspection caches carry different trade-offs; a circuit breaker or timeout must never become a successful authentication without trustworthy token verification.

## References

- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html).
- [Spring Security — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html).
- [Spring Security — Reactive Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html).
- [Spring Security — NimbusJwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html).
- [Spring Security — NimbusReactiveJwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html).
- [Project Reactor Netty — HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html).
- [Project Reactor Netty — Connection Pool](https://projectreactor.io/docs/netty/release/reference/http-client.html#_connection_pool).
- [Apache HttpClient 5 — Connection Management](https://hc.apache.org/httpcomponents-client-5.4.x/current/httpclient5/apidocs/org/apache/hc/client5/http/impl/io/PoolingHttpClientConnectionManager.html).
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414).
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html).
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517).
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662).
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009).
