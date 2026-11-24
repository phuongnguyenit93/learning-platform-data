# Rate limiting by account, request source, and risk signals

## 1. Context: why IP-only rate limiting is not enough?

An Internet-facing login API does not only face users mistyping passwords. Common attacks include **brute force** (trying many passwords for one account), **password spraying** (trying a few passwords across very many accounts), **credential stuffing** (trying leaked username/password pairs), account enumeration, and abusing email/SMS/OTP delivery.

If you only set a limit like "100 requests/minute/IP":

- Attackers can use thousands of IP addresses/proxies to target a single account, staying below each IP's threshold.
- A single IP can still try 1–2 attempts across thousands of accounts without violating a per-username threshold if the system only tracks by account.
- Real users in offices, schools, or mobile networks sharing a single NAT may get blocked because of someone else's activity.
- Authentication flows via other endpoints such as `/login`, `/api/authenticate`, `/mfa/verify`, or `/password/reset` can become bypass paths if not protected consistently.

The solution is combining **independent counters by account, request source, service scope, and risk signals**, then choosing an appropriate action. The goal is to curb automated credential guessing while protecting legitimate users from false lockouts or denial-of-service attacks.

This lesson belongs to the **Attack Protection** section of the **Spring Security - authentication** module, using Java 17+, Spring Security 6.x/Spring Boot 3.x in Servlet/Spring MVC integration examples. The algorithms and design rules still apply to systems using OIDC, API tokens, and MFA, though integration points vary by flow.

## 2. Distinguishing attack patterns to choose rate-limit keys

| Attack type | Traffic pattern | IP-only limit? | Account-only limit? |
| --- | --- | --- | --- |
| Single-user brute force | Many passwords tried on the same username | Can be bypassed with a botnet | Useful, but easily causes lockout DoS |
| Password spraying | One password tried across many usernames | Detects concentrated sources well; insufficient for distributed IPs | Few attempts per account, so may not hit threshold |
| Credential stuffing | Very many leaked username/password pairs | Partially blocks; proxy rotation defeats it | Partially blocks; few attempts per account |
| Username enumeration | Observing status/timing differences or messages | Does not stop logic leaking account existence | Inconsistent counters/responses can leak users |
| OTP/OTT abuse | Repeated code requests, code guessing, or costly SMS/email triggers | IP limit is insufficient | Per-recipient, per-account, per-device, per-channel are critical |
| Distributed low-and-slow | Few attempts spread over time and many sources | Short-term thresholds struggle to see it | Needs longer windows and risk signals |

**Do not choose a single composite key `IP + username` in place of both separate keys.** If you use a single bucket `login:ip1:alice`, the same IP can try up to the threshold for Alice, then Bob, then Carol... with no overall per-source limit. Or an attacker can rotate IPs continuously for Alice alone. You must **check `account` and `source` separately**, and optionally add an `(account,source)` pair bucket as a secondary signal.

## 3. Multi-dimensional matrix: account, source, and risk

A single `POST /login` can be evaluated across:

1. **Submitted account or identifier:** limits total attempts for the same normalized username, regardless of IP. Apply uniformly even to non-existent usernames.
2. **Trusted request source:** client IP normalized through a trusted proxy boundary; optionally add subnet, ASN, egress network, or verified client credential.
3. **Entire endpoint/tenant:** caps total login traffic to avoid exhausting CPU (password hashing), database, or IdP; have infrastructure protection in front of the backend.
4. **Account–source pair:** detects one source repeatedly trying one account; **supplemental only**, never replacing the two primary axes.
5. **Device/session cookie:** helps distinguish normal flows, though easily cleared or spoofed; must not be the sole evidence.
6. **Risk signals:** number of distinct usernames from one source, new source, bot signals, failure rate, known abusive addresses, anomalous devices, IP reputation, and recent security events.

### 3.1. Check concurrently, not sequentially with OR

Given independent buckets `B_account`, `B_source`, `B_global` and an additional condition `R(request)`. A request is allowed to reach the password verifier only when **all required conditions** pass:

```text
allowed =
    accountBudgetAvailable
    AND sourceBudgetAvailable
    AND globalBudgetAvailable
    AND riskPolicyAllowsOrChallengeCompleted
```

If even one bucket is exhausted, reject/challenge before spending CPU on password verification. In distributed systems, **check and decrement related buckets atomically**, avoiding concurrent requests exceeding limits or decrementing one bucket even though the request ends up blocked by another.

The threshold table is **illustrative for discussion**, not standard values for every product:

| Bucket | Policy example | Objective |
| --- | --- | --- |
| Per account | 5 requests/10 minutes; also track 24-hour failures | Limit distributed brute force |
| Per source/IP | 20 requests/1 minute and 200/1 hour | Reduce credential stuffing from one source |
| Global login | Limit per server/IdP capacity | Prevent infrastructure overload |
| Account × source | 3 failures/5 minutes | Add signal for a repeating pair |
| OTP send | 3 times/10 minutes/recipient + source and cost limits | Prevent spam/SMS pumping |
| High-risk source | Lower threshold or challenge step | Protect when multiple reliable signals fire |

