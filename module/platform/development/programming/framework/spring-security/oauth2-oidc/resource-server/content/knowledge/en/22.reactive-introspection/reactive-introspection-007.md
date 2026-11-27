# WebClient, Timeouts, Request Cancellation, and Connection Limits

In a **Spring Security OAuth 2.0/OIDC Resource Server using WebFlux**, when an API receives an opaque access token, the Resource Server typically calls the Authorization Server's **OAuth 2.0 Token Introspection Endpoint** to check whether the token is active and obtain attributes such as **sub**, **scope**, **client_id**, and **aud**. In reactive Spring Security, the central interface is **ReactiveOpaqueTokenIntrospector**, while HTTP transport can use **WebClient** backed by **Reactor Netty**.

Crucially, introspection sits **on the authentication path of every request**. When the Authorization Server is slow, an API request may wait before the controller even starts executing. Using non-blocking WebClient avoids holding a Java thread on I/O per request, yet **does not eliminate limits on sockets, connection pools, pending queues, latency, or Authorization Server capacity**.

This lesson answers four closely related questions:

1. How does **WebClient** participate in the reactive introspection flow, and where should it be customized?
2. How should you distinguish **timeouts while waiting on the connection pool, TCP connect, TLS, receiving the response, and the overall publisher**?
3. When a caller disconnects or **`Mono.timeout`** triggers, what does **cancellation** mean and what does it not guarantee?
4. How do you configure **maxConnections**, **pendingAcquireMaxCount**, and **pendingAcquireTimeout** to avoid unbounded queues, overload, and fail-open behavior?

The goal is a **Resource Server that preserves its authentication boundary under overload**: if a token has not been verified successfully, the API must never construct a valid Authentication just to avoid errors.

## 1. Why Does Introspection Directly Affect API Latency?

A client sends:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer example-opaque-access-token
~~~

In WebFlux, the logical path can be:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as WebFlux Resource Server
    participant I as ReactiveOpaqueTokenIntrospector
    participant W as WebClient / Reactor Netty
    participant A as Authorization Server

    C->>R: Authorization Bearer token
    R->>I: introspect(token)
    I->>W: HTTP POST introspection
    W->>A: token + introspection client credentials
    A-->>W: active=true and metadata
    W-->>I: Decoded response
    I-->>R: Mono OAuth2AuthenticatedPrincipal
    R->>R: Build Authentication; check scope, tenant
    R-->>C: Valid response or error
~~~

**ReactiveOpaqueTokenIntrospector** returns:

~~~java
Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
~~~

This is a **Publisher**, not a synchronous result. Spring Security subscribes and composes it with the authentication flow before evaluating authorization.

Cases to distinguish:

- **active=true** from a trusted AS: token may be accepted; proceed to scope/audience/tenant checks.
- **active=false**: token is inactive; authentication is rejected.
- **AS does not respond**: token could not be verified; this is a timeout/infrastructure error, **never equivalent to active=true**.
- **AS returns 401 to the introspection client**: likely wrong client credentials or introspection policy; not proof the Bearer token was validated.
- **Active token missing scope**: authentication succeeds, while authorization can still return 403.

### 1.1. Non-Blocking Does Not Create Infinite Capacity

Suppose the Orders API receives **600 requests/second** and every request requires an uncached introspection call. The Authorization Server may have to handle nearly 600 introspection POSTs per second from this API alone.

If each round trip takes 200 ms, the number of concurrent outbound requests can be estimated as:

~~~text
Concurrent requests ≈ 600 request/s × 0.2 s = 120
~~~

This is a **Little's Law estimate**, excluding traffic spikes, p99 latency, HTTP protocol specifics, retries, and replicas. It does not by itself determine how many connections to open.

WebClient keeps event-loop threads unblocked while waiting on the network, yet in-flight requests still consume state, buffers, pool slots, and upstream capacity.

## 2. Participating Components in WebFlux

| Component | Responsibility |
|---|---|
| **SecurityWebFilterChain** | Protects requests in Reactive WebFlux |
| **AuthenticationWebFilter** | Converts Bearer tokens into authentication requests |
| **OpaqueTokenReactiveAuthenticationManager** | Authenticates opaque tokens using the introspector |
| **ReactiveOpaqueTokenIntrospector** | Introspection contract returning a Mono of principal |
| **SpringReactiveOpaqueTokenIntrospector** | Implementation calling the introspection endpoint |
| **WebClient** | Non-blocking HTTP client |
| **ReactorClientHttpConnector** | Bridges WebClient with Reactor Netty |
| **Reactor Netty HttpClient** | Configures networking, response timeouts, TLS |
| **ConnectionProvider** | Pools active/idle connections and pending acquisition queue |
| **Mono.timeout** | Publisher-scoped time limit |
| **ReactiveSecurityContextHolder** | Propagates security context in Reactor |
| **ServerAuthenticationEntryPoint** | Produces challenges when requests lack valid authentication |

**Do not confuse** WebFlux **ReactiveOpaqueTokenIntrospector** with Servlet **OpaqueTokenIntrospector**, or use blocking RestClient on the reactive event loop.

### 2.1. Default SpringReactiveOpaqueTokenIntrospector

A modern Spring Security configuration can build the introspector via its builder:

~~~java
ReactiveOpaqueTokenIntrospector introspector =
    SpringReactiveOpaqueTokenIntrospector
        .withIntrospectionUri(
            "https://login.example.com/oauth2/introspect")
        .clientId("orders-resource-server")
        .clientSecret("placeholder-not-real-secret")
        .build();
~~~

