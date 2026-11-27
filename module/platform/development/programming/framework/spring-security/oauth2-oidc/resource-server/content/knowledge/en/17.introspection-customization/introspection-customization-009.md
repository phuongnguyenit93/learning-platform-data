# Bounded Retries, Overload, and Error Policies That Never Bypass Verification

In a **Spring Security OAuth 2.0/OIDC Resource Server**, an API may receive an **opaque access token** and call the **Authorization Server** via OAuth 2.0 Token Introspection (RFC 7662) to determine whether the token is active or revoked, along with attributes such as `scope`, `sub`, `aud`, and `exp`. This allows the Resource Server to rely on a centralized source of truth, yet introduces an operational dependency: if the introspection endpoint is slow, overloaded, or unreachable, Bearer token authentication can be affected across every related request.

The solution is not **infinite retries** or **temporarily skipping verification so the API keeps returning data**. You need an explicit policy covering **timeouts, bounded retries, load shedding, circuit breakers, caching, and error classification**. Regardless of how heavily a policy prioritizes availability, a Resource Server must never turn an **unverified** token into an authenticated principal.

This lesson covers **"Bounded Retries, Overload, and Error Policies That Never Bypass Verification"** in the **Introspection Customization** chapter of the **Spring Security OAuth 2.0 OIDC Resource Server** module. It progresses from introspection mechanics, error models, and resilience design to Spring Security Servlet/WebFlux implementation examples and overload testing.

> The primary scope is OAuth 2.0 **Bearer access tokens**. Even though Spring Security's configuration method is named `opaqueToken()`, the introspection authentication path can also be used for **JWT access tokens** when supported by the Authorization Server. Whether a token is formatted as a JWT or opaque does not alter the rule of **never accepting a token without trustworthy verification evidence**.

## 1. Introspection Is Part of the Authentication Path

The client calls the Orders API:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

A Resource Server relying on introspection typically processes the request along this chain:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as Spring Security Resource Server
    participant A as Authorization Server
    C->>R: GET /api/orders/42 + Bearer token
    R->>A: POST /introspect (token, client authentication)
    A-->>R: HTTP 200 + active=true, scope, aud, exp...
    R->>R: Validate attributes + create principal
    R->>R: HTTP/method/domain authorization
    R-->>C: API response if permitted
~~~

Introspection request per RFC 7662:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <INTROSPECTION_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<ACCESS_TOKEN>&token_type_hint=access_token
~~~

Example response when the token is active:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "scope": "orders.read",
  "sub": "user-123",
  "client_id": "orders-web",
  "aud": "orders-api",
  "iss": "https://login.example.test/realms/company",
  "exp": 1924992000
}
~~~

When the token is not recognized by the Authorization Server:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": false
}
~~~

**HTTP 200 does not mean the token is valid**: you must read `active`. Conversely, an HTTP 503 or timeout when calling introspection **does not prove the token is invalid**; it indicates the Resource Server **could not obtain a trustworthy verification result**.

### 1.1. Three Logical Outcomes to Distinguish

| Outcome | Evidence | Request Decision |
|---|---|---|
| **VALID** | Valid introspection, `active=true`, and issuer/audience/expiry/profile conditions pass | May create `Authentication` and proceed to authorization |
| **INVALID** | Valid introspection, `active=false`, or token fails mandatory contract conditions | Do not produce successful authentication |
| **UNKNOWN / UNAVAILABLE** | Timeout, network error, 5xx, 429, unprocessable response, unverified source | Do not produce successful authentication; classify infrastructure error separately |

Key point: **UNKNOWN must never be treated as VALID**. Policy may return different error codes to callers or use a **previously verified** result within an approved cache window, yet must never return success merely because the Authorization Server failed temporarily.

### 1.2. Distinguishing Authentication from Authorization

~~~text
Client Bearer token
     |
     v
OpaqueTokenIntrospector
     |
     +-- active=false / cannot verify ---> NOT authenticated
     |
     v
OAuth2AuthenticatedPrincipal + GrantedAuthority
     |
     v
HTTP authorization: SCOPE_orders.read?
     |
     v
Domain authorization: does order belong to subject/tenant?
~~~

`active=true` is only one step. The Resource Server must still enforce appropriate policies for **issuer, audience, token type, expiration, scopes, and resource permissions**. Never drop mandatory constraints just to check `active` during overload.

## 2. Retry the Right Errors: Classify Before Retrying

A retry helps when a **transient** error is likely to clear after a short interval. It causes harm when repeating a request whose outcome is already settled, or when the entire Authorization Server is overloaded.

### 2.1. Policy Table by Outcome Type

| Introspection Signal | Common Meaning | Should Auto-Retry? | Authentication Decision |
|---|---|---|---|
| HTTP 200, `active=true`, valid metadata | Token recognized | **No** | Authenticate and apply remaining policies |
| HTTP 200, `active=false` | Token inactive per AS | **No** | Reject token |
| HTTP 400 due to malformed/missing parameters | Error in client calling introspection | **No** before fixing config/code | Do not authenticate |
| HTTP 401 due to wrong introspection client credentials | Wrong infrastructure credentials/config | **No** | Do not authenticate; alert on config |
| HTTP 403 due to missing introspection permission | Invalid introspection caller policy | **No**, unless policy changes validly | Do not authenticate; alert |
| HTTP 404 wrong endpoint URI | Endpoint missing or misconfigured | **No** | Do not authenticate |
| HTTP 429 Too Many Requests | AS requests load reduction | **Very restricted**, only within quota/budget and matching retry guidance | Never let pass |
| HTTP 500/502/503/504 | Temporary recoverable server/proxy error | May retry **a small max count** with backoff/jitter | Never let pass |
| Connect timeout / TLS handshake timeout | Network or AS unreachable | May retry boundedly if contract allows and deadline remains | Never let pass |
| Read timeout | Unknown whether upstream processed the request | Retry only if operation semantics are confirmed safe to repeat and deadline remains | Never let pass |
| DNS / invalid TLS certificate | Trust/transport error | Usually **no** immediate retry; alert | Do not authenticate |
| Malformed JSON schema / missing `active` | Wrong endpoint/protocol | **No** futile retries without knowing root cause | Do not authenticate |
| Introspection returns `active=true` missing required `aud` | Lacks evidence intended for API | **No**; fix contract/config | Do not authenticate |

**Never retry based solely on a generic exception.** Some libraries wrap `active=false`, HTTP errors, deserialization failures, and timeouts in exceptions from the same family. To retry safely, classify at the **HTTP/transport layer** or via normalized domain exceptions before attaching retry logic.

### 2.2. Why Never Retry `active=false`?

`active=false` is a **valid verification result** from the Authorization Server, not an "unsuccessful attempt." Retrying it can:

- Slow down responses to clients presenting bad tokens.
- Add load to the Authorization Server right when it needs to serve valid tokens.
- Aid token guessing / resource-exhaustion DoS.
- Mask an actually expired or revoked token.

For inactive tokens, the Resource Server must reject per policy **without placing them into a retry queue**.

### 2.3. Why HTTP 401 from Introspection Differs from HTTP 401 Sent to the Client

If the Authorization Server returns:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="introspection"
~~~

the issue is usually that **the Resource Server could not authenticate itself to introspection**, such as a wrong or rotated client secret. This is not proof that the user's token is `active=false`.

The Resource Server must not let the request proceed; meanwhile, alert on **AS config/connection failure** rather than labeling every client as having bad tokens. The client response may be an authentication or service error depending on exception handling, yet sensitive data like the client secret or Basic header must never be exposed.

### 2.4. Status 429 and `Retry-After`

An AS or gateway may return:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 2
~~~

The `Retry-After` value is a hint for when to try again, **not a command forcing the current request to wait**. Retry only if the wait plus the next attempt **fit within the request's total deadline** and load policy. If `Retry-After` exceeds the budget, stop rather than holding threads/connections for a request guaranteed to time out.

`Retry-After` can be seconds or an HTTP-date; implementations must parse safely and reject negative, huge, or malformed values. Never treat an arbitrary header as an unbounded `sleep`.

## 3. Bounded Retries: Three Simultaneous Boundaries

To prevent a retry storm, "retry 3 times" is not enough. A safe policy needs **three limits**:

1. **Maximum attempts**: includes the initial call plus retries.
2. **Maximum total duration**: deadline for *the entire introspection process*, not just each individual HTTP call timeout.
3. **Concurrency / system-wide retry budget**: bounds pressure on the AS when many clients fail together.

Illustrative contract example:

~~~text
Per-attempt connection timeout:      200 ms
Per-attempt response timeout:        350 ms
Max total introspection time:        900 ms
Max attempts:                        2 (1 initial + 1 retry)
Backoff:                             random 50..150 ms
Retryable:                           select 502/503/504, known transient I/O
Never retry:                         active=false, 400/401/403/404
Retry on 429:                        normally no in-request retry,
                                     unless Retry-After fits budget and
                                     rate-limit policy explicitly allows
~~~

**These numbers are examples**, not defaults of Spring Security, Nimbus, RFC 7662, or mandatory SLAs. Real values depend on AS p95/p99, request SLOs, thread/connection pools, and expected traffic.

### 3.1. How Many HTTP Calls Does "2 Attempts" Mean?

Avoid ambiguous phrasing like "retry 2 times":

~~~text
Maximum attempts = 2:
    attempt #1  → initial request
    attempt #2  → one retry if appropriate
~~~

Saying "2 retries" is often read as **3 attempts**. Name configuration fields precisely like `maxAttempts` and document clearly that it **includes the initial attempt**.

