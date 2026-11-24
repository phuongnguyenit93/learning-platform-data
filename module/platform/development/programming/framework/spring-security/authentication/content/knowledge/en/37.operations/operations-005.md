# Timeouts, Connection Limits, and Behavior When External Identity Sources Fail

> **Context:** A Spring Security application must verify users or tokens through a system outside the application process: LDAP/Active Directory over LDAPS, an OAuth2/OIDC identity provider (IdP), an opaque token introspection service, a profile/permissions API, or a remote user store. When that system is slow, overloaded, or unreachable, the application must still **protect authentication secrets, deny unverified privileges, respond within bounded time, and avoid crashing itself while waiting on connections**. This lesson focuses on timeouts, connection limits, infrastructure failures, and operations; examples use Spring Boot 3.x / Spring Security 6.x and Java 17+ as the baseline.

## 1. Learning Objectives

After this lesson, you should be able to distinguish and implement:

1. Classify **wrong password/token**, **locked/disabled account**, **connection error**, **timeout**, **TLS/PKI failure**, **IdP HTTP 429/5xx**, **misconfiguration**, and **data store errors**.
2. Choose timeouts for DNS/connect/TLS/read/pool-acquire, overall requests, and caller deadlines; avoid mistaking a single timeout for a guarantee that the entire operation finishes on time.
3. Bound the number of connections and **concurrent authentication operations** (bulkhead), queue/pool waits, retry budgets, and circuit breakers to prevent unbounded queues.
4. Know when **not to fail open** and how to distinguish 401/403 from 429/503 at the HTTP layer without disclosing account details.
5. Configure LDAP/JNDI timeouts and key considerations for Spring Security LDAP, OIDC discovery/JWKS, and opaque token introspection.
6. Design behavior when upstream is unavailable: fresh logins, requests with existing sessions, locally verified JWTs, and operations requiring real-time permission lookups.
7. Test latency, pool exhaustion, retry storms, DNS/TLS errors, stale caches, failover, recovery, and audits; create dashboards and runbooks.
8. Understand the boundary between **verified identity proof** and **previously cached values**, never using stale data to silently bypass authentication.

**Root principle:** When an identity source does not respond, the result is **"unable to verify"**, not "wrong password" and certainly not "valid user". Proper classification keeps security, user support, alerting, and SLAs accurate.

## 2. Map of External Identity Sources and Dependency Points

| Source | Communication | What Is Verified | Risks on Failure |
| --- | --- | --- | --- |
| LDAP/Active Directory | LDAP/LDAPS, search, bind | User DN, password, or attributes/groups | Slow binds, DC unreachable, referrals, TLS, stale pools |
| OIDC Login / OAuth2 Client | Discovery, authorization endpoint, token endpoint, UserInfo if used | Protocol state, code/token/claims per configuration | Login redirect failures, token exchange timeouts, lost SSO |
| OAuth2 opaque token | HTTP introspection | Active token, scopes, issuer/subject per trust contract | API requests depend on the IdP in real time |
| JWT Resource Server | Signature verification via public keys/JWKS | Signature, `iss`, `aud`, `exp`, scopes | Discovery/JWK refresh failure, unknown `kid`, expired cache |
| DB or REST UserDetailsService | JDBC/HTTP/RPC | Account state, password hash, authorities | Pool exhaustion, dead connections, replica lag |
| External MFA service | HTTP/gRPC or push challenge | Independent factor, nonce/challenge | Must never treat MFA as succeeded when upstream times out |
| Policy/authorization service | REST/gRPC, LDAP groups, entitlement DB | Whether a specific action may execute | Permissions may remain unverified at request time |

Each source requires its own **criticality decision**. For example, a resource server endpoint with a valid JWT signature and cached verification key may not need to call the IdP on **every** request, whereas if every request requires live introspection or real-time policy checks, an upstream outage directly impacts the current decision.

Never apply a single blanket rule like "if IdP is down, all requests succeed/fail". Analyze each **trust boundary**: which credential is verified where, what TTL the proof carries, whether immediate revocation is required, and what data may be used temporarily under approved policy.

## 3. Realistic Timeline of a Single Login

~~~text
Caller / Browser
    |
    |-- HTTP request received at gateway
    |     |- queue/wait before app (if any)
    |     |- WAF/rate limit and connection budget
    |
    v
Spring Security AuthenticationManager
    |
    |-- acquire bulkhead permit / connection from pool
    |-- DNS lookup
    |-- TCP connect
    |-- TLS handshake + trust/hostname verification
    |-- LDAP bind / HTTP token exchange / introspection request
    |-- wait response bytes / LDAP response
    |-- parse + verify identity/claims + group lookup
    |
    v
Authentication outcome
    |
    +-- VERIFIED       -> trusted principal/authorities
    +-- INVALID        -> reject credential
    +-- UNAVAILABLE    -> infrastructure error, unverified
    +-- OVERLOADED     -> resource limit, unverified
~~~

**Connect timeout** bounds only the connection-establishment phase; **read/response timeout** bounds waiting for bytes or responses; **pool acquire timeout** bounds waiting for a slot; **overall deadline** bounds the whole journey at a higher level. A library may spend extra time on DNS, TLS, redirects, multiple LDAP URLs, retries, or parsing outside a single timeout.

Distinguish:

- **Server-side inbound deadline:** maximum time the app lets a login request live before rejecting it.
- **Upstream operation deadline:** total limit for one external verification call.
- **Per-attempt timeout:** limit for each individual upstream call attempt.
- **Caller timeout:** the client/gateway may give up before the backend stops processing.
- **Idle/read timeout:** not necessarily a hard wall-clock deadline if the response trickles continuously.
- **Pool wait:** if no connection/permit can be acquired, fail fast instead of waiting indefinitely.
- **Queueing:** queues can exhaust the overall timeout even when sockets are fast.

A request canceled by the caller can keep running on the backend without cancellation/timeout propagation; test this and enforce independent resource budgets.

## 4. Distinguishing Credential Errors from Infrastructure Errors

