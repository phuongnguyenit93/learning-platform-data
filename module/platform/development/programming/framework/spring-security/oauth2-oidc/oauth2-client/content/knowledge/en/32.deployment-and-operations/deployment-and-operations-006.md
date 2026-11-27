# 32.6. Timeouts, Connection Pools, and Load Control Toward Providers

## Lesson objectives

In a **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, properly configuring the issuer, client ID, client secret, scopes, and redirect URI only covers the protocol layer. In production operations, the application also depends on **network latency**, **connection pools**, **timeouts**, **the capacity of the OpenID Provider/Authorization Server**, and how the application handles errors.

A system may log in 10 users rapidly yet stall when 2,000 employees start a shift simultaneously; a refresh request may time out after the Authorization Server (AS) already rotated the refresh token; or a key rotation may cause every Pod to fetch JWKS at once.

This lesson teaches how to design operational boundaries while preserving OAuth/OIDC invariants.

After this lesson, you will be able to:

- Distinguish browser authorization redirects from backend HTTP calls.
- Identify token, refresh, client credentials, UserInfo, JWKS, discovery, and revocation requests.
- Distinguish connection-acquire, connect, response/read, TLS, overall, and idle timeouts.
- Design HTTP pools with max connections, per-route quotas, bounded pending queues, and idle eviction.
- Calculate total cluster load and provider quotas across multiple Pods.
- Wire HTTP clients properly into Spring Security OAuth2 Login and Refresh Token providers.
- Configure Reactor Netty/WebClient for WebFlux.
- Apply controlled rate limits, bulkheads, circuit breakers, backoff, and jitter.
- Avoid blind retries on authorization codes and rotating refresh tokens.
- Monitor p95/p99 latency, pool saturation, 429s, refresh failures, and secret-safe logs.
- Test slow providers, pool exhaustion, fake 429/503 responses, and fail-closed behavior.

---

## 1. Map of outbound requests

~~~mermaid
flowchart LR
    Browser["Browser"] -->|"302 redirect"| Authorize["OP /authorize"]
    Browser -->|"Callback code + state"| Portal["Spring Security Portal"]
    Portal -->|"POST code / refresh"| Token["OP /token"]
    Portal -->|"GET claims if needed"| UserInfo["OP /userinfo"]
    Portal -->|"GET signing keys"| JWKS["OP /jwks"]
    Portal -->|"GET provider metadata"| Discovery["OIDC discovery"]
    Portal -->|"Bearer access token"| API["Orders API"]
~~~

Not every arrow is executed by the same HTTP client.

| Operation | Actor | When | Impact when slow |
|---|---|---|---|
| Authorization endpoint | Browser | Login start | User waits on OP |
| Authorization Code token exchange | Backend Portal | Callback | Servlet threads/HTTP connections held |
| Refresh Token grant | Backend Portal | Token near expiry | Downstream API calls slow down |
| Client Credentials grant | Backend job | Requesting service token | Jobs and API calls slow down |
| UserInfo | Backend (if UserInfo enabled) | After OIDC token validation per flow | Login slows down |
| JWKS | Backend JWT/OIDC decoder | Cache miss/rotation | ID token verification slows down |
| OIDC discovery | Backend per config/version | Startup/config | Startup/readiness slows down |
| Revocation | Backend per workflow | Logout/token cleanup | Remote revocation slows down |

### 1.1. Authorization redirects do not use the token connection pool

`OAuth2AuthorizationRequestRedirectFilter` typically returns:

~~~http
HTTP/1.1 302 Found
Location: https://login.example.com/authorize?client_id=...&state=...
~~~

The browser calls the OP. Increasing the backend token pool will not make the OP login page render faster.

### 1.2. The Token Endpoint is a sensitive backend request

~~~http
POST /token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-auth>

grant_type=authorization_code&code=...&redirect_uri=...
~~~

This request requires timeouts, pooling, and grant-aware retry policies. Never log authorization codes or client authentication.

### 1.3. It is not just the token endpoint

UserInfo, JWKS, and metadata discovery may use separate HTTP transports and do not automatically inherit the HTTP client configured for token grants.

## 2. Distinguishing each type of timeout

An HTTP request passes through multiple stages:

~~~text
Wait for rate/bulkhead permit
  -> Wait for pooled connection
  -> DNS
  -> TCP connect
  -> TLS handshake
  -> Send request
  -> Wait for response headers
  -> Read body
  -> Parse/validate tokens
~~~

| Type | What it bounds | When misconfigured/missing |
|---|---|---|
| Pool acquire timeout | Waiting for a free connection | Queues/threads block indefinitely |
| Connect timeout | Establishing TCP | Long waits reaching dead hosts |
| TLS handshake timeout | TLS handshake | TLS stalls |
| Response/read timeout | Waiting for response/data per client semantics | Server accepted connection but processes slowly |
| Overall deadline | End-to-end operation duration | Cumulative stages exceed SLO |
| Idle timeout | Keeping idle connections in the pool | Accumulation of idle/stale sockets |
| Max connection lifetime | Connection age | Connections live too long |
| Authorization request TTL | Time `state` waits for browser callback | Old callbacks accepted too long or users expire early |

### 2.1. Connect timeout is not response timeout

TCP connection establishment might succeed in 100 ms while the AS takes 30 seconds to process the token. `connect-timeout=2s` does not bound that request's processing time.

