# Preventing Brute Force, Credential Stuffing, and Enumeration

> **Chapter: Server Security.** This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, focusing on designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in Spring Boot. The goal is to protect user authentication flows, clients, and account recovery endpoints against password guessing, leaked credential reuse, password spraying, and account enumeration.

## 1. Distinguishing Login Attack Types

Automated attacks can target the same login endpoint while distributing requests differently. Rate-limiting by IP alone allows attackers to rotate proxies; counting only by username allows attackers to lock out victims' accounts.

| Attack type | How it operates | Common indicators | Goal |
|---|---|---|---|
| Brute force | Tries many passwords against one account | One account receives many failed logins | Guess the password |
| Password spraying | Tries a few common passwords across many accounts | One source or cluster tries the same pattern across many usernames | Evade per-account lockout thresholds |
| Credential stuffing | Tries username/password pairs from external breaches | Many credential pairs, many accounts, distributed IPs/devices | Exploit password reuse |
| Account enumeration | Probes whether accounts exist via differing messages, statuses, timings, or flows | Observable differences when username exists vs. does not exist | Harvest a list of valid accounts |
| MFA/OTP guessing | Guesses OTP codes or recovery codes | Repeated incorrect entries for an authenticator | Bypass the second factor |
| Client credential guessing | Guesses client secrets at the token endpoint | Repeated client authentication failures | Compromise an OAuth client |

The first three differ in request distribution, yet all can increase load on the Authentication Server. Account enumeration is often a reconnaissance step: attackers collect valid accounts before launching password spraying or credential stuffing.

### 1.1. Recognizable Examples

- **Brute force:** 500 different passwords tried against `alice@example.vn`.
- **Password spraying:** the password `Spring2026!` tried once against 500 accounts.
- **Credential stuffing:** 5,000 username/password pairs from a data breach replayed against the Authorization Server.
- **Enumeration:** an endpoint returns `User not found` when an account does not exist, but returns `Invalid password` when the account exists.

Not every wave of failed logins is an attack. Users mistype passwords, switch devices, or forget accounts. Defenses must slow down attackers while preserving legitimate recovery paths for real users.

## 2. Why Is an Authorization Server a High-Value Target?

The Authorization Server is typically a shared authentication gateway across many applications. Compromising one account can unlock multiple relying parties/resource servers according to granted clients, scopes, and privileges.

Surfaces requiring protection:

| Endpoint/flow | Risk |
|---|---|
| Login form / authentication endpoint | Brute force, spraying, credential stuffing |
| Password reset / account recovery | Enumeration, OTP guessing, takeover |
| MFA enrollment / verification | OTP guessing, recovery-code guessing, MFA fatigue |
| OIDC authorization endpoint | Driving users into login flows, creating excessive authentication transactions |
| Device verification | Probing `user_code`, attempting unauthorized device approval |
| Client token endpoint | Guessing client secrets, abusing client authentication |
| Client registration / dynamic registration | Creating junk clients, registration abuse, and enumeration |
| Admin console | Compromising privileged accounts, tampering with redirect URIs or credentials |

Spring Authorization Server handles the OAuth2/OIDC protocol; user authentication is usually handled by Spring Security and the application's login flow. SAS itself does not provide a complete rate-limiting policy for login forms out of the box. Applications must integrate throttling, anti-automation, MFA, account recovery, and monitoring at the appropriate endpoints.

### 2.1. Never Mix User Authentication with Client Authentication

`alice@example.vn` is a user principal. `orders-service` is an OAuth client. The two credential types have different lifecycles, throttling thresholds, and handling procedures.

- User login: rate-limit by account identifier, IP, device/session, and risk signals.
- Client authentication: rate-limit by `client_id`, request origin, and client authentication method.
- Device authorization: separately rate-limit device code creation and user code entry.
- MFA/OTP: rate-limit per authenticator/account and code lifetime.

Never increment a user's failed password counter when a confidential client sends a wrong `client_secret`. Nor should client authentication errors expose internal client registration details.

## 3. Threat Model and Defense Flow

~~~mermaid
flowchart TD
    A["Login request"] --> B["Edge: WAF / CDN / IP reputation"]
    B --> C["Application: normalize account identifier"]
    C --> D["Check account bucket"]
    C --> E["Check IP / ASN bucket"]
    C --> F["Check device / session / endpoint risk"]
    D --> G{"All limits and risk policy pass?"}
    E --> G
    F --> G
    G -->|No| H["Generic throttle response / challenge"]
    G -->|Yes| I["Spring Security AuthenticationManager"]
    I --> J{"Credentials valid?"}
    J -->|No| K["Record failure + emit security event"]
    J -->|Yes| L["MFA / step-up if required"]
    L --> M["Create authenticated session"]
    K --> N["Generic login failure"]
    M --> O["Audit + success metrics"]
