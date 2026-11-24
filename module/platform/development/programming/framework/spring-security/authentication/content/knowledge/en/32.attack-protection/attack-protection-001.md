# Brute force, password spraying, and credential stuffing: detection and defense in Spring Security

## 1. Objectives

Attacks against **password-based login endpoints** do not necessarily exploit cryptographic flaws. They take advantage of systems that allow repeated credential attempts, users choosing weak passwords, or users reusing passwords leaked from other services.

Three common patterns:
- **Brute force / password guessing:** trying many passwords against a single account or a small set of accounts.
- **Password spraying:** trying one or a few common passwords across **many accounts**, typically at a low rate per account to avoid per-account lockout.
- **Credential stuffing:** trying **username/password pairs leaked from another breach**, exploiting password reuse habits. This is not necessarily guessing new passwords.

The three patterns differ in distribution, targets, and detection signals. The shared defense principle is **not trusting that a single IP limit or a single account lockout is enough**.

After this lesson, you will be able to classify the three attack patterns, read signals in login data, design multi-dimensional rate limits, understand the pros/cons of account lockout, combine MFA/passkeys, configure Spring Security Servlet, and build a test suite without attacking real systems.

> **Scope:** this lesson focuses on defending applications that own a username/password authentication endpoint, such as `POST /login`. With OAuth2/OIDC SSO, passwords are verified at the identity provider (IdP), so anti-password-guessing policies must be enforced primarily at the IdP, while the application still protects callbacks/sessions and monitors anomalies. Do not treat demo code as a production WAF or anti-bot system.

## 2. Accurately distinguishing the three attack patterns

### 2.1. Brute force: many password candidates for the same account

Example **hypothetical** aggregated log, without showing actual passwords:

~~~text
10:00 user=alice source=A result=FAIL
10:01 user=alice source=A result=FAIL
10:02 user=alice source=A result=FAIL
10:03 user=alice source=A result=FAIL
10:04 user=alice source=A result=FAIL
~~~

Here one account suffers many failures in a short period. The attack may use a password dictionary, variations of common passwords, or multiple IP sources. If the system only blocks a single source IP, the attacker can switch IPs and continue targeting the same account.

**Defense signals:** attempts per account, failure rate, velocity, and source changes; not just attempts per single IP.

### 2.2. Password spraying: a few passwords across many accounts

Hypothetical log example:

~~~text
10:00 user=alice source=B result=FAIL
10:01 user=bob   source=B result=FAIL
10:02 user=carol source=B result=FAIL
10:03 user=dave  source=B result=FAIL
10:04 user=erin  source=B result=FAIL
~~~

Each account only has one failure, but one source is touching **many different accounts**. If the attacker distributes requests across proxies, each IP may also have few requests. A "5 failures per account then lock" limit may **fail to detect spraying early**, because no single username has crossed the threshold.

**Defense signals:** number of distinct accounts attempted per source/IP pool/ASN/device/browser signal and time windows; detecting *campaigns* system-wide, rather than looking only at individual accounts.

### 2.3. Credential stuffing: credential pairs from another data breach

Hypothetical example:

~~~text
10:00 account=alice source=C result=FAIL
10:01 account=bob   source=C result=SUCCESS
10:02 account=carol source=D result=FAIL
10:03 account=dave  source=D result=SUCCESS
~~~

Each account may only be tried with **one leaked pair**. The login success rate can be noticeable; afterward, unusual behavior often appears in the new session such as changing email, changing password, downloading data, or creating tokens.

**Defense signals:** login volume across many accounts, successes from unusual devices/IPs, leaked credential pairs (based on safe checking mechanisms), post-login behavior, and MFA outcomes. Do not log passwords to "detect identical passwords".

### 2.4. Comparison table

| Criterion | Brute force | Password spraying | Credential stuffing |
|---|---|---|---|
| Input | Many password candidates | One/a few common passwords | Many leaked username/password pairs |
| Distribution across accounts | Usually concentrated | Broad, few attempts per account | Broad, possibly only one attempt per account |
| Per-account limit | Strong effect | May be hard to notice | May not block the first attempt |
| Per-IP limit | Useful if IP-concentrated | Useful if not distributed | Easily bypassed with distributed proxies |
| MFA/passkey | Reduces takeover risk | Reduces takeover risk | Especially critical when passwords are reused |
| Required observability | Account velocity | Distinct accounts per source/campaign | Credential reuse signals + successful anomalies |
| Secondary risk | False account lockouts / DoS | Mass lockouts if policy is rigid | Account takeover using valid passwords |

**Do not classify with certainty from a single log line.** A cluster of failures across many accounts could be spraying or unsuccessful stuffing. Historical and behavioral signals are needed; do not infer passwords from logs.

## 3. Impact on the system and users