### 2.2. Pool-acquire timeout must be short and bounded

A pool caps at 30 active connections; the 31st request must wait. If the queue is unbounded, the app can stall thousands of Servlet threads.

### 2.3. Response timeout is not always total request deadline

Some HTTP clients bound only response/inactivity wait time. Understand the exact semantics of Apache HC5, Reactor Netty, or whichever client you use.

### 2.4. Total duration is not guaranteed to be a simple sum

~~~text
acquire = 500ms
connect = 2s
response = 4s
~~~

Never assume the operation will always finish under 6.5 seconds: DNS, TLS, retries, body reading, and application logic each consume budget.

### 2.5. State TTL is completely different from HTTP timeouts

A user may take several minutes to complete MFA and consent, whereas backend token requests should time out in a few seconds. Never set OAuth state TTL equal to HTTP response timeout.

### 2.6. Illustrative configuration

~~~yaml
app:
  oidc-http:
    pool-acquire-timeout: 500ms
    connect-timeout: 2s
    response-timeout: 4s
    max-total-connections: 80
    max-per-route: 30
    idle-timeout: 30s
    max-life-time: 5m
~~~

**`app.oidc-http` is custom configuration**, not properties applied automatically by Spring Security. You must bind them onto the right HTTP client.

## 3. Choosing timeouts based on SLOs

There is no single magic number for all providers.

Measure:

- Token endpoint p50, p95, p99.
- JWKS/UserInfo latency.
- DNS/TLS/proxy latency.
- 429/5xx rates.
- Servlet request thread capacity.
- Ingress/load balancer timeouts.
- Provider SLA, client quotas, and login SLOs.

### 3.1. Example budget

| Parameter | Hypothetical value | Effect |
|---|---:|---|
| Pool acquire | 0.5 s | Prevents unbounded queuing |
| TCP connect | 2 s | Fails dead connections early |
| Response | 4 s | Caps slow provider calls |
| Callback outbound total | Per SLO, e.g., a few seconds | Overall deadline if needed |
| Idle eviction | 30 s | Cleans up idle connections |
| Max lifetime | 5 minutes | Controlled connection refresh |
| Pending state TTL | Several minutes | Gives users time for login/MFA |

Illustrative values only, not production defaults.

### 3.2. Timeouts too short

Increase false failures, causing users to retry login, generating extra token requests and refresh storms.

### 3.3. Timeouts too long

Hold threads/connections too long, inflate p99 latency, build queue backlogs, and may exceed ingress timeouts before the backend stops processing.

### 3.4. Tune to real latency

Do not raise timeouts simply to silence timeout logs. If OP p99 already breaches your SLO, shed load, optimize network paths, or coordinate with the provider.

## 4. Connection pools and resource limits

Pools amortize the cost of opening new TCP/TLS connections:

~~~text
No reuse:
  request A -> TCP/TLS -> response -> close
  request B -> TCP/TLS -> response -> close

With keepalive:
  request A -> TCP/TLS -> response -> idle
  request B -> reuse connection -> response
~~~

### 4.1. Key parameters

1. Maximum total connections.
2. Maximum connections per route/host.
3. Maximum pending acquire count.
4. Pool acquire timeout.
5. Idle eviction.
6. Maximum connection lifetime.
7. DNS/TLS/proxy policies.
8. Response body/stream closure.
9. Metrics for active/idle/pending connections.

### 4.2. Larger pools do not make the provider faster

Raising a pool from 40 to 200 can overload the OP or trigger more 429s, especially when many Pods scale up simultaneously.

### 4.3. Pools need a shared lifecycle

Never create a new HTTP client/connection manager per callback. Use a singleton bean with explicit shutdown/cleanup.

### 4.4. Connection leaks

If response bodies are not consumed/closed, connections may never return to the pool, spiking acquire timeouts even while the OP is healthy.

### 4.5. Per-route quotas

When one transport serves both OP A and OP B, per-route limits prevent one host from exhausting all connections. If tenant isolation is critical, consider dedicated pools or bulkheads.

## 5. Calculating concurrency from load

Little's law helps estimate:

\[
L \approx \lambda \times W
\]

- \(L\): average concurrent requests.
- \(\lambda\): request rate per second.
- \(W\): average latency in seconds.

For example, 80 requests/second at 0.25 seconds latency:

~~~text
80 × 0.25 = 20 average in-flight requests
~~~

When OP p99 latency jumps to several seconds, real concurrency spikes sharply; plan headroom and bounded queues.

### 5.1. Total cluster capacity

6 Pods, each with 30 connections to the same OP:

~~~text
Cluster potential = 6 × 30 = 180 connections
~~~

If the provider quota is 100, the cluster can exceed it even if each Pod looks modest.

### 5.2. HPA changes quota consumption

Autoscaling from 4 to 12 replicas multiplies connection pools and discovery/JWKS warm-up traffic. Do not mistake a per-Pod pool limit for a cluster-wide rate limiter.

### 5.3. Rate, concurrency, pool, and queue are four distinct quantities

- Rate: requests/second.
- Concurrency: simultaneous operations.
- Pool: physical/logical HTTP connections.
- Queue: requests waiting for permits/connections.

Each limit serves a distinct purpose.

## 6. Typical load storms

