# Login Rate Limiting, Anti-Enumeration, and Infrastructure Coordination

**Context:** Operating and protecting **Spring Security Servlet/Spring MVC** applications on Java 17+, Spring Boot 3.x, Spring Security 6.x. The topic is not merely "allow at most N wrong password attempts": a system must distinguish brute force, password spraying, credential stuffing, and **account enumeration**, enforce limits across multiple layers, avoid accidentally locking out legitimate users, and measure/respond when traffic flows through CDNs, WAFs, reverse proxies, API gateways, or Identity Providers (IdPs).

The limit values in the examples are **assumptions for learning**, not fixed recommended thresholds for every organization. Real configurations must be based on legitimate traffic rates, account types, NAT/mobile network scale, account risk, testing costs, and telemetry.

## 1. Understanding the Threats Accurately

| Behavior | How attackers probe | Why limiting by username or IP alone is insufficient |
| --- | --- | --- |
| **Brute force** | Trying many passwords against one account. | IP-only limits can be bypassed with botnets; account-only limits can be abused to cause denial of service. |
| **Password spraying** | Trying a few common passwords across many accounts. | Few attempts per account evade account-level thresholds; requires IP/ASN/campaign signals. |
| **Credential stuffing** | Using email:password lists leaked from other systems. | Each pair may be tried once; requires device, behavioral, IP reputation, breached-password checks, and MFA/passkeys. |
| **Account enumeration** | Determining whether usernames/emails exist via login, signup, reset, or APIs. | Rate limiting alone does not eliminate differences in status, body, latency, and email side effects. |
| **Distributed low-and-slow** | Many IPs/hosts, each sending few requests over a long period. | Requires long-horizon aggregation, anomaly detection, and identity/source risk management. |
| **Resource exhaustion** | Sending many requests triggering expensive CPU hashing, DB queries, or IdP calls. | Blocking too late after authentication will not save enough resources. |

**Distinguish authentication from authorization:** a login limiter slows down **authentication attempts**; after login, Spring Security still checks authorities, ownership, and tenant/resource boundaries. Rate limiting **does not** make a valid account "allowed to do everything".

### 1.1. Common Enumeration Surfaces

Account enumeration can happen across many endpoints:

- `POST /login`: "Wrong password" vs. "Account does not exist".
- `POST /forgot-password`: "Email sent" vs. "No such email".
- `POST /signup`: "Email already in use".
- `POST /mfa/verify` or `/mfa/setup`: differences between accounts with/without MFA.
- `POST /unlock-account`, resending verification emails, member invitations, OAuth2/OIDC linking.
- User lookup APIs or username-availability endpoints.
- **Measurable** differences, not just text: HTTP status, redirect `Location`, headers, response size, timing, email delivery counts, out-of-band notifications, and even how the limiter increments counters.

Therefore, maintain an **account-neutral** policy across sensitive flows without breaking legitimate UX or making false claims. For example, a forgot-password endpoint can reply "If a matching account exists, we will send instructions" even when the email does not exist.

### 1.2. Counterproductive Mistakes

- **Locking accounts immediately after three failures** lets attackers deliberately lock out thousands of real accounts (denial-of-service/lockout abuse).
- **Locking by IP alone** can block entire offices, schools, or mobile networks sharing NAT.
- **Locking by username alone** is easily bypassed by spraying across many usernames.
- **Trusting arbitrary `X-Forwarded-For` headers** lets attackers spoof IPs, bypass rate limits, or lock out others.
- **Returning 404 when no account exists vs. 401 on wrong password** turns the endpoint into an enumeration oracle.
- **Testing only one instance** while deploying multiple replicas with local counters gives each replica its own separate quota.

## 2. Defense in Depth: Each Layer Doing the Right Job

```text
Internet / botnets / real users
             │
             ▼
CDN / edge / WAF / bot management
  - per-source request-rate & bot signals
  - IP/ASN/reputation, geo anomalies (if policy applies)
  - traffic shaping, challenge when appropriate
             │ [trusted forwarding/trace headers]
             ▼
Ingress / Load Balancer / API Gateway
  - TLS connections, request size, timeouts
  - per-route/client rate limits and upstream protection
  - strip forged source headers, limit request bursts
             │
             ▼
Spring Security Servlet app (multiple replicas)
  - route-specific login attempt control
  - account + source + device/session risk signals
  - generic authentication-failure messages
  - MFA/passkeys/step-up, audit, metrics
             │
             ├── shared counter (suitable Redis/DB)
             │
             └── Identity Provider / User store
                   - verify password / SSO / MFA
                   - official lock/recovery/risk policy
```

**Edge/WAF** sees broad traffic and absorbs CPU/DB load before requests reach Java. However, the edge does not always know account identities or trusted authentication outcomes.

**Gateway/Ingress** throttles routes, connections, and resources. A gateway can apply token buckets by client/IP/path, yet risks conflating users behind NAT. It does not replace account-state and auth-policy checks.

**Spring Security/application** has business semantics: canonicalized usernames, login success/failure, MFA status, tenants, and account sensitivity. It should enforce account-dependent decisions and emit controlled telemetry.

**The IdP**, if performing password authentication, directly observes failed credentials and may already enforce lockout/risk protection. When the application is an **OAuth2/OIDC Client**, the Spring backend usually **never receives user passwords**; rate-limiting local `POST /login` form auth does not cover the IdP's login screen.

**Shared counters** ensure replicas see the same quota. Using a per-node in-memory counter causes effective system-wide limits to scale with replica count or be bypassed via load balancing.

