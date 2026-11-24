# Login Attempt Throttling and Coordinating Anti-Enumeration with Infrastructure

> **Scope:** Protecting Spring Security logins on Java 17+, Spring Boot 3.x/Spring Security 6.x against brute force, password spraying, credential stuffing, and malicious automation. Connects **application, Identity Provider (IdP), WAF/CDN, reverse proxy, API gateway, Redis, and observability**. The illustrative example runs on a single JVM; the distributed deployment sections specify requirements before production.

## 1. Identifying the problem

Storing passwords with BCrypt/Argon2 does not by itself stop an attacker from **sending thousands of password guesses to the login endpoint**. You must control attempt counts, rate, and risk—without locking out legitimate users because a bot intentionally sends wrong passwords to their accounts.

| Attack type | Behavior | Indicators | Defenses |
| --- | --- | --- | --- |
| Brute force | Many passwords for **one account**, possibly rotating IPs. | High failure count per account. | Account counters, progressive delay/step-up, MFA. |
| Password spraying | A few common passwords across **many accounts**. | Many usernames from same IP/ASN, few failures per account. | IP/network/risk detection, IdP/WAF controls. |
| Credential stuffing | Trying leaked username/password pairs from external breaches. | Many accounts, many IPs, potentially successful logins. | MFA/passkeys, bot mitigation, login success/failure and breached-credential checks. |
| Username enumeration | Guessing valid accounts via responses/timing. | Different errors by account state. | Generic errors/statuses, timing mitigation, throttling unknown users too. |
| Authentication resource exhaustion | Flooding login to exhaust password-hashing CPU or DB. | High CPU, rising queues/latency. | Early WAF/gateway request limits, pre-auth checks, backpressure. |

**Authentication** verifies passwords/tokens; **throttling** decides whether a request may reach authentication. Once quota is exhausted, **even a valid password may be temporarily rejected**: this must be reflected in UX and your threat model. Never adopt a blanket "5 wrong tries locks for 24 hours" rule as a universal standard.

## 2. Defense in depth, never a single rule

```text
Browser / Mobile / API client
       |
       v
CDN / WAF / Bot & DDoS protection
  - request rate, IP reputation, ASN, burst, challenge
       |
       v
Trusted reverse proxy / API gateway
  - TLS, canonical client IP, route-specific quotas
       |
       v
Spring Security / authentication endpoint
  - CSRF (when cookie login), pre-auth rate check
  - UserDetailsService / AuthenticationProvider / password hash
  - failure/success handling; account-aware policy
       |
       +--> Distributed counters (Redis atomic + TTL)
       |
       +--> IdP / MFA / passkeys / breached-password checks
       |
       v
Structured logs + metrics + SIEM / alert + incident response
```

**WAF/gateway** sees raw traffic before the application burns CPU. **The application** knows normalized usernames, users/tenants, login failures/successes, and business policies. **The IdP** protects passwords/MFA when real login happens externally via OIDC. **Redis/shared stores** keep state consistent across pods. **Monitoring** spots distributed attacks and false positives. Layered defense lowers miss rates and avoids turning one failing component into a system-wide hole.

### 2.1. Responsibilities by component

| Layer | Appropriate responsibilities | What it cannot replace |
| --- | --- | --- |
| CDN/WAF | Blocking bots/floods, rate/bot challenges, IP reputation, traffic anomalies. | Real account permissions, password correctness, tenant membership. |
| Proxy/gateway | Route limits, TLS, request bounds, canonical IP, blocking origin bypass. | Determining whether a username exists in the database. |
| Spring Security | Password providers, CSRF/session, auth handlers, account-aware limiters. | Edge anti-DDoS or distributed counters if using RAM only. |
| Redis | Atomic counters, TTL, sharing quotas across instances. | Identity policy, MFA, and bot reputation. |
| IdP | Password-guessing defense, MFA/SSO, account risk, token issuance. | App-specific owner/tenant authorization. |
| Monitoring/on-call | Investigating distributed attacks, tuning policies, incident response. | Synchronous login protection if only alerting post-facto. |

**Specifically for OIDC/SAML:** when browsers redirect to the IdP to enter passwords, the BFF/Spring Security OAuth2 client **never sees the user's password**. Limiting `POST /login` in the app does not replace rate limits/MFA/lockout at the IdP; the app still must protect its callbacks, sessions, logout, and its own endpoints.

## 3. Choosing rate-limit keys