| Event With Evidence From Source | Internal Category | Authentication | Suggested HTTP by Endpoint Type |
| --- | --- | --- | --- |
| LDAP bind returns invalid credentials; IdP explicitly rejects token | `INVALID_CREDENTIALS` | Reject | Form login: generic failure redirect; API: 401 |
| Unknown username from successfully queried repository | `UNKNOWN_SUBJECT` | Reject | Generic public response to prevent enumeration |
| Account confirmed disabled/locked | `ACCOUNT_NOT_ALLOWED` | Reject | Generic public response; do not issue session |
| Network connect refused, DNS failure, upstream reset | `UPSTREAM_UNAVAILABLE` | **Unable to verify** | 503/5xx per policy, never 200 |
| Socket/read/operation deadline | `UPSTREAM_TIMEOUT` | **Unable to verify** | 503, or 504 at gateway per architecture |
| Failed to acquire permit/pool connection | `AUTH_CAPACITY_EXHAUSTED` | **Unable to verify** | 503 or 429 depending on limit source |
| IdP returns 429, `Retry-After` | `UPSTREAM_RATE_LIMITED` | **Unable to verify** | 503/429 per contract, respect retry budget |
| IdP returns 500/502/503, malformed JSON, missing fields | `UPSTREAM_PROTOCOL_FAILURE` | **Unable to verify** | 503/5xx; alert |
| Expired TLS certificate, hostname mismatch, untrusted CA | `TRUST_FAILURE` | **Unable to verify** | 5xx + urgent alert; never disable TLS |
| Caller sends JWT with invalid signature/issuer/audience/expiry | `INVALID_TOKEN` | Reject | 401; unrelated to IdP downtime |
| JWT uses unseen `kid` and JWKS fetch fails | `KEY_MATERIAL_UNAVAILABLE` | **Unable to verify** | Never accept an unverified token |
| Required authority missing from verified claims/authorities | `INSUFFICIENT_AUTHORITY` | Authenticated, deny operation | 403 |

**Absence of proof ≠ proof of invalidity.** A `SocketTimeoutException` does not prove the password is wrong; an LDAP timeout does not prove the user does not exist. Nor should every `NamingException` be turned into `BadCredentialsException`. Classify at the connection adapter, log a safe reason category, and return an outcome that leaks no usernames/secrets.

**HTTP status depends on protocol:** Browser form login typically redirects on bad credentials; REST authentication endpoints typically return 401; API gateways may return 502/503/504 during upstream outages. The table gives guidance, not a claim that Spring maps every case identically by default. Configure error boundaries and test the real application.

## 5. Setting Timeouts as a "Budget", Not Scattering Arbitrary Numbers

**Illustrative** policy example, not a default best practice:

| Component | Illustrative Budget |
| --- | ---: |
| Gateway total request | 3,000 ms |
| App overall authentication deadline | 2,400 ms |
| Bulkhead/pool slot wait | Max 100 ms |
| Upstream connection | Max 400 ms |
| Waiting for upstream response | Max 1,200 ms |
| Parsing, account mapping, and session commit | Around 200 ms |
| Reserve for scheduling/TLS/DNS | Remaining budget |

Components do not always add sequentially: some phases overlap, and some libraries apply timeouts per address/attempt. Therefore, design an **overall deadline** and propagate remaining time down to each operation. If the gateway waits 3 seconds while the client waits 2 seconds, the backend wastes resources after the user has given up.

### Overall Decision Formula

~~~text
remaining = overallDeadline - now()

if remaining <= 0:
    return UPSTREAM_TIMEOUT

acquirePermit(wait <= min(poolWaitCap, remaining))
connectTimeout = min(connectCap, remainingAfterAcquire)
readTimeout    = min(readCap, remainingAfterConnect)
parseAndCommit only if enough remaining and verification succeeded
~~~

This is **orchestration pseudocode**; Java's `HttpClient.connectTimeout(...)` and `HttpRequest.timeout(...)` have their own semantics and do not replace an end-to-end deadline across Spring filters, LDAP referrals, and DB transactions. For blocking APIs without proper cancellation, add bulkheads and bounded worker pools rather than trusting `Future.cancel(true)` to always interrupt stuck I/O.

### Picking Thresholds from Data

- Measure p50/p95/p99 latency on real network paths, including errors and connection setup, per region/IdP.
- Keep timeouts long enough to avoid false outages during peak traffic, yet short enough not to pile up thousands of requests.
- Order gateway/client/app/upstream deadlines **hierarchically**; avoid nearly identical timeouts that make diagnosis ambiguous.
- Account for startup, cold pools, DNS misses, TLS handshakes, multiple LDAP URLs, failover, and cold JWKS fetches.
- Avoid a blanket "30 seconds" on every step: a 30-second pool wait × concurrent requests can exhaust all threads.
- Test when upstream responds slowly without timing out to catch queueing and p99 spikes before full outages.

## 6. Connection Limits Do Not Equal Concurrent Authentication Limits

A pool with `maxTotal=20` **does not guarantee** only 20 login requests are running. Requests may be waiting on the pool, parsing payloads, running the password encoder, waiting on DNS, waiting on retries, or calling another upstream. Distinguish:

1. **Connection pool max:** open connections to LDAP/HTTP/DB/IdP.
2. **Max concurrent authentication operations:** attempts holding a bulkhead permit.
3. **Pool-acquire timeout:** how long a request may wait for a slot.
4. **Pending queue capacity:** how many operations may queue; queues must be bounded.
5. **Per-identity/source rate limit:** whether overly fast sources are throttled before hashing passwords or calling the IdP.
6. **Remote provider quota:** IdP rate limits/costs per bind or introspection call.
7. **Worker thread capacity:** servlet/virtual-thread executors, sockets/event loops, and buffers.
8. **Global budget across instances:** 20 connections × 15 pods = 300 connections at the IdP, potentially exceeding quotas unnoticed by any single pod.

### Little's Law for Intuition

~~~text
in_flight_operations ≈ arrival_rate_per_second × average_duration_seconds
~~~

If the app receives 100 authentication requests/second and each waits 1 second on upstream, roughly 100 operations are in flight on average. When upstream slows to 5 seconds at the same rate, roughly 500 operations accumulate unless bounded. The result is exhausted connections/threads/memory even with bug-free app code.

A **bulkhead** protects the authentication zone: once concurrent operations hit the cap, fail fast with `AUTH_CAPACITY_EXHAUSTED`/503 instead of queueing endlessly. Base thresholds on p99, throughput, IdP capacity, and pod count. Consider fairness: a botnet must not consume every permit and lock out legitimate users; edge rate limiting and prioritizing verified traffic can help, provided you never create a "VIP bypass" from client-supplied headers.

### LDAP Bind Pools Carry Special Risks

Connections can carry authentication/bind state. Never blindly reuse a connection bound as account A to authenticate user B. Pooling policies differ between **service-account search contexts** and **per-user binds**. Check Spring LDAP context source/JNDI pool semantics, bound connection lifetime/idle limits, test for stale connections, never cache plaintext passwords, and verify every authentication executes under the right identity.

## 7. Behavior Policy: Fail Closed Without Triggering Cascading Outages

**Fail closed** means **never granting new access without valid proof**; it does not mean every endpoint in the system must return 503 indefinitely.