Consequences go beyond "finding the password":
1. **Account takeover (ATO):** the attacker logs into accounts whose passwords are guessed or match leaked data.
2. **Data exposure or unauthorized transactions:** grabbing tokens, downloading reports, changing addresses/emails, or creating API keys within the account's permissions.
3. **Denial of service via account lockout:** an overly rigid lockout mechanism can turn spraying into a tool for locking thousands of legitimate users.
4. **Increased infrastructure load:** proper password hashing (bcrypt/Argon2id/PBKDF2) is resource-intensive; mass requests can exhaust CPU/DB pools.
5. **User enumeration:** differing HTTP statuses, messages, or processing times between "user does not exist" and "wrong password" can help build an account list.
6. **Operational noise:** millions of login failures trigger false alerts, increase log/storage costs, and make it harder to spot anomalous successes.

If an attacker gets past the password but still has to pass MFA, a **correct password with failed MFA** event is worth close attention. Risk-based alerts should be in place, ensuring credentials or private information are not disclosed to unauthorized parties.

## 4. Multi-layered defense model

A functional diagram:

~~~text
Internet / browser
        |
        v
Edge / gateway / WAF
    - TLS, IP/ASN reputation, burst rate limit
    - bot mitigation when needed
        |
        v
Spring Security login entry point
    - CSRF for browser login
    - per-account + per-source attempt limiter
    - consistent username canonicalization
        |
        v
AuthenticationManager / PasswordEncoder
    - passwords stored with appropriate hash
    - generic authentication failures
        |
        v
Risk decision + MFA / passkey
    - step-up for sensitive situations
    - do not trust self-reported client device/headers
        |
        v
Session / authorization
    - rotate session after login
    - check permissions and account status
        |
        v
Audit/metrics/incident response
    - failure/success/lockout/rate limited
    - suspicious-success monitoring
~~~

Each layer serves a distinct purpose. **The WAF does not fully know account state**; Spring Security does not have full visibility into the entire ASN/proxy landscape; DB transactions do not replace anti-bot; CAPTCHA does not replace MFA.

### 4.1. Policy enforcement points

- `POST /login` and other password authentication APIs.
- Mobile/API endpoints that may have separate JSON forms.
- Admin login, VPN/SSO, IdP if that is where passwords are verified.
- Password change, forgot password, OTP/recovery, and session/token issuance flows when vulnerable to automation.
- Fallback paths (HTTP Basic, legacy endpoints, test accounts) must not bypass the limiter.
- Logged-in APIs must still check authorization: blocking login attacks does not fix BOLA/IDOR flaws.

## 5. Rate limiting: do not lock into a single dimension

### 5.1. Two independent buckets: account and source

An effective configuration usually sets **two separate conditions**:
- **Per account:** limits attempts against one user identifier, **regardless of IP**. Mitigates distributed brute force.
- **Per source:** limits how many times one source can try **many accounts**, regardless of username. Mitigates concentrated spraying/stuffing.

~~~text
request(username = alice, source = 203.0.113.8)
                  |
                  +--> ACCOUNT bucket "alice"
                  |
                  +--> SOURCE bucket "203.0.113.8"
                  |
                  +--> BOTH allow? → continue checking password
                        any bucket exceeds threshold → throttle
~~~

**Very common mistake:** using only a single composite rate-limit key `IP:username`. One IP can try many usernames; each combination gets its own quota so total requests become huge. Similarly, an IP-distributed botnet can try the same account from many IPs. The two buckets **do not replace each other**.

### 5.2. A third bucket for campaigns

For distributed attacks, there should be aggregate detection:
- `distinct_account_count` by source/ASN/cluster across short and long windows;
- number of new source-account pairs, especially from proxy or cloud infrastructure;
- 401/403/429 rates and login successes from never-before-seen devices;
- spikes in captcha/MFA failures;
- anomalous token/session activity after a password success.

Do not blindly trust client-supplied `User-Agent`, `X-Device-ID`, `X-Forwarded-For`; they can be spoofed. Data from trusted proxies and multi-dimensional correlation are more valuable than a single field.

### 5.3. Sliding window and token bucket

| Algorithm | How it works | Pros/cons |
|---|---|---|
| Fixed window | Counts requests within fixed intervals | Easy to implement, but bursts occur at window boundaries |
| Sliding window log/counter | Counts within a sliding interval | More accurate, higher storage/query cost |
| Token bucket | Has burst capacity and refill rate | Balances burst threshold and average rate |
| Leaky bucket | Smooths traffic or queues requests | Useful for rate smoothing, requires backpressure |
| Progressive delay | Increases delay based on risk/failure count | Avoids hard locks, but can hold threads if misimplemented |

**Reference example**, not a universal standard for every system: an account gets 5 burst attempts and refills 1 attempt/minute; a source might get 20 burst attempts and refill 1 attempt/3 seconds. Production chooses based on traffic and risk model; must measure false positives, logins from corporate networks sharing an IP, IPv6/proxies, and lockout DoS risk.

### 5.4. Rate limits must be consistent across replicas