### 6.1. Login storm

At shift start, many users return to the callback at once; the token endpoint receives a burst of authorization-code POSTs.

### 6.2. Refresh storm

Tokens issued around the same time expire together and refresh simultaneously.

### 6.3. Client Credentials cold start

Many new jobs or Pods request service tokens simultaneously even though tokens could be reused.

### 6.4. JWKS stampede

The OP rotates a signing key, and many Pods encounter the new `kid` at once and fetch JWKS.

### 6.5. Metadata discovery storm

A rolling deployment initializes registrations from issuer metadata simultaneously.

### 6.6. UserInfo amplification

If the flow calls UserInfo, every login adds an HTTP GET carrying the access token. Account for this load separately.

## 7. Rate limiting, bulkheads, and bounded queues

~~~mermaid
flowchart TD
    D["Login / refresh demand"] --> RL["Rate limiter"]
    RL --> BH["Bulkhead concurrency cap"]
    BH --> Q["Bounded queue"]
    Q --> HP["HTTP pool"]
    HP --> OP["OpenID Provider"]
    RL --> X["Controlled rejection"]
    BH --> X
    Q --> X
~~~

### 7.1. Rate limiter

Limit request rates by client registration, tenant, IP/session, or grant type. Avoid overly blunt policies that block legitimate post-MFA callbacks without UX or retry guidance.

### 7.2. Bulkhead

Cap maximum concurrent calls to the OP; when the OP slows down, prevent the entire Portal from exhausting all worker threads.

### 7.3. Bounded queue

Never let backlogs grow unbounded. Under overload, fail fast in a controlled way aligned with SLOs.

### 7.4. Circuit breaker

When a provider repeatedly times out or returns 5xx, a breaker can curb outbound requests and aid recovery. A breaker must never permit creating an OIDC Authentication without a verified token.

### 7.5. Load shedding

Some features may return 503 or a temporary login-unavailable page. Never redirect to login endlessly or accept unverified ID tokens to boost availability.

## 8. Servlet: Apache HttpClient 5 pooled transport

With Spring Framework 6.x / Spring Boot 3.x and Apache HttpClient 5, you can configure a shared connection pool:

~~~xml
<dependency>
    <groupId>org.apache.httpcomponents.client5</groupId>
    <artifactId>httpclient5</artifactId>
</dependency>
~~~

### 8.1. Bean configuration

~~~java
import java.time.Duration;

import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io
        .PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.TimeValue;
import org.apache.hc.core5.util.Timeout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;

@Configuration
public class ProviderHttpConfiguration {

    @Bean(destroyMethod = "close")
    CloseableHttpClient providerApacheClient() {

        var manager =
                PoolingHttpClientConnectionManagerBuilder
                        .create()
                        .setMaxConnTotal(80)
                        .setMaxConnPerRoute(30)
                        .build();

        var requestConfig = RequestConfig.custom()
                .setConnectionRequestTimeout(
                        Timeout.ofMilliseconds(500))
                .setResponseTimeout(
                        Timeout.ofSeconds(4))
                .build();

        return HttpClients.custom()
                .setConnectionManager(manager)
                .setDefaultRequestConfig(requestConfig)
                .evictExpiredConnections()
                .evictIdleConnections(
                        TimeValue.ofSeconds(30))
                .build();
    }

    @Bean
    ClientHttpRequestFactory providerRequestFactory(
            CloseableHttpClient providerApacheClient) {

        var factory =
                new HttpComponentsClientHttpRequestFactory(
                        providerApacheClient);

        factory.setConnectTimeout(
                Duration.ofSeconds(2));

        return factory;
    }
}
~~~

### 8.2. Meaning

- `maxConnTotal`: pool-wide connection cap.
- `maxConnPerRoute`: per-route connection cap.
- `connectionRequestTimeout`: waiting for a connection from the pool.
- `responseTimeout`: waiting for response per Apache HC5 semantics.
- `setConnectTimeout`: TCP connect duration.
- `evictIdleConnections`: closes idle connections.
- `destroyMethod`: closes cleanly on shutdown.

### 8.3. Check versions

HTTP client and timeout APIs can change across minor versions. Use BOM-compatible libraries and write integration tests verifying timeouts actually take effect.

### 8.4. Max idle and max lifetime differ

Idle eviction acts on idle duration. Max lifetime caps total connection age regardless of activity and can be configured on the connection manager depending on version.

### 8.5. Pools do not cap RPS

30 connections can drive hundreds of requests/second when each request is fast. Use a dedicated rate limiter when the OP enforces quotas.

## 9. Wiring timeouts into the Authorization Code token client

Creating an arbitrary `RestTemplate` is not enough. For Spring Security 6.x supporting `RestTemplate`-based implementations, configure `DefaultAuthorizationCodeTokenResponseClient`:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.http.converter.FormHttpMessageConverter;
import org.springframework.web.client.RestTemplate;

import org.springframework.security.oauth2.client.endpoint
        .DefaultAuthorizationCodeTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint
        .OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint
        .OAuth2AuthorizationCodeGrantRequest;
import org.springframework.security.oauth2.client.http
        .OAuth2ErrorResponseErrorHandler;
import org.springframework.security.oauth2.core.http.converter
        .OAuth2AccessTokenResponseHttpMessageConverter;

