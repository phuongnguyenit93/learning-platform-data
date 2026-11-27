# Protecting the Token Endpoint with Rate Limiting, Timeouts, and Anti-Abuse Controls

## 1. Context: The Token Endpoint Is a Security and Performance Hotspot

In an **OAuth 2.0/OpenID Connect (OIDC) Authorization Server** built with **Spring Security**, **Spring Authorization Server**, and Spring Boot, the **Token Endpoint** is typically exposed at `POST /oauth2/token`. This is where OAuth clients request access tokens, exchange authorization codes, use refresh tokens, or invoke other supported grants.

Unlike an end-user login page, the Token Endpoint serves **protocol requests** from clients—typically backend services or applications using OAuth client libraries. It must verify sensitive inputs such as client secrets, JWT client assertions, authorization codes, refresh tokens, and grant conditions. Consequently, the Token Endpoint can be targeted from two directions simultaneously:

- **Security:** credential guessing, authorization code replay, refresh token probing, grant abuse, and requesting unauthorized scopes.
- **Availability:** request floods that exhaust authentication providers, the authorization database, caches, JWT-signing KMS/HSM services, and thread pools.

For example, a booking system has `booking-bff` using Authorization Code + PKCE, `billing-service` using Client Credentials, and `partner-service` using refresh tokens. If a buggy client requests a new token on every API call, the Token Endpoint can overload even without an attacker. Conversely, an attacker can send thousands of `invalid_client` requests to guess secrets or burn authentication resources.

**The goal is not simply blocking as much traffic as possible.** The design must protect the Token Endpoint while keeping legitimate clients working, minimizing false positives, preserving OAuth/OIDC compliance, and providing enough operational telemetry for incident response.

### Learning Objectives

After this lesson, you will be able to:

1. Identify abuse patterns and resource-exhaustion points at the Token Endpoint.
2. Design **multi-layered rate limiting** using limit keys with clear trust boundaries.
3. Distinguish **rate limits**, **concurrency limits**, **request timeouts**, **dependency timeouts**, and **circuit breakers**.
4. Configure `SecurityFilterChain` and add narrowly scoped HTTP filters without replacing OAuth authentication.
5. Choose appropriate `429 Too Many Requests`, `Retry-After`, and OAuth error responses.
6. Protect each grant family: Authorization Code + PKCE, Refresh Token, Client Credentials, and extension grants.
7. Build strategies against credential stuffing, replay, token acquisition storms, and client authentication abuse.
8. Test limits, timeouts, concurrency, multi-instance behavior, and recovery.
9. Operate with metrics, tracing, alerts, and audits that never leak credentials.

## 2. Functional Boundaries of the Token Endpoint

The Token Endpoint may receive a typical request such as:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_OF_CLIENT_ID_AND_SECRET
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=inventory.read
```

This is an example of a confidential client. Other grants may use bodies such as:

```text
authorization_code:
  grant_type=authorization_code
  code=...
  redirect_uri=...
  code_verifier=...

refresh_token:
  grant_type=refresh_token
  refresh_token=...

client_credentials:
  grant_type=client_credentials
  scope=...

token_exchange:
  grant_type=urn:ietf:params:oauth:grant-type:token-exchange
  subject_token=...
  subject_token_type=...
```

**These parameters are illustrative only**; exact requirements depend on client type, grant, token/subject type, and Spring Authorization Server version.

### 2.1. Participating Processing Layers

```mermaid
flowchart TB
    OUT["OAuth Client / Internet"]
    EDGE["Gateway / WAF / Load Balancer<br/>TLS, body cap, rate limit, connection limit"]
    IP["Spring Security Application<br/>Pre-auth ingress limiter"]
    CA["OAuth2 Client Authentication<br/>Verify client credentials"]
    POLICY["Authenticated-client policy<br/>grant/tenant/quota"]
    ENDPOINT["OAuth2 Token Endpoint<br/>converter + provider"]
    BACK["Repositories, DB, Cache, HSM/KMS<br/>dependency timeout / bulkhead"]
    TOKEN["Token generation + persistence"]
    RESPONSE["OAuth response or controlled 429/5xx"]

    OUT --> EDGE --> IP --> CA --> POLICY --> ENDPOINT
    ENDPOINT --> BACK --> TOKEN --> RESPONSE