An in-memory `ConcurrentHashMap` **does not share data** across instances. In production use Redis/DB/gateway with atomic operations (Lua scripts, transactions, platform token buckets) and TTL/quotas; distinguish:
- updating buckets atomically so two concurrent requests cannot exceed the threshold;
- expiring state to avoid memory exhaustion;
- failure mode when Redis/gateway fails: fail-safe/step-up/stricter limit per policy, never silently turning all logins into unlimited;
- checking clock skew across nodes;
- if two buckets are decremented separately, one bucket can be consumed even when the other bucket rejects. That is acceptable conservative behavior if explicitly defined; if all-or-nothing is desired, an atomic multi-key policy is needed.

## 6. Account lockout: balancing guessing prevention and DoS avoidance

**Account lockout** stops or delays authentication after a number of failures. NIST SP 800-63B-4 specifies an upper limit on consecutive failed authentication attempts for an authenticator in its compliance context; **that maximum number is not a recommended threshold to copy verbatim for every app**.

Design factors:
- *threshold*: number of failures before throttling/locking;
- *observation window*: observation period, e.g., 15 minutes;
- *lock duration*: delay or temporary lock duration;
- *reset semantics*: how successful login, recovery, or admin reset affects counters;
- *scope*: by account, credential, source, and/or risk policy.

**Drawback:** if a hard lock happens merely because an attacker sends wrong passwords, an adversary can intentionally lock out victims' accounts. Therefore:
- prefer progressive delay, risk-based challenges, or step-up before a long hard lock;
- do not reveal that an account exists when returning "locked" to unauthenticated callers;
- do not allow CAPTCHA to be bypassed via another API client;
- provide secure self-service recovery and auditing;
- admins/integration partners should have appropriate policies without being exempt from monitoring.

If a legitimate user is throttled, the UI can show a generic message like "Too many requests, please try again later" without revealing exact thresholds or internal risk reasons. Do not display a hyper-precise countdown timer that helps bots optimize retry schedules.

## 7. MFA, passkeys, and preventing credential reuse

### 7.1. What weakness does MFA solve?

MFA requires an additional independent factor after the password. With credential stuffing, the password may be **correct** because it was leaked elsewhere; MFA can block login if the attacker does not hold the second factor. However:
- SMS/OTP MFA can be phished or bypassed via recovery-flow attacks.
- Push approval carries "MFA fatigue" risk; requires spam protection and number matching if used.
- TOTP is better than password-only, but can be bypassed by real-time phishing proxies.
- **FIDO2/WebAuthn passkeys** bind assertions to the RP ID/origin, offering stronger phishing resistance than passwords/OTP; enrollment, recovery, and sessions still require protection.
- If the system has weak recovery, attackers can route around MFA.

### 7.2. Password policy and breached-password screening

- Accept sufficiently long passwords/passphrases, without forcing arbitrary complexity rules that lead to predictable password reuse.
- Screen new/changed passwords against breached or overly common password sets via privacy-preserving services or trusted lists; **never send raw passwords to untrusted APIs**.
- Store passwords using an appropriate password hashing algorithm with a work factor such as Argon2id/bcrypt/PBKDF2, not raw SHA-256 or reversible encryption.
- Do not force arbitrary periodic password changes without signs of compromise per policy; when a password is confirmed compromised, require a change and revoke related sessions/tokens.
- Users using password managers to generate unique passwords per service reduce credential stuffing risk.

### 7.3. Post-login detection

A `SUCCESS` login does not prove safety if credentials were leaked. For logins from new devices/locations, the application can:
- require MFA/step-up before changing email, changing password, adding API keys, or making payments;
- send anomalous-login alerts to verified contacts;
- display login/session history to users with the ability to revoke sessions;
- check for anomalous behavior and apply transaction limits.

Be careful to avoid excessive notifications on wrong passwords: attackers can turn that into spam or train users to ignore critical alerts.

## 8. Error messages and preventing user enumeration

If the UI returns different messages:
- "Account alice does not exist";
- "Wrong password for alice";
- "Account alice is locked";

then it leaks account status to unauthenticated callers. Differences in **HTTP status, processing time, and redirects** can also act as leak channels.

Rules:
- on failed login, return a generic message like **"Invalid credentials"**;
- avoid returning whether a user ID exists;
- form login redirects can go to `/login?error`, without attaching a specific reason in the URL;
- when rate limited, `429 Too Many Requests` can be used with a generic message; do not disclose which bucket was exceeded or remaining attempts;
- if performing dummy password hashing to reduce timing enumeration, measure effectiveness and CPU cost; do not make it easy for attackers to force infinite server hashing;
- check all login/forgot-password/signup paths to avoid differing discrepancies.

Credential errors and rate-limit errors do not necessarily need the same status code, but **never turn the difference into a way to probe account existence**.

## 9. Spring Security Servlet architecture

In Spring Security 6.x, `UsernamePasswordAuthenticationFilter` accepts form POST logins and uses `AuthenticationManager` / `AuthenticationProvider` to verify username and password.

~~~text
POST /login (username/password + CSRF)
        |
        v
Spring Security filter chain
   - CSRF / session context handling
   - custom LoginThrottleFilter
        |  account bucket AND source bucket?
        |    NO → 429, stop before password hashing
        |    YES
        v