~~~

Each layer plays a distinct role:

1. **Edge:** absorbs bursts and blocks bad-reputation sources before requests reach the application.
2. **Application:** enforces buckets by account, IP, endpoint, and transaction.
3. **Authentication:** verifies passwords/MFA using the appropriate providers.
4. **Risk engine:** triggers step-up or challenges on anomalous behavior.
5. **Monitoring:** detects distributed patterns and tunes policies.

No single threshold or CAPTCHA stops every attack style. Combine multiple signals and measure impact on legitimate users.

## 4. Multi-Dimensional Rate Limiting

Rate limiting should use multiple independent buckets. Each bucket counters a different request distribution pattern.

| Bucket | Logical key | Defends against | Notes |
|---|---|---|---|
| Account | Normalized and pseudonymized account identifier | Multiple IPs attacking one account | Apply even when the account does not exist |
| IP | Source IP resolved via trusted proxy | One IP trying many accounts | Not a standalone layer because attackers rotate IPs |
| IP + ASN/network | Network source or ASN | Multiple IPs within the same infrastructure | Requires reliable reputation data |
| Device/session | Protected cookie/session identifier | Bot rotating usernames while keeping browser context | Avoid invasive fingerprinting if unnecessary |
| Endpoint | Login, password reset, OTP, device verification | Abuse of a specific flow | Different thresholds per endpoint |
| Client | Resolved `client_id` | Guessing client secrets or abusing clients | Separate from user password buckets |
| Tenant/issuer | Verified tenant | One tenant under attack or generating load | Never take tenant from unverified query parameters |
| Global | System-wide or service cluster | Large bursts, capacity protection | Prevent a single account from starving the whole cluster |

OWASP Bot Management recommends at least two independent buckets for login: per-username and per-IP. Using only a composite key `login:<ip>:<username>` allows one IP to try its threshold against unlimited usernames because each pair gets a fresh bucket. Check each bucket independently and allow the request to proceed only when all are below threshold.

### 4.1. Normalizing Account Identifiers

The rate-limit account bucket must follow the exact same canonicalization rules as user lookup:

- Trim leading/trailing whitespace if the login contract allows it.
- Normalize Unicode according to published policy.
- Normalize email/username per actual lookup rules; do not lowercase automatically if identifiers are case-sensitive.
- Never include passwords in rate-limit keys.
- Avoid writing raw usernames/emails into Redis keys or logs whenever possible.

You can derive pseudonymized keys using HMAC with a dedicated secret:

~~~text
accountKey = HMAC-SHA-256(rateLimitKey, canonicalAccountIdentifier)
ipKey      = HMAC-SHA-256(rateLimitKey, canonicalSourceIp)
~~~

The HMAC key must be managed as a secret with a rotation plan and never shared with signing keys or token keys. Pseudonymization reduces PII exposure in caches/metrics, though it does not replace access control or retention policies.

### 4.2. Resolving Client IPs Behind a Reverse Proxy

`request.getRemoteAddr()` typically returns the reverse proxy's address behind a load balancer. Trusting `X-Forwarded-For` indiscriminately lets an attacker spoof headers to switch IP buckets.

- Trust forwarded headers only from allowlisted proxies/load balancers.
- The proxy must strip client-supplied headers and write canonical values.
- Extract hops strictly per configured topology; never blindly pick the first element.
- Without a trusted proxy, use the connection's remote address.
- Test IPv4, IPv6, NAT, and multi-proxy hops.

## 5. Choosing Throttling Algorithms and Policies

### 5.1. Token Bucket or Sliding Window

Token buckets permit small bounded bursts and refill steadily over time. Sliding windows count attempts over the most recent time window. Both outperform simple fixed-window counters because fixed windows allow double bursts across window boundaries.

Illustrative examples:

| Policy | Window | Action when exceeded |
|---|---|---|
| Account bucket | 5 failures in 10 minutes | Progressive delay or step-up |
| IP bucket | 30 attempts in 5 minutes | Short-term source throttling |
| OTP bucket | Per authenticator-specific policy | Delay/disable authenticator per applicable standard |
| Password reset | Per account and IP in separate windows | Return generic response and limit email/SMS dispatch |
| Client authentication | Per client and request source | Throttle client/source, alert operations |

These are only starting values to illustrate configuration. Production thresholds must reflect normal traffic, account types, assurance levels, user experience, and compliance requirements. Do not copy these numbers as a universal standard.

### 5.2. Rate Limits Must Work Across Multiple Instances