| Key | What it catches | Trade-offs |
| --- | --- | --- |
| **Account/normalized login ID** | Attacks targeting one account across many IPs. | Can be abused to lock victims out; must also apply to non-existent accounts. |
| **IP** | Concentrated bots and some password spraying. | Corporate/mobile NAT, VPNs, IP rotation; false positives. |
| **IP prefix/ASN/risk** | Botnet clusters or anomalous networks. | Shared networks and legitimate VPNs can overlap. |
| **Account + IP** | Persistent attacks from one source on one account. | IP rotation produces endless distinct pairs. |
| **Session/device signal** | Repeated behavior across IPs. | Can be cleared/spoofed; needs privacy policy and TTL. |
| **Route/global burst** | Floods exhausting CPU and connections. | Setting too low causes legitimate-traffic outages. |
| **Verified client/tenant** | Abuse by an identified partner/tenant. | Never trust self-asserted client ID or tenant headers. |

Never rely solely on IP or account. Designs typically combine **edge request rates**, **per-account failure counts**, **network-level abuse detection**, **MFA/step-up**, and **monitoring**. High-value accounts may require stricter controls while users behind shared NAT need generous IP thresholds.

### 3.1. Windows, thresholds, and actions

Every policy must specify:

1. Threshold (requests or failures), window (e.g., minutes), burst, and cooldown.
2. Fixed/sliding window, token bucket, or leaky bucket; keyed by IP, account, or combined.
3. Action: monitor, progressive delay, CAPTCHA/bot challenge, step-up MFA, HTTP 429, or temporary lock.
4. State store: single node or Redis; TTL, cleanup, max keys, and data privacy.
5. When to increment: before password verification for request admission, or after authentication failure?
6. When to reset: partial reset on success, window expiry, audited admin override?
7. Failover when Redis/edge fails, scalability, alerts, and rule ownership.
8. UX: generic responses, retry guidance, recovery paths, and false-positive handling.

**There is no universal threshold for all products.** `5 failures/account` and `12 failures/IP` in the example below are **for testing illustration only**, not security benchmarks or recommended production defaults.

### 3.2. Request quotas differ from failure counters

- **Pre-auth admission quota:** checked/reserved **before** password hashing, mitigating CPU DoS. Production requires atomic reservation so concurrent requests cannot simultaneously bypass the threshold.
- **Failure counter:** incremented **after** the provider determines login failed, useful for detecting per-account brute force. Checking preflight and recording failures afterward allows parallel requests to slip past the quota before counters increment.
- **Successful login:** used to analyze account-compromise risk and optionally reset the account counter; **never reset all IP/global counters** just because one account logged in successfully.

Account lockout can be weaponized into a user DoS. Under high risk, prefer **challenges/MFA/progressive delays**, short cooldowns, and safe recovery over long-term hard locks.

## 4. Error messages, enumeration, and 401/403/429

| Outcome | HTTP/UX by model | What to distinguish |
| --- | --- | --- |
| Wrong username/password, quota remaining | Demo returns **401** with generic message. | Never distinguish "user not found" from "wrong password". |
| Login attempt limit reached | Demo returns **429 Too Many Requests** and `Retry-After`. | Never leak account state via messages or status differences depending on user existence. |
| Browser login POST missing CSRF | **403 Forbidden**. | CSRF failure differs from throttling; never disable CSRF to fix it. |
| Unauthenticated request to auth-required endpoint (form login) | Usually **302** redirect to login. | For HTTP Basic/Bearer APIs, usually **401**. |
| Valid login, within quota | Demo **200**; session established. | Throttling and password validation are two separate checks. |

OWASP recommends generic responses for non-existent users, wrong passwords, and locked or disabled accounts while minimizing noticeable timing differences. A per-account `429` can leak information if non-existent accounts are not counted or behave differently. Apply the same policy to non-existent account keys and minimize status/message divergence based on account existence.

**Never put usernames/passwords, raw tokens, cookies, or OTPs in logs, metrics, or error bodies.** For forgot-password, return a message like "If the account exists, instructions have been sent"; registration, OTP/email resends, magic links, recovery, and refresh tokens are also abuse vectors requiring dedicated limits.

## 5. Runnable Java 17+ example on a single Spring Boot instance

This example uses default form login/session and CSRF to show clearly where the limiter hooks into Spring Security. **This is not a multi-pod production solution**: in-memory counters are not shared across instances and have a race between precheck and failure callback. Later sections explain how to replace them with Redis/edge controls.