UsernamePasswordAuthenticationFilter
        |
        v
AuthenticationManager / ProviderManager
        |
        v
DaoAuthenticationProvider + UserDetailsService + PasswordEncoder
        |
        +---- FAIL → AuthenticationFailureHandler / auth events
        |
        +---- SUCCESS → AuthenticationSuccessHandler / session
        v
Protected endpoints + security logging/metrics
~~~

**Layer responsibilities:**
- `OncePerRequestFilter`: can be used to rate-limit requests **before** password verification.
- `AuthenticationFailureHandler`: handles failed login results, does not replace a pre-auth limiter; if a request is blocked earlier by a filter, the failure handler is not called.
- `AuthenticationSuccessHandler`: handles routing/post-processing after successful login; does not automatically bypass session/CSRF protection.
- `AuthenticationEventPublisher` + `@EventListener`: publishes/receives authentication events for monitoring when configured properly.
- `DaoAuthenticationProvider`: uses `UserDetailsService` and `PasswordEncoder`; no custom plain-string password comparison needed.
- `SecurityContext`: only holds the authenticated principal/authorities after successful authentication; the limiter does not create authentication.

**Important:** Spring Security does not automatically provide a complete anti-credential-stuffing policy just because `formLogin()` is enabled. Rate-limit/risk/MFA decisions and signal collection must be integrated separately or through an IdP/gateway.

## 10. Spring Boot 3.x + Spring Security 6.x + Java 17 example

The following sample is a **defensive demo** that does not perform automated password guessing. Each `POST /login` request is evaluated against two independent token buckets: by username and by source IP. When either runs out of quota, the filter returns 429 before `UsernamePasswordAuthenticationFilter` checks the password. Every request is counted, not just failed attempts; thus the sample limits overall rate, suitable for demonstrating pre-auth throttling.

**Demo limitations:** buckets live in RAM, are not shared across a cluster, do not auto-evict keys, and do not replace distributed spraying/stuffing detection tools. Production requires a Redis/gateway limiter with atomic quotas, eviction/TTL, identity normalization, and multi-dimensional correlation. Numeric thresholds are illustrative only.

### 10.1. Project structure

~~~text
login-defense-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/logindefense/
    │   │   ├── LoginDefenseApplication.java
    │   │   ├── LoginAttemptGuard.java
    │   │   ├── LoginThrottleFilter.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── ProfileController.java
    │   └── resources/application.yml
    └── test/java/com/example/logindefense/
        └── LoginAttemptGuardTest.java
~~~

### 10.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>login-defense-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The project uses `spring-boot-starter-security` and Spring's standard password encoder. Do not use raw SHA-256 or plaintext password comparison.

### 10.3. `application.yml`

~~~yaml
server:
  port: 8080

demo:
  user:
    password: ${DEMO_USER_PASSWORD}
~~~

When running, provide `DEMO_USER_PASSWORD` from an environment variable. The local demo only creates the `alice` account; do not use test credentials in production and do not print passwords to logs.

### 10.4. `LoginDefenseApplication.java`

~~~java
package com.example.logindefense;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoginDefenseApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginDefenseApplication.class, args);
    }
}
~~~

### 10.5. `LoginAttemptGuard.java`: two independent token buckets

~~~java
package com.example.logindefense;

import java.util.Locale;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Component;

@Component
public final class LoginAttemptGuard {

    private final ConcurrentMap<String, TokenBucket> byAccount =
            new ConcurrentHashMap<>();
    private final ConcurrentMap<String, TokenBucket> bySource =
            new ConcurrentHashMap<>();

    public boolean allow(String submittedUsername, String remoteAddress) {
        if (submittedUsername == null || remoteAddress == null) {
            return false;
        }

        String account = submittedUsername.trim()
                .toLowerCase(Locale.ROOT);

        if (account.isBlank() || account.length() > 150) {
            return false;
        }

        // Source bucket: burst 20, refill 1 request / 3 seconds.
        TokenBucket sourceBucket = bySource.computeIfAbsent(
                remoteAddress, key -> new TokenBucket(20, 1.0 / 3.0));

        // Account bucket: burst 5, refill 1 request / 60 seconds.
        TokenBucket accountBucket = byAccount.computeIfAbsent(
                account, key -> new TokenBucket(5, 1.0 / 60.0));

        // Two INDEPENDENT checks: never use one "IP:username" key.
        boolean sourceAllowed = sourceBucket.take();
        boolean accountAllowed = accountBucket.take();
        return sourceAllowed && accountAllowed;
    }

    static final class TokenBucket {
        private final double capacity;
        private final double refillPerSecond;
        private double tokens;
        private long lastNanos;

        TokenBucket(int capacity, double refillPerSecond) {
            this.capacity = capacity;
            this.refillPerSecond = refillPerSecond;
            this.tokens = capacity;
            this.lastNanos = System.nanoTime();
        }