**Must calibrate** thresholds based on real traffic, users behind NAT, mobile patterns, SLOs, and operation sensitivity. Never hardcode "5 failures locks the account permanently"; attackers can intentionally lock mass accounts to cause DoS.

## 4. Choosing an algorithm: fixed window, sliding window, token bucket

### 4.1. Fixed-window counter

Counts requests in slots such as 00:00–00:59, 01:00–01:59. Easy to implement, but attackers can send requests right at the end of one window and start of the next to get nearly double the requests in a short span. Use fixed windows only when boundary bursts are acceptable or additional layers protect against them.

### 4.2. Sliding window

A sliding window counts attempts in the **last 60 seconds**. Implemented with timestamps or approximated using two windows. A sliding log is exact but uses memory proportional to event count; a sliding-window counter approximation is more compact.

Example budget of 3 attempts/60 seconds for Alice:

```text
Time (seconds):    0     10     20     30                 60
                   |      |      |      |                  |
Alice              OK     OK     OK     BLOCK            retry
Count              1      2      3      3                  0/1
```

Once 3 attempts occur at seconds 0, 10, 20, the attempt at second 30 is blocked. After exactly 60 seconds, the event at time 0 leaves the window under the rule that removes `timestamp <= now-window`; at that point a new attempt can be allowed.

### 4.3. Token bucket

A bucket has capacity `C`, refills `r` tokens/second, and each request consumes one token. Approximate token count:

```text
tokens(now) = min(C, tokens(previous) + r * elapsedSeconds)
allow if tokens(now) >= cost
```

Token bucket supports controlled bursts and a long-term average rate; suited for API throughput. Login throttling usually also needs **failure history** and separate account policies because scattered sources can evade short-term limits.

### 4.4. Exponential backoff and progressive challenge

Not every bad signal requires a hard lock. You can increase delay/challenge based on failure count:

```text
delay = min(cap, base * 2^(failures - threshold))
```

Watch out for integer overflow, jitter, wait caps, and not tying up worker threads with `Thread.sleep(...)` per request (easy DoS vector). It is better to return 429/challenge from a gateway or state machine instead of holding connections open. For low risk, only observe; for medium risk, step up with MFA or a bot challenge; for high risk, temporarily deny and alert.

## 5. Identifying accounts without causing username enumeration

A login request contains an **unauthenticated** `username`. It is still useful for account-keyed limiting, but must not be used carelessly:

- Normalize the name according to the identity system's exact rules: whitespace, case sensitivity, Unicode normalization, email aliases if applicable. **Do not** blindly lowercase all usernames if the system's account store is case-sensitive.
- Bound input and body length before constructing keys so attackers cannot force unbounded Redis key creation, choking logs or memory.
- For non-existent usernames, still track budgets and use similar responses/timing as existing usernames, so "which bucket was locked" does not become an account-probing oracle.
- Do not store plaintext usernames/emails in metric labels, easily browsed Redis keys, or logs. Typically store **HMAC-SHA256(normalizedIdentifier, serverSecret)** or an internal ID after lookup policy verification; HMAC reduces dictionary leaks when the username namespace is predictable.
- A trusted tenant ID can be included in the key; unauthenticated client-claimed tenants must be verified before entering authorization policies.
- Public messages must be generic ("Too many requests. Try again later."); never reveal whether the account exists, is locked, or how many attempts remain.
- Throttled accounts risk attacker-induced denial of service via repeated wrong passwords. Use challenges/step-up or protected recovery channels instead of permanent lockouts based on unauthenticated username input.

**Do not clear all limits immediately upon successful login.** You can reset **failure** counters after valid strong authentication, while keeping total request budgets by IP/account and source risk. If all buckets are reset, an attacker holding one valid credential gains a loophole to accelerate or consume resources.

## 6. Determining source IP behind a reverse proxy

Calling `request.getRemoteAddr()` returns the IP of the peer connecting to the servlet. Behind a load balancer/reverse proxy, that can be the **proxy IP**, putting all users into one bucket. Yet directly trusting `X-Forwarded-For` from the client is also dangerous: attackers can forge a new IP on every request to evade limits.

Proper design:

1. Configure the network so the backend only accepts connections from authorized gateways/proxies, restricting direct access.
2. **At the trust boundary**, the gateway must strip all client-sent `Forwarded` and `X-Forwarded-*` headers, then construct a fresh trusted hop chain; never unconditionally append to a client-supplied value.
3. Configure the application/container to honor forwarded headers **only from trusted proxies**; Spring Framework/Servlet container forwarded-header handling can be used. Never manually pick the first/last element of the header without knowing the proxy topology.
4. Normalize IPv4/IPv6, handle dual-stack, IPv6 privacy addresses, and appropriate prefix limits; do not concatenate raw long usernames and IPs into Redis keys.
5. Test behavior with real Nginx/Ingress/CDN, IPv6, multiple hops, and direct non-proxied requests in staging.

