# Do Not Let Response Content Reveal Account Existence or Lock State

**Module:** Spring Security – authentication. **Group:** Account State.

## 1. Why are "login failure messages" a security issue?

Look at two responses:

- User enters `an@example.com` with wrong password: **"Incorrect password"**.
- User enters `nonexistent@example.com`: **"Account not found"**.

Simply by trying many emails, an unauthenticated caller already learns which emails have accounts in the system. If responses also say **"Account locked"**, **"Email not verified"**, or **"Account disabled"**, an attacker learns not only whether an account exists, but also **the state of a specific identity**.

This is **account/user enumeration** and **account-state disclosure**. It facilitates:

- Credential stuffing: prioritizing usernames that genuinely exist alongside leaked passwords.
- Password spraying: trying one or a few common passwords against a verified list of accounts.
- Phishing: impersonating support while already knowing who is locked out or awaiting activation.
- Targeted attacks on high-value accounts, or harassing users via lock/reset flows.
- Inferring sensitive information about whether a person uses a product.

**Design goal:** For a **request without a trusted identity**, public responses for logins that **fail due to missing account, wrong password, lock, disablement, or expiration** should be standardized enough that external callers cannot distinguish these cases. At the same time, the system must still retain accurate root-cause information **internally** for incident handling, abuse prevention, and user support through verified channels.

**This does not mean:** every operation must return HTTP 200, every system error must be hidden, or account owners may never learn their account is locked. Deciding to reveal detailed status **after proving ownership/identity** is a separate, controlled flow.

## 2. Separating internal failures from external responses

In Spring Security, `AuthenticationManager`/`AuthenticationProvider` must identify the cause accurately enough to reject login:

| Internal condition | Typical exception/condition | Should it be exposed directly on public login? |
| --- | --- | --- |
| Non-existent username | `UsernameNotFoundException` in `UserDetailsService`; `DaoAuthenticationProvider` usually converts to `BadCredentialsException` | **No** |
| Wrong password | `BadCredentialsException` | **No** |
| Account locked | `LockedException` | **No** |
| Account disabled | `DisabledException` | **No** |
| Account expired | `AccountExpiredException` | **No** |
| Password/credentials expired | `CredentialsExpiredException` | **No** on public login; use a verified password-change flow |
| Provider/configuration problem | `AuthenticationServiceException`, `InternalAuthenticationServiceException`, or infrastructure error | Do not leak infrastructure details; audit and return appropriate operational error |
| Authenticated user lacking permission | `AccessDeniedException` / authorization decision | This is **authorization**, not a login failure cause |

For example, **the exact same public response** for identity/credential auth failures:

~~~json
{
  "code": "AUTHENTICATION_FAILED",
  "message": "Login failed. Please check your details or use support."
}
~~~

Internally you still distinguish:

~~~text
internal_reason=BAD_CREDENTIALS
internal_reason=LOCKED
internal_reason=DISABLED
internal_reason=CREDENTIALS_EXPIRED
~~~

These `internal_reason` values are **not** fields sent to unauthenticated browsers or API clients. Never put exception class names, account existence, or `locked=true` flags into response bodies, URLs, headers, GraphQL extensions, or client error codes.

### Standardize the entire "response contract"

It is not just the UI text. An attacker can observe:

1. **HTTP status**: `401` for wrong username vs. `423 Locked` for a locked account is a disclosure channel.
2. **Body**: message, code, JSON schema, field count, response length, differing HTML.
3. **Redirect/URL**: `/login?error=wrong_password` vs. `/login?error=account_locked`.
4. **Header/cookie**: `X-Account-Status: disabled`, `Retry-After` present only for existing accounts, differing `Set-Cookie`.
5. **Timing**: real usernames run BCrypt while missing usernames return immediately; or locked accounts are rejected before password checks.
6. **Observable side effects**: emails, SMS, CAPTCHAs, temporary locks, differing rate-limit rates, reset flows, or distinct notifications.
7. **Other server outputs**: WebSocket/SSE, GraphQL error paths, public logs, monitoring endpoints, support pages.

Therefore, you cannot claim "enumeration is prevented" merely because the text message looks identical.

## 3. OWASP generic response principles

A common strategy for **public login** is:

~~~text
Username not found ─┐
Wrong password     ─┤
Account locked     ─┼─> SAME status + body + key headers
Account disabled   ─┤        for this auth failure group
Account expired    ─┘
~~~

Example for an API:

- HTTP: `401 Unauthorized` when login credentials are invalid or the account cannot authenticate.
- Body: same `AUTHENTICATION_FAILED` and generic message, without returning username or exception.
- Login-error-related headers: carry no account status.
- Cache: `Cache-Control: no-store` so responses containing session data or login details are not cached.

With **form login** using redirects, you can choose **the same `/login?error` URL** for these error types. REST APIs typically return JSON; whichever protocol you choose, stay **consistent** within that protocol rather than forcing forms and JSON to share identical status codes.