### 2.1. Where to Enforce Limits?

| Layer | Appropriate key/signal | Strengths | Risks/caveats |
| --- | --- | --- | --- |
| CDN/WAF | IP, ASN, route, reputation, bot fingerprint | Early protection, large scale | False positives, privacy, proxy-masked IPs. |
| API gateway | Source, path, authenticated API client | Burst protection, protects upstream | Shared IPs/NAT; lacks account signals. |
| App before password hashing | Source + canonicalized username + risk | Saves CPU during bursts | Can cause account lockout if hard-blocking. |
| App after `AuthenticationFailure` | Trusted auth result + account/risk | Separates success/failure, strong telemetry | Hash/DB/IdP cost already spent; must avoid leaking account existence. |
| IdP | User, network, MFA, breached credentials | Centralized login policy | Needs callback and UX coordination; avoid conflicting duplicate limits. |
| Redis/shared store | Atomic counters, TTL, cross-node | Consistent across replicas | Latency/outages, hot keys, operations/HA. |

The recommended design uses **multiple moderate signals** instead of a single hard lockout, combined with monitoring and step-up authentication when needed. Never set quotas so low that real users on shared networks get blocked en masse.

## 3. Choosing Rate-Limit Keys: IP, Account, Combined, and Behavioral

### 3.1. By IP

For example, `ip:203.0.113.10` caps total login requests from one source within a time window. It curbs simple bursts, yet:

- One IP address can represent many real users behind NAT/VPN/carrier gateways.
- Botnets can rotate across thousands of IPs.
- Client IP behind ingress may be **the proxy's address**, not the user's.
- IPv6 allocates many addresses per network; prefix/aggregation policies must be evaluated to avoid unfair penalties.

IP should be combined with risk signals, never treated as an account identity.

### 3.2. By Account (or Submitted Username)

For example, `acct:HMAC(normalizedUsername)` bounds password-guessing density per login name. Key considerations:

- Use the **exact same canonicalization rules** as user lookup. If usernames are case-sensitive while the limiter ignores case, two distinct users share a bucket; if lookup is case-insensitive while the limiter is case-sensitive, attackers vary casing to bypass limits.
- **Create buckets for nonexistent usernames too**; if the limiter only increments counters for real accounts, response/rate behavior leaks existence.
- Hard-blocking by account name lets attackers lock victims out. Instead of permanent lockouts, consider progressive delays, step-up challenges, IP+account quotas, and sound recovery flows.
- Raw username keys (email/phone) stored in Redis or logs can leak personal data; use **HMAC keys with a secret** when minimizing PII exposure. Unkeyed SHA-256 of common emails remains vulnerable to dictionary guessing.

### 3.3. Multi-Dimensional Combinations

A common model tracks:

1. **Per-IP:** curbs bursts from one source (with NAT allowance).
2. **Per-account:** protects one identity against distributed IPs.
3. **Per-IP + account:** catches repeated pairs without blocking an entire IP shared by distinct users.
4. **Per-device/session:** assists risk scoring, though client identifiers can be cleared or forged.
5. **Global/campaign:** distinct usernames attempted, failure ratios, ASN/reputation, and repeated-password patterns under privacy-compliant policies (never store passwords to "group" raw secrets).

Never treat a device-ID cookie as proof of identity, since attackers can delete or replace cookies. Fingerprinting carries privacy and accuracy trade-offs; evaluate legal and operational constraints before adopting it.

### 3.4. Which Data May Be Logged?

Log **safe aggregated events**: timestamp, auth flow type, decision (allow/throttle/challenge), route, classified reason, trace ID, policy-processed IP/ASN, and pseudonymized account keys if needed.

**Never log** passwords, Authorization headers, session cookies, reset tokens, OTPs, client secrets, or raw form bodies. Avoid writing raw usernames/emails to general dashboards. Restrict log read permissions and set retention.

## 4. Limiting Mechanisms: Fixed Window, Sliding Window, and Token Bucket

| Algorithm | How it works | Pros | Cons |
| --- | --- | --- | --- |
| **Fixed window counter** | At most N attempts per time window. | Simple, cheap, good for demos. | Boundary bursts: nearly 2N requests in a short span. |
| **Sliding window** | Counts events over the "last T seconds" or an approximation. | Fairer in real time. | More memory/complex logic. |
| **Token bucket** | N tokens refilled at a steady rate; each request spends one token. | Permits controlled bursts while capping average rate. | Requires clock/counter sync and careful quota tuning. |
| **Leaky bucket/queue** | Processes at a fixed rate or rejects when full. | Smooths load. | Long queues can time out logins. |
| **Progressive backoff** | Delays/challenges increase with risk and failures. | Slows brute force without instant hard locks. | Needs UX, fairness, risk tuning, and anti-enumeration care. |
| **Hard lockout** | Locks account after N failures. | Effective in certain high-risk environments. | Abusable for DoS; requires unlock workflows. |

**No algorithm solves account enumeration by itself.** Response shaping and application flows must be aligned independently of quotas.

**There is no "one-size-fits-all" threshold:** e.g., "5 attempts/minute" is only for deterministic test output. Production must measure legitimate error rates, shared-IP ratios, peak login volume, bot traffic, and false-positive impact.

### 4.1. HTTP Response When Throttled

Typically you can return `429 Too Many Requests` with a `Retry-After` header so clients know when to retry; here 429 means **rate-limited**, without revealing whether the account exists.