@Bean
OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
        authorizationCodeTokenClient(
                ClientHttpRequestFactory providerRequestFactory) {

    RestTemplate rest = new RestTemplate(List.of(
            new FormHttpMessageConverter(),
            new OAuth2AccessTokenResponseHttpMessageConverter()));

    rest.setErrorHandler(new OAuth2ErrorResponseErrorHandler());
    rest.setRequestFactory(providerRequestFactory);

    var client =
            new DefaultAuthorizationCodeTokenResponseClient();
    client.setRestOperations(rest);

    return client;
}
~~~

### 9.1. Keep OAuth2 converters

The token endpoint accepts form POSTs and returns OAuth token JSON containing `access_token`, `token_type`, `expires_in`, and optionally `refresh_token`.

### 9.2. Keep the OAuth error handler

`invalid_grant`, `invalid_client`, and other OAuth errors must be parsed as grant errors rather than collapsing everything into a generic HTTP error.

### 9.3. Wiring into `oauth2Login()`

~~~java
@Bean
SecurityFilterChain portalSecurity(
        HttpSecurity http,
        OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
                tokenClient) throws Exception {

    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/error").permitAll()
                    .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                    .tokenEndpoint(endpoint -> endpoint
                            .accessTokenResponseClient(tokenClient)))
            .build();
}
~~~

Standard imports for `HttpSecurity`, `SecurityFilterChain`, and `@Bean` come from Spring Security/Spring Context.

### 9.4. `RestClient`-based alternative

Newer Spring Security versions include `RestClientAuthorizationCodeTokenResponseClient`. When using that implementation, configure the `RestClient` request factory and OAuth error handling with APIs compatible with your version.

### 9.5. Scope of this wiring

This applies to login authorization-code token exchange; **it does not automatically apply** to refresh tokens, UserInfo, JWKS, or discovery.

## 10. Refresh token clients need separate configuration

~~~java
@Bean
OAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>
        refreshTokenClient(
                ClientHttpRequestFactory providerRequestFactory) {

    RestTemplate rest = new RestTemplate(List.of(
            new FormHttpMessageConverter(),
            new OAuth2AccessTokenResponseHttpMessageConverter()));

    rest.setErrorHandler(new OAuth2ErrorResponseErrorHandler());
    rest.setRequestFactory(providerRequestFactory);

    var client =
            new DefaultRefreshTokenTokenResponseClient();
    client.setRestOperations(rest);
    return client;
}
~~~

Imports for `OAuth2RefreshTokenGrantRequest` and `DefaultRefreshTokenTokenResponseClient` belong to `org.springframework.security.oauth2.client.endpoint`.

### 10.1. Wiring into the authorized client manager

~~~java
@Bean
OAuth2AuthorizedClientManager authorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientRepository repository,
        OAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>
                refreshTokenClient) {

    var provider = OAuth2AuthorizedClientProviderBuilder
            .builder()
            .authorizationCode()
            .refreshToken(config -> config
                    .accessTokenResponseClient(refreshTokenClient))
            .build();

    var manager =
            new DefaultOAuth2AuthorizedClientManager(
                    registrations, repository);

    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

Manager/builder/repository classes come from Spring Security OAuth2 Client packages.

### 10.2. Servlet vs. background

`DefaultOAuth2AuthorizedClientManager` works within a Servlet request context. Scheduled jobs should consider `AuthorizedClientServiceOAuth2AuthorizedClientManager` and a service store.

### 10.3. Never blindly retry refresh POSTs

Refresh tokens may rotate R1 into R2; a response timeout does not prove the AS did not process the request.

## 11. UserInfo has its own HTTP transport

`OidcUserService` can delegate to `DefaultOAuth2UserService` to call UserInfo per flow.

~~~java
@Bean
OidcUserService oidcUserService(
        ClientHttpRequestFactory providerRequestFactory) {

    RestTemplate rest = new RestTemplate();
    rest.setRequestFactory(providerRequestFactory);

    var oauth2UserService = new DefaultOAuth2UserService();
    oauth2UserService.setRestOperations(rest);

    var oidc = new OidcUserService();
    oidc.setOauth2UserService(oauth2UserService);

    return oidc;
}
~~~

Depending on project/version, import from `org.springframework.security.oauth2.client.userinfo` and `org.springframework.security.oauth2.client.oidc.userinfo`.

Wire into login:

~~~java
http.oauth2Login(oauth2 -> oauth2
        .userInfoEndpoint(endpoint -> endpoint
                .oidcUserService(oidcUserService)));
~~~

### 11.1. UserInfo is not always called

This depends on OIDC scopes, claims, OP metadata, and configuration.

### 11.2. Never cut latency by skipping mandatory claims

If the app relies on UserInfo groups for authorization, never assign default roles or memberships when UserInfo times out.

### 11.3. UserInfo carries the access token

Send Bearer tokens only to trusted endpoints. Never read a UserInfo URL from browser queries or automatically follow redirects to untrusted hosts.

### 11.4. Never log UserInfo responses

UserInfo may contain PII. Restrict body logging and retention.

## 12. Discovery metadata and JWKS

With an issuer URI:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company:
            issuer-uri: https://login.example.com
~~~

The framework can fetch metadata to learn authorization/token/JWKS endpoints depending on version and `ClientRegistration` initialization.

### 12.1. Discovery at startup

Many Pods starting simultaneously can fetch metadata together, raising startup latency and provider load.

### 12.2. JWKS caching and signing key rotation

ID token validation requires public signing keys. When a new `kid` appears, the decoder may fetch JWKS. Concurrent cache misses across Pods can create a stampede.

### 12.3. Does not inherit token timeouts by default

Token exchange clients and JWKS decoders may use separate HTTP transports. Identify integration hooks, caches, and timeouts for your exact version.

### 12.4. Fail closed when the ID token cannot be verified

Never skip signature, issuer, or audience validation when JWKS is unavailable.

### 12.5. Prevent SSRF

Never let users submit arbitrary issuer/JWKS URLs for backend discovery. Dynamic tenants must go through a trusted allowlist and approval workflow.

## 13. WebFlux: Reactor Netty connection pool

A `WebClient` using Reactor Netty can be configured as:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

@Bean(destroyMethod = "dispose")
ConnectionProvider oidcConnections() {
    return ConnectionProvider.builder("oidc")
            .maxConnections(40)
            .pendingAcquireMaxCount(100)
            .pendingAcquireTimeout(Duration.ofMillis(500))
            .maxIdleTime(Duration.ofSeconds(30))
            .maxLifeTime(Duration.ofMinutes(5))
            .build();
}

@Bean
WebClient oidcWebClient(ConnectionProvider oidcConnections) {
    HttpClient client = HttpClient.create(oidcConnections)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2000)
            .responseTimeout(Duration.ofSeconds(4));

    return WebClient.builder()
            .clientConnector(
                    new ReactorClientHttpConnector(client))
            .build();
}
~~~

