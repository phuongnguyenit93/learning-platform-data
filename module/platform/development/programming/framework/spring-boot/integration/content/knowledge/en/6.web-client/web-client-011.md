# Controlling Retries, Tokens, and Target Destinations to Prevent Data Leakage

## 1. The Problem in WebClient Integration Flows

In **SPRING_BOOT_INTEGRATION**, `WebClient` typically serves as the HTTP adapter from a Spring Boot service to a partner API or internal service. That API's response can determine database writes, cache updates, broker message publishing, or forwarding a message to the next step in Spring Integration. Therefore, retrying after failures must be designed alongside the **data contract, transactions, deduplication, and observability** of the entire flow.

Three seemingly independent elements can combine into a security incident:

1. **Retry:** A transient error causes the same HTTP request to be sent multiple times.
2. **Token:** The request carries `Authorization: Bearer ...` or another credential.
3. **Target destination:** The URL is assembled from configuration, business parameters, or a `Location` header in a redirect response.

If the URL is allowed to change arbitrarily, each retry may resend the token and business data to an unauthorized server. If full requests/responses are logged, the token can also appear in logs, traces, or error messages. Retries do not create a vulnerability by themselves, but they **multiply transmissions and amplify the impact when a request is misrouted**.

### Learning Objectives

- Retry only recoverable errors, with bounded attempts and wait times; identify which operations are safe to resend.
- Issue tokens scoped to the right API, permissions (`scope`), and target (`audience`); avoid leaking them via URLs, redirects, and logs.
- Define, validate, and restrict target HTTP destinations; understand why `baseUrl` alone is insufficient to lock down the destination host.
- Write tests proving requests never go to unknown hosts, never leak tokens, and never retry beyond budget.

## 2. Threat Model: Where Do Leaks Start?

Consider an order lookup flow against a partner API:

```text
Inbound HTTP request to Spring Boot
    → validate orderId
    → obtain access token for partner API
    → WebClient GET /v1/orders/{orderId}
    → receive result
    → update state / return DTO / publish event
```

Common leak points:

| Origin | Unsafe Example | Consequence |
| --- | --- | --- |
| Dynamic URL | `client.get().uri(userSuppliedUrl)` | SSRF: sends requests to unknown servers, internal addresses, or metadata services |
| Shared token | Attaching a default `Authorization` header on one `WebClient` shared across partners | The wrong API can receive a token meant only for another API |
| HTTP redirect | Automatically following `Location` to a host outside the allowlist | Data or credentials risk traveling to an untrusted destination |
| Broad retry | `retry(10)` on every exception, including 401/403 and resource-creating POSTs | Amplifies load, duplicates operations, spreads sensitive data further |
| HTTP logging | Enabling wiretap logging headers/body or logging full requests | Tokens, cookies, and sensitive payloads end up in logs/traces |
| Token in query | `?access_token=...` or passing tokens in the path | Tokens appear in URLs, proxies, access logs, and monitoring reports |

A dangerous URL does not necessarily look suspicious. For example, `https://api.partner.example.evil.test` is not the host `api.partner.example`; `https://api.partner.example@evil.test/path` actually has host `evil.test`. Addresses like `http://169.254.169.254/` and loopback/private addresses must also be blocked whenever input can influence the URL.

**Principle:** Outbound network permissions, token-carrying permissions, and retry permissions must be constrained independently and then verified together at the `WebClient` boundary.

## 3. Validating Target Destinations Before Sending Requests

### 3.1. Create a Dedicated WebClient per API

Configure each critical downstream service with a dedicated `WebClient`, taking the base URL from controlled configuration. Business methods should accept only **identifiers or data**, never a full URL from the user.

```java
@Configuration
class PartnerHttpConfig {
    private static final String PARTNER_HOST = "partner-api.example.net";

    @Bean("partnerWebClient")
    WebClient partnerWebClient(WebClient.Builder builder) {
        HttpClient httpClient = HttpClient.create()
            .followRedirect(false)
            .responseTimeout(Duration.ofSeconds(2));

        return builder.clone()
            .baseUrl("https://" + PARTNER_HOST)
            .clientConnector(new ReactorClientHttpConnector(httpClient))
            .filter((request, next) -> {
                URI destination = request.url();

                boolean allowed =
                    "https".equalsIgnoreCase(destination.getScheme())
                    && PARTNER_HOST.equalsIgnoreCase(destination.getHost())
                    && (destination.getPort() == -1 || destination.getPort() == 443)
                    && destination.getRawUserInfo() == null;

                if (!allowed) {
                    return Mono.error(
                        new IllegalArgumentException("Downstream destination rejected")
                    );
                }
                return next.exchange(request);
            })
            .build();
    }
}
```