```http
HTTP/1.1 429 Too Many Requests
Content-Type: text/plain; charset=UTF-8
Retry-After: 60

Request is rate-limited. Please try again later.
```

Avoid revealing sensitive details like "Account alice has 4 failed attempts, 1 remaining". Across both login APIs and UIs, response bodies, structures, messages, redirects, and retry behavior must remain **account-neutral**. Millisecond-accurate retry headers that differ between existing and nonexistent accounts can also create side channels.

**Important:** 429 does not replace 401/403. Below quota, bad auth returns 401 for APIs or 302 to the login page for Spring form login. In browser logins, 403 can also be a CSRF error.

## 5. Standalone Java 17: Testable Fixed-Window Limiter

Before integrating Spring Security, build a **runnable Java SE model** to understand concurrency and time windows. The code uses `ConcurrentHashMap.compute` to update per-key counters atomically within a single JVM, taking timestamps as a parameter so tests do not depend on wall clocks.

**`src/main/java/com/example/limit/FixedWindowLimiter.java`**

```java
package com.example.limit;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

public final class FixedWindowLimiter {

    private record Window(long startMillis, int count) {}

    private final ConcurrentHashMap<String, Window> windows =
        new ConcurrentHashMap<>();
    private final int maxAttempts;
    private final long windowMillis;

    public FixedWindowLimiter(int maxAttempts, long windowMillis) {
        if (maxAttempts <= 0 || windowMillis <= 0) {
            throw new IllegalArgumentException("limits must be positive");
        }
        this.maxAttempts = maxAttempts;
        this.windowMillis = windowMillis;
    }

    public boolean tryAcquire(String key, long nowMillis) {
        AtomicBoolean allowed = new AtomicBoolean(false);

        windows.compute(key, (k, previous) -> {
            Window current = previous;
            if (current == null
                    || nowMillis < current.startMillis()
                    || nowMillis - current.startMillis() >= windowMillis) {
                current = new Window(nowMillis, 0);
            }

            if (current.count() >= maxAttempts) {
                return current;
            }

            allowed.set(true);
            return new Window(
                current.startMillis(),
                current.count() + 1
            );
        });

        return allowed.get();
    }

    public static void main(String[] args) {
        FixedWindowLimiter limiter =
            new FixedWindowLimiter(3, 60_000);

        for (int n = 1; n <= 4; n++) {
            System.out.println("alice-" + n + "=" +
                limiter.tryAcquire("acct:alice", 1_000));
        }

        System.out.println("bob=" +
            limiter.tryAcquire("acct:bob", 1_000));

        System.out.println("alice-new-window=" +
            limiter.tryAcquire("acct:alice", 61_000));
    }
}
```

Compile from the project root with JDK 17+ (this class has **no** Spring dependency):

```bash
javac -d out src/main/java/com/example/limit/FixedWindowLimiter.java
java -cp out com.example.limit.FixedWindowLimiter
```

**Exact stdout:**

```text
alice-1=true
alice-2=true
alice-3=true
alice-4=false
bob=true
alice-new-window=true
```

Explanation:

- Alice gets 3 attempts in the window starting at millisecond 1000; the fourth is rejected.
- Bob's key has an independent counter.
- 61000 minus 1000 equals 60000 ms: the old window expires and Alice gets a fresh attempt.
- `ConcurrentHashMap.compute` guarantees per-key atomic updates within the **same JVM**.
- `AtomicBoolean` only carries the result out of the lambda; it is not a global access counter.

**Serious limitations of the demo model:**

1. The map never **evicts** old keys; attackers sending endless fake usernames can grow memory unboundedly. Production needs TTL/eviction and resource caps.
2. Each instance has its own map; unsuitable for multiple replicas.
3. System clocks can jump; the algorithm guards against backward jumps by resetting, yet production should use consistent/synchronized time sources (especially with Redis).
4. Fixed windows allow boundary bursts.
5. `tryAcquire` counts **every attempt**, including successes; it does not handle success/failure differentiation, MFA, or risk by itself.
6. If an attacker freely varies usernames, account keys do not stop spraying; combine with per-IP/global risk controls.

This class is for studying/testing logic, **never marketed as a production rate limiter**.

## 6. Attaching the Limiter to Spring Security Servlet Before Form Login

Default Spring Security form login handles `POST /login` via `UsernamePasswordAuthenticationFilter`. A `OncePerRequestFilter` placed **before that filter** can reject throttled requests **before password verification burns CPU/DB**.

The configuration below limits by IP and normalized username. It intentionally uses an **in-memory map** to illustrate the interception point; replace it with a shared backend store or gateway-aware limiter before running multiple replicas in production.

### 6.1 LoginThrottleFilter.java

**`src/main/java/com/example/limit/LoginThrottleFilter.java`**

```java
package com.example.limit;

import java.io.IOException;
import java.util.Locale;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public final class LoginThrottleFilter extends OncePerRequestFilter {

    // Demo values only; tune before production.
    private final FixedWindowLimiter byIp =
        new FixedWindowLimiter(20, 60_000);
    private final FixedWindowLimiter byAccount =
        new FixedWindowLimiter(5, 60_000);

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !"POST".equals(request.getMethod())
            || !"/login".equals(request.getServletPath());
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        long now = System.currentTimeMillis();

        // RemoteAddr is the connecting peer; behind a proxy this may be the proxy's IP.
        String ip = request.getRemoteAddr();
        String supplied = request.getParameter("username");

        // Use lowercase only if the login system uses the same rule.
        String account = supplied == null
            ? ""
            : supplied.strip().toLowerCase(Locale.ROOT);

        if (account.length() > 128) {
            account = "<oversized>";
        }

        // Count both existing and nonexistent accounts.
        boolean allowedIp = byIp.tryAcquire("ip:" + ip, now);
        boolean allowedAccount =
            byAccount.tryAcquire("acct:" + account, now);

        if (!allowedIp || !allowedAccount) {
            response.setStatus(429);
            response.setHeader("Retry-After", "60");
            response.setContentType("text/plain; charset=UTF-8");
            response.getWriter().write(
                "Request is rate-limited. Please try again later."
            );
            return;
        }

        chain.doFilter(request, response);
    }
}
```