**Note:** `ForwardedHeaderFilter` is only useful when the network edge is already protected and headers are sanitized; the filter itself cannot distinguish real vs forged headers if requests can arrive directly from the Internet.

Per-IP helps curb traffic from a single source, but is insufficient against botnet attackers and can affect NAT users. Therefore it is **one axis**, never a reason to omit per-account and risk controls.

## 7. Risk signals: supplement, never replace verification

A risk detector can observe:

- Many distinct usernames tried from the same IP/subnet/ASN in a short time (spraying).
- One account tried from many new sources or experiencing a sudden spike in velocity (distributed guessing).
- Failures relative to successes; frequency of 429s, CAPTCHA failures, unusual user-agents/headers.
- New device/browser, new session cookie, verified IP reputation.
- Location/ASN starkly different from historical usage, logins from regions implausible given prior timestamps.
- High-privilege accounts, sensitive transactions, logins during active leaked-credential alerts.
- Other authentication events such as failed MFA logins, repeated OTT send requests, password resets, token reuse.

**A risk score is not proof of identity.** Fingerprints, user-agents, cookies, and location are easily wrong, spoofed, or unfair. Risk must be combined with verified factors alongside reasonable recovery UX; never auto-grant `ROLE_ADMIN` or skip MFA merely because an IP is rated "good".

Illustrative policy model:

| Risk level | Suggested policy | Must guarantee |
| --- | --- | --- |
| Low | Baseline budgets; normal login | Still verify password/hash, CSRF/session, and permissions |
| Medium | Lower soft thresholds, require challenge or additional MFA | Provide no username enumeration oracle |
| High | Temporarily deny, trigger alert, require protected recovery | No permanent lockouts from easily spoofed signals |
| Very high / widespread attack | Edge protection, service-wide limits, isolate bad traffic | Do not cause outages for legitimate users |

For example, if the risk service returns `StepUpRequired`, the application **must not** accept a POST containing `risk=low` or `X-Trusted-Device=true` set by the client. A challenge is considered complete only when the backend or IdP verifies the result.

## 8. Where in the Spring Security architecture?

A typical `POST /login` request is handled in Spring Security by `UsernamePasswordAuthenticationFilter`, which creates a `UsernamePasswordAuthenticationToken` and invokes `AuthenticationManager`; the provider uses `UserDetailsService` and `PasswordEncoder` to authenticate.

Place throttling in two complementary layers:

```text
Internet → CDN/WAF/Gateway
             | source quota, network region, bot mitigation, global capacity
             v
        Servlet/Spring Security
             | before authentication:
             |  - normalized submitted account
             |  - trusted source
             |  - risk & multi-key reserve
             |  - if exceeded: 429/challenge
             v
   UsernamePasswordAuthenticationFilter
             | AuthenticationManager/Provider
             v
      success/failure events
             | update failure history, user/device risk, telemetry
             v
         session / MFA / authorization
```

**Do not only record `AuthenticationFailureEvent` and throttle afterward:** events fire after credentials are processed, potentially after spending BCrypt/Argon2 CPU. A **pre-auth** filter blocks requests before hashing, while events/handlers reflect outcomes to update risk.

**Spring Security does not provide a complete multi-dimensional throttling suite out of the box.** The framework offers the filter chain, handlers, and events as integration points; bucket algorithms, Redis storage, account policies, risk engines, and observability must be built by the application/infrastructure or integrated from suitable libraries.

### 8.1. Common integration points

| Integration point | Timing | Suitable for what? |
| --- | --- | --- |
| CDN/WAF/API gateway | Before app | Volumetric rate limiting, IP/ASN, bot signals |
| `OncePerRequestFilter` before authentication filter | Before password verifier | Checking account + IP budgets, fast 429 |
| `AuthenticationFailureHandler` | After wrong login | Recording failure risk, unified UI response |
| `AuthenticationSuccessHandler` | After valid login | Recording success, updating risk/session |
| `AuthenticationEventPublisher` and event listeners | After provider emits event | Telemetry and policies shared across multiple methods |
| Method/service authorization | After authentication | Blocking sensitive actions when MFA or tenant policy requires |
| Async analytics | Post-processing | Aggregating patterns and tuning thresholds |

When using both a failure handler and an event listener, avoid **double-counting a single failure**. Pick one authoritative outcome source or attach an event ID/idempotency key.

## 9. Standalone Java 17 program: two separate buckets

The example below implements a **sliding-window log** in a single Java process with two independent limits: at most **3 attempts/minute/account** and **5 attempts/minute/source**. It uses `synchronized` to check both buckets in one JVM operation and uses simulated time for deterministic stdout.

**This is an algorithm demo, not a production solution:** the Map has no TTL/periodic key cleanup, does not use Redis, and does not solve multi-instance, normalization/HMAC, global quotas, or a risk engine. Accounts and sources in the demo are pre-normalized.

**`DualAxisLimiter.java`**