**Demo policy:** within a 5-minute window, 5 failures on the same account (even across IPs) or 12 failures from the same IP (even across usernames) cause the **next attempt** to receive 429. A successful login resets the account counter but **does not reset the IP counter**. Unknown usernames are also counted. Counters use `System.currentTimeMillis` at runtime and a controllable clock in tests; expired buckets reset when next accessed.

### 5.1. Gradle project

`settings.gradle`:

```groovy
rootProject.name = 'login-throttle-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot 3.3.5 is pinned for reproducible dependencies in this lesson; **it is not the newest Spring Boot release or a recommended production target in 2026**. For real systems, pick a branch actively receiving security patches. Requires JDK 17+ and a compatible Gradle 8.x.

### 5.2. Complete application code

Create `src/main/java/demo/loginthrottle/LoginThrottleApplication.java`; one public class plus package-private classes/records in the same Java file is valid.

```java
package demo.loginthrottle;

import java.io.IOException;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.function.LongSupplier;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class LoginThrottleApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginThrottleApplication.class, args);
    }
}

class LoginAttemptLimiter {
    private static final long WINDOW_MS = 5 * 60_000L;
    private static final int MAX_PER_ACCOUNT = 5;
    private static final int MAX_PER_IP = 12;

    private record Bucket(long start, int failures) {}

    private final LongSupplier nowMillis;
    private final Map<String, Bucket> accounts = new HashMap<>();
    private final Map<String, Bucket> ips = new HashMap<>();

    LoginAttemptLimiter(LongSupplier nowMillis) {
        this.nowMillis = nowMillis;
    }

    private String accountKey(String username) {
        // Demo assumes case-insensitive usernames.
        // Production uses canonical identity per IdP.
        return username == null
            ? "<missing>"
            : username.strip().toLowerCase(Locale.ROOT);
    }

    private void increment(Map<String, Bucket> table,
                           String key, long now) {
        Bucket old = table.get(key);
        if (old == null || now < old.start()
                || now - old.start() >= WINDOW_MS) {
            table.put(key, new Bucket(now, 1));
        } else {
            table.put(key, new Bucket(old.start(), old.failures() + 1));
        }
    }

    private long waitFor(Map<String, Bucket> table,
                         String key, int threshold, long now) {
        Bucket old = table.get(key);
        if (old == null) {
            return 0;
        }

        long remaining = WINDOW_MS - (now - old.start());
        if (remaining <= 0 || remaining > WINDOW_MS) {
            table.remove(key);
            return 0;
        }
        if (old.failures() < threshold) {
            return 0;
        }
        return Math.max(1, (remaining + 999) / 1_000);
    }

    synchronized long retryAfterSeconds(String username, String ip) {
        long now = nowMillis.getAsLong();
        return Math.max(
            waitFor(accounts, accountKey(username),
                    MAX_PER_ACCOUNT, now),
            waitFor(ips, ip, MAX_PER_IP, now)
        );
    }

    synchronized void failed(String username, String ip) {
        long now = nowMillis.getAsLong();
        increment(accounts, accountKey(username), now);
        increment(ips, ip, now);
    }

    synchronized void succeeded(String username) {
        // Do not erase signs of repeated failures from an IP.
        accounts.remove(accountKey(username));
    }

    synchronized void clearForTests() {
        accounts.clear();
        ips.clear();
    }
}

class LoginThrottleFilter extends OncePerRequestFilter {
    private final LoginAttemptLimiter limiter;

    LoginThrottleFilter(LoginAttemptLimiter limiter) {
        this.limiter = limiter;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest req) {
        return !("POST".equals(req.getMethod())
                && "/login".equals(req.getServletPath()));
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest req,
            HttpServletResponse res,
            FilterChain chain) throws ServletException, IOException {
        long seconds = limiter.retryAfterSeconds(
            req.getParameter("username"), req.getRemoteAddr()
        );
        if (seconds > 0) {
            res.setStatus(429);
            res.setHeader("Retry-After", Long.toString(seconds));
            res.setHeader("Cache-Control", "no-store");
            res.setContentType("text/plain;charset=UTF-8");
            res.getWriter().write("Please try again later");
            return;
        }
        chain.doFilter(req, res);
    }
}

@RestController
class DemoEndpoints {
    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }
}

