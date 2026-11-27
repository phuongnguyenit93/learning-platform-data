# Rate Limiting, Quotas, and Protecting Public Endpoints

A serverless HTTP endpoint can be called from browsers, mobile apps, partners, or automated systems on the internet. Once an endpoint is public, request volume and usage patterns are no longer fully under the development team's control. A buggy client can send requests continuously; one account can monopolize processing capacity; bots can probe endpoints; or a webhook can be delivered repeatedly.

Rate limiting, quotas, and layered protections help control traffic, shield downstream services, and keep costs within expected bounds. For Java functions, place limits at the right layers: edge or API gateway to drop traffic before functions execute, application layer to enforce per-user/tenant policies, and concurrency limits to protect databases and downstream dependencies.

## 1. Distinguishing Rate Limit, Burst, Concurrency, and Quota

These terms are related yet describe different constraints:

| Concept | Controls | Illustrative Example |
|---|---|---|
| Rate limit | Number of requests within a time interval | A client is permitted an average of 20 requests per second |
| Burst limit | Number of requests that can arrive clustered in a short interval | Allows an immediate burst of 40 requests before throttling down |
| Concurrency limit | Number of invocations or tasks running simultaneously | Allows at most 30 concurrent function executions |
| Quota | Total usage over a longer billing or time cycle | A tenant has 100,000 requests per month |
| Payload limit | Data size of a single request or message | Request body must not exceed the published limit |
| Timeout | Maximum duration allowed for a single execution | Function or service call must complete within its deadline |

Rate limits prevent a source from sending requests too fast. Burst limits allow short-term spikes while maintaining an average rate. Concurrency limits protect resources when requests are slow and overlap. Quotas govern cumulative consumption per day, month, or billing period.

One limit cannot substitute for another. A client sending 10 requests per second where each request takes 30 seconds can still create hundreds of concurrent invocations. Conversely, a low concurrency limit can cause requests to queue or throttle even when the send rate stays below the rate limit.

## 2. Choosing the Scope for Limits

A public endpoint typically needs multiple layers of limits:

- **System-wide:** protects the API gateway, functions, and downstream dependencies from sudden traffic spikes.
- **By IP or network range:** curbs bots and unauthenticated clients.
- **By authenticated identity:** applies per user, service account, API client, or tenant.
- **By endpoint and method:** resource-heavy search endpoints may need tighter limits than status-read endpoints.
- **By business operation:** limits OTP sends, report generation, payment attempts, or sensitive actions.
- **By usage cycle:** daily/monthly quotas tied to service tiers or contracts.

Limiting by IP alone is usually insufficient. Many users may share a single NAT, proxy, or corporate network and get throttled unfairly. Botnets can distribute requests across many IPs. IP addresses also fail to identify tenants or business permissions.

Conversely, limiting by API key alone is also insufficient. Keys can leak or be shared. Combine aggregate edge limits, post-authentication identity limits, and operation-level limits in the application layer.

In multi-tenant systems, bind every request to a tenant verified from a token or trusted identity. Never take a client-supplied tenant ID from a header or query parameter and use it directly as a quota key. If a client is allowed to select a tenant, verify access rights to that tenant before applying quotas.

## 3. Common Rate Limiting Algorithms

### 3.1. Fixed Window Counter

Divides time into fixed windows, such as per minute. Each request increments the counter for the current window. When the counter exceeds the threshold, requests are rejected.

The advantage is simplicity, easy implementation via TTL-backed counters, and low overhead. The downside is boundary bursting. If a client sends requests right before the end of a minute and immediately resumes at the start of the next minute, it can achieve nearly double the allowed rate within a very short span.

### 3.2. Sliding Window Log

Stores the timestamp of each request within the recent window. When a new request arrives, expired timestamps are pruned and the remaining entries are counted.

This controls rates more accurately but requires storing many timestamps, increasing memory usage and operations. Under high traffic, logging every request timestamp can become costly.

### 3.3. Sliding Window Counter

Combines the counters of the current window and the previous window, weighted by elapsed time in the current window. This smooths boundary spikes without storing every individual request.

This is an approximation. It is often a good fit when smoother limiting than fixed windows is needed while keeping state compact.

### 3.4. Token Bucket

A bucket holds tokens replenished at a steady rate up to a maximum capacity. Each request consumes one or more tokens. If insufficient tokens remain, the request is rejected or delayed.

- Refill rate determines the sustained average rate allowed.
- Bucket capacity determines the maximum burst.
- Cost per request can vary with endpoint heaviness.