```java
import java.util.ArrayDeque;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class DualAxisLimiter {

    record Rule(String key, int limit, long windowMillis) {}
    record Decision(boolean allowed, long retryAfterMillis) {}

    private final Map<String, ArrayDeque<Long>> timestamps = new HashMap<>();

    public synchronized Decision acquire(
            String accountKey, String sourceKey, long nowMillis) {

        List<Rule> rules = List.of(
                new Rule("account:" + accountKey, 3, 60_000),
                new Rule("source:" + sourceKey, 5, 60_000));

        long retryAfter = 0;
        for (Rule rule : rules) {
            ArrayDeque<Long> hits =
                    timestamps.computeIfAbsent(
                            rule.key(), unused -> new ArrayDeque<>());
            while (!hits.isEmpty()
                    && hits.peekFirst() <= nowMillis - rule.windowMillis()) {
                hits.removeFirst();
            }
            if (hits.size() >= rule.limit()) {
                long wait = hits.peekFirst()
                        + rule.windowMillis() - nowMillis;
                retryAfter = Math.max(retryAfter, wait);
            }
        }

        // Keep atomicity: if one bucket is full, do not write to the other bucket.
        if (retryAfter > 0) {
            return new Decision(false, retryAfter);
        }
        for (Rule rule : rules) {
            timestamps.get(rule.key()).addLast(nowMillis);
        }
        return new Decision(true, 0);
    }

    private static void print(
            DualAxisLimiter limiter,
            String label, String user, String source, long nowMillis) {
        System.out.println(label + " = "
                + limiter.acquire(user, source, nowMillis).allowed());
    }

    public static void main(String[] args) {
        DualAxisLimiter limiter = new DualAxisLimiter();
        long t = 1_000L;

        print(limiter, "alice/ip1", "alice", "ip1", t);
        print(limiter, "alice/ip2", "alice", "ip2", t);
        print(limiter, "alice/ip3", "alice", "ip3", t);
        print(limiter, "alice/ip4", "alice", "ip4", t);

        print(limiter, "bob/ip1", "bob", "ip1", t);
        print(limiter, "carol/ip1", "carol", "ip1", t);
        print(limiter, "dave/ip1", "dave", "ip1", t);
        print(limiter, "eve/ip1", "eve", "ip1", t);
        print(limiter, "frank/ip1", "frank", "ip1", t);

        print(limiter, "alice/after60s", "alice", "ip4", t + 60_000);
    }
}
```

Compile and run from the directory containing the file:

```bash
javac DualAxisLimiter.java
java DualAxisLimiter
```

Exact stdout:

```text
alice/ip1 = true
alice/ip2 = true
alice/ip3 = true
alice/ip4 = false
bob/ip1 = true
carol/ip1 = true
dave/ip1 = true
eve/ip1 = true
frank/ip1 = false
alice/after60s = true
```

**Explanation:** Alice used 3 attempts despite coming from three different IPs, so she is blocked on IP4. IP1 already had Alice/Bob/Carol/Dave/Eve (5 attempts), so Frank is blocked even though Frank's account has zero attempts. After 60 seconds, the old timestamps expire and Alice can try again.

In a real system, you must bound memory/key cardinality, avoid backward clock jumps, use a consistent clock source, and store shared state across instances. This mechanism counts **every attempt**, not just wrong passwords, so it needs UX policies to prevent account lockout DoS.

## 10. Spring Security Servlet: blocking before form login

The integration example **compiles once an implementation of `LoginGate` is provided** (managed Redis/bucket store). It intentionally separates the **contract/adapter** from the limiter backend to avoid pretending a local Map solves the multi-instance problem.

### 10.1. Contract between filter and throttle service

**`LoginGate.java`**

```java
package com.example.loginprotection;

public interface LoginGate {

    record Decision(boolean allowed, long retryAfterSeconds) {}

    // Service is responsible for normalizing/HMACing username, source, and
    // atomically checking + reserving required buckets.
    Decision reserve(String submittedUsername, String trustedSourceAddress);

    // Record success/failure events into risk/failure counters.
    // Do not use this outcome to wipe per-IP or per-attempt budgets.
    void recordOutcome(String submittedUsername,
                       String trustedSourceAddress,
                       boolean success);
}
```

Implementations should build Redis keys from identifiers normalized with the same lookup rules as the identity system; the raw username in the interface **stays only in request memory**, never logged or placed in metric labels. `trustedSourceAddress` is the IP past the trust boundary, not an arbitrarily read `X-Forwarded-For`.

### 10.2. Pre-authentication filter

**`LoginRateLimitFilter.java`**

```java
package com.example.loginprotection;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

public final class LoginRateLimitFilter extends OncePerRequestFilter {

    private final LoginGate gate;

    public LoginRateLimitFilter(LoginGate gate) {
        this.gate = gate;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !("POST".equals(request.getMethod())
                && "/login".equals(request.getServletPath()));
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        final LoginGate.Decision decision;
        try {
            decision = gate.reserve(
                    request.getParameter("username"),
                    request.getRemoteAddr());
        } catch (RuntimeException failure) {
            // Avoid allowing through when limits cannot be checked.
            response.sendError(
                    HttpServletResponse.SC_SERVICE_UNAVAILABLE);
            return;
        }

        if (!decision.allowed()) {
            response.setStatus(429);
            response.setContentType("application/json;charset=UTF-8");
            response.setHeader("Cache-Control", "no-store");
            // Do not disclose which account / bucket was exhausted.
            response.getWriter().write(
                    "{\"error\":\"Too many attempts. Try again later.\"}");
            return;
        }

        chain.doFilter(request, response);
    }
}
```