A `ConcurrentHashMap` or in-memory counter limits only a single JVM. If the Authorization Server runs 5 pods, an attacker can spread requests across pods and multiply the effective allowance.

Production should use a shared store such as Redis or database counters with atomic updates:

- Increment/check must be atomic so concurrent requests cannot race past thresholds.
- Buckets have TTLs and expire automatically per policy.
- Use sliding windows/token buckets with consistent time.
- Enforce memory bounds and eviction strategies.
- When Redis/cache fails, define fail-open vs. fail-closed explicitly by risk; for critical login abuse protection, circuit breakers and edge rate-limit fallbacks are usually needed.
- Ensure the rate-limit store does not become a bottleneck or a new DoS vector.

### 5.3. Progressive Delay and Account Lockout

Permanent hard lockouts are easily abused for denial of service: an attacker merely submits wrong passwords for a victim's account. Instead:

- Increase delay with consecutive failures, up to a capped maximum.
- Apply account and IP buckets independently.
- Optionally require CAPTCHA or MFA step-up as risk increases.
- Provide users a safe recovery path even while login is throttled.
- Reset the account's consecutive-failure counter only after all required authentication policies complete.
- Notify users of anomalous activity without leaking details to attackers.

NIST SP 800-63B-4 requires throttling for in-scope authenticators and specifies a maximum cap of 100 consecutive failed attempts per authenticator on a subscriber account, unless an authenticator type specifies otherwise. **100 is an upper bound, not a recommended default for every application.** Lower thresholds are permissible and often necessary depending on risk. Techniques to mitigate lockout DoS include increasing wait times and risk-based challenges.

### 5.4. Responses When Thresholds Are Exceeded

Responses should be clear enough for users to know to wait or try another method, without revealing which bucket triggered:

~~~http
HTTP/1.1 429 Too Many Requests
Cache-Control: no-store
Content-Type: application/json

{
  "error": "temporarily_unavailable",
  "message": "Unable to sign in right now. Please try again later."
}
~~~

This is an illustrative response for a login application. For OAuth2 protocol endpoints, follow protocol-compliant error responses and avoid emitting incompatible custom bodies.

Never return details such as:

- The account exists but is locked.
- You have 2 attempts remaining.
- The IP bucket exceeded 20 requests.
- The exact timestamp when the account unlocks if that helps attackers optimize retry schedules.

You may return 429 for throttling, provided the response does not become an enumeration oracle. Apply the generic response uniformly across all identifiers governed by the same policy.

## 6. Integrating Rate Limiting with Spring Security

Spring Security verifies credentials via `AuthenticationManager` and `AuthenticationProvider`. The rate limiter should check before the provider performs password verification, then record the outcome after authentication.

A domain interface decouples filters from Redis/database implementations:

~~~java
public interface LoginAbuseGuard {

    boolean isThrottled(String accountIdentifier, String sourceIp);

    void recordFailure(String accountIdentifier, String sourceIp);

    void recordSuccess(String accountIdentifier);
}
~~~

Production implementations must:

- Canonicalize the account identifier using the exact same policy as user lookup.
- HMAC account/IP keys before storage.
- Check two independent buckets: account and source IP.
- Use Redis/Lua or equivalent atomic primitives.
- Set TTLs and progressive delays.
- Never store passwords or raw credentials.
- Reset the account failure counter only upon policy-complete successful authentication.

### 6.1. Filter Checking Before UsernamePasswordAuthenticationFilter

Example filter for form login at `/login`:

~~~java
import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public final class LoginRateLimitFilter extends OncePerRequestFilter {

    private final LoginAbuseGuard guard;
    private final ClientIpResolver clientIpResolver;

    public LoginRateLimitFilter(
            LoginAbuseGuard guard,
            ClientIpResolver clientIpResolver) {
        this.guard = guard;
        this.clientIpResolver = clientIpResolver;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !"POST".equals(request.getMethod())
                || !"/login".equals(request.getServletPath());
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        String account = request.getParameter("username");
        if (account == null) {
            account = "";
        }

        String sourceIp = clientIpResolver.resolve(request);

        if (guard.isThrottled(account, sourceIp)) {
            response.setStatus(HttpServletResponse.SC_TOO_MANY_REQUESTS);
            response.setHeader("Cache-Control", "no-store");
            response.setContentType("text/plain;charset=UTF-8");
            response.getWriter().write(
                    "Unable to sign in. Please try again later.");
            return;
        }

        filterChain.doFilter(request, response);
    }
}
~~~

`ClientIpResolver` is an application component that reads forwarded headers only from trusted proxies. If the login processing URL or username parameter is customized in `formLogin`, update the filter's matcher and parameter name accordingly. Never apply this filter to every POST request.

### 6.2. Recording Failures and Successes