| Situation | Security Rule | Availability Option |
| --- | --- | --- |
| New LDAP login when LDAP is down | Never grant Authentication from unapproved stale data | Temporary error page, retry later, alert |
| Completing MFA while external MFA provider is down | Never mark the factor as succeeded automatically | Allow bounded retries or verified recovery flow |
| OIDC authorization-code callback when token endpoint is down | Never treat an unexchanged code as an access token | Keep flow state within TTL, allow restarting login |
| Opaque token introspection down | Never guess token `active=true` | Cache valid results only if revocation/TTL policy allows; else reject |
| JWT with locally verified key, issuer/audience/expiry | May accept under active validator | No need to call IdP per request when designed for local verify |
| JWT with unknown `kid` and JWKS unavailable | Signature cannot be verified -> do not accept | 5xx/503 per decoder/error policy, alert on key fetch |
| User already holds a valid local session | Policy-dependent: keep session up to TTL if per-request external checks aren't required | Never silently extend TTL/permissions; revoke/step-up if policy requires |
| Operation requiring real-time check from external policy engine | Deny operation if permissions cannot be verified | Approved restricted read-only mode, or 503 |
| Public health/status endpoint | May report degraded status without secrets | Keep monitoring/incident routes under RBAC |

**One login is not the whole session:** If a user holds a valid locally stored session, LDAP going down afterward does not necessarily mean all sessions must be invalidated immediately; that depends on **account-disable/revocation freshness** policy. If the contract mandates checking LDAP active status on every request, an outage makes the decision incomplete and requires strict handling. Never use "the user got the password right before" to open a **new session** from an old verification cache not designed for that purpose.

### JWT/JWKS vs. Opaque Token Introspection

- With properly signed JWTs, `JwtDecoder` can verify signature, expiry, and issuer/audience **locally** if a trusted key is cached. An IdP outage does not always stop APIs from accepting JWTs.
- When a new key appears or the cache expires, the resource server may need to fetch JWKS. Never disable signature verification, accept arbitrary `kid`/algorithms, or cache public keys indefinitely without a rotation strategy.
- With opaque token introspection, the `active` decision typically requires a response from the authorization server. Caching introspection slows revocation; TTL/circuit behavior must be agreed upon.
- With OIDC Login, authorization code exchange, `state`/nonce, and ID token validation must complete; an IdP outage never permits turning an unverified code into a logged-in user.

## 8. LDAP/LDAPS: JNDI Timeouts Operators Need to Know

The JDK default JNDI LDAP provider recognizes these environment properties:

| Property | Unit | Meaning |
| --- | --- | --- |
| `com.sun.jndi.ldap.connect.timeout` | milliseconds, as String | Limit waiting to establish an LDAP/TCP connection |
| `com.sun.jndi.ldap.read.timeout` | milliseconds, as String | Limit waiting for an LDAP operation response |
| `Context.PROVIDER_URL` | URL(s) | LDAP/LDAPS source; may list multiple URLs |
| `Context.SECURITY_AUTHENTICATION` | `simple` or other mechanism | Bind mechanism |
| `Context.SECURITY_PRINCIPAL` | Distinguished Name/identity | Bind identity |
| `Context.SECURITY_CREDENTIALS` | Secret | Never log/copy into audits |
| `java.naming.referral` | Referral policy | May trigger extra network round trips |

Timeouts must be **greater than 0**; 0 or negative values can mean default or infinite waits depending on the property. Leaving `read.timeout` unset lets LDAP operations hang for a very long time. Oracle notes that with multiple LDAP URLs, the connect timeout may apply **per URL**, so total failover time can exceed one connect timeout.

### Java Snippet Configuring JNDI/LDAPS (Not Standalone)

~~~java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;

// Code snippet inside a method with securely supplied credentials.
// TLS certificate + hostname verification must be properly configured.
Hashtable<String, Object> env = new Hashtable<>();
env.put(Context.INITIAL_CONTEXT_FACTORY, "com.sun.jndi.ldap.LdapCtxFactory");
env.put(Context.PROVIDER_URL, "ldaps://directory.example.test:636");
env.put("com.sun.jndi.ldap.connect.timeout", "800");
env.put("com.sun.jndi.ldap.read.timeout", "1500");
env.put(Context.SECURITY_AUTHENTICATION, "simple");
env.put(Context.SECURITY_PRINCIPAL, userDnFromTrustedLookup);
env.put(Context.SECURITY_CREDENTIALS, passwordFromLogin);

DirContext ctx = null;
try {
    ctx = new InitialDirContext(env);
    // A successful bind only proves the directory accepted the credentials.
    // The application must still verify account status and permissions per policy.
} finally {
    if (ctx != null) {
        ctx.close();
    }
}
~~~

This snippet **is not a standalone compilable file** because `userDnFromTrustedLookup` and `passwordFromLogin` must come from a controlled flow. Never concatenate unvalidated usernames into a DN or LDAP filter due to LDAP injection risk; use proper search filter escaping/parameterization. Never print credentials in exceptions, dump the Hashtable, or log `env`.

### LDAPS/StartTLS and Error Classification

- Use LDAPS or StartTLS per policy, **verifying certificate chains and hostnames**; never install a trust-all socket factory to bypass certificate errors.
- Connection timeouts, read timeouts, SSL handshake failures, expired certificates, and broken LDAP referrals are **connection/trust incidents**, not invalid passwords.
- Classify as wrong credentials in the adapter only when the directory returns **explicit invalid credentials** from bind. A `NameNotFound` during DN search is not a network timeout; it may indicate an unknown account or wrong base DN.
- When using a service account to search and then binding as the user, separate service bind errors (broken config secret) from user wrong-password binds; never lock out users because the service account expired.
- Test domain controller failover, DNS, referrals, stale pooled connections, and TLS rotation, since connect/read timeouts do not cover every dependency.

## 9. Spring Security LDAP: Role of the Authentication Layer and Context

Spring Security LDAP provides `BindAuthenticator`/LDAP authentication providers to check credentials via bind, and `LdapContextSource` (from Spring LDAP) to manage connection details. A configuration or adapter must bind together:

- Endpoint `ldaps://...`, base DN, service credentials (if used), and pool strategy.
- JNDI connect/read timeouts in the context source environment, or connection settings of the chosen LDAP provider.
- Referral/search/attribute lookup handling and filter escaping.
- Creating a successful `Authentication` **only after** LDAP verification and account/group policies pass.
- Error classification: unknown user/invalid password, LDAP unavailable, timeout, TLS trust failure, service-account failure.
- Limits: bulkhead/queue/connection pool wrapping **the entire LDAP bind/search path**, not just one method.

**Do not assume `BindAuthenticator` automatically provides a circuit breaker, per-account retry budget, or HA directory routing.** Those require separate architecture or resilience libraries. When pooling `LdapContextSource`, check connection reuse and identity binding semantics; a service-account search connection has a different lifecycle from a per-user bind. Different Spring Security/LDAP/Boot releases may have different DSLs and property names; verify Javadocs and actual dependency versions before pasting configuration.

### Search + Bind Architecture Choice