### 3.2. Total Deadline Matters More Than Per-Attempt Timeout Sum

If each HTTP timeout is 2 seconds and up to 3 attempts are allowed, a single request can hold resources for 6 seconds **before even counting backoff**. Under high traffic, this fills queues and inflates latency across all endpoints.

With a 900 ms total deadline:

~~~text
0 ms      request arrives at Resource Server
0–300 ms  attempt #1
300–400   jittered backoff
400–750   attempt #2
750–900   margin for processing/cleanup
~~~

If attempt #1 already consumed 800 ms, do not retry for another 350 ms just because "attempts remain." Retries are permitted only while **both deadline and resources remain for a valid next attempt**.

### 3.3. Backoff and Jitter Reduce Synchronized Retries

An illustrative formula:

~~~text
baseDelay(attempt) = min(maxDelay, initialDelay × 2^(attempt-1))
actualDelay        = random(0, baseDelay(attempt))
~~~

Jitter keeps multiple Resource Server instances from **retrying in lockstep at the exact same instant**. However, jitter **does not replace bulkheads/rate limits**: when 100,000 requests await introspection, even randomized backoff can produce aggregate load exceeding AS capacity.

### 3.4. Retrying POST Introspection: Verify Semantics

RFC 7662 uses HTTP POST; introspection is inherently **a query for information**, not an issuance or revocation command. In many implementations, repeating introspection does not mutate token state. Still, **never assume every HTTP POST is safe to retry**: the AS may write audit logs, enforce rate limits, bill calls, or run custom logic.

Before retrying a read timeout, confirm **the specific introspection endpoint** supports repeated requests without unintended side effects. Above all, **never reuse the same retry policy** for token issuance, refresh-token grants, or token revocation merely because they are also HTTP POSTs.

## 4. Overload and Amplification Effects

A system with 20 Resource Server instances, each receiving 100 requests/s needing introspection, can generate:

~~~text
20 instances × 100 authenticated requests/s
= 2,000 introspection requests/s
~~~

If each request permits **3 attempts**, a 503 outage can push potential demand to:

~~~text
2,000 requests/s × 3 attempts
= 6,000 outbound attempts/s
~~~

This is **potential attempt load**, not exact completions: it also depends on deadlines, concurrency, queues, rate limits, and retry timing. It illustrates why unconditional retries can **worsen** an AS outage while exhausting the Resource Server's own thread pools.

### 4.1. Retry Storm

~~~mermaid
flowchart TD
    U["Inbound API request rate rises"] --> R["Resource Server instances"]
    R --> A["Authorization Server introspection"]
    A -->|"timeout/503"| B["Unbounded automatic retries"]
    B -->|"More HTTP calls"| A
    B -->|"Holds threads/connections"| R
    R --> C["Long queues, request timeouts, cascading failures"]
~~~

Never treat retries as "keep calling until the AS works." When upstream is overloaded, **reducing pressure** is a prerequisite for recovery.

### 4.2. Little's Law and Waiting Requests

By rough approximation:

~~~text
inFlight ≈ arrivalRate × averageTimeInSystem
~~~

If a service receives 500 requests/s and introspection averages 0.1 seconds, roughly 50 requests are in flight. When the AS slows to 2 seconds, in-flight requests can climb to roughly 1,000 unless concurrency is capped. This is an **illustrative model** of load vs. latency, not a capacity guarantee.

Consequently, you need **bulkheads/concurrency limits**, bounded queues, proper timeouts, and pool/queue saturation visibility.

### 4.3. Distinguishing Isolated Glitches from Widespread Outages

| Symptom | Appropriate Response |
|---|---|
| Occasional 503s while p95 latency stays normal | May attempt one short jittered retry |
| High 503 rate across many instances | Throttle/disable retries, trip circuit breaker, add no extra load |
| Continuous HTTP 429s | Respect rate limits, cut concurrency; do not pile retries onto the AS |
| Widespread connect timeouts | Treat as network/upstream incident; never hold requests indefinitely |
| Wrong client credentials | Configuration/secret incident; do not keep retrying |
| Spike in `active=false` | Likely many invalid tokens; do not retry, inspect issuer and abuse |

## 5. Timeouts Must Tie to the Request Budget

An API request involves several stages:

~~~text
Gateway → TLS → Spring Security introspection → Controller
        → Database → Downstream service → JSON response
~~~

If the total request SLO is 2 seconds and introspection consumes 1.9 seconds, the controller/service has almost nothing left. Allocate budgets deliberately:

~~~text
End-to-end request budget:             2,000 ms
Introspection total budget:              500 ms
Business logic + DB/downstream budget: 1,000 ms
Gateway/serialization/other:             500 ms
~~~

These numbers illustrate budgeting rather than mandatory proportions. If the Authorization Server already takes 500 ms at p99 normally, reconcile load design, SLAs, caching, and real latency before setting limits.

### 5.1. Different Kinds of Timeouts

| Type | Meaning | If Omitted |
|---|---|---|
| Connection timeout | Bounds opening a network connection | Holds requests when upstream is unreachable |
| TLS handshake timeout | Bounds TLS negotiation | Hangs in TLS/network misconfigurations |
| Response/read timeout | Bounds waiting for data from the endpoint | Waits forever for the AS to respond |
| Connection pool acquisition timeout | Bounds waiting for a connection from the pool | Application queues grow unbounded |
| **Total operation deadline** | Bounds all attempts + backoff + overhead | Retries stretch past the HTTP request SLO |

Do not confuse a single `RestClient`/`WebClient` call timeout with the **overall deadline**. In WebFlux, a Reactor `timeout` wrapping the whole publisher can act as an extra safeguard, provided resources/connections are cancelled and exceptions classified properly.

### 5.2. Timeout Does Not Mean Invalid Token

When introspection times out:

~~~text
Right:
    UNKNOWN / UNAVAILABLE
    → create no principal
    → apply appropriate error policy
    → record upstream_timeout metric

Wrong:
    UNKNOWN
    → assume active=true
    → create fake principal and authorities
~~~

The Resource Server may use a **previously verified** cached result if permitted by system policy and still within validity/freshness bounds, which is fundamentally different from skipping verification.

## 6. Error Policy: Fail Closed Does Not Mean Returning One Status Always

**Fail closed** in authentication means: **without trustworthy token verification evidence, the system grants no access to the request**. This does not force every rejection cause to return the exact same 401 code to clients, nor does it permit exposing internal introspection details.

### 6.1. Distinguishing INVALID and UNAVAILABLE at the API Boundary

One way to design responses:

| Internal Situation | Authentication State | Suggested Contract HTTP Response |
|---|---|---|
| No Bearer token on a protected endpoint | Unauthenticated | 401 with appropriate Bearer challenge |
| `active=false` | Invalid token | 401, `invalid_token` |
| Authenticated token lacking scope | Auth succeeded, authorization failed | 403, `insufficient_scope` if appropriate |
| Introspection timeout / AS 503, no permitted cache | Unable to verify | May return 503/502 or infrastructure-appropriate error; **never return protected data** |
| Introspection caller gets 401 due to wrong client secret | Resource Server config error | Alert operations; block request, leak no credentials |
| Circuit breaker open | Introspection unavailable during window | Reject before calling AS; optionally 503 per design |
| Malformed schema / missing `active` | No valid verification result | Create no principal; report internal protocol/AS error |

The exact choice between 401 and 503 for infrastructure errors depends on exception mapping and **API contract**. Spring Security and libraries may default to exceptions producing different statuses from this example. What must stay invariant is: **never treat timeout/503/circuit-open as `active=true`**.

### 6.2. Three Response Examples

Invalid token per AS:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
~~~

Authenticated principal lacking authority:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
Cache-Control: no-store
~~~

Introspection infrastructure unavailable, when the system chooses to surface a service error:

~~~http
HTTP/1.1 503 Service Unavailable
Cache-Control: no-store
Content-Type: application/json

{
  "code": "AUTHENTICATION_SERVICE_UNAVAILABLE",
  "message": "Authentication cannot be completed."
}
~~~

These are **illustrative response policies**, not responses emitted automatically by every `OpaqueTokenIntrospector` setup. If customizing handlers to return 503, verify that the error still **halts the request** at the security boundary and is never caught by a permissive fallback.

Never return fields such as:

~~~json
{
  "token": "<ACCESS_TOKEN>",
  "clientSecret": "<INTROSPECTION_SECRET>",
  "introspectionErrorBody": "<RAW_INTERNAL_RESPONSE>"
}
~~~

### 6.3. Dangerous Anti-Pattern: Fail Open

~~~java
// ANTI-PATTERN: never create a principal when introspection fails.
try {
    return delegate.introspect(token);
} catch (Exception ex) {
    return new DefaultOAuth2AuthenticatedPrincipal(
        "unknown",
        Map.of("active", true),
        List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
    );
}
~~~

This grants read permission to an **unverified** token solely due to a network/AS error. An attacker can exploit degraded periods to pass any arbitrary Bearer string, turning an availability issue into **authentication bypass**.

A similar mistake:

~~~java
// ANTI-PATTERN: never default active=true when AS response is missing.
boolean active = introspectionResponse == null
    || Boolean.TRUE.equals(introspectionResponse.get("active"));
~~~

The right policy distinguishes:

~~~text
active=true AND metadata policy valid  → Authentication succeeds
active=false / invalid metadata         → Reject
no trustworthy response                 → Reject as UNAVAILABLE
~~~

### 6.4. Fail Closed Also Applies to Attribute Policies

