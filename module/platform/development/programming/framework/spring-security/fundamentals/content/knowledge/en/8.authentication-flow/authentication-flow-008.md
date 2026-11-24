# Handling Authentication Failures Without Revealing Account Existence

## 1. The Problem: Login Error Messages Can Leak the User List

Suppose a system has a POST /login endpoint or an API protected by HTTP Basic. An attacker does not yet know the password, yet wants to check whether the account **alice@example.com** exists in the system.

Both responses below are login errors, yet they leak very different amounts of information:

~~~text
Non-existent username            -> "Account not found"
Existing username, wrong password -> "Incorrect password"
~~~

Simply by trying many usernames, an outsider can build a list of real accounts. Afterward, they can use that list for **credential stuffing, password spraying, targeted phishing, password reset attacks**, or probing administrative accounts.

Even when both cases show a single line "Invalid username or password", an application can still reveal account existence through **HTTP status, redirects, URLs, headers, response size, processing time, rate limits, email notifications**, or account lockout behavior.

**Goal:** Handle failures so that an **unauthenticated** caller cannot distinguish "username does not exist", "username exists yet password is wrong", "account is locked", or "account is disabled" from the responses they observe, within the bounds of the designed threat model.

Examples use **Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x, Spring MVC/Servlet** to explain the APIs. These versions are chosen for learning context; some Spring Security 6.3 releases have a timing security advisory noted in section 8—**do not use versions with known vulnerabilities in production**.

### What you will learn

1. What user enumeration is and where information leaks hide.
2. Distinguish AuthenticationException, UsernameNotFoundException, BadCredentialsException, LockedException, and DisabledException.
3. Why raw internal exceptions must never become public messages or statuses.
4. How DaoAuthenticationProvider hides differences between missing usernames and wrong passwords by default.
5. Why a single error message alone is not enough to stop timing side channels.
6. Build an HTTP Basic API returning the exact same status code and JSON for failed authentication cases.
7. Write MockMvc tests for the public error contract and understand the limits of those tests.
8. Apply the same principles to form login, password reset, registration, OTP codes, and locked accounts.
9. Design rate limiting, logging, and user support without creating new information-disclosure channels.

## 2. Which Vulnerability Class Is User Enumeration?

**User enumeration** is the ability to infer whether an identifier (username/email/phone number/account ID) exists in the system from responses of accessible features without proving ownership of the account.

It does not mean the attacker has logged in. However, knowing which accounts are real **shrinks the search space and raises the effectiveness of subsequent attacks**.

API example:

~~~http
POST /login HTTP/1.1
Content-Type: application/json

{"username":"alice","password":"wrong"}
~~~

The response **must not** state that alice exists yet the password is wrong, nor return an internal identifier or account status. For equivalent invalid login requests, the public interface should return a generic error such as:

~~~json
{
  "error": "invalid_credentials"
}
~~~

A web application can display a short message to users: **"Unable to sign in with the provided credentials."** The wording reveals neither whether the username exists, nor whether the password failed, nor whether the account is locked or active.

### 2.1. Possible leakage channels

| Observation channel | Unsafe response | Design direction |
| --- | --- | --- |
| Displayed message | "Email does not exist" vs. "Wrong password" | One generic error for failed authentication |
| HTTP status | Unknown user 404, wrong password 401 | Same status for equivalent login failures |
| JSON body | Returning enum USER_NOT_FOUND, LOCKED | One public error code; keep details internal |
| Redirect | /login?not-found vs. /login?bad-password | Same login failure URL or flow |
| Response headers | X-Account-Exists: true | Never put account state into headers |
| Response size | Existing-user error page much longer | Same template and response structure |
| Processing time | Missing user returns immediately; existing runs BCrypt | Avoid early exit; use patched provider/version with proper mitigation |
| Rate limit/lockout | Real user quickly locks, fake user shows no change | Anti-abuse design that does not turn account existence into a signal |
| Password reset | "Email sent" only when email exists | Generic reply for syntactically valid requests |
| Registration | "Email already exists" from public endpoint | Use verification/registration workflow limiting enumeration per product needs |
| OTP/resend code | "Phone number not registered" | Generic response; perform code dispatch only on backend |
| Public logs/analytics | Returning raw exceptions in client-visible response/logs | Separate internal reason from public contract |

A system that changes only the wording while leaving differing status codes or sharply differing response times can still leak accounts.

### 2.2. You do not always have to hide every state

Once someone has **verified account ownership** and passed the appropriate authentication step, the system can show more specific guidance such as password-change prompts, expired accounts, or safe recovery options. Never confuse user-support needs with telling an **unauthenticated caller** whether an arbitrary username exists.

In what follows, "unifying errors" applies primarily to **login interfaces and public recovery features**. When an already-logged-in user calls an unauthorized endpoint, HTTP 403 is an authorization branch distinct from a 401 login failure.

## 3. Authentication Flow and Where Errors Should Be Normalized

In Spring Security Servlet, a username/password request normally follows these steps:

~~~text
Client
  |
  | username/password
  v
BasicAuthenticationFilter or UsernamePasswordAuthenticationFilter
  |
  | unauthenticated UsernamePasswordAuthenticationToken
  v
AuthenticationManager / ProviderManager
  |
  v