@Configuration
class SecurityConfig {
    @Bean
    LoginAttemptLimiter loginAttemptLimiter() {
        return new LoginAttemptLimiter(System::currentTimeMillis);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice123"))
                .roles("USER").build(),
            User.withUsername("bob")
                .password(encoder.encode("bob123"))
                .roles("USER").build()
        );
    }

    @Bean
    SecurityFilterChain chain(HttpSecurity http,
                              LoginAttemptLimiter limiter)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .permitAll()
                .successHandler((req, res, authentication) -> {
                    limiter.succeeded(authentication.getName());
                    res.setStatus(200);
                    res.setHeader("Cache-Control", "no-store");
                    res.setContentType("text/plain;charset=UTF-8");
                    res.getWriter().write("Signed in");
                })
                .failureHandler((req, res, ex) -> {
                    limiter.failed(
                        req.getParameter("username"),
                        req.getRemoteAddr()
                    );
                    res.setStatus(401);
                    res.setHeader("Cache-Control", "no-store");
                    res.setContentType("text/plain;charset=UTF-8");
                    res.getWriter().write("Invalid credentials");
                })
            )
            .addFilterBefore(
                new LoginThrottleFilter(limiter),
                UsernamePasswordAuthenticationFilter.class
            );

        // Keep default CSRF for form login/session.
        return http.build();
    }
}
```

### 5.3. Why are these hook points right?

1. `LoginThrottleFilter` **is not declared as a `@Component` or separate `@Bean`**, preventing Spring Boot from also registering it outside the security filter chain. It is instantiated via `new` and added with `addFilterBefore` inside the chain.
2. `shouldNotFilter` restricts the filter to `POST /login`. Requests to `GET /public` or `GET /me` are not treated as password attempts.
3. Before password hashing, the limiter checks whether account/IP quota remains. Only after the provider verifies credentials are invalid does `failureHandler` increment counters; on valid login, `successHandler` resets only the account.
4. `synchronized` keeps map state consistent **within one JVM**, but does not synchronize across pods and does not solve the precheck/recordFailure race under parallel requests.
5. This demo keeps a key in the map until it is accessed again: it lacks proactive TTL eviction and cardinality guards, so **never deploy it directly to production**.
6. `getRemoteAddr()` does not trust client-supplied `X-Forwarded-For` directly. Behind a proxy, it may be the proxy's IP; configure trusted proxies to obtain the canonical client IP properly.
7. The demo form login explicitly returns **401** on bad credentials and **200** on success, whereas unauthenticated browsers hitting protected endpoints redirect **302**. If CSRF is missing, login POST returns **403** before checking passwords.

### 5.4. Testing with MockMvc and spring-security-test

Create `src/test/java/demo/loginthrottle/LoginThrottleIntegrationTest.java`:

```java
package demo.loginthrottle;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
    .content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
    .header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
    .status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginThrottleIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired LoginAttemptLimiter limiter;

    @BeforeEach
    void reset() {
        limiter.clearForTests();
    }

    private MockHttpServletRequestBuilder attempt(
            String name, String password, String ip) {
        return post("/login")
            .param("username", name)
            .param("password", password)
            .with(csrf())
            .with(req -> {
                req.setRemoteAddr(ip);
                return req;
            });
    }

    @Test
    void publicRequestIsAllowed() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void validCredentialsAreAccepted() throws Exception {
        mvc.perform(attempt("alice", "alice123", "192.0.2.8"))
            .andExpect(status().isOk())
            .andExpect(content().string("Signed in"));
    }

    @Test
    void badPasswordReturnsGeneric401() throws Exception {
        mvc.perform(attempt("alice", "wrong", "192.0.2.8"))
            .andExpect(status().isUnauthorized())
            .andExpect(content().string("Invalid credentials"));
    }

    @Test
    void unknownUsernameGetsSameGenericMessage()
            throws Exception {
        mvc.perform(attempt("not-existing", "wrong", "192.0.2.8"))
            .andExpect(status().isUnauthorized())
            .andExpect(content().string("Invalid credentials"));
    }

    @Test
    void accountIsLimitedEvenAfterClientChangesIp()
            throws Exception {
        for (int i = 0; i < 5; i++) {
            mvc.perform(attempt("alice", "wrong", "192.0.2.8"))
                .andExpect(status().isUnauthorized());
        }
        mvc.perform(attempt("alice", "alice123", "198.51.100.9"))
            .andExpect(status().isTooManyRequests())
            .andExpect(header().exists("Retry-After"));
    }

    @Test
    void distributedIpsStillHitSameAccountCounter()
            throws Exception {
        for (int i = 0; i < 5; i++) {
            mvc.perform(attempt(
                    "alice", "wrong", "198.51.100." + (i + 1)))
                .andExpect(status().isUnauthorized());
        }
        mvc.perform(attempt("alice", "alice123", "203.0.113.9"))
            .andExpect(status().isTooManyRequests());
    }

    @Test
    void sameIpAcrossManyAccountsIsLimited()
            throws Exception {
        for (int i = 0; i < 12; i++) {
            mvc.perform(attempt(
                    "unknown-" + i, "wrong", "203.0.113.8"))
                .andExpect(status().isUnauthorized());
        }
        mvc.perform(attempt("bob", "bob123", "203.0.113.8"))
            .andExpect(status().isTooManyRequests());
    }

    @Test
    void otherUserFromOtherIpCanStillLogin()
            throws Exception {
        for (int i = 0; i < 5; i++) {
            mvc.perform(attempt("alice", "wrong", "192.0.2.8"))
                .andExpect(status().isUnauthorized());
        }
        mvc.perform(attempt("bob", "bob123", "198.51.100.9"))
            .andExpect(status().isOk());
    }

    @Test
    void successfulLoginResetsAccountFailures()
            throws Exception {
        mvc.perform(attempt("alice", "wrong", "192.0.2.8"))
            .andExpect(status().isUnauthorized());
        mvc.perform(attempt("alice", "alice123", "198.51.100.8"))
            .andExpect(status().isOk());
        mvc.perform(attempt("alice", "wrong", "198.51.100.9"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void missingCsrfIsForbidden() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "alice123"))
            .andExpect(status().isForbidden());
    }
}
```

**Explanation:** never use `@WithMockUser` to test passwords because that annotation injects a fake authentication. Test requests traverse the real form filter/provider and CSRF. Account-lock tests verify from **another IP**, IP-lock tests use **different usernames**, unknown-user tests assert the same generic message, and CSRF has its own test. IP addresses come from documentation ranges (RFC 5737).

### 5.5. Testing TTL without sleep

Create `src/test/java/demo/loginthrottle/LoginAttemptLimiterTest.java`:

```java
package demo.loginthrottle;