**Distinguishing from success:** Successful login must obviously differ from failed login, because the client needs a session/token issued. The goal is not to hide that a **valid** username/password pair can log in, but to stop callers lacking valid credentials from distinguishing **failure reasons**.

**Regarding 429/rate limits:** You may return `429 Too Many Requests` when throttling under anti-abuse policy. However, thresholds, response timing, and limit headers **must not become an oracle** revealing whether a username exists. A counter that increments only when a username exists is a dangerous design.

## 4. Why doesn't Spring Security solve everything with default configuration?

### 4.1. `hideUserNotFoundExceptions`

`AbstractUserDetailsAuthenticationProvider` is the base class of `DaoAuthenticationProvider`. Its property:

~~~java
// In provider config code; illustrative, not a standalone class.
daoAuthenticationProvider.setHideUserNotFoundExceptions(true);
~~~

In Spring Security 6.5, the default value is **`true`**:

- `UserDetailsService` throws `UsernameNotFoundException` → provider converts it to `BadCredentialsException`;
- Wrong password → `BadCredentialsException`.

This hides the difference between **"no user" and "wrong password"** at the exception type level callers typically observe.

**Yet this is only one layer of defense:**

- `LockedException` and `DisabledException` can still be thrown by account-status checks.
- Processing order/speed for real, missing, or locked accounts may differ.
- A custom failure handler can accidentally return `exception.getMessage()` to the client.
- Custom provider/LDAP/OIDC/OTP configurations do not necessarily follow this exact mapping.
- `hideUserNotFoundExceptions=true` does not automatically standardize signup, password reset, password recovery, HTTP headers, or rate limits.

**Do not set `setHideUserNotFoundExceptions(false)` just to show "username does not exist" on public login**. Spring Security considers distinguishing missing-user errors that way less secure.

### 4.2. UserDetails flags and internal exceptions

`UserDetails` has the flags:

~~~java
boolean isEnabled();
boolean isAccountNonLocked();
boolean isAccountNonExpired();
boolean isCredentialsNonExpired();
~~~

These flags reflect account policy in the user store. `DaoAuthenticationProvider` and appropriate checkers use them to decide login. **They are not data a public login form is allowed to announce.**

An account with the right password yet `isAccountNonLocked() == false` must still be rejected. Conversely, hiding the text "account locked" **does not mean skipping the lock check**. Security logic stays intact; only **the external response channel** avoids distinguishing sensitive causes.

### 4.3. Which exceptions are already handled by Spring Security before controllers?

With **Spring Security Servlet**, `UsernamePasswordAuthenticationFilter`/`AbstractAuthenticationProcessingFilter` normally catches `AuthenticationException`, invokes `AuthenticationFailureHandler`, and clears any unsuccessful context in the filter flow.

Consequently, merely adding `@ControllerAdvice @ExceptionHandler(AuthenticationException.class)` **does not guarantee** control over login failures already caught and handled by security filters. Configure the **failure handler on the right filter/chain**.

Conversely, a REST controller that calls `AuthenticationManager.authenticate(...)` directly can handle exceptions in the controller/service, yet must preserve `SecurityContext` management, session strategy, CSRF, rate limiting, and appropriate success/failure policies. Do not hand-roll a custom login endpoint solely to alter an error message.

## 5. Two-channel architecture: safe responses and internal diagnostics

~~~text
        POST /login (public, unverified)
                        |
                        v
           Auth filter / API boundary
                        |
                        v
             AuthenticationManager
                        |
             +----------+-----------+
             |                      |
          SUCCESS                FAILURE
             |                      |
             v                      v
       Session/token        AuthenticationException
             |                      |
             v             +--------+--------+
       Login success       |                 |
                           v                 v
                     Internal audit     Public mapper
                    reason/category     fixed failure
                    actor? trace id     status/body/header
                    rate-limit event         |
                           |                 v
                           v           Client/browser
                     Security metrics
                     alerts/support
~~~

**Auditing and the public mapper have distinct responsibilities:**

- **Public mapper:** receives internal errors and produces a generic, consistent, non-disclosing response. Must cover all statuses, bodies, headers, and redirects.
- **Audit:** records structured reasons, request IDs, and variables needed for investigation/metrics. Accessible only to authorized personnel; restrict personal data, retention, and viewing permissions.
- **Rate limiter:** curbs username probing and credential stuffing/spraying even when responses are already generic.
- **Recovery/step-up:** lets legitimate users prove ownership before receiving specific guidance on locks, disablement, or resets.

In auditing, logging the full `Authentication`, passwords, or tokens is never "needed for debugging." Do not log `exception` automatically if stack traces or causes might carry sensitive data from custom providers; enforce a logging/sanitization policy.

## 6. Runnable Java 17 demo: four failure causes, one public response

This demo uses **Spring Security Core 6.5.11** with `InMemoryUserDetailsManager`, `DaoAuthenticationProvider`, and `ProviderManager`. We create:

