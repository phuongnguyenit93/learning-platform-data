# 19.9. Integrating Timeouts, Retries, and Downstream Response Analysis

## 1. The Problem: OIDC Login Succeeds, Yet API Calls Are Slow, Failing, or Returning Unexpected Data

An **Employee Portal** application runs **Spring Boot 3, Spring Security OAuth 2.0/OIDC Client, and Spring MVC/Servlet**. Users sign in with corporate accounts via OIDC. Afterward, the backend uses **WebClient** to call the **Orders API** on behalf of the user with an access token:

~~~text
Browser
  |
  | GET /bff/orders (JSESSIONID, Portal's HTTP session)
  v
Employee Portal (Spring MVC / Servlet)
  |
  | WebClient + Servlet OAuth2 Client filter
  | Authorization: Bearer <access-token>
  v
Orders API (Resource Server)
  |
  +-- 200 OK: list of orders
  +-- 401 invalid_token: invalid access token
  +-- 403 insufficient_scope: missing permissions
  +-- 429 Too Many Requests: rate limit
  +-- 502/503/504: infrastructure errors
  +-- slow connection, timeout, or schema mismatch response
~~~

If you only write:

~~~java
return webClient.get()
    .uri("/api/orders")
    .retrieve()
    .bodyToMono(String.class);
~~~

many questions remain unanswered:

- If a TCP connection cannot be established, how long does the application wait?
- If the server accepts the request but sends no response, which wait limit applies?
- Is the timeout per **single attempt** or across all **retries**?
- Should an HTTP POST creating an order be retried, or only read-only GETs?
- Does HTTP 401 mean the Portal session expired or the access token sent to the Resource Server was rejected?
- Can HTTP 403 be fixed by refreshing the token?
- HTTP 429 includes a `Retry-After` header; how should the application handle it?
- How do you inspect downstream **status, headers, and body** without leaking tokens or swallowing the response body?
- If using WebClient inside a **Servlet** application, must all security be switched to WebFlux?

**Lesson goal:** establish how to use **WebClient on Servlet** with explicit timeouts, bounded retries, and accurate downstream response analysis policies, while preserving the boundaries between OAuth2 tokens, login sessions, and Resource Server authorization.

> Example environment: Java 17+, Spring Boot 3, Spring Security 6, Spring MVC, and Spring WebFlux's WebClient. Domains, client IDs, error codes, and tokens are all illustrative. Some APIs vary by exact version; keep dependencies aligned with your project's Spring Boot BOM.

## 2. WebClient on Servlet: Understanding the Execution Model

**Spring MVC** runs on a Servlet container and typically processes controllers on worker threads. **WebClient** is an HTTP client with a Reactive API, usually built on Reactor Netty for non-blocking I/O, yet it can be used inside a **Servlet application**.

| Aspect | Spring MVC + WebClient | Spring WebFlux Application |
|---|---|---|
| Web server request stack | Servlet API, `HttpServletRequest` | Reactive `ServerWebExchange` |
| Security chain | `SecurityFilterChain` / `HttpSecurity` | `SecurityWebFilterChain` / `ServerHttpSecurity` |
| OAuth2 Client manager | `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| WebClient OAuth2 filter | `ServletOAuth2AuthorizedClientExchangeFilterFunction` | `ServerOAuth2AuthorizedClientExchangeFilterFunction` |
| HTTP client response type | `Mono<T>` or `Flux<T>` from WebClient | Same |
| Coordination model | Can return a Publisher via MVC async or block at an appropriate blocking boundary | Never block a Reactor event-loop |

**Adding WebClient does not automatically turn the Portal into WebFlux.** When Spring Boot has both `spring-boot-starter-web` and `spring-webflux` on the classpath, the application normally continues using MVC unless configured for another web application type.

### 2.1. Why Is WebClient Useful with Servlet?

- Network calls are modeled via `Mono`, making it clean to compose timeouts, retries, and error mapping.
- Reactor Netty connection pools, SSL, and HTTP response timeouts can be configured.
- Controllers can return `Mono<T>` to leverage Spring MVC's async support, avoiding blocking a Servlet thread for the entire API call duration when properly configured.
- Useful when fanning out across multiple downstream services, provided total concurrency, memory, and timeouts are controlled.

WebClient **does not eliminate** the need to manage threads, connection pools, backpressure, or security. If a controller calls `.block()`, the Servlet thread still waits. `.block()` can be used at an intentionally designed blocking boundary in an MVC app, yet must never appear on a Reactor event loop or be overused to the point of thread starvation.

## 3. Proper Architecture: OAuth2 Filter, Timeouts, Retries, and Response Handling

~~~mermaid
flowchart TD
    U["Browser calls /bff/orders"] --> S["Spring MVC SecurityContext / OIDC principal"]
    S --> C["OrdersGateway using WebClient"]
    C --> F["ServletOAuth2AuthorizedClientExchangeFilterFunction"]
    F --> M["OAuth2AuthorizedClientManager"]
    M --> AR["Authorized Client Repository/Service"]
    M --> AS["Authorization Server token endpoint when refresh needed"]
    F --> H["HTTP connector / Reactor Netty"]
    H --> API["Orders API"]
    API --> R{"Downstream response"}
    R -->|2xx| D["Decode data / headers"]
    R -->|401 Bearer invalid_token| I["OAuth2 failure handling, avoid reusing old token"]
    R -->|403| A["Report insufficient permissions"]
    R -->|429, 502, 503, 504| T["Conditional retry / backoff"]
    R -->|Other 4xx| B["Handle business error"]
    H -->|Network timeout| X["Timeout / cancellation / retry policy"]
~~~

For clarity, divide the design into four layers:

1. **Security/OAuth2 layer:** acquire tokens for trusted registrations and principals; handle invalid tokens in the right place.
2. **Transport layer:** DNS, connect timeout, response timeout, TLS, connection pool.
3. **Resilience layer:** selective retries, backoff, jitter, total wait budget, and concurrency limits.
4. **Application layer:** interpret downstream status/headers/body and translate them into appropriate Portal results or errors.

If you merely attach retries at the end of the pipeline without knowing which layer failed, the application can easily retry an **unrecoverable** error such as 403 insufficient scope, or replay a side-effecting POST.

## 4. Sample Dependencies and OAuth2 Client Configuration

### 4.1. Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    // WebClient API and required WebFlux components.
    implementation 'org.springframework:spring-webflux'

    // Or use starter-webflux if you want Boot to manage the full
    // reactor-netty client + WebClient support; no need to add both.
    implementation 'org.springframework.boot:spring-boot-starter-reactor-netty'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

In projects using `spring-boot-starter-webflux`, that starter already pulls in the required WebClient/HTTP client dependencies under Boot management, so **do not add** standalone WebFlux/Netty dependencies simultaneously unless managing specific versions. The example above illustrates using WebClient **in MVC** without changing the application type.

### 4.2. OIDC Registration

~~~yaml
# src/main/resources/application.yml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}

server:
  servlet:
    session:
      timeout: 30m
~~~

`session.timeout` is the web session timeout; it is **not** the Orders API network timeout or access token lifetime. `OIDC_CLIENT_SECRET` must be injected via a secret manager/runtime environment and never stored in source code or sent to the frontend.

### 4.3. SecurityFilterChain on Servlet

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

`oauth2Login()` handles OIDC login. `oauth2Client()` supports OAuth2 Client authorization. Enabling those two DSLs does not automatically attach Bearer tokens to every WebClient: you must configure the **OAuth2 exchange filter** on the appropriate WebClient.

## 5. Configuring WebClient HTTP Transport with Reactor Netty

Several distinct limits are loosely called “timeouts”. Distinguish them clearly.

| Limit Type | When It Starts Counting | Problem Solved |
|---|---|---|
| **Connection acquisition timeout** | Waiting for a connection from the pool | Pool exhausted, requests queued too long |
| **TCP connect timeout** | Establishing a TCP connection to host | Unresponsive host, unreachable network |
| **TLS handshake timeout** | Performing the TLS handshake | Unresponsive or broken TLS server/proxy |
| **Response/read timeout** | Waiting for downstream data per HTTP connector policy | Slow server processing or stalled response |
| **Per-attempt reactive timeout** | One subscribed attempt of the pipeline | Caps a single call according to pipeline semantics |
| **Overall timeout/deadline** | End-to-end across pipeline including retries | Prevents total retries from exceeding SLA |
| **HTTP session timeout** | Servlet login session idle duration | Controls login lifecycle, unrelated to Orders API latency |

### 5.1. WebClient Transport Beans

~~~java
package com.example.portal.config;

import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
public class OrdersTransportConfig {

    @Bean("ordersHttpClient")
    HttpClient ordersHttpClient() {
        ConnectionProvider pool = ConnectionProvider.builder("orders-pool")
            .maxConnections(100)
            .pendingAcquireTimeout(Duration.ofSeconds(1))
            .build();

        return HttpClient.create(pool)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
            .responseTimeout(Duration.ofSeconds(5));
    }

    @Bean("ordersBaseWebClient")
    WebClient ordersBaseWebClient(HttpClient ordersHttpClient) {
        return WebClient.builder()
            .baseUrl("https://orders.example.test")
            .clientConnector(
                new ReactorClientHttpConnector(ordersHttpClient)
            )
            .build();
    }
}
~~~

Numbers like **2 seconds, 5 seconds, 100 connections** are purely illustrative; in production, measure latency, load, pool contention, and SLOs before choosing values. Never pick arbitrary numbers for live systems.

**Resource management note:** if you create a custom `ConnectionProvider`, manage its lifecycle and dispose of the connection pool on application shutdown per configuration policy. In typical Spring Boot applications, leveraging `WebClient.Builder`, Reactor Netty resource management, and HTTP client auto-configuration avoids creating unnecessary separate pools.

### 5.2. Response Timeout Is Not the Whole Business Operation Limit

`HttpClient.responseTimeout(...)` applies at HTTP transport for response/read wait per Reactor Netty semantics, yet does not necessarily cover every step:

- Waiting to acquire a connection from the pool.
- Token issuance/refresh via the OAuth2 manager.
- Retry backoff delays between attempts.
- JSON parsing and business processing.

If the requirement is **“the entire request to Orders API must finish within a deadline”**, set an **overall timeout** at the pipeline or orchestration layer.

### 5.3. TLS and Proxies

A WebClient carrying OAuth2 Bearer tokens **must** call only trusted HTTPS endpoints. When an enterprise uses an egress proxy:

- Configure the proxy on the corresponding HTTP connector.
- Configure the right truststore/CA and never disable certificate/hostname verification.
- With mTLS, ensure keystores and client certificates are protected.
- Prevent proxies from logging `Authorization: Bearer`, client secrets, refresh tokens, or sensitive bodies.

If a downstream server redirects to a different hostname, enforce a policy **never to forward Bearer tokens to hosts outside the allowlist**. Never pass user-supplied absolute URLs into a WebClient configured to attach tokens automatically.

## 6. Timeouts in the Reactor Pipeline: Per-Attempt and Overall

Reactor provides the `timeout(Duration)` operator:

~~~java
Mono<String> result = ordersWebClient.get()
    .uri("/api/orders")
    .retrieve()
    .bodyToMono(String.class)
    .timeout(Duration.ofSeconds(6));
~~~

This caps the **`Mono` from subscription until signal emission as defined by the operator**. On timeout, Reactor emits `TimeoutException` and cancels the upstream subscription when possible.

**Cancellation does not mean the downstream server did not process the request.** If the request already reached the server, effects or mutations may still occur; this matters critically for write operations.

### 6.1. Timeout Per Attempt

~~~java
Mono<String> callOnce() {
    return ordersWebClient.get()
        .uri("/api/orders")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(3));
}
~~~

When `timeout` is placed **before** `retryWhen`, each retry re-subscribing upstream receives a fresh timeout window.

### 6.2. Overall Deadline Across All Retries

~~~java
Mono<String> result = callOnce()
    .retryWhen(retryPolicy)
    .timeout(Duration.ofSeconds(8));
~~~

`timeout(Duration.ofSeconds(8))` **after retry** bounds the entire subscription including attempts and backoff delays. This is an application-level deadline, not a TCP-level connection timeout.

If the total wait budget is shorter than 3 attempts plus backoff, the overall timeout cuts off the pipeline before the full retry policy finishes. That is **correct** when business requirements prioritize a strict latency bound.

### 6.3. Controlling the Timeout Budget

Example:

~~~text
SLO of /bff/orders: 1.5 seconds at target percentile
Network/connect budget: a few hundred ms
Downstream response budget: under 1 second
Retry budget: only if remaining time allows
Overall deadline: shorter than upstream gateway timeout
~~~

Exact numbers must be based on measurement. A classic design mistake is configuring:

~~~text
Gateway timeout        = 5 seconds
Portal overall timeout = 30 seconds
3 retries x 10 seconds = can outlive the browser having already disconnected
~~~

Once the gateway closes the connection, the Portal wastes load continuing retries. Align deadlines across all layers together.

## 7. Retries: Not Every Error Should Be Retried

Retrying means **re-sending an operation** after failure. An HTTP request may have already reached the server and caused side effects **before** the Portal timed out. Always evaluate retries against:

1. **HTTP method and business idempotency.**
2. **Error code/exception type**: transient error vs. configuration/permission error.
3. **Attempt count and time budget limits.**
4. **Backoff, jitter, and `Retry-After`.**
5. **Concurrent load** on both Portal and downstream.
6. **Whether the request body can be replayed safely.**
7. **Token, authorization, and user state.**

### 7.1. Retry Decision Matrix

| Scenario | Auto-Retry? | Explanation |
|---|---|---|
| GET returns 502/503/504 | **Yes**, bounded | Usually transient infrastructure failures |
| GET returns 429 | **Yes**, respecting rate limits/`Retry-After` | Must avoid aggravating overload |
| GET hits connect timeout | **Yes**, bounded | If request is safe and deadline remains |
| GET hits response timeout | **Consider carefully** | Server may have processed it; true read-only GETs are lower risk |
| 401 Bearer `invalid_token` | **Do not retry blindly** | Requires OAuth2 authorized client/token lifecycle handling |
| 403 `insufficient_scope` | **No** | Retrying will not grant new permissions |
| 400 validation error | **No** | Invalid request payload needs fixing |
| 404 resource not found | **Usually no** | Depends on consistency contracts, not transient by default |
| 409 conflict | **Depends on business** | Never retry unconditionally; may need version resolution |
| 500 | **Depends on API** | May be transient, not guaranteed; check contract and limits |
| POST creating an order | **No by default** | Risks creating duplicate orders |
| POST with server-backed idempotency key | **Possible** | Only when the API guarantees deduplication per contract |

**HTTP method is only a hint.** A non-standard GET endpoint that mutates state is still risky; a POST with a server-verified idempotency key can be safe to retry. Decide based on actual API semantics.

## 8. `retryWhen` with Backoff, Jitter, and Attempt Limits

For read-only APIs, you can selectively retry certain 502/503/504 errors. Example:

~~~java
package com.example.portal.downstream;

import java.time.Duration;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

@Service
public class OrdersReadGateway {

    private final WebClient ordersWebClient;

    public OrdersReadGateway(WebClient ordersWebClient) {
        this.ordersWebClient = ordersWebClient;
    }

    public Mono<String> listOrders() {
        Retry retryPolicy = Retry.backoff(
                2,
                Duration.ofMillis(200)
            )
            .maxBackoff(Duration.ofSeconds(1))
            .jitter(0.3)
            .filter(this::isRetryable)
            .onRetryExhaustedThrow((spec, signal) -> signal.failure());

        return ordersWebClient.get()
            .uri("/api/orders")
            .retrieve()
            .bodyToMono(String.class)
            .timeout(Duration.ofSeconds(2))
            .retryWhen(retryPolicy)
            .timeout(Duration.ofSeconds(6));
    }

    private boolean isRetryable(Throwable error) {
        if (error instanceof WebClientResponseException response) {
            int code = response.getStatusCode().value();
            return code == 502 || code == 503 || code == 504;
        }
        return error instanceof java.util.concurrent.TimeoutException;
    }
}
~~~

**Important notes:**

- `Retry.backoff(2, ...)` allows **at most two retries after the initial attempt**, i.e., **three total attempts**.
- `.filter(...)` restricts which errors are retried; it does **not** retry 401/403/400.
- `.jitter(0.3)` randomizes wait intervals to reduce “thundering herds”.
- `timeout(2s)` before retry caps each attempt in the Reactor pipeline.
- `timeout(6s)` after retry sets an overall deadline across attempts and backoffs.
- `.onRetryExhaustedThrow(...)` preserves the final failure for the caller to analyze rather than wrapping it in a generic “retry exhausted” error.

This example is **for safe GETs only**. If the client calls other APIs or uses a shared WebClient, scope retries per operation rather than attaching a global retry filter for all methods on the builder.

### 8.1. Timeouts Can Occur After Token Refresh

When WebClient has the Servlet OAuth2 filter, a single attempt may include:

~~~text
Read Authentication/registration
 -> manager retrieves authorized client
 -> possible refresh at Authorization Server
 -> connect to Orders API
 -> receive/parse response
~~~

Where `timeout()` sits determines which part of the pipeline it bounds. If a timeout occurs during the OAuth2 manager stage, retrying the whole pipeline may **repeat a token authorization attempt** rather than just retrying the Orders API call.

That is why you must **classify errors** and bound retries—never put every `Throwable` into a blanket retry list.

### 8.2. Never Enable Unconditional Global Retries on WebClient

Dangerous example:

~~~java
// Never attach unconditionally to every request:
return next.exchange(request)
    .retryWhen(Retry.fixedDelay(10, Duration.ofMillis(50)));
~~~

It may retry:

- 401 due to invalid tokens.
- 403 due to missing permissions.
- Payment or order-creation POSTs.
- Payload decoding failures after receiving a response.
- 500s where downstream already committed side effects.

Apply retries at an **operation-specific boundary** with clear business policies and attempt limits.

## 9. HTTP 429 and `Retry-After`

A downstream API may return:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 3
Content-Type: application/json

{"error":"rate_limited"}
~~~

Or:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: Mon, 16 Nov 2026 03:00:00 GMT
~~~

`Retry-After` can be **delay seconds** or an **HTTP-date**; it is not always an integer.

A sound design:

1. Check whether 429 is a downstream rate limit the client is allowed to retry.
2. Read `Retry-After` if present and parse it per HTTP specification.
3. Enforce a **maximum wait cap** and the Portal's **overall deadline**.
4. If `Retry-After` exceeds the remaining budget, **do not hold the request waiting indefinitely**; return a handleable error to the caller.
5. Consider rate limiters/bulkheads/circuit breakers to keep multiple requests from piling up retries.
6. Never use retries to try to bypass rate limits or quotas.

### 9.1. When Not to Wait for `Retry-After`

Example:

~~~text
Portal request budget: 5 seconds
Downstream Retry-After: 120 seconds
~~~

Do not hold a WebClient `Mono` and Servlet async request open for 120 seconds hoping `Retry-After` passes. Instead:

- Return a standardized “temporarily unavailable” error code.
- Offload the work to a queue if the business permits and idempotency exists.
- Let the frontend retry after an appropriate interval per the API contract.

Never forward an internal API's raw `Retry-After` directly to the frontend if it reveals internal quota details; forward only what Portal policy permits.

## 10. HTTP POST and Idempotency Keys

Suppose the Portal sends:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Authorization: Bearer <token>

{"sku":"SKU-123","quantity":1}
~~~

The Orders API created the order, yet the network failed before the response reached the Portal. Retrying the same request automatically can create **two orders**.

One mechanism to reduce risk is an **idempotency key genuinely supported by the Orders API**:

~~~http
POST /api/orders HTTP/1.1
Idempotency-Key: 45d676e5-9895-4f59-9d9f-75f48bbc4174
Content-Type: application/json
Authorization: Bearer <token>

{"sku":"SKU-123","quantity":1}
~~~

Safety requirements:

- The key must be generated for **one specific business intent**, never regenerated on each retry.
- Downstream must commit to deduplicating the same key, validating payload/tenant/user bindings, and retaining keys for a defined window.
- The client reuses the same key across all retry attempts for that operation.
- On ambiguous outcomes, the app can query an order-status endpoint instead of re-POSTing.
- Never assume simply adding the header makes a request idempotent when downstream does not support it.

**GET retry policies must never be copied verbatim to POST/PATCH/DELETE.**

## 11. Analyzing Responses with `retrieve()`

`retrieve()` is a concise way to read bodies and map HTTP errors. By default, 4xx/5xx responses are converted into `WebClientResponseException` when calling `bodyToMono(...)`.

~~~java
Mono<OrdersPage> result = ordersWebClient.get()
    .uri("/api/orders")
    .retrieve()
    .bodyToMono(OrdersPage.class);
~~~

Here `OrdersPage` is an application-defined DTO, not a Spring Security class. HTTP 200 decodes into the DTO; HTTP errors become error signals by default.

### 11.1. Mapping Status Codes with `onStatus`

~~~java
import org.springframework.http.HttpStatusCode;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

Mono<OrdersPage> orders = ordersWebClient.get()
    .uri("/api/orders")
    .retrieve()
    .onStatus(
        status -> status.value() == 429,
        response -> response.createException()
            .map(error -> new DownstreamRateLimitedException(
                "Orders API rate limit exceeded"))
    )
    .onStatus(
        HttpStatusCode::is5xxServerError,
        response -> response.createException()
            .map(error -> new DownstreamUnavailableException(
                "Orders API temporarily unavailable"))
    )
    .bodyToMono(OrdersPage.class);
~~~

`DownstreamRateLimitedException` and `DownstreamUnavailableException` are **application-specific exceptions** you define yourself; this example illustrates mapping. `response.createException()` **consumes the response body** to build an exception containing status/headers/body, after which this example creates a domain exception without raw body contents to avoid leaking details.

**Consequence:** once mapped to custom exceptions, a retry filter checking `WebClientResponseException` by HTTP status will **no longer see that type** downstream unless you preserve status/cause in your custom exception or adapt the retry filter to match the application-specific exceptions.

That is why **operator ordering for error mapping and retries** must be designed together.

### 11.2. Do Not Return `Mono.empty()` from `onStatus` to Turn 404 into Null

In `retrieve().onStatus(...)`, returning `Mono.empty()` from a status handler means **do not treat that status as an error at this step**, so the response continues to the body decoder. It does **not turn HTTP 404 into a business-level `Mono.empty()`**.

If 404 should mean “resource not found” without decoding a body, use `exchangeToMono()` or controlled downstream exception mapping.

## 12. Inspecting Status, Headers, and Body with `toEntity()`

When you need **status + response headers + decoded body**, `retrieve().toEntity(...)` is useful:

~~~java
import org.springframework.http.ResponseEntity;
import reactor.core.publisher.Mono;

Mono<ResponseEntity<OrdersPage>> response =
    ordersWebClient.get()
        .uri("/api/orders")
        .retrieve()
        .toEntity(OrdersPage.class);
~~~

Example:

~~~java
return response.map(entity -> {
    String etag = entity.getHeaders().getETag();
    int code = entity.getStatusCode().value();
    OrdersPage page = entity.getBody();
    return new OrdersResult(code, etag, page);
});
~~~

`OrdersResult` is an application-defined DTO. `toEntity(...)` lets you read headers such as `ETag` or upstream correlation IDs.

**Note:** `retrieve()` still turns most 4xx/5xx responses into exceptions by default; `toEntity(...)` does not automatically return `ResponseEntity` for errors without `onStatus` or another strategy.

### 12.1. ETag and Conditional Requests

If downstream supports ETags, the Portal can send `If-None-Match` on GETs to reduce payload transfer:

~~~http
GET /api/orders HTTP/1.1
If-None-Match: "orders-v12"
Authorization: Bearer <token>
~~~

When the server returns `304 Not Modified`, the application must hold a corresponding cached response body protected by **principal/tenant/authorization context**—never serve another user's cached data just because the ETag matches.

Caching tokens, responses, and authorizations carry distinct risks; this optimizes downstream HTTP traffic and does not replace the OAuth2 authorized client manager.

## 13. `exchangeToMono()`: When Explicit Control Over Each Status Is Needed

`exchangeToMono()` lets the application inspect `ClientResponse` and decide how to read the body per status.

Example GET for order details:

~~~java
package com.example.portal.downstream;

import org.springframework.http.HttpStatusCode;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public class OrderLookupGateway {

    private final WebClient client;

    public OrderLookupGateway(WebClient client) {
        this.client = client;
    }

    public Mono<OrderDto> findOrder(String id) {
        return client.get()
            .uri("/api/orders/{id}", id)
            .exchangeToMono(response -> {
                HttpStatusCode status = response.statusCode();

                if (status.is2xxSuccessful()) {
                    return response.bodyToMono(OrderDto.class);
                }

                if (status.value() == 404) {
                    // No matching order; release response body.
                    return response.releaseBody()
                        .then(Mono.<OrderDto>empty());
                }

                // Create exception with status/headers and bounded body
                // per codec config, then propagate error signal.
                return response.createException()
                    .flatMap(error -> Mono.<OrderDto>error(error));
            });
    }
}
~~~

`OrderDto` is an application type.

**Key point:** every branch must read, discard, or release the body properly. `ClientResponse` cannot be kept around to call `bodyToMono()` repeatedly after its stream is consumed.

### 13.1. Does 404 Truly Mean “No Data”?

Only return `Mono.empty()` on 404 when the **downstream contract** defines 404 as “not found” in this business context. A 404 caused by a misconfigured route/gateway is a configuration bug to log, not an “empty list”.

### 13.2. Difference from Legacy `exchange()`

The legacy `exchange()` API easily caused body/connection leaks and has been replaced by modern methods like `retrieve()` and `exchangeToMono()`. Never hold onto `ClientResponse` beyond its processing scope without managing resources.

## 14. Distinguishing Resource Server Responses from OAuth2 Client Errors

A WebClient request with an OAuth2 filter typically has two phases:

~~~mermaid
sequenceDiagram
    participant MVC as Spring MVC controller
    participant WC as WebClient + Servlet OAuth2 filter
    participant M as OAuth2AuthorizedClientManager
    participant AS as Authorization Server
    participant RS as Orders API

    MVC->>WC: GET /api/orders
    WC->>M: authorize(company, principal)
    opt Access token needs refresh
        M->>AS: POST /token, refresh_token grant
        AS-->>M: New token or invalid_grant
    end
    M-->>WC: Authorized client or OAuth2 error
    WC->>RS: Authorization: Bearer access token
    RS-->>WC: 200 / 401 / 403 / 429 / 5xx
    WC-->>MVC: Response body or error signal
~~~

| Error Location | Example | Impact |
|---|---|---|
| **Token endpoint** | `invalid_grant` when refresh token is revoked | Manager fails to obtain a new access token |
| **Token endpoint** | `invalid_client` | Client authentication/configuration issue |
| **Resource Server** | `401 invalid_token` | Sent Bearer token was rejected by the API |
| **Resource Server** | `403 insufficient_scope` | Token may be valid yet lacks permissions |
| **Transport** | TCP connect error, TLS failure, timeout | Does not prove the token is broken |
| **Application decoder** | JSON mismatches schema | Incompatible API response format |

**Never retry token endpoint `invalid_grant` by calling again with the same refresh token infinitely.** If the provider uses refresh-token rotation, retries can worsen the failure.

## 15. OAuth2 WebClient on Servlet: Filter and Manager

Spring Security provides:

~~~java
import org.springframework.security.oauth2.client.web.reactive.function.client
    .ServletOAuth2AuthorizedClientExchangeFilterFunction;
~~~

Although its package includes `reactive.function.client`, this class is for **WebClient on the Servlet stack**.

### 15.1. WebClient Bean Using a Custom Manager

~~~java
package com.example.portal.config;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import reactor.netty.http.client.HttpClient;

@Configuration
public class OrdersWebClientConfig {

    @Bean("ordersWebClient")
    WebClient ordersWebClient(
        HttpClient ordersHttpClient,
        @Qualifier("webAuthorizedClientManager")
        OAuth2AuthorizedClientManager manager
    ) {
        ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServletOAuth2AuthorizedClientExchangeFilterFunction(manager);

        return WebClient.builder()
            .baseUrl("https://orders.example.test")
            .clientConnector(
                new ReactorClientHttpConnector(ordersHttpClient)
            )
            .apply(oauth2.oauth2Configuration())
            .build();
    }
}
~~~

This example uses a previously defined `webAuthorizedClientManager` bean, such as `DefaultOAuth2AuthorizedClientManager` for Servlet requests. `ordersHttpClient` is the timeout-configured HTTP client from section 5. Only this WebClient carries the OAuth2 filter.

**The constructor taking a custom manager does not automatically guarantee an authorization failure handler for Resource Server Bearer errors.** If you need to clean up broken authorized clients, configure the proper handler/repository/service for your Spring Security version.

### 15.2. Specifying the Registration When Calling the API

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client
    .ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<String> result = ordersWebClient.get()
    .uri("/api/orders")
    .attributes(clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class);
~~~

When called inside an authenticated Servlet request, the filter/manager uses registration `company` to look up the authorized client for the right principal. **Never use a browser-supplied registration ID and principal name** to access another account's token.

### 15.3. How Do WebClient HTTP Retries and the Token Manager Interact?

A typical call:

~~~text
Retry attempt 1:
  OAuth2 filter -> manager -> may refresh token
  HTTP GET Orders API -> 503

Retry attempt 2:
  OAuth2 filter -> manager -> load token
  HTTP GET Orders API -> 200
~~~

If `retryWhen` sits at the end of the `WebClient` publisher, **each retry can pass back through the OAuth2 filter/manager**, depending on pipeline composition. Account for this when:

- The token endpoint is slow or failing.
- Refresh tokens are rotated.
- A request hits 401 `invalid_token` and the failure handler deletes the token.
- The system runs multiple replicas.

Never treat token exchange retries and downstream API retries as indistinguishable operations.

## 16. Handling 401 Bearer `invalid_token` at the Right Layer

The Resource Server may return:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

This is different from **the browser not being logged into the Portal**.

~~~text
Browser -> Portal:
  valid JSESSIONID, SecurityContext holds OIDC principal

Portal -> Orders API:
  Access token AT-1 rejected
~~~

**Do not assume a downstream `invalid_token` requires invalidating the Portal's HTTP session.** You may need to:

1. Identify which registration/principal the token belongs to.
2. Remove the invalid authorized client if the Bearer error provides sufficient grounds and policy allows.
3. Avoid reusing AT-1 on subsequent requests.
4. Use an appropriate grant to re-authorize if possible; interactive authorization code grants may require a browser redirect/consent.
5. Return an appropriate error/CTA to the frontend if automatic recovery is impossible.

### 16.1. Failure Handler in `ServletOAuth2AuthorizedClientExchangeFilterFunction`

When using the constructor accepting:

~~~java
new ServletOAuth2AuthorizedClientExchangeFilterFunction(
    clientRegistrationRepository,
    authorizedClientRepository
)
~~~

Spring Security configures a handler to remove authorized clients on matching Bearer errors against that repository. When using the constructor **taking a custom manager**, inspect and explicitly configure `OAuth2AuthorizationFailureHandler` if you want consistent cleanup.

Conceptual integration:

~~~java
ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
    new ServletOAuth2AuthorizedClientExchangeFilterFunction(manager);

// Configure an authorization failure handler matching your repository/service
// via oauth2.setAuthorizationFailureHandler(...).
// The handler must operate on the manager's exact authorized-client store.
~~~

Implementations such as `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` can be used for matching error codes; constructor/remover details must match your Spring Security version and chosen storage. This is not a signal to wipe **every token** on any HTTP 401.

### 16.2. Do Not Use `retryWhen` for Infinite 401 Retries

~~~java
// Wrong: retries all Throwables, including invalid_token/401.
return ordersWebClient.get()
    .uri("/api/orders")
    .retrieve()
    .bodyToMono(String.class)
    .retryWhen(Retry.fixedDelay(
        10, Duration.ofMillis(100)
    ));
~~~

If the old token keeps getting sent or the manager cannot re-authorize, 10 retries simply send 10 failing requests to the Orders API. If a token is reissued, retries must be **bounded** and integrated with cleanup/token lifecycle, not blind HTTP repetition.

## 17. HTTP 403: Insufficient Scope Differs from an Expired Token

Downstream may return:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope",
                  scope="orders.write"
~~~

while the access token carries:

~~~text
scope = orders.read
~~~

Here **the token may still be valid** for reading the orders list. Retrying GET or refreshing with the same scope will not grant `orders.write`.

How to handle it:

- Check policies on the Orders API and target resource.
- Check scopes in `ClientRegistration` and issued tokens.
- If incremental authorization is needed, initiate the proper consent flow.
- If the user lacks permission, return a meaningful business 403.

**Do not delete a valid token simply for missing a scope**, unless default handlers/policies require it. Never add an ADMIN authority or tamper with JWT payloads on the Client.

## 18. HTTP 5xx, Gateway Errors, and Network Failures

Errors such as:

~~~text
500 Internal Server Error
502 Bad Gateway
503 Service Unavailable
504 Gateway Timeout
TCP connection refused
DNS resolution failure
TLS handshake failure
Read/response timeout
~~~

must be distinguished because not all are retryable.

| Error | Signal | Action |
|---|---|---|
| 502 from gateway | Upstream service failure | Can retry GET with backoff within budget |
| 503 service unavailable | Service under maintenance/overloaded | Bounded retry or circuit breaker |
| 504 gateway timeout | Gateway timed out waiting | Consider retrying idempotent operations |
| Connection refused | Host/port refused connection | Can retry while checking routing; avoid loops |
| DNS resolution failure | Wrong endpoint or DNS outage | Do not retry aggressively; likely misconfiguration |
| TLS cert invalid | Server/CA not trusted | Fix TLS trust; **never** disable verification and keep retrying |
| Response timeout | Server slow or stalled | Deadlines, pools, and selective idempotent retries |
| JSON decoding error | Response violates schema | Do not retry like a network error without reason |

**Retries amplify load**, especially when many requests hit 503 simultaneously. Backoff/jitter de-synchronizes retries, yet does not replace bulkheads, rate limiting, and circuit breakers when advanced resilience is needed.

## 19. Reading and Normalizing Downstream Error Responses

Suppose the Orders API returns:

~~~json
{
  "code": "ORDER_ALREADY_CANCELLED",
  "message": "Order cannot be cancelled twice",
  "traceId": "order-api-req-8831",
  "details": {
    "orderId": "ORD-100"
  }
}
~~~

The Portal may need to read `code` to show a friendly message, yet should not forward the raw body to the browser because it can contain internal details or sensitive data.

Normalized model:

~~~java
public record DownstreamError(
    String code,
    String message,
    String traceId
) {}
~~~

Then a service translates:

~~~text
HTTP 409 + code ORDER_ALREADY_CANCELLED
  -> AppBusinessException("Order was already cancelled")

HTTP 403 + insufficient_scope
  -> AppAuthorizationException("Not enough permission")

HTTP 503
  -> AppDependencyUnavailableException("Orders API unavailable")
~~~

**Never rely solely on the downstream `message` string** to make authorization or retry decisions. Use HTTP statuses, contract-defined error codes, and request context.

### 19.1. Controlling Body Size When Parsing Errors

Do not log unboundedly:

~~~java
// Dangerous if the response body is huge or holds sensitive data:
response.bodyToMono(String.class)
    .doOnNext(body -> log.error("Downstream body={}", body));
~~~

WebClient has a codec buffer limit, configurable as:

~~~java
WebClient client = WebClient.builder()
    .codecs(codecs ->
        codecs.defaultCodecs().maxInMemorySize(256 * 1024))
    .build();
~~~

A **256 KiB** limit is an example for cases requiring buffering. If legitimate responses are large, use streaming or pagination instead of raising the buffer indefinitely. `DataBufferLimitException` is a signal to revisit response sizes and codecs.

### 19.2. JSON Schemas Can Change

An API might add new fields or change error formats:

~~~json
{"error":"service_unavailable"}
~~~

versus:

~~~json
{"code":"SERVICE_UNAVAILABLE","message":"Please retry later"}
~~~

The Portal needs a fallback when an error body cannot be decoded. **Never turn a decode exception into HTTP 200 with an empty list**, as that hides downstream outages and drives wrong business decisions.

## 20. Handling 204, 304, and Empty-Body Responses

Different endpoints return different responses:

- **200 OK** with JSON body.
- **201 Created** with `Location` header.
- **202 Accepted** when accepted for asynchronous processing.
- **204 No Content** after an operation returning no body.
- **304 Not Modified** for conditional GETs.
- **404 Not Found** when a specific resource is missing.

Do not assume every successful response carries a JSON object.

DELETE example:

~~~java
Mono<Void> result = ordersWebClient.delete()
    .uri("/api/orders/{id}", orderId)
    .retrieve()
    .bodyToMono(Void.class);
~~~

This handles bodyless responses **with no default retries**. If an endpoint returns 202 with a job ID, read the header/body per contract and track progress instead of assuming deletion already completed.

### 20.1. Response Bodies Are Consumed Once

In `exchangeToMono()`, if one branch reads `bodyToMono(ErrorDto.class)`, do not try to read the entire raw body again afterward. HTTP response data is normally a single-consumption stream.

If you need structured error logging and a domain error, parse once into a matching DTO and extract only **log-safe fields**. Never enable debug logging that prints raw tokens, PII, and every response body.

## 21. Distinguishing `WebClientResponseException`, `WebClientRequestException`, and `TimeoutException`

Three error groups help pinpoint root causes:

| Exception/Group | Common Source | Has Downstream HTTP Status? |
|---|---|---|
| `WebClientResponseException` | `retrieve()` receives 4xx/5xx and emits an error signal | **Yes**, read `getStatusCode()`, headers |
| `WebClientRequestException` | Request I/O, DNS, connect/TLS, and transport errors | **Not necessarily**, request may not have received a response |
| `TimeoutException` from Reactor `timeout()` | Pipeline exceeded the configured duration | **Uncertain**, can happen at various stages |
| `DataBufferLimitException` | Body exceeded codec buffering limit | Response may have been received yet could not decode |
| `OAuth2AuthorizationException` | Client authorization/token endpoint failed | Often caused by token exchange ahead of downstream call |

For `WebClientResponseException`:

~~~java
if (error instanceof WebClientResponseException e) {
    int status = e.getStatusCode().value();
    String requestId =
        e.getHeaders().getFirst("X-Request-ID");
    // Only capture controlled fields.
}
~~~

Never call `e.getResponseBodyAsString()` and log it verbatim in production; error bodies may contain personal data or internal system details.

### 21.1. `TimeoutException` Does Not Always Mean the Server Did Not Process It

For a POST:

~~~text
Portal sends POST /api/orders
Orders API creates order and commits
Response arrives slowly, Portal times out
Portal thinks "failed"
~~~

Retrying without idempotency can create two orders. Handle **ambiguous** outcomes per business contract rather than treating timeouts as “guaranteed failure”.

## 22. Operator Order of Timeout, Retry, and Error Mapping Directly Affects Behavior

Compare two pipelines:

~~~java
// Pipeline A: Retry while WebClientResponseException status is still visible.
return webClient.get()
    .uri("/api/orders")
    .retrieve()
    .bodyToMono(OrdersPage.class)
    .retryWhen(retryPolicy)
    .onErrorMap(this::toDomainError);
~~~

~~~java
// Pipeline B: Map error before retry.
return webClient.get()
    .uri("/api/orders")
    .retrieve()
    .bodyToMono(OrdersPage.class)
    .onErrorMap(this::toDomainError)
    .retryWhen(retryPolicy);
~~~

In A, `retryPolicy` sees the original exception (e.g. `WebClientResponseException`) and can filter by HTTP status. In B, `retryPolicy` may only see custom domain errors. For B to work, the retry filter must match those custom exceptions.

### 22.1. A Recommended Pipeline for GET

~~~text
WebClient GET
  -> retrieve() / decode body
  -> per-attempt timeout
  -> retryWhen(transient errors only)
  -> overall deadline
  -> translate remaining errors into business errors
  -> Spring MVC controller returns appropriate response
~~~

This prevents turning 403 into a retryable error via unclear mapping. Even so, if the OAuth2 filter performs token refresh, factor the authorization lifecycle into your timeout and retry policies.

### 22.2. Which Error Details Do Timeouts Lose?

If the overall deadline expires before downstream returns 503, the pipeline knows only that it **timed out**, and cannot infer an HTTP status the server never sent. If the user cancels the request, cancellation can also stop response reading; instrument safe tracing to see where the budget ran out.

## 23. Mapping Errors for Spring MVC Controllers

A gateway can translate WebClient exceptions into domain exceptions, and a controller/advice then returns appropriate JSON to the frontend.

Example:

~~~java
package com.example.portal.web;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class PortalErrorAdvice {

    @ExceptionHandler(DownstreamUnavailableException.class)
    ResponseEntity<ApiError> unavailable() {
        return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
            .body(new ApiError("ORDERS_UNAVAILABLE"));
    }

    @ExceptionHandler(DownstreamRateLimitedException.class)
    ResponseEntity<ApiError> rateLimited() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(new ApiError("ORDERS_RATE_LIMITED"));
    }

    @ExceptionHandler(DownstreamPermissionException.class)
    ResponseEntity<ApiError> forbidden() {
        return ResponseEntity.status(HttpStatus.FORBIDDEN)
            .body(new ApiError("ORDERS_FORBIDDEN"));
    }

    public record ApiError(String code) {}
}
~~~

`DownstreamUnavailableException`, `DownstreamRateLimitedException`, and `DownstreamPermissionException` are **application domain exceptions**, not Spring built-ins. Statuses 502/503/403 illustrate **one API contract**, not a mandatory mapping for every BFF.

**Distinguish:**

- 401 from Portal when the browser lacks a session/authentication.
- 401 from Orders API when the Bearer token sent by Portal was rejected.
- 403 from Orders API due to scope/resource permissions.

Never forward raw upstream OAuth2 challenges/secrets/error bodies unconditionally to the browser. If the frontend needs reauthorization, define a dedicated error code/action.

### 23.1. Controller Returning `Mono` in MVC

~~~java
package com.example.portal.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class OrdersController {

    private final OrdersReadGateway gateway;

    public OrdersController(OrdersReadGateway gateway) {
        this.gateway = gateway;
    }

    @GetMapping("/bff/orders")
    public Mono<String> listOrders() {
        return gateway.listOrders();
    }
}
~~~

Spring MVC supports reactive return types through async integration. However, preserving **Servlet request context / `SecurityContext` ThreadLocal** across asynchronous steps requires care, especially when `ServletOAuth2AuthorizedClientExchangeFilterFunction` needs `Authentication` and Servlet request/response.

If the integration relies on request attributes/ThreadLocals at **subscription time** and subscription runs after the Servlet request thread finishes, context may no longer be there. Pass needed attributes through **Spring Security's supported Servlet WebClient mechanisms** or resolve the authorized client at the authenticated Servlet boundary. Never read `SecurityContextHolder` on an arbitrary Reactor scheduler expecting context to propagate automatically.

## 24. Context Propagation When WebClient Runs Asynchronously

This is specific to **WebClient in a Servlet application**.

### 24.1. Why Is Context Easily Lost?

~~~text
Servlet Thread:
  SecurityContextHolder has Authentication
  HttpServletRequest has session, principal
      |
      v
Create Mono<WebClientResponse>
      |
      v
Mono subscribed or switched to another scheduler
      |
      v
Another Thread:
  ThreadLocal SecurityContext may be absent
~~~

Spring Security's Servlet WebClient filter can pull `Authentication`/Servlet request from the appropriate context per its integration API. When running async or inside scheduled jobs, explicitly define how context is passed.

### 24.2. Do Not “Quick-Fix” with an Arbitrary Principal Name

Wrong:

~~~java
// Never take a principal from user input to pick another person's token:
.attributes(ServletOAuth2AuthorizedClientExchangeFilterFunction
    .clientRegistrationId(userSuppliedRegistrationId))
~~~

and never pass `principalName=admin` just to load an admin token from the store.

For requests acting on behalf of a user, the authorized client must tie to a **verified Authentication**. For scheduled jobs, pick a manager backed by `OAuth2AuthorizedClientService` and a separately managed service principal.

### 24.3. `.block()` in MVC

~~~java
// Usable at a blocking boundary of an MVC app
// once timeouts, thread counts, and context are properly designed:
OrdersPage page = callMono.block(Duration.ofSeconds(6));
~~~

However:

- Each request holds a Servlet thread while waiting.
- Never block inside a Reactor Netty event loop.
- Never call `.block()` nested inside `map`/`flatMap` running on an event loop.
- `.block(Duration)` enforces its own deadline; avoid conflicting deadlines with `.timeout(...)`.
- For high throughput, consider MVC async return types or intentionally adopting a WebFlux architecture rather than merely swapping HTTP clients.

## 25. Timeouts and Retries Across Multiple Downstream Services

Suppose the Portal calls concurrently:

~~~text
Orders API    -> fetch order list
Inventory API -> check stock
Pricing API   -> calculate prices
~~~

If each service has 3 attempts and a 5-second timeout, total time/capacity can blow through the HTTP request budget. Potential issues:

- **Fan-out amplification:** one browser request triggers many backend requests.
- **Retry amplification:** each downstream retries independently, multiplying traffic.
- **Cascade failure:** one slow API ties up connections/threads, taking down other APIs.
- **Cancellation:** when one branch fails or overall timeout hits, other branches may cancel even though servers already processed them.

Policies:

1. Enforce an **overall deadline** on the BFF request and per-downstream budgets.
2. Bound **concurrency** via connection pools/bulkheads.
3. Retry at one intentional layer only; avoid independent retries at HTTP client, gateway, and service layers simultaneously.
4. Use **fallbacks** only when stale/missing data is valid by business rules and clearly surfaced.
5. Never fake success when required data is missing.

Example **intentional** fallback:

~~~java
// Permissible if “product recommendations” content is optional:
return recommendationsClient.get()
    .uri("/api/recommendations")
    .retrieve()
    .bodyToMono(RecommendationList.class)
    .onErrorReturn(RecommendationList.empty());
~~~

**Never apply `onErrorReturn(empty)` to order/payment data requiring consistency**, as hiding errors drives bad business decisions.

## 26. Connection Pools and Backpressure

Non-blocking WebClient does not mean unlimited connections to downstream services.

~~~java
ConnectionProvider pool = ConnectionProvider.builder("orders-pool")
    .maxConnections(100)
    .pendingAcquireTimeout(Duration.ofSeconds(1))
    .build();
~~~

Meaning:

- `maxConnections(100)` caps open connections per pool policy.
- `pendingAcquireTimeout(1s)` caps how long callers wait for a connection when the pool is busy.
- Under overload, requests can fail **before even reaching the Orders API**.

Retrying pool-exhausted errors aggressively can worsen congestion. You should:

- Measure queue latency and pending acquires.
- Cap caller concurrency.
- Use appropriate backpressure, bulkheads, and rate limiting.
- Add an overall request timeout.
- Avoid creating a separate Reactor Netty connection pool per request or per user.

Raising `maxConnections` does not always help because downstream services and gateways have limits too.

## 27. Observability: Pinpointing Failures Without Exposing Data

A request to Orders API can carry:

~~~text
Portal Trace ID: portal-req-192
Downstream request ID: orders-req-202
Registration: company
HTTP method: GET
Route: /api/orders
Attempt: 1/3
Status: 503
Latency: 890 ms
Retry decision: yes
~~~

Safe fields to measure:

| Field/Metric | Purpose |
|---|---|
| Downstream service name | Isolate dependency |
| Route template, not full URL with PII queries | Group requests by API |
| HTTP status / OAuth2 error code | Classify errors |
| Connection/pool wait time | Detect local congestion |
| Token refresh attempted/succeeded | Separate token endpoint from Resource Server |
| Retry count/backoff | Spot amplification |
| Deadline exceeded | Investigate timeouts |
| Correlation/trace ID | Link logs across services |
| Allowlisted Registration ID | Identify OAuth client used |

**Never log:**

~~~text
Authorization: Bearer <real-access-token>
refresh_token=<real-refresh-token>
client_secret=<real-client-secret>
Cookie: JSESSIONID=<real-session-id>
id_token=<real-id-token>
authorization_code=<real-code>
~~~

Do not enable HTTP wiretaps or log full request/response bodies in production just to inspect status codes. Error bodies can contain emails, order IDs, personal data, or internal contents from other systems.

### 27.1. Metrics Should Distinguish Error Groups

~~~text
downstream.http.errors{service=orders,status=503}
downstream.http.errors{service=orders,status=403}
downstream.http.timeout{service=orders}
oauth2.client.refresh.failures{registration=company,error=invalid_grant}
downstream.http.retries{service=orders,reason=503}
~~~

These names are illustrative custom instrumentation, not all emitted by Spring Boot out of the box. Avoid high-cardinality metric labels like token values, user emails, or order IDs.

## 28. Testing Timeouts, Retries, and Response Handling

Tests should use a **mock HTTP server** and dummy authorized clients, never calling production IdPs or Orders APIs.

| Test Case | Simulation | Expected Outcome |
|---|---|---|
| GET 200 valid JSON | Returns `OrdersPage` | Decodes into proper DTO |
| GET 204 | Empty response body | Handles emptiness per contract |
| GET 404 | Order missing | `Mono.empty()` only when API defines it that way |
| GET 429 | Valid `Retry-After` | Respects wait cap and overall deadline |
| GET 503, then 200 | Transient error | Bounded retry succeeds |
| GET 503 continuously | Always fails | Stops after max retries/deadline |
| GET 403 | `insufficient_scope` | No retry; preserves insufficient-permission semantics |
| GET 401 | `invalid_token` | OAuth2 failure handling, not 10 blind retries |
| Order-creation POST timeout | Server may have committed | Does not auto-retry without idempotency |
| Connect timeout | Unresponsive host | Transport error classified properly |
| Response body exceeds buffer | Large payload | Produces `DataBufferLimitException` or uses streaming policy |
| Invalid JSON schema | Decoder fails | Never turns into 200 empty |
| Token refresh fails | `invalid_grant` | Manager failure handled separately from downstream 503 |
| Two principals | Tokens for user A and user B | Never attaches the wrong token |
| Async context lost | Subscribe on another thread | OAuth2 filter gets proper context or fails safely |

### 28.1. `StepVerifier` with a Fake Publisher

Retry logic example independent of real HTTP:

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RetryPolicyTest {

    @Test
    void transientFailureIsRetriedThenSucceeds() {
        AtomicInteger calls = new AtomicInteger();

        Mono<String> source = Mono.defer(() -> {
            int attempt = calls.incrementAndGet();
            if (attempt < 3) {
                return Mono.error(
                    new TemporaryDownstreamException("temporary"));
            }
            return Mono.just("OK");
        });

        Mono<String> result = source.retryWhen(
            Retry.backoff(2, Duration.ofMillis(10))
                .filter(e -> e instanceof TemporaryDownstreamException)
        );

        StepVerifier.create(result)
            .expectNext("OK")
            .verifyComplete();

        assertEquals(3, calls.get());
    }

    static class TemporaryDownstreamException extends RuntimeException {
        TemporaryDownstreamException(String message) {
            super(message);
        }
    }
}
~~~

This example illustrates `Retry.backoff(2, ...)` meaning at most **two retries**. In real tests, use **virtual time** for long backoff schedules so tests remain fast and deterministic.

### 28.2. Mock HTTP Server to Test Responses

Verify at minimum:

~~~text
Attempt 1: GET /api/orders -> HTTP 503
Attempt 2: GET /api/orders -> HTTP 200 with JSON
Result: Valid OrdersPage
HTTP requests observed: 2
Authorization header: Bearer TEST_ACCESS_TOKEN
Token never appears in logs
~~~

To test OAuth2 integration, stub `OAuth2AuthorizedClientManager` to return a dummy `OAuth2AuthorizedClient`, then verify WebClient attaches the Bearer token for the right registration when calling the mock server.

**Test integration wiring and OAuth2 failure handling separately**, not just unit-testing retry functions. Having a `@Bean WebClient` in the Spring context does not prove controllers/services use the exact bean with the configured OAuth2 filter and timeouts.

### 28.3. Testing Timeouts Without Arbitrary Sleeps

For HTTP integration, a mock server can intentionally hold connections open or delay responses to verify Reactor Netty's **response timeout**. For Reactor's `timeout()` operator and retry backoffs, `StepVerifier.withVirtualTime` lets you test timing logic without real-time waiting when operators support virtual schedulers.

Avoid long sleeps across dozens of CI tests, as they cause flakiness and slow down test suites.

## 29. Operating During a Downstream Outage

When the Orders API returns widespread 503s:

1. **Confirm it is a downstream outage**, rather than jumping to conclusions about user logouts or expired tokens.
2. Inspect status, latency, and tracing by route and service.
3. Check connection pools, pending acquisitions, and concurrency limits.
4. Watch for retry amplification; reduce retries if upstream load is overwhelming.
5. Engage circuit breakers/rate limiters if already part of the controlled architecture.
6. Return an appropriate UI error; if valid cached data is shown, clearly label freshness, source, and user permission scope.
7. Only touch OAuth2 authorized clients when there is **evidence of token failure**.

An unresponsive service is **never** a valid reason to wipe access/refresh tokens from the database. Blindly wiping tokens spikes Authorization Server traffic and risks triggering a second outage.

## 30. Symptom-Based Troubleshooting

| Symptom | Possible Cause | How to Isolate |
|---|---|---|
| MVC endpoint hangs | Missing timeout, many retries, or `block()` on Servlet thread | Check per-attempt/overall deadlines and thread pools |
| Connect timeout | Slow DNS/firewall/routing/host | Check egress, connection pool, and TCP timeout |
| Response timeout | API too slow or stream stalled | Check downstream latency and `responseTimeout` |
| 503 keeps retrying and gets slower | Retries exceed budget, no jitter | Cap attempts, add backoff, set overall timeout |
| Repeated 401s despite user login | Invalid access token or gateway error | Check Bearer challenge and authorized-client lifecycle |
| 403 after refresh | Token lacks scope/permissions | Check Resource Server policy; do not retry blindly |
| 429 still increases load | Retries ignore rate limits | Coordinate `Retry-After`/backoff/budget |
| POST creates duplicate orders | Non-idempotent retry without idempotency key | Fix API contract and deduplication |
| JSON decode fails | Schema changed or wrong content type | Inspect bounded response; add fallback error mapping |
| 404 returns 200 with empty list | Misused `onStatus(Mono.empty())` semantics | Use `exchangeToMono` per contract |
| `DataBufferLimitException` | Body exceeds codec buffer | Pagination/streaming or appropriate buffer limit |
| Token missing on async thread | Servlet `SecurityContext`/request context not propagated | Check OAuth2 filter attributes and context |
| Token sent to another hostname | WebClient permits uncontrolled absolute URLs/redirects | Restrict destinations/registrations |
| Retry policy stops catching 503 | `onStatus` replaced exception with custom type | Make retry filter recognize the custom type |
| HTTP transport timeout has no effect | Wrong WebClient or Netty connector configured | Verify which bean is actually injected |
| Token endpoint timeout unchanged | Configured Orders WebClient instead of token WebClient | Configure transport on the token-response client separately |
| API returns 500 yet authorized client is deleted | Failure handler deletes on every response | Clean up only on matching Bearer/OAuth2 errors |

**Investigation path:** check sequentially **Servlet session → OAuth2 manager/token endpoint → HTTP connector → Resource Server response → decoder → retry policy → BFF error mapping**.

## 31. Anti-Patterns to Avoid

**1. Adding `retryWhen(...)` to every HTTP request** without considering HTTP method, idempotency, and error type.

**2. Using `onErrorReturn(emptyList)` for mandatory data.** This disguises service outages as “no orders”, driving wrong business actions.

**3. Setting only a connect timeout.** A server can accept TCP yet stall on the response; configure response and overall timeouts.

**4. Setting a 30-second timeout when the gateway only waits 5 seconds.** Requests keep running after the caller has already disconnected.

**5. Retrying 401 `invalid_token` like 503.** Handle the authorized client, refresh, or reauthorization instead of replaying the exact same token repeatedly.

**6. Deleting an authorized client on 403 `insufficient_scope`.** The token may still be valid for other operations.

**7. Using WebFlux's OAuth2 WebClient filter in a Servlet app with the wrong manager.** Servlet needs the matching integration and principal/session context.

**8. Calling `.block()` inside a Reactor event loop.** This hurts throughput or triggers illegal-blocking exceptions.

**9. Logging full requests/responses or Bearer headers.** High risk of exposing tokens and personal data.

**10. Forwarding raw API error messages straight to the browser.** Error bodies are not always safe to expose.

**11. Retrying a POST after timeout without an idempotency contract.** Risks duplicate transactions.

**12. Testing only HTTP status codes without testing retry/timeout/error-mapping order.** Pipeline operator order changes behavior.

## 32. Applied Exercises

### Exercise 1 — Choosing Timeouts

A WebClient is configured only with:

~~~java
HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000);
~~~

**Question:** Why can an API call still hang for a long time after the TCP connection is established?

**Solution guide:** Connect timeout only caps TCP connection establishment; you need a response timeout and/or overall reactive deadline to bound how long the server takes to return data.

### Exercise 2 — Checking Retry Attempts

~~~java
Retry.backoff(2, Duration.ofMillis(200))
~~~

**Question:** What is the maximum number of attempts?

**Solution guide:** One initial attempt plus **at most two retries**, totaling **three attempts** if every failure is retryable and the deadline allows.

### Exercise 3 — 401 and 403

~~~text
GET /api/orders -> 401 Bearer invalid_token
DELETE /api/orders/42 -> 403 Bearer insufficient_scope
~~~

**Question:** Should both errors trigger the same retry or authorized-client deletion?

**Solution guide:** No. `invalid_token` may require cleanup/re-authorization, whereas `insufficient_scope` is missing permissions; the token may still work for other APIs.

### Exercise 4 — Retrying POST After a Network Timeout

The Portal sends a POST to create an order. Downstream committed it, yet the Portal never received the response.

**Question:** Is simply adding `retryWhen(3)` safe?

**Solution guide:** No. You need an idempotency key/operation ID with downstream deduplication or a transaction-status lookup API. A timeout does not prove the request was not processed.

### Exercise 5 — Misconfigured 404 Mapping

~~~java
.retrieve()
.onStatus(status -> status.value() == 404, response -> Mono.empty())
.bodyToMono(OrderDto.class)
~~~

**Question:** Does 404 automatically become `Mono.empty()` at the end?

**Solution guide:** Not guaranteed; `onStatus(..., Mono.empty())` only means “do not treat 404 as an error”, and the decoder still runs on the response. Use `exchangeToMono()` to return `Mono.empty()` cleanly per business rules.

### Exercise 6 — Retries Stop Working After `onStatus`

The gateway maps every 503 into `DownstreamUnavailableException`, while the retry policy only filters for `WebClientResponseException`.

**Question:** Why does it stop retrying?

**Solution guide:** The exception type changed before reaching retry. Place retry before error mapping or update the retry filter to match the custom exception while preserving required semantics and status.

### Exercise 7 — ThreadLocal and Servlet WebClient

A Spring MVC controller returns `Mono<OrdersPage>`, yet subscription runs on another thread and the OAuth2 filter fails to find the principal.

**Question:** Should you set `principalName="admin"` to fix it?

**Solution guide:** No. Configure Servlet WebClient context propagation using the right API or resolve the authorized client at the authenticated request boundary—never pick an arbitrary principal or borrow another user's token.

### Exercise 8 — 429 with a Large `Retry-After`

The Orders API returns `429 Retry-After: 120`, while the Portal only has a 5-second overall deadline.

**Question:** Should the request wait 120 seconds?

**Solution guide:** No. Stop within budget, return an appropriate error, or offload to an asynchronous workflow if business rules allow; do not overload the server.

## 33. Implementation Checklist for WebClient on Servlet

| Question | What to Ensure |
|---|---|
| Is the web app truly Servlet? | Uses `SecurityFilterChain`/`HttpSecurity` |
| Does OAuth2 integration match the stack? | `ServletOAuth2AuthorizedClientExchangeFilterFunction` |
| Does WebClient use the right manager? | Passed to constructor/filter, not merely declared as a bean |
| Is the Registration ID explicit? | Chosen for Orders API, never arbitrarily from user input |
| Are access tokens protected? | Never returned to browser, never logged as Bearer/refresh token |
| Are URLs/redirects allowlisted? | Never send tokens to hosts outside allowed scope |
| Is there a TCP connect timeout? | Yes, sized for the environment |
| Is there a response timeout? | Yes, distinct from connect timeout |
| Is there an overall deadline? | Yes, covering retries and latency budget |
| Which errors are retried? | Only allowlisted transient errors; never blind-retry 401/403 |
| How many retries? | Bounded attempts, backoff, jitter |
| Does it respect 429/`Retry-After`? | Enforces budget and rate-limit policies |
| Does POST have an idempotency contract? | Never retry arbitrarily |
| Are status/headers/body inspected properly? | `retrieve`/`onStatus`/`toEntity`/`exchangeToMono` used with right semantics |
| How are empty bodies/204/404/304 handled? | Per API contract |
| Are large bodies bounded? | Buffer limits, pagination/streaming |
| Does error mapping preserve status/reason? | Retry filter receives the right exception type |
| Does MVC async preserve principal/context? | Proper integration/context propagation configured |
| Are connection pools and load limits set? | Max connections, pending acquire limits, and metrics |
| Are logs/metrics safe? | No raw tokens, cookies, or PII |
| Are 401/403/429/503/timeout/retry tested? | Yes, including idempotency and OAuth2 wiring |

## 34. Summary

When using **WebClient on Spring MVC/Servlet** in a **Spring Security OAuth 2.0/OIDC Client** application, distinguish **login session**, **authorized client/token**, **HTTP transport**, **retry policy**, and **Resource Server response**. `ServletOAuth2AuthorizedClientExchangeFilterFunction` helps WebClient obtain Bearer tokens via `OAuth2AuthorizedClientManager`, yet it does not choose safe timeouts or retries for each business operation on its own.

**Timeouts** should be designed in layers: connection pool acquisition, TCP connect, response timeout, per-attempt timeout, and overall deadline. **Retries** fit only transient errors, replay-safe operations, and remaining time budgets; always enforce max attempts, backoff/jitter, and `Retry-After` awareness. In particular, never retry side-effecting POSTs without downstream-guaranteed idempotency.

To **analyze responses**, use `retrieve()` for standard cases, `onStatus()` to map errors, `toEntity()` when headers/status are needed, and `exchangeToMono()` when controlling individual status/body branches. Distinguish **401 `invalid_token`**, **403 `insufficient_scope`**, **429 rate limits**, and **5xx/network failures**, avoiding deleting tokens or logging out users over non-OAuth2 errors.

A resilient configuration does more than “retry on error”: it enforces **the right principal/registration**, **no token leakage**, **intact Servlet context**, **bounded execution time**, **no duplicated business operations**, and **safe diagnostics**. That forms the foundation for a Portal calling downstream services reliably and securely even when using a Reactive HTTP client inside a Servlet application.