        synchronized boolean take() {
            long now = System.nanoTime();
            long elapsedNanos = Math.max(0L, now - lastNanos);
            double elapsedSeconds = elapsedNanos / 1_000_000_000.0;
            tokens = Math.min(
                    capacity, tokens + elapsedSeconds * refillPerSecond);
            lastNanos = now;

            if (tokens < 1.0) {
                return false;
            }
            tokens -= 1.0;
            return true;
        }
    }
}
~~~

**Analysis:**
- `byAccount` protects a single user from distributed IP sources; `bySource` protects the system from a single source trying mass usernames.
- `synchronized take()` makes token updates **atomic within one JVM for a single bucket**; there is no atomicity across replicas.
- Decrementing the two buckets is not grouped in a single transaction; if the account bucket rejects, the source bucket can still be decremented, making the policy more conservative. Real applications must clearly define semantics and consider atomic multi-key logic.
- The thresholds 5 and 20 here are for learning about bursts; **they are not default limits mandated by Spring Security or NIST**.
- `toLowerCase(Locale.ROOT)` is only an example normalization for the demo username. For real usernames/emails, normalization must match **the exact lookup policy in UserDetailsService**, without blindly stripping dots or `+` from emails.
- The map will grow unbounded if an attacker sends endless usernames/IPs. Production requires expiration/maximum size and quotas at the edge layer to prevent memory DoS.
- The source key is taken from the actual connection to the application. When the backend sits behind a proxy, do not trust client-sent `X-Forwarded-For`; use trusted proxy configuration or enforce limits at the gateway.

### 10.6. `LoginThrottleFilter.java`

~~~java
package com.example.logindefense;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

public final class LoginThrottleFilter extends OncePerRequestFilter {

    private final LoginAttemptGuard guard;

    public LoginThrottleFilter(LoginAttemptGuard guard) {
        this.guard = guard;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        boolean loginPost = "POST".equalsIgnoreCase(
                request.getMethod())
                && "/login".equals(request.getServletPath());

        if (!loginPost) {
            chain.doFilter(request, response);
            return;
        }

        String username = request.getParameter("username");
        String source = request.getRemoteAddr();

        if (!guard.allow(username, source)) {
            response.setStatus(429);
            response.setHeader("Cache-Control", "no-store");
            response.setContentType("text/plain;charset=UTF-8");
            response.getWriter().write(
                    "Too many requests. Please try again later.");
            return;
        }

        chain.doFilter(request, response);
    }
}
~~~

- `getServletPath()` fits a demo running at the root context; if the app uses custom servlet mapping/context or a different login processing URL, configure the matcher accordingly.
- `request.getParameter("username")` matches default form login. If the app uses JSON login, this filter **does not read JSON**; design a limiter suited to the JSON authentication endpoint.
- Do not include passwords in limit keys, logs, or responses.
- When rejecting, the filter returns `429` before the password is hashed. This is not a normal `AuthenticationFailureHandler`, because Spring has not attempted authentication yet.
- The filter is instantiated directly inside `SecurityFilterChain`, **not registered as a servlet `@Component Filter`** to avoid running twice.

### 10.7. `SecurityConfiguration.java`

~~~java
package com.example.logindefense;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.user.password}") String password) {
        var alice = User.withUsername("alice")
                .password(encoder.encode(password))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            LoginAttemptGuard guard) throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error").permitAll()
                        .requestMatchers("/me").authenticated()
                        .anyRequest().denyAll())
                .formLogin(Customizer.withDefaults())
                .addFilterBefore(
                        new LoginThrottleFilter(guard),
                        UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}
~~~

- `formLogin` enables the default login page and Spring's password verification mechanism; the code does not manually compare password strings.
- The filter is placed **before** `UsernamePasswordAuthenticationFilter`; `anyRequest().denyAll()` blocks undeclared routes.
- **Keep default CSRF protection** for browser forms. When logging in through the Spring-generated `/login` page, the form includes the corresponding CSRF token; a curl request without CSRF may receive 403 before reaching the password verifier, which does not prove rate limiting.
- `PasswordEncoderFactories` creates a delegating encoder using an appropriate password hash; production needs explicit work factor settings and encoder upgrade policies.
- When rate limited, do not distinguish whether the username exists in the response.

### 10.8. `ProfileController.java`

~~~java
package com.example.logindefense;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {
    @GetMapping("/me")
    public Map<String, Object> me(Authentication authentication) {
        return Map.of(
                "username", authentication.getName(),
                "authenticated", authentication.isAuthenticated());
    }
}
~~~

This endpoint is for verifying the session after login; do not log or display the password or full security context.

### 10.9. Running the demo in a local browser

Linux/macOS:

~~~bash
export DEMO_USER_PASSWORD='local-test-password-only'
mvn spring-boot:run
~~~

PowerShell:

~~~powershell
$env:DEMO_USER_PASSWORD = "local-test-password-only"
mvn spring-boot:run
~~~

The password above is only a local example, **do not use it in environments accessible by others**. Open `http://localhost:8080/login` in a browser, enter username `alice` with the demo password, then visit `http://localhost:8080/me`. On a valid login, you receive JSON equivalent to:

~~~json
{"username":"alice","authenticated":true}
~~~

JSON key order is not fixed. When multiple `POST /login` requests in a short window exceed the quota, the filter may return HTTP `429`. There is no need to test third-party passwords; all testing is strictly on developer-owned demo accounts.

**Note:** Limiting applies to **every attempt**, even with the right password. This avoids certain races in the demo model, but can hurt UX when a valid login is rejected due to quota. Production should consider flexible limits, risk scoring, MFA/step-up, and user support flows without opening bypasses.

## 11. Testing the two independent buckets with JUnit 5

Add `src/test/java/com/example/logindefense/LoginAttemptGuardTest.java`:

~~~java
package com.example.logindefense;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class LoginAttemptGuardTest {

    @Test
    void sixthRapidAttemptForSameAccountIsLimited() {
        LoginAttemptGuard guard = new LoginAttemptGuard();

        for (int i = 0; i < 5; i++) {
            assertTrue(guard.allow("alice", "source-" + i));
        }

        assertFalse(guard.allow("alice", "fresh-source"));
    }

    @Test
    void sourceSweepingManyAccountsIsLimited() {
        LoginAttemptGuard guard = new LoginAttemptGuard();

        for (int i = 0; i < 20; i++) {
            assertTrue(guard.allow("account-" + i, "same-source"));
        }

        assertFalse(guard.allow("account-20", "same-source"));
    }

    @Test
    void usernameNormalizationUsesSameAccountBucket() {
        LoginAttemptGuard guard = new LoginAttemptGuard();

        for (int i = 0; i < 5; i++) {
            assertTrue(guard.allow("ALICE", "source-" + i));
        }

        assertFalse(guard.allow("alice", "another-source"));
    }

    @Test
    void badUsernameIsRejected() {
        LoginAttemptGuard guard = new LoginAttemptGuard();
        assertFalse(guard.allow("", "source"));
        assertFalse(guard.allow(null, "source"));
    }
}
~~~

Run from the project directory:

~~~bash
mvn test
~~~

**Expected:** 4 tests PASS; exact test count/stdout format depends on the Maven Surefire/JUnit version. This tests **burst policy within a single JVM** and does not prove protection against botnets/cross-instance traffic/lockout DoS. Because buckets refill over real time, do not use tests with long sleeps or explicit dependence on CPU speed; to deterministically test long-term refills, inject a monotonic clock/ticker in the implementation.

### Testing requests with MockMvc or a browser

Verify at least:
1. `GET /login` renders a form with CSRF.
2. `POST /login` missing CSRF is blocked per policy.
3. Valid login with `alice` and demo password creates a session.
4. Invalid login produces a generic error, revealing neither "user exists" nor exception type.
5. When exceeding the account bucket, even across different test sources, returns `429`.
6. When exceeding the source bucket, even as username changes, returns `429`.
7. Bypasses via alternate `/login` URLs, mixed-case paths, JSON login, or SSO fallback must be prevented per actual configuration.
8. Oversized bodies/headers, duplicate parameters, or malformed usernames do not break the parser or grant an unlimited bucket.
9. When the limiter store fails, behavior is evaluated; it does not silently open an unlimited gate.
10. After logout/session expiration, the `/me` endpoint does not return authenticated content.

**Do not run automated tests against third-party services or unauthorized production systems.** A defensive test can use fake users and in-process MockMvc for evaluation without generating dangerous traffic.

## 12. Adding failure/success telemetry in Spring Security

Limiting requests before authentication reduces load, but to detect credential stuffing **with valid passwords**, login success/failure events are still needed.

Spring Security has `AuthenticationFailureHandler`, `AuthenticationSuccessHandler`, and authentication events. With proper configuration, you can declare:

~~~java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher applicationEventPublisher) {
    return new DefaultAuthenticationEventPublisher(
            applicationEventPublisher);
}
~~~

The snippet above is an **extension configuration fragment**, requiring imports for `org.springframework.security.authentication.AuthenticationEventPublisher`, `DefaultAuthenticationEventPublisher`, and `org.springframework.context.ApplicationEventPublisher`. When using `@EventListener` with `AuthenticationFailureBadCredentialsEvent` or `AuthenticationSuccessEvent`, register the publisher and verify in practice which events your authentication manager emits.

**Do not rely solely on failure events:** requests rejected with 429 by `LoginThrottleFilter` **have not reached AuthenticationManager**, so they will not automatically emit `AuthenticationFailureEvent`. The filter/gateway must emit `login_throttled` metrics independently. Event handlers must also never log `Authentication.getCredentials()`, raw passwords, or full `Authentication.toString()`.

Reasonable security log fields:
- UTC timestamp, request ID/correlation ID;
- result `SUCCESS`, `BAD_CREDENTIALS`, `RATE_LIMITED`, `MFA_FAILED`, `CHALLENGE_REQUIRED`;
- hashed/pseudonymized account ID if policy allows, do not log raw email unless necessary;
- trusted remote IP/ASN/region per privacy policy;
- source system, tenant, risk score/bucket category (internal logs only);
- session ID **must not be logged in plaintext**, substitute a correlation ID that cannot act as a credential;
- no raw passwords, tokens, CSRF tokens, or Authorization/Cookie headers.