DaoAuthenticationProvider
  |
  +-- UserDetailsService.loadUserByUsername(username)
  |      +-- User not found -> internal UsernameNotFoundException
  |
  +-- PasswordEncoder.matches(rawPassword, storedHash)
  |      +-- Wrong password -> BadCredentialsException
  |
  +-- Account status checks
  |      +-- Locked/disabled/expired -> corresponding AuthenticationException
  |
  +-- Success -> authenticated Authentication
  |
  +-- Failure -> AuthenticationException
                  |
                  v
Filter + AuthenticationEntryPoint or AuthenticationFailureHandler
                  |
                  v
HTTP 401/redirect + unified public error message
~~~

**Two layers to separate:**

- **Internal authentication layer** needs the exact reason for auditing, anti-abuse, user support, and monitoring.
- **Public response layer** should reveal only the outcome needed for the client to proceed or adjust input.

For instance, `UserDetailsService` may throw `UsernameNotFoundException` and the provider may encounter `DisabledException`. Yet those two exceptions **must not automatically produce two different bodies or two different error URLs** sent to an unauthenticated client.

### 3.1. Distinguishing filter, manager, and handler

| Component | Primary responsibility |
| --- | --- |
| Authentication filter | Reads credentials from the request and invokes AuthenticationManager |
| AuthenticationManager | Executes the authenticate contract or throws AuthenticationException |
| AuthenticationProvider | Verifies credentials/user state for a supported Authentication type |
| UserDetailsService | Loads account; does not compare passwords |
| PasswordEncoder | Checks raw password against hash |
| AuthenticationEntryPoint | Initiates authentication or responds to unauthenticated requests, e.g. HTTP Basic 401 |
| AuthenticationFailureHandler | Handles failure of interactive login mechanisms, typically form login |
| AccessDeniedHandler | Handles missing permissions for authenticated users, typically HTTP 403 |

AuthenticationManager **does not directly return HTTP 401 or redirects**. HTTP responses belong to the filter/handler layer. Normalizing responses at the proper boundary is usually far more maintainable than trying to hide every exception by modifying services or DAOs.

## 4. Common Failure Categories

| Scenario | Typical exception/outcome | What unauthenticated clients should see |
| --- | --- | --- |
| Username absent from store | UsernameNotFoundException, which the provider may translate to BadCredentialsException | Invalid login credentials |
| Username exists, wrong password | BadCredentialsException | Same generic error |
| Account locked | LockedException or corresponding state | Do not confirm account exists |
| Account disabled | DisabledException | Do not confirm account status |
| Account expired | AccountExpiredException | Do not distinguish from other login errors |
| Password/credentials expired | CredentialsExpiredException | Consider verified recovery flow |
| Token malformed/expired/invalid signature | Mechanism-specific OAuth2/Bearer exception | Do not return secret details or distinguish identities arbitrarily |
| Temporary DB/auth backend outage | InternalAuthenticationServiceException or system error | Generic system notice; never expose SQL/stack traces |
| IP/user exceeds attempt limit | 429/challenge/cooldown per policy | Same policy for unverified usernames |
| User logged in yet lacks role | AccessDeniedException | 403 per authorization, not login user enumeration |

**Do not treat every exception identically internally:** real system outages may need HTTP 503 and separate telemetry per operational policy; the goal is not using errors to reveal account existence. Never "swallow" a database outage and report "wrong password" in all cases, as that disrupts recovery and auditing.

### 4.1. When are 401 and 403 used?

In the HTTP Basic example:

- **401 Unauthorized:** missing or invalid authentication credentials; the entry point may send WWW-Authenticate.
- **403 Forbidden:** already authenticated yet lacking permission for the resource or rejected by policies like CSRF.

If a user with ROLE_USER hits an endpoint requiring ROLE_ADMIN, returning 403 is right. Do not try to turn **every 403 into 401** for anti-enumeration; that is a separate authorization concern. What must stay unified is that **authentication failure branches expose the same public information level**.

## 5. How Does DaoAuthenticationProvider Help?

In Spring Security 6.x, for standard username/password, **DaoAuthenticationProvider** uses UserDetailsService and PasswordEncoder. It inherits behavior from **AbstractUserDetailsAuthenticationProvider**.

### 5.1. hideUserNotFoundExceptions

By default, **hideUserNotFoundExceptions=true** on AbstractUserDetailsAuthenticationProvider. When UserDetailsService cannot find the username, the provider can translate UsernameNotFoundException into **BadCredentialsException**, matching the wrong-password case.

This reduces differences observable through basic exception types. Never call **setHideUserNotFoundExceptions(false)** in public flows just to display "Account does not exist", as that reopens an account-disclosure channel.

One crucial note: even if internal backends classify reasons differently, **exception messages and causes must never be serialized straight into JSON**, especially when custom failure handlers or global exception resolvers exist.

### 5.2. Never substitute UserDetailsService for authentication

This is wrong thinking:

~~~java
UserDetails user = users.loadUserByUsername(username);
// Finding a user does not mean the caller's password is correct.
return UsernamePasswordAuthenticationToken.authenticated(
    user, null, user.getAuthorities()
);
~~~

This snippet is an **illustrative anti-pattern**—never use it to implement login.

It has not verified the raw password, has not checked all account status flags, and risks granting identity to anyone merely knowing a username. Use Spring Security's built-in provider, or a security-designed and tested mechanism.

### 5.3. PasswordEncoder.matches

PasswordEncoder checks raw passwords against stored hashes. With BCrypt or Argon2, password hashing is computationally expensive; thus, the existing-user branch naturally performs costlier work than a missing-user branch.