The builder exists in applicable Spring Security versions, such as 6.5+. Real secrets must come from a protected source; **never commit them to source control**.

When you need control over connection pools, timeouts, and custom HTTP settings, you can supply a **pre-configured WebClient** to the implementation via the constructor/API supported by your version.

## 3. What Does WebClient Send to the Authorization Server?

Per RFC 7662, the introspection request is typically a POST:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <encoded-resource-server-credentials>

token=<access-token>&token_type_hint=access_token
~~~

Bracketed values are placeholders. **The client credentials used for introspection** are not the token users send to the Orders API.

A successful response for an active token:

~~~json
{
  "active": true,
  "sub": "user-123",
  "client_id": "web-client",
  "scope": "orders.read",
  "aud": ["orders-api"],
  "exp": 1893456000
}
~~~

A response for an inactive token:

~~~json
{
  "active": false
}
~~~

**HTTP 200 from the introspection endpoint does not mean active=true**, because RFC 7662 uses HTTP 200 to return active=false. Never write custom WebClient code that checks only the HTTP status code and grants Authentication.

The introspection URI must be a **trusted, system-configured endpoint**, never read from a request parameter, unverified token, or arbitrary client-supplied URL. Otherwise, SSRF and token/client-secret exposure can result.

## 4. Timeout Layers Must Not Be Confused

A single introspection call passes through several stages:

~~~mermaid
flowchart LR
    S[Subscribe Mono] --> P[Wait on connection pool]
    P --> D[DNS resolution]
    D --> T[TCP connect]
    T --> L[TLS handshake]
    L --> Q[Send request]
    Q --> R[Wait / read HTTP response]
    R --> J[Decode and map principal]
    J --> F[Authentication result]
~~~

| Timeout | What does it protect? | Component |
|---|---|---|
| **Pending acquire** | Waiting too long for a connection from the pool | ConnectionProvider.pendingAcquireTimeout |
| **TCP connect** | Slow socket establishment to the AS | ChannelOption.CONNECT_TIMEOUT_MILLIS |
| **DNS** | Slow hostname lookup | Reactor Netty name resolver configuration |
| **TLS handshake** | Incomplete TLS negotiation | SSL/TLS provider timeout |
| **Response timeout** | Slow wait/read of HTTP response | HttpClient.responseTimeout |
| **Whole operation** | Total introspection publisher duration | Mono.timeout(Duration) |
| **Inbound deadline** | How long the caller/gateway still waits for the API | Gateway/application policy |

### 4.1. `pendingAcquireTimeout`

When no connection is free and **maxConnections** is reached, requests can enter the **pending acquire queue**.

~~~java
ConnectionProvider.builder("auth-introspection")
    .pendingAcquireTimeout(Duration.ofMillis(150))
    .build();
~~~

If 150 ms elapses without acquiring a connection, the operation fails at the acquisition step. It may **never have sent any HTTP POST to the AS**.

Never set `pendingAcquireTimeout` longer than the entire API request budget, because by the time a connection is granted the client may have disconnected long ago.

### 4.2. TCP Connect Timeout

~~~java
HttpClient client = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 800);
~~~

This bounds establishing a **new TCP connection**, not the entire HTTP round trip. If the pool holds a reusable keep-alive connection, the request can skip a new TCP connect.

### 4.3. Response Timeout

~~~java
HttpClient client = HttpClient.create()
    .responseTimeout(Duration.ofMillis(1500));
~~~

Reactor Netty allows setting a default response timeout on `HttpClient` or overriding it per request. Response timeout **does not replace** pool wait, DNS, connect, or overall deadlines.

### 4.4. Overall `Mono` Timeout

~~~java
return delegate.introspect(token)
    .timeout(Duration.ofMillis(2500));
~~~

The **`Mono.timeout`** operator bounds the duration from publisher subscription until an expected signal arrives per Reactor semantics. On expiration, it emits **`TimeoutException`** and requests upstream cancellation.

Placed right outside the entire **`delegate.introspect(token)`**, it can cover pool wait, networking, and response decoding together. Still, understand how the publisher is composed, operator placement, work outside the pipeline, and how retries/caching alter effective scope.

**`TimeoutException` does not prove a token was revoked or invalid.** It simply means verification did not complete in time.

## 5. Time Budget Calculation Example

Suppose the API has a response budget of roughly **4 seconds**, and business logic plus serialization need a substantial share. You might allocate an introspection budget of **2.5 seconds**.

| Stage | Example value |
|---|---:|
| Pool wait | 150 ms |
| TCP connect | 800 ms |
| Response wait | 1,500 ms |
| Overall introspection | 2,500 ms |
| Inbound API budget | 4,000 ms |

These are **illustrative figures**, not universal production recommendations.

Individual timeouts **do not sum linearly** into a final limit because the overall timeout spans multiple stages. DNS, TLS, queueing, and business logic must also fit inside the end-to-end budget.

If a gateway cuts the connection after 2 seconds while the Resource Server keeps waiting 10 seconds for introspection, resources continue being consumed unless cancellation propagates properly and the client/transport tears down promptly.

## 6. ConnectionProvider: Max Connections and Pending Queue

**ConnectionProvider** manages pooling for Reactor Netty. Common options:

| Property | Meaning |
|---|---|
| **maxConnections** | Limit on active pool connections |
| **pendingAcquireMaxCount** | Max queued acquire waiters |
| **pendingAcquireTimeout** | Max wait time to acquire |
| **maxIdleTime** | Idle duration after which a connection becomes eligible for eviction |
| **maxLifeTime** | Maximum connection lifetime |
| **metrics(true)** | Enables pool metrics via Micrometer if integrated |
| **dispose()** | Releases an application-owned pool |