## 13. Detection using real metrics

### 13.1. Per account

- Failure count in 1/5/15 minutes.
- Fail/success ratio and number of new IPs/devices.
- Correct password but failed MFA.
- Successful login immediately followed by changing password/email, adding API keys, or creating anomalous new sessions.
- Consecutive throttles or lockouts disrupting legitimate users.

### 13.2. Per source/campaign

- Number of **distinct accounts** tried by one source over short/long intervals.
- Number of distinct sources targeting the same account.
- Request count/latency from an ASN, cloud hosting provider, or proxy network.
- Shifts in 401, 403, 429 rates and login success rate.
- Concurrency/automation patterns, CAPTCHA solve rate, token volume from bot mitigation.
- Success rate on accounts that rarely logged in previously.

### 13.3. Per tenant / product

- Campaigns targeting many users of a single organization.
- Spike in account takeover indicators following a breach announcement.
- Risk comparison between admins vs regular users.
- Volume of password resets/recoveries right after login alerts.
- Number of users experiencing false positives due to office NAT or shared mobile carriers.

**Passwords do not need to be stored to distinguish spraying from stuffing**. The difference is inferred from breach feeds, campaign characteristics, success rates, and valid correlations. Collect under data minimization principles, clear retention, and restricted access.

## 14. Trade-off scenarios: no single fixed threshold fits all

### Scenario A: one account tried many times

If `alice` has many login failures, even across changing IPs, the per-account bucket progresses to throttling. Delay or MFA/step-up can be added after crossing a threshold. **Do not permanently lock Alice's account automatically** from external signals alone.

### Scenario B: one IP tries many accounts

If many different usernames come from the same source, the per-source bucket and distinct-account detector trigger alerts. Do not wait for each user to hit a threshold of 5 because spraying may only try one password per account.

### Scenario C: many proxies try leaked credentials, once per user

The per-account bucket may not trigger; per-IP may not either. Correlation across ASN/device/session/login velocity, breached-password checks, MFA, and post-login behavior is required. **A single login with the right password is not enough to prove the legitimate account owner**.

### Scenario D: shared office IP

A school/company IP has hundreds of legitimate users logging in; a per-IP limit that is too low causes mass 429s. Tune thresholds/controlled allowlisting based on trusted edge signals, add per-account limits and risk signals; do not disable all limits for one shared IP.

### Scenario E: attacker causes account lockout DoS

The attacker intentionally sends wrong passwords to many accounts to trigger hard locks. Replace long hard locks with progressive delays, risk-based controls, and recovery. Design to distinguish voluntary logins from suspicious traffic while still defending against brute force.

## 15. Common implementation mistakes

1. **Rate limiting by IP only:** botnet/proxy rotation can still target a single account.
2. **Rate limiting by username only:** spraying/stuffing once per account is very hard to block.
3. **Using only an `IP:username` key:** creates separate quotas for unlimited combinations.
4. **In-memory buckets for a cluster:** each pod has its own quota; scaling pods unintentionally increases attempt capacity.
5. **Unbounded key map size:** attackers generate fake usernames causing memory DoS.
6. **Using client-sent `X-Forwarded-For`:** can spoof source and bypass per-IP limits.
7. **Hard-locking accounts for hours just for failed attempts:** becomes a denial of service.
8. **CAPTCHA as the sole control:** can be bypassed and causes accessibility issues.
9. **MFA with weak reset/recovery paths:** attackers bypass it via account recovery.
10. **Keeping leaked passwords while only increasing complexity:** still vulnerable to stuffing if the password already matches; requires breached-password detection and MFA.
11. **Returning different messages for non-existent user and wrong password:** aids enumeration.
12. **Logging raw passwords/tokens or entire requests:** causes severe credential leakage.
13. **Using failure count as the only criterion:** credential stuffing can succeed on the first try.
14. **Forgetting JSON/mobile/legacy Basic paths:** attackers choose paths without a limiter.
15. **Rate limiting after password hashing:** does little to reduce CPU load caused by bots.
16. **Lacking concurrency tests:** races in Redis/DB can allow exceeding thresholds.
17. **Mixing proxy IP with user IP:** the whole system is treated as a single source.
18. **Trusting User-Agent/device ID as verified identity:** client data can be spoofed.
19. **No user alerts after anomalous logins:** ATO impact persists longer.
20. **Assuming default Spring `formLogin` blocks all bots:** additional policies are needed at login, gateway, IdP, and domain layers.

## 16. Defensive testing matrix