import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class LoginAttemptLimiterTest {
    @Test
    void fiveMinuteWindowExpires() {
        AtomicLong millis = new AtomicLong(1_000L);
        LoginAttemptLimiter limiter =
            new LoginAttemptLimiter(millis::get);

        for (int i = 0; i < 5; i++) {
            limiter.failed("alice", "192.0.2.8");
        }
        assertThat(limiter.retryAfterSeconds(
            "alice", "198.51.100.9")).isPositive();

        millis.addAndGet(5 * 60_000L);
        assertThat(limiter.retryAfterSeconds(
            "alice", "198.51.100.9")).isZero();
    }
}
```

The test uses a controllable clock instead of waiting 5 real minutes; results are deterministic across CI runs. Production must account for clock drift and exact Redis TTL semantics.

### 5.6. Running and observing

If using Gradle Wrapper:

```bash
./gradlew test
./gradlew bootRun
```

Windows: `gradlew.bat test` and `gradlew.bat bootRun`. Without a wrapper, use `gradle test` and `gradle bootRun` with a compatible Gradle 8.x installation.

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
```

`GET /public` returns 200 with body `public`; unauthenticated `GET /me` typically redirects to the login form. Do not run `curl -d username=...` without CSRF and assume the password was wrong: Spring Security returns **403 CSRF** before running the provider. The MockMvc tests supply valid CSRF tokens to verify 401/429 and 200 logins accurately.

## 6. Scaling up to Redis and multiple instances

### 6.1. Why per-pod RAM is insufficient

With 4 pods each keeping local counters, a bot distributing requests via a load balancer multiplies the account's quota. Even on a single pod, `retryAfterSeconds()` and `failed()` are two separate steps: concurrent requests can pass precheck before failures are recorded. `synchronized` cannot protect a whole cluster nor turn two separate steps into one atomic admission reservation.

### 6.2. Atomic admission and failure counters

A production design should separate:

- **Request admission counter/token bucket:** atomic check + quota reservation **before password hashing**; caps concurrency and burst.
- **Failure counter:** atomically incremented after authentication failure; account and IP rules carry windows/TTLs.
- **MFA/risk signals:** separate counters for OTP/reset, anomalous successful logins, and challenges.
- **TTL/cardinality:** every account/IP key has expiration, max key bounds, and state cleanup; never keep millions of random usernames forever.

Illustrative key patterns:

```text
auth:fail:account:<HMAC(normalized-identifier)>
auth:fail:ip:<canonical-ip-or-prefix>
auth:admission:route:<route-id>:<time-bucket>
```