**Conditions for this code to be correct in a real app:**

- Only works for default `POST /login`; if `loginProcessingUrl` is changed, update the matcher accordingly. `getServletPath()` depends on Servlet mapping/context path.
- The gateway must cap request body size and normalize the remote address before the filter reads parameters.
- The `LoginGate` implementation must check **both account and source** (and global bucket if present), using shared/atomic storage. Do not swallow all errors and "allow through if Redis is down".
- Return 429 with a generic message. If using `Retry-After`, pick an appropriately rounded duration without leaking the bucket, remaining count, or username.
- If username is missing/overly long, the service must have a dedicated input policy and still apply source/global limits. Do not map all blank inputs to one account key that locks out other users.
- Do not register the filter as a `@Component`/`@Bean Filter` for global Boot registration while also calling `addFilterBefore`; instantiate it inside the chain or disable automatic Servlet registration.

### 10.3. Wiring into SecurityFilterChain and tracking outcomes

**`SecurityConfig.java`**

```java
package com.example.loginprotection;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain security(
            HttpSecurity http, LoginGate gate) throws Exception {

        var success = new SavedRequestAwareAuthenticationSuccessHandler();
        var failure = new SimpleUrlAuthenticationFailureHandler("/login?error");

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .successHandler((request, response, auth) -> {
                            gate.recordOutcome(
                                    request.getParameter("username"),
                                    request.getRemoteAddr(),
                                    true);
                            success.onAuthenticationSuccess(
                                    request, response, auth);
                        })
                        .failureHandler((request, response, exception) -> {
                            gate.recordOutcome(
                                    request.getParameter("username"),
                                    request.getRemoteAddr(),
                                    false);
                            failure.onAuthenticationFailure(
                                    request, response, exception);
                        }))
                .addFilterBefore(
                        new LoginRateLimitFilter(gate),
                        UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}
```

**Behavior:** the filter intercepts before `UsernamePasswordAuthenticationFilter`, so no password hashing runs if budget is exhausted. After an actual form-login attempt, success/failure handlers update outcome signals; do not count again via listeners without idempotency. `/login` allows anonymous access, yet **the throttle filter still processes POSTs**; `permitAll()` does not mean skipping custom filters.

The code above is a **Spring Boot 3.x / Security 6.x integration snippet** in a project with web/security dependencies, a user store, a password encoder, and an **application-provided LoginGate implementation**. It is not a system with a pre-built Redis limiter; you must implement the backend and test it in practice. Default browser form login still uses CSRF protection. For MockMvc POST /login, supply a CSRF token in tests.

**Handling outcome errors:** in a production app, `recordOutcome` should have observable error handling and idempotency; do not let non-critical telemetry backend issues break already-succeeded authentication unpredictably. However, **reserve** failures before password checking must follow fail-closed or an explicitly risk-analyzed degraded control, not default permit.

## 11. Distributed state storage: Redis and atomic operations

A per-instance `Map`/`ConcurrentHashMap` is **insufficient** with multiple pods. Attackers can send concurrent requests to multiple instances, each counting locally and allowing more attempts than the limit. Typically use Redis with TTL and atomic primitives (Lua/functions), or a centralized rate-limit service at the gateway.

### 11.1. Key structure

Suppose the service has HMACed the username into a short string:

```text
rl:login:acct:<HMAC(normalizedUsername)>      # all sources on the same account
rl:login:src:<normalizedSourceId>             # all accounts from the same source
rl:login:global                               # overall endpoint protection
rl:login:pair:<accountDigest>:<sourceDigest>  # optional, does not replace the 2 axes
```

In production, use appropriate Redis hash tags/sharding if running a multi-key script on Redis Cluster: all KEYS in an atomic Lua command **must reside on the same hash slot**, or redesign the architecture. Do not blindly funnel all traffic onto one hot slot/key at high scale; move some protection layers to the gateway, use hierarchical quotas, and clear partitioning strategies.

### 11.2. Illustrative Lua sliding-window log

This is an **illustrative Lua script for single-node Redis or same-slot KEYS**; each key is a Sorted Set holding timestamps of accepted attempts. A unique attempt ID is needed so `ZADD` does not overwrite entries with identical timestamps.

Inputs: `KEYS[1]` account, `KEYS[2]` source; `ARGV[1]` windowMilliseconds; `ARGV[2]` unique random attemptId; `ARGV[3]` account limit; `ARGV[4]` source limit. Clock is taken from Redis `TIME` to reduce clock skew across app nodes.