### 13.1. `maxConnections`

Caps the connection count, not necessarily the number of concurrent HTTP/2 streams.

### 13.2. `pendingAcquireMaxCount`

Bounds requests waiting for a connection, preventing unbounded backlogs.

### 13.3. Wiring into Reactive OAuth2 clients

Reactive token clients such as `WebClientReactiveAuthorizationCodeTokenResponseClient` and `WebClientReactiveRefreshTokenTokenResponseClient` must receive the configured `WebClient` per API/version and be wired into `ServerHttpSecurity.oauth2Login()` or `ReactiveOAuth2AuthorizedClientManager`.

**Defining a `WebClient` bean does not automatically make Spring Security OAuth2 flows use it.**

### 13.4. Reactive does not mean zero concurrency limits

Event loops do not block Servlet threads, yet pending Monos, connections, and memory remain finite.

### 13.5. Bound `flatMap` concurrency

~~~java
Flux.fromIterable(tasks)
        .flatMap(task -> invokeProvider(task), 20);
~~~

`invokeProvider` is an application-specific reactive operation. Never use unbounded concurrency when bulk-calling the provider.

### 13.6. Never call `block()` on the event loop

If a token client is blocking, use an appropriate architecture rather than stalling the Reactor event loop.

## 14. Retries: always respect OAuth grant semantics

| Operation | Retry policy |
|---|---|
| Discovery GET | Bounded retry/backoff where appropriate |
| JWKS GET | Bounded retry + caching/throttled refresh |
| UserInfo GET | Consider bounded retry, trusted host only |
| Authorization Code POST | No blind retry when outcome is unknown |
| Refresh Token POST | No blind retry, especially with rotation |
| Client Credentials POST | Bounded retry if AS policy allows |
| Introspection | Per AS/Resource Server contract |
| Revocation | Per AS contract |

### 14.1. Authorization codes are single-use

~~~text
Client sends C1.
AS processes C1, issues tokens, marks code used.
Response is lost.
Client times out.
Client retries C1 -> likely invalid_grant.
~~~

You cannot treat a POST token grant like an idempotent GET retry.

### 14.2. Refresh token rotation

~~~text
Client sends R1.
AS issues A2/R2, invalidates R1.
Response is lost.
Client times out without knowing R2.
Client retries R1 -> invalid_grant or reuse detection.
~~~

Never retry R1 endlessly; reauthorization may be required per policy.

### 14.3. Never retry OAuth logic errors

`invalid_grant`, `invalid_client`, and `unauthorized_client` will not be fixed by exponential backoff.

### 14.4. Even bounded retries need a budget

For GET/discovery calls, enforce max attempts, a total time budget, and jitter to avoid amplifying provider outages.

### 14.5. Watch proxy/service mesh retries

The application may disable retries while a service mesh replays POST token grants. Control network retry policies end-to-end.

## 15. Provider 429s and `Retry-After`

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 3
Content-Type: application/json

{"error":"temporarily_unavailable"}
~~~

### 15.1. Avoid synchronized retries

500 callbacks all waiting exactly 3 seconds and retrying together can create an even larger spike.

### 15.2. Backoff with jitter

Example wait windows for permitted retries:

~~~text
Attempt 1: roughly 200–400ms
Attempt 2: roughly 500–900ms
Attempt 3: roughly 1200–2000ms
~~~

Combine `Retry-After`, total deadlines, and grant safety; this is not a blanket policy for all token requests.

### 15.3. Distinguish retryable from advisable to retry

A read-only GET may be semantically safe yet should still fail fast when the provider is severely overloaded.

### 15.4. Never surface raw provider errors to the browser