Typical imports: `java.net.URI`, `java.time.Duration`, `reactor.core.publisher.Mono`, `reactor.netty.http.client.HttpClient`, `org.springframework.context.annotation.Bean`, `org.springframework.context.annotation.Configuration`, `org.springframework.http.client.reactive.ReactorClientHttpConnector`, and `org.springframework.web.reactive.function.client.WebClient`. This configuration illustrates an application using Spring WebFlux `WebClient` and Reactor Netty; `example.net` is a placeholder domain that must be replaced with an authorized real destination.

**Explanation of each defense layer:**

- `baseUrl(...)` helps construct relative URIs consistently. It is **not a security barrier**: passing an absolute URI to `uri(...)` can bypass the base URL.
- The filter inspects the final URL in `ClientRequest` before handing the request to the connector. It rejects invalid schemes, hosts, ports, and user-info. Compare the **parsed host from the URI**, never `startsWith` or `contains` on a raw URL string.
- `followRedirect(false)` prevents the HTTP client from automatically opening a new connection to the target in `Location`. 3xx responses are handled as errors at the business layer.
- `responseTimeout` bounds the connection's wait for response activity. It **does not replace** a time budget across the full token → HTTP call → retry chain.

In production environments, place the host and port allowlist under controlled deployment configuration, validate configuration at startup, and restrict network egress (egress firewall, service mesh, or proxy). A Java filter cannot replace network policy: DNS rebinding, DNS changes between check and connection, proxies, and redirects must be handled at the connection/infrastructure layer if the system genuinely allows user-supplied URLs.

### 3.2. Treat Business Parameters as Data

Do not accept `targetUrl` and pass it directly into `WebClient.uri(...)`. For a request fetching an order, accept only `orderId` and build a fixed route:

```java
// Prefer fixed endpoints and strict identifier format constraints.
if (orderId == null || !orderId.matches("[A-Za-z0-9_-]{1,64}")) {
    return Mono.error(new IllegalArgumentException("Invalid orderId"));
}

return client.get()
    .uri(builder -> builder.pathSegment("v1", "orders", orderId).build())
    .retrieve()
    .bodyToMono(PartnerOrder.class);
```

`pathSegment` makes explicit that `orderId` is a single path segment; format validation also blocks anomalous values like `..`, `/`, or a full URL. For non-path search values, use `queryParam("q", value)` so the library encodes parameters in the proper context. Never put access tokens, API keys, or passwords in the path or query string.

If business logic must call one of several endpoints, map a **predefined partner code → trusted endpoint**, and select the corresponding `WebClient`; never turn a partner code into a raw URL string. If external URLs must be supported, scheme/host/port, DNS/IP, redirect, and egress validation require dedicated design and testing.

## 4. Issuing Tokens to the Right Destination at the Right Time

### 4.1. Tokens Must Be Scoped

An access token is a credential that can be replayed if exposed. Before sending a token, answer:

| Question | Required Control |
| --- | --- |
| Who issued it? | A trusted identity provider or token service |
| Who is it issued for? | `audience` is the target resource server/API, not every system |
| What can it do? | Least-privilege `scope` / permissions for the specific operation |
| Is it still valid? | Track expiration, cache, and refresh safely in a token provider |
| Where is it sent? | Over HTTPS to an allowed host, via the `Authorization` header |
| Who can see it? | Never log tokens in logs, traces, exceptions, metric tags, or URLs |

In server-to-server integrations, a common choice is OAuth2 `client_credentials` via Spring Security's authorized-client management. Separate obtaining/refreshing tokens from business HTTP calling logic. Do not forward a logged-in user's token to a different API simply because it sits in the security context: that token may carry an `audience` or permissions unsuitable for the downstream service.

Be especially cautious with configurations that auto-select a default authorized client (`setDefaultOAuth2AuthorizedClient(true)` in Spring Security environments that support it), or `defaultHeader("Authorization", ...)` on a shared `WebClient`. These choices can send credentials unintentionally when the same client is used with a different URL. For critical APIs, choose the registration/token provider intentionally and attach tokens on requests whose destination has already been verified.

### 4.2. Handling 401/403 Responses