Attach handlers to form login. Condensed example:

~~~java
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

http
    .addFilterBefore(
            new LoginRateLimitFilter(loginAbuseGuard, clientIpResolver),
            UsernamePasswordAuthenticationFilter.class)
    .formLogin(form -> form
        .failureHandler((request, response, exception) -> {
            loginAbuseGuard.recordFailure(
                    request.getParameter("username"),
                    clientIpResolver.resolve(request));

            response.sendRedirect("/login?error");
        })
        .successHandler((request, response, authentication) -> {
            loginAbuseGuard.recordSuccess(authentication.getName());
            response.sendRedirect("/");
        }));
~~~

This example assumes form login uses processing URL `/login`, parameter `username`, and application-appropriate redirects. When deploying:

- `failureHandler` must return the exact same content/redirect for wrong password, nonexistent account, disabled account, or locked account.
- Never write exception details to the response.
- `successHandler` must reset the counter only after all required authentication steps—including MFA if required by policy—have completed.
- When using custom authentication flows or multiple filter chains, attach the limiter to the exact chain handling login.
- Across multiple pods, `LoginAbuseGuard` must use a shared store.

The filter checks throttling before password verification. The failure handler increments counters after `AuthenticationManager` rejects the attempt. Spring Security events can support auditing/metrics, but do not replace request-aware handlers because authentication events do not inherently carry trusted client IP and endpoint context.

### 6.3. Authentication Events for Monitoring

`ProviderManager` can publish authentication success/failure events when configured with an `AuthenticationEventPublisher`. Useful events include:

- `AuthenticationFailureBadCredentialsEvent`
- `AuthenticationFailureLockedEvent`
- `AuthenticationFailureDisabledEvent`
- `AuthenticationSuccessEvent`
- `InteractiveAuthenticationSuccessEvent`

Use event listeners to update metrics, audit logs, and alerts. Do not expect an IP directly from events; if request correlation is needed, use a request correlation ID or a handler/filter that resolved the IP. Never log full `Authentication` objects if they may contain credentials or sensitive data.

## 7. Preventing Account Enumeration

Attackers can determine whether a username/email exists via messages, status codes, redirects, response sizes, headers, processing timing, or secondary request counts.

### 7.1. Use Generic Messages

Return the exact same message when:

- The username does not exist.
- The password is wrong.
- The account is locked or disabled.
- The account has not verified its email.
- Login is denied by internal policy.

Example:

~~~text
Unable to sign in. Please check your details or try again later.
~~~

Never return `User not found`, `Password incorrect`, `Account locked`, or `MFA not enrolled` in public responses. Support/admins can inspect account status via authorized internal tools.

### 7.2. Unify Status, Redirects, and Response Shapes

Do not change text messages alone. Inspect all of:

- HTTP status code.
- Redirect location and query parameters.
- Response body length and JSON structure.
- Headers such as `Retry-After` or `X-Account-State`.
- Number of database, email, or external provider calls.
- Whether processing latency differs enough for statistical inference.

For example, password recovery should always return a consistent message:

~~~text
If the information matches an account, we will send further instructions.
~~~

Never reveal whether an email exists. Dispatch emails via an asynchronous queue and rate-limit per account/IP so the recovery endpoint cannot become a spam relay.

### 7.3. Minimize Timing Discrepancies

If an account does not exist, an application might return early before executing password hash comparison; if the account exists, the password encoder spends noticeable CPU time. By measuring latency repeatedly, an attacker can distinguish the two cases.

Controls:

- Use a dummy encoded password and run `PasswordEncoder.matches(...)` once when the account does not exist.
- Never return early solely based on the user lookup outcome.
- Follow the same response path for all credential failure types.
- Avoid invoking external services only in the existing-account branch.
- Measure latency distributions in tests/load tests; avoid injecting huge artificial delays that invite DoS.

Spring Security's `DaoAuthenticationProvider` includes user-not-found handling to reduce timing leaks in standard flows; if replacing it with a custom `AuthenticationProvider`, preserve equivalent timing behavior. Never skip dummy hashing merely because error messages are generic.

### 7.4. Enumeration in Non-Login Flows

| Flow | Response to unify |
|---|---|
| Password reset | If the account exists, instructions will be sent |
| Account recovery | Never confirm whether the identifier exists |
| Registration | Never disclose whether an email is already registered if policy requires privacy |
| MFA enrollment/recovery | Never reveal which authenticator types a user enrolled prior to authentication |
| Device verification | Never reveal valid device/user codes through detailed error messages |
| Client lookup/admin | Show details only to authorized admins |

Enumeration protection does not mean hiding everything in every context. Once a user has authenticated with sufficient assurance—or an admin is authorized—the UI can display specific business status as appropriate.