```

This diagram is a reference architecture. Within the framework, authentication filters, providers, authorization services, and token generators execute in a configuration-specific order. **Pre-authentication limits** can run at the gateway or a servlet filter; **authenticated-client policies** must use the verified client identity, never just a self-asserted client name from the request.

### 2.2. Distinguishing Four Control Layers

| Control | Question It Answers | Where Is It Enforced? |
|---|---|---|
| **Rate limit** | How many requests may one source send over a time window? | Gateway, AS limiter, per-client quota |
| **Concurrency limit / bulkhead** | How many heavy requests or tasks may run simultaneously? | Gateway, thread pools, bounded semaphores/queues, dependencies |
| **Timeout / deadline** | How long may a request or dependency call wait at most? | Gateway, servlet container, HTTP/DB/KMS clients |
| **Circuit breaker / overload shedding** | When a dependency fails or overloads, should traffic keep hitting it? | Service integrations, dependency clients, gateway |

Rate limiting alone **is insufficient** when a few requests hang for a long time. Timeouts alone are also insufficient when thousands of short requests exhaust authentication capacity.

## 3. Threat Model and Abuse Behaviors

| Abuse Pattern | Example | Risk | Primary Defenses |
|---|---|---|---|
| Credential stuffing | Repeatedly trying different `client_id`/`client_secret` pairs | Compromising a confidential client | Pre- and post-auth rate limits, failure detection, credential hygiene |
| JWT client assertion flooding | Sending JWTs with bad signatures or nonexistent `kid` | CPU exhaustion, JWKS/network cache pressure | Input limits, trust stores, controlled negative caching |
| Authorization code guessing/replay | Redeeming fake or already-used codes | Unauthorized token issuance if validation is missing | Random codes, short TTL, single-use, PKCE, rate limits |
| Refresh token brute force | Sending forged or revoked refresh tokens | Credential guessing, token replay | State validation, rotation/reuse detection, rate limiting |
| Token acquisition storm | Client Credentials requesting a new token per API call | AS overload | Client-side token caching, quotas, jitter, and backoff |
| Grant spraying | Probing multiple `grant_type` values on the endpoint | Mapping server/client capabilities | Registered grant policy, consistent errors, anomaly detection |
| Scope probing | Repeating requests with sensitive scopes or audiences | Probing policies/attempting privilege escalation | Client registration, audience policy, no sensitive error details |
| Request body exhaustion | Huge form bodies, many duplicate parameters | Parser memory/CPU exhaustion | Body size caps, parameter count caps, timeouts |
| Connection/slow request exhaustion | Opening many connections or sending bytes slowly | Connection/thread exhaustion | TLS termination, read/idle timeouts, connection limits |
| Expensive backend amplification | Requests repeatedly triggering DB/KMS/remote JWK calls | Exhausting downstream pools and quotas | Timeouts, bulkheads, caching, per-operation quotas |
| Distributed abuse | Multiple IPs/regions targeting the same client | Bypassing single-IP limits | Per-client detection and combined risk signals |

Not every `invalid_client` spike is an attack. Incomplete secret rotation or misconfiguration also generates bursts of failed requests; the system should alert and investigate rather than permanently locking out a client on the first spike.

### 3.1. Layer-by-Layer Threat Model

**At the edge:** callers can spoof or rotate IPs, forge headers, and send malformed requests. Never assume incoming requests carry a trustworthy client identity.

**At client authentication:** secrets, JWT assertions, and mTLS certificates must be verified independently. Using a self-asserted client ID from the request as the **sole** quota key lets attackers exhaust a victim client's quota.

**At grant validation:** preserve Spring Authorization Server's built-in guarantees, especially PKCE, redirect URI matching, authorization code ownership, single-use semantics, refresh token state, and scope limits.

**At storage/token generation:** database connections, cache I/O, and JWT/HSM signing are finite resources. A cheap network request can trigger expensive backend work if controls are placed in the wrong layer.

## 4. Multi-Layered Defense Design Principles

A design should apply **defense in depth**:

1. **Before the application:** TLS, connection limits, request size limits, normalized source rate limits, and blocking blatantly malformed requests.
2. **Before OAuth client authentication:** throttle request bursts from unauthenticated networks/sources to reduce expensive credential checks.
3. **After client authentication:** quotas per verified client identity, grant type, and tenant/environment policy.
4. **Before expensive work:** concurrency limits and timeouts for databases, introspection, signers, key stores, and external services.
5. **Responses:** preserve OAuth error semantics when validation fails; emit clear overload statuses and bounded retry guidance when appropriate.
6. **Observability:** record granted/rejected request counts, latencies, queues, retries, and credential failures without logging secrets.
7. **Mitigation:** maintain controls to lower quotas, revoke credentials, shed load, or isolate an abused client.

**No single limiter setting fits every deployment.** Tune policies from baseline traffic, threat models, client architectures, and system criticality.

### 4.1. Why IP-Only Rate Limiting Is Not Enough

A single IP address may be:

- A shared NAT serving thousands of legitimate users.
- An egress gateway for many microservices.
- A proxy or load balancer through which all traffic passes.
- Rotating IPs of legitimate clients or a botnet.
- IPv6 addresses using privacy-rotation policies.

IP-only limits can block many legitimate clients or be bypassed by rotating sources. Yet limiting solely by caller-supplied `client_id` is equally dangerous, because an attacker can supply a victim's ID to exhaust its quota (*quota exhaustion attack*).

**Solution:** Use a pre-auth layer keyed by controlled network/request fingerprints, followed by a post-auth layer keyed by **verified client identity** paired with grant/resource quotas. Never confuse these two layers.

## 5. Choosing Rate-Limit Keys Without Letting Attackers Control Them

| Stage | Usable Key | Trust Level | Caution |
|---|---|---|---|
| Gateway / edge | Real client IP derived by trusted proxy, network range, TLS identity | Depends on gateway configuration | Avoid raw untrusted `X-Forwarded-For` |
| Pre-auth in AS | Normalized source IP, gateway-issued request identity | Does not prove OAuth client | Keep fair for NAT/proxies |
| Post client authentication | Verified registered client ID / internal ID | Higher | Never treat raw body `client_id` as proof |
| Per grant | Authenticated client + parsed grant type | Depends on parsing/validation | Avoid splitting keys excessively and exploding cardinality |
| Per tenant / workload | Authenticated client + trusted tenant | High if tenant binding is verified | Never trust self-asserted tenant IDs blindly |
| Per credential failure | Source + error category / safe credential identifier | Needs privacy review | Never store raw secrets or JWT assertions as cache keys |

Illustrative policy structure:

```text
Layer A: ingress source -> limit total requests before authentication
Layer B: authenticated client -> token request quota
Layer C: authenticated client + grant -> per-grant quota
Layer D: signing/DB dependency -> max concurrency and deadline
```

Limits must work together. If only Layer B is deployed, requests carrying wrong secrets **never reach authenticated-client state** and can still burn verification CPU without per-client throttling.

### 5.1. Avoid Unbounded Metric Cardinality

Never put raw IPs, `client_secret`, refresh tokens, or arbitrary client-generated identifiers into metric labels. Prometheus and similar metric backends degrade severely when millions of distinct label values appear.

For detailed security audits, store normalized source identifiers with proper retention and access controls; aggregate metrics should group by grant, outcome, endpoint, or bounded client groups.

## 6. Common Rate-Limiting Algorithms

### 6.1. Token Bucket

A token bucket has:

- `capacity = B`: how many requests can be served in a short burst.
- `refillRate = r`: how many tokens are replenished per second.
- A valid request consumes tokens; if insufficient tokens remain, the request is rejected.

```mermaid
flowchart LR
    IN["Token Request"] --> BUCKET{"Bucket has tokens?"}
    BUCKET -->|"Yes"| TAKE["Deduct token atomically"] --> PROCESS["Continue pipeline"]
    BUCKET -->|"No"| LIMIT["429 + Retry-After"]
    REFILL["Time-based refill"] --> BUCKET