- An account that can log in, submitting a **wrong password**.
- A **non-existent** username.
- A **locked** account.
- A **disabled** account.
- A **successfully authenticating** account as control.

Internal exceptions are **counted by class in program memory**, while `PublicResponse` carries only a generic status/message. The demo runs no web server; it illustrates the exact boundary a web app should apply inside its failure handler.

### 6.1. Directory structure

~~~text
login-privacy/
├── build.gradle
└── src/main/java/example/LoginPrivacyDemo.java
~~~

**File `build.gradle`:**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'example.LoginPrivacyDemo'
}
~~~

**File `src/main/java/example/LoginPrivacyDemo.java`:**

~~~java
package example;

import java.util.HashMap;
import java.util.Map;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public final class LoginPrivacyDemo {

    record PublicResponse(int status, String body) {}

    private static final PublicResponse PUBLIC_FAILURE =
            new PublicResponse(401, "Login failed.");

    private static final PublicResponse PUBLIC_SUCCESS =
            new PublicResponse(200, "Login succeeded.");

    private static PublicResponse attempt(
            AuthenticationManager manager,
            String username,
            String rawPassword,
            Map<String, Integer> internalAuditCounts) {

        try {
            Authentication result = manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            username, rawPassword
                    )
            );

            if (!result.isAuthenticated()) {
                // Defense in depth: never grant success if not authenticated.
                return PUBLIC_FAILURE;
            }

            return PUBLIC_SUCCESS;
        } catch (AuthenticationException exception) {
            // Record only counts by exception class internally.
            // Never log raw passwords, tokens, or account details.
            internalAuditCounts.merge(
                    exception.getClass().getSimpleName(), 1, Integer::sum
            );
            return PUBLIC_FAILURE;
        }
    }

    private static void show(
            String label, PublicResponse response) {
        System.out.println(label + ": status=" + response.status()
                + " body=" + response.body());
    }

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();

        UserDetails normal = User.withUsername("an")
                .password(encoder.encode("good-password"))
                .roles("USER")
                .build();

        UserDetails locked = User.withUsername("binh")
                .password(encoder.encode("locked-password"))
                .roles("USER")
                .accountLocked(true)
                .build();

        UserDetails disabled = User.withUsername("chi")
                .password(encoder.encode("disabled-password"))
                .roles("USER")
                .disabled(true)
                .build();

        InMemoryUserDetailsManager users =
                new InMemoryUserDetailsManager(normal, locked, disabled);

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        provider.setHideUserNotFoundExceptions(true);

        AuthenticationManager manager = new ProviderManager(provider);
        Map<String, Integer> auditCounts = new HashMap<>();

        PublicResponse wrongPassword = attempt(
                manager, "an", "wrong-password", auditCounts);
        PublicResponse unknown = attempt(
                manager, "not-registered", "anything", auditCounts);
        PublicResponse lockedAccount = attempt(
                manager, "binh", "locked-password", auditCounts);
        PublicResponse disabledAccount = attempt(
                manager, "chi", "disabled-password", auditCounts);
        PublicResponse valid = attempt(
                manager, "an", "good-password", auditCounts);

        // Public side: cannot tell why authentication failed.
        show("wrongPassword", wrongPassword);
        show("unknownUser", unknown);
        show("lockedUser", lockedAccount);
        show("disabledUser", disabledAccount);
        show("validUser", valid);

        System.out.println("failuresEqual="
                + wrongPassword.equals(unknown)
                + "," + unknown.equals(lockedAccount)
                + "," + lockedAccount.equals(disabledAccount));

        // Illustrates INTERNAL metrics only, not HTTP responses.
        System.out.println("internal.badCredentials="
                + auditCounts.getOrDefault(
                        "BadCredentialsException", 0));
        System.out.println("internal.locked="
                + auditCounts.getOrDefault("LockedException", 0));
        System.out.println("internal.disabled="
                + auditCounts.getOrDefault("DisabledException", 0));
    }
}
~~~

**Run** in `login-privacy`, with JDK 17+ and compatible Gradle:

~~~bash
gradle -q run
~~~

If your project has a Gradle Wrapper, use `./gradlew -q run`; on Windows use `gradlew.bat -q run`. Network access may be needed on the first run to download dependencies from Maven Central.

**Stdout printed by the program itself** (excluding any Gradle or library logs if configured):

~~~text
wrongPassword: status=401 body=Login failed.
unknownUser: status=401 body=Login failed.
lockedUser: status=401 body=Login failed.
disabledUser: status=401 body=Login failed.
validUser: status=200 body=Login succeeded.
failuresEqual=true,true,true
internal.badCredentials=2
internal.locked=1
internal.disabled=1
~~~

### 6.2. Reading the results accurately