Avoiding creating a principal on `active=false` is not enough. If introspection returns `active=true` yet **lacks a required audience** or fails scope/issuer contract rules, you must never skip remaining checks to "reduce client errors."

For example, the Orders API requires `aud=orders-api`:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "aud": "billing-api"
}
~~~

This token must not be accepted by the Orders API, even though the introspection endpoint returned 200 and the token is active. The remote result proves the token is active according to the AS, not that it was issued for **every resource**.

## 7. Circuit Breakers, Bulkheads, and Rate Limiting Solve Different Problems

A good retry policy alone cannot prevent overload. Separate the mechanisms:

| Mechanism | Mitigates What Risk? | Decision When Limit Reached |
|---|---|---|
| **Timeout** | Slow upstream, requests holding resources too long | Stop waiting, return failure/UNAVAILABLE |
| **Bounded retry** | Rare transient errors likely to recover promptly | Cap attempts/budget; fail when exhausted |
| **Exponential backoff + jitter** | Many instances retrying in lockstep | Spread retry timing |
| **Circuit breaker** | AS in sustained outage / continuous 503s | Temporarily stop sending calls; fail fast |
| **Bulkhead / concurrency limit** | Too many simultaneous introspections | Reject early or bounded queue |
| **Rate limiter** | Request rate exceeding AS capacity | Shed or throttle rate |
| **Bounded queue** | Unbounded queuing | Reject when queue is full; never wait forever |
| **Request-level deadline** | Total retries/backoff exceeding API SLO | Do not start new attempts once budget is spent |
| **Approved cache** | Repeated introspection of the same token wasting resources | Reuse **valid verified results within expiry/freshness** |

### 7.1. Circuit Breaker States

~~~mermaid
stateDiagram-v2
    [*] --> Closed
    Closed --> Open: transient error rate exceeds threshold
    Open --> HalfOpen: wait duration elapses
    HalfOpen --> Closed: probes succeed per policy
    HalfOpen --> Open: probe fails
~~~

**Closed**: lets requests reach introspection while tracking error rates.  
**Open**: stops calling the AS per request and fails authentication fast.  
**Half-open**: allows only a limited number of probes/requests to check whether the AS has recovered.

While the circuit is open, **never let unverified tokens through by default**. A circuit breaker optimizes failure handling and protects resources; it is not a permission-granting mechanism.

### 7.2. Never Count `active=false` as an AS Health Failure

Suppose a bot sends 10,000 fake tokens, and the AS operates normally returning `active=false`. If the circuit breaker treats every "introspection rejection" as a server error, the bot can trip the circuit open and disrupt legitimate users.

Classify properly:

~~~text
HTTP 200 + active=false → normal application/protocol outcome
HTTP 200 + active=true  → normal application/protocol outcome
HTTP 503 / timeout      → upstream transient failure
HTTP 401 caller auth    → configuration/security incident
HTTP 429                → overload/rate-limit signal
~~~

Circuit breakers must measure **introspection transport/service health**, not users' valid-token ratio.

### 7.3. Bulkheads Protect Threads and Connection Pools

Suppose a Servlet Resource Server is allowed at most 40 concurrent introspection calls. When exceeded:

~~~text
requests waiting for introspection
                |
                v
       concurrency limiter
                |
       +--------+---------+
       |                  |
    slot free          saturated
       |                  |
       v                  v
  call AS            fail fast /
                    bounded queue
~~~

Using timeouts without concurrency caps allows an AS slowdown to stall hundreds or thousands of Servlet threads. With a bulkhead, resource consumption stays predictable. If using a queue, the queue must be **bounded** and queue wait time must fit within the total deadline.

### 7.4. Rate Limiters Protect the Authorization Server

Rate limiters often sit at the outbound introspection layer or share a cluster-wide budget, not only on inbound endpoints. A per-instance limit can still generate huge aggregate load if instance counts double.

Example:

~~~text
Contracted AS introspection capacity: 1,000 req/s
Resource Server cluster: 10 instances
    ↓
Per-instance budget cannot simply be set to 1,000 req/s
~~~

In real designs, account for total allocation, skew across instances, traffic bursts, and retry overhead. If using a shared distributed limiter, also evaluate the limiter's own availability; **never design a fallback saying "if the limiter fails, allow unlimited retries."**

### 7.5. Ordering of Resilience Components Also Matters

One organizational approach:

~~~text
Incoming request
   |
   v
Total deadline
   |
   v
Retry controller (max attempts + jitter)
   |
   +-- per attempt:
        capacity/rate permit
            |
            v
        Circuit breaker check
            |
            v
        HTTP client with per-attempt timeout
            |
            v
        RFC 7662 response classifier
   |
   v
Authentication outcome
~~~

No single library ordering is mandatory for every deployment. Avoid two structural mistakes:

1. Retrying **"bulkhead full" or "circuit open" errors** themselves and amplifying load.
2. Holding a permit/connection during backoff sleep when it could have been released, shrinking serving capacity.

When using a resilience library, determine **whether retry wraps the circuit breaker or vice versa**, which exceptions are recorded, and whether limiters apply per attempt or per whole operation. Never stack annotations assuming they yield identical behavior in any AOP order.

## 8. Expressing the Retry Policy as an Algorithm

Safe pseudocode must separate outcomes and deadlines:

~~~text
function introspectWithPolicy(token, deadline):
    attempts = 0

    while attempts < maxAttempts:
        if deadline exhausted:
            raise IntrospectionUnavailable

        if circuit is open:
            raise IntrospectionUnavailable

        if capacity permit unavailable:
            raise IntrospectionUnavailable

        attempts += 1
        try:
            response = callIntrospectionWithPerAttemptTimeout(
                token, remainingDeadline
            )

            if response is valid RFC 7662 with active=false:
                raise InvalidTokenWithoutRetry

            if response is valid RFC 7662 with active=true:
                validate required metadata
                return VerifiedPrincipal

            if response has invalid schema or trusted policy mismatch:
                raise InvalidProtocolOrTokenWithoutRetry

        catch known non-retryable error:
            propagate error (no retry)

        catch known transient upstream error:
            if attempts >= maxAttempts:
                raise IntrospectionUnavailable

            delay = boundedBackoffWithJitter(attempts)
            if delay + minimumNextAttemptBudget > remainingDeadline:
                raise IntrospectionUnavailable

            wait delay (without violating capacity policy)

    raise IntrospectionUnavailable
~~~

The algorithm illustrates **decisions**, not a copy-pasteable Spring Security implementation. Components such as the HTTP client, deadline propagation, circuit breaker, JSON parser, and exception mapping must match your actual libraries and versions.

### 8.1. Never Retry Immutable or Security Errors

The `retryable` condition must be an **explicit allowlist**:

~~~text
retryable =
    transient upstream 502/503/504
    OR policy-permitted connect/read timeouts
    OR rate-limit signal with Retry-After fitting within budget

NOT retryable =
    active=false
    OR token missing/failing profile
    OR wrong introspection client credentials
    OR audience mismatch
    OR contract-invalid protocol response
    OR TLS certificate validation failure
    OR circuit breaker open / bulkhead rejected
~~~

Even errors listed as "retryable" remain subject to **attempt budget, time, concurrency, and load state**. During widespread outages, policy may disable retries altogether.

### 8.2. Total Retry Volume Needs Its Own Budget

One management technique is a **retry budget**: allowing only a small fraction of introspection requests to issue extra attempts relative to baseline requests in a window. Hypothetical example:

~~~text
Fresh introspection requests: 1,000/s
Retry budget:                 5% additional attempts
Extra attempts allowed:       50/s
~~~

Such a cap keeps the system from doubling call volume when the AS is already weak. The 5% figure is an example policy only; real mechanisms must reflect cluster-wide capacity and AS-agreed limits.

### 8.3. Protecting Tokens During Retries

Every retry resends **the same Bearer credential** in the `token` form field to the introspection endpoint. Therefore:

- Never write `token` to logs when retrying.
- Never put client secrets into exception messages or traces.
- Never log introspection HTTP request/response bodies.
- Never store tokens in an unprotected distributed retry queue.
- If a retry is cancelled due to timeout/client disconnect, cancel/release cancellable HTTP operations and buffers per the API.
- Never switch the introspection URI based on data inside the token to try "another endpoint" outside the trust registry.

## 9. Spring Security Servlet: Where to Place Retry Policy

In Spring MVC/Servlet applications, Spring Security normally uses **`OpaqueTokenIntrospector`** to accept a Bearer token string and return a verified **`OAuth2AuthenticatedPrincipal`** or throw an exception when authentication cannot succeed.

~~~text
BearerTokenAuthenticationFilter
   |
   v
OpaqueTokenAuthenticationProvider
   |
   v
OpaqueTokenIntrospector
   |
   +--> outbound HTTP / local state
   +--> classification + resilience policy
   |
   v
OAuth2AuthenticatedPrincipal / failure
   |
   v
BearerTokenAuthentication + GrantedAuthority
~~~

### 9.1. Configuring Resource Server with an Introspection Endpoint

Servlet dependencies:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

The example uses environment variables instead of hardcoding secrets. In real environments, manage client credentials via a secret manager, enforce trusted TLS, and maintain a rotation plan.

Security chain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OrdersResourceServerSecurity {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(withDefaults()))
            .build();
    }
}
~~~

**This is only baseline introspection configuration.** The properties above do not automatically declare retry policies, circuit breakers, per-attempt timeouts, or custom audience validation. To alter behavior, pick the HTTP client/introspector implementation matching your Spring Security version and wire resilience mechanisms explicitly.

### 9.2. Do Not Place Retries After Authentication Has Failed