Token buckets suit APIs that need to permit short bursts while controlling long-term rates. Higher costs can be assigned to heavy queries or report-generation operations.

### 3.5. Leaky Bucket

Requests enter a queue and are processed at a steady output rate. The queue has bounded capacity; when full, new requests are rejected.

This smooths traffic and protects downstream services, though it can add latency. For synchronous HTTP, queue wait time must remain within client and gateway deadlines. If work cannot complete within that window, move to an asynchronous job model.

| Algorithm | Burst Behavior | State Required | Characteristics |
|---|---|---|---|
| Fixed window | Can spike at window boundaries | One counter per window | Simple, easy to implement |
| Sliding log | Accurate control within window | Timestamp per request | High memory and operation cost |
| Sliding counter | Smoother than fixed window | Counters for a few windows | Approximate, compact state |
| Token bucket | Allows bounded bursts | Token count and last update time | Flexible for APIs |
| Leaky bucket | Smooths traffic | Queue and processing rate | Controls output rate |

There is no single best algorithm for every endpoint. Choose based on traffic patterns, required precision, latency budget, and state storage cost.

## 4. Implementing Rate Limiting in Serverless Architectures

### 4.1. Placing Limits at the Edge or API Gateway

Public requests typically pass through a CDN, WAF, load balancer, or API gateway before reaching a Java function. Placing limits at this layer drops excess requests early, avoiding invocation costs and reducing load on downstream services.

You can configure:

- Overall API rate and burst limits.
- Limits by route, method, or stage.
- Limits by API key or client identity if supported by the gateway.
- Request size limits and timeouts.
- WAF rules to block malicious request patterns or anomalous traffic sources.

Understand the semantics of your specific service. Some gateways describe throttling as best-effort, fluctuating around thresholds across distributed nodes or concurrent requests. Throttling is also not necessarily a hard monthly quota. If contractual spend or request caps are required, maintain dedicated quota counters and usage alerts.

### 4.2. Do Not Treat API Keys as Authentication Proof

API keys are useful for identifying applications, metering usage, and applying quotas. However, bearer-style keys can be copied and used by anyone who obtains them. Never treat sending a valid API key as sufficient authorization for accessing sensitive data or operations.

Use proper authentication mechanisms such as OAuth 2.0/OIDC, JWTs verified for issuer/audience/signature, mutual TLS for certain service connections, or platform identity mechanisms. After authentication, enforce authorization per resource and tenant. API keys can supplement client classification, not replace authentication and authorization.

### 4.3. Distributed Rate Limiters Across Multiple Function Instances

A Java function can run across many execution environments. Static counters or in-memory variables are visible only within a single process. If each instance independently allows 20 requests/second, 10 instances together can allow roughly 200 requests/second.

Therefore, per-user or per-tenant limits require shared state, such as Redis, a database supporting conditional updates, or a dedicated rate limiting service. Checking and consuming quota must be atomic so two concurrent invocations do not read the same stale count and both allow requests through.

~~~mermaid
flowchart LR
    C["Clients"] --> E["CDN / WAF / API Gateway"]
    E --> A["Auth and authorization"]
    A --> R["Shared rate limiter"]
    R -->|Allowed| F["Java Function"]
    R -->|Limit exceeded| X["HTTP 429"]
    F --> D["Database / downstream services"]
~~~

An atomic consume operation can take the limit key, current timestamp, refill rate, capacity, and cost. It returns an allow/deny decision along with remaining tokens and when to retry. With Redis, a Lua script can read, compute, and write state in one atomic step. With databases, use conditional updates or serializable/conditional transactions to avoid lost updates.

When using Redis, define TTLs, key expiration handling, clock source, and failure behavior. Do not create keys for arbitrary uncontrolled client inputs, as attackers can explode cardinality and storage costs. Limiter keys should be based on verified identities or gateway-normalized IP addresses.

### 4.4. Java Should Depend on a Clear Rate Limiter Contract

Application code should depend on an interface so implementations can vary by environment. The example below illustrates how a handler receives a decision from a shared limiter. Token storage and atomic consumption are implemented by an adapter for Redis or a quota service; never substitute a static counter when running across multiple instances.

~~~java
public interface RateLimiter {
    LimitDecision consume(String key, int cost);
}

public record LimitDecision(
        boolean allowed,
        long remaining,
        long retryAfterSeconds
) {}