If you carelessly return immediately when a username does not exist, an attacker can measure timing repeatedly and infer the difference despite identical messages and status codes.

DaoAuthenticationProvider includes a technique to reduce timing discrepancy on the non-existent user branch by performing a match against a dummy hash. Still, **do not treat this default technique as a guarantee of identical response times across every branch and every version**.

## 6. Why Is Unifying the Message Alone Insufficient?

### 6.1. Early exit creates a timing side channel

Common pseudocode:

~~~text
if (!accountExists(username)):
    return genericFailure

if (!passwordEncoder.matches(rawPassword, storedHash)):
    return genericFailure
~~~

Externally both show "Unable to log in", yet the first branch finishes right after lookup while the second computes BCrypt/Argon2. Across many measurements, statistical differences can reveal whether the account exists.

**Solution direction:** use a maintained authentication component with proper timing mitigations; check the latest patches and avoid homegrown early returns. If forced to write a custom provider, analyze unknown-user, locked/disabled, cache hit/miss, DB lookup, encoder work, and abnormal variance branches.

### 6.2. Do not use a fixed Thread.sleep to "prevent timing attacks"

For example, calling Thread.sleep(200) only on the unknown-user branch **does not guarantee equal timing**: CPU load, database, caches, retries, GC, and server load all vary. Fixed delays can also hurt throughput or create new measurement channels. Prefer expert-vetted mechanisms, rate limiting, and real side-channel analysis.

You do not need to promise nanosecond-identical processing times for every request; the goal is eliminating **consistent, exploitable** differences alongside layers limiting large-scale probing.

### 6.3. Body size and structure are also signals

Two bodies:

~~~json
{"error":"invalid_credentials"}
~~~

and:

~~~json
{"error":"invalid_credentials","hint":"reset_password_for_existing_user"}
~~~

share the same error prefix yet differ in content/size and hint at account existence. If guidance is needed, include a **generic password-recovery link** on all login errors rather than showing it only for real users.

### 6.4. Redirects and HTTP headers

Form login may show the same UI text while redirecting differently:

~~~text
No account  -> /login?error=user_missing
Has account -> /login?error=wrong_password
~~~

The query parameter itself exposes the difference. Likewise, custom headers such as X-Account-Status or distinct HTTP 404/423 codes for unverified accounts create disclosure channels.

Test **status, Location, WWW-Authenticate, Content-Type, Cache-Control, body, and body size** across equivalent failures.

## 7. Spring Boot Example: Consistent 401 Response for All Login Failures

The example uses HTTP Basic for easy verification with curl. It keeps standard DaoAuthenticationProvider/UserDetailsService/PasswordEncoder and sets a **unified AuthenticationEntryPoint** for authentication errors.

**Scope:** Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x, Spring MVC/Servlet. The code fits this version family's syntax, yet **response timing in 6.3.x requires checking the CVE in section 8**. The example proves standardized public responses only, not elimination of every timing side channel. Production deployments must use dependencies updated with security patches.

### 7.1. Gradle dependency

In a Spring Boot project with Gradle plugin and Gradle Wrapper, **build.gradle** (Groovy DSL) needs:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is the **dependencies** block of a project with the Spring Boot plugin and Java 17 configured, not an entire standalone build.gradle file. Spring Boot manages starter versions via the chosen BOM.

### 7.2. Complete Java file

Create **src/main/java/com/example/safeauth/SafeAuthApplication.java**:

~~~java
package com.example.safeauth;

import java.nio.charset.StandardCharsets;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SafeAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(SafeAuthApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("learn123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build(),
            User.withUsername("locked")
                .password(encoder.encode("locked123"))
                .roles("USER")
                .accountLocked(true)
                .build(),
            User.withUsername("disabled")
                .password(encoder.encode("disabled123"))
                .roles("USER")
                .disabled(true)
                .build()
        );
    }

    // Same response for any authentication failure.
    @Bean
    AuthenticationEntryPoint genericFailureEntryPoint() {
        return (request, response, exception) -> {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.setHeader(
                HttpHeaders.WWW_AUTHENTICATE, "Basic realm=\"lesson\"");
            response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
            response.getWriter()
                .write("{\"error\":\"invalid_credentials\"}");
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationEntryPoint genericFailure)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/private").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(basic -> basic
                .authenticationEntryPoint(genericFailure)
            )
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(genericFailure)
                .accessDeniedHandler((request, response, exception) -> {
                    response.setStatus(HttpServletResponse.SC_FORBIDDEN);
                    response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                    response.setCharacterEncoding(
                        StandardCharsets.UTF_8.name());
                    response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
                    response.getWriter()
                        .write("{\"error\":\"access_denied\"}");
                })
            )
            .formLogin(form -> form.disable())
            .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/private")
    String privateEndpoint() {
        return "private OK";
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}
~~~

This is a **single Java file inside a Spring Boot project**: the public class matches the filename, and DemoController is a package-private class in the same package discovered by component scanning. Java 17 supports lambdas; Spring Boot 3 uses the `jakarta.servlet` namespace.

The accounts **alice, admin, locked, disabled** and passwords in source **are for local study only**. Never use demo passwords in production; never create locked/disabled accounts with fixed passwords in real environments. In real systems, use a managed identity store, Secret Manager, and proper password policies.

### 7.3. Configuration explanation