**Relative safety highlights of the snippet:** does not query the DB for account existence before rate-limiting; applies account keys to all username values (including nonexistent ones). It checks both per-IP and per-account and does not read `X-Forwarded-For` straight from callers. Rate-limiting runs **before** password verification.

**Insufficient for production:** raw usernames in maps, no TTL eviction, single IP may be a gateway/proxy IP, does not distinguish auth flows, no circuit breaker on store failure, no auditing, and no challenge/soft-backoff mechanism. This filter is intentionally illustrative.

### 6.2 SecurityConfig.java

**`src/main/java/com/example/limit/SecurityConfig.java`**

```java
package com.example.limit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication
    .UsernamePasswordAuthenticationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .addFilterBefore(
                new LoginThrottleFilter(),
                UsernamePasswordAuthenticationFilter.class
            );

        return http.build();
    }
}
```

**Explanation:**

- `formLogin(...)` enables the default login page and processes `POST /login`; default credential parameters are `username`/`password`.
- `LoginThrottleFilter` runs only on `POST /login`, leaving GET assets untouched. `/login` is `permitAll` so unauthenticated users can submit credentials; **`permitAll` does not bypass the throttle filter**.
- `addFilterBefore(..., UsernamePasswordAuthenticationFilter.class)` places the limiter ahead of Spring Security's password verification step.
- The code instantiates `new LoginThrottleFilter()` directly inside the filter chain instead of declaring a `Filter @Bean` and registering it again; this avoids **double registration** where Spring Boot auto-registers a servlet filter and Spring Security also adds it.
- Default CSRF **remains enabled**. For browser POST logins, the frontend must send a valid CSRF token. MockMvc tests need `with(csrf())` when testing rate limiting rather than CSRF.
- In production, keep account state out of login errors and use `AuthenticationFailureHandler`, `AuthenticationSuccessHandler`, and `AuthenticationEventPublisher`/events for outcome-based metrics. **Do not count only failed passwords if pre-check CPU hashing is already exposed to flooding.**

### 6.3 Application.java

**`src/main/java/com/example/limit/Application.java`**

```java
package com.example.limit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

Use Spring Initializr to generate a Gradle project with **Spring Boot 3.x**, Java 17+, and dependencies **Spring Web**, **Spring Security**, **Spring Boot Starter Test**. Add test support:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is the `dependencies` block; keep the plugins/repositories generated by Initializr. For apps with a real user repository, configure `UserDetailsService` and `PasswordEncoder`. When relying solely on demo auto-configuration, Spring Boot may create a default user and log a generated password in dev; **never carry that default user mechanism into production**.

### 6.4 Request Flow

```text
POST /login + CSRF token + form username/password
      │
      ▼
Spring Security FilterChain
      │
      ├── CSRF check: request must be valid
      │
      └── LoginThrottleFilter (before UsernamePasswordAuthenticationFilter)
             │
             ├── allowed → UsernamePasswordAuthenticationFilter
             │                   │
             │                   ├── authentication success
             │                   └── authentication failure (redirects by default)
             │
             └── limited → 429 / Retry-After / generic message