public Response handle(Request request) {
    Principal principal = authenticate(request);
    authorize(principal, request);

    String key = "tenant:" + principal.tenantId() + ":reports";
    LimitDecision decision = rateLimiter.consume(key, 1);

    if (!decision.allowed()) {
        return Response.status(429)
                .header("Retry-After",
                        Long.toString(Math.max(1, decision.retryAfterSeconds())))
                .header("Cache-Control", "no-store")
                .body("Rate limit exceeded")
                .build();
    }

    return createReport(request);
}
~~~

This is an illustrative structure; `Request`, `Response`, and `Principal` types depend on the framework. In real deployments, the limiter must resolve per-endpoint policies, handle store failures, and emit metrics. Never execute report creation before the rate limit decision allows it.

If operations have varying resource costs, pass an appropriate cost. For instance, metadata reads cost 1, complex searches cost 5, and large report generation costs 20. Cost pricing should be grounded in resource measurements and clearly documented in API policies when visible to users.

## 5. Handling Rate-Limited Requests

When a client exceeds a rate limit, HTTP 429 Too Many Requests is the appropriate response. Include a `Retry-After` header indicating the minimum wait before retrying. Where appropriate, also expose limit, remaining count, and reset timing per your published API contract.

Example:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 5
Cache-Control: no-store
Content-Type: application/json

{
  "error": "rate_limit_exceeded",
  "message": "Too many requests. Retry later."
}
~~~

Do not return 500 for intentionally throttled requests. Use 401 when credentials are missing or invalid; 403 when identity is valid but lacks permission; 413 when payloads are too large; 429 when traffic policies are exceeded; and 503 when the service is temporarily unable to serve due to overload or dependency failure.

Clients should honor `Retry-After`, apply exponential backoff with jitter, and cap retry attempts. If every client retries at the exact same moment, they can create a fresh load spike as soon as the limiter window opens. For non-idempotent requests, retries require an idempotency key or a status-lookup mechanism before resending.

Do not expose reset timings or sensitive internal details if doing so helps attackers infer infrastructure structure. Error payloads should give clients enough to act without leaking detailed internal policies.

## 6. Daily, Monthly, and Per-Tenant Quotas

Quotas typically express cumulative usage over a period. For example, a tenant might have monthly caps on requests, reports generated, processing minutes, or bytes transferred.

A quota model should clearly define:

- Subject: user, tenant, API client, or billing account.
- Metric: requests, jobs, bytes, processing duration, or business units.
- Period: minute, hour, day, month, or contract cycle.
- Reset timing: UTC or contract timezone.
- Exhaustion behavior: reject, prompt upgrade, or queue until next period.
- Accounting rules for failed requests, retries, and canceled operations.

Monthly quotas must not be implemented with only an in-memory counter. Persist them durably and update atomically. If quota consumption ties to a business transaction, design transactions or ledgers to avoid deducting quota twice when a request retries.

You can separate hard quotas from warning thresholds. Hard quotas block operations once the allocation is spent. Warning thresholds such as 70%, 85%, or 95% alert tenant owners and operations early. These percentages are examples; choose thresholds based on lead time needed to raise limits or resolve incidents.

If quotas synchronize across multiple regions, define the consistency level. Replication lag can allow two regions together to exceed the global quota. For hard caps, you can partition budgets per region or use a consistent coordinator, trading off latency and availability if the coordinating region degrades.

## 7. Multi-Layered Protection for Public Endpoints

Rate limiting is one layer of defense. Public endpoints also require the following measures.

### 7.1. TLS, Authentication, and Authorization

- Serve exclusively over HTTPS.
- Verify tokens for issuer, audience, signature, expiration, and allowed algorithms.
- Enforce per-resource permissions, not merely that a user is signed in.
- Never trust client-sent tenant IDs, roles, or user IDs unless derived from a verified identity.
- Restrict service account permissions following least privilege.
- Rotate secrets and revoke compromised credentials.

CORS is solely a browser policy governing which web pages can read responses. CORS does not authenticate callers and does not block curl, bots, or other servers from calling endpoints. Never use CORS as a substitute for authorization.

### 7.2. Input Validation and Resource Bounds

- Bound body size, element counts, JSON nesting depth, and string lengths.
- Validate data types, ranges, and formats before calling downstream services.
- Use allowlists for values like sort fields, filters, or operation names.
- Set connect timeouts, read timeouts, and overall deadlines.
- Bound thread pools, connection pools, batch sizes, and concurrent tasks.
- Never let clients arbitrarily choose URLs the function fetches if that could enable SSRF.
- Never log tokens, secrets, payment details, or full sensitive payloads.