- `wrongPassword` and `unknownUser` both map to `BadCredentialsException`, because `hideUserNotFoundExceptions=true`; this hides differences at the provider error-type level.
- `lockedUser` raises `LockedException`; `disabledUser` raises `DisabledException` from account status checks. **Internally you can still distinguish** both reasons.
- `failuresEqual=true,true,true` only proves **the demo's `PublicResponse` status/body match**. It does not prove network timing, headers, or side effects are identical; web apps must test further.
- The `internal.*` lines are **in-process metrics**, solely for understanding root causes. Never send them in JSON, response headers, redirect parameters, or unverified UIs.
- `validUser` differs from failures because credentials and account state are valid; the demo creates no real HTTP session or token.

**Security:** Demo passwords are fake samples for learning. Real apps use proper secrets, password policies, TLS, session/CSRF protection, and rate limiting. Never expose exception class names to unauthenticated callers.

## 7. Spring Security Servlet integration: unified failure handler

With form login using `UsernamePasswordAuthenticationFilter`, the place to standardize responses is `AuthenticationFailureHandler`. The following is a **Spring Boot Servlet application config snippet**, not a standalone program. It intentionally chooses a **uniform JSON response** for login errors — suitable when AJAX clients call a form-encoded login endpoint; traditional redirect UIs can use a single shared `/login?error` URL instead.

~~~java
// Key imports in a Spring Boot Servlet app:
// org.springframework.context.annotation.Bean;
// org.springframework.security.web.SecurityFilterChain;
// org.springframework.security.web.authentication.AuthenticationFailureHandler;
// org.springframework.security.config.annotation.web.builders.HttpSecurity;
// org.springframework.security.config.Customizer;

@Bean
AuthenticationFailureHandler genericLoginFailureHandler() {
    return (request, response, exception) -> {
        // Optionally audit the exception server-side in protected logs.
        // DO NOT write exception.getMessage() to the client.

        response.setStatus(401);
        response.setCharacterEncoding("UTF-8");
        response.setContentType("application/json");
        response.setHeader("Cache-Control", "no-store");

        response.getWriter().write(
            "{\"code\":\"AUTHENTICATION_FAILED\","
          + "\"message\":\"Login failed.\"}"
        );
    };
}

@Bean
SecurityFilterChain webSecurity(
        HttpSecurity http,
        AuthenticationFailureHandler genericLoginFailureHandler)
        throws Exception {

    http.authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated());

    http.formLogin(form ->
            form.failureHandler(genericLoginFailureHandler));

    return http.build();
}
~~~

**Points to remember:**

1. `failureHandler` receives `AuthenticationException`; it can log internally (safely) yet **must not put `exception.getMessage()` or the subclass into the response**.
2. `http.formLogin(...)` handles the Servlet form-login flow, normally receiving form-encoded username/password parameters. This snippet does not define a REST JSON login filter and does not support "POST JSON" merely by returning a JSON `Content-Type`.
3. Returning `401` JSON suits clients of this flow if designed for it. If the app needs HTML redirects, all sensitive errors should go to **the same** `/login?error` page with the same generic message.
4. CSRF still requires proper handling: with browser sessions/cookies, a POST missing a CSRF token may get `403` **before authentication**. That is not an account-locked signal, and CSRF must not be disabled arbitrarily.
5. `SecurityFilterChain` can be configured with multiple chains, each with its own filters/entry points/failure handlers. Verify the exact chain actually handling `/login`; a handler in another chain will not protect this endpoint.
6. Logins using HTTP Basic, bearer tokens, OAuth2/OIDC, passkeys, or custom filters each have their own failure/entry points. The **generic public response** policy must be applied at each mechanism's boundary.

### If using only form redirects

A simple setup for HTML forms is:

~~~java
// ILLUSTRATIVE CODE: same URL for all auth errors on the login form.
http.formLogin(form -> form
        .failureUrl("/login?error"));
~~~

The application must ensure `/login` is accessible while unauthenticated and shows only generic text, **without** query parameters encoding detailed reasons. Never return `/login?locked=true` or `/login?user_exists=false`.

## 8. Custom APIs calling AuthenticationManager

If a controller genuinely calls `authenticationManager.authenticate(...)`, apply mapping at the HTTP boundary:

~~~java
// SKETCH CODE: not a standalone class.
// Apply only when AuthenticationManager + request DTO,
// security context/session strategy, and rate limiter are properly in place.
try {
    Authentication auth = authenticationManager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                    body.username(), body.password()
            )
    );

    // Handle success with a fully designed web mechanism.
} catch (AuthenticationException ex) {
    auditSafely(ex); // internal only, do not log credentials

    return ResponseEntity.status(401)
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                    "code", "AUTHENTICATION_FAILED",
                    "message", "Login failed."
            ));
}
~~~

Never use this snippet to replace `formLogin` while omitting session management, session fixation protection, CSRF, security context persistence, logout, failure throttling, and auditing. If your system has a custom endpoint, design the **entire** login lifecycle, not just a `try/catch` block.