```

A token bucket permits small **bursts** while enforcing the configured average rate. For example, `B=20` and `r=2 requests/sec` allows roughly 20 requests immediately when full, then replenishes 2 tokens/sec.

This is an **illustrative model**, not a universal production quota. Choose `B` and `r` from observed baselines and tolerable backend load.

### 6.2. Sliding Window and Fixed Window

| Mechanism | Strengths | Limitations |
|---|---|---|
| **Fixed window** | Simple, cheap to compute | Allows double-rate bursts across window boundaries |
| **Sliding window** | Smooths boundary spikes, fairer | Requires more complex state/timestamp tracking |
| **Token bucket** | Supports controlled bursts and steady averages | Requires atomic state updates |
| **Leaky bucket / queue** | Smooths traffic in some architectures | Long queues inflate latency and consume memory |
| **Concurrency semaphore** | Caps simultaneous heavy tasks | Does not bound total requests over time by itself |

Avoid unbounded queues in front of a sensitive endpoint. Requests waiting too long still hold resources and cause clients to retry, multiplying duplicate requests.

### 6.3. Weighted Cost for Different Operations

A local client-secret check has a very different cost from:

- Verifying a public-key client assertion and fetching JWKS.
- Looking up a refresh token in the database.
- Calling remote introspection on a subject token.
- Signing tokens via HSM/KMS.
- Persisting authorizations inside a transaction.

You can apply **weighted costs** per grant or execution path after parsing and validating required attributes. For instance, a remote signing flow consumes more quota than an early rejected check.

Test this carefully, as attackers may send expensive grant types to burn shared quotas faster. Cost classification must rely on trusted signals and anti-quota-poisoning rules.

## 7. Rate Limiting in Multi-Instance Environments

If the Token Endpoint runs across 5 pods and each pod enforces an independent local bucket of 100 requests/minute, cluster-wide throughput can reach 500 requests/minute as the load balancer spreads traffic.

### 7.1. Two Operational Models

**Model A — Local per-node limiter:**

- Fast, zero network dependency.
- Useful for protecting local CPU and threads.
- **Does not enforce cluster-wide quotas**, especially during autoscaling.

**Model B — Shared/distributed limiter:**

- State/quotas are shared across nodes, e.g., gateway distributed rate limiting or Redis with atomic operations.
- Suitable for true cluster-wide per-client quotas.
- Must handle Redis outages, replication lag, key cardinality, and cross-region consistency.

With Redis, non-atomic "read counter → increment → write back" sequences allow quota overruns under concurrent nodes. Prefer atomic scripts/transactions or battle-tested rate limiters.

### 7.2. Fail-Open or Fail-Closed When the Limiter Store Fails?

There is no single universal answer:

| Mode | Behavior When Limiter Unavailable | Risk |
|---|---|---|
| **Fail-open** | Allows requests to proceed | Increases load and creates an abuse window, especially during attacks |
| **Fail-closed** | Rejects/throttles requests | Can cause a total client outage even when the AS is healthy |
| **Local fallback quota** | Falls back to per-node limits | Cluster quota drifts; requires capacity planning and alerts |

Always separate an **optional ingress limiter** from **mandatory client authorization policies**. A failure in client authentication or validation services must never "fail open" merely for availability.

### 7.3. Zones and Regions

Multi-region rate limiting often exhibits **eventual consistency**; quotas look global yet drift during network partitions. Where hard caps are mandatory, design consistency and cost models explicitly rather than promising exact global quotas over asynchronous cache replication.

## 8. Quota Policies by Grant and Client Type

A system might define reference policies such as:

| Request Group | Example Legitimate Need | Control Guidance |
|---|---|---|
| **Client Credentials** | Background services fetching tokens periodically | Encourage access token caching; detect token storms |
| **Authorization Code** | Callbacks after user login | Allow short bursts, protect codes/PKCE; avoid rate limits breaking mass logins |
| **Refresh Token** | Clients renewing access tokens | Control rate, replay, and rotation state |
| **Token Exchange** | Services requesting downstream API tokens | Enforce target/subject policies and validation cost |
| **JWT `private_key` authentication** | Clients signing assertions per token request | Bound CPU/JWKS lookups, cache trusted keys |
| **Extension grants** | Custom domain grant flows | Dedicated quotas matching cost and threat model |

Illustrative starter policy **for demonstration only**:

```yaml
token-endpoint:
  limits:
    ingress-per-source:
      burst: 100
      refill-per-second: 10
    authenticated-client:
      burst: 60
      refill-per-second: 3
    expensive-grant:
      max-concurrent: 8
```

**This is hypothetical business YAML**, not a property automatically recognized by Spring Authorization Server or Spring Boot. Applying it requires implementing the corresponding limiter/gateway and tuning via load testing.

### 8.1. Do Not Prioritize Critical Clients by Disabling All Limits

A critical service may deserve a higher quota or reserved capacity. However, "unlimited" access on the Token Endpoint allows one buggy client to saturate the entire HSM, database pool, or thread pool.

Use **fair scheduling**, client-tier quotas, and bulkheads; under overload, reserve capacity for high-priority requests per policy without ever skipping authentication.

### 8.2. Count Successful Requests or All Requests?

Counting only **successful token issuances** lets credential stuffing with wrong secrets bypass quotas completely. Sharing one global quota across unauthenticated requests lets an attacker lock out a legitimate client by sending fake requests bearing its `client_id`.

Instead, maintain:

- Pre-auth quotas counting **all incoming requests** by trusted network source.
- Post-auth quotas counting requests by **authenticated client**.
- Separate counters/anomaly detectors for **authentication failures** and grant errors, without letting unauthenticated traffic permanently lock out another client.

## 9. HTTP 429, `Retry-After`, and OAuth Errors

HTTP `429 Too Many Requests` tells the client it exceeded rate limits. The `Retry-After` header can specify how long to wait before retrying.

Example:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 15
Cache-Control: no-store
Content-Type: application/json

{
  "error": "rate_limited"
}
```

**Compatibility note:** `rate_limited` in this example is an **extension error code**, not part of the standard RFC 6749 OAuth 2.0 Token Endpoint error set. If an API/gateway emits it, clients must be designed to handle that response. Some OAuth client libraries expect OAuth-shaped error bodies on non-2xx responses; test compatibility and document the contract publicly.

### 9.1. Do Not Mix Security Errors with Overload Errors

| Scenario | Appropriate Response | Notes |
|---|---|---|
| Wrong client credentials | OAuth `invalid_client`; typically HTTP 401 when applicable | Never say "secret wrong at character 3" |
| Invalid/expired/used authorization code | `invalid_grant` | Issue no token; enforce single-use |
| Client not permitted to use grant | `unauthorized_client` | Do not convert into a rate-limit error |
| Disallowed scope | `invalid_scope` | Never self-escalate permissions |
| Missing/invalid request parameter | `invalid_request` | Expose no internal details |
| Request quota exceeded | `429` + `Retry-After` when possible | Clients must perform bounded retries |
| AS/dependency temporarily overloaded | `503 Service Unavailable` or infrastructure error | Protect capacity; prevent retry storms |
| Request exceeds processing deadline | Timeout/`504` at proxy or appropriate error | Uncertain whether a token was issued |

Layer ordering affects observed errors: a request blocked at the ingress limiter **before client authentication** returns 429 even if its credentials were also wrong. That is an intentional overload-protection trade-off, not a sign that validators were bypassed for requests proceeding into the pipeline.

### 9.2. `slow_down` Is Not a Generic Rate-Limit Code

The OAuth Device Authorization Grant defines `slow_down` specifically for polling per RFC 8628. Do not reuse `slow_down` as a general rate-limiting code across **all** `grant_type` values at the Token Endpoint.

### 9.3. Limitations of `Retry-After`