~~~text
Login: username/password
    |
    +-- Normalize/validate username (no LDAP filter injection)
    +-- Search user DN via service-account connection
    |       |-- timeout/infra error -> AUTH_SOURCE_UNAVAILABLE
    |       +-- not found -> generic auth failure
    |
    +-- LDAP user bind with password
            |-- invalid credentials -> BAD_CREDENTIALS
            |-- timeout/TLS/referral -> AUTH_SOURCE_UNAVAILABLE
            +-- success -> verified user DN/identity
    |
    +-- Group/role lookup
            |-- if required for permission, error -> authorization incomplete
            +-- success -> Authentication with proven authorities
~~~

If group lookup fails after a successful password bind, do not automatically grant `ROLE_ADMIN` from an unbounded cache. You may distinguish "password verified, authorization unavailable", granting roles only if the entitlement source policy permits it and freshness is met. Some apps maintain a role cache with TTL, invalidation, and revocation SLAs; that is a **separate security decision**, not a default fallback.

## 10. OIDC/OAuth2: Discovery, Token Exchange, JWKS, and Introspection

### OIDC Login / OAuth2 Client

OIDC login may require calls to:

1. Provider discovery/metadata (depending on configuration and timing).
2. Authorization endpoint via browser.
3. Token endpoint to exchange the authorization code.
4. JWKS to verify ID token/access token.
5. UserInfo endpoint if the application needs data from it.
6. Logout/revocation endpoints per contract.

Each step has its own timeouts, retry/callback validity, and error mappings. A 5xx at the token endpoint **does not prove the authorization code is wrong or the user's password is wrong**. Conversely, an `invalid_grant` properly returned by the IdP is not automatically a network outage.

**Be careful retrying token exchanges:** Authorization codes are typically single-use. If a token exchange times out after the IdP already processed it, resending the code may hit `invalid_grant`; handle indeterminate outcomes, protocol state, and provider retry policies properly. Never retry blindly in a loop inside a login filter. In OIDC browser flows, callback `state`/nonce must still be validated and expire per policy.

### JWT Resource Server

Illustrative Boot resource server configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/issuer/jwks
~~~

These are **illustrative** URIs; replace them with your provider's real issuer and JWKS endpoint. Declaring `jwk-set-uri` directly alongside `issuer-uri` allows the resource server to start without pinging the discovery endpoint, while still validating the `iss` claim per configuration. That reduces **startup** coupling, not the need to fetch/refresh JWKs when verifying a token signed with an unseen key.

**Do not confuse key caching with skipping verification.** Tokens with invalid signatures, issuers, audiences, or expiry must still be rejected. If JWKS fails to load and no matching key exists, never accept a token with a new `kid` just because the IdP is down. Set cache TTL/refresh to match key rotation and revocation expectations; never trust unverified claims.

### Opaque Token Introspection

If an API relies on an introspection endpoint, every request or cache miss may make an HTTP call to determine `active`. When the IdP is down:

- Never turn an unknown result into `active=true`.
- Never reassign scopes from client-supplied request headers.
- If caching `active=true` results, define TTL, scopes, revocation SLA, clock/expiry handling, and cache keys via secure token digests.
- If privacy/security requires near-real-time revocation, overly long positive caching violates policy.
- Distinguish an introspection 401 caused by **wrong resource-server client credentials** from a genuinely inactive token; that is a config/upstream error, not all users suddenly presenting bad tokens.

## 11. Java 17 HTTP Client: Connect Timeout and Request Timeout Differ

The following Java snippet shows how to set **connect timeout** on `HttpClient` and **request timeout** on `HttpRequest`. It uses an illustrative `https://...example.test` endpoint, is not a complete real-world caller, and **sends no tokens/secrets**.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.time.Duration;

HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(500))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://idp.example.test/health"))
        .timeout(Duration.ofSeconds(2))
        .GET()
        .build();

// Actual request sending/response parsing and auth contract must be
// implemented by the adapter: never treat HTTP 200 automatically as identity verified.
~~~

**When sending real introspection/token requests**, implement IdP-compliant client authentication, TLS, redirect policy, encoding, and secret management; never put access tokens/refresh tokens in URL queries, logs, or metrics. `HttpConnectTimeoutException`/`HttpTimeoutException` belong to infrastructure errors, not bad credentials. `InterruptedException` must restore the interrupt flag when using blocking `send(...)` and return an error properly. Never log request bodies/headers containing tokens while debugging.

**Do not assume "request timeout = end-to-end login timeout".** The HTTP call sits inside filters, token parsing, LDAP group mapping, DB session persistence, and possibly multiple redirects/retries. Overall deadlines must be managed at the workflow level.

## 12. Retries, Backoff, and Retry Storms

**By default, never unconditionally retry an authentication operation.** Repeated password binds can increment failed-attempt counters, lock accounts, or overload LDAP. A token exchange may be non-idempotent. An MFA challenge may be consumed upstream even when the app timed out.

| Operation | Might Retry Fit? | Risks / Required Controls |
| --- | --- | --- |
| Fetch OIDC metadata via GET | Possibly, tightly bounded within deadline | Use cache/ETag; avoid query storms |
| Fetch JWKS via GET | Possibly with backoff/cache/single-flight | Unknown `kid` must not be accepted on failure |
| Read-only LDAP search | Depends on provider and state; tightly bounded | Pool saturation, referrals, duplicate work |
| LDAP user password bind | Avoid blind retries | Account lockout, password-spray amplification |
| OAuth2 authorization-code exchange | Usually avoid blind retries | Single-use codes, ambiguous timeout outcomes |
| Opaque token introspection | If provider contract permits, short budget | Per-request load, cached revocation lag |
| MFA verification/challenge consume | Never retry without idempotency | Replay protection and attempt counters |
| Password change / token revoke | Retry only with idempotency key and policy | May already have committed upstream |
| TLS certificate/hostname failure | No | Never fix via retries or disabling TLS verification |
| Explicit invalid credentials/invalid token | No | Will not become valid a few milliseconds later |

### Retry Budget

A reasonable policy might allow **0 or 1 retry** for read-only/idempotent operations with exponential backoff + small jitter, and only while the overall deadline and circuit breaker permit. Never default to 3 retries across 10 pods and 5 endpoints, because a slow upstream will suffer multiplied load.

~~~text
maxAttempts = 1 or 2 (depending on operation)
for each attempt:
    if deadline exhausted or circuit open: stop
    if permission/credential invalid: stop
    if TLS trust error: stop
    if transient upstream error and operation safe to retry:
         wait bounded jitter outside request thread when possible
         retry within remaining deadline
    else: stop
~~~

**`Retry-After`** returned by an IdP must be interpreted within the overall deadline and must not synchronize fleet-wide retries at the exact same instant. If a `429` arrives with `Retry-After` longer than the remaining client budget, do not hold the request open waiting; return a temporary error with appropriate public messaging.

### Circuit Breakers and Bulkheads Differ