Example:

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("auth-introspection")
        .maxConnections(32)
        .pendingAcquireMaxCount(64)
        .pendingAcquireTimeout(Duration.ofMillis(150))
        .maxIdleTime(Duration.ofSeconds(20))
        .maxLifeTime(Duration.ofMinutes(2))
        .metrics(true)
        .build();
~~~

With HTTP/1.1 against one remote host, active connections in the pool are capped accordingly; excess requests wait in the pending queue and either time out or are rejected once the queue is full.

### 6.1. `maxConnections` Is Not a QPS Limit

With **maxConnections=32**, do not infer the API handles at most **32 requests/second**. A single connection can be reused many times; throughput depends on latency, keep-alive, pipelining/protocol, and upstream capacity.

HTTP/2 can multiplex multiple streams over one connection, so concurrent requests and connection counts are not always equal.

### 6.2. Pool Limits Are Not Cluster-Wide Limits

With four replicas each maintaining a pool of 32 connections to the same AS, total cluster connections can be several times 32. Pools are normally scoped per remote destination/provider; never treat one process's `maxConnections` as a **global concurrency limit** for the entire system.

Coordinate with rate limiting, load balancing, AS capacity, and replica counts.

### 6.3. What Do Unbounded Queues Cause?

With an unbounded queue, a traffic spike can accumulate countless waiting requests long after callers gave up. The system wastes memory, latency, and tracing resources.

Setting a **finite `pendingAcquireMaxCount`** turns overload into an observable failure. A **short `pendingAcquireTimeout`** avoids doing work after the request's budget has expired.

Never "fix" timeouts by raising `maxConnections`/queues indefinitely. An already overloaded AS may collapse faster when hit with thousands of concurrent connections.

## 7. Configuring Spring Boot/WebFlux with a Dedicated Introspection WebClient

The following example has four layers:

1. A dedicated **ConnectionProvider** bean for the AS.
2. **HttpClient** configuring TCP and response timeouts.
3. Singleton **WebClient** carrying introspection credentials.
4. **SpringReactiveOpaqueTokenIntrospector** using that WebClient plus an overall timeout.

The example uses the modern Spring Security API providing the **`SpringReactiveOpaqueTokenIntrospector(String, WebClient)`** constructor. Check your actual API if targeting an older release line.

### 7.1. application.yml

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: example-inject-via-secret-manager
~~~

**Never place real literal client secrets in Git.** Load them from a secret manager or protected environment. This snippet only illustrates property names.

### 7.2. Complete Java Configuration

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpMethod;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
@EnableWebFluxSecurity
public class ReactiveIntrospectionConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider introspectionConnectionProvider() {
        return ConnectionProvider.builder("auth-introspection")
            .maxConnections(32)
            .pendingAcquireMaxCount(64)
            .pendingAcquireTimeout(Duration.ofMillis(150))
            .maxIdleTime(Duration.ofSeconds(20))
            .maxLifeTime(Duration.ofMinutes(2))
            .metrics(true)
            .build();
    }

    @Bean("introspectionWebClient")
    WebClient introspectionWebClient(
            ConnectionProvider introspectionConnectionProvider,
            Environment environment) {

        HttpClient httpClient = HttpClient
            .create(introspectionConnectionProvider)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 800)
            .responseTimeout(Duration.ofMillis(1500));

        String clientId = environment.getRequiredProperty(
            "spring.security.oauth2.resourceserver.opaquetoken.client-id");
        String clientSecret = environment.getRequiredProperty(
            "spring.security.oauth2.resourceserver.opaquetoken.client-secret");

        return WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(httpClient))
            .defaultHeaders(headers ->
                headers.setBasicAuth(clientId, clientSecret))
            .codecs(codecs ->
                codecs.defaultCodecs().maxInMemorySize(64 * 1024))
            .build();
    }

    @Bean
    ReactiveOpaqueTokenIntrospector opaqueTokenIntrospector(
            @Qualifier("introspectionWebClient") WebClient webClient,
            Environment environment) {

        String uri = environment.getRequiredProperty(
            "spring.security.oauth2.resourceserver.opaquetoken.introspection-uri");

        ReactiveOpaqueTokenIntrospector delegate =
            new SpringReactiveOpaqueTokenIntrospector(uri, webClient);

        return token -> delegate.introspect(token)
            .timeout(Duration.ofMillis(2500));
    }

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange()
                    .authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

### 7.3. Explaining the Decisions in the Example

**Dedicated pool:** the name `auth-introspection` lets you monitor connections to the AS separately from payment/reporting/notification HTTP clients.

**Basic authentication:** WebClient uses **`setBasicAuth(clientId, clientSecret)`** for introspection requests made through this dedicated client. **Never reuse a WebClient configured with default Basic credentials for user-supplied URIs.**

**Transport timeouts:** Reactor Netty `HttpClient` configures connect and response timeouts. This does not automatically create an overall deadline for everything.

**Response size limit:** introspection JSON is usually small. **64 KiB** is an illustrative buffer cap—tune it to your real contract. If upstream returns a huge body, the client should reject/error rather than buffering without limit.

**Overall timeout:** the decorator around the `Mono` bounds total wait time, including stalls in stages not covered by a dedicated timeout.

**Spring bean lifecycle:** the pool uses **`destroyMethod="dispose"`**, released when the `ApplicationContext` closes. Never dispose it after each request.