`Retry-After` can hold **delay seconds** or an **HTTP-date** per HTTP specs. Clients should respect valid values and combine backoff with jitter, never retrying endlessly or sharing an unbounded retry loop across workers.

When quotas are per-client or per-tenant, avoid returning details that reveal client lists or other tenants' quota states.

### 9.4. Never Include Tokens in Errors

429 and 5xx responses must never contain `access_token`, `refresh_token`, `authorization_code`, client secrets, or stack traces. Never attach debug response headers containing raw credentials.

## 10. Timeouts: Set Deadlines Per Layer, Not Just One Property

A single token issuance request may traverse gateway → servlet container → Spring Security → authentication provider → database/cache → KMS/HSM signer → response.

```mermaid
flowchart LR
    G["Gateway deadline"]
    S["Servlet request budget"]
    D["DB/Redis operation timeout"]
    K["KMS/HSM/remote JWT/JWKS timeout"]
    O["Outcome / cancellation / monitoring"]

    G --> S --> D --> K --> O
```

This diagram does not imply every dependency call runs sequentially; real systems may execute dependency calls in parallel.

### 10.1. Easily Confused Timeouts

| Timeout Type | What Does It Protect? | What Does It Not Guarantee? |
|---|---|---|
| **TLS handshake / connection timeout** | Prevents new connections from hanging indefinitely | Does not bound business logic once inside the endpoint |
| **Proxy idle / read timeout** | Guards against slowloris clients or stalled sockets | Does not automatically cancel DB work after the proxy drops the request |
| **Gateway upstream response timeout** | Caps how long the gateway waits for the AS | Does not ensure AS DB/HSM calls stopped running |
| **Servlet async request timeout** | Bounds servlet async request handling | Does not act as a global deadline for synchronous filters/controllers |
| **DB statement / query timeout** | Caps runaway SQL queries | Does not time out remote KMS calls or the entire request |
| **Connection-pool acquire timeout** | Caps waiting for a DB connection | Does not replace query timeouts once a connection is acquired |
| **HTTP client connect / read timeout** | Bounds remote introspection/JWKS/IdP/KMS HTTP calls | Does not make external requests idempotent |
| **Concurrency / bulkhead timeout** | Caps waiting for an execution slot | Does not replace OAuth validation |

Specifically, `server.tomcat.connection-timeout` typically governs socket connection/read waiting at the servlet container. **Never mistake it for "the Token Endpoint will finish within N seconds."**

### 10.2. Designing a Time Budget

Suppose the gateway enforces a 4-second response deadline. An illustrative budget:

| Component | Reference Target Limit |
|---|---|
| Total time to client | 4 seconds |
| AS processing before heavy dependencies | Small budget with capacity guards |
| DB connection acquire | Max 300 ms |
| Critical DB query | Max 800 ms |
| Remote signer / KMS | Max 1 second |
| Remote trust lookup (if any) | Max 500 ms |
| Serialization / network headroom | Enough margin below the total deadline |

**These numbers are illustrative only**, not Spring defaults. Total latency is not simple addition when operations run in parallel, retry, or span transactions. Set end-to-end deadlines from SLOs, measure p95/p99 latency distributions, and bound queues.

Rule of thumb: **dependency timeouts must fit within the remaining total deadline**, rather than letting every layer wait another 30 seconds independently. If the gateway aborts after 4 seconds while a DB query keeps running for 30 seconds, "orphan" work continues draining capacity.

### 10.3. Is `@Transactional(timeout=...)` a Full Request Timeout?

No. Transaction timeouts apply to specific persistence/business boundaries and depend on the transaction manager and JDBC driver. They do not cover overall HTTP handling, client credential verification, KMS signing, or servlet threads.

Configure timeouts on each dependency explicitly, paired with capacity limits and cancellation wherever supported. When running tasks cannot be canceled, cap concurrency so resources cannot be exhausted.

## 11. Configuring `SecurityFilterChain` in Spring Authorization Server

An Authorization Server typically has:

- **AS chain** handling OAuth/OIDC protocol endpoints.
- **Login chain** handling End-User authentication when Authorization Code needs it.
- **Admin API chain** if client management has its own interface.

For the Token Endpoint, HTTP protections can be attached to the **AS chain** without replacing `OAuth2TokenEndpointFilter` or `OAuth2ClientAuthenticationFilter`.

Example structure using the modern configurer API:

```java
@Configuration
@EnableWebSecurity
class AuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(
            HttpSecurity http,
            TokenEndpointRateLimitFilter tokenRateLimitFilter)
            throws Exception {

        OAuth2AuthorizationServerConfigurer as =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(as.getEndpointsMatcher())
            .with(as, Customizer.withDefaults())
            .addFilterAfter(
                tokenRateLimitFilter,
                SecurityContextHolderFilter.class);

        return http.build();
    }
}
```

**This is a filter integration template**, not a full Authorization Server configuration. You must still provide registered clients, authentication services, authorization/consent services, issuer, signing keys/JWKs, login chain, and OIDC features as needed.

Placing the filter after `SecurityContextHolderFilter` anchors it to a public Spring Security order position; **verify actual filter ordering** on your dependency version, especially to confirm the limiter runs before heavy client authentication work as intended. The strongest ingress protection usually sits at the gateway/proxy before traffic ever reaches the servlet container.

### 11.1. Do Not Modify Protocol Filters to Add Rate Limiting

Replacing `OAuth2TokenEndpointFilter` just to insert a counter risks accidentally bypassing:

- Client authentication.
- Grant validation and scope policies.
- PKCE and authorization code replay validation.
- Refresh token rotation and reuse detection.
- Token persistence and issuance semantics.
- OAuth error responses and headers.

**Prefer:** gateways, narrowly scoped cross-cutting HTTP filters, framework-exposed authentication/policy hooks, or a dedicated quota service. When limiting by authenticated client, rely strictly on the verified identity.

## 12. Example Pre-Auth Client Rate-Limiting Filter

The following example illustrates a **pre-auth limiter**. It applies only to `POST /oauth2/token`, resolves the source address from trusted infrastructure, and rejects early when quota is exceeded.

`TokenRateLimitStore` and `TrustedClientAddressResolver` are **application-defined abstractions**, not built-in Spring Authorization Server beans. Production implementations must supply Redis/gateway/local policies, quotas, and store error handling.