**UserDetailsService** provides four illustrative states:

- alice: active account, ROLE_USER.
- admin: active account, ROLE_ADMIN.
- locked: locked account.
- disabled: disabled account.

**PasswordEncoder** uses BCrypt. With UserDetailsService and PasswordEncoder beans present, Spring Security can configure DaoAuthenticationProvider for standard username/password flows.

**genericFailureEntryPoint** owns the public contract when a request lacks valid authentication:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
WWW-Authenticate: Basic realm="lesson"
Cache-Control: no-store

{"error":"invalid_credentials"}
~~~

In the example, both the HTTP Basic filter and exception handling use this entry point. As a result, missing credentials, wrong passwords, unknown usernames, and locked/disabled accounts can be handled with **the same status, the same key headers, and the same body**.

**AccessDeniedHandler** returns 403 with error code `access_denied` when an authenticated user lacks the required role. That is the **authorization** branch, distinct from authentication failure.

**formLogin.disable** merely keeps the Basic demo easy to test; if a browser app uses form login, configure a dedicated AuthenticationFailureHandler/standardized form URL as shown in section 10.

### 7.4. Never leak exceptions in responses

The AuthenticationEntryPoint lambda receives the exception parameter yet **never emits exception.getMessage(), exception.getClass(), cause, or stack trace to the client**. This is intentional and critical.

In real applications, the system still needs internal logging/auditing per policy to detect attacks and support users. However, those logs must have restricted access, bounded retention, and never contain raw passwords, tokens, Authorization headers, or excessive identifying data.

### 7.5. Distinguishing response consistency from timing security

The example demonstrates **consistent response structure**. It **does not guarantee** that processing times for locked/disabled users match unknown users on Spring Security versions affected by the advisory.

Preventing enumeration in production requires combining **patched versions, controlled timing tests, rate limiting, monitoring, limiting public metadata**, and sound account/recovery design. Never judge safety by JSON output alone.

## 8. Version-Specific Security Note: CVE-2026-22746

On **April 20, 2026**, Spring published advisory **CVE-2026-22746 — User Attribute Enumeration when Using DaoAuthenticationProvider**. According to the advisory, when using **isEnabled, isAccountNonExpired, or isAccountNonLocked** states, DaoAuthenticationProvider's timing-attack mitigation could be bypassed for disabled, expired, or locked accounts on affected versions.

Spring Security version ranges listed by the advisory:

| Branch | Affected versions | Announced patched versions |
| --- | --- | --- |
| 6.3 | 6.3.0 to 6.3.15 | 6.3.16, Enterprise Support Only |
| 6.4 | 6.4.0 to 6.4.15 | 6.4.16, Enterprise Support Only |
| 6.5 | 6.5.0 to 6.5.9 | 6.5.10, OSS |
| 7.0 | 7.0.0 to 7.0.4 | 7.0.5, OSS |
| 5.8 | 5.8.0 to 5.8.24 | 5.8.25, Enterprise Support Only |

Source: https://spring.io/security/cve-2026-22746/

**Implications for this lesson:** the demo on Spring Boot 3.3.x/Security 6.3.x illustrates APIs/configuration, not a timing-remediated production blueprint. Even with identical 401 + JSON, locked/disabled users could be distinguished via timing on versions listed in the advisory.

**Practical action:** check the Spring Security version managed by your BOM; upgrade to a fixed and supported version while ensuring Spring Boot compatibility and testing the full authentication flow. Never arbitrarily force Security 6.5 into a Boot 3.3 app just because a patched version exists. Follow the release/security advisory matching your system.

Spring's patch introduced **DaoAuthenticationProvider.setAlwaysPerformAdditionalChecksOnUser**; do not disable the new check merely to save CPU without analyzing the risk. Never claim a configuration is safe solely because UsernameNotFoundException does not appear in responses.

### 8.1. Why mention this vulnerability when learning fundamentals?

Because anti-enumeration has **two layers**:

1. **Output behavior:** messages, HTTP status, redirects, bodies, and headers do not distinguish real accounts.
2. **Processing behavior:** execution paths and processing times must lack consistent, exploitable differences across states.

A lesson stopping at generic error messages could leave learners overlooking the second layer, especially when systems have locked/disabled accounts.

## 9. Hands-On with curl: Verifying Identical Failures

In the directory containing Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell use **.\gradlew.bat bootRun**. Assuming the server listens on localhost:8080.

Run curl:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -u ghost:anything http://localhost:8080/private
curl -i -u alice:wrong http://localhost:8080/private
curl -i -u locked:locked123 http://localhost:8080/private
curl -i -u disabled:disabled123 http://localhost:8080/private
curl -i -u alice:learn123 http://localhost:8080/private
curl -i -u alice:learn123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
~~~

On PowerShell you may need **curl.exe** because curl is an alias. For real credentials, run **curl -u alice URL** so curl prompts for the password rather than saving it in shell history. HTTP Basic requires HTTPS over networks; example passwords are for isolated localhost use only.

### 9.1. Expected result matrix

| Request | Status | Body/meaning |
| --- | --- | --- |
| GET /public anonymous | **200** | public OK |
| GET /private anonymous | **401** | {"error":"invalid_credentials"} |
| GET /private unknown user ghost | **401** | **Same body** |
| GET /private alice wrong password | **401** | **Same body** |
| GET /private locked valid password | **401** | **Same body** |
| GET /private disabled valid password | **401** | **Same body** |
| GET /private alice valid password | **200** | private OK |
| GET /admin alice valid password | **403** | {"error":"access_denied"} |
| GET /admin admin valid password | **200** | admin OK |