Validation at the function layer remains necessary even when the gateway performs schema validation, because not all triggers flow through the same gateway and clients can bypass UI layers.

### 7.3. WAF, Bots, and Traffic Sources

A WAF or edge protection layer can block common attack patterns, automated scraping signals, or anomalous traffic before the function is invoked. IP allowlist rules are helpful for partner webhooks with stable IP ranges, though IPs can change and do not prove request payload authenticity. Combine IP filtering with signature verification and authentication.

When an endpoint sits behind proxies, trust headers like `X-Forwarded-For` or `Forwarded` only when populated by trusted proxies and when the gateway strips client-injected values. Reading client-controlled headers directly for IP identification lets attackers spoof addresses and evade rate limiters.

### 7.4. Concurrency Limits and Protecting Downstream Services

Gateway rate limits do not replace concurrency limits. A function can receive moderate request rates while each invocation runs slowly due to a database or external API. When that happens, concurrent invocations pile up and exhaust connections.

Enforce concurrency caps at the function or platform level, bound pools in Java, and apply backpressure. If a database supports only a fixed number of connections, total concurrency across all functions must stay within that capacity. Use an appropriate connection proxy/pooler, queues for background work, or fail fast under overload.

Prevent retries from amplifying outages. When a dependency fails, synchronized retries across many functions can trigger a retry storm. Use exponential backoff, jitter, retry budgets, circuit breakers, and timeouts shorter than the overall deadline.

## 8. Protecting Webhooks

Webhooks are HTTP requests sent by external systems when events occur. Webhook receiver endpoints are usually public and may receive retries, duplicates, or spoofed requests.

A secure ingestion flow:

1. Receive the raw request body and required metadata.
2. Verify the HMAC signature or provider-specified signature scheme over the exact signed bytes.
3. Check the timestamp or nonce to mitigate replay attacks.
4. Extract the event ID and check idempotency.
5. Persist the event to durable storage or a queue.
6. Return 2xx only after durable acceptance according to the webhook contract.
7. Execute business processing asynchronously with its own retry policy.

Do not parse and re-serialize JSON before verifying signatures if the provider signs the raw body. Whitespace, field ordering, or encoding changes can break signature verification.

The Java example below illustrates HMAC-SHA256 with hex-encoded signatures using `HexFormat` introduced in Java 17. Actual formats must follow the provider's documentation. The timestamp is folded into the signed data so the signature binds to time; the application must still verify the timestamp lies within an acceptable window.

~~~java
static boolean verifyWebhook(
        byte[] rawBody,
        String timestamp,
        String signatureHex,
        byte[] secret) throws GeneralSecurityException {

    Mac mac = Mac.getInstance("HmacSHA256");
    mac.init(new SecretKeySpec(secret, "HmacSHA256"));

    mac.update(timestamp.getBytes(StandardCharsets.UTF_8));
    mac.update((byte) '.');
    byte[] expected = mac.doFinal(rawBody);

    final byte[] supplied;
    try {
        supplied = HexFormat.of().parseHex(signatureHex);
    } catch (IllegalArgumentException invalidHex) {
        return false;
    }

    return MessageDigest.isEqual(expected, supplied);
}
~~~

Validate the timestamp before or after signature verification per the chosen protocol, bounding clock skew and rejecting timestamps that are too old or too far in the future. Do not rely on timestamps alone for replay protection if an event can be replayed within the allowed window. Store processed event IDs or nonces in a durable store with an appropriate TTL.

Compare signatures using constant-time functions like `MessageDigest.isEqual` rather than ordinary string comparison. Fetch secrets from a secret manager or secure configuration—never hardcode them in source code. Support key rotation by accepting both current and previous keys during a bounded transition window.

Webhook senders usually retry on non-2xx responses or timeouts. Receivers must be idempotent: the same event ID must produce business side effects only once. Use a unique constraint on event ID or an inbox table. If processing is slow, durably persist the event and return `202 Accepted`; let a worker process it afterward. Never return 2xx before the event is durably saved, or the sender will stop retrying while the system drops the event.

## 9. Failure Policies When the Rate Limiter or State Store Fails

A distributed rate limiter is a dependency. When it fails, the system needs an explicit policy:

- **Fail closed:** reject requests if quota cannot be verified. Fits high-risk operations or strict contractual quotas.
- **Bounded fail open:** allow a portion of requests when the limiter fails to preserve availability, paired with global concurrency caps, temporary edge limits, and alerts.
- **Fallback:** apply a lower local limit briefly, recognizing that aggregate limits may be exceeded across multiple instances.