## 8. Defending Against Credential Stuffing and Password Spraying

Credential stuffing uses credentials that may be completely valid. Strong password encoders and rate limits alone may not stop a successful login if an attacker replays a valid leaked username/password pair.

### 8.1. MFA and Phishing-Resistant Authentication

MFA is a critical defense against credential reuse. Prefer phishing-resistant authenticators such as WebAuthn/passkeys where supported; existing systems can use TOTP or methods matched to the threat model.

Require step-up when:

- Logging in from a new browser or device.
- The IP/ASN has poor reputation or is probing multiple accounts.
- Geography or time deviates from known patterns.
- Bot/headless automation indicators appear.
- The user recently changed their password or recovery factors.
- Accessing administrative functions or high-risk transactions.

Do not rely on SMS OTP as the sole defense for high-value accounts. MFA fatigue/push bombing also requires mitigations such as number matching, rate limits, and clear contextual prompts.

### 8.2. Checking for Breached Passwords

During registration or password changes:

- Block common, predictable passwords or passwords appearing in breach corpora per policy.
- Use a local list or a k-anonymity service; never send plaintext passwords to third parties.
- If checking breached passwords at login, use the result only as a risk signal to require step-up/alerts or post-authentication password change; never produce a distinct response that leaks account existence.
- Notify users when potentially compromised credentials are detected.

Do not force periodic password rotations without evidence of compromise or regulatory mandate. Encourage password managers and permit paste/autofill.

### 8.3. IP Reputation and Device Signals

Useful signals include:

- IP reputation, ASN, and proxy/VPN/Tor signals per policy.
- Number of distinct accounts attempted from one IP/subnet.
- Number of distinct IPs attempting the same account.
- TLS/HTTP connection fingerprints at the edge where legally grounded.
- Pseudonymized device/session identifiers.
- Request frequency, intervals, and patterns.
- Browser automation/headless indicators.

Fingerprinting can impact privacy and accessibility. Prefer passive/network signals first, collect the minimum necessary, and enforce clear retention limits.

### 8.4. CAPTCHA and Adaptive Challenges

CAPTCHA raises the cost of automation, though it is not an absolute bot barrier. Attackers can use solver farms, automated models, or human-solver services.

Reasonable usage:

- Trigger only when risk scores elevate or after several failures.
- Combine with rate limits, MFA, and IP/device signals.
- Never use CAPTCHA as a substitute for passwords or MFA.
- Provide accessibility alternatives and avoid locking out real users if the CAPTCHA provider fails.
- Track solve rates and false-positive rates.

## 9. Protecting Related Flows in the Authorization Server

### 9.1. Password Reset and Account Recovery

- Rate-limit independently by account identifier and IP.
- Return generic responses regardless of account existence.
- Reset tokens/codes must have high entropy, be single-use, and have short TTLs.
- Store reset tokens hashed whenever possible.
- Never send reset links/codes to unverified channels.
- After a reset, consider revoking active sessions/refresh tokens and notifying the user.
- Never let the reset flow become a bypass around account lockouts or MFA policies.

### 9.2. MFA/OTP and Recovery Codes

Each authenticator needs its own counter per account/authenticator, alongside IP/device risk signals. OTPs are short-lived, yet attackers can guess multiple codes within that window; cap attempts, prevent replay, and accept codes only once.

Recovery codes must have sufficient entropy, be stored hashed, and be single-use. Never log OTPs or recovery codes. NIST SP 800-63B-4 also mandates throttling for in-scope authenticators, including recovery codes and low-entropy OTPs.

### 9.3. Device Authorization Flow

The Device Authorization Grant involves two request types:

- Client calls the device authorization endpoint to obtain `device_code` and `user_code`.
- User enters `user_code` at the verification endpoint to authenticate and approve.

Controls needed:

- Rate-limit device code creation per client/IP.
- Rate-limit user code entry per IP/session.
- Ensure `user_code` has sufficient protocol entropy, a TTL, and attempt limits.
- Never distinguish valid vs. invalid user codes via differing responses.
- Display client name and requested scopes before user approval.
- Require explicit authentication and consent; never auto-approve merely because a code is valid.
- Audit approvals, denials, expirations, and brute-force signals.

### 9.4. Client Authentication at the Token Endpoint

Confidential clients may face `client_secret` guessing at `/oauth2/token`, `/oauth2/introspect`, or `/oauth2/revoke`. Enforce dedicated policies by `client_id`, IP/ASN, client authentication method, and endpoint.