```java
interface TokenRateLimitStore {
    RateLimitDecision consume(String key);
}

interface TrustedClientAddressResolver {
    String resolve(HttpServletRequest request);
}

record RateLimitDecision(boolean permitted, long retryAfterSeconds) {
}

public final class TokenEndpointRateLimitFilter
        extends OncePerRequestFilter {

    private final TokenRateLimitStore store;
    private final TrustedClientAddressResolver addressResolver;
    private final String tokenPath;

    public TokenEndpointRateLimitFilter(
            TokenRateLimitStore store,
            TrustedClientAddressResolver addressResolver,
            String tokenPath) {
        this.store = store;
        this.addressResolver = addressResolver;
        this.tokenPath = tokenPath;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !"POST".equals(request.getMethod())
            || !tokenPath.equals(request.getServletPath());
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String source = addressResolver.resolve(request);
        RateLimitDecision decision =
            store.consume("token:ingress:" + source);

        if (!decision.permitted()) {
            response.setStatus(429);
            response.setHeader(
                "Retry-After",
                Long.toString(Math.max(1, decision.retryAfterSeconds())));
            response.setHeader("Cache-Control", "no-store");
            response.setHeader("Pragma", "no-cache");
            response.setCharacterEncoding("UTF-8");
            response.setContentType("application/json");
            response.getWriter().write(
                "{\"error\":\"rate_limited\"}");
            return;
        }

        chain.doFilter(request, response);
    }
}
```

**Limitations of this example:**

1. Uses **Java 17+** for `record`; servlet and Spring imports are omitted.
2. This filter **does not authenticate clients**. It only throttles ingress ahead of OAuth processing.
3. `tokenPath` should come from actual endpoint configuration (e.g., `AuthorizationServerSettings`) or unified policy; `/oauth2/token` is merely the common default.
4. Test `getServletPath()` when using context paths, servlet mappings, gateway path rewrites, or custom endpoints.
5. `addressResolver` must enforce trusted proxy policies; never trust raw `X-Forwarded-For` sent by arbitrary callers.
6. `store.consume(...)` must update quotas **atomically**, with an explicitly defined store failure mode.
7. `rate_limited` is a **non-standard OAuth error extension**, requiring an agreed client contract or system-wide 429 format.
8. Test filter order and verify the filter runs **exactly once**; do not rely blindly on Spring Boot auto-registration defaults.

### 12.1. Avoiding Double Registration of Servlet Filters

When `TokenEndpointRateLimitFilter` is a Spring bean implementing `Filter`, Spring Boot may auto-register it with the servlet container. If you also add it to a `SecurityFilterChain`, it can execute outside the intended chain scope or run unexpectedly.

If the filter is declared as a bean and should be managed solely by Spring Security, disable servlet auto-registration:

```java
@Bean
FilterRegistrationBean<TokenEndpointRateLimitFilter>
disableServletRegistration(TokenEndpointRateLimitFilter filter) {

    FilterRegistrationBean<TokenEndpointRateLimitFilter> registration =
        new FilterRegistrationBean<>(filter);

    registration.setEnabled(false);
    return registration;
}
```

This snippet illustrates registration control only and omits the filter bean and limiter dependencies. Verify the exact auto-registration mechanics of your Spring Boot version.

### 12.2. Does This Filter Protect Against Every Overload Pattern?

No. This filter counts only **ingress requests**. If an attacker distributes traffic across many IPs, a source-based limiter may miss the aggregate spike. If an authenticated client submits grants with expensive signing work, you still need per-client quotas and a **concurrency guard** directly ahead of the expensive operations.

Furthermore, when 429 responses occur at the gateway **before reaching Java**, the application filter never sees those requests; dashboards must combine gateway and AS metrics.

## 13. Trusting IP Addresses Behind Reverse Proxies

A dangerous bug is reading this header directly:

```java
// DO NOT use as a trusted identity without a trusted proxy policy.
String source = request.getHeader("X-Forwarded-For");
```

An attacker can forge that header and rotate values on every request to bypass quotas or corrupt audit trails.

The right approach depends on topology:

- Accept requests only from authorized load balancers/gateways.
- At the trust boundary, **strip or normalize** forwarded headers sent by external callers.
- Trust proxy header chains only from verified hops.
- Implement `TrustedClientAddressResolver` to match your actual infrastructure.
- Without a trusted proxy, `request.getRemoteAddr()` reflects the direct network peer; behind a gateway, it may reflect only the gateway's IP.
- For IPv6, consider prefix grouping/normalization so rotating interface IDs cannot easily evade limits.

**Never trust caller-supplied headers like `X-Client-Id` to identify an OAuth client.** OAuth client identity must be established by the proper client authentication mechanism.

## 14. Limiting by Authenticated Client

Pre-auth limiters shed initial load, yet they do not guarantee **fairness among valid clients**. A single authenticated client could still send more Token Endpoint requests than all other clients combined.

### 14.1. Must Use the Authenticated Client Identity

In Spring Authorization Server, client authentication is represented by `OAuth2ClientAuthenticationToken` and its providers. Per-client quota policies must rely solely on verified client details or repository metadata linked to the authenticated result.

Illustrative business key:

```text
authenticated-client:
  registeredClientInternalId = "rc-7f9a"
  tenant = "tenant-a"  (already verified)
  grantType = "client_credentials"

quotaKey = "token:client:rc-7f9a:grant:client_credentials"
```

This is a **key model**, not Java code built into Spring Authorization Server. Tenant checks, client registration lookups, and quotas must live in trusted policies/services.

### 14.2. Policy Enforcement Points

Consider:

- Gateway policies keyed by a verified identity, if the gateway genuinely performs/verifies client authentication.
- An `AuthenticationProvider`/Token Endpoint hook published by Spring Authorization Server, ordered properly without bypassing standard providers.
- A domain service invoked by the provider after client authentication and before token issuance.
- A dedicated admission-control layer ahead of the signer and authorization persistence.

**Never add a custom provider and simply assume it runs before default providers.** `AuthenticationManager` ordering and `supports(...)` determine which provider runs. Test hooks and filter chains on your exact version.

### 14.3. Check Quotas Before or After Validation?

Cheap checks (request format, allowed grant types) should fail fast to save resources. However, counting only **fully authenticated and valid requests** still lets attackers flood wrong credentials and burn provider CPU.

Therefore, prefer **pre-auth admission + post-auth per-client quotas + dependency concurrency guards**. Tune exact ordering from real measurements rather than one rigid rule for every grant.

## 15. Protecting Each Grant and Preventing Replay

### 15.1. Authorization Code + PKCE

Typical threats:

- Attempting to exchange guessed codes or another client's codes.
- Reusing an already-exchanged code.
- Missing/invalid `code_verifier`, brute-forcing verifiers.
- Supplying a redirect URI that mismatches the authorization request.

Core protections:

- High-entropy, short-lived, **single-use** codes.
- PKCE S256 where applicable, especially for public clients.
- Client authentication for confidential clients.
- Binding codes to client, redirect URI, and original authorization.
- Reasonable quotas on token exchange; never lengthen code TTLs to paper over rate-limit issues.