```

**Do not misunderstand:** `429` is emitted **before password checking**, so it does not disclose "account exists" or "password right/wrong". The demo filter also does not reset the counter after a successful login, avoiding hiding parts of behavior in tests/logic. Production policies should specify exactly how counters update on success, failure, step-up, lockout, captcha, and IP changes.

## 7. MockMvc HTTP Testing: Blocked, Allowed, and CSRF

Goal: verify the **first five login attempts** for a username within the window pass through to `UsernamePasswordAuthenticationFilter`, while the next attempt returns 429 **before** authentication. Because the demo uses an account limit of 5 and IP limit of 20, behavior is deterministic with one username/test case.

**`src/test/java/com/example/limit/LoginThrottleFilterTest.java`**

```java
package com.example.limit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request
    .MockHttpServletRequestBuilder;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class LoginThrottleFilterTest {

    @Autowired
    MockMvc mvc;

    private MockHttpServletRequestBuilder login(String username) {
        return post("/login")
            .param("username", username)
            .param("password", "invalid-for-demo")
            .with(csrf())
            .with(request -> {
                request.setRemoteAddr("192.0.2.20");
                return request;
            });
    }

    @Test
    void sixthAttemptGets429WithoutAccountLookup() throws Exception {
        for (int i = 0; i < 5; i++) {
            // Spring formLogin redirects by default on failed login.
            mvc.perform(login("unknown@example.test"))
                .andExpect(status().is3xxRedirection());
        }

        mvc.perform(login("unknown@example.test"))
            .andExpect(status().isTooManyRequests())
            .andExpect(header().string("Retry-After", "60"));
    }

    @Test
    void missingCsrfIsRejectedBeforeLogin() throws Exception {
        mvc.perform(post("/login")
                .param("username", "new-user@example.test")
                .param("password", "invalid-for-demo"))
            .andExpect(status().isForbidden());
    }
}
```

**Test conditions:** the Spring Security filter chain must be integrated with MockMvc, e.g., `@SpringBootTest` + `@AutoConfigureMockMvc` above. The test needs no real user because the first five attempts use a nonexistent username; default form login handles failures with a redirect. The test name does not prove account lookup **did not run** during the first five attempts; it proves **the sixth request is blocked at the limiter** and nonexistent usernames are throttled just like any other username. To verify invocation counts on user stores or `PasswordEncoder`, use an appropriate test spy/instrumentation.

**Important for parallel tests:** the filter holds state in the context; if multiple tests share a username/key and run concurrently, they will collide. Use distinct test identifiers, isolate contexts, or design resettable clock/store mocks in unit tests. Never raise thresholds just to "fix" a flaky test.

### 7.1. Additional Account-Neutral Properties to Verify

The suite above does not compare **existing vs. nonexistent accounts**. In production, test a real user fixture (e.g., `alice`) and a nonexistent user with wrong passwords, verifying:

- identical HTTP status/redirect patterns and public messages;
- no disclosure of "account not found" or "account locked" unless allowed by policy;
- consistent throttle/challenge rules regardless of account lookup outcome;
- no abnormal differences in response headers, sizes, or timing distributions;
- email/SMS reset flows never reveal account presence via responses.

**Timing:** measure distributions across many runs in a stable environment rather than expecting two requests to match to the microsecond. When existing users run an expensive `PasswordEncoder` while nonexistent users return fast, attackers can use statistics to enumerate accounts. Spring Security includes mechanisms to reduce timing discrepancies in some providers; custom authentication code should consider dummy password hashing and steady DB lookup paths **without creating a new DoS vector**. Never claim "constant time" without evidence.

### 7.2. Independent Unit Test for Clock/Threshold

For `FixedWindowLimiter`, test without `Thread.sleep`:

```java
@Test
void resetsOnlyAfterWindowExpires() {
    FixedWindowLimiter limit = new FixedWindowLimiter(2, 1000);

    assertTrue(limit.tryAcquire("acct:a", 10_000));
    assertTrue(limit.tryAcquire("acct:a", 10_001));
    assertFalse(limit.tryAcquire("acct:a", 10_999));
    assertTrue(limit.tryAcquire("acct:a", 11_000));
    assertTrue(limit.tryAcquire("acct:b", 10_999));
}
```

This is a **JUnit test method snippet** to place in a test class with `@Test` and JUnit assertion imports. Fixing time makes tests far more reliable than waiting on wall clocks. Also test concurrency races if production limiters use a shared store.

## 8. Ensuring Account Enumeration Never Leaks Through Responses

### 8.1. A Generic Error Message

For Spring form login, the message can be:

> "Invalid login credentials."

Do not distinguish "email not found", "wrong password", or "account disabled" on a public page **without a policy-approved reason accepting that disclosure**. That does not stop the backend from recording detailed reasons in an access-restricted audit stream.

For password reset:

> "If the details match an account, we will send instructions."

Ensure responses do not change just because an account does not exist—including status codes, redirects, JSON shape, public headers, and rate-limiter behavior. **Never promise "email sent" when no account exists** in a way that asserts an action occurred; conditional phrasing is more accurate.

### 8.2. Subtle Enumeration Leak Points

| Location | Common mistake | How to reduce risk |
| --- | --- | --- |
| Login failure | "Username not found" differs from "wrong password". | Generic failure, measure timing, uniform attempt policy. |
| Reset password | 404 when email is missing. | Generic 2xx/202 response per contract; enqueue email only when appropriate. |
| Signup | Reporting email already registered unnecessarily. | Safe registration workflow; minimize disclosure per UX design. |
| MFA challenge | Issuing challenges only for real accounts with visibly different responses. | Gate MFA after account verification; generic pre-auth UX. |
| Throttle quota | Creating keys only for real accounts; differing `Retry-After`. | Increment counters for every identifier; account-neutral responses. |
| Error pages | Stack traces/exception messages containing usernames or user status. | Normalize external errors, redact, audit internally. |
| Password hash timing | Skipping hash for unknown users while running BCrypt for known users. | Use framework providers or proper dummy verification; measure in real environments. |
| SSO/OIDC login mapping | Returning detailed errors like "email unlinked" or user state. | Privacy-preserving error UX, account-linking policy, restricted logs. |

### 8.3. Should You Hard-Lock Accounts?

Hard lockouts can fit certain risk models, yet should never be the sole response. An attacker only needs to submit wrong passwords for a known username to lock the victim out; at scale, this causes outages via "reverse password spraying".

Complementary options: throttle by account + source, add progressive delays, require step-up/risk-based challenges, alert on unfamiliar sources, and require strong trusted-channel verification before unlocking. Ensure support/recovery workflows do not introduce new **account enumeration** paths.

**CAPTCHA** should only be one signal/challenge in a defense stack: bots can solve or outsource solving them, and CAPTCHAs impose UX, accessibility, and privacy costs. CAPTCHA does not replace rate limits, MFA/passkeys, or credential-stuffing detection.

## 9. Multi-Replica Operations: Atomic Redis Counters, TTL, and Failover

In multi-instance deployments, a central store or distributed limiter is required. For example, a fixed window using **Redis Lua** makes `INCR + PEXPIRE` atomic, preventing races and keys without TTLs.

**`login_counter.lua`** (illustrates the Redis algorithm; Spring Boot does not run this file automatically by itself):

```lua
local key = KEYS[1]
local maximum = tonumber(ARGV[1])
local windowMillis = tonumber(ARGV[2])