Some architectures attempt to retry like this:

~~~text
Spring Security authentication failed
         |
         v
HTTP 401 to client
         |
         v
Gateway retries entire HTTP request
~~~

This is normally **not the right place to retry introspection**. Having a gateway retry the entire request can repeat controller side effects if execution occurred, muddles 401/503 semantics, and increases load. Introspection retries belong **where the token-verification service is called**, with explicit protocol error classification and deadlines, rather than retrying whole business requests.

### 9.3. Never Attach Retries to Every Exception from `OpaqueTokenIntrospector`

Anti-pattern:

~~~java
// ANTI-PATTERN: catching every exception and retrying is wrong.
for (int i = 0; i < 5; i++) {
    try {
        return delegate.introspect(token);
    } catch (Exception anyFailure) {
        // Dangerous: active=false could also be wrapped as an exception.
    }
}
~~~

The code above can repeat 5 times on invalid tokens, wrong client secrets, TLS certificate errors, or circuit-open states. Never use it as a resilience policy.

### 9.4. Place an Error-Classifying Transport Adapter Before Wrapping with Retries

Diagram of a sound structure:

~~~text
OpaqueTokenIntrospector (bean used by SecurityFilterChain)
   |
   v
VerifiedIntrospectionAdapter
   |
   v
BoundedRetryPolicy
   |
   v
HTTP Transport (classifies status/timeouts per allowlist)
   |
   v
Trusted introspection endpoint
~~~

The adapter should map outcomes into **non-overlapping** groups:

~~~text
TokenRejected:
  active=false; wrong audience/required claim
  => no retry

IntrospectionConfigurationError:
  caller 401/403; invalid TLS certificate; wrong endpoint
  => no automatic retry

IntrospectionTransientError:
  policy-permitted timeout/502/503/504
  => may retry boundedly

IntrospectionRateLimited:
  429; optional Retry-After
  => shed load; usually no in-request retry
~~~

You cannot classify accurately from exception message strings like `contains("timeout")`. The HTTP client layer must preserve status and exception causes as supported by your library version; when unable to classify safely, default to **no retry**.

## 10. A Decorator Illustrating Bounded Retries

The following example shows a **Servlet/blocking** structure where the transport layer has already normalized **only retry-permitted transient errors** into a dedicated exception. It does not classify Nimbus HTTP statuses itself or perform HTTP connections; that belongs to the application-supplied `delegate`.

~~~java
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.ThreadLocalRandom;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OAuth2IntrospectionException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

// Emitted by the transport adapter ONLY for classified transient errors.
final class TransientIntrospectionFailure extends OAuth2IntrospectionException {
    TransientIntrospectionFailure(String message, Throwable cause) {
        super(message, cause);
    }
}

final class BoundedRetryIntrospector implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final int maxAttempts;
    private final Duration totalBudget;

    BoundedRetryIntrospector(
            OpaqueTokenIntrospector delegate,
            int maxAttempts,
            Duration totalBudget) {
        if (maxAttempts < 1 || totalBudget.isZero()
                || totalBudget.isNegative()) {
            throw new IllegalArgumentException("Invalid retry policy");
        }
        this.delegate = Objects.requireNonNull(delegate);
        this.maxAttempts = maxAttempts;
        this.totalBudget = totalBudget;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        long started = System.nanoTime();
        long budgetNanos = totalBudget.toNanos();

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            long elapsed = System.nanoTime() - started;
            if (elapsed >= budgetNanos) {
                throw new OAuth2IntrospectionException(
                    "Introspection unavailable within deadline");
            }

            try {
                // Delegate must enforce its own per-attempt HTTP timeout,
                // capped to remaining time if possible.
                return delegate.introspect(token);
            } catch (TransientIntrospectionFailure transientFailure) {
                if (attempt == maxAttempts) {
                    throw transientFailure;
                }

                long remainingNanos =
                    budgetNanos - (System.nanoTime() - started);
                long jitterNanos =
                    ThreadLocalRandom.current().nextLong(
                        50_000_000L, 150_000_001L);

                // Reserve at least 250 ms for the next attempt.
                if (remainingNanos <= jitterNanos + 250_000_000L) {
                    throw transientFailure;
                }

                try {
                    long ms = jitterNanos / 1_000_000L;
                    int ns = (int) (jitterNanos % 1_000_000L);
                    Thread.sleep(ms, ns);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new OAuth2IntrospectionException(
                        "Introspection interrupted", interrupted);
                }
            }
        }

        throw new OAuth2IntrospectionException(
            "Introspection attempt budget exhausted");
    }
}
~~~

### 10.1. Policy of the Example Above

With:

~~~java
new BoundedRetryIntrospector(
    classifiedDelegate,
    2,
    Duration.ofMillis(900)
);
~~~

this means **at most two attempts** and an illustrative 900 ms total budget. An `active=false` or configuration error emitted by `delegate` with an exception type **other than** `TransientIntrospectionFailure` is **not retried**.

### 10.2. What the Example Intentionally Does Not Claim

- Not production-ready code: it only illustrates **exception classification and bounded retries** in a wrapper.
- `Thread.sleep` blocks the Servlet thread during backoff; under high load, prefer a resilience library/architecture with explicit concurrency budgets to avoid stalling many threads.
- `System.nanoTime` measures elapsed time, not wall-clock time for JWT expiry.
- **Total deadline is a logical check**; unless the delegate's HTTP client enforces a **per-attempt timeout** smaller than remaining time, one call can block past the budget and the wrapper cannot interrupt it itself.
- Retry budgets, bulkheads, circuit breakers, rate limiters, connection pool timeouts, and metrics must be configured separately.
- Never rely on `TransientIntrospectionFailure` by naively wrapping every `OAuth2IntrospectionException`; classification must occur at the HTTP boundary.
- If the caller cancels the request, ensure the transport client cancels or releases resources per library capabilities; a blocking call may keep running without cancellation support.
- Tokens and credentials must never be placed in decorator exception text or logs.

### 10.3. Why Classify in the Delegate?

`OpaqueTokenIntrospector` only specifies "return principal or fail," without requiring every implementation to emit the same exception class for HTTP 429/5xx/timeouts. If a wrapper catches:

~~~java
catch (OAuth2IntrospectionException ex) {
    // retry everything
}
~~~

it could repeat client-secret errors or `active=false` depending on how the implementation constructs exceptions. **Separating transport errors into domain failure types where full HTTP information exists** keeps the retry policy accurate.

## 11. Resilience Config Must Attach to the Right Introspector

In Spring Security Servlet, you can expose an `OpaqueTokenIntrospector` bean or pass an introspector directly via the DSL. What matters is that the exact **introspector used by the security chain** carries the designed policy.

Structural wiring (assuming the application implements `classifiedDelegate` as a bean):

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
class IntrospectionResilienceConfiguration {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            ClassifiedIntrospectionDelegate classifiedDelegate) {
        return new BoundedRetryIntrospector(
            classifiedDelegate,
            2,
            Duration.ofMillis(900)
        );
    }
}
~~~

`ClassifiedIntrospectionDelegate` is an **application-defined interface/class** implementing the error-classification semantics from earlier; you must provide an implementation for this code to run in a real project. It is not a built-in Spring Security class. Never declare competing introspector beans simultaneously unless the chain explicitly selects which bean to use.

If the security chain attaches another introspector via `opaqueToken(...).introspector(...)`, the bean above may **not be used**. With multiple chains or issuers, each chain must receive the appropriate policy.

### 11.1. Resilience Libraries Can Replace Hand-Rolled Wrappers

A library like Resilience4j can help implement retries, circuit breakers, bulkheads, and rate limiters. However, annotations/decorators **do not automatically know `active=false` differs from 503**, nor do they enforce total request deadlines or ensure retries target the same trusted issuer.

Illustrative config-style policy (**example only, not default Spring Security auto-config properties**):

~~~yaml
app:
  introspection:
    timeout:
      total: 900ms
      connect: 200ms
      response: 350ms
    retry:
      max-attempts: 2
      base-delay: 50ms
      max-delay: 150ms
      jitter: true
      retryable-statuses: [502, 503, 504]
    capacity:
      max-in-flight-per-instance: 40
      max-queue: 0
    circuit-breaker:
      enabled: true
      half-open-probes: 3
~~~

These `app.introspection.*` properties are merely an **application-defined schema** and have no effect just by appearing in `application.yml`. You need code configuring the HTTP client/Resilience4j accordingly, along with limit observability.

### 11.2. Critical: Integration Order and Policy Coverage

A configuration can "look good" yet do nothing if:

- Retries are configured on a `RestClient` other than the one the introspector actually uses.
- Boot's default `OpaqueTokenIntrospector` bean runs instead of your custom bean.
- A custom bean exists, yet the security chain explicitly wires a different introspector.
- A circuit breaker wraps downstream controller services only, not HTTP introspection.
- Timeouts exist on business requests without timeouts on the introspection transport.
- A per-instance rate limiter exceeds aggregate AS quota when scaled out.

Therefore, verify **the exact pipeline a Bearer request actually traverses**, rather than stopping once beans/configs exist in the application context.

## 12. WebFlux: Asynchronous Retries Without Blocking the Event Loop

In **Spring WebFlux**, the Resource Server uses `ReactiveOpaqueTokenIntrospector`. Error models and fail-closed rules remain the same as in Servlet, yet retries/backoff should rely on asynchronous publishers rather than `Thread.sleep`.

### 12.1. Basic Reactive Resource Server Configuration

Dependencies:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