Show a generic message and correlation ID; never expose client secrets or token responses.

## 16. Refresh storms and single-flight

Many tokens expiring simultaneously can overload the AS.

### 16.1. Token reuse

`OAuth2AuthorizedClientManager` can reuse an unexpired access token; do not request a new token on every outbound API call.

### 16.2. Clock skew

Refreshing slightly early lowers API 401 risks, provided concurrency is bounded. Never use an expired access token when the OP is unavailable.

### 16.3. Concurrent R1 usage

~~~text
Request A loads A1/R1
Request B loads A1/R1
A refreshes -> A2/R2
B refreshes R1 -> invalid_grant
B failure handler may accidentally delete A2/R2
~~~

### 16.4. Strategies

- Single-flight per principal + registration.
- Distributed locks across multiple instances.
- Optimistic locking/CAS when persisting authorized clients.
- Delete on failure only if the stored version still matches the stale record.
- Bounded concurrent refreshes.
- Reauthorization policy once the AS invalidates R1.

### 16.5. Do not assume the manager is cluster-atomic

Spring Security's manager coordinates grants and storage, while multi-instance concurrency belongs to your architecture and store design.

## 17. Client Credentials and startup load

Background jobs may request tokens simultaneously on deployment:

~~~text
Pod A startup -> client_credentials
Pod B startup -> client_credentials
Pod C startup -> client_credentials
~~~

### 17.1. Use the right manager for non-web flows

`AuthorizedClientServiceOAuth2AuthorizedClientManager` requires no Servlet request and suits background jobs.

### 17.2. Token reuse

Valid unexpired service tokens should be cached per registration/principal/resource policy.

### 17.3. Stagger/jitter

When many Pods boot together, jittering initialization avoids synchronized token requests and JWKS fetches.

### 17.4. Never mix service and user tokens

A `client_credentials` token does not represent an End-User. Never use it to bypass user ownership or tenant rules in APIs.

## 18. Multi-tenant and multiple providers

### 18.1. Per-provider budgets

If tenant Acme uses OP A and Globex uses OP B, a slow OP A must not exhaust pools or worker threads needed by OP B.

### 18.2. Tenant fairness

One tenant surging with logins can consume a shared OP quota. Consider per-tenant rate and concurrency policies.

### 18.3. Issuer trust cannot be bypassed

On timeouts or 429s, never fall back to an unallowlisted issuer.

### 18.4. Token destination isolation

Never send access tokens, refresh tokens, or client secrets to a provider endpoint supplied by the browser.

### 18.5. Pool and cache namespaces

Dynamic registrations and authorized-client stores must prevent collisions across issuers, principals, tenants, and registration IDs.

## 19. Observability: what to measure?

### 19.1. HTTP latencies

Track p50/p95/p99 for:

- Code token exchanges.
- Refresh token exchanges.
- Client Credentials token calls.
- UserInfo.
- JWKS/discovery.
- Callback backend processing.

### 19.2. Pool saturation

- Active connections.
- Idle connections.
- Pending acquire count.
- Connection acquisition timeouts.
- Connect/response timeout rates.
- Evictions/leaks.
- Per-route usage.

### 19.3. Error categories

~~~text
provider_alias=company-op
registration_id=company
operation=refresh_token
result=failed
category=response_timeout
duration_ms=4080
correlation_id=...
~~~

### 19.4. Do not lump errors together

`access_denied` from consent/policy differs from `invalid_grant`; HTTP 503/429 differs from network timeouts. Classify them clearly in metrics and alerts.

### 19.5. Token request ratios

- Token endpoint calls per login.
- Access-token reuse rate.
- Refresh attempts/success rate.
- `invalid_grant` frequency.
- Circuit breaker open rate.
- Rate limiter rejections.
- Retries per grant.

### 19.6. Protect metric data

Never put raw `sub`, email, `state`, authorization codes, or tokens in metric labels; avoid cardinality explosions and privacy leaks.

## 20. Safe logging and tracing

Minimal log:

~~~text
event=oidc_token_exchange
registration_id=corporate
grant=authorization_code
result=failed
error_category=pool_acquire_timeout
duration_ms=501
trace_id=...
~~~

Never log:

~~~text
authorization_code
code_verifier
client_secret
access_token
refresh_token
id_token
raw Authorization header
raw session cookie
full callback query string
~~~

### 20.1. HTTP wire logs are especially dangerous

Token POSTs carry secrets in form bodies and headers. Enforce redaction, strict access control, and tight retention.

### 20.2. Correlation IDs differ from OAuth state

Never use raw `state` for public tracing, as `state` is a security token tied to login correlation.

### 20.3. Phase-level tracing

Separate pool wait time, token HTTP calls, UserInfo, and JWKS when instrumentation supports it.

## 21. Fail closed when the provider is unavailable

### 21.1. Unauthenticated users

If the callback token exchange fails or the ID token cannot be verified, never create a successful Authentication or session.

### 21.2. Users with an existing valid session

Features not requiring provider calls may continue per session/authorization policy, but never honor revoked permissions or arbitrarily use expired tokens.

### 21.3. When refresh fails

If the access token expired and R1 cannot refresh, downstream API calls must fail or trigger reauthorization. Never send expired tokens and skip API checks.

### 21.4. When UserInfo fails

If roles/permissions depend on UserInfo, never elevate roles when data is missing.