local count = redis.call('INCR', key)

if count == 1 then
    redis.call('PEXPIRE', key, windowMillis)
end

local remainingMillis = redis.call('PTTL', key)

if count > maximum then
    return {0, count, remainingMillis}
end

return {1, count, remainingMillis}
```

Example invocation in a test environment with Redis and the script in the working directory:

```bash
redis-cli --eval login_counter.lua login:ip:example , 5 60000
```

The script returns an array of `allowed` (1/0), count, and TTL in ms. Output depends on Redis state at runtime; no fixed output is assumed. The key `login:ip:example` is a **demo name only**; production needs environment/app/route namespacing, TTLs, data retention, bounded key cardinality, and HMAC for account identifiers.

**Why Lua:** `INCR` and `PEXPIRE` inside a script execute atomically on Redis; two separate commands risk failing after `INCR` before setting TTL, leaving an immortal key. Large systems must also evaluate Redis HA/clustering, load, hot keys, memory eviction, clocks, network partitions, and failover behavior.

**The Lua script above is still a fixed window**, with boundary bursts and returning internal counts/TTLs. **Never expose per-account counts in public HTTP responses** if they can create side channels. Use sliding windows or token buckets when smoothness is needed, and prefer vetted providers/libraries over untested custom distributed algorithms.

### 9.1. Deciding What Happens When the Shared Store Fails

| Option | Benefit | Risk |
| --- | --- | --- |
| **Fail open**: allow requests when Redis errors | Real users can still log in. | Attackers can bypass quotas while the store is down, hammering CPU/IdP. |
| **Fail closed**: block logins when Redis errors | Shrinks brute-force surface. | Can cause a total login outage on Redis/network blips. |
| **Bounded fallback** | Preserves partial availability and protection. | Complex; per-replica quotas; requires circuit breakers/monitoring. |

Choose the policy based on login sensitivity, MFA availability, operational risk, SLOs, and incident procedures. **Never** leave fail-open/fail-closed implicit. Monitor cache/store errors and alert; avoid retry storms that prevent Redis from recovering.

### 9.2. Avoiding "Lost Counters" When Scaling

- Test multiple instances hitting the same key and window; total allowed requests must match the system-wide policy.
- Verify replica restarts do not reset limits if policy requires consistency; in-memory counters definitely reset on process restart.
- Test concurrent requests crossing the threshold; server-side atomicity must not grant extra tokens beyond policy.
- Measure per-login overhead, P95/P99 Redis latency, error rates, and network impact.
- Enforce key TTLs/capacity; attackers can send endless random usernames to exhaust Redis memory without cardinality bounds.
- Account for non-canonical, oversized, or Unicode-variant usernames/sources; normalize before keying and enforce input length bounds.

## 10. Reverse Proxies and Real IPs: Trust Only Verified Hops

A common architecture:

```text
Internet client
    │ (real IP)
    ▼
CDN/WAF ── X-Forwarded-For? ──> Ingress ──> Spring Boot
                                         request.getRemoteAddr()
                                         may = ingress IP