**Never relax single-use guarantees** for retries. Once a client sends a Token Request, a network timeout can leave it unsure whether the server succeeded. Resubmitting the code can legitimately trigger `invalid_grant` per design.

### 15.2. Refresh Token

Typical threats:

- Guessing refresh tokens or redeeming revoked tokens.
- Reusing an old refresh token after rotation.
- Refresh storms from uncached clients.
- Cross-node replay races.

Protections:

1. Persist and verify refresh token state via `OAuth2AuthorizationService` or equivalent.
2. Enforce refresh token rotation/reuse policies appropriate for the client and grant.
3. Rate-limit both successful and anomalous requests, not just newly minted access tokens.
4. When reuse is detected, decide how to revoke the token family/session per threat model.
5. Never log refresh tokens; test concurrent refresh races.

**Never carve out exceptions allowing expired refresh tokens to be reused**, as doing so undermines the token lifecycle.

### 15.3. Client Credentials

M2M services should not request a new token for every API call. Cache access tokens client-side and refresh proactively before `expiresAt` using jitter and backoff.

If 500 instances boot simultaneously and all request tokens at once, pre-auth/per-client limiters can throttle legitimate traffic. Client designs need:

- `OAuth2AuthorizedClientManager` and an appropriate client credentials provider.
- Reusing valid tokens, keyed by registration/workload.
- Clock skew margins and jitter to spread refreshes.
- Single-flight coordination so an instance does not send duplicate concurrent requests.
- Bounded retries on 429/5xx; no infinite retries on `invalid_client`.

### 15.4. Extension Grants and Token Exchange

Extension grants may verify JWT assertions, subject tokens, or external identities:

- Cap assertion sizes and form body sizes.
- Restrict supported token types, issuers, and audiences.
- Cache trusted JWKs safely, guarding against SSRF or arbitrary URL fetches.
- Set timeouts on remote introspection/JWKS/KMS calls.
- Never trust a token merely because its payload parses.
- Apply quotas per authenticated client and grant cost to prevent token-issuance amplification.

When using RFC 8693 Token Exchange, validate target `audience`/`resource`, scope attenuation, and client authorization; rate limiting never replaces privilege-escalation controls.

## 16. Anti-Abuse Controls Beyond Rate Limiting

### 16.1. Bounding Request Sizes and Parameter Counts

The Token Endpoint typically reads `application/x-www-form-urlencoded`. Malicious requests can carry oversized bodies, many duplicate parameters, or unusually long assertions.

Cap at the edge/servlet layer:

- Total request body and header sizes.
- Number of form parameters and maximum per-parameter size.
- Request body read timeout.
- Permitted Content-Types and HTTP methods.
- Counts/lengths of scopes, audiences, and JWT assertions per policy.

**Never let rate limiting run only after the container has buffered tens of megabytes of body**; size limits and timeouts at the proxy/connector must reject early.

### 16.2. Do Not Leak Client Information Through Errors

A system can inadvertently leak:

- Whether a Client ID exists.
- Which client authentication method is configured.
- Partial or near-miss secret guesses.
- Confidential grants/scopes of another client.
- Which tenant or user owns a refresh token.

Keep public error responses OAuth-compliant; log details only to access-controlled security audits. Avoid huge response-time disparities between existing and nonexistent clients where constant-time crypto and uniform baselines can reduce side channels.

### 16.3. Stopping Credential Stuffing Without DoS-ing Victims

Never permanently lock out a client simply because an attacker sent thousands of failed requests claiming its `client_id`. Consider:

- Rate-limiting unauthenticated network sources.
- Quotas per credential/client **after authentication**.
- Adaptive throttling driven by combined risk signals rather than self-asserted usernames or client IDs.
- Alerting and investigating spikes in authentication failures.
- Audited recovery/override procedures for critical services.
- Strong credentials, rotation, and asymmetric/mTLS methods like `private_key_jwt` or mTLS where warranted.

### 16.4. TLS, Secrets, and Token Leakage

- Enforce HTTPS on the Token Endpoint outside controlled local dev environments.
- Never put client secrets or tokens in URLs.
- Never log `Authorization` headers or Token Request form bodies.
- Protect signing keys, JWKS/secret managers, and DB credentials.
- Enforce safe HTTP caching rules on token responses (such as `Cache-Control: no-store`).
- Never add middleware that logs every token response "for performance debugging."

## 17. Timeouts, Circuit Breakers, and Bulkheads for Dependencies

### 17.1. Database / Authorization Store

`OAuth2AuthorizationService` reads and writes authorization codes, refresh tokens, and token metadata. Ensure:

- Properly sized connection pools with bounded acquire timeouts.
- Query/statement timeouts aligned with SLOs.
- Schema/version-appropriate indexes.
- Short transactions that avoid holding locks unnecessarily.
- Concurrency tests for simultaneous code exchange or refresh token races.
- Load shedding before connection pools saturate.

**When the DB slows down, adding more HTTP threads usually makes things worse.** Cap concurrency, watch queue wait times, and shed non-essential work.

### 17.2. Signer / JWK / KMS / HSM

When signing JWTs via HSM/KMS or a remote signer:

- Use a dedicated timeout on signing operations.
- Cap concurrent signing requests.
- Cache **public key metadata** and trusted discovery outputs when allowed; never casually cache private keys.
- Allow only policy-approved algorithms/keys; never fall back to weak keys when the signer errors.
- Monitor KMS/HSM rate limits and quotas.
- When the signer is unavailable, **never issue unsigned tokens or skip verification** to keep availability up.

### 17.3. Remote Identity / Introspection

If a custom grant or client auth depends on external IdP/JWKS/introspection services:

- Call only trusted, configured endpoints to prevent SSRF.
- Enforce connect/read timeouts and retry caps.
- Separate cached metadata from time-sensitive token validity data.
- Never trust a token just because a remote endpoint timed out; trust checks **must never fail open**.
- Consider circuit breakers to protect the system during sustained downstream outages.

### 17.4. Retries Can Multiply Load Dramatically

If every layer (gateway, AS, KMS HTTP client) retries up to 3 times, one incoming request can trigger exponential downstream traffic. Define clear **retry ownership** and total deadlines rather than enabling default retries at every layer.

Especially at the Token Endpoint, requests **are not always idempotent**. Retrying Authorization Code Grant after an ambiguous timeout can return `invalid_grant` because the code was already consumed. Refresh token rotation can similarly turn retries with the old token into policy-flagged replays.

## 18. Guiding OAuth Clients on 429 and Outages

A well-protected Token Endpoint is only half the solution. If clients keep retrying 100 times per second after receiving 429, the AS still faces overload.

### 18.1. Client Principles