**Version caveat:** `SpringReactiveOpaqueTokenIntrospector` builders/constructors and some Reactor Netty APIs vary across Spring Security/Boot release lines. Modern Spring Security documents the `WebClient` constructor; on older versions check the matching Javadoc and never mix major versions.

### 7.4. Why Keep Client Secrets Out of Source Code?

Introspection credentials prove the Resource Server's right to query token status at the AS. If leaked, an attacker can abuse the introspection endpoint depending on AS policy.

Never log raw **`Authorization: Basic`**, client secrets, or Bearer tokens. Protect them in a secret manager, rotate them, and restrict introspection client permissions strictly to required resources.

### 7.5. A Dedicated WebClient Does Not Necessarily Need Dedicated Event-Loop Threads

A custom `ConnectionProvider` does not automatically create a separate Reactor Netty event-loop group. Per Spring Framework, `HttpClient` defaults to Reactor Netty shared resources. Usually sharing event loops appropriately is best unless there is a clear reason to isolate resource lifecycles.

If you explicitly configure non-global resources, the application must manage their shutdown; never dispose global resources shared with the server and other clients.

## 8. Pool Lifecycle: Reuse, Never Create Per Request

An anti-pattern:

~~~java
// WRONG: creates a new client/pool on every introspection call.
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    ConnectionProvider pool =
        ConnectionProvider.builder("temporary-pool").build();
    // Build WebClient and leak the pool on return...
    throw new UnsupportedOperationException("Anti-pattern");
}
~~~

Creating a new pool per request defeats keep-alive reuse, increases sockets/handshakes, and leaks resources.

The right approach is a **singleton WebClient/ConnectionProvider** wired via DI and reused:

~~~text
Application starts
   -> create ConnectionProvider
   -> create HttpClient
   -> create WebClient
   -> create ReactiveOpaqueTokenIntrospector

Each request
   -> subscribe introspect(token)
   -> borrow connection from pool
   -> send/receive HTTP
   -> release connection if reusable

Application stops
   -> dispose custom ConnectionProvider
~~~

**Never call `dispose()` inside `doFinally` per request.** The pool is shared; shutting it down while other requests are active causes widespread failures.

## 9. What Signal Is Cancellation in Reactor?

In Reactive Streams, **`cancel()`** is sent by a subscriber to signal **it no longer wants any more data from upstream**. It differs from normal completion or an error signal.

| Signal | Meaning |
|---|---|
| **onComplete** | Stream finished normally |
| **onError** | Publisher terminated with an error |
| **cancel** | Subscriber no longer wishes to receive signals |
| **Mono.timeout** | Can cancel upstream and emit TimeoutException downstream |

A WebFlux request can form a pipeline:

~~~text
Inbound request
 -> SecurityWebFilterChain
 -> OpaqueTokenReactiveAuthenticationManager
 -> ReactiveOpaqueTokenIntrospector
 -> WebClient
 -> Reactor Netty outbound connection
~~~

If the client closes the connection or an operator cancels, the signal **can propagate upstream** in a properly composed pipeline.

### 9.1. Causes of Cancellation

- Browser navigates away or client aborts the request.
- API Gateway hits its deadline and drops the connection.
- Introspection **`Mono.timeout`** fires.
- A reactive operator chooses another result or stops waiting.
- A test explicitly invokes cancel.
- Application code cancels the `Subscription`.

However, a disconnect does not guarantee you immediately see cancellation everywhere. Behavior depends on how the server connector, streaming, and operators are wired.

### 9.2. Cancellation Does Not Guarantee the Authorization Server Stops Processing

Suppose WebClient already transmitted the introspection HTTP POST. When the Resource Server cancels, the transport may abort the request/channel or reset a stream, yet **an AS that already received the request may continue looking up the token and generating a response**.

With HTTP/2, canceling a stream does not necessarily close the underlying TCP connection. With HTTP/1.1, a connection mid-response may not be safely reusable and gets closed; exact details depend on client/transport.

**Never treat cancellation as proof that all AS CPU/database work was saved.** To protect the AS, you still need pool bounds, rate limiting, controlled retries, and upstream timeouts.

### 9.3. Cancellation While Still in the Pending Queue

If a request is still waiting for a connection and has not sent HTTP yet, cancellation can remove it from the pending queue. This is a major benefit of reactive cancellation, though it must be verified with transport integration tests rather than inferred from a single metric.

## 10. Where to Place `doFinally`/`doOnCancel` for Accurate Observation

A decorator can record terminal signals without logging tokens:

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

class ObservedIntrospector implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;

    ObservedIntrospector(ReactiveOpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token)
            .doFinally(upstreamSignal ->
                recordSignal("upstream", upstreamSignal))
            .timeout(Duration.ofSeconds(3))
            .doOnError(error ->
                recordErrorType(error.getClass().getSimpleName()))
            .doFinally(outerSignal ->
                recordSignal("outer", outerSignal));
    }

    private void recordSignal(String stage, SignalType signal) {
        // Integrate safe metrics/logging; NEVER put raw tokens in tags.
    }

    private void recordErrorType(String errorClass) {
        // Record sanitized error class name; never log credentials.
    }
}
~~~

Because operator positions differ, a single **overall timeout** can look like:

~~~text
Mono inside timeout:  doFinally(CANCEL)
Mono outside timeout: doFinally(ON_ERROR)
~~~

The same timeout event can emit two signal types at **two different observation points**. Do not count them as two unrelated incidents without a correlation ID.

### 10.1. Do Not Self-Subscribe Inside the Introspector

~~~java
// WRONG: detaches the HTTP request from the authentication lifecycle.
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    delegate.introspect(token)
        .subscribe(principal -> writeToCache(principal));
    return Mono.empty();
}
~~~