- **Circuit breaker** tracks upstream errors and fails fast once error rates cross a threshold. It relieves a broken IdP and transitions through closed/open/half-open states.
- **Bulkhead** caps concurrent operations so servlet threads/connections are not exhausted and login cannot starve unrelated endpoints.
- **Rate limiter** caps incoming source/account rates, blocking bots before they trigger costly operations.
- **Timeout** bounds how long a single attempt can drag on.
- **Retry** can amplify load; use only within budget and on safe operations.

Each mechanism needs metrics, reset/hysteresis rules, and **half-open probe testing**. Do not wrap only the network call in a breaker while leaving pool acquisition, DNS, group lookups, or serialization able to hang unguarded.

## 13. Standalone Java 17: Upstream Classification and Concurrency Limiting

This program is an **operational policy simulation**—it does not call a real LDAP/IdP, verify passwords, or issue Spring `Authentication`. It illustrates the difference among **invalid credentials**, **upstream unavailable**, **timeout**, and **bulkhead exhausted**, while proving permits are released via `finally`.

File `ExternalIdentityPolicyDemo.java`:

~~~java
import java.util.concurrent.Semaphore;

public final class ExternalIdentityPolicyDemo {

    enum UpstreamResult {
        VERIFIED, INVALID_CREDENTIALS, TIMEOUT, TLS_FAILURE
    }

    enum Decision {
        AUTHENTICATED, UNAUTHORIZED,
        TEMPORARILY_UNAVAILABLE, OVERLOADED
    }

    static Decision classify(UpstreamResult upstream) {
        return switch (upstream) {
            case VERIFIED -> Decision.AUTHENTICATED;
            case INVALID_CREDENTIALS -> Decision.UNAUTHORIZED;
            case TIMEOUT, TLS_FAILURE ->
                    Decision.TEMPORARILY_UNAVAILABLE;
        };
    }

    static final class AuthBulkhead {
        private final Semaphore permits = new Semaphore(2, true);

        Decision verify(UpstreamResult upstream) {
            if (!permits.tryAcquire()) {
                return Decision.OVERLOADED;
            }
            try {
                // Simulate that the adapter received an outcome from the provider.
                return classify(upstream);
            } finally {
                permits.release();
            }
        }

        boolean holdForTest() {
            return permits.tryAcquire();
        }

        void releaseForTest() {
            permits.release();
        }
    }

    public static void main(String[] args) {
        AuthBulkhead bulkhead = new AuthBulkhead();

        System.out.println("verified: " +
                bulkhead.verify(UpstreamResult.VERIFIED));
        System.out.println("bad credentials: " +
                bulkhead.verify(UpstreamResult.INVALID_CREDENTIALS));
        System.out.println("timeout: " +
                bulkhead.verify(UpstreamResult.TIMEOUT));
        System.out.println("tls failure: " +
                bulkhead.verify(UpstreamResult.TLS_FAILURE));

        boolean first = bulkhead.holdForTest();
        boolean second = bulkhead.holdForTest();
        System.out.println("slots held: " + first + "/" + second);
        System.out.println("pool exhausted: " +
                bulkhead.verify(UpstreamResult.VERIFIED));

        bulkhead.releaseForTest();
        System.out.println("after one release: " +
                bulkhead.verify(UpstreamResult.VERIFIED));
        bulkhead.releaseForTest();
    }
}
~~~

Compile and run with **JDK 17+**, no Spring required:

~~~bash
javac ExternalIdentityPolicyDemo.java
java ExternalIdentityPolicyDemo
~~~

**Exact** stdout:

~~~text
verified: AUTHENTICATED
bad credentials: UNAUTHORIZED
timeout: TEMPORARILY_UNAVAILABLE
tls failure: TEMPORARILY_UNAVAILABLE
slots held: true/true
pool exhausted: OVERLOADED
after one release: AUTHENTICATED
~~~

**Lesson:** Timeout/TLS failures never turn into `UNAUTHORIZED`. While two permits are held, the third request is rejected immediately instead of queueing forever; once one permit is released, new operations proceed. `Semaphore` limits only **one JVM**, and does not replace cluster-wide IdP quotas.

**Intentionally omitted from the demo:** real timeouts (`TIMEOUT` outcome is synthetic data), HTTP connection pooling, circuit breakers, retries, cancellation, user lookups, cryptography, or session issuance. In production, wrap real network calls, use `try/finally`, enforce shared quotas where needed, add breaker metrics, admission policies, and track rejected requests. Never call `classify(VERIFIED)` from a client-supplied request parameter: `VERIFIED` must come only from a **trusted adapter** after complete credential verification.

## 14. Spring Security: Which Errors Should Be Wrapped at the Adapter?

At the authentication provider layer, Spring Security commonly uses `AuthenticationException` and specific subclasses:

| Exception/Category | Suggested Semantics |
| --- | --- |
| `BadCredentialsException` | The source **responded confirming invalid credentials** |
| `UsernameNotFoundException` | Repository user lookup completed and found no user |
| `LockedException` / `DisabledException` | Data source/account policy confirms the account may not log in |
| `AuthenticationServiceException` | Error inside the authentication service unrelated to credentials |
| `InternalAuthenticationServiceException` | Internal/service error inside the authentication provider |
| Custom `AuthenticationException` with category | Used when separating `UPSTREAM_TIMEOUT`, `TLS_FAILURE`, and `POOL_EXHAUSTED` clearly |

Specific classes vary by provider, especially LDAP/REST/IdP. **Never catch every exception and throw `BadCredentialsException`**, never create an "anonymous yet authenticated" principal, and never put credentials/tokens into exception messages or causes exposed in public logs.

An illustrative adapter contract:

~~~java
public interface ExternalIdentityVerifier {

    // Result is VERIFIED only when the trusted source has completed verification.
    VerifiedPrincipal verify(UserCredentials credential)
            throws IdentitySourceUnavailableException;

    // The types below are application-defined contracts.
    record UserCredentials(String username, char[] password) {}
    record VerifiedPrincipal(String stableUserId) {}
}

public class IdentitySourceUnavailableException extends RuntimeException {
    public IdentitySourceUnavailableException(String reason) {
        super(reason);
    }
}
~~~

These classes are **interface fragments**, not a standalone Java file; in real projects avoid putting multiple public top-level types in one file and never include raw passwords/DNs/secret-bearing URLs in error reasons. A real adapter must decode/normalize LDAP/OIDC responses and separate invalid credentials from unavailable sources. The provider builds `Authentication` after `VERIFIED`, or throws the appropriate internal exception, never relying on a client-supplied boolean.

### AuthenticationManager May Hide Outages in Form Login Flows

A default `AuthenticationFailureHandler` may route many `AuthenticationException`s to the same `/login?error`. That prevents account enumeration, yet **does not mean** telemetry may lump `BadCredentials` together with `LDAP_TIMEOUT`. The system needs:

- Generic public responses for bad credentials/unknown accounts/locked accounts per threat model.
- 5xx/503 error handling or a "service temporarily unavailable" page for outages, per HTTP contract.
- Separate audit categories: `BAD_CREDENTIALS`, `ACCOUNT_DISABLED`, `UPSTREAM_TIMEOUT`, `TLS_FAILURE`, `POOL_EXHAUSTED`.
- Never increment bad-password lockout counters for requests whose **credentials were not checked** because the IdP was down.
- Never drop users onto a weaker fallback (e.g., a local default password) just because LDAP stopped answering.
- Full session/MFA rules must still hold before granting access to protected routes.

When building a custom `AuthenticationProvider`, test catch/translation points: an unmapped runtime error may become a 500 or be swept into a generic failure redirect. There is no universal default status across versions; write integration tests against the **real `SecurityFilterChain`**.

## 15. Directory Errors and Account States: When Can You Say "Wrong Password"?

For user lookup and bind:

~~~text
1) user lookup/search:
   - found -> determine DN/canonical ID from source
   - not found -> unknown account (generic public response)
   - timeout/network error -> unknown whether user exists

2) user bind:
   - explicit LDAP invalidCredentials -> wrong password per bind
   - bind successful -> password factor verified
   - timeout/TLS/referral/service unavailable -> unknown whether password is correct

3) authorities/group lookup:
   - succeeded -> permissions verified
   - unavailable -> do not grant elevated roles automatically; follow policy
~~~

Use provider-specific exception mapping tested against test containers/fake LDAP rather than guessing from exception message substrings. An expired LDAP service account can fail **for every user**; if logic treats that as wrong password, thousands of accounts will lock out, creating a secondary DoS incident.

### Public Messages Must Not Reveal Internals

- Invalid credentials: "Unable to sign in. Please check your credentials and try again."
- Identity source unavailable: "Sign-in service is temporarily unavailable. Please try again later."
- Never say "user A exists in AD, but the password is wrong"; never return DNs, hostnames, stack traces, client secrets, or raw JWTs in responses.
- For APIs, HTTP 503 may include `Retry-After` if there is a solid basis to estimate; do not promise recovery times you do not know.
- Infrastructure failures should trigger alerts; never send an email for **every** failed login, which causes notification storms.

**Side-channel checks:** If unknown user, bad password, and disabled account produce noticeably different response bodies, statuses, or timings, attackers can enumerate accounts. You can return a unified response across account-state cases while distinguishing infrastructure outages per incident policy; framework/patch behavior and timing tests still need review.

## 16. Caches and Fallbacks: What May Be Kept When the IdP Fails?

There is no blanket "caching is good" or "caching is bad" answer. Evaluate by **evidence type**:

| Data | Under What Conditions Can It Be Cached? | Risk |
| --- | --- | --- |
| OIDC discovery metadata | Provider TTL/validation, trusted config source | Metadata changes, endpoint/key rotations |
| JWKS public keys | TTL/versioning plus signature/`iss`/`aud`/`exp` verification | Key revoked/rotated; unknown `kid` |
| User profile display name | Bounded TTL and fallback | Stale display info; less sensitive than auth |
| Groups/permissions | Only if revocation SLA and TTL permit | Granting privileges past revocation time |
| Previous successful LDAP bind | **Never use by default for new logins** | Turns stale/cached passwords into auth factors |
| Opaque token introspection positive result | Short TTL and explicit revocation policy | Revoked tokens may still be accepted |
| Previously issued valid local session | Can continue within session TTL/policy | Offboarded accounts may go undetected |
| Rate limit / account lock state | Shared store with TTL, atomic updates | Stale state weakens protection or locks unfairly |

If a product supports **offline authentication**, that is a separately designed and audited security feature with local cryptographic verifiers, device binding, TTLs, revocation, and explicit policy; never enable it implicitly by holding raw usernames/passwords or caching `Authentication` from a prior login. Caching public JWKS keys is fundamentally different from caching raw tokens or passwords.

**Outage recovery:** Many concurrent requests may notice an expired JWKS cache simultaneously and hit the IdP together, causing a thundering herd. Use cache stampede protection/single-flight, bounded refresh, and jitter; never accept a request after timeout unless its signature was verified.

## 17. Health Checks, Readiness, and Circuit Health

Do not wire a live LDAP/IdP call into **every** liveness probe request:

- **Liveness:** Is the process alive and able to make progress? Upstream downtime does not mean the app needs constant restarts.
- **Readiness:** Does the pod have the required dependencies to take traffic for required features? Can use shortly cached dependency status per policy.
- **Functional auth health:** Measure identity source latency and reachability with a dedicated, protected *synthetic* account/service identity at bounded frequency.
- **SLOs:** Measure the percentage of logins completing within deadline and infrastructure auth errors; do not fold user password typos into upstream availability SLOs.

A readiness probe must never repeatedly try wrong-password binds that lock out the synthetic account or overload AD. Use dedicated credentials, minimal scope, a secret manager, and rate control. TLS monitors must catch expiring certificates and hostname chains; DNS and route connectivity need independent checks.

If every pod sees the IdP down and flips readiness to false simultaneously, the entire cluster can drop routes even for endpoints that do not need the IdP. **Design readiness per capability** or keep the service in controlled degraded operation. Liveness checks that restart pods on upstream outages cause restart storms and prolong outages.

### Circuit Breaker Operational States

~~~text
CLOSED: accepts calls normally
   |
   | timeout/network errors exceed threshold in window
   v
OPEN: skips upstream calls, returns UNAVAILABLE quickly
   |
   | bounded wait duration
   v
HALF_OPEN: allows a few controlled probes
   |
   +-- stable success -> CLOSED
   +-- continued failure -> OPEN
~~~

Circuit breakers must count **infrastructure errors** separately from explicit `BAD_CREDENTIALS`. If user wrong passwords count as upstream failures, a password-spraying attack can trip the breaker and lock out all users: a **misclassification-induced DoS**. Testing this condition is mandatory.

## 18. Observability and Logging Without Leaking Identity Data

Metrics should use low-cardinality labels:

| Suggested Metric | Meaning |
| --- | --- |
| `identity_upstream_requests_total{source,result}` | Requests by source: VERIFIED/INVALID/TIMEOUT/UNAVAILABLE |
| `identity_upstream_duration_seconds{source,operation}` | p50/p95/p99 latency for search/bind/token/JWKS |
| `identity_bulkhead_inflight{source}` | Operations currently holding permits |
| `identity_bulkhead_rejected_total{source}` | Requests rejected due to full bulkhead |
| `identity_connection_pool_wait_seconds{source}` | Time spent waiting for a connection |
| `identity_connection_pool_active{source}` | Connections currently in use |
| `identity_connection_pool_pending{source}` | Waiting callers |
| `identity_circuit_state{source}` | Closed/open/half-open |
| `identity_auth_infra_errors_total{category}` | DNS/TLS/timeout/5xx/429/parse |
| `identity_retry_attempts_total{operation}` | Retry rate to spot storms |
| `jwt_jwks_cache_miss_total{issuer}` | Cache refreshes and key rotations |
| `login_completed_total{method,outcome}` | End-to-end login outcome, kept separate from provider events |