The table reflects **expectations from the demo config**, not measured run logs. MockMvc in a later section verifies the HTTP contracts yet still does not test timing side channels.

For the 401 branches, also compare WWW-Authenticate, Content-Type, Cache-Control, and Location (if present). **Date** headers or operational metadata may vary per request, yet must not vary **by account state**.

### 9.2. Why should 401 responses have a consistent WWW-Authenticate header?

HTTP Basic is an HTTP authentication scheme. WWW-Authenticate tells clients to send Basic credentials within a realm. If it is absent or uses different realms depending on whether a username exists, that header itself creates a distinguishing channel.

The code example sets the exact same **Basic realm="lesson"** for all authentication failures. This is a demo realm; production chooses a clear security-scoped realm and never puts account names or user states into the realm.

### 9.3. Valid login lacking permissions is not a username enumeration bug

When alice logs in validly and accesses /admin, she gets 403. The system already knows her identity and evaluates authorization per ROLE_ADMIN. **Do not return generic invalid_credentials here**, as that conflates authorization with authentication and hurts debugging.

## 10. How Should Form Login Handle This?

Form login differs from HTTP Basic in response behavior: when a user POSTs a failed form login, Spring Security invokes **AuthenticationFailureHandler**, usually redirecting back to the login page with an error parameter.

To control the failure handler, you can configure:

~~~java
.formLogin(form -> form
    .failureUrl("/login?error")
)
~~~

This is a **snippet inside a SecurityFilterChain with form login and a matching /login route**, not a standalone Java file. For a custom login page, write the controller/template and permitAll the route properly.

Principles:

- Unknown username -> same redirect /login?error.
- Existing username + wrong password -> same redirect.
- Locked/disabled -> same redirect for unverified callers.
- The login page displays **one generic message**, never rendering exception.getMessage().
- Never append username, account state, internal codes, or exception names to the URL.
- Verify cookies, sessions, CSRF tokens, and request cache across the browser flow.
- When public pages may be cached, set proper cache controls so personal states never leak.

**Never use params like /login?error=user_not_found and /login?error=locked.** Even if the template renders one generic sentence, the URL itself is public output readable by attackers.

### 10.1. How can legitimate users still get help?

The generic error page can include the exact same "Forgot password?" or "Contact support" link for every case. If a user genuinely owns the account, a well-designed recovery flow lets them proceed without disclosing account existence to outsiders.

A personalized support page shown after verification can provide far more detail than the public login page.

## 11. Password Reset and Forgotten Username

User enumeration happens even more easily in **password reset** because developers want to tell users whether the entered email is registered.

Unsafe example:

~~~text
POST /forgot-password with real email    -> 200 "Email sent"
POST /forgot-password with missing email -> 404 "Email not registered"
~~~

A better approach for syntactically valid requests:

~~~json
{
  "message": "If the provided address matches an account, recovery instructions will be sent through the registered channel."
}
~~~

Same body and status whether an account matches the email or not, and never include internal account IDs/tokens in the response. The system dispatches a notification **only when a matching account exists**, yet outsiders cannot infer that from the synchronous response.

### 11.1. Do not let email-sending duration leak existence

If the existing-email branch makes a synchronous SMTP call during the request while the missing-email branch returns immediately, response times will differ. Consider **queued/async message dispatch**, consistent processing paths, and rate limiting. You do not need to send fake emails to non-existent addresses if that risks spam or cost; the goal is minimizing observable signals on the public request.

### 11.2. Reset tokens must have strong properties of their own

Reset tokens must be unpredictable, time-limited, single-use, bound to the right account, and stored/protected safely. Never put tokens in logs, analytics URLs, or error pages. After a reset, consider invalidating old sessions/tokens and notifying the user via verified channels.

**Generic responses do not replace sound reset-token design.** They protect only one facet of account-existence disclosure.

## 12. Account Registration, Resending OTP, and MFA

### 12.1. Email registration

On a public registration endpoint, checking duplicate emails can expose which users already exist. Product UX might want to say "email already in use", yet sensitive systems should design **generic responses and an email-ownership verification channel** before disclosing status.

One pattern is accepting valid registration requests with the same response, then emailing appropriate instructions to the user-controlled address. Enforce anti-abuse controls, prevent duplicate account creation, and avoid revealing status via timing.

### 12.2. Resending OTP

A verification-code resend endpoint can leak whether a phone number/email has an account if it replies "Phone number not found". Instead, return a generic message about processing valid requests and enforce rate limits to prevent SMS/email spam.

### 12.3. MFA

In flows requiring MFA, never let a public endpoint return "Account alice does not have MFA enabled" before the caller proves identity. Once the password is verified and the MFA flow is safely bound to a temporary session, the system can guide the next step.

Bound challenge lifetimes, prevent replay, cap OTP attempts, and never let challenge contents serve as an oracle confirming an arbitrary account exists.

## 13. Rate Limiting, Lockout, and Anti-Abuse

Generic error messages hide account existence on a single request, yet attackers can probe thousands of usernames and measure differences. Hence **defense in depth** is essential:

- Limit attempts per IP or network block while considering normalized account identifiers.
- Limit concurrency and volume service-wide, especially on login, forgot-password, registration, and OTP.
- Use risk-based backoff/challenges instead of relying solely on an easily bypassed CAPTCHA.
- Monitor password spraying (few passwords across many users) and credential stuffing (many user/password pairs).
- Avoid permanently locking a victim's account merely because outsiders deliberately send wrong passwords.
- Design 429, Retry-After, or challenges so policy differences do not reveal real accounts.
- Establish verified account recovery policies and support channels.

### 13.1. Rate limiting by IP alone is insufficient

Attackers can rotate across proxies/IPs, while many legitimate users can share a single NAT IP. Combine multiple signals: IP, client/device reputation, normalized identifier, timing, session, region, recent attempts, and behavioral patterns.

Tracking attempt counters per username must **never make public endpoints reveal account existence**. For example, redirecting a real username straight to an "Account locked" page while fake usernames keep getting "Bad password" creates an account-disclosure signal.

### 13.2. Do not let lockout become a DoS tool

Locking an account after a few wrong passwords can be abused by attackers to block legitimate owners from logging in. Balance security and availability: bounded backoff, verification policies, recovery paths, bot defenses, and monitoring.

No single fixed lockout/rate-limit threshold fits every product; tune based on risk, scale, resilience, threat intelligence, and telemetry.

### 13.3. Rate-limit responses must be consistent under the same conditions

You may return HTTP 429 when throttling applies, yet never let **only real usernames** receive 429 under identical test scenarios. Review counter keys and trigger conditions; even a generic error inside a 429 can reveal an account through frequency or when it triggers.

## 14. Logging and Auditing: Detailed for Operations, Silent to Clients

Security teams need to know how many authentication failures occur, their failure categories, and attack indicators. Therefore you should not **erase all internal reasons**.

A logging strategy may include:

| Log field | Handling direction |
| --- | --- |
| Event name | AUTH_FAILURE or similar |
| Timestamp, request ID | Record for correlation and investigation |
| Internal failure category | May be logged with restricted access |
| Client IP | Apply personal data and retention policies |
| Username/email | Avoid raw logging in general streams; if truly needed, use reduced-identifiability forms with strict access control |
| Raw password, Authorization, OTP, token | **Never record** |
| Full Authentication/Principal | Never log raw objects that may contain secrets/PII |
| Exception stack trace | Only in controlled internal systems; never in responses |
| Public HTTP response | Generic code and body per contract |

A very common mistake is writing:

~~~java
// Do not use in production:
log.warn("Login failed for {}: {}", username, exception);
~~~

This statement can include client-supplied usernames, status details, and exception internals; logs often flow into centralized systems or dashboards viewed by many people. Never print raw Authentication or request headers for "quick debugging".

In real systems, use a **dedicated audit pipeline, field allowlists, log redaction, access controls, and retention**, letting security responders investigate without creating an unintended secret store.

### 14.1. Never put internal reasons into responses

Do not write:

~~~java
response.getWriter().write(
    "{\"error\":\"" + authenticationException.getClass().getSimpleName() + "\"}"
);
~~~

This is an **illustrative anti-pattern**, not safe code. The exception class name distinguishes UsernameNotFoundException, LockedException, DisabledException, and InternalAuthenticationServiceException.

Map them to **one unified public code** for eligible authentication errors, such as invalid_credentials, keeping details inside access-controlled systems.

## 15. MockMvc Tests for the Public Failure Contract

Testing responses is more valuable than simply opening a browser and looking at the same display message. Assert **status, body, and WWW-Authenticate** across equivalent scenarios.

After adding testImplementation spring-boot-starter-test in section 7, create **src/test/java/com/example/safeauth/SafeAuthApplicationTest.java**:

~~~java
package com.example.safeauth;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SafeAuthApplicationTest {

    @Autowired
    MockMvc mvc;

    private String basic(String user, String password) {
        String pair = user + ":" + password;
        String value = Base64.getEncoder()
            .encodeToString(pair.getBytes(StandardCharsets.UTF_8));
        return "Basic " + value;
    }

    private MvcResult expectSameFailure(String user, String password)
            throws Exception {
        return mvc.perform(get("/private")
                .header(HttpHeaders.AUTHORIZATION, basic(user, password)))
            .andExpect(status().isUnauthorized())
            .andExpect(content().json(
                "{\"error\":\"invalid_credentials\"}"))
            .andReturn();
    }

    @Test
    void failedLoginsDoNotRevealAccountStateInHttpBody()
            throws Exception {

        MvcResult unknown = expectSameFailure("ghost", "anything");
        MvcResult wrong = expectSameFailure("alice", "wrong");
        MvcResult locked = expectSameFailure("locked", "locked123");
        MvcResult disabled = expectSameFailure(
            "disabled", "disabled123");

        String publicBody = unknown.getResponse().getContentAsString();

        assertEquals(publicBody,
            wrong.getResponse().getContentAsString());
        assertEquals(publicBody,
            locked.getResponse().getContentAsString());
        assertEquals(publicBody,
            disabled.getResponse().getContentAsString());

        String challenge = unknown.getResponse()
            .getHeader(HttpHeaders.WWW_AUTHENTICATE);

        assertEquals(challenge, wrong.getResponse()
            .getHeader(HttpHeaders.WWW_AUTHENTICATE));
        assertEquals(challenge, locked.getResponse()
            .getHeader(HttpHeaders.WWW_AUTHENTICATE));
        assertEquals(challenge, disabled.getResponse()
            .getHeader(HttpHeaders.WWW_AUTHENTICATE));
    }

    @Test
    void authenticationAndAuthorizationRemainSeparate()
            throws Exception {
        mvc.perform(get("/private")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("alice", "learn123")))
            .andExpect(status().isOk())
            .andExpect(content().string("private OK"));

        mvc.perform(get("/admin")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("alice", "learn123")))
            .andExpect(status().isForbidden())
            .andExpect(content().json(
                "{\"error\":\"access_denied\"}"));

        mvc.perform(get("/admin")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin OK"));
    }
}
~~~