- **401 Unauthorized:** Do not retry in a loop with the same token. Investigate the cause and let the token provider manage expiration/refresh; if business policy allows, refresh and retry at most **once in a controlled manner** to the same host and scope.
- **403 Forbidden:** Typically indicates insufficient permissions, wrong scope, or policy denial. Do not retry automatically.
- **Redirect to a login page:** For APIs carrying bearer tokens, treat this as an unexpected response; do not follow the redirect or resend the token to that page.

Never include the token value or `Authorization` header inside exception messages, even when returning errors for debugging.

## 5. Designing Bounded and Conditional Retries

### 5.1. Retrying Means Resending Side Effects

In Reactor, `retryWhen(...)` **resubscribes to the upstream `Mono`/`Flux` before it** after an error signal. With `WebClient`, this usually produces a new HTTP request. If earlier stages in the chain also write data, publish events, or call other APIs, those steps may run again too.

| Scenario | Default Recommendation | Reason |
| --- | --- | --- |
| Read-only GET, 429 | Bounded retry, respect `Retry-After` | Likely temporary rate limiting |
| Read-only GET, 502/503/504 | Retry with exponential backoff + jitter | Gateway/service failures are often transient |
| GET returning 400/404/401/403 | Do not retry automatically | Waiting longer usually cannot fix an invalid request or permission error |
| POST creating an order/payment | Do not retry blindly | May already have been processed before the client lost the connection |
| PUT/PATCH/DELETE | Evaluate API semantics and contract individually | Safety depends on idempotency, version/ETag, and side effects |
| Timeout/disconnect after sending request | Requires dedicated evaluation | The client does not know whether the server executed it |

**Idempotent** means executing an operation multiple times yields the same observable result/state according to the contract, not merely judging by the HTTP method name. For write operations, you need server-supported idempotency keys, deduplication tables, unique request IDs, optimistic locking, or deduplication logic. If the API does not guarantee deduplication, retrying after a timeout can create two transactions.

### 5.2. Components of a Retry Policy

1. **Condition:** Only a well-classified set of transient statuses or exceptions.
2. **Attempt limit:** Distinguish *retries* from total *attempts*. `Retry.backoff(2, ...)` means at most **two retries**, for at most three requests total.
3. **Backoff + jitter:** Increasing wait intervals with randomized jitter so multiple instances do not thunder back simultaneously.
4. **Time budget:** An overall deadline for the call; per-attempt limits are insufficient if retries drag on.
5. **Rate limits and `Retry-After`:** If the server returns a delay hint, parse valid delta-seconds or HTTP-date values, bounded by the deadline; never wait indefinitely.
6. **Coordination:** Circuit breakers, bulkheads, or concurrency limits when downstream is overloaded; avoid stacked retries across layers (gateway, SDK, app, broker consumer) multiplying attempts.

### 5.3. Combined Example: Destination Lock, Token Attachment, GET Retry

The example below uses `partnerWebClient` from section 3. The token comes from a dedicated provider; only a read-only GET is retried on transient responses. In a real program, add imports for `Mono`, `Retry`, `Duration`, `WebClient`, `HttpStatusCode`, `@Service`, and `@Qualifier`.

```java
interface PartnerTokenProvider {
    // Token with the right audience/scope; caching and refresh managed by the provider.
    Mono<String> tokenForOrdersRead();
}

record PartnerOrder(String id, String state) {}

@Service
class PartnerOrderGateway {
    private final WebClient client;
    private final PartnerTokenProvider tokens;

    PartnerOrderGateway(
        @Qualifier("partnerWebClient") WebClient client,
        PartnerTokenProvider tokens
    ) {
        this.client = client;
        this.tokens = tokens;
    }

    Mono<PartnerOrder> getOrder(String orderId) {
        if (orderId == null || !orderId.matches("[A-Za-z0-9_-]{1,64}")) {
            return Mono.error(new IllegalArgumentException("Invalid orderId"));
        }

        Retry retryPolicy = Retry.backoff(2, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(1))
            .jitter(0.5)
            .filter(RetryablePartnerResponse.class::isInstance)
            .onRetryExhaustedThrow((spec, signal) -> signal.failure());

        return tokens.tokenForOrdersRead()
            .flatMap(token -> client.get()
                .uri(uri -> uri.pathSegment("v1", "orders", orderId).build())
                .headers(headers -> headers.setBearerAuth(token))
                .retrieve()
                .onStatus(
                    status -> status.is3xxRedirection(),
                    response -> response.releaseBody()
                        .thenReturn(new UnexpectedRedirect())
                )
                .onStatus(
                    status -> status.value() == 429
                           || status.value() == 502
                           || status.value() == 503
                           || status.value() == 504,
                    response -> response.releaseBody()
                        .thenReturn(new RetryablePartnerResponse())
                )
                .bodyToMono(PartnerOrder.class)
                .retryWhen(retryPolicy)
            )
            .timeout(Duration.ofSeconds(5));
    }

    static final class RetryablePartnerResponse extends RuntimeException {}
    static final class UnexpectedRedirect extends RuntimeException {}
}
```