`@ControllerAdvice` for controllers does not by default handle exceptions already caught by Spring Security filters. When writing tests, send requests through the **real security filter chain**, not just direct Java method calls.

## 9. "Forgot password" flows must also resist account enumeration

### 9.1. Safe messages

**Avoid:**

~~~text
This email is not registered in our system.
Reset email sent to account an@example.com.
This account is locked and cannot be reset.
~~~

**Prefer (for public requests):**

~~~text
If a matching account exists, we will send instructions to the registered contact channel.
~~~

The output **does not reveal whether the account exists**. `202 Accepted` can indicate the request was queued for processing, but only when the endpoint is designed asynchronously; do not use that status to promise an email was definitely sent.

### 9.2. Recommended architecture

~~~text
POST /forgot-password
       |
       v
Validate email syntax (identical for existing/missing accounts)
       |
       v
Rate limit / abuse detection independent of userExists
       |
       v
Return fixed public response
       |
       v
Internal processing queue
       |
       +-- If account is valid, issue random reset token
       |   with short TTL, one-time use, protected hash/ID storage
       |   and send via registered channel.
       |
       +-- If account does not exist, issue no token
           and reveal no difference over HTTP.
~~~

Queues and async processing reduce timing differences between "real email → send email" and "no user → return immediately." Still, check whether payload size, network paths, status codes, races, rate limits, or mail-sending failures create observable differences. A queue alone is never a complete timing solution.

### 9.3. Preventing abuse of recovery mechanisms

If someone can trigger thousands of reset emails, the system becomes a harassment tool. Limit by IP/device, risk signals, server-side HMAC-hashed identifiers, email send quotas, token lifetimes, auditing, and safe notifications to account owners.

When consuming a reset token, **that is a separate ownership-proof flow**; once the token is fully verified, the system can provide appropriate specific guidance. Never turn the initial email-entry page into an account-existence checker.

## 10. New registration can also expose accounts

A public signup API often returns:

~~~text
409 Conflict: Email already in use.
201 Created: Registration succeeded.
~~~

If an attacker only needs to know which emails are registered, this is an oracle. Depending on product requirements there may be UX trade-offs, yet you must **recognize and explicitly decide the risk**, rather than treating it as unrelated to security.

Ways to reduce leaks:

- Register by email and send an ownership verification flow; return a neutral response: "If the address is eligible, check your email to continue."
- Never reveal existing accounts when resending activation emails or invitations.
- Still enforce unique email/username constraints in the database/identity service and handle concurrent requests; generic responses **do not replace unique constraints**.
- Apply rate limiting and adaptive CAPTCHA/challenges as needed; test whether bots can infer accounts from captcha or timing differences.
- When business requirements force showing "email already exists" for UX, treat it as an **intentional disclosure decision**, paired with rate limiting, monitoring, and service sensitivity review.

Never treat an email verified on another system as proof that a caller is entitled to inspect account status in this product.

## 11. Account lockout, throttling, and denial-of-service risk

Account lockout defends against brute force, yet naive implementations create **two vulnerabilities**:

1. If the UI returns "account locked" for real users, attackers enumerate states.
2. If a few wrong logins can permanently lock a username, attackers can deliberately lock other people's accounts (**account lockout DoS**).

Practical policies should consider:

- Multi-signal rate limiting: IP/device, network origin, canonicalized username or HMAC key, session, anomalous behavior. Do not rely on IP alone behind NAT/proxies; never trust `X-Forwarded-For` from untrusted clients.
- Progressive slowdown / adaptive delays / challenges / risk scoring on repeated failures; bound hashing work to prevent resource exhaustion.
- If using account lockout, prefer temporary locks with reasonable durations and proper recovery channels; tune by account tier.
- **Keep identical public responses for locked/disabled/unknown**; rate limits and captchas must not trigger observably only for real usernames.
- Notify account owners via **verified channels** on suspicious logins/locks, while curbing spam and avoiding creating a login feedback oracle.
- Never leak exception stack traces or detailed counters via GraphQL errors, public metrics endpoints, or WebSockets.

**HTTP 429** may be necessary when exceeding rate limits; if clients receive `429` only after trying a real username, it remains a side channel. Test both **"check username exists → limit"** and **"rate-limit before querying account"** orderings.

## 12. Timing: identical content can still be probed

Naive backend example:

~~~java
// UNSAFE SKETCH CODE.
UserDetails user = users.find(username);

if (user == null) {
    return genericFailure(); // very fast
}

if (!passwordEncoder.matches(rawPassword, user.getPassword())) {
    return genericFailure(); // BCrypt takes longer
}
~~~

Both branches return identical text, yet average latency differs. Attackers can send many samples to estimate timing distributions, especially with weak rate limits.

### Multi-layered defense approach