This is a **complete test file** in the same demo project, using only MockMvc and Base64-built Basic headers. It does not need spring-security-test just to test HTTP Basic because the header is built in the helper.

Run:

~~~bash
./gradlew test
~~~

In PowerShell use **.\gradlew.bat test**.

### 15.1. What does this test prove?

- Unknown user, wrong password, locked, and disabled branches all return 401.
- JSON bodies across all failure branches are identical.
- WWW-Authenticate headers across all failure branches are identical.
- Alice logging in properly can still access authenticated endpoints.
- Alice lacking the ADMIN role gets 403 and is not misreported as invalid credentials.
- Admin with the proper role gets 200.

### 15.2. What does this test NOT prove?

- **Does not prove protection against timing side channels.** MockMvc does not reflect real networks, real DBs, caches, CPU, JIT, GC, contention, SSL/proxies, and latency distributions.
- Does not prove rate limiting, CAPTCHA, account recovery, or auditing are configured.
- Does not check email side effects of reset/registration.
- Does not guarantee the body of every exception from filters outside SecurityFilterChain follows the same schema.
- Does not replace reviewing security advisories and running integration/performance tests on patched dependencies.

Timing measurements must be conducted in an authorized test environment with controlled test data and proper statistical methods. **Never rely on a handful of curl commands to conclude a system is timing-safe.**

## 16. Defensive Testing Technique: Non-Disclosure Matrix

Include these columns for a login test plan:

| Scenario | Status | Public code/body | Redirect/headers | Risk to evaluate |
| --- | --- | --- | --- | --- |
| Username does not exist | 401 | Generic | Generic | Fast lookup, timing |
| Username exists, wrong password | 401 | Generic | Generic | Hash cost |
| Account disabled | 401 | Generic | Generic | Pre-check timing, advisory |
| Account locked | 401 | Generic | Generic | Account state/rate limit |
| Account expired | 401 | Generic | Generic | Pre-check, recovery path |
| Valid password, valid user | 200 | Login result | Per auth mechanism | Do not leak secrets |
| Logged in yet lacks role | 403 | access_denied | Per authorization | Do not confuse with login |
| Login service temporarily down | Operational policy | Generic system error | No SQL details | Availability/error handling |

This matrix is a **design target**, not a guarantee that every Spring Security mechanism/version provides it out of the box. With multiple SecurityFilterChains, check entry points and failure handlers **inside each chain**. Never assume one chain's config automatically applies to another chain.

### 16.1. Why inspect network responses instead of only the UI?

The UI might hide a differing status in Developer Tools, or JavaScript might receive an internal error code from the API and display generic text. Attackers calling the API directly still see the difference. Always inspect **actual endpoint responses**, including status, headers, body, redirects, and timing.

### 16.2. Testing form login

For form login, compare unknown/wrong/locked/disabled:

- Do they redirect to the exact same URL?
- Same method/status and same query params?
- Same error template and comparable response size?
- Does any branch render "Account locked"?
- Does session/cookie flow differ by account state?
- Are any email/SMS events triggered that let outsiders infer the outcome?

Where the UI must help verified accounts, provide a separate flow after proving ownership; never put those branches into public username-probing endpoints.

## 17. Dangerous Coding Mistakes

### 17.1. Returning AuthenticationException message directly

~~~java
// Wrong: exception may expose account state.
response.getWriter().write(exception.getMessage());
~~~

Even if the default message happens to be "Bad credentials" today, swapping providers, localization, or custom exceptions later can turn that message into sensitive data. Choose an explicit public error code.

### 17.2. Turning UsernameNotFoundException into HTTP 404

~~~text
UsernameNotFoundException -> HTTP 404
BadCredentialsException   -> HTTP 401
~~~

This creates an account-confirmation oracle. On login endpoints, whether a user resource exists **must not** dictate public HTTP status codes this way.

### 17.3. Locking accounts and announcing the lock to everyone

If anyone entering a locked username sees "This account has been locked after 5 failed attempts", attackers learn the account is real. It also enables DoS by deliberately locking a victim's account. Combine authentication flow, throttling, and safe recovery.

### 17.4. Exposing a separate user-check API before login

A public endpoint like `GET /users/exists?email=...` defeats all anti-enumeration efforts on `/login`. Audit the **entire product surface**: autocomplete, invitations, support, reset, registration, resend activation, email change, and profile lookup.

### 17.5. Always returning 200 with differing bodies

Returning HTTP 200 for all errors is unsafe if JSON contains an `accountFound` field or differing hints. Never use a single status code as a "shield" while responses still branch on existence.

### 17.6. Comparing passwords manually with equals