### 21.5. When JWKS fails

Never bypass JWT signature or issuer validation. Fail closed.

### 21.6. When the circuit breaker is open

Inform users the OP is temporarily unavailable; never redirect into an infinite login loop.

## 22. Proxies, ingress, service mesh, and TLS

A deployment path may traverse:

~~~text
Browser -> Ingress -> Portal -> Mesh/Proxy -> OP
~~~

### 22.1. Align timeouts

An ingress timeout of 5 seconds paired with a token response timeout of 30 seconds wastes server resources long after the browser gave up.

### 22.2. Proxy retries

Never let a service mesh automatically retry code/refresh HTTP POSTs with unknown outcomes.

### 22.3. DNS/TLS

Connection failures may stem from DNS, truststores, expired certificates, SNI, or proxies. Never disable hostname or certificate verification to mitigate an outage.

### 22.4. Connection pools behind a proxy

Per-route limits may apply per proxy route rather than per logical OP host. Measure actual transport behavior.

## 23. Testing timeouts with a fake OP

A fake OP in tests can expose:

~~~text
GET  /.well-known/openid-configuration
GET  /jwks
POST /token
GET  /userinfo
~~~

### 23.1. Slower than response timeout

~~~text
Configured response timeout = 500ms
Fake OP token delay = 2s
Expected:
  request fails within bounded budget
  no successful OIDC Authentication
  no authorized client newly saved
  no blind retry of code/refresh POST
~~~

### 23.2. Pool acquire exhaustion

~~~text
max connections = 2
acquire timeout = 200ms
fake OP holds two token requests for 2s
third request must fail/wait bounded
~~~

Assert active/pending metrics and post-test cleanup, not just HTTP status codes.

### 23.3. 429

Have the fake OP return `429` with `Retry-After`. Verify classification/backoff if the operation permits retries and ensure total attempts stay within budget.

### 23.4. JWKS 503

Never accept an unverified ID token when the required public key is unavailable.

### 23.5. UserInfo timeout

Verify behavior matches your authentication and optional-claims policy.

### 23.6. Lost rotation response

Have the fake AS rotate R1 to R2 but intentionally drop the response. Verify the application does not keep sending R1 endlessly.

### 23.7. Recovery

After an outage, verify active/pending pool counts normalize, circuit breakers go half-open then closed per policy, and zero connections leak.

## 24. Testing token reuse to reduce load

Given a saved authorized client:

~~~text
registration = corporate
principal = alice
access_token = A1
expires_at = 11:00
now = 10:00

100 sequential manager.authorize() calls
Expected:
  A1 reused
  refresh-token HTTP calls = 0
~~~

### 24.1. Fixed-clock tests

Use `Clock.fixed(...)` to avoid flaky tests near expiry boundaries.

### 24.2. Assert token endpoint HTTP call count

Do not confuse manager/provider invocations with HTTP requests. Token endpoint calls should occur only when refresh is actually needed.

### 24.3. Verify A2/R2 persistence

When the fake AS refreshes R1 into A2/R2, assert both the manager return value **and a fresh load from the authorized client store** contain the new tokens.

### 24.4. Concurrency

Use threads and latches to simulate two requests concurrently using R1. Verify single-flight/versioning/CAS never loses R2.

## 25. Runbook for slow logins

### Step 1: Identify the phase

Is the user stuck on the OP login page or back at the Portal callback?

### Step 2: Check p95/p99 by endpoint

Is the Token Endpoint, JWKS, UserInfo, or discovery slow?

### Step 3: Check pool saturation

Are active/pending counts and acquire timeouts rising?

### Step 4: Check 429/5xx

Is there provider rate limiting, a deployment, or an autoscale spike?

### Step 5: Classify the grant

Authorization Code, Refresh Token, or Client Credentials? Are unsafe retries happening?

### Step 6: Inspect proxy/mesh

Ingress timeouts, service mesh retries, DNS/TLS trust.

### Step 7: Reproduce in staging

Use a delayed/429/503 fake OP. Never stress-test a production OP without explicit approval.

### Step 8: Tune one variable at a time

Never raise pool sizes, timeouts, and retries simultaneously: it amplifies overload and obscures root causes.

## 26. Troubleshooting

| Symptom | Common cause | What to check |
|---|---|---|
| Slow token exchange | OP latency/capacity | Endpoint p99/429 |
| Pool pending queue grows | Exhausted connections | Active/idle/leaks |
| Connect timeout | Network, DNS, proxy | Egress/TLS |
| Read timeout | Slow OP processing | Response metrics |
| Refresh on every request | Token cache/store not reusing | Manager/provider |
| Refresh `invalid_grant` after timeout | Rotation race/unknown outcome | Single-flight/CAS |
| JWKS fetch storm | Key rotation/cache miss | Decoder cache |
| Slow UserInfo | Different HTTP client timeout | UserInfo service wiring |
| New Pods fail login | Discovery startup load | Rolling rollout |
| OP 429 after autoscale | Cluster quota exceeded | Global rate limits |
| API 403 yet app refreshes | Owner/scope denial | Never retry 403 |
| WebFlux pending memory grows | Unbounded concurrency | `ConnectionProvider`/`flatMap` |
| Login redirect loop | Broken failure handler retry | Controlled UX |
| Duplicate code POST | Proxy/client retry | Disable unsafe retries |
| Timeout config has no effect | HTTP client not wired properly | Fake OP test |
| Tokens in logs | Wire logging enabled | Redaction |