1. **Use standard providers** instead of writing custom password handlers unnecessarily. `DaoAuthenticationProvider` handles credential verification and user-not-found masking within its scope; still, never claim every branch is strictly constant-time.
2. When building a custom password provider, implement **dummy password-hash verification** for non-existent usernames if appropriate, using a hash configured with the same algorithm/cost. Never allow dummy users to log in, and ensure non-existent usernames always fail.
3. Never return raw exception messages or types; standardize statuses, bodies, and related headers.
4. Consider async handling for resets and email notifications to remove mail-sending latency from HTTP response paths.
5. Use rate limiting, threat detection, and monitoring to curb large-scale timing-sample harvesting.
6. Measure **latency distributions per case group** under realistic load; never rely on single-run measurements.
7. Never add a fixed `Thread.sleep(500)` and claim timing oracles are eliminated. Network jitter, DB branches, caches, status checks, rate limiters, and CPU still create differences; random sleeps can even increase load without solving anything.

**Note:** Some providers check locked/disabled state **before** password verification, so latencies may differ. Better protection requires realistic threat modeling and testing at external system boundaries. Never tamper with account-status checks to "equalize timing" in ways that accidentally allow invalid logins.

## 13. Notifying real users without leaking to strangers

Generic responses are often less convenient than "account is locked." You can balance them:

- **Public login screen:** "Login failed. Check your details or contact support."
- **Recovery email:** send instructions to the **previously verified** address without stating over HTTP whether an email was sent.
- **Inside an authenticated session:** show status notices or guidance when session trust permits; check for scenarios where old sessions might be hijacked.
- **After step-up** (MFA, recovery code, one-time link, identity verification): provide the specific reason or unlock workflow per policy.
- **Support teams:** follow an identity/authorization verification process for callers before viewing or disclosing account status.

Never return "account is locked" immediately when a client enters a valid email because **knowing an email is not proof of owning it**.

When using neutral wording, still maintain accessibility and guide users to actionable next steps: such as "Forgot password?" or "Contact support" links rather than dead-end vague messages.

## 14. Safe auditing and attack observability

A structured internal event, for example:

~~~json
{
  "event": "authentication_failed",
  "reason": "ACCOUNT_LOCKED",
  "request_id": "req_example",
  "source_group": "network-risk-bucket",
  "occurred_at": "2026-11-05T00:00:00Z"
}
~~~

**Internal illustrative JSON only**, never a public response. Timestamps/IDs are synthetic; contains no raw usernames, passwords, bearer tokens, or cookies. If per-user tracking is needed for abuse prevention, use internal identifiers/pseudonyms with retention and access policies; a keyed HMAC digest can group events while limiting raw username exposure, though it does not render data harmless.

Audits typically track:

| Metric/event | Purpose |
| --- | --- |
| Count of `authentication_failed` by reason group | Detect brute force, credential stuffing, or misconfiguration |
| Count rejected due to locked/disabled | Monitor policy, assist owners via verified channels |
| `forgot-password` request counts and mail quotas | Detect abuse/recovery spam |
| Response-time differences across failure groups | Detect timing oracles |
| `429` and challenge frequencies | Measure rate-limiting effectiveness and risks |
| Username probing from anomalous origins | Detect distributed enumeration |
| Error rates by filter chain/API version | Avoid missing endpoints lacking unified policy |

Never grant unauthenticated users access to metrics or logs holding detailed reasons. In multi-node systems, use correlation/request IDs, control clock accuracy, and keep credentials out of tracing baggage.

## 15. API testing: a complete response matrix

### 15.1. Prepare distinct fixtures

Prepare users in these states:

1. **Non-existent** username.
2. Existing username, **wrong password**.
3. **Locked** account.
4. **Disabled** account.
5. **Expired** account.
6. **Expired** credentials.
7. Normal account with **valid credentials**.

For each failure case, send requests through **the same endpoint**, protocol, and rate-limit/challenge setup barring explicitly accepted differences, then check:

| Property | Expectation for sensitive failure group |
| --- | --- |
| Status | Same status on the same endpoint; e.g., `401` |
| `Content-Type` | Same media type/charset |
| JSON/HTML body | Same schema, code, and generic text |
| Redirect URL | Same URL, no query parameter encoding reason |
| Headers | No account-state markers/usernames; equivalent headers |
| Cookies | No authenticated session issued; no distinction for existing users |
| Timing | No exploitable variance in distribution tests under equivalent load/conditions |
| Rate-limit | Creates no oracle based on existing usernames |
| Reset/signup | No "found/not found" signal across public observable layers |
| Internal | Audit logs exact reason, without exposing to client |
| Success | Only valid credentials + eligible account can log in |

### 15.2. Integration test example (illustrative)

The snippet below **does not run standalone**, as it depends on `MockMvc`, security config, seeded users, fake clock, and project endpoints. It expresses the contract to verify:

~~~java
// PSEUDO-TEST in a Spring Boot integration test; not standalone.
var wrongPassword = login("an", "bad");
var unknownUser = login("nonexistent", "bad");
var locked = login("binh", "any");
var disabled = login("chi", "any");