- Never share user account lockout counters with client secret failures.
- Never leak internal details such as client existence, secret hashes, or credential states.
- Prefer `private_key_jwt` or mTLS over long-lived shared secrets where feasible.
- Monitor repeated failures per client/source and alert owners.
- Never mass-disable legitimate clients simply because an external source sends bad credentials; use throttling and controlled rotation workflows.

## 10. Observability, Auditing, and Incident Response

Logs and metrics must answer: who is being targeted, which sources are sending requests, what pattern is occurring, which policy triggered, and whether legitimate users are impacted.

### 10.1. Recommended Log Fields

| Field | Example | Notes |
|---|---|---|
| Event type | `LOGIN_FAILURE` | Distinguish user/client/MFA/recovery |
| Account fingerprint | HMAC identifier | Never log raw username/email |
| Source IP | Resolved IP | Comply with privacy/retention |
| Tenant/issuer | Verified tenant | Never read from untrusted query parameters |
| Client ID | `employee-portal` | Client resolved in registry |
| Device/session ID | Pseudonymous ID | Never log raw session cookies |
| Risk decision | `STEP_UP_REQUIRED` | Record internal policy code |
| Rate bucket | `ACCOUNT`, `IP`, `OTP` | Never expose bucket names in public responses |
| Correlation ID | Request trace ID | Used for cross-service investigation |
| Outcome | `THROTTLED`, `FAILED`, `SUCCESS` | Contains no passwords or tokens |

Never log passwords, password hashes, OTPs, recovery codes, authorization codes, access tokens, refresh tokens, or client secrets. Avoid using usernames/IPs as high-cardinality metric labels; use aggregate counters, histograms, and controlled logs/traces.

### 10.2. Patterns Worth Alerting On

- One account targeted from many IPs/ASNs within a short window.
- One IP probing many accounts with few attempts per account.
- Many accounts receiving identical failure patterns from a cluster of sources.
- Spikes in successful logins immediately following waves of credential failures.
- Sudden spikes in password resets or MFA recovery requests.
- Multiple `client_id` values failing client authentication from the same source.
- High rates of invalid `user_code` submissions at device verification.
- Sharp increases in throttling false positives after a policy change.

### 10.3. Response When Credential Compromise Is Suspected

1. Identify affected accounts/clients, tenants, issuers, and timeframes.
2. Tighten risk controls or require step-up for targeted groups.
3. Notify users via verified channels; never send sensitive details via untrusted email.
4. Force password resets upon evidence of compromise; revoke sessions/refresh tokens per policy.
5. Audit suspicious post-login authorization and token issuance activity.
6. Rotate client secrets or upgrade to stronger authentication methods if client credentials leaked.
7. Preserve audit evidence and update detection rules post-incident.

## 11. Test Matrix for Brute Force, Stuffing, and Enumeration

| # | Scenario | Expected result |
|---|---|---|
| 1 | One account receives many wrong passwords from one IP | Account bucket increments and triggers delay/throttle |
| 2 | One account is attacked from multiple IPs | Account bucket still limits distributed brute force |
| 3 | One IP tries many accounts | IP bucket caps overall volume |
| 4 | Attacker rotates usernames continuously from one IP | Does not create independent buckets solely keyed by IP+username |
| 5 | Attacker rotates IPs while targeting one account | Account bucket still enforces limits |
| 6 | Multiple pods handle requests for the same account | Shared store keeps counters consistent |
| 7 | Redis processes two concurrent requests | Atomic increment/check prevents racing past thresholds |
| 8 | Bucket TTL expires | Counter resets properly per policy |
| 9 | Request carries spoofed forwarded IP | Does not alter IP bucket when proxy is untrusted |
| 10 | Username varies in Unicode/whitespace/case | Canonicalization matches user lookup policy |
| 11 | Nonexistent account tried repeatedly | Still throttled by account bucket |
| 12 | Nonexistent account vs. wrong password | Equivalent message, status, and redirect |
| 13 | Disabled account with wrong password | Account state not leaked in public response |
| 14 | Locked account with wrong username | Creates no response oracle |
| 15 | Login response timing for existing vs. nonexistent accounts | No statistically exploitable timing discrepancy |
| 16 | Password reset for nonexistent email | Identical response to existing email |
| 17 | Repeated password reset requests | Email dispatch rate-limited and anti-spam enforced |
| 18 | Registration with existing email | Does not disclose account existence per policy |
| 19 | Breached password used during password change | Blocked or user prompted to choose another password |
| 20 | Login using password flagged as compromised | Risk policy can require step-up/rotation |
| 21 | Login from new device | MFA/step-up triggered per policy |
| 22 | One IP probes multiple accounts | Risk engine detects password spraying/stuffing |
| 23 | CAPTCHA solver returns valid token at abnormal velocity | Other risk layers can still throttle |
| 24 | Legitimate user gets throttled | Receives generic message and valid recovery path |
| 25 | Attacker deliberately fills account bucket | Does not trigger permanent DoS lockout |
| 26 | Consecutive wrong MFA OTPs | Authenticator-specific throttle applied |
| 27 | Valid OTP replayed | Replay rejected |
| 28 | Consecutive wrong recovery codes | Counter/throttle applied per authenticator |
| 29 | Valid recovery code used a second time | Rejected |
| 30 | Device verification probes multiple `user_code` values | Throttled and responses do not reveal valid codes |
| 31 | Device authorization client creates requests too fast | Client/IP quota enforced |
| 32 | Confidential client sends repeated wrong secrets | Client-auth bucket increments without locking user accounts |
| 33 | Nonexistent Client ID with wrong secret | Leaks no registration details beyond protocol contract |
| 34 | `AuthenticationFailureBadCredentialsEvent` published | Metrics/audit record event without logging credentials |
| 35 | `AuthenticationSuccessEvent` after MFA | Resets counter only after full authentication per policy |
| 36 | Rate limiter store temporarily unavailable | Fallback/fail policy matches threat model, never fails wide open |
| 37 | Metrics dashboard tracks failures/successes/throttles | Contains no raw usernames/passwords or high-cardinality PII |
| 38 | One source blocked while user switches source | Account bucket and risk policy still apply |
| 39 | Many accounts tried with one common password | Password spraying pattern detected |
| 40 | Many credential pairs replayed across devices | Credential stuffing detected and step-up required |
| 41 | User disabled after a prior successful login | Session/token lifecycle handled per account policy |
| 42 | Client secret rotated after incident | Old credential invalidated and audit preserved |
| 43 | Rate limits configured only at CDN | Integration tests prove application still enforces identity-aware limits |
| 44 | Recovery/MFA endpoints omitted from policy | Security review flags unprotected endpoints |
| 45 | Public response returns remaining attempts | Enumeration test fails |