```lua
local clock = redis.call("TIME")
local now = tonumber(clock[1]) * 1000
          + math.floor(tonumber(clock[2]) / 1000)

local window = tonumber(ARGV[1])
local attemptId = ARGV[2]
local limits = { tonumber(ARGV[3]), tonumber(ARGV[4]) }
local boundary = now - window

for i = 1, 2 do
    redis.call("ZREMRANGEBYSCORE", KEYS[i], "-inf", boundary)
end

for i = 1, 2 do
    if redis.call("ZCARD", KEYS[i]) >= limits[i] then
        return {0, now}
    end
end

for i = 1, 2 do
    redis.call("ZADD", KEYS[i], now, attemptId)
    redis.call("PEXPIRE", KEYS[i], window)
end

return {1, now}
```

Atomicity: if **either** bucket is full, the script does not `ZADD` to **either** bucket; if both have room, it writes both entries in a single Redis operation. `attemptId` must be unique per request, not the username or timestamp (multiple requests share the same millisecond).

**What is still missing for production:** ARGV type/range validation; capping key cardinality and memory, max payload, TTL, Redis eviction policy, optional Lua execution time limits, metrics; error handling and retry idempotency on timeout; behavior during Redis failover/partitions, multi-window limits, global quotas, and risk scores. On Redis Cluster, keep keys in the same slot or adjust computation; never run a cross-slot script assuming cluster-wide transactions.

An easily missed detail: if the Redis request succeeds but the network response is lost, a client retry with a **new attemptId** consumes extra quota. Proper idempotency, retry, and error-handling policies are required. Bucket state must not live forever for arbitrary random usernames; enforce TTLs and global caps at ingress.

### 11.3. Data not to store

Never store passwords, OTPs, bearer tokens, or session cookies in keys, values, or logs. Never use raw emails/usernames as high-cardinality metric labels. Only track event categories: `allowed`, `limited_by_account`, `limited_by_source` (internal only), `challenge_required`, `redis_error`, `login_success`, and `login_failure` with appropriate sampling/privacy.

## 12. Notes on success and failure outcomes

**Pre-auth attempt budget** and **failure history** are not the same:

- Attempt budgets stop resource exhaustion **before** password hashing, counting both right and wrong requests.
- Failure history updates only when authentication actually **fails**, helping compute risk and delays/challenges.
- Success events record legitimate behavior and may lower suspicion on an account/device, but do not wipe risk signals for an IP/botnet.

Spring Security 6.5 supports `AuthenticationFailureEvent` and `AuthenticationSuccessEvent` when `AuthenticationEventPublisher` is configured; you can use `DefaultAuthenticationEventPublisher` with `@EventListener`. Form login also has `AuthenticationFailureHandler` / `AuthenticationSuccessHandler`.

Example publisher configuration (if the app wants provider-level events):

```java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher publisher) {
    return new DefaultAuthenticationEventPublisher(publisher);
}
```

This is a **snippet placed inside an `@Configuration` class** with imports from `org.springframework.security.authentication.AuthenticationEventPublisher`, `DefaultAuthenticationEventPublisher`, and `org.springframework.context.ApplicationEventPublisher`, not a standalone Java file. If using event listeners, do not count outcomes in both handlers **and** listeners without idempotency.

Note when authenticating via external OIDC, API keys, client credentials, or WebAuthn: events and username locations may differ from form login. Never assume every `Authentication.getName()` is a user email or every failure has an existing principal. Rate-limiting password endpoints and OAuth2 callbacks requires distinct keys/policies.

## 13. MFA, CAPTCHA, and recovery paths

### 13.1. MFA reduces the value of leaked passwords

MFA, especially suitable phishing-resistant methods, reduces account takeover when passwords are guessed or leaked. However, MFA does not replace a limiter: attackers can still burn CPU, spam push/OTP, or lock accounts.

Risk-based step-up can require MFA on new devices, unusual sources, or sensitive actions. Do not allow bypassing MFA solely because an IP is allowlisted if policy mandates stronger authentication.

### 13.2. CAPTCHA is only an additional layer

CAPTCHA can raise automation costs, though solving services and bypass techniques exist. Never trust client-sent `captchaPassed=true` to bypass rate limits; the server must verify the challenge, bound to the request/session and TTL. For users with screen readers, slow networks, or VPNs, provide accessible solutions and recovery paths.

### 13.3. Password reset and code-sending paths are separate targets

For `/forgot-password`, `/reset-password`, `/otp/send`, `/otp/verify`, or magic-link generation:

- Track **recipient/account**, **IP/source**, distinct target count, device, delivery channel, and global cost.
- Return generic messages whether or not the account exists; avoid using per-account counters in ways that create an oracle.
- Cap OTP sending and verification frequency, enforce TTL, single-use, anti-replay, and SMS cost controls.
- When an account is login-throttled, recovery flows must be independently protected and never become a weak authentication shortcut.
- Do not share the same threshold for GET login page and POST password, as demand and cost differ.

Similarly, `/mfa/verify` needs code-guessing limits by user/transaction/credential, not IP alone. An OTP with a small keyspace demands stronger brute-force protection than a high-entropy password endpoint.