assertThat(wrongPassword.getStatus()).isEqualTo(401);
assertThat(unknownUser.getStatus()).isEqualTo(401);
assertThat(locked.getStatus()).isEqualTo(401);
assertThat(disabled.getStatus()).isEqualTo(401);

assertThat(unknownUser.getContentAsString())
        .isEqualTo(wrongPassword.getContentAsString());
assertThat(locked.getContentAsString())
        .isEqualTo(wrongPassword.getContentAsString());
assertThat(disabled.getContentAsString())
        .isEqualTo(wrongPassword.getContentAsString());

// Also verify headers, redirects, cookies, rate limits,
// responses for expired account/credentials expired, and timing.
~~~

Run tests through the **real `SecurityFilterChain`** using `MockMvc` or end-to-end HTTP tests, rather than calling Java failure mappers directly. With multiple chains, tenants, or locales, test all variants. In distributed systems, measure timing and responses from the point an attacker actually observes, not only in local unit tests.

### 15.3. Meaningful performance/timing tests

Choose an appropriate sample size and compare **distributions** of latency across non-existent username, wrong password, locked, and disabled under equivalent cache/warmup/DB conditions. Bound load and run only in authorized environments, avoiding production attack traffic. Never claim "constant-time" from an average of a few requests.

Check compressed `Content-Length`, `Retry-After` headers, cookies, `302 Location`, email side effects, and responses on backend timeouts. Specifically test cache misses, reset background workers, DB errors, and rate limits.

## 16. Common implementation mistakes

| Mistake | Why it is exploitable | Fix |
| --- | --- | --- |
| `return ex.getMessage()` in failure handler | Leaks "User account is locked" / "User is disabled" | Return fixed generic string, audit separately |
| Catching `BadCredentialsException` but not `LockedException` | Locked takes a different response path | Standardize the entire `AuthenticationException` family per threat model |
| `hideUserNotFoundExceptions=false` on public login | Exposes missing-username exception class | Keep default true and standardize boundary |
| Returning `404` for missing username, `401` for wrong password | HTTP status becomes an account oracle | Use the same status across the failure group |
| Using `/login?locked=true` | URL/redirect discloses state | Use generic `/login?error` |
| Adding `X-Reason` or GraphQL extension reason | Clients read metadata even when text matches | Never expose reasons in any public field |
| Missing username → skip BCrypt; real user → BCrypt | Timing discrepancy | Standard provider, dummy check if custom, rate limits, and measurement |
| Captcha appears only for real usernames | Challenge becomes an account oracle | Use risk policy that does not leak existence |
| Password reset returns "Email does not exist" | Enumerates accounts via public API | Return neutral receipt and process in backend |
| Rate-limiting only when `userExists=true` | `429` differs by username | Rate-limit before lookup or by non-disclosing signals |
| Signup returns `409` for real accounts in sensitive services | Signup becomes an oracle | Consider email verification + generic response |
| Permanent account lock after a few wrong tries | Adversaries lock users en masse (DoS) | Bounded lockout, adaptive throttling/recovery |
| Returning `200 OK` for all infrastructure errors | Masks system outages and breaks client semantics | Distinguish operational errors safely without leaking account causes |
| `@ControllerAdvice` while filter uses another handler | Handler is never called | Configure the right `SecurityFilterChain`/filter |
| Logging/returning passwords in debug responses | Leaks credentials/PII | Controlled internal audits, never expose secrets |
| Testing only message equality | Status/headers/timing still differ | Test entire contract + side effects |
| Trusting roles/account state from client | Allows bypassing policy | Provider checks state from trusted source |

**Never "fix" enumeration by allowing locked or disabled accounts to log in.** Lock enforcement must stay strict; only public responses are standardized.

## 17. Differences across authentication mechanisms

| Mechanism | Easy-to-leak points to guard |
| --- | --- |
| Servlet `formLogin` | `AuthenticationFailureHandler`, redirect URLs, login page, CSRF, and sessions |
| HTTP Basic | `AuthenticationEntryPoint` / `WWW-Authenticate`, status, and error messages |
| Custom REST JSON login | Custom controller/filter, exception mapper, and context persistence |
| OAuth2/OIDC login | IdP may return distinct error codes; callback mapping and IdP contract, do not leak account-linking state |
| Password reset/activation | Request endpoint, email/SMS side effects, token validation, and rate limits |
| OTP/MFA | Never tell anonymous callers "this user has not enabled MFA" when sensitive; keep verified per-state policy |
| Bearer Resource Server | Distinguish invalid/expired tokens from missing permissions per protocol; do not attach internal account states arbitrarily |
| WebFlux | `ServerAuthenticationFailureHandler` / WebFilter and reactive context; do not copy Servlet config verbatim |

Do not force every case into `AUTHENTICATION_FAILED` JSON in ways that **break protocol standards**, such as mandatory HTTP challenges or OAuth/OIDC responses. The goal is not exposing **account existence/status** beyond what the protocol genuinely requires.