### 11.1. Integration Tests with MockMvc

The example below tests the filter/handler at the HTTP layer. `LoginAbuseGuard` is a mock or test implementation; tests must verify both throttled requests and requests forwarded to the authentication flow.

~~~java
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void throttledLoginIsRejectedBeforeAuthentication() throws Exception {
    when(loginAbuseGuard.isThrottled("alice@example.vn", "203.0.113.10"))
            .thenReturn(true);

    mockMvc.perform(post("/login")
            .param("username", "alice@example.vn")
            .param("password", "not-a-real-password"))
        .andExpect(status().isTooManyRequests());

    verify(authenticationManager, never()).authenticate(any());
}

@Test
void failedLoginIncrementsAccountAndIpBuckets() throws Exception {
    when(loginAbuseGuard.isThrottled("alice@example.vn", "203.0.113.10"))
            .thenReturn(false);

    mockMvc.perform(post("/login")
            .param("username", "alice@example.vn")
            .param("password", "wrong-password"))
        .andExpect(status().is3xxRedirection());

    verify(loginAbuseGuard).recordFailure(
            "alice@example.vn", "203.0.113.10");
}
~~~

The second test assumes the failure handler redirects back to the login page. If the application enforces CSRF on form login, the test must include a valid CSRF token so the request reaches the rate limiter/authentication filter. `ClientIpResolver` in tests should be configured deterministically rather than trusting arbitrary `X-Forwarded-For` headers.

Beyond MockMvc, add integration tests for Redis atomicity, TTL expiration, multi-pod consistency, timing distributions, and reset/MFA/device verification endpoints. Never rely solely on a filter unit test to claim protection against distributed credential stuffing.

## 12. Troubleshooting and Production Checklist

| Symptom | Possible cause | Resolution |
|---|---|---|
| Attackers bypass rate limits using multiple IPs | Rate limiting by IP only | Add an independent account bucket |
| One IP tries thousands of usernames | Only using an IP+username bucket | Add both an overall IP bucket and an account bucket |
| Legitimate users locked out by attackers | Hard account lockout with no recovery | Use progressive delays, step-up, and recovery paths |
| User enumeration despite identical messages | Differences in status, timing, redirects, or headers | Standardize responses and dummy hashing |
| Rate limits reset after pod restart | Counters stored in RAM | Use shared Redis/database store |
| One pod has different thresholds than another | Local state or config drift | Shared policy/configuration and atomic operations |
| Login is throttled but password reset is not | Only `/login` is protected | Inventory and protect all auth/recovery flows |
| Credential stuffing still succeeds | Valid credentials and no MFA/risk signals | MFA/passkeys, breached-password checks, anomaly detection |
| CAPTCHA is bypassed | Relying on CAPTCHA as sole defense | Combine multiple layers and behavioral monitoring |
| Wrong client secret locks user accounts | Shared user/client counter | Separate client authentication throttling |
| Device `user_code` values are guessed | Missing verification throttling | Rate-limit by IP/session plus TTL/code entropy |
| Forwarded IP is spoofed | Trusting `X-Forwarded-For` from any source | Trust only configured proxies |
| Metrics leak emails/usernames | Using raw identifiers as labels | HMAC pseudonymization and aggregate metrics |