**Explanation:**

- `@Qualifier("partnerWebClient")` selects the `WebClient` for the right partner. The destination check filter runs before the request hits the network; `followRedirect(false)` blocks automatic redirection to another host.
- `tokenForOrdersRead()` is an abstract contract on the token provider, **not a built-in Spring method**. It can be implemented using a Spring Security OAuth2 authorized-client manager suited to your environment (servlet or reactive). Tokens must never be hardcoded.
- `headers.setBearerAuth(token)` attaches the token to this specific request. Retry is placed **inside** `flatMap`, so attempts for the same call reuse the token fetched for that call. A 401 is excluded from the retry filter; if token refresh on 401 is required, build a dedicated branch limited to a single refresh attempt.
- `releaseBody()` releases the response body of 3xx/429/502/503/504 responses when mapping them to exceptions. Never include bodies or tokens in exceptions.
- `retryWhen` catches only `RetryablePartnerResponse`. Other errors, including 400/401/403, redirects, and timeouts, are not retried by this policy.
- `timeout(Duration.ofSeconds(5))` sits **after** the retry chain to bound the total duration of token retrieval, HTTP calls, and backoff. The 2-second limit in connector config is the per-request response timeout; it does not mean the entire flow finishes within 2 seconds.

This is an **intentionally conservative policy**: for example, it does not retry connection or timeout errors because safety cannot be inferred for every disconnect. In production, you may expand the exception filter once pre-send errors are separated and the idempotency contract guarantees safety. Handle `Retry-After` for 429/503 and coordinate with overall deadlines if required by the partner; the snippet illustrates fixed internal backoff.

## 6. Why Redirects, Absolute URLs, and Retries Often Cause Surprises

### Scenario A: An Absolute URL Bypasses Base URL

```java
WebClient client = WebClient.builder()
    .baseUrl("https://partner-api.example.net")
    .build();

// Avoid: can send the request to an input-controlled host.
client.get().uri("https://attacker.example.org/collect").retrieve();
```

`baseUrl` does not guarantee every request is forced to `partner-api.example.net`. If a token is configured at the client level, misrouted requests are especially dangerous. The solution is business APIs accepting IDs instead of URLs, destination-checking filters, and egress policies.

### Scenario B: Server Returns 302 to an Unknown Host

```text
GET https://partner-api.example.net/v1/orders/42
Authorization: Bearer [redacted]

HTTP/1.1 302 Found
Location: https://untrusted.example.org/receive
```

Do not assume a library will always strip `Authorization` on cross-host redirects, because behavior depends on the client, configuration, and version. In our example, redirects are disabled at the connector, and 3xx responses become `UnexpectedRedirect` without retrying. If the system genuinely must follow redirects (such as fetching assets from a CDN), maintain an allowlist for *each final destination*, rules to strip credentials on origin changes, and tests against a controlled server.

### Scenario C: Retries Mask an Already-Succeeded Operation

```text
POST /payments  → server records payment successfully
               ← connection drops before client receives 201
retry POST      → server creates a second payment (unless deduplicated)
```

For workflows involving databases or brokers, rolling back a local DB transaction **does not automatically roll back** a completed downstream HTTP call. Specify an idempotency key in the contract, persist processing markers, or use outbox/inbox and deduplication as needed. Consumer retries must also respect the same key and limits so an already-executed request is not re-queued infinitely.

## 7. Logs, Traces, and Metrics: Observability Without Leaking Secrets

Observability aims to tell you **which API**, **how many attempts**, **why it failed**, **how long it took**, and **whether budget was exceeded**. You do not need to store credentials or full request payloads to answer those questions.

**Safe to log:** logical target name (`partner_orders_api`), operation (`getOrder`), HTTP method, status, error category, attempt count, duration, a secret-free correlation ID, and circuit breaker/rate limit outcomes.