Wrong because the caller never receives the true result, errors can be swallowed, and cancellation fails to propagate as expected.

Use composition:

~~~java
return delegate.introspect(token)
    .map(principal -> validateAndMap(principal));
~~~

In this example, **`validateAndMap`** must enforce metadata/authorities per a trusted contract and never synthesize principals from raw tokens.

### 10.2. Never Call `block()` on the Reactive Event Loop

~~~java
// WRONG in a WebFlux pipeline.
OAuth2AuthenticatedPrincipal principal =
    delegate.introspect(token).block();
~~~

A blocking call on the event loop stalls unrelated requests and is sometimes rejected by Reactor. Prefer `Mono`/`Flux` composition and non-blocking HTTP clients.

If integrating a blocking library is unavoidable, use a proper adapter and bounded scheduler/bulkhead; **never pick a blocking introspection client** just to obtain a synchronous result.

## 11. Connection Pools Do Not Replace Application-Wide Backpressure

`ConnectionProvider` bounds connections and connection-acquisition queues, yet it does not by itself limit:

- Total inbound HTTP requests.
- Number of `Mono` instances awaiting authentication.
- Number of replicas simultaneously calling the same AS.
- Load from other applications.
- Generated retries.
- Memory/CPU used for decoding and authorization.

For complete protection, combine:

1. **Gateway rate limits**, especially for unauthenticated traffic.
2. **Bounded concurrency/bulkheads** at the resource server when needed.
3. **Pool active/pending bounds**.
4. **Short pending acquire timeout**.
5. **Overall introspection deadline**.
6. **Circuit breaker** and error-appropriate retry policy.
7. Monitoring AS saturation and capacity.

### 11.1. When the Pending Queue Is Full

~~~mermaid
flowchart TD
    R[Inbound Bearer request] --> P{Connection available or creatable?}
    P -->|Yes| A[POST introspection]
    P -->|No| Q{Room in pending queue?}
    Q -->|Yes| W[Wait up to pendingAcquireTimeout]
    Q -->|No| E[Pool acquisition rejected]
    W -->|Acquired in time| A
    W -->|Timed out| T[Pool acquire timeout]
    A --> O[active true/false or AS error]
    E --> F[No Authentication created; record overload]
    T --> F
~~~

**Never treat a pool acquisition failure as an invalid token**, because the request may never have been sent. Equally, **never grant successful authentication** without an introspection result.

### 11.2. Abnormal Load from Forged Tokens

An attacker can send floods of random Bearer strings to make the Resource Server hammer the AS. Rate limiting must rely on trustworthy edge signals (IP/network, connection, gateway, or already-authenticated client registration), **never trusting unverified `sub`/`scope` claims**.

## 12. Retries and Timeouts Can Cause Self-Inflicted Load Storms

Retries can be reasonable for transient network glitches, yet **retrying every introspection exception is dangerous**.

| Result/error | Retry by default? |
|---|---|
| active=false, invalid token | **No** |
| Expired or revoked token | **No** |
| HTTP 401/403 at introspection endpoint due to bad client credentials | **No**, fix configuration |
| Claim/audience mismatch | **No** |
| Malformed token request | **No** |
| Temporary TCP failure/timeout | Very limited retries may be acceptable |
| AS 502/503/504 | Policy-governed; avoid amplifying load |
| Pool exhausted | Never retry immediately without limit |
| Client already canceled request | Pointless to retry for that request |

If you retry 3 times with a 2-second timeout per attempt, total duration can blow past the API budget. Therefore:

- Bound attempt counts.
- Target only eligible transport/upstream errors.
- Apply backoff/jitter where appropriate.
- Wrap the overall timeout **around all retries**.
- Never retry **`active=false`**.
- Never log raw tokens in retry hooks.
- Use circuit breakers and rate limits to shield the AS.

**Retries do not turn a fake token into a real one.**

## 13. Circuit Breakers Without Fail-Open

When the AS is slow or unavailable, a circuit breaker helps shed outbound traffic. However:

~~~text
Circuit open / AS unavailable
 -> No trusted introspection result
 -> No authenticated principal created
 -> Error response per policy
~~~

Never do:

~~~java
// WRONG: assumes token is valid when introspection fails.
return delegate.introspect(token)
    .onErrorResume(error -> Mono.just(fakeAdminPrincipal));
~~~

Network failures are not authorization. If a cache policy exists for previously verified tokens, explicitly specify TTL, revocation lag, key protection, and outage usage conditions.

## 14. Caching Reduces Load but Alters Token Revocation

One benefit of introspection is that the AS can flip a token to **`active=false`** immediately after revocation.

Without caching:

~~~text
Request 1 -> AS active=true -> authenticate
Token revoked
Request 2 -> AS active=false -> reject
~~~

Caching `active=true` for 5 minutes:

~~~text
Request 1 -> AS active=true -> store in cache
Token revoked
Request 2 -> cache active=true -> may still accept
Cache expires
Request 3 -> AS active=false -> reject
~~~

Thus caching is not merely a performance optimization; it **alters security semantics**. Define:

- Maximum acceptable revocation latency.
- TTL never exceeding token expiration.
- Whether the token guards sensitive operations.
- Whether synchronous invalidation exists from the AS.
- Whether the cache isolates issuer/audience/resource/tenant properly.
- How cache keys/raw tokens and metadata are protected.

### 14.1. Caching Also Affects Cancellation

A shared/cached `Mono` can have other subscribers even after one caller cancels. The upstream HTTP request still has reason to finish even if the first caller left.