There is no universal default for every API. Logins, OTP sends, payments, or expensive operations generally demand strict policies. Public read endpoints may prioritize availability if other protective layers exist.

Never silently bypass the limiter on timeout. Emit metrics for store errors, fallback decisions, requests allowed in degraded mode, and recovery time. Configure short timeouts on limiter calls so a failing dependency does not exhaust all function concurrency.

## 10. Observability and Operations

Metrics to track include:

- Request counts and rates by route, tenant, and status code.
- Counts of 429, 401, 403, 413, and 5xx responses.
- Percentage of requests blocked by WAF.
- Remaining tokens or quota utilization.
- Counts of limiter store timeouts, errors, and fallbacks.
- Function concurrency, throttling, p95/p99 duration, and timeouts.
- Connection pool usage, database latency, and dependency error rates.
- Counts of duplicate webhooks, signature failures, replay rejections, and retries.
- Cost per tenant or API client if required by billing models.

Logs should include request ID, verified tenant ID, route, limiter decision, and reason code. Avoid logging API keys, bearer tokens, webhook secrets, or full signatures. If credential investigation is needed, log a fingerprint or an identifier that cannot be reused as a credential.

Build dashboards distinguishing normal traffic, organic spikes, and attacks. A high 429 rate may confirm the limiter is working, or signal overly tight policies or misbehaving client retries. Combine metrics with user feedback and per-tenant analysis.

## 11. Testing Rate Limits and Endpoint Protections

Testing should simulate both normal load and abnormal behavior:

1. Send requests below, at, and above thresholds.
2. Send bursts across fixed-window boundaries to expose boundary spikes.
3. Send concurrent traffic across multiple function instances to verify atomic consumption.
4. Test multiple IPs under one tenant, and multiple tenants behind one NAT.
5. Test unauthenticated requests, expired tokens, wrong audiences, and unauthorized tenants.
6. Test oversized bodies, deeply nested JSON, overly long fields, and invalid content types.
7. Test limiter store timeouts, disconnects, and recovery.
8. Test slow dependencies to verify concurrency caps and backpressure.
9. Send webhooks with bad signatures, stale timestamps, duplicate event IDs, and modified bodies.
10. Test webhook sender retries when the receiver returns 5xx or times out.
11. Verify 429 responses include `Retry-After` and clients honor backoff.
12. Monitor cost under elevated request rates and when functions are throttled.

Load tests must be bounded and run in authorized environments. Use synthetic test data and cap concurrency to avoid unintentionally overloading production services or external partners.

## 12. Policy Design Workflow

You can follow this process for a new endpoint:

1. **Classify the business risk.** Determine whether the endpoint is public or internal, data sensitivity, per-request cost, and abuse impact.
2. **Establish identity.** Choose authentication, trusted tenant ID sources, and authorization rules.
3. **Measure workload.** Profile duration, CPU, memory, connections, and downstream load to estimate capacity.
4. **Apply layered limits.** Configure edge rate/burst limits, tenant quotas, concurrency caps, payload sizes, and timeouts.
5. **Choose algorithm and state store.** Select fixed/sliding window or token bucket; ensure atomic updates across instances.
6. **Design responses.** Specify status codes, `Retry-After`, quota errors, and client retry guidance.
7. **Design degradation.** Choose fail-open, fail-closed, or fallback behavior when limiters/dependencies fail.
8. **Test and observe.** Test bursts, concurrency, duplicates, replays, and dependency failures; build dashboards and alerts.

A secure public endpoint is not just a single requests-per-second number. It requires explicit identity- and business-aware policies, consistent enforcement across instances, concurrency caps protecting dependencies, and predictable retry handling.

## 13. Self-Check Questions

- How do rate limits differ from concurrency limits and monthly quotas?
- Why is a Java static counter insufficient to limit an entire function when scaling out?
- Which parameters control average rate and burst size in a token bucket?
- Why do API keys not replace authentication and authorization?
- What information should accompany HTTP 429 so clients retry properly?
- Why are limits needed at both the API gateway and application layers?
- Does CORS stop non-browser clients from calling an endpoint?
- Why must webhooks verify signatures over raw bodies and enforce replay protection?
- What are the trade-offs between fail-open and fail-closed when the rate limiter store fails?
- How can a webhook delivered multiple times avoid creating duplicate business side effects?

Understanding rate limiting, quotas, and endpoint protection enables Java serverless developers to govern traffic from the edge all the way through downstream service calls. Limits should be calibrated against real workloads, bound to trusted identities, and tested under concurrent invocations.