## 14. Policies for returning 429, 401, and 403

| Case | Typical response | Notes |
| --- | --- | --- |
| Exceeded rate limit pre-auth | `429 Too Many Requests` | Generic message, optionally rounded `Retry-After` |
| Wrong username/password with remaining budget | Normal login failure | Web forms usually redirect with error; APIs may return 401 |
| Successful login | Per login flow | Session/context created by Spring Security |
| Authenticated user lacking permission | `403 Forbidden` | Authorization; not a password failure |
| Limiter service unavailable | `503` or fail-closed degraded mode | Defined by risk/SLO; never default permit |
| Too many wrong OTP attempts | Block/challenge per OTP policy | Never allow unlimited OTP guessing |
| Locked user or non-existent account | Generic response | Do not turn internal details into a username oracle |

For web forms, returning JSON 429 is not always ideal because browsers need proper UX. You can show a generic notice page or challenge, without disclosing "account exists", "which source was blocked", or exact remaining attempts. If using `Retry-After`, do not give exact timestamps precise enough for attackers to synchronize attacks.

**Distinguish limiter errors from authentication failures:** during a Redis outage, do not increment "wrong password" for millions of accounts. Conversely, when an account lacks credentials, do not return messages indicating whether the account is in the DB.

## 15. Multi-axis testing in Spring Security

### 15.1. Mandatory test matrix

| Scenario | What must be proven |
| --- | --- |
| Many passwords on 1 username from many IPs | Per-account budget blocks despite source rotation |
| One IP tries many distinct usernames | Per-source budget blocks despite few attempts per account |
| One account/IP pair repeating continuously | Does not exceed budget; pair bucket if present only supplements |
| Account has budget left but IP is exhausted | Request is blocked |
| IP has budget left but account is exhausted | Request is blocked |
| Non-existent username | Response/timing does not leak account existence |
| NAT source with many legitimate users | Thresholds/challenges avoid unrecoverable false positives |
| Multiple concurrent instances/pods | Quota not exceeded via races/local counting |
| Concurrent requests right at quota boundary | Allowed requests do not exceed limit |
| Redis timeout/failover | Does not default to passing through to password verifier unlimited |
| Spoofed `X-Forwarded-For` | Does not create fake sources to evade limits |
| JWT/OIDC login, OTP, recovery routes | Have dedicated policies, no bypass paths |
| User logs in successfully | Risk signals updated; per-source budget not wiped |
| Account intentionally spammed with wrong passwords | Recovery/challenges exist without excessive lockout DoS |
| User has MFA but high risk | Step-up per policy, authentication not skipped |
| No keys/passwords/tokens leaked in logs | Observability remains sufficient for diagnostics |

### 15.2. Testing algorithms vs testing wiring

**Algorithm unit tests:** use a fake clock (as in the Java example) to test windows, counts, atomic denial, boundaries, and cleanup. Never use `Thread.sleep` just to make tests pass faster.

**MockMvc security tests:** with Spring Boot 3.x, create `@SpringBootTest` + `@AutoConfigureMockMvc`, use a mock/fake `LoginGate`, and call `POST /login` with `.with(csrf())`. Verify over-limit requests return 429 **before** `AuthenticationManager` runs; verify normal requests reach the login filter. When testing the happy path, configure a test user/password encoder or authentication provider.

Example **MockMvc snippet**, not a standalone test class:

```java
mvc.perform(post("/login")
        .param("username", "alice@example.test")
        .param("password", "not-real")
        .with(csrf()))
    .andExpect(status().isTooManyRequests());
```

Conditions for the test above to hold: the `LoginGate.reserve(...)` test double must return `Decision(false, ...)` for the request, and the filter must be wired into the chain. Thus you cannot copy the snippet into a project and assume the limiter works without configuring the stub and context.

**Distributed integration tests:** run multiple app instances against real Redis/Testcontainers, concurrently sending requests with the same account but different IPs, and same IP but different accounts; allowed counts must not exceed quotas, even under retries, network latency, and clock skew. Write tests for XFF spoofing through proxies, Redis failover, key eviction, and OIDC/MFA endpoints outside form login.

### 15.3. Evaluate more than just "blocked bots"

Beyond blocked request counts, measure **false positives**: real users blocked inside large NATs, login success rate, MFA challenge completion, password reset success, and support tickets. An overly aggressive limiter degrades real accessibility and can be abused by attackers to deliberately lock users out.

## 16. Operations and data security

Useful metrics:

- Total login attempts, successes/failures/429s per endpoint.
- Percentage/time hitting limits by **axis type**, without logging account details.
- Rate of accounts failing from many IPs, rate of IPs trying many accounts, count of new sources.
- Store/Redis latency, retries, failovers, active bucket count, memory, eviction rate.
- CAPTCHA/MFA step-up rates, completion rates, false-positive complaints.
- Password hashing CPU load, DB/IdP latency, and email/SMS consumption.