Passwords must be stored as proper hashes and verified with `PasswordEncoder.matches`. Comparing `String.equals(raw, storedHash)`, storing plaintext, or using unsuitable hash algorithms breaks authentication and raises credential exposure risk.

### 17.7. Ignoring dependency vulnerabilities

A unified handler only normalizes public responses; it does not fix a timing vulnerability inside a provider. Check advisories and upgrade dependencies to patched releases rather than merely masking messages.

### 17.8. Relying on "account does not exist" messages to support users

Real users can mistype emails, yet telling anonymous callers creates an enumeration vector. Use generic guidance, password-reset paths, and an ownership-verified support flow to help legitimate users safely.

## 18. Deployment Checklist

Before shipping login or password reset to production, verify:

1. **Failed logins:** non-existent user, wrong password, and locked/disabled/expired accounts share the same public code/body/status across equivalent flows.
2. **No leaks via headers/redirects:** no exception names, account states, or distinct URLs.
3. **Timing:** no custom early exits; lookup/hash/status/cache branches evaluated and patched provider versions used.
4. **Authentication provider:** use a maintained mechanism; never flip `hideUserNotFoundExceptions` to false on public flows without evaluated justification.
5. **Successful logins:** principal/authorities come from trusted sources; no passwords/secrets in JSON.
6. **Missing permissions:** proper HTTP 403 once authenticated, never misreported as "wrong password".
7. **Reset/registration/OTP:** check related endpoints for enumeration, including side effects.
8. **Rate limiting:** throttle automated probing without creating account-existence signals or mass lockouts.
9. **Logging:** never log passwords/tokens/Authorization, restrict raw identifiers, keep audit reasons in access-controlled systems.
10. **Sessions and tokens:** CSRF, HTTPS, cookie flags, TTL, logout, and revocation suited to client architecture.
11. **Testing:** test HTTP contracts, redirects, headers, case normalization, caching, and timing in authorized environments.
12. **Dependencies:** check Spring Security/BOM against security advisories; re-test after upgrades.
13. **System error path:** never emit SQL/stack traces, and avoid coupling system failure states to account existence.
14. **UI copy:** only generic messages for unverified callers; specific help sits behind ownership verification.
15. **Monitoring:** detect password spraying, credential stuffing, lockout abuse, and failure spikes.

## 19. Self-Check Questions and Answers

**Question 1.** Why are "Wrong password" when the user exists and "User not found" when the user does not exist dangerous?  
**Answer:** Those two responses let callers confirm whether a user exists without knowing the password, enabling user enumeration.

**Question 2.** Is returning the same JSON error enough to stop enumeration?  
**Answer:** No. Status codes, redirects, headers, response sizes, timing, rate limits, and side effects can also disclose account state.

**Question 3.** What mechanism does AbstractUserDetailsAuthenticationProvider have regarding UsernameNotFoundException?  
**Answer:** `hideUserNotFoundExceptions` defaults to true, usually translating unknown usernames into BadCredentialsException instead of distinguishing them publicly.

**Question 4.** Should you enable `setHideUserNotFoundExceptions(false)` to make login debugging easier?  
**Answer:** No, not in public flows without security review; use safe internal auditing/observability instead.

**Question 5.** Why might a username missing from the DB respond faster than a real user with a wrong password?  
**Answer:** The missing-user branch can skip expensive hash comparison work, creating a timing side channel.

**Question 6.** Does Spring Security guarantee timing protection for locked/disabled accounts in all versions?  
**Answer:** No. Check versions and security advisories; CVE-2026-22746 documents affected versions.

**Question 7.** In the demo, what should ghost, alice with wrong password, locked, and disabled receive?  
**Answer:** The same HTTP 401, same `invalid_credentials` body, and same `WWW-Authenticate`; timing must still be evaluated separately.

**Question 8.** If Alice logs in successfully yet gets 403 on the admin endpoint, is that user enumeration?  
**Answer:** No; that is authorization with an already-known identity and should stay distinct from authentication failures.

**Question 9.** How should password reset respond when an email has no account?  
**Answer:** Return a generic notice for valid requests, such as "If a matching account exists, instructions will be sent," without disclosing account existence.

**Question 10.** Why is rate limiting login by IP alone not enough?  
**Answer:** Attackers can distribute across many IPs, while many legitimate users can share a single IP/NAT.

**Question 11.** Should you log the full `AuthenticationException.getMessage()` into responses to assist customers?  
**Answer:** No. Internal reasons can leak account state; expose only generic codes publicly and keep detailed audits in protected systems.

**Question 12.** Does a MockMvc test checking identical body/status prove the timing CVE is mitigated?  
**Answer:** Not yet. It verifies the HTTP contract, not latency distributions or unpatched dependencies.

**Question 13.** What is the risk of showing "Account locked" on the public login page for a locked account?  
**Answer:** Outsiders can confirm the username exists; use a generic error and a verified recovery channel.

**Question 14.** Why should you not manually add `Thread.sleep` to the unknown-user branch?  
**Answer:** A fixed delay cannot balance real processing variance, can introduce a new side channel, and degrades availability.

## 20. Official Reference Documentation

- OWASP Authentication Cheat Sheet — Authentication Responses, User Enumeration, and Rate Limiting: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- Spring Security Advisory CVE-2026-22746 (April 20, 2026): https://spring.io/security/cve-2026-22746/
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Security — Form Login Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
- Spring Security — Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security — Servlet Security Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — Authorization HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Boot 3.3 — Spring Security Configuration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