Therefore, never guess cancellation behavior when using **`cache()`**, **`share()`**, or request deduplication; test the exact composition and TTL behavior.

## 15. Metrics Needed in Production

In Reactor Netty, pool metrics can be exported via Micrometer, for example:

~~~text
reactor.netty.connection.provider.total.connections
reactor.netty.connection.provider.active.connections
reactor.netty.connection.provider.idle.connections
reactor.netty.connection.provider.pending.connections
reactor.netty.connection.provider.max.connections
reactor.netty.connection.provider.pending.connections.time
reactor.netty.connection.provider.max.pending.connections
~~~

Exact names/tags depend on version and integration. Use a **stable pool name** and metrics broken down by introspection outcome.

| Application metric | Meaning |
|---|---|
| **introspection.duration** | Overall publisher latency |
| **introspection.valid** | AS accepted token |
| **introspection.invalid_token** | AS rejected token |
| **introspection.timeout** | Per-layer timeouts if distinguishable |
| **introspection.transport_error** | DNS/TLS/TCP or HTTP client failure |
| **introspection.pending** | Connection acquisition waits |
| **introspection.cancelled** | Reactive subscriber cancellations |
| **introspection.rejected** | Pool/bulkhead rejections under load |
| **introspection.upstream_5xx** | AS infrastructure errors |

**Never use token values, user emails, `sub`, or Authorization headers as metric labels.** These are sensitive data and cause high cardinality. Only log request correlation IDs, logical endpoint names, durations, and sanitized errors.

### 15.1. p95/p99 Matter More Than Averages

Response timeouts and pool sizes tuned solely on mean latency easily fail when the AS exhibits high tail latency. Measure p50/p95/p99, peak traffic, and pending queue times; size timeouts and pools from those numbers.

Never enable HTTP wiretap logging containing introspection form bodies and credentials in production without strict redaction controls.

## 16. HTTP/1.1, HTTP/2, and Connection Reuse

With HTTP/1.1, many concurrent HTTP requests require multiple connections since each connection handles one in-flight response at a time.

With HTTP/2, one TCP/TLS connection can carry many concurrent streams. In that case:

- `maxConnections` does not directly equal max concurrent introspection requests.
- HTTP/2 stream limits and upstream settings can become the bottleneck.
- Cancellation can reset a stream without closing the connection.
- Load tests must use the same HTTP protocol as production.

Never extrapolate HTTP/2 concurrency capacity from HTTP/1.1 connection counts without testing.

### 16.1. `maxIdleTime` and Upstream Load Balancers

If the AS or load balancer closes idle connections after 30 seconds, setting client `maxIdleTime` too high increases errors when reusing connections already closed by the peer.

Reactor Netty recommends keeping client idle timeout equal to or shorter than the upstream idle timeout. For instance, **20 seconds** is a starting point to test, not a universal rule.

### 16.2. `maxLifeTime` and Lifecycle

`maxLifeTime` prevents connections from living forever, which helps with network changes. Still, it does not guarantee immediate pickup of DNS or TLS rotation. Test AS IP changes, certificate rotations, and load balancer topology shifts.

## 17. What Happens When the Caller Disconnects?

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant R as WebFlux Resource Server
    participant W as WebClient
    participant A as Authorization Server

    B->>R: GET /api/orders/42
    R->>W: Subscribe introspection
    W->>A: POST /introspect
    B--xR: Client disconnect
    R--xW: Cancel upstream if pipeline propagates signal
    Note over W,A: Outbound may abort or reset stream
    Note over A: AS may already have processed request
~~~

Guidelines:

- Return **`Mono`**; never manually **`subscribe()`** inside the introspector.
- Never **`block()`** on the Reactor event loop.
- Place timeout/cancellation metrics at the right observation points.
- Never treat cancellation as a revoked token.
- Never assume the AS definitely canceled its work.
- If caching/shared `Mono` is used, one subscriber canceling does not imply upstream cancels.
- Verify resource cleanup with integration tests rather than relying on code that merely looks reactive.

## 18. `StepVerifier`: Testing Timeouts and Cancellation at the Reactor Level

Use **`reactor-test`** and JUnit 5 to verify operator semantics.

### 18.1. Timeout Emits an Error

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TimeoutTest {

    @Test
    void neverCompletingPublisherTimesOut() {
        Mono<String> slow =
            Mono.<String>never().timeout(Duration.ofMillis(50));

        StepVerifier.create(slow)
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(2));
    }
}
~~~

This test verifies **`Mono.timeout`**, not TCP sockets or the HTTP connection pool. To avoid flaky timing, use virtual time or controlled clocks in Reactor Test when designing tests.

### 18.2. Cancellation Propagates to the Publisher

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class CancellationTest {

    @Test
    void cancelReachesUpstream() {
        AtomicBoolean cancelled = new AtomicBoolean();

        Mono<String> publisher = Mono.<String>never()
            .doOnCancel(() -> cancelled.set(true));

        StepVerifier.create(publisher)
            .thenCancel()
            .verify();

        assertTrue(cancelled.get());
    }
}
~~~

This proves **Reactor signal cancellation**, not that a remote AS stopped work or that a socket closed/reused cleanly. Those require an HTTP test server and Reactor Netty metrics.

## 19. Testing WebClient Against an HTTP Stub

Use a test HTTP server such as MockWebServer, WireMock, or Reactor Netty test server in place of a production Authorization Server.

Key cases:

1. **`active=true`** with matching scope → Authentication succeeds.
2. **`active=false`** → rejected; no principal created.
3. **AS returns HTTP 401** to introspection client → never fail open.
4. **AS delays response** beyond `responseTimeout` → client errors.
5. **AS delays** beyond overall timeout → outer Mono emits `TimeoutException`.
6. **Concurrent requests exceed `maxConnections`** → pending acquisitions occur.
7. **Pending queue overflows** → acquisition rejected.
8. **Pending wait exceeds limit** → `pendingAcquireTimeout`.
9. **Client cancels** while outbound request is pending → observe cleanup/cancellation.
10. **Invalid TLS hostname/certificate** → request rejected.
11. **Oversized body or malformed JSON** → no principal created.
12. **AS returns `active=true` without required audience** → custom policy rejects.

Control stub delays and concurrency deliberately. Avoid writing brittle tests that assume request #33 must be queued when scheduling, keep-alive, or HTTP/2 alters ordering.

### 19.1. `WebTestClient` Tests the Resource Server, Not Transport Mechanics

In WebFlux, **`WebTestClient`** wired with Spring Security filters can assert status codes:

| Scenario | Typical outcome |
|---|---|
| Missing Bearer token | **401** |
| Introspection `active=false` | **401 invalid_token** |
| `active=true` with required scope | Request reaches handler |
| `active=true` missing scope | **403** |
| Introspection timeout | Error; no authentication |
| Pool exhausted | Infrastructure error; never fail open |

**`mockOpaqueToken()`** in Spring Security Test injects a mock Authentication to test authorization; it **bypasses real WebClient introspection**. Thus it cannot verify timeouts, TLS, queues, or connection pools. You need integration tests with a fake HTTP AS to exercise the network path.

## 20. 401, 403, and Introspection Infrastructure Errors

One classification scheme:

| Outcome | Enough info to authenticate? | Handling |
|---|---|---|
| No token | No | Bearer challenge, typically 401 |
| AS returns `active=false` | No | Invalid token, typically 401 |
| `active=true`, missing scope | Yes, but insufficient privilege | 403 when rule applies |
| `active=true`, wrong tenant | May be authenticated | Domain policy 403/404 |
| DNS/TCP/TLS timeout | Unverified | Infrastructure error, never fail open |
| Pool pending timeout | Introspection incomplete | Overload/infrastructure error |
| WebClient response timeout | No trusted result | Timeout error |
| Client cancel | Response may not be needed | Stop downstream work per lifecycle |
| AS 5xx | No verification result | Monitor upstream; no principal created |
| Introspection client 401/403 | AS denies client introspection | Fix credentials/policy |

**Never claim every `TimeoutException` defaults to HTTP 401 or 503.** Status depends on exception conversion and handlers in your application/Spring Security version. The mandatory rule is that a token is never treated as valid when introspection did not succeed.

### 20.1. Never Turn Every Transport Error into `invalid_token`

**`active=false`** is a verdict on the token. **Network timeout** means verification failed to finish within budget.

Neither grants access, yet they require distinct logging, metrics, and error policies. If a custom handler formats errors, never expose raw tokens, client secrets, internal hostnames, or stack traces to callers.

## 21. Incident Walkthrough: Slow AS Fills the Pool

Suppose each Resource Server replica has:

~~~text
maxConnections = 32
pendingAcquireMaxCount = 64
pendingAcquireTimeout = 150 ms
responseTimeout = 1500 ms
overallTimeout = 2500 ms
~~~

If the AS takes 2 seconds per response:

1. Active connections remain occupied longer.
2. New requests fill the pending queue.
3. Some pending requests time out after 150 ms or are rejected when the queue fills.
4. Requests holding connections hit the response timeout.
5. Some callers cancel due to gateway deadlines.
6. Authentication never completes for failed requests; none receive privileges.
7. Pool metrics show active/pending spikes; upstream latency or 5xx errors must be investigated.

**Do not simply bump `maxConnections` from 32 to 5,000.** That can overwhelm the AS with even more sockets and crash it faster. Evaluate capacity, traffic bursts, caching/retries, rate limits, and p99 latency instead.

## 22. Anti-Patterns to Recognize

**Creating a new `WebClient` and `ConnectionProvider` per Bearer request.** Breaks connection reuse, increases handshakes, and leaks resources.

**Calling `block()` inside `ReactiveOpaqueTokenIntrospector`.** Blocking the event loop inflates latency and can trigger runtime errors.

**Omitting timeouts at both the network layer and the overall publisher.** A single request can pin a connection or pending slot indefinitely.

**Having only an overall timeout with no pool bounds.** Bursts can pile up massively before timeouts fire.

**Keeping an unbounded pending queue.** Expired requests keep consuming memory and waiting.

**Retrying every exception.** Retrying `active=false` and `invalid_token` is useless; retrying during AS overload amplifies incidents.

**Failing open on introspection errors.** Never fabricate an ADMIN principal or `active=true` on a network timeout.

**Self-subscribing to call the AS outside the pipeline.** Breaks cancellation and error propagation in the security flow.

**Putting raw tokens in logs or metric tags.** Exposes Bearer credentials and creates high-cardinality telemetry.

**Trusting a client-supplied introspection URI.** Enables SSRF and leaks client credentials.

**Treating AS HTTP 200 as an active token.** Always check JSON `active`; HTTP 200 can carry `active=false`.

**Treating cancel as remote rollback.** The AS may already have received and processed the request.

**Using a `WebClient` carrying Basic credentials for arbitrary URLs.** Restrict it strictly to trusted AS endpoints.

**Failing to dispose custom pools on shutdown.** Sockets and connections can leak.