These names are **suggested design conventions**, not exact metrics emitted by Spring automatically. The `issuer` label must be a finite allowlisted alias; never put raw URLs, tokens, usernames, session IDs, IPs, or device fingerprints into metric labels.

**Audits** must capture event ID, UTC timestamp, identity source alias, outcome category, request/trace correlation ID, latency bucket, and policy decision. For invalid credentials, avoid logging passwords, OTPs, tokens, raw LDAP DNs, Bearer headers, or `Authorization`/`Cookie`. For LDAP errors, keep sanitized error codes/exception classes, **never** logging the entire JNDI environment Hashtable containing passwords or refresh tokens.

**Useful alerts:**

- Sudden jump in p99 bind/HTTP introspection latency.
- Majority of logins returning `UPSTREAM_TIMEOUT` rather than `BAD_CREDENTIALS`.
- Pool pending/bulkhead rejections exceeding thresholds before all requests time out.
- TLS certificates expiring in 7/3/1 days, or rising JWKS refresh failures/unknown `kid`s.
- One region timing out while another stays healthy (network partition).
- Retry attempts growing faster than inbound traffic (retry amplification).
- Circuit stuck open, half-open failing to recover; synthetic checks failing while liveness passes.
- Fallbacks active outside policy or entitlement caches exceeding TTL.

## 19. Runbook: IdP/LDAP Stops Responding During Peak Traffic

### A. Detection and Isolation

1. Scope the impact: new logins only, MFA challenges, JWT validation, opaque introspection, or all APIs.
2. Check errors by **category**: connect timeout, read timeout, pool exhaustion, 429, DNS, certificate, 5xx.
3. Compare latency before/after onset, pod counts, connections to DC/IdP, provider quotas, and retry rates.
4. Run a few bounded synthetic probes from the affected region; do not spam binds against the directory.
5. Check whether recent certificate/secret rotations or deployments altered truststores, DNS, proxies, pooling, or hostnames.
6. Protect auditing: slow connection logging must not block threads further; never enable debug logging that prints secrets.

### B. Shedding Load While the Incident Continues

1. Maintain **fail-closed** behavior on unverified decisions.
2. Use gateway throttling, in-flight caps, and circuit breakers to relieve the struggling IdP.
3. If multiple trusted, properly managed DC/IdP endpoints exist, fail over per policy; **never** switch to an unverified-TLS server or an inconsistent backup identity source.
4. Disable or reduce **retries on non-idempotent operations** to avoid 10× load amplification.
5. Prioritize serving endpoints that do not depend on the external source, keeping health/incident UX helpful.
6. Users with valid existing sessions may continue per active policy; never issue new sessions from cached old passwords.
7. For JWTs with cached keys and verified claims, keep local verification running if architecture allows; reject unverified tokens with unknown `kid`.
8. Communicate general service status; never expose which accounts exist or specific DC details for exploitation.

### C. Recovery and Postmortem

1. Verify IdP/LDAP health, TLS trust, pool recovery, and zero connection leaks.
2. Let half-open probes run with limits before closing circuits; prevent the entire fleet from retrying simultaneously right as upstream recovers.
3. Verify fresh logins succeed with a test account, wrong passwords still fail, and locked/disabled accounts remain blocked.
4. Verify MFA, session persistence, JWT/JWKS refresh, and opaque token flows individually.
5. Cross-check audits/metrics to estimate logins failed due to infrastructure; do not count them toward failed-password lockouts.
6. Tune thresholds from measured p99, wait times, saturation, and provider quotas instead of raising timeouts infinitely as a "quick fix".
7. Write a postmortem covering timeline, source-specific error categories, queue growth, retry amplification, blast radius, and action items.

## 20. Mandatory Testing Before Production

### Unit and Policy Tests

| Adapter Input | Expected Decision | Audit / Rate Counter Behavior |
| --- | --- | --- |
| Explicit credential reject | UNAUTHORIZED | Record BAD_CREDENTIALS, increment counter once |
| Explicit account locked | DENIED | Do not count as new wrong password |
| Valid credentials, permissions verified | AUTHENTICATED | Grant verified principal/authorities, session per policy |
| DNS failure / connect refused | TEMPORARILY_UNAVAILABLE | Do not increment bad-password counter |
| Read timeout after sending bind/token request | TEMPORARILY_UNAVAILABLE | No blind retries since outcome is ambiguous |
| TLS certificate/hostname failure | TRUST_FAILURE / unavailable | Alert, never disable validation |
| Pool acquire timeout or full bulkhead | OVERLOADED | Never block threads indefinitely or increment user counters |
| IdP HTTP 429 | UPSTREAM_RATE_LIMITED | Respect retry budget, avoid thundering herd |
| IdP HTTP 500/502/503 | UPSTREAM_UNAVAILABLE | Never create an authenticated principal |
| JWKS unknown `kid` and fetch failure | UNVERIFIED | Never accept an unverified new JWT |
| JWT valid signature/claims with cached key | VERIFIED per contract | Skip unnecessary IdP calls |
| Group lookup fails after LDAP bind succeeds | INCOMPLETE_AUTHORIZATION | Never auto-grant missing roles |

### Spring Security + Fake Upstream Integration Tests

- **Fake LDAP** returning invalid credentials: generic form failure, no session issued; accurate audit.
- Fake LDAP slower than `read.timeout`: response finishes within budget; bad-password count unchanged.
- LDAP service search times out before user bind is attempted: never masquerades as unknown account.
- Expired/untrusted LDAPS certificate: never falls back to insecure `ldap://`.
- Pool full: requests rejected/503 boundedly, app does not exhaust servlet threads; permits released across all error paths.
- 10 concurrent requests with max in-flight 2: remaining 8 rejected/boundedly queued per contract without exceeding quota.
- OIDC discovery timeout at startup: with `issuer-uri` only, handle discovery dependency; direct `jwk-set-uri` avoids startup ping without skipping issuer verification.
- Authorization-code token exchange timeout: login does not complete; code is not retried blindly.
- Locally valid JWT when IdP is down: with valid cached trust material and claims, requests continue per policy.
- JWT with unknown `kid` when JWKS is down: fails closed, never authenticated.
- Opaque token introspection down: unknown tokens rejected; cache TTL/revocation honored per policy.
- Rate limiter/circuit breaker test: 100 bad credentials **must not** count as 100 upstream outages or trip the circuit.
- Existing session: when IdP is down and local session policy does not require per-request checks, behavior matches contract; no new sessions minted.
- Backend timeout after verify but before persisting session: never report login completed when session did not commit.
- MockMvc/`formLogin` with real provider and WireMock/mock LDAP or mock HTTP transport: test HTTP boundaries, not just pure methods.
- Service recovery: bounded half-open probes and zero connection pool leaks.
- Fallback endpoint configuration: no anonymous admin, "allow all" filter, or `ROLE_ADMIN` from a broken cache.