Use HMAC with a server-side key to avoid exposing raw usernames/emails in Redis keys and logs, while still protecting Redis and rotating keys. With Redis Cluster, multi-key atomic Lua scripts must ensure keys share a hash slot or use a compatible split design.

Pseudo-logic (**not standalone runnable Lua**):

```text
function atomicFailureIncrement(key, ttlSeconds):
    n = INCR(key)
    if n == 1: EXPIRE(key, ttlSeconds)
    return n

function atomicAdmit(keys, requestedCost):
    if any quota would be exceeded: return DENY + retryAfter
    reserve all required quotas atomically
    return ALLOW
```

Use Redis Lua/transactions so `INCR` and `EXPIRE` are never split; strict admission quotas require atomic reservation. Sliding windows can use sorted sets with atomic pruning/counting/adding; token buckets smooth bursts better than fixed windows (fixed windows allow double bursts across boundary edges). Choose algorithms per traffic profile and SLO, and never deploy an untested Lua script without concurrency/cluster load tests.

### 6.3. Redis outage: fail-open or fail-closed?

There is no universal answer. Fail-open prioritizes availability at the cost of weakened protection; fail-closed blocks legitimate users when the store is down; degraded mode can apply gateway/per-instance limits, circuit breakers, alerts, and risk controls. Document the policy per endpoint type and threat model, test Redis timeouts/failover, and prevent retry storms. For high-risk login services, coordinate MFA/IdP and recovery procedures when rate limits cannot be verified.

## 7. Trusted client IP behind reverse proxy/WAF

An app behind Nginx/Envoy/CDN may see only the proxy IP in `request.getRemoteAddr()`. Limiting by that IP can lump **all users** into one shared quota. Conversely, reading `X-Forwarded-For` directly from Internet clients lets attackers spoof IPs and bypass limits.

Implementation steps:

1. Allow only **trusted proxies** to write/normalize forwarded headers after verifying the connection source. Proxies must strip or overwrite untrusted client headers.
2. Firewalls, private networks, mTLS, or allowlists block direct access to origin/app bypassing the WAF.
3. Define the trusted hop chain and canonical client IP; edge and app use the exact same definition for correlation.
4. Use `ForwardedHeaderFilter` or `server.forward-headers-strategy` only after securing the trust boundary; they do not verify header trustworthiness themselves.
5. Test that spoofed headers from the Internet **do not alter the IP** used by the limiter, and real users via the gateway are not collapsed into the proxy's IP.
6. Account for IPv6 privacy addresses, mobile carriers, corporate VPNs, and NAT when tuning single-IP limits to curb false positives.

## 8. WAF/gateway policies by path and method

Do not protect only `POST /login`. The authentication surface includes:

- Username/password login on web, API, and mobile.
- MFA/OTP challenges, OTP/email resends.
- Forgot password and password reset.
- Magic-link/passwordless login.
- Account registration and activation.
- Token/refresh and device authorization polling.
- SSO/OIDC callbacks/session management (while main password guessing targets the IdP).

Each endpoint has different semantics. Password login checks account/IP; OTP needs per-challenge/session/account quotas; resends need anti-spam quotas; refresh tokens need replay detection and token rotation; reset endpoints need generic messages.

**Do not rate-limit every URL with one fixed threshold.** An overly tight global edge limit can lock out all customers during peak traffic. Consider monitor-only/shadow mode first, measure baselines, start with soft challenges, and ramp up blocking based on data.

**Protect before burning CPU:** bcrypt/argon2 are intentionally expensive; WAF/gateway filtering sheds raw floods and an admission limiter ahead of the password provider saves CPU, while the app still enforces account-aware rules against IP-rotating bots.

## 9. Account lockout, MFA, and UX

A "5 wrong tries permanently locks the account" policy creates a DoS vector: anyone knowing a victim's email just sends 5 wrong passwords. Even a 24-hour lock can disrupt legitimate use. Therefore:

- Prefer short cooldowns, capped progressive backoff, challenges/step-up MFA, and monitoring.
- Enable MFA/passkeys on sensitive accounts to limit damage from leaked passwords.
- Return generic messages on login failure; never disclose locked/disabled status in public responses.
- Protect account recovery itself; password reset/MFA must not become an abusable bypass.
- Avoid resetting IP/global counters when one user succeeds; retain risk state to catch password spraying.
- Support verified recovery with auditing; avoid unmonitored permanent bypasses.

CAPTCHA is only defense-in-depth: bots can solve or outsource CAPTCHAs. Never replace rate limiting, MFA, or risk detection with CAPTCHA alone.

## 10. Logs, metrics, and alerting

Useful metrics:

| Metric/event name | Meaning | Avoid |
| --- | --- | --- |
| `login_attempt_total` by route/client | Total attempt requests. | Raw passwords/usernames in labels. |
| `login_failures_total` by normalized reason | Bad credentials, disabled, internal MFA failure. | Exposing specific reasons in public responses. |
| `login_throttled_total` by rule | Tracks app/edge quotas and false positives. | Double-counting the same event without correlation. |
| `login_success_total` | Success rate and anomalous spikes. | Wiping all risk state on success. |
| `limiter_storage_errors_total` | Redis outages, timeouts, failovers. | Infinite retries flooding Redis. |
| Distinct IP/account count in window | Credential stuffing and password spraying. | Retaining raw PII long-term or high-cardinality labels. |

Logs use request IDs to correlate edge/gateway/app/IdP without recording raw session cookies, tokens, passwords, OTPs, or recovery codes. Identifiers may be pseudonymized/HMACed with a secure key per privacy policy. Restrict retention and access.

**Signals:** one account targeted from many IPs; one IP trying many accounts; many accounts across many IPs with high failure rates; anomalous login success after failure bursts; or rising 429s alongside support tickets (false positives). Maintain a runbook: enable WAF rules, check compromised accounts, require MFA, revoke sessions, notify via proper channels, and roll back rules if real customers are harmed.

## 11. End-to-end testing, not just unit tests

Checklist from app to infrastructure:

1. **Account across IPs:** targeting the same user from multiple IPs still hits rate limits.
2. **IP across users:** trying many usernames from one IP is blocked appropriately.
3. **Unknown users:** responses never leak existence, and unknown accounts are counted.
4. **Concurrency:** parallel `POST /login` requests cannot exceed the designed strict admission quota.
5. **Multi-pod:** requests hitting pods A/B/C share one distributed counter.
6. **TTL:** counters expire properly, and reset/eviction prevents unbounded memory growth.
7. **IP spoofing:** client-supplied `X-Forwarded-For` cannot bypass quotas.
8. **NAT/shared IP:** real users behind mobile/corporate proxies are not unfairly locked out.
9. **CSRF:** cookie login POST without a CSRF token is rejected; with a token, password and quota still run.
10. **IdP:** OIDC/SAML logins verify anti-brute-force at the IdP, MFA, and security event integration.
11. **Failure modes:** Redis/WAF outages, retry storms, backpressure, and fallback match the runbook.
12. **Telemetry:** alerts carry request correlation; metrics leak no secrets.
13. **Alternate paths:** OTP, reset, registration, magic link, refresh token, and legacy login URLs are all inventoried.
14. **Post-login data protection:** roles/scopes do not replace object ownership or tenant authorization.

**Two-way testing:** testing only 429 can mask a `denyAll()` misconfiguration; testing only 200 login can mask `permitAll()`. Verify valid logins, wrong passwords, limit reached, unaffected other users, and post-login resource permissions.

### 11.1. Controlled policy rollout

Deploy in monitor-only mode if supported, measure baselines across peak hours, tenants/ASNs, mobile networks, and corporate NAT. Start with soft challenges and generous limits, then tighten hard blocks based on false-positive rates, CPU load, credential-stuffing signals, and support feedback. Assign an owner/on-call and rollback procedure, and never change thresholds mid-incident without auditing.

## 12. Common deployment mistakes

| Mistake | Harm | Proper fix |
| --- | --- | --- |
| Rate-limiting only by IP. | Bots rotate IPs; NAT causes collateral lockouts. | Account + IP + network/risk. |
| Hard-locking accounts only. | Attackers lock victims out. | Adaptive delays/step-up and recovery. |
| Per-pod RAM counters. | Quota multiplies by pod count. | Redis shared state / edge limits. |
| Separate `GET` then `INCR`. | Races under parallel requests. | Atomic reservation + TTL. |
| Trusting client-sent `X-Forwarded-For`. | IP spoofing and quota bypass. | Trusted proxy + block origin bypass. |
| Limiting only after password hashing. | CPU DoS still succeeds. | Pre-hash admission check + edge limits. |
| No TTL or key cleanup. | Memory/cardinality exhaustion. | Bounded keys, TTL, eviction. |
| Returning 404 for unknown users. | Username enumeration. | Generic responses & timing mitigation. |
| Resetting all IP counters on valid login. | Attackers wipe spraying history. | Selective resets only. |
| Disabling CSRF so login POST succeeds. | CSRF risk on browser cookies. | Flow-appropriate token handling. |
| WAF only, no app/IdP policy. | Misses per-account credential guessing. | Layered defense and telemetry. |
| Ignoring Redis outages. | Login outage or unexpected fail-open. | Degraded mode/runbook. |
| Forgetting reset/OTP endpoints. | Attackers shift vectors. | Protect the entire auth surface. |
| Logging passwords, tokens, or raw PII. | Secret leakage and privacy risk. | Redaction, access control, retention. |