### 12.1. Production Checklist

- [ ] Brute force, password spraying, credential stuffing, and enumeration are explicitly distinguished.
- [ ] Independent rate limits exist per account identifier and per IP.
- [ ] Composite IP+username keys are never used alone.
- [ ] Account identifiers are canonicalized per user lookup policy.
- [ ] Account/IP keys are pseudonymized and the HMAC secret is managed securely.
- [ ] Rate limiter uses an atomic shared store across instances.
- [ ] Token bucket/sliding window or equivalent algorithm with TTL is used.
- [ ] Policy uses progressive delays and limits hard lockouts to prevent DoS.
- [ ] Thresholds are tuned to traffic/risk; 100 attempts is not treated as a default.
- [ ] Throttling responses never reveal buckets or remaining attempts.
- [ ] Login, reset, recovery, MFA, device verification, and client authentication each have dedicated policies.
- [ ] Login/reset/registration never leak account existence via messages, statuses, or timing.
- [ ] Custom `AuthenticationProvider` handles timing consistently for nonexistent users.
- [ ] MFA/passkeys and risk-based step-up are enforced for sensitive accounts.
- [ ] New passwords are checked against breached/common password corpora.
- [ ] Webhooks/edge/IP reputation are not the sole defense layer.
- [ ] Client credential failures never increment user password counters.
- [ ] Authentication events feed monitoring without logging credentials.
- [ ] Audits contain no passwords, OTPs, recovery codes, tokens, or secrets.
- [ ] Alerts exist for one-account-many-IPs, one-IP-many-accounts, and distributed patterns.
- [ ] Incident playbooks exist for account/client compromise and session/token revocation.
- [ ] Tests cover multi-pod, concurrent requests, enumeration timing, and recovery flows.

**Self-Assessment Questions**

1. How do brute force, password spraying, and credential stuffing differ?
2. Why is account enumeration typically a precursor to credential attacks?
3. Why is IP-only rate limiting insufficient?
4. Why can a bucket keyed solely on `IP+username` be bypassed?
5. How must canonicalized account identifiers be normalized to create stable buckets?
6. Why should usernames be HMAC-hashed before storing in Redis keys or metrics?
7. How do token buckets and sliding windows differ from fixed windows?
8. Why can hard account lockouts become a denial-of-service vector?
9. What does the 100-attempt cap in NIST SP 800-63B-4 signify?
10. Which Spring Security filter position can enforce rate limits before password authentication?
11. Why is `AuthenticationFailureHandler` better suited for capturing request context than plain authentication events?
12. What are `AuthenticationFailureBadCredentialsEvent` and `AuthenticationSuccessEvent` useful for?
13. Why must nonexistent users be processed with timing similar to wrong passwords?
14. How do you keep responses generic for password reset and account recovery?
15. How do MFA and passkeys defend against credential stuffing?
16. When should step-up MFA or CAPTCHA be required?
17. Why should CAPTCHA never be the sole defense layer?
18. Which requests must be rate-limited in Device Verification?
19. Why do client secret failures require a separate bucket from user password failures?
20. Which metrics should be monitored to detect password spraying and credential stuffing?

## References

- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): generic authentication responses, timing discrepancies, login throttling, account lockout, CAPTCHA, and MFA.
- [OWASP Credential Stuffing Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html): MFA, leaked-password detection, IP/device signals, CAPTCHA, and defense-in-depth.
- [OWASP Bot Management and Anti-Automation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Bot_Management_and_Anti-Automation_Cheat_Sheet.html): per-account/IP rate limiting, token bucket/sliding window, risk signals, and privacy-aware fingerprinting.
- [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): protecting password recovery and preventing account enumeration.
- [NIST SP 800-63B-4 — Authentication and Authenticator Management](https://pages.nist.gov/800-63-4/sp800-63b.html): throttling, authenticator failure limits, MFA, and recovery.
- [Spring Security — Authentication Events](https://docs.spring.io/spring-security/reference/servlet/authentication/events.html): publishing and consuming authentication success and failure events.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): user lookup, password verification, and `PasswordEncoder`.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): adaptive one-way password hashing and `DelegatingPasswordEncoder`.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): client authentication and OAuth2/OIDC endpoint customization.