**Privacy protection:** do not write passwords, tokens, OTP codes, or full usernames/emails into unnecessary telemetry. IP addresses may be personal data; define purpose, retention period, access controls, anonymization, and matching legal policies. Avoid using PII or high-cardinality keys as metric labels; separate safe access logs from security audit logs.

**Incident plan:** during a credential stuffing surge, tighten quotas at the gateway, raise challenges for high-risk cohorts, alert users showing compromise signs, and require resets/step-up per policy. Never turn off logging or drop all rate limits under overload; prioritize protecting the authentication core per SLOs and reviewed fallback mechanisms.

## 17. Common implementation mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Limiting by IP only | Botnet rotates IPs, brute force on one account continues | Add independent per-account limit |
| Limiting by account only | Spraying one password across many accounts | Add per-source and global limits |
| Using only `IP:username` key | Fails to block IP sweeps or IP rotation on one account | Use two independent buckets + secondary pair |
| Trusting client-sent `X-Forwarded-For` | IP spoofing bypasses quotas | Strip/write headers at trust boundary, verify proxy |
| Using local counters across multiple pods | Quota multiplied by instance count | Distributed atomic limiter |
| Blocking only after password verifier outcomes | CPU/hashing already consumed | Pre-auth gate before verifier |
| Resetting all buckets on login success | Acceleration loophole after one valid credential | Reset only failure signals intentionally |
| Permanently locking account after a few errors | Attackers cause user DoS | Progressive challenges and protected recovery |
| Distinct "user does not exist" / "account locked" replies | Username enumeration | Generic public responses, similar timing |
| Storing emails/passwords in Redis keys/logs | Data leaks and increased risk | HMAC identifiers, redact secrets, retention |
| Returning exact bucket ID on 429 | Attackers optimize attack cadence | Generic response, internal telemetry |
| Using CAPTCHA instead of rate limiting | Bypassed by bots/challenge solving | Defense in depth |
| Calling `Thread.sleep` on every bad request | Exhausts worker threads, self-inflicted DoS | Non-blocking async challenge / 429 / backoff |
| Disabling entire limiter on Redis failure | Attackers exploit outages | Clear fail-closed or degraded controls |
| Limiting POST login but omitting OTP/reset/API login | Bypass via alternate flows | Inventory all auth endpoints |
| Skipping time-boundary/concurrency tests | Bursts/races exceed quotas | Fake clock + concurrency integration tests |
| Not managing key count/TTL | Memory exhaustion from fake usernames | Input bounds, TTL, global ingress caps |

## 18. Practice exercises

1. Write tests for `DualAxisLimiter`: Alice tries from 4 different IPs, and IP1 tries 6 different usernames. Why do two independent axes block two distinct attack patterns?
2. Port the local demo to a Redis sorted-set or token bucket, ensuring both buckets are checked and consumed **atomically** when multiple pods process concurrently.
3. Configure Nginx/Ingress to strip client-supplied `X-Forwarded-*`. Test from the same source IP with a forged `X-Forwarded-For` header on each request; can the budget be bypassed?
4. Design policies for `POST /otp/send`, `POST /otp/verify`, and `POST /password/reset` with per-recipient, per-IP, global cost, failed attempts, and reuse limits.
5. Use MockMvc to prove requests are rejected by the gate **before** the password verifier runs; preserve the CSRF token in form-login POST tests.
6. Design a risk rule detecting an IP trying 500 accounts in one hour with only one attempt per account. Why is per-account-only insufficient?
7. Design UX for a user intentionally spammed with wrong passwords by an attacker: challenge, recovery, cooldown, support escalation, and avoiding username enumeration.
8. Build a dashboard tracking 429s, false positives, challenge success, Redis latency, and success rates for large NAT users.
9. Run a test restarting a backend or failing over Redis under heavy concurrent requests; determine quota drift bounds and degraded mode behavior.

## 19. Summary and references

- **Per-account limits** defend against distributed brute force on one user; **per-source limits** stop one IP from trying many accounts; they must remain independent and never be replaced by a pair key.
- **Risk** guides adaptive protection levels, but does not replace password/MFA verification or prove identity.
- **Pre-authentication**, throttling reduces CPU/hashing exhaustion; **post-authentication**, events/handlers update failure/risk history.
- **Multi-instance systems** require a distributed store and atomic operations, with TTL, memory bounds, metrics, and failure policies.
- **Proxies/IPs need a trust boundary** to prevent XFF spoofing; avoid over-blocking NAT users.
- **Never leak account existence**, never log secrets, never let reset/OTP/MFA become bypasses, and never widen blocking scope beyond necessity.
- **Test across all three dimensions**: account, source, risk; including concurrency, recovery, false positives, and real users.

References:

- [OWASP Authentication Cheat Sheet — Login Throttling](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Credential Stuffing Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html)
- [OWASP Bot Management and Anti-Automation — Rate Limiting](https://cheatsheetseries.owasp.org/cheatsheets/Bot_Management_and_Anti-Automation_Cheat_Sheet.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html)
- [Spring Security — Servlet Filter Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Framework — Forwarded Headers and ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
- [RFC 6585 — HTTP 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585)