## 13. Self-check exercises

**A.** WAF caps at 20 POST/min/IP, but an attacker tries one user from 500 IPs, 2 tries per IP.  
**Answer:** IP limiting alone fails; add per-account rate detection, risk/MFA, and aggregated telemetry.

**B.** Login limits live in each Spring Boot pod, autoscaling from 2 to 8 pods.  
**Answer:** Per-account quota multiplies by pod count; use a distributed limiter/edge limits and verify atomicity.

**C.** Users are locked out for 24 hours after 5 failures; an attacker knows the victim's email.  
**Answer:** Enables victim DoS. Prefer short cooldowns, step-up challenges, and safe recovery.

**D.** An API reads `X-Forwarded-For` from any request and treats it as the client IP.  
**Answer:** The header can be spoofed; trust headers only behind a normalizing trusted reverse proxy and lock down direct origin access.

**E.** A POST login without CSRF returns 403; a developer concludes the account was throttled.  
**Answer:** Insufficient evidence; the CSRF filter can reject before the login provider runs. Test with a valid CSRF token and check for exact 401/429 responses.

**F.** Non-existent usernames return "no such user", while real users with wrong passwords get "wrong password".  
**Answer:** Username enumeration. Use uniform messages and monitor timing/status parity.

**G.** One IP probes many users, then succeeds on an attacker-controlled account. All IP quotas reset.  
**Answer:** That is a bypass. Preserve IP/network risk counters or reset selectively per policy.

**H.** Spring OAuth2 Login uses an external IdP; the app throttles `POST /login` without managing the IdP.  
**Answer:** Does not protect against brute force at the IdP. Verify password/MFA protections at the IdP and protect callbacks/sessions in the app.

**I.** Redis goes down and the app has no fallback policy.  
**Answer:** Missing operational design: decide fail-open/closed/degraded per risk, paired with gateway controls and alerts.

**J.** A JWT Resource Server API accepts Bearer tokens, yet a developer throttles `POST /login` to stop token guessing.  
**Answer:** Protect the actual authorization/token endpoints and Bearer API per their semantics; a local login form does not protect tokens or the IdP.

## 14. Production checklist

- [ ] Inventoried login, OTP/MFA, reset, magic link, registration, refresh, and IdP endpoints.
- [ ] Threat model covers brute force, spraying, stuffing, enumeration, CPU DoS, and lock-out DoS.
- [ ] Multiple keys (account/IP/network/risk) used rather than a single address.
- [ ] Early request admission runs before password hashing; distributed atomic quotas across multiple pods.
- [ ] Counters have TTL, eviction, and bounded cardinality; unknown users follow the same policy.
- [ ] Canonical client IP comes from trusted proxies; origin bypass is blocked.
- [ ] Generic errors, minimized timing differences, and consistent `Retry-After`.
- [ ] Lockouts avoid rigidity; MFA/passkeys, step-up, and recovery are in place.
- [ ] Browser forms/sessions preserve CSRF and cookie security.
- [ ] WAF, gateway, app, and IdP have clear policy owners and concrete routes.
- [ ] Metrics/alerts track rule/layer without secrets or raw PII labels.
- [ ] Tested multi-IP, multi-user, multi-pod, concurrency, TTL, IP spoofing, and Redis failure.
- [ ] False-positive measurement, shadow rollout, incident response, and rollback plan exist.

## 15. Takeaways and official documentation

**Deployment formula:** WAF/gateway sheds floods; Spring Security/IdP distinguishes password attempts and account privileges; a distributed store enforces consistent limits across instances; monitoring catches distributed attacks and impacted real users. No single CAPTCHA, account lock, or IP rate limit replaces defense in depth. MFA/passkeys, password hygiene, and safe recovery are essential companions to throttling.

Reference documentation:

- [OWASP Authentication Cheat Sheet — Login Throttling, Lockout, Enumeration](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Credential Stuffing Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html)
- [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
- [OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html)
- [Spring Security — Password/Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Servlet Filter Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Testing MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/)
- [Redis — INCR Command and Rate Limiting Pattern](https://redis.io/docs/latest/commands/incr/)