HTTP security:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ReactiveOrdersSecurity {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(withDefaults()))
            .build();
    }
}
~~~

Spring Boot can configure the introspection endpoint via `spring.security.oauth2.resourceserver.opaquetoken.*` just like in Servlet. When customizing retries, ensure the exact `ReactiveOpaqueTokenIntrospector` used by the chain carries the designed policy.

### 12.2. Reactor Retries Only for Classified Errors

Reactive wrapper example:

~~~java
import java.time.Duration;
import java.util.Objects;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

final class BoundedReactiveIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;

    BoundedReactiveIntrospector(ReactiveOpaqueTokenIntrospector delegate) {
        this.delegate = Objects.requireNonNull(delegate);
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return Mono.defer(() -> delegate.introspect(token))
            .retryWhen(
                Retry.backoff(1, Duration.ofMillis(50))
                    .maxBackoff(Duration.ofMillis(150))
                    .jitter(0.5)
                    .filter(error ->
                        error instanceof TransientIntrospectionFailure)
            )
            .timeout(Duration.ofMillis(900));
    }
}
~~~

Meaning:

- `Retry.backoff(1, ...)` allows **at most one retry** after the initial call, i.e., up to two attempts on continuous retryable errors.
- `filter(...)` ensures only transient exceptions **reliably classified by the transport adapter** are retried. `active=false` and configuration errors are excluded.
- `timeout(900ms)` bounds the **entire retry publisher chain**, including backoff. In addition, the HTTP client still needs connection/read timeouts and pool limits.
- `Mono.defer(...)` ensures the delegate is invoked freshly on each subscription/retry per publisher semantics.
- There is no `onErrorResume(error -> Mono.just(fakePrincipal))`: if retries exhaust or time out, **the `Mono` fails** without creating a principal.

**This is an illustrative pattern**, not a complete production resilience system. `TransientIntrospectionFailure` is an application-normalized exception as in the Servlet example. Add **bulkheads, circuit breakers, rate limits, cancellation policies, telemetry, and exception mapping** per architecture. Reactor `retryWhen` may wrap exceptions once retries exhaust; error handlers must classify safely without altering the authentication decision.

### 12.3. Never Make Blocking Calls Inside Reactive Callbacks

Anti-pattern:

~~~java
// ANTI-PATTERN: can block the Reactor event loop.
return Mono.fromCallable(() -> blockingIntrospector.introspect(token))
    .retryWhen(...);
~~~

A `Mono.fromCallable` does not turn a blocking HTTP client into a non-blocking one. Without proper scheduling, it can execute on a blocking-sensitive thread. Use a reactive HTTP client, or if forced to integrate a blocking library, bound concurrency and offload execution to a properly designed bounded scheduler.

### 12.4. CORS and Authentication Errors on WebFlux

For browser clients, preflight requests may omit Bearer tokens. Order CORS handling properly so preflights are not needlessly introspected or rejected for auth. Real requests following preflight must still go through introspection and authorization.

An upstream outage is never solved by:

~~~java
// ANTI-PATTERN:
.onErrorResume(ex -> Mono.just(anAuthenticatedPrincipal))
~~~

If you need to return 503 instead of 401 for transport errors, do so in **exception mapping at the security boundary** while keeping the authentication result failed and creating no principal.

## 13. Introspection Caching: Shed Load Without "Legitimizing" Stale Data

Caching can reduce HTTP calls when the same token is presented repeatedly. However, it shifts part of the trust decision from **the Authorization Server at request time** to **evidence stored on the Resource Server**.

### 13.1. `active=true` Caching Must Be Bounded

A verified cache entry must store structured information:

~~~text
key:         protected fingerprint(token) + trust context
value:       verified active=true result + accepted attributes
verifiedAt:  timestamp of successful verification
expiresAt:   cache expiration per policy
tokenExp:    token exp if present
context:     issuer, resource/audience, introspection client/policy
~~~

General rule:

~~~text
cacheEntryExpiresAt <= tokenExpiresAt (if trusted)
cacheEntryExpiresAt <= verifiedAt + maxAcceptedCacheTTL
cacheEntryExpiresAt <= any policy-specific freshness deadline
~~~

Never cache `active=true` indefinitely if the token lacks `exp`; apply another policy bound or skip caching. Cache keys must never appear as raw Bearer tokens in logs, metrics, traces, or dashboards; use a fingerprint protected per your threat model and proper key management. If the token store/cache leaks, it may contain sensitive identities/attributes, so enforce RBAC, encryption, and retention.

### 13.2. During an AS Outage: Which Entries Remain Usable?

Scenario:

~~~text
10:00:00 introspection → active=true, exp=10:30
10:00:00 local cache entry TTL 30 seconds
10:00:15 AS outage starts
10:00:20 request with same token arrives
10:00:40 request with same token arrives
~~~

Under a **valid-cache-only** policy:

| Time | Cache State | Decision |
|---|---|---|
| 10:00:20 | Entry still within TTL and token not expired | May use verified entry if policy allows |
| 10:00:40 | TTL expired, AS still unavailable | **Do not** use stale entry to authenticate; fail closed |

This is **a design choice**. A system might pre-approve a very short, controlled "stale-if-error" window to preserve availability, provided it explicitly documents **the revocation lag accepted by the organization** and never calls it current-state verification. For sensitive endpoints requiring immediate revocation, **disable caching or stale usage**.

Never implement vague fallbacks like:

~~~java
// ANTI-PATTERN:
catch (Exception upstreamDown) {
    return lastSuccessByToken.get(token); // May already be past TTL or revoked!
}
~~~

### 13.3. If Policy Accepts Stale-If-Error

A policy may be pre-approved under these conditions:

1. The initial entry must be a **successfully verified** introspection result for the exact token/issuer/audience/client context.
2. The token has not passed `exp` and has no new local revocation/denylist signal.
3. The stale window is strictly capped (e.g., a few seconds per risk assessment), never renewed per request.
4. Used only on genuinely **classified infrastructure failures**, never on `active=false` or invalid claims.
5. Explicit metrics and auditing whenever stale evidence is used.
6. Sensitive endpoints can forbid stale usage completely.
7. Never deployed without agreement from security/AS owners on revocation lag.

**Relying on a verified cache still within its window** is a consistent policy option, yet **it is not fresh introspection**. If policy requires remote verification per request, stale-if-error may be inappropriate.

### 13.4. Caching `active=false` Results

Negative caching can cut repeated introspection for common invalid tokens. Still, consider:

- A newly issued token might not yet be visible to an introspection replica, causing temporary false negatives.
- An attacker can send endless random tokens to create many negative entries, causing memory pressure.
- Cache keys must be protected and cardinality bounded.
- Negative cache TTLs must be short, capacity-bounded, and never replace authentication policy.
- Never cache 429/503/timeout as `active=false` unless explicitly designed otherwise; infrastructure errors do not prove a token is invalid.

### 13.5. Stampede When a Popular Token's Cache Entry Expires

If thousands of requests share a service token, cache TTL expiration can trigger hundreds of simultaneous AS calls:

~~~text
same token cache expires
  ├── request A → introspection
  ├── request B → introspection
  ├── request C → introspection
  └── ...
~~~

Use **single-flight / request coalescing** so concurrent requests sharing the same cache key share a single **in-flight future/publisher** rather than calling the AS repeatedly. Bound waiting keys, wait times, failure handling, and cancellation to prevent memory leaks/DoS. If the first request gets `active=false`, all waiters must still be rejected; never let a waiter fall back to stale state.

### 13.6. Never Use Caching to Bypass Token Binding

If an access token has sender constraints (e.g., mTLS/DPoP), introspection `active=true` is not enough for every request: the Resource Server must still verify **the current request's proof/key binding**. Never cache an authentication result and skip sender proof. Likewise, audience and tenant context may need to be part of the cache key/policy.

## 14. Protecting the Authorization Server Itself from Overload

A Resource Server can simultaneously receive:

- Frequently used valid tokens.
- Expired tokens.
- Fake tokens generated randomly by bots.
- Traffic from new clients after a rollout.
- Traffic spikes from gateway retry bugs.

Any unknown token can trigger an introspection call without load-shedding controls.

### 14.1. Inbound Rate Limits vs. Outbound Rate Limits

**Inbound rate limits** protect the Resource Server from request bursts; they can apply at gateways/IPs/appropriate client identities, avoiding relying on unverified claims to assess identity.

**Outbound rate limits** protect the Authorization Server from the total introspection volume emitted by the Resource Server. They should consider **the whole cluster**, not just individual pods.

Both limiters complement each other. If an inbound attacker rotates IPs or uses fake tokens, IP-based inbound limits may fall short; outbound limits still shield the AS from a request flood.

### 14.2. Shed Load Early on Saturation

If a pool has 40 slots and all are full:

~~~text
new request
    |
    v
capacity permits: 0
    |
    v
short-circuit (no Authentication created)
    |
    v
service-unavailable response per policy
~~~

Do not hold requests until queues grow to thousands of items. A timely failure response is better than an unbounded queue that renders the entire service unresponsive.

### 14.3. Handling AS `Retry-After` Through the Resource Server

Never blindly mirror an introspection HTTP 429 as HTTP 429 to the client, because **the quota may belong to the Resource Server's own introspection client credentials**, not the API caller's user quota. You can return 503 or another policy response while **throttling outbound calls** and investigating the 429 source.

If guiding clients to retry, never promise a recovery time the service doesn't know for the AS. Public `Retry-After` headers must fit the contract, contain no sensitive metadata, and avoid synchronized retry waves.

### 14.4. One Issuer Serving Multiple Resource Servers