## 18. Pre-production review checklist

1. **Threat model:** list login, signup, reset, unlock, resend activation, SSO callbacks, and identity-related APIs.
2. **User state:** ensure locked/disabled/expired are genuinely rejected; never weaken authentication to unify responses.
3. **Generic public mapping:** policy covers status/body/error code/redirect/header for all sensitive auth failures.
4. **Spring Security:** verify `hideUserNotFoundExceptions=true` on username/password providers and proper failure handler on the active chain.
5. **No public `ex.getMessage()`:** responses contain no exception types, stack traces, or internal reasons.
6. **Timing:** consider hash costs, dummy verification in custom providers, async resets, and latency distributions; never promise absolute constant-time.
7. **Abuse prevention:** rate limiting/adaptive defenses, avoiding per-account lockout DoS and CAPTCHA oracles.
8. **Recovery:** generic response for anonymous users; provide specific status/guidance only after ownership verification.
9. **Auditing:** internal reasons/metrics for support, access-controlled, with zero credentials.
10. **Regression tests:** compare public responses for unknown/bad/locked/disabled/expired across JSON, HTML, statuses, headers, redirects, and cookies.
11. **Distributed operations:** load balancers, caches, IdPs, email queues, replicas, and error paths create no obvious observable discrepancies.
12. **Documentation:** specify when UX intentionally discloses account existence, who approved it, and compensating controls.
13. **Sensitive accounts:** admin/privileged/recovery accounts apply risk-appropriate rate limits, MFA, and alerts.
14. **Accessibility:** generic messages still point toward verified recovery/support rather than stranding legitimate users.

## 19. Self-check questions

**1.** Two login branches both return "Login failed," yet non-existent usernames return HTTP 404 and locked accounts return HTTP 423. Is enumeration prevented?  
**Answer:** No. Status codes are an observation channel; the response contract must be standardized across the sensitive failure group.

**2.** Why is `setHideUserNotFoundExceptions(true)` insufficient to hide locked accounts?  
**Answer:** It handles only `UsernameNotFoundException`; `LockedException`/`DisabledException` can still be raised and exposed by the failure handler unless standardized.

**3.** Should `exception.getMessage()` be used as the login UI message?  
**Answer:** No. Exception messages are technical details that can reveal locks, disablement, providers, or internals; the public mapper must pick dedicated generic text.

**4.** A user enters an email in "Forgot password," and the API returns "Email not found." What is the risk?  
**Answer:** The endpoint turns into an account-enumeration oracle. Return a neutral message and send instructions via the verified channel when eligible.

**5.** A form has identical generic text and status, yet real usernames take 200 ms while missing usernames take 3 ms. What is the risk?  
**Answer:** A timing side channel. Reduce discrepancies systematically with testing and rate limiting, rather than merely adding sleep.

**6.** Why shouldn't every wrong attempt immediately lock an account indefinitely?  
**Answer:** Attackers can intentionally lock out other people's accounts; use appropriate throttling/lockout and recovery policies.

**7.** After someone completes email/step-up verification, can they be given specific unlock instructions?  
**Answer:** Yes, if identity/authorization verification meets the risk level. Do not confuse that with public login where only a username was entered.

**8.** Is a unit test checking that `failureMapper(BadCredentialsException)` returns a generic message enough?  
**Answer:** No. You also need to test Locked/Disabled/Expired, the real filter chain, headers/statuses/redirects, timing, and other reset/signup APIs.

**9.** Does "internal audit records `reason=LOCKED`" contradict anti-enumeration?  
**Answer:** No, provided the audit is never exposed to unverified callers, is access-controlled, and logs no sensitive credentials.

## 20. Official references

- [OWASP Authentication Cheat Sheet – Authentication and Error Messages](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#authentication-and-error-messages): generic errors, timing, and account-existence disclosure channels.
- [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): consistent messaging and recovery workflows.
- [OWASP Credential Stuffing Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html): preventing automated attacks, rate limiting, and adaptive defenses.
- [Spring Security 6.5 – AbstractUserDetailsAuthenticationProvider Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html): `hideUserNotFoundExceptions` and account checks.
- [Spring Security 6.5 – Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationManager`/`AuthenticationProvider` and `AuthenticationException` types.
- [Spring Security 6.5 – AuthenticationFailureHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AuthenticationFailureHandler.html): handling authentication failures in filters.
- [Spring Security 6.5 – UsernamePasswordAuthenticationFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/UsernamePasswordAuthenticationFilter.html): form login.
- [Spring Security 6.5 – UserDetails API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetails.html): locked, enabled, account expired, and credentials expired.

**Summary:** The system must **verify and reject accurately by account status internally**, while **never letting unverified callers distinguish those states through public responses**. Matching wording alone is not enough: verify HTTP statuses, JSON, headers, URLs, timing, rate limits, recovery, and exception flows; disclose status details only after appropriate proof of ownership.