**Confusing timeouts with token revocation.** Both may deny access, yet require different explanations.

## 23. Design and Implementation Checklist

### Step 1 — Define the Introspection Contract

Use only trusted Authorization Servers/URIs, HTTPS, protected credentials, required claims such as **`active`, `aud`, `scope`**, and token-type/tenant policies.

### Step 2 — Measure Latency Requirements

Estimate peak QPS and p95/p99 introspection latency. Budget an overall timeout smaller than the system's request budget.

### Step 3 — Create a Dedicated WebClient

Configure a fixed endpoint, client credentials, response body size limit, `HttpClient` timeouts, and `ConnectionProvider` bounds. Never use client-supplied URLs.

### Step 4 — Bound Active and Pending Requests

Use finite `maxConnections`, `pendingAcquireMaxCount`, and `pendingAcquireTimeout`, sized across all replicas against AS capacity.

### Step 5 — Handle Cancellation Properly

Return composed `Mono` pipelines; never `block()`/`subscribe()` inside filters or introspectors. Place `doFinally`/`doOnCancel` accurately and test cleanup.

### Step 6 — Design Fail-Closed Error Handling

Inactive tokens, timeouts, exhausted pools, and upstream outages **never produce a successful Authentication**. Classify errors appropriately for monitoring and responses.

### Step 7 — Cache and Retry Only by Policy

Caching must honor revocation lag and token expiration. Retries must filter for transient errors, use backoff, and stay inside an overall deadline.

### Step 8 — Integrate Observability

Track active/pending pool metrics, durations, timeout classes, cancellations, AS 5xx, and circuit-breaker state without logging credentials.

### Step 9 — Test with an HTTP Test Server

Use an AS stub to simulate response delays, `active=false`, malformed responses, 401 client credentials, overload, and cancellation. Use `WebTestClient` to test end-to-end authentication and authorization.

### Step 10 — Re-Evaluate When Scaling Deployments

Adding replicas or changing AS, gateways, TLS, or HTTP protocols alters connection capacity and latency. Re-test pools and timeouts in realistic environments.

## 24. Self-Check Questions

**1. Does non-blocking WebClient mean a slow AS will not affect the API?**

No. It avoids holding a blocked thread per request, yet pools, pending queues, memory, and end-to-end latency are still impacted.

**2. Does `responseTimeout` cover `pendingAcquireTimeout`?**

No. They bound completely different stages.

**3. Can `Mono.timeout` bound an entire introspection call?**

Yes, when placed around the corresponding publisher. It emits `TimeoutException` and signals upstream cancellation upon expiration.

**4. Does cancel guarantee the AS stops processing the HTTP POST?**

No. The AS may have already received the request and continued processing after the client stopped waiting.

**5. Does `maxConnections=32` mean at most 32 requests/second?**

No. That is the pool's active connection cap, not QPS; HTTP/2 also adds stream multiplexing.

**6. Is one replica's `maxConnections` a cluster-wide limit?**

No. Other replicas maintain their own pools and other clients also call the AS.

**7. Why avoid an unbounded pending queue?**

Because requests can wait indefinitely past their deadlines and consume memory with no useful result.

**8. May we retry `active=false` until the AS returns true?**

No. `active=false` is an invalid-token verdict, not a transient network error.

**9. Should `active=true` be cached?**

Only within explicitly defined TTLs, token expiration, revocation lag, and security policies.

**10. Does testing cancellation with `StepVerifier` prove the socket closed?**

No. `StepVerifier` checks only Reactor signals; network integration tests are required.

**11. Can a JWT-shaped token be introspected with the opaque strategy?**

Yes. When the Resource Server chooses introspection, validation still depends on the AS response and faces the same timeouts, cancellation, and pool limits.

**12. Should a timeout be treated as `invalid_token`?**

No. A timeout merely shows the Resource Server failed to get a trusted verification result within the deadline.

## Conclusion

In a **Spring Security WebFlux Resource Server**, opaque-token introspection is typically a reactive HTTP operation over **WebClient/Reactor Netty**. Every authentication depends on **connection pools, networking, Authorization Server latency, and the Reactor subscription lifecycle**.

A reliable design includes:

- A **singleton WebClient** talking strictly to trusted introspection endpoints.
- **Dedicated timeouts** for pending acquire, TCP connect, and response, plus an **overall `Mono.timeout`** for the request budget.
- A **bounded `ConnectionProvider`** for `maxConnections` and the pending queue instead of unbounded connections/queues.
- **Cancellation propagation** via Publisher composition, without assuming the AS stopped work after cancel.
- **Fail-closed behavior when introspection fails**, never fabricating principals from unverified tokens.
- **Metrics, bounded retries/caching, and HTTP integration tests** to evaluate performance, revocation, and overload.

**Never just increase pool sizes to "fix" a slow upstream, call `block()`/`subscribe()` in the wrong place, retry `invalid_token`, or confuse timeouts with token revocation.** Keeping these distinctions straight is foundational to maintaining security and availability when a Resource Server depends on an introspection service.

### References

- [Spring Security — Reactive OAuth 2.0 Resource Server Opaque Tokens](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/)
- [Spring Security API — ReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html)
- [Spring Security API — SpringReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html)
- [Spring Security API — SpringReactiveOpaqueTokenIntrospector.Builder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.Builder.html)
- [Spring Framework — WebClient Configuration and Timeouts](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html)
- [Reactor Netty — HTTP Client, Connection Pool and Timeouts](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [Project Reactor — Reactor Core Reference](https://projectreactor.io/docs/core/release/reference/)
- [Project Reactor — Reactor Test StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