```

**`request.getRemoteAddr()` returns the connecting peer address known to the servlet container.** If connections arrive from ingress, that value may be the ingress IP, causing **all users to share one quota**. Conversely, reading `X-Forwarded-For` or `Forwarded` straight from Internet requests is **unsafe**, because clients can forge those headers unless sanitized by the proxy.

Extract the original client address only when:

1. You know the exact proxies/load balancers allowed to reach the backend and their hop order.
2. Ingress/WAF **strips or overwrites** client-supplied forwarded headers outside the trust policy.
3. The backend **cannot be reached directly**, bypassing ingress.
4. Trusted-proxy/forwarded-header processing in infrastructure/containers is verified; never enable "trust all proxies" by default.
5. Tests spoof `X-Forwarded-For: 1.2.3.4` to confirm requests cannot switch buckets arbitrarily.

Spring Boot includes forwarded-header settings for URL/proxy handling, but **enabling forwarded headers does not prove headers are trustworthy**. The trust boundary must be enforced at the network/ingress layer with an appropriate parser.

### 10.1. Avoiding Duplicate Counting Between Edge and App

A request might be blocked at the WAF before reaching Spring, or Spring might return 429 after the gateway let it through. If each layer uses uncoordinated thresholds, the UI sees confusing behavior. Use:

- Secret-free request IDs/correlation IDs propagated across layers.
- Metrics clearly identifying **decision source**: `edge_limit`, `gateway_limit`, `app_login_limit`, `idp_risk_challenge`.
- Consistent HTTP contract: 429 with clear messaging, `Retry-After` if appropriate, no account-state disclosure.
- Dashboards tracking block rates, false positives, and latency per layer.
- On-call coordination when tuning thresholds or mitigating campaigns; never let edge and app teams set conflicting quotas independently.

## 11. OAuth2/OIDC Logins and MFA: Different Enforcement Points from Local Forms

### 11.1. Form Login Checked by Spring Security

With `UsernamePasswordAuthenticationFilter` and `UserDetailsService`, the app directly receives form usernames/passwords. An app-level filter before `POST /login` cuts password-hashing load. For password failures, the server should use a generic failure handler and internal auditing.

### 11.2. OAuth2 Login / OIDC SSO

When a web app uses `oauth2Login()` in Spring Security, **passwords are entered at the IdP**, not the client app. The app should:

- Let the **IdP** handle password brute force, credential stuffing, MFA, and primary login policies.
- Throttle anomalies on **authorization initiation** (`/oauth2/authorization/{registrationId}`) by source/session if redirect abuse is a risk, without blocking legitimate users.
- Monitor `/login/oauth2/code/{registrationId}` callbacks and state/missing-session errors; never block valid callbacks with an overly tight per-IP bucket, especially behind NAT.
- Never use rate limiting as an excuse to **skip `state`, `nonce`, PKCE, or token validation**. Protocol protections remain mandatory.
- Coordinate with the IdP on account lockouts, risk-based MFA, session lifetimes, and account recovery. App-side 429s cannot replace IdP policies.

### 11.3. MFA, OTP, and Passkeys

- OTP verification must cap code guesses per **challenge/session/account** with TTLs, not just IP.
- Backup/recovery codes must be single-use, attempt-limited, and protected like high-value credentials.
- Passkeys/WebAuthn reduce credential phishing, yet registration, login initiation, recovery, sessions, and abuse endpoints still need risk-based rate controls.
- For risk-based step-up, the server must decide after policy verification; never trust client-submitted flags like `mfaPassed=true`.
- Account recovery can be an easier attack path than login; enforce generic responses, rate limiting, strong verification, and auditing.

## 12. Observability: Metrics, Logs, Alerts, and Incident Response

Separate key metrics:

| Metric | Purpose |
| --- | --- |
| `auth_attempts_total{flow,outcome}` | Total attempts and failure ratios across form/SSO/MFA. |
| `auth_throttled_total{layer,reason}` | Separate 429s from edge/gateway/app/IdP. |
| `auth_failure_ratio` | Detect failure anomalies; separate UX issues from attacks. |
| `distinct_account_keys_per_source` | Detect password spraying (over pseudonymized data). |
| `distinct_sources_per_account` | Detect distributed brute force. |
| `login_latency_seconds` | Measure hashing/Redis/IdP overhead. |
| `rate_store_errors_total` | Track Redis/throttle-store failures and applied fallback policy. |
| `false_positive_reports` | Reduce blocking real users, especially on NAT IPs. |
| `mfa_challenge_rate` and `recovery_attempts` | Observe fallback paths when primary login is targeted. |

**Never use raw usernames/emails/IPs as Prometheus labels**: cardinality explodes, personal data leaks, and monitoring backends overload. Metric labels should stay **bounded** (flow/layer/outcome/risk bucket); detailed investigative data belongs in an audit store with proper ACLs and retention.

### 12.1. Signals of Specific Attack Types

- **Single-account brute force:** rapid failure spikes on one account key, many password attempts, potentially across many IPs.
- **Spraying:** one source or source group trying many distinct accounts at low per-account frequency, with a high failure ratio.
- **Credential stuffing:** many account/password pairs attempted, possibly with suspicious successes; correlate post-login account takeover signals.
- **Enumeration:** traffic concentrated on lookup/reset/signup, many usernames, exploitation of response/timing differences.
- **False lockouts:** 429 spikes on shared networks, rising support tickets, real users reporting inability to log in.

Detection should not rely on request counts alone: bots can operate slowly, and real users can retry repeatedly due to app bugs.

### 12.2. When an Alert Fires

1. Identify which layer emitted 429, traffic profile, affected population, and Redis/IdP health.
2. Separate attacks from UX regressions, client retry loops, buggy mobile apps, or NAT networks.
3. If an attack, tune edge/gateway/app per playbook; add challenges/MFA, block clear offending sources, and protect reset/MFA endpoints.
4. If false positives, widen quotas under control, add exemptions based on trusted signals (never user-supplied headers), and assess impact on sensitive accounts.
5. If the rate-store is down, activate the pre-defined fallback and monitor auth failure rates and DB CPU.
6. Check for account takeover signs, session anomalies, credential resets, and audits; follow incident response procedures.
7. Afterward, add regression/chaos tests and recalibrate baselines—never just bump thresholds and close the ticket.

## 13. Critical Test Cases Before Production

### 13.1. Quota Enforcement

| Case | Test | What to observe |
| --- | --- | --- |
| Within quota | 1–N attempts with same key | Reaches authentication; response matches valid/wrong credential. |
| Over quota | (N+1)th attempt | 429/challenge per policy; avoids expensive auth work. |
| Window expired | Request after TTL | Handled under fresh counter. |
| Multiple accounts from one IP | Try distinct usernames | Per-IP/behavioral rules still spot spraying without blindly blocking whole NATs. |
| One account from many IPs | Distribute attempts | Account-level/campaign rules still observe. |
| Two replicas | Alternate requests across 2 backends | Total quota holds, not multiplied per instance. |
| Concurrent requests | Burst past threshold concurrently | Atomic counters do not grant excess attempts beyond policy. |
| Redis unavailable | Temporarily disconnect Redis | Fail-open/closed/fallback behaves per playbook with metrics. |
| Clock boundary | Attempts near TTL boundary | No major fixed-window boundary bypass, or mitigated by secondary rules. |
| Key explosion | Many random usernames | Memory/TTL/eviction/capacity stays bounded. |

### 13.2. Anti-Enumeration

| Test | Expected |
| --- | --- |
| Real username + wrong password | Public response does not reveal account state. |
| Nonexistent username + wrong password | Intentionally identical message/status/redirect. |
| Real username + exhausted quota | Do not reveal account-specific quota if it leaks presence. |
| Nonexistent username + exhausted quota | No abnormal exception just because DB lookup fails. |
| Forgot password with/without email | Generic response; no account existence leak. |
| Locked/disabled account | Policy-aligned UX without leaking extra info to attackers. |
| Email/username varying case, whitespace, Unicode | Same canonicalization as user store; no quota bypass. |
| Oversized/invalid identifier | Input bounded; prevents memory/key explosion and verbose errors. |
| Invalid CSRF or malformed request | Blocked at right layer; no password logged; no skewed auth metrics. |
| Spoofed `X-Forwarded-For` header | Cannot pick arbitrary source buckets. |

### 13.3. Real User Experience Testing

- User mistypes twice then logs in right: not excessively penalized.
- Users behind shared NAT: source quotas do not unreasonably lock out an entire network.
- Users on screen readers or unable to solve CAPTCHAs: suitable accessible alternatives exist.
- Clients hitting 429: do not spin in tight retry loops; honor `Retry-After`/backoff and show clear messages.
- Authenticated sessions are not falsely blocked by the login limiter; never apply `POST /login` quotas to all APIs.
- MFA or account recovery does not accidentally bypass primary login counters or open new enumeration paths.
- Ops can tell **who/what triggered 429** without viewing passwords or sensitive headers.

## 14. Common Implementation Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Bots rotate `X-Forwarded-For` to evade limiter | Backend trusts client-sent headers. | Trust only configured hops/proxies; strip/overwrite headers at ingress. |
| Scaling replicas gives attackers more attempts | Local per-JVM counters. | Shared Redis/gateway quotas; test cross-node. |
| Entire office gets 429 | Relies solely on NAT IP. | Combine account/session/risk signals; tune IP thresholds reasonably. |
| Users locked out by others' wrong tries | Hard account lockouts enable DoS. | Soft backoff, step-up, risk scoring, recovery, monitoring. |
| Account enumeration via `Retry-After` | Counters created only for existing accounts. | Create counters before lookup; account-neutral responses. |
| Account enumeration via latency | Unknown users fail faster than password hashing. | Audit custom auth providers, dummy hash/constant-shape paths, measure statistically. |
| POST login returns 403 even below quota | CSRF filter blocks before login. | Supply valid CSRF token; never disable CSRF. |
| Valid login still gets 429 | Demo counts all attempts without resetting on success. | Design controlled success/failure policy; avoid naive resets enabling bypasses. |
| Redis runs out of memory | Unbounded raw username keys without TTL. | Bounded key cardinality, TTLs, HMAC keys, capacity/eviction policies. |
| 429 returned yet DB still overloaded | Blocked too late after hashing or IdP calls. | Edge prefilter + app pre-auth gate; measure DB CPU. |
| Throttling IdP login has no effect | App throttles only local `POST /login`; passwords are at IdP. | Coordinate rate controls at IdP and OIDC initiation/callback. |
| CAPTCHA causes high drop-off | All users challenged too early. | Risk-based triggers, accessibility, measurement. |
| Monitoring explodes cardinality | Usernames/IPs in metric labels. | Low-cardinality labels and details in ACL-protected audit stores. |
| Whitelisting via `X-Internal-User` header | Callers can forge the header. | Use mTLS/service identity, network trust, and proxy-enforced metadata. |

## 15. Operations and Design Checklist

1. Map all auth flows: local forms, JSON login APIs, OAuth2/OIDC SSO, password resets, MFA, passkeys, service auth.
2. Measure real traffic, NAT/proxy breadth, and failure baselines before picking thresholds/algorithms.
3. Combine keys: IP, account, IP+account, campaign/ASN, while guarding against account lockout abuse.
4. Align canonicalization with the user store; keep raw usernames/emails out of unprotected logs/metrics.
5. Use generic public errors for account existence; test statuses, bodies, redirects, headers, timing, and reset paths.
6. Keep CSRF active on browser forms/sessions; never use rate limiting to replace authentication or CSRF protection.
7. Place limiters early enough before hashing/DB/IdP when needed, while collecting post-auth outcomes to spot campaigns.
8. Use a shared atomic store for multi-replica deployments; set TTLs/eviction and decide fail-open/closed/fallback before outages occur.
9. Trust forwarded IPs only behind verified proxies/ingresses and block direct backend bypasses.
10. Coordinate CDN/WAF/gateway/IdP/app via trace IDs, standardize 429/`Retry-After`, and separate decision layers.
11. Monitor false positives, brute-force/spraying/stuffing signals, Redis errors, user recovery, and SLOs.
12. Test concurrency, multi-instance, clock boundaries, key explosion, spoofed forwarded headers, and infrastructure failures.
13. Use MFA/passkeys and protect recovery flows; never rely solely on CAPTCHAs or quotas.
14. Document incident playbooks and threshold-tuning workflows with review, audit, and rollback.

**Key Takeaways:** Effective login rate limiting is a **multi-layer defense strategy**, not a counter in one JVM. Spring Security Servlet can block early on `POST /login`, yet anti-enumeration requires consistent responses and account-state handling; distributed brute force requires shared counters and signals; NAT/reverse proxies demand strict trust boundaries; and OAuth2/OIDC logins require coordination with the IdP itself. Testing must cover **permissions, real-user experience, multiple replicas, and infrastructure failure modes**, not merely "the sixth attempt returns 429".