1. **Reuse valid tokens**; never request a token for every API call.
2. On 429, honor a valid `Retry-After` header.
3. Use exponential backoff + jitter with a strict retry cap.
4. Enforce an **overall business deadline**.
5. Never retry indefinitely on `invalid_client`, `invalid_grant`, or `invalid_scope`.
6. Never automatically retry non-idempotent requests when the prior attempt's completion state is unknown.
7. Use circuit breakers during AS outages to prevent request storms.
8. Alert when cached tokens approach expiration without successful renewal.

### 18.2. Pseudocode for Bounded Retries

```text
function acquireToken():
    if cachedToken has enough lifetime:
        return cachedToken

    for attempt in 1..MAX_ATTEMPTS:
        response = tokenEndpointRequest(deadlineRemaining)

        if success:
            cache token until safe expiry
            return token

        if oauthError in {invalid_client, invalid_grant,
                          unauthorized_client, invalid_scope}:
            fail without blind retry

        if response is 429 or transient 503:
            delay = retryAfter or boundedExponentialBackoffWithJitter
            if delay exceeds remaining deadline:
                fail
            wait(delay)
            continue

        fail

    fail with controlled error
```

**This is pseudocode**, not Spring library code. For grants involving authorization codes or refresh rotation, base retry behavior on transaction semantics; an ambiguous error response does not justify blindly reusing the same credential.

### 18.3. `Retry-After` Is Not an Exact Synchronized Schedule

Many clients may receive `Retry-After: 10` together and all retry at second 10. Combining jitter with upper bounds avoids synchronized waves while respecting the contract's minimum wait and system SLAs.

## 19. Observability: Tracking Abuse Without Leaking Data

### 19.1. Recommended Metrics

| Metric | Purpose |
|---|---|
| Token Endpoint RPS by grant and outcome | Separates legitimate load from invalid traffic |
| HTTP 429 rate and total denied requests | Evaluates quota effectiveness and false positives |
| HTTP 401/400/5xx rates | Detects auth failures, grant failures, and outages |
| `invalid_client`/`invalid_grant` rates | Alerts on credential stuffing/replay and integration bugs |
| p50/p95/p99 latency | Tracks client experience and dependency health |
| In-flight request count | Detects concurrency exhaustion |
| Queue wait time | Predicts overload before 5xx spikes |
| DB pool wait/timeouts | Pinpoints persistence bottlenecks |
| Redis limiter timeouts/errors | Monitors rate-limiter health |
| Signing/KMS latency/errors | Pinpoints token-issuance bottlenecks |
| Client Credentials acquisition rate | Detects uncached clients or stampedes |
| Refresh token reuse detections | Detects replay behavior per policy |

### 19.2. Appropriate Audit Events

Safe to store:

- Event types: `TOKEN_REQUEST_LIMITED`, `CLIENT_AUTH_FAILURE`, `GRANT_REJECTED`, `TOKEN_ISSUED`, `DEPENDENCY_TIMEOUT`.
- Timestamp, correlation ID, and environment.
- Grant type, **verified** client identity, and normalized source/network signals.
- Policy name or quota bucket, recommended wait duration.
- Latency, outcome, and non-sensitive error categories.
- Active limiter or policy configuration version.

Never store:

- Client secrets, private keys, or raw JWT assertions.
- Authorization codes, `code_verifier`, access tokens, or refresh tokens.
- Unredacted `Authorization` headers, cookies, or request bodies.
- SQL queries containing token values or stack traces in responses.
- Arbitrary unbounded-cardinality identifiers in metric labels.

### 19.3. Distinguishing Attacks from Deployment Bugs

A spike in `invalid_client` right after deployment could mean:

- Unsynchronized secret rotation updates.
- Client config pointing to the wrong issuer or token URI.
- Clock skew expiring client assertions.
- Broken token caching driving up request volume.
- A credential-guessing attack.

Investigation should correlate deploy timestamps, client versions, grant types, sources, and dependency metrics. Never lock out critical clients solely on a raw failure threshold without a clear runbook or policy.

## 20. Testing Rate Limits, Timeouts, and Anti-Abuse Controls

### 20.1. Protocol Test Matrix

| Scenario | Setup | Outcome to Prove |
|---|---|---|
| Valid request under quota | Valid client credentials / authorization code | Token Endpoint succeeds normally without limiter interference |
| Exceeding ingress quota | Multiple POSTs from same normalized source | `429`, `Retry-After`, and zero tokens issued |
| Under quota with wrong secret | Invalid client credentials | Compliant OAuth `invalid_client` |
| Spoofing victim `client_id` | Attacker lacks credentials | Cannot exhaust victim's **post-auth** quota |
| Spoofing `X-Forwarded-For` | Forged header from Internet | Cannot bypass limiter via untrusted header |
| Multiple clients behind NAT | Valid clients sharing an IP | Quotas/false positives remain within policy tolerance |
| Public vs. confidential clients | Different grants/methods | Never apply one client-auth assumption to both |
| Authorization code replay | Exchange same code twice | Token issued at most once |
| Invalid PKCE | Wrong `code_verifier` | Rejected regardless of quota |
| Refresh token reuse | Old token after rotation | Enforces reuse/revocation policy |
| Disallowed scope/grant | Requesting scope or grant outside registration | Standard OAuth error; never grants silently |
| Oversized form request | Body/headers/params exceed caps | Rejected early without memory exhaustion |
| HTTP `GET /oauth2/token` | Wrong HTTP method | Zero tokens issued |
| Token Endpoint overloaded | Concurrency slots exhausted | Controlled rejection without unbounded queuing |

### 20.2. Timeout / Dependency Test Matrix

| Scenario | Behavior to Verify |
|---|---|
| DB connection pool exhausted | Never hangs forever; timeout/bulkhead triggers |
| Slow authorization query | Query timeout and metrics fire; code state stays intact |
| KMS signer timeout | Never emits unsigned or invalid JWTs |
| Remote JWKS/introspection timeout | Never treats unverified tokens as valid |
| Limiter store failure | Fail-open/closed/fallback matches design, with alerts |
| Gateway times out before AS | Monitor whether background work keeps draining resources |
| 100 concurrent requests | Never exceeds configured concurrency limit |
| Multi-node load test | Cluster-wide quota honors agreed consistency guarantees |
| Redis failover/partition | Does not corrupt quota state or trigger unexpected outages |
| Rolling upgrade deployment | Limiter config/version and token policies remain consistent |
| Retry storm during AS recovery | Client backoff/jitter prevents traffic spikes beyond capacity |

### 20.3. Testing the Distinction Between 429 and OAuth Errors

With `MockMvc` or HTTP integration tests:

1. Configure a test limiter with deterministic quotas, avoiding reliance on wall-clock time where possible.
2. Send a valid `client_credentials` request under quota and verify the token response.
3. Send requests exceeding quota and verify **HTTP 429**, `Retry-After`, and zero tokens.
4. Send a wrong-secret request under quota and verify **`invalid_client`** per contract.
5. Verify quota-exceeded requests **do not invoke token generators** or heavy DB providers if the limiter runs upfront.
6. Verify the filter executes once in the right chain without duplicate servlet-container execution.
7. Send requests to other endpoints like `/oauth2/authorize` to confirm the Token Endpoint limiter does not block them accidentally.
8. Across multiple instances, verify shared bucket keys sync properly or behave as documented.

Conceptual test example:

```java
@Test
void overQuotaTokenRequestReturns429() throws Exception {
    // Assumes test fixture causes TokenRateLimitStore to return
    // RateLimitDecision(permitted=false, retryAfterSeconds=10).

    mockMvc.perform(post("/oauth2/token")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("grant_type", "client_credentials"))
        .andExpect(status().isTooManyRequests())
        .andExpect(header().string("Retry-After", "10"));
}
```

The test requires proper security chain configuration, mock store, and beans. It proves only the **HTTP limiter response**; full integration tests must also cover client authentication and grants when requests are permitted.

### 20.4. Performance and Fairness Testing

Simulate three profiles:

- Client A: normal traffic needing login and code exchange.
- Client B: heavy but legitimate M2M traffic with token caching.
- Attacker: bogus credentials or forged refresh tokens.

Measure whether the limiter:

- Preserves minimum throughput for Client A.
- Prevents Client B from monopolizing capacity even though it is legitimate.
- Blocks the Attacker before KMS/DB pools saturate.
- Avoids spiking 429s for Client A when sharing a NAT with the Attacker.
- Maintains p95/p99 latency without unbounded queue backlogs.

This is the evidence needed before locking production quotas; a single token-bucket unit test does not prove system-wide DoS resilience.

## 21. Incident Response Playbook When the Token Endpoint Is Attacked or Overloaded

1. **Identify symptoms:** rising RPS, 429/5xx spikes, `invalid_client`/`invalid_grant` surges, slow queues/DB/HSM.
2. **Isolate sources:** break down by ingress IP/network, authenticated client, grant type, tenant, route, and deployment version.
3. **Protect capacity:** enable or tighten edge rate limits and controlled concurrency guards.
4. **Prioritize critical clients:** apply tiered policies/quotas; never disable validation.
5. **Assess credentials:** if secret/JWT assertion compromise is suspected, revoke/rotate per runbook and audit issued tokens.
6. **Curb retry storms:** emit `Retry-After`/backoff guidance for clients and spot misconfigured client libraries.
7. **Check dependencies:** DB pools, Redis limiters, HSM/KMS, JWKS, remote introspection, and network links.
8. **Preserve evidence:** rely on audits and correlation IDs; never capture raw tokens/secrets "for debugging."
9. **Recover:** gradually relax temporary limits under close monitoring while checking token issuance and OAuth compliance.
10. **Prevent recurrence:** add regression/load tests, tune quotas, improve client caching, and update runbooks.

If the outage stems from the limiter store itself, follow an approved fallback plan. Never bypass client authentication, PKCE, or token validation just for a "quick recovery."

## 22. Production Deployment Checklist

- [ ] Token Endpoint runs over HTTPS and matches accurately in `SecurityFilterChain`.
- [ ] Edge enforces connection limits, request body caps, header/parameter limits, and slow-client timeouts.
- [ ] Pre-auth ingress limiter uses source identities resolved from trusted proxies.
- [ ] Post-auth quotas apply per **verified client identity** and grant type.
- [ ] Quotas never rely solely on self-asserted `client_id` or untrusted `X-Forwarded-For`.
- [ ] Limiters use atomic updates with a consistent multi-instance/multi-region strategy.
- [ ] Both **rate** and **concurrency** are bounded around heavy DB and signing work.
- [ ] Timeouts are configured for DB pools/queries, signers/KMS, remote introspection/JWKS, and network hops.
- [ ] Timeouts align with end-to-end SLOs/deadlines without confusing connector timeouts for request timeouts.
- [ ] No unbounded queues or uncontrolled cascading retries across layers.
- [ ] OAuth `invalid_client`/`invalid_grant`/`invalid_scope` are never replaced with arbitrary custom messages.
- [ ] Clients handle 429/`Retry-After` with bounded exponential backoff and jitter.
- [ ] Device Authorization Grant's `slow_down` is not misused across all grant types.
- [ ] Authorization Codes remain single-use with PKCE and redirect validation intact.
- [ ] Refresh token rotation and replay detection are never relaxed under load.
- [ ] Client Credentials clients cache tokens rather than fetching one on every API call.
- [ ] Custom filters run only in the right chain without double registration.
- [ ] Client secrets, JWT assertions, authorization codes, refresh/access tokens, and raw HTTP bodies are never logged.
- [ ] Metrics, traces, and audits enforce proper access control, bounded cardinality, and retention.
- [ ] Load tests cover valid traffic, attackers, multi-client NATs, and multi-instance setups.
- [ ] Runbooks exist for limiter/DB/KMS failures and credential compromises.

### Core Takeaways

**The Token Endpoint must be guarded as a critical authentication and credential-issuing surface.** Rate limiting is the first line of defense, paired with:

- **Pre-auth admission control** to shed anomalous traffic before expensive credential checks.
- **Post-auth quotas per verified client** to ensure fairness and contain misbehaving valid clients.
- **Concurrency limits + timeouts/deadlines** to protect DBs, signers/HSMs, caches, and servlet threads from exhaustion.
- **429 responses and bounded retry policies** to stop clients from amplifying load.
- **Uncompromised OAuth/OIDC validation**, especially client authentication, grants, PKCE, code replay, and refresh token state.
- **Credential-free observability**, backed by load/multi-instance testing and incident runbooks.

Spring Authorization Server handles Token Endpoint protocol semantics; Spring Security and gateway infrastructure provide the enforcement points for protective policies. **Never replace protocol filters or skip authentication just to implement rate limiting.** A production-ready solution preserves both OAuth correctness and availability under abuse.

## References

- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Multiple SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html#_multiple_httpsecurity_instances)
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework, Token Endpoint](https://www.rfc-editor.org/rfc/rfc6749#section-3.2)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 6585 — Additional HTTP Status Codes, 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585#section-4)
- [RFC 9110 — HTTP Semantics (Retry-After)](https://www.rfc-editor.org/rfc/rfc9110)
- [OWASP API Security Top 10 (2023)](https://owasp.org/API-Security/editions/2023/en/0x11-t10/)