If dozens of microservices share an introspection client or quota, each service independently retrying twice can still break the shared quota. Establish:

~~~text
Shared AS capacity / contract
       |
       +--> Orders API budget
       +--> Billing API budget
       +--> Inventory API budget
       +--> Admin API budget
~~~

Budgets can be partitioned by criticality and endpoint sensitivity. One service under a fake-token attack must not exhaust authentication quota for other services. When credentials or quotas cannot be separated, add aggregate load/circuit protection.

## 15. Observing the System Without Leaking Tokens

A retry policy is operable only if developers can tell failure sources apart. Yet logging raw tokens or client secrets to "debug" creates severe security exposure.

### 15.1. Useful Metrics

| Metric | Recommended Labels | Avoid |
|---|---|---|
| `introspection_attempts_total` | issuer alias, outcome category, environment | Raw token, email, full URI with secrets |
| `introspection_retries_total` | retry reason, policy version | Arbitrary token hash as label |
| `introspection_duration_seconds` | service, outcome, bounded buckets | Per-request subject/jti |
| `introspection_in_flight` | instance/cluster | Credentials or PII |
| `introspection_queue_depth` | endpoint alias | Full request body |
| `introspection_circuit_state` | CLOSED/OPEN/HALF_OPEN | Arbitrary exception messages |
| `introspection_rejected_capacity_total` | bulkhead/rate-limit cause | Token string |
| `introspection_cache_hits_total` | hit/miss/stale-within-policy | Token as a label |
| `authentication_outcomes_total` | authenticated/invalid/unavailable | Claims/credentials |

Metrics must have **bounded-cardinality labels**. Use system-generated trace/request IDs when correlating individual requests. Never use `sub`, `jti`, token values, or client secrets as metric dimensions.

### 15.2. Structured Logging Categories

Safe examples:

~~~text
INFO event=introspection outcome=active duration_ms=81 attempts=1 req_id=...
WARN event=introspection outcome=upstream_503 attempts=2 req_id=...
WARN event=introspection outcome=rate_limited attempts=1 req_id=...
WARN event=introspection outcome=invalid_token attempts=1 req_id=...
ERROR event=introspection outcome=client_auth_failed req_id=...
~~~

Do not use:

~~~text
WARN introspection failed token=eyJ... clientSecret=...
ERROR upstream request body=token=...&client_secret=...
DEBUG principal={all-claims-and-credentials}
~~~

Because introspection POSTs carry the **raw access token** in the form body and may carry Basic client auth in headers, disable/redact HTTP wire/body/header logging in `RestClient`, `WebClient`, gateways/proxies, distributed tracing, and error monitoring.

### 15.3. Alerting by Incident Type

| Signal | Priority Investigation |
|---|---|
| Unusual spike in `active=false` | Clients sending expired tokens, abuse, or token issuance issues |
| 401 from AS introspection | Secret rotation / caller authentication |
| 429 from AS introspection | Quota/capacity, duplicate retries, traffic-increasing deployment |
| Continuous 503/timeouts | AS/network outage, circuit breaker, thread pools |
| Retry ratio exceeding budget | Backoff/retry config or degraded AS |
| Circuit breaker OPEN for long duration | Upstream not recovering, probes failing |
| Rising stale cache usage | Unstable AS or policy consuming risk allowance |
| 401/403 at Resource Server after AS change | Scope/audience/token metadata mapping drift |

**Never treat rising client 401s as sole proof of an AS outage**: the same status can arise from invalid tokens, issuer policy, missing authorities, or exception handling. Monitor the introspection layer directly.

## 16. Testing Errors and Load: Prove No "Verification Bypass" Path Exists

Testing retries does not just verify that a request eventually succeeds after one 503. More importantly, confirm **every failure path creates no valid `Authentication`** and never lets outbound requests exceed budget.

### 16.1. Integration Matrix with a Mocked Introspection Endpoint

| Scenario | Mocked AS Response/Transport | Expected Attempts | Authentication Outcome |
|---|---|---|---|
| Valid token | 200 `active=true` and complete metadata | 1 | Success |
| Inactive token | 200 `active=false` | **1**, no retry | Not authenticated |
| Wrong audience | 200 `active=true`, `aud=billing-api` | 1 | Not authenticated for Orders API |
| Missing required metadata | 200 `active=true`, missing contracted `aud` | 1 | Not authenticated |
| Wrong RS credentials | HTTP 401 from introspection | **1** | Not authenticated; alert |
| Caller lacks introspection permission | HTTP 403 | 1 | Not authenticated; alert |
| Wrong introspection URI | HTTP 404 | 1 | Not authenticated; config error |
| Transient failure then recovery | 503 then 200 `active=true` | At most 2 when policy allows | Succeeds if total deadline remains |
| Sustained transient failures | 503, 503, 503... | Never exceeds `maxAttempts` | Not authenticated |
| AS overload | 429 with large `Retry-After` | Usually 1; never waits past budget | Not authenticated |
| Connect timeout | Timeout classified retryable | Per attempt/budget | Not authenticated if no result |
| Read timeout after sending request | Unknown if AS processed | Per idempotency policy | Not authenticated if no result |
| Invalid TLS certificate | TLS validation failure | 1 | Not authenticated |
| Malformed JSON / missing `active` | 200 yet response violates contract | 1 | Not authenticated |
| Circuit breaker OPEN | No request sent to AS | **0 outbound calls** | Not authenticated |
| Bulkhead saturated | No permit available | 0 or per queue policy | Not authenticated |
| Valid cached entry | Previously verified and within TTL | 0 outbound calls on hit | May authenticate per cache policy |
| Cached entry TTL expired, AS unavailable | No permitted evidence remaining | Never exceeds attempts/budget | **Not authenticated** |

In tests, observe **actual HTTP call counts**, elapsed time, and `SecurityContext` state. Asserting only the final HTTP status without counting attempts could hide an implementation silently firing 10 requests at the AS before returning 401, worsening an outage.

### 16.2. Unit Testing That the Decorator Never Retries Invalid Tokens

Unit test example for `BoundedRetryIntrospector` from Section 10. This is an HTTP-independent unit test; `BadOpaqueTokenException` represents an inactive token and is not treated as transient.

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class BoundedRetryIntrospectorTest {

    @Test
    void inactiveTokenIsNeverRetried() {
        AtomicInteger attempts = new AtomicInteger();

        OpaqueTokenIntrospector delegate = token -> {
            attempts.incrementAndGet();
            throw new BadOpaqueTokenException("Token not active");
        };

        OpaqueTokenIntrospector policy = new BoundedRetryIntrospector(
            delegate, 2, Duration.ofMillis(900));

        assertThatThrownBy(() -> policy.introspect("fake-token"))
            .isInstanceOf(BadOpaqueTokenException.class);

        assertThat(attempts.get()).isEqualTo(1);
    }
}
~~~

Because the wrapper catches only `TransientIntrospectionFailure`, the invalid-token exception propagates immediately. This test verifies **attempt count**, not just exception presence.

### 16.3. Unit Testing That Transient Failures Retry at Most Once

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

import static org.assertj.core.api.Assertions.assertThat;

class TransientRetryExampleTest {

    @Test
    void oneTransientFailureCanBeRetriedOnce() {
        AtomicInteger attempts = new AtomicInteger();

        OpaqueTokenIntrospector delegate = token -> {
            if (attempts.incrementAndGet() == 1) {
                throw new TransientIntrospectionFailure(
                    "Synthetic upstream 503",
                    new IllegalStateException("test-only")
                );
            }
            return new DefaultOAuth2AuthenticatedPrincipal(
                "test-user",
                Map.of("sub", "test-user"),
                List.of()
            );
        };

        OpaqueTokenIntrospector policy = new BoundedRetryIntrospector(
            delegate, 2, Duration.ofMillis(900));

        assertThat(policy.introspect("fake-token"))
            .isNotNull();
        assertThat(attempts.get()).isEqualTo(2);
    }
}
~~~

The test verifies **at most one retry**. `DefaultOAuth2AuthenticatedPrincipal` in the test is produced by the stub on the second attempt; in the real system, **only a trusted, policy-compliant introspection response** may produce a principal.

### 16.4. Unit Testing Sustained Transient Failures Stopping at the Attempt Limit

~~~java
@Test
void persistentTransientFailureStopsAtAttemptLimit() {
    AtomicInteger attempts = new AtomicInteger();
    OpaqueTokenIntrospector delegate = token -> {
        attempts.incrementAndGet();
        throw new TransientIntrospectionFailure(
            "Synthetic upstream 503",
            new IllegalStateException("test-only")
        );
    };

    OpaqueTokenIntrospector policy = new BoundedRetryIntrospector(
        delegate, 2, Duration.ofMillis(900));

    assertThatThrownBy(() -> policy.introspect("fake-token"))
        .isInstanceOf(TransientIntrospectionFailure.class);
    assertThat(attempts.get()).isEqualTo(2);
}
~~~

This is an example test method placed inside a class with the appropriate `JUnit`, `AssertJ`, `AtomicInteger`, `Duration`, `OpaqueTokenIntrospector`, and demo class imports. These snippets are **not a complete project test suite**.

### 16.5. Timeout Tests Must Cover the Total Budget

An important test:

~~~text
Configured maxAttempts: 3
Total operation budget: 900 ms
Attempt #1 duration: 850 ms
Retry delay planned: 100 ms
Minimum next-attempt budget: 200 ms

Expected:
    Do not start attempt #2
    Create no Authentication
    Finish per UNAVAILABLE policy
~~~