### Load/Chaos Testing and Detecting Secondary DoS

1. Simulate 5× p99 spikes alongside rising concurrent logins: measure in-flight, rejected, and queue/heap growth.
2. Simulate losing all LDAP DCs or IdP endpoints, DNS failures, TLS failures, packet loss, and connection resets.
3. Multi-node: pool 20 per pod × 15 pods -> 300 provider budget; verify global quotas and fairness.
4. Shut down audit backend while IdP is down: error handling must not spawn unbounded threads/queues.
5. Rotate client secrets or TLS certificates with active pooled connections; detect stale/revocation issues.
6. Drill IdP sending `429` with `Retry-After` as all pods approach deadlines; verify no retry storms.
7. Random usernames/bot traffic: per-source limits prevent unbounded backend password hashing or LDAP binds.
8. Verify 503 UX vs. invalid-password UX leaks no account/secret details; metrics classify errors accurately.
9. Verify worker-thread pool/executor saturation does not block endpoints unrelated to identity.
10. Measure recovery after upstream returns, ensuring circuit breakers do not all close simultaneously and cause a herd.

## 21. Common Mistakes and Fixes

| Implementation Mistake | Consequence | Fix |
| --- | --- | --- |
| Missing LDAP read timeout | Requests can hang indefinitely | Configure positive connect/read timeouts and overall budget |
| Raising timeout from 3s to 60s when IdP slows | Piles up thousands of requests/threads | Bounded bulkhead, time limits, and latency monitoring |
| Pool max=100 across 20 pods | IdP receives up to 2,000 connections | Calculate global capacity and provider quotas |
| No pool-acquire timeout | Requests wait forever for a slot | Bounded wait/queue, fail fast |
| Retrying every login error 3× | Account lockouts, IdP overload | Conditional retries only for safe/idempotent operations |
| Treating any `NamingException` as bad password | Users locked out when LDAP is down | Separate explicit invalid credentials from infrastructure errors |
| Binding user A then reusing connection for B | Identity/security corruption | Pool per proper bind identity semantics |
| Trust-all TLS or HTTP fallback | Credentials/claims leaked or MITMed | Standard certificate + hostname validation |
| Allowing cached-password login when IdP is down | Fail open, opens takeover paths | Never grant identity without fresh verification |
| Accepting unknown `kid` when JWKS fails to load | Signature bypass | Reject unverified tokens, alert |
| Caching group entitlements indefinitely | Revoked permissions remain active | TTL/invalidations matching revocation SLA |
| Treating HTTP 200 from IdP as authenticated user | Claims/contents unverified | Validate schema, status, issuer, audience, and signature |
| Circuit breaker counting bad credentials as upstream errors | Password spray triggers system-wide outage | Metrics and breakers count infrastructure errors only |
| Health liveness depending on IdP | Pod restart storms | Process-based liveness, capability-based readiness |
| IP-only rate limiting | Botnets rotate IPs to bypass | Account + source + endpoint budgets |
| Logging LDAP env or `Authorization` headers | Leaks service passwords/tokens | Field allowlists, secret redaction |
| Sending warning emails on every timeout | Notification flooding | Debounce/batch, alert via ops channels |
| Randomly revoking active sessions during brief LDAP blips | DoS on already-logged-in users | Clear session policy aligned with trust freshness |
| Watching p50 while ignoring p99/pool pending | Outages detected too late | Track p95/p99, queue waits, rejections, and breakers |
| Untested failures after upstream received the request | Non-idempotent retries corrupt state | Test "response lost after commit" and idempotency |

## 22. Operational Implementation Checklist

**Specification and Security**

- [ ] Classified LDAP/LDAPS, OIDC Login, JWT/JWKS, opaque introspection, UserDetails DB, MFA, and policy services.
- [ ] Every source has its own deadline, retry budget, TLS trust, owner, rate limit, and error taxonomy.
- [ ] Invalid credentials never merged with unavailable; no sessions/roles granted without proven identity and permissions.
- [ ] Never drop TLS, switch to a weaker identity source, or log in from cached old passwords to "keep uptime".
- [ ] Explicitly defined existing sessions vs. new logins, entitlement freshness, and revocation SLAs.

**Resource Limits**

- [ ] Connect/read/request/pool wait/overall deadlines have explicit values and clear hierarchy.
- [ ] LDAP/JNDI environment properties verified per provider, tested with multiple URLs/referrals.
- [ ] Max in-flight, max connections, queue capacity, and per-pod/global quotas are explicit with no unbounded waits.
- [ ] Retries/backoff/jitter restricted to eligible operations; circuit breakers, bulkheads, and rate limits sit in front of auth.
- [ ] Servlet threads never blocked with multi-second `Thread.sleep`; cancellation/`finally` releases enforced.
- [ ] Health probes do not spam LDAP binds or trigger restart storms during IdP outages.

**Operations, QA, and Incident Response**

- [ ] Dashboards track p95/p99, pool pending, in-flight, quota rejections, timeout categories, 429/5xx, and circuit states.
- [ ] No passwords, tokens, LDAP env, session cookies, keys, or raw headers in logs or metrics.
- [ ] Tested invalid credentials vs. read timeouts vs. TLS errors vs. 429 vs. 5xx vs. unknown `kid`.
- [ ] Tested multi-instance behavior, upstream outages, recovery, half-open states, connection leaks, and retry storms.
- [ ] Verified locally validated JWTs follow policy while opaque introspection fails closed.
- [ ] Runbooks exist to diagnose DNS/TLS/IdP/LDAP/pool issues without weakening security during recovery.
- [ ] Rollout, canary, rollback, and threshold re-evaluation processes exist when changing providers/quotas.

**Conclusion:** A slow or unreachable external identity source produces an **unverifiable state**, not proof of a wrong password and never valid identity. Protect Spring Security with **tiered timeouts, connection/in-flight limits, budgeted retries, circuit breakers, error classification, strict TLS, and multi-node testing**. An available system is not one that lets everyone log in at any cost—it is one that denies safely, explains the failure category accurately, prevents cascading outages across other services, and recovers under control when upstream returns.

## Official References

- [Oracle Java — LDAP connect/read timeouts](https://docs.oracle.com/javase/tutorial/jndi/newstuff/readtimeout.html)
- [Oracle Java — JNDI LDAP connection creation and multiple URLs](https://docs.oracle.com/javase/tutorial/jndi/ldap/create.html)
- [Oracle Java SE 17 — java.naming module](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/module-summary.html)
- [Spring Security — LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security 6.5 — OAuth2 Resource Server JWT/JWK startup, cache, and timeouts](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Opaque Token Introspection](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security — AuthenticationServiceException Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationServiceException.html)
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html)
- [Java SE 17 — Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