**Never log:** `Authorization`, `Cookie`, `Set-Cookie`, API keys, refresh tokens, token responses, URLs containing credentials, sensitive bodies, raw query strings with personal data, or stack traces with dumped response bodies.

Example metric with bounded cardinality:

```text
integration.outbound.requests{
  target="partner_orders_api",
  operation="getOrder",
  result="retry_exhausted"
}
```

Avoid using order IDs, access tokens, dynamic hosts, or full URLs as metric tags. When enabling Reactor Netty wiretap, request/response logging, or HTTP tracing, verify that sensitive headers and bodies are redacted; never enable body logging by default in production. Redaction rules must apply during retries, exceptions, and automatic header collection by monitoring libraries.

A useful log entry looks like: `downstream=partner_orders_api operation=getOrder attempt=2 status=503 duration_ms=210`. It supports operational investigation without granting log readers credentials to call the partner API.

## 8. Testing Security and Behavior with a Mock HTTP Server

You can use `MockWebServer`, WireMock, or an equivalent mock HTTP server. Assert the actual requests received on each server, not just the thrown exception types. A minimal test suite:

| Test Case | Setup | Assertion |
| --- | --- | --- |
| Bounded retry | Server returns 503, 503, then 200 | Exactly three GETs and returns the DTO; if always 503, stops after three attempts |
| No retry on auth errors | Server returns 401 or 403 | Only one GET; does not resend the stale token |
| Block redirects | Trusted server returns 302 with `Location` pointing to another mock server | Zero requests hit the second server; token never appears there |
| Block absolute URL | Attempt calling an out-of-allowlist host through the `WebClient` with destination filter | Rejected before connecting; unknown mock server receives 0 requests |
| Input validation | `orderId` is `../admin`, a URL, overly long, or contains disallowed characters | No request created; returns validation error |
| No blind POST retry | Mock server processes POST then drops connection | Does not repeat the operation unless idempotency contract is designed and tested |
| Scoped tokens | Two mock APIs have different tokens/scopes | API A's token never appears at API B |
| No log leaks | Enable the deployment logging/tracing configuration | Verify logs and traces do not contain the dummy token string |
| Overall deadline | Mock server intentionally stalls across attempts | Call stops within overall budget; no infinite retries |
| Coordinated retries | Simulate both gateway and consumer having retries | Total attempts stay within end-to-end cap |

When running tests against a mock server, configure the allowed host/port **specifically for test** while keeping the same destination validation mechanism active. Never disable the filter in tests just to make requests pass: doing so leaves production security boundaries unproven.

For behaviors harder to simulate—such as DNS changes, proxies, or redirect chains—add integration tests in an isolated network environment. Tests should also verify that retry error messages do not include tokens and that broker events are not replayed when downstream already succeeded.

## 9. Checklist for Putting WebClient into Integration Flows

- [ ] Target URLs are explicitly configured/allowed; business methods do not accept arbitrary URLs.
- [ ] HTTPS only to allowed hosts and ports; automatic redirects are disabled or strictly validated per hop.
- [ ] Tokens carry partner-appropriate audience/scope and are attached per request; refresh policy exists and tokens are never logged.
- [ ] User access tokens are never forwarded downstream without proper delegation design.
- [ ] Retry policy explicitly lists allowed statuses/exceptions; 401/403, redirects, and validation errors are excluded from automatic retry.
- [ ] Attempt caps, backoff, jitter, overall deadline, and `Retry-After` handling are configured.
- [ ] Write operations establish an idempotency/deduplication contract before allowing retries on uncertain outcomes.
- [ ] Logs, metrics, and traces use logical downstream names; masking is active and tested against token leaks.
- [ ] Tests include at least one disallowed mock host to verify zero requests or tokens reach it.

### Self-Check Questions

1. Why does `baseUrl("https://api.example")` not guarantee every URI passed to `WebClient` uses that host?
2. If downstream committed a transaction but the client timed out, what bug can retrying a POST cause? What contract prevents it?
3. How many HTTP attempts does `Retry.backoff(2, ...)` produce at most? What changes if `retryWhen` wraps an outer chain that also publishes events?
4. Why must 401 and 403 be separated from the 429/502/503/504 group?
5. How can you prove a token is neither forwarded to the host in a `Location` header nor printed in logs across attempts?

**Remember:** A `WebClient` is safe in an integration system when each request has a **trusted destination**, **properly scoped credentials**, and **conditional retry permissions**. These three boundaries must be enforced through configuration, code, network policy, and tests rather than relying on HTTP client defaults.