When testing a blocking HTTP client, configure **read/response timeouts** explicitly because a wrapper measuring `System.nanoTime()` before/after the call cannot interrupt a hung network call on its own.

### 16.6. Test That No Error Path Has a "Fallback Principal"

Specifically simulate:

- AS down right at startup.
- AS returning 503 continuously for 30 seconds.
- Circuit breaker transitioning OPEN then HALF_OPEN.
- A token introspected while the AS was healthy whose cache entry expires during an AS outage.
- A token revoked while an `active=true` cache entry is still valid.
- A request to a sensitive endpoint with no token, an invalid token, or missing scope.
- Gateway/Resource Server concurrency saturated with zero permits left.
- HTTP client hitting TLS/secret-rotation errors.
- Client disconnecting while introspection is pending, observing cancellation/resource cleanup.

Every scenario **lacking valid verification evidence** must finish **with no authenticated principal or business access**.

## 17. Load and Chaos Testing Across Multiple Instances

A handful of unit tests do not prove a system is safe when 100 pods retry together. Run controlled load tests in staging using test credentials and a mocked/approved introspection service.

### 17.1. Quantities to Measure

| Quantity | Why Measure? |
|---|---|
| Incoming RPS | Measures requests needing authentication |
| Introspection outbound RPS | Detects retry amplification |
| Retry attempts / original requests | Verifies retry budget |
| Concurrency / waiting queue | Detects exhaustion |
| Connection pool utilization | Detects HTTP client bottlenecks |
| AS latency p50/p95/p99 | Guides per-attempt timeouts |
| Resource Server end-to-end latency | Protects total request budget |
| Circuit breaker transitions | Evaluates outage detection/recovery speed |
| Cache hit/expiry/stale usage | Measures call reduction and revocation windows |
| `active=false` / `unavailable` / `invalid_metadata` | Prevents confusing invalid tokens with AS outages |
| 401/403/503 from API | Observes client impact |

### 17.2. An Illustrative Load Test

~~~text
Normal:
  Incoming request rate: 500/s
  Introspection p95:      80 ms
  AS response:           mostly active=true/false

Degraded:
  AS 503:                60% of calls
  AS latency p95:        400 ms
  Max attempts:          2
  Total budget:          900 ms
  Max in-flight:         40 per instance

Expected:
  No requests bypass token verification
  Retry attempts bounded
  No unbounded queue growth
  Circuit breaker opens according to policy
  Resources released after timeout/cancellation
  HTTP responses distinguish token invalid vs unavailable
~~~

These numbers illustrate a load-test scenario, not guaranteed capacity. If business requirements demand sustaining 500/s during 60% 503s, evaluate actual capacity and what temporary error rate clients are permitted to see.

### 17.3. Coordinated Testing with Gateways

If both the Resource Server **and** the gateway retry:

~~~text
Gateway retry 2 attempts × Resource Server introspection 2 attempts
= up to 4 introspection attempts for one client request
~~~

If a service mesh adds retries too, total amplification grows further. Designate **only one or a few layers permitted to retry**, which request types are safe to repeat, and how deadlines divide across the system. Never let a gateway automatically retry side-effecting APIs on 503 if business execution may have already started on another branch.

### 17.4. Testing Under Multiple Issuers

If the Resource Server uses multiple issuers/introspection endpoints:

~~~text
Issuer A: healthy
Issuer B: slow / 503
~~~

Do not let Issuer B's circuit breaker block all Issuer A tokens unless the architecture genuinely shares a mandatory resource. Maintain metrics and capacity by issuer alias/trust policy, and never trust an unverified issuer claim to dynamically pick an introspection endpoint outside the allowlist.

## 18. Operational Runbook When the Introspection Endpoint Fails

When error rates rise, respond with these steps **without loosening authentication**.

### 18.1. Identify the Incident Type Accurately

Distinguish:

~~~text
A. active=false spikes while AS returns steady 200
   → Client / token issuance / expiration / abuse issue

B. AS returns 401/403 to introspection client
   → Credential / permission / config issue

C. AS returns 429
   → Capacity / quota / retry amplification issue

D. AS returns 5xx or times out
   → Upstream outage / network / service degradation

E. Malformed JSON, missing active, or metadata drift
   → Protocol / contract incompatibility
~~~

Never push a quick `permitAll()` on endpoints to "temporarily patch" C or D; that turns a protected API into a public API during an outage.

### 18.2. If the AS Is Returning 429 or 503

- Verify retry budgets and circuit breakers are reducing outbound calls, not amplifying them.
- Inspect saturation of HTTP connection pools, Servlet threads, or reactive event loops.
- Verify all instances run the same attempt/timeout policy rather than an old version retrying aggressively.
- Contact the AS owner regarding quotas, capacity, timeouts, and recent rollouts.
- If valid cache entries exist, use them only within approved TTL/freshness bounds; never enable unbounded staleness.
- Without verification evidence, return temporary/unauthenticated errors per policy and preserve the security boundary.
- Watch AS recovery to close the circuit breaker gradually, avoiding sending all traffic back at once.

### 18.3. If Introspection Client Secrets Are No Longer Valid

- Check secrets/certificates in the secret manager and rotation schedule.
- Never paste Basic headers or raw secrets into tickets.
- Never retry caller-auth HTTP 401s forever; they rarely fix themselves in 100 ms.
- Update credentials via approved workflows and confirm the AS grants introspection rights to the caller.
- Ensure all instances roll out with the new secret within the policy window.

### 18.4. If Invalid Tokens Spike After a Deployment

- Check whether the Authorization Server changed token issuance, TTLs, client policies, or token profiles.
- Check whether the Resource Server changed audience/issuer/scope mapping or the introspection caller.
- Check cache/clock/replica lag, without ever temporarily flipping `active=false` to `active=true`.
- Separate decoder/introspector errors from authorization errors caused by missing scopes or record permissions.

### 18.5. When Asked to "Let Traffic Through Temporarily While the IdP Is Down"

Respond with policy:

~~~text
Without trustworthy verification results:
    DO NOT create Authentication
    DO NOT grant default permissions
    DO NOT return protected data

Operational solutions:
    load shedding / bounded retries
    circuit breakers / bulkheads
    valid cached verification results (if policy permits)
    restore AS / configuration / secrets
    return clear service errors and sensible retry guidance
~~~

If the business requires offline operation, that must be a **pre-designed authentication architecture** with local cryptographic proof and explicit revocation/freshness policies—not a `catch(Exception) { permitAll(); }` inside the Resource Server.

## 19. Decisions That Must Be Agreed Upon with the Authorization Server

A Resource Server cannot set an effective retry policy without knowing what the AS infrastructure supports.

### 19.1. Minimum Introspection Contract

| Topic | Questions to Clarify |
|---|---|
| URI/trust | What is the official endpoint? Does it vary by environment/issuer? |
| Client authentication | Basic, `private_key_jwt`, mTLS, or what mechanism? How is rotation handled? |
| Token types | Does the AS introspect opaque tokens, JWT access tokens, or multiple profiles? |
| `active` | When does it return false: expiry, revocation, disabled client, revoked session? |
| Audience/resource | Does the AS return `aud`, resource indicators, or enforce policies per introspection client? |
| Metadata | Which claims are required to build principal/scope/tenant? |
| Timeouts | What are actual p95/p99 latencies, server limits, and gateway limits? |
| Rate limits | Quotas per client, IP, tenant, or cluster? Is `Retry-After` emitted? |
| Retry semantics | Is retrying POST introspection after a read timeout safe? |
| Availability | SLOs, backup regions, permitted failover endpoints |
| Revocation | Lag when revoking tokens/sessions/clients, cross-replica consistency |
| Caching | Does the AS permit caching `active=true`? Maximum allowed bounds? |
| Error contract | How are HTTP 401/403/429/5xx/malformed responses classified? |
| Observability | Which alerts and diagnostics exclude credentials? |

Retry and cache values **must satisfy these constraints**. For example, if the AS forbids retrying HTTP 429 yet the client retries aggressively, even an implementation labeled "resilient" weakens the system.

### 19.2. Failover Endpoints Require a Trusted Allowlist

If the AS has backup regions:

~~~text
primary:   https://idp-primary.example.test/oauth2/introspect
secondary: https://idp-backup.example.test/oauth2/introspect
~~~

Fail over only when both endpoints are designed to share **an equivalent token-state source** and matching trust policy. A secondary returning `active=false` because it hasn't synced cannot simply be skipped in search of another secondary returning true. Rules must align with the AS on replica consistency, client credentials, TLS, and revocation.

Never try a "backup introspection address" extracted from a Bearer token claim or an unverified redirect. Those URLs must belong to an **approved trust registry**. Avoid accidentally sending tokens/secrets to an untrusted hostname during retries/failover.

### 19.3. Separate Policies and Circuits Per Issuer When Needed

A Resource Server accepting multiple issuers should isolate:

~~~text
Issuer A:
  trusted introspection URI A
  credentials A
  audience policy A
  circuit/bulkhead/rate budget A

Issuer B:
  trusted introspection URI B
  credentials B
  audience policy B
  circuit/bulkhead/rate budget B
~~~

Never mix cached results across issuers. An unverified `iss` claim may only select a configuration from an **allowlist**, never causing the Resource Server to send Bearer tokens to an arbitrary client-supplied URI.

## 20. Pre-Production Checklist

### 20.1. Security Requirements