| Case | What to verify |
|---|---|
| One account many attempts, same IP | Per-account limit blocks burst |
| One account many attempts, different IPs | Per-account limit still blocks |
| Many accounts, same IP | Per-source limit still blocks |
| Many accounts, many IPs, low rate | Campaign detector/correlation detects |
| Login with right password but wrong MFA | No authenticated session created, risk signal emitted |
| Login with right password on unfamiliar device | MFA/step-up or risk policy applies |
| Non-existent user vs wrong password | Message/status/timing does not leak account |
| Login missing CSRF | Browser form blocked by CSRF policy |
| Request with overly long username | Limited before storing unbounded state |
| User enters email with different casing | Canonicalization follows shared contract |
| User `alice` via `/login` and JSON login | Same policy across all entry points |
| Shared IP with many legitimate users | False positives measured and tuned |
| Burst at minute boundary | Sliding/token bucket avoids fixed-window burst gap |
| Many concurrent requests on same bucket | Quota not exceeded due to race |
| 3 instances + one Redis | Cluster-wide limit, not multiplying quota per instance |
| Redis/gateway outage | Does not silently open unlimited; fallback policy tested |
| Account hard-locked by attacker | Recovery and DoS protection exist |
| CAPTCHA cannot be completed | Does not strip authentication controls or break accessibility |
| Filter blocks request with 429 | Throttle metrics emitted even without authentication failure event |
| Login success then risky behavior | Audit/alert/step-up on sensitive endpoints |
| Old sessions after reset/compromise | Invalidated/revalidated per policy |
| Password reset/forgot-password | Does not create enumeration/limit bypass path |
| API key/SSO/legacy Basic | Appropriate policy instead of bypass |
| Logs and tracing | Contain no raw passwords, CSRF tokens, session IDs, or bearer tokens |

**Measure false positives alongside detection rate**: a configuration that blocks all bots while locking out masses of legitimate users is not a successful design. Roll out via audit-only → challenge/soft throttle → block, monitor error rates, and maintain a rollback plan.

## 17. Production checklist

- [ ] All username/password authentication endpoints are inventoried, including mobile, API, admin, and fallbacks.
- [ ] Independent rate limits exist per account and per source; not just combined IP:username.
- [ ] Distributed spraying/stuffing detection exists using aggregate signals and short/long windows.
- [ ] Limiter is shared across replicas, updated atomically, with TTL/eviction and capacity bounds.
- [ ] Origin IP is determined via trusted proxies, not untrusted client headers.
- [ ] Thresholds, windows, delays, CAPTCHA, and lockouts are measured for false positives/DoS.
- [ ] Attackers cannot permanently lock out users solely via wrong password attempts.
- [ ] MFA/passkeys are required appropriately for risk, especially for admins and unfamiliar logins.
- [ ] Passwords are stored with strong password hashing; breached passwords are screened on change/creation.
- [ ] Error messages/login statuses do not facilitate enumeration.
- [ ] CSRF/session fixation/cookie security remain protected in browser logins.
- [ ] Authentication success/failure and throttled requests each have dedicated metrics.
- [ ] Raw passwords, Authorization headers, Cookie/session IDs, or secret tokens are never logged.
- [ ] Alerts exist for abnormal success, MFA failure, session takeover, and email/password changes.
- [ ] Incident response procedures exist: force reset/revoke sessions/tokens, notify users, temporarily tighten controls.
- [ ] Tested for concurrency, multi-replica, store outage, NAT/shared IP, and browser accessibility.
- [ ] For IdP/SSO cases: policy is enabled where passwords are actually verified.

## 18. Key takeaways

- **Brute force:** many passwords targeting **one account** → per-account velocity is the primary signal.
- **Password spraying:** one/a few passwords targeting **many accounts** → watch distinct accounts/source/campaign.
- **Credential stuffing:** using **leaked credential pairs** → a single attempt can succeed; MFA/passkeys and post-login anomaly detection are crucial.

**The solution does not lie in one fixed threshold:** combine two independent account + source buckets, correlation at the edge and application, MFA/WebAuthn, breached-password screening, generic error messages, safe auditing, and mechanisms that do not turn login throttling into a DoS tool. Spring Security provides extension points to integrate these layers, but detection policies and anti-automation state management still need dedicated design.

## 19. References

1. [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): brute force/spraying/stuffing classification, login throttling, lockout, generic errors, logging.
2. [OWASP — Credential Stuffing Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html): MFA, IP intelligence, device signals, detection, defense in depth.
3. [OWASP — Bot Management and Anti-Automation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Bot_Management_and_Anti-Automation_Cheat_Sheet.html): edge/application/backend layers, per-account vs per-source quotas.
4. [NIST SP 800-63B-4 — Authentication and Authenticator Management](https://pages.nist.gov/800-63-4/sp800-63b.html): online guessing/throttling controls and consecutive failed attempt limits.
5. [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): `UsernamePasswordAuthenticationFilter`, authentication success/failure handlers.
6. [Spring Security 6.5 — Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html): `DefaultAuthenticationEventPublisher`, success/failure events.
7. [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationManager`, `AuthenticationProvider`, `SecurityContext`.
8. [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): secure password hashing and work factors.
9. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): login security logs and removing sensitive data.