## 27. Common misconceptions

**“Connect timeout is the total HTTP timeout.”** No—there are also pool acquire, TLS, response/read, and overall deadlines.

**“Bigger pools are always better.”** No. They can overload the OP further.

**“One RestTemplate timeout automatically covers every Spring Security HTTP call.”** No. You must wire each integration point.

**“Authorization endpoint redirects use the backend token pool.”** No; browsers call the OP authorization endpoint directly.

**“If a token POST times out, just retry.”** No. Single-use authorization codes and rotating refresh tokens leave unknown outcomes.

**“On R1 timeout, you can always retry R1.”** No. The AS may have already rotated R1 to R2.

**“If JWKS fails, skip signature verification temporarily.”** No. Fail closed.

**“WebFlux needs no pools or queues.”** No. Resources are still finite.

**“429 with Retry-After means retry every grant.”** No—respect grant semantics and retry budgets.

**“Pool size 50 means 50 connections across the cluster.”** No; each Pod owns its own pool.

## 28. Practical scenarios

### A. 2,000 callbacks at shift start

The provider receives a burst of token exchanges.

**Analysis:** measure OP p99, pool saturation, cluster concurrency, and quotas; enforce bulkheads and bounded queues.

### B. Unexpired token keeps refreshing

**Analysis:** inspect `OAuth2AuthorizedClientManager`/store and token reuse.

### C. R1 times out then returns `invalid_grant`

**Analysis:** the AS likely rotated it; do not retry blindly, design reauthorization.

### D. Signing key rotation

**Analysis:** watch for cache/JWKS fetch stampedes; keep signature verification enabled.

### E. UserInfo slow despite low token client timeout

**Analysis:** configure the UserInfo HTTP client separately.

### F. Tenant A exhausts the entire quota

**Analysis:** enforce per-tenant rate and concurrency fairness.

### G. Service mesh retries POST

**Analysis:** mesh policies can duplicate grant requests.

### H. WebFlux memory grows

**Analysis:** bound pool acquisition, concurrency, and cancellation.

### I. Token endpoint 429 after scale-out

**Analysis:** compute total cluster quota, add jitter/RateLimiter.

### J. Ingress times out before backend

**Analysis:** align deadlines; avoid holding Servlet threads too long.

## 29. Self-check questions

**1. Is the authorization endpoint called by the browser or backend?** Usually the browser via redirect.

**2. When is the token endpoint called?** Code exchange, refresh, or other grants.

**3. Does connect timeout bound the entire request?** No.

**4. What is pool acquire timeout?** Limit waiting for a free connection.

**5. Why bound the pending queue?** Prevent unbounded backlog, thread, and memory growth.

**6. Can increasing pool size raise 429s?** Yes.

**7. Why calculate cluster-wide quotas?** Because each replica maintains its own pool.

**8. Must an unexpired token refresh on every request?** No.

**9. Should code grant POSTs be blindly retried?** No.

**10. Could a timed-out R1 have already been rotated by the AS?** Yes.

**11. Can signature validation be skipped when JWKS is unavailable?** No.

**12. Does a single RestTemplate bean apply to all OAuth calls automatically?** No.

**13. Does WebFlux need a bounded ConnectionProvider?** Yes.

**14. How should HTTP 429s be handled?** Reduce load, apply bounded backoff/jitter per operation.

**15. Are `invalid_grant` and response timeout the same?** No.

**16. Which metrics show pool saturation?** Active/pending connections and acquire timeouts.

**17. Should refresh tokens be logged for debugging?** No.

**18. Does UserInfo inherit timeouts from the token client automatically?** Not necessarily; wire separately.

**19. Which manager suits non-web jobs?** Typically `AuthorizedClientServiceOAuth2AuthorizedClientManager`.

**20. May an OP outage create an unverified OIDC session?** No.

## Key takeaways

- **An OAuth2/OIDC Client calls multiple endpoints**: token, refresh, UserInfo, JWKS, and discovery; browser authorization redirects are separate.
- **Pool acquire, connect, response/read, and overall deadlines are distinct limits** that must reflect real SLOs.
- **Connection pools require max total/per-route, bounded pending queues, idle/lifetime policies**, and cluster-wide quota budgeting.
- **Timeout-configured HTTP clients must be wired explicitly into Spring Security token, refresh, UserInfo, and JWKS/discovery components**—creating a bean alone is not enough.
- **Never blindly retry authorization code or rotating refresh token POSTs** after timeouts; the AS may have already consumed the code or rotated R1 to R2.
- **Rate limiting, bulkheads, circuit breakers, jitter, and load shedding work together** without disabling OAuth/OIDC validation.
- **Token reuse, single-flight refreshes, JWKS caching, and staggered rollouts reduce provider load** without permitting expired or unverified tokens.
- **WebFlux also needs bounded pools and concurrency**, even though it is non-blocking unlike Servlet.
- **Metrics must track p95/p99, pool saturation, 429/5xx, refresh errors, and request counts** without logging credentials.
- **Fake OP and load tests must verify timeout enforcement, fail-closed behavior, and recovery** without stress-testing production OPs casually.