- [ ] Invalid tokens or `active=false` are never retried.
- [ ] Timeout/503/429 never produce a default principal.
- [ ] Responses missing `active` or required metadata are never treated as success.
- [ ] Issuer, audience, scope, token type, and validity times remain enforced per contract.
- [ ] Cached entries are never used past their approved expiry/freshness window.
- [ ] Stale-if-error is never used outside an approved security policy.
- [ ] Raw tokens, introspection client secrets, Basic headers, and sensitive response claims never appear in logs/traces.
- [ ] Requests never automatically route to untrusted introspection endpoints.
- [ ] Circuit breaker / bulkhead rejections halt authentication without bypassing filters.

### 20.2. Resource and Resilience Requirements

- [ ] `maxAttempts` includes the initial call and is small and bounded.
- [ ] Per-attempt connect/response timeouts are configured on the real HTTP client.
- [ ] Total operation deadline bounds attempts + backoff + queue wait.
- [ ] Retries apply only to an allowlist of classified transient errors.
- [ ] HTTP 429 is handled per rate limits/`Retry-After` and total budget.
- [ ] Backoff and jitter are enabled if retries are permitted.
- [ ] Concurrency/bulkhead/queues are all bounded.
- [ ] Retry budgets account for cluster-wide amplification.
- [ ] Circuit breakers are never tripped by `active=false`.
- [ ] HALF_OPEN permits only a small number of probes to avoid herd recovery.
- [ ] A plan exists for AS recovery and prolonged degradation.

### 20.3. Integration and Observability Requirements

- [ ] The `OpaqueTokenIntrospector` or `ReactiveOpaqueTokenIntrospector` used by the security chain is indeed the resilient implementation.
- [ ] Exception mapping preserves fail-closed decisions on both Servlet and WebFlux.
- [ ] Gateway retries do not stack uncontrolled with internal retries.
- [ ] Metrics cover attempts, retries, latency, timeouts, 429, 5xx, circuit/bulkhead, and cache freshness.
- [ ] Metric labels and logs exclude unapproved tokens/subjects/emails.
- [ ] Tests cover `active=true`, `active=false`, 401 client secret, 429, 503, timeouts, malformed responses, and stale caches.
- [ ] Tests verify outbound call counts and max elapsed time, not just HTTP status codes.
- [ ] Load tests cover multiple Resource Server instances experiencing AS errors together.

This checklist is an **implementation design aid**, not a substitute for threat modeling, IAM/Security operational reviews, or real system testing.

## 21. Common Misconceptions

### 21.1. "Retrying three times on any error improves availability"

False. Invalid tokens, wrong client secrets, and TLS trust failures rarely resolve on retry. Conversely, retrying 503s across dozens of instances amplifies load and slows AS recovery. Retries must be **conditional**, time-bounded, and concurrency-bounded.

### 21.2. "HTTP 200 from introspection means the token is valid"

False. RFC 7662 returns `active=false` inside a valid HTTP 200. The Resource Server must inspect `active` and resource metadata. Retrying `active=false` retries a **completed business outcome**, not a network failure.

### 21.3. "Introspection 401 means the user sent an invalid token"

Not necessarily. HTTP 401 from the **introspection endpoint** typically indicates authentication failure of **the client calling introspection**. It differs from the HTTP 401 the Resource Server returns to **API callers** when a Bearer token is invalid. Misclassifying it hides secret-rotation bugs and triggers pointless retries.

### 21.4. "When the circuit breaker is OPEN, the app should temporarily bypass auth"

False. A circuit breaker exists to **reduce load on upstream** and fail fast when verification is impossible; it is not an authentication bypass switch. Without valid evidence per policy, create no principal.

### 21.5. "A 900 ms total timeout is enough even if each call can hang for 30 s"

False. A wrapper measuring elapsed time after an HTTP call finishes **cannot interrupt a hung call on its own**. You need timeouts at the HTTP client/connection pool, total deadlines, cancellation, and real resource observability.

### 21.6. "Caching keeps every token working when the AS fails"

False. Caches can store only **previously verified results** and require clear TTL/freshness, token expiry, and revocation policies. An expired cache entry does not become proof that a token is still active.

### 21.7. "Enabling a 60-second cache still revokes tokens instantaneously"

Unlikely. A cached `active=true` can persist after the AS revokes a token. If faster revocation is required, shrink/remove caching or implement appropriate invalidation/synchronization.

### 21.8. "When introspection times out, try switching to any endpoint on the same domain"

Dangerous. Fail over only to URIs published and trusted in the **failover contract**. Never send raw tokens and client secrets to random endpoints or hostnames influenced by unverified input.

### 21.9. "Resilience4j annotations automatically enforce authentication policies"

No. Resilience libraries manage retries/circuits/bulkheads at call level, yet **do not understand** `active=false`, audiences, client credentials, scopes, or trust boundaries. The application must classify errors properly and let the security provider reject unverified tokens.

### 21.10. "A valid token needs no HTTP authorization"

False. `active=true` is only part of authentication. The Orders API still needs `SCOPE_orders.read` or other permissions, plus per-record owner/tenant checks.

## 22. Practical Scenario: A 20-Second 503 Outage

Hypothetical system:

~~~text
Orders API instances:           8
Requests requiring introspect:  100/s per instance
Total incoming to AS:           800/s (excluding retries)
Normal AS p95 latency:           70 ms
Transient 503 rate:              80% for 20 seconds
Max attempts per request:       2
Total introspection budget:     900 ms
Max in-flight per instance:     40
~~~

### 22.1. Without Bounded Retries

Each request can emit many calls; multiple instances block and retry in lockstep. Total outbound rate can soar far past the initial 800/s, delaying AS recovery. Resource Server thread/connection pools are tied up for long periods as well.

### 22.2. With Bounded Retries and a Circuit Breaker

Suppose policy enforces:

~~~text
1 initial attempt + at most 1 approved retry
Backoff jitter: 50–150 ms
Total budget: 900 ms
Bulkhead: max 40 in-flight per instance
Circuit breaker: opens once sufficient transient-failure data accumulates
Retry budget: partitioned per AS quota
~~~

On initial requests:

1. If AS returns 200 `active=true` with valid metadata, proceed with authentication and authorization.
2. If AS returns 200 `active=false`, reject immediately with no retry.
3. If AS returns 503, retry only if budget and capacity permits remain.
4. If 503 persists or the deadline expires, create no principal and return an error per policy.
5. Once the circuit breaker opens, halt most calls and fail fast; HALF_OPEN tests only a limited probe count.
6. As the AS recovers, close the circuit gradually per policy instead of dumping all traffic past quota at once.

### 22.3. What About Already-Cached Tokens?

If an `active=true` token was introspected before the outage and **its cache entry is still within TTL/freshness and before `exp`**, the system may use that entry per approved policy. If the entry's TTL expires during the outage, fail closed by default; never synthesize `active=true` from "it looked fine last time."

### 22.4. Criteria to Conclude the Solution Works

You cannot just ask "what percentage of requests did the API still serve?" Check **two dimensions**:

**Security:** zero invalid/unknown tokens slipped through, no loss of audience/scope validation, zero credential leaks.

**Operations:** total outbound attempts stayed bounded, no unbounded queue growth, p99 latency/timeouts controlled, circuit functioned as designed, and alerts accurately reflected error types.

## 23. Remembering the Overall Policy

~~~mermaid
flowchart TD
    A["Bearer access token"] --> B{"Valid, non-expired cached result permitted by policy?"}
    B -->|Yes| C["Use still-valid verified attributes"]
    B -->|No| D{"Circuit/capacity allow calling AS?"}
    D -->|No| U["UNAVAILABLE: create no principal"]
    D -->|Yes| E["HTTP introspection with deadline and timeouts"]
    E --> F{"Result?"}
    F -->|"active=true + valid metadata"| G["Authenticated principal"]
    F -->|"active=false / policy invalid"| I["INVALID: create no principal"]
    F -->|"Transient failure"| R{"Retry budget + deadline remain?"}
    R -->|Yes| E
    R -->|No| U
    F -->|"Configuration/protocol failure"| U
    C --> H["Check scope/HTTP/domain authorization"]
    G --> H
    H --> J["Return API data only when permitted"]
~~~

**Core principles:**

1. **Conditional retries:** only for appropriate transient errors; never retry `active=false`, 401 client credentials, or policy-invalid responses.
2. **Simultaneous bounds:** attempts, total deadlines, connect/read timeouts, concurrency, queues, retry budgets, and rate limits must all have real limits.
3. **Proactive load shedding:** circuit breakers, bulkheads, jitter, and controlled caching shield the AS from retry storms.
4. **Never bypass verification:** without trustworthy introspection results or valid cached evidence per policy, the Resource Server never creates a successful `Authentication`.
5. **Never bypass authorization:** active tokens must still pass issuer/audience/time/profile, scope, and resource-level permissions.
6. **Never expose credentials:** protect raw tokens and introspection client secrets from logs, traces, errors, and support systems.

**"Bounded retries, overload, and error policies that never bypass verification"** is more than tuning a few HTTP parameters. It defines **the trust boundary when the Authorization Server is unavailable**: controlled recovery from transient errors, upstream load reduction during overload, and consistent security decisions—**never granting access when a token cannot be verified**.

## References

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 9110 — HTTP Semantics (including status codes and Retry-After)](https://www.rfc-editor.org/rfc/rfc9110)
- [Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — OpaqueTokenIntrospector Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html)
- [Spring Security — ReactiveOpaqueTokenIntrospector Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html)
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Resilience4j — Documentation](https://resilience4j.readme.io/docs)
- [Project Reactor — Retry Reference](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
- [OWASP Cheat Sheet — REST Security](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [OWASP Cheat Sheet — Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
